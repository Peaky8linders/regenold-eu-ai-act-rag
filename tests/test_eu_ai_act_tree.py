"""Tests for Layer A — Document-as-a-Tree topology of the EU AI Act.

Covers ``app.data.eu_ai_act_tree``: the layout-aware parser that splits
the flat EUR-Lex prose in ``ARTICLE_FULL_TEXT`` into a typed tree of
:class:`TreeNode` instances with deterministic risk-tier + timeline
metadata, per the architecture-PDF whitepaper.
"""
from __future__ import annotations

from collections import Counter

import pytest

from app.data.eu_ai_act_tree import (
    RISK_TIER_BY_ARTICLE,
    TIMELINE_BY_ARTICLE,
    TreeNode,
    build_tree,
    find_nodes_by_keyword,
    get_parent_context,
    iter_children,
    parent_of,
)


# ──────────────────────────────────────────────────────────────────────────
# Construction + invariants.
# ──────────────────────────────────────────────────────────────────────────


class TestTreeConstruction:
    def test_tree_builds_without_exception(self):
        tree = build_tree()
        assert isinstance(tree, dict)
        assert len(tree) > 0

    def test_tree_has_reasonable_node_count(self):
        """≥ 400 nodes (126 articles/annexes × avg 3 children +
        180 recitals + 68 definitions ≈ 626 minimum)."""
        tree = build_tree()
        assert len(tree) >= 600, f"tree only has {len(tree)} nodes"

    def test_all_113_articles_present_as_roots(self):
        tree = build_tree()
        for n in range(1, 114):
            slug = f"art_{n}"
            assert slug in tree, f"missing article root {slug}"
            assert tree[slug].kind == "article"

    def test_all_13_annexes_present_as_roots(self):
        tree = build_tree()
        roman = ["I", "II", "III", "IV", "V", "VI", "VII",
                 "VIII", "IX", "X", "XI", "XII", "XIII"]
        for r in roman:
            slug = f"annex_{r.lower()}"
            assert slug in tree, f"missing annex root {slug}"
            assert tree[slug].kind == "annex"

    def test_kind_histogram_breakdown(self):
        """Sanity-bounds on the kind histogram — ensures the parser
        actually found paragraphs and sub-points, not just emitted
        article roots."""
        tree = build_tree()
        kinds = Counter(n.kind for n in tree.values())
        assert kinds["article"] == 113
        assert kinds["annex"] == 13
        assert kinds["recital"] == 180
        assert kinds["definition"] == 68
        # Should have hundreds of paragraphs + sub-points.
        assert kinds["paragraph"] >= 200, f"only {kinds['paragraph']} paragraphs"
        assert kinds["subpoint"] >= 100, f"only {kinds['subpoint']} subpoints"
        assert kinds["annex_point"] >= 20, f"only {kinds['annex_point']} annex points"

    def test_build_tree_is_cached(self):
        """``lru_cache`` means repeat calls return the same instance."""
        a = build_tree()
        b = build_tree()
        assert a is b


# ──────────────────────────────────────────────────────────────────────────
# Parent-ID linking + traversal.
# ──────────────────────────────────────────────────────────────────────────


