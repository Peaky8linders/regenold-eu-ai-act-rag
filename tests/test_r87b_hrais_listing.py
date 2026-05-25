"""R87-B — HRAIS-listing dynamic budget (P1) + Art. 6 seed injection (P2).

P1 — lift the ref budget 10 → 22 when the question explicitly asks for
the full Article list of a high-risk system's obligations. The first
live measurement (r86-live-postship) had every multi-turn HRAIS row
hitting the 10-ref cap against gold cardinality 20-35; this targets the
multi_turn Ref Loose 0.371 floor.

P2 — defensive Art. 6 seed when the question is HRAIS-listing-shaped
but the engine missed Art. 6 entirely (the chain expander has nothing
to walk without the hub). Strictly additive — never injects when
Art. 6 / Art. 6.* already a candidate.

Gating discipline:
* P1 + P2 BOTH require (listing trigger phrase) AND (Art. 6 anchor OR
  literal "high-risk"). Davidath scenarios (gold ~10 refs, no listing
  intent phrasing) are byte-identical.
* P1 env-gated REGENOLD_HRAIS_LISTING_BUDGET (default ON).
* P2 env-gated REGENOLD_HRAIS_EXPAND (default ON).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.routes.regenold import _engine_cache_key


_TEST_KEY = "regenold-r87b-test-key"


@pytest.fixture
def client(monkeypatch):
    """TestClient with a configured Regenold API key + default env."""
    settings.regenold.api_key = SecretStr(_TEST_KEY)
    # Default ON for both R87-B knobs; tests that want OFF override.
    monkeypatch.setenv("REGENOLD_HRAIS_LISTING_BUDGET", "1")
    monkeypatch.setenv("REGENOLD_HRAIS_EXPAND", "1")
    yield TestClient(app)
    settings.regenold.api_key = None


def _ask(client, content: str, with_reasoning: bool = True) -> dict:
    url = "/api/v1/regenold/eu-ai-act/ask"
    if with_reasoning:
        url += "?include_reasoning=true"
    r = client.post(
        url,
        json={"messages": [{"role": "user", "content": content}]},
        headers={"X-Regenold-Api-Key": _TEST_KEY},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _notes(response: dict) -> list[str]:
    """Pull the reasoning notes list from a response (empty if absent)."""
    reas = json.loads(response.get("reasoning") or "{}")
    return reas.get("notes") or []


# ─── P1: HRAIS-listing budget lift ────────────────────────────────────────


def test_p1_listing_intent_with_hrais_lifts_budget(client) -> None:
    """A scenario that asks 'which Articles set them out' + names high-risk
    should fire the budget lift and ship more than 10 refs."""
    resp = _ask(
        client,
        "We are a provider of a high-risk AI system for utility planning. "
        "Which Articles of the EU AI Act set them out?",
    )
    assert any(
        n.startswith("hrais_listing_budget_lift") for n in _notes(resp)
    ), f"expected budget-lift note in {_notes(resp)}"
    # Pred refs should exceed the standard 10-ref scenario cap
    assert len(resp["references"]) > 10, (
        f"expected >10 refs after budget lift; got "
        f"{len(resp['references'])}: {resp['references']}"
    )


def test_p1_listing_intent_without_hrais_does_not_fire(client) -> None:
    """'Which Articles cover deepfakes?' is a listing intent but doesn't
    mention high-risk / Art. 6 — must NOT fire the lift."""
    resp = _ask(client, "Which Articles cover deepfake disclosure?")
    # Should NOT have the lift note
    assert not any(
        n.startswith("hrais_listing_budget_lift") for n in _notes(resp)
    ), f"unexpected budget-lift note: {_notes(resp)}"


def test_p1_hrais_anchor_without_listing_does_not_fire(client) -> None:
    """A high-risk question that doesn't ask for a list ('what is the
    risk classification of a high-risk system?') must NOT fire the lift."""
    resp = _ask(
        client,
        "We are a provider of a high-risk AI system. What is the risk "
        "classification of this system?",
    )
    assert not any(
        n.startswith("hrais_listing_budget_lift") for n in _notes(resp)
    )


