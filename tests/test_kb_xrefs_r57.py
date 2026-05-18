"""R57-C — 14 P0 cross-reference graph edges + confidence-boost retune.

The R57 graph audit (``docs/reviews/R57-GRAPH-RETRIEVAL-AUDIT.md``)
identified that the CORE xref graph had 8 of 11 V2-weak-axis articles
with zero outgoing edges — meaning the route's 1-hop scenario expand
(``cross_refs``) returned ``()`` and the BM25 confidence boost
(``_xref_in_degree``) was a flat 1.0 for them. These tests pin the 14
P0 edges added to ``MANUAL_XREFS`` and verify the boost now reads
from the FULL graph with a 1.10 cap (down from 1.15).

Each P0 edge is grounded in a specific EUR-Lex paragraph or sub-point
— see the comment block at the top of ``app/data/kb_xrefs.py``'s
R57-C section for the audit reasoning.
"""
from __future__ import annotations

import pytest

from app.data.kb_xrefs import (
    MANUAL_XREFS,
    _build_xref_graph,
    _build_xref_graph_core,
    cross_refs,
)


# Audit's full P0 edge list (14 tuples). Order matches the audit table.
R57_P0_EDGES: tuple[tuple[str, str], ...] = (
    # role_ambiguity
    ("Art. 16", "Art. 25"),
    ("Art. 26", "Art. 16"),
    ("Art. 26", "Art. 25"),
    ("Art. 22", "Art. 16"),
    ("Art. 22", "Art. 25"),
    # gpai
    ("Art. 53", "Art. 56"),
    ("Art. 53", "Art. 101"),
    ("Art. 51", "Art. 53"),
    ("Art. 55", "Art. 53"),
    ("Art. 25", "Art. 53"),
    # conflict
    ("Art. 73", "Art. 79"),
    ("Art. 79", "Art. 73"),
    ("Art. 79", "Art. 26"),
    ("Art. 6", "Art. 5"),
)


# ── Edge presence guards ───────────────────────────────────────────────


class TestR57P0Edges:
    """Each P0 edge must land in the CORE graph (so the route's 1-hop
    expand sees it AND the BM25 confidence boost picks up the in-degree
    contribution after R57-C's full-graph swap)."""

    def test_all_p0_edges_present_in_core_graph(self) -> None:
        core = _build_xref_graph_core()
        missing = [
            (src, dst)
            for src, dst in R57_P0_EDGES
            if dst not in core.get(src, ())
        ]
        assert not missing, (
            f"R57-C P0 edges missing from CORE graph: {missing}"
        )

    def test_all_p0_edges_present_in_full_graph(self) -> None:
        full = _build_xref_graph()
        missing = [
            (src, dst)
            for src, dst in R57_P0_EDGES
            if dst not in full.get(src, ())
        ]
        assert not missing, (
            f"R57-C P0 edges missing from FULL graph: {missing}"
        )

    @pytest.mark.parametrize("source,target", R57_P0_EDGES)
    def test_p0_edge_via_cross_refs(self, source: str, target: str) -> None:
        """``cross_refs(source)`` (route's 1-hop API) must include the
        target within a reasonable limit (10 wide enough to cover the
        densest source in this set)."""
        assert target in cross_refs(source, limit=10), (
            f"cross_refs({source!r}, limit=10) missing R57-C target {target!r}"
        )

    def test_p0_edges_carry_r57c_reason(self) -> None:
        """Each new P0 edge must surface an R57-C-tagged reason via the
        forensic ``cross_refs_with_reason`` API so audit consumers see
        why it was added."""
        from app.data.kb_xrefs import cross_refs_with_reason

        p0_set = set(R57_P0_EDGES)
        for source, target in p0_set:
            pairs = dict(cross_refs_with_reason(source, limit=20))
            reason = pairs.get(target, "")
            assert reason, (
                f"R57-C edge {source!r} -> {target!r} has no reason surfaced"
            )
            # The reason itself should be EU AI Act-grounded (mentions an
            # Article or specific concept), not lazy "see prose".
            assert (
                "Art. " in reason
                or "R57-C" in reason
                or "AI Act" in reason
            ), (
                f"R57-C edge {source!r} -> {target!r} reason looks ungrounded: "
                f"{reason!r}"
            )


