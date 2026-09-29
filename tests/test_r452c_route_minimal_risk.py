"""R452c: the minimal-risk curated answer on the real route, across phrasings and turns.

Every phrasing the R452c review found leaking a sub-point (6.3.d, 6.4, 6.6, 5.1.d,
50.x) or evicting Article 95 must ship the curated five heads: Articles 4, 5, 6,
50 and 95. Article 5 may appear as 5(1), the paragraph that holds the
prohibitions; no other sub-point may appear.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

MIN = "What are AI systems with minimal risks?"
PHRASINGS = [
    MIN,
    "Which AI applications are considered minimal risk?",
    "What are AI systems with minimal risk under the AI Act?",
    "Do minimal risk AI systems have any obligations under the AI Act?",
    "Does the EU AI Act provide for a category of minimal risk AI systems?",
    "Which systems fall under the minimal-risk tier?",
    "Are minimal-risk AI systems regulated differently from high-risk systems?",
    "What are minimal risk AI systems, such as chatbots and emotion recognition tools?",
    "What are minimal risk AI systems in the context of biometric identification?",
]


@pytest.fixture(scope="module")
def client():
    saved = {k: os.environ.get(k) for k in ("P2P_GRAPH_RAG_PROVIDER", "OPENAI_API_BASE",
                                            "REGENOLD_EXTERNAL_EMBEDDINGS")}
    os.environ.update({"P2P_GRAPH_RAG_PROVIDER": "cli", "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
                       "REGENOLD_EXTERNAL_EMBEDDINGS": "0"})
    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    yield TestClient(app)
    limiter.enabled = True
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _refs(client, messages):
    r = client.post("/api/v1/regenold/eu-ai-act/ask", json={"messages": messages})
    assert r.status_code == 200, r.text
    return r.json()["references"]


def _curated_five(refs):
    heads = {r.split(".")[0] for r in refs}
    extra = [r for r in refs if "." in r and r != "Article 5.1"]
    return heads == {"Article 4", "Article 5", "Article 6", "Article 50", "Article 95"} and not extra


@pytest.mark.parametrize("question", PHRASINGS)
def test_curated_minimal_risk_citations_hold_across_phrasings(client, question):
    refs = _refs(client, [{"role": "user", "content": question}])
    assert _curated_five(refs), refs


def test_multi_turn_uses_the_live_question(client):
    refs = _refs(client, [
        {"role": "user", "content": "What does the AI Act say about chatbots?"},
        {"role": "assistant", "content": ("Under Article 50(1), providers must ensure people are "
                                          "informed they are interacting with an AI system. Article 5 "
                                          "lists prohibited practices.")},
        {"role": "user", "content": MIN},
    ])
    assert _curated_five(refs), refs


def test_a_bare_pushback_keeps_the_curated_citations(client):
    """R452c review F1: a pushback without "Let's try again:" takes challenge recovery,
    and the deepener used to see the flattened 800-char transcript as its question."""
    first = client.post("/api/v1/regenold/eu-ai-act/ask",
                        json={"messages": [{"role": "user", "content": MIN}]})
    assert first.status_code == 200, first.text
    refs = _refs(client, [
        {"role": "user", "content": MIN},
        {"role": "assistant", "content": first.json()["answer"]},
        {"role": "user", "content": "Are you sure? That doesn't sound right."},
    ])
    assert _curated_five(refs), refs


def test_the_deepener_still_deepens_through_the_route(client):
    """Control: the call site runs (a swallowed NameError would silently stop deepening)."""
    refs = _refs(client, [{"role": "user", "content": (
        "Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer "
        "in the instructions for use? List the required categories of information.")}])
    assert "Article 13.3" in refs, refs
