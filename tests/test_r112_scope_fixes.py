"""R112 regression tests — verified code-review findings #2, #8, #9.

Finding #2 (scope.py) — the aaf6739 "expand prohibited anchor scope"
pass added nine bare GDPR / anti-discrimination phrases to
``_AI_ACT_ANCHORS`` ("sexual orientation", "biometric data", …) that
flipped clearly out-of-scope questions in-scope. They are now
CONDITIONAL anchors requiring an AI marker co-occurrence.

Finding #8 (scenario_classifier.py) — bare markers "exploit" /
"migration" / "election" produced categorically wrong prohibited /
high-risk verdicts on benign scenarios. Replaced with context-bound
forms; the canonical Art. 5(1)(b) / Annex III(7)/(8) davidath
phrasings must keep firing.

Finding #9 (entity_extractor.py) — the penalties→Art. 99 alias
"transparency risk systems" names the LIMITED-RISK tier, not
penalties; combined with the kb_search Art.-99 drift penalty it
promoted Article 99 to rank #1 on transparency-tier questions.
"""
from __future__ import annotations

import pytest

from app.engines.entity_extractor import extract_entities
from app.engines.scenario_classifier import classify_scenario_query
from app.integrations.regenold.scope import classify_scope


# ─── Finding #2 — sensitive-attribute anchors need AI co-occurrence ──────


class TestR112SensitiveAttributeAnchorsRefuseWithoutAI:
    """Each aaf6739 bare anchor: the plain GDPR / anti-discrimination
    shape must refuse (no AI marker present)."""

    #: R364 (commit ``1f4dc20``, "answer adjacent-EU-instrument and MedTech
    #: questions") moved two of the original nine probes out of this table.
    #: Both of them named GDPR, and ``scope.py`` (§ "R364 — domain-boundary
    #: directive", the ``_is_eu_instrument_mention`` branch) now says a
    #: question naming an EU instrument *"is answered on its EU AI Act side
    #: instead of refused"*. So their refusal is no longer the contract —
    #: but the R112 property they were written to pin (the bare
    #: sensitive-attribute anchor must not, on its own, flip an off-topic
    #: question in-scope) is untouched, and is re-pinned strictly more
    #: precisely in ``ADJACENT_EU_PROBES`` below: the GDPR-free form of each
    #: probe must still refuse, AND the in-scope verdict on the GDPR form
    #: must be attributed to the adjacent instrument rather than to the
    #: anchor. That distinguishes the deliberate R364 answer from the
    #: anchor regression this class exists to catch — which the bare
    #: ``in_scope is False`` it replaces could not do.
    ADJACENT_EU_PROBES = (
        # anchor phrase → (GDPR-naming probe, same probe with GDPR removed)
        ("sexual orientation",
         "My dating app asks for sexual orientation. Is that allowed under GDPR?",
         "My dating app asks for sexual orientation. Is that allowed?"),
        ("biometric data",
         "Does GDPR treat biometric data as a special category?",
         "Is biometric data a special category of personal data?"),
    )

    OOS_PROBES = (
        # anchor phrase → off-topic probe carrying it
        ("political affiliation",
         "Can my employer ask about my political affiliation?"),
        ("physical appearance",
         "Can a nightclub deny entry based on physical appearance?"),
        ("trade union membership",
         "My colleague was fired for trade union membership. Is that legal?"),
        ("religious beliefs",
         "Are religious beliefs respected in French public schools?"),
        ("emotional state",
         "My therapist says my emotional state has improved this year."),
        ("protected characteristics",
         "Does the Equality Act cover protected characteristics like age?"),
        ("facial analysis",
         "My beautician offers a facial analysis before every treatment."),
    )

    @pytest.mark.parametrize("anchor,question", OOS_PROBES,
                             ids=[a for a, _ in OOS_PROBES])
    def test_bare_phrase_refuses(self, anchor: str, question: str) -> None:
        verdict = classify_scope(question)
        assert verdict.in_scope is False, (
            f"bare anchor {anchor!r} flipped an off-topic question "
            f"in-scope: {question!r} → {verdict.reason} / {verdict.evidence}"
        )

    @pytest.mark.parametrize("anchor,eu_probe,bare_probe", ADJACENT_EU_PROBES,
                             ids=[a for a, _, _ in ADJACENT_EU_PROBES])
    def test_anchor_is_still_conditional_under_r364(
        self, anchor: str, eu_probe: str, bare_probe: str
    ) -> None:
        """R364 re-pin — the anchor is still conditional; only GDPR flips it.

        These two rows sat in ``OOS_PROBES`` when R112 was written and
        ``classify_scope`` refused them. R364 (``1f4dc20``) deliberately
        changed the contract for questions that NAME an EU instrument, and
        ``app/integrations/regenold/scope.py`` carries the directive as a
        comment: *"EU instruments (GDPR / DSA / DMA / NIS2 / CRA / PLD /
        MDR / IVDR / …) are ADJACENT to the EU AI Act, so a question naming
        one is answered on its EU AI Act side instead of refused"*.

        This is a two-sided, STRONGER replacement for the bare
        ``in_scope is False`` it supersedes:

        1. strip the instrument name and the probe must STILL refuse — that
           is the exact R112 finding-#2 property (a bare sensitive-attribute
           anchor cannot flip an off-topic question in-scope), now isolated
           from the R364 confound instead of being masked by it;
        2. the GDPR form must be in-scope *and* attributed to the adjacent
           instrument. A genuine anchor regression carries no such
           attribution (it reads "AI Act anchor keyword(s) present."), so it
           still fails here.
        """
        bare = classify_scope(bare_probe)
        assert bare.in_scope is False, (
            f"bare anchor {anchor!r} flipped an off-topic question in-scope "
            f"with no EU instrument named: {bare_probe!r} → "
            f"{bare.reason} / {bare.evidence}"
        )
        eu = classify_scope(eu_probe)
        assert eu.in_scope is True, (
            f"R364 adjacent-EU-instrument question refused: {eu_probe!r}"
        )
        assert "adjacent EU instrument" in eu.evidence, (
            f"{eu_probe!r} is in-scope but NOT attributed to the adjacent "
            f"instrument — this is the anchor leak R112 pins, not R364: "
            f"{eu.evidence!r}"
        )

    def test_r34_p0_oos_regression_set_still_refuses(self) -> None:
        for question in (
            "When did the queen withdraw from public life?",
            "Birth certificate processing time in France?",
            "I want to suspend my Netflix subscription.",
            "Which singer would you designate as your favourite musician?",
            "What's the best Italian restaurant in Rome?",
        ):
            assert classify_scope(question).in_scope is False, question


