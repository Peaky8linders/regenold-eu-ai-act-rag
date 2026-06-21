"""R144 fix #1 — emotion-recognition classification curated authoritative skip.

The 2026-06-11 "Stage-2 for all" directive bypassed the R111
authoritative-intercept Stage-2 skip, so Stage-2 (Opus) regenerates the
deterministic emotion cross-tier verdict into a narrower Article-5-only
answer (live: the R72 reconcile then prunes the Annex III(1)(c) + Article
50(3) sub-points). R144 restores the skip (env-reversible) and adds emotion
to the curated authoritative set.

Every gate must fire on 0 davidath rows so the deterministic bench stays
byte-identical.
"""
from __future__ import annotations

import pytest

from app.engines.graph_rag import (
    GraphContext,
    _curated_stage2_skip_enabled,
    _deterministic_answer,
    _detect_emotion_classification_inquiry,
    _is_curated_authoritative_intercept,
)


def _ctx_refs(question: str) -> tuple[str, list[str]]:
    ctx = GraphContext()
    ans = _deterministic_answer(question, ctx)
    refs = sorted({o.get("article") for o in ctx.obligations})
    return ans, refs


class TestR144EmotionDetector:
    @pytest.mark.parametrize(
        "q",
        [
            "Are AI systems for emotion recognition always prohibited under the EU AI Act?",
            "Is emotion recognition by an AI system permitted in a retail shop, or is it prohibited?",
            "Are emotion recognition systems high-risk?",
            "Is emotion recognition ever allowed?",
            "Is emotion inference categorically banned?",
            "What risk tier does emotion detection fall into?",
        ],
    )
    def test_detector_fires_on_classification_ask(self, q):
        assert _detect_emotion_classification_inquiry(q) is True

    @pytest.mark.parametrize(
        "q",
        [
            # scenario shape — stays on the scenario-classifier path
            "We are a hospital deploying emotion recognition to monitor staff stress. Is this allowed?",
            "We are a provider of an emotion recognition system. What are our obligations?",
            "Our company uses emotion recognition in classrooms.",
            # obligation ask, not classification — Stage-2 may polish
            "What does Article 50 require for emotion recognition systems?",
            # unrelated
            "What is a deployer?",
            "What are the transparency obligations for high-risk AI?",
        ],
    )
    def test_detector_no_false_positive(self, q):
        assert _detect_emotion_classification_inquiry(q) is False

    def test_multiturn_uses_latest_turn(self):
        # A prior turn about emotion must not flip a later non-emotion turn.
        q = "Conversation so far:\nemotion recognition prohibited?\nLatest question:\nWhat is a deployer?"
        assert _detect_emotion_classification_inquiry(q) is False


class TestR144CuratedCoverage:
    def test_curated_covers_emotion_classification(self):
        assert _is_curated_authoritative_intercept(
            "Are AI systems for emotion recognition always prohibited?"
        ) is True

    def test_curated_false_on_emotion_obligation(self):
        assert _is_curated_authoritative_intercept(
            "What does Article 50 require for emotion recognition systems?"
        ) is False


class TestR144EnvGate:
    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_CURATED_STAGE2_SKIP", raising=False)
        assert _curated_stage2_skip_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF"])
    def test_disabled(self, monkeypatch, val):
        monkeypatch.setenv("REGENOLD_CURATED_STAGE2_SKIP", val)
        assert _curated_stage2_skip_enabled() is False


class TestR144DeterministicVerdictIsCrossTier:
    def test_emotion_always_answer_maps_all_three_tiers(self):
        ans, refs = _ctx_refs(
            "Are AI systems for emotion recognition always prohibited under the EU AI Act?"
        )
        low = ans.lower()
        # prohibited tier
        assert "article 5" in low or "art. 5" in low
        assert "workplace" in low and ("education" in low or "educational" in low)
        # high-risk tier elsewhere
        assert "high-risk" in low or "high risk" in low
        assert "annex iii" in low
        # transparency tier
        assert "article 50" in low or "art. 50" in low
        # must NOT be a bare prohibition-only answer
        assert "not categorically prohibited" in low or "not always" in low
        # refs carry the cross-tier set
        assert "Art. 5" in refs and "Annex III" in refs and "Art. 50" in refs


class TestR144DavidathByteIdentical:
    """The curated gate + emotion detector MUST fire on 0 davidath rows so the
    deterministic bench is byte-identical (route gates + Stage-2 skip never
    trigger on any davidath question)."""

    def test_zero_firings_on_davidath(self):
        from evals.bench import dataset

        qa_qs = [(it.get("question") or "") for it in dataset.load_qa_pairs()]
        scen_qs = [dataset.scenario_to_question(s) for s in dataset.load_scenarios()]
        all_qs = qa_qs + scen_qs
        curated_fires = [q for q in all_qs if _is_curated_authoritative_intercept(q)]
        emo_fires = [q for q in all_qs if _detect_emotion_classification_inquiry(q)]
        assert curated_fires == [], f"curated gate fired on davidath: {curated_fires[:5]}"
        assert emo_fires == [], f"emotion detector fired on davidath: {emo_fires[:5]}"
