"""R471 — the predictive-policing topic no longer calls place-based policing high-risk.

The ``predictive_policing`` classification topic (``app/engines/_graph_rag_data.py``)
read: "Place-based or non-profiling predictive policing remains permitted, but is
high-risk under Annex III and subject to Chapter III Section 2 obligations."

Annex III point 6 lists law-enforcement systems that assess natural persons
(points (a), (d) and (e)), polygraphs (b) and the reliability of evidence (c). A
tool that forecasts where or when crime will occur, without assessing anyone, is
none of them, and recital 42 puts it outside Article 5(1)(d). The high-risk half
of the sentence holds only for assessing a person's risk of offending not solely
on the basis of profiling, which is point 6(d).

The text is the deterministic answer to a "is predictive policing prohibited?"
question: the Stage-2 draft on the live path, and the shipped answer whenever
Stage-2 does not land.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.engines._graph_rag_impl import _detect_classification_topic

QUESTION = "Is predictive policing prohibited under the AI Act?"
OLD_SENTENCE = "Place-based or non-profiling predictive policing remains permitted"


def _topic_answer() -> str:
    topic = _detect_classification_topic(QUESTION)
    assert topic is not None and topic["name"] == "predictive_policing"
    return topic["answer"]


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def test_no_sentence_calls_place_based_policing_high_risk():
    for sentence in _sentences(_topic_answer()):
        if re.search(r"\b(?:place|location|area)[- ]based\b|\bwhere or when\b", sentence, re.I):
            assert "high-risk" not in sentence, sentence


def test_the_high_risk_case_is_the_annex_iii_6_d_one():
    answer = _topic_answer()
    assert "high-risk under Annex III point 6(d)" in answer
    assert "offending or re-offending not solely on the basis of profiling" in answer


def test_place_based_forecasting_is_outside_article_5_1_d_and_annex_iii_6():
    answer = _topic_answer()
    assert "forecasts where or when crime will occur" in answer
    assert "outside Article 5(1)(d)" in answer
    assert "not among the law-enforcement uses listed in Annex III point 6" in answer


def test_every_sentence_carries_a_provision_anchor():
    """R447 rule 2: the soft char cap drops an unanchored sentence first."""
    for sentence in _sentences(_topic_answer()):
        assert re.search(r"\b(?:Article|Annex)\s", sentence), sentence


@pytest.mark.parametrize(("phrase", "source"), [
    # Article 5(1)(d).
    ("the risk of a natural person committing a criminal offence", "official_eu_ai_act.py"),
    # Annex III point 6(d).
    ("offending or re-offending not solely on the basis of", "eu_ai_act_corpus.py"),
])
def test_the_wording_is_the_act_s(phrase, source):
    """The text's statutory phrases appear verbatim in the Act's own text."""
    assert phrase in _topic_answer()
    text = open(f"app/data/{source}", encoding="utf-8").read().replace("\xa0", " ")
    flat = re.sub(r"\s+", " ", re.sub(r"'\s*\n\s*'", "", text))
    assert phrase in flat


@pytest.fixture()
def ask(monkeypatch):
    from pydantic import SecretStr

    from app.config import settings
    from app.main import app
    from app.rate_limit import limiter
    from app.routes import regenold as route

    monkeypatch.setattr(settings.regenold, "api_key", SecretStr("r471-test"))
    for key, value in {"REGENOLD_SKIP_DOTENV": "1", "P2P_GRAPH_RAG_PROVIDER": "cli",
                       "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
                       "P2P_GRAPH_RAG_ENABLE_STAGE2": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(limiter, "enabled", False)
    client = TestClient(app)

    def _ask(question: str) -> dict:
        route._ENGINE_CACHE._data.clear()
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           headers={"X-Regenold-Api-Key": "r471-test"},
                           json={"messages": [{"role": "user", "content": question}]})
        assert resp.status_code == 200, resp.text[:300]
        return resp.json()

    yield _ask
    route._ENGINE_CACHE._data.clear()


@pytest.mark.parametrize("question", [
    "Is predictive policing prohibited?",
    "Is place-based predictive policing prohibited under the AI Act?",
])
def test_the_deterministic_answer_ships_the_corrected_text(ask, question):
    answer = ask(question)["answer"]
    assert OLD_SENTENCE not in answer
    assert "high-risk under Annex III point 6(d)" in answer
    assert "outside Article 5(1)(d)" in answer
