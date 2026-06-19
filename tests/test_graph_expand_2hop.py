"""Tests for ``app.engines.graph_expand_2hop`` — Neo4j 2-hop expansion.

Covers env-gating, mocked Cypher returns (hop1/hop2 split), exception
swallowing, existence-validation, additive fusion + budget caps. The
real Neo4j driver is never invoked — every test mocks
``app.graph.client.get_graph_client``.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from app.engines import graph_expand_2hop as g2
from app.engines.graph_expand_2hop import (
    GraphExpansion,
    expand_2hop,
    fuse_with_kb_xrefs,
    is_enabled,
)


# ── Fake client ────────────────────────────────────────────────────────────


class _FakeClient:
    """Stand-in for ``GraphClient``. Records ``execute_read`` calls."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        return_value: list[dict] | None = None,
        raise_exc: BaseException | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.enabled = enabled
        self._return_value = return_value or []
        self._raise_exc = raise_exc
        self._delay_seconds = delay_seconds
        self.calls: list[tuple[str, dict]] = []

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        self.calls.append((query, dict(parameters or {})))
        if self._delay_seconds:
            import time
            time.sleep(self._delay_seconds)
        if self._raise_exc is not None:
            raise self._raise_exc
        return list(self._return_value)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Default to env-var unset for every test (explicit set inside)."""
    monkeypatch.delenv("REGENOLD_GRAPH_2HOP", raising=False)
    yield


def _install_fake(monkeypatch, client: _FakeClient) -> None:
    """Patch ``get_graph_client`` at the import site used by g2."""
    # graph_expand_2hop does a *deferred* import inside is_enabled / _resolve_client,
    # so we patch the source module — not g2.get_graph_client (which doesn't
    # exist on the module namespace).
    import app.graph.client as gc

    monkeypatch.setattr(gc, "get_graph_client", lambda: client)


# ── is_enabled() ──────────────────────────────────────────────────────────


def test_is_enabled_false_when_env_unset(monkeypatch):
    """No env-var → disabled even with a healthy client."""
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is False


def test_is_enabled_false_when_env_zero(monkeypatch):
    """Env-var ``"0"`` → disabled (strict ``"1"`` match)."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "0")
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is False


def test_is_enabled_false_when_client_disabled(monkeypatch):
    """Env-var set but ``client.enabled=False`` → disabled."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    _install_fake(monkeypatch, _FakeClient(enabled=False))
    assert is_enabled() is False


def test_is_enabled_true_when_both_conditions_met(monkeypatch):
    """Env-var ``"1"`` AND ``client.enabled=True`` → enabled."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    _install_fake(monkeypatch, _FakeClient(enabled=True))
    assert is_enabled() is True


def test_is_enabled_false_when_client_factory_raises(monkeypatch):
    """``get_graph_client`` raises → treated as disabled."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    import app.graph.client as gc

    def _boom():
        raise RuntimeError("driver init failed")

    monkeypatch.setattr(gc, "get_graph_client", _boom)
    assert is_enabled() is False


# ── expand_2hop() — env-gate / passthrough ───────────────────────────────


def test_expand_2hop_returns_empty_passthrough_when_disabled(monkeypatch):
    """Env-var unset → seed echo, no Cypher call."""
    client = _FakeClient(enabled=True, return_value=[{"num": "9", "hops": 1}])
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert isinstance(result, GraphExpansion)
    assert result.seed_articles == ("Art. 6",)
    assert result.hop1_articles == ()
    assert result.hop2_articles == ()
    # Most importantly: no Cypher call was issued.
    assert client.calls == []


def test_expand_2hop_returns_empty_passthrough_when_client_disabled(monkeypatch):
    """Env on but client.enabled=False → no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=False, return_value=[{"num": "9", "hops": 1}])
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert result.hop2_articles == ()
    assert client.calls == []


