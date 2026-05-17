"""Implicit cross-reference graph extracted from KB obligation summaries.

Many obligation rows in :data:`app.data.kb.EC_CHECKER_OBLIGATION_MAP`
already name other articles in their prose:

    Art. 16: "Provider obligations for high-risk AI: ensure system meets
    Section-2 requirements, … operate a quality-management system
    (Art. 17), keep documentation (Arts. 11 + 18), keep logs (Art. 19),
    undertake conformity assessment (Art. 43), draw up declaration of
    conformity (Art. 47), affix CE marking (Art. 48), register in EU
    database (Art. 49), take corrective actions (Art. 20), and
    demonstrate compliance to authorities (Art. 21)."

That's ~10 cross-references in one summary that the retrieval layer
never surfaces. When a user asks "what does Art. 16 require?", the
system answers with Art. 16's summary — but doesn't pull the linked
obligations (Art. 11, Art. 17, Art. 18, …) into the citation set,
even though they're exactly the obligations the deployer needs to
know about.

This module regex-extracts those mentions once at import time, building
a deterministic adjacency map. The engine consults the map when
expanding the citation set for any matched entity, adding 1-degree
cross-refs with reduced weight so they appear in the references list
but don't dominate the answer text.

## Cost

* Build: one regex pass over ~110 summary strings — sub-5ms at import.
* Query: O(1) dict lookup per entity.
* Latency overhead: negligible, well within the 5.45ms p95 budget.

## What this is NOT

This is NOT a real ontological graph (no typed edges, no semantic
relationship labels). Every cross-reference is just "mentioned by" —
the route layer interprets the relationship from context. For typed
relationships (Practice → Article, ActorRole → obligations), see
:mod:`app.data.ontology`.
"""
from __future__ import annotations

import re
from functools import lru_cache

from app.data.article_existence import ARTICLE_EXISTENCE, ARTICLE_NUMBER_RE_BODY
from app.data.kb import EC_CHECKER_OBLIGATION_MAP


# Article and annex citation patterns. Matches the short ``Art.`` form
# (and the no-period ``Art`` form when followed by digits), and the
# Roman-numeral Annex form. Sub-paragraph chains like ``(1)(a)`` are
# stripped — we record the bare article number / annex roman as the
# cross-reference target.
#
# R41 / Digital Omnibus introduces letter-suffix articles (``4a``,
# ``60a``, ``75a``-``75e``). The number-token body is sourced from the
# canonical ``ARTICLE_NUMBER_RE_BODY`` constant so the regex tracks the
# regulation surface automatically as future amendments add new
# letter-suffix articles.
_ART_RE = re.compile(
    r"\bArt\.?\s*(" + ARTICLE_NUMBER_RE_BODY + r")\b",
    re.IGNORECASE,
)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLC]+)\b", re.IGNORECASE)


