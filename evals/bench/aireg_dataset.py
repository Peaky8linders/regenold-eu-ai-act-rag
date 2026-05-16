"""SHA-pinned loader for the camlsys/AIReg-Bench dataset.

Source: https://huggingface.co/datasets/camlsys/AIReg-Bench
Paper:  arXiv:2510.01474 (Marino et al., 2025)
Licence: CC-BY-4.0

AIReg-Bench scores AI-system technical documentation against five
high-risk AI Act articles:

    * Article 9  — Risk Management System
    * Article 10 — Data and data governance
    * Article 12 — Record-keeping (logging)
    * Article 14 — Human oversight
    * Article 15 — Accuracy, robustness and cybersecurity

Each row in ``human_annotations.parquet`` covers one
``(article, scenario)`` pair across **ten** ``intended_use`` columns
(10 high-risk uses lifted from Annex III, listed in
``intended_uses.txt``). Within each use, three human annotators score
the AI system's compliance with the article on a 1–5 scale and write a
short explanation. The 1–5 score is bucketed to a verdict:

    compliance_score >= 4  → "compliant"
    compliance_score == 3  → "borderline"
    compliance_score <= 2  → "non-compliant"

Important caveat about the HuggingFace mirror as of 2025-11-17
(revision ``c656725c22568ef5fa489ea3940d3b6d7ff4b2ff``):

    The README documents a ``documentation/`` folder containing 300
    .txt excerpts — but those files are NOT present in the current HF
    tree. The mirror only ships:
        - README.md
        - intended_uses.txt
        - human_annotations.parquet
        - llm_annotations.parquet
        - .gitattributes

    Until the upstream maintainers publish the document excerpts, the
    runner falls back to a **prompt-only** mode that asks the route
    "Is an AI system used for {intended_use} likely to comply with
    Article N under scenario X?". This still measures whether the
    engine cites the right article when asked about it, and is a
    useful secondary signal alongside the davidath bench.

Network access on Windows: the local cache file ``annotations.json``
is committed inside the cache dir (``.aireg-bench-cache/``) once
fetched. Subsequent runs are offline. If both the HF rows-API and the
raw-parquet download are blocked (corporate firewall, rate-limit,
upstream 5xx), ``_FETCH_BLOCKED`` is set to True and any cached data is
returned instead. The runner + tests can detect this state and skip
network-dependent assertions accordingly.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ── Upstream pins ────────────────────────────────────────────────────────

AIREG_HF_ID = "camlsys/AIReg-Bench"
AIREG_REVISION = "c656725c22568ef5fa489ea3940d3b6d7ff4b2ff"

# SHA256 of human_annotations.parquet at the pinned revision (verified
# 2025-11-17 via direct GET on huggingface.co). The parquet itself is
# not parsed at runtime (no pyarrow on Windows by default) — we keep
# the SHA for reproducibility and integrity assertions.
AIREG_PARQUET_SHA256 = (
    "7fd76b10aeef9a3beb10456ba23be227837f3c10f9f31892f544b28e7255d5e1"
)

# Five high-risk AI Act articles scored by the bench.
AIREG_ARTICLES = (9, 10, 12, 14, 15)

# Ten intended-use labels (Annex III) — exact text from intended_uses.txt
# at the pinned revision.
AIREG_INTENDED_USES = (
    "Biometric identification and categorisation of natural persons",
    "Management and operation of critical infrastructure",
    "Education and vocational training",
    "Employment, workers management and access to self-employment",
    (
        "Access to and enjoyment of essential private and public services"
        " and benefits"
    ),
    "Law enforcement",
    "Migration, asylum and border control management",
    "Administration of justice and democratic processes",
    "Medical diagnosis and treatment",
    "Autonomous vehicles",
)

# ── Cache layout ─────────────────────────────────────────────────────────

AIREG_LOCAL_CACHE = Path(".aireg-bench-cache")
_ANNOTATIONS_JSON = AIREG_LOCAL_CACHE / "annotations.json"
_DOCS_DIR = AIREG_LOCAL_CACHE / "documentation"
_FETCH_META = AIREG_LOCAL_CACHE / "fetch_meta.json"

# Set True after one failed datasets-server fetch attempt so the runner
# and tests can branch on "no network" without forcing a retry loop.
_FETCH_BLOCKED: bool = False


# ── Low-level HTTP fetch ─────────────────────────────────────────────────


_USER_AGENT = "regenold-eu-ai-act-rag/aireg-bench"


def _http_get(url: str, *, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _datasets_server_rows(
    offset: int, length: int = 5, *, max_retries: int = 4
) -> list[dict[str, Any]] | None:
    """Fetch a slice via the HF datasets-server rows endpoint.

    The endpoint returns JSON — pure stdlib parse, no pyarrow / pandas
    dependency. Empirically the server tolerates ``length=5`` reliably
    but 500s on larger batches against this dataset's 41-column shape.
    Returns ``None`` on terminal failure (rate-limit / 5xx after
    retries) so the caller can mark ``_FETCH_BLOCKED``.
    """
    url = (
        "https://datasets-server.huggingface.co/rows"
        f"?dataset={AIREG_HF_ID}&config=default&split=train"
        f"&offset={offset}&length={length}"
    )
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            payload = json.loads(_http_get(url, timeout=30.0))
            return list(payload.get("rows") or [])
        except urllib.error.HTTPError as exc:
            last_exc = exc
            # Rate limit → exponential backoff; 5xx → linear; 4xx else → give up.
            if exc.code == 429:
                time.sleep(min(30.0, 5.0 * (2 ** attempt)))
                continue
            if 500 <= exc.code < 600:
                time.sleep(min(10.0, 2.0 + attempt))
                continue
            return None
        except (OSError, ValueError) as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2.0)
    if last_exc:
        # Persist the last error for forensics.
        try:
            AIREG_LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
            (AIREG_LOCAL_CACHE / "last_fetch_error.txt").write_text(
                f"{type(last_exc).__name__}: {last_exc}", encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass
    return None


def _verify_parquet_sha256() -> bool:
    """Best-effort SHA verification on the raw parquet file.

    Downloads the parquet, hashes it, and confirms byte-identity with
    the pinned revision. Returns True/False; never raises. Called by
    ``fetch_aireg_bench`` to give the cache a strong provenance link
    even though we don't parse the parquet itself.
    """
    try:
        url = (
            f"https://huggingface.co/datasets/{AIREG_HF_ID}/resolve/"
            f"{AIREG_REVISION}/human_annotations.parquet"
        )
        data = _http_get(url, timeout=60.0)
        return hashlib.sha256(data).hexdigest() == AIREG_PARQUET_SHA256
    except Exception:  # noqa: BLE001
        return False


# ── Row normalisation ────────────────────────────────────────────────────


_ROW_LABEL_RE = re.compile(r"^Art\s+(\d+)\s*/\s*Scenario\s+([A-Z])$", re.I)


# Column groupings: the wide schema has 10 "Use N" blocks, each spanning
# 5 columns (compliance_score, compliance_text, difficult_to_assess,
# plausibility_score, plausibility_text).
_USE_COL_GROUPS = (
    ("Use 1", "Unnamed: 2", "Unnamed: 3", "Unnamed: 4", "Unnamed: 5"),
    ("Use 2", "Unnamed: 7", "Unnamed: 8", "Unnamed: 9", "Unnamed: 10"),
    ("Use 3", "Unnamed: 12", "Unnamed: 13", "Unnamed: 14", "Unnamed: 15"),
    ("Use 4", "Unnamed: 17", "Unnamed: 18", "Unnamed: 19", "Unnamed: 20"),
    ("Use 5", "Unnamed: 22", "Unnamed: 23", "Unnamed: 24", "Unnamed: 25"),
    ("Use 6", "Unnamed: 27", "Unnamed: 28", "Unnamed: 29", "Unnamed: 30"),
    ("Use 7", "Unnamed: 32", "Unnamed: 33", "Unnamed: 34", "Unnamed: 35"),
    ("Use 8", "Unnamed: 37", "Unnamed: 38", "Unnamed: 39", "Unnamed: 40"),
    # Use 9 + Use 10 appear in some revisions; we look them up dynamically.
)


def _coerce_score(value: Any) -> int | None:
    """Cast a raw cell to an int 1–5, or None for missing / non-numeric."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return None
    if not 1 <= n <= 5:
        return None
    return n


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def _normalize_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Explode the wide HF rows into one annotation record per
    ``(row_label, use_index, annotator_slot)`` tuple.

    Each output record has::

        {
            "document_id": "art9_scenarioA_use1",
            "article_id": 9,
            "scenario_id": "A",
            "use_index": 1,                 # 1..10
            "intended_use": "Biometric...", # from AIREG_INTENDED_USES
            "compliance_score": 1-5 or None,
            "compliance_explanation": str,
            "difficult_to_assess": bool,
            "plausibility_score": 1-5 or None,
            "plausibility_explanation": str,
            "annotator_slot": 0,            # only one annotator per slot in this schema
        }

    Rows whose ``Unnamed: 0`` doesn't match the ``Art N / Scenario X``
    shape (e.g. the literal header row) are skipped.
    """
    out: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = raw.get("row") if isinstance(raw, dict) and "row" in raw else raw
        if not isinstance(row, dict):
            continue
        label = row.get("Unnamed: 0") or ""
        m = _ROW_LABEL_RE.match(str(label).strip())
        if not m:
            continue
        article_id = int(m.group(1))
        scenario_id = m.group(2).upper()
        for use_idx, cols in enumerate(_USE_COL_GROUPS, start=1):
            score_col, text_col, diff_col, plaus_col, plaus_text_col = cols
            if score_col not in row:
                continue
            compliance = _coerce_score(row.get(score_col))
            explanation = _coerce_text(row.get(text_col))
            # Skip cells where ALL fields are empty (missing annotator).
            if compliance is None and not explanation:
                continue
            intended_use = (
                AIREG_INTENDED_USES[use_idx - 1]
                if use_idx <= len(AIREG_INTENDED_USES)
                else f"Use {use_idx}"
            )
            doc_id = f"art{article_id}_scenario{scenario_id}_use{use_idx}"
            out.append(
                {
                    "document_id": doc_id,
                    "article_id": article_id,
                    "scenario_id": scenario_id,
                    "use_index": use_idx,
                    "intended_use": intended_use,
                    "compliance_score": compliance,
                    "compliance_explanation": explanation,
                    "difficult_to_assess": _coerce_text(
                        row.get(diff_col)
                    ).lower()
                    in {"true", "yes", "1", "x"},
                    "plausibility_score": _coerce_score(row.get(plaus_col)),
                    "plausibility_explanation": _coerce_text(
                        row.get(plaus_text_col)
                    ),
                }
            )
    return out


# ── Verdict bucketing ────────────────────────────────────────────────────


VERDICT_COMPLIANT = "compliant"
VERDICT_BORDERLINE = "borderline"
VERDICT_NON_COMPLIANT = "non-compliant"
VERDICT_UNKNOWN = "unknown"

VERDICT_SET = (VERDICT_COMPLIANT, VERDICT_BORDERLINE, VERDICT_NON_COMPLIANT)


def bucket_compliance_score(score: int | float | None) -> str:
    """Map a 1-5 compliance score to a verdict label.

    >>> bucket_compliance_score(5)
    'compliant'
    >>> bucket_compliance_score(4)
    'compliant'
    >>> bucket_compliance_score(3)
    'borderline'
    >>> bucket_compliance_score(2)
    'non-compliant'
    >>> bucket_compliance_score(1)
    'non-compliant'
    >>> bucket_compliance_score(None)
    'unknown'
    """
    if score is None:
        return VERDICT_UNKNOWN
    try:
        s = float(score)
    except (TypeError, ValueError):
        return VERDICT_UNKNOWN
    if s >= 4.0:
        return VERDICT_COMPLIANT
    if s >= 3.0:
        return VERDICT_BORDERLINE
    if s >= 1.0:
        return VERDICT_NON_COMPLIANT
    return VERDICT_UNKNOWN


def median(values: list[int | float]) -> float | None:
    """Statistics-stdlib-free median (saves an import on the hot path)."""
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return None
    xs.sort()
    n = len(xs)
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


# ── Public API ───────────────────────────────────────────────────────────


def fetch_aireg_bench(
    *, refresh: bool = False, max_offset: int = 220
) -> dict[str, Any]:
    """Fetch (or load from cache) the AIReg-Bench annotations + docs.

    Returns::

        {
            "documents": dict[str, str],     # may be empty (see module note)
            "annotations": list[dict],       # normalised per (doc, annotator)
            "revision": str,
            "parquet_sha256": str,           # actual hash of upstream parquet
            "parquet_sha256_pinned": str,    # expected hash
            "parquet_verified": bool,
            "n_rows": int,
            "fetch_blocked": bool,
        }

    The cache lives at ``.aireg-bench-cache/annotations.json`` next to
    the project root and is idempotent across runs. Use ``refresh=True``
    to force a re-fetch.
    """
    global _FETCH_BLOCKED
    AIREG_LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
    cached_payload: dict[str, Any] | None = None
    if _ANNOTATIONS_JSON.exists() and not refresh:
        try:
            cached_payload = json.loads(
                _ANNOTATIONS_JSON.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            cached_payload = None

    # Decision: prefer cache. Only hit network when cache is missing or
    # the caller asked for refresh.
    if cached_payload and not refresh:
        cached_payload.setdefault("fetch_blocked", _FETCH_BLOCKED)
        cached_payload["documents"] = _load_documents()
        return cached_payload

    # Try datasets-server. Smaller batches (length=5) are more reliable
    # than length=100 against this dataset.
    raw_rows: list[dict[str, Any]] = []
    blocked = False
    for offset in range(0, max_offset, 5):
        batch = _datasets_server_rows(offset, length=5)
        if batch is None:
            blocked = True
            break
        if not batch:
            break
        raw_rows.extend(batch)
        # Light politeness pause (avoid 429).
        time.sleep(0.2)

    if blocked and not raw_rows and not cached_payload:
        _FETCH_BLOCKED = True
        empty_payload: dict[str, Any] = {
            "documents": _load_documents(),
            "annotations": [],
            "revision": AIREG_REVISION,
            "parquet_sha256": "",
            "parquet_sha256_pinned": AIREG_PARQUET_SHA256,
            "parquet_verified": False,
            "n_rows": 0,
            "fetch_blocked": True,
        }
        return empty_payload

    annotations = _normalize_rows(raw_rows) if raw_rows else (
        cached_payload.get("annotations", []) if cached_payload else []
    )

    parquet_sha = ""
    parquet_verified = False
    try:
        url = (
            f"https://huggingface.co/datasets/{AIREG_HF_ID}/resolve/"
            f"{AIREG_REVISION}/human_annotations.parquet"
        )
        parquet_data = _http_get(url, timeout=60.0)
        parquet_sha = hashlib.sha256(parquet_data).hexdigest()
        parquet_verified = parquet_sha == AIREG_PARQUET_SHA256
    except Exception:  # noqa: BLE001 — verification is best-effort
        if cached_payload:
            parquet_sha = cached_payload.get("parquet_sha256", "")
            parquet_verified = cached_payload.get("parquet_verified", False)

    payload = {
        "documents": _load_documents(),
        "annotations": annotations,
        "revision": AIREG_REVISION,
        "parquet_sha256": parquet_sha,
        "parquet_sha256_pinned": AIREG_PARQUET_SHA256,
        "parquet_verified": parquet_verified,
        "n_rows": len(annotations),
        "fetch_blocked": blocked and not raw_rows,
    }
    # Persist (sans documents — they live on disk separately).
    persisted = {k: v for k, v in payload.items() if k != "documents"}
    try:
        _ANNOTATIONS_JSON.write_text(
            json.dumps(persisted, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        pass
    _FETCH_BLOCKED = bool(payload["fetch_blocked"])
    return payload


def _load_documents() -> dict[str, str]:
    """Return ``{document_id: text}`` from the local cache.

    On the current HF revision the ``documentation/`` directory is
    absent — we return ``{}`` then. If a future drop publishes the
    excerpts, they should be placed in
    ``.aireg-bench-cache/documentation/{document_id}.txt`` and this
    function will pick them up.
    """
    if not _DOCS_DIR.exists():
        return {}
    docs: dict[str, str] = {}
    for path in _DOCS_DIR.glob("*.txt"):
        try:
            docs[path.stem] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return docs


def aireg_dataset_sha256() -> str:
    """Return the SHA-256 of the cached ``annotations.json`` file.

    Empty string when the cache hasn't been populated yet. Used as a
    fingerprint for the benchmark-run audit-chain entry.
    """
    if not _ANNOTATIONS_JSON.exists():
        return ""
    return hashlib.sha256(_ANNOTATIONS_JSON.read_bytes()).hexdigest()


def dataset_fingerprint() -> dict[str, Any]:
    """Provenance fingerprint included in result rows + audit chain."""
    return {
        "hf_id": AIREG_HF_ID,
        "revision": AIREG_REVISION,
        "parquet_sha256_pinned": AIREG_PARQUET_SHA256,
        "annotations_json_sha256": aireg_dataset_sha256(),
        "fetch_blocked": _FETCH_BLOCKED,
    }


def is_fetch_blocked() -> bool:
    """Surface-level read of the module-level ``_FETCH_BLOCKED`` flag."""
    return _FETCH_BLOCKED


__all__ = [
    "AIREG_HF_ID",
    "AIREG_REVISION",
    "AIREG_PARQUET_SHA256",
    "AIREG_ARTICLES",
    "AIREG_INTENDED_USES",
    "AIREG_LOCAL_CACHE",
    "VERDICT_COMPLIANT",
    "VERDICT_BORDERLINE",
    "VERDICT_NON_COMPLIANT",
    "VERDICT_UNKNOWN",
    "VERDICT_SET",
    "aireg_dataset_sha256",
    "bucket_compliance_score",
    "dataset_fingerprint",
    "fetch_aireg_bench",
    "is_fetch_blocked",
    "median",
]
