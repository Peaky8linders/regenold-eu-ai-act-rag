"""R433 — quota-aware query-denoiser failover."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.integrations.regenold import reasoning_trace as rt
from app.routes import regenold as route


def _msg(role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content)


def _provider(*, error: str | None = None, text: str = "") -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = SimpleNamespace(
        error=error, text=text, finish_reason="stop"
    )
    return provider


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://wrapper.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.setenv("REGENOLD_DENOISER_QUOTA_COOLDOWN", "60")
    route._reset_denoiser_quota_cooldowns()
    yield
    route._reset_denoiser_quota_cooldowns()


def test_quota_error_is_classified_but_transient_error_is_not() -> None:
    assert route._denoiser_quota_error("api_status_429: tokens per day exceeded")
    assert route._denoiser_quota_error("quota_exceeded")
    assert not route._denoiser_quota_error("network_error: timed out")
    assert not route._denoiser_quota_error("HTTP 500 upstream unavailable")


def test_quota_cooldown_is_provider_specific_and_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((100.0, 100.0, 159.0, 161.0))
    monkeypatch.setattr(route.time, "monotonic", lambda: next(clock))
    route._mark_denoiser_provider_quota("groq")
    assert route._denoiser_provider_suppressed("groq")
    assert not route._denoiser_provider_suppressed("wrapper")
    assert not route._denoiser_provider_suppressed("groq")


def test_cache_key_includes_quota_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_DENOISER_QUOTA_COOLDOWN", "60")
    first = route._engine_cache_key("What is Article 6?", None)
    monkeypatch.setenv("REGENOLD_DENOISER_QUOTA_COOLDOWN", "120")
    second = route._engine_cache_key("What is Article 6?", None)
    assert first != second


def test_exhausted_groq_skips_next_request_and_uses_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TPD response must not be paid again on the next request."""
    groq = _provider(error="api_status_429: tokens per day limit reached")
    wrapper = _provider(text="Article 5 prohibits the practice.")
    import app.llm.openai_wrapper_provider as providers

    monkeypatch.setattr(providers, "is_groq_intent_provider_enabled", lambda: True)
    monkeypatch.setattr(providers, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(providers, "get_groq_intent_provider", lambda: groq)
    monkeypatch.setattr(providers, "get_openai_wrapper_provider", lambda: wrapper)
    trace = rt.activate()
    try:
        route._rewrite_multiturn_query(
            "Are they prohibited?",
            [_msg("user", "Tell me about emotion recognition.")],
        )
        route._rewrite_multiturn_query(
            "Are they prohibited?",
            [_msg("user", "Tell me about emotion recognition.")],
        )
    finally:
        rt.deactivate()
    assert groq.complete.call_count == 1
    assert wrapper.complete.call_count == 2
    assert trace.query_denoiser["fired"] is True
