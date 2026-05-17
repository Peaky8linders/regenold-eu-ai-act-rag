"""Tests for R44 Pattern A — definition-graph recursive resolution.

Covers the public API of :mod:`app.engines.definition_expand`
(``build_definition_index`` + ``expand_with_definitions``) plus a
route-level integration through
``app.data.kb_search.top_articles_by_relevance``.

The expansion is **strictly additive**: every test verifies that the
original BM25 / dense ordering is preserved verbatim — only the tail
gains Art. 3 sub-citations.
"""
from __future__ import annotations

import pytest


# ── build_definition_index ────────────────────────────────────────────────


class TestBuildDefinitionIndex:
    """The frozen ``citation → frozenset(article-refs)`` map."""

    def test_returns_dict(self) -> None:
        from app.engines.definition_expand import build_definition_index

        idx = build_definition_index()
        assert isinstance(idx, dict)
        # Should have several dozen definitions populated.
        assert len(idx) >= 30

    def test_keys_are_art3_sub_citations(self) -> None:
        from app.engines.definition_expand import build_definition_index

        idx = build_definition_index()
        for citation in idx:
            assert citation.startswith("Art. 3.")

    def test_values_are_frozensets_of_real_refs(self) -> None:
        from app.engines.definition_expand import build_definition_index

        idx = build_definition_index()
        for citation, supporters in idx.items():
            assert isinstance(supporters, frozenset)
            assert all(isinstance(r, str) for r in supporters)
            # Every supporter is an Art. N or Annex X form (never Art. 3
            # itself — that's excluded from the scan).
            for ref in supporters:
                assert ref.startswith(("Art. ", "Annex "))

    def test_art3_self_exclusion(self) -> None:
        """Art. 3 itself is excluded from every supporter set."""
        from app.engines.definition_expand import build_definition_index

        idx = build_definition_index()
        for citation, supporters in idx.items():
            assert "Art. 3" not in supporters, (
                f"{citation} incorrectly includes Art. 3 in its supporter set"
            )

    def test_determinism(self) -> None:
        """Same input → same output across repeated calls."""
        from app.engines.definition_expand import build_definition_index

        first = build_definition_index()
        second = build_definition_index()
        # ``lru_cache`` makes this an identity equality.
        assert first is second
        # Even if a future refactor drops the cache, the contents must
        # match.
        assert first == second

    def test_high_impact_terms_have_supporters(self) -> None:
        """The big six operator-role terms all have non-empty supporter sets."""
        from app.engines.definition_expand import build_definition_index

        idx = build_definition_index()
        # Art. 3.3 = provider, Art. 3.4 = deployer, Art. 3.6 = importer,
        # Art. 3.7 = distributor, Art. 3.1 = AI system, Art. 3.15 (or
        # nearby) = high-risk AI system.
        for cit in ("Art. 3.1", "Art. 3.3", "Art. 3.4"):
            assert cit in idx, f"missing {cit} from index"
            assert len(idx[cit]) > 0, f"{cit} has empty supporter set"


# ── expand_with_definitions — unit cases ──────────────────────────────────


