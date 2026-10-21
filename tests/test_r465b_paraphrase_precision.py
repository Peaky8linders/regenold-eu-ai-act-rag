"""R465b — the A/B paraphrase audit: the review's shapes under other phrasings.

R465 fixed the ten 2026-09-29 review questions. A position-swapped pairwise A/B
(``scratch/r465_ab_judge.py``) then re-asked each of those ten families in three
independently written phrasings — the honest test, because the ten questions are
rehearsed by construction. It found six paraphrases that were still wrong in
BOTH arms, i.e. defects the curated verdicts did not cover:

| paraphrase | what the wire did |
| --- | --- |
| \"Which details must a provider document for deployers in the instructions for use …\" | answered Article 26 deployer duties — a different provision |
| \"Which areas does Annex III list, and where does healthcare actually appear?\" | listed the eight areas and never placed healthcare |
| \"Which AI systems are neither prohibited nor high-risk, and what obligations remain?\" | answered with live biometric identification (Art. 5) |
| \"If my AI system is not high-risk, do any duties still apply?\" | never named Article 4 or Article 95 |
| \"Can a company be both the provider and the deployer of the same AI system?\" | a 12-reference transparency dump |
| \"What is the difference between placing on the market, putting into service and using …\" | the 68-term Article 3 glossary line |

and one that was worse than wrong: \"Our factory wants to detect worker stress to
optimise the production line. Is that prohibited?\" was refused by the SCOPE gate
as conversational (it names no AI system and no anchor keyword), and on a live
deployment the out-of-scope branch answered it from a general model, which
called stress detection \"biometric categorisation\" and asserted a high-risk
classification the Act does not give.

Every pin below is at the WIRE — the answer and references the user receives —
through the offline route, which is the regime the A/B measured.
"""
from __future__ import annotations

import os

import pytest

# R465d (deep review) — ``setdefault`` here runs BEFORE the fixture snapshots,
# so restoring the snapshot only restores "1" and the key stays set for the
# whole session. Record the real prior value first and put it back in teardown.
_PRIOR_SKIP_DOTENV = os.environ.get("REGENOLD_SKIP_DOTENV")
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

DETERMINISTIC_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "0",
}

IFU_DETAILS = (
    "Which details must a provider document for deployers in the instructions "
    "for use of a high-risk system?"
)
AREAS_HEALTHCARE = "Which areas does Annex III list, and where does healthcare actually appear?"
RESIDUAL = "Which AI systems are neither prohibited nor high-risk, and what obligations remain?"
NOT_HIGH_RISK = "If my AI system is not high-risk, do any duties still apply?"
DUAL_ROLE = "Can a company be both the provider and the deployer of the same AI system?"
THREE_ACTS = (
    "What is the difference between placing on the market, putting into service "
    "and using an AI system?"
)
STRESS_ONLY = (
    "Our factory wants to detect worker stress to optimise the production line. "
    "Is that prohibited?"
)
#: R465c — the two emotion-only phrasings of the same workplace question. Both
#: were answered from generic retrieval, and BOTH arms of the A/B named
#: Article 5(1)(f) plus the medical/safety exception while omitting the
#: Recital 18 stress / Annex III 4(b) branch the reference position grades.
EMOTION_EMPLOYEES = (
    "Is emotion recognition of employees allowed if the employer only wants to "
    "raise productivity?"
)
ARTICLE_5_WORKERS = (
    "Does Article 5(1)(f) prohibit using an emotion recognition system on "
    "workers, and what exception applies?"
)


