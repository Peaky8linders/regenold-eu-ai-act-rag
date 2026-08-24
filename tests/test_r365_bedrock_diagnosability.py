"""R365 — Stage-2 leg 2 (AWS Bedrock) must be diagnosable from OUTSIDE the container.

Three defects made a Bedrock failure invisible to anyone without shell access
to the Railway container, all three re-verified by execution before this file
was written:

1. ``_bedrock_complete_for_graph_rag`` classified the AWS error and then threw
   the string away (``logger.warning`` + ``return None``,
   ``app/engines/_graph_rag_impl.py:745-747``). It reached neither the wire
   response, nor the reasoning trace, nor ``/healthz/llm``.
2. ``check_connectivity_and_permissions`` — which returns the exact AWS status
   AND a remediation hint — had **zero call sites in ``app/``**; the only
   caller was ``scripts/test_bedrock_client.py``.
3. ``/healthz/llm`` never probed Bedrock at all. On the production
   ``openai_wrapper`` path it decided green/red from
   ``is_bedrock_provider_enabled()`` ("are credentials PRESENT") plus
   ``fallback_attempts > 0 and fallback_ok == 0``, so with zero attempts it
   reported ``llm_ok: true`` + "bedrock fallback active" no matter how broken
   Bedrock was.

Every test here pins a RUNTIME observation — a call count, a returned body, a
recorded note — never the shape of the code. Two-sided throughout: the
important half of the opt-in probe is that the DEFAULT endpoint makes no AWS
call at all, and the important half of the trace note is that a SUCCESSFUL
Bedrock call records no failure note.

Fully offline: boto3 is stubbed at ``_create_client_with_auth``, the single
seam every Bedrock client construction passes through, so a leaked network
call fails the test rather than reaching AWS.
"""
from __future__ import annotations

import os

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.llm import bedrock_client as bc


# ══════════════════════════════════════════════════════════════════════════
# Fixtures — boto3 stubbed at the ONE construction seam.
# ══════════════════════════════════════════════════════════════════════════

#: Credential-shaped strings planted in stubbed AWS errors. None of these may
#: appear in anything the endpoint or the trace emits.
SECRET_ABSK = "ABSKQWERTYUIOPASDFGHJKLZXCVBNM1234567890"
SECRET_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
SECRET_40 = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYab"  # 40 chars, base64 alphabet


class _FakeBotoClient:
    """Stand-in for a ``bedrock-runtime`` boto3 client."""

    def __init__(self, behaviour) -> None:
        self._behaviour = behaviour
        self.converse_calls: list[dict] = []

    def converse(self, **kwargs):
        self.converse_calls.append(kwargs)
        return self._behaviour(kwargs)


class _BotoSpy:
    """Counts EVERY boto3 client construction and every ``converse``."""

    def __init__(self) -> None:
        self.client_constructions = 0
        self.client: _FakeBotoClient | None = None
        self.behaviour = lambda kwargs: (_ for _ in ()).throw(
            AssertionError("no behaviour configured")
        )

    def factory(self, *args, **kwargs):
        self.client_constructions += 1
        self.client = _FakeBotoClient(self.behaviour)
        return self.client

    @property
    def converse_calls(self) -> int:
        return len(self.client.converse_calls) if self.client else 0

    @property
    def aws_calls(self) -> int:
        """Any evidence at all that we touched AWS."""
        return self.client_constructions + self.converse_calls


def _client_error(code: str, status: int, message: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "Converse",
    )


@pytest.fixture()
def boto(monkeypatch: pytest.MonkeyPatch) -> _BotoSpy:
    spy = _BotoSpy()
    bc._reset_bedrock_singletons_for_tests()
    bc._reset_bedrock_provider_for_tests()
    monkeypatch.setattr(bc, "_create_client_with_auth", spy.factory)
    # Also block the real boto3 entry point outright — if anything reaches it,
    # the test fails loudly instead of opening a socket.
    monkeypatch.setattr(
        bc.boto3,
        "Session",
        lambda *a, **k: pytest.fail("real boto3.Session constructed — test leaked to AWS"),
    )
    yield spy
    bc._reset_bedrock_singletons_for_tests()
    bc._reset_bedrock_provider_for_tests()