# ── Manually-curated cross-reference edges ─────────────────────────────
#
# The regex extractor above only catches Art./Annex mentions that appear
# verbatim in a summary string. Two important classes of edge get missed:
#
# 1. Annex ↔ Article edges where the Annex doesn't appear in any
#    obligation summary (e.g. Annex IV doesn't have its own row in
#    EC_CHECKER_OBLIGATION_MAP, so the regex never sees its source side).
# 2. Reverse edges that the author of the summary didn't write
#    explicitly. The regex graph is directed; we need both directions
#    to answer "what references Annex IV?".
#
# Each tuple is ``(source, target, reason)``. The ``reason`` is surfaced
# by :func:`cross_refs_with_reason` so answer composition can cite the
# semantic relationship rather than just both refs side by side.
#
# Endpoints are validated at import time by ``MANUAL_XREFS_LINTED``
# below — a typo here fails the module load, not the user query.
MANUAL_XREFS: tuple[tuple[str, str, str], ...] = (
    (
        "Annex IV",
        "Art. 11",
        "Annex IV enumerates the contents of the technical documentation "
        "required by Art. 11",
    ),
    (
        "Art. 11",
        "Annex IV",
        "Reverse: Art. 11 documentation contents are specified in Annex IV",
    ),
    (
        "Annex V",
        "Art. 47",
        "Annex V specifies the contents of the EU declaration of conformity "
        "required by Art. 47",
    ),
    ("Art. 47", "Annex V", "Reverse"),
    (
        "Annex VI",
        "Art. 43",
        "Annex VI is the conformity assessment procedure based on internal "
        "control referenced in Art. 43",
    ),
    (
        "Annex VII",
        "Art. 43",
        "Annex VII is the conformity assessment based on QMS + technical doc "
        "assessment referenced in Art. 43",
    ),
    ("Art. 43", "Annex VI", "Reverse"),
    ("Art. 43", "Annex VII", "Reverse"),
    (
        "Annex III",
        "Art. 6",
        "Annex III enumerates the high-risk use cases referenced in Art. 6(2)",
    ),
    ("Art. 6", "Annex III", "Reverse"),
    (
        "Annex I",
        "Art. 6",
        "Annex I lists Union harmonisation legislation whose safety "
        "components are high-risk under Art. 6(1)",
    ),
    ("Art. 6", "Annex I", "Reverse"),
    (
        "Annex II",
        "Art. 5",
        "Annex II is the list of offences relevant to the Art. 5(1)(h) RBI "
        "law-enforcement carve-out",
    ),
    ("Art. 5", "Annex II", "Reverse"),
    (
        "Annex XI",
        "Art. 53",
        "Annex XI is the technical documentation for GPAI providers required "
        "by Art. 53(1)(a)",
    ),
    (
        "Annex XII",
        "Art. 53",
        "Annex XII is the information required for downstream providers "
        "under Art. 53(1)(b)",
    ),
    (
        "Annex XIII",
        "Art. 51",
        "Annex XIII is the criteria for designating GPAI models with systemic "
        "risk under Art. 51",
    ),
    ("Art. 53", "Annex XI", "Reverse"),
    ("Art. 53", "Annex XII", "Reverse"),
    ("Art. 51", "Annex XIII", "Reverse"),
    # ─── R41 / Digital Omnibus edges (COREPER 9247/26, 13 May 2026) ────────
    # Art. 5(1)(ba) non-consensual intimate material ↔ Art. 99(1) penalty
    # link per recital 6c — recorded at bare-article granularity since the
    # existence catalog tracks articles, not sub-points (lint floor).
    (
        "Art. 5",
        "Art. 99",
        "Art. 5(1)(ba) non-consensual intimate material breach is fined "
        "under Art. 99(1) prohibited-practice bracket (up to EUR 35M / 7%) "
        "per Digital Omnibus recital 6c",
    ),
    (
        "Art. 99",
        "Art. 5",
        "Reverse: Art. 99(1) penalty regime references Art. 5 prohibited "
        "practices including the new (ba) non-consensual intimate material "
        "and (bb) AI-CSAM prohibitions",
    ),
    # Art. 6(1a) safety-component carve-out ↔ Art. 3(14) revised
    # safety-component definition (intended-purpose-as-safety-function gate)
    (
        "Art. 6",
        "Art. 3",
        "Art. 6(1a) safety-component non-qualification cross-references "
        "the revised Art. 3(14) 'safety component' definition (intended "
        "purpose to prevent or mitigate risks to health and safety)",
    ),
    # Art. 4a bias-data legal basis ↔ Art. 10 data-governance regime
    (
        "Art. 4a",
        "Art. 10",
        "Art. 4a establishes the legal basis for processing special-"
        "category personal data for bias detection / correction; "
        "Art. 10(2)(f)+(g) define the data-quality + bias-examination "
        "obligations the bias-data is used to satisfy",
    ),
    (
        "Art. 10",
        "Art. 4a",
        "Reverse: Art. 10(2)(f)+(g) bias-examination references Art. 4a "
        "for the legal basis to process special-category data",
    ),
    # Art. 75 ↔ Art. 75a–75e governance chain (AI Office investigatory +
    # enforcement powers, procedural safeguards, limitation period)
    (
        "Art. 75",
        "Art. 75a",
        "Art. 75 exclusive AI Office competence → Art. 75a information-"
        "request powers",
    ),
    (
        "Art. 75",
        "Art. 75b",
        "Art. 75 exclusive AI Office competence → Art. 75b on-site "
        "inspection + commitment powers",
    ),
    (
        "Art. 75",
        "Art. 75c",
        "Art. 75 exclusive AI Office competence → Art. 75c fines + "
        "periodic penalty payments (5% of average daily income/turnover "
        "per day cap)",
    ),
    (
        "Art. 75",
        "Art. 75d",
        "Art. 75 exclusive AI Office competence → Art. 75d procedural "
        "safeguards (right to be heard, file access, CJEU review)",
    ),
    (
        "Art. 75",
        "Art. 75e",
        "Art. 75 exclusive AI Office competence → Art. 75e 5-year "
        "limitation period for fines + periodic penalties",
    ),
    (
        "Art. 75a",
        "Art. 75d",
        "Art. 75a information-request power triggers Art. 75d procedural "
        "safeguards (right to be heard, self-incrimination protections)",
    ),
    (
        "Art. 75b",
        "Art. 75d",
        "Art. 75b on-site inspection power triggers Art. 75d procedural "
        "safeguards (right to counsel, sealing of premises)",
    ),
    (
        "Art. 75c",
        "Art. 75d",
        "Art. 75c fine + periodic-penalty power triggers Art. 75d "
        "procedural safeguards before adverse decision",
    ),
    (
        "Art. 75c",
        "Art. 75e",
        "Art. 75c fines are subject to the Art. 75e 5-year limitation "
        "period",
    ),
    # Art. 60a Section B Annex I sectoral real-world testing ↔ Art. 60
    # (Section A RWT) ↔ Art. 76(1) MSA-to-NCA reference rule
    (
        "Art. 60a",
        "Art. 60",
        "Art. 60a Section B Annex I real-world-testing framework runs in "
        "parallel to Art. 60 Section A real-world-testing under sectoral "
        "Member-State frameworks",
    ),
    (
        "Art. 60",
        "Art. 60a",
        "Reverse: Art. 60 real-world testing extension to Section A Annex I "
        "complemented by Art. 60a Section B Annex I framework",
    ),
    (
        "Art. 60a",
        "Art. 76",
        "Art. 60a — references to the market-surveillance authority in "
        "Art. 76(1) are construed as references to the relevant Section B "
        "Annex I national competent authority where testing is conducted "
        "under Art. 60a",
    ),
    (
        "Art. 76",
        "Art. 60a",
        "Reverse: Art. 76(1) MSA scope rule cross-references Art. 60a "
        "Section B Annex I sectoral testing",
    ),
)


