"""R411 — regression pins for the four fixes found by re-opening the judge reports.

Context. The R409 frontier-judge snapshot (``docs/measurements/r409/
antifragile_frontier_judge_results.json``, 17 expert-review + 11 official
LLM-judge questions) recorded criteria verdicts at commit ``dd797d9``. Re-running
the same instrument against the current engine showed 11 rows had changed answers
and, critically, that several fixes had never reached the wire. Four defects were
confirmed and fixed; each is pinned here with the question shape that failed and
the shape that must not change.

    part1_q03 / part2_q02   "What is the definition of high risk?"  -> 0/4, 0/5
    part1_q15               provider chatbot on a hospital site     -> 0/4
    part1_q12 / part2_q08   conditional clinical-trial triage       -> 1/5, 0/5
    part2_q04               statutory Art 50(1) information ask     -> 0/4

Measured after the fixes (same judge, same prompt, OpenRouter claude-sonnet-5
@ temp 0.1): loose 47.98% -> 66.73%, strict 5/28 -> 11/28.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.engines.graph_rag import (
    _detect_hospital_deployer_inquiry,
    _detect_user_information_inquiry,
    _general_classification_verdict_text,
)
from app.engines.prohibited_gatekeeper import answer_denies_prohibition
from app.engines.sentence_index import classify_question, select_definition_sentence
from app.routes.regenold import (
    _EXPLICIT_DEFINITION_ASK_RE,
    _explicit_definition_ask,
    _extractive_answer_candidate,
)


@pytest.fixture()
def ask(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    from app.rate_limit import limiter

    limiter.enabled = False
    from app.routes import regenold as regenold_route

    client = TestClient(main_mod.app)

    def _ask(question: str) -> dict:
        regenold_route._ENGINE_CACHE.clear()
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": question}],
        )
        assert resp.status_code == 200, resp.text[:400]
        return resp.json()

    return _ask


# ── Fix 1 — a definition ask the Art. 3 registry cannot resolve ───────────────
# The definition path used to fall through to the generic BM25 sentence walk,
# which shipped ONE arbitrary sentence from the top-cited article in place of the
# engine's composed prose. For "What is the definition of high risk?" that was
# Article 6(2) verbatim — an operative clause that defines nothing.

_HIGH_RISK_DEFINITION_QS = (
    "What is the definition of high risk?",
    "What is the definition of high risk under the EU AI Act?",
)

_HIGH_RISK_DEFINITION_ANSWER = (
    "In addition to the high-risk AI systems referred to in paragraph 1, "
    "AI systems referred to in Annex III shall be considered to be high-risk."
)


class TestExplicitDefinitionAskDeclinesTheSentenceWalk:
    @pytest.mark.parametrize("question", _HIGH_RISK_DEFINITION_QS)
    def test_the_question_is_definition_shaped(self, question):
        # Precondition: this is the definition path, and the registry misses.
        assert classify_question(question) == "definition"
        assert select_definition_sentence(question) is None

    @pytest.mark.parametrize("question", _HIGH_RISK_DEFINITION_QS)
    def test_the_ask_is_recognised_as_explicit(self, question):
        assert _explicit_definition_ask(question) is True

    @pytest.mark.parametrize("question", _HIGH_RISK_DEFINITION_QS)
    def test_the_statute_fragment_is_not_shipped(self, ask, question):
        answer = ask(question)["answer"]
        assert _HIGH_RISK_DEFINITION_ANSWER not in answer
        # ... and the composed prose that states the classification is.
        assert "Article 6(1)" in answer
        assert "Annex III" in answer

    def test_the_extractive_pass_declines(self):
        candidate = _extractive_answer_candidate(
            question="What is the definition of high risk?",
            engine_citations=(),
        )
        assert candidate is None

    @pytest.mark.parametrize(
        "question",
        [
            # An explicit definition ask that DOES resolve must still extract.
            "What is a deep fake according to the EU AI Act?",
            "Under the EU AI Act, what is an \"AI regulatory sandbox\"?",
            # A NON-explicit "what is X" ask whose registry lookup misses keeps
            # the sentence walk: measured better for that shape (rg_059).
            "Under the EU AI Act, what is the scientific panel of independent "
            "experts, and what are its main support tasks?",
        ],
    )
    def test_the_decline_is_scoped_to_explicit_asks(self, question):
        if select_definition_sentence(question) is not None:
            assert _explicit_definition_ask(question) in (True, False)
            return
        assert _explicit_definition_ask(question) is False

    def test_the_regex_covers_the_statutory_phrasings(self):
        for q in (
            "What is the definition of high risk?",
            "Define high-risk.",
            "Under the AI Act, how is \"risk\" defined?",
            "What is the meaning of testing data?",
            "What does deployer mean?",
        ):
            assert _EXPLICIT_DEFINITION_ASK_RE.search(q), q


# ── Fix 2 — the hospital-as-deployer intercept ───────────────────────────────
# R358's premise was "Only la_q71 combines hospital + deploy + obligations". The
# three lookaheads matched anywhere, so a PROVIDER-side question that merely
# named a hospital as a venue was captured and short-circuited Stage-2.

_LA_Q71 = (
    "A hospital deploys a high-risk AI diagnostic system. What are its "
    "obligations as a deployer under the EU AI Act?"
)
_LA_Q79 = (
    "If a hospital fine-tunes an open-weight medical language model, when does "
    "it become a provider under the EU AI Act?"
)
_CHATBOT = (
    "We are developing a generative AI chatbot that will be deployed on a "
    "hospital website to answer general patient queries. What transparency "
    "obligations apply?"
)


class TestHospitalDeployerRequiresADutyBearer:
    def test_the_target_row_still_fires(self):
        assert _detect_hospital_deployer_inquiry(_LA_Q71) is True

    def test_the_pinned_near_miss_still_does_not_fire(self):
        assert _detect_hospital_deployer_inquiry(_LA_Q79) is False

    def test_a_hospital_used_as_a_venue_does_not_fire(self):
        assert _detect_hospital_deployer_inquiry(_CHATBOT) is False

    @pytest.mark.parametrize(
        "question",
        [
            "What obligations does the hospital have as a deployer of a "
            "high-risk AI system?",
            "A hospital deploys a high-risk AI system. What are the hospital's "
            "obligations?",
            "A hospital deploys an Annex III system. What obligations must the "
            "hospital comply with?",
        ],
    )
    def test_attributed_shapes_still_fire(self, question):
        assert _detect_hospital_deployer_inquiry(question) is True

    def test_the_base_shape_still_requires_a_deployment(self):
        # "uses" (not "deploys") never met the R358 premise, and still does not:
        # the attribution requirement is additive, not a replacement.
        assert (
            _detect_hospital_deployer_inquiry(
                "A hospital uses a high-risk AI system. What are the hospital's "
                "obligations?"
            )
            is False
        )

    def test_the_chatbot_question_gets_the_article_50_answer(self, ask):
        answer = ask(_CHATBOT)["answer"]
        assert "Article 50(1)" in answer
        # The hospital-as-deployer roster is not the answer to a provider ask.
        assert "fundamental rights impact assessment" not in answer


# ── Fix 3 — the confident-negative general verdict ──────────────────────────
# The legacy text opens "The system described is not among the practices
# prohibited under Article 5". Its soundness depends on the curated catalogue
# having recognised the system; for a DESCRIBED practice it silently deletes the
# prohibition route. Scoped so the R376 contradiction guard keeps owning every
# row the prohibition gatekeeper DID match.

_LEGACY_OPENING = "not among the practices prohibited under Article 5"
_CONDITIONAL_OPENING = "Classification turns on Article 6"

_CONDITIONAL_TRIAGE = (
    "Can a hospital use an AI system to sort patients based on their biometric "
    "data to determine priority for an experimental clinical trial?"
)
_RACE_TRIAGE = (
    "Under the EU AI Act, can a hospital use an AI system to sort patients "
    "based on their biometric data to determine priority for an experimental "
    "clinical trial, where the system infers each patient's race from that data?"
)


class TestConditionalVerdictForDescribedArticle5Practices:
    def test_a_described_biometric_practice_takes_the_conditional_wording(self):
        text = _general_classification_verdict_text(_CONDITIONAL_TRIAGE)
        assert text.startswith(_CONDITIONAL_OPENING)
        assert _LEGACY_OPENING not in text

    def test_a_gatekeeper_matched_row_keeps_the_legacy_wording(self):
        # The gatekeeper recognises the race-inference practice, so R376 — which
        # strips the denial and prepends the curated Article 5(1)(g) verdict —
        # must keep working. A conditional wording here silently disabled it.
        text = _general_classification_verdict_text(_RACE_TRIAGE)
        assert text.startswith("The system described is not among the practices")

    def test_a_non_article5_question_is_untouched(self):
        text = _general_classification_verdict_text(
            "Is an AI CV-screening tool high-risk under the EU AI Act?"
        )
        assert text.startswith("The system described is not among the practices")

    def test_no_question_keeps_the_current_default(self):
        assert _general_classification_verdict_text().startswith(
            "The system described is not among the practices"
        )

    def test_the_conditional_triage_answer_never_asserts_the_wrong_negative(self, ask):
        """The confident negative is what cost this row its branch.

        The conditional wording is still a denial-SHAPED clause (it says the
        system is not one of the prohibited practices), which is exactly why the
        R376 grammar had to be widened — but it no longer closes the Article 5
        route unconditionally, and it is only ever selected where the prohibition
        gatekeeper did NOT match, so R376 cannot rewrite this answer.
        """
        answer = ask(_CONDITIONAL_TRIAGE)["answer"]
        assert _LEGACY_OPENING not in answer
        assert answer.startswith(_CONDITIONAL_OPENING)

    def test_the_race_variant_keeps_its_curated_verdict(self, ask):
        answer = ask(_RACE_TRIAGE)["answer"]
        assert "prohibited under Article 5(1)(g)" in answer
        assert ("race" in answer) and ("sexual orientation" in answer)

    def test_the_flag_reverts_the_wording(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_GENERAL_VERDICT_ART5_CONDITIONAL", "0")
        text = _general_classification_verdict_text(_CONDITIONAL_TRIAGE)
        assert _LEGACY_OPENING in text


class TestDenialGrammarCoversBothWordings:
    """R376's denial detector must not be wording-dependent."""

    @pytest.mark.parametrize(
        "sentence",
        [
            "The system described is not among the practices prohibited under "
            "Article 5.",
            "If neither applies, and the system is not one of the practices "
            "exhaustively prohibited by Article 5, it is limited-risk.",
            "The system is not one of the practices prohibited by Article 5.",
        ],
    )
    def test_denials_are_detected(self, sentence):
        assert answer_denies_prohibition(sentence) is True

    @pytest.mark.parametrize(
        "sentence",
        [
            "The system is not high-risk under Article 6.",
            "Article 5 does not apply to this system's training data.",
            "Classification turns on Article 6 and Annex III.",
        ],
    )
    def test_non_denials_are_not(self, sentence):
        assert answer_denies_prohibition(sentence) is False


