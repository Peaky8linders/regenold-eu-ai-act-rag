"""Round 69 — Structured query payload regression tests.

Covers ``app/engines/query_structure.py`` — the proposed Hybrid-RAG
architecture's Section-3A structured query extractor. The two genuinely
missing dimensions versus the existing intent classifier are
``actor_location`` (EU vs non-EU) and ``market_location`` — the
extraterritorial axis the EU AI Act's Article 2 scope turns on.

The payload feeds a one-line ``QUERY PROFILE`` hint into the Stage-2
generation context only, so these tests assert extraction correctness,
not any wire-level rubric behaviour.
"""
from __future__ import annotations

from app.engines.query_structure import (
    StructuredQuery,
    analyse_query,
    profile_line,
)


class TestStructuredQueryDataclass:
    def test_empty_is_empty(self) -> None:
        assert StructuredQuery().is_empty() is True

    def test_any_field_makes_non_empty(self) -> None:
        assert StructuredQuery(target_actor="provider").is_empty() is False

    def test_frozen(self) -> None:
        sq = StructuredQuery()
        try:
            sq.target_actor = "x"  # type: ignore[misc]
        except Exception:  # noqa: BLE001 — dataclass(frozen=True) raises
            return
        raise AssertionError("StructuredQuery should be frozen")


class TestActorDetection:
    def test_provider(self) -> None:
        assert analyse_query("What must a provider do?").target_actor == "provider"

    def test_deployer(self) -> None:
        assert analyse_query("What is a deployer?").target_actor == "deployer"

    def test_importer(self) -> None:
        assert (
            analyse_query("obligations of the importer").target_actor == "importer"
        )

    def test_distributor(self) -> None:
        assert (
            analyse_query("a distributor of AI systems").target_actor
            == "distributor"
        )

    def test_authorised_representative(self) -> None:
        sq = analyse_query("Does the authorised representative need to register?")
        assert sq.target_actor == "authorised representative"

    def test_no_actor(self) -> None:
        assert analyse_query("What is the maximum fine?").target_actor == ""


class TestActorLocation:
    def test_us_provider_is_non_eu(self) -> None:
        assert analyse_query("a US provider of AI").actor_location == "non-EU"

    def test_chinese_company_is_non_eu(self) -> None:
        sq = analyse_query("A Chinese AI company sells a system.")
        assert sq.actor_location == "non-EU"

    def test_outside_the_union_is_non_eu(self) -> None:
        sq = analyse_query("a company established outside the Union")
        assert sq.actor_location == "non-EU"

    def test_eu_based_is_eu(self) -> None:
        assert analyse_query("an EU-based provider").actor_location == "EU"

    def test_no_location_signal(self) -> None:
        assert analyse_query("What is a deployer?").actor_location == ""


class TestMarketLocation:
    def test_into_france_is_eu(self) -> None:
        assert analyse_query("deploy the tool into France").market_location == "EU"

    def test_on_the_union_market(self) -> None:
        sq = analyse_query("placed on the Union market")
        assert sq.market_location == "EU"

    def test_in_germany(self) -> None:
        assert analyse_query("sell it in Germany").market_location == "EU"

    def test_no_market_signal(self) -> None:
        assert analyse_query("What is a provider?").market_location == ""


class TestApplicationAndRisk:
    def test_recruitment_application(self) -> None:
        sq = analyse_query("an AI tool that screens CVs for hiring")
        assert sq.ai_application == "recruitment & employment"

    def test_emotion_recognition(self) -> None:
        sq = analyse_query("Is emotion recognition prohibited?")
        assert sq.ai_application == "emotion recognition"
        assert sq.implied_risk_level == "prohibited"

    def test_high_risk_marker(self) -> None:
        assert analyse_query("a high-risk AI system").implied_risk_level == "high-risk"

    def test_gpai_marker(self) -> None:
        sq = analyse_query("obligations for a general-purpose AI model")
        assert sq.implied_risk_level == "GPAI"

    def test_legal_concept(self) -> None:
        assert (
            analyse_query("What are the data governance requirements?").legal_concept
            == "data & data governance"
        )


class TestCanonicalCrossBorderCase:
    """The proposal's Section-3A worked example must extract fully."""

    def test_full_payload(self) -> None:
        sq = analyse_query(
            "What data governance requirements must a US provider follow if "
            "they deploy a high-risk resume-scanning AI tool into France?"
        )
        assert sq.target_actor == "provider"
        assert sq.actor_location == "non-EU"
        assert sq.market_location == "EU"
        assert sq.ai_application == "recruitment & employment"
        assert sq.implied_risk_level == "high-risk"
        assert sq.legal_concept == "data & data governance"


class TestProfileLine:
    def test_empty_query_yields_empty_line(self) -> None:
        assert profile_line(analyse_query("")) == ""

    def test_empty_structured_query_yields_empty_line(self) -> None:
        assert profile_line(StructuredQuery()) == ""

    def test_profile_line_format(self) -> None:
        line = profile_line(analyse_query("What must a US provider do?"))
        assert line.startswith("QUERY PROFILE:")
        assert "actor=provider" in line
        assert "actor location=non-EU" in line

    def test_profile_line_omits_empty_fields(self) -> None:
        line = profile_line(StructuredQuery(target_actor="deployer"))
        assert line == "QUERY PROFILE: actor=deployer"


class TestRobustness:
    def test_empty_question(self) -> None:
        assert analyse_query("").is_empty() is True

    def test_garbage_never_raises(self) -> None:
        for q in ("\x00\x01", "?" * 3000, "   ", "123 456"):
            analyse_query(q)  # must not raise

    def test_out_of_scope_question_low_signal(self) -> None:
        # An off-topic question should not hallucinate a rich payload.
        sq = analyse_query("What is the best restaurant in Rome?")
        assert sq.target_actor == ""
        assert sq.ai_application == ""
