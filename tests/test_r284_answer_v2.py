"""R284 — answer-correctness bundle (H3 classifier fixes + H1/H2 Stage-2 prompt).

The bundle master gate is ``REGENOLD_ANSWER_V2`` (default OFF = the ab_judge /
easyhard_ab baseline arm). H3 adds ``patterns_v2`` to three classification
topics so the wrong-verdict rows the literal patterns miss are rescued:
  * tp_v4_003 predictive-policing-by-profiling  -> Art 5(1)(d) prohibited
  * mt_v4_012 sensitive-attribute biometric inference -> Art 5(1)(g) prohibited
  * st_v4_006 critical-infrastructure supply-sector safety component -> Annex III(2)

These are LEGAL corrections scoped so they fire on 0/476 davidath rows (the
deterministic bench is byte-identical) and never flip the false-positive shapes
(victim-risk / product-safety-component / non-sensitive categorisation).
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

from app.engines import graph_rag as g
from app.engines._graph_rag_data import _CLASSIFICATION_TOPICS


@contextmanager
def answer_v2(value: str):
    prev = os.environ.get("REGENOLD_ANSWER_V2")
    os.environ["REGENOLD_ANSWER_V2"] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("REGENOLD_ANSWER_V2", None)
        else:
            os.environ["REGENOLD_ANSWER_V2"] = prev


_TOPICS = {t["name"]: t for t in _CLASSIFICATION_TOPICS}

# The three confirmed wrong-verdict probe rows (single-turn shapes that reach
# the classifier). mt_v4_012 is multi-turn; its rescue is covered by the raw
# pattern-match test below (its real prod form passes _is_classification_question,
# proven by the fact it reached the general fallback).
PREDICTIVE_Q = (
    "An AI predicts the likelihood that an individual will commit a crime based "
    "solely on profiling their personality traits and background, with no "
    "objective facts tied to a specific offence. Prohibited or high-risk "
    "law-enforcement use?"
)
GRID_Q = (
    "An AI system is used as a safety component to manage the supply of "
    "electricity on a national grid. How is it classified and under which article?"
)
BIOMETRIC_VERDICT_Q = (
    "Is biometric categorisation to infer someone's religion prohibited?"
)


class TestPatternsV2Present:
    def test_three_topics_carry_patterns_v2(self):
        for name in (
            "predictive_policing",
            "biometric_categorisation_sensitive",
            "critical_infrastructure",
        ):
            assert len(_TOPICS[name].get("patterns_v2", [])) >= 1, name

    def test_flag_helper_reads_env(self):
        with answer_v2("0"):
            assert g._answer_v2_enabled() is False
        with answer_v2("1"):
            assert g._answer_v2_enabled() is True


class TestH3RescuesWrongVerdicts:
    def test_predictive_policing_off_falls_through(self):
        with answer_v2("0"):
            assert g._detect_classification_topic(PREDICTIVE_Q) is None

    def test_predictive_policing_on_rescued(self):
        with answer_v2("1"):
            t = g._detect_classification_topic(PREDICTIVE_Q)
            assert t is not None and t["name"] == "predictive_policing"

    def test_grid_off_wrong_annex_i(self):
        with answer_v2("0"):
            t = g._detect_classification_topic(GRID_Q)
            assert t is not None and t["name"] == "annex_i_safety_component"

    def test_grid_on_rescued_to_critical_infrastructure(self):
        with answer_v2("1"):
            t = g._detect_classification_topic(GRID_Q)
            assert t is not None and t["name"] == "critical_infrastructure"

    def test_biometric_verdict_on_rescued(self):
        with answer_v2("1"):
            t = g._detect_classification_topic(BIOMETRIC_VERDICT_Q)
            assert t is not None and t["name"] == "biometric_categorisation_sensitive"

    def test_biometric_patterns_v2_cross_apostrophe(self):
        """mt_v4_012's real text ('infer users' religious ... biometric data')
        breaks the base pattern at the ' in "users'"; the v2 pattern crosses it."""
        mt = (
            "To sharpen targeting we now infer users' religious beliefs and "
            "political opinions from their biometric data. Is that a problem?"
        )
        bio = _TOPICS["biometric_categorisation_sensitive"]
        assert not any(p.search(mt) for p in bio["patterns"])
        assert any(p.search(mt) for p in bio["patterns_v2"])


