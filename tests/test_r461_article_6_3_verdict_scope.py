"""R461 — the canned Article 6(3) verdict ships only for the system it is about.

The verdict opens "No. Structuring or deduplicating information is a narrow
procedural task, so the system ... is not high-risk". Before R461 the Article
6(3) intercept shipped it, and skipped Stage-2, for ANY "can <system> benefit
from the Article 6(3) derogation?" ask: credit scoring, CV screening, asylum
examination, a pathology tool. Each was told it is not high-risk because it
structures information, which none of them was said to do. Credit scoring and
CV screening are Annex III uses that profile natural persons, so the last
subparagraph of Article 6(3) makes them high-risk in every case.

The fix is structural, not a list of uses: the verdict ships when the question
describes its system by the verdict's own task, or describes no system at all
(a question about the derogation itself). These tests assert on the detector,
the deterministic answer and its seeded references, the Stage-2 skip, and the
wire, never on source text.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.data.provision_text import get_provision_text
from app.engines._graph_rag_impl import (
    GraphContext,
    _detect_article_6_3_inquiry,
    _deterministic_answer,
    _is_curated_authoritative_intercept,
)
from app.main import app
from app.rate_limit import limiter

_CANNED = "No. Structuring or deduplicating information is a narrow procedural task"

# One or more phrasings per Annex III area, in different syntactic shapes (a
# premodified noun, a relative clause, a participle, a finite verb), plus a
# recorded corpus row (scenarios_medtech_lifesci mt_15). Every one fired the
# intercept before R461.
OTHER_USE = [
    "Can a credit scoring AI system benefit from the Article 6(3) derogation?",
    "Is an AI system that evaluates the creditworthiness of loan applicants exempt under "
    "Article 6(3)?",
    "Can a CV-screening AI used by an employer benefit from the Article 6(3) derogation?",
    "Can an AI system used to rank job applicants claim the high-risk exemption?",
    "Does Article 6(3) exempt an AI tool that allocates tasks to workers based on their "
    "behaviour?",
    "Does the Article 6(3) exception apply to a remote biometric identification system?",
    "Does Article 6(3) exempt an emotion recognition system used at border controls from "
    "high-risk classification?",
    "Can an AI safety component of a water supply network benefit from the Article 6(3) "
    "derogation?",
    "Can an AI system that evaluates students' learning outcomes rely on the Article 6(3) "
    "exemption?",
    "Is an exam proctoring AI that detects cheating eligible for the high-risk exemption?",
    "Is an AI system that assesses eligibility for public assistance benefits exempt under "
    "Article 6(3)?",
    "Is a life insurance pricing AI eligible for the Article 6(3) derogation?",
    "Can an AI system that evaluates and classifies emergency calls rely on the Article 6(3) "
    "derogation?",
    "Can a police risk-assessment tool predicting reoffending use the Article 6(3) derogation?",
    "Can predictive policing tools rely on the Article 6(3) exemption?",
    "Is an AI system that examines asylum applications exempt from high-risk classification "
    "under Article 6(3)?",
    "Is an AI tool that helps judges research and interpret facts and the law exempt under "
    "Article 6(3)?",
    "Could an AI system that influences how people vote in elections fall under the Article "
    "6(3) exemption?",
    "Does the Article 6(3) derogation apply to software ranking students for university "
    "admission?",
    "An AI tool flags suspicious cells on pathology slides, but a pathologist always makes the "
    "final diagnosis. Could the Article 6(3) derogation make it not high-risk, and what must "
    "the provider do to rely on it?",
]

# The verdict's own class: the system structures / deduplicates / organises
# information, or performs a narrow procedural or preparatory task.
RG_031 = (
    "Is an AI system used to structure or deduplicate information for a use case listed in "
    "Annex III considered high-risk?"
)
PROCEDURAL = [
    RG_031,
    "Can an AI system that only deduplicates records in a credit file benefit from the "
    "Article 6(3) derogation?",
    "Does the Article 6(3) derogation cover an AI system that organises information in "
    "applicant files?",
    "Is a tool that structures unstructured data for a recruitment workflow exempt under "
    "Article 6(3)?",
    "Is a system that just deduplicates customer records exempt under Article 6(3)?",
    "Can an AI system that performs a narrow procedural task benefit from the high-risk "
    "exemption?",
    "Is our system exempt under Article 6(3) if it performs only preparatory tasks?",
]

# Questions about the derogation that describe no particular system. They fired
# before R461 and must keep firing (the tests/test_r411_mention_vs_ask contract).
GENERIC = [
    "What are the self-assessment requirements under Article 6(3)?",
    "What does the Article 6(3) exception require?",
    "How do we self-assess as not high-risk under Article 6(3)?",
    "What are the conditions of the Article 6(3) derogation?",
    "What is the high-risk exemption under the AI Act?",
    "Does the Article 6(3) derogation apply to our Annex III system?",
    "Is the Article 6(3) exception available for an AI system referred to in Annex III?",
    "Can a provider of an Annex III AI system rely on the Article 6(3) derogation?",
    "Which conditions must a high-risk AI system meet to be exempt under Article 6(3)?",
    "Can our AI system be classified as not high-risk under Article 6(3)?",
    "Which AI systems can rely on the Article 6(3) derogation?",
    "What must a provider document before relying on the Article 6(3) derogation?",
]


def _answer(question: str) -> tuple[str, list[str]]:
    context = GraphContext(question=question)
    answer = _deterministic_answer(question, context)
    return answer, [o.get("article") for o in (context.obligations or [])]


@pytest.mark.parametrize("question", OTHER_USE)
def test_another_system_does_not_get_the_structuring_verdict(question: str) -> None:
    assert not _detect_article_6_3_inquiry(question)
    answer, refs = _answer(question)
    assert not answer.startswith(_CANNED), answer[:160]
    assert "Art. 6.3.a" not in refs


@pytest.mark.parametrize(
    "question",
    [q for q in OTHER_USE if "emotion recognition" not in q],
)
def test_another_system_keeps_stage2(question: str) -> None:
    """The canned verdict skipped Stage-2; nothing else curated owns these rows.

    The emotion-recognition row is excluded because the emotion cross-tier
    intercept owns it (and states it is high-risk under Annex III(1)(c)).
    """
    assert not _is_curated_authoritative_intercept(question)


def test_the_emotion_row_now_gets_its_own_intercept() -> None:
    q = next(q for q in OTHER_USE if "emotion recognition" in q)
    answer, refs = _answer(q)
    assert "Annex III.1.c" in refs
    assert "high-risk under Annex III(1)(c)" in answer


@pytest.mark.parametrize("question", PROCEDURAL)
def test_the_verdicts_own_system_keeps_it(question: str) -> None:
    assert _detect_article_6_3_inquiry(question)
    assert _is_curated_authoritative_intercept(question)
    answer, refs = _answer(question)
    assert answer.startswith(_CANNED)
    assert "Art. 6.3.a" in refs


def test_rg031_answer_is_unchanged() -> None:
    """Every procedural phrasing gets the byte-identical rg_031 answer."""
    expected, expected_refs = _answer(RG_031)
    assert expected.startswith("No.") and "point (a)" in expected
    for q in PROCEDURAL[1:]:
        assert _answer(q) == (expected, expected_refs)


@pytest.mark.parametrize("question", GENERIC)
def test_a_question_about_the_derogation_itself_still_fires(question: str) -> None:
    assert _detect_article_6_3_inquiry(question)


def test_the_profiling_rule_is_the_verbatim_statute() -> None:
    """The legal ground for the fix, read from the corpus, not from memory."""
    art_6_3 = get_provision_text("Article 6.3") or ""
    assert (
        "shall always be considered to be high-risk where the AI system performs "
        "profiling of natural persons"
    ) in art_6_3
    assert "evaluate the creditworthiness of natural persons" in (
        get_provision_text("Annex III.5.b") or ""
    )
    assert "analyse and filter job applications" in (get_provision_text("Annex III.4.a") or "")


_EVAL_KEY = "regenold-bench-eval-key"


@pytest.fixture
def _client():
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_EVAL_KEY)
    try:
        with TestClient(app, headers={"X-Regenold-Api-Key": _EVAL_KEY}) as c:
            yield c
    finally:
        settings.regenold.api_key = prev


def _wire(client: TestClient, question: str) -> str:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask", json=[{"role": "user", "content": question}]
    )
    assert resp.status_code == 200
    return resp.json().get("answer") or ""


def test_the_wire_answers_credit_scoring_and_rg031_differently(_client: TestClient) -> None:
    """Measured before R461: both shipped the same canned "not high-risk" answer."""
    assert _CANNED not in _wire(_client, OTHER_USE[0])
    assert _CANNED not in _wire(_client, OTHER_USE[2])
    assert _CANNED in _wire(_client, RG_031)
