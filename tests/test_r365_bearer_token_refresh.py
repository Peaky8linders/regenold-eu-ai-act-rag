"""R365 — the Bedrock bearer token must be read at REQUEST time, not pinned.

THE DEFECT. ``_add_bearer_header`` closed over ``bearer_token``, the value read
when the boto3 client was constructed. Every Bedrock client in this module is a
process-wide singleton (``_RUNTIME_CLIENT``, ``_CATALOG_CLIENT``,
``_TIMEOUT_CLIENTS``), so the credential captured at first use was PINNED for
the life of the process. Reproduced before the fix::

    AWS_BEARER_TOKEN_BEDROCK=FAKE-TOKEN-ONE  -> _get_runtime_client()
    AWS_BEARER_TOKEN_BEDROCK=FAKE-TOKEN-TWO
    resolve_bearer now    -> FAKE-TOKEN-TWO
    same client object    -> True
    handler closure token -> ['FAKE-TOKEN-ONE']
    header actually sent  -> Bearer FAKE-TOKEN-ONE      <-- the DEAD key

and the operator hint at the ``api_key_invalid_403`` branch said the opposite:
"the code picks the new key up on the next request with no restart".

⚠ These tests assert on the header a request would ACTUALLY carry — obtained by
emitting botocore's real ``before-send`` event, under the event name derived
from the client's own service model, onto a real ``AWSPreparedRequest``. They
never assert on the shape of the code. That is deliberate: a handler that is
registered under a name botocore never emits reads perfectly in a diff and
injects nothing at runtime (cf. the R329 rerank placements, three of which
looked right and made zero calls).

Two-sided by construction: the no-bearer (IAM / default-chain) path is pinned
UNCHANGED, including that a bearer variable appearing later must NOT retrofit a
header onto an already-built signed client.

No AWS calls. Building a boto3 client and emitting an event are both offline.
"""
from __future__ import annotations

import logging
import os

import pytest
from botocore.awsrequest import AWSRequest

# Placeholders only — never a real credential in a test file.
TOKEN_ONE = "FAKE-TOKEN-ONE"
TOKEN_TWO = "FAKE-TOKEN-TWO"
TOKEN_THREE = "FAKE-TOKEN-THREE"

_BEARER_VARS = (
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_BEDROCK_BEARER_TOKEN",
    "BEDROCK_BEARER_TOKEN",
    "AWS_BEDROCK_API_KEY",
)
_IAM_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)


@pytest.fixture
def clean_bedrock_env(monkeypatch: pytest.MonkeyPatch):
    """Blank every credential source, pin a region, reset the singletons."""
    from app.llm.bedrock_client import _reset_bedrock_singletons_for_tests

    for name in (*_BEARER_VARS, *_IAM_VARS, "AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BEDROCK_REGION", "eu-central-1")
    _reset_bedrock_singletons_for_tests()
    yield monkeypatch
    _reset_bedrock_singletons_for_tests()


def _authorization_header_for_next_request(client) -> str | None:
    """Return the ``Authorization`` header a real request would carry.

    The event name is derived from the client's OWN service model, exactly as
    ``botocore.endpoint.Endpoint._send_request`` builds it, so a registration
    that drifts away from the emitted name fails this helper rather than
    silently injecting nothing.
    """
    service_id = client.meta.service_model.service_id.hyphenize()
    request = AWSRequest(
        method="POST",
        url=f"https://{service_id}.eu-central-1.amazonaws.com/model/m/converse",
        data=b"{}",
    ).prepare()
    client.meta.events.emit(
        f"before-send.{service_id}.Converse", request=request
    )
    return request.headers.get("Authorization")


# ── 1. Rotation reaches the wire ─────────────────────────────────────────────


