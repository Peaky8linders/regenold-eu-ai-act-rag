"""R449 — retrieval-grain harness over the official 110-row gold set.

WHY THIS EXISTS
===============

Every scored instrument in this repository is answer- or reference-level
(:mod:`evals.official.rubric`), while the published retrieval research this
project draws on is measured at *retrieval* grain (recall@k, nDCG@k, minimal
span recall). A change that improves which provisions are discovered and which
passages are selected can therefore be cancelled — or hidden — by the
generation stage, and a regression in discovery can be masked by a lucky
answer.

This module runs the **production retrieval entry point** on the real 110-row
gold set and reports, per configuration:

* head-grain recall / precision / F1 / nDCG@k over the gold heads,
* how many references each dense stage *adds* and how many of those additions
  are gold (the "weakest link" measurement from arXiv 2508.01405),
* context cost (verbatim provision characters pulled for the returned heads),
* unit-grain accuracy of the shipped passage selector on the same heads — how
  often its top-ranked unit is the gold unit, and how much of the gold unit's
  content its bounded output actually carries — against a within-document BM25
  baseline and the existing TF-IDF/SVD space applied at paragraph grain.

The last item is the one the answer-level axes cannot see: R436 recorded
ref-faithfulness at 25% with answers discussing one provision and citing a
neighbour, and its healthy-leg retest traced a surviving failure to an answer
binding ``Article 10(4)`` where the criterion needed ``Article 10(3)``.

WHAT IT DOES NOT DO
===================

No network, no judge, no LLM. It sets the repo's documented deterministic
offline environment and calls :func:`app.data.kb_search.top_articles_by_relevance`
— the same function the deterministic-parse fallback lane calls with
``k=_bm25_fallback_k()`` (8) and ``min_score=1.0``. It is a *retrieval*
instrument: passing here is not evidence that a live answer changed, and
failing here is not proof that an answer will regress. Use it to decide what
deserves a live gate, not to replace the gates.

USAGE
=====

    python -m evals.retrieval.unit_grain --arms bm25,dense_a,dense_b,default,rrf,score
    python -m evals.retrieval.unit_grain --rows 25 --no-unit
    python -m evals.retrieval.unit_grain --out docs/measurements/r449/unit-grain.json \
        --md-out docs/measurements/r449/UNIT-GRAIN.md
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

# ── Deterministic offline environment ────────────────────────────────────────
#
# Must be applied BEFORE any ``app.*`` import so ``config.py``'s dotenv loader
# sees REGENOLD_SKIP_DOTENV and no API key leaks into a "deterministic" run.
_OFFLINE_ENV: dict[str, str] = {
    "REGENOLD_SKIP_DOTENV": "1",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_GRAPH_2HOP": "0",
    "REGENOLD_COHERE_RERANK": "0",
    "REGENOLD_HYPA_RRF_RETRIEVAL": "0",
    "REGENOLD_CONTEXTUAL_FIELDS": "0",
}

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_GOLD = _REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: The k the deterministic-parse fallback lane actually uses
#: (``_graph_rag_impl._bm25_fallback_k()`` → ``_BM25_FALLBACK_K = 8``).
_PRODUCTION_K = 8

#: R450 — the passage-emission defaults. 500 is the verbatim-ANSWER budget
#: (``REGENOLD_VERBATIM_PARA_CHARS``) that R449 judged at; 1200 is what the
#: Stage-2 GROUNDING block — the evidence the scored answer actually reads —
#: passes (``_graph_rag_impl._grounding_ref_budget()``). Arm-level overrides
#: live on :class:`Arm`; these are the fallbacks.
_DEFAULT_UNIT_BUDGET = 500
_DEFAULT_UNIT_ALLOC = "rank"

#: The allocation-policy env gate. Mirrors ``provision_text._EMIT_ALLOC_ENV``;
#: it is duplicated as a literal because ``_OFFLINE_ENV`` must be applied before
#: any ``app.*`` import (the harness must never import the app to read a name),
#: and ``tests/test_r450_emit_allocation.py`` pins the two strings equal.
_EMIT_ALLOC_ENV = "REGENOLD_EMIT_ALLOC"


@dataclass(frozen=True)
class Arm:
    """One retrieval configuration, expressed as environment overrides.

    ``unit_budget`` / ``unit_alloc`` scope the PASSAGE-GRAIN stage only (the
    per-provision verbatim emission budget and its allocation policy). They are
    separate from ``env`` because the budget is a call parameter of
    ``select_relevant_paragraphs``, not an env gate — and because the R449
    default of 500 is the verbatim-ANSWER budget, while the evidence that
    produces the scored answer is Stage-2 GROUNDING at 1200 per ref
    (``_graph_rag_impl._grounding_ref_budget()``). Judging emission at 500 and
    then generalising to the answer path is a category error this field exists
    to prevent.
    """

    name: str
    env: dict[str, str]
    note: str
    unit_budget: int | None = None
    unit_alloc: str | None = None


#: Arms are additive deltas over the production fallback ranking. ``bm25`` is
#: the sparse-only control; each later arm turns on exactly one extra stage so
#: the marginal contribution of that stage is attributable.
ARMS: tuple[Arm, ...] = (
    Arm("bm25", {"REGENOLD_TURBOQUANT_DENSE": "0", "REGENOLD_EMBEDDINGS_INDEX": "0"},
        "sparse only (BM25 + entity boosts) — control"),
    Arm("dense_a", {"REGENOLD_TURBOQUANT_DENSE": "1", "REGENOLD_EMBEDDINGS_INDEX": "0"},
        "BM25 + article-level TF-IDF/SVD (turboquant_index)"),
    Arm("dense_b", {"REGENOLD_TURBOQUANT_DENSE": "0", "REGENOLD_EMBEDDINGS_INDEX": "1"},
        "BM25 + sentence-level SVD (embeddings_index), collapsed to article"),
    Arm("default", {"REGENOLD_TURBOQUANT_DENSE": "1", "REGENOLD_EMBEDDINGS_INDEX": "1"},
        "shipped additive fusion (both dense stages)"),
    Arm("rrf", {"REGENOLD_TURBOQUANT_DENSE": "1", "REGENOLD_EMBEDDINGS_INDEX": "1",
                "REGENOLD_RRF_FUSION": "1"},
        "R69 weighted RRF, BM25-dominant 2:1"),
    Arm("score", {"REGENOLD_TURBOQUANT_DENSE": "1", "REGENOLD_EMBEDDINGS_INDEX": "1",
                  "REGENOLD_SCORE_FUSION": "1"},
        "score fusion, alpha 0.3"),
    Arm("ctx_fields", {"REGENOLD_TURBOQUANT_DENSE": "0", "REGENOLD_EMBEDDINGS_INDEX": "0",
                       "REGENOLD_CONTEXTUAL_FIELDS": "1"},
        "R449 contextual BM25F fields (title/body), sparse only"),
    #: LIVE arm — talks to Cohere/OpenAI. Requires the provider key in the
    #: child environment (the harness deliberately skips .env), and it is rate
    #: limited by whatever key is supplied; run it with a small --rows first.
    Arm("dense_ext", {"REGENOLD_TURBOQUANT_DENSE": "1", "REGENOLD_EMBEDDINGS_INDEX": "1",
                      "REGENOLD_EXTERNAL_EMBEDDINGS": "1"},
        "LIVE — external embeddings replace the local SVD article vectors"),
    Arm("ctx_fields_dense", {"REGENOLD_TURBOQUANT_DENSE": "0", "REGENOLD_EMBEDDINGS_INDEX": "1",
                             "REGENOLD_CONTEXTUAL_FIELDS": "1"},
        "R449 contextual fields + shipped dense stage"),
    # ── R450 — passage-emission arms (same retrieval, different spending) ──
    # These hold the head-grain ranking fixed and vary ONLY how
    # ``select_relevant_paragraphs`` spends its per-provision budget, which is
    # the axis R450 measured as the binding one (79% of gold units are larger
    # than the 500-char verbatim-answer budget).
    Arm("emit_rank_1200", {}, "R450 — shipped rank allocation at the 1200-char Grounding budget",
        unit_budget=1200, unit_alloc="rank"),
    Arm("emit_density_1200", {}, "R450 — density allocation (relevance per char) at 1200",
        unit_budget=1200, unit_alloc="density"),
    Arm("emit_density_500", {}, "R450 — density allocation at the shipped 500-char budget",
        unit_budget=500, unit_alloc="density"),
    Arm("emit_top1_1200", {}, "R450 — top unit only at 1200 (context-reducing control)",
        unit_budget=1200, unit_alloc="top1"),
)

_ANNEX_ARABIC_TO_ROMAN = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII",
    8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII", 13: "XIII",
}

_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Whitespace-collapsed text for verbatim containment tests."""
    return _WS_RE.sub(" ", (text or "").strip().lower())


