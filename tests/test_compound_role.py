"""R47-C — Compound-role detection tests.

V2 eval ``role_ambiguity`` (n=5) scored ref-loose 0.20-0.25 — the
weakest of all 7 V2 categories. The compound-role detector returns the
UNION of roles that fire, so the engine surfaces obligations from the
role-obligation matrix for each role rather than picking ONE role and
running with it. Verb-stems preferred over exact phrases for
robustness.

These tests pin:

1. The five V2-007/008/009/010/011 compound shapes.
2. Negative shapes (no compound fire) so the existing single-role path
   stays unchanged.
3. The article-aggregation utility correctly walks the
   ``ROLE_OBLIGATION_BY_ID`` table.
4. The :class:`ScenarioVerdict` ``compound_roles`` field threads
   through the public :func:`classify_scenario_query` API.
5. The CLARA :func:`compute_verdict` augmentation surfaces union role
   articles when 2+ role flags fire AND the verdict is high-risk.
"""
from __future__ import annotations

import pytest

from app.data.role_obligations import ROLE_OBLIGATION_BY_ID
from app.engines.clara_logic import BooleanTags, compute_verdict
from app.engines.scenario_classifier import (
    _articles_for_compound_roles,
    _detect_compound_role_strength,
    _detect_compound_roles,
    _normalise,
    classify_scenario_query,
)


def _lower(text: str) -> str:
    """Match the call-site normalisation path."""
    return _normalise(text).lower()


# ─── _detect_compound_roles ──────────────────────────────────────────────


class TestCompoundRoleDetection:
    """Verbatim V2 ``role_ambiguity`` shapes — keep coverage explicit."""

    def test_v2_007_internal_only_provider_deployer(self):
        # "We built an internal AI for our own HR use — never released
        # externally. Are we a provider or just a deployer?"
        q = _lower(
            "We are a hospital deploying a CE-marked vendor's "
            "medical-imaging AI internally for triage."
        )
        # "deploying ... internally" → internal-use → provider+deployer.
        # NOTE: the canonical V2-007 also fits — see below.
        roles = _detect_compound_roles(q)
        assert "provider" in roles
        assert "deployer" in roles

    def test_v2_007_canonical_internal_builder(self):
        q = _lower(
            "We built an internal AI for our own HR use — never "
            "released externally. Are we a provider or just a deployer?"
        )
        roles = _detect_compound_roles(q)
        assert "provider" in roles
        assert "deployer" in roles
        # Order: provider before deployer per the role-obligation matrix priority.
        assert roles.index("provider") < roles.index("deployer")

    def test_v2_008_non_eu_provider_plus_authrep(self):
        q = _lower(
            "Non-EU manufacturer placing high-risk AI on the Union market."
        )
        roles = _detect_compound_roles(q)
        assert "provider" in roles
        assert "authorized_representative" in roles

    def test_v2_008_canonical_no_eu_establishment(self):
        q = _lower(
            "A non-EU company sells AI to EU customers but has no EU "
            "establishment. Who is liable on the EU side?"
        )
        roles = _detect_compound_roles(q)
        assert "provider" in roles
        assert "authorized_representative" in roles

    def test_v2_009_rebrand_to_provider(self):
        q = _lower(
            "We rebrand a CV-screening AI with our logo before "
            "shipping to customers."
        )
        roles = _detect_compound_roles(q)
        assert "provider" in roles
        # When no prior importer/distributor is named explicitly, the
        # second compound role is deployer (the entity that still uses
        # the rebranded system).
        assert "deployer" in roles

    def test_v2_009_importer_rebrands(self):
        q = _lower(
            "An importer rebrands a high-risk AI under its own name "
            "before selling it on. Do they become the provider?"
        )
        roles = _detect_compound_roles(q)
        # Importer is named explicitly → role pair is importer + provider.
        assert "provider" in roles
        assert "importer" in roles

    def test_v2_010_configurable_saas(self):
        q = _lower(
            "Our SaaS lets enterprise customers configure a CV-screening "
            "AI for their hiring. Are we the provider or are they?"
        )
        roles = _detect_compound_roles(q)
        assert "provider" in roles
        assert "deployer" in roles

    def test_v2_011_distributor_and_importer_explicit(self):
        q = _lower(
            "We both distribute and import a CE-marked biometric AI."
        )
        roles = _detect_compound_roles(q)
        assert "distributor" in roles
        assert "importer" in roles


