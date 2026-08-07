"""Unit tests validating the I2 / I7 findings that survive R322.

The C2 (HyDE) and C3 (role-boosting) tests were removed with the dead code
they covered — see ``tests/test_cr_critical_fixes.py`` for the rationale.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.engines.retrieval_stack import (
    ExternalEmbeddingRetriever,
    LsaRetriever,
    TfidfRetriever,
)
from app.engines import embeddings_index as ei


# ── C3 & I7: Role-Aware Retrieval & Dynamic Top-K Retrieval ────────────────


def test_external_embedding_retriever_custom_embed_fn():
    provisions = [
        {"provision_id": "article_16", "text": "Provider obligations"},
        {"provision_id": "article_26", "text": "Deployer obligations"},
    ]

    def dummy_embed(texts):
        return [[1.0, 0.0] for _ in texts]

    retriever = ExternalEmbeddingRetriever(provisions, embed_fn=dummy_embed)
    retriever._doc_embeddings = [[1.0, 0.0], [0.8, 0.2]]

    res = retriever.search("provider requirements", k=2)
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
