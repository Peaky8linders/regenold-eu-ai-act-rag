"""Diagnostics are partner-only; only ``/healthz`` and ``/`` answer anonymously.

``/healthz/llm`` makes a live model call per request (``probe_bedrock=1`` adds
billable AWS Bedrock Converse calls), ``/healthz/email?probe=1`` sends real
mail to a caller-supplied address, ``/healthz/graph`` queries Neo4j and
``/info`` describes the service. Each depends on ``require_regenold_api_key``
as a route dependency, so a rejected caller never reaches the probe.

Every spend test asserts the CALL COUNT of the downstream function, not just
the status code: a 401 returned *after* dialling AWS would satisfy a status
assertion and none of the intent.

Railway's deploy healthcheck (``railway.toml`` healthcheckPath = "/healthz")
must stay public, and the API documentation must not be served.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.main as main_mod
from app.config import settings
from app.main import app
from app.rate_limit import limiter

_OPS_KEY = "r370-operator-key"
_OPS_HEADERS = {"X-Regenold-Api-Key": _OPS_KEY}
_WRONG_HEADERS = {"X-Regenold-Api-Key": "r370-not-the-key"}

_PROBE_URLS = (
    "/healthz/llm",
    "/healthz/llm?probe_bedrock=1",
    "/healthz/graph",
    "/healthz/email",
    "/healthz/email?probe=1&to=victim@example.com",
    "/info",
)


@pytest.fixture(autouse=True)
def _partner_key_dependency_override():
    """Exercise the REAL key check: this module tests the auth dependency."""
    yield


@pytest.fixture(autouse=True)
def _ops_key():
    """Pin the partner key. conftest restores the singleton after each test."""
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001 — never block a test on cleanup
        pass
    settings.regenold.api_key = SecretStr(_OPS_KEY)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestPublicSurface:
    def test_healthz_is_public_and_ok(self, client: TestClient) -> None:
        r = client.get("/healthz")
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ok"

    def test_the_railway_healthcheck_is_not_throttled_that_hard(
        self, client: TestClient
    ) -> None:
        codes = [client.get("/healthz").status_code for _ in range(14)]
        assert 429 not in codes, codes

    def test_root_is_a_minimal_json_identity(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200, r.text
        assert set(r.json()) == {"service", "version", "status"}

    @pytest.mark.parametrize(
        "path",
        ["/docs", "/redoc", "/openapi.json", "/api/v1/docs", "/api/v1/redoc",
         "/api/v1/openapi.json", "/app", "/lexy_avatar.png",
         "/api/v1/regenold/auth/signup", "/api/v1/regenold/auth/signin"],
    )
    def test_docs_ui_and_signup_are_gone(self, client: TestClient, path: str) -> None:
        assert client.get(path).status_code in (404, 405), path
        assert client.post(path, json={"email": "a@b.example"}).status_code in (404, 405), path


class TestDiagnosticsRequireThePartnerKey:
    @pytest.mark.parametrize("url", _PROBE_URLS)
    def test_anonymous_is_401(self, client: TestClient, url: str) -> None:
        r = client.get(url)
        assert r.status_code == 401, (url, r.text)
        assert r.json()["detail"]["code"] == "regenold_api_key_missing"

    @pytest.mark.parametrize("url", _PROBE_URLS)
    def test_wrong_key_is_403(self, client: TestClient, url: str) -> None:
        r = client.get(url, headers=_WRONG_HEADERS)
        assert r.status_code == 403, (url, r.text)

    @pytest.mark.parametrize("url", _PROBE_URLS)
    def test_unconfigured_deploy_is_503(self, client: TestClient, url: str) -> None:
        settings.regenold.api_key = None
        r = client.get(url, headers=_OPS_HEADERS)
        assert r.status_code == 503, (url, r.text)

    def test_rejected_callers_never_reach_the_probes(self, client: TestClient) -> None:
        from app.integrations.regenold import email as lexy_email

        with patch.object(main_mod, "_probe_bedrock_leg") as bedrock, patch.object(
            main_mod, "_healthz_llm_probe"
        ) as llm, patch.object(main_mod, "_healthz_graph_probe") as graph, patch.object(
            lexy_email, "probe_send"
        ) as send:
            for url in _PROBE_URLS:
                client.get(url)
                client.get(url, headers=_WRONG_HEADERS)
            assert bedrock.call_count == 0
            assert llm.call_count == 0
            assert graph.call_count == 0
            assert send.call_count == 0

    def test_operator_can_run_the_bedrock_probe(self, client: TestClient) -> None:
        with patch.object(
            main_mod, "_probe_bedrock_leg", return_value={"status": "ok"}
        ) as probe:
            r = client.get("/healthz/llm?probe_bedrock=1", headers=_OPS_HEADERS)
            assert r.status_code == 200, r.text
            assert probe.call_count == 1
            assert r.json().get("bedrock_probe") == {"status": "ok"}

    def test_operator_can_send_the_email_probe(self, client: TestClient) -> None:
        from app.integrations.regenold import email as lexy_email

        with patch.object(
            lexy_email, "probe_send", return_value=(True, "id-123")
        ) as send:
            r = client.get(
                "/healthz/email?probe=1&to=ops@example.com", headers=_OPS_HEADERS
            )
            assert r.status_code == 200, r.text
            assert send.call_count == 1
            assert send.call_args.args[0] == "ops@example.com"

    def test_operator_reads_graph_and_info(self, client: TestClient) -> None:
        assert client.get("/healthz/graph", headers=_OPS_HEADERS).status_code == 200
        r = client.get("/info", headers=_OPS_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ask_endpoint"] == "/api/v1/regenold/eu-ai-act/ask"
        assert not {"docs", "ui", "chat_ui", "signup_endpoint"} & set(body)


class TestPerRouteLimitsAreTighterThanTheAppDefault:
    def test_llm_route_429s_well_before_the_app_default(
        self, client: TestClient
    ) -> None:
        codes = [
            client.get("/healthz/llm", headers=_OPS_HEADERS).status_code
            for _ in range(14)
        ]
        assert 429 in codes, codes
        assert codes.index(429) <= 10, codes

    def test_graph_route_is_limited_too(self, client: TestClient) -> None:
        codes = [
            client.get("/healthz/graph", headers=_OPS_HEADERS).status_code
            for _ in range(34)
        ]
        assert 429 in codes, codes[:12]
