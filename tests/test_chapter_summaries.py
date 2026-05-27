"""R66-E Phase 2a — Hierarchical Chapter Community Summary tests.

Validates:

* All 13 chapters (I-XIII) have a summary AND primary_anchors entry.
* Each summary is in [80, 350] chars, regulator-voice, no meta-talk.
* Each primary_anchor resolves in ARTICLE_EXISTENCE.
* Every article in ARTICLE_EXISTENCE maps to a chapter via the
  canonical ranges (cross-validates against the eu_ai_act_corpus
  ARTICLE_CHAPTER fix from Phase 1).
* ``chapter_for_query`` returns the right chapter on broad shapes,
  ``None`` on vague / off-topic inputs, and honours the intent label.
"""
from __future__ import annotations

import pytest


# ── Module loads cleanly ─────────────────────────────────────────────────


class TestModuleLoad:
    """Smoke test: the module's import-time _self_check() passed."""

    def test_module_imports(self):
        from app.data import chapter_summaries
        assert hasattr(chapter_summaries, "CHAPTER_SUMMARY")
        assert hasattr(chapter_summaries, "CHAPTER_PRIMARY_ANCHORS")
        assert hasattr(chapter_summaries, "chapter_for_query")


# ── 13-chapter coverage ─────────────────────────────────────────────────


class TestChapterCoverage:
    """Every chapter I-XIII has a summary AND primary anchors."""

    EXPECTED_CHAPTERS = ("I", "II", "III", "IV", "V", "VI", "VII",
                         "VIII", "IX", "X", "XI", "XII", "XIII")

    def test_all_13_chapters_have_summaries(self):
        from app.data.chapter_summaries import CHAPTER_SUMMARY
        assert len(CHAPTER_SUMMARY) == 13
        for ch in self.EXPECTED_CHAPTERS:
            assert ch in CHAPTER_SUMMARY, f"missing summary for chapter {ch}"

    def test_all_13_chapters_have_primary_anchors(self):
        from app.data.chapter_summaries import CHAPTER_PRIMARY_ANCHORS
        assert len(CHAPTER_PRIMARY_ANCHORS) == 13
        for ch in self.EXPECTED_CHAPTERS:
            assert ch in CHAPTER_PRIMARY_ANCHORS
            assert CHAPTER_PRIMARY_ANCHORS[ch], (
                f"chapter {ch} has empty primary_anchors"
            )


# ── Summary length budget ─────────────────────────────────────────────────


class TestSummaryLength:
    """Each summary fits the 80-350 char window for the wire 600-char cap."""

    def test_summary_length_in_range(self):
        from app.data.chapter_summaries import CHAPTER_SUMMARY
        for ch, text in CHAPTER_SUMMARY.items():
            n = len(text)
            assert 80 <= n <= 350, (
                f"Chapter {ch} summary length {n} out of [80, 350]"
            )

    def test_summary_no_metatalk_about_section(self):
        """Summaries should avoid phrases that read as meta-commentary."""
        from app.data.chapter_summaries import CHAPTER_SUMMARY
        forbidden = ("this chapter", "this section", "in this chapter",
                     "this regulation chapter")
        for ch, text in CHAPTER_SUMMARY.items():
            low = text.lower()
            for f in forbidden:
                assert f not in low, (
                    f"Chapter {ch} summary contains meta-phrase {f!r}"
                )

    def test_summary_no_drifty_dates(self):
        """Summaries don't carry drifty dates — article-level KB owns those.

        "Regulation 2024/1689" is the regulation's official CELEX
        identifier and is permitted; the year of an Omnibus event or a
        staged-applicability cliff is NOT, because Omnibus dates have
        drifted and re-drifted across rounds.
        """
        from app.data.chapter_summaries import CHAPTER_SUMMARY
        import re
        # Calendar-style date forms (full month names) and explicit
        # year-only mentions OTHER than the canonical 2024/1689
        # regulation identifier.
        month_re = re.compile(
            r"\b(January|February|March|April|May|June|July|"
            r"August|September|October|November|December)\b",
            re.IGNORECASE,
        )
        # Allow "2024/1689" (or "(EU) 2024/1689" or "Regulation 2024/1689").
        # Disallow standalone year mentions like "2 December 2027".
        for ch, text in CHAPTER_SUMMARY.items():
            assert month_re.search(text) is None, (
                f"Chapter {ch} summary mentions a calendar month — "
                "dates belong in article KB stubs"
            )
            # Find standalone years not part of "2024/1689".
            cleaned = text.replace("2024/1689", "")
            stray = re.search(r"\b(202[5-9]|20[3-9]\d)\b", cleaned)
            assert stray is None, (
                f"Chapter {ch} summary contains stray year "
                f"{stray.group()!r}"
            )


# ── Anchor validity ─────────────────────────────────────────────────────