@pytest.fixture()
def creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``is_bedrock_provider_enabled()`` True without a real credential."""
    for k in ("AWS_BEDROCK_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-token-not-a-real-credential")
    monkeypatch.setenv("BEDROCK_REGION", "eu-central-1")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient on the deterministic provider path.

    ``cli`` is deliberate: it keeps the wrapper's own live probe out of the
    way so the only thing that could touch the network is the Bedrock probe
    under test.
    """
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
    from app.main import app

    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# Defect 3a — the OPT-IN probe surfaces the AWS status/error/hint verbatim.
# ══════════════════════════════════════════════════════════════════════════

class TestProbeBedrockOptIn:
    def test_probe_surfaces_stubbed_aws_error_verbatim(
        self, client: TestClient, boto: _BotoSpy, creds: None
    ) -> None:
        boto.behaviour = lambda kwargs: (_ for _ in ()).throw(
            _client_error("AccessDeniedException", 403, "You don't have access to the model")
        )

        r = client.get("/healthz/llm", params={"probe_bedrock": "1"})

        assert r.status_code == 200, r.text
        probe = r.json()["bedrock_probe"]
        # VERBATIM: the classifier's own string, not a paraphrase.
        assert probe["error"] == "api_access_denied_403", probe
        assert probe["status"] == "error", probe
        assert probe["hint"], "an operator hint must accompany a failure"
        assert "elapsed_ms" in probe
        # And it really dialled AWS (the R329 lesson: prove the lever fires).
        assert boto.converse_calls == 1, "probe_bedrock=1 must make exactly one call"

    def test_probe_surfaces_the_expired_key_hint(
        self, client: TestClient, boto: _BotoSpy, creds: None
    ) -> None:
        """The one case with a purpose-written remediation hint."""
        boto.behaviour = lambda kwargs: (_ for _ in ()).throw(
            _client_error(
                "AccessDeniedException",
                403,
                "Authentication failed: Please make sure your API Key is valid.",
            )
        )

        probe = client.get("/healthz/llm?probe_bedrock=1").json()["bedrock_probe"]

        assert probe["status"] == "key_invalid", probe
        assert probe["error"] == "api_key_invalid_403", probe
        assert "AWS_BEARER_TOKEN_BEDROCK" in probe["hint"]

    def test_probe_reports_ok_when_bedrock_answers(
        self, client: TestClient, boto: _BotoSpy, creds: None
    ) -> None:
        """Inverse arm — a green probe must be reachable, or the test above
        only proves the endpoint always says 'error'."""
        boto.behaviour = lambda kwargs: {
            "output": {"message": {"content": [{"text": "OK"}]}},
            "usage": {"inputTokens": 3, "outputTokens": 1},
            "stopReason": "end_turn",
        }

        probe = client.get("/healthz/llm?probe_bedrock=1").json()["bedrock_probe"]

        assert probe["status"] == "ok", probe
        assert probe["error"] is None
        assert boto.converse_calls == 1

    def test_probe_without_credentials_reports_so_without_calling_aws(
        self, client: TestClient, boto: _BotoSpy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for k in (
            "AWS_BEARER_TOKEN_BEDROCK",
            "AWS_BEDROCK_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ):
            monkeypatch.delenv(k, raising=False)

        probe = client.get("/healthz/llm?probe_bedrock=1").json()["bedrock_probe"]

        assert probe["status"] == "no_credentials", probe
        assert "AWS_BEARER_TOKEN_BEDROCK" in probe["hint"]
        assert boto.aws_calls == 0, "must not dial AWS with no credential wired"


# ══════════════════════════════════════════════════════════════════════════
# Defect 3b — THE IMPORTANT HALF. The DEFAULT endpoint makes no AWS call.
# ══════════════════════════════════════════════════════════════════════════

class TestDefaultHealthzMakesNoAwsCall:
    def test_default_healthz_llm_never_touches_bedrock(
        self, client: TestClient, boto: _BotoSpy, creds: None
    ) -> None:
        """Opt-in means opt-in.

        ``/healthz/llm`` already fires one billable model call per hit on the
        wrapper path; a default Bedrock probe would make every uptime check
        two paid round-trips. Credentials ARE wired here, so nothing but the
        missing flag can be keeping the call away.
        """
        boto.behaviour = lambda kwargs: pytest.fail(
            "default /healthz/llm made an AWS Converse call"
        )

        r = client.get("/healthz/llm")

        assert r.status_code == 200
        assert "bedrock_probe" not in r.json()
        assert boto.aws_calls == 0, (
            f"default healthz constructed {boto.client_constructions} boto client(s) "
            f"and made {boto.converse_calls} converse call(s)"
        )

    @pytest.mark.parametrize("value", ["0", "", "no", "off", "false"])
    def test_falsy_flag_values_do_not_probe(
        self, client: TestClient, boto: _BotoSpy, creds: None, value: str
    ) -> None:
        boto.behaviour = lambda kwargs: pytest.fail("falsy probe_bedrock made an AWS call")

        r = client.get("/healthz/llm", params={"probe_bedrock": value})

        assert r.status_code == 200
        assert "bedrock_probe" not in r.json()
        assert boto.aws_calls == 0


# ══════════════════════════════════════════════════════════════════════════
# Redaction — the probe text is partner-reachable, so no credential shape
# may survive it.
# ══════════════════════════════════════════════════════════════════════════

class TestRedaction:
    @pytest.mark.parametrize(
        "raw",
        [
            f"AccessDenied for {SECRET_KEY_ID} in eu-central-1",
            f"auth failed with {SECRET_ABSK}",
            f"aws_secret_access_key={SECRET_40}",
            f"Authorization: Bearer {SECRET_40}",
            f"credentials: {SECRET_40}",
        ],
    )
    def test_credential_shapes_are_masked(self, raw: str) -> None:
        out = bc.redact_credential_like(raw)
        for secret in (SECRET_KEY_ID, SECRET_ABSK, SECRET_40):
            assert secret not in out, f"{secret!r} survived redaction of {raw!r}"
        assert "[REDACTED" in out

    def test_redaction_keeps_the_diagnostic_readable(self) -> None:
        """Two-sided — over-redaction would destroy the thing we built this for."""
        out = bc.redact_credential_like(
            "api_access_denied_403 on eu.anthropic.claude-opus-4-8 in eu-central-1"
        )
        assert out == (
            "api_access_denied_403 on eu.anthropic.claude-opus-4-8 in eu-central-1"
        )

    def test_redaction_never_raises(self) -> None:
        assert bc.redact_credential_like(None) == "None"
        assert bc.redact_credential_like(1234) == "1234"

    def test_redaction_caps_length(self) -> None:
        assert len(bc.redact_credential_like("x" * 5000)) <= 601

    def test_endpoint_body_carries_no_credential_shape(
        self, client: TestClient, boto: _BotoSpy, creds: None
    ) -> None:
        """End-to-end: a secret planted in the AWS exception must not reach the wire."""
        boto.behaviour = lambda kwargs: (_ for _ in ()).throw(
            RuntimeError(f"boom key={SECRET_ABSK} id={SECRET_KEY_ID} secret={SECRET_40}")
        )

        r = client.get("/healthz/llm?probe_bedrock=1")

        assert r.status_code == 200
        for secret in (SECRET_ABSK, SECRET_KEY_ID, SECRET_40):
            assert secret not in r.text, f"{secret!r} leaked onto the wire"
        probe = r.json()["bedrock_probe"]
        assert probe["status"] == "error"
        assert "[REDACTED" in str(probe["error"]), probe


# ══════════════════════════════════════════════════════════════════════════
# The probe must never 500 the endpoint.
# ══════════════════════════════════════════════════════════════════════════

class TestProbeFailsSoft:
    def test_raising_diagnostic_does_not_500(
        self, client: TestClient, creds: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _explode(*a, **k):
            raise RuntimeError("diagnostic itself is broken")

        monkeypatch.setattr(bc, "check_connectivity_and_permissions", _explode)

        r = client.get("/healthz/llm?probe_bedrock=1")

        assert r.status_code == 200, r.text
        probe = r.json()["bedrock_probe"]
        assert probe["status"] == "probe_raised", probe
        assert "RuntimeError" in probe["error"]

    def test_malformed_diagnostic_return_does_not_500(
        self, client: TestClient, creds: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bc, "check_connectivity_and_permissions", lambda *a, **k: "nope")

        r = client.get("/healthz/llm?probe_bedrock=1")

        assert r.status_code == 200
        assert r.json()["bedrock_probe"]["status"] == "probe_malformed"

    def test_probe_survives_the_production_openai_wrapper_path(
        self, boto: _BotoSpy, creds: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The path that matters: ``openai_wrapper`` + a down tunnel.

        That branch returns through ``_degraded_to_bedrock``, which mutates
        and returns the same dict — and it is EXACTLY the state where the
        endpoint reports ``llm_ok: true`` + "bedrock fallback active" off
        nothing but "credentials are present". The probe has to reach the body
        there or it is useless where it is needed most.
        """
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")
        monkeypatch.setenv("REGENOLD_HEALTHZ_PROBE_TIMEOUT", "1")
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        boto.behaviour = lambda kwargs: (_ for _ in ()).throw(
            _client_error("AccessDeniedException", 403, "no entitlement")
        )
        from app.main import app

        with TestClient(app) as c:
            body = c.get("/healthz/llm?probe_bedrock=1").json()

        # The pre-R365 false green, still reported the same way …
        assert "bedrock" in str(body["provider"]).lower()
        # … but now with the reason leg 2 is actually dark, in the body.
        assert body["bedrock_probe"]["error"] == "api_access_denied_403", body

    def test_probe_does_not_change_llm_ok(
        self, client: TestClient, boto: _BotoSpy, creds: None
    ) -> None:
        """Diagnosability only — the probe must not become a routing input."""
        boto.behaviour = lambda kwargs: (_ for _ in ()).throw(
            _client_error("AccessDeniedException", 403, "denied")
        )

        without = client.get("/healthz/llm").json()
        with_probe = client.get("/healthz/llm?probe_bedrock=1").json()

        assert with_probe["llm_ok"] == without["llm_ok"]
        assert with_probe["detail"] == without["detail"]


# ══════════════════════════════════════════════════════════════════════════
# Defect 4 — worker identity. ``--workers 2`` makes every counter a sample.
# ══════════════════════════════════════════════════════════════════════════

class TestWorkerIdentity:
    def test_pid_and_per_worker_note_present(self, client: TestClient) -> None:
        body = client.get("/healthz/llm").json()

        assert body["pid"] == os.getpid()
        note = body["counters_scope"]
        assert "per-worker" in note
        assert "--workers 2" in note or "workers" in note

    def test_pid_present_alongside_the_counters_it_qualifies(
        self, client: TestClient
    ) -> None:
        """The note is worthless if it does not travel with the counters."""
        body = client.get("/healthz/llm").json()

        assert "stats" in body["stage2_transport"]
        assert "pid" in body and "counters_scope" in body


# ══════════════════════════════════════════════════════════════════════════
# Defect 1 — the AWS error must reach the reasoning trace, and the
# ``return None`` contract must be unchanged.
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def trace():
    from app.integrations.regenold import reasoning_trace as rt

    t = rt.activate()
    try:
        yield t
    finally:
        rt.deactivate()


def _pin_single_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the 5-deep rollover chain so the assertions stay legible."""
    monkeypatch.setenv("REGENOLD_BEDROCK_FALLBACK_CHAIN", "qwen.qwen3-32b-v1:0")
    monkeypatch.setattr(bc, "resolve_bedrock_model", lambda m: m or "qwen.qwen3-32b-v1:0")
    monkeypatch.setattr(bc, "is_bedrock_provider_enabled", lambda: True)


class TestAwsErrorReachesTheTrace:
    def test_failed_bedrock_attempt_is_recorded_as_a_note(
        self, trace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines import _graph_rag_impl as impl

        _pin_single_model(monkeypatch)
        monkeypatch.setattr(
            bc,
            "complete_with_fallback",
            lambda req, fallbacks=(): bc.BedrockResponse(
                error="api_access_denied_403", model=req.model
            ),
        )

        out = impl._bedrock_complete_for_graph_rag(
            system="s", user="u", max_tokens=64, temperature=0.0,
            model_override="qwen.qwen3-32b-v1:0", stage_name="Stage 2",
        )

        # Contract preserved — callers depend on None meaning "no answer".
        assert out is None
        notes = [n for n in trace.notes if "bedrock" in n]
        assert notes, f"the AWS error was discarded again; notes={trace.notes}"
        assert "api_access_denied_403" in notes[0], notes

    def test_successful_bedrock_call_records_no_failure_note(
        self, trace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The inverse — a note on every call would be noise, not a signal."""
        from app.engines import _graph_rag_impl as impl

        _pin_single_model(monkeypatch)
        monkeypatch.setattr(
            bc,
            "complete_with_fallback",
            lambda req, fallbacks=(): bc.BedrockResponse(
                text="A complete sentence about Article 6.", model=req.model
            ),
        )

        out = impl._bedrock_complete_for_graph_rag(
            system="s", user="u", max_tokens=64, temperature=0.0,
            model_override="qwen.qwen3-32b-v1:0", stage_name="Stage 2",
        )

        assert out == "A complete sentence about Article 6."
        assert not [n for n in trace.notes if "attempt_failed" in n or "exception" in n]

    def test_note_is_redacted(self, trace, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.engines import _graph_rag_impl as impl

        _pin_single_model(monkeypatch)
        monkeypatch.setattr(
            bc,
            "complete_with_fallback",
            lambda req, fallbacks=(): bc.BedrockResponse(
                error=f"unexpected_error: creds {SECRET_ABSK} / {SECRET_KEY_ID}",
                model=req.model,
            ),
        )

        impl._bedrock_complete_for_graph_rag(
            system="s", user="u", max_tokens=64, temperature=0.0,
            model_override="qwen.qwen3-32b-v1:0", stage_name="Stage 2",
        )

        joined = " ".join(trace.notes)
        assert SECRET_ABSK not in joined
        assert SECRET_KEY_ID not in joined
        assert "[REDACTED" in joined

    def test_exception_path_also_records_and_returns_none(
        self, trace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines import _graph_rag_impl as impl

        _pin_single_model(monkeypatch)

        def _boom(req, fallbacks=()):
            raise RuntimeError("socket closed")

        monkeypatch.setattr(bc, "complete_with_fallback", _boom)

        out = impl._bedrock_complete_for_graph_rag(
            system="s", user="u", max_tokens=64, temperature=0.0,
            model_override="qwen.qwen3-32b-v1:0", stage_name="Stage 2",
        )

        assert out is None
        assert [n for n in trace.notes if "stage2_bedrock_exception" in n], trace.notes


# ══════════════════════════════════════════════════════════════════════════
# Defect 2 — the diagnostic now HAS a call site in app/.
# ══════════════════════════════════════════════════════════════════════════

def test_diagnostic_is_reachable_from_the_app(
    client: TestClient, boto: _BotoSpy, creds: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime proof, not a grep: the endpoint calls the real function."""
    called: list[object] = []
    real = bc.check_connectivity_and_permissions

    def _spy(*a, **k):
        called.append(True)
        return real(*a, **k)

    monkeypatch.setattr(bc, "check_connectivity_and_permissions", _spy)
    boto.behaviour = lambda kwargs: (_ for _ in ()).throw(
        _client_error("ValidationException", 400, "bad model id")
    )

    body = client.get("/healthz/llm?probe_bedrock=1").json()

    assert called, "check_connectivity_and_permissions still has no app/ call site"
    assert body["bedrock_probe"]["error"] == "api_validation_400"
