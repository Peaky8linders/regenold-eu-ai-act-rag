"""R469 — rephrasings that missed a statutory verdict and got the review's defects back.

The R467 held-out run (``docs/measurements/r467/heldout_prefix.json``) asked two
rephrasings per review family. Seven missed the detector that serves the vetted
answer, so Stage-2 answered them and repeated what the October 2026 review
criticised:

* H74_a (musician, backing vocals, album): assumed the asker is a deployer and
  the album "evidently artistic", and named liner notes as the disclosure. The
  artistic cue knew "artist" but not "musician" or "album".
* H16_a (webcams, call-centre staff "frustrated or stressed"): called stress an
  emotion. The stress cue missed "stressed", the emotion cue knew only
  "emotion", and "Can an employer use ..." was not read as a legality ask.
* HD_a ("Would an AI module that controls a surgical robot's movements be a
  high-risk AI system?"): asserted a device class and cited ``Annex I.20``. The
  verdict-ask gate has no "would ... be" shape.
* H45_a ("what do I have to put in the instructions for use"): dropped the
  Article 13(3) qualifiers and abridged Article 13(2). Only list / categories /
  "what information" counted as a content ask.
* H96_a ("Which sectors does Annex III cover ... a clinical decision-support AI
  in a hospital"): abridged the area headings. The detector knew "areas" and
  "health" only.
* H10_a ("How does the AI Act distinguish a provider from a deployer?"): shipped
  the stored 68-term Article 3 summary. "distinguish" was not a contrast marker.
* H17_a ("Could the Commission add a brand-new area to Annex III through a
  delegated act?"): reached the Article 7 verdict, which opens "Yes". Under
  Article 7(1)(a) a delegated act adds use cases only within the areas already
  listed, so the answer to a new-area ask is No (Article 112(2)(a)).

The held-out set that measures the fix (``docs/measurements/r469``) was written
blind and is not used here.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

_PRIOR_SKIP_DOTENV = os.environ.get("REGENOLD_SKIP_DOTENV")
os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

from app.engines import _graph_rag_impl as impl  # noqa: E402
from app.engines.statutory_precision import (  # noqa: E402
    ANNEX_III_AREAS,
    curated_statutory_verdict,
)

DETERMINISTIC_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "0",
}
FLAG = "REGENOLD_STATUTORY_REPHRASINGS"

H45_A = ("As a provider of a high-risk AI system, what do I have to put in the instructions "
         "for use I give to deployers?")
H96_A = ("Which sectors does Annex III cover, and is a clinical decision-support AI in a "
         "hospital one of them?")
H17_A = "Could the Commission add a brand-new area to Annex III through a delegated act?"
H17_B = "What procedure applies when the Commission wants to update the list of high-risk use cases?"
H74_A = ("I'm a musician and use an AI tool to create backing vocals for my album. Do I have to "
         "label the tracks as AI-generated?")
H10_A = "How does the AI Act distinguish a provider from a deployer?"
H16_A = ("Can an employer use webcams with AI to detect whether call-centre staff are frustrated "
         "or stressed?")
HD_A = "Would an AI module that controls a surgical robot's movements be a high-risk AI system?"

#: The R467 phrasings of the use-case ask, which keep the "Yes" lead.
Q17_ORIGINAL = (
    "Can the European Commission amend Annex III of the EU AI Act to add or modify "
    "use-cases classified as high-risk AI systems? Under what conditions?"
)
Q17_ENTRY_INTO_FORCE = (
    "How can the Commission add a new high-risk use case to Annex III, and what "
    "must happen before the delegated act enters into force?"
)
Q17_YES_LEAD = "Yes, but only within the limits Article 7 sets."


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


# ── 1. The rephrasings reach their verdicts ─────────────────────────────────


@pytest.mark.parametrize(
    ("question", "name"),
    [
        (H45_A, "instructions_for_use_categories"),
        (H96_A, "annex_iii_areas_healthcare"),
        (H17_A, "annex_iii_amendment"),
        (H17_B, "annex_iii_amendment"),
        (H74_A, "deepfake_artistic_disclosure"),
        (H16_A, "workplace_emotion_and_stress"),
    ],
)
def test_the_rephrasing_reaches_its_statutory_verdict(question, name):
    verdict = curated_statutory_verdict(question)
    assert verdict is not None, "the rephrasing missed every statutory detector"
    assert verdict["name"] == name


def test_distinguish_is_a_role_contrast():
    assert impl._detect_role_difference_inquiry(H10_A)


def test_a_would_be_ask_is_a_robotic_surgery_verdict_ask():
    assert impl._detect_robotic_surgery_inquiry(HD_A)


def test_the_scope_bridge_admits_the_call_centre_question():
    from app.engines.statutory_precision import is_workplace_monitoring_ask

    assert is_workplace_monitoring_ask(H16_A)


# ── 2. The wire no longer repeats the review's defects ──────────────────────


def test_the_musician_is_not_assumed_to_be_a_deployer(ask):
    answer = ask(H74_A)["answer"]
    assert answer.startswith("Making AI-generated audio does not by itself put a marking duty")
    assert "Article 50(2)" in answer and "Article 2(10)" in answer
    assert "liner notes" not in answer.lower()


def test_stress_is_not_treated_as_an_emotion(ask):
    answer = ask(H16_A)["answer"]
    assert answer.startswith("No as to the emotions:")
    assert "Stress is separate: Recital 18" in answer
    assert "Annex III, point 4(b)" in answer


def test_the_device_class_is_derived_not_assumed(ask):
    body = ask(HD_A)
    assert "Article 51(1)), which the question does not state" in body["answer"]
    assert "Annex I.20" not in body["references"]


def test_the_instructions_for_use_keep_their_qualifiers(ask):
    answer = ask(H45_A)["answer"]
    assert "Article 13(2) requires it to be accompanied by instructions for use" in answer
    assert "(a) the identity and contact details of the provider and, where applicable," in answer
    assert "at the initial conformity assessment, if any" in answer
    assert "(f) where relevant, the mechanisms" in answer


def test_the_area_headings_are_verbatim(ask):
    answer = ask(H96_A)["answer"].lower()
    for heading in ANNEX_III_AREAS:
        assert heading in answer


def test_a_clinical_system_is_pointed_to_article_6_1(ask):
    """A clinical decision-support system can be high-risk outside Annex III."""
    answer = ask(H96_A)["answer"]
    assert "Article 6(1)" in answer
    assert "Regulation (EU) 2017/745" in answer


def test_the_role_contrast_states_cumulative_roles_and_the_transition(ask):
    body = ask(H10_A)
    for anchor in ("Article 3(3)", "Article 3(4)", "Article 3(11)", "Article 25(1)"):
        assert anchor in body["answer"]
    assert "Article 3.3" in body["references"] and "Article 3.4" in body["references"]


def test_a_new_area_ask_is_answered_no(ask):
    answer = ask(H17_A)["answer"]
    assert answer.startswith("No:")
    assert "in any of the areas listed in Annex III" in answer
    assert "Article 112(2)(a)" in answer


def test_the_procedure_rephrasing_states_the_objection_window(ask):
    assert "Article 97(6)" in ask(H17_B)["answer"]


@pytest.mark.parametrize("question", [Q17_ORIGINAL, Q17_ENTRY_INTO_FORCE])
def test_a_use_case_amendment_keeps_the_yes_lead(ask, question):
    assert ask(question)["answer"].startswith(Q17_YES_LEAD)


def test_a_new_area_answer_states_what_a_delegated_act_can_do(ask):
    """The No answers the area; within the listed areas the use-case route remains."""
    answer = ask(H17_A)["answer"]
    assert "Article 7(1)(b)" in answer
    assert "Yes" not in answer


def test_a_performance_review_question_no_longer_needs_the_r376_repair(ask, monkeypatch):
    """R376 repairs a generated answer that denied the Article 5(1)(f) ban; the
    question now gets the curated verdict, so the denial cannot be written."""
    monkeypatch.setenv("REGENOLD_PROHIBITION_CONTRADICTION_GUARD", "0")
    answer = ask("Can we use an AI system that infers the emotions of our employees "
                 "during performance reviews?")["answer"]
    assert answer.startswith("No as to the emotions:")
    assert "not among the practices prohibited" not in answer


# ── 3. Near misses stay on their own paths ──────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        # Q74 vocabulary without a marking ask, or without generated content.
        "Can I use AI-generated music on my album without paying royalties?",
        "Must a newspaper label AI-generated articles about the election?",
        "Do I need to label a song I recorded with my band?",
        # Q16 vocabulary without a worker, or without an emotion or stress.
        "Can a hospital use AI to detect whether patients are stressed?",
        "Can an employer use AI to schedule staff shifts?",
        "Can an employer use AI to detect whether staff are tired?",
        # Q45 vocabulary that does not ask for the content.
        "Who must provide the instructions for use of a high-risk AI system?",
        "In which language must the instructions for use be written?",
        # Q96 vocabulary asking about one use case, not the areas.
        "Which Annex III area covers AI that triages patients in a hospital emergency department?",
        # Q17 vocabulary about other lists.
        "Can the Commission add new prohibited practices to Article 5 by delegated act?",
        "Can the Commission amend Annex I by delegated act?",
    ],
)
def test_a_near_miss_gets_no_statutory_verdict(question):
    assert curated_statutory_verdict(question) is None


@pytest.mark.parametrize(
    "question",
    [
        "How does the AI Act distinguish high-risk from limited-risk AI systems?",
        "How do provider obligations differ from deployer obligations?",
        # Found by the pool control: three roles, and the verdict defines two.
        "Does the Act distinguish providers and deployers and importers?",
    ],
)
def test_a_non_definitional_contrast_is_not_the_role_verdict(question):
    assert not impl._detect_role_difference_inquiry(question)


@pytest.mark.parametrize(
    "question",
    [
        "Who counts as the provider of a surgical robot when a hospital fine-tunes it?",
        "Would a surgical robot need to be registered in the EU database?",
    ],
)
def test_a_robot_question_that_asks_no_risk_verdict_is_not_the_verdict(question):
    assert not impl._detect_robotic_surgery_inquiry(question)


# ── 5. Iteration 2: held-out set 1, development data now ────────────────────
#
# Iteration 1 moved 2 of held-out set 1's 28 targets. The set was then read to
# design the iteration-2 cues, so its rows are development data here; held-out
# set 2 (written blind, committed before these tests) measures iteration 2.

HELDOUT_1 = json.loads(
    (Path(__file__).resolve().parents[1] / "docs" / "measurements" / "r469"
     / "heldout_rephrasings.json").read_text(encoding="utf-8")
)["rows"]
#: The statutory verdict each family's targets should reach.
STATUTORY_FAMILY = {
    "Q74": "deepfake_artistic_disclosure",
    "Q16": "workplace_emotion_and_stress",
    "Q45": "instructions_for_use_categories",
    "Q96": "annex_iii_areas_healthcare",
    "Q17": "annex_iii_amendment",
    "Q95": "annex_iii_area_vs_use_case",
    "Q104": "annex_x_overview",
}
#: Targets that ask for ONE item of a statutory list stay on the ordinary path:
#: the whole Article 13(3) list would answer "must the instructions describe
#: pre-determined changes if none are planned?" at ten times its length.
SINGLE_ITEM = {"N45_t2"}
#: Q10 targets that ask how a deployer becomes the provider take the Article 25(1)
#: reclassification verdict, which states each route's condition.
RECLASSIFICATION = {"N10_t3", "N10_t4"}
#: Known misses, kept so the record is honest. ND_t1 opens "We're a Munich
#: start-up ...": the scenario opener keeps it with the scenario classifier, and
#: lifting that guard for the robotic-surgery verdict would fire on a davidath
#: scenario row (the invariant ``test_r144_emotion_curated`` pins).
KNOWN_MISSES = {"ND_t1"}


def _family_route(row: dict) -> bool:
    """Does the question reach its family's vetted answer?"""
    question, family = row["question"], row["family"]
    if family in STATUTORY_FAMILY:
        verdict = curated_statutory_verdict(question)
        return verdict is not None and verdict["name"] == STATUTORY_FAMILY[family]
    if family == "CASE_D":
        return impl._detect_robotic_surgery_inquiry(question)
    if family == "Q10":
        if row["id"] in RECLASSIFICATION:
            return impl._detect_reclassification_inquiry(question)
        return impl._detect_role_difference_inquiry(question)
    if family == "Q6":
        return impl._detect_minimal_risk_inquiry(question)
    raise AssertionError(f"no route rule for family {family}")


