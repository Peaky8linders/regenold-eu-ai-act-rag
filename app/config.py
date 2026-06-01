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
    max_tokens: int = 384
    """Stage-1/2 polish output token cap.

    R84 default 384 (was 512 in R80.2, was 1024 pre-R80.2). The
    ``ANSWER_GENERATE_SYSTEM`` prompt mandates "AT MOST 3 sentences"
    (since R80.1) — a wire-normalised 3-sentence answer is ~150-200
    tokens typical, ~280 worst-case. 384 keeps ~80-token headroom for
    a long 3rd sentence while saving ~2-4 s p95 generation tail vs the
    R80.2 512 cap on the slow Sonnet generation path the R81-A1 live
    rep-100 surfaced. Operators wanting larger answers can override
    with ``P2P_GRAPH_RAG_MAX_TOKENS=512`` (R80.2) or ``=1024`` (pre-R80.2).

    Prior values:
      * pre-R80.2: 1024 (Sonnet default).
      * R80.2: reduced 1024 → 512 (cuts worst-case generation tail).
      * R84: reduced 512 → 384 (further latency trim; zero answer-quality
        risk since the prompt's 3-sentence cap is well under the new
        ceiling)."""

    temperature: float = 0.0

    # R51 — complex-question routing. When a question is classified as
    # ``complex`` (role-ambiguity, GPAI threshold, borderline-prohibition,
    # conflict, or compound multi-turn) AND ``complex_model`` is set, the
    # Stage-2 polish call swaps to that model with optional
    # extended-thinking budget.
    #
    # **R81-A1 reversal (2026-05-23): default flipped to empty.** R51
    # originally set ``claude-opus-4-7`` as the default to win on the
    # structured-reasoning categories (r69-live conflict refS 0.95,
    # borderline refL 1.0 — both above-target). R80.2 trimmed the
    # extended-thinking budget 2500 → 1024 (the engine clamp floor),
    # but the r80.2-live measurement still showed a 51 s max-latency
    # outlier on the Opus complex path with live p50 = 15,962 ms
    # (~16 s, well above the < 6 s R77-R79 target). Disabling the
    # swap as the CODE default keeps every Stage-2 polish call on a
    # single Sonnet 4.6 round-trip — expected live p50 ~5-8 s.
    #
    # Trade: loses the structured-reasoning quality win on the ~20%
    # of rows the complexity gate fires on. The R81 plan flagged
    # this risk as acceptable because latency is also a scored axis
    # and the deterministic + Sonnet polish path is rubric-positive
    # in aggregate.
    #
    # **R103 reversal (2026-06-01): default = ``claude-opus-4-8``, NO
    # extended thinking.** The R81-A1 latency disaster (16 s p50, 51 s
    # outlier) was the 8000→1024-token EXTENDED-THINKING budget, NOT
    # Opus itself. Opus 4.8 (newer + stronger reasoning than the 4.7
    # R51 tried) with ``complex_thinking_tokens=0`` runs as a plain
    # model swap at ~Sonnet latency, lifting the hard reasoning
    # categories (conflict / borderline-prohibition / GPAI thresholds /
    # multi-turn coreference — the ~20% the complexity gate fires on)
    # without the thinking-budget tail. Verified reachable via the Max
    # wrapper (`claude-opus-4-8`, HTTP 200, ~6 s tiny prompt).
    #
    # Operator override (per-deploy): set
    # ``P2P_GRAPH_RAG_COMPLEX_MODEL=`` (empty) to disable the swap and
    # keep every Stage-2 call on Sonnet for cost/latency reasons.
    complex_model: str = "claude-opus-4-8"
    """Model name for the complex-question path. **R103 default**:
    ``claude-opus-4-8`` (no extended thinking — see
    ``complex_thinking_tokens=0``). Set empty to disable the swap
    (every Stage-2 polish call uses the base ``model``). The provider
    falls back to deterministic if the configured complex model is
    unreachable, so worst case is a soft miss, not a 500."""

    complex_thinking_tokens: int = 0
    """``max_thinking_tokens`` for extended-thinking Stage-2 polish on
    complex questions.

    **R103 — default 0 (extended thinking OFF).** The complex path now
    swaps to Opus 4.8 as a plain (stronger) model, NOT an extended-
    thinking run — extended thinking was the sole driver of the
    R81-A1 / r80.2-live 16 s p50 + 51 s outlier latency disaster. 0
    means no ``X-Claude-Max-Thinking-Tokens`` header is sent, so Opus
    4.8 answers at ~Sonnet latency. Re-enable per-deploy with
    ``P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS=2500`` (engine clamps to
    [1024, 16000]) ONLY if a live A/B shows the reasoning lift beats
    the latency cost.

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
