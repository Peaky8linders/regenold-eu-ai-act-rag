"""R277 — Cloudflare Access service-token support for the Claude Max wrapper.

Context: a Cloudflare Access (Zero Trust) application now fronts
``wrapper.antifragile-ai.net``. Railway's unauthenticated calls get an HTML
login page + HTTP 401, so the engine falls back to deterministic and
production serves NO Claude Max. Access is worth keeping (the wrapper has no
auth of its own), so the fix is a service token.

The load-bearing invariant is NOT "the headers get attached" — it is
"the secret NEVER reaches a third-party host". ``_OpenAIWrapperProvider`` is
reused verbatim for Groq / Gemini / Mistral, so an unscoped implementation
would ship a Cloudflare service-token secret to api.groq.com,
api.mistral.ai and generativelanguage.googleapis.com.
"""
from __future__ import annotations

import pytest

from app.llm.openai_wrapper_provider import (
    _OpenAIWrapperProvider,
    _resolve_cf_access_headers,
)

CF_ID = "test-client-id.access"
CF_SECRET = "test-client-secret-value"
WRAPPER = "https://wrapper.antifragile-ai.net/v1"


@pytest.fixture(autouse=True)
def _clean_cf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "CF_ACCESS_HOSTNAME",
        "OPENAI_API_BASE",
    ):
        monkeypatch.delenv(var, raising=False)


def _set_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", CF_ID)
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", CF_SECRET)


class TestDefaultOffContract:
    """With no token configured, behaviour is byte-identical to pre-R277."""

    def test_no_env_no_headers(self) -> None:
        assert _resolve_cf_access_headers(WRAPPER) == {}

    def test_id_without_secret_is_inert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", CF_ID)
        assert _resolve_cf_access_headers(WRAPPER) == {}

    def test_secret_without_id_is_inert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", CF_SECRET)
        assert _resolve_cf_access_headers(WRAPPER) == {}

    def test_blank_values_are_inert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "   ")
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "   ")
        assert _resolve_cf_access_headers(WRAPPER) == {}

    def test_provider_headers_unchanged_without_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        p = _OpenAIWrapperProvider()
        h = p._headers()
        assert "CF-Access-Client-Id" not in h
        assert "CF-Access-Client-Secret" not in h
        assert h["Authorization"].startswith("Bearer ")


class TestAttachesToProtectedHost:
    def test_attaches_for_wrapper_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        assert _resolve_cf_access_headers(WRAPPER) == {
            "CF-Access-Client-Id": CF_ID,
            "CF-Access-Client-Secret": CF_SECRET,
        }

    def test_provider_sends_both_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        p = _OpenAIWrapperProvider()
        h = p._headers()
        assert h["CF-Access-Client-Id"] == CF_ID
        assert h["CF-Access-Client-Secret"] == CF_SECRET
        # and the pre-existing headers survive
        assert h["Content-Type"] == "application/json"
        assert h["Authorization"].startswith("Bearer ")

    def test_explicit_hostname_env_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("CF_ACCESS_HOSTNAME", "wrapper.antifragile-ai.net")
        assert _resolve_cf_access_headers(WRAPPER) != {}
        # ...and the Groq host still gets nothing even though it is the base
        assert _resolve_cf_access_headers("https://api.groq.com/openai/v1") == {}

    def test_falls_back_to_default_wrapper_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OPENAI_API_BASE unset -> the default wrapper host is the protected one."""
        _set_token(monkeypatch)
        assert _resolve_cf_access_headers(WRAPPER) != {}


class TestNeverLeaksToThirdParties:
    """The security-critical invariant. A regression here ships a Cloudflare
    service-token secret to a third-party LLM vendor."""

    @pytest.mark.parametrize(
        "third_party",
        [
            "https://api.groq.com/openai/v1",
            "https://api.mistral.ai/v1",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "https://api.openai.com/v1",
            "https://openrouter.ai/api/v1",
        ],
    )
    def test_no_token_for_third_party_hosts(
        self, monkeypatch: pytest.MonkeyPatch, third_party: str
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        assert _resolve_cf_access_headers(third_party) == {}

    @pytest.mark.parametrize(
        "third_party",
        [
            "https://api.groq.com/openai/v1",
            "https://api.mistral.ai/v1",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ],
    )
    def test_provider_instance_for_third_party_sends_no_token(
        self, monkeypatch: pytest.MonkeyPatch, third_party: str
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        p = _OpenAIWrapperProvider(base_url=third_party, api_key="k")
        h = p._headers()
        assert "CF-Access-Client-Id" not in h
        assert "CF-Access-Client-Secret" not in h

    def test_lookalike_host_gets_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Suffix-style near-miss must not match (no endswith matching)."""
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        assert _resolve_cf_access_headers("https://evil-wrapper.antifragile-ai.net.attacker.tld/v1") == {}
        assert _resolve_cf_access_headers("https://notwrapper.antifragile-ai.net/v1") == {}

    @pytest.mark.parametrize(
        "local", ["http://127.0.0.1:8000/v1", "http://localhost:8000/v1"]
    )
    def test_local_wrapper_gets_no_token(
        self, monkeypatch: pytest.MonkeyPatch, local: str
    ) -> None:
        """A local wrapper has no Cloudflare edge in front — sending the token
        there is pointless and needlessly widens the secret's blast radius."""
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", local)
        assert _resolve_cf_access_headers(local) == {}


class TestFailSoft:
    def test_malformed_base_url_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", "::::not a url::::")
        assert _resolve_cf_access_headers("::::not a url::::") == {}

    def test_empty_base_url_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_token(monkeypatch)
        assert _resolve_cf_access_headers("") == {}

    def test_case_insensitive_host_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        assert _resolve_cf_access_headers("https://WRAPPER.ANTIFRAGILE-AI.NET/v1") != {}
