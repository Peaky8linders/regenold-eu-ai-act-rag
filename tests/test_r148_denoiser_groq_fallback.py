"""R148 — Query de-noiser Groq→wrapper provider fallback.

Root cause (reproduced live 2026-06-22): once Groq's free-tier 100K
tokens-per-day budget is exhausted, every ``llama-3.3-70b-versatile``
call returns ``api_status_429`` and the trace shows
``denoiser skipped (provider_error)``. The de-noiser's provider
selection was ``if groq … elif wrapper …``, so a Groq failure dropped the
multi-turn rewrite entirely instead of falling back to the
already-configured Haiku wrapper — the fallback the intent classifier
(``app/llm/intent_classifier.py``) has always had.

These tests pin the provider chain: Groq first, wrapper as fallback on a
Groq provider failure, deterministic salvage only when BOTH fail. The
wrapper-only and Groq-only configurations stay byte-identical to the
pre-R148 single-provider behaviour (covered by
``tests/test_r87a_query_denoiser_trace.py``).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.integrations.regenold import reasoning_trace as rt
from app.routes.regenold import _rewrite_multiturn_query

GROQ_429 = (
    'api_status_429: {"error":{"message":"Rate limit reached for model '
    "`llama-3.3-70b-versatile` in organization `org_x` service tier "
    '`on_demand` on tokens per day (TPD): Limit 100000, Used 100000"}}'
)


@pytest.fixture(autouse=True)
def _both_providers_wired(monkeypatch):
    """Wire BOTH Groq (key present, default intent provider) and the
    wrapper (OPENAI_API_BASE set) — the production shape where the
    fallback chain matters."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)  # wrapper reachable
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)  # → groq default


@pytest.fixture
def trace():
    t = rt.activate()
    yield t
    rt.deactivate()


def _mk_msg(role: str, content: str):
    m = MagicMock()
    m.role = role
    m.content = content
    return m


def _resp(*, error=None, text="", finish_reason="stop"):
    return SimpleNamespace(error=error, text=text, finish_reason=finish_reason)


def _provider(resp):
    p = MagicMock()
    p.complete.return_value = resp
    return p


def _wire(monkeypatch, groq, wrapper):
    import app.llm.openai_wrapper_provider as owp

    monkeypatch.setattr(owp, "is_groq_intent_provider_enabled", lambda: True)
    monkeypatch.setattr(owp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(owp, "get_groq_intent_provider", lambda: groq)
    monkeypatch.setattr(owp, "get_openai_wrapper_provider", lambda: wrapper)


def test_groq_429_falls_back_to_wrapper(monkeypatch, trace):
    """The reported bug: Groq TPD 429 must degrade to the Haiku wrapper,
    not drop the rewrite."""
    groq = _provider(_resp(error=GROQ_429))
    wrapper = _provider(_resp(text="emotion recognition prohibition workplace Article 5"))
    _wire(monkeypatch, groq, wrapper)

    out = _rewrite_multiturn_query(
        "are they always prohibited?",
        [_mk_msg("user", "Tell me about emotion recognition systems.")],
    )

    assert out == "emotion recognition prohibition workplace Article 5"
    groq.complete.assert_called_once()
    wrapper.complete.assert_called_once()
    qd = trace.query_denoiser
    assert qd["fired"] is True
    assert qd["provider"] == "wrapper"
    assert qd["model"] == "claude-haiku-4-5-20251001"


def test_groq_success_does_not_call_wrapper(monkeypatch, trace):
    """Happy Groq path is unchanged — wrapper is never touched."""
    groq = _provider(_resp(text="emotion recognition always prohibited Article 5"))
    wrapper = _provider(_resp(text="SHOULD NOT BE USED"))
    _wire(monkeypatch, groq, wrapper)

    out = _rewrite_multiturn_query(
        "are they always prohibited?",
        [_mk_msg("user", "Tell me about emotion recognition systems.")],
    )

    assert out == "emotion recognition always prohibited Article 5"
    groq.complete.assert_called_once()
    wrapper.complete.assert_not_called()
    assert trace.query_denoiser["provider"] == "groq"


def test_groq_exception_falls_back_to_wrapper(monkeypatch, trace):
    """A transport-level Groq exception (not just resp.error) also falls
    through to the wrapper."""
    groq = MagicMock()
    groq.complete.side_effect = RuntimeError("connection reset by peer")
    wrapper = _provider(_resp(text="deployer transparency obligations Article 26"))
    _wire(monkeypatch, groq, wrapper)

    out = _rewrite_multiturn_query(
        "what about deployers?",
        [_mk_msg("user", "What is Article 13?")],
    )

    assert out == "deployer transparency obligations Article 26"
    wrapper.complete.assert_called_once()
    assert trace.query_denoiser["fired"] is True
    assert trace.query_denoiser["provider"] == "wrapper"


def test_both_providers_fail_records_final_failure(monkeypatch, trace):
    """When Groq 429s AND the wrapper errors, the chain is exhausted →
    the de-noiser records the final provider failure and the caller falls
    back (salvage / concatenation)."""
    groq = _provider(_resp(error=GROQ_429))
    wrapper = _provider(_resp(error="network_error: timed out"))
    _wire(monkeypatch, groq, wrapper)

    _rewrite_multiturn_query(
        "what about deployers?",
        [_mk_msg("user", "What is Article 13?")],
    )

    groq.complete.assert_called_once()
    wrapper.complete.assert_called_once()
    qd = trace.query_denoiser
    assert qd["fired"] is False
    assert qd["fallback_reason"] == "provider_error"
    assert qd["provider"] == "wrapper"  # last provider attempted


def test_groq_empty_then_wrapper_succeeds(monkeypatch, trace):
    """An empty Groq completion is a provider failure → fall through."""
    groq = _provider(_resp(error=None, text="   "))
    wrapper = _provider(_resp(text="high-risk classification Annex III Article 6"))
    _wire(monkeypatch, groq, wrapper)

    out = _rewrite_multiturn_query(
        "is it high-risk?",
        [_mk_msg("user", "We deploy an emotion recognition system.")],
    )

    assert out == "high-risk classification Annex III Article 6"
    assert trace.query_denoiser["provider"] == "wrapper"
    assert trace.query_denoiser["fired"] is True
