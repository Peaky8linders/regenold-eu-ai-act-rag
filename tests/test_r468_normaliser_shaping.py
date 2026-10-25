"""R468 — three answer-shaping defects in ``normalise_answer_for_regenold``.

Found by the R467 held-out run and its review (``docs/measurements/r467``):

1. **List flattening.** ``_strip_markdown`` turns every line into a sentence and
   promotes a line-final colon to a period, so a list the answer introduces
   ("The other required contents are:" + bullets) shipped as a dangling
   "The other required contents are." followed by sentence fragments (live
   held-out row H45_b; 20-odd recorded live answers show the shape, e.g. "The
   eight areas are. Biometrics. Critical infrastructure.").
2. **Meta-leak false positive.** ``_META_LEAK_SUBSTRINGS`` matched "graph does
   not", "graph provides", "graph contains" ... as plain substrings, so a sentence
   about a "paragraph" or "subparagraph" was deleted as meta-commentary.
3. **Curated sentences the char cap can drop.** The 400-char soft cap drops the
   longest sentence without an ``article`` / ``annex`` token. R447 made "every
   sentence of a curated answer carries a provision anchor" a rule; 15 curated
   drafts broke it, and on the official questions the cap deleted a verdict lead
   ("Not automatically.", "Systemic risk applies to general-purpose AI models,
   not to AI systems.") or a statutory clause (Article 10(5)'s "in addition to"
   GDPR clause).
"""
from __future__ import annotations

import inspect
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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _anchored(sentence: str) -> bool:
    """The soft char cap's own test (``_has_cite_anchor`` in the normaliser)."""
    low = sentence.lower()
    return "art." in low or "annex" in low or "article " in low


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


@pytest.fixture()
def live_shaping():
    """The live Stage-2 regime: the route sets the request-scoped uncap."""
    from app.integrations.regenold import models

    models.set_answer_no_cap(True)
    yield models
    models.set_answer_no_cap(False)


# ── 1. A colon-introduced list stays one sentence ───────────────────────────

#: The live H45_b Stage-2 answer's shape before normalisation.
H45B_RAW = (
    "Yes. Article 13(3) requires the instructions for use that accompany a high-risk AI "
    "system to cover both topics.\n"
    "Under Article 13(3)(d), they must set out the human oversight measures, including the "
    "technical measures that help deployers interpret the system's outputs.\n"
    "The other required contents are:\n"
    "- The provider's identity and contact details.\n"
    "- The system's characteristics, capabilities and limitations of performance.\n"
    "- Any changes the provider decided in advance.\n"
    "- The computational and hardware resources needed, the expected lifetime and the "
    "maintenance measures.\n"
    "The human oversight item always applies."
)

AREAS_RAW = (
    "Annex III sets out the high-risk areas. The eight areas are:\n"
    "1. Biometrics\n"
    "2. Critical infrastructure\n"
    "3. Education and vocational training\n"
    "4. Employment, workers' management and access to self-employment\n"
    "Each area lists specific use cases under Article 6(2)."
)


def test_a_colon_introduced_list_is_inlined(live_shaping):
    out = live_shaping.normalise_answer_for_regenold(H45B_RAW, question="Does Article 13 cover logs?")
    assert "The other required contents are: the provider's identity and contact details; " in out
    assert "; any changes the provider decided in advance; " in out
    assert "are. " not in out
    assert "The human oversight item always applies." in out


def test_a_numbered_list_is_inlined_and_keeps_its_headings(live_shaping):
    out = live_shaping.normalise_answer_for_regenold(AREAS_RAW, question="Which areas are high-risk?")
    assert (
        "The eight areas are: biometrics; critical infrastructure; education and vocational "
        "training; employment, workers' management and access to self-employment."
    ) in out


def test_a_proper_noun_keeps_its_capital(live_shaping):
    raw = "The requirements include:\n- Article 9 risk management.\n- Data governance under Article 10."
    out = live_shaping.normalise_answer_for_regenold(raw, question="What is required?")
    assert "include: Article 9 risk management; data governance under Article 10." in out


