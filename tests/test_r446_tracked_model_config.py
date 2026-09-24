"""R446 — the Stage-2 model is updateable without an environment variable.

The model ids ship from the tracked ``app/data/model_config.json``. Precedence,
highest first: env var > tracked file > ``GraphRAGSettings`` field default.

    P2P_GRAPH_RAG_<FIELD> set? ── yes ──> env value (per-deploy override)
            │ no
            ▼
    model_config.json has key? ── yes ──> tracked value (edit + merge to change)
            │ no / file missing / malformed (warning logged)
            ▼
    GraphRAGSettings field default

The route-level test asserts on the request the engine actually builds for the
wrapper, not on the source, so an inert layer cannot pass.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app.config as config_module
from app.config import GraphRAGSettings, load_tracked_model_config
from app.llm.openai_wrapper_provider import OpenAIWrapperRequest, OpenAIWrapperResponse

MODEL_ENV_VARS = (
    "P2P_GRAPH_RAG_MODEL",
    "P2P_GRAPH_RAG_STAGE2_MODEL",
    "P2P_GRAPH_RAG_COMPLEX_MODEL",
)


@pytest.fixture
def _no_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MODEL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _write_config(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "model_config.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


def _field_default(name: str) -> str:
    return GraphRAGSettings.model_fields[name].default


class TestTrackedFile:
    def test_shipped_file_parses_and_selects_opus_5_5(self) -> None:
        tracked = load_tracked_model_config()
        assert set(tracked) == {"model", "stage2_model", "complex_model"}
        assert tracked["stage2_model"] == "claude-opus-5-5"
        assert tracked["complex_model"] == "claude-opus-5-5"
        assert all(value.startswith("claude-") for value in tracked.values())

    def test_missing_file_yields_nothing(self, tmp_path: Path) -> None:
        assert load_tracked_model_config(tmp_path / "absent.json") == {}

    def test_malformed_file_is_fail_soft(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write_config(tmp_path, "{not json")
        with caplog.at_level(logging.WARNING, logger="app.config"):
            assert load_tracked_model_config(path) == {}
        assert "model_config" in caplog.text

    def test_non_object_json_is_fail_soft(self, tmp_path: Path) -> None:
        assert load_tracked_model_config(_write_config(tmp_path, ["claude-opus-5-5"])) == {}

    def test_only_model_fields_are_read(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path,
            {
                "_comment": ["ignored"],
                "stage2_model": 5,
                "api_key": "sk-must-never-come-from-this-file",
                "max_tokens": 99,
                "complex_model": "  claude-opus-5-5  ",
            },
        )
        assert load_tracked_model_config(path) == {"complex_model": "claude-opus-5-5"}

    def test_empty_complex_model_is_kept_because_it_disables_the_swap(
        self, tmp_path: Path
    ) -> None:
        path = _write_config(tmp_path, {"complex_model": ""})
        assert load_tracked_model_config(path) == {"complex_model": ""}


@pytest.mark.usefixtures("_no_model_env")
class TestPrecedence:
    def test_tracked_file_applies_without_any_env_var(self) -> None:
        built = GraphRAGSettings()
        tracked = load_tracked_model_config()
        assert built.stage2_model == tracked["stage2_model"]
        assert built.complex_model == tracked["complex_model"]
        assert built.model == tracked["model"]

    def test_tracked_file_beats_the_field_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _write_config(tmp_path, {"stage2_model": "claude-opus-4-8"})
        monkeypatch.setattr(config_module, "MODEL_CONFIG_PATH", path)
        assert GraphRAGSettings().stage2_model == "claude-opus-4-8"
        # keys the file omits keep their field default
        assert GraphRAGSettings().complex_model == _field_default("complex_model")

    def test_missing_file_falls_back_to_field_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config_module, "MODEL_CONFIG_PATH", tmp_path / "absent.json")
        built = GraphRAGSettings()
        assert built.stage2_model == _field_default("stage2_model")
        assert built.complex_model == _field_default("complex_model")

    def test_malformed_file_never_blocks_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config_module, "MODEL_CONFIG_PATH", _write_config(tmp_path, "{"))
        assert GraphRAGSettings().stage2_model == _field_default("stage2_model")

    @pytest.mark.parametrize(
        ("env_name", "field_name"),
        [
            ("P2P_GRAPH_RAG_STAGE2_MODEL", "stage2_model"),
            ("P2P_GRAPH_RAG_COMPLEX_MODEL", "complex_model"),
            ("P2P_GRAPH_RAG_MODEL", "model"),
        ],
    )
    def test_env_var_beats_the_tracked_file(
        self, monkeypatch: pytest.MonkeyPatch, env_name: str, field_name: str
    ) -> None:
        monkeypatch.setenv(env_name, "claude-opus-4-8")
        assert getattr(GraphRAGSettings(), field_name) == "claude-opus-4-8"

    def test_explicit_empty_env_still_disables_the_complex_swap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.engines._graph_rag_impl import _resolve_complex_model

        monkeypatch.setenv("P2P_GRAPH_RAG_COMPLEX_MODEL", "")
        assert _resolve_complex_model() == ""


@pytest.mark.usefixtures("_no_model_env")
class TestWire:
    """The engine's wrapper request and the eval preflight both see Opus 5.5."""

    @pytest.fixture
    def _wrapper(self):
        provider = MagicMock()
        provider.complete = MagicMock(
            return_value=OpenAIWrapperResponse(text="ok.", model="claude-opus-5-5")
        )
        with patch(
            "app.llm.openai_wrapper_provider.get_openai_wrapper_provider",
            return_value=provider,
        ):
            yield provider

    @pytest.mark.parametrize("complex_question", [False, True])
    def test_stage2_request_carries_the_tracked_model(
        self, _wrapper: MagicMock, complex_question: bool
    ) -> None:
        from app.engines.graph_rag import _openai_wrapper_complete_for_graph_rag

        _openai_wrapper_complete_for_graph_rag(
            system="x",
            user="Is a medtech system that tracks patient weight high risk?",
            max_tokens=400,
            temperature=0.0,
            complex_question=complex_question,
            stage_name="Stage 2 (Polishing)",
        )
        assert _wrapper.complete.call_count == 1
        request: OpenAIWrapperRequest = _wrapper.complete.call_args.args[0]
        assert request.model == "claude-opus-5-5"

    def test_preflight_probes_the_tracked_model(self) -> None:
        from app.engines._graph_rag_impl import effective_stage2_model

        assert effective_stage2_model() == "claude-opus-5-5"
        assert effective_stage2_model(complex_question=True) == "claude-opus-5-5"

    def test_healthz_llm_probes_the_stage2_model_not_the_auxiliary_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R446 — /healthz/llm probed ``settings.graph_rag.model`` (Sonnet 5, the
        auxiliary model) while every answer went to Opus 5.5."""
        import httpx
        from fastapi.testclient import TestClient

        from app.llm import openai_wrapper_provider
        from app.main import app

        for name in (
            "REGENOLD_HEALTHZ_PROBE_MODEL",
            "REGENOLD_WRAPPER_MODEL_PREFIX",
            "P2P_GRAPH_RAG_API_KEY",
            "AWS_BEARER_TOKEN_BEDROCK",
            "AWS_BEDROCK_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
        monkeypatch.setenv("OPENAI_API_BASE", "https://api.test.invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "dummy")

        sent: list[str] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            model = json.loads(request.content)["model"]
            sent.append(model)
            return httpx.Response(
                200,
                json={
                    "id": "probe",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "OK"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                },
            )

        openai_wrapper_provider._SINGLETON = None
        provider = openai_wrapper_provider.get_openai_wrapper_provider()
        provider._client = httpx.Client(
            transport=httpx.MockTransport(_handler), base_url="https://api.test.invalid"
        )
        try:
            body = TestClient(app).get("/healthz/llm").json()
        finally:
            openai_wrapper_provider._SINGLETON = None

        assert sent == ["claude-opus-5-5"]
        assert body["llm_ok"] is True
        assert body["model"] == "claude-opus-5-5"
