"""R118 — Opus 4.8 usage optimisations.

REC-1: ``REGENOLD_COMPLEX_GATE_WIDE`` widens ``is_complex_question`` to fire
on regulatory difficulty (not just sentence count), routing genuinely-hard
SINGLE-sentence questions to Opus 4.8. Default OFF → byte-identical routing.
Also fixes the latent ``always\\s+prohibit\\b`` boundary bug.

REC-4: the Anthropic-SDK Stage-2 path now floors ``max_tokens`` to 1024
(parity with the wrapper-path R112.2 floor), so a Pro-tier Opus complex
answer is not capped at the config default 384 and silently truncated.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.engines import question_complexity as qc

# The four genuinely-hard SINGLE-sentence Antifragile questions that the
# audit found route to Sonnet today (one sentence → no multi-phrase trigger)
# but warrant Opus 4.8 deliberation.
_HARD_SINGLE_SENTENCE = {
    "q12_always_prohibited": (
        "Are AI systems intended for emotion recognition from biometric data "
        "always prohibited?"
    ),
    "q15_biometric_triage": (
        "Can a hospital use an AI system to sort patients based on their "
        "biometric data to determine priority for an experimental clinical trial?"
    ),
    "q19_workplace_emotion": (
        "A pharmaceutical company wants to use an AI system to monitor the "
        "emotions and stress levels of their manufacturing line workers to "
        "improve efficiency. Is this allowed?"
    ),
    "q20_robotic_surgery": (
        "Is an AI system intended to be used as a safety component in robotic "
        "surgery considered high-risk under the AI Act?"
    ),
}


class TestR118ComplexGateWideDefaultOff:
    """Default OFF preserves byte-identical routing (the bench/live guard)."""

    def test_hard_single_sentence_stays_sonnet_when_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
        for name, q in _HARD_SINGLE_SENTENCE.items():
            assert qc.is_complex_question(q) is False, name

    def test_always_prohibited_stays_false_when_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
        assert qc.is_complex_question(
            "Is emotion recognition always prohibited?"
        ) is False


class TestR118ComplexGateWideOn:
    """With the env ON, the hard single-sentence questions route to Opus."""

    def test_hard_single_sentence_fires_when_on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_COMPLEX_GATE_WIDE", "1")
        for name, q in _HARD_SINGLE_SENTENCE.items():
            assert qc.is_complex_question(q) is True, name

    def test_always_prohibited_boundary_bug_fixed_when_on(self, monkeypatch):
        # The latent ``always\s+prohibit\b`` bug: the trailing \b blocked the
        # inflected "prohibit*ed*". The WIDE pattern uses ``prohibit\w*``.
        monkeypatch.setenv("REGENOLD_COMPLEX_GATE_WIDE", "1")
        assert qc.is_complex_question("Is X always prohibited?") is True
        assert qc.is_complex_question("Is X ever prohibited?") is True

    def test_general_purpose_model_fires_when_on(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_COMPLEX_GATE_WIDE", "1")
        assert qc.is_complex_question(
            "What obligations apply to our general-purpose AI model?"
        ) is True


class TestR118ComplexGateWideInvariants:
    """The widening never touches the baseline-complex set or simple QA."""

    def test_baseline_multiphrase_complex_in_both_modes(self, monkeypatch):
        q = ("We are a hospital deploying an X-ray tumor detector. Is it "
             "high-risk, and what conformity assessment is required?")
        monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
        assert qc.is_complex_question(q) is True
        monkeypatch.setenv("REGENOLD_COMPLEX_GATE_WIDE", "1")
        assert qc.is_complex_question(q) is True

    def test_simple_definitional_stays_simple_in_both_modes(self, monkeypatch):
        q = "What is the definition of a provider?"
        monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
        assert qc.is_complex_question(q) is False
        monkeypatch.setenv("REGENOLD_COMPLEX_GATE_WIDE", "1")
        assert qc.is_complex_question(q) is False

    def test_empty_question_false_in_both_modes(self, monkeypatch):
        for val in (None, "1"):
            if val is None:
                monkeypatch.delenv("REGENOLD_COMPLEX_GATE_WIDE", raising=False)
            else:
                monkeypatch.setenv("REGENOLD_COMPLEX_GATE_WIDE", val)
            assert qc.is_complex_question("") is False
            assert qc.is_complex_question("   ") is False


class TestR118SdkMaxTokensFloor:
    """REC-4 — the Anthropic-SDK Stage-2 path floors max_tokens to 1024."""

    def _mock_client(self, captured: dict) -> MagicMock:
        client = MagicMock()

        def fake_create(**kwargs):
            captured.update(kwargs)
            resp = MagicMock()
            resp.content = [MagicMock(text="ok")]
            resp.stop_reason = "end_turn"
            return resp

        client.messages.create.side_effect = fake_create
        return client

    def test_floor_applied_to_low_max_tokens(self, monkeypatch):
        from app.engines import graph_rag
        captured: dict = {}
        monkeypatch.setattr(
            graph_rag, "_get_anthropic_client",
            lambda: self._mock_client(captured),
        )
        graph_rag._anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=384, temperature=0.0,
        )
        assert captured.get("max_tokens") == 1024

    def test_high_max_tokens_passes_through(self, monkeypatch):
        from app.engines import graph_rag
        captured: dict = {}
        monkeypatch.setattr(
            graph_rag, "_get_anthropic_client",
            lambda: self._mock_client(captured),
        )
        graph_rag._anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=2048, temperature=0.0,
        )
        assert captured.get("max_tokens") == 2048


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
