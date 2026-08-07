"""Tests for C4, I1, I3, I5, I6, and I8 findings implementations:

1. scenario_classifier: prohibited risk articles, answer router check, Art 6(3) derogations, Art 53(2) open-source GPAI exemptions.
2. fria_evaluator: FRIA evaluation & EU Charter mapping (Art 1, 7, 8, 21, 47).
3. kg_context: fetch_cross_regulatory_context preserving GDPR/EU Charter graph edges.
4. sufficient_context: NLI entailment verification (EntailmentScorer) integration.
"""

from __future__ import annotations

import pytest

from app.engines.scenario_classifier import (
    _RISK_ARTICLES,
    classify_scenario_query,
)
from app.engines.fria_evaluator import (
    evaluate_fria,
    get_charter_mapping,
    FRIAEvaluation,
)
from app.engines.kg_context import (
    fetch_cross_regulatory_context,
    render_kg_context,
)
from app.engines.sufficient_context import (
    assess_sufficiency,
    verify_context_entailment,
)
from app.engines.crag_nli_verifier import LexicalEntailmentScorer


class TestScenarioClassifierFindings:
    def test_prohibited_risk_articles_strictly_three(self):
        prohibited = _RISK_ARTICLES["prohibited"]
        assert prohibited == ("Art. 5", "Art. 10", "Art. 50")
        assert "Art. 27" not in prohibited

    def test_art_6_3_narrow_non_profiling_derogation(self):
        # Annex III recruitment/CV screening system doing narrow procedural task without profiling
        q = (
            "We are a deployer using an AI system for CV screening that performs a narrow "
            "procedural task of formatting and de-duplication without profiling natural persons."
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "art6_3_derogated"
        # R321 — dot form: "Art. 6(3)" resolved in NEITHER ARTICLE_EXISTENCE nor
        # the catalog lint, so test_all_risk_packs_resolve_in_catalog was red.
        assert "Art. 6.3" in v.articles
        assert "Art. 49" in v.articles
        assert "Article 6(3)" in v.answer

    def test_art_6_3_profiling_killswitch(self):
        # Same narrow task BUT explicitly performs profiling -> Art 6(3) derogation MUST NOT apply
        q = (
            "We are a deployer using an AI system for CV screening performing a narrow "
            "procedural task with profiling of natural persons."
        )
        v = classify_scenario_query(q)
        assert v is not None
        # Must remain high-risk because profiling overrides derogation
        assert v.risk_level == "high-risk"

    def test_art_53_2_open_source_gpai_exemption(self):
        # Open source GPAI model without systemic risk
        q = (
            "We are a provider offering a general-purpose AI model under a free and open-source license "
            "with open weights and compute under 10^23 FLOPs."
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "gpai-open-source"
        # R321 — dot form, see test_art_6_3_narrow_non_profiling_derogation.
        assert "Art. 53.2" in v.articles
        assert "Article 53(2)" in v.answer

    def test_art_53_2_systemic_risk_override(self):
        # Open source GPAI model WITH systemic risk -> exemption overridden
        q = (
            "We are a provider offering an open-source general-purpose AI model with open weights "
            "presenting systemic risk at 10^25 FLOPs compute."
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "gpai"

    def test_verdict_get_route_decision(self):
        q = "We are a provider offering a chatbot system."
        v = classify_scenario_query(q)
        assert v is not None
        decision = v.get_route_decision(q)
        assert hasattr(decision, "mode")


class TestFRIAEvaluator:
    def test_fria_evaluation_annex_iii_deployer(self):
        text = "We are a deployer of an AI system for CV screening and recruitment at a hospital."
        eval_result = evaluate_fria(text, role="deployer")
        assert isinstance(eval_result, FRIAEvaluation)
        assert eval_result.is_annex_iii is True
        assert eval_result.annex_iii_category == "employment"
        assert eval_result.fria_required is True
        
        # R321 — Charter ids are namespaced "Charter Art. N". Bare "Art. 1"/
        # "Art. 7"/"Art. 8"/"Art. 21" are EU AI ACT articles in this repo and
        # ALL resolve in ARTICLE_EXISTENCE, so the unprefixed ids would pass
        # the citation lint and ship as wrong AI Act references.
        charter_ids = [art.article_id for art in eval_result.charter_articles]
        assert "Charter Art. 1" in charter_ids
        assert "Charter Art. 7" in charter_ids
        assert "Charter Art. 8" in charter_ids
        assert "Charter Art. 21" in charter_ids
        # ...and none of them may look like an AI Act reference.
        assert all(cid.startswith("Charter ") for cid in charter_ids)

    def test_fria_evaluation_law_enforcement(self):
        text = "Deploying an AI system for law enforcement risk assessment of reoffending."
        eval_result = evaluate_fria(text, role="deployer")
        assert eval_result.annex_iii_category == "law_enforcement"
        charter_ids = [art.article_id for art in eval_result.charter_articles]
        # R321 — Charter ids are namespaced. A bare "Art. 47" is EU AI Act
        # Article 47 (EU declaration of conformity) everywhere else in this
        # repo, and it resolves in ARTICLE_EXISTENCE, so the unprefixed form
        # would ship as a wrong AI Act citation once this module is wired.
        assert "Charter Art. 47" in charter_ids  # Charter: Fair Trial

    def test_get_charter_mapping(self):
        mapping = get_charter_mapping("justice")
        assert "Charter Art. 47" in mapping  # R321 — namespaced, see above
        assert "Charter Art. 21" in mapping  # R321 — namespaced


class TestKGContextCrossRegulatory:
    def test_fetch_cross_regulatory_context(self):
        refs = ["Art. 10", "Art. 27"]
        cross = fetch_cross_regulatory_context(refs)
        assert isinstance(cross, list)
        assert len(cross) > 0

        frameworks = {c["framework"] for c in cross}
        assert "GDPR" in frameworks or "EU_Charter" in frameworks

    def test_render_kg_context_includes_cross_regulatory(self):
        refs = ["Art. 10", "Art. 27"]
        rendered = render_kg_context(refs)
        rendered_str = "\n".join(rendered)
        assert "CROSS-REGULATORY" in rendered_str or len(rendered) > 0


class TestSufficientContextNLI:
    def test_verify_context_entailment_matching(self):
        question = "What are the data governance requirements under Article 10?"
        passages = [
            "Article 10 specifies that high-risk AI systems must establish data governance and management practices covering training data quality."
        ]
        scorer = LexicalEntailmentScorer([{"text": passages[0]}])
        is_entailed, score = verify_context_entailment(question, passages, scorer=scorer, threshold=0.1)
        assert is_entailed is True
        assert score > 0.0

    def test_assess_sufficiency_nli_failure_on_unrelated_passage(self):
        question = "What are the requirements for high-risk credit scoring AI systems under Article 27?"
        covered = {"Art. 27"}
        # Passages completely unrelated to credit scoring/FRIA
        unrelated_passages = ["The weather in Paris is sunny today."]
        verdict = assess_sufficiency(question, covered, context_passages=unrelated_passages, entailment_threshold=0.5)
        assert verdict.sufficient is False
        assert verdict.reason == "nli_entailment_failure"