@pytest.fixture(scope="module")
def ask():
    # Module-scoped, so ``os.environ`` is mutated for the whole module — but
    # the previous values MUST be restored on teardown. ``setdefault`` alone
    # leaks ``P2P_GRAPH_RAG_ENABLE_STAGE2=0`` and the offline provider / API
    # base into every test that runs after this file alphabetically, which
    # silently switched Stage-2 off downstream (see the same note in
    # ``tests/test_r465_statutory_precision.py``).
    saved = {key: os.environ.get(key) for key in DETERMINISTIC_ENV}
    os.environ.update(DETERMINISTIC_ENV)

    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    limiter_was_enabled = limiter.enabled
    limiter.enabled = False
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
        # R465d (deep review) — a non-200 is a FAILURE, not a skip: a raising
        # curated dispatch must not be able to turn the wire assertions green.
        pytest.fail(f"route returned {last.status_code}: {last.text[:200]}")

    yield _ask

    limiter.enabled = limiter_was_enabled
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    if _PRIOR_SKIP_DOTENV is None:
        os.environ.pop("REGENOLD_SKIP_DOTENV", None)
    else:
        os.environ["REGENOLD_SKIP_DOTENV"] = _PRIOR_SKIP_DOTENV


def _low(s: str) -> str:
    return (s or "").lower()


# ── Q45b — the instructions-for-use ask with "which details" ──────────────────


class TestInstructionsForUseDetailsPhrasing:
    def test_the_detector_accepts_which_details(self):
        from app.engines.statutory_precision import _detect_instructions_for_use

        assert _detect_instructions_for_use(IFU_DETAILS)

    def test_the_wire_answers_article_13_not_the_deployer_duties(self, ask):
        body = ask(IFU_DETAILS)
        answer = _low(body["answer"])
        assert "article 13(2)" in answer
        assert "digital format or otherwise" in answer
        # The pre-fix answer was the Article 26 deployer dump: log retention,
        # oversight assignment, market-surveillance cooperation.
        assert "article 26" not in answer
        assert "retain the logs" not in answer
        assert body["references"] == ["Article 13.2", "Article 13.3"]


# ── Q96b — the healthcare-placement phrasing ─────────────────────────────────


class TestAnnexIiiHealthcarePlacement:
    def test_the_wire_places_healthcare_inside_the_areas(self, ask):
        body = ask(AREAS_HEALTHCARE)
        answer = _low(body["answer"])
        assert "healthcare decision making is not one of them" in answer
        assert "5(a)" in answer and "5(d)" in answer
        assert "emergency healthcare patient triage" in answer
        # Head or deepened sub-point: the answer now anchors the healthcare
        # sentences ("Annex III, point 5(a)"), so the R386 deepener surfaces
        # Annex III.5.a and R325 collapses the parent head. Both resolve.
        assert body["references"], "no citation at all on the healthcare ask"
        assert all(r.startswith("Annex III") for r in body["references"]), body["references"]

    def test_all_eight_official_area_names_survive(self, ask):
        answer = _low(ask(AREAS_HEALTHCARE)["answer"])
        for name in (
            "biometrics",
            "critical infrastructure",
            "education and vocational training",
            "employment, workers' management and access to self-employment",
            "access to and enjoyment of essential private services",
            "law enforcement",
            "migration, asylum and border control management",
            "administration of justice and democratic processes",
        ):
            assert name in answer, name


# ── Q6b — the residual-class shapes ──────────────────────────────────────────


class TestResidualClassPhrasings:
    @pytest.mark.parametrize("question", [RESIDUAL, NOT_HIGH_RISK])
    def test_the_detector_fires_without_the_word_minimal(self, question):
        from app.engines import _graph_rag_impl as E

        assert E._detect_minimal_risk_inquiry(question)

    @pytest.mark.parametrize("question", [RESIDUAL, NOT_HIGH_RISK])
    def test_the_wire_names_both_annex_i_limbs_and_the_residual_duties(self, ask, question):
        answer = _low(ask(question)["answer"])
        assert "safety component of, or itself, a product" in answer
        assert "third-party conformity assessment" in answer
        # The residual duties the generic path dropped on both paraphrases.
        assert "article 4" in answer
        assert "article 95" in answer

    def test_a_scenario_still_uses_the_classifier_not_the_residual_tier(self):
        from app.engines import _graph_rag_impl as E

        assert not E._detect_minimal_risk_inquiry(
            "We are a hospital deploying a triage system; is it considered minimal risk?"
        )