def _lint_manual_xrefs() -> tuple[tuple[str, str, str], ...]:
    """Validate every endpoint in :data:`MANUAL_XREFS` at import time.

    A bad edge (typo in ``Art. 5OO`` or ``Annex XIV``) raises an
    ``AssertionError`` here rather than silently propagating into a
    user-facing citation set. This is the same fail-fast posture as the
    consistency lint in ``tests/test_kb_consistency.py``, run a layer
    earlier so the module simply will not load on a bad edit.

    Returns the (immutable) validated edge list. Stored as
    :data:`MANUAL_XREFS_LINTED` so consumers can prove the lint ran.
    """
    for source, target, reason in MANUAL_XREFS:
        assert source in ARTICLE_EXISTENCE, (
            f"MANUAL_XREFS source {source!r} not in ARTICLE_EXISTENCE "
            f"(edge: {source!r} → {target!r})"
        )
        assert target in ARTICLE_EXISTENCE, (
            f"MANUAL_XREFS target {target!r} not in ARTICLE_EXISTENCE "
            f"(edge: {source!r} → {target!r})"
        )
        assert source != target, (
            f"MANUAL_XREFS self-edge {source!r} → {target!r}"
        )
        assert reason, (
            f"MANUAL_XREFS edge {source!r} → {target!r} has empty reason"
        )
    return MANUAL_XREFS


#: The lint-validated copy of :data:`MANUAL_XREFS`. Import-time evaluation
#: means a bad edge prevents the module from loading at all.
MANUAL_XREFS_LINTED: tuple[tuple[str, str, str], ...] = _lint_manual_xrefs()


@lru_cache(maxsize=1)
def _build_regex_xref_graph() -> dict[str, tuple[str, ...]]:
    """Build the regex-extracted cross-reference adjacency map.

    Walks every obligation summary, extracts Art. N / Annex X mentions,
    validates each against :data:`ARTICLE_EXISTENCE`, and stores the
    deduplicated cross-reference list keyed by the source article.

    Self-references are dropped: an obligation that mentions its own
    article in its summary doesn't need a self-edge in the graph.

    This is the legacy graph — the public :func:`_build_xref_graph` and
    :func:`cross_refs` overlay :data:`MANUAL_XREFS` on top of it.
    """
    graph: dict[str, list[str]] = {}

    for source_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        summary = entry.get("summary", "")
        if not summary:
            continue

        targets: list[str] = []
        seen: set[str] = {source_ref}

        for match in _ART_RE.finditer(summary):
            # R41 letter-suffix tokens (``75a``, ``4a``) should normalise
            # to lowercase so the catalog form ``Art. 75a`` matches even
            # when prose typed ``Art. 75A``. Pure-digit forms unaffected.
            num = match.group(1).lower()
            target = f"Art. {num}"
            # Validate existence so we don't surface a hallucinated
            # cross-ref (e.g. a typo in the summary like Art. 200).
            if target in ARTICLE_EXISTENCE and target not in seen:
                seen.add(target)
                targets.append(target)

        for match in _ANNEX_RE.finditer(summary):
            roman = match.group(1).upper()
            target = f"Annex {roman}"
            if target in ARTICLE_EXISTENCE and target not in seen:
                seen.add(target)
                targets.append(target)

        if targets:
            graph[source_ref] = targets

    return {k: tuple(v) for k, v in graph.items()}


