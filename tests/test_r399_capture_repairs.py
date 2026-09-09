"""Statutory regressions found in the Sept 7 capture, without its private gold."""
import pytest

from app.data.provision_text import get_provision_text
from app.engines import _graph_rag_impl as impl
from app.routes.regenold import _deepen_one_ref


@pytest.mark.parametrize("question", [
    "Are AI safety components within medical devices of MDR class IIa, IIb, or III considered to be high-risk according to the EU AI Act? Why?",
    "Is an AI safety component of a toy subject to third-party conformity assessment high-risk?",
])
def test_product_route_is_not_relabelled_annex_iii(question):
    answer = (
        "The AI system is high-risk under Article 6(1) if it is a safety component "
        "of a product covered by Annex I legislation and that product requires "
        "third-party conformity assessment."
    )
    assert _deepen_one_ref("Article 6", question, answer) == "Article 6.1"


def test_annex_iii_route_stays_distinct():
    assert _deepen_one_ref(
        "Article 6", "Are recruitment AI systems listed in Annex III high-risk?",
        "Article 6(2) classifies the listed Annex III systems as high-risk.",
    ) == "Article 6.2"


def test_product_route_does_not_follow_excluded_derogation_in_answer():
    assert _deepen_one_ref(
        "Article 6", "Could software supporting clinicians in treatment decisions be high-risk?",
        "Under Article 6(1), medical-device AI requiring third-party conformity "
        "assessment is high-risk. Article 6(3)'s narrow procedural task, preparatory "
        "task and decision-making-pattern exceptions are unavailable on that route.",
    ) == "Article 6.1"


@pytest.mark.parametrize("question", [
    "What are all the risk categories in the EU AI Act?",
    "What are AI systems with minimal risks?",
])
def test_minimal_risk_does_not_erase_general_ai_literacy_duties(question):
    answer = impl._deterministic_answer(question, impl.GraphContext(question=question))
    assert "Article 4" in answer
    assert "literacy" in answer
    assert "voluntary" in answer and "95" in answer
    # Excluding Chapter III duties is correct; denying ALL Act duties is not.
    assert "carry no mandatory obligations under the Regulation" not in answer
    assert "no mandatory duties under the Act" not in answer


def test_scope_identifies_market_acts_for_both_regimes():
    question = "Does the EU AI Act apply to AI systems or AI models or both?"
    answer = impl._deterministic_answer(question, impl.GraphContext(question=question))
    assert answer.startswith("Both.")
    assert "Article 2(1)(a)" in answer
    assert "putting" in answer and "service" in answer
    assert "placing general-purpose AI models on the market" in answer


def test_general_duty_and_scope_corrections_follow_adopted_text():
    assert "Providers and deployers of AI systems" in get_provision_text("Article 4")
    assert "AI literacy" in get_provision_text("Article 4")
    assert "placing on the market general-purpose AI models" in get_provision_text("Article 2.1.a")


@pytest.mark.parametrize("question,required", [
    ("What are all the risk categories in the EU AI Act?", ("Article 4", "literacy", "95")),
    ("What are AI systems with minimal risks?", ("Article 4", "literacy", "95")),
    ("Does the EU AI Act apply to AI systems or AI models or both?", ("Article 2(1)(a)", "putting", "general-purpose AI models")),
])
def test_corrections_survive_the_real_route(monkeypatch, question, required):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.config import settings
    from app.main import app
    from app.rate_limit import limiter
    from app.routes.regenold import _ENGINE_CACHE

    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "cli")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDINGS", "0")
    monkeypatch.setattr(settings.regenold, "api_key", SecretStr("r399-local-test"))
    limiter.reset()
    _ENGINE_CACHE.clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/regenold/eu-ai-act/ask?include_reasoning=false",
                json=[{"role": "user", "content": question}],
                headers={"X-Regenold-Api-Key": "r399-local-test"},
            )
        assert response.status_code == 200, response.text
        for phrase in required:
            assert phrase in response.json()["answer"]
    finally:
        _ENGINE_CACHE.clear()


# ---------------------------------------------------------------------------
# R399 batch 2 — the two defects the review recorded as still open after the
# first batch: the missing storage/transport safeguards (rg_069, 0/3 easy) and
# the lexical deepener overwriting a correct head with the wrong coordinate
# (rg_008 "Annex I.19", rg_001 "Annex IV.2").
# ---------------------------------------------------------------------------

_RG_069 = (
    "I am a distributor of an AI systems. Do I have obligation not to jeopardize "
    "its conformity? I was not told if the system is high-risk or not. What if am "
    "I am importer instead?"
)


@pytest.mark.parametrize("ize,ise", [
    ("jeopardize", "jeopardise"),
    ("harmonized", "harmonised"),
    ("organization", "organisation"),
    ("standardization", "standardisation"),
    ("categorizing", "categorising"),
    ("authorize", "authorise"),
])
def test_ize_and_ise_spellings_share_a_token(ize, ise):
    """The adopted text is predominantly -ise; questions arrive in -ize."""
    from app.data.provision_text import _stem

    assert _stem(ize) == _stem(ise)


