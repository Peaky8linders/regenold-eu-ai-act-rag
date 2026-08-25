"""R365 — the Cloudflare Access service token must be pinned to a TRUSTED host,
not to whatever ``OPENAI_API_BASE`` happens to name.

R277 scoped the token by comparing the instance's ``base_url`` host against a
"protected host" that, with ``CF_ACCESS_HOSTNAME`` unset, was derived from
``OPENAI_API_BASE`` itself. That comparison is self-referential: the destination
was also the trust anchor, so it always agreed with itself. Measured on ``main``
before this round::

    OPENAI_API_BASE=https://openrouter.ai/api/v1, CF_ACCESS_HOSTNAME unset
    _resolve_cf_access_headers("https://openrouter.ai/api/v1")
      -> {'CF-Access-Client-Id': 'ID', 'CF-Access-Client-Secret': 'SECRET'}

One env var shipped the org's Zero Trust service-token SECRET to a third party.
That is the same env var R360.7 (``stage2_policy`` destination pinning) exists to
defend against, and ``AGENTS.md``'s prohibited list names Cloudflare Zero Trust
service tokens explicitly.

These tests are TWO-SIDED on purpose. The leak half is the security fix; the
attach half is load-bearing in the opposite direction — ``CLAUDE.md`` records
that without ``CF_ACCESS_*`` reaching the edge, production serves ZERO Claude Max
and every Stage-2 call falls back. A pin that over-tightens is an outage.

They also assert on the bytes that would go ON THE WIRE (``MockTransport``
captures the real ``complete()`` request), not on the shape of the resolver —
this repo's signature failure is a lever that reads correctly in the diff and
never fires.
"""
from __future__ import annotations

import httpx
import pytest

from app.llm.openai_wrapper_provider import (
    _OpenAIWrapperProvider,
    _resolve_cf_access_headers,
)

CF_ID = "test-client-id.access"
CF_SECRET = "test-client-secret-value"

#: The real Access-protected tunnel. Production MUST keep getting the token.
WRAPPER = "https://wrapper.antifragile-ai.net/v1"

#: Hosts that must never see the secret. ``OPENAI_API_BASE`` names each of them
#: in turn, which is exactly the configuration that leaked.
THIRD_PARTY_BASES = [
    "https://openrouter.ai/api/v1",
    "https://api.groq.com/openai/v1",
    "https://api.mistral.ai/v1",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
    "https://api.openai.com/v1",
    "https://attacker.example.com/v1",
]

#: The documented local dev base and the eval blackhole base. Neither has a
#: Cloudflare edge in front of it, so neither may receive the token — and
#: neither may start erroring either.
LOCAL_BASES = [
    "http://127.0.0.1:8000/v1",  # CLAUDE.md local wrapper setup
    "http://127.0.0.1:1/v1",     # AGENTS.md deterministic eval base
    "http://localhost:8000/v1",
]

