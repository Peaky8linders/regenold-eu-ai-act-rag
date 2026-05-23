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
    max_tokens: int = 512
    """Stage-1/2 polish output token cap. R80.2 default 512 (was 1024).
    A wire-normalised 3-sentence answer is ~150-200 tokens typical, 400
    worst-case. Trimming the ceiling cuts the worst-case Sonnet
    generation tail in the r80-stage2-tunnel run (p95 42s, max 87s)
    without affecting typical answers. Operators wanting larger answers
    can override with ``P2P_GRAPH_RAG_MAX_TOKENS=1024``."""

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

    complex_thinking_tokens: int = 1024
    """``max_thinking_tokens`` for extended-thinking Stage-2 polish on
    complex questions.

    R80.2 — reduced 2500 → 1024 (the engine clamp floor). The
    r80-stage2-tunnel run still showed an 87 s max-latency outlier
    driven by the Opus complex extended-thinking path. Trimming to
    the floor preserves the structured-reasoning win on conflict /
    borderline-prohibition rows (r69-live conflict refS 0.95,
    borderline refL 1.0) while cutting worst-case thinking time
    further (~2.5× since R69's 2500). Clamped at the engine to
    [1024, 16000]; 0 disables thinking. Override per-deploy via
    ``P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS``.

    Prior values:
      * R51 original: 8000 (Anthropic's then-default extended-think
        budget). Measured a 103 s worst-case tr_v2_007 outlier on
        r69-live + p95 35 s.
      * R69 round-2: reduced 8000 → 2500.
      * R80.2: reduced 2500 → 1024 (current).
    """


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
