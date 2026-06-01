"""R56 — Anthropic SDK direct provider hardening.

The Anthropic API direct path is the Pro-tier fallback for when the
Claude Max OpenAI wrapper isn't viable (Pro's tighter rate limits would
throttle Stage-2 polish on Max-on-Pro). R56 wires Stage-2 polish through
the Anthropic SDK directly when ``P2P_GRAPH_RAG_PROVIDER=anthropic``.

These tests lock in:

1. Stage-2 gate (:func:`_stage2_provider_enabled`) accepts BOTH
   the openai_wrapper and the anthropic-SDK-direct path.
2. The new :func:`_anthropic_complete_for_graph_rag` falls back to
   ``None`` on every failure mode (missing SDK, missing key,
   RateLimitError, AuthenticationError, transport error, empty content).
3. :func:`_claude_max_enhance_answer` routes the call through the
   Anthropic SDK when the provider env is set to ``anthropic``.
4. :func:`_two_stage_generate` end-to-end through the anthropic path —
   Stage-2 polish lands when configured + returns the polished prose.
5. Engine cache key includes the resolved provider (R30-style
   cache-poisoning fix).
6. :func:`/healthz/llm` reports ``provider=anthropic`` cleanly for
   the SDK-missing and SDK-present states (already covered in
   ``test_healthz_llm.py`` — this file adds a smoke).
"""
from __future__ import annotations

import builtins as _builtins
import sys
import types
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr as _SS


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _disable_r87e_stage2_gate(monkeypatch):
    """R87-E confidence-gated Stage-2 skip uses ``_compute_confidence``
    which returns 0.3 for the empty mock contexts these tests construct.
    These pre-R87-E tests assert Stage-2 polish lands through the
    Anthropic SDK direct path; we disable the new gate so the original
    assertions still hold. The R87-E gate has its own coverage in
    ``tests/test_r87cde_subpoint_roleduty_stage2gate.py``."""
    monkeypatch.setenv("REGENOLD_STAGE2_MIN_CONFIDENCE", "0")


@pytest.fixture()
def reset_anthropic_env(monkeypatch: pytest.MonkeyPatch):
    """Wipe all LLM-provider env vars so each test sets exactly what it needs."""
    for k in (
        "P2P_GRAPH_RAG_PROVIDER",
        "P2P_GRAPH_RAG_API_KEY",
        "P2P_GRAPH_RAG_MODEL",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "REGENOLD_INTENT_PROVIDER",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
    # Reset cached settings.graph_rag.api_key to None for a clean slate.
    from app.config import settings
    monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)


@pytest.fixture(autouse=True)
def _r77_enable_stage2_polish(monkeypatch: pytest.MonkeyPatch) -> None:
    """R77 — Stage-2 polish now defaults OFF (``P2P_GRAPH_RAG_ENABLE_STAGE2``).

    These tests predate that default and exercise the Stage-2 path with a
    mocked provider. Force the master switch ON so they keep testing
    Stage-2 behaviour. This env var gates :func:`_stage2_polish_enabled`,
    which is distinct from :func:`_stage2_provider_enabled` (tested by
    ``TestStage2ProviderGate``), so the provider-gate tests are unaffected.
    ``reset_anthropic_env`` does not clear this var, so it survives there.

    R96 — also disable the verbatim surface so ``_stage2_polish_enabled``
    falls through to ``P2P_GRAPH_RAG_ENABLE_STAGE2`` (the gate now
    short-circuits OFF under verbatim, since the route discards Stage-2
    prose there).
    """
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "1")
    monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "0")


# ─── 1. Stage-2 gate accepts both providers ──────────────────────────────────


