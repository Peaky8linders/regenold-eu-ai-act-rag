import os

os.environ['NEO4J_AUTO_SEED'] = '0'

from types import SimpleNamespace

from app.engines import vector_recall


def test_recall_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAPH_VECTOR_RECALL", raising=False)
    assert vector_recall.recall_articles("What are the prohibited practices?") == []

def test_is_enabled_gate(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAPH_VECTOR_RECALL", raising=False)
    assert vector_recall.is_enabled() is False

    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    assert vector_recall.is_enabled() is True

def test_recall_enabled_returns_articles(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    res = vector_recall.recall_articles("What are the prohibited practices?")
    assert isinstance(res, list)
    assert len(res) > 0

def test_recall_respects_min_sim(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    monkeypatch.setenv("REGENOLD_VECTOR_MIN_SIM", "0.99")
    res = vector_recall.recall_articles("What are the prohibited practices?")
    assert res == []


def test_arabic_annex_normalization_is_bounded_to_official_range():
    assert vector_recall._norm_ref("Annex 4") == "Annex IV"
    assert vector_recall._norm_ref("annex_13") == "Annex XIII"
    assert vector_recall._norm_ref("Annex 4.2.c") == "Annex IV"
    assert vector_recall._norm_ref("Annex 0") == "Annex 0"
    assert vector_recall._norm_ref("annex_14") == "annex_14"


def test_invalid_native_hits_trigger_valid_local_fallback(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    monkeypatch.setattr(
        vector_recall,
        "_query_neo4j_vector_index",
        lambda *_a, **_kw: [
            vector_recall.RecallHit("article_999", 0.99, "neo4j:v_article_embedding")
        ],
    )
    monkeypatch.setattr(
        "app.engines.embeddings_index.query",
        lambda *_a, **_kw: [SimpleNamespace(article_ref="article_5", similarity=0.8)],
    )

    hits = vector_recall.recall_articles_with_provenance("synthetic", top_k=2)

    assert hits == [vector_recall.RecallHit("Art. 5", 0.8, "local:svd_sentence")]


def test_native_provenance_and_best_score_are_preserved(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    monkeypatch.setattr(
        vector_recall,
        "_query_neo4j_vector_index",
        lambda *_a, **_kw: [
            vector_recall.RecallHit("article_6", 0.7, "neo4j:v_article_embedding"),
            vector_recall.RecallHit("Art. 6", 0.9, "neo4j:v_article_embedding"),
            vector_recall.RecallHit("annex_III", 0.8, "neo4j:v_annex_embedding"),
        ],
    )

    hits = vector_recall.recall_articles_with_provenance("synthetic", top_k=2)

    assert hits == [
        vector_recall.RecallHit("Art. 6", 0.9, "neo4j:v_article_embedding"),
        vector_recall.RecallHit("Annex III", 0.8, "neo4j:v_annex_embedding"),
    ]


def test_native_queries_both_indexes_with_dedup_headroom(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.graph.client.get_graph_client",
        lambda: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(
        "app.engines.embeddings_index._embed_query",
        lambda _q: [0.1, 0.2],
    )

    def _read(cypher, params):
        calls.append((cypher, params))
        return []

    monkeypatch.setattr("app.engines.kg_context._bounded_execute_read", _read)

    assert vector_recall._query_neo4j_vector_index("q", 3, 0.35) == []
    assert len(calls) == 2
    assert {"v_article_embedding", "v_annex_embedding"} == {
        "v_article_embedding" if "v_article_embedding" in cypher else "v_annex_embedding"
        for cypher, _params in calls
    }
    assert all(params["k"] == 6 for _cypher, params in calls)


def test_parse_reserves_vector_lane_after_full_bm25(monkeypatch):
    import app.engines._graph_rag_impl as graph_rag
    import app.integrations.regenold.reasoning_trace as reasoning_trace

    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    notes = []
    bm25 = [f"Art. {n}" for n in range(70, 78)]
    monkeypatch.setattr(graph_rag, "candidate_chapters_for_query", lambda *_a, **_kw: [])
    monkeypatch.setattr(graph_rag, "top_articles_by_relevance", lambda *_a, **_kw: bm25)
    monkeypatch.setattr(vector_recall, "is_enabled", lambda: True)
    monkeypatch.setattr(reasoning_trace, "record_note", notes.append)
    monkeypatch.setattr(
        vector_recall,
        "recall_articles_with_provenance",
        lambda *_a, **_kw: [
            vector_recall.RecallHit("Art. 5", 0.8, "local:svd_sentence"),
            vector_recall.RecallHit("Annex III", 0.7, "local:svd_sentence"),
        ],
    )

    parsed = graph_rag._deterministic_parse("r326 synthetic semantic probe zyx")

    assert parsed.entities == bm25 + ["Art. 5", "Annex III"]
    assert notes == ["vector_recall source=svd added=2"]


def test_parse_skips_vector_expansion_for_exact_anchor(monkeypatch):
    import app.engines._graph_rag_impl as graph_rag

    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    monkeypatch.setattr(vector_recall, "is_enabled", lambda: True)

    def _unexpected(*_a, **_kw):
        raise AssertionError("exact provision anchor must not invoke vector recall")

    monkeypatch.setattr(vector_recall, "recall_articles_with_provenance", _unexpected)
    assert graph_rag._deterministic_parse("What does Article 13 require?").entities[0] == "Art. 13"
