"""Unit tests validating C2, C3, I2, and I7 findings implementation."""

from unittest.mock import MagicMock, patch

import pytest

from app.engines.query_expansion import (
    generate_hyde_document,
    strip_citation_bias,
)
from app.engines.retrieval_stack import (
    ExternalEmbeddingRetriever,
    LsaRetriever,
    TfidfRetriever,
)
from app.engines import embeddings_index as ei


# ── C2: Legal HyDE Document Generation & Citation Stripping ───────────────


def test_generate_hyde_document_empty_input():
    assert generate_hyde_document("") == ""
    assert generate_hyde_document("   ") == ""


@patch("app.engines.query_expansion.is_openai_wrapper_enabled", return_value=False)
def test_generate_hyde_document_disabled_wrapper(mock_enabled):
    assert generate_hyde_document("What are provider obligations?") == ""


@patch("app.engines.query_expansion.is_openai_wrapper_enabled", return_value=True)
@patch("app.engines.query_expansion.get_openai_wrapper_provider")
def test_generate_hyde_document_strips_citations(mock_get_provider, mock_enabled):
    mock_provider = MagicMock()
    mock_resp = MagicMock()
    mock_resp.error = None
    mock_resp.text = "Pursuant to Article 112 and Annex III, high-risk AI system providers must maintain logging."
    mock_provider.complete.return_value = mock_resp
    mock_get_provider.return_value = mock_provider

    res = generate_hyde_document("What logging is required for high-risk AI?")
    assert "112" not in res
    assert "Annex III" not in res
    assert "high-risk AI system providers must maintain logging" in res


# ── C3 & I7: Role-Aware Retrieval & Dynamic Top-K Retrieval ────────────────


def test_retriever_role_forwarding_and_boosting():
    provisions = [
        {"provision_id": "article_16", "text": "Provider obligations for high-risk AI system compliance."},
        {"provision_id": "article_23", "text": "Importer obligations for high-risk AI system compliance."},
        {"provision_id": "article_24", "text": "Distributor obligations for high-risk AI system compliance."},
        {"provision_id": "article_26", "text": "Deployer obligations for high-risk AI system compliance."},
    ]

    # Test TfidfRetriever
    tfidf = TfidfRetriever(provisions)

    provider_res = tfidf.search("high-risk AI obligations", k=4, role="provider")
    assert provider_res[0] == "article_16"

    deployer_res = tfidf.search("high-risk AI obligations", k=4, role="deployer")
    assert deployer_res[0] == "article_26"

    importer_res = tfidf.search("high-risk AI obligations", k=4, role="importer")
    assert importer_res[0] == "article_23"

    distributor_res = tfidf.search("high-risk AI obligations", k=4, role="distributor")
    assert distributor_res[0] == "article_24"

    # Test ExternalEmbeddingRetriever with dense embeddings and role boosting
    ext_retriever = ExternalEmbeddingRetriever(provisions, embed_fn=lambda texts: [[1.0, 0.0] for _ in texts])
    ext_retriever._doc_embeddings = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    ext_res = ext_retriever.search("high-risk AI obligations", k=2, role="deployer")
    assert len(ext_res) == 2
    assert ext_res[0] == "article_26"


def test_lsa_retriever_role_forwarding():
    provisions = [
        {"provision_id": "article_16", "text": "Provider obligations for high-risk AI quality systems."},
        {"provision_id": "article_26", "text": "Deployer obligations for high-risk AI operational monitoring."},
    ]
    lsa = LsaRetriever(provisions, n_components=2)
    res = lsa.search_scored("high-risk AI obligations", k=2, role="deployer")
    assert len(res) <= 2
    assert isinstance(res, list)


def test_external_embedding_retriever_custom_embed_fn():
    provisions = [
        {"provision_id": "article_16", "text": "Provider obligations"},
        {"provision_id": "article_26", "text": "Deployer obligations"},
    ]

    def dummy_embed(texts):
        return [[1.0, 0.0] for _ in texts]

    retriever = ExternalEmbeddingRetriever(provisions, embed_fn=dummy_embed)
    retriever._doc_embeddings = [[1.0, 0.0], [0.8, 0.2]]

    res = retriever.search("provider requirements", k=2, role="provider")
    assert len(res) == 2
    assert res[0] == "article_16"


# ── I2: Layer Metadata Filtering in Embeddings Index ──────────────────────


@pytest.mark.skipif(not ei.is_available(), reason="embedding assets not built")
def test_embeddings_index_layer_filtering():
    # Query with default layer (all layers or layer_1_binding)
    hits_all = ei.query("biometric identification", top_k=10)
    assert hits_all
    assert all(hasattr(h, "layer") for h in hits_all)
    assert all(h.layer in ("layer_1_binding", "layer_2_standards", "layer_3_soft_law", "layer_4_rights") for h in hits_all)

    # Query with specific layer
    hits_binding = ei.query("biometric identification", top_k=10, layer="layer_1_binding")
    assert all(h.layer == "layer_1_binding" for h in hits_binding)

    # Filtering for a non-existent layer returns empty list
    hits_none = ei.query("biometric identification", top_k=10, layer="layer_99_nonexistent")
    assert hits_none == []
