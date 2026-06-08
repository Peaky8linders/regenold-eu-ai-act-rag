"""Round 109 — answer-quality fixes (reviewer-feedback driven).

Regression guards for the four anti-patterns an expert legal reviewer
flagged on three live answers (Q1 risk categories / Q2 prohibited
practices / Q3 high-risk definition):

  A. Factual error  — social scoring wrongly scoped to "public
     authorities" (a draft-only limitation removed from the final
     Regulation 2024/1689).
  B. Incomplete enumeration of a closed statutory set when the question
     asks for the set itself (3 of 8 prohibitions; 5 of 8).
  C. Over-focus on the prohibited tier when asked about the whole risk
     framework (GPAI Art. 51-55 + the high-risk dual route omitted).
  E. Material omission of load-bearing high-risk conditions/carve-outs
     (Art. 6(1)(b) third-party conformity assessment; Art. 6(3)
     derogation + Art. 49(2) registration).

Most fixes live on the Stage-2 prompt (live-only, davidath-neutral) and
the deterministic describers (verified to fire on 0 davidath rows). The
Art. 6 KB stub enrichment is bench-affecting (and intended bench-positive
on the 2 Article-6 gold rows).
"""

from __future__ import annotations

import inspect

import pytest

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.article_requirements_full import ARTICLE_REQUIREMENTS
from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM
from app.data.kb import EC_CHECKER_OBLIGATION_MAP, KB_VERSION
from app.engines import graph_rag
from app.engines.prohibited_gatekeeper import _PRACTICE_VERDICT_CLAUSE
from app.integrations.regenold.grounded_prose import _ART_CONDITIONAL_DESCRIBERS
from app.integrations.regenold.tone_guard import enforce_tone


def _topic(name: str) -> dict:
    for topic in graph_rag._CLASSIFICATION_TOPICS:
        if topic["name"] == name:
            return topic
    raise AssertionError(f"_CLASSIFICATION_TOPICS has no topic named {name!r}")


# ─────────────────────────── Anti-pattern A ────────────────────────────


class TestR109SocialScoringFactualError:
    def test_social_scoring_describer_drops_public_authority_limitation(self):
        answer = _topic("social_scoring")["answer"].lower()
        # The final Art. 5(1)(c) binds ANY provider/deployer.
        assert "any provider or deployer" in answer
        # It must NOT scope the prohibition to public authorities.
        assert "by public authorities" not in answer
        assert "public authorities or on their behalf" not in answer
        # Still anchored on Article 5(1)(c).
        assert "article 5(1)(c)" in answer

    def test_article_requirements_5_1_c_drops_public_authority_limitation(self):
        text = ARTICLE_REQUIREMENTS["Art. 5"]["paragraphs"]["5(1)(c)"]["text"].lower()
        assert "by public authorities" not in text
        assert "any provider or deployer" in text

    def test_social_scoring_describer_has_no_dash_separator_or_ellipsis(self):
        # R108 legal-tone rule: no em/en dash separators, no ellipsis.
        answer = _topic("social_scoring")["answer"]
        assert "—" not in answer  # em dash
        assert "–" not in answer  # en dash
        assert "…" not in answer  # ellipsis
        assert "..." not in answer


# ─────────────────────────── Anti-pattern C ────────────────────────────


class TestR109RiskFrameworkOverview:
    def test_names_all_four_tiers_plus_gpai(self):
        answer = _topic("risk_framework_overview")["answer"].lower()
        # all four tiers present
        for token in ("prohibited", "high-risk", "limited-risk", "minimal-risk"):
            assert token in answer, f"risk framework missing tier label {token!r}"
        # parallel GPAI regime
        assert "general-purpose ai" in answer
        assert "articles 51 to 55" in answer
        # high-risk dual route surfaced
        assert "annex i" in answer
        assert "annex iii" in answer
        assert "article 6" in answer

    def test_refs_cover_the_framework_and_resolve(self):
        refs = _topic("risk_framework_overview")["refs"]
        # GPAI tier is now citable; the high-risk Annex route is surfaced.
        assert "Art. 51" in refs
        assert "Art. 6" in refs
        assert "Annex III" in refs
        for ref in refs:
            assert ref in ARTICLE_EXISTENCE, f"{ref} not in ARTICLE_EXISTENCE"

    def test_keyword_entity_map_surfaces_gpai_for_framework_questions(self):
        pairs = set(graph_rag._KEYWORD_ENTITY_MAP)
        for kw in ("risk categories", "risk category", "risk taxonomy"):
            assert (kw, "Art. 51") in pairs, f"{kw!r} should surface Art. 51 (GPAI)"