def test_expand_2hop_empty_seeds_returns_empty(monkeypatch):
    """No seeds → no work."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True)
    _install_fake(monkeypatch, client)
    result = expand_2hop([])
    assert result == GraphExpansion()
    assert client.calls == []


def test_expand_2hop_zero_max_hop2_passthrough(monkeypatch):
    """max_hop2=0 → seed echo, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True, return_value=[{"num": "9", "hops": 1}])
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"], max_hop2=0)
    assert result.seed_articles == ("Art. 6",)
    assert result.hop2_articles == ()
    assert client.calls == []


# ── expand_2hop() — happy path ────────────────────────────────────────────


def test_expand_2hop_splits_hop1_and_hop2_correctly(monkeypatch):
    """Rows with hops=1 → hop1; rows with hops=2 → hop2."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"num": "9", "hops": 1},     # 1-hop
            {"num": "61", "hops": 2},    # 2-hop only
            {"num": "11", "hops": 1},    # 1-hop
            {"num": "72", "hops": 2},    # 2-hop only
        ],
    )
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert result.seed_articles == ("Art. 6",)
    assert "Art. 9" in result.hop1_articles
    assert "Art. 11" in result.hop1_articles
    assert "Art. 61" in result.hop2_articles
    assert "Art. 72" in result.hop2_articles
    # Hop2 must NOT contain hop1 refs.
    assert "Art. 9" not in result.hop2_articles
    assert "Art. 11" not in result.hop2_articles


def test_expand_2hop_normalises_user_facing_seed(monkeypatch):
    """``Article 6`` seed → Cypher ``$seed_nums = ["6"]``."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    expand_2hop(["Article 6", "Annex III"])
    assert len(client.calls) == 1
    _, params = client.calls[0]
    assert params["seed_nums"] == ["6", "III"]


def test_expand_2hop_strips_subpoints(monkeypatch):
    """``Art. 13.2`` → ``"13"`` (xref graph collapses sub-points)."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    expand_2hop(["Art. 13.2"])
    _, params = client.calls[0]
    assert params["seed_nums"] == ["13"]


def test_expand_2hop_cap_full_vs_legacy(monkeypatch):
    """F1 fix: the LIMIT cap is the catalog ceiling by default (so hop1 can't
    crowd out hop2 for hub seeds); ``REGENOLD_GRAPH_2HOP_FULL_CAP=0`` restores
    the legacy ``max_hop2 * 2`` cap."""
    from app.data.article_existence import ARTICLE_EXISTENCE

    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")

    # Legacy cap under the rollback flag.
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "0")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    expand_2hop(["Art. 6"], max_hop2=5)
    _, params = client.calls[0]
    assert params["cap"] == 10

    # Default (fix ON) → catalog ceiling, never truncates before hop2.
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_FULL_CAP", "1")
    client = _FakeClient(enabled=True, return_value=[])
    _install_fake(monkeypatch, client)
    expand_2hop(["Art. 6"], max_hop2=5)
    _, params = client.calls[0]
    assert params["cap"] == len(ARTICLE_EXISTENCE)


def test_expand_2hop_caps_hop2_at_max_hop2(monkeypatch):
    """Even if Neo4j returns 100 hop2 rows, output is capped."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    rows = [{"num": str(n), "hops": 2} for n in range(20, 40)]  # 20 hop2 rows
    client = _FakeClient(enabled=True, return_value=rows)
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"], max_hop2=3)
    assert len(result.hop2_articles) == 3


def test_expand_2hop_returns_annex_form_for_roman_numerals(monkeypatch):
    """``num="III"`` → ``"Annex III"``."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[{"num": "III", "hops": 2}],
    )
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert "Annex III" in result.hop2_articles


# ── expand_2hop() — failure modes ─────────────────────────────────────────


def test_expand_2hop_returns_empty_on_client_exception(monkeypatch):
    """Any exception from ``execute_read`` → empty expansion, no raise."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True, raise_exc=RuntimeError("oh no"))
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    # Must not raise + must echo seeds + must have empty hops.
    assert result.seed_articles == ("Art. 6",)
    assert result.hop1_articles == ()
    assert result.hop2_articles == ()


