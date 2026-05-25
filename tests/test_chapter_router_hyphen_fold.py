"""Chapter-router hyphen-fold — salvaged from PR #101 commits 37670c2 + ac8bef2.

The chapter pre-filter's content-marker scan did ASCII-literal matching, so
hyphenated terms never matched their space-form markers across the
:data:`_BROAD_KEYWORD_CHAPTER_MAP` and risk/domain marker scan in
``candidate_chapters_for_query`` (e.g. "deep-fake" missed Chapter IV
"deep fake", "market-surveillance" missed Chapter IX "market surveillance").

The davidath benchmark ships 90 U+2011 non-breaking hyphens; queries like
qa_030 / qa_042 / qa_064 / qa_068 / qa_080 fell back to coarse intent labels
and lost the gold article.

R79 added Unicode normalisation in ``_deterministic_parse`` /
``text_normalize.py`` but did NOT reach this module's
``_BROAD_KEYWORD_CHAPTER_MAP`` scan — different code layer.

This module pins the hyphen-fold + the corrected multi-word certificate
markers added in #101's deep-review hardening commit.
"""
from __future__ import annotations

import pytest

from app.data.chapter_summaries import (
    _BROAD_KEYWORD_CHAPTER_MAP,
    _fold_hyphens,
    candidate_chapters_for_query,
    chapter_for_query,
)


class TestFoldHyphens:
    """Hyphen-family chars must collapse to a single space; runs collapsed."""

    @pytest.mark.parametrize(
        "src, expected",
        [
            # ASCII hyphen-minus
            ("deep-fake", "deep fake"),
            # U+2011 non-breaking hyphen (davidath's primary form)
            ("deep‑fake", "deep fake"),
            # U+2010 hyphen
            ("deep‐fake", "deep fake"),
            # U+2013 en-dash
            ("deep–fake", "deep fake"),
            # U+2014 em-dash
            ("deep—fake", "deep fake"),
            # U+2212 minus
            ("deep−fake", "deep fake"),
            # Multi-token forms with mixed hyphenation
            ("market-surveillance", "market surveillance"),
            ("conformity-assessment", "conformity assessment"),
            ("post-market monitoring", "post market monitoring"),
            # Run-collapsing + leading/trailing whitespace
            ("  multiple‑spaces  ", "multiple spaces"),
            ("ALREADY-LOWER", "already lower"),
            ("UPPER WITH NO HYPHEN", "upper with no hyphen"),
        ],
    )
    def test_fold_normalises(self, src: str, expected: str) -> None:
        assert _fold_hyphens(src) == expected


class TestCandidateChaptersHyphenAware:
    """Hyphen-mismatched queries must route to the same chapter as the
    space-form. Each parametrised pair is a (hyphenated_query,
    space_form_query, expected_chapter) row from the PR-#101 commit
    description.
    """

    @pytest.mark.parametrize(
        "query, expected_chapter",
        [
            # PR #101: "deep-fake" missed Ch IV "deep fake" marker.
            ("What is a deep-fake under Article 50?", "IV"),
            ("What is a deep‑fake under Article 50?", "IV"),  # U+2011
            # PR #101: "market-surveillance" missed Ch IX.
            ("Who handles market-surveillance for AI?", "IX"),
            ("Who handles market‑surveillance for AI?", "IX"),
            # PR #101: "conformity-assessment" missed Ch III.
            ("What is conformity-assessment under the AI Act?", "III"),
            ("How does conformity‑assessment work?", "III"),
            # Multi-word certificate markers — PR #101 ac8bef2 fix
            # (replaced bare ``certificate`` with multi-word lifecycle
            # forms after deep-review marker-precision feedback).
            (
                "When can a notified body withdraw a certificate?",
                "III",
            ),
            ("Can the AI Office suspend a certificate?", "III"),
            (
                "What triggers withdrawal of a certificate?",
                "III",
            ),
        ],
    )
    def test_hyphenated_routes(
        self, query: str, expected_chapter: str
    ) -> None:
        chapters = candidate_chapters_for_query(query)
        assert expected_chapter in chapters, (
            f"Expected chapter {expected_chapter!r} in {chapters!r} "
            f"for query {query!r}"
        )


class TestPrecisionPreservation:
    """The hyphen-fold + new certificate markers must NOT broaden the
    chapter router on OOS / off-topic queries.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "Best Italian restaurant in Rome?",
            "When did the queen withdraw from public life?",
            "I want to suspend my Netflix subscription.",
            "Designate as your favourite musician?",
        ],
    )
    def test_oos_queries_dont_route_to_chapter_iii(self, query: str) -> None:
        # OOS queries SHOULD not pick up Chapter III via the bare-word
        # paths the deep-review feedback flagged. (The hyphen-fold helper
        # only normalises whitespace + lowercase + hyphen-family chars;
        # it cannot widen substring matches.)
        chapters = candidate_chapters_for_query(query)
        assert "III" not in chapters, (
            f"OOS query {query!r} should not route to Chapter III; "
            f"got {chapters!r}"
        )

    def test_certificate_in_noun_compound_does_not_fire(self) -> None:
        """The marker is ``withdraw a certificate`` (multi-word). A
        compound noun like ``"certificates of conformity"`` should NOT
        fire the Chapter III certificate route alone (other III markers
        like ``ce marking`` will route it correctly when applicable)."""
        # A bare "certificate" mention without the lifecycle verb must
        # not flip the route — the multi-word markers are the gate.
        chapters = candidate_chapters_for_query("The certificate hung on the wall.")
        # No CE marking / conformity etc. → no chapter III hit.
        # (The intent fallback for "" intent_label returns [].)
        assert "III" not in chapters


class TestBroadKeywordHyphenFold:
    """The first-pass broad-keyword scan in
    :data:`_BROAD_KEYWORD_CHAPTER_MAP` must also be hyphen-aware so an
    explicit, more-specific phrase like ``"entry-into-force"`` still
    wins its hard-coded chapter.
    """

    def test_broad_keyword_hyphen_fold(self) -> None:
        # The map has both ``"entry into force"`` and ``"entry-into-force"``
        # entries → Chapter XIII. Either form should resolve.
        assert chapter_for_query(
            "What is the entry-into-force date?",
        ) == "XIII"
        assert chapter_for_query(
            "What is the entry‑into‑force date?",
        ) == "XIII"
        assert chapter_for_query(
            "What is the entry into force date?",
        ) == "XIII"

    def test_broad_keyword_map_table_entries_unchanged(self) -> None:
        """Pinning — the table itself isn't touched by R88-salvage. If
        a future round modifies it the test will catch the drift so the
        salvage rationale is re-evaluated.
        """
        # Spot-check a few load-bearing entries.
        kw_to_chapter = dict(_BROAD_KEYWORD_CHAPTER_MAP)
        assert kw_to_chapter.get("entry into force") == "XIII"
        assert kw_to_chapter.get("entry-into-force") == "XIII"
