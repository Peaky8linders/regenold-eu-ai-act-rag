"""Unit tests for Simplification B: Native Dual-Pass Retrieval for Multi-Turn Conversations."""
from __future__ import annotations

import pytest

from app.engines._graph_rag_impl import _deterministic_parse, ask_compliance_question
from app.engines.dual_pass_retriever import (
    build_context_retrieval_text,
    dual_pass_parse,
    extract_context_anchors_text,
    is_dual_pass_retrieval_enabled,
)
from app.integrations.regenold.models import RegenoldChatMessage
from app.models import GraphRAGRequest
from app.routes.regenold import _build_question_from_history, _rewrite_multiturn_query


def test_dual_pass_disabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGENOLD_DUAL_PASS_RETRIEVAL", raising=False)
    assert is_dual_pass_retrieval_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "TRUE", "ON"])
def test_dual_pass_enabled_by_env(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("REGENOLD_DUAL_PASS_RETRIEVAL", val)
    assert is_dual_pass_retrieval_enabled() is True


def test_extract_context_anchors_text_explicit_header() -> None:
    ctx = (
        "[Context anchors — articles: Art. 5; roles: deployer; risk tier: prohibited]\n\n"
        "Conversation so far:\n"
        "User: Is emotion recognition in workplaces prohibited?\n"
        "Assistant: Under Article 5(1)(f), it is prohibited.\n\n"
        "Latest question:\n"
        "What are the fines if an employer violates this?"
    )
    header = extract_context_anchors_text(ctx)
    assert "[Context anchors — articles: Art. 5; roles: deployer; risk tier: prohibited]" in header
    # Must NOT extract assistant text
    assert "Article 5(1)(f), it is prohibited" not in header


def test_extract_context_anchors_text_user_turn_fallback() -> None:
    ctx = (
        "Conversation so far:\n"
        "User: We make AI biometric identification systems for public spaces.\n"
        "Assistant: Under Article 5(1)(d), real-time biometric ID is prohibited with narrow exceptions under Article 5(2).\n\n"
        "Latest question:\n"
        "What are the penalties?"
    )
    header = extract_context_anchors_text(ctx)
    assert "We make AI biometric identification systems for public spaces" in header
    # Must NOT extract assistant text
    assert "narrow exceptions under Article 5(2)" not in header


def test_clean_context_includes_prior_user_topic_but_not_assistant_prose() -> None:
    turns = [
        RegenoldChatMessage(
            role="user",
            content="Is workplace emotion recognition prohibited?",
        ),
        RegenoldChatMessage(
            role="assistant",
            content="Article 86 is also relevant.",
        ),
    ]
    context = build_context_retrieval_text("", turns)
    query = dual_pass_parse(
        resolved_question="What are the fines if an employer violates this?",
        context_question="irrelevant formatted dialogue",
        context_retrieval_text=context,
        deterministic_parse_fn=_deterministic_parse,
    )

    assert query.entities[:2] == ["Art. 99", "Art. 5"]
    assert "Art. 86" not in query.entities


def test_question_history_threads_clean_prior_user_context() -> None:
    messages = [
        RegenoldChatMessage(
            role="user",
            content="Is workplace emotion recognition prohibited?",
        ),
        RegenoldChatMessage(
            role="assistant",
            content="Article 86 sets procedural rules.",
        ),
        RegenoldChatMessage(role="user", content="What are the fines if we violate this?"),
    ]
    history = _build_question_from_history(messages)

    assert "workplace emotion recognition" in (history.context_retrieval_text or "")
    assert "Article 86" not in (history.context_retrieval_text or "")


def test_dual_pass_skips_stage_zero_before_provider_initialisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_DUAL_PASS_RETRIEVAL", "1")
    monkeypatch.setattr(
        "app.llm.openai_wrapper_provider.is_groq_intent_provider_enabled",
        lambda: (_ for _ in ()).throw(AssertionError("provider selection must not run")),
    )

    assert _rewrite_multiturn_query("What are the fines?", [object()]) is None


def test_dual_pass_parse_fuses_operative_and_contextual() -> None:
    live_q = "What are the fines if an employer violates this?"
    ctx_q = (
        "[Context anchors — articles: Art. 5; roles: deployer; risk tier: prohibited]\n\n"
        "Conversation so far:\n"
        "User: Is emotion recognition in workplaces prohibited?\n"
        "Assistant: Under Article 5(1)(f), it is prohibited, subject to GDPR and Article 86.\n\n"
        "Latest question:\n"
        "What are the fines if an employer violates this?"
    )
    query = dual_pass_parse(
        resolved_question=live_q,
        context_question=ctx_q,
        deterministic_parse_fn=_deterministic_parse,
    )
    # Operative provision (Art. 99 for fines) must lead
    assert query.entities[0] == "Art. 99"
    # Context provision (Art. 5 from anchor header) must follow
    assert "Art. 5" in query.entities
    # Assistant noise (Art. 86) must NOT be present
    assert "Art. 86" not in query.entities
    # Risk context from prior turn must be preserved (prohibited maps to unacceptable)
    assert query.risk_context == "unacceptable"


def test_dual_pass_in_ask_compliance_question(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_DUAL_PASS_RETRIEVAL", "1")
    req = GraphRAGRequest(
        question=(
            "[Context anchors — articles: Art. 5; roles: deployer; risk tier: prohibited]\n\n"
            "Conversation so far:\n"
            "User: Is emotion recognition in workplaces prohibited?\n"
            "Assistant: Under Article 5(1)(f), it is prohibited, with Article 86 procedural rules.\n\n"
            "Latest question:\n"
            "What are the fines if an employer violates this?"
        ),
        resolved_question="What are the fines if an employer violates this?",
        history_turn_count=2,
    )
    resp = ask_compliance_question(req)
    # Check that Article 99 is cited
    citation_refs = [c.article_ref for c in resp.citations]
    assert any("99" in ref for ref in citation_refs)
    # Check that Article 86 (assistant bleed) is NOT in citations
    assert not any("86" in ref for ref in citation_refs)


def test_engine_uses_clean_context_metadata_for_implicit_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_DUAL_PASS_RETRIEVAL", "1")
    req = GraphRAGRequest(
        question=(
            "Conversation so far:\n"
            "User: Is workplace emotion recognition prohibited?\n"
            "Assistant: Article 86 sets procedural rules.\n\n"
            "Latest question:\n"
            "What are the fines if an employer violates this?"
        ),
        resolved_question="What are the fines if an employer violates this?",
        context_retrieval_text="User: Is workplace emotion recognition prohibited?",
        history_turn_count=2,
    )
    resp = ask_compliance_question(req)
    citation_refs = [citation.article_ref for citation in resp.citations]

    assert any("99" in ref for ref in citation_refs)
    assert any(ref.startswith("Art. 5") for ref in citation_refs)
    assert not any("86" in ref for ref in citation_refs)


def test_dual_pass_disabled_falls_back_to_single_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENOLD_DUAL_PASS_RETRIEVAL", "0")
    req = GraphRAGRequest(
        question="What are the fines for Article 5 violations under the EU AI Act?",
        resolved_question="What are the fines for Article 5 violations under the EU AI Act?",
        history_turn_count=0,
    )
    resp = ask_compliance_question(req)
    citation_refs = [c.article_ref for c in resp.citations]
    assert any("99" in ref or "5" in ref for ref in citation_refs)