class TestAnchorValidity:
    """Every primary_anchor resolves in ARTICLE_EXISTENCE."""

    def test_every_anchor_in_article_existence(self):
        from app.data.article_existence import ARTICLE_EXISTENCE
        from app.data.chapter_summaries import CHAPTER_PRIMARY_ANCHORS
        for ch, anchors in CHAPTER_PRIMARY_ANCHORS.items():
            for a in anchors:
                assert a in ARTICLE_EXISTENCE, (
                    f"Chapter {ch} anchor {a!r} not in ARTICLE_EXISTENCE"
                )


# ── Chapter coverage of every article ───────────────────────────────────


class TestArticleChapterCoverage:
    """Every Art. 1-113 maps to exactly one chapter via ARTICLE_CHAPTER —
    cross-validates the Phase-1 fix.
    """

    def test_every_article_maps_to_a_chapter(self):
        from app.data.eu_ai_act_corpus import ARTICLE_CHAPTER
        from app.data.chapter_summaries import CHAPTER_SUMMARY
        for n in range(1, 114):
            key = f"Art. {n}"
            ch = ARTICLE_CHAPTER.get(key)
            assert ch in CHAPTER_SUMMARY, (
                f"{key} maps to chapter {ch!r} which has no summary"
            )

    def test_chapter_primary_anchors_land_in_chapter_iii_high_risk(self):
        """Chapter III's primary anchors must all be Arts 6-49."""
        from app.data.chapter_summaries import CHAPTER_PRIMARY_ANCHORS
        for anchor in CHAPTER_PRIMARY_ANCHORS["III"]:
            n = int(anchor.split()[-1])
            assert 6 <= n <= 49, (
                f"Chapter III anchor {anchor!r} ({n}) outside 6-49 range"
            )

    def test_chapter_xiii_primary_anchor_is_final_provision(self):
        """Chapter XIII covers final provisions Arts 102-113."""
        from app.data.chapter_summaries import CHAPTER_PRIMARY_ANCHORS
        for anchor in CHAPTER_PRIMARY_ANCHORS["XIII"]:
            n = int(anchor.split()[-1])
            assert 102 <= n <= 113, (
                f"Chapter XIII anchor {anchor!r} ({n}) outside 102-113"
            )


# ── chapter_for_query heuristic ─────────────────────────────────────────


