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

import json

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

    @pytest.mark.parametrize(
        "model,temperature_field",
        [
            ("claude-sonnet-5-5", False),
            ("anthropic/claude-sonnet-5-5", False),
            ("eu.anthropic.claude-sonnet-5-5-v1:0", False),
            ("claude-sonnet-5", True),
        ],
    )
    def test_model_sampling_compatibility(self, model: str, temperature_field: bool) -> None:
        """Sonnet 5.5 rejects even temperature=0; legacy models keep their payload."""
        from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

        seen: list[dict[str, object]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"model": model, "choices": [{"message": {"content": "OK"}}]},
            )

        provider = _OpenAIWrapperProvider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.wrapper.test",
        )
        result = provider.complete(
            OpenAIWrapperRequest(user="probe", model=model, temperature=0.0)
        )

        assert result.error is None
        assert ("temperature" in seen[0]) is temperature_field
        assert seen[0]["model"] == model


_WIRE_URL = "https://api.wrapper.test/chat/completions"


def _post_body(model: str, *, temperature: float = 0.0) -> bytes:
    """The exact bytes ``complete()`` posts for ``model``."""
    from app.llm.openai_wrapper_provider import _OpenAIWrapperProvider

    seen: list[bytes] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(
            200, json={"model": model, "choices": [{"message": {"content": "OK"}}]}
        )

    provider = _OpenAIWrapperProvider()
    provider._client = httpx.Client(
        transport=httpx.MockTransport(_handler),
        base_url="https://api.wrapper.test",
    )
    result = provider.complete(
        OpenAIWrapperRequest(
            system="SYS", user="probe", model=model, max_tokens=64, temperature=temperature
        )
    )
    assert result.error is None
    assert len(seen) == 1
    return seen[0]


def _serialised(body: dict[str, object]) -> bytes:
    """Serialise ``body`` with the same encoder the provider's client uses."""
    return httpx.Request("POST", _WIRE_URL, json=body).content


def _main_body(
    model: str, *, temperature: float | None = 0.0, **tail: object
) -> dict[str, object]:
    """The request body ``main`` built: ``temperature`` sits between max_tokens and stream.

    ``temperature=None`` drops the field (the Sonnet 5.5 shape). ``tail`` is whatever
    the provider appends after ``stream`` (Groq's ``reasoning_effort``).
    """
    body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "probe"},
        ],
        "max_tokens": 64,
    }
    if temperature is not None:
        body["temperature"] = temperature
    body["stream"] = False
    body.update(tail)
    return body


class TestSamplingParameterWire:
    """What actually goes on the wire, byte for byte.

    The predicate lives in a choke point shared by Stage-2, Stage-0, the intent
    classifier, query expansion, fusion and the judge, so it is asserted on the
    posted bytes and never on the source text, and in both directions: Sonnet 5.5
    loses ``temperature``, every other model posts exactly what ``main`` posted.
    """

    @pytest.fixture(autouse=True)
    def _plain_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_ALIAS", raising=False)

    @pytest.mark.parametrize(
        "model,tail",
        [
            ("claude-opus-5-5", {}),
            ("claude-sonnet-5", {}),
            ("claude-opus-5", {}),
            ("claude-opus-4-8", {}),
            ("claude-sonnet-4-6", {}),
            ("claude-sonnet-5-50", {}),
            ("anthropic/claude-opus-5-5", {}),
            ("eu.anthropic.claude-opus-4-8", {}),
            ("llama-3.3-70b-versatile", {}),
            ("gemini-2.5-flash", {}),
            ("mistral-large-latest", {}),
            ("qwen/qwen3-32b", {"reasoning_effort": "none"}),
            ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
        ],
    )
    def test_other_models_post_the_exact_bytes_main_posted(
        self, model: str, tail: dict[str, object]
    ) -> None:
        posted = _post_body(model)
        assert posted == _serialised(_main_body(model, **tail))
        assert json.loads(posted)["temperature"] == 0.0

    @pytest.mark.parametrize("temperature", [0.0, 0.1, 0.3, 1.0])
    def test_other_models_keep_whatever_temperature_the_caller_set(
        self, temperature: float
    ) -> None:
        assert _post_body("claude-sonnet-5", temperature=temperature) == _serialised(
            _main_body("claude-sonnet-5", temperature=temperature)
        )

    @pytest.mark.parametrize(
        "model",
        [
            "claude-sonnet-5-5",
            "anthropic/claude-sonnet-5-5",
            "anthropic/claude-sonnet-5.5",
            "claude-sonnet-5-5-20260901",
            "eu.anthropic.claude-sonnet-5-5-v1:0",
            "global.anthropic.claude-sonnet-5-5-v1:0",
        ],
    )
    @pytest.mark.parametrize("temperature", [0.0, 0.1, 0.7])
    def test_sonnet_55_posts_no_temperature_and_nothing_else_changes(
        self, model: str, temperature: float
    ) -> None:
        posted = _post_body(model, temperature=temperature)
        assert posted == _serialised(_main_body(model, temperature=None))
        decoded = json.loads(posted)
        assert "temperature" not in decoded
        assert list(decoded) == ["model", "messages", "max_tokens", "stream"]
        assert decoded["model"] == model
        assert decoded["max_tokens"] == 64

    def test_namespaced_transport_is_read_after_the_prefix_is_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R432: with REGENOLD_WRAPPER_MODEL_PREFIX set the id on the wire is namespaced."""
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")

        assert _post_body("claude-sonnet-5-5") == _serialised(
            _main_body("anthropic/claude-sonnet-5-5", temperature=None)
        )
        # The shipped Stage-2 model on the same transport still carries temperature.
        assert _post_body("claude-opus-5-5") == _serialised(
            _main_body("anthropic/claude-opus-5-5")
        )


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


class TestGeminiProvider:
    def test_gemini_enabled_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.openai_wrapper_provider import is_gemini_provider_enabled

        # When GEMINI_API_KEY is not set
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert is_gemini_provider_enabled() is False

        # When GEMINI_API_KEY is empty
        monkeypatch.setenv("GEMINI_API_KEY", "  ")
        assert is_gemini_provider_enabled() is False

        # When GEMINI_API_KEY is present
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        assert is_gemini_provider_enabled() is True

    def test_gemini_provider_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.openai_wrapper_provider import (
            get_gemini_provider,
            _reset_gemini_singleton_for_tests,
        )

        _reset_gemini_singleton_for_tests()
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("GEMINI_API_BASE", "https://custom.gemini.api/v1")
        monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "30")

        provider = get_gemini_provider()
        assert provider._base_url == "https://custom.gemini.api/v1"
        assert provider._api_key == "test-gemini-key"
        assert provider._timeout == 30.0

        # Singleton preservation
        provider2 = get_gemini_provider()
        assert provider is provider2

        _reset_gemini_singleton_for_tests()