class TestR112SensitiveAttributeAnchorsInScopeWithAI:
    """The Article 5(1)(g) prohibition shapes the aaf6739 anchors
    protected must STAY in-scope via the co-occurrence guard."""

    IN_SCOPE_PROBES = (
        ("sexual orientation",
         "Can an AI system infer sexual orientation from facial images?"),
        ("biometric data",
         "Can an algorithm use biometric data to categorise people by race?"),
        ("political affiliation",
         "Can an algorithm infer political affiliation from biometric data?"),
        ("trade union membership",
         "Does the AI Act prohibit inferring trade union membership from biometric data?"),
        ("religious beliefs",
         "Is biometric categorisation by religious beliefs prohibited?"),
        ("emotional state",
         "Is an AI system that detects a worker's emotional state allowed in the workplace?"),
        ("protected characteristics",
         "Can AI infer protected characteristics like sexual orientation?"),
        ("facial analysis",
         "Is facial analysis by machine learning to detect emotional state allowed?"),
        ("physical appearance",
         "Can an AI system rank job applicants by physical appearance?"),
    )

    @pytest.mark.parametrize("anchor,question", IN_SCOPE_PROBES,
                             ids=[a for a, _ in IN_SCOPE_PROBES])
    def test_ai_cooccurrence_stays_in_scope(self, anchor: str, question: str) -> None:
        verdict = classify_scope(question)
        assert verdict.in_scope is True, (
            f"protected in-scope shape for anchor {anchor!r} now refuses: "
            f"{question!r} → {verdict.reason} / {verdict.evidence}"
        )

    def test_antifragile_emotion_recognition_shape(self) -> None:
        # The Antifragile review shape that motivated the aaf6739 pass.
        assert classify_scope(
            "Are AI systems for emotion recognition always prohibited?"
        ).in_scope is True


# ─── Finding #8 — scenario classifier context-bound markers ──────────────


