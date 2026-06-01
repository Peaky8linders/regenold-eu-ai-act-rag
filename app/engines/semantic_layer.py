"""Round 69 — Semantic Layer: wires the structure-aware document tree.

This module is the "Semantic Layer" of the proposed Hybrid-RAG
architecture, adapted to this codebase's constraints.

WHAT THE PROPOSED ARCHITECTURE GOT RIGHT, AND HOW WE ADAPTED IT
---------------------------------------------------------------
The proposal calls for a structure-aware legal parser, a knowledge
graph, dense + sparse retrieval, and a middleware "Semantic Layer" that
coordinates them. The codebase already ships all of those — but with
two deliberate substitutions versus the proposal's literal tech list:

* External vector DBs (Pinecone / Milvus / Qdrant), Elasticsearch,
  Cohere Rerank and ``bge-large`` are NOT adopted. They require an
  external service or a GPU; the Railway deploy has neither. The
  codebase ships their Windows-friendly, dependency-free equivalents:
  in-memory BM25 (``app/data/kb_search.py``), a NumPy-SVD dense index
  (``app/engines/embeddings_index.py``), and a Neo4j graph.

* The proposal's structure-aware parser already exists as
  ``app/data/eu_ai_act_tree.py`` (a 1,426-node hierarchical tree,
  Round 32). The genuine gap this module closes: that tree was built
  but **never wired into the live request path** — zero imports across
  ``app/`` until Round 69.

TWO CAPABILITIES
----------------
* :func:`paragraph_extract` — Layer-A paragraph-level retrieval. Reuses
  the Round-34-tuned BM25 sentence scorer to pick the answer sentence,
  then WIDENS the unit from sentence to its enclosing *paragraph* node.
  The paragraph is the natural unit for multi-clause QA gold: tighter
  than the ~480-char full-article prose the engine emits, wider than a
  single sentence (Round 26 found single-sentence extraction drops gold
  tokens on broad question shapes). Env-gated ``REGENOLD_TREE_EXTRACT``.

* :func:`cross_reference_context` — the architecture's "Fragmentation
  Problem" fix. When a cited article's EUR-Lex prose references an Annex
  or sister Article (the proposal's canonical example: "an obligation in
  Article 16 references a technical folder layout in Annex IV"), the
  referenced node's text is surfaced so the generator sees both halves
  of the cross-reference. This feeds the Stage-2 generation context
  ONLY — it never enters the wire ``references`` list, so it cannot move
  the rubric's reference-correctness / -conciseness axes, and the
  deterministic davidath path (no Stage-2) is byte-unaffected.

Pure stdlib + the existing tree/corpus modules. No new pip deps, no I/O
at import time (the tree builds lazily on first call).
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterable

from app.data.eu_ai_act_tree import (
    _split_annex_items,
    _split_paragraphs_article,
    build_tree,
)

__all__ = [
    "is_tree_extract_enabled",
    "is_cross_ref_context_enabled",
    "paragraph_extract",
    "cross_reference_context",
]


# ──────────────────────────────────────────────────────────────────────────
# Env gates.
# ──────────────────────────────────────────────────────────────────────────


def _env_on(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def is_tree_extract_enabled() -> bool:
    """``REGENOLD_TREE_EXTRACT`` — paragraph-level extractive answers.

    Default OFF. This path CHANGES the deterministic davidath answer
    prose, so it ships behind an A/B gate (Round 69 methodology — a
    change that can move a rubric axis must be benchmark-proven before
    it defaults ON).
    """
    return _env_on("REGENOLD_TREE_EXTRACT", "0")


def is_cross_ref_context_enabled() -> bool:
    """``REGENOLD_CROSS_REF_CONTEXT`` — Fragmentation-fix context injection.

    Default ON. It is additive to the Stage-2 generation context only,
    never to the wire ``references`` list, so it cannot regress any
    davidath rubric axis (the deterministic bench never runs Stage-2).
    """
    return _env_on("REGENOLD_CROSS_REF_CONTEXT", "1")


# ──────────────────────────────────────────────────────────────────────────
# Reference → corpus-key / tree-slug normalisation.
#
# The corpus (``ARTICLE_FULL_TEXT``) and sentence index key on the short
# publication form ``Art. 13`` / ``Annex IV``. The tree keys article
# roots as ``art_13`` / ``annex_iv``. Engine citations arrive in internal
# form and may carry sub-points (``Art. 13(2)(a)``, ``Annex IV.2``) —
# we strip those to address the article/annex root.
# ──────────────────────────────────────────────────────────────────────────


_ART_REF_RE = re.compile(r"\bart(?:icle)?\.?\s*0*(\d{1,3})\b", re.IGNORECASE)
_ANNEX_REF_RE = re.compile(r"\bannex\s+([IVX]{1,5})\b", re.IGNORECASE)


def _corpus_ref_for(ref: str) -> str | None:
    """Map a ref (with optional sub-points) to the corpus short key.

    ``"Art. 13(2)(a)"`` → ``"Art. 13"``; ``"Annex IV.2"`` → ``"Annex IV"``.
    Returns ``None`` for an unrecognised shape.
    """
    if not ref:
        return None
    m = _ART_REF_RE.search(ref)
    if m:
        return f"Art. {int(m.group(1))}"
    m = _ANNEX_REF_RE.search(ref)
    if m:
        return f"Annex {m.group(1).upper()}"
    return None


def _slug_for(ref: str) -> str | None:
    """Map a ref to a tree article-root slug (``art_13`` / ``annex_iv``)."""
    if not ref:
        return None
    m = _ART_REF_RE.search(ref)
    if m:
        return f"art_{int(m.group(1))}"
    m = _ANNEX_REF_RE.search(ref)
    if m:
        return f"annex_{m.group(1).lower()}"
    return None


def _norm(text: str) -> str:
    """Collapse NBSP + whitespace, lower-case — for substring matching."""
    return " ".join((text or "").replace("\xa0", " ").split()).lower()


_WORD_RE = re.compile(r"[a-z0-9]+")


def _word_set(text: str) -> set[str]:
    """Lower-cased word tokens — for locating a sentence's home block."""
    return set(_WORD_RE.findall((text or "").lower()))