def test_p1_disabled_via_env(client, monkeypatch) -> None:
    """REGENOLD_HRAIS_LISTING_BUDGET=0 → lift never fires, stays at 10."""
    monkeypatch.setenv("REGENOLD_HRAIS_LISTING_BUDGET", "0")
    resp = _ask(
        client,
        "We are a provider of a high-risk AI system for utility planning. "
        "Which Articles of the EU AI Act set them out?",
    )
    assert not any(
        n.startswith("hrais_listing_budget_lift") for n in _notes(resp)
    )
    # Should respect the standard 10-ref scenario cap
    assert len(resp["references"]) <= 10


def test_p1_env_var_in_cache_key(monkeypatch) -> None:
    """Flipping REGENOLD_HRAIS_LISTING_BUDGET must produce a distinct cache
    key (R30/R56/R79 cache-poisoning doctrine — any input that flips
    pre-engine behaviour must be folded into the key)."""
    monkeypatch.setenv("REGENOLD_HRAIS_LISTING_BUDGET", "1")
    key_on = _engine_cache_key("any q", None)
    monkeypatch.setenv("REGENOLD_HRAIS_LISTING_BUDGET", "0")
    key_off = _engine_cache_key("any q", None)
    assert key_on != key_off


# ─── P2: Art. 6 seed injection ─────────────────────────────────────────────


def test_p2_seeds_art6_when_missing_on_listing_question(client) -> None:
    """When the question is HRAIS-listing-shaped and Art. 6 isn't in
    candidates, seed it so the downstream expander has a hub.

    Note: the davidath/TestClient retrieval path normally surfaces Art. 6
    for any 'high-risk' question, so this seed path mostly fires when
    BM25 anchored on transparency/GPAI keywords instead. We test the
    structural invariant: when the lift fires, Art. 6 (or a sub-point)
    MUST be present in the final references."""
    resp = _ask(
        client,
        "We are a provider of a high-risk AI system for utility planning. "
        "Which Articles of the EU AI Act set them out?",
    )
    if any(n.startswith("hrais_listing_budget_lift") for n in _notes(resp)):
        refs = resp["references"]
        has_art6 = any(
            r == "Article 6" or r.startswith("Article 6.") for r in refs
        )
        assert has_art6, (
            f"Art. 6 must be present after HRAIS seed injection; "
            f"got {refs}"
        )


def test_p2_env_var_in_cache_key(monkeypatch) -> None:
    """Flipping REGENOLD_HRAIS_EXPAND must produce a distinct cache key."""
    monkeypatch.setenv("REGENOLD_HRAIS_EXPAND", "1")
    key_on = _engine_cache_key("any q", None)
    monkeypatch.setenv("REGENOLD_HRAIS_EXPAND", "0")
    key_off = _engine_cache_key("any q", None)
    assert key_on != key_off


# ─── compound behaviour: P1 + P2 together pull the Section-2 chain ────────


def test_p1_p2_pull_hrais_section2_articles(client) -> None:
    """The whole point: when both fire, the references list contains a
    representative slice of the HRAIS Section-2 chain (Arts. 9-15)."""
    resp = _ask(
        client,
        "We are a provider of a high-risk AI system for utility planning. "
        "Which Articles of the EU AI Act set them out?",
    )
    refs = set(resp["references"])
    # At least 3 of the load-bearing Section-2 articles should appear
    section_2_chain = {
        "Article 9",   # RMS
        "Article 10",  # Data governance
        "Article 11",  # Technical docs
        "Article 13",  # Transparency
        "Article 14",  # Human oversight
        "Article 15",  # Accuracy
        "Article 16",  # Provider obligations
    }
    overlap = refs & section_2_chain
    assert len(overlap) >= 3, (
        f"expected ≥3 Section-2 articles after R87-B fires; "
        f"got {sorted(overlap)} from {sorted(refs)}"
    )
