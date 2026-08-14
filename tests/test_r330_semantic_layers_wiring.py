"""R330 — the R327 semantic layer was dead code; pin the wiring that revives it.

The defect: ``_render_supplementary_sections`` (``app/engines/_graph_rag_impl.py``)
is the ONLY ``render_kg_context`` call site in ``app/``, and it omitted the
``question`` argument. ``kg_context._render_semantic_layers`` opens with
``if not question: return []``, so BOTH R327 features —
``REGENOLD_GRAPH_SEMANTIC_LAYERS`` and ``REGENOLD_SEMANTIC_GLOSS`` — emitted zero
Stage-2 context on every request, while the layers flag read ON and was
registered in ``_engine_cache_key``.

These tests fail on the pre-R330 code and pass after it.
"""
from __future__ import annotations

import inspect

import app.engines.kg_context as kg
from app.engines.graph_rag.models import GraphContext


def test_render_kg_context_accepts_a_question() -> None:
    """The signature must keep the parameter the call site now passes."""
    sig = inspect.signature(kg.render_kg_context)
    assert "question" in sig.parameters


def test_semantic_layers_short_circuit_on_empty_question_still_exists() -> None:
    """Pin the guard itself — it is WHY the missing argument was fatal.

    If someone deletes this guard the bug looks fixed while the real call site
    is still broken, so the guard is part of the contract this test protects.
    """
    src = inspect.getsource(kg._render_semantic_layers)
    assert "if not question" in src


def test_supplementary_sections_forwards_the_question(monkeypatch) -> None:
    """THE REGRESSION TEST: the engine must hand the question to the renderer.

    Pre-R330 this captured ``""`` and the semantic layer never ran.
    """
    import app.engines._graph_rag_impl as impl

    seen: dict[str, object] = {}

    def _fake_render(refs, question=""):
        seen["refs"] = refs
        seen["question"] = question
        return ["KG BLOCK"]

    monkeypatch.setattr(kg, "render_kg_context", _fake_render)

    ctx = GraphContext()
    ctx.question = "Must a deployer of an emotion recognition system inform people?"
    ctx.article_info = [{"cite": "Art. 50", "title": "Transparency", "text": "x"}]

    parts = impl._render_supplementary_sections(ctx, include_kg=True)

    assert seen.get("question") == ctx.question, (
        "render_kg_context was called without the question — the R327 semantic "
        "layer is dead again"
    )
    assert any("KG BLOCK" in p for p in parts)


def test_include_kg_false_still_skips_the_renderer(monkeypatch) -> None:
    """The citation-drift allowlist path must not gain graph blocks."""
    import app.engines._graph_rag_impl as impl

    called = {"n": 0}

    def _fake_render(refs, question=""):
        called["n"] += 1
        return ["KG BLOCK"]

    monkeypatch.setattr(kg, "render_kg_context", _fake_render)

    ctx = GraphContext()
    ctx.question = "anything"
    impl._render_supplementary_sections(ctx, include_kg=False)

    assert called["n"] == 0


def test_semantic_layers_default_is_off() -> None:
    """R330 ships the repaired wiring with the flag DEFAULT OFF.

    That pairing keeps production byte-identical to the behaviour the bug
    produced. Repairing the wiring while leaving the flag ON would activate an
    unmeasured feature in production on merge — the R308/R299 mistake.
    """
    import os

    from app.engines.graph_semantic import semantic_layers_enabled

    os.environ.pop("REGENOLD_GRAPH_SEMANTIC_LAYERS", None)
    assert semantic_layers_enabled() is False


def test_semantic_layers_flag_parses_fail_closed(monkeypatch) -> None:
    """Garbage must mean OFF, never a silent enable (the R321 bug class)."""
    from app.engines.graph_semantic import semantic_layers_enabled

    for raw in ("", " ", "false", "no", "off", "-2", "four", "0"):
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", raw)
        assert semantic_layers_enabled() is False, raw

    for raw in ("1", "true", "yes", "on", "ON"):
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", raw)
        assert semantic_layers_enabled() is True, raw
