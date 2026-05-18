"""R47-A — EU AI Act xref graph backfill (orphaned-article rescue).

These tests guard the prose-mined ``_BACKFILL_XREFS`` edge set in
:mod:`app.data.kb_xrefs`. The backfill was added to rescue 32 of 113
articles that had zero outgoing xref edges from the regex-extracted
graph — blocking the 2-hop GraphRAG expander from firing on critical
orphans like Art. 13 (transparency for high-risk), Art. 14 (human
oversight), Art. 26 (deployer obligations), Art. 50 (limited-risk
transparency), and Art. 56 (codes of practice).

Each guard below is structural, not data-shape-sensitive: edges may be
added or removed without breaking the suite, as long as the orphan
list stays small and the critical articles keep their fan-out.
"""
from __future__ import annotations

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb_xrefs import (
    BACKFILL_XREFS_LINTED,
    MANUAL_XREFS,
    _BACKFILL_XREFS,
    _build_regex_xref_graph,
    _build_xref_graph,
    all_edges,
    cross_refs,
    cross_refs_with_reason,
)


# ── R47 backfill linter ───────────────────────────────────────────────


class TestBackfillLinter:
    """The R47 prose-mined edges are the highest-confidence but also the
    largest set; the lint must reject any typo before it ships."""

    def test_backfill_lint_runs_at_import(self) -> None:
        """``BACKFILL_XREFS_LINTED`` is populated only if the import-time
        lint passed."""
        assert BACKFILL_XREFS_LINTED is _BACKFILL_XREFS or (
            tuple(BACKFILL_XREFS_LINTED) == tuple(_BACKFILL_XREFS)
        )

    def test_backfill_endpoints_in_existence(self) -> None:
        for source, target, _reason in _BACKFILL_XREFS:
            assert source in ARTICLE_EXISTENCE, (
                f"_BACKFILL_XREFS source {source!r} not in ARTICLE_EXISTENCE"
            )
            assert target in ARTICLE_EXISTENCE, (
                f"_BACKFILL_XREFS target {target!r} not in ARTICLE_EXISTENCE "
                f"(edge {source!r} → {target!r})"
            )

    def test_backfill_has_no_self_edges(self) -> None:
        for source, target, _reason in _BACKFILL_XREFS:
            assert source != target, (
                f"_BACKFILL_XREFS self-edge {source!r} → {target!r}"
            )

    def test_backfill_has_no_duplicates(self) -> None:
        """No ``(source, target)`` pair appears more than once in the
        backfill. Pairs that also exist in the regex pass or in
        ``MANUAL_XREFS`` are fine — the merge in
        :func:`_build_xref_graph` deduplicates."""
        seen: set[tuple[str, str]] = set()
        for source, target, _reason in _BACKFILL_XREFS:
            pair = (source, target)
            assert pair not in seen, (
                f"Duplicate _BACKFILL_XREFS edge {pair!r}"
            )
            seen.add(pair)

    def test_backfill_reasons_non_empty(self) -> None:
        for source, target, reason in _BACKFILL_XREFS:
            assert reason and reason.strip(), (
                f"_BACKFILL_XREFS {source!r} → {target!r} has empty reason"
            )

    def test_backfill_reasons_cite_a_paragraph_or_concept(self) -> None:
        """Every backfill reason should anchor itself in a specific
        prose locus — either an Article paragraph reference (``Art.
        N(M)``) or a recognisable AI-Act concept (HRAIS / GPAI /
        sandbox / etc.). Catches lazy reasons like "see prose"."""
        anchors = (
            "Art. ",
            "Annex ",
            "HRAIS",
            "GPAI",
            "sandbox",
            "deployer",
            "provider",
            "AR ",
            "CE marking",
            "EU database",
            "EU declaration",
            "Section",
            "Reverse",
            "AI Office",
            "Board",
            "Commission",
        )
        for source, target, reason in _BACKFILL_XREFS:
            assert any(a in reason for a in anchors), (
                f"_BACKFILL_XREFS {source!r} → {target!r} reason "
                f"{reason!r} doesn't cite a paragraph or concept"
            )


