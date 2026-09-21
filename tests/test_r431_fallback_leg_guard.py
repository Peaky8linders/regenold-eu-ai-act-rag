"""R431 — the Stage-2 transport guard must be LEG-AWARE, not primary-or-nothing.

The guard aborts for one condition: the rows stop being served by a Stage-2 leg at
all, so the batch would grade deterministic Stage-1 drafts and measure the transport
instead of the lever. A tripped PRIMARY is not that condition while the Bedrock
fallback is answering — the wire is still Stage-2's and every row records which leg
served it.

MEASURED cost of the old behaviour: the R431 hard draw lost its third generation at
12/37 while the fallback was healthy the whole time.

These tests drive the REAL installer with a real provider instance whose transport is
faked at the class method, so what is pinned is the shipped wiring rather than a
paraphrase of it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


class _Resp:
    def __init__(self, *, error: str = "", model: str = "") -> None:
        self.error = error or None
        self.model = model


def _provider(error: str) -> Any:
    """A real ``_OpenAIWrapperProvider`` with no transport behind it."""
    from app.llm import openai_wrapper_provider as wp

    p = wp._OpenAIWrapperProvider.__new__(wp._OpenAIWrapperProvider)
    p._base_url = "https://wrapper.example/v1"
    p._error = error
    return p


def _trace(served_by: str) -> dict[str, Any]:
    """A response body carrying a provenance trace, as the route emits it."""
    return {
        "reasoning": json.dumps(
            {
                "stage2_polish": True,
                "notes": [
                    "stage2_model=claude-opus-5",
                    f"stage2_served_by={served_by}",
                ],
            }
        )
    }


def _install(monkeypatch: pytest.MonkeyPatch, provider: Any):
    from app.llm import openai_wrapper_provider as wp
    from evals.regenold import run_official_batch as rob

    monkeypatch.setattr(wp, "is_openai_wrapper_enabled", lambda: True)
    monkeypatch.setattr(wp, "get_openai_wrapper_provider", lambda: provider)
    monkeypatch.setattr(
        wp._OpenAIWrapperProvider,
        "complete",
        lambda self, _req: _Resp(error=getattr(self, "_error", "")),
    )
    return rob, wp


def _trip(wp: Any, provider: Any) -> None:
    """Five consecutive primary failures, through the REAL patched method."""
    req = wp.OpenAIWrapperRequest(user="x", max_tokens=8)
    for _ in range(5):
        wp._OpenAIWrapperProvider.complete(provider, req)


def test_tripped_primary_with_a_healthy_fallback_does_not_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider("api_status_500: No response from Claude Code")
    rob, wp = _install(monkeypatch, provider)
    monkeypatch.setattr(rob, "_probe_fallback_leg", lambda: "")
    preflight, assert_healthy = rob._install_stage2_transport_guard()
    with pytest.raises(RuntimeError):
        preflight()
    _trip(wp, provider)
    # The row that just landed was served by the fallback: continue, loudly.
    assert_healthy(_trace("fallback"))


def test_tripped_primary_without_any_leg_still_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider("api_status_500: No response from Claude Code")
    rob, wp = _install(monkeypatch, provider)
    _preflight, assert_healthy = rob._install_stage2_transport_guard()
    _trip(wp, provider)
    with pytest.raises(RuntimeError, match="deterministic Stage-1 drafts"):
        assert_healthy(_trace("deterministic"))


def test_preflight_returns_the_fallback_leg_when_the_primary_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider("api_status_500: No response from Claude Code")
    rob, _wp = _install(monkeypatch, provider)
    monkeypatch.setattr(rob, "_probe_fallback_leg", lambda: "qwen.qwen3-235b")
    preflight, _assert = rob._install_stage2_transport_guard()
    assert preflight() == "fallback:qwen.qwen3-235b"


def test_preflight_refuses_when_neither_leg_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider("api_status_500: No response from Claude Code")
    rob, _wp = _install(monkeypatch, provider)
    monkeypatch.setattr(rob, "_probe_fallback_leg", lambda: "")
    preflight, _assert = rob._install_stage2_transport_guard()
    with pytest.raises(RuntimeError, match="fallback leg did not answer"):
        preflight()


def test_probe_fallback_leg_is_fail_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm import bedrock_client as bc
    from evals.regenold import run_official_batch as rob

    def _boom() -> dict[str, Any]:
        raise RuntimeError("no credentials")

    monkeypatch.setattr(bc, "check_connectivity_and_permissions", _boom)
    assert rob._probe_fallback_leg() == ""

    monkeypatch.setattr(
        bc, "check_connectivity_and_permissions", lambda: {"status": "key_invalid"}
    )
    assert rob._probe_fallback_leg() == ""

    monkeypatch.setattr(
        bc,
        "check_connectivity_and_permissions",
        lambda: {"status": "ok", "model": "qwen.qwen3-235b"},
    )
    assert rob._probe_fallback_leg() == "qwen.qwen3-235b"


def test_the_health_checks_are_called_with_the_row_payload() -> None:
    """The wiring, not just the behaviour: the guard needs the row it just drew."""
    import inspect

    from evals.regenold import run_official_batch as rob

    assert "check(result)" in inspect.getsource(rob)
    assert (
        "def assert_healthy(_payload: object | None = None)"
        in inspect.getsource(rob._install_cohere_guard)
    )
    guard_src = inspect.getsource(rob._install_stage2_transport_guard)
    assert "def assert_healthy(payload: object | None = None)" in guard_src
    assert 'if leg_state["last_leg"] == "fallback":' in guard_src
