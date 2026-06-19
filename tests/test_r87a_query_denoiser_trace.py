"""R87-A — Query De-Noiser observability via ReasoningTrace.

The R86 Query De-Noiser ships seven distinct exit paths (disabled,
single-turn, import_error, no_provider, provider_init_error,
provider_error, empty_text, length_out_of_bounds, exception, success).
The first live measurement (r86-live-postship) had no way to tell which
path each multi-turn row took, so we couldn't attribute the persistent
multi-turn Ref Loose 0.371 floor to de-noiser non-firing vs. a deeper
retrieval miss.

R87-A wires every exit path through ``record_query_denoiser`` onto the
active ``ReasoningTrace``. Pure observability — zero behaviour change
on the happy or any fallback path. The judge runner + post-deploy
analysis can now read ``reasoning.query_denoiser`` and see the firing
breakdown across all 100 sample rows.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.regenold import reasoning_trace as rt
from app.routes.regenold import _rewrite_multiturn_query


@pytest.fixture(autouse=True)
def _neutralise_cli_provider_gate(monkeypatch):
    """Make the wrapper/Groq de-noiser branch reachable regardless of the
    ambient provider env.

    R127 made ``is_openai_wrapper_enabled()`` return ``False`` whenever
    ``P2P_GRAPH_RAG_PROVIDER=cli`` — the deterministic-eval / developer
    setting (and the value the davidath harness exports). These tests
    exercise the LLM-wired de-noiser path and ``patch`` the provider
    factory; under the cli gate ``_rewrite_multiturn_query`` short-circuits
    to ``no_provider`` BEFORE reaching that patch, so the wrapper-branch
    assertions fail. Drop the cli override here so the suite passes under
    any invocation env. Tests that want the wrapper OFF patch
    ``is_openai_wrapper_enabled`` directly (``test_records_no_provider_fallback``)
    and are unaffected; the disabled / single-turn / trace-inactive tests
    short-circuit before the provider gate.
    """
    monkeypatch.delenv("P2P_GRAPH_RAG_PROVIDER", raising=False)


@pytest.fixture
def trace():
    """Activate a fresh trace per test; deactivate on teardown."""
    t = rt.activate()
    yield t
    rt.deactivate()


def _mk_msg(role: str, content: str):
    """Mirror the route's expected message shape (has .role + .content)."""
    m = MagicMock()
    m.role = role
    m.content = content
    return m


# ─── exit paths ────────────────────────────────────────────────────────────


def test_records_disabled_fallback(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    _rewrite_multiturn_query("any?", [_mk_msg("user", "prior")])
    assert trace.query_denoiser == {
        "fired": False,
        "fallback_reason": "disabled",
    }


def test_records_single_turn_no_history(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    _rewrite_multiturn_query("any?", [])
    assert trace.query_denoiser == {
        "fired": False,
        "fallback_reason": "single_turn",
    }


def test_records_no_provider_fallback(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.llm.openai_wrapper_provider
    monkeypatch.setattr(app.llm.openai_wrapper_provider, "is_openai_wrapper_enabled", lambda: False)

    _rewrite_multiturn_query("any?", [_mk_msg("user", "prior")])
    assert trace.query_denoiser == {
        "fired": False,
        "fallback_reason": "no_provider",
    }


def test_records_provider_error_with_latency(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = "network_error: timed out"
    fake_resp.text = ""
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        _rewrite_multiturn_query("any?", [_mk_msg("user", "prior")])

    qd = trace.query_denoiser
    assert qd["fired"] is False
    assert qd["fallback_reason"] == "provider_error"
    assert qd["provider"] == "wrapper"
    assert "model" in qd
    # latency may or may not exceed 1 ms tick — just sanity-check it's
    # either absent (sub-ms) or a small integer.
    assert qd.get("latency_ms", 0) >= 0


def test_records_empty_text_distinct_from_error(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "   "
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        _rewrite_multiturn_query("any?", [_mk_msg("user", "prior")])

    qd = trace.query_denoiser
    assert qd["fired"] is False
    assert qd["fallback_reason"] == "empty_text"


def test_records_length_out_of_bounds(monkeypatch, trace) -> None:
    """A too-long rewrite means the LLM ignored rule 7 — bail + record."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "x" * 600
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        _rewrite_multiturn_query("any?", [_mk_msg("user", "prior")])

    qd = trace.query_denoiser
    assert qd["fired"] is False
    assert qd["fallback_reason"] == "length_out_of_bounds"
    assert qd["rewritten_chars"] == 600


def test_records_happy_path_with_provider_metadata(monkeypatch, trace) -> None:
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "1")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("REGENOLD_INTENT_PROVIDER", raising=False)

    fake_resp = MagicMock()
    fake_resp.error = None
    fake_resp.text = "deployer transparency obligations Art. 26"
    fake_provider = MagicMock()
    fake_provider.complete.return_value = fake_resp

    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        out = _rewrite_multiturn_query(
            "What about deployers?",
            [_mk_msg("user", "What is Article 13?")],
        )

    # Happy path actually returns the rewrite to the caller
    assert out == "deployer transparency obligations Art. 26"

    qd = trace.query_denoiser
    assert qd["fired"] is True
    # Happy path: fallback_reason MUST be absent from the payload.
    assert "fallback_reason" not in qd
    assert qd["provider"] == "wrapper"
    assert qd["model"] == "claude-haiku-4-5-20251001"
    assert qd["rewritten_chars"] == len(out)


# ─── trace inactive path — zero overhead ───────────────────────────────────


def test_no_overhead_when_trace_inactive(monkeypatch) -> None:
    """When no ReasoningTrace is active, ``record_query_denoiser``
    short-circuits and the de-noiser still returns its normal value.
    Verified by NOT activating a trace fixture — the recorder helper
    must check ``current()`` first and bail."""
    monkeypatch.setenv("REGENOLD_QUERY_DENOISER", "0")
    # No `trace` fixture — recorder must not crash on missing ContextVar
    out = _rewrite_multiturn_query("any?", [_mk_msg("user", "prior")])
    assert out is None  # disabled → None as before


# ─── serialisation surface ────────────────────────────────────────────────


def test_trace_serialises_query_denoiser_block(trace) -> None:
    rt.record_query_denoiser(
        fired=True,
        latency_ms=243,
        rewritten_chars=58,
        model="claude-haiku-4-5-20251001",
        provider="wrapper",
    )
    j = trace.to_json_dict()
    assert "query_denoiser" in j
    assert j["query_denoiser"]["fired"] is True
    assert j["query_denoiser"]["latency_ms"] == 243
    assert j["query_denoiser"]["rewritten_chars"] == 58
    assert j["query_denoiser"]["provider"] == "wrapper"


def test_trace_omits_query_denoiser_block_when_unrecorded(trace) -> None:
    """Empty payload → field is omitted from the JSON output (keeps the
    reasoning string compact when the de-noiser branch never ran)."""
    j = trace.to_json_dict()
    assert "query_denoiser" not in j


def test_record_query_denoiser_caps_field_lengths(trace) -> None:
    """Long fallback_reason / model strings get truncated so a runaway
    error string can't bloat the reasoning payload."""
    rt.record_query_denoiser(
        fired=False,
        fallback_reason="x" * 500,
        model="y" * 500,
        provider="z" * 500,
    )
    qd = trace.query_denoiser
    assert len(qd["fallback_reason"]) <= 64
    assert len(qd["model"]) <= 64
    assert len(qd["provider"]) <= 32
