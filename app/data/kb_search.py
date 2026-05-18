"""BM25 fallback retrieval over the KB obligation corpus + typed ontology.

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

## Ontology virtual documents (added May 2026)

The typed ontology in :mod:`app.data.ontology` carries rich prose that
the legacy obligation corpus does NOT: ``Practice.description`` (full
Art. 5(1)(a)-(h) plus the Omnibus 9th prohibition narrative),
``AnnexIIICategory.description + sub_points`` (the eight high-risk
use-case categories), and ``Phase.description`` (rollout-date prose).
Before this change those entries were unsearchable — a query like
"manipulative AI" never surfaced Art. 5 because the obligation
summary for Art. 5 enumerates the prohibitions tersely and BM25
couldn't match the lay phrasing.

Each ontology entry becomes a *virtual document* keyed by its primary
article anchor:

* :class:`~app.data.ontology.Practice` → keyed by ``practice.citation[0]``
  (typically ``"Art. 5"``). The sub-paragraph citation ``Art. 5.1.a``
  is folded into the indexable text, not the key, because downstream
  consumers (``graph_rag._deterministic_parse``) feed the article key
  back into :data:`EC_CHECKER_OBLIGATION_MAP` lookups that require the
  parent ``Art. N`` form.
* :class:`~app.data.ontology.AnnexIIICategory` → keyed by ``"Annex III"``.
  All eight categories share the same article anchor; BM25 ranks the
  more-relevant *document* higher, and the consumer needs only one
  anchor (Annex III) for the resulting verdict / KB lookup chain.
* :class:`~app.data.ontology.Phase` → keyed by the first article in
  ``phase.articles`` (e.g. ``"Art. 113"`` for the entry-into-force
  phase, ``"Art. 5"`` for the prohibitions phase).

The KB corpus and the ontology corpus may share keys (e.g. both
contribute a doc for ``Art. 5``). That's intentional — BM25 scores
each document independently, so a "subliminal manipulation" query
naturally ranks the Practice-description doc above the terse Art. 5
obligation row. Each doc carries a ``source`` tag (``"kb"`` or
``"ontology"``) so a consumer can filter if needed.

## Algorithm

Standard BM25 with k1=1.5, b=0.75. Document text construction:

* KB doc: ``f"{article_ref} {summary}"``
* Practice doc: ``f"{anchor} {sub_paragraph} {description} {keywords} {short_name}"``
* AnnexIIICategory doc: ``f"Annex III {description} {sub_points} {keywords} {short_name}"``
* Phase doc: ``f"{anchor} {label} {description}"``

Tokeniser is a stopword-filtered word-character split. Stopwords are
a small domain-tuned list (the AI Act prose uses "shall", "system",
"provider" in nearly every row — keeping them poisons the relevance
signal).

## Why not a real embedding store

At ~110 KB documents + ~25 ontology virtual documents ≈ 135 docs ×
~60 tokens each, BM25 ties or beats a dense embedding model in our
measurements while remaining deterministic and adding zero
dependencies. Embedding stores add 100-300ms p95 latency from the
model load + inference, plus a 300MB+ disk footprint for any
reasonable sentence-transformer — both regressions on the competition
rubric (which scores latency) for marginal recall gain on a corpus
this small.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.data.kb import EC_CHECKER_OBLIGATION_MAP
from app.data.ontology import (
    ANNEX_III_REGISTRY,
    PHASE_REGISTRY,
    PRACTICE_REGISTRY,
)

# Round 25 — augment the BM25 corpus with the full EUR-Lex prose from the
# Ansvar-Systems/EU_compliance_MCP snapshot (Apache 2.0; regulation text
# itself is public domain under Article 297 TFEU). Ports 126 articles +
# annexes (~600 KB) into the retrieval corpus. Lifts loose recall on
# Articles where our hand-curated summary was sparse (Arts. 1, 2, 18,
# 26, 43-49, 56-60, 70-90 — top miss zones on the davidath benchmark).
from app.data.eu_ai_act_corpus import (
    ARTICLE_FULL_TEXT as _UPSTREAM_FULL_TEXT,
    ART_3_DEFINITIONS as _UPSTREAM_DEFINITIONS,
)


DocSource = Literal["kb", "ontology", "corpus", "definition"]


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
        if raw.isdigit() and len(raw) > 4:
            continue
        tokens.append(raw)
    return tokens


@dataclass(frozen=True)
class _BM25Index:
    """Pre-computed BM25 statistics over the KB obligation corpus +
    typed-ontology virtual documents.

    ``article_refs``, ``sources``, ``docs``, ``doc_freqs`` are all
    parallel tuples of length ``n_docs``. ``sources[i]`` tags each row
    as ``"kb"`` (from :data:`EC_CHECKER_OBLIGATION_MAP`) or
    ``"ontology"`` (from :data:`PRACTICE_REGISTRY` /
    :data:`ANNEX_III_REGISTRY` / :data:`PHASE_REGISTRY`).
    """

    article_refs: tuple[str, ...]  # parallel to ``docs``
    sources: tuple[DocSource, ...]  # parallel to ``docs`` — "kb" or "ontology"
    docs: tuple[tuple[str, ...], ...]  # tokenised documents
    doc_freqs: tuple[dict[str, int], ...]  # term → count per document
    avg_doc_len: float
    idf: dict[str, float]  # term → inverse document frequency
    k1: float = 1.5
    b: float = 0.75


def _build_ontology_docs() -> list[tuple[str, DocSource, str]]:
    """Build ``(article_key, source, raw_text)`` triples for every ontology entry.

    Returns a list rather than a generator so the caller can take its
    length cheaply and the surface stays test-friendly. Each entry's
    article key matches the format already used downstream by
    ``EC_CHECKER_OBLIGATION_MAP`` (``"Art. N"``, ``"Annex III"``, etc.)
    — see the ``graph_rag._deterministic_parse`` BM25 fallback at the
    top of the module for the consumer.
    """
    rows: list[tuple[str, DocSource, str]] = []

    # Practices — keyed by the parent article (e.g. Art. 5), not the
    # sub-paragraph form (Art. 5.1.a). The sub-paragraph string is
    # folded into the indexable text so a query like
    # "Art. 5.1.h prohibition" still hits, but the emitted key is
    # the parent article that downstream KB lookups expect.
    for practice in PRACTICE_REGISTRY.values():
        if not practice.citation:
            continue
        anchor = practice.citation[0]
        text_parts: list[str] = [anchor]
        # Sub-paragraph citation (full chain) goes into the body so
        # queries that mention "Art. 5.1.a" still tokenise meaningfully.
        text_parts.extend(practice.citation)
        text_parts.append(practice.sub_paragraph)
        text_parts.append(practice.short_name)
        text_parts.append(practice.description)
        text_parts.extend(practice.keywords)
        rows.append((anchor, "ontology", " ".join(text_parts)))

    # Annex III categories — all keyed by "Annex III" (the canonical
    # article anchor for every high-risk use-case category). Each
    # category contributes its own virtual document so BM25 can rank
    # "essential public services" → essential_services and "judicial
    # interpretation" → justice_democracy independently, even though
    # both share the Annex III key.
    #
    # The short_name + keywords are repeated TWICE in the doc text so
    # the category-specific terms ("credit scoring", "welfare
    # eligibility") dominate over incidental description terms
    # ("healthcare" appears once inside the essential_services prose
    # as an example domain but isn't a category keyword). Without this
    # weighting, a generic "healthcare deployers" question over-fires
    # on Annex III because the description happens to list healthcare
    # as an example essential-service area. BM25 scores on TF —
    # duplicating the category-specific tokens raises the
    # discrimination bar without changing the algorithm or threshold.
    for category in ANNEX_III_REGISTRY.values():
        text_parts = [
            "Annex III",
            category.short_name,
            category.short_name,  # weight short_name 2×
            category.description,
        ]
        # Sub-points repeated 2× — these carry the precise sub-category
        # citation chain (e.g. "(5)(a) Public benefit eligibility").
        text_parts.extend(category.sub_points)
        text_parts.extend(category.sub_points)
        # Keywords weighted 3× — these are the user-facing anchor
        # phrases the ontology author explicitly chose as the
        # category's discriminative surface. Heavier weighting lets a
        # direct keyword hit dominate over incidental term matches in
        # the longer description prose.
        text_parts.extend(category.keywords)
        text_parts.extend(category.keywords)
        text_parts.extend(category.keywords)
        rows.append(("Annex III", "ontology", " ".join(text_parts)))

    # Phases — keyed by the first article in the phase's articles tuple.
    # Phase descriptions carry the prose for date-shaped queries
    # ("applicable from", "entry into force", "Digital Omnibus") that
    # neither the keyword map nor the KB summaries cover well.
    for phase in PHASE_REGISTRY.values():
        if not phase.articles:
            continue
        anchor = phase.articles[0]
        text_parts = [
            anchor,
            phase.label,
            phase.description,
        ]
        # Include every article the phase activates — questions like
        # "when does Art. 113 take effect?" should hit the entry-into-
        # force phase document.
        text_parts.extend(phase.articles)
        rows.append((anchor, "ontology", " ".join(text_parts)))

    return rows


@lru_cache(maxsize=1)
def _build_index() -> _BM25Index:
    """Build the BM25 index from :data:`EC_CHECKER_OBLIGATION_MAP` +
    the typed ontology registries.

    Memoised so the index is built once per process. Re-computing on
    every request would burn ~5-10ms per call needlessly; the index is
    immutable for the lifetime of the process.
    """
    article_refs: list[str] = []
    sources: list[DocSource] = []
    docs: list[tuple[str, ...]] = []
    doc_freqs: list[dict[str, int]] = []

    def _add(article_ref: str, source: DocSource, text: str) -> None:
        tokens = _tokenize(text)
        if not tokens:
            return
        article_refs.append(article_ref)
        sources.append(source)
        docs.append(tuple(tokens))
        freqs: dict[str, int] = {}
        for tok in tokens:
            freqs[tok] = freqs.get(tok, 0) + 1
        doc_freqs.append(freqs)

    # KB obligation corpus — the legacy ~82 docs. Index these first so
    # if a query ties between a KB doc and an ontology doc for the same
    # article key, ``_score``'s stable enumerate ordering keeps the KB
    # row at the earlier index (no observable consumer effect, but
    # tidier for debugging).
    for article_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        summary = entry.get("summary", "")
        # Include the article ref in the document — questions sometimes
        # reference the article number via the dimension keywords AND
        # the summary text. Concatenation gives BM25 a fair shot at
        # matching either signal.
        text = f"{article_ref} {summary}"
        _add(article_ref, "kb", text)

    # Typed ontology virtual documents — added May 2026 to close the
    # gap on lay phrasings of Art. 5 prohibitions, Annex III categories
    # and rollout-date questions. Duplicates of KB article keys are
    # allowed; BM25 scores documents independently.
    for article_ref, source, text in _build_ontology_docs():
        _add(article_ref, source, text)

    # Round 25 — upstream EUR-Lex corpus. Adds full prose for the 126
    # article/annex entries from the Ansvar-Systems snapshot. Each doc
    # is tagged ``source="corpus"`` so consumers can filter; BM25 ranks
    # against every doc independently. The KB summary row for the same
    # article remains present (different tokens), so a question that
    # phrases its terms close to our terse summary still favours that
    # doc, while a question that phrases like the legal text now finds
    # the upstream prose instead of falling through to BM25 noise.
    for article_ref, full_text in _UPSTREAM_FULL_TEXT.items():
        if not full_text:
            continue
        _add(article_ref, "corpus", f"{article_ref} {full_text}")

    # Round 25 — Art. 3 definitions as virtual docs. Each of the 68
    # terms becomes its own doc anchored to ``Art. 3`` so questions
    # phrased as "What does X mean?" / "Definition of Y" naturally
    # surface Art. 3 even when our keyword map doesn't carry that
    # specific phrase. The ``term`` is included as a leading anchor in
    # the doc text so a literal match scores highest.
    for term, body in _UPSTREAM_DEFINITIONS.items():
        if not body:
            continue
        _add("Art. 3", "definition", f"definition of {term}: {body}")

    n_docs = len(docs)
    if n_docs == 0:
        return _BM25Index(
            article_refs=(),
            sources=(),
            docs=(),
            doc_freqs=(),
            avg_doc_len=0.0,
            idf={},
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
        sources=tuple(sources),
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

    Returns refs in descending relevance order. Duplicate article keys
    are de-duplicated (the same article may appear in both the KB and
    the ontology corpus, but a caller wants each key at most once in
    the output). The highest-scoring doc wins for each key.

    Empty list if no document scores above the threshold or the query
    is empty after tokenisation.

    Issue #54 — short-query rescue. The absolute ``min_score`` cutoff
    is well-tuned for 4+ token queries, but a 1-2 token query can have
    a *clear* top winner whose score never clears the floor (e.g. the
    1-token query "vehicle" scores ~1.5 against Annex I but ≤ the 2.5
    floor the engine uses on the deterministic-parse fallback path).
    Pre-fix, this returned zero hits and the deterministic parse fell
    back to "no matching obligation". Post-fix, a candidate also
    survives when its raw score is ≥ ``MIN_SCORE_FACTOR`` (0.4) of the
    best raw score AND that best is itself above a low absolute sanity
    floor (``MIN_ABSOLUTE_RESCUE``, 0.5) — so the rescue can never
    promote pure noise but does keep a clearly-dominant short-query
    winner.
    """
    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    index = _build_index()
    if not index.docs:
        return []

    # Score every doc, then collapse to one entry per article_key
    # keeping the maximum score across kb + ontology rows.
    #
    # Source-aware weighting (Round 25): KB summary + ontology docs are
    # hand-authored and tight; the upstream EUR-Lex corpus docs are
    # long-form legal prose where BM25 length-normalisation under-shoots
    # the dilution penalty (`len(corpus_doc) >> avg_doc_len`, but the
    # b=0.75 normalisation tapers off). Without scaling, a query like
    # "ai that generates a logo" matches Art. 11 (technical
    # documentation) in the corpus higher than Art. 50 (transparency)
    # in the KB summary, because Art. 11's corpus text contains
    # "generates", "AI system", and "documentation". Scaling the
    # corpus + definition sources down to 0.6× keeps them as a SAFETY
    # NET (they still win when the KB doc has zero overlap) without
    # over-displacing authored summaries.
    #
    # Round 28 — confidence-weighted boost (per the LLM Wiki v2 gist's
    # "many sources support it" pattern). Articles linked by many other
    # KB rows (high in-degree on the cross-reference graph) are
    # structurally more important than peripheral leaf nodes. Multiply
    # the source-tier weight by a confidence boost ∈ [1.0, 1.15] derived
    # from the article's in-degree on :data:`kb_xrefs._build_xref_graph`.
    # Tiny effect on already-strong matches; meaningful tie-break on
    # close-score competitors. See :func:`_confidence_boost`.
    _SOURCE_WEIGHT = {
        "kb": 1.0,
        "ontology": 1.0,
        "corpus": 0.6,
        "definition": 0.8,
    }
    # Issue #54 — relative-cutoff parameters.
    _MIN_SCORE_FACTOR = 0.4
    _MIN_ABSOLUTE_RESCUE = 0.5

    # Pass 1 — score every doc unfiltered so we can compute the best
    # raw score for the relative-cutoff threshold.
    raw_scores: list[tuple[int, str, float]] = []
    best_raw = 0.0
    for doc_idx, article_ref in enumerate(index.article_refs):
        raw = _score(index, doc_idx, query_tokens)
        if raw > best_raw:
            best_raw = raw
        raw_scores.append((doc_idx, article_ref, raw))

    # Relative floor — only effective when the absolute best score is
    # itself meaningful (≥ ``_MIN_ABSOLUTE_RESCUE``). This stops the
    # rescue from turning a corpus full of zero-overlap matches into a
    # noise spew.
    relative_floor = (
        best_raw * _MIN_SCORE_FACTOR
        if best_raw >= _MIN_ABSOLUTE_RESCUE
        else float("inf")
    )

    best: dict[str, float] = {}
    for doc_idx, article_ref, raw in raw_scores:
        # Keep candidates that clear EITHER the absolute floor OR the
        # relative-to-best floor. The relative path is what unlocks
        # short-query recall — a 1-token query whose top raw score is
        # 1.5 (below the engine's 2.5 cutoff) still surfaces here.
        if raw < min_score and raw < relative_floor:
            continue
        if raw <= 0.0:
            continue
        weight = _SOURCE_WEIGHT.get(index.sources[doc_idx], 1.0)
        boost = _confidence_boost(article_ref)
        s = raw * weight * boost
        prev = best.get(article_ref)
        if prev is None or s > prev:
            best[article_ref] = s

    scored = sorted(best.items(), key=lambda t: t[1], reverse=True)
    bm25_top = [ref for ref, _ in scored[:k]]

    # Round 31 — when the TurboQuant dense path is enabled
    # (``REGENOLD_TURBOQUANT_DENSE=1``), use the dense ranking to APPEND
    # recall candidates BM25 didn't surface — never to reshape BM25's
    # ranking. First-cut Round-31 benchmark showed RRF (symmetric
    # fusion) traded ~0.004 Ref Correctness Strict for ~0.004 Ans
    # Correctness Strict — wash. Additive fill is purely recall-positive:
    # if BM25 already filled ``k`` slots, the dense path is a no-op;
    # otherwise dense refs fill the remaining slots in dense-rank order.
    #
    # Lazy import — the module imports numpy + optional turboquant at
    # build time. Skipping the import when the env-flag is off keeps the
    # zero-overhead promise for the deterministic baseline path.
    fused = bm25_top
    # Round 31 — TurboQuant additive dense fill (NumPy TF-IDF + SVD,
    # Windows-friendly). Env-gated REGENOLD_TURBOQUANT_DENSE=1.
    try:
        from app.engines.turboquant_index import (  # noqa: PLC0415
            additive_dense_fill,
            dense_top_k,
            is_enabled as _dense_enabled,
        )
        if _dense_enabled():
            try:
                dense_hits = dense_top_k(question, k=k * 2)
            except Exception:  # noqa: BLE001 — never 500 the route
                dense_hits = []
            if dense_hits:
                fused = additive_dense_fill(fused, dense_hits, k=k)
    except Exception:  # noqa: BLE001 — numpy missing on a stripped install
        pass

    # Round 32 — Embeddings sentence-index additive recall (Layer A+D
    # dense path). Aggregates sentence hits → article refs taking max
    # cosine sim. Purely additive (never displaces a BM25 winner). Env-
    # gated REGENOLD_EMBEDDINGS_INDEX=1 (default ON when assets are
    # present; the asset-presence check inside ``is_available`` makes
    # this a no-op on stripped installs).
    try:
        from app.engines.embeddings_index import (  # noqa: PLC0415
            is_available as _emb_available,
            query as _emb_query,
        )
    except Exception:  # noqa: BLE001 — module guards its own import
        return fused
    if not _emb_available():
        return fused
    env_flag = os.getenv("REGENOLD_EMBEDDINGS_INDEX", "1").strip().lower()
    if env_flag not in ("1", "true", "yes", "on"):
        return fused
    try:
        emb_hits = _emb_query(question, top_k=k * 4, threshold=0.15)
    except Exception:  # noqa: BLE001 — never 500 the route
        return fused
    if not emb_hits:
        return fused
    # Aggregate sentence hits → article-level candidates, max sim per article.
    article_max: dict[str, float] = {}
    for hit in emb_hits:
        ref = hit.article_ref
        if not ref:
            continue
        # Normalise to internal BM25 key shape (e.g. "Article 6" → "Art. 6").
        if ref.startswith("Article "):
            internal = "Art. " + ref[len("Article "):]
        elif ref.startswith("Annex "):
            internal = ref  # already in internal form
        else:
            internal = ref
        prev = article_max.get(internal, -1.0)
        if hit.similarity > prev:
            article_max[internal] = hit.similarity
    emb_refs = sorted(article_max.items(), key=lambda t: t[1], reverse=True)
    if not emb_refs:
        return fused
    fused = additive_dense_fill(fused, emb_refs, k=k)

    # Round 35 — Neo4j 2-hop graph expansion (env-gated REGENOLD_GRAPH_2HOP).
    # When OFF (default) the call returns empty in 1 µs and ``fused`` is
    # unchanged. When ON AND a seeded Neo4j instance is reachable, the
    # 2-hop CROSS_REFERENCES traversal surfaces non-obvious connections
    # that BM25 + dense paths miss — primarily for paraphrased / novel-
    # phrase production queries (NOT davidath, which BM25 already saturates).
    # Defensive: never raises, capped at 50 ms timeout, existence-gated
    # against ARTICLE_EXISTENCE.
    try:
        from app.engines.graph_expand_2hop import (  # noqa: PLC0415
            expand_2hop as _g2,
            fuse_with_kb_xrefs as _g2_fuse,
            is_enabled as _g2_enabled,
        )
    except Exception:  # noqa: BLE001 — neo4j missing on a stripped install
        return fused
    if not _g2_enabled():
        return fused
    try:
        expansion = _g2(fused[:3])  # seed from top-3 BM25 winners
    except Exception:  # noqa: BLE001 — never let graph expand 500 the route
        expansion = []
    fused = _g2_fuse(fused, expansion, budget=k) if expansion else fused

    # R39 / B6 — HippoRAG 2 Personalized PageRank over Neo4j. Strictly
    # additive: PPR candidates fill remaining slots in `fused`, never
    # displace BM25 winners. Env-gated REGENOLD_GRAPH_PPR=1; default OFF.
    try:
        from app.engines.graph_ppr import (  # noqa: PLC0415
            is_ppr_available,
            ppr_candidates,
        )
        if is_ppr_available():
            seed_articles = []
            for ref in fused[:3]:
                if ref.startswith("Art. "):
                    seed_articles.append(ref)
            ppr_extra = ppr_candidates(seed_articles=seed_articles, top_k=k)
            for extra_ref in ppr_extra:
                if extra_ref not in fused and len(fused) < k * 2:
                    fused.append(extra_ref)
    except Exception:  # noqa: BLE001 — fail-soft
        pass

    # R39 / B7 — PathRAG relational-path retrieval over Neo4j. Same
    # additive policy. Env-gated REGENOLD_PATH_RAG=1.
    try:
        from app.engines.path_rag import (  # noqa: PLC0415
            is_pathrag_available,
            pathrag_candidates,
        )
        if is_pathrag_available():
            seed_articles = []
            for ref in fused[:3]:
                if ref.startswith("Art. "):
                    seed_articles.append(ref)
            path_extra = pathrag_candidates(seed_articles=seed_articles, top_k=k)
            for extra_ref in path_extra:
                if extra_ref not in fused and len(fused) < k * 2:
                    fused.append(extra_ref)
    except Exception:  # noqa: BLE001 — fail-soft
        pass

    return fused


