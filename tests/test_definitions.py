"""Tests for the Art. 3 definitions catalogue.

Pins the contract for :mod:`app.data.definitions`:

* ``DEFINITION_REGISTRY`` is keyed by valid ``Art. 3.N`` citations whose
  parents resolve in ``ARTICLE_EXISTENCE``.
* ``lookup_term`` finds a definition by its canonical term and by any
  of its keyword aliases.
* ``search_definitions`` returns at least three biometric-family
  definitions for the query ``"biometric"``.
* Every definition carries non-empty term + description + ≥1 keyword.
"""
from __future__ import annotations

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.definitions import (
    DEFINITION_REGISTRY,
    Definition,
    lookup_term,
    search_definitions,
)


def _is_known_or_prefix_known(ref: str) -> bool:
    """Mirror of the consistency-lint helper from test_kb_consistency."""
    if ref in ARTICLE_EXISTENCE:
        return True
    candidate = ref
    while "." in candidate:
        candidate = candidate.rsplit(".", 1)[0].strip()
        if candidate in ARTICLE_EXISTENCE:
            return True
    return False


class TestDefinitionRegistry:
    """Structural invariants of the registry."""

    def test_registry_non_empty(self) -> None:
        assert len(DEFINITION_REGISTRY) >= 30, (
            f"Expected ≥ 30 Art. 3 definitions; got {len(DEFINITION_REGISTRY)}"
        )

    def test_all_citations_resolve(self) -> None:
        """Every citation key resolves under prefix-fallback in ARTICLE_EXISTENCE."""
        for citation in DEFINITION_REGISTRY:
            assert _is_known_or_prefix_known(citation), (
                f"Definition citation {citation!r} does not resolve in "
                f"ARTICLE_EXISTENCE"
            )

    def test_every_entry_well_formed(self) -> None:
        """Term, description and ≥1 keyword are present for every entry."""
        for citation, defn in DEFINITION_REGISTRY.items():
            assert isinstance(defn, Definition), citation
            assert defn.term, f"{citation}: empty term"
            assert defn.description, f"{citation}: empty description"
            assert defn.keywords, f"{citation}: empty keywords tuple"

    def test_citations_are_art_3_subforms(self) -> None:
        """Every citation is an ``Art. 3.N`` sub-form."""
        for citation in DEFINITION_REGISTRY:
            assert citation.startswith("Art. 3."), (
                f"Definition citation {citation!r} is not under Art. 3"
            )


class TestLookupTerm:
    """Lookup by canonical term + alias."""

    def test_provider_maps_to_art_3_3(self) -> None:
        defn = lookup_term("provider")
        assert defn is not None
        assert defn.citation == "Art. 3.3"

    def test_deployer_maps_to_art_3_4(self) -> None:
        defn = lookup_term("deployer")
        assert defn is not None
        assert defn.citation == "Art. 3.4"

    def test_lookup_is_case_insensitive(self) -> None:
        upper = lookup_term("PROVIDER")
        lower = lookup_term("provider")
        assert upper is not None
        assert lower is not None
        assert upper.citation == lower.citation

    def test_lookup_by_alias_finds_definition(self) -> None:
        """``"GPAI model"`` should resolve via the alias tuple."""
        defn = lookup_term("GPAI model")
        assert defn is not None
        assert defn.citation == "Art. 3.63"

    def test_lookup_by_plural_alias(self) -> None:
        """Plural aliases are part of the keyword tuple."""
        defn = lookup_term("providers")
        assert defn is not None
        assert defn.citation == "Art. 3.3"

    def test_unknown_term_returns_none(self) -> None:
        assert lookup_term("nonexistent regulatory term xyz") is None

    def test_empty_input_returns_none(self) -> None:
        assert lookup_term("") is None


class TestSearchDefinitions:
    """Token-overlap search across the catalogue."""

    def test_biometric_query_returns_at_least_three(self) -> None:
        """The biometric family has ≥3 entries (data / identification /
        verification / categorisation / RBI variants)."""
        hits = search_definitions("biometric", top_k=10)
        assert len(hits) >= 3, (
            f"Expected ≥ 3 biometric definitions; got {len(hits)}: {hits!r}"
        )

    def test_search_respects_top_k(self) -> None:
        hits = search_definitions("biometric", top_k=2)
        assert len(hits) <= 2

    def test_empty_query_returns_empty(self) -> None:
        assert search_definitions("") == []
        assert search_definitions("   ") == []

    def test_search_returns_citation_definition_pairs(self) -> None:
        hits = search_definitions("provider", top_k=3)
        assert hits, "expected at least one hit for 'provider'"
        for citation, defn in hits:
            assert citation == defn.citation
            assert isinstance(defn, Definition)

    def test_phrase_match_beats_token_match(self) -> None:
        """Multi-word query should prefer the entry whose alias contains
        the whole phrase over one that only matches a single token."""
        hits = search_definitions("biometric verification", top_k=3)
        assert hits, "expected at least one hit"
        top_citation, _top_defn = hits[0]
        # Art. 3.35 is the biometric-verification entry; it should rank
        # at or near the top of a "biometric verification" search.
        assert top_citation == "Art. 3.35", (
            f"Expected Art. 3.35 (biometric verification) at top; got {top_citation}"
        )
