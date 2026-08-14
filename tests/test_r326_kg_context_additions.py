import os

os.environ["NEO4J_AUTO_SEED"] = "0"

from types import SimpleNamespace

from app.engines import kg_context as kg
from app.engines.kg_context import (
    fetch_deontic_context,
    fetch_subpoint_detail,
    render_kg_context,
    reset_kg_context_memo,
)


def setup_function():
    reset_kg_context_memo()

def test_fetch_subpoint_detail_disabled_by_default():
    res = fetch_subpoint_detail(["Art. 5"])
    assert isinstance(res, list)

def test_fetch_deontic_context_disabled_by_default():
    res = fetch_deontic_context(["Art. 5"])
    assert isinstance(res, list)

def test_render_kg_context_returns_list():
    res = render_kg_context(["Art. 5"])
    assert isinstance(res, list)


def test_annex_iii_has_a_direct_category_query_path():
    assert "'annex_III' IN $ids" in kg._DEONTIC_CYPHER
    assert "MATCH (cat:AnnexIIICategory)" in kg._DEONTIC_CYPHER
    assert "CALL () {" in kg._DEONTIC_CYPHER, (
        "a bare `CALL {` is deprecated on Aura (01N00 variable scope clause)"
    )


def test_annex_iii_only_reference_fires_category_render(monkeypatch):
    # R330 Z3 — the deontic fetch is now gated (REGENOLD_KG_DEONTIC, default
    # OFF) because its Cypher could never execute: it ends ``LIMIT $limit`` and
    # the caller never bound ``$limit``, so Aura returned ParameterMissing,
    # ``execute_read`` swallowed it as ``[]``, and the block never rendered.
    # This test asserts the render, so it must opt the gate ON explicitly.
    monkeypatch.setenv("REGENOLD_KG_DEONTIC", "1")
    calls = []

    def _read(cypher, params):
        calls.append((cypher, params))
        if cypher == kg._DEONTIC_CYPHER:
            assert params["ids"] == ["annex_III"]
            return [{
                "cite": "Annex III",
                "practices": [],
                "annex_iii": ["Employment, workers management and access to self-employment"],
                "roles": [],
                "phases": [],
            }]
        return []

    monkeypatch.setattr(kg, "_bounded_execute_read", _read)
    reset_kg_context_memo()

    rendered = "\n".join(render_kg_context(["Annex III"]))

    assert "KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION" in rendered
    assert "Employment, workers management" in rendered
    assert any(cypher == kg._DEONTIC_CYPHER for cypher, _params in calls)


def test_subpoint_renders_full_roman_coordinate_with_neutral_label(monkeypatch):
    monkeypatch.setattr(kg, "fetch_provision_hierarchy", lambda _refs: [])
    monkeypatch.setattr(kg, "fetch_recital_anchors", lambda _refs: [])
    monkeypatch.setattr(kg, "fetch_deontic_context", lambda _refs: [])
    monkeypatch.setattr(
        kg,
        "fetch_subpoint_detail",
        lambda _refs: [{
            "cite": "Article 5",
            "para": "1",
            "letter": "h",
            "roman": "iii",
            "sid": "article_5_1_h_iii",
            "text": "A nested enumerated element.",
        }],
    )

    rendered = "\n".join(render_kg_context(["Art. 5"]))

    assert "KNOWLEDGE-GRAPH SUB-POINT DETAIL" in rendered
    assert "paragraph 1, point (h), subpoint (iii)" in rendered
    assert "CARVE-OUT" not in rendered


def test_hard_cap_reserves_present_r326_sections(monkeypatch):
    # R330 Z3 — see the note on the category-render test above: this asserts a
    # reserve for the deontic section, so it needs the gate ON explicitly.
    monkeypatch.setenv("REGENOLD_KG_DEONTIC", "1")
    monkeypatch.setenv("REGENOLD_KG_MAX_CHARS", "2000")
    monkeypatch.setattr(
        kg,
        "fetch_provision_hierarchy",
        lambda _refs: [{
            "id": "article_5",
            "cite": "Article 5",
            "title": "Prohibited AI practices",
            "units": [{"num": str(i), "text": "long hierarchy text " * 100} for i in range(12)],
        }],
    )
    monkeypatch.setattr(kg, "fetch_recital_anchors", lambda _refs: [])
    monkeypatch.setattr(
        kg,
        "fetch_subpoint_detail",
        lambda _refs: [{
            "cite": "Article 5", "para": "1", "letter": "h", "roman": "i",
            "text": "Nested element retained under the reserved budget.",
        }],
    )
    monkeypatch.setattr(
        kg,
        "fetch_deontic_context",
        lambda _refs: [{
            "cite": "Article 5",
            "practices": ["manipulative practice"],
            "annex_iii": [], "roles": [], "phases": [],
        }],
    )

    parts = render_kg_context(["Art. 5"])
    rendered = "\n".join(parts)

    assert sum(map(len, parts)) <= 2000
    assert len("\n".join(parts)) <= 2000
    assert "KNOWLEDGE-GRAPH SUB-POINT DETAIL" in rendered
    assert "KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION" in rendered


