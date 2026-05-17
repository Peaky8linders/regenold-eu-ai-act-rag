"""R41 Phase C.2/C.3 — Art. 6(1a) carve-out + Art. 6(3) exception tests.

Covers the Digital Omnibus Art. 6(1a) safety-component carve-out (the
rubric mover for the Regenold doctor-transcription probe) plus the
AI Guide Art. 6(3) four-exception list with its profiling override
from Recital 53.

Spec contract (R41_OMNIBUS_CHANGES.md §B4 + §C.5 + AI Guide §4):

* The carve-out returns a structured ``ScenarioVerdict`` citing
  ``Art. 6(1a)`` (NOT HRAIS) when:
    - the question matches one of ``_SAFETY_COMPONENT_CARVE_OUT_PATTERNS``,
    - AND no failure-endangers / safety-function override fires,
    - AND no Annex III high-risk marker fires,
    - AND either a role marker, an intended-use signal, or ≥2 distinct
      carve-out keywords concur (defence in depth).
* When a generative-content marker is present (e.g. transcription),
  the verdict also cites ``Art. 50`` for the transparency obligation
  that survives the safety-component exception.
* The Art. 6(3) exception fires when one of the four narrow procedural
  / preparatory / deviation-detection / output-improvement patterns
  appears AND no profiling marker fires (Recital 53 carves profiling
  systems OUT of the exception).
"""
from __future__ import annotations

import pytest

from app.engines.scenario_classifier import (
    ScenarioVerdict,
    classify_scenario_query,
)


# ── Art. 6(1a) — positive carve-out ──────────────────────────────────────


