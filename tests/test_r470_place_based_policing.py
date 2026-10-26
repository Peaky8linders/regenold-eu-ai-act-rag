"""R470 — Article 5(1)(d) is not asserted on place-based crime forecasting.

The route's prohibition gatekeeper (``app/engines/prohibited_gatekeeper.py``)
matches the PRACTICE_REGISTRY keyword "predictive policing". It then:

* forces ``Article 5`` and ``Article 5.1.d`` onto the wire;
* prepends "Risk assessment of natural persons based solely on profiling or
  personality traits is prohibited under Article 5(1)(d).";
* deletes any sentence that says Article 5 does not apply (the R376 guard).

Article 5(1)(d) concerns risk assessments of natural persons. A tool that
forecasts where or when crime will occur, without assessing individuals, is
outside it (recital 42: the prohibition does not touch risk analytics that are
not based on the profiling of individuals). R469's held-out row N17_t2 ("place-
based predictive policing tools (forecasting where crime will happen rather than
who will commit it)") shipped the Article 7 amendment verdict behind the Article
5(1)(d) sentence, and a Stage-2 answer that correctly said Article 5 does not
apply would have lost that sentence to the verdict.

The fix is a negative qualifier on ``Art. 5.1.d``, the shape R376 gave
``Art. 5.1.h`` for post-remote biometric identification: a place-based cue
removes the match unless the question also assesses people (profiling,
personality traits, scoring or flagging individuals), so a comparison or a
look-alike keeps the prohibition.

The blind held-out set that measures the fix
(``docs/measurements/r470/heldout_policing.json``) is not used here.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.engines.prohibited_gatekeeper import build_verdict_prefix, scan_for_prohibitions

FLAG = "REGENOLD_PLACE_BASED_POLICING"
PREFIX_5_1_D = (
    "Risk assessment of natural persons based solely on profiling or personality traits "
    "is prohibited under Article 5(1)(d)."
)
N17_T2 = (
    "If place-based predictive policing tools (forecasting where crime will happen rather "
    "than who will commit it) prove harmful, could the Commission bring them into Annex III "
    "by delegated act, and what has to happen before such an act takes effect?"
)

#: Forecasts places or times and assesses nobody: Article 5(1)(d) does not apply.
PLACE_BASED = [
    N17_T2,
    "Is place-based predictive policing prohibited under the AI Act?",
    "Our police force uses hotspot software that forecasts which neighbourhoods will see "
    "burglaries next week. Is that banned as predictive policing?",
    "Does Article 5 ban location-based predictive policing that predicts where crimes are "
    "likely to occur?",
    "Is predictive policing software that maps where thefts happen, without profiling any "
    "individual, prohibited?",
    "Our city council wants software that forecasts the criminal risk of each district for "
    "next week so it can plan patrols. Is that allowed under the AI Act?",
]

#: Assesses people, or compares the two: the prohibition stays in play.
PERSON_BASED = [
    "Is predictive policing prohibited?",
    "Predictive policing using personality profiling",
    "Is predictive policing that profiles individuals to predict who will commit a crime "
    "prohibited?",
    "A hotspot tool also scores residents of high-crime neighbourhoods as likely offenders "
    "from their personal profiles. Is this predictive policing prohibited?",
    "How does the AI Act treat place-based predictive policing compared with predictive "
    "policing based on profiling individuals?",
    # The davidath scenario row's intended use.
    "Offer a predictive policing AI that assesses the likelihood of individuals committing "
    "crimes based solely on personality traits extracted from social media",
    "Is software that rates each resident's criminal risk from their social-media profile "
    "allowed under the AI Act?",
]


def _subs(question: str) -> set[str]:
    return {sub for _parent, sub in scan_for_prohibitions(question)}


@pytest.mark.parametrize("question", PLACE_BASED)
def test_a_place_based_question_does_not_match_5_1_d(monkeypatch, question):
    monkeypatch.delenv(FLAG, raising=False)
    assert "Art. 5.1.d" not in _subs(question)
    assert build_verdict_prefix(question) is None


@pytest.mark.parametrize("question", PERSON_BASED)
def test_a_person_based_question_keeps_5_1_d(monkeypatch, question):
    monkeypatch.delenv(FLAG, raising=False)
    assert "Art. 5.1.d" in _subs(question)


def test_the_switch_restores_the_match(monkeypatch):
    monkeypatch.setenv(FLAG, "0")
    assert "Art. 5.1.d" in _subs(N17_T2)
    assert build_verdict_prefix(N17_T2) == PREFIX_5_1_D


def test_a_blank_value_keeps_the_default(monkeypatch):
    monkeypatch.setenv(FLAG, "")
    assert "Art. 5.1.d" not in _subs(N17_T2)


@pytest.mark.parametrize(("question", "expected"), [
    # R376's post-remote exclusion is unchanged by the refactor.
    ("Can law enforcement use post-remote biometric identification for a targeted search?",
     False),
    ("Is real-time remote biometric identification treated differently from post remote "
     "biometric identification?", True),
    ("Real-time biometric identification in public spaces", True),
])
def test_the_post_remote_exclusion_is_unchanged(question, expected):
    assert ("Art. 5.1.h" in _subs(question)) is expected


def test_the_flag_is_in_the_engine_cache_key(monkeypatch):
    from app.routes import regenold as route

    monkeypatch.setenv(FLAG, "1")
    on = route._engine_cache_key("q", "ctx")
    monkeypatch.setenv(FLAG, "0")
    assert route._engine_cache_key("q", "ctx") != on


# ── on the wire ──────────────────────────────────────────────────────────────


@pytest.fixture()
def wire(monkeypatch):
    from app.config import settings
    from app.routes import regenold as route

    monkeypatch.setattr(settings.regenold, "api_key", SecretStr("r470-test"))
    monkeypatch.setenv("REGENOLD_SKIP_DOTENV", "1")
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("P2P_GRAPH_RAG_ENABLE_STAGE2", "0")
    from app.main import app
    from app.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    client = TestClient(app)

    def _ask(question: str) -> dict:
        route._ENGINE_CACHE._data.clear()
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           headers={"X-Regenold-Api-Key": "r470-test"},
                           json={"messages": [{"role": "user", "content": question}]})
        assert resp.status_code == 200, resp.text[:300]
        return resp.json()

    yield _ask
    route._ENGINE_CACHE._data.clear()


def test_n17_t2_ships_the_amendment_verdict_without_the_5_1_d_sentence(monkeypatch, wire):
    monkeypatch.delenv(FLAG, raising=False)
    answer = wire(N17_T2)["answer"]
    assert "Article 5(1)(d)" not in answer
    assert answer.startswith("Yes, but only within the limits Article 7 sets")


def test_n17_t2_keeps_the_old_wire_with_the_switch_off(monkeypatch, wire):
    monkeypatch.setenv(FLAG, "0")
    assert wire(N17_T2)["answer"].startswith(PREFIX_5_1_D)


@pytest.fixture()
def stage2_answer(monkeypatch, wire):
    """The route with the engine stubbed to return a given (Stage-2-shaped) answer."""
    from unittest.mock import Mock

    from app.engines import clara_logic
    from app.models import CitationNode, GraphRAGResponse
    from app.routes import regenold as route

    monkeypatch.setattr(clara_logic, "analyse", Mock(return_value=(None, None)))

    def _ask(question: str, answer: str) -> dict:
        monkeypatch.setattr(route, "ask_compliance_question", Mock(return_value=GraphRAGResponse(
            answer=answer,
            citations=[CitationNode(node_type="Article", node_id="art-5", text="Prohibited",
                                    article_ref="Art. 5")],
            confidence=0.9, graph_stats={"nodes_traversed": 1},
        )))
        return wire(question)

    return _ask


# Neither question names "predictive policing", so neither reaches the engine's
# ``predictive_policing`` classification topic, whose curated text the route ships
# without the R376 strip or the verdict prepend. Both match the gatekeeper's
# "criminal risk" keyword, which is where a Stage-2 answer meets the guard.
DISTRICT_FORECAST = (
    "Our city council wants software that forecasts the criminal risk of each district for "
    "next week so it can plan patrols. Is that allowed under the AI Act?"
)
RESIDENT_SCORING = (
    "Is software that rates each resident's criminal risk from their social-media profile "
    "allowed under the AI Act?"
)
DENIAL = (
    "Forecasting the criminal risk of districts is not prohibited under Article 5, because the "
    "system assesses places, not natural persons. Article 5(1)(d) covers only risk assessments "
    "of natural persons based solely on profiling or personality traits."
)


def test_a_correct_denial_survives_on_a_place_based_question(monkeypatch, stage2_answer):
    monkeypatch.delenv(FLAG, raising=False)
    answer = stage2_answer(DISTRICT_FORECAST, DENIAL)["answer"]
    assert "is not prohibited under Article 5" in answer
    assert PREFIX_5_1_D not in answer


def test_the_denial_is_still_replaced_on_a_profiling_question(monkeypatch, stage2_answer):
    """R376 unchanged: a denial on a person-based question gives way to the verdict."""
    monkeypatch.delenv(FLAG, raising=False)
    answer = stage2_answer(
        RESIDENT_SCORING,
        "Rating residents in this way is not prohibited under Article 5. Article 26 sets the "
        "deployer duties.",
    )["answer"]
    # The grounded-prose pass may lead with its own Article 5.1.d gloss, so the
    # verdict is asserted present rather than first.
    assert PREFIX_5_1_D in answer
    assert "is not prohibited under Article 5" not in answer
