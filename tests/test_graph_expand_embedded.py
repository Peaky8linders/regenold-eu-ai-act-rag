"""R121 — embedded (in-process) 2-hop graph expansion is the default backend.

The 2-hop traversal no longer depends on a reachable / seeded Neo4j instance:
``REGENOLD_GRAPH_2HOP_BACKEND`` defaults to ``"embedded"``, which walks the
in-process ``kb_xrefs._build_xref_graph`` adjacency map (the FULL R47 graph,
the same data the Neo4j seed is built from). ``"neo4j"`` re-enables the Cypher
path (retained, not deleted).

Bench neutrality is preserved by construction: the 2-hop still only fires when
``REGENOLD_GRAPH_2HOP="1"`` (which the davidath bench never sets), so the
default-OFF behaviour is unchanged regardless of backend.
"""

from __future__ import annotations

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE
from app.engines import graph_expand_2hop as g2


# ── Backend selector ─────────────────────────────────────────────────────────


def test_backend_defaults_to_embedded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_GRAPH_2HOP_BACKEND", raising=False)
    assert g2._backend() == "embedded"


def test_backend_neo4j_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "neo4j")
    assert g2._backend() == "neo4j"
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "  NEO4J  ")
    assert g2._backend() == "neo4j"


def test_backend_unrecognised_falls_back_to_embedded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "duckdb")
    assert g2._backend() == "embedded"


# ── Enablement (bench neutrality) ────────────────────────────────────────────


def test_disabled_when_2hop_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """The davidath bench never sets REGENOLD_GRAPH_2HOP → 2-hop stays off."""
    monkeypatch.delenv("REGENOLD_GRAPH_2HOP", raising=False)
    monkeypatch.delenv("REGENOLD_GRAPH_2HOP_BACKEND", raising=False)
    assert g2.is_enabled() is False
    # And expand is a no-op echo on the disabled path.
    exp = g2.expand_2hop(["Art. 6"])
    assert exp.hop1_articles == () and exp.hop2_articles == ()


def test_embedded_enabled_needs_no_neo4j_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedded backend + env on → enabled WITHOUT any Neo4j client."""
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "embedded")
    # No NEO4J_URI / no driver — embedded must still report enabled.
    monkeypatch.delenv("NEO4J_URI", raising=False)
    assert g2.is_enabled() is True


# ── Embedded traversal ───────────────────────────────────────────────────────


def test_embedded_expand_structural_invariants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "embedded")
    exp = g2.expand_2hop(["Art. 6"], max_hop2=5)

    seeds = {"Art. 6"}
    hop1 = set(exp.hop1_articles)
    hop2 = set(exp.hop2_articles)

    # Art. 6 is a hub (R47/R59 edges) → at least one direct neighbour.
    assert hop1, "Art. 6 should have ≥1 xref neighbour in the full graph"
    # Disjointness: seeds ∉ hop1 ∉ hop2.
    assert not (hop1 & seeds)
    assert not (hop2 & seeds)
    assert not (hop1 & hop2)
    # Existence gate — no ref escapes the canonical catalog.
    for ref in hop1 | hop2:
        assert ref in ARTICLE_EXISTENCE, f"{ref} not in ARTICLE_EXISTENCE"
    # hop2 capped.
    assert len(exp.hop2_articles) <= 5
    # R59 pinned the Art. 6 → Art. 9 Section-2 gateway edge.
    assert "Art. 9" in (hop1 | hop2)


def test_embedded_expand_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "embedded")
    a = g2.expand_2hop(["Art. 6", "Art. 26"], max_hop2=5)
    b = g2.expand_2hop(["Art. 6", "Art. 26"], max_hop2=5)
    assert a.hop1_articles == b.hop1_articles
    assert a.hop2_articles == b.hop2_articles


def test_embedded_accepts_user_facing_and_annex_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "embedded")
    # User-facing "Article 6" must normalise to the graph key "Art. 6".
    exp = g2.expand_2hop(["Article 6"], max_hop2=5)
    assert exp.hop1_articles, "user-facing seed should resolve to graph key"


def test_embedded_fail_soft_on_garbage_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "embedded")
    exp = g2.expand_2hop(["definitely not a ref"], max_hop2=5)
    assert exp.hop1_articles == () and exp.hop2_articles == ()


def test_embedded_fuses_additively_below_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
    monkeypatch.setenv("REGENOLD_GRAPH_2HOP_BACKEND", "embedded")
    winners = ["Art. 6", "Art. 13"]
    exp = g2.expand_2hop(winners, max_hop2=5)
    fused = g2.fuse_with_kb_xrefs(winners, exp, budget=10)
    # BM25 winners survive verbatim at the head.
    assert fused[: len(winners)] == winners
    # Never exceeds budget; only hop2-only refs appended.
    assert len(fused) <= 10