@pytest.mark.parametrize(
    "row",
    [r for r in HELDOUT_1
     if r["kind"] == "target" and r["id"] not in SINGLE_ITEM | KNOWN_MISSES],
    ids=lambda r: r["id"],
)
def test_a_held_out_set_1_target_reaches_its_verdict(row):
    assert _family_route(row), row["note"]


@pytest.mark.parametrize("rid", sorted(KNOWN_MISSES))
def test_a_known_miss_is_still_missed(rid):
    """A tripwire: if this starts passing, move the row out of KNOWN_MISSES."""
    row = next(r for r in HELDOUT_1 if r["id"] == rid)
    assert not _family_route(row)


@pytest.mark.parametrize(
    "row", [r for r in HELDOUT_1 if r["kind"] == "control"], ids=lambda r: r["id"]
)
def test_a_held_out_set_1_control_does_not(row):
    assert not _family_route(row), row["note"]


@pytest.mark.parametrize("rid", sorted(SINGLE_ITEM))
def test_a_single_item_ask_stays_on_the_ordinary_path(rid):
    row = next(r for r in HELDOUT_1 if r["id"] == rid)
    assert curated_statutory_verdict(row["question"]) is None


def _set_1(rid: str) -> str:
    return next(r["question"] for r in HELDOUT_1 if r["id"] == rid)


