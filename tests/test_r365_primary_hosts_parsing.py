"""R365 — ``REGENOLD_STAGE2_PRIMARY_HOSTS`` must accept the value an operator pastes.

R360.7 pinned the Stage-2 *destination*, not just the provider id, and gave the
operator ``REGENOLD_STAGE2_PRIMARY_HOSTS`` so they could rename their tunnel.
The candidate side of that comparison is normalised by ``_host_of``
(``urlsplit(...).hostname``); the configured side was only ``split(",")`` +
``strip().lower()``. The two sides therefore spoke different languages, and the
single most likely thing an operator pastes — **the URL they already have** —
matched nothing. Measured on this repo before the fix::

    hosts="https://wrapper.antifragile-ai.net/v1"  -> is_primary_base_url_allowed(...) = False
    hosts="wrapper.antifragile-ai.net:443"         -> False
    hosts=" Wrapper.Antifragile-AI.net "           -> True

Only the third shape worked. The first two silently refuse **100%** of primary
requests, and ``_graph_rag_impl`` answers a refusal by falling straight to leg 2
— so the whole service degrades to Bedrock/Qwen, which ``CLAUDE.md`` records at
**−0.27 answer correctness / −0.22 citation faithfulness** against the tunnel.
A quality cliff armed by a plausible env value and no error the operator sees.

Two-sidedness, in the R360 idiom: a fix that normalises everything into "allow"
is worse than the bug it replaces, because R360.7's whole point was that
``OPENAI_API_BASE=https://openrouter.ai/api/v1`` must not serve Stage-2. So the
refusal half is pinned as hard as the acceptance half, and it is pinned on the
``transport_stats()`` **counters** — the R329 rule — not on the shape of the
parser.
"""
from __future__ import annotations

import pytest

from app.llm import stage2_policy as pol

#: What the operator is trying to allow: the live cloudflared tunnel.
TUNNEL = "https://wrapper.antifragile-ai.net/v1"
#: The destination R360.7 exists to keep Stage-2 away from.
FOREIGN = "https://openrouter.ai/api/v1"


@pytest.fixture(autouse=True)
def _clean_counters():
    pol.reset_transport_stats()
    yield
    pol.reset_transport_stats()


@pytest.fixture(autouse=True)
def _strict_on(monkeypatch: pytest.MonkeyPatch):
    """Every test here is about the STRICT regime. Pin it rather than inherit
    it, so a stray ``REGENOLD_STAGE2_STRICT_TRANSPORT=0`` in a developer's
    environment cannot turn this whole module into a no-op that passes."""
    monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "1")


# ── the acceptance half ──────────────────────────────────────────────────────

#: Every shape an operator plausibly pastes for the one tunnel host. Each of
#: these names exactly one destination — ``wrapper.antifragile-ai.net`` — so
#: each must admit the tunnel and nothing else.
OPERATOR_PLAUSIBLE = [
    pytest.param("wrapper.antifragile-ai.net", id="bare-host"),
    pytest.param("https://wrapper.antifragile-ai.net", id="scheme"),
    pytest.param("https://wrapper.antifragile-ai.net/v1", id="scheme+path"),
    pytest.param("http://wrapper.antifragile-ai.net/v1/", id="scheme+path+slash"),
    pytest.param("wrapper.antifragile-ai.net:443", id="host+port"),
    pytest.param("https://wrapper.antifragile-ai.net:443/v1", id="scheme+port+path"),
    pytest.param("wrapper.antifragile-ai.net/v1", id="host+path-no-scheme"),
    pytest.param("Wrapper.Antifragile-AI.NET", id="mixed-case"),
    pytest.param("  https://Wrapper.Antifragile-AI.net/v1  ", id="whitespace+case+url"),
]