class TestSafetyComponentCarveOutFires:
    def test_hospital_scheduler_performance_optimisation(self) -> None:
        """A hospital scheduler for performance optimisation is NOT a
        safety component per the new Art. 6(1a) wording."""
        q = (
            "We are a hospital that uses an AI scheduler for performance "
            "optimisation"
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        assert "Art. 6(1a)" in v.articles
        # AI literacy still applies under Art. 4.
        assert "Art. 4" in v.articles

    def test_pure_convenience_question(self) -> None:
        """The bare ``Our AI is for convenience`` triggers the carve-out
        via the ``is for X`` intended-use signal."""
        q = "Our AI is for convenience."
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        assert "Art. 6(1a)" in v.articles

    def test_doctor_transcription_paraphrase_with_art50(self) -> None:
        """The Regenold doctor-transcription probe paraphrase must
        return a non-HRAIS verdict citing both Art. 6(1a) and Art. 50
        — transcription is generative content, so the transparency
        obligation survives the carve-out."""
        q = (
            "An AI that transcribes doctor-patient conversations for "
            "record-keeping convenience"
        )
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        assert "Art. 6(1a)" in v.articles
        assert "Art. 50" in v.articles
        # The verdict prose should mention the carve-out terms verbatim.
        assert "safety component" in v.answer.lower()
        assert "article 6(1a)" in v.answer.lower()

    def test_verdict_prose_matches_spec(self) -> None:
        """The verdict text must use the canonical spec phrasing."""
        q = "An AI used for automation and convenience"
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais"
        # Spec contract: "This system is not a safety component for the
        # purposes of the AI Act. Per Article 6(1a) …"
        assert "not a safety component" in v.answer.lower()
        assert "non-safety related" in v.answer.lower()


# ── Art. 6(1b) override — carve-out MUST defer ───────────────────────────


class TestSafetyComponentOverride:
    def test_malfunctioning_endangers_safety(self) -> None:
        """Even though ``automation`` could match the carve-out, the
        ``malfunctioning ... endangers safety`` 6(1b) override fires
        first — so the carve-out must defer."""
        q = (
            "We deploy an AI failure-detection system in nuclear "
            "reactors where malfunctioning endangers safety"
        )
        v = classify_scenario_query(q)
        # Carve-out must defer. The engine returns either HRAIS (if a
        # high-risk marker also fires via "critical infrastructure" /
        # "safety component") or None (no fast-path). Critically, the
        # verdict — if any — must NOT cite Art. 6(1a).
        if v is not None:
            assert v.risk_level != "non_hrais", (
                f"Carve-out leaked through 6(1b) override: {v}"
            )
            assert "Art. 6(1a)" not in v.articles

    def test_loss_of_life_override(self) -> None:
        q = (
            "We are a provider offering an AI for quality control of "
            "anaesthesia dosing where failure could lead to loss of life"
        )
        v = classify_scenario_query(q)
        if v is not None:
            assert v.risk_level != "non_hrais"
            assert "Art. 6(1a)" not in v.articles

    def test_safety_function_override(self) -> None:
        q = "Our AI is for automation but it also performs a safety function in the lift"
        v = classify_scenario_query(q)
        if v is not None:
            assert v.risk_level != "non_hrais"
            assert "Art. 6(1a)" not in v.articles


# ── Annex III gate — carve-out MUST defer ─────────────────────────────────


class TestAnnexIIIDeferral:
    def test_annex_iii_education_blocks_carve_out(self) -> None:
        """Carve-out term ``convenience`` is overpowered by the Annex
        III ``exam scoring`` marker — the system is HRAIS."""
        q = (
            "An AI for exam scoring used for record-keeping convenience "
            "in a school"
        )
        v = classify_scenario_query(q)
        # Either HRAIS or None — never non_hrais.
        if v is not None:
            assert v.risk_level != "non_hrais"
            assert "Art. 6(1a)" not in v.articles


# ── Art. 6(3) — narrow procedural / preparatory exceptions ──────────────


class TestArt6_3Exception:
    def test_narrow_procedural_task_fires(self) -> None:
        q = "A narrow procedural task to organise inbound emails"
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais_art6_3"
        assert "Art. 6(3)" in v.articles
        assert "Art. 4" in v.articles

    def test_preparatory_task_fires(self) -> None:
        q = "We deploy AI for a preparatory task before a credit decision"
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "non_hrais_art6_3"
        assert "Art. 6(3)" in v.articles


# ── Profiling override — Art. 6(3) exception MUST defer ─────────────────


class TestArt6_3ProfilingOverride:
    def test_profiling_overrides_deviation_detection(self) -> None:
        """Per Recital 53, an AI that ``detects deviations from
        decision-making patterns for individual profiling`` does NOT
        qualify for the Art. 6(3) exception — profiling overrides."""
        q = (
            "An AI that detects deviations from decision-making patterns "
            "for individual profiling"
        )
        v = classify_scenario_query(q)
        # Profiling override means the Art. 6(3) helper returns None.
        # The engine's general path then takes over; the verdict, if
        # any, must NOT cite Art. 6(3) as the non-HRAIS basis.
        if v is not None:
            assert v.risk_level != "non_hrais_art6_3", (
                f"Profiling override failed: {v}"
            )

    def test_automated_decision_making_overrides(self) -> None:
        q = (
            "An AI for a narrow procedural task that also performs "
            "automated decision-making about applicants"
        )
        v = classify_scenario_query(q)
        if v is not None:
            assert v.risk_level != "non_hrais_art6_3"


# ── Smoke: existing scenarios still work ─────────────────────────────────


class TestExistingScenariosUntouched:
    """Sanity check: the carve-out additions must NOT regress the
    existing scenario-classifier hot paths (prohibited / high-risk /
    limited / minimal)."""

    def test_subliminal_still_prohibited(self) -> None:
        q = "We are a provider offering a subliminal influence platform"
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "prohibited"

    def test_worker_monitoring_still_high_risk(self) -> None:
        q = (
            "We are a deployer using an AI for worker monitoring and "
            "performance evaluation of workers"
        )
        v = classify_scenario_query(q)
        assert v is not None
        # Worker-monitoring HRAIS markers fire BEFORE the carve-out
        # gate via the Annex III deferral — must not collapse to
        # non_hrais even though "performance" is in the text.
        assert v.risk_level == "high-risk"

    def test_chatbot_still_limited(self) -> None:
        q = "We are a provider offering a chatbot that interacts with natural persons"
        v = classify_scenario_query(q)
        assert v is not None
        assert v.risk_level == "limited"
