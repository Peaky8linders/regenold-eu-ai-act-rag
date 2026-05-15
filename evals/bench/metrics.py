"""Per-rubric scoring functions for the Regenold competition.

The 2026 competition rubric scores 8 axes (page 3 of the rules deck):

    1. Answer Correctness (Loose)   — substantive agreement with gold
    2. Answer Correctness (Strict)  — every gold-anchor keyword present
    3. Answer Conciseness           — length normalised vs gold answer
    4. Reference Correctness (Loose) — recall of gold article set
    5. Reference Correctness (Strict) — exact set match with gold
    6. Reference Conciseness        — over/under-citation penalty
    7. Latency                      — p50, p95, max ms
    8. Regulatory Tone              — regulator-voice classifier

Every function is pure (no I/O, no globals) so the runner can call them
deterministically and reproduce a score from a stored JSON sidecar.

Design intent:
    * "Loose" metrics use token-Jaccard or set-recall — robust to phrasing.
    * "Strict" metrics use exact-set or every-keyword-present — robust to
      hallucinated additions.
    * Conciseness uses a symmetric length-ratio penalty so both
      under-shooting and over-shooting are punished proportionally.
    * Tone is a heuristic classifier — first-person, hedging, and AI
      preamble phrases each subtract points; regulator-voice anchors add.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


# ── Tokenisation ─────────────────────────────────────────────────────────


_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "of", "to", "in",
        "on", "for", "with", "as", "by", "is", "are", "was", "were", "be",
        "been", "being", "this", "that", "these", "those", "it", "its",
        "must", "shall", "should", "would", "can", "may", "from", "at",
        "any", "all", "such", "which", "who", "what", "when", "where",
        "their", "they", "them", "his", "her", "he", "she", "you", "we",
        "i", "us", "our", "your", "my", "do", "does", "did", "have", "has",
        "had", "not", "no", "yes",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")


def _tokens(text: str) -> set[str]:
    """Lowercase, dedup, drop stopwords + sub-3-char fragments."""
    if not text:
        return set()
    raw = _TOKEN_RE.findall(text.lower())
    return {t for t in raw if len(t) >= 3 and t not in _STOPWORDS}


# ── Citation helpers ─────────────────────────────────────────────────────


_ARTICLE_HEAD_RE = re.compile(r"^Article\s+(\d+)(?:\..*)?$")
_ANNEX_HEAD_RE = re.compile(r"^Annex\s+([IVXLC]+)(?:\..*)?$")


def article_head(ref: str) -> str | None:
    """Strip ``Article 13.1.a`` → ``Article 13``; return None if not parseable."""
    if not isinstance(ref, str):
        return None
    m = _ARTICLE_HEAD_RE.match(ref.strip())
    if m:
        return f"Article {int(m.group(1))}"
    m = _ANNEX_HEAD_RE.match(ref.strip())
    if m:
        return f"Annex {m.group(1).upper()}"
    return None


def article_heads(refs: Iterable[str]) -> set[str]:
    """Project a list of refs onto the unique set of article/annex heads."""
    out: set[str] = set()
    for r in refs or ():
        h = article_head(r)
        if h is not None:
            out.add(h)
    return out


# ── 1+2: Answer correctness ──────────────────────────────────────────────


def answer_correctness_loose(pred: str, gold: str) -> float:
    """Token-Jaccard between predicted and gold answer.

    Returns 0.0–1.0. Robust to phrasing differences as long as the
    substantive vocabulary overlaps. Empty predicted answer → 0.0.
    """
    pt = _tokens(pred)
    gt = _tokens(gold)
    if not gt:
        return 0.0
    if not pt:
        return 0.0
    overlap = len(pt & gt)
    union = len(pt | gt)
    return overlap / union if union else 0.0


def answer_correctness_strict(pred: str, gold: str) -> float:
    """Fraction of gold-answer tokens present in the prediction.

    Strict because *every* gold token has to appear — but it's per-token
    fraction rather than binary, so a near-complete answer still scores
    high. A confidently wrong answer with new tokens that don't match
    scores low even if it's eloquent.
    """
    pt = _tokens(pred)
    gt = _tokens(gold)
    if not gt:
        return 0.0
    return len(pt & gt) / len(gt)


# ── 3: Answer conciseness ────────────────────────────────────────────────


def answer_conciseness(pred: str, gold: str) -> float:
    """Length-similarity score in 0.0–1.0. 1.0 = pred length == gold length.

    Symmetric — 2x too long and 2x too short both score 0.5. Falls off
    quadratically beyond 3x divergence to penalise rambling.
    """
    lg = len(gold or "")
    lp = len(pred or "")
    if lg == 0:
        return 1.0 if lp == 0 else 0.0
    if lp == 0:
        return 0.0
    ratio = min(lp, lg) / max(lp, lg)
    # Quadratic falloff so a 0.5 ratio (2x divergence) scores 0.25, not 0.5.
    return ratio * ratio


# ── 4+5: Reference correctness ───────────────────────────────────────────


def _gold_ref_set(relevant_article: int | list[int] | None) -> set[str]:
    """Normalise the gold reference field across QA + scenarios shapes.

    * qa_pairs.json: ``relevant_article`` is an int.
    * scenarios.json: ``related_articles`` is a list[int].
    """
    if relevant_article is None:
        return set()
    if isinstance(relevant_article, int):
        return {f"Article {relevant_article}"}
    if isinstance(relevant_article, list):
        return {f"Article {int(a)}" for a in relevant_article if a is not None}
    return set()


def reference_correctness_loose(
    pred_refs: list[str], gold_articles: int | list[int] | None
) -> float:
    """Recall of gold articles. 1.0 = every gold article is cited.

    Loose because over-citation isn't penalised here (that's what
    Reference Conciseness is for). A prediction that cites the right
    article among 8 distractors still scores 1.0 here.
    """
    pred_heads = article_heads(pred_refs)
    gold = _gold_ref_set(gold_articles)
    if not gold:
        return 1.0 if not pred_heads else 0.0
    overlap = len(pred_heads & gold)
    return overlap / len(gold)


def reference_correctness_strict(
    pred_refs: list[str], gold_articles: int | list[int] | None
) -> float:
    """F1 of predicted vs gold article set. 1.0 = exact set match.

    Strict — over-citation reduces precision, under-citation reduces
    recall. Combined into F1 so the score is symmetric to both errors.
    """
    pred_heads = article_heads(pred_refs)
    gold = _gold_ref_set(gold_articles)
    if not gold and not pred_heads:
        return 1.0
    if not gold or not pred_heads:
        return 0.0
    tp = len(pred_heads & gold)
    if tp == 0:
        return 0.0
    precision = tp / len(pred_heads)
    recall = tp / len(gold)
    return 2 * precision * recall / (precision + recall)


# ── 6: Reference conciseness ─────────────────────────────────────────────


def reference_conciseness(
    pred_refs: list[str], gold_articles: int | list[int] | None
) -> float:
    """Length-ratio of predicted refs vs gold reference count.

    For QA pairs (single relevant_article), the rubric is one citation —
    over-citation linearly degrades. For scenarios (multi-article gold),
    the ideal length is the gold cardinality.
    """
    pred_heads = article_heads(pred_refs)
    gold = _gold_ref_set(gold_articles)
    lp = len(pred_heads)
    lg = len(gold)
    if lg == 0:
        return 1.0 if lp == 0 else 0.0
    if lp == 0:
        return 0.0
    # Symmetric length ratio with quadratic falloff (same shape as answer
    # conciseness so the rubric is internally consistent).
    ratio = min(lp, lg) / max(lp, lg)
    return ratio * ratio


# ── 8: Regulatory tone ───────────────────────────────────────────────────


_TONE_DEMERIT_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    # AI-assistant preamble — biggest violator.
    (re.compile(r"\b(?:as an ai|i am an ai|i'm an ai|as an ai assistant)\b", re.I), 0.40),
    (re.compile(r"\b(?:as a language model|i am a language model)\b", re.I), 0.40),
    # First-person / hedging.
    (re.compile(r"\b(?:i think|i believe|in my opinion|i would say)\b", re.I), 0.25),
    (re.compile(r"\b(?:arguably|presumably|seemingly|it appears)\b", re.I), 0.15),
    # Excess hedging on the regulation itself.
    (re.compile(r"\b(?:might|could|may possibly|perhaps)\b\s+\bbe\b", re.I), 0.10),
    # Conversational fillers.
    (re.compile(r"\b(?:hi there|hello|hey|sure thing|of course)\b", re.I), 0.20),
    # Emoji / markdown leakage.
    (re.compile(r"[\U0001F600-\U0001F6FF]"), 0.30),
    (re.compile(r"\*\*"), 0.10),
)

_TONE_BONUS_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    # Regulator-voice anchors — refer to the regulation by canonical form.
    (re.compile(r"\bArticle\s+\d+\b"), 0.10),
    (re.compile(r"\bAnnex\s+[IVXLC]+\b"), 0.10),
    # Imperative modality consistent with regulator drafting.
    (re.compile(r"\b(?:must|shall|prohibits?|requires?|obligates?)\b", re.I), 0.05),
    # Role-of-obligation framing.
    (re.compile(r"\b(?:provider|deployer|importer|distributor)s?\b", re.I), 0.05),
)


def regulatory_tone(text: str) -> float:
    """Heuristic 0.0–1.0 regulator-voice score.

    Starts at 1.0 and subtracts for each demerit pattern, adds (capped)
    for each bonus anchor. Caps prevent stacking — e.g. citing 5 articles
    doesn't give 5x bonus.
    """
    if not text:
        return 0.0
    score = 1.0
    for pattern, penalty in _TONE_DEMERIT_PATTERNS:
        if pattern.search(text):
            score -= penalty
    # Bonus capped at +0.30 total so a paragraph stuffed with anchors
    # can't drown the demerits.
    bonus = 0.0
    for pattern, weight in _TONE_BONUS_PATTERNS:
        if pattern.search(text):
            bonus += weight
    score += min(bonus, 0.30)
    return max(0.0, min(1.0, score))


# ── 7: Latency aggregation ───────────────────────────────────────────────


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile, no numpy dep. ``pct`` in [0, 100]."""
    if not values:
        return 0.0
    s = sorted(values)
    if pct <= 0:
        return s[0]
    if pct >= 100:
        return s[-1]
    rank = max(1, int((pct / 100.0) * len(s) + 0.5))
    rank = min(rank, len(s))
    return s[rank - 1]


