"""KB / ontology consistency lint.

Enforces the invariants documented in ``docs/ontology/ONTOLOGY.md``:
every article/annex reference appearing anywhere in the typed ontology
OR in any of the legacy lookup maps must resolve to a real entry in
:data:`app.data.article_existence.ARTICLE_EXISTENCE`.

Without this lint, a typo in a new keyword entry (e.g. ``("typo_keyword",
"Art. 500")``) would silently ship a hallucinated citation on the wire,
because the route's ``reference_from_article_ref`` filter validates
against ``ARTICLE_EXISTENCE`` but only at request time. We want fail-fast
at import / CI time — that's what the consistency lint provides.

The lint runs in CI as part of the standard pytest suite. New
ontology entries must pass these checks before they can land.
"""
from __future__ import annotations

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb import EC_CHECKER_OBLIGATION_MAP
from app.data.ontology import (
    ANNEX_III_REGISTRY,
    PHASE_REGISTRY,
    PRACTICE_REGISTRY,
    ROLE_OBLIGATIONS,
    all_articles_referenced,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _is_known_or_prefix_known(ref: str) -> bool:
    """A reference is valid if it's in :data:`ARTICLE_EXISTENCE` OR a
    sub-paragraph variant of an entry in it.

    Mirrors the route's existence semantics (``Art. 13.1.a`` is valid
    because ``Art. 13`` is in the catalog). Without this fallback, the
    ontology's intentional sub-paragraph references like ``Art. 5.1.a``
    would fail the lint.
    """
    if ref in ARTICLE_EXISTENCE:
        return True
    # Strip trailing ``.X`` segments and re-check.
    candidate = ref
    while "." in candidate:
        candidate = candidate.rsplit(".", 1)[0].strip()
        if candidate in ARTICLE_EXISTENCE:
            return True
    return False


# ── Ontology lint ─────────────────────────────────────────────────────


class TestOntologyConsistency:
    """Every typed-ontology reference must resolve in ARTICLE_EXISTENCE."""

    def test_practice_citations_resolve(self) -> None:
        """Every ``Practice.citation`` tuple member is a known article/annex."""
        for practice in PRACTICE_REGISTRY.values():
            for ref in practice.citation:
                assert _is_known_or_prefix_known(ref), (
                    f"Practice {practice.id!r}: citation {ref!r} not in "
                    f"ARTICLE_EXISTENCE"
                )

    def test_practice_high_risk_anchors_resolve(self) -> None:
        """Every ``Practice.related_high_risk_anchor`` (if set) is known."""
        for practice in PRACTICE_REGISTRY.values():
            if practice.related_high_risk_anchor is None:
                continue
            assert _is_known_or_prefix_known(practice.related_high_risk_anchor), (
                f"Practice {practice.id!r}: "
                f"related_high_risk_anchor={practice.related_high_risk_anchor!r} "
                f"not in ARTICLE_EXISTENCE"
            )

    def test_practice_effective_phases_resolve(self) -> None:
        """Every ``Practice.effective_phase`` is a valid Phase id."""
        for practice in PRACTICE_REGISTRY.values():
            assert practice.effective_phase in PHASE_REGISTRY, (
                f"Practice {practice.id!r}: effective_phase="
                f"{practice.effective_phase!r} is not a Phase id"
            )

    def test_annex_iii_categories_have_keywords(self) -> None:
        """Every Annex III category carries at least one keyword anchor.

        Without keywords the category is unreachable from a user
        question — defeats the purpose of having a typed registry.
        """
        for category in ANNEX_III_REGISTRY.values():
            assert category.keywords, (
                f"AnnexIIICategory {category.id!r} has no keywords"
            )

    def test_annex_iii_related_prohibitions_resolve(self) -> None:
        """Every related-prohibition reference is a valid Practice id."""
        for category in ANNEX_III_REGISTRY.values():
            for practice_id in category.related_prohibitions:
                assert practice_id in PRACTICE_REGISTRY, (
                    f"AnnexIIICategory {category.id!r}: "
                    f"related_prohibitions entry {practice_id!r} is not a "
                    f"Practice id"
                )

    def test_phase_articles_resolve(self) -> None:
        """Every article a Phase activates is in the catalog."""
        for phase in PHASE_REGISTRY.values():
            for ref in phase.articles:
                assert _is_known_or_prefix_known(ref), (
                    f"Phase {phase.id!r}: articles entry {ref!r} not in "
                    f"ARTICLE_EXISTENCE"
                )

    def test_phase_supersession_targets_resolve(self) -> None:
        """``Phase.superseded_by`` (if set) is a valid Phase id."""
        for phase in PHASE_REGISTRY.values():
            if phase.superseded_by is None:
                continue
            assert phase.superseded_by in PHASE_REGISTRY, (
                f"Phase {phase.id!r}: superseded_by={phase.superseded_by!r} "
                f"is not a Phase id"
            )

    def test_role_obligation_matrix_refs_resolve(self) -> None:
        """Every article ref in ROLE_OBLIGATIONS is in the catalog."""
        for role, by_class in ROLE_OBLIGATIONS.items():
            for risk_class, refs in by_class.items():
                for ref in refs:
                    assert _is_known_or_prefix_known(ref), (
                        f"ROLE_OBLIGATIONS[{role.value}][{risk_class.value}]: "
                        f"ref {ref!r} not in ARTICLE_EXISTENCE"
                    )

    def test_all_articles_referenced_helper_returns_only_known(self) -> None:
        """``all_articles_referenced()`` aggregates the full ontology ref set."""
        for ref in all_articles_referenced():
            assert _is_known_or_prefix_known(ref), (
                f"all_articles_referenced() includes {ref!r} not in "
                f"ARTICLE_EXISTENCE"
            )


# ── Legacy lookup-map lint ─────────────────────────────────────────────
#
# The legacy maps in graph_rag.py + scope.py predate the typed
# ontology. They stay live (they encode round-1-through-13 wins) but
# every reference value must still resolve in ARTICLE_EXISTENCE.


class TestLegacyMapConsistency:
    """The legacy keyword + classification maps must point at real refs."""

    def test_ec_checker_obligation_map_keys_resolve(self) -> None:
        """Every key in :data:`EC_CHECKER_OBLIGATION_MAP` is a real article."""
        for key in EC_CHECKER_OBLIGATION_MAP:
            assert _is_known_or_prefix_known(key), (
                f"EC_CHECKER_OBLIGATION_MAP key {key!r} not in ARTICLE_EXISTENCE"
            )

    def test_keyword_entity_map_targets_resolve(self) -> None:
        """Every ``_KEYWORD_ENTITY_MAP`` target article is real."""
        from app.engines.graph_rag import _deterministic_parse

        # _KEYWORD_ENTITY_MAP isn't a module-level constant; it's defined
        # inside _deterministic_parse. We exercise it indirectly by
        # asking the parser to extract entities from a question that
        # contains every keyword — but that's impractical, so instead
        # we import the source module and pull the list via the
        # function's closure. Tactical: just walk the literal value at
        # import time by re-reading the module file.
        import inspect
        source = inspect.getsource(_deterministic_parse)
        # Each entry in _KEYWORD_ENTITY_MAP looks like ``("kw", "Art. X")``.
        # Extract the second element with a tight regex over the literal.
        import re as _re
        refs = _re.findall(r'\(\s*"[^"]+"\s*,\s*"([^"]+)"\s*\)', source)
        # The function source also contains ``"_KEYWORD_ENTITY_MAP: list[…]"``
        # type annotation and the dict's inline definition; the regex
        # over (str, str) tuples captures only the keyword→article pairs.
        assert refs, "Could not extract _KEYWORD_ENTITY_MAP refs from source"
        for ref in refs:
            assert _is_known_or_prefix_known(ref), (
                f"_KEYWORD_ENTITY_MAP entry maps to {ref!r}, not in "
                f"ARTICLE_EXISTENCE"
            )

    def test_keyword_to_article_targets_resolve(self) -> None:
        """Every ``KEYWORD_TO_ARTICLE`` (scope) target is a real article."""
        from app.integrations.regenold.scope import KEYWORD_TO_ARTICLE
        for keyword, ref in KEYWORD_TO_ARTICLE.items():
            assert _is_known_or_prefix_known(ref), (
                f"KEYWORD_TO_ARTICLE[{keyword!r}] = {ref!r}, not in "
                f"ARTICLE_EXISTENCE"
            )

    def test_classification_topic_refs_resolve(self) -> None:
        """Every ``_CLASSIFICATION_TOPICS[i]['refs']`` entry is a real article."""
        from app.engines.graph_rag import _CLASSIFICATION_TOPICS
        for topic in _CLASSIFICATION_TOPICS:
            for ref in topic["refs"]:
                assert _is_known_or_prefix_known(ref), (
                    f"_CLASSIFICATION_TOPICS[{topic['name']!r}] cites "
                    f"{ref!r}, not in ARTICLE_EXISTENCE"
                )


# ── Cross-reference graph lint ────────────────────────────────────────


class TestCrossRefGraphConsistency:
    """The auto-derived cross-reference graph must only target real refs."""

    def test_all_edges_target_known_articles(self) -> None:
        from app.data.kb_xrefs import all_edges
        for source, target in all_edges():
            assert _is_known_or_prefix_known(source), (
                f"Cross-ref edge source {source!r} not in ARTICLE_EXISTENCE"
            )
            assert _is_known_or_prefix_known(target), (
                f"Cross-ref edge source={source!r} → target={target!r}: "
                f"target not in ARTICLE_EXISTENCE"
            )

    def test_no_self_edges(self) -> None:
        """A cross-ref graph with self-edges is a regression."""
        from app.data.kb_xrefs import all_edges
        for source, target in all_edges():
            assert source != target, (
                f"Self-edge {source!r} → {target!r} in cross-ref graph"
            )