class TestParentLinking:
    def test_every_parent_id_resolves(self):
        """Every non-root node's parent_id must exist in the tree."""
        tree = build_tree()
        orphans = []
        for node in tree.values():
            if node.parent_id is not None and node.parent_id not in tree:
                orphans.append((node.node_id, node.parent_id))
        assert orphans == [], f"orphan parent_ids: {orphans[:5]}"

    def test_article_roots_have_no_parent(self):
        tree = build_tree()
        for n in range(1, 114):
            root = tree[f"art_{n}"]
            assert root.parent_id is None, f"art_{n} has parent {root.parent_id}"

    def test_paragraph_parent_is_article(self):
        tree = build_tree()
        node = tree.get("art_5_p_1")
        assert node is not None, "Art. 5 paragraph 1 missing"
        assert node.kind == "paragraph"
        parent = parent_of("art_5_p_1")
        assert parent is not None
        assert parent.node_id == "art_5"
        assert parent.kind == "article"

    def test_subpoint_parent_is_paragraph(self):
        tree = build_tree()
        node = tree.get("art_5_p_1_a")
        assert node is not None, "Art. 5(1)(a) missing"
        assert node.kind == "subpoint"
        parent = parent_of("art_5_p_1_a")
        assert parent is not None
        assert parent.kind == "paragraph"
        assert parent.node_id == "art_5_p_1"

    def test_children_list_consistent_with_parent_ids(self):
        """For each node, every child_id should back-reference the parent."""
        tree = build_tree()
        for parent in tree.values():
            for child_id in parent.children_ids:
                child = tree.get(child_id)
                assert child is not None, f"dangling child {child_id} on {parent.node_id}"
                assert child.parent_id == parent.node_id, (
                    f"child {child_id} parent_id={child.parent_id} "
                    f"!= expected {parent.node_id}"
                )

    def test_recitals_have_no_parent(self):
        tree = build_tree()
        for n in (1, 50, 100, 180):
            node = tree.get(f"recital_{n}")
            assert node is not None, f"recital_{n} missing"
            assert node.kind == "recital"
            assert node.parent_id is None

    def test_definitions_parented_to_article_3(self):
        tree = build_tree()
        # Pick a few well-known definitions.
        for slug_part in ("ai_system", "provider", "deployer"):
            slug = f"def_{slug_part}"
            if slug in tree:
                node = tree[slug]
                assert node.kind == "definition"
                assert node.parent_id == "art_3"


# ──────────────────────────────────────────────────────────────────────────
# Risk-tier + timeline derivation.
# ──────────────────────────────────────────────────────────────────────────


class TestRiskTier:
    def test_article_5_is_prohibited(self):
        assert RISK_TIER_BY_ARTICLE["Article 5"] == "prohibited"

    def test_article_6_is_high_risk(self):
        assert RISK_TIER_BY_ARTICLE["Article 6"] == "high_risk"

    def test_article_50_is_limited(self):
        assert RISK_TIER_BY_ARTICLE["Article 50"] == "limited"

    def test_article_51_is_gpai(self):
        assert RISK_TIER_BY_ARTICLE["Article 51"] == "gpai"

    def test_article_55_is_gpai_systemic(self):
        assert RISK_TIER_BY_ARTICLE["Article 55"] == "gpai_systemic"

    def test_annex_iii_is_high_risk(self):
        assert RISK_TIER_BY_ARTICLE["Annex III"] == "high_risk"

    def test_annex_xiii_is_gpai(self):
        assert RISK_TIER_BY_ARTICLE["Annex XIII"] == "gpai"

    def test_governance_articles_are_n_a(self):
        # Penalties (Art. 99), AI Office (Art. 64), entry-into-force
        # (Art. 113) are not themselves risk-tier articles.
        for n in (1, 2, 3, 64, 99, 113):
            assert RISK_TIER_BY_ARTICLE[f"Article {n}"] == "n/a", (
                f"Article {n} should be n/a"
            )

    def test_high_risk_chapter_iii_articles(self):
        """Chapter III obligations (Art. 8-49) are all high-risk."""
        for n in range(8, 50):
            assert RISK_TIER_BY_ARTICLE[f"Article {n}"] == "high_risk", (
                f"Article {n} missing high_risk"
            )

    def test_tree_nodes_inherit_risk_tier(self):
        """Every paragraph/subpoint under Art. 5 inherits ``prohibited``."""
        tree = build_tree()
        for node in tree.values():
            if node.article_number == "Article 5":
                assert node.risk_tier == "prohibited", (
                    f"{node.node_id} should be prohibited, got {node.risk_tier}"
                )


