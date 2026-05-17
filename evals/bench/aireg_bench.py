"""Offline-first AIReg-Bench loader + scorer (unbiased eval).

This is the lightweight, fixture-backed adapter used by
``unbiased_runner``. It is intentionally SEPARATE from the in-tree
``aireg_dataset`` / ``aireg_runner`` modules (which talk to HuggingFace
parquet rows and human annotations directly):

    * ``aireg_dataset`` — full HF integration, parquet, 3-annotator
      structure, large surface area. The Round-32+ pipeline.
    * ``aireg_bench``  — small fixture (10 hand-crafted items) plus an
      OPTIONAL live-fetch path that falls back to the fixture on any
      error. Designed so the unbiased runner ALWAYS produces a score,
      even on a machine with no network or no ``huggingface_hub``.

The benchmark surface scored here:
    * Articles 9, 10, 12, 14, 15 — the HRAIS compliance backbone
    * Two verdicts per article: ``compliant`` / ``non_compliant``
      (we don't probe the rarer ``unclear`` bucket in the fixture)

Public API:
    * ``load_aireg_fixture()``  → list of fixture rows (offline, deterministic)
    * ``load_aireg_bench()``    → live HF rows on success, fixture fallback
    * ``score_aireg_bench(items, agent_fn)`` → scoring dict

The ``agent_fn`` signature is::

    agent_fn(item: dict) -> {"answer": str, "references": list[str]}

so the unbiased runner can wrap the Regenold wire (TestClient + POST
/api/v1/regenold/eu-ai-act/ask) in a tiny adapter and pass it in here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "fixtures"
    / "aireg_sample.jsonl"
)

HF_REPO_ID = "camlsys/aireg-bench"


# ── Article normalisation ────────────────────────────────────────────────


_ARTICLE_RE = re.compile(
    r"^\s*(?:art\.?|article)\s*(\d+)\b",
    re.IGNORECASE,
)


def _normalise_article(raw: str | None) -> str | None:
    """Project ``"Art. 9"``, ``"Article 9(1)(a)"``, etc. → ``"Article 9"``.

    Returns None when the input doesn't parse as an article reference.
    Annexes are out of scope for the AIReg-Bench fixture (it's HRAIS
    articles only) so we don't accept ``Annex …`` here — that would
    silently mislabel a row.
    """
    if not raw:
        return None
    m = _ARTICLE_RE.match(raw)
    if not m:
        return None
    return f"Article {int(m.group(1))}"


def _normalise_refs(refs: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for r in refs or ():
        n = _normalise_article(r)
        if n is not None:
            out.add(n)
    return out


# ── Fixture loader ───────────────────────────────────────────────────────


def load_aireg_fixture() -> list[dict[str, Any]]:
    """Read the bundled 10-item JSONL fixture.

    Each line is one item with the schema::

        {
          "id": "aireg-001",
          "article": "Art. 9",
          "scenario": "...",
          "expected_articles": ["Art. 9"],
          "expected_verdict": "compliant" | "non_compliant" | "unclear"
        }

    Malformed lines are skipped (logged via raise from ``json`` if you
    re-enable strict mode).
    """
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"AIReg-Bench fixture missing at {FIXTURE_PATH}. "
            "Re-checkout tests/fixtures/aireg_sample.jsonl."
        )
    rows: list[dict[str, Any]] = []
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        # Skip malformed rows missing required keys.
        if {"id", "scenario", "expected_articles", "expected_verdict"} - row.keys():
            continue
        rows.append(row)
    return rows


# ── Live-fetch path (HuggingFace) ────────────────────────────────────────


def _fetch_hf_snapshot() -> list[dict[str, Any]]:
    """Attempt to load AIReg-Bench rows from a local HF snapshot cache.

    Returns the list of fixture-shape rows on success. Raises
    ``RuntimeError`` on ANY failure path so ``load_aireg_bench`` can
    catch and fall back.

    NOTE: This path is best-effort. The real ``camlsys/aireg-bench``
    schema is a parquet table of (article × scenario × intended_use ×
    annotator) annotations — converting that to the simpler
    ``(id, scenario, expected_articles, expected_verdict)`` shape used
    by the unbiased runner needs a deterministic projection. The full
    integration lives in ``evals.bench.aireg_dataset``; this module
    only attempts the snapshot fetch and projects the first 10
    available rows to the fixture shape.
    """
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - depends on host
        raise RuntimeError("huggingface_hub not installed") from exc

    try:
        local_dir = snapshot_download(
            repo_id=HF_REPO_ID, repo_type="dataset"
        )
    except Exception as exc:  # noqa: BLE001 - any network/auth error
        raise RuntimeError(f"snapshot_download failed: {exc}") from exc

    # Look for any *.parquet under the snapshot — if found, defer to
    # the deeper ``aireg_dataset`` module to read it. We don't replicate
    # parquet parsing here.
    parquet_files = list(Path(local_dir).rglob("*.parquet"))
    if not parquet_files:
        raise RuntimeError(f"no parquet found in {local_dir}")
    try:
        from evals.bench import aireg_dataset  # type: ignore[import-untyped]

        rows = aireg_dataset.fetch_aireg_bench()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"aireg_dataset projection failed: {exc}") from exc

    # Project to fixture shape — use the row's article + median verdict.
    projected: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:120]):  # 120 = AIReg's HRAIS subset
        article = row.get("article")
        scenario = row.get("scenario") or row.get("text") or ""
        verdict = row.get("verdict") or row.get("expected_verdict")
        if not (article and scenario and verdict):
            continue
        projected.append(
            {
                "id": f"aireg-live-{idx:03d}",
                "article": article,
                "scenario": scenario,
                "expected_articles": [article],
                "expected_verdict": verdict,
            }
        )
    if not projected:
        raise RuntimeError("no usable rows after projection")
    return projected


def load_aireg_bench() -> list[dict[str, Any]]:
    """Return AIReg-Bench rows — live HF fetch with fixture fallback.

    Tries ``_fetch_hf_snapshot`` first. On ANY error (no network, no
    huggingface_hub, projection failure) returns the bundled fixture.
    """
    try:
        return _fetch_hf_snapshot()
    except Exception:  # noqa: BLE001 - intentional fallback
        return load_aireg_fixture()


# ── Verdict extraction from agent prose ──────────────────────────────────


_COMPLIANT_MARKERS = (
    "is compliant",
    "fully compliant",
    "meets the requirement",
    "satisfies the requirement",
    "in compliance",
    "complies with",
    # Bare-word fallback — caught AFTER the more specific markers so a
    # phrase like "fully compliant" still attributes to that variant.
    " compliant.",
    " compliant ",
)
_NON_COMPLIANT_MARKERS = (
    "non-compliant",
    "non compliant",
    "not compliant",
    "fails to meet",
    "does not satisfy",
    "does not comply",
    "in breach of",
    "violates",
    "infringes",
)
_UNCLEAR_MARKERS = (
    "depends on the context",
    "context-dependent",
    "context dependent",
    "insufficient information",
    "cannot determine",
    "unclear from",
)


def _extract_verdict(text: str) -> str:
    """Heuristic — best-effort verdict label from free-form agent prose."""
    if not text:
        return "unclear"
    low = text.lower()
    # Order matters: "non-compliant" must beat "compliant" because the
    # latter is a substring of the former phrasing.
    for marker in _NON_COMPLIANT_MARKERS:
        if marker in low:
            return "non_compliant"
    for marker in _UNCLEAR_MARKERS:
        if marker in low:
            return "unclear"
    for marker in _COMPLIANT_MARKERS:
        if marker in low:
            return "compliant"
    return "unclear"


# ── Scoring ──────────────────────────────────────────────────────────────


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_aireg_bench(
    items: list[dict[str, Any]],
    agent_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Score an agent against the AIReg-Bench fixture / live items.

    Args:
        items: List of fixture-shape rows.
        agent_fn: Callable taking one item and returning
            ``{"answer": str, "references": list[str]}``.

    Returns:
        A scoring dict::

            {
              "n": N,
              "article_precision": float,
              "article_recall":    float,
              "article_f1":        float,
              "verdict_accuracy":  float,
              "per_article":       {"Article 9": {p,r,f1,n,acc}, ...},
              "verdict_confusion": {gold_label: {pred_label: count}},
              "rows":              [...]  # per-item detail
            }

    All floats are JSON-serialisable rounded to 4 decimal places.
    Empty inputs yield an all-zero scorecard (n=0).
    """
    if not items:
        return {
            "n": 0,
            "article_precision": 0.0,
            "article_recall": 0.0,
            "article_f1": 0.0,
            "verdict_accuracy": 0.0,
            "per_article": {},
            "verdict_confusion": {},
            "rows": [],
        }

    rows: list[dict[str, Any]] = []
    tp_all = fp_all = fn_all = 0
    correct_verdicts = 0
    per_article_stats: dict[str, dict[str, int]] = {}
    confusion: dict[str, dict[str, int]] = {}

    for item in items:
        result = agent_fn(item) or {}
        pred_refs = _normalise_refs(result.get("references") or [])
        gold_refs = _normalise_refs(item.get("expected_articles") or [])

        tp = len(pred_refs & gold_refs)
        fp = len(pred_refs - gold_refs)
        fn = len(gold_refs - pred_refs)
        tp_all += tp
        fp_all += fp
        fn_all += fn

        gold_verdict = item.get("expected_verdict") or "unclear"
        pred_verdict = _extract_verdict(result.get("answer") or "")
        verdict_match = pred_verdict == gold_verdict
        if verdict_match:
            correct_verdicts += 1

        for gold_art in gold_refs:
            stats = per_article_stats.setdefault(
                gold_art, {"tp": 0, "fp": 0, "fn": 0, "n": 0, "correct_v": 0}
            )
            stats["n"] += 1
            if gold_art in pred_refs:
                stats["tp"] += 1
            else:
                stats["fn"] += 1
            if verdict_match:
                stats["correct_v"] += 1
        for pred_art in pred_refs - gold_refs:
            stats = per_article_stats.setdefault(
                pred_art, {"tp": 0, "fp": 0, "fn": 0, "n": 0, "correct_v": 0}
            )
            stats["fp"] += 1

        confusion.setdefault(gold_verdict, {}).setdefault(pred_verdict, 0)
        confusion[gold_verdict][pred_verdict] += 1

        rows.append(
            {
                "id": item.get("id"),
                "gold_articles": sorted(gold_refs),
                "pred_articles": sorted(pred_refs),
                "gold_verdict": gold_verdict,
                "pred_verdict": pred_verdict,
                "verdict_match": verdict_match,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }
        )

    precision = tp_all / (tp_all + fp_all) if (tp_all + fp_all) else 0.0
    recall = tp_all / (tp_all + fn_all) if (tp_all + fn_all) else 0.0
    article_f1 = _f1(precision, recall)
    verdict_accuracy = correct_verdicts / len(items)

    per_article_out: dict[str, dict[str, float]] = {}
    for art, s in per_article_stats.items():
        a_p = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 0.0
        a_r = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 0.0
        a_acc = s["correct_v"] / s["n"] if s["n"] else 0.0
        per_article_out[art] = {
            "n": s["n"],
            "precision": round(a_p, 4),
            "recall": round(a_r, 4),
            "f1": round(_f1(a_p, a_r), 4),
            "verdict_accuracy": round(a_acc, 4),
        }

    return {
        "n": len(items),
        "article_precision": round(precision, 4),
        "article_recall": round(recall, 4),
        "article_f1": round(article_f1, 4),
        "verdict_accuracy": round(verdict_accuracy, 4),
        "per_article": per_article_out,
        "verdict_confusion": confusion,
        "rows": rows,
    }
