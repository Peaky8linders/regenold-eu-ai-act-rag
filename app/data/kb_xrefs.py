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

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb import EC_CHECKER_OBLIGATION_MAP


# Article and annex citation patterns. Matches the short ``Art.`` form
# (and the no-period ``Art`` form when followed by digits), and the
# Roman-numeral Annex form. Sub-paragraph chains like ``(1)(a)`` are
# stripped — we record the bare article number / annex roman as the
# cross-reference target.
_ART_RE = re.compile(r"\bArt\.?\s*(\d{1,3})\b", re.IGNORECASE)
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLC]+)\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _build_xref_graph() -> dict[str, tuple[str, ...]]:
    """Build the cross-reference adjacency map at import time.

    Walks every obligation summary, extracts Art. N / Annex X mentions,
    validates each against :data:`ARTICLE_EXISTENCE`, and stores the
    deduplicated cross-reference list keyed by the source article.

    Self-references are dropped: an obligation that mentions its own
    article in its summary doesn't need a self-edge in the graph.
    """
    graph: dict[str, list[str]] = {}

    for source_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        summary = entry.get("summary", "")
        if not summary:
            continue

        targets: list[str] = []
        seen: set[str] = {source_ref}

        for match in _ART_RE.finditer(summary):
            num = match.group(1)
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


__all__ = ["cross_refs", "all_edges"]