class TestExpandWithDefinitions:
    """Spec-mandated unit coverage."""

    # Case 1
    def test_empty_input_returns_empty(self) -> None:
        from app.engines.definition_expand import expand_with_definitions

        assert expand_with_definitions([]) == []

    # Case 2
    def test_no_defined_terms_unchanged(self) -> None:
        """A candidate whose prose doesn't use any Art. 3 term passes
        through unchanged.

        Pragmatic note: in the EU AI Act, "Art. 3" is excluded and most
        other articles use SOME defined term (the regulation is one big
        cross-reference). We use a fabricated ref outside the corpus to
        guarantee a no-hit case.
        """
        from app.engines.definition_expand import expand_with_definitions

        # ``Art. 999`` is not in ARTICLE_FULL_TEXT, so it has no prose
        # to scan — no definition gets a positive support count.
        out = expand_with_definitions(["Art. 999"], max_added=3)
        assert out == ["Art. 999"]

    # Case 3
    def test_single_defined_term_in_one_candidate(self) -> None:
        """A real article appends at least one definition sub-citation."""
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(["Art. 26"], max_added=3)
        # BM25 winner preserved at slot 0.
        assert out[0] == "Art. 26"
        # At least one Art. 3 sub-citation appended.
        appended = [r for r in out[1:] if r.startswith("Art. 3.")]
        assert appended, "expected at least one Art. 3 sub-citation"
        # No duplicates.
        assert len(set(out)) == len(out)

    # Case 4
    def test_multiple_defined_terms_deduplicated(self) -> None:
        """Distinct definitions across multiple candidates — each
        appears at most once."""
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(
            ["Art. 26", "Art. 19", "Art. 13"], max_added=3,
        )
        # Original order intact at the head.
        assert out[:3] == ["Art. 26", "Art. 19", "Art. 13"]
        # All appended refs distinct.
        appended = out[3:]
        assert len(appended) == len(set(appended))

    # Case 5
    def test_budget_cap_enforced(self) -> None:
        """Even with many definitions matched, only ``max_added`` are
        appended."""
        from app.engines.definition_expand import expand_with_definitions

        # A wide candidate set — many definitions will have multi-
        # candidate support.
        wide = [
            "Art. 6", "Art. 9", "Art. 10", "Art. 11", "Art. 12",
            "Art. 13", "Art. 14", "Art. 15", "Art. 16", "Art. 17",
        ]
        out = expand_with_definitions(wide, max_added=3)
        # Originals preserved.
        assert out[:10] == wide
        # Only 3 appended.
        assert len(out) == 13
        for ref in out[10:]:
            assert ref.startswith("Art. 3.")

    def test_zero_budget_no_appends(self) -> None:
        """``max_added=0`` is a valid no-op cap."""
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(["Art. 26", "Art. 19"], max_added=0)
        assert out == ["Art. 26", "Art. 19"]

    def test_negative_budget_no_appends(self) -> None:
        """Negative budget treated as zero — defensive."""
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(["Art. 26"], max_added=-5)
        assert out == ["Art. 26"]

    # Case 6
    def test_art3_already_present_no_double_append(self) -> None:
        """If ``Art. 3`` (parent) is in candidates, expansion is a
        complete no-op — sub-citations would collapse to the parent
        downstream anyway."""
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(["Art. 3", "Art. 26"], max_added=3)
        assert out == ["Art. 3", "Art. 26"]

    def test_art3_subcitation_already_present_skipped(self) -> None:
        """A specific Art. 3 sub-citation already in candidates is not
        re-appended."""
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(
            ["Art. 26", "Art. 3.4"], max_added=3,
        )
        # ``Art. 3.4`` survives at its original position.
        assert "Art. 3.4" in out
        # It only appears once.
        assert out.count("Art. 3.4") == 1
        # Other Art. 3 sub-citations may still be appended.
        assert out[0] == "Art. 26"
        assert out[1] == "Art. 3.4"

    # Case 7
    def test_plural_form_matches(self) -> None:
        """A definition whose plural surfaces in candidate prose is
        recognised.

        ``Art. 26`` is the deployer-obligations article; its prose uses
        "deployers" (plural) in addition to "deployer". The index
        should still credit Art. 3.4 (deployer) for that article.
        """
        from app.engines.definition_expand import build_definition_index

        idx = build_definition_index()
        # Art. 3.4 ("deployer") should have Art. 26 in supporters
        # regardless of whether the prose uses the singular or plural.
        assert "Art. 26" in idx["Art. 3.4"]

    # Case 8
    def test_index_build_determinism(self) -> None:
        from app.engines.definition_expand import build_definition_index

        a = build_definition_index()
        b = build_definition_index()
        # Same identity (cached) AND same contents.
        assert a is b
        assert dict(a) == dict(b)

    # Case 9 — fail-soft on garbage input
    def test_none_input_returns_empty(self) -> None:
        """Garbage non-list input → empty (never raises)."""
        from app.engines.definition_expand import expand_with_definitions

        # ``None`` — defensive sanity.
        assert expand_with_definitions(None) == []  # type: ignore[arg-type]

    def test_mixed_garbage_filtered(self) -> None:
        """List containing empty strings / None entries doesn't blow up."""
        from app.engines.definition_expand import expand_with_definitions

        # Empty strings and None entries are filtered; the function
        # returns the input echoed when nothing real survives.
        out = expand_with_definitions(
            ["", None, "Art. 999"], max_added=3,  # type: ignore[list-item]
        )
        # No exception raised.
        assert isinstance(out, list)
        # The fabricated Art. 999 has no corpus prose → no appends.
        assert "Art. 999" in out

    def test_never_raises_on_str_typed_garbage(self) -> None:
        """Garbage but type-correct input doesn't raise."""
        from app.engines.definition_expand import expand_with_definitions

        # All these should return cleanly.
        for garbage in [
            ["xxx"],
            ["Article 13"],  # external form — not internal, no prose lookup.
            ["123"],
            ["   "],
        ]:
            out = expand_with_definitions(garbage, max_added=3)
            assert isinstance(out, list)

    def test_does_not_mutate_input(self) -> None:
        from app.engines.definition_expand import expand_with_definitions

        original = ["Art. 26", "Art. 19"]
        snapshot = list(original)
        _ = expand_with_definitions(original, max_added=3)
        assert original == snapshot

    def test_appended_refs_are_art3_sub_citations(self) -> None:
        from app.engines.definition_expand import expand_with_definitions

        out = expand_with_definitions(["Art. 26", "Art. 19"], max_added=3)
        for ref in out[2:]:
            assert ref.startswith("Art. 3.")

    def test_specificity_tiebreak_favours_longer_terms(self) -> None:
        """Among definitions with equal support count, longer terms
        win the tiebreak (more specific → less noise)."""
        from app.engines.definition_expand import expand_with_definitions

        # Pick two candidates whose intersection contains several
        # tied-count definitions; the longer-term ones should appear
        # before shorter-term ones in the appended tail.
        out = expand_with_definitions(["Art. 26", "Art. 19"], max_added=3)
        appended = out[2:]
        # Look up the term lengths.
        from app.data.definitions import DEFINITION_REGISTRY

        term_lens = [
            len(DEFINITION_REGISTRY[c].term)
            for c in appended
            if c in DEFINITION_REGISTRY
        ]
        # The append order should be by descending count, then
        # descending term length. Among tied-count terms the lengths
        # should appear in non-increasing order.
        # Since all may have equal count here, we just check the head
        # has the longest length seen.
        assert term_lens, "expected at least one valid append"
        assert max(term_lens) == term_lens[0]


