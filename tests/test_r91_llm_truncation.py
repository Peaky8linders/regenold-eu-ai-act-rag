"""R91 — LLM truncation guard regression tests.

Three call sites silently shipped length-truncated LLM output as
"successful" before R91:

1. ``OpenAIWrapperResponse`` had no ``finish_reason`` field, so the
   chat-completion ``finish_reason="length"`` signal never crossed
   the provider boundary.
2. ``_rewrite_multiturn_query`` (``max_tokens=100``) accepted any
   non-empty rewrite passing the ``10 < len <= 500`` sanity bounds
   — a mid-sentence cut became the retrieval query.
3. ``_claude_max_enhance_answer`` returned the polished text on a
   non-empty ``validate_llm_output`` result, setting
   ``stage2_landed=True`` even when the polish was truncated. That
   in turn triggered the R72 ``_reconcile_references_to_prose``
   pass to PRUNE references not described in the (truncated, partial)
   prose — silently dropping valid citations.

R91 captures ``finish_reason`` on the response model, treats
``"length"`` as a soft failure in the wrapper graph-RAG helper +
denoiser, and mirrors the signal via the Anthropic SDK's
``stop_reason="max_tokens"`` on the SDK direct path.

These tests lock in the contract — the fail-soft envelope is
preserved (no exception raised; the caller falls back to the
deterministic path).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest


# ─── 1. Wrapper response carries finish_reason ────────────────────────────


class TestOpenAIWrapperFinishReasonCaptured:
    def test_finish_reason_length_propagated(self) -> None:
        """The chat-completion ``finish_reason`` lands on the response."""
        from app.llm.openai_wrapper_provider import (
            OpenAIWrapperRequest,
            _OpenAIWrapperProvider,
        )

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-6",
                    "choices": [
                        {
                            "message": {"content": "Partial text…"},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 100},
                },
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.wrapper.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="ping"))
        assert result.error is None
        assert result.text == "Partial text…"
        assert result.finish_reason == "length"

    def test_finish_reason_stop_propagated(self) -> None:
        """Natural completion returns ``finish_reason="stop"``."""
        from app.llm.openai_wrapper_provider import (
            OpenAIWrapperRequest,
            _OpenAIWrapperProvider,
        )

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-6",
                    "choices": [
                        {
                            "message": {"content": "Done."},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.wrapper.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="ping"))
        assert result.finish_reason == "stop"

    def test_finish_reason_missing_is_none(self) -> None:
        """When upstream omits ``finish_reason`` it stays None."""
        from app.llm.openai_wrapper_provider import (
            OpenAIWrapperRequest,
            _OpenAIWrapperProvider,
        )

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-6",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.wrapper.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="ping"))
        assert result.finish_reason is None


# ─── 2. _rewrite_multiturn_query bails on truncation ──────────────────────


def _mk_msg(role: str, content: str):
    """Mirror the route's message shape (has .role + .content attrs)."""
    m = MagicMock()
    m.role = role
    m.content = content
    return m


