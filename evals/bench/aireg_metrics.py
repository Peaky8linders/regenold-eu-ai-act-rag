"""Verdict-match metric for the AIReg-Bench secondary benchmark.

The seven canonical Regenold rubric axes (correctness, conciseness,
reference correctness, latency, tone) are already implemented in
``evals.bench.metrics`` — we reuse those unchanged. AIReg-Bench adds
one new axis:

    **Verdict match** — does the engine's predicted answer carry the
    same compliance verdict (compliant / borderline / non-compliant)
    as the median human annotator?

The compliance signal is extracted from the engine's free-form answer
with three layered detectors (each tried in order, first hit wins):

    1. Explicit verdict keywords:
         "non-compliant" / "not compliant"   → non-compliant
         "compliant"                         → compliant
         "borderline" / "partially compliant"→ borderline

    2. Modality cues with negation handling:
         "does not comply" / "fails to comply" → non-compliant
         "complies with"                       → compliant
         "may comply" / "could comply"         → borderline

    3. Numeric scores in answer (rare on this engine, but defensive):
         "score: 1-2"  → non-compliant
         "score: 3"    → borderline
         "score: 4-5"  → compliant

When no signal is detectable, the prediction is ``unknown`` and counts
as a miss against any defined gold verdict. The matching itself is
exact equality between predicted and gold labels.

The output is stable across runs (deterministic regex; no LLM call).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from evals.bench.aireg_dataset import (
    VERDICT_BORDERLINE,
    VERDICT_COMPLIANT,
    VERDICT_NON_COMPLIANT,
    VERDICT_SET,
    VERDICT_UNKNOWN,
    bucket_compliance_score,
    median,
)


# ── Verdict extraction ───────────────────────────────────────────────────


# Tier 1: explicit verdict keywords. Order matters — "non-compliant"
# must be tested before "compliant" so the negation prefix wins.
_RE_NON_COMPLIANT = re.compile(
    r"\b("
    r"non[\-\s]?compliant"
    r"|not\s+compliant"
    r"|non[\-\s]?compliance"
    r"|fails?\s+to\s+(?:comply|meet)"
    r"|does\s+not\s+comply"
    r"|do\s+not\s+comply"
    r"|cannot\s+comply"
    r"|breach(?:es)?\s+(?:the\s+)?(?:requirement|article)"
    r"|prohibited"
    r")\b",
    re.IGNORECASE,
)

_RE_BORDERLINE = re.compile(
    r"\b("
    r"borderline"
    r"|partially\s+compliant"
    r"|partial\s+compliance"
    r"|may\s+comply"
    r"|might\s+comply"
    r"|could\s+comply"
    r"|conditional\s+compliance"
    r"|some\s+(?:gaps?|concerns?)"
    r"|likely\s+but\s+not"
    r")\b",
    re.IGNORECASE,
)

_RE_COMPLIANT = re.compile(
    r"\b("
    r"is\s+compliant"
    r"|are\s+compliant"
    r"|fully\s+compliant"
    r"|in\s+compliance\s+with"
    r"|complies\s+with"
    r"|meets?\s+(?:the\s+)?requirements?"
    r"|satisf(?:y|ies|ied)\s+(?:the\s+)?(?:requirements?|article)"
    r")\b",
    re.IGNORECASE,
)

# Tier 3: numeric-score fallback. Engine doesn't currently emit these,
# but defensive against future Stage-2 LLM outputs.
_RE_SCORE = re.compile(
    r"(?:score|rating|compliance)\s*[:=]?\s*([1-5])(?:\s*/\s*5)?",
    re.IGNORECASE,
)


def extract_predicted_verdict(answer: str) -> str:
    """Map a free-form answer to one of the four verdict labels.

    Always returns one of ``compliant`` / ``borderline`` /
    ``non-compliant`` / ``unknown``. Side-effect-free (no I/O, no logs).
    """
    if not answer or not isinstance(answer, str):
        return VERDICT_UNKNOWN
    text = answer.strip()
    if _RE_NON_COMPLIANT.search(text):
        return VERDICT_NON_COMPLIANT
    if _RE_BORDERLINE.search(text):
        return VERDICT_BORDERLINE
    if _RE_COMPLIANT.search(text):
        return VERDICT_COMPLIANT
    m = _RE_SCORE.search(text)
    if m:
        try:
            n = int(m.group(1))
        except (TypeError, ValueError):
            return VERDICT_UNKNOWN
        return bucket_compliance_score(n)
    return VERDICT_UNKNOWN


# ── Gold-verdict aggregation ─────────────────────────────────────────────


def gold_verdict_from_annotations(
    annotation_scores: Iterable[int | float | None],
) -> str:
    """Reduce N annotator scores → one gold verdict via median bucket.

    Used when multiple annotators graded the same ``(doc, article)``.
    """
    scores = [s for s in annotation_scores if s is not None]
    if not scores:
        return VERDICT_UNKNOWN
    med = median(scores)
    return bucket_compliance_score(med)


# ── Verdict match scoring ────────────────────────────────────────────────


def verdict_match(pred_verdict: str, gold_verdict: str) -> float:
    """Binary 1.0/0.0 — does predicted verdict equal gold verdict?

    Unknown gold means we can't score → 0.0 (counted as a miss). This
    is more conservative than dropping the row; the runner can filter
    on ``gold_verdict != 'unknown'`` if it wants population-only stats.
    """
    if gold_verdict not in VERDICT_SET:
        return 0.0
    if pred_verdict not in VERDICT_SET:
        return 0.0
    return 1.0 if pred_verdict == gold_verdict else 0.0


def verdict_soft_match(pred_verdict: str, gold_verdict: str) -> float:
    """Three-class soft scoring with adjacent-class partial credit.

    Returns 1.0 for an exact match, 0.5 for an off-by-one
    (borderline ↔ {compliant, non-compliant}), and 0.0 for
    polar opposites (compliant ↔ non-compliant) or any unknown.

    Useful because annotator medians sit on the boundary often;
    grading borderline ≈ compliant should not be punished as harshly
    as flipping a non-compliant to compliant.
    """
    if (
        pred_verdict not in VERDICT_SET
        or gold_verdict not in VERDICT_SET
    ):
        return 0.0
    if pred_verdict == gold_verdict:
        return 1.0
    polar = {VERDICT_COMPLIANT, VERDICT_NON_COMPLIANT}
    if {pred_verdict, gold_verdict} == polar:
        return 0.0
    # One of them is borderline — adjacent-class partial credit.
    return 0.5


# ── Confusion matrix for terminal report ─────────────────────────────────


@dataclass
class VerdictReport:
    """Per-axis aggregate for the verdict-match column.

    ``confusion`` is a 4×4 nested dict (rows = gold, cols = pred) so
    the terminal scorecard can show e.g. how often the engine flipped
    non-compliant gold to compliant pred (the worst miss type).
    """

    n: int
    exact_match: float
    soft_match: float
    confusion: dict[str, dict[str, int]]
    coverage: float  # fraction of items where gold_verdict != unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "verdict_exact": round(self.exact_match, 4),
            "verdict_soft": round(self.soft_match, 4),
            "verdict_coverage": round(self.coverage, 4),
            "confusion": self.confusion,
        }


def _zero_confusion() -> dict[str, dict[str, int]]:
    labels = list(VERDICT_SET) + [VERDICT_UNKNOWN]
    return {gold: {pred: 0 for pred in labels} for gold in labels}


def aggregate_verdicts(rows: Iterable[dict[str, Any]]) -> VerdictReport:
    """Build the verdict scorecard from per-row dicts.

    Each input row must have ``pred_verdict`` and ``gold_verdict``
    keys (already lower-cased; ``unknown`` allowed).
    """
    rows = list(rows)
    n = len(rows)
    if n == 0:
        return VerdictReport(
            n=0,
            exact_match=0.0,
            soft_match=0.0,
            confusion=_zero_confusion(),
            coverage=0.0,
        )
    confusion = _zero_confusion()
    exact_sum = 0.0
    soft_sum = 0.0
    scored = 0
    for r in rows:
        pred = r.get("pred_verdict") or VERDICT_UNKNOWN
        gold = r.get("gold_verdict") or VERDICT_UNKNOWN
        if pred not in confusion[gold]:
            # Defensive: if a caller passed a custom label, fold it
            # into 'unknown' rather than KeyError.
            pred_key = VERDICT_UNKNOWN
        else:
            pred_key = pred
        confusion[gold][pred_key] += 1
        if gold in VERDICT_SET:
            scored += 1
            exact_sum += verdict_match(pred, gold)
            soft_sum += verdict_soft_match(pred, gold)
    return VerdictReport(
        n=n,
        exact_match=(exact_sum / scored) if scored else 0.0,
        soft_match=(soft_sum / scored) if scored else 0.0,
        confusion=confusion,
        coverage=(scored / n) if n else 0.0,
    )


__all__ = [
    "VerdictReport",
    "aggregate_verdicts",
    "extract_predicted_verdict",
    "gold_verdict_from_annotations",
    "verdict_match",
    "verdict_soft_match",
]