# ── Reference normalisation ──────────────────────────────────────────────────


def canonical_head(wire_ref: str) -> str:
    """Map any article/annex reference to the retriever's head key.

    ``"Article 13.3.b.iv"`` → ``"Art. 13"``; ``"Annex III.5.b"`` → ``"Annex III"``;
    ``"Annex 4"`` → ``"Annex IV"``. Returns ``""`` for anything unrecognised so
    callers can exclude rather than guess.
    """
    ref = (wire_ref or "").strip()
    m = re.match(r"(?i)^(article|art\.?|annex)\s+([0-9]+|[IVXLCDM]+)(?:[.\s]|$)", ref)
    if not m:
        return ""
    kind = m.group(1).lower()
    token = m.group(2)
    if kind.startswith("art"):
        try:
            return f"Art. {int(token)}"
        except ValueError:
            return ""
    if token.isdigit():
        roman = _ANNEX_ARABIC_TO_ROMAN.get(int(token))
        return f"Annex {roman}" if roman else ""
    return f"Annex {token.upper()}"


def _annex_section_canonical(coord: str) -> str:
    """Canonicalise section-tagged annex coordinates to printed point numbers.

    Reuses the merged scorer mapping rather than re-deriving it, so the harness
    and the official rubric cannot drift apart (``Annex I.A.11`` → ``Annex I.11``).
    Falls back to the input when the scorer is unavailable.
    """
    try:
        from evals.official.rubric import canonical_annex_point  # noqa: PLC0415

        return canonical_annex_point(coord)
    except Exception:  # noqa: BLE001 — harness must run on a partial checkout
        return coord


