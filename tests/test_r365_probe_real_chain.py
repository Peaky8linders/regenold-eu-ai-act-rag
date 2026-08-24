"""R365 — the Bedrock diagnostic must probe the models the FALLBACK actually dials.

Measured 2026-08-24 against a healthy live credential:

    qwen.qwen3-235b-a22b-2507-v1:0  -> ok
    qwen.qwen3-32b-v1:0             -> ok
    eu.anthropic.claude-opus-4-8    -> api_access_denied_403      <-- the OLD default

So the previous default could report Stage-2 leg 2 BROKEN on a deployment whose
fallback was in fact fully working — a false alarm in the one instrument an
operator reaches for during an outage.

Every test here is offline: ``check_connectivity_and_permissions`` is exercised
through a stubbed single-model probe, never against AWS.
"""

from __future__ import annotations

import pytest

from app.llm import bedrock_client as bc


def test_the_probe_chain_is_the_engine_fallback_chain() -> None:
    """The constant must mirror ``_default_fallback_models`` in the engine.

    Pinned as a literal rather than imported so a silent edit to either side
    fails here instead of drifting apart unnoticed.
    """
    assert bc.BEDROCK_FALLBACK_PROBE_MODELS == (
        "qwen.qwen3-235b-a22b-2507-v1:0",
        "qwen.qwen3-32b-v1:0",
    )


def test_the_old_default_is_not_in_the_chain() -> None:
    """Regression pin for the actual defect."""
    assert "eu.anthropic.claude-opus-4-8" not in bc.BEDROCK_FALLBACK_PROBE_MODELS
    # ...and it is still what _resolve_default_model returns, which is exactly
    # why the probe must not use that resolver.
    assert bc._resolve_default_model() == "eu.anthropic.claude-opus-4-8"


def _stub(monkeypatch, outcomes: dict[str, str]) -> list[str]:
    """Route single-model probes through ``outcomes``; record the call order."""
    seen: list[str] = []
    real = bc.check_connectivity_and_permissions

    def _fake(model_id: str | None = None):
        if model_id is None:
            return real(model_id=None)  # exercise the REAL chain-walking branch
        seen.append(model_id)
        status = outcomes.get(model_id, "error")
        return {
            "status": status,
            "model": model_id,
            "error": None if status == "ok" else "api_access_denied_403",
            "elapsed_ms": 1,
        }

    monkeypatch.setattr(bc, "check_connectivity_and_permissions", _fake)
    return seen


class TestChainWalking:
    def test_reports_ok_when_the_first_chain_model_answers(self, monkeypatch) -> None:
        seen = _stub(monkeypatch, {"qwen.qwen3-235b-a22b-2507-v1:0": "ok"})
        res = bc.check_connectivity_and_permissions()
        assert res["status"] == "ok"
        assert res["model"] == "qwen.qwen3-235b-a22b-2507-v1:0"
        assert [c["status"] for c in res["chain"]][0] == "ok"

    def test_reports_ok_when_only_the_SECOND_chain_model_answers(
        self, monkeypatch
    ) -> None:
        """"The fallback leg works" means SOME chain model answers."""
        seen = _stub(monkeypatch, {"qwen.qwen3-32b-v1:0": "ok"})
        res = bc.check_connectivity_and_permissions()
        assert res["status"] == "ok"
        assert res["model"] == "qwen.qwen3-32b-v1:0"
        assert seen[0] == "qwen.qwen3-235b-a22b-2507-v1:0", "must try 235b first"

    def test_reports_error_only_when_NO_chain_model_answers(self, monkeypatch) -> None:
        _stub(monkeypatch, {})
        res = bc.check_connectivity_and_permissions()
        assert res["status"] != "ok"
        assert len(res["chain"]) == len(bc.BEDROCK_FALLBACK_PROBE_MODELS)
        assert all(c["status"] != "ok" for c in res["chain"])

    def test_every_attempt_is_surfaced_even_on_success(self, monkeypatch) -> None:
        """A partial entitlement must stay visible, not be hidden by the first ok."""
        _stub(monkeypatch, {"qwen.qwen3-235b-a22b-2507-v1:0": "ok"})
        res = bc.check_connectivity_and_permissions()
        assert "chain" in res
        assert {c["model"] for c in res["chain"]} <= set(
            bc.BEDROCK_FALLBACK_PROBE_MODELS
        )


class TestExplicitModelStillWorks:
    """Two-sided: an explicit model_id must NOT be redirected to the chain."""

    def test_explicit_model_is_probed_verbatim(self, monkeypatch) -> None:
        seen = _stub(monkeypatch, {"eu.anthropic.claude-opus-4-8": "ok"})
        res = bc.check_connectivity_and_permissions(
            model_id="eu.anthropic.claude-opus-4-8"
        )
        assert res["model"] == "eu.anthropic.claude-opus-4-8"
        assert seen == ["eu.anthropic.claude-opus-4-8"]
        assert "chain" not in res, "an explicit probe is single-model, not a walk"

    def test_explicit_probe_of_a_chain_model_does_not_walk(self, monkeypatch) -> None:
        seen = _stub(monkeypatch, {"qwen.qwen3-32b-v1:0": "ok"})
        res = bc.check_connectivity_and_permissions(model_id="qwen.qwen3-32b-v1:0")
        assert seen == ["qwen.qwen3-32b-v1:0"]
        assert res["status"] == "ok"


class TestPolicy:
    """The operator directive is recorded next to the constant, not in a doc
    that can drift out of the repo."""

    def test_the_fallback_only_policy_is_documented_at_the_constant(self) -> None:
        src = bc.__doc__ or ""
        import inspect

        mod_src = inspect.getsource(bc)
        idx = mod_src.index("BEDROCK_FALLBACK_PROBE_MODELS")
        preamble = mod_src[max(0, idx - 1400) : idx].lower()
        assert "fallback" in preamble
        assert "judge" in preamble
        assert "never the primary" in preamble or "not the primary" in preamble
