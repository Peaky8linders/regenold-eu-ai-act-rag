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
        return_value=OpenAIWrapperResponse(text="ok", model="claude-sonnet-4-6")
    )
    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=mock_provider,
    ):
        yield mock_provider


class TestDefaultRouting:
    """With complex_model unset (default), the wrapper request must
    use the base model + carry no extra headers — preserving R50
    byte-identical behaviour."""

    def test_simple_question_uses_base_model(self, _mock_wrapper) -> None:
        original_complex = settings.graph_rag.complex_model
        settings.graph_rag.complex_model = ""
        try:
            _openai_wrapper_complete_for_graph_rag(
                system="you are an EU AI Act expert",
                user="What does Article 13 require?",
                max_tokens=400,
                temperature=0.0,
                complex_question=False,
            )
        finally:
            settings.graph_rag.complex_model = original_complex
        req: OpenAIWrapperRequest = _mock_wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.model
        assert req.extra_headers == {}

    def test_complex_question_without_complex_model_uses_base(
        self, _mock_wrapper
    ) -> None:
        """Even when the gate fires, if the deploy hasn't wired
        complex_model the call stays on base. Cost-safe default."""
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
