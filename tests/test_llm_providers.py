"""Smoke tests for the LLM provider stubs.

Eng-review round-6 finding: the ``openai_wrapper_provider.py`` ships
real httpx-backed retry logic that was completely untested. Covered
here: happy path, the wrapper-specific "Not logged in" sentinel, API
errors, Retry-After 429 handling, and per-call timeout behaviour.

The transport is mocked via ``httpx.MockTransport`` so no network calls
fire in CI. The provider's pooled client is reconstructed per test
via the public factory so tests stay isolated.
"""
from __future__ import annotations

import httpx
import pytest

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
)

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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
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
            base_url="https://api.wrapper.test",
        )
        result = provider.complete(OpenAIWrapperRequest(user="x"))
        assert result.error is not None
        assert result.error.startswith("api_status_429")
        assert call_count["n"] == 2  # one attempt + one retry


class TestOpenAIWrapperPerCallTimeout:
    """Per-request ``timeout_seconds`` overrides the singleton default.

    The bug this fixes: the intent classifier used to mutate
    ``OPENAI_TIMEOUT_SECONDS=2.5`` env var before constructing the
    singleton, then restore. Since the singleton is process-wide, all
    subsequent Stage-1/2 Sonnet calls inherited the 2.5 s cap and
    timed out (Sonnet through the wrapper takes 10-20 s). Now the
    timeout lives on the request, not the env.
    """

    def test_request_timeout_override_passed_to_post(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        captured_timeouts: list[object] = []

        def _handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"model": "x", "choices": [{"message": {"content": "ok"}}]},
            )

        provider = _OpenAIWrapperProvider()
        provider._timeout = 60.0  # singleton default
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.test.invalid",
        )

        # Wrap the client to capture the per-call timeout kwarg.
        orig_post = provider._client.post

        def _capturing_post(url, **kwargs):  # type: ignore[no-untyped-def]
            captured_timeouts.append(kwargs.get("timeout"))
            return orig_post(url, **kwargs)

        provider._client.post = _capturing_post  # type: ignore[assignment]

        # Default — no per-request override → use singleton timeout.
        provider.complete(OpenAIWrapperRequest(user="ping"))
        assert captured_timeouts[-1] == 60.0

        # Short override — should NOT poison subsequent calls.
        provider.complete(
            OpenAIWrapperRequest(user="quick", timeout_seconds=2.5)
        )
        assert captured_timeouts[-1] == 2.5

        # Next call without override — should be 60 again (no poisoning).
        provider.complete(OpenAIWrapperRequest(user="back to normal"))
        assert captured_timeouts[-1] == 60.0

    def test_singleton_default_is_60s_not_8s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression for the round-29 8s-default-killed-Sonnet bug."""
        monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        provider = _OpenAIWrapperProvider()
        assert provider._timeout == 60.0


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
