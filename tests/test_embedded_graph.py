"""Embedded property-graph backend — Orbit-inspired, Neo4j-free 2-hop.

The embedded graph mirrors the in-process cross-reference graph
(:func:`app.data.kb_xrefs._build_xref_graph` / :func:`all_edges`) — the
SAME source :file:`scripts/seed_neo4j_kb.py` seeds ``CROSS_REFERENCES``
from — into a single-file SQLite property graph built at startup. It
serves the 2-hop traversal that :mod:`app.engines.graph_expand_2hop`
otherwise needs Neo4j Aura for, with zero external dependency, zero
seed step, no duplicate-node drift, and deterministic sub-ms queries.

These tests pin: (1) the graph build mirrors ``kb_xrefs``; (2) the
2-hop traversal returns the same ``{num, hops}`` row shape the Cypher
path returns; (3) the typed ``neighbors`` helper; (4) the
``REGENOLD_GRAPH_BACKEND`` selector; (5) the ``expand_2hop`` wiring
proves 2-hop works WITHOUT Neo4j when the embedded backend is selected.
"""
from __future__ import annotations

import pytest

from app.data import kb_xrefs
from app.data.article_existence import ARTICLE_EXISTENCE


@pytest.fixture(autouse=True)
def _reset_embedded_singleton():
    """Drop the cached embedded graph before+after each test."""
    from app.graph import embedded_graph

    embedded_graph._reset_embedded_graph_for_tests()
    yield
    embedded_graph._reset_embedded_graph_for_tests()


def _internal(num: str) -> str:
    """Bare token → internal ref form (Arabic→Art., Roman→Annex)."""
    return f"Art. {num}" if num.isdigit() else f"Annex {num}"


# ── Build ────────────────────────────────────────────────────────────────────


