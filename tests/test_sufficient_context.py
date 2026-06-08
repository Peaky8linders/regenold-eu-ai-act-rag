"""R110 — Sufficient-Context gate: bounded, deterministic multi-hop decomposition.

Covers the four invariants the round must hold:

* **Default OFF** — ``sufficient_context_enabled()`` is False without the env,
  so the davidath TestClient bench is byte-identical by construction.
* **Deterministic missing-pieces analysis** — ``assess_sufficiency`` fires only
  on uncovered explicit refs or genuinely multi-part complex questions; the
  decomposition is a pure regex clause split with a verb-guarded coordination
  rule (no noun-coordination false split).
* **Additive-only merge** — the bounded hop appends sub-query obligations after
  the first-pass anchors, never displacing them, and accumulates counters.
* **Glass-box audit lineage** — every sub-query + the refs it surfaced lands in
  the ReasoningTrace; the cache key folds in the env flag (R30/R56/R79).
"""
from __future__ import annotations

import pytest

from app.engines import graph_rag as gr
from app.engines import sufficient_context as sc
from app.engines.graph_rag import GraphContext, GraphQuery
from app.integrations.regenold import reasoning_trace as rt
from app.models import GraphRAGRequest


@pytest.fixture
def trace():
    """Activate a fresh reasoning trace per test; deactivate on teardown."""
    t = rt.activate()
    yield t
    rt.deactivate()


# ── Env gates ────────────────────────────────────────────────────────────


def test_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_SUFFICIENT_CONTEXT", raising=False)
    assert sc.sufficient_context_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_enabled_truthy(monkeypatch, val) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", val)
    assert sc.sufficient_context_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", ""])
def test_disabled_falsy(monkeypatch, val) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", val)
    assert sc.sufficient_context_enabled() is False


def test_max_sub_queries_default(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", raising=False)
    assert sc.max_sub_queries() == 3


@pytest.mark.parametrize("env,expected", [("1", 1), ("5", 5), ("2", 2)])
def test_max_sub_queries_override(monkeypatch, env, expected) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", env)
    assert sc.max_sub_queries() == expected


@pytest.mark.parametrize("env", ["0", "9", "-3", "garbage"])
def test_max_sub_queries_clamped(monkeypatch, env) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", env)
    assert 1 <= sc.max_sub_queries() <= 5


# ── Reference normalisation ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "ref,key",
    [
        ("Art. 13", "art13"),
        ("Article 13", "art13"),
        ("Art 13", "art13"),
        ("Article 013", "art13"),
        ("Art. 5(1)(a)", "art5"),
        ("Annex IV", "annexiv"),
        ("Annex III(2)", "annexiii"),
        ("Annex 4", "annex4"),
        ("provider obligation", ""),
        ("", ""),
    ],
)
def test_article_key(ref, key) -> None:
    assert sc._article_key(ref) == key


def test_explicit_refs_dedupe_and_form() -> None:
    refs = sc._explicit_refs("What do Article 13 and Art. 13 and Annex iv require?")
    assert refs == ["Article 13", "Annex IV"]


def test_explicit_refs_none() -> None:
    assert sc._explicit_refs("What are the obligations of importers?") == []


# ── Decomposition ────────────────────────────────────────────────────────


def test_decompose_patient_weight_splits_two_clauses() -> None:
    q = (
        "Can a system be deployed that tracks patient weight or is it "
        "high risk according to Article 5?"
    )
    clauses = sc.decompose_question(q)
    assert len(clauses) == 2
    assert "patient weight" in clauses[0].lower()
    assert "article 5" in clauses[1].lower()


def test_decompose_noun_coordination_does_not_split() -> None:
    # "providers and deployers" is a NOUN coordination — the left side has no
    # clause verb, so it must NOT split into two sub-clauses.
    clauses = sc.decompose_question("What must providers and deployers do?")
    assert len(clauses) == 1