def gold_unit_key(wire_ref: str) -> str | None:
    """The numbered paragraph/item of a gold coordinate, or ``None``.

    ``"Article 13.3.b.iv"`` → ``"3"``; ``"Annex IV.1.e"`` → ``"1"``;
    ``"Annex VIII.a"`` → ``None`` (section-lettered annex whose items are not
    numbered → not gradable at this grain).
    """
    coord = _annex_section_canonical((wire_ref or "").strip())
    segments = coord.split(".")[1:]
    for seg in segments:
        seg = seg.strip()
        if seg.isdigit():
            return str(int(seg))
    return None


# ── Gold loading ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldRow:
    row_id: str
    question: str
    expected_refs: tuple[str, ...]
    gold_heads: tuple[str, ...]


def load_gold(path: Path, *, limit: int | None = None) -> list[GoldRow]:
    """Read the official gold JSONL into resolved head keys."""
    rows: list[GoldRow] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            refs = tuple(str(r) for r in (raw.get("expected_refs") or []))
            heads = tuple(sorted({h for h in (canonical_head(r) for r in refs) if h}))
            rows.append(
                GoldRow(
                    row_id=str(raw.get("id") or f"row_{len(rows)}"),
                    question=str(raw.get("question") or ""),
                    expected_refs=refs,
                    gold_heads=heads,
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows


# ── Ranking metrics ──────────────────────────────────────────────────────────


def ref_recall(retrieved: Sequence[str], gold_heads: Iterable[str]) -> tuple[int, int]:
    """(matched gold heads, total gold heads) at whatever cut ``retrieved`` is."""
    gold = set(gold_heads)
    if not gold:
        return 0, 0
    return len(gold & set(retrieved)), len(gold)


def precision_at_k(retrieved: Sequence[str], gold_heads: Iterable[str]) -> float:
    if not retrieved:
        return 0.0
    gold = set(gold_heads)
    return len(gold & set(retrieved)) / len(retrieved)


def f1(precision: float, recall: float) -> float:
    if precision + recall <= 0.0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def ndcg_at_k(retrieved: Sequence[str], gold_heads: Iterable[str]) -> float:
    """Binary-gain nDCG at the returned cut (head grain)."""
    gold = set(gold_heads)
    if not gold:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 2)
        for rank, ref in enumerate(retrieved)
        if ref in gold
    )
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(min(len(gold), len(retrieved))))
    if ideal <= 0.0:  # pragma: no cover — unreachable when gold is non-empty
        return 0.0
    return dcg / ideal


# ── Unit (paragraph/item) selection ──────────────────────────────────────────


def _units_for_head(head: str) -> dict[int, str]:
    """Verbatim numbered paragraphs (articles) / items (annexes) for a head.

    Uses the same private helpers as :func:`provision_text.select_relevant_paragraphs`
    so the harness scores the production unit inventory, not a reconstruction.
    """
    from app.data import provision_text as pt  # noqa: PLC0415

    if head.startswith("Art."):
        key = f"Article {head.split()[1]}"
        if key == "Article 3":
            return {}  # definitions are queried by term, not by paragraph
        body = pt.article_body(key)
        return pt._paragraphs(body) if body else {}  # noqa: SLF001 — production inventory
    if head.startswith("Annex "):
        body = pt.article_body(head)
        return pt._annex_items(body) if body else {}  # noqa: SLF001
    return {}


def overlap_top1(head: str, question: str) -> int | None:
    """Top-1 unit under the production token-overlap ranking.

    Replays the exact call sequence of ``select_relevant_paragraphs`` up to its
    ``ranked`` line (sibling-IDF weights + ``_overlap_score`` + document-order
    tie-break) so the harness ranks units the way the shipped selector does,
    while still exposing *which* unit won.
    """
    from app.data import provision_text as pt  # noqa: PLC0415

    units = _units_for_head(head)
    if not units:
        return None
    q_tok = pt._tokens(question)  # noqa: SLF001
    weights = pt._sibling_idf(units) if pt._evidence_idf_enabled() else None  # noqa: SLF001
    scored = [
        (num, txt, pt._overlap_score(q_tok, pt._tokens(txt), weights))  # noqa: SLF001
        for num, txt in sorted(units.items())
    ]
    ranked = sorted(scored, key=lambda x: (-x[2], x[0]))
    if q_tok and ranked[0][2] == 0:
        ranked = sorted(scored, key=lambda x: x[0])
    return ranked[0][0]


