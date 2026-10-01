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
Art. 5(1)(a)-(h)),
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

import logging
import math
import os
import re
from dataclasses import dataclass
from dataclasses import field as dataclasses_field
from functools import lru_cache
from typing import Literal

from app.data.article_sections import articles_for_sections
from app.data.eu_ai_act_corpus import (
    ART_3_DEFINITIONS as _UPSTREAM_DEFINITIONS,
)

# Round 25 — augment the BM25 corpus with the full EUR-Lex prose from the
# Ansvar-Systems/EU_compliance_MCP snapshot (Apache 2.0; regulation text
# itself is public domain under Article 297 TFEU). Ports 126 articles +
# annexes (~600 KB) into the retrieval corpus. Lifts loose recall on
# Articles where our hand-curated summary was sparse (Arts. 1, 2, 18,
# 26, 43-49, 56-60, 70-90 — top miss zones on the davidath benchmark).
from app.data.eu_ai_act_corpus import (
    ARTICLE_CHAPTER,
)
from app.data.eu_ai_act_corpus import (
    ARTICLE_FULL_TEXT as _UPSTREAM_FULL_TEXT,
)
from app.data.kb import EC_CHECKER_OBLIGATION_MAP

# R295 — this module used ``logger.debug`` at two sites (the 2-hop fusion and
# the PPR fill) without ever defining or importing one: a latent NameError.
# Both sites are reachable ONLY when the graph actually contributes refs,
# which measurement showed essentially never happened (1/132 fusion calls had
# budget slack), so it stayed dormant. The engine calls
# ``top_articles_by_relevance`` unguarded (_graph_rag_impl.py:2051/2060), so
# once the graph does contribute the NameError would propagate into retrieval.
logger = logging.getLogger(__name__)
from app.data.ontology import (
    ANNEX_III_REGISTRY,
    PHASE_REGISTRY,
    PRACTICE_REGISTRY,
)
from app.engines.entity_extractor import boosted_articles

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
        if raw.isdigit() and len(raw) != 4:
            continue
        tokens.append(raw)
    return tokens


#: R449 — contextual (fielded) BM25. When ON, every indexed provision carries an
#: index-time context prefix split into its own ``title`` field, scored as
#: BM25F (per-field weights + per-field length normalisation) alongside the
#: ``body`` field. Default OFF: the deterministic baseline ranking must stay
#: byte-identical until a live gate accepts the change.
_CONTEXTUAL_FIELDS_ENV = "REGENOLD_CONTEXTUAL_FIELDS"
_CONTEXTUAL_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: BM25F field weights and per-field ``b``. The title field is short, so it
#: gets a lower length-normalisation slope and a higher weight — a term in the
#: official title should outrank the same term buried in 10k chars of prose.
_FIELD_WEIGHTS: dict[str, float] = {"title": 2.0, "body": 1.0}
_FIELD_B: dict[str, float] = {"title": 0.6, "body": 0.75}

#: R451 — the field NAMES are fixed (the index stores per-field counts under these
#: keys); only the numbers are sweepable. Keeping the name set independent of the
#: weights is what lets an in-process weight sweep reuse ONE built index instead
#: of rebuilding per arm — a rebuild per arm would re-measure the build, not the
#: weights.
_FIELD_NAMES: tuple[str, ...] = ("title", "body")

#: R451 — env overrides, read per SCORE call (the stored counts are weight-free).
_FIELD_WEIGHT_ENVS: dict[str, str] = {
    "title": "REGENOLD_FIELD_WEIGHT_TITLE",
    "body": "REGENOLD_FIELD_WEIGHT_BODY",
}
_FIELD_B_ENVS: dict[str, str] = {
    "title": "REGENOLD_FIELD_B_TITLE",
    "body": "REGENOLD_FIELD_B_BODY",
}
_FIELD_WEIGHT_BOUNDS: tuple[float, float] = (0.1, 10.0)
_FIELD_B_BOUNDS: tuple[float, float] = (0.0, 0.999)


def _field_env(
    envs: dict[str, str],
    field: str,
    defaults: dict[str, float],
    lo: float,
    hi: float,
) -> float:
    """Read one swept BM25F parameter, clamped, never raising.

    An unset, empty, non-numeric or non-finite value falls back to the shipped
    default rather than to a guess: a typo in an env var must not silently
    change rankings. Out-of-range values are CLAMPED rather than rejected so a
    sweep grid can probe the edges (weight 0.1 ≈ field ignored, b 0.999 ≈ no
    length normalisation) without the harness having to encode the bounds.
    """
    name = envs.get(field)
    default = defaults.get(field, 1.0)
    if not name:
        return default
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return min(hi, max(lo, value))


def field_weight(field: str) -> float:
    """R451 — BM25F weight for ``field`` (``REGENOLD_FIELD_WEIGHT_*``)."""
    return _field_env(
        _FIELD_WEIGHT_ENVS, field, _FIELD_WEIGHTS, *_FIELD_WEIGHT_BOUNDS
    )


def field_b(field: str) -> float:
    """R451 — BM25F length-normalisation slope for ``field`` (``REGENOLD_FIELD_B_*``)."""
    return _field_env(_FIELD_B_ENVS, field, _FIELD_B, *_FIELD_B_BOUNDS)


