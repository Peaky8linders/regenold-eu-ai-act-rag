"""R432 — safe alternate-transport recovery and cache identity."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm.openai_wrapper_provider import (
    resolve_wrapper_model,
    wrapper_model_prefix,
)

REPO = Path(__file__).resolve().parents[1]
PREFLIGHT_SRC = (REPO / "evals/regenold/run_official_batch.py").read_text(
    encoding="utf-8"
)


@pytest.fixture(autouse=True)
def _no_ambient_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test states its own prefix; none inherits the operator's."""
    monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_PREFIX", raising=False)
    monkeypatch.delenv("REGENOLD_WRAPPER_MODEL_ALIAS", raising=False)


def test_absent_prefix_is_a_true_noop() -> None:
    """The default deployment must be byte-identical to pre-R432."""
    assert wrapper_model_prefix() == ""
    for name in ("claude-opus-5", "claude-sonnet-5", "llama-3.3-70b-versatile"):
        assert resolve_wrapper_model(name) == name


def test_prefix_namespaces_the_claude_models_the_app_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")
    assert resolve_wrapper_model("claude-opus-5") == "anthropic/claude-opus-5"
    assert resolve_wrapper_model("claude-sonnet-5") == "anthropic/claude-sonnet-5"


def test_prefix_never_touches_a_non_claude_provider_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generic provider is reused for Groq / Gemini / Mistral."""
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")
    for name in (
        "llama-3.3-70b-versatile",
        "qwen/qwen3-235b-a22b-2507",
        "gemini-2.5-flash",
        "openai/gpt-oss-120b",
    ):
        assert resolve_wrapper_model(name) == name


def test_prefix_is_idempotent_and_tolerates_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")
    assert (
        resolve_wrapper_model("anthropic/claude-opus-5")
        == "anthropic/claude-opus-5"
    )
    assert resolve_wrapper_model("") == ""
    assert resolve_wrapper_model("   ") == ""


def test_prefix_wins_over_the_alias_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alias targets are for the Claude wrapper; do not compose them with a
    different vendor namespace."""
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_PREFIX", "anthropic/")
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "1")
    assert resolve_wrapper_model("claude-opus-5") == "anthropic/claude-opus-5"


def test_alias_table_still_works_without_a_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGENOLD_WRAPPER_MODEL_ALIAS", "1")
    assert resolve_wrapper_model("claude-opus-5") == "claude-opus-4-6"


def test_preflight_probes_the_configured_stage2_model() -> None:
    """The probe must name the model the run will actually send."""
    body = PREFLIGHT_SRC.split("def preflight() -> str:", 1)[1].split(
        "original_complete =", 1
    )[0]
    assert "GraphRAGSettings" in body
    assert "stage2_model" in body


def test_transport_destination_changes_cache_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude Max, an alternate provider, and a dead host cannot share a
    cached response even when every REGENOLD flag is unchanged."""
    from app.routes.regenold import _engine_cache_key

    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    monkeypatch.setenv("OPENAI_API_BASE", "https://wrapper.antifragile-ai.net/v1")
    wrapper_key = _engine_cache_key("What is Article 6?", None)
    monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    alternate_key = _engine_cache_key("What is Article 6?", None)
    assert wrapper_key != alternate_key
