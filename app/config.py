"""Minimal settings module — Regenold + GraphRAG.

Trimmed-down extract of CodexAI's full ``app/config.py``. Only the
sub-settings the Regenold pipeline + Graph-RAG engine actually read are
preserved. Adding new options outside this scope is intentional — keep
this file small so partners auditing the bundle can read it in one pass.
"""
from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GraphRAGSettings(BaseSettings):
    """LLM config for the Graph-RAG engine."""

    model_config = SettingsConfigDict(env_prefix="P2P_GRAPH_RAG_", extra="ignore")

    api_key: SecretStr | None = None
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024
    temperature: float = 0.0

    # R51 — complex-question routing. When a question is classified as
    # ``complex`` (role-ambiguity, GPAI threshold, borderline-prohibition,
    # conflict, or compound multi-turn) AND ``complex_model`` is set, the
    # Stage-2 polish call swaps to that model with optional
    # extended-thinking budget. Defaults keep R50 behaviour byte-identical
    # (no model swap, no thinking).
    #
    # Recommended production setting: complex_model=claude-opus-4-7,
    # complex_thinking_tokens=8000. Cost trade: Opus 4.7 is ~5x Sonnet
    # 4.6 per million tokens, but it only fires on ~20% of bench rows
    # (the tagged-complex ones), and extended thinking adds ~5-15s p50
    # latency only on those rows.
    complex_model: str = "claude-opus-4-7"
    """Model name for the complex-question path. Default ``claude-opus-4-7``
    (R51 production setting). Set empty to disable the swap and keep
    every Stage-2 call on the base ``model``. The wrapper falls back
    to deterministic if Opus is unreachable, so worst case is a soft
    miss, not a 500."""

    complex_thinking_tokens: int = 8000
    """``max_thinking_tokens`` for extended-thinking Stage-2 polish on
    complex questions. Default 8000 (R51 production setting).
    Clamped at the engine to [1024, 16000]. 0 disables thinking.
    Tip: the wrapper enforces a hard 50000 ceiling — we stay well
    below that for cost + latency reasons."""


class RegenoldSettings(BaseSettings):
    """Regenold partner-tier auth + rate-limit settings."""

    model_config = SettingsConfigDict(env_prefix="P2P_REGENOLD_", extra="ignore")

    api_key: SecretStr | None = None
    """Optional. When set, callers with a matching X-Regenold-Api-Key
    header get the privileged 60/min rate-limit bucket.
    """


class RateLimitSettings(BaseSettings):
    """slowapi limiter knobs."""

    model_config = SettingsConfigDict(env_prefix="P2P_RATELIMIT_", extra="ignore")

    storage_uri: str = "memory://"
    default_limit: str = "100/minute"


class AppSettings(BaseSettings):
    """Top-level container — sub-settings are eagerly instantiated."""

    model_config = SettingsConfigDict(env_prefix="P2P_", extra="ignore")

    graph_rag: GraphRAGSettings = Field(default_factory=GraphRAGSettings)
    regenold: RegenoldSettings = Field(default_factory=RegenoldSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

    version: str = "0.1.0"


settings = AppSettings()
