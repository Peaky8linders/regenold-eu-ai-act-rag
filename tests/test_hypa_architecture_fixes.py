"""Unit tests validating HyPA-RAG, Neo4j Aura KG, Deontic Ontology, and Vector Recall fixes."""
import os
os.environ['NEO4J_AUTO_SEED'] = '0'

from app.engines.hybrid_rrf_retriever import (
    canonicalize_article_ref,
    canonicalize_to_internal_ref,
    extract_provision_head,
    fuse_sparse_dense_candidates,
    is_valid_article_ref,
    reciprocal_rank_fusion,
)
from app.engines.query_complexity_router import (
    CLASS_2_PARAMS,
    classify_query_complexity,
)
from app.data.ontology import ActorRole, RiskClass, obligations_for
from app.engines.scenario_classifier import _build_article_pack
from app.engines.kg_context import fetch_cross_regulatory_context
from app.engines.vector_recall import recall_articles_with_provenance


def test_vector_recall_provenance_symbol_exists():
    """Verify recall_articles_with_provenance symbol is exported and callable."""
    assert callable(recall_articles_with_provenance)


def test_arabic_annex_mapping_in_hybrid_rrf():
    """Verify Arabic Annex numbers map to Roman numerals in hybrid_rrf_retriever."""
    assert canonicalize_article_ref("Annex 3") == "Annex III"
    assert canonicalize_article_ref("Annex 4.2.a") == "Annex IV.2.a"
    assert is_valid_article_ref("Annex 3") is True
    assert canonicalize_to_internal_ref("Annex 3") == "Annex III"


def test_hyphenated_subpoint_regex_in_hybrid_rrf():
    """Verify hyphenated subpoints are parsed correctly."""
    assert canonicalize_article_ref("Article 5.1-a") == "Article 5.1-a"
    assert is_valid_article_ref("Article 5.1-a") is True


def test_canonicalize_to_internal_ref():
    """Verify conversion of wire format 'Article N' to internal KB format 'Art. N'."""
    assert canonicalize_to_internal_ref("Article 5") == "Art. 5"
    assert canonicalize_to_internal_ref("Article 10.1") == "Art. 10"
    assert canonicalize_to_internal_ref("Annex III") == "Annex III"


def test_extract_provision_head():
    """Verify provision head extraction for subpoint citations."""
    assert extract_provision_head("Article 13(1)") == "Article 13"
    assert extract_provision_head("Annex III.5.a") == "Annex III"


def test_rrf_head_collapsing():
    """Verify subpoints aggregate ranks at provision head level in RRF fusion."""
    ranked = [["Article 13(1)", "Article 13.2", "Article 5"], ["Article 13", "Article 26"]]
    fused = reciprocal_rank_fusion(ranked, collapse_to_head=True)
    heads = [item[0] for item in fused]
    assert "Article 13" in heads
    assert "Article 5" in heads
    assert "Article 26" in heads
    # Article 13 should be top ranked due to combined subpoint hits
    assert heads[0] == "Article 13"


def test_query_complexity_router_article5_and_penalty_queries():
    """Verify Article 5 and Article 99 penalty queries map to Class 2 (Complex)."""
    p_art5 = classify_query_complexity("What does Article 5 say about prohibited AI?")
    assert p_art5.complexity_class == 2

    p_fine = classify_query_complexity("What are the fines and penalties under Article 99?")
    assert p_fine.complexity_class == 2


def test_ontology_obligations_for_string_resolution():
    """Verify obligations_for handles string risk levels emitted by scenario_classifier."""
    obs_hi = obligations_for("provider", "high-risk")
    assert "Art. 16" in obs_hi
    assert "Art. 73" in obs_hi  # Serious incident reporting

    obs_annex3 = obligations_for("deployer", "high_risk_annex_iii")
    assert "Art. 27" in obs_annex3

    obs_annex1 = obligations_for("deployer", "high_risk_annex_i")
    assert "Art. 27" not in obs_annex1
    assert "Art. 26" in obs_annex1


def test_scenario_classifier_annex1_fria_exclusion():
    """Verify high-risk-annex-i deployers are excluded from Art. 27 (FRIA)."""
    pack = _build_article_pack("deployer", "high-risk-annex-i")
    assert "Art. 26" in pack
    assert "Art. 27" not in pack


def test_kg_context_mdr_ivdr_cross_regulatory_linkages():
    """Verify fetch_cross_regulatory_context includes MDR/IVDR for Article 6(1) / Annex I."""
    ctx = fetch_cross_regulatory_context(["Article 6", "Annex I"])
    frameworks = [item["framework"] for item in ctx]
    assert "MDR_IVDR" in frameworks
