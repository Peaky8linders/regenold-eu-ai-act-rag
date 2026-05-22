"""Regression guards for the two-stage KG-first answer pipeline.

Stage 1 (always): deterministic ontology/KB parse → Neo4j/KB retrieval →
  citation-exact structured answer.  No LLM cost; always runs.

Stage 2 (auto-activated): pass the Stage-1 answer to the ``openai_wrapper``
  proxy (Claude Max subscription) for natural-language polish.

Stage 2 fires when BOTH:
  a) ``is_openai_wrapper_enabled()`` → the proxy is wired up, AND
  b) ``_needs_stage2_enhancement()`` → the question is complex enough:
       - multi-turn conversation history in the question
       - gap_analysis or cross_framework intent
       - ≥ 2 article entities (comparison / multi-obligation)
       - live question > 200 chars
       - synthesis / remediation / comparison keywords present
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engines.graph_rag import (
    GraphContext,
    GraphQuery,
    _claude_max_enhance_answer,
    _needs_stage2_enhancement,
    _two_stage_generate,
    ask_compliance_question,
)
from app.models import GraphRAGRequest


# ─── Helpers ─────────────────────────────────────────────────────────────────

# A question that is always complex enough to trigger Stage 2 — multi-turn
# indicator is the most reliable signal.
_MULTI_TURN_Q = (
    "Conversation so far:\nUser: What does Art. 9 require?\n"
    "Assistant: Article 9 requires data governance.\n\n"
    "Latest question:\nWhat are the specific training-data obligations?"
)

# A short, single-article question — should NOT trigger Stage 2 on its own.
_SIMPLE_Q = "What does Art. 9 require?"


def _query(intent: str = "article_lookup", entities: list[str] | None = None) -> GraphQuery:
    return GraphQuery(
        intent=intent,
        entities=entities or [],
        raw_question="",
    )


def _empty_ctx() -> GraphContext:
    return GraphContext()


# ─── Stage 1: parse is always deterministic ──────────────────────────────────


class TestStage1AlwaysDeterministic:
    """The pipeline must never call _llm_parse_query — Stage 1 parse is always
    ontology/KB-based so there is no LLM cost or latency on the parse path."""

    def test_llm_parse_query_never_called(self) -> None:
        with patch("app.engines.graph_rag._llm_parse_query") as mock_llm:
            req = GraphRAGRequest(question=_SIMPLE_Q)
            ask_compliance_question(req)
        mock_llm.assert_not_called()

    def test_deterministic_parse_always_called(self) -> None:
        with patch(
            "app.engines.graph_rag._deterministic_parse",
            wraps=__import__(
                "app.engines.graph_rag", fromlist=["_deterministic_parse"]
            )._deterministic_parse,
        ) as mock_det:
            req = GraphRAGRequest(question="What obligations does Art. 13 impose?")
            ask_compliance_question(req)
        mock_det.assert_called_once()

    def test_reasoning_trace_has_seven_entries(self) -> None:
        """The trace must include the Stage-2 indicator entry."""
        req = GraphRAGRequest(question=_SIMPLE_Q)
        result = ask_compliance_question(req)
        assert len(result.reasoning_trace) == 7, result.reasoning_trace

    def test_reasoning_trace_includes_stage2_indicator(self) -> None:
        req = GraphRAGRequest(question=_SIMPLE_Q)
        result = ask_compliance_question(req)
        stage2_entries = [t for t in result.reasoning_trace if "Stage 2" in t]
        assert len(stage2_entries) == 1, result.reasoning_trace


# ─── _needs_stage2_enhancement heuristic ─────────────────────────────────────


class TestNeedsStage2Heuristic:
    """Unit tests on the complexity heuristic that gates Stage-2 activation."""

    # --- must return True ---

    def test_multi_turn_prefix_triggers(self) -> None:
        assert _needs_stage2_enhancement(_MULTI_TURN_Q, _empty_ctx()) is True

    def test_gap_analysis_intent_triggers(self) -> None:
        assert _needs_stage2_enhancement(
            _SIMPLE_Q, _empty_ctx(), _query(intent="gap_analysis")
        ) is True

    def test_cross_framework_intent_triggers(self) -> None:
        assert _needs_stage2_enhancement(
            _SIMPLE_Q, _empty_ctx(), _query(intent="cross_framework")
        ) is True

    def test_two_or_more_entities_triggers(self) -> None:
        assert _needs_stage2_enhancement(
            _SIMPLE_Q,
            _empty_ctx(),
            _query(entities=["Art. 9", "Art. 10"]),
        ) is True

    def test_long_live_question_triggers(self) -> None:
        long_q = "What are the exact obligations " + "a " * 100 + "deployer faces?"
        assert _needs_stage2_enhancement(long_q, _empty_ctx()) is True

    @pytest.mark.parametrize("keyword", [
        "compare these two articles",
        "what is the difference between Art. 9 and Art. 10",
        "vs. the GDPR approach",
        "how should we prioritise the remediation work",
        "please explain why this obligation exists",
    ])
    def test_complex_keywords_trigger(self, keyword: str) -> None:
        assert _needs_stage2_enhancement(keyword, _empty_ctx()) is True

    # --- must return False ---

    def test_simple_short_question_does_not_trigger(self) -> None:
        assert _needs_stage2_enhancement(_SIMPLE_Q, _empty_ctx()) is False

    def test_single_entity_article_lookup_does_not_trigger(self) -> None:
        assert _needs_stage2_enhancement(
            _SIMPLE_Q, _empty_ctx(), _query(intent="article_lookup", entities=["Art. 9"])
        ) is False

    def test_obligation_check_no_extras_does_not_trigger(self) -> None:
        assert _needs_stage2_enhancement(
            "Does Art. 13 require disclosure?",
            _empty_ctx(),
            _query(intent="obligation_check", entities=["Art. 13"]),
        ) is False


# ─── Stage 2: Claude Max proxy engagement ────────────────────────────────────


class TestStage2ClaudeMaxProxy:
    """Stage 2 fires only when wrapper is enabled AND heuristic returns True."""

    def test_stage2_skipped_when_wrapper_disabled(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=False),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag") as mock_wrapper,
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)

        mock_wrapper.assert_not_called()
        stage2_line = next(t for t in result.reasoning_trace if "Stage 2" in t)
        assert "False" in stage2_line

    def test_stage2_skipped_for_simple_question_even_when_wrapper_enabled(self) -> None:
        """A simple single-article question must NOT trigger Stage 2 even if the
        proxy is running — Stage 2 cost is only paid when the question warrants it."""
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag") as mock_wrapper,
        ):
            req = GraphRAGRequest(question=_SIMPLE_Q)
            result = ask_compliance_question(req)

        mock_wrapper.assert_not_called()
        stage2_line = next(t for t in result.reasoning_trace if "Stage 2" in t)
        assert "False" in stage2_line

    def test_stage2_fires_for_multi_turn_when_wrapper_enabled(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Enhanced compliance guidance.",
            ) as mock_wrapper,
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)

        mock_wrapper.assert_called_once()
        assert result.answer == "Enhanced compliance guidance."
        stage2_line = next(t for t in result.reasoning_trace if "Stage 2" in t)
        assert "True" in stage2_line

    def test_stage2_failure_returns_kg_answer(self) -> None:
        """When the Claude Max call returns None the Stage-1 KG answer is used."""
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", return_value=None),
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)

        assert result.answer
        stage2_line = next(t for t in result.reasoning_trace if "Stage 2" in t)
        assert "False" in stage2_line

    def test_stage2_exception_returns_kg_answer(self) -> None:
        """A hard exception inside the wrapper path must not propagate."""
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                side_effect=RuntimeError("connection refused"),
            ),
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)

        assert result.answer


# ─── Stage-2 cache-poisoning guard ───────────────────────────────────────────


class TestStage2CallFailedFlag:
    """Round-30: Stage-2 transient failure must NOT be cacheable.

    Without this flag the route-level LRU cache stores the deterministic
    fallback answer and every subsequent identical question gets the
    un-polished answer forever (until LRU eviction). A single ~20%-rate
    wrapper hiccup permanently disables Stage-2 for that question.
    """

    def test_stage2_call_failed_set_when_wrapper_returns_none(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value=None,
            ),
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)
        assert result.graph_stats.get("stage2_call_failed") is True

    def test_stage2_call_failed_unset_when_stage2_succeeds(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Polished answer.",
            ),
        ):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)
        assert result.graph_stats.get("stage2_call_failed") is False

    def test_stage2_call_failed_unset_when_stage2_not_needed(self) -> None:
        """Simple single-article question doesn't trigger Stage-2 — not a failure."""
        with patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True):
            req = GraphRAGRequest(question=_SIMPLE_Q)
            result = ask_compliance_question(req)
        assert result.graph_stats.get("stage2_call_failed") is False

    def test_stage2_call_failed_unset_when_wrapper_disabled(self) -> None:
        """Wrapper not configured — also not a failure, just not applicable."""
        with patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=False):
            req = GraphRAGRequest(question=_MULTI_TURN_Q[:2000])
            result = ask_compliance_question(req)
        assert result.graph_stats.get("stage2_call_failed") is False