def test_decompose_long_noun_list_does_not_split() -> None:
    # The right side of each " and " starts with a bare noun ("deployers" /
    # "importers"), not a clause-initial token — so a long noun list must NOT
    # be chopped even though both sides clear the 4-word + verb guards.
    clauses = sc.decompose_question(
        "What must providers and deployers and importers do for high-risk AI?"
    )
    assert len(clauses) == 1


def test_decompose_genuine_two_clause_and_splits() -> None:
    # "what must X do AND what must Y do" — the right side begins with a
    # Wh-word, so it IS a genuine clause boundary (the importer/distributor
    # multi-part case the FRAMES methodology targets).
    clauses = sc.decompose_question(
        "What are the obligations of importers and what must distributors do?"
    )
    assert len(clauses) == 2
    assert "importer" in clauses[0].lower()
    assert "distributor" in clauses[1].lower()


def test_decompose_two_questions() -> None:
    clauses = sc.decompose_question(
        "What must importers do? What about distributors of high-risk AI?"
    )
    assert len(clauses) == 2


def test_decompose_uses_live_section_only() -> None:
    flattened = (
        "Conversation so far:\nuser: We are a hospital deploying triage AI.\n"
        "assistant: That is high-risk under Annex III.\n\n"
        "Latest question:\nDo we need human oversight or must we keep detailed logs?"
    )
    clauses = sc.decompose_question(flattened)
    # Only the live turn decomposes — the history prose must not leak in.
    joined = " ".join(clauses).lower()
    assert "conversation so far" not in joined
    assert "hospital" not in joined
    assert len(clauses) == 2


def test_decompose_single_clause_returns_one() -> None:
    clauses = sc.decompose_question("What does Article 13 require?")
    assert len(clauses) == 1


def test_decompose_empty() -> None:
    assert sc.decompose_question("") == []


# ── Sufficiency assessment ───────────────────────────────────────────────


def test_uncovered_explicit_ref_is_insufficient() -> None:
    v = sc.assess_sufficiency(
        "What do Article 13 and Article 50 require?",
        covered_articles={"Art. 13"},
    )
    assert v.sufficient is False
    assert v.reason == "uncovered_explicit_refs"
    assert "Article 50" in v.sub_queries
    assert "Article 13" not in v.sub_queries  # already covered
    assert v.uncovered_anchors == ("Article 50",)


def test_all_explicit_refs_covered_is_sufficient() -> None:
    v = sc.assess_sufficiency(
        "What do Article 13 and Article 50 require?",
        covered_articles={"Article 13", "Art. 50"},
    )
    assert v.sufficient is True
    assert v.sub_queries == ()


def test_uncovered_ref_fires_high_precision() -> None:
    # The explicit-ref gap is high precision — a named-but-missing article is
    # provably a gap, so it fires even on a short single-clause question.
    v = sc.assess_sufficiency("Tell me about Annex IV.", covered_articles=set())
    assert v.sufficient is False
    assert "Annex IV" in v.sub_queries


def test_multi_part_decomposes() -> None:
    q = (
        "Can a system be deployed that tracks patient weight or is it "
        "high risk according to the Act?"
    )
    v = sc.assess_sufficiency(q, covered_articles={"Art. 6"})
    assert v.sufficient is False
    assert v.reason == "multi_phrase_decompose"
    assert len(v.sub_queries) == 2


def test_importer_distributor_multi_part_decomposes() -> None:
    # The FRAMES target: a single-sentence multi-part ask whose two anchors
    # (Art. 23 importer / Art. 24 distributor) a single BM25 pass typically
    # surfaces only one of. The gate decomposes so BOTH get retrieved.
    q = "What are the obligations of importers and what must distributors do?"
    v = sc.assess_sufficiency(q, covered_articles={"Art. 24"})
    assert v.sufficient is False
    assert v.reason == "multi_phrase_decompose"
    assert len(v.sub_queries) == 2


def test_noun_list_is_sufficient() -> None:
    # A noun-list coordination must NOT trip the multi-part decompose.
    q = "What must providers and deployers and importers do for high-risk AI?"
    v = sc.assess_sufficiency(q, covered_articles={"Art. 6"})
    assert v.sufficient is True
    assert v.reason == "sufficient"


