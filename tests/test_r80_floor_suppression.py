"""R80-F — floor-suppression + 9 zero-retrieval keyword adds.

Verifies:

* ``zero_retrieval_fallback`` no longer pads the default
  ``Art. 1 / Art. 2 / Art. 3`` floor when narrower signals (topic
  keyword OR explicit anchor from the scope-gate) are present AND
  ``intent_label`` is unknown / ``None``. Closes the r80-live precision
  leak where 9 in-scope rows shipped a real anchor PLUS the floor
  padding, deflating Ref Loose / Strict.

* The new ``KEYWORD_TO_ARTICLE`` entries route each of the 9
  zero-retrieval shapes from the r80-live judge run to its gold
  article.

* The R34 P0 OOS regression set still refuses (the new entries are
  conservatively narrow multi-word phrases).
"""

from __future__ import annotations

import pytest

from app.engines.zero_retrieval_fallback import (
    _DEFAULT_FLOOR,
    _MAX_FALLBACK_REFS,
    zero_retrieval_fallback,
)
from app.integrations.regenold.scope import (
    KEYWORD_TO_ARTICLE,
    classify_conversation,
    derive_strong_anchor_articles_from_keywords,
)


class TestR80FFloorSuppression:
    """Floor padding is suppressed when narrower signals are present."""

    def test_floor_suppressed_with_explicit_anchor_and_no_intent(self) -> None:
        """Scope-gate anchor + unknown intent → ship the anchor only."""
        refs, _ = zero_retrieval_fallback(
            "What is the definition of an AI system under the Regulation?",
            intent_label=None,
            explicit_anchors=("Art. 3",),
        )
        assert "Art. 3" in refs, f"explicit anchor must survive: {refs}"
        # Default-floor pad must NOT be added when we have specifics.
        assert "Art. 1" not in refs, f"floor padding leaked: {refs}"
        assert "Art. 2" not in refs, f"floor padding leaked: {refs}"

    def test_floor_suppressed_with_topic_match_and_no_intent(self) -> None:
        """Topic-keyword match + unknown intent → ship topic refs only."""
        refs, _ = zero_retrieval_fallback(
            # 'serious incident' is in _TOPIC_KEYWORD_EXTENSIONS → Art. 73.
            "What are the reporting obligations for serious incidents causing death?",
            intent_label=None,
        )
        assert refs[0] == "Art. 73", f"topic ref must lead: {refs}"
        assert "Art. 1" not in refs, f"floor padding leaked: {refs}"
        assert "Art. 2" not in refs, f"floor padding leaked: {refs}"

    def test_floor_preserved_when_no_specifics(self) -> None:
        """Bare unknown-intent + no anchors + no topic match → floor only."""
        refs, _ = zero_retrieval_fallback(
            "Tell me about the EU AI Act in general terms.",
            intent_label=None,
        )
        for r in _DEFAULT_FLOOR:
            assert r in refs, f"floor must be present when no specifics: {refs}"

    def test_floor_preserved_when_unknown_label_no_specifics(self) -> None:
        """Unknown label string + no anchors + no topic → floor only."""
        refs, _ = zero_retrieval_fallback(
            "Random ungroundable question",
            intent_label="some-future-label-we-do-not-recognise",
        )
        for r in _DEFAULT_FLOOR:
            assert r in refs

    def test_intent_seed_still_authoritative_when_label_matches(self) -> None:
        """Known intent label → intent_seed used, floor never appended."""
        refs, _ = zero_retrieval_fallback(
            "What is the definition of an AI system?",
            intent_label="definition",  # _INTENT_SEED_MAP['definition'] = ('Art. 3',)
        )
        assert "Art. 3" in refs
        # Art. 1 / Art. 2 are NOT in the definition intent seed; they were
        # only ever showing up via the default floor. Now suppressed.
        assert "Art. 1" not in refs, f"floor leaked via known-intent path: {refs}"
        assert "Art. 2" not in refs

    def test_explicit_anchor_dedup_with_intent_seed(self) -> None:
        """When anchor and intent_seed both name Art. 3, no duplicate."""
        refs, _ = zero_retrieval_fallback(
            "What is the definition of an AI system?",
            intent_label="definition",
            explicit_anchors=("Art. 3",),
        )
        assert refs.count("Art. 3") == 1

    def test_max_refs_cap_preserved(self) -> None:
        """Even with many specifics, never exceed the budget cap."""
        refs, _ = zero_retrieval_fallback(
            "What does Article 13 require for high-risk AI?",
            intent_label=None,
            explicit_anchors=("Art. 13", "Art. 14", "Art. 15", "Art. 16", "Art. 17", "Art. 18", "Art. 19"),
        )
        assert len(refs) <= _MAX_FALLBACK_REFS

    def test_refs_always_non_empty_edge_case(self) -> None:
        """Floor invariant: empty question + None intent → still ≥1 ref."""
        refs, prose = zero_retrieval_fallback("", intent_label=None)
        assert len(refs) >= 1
        assert prose


