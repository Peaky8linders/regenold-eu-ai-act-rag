"""R323/W2 — the knowledge-graph blocks must not widen the citation-drift allowlist.

``_extract_context_grounded_refs`` builds the allowlist for
``_polished_prose_has_unknown_citations`` by MINING the rendered references
block. ``kg_context`` renders the regulation's own provision structure and
cross-references into that block, and every one of its headings tells the model
"do NOT cite anything here that is not already listed above".

So a citation appearing ONLY in the graph blocks IS drift — and admitting it to
the allowlist silently disarms the guard that is supposed to catch it.

MEASURED before the fix, with REGENOLD_KG_CONTEXT OFF vs ON:

    allowlist 21 -> 27 refs, mined block  7,923 -> 24,329 chars
    allowlist 17 -> 24 refs, mined block  5,023 -> 21,234 chars
    allowlist 13 -> 14 refs, mined block  1,179 ->  6,849 chars

with the added refs being Art. 35 / 46 / 74 / Annex VIII / Annex IX — the
regulation's own cross-references, not provisions we retrieved.

This is precisely the treatment R288.1 already applied to the verbatim grounding
section ("the regulation's own cross-references are not provisions we supplied,
and admitting them turns the guard's allowlist into a superset of what was
retrieved"). The graph blocks never got it, and wiring more graph layers onto
the answer path only widened the hole.

THE ASYMMETRY THESE TESTS PIN: the model must still SEE the graph context (it is
useful, non-citable background), while the GUARD must not treat it as licence to
cite. Only the guard passes ``include_grounding=False``, so the prompt is
unaffected.
"""

from __future__ import annotations

import pytest

import app.engines._graph_rag_impl as G
import app.engines.kg_context as K

_KG_MARKERS = (
    "KNOWLEDGE-GRAPH PROVISION STRUCTURE",
    "KNOWLEDGE-GRAPH SUB-POINT DETAIL",
    "KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION",
    "KNOWLEDGE-GRAPH RECITAL ANCHORS",
)


class _FakeClient:
    """Minimal graph stub so these run without a live instance."""

    enabled = True

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        if "HAS_PARAGRAPH" in query:
            return [
                {
                    "id": "article_5",
                    "cite": "Article 5",
                    "title": "Prohibited AI practices",
                    # A cross-reference the regulation makes but we did NOT retrieve.
                    "units": [{"num": "1", "text": "See Article 74 and Annex IX for enforcement."}],
                }
            ]
        return []


@pytest.fixture()
def graphy(monkeypatch: pytest.MonkeyPatch):
    import app.graph.client as GC

    monkeypatch.setattr(GC, "get_graph_client", lambda: _FakeClient())
    monkeypatch.setattr(K, "kg_context_enabled", lambda: True)
    K._RENDER_MEMO.set(None)
    yield
    K._RENDER_MEMO.set(None)


def _context():
    return G._retrieve_from_kb(G._deterministic_parse("What must a deployer of a high-risk AI system do?"))


# ── the guard-mined block excludes the graph blocks ─────────────────────────


def test_guard_block_excludes_kg_context(graphy) -> None:
    """include_grounding=False is the guard-mining path."""
    block = G._build_context_references_block(_context(), include_grounding=False)
    for marker in _KG_MARKERS:
        assert marker not in block, f"{marker} must not reach the drift allowlist"


def test_prompt_block_still_includes_kg_context(graphy) -> None:
    """The model must still SEE the graph context — this is the asymmetry."""
    K._RENDER_MEMO.set(None)
    block = G._build_context_references_block(_context(), question="deployer duties?")
    assert any(m in block for m in _KG_MARKERS), (
        "the prompt must keep the graph context; only the guard drops it"
    )


def test_allowlist_is_not_widened_by_the_graph(graphy) -> None:
    """Turning the graph on must not add refs to the allowlist."""
    ctx = _context()

    K._RENDER_MEMO.set(None)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(K, "kg_context_enabled", lambda: False)
        off = G._extract_context_grounded_refs(ctx)

    K._RENDER_MEMO.set(None)
    on = G._extract_context_grounded_refs(ctx)

    assert on == off, f"the graph widened the allowlist by {sorted(on - off)}"


def test_render_supplementary_sections_honours_include_kg(graphy) -> None:
    ctx = _context()
    K._RENDER_MEMO.set(None)
    with_kg = "\n".join(G._render_supplementary_sections(ctx, include_kg=True))
    K._RENDER_MEMO.set(None)
    without = "\n".join(G._render_supplementary_sections(ctx, include_kg=False))
    assert any(m in with_kg for m in _KG_MARKERS)
    assert not any(m in without for m in _KG_MARKERS)


def test_include_kg_defaults_true_so_the_prompt_path_is_unchanged(graphy) -> None:
    """Every caller except the guard relies on the default."""
    ctx = _context()
    K._RENDER_MEMO.set(None)
    default = "\n".join(G._render_supplementary_sections(ctx))
    K._RENDER_MEMO.set(None)
    explicit = "\n".join(G._render_supplementary_sections(ctx, include_kg=True))
    assert default == explicit


def test_only_the_guard_passes_include_grounding_false() -> None:
    """If another caller starts passing False, it would silently lose the graph.

    Pinning this makes that a test failure rather than a silent prompt change.
    """
    import pathlib
    import re

    src = pathlib.Path(G.__file__).read_text(encoding="utf-8")
    hits = [
        m.start()
        for m in re.finditer(r"_build_context_references_block\([^)]*include_grounding=False", src)
    ]
    assert len(hits) == 1, (
        f"expected exactly one include_grounding=False caller (the guard), found {len(hits)}"
    )
