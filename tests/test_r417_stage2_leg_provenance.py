"""R417 — Stage-2 leg provenance, and the degenerate-completion retry.

Two defects of one class: a degraded answer that silently became the durable one.

1. **A *successful* Bedrock fallback left ``stage2_call_failed`` False.** The
   route's cache-poisoning guard (R28) keys on that flag, so a fallback-served
   polish was indistinguishable from a wrapper-served one and was CACHED. On
   rg_010 a quota-flap window produced one Bedrock generation whose replay
   returned in 0.1-0.2 s (the route's in-process LRU) — three production
   "observations" that were one answer, none of them the wrapper's.
   ``graph_stats["stage2_served_by"]`` now names the leg and the route refuses
   to cache anything but the primary leg (or no attempt at all).

2. **The wrapper intermittently relays an interim/empty Claude-CLI assistant
   message as an HTTP-200 completion** (measured live: ``completion_tokens=1``,
   a 1-2 char body). The structural guard read that as a model truncation, so
   every blip paid a full Bedrock downgrade — and, per (1), kept it. The
   primary leg now retries ONCE on the identical request before the downgrade.

Every assertion here reads a shipped return value, a transport counter, or the
route's own LRU — never the shape of the code. That is the R329/R331
discipline: a lever that reads correctly in a diff and makes zero calls is
exactly what these tests exist to catch, and the retry tests are two-sided (a
healthy completion must NOT be re-dialled).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.engines._graph_rag_impl import (
    _STAGE2_LEG2_SERVED,
    _is_degenerate_completion,
    _mark_stage2_served_by,
    _openai_wrapper_complete_for_graph_rag,
    _stage2_degenerate_retry_enabled,
)
from app.engines.graph_rag.models import GraphContext
from app.llm import stage2_policy as pol
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse
from app.main import app


@pytest.fixture(autouse=True)
def _clean_counters():
    pol.reset_transport_stats()
    _STAGE2_LEG2_SERVED.set(False)
    yield
    pol.reset_transport_stats()
    _STAGE2_LEG2_SERVED.set(False)


@pytest.fixture(autouse=True)
def _arm_bedrock(monkeypatch: pytest.MonkeyPatch):
    """Credentials present, so "leg 2 was skipped" is never a missing-key artefact."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


# ── the predicate ───────────────────────────────────────────────────────────


class TestTheDegenerateCompletionPredicate:
    @pytest.mark.parametrize(
        ("text", "tokens"),
        [
            ("", 0),
            (None, 0),
            ("   \n\t ", 0),
            ("I", 1),
            ("Here", 1),
            ("Sure", 2),
            (".", 1),
            # The observed live shape: a body that is only an interim message.
            ("I'll", 2),
        ],
        ids=[
            "empty", "none", "whitespace", "one_char", "one_token_word",
            "two_tokens", "punctuation", "interim",
        ],
    )
    def test_degenerate_shapes_are_recognised(self, text, tokens) -> None:
        assert _is_degenerate_completion(text, tokens) is True

    @pytest.mark.parametrize(
        ("text", "tokens"),
        [
            ("Article 50 requires disclosure of the AI interaction.", 9),
            ("Article 6(2) applies, so Annex III documentation is owed.", 11),
            ("Article 14 requires human oversight: stop or override.", 8),
        ],
        ids=["article_50", "article_6_2", "article_14"],
    )
    def test_a_real_answer_is_never_degenerate(self, text, tokens) -> None:
        assert _is_degenerate_completion(text, tokens) is False

    def test_the_retry_gate_defaults_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_STAGE2_DEGENERATE_RETRY", raising=False)
        assert _stage2_degenerate_retry_enabled() is True
        for off in ("0", "off", "false", "no"):
            monkeypatch.setenv("REGENOLD_STAGE2_DEGENERATE_RETRY", off)
            assert _stage2_degenerate_retry_enabled() is False


# ── the primary leg retries a degenerate completion ─────────────────────────