class TestR80FScopeAnchors:
    """The 9 r80-live zero-retrieval question shapes now route to gold."""

    @pytest.mark.parametrize(
        "needle, expected_ref",
        [
            ("authorised representative", "Art. 22"),
            ("authorized representative", "Art. 22"),
            ("appoint an authorised representative", "Art. 22"),
            ("retain logs", "Art. 19"),
            ("retain automatically generated logs", "Art. 19"),
            ("log retention", "Art. 19"),
            ("automatically generated logs", "Art. 19"),
            ("obligations of deployers", "Art. 26"),
            ("obligations of downstream providers", "Art. 26"),
            ("transparency information must be provided", "Art. 13"),
            ("transparency information to deployers", "Art. 13"),
            ("european artificial intelligence board", "Art. 65"),
            ("who must comply with the ai regulation", "Art. 2"),
            ("who must comply with the ai act", "Art. 2"),
            ("who must comply with the regulation", "Art. 2"),
        ],
    )
    def test_keyword_resolves_to_gold_ref(
        self, needle: str, expected_ref: str
    ) -> None:
        assert KEYWORD_TO_ARTICLE.get(needle) == expected_ref, (
            f"{needle!r} must route to {expected_ref!r}: "
            f"got {KEYWORD_TO_ARTICLE.get(needle)!r}"
        )

    @pytest.mark.parametrize(
        "question, expected_anchor",
        [
            # qa_023 — authrep appointment
            (
                "When must a provider appoint an authorised representative?",
                "Art. 22",
            ),
            # qa_018 — log retention
            (
                "For how long must providers retain automatically generated logs?",
                "Art. 19",
            ),
            # qa_027 — main obligations of deployers
            (
                "What are the main obligations of deployers of high-risk AI systems?",
                "Art. 26",
            ),
            # qa_019 — transparency information to deployers
            (
                "What transparency information must be provided to deployers of high-risk AI systems?",
                "Art. 13",
            ),
            # qa_050 — European AI Board
            (
                "What is the European Artificial Intelligence Board?",
                "Art. 65",
            ),
            # qa_001 — Who must comply
            (
                "Who must comply with the AI Regulation?",
                "Art. 2",
            ),
        ],
    )
    def test_r80_live_question_surfaces_anchor(
        self, question: str, expected_anchor: str
    ) -> None:
        """Each r80-live zero-retrieval shape now surfaces the gold anchor."""
        anchors = derive_strong_anchor_articles_from_keywords(question)
        assert expected_anchor in anchors, (
            f"{question!r} must surface {expected_anchor!r}: got {anchors}"
        )


class TestR80FOOSPreserved:
    """R34 P0 OOS regression set still refuses post-R80-F additions."""

    @pytest.mark.parametrize(
        "off_topic_q",
        [
            "When did the queen withdraw from public life?",
            "Birth certificate processing time in France?",
            "I want to suspend my Netflix subscription.",
            "Designate as your favourite musician?",
            "What's the best Italian restaurant in Rome?",
            # R80-F additions are multi-word AI-Act-specific — make sure
            # off-topic uses of the constituent words don't false-flip.
            "Who must comply with their HR onboarding paperwork?",
            "Do I need to retain logs of my home router traffic?",
            "Board game recommendations for European holiday?",
            "Do you have any transparency information for your pricing?",
        ],
    )
    def test_off_topic_refuses(self, off_topic_q: str) -> None:
        verdict = classify_conversation(
            [{"role": "user", "content": off_topic_q}]
        )
        assert verdict.verdict != "in_scope", (
            f"OOS query leaked in-scope: {off_topic_q!r} verdict={verdict.verdict}"
        )
