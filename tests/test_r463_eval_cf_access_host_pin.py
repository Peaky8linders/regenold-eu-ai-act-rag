"""R463 — the eval harnesses must not hand the Zero Trust service token to a host
that merely happens to be named by an environment variable.

Two callers were left behind when R365/R432 pinned the token inside the app and
R419 pinned it in ``evals/official/judge.py``:

* ``evals/harness/frontier_baseline.py`` built the ``CF-Access-*`` pair straight
  from the env and attached it to whatever base it was given — no host test at
  all;
* ``evals/official/build_gold.py`` guarded it with a SUBSTRING test
  (``"127.0.0.1" not in URL and "localhost" not in URL``), which is not a host
  pin: every other base, a third party included, received the SECRET.

Both had the shape, measured on ``main`` with ``CF_ACCESS_*`` set and
``OPENAI_API_BASE=https://openrouter.ai/api/v1``::

    CF-Access-Client-Id: <the id>.access
    CF-Access-Client-Secret: <the org's Zero Trust secret>

One env var exfiltrated a credential that AGENTS.md's prohibited list names —
the same class R365 closed one layer up, which is why the remedy is to route
both callers through the pinned resolver rather than to re-implement the pin.

These tests drive the CALLERS, not the resolver. ``tests/test_r365_cf_access_host_pin.py``
already covers ``_resolve_cf_access_headers`` itself, and passing there while a
caller keeps building its own headers is precisely how this survived four
rounds. They are two-sided for the same reason R365's are: an over-tightened pin
is an outage (without ``CF-Access-*`` at the edge, production serves zero Claude
Max), so the attach half is as load-bearing as the leak half. No network I/O.
"""
from __future__ import annotations

import importlib

import pytest

CF_ID = "test-client-id.access"
CF_SECRET = "test-client-secret-value"

#: The real Access-protected tunnel. Production MUST keep getting the token.
WRAPPER = "https://wrapper.antifragile-ai.net/v1"

#: A host that must never see the secret. Naming it in ``OPENAI_API_BASE`` (or
#: ``R388_WRAPPER_URL``) is the exact configuration that leaked.
THIRD_PARTY = "https://openrouter.ai/api/v1"

#: Loopback has no Cloudflare edge in front of it, so the token is pointless
#: there — and it must not start erroring either.
LOCAL = "http://127.0.0.1:8000/v1"

#: An operator's own renamed tunnel, armed by an explicit declaration.
PINNED_TUNNEL = "https://tunnel2.antifragile-ai.net/v1"

CF_HEADER_KEYS = ("CF-Access-Client-Id", "CF-Access-Client-Secret")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every knob that can move the pin, cleared. ``CF_ACCESS_HOSTNAME`` in
    particular: a developer's own pin would otherwise decide what this file
    asserts. ``REGENOLD_SKIP_DOTENV`` so a local ``.env`` (which carries the REAL
    service token) cannot arm or disarm any of it."""
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    for var in (
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "CF_ACCESS_HOSTNAME",
        "OPENAI_API_BASE",
        "R388_WRAPPER_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def _arm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", CF_ID)
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", CF_SECRET)


def _cf_keys(headers: dict[str, str]) -> list[str]:
    """Any header that names Cloudflare, under any capitalisation."""
    return sorted(k for k in headers if "cf-access" in k.lower())


def _reload_build_gold():
    """``build_gold`` builds ``_HDRS`` at import time, so re-import it."""
    import evals.official.build_gold as build_gold

    return importlib.reload(build_gold)


# ══════════════════════════════════════════════════════════════════════════
# frontier_baseline — the caller that had no host test at all.
# ══════════════════════════════════════════════════════════════════════════
def _frontier_headers(base: str) -> dict[str, str]:
    import evals.harness.frontier_baseline as frontier

    return frontier._headers_for(base)


def test_frontier_baseline_does_not_ship_the_token_to_a_third_party(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The leak case. On the pre-R463 code this dict carried both CF headers."""
    _arm(monkeypatch)

    headers = _frontier_headers(THIRD_PARTY)

    assert "CF-Access-Client-Secret" not in headers, (
        "frontier_baseline attached the Zero Trust service token to "
        f"{THIRD_PARTY} — the base is env-derived, so this is credential "
        "exfiltration, not a misconfiguration"
    )
    assert _cf_keys(headers) == []
    # ...and the request is still a real request: a fix that dropped the whole
    # header set would pass the assertion above for the wrong reason.
    assert headers["Authorization"] == "Bearer dummy"
    assert headers["Content-Type"] == "application/json"


