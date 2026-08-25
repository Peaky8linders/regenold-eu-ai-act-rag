"""R370 — the health probes that SPEND are operator-only.

Two endpoints let an anonymous caller spend someone else's money or someone
else's sending reputation. Both were publicly reachable on production —
verified with an unauthenticated request that returned HTTP 200.

  * ``/healthz/llm?probe_bedrock=1`` — walks ``BEDROCK_FALLBACK_PROBE_MODELS``
    and issues real AWS Bedrock Converse calls. Billable by a stranger.
  * ``/healthz/email?probe=1&to=…``  — fires ONE real Resend send to an
    ARBITRARY caller-supplied address. An open relay; the target is the
    verified sending domain's reputation, not the spend.

Only the app-wide slowapi ``100/minute`` per-IP default applied, and it is per
IP, so the ceiling was ~100 invocations/minute/IP from any number of IPs.

WHAT R370 DELIBERATELY DOES NOT DO, so the next reader does not assume it is
covered:

  * The BASE ``/healthz/llm`` reading stays PUBLIC. It performs a live Claude
    Max completion, which is subscription quota rather than metered spend, and
    ``app/web_ui.py::checkSystemHealth`` fetches it FROM THE BROWSER to render
    the operator's LLM badge. The browser cannot hold the partner key, so
    closing this route outright would break the panel whose entire job is to
    say "the tunnel is down". Mitigated by a tighter per-route limit
    (100/min -> 10/min per IP), not closed. Closing it properly means moving
    the badge onto a cheap non-probing signal — a product decision.
  * NO payload redaction. An earlier draft projected the anonymous response
    down to the badge fields. It is theatre while ``/healthz`` stays public for
    Railway's deploy healthcheck and already serves ``commit`` and
    ``deployment_id`` to anyone. Close ``/healthz`` first or the rest is
    decoration.

Every spend test asserts the CALL COUNT of the downstream function, not just
the status code. A 401 returned *after* dialling AWS would satisfy a status
assertion and none of the intent.
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

#: Fields ``web_ui.py::checkSystemHealth`` renders. If these stop being served
#: anonymously, the in-app diagnostics panel silently degrades.
_WEB_UI_LLM_FIELDS = ("llm_ok", "provider", "detail")
_WEB_UI_GRAPH_FIELDS = ("graph_ok", "detail")


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


class TestRailwayHealthcheckIsUntouched:
    """``railway.toml`` healthcheckPath = "/healthz" — breaking it fails deploys."""

    def test_healthz_is_public_and_ok(self, client: TestClient) -> None:
        r = client.get("/healthz")
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ok"

    def test_healthz_still_carries_version_for_the_web_ui(
        self, client: TestClient
    ) -> None:
        assert client.get("/healthz").json().get("version")


class TestBedrockProbeCannotBeTriggeredAnonymously:
    """The billable-by-a-stranger branch."""

    def test_anonymous_is_401(self, client: TestClient) -> None:
        r = client.get("/healthz/llm?probe_bedrock=1")
        assert r.status_code == 401, r.text
        assert r.json()["detail"]["code"] == "probe_requires_operator_key"

    def test_wrong_key_is_403(self, client: TestClient) -> None:
        r = client.get("/healthz/llm?probe_bedrock=1", headers=_WRONG_HEADERS)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "regenold_api_key_invalid"

    def test_anonymous_never_reaches_aws(self, client: TestClient) -> None:
        """The assertion that actually protects the account.

        A 401 returned *after* dialling AWS would pass the status test above
        and defeat the entire point.
        """
        with patch.object(main_mod, "_probe_bedrock_leg") as probe:
            client.get("/healthz/llm?probe_bedrock=1")
            client.get("/healthz/llm?probe_bedrock=1", headers=_WRONG_HEADERS)
            assert probe.call_count == 0, (
                "an unauthorised caller reached the Bedrock probe — the gate "
                "runs too late to prevent spend"
            )

    def test_every_truthy_spelling_is_gated(self, client: TestClient) -> None:
        """``_HEALTHZ_TRUTHY`` accepts several spellings; all must be gated."""
        with patch.object(main_mod, "_probe_bedrock_leg") as probe:
            for value in ("1", "true", "TRUE", "yes", "on"):
                r = client.get(f"/healthz/llm?probe_bedrock={value}")
                assert r.status_code == 401, (value, r.status_code)
            assert probe.call_count == 0

    def test_falsy_values_are_not_gated(self, client: TestClient) -> None:
        """Two-sided: the default request must not start demanding a key."""
        for value in ("0", "false", "off", ""):
            r = client.get(f"/healthz/llm?probe_bedrock={value}")
            assert r.status_code == 200, (value, r.text)

    def test_operator_can_still_run_it(self, client: TestClient) -> None:
        """Two-sided: the gate must not break the operator's diagnostic."""
        with patch.object(
            main_mod, "_probe_bedrock_leg", return_value={"status": "ok"}
        ) as probe:
            r = client.get("/healthz/llm?probe_bedrock=1", headers=_OPS_HEADERS)
            assert r.status_code == 200, r.text
            assert probe.call_count == 1
            assert r.json().get("bedrock_probe") == {"status": "ok"}


