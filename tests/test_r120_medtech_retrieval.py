"""R120 — MedTech classification-anchor retrieval fix.

A live MedTech eval found the engine surfaced the generic high-risk
obligation chain (Arts. 10/11/12) instead of the classification basis
(Art. 6 + Annex I) and the substantial-modification anchor (Art. 25) on
medical-device safety-component questions. The fix adds two closed-vocab
concepts to the R81-N entity extractor + a product-token-gated Annex I
companion injection in kb_search.

These tests pin: the concept firing, the Annex I injection, the
product-token gate (davidath-neutral by construction), word-boundary
safety, and the REGENOLD_ENTITY_BOOST disable knob.
"""
from __future__ import annotations

import pytest

from app.engines.entity_extractor import extract_entities, boosted_articles
from app.data.kb_search import top_articles_by_relevance


def _concept_ids(question: str) -> list[str]:
    return [eid for eid, _ in extract_entities(question)["concept"]]


# ───────────────────────── concept firing ─────────────────────────


@pytest.mark.parametrize("text", [
    "the host platform is a Class III medical device under the MDR",
    "CE-marked as a Class IIb device under the MDR",
    "a SaMD requiring a Class III certificate under the IVDR",
    "software as a medical device analysing biopsy slides",
    "acts as a safety component for an MDR-regulated product",
    "notified body conformity assessment under the MDR",
])
def test_medtech_classification_concept_fires(text):
    assert "medtech_classification" in _concept_ids(text)
    assert "Art. 6" in boosted_articles(text)


@pytest.mark.parametrize("text", [
    "significantly modifying its clinical performance",
    "significantly modified the model outputs",
    "a major modification to the high-risk system",
    "the model was fundamentally modified after launch",
])
def test_substantial_modification_concept_fires(text):
    assert "substantial_modification" in _concept_ids(text)
    assert "Art. 25" in boosted_articles(text)


@pytest.mark.parametrize("text", [
    "the deployer makes a substantial modification",
    "the system was substantially modified after deployment",
])
def test_literal_substantial_modification_does_not_fire(text):
    # R120 davidath-neutrality: the literal "substantial modification" /
    # "substantially modified" aliases were DROPPED because a davidath QA
    # row carrying that phrase has gold Art. 43 (not 25), so boosting Art. 25
    # there would over-cite. The concept fires only on the V4 paraphrases;
    # scope.py / the engine keyword map still map the literal to Art. 25.
    assert "substantial_modification" not in _concept_ids(text)


def test_word_boundary_mdr_no_false_positive():
    # \bmdr\b must not match inside another token.
    assert "medtech_classification" not in _concept_ids("the commander reviewed the model")


def test_non_medtech_question_no_medtech_concept():
    # Davidath-neutrality canary: a plain operator question fires neither
    # new concept (so Art. 6/Annex I/Art. 25 are not spuriously boosted).
    ids = _concept_ids("What are the obligations of importers of high-risk AI systems?")
    assert "medtech_classification" not in ids
    assert "substantial_modification" not in ids


# ──────────────────── Annex I companion injection ────────────────────


def test_annex_i_injected_on_product_question():
    q = ("We are developing an AI-driven robotic surgical assistant. The host "
         "robotic platform is a Class III medical device requiring a notified "
         "body conformity assessment under the MDR. How does the AI Act "
         "classify this AI module, and which conformity route applies?")
    top = top_articles_by_relevance(q, k=10)
    assert "Annex I" in top
    assert "Art. 6" in top


def test_annex_i_not_injected_without_product_token():
    # No MDR/IVDR/Class III/IIb/SaMD token → Annex I injection must NOT fire.
    # (Annex I may still appear if BM25 surfaces it naturally — but for a
    # plain operator question it will not.)
    q = "What are the obligations of importers of high-risk AI systems?"
    top = top_articles_by_relevance(q, k=10)
    assert "Annex I" not in top


def test_annex_i_injection_disabled_when_entity_boost_off(monkeypatch):
    monkeypatch.setenv("REGENOLD_ENTITY_BOOST", "0")
    q = ("CE-marked as a Class IIb device under the MDR. Under which AI Act "
         "risk tier does this model fall?")
    top = top_articles_by_relevance(q, k=10)
    # With the entity boost off, _ents_for_injection is None → no injection.
    assert "Annex I" not in top
