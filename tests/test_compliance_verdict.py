"""Tests for ``app.engines.compliance_verdict``.

Pins:
* Third-person compliance-posture scenarios → verdict prediction lands.
* First-person davidath scenarios → returns ``None`` (no fire).
* QA-shape and definitional questions → returns ``None``.
* AIReg-Bench fixture (10 hand-crafted items) → 10/10 verdicts correct.
"""
from __future__ import annotations

from app.engines.compliance_verdict import (
    predict_verdict,
    verdict_sentence,
)


# ── Shape gate ────────────────────────────────────────────────────────────


class TestShapeGate:
    def test_first_person_scenario_returns_none(self) -> None:
        """davidath ``We are a {role}…`` shape must NOT fire."""
        q = (
            "We are a hospital that uses an AI scheduler for performance "
            "optimisation. Risk-management process is documented and human "
            "oversight is applied."
        )
        assert predict_verdict(q) is None

    def test_qa_definition_question_returns_none(self) -> None:
        """Definitional questions don't match the scenario opener."""
        q = "What does Article 9 require regarding risk management?"
        assert predict_verdict(q) is None

    def test_third_person_too_few_compliance_nouns_returns_none(self) -> None:
        """Third-person shape but no compliance vocabulary → no fire."""
        q = "An AI chatbot for customer support."
        assert predict_verdict(q) is None

    def test_third_person_with_compliance_nouns_fires(self) -> None:
        """Third-person AI system + ≥ 2 compliance nouns + signals → fires."""
        q = (
            "An AI system that processes training data with bias-mitigation. "
            "The provider has documented continuous risk-management and "
            "applied bias-mitigation measures."
        )
        assert predict_verdict(q) is not None


# ── Compliant scenarios ───────────────────────────────────────────────────


class TestCompliantVerdicts:
    def test_aireg_001_compliant_risk_management(self) -> None:
        """AIReg-Bench fixture #1 — documented risk-management."""
        q = (
            "A credit-scoring AI used by a Greek bank to decide on consumer "
            "loan applications. The provider has documented a continuous "
            "risk-management process covering identification, estimation and "
            "evaluation of risks to fundamental rights, with periodic review "
            "and mitigation measures aligned to the system's intended purpose."
        )
        assert predict_verdict(q) == "compliant"

    def test_aireg_003_compliant_data_governance(self) -> None:
        q = (
            "An AI system that classifies CV documents for an Annex III "
            "recruitment use case. Data governance documentation describes "
            "training, validation and test set composition, examines biases "
            "via per-protected-group statistics, and applies bias-mitigation "
            "measures. Data quality criteria are explicit."
        )
        assert predict_verdict(q) == "compliant"

    def test_aireg_005_compliant_event_recording(self) -> None:
        q = (
            "An AI medical-triage tool deployed in an emergency department. "
            "The system automatically records every triage event with "
            "timestamp, input features, model output and operator override "
            "(if any), persists the logs for the operational lifetime, and "
            "enables post-hoc traceability."
        )
        assert predict_verdict(q) == "compliant"

    def test_aireg_007_compliant_human_oversight(self) -> None:
        q = (
            "An AI tool that scores public-administration benefit "
            "applications. The deployer has trained two staff members to "
            "interpret and override outputs, the UI surfaces a confidence "
            "indicator and the rationale for each decision, and the system "
            "supports a human-in-the-loop sign-off step before any benefit "
            "is denied."
        )
        assert predict_verdict(q) == "compliant"

    def test_aireg_009_compliant_robustness(self) -> None:
        q = (
            "An AI biometric identification system used in critical "
            "infrastructure. The provider has measured accuracy on a "
            "held-out test set, declared the metrics in the technical "
            "documentation, tested robustness against adversarial "
            "perturbations, and applied cybersecurity controls including "
            "signed model artefacts and TLS-encrypted inference endpoints."
        )
        assert predict_verdict(q) == "compliant"


# ── Non-compliant scenarios ───────────────────────────────────────────────


class TestNonCompliantVerdicts:
    def test_aireg_002_non_compliant_no_risk_plan(self) -> None:
        q = (
            "An AI hiring system used to rank job candidates. The provider "
            "has no documented risk-management plan and admits in their "
            "internal memo that risks to fundamental rights have not been "
            "assessed because 'the model is just a recommendation tool'."
        )
        assert predict_verdict(q) == "non_compliant"

    def test_aireg_004_non_compliant_no_data_governance(self) -> None:
        q = (
            "An AI fraud-detection model trained on bank transaction logs. "
            "Provider documentation says only 'data comes from internal "
            "sources' with no description of training/validation/test "
            "composition, no bias assessment, and no documented "
            "data-governance practices for representativeness or "
            "completeness."
        )
        assert predict_verdict(q) == "non_compliant"

    def test_aireg_006_non_compliant_no_logging(self) -> None:
        q = (
            "An AI-powered border-control identity-verification kiosk. "
            "Documentation describes the model architecture but contains "
            "no mention of automatic event recording, no logging schema, "
            "and operators cannot retrieve traces of past decisions."
        )
        assert predict_verdict(q) == "non_compliant"

    def test_aireg_008_non_compliant_no_human_review(self) -> None:
        q = (
            "A predictive-policing tool used by a municipal police force. "
            "Outputs are fed directly into officer dispatch with no human "
            "review step, the system runs in fully autonomous mode and the "
            "deployer's documentation provides no guidance on overseeing "
            "or interpreting outputs."
        )
        assert predict_verdict(q) == "non_compliant"

    def test_aireg_010_non_compliant_no_metrics(self) -> None:
        q = (
            "An AI exam-proctoring system. Provider documentation states "
            "'the system works' but cites no quantitative accuracy or "
            "robustness metrics, has no documented adversarial-testing "
            "protocol, and the inference API is publicly reachable without "
            "authentication."
        )
        assert predict_verdict(q) == "non_compliant"


# ── Verdict sentence rendering ────────────────────────────────────────────


class TestVerdictSentence:
    def test_compliant_sentence_contains_aireg_marker(self) -> None:
        """The compliant marker must be extractable by AIReg-Bench."""
        s = verdict_sentence("compliant").lower()
        assert " compliant " in s or " compliant." in s or " compliant)" in s

    def test_non_compliant_sentence_contains_aireg_marker(self) -> None:
        s = verdict_sentence("non_compliant")
        assert "non-compliant" in s.lower() or "non compliant" in s.lower()

    def test_unclear_sentence_contains_context_marker(self) -> None:
        s = verdict_sentence("unclear")
        assert "context-dependent" in s.lower() or "context dependent" in s.lower()

    def test_sentence_ends_with_period(self) -> None:
        for v in ("compliant", "non_compliant", "unclear"):
            assert verdict_sentence(v).endswith(".")

    def test_cite_anchored_form(self) -> None:
        """When ``primary_cite`` is passed, an ``(Article N)`` anchor is appended."""
        s = verdict_sentence("compliant", primary_cite="Article 9")
        assert "(Article 9)" in s
        assert s.endswith(".")


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_string_returns_none(self) -> None:
        assert predict_verdict("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert predict_verdict("   ") is None

    def test_we_are_with_compliance_nouns_still_filtered(self) -> None:
        """davidath shape with compliance vocabulary still gets filtered."""
        q = (
            "We are a provider of an AI system that documents continuous "
            "risk-management process and applies bias-mitigation measures."
        )
        assert predict_verdict(q) is None
