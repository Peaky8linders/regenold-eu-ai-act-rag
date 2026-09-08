"""R394 — Stage-0 intent was silently OFF for most of a batch run.

MEASURED. ``max_tokens`` was hardcoded to 250. The classifier's JSON carries a
``reasoning`` field, so at 250 the object is truncated mid-field — observed tail
``'"primary_anchor": "Art'`` — and ``_parse_intent_json`` returns ``None``.
Three of those inside the 60 s window trip ``_BREAKER``, after which
``is_intent_enabled()`` is False and every later call returns ``None`` in 0 ms.

Observed live on the official batch, BEFORE the fix:

    rg_001-rg_004   classified            651-1923 ms
    rg_005-rg_007   None                 3.5-4.3 s   (parse failure / timeout)
    rg_008 onward   None                        0 ms  <-- breaker latched

AFTER the fix (Bedrock sonnet-4-6, max_tokens 600): 14/14 classified, p50 3.1 s.

Budget sweep on Bedrock ``claude-sonnet-4-6`` over the official questions:
mt=250 -> 7/10, mt=600 -> 10/10, mt=1000 -> 10/10. 600 is the measured knee.

Same bug class R380 fixed for the Stage-0 de-noiser
(``REGENOLD_DENOISER_MAX_TOKENS`` 100 -> 400) at a call site never fixed.
"""
from __future__ import annotations

import pytest

from app.llm import intent_classifier as IC


# -- the completion budget ---------------------------------------------------


def test_default_budget_is_above_the_truncation_knee(monkeypatch):
    """250 truncated the schema; the measured knee is 600."""
    monkeypatch.delenv("REGENOLD_INTENT_MAX_TOKENS", raising=False)
    assert IC._max_tokens() == 600
    assert IC._max_tokens() > 250, (
        "a budget at or below 250 truncates the intent JSON mid-field and "
        "latches the circuit breaker after three rows"
    )


@pytest.mark.parametrize("bad", ["", "abc", "1.5", None])
def test_budget_fails_open(monkeypatch, bad):
    if bad is None:
        monkeypatch.delenv("REGENOLD_INTENT_MAX_TOKENS", raising=False)
    else:
        monkeypatch.setenv("REGENOLD_INTENT_MAX_TOKENS", bad)
    assert IC._max_tokens() == IC._INTENT_MAX_TOKENS_DEFAULT


def test_budget_is_clamped(monkeypatch):
    monkeypatch.setenv("REGENOLD_INTENT_MAX_TOKENS", "999999")
    assert IC._max_tokens() == 4000
    monkeypatch.setenv("REGENOLD_INTENT_MAX_TOKENS", "1")
    assert IC._max_tokens() == 120


def test_both_call_sites_use_the_knob():
    """The primary AND the fallback call must both honour the budget.

    Asserted on the source because the fallback only executes when the primary
    provider raises, which no unit test should have to simulate to pin a
    constant that was previously hardcoded twice.
    """
    import inspect

    src = inspect.getsource(IC.classify_intent)
    assert src.count("max_tokens=_max_tokens()") == 2
    assert "max_tokens=250" not in src


# -- the hot-path latency guard ----------------------------------------------


def test_global_timeout_still_honours_the_hot_path_guard(monkeypatch):
    """tests/test_rag_hardening.py pins <= 5.0s: intent is on the hot budget.

    R394 briefly raised this to 12.0 to accommodate Bedrock and broke that
    contract. The Bedrock path carries its OWN timeout instead; this one stays.
    """
    monkeypatch.delenv("REGENOLD_INTENT_TIMEOUT", raising=False)
    import importlib

    importlib.reload(IC)
    assert IC._TIMEOUT_SECONDS <= 5.0


def test_bedrock_path_has_its_own_timeout(monkeypatch):
    monkeypatch.delenv("REGENOLD_INTENT_BEDROCK_TIMEOUT", raising=False)
    assert IC._bedrock_intent_timeout() == 12.0
    assert IC._bedrock_intent_timeout() > IC._TIMEOUT_SECONDS, (
        "Bedrock measured 3.1s p50 / 7.7s worst, so it cannot run under the "
        "3.5s hot-path guard — which is exactly why it ships default OFF"
    )
    monkeypatch.setenv("REGENOLD_INTENT_BEDROCK_TIMEOUT", "junk")
    assert IC._bedrock_intent_timeout() == 12.0


# -- the provider flag, two-sided --------------------------------------------


def test_bedrock_intent_is_default_off(monkeypatch):
    """A reliable Stage-0 costs more latency than the guard allows.

    Speed is a scored axis we currently BEAT the frontier baseline on (+7.0),
    so spending ~3.1s/row on intent is a gated decision, not a default.
    """
    monkeypatch.delenv("REGENOLD_INTENT_BEDROCK", raising=False)
    assert IC._bedrock_intent_enabled() is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
def test_bedrock_intent_turns_on(monkeypatch, truthy):
    monkeypatch.setenv("REGENOLD_INTENT_BEDROCK", truthy)
    assert IC._bedrock_intent_enabled() is True


@pytest.mark.parametrize("falsy", ["0", "", "no", "off", "garbage"])
def test_bedrock_intent_stays_off(monkeypatch, falsy):
    monkeypatch.setenv("REGENOLD_INTENT_BEDROCK", falsy)
    assert IC._bedrock_intent_enabled() is False


def test_bedrock_model_default_is_not_sonnet_5(monkeypatch):
    """``claude-sonnet-5`` returns api_access_denied_403 on this Bedrock key.

    Measured this round, and consistent with the standing note that opus-5 and
    sonnet-5 both 403 there. Selecting it would silently disable intent again.
    """
    monkeypatch.delenv("REGENOLD_INTENT_MODEL_BEDROCK", raising=False)
    assert IC._bedrock_intent_model() == "claude-sonnet-4-6"
    monkeypatch.setenv("REGENOLD_INTENT_MODEL_BEDROCK", "")
    assert IC._bedrock_intent_model() == "claude-sonnet-4-6"


def test_bedrock_is_not_selected_when_the_flag_is_off(monkeypatch):
    """The inert-feature tripwire: OFF must really route elsewhere."""
    monkeypatch.setenv("REGENOLD_INTENT_BEDROCK", "0")
    sel = IC._resolve_intent_provider()
    if sel is not None:
        assert not isinstance(sel[0], IC._BedrockIntentAdapter)


# -- the breaker still protects the hot path ---------------------------------


def test_three_failures_still_open_the_breaker():
    """The budget fix removes the CAUSE; the breaker must still be armed."""
    breaker = IC._BreakerState()
    for _ in range(IC._FAILURE_THRESHOLD):
        breaker.record_failure()
    assert breaker.open() is True
    breaker.record_success()
    assert breaker.open() is False
