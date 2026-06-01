"""Sentence-level citation guard — Layer G (Zero-Hallucination Generation).

Implements the post-generation verification parser the
``EU_AI_Act_High_Precision_RAG_Architecture.pdf`` whitepaper specifies:

> Every assertion must map directly to its retrieved metadata tag
> (e.g. ``[Article 6(2), Annex III, Point 1(a)]``). A post-generation
> verification parser audits the text; any paragraph failing the
> citation-to-source integrity test is dropped before being surfaced to
> the user UI.

This is the **inverse** of the ``_drop_orphan_refs`` pass disabled in
Round 16 (which dropped REFERENCES without supporting SENTENCES). The
guard here drops SENTENCES without supporting REFERENCES — and only when
doing so leaves the answer with at least one sentence remaining.

## Design constraints

1. **Never drop the only sentence.** Round-16 finding: an over-broad
   answer is *better* than an empty one on the Regenold rubric. The
   guard always preserves a minimum of one sentence.
2. **Be lenient on lay-prose claims.** Most answers' first sentence is
   a topical preamble ("AI-Act high-risk systems must..."); requiring
   that sentence to NAME an article number would be over-strict. The
   guard checks for **lexical evidence overlap** with the surfaced
   article's KB stub, not for inline citation markers.
3. **Pure stdlib, sub-millisecond.** No new dependencies, no LLM
   invocation. Production hot-path safe.
4. **Reversible via env-gate.** ``REGENOLD_CITATION_GUARD=1`` opt-in;
   default OFF until benchmark evidence proves it's a rubric lift.

## Algorithm

For each sentence in the candidate answer:

1. Tokenise the sentence via the existing
   :func:`app.data.kb_search._tokenize` (drops stopwords + filler).
2. For each surfaced reference, fetch its KB stub text + ontology
   keywords; tokenise the same way.
3. The sentence is **supported** when its token set has at least
   :data:`_MIN_OVERLAP_TOKENS` tokens overlapping the union of the
   referenced articles' tokens.
4. Unsupported sentences are dropped, unless that would empty the
   answer. The minimum-one-sentence floor is enforced by sorting
   unsupported sentences by overlap descending and keeping the best
   one if all sentences are unsupported.

The guard is **purely subtractive** — it never adds, paraphrases, or
reorders sentences. The output is a subsequence of the input.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

_ENV_FLAG = "REGENOLD_CITATION_GUARD"
_MIN_OVERLAP_TOKENS = 1


def is_enabled() -> bool:
    """True iff the env-gate is set. Cheap to call."""
    val = os.getenv(_ENV_FLAG, "").strip().lower()
    return val in ("1", "true", "yes", "on")


# Round 31 — accept arbitrary sub-point depth on the leading numeric /
# Roman tag. The wire-contract regex in
# ``app/integrations/regenold/models.py::_ARTICLE_OUTPUT_RE`` permits
# ``Article 5.2.a.iii`` and equivalents, so the citation guard must
# collapse those to the parent article number too.
#
# TODO(R47): migrate to app.integrations.regenold.refs (centralised converter).
_USER_FACING_ARTICLE_RE = re.compile(r"^Article\s+(\d+)(?:\.[\w.]+)?$")
_USER_FACING_ANNEX_RE = re.compile(r"^Annex\s+([IVXLCDM]+)(?:\.[\w.]+)?$")


def _to_internal_ref(ref: str) -> str:
    """Convert a user-facing ref (``"Article 5"`` / ``"Annex IV.2"``) to
    the internal BM25 form (``"Art. 5"`` / ``"Annex IV"``).

    Returns ``ref`` unchanged when already in internal form or when the
    shape doesn't match. The BM25 index keys collapse sub-points to the
    parent article, so a user-facing ``Article 13.2`` maps to ``Art. 13``.
    Deep subpoints like ``Article 5.2.a.iii`` collapse to ``Art. 5``.
    """
    ref = (ref or "").strip()
    m = _USER_FACING_ARTICLE_RE.match(ref)
    if m:
        return f"Art. {m.group(1)}"
    m = _USER_FACING_ANNEX_RE.match(ref)
    if m:
        # BM25 keys Annex docs by the Roman numeral only.
        return f"Annex {m.group(1).upper()}"
    return ref


@lru_cache(maxsize=256)
def _reference_token_pool(article_ref: str) -> frozenset[str]:
    """Token set for a single article ref — union of every doc keyed by it.

    Pulls from the existing BM25 corpus (KB + ontology + corpus +
    definition rows) and unions their tokens. Cached per ref so the
    guard's hot path is essentially a set lookup.

    Accepts both internal form (``"Art. 5"``) and user-facing form
    (``"Article 5"`` / ``"Annex IV.2"``) — normalises internally.

    Returns the empty set when the ref is unknown — the caller treats
    that as "no support" and falls into the keep-best-one fallback.
    """
    # Lazy imports — citation_guard runs after retrieval, so the BM25
    # index is guaranteed already built; but we keep imports inside the
    # function so module import stays cheap.
    from app.data.kb_search import _build_index, _tokenize  # noqa: PLC0415

    internal = _to_internal_ref(article_ref)
    index = _build_index()
    tokens: set[str] = set()
    for doc_idx, ref in enumerate(index.article_refs):
        if ref != internal:
            continue
        tokens.update(index.docs[doc_idx])
    # Also fold in the article ref itself + canonical aliases so the
    # phrase "Article 5" in a sentence registers as overlap. Lowercase
    # to match the tokenizer convention.
    tokens.update(_tokenize(article_ref))
    tokens.update(_tokenize(internal))
    return frozenset(tokens)


def _reference_pool(refs: tuple[str, ...]) -> frozenset[str]:
    """Union token pool over a tuple of refs (small; not cached itself)."""
    if not refs:
        return frozenset()
    out: set[str] = set()
    for ref in refs:
        out.update(_reference_token_pool(ref))
    return frozenset(out)


# Sentence splitter — reuses the abbreviation-aware logic from the
# sentence-index module so legal abbreviations (``Art.``, ``Annex IV.``,
# ``e.g.``, ``i.e.``) don't trigger false splits. We don't re-implement
# here; lazy import keeps module-load cheap.


def _split_sentences(text: str) -> list[str]:
    """Split an answer string into sentences, preserving punctuation.

    Delegates to :func:`app.engines.sentence_index.split_legal_sentences`
    — the canonical regulatory-aware splitter (round-26 BM25 sentence
    index). Falls back to the whole text as a single sentence when no
    boundary is found.

    Re-importing here instead of duplicating the regex tree keeps the
    abbreviation list (``Art.``, ``Annex N.``, ``e.g.``, ``i.e.``,
    numbered list markers) in one place — earlier Round-31 first-cut
    used a naive ``(?<=[.!?])\\s+(?=[A-Z(])`` regex that rejected
    lowercase continuations like "Art. 5 ... art. 6 ..." and produced
    a single mega-sentence the guard couldn't split.
    """
    if not text or not text.strip():
        return []
    # Lazy import — keeps module-load cheap and avoids a circular path.
    from app.engines.sentence_index import split_legal_sentences  # noqa: PLC0415
    return split_legal_sentences(text)


def filter_unsupported_sentences(
    answer: str,
    refs: tuple[str, ...],
    *,
    min_overlap_tokens: int = _MIN_OVERLAP_TOKENS,
) -> str:
    """Return ``answer`` with unsupported sentences removed.

    Behaviour:

    * **No refs surfaced** → return ``answer`` unchanged. There's
      nothing to verify against; dropping sentences in that state
      would just empty the answer.
    * **Empty / whitespace answer** → return ``answer`` unchanged
      (the engine's own cap pass will deal with empties).
    * **Single sentence** → return ``answer`` unchanged regardless of
      support. The "never drop the only sentence" floor.
    * **Multiple sentences, all unsupported** → keep the
      best-overlap one, drop the rest. Answer never becomes empty.
    * **Multiple sentences, some supported** → keep the supported
      ones in document order, drop the rest.

    ``min_overlap_tokens`` controls how strict the guard is. The default
    (1) means a single shared content token is enough to keep a
    sentence — very lenient, optimised for "don't damage the rubric."

    Pure function. Never raises. Caller can rely on the return being a
    non-empty string when ``answer`` was a non-empty string.
    """
    if not answer or not answer.strip():
        return answer
    if not refs:
        return answer

    sentences = _split_sentences(answer)
    if len(sentences) <= 1:
        return answer

    # Token pool for the referenced articles.
    pool = _reference_pool(tuple(refs))
    if not pool:
        # No references resolved → can't verify → keep everything.
        return answer

    # Lazy import — tokeniser is the same one BM25 uses, keeps the
    # support test consistent with retrieval.
    from app.data.kb_search import _tokenize  # noqa: PLC0415

    # Score each sentence by overlap size. Sentences above the threshold
    # are "supported" and kept; sub-threshold sentences are unsupported.
    sentence_overlap: list[tuple[int, int]] = []  # (idx, overlap_count)
    supported_idx: list[int] = []
    for i, sent in enumerate(sentences):
        sent_tokens = set(_tokenize(sent))
        overlap = len(sent_tokens & pool)
        sentence_overlap.append((i, overlap))
        if overlap >= min_overlap_tokens:
            supported_idx.append(i)

    if not supported_idx:
        # All sentences fell below the bar — keep the best-overlap one
        # to honour the minimum-one-sentence floor.
        best = max(sentence_overlap, key=lambda t: t[1])
        return sentences[best[0]]

    # Preserve document order in the output. Re-join with single spaces;
    # the upstream answer normaliser handles its own punctuation tidy-up.
    kept = [sentences[i] for i in supported_idx]
    return " ".join(kept)


def maybe_apply_guard(answer: str, refs: tuple[str, ...]) -> str:
    """Env-gated convenience wrapper for the citation guard.

    When ``REGENOLD_CITATION_GUARD=1`` is set, drops unsupported
    sentences via :func:`filter_unsupported_sentences`. Otherwise
    returns the answer unchanged.

    The route layer calls THIS function rather than the raw filter so
    one env-flag lookup short-circuits the work when the guard is off.
    """
    if not is_enabled():
        return answer
    return filter_unsupported_sentences(answer, refs)


__all__ = [
    "filter_unsupported_sentences",
    "is_enabled",
    "maybe_apply_guard",
]