# ─────────────────────────── Anti-pattern E ────────────────────────────


class TestR109HighRiskDefinitionCompleteness:
    def test_art6_stub_carries_third_party_conformity_and_6_3_carveouts(self):
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 6"]["summary"].lower()
        # Art. 6(1)(b): third-party conformity assessment condition.
        assert "third-party conformity assessment" in summary
        # Both routes named.
        assert "annex i" in summary
        assert "annex iii" in summary
        # Art. 6(3) derogation + the profiling kill-switch.
        assert "6(3)" in summary
        assert "preparatory task" in summary
        assert "profiles natural persons" in summary
        # Art. 49(2) registration duty.
        assert "article 49(2)" in summary

    def test_article_6_3_describer_states_profiling_killswitch_not_support(self):
        src = inspect.getsource(graph_rag._deterministic_answer).lower()
        # The carve-out NEVER applies when the system profiles natural
        # persons (the prior prose wrongly allowed "narrow profiling
        # support").
        assert "never applies where the system profiles natural persons" in src
        assert "narrow profiling support" not in src
        assert "register it under article 49(2)" in src


# ─────────────────────────── Anti-patterns B + C + D + A (prompt) ───────


class TestR109Stage2PromptDiscipline:
    def test_closed_set_completeness_rule_present(self):
        assert "CLOSED-SET COMPLETENESS" in ANSWER_GENERATE_SYSTEM
        assert "name EVERY member of that set" in ANSWER_GENERATE_SYSTEM

    def test_headline_rule_names_gpai(self):
        # ANSWER THE HEADLINE for risk-tier questions now includes GPAI.
        assert "Articles 51 to 55" in ANSWER_GENERATE_SYSTEM

    def test_reference_discipline_forbids_tangential_cites(self):
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "do not pull in a provision merely because" in low
        # Annex II / Art. 27 / Art. 49 are the named tangential cites.
        assert "annex ii" in low

    def test_factual_guards_present(self):
        low = ANSWER_GENERATE_SYSTEM.lower()
        # Social-scoring guard.
        assert "not limited to" in low and "public authorities" in low
        # High-risk dual-route + 6(3) guard.
        assert "third-party conformity assessment" in low
        assert "6(3)" in low


# ─────────────────────────── KB version ────────────────────────────────


class TestR109KBVersion:
    def test_kb_version_bumped(self):
        assert KB_VERSION == "2024.1689.v14"


# ═══════════════════════════ Batch 2 ════════════════════════════════════
# Full antifragile dataset + GraphRAG-paper benchmark sweep.


class TestR109Batch2CitationDiscipline:
    """Q4 sectors / Q10 role-contrast / Q14 conformity / Q18 chatbot +
    the Article-49 exemplar fix — all on the Stage-2 prompt."""

    def test_exemplar_cites_article_49_not_51_for_eu_database(self):
        # EU-database registration is Article 49, NOT Article 51 (GPAI).
        assert "register the system in the EU database pursuant to Article 49" in ANSWER_GENERATE_SYSTEM
        assert "pursuant to Article 51" not in ANSWER_GENERATE_SYSTEM

    def test_sectors_reference_discipline(self):
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "which sectors or use cases are high-risk" in low
        assert "article 6 (the classification rule) and annex iii" in low

    def test_role_contrast_definition_discipline(self):
        assert "contrasting two DEFINED ROLES" in ANSWER_GENERATE_SYSTEM

    def test_conformity_assessment_discipline(self):
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "conformity-assessment question about a regulated product" in low
        assert "foreground article 43" in low

    def test_chatbot_limited_risk_guard(self):
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "generative ai chatbot that answers general queries" in low
        assert "limited-risk" in low

    def test_gpai_plus_article50_guard(self):
        assert "general-purpose AI model that ALSO interacts directly" in ANSWER_GENERATE_SYSTEM

    def test_no_entry_into_force_tangent_guard(self):
        low = ANSWER_GENERATE_SYSTEM.lower()
        assert "entry-into-force" in low
        assert "article 113 timeline" in low

    def test_voice_forbids_extra_second_person(self):
        assert "you place" in ANSWER_GENERATE_SYSTEM
        assert "applies to you" in ANSWER_GENERATE_SYSTEM


