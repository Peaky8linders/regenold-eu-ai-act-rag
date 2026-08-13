"""Unit tests for app/engines/hybrid_rrf_retriever.py."""
from __future__ import annotations

import pytest

from app.engines.hybrid_rrf_retriever import (
    canonicalize_article_ref,
    fuse_sparse_dense_candidates,
    is_valid_article_ref,
    reciprocal_rank_fusion,
)


def test_canonicalize_article_ref():
    assert canonicalize_article_ref("Art. 13") == "Article 13"
    assert canonicalize_article_ref("Article 13") == "Article 13"
    assert canonicalize_article_ref("Annex iii") == "Annex III"
    assert canonicalize_article_ref("Art. 27.1") == "Article 27.1"
    assert canonicalize_article_ref("Art. 999") == "Art. 999"


def test_is_valid_article_ref_strict_bounds():
    assert is_valid_article_ref("Article 13") is True
    assert is_valid_article_ref("Art. 13") is True
    assert is_valid_article_ref("Annex III") is True
    assert is_valid_article_ref("Article 13 random prose text") is False
    assert is_valid_article_ref("Art. 999") is False
    assert is_valid_article_ref("") is False


def test_reciprocal_rank_fusion_alias_canonicalization():
    bm25 = ["Art. 13", "Article 26"]
    vector = ["Article 13", "Art. 26"]
    fused = reciprocal_rank_fusion([bm25, vector])
    refs = [ref for ref, score in fused]

    # Both Art. 13 and Article 13 canonicalize to Article 13 and fuse into rank 1
    assert refs[0] == "Article 13"
    assert refs[1] == "Article 26"


def test_reciprocal_rank_fusion_invalid_k_constant():
    with pytest.raises(ValueError, match="k_constant must be positive"):
        reciprocal_rank_fusion([["Article 13"]], k_constant=0)


def test_fuse_sparse_dense_candidates_canonical_output():
    bm25 = ["Art. 13", "Art. 999", "Annex III"]
    vector = ["Art. 26", "Article 13", "Art. 5"]

    fused = fuse_sparse_dense_candidates(bm25, vector, top_k=5)

    # Output must be canonicalized and invalid references removed
    assert "Art. 999" not in fused
    assert "Article 13" in fused
    assert "Annex III" in fused
    assert "Article 26" in fused
    assert "Article 5" in fused


def test_fuse_sparse_dense_boundary_top_k():
    assert fuse_sparse_dense_candidates(["Article 13"], ["Article 26"], top_k=0) == []
    assert fuse_sparse_dense_candidates(["Article 13"], ["Article 26"], top_k=-5) == []