class TestEmbeddedGraphBuild:
    def test_enabled_after_build(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        assert EmbeddedGraph().enabled is True

    def test_node_count_matches_article_existence(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        # 113 articles + 13 annexes = 126 canonical nodes.
        assert EmbeddedGraph().node_count() == len(ARTICLE_EXISTENCE)

    def test_edge_endpoints_are_all_real_refs(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        g = EmbeddedGraph()
        # Every stored edge endpoint must resolve in ARTICLE_EXISTENCE —
        # a malformed xref can never pollute the graph.
        for src, dst in g.directed_edges():
            assert src in ARTICLE_EXISTENCE
            assert dst in ARTICLE_EXISTENCE

    def test_build_is_dependency_free(self) -> None:
        # Building must not require the neo4j driver or any network.
        import sys

        from app.graph.embedded_graph import EmbeddedGraph

        had_neo4j = "neo4j" in sys.modules
        EmbeddedGraph()
        # Building the embedded graph must not import neo4j on its own.
        if not had_neo4j:
            assert "neo4j" not in sys.modules


# ── 2-hop traversal (expander-facing, num-space, row-shaped) ─────────────────


class TestTwoHop:
    def test_rows_have_num_and_hops(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        rows = EmbeddedGraph().two_hop(["6"], cap=20)
        assert rows, "Art. 6 is a hub — must surface neighbours"
        for r in rows:
            assert set(r.keys()) == {"num", "hops"}
            assert r["hops"] in (1, 2)

    def test_excludes_seed(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        rows = EmbeddedGraph().two_hop(["6"], cap=100)
        assert all(r["num"] != "6" for r in rows)

    def test_respects_cap(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        rows = EmbeddedGraph().two_hop(["6"], cap=3)
        assert len(rows) <= 3

    def test_deterministic_order_by_hops_then_num(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        rows = EmbeddedGraph().two_hop(["6"], cap=100)
        keys = [(r["hops"], r["num"]) for r in rows]
        assert keys == sorted(keys)

    def test_unknown_seed_returns_empty(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        assert EmbeddedGraph().two_hop(["999"], cap=10) == []

    def test_neighbours_are_real_refs(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        rows = EmbeddedGraph().two_hop(["6"], cap=100)
        for r in rows:
            assert _internal(r["num"]) in ARTICLE_EXISTENCE

    def test_min_hops_wins(self) -> None:
        # A node reachable at both hop1 and hop2 is reported at hop1.
        from app.graph.embedded_graph import EmbeddedGraph

        g = EmbeddedGraph()
        rows = g.two_hop(["6"], cap=100)
        # Direct 1-hop targets of Art. 6 (that exist) must appear at hops=1.
        one_hop = {
            t.split(" ", 1)[1] if t.startswith("Annex ") else t.split(". ")[1]
            for t in kb_xrefs._build_xref_graph().get("Art. 6", ())
            if t in ARTICLE_EXISTENCE
        }
        reported_hop1 = {r["num"] for r in rows if r["hops"] == 1}
        assert one_hop & reported_hop1  # at least the direct targets land at hop1
        for r in rows:
            if r["num"] in one_hop:
                assert r["hops"] == 1

    def test_empty_seed_list_returns_empty(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        assert EmbeddedGraph().two_hop([], cap=10) == []


# ── Typed neighbours helper (human-facing, internal-ref space) ───────────────


class TestNeighbors:
    def test_one_hop_covers_kb_xref_targets(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        g = EmbeddedGraph()
        n = set(g.neighbors("Art. 6", hops=1))
        for target in kb_xrefs._build_xref_graph().get("Art. 6", ()):
            if target in ARTICLE_EXISTENCE:
                assert target in n

    def test_excludes_self(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        assert "Art. 6" not in EmbeddedGraph().neighbors("Art. 6", hops=2)

    def test_two_hop_superset_of_one_hop(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        g = EmbeddedGraph()
        assert set(g.neighbors("Art. 6", hops=1)) <= set(
            g.neighbors("Art. 6", hops=2)
        )

    def test_returns_internal_ref_form(self) -> None:
        from app.graph.embedded_graph import EmbeddedGraph

        for ref in EmbeddedGraph().neighbors("Art. 6", hops=1):
            assert ref.startswith("Art. ") or ref.startswith("Annex ")


# ── Backend selector ─────────────────────────────────────────────────────────


class TestBackendSelector:
    def test_embedded_is_default(self, monkeypatch) -> None:
        # R127 — embedded is now the default backend (Aura retired as
        # default). Deleting the env var exercises the CODE default.
        from app.graph.embedded_graph import (
            embedded_backend_selected,
            graph_backend,
            neo4j_backend_selected,
        )

        monkeypatch.delenv("REGENOLD_GRAPH_BACKEND", raising=False)
        assert graph_backend() == "embedded"
        assert embedded_backend_selected() is True
        assert neo4j_backend_selected() is False

    def test_selected_when_embedded(self, monkeypatch) -> None:
        from app.graph.embedded_graph import embedded_backend_selected

        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        assert embedded_backend_selected() is True

    def test_case_insensitive_and_whitespace(self, monkeypatch) -> None:
        from app.graph.embedded_graph import embedded_backend_selected

        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "  Embedded ")
        assert embedded_backend_selected() is True

    def test_neo4j_value_selects_neo4j_not_embedded(self, monkeypatch) -> None:
        # R127 — explicit ``neo4j`` opts back into Aura: embedded OFF,
        # neo4j ON (this is what gates the Neo4j driver activation).
        from app.graph.embedded_graph import (
            embedded_backend_selected,
            graph_backend,
            neo4j_backend_selected,
        )

        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "neo4j")
        assert graph_backend() == "neo4j"
        assert embedded_backend_selected() is False
        assert neo4j_backend_selected() is True

    def test_rushdb_value_selects_neither_embedded_nor_neo4j(self, monkeypatch) -> None:
        from app.graph.embedded_graph import (
            embedded_backend_selected,
            neo4j_backend_selected,
        )

        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "rushdb")
        assert embedded_backend_selected() is False
        assert neo4j_backend_selected() is False


class TestClientActivationGate:
    """R127 — the Neo4j driver activates only on explicit neo4j backend."""

    def test_client_disabled_when_embedded_even_with_uri(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        from app.graph.client import _should_activate

        # NEO4J_URI present (as a stale dashboard var would be) but the
        # embedded backend is active → the Neo4j client must NOT activate,
        # so no Aura retrieval / boot-seed network cost is paid.
        monkeypatch.setenv("NEO4J_URI", "bolt://stale-aura:7687")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        assert _should_activate(MagicMock()) is False

    def test_client_disabled_when_rushdb_even_with_uri(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        from app.graph.client import _should_activate

        monkeypatch.setenv("NEO4J_URI", "bolt://stale-aura:7687")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "rushdb")
        assert _should_activate(MagicMock()) is False

    def test_neo4j_backend_still_requires_uri(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        from app.graph.client import _should_activate

        # Explicit neo4j backend but no URI → still disabled (the historical
        # NEO4J_URI gate is preserved beneath the new backend gate).
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "neo4j")
        monkeypatch.delenv("NEO4J_URI", raising=False)
        assert _should_activate(MagicMock()) is False


# ── Singleton ────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_singleton_same_instance(self) -> None:
        from app.graph.embedded_graph import get_embedded_graph

        assert get_embedded_graph() is get_embedded_graph()

    def test_reset_drops_singleton(self) -> None:
        from app.graph import embedded_graph

        first = embedded_graph.get_embedded_graph()
        embedded_graph._reset_embedded_graph_for_tests()
        assert embedded_graph.get_embedded_graph() is not first


# ── Ontology single-source-of-truth ──────────────────────────────────────────


class TestOntology:
    def test_ontology_declares_node_and_edge_types(self) -> None:
        from app.graph.embedded_graph import ONTOLOGY

        assert "Article" in ONTOLOGY["node_labels"]
        assert "Annex" in ONTOLOGY["node_labels"]
        assert "CROSS_REFERENCES" in ONTOLOGY["edge_types"]

    def test_self_check_passes(self) -> None:
        # Import-time invariant — every edge endpoint resolves, schema
        # is internally consistent. Must not raise.
        from app.graph.embedded_graph import _self_check

        _self_check()


# ── expand_2hop wiring — 2-hop works with NO Neo4j ───────────────────────────


class TestExpand2hopEmbeddedWiring:
    def test_is_enabled_embedded_without_neo4j(self, monkeypatch) -> None:
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        monkeypatch.delenv("REGENOLD_CAP_EXPANSION", raising=False)
        from app.engines import graph_expand_2hop as g2

        assert g2.is_enabled() is True

    def test_expand_2hop_embedded_returns_hop2(self, monkeypatch) -> None:
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        monkeypatch.delenv("REGENOLD_CAP_EXPANSION", raising=False)
        from app.engines import graph_expand_2hop as g2

        # max_hop2=20 → cap=40. Art. 6 is a hub (~10 one-hop neighbours);
        # the cap (ordered hop1-then-hop2, identical to the Neo4j Cypher
        # ``ORDER BY hops, num LIMIT``) needs headroom past hop1 for the
        # 2-hop-only refs to surface. A small budget squeezes hop2 out on
        # a hub — a pre-existing property of the expand_2hop contract that
        # the embedded backend faithfully mirrors.
        exp = g2.expand_2hop(["Art. 6"], max_hop2=20)
        assert exp.seed_articles == ("Art. 6",)
        # Embedded query works with NO Neo4j — hop1 neighbours surfaced.
        assert exp.hop1_articles
        # The whole point: real 2-hop-only neighbours, no Neo4j.
        assert exp.hop2_articles
        for ref in exp.hop2_articles:
            assert ref in ARTICLE_EXISTENCE
            assert ref != "Art. 6"
            assert ref not in exp.hop1_articles  # hop2-only

    def test_default_backend_uses_embedded(self, monkeypatch) -> None:
        # R127 — backend unset → embedded is the CODE default → the 2-hop
        # uses the in-process graph (no Neo4j needed). With the env-gate on,
        # is_enabled() is True via the embedded graph, NOT the Neo4j client.
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.delenv("REGENOLD_GRAPH_BACKEND", raising=False)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        from app.engines import graph_expand_2hop as g2

        assert g2.is_enabled() is True

    def test_explicit_neo4j_without_uri_is_disabled(self, monkeypatch) -> None:
        # Explicit neo4j backend but no URI → the Neo4j client stays
        # disabled, and embedded is NOT selected, so is_enabled() is False.
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "neo4j")
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        from app.engines import graph_expand_2hop as g2

        assert g2.is_enabled() is False

    def test_embedded_expansion_fuses_additively(self, monkeypatch) -> None:
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        monkeypatch.delenv("REGENOLD_CAP_EXPANSION", raising=False)
        from app.engines import graph_expand_2hop as g2

        exp = g2.expand_2hop(["Art. 6"], max_hop2=5)
        winners = ["Art. 6", "Art. 99"]
        fused = g2.fuse_with_kb_xrefs(winners, exp, budget=10)
        # BM25 winners always survive, in order, at the head.
        assert fused[: len(winners)] == winners
        assert len(fused) <= 10