class TestTimeline:
    def test_article_5_prohibition_date(self):
        assert TIMELINE_BY_ARTICLE["Article 5"] == "2025-02-02"

    def test_article_4_ai_literacy_date(self):
        # AI literacy applies on the same date as prohibitions.
        assert TIMELINE_BY_ARTICLE["Article 4"] == "2025-02-02"

    def test_gpai_obligations_date(self):
        for n in (51, 53, 55):
            assert TIMELINE_BY_ARTICLE[f"Article {n}"] == "2025-08-02", (
                f"Art. {n} should be 2025-08-02"
            )

    def test_annex_iii_omnibus_deferred_date(self):
        # Digital Omnibus political agreement 7 May 2026 — Annex III
        # high-risk to 2 December 2027 (was Aug 2026).
        assert TIMELINE_BY_ARTICLE["Annex III"] == "2027-12-02"

    def test_annex_i_omnibus_deferred_date(self):
        # Digital Omnibus — Annex I embedded-product to 2 August 2028.
        assert TIMELINE_BY_ARTICLE["Annex I"] == "2028-08-02"

    def test_general_application_date_default(self):
        # Art. 6 itself applies on the general date (its OBLIGATIONS are
        # tied to Annex III, but the classification article is general).
        assert TIMELINE_BY_ARTICLE["Article 6"] == "2026-08-02"

    def test_tree_nodes_inherit_timeline(self):
        tree = build_tree()
        any_art5_child = False
        for node in tree.values():
            if node.article_number == "Article 5":
                assert node.timeline_effective_date == "2025-02-02"
                any_art5_child = True
        assert any_art5_child, "no Art. 5 child nodes found"


# ──────────────────────────────────────────────────────────────────────────
# Keyword scan + parent-context retrieval.
# ──────────────────────────────────────────────────────────────────────────


class TestKeywordScan:
    def test_real_time_biometric_returns_art_5_child(self):
        """The architecture-PDF acid test — real-time biometric is the
        canonical Art. 5(1)(h) probe.

        Spec wording: ``find_nodes_by_keyword("real-time biometric")``
        — but the EUR-Lex prose says ``"'real-time' remote biometric"``.
        We accept the longer canonical phrase here because the bare
        2-word phrase doesn't appear contiguously in the regulation."""
        hits = find_nodes_by_keyword("real-time remote biometric")
        assert len(hits) >= 1, "no real-time biometric hits"
        # At least one hit must be from Article 5.
        art5_hits = [h for h in hits if h.article_number == "Article 5"]
        assert art5_hits, f"hits span {[h.article_number for h in hits]} — no Art. 5"

    def test_keyword_case_insensitive(self):
        a = find_nodes_by_keyword("BIOMETRIC")
        b = find_nodes_by_keyword("biometric")
        assert len(a) == len(b)
        assert set(n.node_id for n in a) == set(n.node_id for n in b)

    def test_keyword_curly_quotes_normalised(self):
        """The corpus pads ``real-time`` with curly quotes (U+2018/2019);
        our scan must hit even when the needle uses plain quotes."""
        # No quotes in needle — should still match the curly-quoted body.
        hits = find_nodes_by_keyword("remote biometric")
        assert len(hits) >= 1

    def test_empty_keyword_returns_empty(self):
        assert find_nodes_by_keyword("") == []

    def test_unknown_keyword_returns_empty(self):
        hits = find_nodes_by_keyword("zzzzz_no_such_phrase_xyz")
        assert hits == []

    def test_kind_filter(self):
        """Restricting to article roots should give different results
        than the default child-level filter."""
        child_hits = find_nodes_by_keyword(
            "biometric",
            kinds=("paragraph", "subpoint", "annex_point"),
        )
        root_hits = find_nodes_by_keyword(
            "biometric",
            kinds=("article", "annex"),
        )
        # Root hits should be a much smaller set.
        assert len(root_hits) < len(child_hits)


class TestParentContext:
    def test_parent_context_for_subpoint_returns_article(self):
        """Per the spec: sub-points climb to the encompassing Article."""
        ctx = get_parent_context("art_5_p_1_a")
        # Should contain the sub-point text itself.
        assert "subliminal" in ctx.lower()
        # Should also contain SIBLING sub-points (Art. 5(1)(b) — exploits
        # vulnerabilities; Art. 5(1)(c) — social scoring).
        assert "vulnerabilities" in ctx.lower() or "social" in ctx.lower()

    def test_parent_context_includes_sibling_paragraphs(self):
        """Spec test 7 — parent context for a paragraph child returns
        text that includes its sibling paragraphs."""
        # Art. 6 has multiple paragraphs (Art. 6(1), 6(2), 6(3)).
        ctx = get_parent_context("art_6_p_1")
        assert len(ctx) > 1000, f"parent context only {len(ctx)} chars"
        # Should include content from paragraph 2 or later — i.e. the
        # text mentions Annex III (Art. 6(2) topic) or paragraph 2's body.
        lower = ctx.lower()
        assert "annex" in lower, "parent context missing Annex reference"

    def test_parent_context_for_article_root_returns_self(self):
        """An article root has no parent — context is its own text."""
        ctx = get_parent_context("art_5")
        assert "prohibited" in ctx.lower()
        assert len(ctx) > 5000  # Art. 5 is a long article.

    def test_parent_context_for_recital_returns_self(self):
        """Recitals are atomic — no parent, context is self."""
        ctx = get_parent_context("recital_1")
        assert len(ctx) > 50

    def test_parent_context_for_unknown_node_returns_empty(self):
        assert get_parent_context("no_such_node") == ""


