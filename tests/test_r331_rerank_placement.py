"""R331 — the reranker PLACEMENT, not the reranker itself.

``tests/test_r329_cohere_rerank.py`` pins the module's safety invariants
(permutation, never-drop, fail-open). Those all passed while the feature was
making **zero calls**, which is the whole problem this file exists to prevent.

R329 tried three placements. Each looked correct in the diff; each was a no-op
by construction:

    reorder the FINAL emitted refs        fires, but measured WORSE (-0.019)
    kb_search.top_articles_by_relevance   0 calls — gated behind `if not entities:`
    candidate list before the budget cut  0 calls — already within budget

An inert feature and a useless feature both produce +0.0000, so the tests below
assert the placement *runs* and *changes what reaches Stage-2* before any A/B
number off this path is worth reading.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engines import _graph_rag_impl as GR
from app.engines import cohere_rerank as CR
from app.engines import kg_context as KG

#: More than ``kg_context``'s ``_DEFAULT_MAX_REFS`` (8) — the truncation the
#: placement exists to exploit. At 8 or fewer refs the reorder is a pure
#: permutation of the graph fetch and changes no Stage-2 content.
_REFS = [
    "Article 6", "Article 43", "Annex I", "Article 50.1", "Article 13",
    "Annex III", "Article 5", "Article 99", "Article 19", "Article 27",
]
_Q = "must a deployer of an emotion recognition system inform the people exposed"


@pytest.fixture()
def _wired(monkeypatch):
    """Patch the seams around the placement and capture what the graph gets."""
    seen: dict[str, object] = {}

    monkeypatch.setattr(GR, "_context_article_refs", lambda ctx: list(_REFS))

    def _capture(refs, question=""):
        seen["refs"] = list(refs)
        seen["question"] = question
        return []

    monkeypatch.setattr(KG, "render_kg_context", _capture)
    # Provision text always resolves, so ``scorable`` is never the limiting
    # factor. (Verified against the real corpus: 10/10 of these refs resolve.)
    monkeypatch.setattr(
        "app.data.provision_text.get_provision_text", lambda r: f"verbatim text of {r}"
    )
    # Reverse whatever it is asked to rank — deterministic, and no network.
    monkeypatch.setattr(
        CR, "rerank_documents",
        lambda q, d, top_n=None: [(i, 1.0) for i in range(len(d) - 1, -1, -1)],
    )
    CR.reset_rerank_stats()
    return seen


def _render(question):
    """Drive the real call site. ``question`` rides on the GraphContext (R330)."""
    return GR._render_supplementary_sections(
        SimpleNamespace(question=question), include_kg=True
    )


def _on(monkeypatch):
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")


def test_placement_actually_fires(monkeypatch, _wired):
    """THE test. All three R329 placements would fail this one."""
    _on(monkeypatch)

    _render(_Q)

    assert CR.rerank_stats()["reordered"] == 1, (
        "the reranker did not reorder anything — this placement is inert, "
        f"stats={CR.rerank_stats()}"
    )
    assert _wired["refs"] != _REFS, "graph received the unreranked order"


def test_reorder_changes_which_provisions_survive_the_cut(monkeypatch, _wired):
    """Reordering must change CONTENT, not just order.

    ``kg_context.fetch_*`` truncates with ``_node_ids(refs, limit=max_refs)``,
    max_refs=8, so the surviving set is ``refs[:8]``. If that set is unchanged
    the placement is a permutation with no downstream effect — the exact defect
    in R329's third placement.
    """
    _on(monkeypatch)

    _render(_Q)

    assert set(_wired["refs"][:8]) != set(_REFS[:8]), (
        "the same 8 provisions survive the graph cut either way — reordering "
        "here would be a no-op on Stage-2 content"
    )


def test_default_off_is_byte_identical(monkeypatch, _wired):
    """Gate off ⇒ the graph sees exactly the pre-R331 list."""
    monkeypatch.delenv("REGENOLD_COHERE_RERANK", raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "x")

    _render(_Q)

    assert _wired["refs"] == _REFS
    assert CR.rerank_stats()["reordered"] == 0


def test_r330_question_still_reaches_the_graph(monkeypatch, _wired):
    """Composition guard.

    R330 repaired the dead R327 semantic layer by passing ``context.question``
    into ``render_kg_context``. R331 inserts a rerank between those two points.
    The question must still arrive, or R331 silently re-breaks R330's fix.
    """
    _on(monkeypatch)

    _render(_Q)

    assert _wired["question"] == _Q


def test_no_question_skips_the_rerank(monkeypatch, _wired):
    """No question ⇒ nothing to rank against; must not call out."""
    _on(monkeypatch)

    _render(None)
    _render("   ")

    assert _wired["refs"] == _REFS
    assert CR.rerank_stats()["reordered"] == 0


def test_context_is_not_mutated(monkeypatch, _wired):
    """The reorder must not leak back into the context.

    The wire reference list is built elsewhere from the same context. If this
    reordered it in place, a Stage-2 CONTEXT change would silently become a
    CITATION change — the one thing this placement claims it cannot do, and the
    claim on which "cannot drop a gold ref" rests.
    """
    _on(monkeypatch)
    ctx = SimpleNamespace(question=_Q)

    GR._render_supplementary_sections(ctx, include_kg=True)

    assert GR._context_article_refs(ctx) == _REFS


def test_flag_is_in_the_engine_cache_key(monkeypatch):
    """Trap #1: omitted from the key, arm B replays arm A and reads +0.0000."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("COHERE_API_KEY", "x")
    monkeypatch.delenv("REGENOLD_COHERE_RERANK", raising=False)
    off = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    on = _engine_cache_key("q", None)

    assert off != on, (
        "REGENOLD_COHERE_RERANK does not reach _engine_cache_key — an "
        "in-process A/B of this flag is unfalsifiable"
    )


def test_stats_distinguish_inert_from_ineffective(monkeypatch, _wired):
    """``noop`` vs ``reordered`` — the counter must tell these apart."""
    _on(monkeypatch)
    # An API returning the identity permutation: it RAN, and changed nothing.
    monkeypatch.setattr(
        CR, "rerank_documents",
        lambda q, d, top_n=None: [(i, 1.0) for i in range(len(d))],
    )

    _render(_Q)

    stats = CR.rerank_stats()
    assert stats["noop"] == 1 and stats["reordered"] == 0, stats