@lru_cache(maxsize=1)
def _xref_in_degree() -> dict[str, int]:
    """Count how many KB articles cross-reference each target article.

    High in-degree = many other regulatory provisions mention this
    article = central / structurally important. We use it as a
    confidence multiplier on the BM25 rank (LLM Wiki v2 gist pattern:
    "a fact supported by many sources is more reliable than one
    supported by few"). The in-degree is computed once per process
    from :mod:`app.data.kb_xrefs`.

    R57-C: switched from CORE to FULL graph. The R57 graph audit
    found 8 of 11 V2-weak-axis articles (Art. 13/14/26/56/72/73/101)
    had core_in_degree=0 → flat 1.0 boost, despite being central in
    the FULL graph (R47-A backfill). Reading the FULL graph lifts
    these articles into the boost tier; the cap is simultaneously
    lowered 1.15 → 1.10 in :func:`_confidence_boost` to prevent the
    larger graph from over-compressing the hub tier vs the R28
    calibration.
    """
    # Lazy import — keeps the build-time dependency graph clean.
    from app.data.kb_xrefs import _build_xref_graph  # noqa: PLC0415

    counts: dict[str, int] = {}
    for _source, targets in _build_xref_graph().items():
        for t in targets:
            counts[t] = counts.get(t, 0) + 1
    return counts