# ── Aggregate per-row scoring ────────────────────────────────────────────


@dataclass
class RowScore:
    """Eight-axis score for a single QA / scenario row."""

    answer_correctness_loose: float
    answer_correctness_strict: float
    answer_conciseness: float
    reference_correctness_loose: float
    reference_correctness_strict: float
    reference_conciseness: float
    latency_ms: float
    regulatory_tone: float

    def to_dict(self) -> dict[str, float]:
        return {
            "ans_correctness_loose": round(self.answer_correctness_loose, 4),
            "ans_correctness_strict": round(self.answer_correctness_strict, 4),
            "ans_conciseness": round(self.answer_conciseness, 4),
            "ref_correctness_loose": round(self.reference_correctness_loose, 4),
            "ref_correctness_strict": round(self.reference_correctness_strict, 4),
            "ref_conciseness": round(self.reference_conciseness, 4),
            "latency_ms": round(self.latency_ms, 2),
            "regulatory_tone": round(self.regulatory_tone, 4),
        }


def score_row(
    pred_answer: str,
    pred_refs: list[str],
    gold_answer: str,
    gold_articles: int | list[int] | None,
    latency_ms: float,
) -> RowScore:
    """Compute every metric for one row in one call."""
    return RowScore(
        answer_correctness_loose=answer_correctness_loose(pred_answer, gold_answer),
        answer_correctness_strict=answer_correctness_strict(pred_answer, gold_answer),
        answer_conciseness=answer_conciseness(pred_answer, gold_answer),
        reference_correctness_loose=reference_correctness_loose(
            pred_refs, gold_articles
        ),
        reference_correctness_strict=reference_correctness_strict(
            pred_refs, gold_articles
        ),
        reference_conciseness=reference_conciseness(pred_refs, gold_articles),
        latency_ms=latency_ms,
        regulatory_tone=regulatory_tone(pred_answer),
    )


# ── Batch-level aggregation ──────────────────────────────────────────────


def aggregate(rows: list[RowScore]) -> dict[str, float]:
    """Mean per axis + latency percentiles."""
    if not rows:
        return {}
    n = len(rows)
    s = lambda key: sum(getattr(r, key) for r in rows)
    latencies = [r.latency_ms for r in rows]
    return {
        "n": n,
        "ans_correctness_loose": round(s("answer_correctness_loose") / n, 4),
        "ans_correctness_strict": round(s("answer_correctness_strict") / n, 4),
        "ans_conciseness": round(s("answer_conciseness") / n, 4),
        "ref_correctness_loose": round(s("reference_correctness_loose") / n, 4),
        "ref_correctness_strict": round(s("reference_correctness_strict") / n, 4),
        "ref_conciseness": round(s("reference_conciseness") / n, 4),
        "regulatory_tone": round(s("regulatory_tone") / n, 4),
        "latency_p50_ms": round(percentile(latencies, 50), 2),
        "latency_p95_ms": round(percentile(latencies, 95), 2),
        "latency_max_ms": round(max(latencies) if latencies else 0.0, 2),
        "latency_mean_ms": round(sum(latencies) / n, 2),
    }
