"""R95-P0 — over-citation noise-anchor suppression regression tests.

The R94 fresh-200 + r94-live over-citation analysis found three phantom
broad anchors dragging the judge refs axis (0.37): Art. 6 ×29,
Art. 3 ×13, Art. 51 ×11 surfaced as NON-gold citations. R95-P0 drops
them from the candidate list when the question lacks their topic signal
AND a more-specific article survives (floor-protected, QA-only,
env-gated REGENOLD_NOISE_SUPPRESS). The transparency case also closes
R95-P1 (Art. 5 RBI demotion when Art. 50 leads a disclosure question).

These tests pin BOTH the drop behaviour AND the gold-protection gates so
a future edit that over-broadens the suppression (and tanks davidath /
the gpai / definition / classification categories) fails loudly.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest

from app.routes.regenold import _suppress_noise_anchors as suppress


# ── Phantom drops (the R94 over-citation failure shapes) ─────────────────


def test_drops_phantom_art6_on_importer_qa():
    # gold Art. 23; "high-risk AI system" bleeds Art. 6 via BM25.
    out = suppress(
        ["Article 6", "Article 23"],
        "What are the obligations of importers of high-risk AI systems?",
        set(),
    )
    assert out == ["Article 23"]


def test_drops_phantom_art6_on_deployer_qa():
    out = suppress(
        ["Article 6", "Article 26"],
        "What must deployers of high-risk AI do?",
        set(),
    )
    assert "Article 6" not in out
    assert "Article 26" in out


def test_drops_phantom_art3_on_non_definitional_qa():
    out = suppress(
        ["Article 3", "Article 13"],
        "What transparency information must providers give deployers?",
        set(),
    )
    assert out == ["Article 13"]


def test_drops_phantom_art51_on_non_gpai_qa():
    out = suppress(
        ["Article 51", "Article 26"],
        "What are deployer obligations?",
        set(),
    )
    assert out == ["Article 26"]


def test_r95_p1_drops_rbi_art5_on_transparency_question():
    # P1 transparency_disclosure → Art. 50. The chatbot/disclosure shape
    # bleeds the Art. 5 RBI prohibition; demote it so Art. 50 leads.
    out = suppress(
        ["Article 5", "Article 50"],
        "Do we have to tell users they are talking to an AI chatbot?",
        set(),
    )
    assert out == ["Article 50"]


# ── Gold-protection gates (must NOT regress davidath categories) ─────────


def test_keeps_art3_on_definitional_question():
    out = suppress(
        ["Article 3", "Article 13"],
        "What is an AI system?",
        set(),
    )
    assert "Article 3" in out


def test_keeps_art3_on_definition_of_phrasing():
    out = suppress(
        ["Article 3", "Article 50"],
        "What does 'deep fake' mean under the regulation?",
        set(),
    )
    assert "Article 3" in out


def test_keeps_art51_on_gpai_question():
    out = suppress(
        ["Article 51", "Article 53"],
        "What are the obligations for general-purpose AI models with systemic risk?",
        set(),
    )
    assert "Article 51" in out


def test_keeps_art51_on_flops_threshold_question():
    out = suppress(
        ["Article 51", "Article 55"],
        "Is a model trained on 10^25 FLOPs a systemic-risk model?",
        set(),
    )
    assert "Article 51" in out


def test_keeps_art6_on_classification_question():
    out = suppress(
        ["Article 6", "Annex III"],
        "When is an AI system considered high-risk?",
        set(),
    )
    assert "Article 6" in out


def test_keeps_art5_on_prohibition_question():
    out = suppress(
        ["Article 5", "Article 99"],
        "Is social scoring prohibited under the AI Act?",
        set(),
    )
    assert "Article 5" in out


# ── Floor + scope-anchor protections ─────────────────────────────────────


def test_floor_never_empties_when_only_broad_anchors():
    # Only broad anchors present, nothing more specific → no drop
    # (demotion is unsafe when no real topic article survives).
    out = suppress(["Article 6"], "totally unrelated", set())
    assert out == ["Article 6"]


def test_floor_only_broad_multiple():
    out = suppress(["Article 6", "Article 3"], "random text", set())
    # No more-specific article present → returns unchanged.
    assert out == ["Article 6", "Article 3"]


def test_scope_anchor_protects_art6():
    # Art. 6 is the leading scope anchor → the question IS about
    # high-risk classification → keep it.
    out = suppress(
        ["Article 6", "Article 23"],
        "obligations question",
        {"Article 6"},
    )
    assert "Article 6" in out


def test_scope_anchor_protects_art3():
    out = suppress(
        ["Article 3", "Article 13"],
        "obligations question",
        {"Article 3"},
    )
    assert "Article 3" in out


# ── Purity, idempotence, env-gate ────────────────────────────────────────


def test_does_not_mutate_input():
    original = ["Article 6", "Article 23"]
    snapshot = list(original)
    suppress(original, "What are importer obligations?", set())
    assert original == snapshot


def test_idempotent():
    q = "What are the obligations of importers of high-risk AI systems?"
    once = suppress(["Article 6", "Article 23"], q, set())
    twice = suppress(once, q, set())
    assert once == twice


def test_empty_candidates():
    assert suppress([], "anything", set()) == []


def test_env_gate_off_is_passthrough():
    with mock.patch.dict(os.environ, {"REGENOLD_NOISE_SUPPRESS": "0"}):
        out = suppress(
            ["Article 6", "Article 23"],
            "What are importer obligations?",
            set(),
        )
    assert out == ["Article 6", "Article 23"]


def test_preserves_rank_order_of_survivors():
    out = suppress(
        ["Article 26", "Article 6", "Article 13"],
        "What must deployers do?",
        set(),
    )
    assert out == ["Article 26", "Article 13"]


def test_subpoint_of_broad_anchor_also_dropped():
    # A leaf of a broad anchor (Article 6.x) is matched on its base.
    out = suppress(
        ["Article 6.2", "Article 23"],
        "What are importer obligations?",
        set(),
    )
    assert "Article 6.2" not in out
    assert "Article 23" in out


# ── Route-level integration (transparency / chatbot → Art. 50 leads) ─────


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.config import settings
    from app.main import app
    from app.rate_limit import limiter

    key = "regenold-r95-noise-test-key"
    prev = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(key)
    limiter.enabled = False
    try:
        yield TestClient(app), key
    finally:
        settings.regenold.api_key = prev
        limiter.enabled = True


def _ask(client_key, content):
    client, key = client_key
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask",
        json={"messages": [{"role": "user", "content": content}]},
        headers={"X-Regenold-Api-Key": key},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_route_chatbot_disclosure_surfaces_art50(client):
    body = _ask(
        client,
        "Do we have to tell users they are interacting with an AI chatbot?",
    )
    refs = body.get("references", [])
    assert any(r == "Article 50" or r.startswith("Article 50.") for r in refs), refs
    # The Art. 5 RBI prohibition must NOT lead a transparency question.
    if refs:
        assert not (refs[0] == "Article 5" or refs[0].startswith("Article 5."))