class TestRewriteMultiturnQueryTruncation:
    def test_truncated_response_returns_none(self, monkeypatch) -> None:
        """``finish_reason="length"`` with non-empty text → return None
        even though the text would otherwise pass the ``10 < len <= 500``
        sanity gate."""
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

        fake_resp = MagicMock()
        fake_resp.error = None
        # Long enough to pass the 10 < len <= 500 sanity check.
        fake_resp.text = "deployer transparency obligations under Article 26 of"
        fake_resp.finish_reason = "length"
        fake_provider = MagicMock()
        fake_provider.complete.return_value = fake_resp

        from app.routes.regenold import _rewrite_multiturn_query

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=fake_provider,
        ):
            out = _rewrite_multiturn_query(
                "What about deployers?",
                [_mk_msg("user", "What is Article 13?")],
            )
        assert out is None

    def test_natural_stop_returns_rewritten_text(self, monkeypatch) -> None:
        """``finish_reason="stop"`` + valid text → caller gets the rewrite."""
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

        fake_resp = MagicMock()
        fake_resp.error = None
        fake_resp.text = "deployer obligations Art. 26"
        fake_resp.finish_reason = "stop"
        fake_provider = MagicMock()
        fake_provider.complete.return_value = fake_resp

        from app.routes.regenold import _rewrite_multiturn_query

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=fake_provider,
        ):
            out = _rewrite_multiturn_query(
                "What about deployers?",
                [_mk_msg("user", "What is Article 13?")],
            )
        assert out == "deployer obligations Art. 26"

    def test_missing_finish_reason_returns_rewritten_text(self, monkeypatch) -> None:
        """Backwards compatibility — when ``finish_reason`` is None
        (legacy responses, mocked tests without the field) the rewrite
        still flows through. Only an explicit ``"length"`` bails."""
        monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

        fake_resp = MagicMock()
        fake_resp.error = None
        fake_resp.text = "deployer obligations Art. 26"
        fake_resp.finish_reason = None
        fake_provider = MagicMock()
        fake_provider.complete.return_value = fake_resp

        from app.routes.regenold import _rewrite_multiturn_query

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=fake_provider,
        ):
            out = _rewrite_multiturn_query(
                "What about deployers?",
                [_mk_msg("user", "What is Article 13?")],
            )
        assert out == "deployer obligations Art. 26"


# ─── 3. Wrapper graph-RAG helper bails on truncation ──────────────────────