def bm25_para_top1(head: str, question: str) -> int | None:
    """Top-1 unit under a within-document Okapi BM25 (k1=1.5, b=0.75).

    Eval-only baseline: it exists to test the hypothesis that paragraph-grain
    BM25 beats the shipped token-overlap selector, before anyone builds a
    paragraph index into the production path.
    """
    from app.data import provision_text as pt  # noqa: PLC0415

    units = _units_for_head(head)
    if not units:
        return None
    q_tokens = pt._tokens(question)  # noqa: SLF001
    if not q_tokens:
        return min(units)
    tokenised = {num: pt._tokens(txt) for num, txt in units.items()}  # noqa: SLF001
    n = len(tokenised)
    avg_len = mean(len(t) for t in tokenised.values()) or 1.0
    df: dict[str, int] = {}
    for toks in tokenised.values():
        for term in set(toks):
            df[term] = df.get(term, 0) + 1
    k1, b = 1.5, 0.75
    best_num: int | None = None
    best_score = -1.0
    for num in sorted(tokenised):
        toks = tokenised[num]
        freqs: dict[str, int] = {}
        for term in toks:
            freqs[term] = freqs.get(term, 0) + 1
        doc_len = len(toks)
        score = 0.0
        for term in q_tokens:
            tf = freqs.get(term, 0)
            if not tf:
                continue
            idf = math.log((n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1.0)
            denom = tf + k1 * (1 - b + b * doc_len / avg_len)
            score += idf * (tf * (k1 + 1)) / denom
        if score > best_score:
            best_score, best_num = score, num
    return best_num


def svd_unit_top1(head: str, question: str) -> int | None:
    """Top-1 unit by cosine inside the index's own TF-IDF/SVD space.

    Both the question and each candidate unit are projected through the SAME
    basis and vocabulary the sentence index uses
    (``embeddings_index._embed_query``), so this answers a precise question:
    *if the paragraph grain were indexed into the existing dense space, would
    unit selection beat the shipped token-overlap selector?* It is the cheap,
    dependency-free analogue of late chunking — one corpus-level projection
    basis, pooled per passage — and the private accessor is deliberate: the
    public ``query()`` only projects questions against its own frozen corpus,
    which is exactly the collapse this instrument exists to look past.
    """
    from app.engines import embeddings_index  # noqa: PLC0415

    units = _units_for_head(head)
    if not units:
        return None
    q_vec = embeddings_index._embed_query(question)  # noqa: SLF001 — see docstring
    if q_vec is None:
        return None

    import numpy as np  # noqa: PLC0415

    best_num: int | None = None
    best_sim = -2.0
    for num, text in units.items():
        unit_vec = embeddings_index._embed_query(text)  # noqa: SLF001
        if unit_vec is None:
            continue
        sim = float(np.dot(q_vec, unit_vec))
        if sim > best_sim:
            best_sim, best_num = sim, num
    return best_num


def selection_coverage(
    head: str,
    question: str,
    gold_num: str | None,
    budget: int = _DEFAULT_UNIT_BUDGET,
    alloc: str | None = None,
) -> tuple[float, int] | None:
    """Share of the gold unit's tokens present in the shipped selector's output.

    Token coverage, NOT substring containment: for a long paragraph that carries
    lettered sub-points the production selector legitimately returns a *drilled*
    excerpt (``_drill_subpoints``) rather than the whole paragraph, so a
    verbatim-substring test would report a coverage failure where the shipped
    behaviour is a deliberate narrowing. Coverage ≥ 0.8 is the reported hit.

    Returns ``(coverage, emitted_chars)``: the share of the gold unit's tokens
    the bounded output carries, and how many characters that emission cost —
    the two numbers an emission change has to move in opposite directions to be
    interesting. ``budget`` / ``alloc`` are the per-provision emission budget
    and its allocation policy (R450); the defaults reproduce the R449 arm.
    """
    from app.data import provision_text as pt  # noqa: PLC0415

    if gold_num is None:
        return None
    units = _units_for_head(head)
    gold_text = units.get(int(gold_num))
    if not gold_text:
        return None
    selected = pt.select_relevant_paragraphs(
        head, question, max_chars=budget, alloc=alloc
    )
    if not selected:
        return None
    gold_tokens = set(pt._tokens(gold_text))  # noqa: SLF001
    if not gold_tokens:
        return None
    selected_tokens = set(pt._tokens(selected))  # noqa: SLF001
    return len(gold_tokens & selected_tokens) / len(gold_tokens), len(selected)


# ── Arm execution ────────────────────────────────────────────────────────────


@dataclass
class RowDetail:
    row_id: str
    gold_heads: list[str]
    retrieved: list[str]
    added_over_bm25: list[str]
    unit_gold: str | None
    unit_overlap_top1: int | None
    unit_overlap_coverage: float | None
    unit_bm25_top1: int | None
    unit_svd_top1: int | None
    #: Characters the bounded verbatim emission cost for this row (R450).
    unit_emitted_chars: int | None = None


@dataclass
class ArmResult:
    name: str
    note: str
    env: dict[str, str]
    k: int
    n_rows: int
    head_recall: float
    row_all_head_recall: float
    head_precision: float
    head_f1: float
    ndcg: float
    excess_refs_mean: float
    context_chars_mean: float
    added_total: int = 0
    added_gold: int = 0
    added_precision: float = 0.0
    #: Which dense backend actually served this arm. A live arm whose provider
    #: key 429s SILENTLY falls back to the local SVD path, so two arms can read
    #: byte-identical and look like "external embeddings add nothing" when the
    #: truth is "the external call never landed" (measured R449: Cohere returned
    #: 429 on every attempt and turboquant logged the SVD fallback).
    embedding_backend: str = "unknown"
    unit_denominator: int = 0
    unit_overlap_top1: float = 0.0
    unit_overlap_covered: float = 0.0
    unit_overlap_coverage_mean: float = 0.0
    unit_bm25_top1: float = 0.0
    unit_svd_top1: float = 0.0
    #: R450 — emission cost of the passage stage (mean / p95 characters).
    unit_emitted_chars_mean: float = 0.0
    unit_emitted_chars_p95: float = 0.0
    unit_budget: int = _DEFAULT_UNIT_BUDGET
    unit_alloc: str = "rank"
    detail: list[RowDetail] = field(default_factory=list)


def _resolved_backend() -> str:
    """The dense backend the index actually used (never raises).

    Read AFTER the rows have run so the answer reflects the build that served
    them, not a fresh probe of the env flags.
    """
    try:
        from app.engines import turboquant_index  # noqa: PLC0415

        diag = turboquant_index.index_diagnostics()
        if not diag.get("loaded"):
            return "unavailable"
        return str(diag.get("embedding_backend") or "unknown")
    except Exception:  # noqa: BLE001 — telemetry must never fail a run
        return "unknown"


def _retrieve(question: str, k: int) -> list[str]:
    from app.data.kb_search import top_articles_by_relevance  # noqa: PLC0415

    hits = top_articles_by_relevance(question, k=k, min_score=1.0)
    return [h for h in hits if isinstance(h, str) and h.strip()]


def _context_chars(refs: Sequence[str]) -> int:
    from app.data.provision_text import get_provision_text  # noqa: PLC0415

    total = 0
    for ref in refs:
        try:
            text = get_provision_text(ref)
        except Exception:  # noqa: BLE001 — a bad coordinate must not fail the run
            text = None
        total += len(text or "")
    return total


def run_arm(
    arm: Arm,
    rows: Sequence[GoldRow],
    *,
    k: int,
    unit: bool,
    unit_budget: int = _DEFAULT_UNIT_BUDGET,
    unit_alloc: str = _DEFAULT_UNIT_ALLOC,
    baseline: dict[str, list[str]] | None = None,
) -> ArmResult:
    """Run one configuration over the gold rows and aggregate its metrics.

    ``baseline`` is shared across arms by :func:`run_arms`: the FIRST arm to
    run for a row records that row's retrieved set, and every later arm reports
    ``added_over_bm25`` against it. A per-call dict (the previous behaviour)
    silently reported zero additions for every arm, which is indistinguishable
    from "the stage does nothing".
    """
    budget = arm.unit_budget if arm.unit_budget is not None else unit_budget
    alloc = arm.unit_alloc if arm.unit_alloc is not None else unit_alloc
    previous = {name: os.environ.get(name) for name in _OFFLINE_ENV}
    previous_alloc = os.environ.get(_EMIT_ALLOC_ENV)
    for name, value in _OFFLINE_ENV.items():
        os.environ[name] = value
    for name, value in arm.env.items():
        os.environ[name] = value
    # The emission policy is read per call by ``select_relevant_paragraphs``, so
    # it is set here rather than in ``arm.env`` — and it is NOT part of the
    # retrieval index, so arms differing only in it stay index-identical.
    os.environ[_EMIT_ALLOC_ENV] = alloc
    if baseline is None:
        baseline = {}
    try:
        details: list[RowDetail] = []
        recalls: list[float] = []
        all_rows: list[float] = []
        precisions: list[float] = []
        f1s: list[float] = []
        ndcgs: list[float] = []
        excess: list[float] = []
        chars: list[float] = []
        added_total = added_gold = 0
        unit_hits = {"overlap": 0, "covered": 0, "bm25": 0, "dense": 0}
        coverage_values: list[float] = []
        emitted_chars: list[int] = []
        unit_den = 0

        for row in rows:
            retrieved = _retrieve(row.question, k)
            gold = row.gold_heads
            matched, total = ref_recall(retrieved, gold)
            row_recall = matched / total if total else 0.0
            row_precision = precision_at_k(retrieved, gold)
            recalls.append(row_recall)
            all_rows.append(1.0 if gold and set(gold) <= set(retrieved) else 0.0)
            precisions.append(row_precision)
            f1s.append(f1(row_precision, row_recall))
            ndcgs.append(ndcg_at_k(retrieved, gold))
            excess.append(max(0, len(retrieved) - len(set(gold) & set(retrieved))))
            chars.append(float(_context_chars(retrieved)))

            base = baseline.get(row.row_id)
            added = [r for r in retrieved if base is not None and r not in base]
            if base is not None:
                added_total += len(added)
                added_gold += len([r for r in added if r in gold])
            else:
                baseline[row.row_id] = list(retrieved)

            detail = RowDetail(
                row_id=row.row_id,
                gold_heads=list(gold),
                retrieved=list(retrieved),
                added_over_bm25=added,
                unit_gold=None,
                unit_overlap_top1=None,
                unit_overlap_coverage=None,
                unit_bm25_top1=None,
                unit_svd_top1=None,
            )

            if unit:
                # Grade the coordinate ONLY when its own head was retrieved:
                # otherwise the selector never had a chance, and mixing those
                # rows in would report retrieval failure as selection failure.
                gold_num: str | None = None
                head = ""
                for ref in row.expected_refs:
                    if canonical_head(ref) not in retrieved:
                        continue
                    candidate = gold_unit_key(ref)
                    if candidate is None:
                        continue
                    gold_num = candidate
                    head = canonical_head(ref)
                    break
                detail.unit_gold = gold_num
                if gold_num is not None and head:
                    unit_den += 1
                    o1 = overlap_top1(head, row.question)
                    b1 = bm25_para_top1(head, row.question)
                    d1 = svd_unit_top1(head, row.question)
                    detail.unit_overlap_top1 = o1
                    detail.unit_bm25_top1 = b1
                    detail.unit_svd_top1 = d1
                    probe = selection_coverage(
                        head, row.question, gold_num, budget=budget, alloc=alloc
                    )
                    if probe is not None:
                        coverage, emitted_len = probe
                        detail.unit_overlap_coverage = coverage
                        detail.unit_emitted_chars = emitted_len
                        coverage_values.append(coverage)
                        emitted_chars.append(emitted_len)
                        unit_hits["covered"] += int(coverage >= 0.8)
                    want = int(gold_num)  # gold_num is always digit-normalised
                    unit_hits["overlap"] += int(o1 == want)
                    unit_hits["bm25"] += int(b1 == want)
                    unit_hits["dense"] += int(d1 == want)

            details.append(detail)

        return ArmResult(
            name=arm.name,
            note=arm.note,
            env=dict(arm.env),
            k=k,
            n_rows=len(rows),
            head_recall=mean(recalls) if recalls else 0.0,
            row_all_head_recall=mean(all_rows) if all_rows else 0.0,
            head_precision=mean(precisions) if precisions else 0.0,
            head_f1=mean(f1s) if f1s else 0.0,
            ndcg=mean(ndcgs) if ndcgs else 0.0,
            excess_refs_mean=mean(excess) if excess else 0.0,
            context_chars_mean=mean(chars) if chars else 0.0,
            added_total=added_total,
            added_gold=added_gold,
            added_precision=(added_gold / added_total) if added_total else 0.0,
            embedding_backend=_resolved_backend(),
            unit_denominator=unit_den,
            unit_overlap_top1=(unit_hits["overlap"] / unit_den) if unit_den else 0.0,
            unit_overlap_covered=(unit_hits["covered"] / unit_den) if unit_den else 0.0,
            unit_overlap_coverage_mean=(mean(coverage_values) if coverage_values else 0.0),
            unit_bm25_top1=(unit_hits["bm25"] / unit_den) if unit_den else 0.0,
            unit_svd_top1=(unit_hits["dense"] / unit_den) if unit_den else 0.0,
            unit_emitted_chars_mean=(mean(emitted_chars) if emitted_chars else 0.0),
            unit_emitted_chars_p95=(
                sorted(emitted_chars)[max(0, int(len(emitted_chars) * 0.95) - 1)]
                if emitted_chars
                else 0
            ),
            unit_budget=budget,
            unit_alloc=alloc,
            detail=details,
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if previous_alloc is None:
            os.environ.pop(_EMIT_ALLOC_ENV, None)
        else:
            os.environ[_EMIT_ALLOC_ENV] = previous_alloc


def run_arms(
    arms: Sequence[Arm],
    rows: Sequence[GoldRow],
    *,
    k: int = _PRODUCTION_K,
    unit: bool = True,
    unit_budget: int = _DEFAULT_UNIT_BUDGET,
    unit_alloc: str = _DEFAULT_UNIT_ALLOC,
) -> list[ArmResult]:
    """Run arms in ONE process. **Only valid for arms that share an index.**

    ⚠ ``app.data.kb_search._build_index`` is ``lru_cache(maxsize=1)`` and the
    dense index is a process singleton, so the FIRST arm's configuration fixes
    the index for every later arm in the same process — including
    ``REGENOLD_CONTEXTUAL_FIELDS`` (which changes the index itself) and the
    external-embedding switch. Arms that differ on those flags must be run via
    the CLI (one subprocess per arm, see :func:`main`), which is why that is the
    default path. In-process runs remain useful for testing the metrics.
    """
    baseline: dict[str, list[str]] = {}
    ordered = sorted(arms, key=lambda a: (a.name != "bm25", a.name))
    if not any(a.name == "bm25" for a in ordered):
        run_arm(ARMS[0], rows, k=k, unit=False, baseline=baseline)
    return [
        run_arm(arm, rows, k=k, unit=unit, unit_budget=unit_budget,
                unit_alloc=unit_alloc, baseline=baseline)
        for arm in ordered
    ]


def arm_payload(
    arm: Arm,
    rows: Sequence[GoldRow],
    *,
    k: int,
    unit: bool,
    unit_budget: int = _DEFAULT_UNIT_BUDGET,
    unit_alloc: str = _DEFAULT_UNIT_ALLOC,
) -> dict[str, Any]:
    """Serialisable result of ONE arm, for the subprocess-isolated CLI path."""
    result = run_arm(
        arm, rows, k=k, unit=unit, unit_budget=unit_budget, unit_alloc=unit_alloc,
        baseline=None,
    )
    payload = asdict(result)
    payload.pop("added_total", None)  # computed by the parent from all arms
    payload.pop("added_gold", None)
    payload.pop("added_precision", None)
    return payload


def _apply_additions(results: Sequence[ArmResult], baseline_name: str = "bm25") -> None:
    """Fill ``added_*`` from a baseline arm's per-row sets.

    Done in the parent so arms can run in separate processes (each with a
    correctly-built index) while additions stay attributable to the sparse
    control.
    """
    baseline = next((r for r in results if r.name == baseline_name), None)
    if baseline is None or not baseline.detail:
        return
    base_refs = {d.row_id: set(d.retrieved) for d in baseline.detail}
    for result in results:
        if result.name == baseline_name:
            continue
        total = gold = 0
        for detail in result.detail:
            base = base_refs.get(detail.row_id)
            if base is None:
                continue
            added = [ref for ref in detail.retrieved if ref not in base]
            detail.added_over_bm25 = added
            total += len(added)
            gold += len([ref for ref in added if ref in set(detail.gold_heads)])
        result.added_total = total
        result.added_gold = gold
        result.added_precision = (gold / total) if total else 0.0


def result_from_payload(payload: dict[str, Any]) -> ArmResult:
    """Rehydrate an :class:`ArmResult` from a child process's JSON."""
    detail = [RowDetail(**d) for d in payload.pop("detail", [])]
    return ArmResult(**payload, detail=detail)


# ── Reporting ────────────────────────────────────────────────────────────────


def markdown_table(results: Sequence[ArmResult]) -> str:
    """Render the retrieval-grain comparison as a GitHub-flavoured table."""
    lines = [
        "| arm | head recall | row all-heads | precision | F1 | nDCG@k | excess refs | ctx chars | "
        "added refs | added gold-precision |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r.name}` | {r.head_recall:.3f} | {r.row_all_head_recall:.3f} | "
            f"{r.head_precision:.3f} | {r.head_f1:.3f} | {r.ndcg:.3f} | "
            f"{r.excess_refs_mean:.2f} | {r.context_chars_mean:,.0f} | "
            f"{r.added_total} | {r.added_precision:.3f} |"
        )
    unit_rows = [
        r for r in results if r.unit_denominator
    ]
    if unit_rows:
        lines += [
            "",
            "| arm | unit n | overlap top-1 | overlap coverage>=0.8 | coverage mean | "
            "paragraph BM25 top-1 | SVD-grain top-1 | emit budget | emit alloc | "
            "emitted chars mean | emitted chars p95 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in unit_rows:
            lines.append(
                f"| `{r.name}` | {r.unit_denominator} | {r.unit_overlap_top1:.3f} | "
                f"{r.unit_overlap_covered:.3f} | {r.unit_overlap_coverage_mean:.3f} | "
                f"{r.unit_bm25_top1:.3f} | {r.unit_svd_top1:.3f} | {r.unit_budget} | "
                f"`{r.unit_alloc}` | {r.unit_emitted_chars_mean:,.0f} | "
                f"{r.unit_emitted_chars_p95:,.0f} |"
            )
    return "\n".join(lines)


def _summary_payload(results: Sequence[ArmResult], rows: Sequence[GoldRow], k: int) -> dict[str, Any]:
    return {
        "instrument": "evals.retrieval.unit_grain",
        "round": "r449",
        "k": k,
        "n_rows": len(rows),
        "gold_path": str(_DEFAULT_GOLD.relative_to(_REPO)).replace("\\", "/"),
        "offline_env": _OFFLINE_ENV,
        "arms": [
            {kk: vv for kk, vv in asdict(r).items() if kk != "detail"} for r in results
        ],
        "arms_run": [r.name for r in results],
        "dense_backends": {r.name: r.embedding_backend for r in results},
    }


def _spawn_arm(arm_name: str, *, gold: str, rows: int | None, k: int, unit: bool,
               tmp: Path, unit_budget: int, unit_alloc: str) -> dict[str, Any]:
    """Run one arm in a fresh interpreter and return its JSON payload.

    Process isolation is not tidiness: ``_build_index`` is ``lru_cache``d and
    the dense index is a module singleton, so two arms with different index
    flags in one process do not measure their own configuration. Isolating them
    is what makes ``ctx_fields`` a real measurement rather than a silent replay
    of the first arm's index.
    """
    cmd = [
        sys.executable, "-m", "evals.retrieval.unit_grain",
        "--run-one", arm_name, "--gold", gold, "--k", str(k),
        "--unit-budget", str(unit_budget), "--unit-alloc", unit_alloc,
        "--json-out", str(tmp),
    ]
    if rows is not None:
        cmd += ["--rows", str(rows)]
    if not unit:
        cmd += ["--no-unit"]
    proc = subprocess.run(cmd, cwd=str(_REPO), capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists():
        raise RuntimeError(
            f"arm {arm_name!r} subprocess failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '').strip()[-600:]}"
        )
    return json.loads(tmp.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default="bm25,dense_a,dense_b,default,rrf,score",
                        help="comma-separated arm names")
    parser.add_argument("--gold", default=str(_DEFAULT_GOLD))
    parser.add_argument("--rows", type=int, default=None, help="limit rows (smoke runs)")
    parser.add_argument("--k", type=int, default=_PRODUCTION_K)
    parser.add_argument("--no-unit", action="store_true", help="skip passage-grain selectors")
    parser.add_argument("--unit-budget", type=int, default=_DEFAULT_UNIT_BUDGET,
                        help="per-provision verbatim emission budget (500 = verbatim answer, "
                             "1200 = Stage-2 grounding)")
    parser.add_argument("--unit-alloc", default=_DEFAULT_UNIT_ALLOC,
                        help="passage allocation policy (rank|pack|density|top1|split)")
    parser.add_argument("--out", default=None, help="write the full JSON payload here")
    parser.add_argument("--md-out", default=None, help="write the markdown table here")
    parser.add_argument("--details", action="store_true", help="include per-row detail in JSON")
    parser.add_argument("--in-process", action="store_true",
                        help="run all arms in one process (only valid for index-identical arms)")
    parser.add_argument("--run-one", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json-out", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    known = {a.name: a for a in ARMS}
    if args.run_one:
        if args.run_one not in known:
            parser.error(f"unknown arm: {args.run_one}")
        rows = load_gold(Path(args.gold), limit=args.rows)
        payload = arm_payload(
            known[args.run_one], rows, k=args.k, unit=not args.no_unit,
            unit_budget=args.unit_budget, unit_alloc=args.unit_alloc,
        )
        Path(args.json_out).write_text(json.dumps(payload), encoding="utf-8")
        return 0

    wanted = [name.strip() for name in args.arms.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in known]
    if unknown:
        parser.error(f"unknown arm(s): {', '.join(unknown)}; known: {', '.join(sorted(known))}")

    rows = load_gold(Path(args.gold), limit=args.rows)
    if not rows:
        parser.error("gold set is empty")

    ordered = sorted([known[name] for name in wanted], key=lambda a: (a.name != "bm25", a.name))
    if args.in_process:
        results = run_arms(
            ordered, rows, k=args.k, unit=not args.no_unit,
            unit_budget=args.unit_budget, unit_alloc=args.unit_alloc,
        )
    else:
        if not any(a.name == "bm25" for a in ordered):
            ordered = [ARMS[0], *ordered]
        import tempfile  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            results = []
            for arm in ordered:
                tmp = Path(tmpdir) / f"{arm.name}.json"
                results.append(
                    result_from_payload(
                        _spawn_arm(arm.name, gold=args.gold, rows=args.rows,
                                   k=args.k, unit=not args.no_unit, tmp=tmp,
                                   unit_budget=args.unit_budget,
                                   unit_alloc=args.unit_alloc)
                    )
                )
        _apply_additions(results)
        if "bm25" not in wanted:
            results = [r for r in results if r.name != "bm25"]

    table = markdown_table(results)
    print(f"R449 retrieval-grain harness — k={args.k}, rows={len(rows)}")
    print(table)
    print(
        "dense backend per arm: "
        + ", ".join(f"{r.name}={r.embedding_backend}" for r in results)
    )

    if args.out:
        payload = _summary_payload(results, rows, args.k)
        if args.details:
            payload["detail"] = {r.name: [asdict(d) for d in r.detail] for r in results}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote {out_path}")
    if args.md_out:
        md_path = Path(args.md_out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(table + "\n", encoding="utf-8")
        print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    sys.exit(main())