CF_HEADER_KEYS = ("CF-Access-Client-Id", "CF-Access-Client-Secret")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every knob that can move the pin, cleared. ``REGENOLD_SKIP_DOTENV`` so a
    developer's local ``.env`` (which carries the REAL service token) cannot
    silently arm or disarm any of this — the R330 import-time coupling."""
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    for var in (
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "CF_ACCESS_HOSTNAME",
        "OPENAI_API_BASE",
        "REGENOLD_STAGE2_PRIMARY_HOSTS",
        "REGENOLD_STAGE2_STRICT_TRANSPORT",
    ):
        monkeypatch.delenv(var, raising=False)


def _set_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", CF_ID)
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", CF_SECRET)


def _wire_headers(base_url: str) -> httpx.Headers:
    """Headers of the request ``complete()`` actually puts on the wire.

    Builds a real provider (so ``__init__`` resolves the token exactly as it
    does in production), then swaps its pooled client for one on a
    ``MockTransport`` that records the outbound request. This is the counter
    equivalent for a header: it proves the bytes leave, or prove they do not.
    """
    from app.llm.openai_wrapper_provider import OpenAIWrapperRequest

    provider = _OpenAIWrapperProvider(base_url=base_url, api_key="k")
    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "model": "m"},
        )

    provider._client = httpx.Client(
        base_url=base_url, transport=httpx.MockTransport(_handler)
    )
    provider.complete(OpenAIWrapperRequest(user="hello", model="sonnet"))
    assert captured, "provider made no request — the probe itself is broken"
    return captured[0].headers


class TestProductionStillGetsTheToken:
    """The half that must NOT over-tighten. Without these headers reaching the
    Access edge the tunnel answers 401, the engine reads ``api_status_401`` and
    production serves NO Claude Max at all."""

    def test_tunnel_host_gets_token_with_openai_api_base_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact Railway configuration."""
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        assert _resolve_cf_access_headers(WRAPPER) == {
            "CF-Access-Client-Id": CF_ID,
            "CF-Access-Client-Secret": CF_SECRET,
        }

    def test_tunnel_host_gets_token_with_openai_api_base_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_DEFAULT_WRAPPER_BASE`` is the fallback destination, so it must
        also be trusted — otherwise an unset ``OPENAI_API_BASE`` silently kills
        Stage-2."""
        _set_token(monkeypatch)
        assert _resolve_cf_access_headers(WRAPPER) != {}

    def test_tunnel_token_reaches_the_wire(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        headers = _wire_headers(WRAPPER)
        assert headers["CF-Access-Client-Id"] == CF_ID
        assert headers["CF-Access-Client-Secret"] == CF_SECRET
        # the pre-existing headers survive the pin
        assert headers["Authorization"].startswith("Bearer ")

    def test_case_insensitive_tunnel_host_still_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
        assert _resolve_cf_access_headers("https://WRAPPER.ANTIFRAGILE-AI.NET/v1") != {}


class TestUntrustedHostGetsNothing:
    """THE DEFECT. With ``CF_ACCESS_HOSTNAME`` unset, ``OPENAI_API_BASE`` used
    to be its own trust anchor, so naming a third party there shipped it the
    secret."""

    @pytest.mark.parametrize("base", THIRD_PARTY_BASES)
    def test_openai_api_base_cannot_arm_its_own_host(
        self, monkeypatch: pytest.MonkeyPatch, base: str
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", base)
        assert _resolve_cf_access_headers(base) == {}

    @pytest.mark.parametrize("base", THIRD_PARTY_BASES)
    def test_no_cf_header_reaches_the_wire_for_untrusted_host(
        self, monkeypatch: pytest.MonkeyPatch, base: str
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", base)
        headers = _wire_headers(base)
        for key in CF_HEADER_KEYS:
            assert key not in headers, f"service token leaked to {base}"
        # and the secret is nowhere in the request at all, under any casing
        joined = " ".join(f"{k}: {v}" for k, v in headers.items())
        assert CF_SECRET not in joined
        assert CF_ID not in joined

    def test_strict_transport_off_does_not_reopen_the_leak(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R365 pins to the ALLOWLIST DATA (``allowed_primary_hosts``), never to
        ``is_primary_base_url_allowed`` — that one short-circuits ``True`` when
        strict mode is off, which would hand the escape hatch straight back.
        Secret scoping and the Stage-2 transport contract are different concerns:
        the host list is shared, the off-switch is not."""
        _set_token(monkeypatch)
        monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
        monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
        assert _resolve_cf_access_headers("https://openrouter.ai/api/v1") == {}
        # ...and the legitimate host is unaffected by the off-switch either way
        assert _resolve_cf_access_headers(WRAPPER) != {}

    def test_lookalike_hosts_get_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exact host equality, never suffix matching."""
        _set_token(monkeypatch)
        for evil in (
            "https://wrapper.antifragile-ai.net.attacker.tld/v1",
            "https://notwrapper.antifragile-ai.net/v1",
            "https://wrapper.antifragile-ai.net.evil/v1",
        ):
            monkeypatch.setenv("OPENAI_API_BASE", evil)
            assert _resolve_cf_access_headers(evil) == {}


class TestExplicitHostnamePinStillWorks:
    """``CF_ACCESS_HOSTNAME`` remains the operator's explicit override — it is a
    trust DECLARATION, unlike ``OPENAI_API_BASE`` which is only a destination."""

    def test_explicit_hostname_arms_that_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("CF_ACCESS_HOSTNAME", "tunnel2.antifragile-ai.net")
        assert _resolve_cf_access_headers("https://tunnel2.antifragile-ai.net/v1") != {}

    def test_explicit_hostname_still_pins_everything_else_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("CF_ACCESS_HOSTNAME", "wrapper.antifragile-ai.net")
        assert _resolve_cf_access_headers(WRAPPER) != {}
        assert _resolve_cf_access_headers("https://api.groq.com/openai/v1") == {}

    def test_explicit_hostname_narrows_rather_than_widens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When set, it is the ONLY trusted host — the default allowlist does
        not leak back in underneath it."""
        _set_token(monkeypatch)
        monkeypatch.setenv("CF_ACCESS_HOSTNAME", "tunnel2.antifragile-ai.net")
        assert _resolve_cf_access_headers(WRAPPER) == {}