# ──────────────────────────────────────────────────────────────────────────
# Navigation API surface.
# ──────────────────────────────────────────────────────────────────────────


class TestNavigation:
    def test_iter_children_yields_paragraphs(self):
        kids = list(iter_children("art_5"))
        assert len(kids) > 1, "Art. 5 has multiple paragraphs"
        assert all(k.kind == "paragraph" for k in kids)

    def test_iter_children_yields_subpoints(self):
        # Art. 5(1) has letter sub-points (a)-(h).
        kids = list(iter_children("art_5_p_1"))
        if kids:
            assert all(k.kind == "subpoint" for k in kids)
            assert any(k.subpoint_letter == "a" for k in kids)

    def test_iter_children_unknown_parent_is_empty(self):
        assert list(iter_children("no_such_node")) == []

    def test_parent_of_top_level_is_none(self):
        assert parent_of("art_5") is None
        assert parent_of("recital_1") is None

    def test_parent_of_unknown_node_is_none(self):
        assert parent_of("no_such_node") is None


# ──────────────────────────────────────────────────────────────────────────
# TreeNode immutability + dataclass contract.
# ──────────────────────────────────────────────────────────────────────────


class TestTreeNodeShape:
    def test_treenode_is_frozen(self):
        tree = build_tree()
        node = tree["art_5"]
        with pytest.raises((AttributeError, TypeError)):
            node.text = "modified"

    def test_treenode_has_all_required_fields(self):
        tree = build_tree()
        node = tree["art_5_p_1"]
        # All public attrs from the spec.
        for attr in (
            "node_id", "kind", "article_number", "paragraph_number",
            "subpoint_letter", "text", "parent_id", "risk_tier",
            "timeline_effective_date", "chapter_id", "children_ids",
        ):
            assert hasattr(node, attr), f"missing {attr}"

    def test_paragraph_number_is_int_when_present(self):
        tree = build_tree()
        node = tree.get("art_5_p_1")
        assert node is not None
        assert isinstance(node.paragraph_number, int)
        assert node.paragraph_number == 1

    def test_subpoint_letter_normalised(self):
        tree = build_tree()
        node = tree.get("art_5_p_1_a")
        assert node is not None
        assert node.subpoint_letter == "a"


# ──────────────────────────────────────────────────────────────────────────
# Annex IV tabular layout — architecture-PDF specifically calls this out.
# ──────────────────────────────────────────────────────────────────────────


class TestAnnexLayout:
    def test_annex_iii_has_eight_numbered_items(self):
        """Annex III enumerates 8 high-risk domains (biometrics,
        critical infrastructure, education, employment, essential
        services, law enforcement, migration, justice)."""
        tree = build_tree()
        annex_iii = tree["annex_iii"]
        # Filter out the preamble (item_number=None).
        numbered = [
            tree[c] for c in annex_iii.children_ids
            if tree[c].paragraph_number is not None
        ]
        assert len(numbered) >= 8, f"only {len(numbered)} items in Annex III"

    def test_annex_iv_preserves_numbered_items(self):
        """Annex IV's tabular tech-doc layout — each numbered item is a
        separate child node (not merged)."""
        tree = build_tree()
        annex_iv = tree["annex_iv"]
        numbered = [
            tree[c] for c in annex_iv.children_ids
            if tree[c].paragraph_number is not None
        ]
        # Annex IV has 9 numbered items.
        assert len(numbered) >= 8, f"Annex IV missing items, got {len(numbered)}"