# ─── _two_stage_generate unit tests ──────────────────────────────────────────


class TestTwoStageGenerateUnit:
    """Direct unit tests on the helper without going through the route."""

    def test_returns_kg_answer_when_wrapper_disabled(self) -> None:
        with patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=False):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert not used
        assert answer

    def test_skips_stage2_for_simple_question_even_if_wrapper_enabled(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag") as mock,
        ):
            answer, used = _two_stage_generate(_SIMPLE_Q, _empty_ctx())
        assert not used
        mock.assert_not_called()

    def test_returns_enhanced_for_complex_question_when_wrapper_enabled(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Polished answer.",
            ),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert used
        assert answer == "Polished answer."

    def test_returns_kg_answer_when_enhance_returns_none(self) -> None:
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", return_value=None),
        ):
            answer, used = _two_stage_generate(_MULTI_TURN_Q, _empty_ctx())
        assert not used
        assert answer

    def test_gap_analysis_query_triggers_stage2(self) -> None:
        q = _query(intent="gap_analysis")
        with (
            patch("app.llm.openai_wrapper_provider.is_openai_wrapper_enabled", return_value=True),
            patch(
                "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
                return_value="Gap analysis answer.",
            ),
        ):
            answer, used = _two_stage_generate(_SIMPLE_Q, _empty_ctx(), query=q)
        assert used
        assert answer == "Gap analysis answer."