#: Five of the 23 recorded live cases open the list with a two-word intro
#: ("These include:", "This covers:", "These are:"). On a line of its own such an
#: intro is still prose, not a heading.
@pytest.mark.parametrize("intro", ["These include:", "This covers:", "These are:"])
def test_a_two_word_intro_is_inlined(live_shaping, intro):
    raw = (
        "Article 7(2) lists the criteria the Commission must weigh.\n"
        f"{intro}\n- The intended purpose.\n- The extent of use.\n"
        "The list is not exhaustive."
    )
    out = live_shaping.normalise_answer_for_regenold(raw, question="What does Article 7(2) require?")
    assert f"{intro} the intended purpose; the extent of use." in out


@pytest.mark.parametrize(
    "raw",
    [
        # A heading label, which the normaliser drops as a label-only sentence.
        "### Key Requirements:\n- Use the system per the instructions.\n- Keep the logs.",
        # A colon line not followed by list items.
        "Note the following:\nThe deployer must inform the workers under Article 26(7).",
        # A list item that is itself more than one sentence.
        "The duties are:\n- Keep the logs. They must be retained.\n- Inform the workers.",
    ],
)
def test_other_shapes_are_unchanged(live_shaping, raw, monkeypatch):
    on = live_shaping._strip_markdown(raw)
    monkeypatch.setenv("REGENOLD_LIST_INLINE", "0")
    assert live_shaping._strip_markdown(raw) == on


def test_the_list_rule_is_two_sided(live_shaping, monkeypatch):
    monkeypatch.setenv("REGENOLD_LIST_INLINE", "0")
    out = live_shaping.normalise_answer_for_regenold(H45B_RAW, question="Does Article 13 cover logs?")
    assert "The other required contents are. The provider's identity and contact details." in out


# ── 2. "paragraph" is not meta-commentary ───────────────────────────────────


@pytest.mark.parametrize(
    "sentence",
    [
        "That paragraph does not apply to systems already placed on the market.",
        "The second subparagraph provides that the deployer must inform the workers.",
        "Article 6(3), first subparagraph, contains the derogation.",
        "The paragraph lacks a definition of the term.",
    ],
)
def test_paragraph_wording_is_not_meta_commentary(sentence):
    from app.integrations.regenold.models import _sentence_has_meta_leak

    assert not _sentence_has_meta_leak(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "The knowledge graph does not list this provision.",
        "The graph does not contain Article 7.",
        "Based on the provided graph, the answer is yes.",
        "Graph data shows no obligation here.",
        "As an AI, I cannot give legal advice.",
    ],
)
def test_genuine_meta_commentary_is_still_dropped(sentence):
    from app.integrations.regenold.models import _sentence_has_meta_leak

    assert _sentence_has_meta_leak(sentence)


def test_the_word_start_rule_is_two_sided(monkeypatch):
    from app.integrations.regenold.models import _sentence_has_meta_leak

    monkeypatch.setenv("REGENOLD_META_LEAK_WORD_START", "0")
    assert _sentence_has_meta_leak("That paragraph does not apply to systems already placed on the market.")


def test_a_paragraph_sentence_survives_the_normaliser(live_shaping):
    raw = (
        "Under Article 25(2) the initial provider must cooperate with the new provider. "
        "That paragraph does not apply where the initial provider has clearly specified that "
        "its system is not to be changed into a high-risk AI system."
    )
    out = live_shaping.normalise_answer_for_regenold(raw, question="When does Article 25(2) apply?")
    assert "That paragraph does not apply where" in out


# ── 3. Every curated sentence carries a provision anchor ────────────────────

