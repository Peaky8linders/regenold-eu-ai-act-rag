# R110 — FRAMES Sufficient-Context bounded multi-hop retrieval

**Date:** 2026-06-08
**Trigger:** Analysis of a LinkedIn critique of agentic RAG + a deep-research
pass on the FRAMES benchmark (arXiv:2409.12941) and Google's Sufficient-Context
agentic RAG (90-93% FramesQA; arXiv:2411.06037). User directive: *"deep research
and get the framesqa paper then deep dive and create a plan to integrate
methodology proposed to further increase accuracy, precision and Regenold related
metrics. Go ship and re-evaluate."*

## The post, in one paragraph

A LinkedIn post argues agentic RAG's accuracy gains (the chart: Vanilla 58.68% →
Cross-Corpus Agentic 90.1% → Single-Corpus Agentic 93.61% on FramesQA) are
oversold because three production costs get "swept under the rug": (1) **latency**
— 4-5 sequential agent tasks → "30 sec wait" → user-facing failure; (2) **token
bill** — every iteration / draft assessment / gap-analysis loop multiplies token
consumption; (3) **AI governance** — agents independently orchestrating + routing
across data silos make data lineage a "black box", sacrificing auditability for
automation.

**Verdict:** the three critiques are *correct for unbounded loops* and overstated
as inevitabilities. They are precisely the three constraints Regenold was already
built around (sub-10 ms deterministic default, env-gated bounded LLM polish,
hash-chained audit chain + `ReasoningTrace`). The engineering question is: can we
take the *accuracy methodology* (the part the chart measures) while keeping the
three constraints satisfied? Yes — and R110 does it.

## What FRAMES / Google actually showed (the methodology to steal)

| Source | Finding |
| ------ | ------- |
| FRAMES paper (NAACL 2025) | Single-step retrieval barely beats no-retrieval (Gemini-Pro-1.5: 0.45 vs 0.41). **Multi-step iterative retrieval → 0.66**, oracle (gold docs) 0.73. The win is *iterating*: re-plan sub-queries against accumulated context, dedupe, accumulate. Failure mode of single-shot: *"goes in the wrong direction and never corrects itself."* |
| Google Sufficient-Context Agentic RAG | FramesQA 58.68% → 90.1% (cross-corpus) / 93.61% (single-corpus). Key innovation = a **Sufficient Context Agent**: after retrieval it runs a *missing-pieces analysis* vs the request and decides whether to loop again. This loop-gate is the biggest driver of the 0.66 → 0.90 jump. |
| Adaptive-RAG (NAACL 2024) | Route by complexity: simple → fast single-pass, complex → multi-step. ~half the steps at comparable accuracy; production reports −35% p50 latency, −28% cost, +8% accuracy. **Graceful degradation** — a misroute loses recall, it doesn't fail. |
| Bounded self-critique / deterministic faithfulness | Two-step CoVe = the bounded (one extra call) sweet spot; deterministic citation-faithfulness (zero LLM) catches the up-to-57%-unfaithful-citation failure. Regenold already has the drift / self-contradiction / Component-D grounding guards. |
| Auditable RAG (Frontiers AI 2026, EU-AI-Act-cited) | "Glass box": log every sub-query + every source touched + a reasoning-chain hash. The iterative path is *more* auditable than single-shot when each hop is logged. Regenold's `ReasoningTrace` + hash-chained `evidence/store.py` are exactly this. |

## What R110 ships

A **Sufficient-Context-gated, bounded one-hop decomposition** at the retrieval
layer — the FRAMES methodology, made latency/cost/governance-safe:

