"""R43 fix — hyphen-tolerant marker matching for Art. 6(1a) carve-out.

R41's _check_safety_component_carve_out used space-form substring
matching against _PROHIBITED_MARKERS / _ANNEX_III_MARKERS. The
davidath / Regenold scenarios use hyphenated forms (predictive-policing,
credit-scoring, fraud-detection, medical-diagnosis) which silently
bypassed the override gates → carve-out returned non_hrais on Art. 5
prohibited and Annex III high-risk practices. This is a regulatory
correctness defect.

This module pins:
* Hyphenated Art. 5 practices override the carve-out (returns None or
  a prohibition verdict, NEVER non_hrais).
* Hyphenated Annex III categories override the carve-out.
* Hyphenated Annex I product-safety categories (medical-diagnosis,
  medical-imaging, safety-critical) override the carve-out.
* Space-form variants still work (no regression on R41 baseline).
"""
from __future__ import annotations

import pytest

from app.engines.scenario_classifier import (
    ScenarioVerdict,
    _check_safety_component_carve_out,
    classify_scenario_query,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _assert_not_non_hrais(verdict: ScenarioVerdict | None, label: str) -> None:
    """A verdict must NOT be the Art. 6(1a) non-HRAIS escape hatch.

    ``None`` is acceptable (downstream classifier handles); a
    prohibition / HRAIS verdict is also acceptable. The defect signal
    is ``risk_level == 'non_hrais'`` with ``Art. 6(1a)`` in the
    article pack — that means the carve-out leaked through an override
    gate.
    """
    if verdict is None:
        return
    assert verdict.risk_level != "non_hrais", (
        f"{label}: carve-out leaked through override → {verdict!r}"
    )
    assert "Art. 6(1a)" not in verdict.articles, (
        f"{label}: carve-out cited Art. 6(1a) despite override → {verdict!r}"
    )


# ── Art. 5 prohibited — hyphenated forms must override the carve-out ──────


class TestArt5HyphenatedOverridesCarveOut:
    """Art. 5 prohibited practices in hyphenated form must defer the
    carve-out. Pre-R43 these silently slipped through because the
    marker set used space-form (``predictive policing``) while
    davidath-style scenarios use hyphenated (``predictive-policing``)."""

    def test_predictive_policing_hyphenated_carve_out(self) -> None:
        q = "A predictive-policing tool for officer convenience."
        v = _check_safety_component_carve_out(q, role="deployer")
        _assert_not_non_hrais(v, "predictive-policing carve-out")
        # Engineering review specifically requires: returns None (override fires).
        assert v is None, f"Expected None, got {v!r}"

    def test_predictive_policing_hyphenated_full_classify(self) -> None:
        q = "A predictive-policing tool for officer convenience."
        v = classify_scenario_query(q)
        _assert_not_non_hrais(v, "predictive-policing classify_scenario_query")

    def test_social_scoring_hyphenated(self) -> None:
        q = "A social-scoring system for citizen quality control."
        v = _check_safety_component_carve_out(q, role="deployer")
        _assert_not_non_hrais(v, "social-scoring carve-out")
        assert v is None

    def test_emotion_recognition_hyphenated_workplace(self) -> None:
        q = (
            "An emotion-recognition system at workplace for "
            "performance optimisation."
        )
        v = _check_safety_component_carve_out(q, role="provider")
        _assert_not_non_hrais(v, "emotion-recognition workplace carve-out")
        assert v is None


# ── Annex III high-risk — hyphenated forms must override the carve-out ────


class TestAnnexIIIHyphenatedOverridesCarveOut:
    """Annex III high-risk categories in hyphenated form must defer
    the carve-out. The R41 baseline used `credit scoring` /
    `recruitment` / `biometric categorisation` / `cv screening` —
    these wouldn't match the davidath-style hyphenated phrasings
    without the R43 normalisation."""

    def test_credit_scoring_hyphenated_carve_out(self) -> None:
        q = (
            "A credit-scoring system intended to automate consumer-loan "
            "workflow for bank convenience."
        )
        v = _check_safety_component_carve_out(q, role="deployer")
        _assert_not_non_hrais(v, "credit-scoring carve-out")
        assert v is None

    def test_credit_scoring_hyphenated_full_classify(self) -> None:
        q = (
            "A credit-scoring system intended to automate consumer-loan "
            "workflow for bank convenience."
        )
        v = classify_scenario_query(q)
        _assert_not_non_hrais(v, "credit-scoring classify_scenario_query")

    def test_recruitment_screening_hyphenated(self) -> None:
        q = "A recruitment-screening AI for HR convenience."
        v = _check_safety_component_carve_out(q, role="provider")
        _assert_not_non_hrais(v, "recruitment-screening carve-out")
        assert v is None

    def test_biometric_categorisation_hyphenated(self) -> None:
        q = "A biometric-categorisation tool for staff quality control."
        v = _check_safety_component_carve_out(q, role="deployer")
        _assert_not_non_hrais(v, "biometric-categorisation carve-out")
        assert v is None

    def test_cv_screening_hyphenated(self) -> None:
        q = "A cv-screening engine for recruitment convenience."
        v = _check_safety_component_carve_out(q, role="provider")
        _assert_not_non_hrais(v, "cv-screening carve-out")
        assert v is None


# ── Annex I product safety — hyphenated forms must override ──────────────


class TestAnnexIProductSafetyHyphenatedOverridesCarveOut:
    """Annex I product safety categories (medical-diagnosis,
    medical-imaging, safety-critical) must override the carve-out.
    These products fall under Art. 6(1) HRAIS via the EU product-safety
    legislation list (MDR / IVDR / Machinery / RED / etc.)."""

    def test_medical_diagnosis_hyphenated_carve_out(self) -> None:
        q = "An AI medical-diagnosis tool used for clinician convenience."
        v = _check_safety_component_carve_out(q, role="provider")
        _assert_not_non_hrais(v, "medical-diagnosis carve-out")
        assert v is None

    def test_medical_diagnosis_hyphenated_full_classify(self) -> None:
        q = "An AI medical-diagnosis tool used for clinician convenience."
        v = classify_scenario_query(q)
        _assert_not_non_hrais(v, "medical-diagnosis classify_scenario_query")

    def test_medical_imaging_hyphenated(self) -> None:
        q = "AI medical-imaging system for clinician convenience."
        v = _check_safety_component_carve_out(q, role="provider")
        _assert_not_non_hrais(v, "medical-imaging carve-out")
        assert v is None

    def test_safety_critical_hyphenated(self) -> None:
        q = "Safety-critical control AI for automation."
        v = _check_safety_component_carve_out(q, role="deployer")
        _assert_not_non_hrais(v, "safety-critical carve-out")
        assert v is None


# ── Regression preservation — space-form carve-out paths still fire ──────


class TestR41NoRegressionOnLegitimateCarveOut:
    """The R43 fix must not break the R41 baseline. Plain carve-out
    paths (no Art. 5 / Annex III / Annex I override) must still
    return ``non_hrais`` with Art. 6(1a)."""

    def test_hospital_scheduler_still_non_hrais(self) -> None:
        q = (
            "We are a hospital that uses an AI scheduler for performance "
            "optimisation"
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        assert "Art. 6(1a)" in v.articles

    def test_bare_convenience_still_non_hrais(self) -> None:
        q = "Our AI is for convenience."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        assert "Art. 6(1a)" in v.articles

    def test_automation_and_convenience_still_non_hrais(self) -> None:
        q = "An AI used for automation and convenience"
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"

    def test_doctor_transcription_still_non_hrais_with_art50(self) -> None:
        """Transcription is a generative-content carve-out path —
        non_hrais + Art. 50 transparency survives the safety-component
        exception. Must not regress."""
        q = (
            "An AI that transcribes doctor-patient conversations for "
            "record-keeping convenience"
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        assert "Art. 6(1a)" in v.articles
        assert "Art. 50" in v.articles


# ── Normalisation helper — direct unit coverage ──────────────────────────


class TestNormaliseHelperUnit:
    """Direct coverage of the _normalise_for_marker_match helper so
    the contract is pinned at the unit level."""

    def test_hyphen_collapses_to_space(self) -> None:
        from app.engines.scenario_classifier import _normalise_for_marker_match

        assert _normalise_for_marker_match("predictive-policing") == (
            "predictive policing"
        )
        assert _normalise_for_marker_match("Credit-Scoring") == "credit scoring"

    def test_unicode_dashes_normalised_then_collapsed(self) -> None:
        from app.engines.scenario_classifier import _normalise_for_marker_match

        # Non-breaking hyphen (U+2011) → ASCII hyphen → space
        assert _normalise_for_marker_match("predictive‑policing") == (
            "predictive policing"
        )
        # En dash (U+2013) → ASCII hyphen → space
        assert _normalise_for_marker_match("credit–scoring") == (
            "credit scoring"
        )

    def test_space_form_unchanged_modulo_case(self) -> None:
        from app.engines.scenario_classifier import _normalise_for_marker_match

        assert _normalise_for_marker_match("Predictive Policing") == (
            "predictive policing"
        )
        assert _normalise_for_marker_match("CREDIT SCORING") == "credit scoring"