class TestFalsePositiveExclusions:
    """The precise scoping must NOT flip legally-different shapes."""

    def test_victim_risk_stays_non_prohibited(self):
        # Art 5(1)(d) is prohibited only for COMMITTING a crime by profiling;
        # victim-risk assessment is high-risk, not prohibited.
        q = (
            "Is an AI system used by police to assess the risk of a person "
            "becoming a victim of violent crime high-risk?"
        )
        with answer_v2("1"):
            t = g._detect_classification_topic(q)
            assert t is None or t["name"] != "predictive_policing"

    def test_medical_device_safety_component_stays_annex_i(self):
        q = (
            "Is an AI system that is a safety component of an MRI scanner "
            "medical device high-risk?"
        )
        with answer_v2("1"):
            t = g._detect_classification_topic(q)
            assert t is not None and t["name"] == "annex_i_safety_component"

    def test_gas_appliance_product_stays_annex_i(self):
        # davidath SC#108 shape: a gas-appliance safety component under sectoral
        # conformity assessment is Annex I, not Annex III(2) critical infra.
        q = (
            "We are a provider, offering a residential heating safety ai, "
            "intended to ai safety component for automated gas valve control in "
            "residential heating systems, subject to eu gas appliance conformity "
            "assessment, in the product safety ai systems domain. Under the EU AI "
            "Act, what is the risk classification of this system and what are the "
            "key obligations on us as provider?"
        )
        with answer_v2("1"):
            t = g._detect_classification_topic(q)
            assert t is None or t["name"] != "critical_infrastructure"

    def test_gender_biometric_not_prohibited(self):
        q = "Is an AI system that infers a person's gender from their biometric data prohibited?"
        with answer_v2("1"):
            t = g._detect_classification_topic(q)
            assert t is None or t["name"] != "biometric_categorisation_sensitive"


class TestDavidathByteIdentical:
    """The whole H3 fix must fire on 0/476 davidath rows (deterministic bench
    regression guard). If this fails, a new pattern is over-reaching."""

    def test_zero_davidath_classification_changes(self):
        from evals.bench.dataset import (
            load_qa_pairs,
            load_scenarios,
            scenario_to_question,
        )

        qs = [r.get("question", "") for r in load_qa_pairs()]
        qs += [scenario_to_question(r) for r in load_scenarios()]

        def topic(q, flag):
            os.environ["REGENOLD_ANSWER_V2"] = flag
            t = g._detect_classification_topic(q)
            return t["name"] if t else None

        prev = os.environ.get("REGENOLD_ANSWER_V2")
        try:
            changed = [q for q in qs if topic(q, "0") != topic(q, "1")]
        finally:
            if prev is None:
                os.environ.pop("REGENOLD_ANSWER_V2", None)
            else:
                os.environ["REGENOLD_ANSWER_V2"] = prev
        assert changed == [], f"{len(changed)} davidath rows change classification: {changed[:3]}"


def test_answer_v2_in_engine_cache_key():
    """R30/R56/R79 cache-poisoning doctrine — the flag flips the engine answer
    (H3 refs + H1/H2 prose) so it must be in _engine_cache_key's env tuple."""
    import inspect

    from app.routes import regenold

    src = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_ANSWER_V2" in src


def test_r284_stage2_flags_default_off_and_in_cache_key():
    """The two default-OFF Stage-2 levers (H1 completeness + verify-verdict) read
    their env and are in the cache key (they flip the polished answer)."""
    import inspect

    from app.routes import regenold

    with answer_v2("0"):  # ensure a clean env baseline for the helpers
        os.environ.pop("REGENOLD_ANSWER_COMPLETE", None)
        os.environ.pop("REGENOLD_VERIFY_VERDICT", None)
        assert g._answer_complete_enabled() is False
        assert g._verify_verdict_enabled() is False
        os.environ["REGENOLD_ANSWER_COMPLETE"] = "1"
        os.environ["REGENOLD_VERIFY_VERDICT"] = "1"
        assert g._answer_complete_enabled() is True
        assert g._verify_verdict_enabled() is True
        os.environ.pop("REGENOLD_ANSWER_COMPLETE", None)
        os.environ.pop("REGENOLD_VERIFY_VERDICT", None)

    src = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_ANSWER_COMPLETE" in src
    assert "REGENOLD_VERIFY_VERDICT" in src