def test_frontier_baseline_still_arms_the_real_wrapper_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The inverse. Without the token at the edge, every Stage-2 call falls back."""
    _arm(monkeypatch)

    headers = _frontier_headers(WRAPPER)

    assert headers["CF-Access-Client-Id"] == CF_ID
    assert headers["CF-Access-Client-Secret"] == CF_SECRET


def test_frontier_baseline_leaves_loopback_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behaviour-equivalent on the pre-R463 inputs: loopback got nothing before."""
    _arm(monkeypatch)

    assert _cf_keys(_frontier_headers(LOCAL)) == []


def test_frontier_baseline_pin_is_case_folded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shouted host is the same host: the pin must not become an outage."""
    _arm(monkeypatch)

    headers = _frontier_headers("https://WRAPPER.ANTIFRAGILE-AI.NET/v1")

    assert headers["CF-Access-Client-Id"] == CF_ID


def test_frontier_baseline_honours_an_explicit_operator_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented remedy for a renamed tunnel: declare it, do not widen the
    base. ``CF_ACCESS_HOSTNAME`` arms that host and only that host."""
    _arm(monkeypatch)
    monkeypatch.setenv("CF_ACCESS_HOSTNAME", "tunnel2.antifragile-ai.net")

    assert _frontier_headers(PINNED_TUNNEL)["CF-Access-Client-Secret"] == CF_SECRET
    assert _cf_keys(_frontier_headers(WRAPPER)) == []


# ══════════════════════════════════════════════════════════════════════════
# build_gold — the caller whose guard was a substring test on the URL.
# ══════════════════════════════════════════════════════════════════════════
def test_build_gold_does_not_ship_the_token_to_a_third_party_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _arm(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE", THIRD_PARTY)
    try:
        headers = _reload_build_gold()._HDRS
        assert "CF-Access-Client-Secret" not in headers, (
            "build_gold attached the Zero Trust service token to a "
            "third-party ``OPENAI_API_BASE`` — `\"127.0.0.1\" not in URL` is a "
            "substring test, not a host pin"
        )
        assert _cf_keys(headers) == []
        assert headers["Authorization"] == "Bearer dummy"
    finally:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
        _reload_build_gold()  # leave the module as the suite found it


def test_build_gold_does_not_ship_the_token_to_a_third_party_wrapper_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``R388_WRAPPER_URL`` is the second env var that reached the same attach."""
    _arm(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
    monkeypatch.setenv("R388_WRAPPER_URL", f"{THIRD_PARTY}/chat/completions")
    try:
        headers = _reload_build_gold()._HDRS
        assert _cf_keys(headers) == []
    finally:
        monkeypatch.delenv("R388_WRAPPER_URL", raising=False)
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
        _reload_build_gold()


def test_build_gold_still_arms_the_real_wrapper_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The attach half, plus the browser UA the tunnel's Cloudflare 1010 needs:
    a pin that also stripped the UA would trade a leak for a 403."""
    _arm(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE", WRAPPER)
    try:
        headers = _reload_build_gold()._HDRS
        assert headers["CF-Access-Client-Id"] == CF_ID
        assert headers["CF-Access-Client-Secret"] == CF_SECRET
        assert headers["User-Agent"].startswith("Mozilla/5.0")
    finally:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
        _reload_build_gold()


def test_build_gold_leaves_loopback_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    _arm(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE", LOCAL)
    try:
        assert _cf_keys(_reload_build_gold()._HDRS) == []
    finally:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
        _reload_build_gold()


def test_both_callers_resolve_through_the_same_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam itself: neither module keeps a private copy of the rule."""
    import evals.harness.frontier_baseline as frontier
    import evals.official.build_gold as build_gold

    _arm(monkeypatch)

    assert frontier._cf_access_headers(THIRD_PARTY) == {}
    assert build_gold._cf_access_headers(THIRD_PARTY) == {}
    assert set(frontier._cf_access_headers(WRAPPER)) == set(CF_HEADER_KEYS)
    assert set(build_gold._cf_access_headers(WRAPPER)) == set(CF_HEADER_KEYS)
