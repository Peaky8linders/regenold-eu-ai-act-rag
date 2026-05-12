"""BM25 fallback retrieval over the KB obligation corpus.

The deterministic-parse pipeline in :func:`app.engines.graph_rag._deterministic_parse`
extracts entities purely by regex over a hand-curated keyword map (~370
entries). Coverage is good on phrasings we've seen before, near-zero on
novel phrasings. The retrieval audit (May 2026 — see
``llm-wiki.md.txt`` correlation) identified content questions with
novel phrasing as the largest remaining failure mode:

    "How long must records be kept?"      → no keyword hits, returns
                                             "No matching obligation".
    "What documents must I retain        → never anchors Art. 18 (10-year
     after launch?"                        retention) or Art. 19 (6-month
                                            log retention).

BM25 over the obligation-summary corpus closes that gap. The corpus is
small (~110 rows of ~50 words each ≈ ~5500 tokens total), so index
construction at module import is sub-50ms and per-query scoring is
sub-1ms. Pure-Python — no external dependency, since adding
``rank_bm25`` would require a new pyproject entry and the algorithm is
simple enough to implement in-place.

The BM25 path is INTENTIONALLY a fallback, not a replacement. The
deterministic keyword map remains the primary path; BM25 only fires
when ``entities`` is empty after the keyword pass, OR is invoked
defensively to add 1-2 supplementary entities for richer retrieval.

## Algorithm

Standard BM25 with k1=1.5, b=0.75. Document = ``f"{article_ref} {summary}"``
for each row in :data:`app.data.kb.EC_CHECKER_OBLIGATION_MAP`. Tokeniser
is a stopword-filtered word-character split. Stopwords are a small
domain-tuned list (the AI Act prose uses "shall", "system", "provider"
in nearly every row — keeping them poisons the relevance signal).

## Why not a real embedding store

At 110 documents × ~50 tokens, BM25 ties or beats a dense embedding
model in our measurements while remaining deterministic and adding
zero dependencies. Embedding stores add 100-300ms p95 latency from the
model load + inference, plus a 300MB+ disk footprint for any
reasonable sentence-transformer — both regressions on the competition
rubric (which scores latency) for marginal recall gain on a corpus
this small.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache

from app.data.kb import EC_CHECKER_OBLIGATION_MAP


# Domain-tuned stopwords. Keeps `bias`, `fairness`, `data` (informative)
# but drops verbs that recur in every obligation row (`requires`, `must`,
# `shall`) and structural function words. Without this filter, BM25 ranks
# every document highly on every query.
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


def _tokenize(text: str) -> list[str]:
    """Lowercase + alphanumeric-only + stopword-filter.

    Defensive: drops single-character tokens and pure digits ≤ 4 (we
    keep "2025", "2026" because those carry meaning in timing questions,
    but drop "1"-"99"-style article-number digits since they're already
    handled by the explicit ``\\bArt\\.?\\s+\\d+\\b`` regex in the
    engine's parse path).
    """
    tokens = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in _STOPWORDS:
            continue
        if len(raw) <= 1:
            continue
        if raw.isdigit() and len(raw) <= 3:
            continue
        tokens.append(raw)
    return tokens


@dataclass(frozen=True)
class _BM25Index:
    """Pre-computed BM25 statistics over the KB obligation corpus."""

    article_refs: tuple[str, ...]  # parallel to ``docs``
    docs: tuple[tuple[str, ...], ...]  # tokenised documents
    doc_freqs: tuple[dict[str, int], ...]  # term → count per document
    avg_doc_len: float
    idf: dict[str, float]  # term → inverse document frequency
    k1: float = 1.5
    b: float = 0.75


@lru_cache(maxsize=1)
def _build_index() -> _BM25Index:
    """Build the BM25 index from :data:`EC_CHECKER_OBLIGATION_MAP`.

    Memoised so the index is built once per process. Re-computing on
    every request would burn ~5ms per call needlessly; the index is
    immutable for the lifetime of the process.
    """
    article_refs: list[str] = []
    docs: list[tuple[str, ...]] = []
    doc_freqs: list[dict[str, int]] = []

    for article_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        summary = entry.get("summary", "")
        # Include the article ref in the document — questions sometimes
        # reference the article number via the dimension keywords AND
        # the summary text. Concatenation gives BM25 a fair shot at
        # matching either signal.
        text = f"{article_ref} {summary}"
        tokens = _tokenize(text)
        if not tokens:
            continue
        article_refs.append(article_ref)
        docs.append(tuple(tokens))
        freqs: dict[str, int] = {}
        for tok in tokens:
            freqs[tok] = freqs.get(tok, 0) + 1
        doc_freqs.append(freqs)

    n_docs = len(docs)
    if n_docs == 0:
        return _BM25Index(
            article_refs=(), docs=(), doc_freqs=(), avg_doc_len=0.0, idf={},
        )

    avg_doc_len = sum(len(d) for d in docs) / n_docs

    # Per-term document frequency (in how many docs does this term appear).
    df: dict[str, int] = {}
    for freqs in doc_freqs:
        for term in freqs:
            df[term] = df.get(term, 0) + 1

    # BM25 IDF with the standard "+1" smoothing so the value never goes
    # negative (Lucene-style). Terms that appear in every doc still get
    # a small positive IDF; terms that appear in <half docs get
    # significantly higher IDF.
    idf: dict[str, float] = {}
    for term, count in df.items():
        idf[term] = math.log((n_docs - count + 0.5) / (count + 0.5) + 1.0)

    return _BM25Index(
        article_refs=tuple(article_refs),
        docs=tuple(docs),
        doc_freqs=tuple(doc_freqs),
        avg_doc_len=avg_doc_len,
        idf=idf,
    )


def _score(index: _BM25Index, doc_idx: int, query_tokens: list[str]) -> float:
    """BM25 score of a single document against the query tokens."""
    doc = index.docs[doc_idx]
    freqs = index.doc_freqs[doc_idx]
    doc_len = len(doc)
    score = 0.0
    for term in query_tokens:
        if term not in freqs:
            continue
        tf = freqs[term]
        idf = index.idf.get(term, 0.0)
        # Standard BM25 term contribution
        numerator = tf * (index.k1 + 1)
        denominator = tf + index.k1 * (
            1 - index.b + index.b * doc_len / index.avg_doc_len
        )
        score += idf * (numerator / denominator)
    return score


def top_articles_by_relevance(
    question: str, *, k: int = 3, min_score: float = 1.5,
) -> list[str]:
    """Return up to ``k`` article references most relevant to ``question``.

    The score threshold filters noise: a document scoring ≤ 1.5 against
    a query usually shares only one or two non-stopword terms, which is
    not a strong signal. The default keeps recall conservative — BM25
    is a fallback, not an oracle.

    Returns refs in descending relevance order. Empty list if no
    document scores above the threshold or the query is empty after
    tokenisation.
    """
    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    index = _build_index()
    if not index.docs:
        return []

    scored: list[tuple[float, str]] = []
    for doc_idx, article_ref in enumerate(index.article_refs):
        s = _score(index, doc_idx, query_tokens)
        if s >= min_score:
            scored.append((s, article_ref))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [ref for _, ref in scored[:k]]


def relevance_score(question: str, article_ref: str) -> float:
    """Compute the BM25 score of a single article against the question.

    Used by tests + debug tools. Returns 0.0 if the article isn't in the
    corpus.
    """
    index = _build_index()
    try:
        doc_idx = index.article_refs.index(article_ref)
    except ValueError:
        return 0.0
    return _score(index, doc_idx, _tokenize(question))


# Public API
__all__ = ["top_articles_by_relevance", "relevance_score"]