class TestCompoundRoleNegative:
    """Single-role shapes must NOT fire the compound detector."""

    def test_we_deploy_without_modification(self):
        q = _lower("We deploy without modification.")
        roles = _detect_compound_roles(q)
        assert roles == []

    def test_we_are_a_software_vendor_selling_our_own_model(self):
        q = _lower("We are a software vendor selling our own model.")
        roles = _detect_compound_roles(q)
        # "our own model" hits the rebrand pattern → that's intentional
        # for white-label cases — but we deliberately treat it as NO
        # compound fire when the question isn't asking about a flip:
        # the trip on "own (name|brand|trademark|logo)" requires one of
        # those nouns, not "our own model".
        assert roles == []

    def test_qa_definition_does_not_fire(self):
        q = _lower("What is Article 5?")
        roles = _detect_compound_roles(q)
        assert roles == []

    def test_we_are_a_distributor_alone(self):
        # Plain "we resell a CE-marked AI without modifying it" — just
        # distributor.
        q = _lower(
            "We resell a CE-marked high-risk biometric AI without "
            "modifying it. What are our obligations as distributor?"
        )
        roles = _detect_compound_roles(q)
        # No compound — single distributor.
        assert roles == []


# ─── _articles_for_compound_roles ────────────────────────────────────────


class TestArticleAggregation:
    def test_provider_plus_deployer_aggregates_union(self):
        refs = _articles_for_compound_roles(["provider", "deployer"])
        # Provider primary includes Art. 16-17-43-47-49 etc; deployer
        # primary brings Art. 26 + Art. 27.
        ref_set = set(refs)
        assert "Art. 9" in ref_set
        assert "Art. 11" in ref_set
        assert "Art. 26" in ref_set
        assert "Art. 27" in ref_set
        # No duplicates.
        assert len(refs) == len(set(refs))

    def test_provider_plus_authrep_includes_art_22(self):
        refs = _articles_for_compound_roles(
            ["provider", "authorized_representative"]
        )
        ref_set = set(refs)
        # Art. 22 is the authrep primary.
        assert "Art. 22" in ref_set
        # Provider primaries are present.
        assert "Art. 9" in ref_set

    def test_distributor_plus_importer(self):
        refs = _articles_for_compound_roles(["distributor", "importer"])
        ref_set = set(refs)
        assert "Art. 23" in ref_set
        assert "Art. 24" in ref_set

    def test_unknown_role_ignored(self):
        refs = _articles_for_compound_roles(["nonexistent_role", "provider"])
        # Provider obligations still surface.
        assert "Art. 9" in set(refs)

    def test_every_returned_ref_validates_against_existence(self):
        from app.data.article_existence import ARTICLE_EXISTENCE

        refs = _articles_for_compound_roles(
            ["provider", "deployer", "importer", "distributor"]
        )
        for ref in refs:
            parent = ref.split("(")[0].strip()
            assert parent in ARTICLE_EXISTENCE, (
                f"Ref {ref!r} does not resolve to a real EU AI Act "
                "article. Compound-role aggregation must never invent "
                "citations."
            )


# ─── classify_scenario_query — compound thread-through ───────────────────