class TestOperatorAllowlistIsTheSingleSourceOfTruth:
    """R365 reuses ``stage2_policy.allowed_primary_hosts()`` rather than minting
    a second host list. An operator who renames the tunnel edits one place."""

    def test_renamed_tunnel_via_stage2_allowlist_gets_the_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv(
            "REGENOLD_STAGE2_PRIMARY_HOSTS", "tunnel-b.antifragile-ai.net"
        )
        monkeypatch.setenv("OPENAI_API_BASE", "https://tunnel-b.antifragile-ai.net/v1")
        assert _resolve_cf_access_headers("https://tunnel-b.antifragile-ai.net/v1") != {}

    def test_narrowing_the_allowlist_never_disarms_the_default_tunnel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Belt-and-braces: the repo's own ``_DEFAULT_WRAPPER_BASE`` host is a
        hardcoded constant naming the Access-protected edge, so it stays
        trusted even if the allowlist var is set to something narrower. A typo
        in an env var must not take Stage-2 down."""
        _set_token(monkeypatch)
        monkeypatch.setenv(
            "REGENOLD_STAGE2_PRIMARY_HOSTS", "tunnel-b.antifragile-ai.net"
        )
        assert _resolve_cf_access_headers(WRAPPER) != {}

    def test_allowlist_cannot_arm_a_third_party_it_does_not_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv(
            "REGENOLD_STAGE2_PRIMARY_HOSTS", "tunnel-b.antifragile-ai.net"
        )
        monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
        assert _resolve_cf_access_headers("https://openrouter.ai/api/v1") == {}


class TestLocalDevAndEvalsDoNotRegress:
    """The documented local wrapper (``127.0.0.1:8000``) and the eval blackhole
    (``127.0.0.1:1``) must keep getting NO token — a local wrapper has no
    Cloudflare edge, so the token would be pointless and would widen the
    secret's blast radius into a local process. They are on
    ``STAGE2_PRIMARY_HOSTS``, so this is the case where the reused allowlist is
    deliberately NOT sufficient on its own."""

    @pytest.mark.parametrize("base", LOCAL_BASES)
    def test_local_base_gets_no_token(
        self, monkeypatch: pytest.MonkeyPatch, base: str
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", base)
        assert _resolve_cf_access_headers(base) == {}

    @pytest.mark.parametrize("base", LOCAL_BASES)
    def test_local_base_still_serves_requests(
        self, monkeypatch: pytest.MonkeyPatch, base: str
    ) -> None:
        """The pin must not turn a local dev / eval call into an error."""
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", base)
        headers = _wire_headers(base)
        assert headers["Authorization"].startswith("Bearer ")
        for key in CF_HEADER_KEYS:
            assert key not in headers

    def test_explicit_hostname_cannot_force_the_token_onto_localhost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("CF_ACCESS_HOSTNAME", "127.0.0.1")
        assert _resolve_cf_access_headers("http://127.0.0.1:8000/v1") == {}


class TestFailSoft:
    """Any missing / unparseable value yields ``{}`` — the safe direction for a
    secret — and never raises during provider construction."""

    @pytest.mark.parametrize("base", ["", "::::not a url::::", "not-a-url"])
    def test_malformed_base_url_yields_no_token(
        self, monkeypatch: pytest.MonkeyPatch, base: str
    ) -> None:
        _set_token(monkeypatch)
        monkeypatch.setenv("OPENAI_API_BASE", base)
        assert _resolve_cf_access_headers(base) == {}

    def test_no_token_configured_is_inert_everywhere(self) -> None:
        for base in [WRAPPER, *THIRD_PARTY_BASES, *LOCAL_BASES]:
            assert _resolve_cf_access_headers(base) == {}
