"""R323 — the graph health probe could never report unhealthy, and the
default query budget was below the measured cold round-trip.

BLIND SPOT (found R290, still live at R322). ``GraphClient.execute_read``
catches ``Exception`` on every path and returns ``[]`` so the engine can fall
back to the in-memory KB. That contract is correct for the request path, but it
means ``health_check``'s ``except Exception`` is UNREACHABLE via that call —
so a completely dead instance returned::

    {"status": "healthy", "ping": None}

and ``/healthz/graph`` rendered ``graph_ok: true`` against it. That is exactly
what was observed during the Aura outage: a green probe alongside empty node
counts and an empty seed_version.

``RETURN 1 AS ping`` returns exactly one row on any reachable instance, so an
empty result is the only available — and a sufficient — failure signal.

BUDGET. ``DEFAULT_GRAPH_TIMEOUT_MS`` was 500, but the FIRST query of a
connection lifetime costs 524-593 ms against hosted Aura (TLS handshake +
routing table + plan compile). So the cold call always timed out and its work
was discarded. Warm calls measured 29-32 ms — ~16x under the old budget — so
raising to 750 cannot affect a warm request.
"""

from __future__ import annotations

import pytest

from app.graph.client import GraphClient
from app.graph.timeouts import (
    DEFAULT_GRAPH_TIMEOUT_MS,
    MAX_GRAPH_TIMEOUT_MS,
    MIN_GRAPH_TIMEOUT_MS,
    resolve_graph_timeout_ms,
)


class _Client(GraphClient):
    """A GraphClient whose execute_read is stubbed, leaving health_check real.

    Subclassing rather than hand-building an instance: an earlier probe set
    ``_settings = None`` and made ``execute_read`` raise on ``max_retries``,
    which exercised a path that does not occur in production and proved
    nothing. Overriding only ``execute_read`` keeps everything else genuine.
    """

    def __init__(self, rows: list[dict] | None) -> None:  # noqa: D107
        self._rows = rows

    @property
    def enabled(self) -> bool:  # type: ignore[override]
        return True

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:  # type: ignore[override]
        return list(self._rows or [])


# ── the blind spot ──────────────────────────────────────────────────────────


def test_empty_ping_is_reported_unhealthy() -> None:
    """The regression: execute_read swallows the error and returns []."""
    out = _Client([]).health_check()
    assert out["status"] == "unhealthy", (
        f"a dead instance must not report healthy; got {out}"
    )
    assert "no rows" in out.get("error", "").lower()


def test_healthy_ping_is_reported_healthy() -> None:
    out = _Client([{"ping": 1}]).health_check()
    assert out["status"] == "healthy"
    assert out["ping"] == 1


def test_health_check_never_raises_on_a_malformed_row() -> None:
    """A row without the expected key must degrade, not explode."""
    out = _Client([{"unexpected": 1}]).health_check()
    assert out["status"] == "healthy"
    assert out["ping"] is None


def test_disabled_client_is_reported_disabled_not_unhealthy() -> None:
    """A graph that is switched OFF is not a graph that is BROKEN.

    Conflating them would page an operator for a deliberate configuration.
    """

    class _Off(_Client):
        @property
        def enabled(self) -> bool:  # type: ignore[override]
            return False

    assert _Off([]).health_check()["status"] == "disabled"


# ── the budget ──────────────────────────────────────────────────────────────


def test_default_budget_exceeds_the_measured_cold_round_trip() -> None:
    """Cold calls measured 524-593 ms against the live instance."""
    assert DEFAULT_GRAPH_TIMEOUT_MS >= 650, (
        f"budget {DEFAULT_GRAPH_TIMEOUT_MS} ms is below the measured cold "
        "round-trip, so the first graph call of a connection always times out"
    )


def test_default_budget_stays_modest_because_latency_is_scored() -> None:
    assert DEFAULT_GRAPH_TIMEOUT_MS <= 1000, (
        "latency is a scored axis; the budget is headroom for the cold call, "
        "not licence to park a request on a hung socket"
    )


@pytest.mark.parametrize(
    "explicit, expected",
    [
        (None, DEFAULT_GRAPH_TIMEOUT_MS),
        (0, MIN_GRAPH_TIMEOUT_MS),
        (-1, MIN_GRAPH_TIMEOUT_MS),
        (999_999, MAX_GRAPH_TIMEOUT_MS),
        (300, 300),
    ],
)
def test_explicit_budget_wins_and_is_clamped(explicit: int | None, expected: int) -> None:
    assert resolve_graph_timeout_ms(explicit) == expected


def test_env_override_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_TIMEOUT_MS", "1200")
    assert resolve_graph_timeout_ms() == 1200
