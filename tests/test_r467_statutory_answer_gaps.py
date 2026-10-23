"""R467 — the limitations the October 2026 review appendix disclosed.

R465 fixed the ten questions the 2026-09-29 review read. The R467 live check of
30 rephrasings (``docs/measurements/r467/paraphrase_rerun.json``) found that the
fixes did not hold under other wording:

* a curated answer is cut to three sentences when the route reads the question
  as a single ask (``MAX_ANSWER_SENTENCES``), so the Q17 rephrasings lost the
  Article 97(4)/(6) sentence and the short Q74 phrasing lost Article 50(5) and the
  application date;
* "When does a deployer become a provider under Article 25(1)?" got an answer
  without the Article 25(1)(a) and (c) conditions the review asked for;
* the grain deepener re-deepened a curated answer's references after the curated
  guards ran (``Annex III.7.b`` on a Q17 rephrasing, ``Article 26.5`` / ``26.7`` on
  the workplace answers);
* wording the appendix had to disclose: "is instead its provider" (Q74), "must"
  for Recital 83's "should" (Q10), and three abridged Article 13(3)(b) items (Q45);
* an art-project image question missed the Q74 verdict and was answered by
  Stage-2 with the deployer assumption the review criticised.

Every pin below is at the WIRE through the offline route, which is the regime
these answers are served in live (curated answers skip Stage-2).
"""
from __future__ import annotations

import os
import re

import pytest

_PRIOR_SKIP_DOTENV = os.environ.get("REGENOLD_SKIP_DOTENV")
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

DETERMINISTIC_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "0",
}

Q17_ORIGINAL = (
    "Can the European Commission amend Annex III of the EU AI Act to add or modify "
    "use-cases classified as high-risk AI systems? Under what conditions?"
)
Q17_ENTRY_INTO_FORCE = (
    "How can the Commission add a new high-risk use case to Annex III, and what "
    "must happen before the delegated act enters into force?"
)
Q45_ARTICLE_13_3 = (
    "What information must the instructions for use of a high-risk AI system "
    "contain under Article 13(3)?"
)
Q96_LIST = "List the high-risk areas in Annex III. Is healthcare decision-making one of them?"
Q96_WHERE = "Which areas does Annex III list, and where does healthcare actually appear?"
Q104_ARTICLE_111 = "What does Article 111(1) do with Annex X?"
Q74_ORIGINAL = (
    "I generated audio with AI for my artistic work (sole purpose). Do I need to "
    "provide some marking of its artificial nature? I feel that would compromise "
    "the enjoyment of the work."
)
Q74_SHORT = "Must I label AI-generated audio in my artistic work?"
Q74_IMAGES = "Must AI-generated images in an art project be marked as AI-generated, and by whom?"
Q16_ORIGINAL = (
    "A pharmaceutical company wants to use an AI system to monitor the emotions and "
    "stress levels of their manufacturing line workers to improve efficiency. Is "
    "this allowed?"
)
Q16_EMPLOYEES = (
    "Is emotion recognition of employees allowed if the employer only wants to "
    "raise productivity?"
)
Q10_ORIGINAL = "What is the difference between the deployer and the provider?"
ARTICLE_25_1 = "When does a deployer become a provider under Article 25(1)?"

#: Single-ask rephrasings whose statutory answer the three-sentence cap cut.
SINGLE_ASK_STATUTORY = [Q17_ENTRY_INTO_FORCE, Q45_ARTICLE_13_3, Q96_WHERE, Q104_ARTICLE_111, Q74_SHORT]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


@pytest.fixture(scope="module")
def ask():
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


# ── 1. A curated answer ships whole ─────────────────────────────────────────


@pytest.mark.parametrize("question", SINGLE_ASK_STATUTORY)
def test_a_statutory_answer_ships_whole_on_a_single_ask(ask, question):
    """The verdict is drafted complete; the sentence cap must not cut its tail."""
    from app.engines.statutory_precision import curated_statutory_verdict

    verdict = curated_statutory_verdict(question)
    assert verdict is not None, "the rephrasing must still reach its statutory verdict"
    assert _norm(ask(question)["answer"]) == _norm(verdict["answer"])


