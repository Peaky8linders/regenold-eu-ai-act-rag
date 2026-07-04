"""Standard Stage-2 thinking-budget contract (R135 → 2026-07-04 directive).

R135 gave the standard synthesis path a moderate thinking budget. The
**2026-07-04 operator directive** reverses that for the simple tier: Opus 4.8
now answers BOTH tiers, and the simple (non-complex) path is thinking-FREE
(``GraphRAGSettings.thinking_tokens`` default 0) so Opus answers simple
questions in a single fast pass. The complex/Opus path keeps the EXTENDED
``complex_thinking_tokens``. The Stage-1 parse call NEVER requests thinking
(JSON entity extraction — wasteful + corruption risk).

These tests track the mechanism (a positive ``thinking_tokens`` → header;
``0`` → no header) so they hold regardless of the tuned default, plus pin the
current default (0). All wrapper/SDK-only → davidath byte-identical (no
provider wired in the TestClient bench).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.engines.graph_rag import _openai_wrapper_complete_for_graph_rag
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse

_STAGE2 = "Stage 2 (Synthesis)"
_STAGE1 = "Stage 1 (Scope & Extraction)"
_HDR = "X-Claude-Max-Thinking-Tokens"


@pytest.fixture
def _wrapper():
    mock = MagicMock()
    mock.complete = MagicMock(
        return_value=OpenAIWrapperResponse(text="Article 13 requires transparency.", model="m")
    )
    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=mock,
    ):
        yield mock


def _call(stage_name: str, complex_question: bool, max_tokens: int = 384):
    _openai_wrapper_complete_for_graph_rag(
        system="s", user="u", max_tokens=max_tokens, temperature=0.0,
        complex_question=complex_question, stage_name=stage_name,
    )


class TestStandardStage2Thinking:
    def test_stage2_standard_tracks_thinking_budget(self, _wrapper):
        """The standard (non-complex) Stage-2 answer runs on ``stage2_model``
        (Opus 4.8 — 2026-07-04). Its thinking header tracks ``thinking_tokens``:
        a positive budget sends the header, the default 0 sends none (Opus
        answers the simple tier in one fast pass)."""
        _call(_STAGE2, complex_question=False)
        req = _wrapper.complete.call_args.args[0]
        assert req.model == settings.graph_rag.stage2_model  # Opus 4.8
        if settings.graph_rag.thinking_tokens > 0:
            assert req.extra_headers.get(_HDR) == str(settings.graph_rag.thinking_tokens)
        else:
            assert _HDR not in (req.extra_headers or {})

    def test_stage1_parse_never_thinks(self, _wrapper):
        """The Stage-1 parse (JSON entity extraction) must NEVER request a
        thinking budget — wasteful and a JSON-corruption risk."""
        _call(_STAGE1, complex_question=False)
        req = _wrapper.complete.call_args.args[0]
        assert _HDR not in (req.extra_headers or {})

    def test_default_stage_name_no_thinking(self, _wrapper):
        """A call with the default ``stage_name`` (not 'Stage 2') + simple
        question gets no thinking header (preserves the non-Stage-2 cost guard)."""
        _call("Stage", complex_question=False)
        req = _wrapper.complete.call_args.args[0]
        assert _HDR not in (req.extra_headers or {})

    def test_complex_uses_complex_budget(self, _wrapper):
        """Complex Stage-2 uses ``complex_thinking_tokens`` (the Opus budget),
        not the standard ``thinking_tokens``."""
        orig = settings.graph_rag.thinking_tokens
        settings.graph_rag.thinking_tokens = 1024
        try:
            _call(_STAGE2, complex_question=True)
        finally:
            settings.graph_rag.thinking_tokens = orig
        req = _wrapper.complete.call_args.args[0]
        assert req.extra_headers.get(_HDR) == str(settings.graph_rag.complex_thinking_tokens)

    def test_thinking_tokens_zero_disables(self, _wrapper):
        """``thinking_tokens=0`` restores the fast thinking-free Sonnet path."""
        orig = settings.graph_rag.thinking_tokens
        settings.graph_rag.thinking_tokens = 0
        try:
            _call(_STAGE2, complex_question=False)
        finally:
            settings.graph_rag.thinking_tokens = orig
        req = _wrapper.complete.call_args.args[0]
        assert _HDR not in (req.extra_headers or {})

    def test_max_tokens_floored_above_thinking(self, _wrapper):
        """When thinking is on, max_tokens is floored ABOVE the thinking
        budget so the answer has output room (API requires max_tokens >
        thinking budget)."""
        _call(_STAGE2, complex_question=False, max_tokens=384)
        req = _wrapper.complete.call_args.args[0]
        assert req.max_tokens >= settings.graph_rag.thinking_tokens + 512


class TestConfig:
    def test_thinking_tokens_default(self):
        # 2026-07-04 operator directive — 0 (no thinking on the simple/Opus
        # tier; reversible via P2P_GRAPH_RAG_THINKING_TOKENS=2048).
        assert settings.graph_rag.thinking_tokens == 0


class TestAnthropicParity:
    def test_anthropic_standard_thinking_param(self):
        """The Anthropic-SDK Stage-2 standard path mirrors the wrapper: a
        positive ``thinking_tokens`` enables extended thinking; the default 0
        requests none (fast single-pass Opus)."""
        client = MagicMock()
        resp = MagicMock()
        block = MagicMock(); block.type = "text"; block.text = "ok."
        resp.content = [block]
        resp.stop_reason = "end_turn"
        client.messages.create = MagicMock(return_value=resp)
        from app.engines import graph_rag as g
        with patch.object(g, "_get_anthropic_client", return_value=client):
            g._anthropic_complete_for_graph_rag(
                system="s", user="u", max_tokens=384, temperature=0.0,
                complex_question=False, stage_name=_STAGE2,
            )
        kwargs = client.messages.create.call_args.kwargs
        if settings.graph_rag.thinking_tokens > 0:
            assert "thinking" in kwargs
            assert kwargs["thinking"]["budget_tokens"] == settings.graph_rag.thinking_tokens
            assert kwargs["max_tokens"] >= settings.graph_rag.thinking_tokens + 512
        else:
            assert "thinking" not in kwargs

    def test_anthropic_stage1_no_thinking(self):
        client = MagicMock()
        resp = MagicMock()
        block = MagicMock(); block.type = "text"; block.text = "ok."
        resp.content = [block]; resp.stop_reason = "end_turn"
        client.messages.create = MagicMock(return_value=resp)
        from app.engines import graph_rag as g
        with patch.object(g, "_get_anthropic_client", return_value=client):
            g._anthropic_complete_for_graph_rag(
                system="s", user="u", max_tokens=384, temperature=0.0,
                complex_question=False, stage_name=_STAGE1,
            )
        assert "thinking" not in client.messages.create.call_args.kwargs
