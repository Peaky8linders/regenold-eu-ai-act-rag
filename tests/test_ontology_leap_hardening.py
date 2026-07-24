"""Regression guards for the Ontology Leap (Legal AST) hardening round.

These pin the fixes that the Gemini "complete Ontology Leap" commit (008caaa)
shipped broken / latent:

* the ``_CYPHER_HAS_RECITAL_ANCHOR`` rename NameError that crashed the LIVE
  Aura seed (``seed_graph`` referenced a name the commit deleted);
* the annex node drift (legal_ast mislabelled annexes ``:Article`` with a
  lowercase id; ontology_ingest pointed edges at a duplicate ``:Article``);
* the prod-seed path never building the Paragraph/Point hierarchy the
  Article 6(3) Cypher depends on;
* the parenthesised ``Article 6(3)(a)`` citation (forbidden wire shape);
* the bridging-context block missing the "do not cite" guard.

Pure / mocked — no live Neo4j required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _RecordingClient:
    """A GraphClient stand-in that records every write without a real driver."""

    enabled = True

    def __init__(self, *_a, **_k):
        self.writes: list = []
        self.batches: list = []

    def execute_write(self, query, parameters=None):
        self.writes.append((query, parameters))
        return []

    def execute_write_batch(self, queries):
        self.batches.append(list(queries))

    def execute_read(self, query, parameters=None):
        return []

    def clear_graph(self):  # pragma: no cover - not exercised here
        pass

    def close(self):
        pass


# ── ship-blocker: the recital-anchor NameError ───────────────────────────────


def test_seeder_recital_anchor_template_is_defined():
    """``seed_graph`` references ``_CYPHER_HAS_RECITAL_ANCHOR`` — it MUST exist.

    The Gemini commit renamed the definition to ``_CYPH_MERGE_HAS_RECITAL_ANCHOR``
    while the usage stayed ``_CYPHER_HAS_RECITAL_ANCHOR`` — a runtime NameError
    that only fires against an enabled client (i.e. the live Aura seed).
    """
    import scripts.seed_neo4j_kb as s

    assert hasattr(s, "_CYPHER_HAS_RECITAL_ANCHOR")
    assert "HAS_RECITAL_ANCHOR" in s._CYPHER_HAS_RECITAL_ANCHOR


def test_seed_graph_runs_end_to_end_without_nameerror():
    """The whole seeder write-path must execute without an undefined name."""
    import scripts.seed_neo4j_kb as s

    payload = s.build_payload()
    client = _RecordingClient()
    counts = s.seed_graph(client, payload, batch_size=500, verbose=False)

    # every edge/node group wrote (the recital-anchor edge among them)
    assert "HAS_RECITAL_ANCHOR" in counts
    assert counts["HAS_OBLIGATION"] > 0


# ── prod seed actually builds the Paragraph/Point hierarchy ──────────────────


def test_run_seed_invokes_legal_ast_hierarchy():
    """``run_seed`` (the prod auto-seed entrypoint) builds the AST hierarchy."""
    import scripts.seed_neo4j_kb as s

    client = _RecordingClient()
    with patch("app.graph.client.GraphClient", return_value=client), patch(
        "app.graph.config.GraphSettings", return_value=object()
    ):
        result = s.run_seed(dry_run=False, clear=False, verbose=False)

    assert result["status"] == "ok"
    # The hierarchy marker is recorded in the counts dict.
    assert result["counts"].get("legal_ast_hierarchy") == 1
    # And Paragraph/Point nodes were actually MERGEd through the seed client.
    all_q = [q for batch in client.batches for q in batch]
    texts = [q[0] for q in all_q]
    assert any("MERGE (p:Paragraph {id: $id})" in t for t in texts)
    assert any("MERGE (pt:Point {id: $id})" in t for t in texts)
    # article_6_3 — the node the graph_rag Article 6(3) Cypher traverses.
    assert any(q[1].get("id") == "article_6_3" for q in all_q)


def test_run_seed_survives_hierarchy_failure():
    """A hierarchy-ingest error must NOT abort an otherwise-successful seed."""
    import scripts.seed_neo4j_kb as s

    client = _RecordingClient()
    with patch("app.graph.client.GraphClient", return_value=client), patch(
        "app.graph.config.GraphSettings", return_value=object()
    ), patch(
        "app.engines.legal_ast.ingest_legal_ast", side_effect=RuntimeError("boom")
    ):
        result = s.run_seed(dry_run=False, clear=False, verbose=False)

    assert result["status"] == "ok"  # base seed still succeeded
    assert result["counts"].get("legal_ast_hierarchy") == 0  # fail-soft marker


def test_seed_version_bumped_for_hierarchy():
    """SEED_VERSION must move so existing Aura instances re-seed the hierarchy."""
    import scripts.seed_neo4j_kb as s

    assert s.SEED_VERSION != "2026-05-24-r84c"
    # canonical ``YYYY-MM-DD-<slug>`` shape
    assert s.SEED_VERSION.startswith("2026-")


# ── annex node consistency across the 3 modules ──────────────────────────────


def test_legal_ast_annexes_match_seeder_label_and_id():
    """legal_ast annex nodes are ``:Annex`` with the seeder's UPPERCASE id."""
    import scripts.seed_neo4j_kb as seed
    from app.engines import legal_ast

    mc = MagicMock()
    mc.enabled = True
    legal_ast.ingest_legal_ast(mc)

    queries = []
    for call in mc.execute_write_batch.call_args_list:
        queries.extend(call[0][0])

    annex_merges = [q for q in queries if "MERGE (a:Annex {id: $id})" in q[0]]
    annex_ids = {q[1]["id"] for q in annex_merges}
    assert annex_ids  # at least one annex node
    # ids match the seeder convention exactly
    assert "annex_III" in annex_ids
    assert "annex_iii" not in annex_ids
    assert seed._article_id("Annex III") in annex_ids
    # NO annex root mislabelled as :Article (the pre-fix duplicate bug)
    assert not any(
        "MERGE (a:Article {id: $id})" in q[0] and str(q[1].get("id", "")).startswith("annex_")
        for q in queries
    )
    # annex paragraphs attach to :Annex, not :Article (R291 label-qualified
    # per parent kind; the id param is the shared writer's ``$source_id``).
    assert any("MATCH (a:Annex {id: $source_id})" in q[0] for q in queries)