class TestEmailProbeIsNotAnOpenRelay:
    """``?probe=1&to=<anything>`` sent real mail to any address on request."""

    def test_anonymous_is_401(self, client: TestClient) -> None:
        r = client.get("/healthz/email?probe=1&to=victim@example.com")
        assert r.status_code == 401, r.text

    def test_wrong_key_is_403(self, client: TestClient) -> None:
        r = client.get(
            "/healthz/email?probe=1&to=victim@example.com", headers=_WRONG_HEADERS
        )
        assert r.status_code == 403, r.text

    def test_anonymous_never_sends(self, client: TestClient) -> None:
        from app.integrations.regenold import email as lexy_email

        with patch.object(lexy_email, "probe_send") as send:
            client.get("/healthz/email?probe=1&to=victim@example.com")
            client.get(
                "/healthz/email?probe=1&to=victim@example.com",
                headers=_WRONG_HEADERS,
            )
            assert send.call_count == 0, (
                "an unauthorised caller triggered a real send — the verified "
                "sending domain is the abuse target here, not the spend"
            )

    def test_operator_can_still_send(self, client: TestClient) -> None:
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
            assert r.json().get("send_ok") is True

    def test_config_only_view_stays_public_and_sends_nothing(
        self, client: TestClient
    ) -> None:
        """Two-sided: the no-probe view must stay reachable and silent."""
        from app.integrations.regenold import email as lexy_email

        with patch.object(lexy_email, "probe_send") as send:
            r = client.get("/healthz/email")
            assert r.status_code == 200, r.text
            assert send.call_count == 0


class TestThePublicReadingsStillServeTheWebUI:
    """Pins the deliberate decision NOT to close the base routes.

    If someone later authenticates these, this fails and points at
    ``web_ui.py::checkSystemHealth`` — which cannot hold the key.
    """

    def test_llm_badge_fields_are_public(self, client: TestClient) -> None:
        r = client.get("/healthz/llm")
        assert r.status_code == 200, r.text
        missing = [f for f in _WEB_UI_LLM_FIELDS if f not in r.json()]
        assert not missing, missing

    def test_graph_badge_fields_are_public(self, client: TestClient) -> None:
        r = client.get("/healthz/graph")
        assert r.status_code == 200, r.text
        missing = [f for f in _WEB_UI_GRAPH_FIELDS if f not in r.json()]
        assert not missing, missing


class TestPerRouteLimitsAreTighterThanTheAppDefault:
    """Item 3 of the brief. The app-wide default is 100/minute per IP.

    Asserted BEHAVIOURALLY — drive the route until it 429s — rather than by
    reading a slowapi private attribute, so the test measures what a caller
    actually experiences.
    """

    def test_llm_route_429s_well_before_the_app_default(
        self, client: TestClient
    ) -> None:
        codes = [client.get("/healthz/llm").status_code for _ in range(14)]
        assert 429 in codes, (
            "no 429 within 14 requests — the app-wide 100/minute default is "
            f"still governing this route: {codes}"
        )
        first_429 = codes.index(429)
        assert first_429 <= 10, (
            f"first 429 at request {first_429 + 1}; expected the 10/minute "
            f"per-route limit: {codes}"
        )

    def test_graph_route_is_limited_too(self, client: TestClient) -> None:
        codes = [client.get("/healthz/graph").status_code for _ in range(34)]
        assert 429 in codes, (
            f"no 429 within 34 requests on /healthz/graph: {codes[:12]}…"
        )

    def test_the_railway_healthcheck_is_not_throttled_that_hard(
        self, client: TestClient
    ) -> None:
        """Two-sided: ``/healthz`` must keep its permissive app-wide default.

        Railway polls it on every deploy; a 10/minute cap there would flap
        the healthcheck.
        """
        codes = [client.get("/healthz").status_code for _ in range(14)]
        assert 429 not in codes, (
            f"/healthz got throttled inside 14 requests: {codes}"
        )