def test_expand_2hop_drops_invalid_article_numbers(monkeypatch):
    """Refs not in ARTICLE_EXISTENCE are dropped from output."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"num": "200", "hops": 2},  # No such article — must drop
            {"num": "9", "hops": 2},    # Valid — must surface
            {"num": "XX", "hops": 2},   # Not in ARTICLE_EXISTENCE (no Annex XX) — drop
        ],
    )
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert "Art. 200" not in result.hop2_articles
    assert "Annex XX" not in result.hop2_articles
    assert "Art. 9" in result.hop2_articles


def test_expand_2hop_drops_malformed_rows(monkeypatch):
    """Rows missing ``num`` / ``hops`` / non-dict shapes are skipped."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"hops": 2},  # missing num
            {"num": "9"},  # missing hops
            {"num": "11", "hops": "not-an-int"},  # malformed hops
            {"num": "13", "hops": 2},  # well-formed → must survive
            "not-a-dict",  # malformed row entirely
        ],
    )
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert "Art. 13" in result.hop2_articles
    # The malformed entries don't show up.
    assert "Art. 11" not in result.hop2_articles


def test_expand_2hop_deduplicates_hop2(monkeypatch):
    """Duplicate ``num`` rows surface once."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(
        enabled=True,
        return_value=[
            {"num": "9", "hops": 2},
            {"num": "9", "hops": 2},  # dupe
        ],
    )
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert result.hop2_articles.count("Art. 9") == 1


def test_expand_2hop_unparseable_seeds_passthrough(monkeypatch):
    """No parseable seed numbers → empty expansion, no Cypher call."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True, return_value=[{"num": "9", "hops": 2}])
    _install_fake(monkeypatch, client)
    result = expand_2hop(["TotallyMadeUp", "Nothing"])
    assert result.hop2_articles == ()
    assert client.calls == []


def test_expand_2hop_timeout_collapses_to_empty(monkeypatch):
    """A Cypher call that exceeds timeout_ms → empty hop2."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    # 200 ms delay vs 10 ms timeout → must time out.
    client = _FakeClient(
        enabled=True,
        return_value=[{"num": "9", "hops": 2}],
        delay_seconds=0.2,
    )
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"], timeout_ms=10)
    assert result.hop2_articles == ()
    # The seeds are still echoed (timeout != bug).
    assert result.seed_articles == ("Art. 6",)


def test_expand_2hop_records_elapsed_ms(monkeypatch):
    """Successful call populates ``elapsed_ms`` (non-negative)."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    client = _FakeClient(enabled=True, return_value=[{"num": "9", "hops": 2}])
    _install_fake(monkeypatch, client)
    result = expand_2hop(["Art. 6"])
    assert result.elapsed_ms >= 0


# ── fuse_with_kb_xrefs() ──────────────────────────────────────────────────


def test_fuse_preserves_bm25_winners_in_order():
    """BM25 winners always survive in their original ranking."""
    winners = ["Article 5", "Article 6", "Article 9"]
    expansion = GraphExpansion(
        seed_articles=("Art. 6",),
        hop1_articles=(),
        hop2_articles=("Art. 72",),
    )
    out = fuse_with_kb_xrefs(winners, expansion, budget=10)
    assert out[:3] == winners


def test_fuse_appends_hop2_only():
    """Hop2-only refs land at the tail."""
    winners = ["Article 6"]
    expansion = GraphExpansion(
        seed_articles=("Art. 6",),
        hop1_articles=("Art. 9",),
        hop2_articles=("Art. 72", "Art. 61"),
    )
    out = fuse_with_kb_xrefs(winners, expansion, budget=10)
    assert out == ["Article 6", "Art. 72", "Art. 61"]


