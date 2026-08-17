"""R273 + R364 — wrong-framework scope routing tests.

R273 pinned that wrong-framework queries must NOT be routed to the
ungrounded general assistant (live: "Article 52a" on a VLOP question).

R364 extends the operator directive: adjacent-EU-instrument questions
(DSA / GDPR / DMA / PLD / NIS2 / CRA) are answered by the GROUNDED RAG
engine on their EU AI Act side — never the general assistant, and no
longer refused. Only non-EU laws (HIPAA / CCPA / SOX) keep the
OTHER_REGULATION refusal.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.config import settings
from app.integrations.regenold.scope import (
    ScopeReason,
    classify_scope,
)


# ── unit: classify_scope → NEAR_OOS / OTHER_REGULATION ──────────────────


@pytest.mark.parametrize(
    "question,expected_framework",
    [
        # DSA / VLOP → answered on the AI Act side, framework preserved
        (
            "What are the transparency obligations for Very Large Online Platforms?",
            "Digital Services Act",
        ),
        # PLD → answered on the AI Act side, framework preserved
        (
            "If AI causes property damage to a consumer, what is the AI-Act liability?",
            "Product Liability Directive",
        ),
        # NIS2 → answered on the AI Act side, framework preserved
        (
            "What are the NIS2 cybersecurity obligations for essential entities?",
            "NIS2 Directive",
        ),
    ],
    ids=["dsa_vlop", "pld_liability", "nis2_essential"],
)
def test_near_oos_question_answered_on_ai_act_side(
    question: str,
    expected_framework: str,
) -> None:
    """R364 — adjacent-EU-framework questions are IN-SCOPE: answered on
    their EU AI Act side, framework name preserved for the trace."""
    v = classify_scope(question)
    assert v.in_scope is True, f"Expected in-scope, got out-of-scope for: {question}"
    assert v.reason == ScopeReason.IN_SCOPE
    assert v.near_oos_framework == expected_framework


def test_gdpr_question_answered_on_ai_act_side() -> None:
    """R364 — GDPR is an EU instrument; answered on its EU AI Act side."""
    v = classify_scope("What does GDPR Article 17 say about the right to be forgotten?")
    assert v.in_scope is True
    assert v.reason == ScopeReason.IN_SCOPE


def test_non_eu_hipaa_still_other_regulation() -> None:
    """Non-EU law (HIPAA) keeps the refusal — answering it from the EU
    AI Act corpus would fabricate a foreign-law answer."""
    v = classify_scope("How does HIPAA apply to AI-powered medical devices?")
    assert v.in_scope is False
    assert v.reason == ScopeReason.OTHER_REGULATION


# ── unit: _general_answer_reason_ok gate ─────────────────────────────────


def test_general_answer_reason_ok_blocks_near_oos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEAR_OOS must be blocked from the general assistant by default."""
    monkeypatch.delenv("REGENOLD_WRONG_FRAMEWORK_GENERAL", raising=False)
    import app.routes.regenold as route_mod

    assert route_mod._general_answer_reason_ok(ScopeReason.NEAR_OOS) is False


def test_general_answer_reason_ok_blocks_other_regulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OTHER_REGULATION must be blocked from the general assistant by default."""
    monkeypatch.delenv("REGENOLD_WRONG_FRAMEWORK_GENERAL", raising=False)
    import app.routes.regenold as route_mod

    assert route_mod._general_answer_reason_ok(ScopeReason.OTHER_REGULATION) is False


def test_general_answer_reason_ok_allows_conversational() -> None:
    """CONVERSATIONAL (benign off-topic) IS allowed to the general assistant."""
    import app.routes.regenold as route_mod

    assert route_mod._general_answer_reason_ok(ScopeReason.CONVERSATIONAL) is True


def test_override_env_restores_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGENOLD_WRONG_FRAMEWORK_GENERAL=1 re-enables the pre-R273 routing."""
    monkeypatch.setenv("REGENOLD_WRONG_FRAMEWORK_GENERAL", "1")
    import app.routes.regenold as route_mod

    assert route_mod._general_answer_reason_ok(ScopeReason.NEAR_OOS) is True
    assert route_mod._general_answer_reason_ok(ScopeReason.OTHER_REGULATION) is True


# ── route-level: wrong-framework gets branded refusal, not general_assistant ─


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REGENOLD_GRAPH_BACKEND", "embedded")
    monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
    # Ensure general-answer is ON so the test proves the routing block works
    # (if the gate weren't blocking, the general LLM would answer instead).
    monkeypatch.setenv("REGENOLD_GENERAL_ANSWER", "1")
    monkeypatch.delenv("REGENOLD_WRONG_FRAMEWORK_GENERAL", raising=False)
    settings.regenold.api_key = SecretStr("test-key")
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def _ask(client, question: str) -> dict:
    resp = client.post(
        "/api/v1/regenold/eu-ai-act/ask?include_reasoning=true",
        json=[{"role": "user", "content": question}],
        headers={"X-Regenold-Api-Key": "test-key"},
    )
    assert resp.status_code == 200
    return resp.json()


def test_route_dsa_vlop_answered_by_rag(client) -> None:
    """R364 — a DSA/VLOP question is answered by the grounded RAG engine,
    NOT the ungrounded general assistant (which hallucinated "Article 52a")."""
    body = _ask(client, "What are the transparency obligations for Very Large Online Platforms?")
    answer = body.get("answer", "")
    assert answer, "DSA/VLOP question must be answered, not refused"
    # Must NOT have been routed to the general assistant or refused.
    reasoning = body.get("reasoning", "")
    rpath = ""
    if isinstance(reasoning, str):
        try:
            rpath = json.loads(reasoning).get("retrieval_path", "")
        except (json.JSONDecodeError, TypeError):
            pass
    assert rpath not in ("general_assistant", "scope_refusal"), (
        f"DSA/VLOP query routed to {rpath!r} — R364 answer-don't-refuse directive failed"
    )


def test_route_gdpr_answered_by_rag(client) -> None:
    """R364 — a GDPR question is answered on its EU AI Act side."""
    body = _ask(client, "What does GDPR Article 17 say about the right to be forgotten?")
    answer = body.get("answer", "")
    assert answer, "GDPR question must be answered, not refused"
    # Must NOT have been routed to the general assistant or refused.
    reasoning = body.get("reasoning", "")
    rpath = ""
    if isinstance(reasoning, str):
        try:
            rpath = json.loads(reasoning).get("retrieval_path", "")
        except (json.JSONDecodeError, TypeError):
            pass
    assert rpath not in ("general_assistant", "scope_refusal"), (
        f"GDPR query routed to {rpath!r} — R364 answer-don't-refuse directive failed"
    )