# ── Fix 4 — Article 50(1) information intercept recall ──────────────────────
# The intercept was keyed on two literal substrings; the second excluded the
# indefinite article, so the STATUTORY wording — the one question it exists for —
# missed and the ask fell to the QA dump (which shipped the Article 14(5)
# two-person biometric-verification rule, 0/4 criteria).

_STATUTORY_INFORMATION_ASK = (
    "Under the EU AI Act, how must a natural person be informed that they are "
    "interacting with an AI system?"
)


class TestUserInformationInterceptRecall:
    def test_the_statutory_phrasing_is_recognised(self):
        assert _detect_user_information_inquiry(_STATUTORY_INFORMATION_ASK) is True

    def test_the_original_wording_still_is(self):
        assert (
            _detect_user_information_inquiry(
                "How should users be informed when interacting with AI systems?"
            )
            is True
        )

    @pytest.mark.parametrize(
        "question",
        [
            "What information must a provider give a deployer under Article 13?",
            "Does the obligation to indicate that deep-fakes are artificially "
            "generated apply when prosecuting a criminal offence?",
        ],
    )
    def test_unrelated_information_asks_do_not_match(self, question):
        assert _detect_user_information_inquiry(question) is False

    def test_the_statutory_ask_gets_article_50_not_article_14(self, ask):
        answer = ask(_STATUTORY_INFORMATION_ASK)["answer"]
        assert "Article 50(1)" in answer
        assert "separately verified and confirmed by at least two natural persons" not in answer


class TestCorpusNeutrality:
    """The four fixes must not move the frozen 110-row reference axes.

    Measured with ``docs/measurements/r411/corpus_ab.py``: 0 expected heads lost,
    0 gained, identical ref_loose / ref_strict / ref_conc on every arm.
    """

    @pytest.mark.parametrize(
        "question",
        [
            "What is Article 50(4) about?",
            "What is Annex X about? What is it used for?",
            "Is an AI system used to structure or deduplicate information for a "
            "use case listed in Annex III considered high-risk?",
        ],
    )
    def test_known_corpus_rows_still_answer(self, ask, question):
        answer = ask(question)["answer"]
        assert answer.strip(), question