@pytest.mark.parametrize("configured", OPERATOR_PLAUSIBLE)
def test_every_shape_of_the_tunnel_host_is_accepted(
    configured: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", configured)
    assert pol.allowed_primary_hosts() == ("wrapper.antifragile-ai.net",), (
        f"{configured!r} must reduce to the bare host the candidate URL is "
        f"normalised to; got {pol.allowed_primary_hosts()!r}"
    )
    assert pol.is_primary_base_url_allowed(TUNNEL) is True


@pytest.mark.parametrize("configured", OPERATOR_PLAUSIBLE)
def test_accepting_the_tunnel_never_widens_to_a_foreign_host(
    configured: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal half, per shape. Normalisation must move exactly one host
    into the allowlist — never relax the comparison itself."""
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", configured)
    assert pol.is_primary_base_url_allowed(FOREIGN) is False
    # And the sibling-lookalike R360.7 already pins for the default list.
    assert (
        pol.is_primary_base_url_allowed("https://evil-wrapper.antifragile-ai.net/v1")
        is False
    )
    assert (
        pol.is_primary_base_url_allowed(
            "https://wrapper.antifragile-ai.net.attacker.test/v1"
        )
        is False
    )


def test_several_comma_separated_entries_of_mixed_shape(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """The realistic operator value: a renamed tunnel pasted as a URL, next to
    the local wrapper pasted as host:port, next to a bare hostname."""
    monkeypatch.setenv(
        "REGENOLD_STAGE2_PRIMARY_HOSTS",
        "https://tunnel.example.test/v1, 127.0.0.1:8000 ,LocalHost",
    )
    assert pol.allowed_primary_hosts() == (
        "tunnel.example.test",
        "127.0.0.1",
        "localhost",
    )
    for base in (
        "https://tunnel.example.test/v1",
        "http://127.0.0.1:8000/v1",
        "http://localhost:8000/v1",
    ):
        assert pol.is_primary_base_url_allowed(base) is True
    # The renamed tunnel replaces the default — the old one is no longer allowed.
    assert pol.is_primary_base_url_allowed(TUNNEL) is False
    assert pol.is_primary_base_url_allowed(FOREIGN) is False


def test_a_bare_ipv6_literal_survives_the_parser(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """``::1`` is in the shipped default list, so the env parser has to read it
    too. ``urlsplit`` only yields a hostname for a **bracketed** IPv6 literal;
    unbracketed it swallows the tail as a port and returns ``None``, which
    would drop the entry on the floor."""
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "::1, [::1]:8000")
    assert pol.allowed_primary_hosts() == ("::1", "::1")
    assert pol.is_primary_base_url_allowed("http://[::1]:8000/v1") is True
    assert pol.is_primary_base_url_allowed(FOREIGN) is False


# ── the "today's behaviour is preserved" half ────────────────────────────────


def test_unset_keeps_the_shipped_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_STAGE2_PRIMARY_HOSTS", raising=False)
    assert pol.allowed_primary_hosts() == pol.STAGE2_PRIMARY_HOSTS
    for base in (
        TUNNEL,
        "http://127.0.0.1:8000/v1",
        "http://localhost:8000/v1",
        "http://127.0.0.1:1/v1",  # the deterministic-bench dead port
        "http://[::1]:8000/v1",
    ):
        assert pol.is_primary_base_url_allowed(base) is True
    assert pol.is_primary_base_url_allowed(FOREIGN) is False


@pytest.mark.parametrize("blank", ["", "   ", ",,,", " , , "])
def test_a_blank_value_still_falls_back_rather_than_disabling_the_guard(
    blank: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R360.7's rule, unchanged: the allowlist cannot be emptied by accident.
    Turning the guard off must be a deliberate ``strict=0``."""
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", blank)
    assert pol.allowed_primary_hosts() == pol.STAGE2_PRIMARY_HOSTS
    assert pol.is_primary_base_url_allowed(FOREIGN) is False


def test_an_unparseable_entry_does_not_empty_the_allowlist(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A value that normalises to nothing at all must land in the same place a
    blank one does — the defaults — not in an empty tuple that refuses the
    tunnel itself."""
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "https:///v1")
    assert pol.allowed_primary_hosts() == pol.STAGE2_PRIMARY_HOSTS
    assert pol.is_primary_base_url_allowed(TUNNEL) is True
    assert pol.is_primary_base_url_allowed(FOREIGN) is False


def test_the_legacy_regime_is_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """``strict=0`` restores pre-R360 behaviour byte-for-byte: no destination
    check at all, whatever the allowlist says."""
    monkeypatch.setenv("REGENOLD_STAGE2_STRICT_TRANSPORT", "0")
    monkeypatch.setenv("REGENOLD_STAGE2_PRIMARY_HOSTS", "https://tunnel.example.test/v1")
    assert pol.is_primary_base_url_allowed(FOREIGN) is True


# ── proof on the RUNTIME COUNTERS, not on the shape of the parser ────────────


def test_the_guard_counts_a_refusal_for_a_foreign_host_and_none_for_the_tunnel(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """R329's rule applied to a parser: assert the guard *fires*, and that it
    *does not* fire on the traffic it is meant to pass. A parser fix that
    reads correctly in the diff and refuses everything anyway looks identical
    to one that works, right up until production serves Qwen for a week."""
    monkeypatch.setenv(
        "REGENOLD_STAGE2_PRIMARY_HOSTS", "https://wrapper.antifragile-ai.net/v1"
    )

    assert pol.check_primary_base_url(TUNNEL) is True
    stats = pol.transport_stats()
    assert stats["refused"] == 0, (
        "the operator-plausible value refused the very host it names — this is "
        "the 100%-degrade-to-Bedrock defect, and it is silent"
    )
    assert stats["refused_by_provider"] == {}

    assert pol.check_primary_base_url(FOREIGN) is False
    stats = pol.transport_stats()
    assert stats["refused"] == 1
    assert stats["refused_by_provider"] == {"base_url:openrouter.ai": 1}


def test_the_pasted_url_shape_does_not_silently_route_everything_to_bedrock(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect end to end: N primary calls with a pasted-URL allowlist must
    produce N passes and ZERO refusals. Pre-fix this read 0 / N."""
    monkeypatch.setenv(
        "REGENOLD_STAGE2_PRIMARY_HOSTS", "https://wrapper.antifragile-ai.net/v1"
    )
    passes = sum(1 for _ in range(5) if pol.check_primary_base_url(TUNNEL))
    assert passes == 5
    assert pol.transport_stats()["refused"] == 0
