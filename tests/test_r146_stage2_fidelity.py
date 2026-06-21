"""R146 — Stage-2 fidelity guard (the intelligent Stage-1/Stage-2 combine).

The guard makes the deterministic Stage-1 draft the CONTENT source of truth:
when the QUESTION asks for a cross-tier classification AND the deterministic
verdict is cross-tier AND Opus polish drops a load-bearing risk tier, it FALLS
BACK to the complete deterministic verdict (or, mode=repair, re-injects the
dropped tier). On focused yes/no questions Opus narrowing the verdict is correct,
so the guard is a no-op. These tests pin:

* the pure-module tier detection + word-boundary precision,
* the classification-ask question gate,
* the env gates,
* every ``guard_cross_tier_polish`` action branch,
* the engine integration through ``_two_stage_generate`` (the only place the
  guard runs), incl. the byte-identical-under-``cli`` guarantee.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engines.graph_rag import GraphContext, _two_stage_generate
from app.engines.stage2_fidelity import (
    extract_tier_set,
    fidelity_guard_enabled,
    fidelity_mode,
    guard_cross_tier_polish,
    is_cross_tier_classification_ask,
)

# A multi-turn-shaped question whose LIVE turn is a cross-tier classification ask
# (forces Stage-2 AND triggers the classification-ask gate).
_MULTI_TURN_Q = (
    "Conversation so far:\nUser: Classify our retail emotion-analytics camera.\n"
    "Assistant: It depends on the deployment context.\n\n"
    "Latest question:\nWhat risk tier does it fall under, prohibited or high-risk?"
)

# A bare cross-tier classification ask (for the pure-module tests).
_CLS_Q = "Is this AI system prohibited, high-risk, or limited-risk?"

# A focused yes/no question — Opus narrowing is fine, guard must NOT act.
_YESNO_Q = "Is this AI system high-risk under the EU AI Act?"

# A complete cross-tier deterministic verdict (prohibited + high-risk + limited).
_CROSS_TIER_DRAFT = (
    "The system is not categorically prohibited under Article 5. "
    "In workplaces or education it is banned, but elsewhere it is high-risk "
    "under Annex III and Article 6. It also triggers Article 50 transparency "
    "duties toward exposed persons."
)


def _empty_ctx() -> GraphContext:
    return GraphContext()


# ── extract_tier_set — word-boundary precision ───────────────────────────────


class TestExtractTierSet:
    def test_all_three_tiers_detected(self) -> None:
        assert extract_tier_set(_CROSS_TIER_DRAFT) == {"prohibited", "high_risk", "limited"}

    def test_article_5_not_matched_inside_article_50(self) -> None:
        tiers = extract_tier_set("Article 50 applies to transparency.")
        assert "prohibited" not in tiers
        assert tiers == {"limited"}

    def test_article_5_subpoint_matches_prohibited(self) -> None:
        assert "prohibited" in extract_tier_set("Article 5(1)(f) bans this.")

    def test_annex_iii_high_risk(self) -> None:
        assert extract_tier_set("Annex III lists the use cases.") == {"high_risk"}

    def test_article_6_high_risk(self) -> None:
        assert extract_tier_set("Article 6 classifies it.") == {"high_risk"}

    def test_gpai_tier(self) -> None:
        assert extract_tier_set("Article 53 and Article 55 govern GPAI.") == {"gpai"}

    def test_art_short_form_matches(self) -> None:
        assert "prohibited" in extract_tier_set("Art. 5 prohibits it.")

    def test_no_tier(self) -> None:
        assert extract_tier_set("This is general regulatory prose.") == set()

    def test_empty(self) -> None:
        assert extract_tier_set("") == set()


# ── is_cross_tier_classification_ask — the question gate ─────────────────────


class TestClassificationAsk:
    @pytest.mark.parametrize(
        "q",
        [
            "Is this prohibited, high-risk, or limited-risk?",
            "Is the system prohibited or high-risk?",
            "What risk tier applies to this AI?",
            "Which risk category does it fall under?",
            "Are emotion recognition systems always prohibited?",
            "What risk level is an AI credit scorer?",
        ],
    )
    def test_classification_asks_fire(self, q) -> None:
        assert is_cross_tier_classification_ask(q) is True

    @pytest.mark.parametrize(
        "q",
        [
            "Is this AI system high-risk?",
            "What does Article 13 require?",
            "What are the obligations of deployers?",
            "How is an AI system defined?",
            "Is my chatbot subject to transparency duties?",
        ],
    )
    def test_focused_questions_do_not_fire(self, q) -> None:
        assert is_cross_tier_classification_ask(q) is False

    def test_empty(self) -> None:
        assert is_cross_tier_classification_ask("") is False


# ── env gates ────────────────────────────────────────────────────────────────


class TestEnvGates:
    def test_enabled_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_FIDELITY", raising=False)
        assert fidelity_guard_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF"])
    def test_disabled_by_env(self, monkeypatch, val) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", val)
        assert fidelity_guard_enabled() is False

    def test_mode_default_fallback(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_FIDELITY_MODE", raising=False)
        assert fidelity_mode() == "fallback"

    def test_mode_repair(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY_MODE", "repair")
        assert fidelity_mode() == "repair"

    def test_mode_unknown_falls_back_to_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY_MODE", "weird")
        assert fidelity_mode() == "fallback"


# ── guard_cross_tier_polish — action branches ────────────────────────────────


class TestGuardActions:
    def test_disabled_no_op(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "0")
        polished = "Some polished answer about Article 5 only."
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _CLS_Q)
        assert action == "disabled"
        assert out == polished

    def test_focused_question_not_classification_ask(self, monkeypatch) -> None:
        # A yes/no question — Opus narrowing the verdict is correct → no-op.
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        polished = "The system is high-risk under Annex III."
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _YESNO_Q)
        assert action == "not_classification_ask"
        assert out == polished

    def test_single_tier_draft_not_cross_tier(self) -> None:
        det = "Article 5 prohibits this practice outright."
        polished = "The practice is banned under Article 5."
        out, action = guard_cross_tier_polish(det, polished, _CLS_Q)
        assert action == "not_cross_tier"
        assert out == polished

    def test_complete_polish_shipped(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_FIDELITY", raising=False)
        polished = (
            "Not categorically prohibited under Article 5; high-risk under "
            "Annex III; triggers Article 50 transparency."
        )
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _CLS_Q)
        assert action == "complete"
        assert out == polished

    def test_dropped_tier_fallback_default(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        monkeypatch.delenv("REGENOLD_STAGE2_FIDELITY_MODE", raising=False)  # default fallback
        polished = "The system is not prohibited under Article 5."
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _CLS_Q)
        assert action == "fallback_tier_drop"
        assert out == _CROSS_TIER_DRAFT

    def test_dropped_tier_repair_mode(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY_MODE", "repair")
        # Polish kept prohibited (Article 5) + limited (Article 50) but DROPPED
        # the high-risk tier (Article 6 / Annex III).
        polished = (
            "The system is not categorically prohibited under Article 5. "
            "It triggers Article 50 transparency duties."
        )
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _CLS_Q)
        assert action.startswith("repaired:")
        assert "high_risk" in action
        assert "Article 50" in out  # polish preserved
        assert {"prohibited", "high_risk", "limited"} <= extract_tier_set(out)

    def test_verdict_flip_falls_back(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        polished = (
            "The system is prohibited under Article 5. It is also high-risk "
            "under Annex III and triggers Article 50."
        )
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _CLS_Q)
        assert action == "fallback_verdict_flip"
        assert out == _CROSS_TIER_DRAFT

    def test_conditional_prohibition_is_not_a_flip(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        polished = (
            "Not categorically prohibited under Article 5; only in workplaces "
            "is it prohibited, elsewhere high-risk under Annex III and "
            "Article 50 transparency applies."
        )
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, polished, _CLS_Q)
        assert action == "complete"
        assert out == polished

    def test_empty_polish_falls_back(self) -> None:
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, "   ", _CLS_Q)
        assert action == "fallback_empty_polish"
        assert out == _CROSS_TIER_DRAFT

    def test_empty_deterministic_no_op(self) -> None:
        out, action = guard_cross_tier_polish("", "polish", _CLS_Q)
        assert action == "not_cross_tier"
        assert out == "polish"

    def test_fail_soft_on_exception(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.engines.stage2_fidelity.extract_tier_set",
            lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        out, action = guard_cross_tier_polish(_CROSS_TIER_DRAFT, "polish text", _CLS_Q)
        assert action == "error"
        assert out == "polish text"


# ── engine integration through _two_stage_generate ───────────────────────────


class TestEngineIntegration:
    @pytest.fixture(autouse=True)
    def _wrapper_env(self, monkeypatch):
        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
        monkeypatch.setenv("REGENOLD_CURATED_STAGE2_SKIP", "1")

    def test_guard_fallback_default_ships_deterministic(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        monkeypatch.delenv("REGENOLD_STAGE2_FIDELITY_MODE", raising=False)
        incomplete_polish = "The system is not prohibited under Article 5."
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._deterministic_answer", return_value=_CROSS_TIER_DRAFT),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value=incomplete_polish,
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        # Guard fell back to the complete deterministic verdict → stage2_used False.
        assert not used
        assert answer == _CROSS_TIER_DRAFT
        assert {"prohibited", "high_risk", "limited"} <= extract_tier_set(answer)

    def test_guard_repair_mode_restores_tier(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY_MODE", "repair")
        incomplete_polish = (
            "The system is not categorically prohibited under Article 5. "
            "It triggers Article 50 transparency duties toward exposed persons."
        )
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._deterministic_answer", return_value=_CROSS_TIER_DRAFT),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value=incomplete_polish,
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert used
        assert {"prohibited", "high_risk", "limited"} <= extract_tier_set(answer)

    def test_complete_polish_ships_unchanged(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        complete_polish = (
            "Not categorically prohibited under Article 5; high-risk under "
            "Annex III and Article 6; Article 50 transparency duties apply."
        )
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._deterministic_answer", return_value=_CROSS_TIER_DRAFT),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value=complete_polish,
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert used
        assert answer == complete_polish

    def test_focused_question_ships_narrowed_polish(self, monkeypatch) -> None:
        # The live turn is a focused yes/no question → guard no-op → Opus's
        # narrowed (single-tier) polish ships even though the det draft is
        # cross-tier (the conciseness-preserving behaviour).
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        yesno_mt_q = (
            "Conversation so far:\nUser: We run a workplace analytics tool.\n"
            "Assistant: Noted.\n\nLatest question:\nIs it high-risk?"
        )
        narrowed_polish = "It is high-risk under Annex III and Article 6."
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._deterministic_answer", return_value=_CROSS_TIER_DRAFT),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value=narrowed_polish,
            ),
        ):
            answer, used = _two_stage_generate(yesno_mt_q, _empty_ctx())
        assert used
        assert answer == narrowed_polish  # not re-inflated to the cross-tier dump

    def test_guard_disabled_ships_incomplete_polish(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "0")
        incomplete_polish = "The system is not prohibited under Article 5."
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._deterministic_answer", return_value=_CROSS_TIER_DRAFT),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value=incomplete_polish,
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert used
        assert answer == incomplete_polish

    def test_inert_when_provider_cli(self, monkeypatch) -> None:
        # Under provider=cli the Stage-2 provider gate is False → the guard is
        # never reached (davidath byte-identical by construction).
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        monkeypatch.setenv("REGENOLD_STAGE2_FIDELITY", "1")
        with patch("app.engines.graph_rag._deterministic_answer", return_value=_CROSS_TIER_DRAFT):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert not used
        assert answer == _CROSS_TIER_DRAFT