@pytest.mark.parametrize(("rid", "lead"), [
    ("N17_t1", Q17_YES_LEAD), ("N17_t2", Q17_YES_LEAD), ("N17_t3", "No:"), ("N17_t4", "No:"),
])
def test_the_amendment_lead_follows_the_shape(rid, lead):
    # At the verdict: on the wire, N17_t2 ("place-based predictive policing") also
    # gets the route's Article 5(1)(d) prefix, a gatekeeper match outside R469.
    assert curated_statutory_verdict(_set_1(rid))["answer"].startswith(lead)


def test_a_new_area_rephrasing_is_answered_no_on_the_wire(ask):
    assert ask(_set_1("N17_t3"))["answer"].startswith("No:")


def test_a_headings_ask_without_healthcare_gets_the_headings_only(ask):
    """"List every area heading ... in full": the healthcare paragraph is unasked."""
    answer = ask(_set_1("N96_t2"))["answer"]
    for heading in ANNEX_III_AREAS:
        assert heading in answer.lower()
    assert "Healthcare decision making is not one of them" not in answer


def test_a_named_annex_x_system_gets_the_transitional_answer(ask):
    answer = ask(_set_1("N104_t1"))["answer"]
    assert "31 December 2030" in answer and "2 February 2025" in answer


@pytest.mark.parametrize("rid", ["N74_t1", "N74_t3", "N16_t1"])
def test_an_anchorless_statutory_shape_is_in_scope(ask, rid):
    """Offline, these were refused as conversational: they name no AI Act anchor."""
    assert ask(_set_1(rid))["references"], "the scope gate refused a statutory shape"


# ── 4. The switch ───────────────────────────────────────────────────────────


def test_the_flag_is_two_sided(monkeypatch):
    monkeypatch.setenv(FLAG, "0")
    assert curated_statutory_verdict(H74_A) is None
    assert curated_statutory_verdict(H96_A) is None
    assert not impl._detect_role_difference_inquiry(H10_A)
    assert not impl._detect_robotic_surgery_inquiry(HD_A)
    assert curated_statutory_verdict(H17_A)["answer"].startswith(Q17_YES_LEAD)


def test_a_blank_value_keeps_the_default(monkeypatch):
    monkeypatch.setenv(FLAG, "")
    assert curated_statutory_verdict(H74_A) is not None


def test_the_flag_is_in_the_engine_cache_key(monkeypatch):
    from app.routes import regenold as route

    monkeypatch.setenv(FLAG, "1")
    on = route._engine_cache_key("q", "ctx")
    monkeypatch.setenv(FLAG, "0")
    assert route._engine_cache_key("q", "ctx") != on
