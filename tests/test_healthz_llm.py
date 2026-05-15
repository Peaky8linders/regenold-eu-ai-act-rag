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
