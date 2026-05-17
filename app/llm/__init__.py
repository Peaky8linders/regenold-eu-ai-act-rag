"""LLM provider helpers — provider resolution.

Extracted from CodexAI's ``app/llm/``. The bundle supports three LLM
paths: the deterministic-fallback (``cli``), the Anthropic SDK direct
path, and the local ``openai_wrapper`` (Claude Max via the
``claude-code-openai-wrapper`` facade).
"""
from __future__ import annotations

import os
from typing import Literal


def resolve_provider(
    env_value: str | None,
    *,
    default_when_auto: Literal["anthropic", "cli"] = "anthropic",
) -> str:
    """Resolve the LLM provider for a feature.

    Honours an explicit ``anthropic`` / ``cli`` / ``openai_wrapper``
    setting. On unset / empty / ``auto``, falls back to
    ``default_when_auto`` (``anthropic`` by default).

    ``openai_wrapper`` routes through ``OPENAI_API_BASE`` (default
    ``http://127.0.0.1:8000/v1``) — used by the partner bundle to A/B
    Sonnet 4.6 via the local ``claude-code-openai-wrapper``.
    """
    value = (env_value or "").strip().lower()
    if value in {"anthropic", "cli", "openai_wrapper"}:
        return value
    if value in {"", "auto"}:
        return default_when_auto
    raise ValueError(f"Unsupported provider value: {value!r}")


__all__ = [
    "resolve_provider",
]
