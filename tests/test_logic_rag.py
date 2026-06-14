"""R117 — LogicRAG hardening regression tests.

LogicRAG (``app/engines/logic_rag.py``) is the LLM-driven retrieval-replacement
engine wired into ``ask_compliance_question`` and default-ON in production
(``railway.toml`` REGENOLD_LOGIC_RAG=1). Before R117 it shipped with ZERO test
coverage, was unguarded (any exception 500'd the route), hardcoded a 120s
timeout, and dropped ``risk_level``. These tests pin the R117 hardening:

  * fail-soft DAG / JSON parsing (empty, garbage, object-not-list, fenced);
  * topological sort ranks + cycle safety (must terminate);
  * context-merge de-duplication by id;
  * ``execute_logic_rag`` returns a valid GraphContext with the wrapper off and
    threads ``risk_level`` through to retrieval;
  * THE GUARD — ``ask_compliance_question`` never raises when LogicRAG explodes
    (it falls back to the deterministic retrieval path), and LogicRAG is NOT
    invoked when REGENOLD_LOGIC_RAG is unset.
"""

from app.engines import logic_rag
from app.engines.graph_rag import GraphContext, ask_compliance_question
from app.engines.logic_rag import (
    _decompose_to_dag,
    _merge_contexts,
    _topological_sort,
    execute_logic_rag,
)
from app.models import GraphRAGRequest

_COMPLEX_Q = "We are both a provider and a deployer of a high-risk AI system; what are our obligations under Article 16 versus Article 26?"


class TestDecomposeFailSoft:
    def test_empty_output_falls_back_to_single_node(self, monkeypatch):
        monkeypatch.setattr(logic_rag, "_call_llm", lambda *a, **k: "")
        assert _decompose_to_dag("What is Article 5?") == [
            {"id": 1, "query": "What is Article 5?", "dependencies": []}
        ]

    def test_garbage_output_falls_back(self, monkeypatch):
        monkeypatch.setattr(logic_rag, "_call_llm", lambda *a, **k: "not json at all {[")
        assert _decompose_to_dag("Q") == [{"id": 1, "query": "Q", "dependencies": []}]

    def test_json_object_not_list_falls_back(self, monkeypatch):
        monkeypatch.setattr(logic_rag, "_call_llm", lambda *a, **k: '{"answer": "42"}')
        assert _decompose_to_dag("Q") == [{"id": 1, "query": "Q", "dependencies": []}]

    def test_valid_dag_parsed(self, monkeypatch):
        monkeypatch.setattr(
            logic_rag,
            "_call_llm",
            lambda *a, **k: '[{"id":1,"query":"a","dependencies":[]},{"id":2,"query":"b","dependencies":[1]}]',
        )
        dag = _decompose_to_dag("Q")
        assert len(dag) == 2 and dag[1]["dependencies"] == [1]

    def test_markdown_fenced_json_parsed(self, monkeypatch):
        monkeypatch.setattr(
            logic_rag,
            "_call_llm",
            lambda *a, **k: '```json\n[{"id":1,"query":"a","dependencies":[]}]\n```',
        )
        assert _decompose_to_dag("Q") == [{"id": 1, "query": "a", "dependencies": []}]


class TestTopologicalSort:
    def test_linear_deps_split_into_ordered_ranks(self):
        dag = [
            {"id": 1, "query": "a", "dependencies": []},
            {"id": 2, "query": "b", "dependencies": [1]},
        ]
        ranks = _topological_sort(dag)
        assert [n["id"] for n in ranks[0]] == [1]
        assert [n["id"] for n in ranks[1]] == [2]

    def test_independent_nodes_same_rank(self):
        dag = [
            {"id": 1, "query": "a", "dependencies": []},
            {"id": 2, "query": "b", "dependencies": []},
        ]
        ranks = _topological_sort(dag)
        assert len(ranks) == 1 and {n["id"] for n in ranks[0]} == {1, 2}

    def test_cycle_terminates_and_surfaces_all_nodes(self):
        dag = [
            {"id": 1, "query": "a", "dependencies": [2]},
            {"id": 2, "query": "b", "dependencies": [1]},
        ]
        ranks = _topological_sort(dag)  # must NOT hang
        assert {n["id"] for rank in ranks for n in rank} == {1, 2}


