"""Lexy sign-up funnel — user store + auth routes + Q&A containment.

Covers the R-signup deliverable:
* :mod:`app.integrations.regenold.user_store` (in-memory backend, key
  format, email normalisation, idempotency, fast-path validation);
* the ``/api/v1/regenold/auth/{signup,signin,me}`` routes;
* self-service ``lexy_sk_...`` keys cannot access partner-only paid Q&A.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.integrations.regenold import auth as auth_mod
from app.integrations.regenold import user_store as us
from app.main import app
from app.rate_limit import limiter


@pytest.fixture(autouse=True)
def _isolate():
    """Fresh user store + clean partner key + no rate-limiting per test."""
    us.reset_user_store_for_tests()
    saved_key = settings.regenold.api_key
    saved_limiter = limiter.enabled
    settings.regenold.api_key = None
    limiter.enabled = False
    try:
        yield
    finally:
        settings.regenold.api_key = saved_key
        limiter.enabled = saved_limiter
        us.reset_user_store_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── user_store unit ───────────────────────────────────────────────────────────


def test_generate_api_key_format() -> None:
    k = us.generate_api_key()
    assert k.startswith("lexy_sk_")
    assert len(k) > 16
    assert us.generate_api_key() != us.generate_api_key()  # unique


@pytest.mark.parametrize(
    "raw,valid",
    [
        ("a@b.co", True),
        ("  Jane.Doe@Example.COM ", True),
        ("no-at-sign", False),
        ("missing@domain", False),
        ("", False),
        ("a@b", False),
    ],
)
def test_is_valid_email(raw: str, valid: bool) -> None:
    assert us.is_valid_email(raw) is valid


def test_normalise_email_lowercases_and_strips() -> None:
    assert us.normalise_email("  Foo@BAR.com ") == "foo@bar.com"


def test_in_memory_create_or_get_idempotent() -> None:
    store = us.InMemoryUserStore()
    rec1, created1 = store.create_or_get("X@Y.com", name="X", company="Acme")
    assert created1 is True
    assert rec1.email == "x@y.com"
    assert rec1.api_key.startswith("lexy_sk_")
    rec2, created2 = store.create_or_get("x@y.com")
    assert created2 is False
    assert rec2.api_key == rec1.api_key  # same key on re-signup
    assert store.count() == 1


def test_in_memory_lookup_by_key() -> None:
    store = us.InMemoryUserStore()
    rec, _ = store.create_or_get("a@b.com")
    assert store.get_by_api_key(rec.api_key).email == "a@b.com"
    assert store.has_api_key(rec.api_key) is True
    assert store.has_api_key("lexy_sk_nope") is False
    assert store.get_by_api_key("") is None


def test_is_registered_user_key_via_singleton() -> None:
    store = us.get_user_store()
    rec, _ = store.create_or_get("reg@x.com")
    assert us.is_registered_user_key(rec.api_key) is True
    assert us.is_registered_user_key("lexy_sk_unknown") is False
    assert us.is_registered_user_key(None) is False
    assert us.is_registered_user_key("") is False


# ── auth helper ───────────────────────────────────────────────────────────────


def test_is_known_regenold_key_partner_and_user() -> None:
    settings.regenold.api_key = SecretStr("partner-abc")
    store = us.get_user_store()
    rec, _ = store.create_or_get("u@x.com")
    assert auth_mod.is_known_regenold_key("partner-abc") is True  # partner key
    assert auth_mod.is_known_regenold_key(rec.api_key) is True    # user key
    assert auth_mod.is_known_regenold_key("lexy_sk_bogus") is False
    # validate_regenold_api_key stays partner-only (user key is NOT a match)
    assert auth_mod.validate_regenold_api_key(rec.api_key) is False
    assert auth_mod.validate_regenold_api_key("partner-abc") is True


# ── signup route ──────────────────────────────────────────────────────────────


def test_signup_issues_key(client: TestClient) -> None:
    r = client.post(
        "/api/v1/regenold/auth/signup",
        json={"email": "New.User@Example.com", "name": "New", "company": "Acme"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["api_key"].startswith("lexy_sk_")
    assert d["email"] == "new.user@example.com"
    assert d["returning"] is False
    assert d["name"] == "New"


def test_signup_idempotent(client: TestClient) -> None:
    a = client.post("/api/v1/regenold/auth/signup", json={"email": "dup@x.com"}).json()
    b = client.post("/api/v1/regenold/auth/signup", json={"email": "dup@x.com"}).json()
    assert a["api_key"] == b["api_key"]
    assert a["returning"] is False
    assert b["returning"] is True


def test_signup_invalid_email_400(client: TestClient) -> None:
    r = client.post("/api/v1/regenold/auth/signup", json={"email": "nope"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_email"


# ── signin route ──────────────────────────────────────────────────────────────


def test_signin_returns_existing_key(client: TestClient) -> None:
    key = client.post(
        "/api/v1/regenold/auth/signup", json={"email": "back@x.com"}
    ).json()["api_key"]
    r = client.post("/api/v1/regenold/auth/signin", json={"email": "back@x.com"})
    assert r.status_code == 200
    assert r.json()["api_key"] == key
    assert r.json()["returning"] is True


def test_signin_unknown_404(client: TestClient) -> None:
    r = client.post("/api/v1/regenold/auth/signin", json={"email": "ghost@x.com"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "account_not_found"


# ── /me route ─────────────────────────────────────────────────────────────────


def test_me_with_key(client: TestClient) -> None:
    key = client.post(
        "/api/v1/regenold/auth/signup", json={"email": "me@x.com", "name": "Me"}
    ).json()["api_key"]
    r = client.get("/api/v1/regenold/auth/me", headers={"X-Regenold-Api-Key": key})
    assert r.status_code == 200
    assert r.json()["email"] == "me@x.com"
    assert r.json()["name"] == "Me"


def test_me_missing_key_401(client: TestClient) -> None:
    assert client.get("/api/v1/regenold/auth/me").status_code == 401


def test_me_unknown_key_403(client: TestClient) -> None:
    r = client.get("/api/v1/regenold/auth/me", headers={"X-Regenold-Api-Key": "lexy_sk_x"})
    assert r.status_code == 403


# ── the load-bearing invariant: issued key works for the Q&A route ────────────


def test_issued_key_cannot_open_unconfigured_ask_route(client: TestClient) -> None:
    """Self-service signup cannot provision access to metered Q&A."""
    settings.regenold.api_key = None  # no partner key on this deploy
    key = client.post(
        "/api/v1/regenold/auth/signup", json={"email": "qa@x.com"}
    ).json()["api_key"]
    r = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": key},
        json={
            "messages": [
                {"role": "user", "content": "What are the obligations of deployers of high-risk AI systems?"}
            ]
        },
    )
    assert r.status_code == 503


def test_issued_key_cannot_access_partner_only_ask_route(client: TestClient) -> None:
    """A freely issued user key must not grant the partner's inference budget."""
    settings.regenold.api_key = SecretStr("the-partner-key")
    key = client.post(
        "/api/v1/regenold/auth/signup", json={"email": "qa2@x.com"}
    ).json()["api_key"]
    r = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": key},
        json={"messages": [{"role": "user", "content": "What is Article 5?"}]},
    )
    assert r.status_code == 403


def test_bogus_key_still_403s_when_partner_key_configured(client: TestClient) -> None:
    """With a partner key configured, an unknown header still fails loudly."""
    settings.regenold.api_key = SecretStr("the-partner-key")
    r = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "lexy_sk_not_a_real_key"},
        json={"messages": [{"role": "user", "content": "What is Article 5?"}]},
    )
    assert r.status_code == 403


# ── email module is optional / fail-soft ──────────────────────────────────────


def test_email_not_configured_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.regenold import email as lexy_email

    # Resend (the legit-ai provider) — no key configured → no-op.
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_RESEND_API_KEY", raising=False)
    assert lexy_email.is_configured() is False
    # Must not raise and must return False when unconfigured.
    assert lexy_email.send_welcome_email(to_email="x@y.com", api_key="lexy_sk_z", name="X") is False
