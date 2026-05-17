"""R45 production-hardening regression suite.

Covers the Fix-1 batch from ``docs/reviews/R45_PRODUCTION_REVIEW.md``:

* Fix 1.1 — route swaps strict auth → optional auth (competition deploy
  must serve anonymous traffic).
* Fix 1.2 — multi-worker + memory:// rate-limit storage logs a warning.
* Fix 1.3 — Neo4j URI userinfo is redacted at log sites.
* Fix 1.4 — audit-chain failures log at WARNING (not DEBUG).
* Fix 1.5 — audit payload ``tier`` is derived from the resolved key,
  not hardcoded.
"""

from __future__ import annotations

import logging
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app


def _client() -> TestClient:
    return TestClient(app)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


# ─── Fix 1.1 — optional-auth swap ──────────────────────────────────────────


def test_anonymous_request_returns_200_with_configured_key() -> None:
    """Acceptance check for Fix 1.1.

    With ``P2P_REGENOLD_API_KEY`` configured on the deploy, an anonymous
    request (no header) MUST return 200, not 401 / 503. This is the
    competition contract.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert isinstance(body.get("answer"), str) and body["answer"], (
        "anonymous request must receive a non-empty answer"
    )
    assert "references" in body and isinstance(body["references"], list)


def test_anonymous_request_returns_200_unconfigured_deploy() -> None:
    """Companion to Fix 1.1 — unconfigured deploy (no partner key set
    on Railway) must STILL accept anonymous traffic.

    Previously, ``require_regenold_api_key`` returned 503 when
    ``_configured_key() is None``. With the optional dep, the route
    serves anonymous traffic regardless of partner-key provisioning.
    """
    saved = settings.regenold.api_key
    settings.regenold.api_key = None
    try:
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=_messages("What does Art. 13(1)(a) require?"),
        )
        assert r.status_code == 200, r.json()
    finally:
        settings.regenold.api_key = saved


def test_wrong_header_returns_403_invariant() -> None:
    """Fix 1.1 invariant — a header that's present but non-matching
    still returns 403. Silent downgrade would hide partner-side typos
    / stale keys, so the explicit failure stays.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "wrong-key"},
        json=_messages("Summarise EU AI Act Art. 13."),
    )
    assert r.status_code == 403, r.json()


def test_valid_header_still_gets_partner_tier() -> None:
    """Fix 1.1 invariant — a valid header still works and the audit
    payload picks ``tier="partner"`` (Fix 1.5 derives from the key).
    """
    from app.evidence.store import get_evidence_store

    settings.regenold.api_key = SecretStr("regenold-test-key")
    store = get_evidence_store()
    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "regenold-test-key"},
        json=_messages("Summarise EU AI Act Art. 26."),
    )
    assert r.status_code == 200, r.json()

    rows = list(store.get_chain(tenant_id="partner:regenold", limit=10))
    assert rows, "no partner:regenold chain entry written for valid-header request"
    payload = rows[0].payload if isinstance(rows[0].payload, dict) else {}
    assert payload.get("tier") == "partner"


# ─── Fix 1.2 — multi-worker memory:// warning ──────────────────────────────


def test_multiworker_memory_storage_emits_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fix 1.2 — when WEB_CONCURRENCY >= 2 AND storage_uri starts with
    memory://, the boot-time guard logs a warning.

    We reload the rate-limit module under a patched env so the
    boot-time check re-fires with the multi-worker config.
    """
    import importlib

    import app.rate_limit as rate_limit_mod

    with caplog.at_level(logging.WARNING, logger="app.rate_limit"):
        with mock.patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}, clear=False):
            # Re-import so the module-level boot check fires under the
            # patched env. The Limiter instance is rebuilt as a side
            # effect — that's fine; nothing in tests references the
            # original limiter singleton at this point.
            importlib.reload(rate_limit_mod)

    matching = [
        rec
        for rec in caplog.records
        if "Rate limit storage uri = memory://" in rec.getMessage()
    ]
    assert matching, (
        "expected a WARNING about memory:// multi-worker config; "
        f"got: {[r.getMessage() for r in caplog.records]}"
    )
    # Restore a clean state for the rest of the suite.
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("WEB_CONCURRENCY", None)
        importlib.reload(rate_limit_mod)


def test_single_worker_memory_storage_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fix 1.2 — when only 1 worker, memory:// is safe and no warning."""
    import importlib

    import app.rate_limit as rate_limit_mod

    with caplog.at_level(logging.WARNING, logger="app.rate_limit"):
        os.environ.pop("WEB_CONCURRENCY", None)
        importlib.reload(rate_limit_mod)

    matching = [
        rec
        for rec in caplog.records
        if "Rate limit storage uri = memory://" in rec.getMessage()
    ]
    assert not matching, (
        "no warning should fire for single-worker memory:// config"
    )


# ─── Fix 1.3 — Neo4j URI redaction ─────────────────────────────────────────