def test_fuse_dedupes_hop2_against_winners():
    """A hop2 ref that's already in winners isn't double-appended."""
    winners = ["Art. 9", "Art. 11"]
    expansion = GraphExpansion(
        seed_articles=("Art. 6",),
        hop1_articles=(),
        hop2_articles=("Art. 9", "Art. 72"),  # Art. 9 dupe
    )
    out = fuse_with_kb_xrefs(winners, expansion, budget=10)
    assert out == ["Art. 9", "Art. 11", "Art. 72"]
    assert out.count("Art. 9") == 1


def test_fuse_respects_budget():
    """Output length never exceeds ``budget``."""
    winners = ["Art. 5", "Art. 6", "Art. 9"]
    expansion = GraphExpansion(
        seed_articles=("Art. 6",),
        hop1_articles=(),
        hop2_articles=("Art. 13", "Art. 14", "Art. 15", "Art. 16"),
    )
    out = fuse_with_kb_xrefs(winners, expansion, budget=5)
    assert len(out) == 5
    assert out[:3] == winners
    # Two hop2 refs were appended.
    assert out[3:] == ["Art. 13", "Art. 14"]


def test_fuse_budget_already_full_truncates_winners():
    """Budget ≤ len(winners) → no fusion, returns budget-sized prefix."""
    winners = ["Art. 5", "Art. 6", "Art. 9", "Art. 11"]
    expansion = GraphExpansion(
        seed_articles=("Art. 6",),
        hop2_articles=("Art. 13",),
    )
    out = fuse_with_kb_xrefs(winners, expansion, budget=2)
    assert out == ["Art. 5", "Art. 6"]


def test_fuse_empty_expansion_returns_winners_intact():
    """No hop2 candidates → BM25 list unchanged (modulo budget)."""
    winners = ["Art. 5", "Art. 6"]
    expansion = GraphExpansion()
    out = fuse_with_kb_xrefs(winners, expansion, budget=10)
    assert out == winners


def test_fuse_empty_winners_returns_hop2():
    """Empty BM25 list + hop2 candidates → hop2 only."""
    expansion = GraphExpansion(
        hop2_articles=("Art. 9", "Art. 72"),
    )
    out = fuse_with_kb_xrefs([], expansion, budget=10)
    assert out == ["Art. 9", "Art. 72"]


def test_fuse_does_not_mutate_input():
    """Pure function — caller's BM25 list is untouched."""
    winners = ["Art. 5", "Art. 6"]
    original = list(winners)
    expansion = GraphExpansion(hop2_articles=("Art. 72",))
    fuse_with_kb_xrefs(winners, expansion, budget=10)
    assert winners == original


# ── Module-level guarantees ───────────────────────────────────────────────


def test_module_import_is_lightweight():
    """Reimporting the module shouldn't trigger Neo4j or driver load."""
    # If importing the module ever calls get_graph_client at top-level,
    # this test will surface it (we patch the module to raise on call).
    import importlib

    import app.graph.client as gc

    # Replace with a guard that raises if invoked during import.
    sentinel = {"called": False}

    def _trap():
        sentinel["called"] = True
        raise AssertionError("get_graph_client called during module import")

    original = gc.get_graph_client
    gc.get_graph_client = _trap  # type: ignore[assignment]
    try:
        importlib.reload(g2)
    finally:
        gc.get_graph_client = original  # type: ignore[assignment]
    assert sentinel["called"] is False


def test_graph_expansion_is_frozen():
    """The dataclass is frozen — assignment should raise."""
    expansion = GraphExpansion(seed_articles=("Art. 6",))
    with pytest.raises(Exception):  # FrozenInstanceError subclasses AttributeError
        expansion.seed_articles = ("Art. 9",)  # type: ignore[misc]


def test_public_api_surface():
    """``__all__`` exports the documented symbols."""
    assert set(g2.__all__) == {
        "GraphExpansion",
        "is_enabled",
        "expand_2hop",
        "fuse_with_kb_xrefs",
    }