#: One question per curated detector (``_is_curated_authoritative_intercept``).
CURATED_QUESTIONS: dict[str, str] = {
    "_detect_guiding_principles_inquiry": "What principles underpin the regulation?",
    "_detect_minimal_risk_inquiry": "What is minimal risk?",
    "_detect_article_6_3_inquiry": "What does the Article 6(3) exception require?",
    "_detect_research_scope_inquiry": "Does the AI Act cover models still in development?",
    "_detect_high_risk_penalty_inquiry": "What penalties apply to high-risk AI violations?",
    "_detect_emotion_classification_inquiry": "emotion recognition prohibited?",
    "_detect_systems_or_models_inquiry": "Does the EU AI Act apply to AI systems or AI models or both?",
    "_detect_annex_iii_8_admin_justice_inquiry": (
        "What are the high-risk uses of AI systems listed under 'Administration of justice and "
        "democratic processes' cited in the EU AI Act?"
    ),
    "_detect_annex_iii_8_election_inquiry": (
        "How are AI systems intended to influence the outcome of an election or referendum "
        "classified, and what exception is given for certain campaign-related tools?"
    ),
    "_detect_explainability_inquiry": "Must high-risk AI use SHAP or LIME to be trustworthy?",
    "_detect_reclassification_inquiry": "When does a deployer become a provider under Article 25(1)?",
    "_detect_ai_board_governance_inquiry": "How long is a Board member's term and is it renewable?",
    "_detect_sme_simplified_doc_inquiry": (
        "Under the EU AI Act, is there a simplified way for SMEs (including startups) to provide "
        "the technical documentation for high-risk AI systems, and who must accept it for "
        "conformity assessment?"
    ),
    "_detect_workplace_worker_notification_inquiry": (
        "Under the EU AI Act, must an employer inform affected workers and workers' "
        "representatives before putting into service or using a high-risk AI system in the "
        "workplace?"
    ),
    "_detect_art50_text_public_interest_inquiry": (
        "Does the Article 50(4) duty to disclose AI-generated text on matters of public "
        "interest have exceptions?"
    ),
    "_detect_risk_framework_inquiry": "which risk category?",
    "_detect_prohibited_practices_inquiry": "Which AI practices are banned?",
    "_detect_deepfake_criminal_exception_inquiry": (
        "Does the deep-fake disclosure duty apply when prosecuting a criminal offence?"
    ),
    "_detect_testing_data_definition_inquiry": "What is the meaning of testing data?",
    "_detect_retention_docs_inquiry": (
        "What documentation does a provider of a high-risk AI system needs to keep available for "
        "the national competent authorities, and for how long?"
    ),
    "_detect_special_data_bias_inquiry": (
        "Under Article 10(5), when may a provider of a high-risk AI system process special "
        "categories of personal data for bias detection and correction?"
    ),
    "_detect_tech_doc_certificate_inquiry": (
        "When a high-risk AI system is found to conform, what information must the Union "
        "technical documentation assessment certificate contain?"
    ),
    "_detect_hardware_techdoc_inquiry": "Does the technical documentation require hardware specs?",
    "_detect_deviation_detection_inquiry": "Is deviation detection automatically high-risk?",
    "_detect_role_difference_inquiry": "How does a provider differ from a deployer?",
    "_detect_user_information_inquiry": "How should users be informed when interacting with AI systems?",
    "_detect_gpai_transparency_exception_inquiry": (
        "Under what conditions should providers of general-purpose AI models be subject to "
        "exceptions regarding transparency-related requirements, if any? And what do those "
        "exceptions not cover?"
    ),
    "_detect_systemic_risk_scope_inquiry": (
        'Does "systemic risk" apply to AI systems or general purpose AI models or both?'
    ),
    "_detect_emergency_triage_inquiry": (
        "Under the EU AI Act, which specific AI systems are explicitly listed as high-risk because "
        "they make decisions in critical life- and health-related situations involving emergency "
        "calls and triage?"
    ),
    "_detect_health_insurance_inquiry": (
        "What does the EU AI Act require for an AI system used for risk assessment and pricing in "
        "health insurance?"
    ),
    "_detect_hospital_deployer_inquiry": (
        "A hospital deploys a high-risk AI system. What are the hospital's obligations?"
    ),
    "_detect_provider_pre_market_inquiry": "What must the provider put in place before market?",
    "_detect_robotic_surgery_inquiry": "Is a surgical robot classified as high-risk?",
}


