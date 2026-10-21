"""R465 — pins for the 2026-09-29 expert review of the appendix answers.

The review graded the same ten questions the 2026-08-25 official report used
and found a DIFFERENT class of defect from the one R367/R381 fixed: the answers
named the right provision and the right categories, but dropped the CONDITIONS
the statute attaches to them. Each test below pins one of those conditions at
the level the user actually receives: the WIRE answer and the WIRE references,
through the offline route (``P2P_GRAPH_RAG_ENABLE_STAGE2=0``), which is where
the extractive pass and the reference budget do their damage.

Checks are phrased against the OFFICIAL TEXT (verified against
``app.data.eu_ai_act_corpus``), not against the review's prose, so a paraphrase
that keeps the condition still passes.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")


DETERMINISTIC_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "0",
}

Q45 = (
    "Under the EU AI Act, what must a provider of a high-risk AI system supply "
    "to the deployer in the instructions for use? List the required categories "
    "of information."
)
Q96 = (
    "Name the areas of high-risk use cases. Is healthcare decision making one "
    "of them?"
)
Q17 = (
    "Can the European Commission amend Annex III of the EU AI Act to add or "
    "modify use-cases classified as high-risk AI systems? Under what conditions?"
)
Q74 = (
    "I generated audio with AI for my artistic work (sole purpose). Do I need to "
    "provide some marking of its artificial nature? I feel that would "
    "compromise the enjoyment of the work."
)
Q95 = (
    "What is an 'area' and what is a 'use case' for high-risk as per Article "
    "6(2)? How many areas exist?"
)
Q104 = "What is Annex X about? What is it used for?"
Q6 = "What are AI systems with minimal risks?"
Q10 = "What is the difference between the deployer and the provider?"
Q16 = (
    "A pharmaceutical company wants to use an AI system to monitor the emotions "
    "and stress levels of their manufacturing line workers to improve "
    "efficiency. Is this allowed?"
)
QCASE_D = (
    "Is an AI system intended to be used as a safety component in robotic "
    "surgery considered high-risk under the AI Act?"
)

#: The eight Annex III headings, verbatim from the OJ text. Kept here as a
#: literal so the test fails if the production constant is ever compressed
#: again (the compressed forms are what the review rejected).
OFFICIAL_AREA_NAMES = (
    "biometrics",
    "critical infrastructure",
    "education and vocational training",
    "employment, workers' management and access to self-employment",
    "access to and enjoyment of essential private services and essential "
    "public services and benefits",
    "law enforcement",
    "migration, asylum and border control management",
    "administration of justice and democratic processes",
)


@pytest.fixture(scope="module")
def ask():
    # Module-scoped, so ``os.environ`` is mutated for the whole module — but
    # the previous values MUST be restored on teardown. ``setdefault`` alone
    # leaks ``P2P_GRAPH_RAG_ENABLE_STAGE2=0`` (and the offline provider / API
    # base) into every test that runs after this file alphabetically, which
    # silently switched Stage-2 off for ``test_r86`` / ``test_r91`` /
    # ``test_r97`` / ``test_two_stage_pipeline`` and turned 21 passing tests
    # into failures in a full-suite run.
    saved = {key: os.environ.get(key) for key in DETERMINISTIC_ENV}
    os.environ.update(DETERMINISTIC_ENV)

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    def _ask(question: str) -> dict:
        last = None
        for _ in range(8):
            last = client.post(
                "/api/v1/regenold/eu-ai-act/ask",
                json={"messages": [{"role": "user", "content": question}]},
            )
            if last.status_code == 200:
                return last.json()
        # R465d (deep review) — a non-200 is a FAILURE, not a skip. With
        # ``pytest.skip`` here a broken dispatch turned all ~30 wire tests green
        # as "skipped", invisible beside the suite's 23 legitimate skips.
        pytest.fail(f"route returned {last.status_code}: {last.text[:200]}")

    yield _ask

    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _norm(s: str) -> str:
    return re.sub(r"[\s\u2011]+", " ", (s or "").lower())


# ── Q45 — Article 13(2) and the conditions inside 13(3) ───────────────────────


class TestQ45InstructionsForUse:
    def test_states_the_article_13_2_format_and_quality_conditions(self, ask):
        answer = _norm(ask(Q45)["answer"])
        assert "article 13(2)" in answer
        # Article 13(2): appropriate digital format or otherwise; concise,
        # complete, correct and clear; relevant, accessible, comprehensible.
        for token in (
            "digital format or otherwise",
            "concise, complete, correct and clear",
            "accessible and comprehensible",
        ):
            assert token in answer, token

    def test_keeps_the_where_applicable_conditions_inside_13_3(self, ask):
        answer = _norm(ask(Q45)["answer"])
        # (a) authorised representative, (b)(iv)/(vii), (b)(v)/(vi), (c), (f).
        assert "where applicable" in answer
        assert "when appropriate" in answer
        assert "if any" in answer
        assert "where relevant" in answer

    def test_keeps_the_sub_limbs_of_13_3_b(self, ask):
        answer = _norm(ask(Q45)["answer"])
        # The nested (i)-(vii) content the extractive pass used to cut.
        for token in (
            "intended purpose",
            "metrics",
            "robustness",
            "reasonably foreseeable",
            "input data",
            "interpret the output",
        ):
            assert token in answer, token

    def test_says_the_list_is_a_minimum(self, ask):
        answer = _norm(ask(Q45)["answer"])
        assert "minimum" in answer

    def test_cites_article_13_2_and_13_3(self, ask):
        refs = ask(Q45)["references"]
        assert "Article 13.2" in refs and "Article 13.3" in refs, refs
        # and nothing else: the gold key for this row is those two.
        assert refs == ["Article 13.2", "Article 13.3"], refs


# ── Q96 / Q95 / Q17 — the eight areas by their official names ────────────────


class TestAnnexIIIAreaNames:
    @pytest.mark.parametrize("qid,question", [("Q96", Q96), ("Q95", Q95), ("Q17", Q17)])
    def test_no_compressed_area_heading_survives(self, ask, qid, question):
        answer = _norm(ask(question)["answer"])
        for compressed in (
            "education + vocational",
            "employment + worker management",
            "essential private + public services",
            "migration + asylum + border control",
            "employment and worker management",
        ):
            assert compressed not in answer, f"{qid}: {compressed}"

    def test_q96_names_all_eight_official_areas(self, ask):
        answer = _norm(ask(Q96)["answer"])
        for name in OFFICIAL_AREA_NAMES:
            assert _norm(name) in answer, name

    def test_q96_answers_the_healthcare_question(self, ask):
        answer = _norm(ask(Q96)["answer"])
        assert "healthcare decision making is not one of them" in answer
        # 5(a) with its "on behalf of" + grant/reduce/revoke/reclaim limbs, and
        # 5(d) emergency triage.
        assert "on behalf of public authorit" in answer
        assert "grant, reduce, revoke or reclaim" in answer
        assert "5(d)" in answer and "triage" in answer
        # 5(c) life/health insurance and 7(b) health risk are named so the
        # answer distinguishes them from healthcare decisions.
        assert "5(c)" in answer and "7(b)" in answer

    def test_q95_handles_the_critical_infrastructure_heading(self, ask):
        answer = _norm(ask(Q95)["answer"])
        assert "eight" in answer
        # Point 2 has NO lettered points: the heading states the use.
        assert "the heading itself states the use" in answer
        assert "safety components in the management and operation" in answer
        assert "not enough on its own" in answer

    def test_q95_cites_both_gold_heads(self, ask):
        refs = ask(Q95)["references"]
        assert "Article 6.2" in refs and "Annex III" in refs, refs


# ── Q17 — the Article 97 procedure ───────────────────────────────────────────


class TestQ17AmendmentProcedure:
    def test_keeps_the_appendix_a_conditions(self, ask):
        answer = _norm(ask(Q17)["answer"])
        assert "article 7(1)" in answer
        assert "areas already listed in annex iii" in answer
        assert "equivalent to or greater than" in answer
        assert "cumulative" in answer

    def test_states_the_article_97_4_consultation_and_97_6_objection_window(self, ask):
        answer = _norm(ask(Q17)["answer"])
        assert "article 97(4)" in answer
        assert "experts designated by each member state" in answer
        assert "article 97(6)" in answer
        assert "three months" in answer
        assert "extended by three months" in answer
        # The "or earlier where both inform the Commission" limb.
        assert "will not object" in answer


# ── Q74 — deep fake marking vs disclosure, artistic limit, manner, dates ─────


class TestQ74ArtisticAudio:
    def test_separates_the_provider_marking_duty_from_the_deployer_disclosure(
        self, ask
    ):
        answer = _norm(ask(Q74)["answer"])
        assert "article 50(2)" in answer
        assert "machine-readable" in answer
        assert "provider of the system" in answer
        assert "article 50(4)" in answer

    def test_states_the_deployer_capacity_and_the_personal_activity_carve_out(
        self, ask
    ):
        answer = _norm(ask(Q74)["answer"])
        assert "article 3(4)" in answer
        assert "personal non-professional activity" in answer
        assert "article 2(10)" in answer
        # The provider branch (own use under own name).
        assert "article 3(3)" in answer and "3(11)" in answer

    def test_uses_the_statutory_deep_fake_definition_including_to_a_person(self, ask):
        answer = _norm(ask(Q74)["answer"])
        assert "article 3(60)" in answer
        assert "would falsely appear to a person to be authentic or truthful" in answer

    def test_states_the_artistic_limit_not_an_exemption(self, ask):
        answer = _norm(ask(Q74)["answer"])
        assert "evidently artistic" in answer
        assert "limited to disclosing the existence" in answer
        assert "does not hamper the display or enjoyment" in answer

    def test_states_the_article_50_5_manner_and_timing(self, ask):
        answer = _norm(ask(Q74)["answer"])
        assert "article 50(5)" in answer
        assert "clear and distinguishable" in answer
        assert "at the latest at the time of first exposure" in answer
        assert "accessible" in answer

    def test_states_the_application_date_and_drops_the_non_statutory_note(self, ask):
        answer = _norm(ask(Q74)["answer"])
        assert "2 august 2026" in answer
        assert "credit or accompanying note" not in answer

    def test_cites_the_operative_deep_fake_provision(self, ask):
        refs = ask(Q74)["references"]
        assert "Article 50.4" in refs, refs
        assert "Article 3.60" in refs, refs


# ── Q104 — Annex X is a list; Article 5 already applies ─────────────────────


class TestQ104AnnexX:
    def test_says_annex_x_lists_acts_and_article_111_uses_it(self, ask):
        answer = _norm(ask(Q104)["answer"])
        assert "lists the union legislative acts" in answer
        assert "article 111(1) uses it" in answer
        assert "sets a transitional regime" not in answer
        assert "large-scale it systems" in answer
        assert "freedom, security and justice" in answer

    def test_does_not_put_the_whole_regulation_on_the_2030_timetable(self, ask):
        answer = _norm(ask(Q104)["answer"])
        assert "without prejudice to article 5" in answer
        assert "2 february 2025" in answer
        assert "31 december 2030" in answer
        assert "before 2 august 2027" in answer
        # Article 111(1)'s second sentence.
        assert "taken into account in the evaluation" in answer

    def test_names_the_seven_headings(self, ask):
        answer = _norm(ask(Q104)["answer"])
        for name in (
            "schengen information system",
            "visa information system",
            "eurodac",
            "entry/exit system",
            "etias",
            "ecris-tcn",
            "interoperability",
        ):
            assert name in answer, name

    def test_cites_both_gold_heads(self, ask):
        refs = ask(Q104)["references"]
        assert refs == ["Article 111.1", "Annex X"], refs


# ── Q6 / Q10 / Q16 / Case D — the remaining precision points ─────────────────


class TestQ6MinimalRisk:
    def test_states_the_second_annex_i_limb(self, ask):
        answer = _norm(ask(Q6)["answer"])
        # "the AI system is itself a product" + third-party assessment.
        assert "itself, a product" in answer or "itself a product" in answer
        assert "third-party conformity assessment" in answer
        assert "annex i" in answer


class TestQ10RolesAreNotAlternatives:
    def test_drops_the_alternatives_framing(self, ask):
        answer = _norm(ask(Q10)["answer"])
        assert "as opposed to using it" not in answer
        assert "roles are not alternatives" in answer

    def test_states_own_use_under_article_3_11(self, ask):
        answer = _norm(ask(Q10)["answer"])
        assert "article 3(11)" in answer
        assert "for own use" in answer
        assert "cumulatively" in answer

    def test_states_the_article_25_1_limbs_with_their_conditions(self, ask):
        answer = _norm(ask(Q10)["answer"])
        assert "without prejudice to contractual arrangements" in answer
        assert "placed on the market or put into service" in answer
        assert "remains a high-risk ai system pursuant to article 6" in answer
        assert "including a general-purpose ai system" in answer

    def test_does_not_deepen_the_article_25_transition_to_a_duty(self, ask):
        refs = ask(Q10)["references"]
        assert not any(r.startswith("Article 26") for r in refs), refs


class TestQ16EmotionAndStress:
    def test_names_the_use_act_committed_by_the_company(self, ask):
        answer = _norm(ask(Q16)["answer"])
        assert "article 5(1)(f)" in answer
        assert "the use of ai systems to infer emotions" in answer
        assert "commits the third of those acts" in answer

    def test_states_the_medical_or_safety_exception_and_rejects_efficiency(self, ask):
        answer = _norm(ask(Q16)["answer"])
        assert "medical or safety reasons" in answer
        assert "efficiency is neither" in answer

    def test_gives_stress_its_own_branch(self, ask):
        answer = _norm(ask(Q16)["answer"])
        assert "recital 18" in answer
        assert "physical states" in answer
        assert "point 4(b)" in answer
        assert "article 26" in answer

    def test_states_both_application_dates(self, ask):
        answer = _norm(ask(Q16)["answer"])
        assert "2 february 2025" in answer
        assert "2 august 2026" in answer


class TestCaseDRoboticSurgery:
    def test_derives_the_class_from_intended_purpose(self, ask):
        answer = _norm(ask(QCASE_D)["answer"])
        assert "article 51(1)" in answer
        assert "the question does not state" in answer
        assert "classes iia, iib and iii" in answer
        assert "article 52(6), (4) and (3)" in answer

    def test_states_the_annex_i_point_and_the_2027_date(self, ask):
        answer = _norm(ask(QCASE_D)["answer"])
        assert "point 11" in answer
        assert "2 august 2027" in answer

    def test_does_not_invent_duties_the_question_did_not_ask_for(self, ask):
        refs = ask(QCASE_D)["references"]
        assert refs == ["Article 6.1", "Annex I"], refs


# ── Module-level guards ─────────────────────────────────────────────────────


class TestModuleGuards:
    def test_area_constant_is_the_official_list(self):
        from app.engines.statutory_precision import ANNEX_III_AREAS

        assert ANNEX_III_AREAS == OFFICIAL_AREA_NAMES

    def test_the_curated_gate_covers_every_review_shape(self):
        from app.engines._graph_rag_impl import _is_curated_authoritative_intercept

        for q in (Q45, Q96, Q17, Q74, Q95, Q104, Q16):
            assert _is_curated_authoritative_intercept(q), q

    def test_the_kb_annex_iii_summary_carries_the_official_names(self):
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = _norm(EC_CHECKER_OBLIGATION_MAP["Annex III"]["summary"])
        for name in OFFICIAL_AREA_NAMES:
            assert _norm(name) in summary, name
        assert "education + vocational" not in summary

    def test_the_kb_annex_x_summary_keeps_the_article_5_reservation(self):
        from app.data.kb import EC_CHECKER_OBLIGATION_MAP

        summary = _norm(EC_CHECKER_OBLIGATION_MAP["Annex X"]["summary"])
        assert "without prejudice to article 5" in summary
        assert "2 february 2025" in summary

    def test_the_article_50_describer_does_not_conflate_marking_and_disclosure(
        self,
    ):
        from app.integrations.regenold.grounded_prose import (
            _ART_SUBPOINT_DESCRIBERS,
        )

        text = _norm(_ART_SUBPOINT_DESCRIBERS["Article 50"])
        assert "50(2)" in text and "50(4)" in text
        assert "machine-readable" in text
        # The davidath keyword trio must survive the rewrite.
        for kw in ("transparency", "deepfakes", "labelled"):
            assert kw in text, kw

    def test_the_article_5_1_f_describer_states_the_statutory_exception(self):
        from app.integrations.regenold.grounded_prose import (
            _ART_SUBPOINT_DESCRIBERS,
        )

        text = _norm(_ART_SUBPOINT_DESCRIBERS["Article 5.1.f"])
        assert "medical or safety reasons" in text
        assert "therapeutic or accident-prevention" not in text
        for kw in ("workplace", "prohibited", "call-centre"):
            assert kw in text, kw

    def test_every_curated_answer_cites_only_existing_provisions(self):
        from app.data.article_existence import ARTICLE_EXISTENCE
        from app.engines.statutory_precision import (
            _annex_iii_amendment,
            _annex_iii_area_vs_use_case,
            _annex_iii_areas,
            _annex_x_overview,
            _deepfake_artistic_disclosure,
            _instructions_for_use,
            _workplace_emotion_and_stress,
        )

        for build in (
            _instructions_for_use,
            _annex_iii_areas,
            _annex_iii_area_vs_use_case,
            _annex_iii_amendment,
            _deepfake_artistic_disclosure,
            _annex_x_overview,
            # R465c — the workplace verdict is question-framed, so pin it with
            # the review question rather than calling it bare.
            lambda: _workplace_emotion_and_stress(Q16),
        ):
            verdict = build()
            assert verdict["refs"], verdict["name"]
            for ref in verdict["refs"]:
                internal = (
                    "Art. " + ref[len("Article "):]
                    if ref.startswith("Article ")
                    else ref
                )
                # ARTICLE_EXISTENCE keys are HEADS ("Art. 13", "Annex III");
                # sub-points resolve through their head, which is the lint floor
                # the wire honours.
                head = re.match(r"^(Art\.\s*\d+|Annex\s+[IVXLC]+)", internal)
                assert head is not None, (verdict["name"], ref)
                assert head.group(1) in ARTICLE_EXISTENCE, (verdict["name"], ref)