@pytest.mark.parametrize("word", ["size", "sized", "prize", "seize", "maize"])
def test_the_fold_leaves_non_suffix_ize_words_alone(word):
    """``ize`` is not a suffix in these, so the prefix floor must exclude them."""
    from app.data.provision_text import _oxford_z, _stem

    assert _oxford_z(word) == word
    assert "is" not in _stem(word)[max(0, len(_stem(word)) - 2):]


def test_importer_storage_and_transport_duty_reaches_the_evidence_block():
    """rg_069's operative importer paragraph, lost to a spelling variant.

    Article 23(4) is the ONLY paragraph answering "obligation not to jeopardize
    its conformity" on the importer limb. Before the fold it scored below two
    paragraphs that merely share boilerplate and fell outside the budget.
    """
    from app.data.provision_text import select_relevant_paragraphs

    body = select_relevant_paragraphs("Article 23", _RG_069, 1200) or ""
    assert "storage or transport" in body
    assert "jeopardise" in body


def test_the_fold_is_symmetric_not_a_rewrite_of_the_statute():
    """Only the token index folds; the verbatim text we quote is untouched."""
    from app.data.provision_text import get_provision_text

    assert "jeopardise" in get_provision_text("Article 24.3")
    assert "jeopardize" not in get_provision_text("Article 24.3")


@pytest.mark.parametrize("head,question,answer,expected", [
    # rg_008 — the answer names point 11 across a clause; point 19 is motor
    # vehicle type-approval and was what shipped.
    (
        "Annex I",
        "Are AI safety components within medical devices of MDR class IIa, IIb, "
        "or III considered to be high-risk according to the EU AI Act? Why?",
        "The product is covered by the Union harmonisation legislation listed in "
        "Annex I, which includes Regulation (EU) 2017/745 (MDR) at point 11, and "
        "a device of MDR class IIa must undergo third-party conformity assessment.",
        "Annex I.11",
    ),
    # rg_001 — the answer answers the hardware question at point 1(e).
    (
        "Annex IV",
        "Does the technical documentation of a high-risk AI system require to "
        "provide specifications regarding the required hardware?",
        "Under Article 11, a provider must draw up technical documentation "
        "containing the information set out in Annex IV, which expressly requires "
        "a description of the hardware on which the AI system is intended to run "
        "(Annex IV point 1(e)).",
        "Annex IV.1",
    ),
    # rg_098 — the question asks what Annex VII point 5.1 says.
    (
        "Annex VII",
        "What does Annex VII point 5.1 say? Try to get the substance right.",
        "Annex VII point 5.1 opens the surveillance stage of the notified-body "
        "conformity assessment procedure.",
        "Annex VII.5",
    ),
])
def test_deepener_honours_a_point_the_answer_itself_names(head, question, answer, expected):
    assert _deepen_one_ref(head, question, answer) == expected


def test_deepener_abstains_when_the_prose_names_several_points():
    """Naming a LIST of points names none of them in particular.

    Without this the first listed number was promoted to THE coordinate, which
    measured three lateral-or-wrong moves against four clear wins.
    """
    from app.routes.regenold import _prose_named_annex_point

    units = {n: "" for n in range(1, 9)}
    assert _prose_named_annex_point(
        "III", "systems in Annex III points 1, 6 and 7 are registered separately.", units
    ) is None
    assert _prose_named_annex_point(
        "III", "the areas in Annex III points 1 and 2 differ.", units
    ) is None
    assert _prose_named_annex_point(
        "III", "the area in Annex III point 5 on essential services.", units
    ) == 5


def test_a_point_from_another_annex_never_matches():
    from app.routes.regenold import _prose_named_annex_point

    units = {n: "" for n in range(1, 21)}
    assert _prose_named_annex_point(
        "I", "Annex IV point 2 lists the development description.", units
    ) is None


def test_the_named_point_must_exist_in_the_annex():
    from app.routes.regenold import _prose_named_annex_point

    assert _prose_named_annex_point("IV", "Annex IV point 88 says so.", {1: "", 2: ""}) is None


def test_the_prose_rule_never_changes_a_reference_head():
    """Hard rule #8 holds by construction: only the coordinate below the head
    can move, so ``gold_dropped_head`` (which folds both sides onto heads)
    cannot see this lever. Measured over the full Sept 7 capture: 220 rows,
    7 coordinates changed, 0 head-changing diffs."""
    import re as _re

    cases = [
        ("Annex I", "medical devices under MDR", "Annex I point 11 covers the MDR."),
        ("Annex IV", "hardware specifications", "Annex IV point 1(e) covers hardware."),
        ("Annex VII", "what does point 5.1 say", "Annex VII point 5.1 opens surveillance."),
    ]
    for head, q, a in cases:
        out = _deepen_one_ref(head, q, a)
        assert _re.match(r"^Annex\s+[IVXL]+", out).group(0) == head