def test_the_q17_rephrasing_states_the_objection_procedure(ask):
    """The rephrasing ASKS what must happen before entry into force."""
    answer = ask(Q17_ENTRY_INTO_FORCE)["answer"]
    assert "experts designated by each Member State (Article 97(4))" in answer
    assert "(Article 97(6))" in answer


def test_the_short_q74_phrasing_keeps_article_50_5_and_the_date(ask):
    answer = ask(Q74_SHORT)["answer"]
    assert "clear and distinguishable" in answer
    assert "2 August 2026" in answer


def test_the_article_25_1_answer_ships_whole(ask):
    """A curated answer outside the R465 module is covered by the same rule."""
    from app.engines._graph_rag_impl import _is_curated_authoritative_intercept

    assert _is_curated_authoritative_intercept(ARTICLE_25_1)
    answer = ask(ARTICLE_25_1)["answer"]
    assert "Article 25(2)" in answer, "the final sentence was cut"


def test_the_full_text_rule_is_two_sided(ask, monkeypatch):
    """``REGENOLD_CURATED_FULL_TEXT=0`` restores the cut, so the flag is real."""
    from app.engines.statutory_precision import curated_statutory_verdict

    monkeypatch.setenv("REGENOLD_CURATED_FULL_TEXT", "0")
    answer = ask(Q17_ENTRY_INTO_FORCE)["answer"]
    assert _norm(answer) != _norm(curated_statutory_verdict(Q17_ENTRY_INTO_FORCE)["answer"])
    assert "(Article 97(6))" not in answer


# ── 2. The Article 25(1) answer states each condition ──────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "already placed on the market or put into service",
        "without prejudice to contractual arrangements stipulating that the obligations are "
        "otherwise allocated",
        "in such a way that it remains a high-risk AI system pursuant to Article 6",
        "which has not been classified as high-risk and has already been placed on the market or "
        "put into service",
    ],
)
def test_the_article_25_1_answer_states_the_condition(ask, phrase):
    assert phrase in _norm(ask(ARTICLE_25_1)["answer"])


# ── 3. A statutory answer cites exactly what it declares ───────────────────


@pytest.mark.parametrize(
    "question",
    [Q17_ORIGINAL, Q17_ENTRY_INTO_FORCE, Q96_LIST, Q96_WHERE, Q16_ORIGINAL, Q16_EMPLOYEES, Q74_ORIGINAL],
)
def test_statutory_citations_are_the_declared_set(ask, question):
    from app.engines.statutory_precision import curated_statutory_verdict
    from app.integrations.regenold.models import reference_from_article_ref

    declared = [reference_from_article_ref(r) for r in curated_statutory_verdict(question)["refs"]]
    assert all(declared)
    assert ask(question)["references"] == declared


def test_no_unrelated_annex_iii_point_on_the_q17_rephrasing(ask):
    """``enters into force`` matched point 7(b)'s ``enter`` and the deepener took it."""
    assert "Annex III.7.b" not in ask(Q17_ENTRY_INTO_FORCE)["references"]


@pytest.mark.parametrize("question", [Q16_ORIGINAL, Q16_EMPLOYEES])
def test_the_workplace_answer_cites_article_26_as_a_whole(ask, question):
    """The answer refers to "the Article 26 deployer obligations", not one paragraph."""
    refs = ask(question)["references"]
    assert "Article 26" in refs
    assert not [r for r in refs if r.startswith("Article 26.")]


def test_the_pin_is_two_sided(ask, monkeypatch):
    monkeypatch.setenv("REGENOLD_STATUTORY_REFS_PINNED", "0")
    assert "Annex III.7.b" in ask(Q17_ENTRY_INTO_FORCE)["references"]


#: Official row rg_025. Once its answer states the Article 6 conditions the
#: review asked for, the ``Art. 6`` anchor survives the curated prose scope and
#: the deepener turned it into ``Article 6.2`` — a third reference against an
#: expected set of one.
RG_025 = (
    "Can an operator that is not a provider according to the EU AI Act, for example a "
    "deployer, take actions on a given high-risk AI system such that it can be "
    "effectively seen as a provider by the authorities? If yes, what kind of action "
    "would result in such an outcome?"
)


