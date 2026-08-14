"""R330 §4 (TIER 2 — Speed, output-identical) — the two wasted wrapper calls.

Both `frames_rewriter.rewrite_sub_query_llm` and `clara_logic.analyse`'s LLM
leg budget 3.0 s against a measured 12-17 s Claude Max wrapper floor with no
fast-provider chain, so neither call can realistically land: it burns its full
budget and then takes a fail-soft branch whose return value is identical to
never having called at all.

These tests pin BOTH halves of that claim:

* with the gate unset (the shipped default) the provider is invoked **zero**
  times, and the returned value equals today's failure-path value;
* with the gate on, the provider IS invoked — i.e. the gate is a gate, not a
  deletion.

Gates under test (both DEFAULT ``0``):
  * ``REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER``  (frames_rewriter, R330 §4.1)
  * ``REGENOLD_CLARA_LLM``                      (clara_logic,     R330 §4.2)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import app.llm.openai_wrapper_provider as ow
from app.engines import clara_logic, frames_rewriter
from app.engines.clara_logic import analyse, extract_tags_deterministic
from app.engines.frames_rewriter import rewrite_sub_query_llm
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


_SUB_QUERY = "obligations for high-risk providers"
_ORIGINAL_Q = "What must a provider of a high-risk AI system do before placing it on the market?"

# july7-259-style row: clara's deterministic extractor lands a prohibited
# verdict on it, so any divergence between the LLM and deterministic legs
# would be visible in the asserted verdict below.
_CLARA_Q = "We use emotion recognition AI in the workplace to monitor staff."


class _CountingProvider:
    """Stands in for the wrapper. Records every ``complete`` invocation."""

    def __init__(self, response: OpenAIWrapperResponse) -> None:
        self.calls = 0
        self._response = response

    def complete(self, _req):  # noqa: ANN001 — mirrors the provider contract
        self.calls += 1
        return self._response


@pytest.fixture(autouse=True)
def _wrapper_env(monkeypatch):
    """Make ``is_openai_wrapper_enabled()`` True so the gate is the ONLY thing
    standing between the caller and the provider."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER", raising=False)
    monkeypatch.delenv("REGENOLD_CLARA_LLM", raising=False)
    clara_logic._reset_for_tests()
    yield
    clara_logic._reset_for_tests()


# ── §4.1 frames_rewriter ─────────────────────────────────────────────────


def test_frames_rewriter_default_off_makes_zero_provider_calls():
    """Default (gate unset): no wrapper call, and the sub-query is returned
    unchanged — byte-identical to the ``frames_rewriter_error`` branch."""
    provider = _CountingProvider(OpenAIWrapperResponse(
        text="high-risk AI system provider pre-market obligations",
        model="claude-haiku-4-5",
        elapsed_ms=2999,
    ))
    with patch.object(frames_rewriter, "get_openai_wrapper_provider", return_value=provider):
        out = rewrite_sub_query_llm(_SUB_QUERY, _ORIGINAL_Q)

    assert provider.calls == 0
    assert out == _SUB_QUERY


def test_frames_rewriter_default_off_matches_the_error_branch_verbatim():
    """The skip must return exactly what a timed-out wrapper returns today."""
    error_provider = _CountingProvider(OpenAIWrapperResponse(
        error="timeout after 3.0s",
        model="claude-haiku-4-5",
        elapsed_ms=3000,
    ))
    with patch.object(frames_rewriter, "get_openai_wrapper_provider", return_value=error_provider):
        # Gate ON but the wrapper fails — today's live behaviour.
        with patch.dict("os.environ", {"REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER": "1"}):
            failure_path = rewrite_sub_query_llm(_SUB_QUERY, _ORIGINAL_Q)
        assert error_provider.calls == 1

    skip_provider = _CountingProvider(OpenAIWrapperResponse(
        error="timeout after 3.0s", model="claude-haiku-4-5", elapsed_ms=3000,
    ))
    with patch.object(frames_rewriter, "get_openai_wrapper_provider", return_value=skip_provider):
        skip_path = rewrite_sub_query_llm(_SUB_QUERY, _ORIGINAL_Q)

    assert skip_provider.calls == 0
    assert skip_path == failure_path == _SUB_QUERY


def test_frames_rewriter_gate_on_attempts_the_call(monkeypatch):
    """Flag ON restores the pre-R330 behaviour exactly."""
    monkeypatch.setenv("REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER", "1")
    provider = _CountingProvider(OpenAIWrapperResponse(
        text="high-risk AI system provider pre-market obligations",
        model="claude-haiku-4-5",
        elapsed_ms=2999,
    ))
    with patch.object(frames_rewriter, "get_openai_wrapper_provider", return_value=provider):
        out = rewrite_sub_query_llm(_SUB_QUERY, _ORIGINAL_Q)

    assert provider.calls == 1
    assert out == "high-risk AI system provider pre-market obligations"


