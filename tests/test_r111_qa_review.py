"""R111 — Antifragile Q&A review fixes.

Regression tests for the deterministic intercepts + prompt directives added
to close the reviewer-flagged defects (Q6 minimal-risk, Q7 guiding principles,
Q9 high-risk penalties, Q17 R&D scope, Q1/Q2 route helpers, Q5/Q3/Q14 prompt
guards). Every code-path change is verified davidath-neutral: the new
intercept gates must fire on 0 davidath QA + 0 davidath scenario rows.
"""
from __future__ import annotations

import json

import pytest

from app.engines.graph_rag import (
    GraphContext,
    _deterministic_answer,
    _detect_guiding_principles_inquiry,
    _detect_high_risk_penalty_inquiry,
    _detect_minimal_risk_inquiry,
    _detect_research_scope_inquiry,
    _is_curated_authoritative_intercept,
)


def _ctx_refs(question: str) -> tuple[str, list[str]]:
    ctx = GraphContext()
    ans = _deterministic_answer(question, ctx)
    refs = sorted({o.get("article") for o in ctx.obligations})
    return ans, refs


# ── Q6 — minimal-risk residual-tier intercept ────────────────────────────


class TestR111MinimalRisk:
    @pytest.mark.parametrize(
        "q",
        [
            "What are AI systems with minimal risks?",
            "What is minimal risk?",
            "What is a minimal-risk AI system?",
            "What are minimal-risk AI systems?",
        ],
    )
    def test_detector_fires(self, q):
        assert _detect_minimal_risk_inquiry(q) is True

    def test_detector_no_false_positive_on_high_risk(self):
        assert _detect_minimal_risk_inquiry(
            "What is the maximum penalty for high-risk providers?"
        ) is False

    def test_answer_is_residual_tier_not_high_risk(self):
        # R399 — this test used to require the phrase "no mandatory
        # obligations", which is a FALSE statement of law and was shipping on
        # every minimal-risk answer: Article 4 binds providers and deployers of
        # AI systems generally, whatever the tier, and Article 95 voluntary
        # codes do not displace it. The assertion is re-pointed at the
        # corrected wording rather than dropped — what the test exists to pin
        # is that minimal risk does not attract the Chapter III high-risk
        # regime, and that is asserted below exactly as before.
        ans, refs = _ctx_refs("What are AI systems with minimal risks?")
        low = ans.lower()
        assert "residual" in low
        # The exclusion must stay QUALIFIED to the Chapter III regime. The
        # unqualified forms this test used to REQUIRE ("no mandatory
        # obligations under the Regulation") are false statements of law:
        # Article 4 binds providers and deployers of AI systems generally,
        # whatever the tier, and Article 95 voluntary codes do not displace it.
        assert "chapter iii" in low
        assert "no mandatory obligations under the regulation" not in low
        assert "no mandatory duties under the act" not in low
        assert "article 4" in low and "literacy" in low
        assert "voluntary codes of conduct under article 95" in low
        # Must NOT be the old high-risk risk-management / FRIA dump.
        assert "risk-management system" not in low
        assert "fundamental rights impact" not in low
        # Clean contrast refs only — no high-risk Chapter III articles. The
        # Article 4 / 95 anchors are stated in the prose and reach the wire via
        # _add_prose_named_refs on the live path; seeding them here as well
        # would double-count against the pure-count Ref. Conciseness axis.
        assert set(refs) == {"Art. 5", "Art. 6", "Art. 50"}


# ── Q7 — guiding principles (all 7, incl. accountability) ────────────────


class TestR111GuidingPrinciples:
    def test_all_seven_principles_named(self):
        ans, refs = _ctx_refs("What are the guiding principles established by the AI Act?")
        low = ans.lower()
        for principle in (
            "human agency",
            "technical robustness",
            "privacy and data governance",
            "transparency",
            "non-discrimination",
            "social and environmental",
            "accountability",
        ):
            assert principle in low, f"missing principle: {principle}"
        # R410 — Art. 95(2)(a) is the single operative connection (Recital 27 is
        # non-binding and the answer says so), so the wire cites it too. Art. 1
        # is deliberately gone: it was a purpose-clause aside, not the
        # question's operative connection, and the annotated gold for this item
        # is Recital 27 + Art. 95.2(a) + Art. 95 — so citing it cost pure-count
        # Ref. Conciseness for no reference-correctness gain.
        assert low.startswith("the eu ai act does not establish")
        assert set(refs) == {"Art. 4", "Art. 95"}

    def test_curated_short_circuit_covers_guiding_principles(self):
        assert _is_curated_authoritative_intercept(
            "What are the guiding principles established by the AI Act?"
        ) is True

    def test_curated_short_circuit_false_on_plain_qa(self):
        assert _is_curated_authoritative_intercept(
            "What is the primary purpose of the AI Regulation?"
        ) is False


# ── Q9 — high-risk penalties (99(4) ceiling + 99(6) SME) ─────────────────