1. **`app/engines/sufficient_context.py`** (new, pure-stdlib):
   - `assess_sufficiency(question, covered_articles, *, is_complex)` — the
     deterministic missing-pieces analysis. INSUFFICIENT when (a) the question
     names an explicit Article/Annex the first-pass retrieval missed
     (high-precision), or (b) the question is complex AND decomposes into ≥2
     substantive sub-clauses (the FRAMES multi-part case).
   - `decompose_question` — deterministic clause split, verb-guarded coordination
     rule (no "providers and deployers" false split), live-section aware, ≤cap.
   - Env gates `sufficient_context_enabled()` (default OFF) +
     `max_sub_queries()` (default 3, clamp [1,5]).

2. **Engine wire** (`graph_rag.py::ask_compliance_question`): after the first
   `_retrieve_from_graph`, `_maybe_sufficient_context_hop` fires ONE bounded hop
   when enabled + insufficient + complex — decomposes, re-retrieves each
   sub-query through the existing deterministic retrieval, and `_merge_graph_context`
   **additive-unions** the result (appends behind the first-pass anchors → never
   displaces a winner; accumulates counters). Fail-soft.

3. **Audit lineage** (`reasoning_trace.py`): new `sub_queries` field +
   `record_sub_query(text, refs, source, reason)` — every hop + the refs it
   surfaced is serialised into the `reasoning` wire field and the audit chain.
   The glass-box rebuttal to the "black box" critique.

4. **Cache key** (`routes/regenold.py::_engine_cache_key`): folds in
   `REGENOLD_SUFFICIENT_CONTEXT` + `..._MAX_HOPS` (R30/R56/R79 doctrine — both
   flip the engine output).

5. **`railway.toml`**: `REGENOLD_SUFFICIENT_CONTEXT = "1"` (production ON, after
   the flag-ON davidath A/B confirms non-negative; the bench never reads
   railway.toml so the local scorecard stays clean).

## Why bounded, not a loop — the three constraints, answered

| Post's critique | R110's answer |
| --------------- | ------------- |
| Latency ("30 sec") | Adaptive-routed (fires only on the ~20% `is_complex_question` path) + capped at ONE hop of ≤3 deterministic retrievals (sub-ms BM25 / 50 ms-capped Neo4j). The complex path already pays seconds for Sonnet; the hop adds ≤150 ms. Default-fast path untouched. |
| Token bill | The gate + decomposition are **deterministic** — zero LLM calls. It re-runs existing retrieval, not new generation. No exponential loop. |
| Governance / black box | Every sub-query + source touched + gate reason logged to `ReasoningTrace` → `reasoning` field + hash-chained audit. *More* auditable than single-shot. |

## Verification gates

- `pytest` — full suite green + 60 new `tests/test_sufficient_context.py`.
- davidath bench gate-OFF — **byte-identical** to R108 (Ans Strict 0.3463 / Ref
  Loose 0.5965 / Ref Strict 0.4558 / Tone 1.0 / mt 20/20). The gate is a no-op
  when off.
- davidath bench gate-ON — A/B; must be non-negative on the reference axes
  before enabling in `railway.toml` (BM25-saturated corpus → expect a wash
  locally; the win lands LIVE on multi-part questions + the judge axes, the
  established R31/R69/R97 pattern).
- 276-runner — 255/255 (or 276/276).
- OOS probe (`runner_v2 --local --probe-oos`) — 21/21, 0 leaks (the gate doesn't
  touch scope).

## Honest scope notes

- **davidath won't move much.** The corpus is BM25-saturated (proven across
  R31/R59/R69). The bounded hop's value is on genuinely multi-part / multi-hop
  questions and the live judge axes (refs-faithfulness, correctness), which the
  deterministic local bench can't score. This is the same trade every retrieval
  round since R31 has made.
- **Deferred (documented, not shipped):** a one-bounded-call CoVe-style answer
  verification. Regenold already has deterministic drift/self-contradiction
  guards on Stage-2 output; adding an LLM verification call risks the latency the
  R77-R87 rounds spent tuning down. Park behind a future `REGENOLD_ANSWER_VERIFY`
  flag if a live judge run shows refs-faithfulness headroom the existing guards
  don't capture.