@pytest.mark.parametrize("raw", ["0", "", "off", "no", "false", "maybe", "2", " "])
def test_frames_rewriter_gate_fails_closed(monkeypatch, raw):
    """Anything not an explicit enable means OFF."""
    monkeypatch.setenv("REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER", raw)
    provider = _CountingProvider(OpenAIWrapperResponse(text="rewritten", model="m", elapsed_ms=1))
    with patch.object(frames_rewriter, "get_openai_wrapper_provider", return_value=provider):
        assert rewrite_sub_query_llm(_SUB_QUERY, _ORIGINAL_Q) == _SUB_QUERY
    assert provider.calls == 0


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", " 1 "])
def test_frames_rewriter_gate_accepts_the_repo_truthy_set(monkeypatch, raw):
    monkeypatch.setenv("REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER", raw)
    assert frames_rewriter._frames_rewriter_wrapper_allowed() is True


# ── §4.2 clara_logic ─────────────────────────────────────────────────────


def test_clara_analyse_default_off_makes_zero_provider_calls():
    """Default (gate unset): the serial-tail wrapper call never happens and
    ``analyse`` returns the deterministic tags/verdict — exactly what a
    timed-out LLM leg produces today via the ``None`` fallback."""
    provider = _CountingProvider(OpenAIWrapperResponse(
        text='{"is_emotion_recognition": true, "used_in_workplace": true}',
        model="claude-haiku-4-5",
        elapsed_ms=2999,
    ))
    with patch.object(ow, "get_openai_wrapper_provider", return_value=provider):
        tags, verdict = analyse(_CLARA_Q)

    assert provider.calls == 0
    assert tags == extract_tags_deterministic(_CLARA_Q)
    assert verdict.risk_tier == "prohibited"
    assert verdict.primary_articles == ("Article 5.1.f",)


def test_clara_analyse_default_off_matches_the_timeout_path_verbatim():
    """The skip must be indistinguishable from a wrapper error."""
    error_provider = _CountingProvider(OpenAIWrapperResponse(
        error="timeout after 3.0s", model="claude-haiku-4-5", elapsed_ms=3000,
    ))
    with patch.object(ow, "get_openai_wrapper_provider", return_value=error_provider):
        with patch.dict("os.environ", {"REGENOLD_CLARA_LLM": "1"}):
            failure_tags, failure_verdict = analyse(_CLARA_Q)
        assert error_provider.calls == 1

    clara_logic._reset_for_tests()
    skip_provider = _CountingProvider(OpenAIWrapperResponse(
        error="timeout after 3.0s", model="claude-haiku-4-5", elapsed_ms=3000,
    ))
    with patch.object(ow, "get_openai_wrapper_provider", return_value=skip_provider):
        skip_tags, skip_verdict = analyse(_CLARA_Q)

    assert skip_provider.calls == 0
    assert skip_tags == failure_tags
    assert skip_verdict == failure_verdict


def test_clara_analyse_gate_on_attempts_the_call(monkeypatch):
    """Flag ON restores the pre-R330 behaviour: the LLM tags win."""
    monkeypatch.setenv("REGENOLD_CLARA_LLM", "1")
    provider = _CountingProvider(OpenAIWrapperResponse(
        text='{"is_social_scoring": true}',
        model="claude-haiku-4-5",
        elapsed_ms=2999,
    ))
    with patch.object(ow, "get_openai_wrapper_provider", return_value=provider):
        tags, verdict = analyse("Some question the deterministic pass would read differently?")

    assert provider.calls == 1
    assert tags.is_social_scoring is True
    assert verdict.risk_tier == "prohibited"


@pytest.mark.parametrize("raw", ["0", "", "off", "no", "false", "maybe", "2", " "])
def test_clara_gate_fails_closed(monkeypatch, raw):
    monkeypatch.setenv("REGENOLD_CLARA_LLM", raw)
    provider = _CountingProvider(OpenAIWrapperResponse(
        text='{"is_social_scoring": true}', model="m", elapsed_ms=1,
    ))
    with patch.object(ow, "get_openai_wrapper_provider", return_value=provider):
        analyse(_CLARA_Q)
    assert provider.calls == 0


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", " 1 "])
def test_clara_gate_accepts_the_repo_truthy_set(monkeypatch, raw):
    monkeypatch.setenv("REGENOLD_CLARA_LLM", raw)
    assert clara_logic._clara_llm_wrapper_allowed() is True


def test_clara_gate_is_read_at_call_time(monkeypatch):
    """Not a module-level constant — flipping it mid-process must take
    effect (the R263.2 fresh-read idiom)."""
    provider = _CountingProvider(OpenAIWrapperResponse(
        text='{"is_social_scoring": true}', model="m", elapsed_ms=1,
    ))
    with patch.object(ow, "get_openai_wrapper_provider", return_value=provider):
        analyse("first pass question about social scoring?")
        assert provider.calls == 0
        monkeypatch.setenv("REGENOLD_CLARA_LLM", "1")
        analyse("second pass question about social scoring?")
    assert provider.calls == 1