def test_the_article_25_1_verdict_keeps_its_declared_citations(ask):
    assert ask(RG_025)["references"] == ["Article 25.1", "Article 16"]


def test_a_yes_no_article_25_1_question_still_leads_with_yes(ask):
    """rg_025's first criterion is "Yes"; the lead sits inside the cited sentence."""
    answer = ask(RG_025)["answer"]
    assert answer.startswith("Yes: under Article 25(1)")
    assert not ask(ARTICLE_25_1)["answer"].startswith("Yes")


def test_the_verdict_name_registry_matches_the_builders():
    """The route recognises a statutory verdict by name; a renamed or new builder
    that is missing here would silently lose the pin."""
    from app.engines import statutory_precision as sp

    built = {
        sp._instructions_for_use()["name"],
        sp._annex_iii_areas()["name"],
        sp._annex_iii_area_vs_use_case()["name"],
        sp._annex_iii_amendment()["name"],
        sp._deepfake_artistic_disclosure(Q74_ORIGINAL)["name"],
        sp._market_service_use()["name"],
        sp._annex_x_overview()["name"],
        sp._workplace_emotion_and_stress(Q16_ORIGINAL)["name"],
    }
    assert built == sp.STATUTORY_VERDICT_NAMES


# ── 4. Wording the appendix had to disclose ────────────────────────────────


def test_q74_does_not_present_provider_and_deployer_as_alternatives(ask):
    answer = ask(Q74_ORIGINAL)["answer"]
    assert "instead its provider" not in answer
    assert "is also its provider" in answer


@pytest.mark.parametrize(
    "phrase",
    [
        "should fulfil cumulatively all relevant obligations associated with those roles",
        "develops an AI system or a general-purpose AI model",
    ],
)
def test_q10_states_the_act_as_worded(ask, phrase):
    # Article 16 is deliberately not named in this definitional answer (R447:
    # naming duty articles failed the citation criterion and the tone check).
    assert phrase in _norm(ask(Q10_ORIGINAL)["answer"])


def test_q10_no_longer_turns_recital_83_into_a_rule(ask):
    assert "must fulfil cumulatively" not in ask(Q10_ORIGINAL)["answer"]


@pytest.mark.parametrize(
    "phrase",
    [
        "against which the system has been tested and validated",
        "in accordance with its intended purpose or under conditions of reasonably foreseeable misuse",
        "taking into account the intended purpose",
    ],
)
def test_q45_states_the_article_13_3_b_items_in_full(ask, phrase):
    assert phrase in _norm(ask(Q45_ARTICLE_13_3)["answer"])


# ── 5. The Q74 verdict covers images and video, not only audio ─────────────


def test_an_art_project_image_question_reaches_the_q74_verdict(ask):
    from app.engines.statutory_precision import is_statutory_precision_ask

    assert is_statutory_precision_ask(Q74_IMAGES)
    answer = ask(Q74_IMAGES)["answer"]
    assert answer.startswith("Making AI-generated images")
    assert "Article 50(5)" in answer
    assert "audio" not in answer
    assert "as deployer, has no marking duty" not in answer


def test_the_reviewed_audio_question_keeps_its_medium(ask):
    assert ask(Q74_ORIGINAL)["answer"].startswith("Making AI-generated audio")


@pytest.mark.parametrize(
    "question",
    [
        "Must AI-generated content be marked with state-of-the-art watermarking techniques?",
        "Must AI-generated text published to inform the public be labelled?",
    ],
)
def test_the_widened_q74_detector_does_not_take_other_article_50_questions(question):
    from app.engines.statutory_precision import is_statutory_precision_ask

    assert not is_statutory_precision_ask(question)


# ── 6. Both flags reach the cache key ─────────────────────────────────────


@pytest.mark.parametrize("flag", ["REGENOLD_CURATED_FULL_TEXT", "REGENOLD_STATUTORY_REFS_PINNED"])
def test_flag_is_in_the_engine_cache_key(flag, monkeypatch):
    from app.routes import regenold

    monkeypatch.delenv(flag, raising=False)
    on = regenold._engine_cache_key(Q17_ENTRY_INTO_FORCE, None)
    monkeypatch.setenv(flag, "0")
    assert regenold._engine_cache_key(Q17_ENTRY_INTO_FORCE, None) != on
