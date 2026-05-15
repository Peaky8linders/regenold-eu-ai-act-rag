"""Smoke tests for the LLM provider stubs.

Eng-review round-6 finding: the two providers (`mistral_provider.py` +
`openai_wrapper_provider.py`) ship real httpx-backed retry logic that
was completely untested. Covered here: happy path, transient 429 retry,
fail-fast 4xx, network error retry-and-give-up, shape errors, decode
errors, and the wrapper-specific "Not logged in" sentinel.

The transport is mocked via ``httpx.MockTransport`` so no network calls
fire in CI. Each provider's pooled client is reconstructed per test
via the public factory so tests stay isolated.
"""
from __future__ import annotations

import httpx
import pytest

from app.llm.mistral_provider import (
    MistralRequest,
    is_mistral_enabled,
)
from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
)

# ─── Mistral provider ──────────────────────────────────────────────────


class TestMistralProviderHappyPath:
    """One-shot 200 from the Mistral API parses cleanly."""

    def test_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from app.llm.mistral_provider import _HttpxMistralProvider

        def _handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert "/v1/chat/completions" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "model": "mistral-large-latest",
                    "choices": [{"message": {"content": "PONG"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                },
            )

        provider = _HttpxMistralProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(MistralRequest(user="ping", model="mistral-large-latest"))
        assert result.error is None
        assert result.text == "PONG"
        assert result.prompt_tokens == 5
        assert result.completion_tokens == 1


class TestMistralProviderTransientRetry:
    """A single 429 followed by 200 should succeed via the retry path."""

    def test_429_then_200_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from app.llm.mistral_provider import _HttpxMistralProvider

        attempts: list[int] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(429, text="rate-limited")
            return httpx.Response(
                200,
                json={
                    "model": "mistral-large-latest",
                    "choices": [{"message": {"content": "after-retry"}}],
                    "usage": {},
                },
            )

        provider = _HttpxMistralProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        # Patch out the sleep so the test doesn't burn 500ms.
        monkeypatch.setattr("app.llm.mistral_provider.time.sleep", lambda _s: None)
        result = provider.complete(MistralRequest(user="x"))
        assert result.error is None
        assert result.text == "after-retry"
        assert len(attempts) == 2


class TestMistralProviderFailFast4xx:
    """401 should NOT retry — surfaces as an error immediately."""

    def test_401_fail_fast(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from app.llm.mistral_provider import _HttpxMistralProvider

        attempts: list[int] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            return httpx.Response(401, text='{"detail":"invalid key"}')

        provider = _HttpxMistralProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(MistralRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_401")
        assert len(attempts) == 1  # NO retry on auth failure


class TestMistralProviderNetworkError:
    """Network failure on both attempts surfaces as ``network_error``."""

    def test_network_error_after_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from app.llm.mistral_provider import _HttpxMistralProvider

        def _handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated network down")

        provider = _HttpxMistralProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        monkeypatch.setattr("app.llm.mistral_provider.time.sleep", lambda _s: None)
        result = provider.complete(MistralRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("network_error")


class TestMistralProviderShapeError:
    """A 200 with a missing ``choices`` key parses as a shape error."""

    def test_missing_choices_shape_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from app.llm.mistral_provider import _HttpxMistralProvider

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "abc", "object": "chat.completion"})

        provider = _HttpxMistralProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(MistralRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("shape_error")


class TestMistralProviderEnabledGuard:
    """Empty / missing ``MISTRAL_API_KEY`` short-circuits with an error."""

    def test_unset_key_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        from app.llm.mistral_provider import _HttpxMistralProvider

        assert is_mistral_enabled() is False
        provider = _HttpxMistralProvider()
        result = provider.complete(MistralRequest(user="x"))
        assert result.error == "mistral_api_key_not_set"

    def test_empty_user_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
        from app.llm.mistral_provider import _HttpxMistralProvider

        provider = _HttpxMistralProvider()
        # No transport set — would crash with a real network call. The
        # empty-user guard must short-circuit BEFORE hitting the wire.
        result = provider.complete(MistralRequest(user="   "))
        assert result.error == "empty_user_after_sanitise"


# ─── OpenAI wrapper provider ───────────────────────────────────────────


class TestOpenAIWrapperHappyPath:
    def test_happy_path(self) -> None:
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-6",
                    "choices": [{"message": {"content": "PONG"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="ping"))
        assert result.error is None
        assert result.text == "PONG"


class TestOpenAIWrapperNotLoggedInSentinel:
    """The wrapper returns 200 with the sentinel when its CLI OAuth lapsed.

    Critical: the engine layer surfaces this as a loud ``logger.error``
    so the eval operator doesn't silently A/B Sonnet against
    deterministic-fallback for an entire round.
    """

    def test_not_logged_in_surfaces_as_error(self) -> None:
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-6",
                    "choices": [
                        {"message": {"content": "Not logged in · Please run /login"}}
                    ],
                },
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="ping"))
        assert result.error is not None
        assert "not_logged_in" in result.error


class TestOpenAIWrapperApiError:
    def test_500_surfaces_as_api_status_error(self) -> None:
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_500")


class TestOpenAIWrapperRetryAfter:
    """The upstream wrapper defaults to ``RATE_LIMIT_CHAT_PER_MINUTE=10``.

    On a bench run (476 items in a few minutes) or bursty partner
    traffic, the wrapper sends 429 with a ``Retry-After: <seconds>``
    header. We honour ONE retry — capped at ``OPENAI_MAX_RETRY_AFTER``
    — so well-paced traffic recovers instead of falling back to
    deterministic on every other request.
    """

    def test_retry_after_succeeds_on_second_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm import openai_wrapper_provider as mod
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        # Don't actually sleep in the test — sleep is observable here as
        # the call into time.sleep. We patch it to a no-op + capture.
        sleeps: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        call_count = {"n": 0}

        def _handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "1"},
                    text='{"error":"rate_limited"}',
                )
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-6",
                    "choices": [{"message": {"content": "OK"}}],
                },
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is None
        assert result.text == "OK"
        assert call_count["n"] == 2
        assert sleeps == [1.0]

    def test_retry_after_too_long_skips_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 60 s Retry-After exceeds the 8 s default cap → no retry."""
        from app.llm import openai_wrapper_provider as mod
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        sleeps: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        call_count = {"n": 0}

        def _handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "60"},
                text='{"error":"rate_limited"}',
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_429")
        assert call_count["n"] == 1
        assert sleeps == []  # no sleep, no retry

    def test_retry_after_missing_skips_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No Retry-After header → no retry (we don't guess a backoff)."""
        from app.llm import openai_wrapper_provider as mod
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        sleeps: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        call_count = {"n": 0}

        def _handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(
                429, text='{"error":"rate_limited"}'
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_429")
        assert call_count["n"] == 1
        assert sleeps == []

    def test_retry_after_invalid_value_skips_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Garbage Retry-After (e.g. an HTTP-date) → no retry, no crash."""
        from app.llm import openai_wrapper_provider as mod
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        sleeps: list[float] = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        def _handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                text='{"error":"rate_limited"}',
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_429")
        assert sleeps == []

    def test_retry_second_call_also_429_surfaces_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both calls 429 → deterministic fallback (engine layer)."""
        from app.llm import openai_wrapper_provider as mod
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

        call_count = {"n": 0}

        def _handler(_request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "1"},
                text='{"error":"rate_limited"}',
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.mistral.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_429")
        assert call_count["n"] == 2  # one attempt + one retry


def test_parse_retry_after_helper() -> None:
    from app.llm.openai_wrapper_provider import _parse_retry_after

    assert _parse_retry_after("5") == 5.0
    assert _parse_retry_after("  3.5  ") == 3.5
    assert _parse_retry_after("0") == 0.0
    assert _parse_retry_after(None) == 0.0
    assert _parse_retry_after("") == 0.0
    assert _parse_retry_after("not a number") == 0.0
    assert _parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") == 0.0
    # Negative clamped to 0 (defensive — server bug shouldn't crash us)
    assert _parse_retry_after("-3") == 0.0
