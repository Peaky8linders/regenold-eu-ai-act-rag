"""Tests for /healthz/llm — operator-visible provider health surface.

The endpoint must:
  * Always return HTTP 200 so uptime monitors don't flap on wrapper outages.
  * Surface the *resolved* provider name (so a typo like ``mistraal`` is
    visible — but we already validate that at boot, so this is belt-and-braces).
  * Probe the openai_wrapper LIVE (we want to know the wrapper actually
    answers, not just that it's reachable).
  * NOT burn a live API call on the anthropic / mistral paths (per-token
    cost — only confirm "configured").
  * Reflect the bundled ``OpenAIWrapperResponse.error`` shape verbatim
    so operators see "Not logged in", "api_status_429", etc. without
    needing to inspect logs.
"""
from __future__ import annotations

import os

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Reset to known state — no provider-specific env unless test sets it.
    for k in (
        "P2P_GRAPH_RAG_PROVIDER",
        "P2P_GRAPH_RAG_API_KEY",
        "MISTRAL_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
    from app.main import app
    return TestClient(app)


class TestHealthzLLMDeterministicPath:
    """Default install (no env vars) resolves to ``anthropic`` per
    ``resolve_provider(default_when_auto='anthropic')``. Without a key
    the probe reports llm_ok=False and a clear diagnostic.
    """

    def test_no_provider_set_reports_anthropic_no_key(
        self, client: TestClient
    ) -> None:
        r = client.get("/healthz/llm")
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "anthropic"
        assert body["llm_ok"] is False
        assert "P2P_GRAPH_RAG_API_KEY" in body["detail"]

    def test_cli_provider_reports_deterministic_ok(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
        r = client.get("/healthz/llm")
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "cli"
        assert body["llm_ok"] is True
        assert "deterministic" in body["detail"]


class TestHealthzLLMOpenAIWrapper:
    def test_wrapper_configured_but_unreachable(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPENAI_API_BASE set, but probe gets a network error."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.test.invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        from app.llm import openai_wrapper_provider

        # Force a fresh singleton against the new base URL + mock transport
        # that always errors.
        def _err_handler(_req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated")

        openai_wrapper_provider._SINGLETON = None
        prov = openai_wrapper_provider.get_openai_wrapper_provider()
        prov._client = httpx.Client(
            transport=httpx.MockTransport(_err_handler),
            base_url="https://api.test.invalid",
        )
        try:
            r = client.get("/healthz/llm")
        finally:
            # Reset so other tests don't inherit the mock transport
            openai_wrapper_provider._SINGLETON = None

        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "openai_wrapper"
        assert body["llm_ok"] is False
        assert "network_error" in body["detail"]

    def test_wrapper_returns_500(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The 'No response from Claude Code' production failure mode."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.test.invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        from app.llm import openai_wrapper_provider

        def _handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500,
                json={
                    "error": {
                        "message": "No response from Claude Code",
                        "type": "api_error",
                        "code": "500",
                    }
                },
            )

        openai_wrapper_provider._SINGLETON = None
        prov = openai_wrapper_provider.get_openai_wrapper_provider()
        prov._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.test.invalid",
        )
        try:
            r = client.get("/healthz/llm")
        finally:
            openai_wrapper_provider._SINGLETON = None

        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "openai_wrapper"
        assert body["llm_ok"] is False
        assert "api_status_500" in body["detail"]
        assert "No response from Claude Code" in body["detail"]

    def test_wrapper_not_logged_in_sentinel(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTTP 200 with the 'Not logged in' sentinel must NOT be llm_ok."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.test.invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        from app.llm import openai_wrapper_provider

        def _handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "choices": [
                        {
                            "message": {
                                "content": "Not logged in · Please run /login"
                            }
                        }
                    ],
                },
            )

        openai_wrapper_provider._SINGLETON = None
        prov = openai_wrapper_provider.get_openai_wrapper_provider()
        prov._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.test.invalid",
        )
        try:
            r = client.get("/healthz/llm")
        finally:
            openai_wrapper_provider._SINGLETON = None

        assert r.status_code == 200
        body = r.json()
        assert body["llm_ok"] is False
        assert "not_logged_in" in body["detail"]

    def test_wrapper_happy_path_llm_ok_true(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.test.invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        from app.llm import openai_wrapper_provider

        def _handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                },
            )

        openai_wrapper_provider._SINGLETON = None
        prov = openai_wrapper_provider.get_openai_wrapper_provider()
        prov._client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="https://api.test.invalid",
        )
        try:
            r = client.get("/healthz/llm")
        finally:
            openai_wrapper_provider._SINGLETON = None

        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "openai_wrapper"
        assert body["llm_ok"] is True
        assert body["detail"] == "ok"
        assert body["model"] == "claude-haiku-4-5-20251001"
        assert body["prompt_tokens"] == 3
        assert body["completion_tokens"] == 1

    def test_wrapper_misconfigured_no_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """provider=openai_wrapper but neither base nor key set."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        # Clear both — even auto-resolved defaults
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        r = client.get("/healthz/llm")
        assert r.status_code == 200
        body = r.json()
        assert body["llm_ok"] is False
        assert "OPENAI_API_BASE" in body["detail"]


class TestHealthzLLMAnthropicProvider:
    def test_anthropic_no_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        r = client.get("/healthz/llm")
        body = r.json()
        assert body["provider"] == "anthropic"
        assert body["llm_ok"] is False
        assert "P2P_GRAPH_RAG_API_KEY" in body["detail"]

    def test_anthropic_live_probe_failure_reports_not_ok(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Round-30: a bad key on Railway must report llm_ok=False, not silently
        say "configured" — the configured-only probe we shipped in round 29
        would lie when the key was revoked / typo'd / pointed at the wrong tenant.
        """
        anthropic = pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-broken")
        # Force settings re-read so the new env propagates to the live
        # probe (cached pydantic settings keep the previous value).
        from app.config import settings
        from pydantic import SecretStr as _SS
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-broken"), raising=True
        )

        class _Boom:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass
            class models:  # noqa: D401, N801 — match SDK shape
                @staticmethod
                def list(*args: object, **kwargs: object) -> object:
                    raise RuntimeError("authentication failed")

        monkeypatch.setattr(anthropic, "Anthropic", _Boom)
        r = client.get("/healthz/llm")

        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "anthropic"
        assert body["llm_ok"] is False
        assert "anthropic_probe_failed" in body["detail"]
        # Reset for downstream tests.
        monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)

    def test_anthropic_live_probe_success_reports_ok(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        anthropic = pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-fake")
        from app.config import settings
        from pydantic import SecretStr as _SS
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        class _OK:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass
            class models:  # noqa: N801
                @staticmethod
                def list(*args: object, **kwargs: object) -> object:
                    return {"data": []}

        monkeypatch.setattr(anthropic, "Anthropic", _OK)
        r = client.get("/healthz/llm")

        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "anthropic"
        assert body["llm_ok"] is True
        assert body["detail"] == "ok"
        monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)

    def test_anthropic_probe_can_be_disabled_via_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Operators can opt out of the live probe to preserve the old
        configured-only behaviour."""
        pytest.importorskip("anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-fake")
        monkeypatch.setenv("REGENOLD_HEALTHZ_PROBE_ANTHROPIC", "0")
        from app.config import settings
        from pydantic import SecretStr as _SS
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        r = client.get("/healthz/llm")
        body = r.json()
        assert body["provider"] == "anthropic"
        assert body["llm_ok"] is True
        assert "not probed live" in body["detail"]
        monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)

    def test_anthropic_sdk_missing_reports_not_ok(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the SDK isn't installed at all the probe must surface a clear
        pip-install hint rather than blowing up."""
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "anthropic")
        monkeypatch.setenv("P2P_GRAPH_RAG_API_KEY", "sk-ant-fake")
        from app.config import settings
        from pydantic import SecretStr as _SS
        monkeypatch.setattr(
            settings.graph_rag, "api_key", _SS("sk-ant-fake"), raising=True
        )

        import builtins as _builtins
        orig_import = _builtins.__import__

        def _no_anthropic(name: str, *args: object, **kwargs: object) -> object:
            if name == "anthropic":
                raise ImportError("not installed")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(_builtins, "__import__", _no_anthropic)
        r = client.get("/healthz/llm")
        body = r.json()
        assert body["provider"] == "anthropic"
        assert body["llm_ok"] is False
        assert "not installed" in body["detail"]
        monkeypatch.setattr(settings.graph_rag, "api_key", None, raising=True)


class TestHealthzLLMMistralProvider:
    def test_mistral_no_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "mistral")
        r = client.get("/healthz/llm")
        body = r.json()
        assert body["provider"] == "mistral"
        assert body["llm_ok"] is False
        assert "MISTRAL_API_KEY" in body["detail"]

    def test_mistral_with_key(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "mistral")
        monkeypatch.setenv("MISTRAL_API_KEY", "sk-test")
        r = client.get("/healthz/llm")
        body = r.json()
        assert body["provider"] == "mistral"
        assert body["llm_ok"] is True
        assert "MISTRAL_API_KEY" in body["detail"]


def test_healthz_always_returns_200(client: TestClient) -> None:
    """The simple ``/healthz`` shouldn't be affected by any LLM state."""
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
