"""R129 deep-code-review regression tests — embedded graph go-live.

The R121 embedded in-process SQLite property graph became the live 2-hop
backend in R129 (code default `embedded`) and the operator flipped the
Railway dashboard `REGENOLD_GRAPH_BACKEND` to `embedded`. The default test
suite, however, pins `REGENOLD_GRAPH_BACKEND=neo4j` (``tests/conftest.py``),
so before this module the now-live wiring — route/``kb_search`` →
``expand_2hop`` → embedded ``two_hop`` — had ZERO end-to-end coverage. These
tests close that gap and pin the R129-review fixes:

* ``/healthz/graph`` reports the embedded backend (was Neo4j-only → would
  misreport the live graph as ``graph_enabled=false``).
* the embedded 2-hop is genuinely wired (active without any Neo4j).
* ``EmbeddedGraph.close()`` is race-safe with concurrent reads.
* ``_engine_cache_key`` folds in the three R129 engine-behaviour flags.
* the "deterministic" fusion judge is order-independent on a score tie.
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from app.data.article_existence import ARTICLE_EXISTENCE


# ── /healthz/graph reports the embedded backend ──────────────────────────────


class TestHealthzGraphEmbedded:
    def test_reports_embedded_backend_and_counts(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        from app.main import app

        client = TestClient(app)
        resp = client.get("/healthz/graph")
        assert resp.status_code == 200
        body = resp.json()
        # The live embedded graph must NOT be reported as a disabled Neo4j.
        assert body["backend"] == "embedded"
        assert body["graph_enabled"] is True
        assert body["graph_ok"] is True
        assert "embedded" in body["detail"]
        # Surfaces the real node/edge counts (113 articles + 13 annexes).
        node_counts = body["node_counts"]
        assert sum(node_counts.values()) == len(ARTICLE_EXISTENCE)
        assert body["edge_counts"].get("CROSS_REFERENCES", 0) > 0

    def test_neo4j_path_untouched_when_explicitly_selected(self, monkeypatch):
        # With an explicit neo4j backend but no NEO4J_URI, the historical
        # "disabled" path must still report backend=neo4j / not-set.
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "neo4j")
        monkeypatch.delenv("NEO4J_URI", raising=False)
        from app.main import app

        client = TestClient(app)
        body = client.get("/healthz/graph").json()
        assert body["backend"] == "neo4j"
        assert body["graph_enabled"] is False
        assert "NEO4J_URI not set" in body["detail"]


# ── The embedded 2-hop is genuinely wired (active without Neo4j) ─────────────


class TestEmbeddedTwoHopWired:
    def test_is_enabled_without_any_neo4j(self, monkeypatch):
        # ``is_enabled()`` can only return True via the embedded branch here:
        # the Neo4j path requires NEO4J_URI + the driver, neither of which is
        # present in the test env. This proves the embedded backend is live.
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        monkeypatch.delenv("NEO4J_URI", raising=False)
        from app.engines import graph_expand_2hop as g2

        assert g2.is_enabled() is True

    def test_expand_2hop_surfaces_hop2_through_embedded(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GRAPH_2HOP", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        from app.engines import graph_expand_2hop as g2

        # Art. 26 (deployer) is a well-connected hub. A generous max_hop2
        # keeps the Cypher-parity ``LIMIT`` above the hop1 degree so hop2-only
        # neighbours survive (the default budget of 5 is intentionally tighter
        # — see the R129-review F1 note in the report).
        exp = g2.expand_2hop(["Art. 26"], max_hop2=50)
        assert exp.seed_articles == ("Art. 26",)
        assert exp.hop2_articles, "embedded 2-hop surfaced no hop2 neighbours"
        for ref in exp.hop2_articles:
            assert ref in ARTICLE_EXISTENCE  # existence-gated
            assert ref != "Art. 26"  # excludes the seed
            assert ref not in exp.hop1_articles  # hop2-only

        fused = g2.fuse_with_kb_xrefs(["Art. 26"], exp, budget=20)
        assert len(fused) > 1  # hop2 refs additively appended
        assert fused[0] == "Art. 26"  # BM25 winner preserved at the head

    def test_disabled_when_graph_2hop_env_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_GRAPH_2HOP", raising=False)
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        from app.engines import graph_expand_2hop as g2

        assert g2.is_enabled() is False  # env-gate still governs


# ── close() is race-safe with concurrent reads ──────────────────────────────


class TestEmbeddedCloseRaceSafe:
    def test_read_after_close_returns_empty_never_raises(self):
        from app.graph.embedded_graph import EmbeddedGraph

        g = EmbeddedGraph()
        assert g.enabled
        assert g.node_count() == len(ARTICLE_EXISTENCE)
        g.close()
        assert not g.enabled
        # Every read degrades to an empty result — no AttributeError /
        # "Cannot operate on a closed database".
        assert g.node_count() == 0
        assert g.edge_count() == 0
        assert g.directed_edges() == []
        assert g.two_hop(["6"], 10) == []
        assert g.neighbors("Art. 6") == []

    def test_concurrent_reads_and_close_do_not_raise(self):
        from app.graph.embedded_graph import EmbeddedGraph

        g = EmbeddedGraph()
        errors: list[BaseException] = []

        def reader() -> None:
            try:
                for _ in range(200):
                    g.two_hop(["26"], 10)
                    g.node_count()
            except Exception as exc:  # noqa: BLE001 — capture for the assert
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        g.close()  # races the readers; lock + local-bind must keep it safe
        for t in threads:
            t.join()
        assert not errors, f"concurrent read/close raised: {errors}"


# ── _engine_cache_key folds in the R129 engine-behaviour flags ──────────────


class TestEngineCacheKeyR129Flags:
    def test_new_flags_change_the_key(self, monkeypatch):
        from app.routes.regenold import _engine_cache_key

        base = _engine_cache_key("q", None)

        # STAGE2_SIMPLE_SKIP (unset in base) → flipping ON flips the answer.
        monkeypatch.setenv("REGENOLD_STAGE2_SIMPLE_SKIP", "1")
        assert _engine_cache_key("q", None) != base
        monkeypatch.delenv("REGENOLD_STAGE2_SIMPLE_SKIP", raising=False)

        # MAX_HOP2 (unset in base) → sizes the 2-hop budget.
        monkeypatch.setenv("REGENOLD_MAX_HOP2", "9")
        assert _engine_cache_key("q", None) != base
        monkeypatch.delenv("REGENOLD_MAX_HOP2", raising=False)

        # GRAPH_BACKEND (neo4j in base via conftest) → selects the 2-hop graph.
        monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
        assert _engine_cache_key("q", None) != base

    def test_key_stable_for_identical_inputs(self):
        from app.routes.regenold import _engine_cache_key

        assert _engine_cache_key("q", None) == _engine_cache_key("q", None)


# ── deterministic fusion judge is order-independent on a tie ─────────────────


class TestFusionDeterministicJudgeStable:
    def test_tie_break_is_order_independent(self):
        from app.engines.fusion import _deterministic_judge

        user = "EU AI ACT REFERENCES: Article 13 — transparency for high-risk AI."
        # Two non-wrapper drafts that both cite the allowed Article 13, both
        # > 40 chars, no first-person / dash penalties → identical score 1.0.
        groq = (
            "groq",
            "Article 13 requires high-risk providers to guarantee transparency for systems.",
        )
        mistral = (
            "mistral",
            "Article 13 mandates that high-risk providers give clear operating instructions.",
        )
        out1 = _deterministic_judge(user, [groq, mistral])
        out2 = _deterministic_judge(user, [mistral, groq])
        assert out1 == out2  # arrival order must not change the pick
        # Stable tie-break = alphabetically-first label (groq < mistral).
        assert out1 == groq[1].strip()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