def test_single_clause_is_sufficient() -> None:
    v = sc.assess_sufficiency(
        "What does the transparency obligation require?",
        covered_articles={"Art. 13"},
    )
    assert v.sufficient is True


def test_sub_queries_capped(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", "2")
    v = sc.assess_sufficiency(
        "What do Article 9, Article 10, Article 13 and Article 50 require?",
        covered_articles=set(),
    )
    assert len(v.sub_queries) == 2  # capped
    assert len(v.uncovered_anchors) == 4  # full gap list still reported


def test_empty_question_is_sufficient() -> None:
    v = sc.assess_sufficiency("", covered_articles=set())
    assert v.sufficient is True


# ── Audit trace recorder ─────────────────────────────────────────────────


def test_record_sub_query_populates_trace(trace) -> None:
    rt.record_sub_query(
        "Article 50", refs=["Art. 50"], source="kb", reason="uncovered_explicit_refs"
    )
    assert len(trace.sub_queries) == 1
    entry = trace.sub_queries[0]
    assert entry["q"] == "Article 50"
    assert entry["refs"] == ["Art. 50"]
    assert entry["source"] == "kb"
    assert entry["reason"] == "uncovered_explicit_refs"


def test_record_sub_query_noop_without_trace() -> None:
    rt.deactivate()
    # Must not raise when no trace is active (deterministic prod path).
    rt.record_sub_query("Article 50", refs=["Art. 50"])
    assert rt.current() is None


def test_record_sub_query_capped(trace) -> None:
    for i in range(20):
        rt.record_sub_query(f"Article {i + 1}")
    assert len(trace.sub_queries) == 8


def test_sub_queries_serialised(trace) -> None:
    rt.record_sub_query("Article 50", refs=["Art. 50"], source="kb")
    out = trace.to_json_dict()
    assert out["sub_queries"][0]["q"] == "Article 50"


def test_sub_queries_absent_when_empty(trace) -> None:
    out = trace.to_json_dict()
    assert "sub_queries" not in out


# ── Engine helpers: coverage + merge ─────────────────────────────────────


def test_covered_article_keys() -> None:
    ctx = GraphContext(
        obligations=[{"id": "o13", "article": "Art. 13", "text": "x"}],
        article_info=[{"id": "Art. 50", "article": "Article 50"}],
    )
    keys = gr._covered_article_keys(ctx)
    assert keys == {"art13", "art50"}


def test_merge_graph_context_additive_and_dedup() -> None:
    base = GraphContext(
        obligations=[{"id": "o13", "article": "Art. 13", "text": "transparency"}],
        nodes_traversed=3,
        edges_followed=1,
    )
    extra = GraphContext(
        obligations=[
            {"id": "o13", "article": "Art. 13", "text": "dup"},  # dedup
            {"id": "o99", "article": "Art. 99", "text": "penalties"},  # new
        ],
        nodes_traversed=2,
        edges_followed=4,
    )
    added = gr._merge_graph_context(base, extra)
    ids = [o["id"] for o in base.obligations]
    assert ids == ["o13", "o99"]  # first-pass anchor stays at the front
    assert base.obligations[0]["text"] == "transparency"  # dup did not overwrite
    assert "Art. 99" in added
    assert base.nodes_traversed == 5  # 3 + 2
    assert base.edges_followed == 5  # 1 + 4


def test_merge_graph_context_gaps_dedup() -> None:
    base = GraphContext(gaps=[{"obligation_id": "g1"}])
    extra = GraphContext(gaps=[{"obligation_id": "g1"}, {"obligation_id": "g2"}])
    gr._merge_graph_context(base, extra)
    assert [g["obligation_id"] for g in base.gaps] == ["g1", "g2"]


# ── Engine wire: the bounded hop ─────────────────────────────────────────


def test_hop_noop_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("REGENOLD_SUFFICIENT_CONTEXT", raising=False)
    base = GraphContext(obligations=[{"id": "o13", "article": "Art. 13"}])
    req = GraphRAGRequest(question="What do Article 13 and Article 99 require?")
    out = gr._maybe_sufficient_context_hop(
        req, GraphQuery(raw_question=req.question), base, {}
    )
    assert out is base
    assert len(out.obligations) == 1  # no extra hop happened


def test_hop_fetches_uncovered_explicit_ref(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", "1")
    base = GraphContext(
        obligations=[{"id": "o13", "article": "Art. 13", "text": "transparency"}]
    )
    seen: list[list[str]] = []

    def fake_retrieve(query, risk_level=None, answers=None):
        seen.append(list(query.entities))
        return GraphContext(
            obligations=[{"id": "o99", "article": "Art. 99", "text": "penalties"}],
            nodes_traversed=2,
        )

    monkeypatch.setattr(gr, "_retrieve_from_graph", fake_retrieve)
    req = GraphRAGRequest(question="What do Article 13 and Article 99 require?")
    out = gr._maybe_sufficient_context_hop(
        req, gr._deterministic_parse(req.question), base, {}
    )
    # The uncovered Art. 99 sub-query retrieved + merged behind the anchor.
    ids = [o["id"] for o in out.obligations]
    assert ids == ["o13", "o99"]
    assert out.nodes_traversed == 2
    # The sub-query parsed the missing article.
    assert any("99" in "".join(e) for e in seen)
    # Glass-box audit lineage was recorded.
    assert trace.sub_queries
    assert trace.sub_queries[0]["reason"] == "uncovered_explicit_refs"


def test_hop_failsoft_on_retrieval_error(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", "1")
    base = GraphContext(obligations=[{"id": "o13", "article": "Art. 13"}])

    def boom(query, risk_level=None, answers=None):
        raise RuntimeError("graph down")

    monkeypatch.setattr(gr, "_retrieve_from_graph", boom)
    req = GraphRAGRequest(question="What do Article 13 and Article 50 require?")
    # Must return the first-pass context unmodified, never raise.
    out = gr._maybe_sufficient_context_hop(
        req, gr._deterministic_parse(req.question), base, {}
    )
    assert len(out.obligations) == 1


# ── End-to-end + cache key ───────────────────────────────────────────────


def test_engine_end_to_end_with_gate_on(monkeypatch) -> None:
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")  # deterministic only
    res = ask_compliance_question_e2e(
        "What do Article 13 and Article 99 require for high-risk AI?"
    )
    assert res.answer.strip()
    assert res.confidence >= 0.0


def ask_compliance_question_e2e(question: str):
    from app.engines.graph_rag import ask_compliance_question
    return ask_compliance_question(GraphRAGRequest(question=question))


def test_engine_gate_off_is_noop_e2e(monkeypatch) -> None:
    # With the gate OFF, the engine output is the normal deterministic path —
    # this is the davidath byte-identity guarantee in miniature.
    monkeypatch.delenv("REGENOLD_SUFFICIENT_CONTEXT", raising=False)
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")
    a = ask_compliance_question_e2e("What does Article 13 require?")
    b = ask_compliance_question_e2e("What does Article 13 require?")
    assert a.answer == b.answer
    assert [c.node_id for c in a.citations] == [c.node_id for c in b.citations]


def test_cache_key_includes_flag(monkeypatch) -> None:
    from app.routes.regenold import _engine_cache_key

    monkeypatch.delenv("REGENOLD_SUFFICIENT_CONTEXT", raising=False)
    k_off = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", "1")
    k_on = _engine_cache_key("q", None)
    assert k_off != k_on


def test_cache_key_includes_max_hops(monkeypatch) -> None:
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT", "1")
    monkeypatch.delenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", raising=False)
    k_default = _engine_cache_key("q", None)
    monkeypatch.setenv("REGENOLD_SUFFICIENT_CONTEXT_MAX_HOPS", "5")
    k_five = _engine_cache_key("q", None)
    assert k_default != k_five