class TestStage2ProviderGate:
    def test_no_provider_set_disables_stage2(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default (unset) provider resolves to ``anthropic`` but with no key →
        Stage-2 disabled."""
        from app.engines.graph_rag import _stage2_provider_enabled
        assert _stage2_provider_enabled() is False

    def test_cli_provider_disables_stage2(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        from app.engines.graph_rag import _stage2_provider_enabled
        assert _stage2_provider_enabled() is False

    def test_openai_wrapper_enabled_via_base_url(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        from app.engines.graph_rag import _stage2_provider_enabled
        assert _stage2_provider_enabled() is True

    def test_anthropic_enabled_via_api_key(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The R56 hardening: ``P2P_GRAPH_RAG_PROVIDER=anthropic`` +
        ``P2P_GRAPH_RAG_API_KEY=...`` activates Stage-2 polish."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )
        from app.engines.graph_rag import _stage2_provider_enabled
        assert _stage2_provider_enabled() is True

    def test_anthropic_without_key_disables_stage2(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``P2P_GRAPH_RAG_PROVIDER=anthropic`` but no API key → Stage-2
        OFF, never raises."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.engines.graph_rag import _stage2_provider_enabled
        assert _stage2_provider_enabled() is False


# ─── 2. _anthropic_complete_for_graph_rag fail-soft contract ─────────────────


class TestAnthropicCompleteFailSoft:
    def test_no_key_returns_none(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=10, temperature=0.0,
        )
        assert result is None

    def test_sdk_import_error_returns_none(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mock anthropic SDK absence — _get_anthropic_client returns None,
        the higher-level function returns None too."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        orig_import = _builtins.__import__

        def _no_anthropic(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("not installed")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(_builtins, "__import__", _no_anthropic)
        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=10, temperature=0.0,
        )
        assert result is None

    def test_rate_limit_error_returns_none(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mocked RateLimitError → graph_rag wrapper falls back."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        class _RateLimitErrorMock(Exception):
            pass
        _RateLimitErrorMock.__name__ = "RateLimitError"

        class _Anthropic:
            def __init__(self, *a, **kw): pass

            class _Messages:
                @staticmethod
                def create(*a, **kw):
                    raise _RateLimitErrorMock("429 rate limited")

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=10, temperature=0.0,
        )
        assert result is None

    def test_authentication_error_returns_none(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-broken"), raising=True
        )

        class _AuthErr(Exception):
            pass
        _AuthErr.__name__ = "AuthenticationError"

        class _Anthropic:
            def __init__(self, *a, **kw): pass

            class _Messages:
                @staticmethod
                def create(*a, **kw):
                    raise _AuthErr("invalid x-api-key")

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="s", user="u", max_tokens=10, temperature=0.0,
        )
        assert result is None

    def test_empty_content_block_returns_none(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        class _Resp:
            content = []  # empty content block

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

    def test_happy_path_returns_text(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        class _Block:
            text = "Article 13 requires logs."

        class _Resp:
            content = [_Block()]

        captured: dict[str, object] = {}

        class _Anthropic:
            def __init__(self, *a, **kw):
                captured["init_kwargs"] = kw

            class _Messages:
                @staticmethod
                def create(**kw):
                    captured["create_kwargs"] = kw
                    return _Resp()

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        result = _anthropic_complete_for_graph_rag(
            system="hello", user="ping", max_tokens=64, temperature=0.0,
        )
        assert result == "Article 13 requires logs."
        # Default model when unset comes from settings.graph_rag.model.
        kwargs = captured["create_kwargs"]
        assert kwargs["model"] == settings.graph_rag.model
        assert kwargs["max_tokens"] == 64
        assert kwargs["temperature"] == 0.0
        assert kwargs["system"] == "hello"
        assert kwargs["messages"] == [{"role": "user", "content": "ping"}]
        # Thinking off by default — no thinking= kwarg.
        assert "thinking" not in kwargs

    def test_complex_question_enables_extended_thinking(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R51 thinking-token routing fires through the Anthropic SDK
        when ``complex_question=True`` AND ``complex_thinking_tokens > 0``
        AND ``complex_model`` is configured.

        **R81-A1**: ``complex_model`` is now empty by default — this
        test pins the operator-override path (set
        ``P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-4-7`` to restore
        the pre-R81-A1 behaviour) so it still exercises the swap +
        extended-thinking surface."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )
        # R103: complex_model defaults to claude-opus-4-8 and
        # complex_thinking_tokens to 0 (extended thinking OFF by default).
        # Override BOTH on this test only so the swap + extended-thinking
        # surface under test still fires.
        original_complex = settings.graph_rag.complex_model
        original_thinking = settings.graph_rag.complex_thinking_tokens
        settings.graph_rag.complex_model = "claude-opus-4-7"
        settings.graph_rag.complex_thinking_tokens = 2500

        class _Block:
            text = "Polished prose."

        class _Resp:
            content = [_Block()]

        captured: dict[str, object] = {}

        class _Anthropic:
            def __init__(self, *a, **kw): pass

            class _Messages:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    return _Resp()

            messages = _Messages()

        import anthropic as _ant
        monkeypatch.setattr(_ant, "Anthropic", _Anthropic)

        from app.engines.graph_rag import _anthropic_complete_for_graph_rag
        try:
            result = _anthropic_complete_for_graph_rag(
                system="s", user="u", max_tokens=512, temperature=0.0,
                complex_question=True,
            )
        finally:
            settings.graph_rag.complex_model = original_complex
            settings.graph_rag.complex_thinking_tokens = original_thinking
        assert result == "Polished prose."
        # complex_model swaps to claude-opus-4-7 because we set it
        # explicitly above (mirroring an operator override).
        assert captured["model"] == "claude-opus-4-7"
        # Thinking kwarg present, budget clamped to [1024, 16000].
        thinking = captured["thinking"]
        assert thinking["type"] == "enabled"
        assert 1024 <= thinking["budget_tokens"] <= 16000


# ─── 3. _claude_max_enhance_answer routes via provider ───────────────────────


class TestStage2EnhanceRouting:
    def test_anthropic_provider_routes_through_sdk(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When provider=anthropic, Stage-2 polish goes through the SDK,
        not the openai_wrapper."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        anthropic_called = {"n": 0}
        wrapper_called = {"n": 0}

        def _fake_anthropic(**kwargs):
            anthropic_called["n"] += 1
            return "anthropic polished"

        def _fake_wrapper(**kwargs):
            wrapper_called["n"] += 1
            return "wrapper polished"

        from app.engines import graph_rag as gr
        monkeypatch.setattr(
            gr, "_anthropic_complete_for_graph_rag", _fake_anthropic
        )
        monkeypatch.setattr(
            gr, "_openai_wrapper_complete_for_graph_rag", _fake_wrapper
        )

        from app.engines.graph_rag import (
            GraphContext, _claude_max_enhance_answer,
        )
        result = _claude_max_enhance_answer(
            question="What does Art. 13 require?",
            kg_answer="Art. 13 requires technical documentation.",
            context=GraphContext(),
        )
        assert result == "anthropic polished"
        assert anthropic_called["n"] == 1
        assert wrapper_called["n"] == 0

    def test_openai_wrapper_provider_still_routes_through_wrapper(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing wrapper path unchanged — R56 must not regress it."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        anthropic_called = {"n": 0}
        wrapper_called = {"n": 0}

        def _fake_anthropic(**kwargs):
            anthropic_called["n"] += 1
            return "anthropic polished"

        def _fake_wrapper(**kwargs):
            wrapper_called["n"] += 1
            return "wrapper polished"

        from app.engines import graph_rag as gr
        monkeypatch.setattr(
            gr, "_anthropic_complete_for_graph_rag", _fake_anthropic
        )
        monkeypatch.setattr(
            gr, "_openai_wrapper_complete_for_graph_rag", _fake_wrapper
        )

        from app.engines.graph_rag import (
            GraphContext, _claude_max_enhance_answer,
        )
        result = _claude_max_enhance_answer(
            question="Q", kg_answer="A", context=GraphContext(),
        )
        assert result == "wrapper polished"
        assert wrapper_called["n"] == 1
        assert anthropic_called["n"] == 0


# ─── 4. _two_stage_generate end-to-end through anthropic ─────────────────────


class TestTwoStageGenerateAnthropic:
    def test_anthropic_stage2_fires_on_complex_question(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With P2P_GRAPH_RAG_PROVIDER=anthropic + key + a 'complex enough'
        question, Stage-2 polish runs via the anthropic SDK and the polished
        prose lands in the response tuple."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        def _fake_anthropic(**kwargs):
            return "Refined regulatory prose with cite (Article 13)."

        from app.engines import graph_rag as gr
        monkeypatch.setattr(
            gr, "_anthropic_complete_for_graph_rag", _fake_anthropic
        )
        # Force _needs_stage2_enhancement to return True for this test
        # (independent of the specific question shape).
        monkeypatch.setattr(
            gr, "_needs_stage2_enhancement", lambda *a, **kw: True
        )
        # Skip classification short-circuit.
        monkeypatch.setattr(
            gr, "_detect_classification_topic", lambda q: None
        )
        # Skip the post-Stage-2 hallucination + self-contradiction guards
        # for this isolated test.
        monkeypatch.setattr(
            gr, "_polished_prose_has_unknown_citations",
            lambda prose, ctx: (False, None),
        )
        monkeypatch.setattr(
            gr, "_polished_prose_self_contradicts_refs",
            lambda prose, ctx: (False, None),
        )

        from app.engines.graph_rag import (
            GraphContext, _two_stage_generate,
        )
        # Provide a minimal context with one reference so the prompt's
        # ground-truth block is non-empty.
        ctx = GraphContext(
            article_info=[
                {"id": "Art. 13", "text": "Transparency obligations for HRAIS."},
            ],
        )
        answer, used = _two_stage_generate(
            "What are the transparency obligations for high-risk AI systems?",
            ctx,
        )
        assert used is True
        assert answer == "Refined regulatory prose with cite (Article 13)."

    def test_anthropic_stage2_fallback_on_call_failure(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If _anthropic_complete_for_graph_rag returns None (failure),
        Stage-2 falls back to the KG answer and marks stage2_call_failed."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        from app.engines import graph_rag as gr
        monkeypatch.setattr(
            gr, "_anthropic_complete_for_graph_rag",
            lambda **kw: None,  # simulated failure
        )
        monkeypatch.setattr(
            gr, "_needs_stage2_enhancement", lambda *a, **kw: True
        )
        monkeypatch.setattr(
            gr, "_detect_classification_topic", lambda q: None
        )

        from app.engines.graph_rag import (
            GraphContext, _two_stage_generate,
        )
        ctx = GraphContext()
        answer, used = _two_stage_generate("complex multi-turn q", ctx)
        assert used is False
        assert ctx.stage2_call_failed is True


# ─── 5. Engine cache key folds in the resolved provider ──────────────────────


class TestEngineCacheKeyProvider:
    def test_cache_key_differs_per_provider(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        key_anthropic = _engine_cache_key("Q", "ctx")

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        key_wrapper = _engine_cache_key("Q", "ctx")

        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        key_cli = _engine_cache_key("Q", "ctx")

        # All three must be distinct — provider must be in the identity.
        assert len({key_anthropic, key_wrapper, key_cli}) == 3

    def test_cache_key_stable_for_same_provider(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        a1 = _engine_cache_key("Q", "ctx")
        a2 = _engine_cache_key("Q", "ctx")
        assert a1 == a2


# ─── 6. _get_anthropic_client smoke ──────────────────────────────────────────


class TestGetAnthropicClient:
    def test_returns_none_when_no_key(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines.graph_rag import _get_anthropic_client
        assert _get_anthropic_client() is None

    def test_returns_client_when_key_set(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("anthropic")
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        import anthropic as _ant
        sentinel = MagicMock(name="anthropic.Anthropic-instance")
        monkeypatch.setattr(
            _ant, "Anthropic", lambda **kw: sentinel
        )
        from app.engines.graph_rag import _get_anthropic_client
        client = _get_anthropic_client()
        assert client is sentinel

    def test_returns_none_when_sdk_missing(
        self, reset_anthropic_env, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import settings
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )
        orig_import = _builtins.__import__

        def _no_anthropic(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("not installed")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(_builtins, "__import__", _no_anthropic)
        from app.engines.graph_rag import _get_anthropic_client
        assert _get_anthropic_client() is None