def _curated_sentences(question: str) -> list[str]:
    from app.engines import _graph_rag_impl as engine
    from app.integrations.regenold import models

    draft = engine._deterministic_answer(question, engine.GraphContext())
    return models._split_sentences(models._strip_markdown(draft))


def test_every_curated_detector_has_a_question():
    from app.engines import _graph_rag_impl as engine

    source = inspect.getsource(engine._is_curated_authoritative_intercept)
    detectors = set(re.findall(r"(_detect_\w+_inquiry)\(question\)", source))
    assert detectors == set(CURATED_QUESTIONS), "add a question for each new curated detector"


@pytest.mark.parametrize("detector", sorted(CURATED_QUESTIONS))
def test_every_curated_sentence_carries_an_anchor(detector):
    """R447 rule 2: the soft char cap can only drop a sentence without an anchor."""
    from app.engines import _graph_rag_impl as engine

    question = CURATED_QUESTIONS[detector]
    assert getattr(engine, detector)(question), "the sample question must reach its detector"
    for sentence in _curated_sentences(question):
        assert _anchored(sentence), sentence


@pytest.mark.parametrize("detector", sorted(CURATED_QUESTIONS))
def test_no_curated_sentence_trips_the_meta_leak_filter(detector):
    from app.integrations.regenold.models import _sentence_has_meta_leak

    for sentence in _curated_sentences(CURATED_QUESTIONS[detector]):
        assert not _sentence_has_meta_leak(sentence), sentence


def test_the_minimal_risk_answer_gives_no_non_statutory_examples():
    text = " ".join(_curated_sentences(CURATED_QUESTIONS["_detect_minimal_risk_inquiry"]))
    assert "spam filters" not in text and "video games" not in text


#: Official questions whose curated answer lost a sentence to the char cap (R467).
#: Regression checks on named rows, not a measurement (AGENTS.md, R468).
CAP_DROPPED = {
    "rg_005": (
        "Does the EU AI Act explicitly requires to use explainable AI techniques such as LIME or "
        "SHAP to increase the trustworthiness of high-risk AI systems?",
        "the choice of any interpretability method is left to the provider",
    ),
    "rg_023": (
        'Does "systemic risk" apply to AI systems or general purpose AI models or both?',
        "Systemic risk applies to general-purpose AI models, not to AI systems",
    ),
    "rg_032": (
        "Is an AI system used to detect decision-making patterns or deviations for a use case "
        "listed in Annex III considered high-risk?",
        "Not automatically",
    ),
    "rg_043": (
        "Under Article 10(5) of the EU AI Act, when may a provider of a high-risk AI system "
        "process special categories of personal data for bias detection and correction, and what "
        "key safeguards/conditions must be met?",
        "in addition to, and not instead of, Regulation (EU) 2016/679",
    ),
    # Offline, a question with no provision anchor ("Is a surgical robot
    # classified as high-risk?") is refused by the scope gate before it reaches
    # the intercept, so this phrasing names the Act.
    "case_d_single_ask": (
        "Under the EU AI Act, is a surgical robot a high-risk AI system?",
        "Yes, where the surgical robot itself is required to undergo a third-party conformity "
        "assessment",
    ),
}


@pytest.mark.parametrize("row", sorted(CAP_DROPPED))
def test_the_cap_no_longer_drops_a_curated_sentence(ask, row):
    question, phrase = CAP_DROPPED[row]
    assert phrase in _norm(ask(question)["answer"])


@pytest.mark.parametrize("flag", ["REGENOLD_LIST_INLINE", "REGENOLD_META_LEAK_WORD_START"])
def test_flag_is_in_the_engine_cache_key(flag, monkeypatch):
    from app.routes import regenold as route

    monkeypatch.setenv(flag, "1")
    on = route._engine_cache_key("q", "ctx")
    monkeypatch.setenv(flag, "0")
    assert route._engine_cache_key("q", "ctx") != on
