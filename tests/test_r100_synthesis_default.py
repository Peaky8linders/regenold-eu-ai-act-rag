"""R100 — synthesis-default routing + verbatim reserved for explicit quotes.

R99.2's LLM-as-Judge head-to-head vs the GraphRAG paper measured the
verbatim-default answer surface at **0.25** on answer-correctness: a raw
provision quote rarely matches the question's gold (wrong-shaped provision,
char-cap truncation), while the paper's lawyer-reviewed reference answers and
the competition correctness axis are synthesis-shaped.

R100 demotes verbatim from the default answer surface to an explicit-quote-only
mode:

* :func:`is_explicit_quote_request` — detects "exact text / verbatim / quote the
  wording of Article N" requests (scans the LIVE turn of a multi-turn prompt).
* :func:`select_answer_mode` — returns VERBATIM only for explicit-quote (or under
  the ``REGENOLD_SYNTHESIS_DEFAULT=0`` rollback for simple QA); SYNTHESIS for
  everything else (multi-turn, nuanced, AND simple factual QA).
* the route's verbatim overwrite is gated on
  :func:`app.routes.regenold._should_ship_verbatim` so a synthesis target whose
  Stage-2 did NOT land (no wrapper / low confidence / wrapper failure) ships the
  deterministic Stage-1 prose, never a raw verbatim dump.

These tests pin the router decisions, the explicit-quote detector (positive +
negative), the route helper across every flag combination, and the route-level
behaviour (default synthesis target ships deterministic prose without a wrapper;
explicit-quote ships verbatim; OOS still refuses).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines.answer_router import (
    AnswerMode,
    is_explicit_quote_request,
    select_answer_mode,
    synthesis_default_enabled,
)
from app.main import app
from app.routes.regenold import _should_ship_verbatim


# ─── is_explicit_quote_request ───────────────────────────────────────────────


class TestExplicitQuoteDetector:
    @pytest.mark.parametrize(
        "q",
        [
            "What is the exact text of Article 13?",
            "Quote Article 5 verbatim.",
            "Give me the verbatim wording of Annex IV.",
            "What does Article 13 say word for word?",
            "Show me the full text of Article 6.",
            "Provide the exact wording of Article 50.",
            "I need the literal text of Article 9.",
            "quote me the provision",
            "What is the complete text of paragraph 2?",
            "the wording of article 99 please",
        ],
    )
    def test_positive(self, q) -> None:
        assert is_explicit_quote_request(q) is True

    @pytest.mark.parametrize(
        "q",
        [
            "What does Article 13 require?",
            "What are the obligations of deployers of high-risk AI systems?",
            "What practices are prohibited by the AI Act?",
            "What is the definition of high risk?",
            "Explain Article 5.",
            "What is the exact scope of Article 2?",  # "scope" is not a quote noun
            "Which sectors are high-risk?",
            "How should users be informed when interacting with AI systems?",
            "",
            "   ",
        ],
    )
    def test_negative(self, q) -> None:
        assert is_explicit_quote_request(q) is False

    def test_scans_only_live_turn(self) -> None:
        # A prior turn mentioning "verbatim" must NOT flip a normal final turn.
        flattened = (
            "Conversation so far:\n"
            "User: Give me the verbatim text of Article 5.\n"
            "Assistant: Article 5: ...\n\n"
            "Latest question:\nWhat about deployers of high-risk systems?"
        )
        assert is_explicit_quote_request(flattened) is False

    def test_live_turn_quote_request_in_multiturn(self) -> None:
        flattened = (
            "Conversation so far:\n"
            "User: What does Article 13 require?\n"
            "Assistant: Article 13 sets transparency obligations.\n\n"
            "Latest question:\nNow give me the exact text of Article 13."
        )
        assert is_explicit_quote_request(flattened) is True


# ─── select_answer_mode (R100 default ON) ────────────────────────────────────


class TestRouterSynthesisDefault:
    @pytest.fixture(autouse=True)
    def _default_on(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_SYNTHESIS_DEFAULT", raising=False)
        yield

    def test_env_default_on(self) -> None:
        assert synthesis_default_enabled() is True

    def test_simple_qa_is_synthesis_by_default(self) -> None:
        d = select_answer_mode("What does Article 13 require?", history_turn_count=1)
        assert d.mode is AnswerMode.SYNTHESIS
        assert d.reason == "synthesis_default"

    def test_definitional_is_synthesis_by_default(self) -> None:
        d = select_answer_mode("What is the definition of high risk?")
        assert d.mode is AnswerMode.SYNTHESIS

    def test_explicit_quote_is_verbatim(self) -> None:
        d = select_answer_mode("What is the exact text of Article 13?")
        assert d.mode is AnswerMode.VERBATIM
        assert d.reason == "explicit_quote"

    def test_explicit_quote_wins_over_multiturn(self) -> None:
        flattened = (
            "Conversation so far:\nUser: x\nAssistant: y\n\n"
            "Latest question:\nQuote Article 5 verbatim."
        )
        d = select_answer_mode(flattened, history_turn_count=2)
        assert d.mode is AnswerMode.VERBATIM
        assert d.reason == "explicit_quote"

    def test_multiturn_still_synthesis(self) -> None:
        flattened = (
            "Conversation so far:\nUser: x\nAssistant: y\n\n"
            "Latest question:\nWhat about deployers?"
        )
        assert select_answer_mode(flattened, history_turn_count=2).reason == "multi_turn"


class TestRouterSynthesisDefaultOff:
    @pytest.fixture(autouse=True)
    def _off(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_SYNTHESIS_DEFAULT", "0")
        yield

    def test_env_off(self) -> None:
        assert synthesis_default_enabled() is False

    def test_simple_qa_is_verbatim(self) -> None:
        d = select_answer_mode("What does Article 13 require?")
        assert d.mode is AnswerMode.VERBATIM
        assert d.reason == "simple_qa"

    def test_explicit_quote_still_verbatim(self) -> None:
        assert select_answer_mode(
            "What is the exact text of Article 13?"
        ).mode is AnswerMode.VERBATIM


# ─── _should_ship_verbatim route helper (all flag combos) ────────────────────


class TestShouldShipVerbatim:
    def test_default_simple_qa_does_not_ship_verbatim(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_SYNTHESIS_DEFAULT", raising=False)
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        assert _should_ship_verbatim("What does Article 13 require?", 1) is False

    def test_explicit_quote_ships_verbatim(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        assert _should_ship_verbatim("What is the exact text of Article 13?", 1) is True

    def test_synthesis_default_off_ships_verbatim(self, monkeypatch) -> None:
        monkeypatch.setenv("REGENOLD_SYNTHESIS_DEFAULT", "0")
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        assert _should_ship_verbatim("What does Article 13 require?", 1) is True

    def test_router_off_ships_verbatim(self, monkeypatch) -> None:
        # R96 rollback — verbatim-only regardless of question shape.
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "0")
        assert _should_ship_verbatim("What does Article 13 require?", 1) is True

    def test_multiturn_does_not_ship_verbatim(self, monkeypatch) -> None:
        monkeypatch.delenv("REGENOLD_SYNTHESIS_DEFAULT", raising=False)
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        flattened = (
            "Conversation so far:\nUser: x\nAssistant: y\n\n"
            "Latest question:\nWhat about deployers?"
        )
        assert _should_ship_verbatim(flattened, 2) is False


# ─── Route-level behaviour (no wrapper → deterministic, not verbatim) ────────


def _client() -> TestClient:
    settings.regenold.api_key = SecretStr("regenold-test-key")
    return TestClient(app)


class TestRouteSynthesisDefault:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        # Production answer surface, no wrapper provider wired → Stage-2 can't
        # land → the route falls back to the deterministic Stage-1 answer.
        monkeypatch.setenv("REGENOLD_VERBATIM_ANSWER", "1")
        monkeypatch.setenv("REGENOLD_ANSWER_ROUTER", "1")
        monkeypatch.delenv("REGENOLD_SYNTHESIS_DEFAULT", raising=False)
        monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        yield

    def test_simple_qa_ships_deterministic_not_verbatim(self) -> None:
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": "What does Article 13 require?"}],
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        # R100 default: simple QA is a synthesis target. With no wrapper, the
        # deterministic Stage-1 prose ships — NOT the verbatim provision dump.
        assert body.get("retrieval_path") != "verbatim_exact_text", body.get("retrieval_path")
        assert body.get("answer")
        assert body.get("references")

    def test_explicit_quote_ships_verbatim(self) -> None:
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask?include_telemetry=true",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": "Give me the exact text of Article 13."}],
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body.get("retrieval_path") == "verbatim_exact_text", body.get("retrieval_path")

    def test_out_of_scope_still_refused(self) -> None:
        c = _client()
        r = c.post(
            "/api/v1/regenold/eu-ai-act/ask",
            headers={"X-Regenold-Api-Key": "regenold-test-key"},
            json=[{"role": "user", "content": "What's the best Italian restaurant in Rome?"}],
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        # Refusal copy — no AI Act references surfaced.
        assert not body.get("references")