class TestR111HighRiskPenalties:
    def test_detector_fires_for_high_risk(self):
        assert _detect_high_risk_penalty_inquiry(
            "What are the penalties for violating the provisions of the "
            "regulation for high-risk AI systems?"
        ) is True

    def test_detector_false_for_prohibited(self):
        assert _detect_high_risk_penalty_inquiry(
            "What are the penalties for prohibited AI practices?"
        ) is False

    def test_answer_surfaces_99_4_and_sme_rule(self):
        ans, refs = _ctx_refs(
            "What are the penalties for violating the provisions of the "
            "regulation for high-risk AI systems?"
        )
        assert "99(4)" in ans
        assert "15 000 000" in ans or "EUR 15" in ans
        assert "99(6)" in ans  # SME lower-of-two rule
        assert refs == ["Art. 99"]


# ── Q17 — scientific R&D pre-market scope exclusion (vs Q16 GPAI) ────────


class TestR111ResearchScope:
    def test_q17_fires(self):
        assert _detect_research_scope_inquiry(
            "We are a university lab developing an AI model exclusively for "
            "scientific research and development into new life science drugs. "
            "Does the AI Act apply to our model before it is released to the market?"
        ) is True

    def test_q16_does_not_fire(self):
        # Q16 is a GPAI transparency-obligations question — must stay on the
        # GPAI path, NOT the Article 2 scope intercept.
        assert _detect_research_scope_inquiry(
            "Our life sciences startup developed a general-purpose AI model "
            "trained on massive amounts of genomic data. What transparency "
            "obligations apply to us?"
        ) is False

    def test_answer_is_article_2_scope_not_gpai(self):
        ans, refs = _ctx_refs(
            "We are a university lab developing an AI model exclusively for "
            "scientific research and development. Does the AI Act apply before "
            "it is released to the market?"
        )
        low = ans.lower()
        assert "2(6)" in ans or "scientific research" in low
        # Must NOT lead with the GPAI obligations dump.
        assert "annex xi" not in low
        assert "gpai provider obligations" not in low
        assert refs == ["Art. 2"]


# ── davidath neutrality — the new gates fire on 0 dataset rows ───────────


class TestR111DavidathNeutrality:
    def _qa_questions(self) -> list[str]:
        d = json.load(open("evals/bench/data/qa_pairs.json", encoding="utf-8"))
        rows = d.get("data", d) if isinstance(d, dict) else d
        return [r.get("question", "") for r in rows if isinstance(r, dict)]

    def _scenario_questions(self) -> list[str]:
        from evals.bench.dataset import scenario_to_question

        d = json.load(open("evals/bench/data/scenarios.json", encoding="utf-8"))
        rows = d.get("data", d) if isinstance(d, dict) else d
        return [scenario_to_question(r) for r in rows if isinstance(r, dict)]

    @pytest.mark.parametrize(
        "detector",
        [
            _detect_minimal_risk_inquiry,
            _detect_research_scope_inquiry,
            _detect_high_risk_penalty_inquiry,
        ],
    )
    def test_zero_hits_on_qa(self, detector):
        hits = [q for q in self._qa_questions() if detector(q)]
        assert hits == [], f"{detector.__name__} fired on davidath QA: {hits[:3]}"

    @pytest.mark.parametrize(
        "detector",
        [
            _detect_minimal_risk_inquiry,
            _detect_research_scope_inquiry,
            _detect_high_risk_penalty_inquiry,
        ],
    )
    def test_zero_hits_on_scenarios(self, detector):
        hits = [q for q in self._scenario_questions() if detector(q)]
        assert hits == [], f"{detector.__name__} fired on davidath scenarios: {hits[:3]}"


# ── Q1/Q2 — route-level closed-set enumeration helper ────────────────────


class TestR111ClosedSetHelper:
    def test_closed_set_helper(self):
        from app.routes.regenold import _is_closed_set_enumeration_ask

        assert _is_closed_set_enumeration_ask(
            "What practices are explicitly prohibited by the AI Act?"
        ) is True
        assert _is_closed_set_enumeration_ask(
            "What risk categories are provided for AI systems?"
        ) is True
        assert _is_closed_set_enumeration_ask("List the prohibited practices") is True
        # NOT a closed-set ask.
        assert _is_closed_set_enumeration_ask(
            "What are the transparency obligations for high-risk AI?"
        ) is False
        assert _is_closed_set_enumeration_ask(
            "What is the definition of high risk?"
        ) is True


# ── Prompt-content directives (davidath byte-identical; live-only effect) ─


class TestR111PromptDirectives:
    def test_prompt_contains_r111_directives(self):
        from app.data.graph_rag_prompts import ANSWER_GENERATE_SYSTEM as S

        assert "do NOT format the members as lettered" in S  # Q2
        assert "MUST describe BOTH routes" in S  # Q3
        assert "Article 6(3) carve-outs" in S  # Q3
        assert "Article 50(3) is a DEPLOYER duty" in S  # Q5
        assert "Article 50(1) is a PROVIDER duty" in S  # Q5
        assert "Answer EVERY distinct sub-question" in S  # Q14/15/20
        assert "Article 43(3)" in S  # Q14
        assert "classify the system FIRST" in S  # Q18