@lru_cache(maxsize=1)
def _build_xref_graph() -> dict[str, tuple[str, ...]]:
    """Build the merged regex + manual cross-reference graph.

    The merge preserves regex-extracted order (round-1 stable behaviour)
    and appends only the manually-curated edges that aren't already
    present from the regex pass. This keeps :func:`cross_refs` strictly
    additive against the legacy graph: an answer that previously cited
    Art. 11 → (whatever the regex found) still cites those refs, plus
    the new Art. 11 → Annex IV manual edge appended at the tail.
    """
    regex_graph = _build_regex_xref_graph()
    graph: dict[str, list[str]] = {k: list(v) for k, v in regex_graph.items()}

    for source, target, _reason in MANUAL_XREFS:
        if source == target:
            continue
        bucket = graph.setdefault(source, [])
        if target not in bucket:
            bucket.append(target)

    return {k: tuple(v) for k, v in graph.items()}


@lru_cache(maxsize=1)
def _build_xref_reason_index() -> dict[tuple[str, str], str]:
    """Index ``(source, target) → reason`` for manual edges.

    Regex-extracted edges have no semantic reason (the surface text just
    mentioned the target), so they fall back to a generic
    ``"mentioned by"`` label in :func:`cross_refs_with_reason`. Manual
    edges win on collision — if a manual edge restates a regex one with
    a richer reason, the manual reason is what gets surfaced.
    """
    return {(source, target): reason for source, target, reason in MANUAL_XREFS}


def cross_refs(article_ref: str, *, limit: int = 5) -> tuple[str, ...]:
    """Return up to ``limit`` cross-referenced articles for ``article_ref``.

    Returns an empty tuple if ``article_ref`` has no recorded
    cross-references OR isn't in :data:`EC_CHECKER_OBLIGATION_MAP`.

    ``limit`` caps the surfaced set so a hub article (like Art. 16 with
    ~10 cross-refs) doesn't dominate the citation list. Default 5 keeps
    the cap consistent with the route's ``MAX_REFERENCES``.
    """
    graph = _build_xref_graph()
    return graph.get(article_ref, ())[:limit]


def cross_refs_with_reason(
    article_ref: str, *, limit: int = 5
) -> tuple[tuple[str, str], ...]:
    """Return up to ``limit`` ``(target, reason)`` pairs for ``article_ref``.

    Wraps :func:`cross_refs` with the semantic reason from the manual
    edge table. Regex-extracted edges (where there is no curated reason)
    fall back to a generic ``"mentioned in obligation summary"`` label,
    which is still useful: the route layer can decide to suppress those
    when answering "why does X link to Y?" but keep the manual ones.

    The pair order matches the order returned by :func:`cross_refs`, so a
    caller can swap the two functions without re-sorting.
    """
    targets = cross_refs(article_ref, limit=limit)
    reasons = _build_xref_reason_index()
    out: list[tuple[str, str]] = []
    for target in targets:
        reason = reasons.get(
            (article_ref, target),
            "mentioned in obligation summary",
        )
        out.append((target, reason))
    return tuple(out)


def all_edges() -> tuple[tuple[str, str], ...]:
    """Return every (source, target) cross-reference edge.

    Useful for tests + debugging — lets a consistency check verify that
    every edge endpoint passes ``article_existence`` validation.
    """
    graph = _build_xref_graph()
    edges: list[tuple[str, str]] = []
    for source, targets in graph.items():
        for target in targets:
            edges.append((source, target))
    return tuple(edges)


__all__ = [
    "cross_refs",
    "cross_refs_with_reason",
    "all_edges",
    "MANUAL_XREFS",
    "MANUAL_XREFS_LINTED",
]
