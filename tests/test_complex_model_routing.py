"""R51 — engine-side complex-model routing tests.

Locks in:
* When ``complex_model`` is unset (default), all Stage-2 calls hit
  the base ``settings.graph_rag.model`` regardless of complexity.
* When ``complex_model`` is set AND the question is complex, the
  call swaps to ``complex_model``.
* When ``complex_thinking_tokens > 0`` AND the question is complex,
  the wrapper request carries ``X-Claude-Max-Thinking-Tokens``.
* Simple questions never get the thinking header (cost guard).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.engines.graph_rag import _openai_wrapper_complete_for_graph_rag
from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    OpenAIWrapperResponse,
)


@pytest.fixture
def _mock_wrapper():
    """Replace the wrapper singleton with a MagicMock so we can
    inspect the OpenAIWrapperRequest the engine builds."""
    mock_provider = MagicMock()
    mock_provider.complete = MagicMock(
        return_value=OpenAIWrapperResponse(text="ok.", model="claude-sonnet-4-6")
    )
    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=mock_provider,
    ):
        yield mock_provider


class TestDefaultRouting:
    """**R81-A1 default**: ``complex_model=""`` (empty). Every Stage-2
    polish call — simple or complex — uses the base ``model``. The R51
    swap path is operator-opt-in via ``P2P_GRAPH_RAG_COMPLEX_MODEL``."""

    def test_simple_question_uses_base_model(self, _mock_wrapper) -> None:
        """Simple questions stay on the base model regardless of
        ``complex_model`` setting (R51 cost guard preserved)."""
        _openai_wrapper_complete_for_graph_rag(
            system="you are an EU AI Act expert",
            user="What does Article 13 require?",
            max_tokens=400,
            temperature=0.0,
            complex_question=False,
        )
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.model
        assert req.extra_headers == {}

    def test_complex_question_when_complex_model_unset_uses_base(
        self, _mock_wrapper
    ) -> None:
        """Operator override path: setting complex_model="" disables
        the swap even when the gate fires. Verifies the fallback path
        for operators who don't want the Opus + thinking spend."""
        original_complex = settings.graph_rag.complex_model
        original_tokens = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_model = ""
        settings.graph_rag.complex_thinking_tokens = 0
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_model = original_complex
            settings.graph_rag.complex_thinking_tokens = original_tokens
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.model
        assert req.extra_headers == {}

    def test_complex_question_swaps_to_opus48_by_default(
        self, _mock_wrapper
    ) -> None:
        """**R103 + R131.2 default behaviour**: with no env override, a
        ``complex_question=True`` call swaps the model to ``opus-4-8``
        (the default) — Opus 4.8 is the stronger reasoner for the ~20%
        complex categories (conflict / borderline-prohibition / GPAI
        thresholds / multi-turn coreference). R131.2 re-enables a MODEST
        1024-token extended-thinking budget (operator directive — surface
        real model reasoning in the trace / UI), so the wrapper request
        now carries the ``X-Claude-Max-Thinking-Tokens: 1024`` header on
        the complex path. Operators can disable the swap with
        ``P2P_GRAPH_RAG_COMPLEX_MODEL=`` (empty) or the thinking with
        ``P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS=0``."""
        _openai_wrapper_complete_for_graph_rag(
            system="x", user="y", max_tokens=400, temperature=0.0,
            complex_question=True,
        )
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        # Load-bearing: the complex path swaps to Opus 4.8 by default.
        assert req.model == "claude-opus-4-8"
        # Pin the R139 defaults so a future revert is loud, not silent.
        assert settings.graph_rag.complex_model == "claude-opus-4-8"
        # R139 — EXTENDED thinking budget on the complex tier (was 1024 in R131.2).
        assert settings.graph_rag.complex_thinking_tokens == 4000
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == "4000"

    def test_complex_question_swap_path_when_opus_configured(
        self, _mock_wrapper
    ) -> None:
        """Operator extended-thinking override path: R103 disables
        extended thinking by default (``complex_thinking_tokens=0`` → no
        ``X-Claude-Max-Thinking-Tokens`` header). When an operator
        explicitly sets a thinking budget > 0, the wrapper request adds
        the header whose value tracks ``complex_thinking_tokens``. (The
        model swap itself is the default — see the by-default
        test above.)"""
        original_complex = settings.graph_rag.complex_model
        original_thinking = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_model = "claude-opus-4-8"
        settings.graph_rag.complex_thinking_tokens = 2500
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_model = original_complex
            settings.graph_rag.complex_thinking_tokens = original_thinking
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == "claude-opus-4-8"
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == "2500"