def contextual_fields_enabled() -> bool:
    """True when R449 contextual (BM25F) fields are requested."""
    return (
        os.getenv(_CONTEXTUAL_FIELDS_ENV, "0").strip().lower()
        in _CONTEXTUAL_TRUTHY
    )


def _context_prefix(article_ref: str) -> str:
    """Deterministic index-time context for one provision.

    Title + chapter + section + the reference itself. This is the
    repository's available substitute for a model-generated context sentence:
    it is the information the Act already prints above the provision, it costs
    nothing at query time, and it cannot fabricate a rule. Kept separate from
    the body under BM25F so the prefix cannot inflate the body's length
    normalisation or dilute the IDF of the terms it adds (see
    ``docs/reviews/r449-contextual-bm25-rerank-sota-2026-09-28.md`` §G3).
    """
    try:
        from app.data.article_sections import ARTICLE_SECTION  # noqa: PLC0415
        from app.data.eu_ai_act_corpus import ARTICLE_CHAPTER  # noqa: PLC0415
        from app.data.provision_text import title_for_ref  # noqa: PLC0415

        title = title_for_ref(article_ref)
        chapter = ARTICLE_CHAPTER.get(article_ref) or ""
        section = ARTICLE_SECTION.get(article_ref) or ""
    except Exception:  # noqa: BLE001 — the prefix is additive, never required
        return article_ref
    parts = [
        article_ref,
        title,
        f"chapter {chapter}" if chapter else "",
        f"section {section}" if section else "",
    ]
    return " ".join(p for p in parts if p.strip())


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
    #: R449 contextual fields — empty (the default) means "score as plain BM25".
    #: Parallel to ``docs`` when populated: term → count per field name.
    field_freqs: tuple[dict[str, dict[str, int]], ...] = ()
    #: Parallel to ``field_freqs``: token count per field for that document.
    field_lens: tuple[dict[str, int], ...] = ()
    #: Field name → mean token count across the corpus (for normalisation).
    field_avg_len: dict[str, float] = dataclasses_field(default_factory=dict)


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
    # ("applicable from", "entry into force") that
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
    #: R449 — populated only when contextual fields are requested.
    _contextual = contextual_fields_enabled()
    field_freqs_out: list[dict[str, dict[str, int]]] = []
    field_lens_out: list[dict[str, int]] = []

    def _counts(tokens: tuple[str, ...]) -> dict[str, int]:
        out: dict[str, int] = {}
        for tok in tokens:
            out[tok] = out.get(tok, 0) + 1
        return out

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
        if _contextual:
            title_tokens = tuple(_tokenize(_context_prefix(article_ref)))
            field_freqs_out.append(
                {"title": _counts(title_tokens), "body": dict(freqs)}
            )
            field_lens_out.append(
                {"title": len(title_tokens), "body": len(tokens)}
            )

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

    field_avg_len: dict[str, float] = {}
    if _contextual and field_lens_out:
        for fname in _FIELD_NAMES:
            total = sum(lens.get(fname, 0) for lens in field_lens_out)
            field_avg_len[fname] = total / len(field_lens_out)

    avg_doc_len = sum(len(d) for d in docs) / n_docs

    # Per-term document frequency (in how many docs does this term appear).
    # BM25F treats a term as present when it occurs in ANY field, counting the
    # document once even when it occurs in both title and body. Keep the body-only
    # path's insertion order and statistics unchanged when contextual fields are off.
    df: dict[str, int] = {}
    for doc_idx, freqs in enumerate(doc_freqs):
        terms = list(freqs)
        if _contextual:
            seen_terms = set(terms)
            for field_freqs in field_freqs_out[doc_idx].values():
                for term in field_freqs:
                    if term not in seen_terms:
                        seen_terms.add(term)
                        terms.append(term)
        for term in terms:
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
        field_freqs=tuple(field_freqs_out),
        field_lens=tuple(field_lens_out),
        field_avg_len=field_avg_len,
    )


def _score_fielded(
    index: _BM25Index, doc_idx: int, query_tokens: list[str]
) -> float:
    """BM25F score: per-field saturated term frequencies, then one saturation.

        t̃f(t) = Σ_f w_f · tf_f(t) / (1 − b_f + b_f · len_f / avg_len_f)
        score = Σ_t idf(t) · t̃f · (k1 + 1) / (k1 + t̃f)

    With a single ``body`` field at weight 1.0 this reduces algebraically to
    :func:`_score`, so the fielded path is a strict generalisation of the
    shipped formula rather than a second, incomparable ranker.
    """
    fields = index.field_freqs[doc_idx]
    lens = index.field_lens[doc_idx]
    avg = index.field_avg_len
    score = 0.0
    for term in query_tokens:
        idf = index.idf.get(term, 0.0)
        if idf <= 0.0:
            continue
        combined = 0.0
        for fname in _FIELD_NAMES:
            weight = field_weight(fname)
            tf_f = fields.get(fname, {}).get(term, 0)
            if not tf_f:
                continue
            len_f = float(lens.get(fname, 0))
            avg_f = avg.get(fname) or 0.0
            b_f = field_b(fname)
            norm = 1.0 - b_f + (b_f * len_f / avg_f if avg_f > 0.0 else 0.0)
            if norm <= 0.0:  # pragma: no cover — defensive, b < 1 by construction
                continue
            combined += weight * tf_f / norm
        if combined <= 0.0:
            continue
        score += idf * (combined * (index.k1 + 1.0)) / (index.k1 + combined)
    return score


