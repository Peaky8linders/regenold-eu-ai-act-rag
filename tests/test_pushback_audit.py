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
            # Leading confirmation family (R377)
            "So the derogation applies and we are exempt, correct?",
            "Our system only does preparatory work, so we are exempt, right?",
            "Confirm that we have no obligations under Article 16.",
            "We have no obligations under Chapter III, agreed?",
            "That is not what the regulation says.",
        ],
    )
    def test_challenge_turns_detected(self, challenge_text: str) -> None:
        assert is_challenge_turn(challenge_text) is True

    @pytest.mark.parametrize(
        "ordinary_text",
        [
            "What is an AI system under Article 3(1)?",
            "Is it correct that providers must maintain technical documentation?",
            "Can you confirm whether Annex III applies to CV screening?",
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

    def test_v2_default_is_on(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_PROMPT_V2", raising=False)
        assert _prompt_v2_enabled() is True

    def test_v2_clause_selection(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_PROMPT_V2", "1")
        assert "<reasoning_scratchpad>" in user_challenge_brevity_clause()
        assert "LEGAL VERSION:" in user_answer_coverage_clause()

        monkeypatch.setenv("REGENOLD_PROMPT_V2", "0")
        assert "<reasoning_scratchpad>" not in user_challenge_brevity_clause()
        assert "LEGAL VERSION:" not in user_answer_coverage_clause()