class TestComplexRouting:
    """When complex_model AND/OR complex_thinking_tokens are wired,
    complex questions get the upgraded path."""

    def test_complex_question_swaps_model(self, _mock_wrapper) -> None:
        original_complex = settings.graph_rag.complex_model
        settings.graph_rag.complex_model = "claude-opus-4-7"
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_model = original_complex
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == "claude-opus-4-7"

    def test_simple_question_does_not_swap_model(self, _mock_wrapper) -> None:
        original_complex = settings.graph_rag.complex_model
        settings.graph_rag.complex_model = "claude-opus-4-7"
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=False,
            )
        finally:
            settings.graph_rag.complex_model = original_complex
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.model
        assert "X-Claude-Max-Thinking-Tokens" not in req.extra_headers

    def test_complex_question_adds_thinking_header(self, _mock_wrapper) -> None:
        original_tokens = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_thinking_tokens = 8000
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_thinking_tokens = original_tokens
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == "8000"

    def test_thinking_budget_capped(self, _mock_wrapper) -> None:
        """Out-of-range thinking budgets are clamped to [1024, 16000]."""
        original_tokens = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_thinking_tokens = 50000  # too high
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_thinking_tokens = original_tokens
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == "16000"

    def test_thinking_budget_minimum_enforced(self, _mock_wrapper) -> None:
        original_tokens = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_thinking_tokens = 100  # too low
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_thinking_tokens = original_tokens
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == "1024"

    def test_simple_question_never_gets_thinking_header(
        self, _mock_wrapper
    ) -> None:
        """Cost guard: thinking budget MUST NOT fire on simple
        questions even if the env knob is set globally."""
        original_tokens = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_thinking_tokens = 8000
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="x", user="y", max_tokens=400, temperature=0.0,
                complex_question=False,
            )
        finally:
            settings.graph_rag.complex_thinking_tokens = original_tokens
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert "X-Claude-Max-Thinking-Tokens" not in req.extra_headers


class TestStage2AlwaysOpus:
    """2026-06-30 Sonnet-5-routing directive (supersedes R139's always-Opus).
    Stage-2 ANSWER: the SIMPLE tier → ``stage2_model`` (Sonnet 5 + reasoning
    tokens); the COMPLEX tier → ``complex_model`` (Opus 4.8 + extended thinking).
    The Stage-1 parse stays on the fast base model (now Sonnet 5).

    ``is_stage2`` keys off the caller's ``stage_name`` (only the Stage-2 polish
    calls pass "Stage 2 …"), so these tests pass it explicitly — the other
    tests in this module omit it (is_stage2=False → base-model path).
    """

    def test_stage2_simple_uses_sonnet5_with_moderate_thinking(
        self, _mock_wrapper
    ) -> None:
        """Simple Stage-2 question → ``stage2_model`` (Sonnet 5) + the MODERATE
        ``thinking_tokens`` reasoning budget, so latency stays bounded on the
        ~80% simple majority while the answer is verdict-first quality. Pins the
        2026-06-30 default loudly so a revert to Opus is not silent."""
        _openai_wrapper_complete_for_graph_rag(
            system="x", user="Is a medtech system that tracks patient weight high risk?",
            max_tokens=400, temperature=0.0,
            complex_question=False,
            stage_name="Stage 2 (Polishing)",
        )
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.stage2_model == "claude-sonnet-5"
        # MODERATE reasoning tokens on the simple Stage-2 path.
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == str(
            settings.graph_rag.thinking_tokens
        )

    def test_stage2_complex_uses_opus_with_extended_thinking(
        self, _mock_wrapper
    ) -> None:
        """Complex Stage-2 question → ``complex_model`` (Opus 4.8) + the
        EXTENDED ``complex_thinking_tokens`` budget (4000 by default)."""
        _openai_wrapper_complete_for_graph_rag(
            system="x", user="y", max_tokens=400, temperature=0.0,
            complex_question=True,
            stage_name="Stage 2 (Polishing)",
        )
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.complex_model == "claude-opus-4-8"
        assert req.extra_headers.get("X-Claude-Max-Thinking-Tokens") == str(
            settings.graph_rag.complex_thinking_tokens
        )

    def test_stage1_parse_stays_on_base_model_no_thinking(
        self, _mock_wrapper
    ) -> None:
        """The Stage-1 PARSE (JSON entity extraction) must NEVER swap to a
        stronger model or burn a thinking budget — it stays on the fast base
        model (Sonnet 5 as of 2026-06-30) with no thinking header, even though
        the Stage-2 answer paths do."""
        _openai_wrapper_complete_for_graph_rag(
            system="x", user="y", max_tokens=400, temperature=0.0,
            complex_question=False,
            stage_name="Stage 1 (Scope & Extraction)",
        )
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.model == "claude-sonnet-5"
        assert "X-Claude-Max-Thinking-Tokens" not in req.extra_headers