class TestR112ScenarioClassifierBenignShapes:
    """Benign business scenarios must NOT get prohibited / high-risk."""

    def test_exploit_market_data_not_prohibited(self) -> None:
        v = classify_scenario_query(
            "We are a provider offering an AI system intended to exploit "
            "market data to forecast retail demand."
        )
        assert v is None or v.risk_level != "prohibited"

    def test_database_migration_not_high_risk(self) -> None:
        v = classify_scenario_query(
            "We are a provider offering an AI system intended to automate "
            "database migration for enterprise clients."
        )
        assert v is None or v.risk_level not in ("high-risk", "prohibited")

    def test_product_selection_not_high_risk(self) -> None:
        # "selection" contains the substring "election" — must not fire.
        v = classify_scenario_query(
            "We are a provider offering an AI system intended to optimise "
            "product selection for our online catalogue."
        )
        assert v is None or v.risk_level not in ("high-risk", "prohibited")

    def test_exploit_synergies_not_prohibited(self) -> None:
        v = classify_scenario_query(
            "We are a deployer operating an AI tool intended to exploit "
            "synergies across our logistics network."
        )
        assert v is None or v.risk_level != "prohibited"


class TestR112ScenarioClassifierCanonicalShapesKeepFiring:
    """Canonical Art. 5(1)(b) / Annex III(7)/(8) phrasings (davidath
    gold shapes) must keep their verdicts."""

    def test_exploits_vulnerabilities_of_prohibited(self) -> None:
        v = classify_scenario_query(
            "We are a provider offering an AI system that exploits "
            "vulnerabilities of children to drive in-app purchases."
        )
        assert v is not None and v.risk_level == "prohibited"

    def test_exploit_loneliness_of_elderly_prohibited(self) -> None:
        # davidath row 16 shape — relied on the bare "exploit" stem.
        v = classify_scenario_query(
            "We are a provider offering a subscription service that uses AI "
            "to identify and exploit the loneliness of elderly users for "
            "paid companionship services."
        )
        assert v is not None and v.risk_level == "prohibited"

    def test_migration_asylum_control_high_risk(self) -> None:
        v = classify_scenario_query(
            "We are a deployer operating an AI system intended for "
            "migration and asylum control decisions."
        )
        assert v is not None and v.risk_level == "high-risk"

    def test_immigration_travel_document_check_high_risk(self) -> None:
        # davidath row 107 shape — "immigration officers" + passports,
        # no literal "asylum" / "border control".
        v = classify_scenario_query(
            "We are a deployer operating an AI that assists immigration "
            "officers in verifying the authenticity of travel documents "
            "and detecting forged passports."
        )
        assert v is not None and v.risk_level == "high-risk"

    def test_election_influence_high_risk(self) -> None:
        # davidath row 79 shape.
        v = classify_scenario_query(
            "We are a deployer operating an AI system that manipulates "
            "social media content to influence voting behaviour in an "
            "election."
        )
        # "manipulat" is a prohibited marker — pyramid order means this
        # canonical shape lands at prohibited or high-risk, never lower.
        assert v is not None and v.risk_level in ("prohibited", "high-risk")

    def test_election_voter_ads_high_risk(self) -> None:
        # davidath row 137 shape without a prohibited marker.
        v = classify_scenario_query(
            "We are a deployer operating an AI that creates targeted "
            "political advertisements to sway voter preferences during "
            "an election."
        )
        assert v is not None and v.risk_level == "high-risk"


# ─── Finding #9 — penalties alias overfit ────────────────────────────────


class TestR112PenaltiesAlias:
    def test_transparency_risk_systems_does_not_fire_penalties(self) -> None:
        ents = extract_entities(
            "What obligations apply to transparency risk systems that "
            "interact with people?"
        )
        assert ("penalties", 99) not in ents.get("concept", [])

    def test_sanctions_question_still_fires_penalties(self) -> None:
        # GraphRAG benchmark ng_02 — the genuinely intended case.
        ents = extract_entities(
            "What are the sanctions for violating the provisions of the "
            "regulation for transparency risk systems?"
        )
        assert ("penalties", 99) in ents.get("concept", [])

    def test_transparency_question_retrieval_not_art99_first(self) -> None:
        from app.data.kb_search import top_articles_by_relevance

        top = top_articles_by_relevance(
            "What obligations apply to transparency risk systems that "
            "interact with people?",
            k=5,
        )
        assert top and top[0] != "Art. 99"
        assert "Art. 99" not in top

    def test_sanctions_question_retrieval_art99_first(self) -> None:
        from app.data.kb_search import top_articles_by_relevance

        top = top_articles_by_relevance(
            "What are the sanctions for violating the provisions of the "
            "regulation for transparency risk systems?",
            k=5,
        )
        assert top and top[0] == "Art. 99"
