"""R423 — a live run must refuse to spend itself on a Stage-2 leg that is down.

WHY THIS FILE EXISTS (one measured gate run, 90 minutes)
-------------------------------------------------------
The ``REGENOLD_NEED_PROPORTIONAL_CONTRACT`` gate completed and was correctly
VOIDED — but only after burning ~90 minutes and 243 Stage-2 calls inside a
single DNS outage. Read straight off the run log:

    233  wrapper_call_failed: network_error: [Errno 11001] getaddrinfo failed
      8  [WinError 10065] A socket operation was attempted to an unreachable host
      2  The read operation timed out
    243  -> exactly matches the 243 refused Groq fallbacks, then dead Bedrock

Every one of those calls walked the same dead path: the wrapper hostname did not
resolve (the Cloudflare tunnel that publishes it was down), the legacy Groq hatch
was refused by the strict-transport policy (by design), and the Bedrock
credential answers ``api_key_invalid_403`` — so the row shipped a deterministic
Stage-1 draft. Both arms voided on it, which is the R412/R422 void guard working
exactly as intended.

Catching that AFTER the fact is the expensive half. ``gate_validity`` can only
say "this run is unreadable"; it cannot stop the next one from spending an hour
the same way, and a degraded run is not a lever result at any sample size. So the
runner now probes the wrapper once BEFORE the first row is spent and aborts the
batch once ``max_consecutive`` Stage-2 calls in a row fail to reach a leg.
"""

from __future__ import annotations

import inspect

import pytest

from app.llm import openai_wrapper_provider as WP
from evals.regenold import run_official_batch as ROB

_OUTAGE = "network_error: [Errno 11001] getaddrinfo failed"


class _Resp:
    """Stand-in for ``OpenAIWrapperResponse``; only the fields the guard reads."""

    def __init__(self, *, error: str | None = None, model: str = "claude-opus-4-6") -> None:
        self.error = error
        self.model = model
        self.text = "" if error else "alive"


class _Stub:
    """The method the guard captures as ``original_complete``.

    Deliberately an OBJECT, not a function: assigning a non-descriptor to a class
    attribute means no binding happens, so the guard's ``original_complete(self,
    req)`` two-argument call lands here unchanged. That is what makes the stub
    replaceable *under* the guard — the earlier version of this test overwrote the
    class attribute AFTER installation, which silently bypassed the very counter
    under test and passed for the wrong reason.
    """

    def __init__(self, resp: _Resp) -> None:
        self.next = resp
        self.calls = 0

    def __call__(self, _self, _req):  # noqa: ANN001
        self.calls += 1
        return self.next


def _bare_provider() -> object:
    """An uninitialised provider, so ``complete`` resolves to the patched class
    method instead of building a real httpx client against the network."""
    return WP._OpenAIWrapperProvider.__new__(WP._OpenAIWrapperProvider)


def _install(monkeypatch, *, max_consecutive: int = 3, preflight_resp: str | None = None):
    """Install the guard over a stubbed original; return (preflight, healthy, stub)."""
    monkeypatch.setattr(WP, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(WP, "get_openai_wrapper_provider", _bare_provider)
    stub = _Stub(_Resp(error=preflight_resp))
    monkeypatch.setattr(WP._OpenAIWrapperProvider, "complete", stub)
    preflight, healthy = ROB._install_stage2_transport_guard(
        max_consecutive=max_consecutive
    )
    return preflight, healthy, stub


def _call() -> None:
    """Dial the guarded method the way the engine does (self is bound)."""
    provider = _bare_provider()
    provider.complete("probe")  # type: ignore[attr-defined]


def test_preflight_refuses_a_wrapper_that_cannot_answer(monkeypatch) -> None:
    """The whole point: refuse BEFORE the sample is spent, not after."""
    preflight, _healthy, stub = _install(monkeypatch, preflight_resp=_OUTAGE)
    with pytest.raises(RuntimeError) as excinfo:
        preflight()
    message = str(excinfo.value)
    assert "preflight failed" in message
    assert "getaddrinfo" in message
    # The message must name the escape hatch, or an operator cannot tell a
    # deliberate degraded run from a broken one.
    assert "--allow-degraded-transport" in message
    assert stub.calls == 1


def test_preflight_passes_and_names_the_serving_model(monkeypatch) -> None:
    preflight, healthy, _stub = _install(monkeypatch)
    assert preflight() == "claude-opus-4-6"
    healthy()  # a clean leg never trips the guard


def test_guard_trips_on_the_nth_consecutive_failure(monkeypatch) -> None:
    """One blip must not kill a run; a streak must."""
    preflight, healthy, stub = _install(monkeypatch, max_consecutive=3)
    preflight()
    stub.next = _Resp(error=_OUTAGE)
    for _ in range(2):
        _call()
        healthy()  # below the threshold: the batch keeps running
    _call()  # third consecutive failure
    with pytest.raises(RuntimeError, match="consecutive calls failed"):
        healthy()


def test_a_success_resets_the_streak(monkeypatch) -> None:
    preflight, healthy, stub = _install(monkeypatch, max_consecutive=3)
    preflight()
    stub.next = _Resp(error=_OUTAGE)
    for _ in range(2):
        _call()
    stub.next = _Resp()  # recovery
    _call()
    healthy()
    stub.next = _Resp(error=_OUTAGE)
    for _ in range(2):
        _call()
        healthy()  # the streak restarted, so two more is not yet an outage
    _call()
    with pytest.raises(RuntimeError, match="3 consecutive calls failed"):
        healthy()


def test_guard_aborts_on_a_sustained_outage(monkeypatch) -> None:
    preflight, healthy, stub = _install(monkeypatch, max_consecutive=3)
    preflight()
    stub.next = _Resp(error="network_error: The read operation timed out")
    for _ in range(3):
        _call()
    with pytest.raises(RuntimeError) as excinfo:
        healthy()
    message = str(excinfo.value)
    assert "Stage-2 transport is down" in message
    assert "3 consecutive calls failed" in message
    assert "read operation timed out" in message


def test_a_model_side_error_also_counts(monkeypatch) -> None:
    """With Bedrock dead and Groq refused, a 429 streak is just as unreadable."""
    preflight, healthy, stub = _install(monkeypatch, max_consecutive=2)
    preflight()
    stub.next = _Resp(error="api_status_429: rate limited")
    _call()
    _call()
    with pytest.raises(RuntimeError, match="consecutive calls failed"):
        healthy()


def test_tracker_resets_and_reports_its_last_error() -> None:
    tracker = ROB._ConsecutiveTransportFailures(2)
    tracker.record_failure(_OUTAGE)
    assert tracker.tripped() == ""
    tracker.record_failure(_OUTAGE)
    assert "2 consecutive calls failed" in tracker.tripped()
    tracker.record_ok()
    assert tracker.tripped() == ""


def test_transport_markers_cover_the_measured_shapes() -> None:
    """The markers are evidence, not taste: these are the strings the R423 log
    actually carried. A regression that narrows them would let an outage through
    as a model error."""
    markers = ROB._TRANSPORT_ERROR_MARKERS
    for measured in (
        "network_error: [Errno 11001] getaddrinfo failed",
        "network_error: [WinError 10065] A socket operation was attempted to an "
        "unreachable host",
        "network_error: The read operation timed out",
    ):
        assert any(marker in measured.lower() for marker in markers), measured


def test_degraded_runs_are_opt_in() -> None:
    """A run that measures the degradation path must say so explicitly."""
    source = inspect.getsource(ROB.main)
    assert "--allow-degraded-transport" in source
    assert "if local and not args.allow_degraded_transport" in source
