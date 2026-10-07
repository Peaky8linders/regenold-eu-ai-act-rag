"""The sampling-parameter allow-list: Claude Sonnet 5.5, in every spelling, and nothing else.

The predicate removes ``temperature`` from a request, so a false positive silently
changes a payload and a false negative is a 400. Both directions are pinned here,
including the models that SHIP today (``claude-opus-5-5`` Stage-2, ``claude-sonnet-5``
Stage-1), which must keep sending temperature.
"""
from __future__ import annotations

import pytest

from app.llm.model_compatibility import rejects_sampling_parameters


@pytest.mark.parametrize(
    "model",
    [
        # bare first-party id
        "claude-sonnet-5-5",
        "Claude-Sonnet-5-5",
        "  claude-sonnet-5-5  ",
        # vendor-namespaced (REGENOLD_WRAPPER_MODEL_PREFIX, R432) and the dotted
        # spelling namespaced catalogues use
        "anthropic/claude-sonnet-5-5",
        "anthropic/claude-sonnet-5.5",
        "anthropic/claude-sonnet-5.5:thinking",
        "openrouter/anthropic/claude-sonnet-5-5",
        # dated / versioned snapshots
        "claude-sonnet-5-5-20260901",
        "claude-sonnet-5-5@20260901",
        # Bedrock inference-profile ids, every geography, with and without a version
        "anthropic.claude-sonnet-5-5-v1:0",
        "eu.anthropic.claude-sonnet-5-5",
        "eu.anthropic.claude-sonnet-5-5-v1:0",
        "us.anthropic.claude-sonnet-5-5-v2:0",
        "global.anthropic.claude-sonnet-5-5-v1:0",
        "apac.anthropic.claude-sonnet-5-5-v1:0",
        "arn:aws:bedrock:eu-central-1:111122223333:inference-profile/eu.anthropic.claude-sonnet-5-5-v1:0",
    ],
)
def test_sonnet_55_model_ids_reject_explicit_sampling_parameters(model: str) -> None:
    assert rejects_sampling_parameters(model) is True


@pytest.mark.parametrize(
    "model",
    [
        # the models that SHIP: Stage-2 (model_config.json) and Stage-1 / auxiliary
        "claude-opus-5-5",
        "anthropic/claude-opus-5-5",
        "claude-sonnet-5",
        "anthropic/claude-sonnet-5",
        "eu.anthropic.claude-sonnet-5",
        # neighbours in the same family
        "claude-sonnet-4-6",
        "claude-sonnet-4.6",
        "claude-opus-5",
        "claude-opus-4-8",
        "eu.anthropic.claude-opus-4-8",
        "claude-fable-5-1",
        "claude-haiku-4-5-20251001",
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        # a later release must not inherit the entry through a shared prefix
        "claude-sonnet-5-50",
        "claude-sonnet-5-6",
        "claude-sonnet-5.50",
        # the other vendors this provider class is reused for
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
        "qwen.qwen3-32b-v1:0",
        "gemini-2.5-flash",
        "mistral-large-latest",
        # degenerate input
        "",
        "   ",
        None,
    ],
)
def test_other_models_keep_existing_sampling_behavior(model: str | None) -> None:
    assert rejects_sampling_parameters(model) is False