def test_redact_neo4j_uri_strips_userinfo() -> None:
    """Fix 1.3 acceptance — ``bolt://user:pass@host:7687`` →
    ``bolt://[redacted]@host:7687``.
    """
    from app.graph.client import _redact_neo4j_uri

    assert (
        _redact_neo4j_uri("bolt://neo4j:secret@host:7687")
        == "bolt://[redacted]@host:7687"
    )
    assert (
        _redact_neo4j_uri("bolt+s://user:passw0rd@aura-host.io:7687")
        == "bolt+s://[redacted]@aura-host.io:7687"
    )
    assert (
        _redact_neo4j_uri("neo4j+s://admin:hunter2@cluster.example:7687")
        == "neo4j+s://[redacted]@cluster.example:7687"
    )


def test_redact_neo4j_uri_passthrough_when_no_userinfo() -> None:
    """Fix 1.3 invariant — a URI without userinfo is unchanged."""
    from app.graph.client import _redact_neo4j_uri

    assert _redact_neo4j_uri("bolt+s://host:7687") == "bolt+s://host:7687"
    assert _redact_neo4j_uri("neo4j://localhost:7687") == "neo4j://localhost:7687"
    assert _redact_neo4j_uri("") == ""
    assert _redact_neo4j_uri(None) == ""


def test_redact_neo4j_uri_handles_embedded_in_message() -> None:
    """Fix 1.3 — the helper also redacts URIs embedded in exception
    messages (driver errors love to quote the connection target).
    """
    from app.graph.client import _redact_neo4j_uri

    msg = (
        "Failed to connect to bolt://neo4j:secret@host:7687: "
        "ServiceUnavailable raised"
    )
    redacted = _redact_neo4j_uri(msg)
    assert "secret" not in redacted
    assert "[redacted]" in redacted
    assert "host:7687" in redacted


# ─── Fix 1.4 — audit-chain failure logged at WARNING ───────────────────────


def test_audit_chain_failure_logged_at_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fix 1.4 — when ``store.record`` raises, the route logs a WARNING
    (not DEBUG). EU AI Act Art. 12 record-keeping needs operator
    visibility on audit-chain outages.

    The route's logger is a structlog ``PrintLogger`` (default config),
    which writes to stdout — we capture via capsys instead of caplog.
    """
    settings.regenold.api_key = SecretStr("regenold-test-key")

    # Replace the evidence-store record() with one that raises.
    from app.evidence.store import get_evidence_store

    store = get_evidence_store()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated postgres outage")

    with mock.patch.object(store, "record", side_effect=_boom):
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
        )
    # The route must NOT 500 — audit failure is best-effort.
    assert r.status_code == 200, r.json()

    captured = capsys.readouterr().out
    # The structlog-formatted line includes the level marker + the
    # event key. Fix 1.4 promoted DEBUG → WARNING.
    evidence_lines = [
        line
        for line in captured.splitlines()
        if "regenold_question_evidence_failed" in line
    ]
    assert evidence_lines, (
        f"audit-chain failure event missing from log output: {captured!r}"
    )
    # The relevant line must carry "warning" (Fix 1.4 contract).
    assert any("warning" in line.lower() for line in evidence_lines), (
        f"expected WARNING-level audit-chain failure log; got: {evidence_lines!r}"
    )


# ─── Fix 1.5 — audit tier derived from key ─────────────────────────────────


def test_anonymous_request_audit_payload_has_anonymous_tier() -> None:
    """Fix 1.5 acceptance — anonymous request audit payload carries
    ``tier="anonymous"``, not ``tier="partner"``.
    """
    from app.evidence.store import get_evidence_store

    settings.regenold.api_key = SecretStr("regenold-test-key")
    store = get_evidence_store()
    before_anon = len(list(store.get_chain(tenant_id="anonymous:regenold", limit=1000)))

    c = _client()
    r = c.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json=_messages("Summarise EU AI Act Art. 13(1)(a)."),
    )
    assert r.status_code == 200, r.json()

    rows = list(store.get_chain(tenant_id="anonymous:regenold", limit=10))
    assert len(rows) > before_anon, "no anonymous:regenold chain entry written"
    payload = rows[0].payload if isinstance(rows[0].payload, dict) else {}
    assert payload.get("tier") == "anonymous", (
        f"expected tier=anonymous on anon traffic; got {payload.get('tier')!r}"
    )


def test_resolve_audit_tier_helper_contract() -> None:
    """Pure unit test for the Fix 1.5 helper."""
    from app.routes.regenold import _resolve_audit_tier

    settings.regenold.api_key = SecretStr("regenold-test-key")
    assert _resolve_audit_tier(None) == "anonymous"
    assert _resolve_audit_tier("regenold-test-key") == "partner"
    # Defensive fallback — invalid key resolves to anonymous (the dep
    # would have raised 403 in practice, so this branch is route-internal).
    assert _resolve_audit_tier("wrong-key") == "anonymous"


# ─── Fix 1.6 — structlog JSON helper exists (P2, opt-in) ───────────────────


def test_configure_logging_helper_is_importable() -> None:
    """Fix 1.6 — the helper exists, is callable, and is idempotent.

    The call-site wiring lives in ``app/main.py`` (owned by Fix 3 this
    sprint), but we pin the helper's surface here so a future refactor
    doesn't drop it.
    """
    from app.logging import configure_logging, is_configured

    # Idempotent — call twice without raising.
    configure_logging()
    configure_logging()
    assert is_configured() is True