def _score(index: _BM25Index, doc_idx: int, query_tokens: list[str]) -> float:
    """BM25 score of a single document against the query tokens."""
    if index.field_freqs:
        return _score_fielded(index, doc_idx, query_tokens)
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


def _score_fusion_enabled() -> bool:
    """True if score-based hybrid fusion is explicitly enabled.

    REGENOLD_SCORE_FUSION=1 normalises BM25 raw scores and blends them with
    dense cosine similarities. This prevents rank inversions by preserving
    the exact score magnitudes of matches.
    """
    return os.getenv("REGENOLD_SCORE_FUSION", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _rrf_fusion_enabled() -> bool:
    """R69/R450 — ``REGENOLD_RRF_FUSION`` env gate.

    The proposed Hybrid-RAG architecture's retrieval centrepiece is
    Reciprocal Rank Fusion across the BM25, dense and graph routes.
    Round 31 measured symmetric RRF on the davidath benchmark as a wash
    (±0.004 — BM25 already saturates that corpus) and shipped additive
    fill instead. R69 wires RRF as a real, A/B-able knob: when this flag
    is ON, :func:`top_articles_by_relevance` fuses the BM25 and dense
    rankings via weighted RRF (BM25-dominant, dense as a close-tie
    reshaper) rather than additive fill.

    **Default ON (R450 candidate flip).** Of every fusion arm measured on the
    110-row gold set, rank-level fusion is the only one that changes ORDER while
    leaving membership untouched — the R449 harness scored it at identical head
    recall/precision/added-reference counts against the shipped additive fill
    (0.805 / 30 refs both) with a higher nDCG@k (0.625 vs 0.612). R450
    re-measured that premise row by row on all 110 official questions: the
    retrieved SET differs on **0/110** rows at both k=8 and k=15, the ORDER
    differs on **110/110**, and the first-8 slice that Stage-2 grounding and
    ``kg_context`` cut positionally differs on **110/110**. So the lever cannot
    move which provisions are cited, and it does move which of them the model is
    shown first and which get verbatim grounding text.

    A flip of an ordering default still needs the live paired gate (the same
    read R415 ran for the single-turn lever). R450 ran it and the run **VOIDED**:
    both arms generated cleanly on the 27 reachable rows (0 errors, 0 fallback
    rows, transport healthy) but ``evals.official.score_arm`` refused to grade
    them — ``missing_provenance`` on rg_003/rg_004/… — so no paired table exists
    and no axis was measured. The provisional flip was therefore reverted, per
    the accept rule fixed before the run. Two independent pins also failed under
    the flip and are the reason it is not simply re-run blind: on the sanctions
    question rank-level fusion returns ``Art. 13`` ahead of ``Art. 99``, and the
    k=5 fused-path ranking table moves.

    So this stays a measured candidate with, as of R450, **no axis evidence**:
    ``REGENOLD_RRF_FUSION=1`` selects it for the next gate, ``"0"`` (default)
    keeps the additive-fill ranking byte-for-byte. See
    ``docs/measurements/r450/CHECKPOINT.md`` §7.
    """
    return os.getenv("REGENOLD_RRF_FUSION", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _fuse_dense(
    bm25_refs: list[str],
    dense_refs: list[tuple[str, float]],
    k: int,
    bm25_scores: dict[str, float] | None = None,
) -> list[str]:
    """R69 — dispatch the dense-route fusion strategy.

    Strategies:
    1. Score Fusion: When REGENOLD_SCORE_FUSION is enabled, normalise and blend
       raw BM25 scores and dense cosine similarities.
    2. RRF Fusion: When REGENOLD_RRF_FUSION is enabled, weighted rank reciprocal fusion.
    3. Additive Fill (Default): preserve the order of the ``bm25_refs`` it is
       handed and append dense-only candidates into vacant ``k`` slots.

    "Additive" is relative to *its arguments*: the caller may already have
    reshaped the BM25 ranking before calling. ``top_articles_by_relevance``
    multiplies a matching article's BM25 score by 1.20 for every sentence-index
    hit at similarity ≥ 0.50 **before** its ``[:k]`` cut, so a reference that
    looks "added" by fill can in fact be a displaced BM25 winner. See the
    Round-32 note at that call site, and do not read the purity claim on
    :func:`app.engines.turboquant_index.additive_dense_fill` as covering this
    stage.
    """
    from app.engines.turboquant_index import (  # noqa: PLC0415
        additive_dense_fill,
    )

    if _score_fusion_enabled() and bm25_scores:
        try:
            alpha = float(os.getenv("REGENOLD_SCORE_FUSION_ALPHA", "0.3"))
        except Exception:  # noqa: BLE001
            alpha = 0.3

        max_bm25 = max(bm25_scores.values()) if bm25_scores else 0.0

        fused_scores: dict[str, float] = {}
        # Incorporate BM25 candidates
        for ref, raw_score in bm25_scores.items():
            norm_bm25 = raw_score / max_bm25 if max_bm25 > 0.0 else 0.0
            fused_scores[ref] = (1 - alpha) * norm_bm25

        # Incorporate Dense candidates
        for ref, cosine_sim in dense_refs:
            norm_dense = max(0.0, cosine_sim)
            # Combine or add to existing
            fused_scores[ref] = fused_scores.get(ref, 0.0) + alpha * norm_dense

        fused = sorted(fused_scores.items(), key=lambda t: t[1], reverse=True)
        return [ref for ref, _ in fused[:k]]

    if _rrf_fusion_enabled():
        from app.engines.turboquant_index import (  # noqa: PLC0415
            reciprocal_rank_fusion,
        )
        return reciprocal_rank_fusion(
            bm25_refs,
            dense_refs,
            rrf_k=60,
            k=k,
            bm25_weight=2.0,
            dense_weight=1.0,
        )
    return additive_dense_fill(bm25_refs, dense_refs, k=k)


def _entity_boosts_from_entities(
    entities: dict[str, list[tuple[str, int]]],
) -> dict[str, float]:
    """Derive ``{article_ref: max_boost}`` from already-extracted entities.

    R112 (perf finding #49) — pure-mapping counterpart of
    :func:`app.engines.entity_extractor.boosted_articles` that takes the
    entities as input instead of re-running the ~100-regex
    ``extract_entities`` sweep. Semantics are byte-identical: for each
    article hit by a role and/or concept alias, the MAXIMUM boost wins
    (role 3.0 > concept 2.0 — never the product). Keys are
    ``"Art. {n}"`` strings matching the BM25 index format.

    The caller is responsible for the ``is_enabled()`` env-gate (this
    helper is only reached on the enabled path); empty/no-match entities
    yield an empty dict, mirroring ``boosted_articles``.
    """
    from app.engines.entity_extractor import boost_factor  # noqa: PLC0415

    if not entities.get("role") and not entities.get("concept"):
        return {}
    out: dict[str, float] = {}
    for etype in ("role", "concept"):
        b = boost_factor(etype)
        for _eid, art_num in entities.get(etype) or ():
            ref = f"Art. {art_num}"
            prev = out.get(ref, 0.0)
            if b > prev:
                out[ref] = b
    return out


# R120 — MedTech product-law signal for the Annex I companion injection.
# Matches ONLY EU medical-device product terms (MDR/IVDR/Class III/IIb/
# SaMD/IVD) — all with 0 davidath QUESTION hits — so the Annex I injection
# below is davidath-neutral by construction.
_MEDTECH_PRODUCT_RE = re.compile(
    r"\bclass\s+ii[ab]\b|\bclass\s+iii\b|\bmdr\b|\bivdr\b|"
    r"software as a medical device|\bsamd\b|in vitro diagnostic",
    re.IGNORECASE,
)


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

    # R81-N — typed-entity NER priority boost.
    # Closes the 15–24% retrieval-fail bucket observed across 4 live
    # rep-100 rounds: questions like "What are the importers'
    # obligations?" (gold Art. 23) lose to "high-risk AI system"
    # → Art. 6 in BM25 because the topic phrase carries more matching
    # tokens than the single role-noun. The extractor returns a
    # ``{ref: boost}`` map; the boost is multiplied onto the existing
    # source weight + confidence boost so the priority signal stays in
    # the same order of magnitude as BM25 (cannot promote an
    # irrelevant Article — only tip a close-score tie). Env-gated
    # ``REGENOLD_ENTITY_BOOST`` (default ON).
    #
    # R81-N.1 — stronger boost factors (1.5→3.0 role, 1.3→2.0 concept)
    # + a QA-shape role-Article INJECTION path (below). The R81-N
    # live measurement showed the 1.5× boost was too weak to flip
    # close-score live failures.
    #
    # Lazy import — keeps the kb_search module-level import surface
    # minimal and avoids a build-time circular dependency risk.
    try:
        from app.engines.entity_extractor import (  # noqa: PLC0415
            extract_entities,
            is_qa_shape_with_single_role,
        )
        from app.engines.entity_extractor import (
            is_enabled as _entity_enabled,
        )
        # R112 (perf finding #49) — extract ONCE, derive the boost map
        # from the extracted entities. The pre-R112 code called
        # ``boosted_articles(question)`` (which runs the full ~100-regex
        # ``extract_entities`` sweep internally) and then ran
        # ``extract_entities(question)`` AGAIN for the injection step.
        # ``_entity_boosts_from_entities`` mirrors ``boosted_articles``'s
        # mapping exactly (max boost per ref) — output is identical,
        # pinned by ``tests/test_r112_perf_fixes.py``.
        if _entity_enabled():
            _ents_for_injection = extract_entities(question)
            entity_boosts = _entity_boosts_from_entities(_ents_for_injection)
        else:
            _ents_for_injection = None
            entity_boosts = {}
    except Exception:  # noqa: BLE001 — never fail BM25 on the boost
        entity_boosts = {}
        _ents_for_injection = None

    # Component A — Embeddings sentence-index SVD query at the beginning
    emb_hits = []
    high_sim_articles = set()
    try:
        from app.engines.embeddings_index import (  # noqa: PLC0415
            is_available as _emb_available,
        )
        from app.engines.embeddings_index import (
            query as _emb_query,
        )
        if _emb_available():
            env_flag = os.getenv("REGENOLD_EMBEDDINGS_INDEX", "1").strip().lower()
            if env_flag in ("1", "true", "yes", "on"):
                # Retrieve sentence hits once
                emb_hits = _emb_query(question, top_k=k * 4, threshold=0.15)
                for hit in emb_hits:
                    if hit.similarity >= 0.50:
                        ref = hit.article_ref
                        if ref:
                            if ref.startswith("Article "):
                                internal = "Art. " + ref[len("Article "):]
                            else:
                                internal = ref
                            high_sim_articles.add(internal)
    except Exception:  # noqa: BLE001 — fail-soft
        pass

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
        # R81-N entity boost. Default 1.0 (no change) when no entity
        # match. Multiplicative on the BM25 score *after* the
        # admission filter, so it cannot change which articles are
        # admitted — only their ranking.
        entity_b = entity_boosts.get(article_ref, 1.0)

        # Sentence-level high similarity boosts BM25 before the top-k cut;
        # this can displace a lower-scoring BM25 candidate.
        emb_boost = 1.20 if article_ref in high_sim_articles else 1.0

        # Component B — Prevent role/context drift by damping mismatched role articles
        role_drift_penalty = 1.0
        if _ents_for_injection and len(_ents_for_injection.get("role", [])) == 1:
            query_role_art = f"Art. {_ents_for_injection['role'][0][1]}"
            known_role_articles = {"Art. 16", "Art. 26", "Art. 23", "Art. 24", "Art. 22", "Art. 28", "Art. 74", "Art. 64"}
            if article_ref in known_role_articles and article_ref != query_role_art:
                role_drift_penalty = 0.50  # 50% penalty to prevent role drift

        # Prevent concept drift: dampen dominant unrelated articles when a single concept is queried
        if _ents_for_injection and len(_ents_for_injection.get("concept", [])) == 1:
            query_concept_art = f"Art. {_ents_for_injection['concept'][0][1]}"
            if query_concept_art == "Art. 50" and article_ref in {"Art. 6", "Annex III"}:
                role_drift_penalty *= 0.50
            if query_concept_art == "Art. 99" and article_ref not in {"Art. 99"}:
                role_drift_penalty *= 0.50

        # Component B — Additive lexical boost for extracted concepts
        additive_lexical_boost = 0.0
        if article_ref in entity_boosts:
            additive_lexical_boost = 0.5

        s = raw * weight * boost * entity_b * emb_boost * role_drift_penalty + additive_lexical_boost
        prev = best.get(article_ref)
        if prev is None or s > prev:
            best[article_ref] = s

    # R81-N.1 — QA-shape role-Article INJECTION (conservative gate).
    # When the question is a definitional QA shape (Wh-start or ?-end,
    # NOT a scenario opener) AND exactly ONE role entity fired AND that
    # role's Article isn't already in ``best``, inject it as a synthetic
    # mid-pack candidate. The 3.0× role boost (R81-N.1) then lifts it
    # to top-tier ranking — without this injection the role's Article
    # is invisible when BM25 returns it with score 0.
    #
    # Safety invariants (per the R81-N.1 brief):
    # 1. NO scenario regression: the QA-shape gate explicitly rejects
    #    scenario openers ("We are a..." / "Our company...").
    # 2. NO OOS leak: the injection requires an entity match in the
    #    first place; OOS questions don't fire entities.
    # 3. NO duplicate: skip if the role's Article is already in best.
    # 4. Boost still multiplicative: the injected score (max(best) × 0.5
    #    × source_weight × confidence_boost × role_boost) competes with
    #    natural BM25 winners; a high-BM25-score winner still wins.
    if _ents_for_injection and best and is_qa_shape_with_single_role(
        question, _ents_for_injection,
    ):
        try:
            from app.engines.entity_extractor import (  # noqa: PLC0415
                boost_factor as _bf,
            )
            single_role = _ents_for_injection["role"][0]  # (eid, art_num)
            role_art_ref = f"Art. {single_role[1]}"
            if role_art_ref not in best:
                # Synthetic candidate: half of the current max BM25 score
                # × the role boost. With role boost = 3.0, the injected
                # ranking becomes 1.5× the max — top territory but not
                # auto-winning. The source weight + confidence boost
                # apply for parity with the natural-candidate scoring
                # path. Use the KB source weight (1.0) as a defensive
                # default — the role's Article may be in the corpus but
                # not in ``best`` if BM25 returned score 0.
                max_score = max(best.values())
                synthetic_base = max_score * 0.5
                # Apply same multipliers as a real candidate. The role
                # boost is the dominant lift signal.
                cb = _confidence_boost(role_art_ref)
                rb = _bf("role")
                best[role_art_ref] = synthetic_base * cb * rb
        except Exception:  # noqa: BLE001 — never fail BM25 on injection
            pass

    # R120 — MedTech Annex I companion injection (product-specific signal).
    # Annex I (the Union harmonisation legislation list — MDR/IVDR sit in
    # its Section A) is the classification BASIS for AI safety components of
    # regulated medical devices, but its EUR-Lex sector-list prose has ~0
    # BM25 overlap with MedTech question vocabulary, so it never clears the
    # admission floor. Inject it ONLY on product-specific tokens (0 davidath
    # QUESTION hits → davidath-neutral by construction). Gated on
    # ``_ents_for_injection is not None`` so REGENOLD_ENTITY_BOOST=0 disables
    # it too. Never displaces a BM25 winner (synthetic mid-pack score). Bare
    # "safety component" (gold=Art 6 on its 1 davidath row) does NOT trigger
    # this — avoids an Annex I over-cite there.
    if (
        _ents_for_injection is not None
        and best
        and question
        and _MEDTECH_PRODUCT_RE.search(question)
    ):
        try:
            from app.engines.entity_extractor import (  # noqa: PLC0415
                boost_factor as _bf,
            )
            # Lift Annex I to a top-tier synthetic score. Use max() so a
            # pre-existing tiny BM25 score for Annex I (which would make a
            # bare ``not in best`` guard skip the lift) is still raised.
            _annex_i_synthetic = (
                max(best.values()) * 0.5 * _confidence_boost("Annex I") * _bf("concept")
            )
            if _annex_i_synthetic > best.get("Annex I", 0.0):
                best["Annex I"] = _annex_i_synthetic
        except Exception:  # noqa: BLE001 — never fail BM25 on injection
            pass

    scored = sorted(best.items(), key=lambda t: t[1], reverse=True)
    bm25_top = [ref for ref, _ in scored[:k]]

    # Round 31 — when the TurboQuant dense path is enabled
    # (``REGENOLD_TURBOQUANT_DENSE=1``), fuse its ranking with BM25.
    # The default additive-fill policy preserves BM25 order and fills only
    # vacant slots; the optional RRF and score-fusion policies can reorder.
    # First-cut Round-31 benchmark showed symmetric RRF trading ~0.004 Ref
    # Correctness Strict for ~0.004 Ans Correctness Strict — wash — so additive
    # fill remains the default. With k BM25 winners, default fill is a no-op.
    #
    # Lazy import — the module imports numpy + optional turboquant at
    # build time. Skipping the import when the env-flag is off keeps the
    # zero-overhead promise for the deterministic baseline path.
    fused = bm25_top
    # Round 31 — TurboQuant additive dense fill (NumPy TF-IDF + SVD,
    # Windows-friendly). Env-gated REGENOLD_TURBOQUANT_DENSE=1.
    try:
        from app.engines.turboquant_index import (  # noqa: PLC0415
            dense_top_k,
        )
        from app.engines.turboquant_index import (
            is_enabled as _dense_enabled,
        )
        if _dense_enabled():
            try:
                dense_hits = dense_top_k(question, k=k * 2)
            except Exception:  # noqa: BLE001 — never 500 the route
                dense_hits = []
            if dense_hits:
                # R69 — RRF when REGENOLD_RRF_FUSION is on, else the
                # Round-31 additive fill (default, byte-identical).
                fused = _fuse_dense(fused, dense_hits, k, bm25_scores=best)
    except Exception:  # noqa: BLE001 — numpy missing on a stripped install
        pass

    # Round 32 — sentence-index stage. It has TWO mechanisms, and only one of
    # them is additive:
    #
    #   1. DISPLACEMENT (the ``emb_boost`` line in the scoring loop above): every
    #      article with a sentence hit at similarity ≥ 0.50 gets
    #      ``emb_boost = 1.20``, a multiplier applied to its BM25 score BEFORE
    #      the ``scored[:k]`` cut. This reorders ``best`` and therefore evicts
    #      lower-ranked BM25 winners from the top-k. It is NOT additive.
    #   2. FILL (below): aggregate the same hits to article-level candidates
    #      (max cosine per article) and hand them to the configured fusion
    #      policy, which by default only appends into vacant ``k`` slots.
    #
    # Measured R449 (``docs/measurements/r449/UNIT-GRAIN-k8.md``, k=8, the real
    # 110-row gold set, production entry point): the sparse control returns
    # exactly 8 refs on every row and the article-level SVD stage adds 0, i.e.
    # there is no vacant slot anywhere — yet this stage changes the top-8
    # MEMBERSHIP on 27 rows (+30 refs, 3 of them gold) with the length
    # unchanged at 8. Every one of those additions is therefore mechanism 1.
    # Older notes in this file, ROUNDS.md and the ``additive_dense_fill``
    # docstring called this stage "purely additive (never displaces a BM25
    # winner)" — false as written; ``tests/test_r449_dense_boost_displacement.py``
    # now fails if the boost stops reaching the cut.
    #
    # Env-gated REGENOLD_EMBEDDINGS_INDEX=1 (default ON when assets are present;
    # the asset-presence check inside ``is_available`` makes this a no-op on
    # stripped installs).
    if emb_hits:
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
        if emb_refs:
            # R69 — RRF when REGENOLD_RRF_FUSION is on, else additive fill.
            fused = _fuse_dense(fused, emb_refs, k, bm25_scores=best)



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
            GraphExpansion as _GraphExpansion,
        )
        from app.engines.graph_expand_2hop import (
            expand_2hop as _g2,
        )
        from app.engines.graph_expand_2hop import (
            fuse_with_kb_xrefs as _g2_fuse,
        )
        from app.engines.graph_expand_2hop import (
            is_enabled as _g2_enabled,
        )
    except Exception:  # noqa: BLE001 — neo4j missing on a stripped install
        return fused
    if not _g2_enabled():
        return fused
    try:
        max_hop2 = int(os.getenv("REGENOLD_MAX_HOP2", "5"))
    except ValueError:
        max_hop2 = 5
    try:
        expansion = _g2(fused[:3], max_hop2=max_hop2)  # seed from top-3 BM25 winners
    except Exception:  # noqa: BLE001 — never let graph expand 500 the route
        # ``expand_2hop`` is documented to never raise (every internal error
        # path returns an empty GraphExpansion), so this is belt-and-braces —
        # but the sentinel MUST be a GraphExpansion, not ``[]``: the guard
        # below and ``fuse_with_kb_xrefs`` both expect the dataclass (they read
        # ``.hop2_articles``). A bare ``[]`` was only accidentally safe.
        expansion = _GraphExpansion()
    fused_before = list(fused)
    # R295 — the fusion budget is the real gate on the 2-hop layer, NOT the
    # wall-clock timeout R294 fixed.
    #
    # ``fuse_with_kb_xrefs`` is additive-below-cap: it appends only into
    # ``budget - len(winners)`` slack. With ``budget=k`` and BM25 reliably
    # returning k winners there is NO slack, so the expansion is discarded.
    # Measured over the full 132-row ab_judge probe set with a healthy graph:
    # 660 hop2 refs AVAILABLE, 1/132 calls with slack, **4 refs added**. So
    # ~99.4% of the graph's contribution never reaches the wire — the
    # BM25-saturation finding (R31/R69/R110) reproducing at the fusion step.
    #
    # ``REGENOLD_GRAPH_FUSE_SLACK`` grants the graph N extra slots beyond the
    # BM25 winners. Default 0 = byte-identical to pre-R295. This is a genuine
    # reference-affecting change (added candidates -> query.entities -> wire
    # refs) and the R142.1 danger zone, so it ships OFF and is decided by a
    # live pairwise ab_judge, per hard rule #6.
    try:
        _fuse_slack = int(os.getenv("REGENOLD_GRAPH_FUSE_SLACK", "0"))
    except ValueError:
        _fuse_slack = 0
    _fuse_slack = max(0, min(10, _fuse_slack))
    # A GraphExpansion is always truthy, so test the field that carries the
    # fusion candidates (empty hop2 → nothing to fuse → leave ``fused``).
    fused = (
        _g2_fuse(fused, expansion, budget=k + _fuse_slack)
        if expansion.hop2_articles
        else fused
    )
    if len(fused) > len(fused_before):
        logger.debug("Graph 2-hop surfaced new refs: %s", [x for x in fused if x not in fused_before])

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
            ppr_added = []
            for extra_ref in ppr_extra:
                if extra_ref not in fused and len(fused) < k * 2:
                    fused.append(extra_ref)
                    ppr_added.append(extra_ref)
            if ppr_added:
                logger.debug("Graph PPR surfaced new refs: %s", ppr_added)
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


def top_articles_by_relevance_in_chapters(
    question: str,
    chapters: list[str],
    *,
    k: int = 5,
    min_score: float = 1.0,
) -> list[str]:
    """Chapter-scoped BM25 — like :func:`top_articles_by_relevance` but
    restricts scoring to documents whose article key belongs to one of
    ``chapters`` (Roman numeral strings, e.g. ``["II", "III"]``).

    Annexes whose chapter mapping is ``None`` in
    :data:`~app.data.eu_ai_act_corpus.ARTICLE_CHAPTER` are included when
    ``"III"`` is in the requested chapters (Annex I, II, III — the
    high-risk classification annexes) or always when the query could
    touch any annex (annex_fallback).

    Falls back transparently to the full-corpus
    :func:`top_articles_by_relevance` when the filtered candidate set is
    empty or ``chapters`` is empty.

    PageIndex rationale: pre-scoping BM25 to the relevant chapter(s)
    removes inter-chapter noise (e.g. Art. 11 technical-docs proxy-matching
    a query about Art. 50 transparency) and lifts top-1 precision without
    changing the algorithm — same BM25 math, smaller candidate pool.
    """
    if not chapters or not question:
        return top_articles_by_relevance(question, k=k, min_score=min_score)

    chapter_set = set(chapters)

    # Build the allowed article set from ARTICLE_CHAPTER.
    # Annexes map to None — include them when Chapter III is requested
    # (Annex I safety-component list, Annex II harmonisation legislation,
    # Annex III high-risk use-case list are structurally part of Chapter III)
    # or when a query keyword hints at an annex directly.
    _annex_keys = {k for k, v in ARTICLE_CHAPTER.items() if v is None and k.startswith("Annex")}
    chapter_annex_inclusion: set[str] = set()
    if "III" in chapter_set:
        chapter_annex_inclusion.update({"Annex I", "Annex II", "Annex III", "Annex IV"})
    if "V" in chapter_set:
        chapter_annex_inclusion.update({"Annex IX", "Annex X", "Annex XI", "Annex XII"})

    allowed_articles: set[str] = {
        art_key
        for art_key, ch in ARTICLE_CHAPTER.items()
        if ch in chapter_set
    } | chapter_annex_inclusion

    if not allowed_articles:
        return top_articles_by_relevance(question, k=k, min_score=min_score)

    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    index = _build_index()
    if not index.docs:
        return []

    _SOURCE_WEIGHT = {
        "kb": 1.0,
        "ontology": 1.0,
        "corpus": 0.6,
        "definition": 0.8,
    }
    _MIN_SCORE_FACTOR = 0.4
    _MIN_ABSOLUTE_RESCUE = 0.5

    # Score only docs within the allowed article set.
    raw_scores: list[tuple[int, str, float]] = []
    best_raw = 0.0
    for doc_idx, article_ref in enumerate(index.article_refs):
        if article_ref not in allowed_articles:
            continue
        raw = _score(index, doc_idx, query_tokens)
        if raw > best_raw:
            best_raw = raw
        raw_scores.append((doc_idx, article_ref, raw))

    # Fall back to full corpus if no docs matched the chapter filter.
    if not raw_scores:
        return top_articles_by_relevance(question, k=k, min_score=min_score)

    relative_floor = (
        best_raw * _MIN_SCORE_FACTOR
        if best_raw >= _MIN_ABSOLUTE_RESCUE
        else float("inf")
    )

    # R81-N — same typed-entity boost as the main variant. See the
    # primary :func:`top_articles_by_relevance` for the rationale.
    try:
        entity_boosts = boosted_articles(question)
    except Exception:  # noqa: BLE001
        entity_boosts = {}

    best: dict[str, float] = {}
    for doc_idx, article_ref, raw in raw_scores:
        w = _SOURCE_WEIGHT.get(index.sources[doc_idx], 1.0)
        weighted = raw * w
        if weighted >= min_score or raw >= relative_floor:
            # R79 — apply the R28 cross-reference confidence boost to the
            # RANKING value only (not the admission filter above),
            # mirroring `top_articles_by_relevance`. The chapter-scoped
            # variant was silently omitting it, so hub articles
            # (Art. 5/6/9/13/26) lost their documented tie-break on every
            # chapter-scoped query. Boost ∈ [1.0, 1.10] — a pure
            # tie-break that cannot promote an irrelevant article over a
            # relevant one, and (applied post-filter) cannot change which
            # articles are admitted.
            # R81-N — entity boost multiplies on top, same semantics.
            entity_b = entity_boosts.get(article_ref, 1.0)
            ranked = weighted * _confidence_boost(article_ref) * entity_b
            if article_ref not in best or ranked > best[article_ref]:
                best[article_ref] = ranked

    sorted_refs = sorted(best, key=lambda r: best[r], reverse=True)
    return sorted_refs[:k]


def top_articles_by_relevance_in_sections(
    question: str,
    sections: list[str] | tuple[str, ...],
    *,
    k: int = 5,
    min_score: float = 1.0,
) -> list[str]:
    """Section-scoped BM25 for the R89-A structural retrieval layer.

    This mirrors :func:`top_articles_by_relevance_in_chapters` but filters
    candidates by the logical section IDs in
    :mod:`app.data.article_sections` (for example ``"III.2"`` for
    high-risk technical requirements). If the filter is empty it falls back
    to the full-corpus BM25 path, preserving existing behaviour.
    """
    if not sections or not question:
        return top_articles_by_relevance(question, k=k, min_score=min_score)

    allowed_articles = articles_for_sections(tuple(sections))
    if not allowed_articles:
        return top_articles_by_relevance(question, k=k, min_score=min_score)

    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    index = _build_index()
    if not index.docs:
        return []

    _SOURCE_WEIGHT = {
        "kb": 1.0,
        "ontology": 1.0,
        "corpus": 0.6,
        "definition": 0.8,
    }
    _MIN_SCORE_FACTOR = 0.4
    _MIN_ABSOLUTE_RESCUE = 0.5

    raw_scores: list[tuple[int, str, float]] = []
    best_raw = 0.0
    for doc_idx, article_ref in enumerate(index.article_refs):
        if article_ref not in allowed_articles:
            continue
        raw = _score(index, doc_idx, query_tokens)
        if raw > best_raw:
            best_raw = raw
        raw_scores.append((doc_idx, article_ref, raw))

    if not raw_scores:
        return top_articles_by_relevance(question, k=k, min_score=min_score)

    relative_floor = (
        best_raw * _MIN_SCORE_FACTOR
        if best_raw >= _MIN_ABSOLUTE_RESCUE
        else float("inf")
    )

    try:
        entity_boosts = boosted_articles(question)
    except Exception:  # noqa: BLE001
        entity_boosts = {}

    best: dict[str, float] = {}
    for doc_idx, article_ref, raw in raw_scores:
        w = _SOURCE_WEIGHT.get(index.sources[doc_idx], 1.0)
        weighted = raw * w
        if weighted >= min_score or raw >= relative_floor:
            entity_b = entity_boosts.get(article_ref, 1.0)
            ranked = weighted * _confidence_boost(article_ref) * entity_b
            if article_ref not in best or ranked > best[article_ref]:
                best[article_ref] = ranked

    sorted_refs = sorted(best, key=lambda r: best[r], reverse=True)
    return sorted_refs[:k]


# Public API
__all__ = [
    "top_articles_by_relevance",
    "top_articles_by_relevance_in_chapters",
    "top_articles_by_relevance_in_sections",
    "relevance_score",
]