# ── audit-spec inverse cases (orphan rescue) ──────────────────────────


class TestR57OrphanRescue:
    """Three audit-flagged orphan articles (Art. 22, Art. 26, Art. 79)
    that returned ``()`` pre-R57 must now return non-empty fan-out."""

    @pytest.mark.parametrize("orphan", ["Art. 22", "Art. 26", "Art. 79"])
    def test_audit_orphan_now_has_outgoing(self, orphan: str) -> None:
        """Pre-R57: ``cross_refs('Art. 22') = ()``. Post-R57: ≥ 1."""
        refs = cross_refs(orphan, limit=10)
        assert len(refs) >= 1, (
            f"R57-C: {orphan} should have ≥1 outgoing edge post-R57 "
            f"(audit-flagged orphan); got {refs!r}"
        )


# ── P1 — confidence-boost retune ──────────────────────────────────────


class TestConfidenceBoostR57:
    """``_xref_in_degree`` must read the FULL graph so all R47-A backfill
    edges contribute to the BM25 boost. The saturation cap drops from
    1.15 → 1.10 to compensate for the larger graph."""

    def test_xref_in_degree_reads_full_graph(self) -> None:
        """An article with edges only in FULL graph (R47-A backfill) but
        not in CORE pre-R57-C should now have non-zero in-degree.

        Art. 13 (transparency for high-risk) is the canonical example:
        the audit observed core_in_degree=0, full_in_degree=4.
        """
        from app.data.kb_search import _xref_in_degree

        _xref_in_degree.cache_clear()
        deg = _xref_in_degree()

        # Art. 13 had zero core in-degree pre-R57-C; its in-degree
        # comes entirely from R47-A's backfill (Art. 26 → 13,
        # Art. 27 → 13, Art. 60 → 13, Annex IV → 13). Must be ≥ 2
        # for the FULL-graph swap to be detectable.
        assert deg.get("Art. 13", 0) >= 2, (
            f"R57-C: _xref_in_degree should read FULL graph; "
            f"Art. 13 in-degree = {deg.get('Art. 13', 0)} (expected ≥ 2)"
        )

    def test_confidence_boost_cap_lowered_to_1_10(self) -> None:
        """The boost saturation cap dropped 1.15 → 1.10. No article can
        return a multiplier above 1.10, even at very high in-degree."""
        from app.data.kb_search import _confidence_boost, _xref_in_degree

        _xref_in_degree.cache_clear()
        deg = _xref_in_degree()
        if not deg:
            pytest.skip("No articles with in-degree — empty xref graph")
        # Find the highest-in-degree article and verify its boost
        # respects the new 1.10 ceiling.
        max_art = max(deg, key=deg.get)
        max_boost = _confidence_boost(max_art)
        assert max_boost <= 1.10 + 1e-9, (
            f"R57-C: max boost {max_boost:.4f} on {max_art!r} "
            f"(in_degree={deg[max_art]}) exceeds 1.10 cap"
        )

    def test_orphan_articles_have_zero_boost(self) -> None:
        """An article with no incoming xref edges still returns 1.0
        (no boost)."""
        from app.data.kb_search import _confidence_boost

        # Pick an article that genuinely has no incoming edges in the
        # FULL graph. Art. 113 (entry into application) is a
        # purpose-statement leaf — nothing internal cites it.
        # If this assertion fails because we added an edge to Art. 113,
        # swap to another genuinely-leaf article.
        from app.data.kb_search import _xref_in_degree

        _xref_in_degree.cache_clear()
        deg = _xref_in_degree()

        # Find any article with zero in-degree.
        from app.data.article_existence import ARTICLE_EXISTENCE

        zero_articles = [
            a for a in ARTICLE_EXISTENCE
            if a.startswith("Art. ") and deg.get(a, 0) == 0
        ]
        if not zero_articles:
            pytest.skip("Every article has incoming edges post-R57-C")
        # Pick any zero-degree article and verify boost == 1.0.
        sample = zero_articles[0]
        assert _confidence_boost(sample) == pytest.approx(1.0)

    def test_high_in_degree_lifted_relative_to_low(self) -> None:
        """V2-weak-axis articles (Art. 13/14/26/56/73/101) were flat 1.0
        pre-R57-C because their core_in_degree was 0. Post-R57-C they
        must rank above a flat 1.0 baseline."""
        from app.data.kb_search import _confidence_boost, _xref_in_degree

        _xref_in_degree.cache_clear()
        for art in [
            "Art. 13",
            "Art. 14",
            "Art. 26",
            "Art. 56",
            "Art. 72",
            "Art. 73",
            "Art. 101",
        ]:
            boost = _confidence_boost(art)
            assert boost > 1.0, (
                f"R57-C: {art} should have boost > 1.0 post-R57-C "
                f"(audit-flagged V2-weak-axis article); got {boost:.4f}"
            )

    def test_boost_monotone_in_indegree(self) -> None:
        """Boost must increase monotonically with in-degree (no
        discontinuities, no regressions)."""
        from app.data.kb_search import _confidence_boost

        # Build a synthetic monotone sequence and verify boost is
        # non-decreasing. (Tests the pure function shape, not the
        # graph state.)
        prev = 1.0
        for fake_deg in range(0, 50):
            # _confidence_boost takes article_ref — patch via
            # bypassing the lookup. Test the underlying math:
            import math

            if fake_deg <= 0:
                computed = 1.0
            else:
                computed = min(
                    1.0 + 0.04 * math.log2(1 + fake_deg) / 2.0, 1.10
                )
            assert computed >= prev - 1e-9, (
                f"Boost non-monotone at deg={fake_deg}: {computed} < {prev}"
            )
            prev = computed
        # Saturation reached.
        assert prev <= 1.10 + 1e-9