class TestRotationChangesTheHeaderActuallySent:
    def test_runtime_singleton_sends_the_rotated_token(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import _get_runtime_client

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        client = _get_runtime_client()
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_ONE}"

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
        # The singleton is deliberately NOT rebuilt — the whole point is that a
        # rotation does not require tearing down a live connection pool.
        assert _get_runtime_client() is client
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_TWO}"

        # Rotating again keeps working: this is not a one-shot latch.
        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_THREE)
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_THREE}"

    def test_timeout_scoped_client_sends_the_rotated_token(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        # The judge passes timeout_s=45 on every axis of every row, so this
        # cache — not _RUNTIME_CLIENT — is the one most evals actually use.
        from app.llm.bedrock_client import BedrockProvider

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        provider = BedrockProvider()
        client = provider._client_for_timeout(45.0)
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_ONE}"

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
        assert provider._client_for_timeout(45.0) is client
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_TWO}"

    def test_catalog_client_sends_the_rotated_token(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import _get_catalog_client

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        client = _get_catalog_client()
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_ONE}"

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
        assert _get_catalog_client() is client
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_TWO}"


# ── 2. The no-token path is UNCHANGED (the other side of the guard) ──────────


class TestNoTokenPathUnchanged:
    def test_iam_client_sends_no_bearer_header(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import _create_client_with_auth

        clean_bedrock_env.setenv("AWS_ACCESS_KEY_ID", "AKIA_FAKE_ID")
        clean_bedrock_env.setenv("AWS_SECRET_ACCESS_KEY", "FAKE-SECRET")
        client = _create_client_with_auth("bedrock-runtime", 60.0, 10)

        assert _authorization_header_for_next_request(client) is None

    def test_bearer_var_appearing_later_does_not_retrofit_a_signed_client(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        # R365 moved WHEN the token is read, never WHICH source wins. A client
        # built in IAM/SigV4 mode must stay in IAM mode: injecting a bearer
        # header into a SigV4-signed request would be a credential-precedence
        # change, not a refresh.
        from app.llm.bedrock_client import _create_client_with_auth

        clean_bedrock_env.setenv("AWS_ACCESS_KEY_ID", "AKIA_FAKE_ID")
        clean_bedrock_env.setenv("AWS_SECRET_ACCESS_KEY", "FAKE-SECRET")
        client = _create_client_with_auth("bedrock-runtime", 60.0, 10)

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
        assert _authorization_header_for_next_request(client) is None

    def test_token_unset_after_build_keeps_the_build_time_token(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        # Pre-R365 behaviour for this case was "keep using the captured token".
        # Preserved exactly — the client is UNSIGNED, so degrading to no header
        # (or to the string "Bearer None") would turn a blanked variable into an
        # instant outage.
        from app.llm.bedrock_client import _get_runtime_client

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        client = _get_runtime_client()

        clean_bedrock_env.delenv("AWS_BEARER_TOKEN_BEDROCK")
        header = _authorization_header_for_next_request(client)
        assert header == f"Bearer {TOKEN_ONE}"
        assert "None" not in header

    def test_source_precedence_is_unchanged_at_request_time(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import _get_runtime_client

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        client = _get_runtime_client()

        # All three names present at once: the documented order must still hold,
        # and it must hold for the REQUEST-time read too, not just the build.
        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
        clean_bedrock_env.setenv("AWS_BEDROCK_BEARER_TOKEN", "FAKE-SECOND-CHOICE")
        clean_bedrock_env.setenv("BEDROCK_BEARER_TOKEN", "FAKE-THIRD-CHOICE")
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_TWO}"

        clean_bedrock_env.delenv("AWS_BEARER_TOKEN_BEDROCK")
        assert (
            _authorization_header_for_next_request(client)
            == "Bearer FAKE-SECOND-CHOICE"
        )

        clean_bedrock_env.delenv("AWS_BEDROCK_BEARER_TOKEN")
        assert (
            _authorization_header_for_next_request(client)
            == "Bearer FAKE-THIRD-CHOICE"
        )


# ── 3. The token never leaks into a log record or an exception string ────────


class TestTokenNeverLeaks:
    def test_build_rotate_and_send_log_nothing_secret(
        self,
        clean_bedrock_env: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app.llm.bedrock_client import BedrockProvider, _get_runtime_client

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        with caplog.at_level(logging.DEBUG):
            client = _get_runtime_client()  # emits bedrock_runtime_client_init
            _authorization_header_for_next_request(client)
            clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
            _authorization_header_for_next_request(client)
            rendered_repr = repr(BedrockProvider())

        # Something WAS captured, or this assertion proves nothing.
        assert caplog.records, "expected at least the client-init log record"

        haystacks = [caplog.text, rendered_repr]
        for record in caplog.records:
            haystacks.append(record.getMessage())
            haystacks.append(repr(record.args))
        blob = "\n".join(haystacks)
        for secret in (TOKEN_ONE, TOKEN_TWO):
            assert secret not in blob

    def test_resolver_failure_is_swallowed_and_never_surfaces_the_token(
        self,
        clean_bedrock_env: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app.llm import bedrock_client as bc

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        client = bc._get_runtime_client()

        boom = "FAKE-SECRET-INSIDE-EXCEPTION"

        def _explode() -> str | None:
            raise RuntimeError(f"resolver blew up carrying {boom}")

        clean_bedrock_env.setattr(bc, "_resolve_bearer_token", _explode)

        with caplog.at_level(logging.DEBUG):
            header = _authorization_header_for_next_request(client)

        # The send is not broken by a failing lookup, and it degrades to the
        # build-time token rather than to an unauthenticated request.
        assert header == f"Bearer {TOKEN_ONE}"
        blob = "\n".join(
            [caplog.text, *(r.getMessage() for r in caplog.records)]
        )
        assert boom not in blob
        assert TOKEN_ONE not in blob


# ── 4. The operator hint and the real behaviour cannot drift apart ───────────


class TestHintMatchesMeasuredBehaviour:
    def test_hint_no_longer_promises_a_restart_free_rotation_of_env_files(
        self,
    ) -> None:
        from app.llm.bedrock_client import KEY_INVALID_HINT

        # The exact false claim this round removed.
        assert "with no restart" not in KEY_INVALID_HINT.lower()
        # ... replaced by the instruction that is actually true.
        assert "RESTART" in KEY_INVALID_HINT
        assert "--skip-deploys" in KEY_INVALID_HINT
        assert "redeploy" in KEY_INVALID_HINT.lower()

    def test_hint_claims_per_request_reads_and_that_claim_is_measured_here(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import KEY_INVALID_HINT, _get_runtime_client

        assert "os.environ on every request" in KEY_INVALID_HINT

        # Same assertion, measured: an IN-PROCESS update is picked up with no
        # restart and no client rebuild.
        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)
        client = _get_runtime_client()
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_ONE}"
        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_TWO)
        assert _get_runtime_client() is client
        assert _authorization_header_for_next_request(client) == f"Bearer {TOKEN_TWO}"

    def test_hint_claim_that_a_rewritten_dotenv_cannot_displace_os_environ(
        self, tmp_path, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        # The hint tells the operator a value typed into .env or the Railway
        # dashboard does not reach a RUNNING process. The load-bearing mechanism
        # is app/config.py::_load_dotenv_once loading with override=False, so an
        # already-set variable always wins. Measured, not asserted from prose.
        from dotenv import load_dotenv

        from app.llm.bedrock_client import KEY_INVALID_HINT

        assert "override=False" in KEY_INVALID_HINT
        assert ".env is read once at import" in KEY_INVALID_HINT

        env_file = tmp_path / ".env"
        env_file.write_text(
            f"AWS_BEARER_TOKEN_BEDROCK={TOKEN_THREE}\n", encoding="utf-8"
        )
        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == TOKEN_ONE

    def test_connectivity_check_returns_exactly_this_hint(
        self, clean_bedrock_env: pytest.MonkeyPatch
    ) -> None:
        # Pins the constant to the branch it documents, so the hint cannot be
        # corrected in one place and left stale in the other. No AWS call:
        # complete() is replaced wholesale.
        from app.llm import bedrock_client as bc

        clean_bedrock_env.setenv("AWS_BEARER_TOKEN_BEDROCK", TOKEN_ONE)

        def _fake_complete(self, req):  # noqa: ANN001, ARG001
            return bc.BedrockResponse(error="api_key_invalid_403", model=req.model)

        clean_bedrock_env.setattr(bc.BedrockProvider, "complete", _fake_complete)

        result = bc.check_connectivity_and_permissions("eu.anthropic.fake-model")

        assert result["status"] == "key_invalid"
        assert result["hint"] == bc.KEY_INVALID_HINT
        assert TOKEN_ONE not in str(result)
