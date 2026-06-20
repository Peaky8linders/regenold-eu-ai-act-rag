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
    """Stage-1 PARSE model (JSON entity extraction) AND the base model for any
    non-Stage-2 LLM call. Default Sonnet 4.6 — fast, cheap, and it must NEVER
    pay an Opus latency tax or a thinking budget (the parse is a strict-schema
    JSON call; extended thinking there only risks corrupting the JSON). The
    Stage-2 ANSWER is governed by :attr:`stage2_model`, not this field."""

    stage2_model: str = "claude-opus-4-8"
    """R139 (operator directive 2026-06-20) — model for the Stage-2 ANSWER
    (the user-facing legal prose), used on EVERY Stage-2 polish/synthesis call
    regardless of question complexity. Default ``claude-opus-4-8``: Opus 4.8 is
    the stronger legal reasoner and produces verdict-first, professionally-toned
    answers where Sonnet 4.6 buried the bottom line (the medtech "is X high
    risk?" → "Article 6(1) read with Annex I is the operative provision…"
    regression that motivated this round). Empty → fall back to :attr:`model`
    for Stage-2 (the pre-R139 behaviour: Sonnet standard / Opus complex).

    Cost is flat on the production Claude Max subscription (the wrapper bills
    the Max plan, not per token), so "always Opus" carries no marginal token
    cost there; the trade is latency (Opus is slower than Sonnet), mitigated by
    :attr:`thinking_tokens` (a MODERATE budget on the ~80% simple questions) vs
    :attr:`complex_thinking_tokens` (EXTENDED only on the ~20% complex ones).
    Override per-deploy with ``P2P_GRAPH_RAG_STAGE2_MODEL``."""

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
    # R103 (2026-06-01): default = claude-opus-4-8, extended thinking
    # OFF (complex_thinking_tokens=0). R131.2 (2026-06-19) re-enables a
    # MODEST 1024-token thinking budget (operator directive — surface real
    # model reasoning in the reasoning trace / UI; see the field docstring).
    # The R81-A1 latency disaster (16 s p50, 51 s outlier) was the
    # 8000-token extended-thinking budget, NOT the model swap or a modest
    # budget; Opus 4.8 as a (stronger) model swap lifts the hard reasoning categories
    # (conflict / borderline-prohibition / GPAI thresholds / multi-turn
    # coreference, the ~20% the complexity gate fires on) without the
    # thinking-budget tail.
    #
    # R116 (2026-06-13): the experimental Fable 5 ``ultra_complex``
    # tier was removed per operator directive -- keep only Sonnet 4.6
    # (base) and Opus 4.8 (complex). It was already effectively dead
    # (its model selection re-checked is_ultra_complex_question(user, 1)
    # with history=1, which can never satisfy the history>=3 gate), so
    # removal is wire-neutral.
    #
    # Operator overrides (per-deploy): set
    # ``P2P_GRAPH_RAG_COMPLEX_MODEL=`` (empty) to disable the swap and
    # keep every Stage-2 call on Sonnet, or point it at another model.
    complex_model: str = "claude-opus-4-8"
    """Model name for the complex-question path. Default:
    ``claude-opus-4-8``. Set empty to disable the swap (every Stage-2
    polish call uses the base ``model``)."""

    complex_thinking_tokens: int = 4000
    """``max_thinking_tokens`` — the **EXTENDED** thinking budget for the
    ~20% of questions :func:`app.engines.question_complexity.is_complex_question`
    flags (conflict / borderline-prohibition / GPAI thresholds / role-ambiguity
    / multi-turn coreference, plus the R118 widened difficulty set).

    **R139 — default 4000 (extended thinking on COMPLEX questions).** Per the
    operator directive, the complex tier gets a genuinely extended budget so
    Opus 4.8 deliberates before committing on the hard legal-reasoning cases;
    the latency cost lands ONLY on the complex ~20% (the user accepts latency
    there). 4000 is a deliberate middle ground: clearly extended vs the 1024
    MODERATE budget on simple questions, yet well below the 8000-token budget
    that drove the R51 / r80.2-live 103 s latency outlier. Clamped at the
    engine to [1024, 16000]; ``0`` disables. The answer gets ``budget + 512``
    output-token headroom above the thinking allocation. Override per-deploy
    with ``P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS``.

    **R131.2 — default 1024 (extended thinking ON, modest).** Operator
    directive: surface REAL model reasoning in the ``?include_reasoning=true``
    trace's ``llm_thinking`` field + the UI 🧠 panel (it otherwise shows the
    ``"Single-pass synthesis (no extended thinking)"`` placeholder). 1024 is
    the engine clamp floor — the smallest budget that produces visible
    reasoning, and the proven R80.2 production value — fired ONLY on the
    ~20% complex/Opus path (the standard Sonnet path stays thinking-free /
    fast). Latency trade: ~+5-15 s on complex questions only (a scored axis);
    fully reversible per-deploy with ``P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS=0``
    to restore the R103 fast placeholder. The R81-A1 / r80.2-live latency
    disaster (16 s p50, 51 s outlier) was the **8000**-token budget, not a
    modest one.

    **R103 (superseded by R131.2) — default 0 (extended thinking OFF).** The
    complex path swaps to Opus 4.8 as a plain (stronger) model; 0 means no
    ``X-Claude-Max-Thinking-Tokens`` header is sent, so Opus 4.8 answers at
    ~Sonnet latency.

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

    thinking_tokens: int = 1024
    """``max_thinking_tokens`` — the **MODERATE** thinking budget for the
    STANDARD Stage-2 synthesis path: the ~80% of questions the complexity gate
    does NOT flag. As of R139 these run on Opus 4.8 (:attr:`stage2_model`), not
    Sonnet.

    **R139 — default 1024 (MODERATE, latency-conscious).** With Opus 4.8 now on
    every Stage-2 answer, the simple-question path is the 80% that dominates
    latency, so its thinking budget is kept at the engine floor (1024) "so the
    latency is not impacted" (operator directive). Complex questions get the
    larger :attr:`complex_thinking_tokens` (EXTENDED) instead. Lowered from the
    R138 value of 2048 because that was tuned for the faster Sonnet standard
    path; on Opus the moderate 1024 keeps simple-question latency bounded.
    Clamped at the engine to [1024, 16000]; ``0`` the fast thinking-free path.
    Override per-deploy with ``P2P_GRAPH_RAG_THINKING_TOKENS``.

    **R138 (operator directive) — default 2048 (doubled from R135's 1024).**
    The operator asked to double Sonnet 4.6's standard-path extended-thinking
    budget "to get better answers" — more deliberation before the
    bottom-line-up-front verdict + grounded explanation, especially on
    concrete use-case / application / system classification questions. The
    engine gives the answer ``budget + 512`` tokens of output headroom above
    the thinking allocation (``safe_max_tokens``), so 2048 leaves ample room
    for a complete multi-part answer (also helps the R118 multi-part
    truncation). Latency trade: ~+5-12 s per standard Stage-2 call (a scored
    axis); the R81-A1 / r80.2-live latency disaster was the **8000**-token
    budget, not a modest one. Fully reversible per-deploy:
    ``P2P_GRAPH_RAG_THINKING_TOKENS=1024`` restores the R135 value, ``=0``
    the fast thinking-free path. Clamped at the engine to [1024, 16000]; 0
    disables.

    **R135 — default 1024 (Sonnet 4.6 ALSO thinks).** Previously only the
    complex/Opus path used extended thinking (``complex_thinking_tokens``);
    the standard Sonnet path ran thinking-free. The directive: Sonnet should
    reason before answering, not just Opus on the hard ~20%. The model thinks
    (improving the answer) whether or not the wrapper surfaces the reasoning
    text in ``reasoning.llm_thinking`` (surfacing the text needs the
    wrapper-repo patch — see project memory). Applied to Stage-2 ONLY (never
    the Stage-1 parse / JSON entity-extraction call).
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

    version: str = "1.0.0"


settings = AppSettings()
