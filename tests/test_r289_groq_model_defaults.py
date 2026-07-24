"""R289 — the Groq model default, and the knobs that select it.

8145be2 swapped the Groq default from ``qwen/qwen3.6-27b`` to ``groq/compound``
at eight call sites plus a hardcoded ninth in ``/healthz``, and production
started returning HTTP 413 on a ~100-character probe. The controlled before/after
on the SAME probe:

    62ca878  -> {"status": "ok",    "model": "qwen/qwen3.6-27b"}
    8145be2  -> {"status": "error", "model": "groq/compound", 413 request_too_large}
    348ea6a  -> still 413

Groq's docs explain it: "Rate limits for groq/compound are determined by the rate
limits of the individual models that comprise them" — compound is an agentic
system whose internal fan-out draws on the account budget, and Groq reuses 413 /
``request_too_large`` for budget exhaustion. Payload size was never the constraint.

These tests pin the three properties that failure had no guard for.
"""
from __future__ import annotations

import pytest


class TestGroqDefaultModel:
    def test_default_is_the_live_validated_model_not_compound(self, monkeypatch):
        """The whole outage in one assertion (5869eec's validated value)."""
        from app.llm.openai_wrapper_provider import default_groq_model

        monkeypatch.delenv("REGENOLD_GROQ_DEFAULT_MODEL", raising=False)
        assert default_groq_model() == "openai/gpt-oss-120b"

    def test_compound_is_still_reachable_by_opt_in(self, monkeypatch):
        """Reverting the default must not make compound unreachable for debugging."""
        from app.llm.openai_wrapper_provider import default_groq_model

        monkeypatch.setenv("REGENOLD_GROQ_DEFAULT_MODEL", "groq/compound")
        assert default_groq_model() == "groq/compound"

    def test_blank_env_falls_back_rather_than_selecting_empty_model(
        self, monkeypatch
    ):
        from app.llm.openai_wrapper_provider import default_groq_model

        monkeypatch.setenv("REGENOLD_GROQ_DEFAULT_MODEL", "   ")
        assert default_groq_model() == "openai/gpt-oss-120b"

    def test_no_call_site_hardcodes_compound(self):
        """A per-site literal is how this broke; keep the default in ONE place.

        Nine sites each carried their own default. Grepping is the only thing
        that stops the tenth from being added.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        offenders = []
        for path in root.rglob("*.py"):
            for i, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if "groq/compound" not in line:
                    continue
                # A comment explaining the outage is fine; a live default is not.
                if re.match(r"\s*#", line):
                    continue
                offenders.append(f"{path.relative_to(root.parent)}:{i}: {line.strip()}")
        assert not offenders, (
            "groq/compound is hardcoded outside a comment — route it through "
            "default_groq_model() instead:\n" + "\n".join(offenders)
        )


class TestFusionPanel:
    def test_registry_reads_env_per_call_not_at_import(self, monkeypatch):
        """An env knob read in a module-level dict literal cannot be A/B'd.

        easyhard_ab mutates os.environ in-process for both arms; if the dict was
        already built at import, the branch arm silently runs the baseline model.
        """
        from app.engines.fusion import _panel_registry

        monkeypatch.setenv("REGENOLD_FUSION_MODEL_GROQ", "sentinel-model-a")
        assert _panel_registry()["groq"][0] == "sentinel-model-a"
        monkeypatch.setenv("REGENOLD_FUSION_MODEL_GROQ", "sentinel-model-b")
        assert _panel_registry()["groq"][0] == "sentinel-model-b"

    def test_default_panel_members_are_distinct_models(self, monkeypatch):
        """A panel exists for diversity. Two seats on one model is not a panel."""
        from app.engines.fusion import _DEFAULT_PANEL, _panel_registry

        for var in (
            "REGENOLD_FUSION_MODEL_GROQ",
            "REGENOLD_FUSION_MODEL_SONNET",
            "REGENOLD_GROQ_DEFAULT_MODEL",
        ):
            monkeypatch.delenv(var, raising=False)
        reg = _panel_registry()
        models = [reg[label][0] for label in _DEFAULT_PANEL]
        assert len(set(models)) == len(models), (
            f"default panel collapsed onto duplicate models: {models}"
        )

    def test_judge_is_not_also_a_panel_member(self, monkeypatch):
        """A judge scoring a slate containing its own draft is self-evaluation."""
        from app.engines.fusion import (
            _DEFAULT_JUDGE_MODEL,
            _DEFAULT_PANEL,
            _panel_registry,
        )

        for var in (
            "REGENOLD_FUSION_MODEL_GROQ",
            "REGENOLD_FUSION_MODEL_SONNET",
            "REGENOLD_GROQ_DEFAULT_MODEL",
        ):
            monkeypatch.delenv(var, raising=False)
        reg = _panel_registry()
        panel_models = {reg[label][0] for label in _DEFAULT_PANEL}
        assert _DEFAULT_JUDGE_MODEL not in panel_models, (
            f"judge {_DEFAULT_JUDGE_MODEL!r} is also a panel member — it would "
            "be grading its own draft"
        )

    def test_sonnet_seat_actually_holds_a_sonnet_model(self, monkeypatch):
        """The label is load-bearing: _DEFAULT_PANEL is written in labels."""
        from app.engines.fusion import _panel_registry

        monkeypatch.delenv("REGENOLD_FUSION_MODEL_SONNET", raising=False)
        assert "sonnet" in _panel_registry()["sonnet"][0]


class TestGroqModelSelectorsAreCacheKeyed:
    """R263.2 — a var that picks the model picks the answer.

    R288.1 had just fixed exactly this class for REGENOLD_GROUNDING_REF_CHARS;
    8145be2 reintroduced it three commits later with model-id strings.
    """

    @pytest.mark.parametrize(
        "var",
        [
            "REGENOLD_GROQ_DEFAULT_MODEL",
            "REGENOLD_SYNTHESIS_MODEL_GROQ",
            "REGENOLD_STAGE1_MODEL_GROQ",
            "REGENOLD_STAGE2_MODEL_GROQ",
            "REGENOLD_INTENT_MODEL_GROQ",
            "REGENOLD_DENOISER_MODEL_GROQ",
            "REGENOLD_GENERAL_MODEL_GROQ",
            "REGENOLD_SAFETY_MODEL_GROQ",
            "REGENOLD_FUSION_MODEL_GROQ",
            "REGENOLD_FUSION_MODEL_SONNET",
        ],
    )
    def test_model_selector_changes_the_engine_cache_key(self, monkeypatch, var):
        from app.routes import regenold as R

        monkeypatch.setenv(var, "model-arm-a")
        a = R._engine_cache_key("q", None)
        monkeypatch.setenv(var, "model-arm-b")
        b = R._engine_cache_key("q", None)
        assert a != b, (
            f"{var} selects a model but does not key the cache — an in-process "
            "A/B would serve arm A's answer to arm B"
        )