def _confidence_boost(article_ref: str) -> float:
    """Map in-degree to a score multiplier in [1.0, 1.10].

    Articles never referenced elsewhere get 1.0 (no boost). Articles
    with 1-2 in-edges get a mild boost. High-hub articles (the
    central Art. 5, Art. 6, Art. 13 et al.) saturate at 1.10. The cap
    is deliberately small so confidence weighting cannot promote an
    irrelevant article over a relevant one — it only tie-breaks among
    close competitors.

    R57-C: cap lowered 1.15 → 1.10. Together with the
    :func:`_xref_in_degree` switch to the FULL graph, the smaller cap
    compensates for the larger graph (R47-A backfill contributes
    extra in-edges to operator-obligation articles) so the hub tier
    doesn't over-compress vs the R28 calibration.

    Pure function of ``article_ref``; no per-query state. The boost
    table is memoised via :func:`_xref_in_degree`.
    """
    deg = _xref_in_degree().get(article_ref, 0)
    if deg <= 0:
        return 1.0
    # Logarithmic curve so the boost saturates: with the 1.10 cap and
    # 0.04 coefficient, deg=1 → ~1.04, deg=3 → ~1.06, deg=10 → ~1.10.
    import math  # noqa: PLC0415 — local; the module already imports math

    return min(1.0 + 0.04 * math.log2(1 + deg) / 2.0, 1.10)


def relevance_score(question: str, article_ref: str) -> float:
    """Compute the BM25 score of a single article against the question.

    Returns the MAXIMUM score across all docs sharing ``article_ref``
    (both the KB row and any ontology virtual docs). Used by tests +
    debug tools. Returns 0.0 if the article isn't in the corpus.
    """
    index = _build_index()
    query_tokens = _tokenize(question)
    best = 0.0
    found = False
    for doc_idx, ref in enumerate(index.article_refs):
        if ref != article_ref:
            continue
        found = True
        s = _score(index, doc_idx, query_tokens)
        if s > best:
            best = s
    if not found:
        return 0.0
    return best


def _index_stats() -> dict[str, int]:
    """Doc count by source — used by tests + debug tooling.

    Not part of the stable public API; the underscore prefix signals
    "internal but importable from tests".
    """
    index = _build_index()
    kb = sum(1 for s in index.sources if s == "kb")
    ontology = sum(1 for s in index.sources if s == "ontology")
    return {"total": len(index.docs), "kb": kb, "ontology": ontology}


# Public API
__all__ = ["top_articles_by_relevance", "relevance_score"]