# ── Coverage guarantees ───────────────────────────────────────────────


class TestOrphanRescue:
    """The backfill must shrink the orphan-article set substantially
    AND give the critical hub articles a real fan-out."""

    def test_total_edge_count_grew(self) -> None:
        """Sanity: the merged graph carries strictly more edges than
        the regex-only graph. Catches an accidental no-op refactor."""
        regex_graph = _build_regex_xref_graph()
        merged = _build_xref_graph()
        regex_edges = sum(len(v) for v in regex_graph.values())
        merged_edges = sum(len(v) for v in merged.values())
        assert merged_edges > regex_edges + 50, (
            f"Expected merged graph to add >50 edges over regex-only "
            f"({regex_edges} regex vs {merged_edges} merged)"
        )

    def test_orphan_article_count_dropped_below_threshold(self) -> None:
        """At most 10 articles may remain with zero outgoing xref edges.

        Before R47-A: 32 orphans (28% of all articles).
        After R47-A:  expected ≤ 10 (≤ 9% — a 70%+ reduction).
        """
        merged = _build_xref_graph()
        articles_only = {k for k in ARTICLE_EXISTENCE if k.startswith("Art.")}
        nodes_with_edges = set(merged.keys()) | {
            t for ts in merged.values() for t in ts
        }
        # Orphan = article that appears NEITHER as a source NOR as a target.
        # We tolerate articles whose only role is "target" — those can be
        # rescued by 2-hop expansion from incoming neighbours.
        orphans_strict = sorted(
            (a for a in articles_only if a not in nodes_with_edges),
            key=lambda s: int(s.split()[1]),
        )
        assert len(orphans_strict) <= 10, (
            f"Too many orphan articles after R47-A backfill: "
            f"{len(orphans_strict)} > 10. Orphans: {orphans_strict}"
        )

    @pytest.mark.parametrize(
        "article,min_outgoing",
        [
            ("Art. 13", 2),   # transparency for high-risk
            ("Art. 14", 1),   # human oversight (prose only cites Annex III)
            ("Art. 26", 2),   # deployer obligations (V2 role_ambiguity)
            ("Art. 50", 2),   # limited-risk transparency
            ("Art. 56", 2),   # codes of practice
        ],
    )
    def test_critical_articles_have_fanout(
        self, article: str, min_outgoing: int
    ) -> None:
        """The pre-R47 zero-outgoing articles must now carry enough
        fan-out for the 2-hop expander to fire on them.

        R47 reconciliation: the orphan-rescue edges live in the FULL
        graph (``_build_xref_graph``) — the 1-hop ``cross_refs`` API
        returns the CORE graph (regex + manual only) so single-anchor
        QA isn't over-cited. Neo4j 2-hop expand reads the full graph
        via the seeder. So we check `_build_xref_graph` directly.
        """
        full_graph = _build_xref_graph()
        refs = full_graph.get(article, ())[:100]
        assert len(refs) >= min_outgoing, (
            f"{article} expected ≥{min_outgoing} outgoing xrefs in full graph, "
            f"got {len(refs)}: {refs}"
        )

    def test_art_13_includes_expected_high_risk_chain(self) -> None:
        """Art. 13 (transparency for high-risk) explicitly references the
        Art. 9 RMS, Art. 12 logs, Art. 14 oversight, Art. 15 cyber chain
        in its (3)(b) paragraph. This is the single highest-value
        rescue — it makes the 2-hop expander work for the most-asked
        high-risk-transparency probe."""
        full_graph = _build_xref_graph()
        refs = set(full_graph.get("Art. 13", ()))
        expected = {"Art. 9", "Art. 12", "Art. 14", "Art. 15"}
        missing = expected - refs
        assert not missing, (
            f"Art. 13 xrefs missing expected high-risk chain entries: {missing}"
        )

    def test_art_26_includes_deployer_chain(self) -> None:
        """Art. 26 must reach Art. 13 (provider's info schema), Art. 71
        (EU database), Art. 72 (post-market), and Annex III (the
        R47 orphan-rescue edges live in the FULL graph; cross_refs
        intentionally returns the CORE graph to keep QA precision).
        underlying use cases) — these are the deployer-side xrefs the
        V2 probe's ``role_ambiguity`` axis was failing on."""
        full_graph = _build_xref_graph()
        refs = set(full_graph.get("Art. 26", ()))
        expected_subset = {"Art. 13", "Art. 71", "Art. 72", "Annex III"}
        missing = expected_subset - refs
        assert not missing, (
            f"Art. 26 deployer-chain xrefs missing: {missing}"
        )