class TestMergeContexts:
    def test_dedup_article_info_by_id(self):
        base = GraphContext()
        base.article_info = [{"id": "A"}]
        new = GraphContext()
        new.article_info = [{"id": "A"}, {"id": "B"}]
        _merge_contexts(base, new)
        assert [a["id"] for a in base.article_info] == ["A", "B"]


class TestExecuteLogicRag:
    def test_wrapper_off_returns_valid_context(self, monkeypatch):
        # Wrapper disabled -> _call_llm returns "" -> single-node DAG ->
        # deterministic retrieve. No network, no exception.
        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: False)
        ctx = execute_logic_rag(
            "What are the obligations of a provider of a high-risk AI system?"
        )
        assert isinstance(ctx, GraphContext)
        assert ctx.retrieval_path == "logic_rag"

    def test_risk_level_threaded_to_retrieval(self, monkeypatch):
        seen = {}

        def fake_retrieve(parsed, risk_level=None, answers=None):
            seen["risk_level"] = risk_level
            return GraphContext()

        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: False)
        monkeypatch.setattr(logic_rag, "_retrieve_from_graph", fake_retrieve)
        execute_logic_rag("Q", {}, risk_level="risk_high")
        assert seen["risk_level"] == "risk_high"


class TestLogicRagGuard:
    def test_exception_falls_back_to_deterministic(self, monkeypatch):
        """The critical R117 fix: a LogicRAG exception must NOT propagate (no 500)."""
        monkeypatch.setenv("REGENOLD_LOGIC_RAG", "1")
        monkeypatch.setattr(
            "app.engines.question_complexity.is_complex_question", lambda *a, **k: True
        )

        def boom(*a, **k):
            raise RuntimeError("LogicRAG exploded")

        monkeypatch.setattr(logic_rag, "execute_logic_rag", boom)
        res = ask_compliance_question(GraphRAGRequest(question=_COMPLEX_Q))
        assert res is not None
        assert res.answer  # deterministic fallback produced a real answer

    def test_disabled_does_not_invoke_logic_rag(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_LOGIC_RAG", raising=False)

        def boom(*a, **k):
            raise AssertionError("LogicRAG must NOT run when REGENOLD_LOGIC_RAG is unset")

        monkeypatch.setattr(logic_rag, "execute_logic_rag", boom)
        res = ask_compliance_question(GraphRAGRequest(question=_COMPLEX_Q))
        assert res is not None


# ─── R117-review deep-code-review hardening ──────────────────────────────────


def _ctx(**kw) -> GraphContext:
    c = GraphContext()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestR117MergeCarriesPayload:
    """C1 — _merge_contexts must carry obligations + every retrieval-payload
    field, not just article_info (the multi-rank obligation-empty bug)."""

    def test_merge_carries_obligations(self):
        base = GraphContext()
        new = _ctx(obligations=[{"id": "Art. 16", "text": "provider duty"}])
        _merge_contexts(base, new)
        assert base.obligations == [{"id": "Art. 16", "text": "provider duty"}]

    def test_merge_carries_statements_recitals_xrefs(self):
        base = GraphContext()
        new = _ctx(
            semantically_relevant_statements=["[Art. 10] data governance"],
            referenced_annexes_and_recitals=[{"id": "Recital 27"}],
            xrefs=["Art. 9"],
        )
        _merge_contexts(base, new)
        assert "[Art. 10] data governance" in base.semantically_relevant_statements
        assert base.referenced_annexes_and_recitals == [{"id": "Recital 27"}]
        assert "Art. 9" in base.xrefs

    def test_merge_dedups_obligations_by_id(self):
        base = _ctx(obligations=[{"id": "Art. 16"}])
        new = _ctx(obligations=[{"id": "Art. 16"}, {"id": "Art. 26"}])
        _merge_contexts(base, new)
        assert [o["id"] for o in base.obligations] == ["Art. 16", "Art. 26"]

    def test_merge_accumulates_counters_and_degraded(self):
        base = _ctx(nodes_traversed=1, edges_followed=2)
        new = _ctx(nodes_traversed=3, edges_followed=4, degraded=True)
        _merge_contexts(base, new)
        assert base.nodes_traversed == 4 and base.edges_followed == 6
        assert base.degraded is True


class TestR117BraceSafeFill:
    """C3 — str.format on user/LLM/KB strings raised KeyError on literal braces."""

    def test_safe_fill_leaves_braces_in_values_inert(self):
        out = logic_rag._safe_fill("Question: {q}\nJSON:", q="what does {provider} mean?")
        assert out == "Question: what does {provider} mean?\nJSON:"

    def test_safe_fill_single_pass_no_cross_substitution(self):
        # memory contains the literal "{context}" — must NOT be re-substituted
        out = logic_rag._safe_fill(
            "M:{memory} C:{context}", memory="see {context} below", context="REAL"
        )
        assert out == "M:see {context} below C:REAL"

    def test_decompose_brace_question_no_raise(self, monkeypatch):
        monkeypatch.setattr(logic_rag, "_call_llm", lambda *a, **k: "")
        q = "What does '{x}' mean in {financial} services under Article 6?"
        assert _decompose_to_dag(q) == [{"id": 1, "query": q, "dependencies": []}]


class TestR117DagBounds:
    """M5 — node cap + duplicate-id dedup."""

    def test_node_cap(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOGIC_RAG_MAX_NODES", "3")
        big = [{"id": i, "query": f"q{i}", "dependencies": []} for i in range(1, 11)]
        assert len(logic_rag._finalise_dag(big)) == 3

    def test_duplicate_ids_deduped(self):
        dag = [
            {"id": 1, "query": "a", "dependencies": []},
            {"id": 1, "query": "b", "dependencies": []},
        ]
        out = logic_rag._finalise_dag(dag)
        assert len(out) == 1 and out[0]["query"] == "a"


class TestR117IdTypeNormalisation:
    """M3 — int id vs str dependency must still resolve the edge."""

    def test_int_id_str_dep_resolves_in_order(self):
        dag = [
            {"id": 1, "query": "a", "dependencies": []},
            {"id": 2, "query": "b", "dependencies": ["1"]},  # str dep vs int id
        ]
        ranks = _topological_sort(dag)
        assert [n["id"] for n in ranks[0]] == [1]
        assert [n["id"] for n in ranks[1]] == [2]

    def test_missing_dep_does_not_stall(self):
        dag = [{"id": 1, "query": "a", "dependencies": ["999"]}]  # dep to nonexistent
        ranks = _topological_sort(dag)
        assert {n["id"] for rank in ranks for n in rank} == {1}


class TestR117TruncationSoftFail:
    """M4 — finish_reason=length is a soft failure (returns "")."""

    def test_length_finish_reason_returns_empty(self, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: True)
        resp = MagicMock()
        resp.error = None
        resp.text = "partial mid-sen"
        resp.finish_reason = "length"
        prov = MagicMock()
        prov.complete.return_value = resp
        monkeypatch.setattr(logic_rag, "get_openai_wrapper_provider", lambda: prov)
        assert logic_rag._call_llm("s", "u") == ""

    def test_stop_finish_reason_returns_text(self, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: True)
        resp = MagicMock()
        resp.error = None
        resp.text = "complete answer."
        resp.finish_reason = "stop"
        prov = MagicMock()
        prov.complete.return_value = resp
        monkeypatch.setattr(logic_rag, "get_openai_wrapper_provider", lambda: prov)
        assert logic_rag._call_llm("s", "u") == "complete answer."


class TestR117Budget:
    """C2 — total wall-clock budget + per-call timeout clamp."""

    def test_budget_env_parse(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOGIC_RAG_BUDGET", "5")
        assert logic_rag._logic_rag_budget_seconds() == 5.0

    def test_budget_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_LOGIC_RAG_BUDGET", "abc")
        assert logic_rag._logic_rag_budget_seconds() == 12.0

    def test_call_llm_clamps_to_timeout_override(self, monkeypatch):
        from unittest.mock import MagicMock

        captured = {}
        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: True)
        monkeypatch.setenv("REGENOLD_LOGIC_RAG_TIMEOUT", "15")

        def fake_complete(req):
            captured["timeout"] = req.timeout_seconds
            r = MagicMock()
            r.error = None
            r.text = "ok"
            r.finish_reason = "stop"
            return r

        prov = MagicMock()
        prov.complete.side_effect = fake_complete
        monkeypatch.setattr(logic_rag, "get_openai_wrapper_provider", lambda: prov)
        logic_rag._call_llm("s", "u", timeout_override=3.0)
        assert captured["timeout"] == 3.0  # min(15, 3)

    def test_truncate_on_boundary(self):
        text = "First sentence here. Second sentence here. Third."
        out = logic_rag._truncate_on_boundary(text, 25)
        assert out == "First sentence here."


class TestR117ExecuteHardening:
    """C4 (empty→None) + M1 (synthesis_memory, no fake article) + M2 (sanitise)."""

    def test_empty_retrieval_returns_none(self, monkeypatch):
        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: False)
        monkeypatch.setattr(logic_rag, "_retrieve_from_graph", lambda *a, **k: GraphContext())
        assert execute_logic_rag("What is the obligation here?") is None

    def test_nonempty_retrieval_returns_context(self, monkeypatch):
        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: False)
        monkeypatch.setattr(
            logic_rag, "_retrieve_from_graph",
            lambda *a, **k: _ctx(article_info=[{"id": "Art. 6"}]),
        )
        ctx = execute_logic_rag("Q")
        assert ctx is not None and ctx.retrieval_path == "logic_rag"

    def test_synthesis_memory_set_no_fake_article(self, monkeypatch):
        # Force a 2-rank DAG so context pruning fires.
        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: True)
        monkeypatch.setattr(
            logic_rag, "_decompose_to_dag",
            lambda q, deadline=None: [
                {"id": 1, "query": "a", "dependencies": []},
                {"id": 2, "query": "b", "dependencies": [1]},
            ],
        )
        monkeypatch.setattr(
            logic_rag, "_retrieve_from_graph",
            lambda *a, **k: _ctx(article_info=[{"id": "Art. 6", "article": "Article 6"}]),
        )
        monkeypatch.setattr(logic_rag, "_call_llm", lambda *a, **k: "Synthesised analysis.")
        ctx = execute_logic_rag("Q")
        assert ctx is not None
        assert ctx.synthesis_memory == "Synthesised analysis."
        # No fake "LogicRAG Synthesis" article injected into the citation pool:
        assert all(a.get("id") != "LogicRAG Synthesis" for a in ctx.article_info)
        assert any(
            s.startswith("LOGIC_RAG_MEMORY:") for s in ctx.semantically_relevant_statements
        )

    def test_query_sanitised_before_retrieval(self, monkeypatch):
        seen = {}
        real_parse = logic_rag._deterministic_parse
        monkeypatch.setattr(logic_rag, "is_openai_wrapper_enabled", lambda: False)
        monkeypatch.setattr(logic_rag, "sanitize_for_llm", lambda s, **k: "SANITISED QUERY")

        def fake_parse(q):
            seen["q"] = q
            return real_parse(q)

        monkeypatch.setattr(logic_rag, "_deterministic_parse", fake_parse)
        monkeypatch.setattr(
            logic_rag, "_retrieve_from_graph",
            lambda *a, **k: _ctx(article_info=[{"id": "Art. 6"}]),
        )
        execute_logic_rag("raw <tag>injection</tag>")
        assert seen["q"] == "SANITISED QUERY"


class TestR117StageContextRender:
    """M1 — synthesis_memory renders as a labelled non-citation Stage-2 block."""

    def test_synthesis_memory_rendered_when_present(self):
        from app.engines.graph_rag import _build_context_references_block

        ctx = _ctx(
            article_info=[{"id": "Art. 6", "article": "Article 6", "text": "high-risk"}],
            synthesis_memory="Multi-hop synthesis prose.",
        )
        block = _build_context_references_block(ctx)
        assert "SYNTHESIZED MULTI-HOP ANALYSIS" in block
        assert "Multi-hop synthesis prose." in block

    def test_no_synthesis_section_when_absent(self):
        from app.engines.graph_rag import _build_context_references_block

        ctx = _ctx(article_info=[{"id": "Art. 6", "article": "Article 6", "text": "x"}])
        block = _build_context_references_block(ctx)
        assert "SYNTHESIZED MULTI-HOP ANALYSIS" not in block
