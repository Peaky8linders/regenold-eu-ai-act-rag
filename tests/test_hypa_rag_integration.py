"""End-to-end integration tests for HyPA-RAG SOTA components in EU AI Act RAG."""
from __future__ import annotations

from app.engines._graph_rag_impl import ask_compliance_question
from app.engines.hybrid_rrf_retriever import (
    fuse_sparse_dense_candidates,
)
from app.engines.query_complexity_router import (
    CLASS_0_PARAMS,
    CLASS_1_PARAMS,
    CLASS_2_PARAMS,
    classify_query_complexity,
)
from app.models import GraphRAGRequest
from app.routes.regenold import _engine_cache_key


def test_hypa_adaptive_router_classification():
    # Class 0 (Simple definition)
    p0 = classify_query_complexity("What is a provider?")
    assert p0 == CLASS_0_PARAMS
    assert p0.top_k_dense == 3
    assert p0.kg_depth == 1

    # Class 1 (Standard compliance)
    p1 = classify_query_complexity("What are the technical documentation requirements for high-risk AI?")
    assert p1 == CLASS_1_PARAMS
    assert p1.top_k_dense == 5
    assert p1.kg_depth == 2

    # Class 2 (Complex / Situational)
    p2 = classify_query_complexity(
        "Are we a provider or deployer if we significantly configure a third party medical model under Article 25?"
    )
    assert p2 == CLASS_2_PARAMS
    # R329 — 7, not 10: 10 came from the paper's 2-class table (Table 5),
    # while this router implements the 3-class mapping (Tables 5/6).
    assert p2.top_k_dense == 7
    assert p2.kg_depth == 3


def test_hypa_hybrid_rrf_retrieval_and_validation():
    bm25_hits = ["Art. 11", "Art. 13", "Art. 17"]
    vector_hits = ["Art. 13", "Art. 26", "Annex III"]
    role_seed_hits = ["Art. 16"]

    fused = fuse_sparse_dense_candidates(
        bm25_hits, vector_hits, role_seed_refs=role_seed_hits, top_k=6
    )

    assert len(fused) <= 6
    # Output MUST be canonicalized (Article 13, not Art. 13)
    assert "Article 13" in fused
    assert "Article 16" in fused
    assert "Annex III" in fused


def test_engine_cache_key_includes_hypa_flags(monkeypatch):
    monkeypatch.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")
    monkeypatch.setenv("REGENOLD_HYPA_RRF_RETRIEVAL", "1")
    key1 = _engine_cache_key("What is a provider?", None)

    monkeypatch.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "0")
    key2 = _engine_cache_key("What is a provider?", None)

    assert key1 != key2, "Cache key must reflect HyPA adaptive router flag state"


def test_ask_compliance_question_hypa_end_to_end_integration(monkeypatch):
    """Real end-to-end execution of ask_compliance_question with HyPA adaptive router and RRF active."""
    monkeypatch.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")
    monkeypatch.setenv("REGENOLD_HYPA_RRF_RETRIEVAL", "1")

    req = GraphRAGRequest(question="What transparency information must providers give to deployers under Article 13?")
    resp = ask_compliance_question(req)

    assert resp is not None
    assert hasattr(resp, "answer")
    assert hasattr(resp, "citations")

    # R329 — this assertion previously read ``c.article if hasattr(c, "article")``.
    # ``CitationNode`` has no ``article`` field (only ``article_ref``), so the
    # hasattr guard was always False and the check degraded to substring-matching
    # "13" against the FULL stringified citation — it would pass on an incidental
    # "13" anywhere in unrelated obligation prose. Scope it to the reference field.
    refs = [c.article_ref for c in resp.citations]
    assert any(r == "Art. 13" or r.startswith("Art. 13.") for r in refs), refs

    # R329 — the real invariant: for a question that already carries an explicit
    # anchor, the BM25/RRF fallback must not fire, so enabling HyPA must be a
    # NO-OP on the citation set. (Art. 26 / Art. 50 here come from ordinary
    # retrieval, not from HyPA — asserting "Art. 13 only" would wrongly fail.)
    # Before the `not query.entities` gate this widened 2x-15x on anchored
    # questions; the parity check pins that regression directly.
    monkeypatch.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "0")
    monkeypatch.setenv("REGENOLD_HYPA_RRF_RETRIEVAL", "0")
    refs_off = [c.article_ref for c in ask_compliance_question(
        GraphRAGRequest(question=req.question)
    ).citations]
    assert refs == refs_off, (
        f"HyPA changed an anchored question's citations: on={refs} off={refs_off}"
    )