# ── Q10b — dual capacity, and the three Article 3 acts ───────────────────────


class TestRoleFamilyParaphrases:
    def test_the_dual_capacity_detector_fires(self):
        from app.engines import _graph_rag_impl as E

        assert E._detect_role_difference_inquiry(DUAL_ROLE)

    def test_a_scenario_opener_stays_off_the_role_difference_path(self):
        from app.engines import _graph_rag_impl as E

        assert not E._detect_role_difference_inquiry(
            "We are a provider and a deployer of a chatbot. What obligations do we have?"
        )

    def test_the_wire_answers_the_dual_capacity_question_with_the_roles(self, ask):
        body = ask(DUAL_ROLE)
        answer = _low(body["answer"])
        assert "article 3(3)" in answer and "article 3(4)" in answer
        assert "article 3(11)" in answer
        assert "recital 83" in answer
        assert "article 25(1)" in answer
        # The pre-fix dump carried twelve references and no Article 3/25.
        assert len(body["references"]) <= 4
        assert not any(r.startswith("Article 50") for r in body["references"])

    def test_the_wire_separates_placing_on_the_market_from_putting_into_service(self, ask):
        body = ask(THREE_ACTS)
        answer = _low(body["answer"])
        assert "first making available" in answer
        assert "supply of an ai system for first use directly to the deployer" in answer
        assert "for own use" in answer
        assert body["references"] == ["Article 3.9", "Article 3.10", "Article 3.11"]


# ── Q16c — the emotion-only workplace asks (R465c) ───────────────────────────


class TestEmotionOnlyWorkplaceAsks:
    @pytest.mark.parametrize("question", [EMOTION_EMPLOYEES, ARTICLE_5_WORKERS])
    def test_the_detector_no_longer_needs_the_stress_word(self, question):
        from app.engines.statutory_precision import (
            curated_statutory_verdict,
            _detect_workplace_emotion_and_stress,
        )

        assert _detect_workplace_emotion_and_stress(question)
        verdict = curated_statutory_verdict(question)
        assert verdict is not None and verdict["name"] == "workplace_emotion_and_stress"

    def test_the_employer_phrasing_keeps_the_stress_branch(self, ask):
        body = ask(EMOTION_EMPLOYEES)
        answer = _low(body["answer"])
        assert "article 5(1)(f)" in answer
        # Polarity: "is it allowed ...?" must lead with NO.
        assert answer.startswith("no as to the emotions")
        assert "medical or safety reasons" in answer
        assert "raising productivity" in answer
        assert "stress is separate" in answer and "point 4(b)" in answer
        # Framing guard: the asker never mentioned a line, so the answer must
        # not put one in their mouth (that is the scenario framing, below).
        assert "manufacturing line" not in answer
        assert body["references"][0] == "Article 5.1.f"

    def test_the_article_5_phrasing_is_answered_as_a_prohibition(self, ask):
        body = ask(ARTICLE_5_WORKERS)
        answer = _low(body["answer"])
        # Polarity: "does Article 5(1)(f) prohibit ...?" must lead with YES.
        assert answer.startswith("yes as to the emotions")
        assert "prohibited under article 5(1)(f)" in answer
        assert "prohibited outright" in answer
        assert "the only article 5(1)(f) exception" in answer
        # The stress half is the part the reference position graded and both
        # pre-fix arms dropped.
        assert "stress is separate" in answer and "point 4(b)" in answer
        assert "article 26" in answer
        assert body["references"][0] == "Article 5.1.f"

    def test_a_concrete_scenario_still_gets_the_scenario_framing(self):
        from app.engines.statutory_precision import _workplace_emotion_and_stress

        scenario = _workplace_emotion_and_stress(STRESS_ONLY)["answer"].lower()
        assert "its own manufacturing line workers" in scenario
        generic = _workplace_emotion_and_stress(EMOTION_EMPLOYEES)["answer"].lower()
        assert "manufacturing line" not in generic


