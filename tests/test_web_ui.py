"""Web UI (Lexy) route registration + API-key non-leak guard.

Verifies the R102 follow-up: the chat UI is mounted at ``/`` without
ever injecting ``P2P_REGENOLD_API_KEY`` into the served HTML, the JSON
service descriptor moved to ``/info``, and the wire contract
``POST /api/v1/regenold/eu-ai-act/ask`` is undisturbed.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

_SENTINEL_KEY = "regenold-secret-key-DO-NOT-LEAK-12345"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_root_serves_html_ui(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    # It's the Lexy chat UI, not the JSON descriptor.
    assert "<!DOCTYPE html>" in body
    assert "Lexy" in body


def test_root_does_not_leak_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The served HTML must NEVER contain the partner API key.

    This is the load-bearing security assertion of the round: even with
    a key set in the environment, the rendered ``/`` page must not embed
    it, and the template placeholder must be gone.
    """
    monkeypatch.setenv("P2P_REGENOLD_API_KEY", _SENTINEL_KEY)
    local_client = TestClient(app)
    body = local_client.get("/").text
    assert _SENTINEL_KEY not in body
    assert "{{API_KEY}}" not in body
    # The key input ships empty.
    assert 'id="cfg-api-key" class="form-input" value=""' in body


def test_info_endpoint_serves_json(client: TestClient) -> None:
    resp = client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "regenold-eu-ai-act-rag"
    assert data["ask_endpoint"] == "/api/v1/regenold/eu-ai-act/ask"
    assert data["ui"] == "/"


def test_avatar_route_registered(client: TestClient) -> None:
    # The avatar PNG may or may not be present on disk in CI, but the
    # route must be registered (not a 404 from a missing handler). When
    # the file is absent FileResponse raises -> 500; when present -> 200.
    # Either way it is NOT a routing 404.
    resp = client.get("/lexy_avatar.png")
    assert resp.status_code != 404


def test_ask_contract_unchanged(client: TestClient) -> None:
    """The wire contract must still return {answer, references, reasoning}.

    Mirrors the authed setup the integration suite uses: configure the
    partner key + send the matching ``X-Regenold-Api-Key`` header. This
    guards that mounting the web UI at ``/`` did not disturb the
    ``POST /api/v1/regenold/eu-ai-act/ask`` route.
    """
    from pydantic import SecretStr

    from app.config import settings

    settings.regenold.api_key = SecretStr("regenold-test-key")
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "What are the obligations of providers of high-risk AI systems?",
                }
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "references" in data
    assert "reasoning" in data
