"""Round 52 — Groq Stage-0 intent provider routing tests.

The intent classifier now picks between two pooled provider singletons:

* The Claude-Max ``openai_wrapper`` (Haiku 4.5 by default) — current
  default, expensive on Pro after the planned downgrade.
* Groq's OpenAI-compatible endpoint (Llama 3.3 70B Versatile by
  default) — ~$0.50/mo at the project's volume, ~3× faster than Haiku.

The selection lives in ``_resolve_intent_provider``. Critical
invariants:

1. ``REGENOLD_INTENT_PROVIDER=groq`` without ``GROQ_API_KEY`` falls
   back to the wrapper. (No surprise silent disablement.)
2. ``GROQ_API_KEY`` set without ``REGENOLD_INTENT_PROVIDER=groq``
   stays on the wrapper. (Opt-in only.)
3. The wrapper singleton is NOT constructed when Groq is active —
   protects the Stage-1/2 polish path's pooled httpx client from
   piggybacking on an env-mutation race.
4. Cache key includes the model, so Groq and wrapper results don't
   collide on the same question.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.llm import intent_classifier as ic
from app.llm import openai_wrapper_provider as owp
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


@pytest.fixture(autouse=True)
def _reset() -> None:
    ic._reset_for_tests()
    owp._reset_groq_singleton_for_tests()
    yield
    ic._reset_for_tests()
    owp._reset_groq_singleton_for_tests()


# ── is_groq_intent_provider_enabled ──────────────────────────────────────────


def test_groq_disabled_when_provider_var_missing(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert owp.is_groq_intent_provider_enabled() is False


def test_groq_disabled_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert owp.is_groq_intent_provider_enabled() is False


def test_groq_disabled_when_api_key_blank(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    assert owp.is_groq_intent_provider_enabled() is False


def test_groq_enabled_when_both_set(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert owp.is_groq_intent_provider_enabled() is True


def test_groq_provider_var_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "GROQ")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert owp.is_groq_intent_provider_enabled() is True


# ── Singleton lifecycle ──────────────────────────────────────────────────────


def test_groq_singleton_uses_groq_defaults(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_BASE", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    provider = owp.get_groq_intent_provider()
    assert provider._base_url == "https://api.groq.com/openai/v1"
    assert provider._api_key == "gsk_test"


def test_groq_singleton_honours_api_base_override(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_BASE", "https://proxy.example.com/v1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    provider = owp.get_groq_intent_provider()
    assert provider._base_url == "https://proxy.example.com/v1"


def test_groq_singleton_independent_of_wrapper_singleton(monkeypatch) -> None:
    """Two singletons must coexist — Stage-1/2 polish on the wrapper, Stage-0
    on Groq."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    wrapper = owp.get_openai_wrapper_provider()
    groq = owp.get_groq_intent_provider()
    assert wrapper is not groq
    assert wrapper._base_url != groq._base_url


# ── _resolve_intent_provider ─────────────────────────────────────────────────