class TestOpenAIWrapperCompleteForGraphRagTruncation:
    def test_wrapper_truncated_returns_none(self, monkeypatch) -> None:
        """``_openai_wrapper_complete_for_graph_rag`` returns None when
        the underlying wrapper response carries ``finish_reason="length"``.
        That None propagates to ``_claude_max_enhance_answer`` →
        ``_two_stage_generate`` falls back to the deterministic KG draft
        → ``stage2_landed=False`` → R72 reconcile no-op → valid cites
        stay on the wire."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        fake_resp = MagicMock()
        fake_resp.error = None
        fake_resp.text = "Article 13 requires transparency to deployers"
        fake_resp.model = "claude-sonnet-4-6"
        fake_resp.completion_tokens = 512
        fake_resp.finish_reason = "length"
        fake_provider = MagicMock()
        fake_provider.complete.return_value = fake_resp

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=fake_provider,
        ):
            from app.engines.graph_rag import (
                _openai_wrapper_complete_for_graph_rag,
            )
            result = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=512, temperature=0.0,
            )
        assert result is None

    def test_wrapper_natural_stop_returns_text(self, monkeypatch) -> None:
        """``finish_reason="stop"`` (or absent) returns the text as before."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        fake_resp = MagicMock()
        fake_resp.error = None
        fake_resp.text = "Polished prose."
        fake_resp.model = "claude-sonnet-4-6"
        fake_resp.completion_tokens = 10
        fake_resp.finish_reason = "stop"
        fake_provider = MagicMock()
        fake_provider.complete.return_value = fake_resp

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=fake_provider,
        ):
            from app.engines.graph_rag import (
                _openai_wrapper_complete_for_graph_rag,
            )
            result = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=512, temperature=0.0,
            )
        assert result == "Polished prose."

    def test_wrapper_midword_truncation_with_stop_returns_none(
        self, monkeypatch
    ) -> None:
        """ROOT-CAUSE REGRESSION (live bug: ``...safety component of a produc.``).

        The Claude-Max ``claude-code-openai-wrapper`` ignores ``max_tokens``
        and reports ``finish_reason="stop"`` EVEN when the underlying Claude
        CLI/SSE stream truncates the answer mid-word. The R91 guard only
        checked ``finish_reason == "length"``, so the mid-word fragment shipped
        as ``stage2_landed=True``. The structural guard must detect that the
        text ends without sentence-terminal punctuation and bail so the caller
        falls back to the complete deterministic answer.
        """
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        fake_resp = MagicMock()
        fake_resp.error = None
        # Mid-word cut, finish_reason="stop" (the actual wrapper behaviour).
        fake_resp.text = (
            "Under Article 11, providers must draw up technical documentation "
            "before placing a high-risk AI system on the market. Article 6 "
            "classifies an AI system as high-risk when it is intended as a "
            "safety component of a produc"
        )
        fake_resp.model = "claude-sonnet-4-6"
        fake_resp.completion_tokens = 95
        fake_resp.finish_reason = "stop"
        fake_provider = MagicMock()
        fake_provider.complete.return_value = fake_resp

        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=fake_provider,
        ):
            from app.engines.graph_rag import (
                _openai_wrapper_complete_for_graph_rag,
            )
            result = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=512, temperature=0.0,
            )
        assert result is None

    def test_wrapper_complete_answer_with_trailing_paren_returns_text(
        self, monkeypatch
    ) -> None:
        """Guard must NOT false-positive on legitimate complete answers whose
        final char is ``)`` / ``”`` after the terminator, or a bare
        sentence end."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        for complete_text in (
            "Article 13 requires transparency (see Annex IV).",
            "Providers must keep logs under Article 12.",
            "Is this prohibited under Article 5?",
            'The Act calls this a "high-risk system."',
        ):
            fake_resp = MagicMock()
            fake_resp.error = None
            fake_resp.text = complete_text
            fake_resp.model = "claude-sonnet-4-6"
            fake_resp.completion_tokens = 30
            fake_resp.finish_reason = "stop"
            fake_provider = MagicMock()
            fake_provider.complete.return_value = fake_resp

            with patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=fake_provider,
            ):
                from app.engines.graph_rag import (
                    _openai_wrapper_complete_for_graph_rag,
                )
                result = _openai_wrapper_complete_for_graph_rag(
                    system="s", user="u", max_tokens=512, temperature=0.0,
                )
            assert result == complete_text, f"false-positive on: {complete_text!r}"


# ─── 4. Anthropic SDK path bails on max_tokens stop_reason ────────────────


class TestAnthropicCompleteForGraphRagTruncation:
    """The Anthropic SDK response carries ``stop_reason`` rather than
    ``finish_reason``; ``"max_tokens"`` is the equivalent truncation
    signal to the wrapper's ``"length"``.
    """

    def test_anthropic_max_tokens_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("anthropic")
        # Clean env, mirror tests/test_anthropic_provider.py setup.
        for k in (
            "P2P_GRAPH_RAG_PROVIDER",
            "OPENAI_API_BASE",
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "REGENOLD_INTENT_PROVIDER",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")

        from pydantic import SecretStr
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", SecretStr("sk-ant-fake"),
            raising=True,
        )

        class _Block:
            text = "Partial Article 13 prose…"

        class _Resp:
            content = [_Block()]
            stop_reason = "max_tokens"

        class _Anthropic:
            def __init__(self, *a, **kw): pass

            class _Messages:
                @staticmethod
                def create(*a, **kw):
                    return _Resp()

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=10, temperature=0.0,
        )
        assert result is None

    def test_anthropic_end_turn_returns_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("anthropic")
        for k in (
            "P2P_GRAPH_RAG_PROVIDER",
            "OPENAI_API_BASE",
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "REGENOLD_INTENT_PROVIDER",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")

        from pydantic import SecretStr
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", SecretStr("sk-ant-fake"),
            raising=True,
        )

        class _Block:
            text = "Article 13 requires logs."

        class _Resp:
            content = [_Block()]
            stop_reason = "end_turn"

        class _Anthropic:
            def __init__(self, *a, **kw): pass

            class _Messages:
                @staticmethod
                def create(*a, **kw):
                    return _Resp()

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=10, temperature=0.0,
        )
        assert result == "Article 13 requires logs."
