"""R321 — regression tests for the review fixes.

Every test here pins a defect that was MEASURED on the live code, not inferred.
Each docstring records the measurement so a future round can tell a real
regression from a contract change.
"""
from __future__ import annotations

import os

import pytest


# ── Foreign-instrument citation leak (Critical) ─────────────────────────────


class TestForeignInstrumentRefLeak:
    """`GDPR Art. 5` must never be promoted to AI Act `Article 5`.

    MEASURED before the fix::

        _add_prose_named_refs(["Article 27"],
            "...under EU Charter Art. 21 and on personal data under GDPR
             Art. 5, complementing GDPR Art. 35 DPIA duties.")
        -> ['Article 27', 'Article 21', 'Article 5', 'Article 35']

    Article 5 is the prohibited-practices article, so that is a confidently
    wrong legal claim in a wire-legal shape. The pre-existing guard only
    looked AHEAD ("Article 50 of the GDPR"); this covers the PREFIX form,
    which is exactly what ``kg_context`` injects into the Stage-2 context.
    """

    @pytest.mark.parametrize(
        "prose",
        [
            "The assessment evaluates non-discrimination under EU Charter Art. 21.",
            "Personal data processing is governed by GDPR Art. 5.",
            "This complements GDPR Art. 35 DPIA duties.",
            "Conformity follows MDR Article 52 for class IIb devices.",
            "See Directive Article 9 for the sectoral rule.",
        ],
    )
    def test_foreign_instrument_prefix_never_leaks(self, prose: str) -> None:
        from app.routes.regenold import _add_prose_named_refs

        base = ["Article 27"]
        out = _add_prose_named_refs(list(base), prose, cap=4)
        assert out == base, f"foreign-instrument number leaked onto the wire: {out}"

    def test_real_ai_act_mentions_are_still_promoted(self) -> None:
        """The guard must not make the whole pass inert."""
        from app.routes.regenold import _add_prose_named_refs

        prose = (
            "Under Article 13 the provider must ensure transparency, and "
            "Article 14 requires human oversight."
        )
        out = _add_prose_named_refs(["Article 26"], prose, cap=4)
        assert "Article 13" in out and "Article 14" in out

    def test_ai_act_mention_after_a_gdpr_sentence_still_promoted(self) -> None:
        """Only an IMMEDIATELY preceding qualifier suppresses (24-char window)."""
        from app.routes.regenold import _add_prose_named_refs

        prose = (
            "The GDPR governs personal data. Separately, Article 10 of this "
            "Regulation governs data governance."
        )
        out = _add_prose_named_refs(["Article 26"], prose, cap=4)
        assert "Article 10" in out


# ── FRIA / Article 27(1) (Critical) ─────────────────────────────────────────


class TestFRIAArticle27Trigger:
    """Article 27(1), verbatim, has three conjunctive conditions.

    MEASURED before the fix: a bank doing credit scoring — the case
    Article 27(1) names EXPLICITLY via Annex III 5(b) — returned
    ``fria_required=False``, while a private manufacturer screening its own
    job applicants returned ``True``. Cause: ``has_trigger = any(...) or
    is_deployer`` with ``role`` defaulting to ``"deployer"``.
    """

    @pytest.mark.parametrize(
        "text,role,expected",
        [
            # Annex III 5(b) — named explicitly in Article 27(1)
            ("We are a bank deploying an AI system to evaluate the "
             "creditworthiness of natural persons.", "deployer", True),
            # Annex III 5(c)
            ("We deploy an AI system for risk assessment and pricing in "
             "relation to life insurance for natural persons.", "deployer", True),
            # public authority + Annex III 5(a)
            ("We are a public authority deploying AI to evaluate the eligibility "
             "of natural persons for essential public assistance benefits "
             "including healthcare services.", "deployer", True),
            # Annex III point 2 — EXPLICITLY carved out by Article 27(1)
            ("We are a public body deploying an AI safety component in the "
             "management of critical infrastructure for the supply of "
             "electricity.", "deployer", False),
            # neither a public-law body nor a public-service provider, and not 5(b)/(c)
            ("We are a private manufacturing company using AI to screen job "
             "applicants for our own hiring.", "deployer", False),
            # a provider is not a deployer
            ("We are a provider building a recruitment AI system that we sell "
             "to other companies.", "provider", False),
        ],
    )
    def test_trigger_matches_verbatim_article_27_1(
        self, text: str, role: str, expected: bool
    ) -> None:
        from app.engines.fria_evaluator import evaluate_fria

        assert evaluate_fria(text, role=role).fria_required is expected

    def test_notification_is_cited_as_article_27_3_not_27_2(self) -> None:
        """Verbatim 27(3): 'the deployer shall notify the market surveillance
        authority of its results'. 27(2) is the first-use / reuse rule."""
        from app.engines.fria_evaluator import evaluate_fria

        actions = " ".join(
            evaluate_fria(
                "We are a bank deploying an AI system to evaluate the "
                "creditworthiness of natural persons."
            ).recommended_actions
        )
        assert "Article 27(3)" in actions
        assert "market surveillance authority" in actions.lower()

    def test_charter_ids_can_never_be_read_as_ai_act_refs(self) -> None:
        """Articles 1/7/8/21/47 all EXIST in the AI Act, so an unprefixed
        Charter id would pass the ARTICLE_EXISTENCE lint and ship as a wrong
        AI Act citation."""
        from app.data.article_existence import ARTICLE_EXISTENCE
        from app.engines.fria_evaluator import CHARTER_CATALOG, get_charter_mapping

        for cid, art in CHARTER_CATALOG.items():
            assert cid.startswith("Charter "), cid
            assert art.article_id.startswith("Charter "), art.article_id
            assert cid not in ARTICLE_EXISTENCE
        assert all(c.startswith("Charter ") for c in get_charter_mapping("justice"))