class TestR109Batch2MedTechDescribers:
    def test_medtech_triage_split_emergency_vs_clinical_trial(self):
        ans = _topic("medtech_triage")["answer"].lower()
        # Honest split: emergency triage IS Annex III(5)(d); clinical-trial
        # selection is NOT a listed Annex III use case.
        assert "emergency healthcare patient triage" in ans
        assert "not itself a listed annex iii use case" in ans
        # Biometric-categorisation prohibition retained.
        assert "article 5(1)(g)" in ans
        # No em-dash (R108).
        assert "—" not in _topic("medtech_triage")["answer"]

    def test_annex_i_safety_component_names_article_43_and_notified_body(self):
        topic = _topic("annex_i_safety_component")
        ans = topic["answer"].lower()
        assert "article 43" in ans
        assert "notified-body" in ans or "notified body" in ans
        assert "Art. 43" in topic["refs"]
        for ref in topic["refs"]:
            assert ref in ARTICLE_EXISTENCE


class TestR109Batch2ProhibitedGatekeeperRBI:
    def test_rbi_clause_drops_annex_ii_misattribution(self):
        clause = _PRACTICE_VERDICT_CLAUSE["real_time_rbi"]
        assert "Annex II" not in clause
        assert "Article 5(1)(h)" in clause
        # Names the actual exceptions (concise, within the 250-char prefix cap).
        low = clause.lower()
        assert "terrorist" in low and "serious" in low and "victim" in low
        assert len(clause) <= 250


class TestR109Batch2GroundedProseNoDash:
    def test_conditional_describers_have_no_dash_separator(self):
        for key, (_pred, clause) in _ART_CONDITIONAL_DESCRIBERS.items():
            assert "—" not in clause, f"em-dash in conditional describer {key}"
            assert "–" not in clause, f"en-dash in conditional describer {key}"


class TestR109Batch2ToneGuardSecondPerson:
    def test_you_place_become_rewritten_third_person(self):
        out = enforce_tone(
            "When you place an AI system on the market, you become the provider."
        )
        assert "you place" not in out.lower()
        assert "you become" not in out.lower()
        assert "the operator places" in out.lower()
        assert "the operator becomes" in out.lower()

    def test_applies_to_you_rewritten(self):
        out = enforce_tone("The AI Act does not apply to you during research.")
        assert "apply to you" not in out.lower()
        assert "apply to the operator" in out.lower()

    def test_regulator_voice_untouched(self):
        # Standalone regulator voice must not be rewritten.
        src = "Providers must establish a quality management system under Article 17."
        assert enforce_tone(src) == src


class TestR109Batch2GuidingPrinciples:
    def test_detect_guiding_principles(self):
        assert graph_rag._detect_guiding_principles_inquiry(
            "What are the guiding principles established by the AI Act?"
        )
        assert graph_rag._detect_guiding_principles_inquiry(
            "what general principles underpin the regulation?"
        )
        # Must NOT fire on unrelated "principle" usage.
        assert not graph_rag._detect_guiding_principles_inquiry(
            "What is the principle place of business of a provider?"
        )

    def test_intercept_emits_principles_not_gpai(self):
        from app.engines.graph_rag import GraphContext, _deterministic_answer

        ctx = GraphContext()
        ans = _deterministic_answer(
            "What are the guiding principles established by the AI Act?", ctx
        ).lower()
        # The actual principles, not GPAI authrep (the live-benchmark bug).
        assert "human agency" in ans or "human oversight" in ans
        assert "transparency" in ans
        assert "article 1" in ans and "article 4" in ans
        assert "authorised representative" not in ans
        # Seeded refs are Art. 1 + Art. 4.
        arts = [o.get("article") for o in ctx.obligations]
        assert "Art. 1" in arts and "Art. 4" in arts


class TestR109Batch2Penalties:
    def test_art99_stub_binds_amounts_to_paragraphs_and_tiers(self):
        summary = EC_CHECKER_OBLIGATION_MAP["Art. 99"]["summary"]
        low = summary.lower()
        # Per-paragraph mapping.
        assert "99(3)" in summary and "99(4)" in summary and "99(5)" in summary
        # Concrete amounts.
        assert "35m" in low and "15m" in low and "7.5m" in low
        assert "7%" in summary and "3%" in summary and "1%" in summary
        # The Art 99(4) tier explicitly names high-risk + transparency.
        assert "high-risk ai system obligations" in low
        assert "transparency obligations" in low