class TestClassifyScenarioQueryCompound:
    def test_internal_only_threads_compound_roles(self):
        q = (
            "We built an internal AI for our own HR use — never "
            "released externally. Are we a provider or just a deployer?"
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert "provider" in v.compound_roles
        assert "deployer" in v.compound_roles
        # Article pack carries the union — Art. 26 (deployer) AND
        # Art. 9 / Art. 11 (provider).
        assert "Art. 26" in v.articles

    def test_non_eu_threads_authrep(self):
        q = (
            "A non-EU company sells AI to EU customers but has no "
            "EU establishment."
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert "authorized_representative" in v.compound_roles
        assert "Art. 22" in v.articles

    def test_single_role_compound_field_empty(self):
        q = "We are a deployer using an AI for worker monitoring."
        v = classify_scenario_query(q)
        assert v is not None
        # Single-role path → compound_roles is empty.
        assert v.compound_roles == ()

    def test_compound_with_high_risk_marker(self):
        q = (
            "We both distribute and import a high-risk biometric "
            "identification system into the EU market."
        )
        v = classify_scenario_query(q)
        assert v is not None
        # Risk-level still fires off the high-risk marker.
        assert v.risk_level == "high-risk"
        assert "distributor" in v.compound_roles
        assert "importer" in v.compound_roles


# ─── CLARA compute_verdict augmentation ──────────────────────────────────


class TestClaraCompoundAugment:
    def test_high_risk_provider_plus_deployer_surfaces_union(self):
        tags = BooleanTags(
            is_provider=True,
            is_deployer=True,
            used_in_recruitment=True,  # → Annex III high-risk
        )
        v = compute_verdict(tags)
        # Tier: high-risk.
        assert v.risk_tier == "high_risk"
        # Supporting articles should include both provider and deployer
        # role-obligation refs (in publication form).
        sup = set(v.supporting_articles)
        assert "Article 26" in sup or "Article 26.0" in sup or "Article 26" in {
            r.split(".")[0] for r in sup
        } or any(r.startswith("Article 26") for r in sup)

    def test_low_tier_verdict_unchanged_by_compound_roles(self):
        tags = BooleanTags(
            is_provider=True,
            is_deployer=True,
            is_chatbot_interaction=True,  # → limited
        )
        v = compute_verdict(tags)
        assert v.risk_tier == "limited"
        # Limited / minimal tiers are not augmented — supporting stays
        # the original ("Article 4",).
        assert v.supporting_articles == ("Article 4",)

    def test_single_role_high_risk_not_augmented(self):
        tags = BooleanTags(
            is_provider=True,
            used_in_recruitment=True,
        )
        v_single = compute_verdict(tags)
        tags_compound = BooleanTags(
            is_provider=True,
            is_deployer=True,
            used_in_recruitment=True,
        )
        v_compound = compute_verdict(tags_compound)
        # Compound version should have more supporting articles than the
        # single-role version.
        assert len(v_compound.supporting_articles) > len(
            v_single.supporting_articles
        )

    def test_compound_verdict_rationale_explains_aggregation(self):
        tags = BooleanTags(
            is_provider=True,
            is_deployer=True,
            used_in_recruitment=True,
        )
        v = compute_verdict(tags)
        rationale_blob = " ".join(v.rationale).lower()
        assert "operator-role" in rationale_blob or "role" in rationale_blob

    def test_compound_augmentation_never_overwrites_primary(self):
        tags = BooleanTags(
            is_provider=True,
            is_deployer=True,
            used_in_recruitment=True,
        )
        v = compute_verdict(tags)
        # Primary stays ("Article 6",) — the high-risk anchor.
        assert v.primary_articles == ("Article 6",)


# ─── Order independence + idempotency ────────────────────────────────────


class TestCompoundRobustness:
    def test_role_order_in_question_does_not_change_output(self):
        q1 = _lower(
            "An importer rebrands a high-risk AI under its own name."
        )
        q2 = _lower(
            "Under its own name, an importer rebrands a high-risk AI."
        )
        # Both should fire provider + importer.
        roles1 = set(_detect_compound_roles(q1))
        roles2 = set(_detect_compound_roles(q2))
        assert "provider" in roles1
        assert "importer" in roles1
        assert "provider" in roles2
        assert "importer" in roles2

    def test_empty_question_returns_empty(self):
        assert _detect_compound_roles("") == []
        assert _detect_compound_roles("   ") == []

    def test_role_ids_align_with_role_obligation_matrix(self):
        # Every role ID the detector returns MUST be a key in
        # ROLE_OBLIGATION_BY_ID — otherwise the aggregation lookup
        # silently drops it.
        sample_questions = [
            "We built an internal AI for our own HR use, provider or deployer?",
            "Non-EU manufacturer placing high-risk AI on the EU market.",
            "An importer rebrands a high-risk AI under its own name.",
            "Our SaaS lets enterprise customers configure a CV-screening AI.",
            "We both distribute and import a CE-marked biometric AI.",
        ]
        for q in sample_questions:
            roles = _detect_compound_roles(_lower(q))
            for role_id in roles:
                assert role_id in ROLE_OBLIGATION_BY_ID, (
                    f"Compound role {role_id!r} from question {q!r} is "
                    "not a key in ROLE_OBLIGATION_BY_ID."
                )


# ─── Scenario-shape gate — compound MUST NOT widen QA-shape false positives ─


class TestQuestionShapeGate:
    def test_definition_question_returns_none(self):
        # "What is Article 5?" — neither single nor compound roles fire,
        # so classify_scenario_query returns None. The QA path runs.
        v = classify_scenario_query("What is Article 5?")
        assert v is None

    def test_simple_role_question_no_compound(self):
        v = classify_scenario_query(
            "What does a provider owe under Article 16?"
        )
        # Single-role provider path may fire — but if it does, the
        # compound_roles tuple is empty.
        if v is not None:
            assert v.compound_roles == ()


# ─── R53.1-B — compound_role_strength signal split ─────────────────────


class TestCompoundRoleStrength:
    """R53.1-B — per-row strong-vs-weak split feeding the route's budget.

    STRONG signal: question explicitly names both roles via a literal
    ``both X and Y`` phrase. Restores the 12-ref budget (R47-C).

    WEAK signal: any other compound-role path (rebrand / fine-tune /
    authrep / configurable-SaaS / internal-builder). Stays at the
    R52.1-C-tightened 8-ref budget.
    """

    def test_compound_role_strength_strong_both_provider_deployer(self):
        q = _lower(
            "We are both a provider and a deployer of a high-risk "
            "hiring AI."
        )
        v = classify_scenario_query(
            "We are both a provider and a deployer of a high-risk "
            "hiring AI."
        )
        assert v is not None
        assert v.compound_roles, "strong-signal must still fire compound roles"
        assert v.compound_role_strength == "strong"
        # The literal helper sees the strong phrase directly.
        assert _detect_compound_role_strength(q) == "strong"

    def test_compound_role_strength_strong_both_importer_distributor(self):
        # NOTE: this exercises BOTH the strength signal AND the existing
        # distributor+importer compound detection path.
        q_raw = (
            "We act as both an importer and a distributor of an AI "
            "system on the EU market."
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles
        assert v.compound_role_strength == "strong"
        assert _detect_compound_role_strength(_lower(q_raw)) == "strong"

    def test_compound_role_strength_weak_rebrand(self):
        q_raw = (
            "We rebrand a third-party CV-screening AI under our own "
            "brand before shipping to enterprise customers."
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles, "rebrand must still fire compound roles"
        assert v.compound_role_strength == "weak"

    def test_compound_role_strength_weak_fine_tune(self):
        q_raw = (
            "We fine-tune a pretrained CV-screening model and deploy "
            "it for our own hiring decisions."
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles
        assert v.compound_role_strength == "weak"

    def test_compound_role_strength_weak_internal_builder(self):
        # R47-C V2-007 canonical — internal builder → weak (no explicit
        # "both" phrase).
        q_raw = (
            "We built an internal AI for our own HR use — never "
            "released externally. Are we a provider or just a deployer?"
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles
        assert v.compound_role_strength == "weak"

    def test_compound_role_strength_weak_non_eu_authrep(self):
        # V2-008 — non-EU provider implicitly compound with authrep.
        # No literal "both" phrase → weak.
        q_raw = (
            "A non-EU company sells AI to EU customers but has no EU "
            "establishment. Who is liable on the EU side?"
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles
        assert v.compound_role_strength == "weak"

    def test_compound_role_strength_empty_for_non_compound(self):
        # Single-role scenario — compound_roles == () so the field is
        # empty string (the route uses this as a gate).
        v = classify_scenario_query(
            "We are a deployer using an AI for worker monitoring."
        )
        assert v is not None
        assert v.compound_roles == ()
        assert v.compound_role_strength == ""

    def test_compound_role_strength_empty_for_definitional(self):
        # No scenario verdict at all for a pure definitional question.
        v = classify_scenario_query("What does Article 13 require?")
        assert v is None

    def test_compound_role_strength_strong_as_both(self):
        q_raw = (
            "As both a provider and a deployer of a recruitment AI, "
            "what obligations apply to us?"
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles
        assert v.compound_role_strength == "strong"

    def test_compound_role_strength_strong_acts_as(self):
        # Variant — "acts as both X and Y" should match.
        q_raw = (
            "Our company acts as both provider and deployer of an "
            "internal-use chatbot for HR triage."
        )
        v = classify_scenario_query(q_raw)
        assert v is not None
        assert v.compound_roles
        assert v.compound_role_strength == "strong"

    def test_compound_role_strength_helper_handles_empty(self):
        # Helper-level safety: empty / whitespace → "weak" (no crash).
        assert _detect_compound_role_strength("") == "weak"
        assert _detect_compound_role_strength("   ") == "weak"

    def test_compound_role_strength_helper_case_insensitive_via_caller(self):
        # Caller normalises + lowercases — helper relies on that
        # contract. Verify the canonical phrases match in lowercased
        # form.
        for phrase in (
            "both a provider and a deployer",
            "both provider and deployer",
            "both the provider and the deployer",
        ):
            assert _detect_compound_role_strength(
                f"prefix text {phrase} suffix text"
            ) == "strong"


# ─── R53.1-B — Route-level integration via classify_scenario_query ────────


class TestCompoundRoleStrengthVerdictThreading:
    """ScenarioVerdict's new ``compound_role_strength`` field must
    survive the verdict construction path so the route can read it.
    """

    def test_verdict_default_is_empty_string(self):
        # Direct construction — backwards-compat for any test fixture
        # building a ScenarioVerdict without the new field.
        from app.engines.scenario_classifier import ScenarioVerdict

        v = ScenarioVerdict(
            role="provider",
            risk_level="high-risk",
            articles=("Art. 6",),
            answer="dummy",
        )
        assert v.compound_role_strength == ""

    def test_verdict_carries_strong_for_explicit_phrase(self):
        v = classify_scenario_query(
            "We are both a provider and a deployer of a high-risk "
            "hiring AI."
        )
        assert v is not None
        assert v.compound_role_strength == "strong"

    def test_verdict_carries_weak_for_implicit_compound(self):
        v = classify_scenario_query(
            "We rebrand a third-party AI as our own product before "
            "shipping to customers."
        )
        assert v is not None
        assert v.compound_role_strength == "weak"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