_MAX_BLOCK_CHARS = 500
"""A paragraph block longer than this is not returned. The engine's
normalised QA prose runs ~480 chars (CLAUDE.md QA-conciseness analysis);
a paragraph must be tighter than that to be a conciseness win. An
over-long block defers to the engine prose rather than regressing the
length axis."""


# ──────────────────────────────────────────────────────────────────────────
# Capability 1 — paragraph-level extractive retrieval.
# ──────────────────────────────────────────────────────────────────────────


def paragraph_extract(question: str, article_ref: str) -> str | None:
    """Return the *paragraph* block containing the best-matching sentence.

    Strategy: reuse the Round-34-tuned BM25 sentence scorer
    (:func:`app.engines.sentence_index.select_answer_sentence` — with its
    confidence-ratio gate and length gate) to pick the answer sentence,
    then WIDEN the unit from the sentence to its enclosing paragraph
    block (paragraph preamble + its sub-points, as split by the
    structure-aware tree parser). The paragraph is the architecture's
    Layer-A granularity: multi-clause-complete (Round 26 found
    single-sentence extraction drops gold tokens on broad question
    shapes) yet tighter than the ~480-char full article.

    Returns ``None`` when:

    * the article/annex ref is unrecognised or absent from the corpus;
    * ``select_answer_sentence`` finds no confident sentence;
    * the sentence cannot be located within a single paragraph block;
    * the enclosing paragraph is not actually shorter than the full
      article body (single-block article — no conciseness gain).

    Pure-deterministic, never raises.
    """
    if not question or not article_ref:
        return None
    corpus_ref = _corpus_ref_for(article_ref)
    if corpus_ref is None:
        return None

    try:
        from app.data.eu_ai_act_corpus import (  # noqa: PLC0415
            ARTICLE_FULL_TEXT,
        )
        from app.engines.sentence_index import (  # noqa: PLC0415
            select_answer_sentence,
        )
    except Exception:  # noqa: BLE001 — never let an import fault 500 the route
        return None

    body = ARTICLE_FULL_TEXT.get(corpus_ref)
    if not body or not body.strip():
        return None

    try:
        sentence = select_answer_sentence(question, corpus_ref)
    except Exception:  # noqa: BLE001
        return None
    if not sentence or not sentence.strip():
        return None

    # Split the article/annex into paragraph blocks via the tree's
    # structure-aware parser.
    try:
        if corpus_ref.startswith("Annex "):
            blocks = [t.strip() for _, t in _split_annex_items(body) if t.strip()]
        else:
            blocks = [
                t.strip() for _, t in _split_paragraphs_article(body) if t.strip()
            ]
    except Exception:  # noqa: BLE001
        return None
    if len(blocks) < 2:
        # Single-block article — the "paragraph" is the whole article.
        return None

    # Locate the answer sentence's home paragraph by token overlap. The
    # sentence is a contiguous slice of one paragraph, so that paragraph
    # contains essentially all of the sentence's tokens while sibling
    # paragraphs do not. Token overlap is robust to the heading-prefix /
    # whitespace differences between the sentence splitter and the
    # paragraph splitter (a plain substring match is not).
    sent_tokens = _word_set(sentence)
    if len(sent_tokens) < 3:
        return None
    body_len = len(body.strip())
    best_block: str | None = None
    best_overlap = 0
    for block in blocks:
        overlap = len(_word_set(block) & sent_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_block = block
    # The home paragraph must contain all-but-one of the sentence's
    # tokens — anything less means the sentence straddles a boundary or
    # the split disagreed, and surfacing a partial block is unsafe.
    if best_block is None or best_overlap < len(sent_tokens) - 1:
        return None
    if len(best_block) >= body_len:
        return None
    if len(best_block) > _MAX_BLOCK_CHARS:
        # The paragraph is no tighter than the engine's own prose —
        # surfacing it would regress the conciseness axis. Defer.
        return None
    return best_block


# ──────────────────────────────────────────────────────────────────────────
# Capability 2 — cross-reference context (the Fragmentation-Problem fix).
# ──────────────────────────────────────────────────────────────────────────


# In-text references to a sibling provision. EUR-Lex prose writes
# ``Annex IV`` / ``Article 11`` in full publication form.
_XREF_IN_TEXT_RE = re.compile(r"\b(?:Annex\s+[IVX]{1,5}|Article\s+\d{1,3})\b")

_CROSS_REF_SNIPPET_CHARS = 240
"""Each surfaced cross-referenced node is clipped to roughly one clause
— enough to show what the sibling provision is about without bloating
the generation context."""

_CROSS_REF_MAX_ITEMS = 3
"""Cap the number of cross-reference snippets — the Stage-2 context is a
budget, and 3 sibling provisions is the spec's 'minimal set' spirit."""


def _xref_to_slug(xref: str) -> str | None:
    """``"Annex IV"`` → ``"annex_iv"``; ``"Article 11"`` → ``"art_11"``."""
    m = re.match(r"Article\s+(\d{1,3})$", xref.strip())
    if m:
        return f"art_{int(m.group(1))}"
    m = re.match(r"Annex\s+([IVX]{1,5})$", xref.strip())
    if m:
        return f"annex_{m.group(1).lower()}"
    return None


def _clip_clause(text: str, limit: int) -> str:
    """Clip ``text`` to ~``limit`` chars on a sentence/clause boundary."""
    t = " ".join((text or "").replace("\xa0", " ").split())
    if len(t) <= limit:
        return t
    window = t[:limit]
    for sep in (". ", "; ", ", "):
        cut = window.rfind(sep)
        if cut >= limit // 2:
            return window[: cut + 1].strip()
    return window.rstrip() + "…"


def cross_reference_context(
    article_refs: Iterable[str],
    *,
    max_items: int = _CROSS_REF_MAX_ITEMS,
) -> list[str]:
    """Surface text of provisions cross-referenced by the cited articles.

    The architecture's "Fragmentation Problem": when an obligation in
    one article points at another provision (the proposal's example —
    Article 16 referencing the technical-documentation layout of
    Annex IV), naive chunking severs the link. This function walks each
    cited article's EUR-Lex prose, finds its in-text ``Annex N`` /
    ``Article N`` references, and returns short snippets of those
    referenced nodes.

    Returns a list of ``"Article N: <clause>"`` / ``"Annex N: <clause>"``
    strings, de-duplicated, capped at ``max_items``. Feeds the Stage-2
    generation context only — never the wire ``references`` list.

    Never raises; returns ``[]`` on any fault or when the env gate is off.
    """
    if not is_cross_ref_context_enabled():
        return []
    refs = [r for r in article_refs if r]
    if not refs:
        return []
    try:
        tree = build_tree()
    except Exception:  # noqa: BLE001
        return []

    # The set of slugs the engine already cited — never surface a
    # cross-reference back to a provision already in the references.
    cited_slugs = {s for s in (_slug_for(r) for r in refs) if s}

    out: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        slug = _slug_for(ref)
        if slug is None:
            continue
        node = tree.get(slug)
        if node is None or not node.text:
            continue
        for xref in _XREF_IN_TEXT_RE.findall(node.text):
            xslug = _xref_to_slug(xref)
            if xslug is None or xslug == slug:
                continue
            if xslug in cited_slugs or xslug in seen:
                continue
            target = tree.get(xslug)
            if target is None or not target.text:
                continue
            seen.add(xslug)
            label = target.article_number or xref
            out.append(
                f"{label}: {_clip_clause(target.text, _CROSS_REF_SNIPPET_CHARS)}"
            )
            if len(out) >= max_items:
                return out
    return out