def test_legal_ast_articles_still_match_seeder():
    """Article roots are unchanged: ``article_<n>`` :Article (no regression)."""
    import scripts.seed_neo4j_kb as seed
    from app.engines import legal_ast

    mc = MagicMock()
    mc.enabled = True
    legal_ast.ingest_legal_ast(mc)
    params = [q[1] for call in mc.execute_write_batch.call_args_list for q in call[0][0]]
    assert any(p.get("id") == "article_6" for p in params)
    assert seed._article_id("Art. 6") == "article_6"


# ── reference-format compliance for the 6(3) injection ───────────────────────


def test_6_3_internal_citation_converts_to_valid_wire_ref():
    """``Art. 6(3)(a)`` (the injected form) -> strict dotted ``Article 6.3.a``."""
    from app.integrations.regenold.models import reference_from_article_ref

    assert reference_from_article_ref("Art. 6(3)(a)") == "Article 6.3.a"
    assert reference_from_article_ref("Art. 6(3)(d)") == "Article 6.3.d"


def test_engine_injects_internal_canonical_6_3_form_not_parenthesised():
    """The engine source injects ``Art. 6(3)(...)``, never ``Article 6(3)(...)``."""
    import inspect
    import app.engines.graph_rag as gr

    src = inspect.getsource(gr.ask_compliance_question)
    assert 'internal_citation = f"Art. 6(3)({letter})"' in src
    # the parenthesised wire form must never be the injected citation field
    assert '"article": internal_citation' in src


# ── bridging-context cite guard ──────────────────────────────────────────────


def test_bridging_block_carries_do_not_cite_guard():
    from app.engines.graph_rag import GraphContext, _build_context_references_block

    ctx = GraphContext()
    ctx.bridging_context = ["GDPR Art. 9 (Special Categories of Data)"]
    block = _build_context_references_block(ctx)
    assert "CROSS-REGULATORY BRIDGING CONTEXT" in block
    assert "GDPR Art. 9 (Special Categories of Data)" in block
    # the guard the other supporting-context blocks already carry
    assert "NEVER emit them as an Article/Annex citation" in block