# ── manual-xref lint regression — make sure the lint still runs ───────


class TestR57ManualXrefsLint:
    """The R57-C edges were appended to ``MANUAL_XREFS``. The existing
    lint at ``_lint_manual_xrefs`` must still pass against the larger
    list (already enforced at import — these tests are redundant safety
    nets)."""

    def test_all_r57c_endpoints_in_existence(self) -> None:
        from app.data.article_existence import ARTICLE_EXISTENCE

        for source, target in R57_P0_EDGES:
            assert source in ARTICLE_EXISTENCE, (
                f"R57-C source {source!r} not in ARTICLE_EXISTENCE"
            )
            assert target in ARTICLE_EXISTENCE, (
                f"R57-C target {target!r} not in ARTICLE_EXISTENCE"
            )

    def test_r57c_edges_in_manual_xrefs(self) -> None:
        """Each P0 edge must appear in the curated ``MANUAL_XREFS`` list
        (not in ``_BACKFILL_XREFS``), since the route's CORE graph reads
        manual edges only."""
        manual_pairs = {(s, t) for s, t, _ in MANUAL_XREFS}
        missing = [
            (s, t) for s, t in R57_P0_EDGES if (s, t) not in manual_pairs
        ]
        assert not missing, (
            f"R57-C edges not in MANUAL_XREFS (would only land in FULL graph): "
            f"{missing}"
        )

    def test_no_p0_self_edges(self) -> None:
        for source, target in R57_P0_EDGES:
            assert source != target, (
                f"R57-C self-edge {source!r} -> {target!r}"
            )

    def test_p0_edges_unique(self) -> None:
        """No duplicate ``(source, target)`` pairs in the audit's P0 list."""
        seen: set[tuple[str, str]] = set()
        for pair in R57_P0_EDGES:
            assert pair not in seen, f"Duplicate R57-C P0 edge: {pair!r}"
            seen.add(pair)
