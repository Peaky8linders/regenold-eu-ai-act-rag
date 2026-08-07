"""Unit tests validating CR_Skill Critical Issue Fixes ([C1] through [C5])."""
import pytest

from evals.bench.metrics import (
    reference_correctness_exact_strict,
    reference_correctness_hierarchical,
)
from app.engines.query_expansion import strip_citation_bias
from app.engines.retrieval_stack import TfidfRetriever
from app.engines.scenario_classifier import _RISK_ARTICLES
from app.models import RiskLevel
from app.data.role_obligations import normalize_role_id, get_role_obligation


def test_c1_reference_correctness_exact_and_hierarchical():
    # Exact sub-clause matching
    pred = ["Article 5(1)(a)", "Article 10"]
    gold = ["Article 5(1)(a)", "Article 10"]
    assert reference_correctness_exact_strict(pred, gold) == 1.0

    # Sub-clause mismatch
    pred_mismatch = ["Article 5(1)(h)"]
    gold_target = ["Article 5(1)(a)"]
    assert reference_correctness_exact_strict(pred_mismatch, gold_target) == 0.0

    # Hierarchical matching gives partial credit for macro-head match
    hierarchical_score = reference_correctness_hierarchical(pred_mismatch, gold_target)
    assert 0.0 < hierarchical_score < 1.0


def test_c2_strip_citation_bias():
    hypothetical_text = "Pursuant to Article 112 and Annex III, high-risk AI systems must implement logging."
    cleaned = strip_citation_bias(hypothetical_text)
    assert "112" not in cleaned
    assert "Annex III" not in cleaned
    assert "high-risk AI systems must implement logging" in cleaned


def test_c3_role_aware_retrieval_boosting():
    provisions = [
        {"provision_id": "article_16", "text": "Provider obligations for high-risk AI systems quality management."},
        {"provision_id": "article_26", "text": "Deployer obligations for high-risk AI systems operational monitoring."},
    ]
    retriever = TfidfRetriever(provisions)
    
    # Search without role
    base_results = retriever.search_scored("high-risk AI systems obligations", k=2)
    assert len(base_results) == 2

    # Search with provider role -> article_16 boosted
    provider_results = retriever.search_scored("high-risk AI systems obligations", k=2, role="provider")
    assert provider_results[0][0] == "article_16"

    # Search with deployer role -> article_26 boosted
    deployer_results = retriever.search_scored("high-risk AI systems obligations", k=2, role="deployer")
    assert deployer_results[0][0] == "article_26"


def test_c4_prohibited_risk_articles_exclusion_of_art27():
    prohibited_articles = _RISK_ARTICLES.get("prohibited", ())
    assert "Art. 27" not in prohibited_articles
    assert "Art. 5" in prohibited_articles


def test_c5_models_risk_level_and_role_spelling_normalization():
    # RiskLevel enum harmonization
    assert RiskLevel.PROHIBITED.value == "prohibited"
    assert RiskLevel.HIGH_RISK_ANNEX_I.value == "high_risk_annex_i"
    assert RiskLevel.HIGH_RISK_ANNEX_III.value == "high_risk_annex_iii"

    # Role spelling normalization
    assert normalize_role_id("authorized_representative") == "authorized_representative"
    assert normalize_role_id("authorised_representative") == "authorized_representative"
    assert get_role_obligation("authorised_representative") is not None