class _ScriptedWrapper:
    """A tunnel whose ``complete`` replays a fixed script, counting calls."""

    def __init__(self, responses: list[OpenAIWrapperResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, req):
        self.calls += 1
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def _degenerate() -> OpenAIWrapperResponse:
    """The measured artefact: one token, a 1-char body, ``finish_reason=stop``."""
    return OpenAIWrapperResponse(
        text="I", model="claude-opus-5", error=None,
        finish_reason="stop", completion_tokens=1, elapsed_ms=1,
    )


def _good(text: str = "Article 50 requires disclosure of the AI interaction."):
    return OpenAIWrapperResponse(
        text=text, model="claude-opus-5", error=None,
        finish_reason="stop", completion_tokens=12, elapsed_ms=1,
    )


def _bedrock_recorder(calls: list[str], answer: str | None):
    def _fake(**kwargs):
        calls.append(kwargs.get("stage_name") or "?")
        return answer

    return _fake


class TestAPrimaryDegenerateCompletionIsRetried:
    def test_the_retry_serves_the_second_answer_and_never_dials_leg_2(self) -> None:
        wrapper = _ScriptedWrapper([_degenerate(), _good()])
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "must not be used"),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == _good().text, "the second (real) answer must ship"
        assert wrapper.calls == 2, "the degenerate completion must be retried once"
        stats = pol.transport_stats()
        assert stats["primary_ok"] == 1, f"the retried call DID serve: {stats}"
        assert stats["primary_failed"] == 0, (
            f"a successful retry must not be counted as a primary failure: {stats}"
        )
        assert stats["fallback_attempts"] == 0 and bedrock == [], (
            "a retryable blip must not cost a Bedrock downgrade"
        )
        assert _STAGE2_LEG2_SERVED.get() is False, (
            "a retry-served answer was mislabelled as fallback-served"
        )

    def test_a_healthy_completion_is_never_redialled(self) -> None:
        """The other side: the retry must not fire on a real answer."""
        wrapper = _ScriptedWrapper([_good()])
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "must not be used"),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert out == _good().text
        assert wrapper.calls == 1, "a healthy completion must be dialled exactly once"
        assert bedrock == []

    def test_a_persisted_degeneracy_reaches_bedrock_and_names_itself(self) -> None:
        """Both calls degenerate ⇒ leg 2 serves, with the honest reason + counters."""
        wrapper = _ScriptedWrapper([_degenerate(), _degenerate()])
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(
                    bedrock, "Article 14 requires human oversight."
                ),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert wrapper.calls == 2, "the degenerate completion must be retried once"
        assert out == "Article 14 requires human oversight."
        stats = pol.transport_stats()
        assert stats["primary_failed"] == 1, f"the primary did fail: {stats}"
        assert (
            stats["primary_attempts"] == stats["primary_ok"] + stats["primary_failed"]
        ), f"the one retry must not unbalance /healthz/llm: {stats}"
        assert stats["fallback_attempts"] == 1 and stats["fallback_ok"] == 1
        assert bedrock == ["Stage 2 (Polishing)"], "leg 2 dialled exactly once"
        assert _STAGE2_LEG2_SERVED.get() is True, (
            "a Bedrock-served answer must be marked fallback-served, or the route "
            "will cache it (the rg_010 replay)"
        )

    def test_with_no_usable_answer_the_failure_is_raised_not_shipped(self) -> None:
        """Fail-soft is the caller's job; a 1-char body must never be returned."""
        wrapper = _ScriptedWrapper([_degenerate(), _degenerate()])
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.llm.bedrock_client.is_bedrock_provider_enabled",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="degenerate completion"),
        ):
            _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )
        assert wrapper.calls == 2

    def test_the_env_gate_restores_the_pre_r417_single_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``REGENOLD_STAGE2_DEGENERATE_RETRY=0`` ⇒ straight to the Bedrock leg."""
        monkeypatch.setenv("REGENOLD_STAGE2_DEGENERATE_RETRY", "0")
        wrapper = _ScriptedWrapper([_degenerate(), _good()])
        bedrock: list[str] = []
        with (
            patch(
                "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
                return_value=wrapper,
            ),
            patch(
                "app.engines._graph_rag_impl._bedrock_complete_for_graph_rag",
                side_effect=_bedrock_recorder(bedrock, "Article 50 requires disclosure."),
            ),
        ):
            out = _openai_wrapper_complete_for_graph_rag(
                system="s", user="u", max_tokens=256, temperature=0.0,
                stage_name="Stage 2 (Polishing)",
            )

        assert wrapper.calls == 1, "the gate OFF must not retry"
        assert out == "Article 50 requires disclosure."
        assert len(bedrock) == 1


# ── the serving-leg marker ──────────────────────────────────────────────────


class TestTheServingLegMarker:
    def test_a_fallback_mark_cannot_be_overwritten_by_primary(self) -> None:
        """A Bedrock body completed on the primary tail is still a Bedrock body."""
        ctx = GraphContext()
        _mark_stage2_served_by(ctx, "fallback")
        _mark_stage2_served_by(ctx, "primary")
        assert ctx.stage2_served_by == "fallback"

    def test_deterministic_always_wins(self) -> None:
        ctx = GraphContext()
        _mark_stage2_served_by(ctx, "fallback")
        _mark_stage2_served_by(ctx, "deterministic")
        assert ctx.stage2_served_by == "deterministic"

    def test_primary_is_recorded_when_nothing_else_has_served(self) -> None:
        ctx = GraphContext()
        assert ctx.stage2_served_by == "", "the default must mean 'not attempted'"
        _mark_stage2_served_by(ctx, "primary")
        assert ctx.stage2_served_by == "primary"

    def test_a_none_context_is_a_no_op(self) -> None:
        _mark_stage2_served_by(None, "fallback")  # must not raise


# ── the route refuses to cache a degraded serve ─────────────────────────────


def _headers() -> dict[str, str]:
    return {"X-Regenold-Api-Key": "regenold-test-key"}


def _response(*, served_by: str):
    from app.models import CitationNode, GraphRAGResponse  # noqa: PLC0415

    return GraphRAGResponse(
        answer=(
            "Article 13 requires high-risk AI providers to design transparency "
            "mechanisms so deployers can interpret outputs."
        ),
        citations=[
            CitationNode(
                node_type="Article",
                node_id="art-13",
                text="Transparency obligations.",
                article_ref="Art. 13",
            ),
        ],
        confidence=0.7,
        graph_stats={
            "nodes_traversed": 2,
            "stage2_call_failed": False,
            "stage2_landed": served_by in ("primary", "fallback"),
            "stage2_served_by": served_by,
        },
    )


@pytest.fixture
def _partner_key_and_clean_cache():
    settings.regenold.api_key = SecretStr("regenold-test-key")
    from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415

    with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
        _ENGINE_CACHE._data.clear()  # type: ignore[attr-defined]
    yield
    with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
        _ENGINE_CACHE._data.clear()  # type: ignore[attr-defined]


class TestTheRouteCachesOnlyAPrimaryServedAnswer:
    @pytest.mark.parametrize(
        "served_by", ["", "primary"], ids=["not_attempted", "primary"]
    )
    def test_a_primary_or_unattempted_serve_is_cached(
        self, served_by: str, _partner_key_and_clean_cache
    ) -> None:
        from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415

        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=_response(served_by=served_by),
        ):
            r = TestClient(app).post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=[{"role": "user", "content": "What does Article 13 require?"}],
            )
        assert r.status_code == 200, r.json()
        with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
            size = len(_ENGINE_CACHE._data)  # type: ignore[attr-defined]
        assert size == 1, (
            f"served_by={served_by!r} is a normal serve and must stay cacheable"
        )

    @pytest.mark.parametrize(
        "served_by", ["fallback", "deterministic"], ids=["bedrock", "deterministic"]
    )
    def test_a_degraded_serve_is_never_cached(
        self, served_by: str, _partner_key_and_clean_cache
    ) -> None:
        """The rg_010 replay: one degraded generation must not become the answer."""
        from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415

        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=_response(served_by=served_by),
        ):
            r = TestClient(app).post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers=_headers(),
                json=[{"role": "user", "content": "What does Article 13 require?"}],
            )
        assert r.status_code == 200, r.json()
        assert r.json()["answer"], "the answer is still served — only not cached"
        with _ENGINE_CACHE._lock:  # type: ignore[attr-defined]
            size = len(_ENGINE_CACHE._data)  # type: ignore[attr-defined]
        assert size == 0, (
            f"served_by={served_by!r} must not be cached: the next ask has to "
            f"recompute so a later wrapper-served answer can land"
        )


# ── the retry flag is answer-flipping, so it is in the cache key ────────────


class TestTheRetryFlagIsInTheEngineCacheKey:
    def test_the_two_flag_states_do_not_share_a_cache_entry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key  # noqa: PLC0415

        monkeypatch.setenv("REGENOLD_STAGE2_DEGENERATE_RETRY", "1")
        on = _engine_cache_key("What does Article 13 require?", None)
        monkeypatch.setenv("REGENOLD_STAGE2_DEGENERATE_RETRY", "0")
        off = _engine_cache_key("What does Article 13 require?", None)
        assert on != off, (
            "the flag decides tunnel vs Bedrock provenance, so an A/B of it would "
            "replay the other arm's prose and read +0.0000 on every axis "
            "(the R329 unfalsifiable-lever trap)"
        )