# ── Q16b — the stress-only workplace-monitoring ask ──────────────────────────


class TestStressOnlyWorkplaceMonitoring:
    def test_the_scope_gate_accepts_the_question(self):
        # Pre-fix this returned CONVERSATIONAL: no AI system, no article, no
        # anchor keyword — and the live out-of-scope branch then invented a
        # "biometric categorisation" high-risk answer.
        from app.integrations.regenold.scope import classify_conversation

        verdict = classify_conversation([{"role": "user", "content": STRESS_ONLY}])
        assert verdict.verdict.in_scope, verdict.verdict

    def test_the_wire_states_the_prohibition_and_the_stress_branch(self, ask):
        body = ask(STRESS_ONLY)
        answer = _low(body["answer"])
        assert "article 5(1)(f)" in answer
        assert "prohibits" in answer and "use of ai systems to infer emotions" in answer
        assert "stress is separate" in answer
        assert "point 4(b)" in answer
        assert "2 february 2025" in answer and "2 august 2026" in answer
        assert body["references"][0] == "Article 5.1.f"

    def test_a_generic_hr_question_is_still_out_of_scope(self):
        from app.integrations.regenold.scope import classify_conversation

        verdict = classify_conversation(
            [{"role": "user", "content": "How do I run a performance review with a stressed employee?"}]
        )
        assert not verdict.verdict.in_scope


# ── R465d — the scope bridge is bounded by a technology token ───────────────


class TestScopeBridgeIsBounded:
    """The bridge admits a question only when it can name WHAT is doing the work.

    The engine detector behind ``is_workplace_monitoring_ask`` is
    ``(stress|emotion) AND worker noun AND legality verb`` — none of which says
    an AI system is involved. Routed through the scope gate unchanged, that
    admitted pure HR questions (stress surveys, stress leave, emotional
    support) and answered them with curated Article 5(1)(f) prose asserting a
    system the user never mentioned — worse than the refusal it replaced, since
    a refusal is not confidently wrong.
    """

    @pytest.mark.parametrize("question", [STRESS_ONLY, EMOTION_EMPLOYEES, ARTICLE_5_WORKERS])
    def test_the_r465_shapes_still_cross_the_bridge(self, question):
        from app.engines.statutory_precision import is_workplace_monitoring_ask

        assert is_workplace_monitoring_ask(question), question

    @pytest.mark.parametrize(
        "question",
        [
            "Is it legal for managers to give emotional support to staff?",
            "Is it legal to survey employees about their stress levels each quarter?",
            "Our HR team asks whether stress leave is legal for employees.",
        ],
    )
    def test_non_ai_hr_questions_do_not_cross_it(self, question):
        from app.engines.statutory_precision import is_workplace_monitoring_ask
        from app.integrations.regenold.scope import classify_conversation

        assert not is_workplace_monitoring_ask(question), question
        verdict = classify_conversation([{"role": "user", "content": question}])
        assert not verdict.verdict.in_scope, verdict.verdict

    def test_the_hr_question_does_not_reach_the_curated_verdict(self, ask):
        # The narrowing's purpose: an HR survey question must not be answered
        # with the workplace-emotion verdict's Article 5(1)(f) prose.
        body = ask("Is it legal to survey employees about their stress levels each quarter?")
        assert not any(r.startswith("Article 5.1.f") for r in body["references"]), body["references"]
        assert "commits the third of those acts" not in body["answer"], body["answer"]


# ── R465d — the deep-review regressions ──────────────────────────────────────
#
# Every case below is a false positive or a polarity inversion found by the
# read-only review fan-out and REPRODUCED against the pre-fix tree before it was
# fixed. They are pinned here because each one shipped a sentence the statute
# does not support, which is the defect class this round exists to close.


def _answer(question: str) -> str:
    from app.engines.statutory_precision import _workplace_emotion_and_stress

    return _low(_workplace_emotion_and_stress(question)["answer"])


