"""R442 — Opus 5.5 as a Stage-2 model option over the tunnel.

Selecting it is one env var, ``P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-5-5``
(fresh env read, already in ``_engine_cache_key``): the complex-tier model also
wins on the standard Stage-2 path, so it routes EVERY Stage-2 answer call.

What these tests pin, all by capturing the request at the provider seam rather
than by reading source:

* the id reaches the wire verbatim — the R300 alias table never downgrades it,
  and the R139 Opus floor admits it;
* the Stage-1 parse stays on the base model (no Opus/thinking tax there);
* ``effective_stage2_model()`` — the one routing rule — agrees with what the
  engine actually sends, in every regime (default, Opus 5.5, empty override,
  non-Opus override that the floor must correct);
* the eval preflight probes THAT model, per arm. It used to read
  ``GraphRAGSettings().stage2_model`` alone and run once before any arm env was
  applied, so a model A/B preflighted ``claude-opus-5`` and never the branch
  arm's model. (MEASURED 2026-09-23: Claude Code 2.1.269 answers a
  ``claude-opus-5-5`` request with ``400 ... version 2.1.280 or newer is
  required`` — exactly the failure a preflight exists to catch before a run.)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.engines._graph_rag_impl import (
    _openai_wrapper_complete_for_graph_rag,
    effective_stage2_model,
)
from app.llm import openai_wrapper_provider as _wp
from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    OpenAIWrapperResponse,
    resolve_wrapper_model,
)

OPUS_55 = "claude-opus-5-5"


@pytest.fixture
def captured_requests():
    """Replace the wrapper singleton; collect every request the engine sends."""
    sent: list[OpenAIWrapperRequest] = []
    provider = MagicMock()

    def _complete(req: OpenAIWrapperRequest) -> OpenAIWrapperResponse:
        sent.append(req)
        return OpenAIWrapperResponse(text="ok.", model=req.model)

    provider.complete = MagicMock(side_effect=_complete)
    with patch(
        "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
        return_value=provider,
    ):
        yield sent


def _call(*, stage_name: str, complex_question: bool) -> None:
    _openai_wrapper_complete_for_graph_rag(
        system="you are an EU AI Act expert",
        user="Does Article 50 apply to a customer-service chatbot?",
        max_tokens=400,
        temperature=0.0,
        complex_question=complex_question,
        stage_name=stage_name,
    )


class TestWireModelId:
    def test_opus55_is_sent_verbatim_with_the_alias_table_off(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "0")
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        assert resolve_wrapper_model(OPUS_55) == OPUS_55

    def test_the_legacy_alias_table_does_not_downgrade_opus55(self, monkeypatch):
        """The R300 table rewrites Opus 5 / 4.8 to 4.6 when switched on; a
        newer id must not be silently caught by that rollback switch."""
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "1")
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        assert resolve_wrapper_model(OPUS_55) == OPUS_55
        # Two-sided: the switch is genuinely on for the ids it does cover.
        assert resolve_wrapper_model("claude-opus-5") == "claude-opus-4-6"

    def test_a_namespaced_transport_gets_the_namespaced_id(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")
        assert resolve_wrapper_model(OPUS_55) == f"anthropic/{OPUS_55}"


class TestStage2Routing:
    def test_standard_and_complex_stage2_both_route_to_opus55(
        self, captured_requests, monkeypatch
    ):
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", OPUS_55)
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "0")
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        _call(stage_name="Stage 2 polish", complex_question=False)
        _call(stage_name="Stage 2 polish", complex_question=True)
        assert [r.model for r in captured_requests] == [OPUS_55, OPUS_55]
        # The complex tier keeps its extended-thinking header on the new model.
        assert captured_requests[1].extra_headers.get("X-Claude-Max-Thinking-Tokens")

    def test_stage1_parse_stays_on_the_base_model(self, captured_requests, monkeypatch):
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", OPUS_55)
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "0")
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        _call(stage_name="Stage 1 parse", complex_question=False)
        assert [r.model for r in captured_requests] == [settings.graph_rag.model]
        assert captured_requests[0].extra_headers == {}

    @pytest.mark.parametrize(
        ("override", "expected"),
        [
            (None, None),  # unset: the settings default governs
            (OPUS_55, OPUS_55),
            ("", "stage2"),  # explicit empty disables the swap
            ("claude-sonnet-5", "claude-opus-4-8"),  # R139 Opus floor
        ],
    )
    def test_effective_stage2_model_matches_what_the_engine_sends(
        self, captured_requests, monkeypatch, override, expected
    ):
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "0")
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        if override is None:
            monkeypatch.delenv("P2P_GRAPH_RAG_COMPLEX_MODEL", raising=False)
            expected = settings.graph_rag.complex_model or settings.graph_rag.stage2_model
        else:
            monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", override)
        if expected == "stage2":
            expected = settings.graph_rag.stage2_model
        _call(stage_name="Stage 2 polish", complex_question=False)
        assert captured_requests[-1].model == expected
        assert effective_stage2_model() == expected


class TestPreflightProbesTheArmModel:
    """The live-run preflight must probe the model the engine will send."""

    @pytest.fixture
    def guard(self, monkeypatch):
        from evals.regenold import run_official_batch as rob

        probes: list[str] = []
        provider = MagicMock()

        def _complete(req: OpenAIWrapperRequest) -> OpenAIWrapperResponse:
            probes.append(req.model)
            return OpenAIWrapperResponse(text="alive", model=req.model)

        provider.complete = MagicMock(side_effect=_complete)
        provider._base_url = "http://127.0.0.1:9/v1"
        # The installer loads the repo .env and patches the provider CLASS;
        # keep both out of the rest of the session.
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        monkeypatch.setattr(
            _wp._OpenAIWrapperProvider, "complete", _wp._OpenAIWrapperProvider.complete
        )
        monkeypatch.setattr(_wp, "get_openai_wrapper_provider", lambda: provider)
        monkeypatch.setattr(_wp, "is_openai_wrapper_enabled", lambda: True)
        monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "0")
        monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
        preflight, _ = rob._install_stage2_transport_guard()
        return preflight, probes

    def test_probe_names_the_overridden_model(self, guard, monkeypatch):
        preflight, probes = guard
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", OPUS_55)
        assert preflight() == OPUS_55
        assert probes == [OPUS_55]

    def test_each_distinct_arm_model_is_probed_once(self, guard, monkeypatch):
        """An A/B on the model preflights BOTH arms' models, and re-entering an
        arm whose model was already proven costs no second live call."""
        preflight, probes = guard
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "claude-opus-5")
        preflight()
        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", OPUS_55)
        preflight()
        preflight()
        assert probes == ["claude-opus-5", OPUS_55]

    def test_arm_runs_the_preflight_under_its_own_env(self, monkeypatch, tmp_path):
        """``_arm`` applies the arm env BEFORE probing, then restores it."""
        from evals.regenold import run_official_batch as rob

        seen: list[str | None] = []

        def fake_preflight() -> str:
            import os

            seen.append(os.environ.get("P2P_GRAPH_RAG_COMPLEX_MODEL"))
            raise RuntimeError("stop after the probe")

        monkeypatch.delenv("P2P_GRAPH_RAG_COMPLEX_MODEL", raising=False)
        monkeypatch.setattr(rob, "_RESULTS", tmp_path)
        with pytest.raises(RuntimeError, match="stop after the probe"):
            rob._arm(
                "r442-test", "easy", [],
                poster=None, url="local://x", api_key=None, timeout=1.0,
                arm_env={"P2P_GRAPH_RAG_COMPLEX_MODEL": OPUS_55}, suffix="-B",
                preflight=fake_preflight,
            )
        assert seen == [OPUS_55]
        import os

        assert os.environ.get("P2P_GRAPH_RAG_COMPLEX_MODEL") is None
