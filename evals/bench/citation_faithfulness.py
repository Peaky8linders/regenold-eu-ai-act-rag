"""Deterministic citation-faithfulness proxy for the unbiased eval harness.

Why this module exists:
    Round 32+ rubric scoring matches references against gold (Jaccard) but
    NEVER asks whether the answer prose actually USES the cited references.
    ALCE (Gao et al., EMNLP 2023) splits citation faithfulness into:

      * Citation Recall    — fraction of answer sentences supported by
                             at least one cited reference.
      * Citation Precision — fraction of cited references actually used
                             by at least one answer sentence.

    ALCE uses an NLI model for entailment; we ship a deterministic proxy
    so the eval can run without a GPU, model download, or external API
    call. The proxy: a sentence is "supported" by a ref iff the
    sentence's stopword-filtered token bag shares >= ``MIN_OVERLAP_TOKENS``
    tokens with the ref's KB text (article full text + KB obligation
    summary). This is a lower bound on real entailment but a sane,
    stable, sub-millisecond signal.

Public API:
    * :class:`FaithfulnessScore` — frozen dataclass with recall, precision,
      F1 and the underlying counts.
    * :func:`score_citation_faithfulness` — score a single answer/refs pair.
    * :func:`aggregate` — average a list of scores into the same shape.

Pure stdlib + the existing project imports (sentence splitter, KB).
Never raises; degrades to zeros on bad inputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from app.engines.sentence_index import split_legal_sentences


# Stopword list copied verbatim from app/data/kb_search.py::_STOPWORDS
# (kept local to honour the eval-vs-app boundary — DO NOT touch app/).
# Match the existing vocabulary so faithfulness signal is comparable
# with the BM25 retrieval scoring already in the project.
_STOPWORDS: frozenset[str] = frozenset({
    # English function words
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at",
    "to", "from", "for", "with", "without", "into", "onto", "by",
    "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing", "done",
    "will", "would", "should", "could", "may", "might", "must",
    "shall", "can", "cannot", "no", "not",
    "this", "that", "these", "those",
    "it", "its", "they", "them", "their", "there", "here",
    "who", "what", "which", "where", "when", "why", "how",
    "we", "us", "our", "you", "your", "i", "me", "my",
    "any", "all", "some", "each", "every", "either", "neither",
    "more", "most", "less", "least", "many", "much", "few",
    "such", "also", "than", "then", "so",
    # AI Act prose recurring words
    "system", "systems", "ai", "provider", "providers", "deployer",
    "deployers", "obligation", "obligations", "requirement",
    "requirements", "requires", "required", "include", "includes",
    "including", "covered", "cover", "covers", "subject", "use", "used",
    "using", "uses", "act", "regulation", "regulations", "article",
    "articles", "annex", "annexes", "section", "sections", "art",
})


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

# A sentence is "supported" by a ref iff it shares at least this many
# non-stopword tokens with the ref's KB text. 3 is a deliberately
# permissive floor — even short answer fragments will clear it when
# they paraphrase the regulation text. Stricter thresholds collapse
# legitimate prose into false-negatives.
MIN_OVERLAP_TOKENS: int = 3


def _tokenize(text: str) -> set[str]:
    """Lowercase + alphanumeric + stopword-filter; sets for O(1) intersect."""
    out: set[str] = set()
    if not text:
        return out
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in _STOPWORDS:
            continue
        if len(raw) <= 1:
            continue
        if raw.isdigit() and len(raw) > 4:
            continue
        out.add(raw)
    return out


# ── Wire-format ref → internal key normalisation ─────────────────────────


_ART_REF_RE = re.compile(r"^Article\s+(\d+)(?:[.\(](.*))?$", re.IGNORECASE)
_ANNEX_REF_RE = re.compile(r"^Annex\s+([IVX]+)(?:[.\(](.*))?$", re.IGNORECASE)


def _normalise_ref_to_kb_key(ref: str) -> str | None:
    """Convert a wire ref ("Article 13", "Article 13.1", "Annex III")
    to its internal KB key ("Art. 13", "Annex III").

    The wire output uses the strict ``Article N`` / ``Annex X`` form
    enforced by ``_ARTICLE_OUTPUT_RE`` in
    ``app/integrations/regenold/models.py``. The internal KB is keyed
    on ``Art. N`` / ``Annex X``.

    Returns ``None`` for malformed inputs — caller treats them as
    unsupported (precision-side penalty).
    """
    if not ref:
        return None
    s = ref.strip()
    m = _ART_REF_RE.match(s)
    if m:
        return f"Art. {m.group(1)}"
    m = _ANNEX_REF_RE.match(s)
    if m:
        return f"Annex {m.group(1).upper()}"
    return None


def _default_kb_text_lookup() -> Callable[[str], str]:
    """Build the default KB-text lookup once.

    Lookup order, concatenated:
        1. ``app.data.eu_ai_act_corpus.ARTICLE_FULL_TEXT[key]`` — full
           EUR-Lex prose where available.
        2. ``app.data.kb.EC_CHECKER_OBLIGATION_MAP[key]["summary"]`` —
           hand-curated obligation summary.

    If both are missing the lookup returns ``""`` and the ref counts
    as unused (precision penalty).
    """
    # Lazy-import inside so test fixtures can monkeypatch the lookup
    # without paying the import cost at collection time.
    try:
        from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT as _FULL
    except Exception:  # noqa: BLE001
        _FULL = {}
    try:
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP as _KB
    except Exception:  # noqa: BLE001
        _KB = {}

    def _lookup(kb_key: str) -> str:
        parts: list[str] = []
        full_text = _FULL.get(kb_key)
        if full_text:
            parts.append(full_text)
        kb_entry = _KB.get(kb_key)
        if kb_entry:
            try:
                summary = kb_entry.get("summary", "")
            except Exception:  # noqa: BLE001
                summary = ""
            if summary:
                parts.append(summary)
        return " ".join(parts)

    return _lookup


_DEFAULT_LOOKUP: Callable[[str], str] | None = None


def _get_default_lookup() -> Callable[[str], str]:
    global _DEFAULT_LOOKUP
    if _DEFAULT_LOOKUP is None:
        _DEFAULT_LOOKUP = _default_kb_text_lookup()
    return _DEFAULT_LOOKUP


# ── Score dataclass ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class FaithfulnessScore:
    """Score for a single (answer, refs) pair.

    Attributes:
        citation_recall    Fraction of answer-sentence-claims supported
                           by ≥1 cited ref. ``1.0`` when answer is empty
                           (vacuous: no claims to be supported).
        citation_precision Fraction of cited refs used by ≥1 sentence.
                           ``0.0`` when refs list is empty (no refs to
                           justify) AND there are sentences; ``0.0``
                           when refs list is empty and answer is empty
                           too (no refs → 0/0 → conservative 0.0).
        citation_f1        Harmonic mean. ``0.0`` if either side is 0.
        n_sentences        Total non-trivial answer sentences.
        n_supported        Sentences with at least one supporting ref.
        n_used_refs        Refs with at least one supporting sentence.
    """

    citation_recall: float
    citation_precision: float
    citation_f1: float
    n_sentences: int
    n_supported: int
    n_used_refs: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "citation_recall": self.citation_recall,
            "citation_precision": self.citation_precision,
            "citation_f1": self.citation_f1,
            "n_sentences": self.n_sentences,
            "n_supported": self.n_supported,
            "n_used_refs": self.n_used_refs,
        }


_ZERO = FaithfulnessScore(0.0, 0.0, 0.0, 0, 0, 0)


# ── Core scoring ─────────────────────────────────────────────────────────


def score_citation_faithfulness(
    answer: str,
    references: list[str],
    *,
    kb_text_lookup: Callable[[str], str] | None = None,
) -> FaithfulnessScore:
    """Score how well the answer prose is grounded in the cited refs.

    Deterministic proxy for ALCE-style NLI:

        * Split the answer with the project's regulatory sentence
          splitter (``split_legal_sentences``).
        * For each sentence, count it as supported iff its
          stopword-filtered token bag shares ``>= MIN_OVERLAP_TOKENS``
          tokens with at least one cited reference's KB text.
        * Recall    = supported_sentences / total_sentences
        * Precision = used_refs           / total_refs
        * F1        = 2pr / (p + r)

    Never raises. Returns the zero score on a broken input pair.
    """
    if answer is None:
        answer = ""
    if references is None:
        references = []

    lookup = kb_text_lookup or _get_default_lookup()

    # Reference-side token bags
    ref_tokens: list[tuple[str, set[str]]] = []
    for ref in references:
        kb_key = _normalise_ref_to_kb_key(ref)
        if kb_key is None:
            # Unrecognised wire-format ref → empty bag → never supports
            # any sentence. Cost: this ref counts in the precision
            # denominator but never lands in the numerator.
            ref_tokens.append((ref, set()))
            continue
        try:
            text = lookup(kb_key) or ""
        except Exception:  # noqa: BLE001
            text = ""
        ref_tokens.append((ref, _tokenize(text)))

    # Answer-side sentences. Strip trivial whitespace-only items.
    try:
        sentences = split_legal_sentences(answer)
    except Exception:  # noqa: BLE001
        sentences = []
    sentences = [s for s in sentences if s and s.strip()]

    if not sentences:
        # Empty answer → recall is vacuously 1.0 (nothing to support).
        # Precision is 0/N when refs > 0, else 0/0 → 0.0 (conservative).
        recall = 1.0
        if references:
            precision = 0.0
        else:
            precision = 0.0
        f1 = 0.0  # F1 requires non-zero both sides
        return FaithfulnessScore(recall, precision, f1, 0, 0, 0)

    used_refs: set[int] = set()
    n_supported = 0

    for sent in sentences:
        sent_tokens = _tokenize(sent)
        if not sent_tokens:
            # Stopword-only sentence (rare) — never countable; treat
            # as supported by convention so we don't penalise the
            # answer for trivial whitespace residue.
            n_supported += 1
            continue
        supported = False
        for i, (_, rtoks) in enumerate(ref_tokens):
            if not rtoks:
                continue
            overlap = len(sent_tokens & rtoks)
            if overlap >= MIN_OVERLAP_TOKENS:
                supported = True
                used_refs.add(i)
        if supported:
            n_supported += 1

    n_sentences = len(sentences)
    n_refs = len(references)
    recall = n_supported / n_sentences if n_sentences else 1.0
    precision = (len(used_refs) / n_refs) if n_refs else 1.0
    # When refs == 0 and there ARE sentences, the answer claims things
    # without ANY citation — that's a strict precision failure. Override
    # the vacuous 1.0 above.
    if n_refs == 0 and n_sentences > 0:
        precision = 0.0
    if recall + precision > 0:
        f1 = 2.0 * recall * precision / (recall + precision)
    else:
        f1 = 0.0
    return FaithfulnessScore(
        citation_recall=round(recall, 4),
        citation_precision=round(precision, 4),
        citation_f1=round(f1, 4),
        n_sentences=n_sentences,
        n_supported=n_supported,
        n_used_refs=len(used_refs),
    )


def aggregate(scores: Iterable[FaithfulnessScore]) -> dict[str, float | int]:
    """Macro-average a list of FaithfulnessScore into a summary dict.

    Returns zero counts on empty input. Macro-averaging (mean of
    per-row scores) is the standard for ALCE-style citation metrics.
    """
    rows = list(scores)
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "citation_recall": 0.0,
            "citation_precision": 0.0,
            "citation_f1": 0.0,
            "n_sentences_total": 0,
            "n_supported_total": 0,
            "n_used_refs_total": 0,
        }
    recall = sum(r.citation_recall for r in rows) / n
    precision = sum(r.citation_precision for r in rows) / n
    # F1 is recomputed from the macro averages (NOT averaged) — the
    # per-row F1 would over-weight zero rows.
    if recall + precision > 0:
        f1 = 2.0 * recall * precision / (recall + precision)
    else:
        f1 = 0.0
    return {
        "n": n,
        "citation_recall": round(recall, 4),
        "citation_precision": round(precision, 4),
        "citation_f1": round(f1, 4),
        "n_sentences_total": sum(r.n_sentences for r in rows),
        "n_supported_total": sum(r.n_supported for r in rows),
        "n_used_refs_total": sum(r.n_used_refs for r in rows),
    }


__all__ = [
    "FaithfulnessScore",
    "MIN_OVERLAP_TOKENS",
    "aggregate",
    "score_citation_faithfulness",
]