class TestDeepReviewRegressions:
    def test_a_bare_possessive_does_not_invent_a_manufacturing_line(self):
        # "our" alone used to take the own-setup branch and assert a line the
        # question never named.
        assert "manufacturing line" not in _answer(
            "Our HR team monitors employees' emotions. Is that allowed?"
        )

    def test_a_metalinguistic_ask_does_not_invent_a_manufacturing_line(self):
        assert "manufacturing line" not in _answer(
            "Is my understanding correct that emotion recognition of workers is prohibited?"
        )

    def test_a_negated_prohibition_is_not_led_with_yes(self):
        # The Yes/No word is the verdict: answering "Yes" to "is it true that
        # this is NOT prohibited?" agrees with the negation.
        answer = _answer(
            "Is it true that emotion recognition of workers is not prohibited in all cases?"
        )
        assert not answer.startswith("yes"), answer[:120]
        assert "prohibited under article 5(1)(f)" in answer

    def test_stress_testing_is_not_the_workplace_verdict(self):
        from app.engines.statutory_precision import _detect_workplace_emotion_and_stress

        assert not _detect_workplace_emotion_and_stress(
            "Is stress testing of our model by staff legal?"
        )

    def test_the_education_limb_is_stated(self):
        answer = _answer("Are emotion recognition systems allowed for students and staff?")
        assert "education and vocational training institutions" in answer

    def test_a_provider_ask_names_the_first_two_acts(self):
        answer = _answer(
            "We are a provider of emotion-recognition software sold to employers - is it allowed?"
        )
        assert "places such a system on the market" in answer
        assert "first two" in answer

    def test_the_residual_class_does_not_answer_a_transparency_ask(self):
        from app.engines._graph_rag_impl import _detect_minimal_risk_inquiry

        assert not _detect_minimal_risk_inquiry(
            "Our chatbot is not high-risk, so which transparency obligations apply?"
        )
        # The measured R465b shape still needs the residual-tier answer.
        assert _detect_minimal_risk_inquiry(
            "Which systems are neither prohibited nor high-risk?"
        )
        assert _detect_minimal_risk_inquiry(
            "If my system is not high-risk, do any duties still apply?"
        )

    def test_the_article_50_describer_keeps_all_five_paragraphs(self):
        from app.integrations.regenold.grounded_prose import _ART_SUBPOINT_DESCRIBERS

        text = _low(_ART_SUBPOINT_DESCRIBERS["Article 50"])
        for token in ("50(1)", "50(2)", "50(3)", "50(4)", "50(5)"):
            assert token in text, token

    def test_the_three_framings_are_actually_different(self):
        # R465d (deep review) — the branch assertions elsewhere check text that
        # EVERY branch emits (the prohibition sentence, the exception, the
        # dates), so they would pass with the framing hard-coded. This diffs the
        # tails instead: the own-setup, employer and provider framings must be
        # distinguishable sentences, not three copies of one.
        own = _answer("Our factory monitors worker emotions - is that allowed?")
        employer = _answer("Is emotion recognition of employees allowed?")
        provider = _answer(
            "We are a provider of emotion-recognition software sold to employers - is it allowed?"
        )
        assert "manufacturing line" in own
        assert "manufacturing line" not in employer
        assert "first two" in provider
        assert "first two" not in employer
        assert own.split("as well,")[-1] != employer.split("as well,")[-1]

    def test_history_does_not_activate_the_verdict(self):
        # R465d (deep review) — ``_live_turn`` is the whole gate discipline and
        # had no pin: a detector that read the flattened conversation would
        # answer a follow-up from the PREVIOUS turn's subject.
        from app.engines.statutory_precision import _detect_workplace_emotion_and_stress

        carried = (
            "User: our factory monitors worker emotions\n"
            "Assistant: Article 5(1)(f) prohibits that.\n"
            "Latest question: what are the penalties?"
        )
        assert not _detect_workplace_emotion_and_stress(carried)
        live = (
            "User: hello\n"
            "Latest question: our factory monitors worker emotions - is that allowed?"
        )
        assert _detect_workplace_emotion_and_stress(live)
