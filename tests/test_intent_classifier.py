"""Tests for the intent classifier — wrapper mocked, no network.

The classifier MUST be a no-op when the wrapper is unconfigured or
unreachable (that's the production safety contract — the engine falls
through to the deterministic path on any failure). These tests pin
that invariant and exercise the JSON-parsing, caching, and
circuit-breaker paths.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.llm import intent_classifier as ic
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Wipe cache + breaker between tests."""
    ic._reset_for_tests()
    yield
    ic._reset_for_tests()


# ── Disabled paths ───────────────────────────────────────────────────────────


def test_classifier_returns_none_when_wrapper_disabled(monkeypatch) -> None:
    """No ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` → instant ``None``."""
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not ic.is_intent_enabled()
    assert ic.classify_intent("What does Art. 13 require?") is None


def test_classifier_returns_none_on_empty_question() -> None:
    """Empty input short-circuits without touching the wrapper."""
    assert ic.classify_intent("") is None
    assert ic.classify_intent("   ") is None


def test_classifier_returns_none_on_wrapper_error(monkeypatch) -> None:
    """Wrapper error → classifier returns None (engine falls through)."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                error="network_error: connection refused",
                model="claude-haiku-4-5",
                elapsed_ms=42,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        assert ic.classify_intent("What's the max penalty?") is None


def test_classifier_returns_none_on_not_logged_in(monkeypatch) -> None:
    """Wrapper sentinel ``Not logged in`` already maps to ``error`` in
    the provider — classifier path treats it as a failure.
    """
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                error="wrapper_not_logged_in: Please run /login",
                model="claude-haiku-4-5",
                elapsed_ms=10,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        assert ic.classify_intent("Test") is None


# ── Happy path ───────────────────────────────────────────────────────────────


def test_classifier_parses_valid_json_response(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text=(
                    '{"intent": "penalty_inquiry", "primary_anchor": "Art. 99", '
                    '"alternate_anchors": [], "confidence": 0.95}'
                ),
                model="claude-haiku-4-5",
                elapsed_ms=180,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        result = ic.classify_intent("What's the maximum fine for prohibited AI?")

    assert result is not None
    assert result.intent == "penalty_inquiry"
    assert result.primary_anchor == "Art. 99"
    assert result.confidence == pytest.approx(0.95)
    assert result.cache_hit is False
    assert result.elapsed_ms >= 0  # mock provider may return in 0ms


def test_classifier_handles_prose_preamble(monkeypatch) -> None:
    """Haiku occasionally prefixes the JSON with ``Here is the JSON:``
    — the parser strips it.
    """
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text=(
                    "Here is the JSON:\n"
                    '{"intent": "fria", "primary_anchor": "Art. 27", '
                    '"alternate_anchors": [], "confidence": 0.88}\n'
                    "Hope that helps!"
                ),
                model="claude-haiku-4-5",
                elapsed_ms=200,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        result = ic.classify_intent("Who has to do a FRIA?")

    assert result is not None
    assert result.intent == "fria"
    assert result.primary_anchor == "Art. 27"


def test_classifier_injects_default_anchor_when_missing(monkeypatch) -> None:
    """Model returns intent but no primary_anchor → taxonomy default fills in."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text='{"intent": "penalty_inquiry", "primary_anchor": "", "alternate_anchors": [], "confidence": 0.8}',
                model="claude-haiku-4-5",
                elapsed_ms=150,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        result = ic.classify_intent("Max fine?")

    assert result is not None
    assert result.primary_anchor == "Art. 99"  # Filled from INTENT_PRIMARY_ANCHOR


# ── Error / malformed paths ──────────────────────────────────────────────────


def test_classifier_rejects_unknown_intent_label(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text='{"intent": "rocket_science", "primary_anchor": "Art. 99", "alternate_anchors": [], "confidence": 0.9}',
                model="claude-haiku-4-5",
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        assert ic.classify_intent("Test") is None


def test_classifier_rejects_malformed_anchor(monkeypatch) -> None:
    """``primary_anchor`` must match the strict shape regex; otherwise
    it falls back to the taxonomy default (or empty)."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text='{"intent": "fria", "primary_anchor": "Article 27(1)(a)", "alternate_anchors": [], "confidence": 0.9}',
                model="claude-haiku-4-5",
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        result = ic.classify_intent("Test")

    assert result is not None
    # Malformed primary → fall back to taxonomy default for "fria" → Art. 27
    assert result.primary_anchor == "Art. 27"


def test_classifier_handles_unparseable_response(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FakeProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                text="I don't think I can classify this.",
                model="claude-haiku-4-5",
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        assert ic.classify_intent("Test") is None


# ── Cache ────────────────────────────────────────────────────────────────────


def test_classifier_caches_repeated_questions(monkeypatch) -> None:
    """A repeated question hits the cache; the provider is called once."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    call_count = {"n": 0}

    class FakeProvider:
        def complete(self, _req):
            call_count["n"] += 1
            return OpenAIWrapperResponse(
                text='{"intent": "definition", "primary_anchor": "Art. 3", "alternate_anchors": [], "confidence": 0.92}',
                model="claude-haiku-4-5",
                elapsed_ms=180,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FakeProvider()):
        first = ic.classify_intent("What is an AI system?")
        second = ic.classify_intent("What is an AI system?")
        third = ic.classify_intent("WHAT IS AN AI SYSTEM?")  # case-insensitive cache key

    assert first is not None and not first.cache_hit
    assert second is not None and second.cache_hit
    assert third is not None and third.cache_hit
    assert call_count["n"] == 1


# ── Circuit breaker ──────────────────────────────────────────────────────────


def test_breaker_opens_after_threshold_failures(monkeypatch) -> None:
    """N consecutive failures → ``is_intent_enabled()`` returns False
    even though the wrapper env is set — protects latency budget.
    """
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    class FailingProvider:
        def complete(self, _req):
            return OpenAIWrapperResponse(
                error="network_error: refused",
                model="claude-haiku-4-5",
                elapsed_ms=5,
            )

    with patch.object(ic, "get_openai_wrapper_provider", return_value=FailingProvider()):
        # Each unique question triggers a wrapper call.
        for i in range(ic._FAILURE_THRESHOLD):
            assert ic.classify_intent(f"unique question {i}") is None

    # Breaker should now be open — subsequent calls don't even probe.
    assert not ic.is_intent_enabled()
    assert ic.classify_intent("anything else") is None


def test_breaker_resets_on_success(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")

    responses = [
        OpenAIWrapperResponse(error="net err", model="haiku"),
        OpenAIWrapperResponse(error="net err", model="haiku"),
        OpenAIWrapperResponse(
            text='{"intent": "fria", "primary_anchor": "Art. 27", "alternate_anchors": [], "confidence": 0.9}',
            model="haiku",
        ),
    ]

    class StatefulProvider:
        def __init__(self):
            self.idx = 0

        def complete(self, _req):
            resp = responses[self.idx]
            self.idx += 1
            return resp

    with patch.object(ic, "get_openai_wrapper_provider", return_value=StatefulProvider()):
        assert ic.classify_intent("q1") is None  # fail
        assert ic.classify_intent("q2") is None  # fail
        result = ic.classify_intent("q3")        # succeeds → breaker resets
        assert result is not None
        assert ic._BREAKER.failures == 0
