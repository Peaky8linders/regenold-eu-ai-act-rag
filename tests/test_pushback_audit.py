"""Regression and audit tests for the pushback line and V2 prompt family."""

from __future__ import annotations

import pytest

from app.data.graph_rag_prompts import (
    _CHALLENGE_MARKERS,
    _CHALLENGE_PATTERNS,
    _prompt_v2_enabled,
    is_challenge_turn,
    user_answer_coverage_clause,
    user_challenge_brevity_clause,
    user_ref_minimality_clause,
    user_subparagraph_attribution_clause,
)


_MT = (
    "Conversation so far:\nuser: Is our CV screener high-risk?\n"
    "assistant: Yes, under Annex III(4)(a).\nLatest question:\n"
)


class TestPushbackChallengeDetection:
    """Verifies that adversarial pushback turns are accurately detected without false-positives."""

    @pytest.mark.parametrize(
        "challenge_text",
        [
            "I don't think this is correct. Perhaps your answer contains hallucinations.",
            "You are wrong, Article 5(1)(f) does not apply here.",
            "That is not right. We are only doing biometric verification.",
            "I disagree with this assessment.",
            "Please correct your answer.",
            "Let's try again: What are the high-risk use cases?",
            # Leading confirmation family (R377). R379: these ratify or dispute a
            # PREVIOUS answer, so they are only challenges where a prior turn
            # exists - the route's ``Latest question:`` flatten marker.
            _MT + "So the derogation applies and we are exempt, correct?",
            _MT + "Our system only does preparatory work, so we are exempt, right?",
            _MT + "Confirm that we have no obligations under Article 16.",
            _MT + "We have no obligations under Chapter III, agreed?",
            _MT + "That is not what the regulation says.",
        ],
    )
    def test_challenge_turns_detected(self, challenge_text: str) -> None:
        assert is_challenge_turn(challenge_text) is True

    @pytest.mark.parametrize(
        "ordinary_text",
        [
            "What is an AI system under Article 3(1)?",
            "Is it correct that providers must maintain technical documentation?",
            # R379 - the port's negative case used "confirm whether", which dodged
            # the ratification pattern by one word. The real test is the Act's
            # own "confirm that" (Art. 3(36) / Annex III(1)(a)), which fired.
            "Can you confirm that Annex III applies to CV screening?",
            "We deploy biometric verification solely to confirm that a specific "
            "natural person is the person he or she claims to be. Is it high-risk?",
            "Does Article 6(3) provide an exemption for narrow procedural tasks?",
            "Please explain the obligations under Article 13.",
        ],
    )
    def test_ordinary_questions_not_flagged(self, ordinary_text: str) -> None:
        assert is_challenge_turn(ordinary_text) is False

    def test_multi_turn_history_isolation(self) -> None:
        history = (
            "Turn 1: What is high-risk AI?\n"
            "Answer: Systems in Annex III...\n"
            "Turn 2: You are wrong, check Article 5.\n"
            "Answer: Article 5 is prohibited...\n"
            "Latest question:\n"
            "What documentation must providers maintain?"
        )
        # Latest question is ordinary, so should not trigger challenge
        assert is_challenge_turn(history) is False


class TestV2PromptGating:
    """Verifies that REGENOLD_PROMPT_V2 properly toggles the prompt variants."""

    def test_v2_default_is_off(self, monkeypatch) -> None:
        """R379 - the port shipped ON on an unrecorded gate claim; the R379
        Bedrock A/B dropped one more gold head on the easy split (21 -> 22),
        so hard rule #8 puts it OFF until a powered re-run clears it."""
        monkeypatch.delenv("REGENOLD_PROMPT_V2", raising=False)
        assert _prompt_v2_enabled() is False

    def test_v2_clause_selection(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_PROMPT_V2", "1")
        assert "<reasoning_scratchpad>" in user_challenge_brevity_clause()
        assert "LEGAL VERSION:" in user_answer_coverage_clause()

        monkeypatch.setenv("REGENOLD_PROMPT_V2", "0")
        assert "<reasoning_scratchpad>" not in user_challenge_brevity_clause()
        assert "LEGAL VERSION:" not in user_answer_coverage_clause()