# ─── _claude_max_enhance_answer unit tests ───────────────────────────────────


class TestClaudeMaxEnhanceAnswerUnit:
    """_claude_max_enhance_answer must pass the KG answer to the wrapper and
    return the polished result, or None on any failure."""

    def test_passes_kg_answer_in_user_message(self) -> None:
        captured: list[str] = []

        def capture(**kwargs: object) -> str:
            captured.append(str(kwargs.get("user", "")))
            return "Polished answer."

        with patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", side_effect=capture):
            result = _claude_max_enhance_answer(
                question="What does Art. 9 require?",
                kg_answer="Some KG answer text.",
            )

        assert result == "Polished answer."
        assert len(captured) == 1
        assert "Some KG answer text." in captured[0]
        assert "Art. 9" in captured[0]

    def test_returns_none_when_wrapper_returns_none(self) -> None:
        with patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", return_value=None):
            assert _claude_max_enhance_answer(question="Q", kg_answer="A") is None

    def test_returns_none_on_exception(self) -> None:
        with patch(
            "app.engines.graph_rag._openai_wrapper_complete_for_graph_rag",
            side_effect=RuntimeError("boom"),
        ):
            assert _claude_max_enhance_answer(question="Q", kg_answer="A") is None

    def test_includes_system_description_when_provided(self) -> None:
        captured: list[str] = []

        def capture(**kwargs: object) -> str:
            captured.append(str(kwargs.get("user", "")))
            return "Polished."

        with patch("app.engines.graph_rag._openai_wrapper_complete_for_graph_rag", side_effect=capture):
            _claude_max_enhance_answer(
                question="What is Art. 9?",
                kg_answer="KG answer.",
                system_description="HR screening tool at a large bank.",
            )

        assert "HR screening" in captured[0]


# ─── R72.1 — graph_stats carries the stage2_landed signal ────────────────────


class TestR721Stage2LandedSignal:
    """R72.1 — `graph_stats` must export `stage2_landed`. Before R72.1 the
    key was never set, so the route's `_trace_stage2` reasoning record AND
    the R72 reference-reconciliation gate both silently read False."""

    def test_stage2_landed_key_always_present(self) -> None:
        result = ask_compliance_question(GraphRAGRequest(question=_SIMPLE_Q))
        assert "stage2_landed" in (result.graph_stats or {})

    def test_stage2_landed_false_on_deterministic_path(self) -> None:
        # No wrapper wired → Stage-2 never lands → False (not absent).
        result = ask_compliance_question(GraphRAGRequest(question=_SIMPLE_Q))
        assert result.graph_stats["stage2_landed"] is False

    def test_stage2_landed_true_when_stage2_enhances(self) -> None:
        # When `_two_stage_generate` reports an enhanced answer the signal
        # must surface True so the route's R72 reconciliation gate fires.
        with patch(
            "app.engines.graph_rag._two_stage_generate",
            return_value=("Polished Stage-2 answer.", True),
        ):
            result = ask_compliance_question(GraphRAGRequest(question=_SIMPLE_Q))
        assert result.graph_stats["stage2_landed"] is True