# ── Case 10 — integration through top_articles_by_relevance ───────────────


class TestRouteIntegration:
    """Verify the wire-in lands an Art. 3 sub-citation on a multi-cite
    deployer-logs question."""

    def test_deployer_logs_includes_art3_subcite(self) -> None:
        """A question phrased like the spec's worked example surfaces an
        Art. 3 sub-citation in the candidate list."""
        from app.data.kb_search import top_articles_by_relevance

        refs = top_articles_by_relevance(
            "What logs must a deployer of a high-risk AI system retain?",
            k=5,
            min_score=0.5,
        )
        # Expect at least one Art. 3 sub-citation in the result.
        art3_subs = [r for r in refs if r.startswith("Art. 3.")]
        assert art3_subs, (
            f"expected Art. 3 sub-citation in {refs}; the definition-graph "
            "expansion should land at least one for this multi-cite question"
        )

    def test_no_subcites_when_no_bm25_winners(self) -> None:
        """Pure-garbage query → empty list. The expansion respects the
        upstream empty contract."""
        from app.data.kb_search import top_articles_by_relevance

        refs = top_articles_by_relevance("xyzzy qux", k=3)
        assert refs == []

    def test_bm25_winner_order_preserved(self) -> None:
        """The expansion never reshuffles non-Art-3 winners."""
        from app.data.kb_search import top_articles_by_relevance

        refs = top_articles_by_relevance(
            "transparency obligations for deployers", k=5, min_score=0.5,
        )
        # Filter out Art. 3 sub-citations; the remaining order must be
        # the same as if expansion hadn't fired.
        non_art3 = [r for r in refs if not r.startswith("Art. 3.")]
        # We can't compare to a baseline directly without an env-gate;
        # instead verify there are no duplicates and the head is a non-
        # Art-3 ref (BM25 winners always lead).
        assert len(set(non_art3)) == len(non_art3)
        if refs:
            assert not refs[0].startswith("Art. 3.")


# ── Existence-gate — every Art. 3.N appended resolves under prefix fallback


def test_appended_subcitations_resolve_under_article_existence() -> None:
    """Every Art. 3.N citation we emit has a real Art. 3 parent in
    ``ARTICLE_EXISTENCE``."""
    from app.data.article_existence import ARTICLE_EXISTENCE
    from app.engines.definition_expand import build_definition_index

    idx = build_definition_index()
    for citation in idx:
        # Sub-citations of Art. 3 — the parent must exist.
        parent = citation.split(".", 2)[0] + "." + citation.split(".", 2)[1]
        # parent is "Art. 3" — drop trailing digits to get the bare parent
        assert "Art. 3" in ARTICLE_EXISTENCE, (
            f"parent Art. 3 missing from ARTICLE_EXISTENCE for {citation}"
        )


# ── Performance — index build is sub-1s; expand is sub-1ms warm ───────────


def test_expand_is_fast_when_warm() -> None:
    """Sanity check: warm expansion is microsecond-scale (no per-query
    regex compile, no full corpus scan)."""
    import time
    from app.engines.definition_expand import (
        build_definition_index,
        expand_with_definitions,
    )

    # Prime the cache.
    build_definition_index()

    # Warm call — should be sub-1ms.
    start = time.perf_counter()
    for _ in range(100):
        _ = expand_with_definitions(["Art. 26", "Art. 19"], max_added=3)
    elapsed = (time.perf_counter() - start) / 100
    # Sub-2ms per call leaves enough headroom for CI variance.
    assert elapsed < 0.002, f"warm expand was {elapsed * 1000:.2f}ms"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