# ── Article 6(3) / 53(2) scope (Critical) ───────────────────────────────────


class TestDerogationAndExemptionScope:
    """Art 6(3) derogates from PARAGRAPH 2 (Annex III) only; Art 53(2)
    relieves a MODEL PROVIDER of two Art 53(1) duties and says nothing about
    a deployer's system being high-risk."""

    def test_art_6_3_does_not_reach_annex_i(self) -> None:
        from app.engines.scenario_classifier import classify_scenario_query

        v = classify_scenario_query(
            "We are a provider of an AI system that is a safety component of a "
            "surgical robot regulated as a medical device under the MDR, "
            "intended to perform a narrow procedural task, in the healthcare "
            "domain."
        )
        assert v is not None
        assert v.risk_level == "high-risk-annex-i"
        assert "Art. 9" in v.articles, "the Section 2 chain must survive"

    def test_art_53_2_does_not_override_a_high_risk_deployer(self) -> None:
        from app.engines.scenario_classifier import classify_scenario_query

        v = classify_scenario_query(
            "We are a deployer offering a CV screening system built on an "
            "open-weights general purpose AI model, intended to rank job "
            "applicants, in the recruitment domain."
        )
        assert v is not None
        assert v.risk_level == "high-risk"
        assert "Art. 27" in v.articles, "the FRIA duty must survive"

    def test_a_genuine_annex_iii_derogation_still_fires(self) -> None:
        """The narrowing must not make the feature inert."""
        from app.engines.scenario_classifier import classify_scenario_query

        v = classify_scenario_query(
            "We are a provider offering a system intended to perform a narrow "
            "procedural task, to de-duplicate records, in the recruitment domain."
        )
        assert v is not None
        assert v.risk_level == "art6_3_derogated"


# ── Env-parse fail-closed (Important) ───────────────────────────────────────


class TestLiveSentenceCapFailsClosed:
    """MEASURED before the fix: '' / '  ' / 'false' / 'no' / 'disabled' /
    'four' all ENABLED the cap at 4, and '-2' clamped to ONE sentence."""

    @pytest.mark.parametrize(
        "raw", ["", "   ", "0", "off", "no", "false", "disabled", "unlimited",
                "-1", "-2", "abc", "four", "4.0"],
    )
    def test_non_positive_integer_means_off(self, raw: str, monkeypatch) -> None:
        from app.integrations.regenold import models as M

        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", raw)
        M.set_answer_no_cap(True)
        text = " ".join(
            f"Sentence number {i} carries prose long enough to exceed the cap."
            for i in range(1, 9)
        )
        out = M.normalise_answer_for_regenold(text, question="What are the obligations?")
        assert len(M._split_sentences(out)) > 4, f"{raw!r} must not enable the cap"

    def test_an_explicit_positive_integer_still_enables_it(self, monkeypatch) -> None:
        from app.integrations.regenold import models as M

        monkeypatch.delenv("REGENOLD_MAX_ANSWER_SENTENCES", raising=False)
        monkeypatch.setenv("REGENOLD_LIVE_SENTENCE_CAP", "4")
        M.set_answer_no_cap(True)
        text = " ".join(
            f"Sentence number {i} carries prose long enough to exceed the cap."
            for i in range(1, 9)
        )
        out = M.normalise_answer_for_regenold(text, question="What are the obligations?")
        assert len(M._split_sentences(out)) <= 4


# ── Deploy safety (Critical) ────────────────────────────────────────────────


class TestDeploySafety:
    def test_healthz_does_no_llm_call_by_default(self) -> None:
        """/healthz is Railway's healthcheckPath under a 30 s timeout. As
        shipped it fired a live Groq completion whose budget fell back to the
        60 s singleton default."""
        from app.main import _healthz_probe_enabled

        assert _healthz_probe_enabled() is False

    @pytest.mark.parametrize("val,expected", [("1", True), ("true", True),
                                              ("0", False), ("", False)])
    def test_healthz_probe_is_opt_in(self, val: str, expected: bool, monkeypatch) -> None:
        from app.main import _healthz_probe_enabled

        monkeypatch.setenv("REGENOLD_HEALTHZ_PROBE", val)
        assert _healthz_probe_enabled() is expected