class TestChapterForQueryBroadKeywords:
    """Broad-keyword shapes map to the canonical chapter."""

    def test_prohibited_practices_routes_to_ii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("What are the prohibited AI practices?") == "II"

    def test_high_risk_routes_to_iii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("Tell me about high-risk AI systems") == "III"
        assert chapter_for_query("How do I do high-risk classification?") == "III"

    def test_transparency_routes_to_iv(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query(
            "What are the transparency obligations?"
        ) == "IV"

    def test_gpai_routes_to_v(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query(
            "What is a general-purpose AI model?"
        ) == "V"

    def test_sandbox_routes_to_vi(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("Tell me about regulatory sandboxes") == "VI"

    def test_ai_office_routes_to_vii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("What is the AI Office?") == "VII"

    def test_penalties_routes_to_xii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("What is the maximum fine?") == "XII"
        assert chapter_for_query("administrative fines under the AI Act") == "XII"

    def test_digital_omnibus_routes_to_xiii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query(
            "What does the Digital Omnibus change?"
        ) == "XIII"

    def test_entry_into_force_routes_to_xiii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("When is the entry into force?") == "XIII"

    def test_serious_incident_routes_to_ix(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query(
            "How does serious incident reporting work?"
        ) == "IX"


class TestChapterForQueryIntentFallback:
    """When no broad keyword fires, the intent label provides the chapter."""

    def test_penalty_intent_routes_to_xii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("vague question", intent_label="penalty_inquiry") == "XII"

    def test_risk_intent_routes_to_iii(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("vague", intent_label="risk_classification") == "III"

    def test_sandbox_intent_routes_to_vi(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("vague", intent_label="sandbox") == "VI"

    def test_gpai_intent_routes_to_v(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("vague", intent_label="gpai_systemic") == "V"


class TestChapterForQueryNonMatch:
    """Vague / off-topic questions return None."""

    def test_short_off_topic_returns_none(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("Hello") is None

    def test_off_topic_intent_returns_none(self):
        from app.data.chapter_summaries import chapter_for_query
        assert chapter_for_query("Hello", intent_label="out_of_scope") is None
        assert chapter_for_query("Hello", intent_label="other") is None

    def test_none_question_with_no_intent(self):
        from app.data.chapter_summaries import chapter_for_query
        # Empty question + no intent → None.
        assert chapter_for_query("", intent_label=None) is None

    def test_specific_article_still_returns_a_chapter_if_keyword_hits(self):
        """``"Annex III"`` is a broad keyword AND tags Chapter III — by
        design (chapter_for_query is a heuristic, not a router)."""
        from app.data.chapter_summaries import chapter_for_query
        # The chapter heuristic returns III for any "Annex III" mention
        # — that is the intended behaviour because Annex III IS the
        # high-risk-classification annex.
        assert chapter_for_query("What is Annex III?") == "III"


# ── Public helper API ───────────────────────────────────────────────────


class TestPublicHelpers:
    def test_summary_for_chapter_returns_text(self):
        from app.data.chapter_summaries import summary_for_chapter
        text = summary_for_chapter("II")
        assert text is not None
        assert "prohibited" in text.lower() or "Article 5" in text

    def test_summary_for_unknown_chapter_returns_none(self):
        from app.data.chapter_summaries import summary_for_chapter
        assert summary_for_chapter("XIV") is None
        assert summary_for_chapter("") is None

    def test_primary_anchors_for_chapter_returns_tuple(self):
        from app.data.chapter_summaries import primary_anchors_for_chapter
        anchors = primary_anchors_for_chapter("II")
        assert isinstance(anchors, tuple)
        assert "Art. 5" in anchors

    def test_primary_anchors_for_unknown_chapter_returns_empty(self):
        from app.data.chapter_summaries import primary_anchors_for_chapter
        assert primary_anchors_for_chapter("XIV") == ()


# ── R34 P0 OOS regression preservation ───────────────────────────────────


class TestNoOOSLeak:
    """The chapter heuristic must NOT route off-topic English questions
    to a chapter — they should remain None so the scope-gate's
    refusal path runs.
    """

    OOS_QUERIES = (
        "When did the queen withdraw from public life?",
        "Birth certificate processing time in France?",
        "I want to suspend my Netflix subscription.",
        "Designate as your favourite musician?",
        "What is your favourite colour?",
        "Tell me a joke about dogs.",
        "How do I bake a chocolate cake?",
    )

    @pytest.mark.parametrize("q", OOS_QUERIES)
    def test_off_topic_question_returns_none(self, q):
        from app.data.chapter_summaries import chapter_for_query
        # Without a relevant intent, off-topic should be None.
        # ``out_of_scope`` is the intent the classifier would emit;
        # other intent labels should also not over-route on these
        # off-topic shapes — but this test pins the no-intent case.
        result = chapter_for_query(q)
        assert result is None, (
            f"OOS question {q!r} routed to chapter {result!r}; the "
            "chapter heuristic must not flip off-topic queries in-scope."
        )


# ── candidate_chapters_for_query (PageIndex pre-router) ───────────────────


class TestCandidateChaptersForQuery:
    """Validate the pre-retrieval chapter router added for the PageIndex
    hierarchical-filter optimisation.
    """

    def test_high_risk_query_routes_to_chapter_iii(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query(
            "What are the requirements for high-risk AI providers?"
        )
        assert "III" in result, f"Expected III; got {result}"

    def test_prohibition_query_routes_to_chapter_ii(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query(
            "What AI practices are prohibited under the regulation?"
        )
        assert "II" in result, f"Expected II; got {result}"

    def test_gpai_query_routes_to_chapter_v(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query(
            "What obligations apply to general-purpose AI model providers?"
        )
        assert "V" in result, f"Expected V; got {result}"

    def test_penalty_query_routes_to_chapter_xii(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query("What are the maximum administrative fines?")
        assert "XII" in result, f"Expected XII; got {result}"

    def test_intent_label_extends_routing(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query(
            "Is this system in scope?", intent_label="risk_assessment"
        )
        assert "III" in result, f"Expected III from intent; got {result}"

    def test_broad_query_returns_empty(self) -> None:
        """A broad, multi-chapter question must return [] so full BM25 runs."""
        from app.data.chapter_summaries import candidate_chapters_for_query
        # Fires ≥ 4 distinct chapter markers: prohibited (II), high-risk (III),
        # general-purpose AI (V), penalties (XII), post-market monitoring (IX),
        # regulatory sandbox (VI) → scope guard (≥ 4) fires → [].
        result = candidate_chapters_for_query(
            "What are the prohibited AI practices, high-risk obligations, "
            "general-purpose AI model duties, penalties, post-market monitoring "
            "requirements, and regulatory sandbox rules under the AI Act?"
        )
        assert result == [], (
            f"Broad multi-chapter query should return []; got {result}"
        )

    def test_empty_query_returns_empty(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        assert candidate_chapters_for_query("") == []

    def test_oos_query_returns_empty(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query("How do I bake a chocolate cake?")
        assert result == [], f"OOS query should return []; got {result}"

    def test_returns_sorted_list(self) -> None:
        from app.data.chapter_summaries import candidate_chapters_for_query
        result = candidate_chapters_for_query(
            "What are prohibited practices for general-purpose AI?"
        )
        assert result == sorted(result), "Output must be sorted"