def test_resolve_returns_none_when_no_provider_configured(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert ic._resolve_intent_provider() is None
    assert ic.is_intent_enabled() is False


def test_resolve_picks_wrapper_when_only_wrapper_configured(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    selection = ic._resolve_intent_provider()
    assert selection is not None
    provider, model = selection
    assert model == ic._DEFAULT_MODEL  # claude-haiku-4-5-20251001 by default
    assert provider is owp.get_openai_wrapper_provider()


def test_resolve_picks_groq_when_groq_configured(monkeypatch) -> None:
    """Even with the wrapper available, Groq wins when explicitly chosen."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    selection = ic._resolve_intent_provider()
    assert selection is not None
    provider, model = selection
    assert model == ic._DEFAULT_GROQ_MODEL  # llama-3.3-70b-versatile
    assert provider is owp.get_groq_intent_provider()


def test_resolve_falls_back_to_wrapper_when_groq_misconfigured(monkeypatch) -> None:
    """REGENOLD_INTENT_PROVIDER=groq but no GROQ_API_KEY → wrapper, not None."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    selection = ic._resolve_intent_provider()
    assert selection is not None
    _, model = selection
    assert model == ic._DEFAULT_MODEL  # Haiku, not Groq Llama


# ── End-to-end classification through Groq ───────────────────────────────────


def test_classify_routes_through_groq_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    captured_models: list[str] = []

    class FakeGroqProvider:
        def complete(self, req):
            captured_models.append(req.model)
            return OpenAIWrapperResponse(
                text=(
                    '{"intent": "penalty_inquiry", '
                    '"primary_anchor": "Art. 99", '
                    '"alternate_anchors": [], "confidence": 0.9}'
                ),
                model=req.model,
                elapsed_ms=120,
            )

    fake = FakeGroqProvider()
    # NOTE: patch on ``ic.get_groq_intent_provider`` (the from-import binding
    # in the consumer module), not on ``owp`` — same convention as the
    # existing test_intent_classifier.py wrapper tests.
    with patch.object(ic, "get_groq_intent_provider", return_value=fake):
        result = ic.classify_intent("What's the max fine?")

    assert result is not None
    assert result.intent == "penalty_inquiry"
    assert captured_models == ["llama-3.3-70b-versatile"]


def test_classify_does_not_call_wrapper_when_groq_active(monkeypatch) -> None:
    """Critical invariant — Stage-1/2 polish pool stays warm only for its
    own callers. Groq path must NOT spin up the wrapper singleton."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    wrapper_calls = {"n": 0}

    class FakeWrapper:
        def complete(self, _req):
            wrapper_calls["n"] += 1
            raise AssertionError("wrapper called in groq mode")

    class FakeGroq:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text='{"intent": "definition", "primary_anchor": "Art. 3", "alternate_anchors": [], "confidence": 0.85}',
                model="llama-3.3-70b-versatile",
                elapsed_ms=90,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeWrapper()), \
         patch.object(ic, "get_groq_intent_provider", return_value=FakeGroq()):
        result = ic.classify_intent("What is an 'AI system'?")

    assert result is not None
    assert wrapper_calls["n"] == 0


def test_classify_groq_override_model(monkeypatch) -> None:
    """REGENOLD_INTENT_MODEL_GROQ should override the default model.

    This matters because Groq's catalog changes — when llama-3.3-70b is
    deprecated, operators flip the env var instead of editing code.
    """
    monkeypatch.setenv("REGENOLD_INTENT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("REGENOLD_INTENT_MODEL_GROQ", "llama-4-scout-17b")
    # Module-level constant was bound at import — reload to pick up the new
    # env value, then patch the RELOADED module's from-import binding.
    import importlib

    import app.llm.intent_classifier as ic_module

    importlib.reload(ic_module)
    try:
        captured: list[str] = []

        class FakeGroq:
            def complete(self, req):
                captured.append(req.model)
                return OpenAIWrapperResponse(
                    text='{"intent": "definition", "primary_anchor": "Art. 3", "alternate_anchors": [], "confidence": 0.7}',
                    model=req.model,
                    elapsed_ms=80,
                )

        with patch.object(ic_module, "get_groq_intent_provider", return_value=FakeGroq()):
            ic_module.classify_intent("Define provider")
        assert captured == ["llama-4-scout-17b"]
    finally:
        monkeypatch.delenv("REGENOLD_INTENT_MODEL_GROQ", raising=False)
        importlib.reload(ic_module)


# ── Cache key isolation ──────────────────────────────────────────────────────


def test_cache_key_separates_groq_and_wrapper_results(monkeypatch) -> None:
    """Same question, different models → distinct cache keys. Otherwise an
    operator A/Bing the two paths back-to-back would see the second result
    cache-hit on the first's value."""
    haiku_key = ic._cache_key("What is GPAI?", "claude-haiku-4-5-20251001")
    groq_key = ic._cache_key("What is GPAI?", "llama-3.3-70b-versatile")
    assert haiku_key != groq_key
