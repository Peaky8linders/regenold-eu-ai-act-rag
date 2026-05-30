"""R97 — adaptive verbatim-vs-synthesis answer routing.

The user directive (2026-05-30): production had gone effectively
deterministic + verbatim since R94/R96; the Claude Max wrapper + Sonnet was
barely used. R96 blanket-disabled Stage-2 polish whenever verbatim was on,
which is correct for simple single-turn QA (a verbatim provision quote IS
the answer) but wrong for multi-turn / nuanced conversations the verbatim
dump cannot answer. R97 decouples verbatim from Stage-2 and routes multi-turn
+ genuinely-nuanced questions to Sonnet synthesis via
:func:`app.engines.answer_router.select_answer_mode`, keeping the fast
deterministic verbatim path for simple QA.

These tests pin:

* the router decision (unit);
* the engine gate (verbatim ON + router ON → Stage-2 fires for multi-turn /
  complex, skips for simple; router OFF → R96 behaviour);
* the route-level verbatim overwrite skip when Stage-2 landed;
* the router-aware confidence floor (multi-turn uses a lower floor);
* the cache-key folds in the new env flags (R79 doctrine).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines.answer_router import (
    AnswerMode,
    answer_router_enabled,
    is_multi_turn,
    select_answer_mode,
    verbatim_enabled,
)
from app.engines.graph_rag import GraphQuery, ask_compliance_question
from app.main import app
from app.models import GraphRAGRequest
from app.routes.regenold import _engine_cache_key


_MULTI_TURN_Q = (
    "Conversation so far:\nUser: What does Art. 26 require of deployers?\n"
    "Assistant: Article 26 sets out deployer obligations for high-risk AI.\n\n"
    "Latest question:\nDoes the oversight you mentioned have to be continuous?"
)
_SIMPLE_Q = "What does Article 13 require?"
_CONFLICT_Q = (
    "Does Article 6 or Article 5 apply here, and can we skip the conformity "
    "assessment if GDPR already covers it?"
)
# Stage-2 mock prose with NO article numbers → never trips the drift guard,
# no refusal markers → never trips the self-contradiction guard.
_SYNTH = "The deployer must ensure human oversight continues throughout the system lifecycle."


def _query(intent: str = "article_lookup") -> GraphQuery:
    return GraphQuery(intent=intent, raw_question="")


# ─── Router unit ─────────────────────────────────────────────────────────────


class TestSelectAnswerMode:
    def test_simple_qa_is_verbatim(self) -> None:
        d = select_answer_mode(_SIMPLE_Q, history_turn_count=1)
        assert d.mode is AnswerMode.VERBATIM
        assert d.reason == "simple_qa"

    def test_definitional_is_verbatim(self) -> None:
        assert select_answer_mode("What is an AI system?").mode is AnswerMode.VERBATIM

    def test_multi_turn_marker_is_synthesis(self) -> None:
        d = select_answer_mode(_MULTI_TURN_Q, history_turn_count=2)
        assert d.mode is AnswerMode.SYNTHESIS
        assert d.reason == "multi_turn"

    def test_history_depth_is_synthesis(self) -> None:
        # No flatten marker but ≥1 prior user+assistant pair.
        d = select_answer_mode("Do we also need a FRIA?", history_turn_count=2)
        assert d.mode is AnswerMode.SYNTHESIS
        assert d.reason == "multi_turn"

    def test_complex_single_turn_is_synthesis(self) -> None:
        d = select_answer_mode(_CONFLICT_Q, history_turn_count=1)
        assert d.mode is AnswerMode.SYNTHESIS
        assert d.reason == "complex_question"

    def test_synthesis_intent_is_synthesis(self) -> None:
        d = select_answer_mode(_SIMPLE_Q, query=_query("gap_analysis"))
        assert d.mode is AnswerMode.SYNTHESIS
        assert d.reason.startswith("intent:")

    def test_empty_is_verbatim(self) -> None:
        assert select_answer_mode("").mode is AnswerMode.VERBATIM
        assert select_answer_mode("   ").mode is AnswerMode.VERBATIM

    def test_failsoft_defaults_verbatim(self) -> None:
        # A query whose ``intent`` attr raises must not break routing.
        class Boom:
            @property
            def intent(self):  # noqa: ANN202
                raise RuntimeError("boom")

        d = select_answer_mode(_SIMPLE_Q, query=Boom())
        assert d.mode is AnswerMode.VERBATIM

    def test_is_multi_turn_signals(self) -> None:
        assert is_multi_turn(_MULTI_TURN_Q, 1) is True       # marker
        assert is_multi_turn("plain", 2) is True             # depth
        assert is_multi_turn("plain", 1) is False
        assert is_multi_turn("plain", 0) is False

    def test_env_defaults_on(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_VERBATIM_ANSWER", raising=False)
        monkeypatch.delenv("REGENOLD_ANSWER_ROUTER", raising=False)
        assert verbatim_enabled() is True
        assert answer_router_enabled() is True

    def test_router_off_switch(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "0")
        assert answer_router_enabled() is False


# ─── Engine gate (verbatim ON is the production default) ─────────────────────


@pytest.fixture
def _verbatim_on(monkeypatch):
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
    monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    # Disable the confidence floor so these gate tests are deterministic.
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
    yield


class TestEngineRoutingUnderVerbatim:
    def test_multi_turn_fires_stage2_under_verbatim(self, _verbatim_on) -> None:
        """The R97 win: multi-turn routes to Sonnet even though verbatim is ON."""
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                  return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                  return_value=_SYNTH) as mock_wrapper,
        ):
            result = ask_compliance_question(
                GraphRAGRequest(question=_MULTI_TURN_Q, history_turn_count=2)
            )
        mock_wrapper.assert_called_once()
        assert result.answer == _SYNTH
        assert (result.graph_stats or {}).get("stage2_landed") is True

    def test_simple_qa_skips_stage2_under_verbatim(self, _verbatim_on) -> None:
        """Simple single-turn QA stays on the fast deterministic path."""
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                  return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag")
            as mock_wrapper,
        ):
            result = ask_compliance_question(GraphRAGRequest(question=_SIMPLE_Q))
        mock_wrapper.assert_not_called()
        assert (result.graph_stats or {}).get("stage2_landed") is False

    def test_complex_single_turn_fires_stage2_under_verbatim(self, _verbatim_on) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                  return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                  return_value=_SYNTH) as mock_wrapper,
        ):
            result = ask_compliance_question(GraphRAGRequest(question=_CONFLICT_Q))
        mock_wrapper.assert_called_once()
        assert (result.graph_stats or {}).get("stage2_landed") is True

    def test_router_off_restores_r96_baseline(self, monkeypatch) -> None:
        """REGENOLD_ANSWER_ROUTER=0 → verbatim never runs Stage-2 (R96)."""
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "0")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                  return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag")
            as mock_wrapper,
        ):
            result = ask_compliance_question(
                GraphRAGRequest(question=_MULTI_TURN_Q, history_turn_count=2)
            )
        mock_wrapper.assert_not_called()
        assert (result.graph_stats or {}).get("stage2_landed") is False


# ─── Router-aware confidence floor ───────────────────────────────────────────


class TestConfidenceFloorRouterAware:
    """Multi-turn synthesis uses a lower floor (default 0.3) than single-turn
    (default 0.5) so coreferent follow-ups still reach Sonnet."""

    def _run(self, question, history, monkeypatch):
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0.5")
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE_MULTITURN", "0.3")
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                  return_value=True),
            patch("app.engines.graph_rag._compute_confidence", return_value=0.35),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                  return_value=_SYNTH) as mock_wrapper,
        ):
            ask_compliance_question(
                GraphRAGRequest(question=question, history_turn_count=history)
            )
        return mock_wrapper

    def test_multi_turn_passes_low_floor(self, monkeypatch) -> None:
        """conf 0.35 ≥ multi-turn floor 0.3 → Stage-2 fires."""
        mock_wrapper = self._run(_MULTI_TURN_Q, 2, monkeypatch)
        mock_wrapper.assert_called_once()

    def test_single_turn_complex_blocked_by_high_floor(self, monkeypatch) -> None:
        """conf 0.35 < single-turn floor 0.5 → Stage-2 skipped."""
        mock_wrapper = self._run(_CONFLICT_Q, 1, monkeypatch)
        mock_wrapper.assert_not_called()


# ─── Route-level: verbatim overwrite skipped when Stage-2 landed ─────────────


def _client() -> TestClient:
    settings.regenold.api_key = SecretStr("regenold-test-key")
    return TestClient(app)


class TestRouteVerbatimSkipOnSynthesis:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")
        yield

    def test_multiturn_answer_is_synthesis_not_verbatim_dump(self, monkeypatch) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled",
                  return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                  return_value=_SYNTH),
        ):
            c = _client()
            r = c.post(
                "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
                headers={"X-Regenold-Api-Key": "regenold-test-key"},
                json=[
                    {"role": "user", "content": "What does Article 26 require of deployers?"},
                    {"role": "assistant", "content": "Article 26 sets out deployer obligations."},
                    {"role": "user", "content": "Does that oversight have to be continuous?"},
                ],
            )
        assert r.status_code == 200, r.json()
        body = r.json()
        # Stage-2 landed → verbatim overwrite skipped → NOT the verbatim path.
        assert body.get("retrieval_path") != "verbatim_exact_text", body.get("retrieval_path")

    def test_simple_qa_answer_is_verbatim(self) -> None:
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": "What does Article 13 require?"}],
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        # Single-turn QA → router VERBATIM → verbatim provision dump on the wire.
        assert body.get("retrieval_path") == "verbatim_exact_text", body.get("retrieval_path")


# ─── Cache key folds in the R97 routing flags (R79 doctrine) ─────────────────


class TestCacheKeyRoutingFlags:
    def test_router_flag_changes_key(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        k1 = _engine_cache_key("q", None, 2)
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "0")
        k2 = _engine_cache_key("q", None, 2)
        assert k1 != k2

    def test_verbatim_flag_changes_key(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
        k1 = _engine_cache_key("q", None, 2)
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")
        k2 = _engine_cache_key("q", None, 2)
        assert k1 != k2

    def test_multiturn_floor_flag_changes_key(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE_MULTITURN", "0.3")
        k1 = _engine_cache_key("q", None, 2)
        monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE_MULTITURN", "0.1")
        k2 = _engine_cache_key("q", None, 2)
        assert k1 != k2
