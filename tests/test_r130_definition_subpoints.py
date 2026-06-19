"""R130 — Article 3 definitional sub-point reference emission.

The Regenold competition rules PDF allows references "optionally [with] a
sub-point, after a dot symbol" and gives the worked example
``"references": ["Annex IV.2", "Article 3.1"]`` — i.e. a definitional
question about a term defined in Article 3 should cite the SPECIFIC
sub-point (``Article 3.1`` for "AI system"), not the bare ``Article 3``.

Pre-R130 the route hard-promoted bare ``Article 3`` for every definitional
question (route R103 attribution block + the engine's Art. 3 anchor never
carried the point number), so "What is an AI system?" shipped
``["Article 3"]`` instead of ``["Article 3.1"]``.

These are davidath-score-neutral by construction (the bench collapses
references to article HEADS via ``article_heads`` — ``Article 3.1`` and
``Article 3`` share the head ``Article 3``); the lift is purely on the
Regenold sub-point gold.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr


# ── Unit: the registry-driven resolver ───────────────────────────────────


def test_resolver_ai_system_to_art_3_1():
    from app.data.definitions import definition_citation_for_question

    assert (
        definition_citation_for_question("What is the definition of an AI system?")
        == "Art. 3.1"
    )


def test_resolver_provider_to_art_3_3():
    from app.data.definitions import definition_citation_for_question

    assert (
        definition_citation_for_question("Who is a provider under the EU AI Act?")
        == "Art. 3.3"
    )


def test_resolver_deployer_to_art_3_4():
    from app.data.definitions import definition_citation_for_question

    assert (
        definition_citation_for_question("What does deployer mean in the AI Act?")
        == "Art. 3.4"
    )


def test_resolver_gpai_model_to_art_3_63():
    from app.data.definitions import definition_citation_for_question

    # The most-specific multi-word term must win over any nested shorter
    # alias ("model" / "ai").
    assert (
        definition_citation_for_question(
            "What is a general-purpose AI model under the Act?"
        )
        == "Art. 3.63"
    )


def test_resolver_returns_none_when_no_defined_term():
    from app.data.definitions import definition_citation_for_question

    # A question that names no Article-3 defined term must NOT resolve to a
    # spurious sub-point.
    assert definition_citation_for_question(
        "What are the penalties for non-compliance?"
    ) is None
    assert definition_citation_for_question("") is None


def test_resolver_word_boundary_no_substring_false_positive():
    from app.data.definitions import definition_citation_for_question

    # "ai" is NOT a defined-term alias; it must not match inside "gpai" /
    # "maintain" etc. The GPAI-model term resolves on its own multi-word
    # alias, not on a bare "ai" substring.
    cit = definition_citation_for_question("Explain the GPAI model concept.")
    assert cit in (None, "Art. 3.63")  # never Art. 3.1 via an "ai" substring


def test_every_resolved_citation_is_known_article():
    from app.data.definitions import _DEFINITIONS, definition_citation_for_question
    from app.integrations.regenold.models import reference_from_article_ref

    # Each defined term, asked plainly, must resolve to a wire-valid ref.
    for defn in _DEFINITIONS:
        cit = definition_citation_for_question(f"What is a {defn.term}?")
        if cit is None:
            continue
        wire = reference_from_article_ref(cit)
        assert wire is not None, f"{defn.term} -> {cit} did not validate"
        assert wire.startswith("Article 3."), f"{defn.term} -> {wire}"


# ── Route end-to-end (deterministic provider=cli path) ───────────────────


@pytest.fixture()
def client():
    os.environ["REGENOLD_SKIP_STARTUP_LOG"] = "1"
    from app.config import settings
    from app.main import app

    settings.regenold.api_key = SecretStr("r130-test-key")
    with TestClient(app) as c:
        yield c


def _ask(client: TestClient, question: str) -> list[str]:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        headers={"X-Regenold-Api-Key": "r130-test-key"},
        json={"messages": [{"role": "user", "content": question}]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["references"]


def test_route_ai_system_definition_emits_article_3_1(client):
    refs = _ask(client, "What is the definition of an AI system under the EU AI Act?")
    # The PDF worked example: gold is Article 3.1.
    assert "Article 3.1" in refs, refs
    # And the bare parent must not also be shipped (minimal-set rubric).
    assert "Article 3" not in refs, refs


def test_route_provider_definition_emits_article_3_3(client):
    refs = _ask(client, "Who is considered a provider under the EU AI Act?")
    assert "Article 3.3" in refs, refs


def test_route_non_definitional_keeps_no_spurious_art3_subpoint(client):
    # An obligations question must not get an Article 3.x definition subpoint.
    refs = _ask(
        client,
        "What are the obligations of providers of high-risk AI systems?",
    )
    assert not any(r.startswith("Article 3.") for r in refs), refs