def test_strict_read_failure_is_not_memoised_as_empty(monkeypatch):
    calls = []

    class StrictClient:
        enabled = True

        def execute_read_strict(self, cypher, params=None):
            calls.append((cypher, params))
            raise RuntimeError("authentication failed")

        def execute_read(self, *_a, **_kw):
            return []

    monkeypatch.setattr("app.graph.client.get_graph_client", lambda: StrictClient())
    monkeypatch.setattr("app.graph.timeouts.graph_circuit_open", lambda: False)
    monkeypatch.setattr("app.graph.timeouts.record_graph_failure", lambda: None)
    monkeypatch.setattr("app.graph.timeouts.record_graph_success", lambda: None)
    reset_kg_context_memo()

    assert kg.fetch_provision_hierarchy(["Art. 97"]) == []
    assert kg.fetch_provision_hierarchy(["Art. 97"]) == []
    assert len(calls) == 2


def test_executor_cold_initialization_is_singleton_under_concurrency():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    previous = getattr(kg, "_EXECUTOR", None)
    created = None
    kg._EXECUTOR = None
    barrier = Barrier(8)

    def _cold_get():
        barrier.wait()
        return kg._get_kg_executor()

    try:
        with ThreadPoolExecutor(max_workers=8) as callers:
            executors = list(callers.map(lambda _idx: _cold_get(), range(8)))
        created = executors[0]
        assert all(executor is created for executor in executors)
    finally:
        if created is not None:
            created.shutdown(wait=True, cancel_futures=True)
        kg._EXECUTOR = previous


def test_semantic_layers_default_off_after_r330(monkeypatch):
    """R330 — this default was flipped ON -> OFF, deliberately.

    Was ``test_semantic_layers_default_on_constrained_only``, asserting ON. The
    ON default was never real: R330 found the only ``render_kg_context`` call
    site in ``app/`` omitted the ``question`` argument, and
    ``kg_context._render_semantic_layers`` returns ``[]`` when it is empty — so
    the layer emitted nothing on every request regardless of this flag.

    R330 repairs the wiring AND flips the default to OFF in the same commit, so
    production stays byte-identical to the behaviour the bug produced instead of
    silently activating an unmeasured feature (live Neo4j vector queries on a
    scored latency axis) the moment the wiring landed.

    This is a deliberate contract change, not a weakened assertion: the flag
    still has both states, and ``test_semantic_layers_have_an_off_switch`` plus
    ``tests/test_r330_semantic_layers_wiring.py`` pin the ON path and the
    fail-closed parse.
    """
    from app.engines import graph_semantic as gs

    monkeypatch.delenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", raising=False)
    monkeypatch.delenv("REGENOLD_SEMANTIC_GLOSS", raising=False)
    assert gs.semantic_layers_enabled() is False
    assert gs.gloss_layers_enabled() is False


def test_semantic_layers_have_an_on_switch(monkeypatch):
    """The repaired path must still be reachable — R330."""
    from app.engines import graph_semantic as gs

    monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
    assert gs.semantic_layers_enabled() is True


def test_semantic_layers_have_an_off_switch(monkeypatch):
    from app.engines import graph_semantic as gs

    monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "0")
    assert gs.semantic_layers_enabled() is False


def test_gloss_off_suppresses_only_the_open_domain_blocks(monkeypatch):
    from app.engines import graph_semantic as gs

    monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
    monkeypatch.setenv("REGENOLD_SEMANTIC_GLOSS", "0")
    assert gs.fetch_definition_and_recital_context("q", ["Article 50"]) == []


def test_both_semantic_flags_are_in_the_engine_cache_key():
    import app.routes.regenold as route
    import inspect

    body = inspect.getsource(route._engine_cache_key)
    for flag in ("REGENOLD_GRAPH_SEMANTIC_LAYERS", "REGENOLD_SEMANTIC_GLOSS"):
        assert flag in body, f"{flag} missing from _engine_cache_key"
