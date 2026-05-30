# R97 — Adaptive LLM routing for multi-turn / nuanced questions

## Problem (user directive, 2026-05-30)

Production is effectively **deterministic + verbatim** since R94/R96. The
Claude Max wrapper + Sonnet is barely used (only Groq Stage-0 intent). R96
blanket-disabled Stage-2 polish whenever `REGENOLD_VERBATIM_ANSWER` is ON
(default), because under verbatim the route REPLACES the answer with
verbatim EUR-Lex provision text — so any Stage-2 prose was discarded.

That coupling is **correct for simple single-turn QA** ("What does Article
13 require?" → quote Art. 13 verbatim) but **wrong for multi-turn nuanced
conversations**: a verbatim provision dump cannot synthesise across turns
("does the regulator you mentioned require X?", role flips, conflict
reconciliation, cross-framework). The LLM-supercharged path adds the most
value exactly where R96 turned it off.

## Goal

Use the **LLM (Sonnet via Claude Max wrapper) for multi-turn + genuinely
nuanced questions**, and the **fast deterministic verbatim path only when it
suffices** (simple single-turn factual / definitional QA). Optimise the
intent detection that makes this routing decision. Benchmark multi-turn
conversations with an LLM-as-judge to prove it.

## Design

### 1. `app/engines/answer_router.py` (new) — single routing source of truth
`AnswerMode = {VERBATIM, SYNTHESIS}`.
`select_answer_mode(question, history_turn_count, query) -> RouteDecision`
returns SYNTHESIS when ANY of:
- **multi-turn** — `"Conversation so far:"` in the flattened question OR
  `history_turn_count >= 2` (≥1 prior user+assistant pair). Verbatim dump
  can't synthesise across turns — this is the user's primary concern.
- **nuanced single-turn** — `is_complex_question(...)` fires (conflict,
  role-ambiguity, cross-framework, borderline-prohibition, GPAI boundary).
- **synthesis intent** — `query.intent in {gap_analysis, cross_framework}`.
Else VERBATIM. Pure-stdlib, fail-soft (returns VERBATIM on any exception →
safe default = deterministic). Carries a short `reason` for telemetry.

### 2. `graph_rag.py` — decouple verbatim from Stage-2; route via the router
- `_stage2_polish_enabled()` reverts to **pure** `P2P_GRAPH_RAG_ENABLE_STAGE2`
  semantics (drop the R96 verbatim coupling).
- `_two_stage_generate` gate sequence:
  1. classification-topic short-circuit (unchanged — curated verdict).
  2. `_stage2_polish_enabled()` (master env, no verbatim coupling).
  3. `_stage2_provider_enabled()` (provider wired — **this keeps davidath
     byte-identical**: CI/local bench has no wrapper → no Stage-2).
  4. **routing**: when verbatim ON → Stage-2 fires iff
     `select_answer_mode(...) == SYNTHESIS` (and `REGENOLD_ANSWER_ROUTER`
     is on; `=0` restores exact R96 behaviour = the A/B baseline). When
     verbatim OFF → preserve the historical `_needs_stage2_enhancement`
     gate byte-for-byte.
  5. confidence gate — **router-aware**: multi-turn synthesis uses a lower
     floor (`REGENOLD_STAGE2_MIN_CONFIDENCE_MULTITURN`, default 0.3) since
     coreferent follow-ups retrieve sparsely; single-turn keeps 0.5.

### 3. `routes/regenold.py` — skip verbatim overwrite when Stage-2 landed
The verbatim replacement block gains `and not _stage2_landed`. When Stage-2
synthesised the answer (multi-turn/nuanced), keep it; when Stage-2 was
skipped or fell back (drift / contradiction / wrapper failure), verbatim
applies as the safe deterministic fallback. `_stage2_landed` read from
`rag_res.graph_stats["stage2_landed"]` (already exported R72.1).

### 4. Cache key — R79 doctrine
`_engine_cache_key` folds in `REGENOLD_ANSWER_ROUTER`,
`REGENOLD_VERBATIM_ANSWER`, `REGENOLD_STAGE2_MIN_CONFIDENCE_MULTITURN`
(these now flip engine output). `P2P_GRAPH_RAG_ENABLE_STAGE2` already there.

### 5. Telemetry
Record `answer_mode` + `route_reason` into the ReasoningTrace + graph_stats
so the judge / benchmark can correlate "routed to Sonnet" with quality.

## Benchmark (multi-turn, LLM-as-judge, wrapper)

Per project rule: evals MUST go through the Claude Max wrapper (127.0.0.1:8000),
not the Anthropic SDK direct. A/B is valid because the baseline run has
Sonnet OFF (deterministic) — we never diff two Sonnet runs against each other.

- **A (R96 baseline)**: `REGENOLD_ANSWER_ROUTER=0` → verbatim-only, no Sonnet.
- **B (new routing)**: `REGENOLD_ANSWER_ROUTER=1` → Sonnet on multi-turn/nuanced.

Harness: `evals/regenold/multiturn_ab.py` runs the V2 (25) + extended (100)
multi-turn scenarios via in-process TestClient with the wrapper env active,
both modes, reports coherence + per-axis judge pass rates + latency, writes a
comparison sidecar. Coherence = runner_v2 formula (ref_loose>0 ∧ kw≥0.5 ∧
not-refusal ∧ no-error). Judge = `evals.judge.runner --provider wrapper`.

## Regression guards (must hold)
- `pytest -q` green (+new R97 tests; R96 tests rewritten to new contract).
- `evals.bench.runner` davidath byte-identical (no wrapper → no Stage-2).
- `evals.regenold.runner` 276/276; `runner_v2 --local --probe-oos` 21/21.

## Reversibility
`REGENOLD_ANSWER_ROUTER=0` → exact R96 behaviour. Every knob env-gated.