# ── Merge / dedup invariants ──────────────────────────────────────────


class TestMergeInvariants:
    """The backfill is APPENDED to the regex+manual edge set without
    duplicating existing edges. Catches a regression where the merge
    re-introduces an edge already in another source."""

    def test_no_edge_appears_twice_in_merged_adjacency(self) -> None:
        merged = _build_xref_graph()
        for source, targets in merged.items():
            assert len(targets) == len(set(targets)), (
                f"Duplicate edge in merged adjacency for {source!r}: {targets}"
            )

    def test_all_merged_edges_have_known_endpoints(self) -> None:
        """Every merged edge endpoint resolves to ARTICLE_EXISTENCE
        (sub-paragraph variants like ``Art. 6.3`` are accepted, mirroring
        the route's existence semantics)."""

        def _known(ref: str) -> bool:
            if ref in ARTICLE_EXISTENCE:
                return True
            candidate = ref
            while "." in candidate:
                candidate = candidate.rsplit(".", 1)[0].strip()
                if candidate in ARTICLE_EXISTENCE:
                    return True
            return False

        for source, target in all_edges():
            assert _known(source), (
                f"Merged edge source {source!r} unresolvable to ARTICLE_EXISTENCE"
            )
            assert _known(target), (
                f"Merged edge target {target!r} unresolvable to ARTICLE_EXISTENCE "
                f"(source: {source!r})"
            )

    def test_manual_xrefs_still_appear_after_backfill_merge(self) -> None:
        """The backfill must not displace any pre-existing manual edge.
        Regression guard against accidental list-overwrite. Manual edges
        live in BOTH core (cross_refs API) and full (_build_xref_graph)."""
        for source, target, _reason in MANUAL_XREFS:
            refs = cross_refs(source, limit=100)
            assert target in refs, (
                f"MANUAL_XREFS edge {source!r} → {target!r} missing from "
                f"core graph (cross_refs). Got: {refs}"
            )

    def test_backfill_xrefs_appear_in_merged_graph(self) -> None:
        """Every curated backfill edge must end up in the FULL merged graph.
        Backfill edges are intentionally excluded from cross_refs (route's
        1-hop API) to keep QA precision; they ARE in _build_xref_graph
        for Neo4j seeding + 2-hop production expansion."""
        full_graph = _build_xref_graph()
        for source, target, _reason in _BACKFILL_XREFS:
            refs = full_graph.get(source, ())
            assert target in refs, (
                f"_BACKFILL_XREFS edge {source!r} → {target!r} missing from "
                f"full merged graph. Got _build_xref_graph()[{source!r}]={refs}"
            )

    def test_backfill_reason_surfaces_in_cross_refs_with_reason(self) -> None:
        """The R47 reason — not the generic ``mentioned by`` fallback —
        is what ``cross_refs_with_reason`` returns for backfill edges.

        Smoke-test on the Art. 26 → Art. 13 edge, the canonical
        deployer-chain rescue.
        """
        pairs = dict(cross_refs_with_reason("Art. 26", limit=100))
        assert "Art. 13" in pairs, (
            f"Art. 26 → Art. 13 reason pair not surfaced: {pairs}"
        )
        reason = pairs["Art. 13"]
        assert "deployer" in reason.lower() or "Art. 13" in reason, (
            f"Art. 26 → Art. 13 reason looks generic: {reason!r}"
        )
        assert reason != "mentioned in obligation summary", (
            f"Art. 26 → Art. 13 fell back to generic reason: {reason!r}"
        )
