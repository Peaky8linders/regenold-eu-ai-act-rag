# Analysis: the agentic-RAG critique post → R110 integration

**Date:** 2026-06-08 · companion to [`.planning/R110-PLAN.md`](../.planning/R110-PLAN.md)

## 1. The post

A LinkedIn post reacts to Google Research's agentic-RAG work (the chart:
**FramesQA accuracy — Vanilla RAG 58.68% → Cross-Corpus Agentic 90.1% →
Single-Corpus Agentic 93.61%**). It argues the accuracy story buries two
metrics and one risk:

1. **Latency.** A standard RAG query is ~1-2 s; an iterative multi-agent loop
   (sequential planning → query rewriting → self-critique) where one prompt
   triggers 4-5 agent tasks introduces a "significant delay" — *"a 30 sec wait
   time is a complete failure"* for a user-facing system.
2. **Token bill.** *"Every single iteration, intermediate draft assessment, and
   gap analysis loop multiplies token consumption exponentially"* → an enterprise
   on thousands of users sees a "massive spike in API costs".
3. **AI governance / data lineage.** Because agents *"independently orchestrate,
   rewrite, and route queries across multiple corporate data silos, data lineage
   becomes a black box"* — you can't track which sources were touched, how
   information was filtered, or whether sensitive data leaked in the loop.
   *"Auditability is sacrificed for the sake of automation."*

## 2. Fact-check (deep research)

The chart and the framework are **real and correctly cited**:

- **FRAMES** = *Fact, Fetch, and Reason* (Krishna et al., Google/DeepMind,
  NAACL 2025, [arXiv:2409.12941](https://arxiv.org/abs/2409.12941)). 824
  multi-hop questions, 2-15 Wikipedia articles each. **Single-step retrieval
  barely beats no retrieval** (Gemini-Pro-1.5: 0.45 vs 0.41); **multi-step
  iterative retrieval → 0.66**; oracle (gold docs) = 0.73. The entire value is
  iterating.
- The 58.68 / 90.1 / 93.61 chart is from Google Research's *"Unlocking
  dependable responses with Gemini Enterprise Agent Platform's Agentic RAG"*,
  whose key innovation is a **Sufficient Context Agent** — a missing-pieces
  analysis that gates the retrieval loop (grounded in *Sufficient Context*,
  Joren et al., ICLR 2025, [arXiv:2411.06037](https://arxiv.org/abs/2411.06037)).
  This loop-gate is the biggest driver of 0.66 → 0.90.

**Where the post is right:** for an *unbounded* multi-agent loop, all three
costs are real. The FRAMES paper's best config is 6 non-parallelisable inference
calls per question; an enterprise multi-agent loop is several-fold more.

**Where the post overstates:** "30 sec" and "exponential" are properties of a
*naive* loop, not of the methodology. The research literature already solves all
three:

| Critique | The published fix |
| -------- | ----------------- |
| Latency | **Adaptive-RAG** (Jeong et al., NAACL 2024): route by complexity — simple → single-pass, complex → multi-step. ~half the steps at comparable accuracy; production reports −35% p50 latency. Misroutes degrade gracefully (lose recall, don't fail). |
| Token bill | The decomposition + sufficiency check can be **deterministic** (no LLM); cap the loop at ONE bounded hop. Plan-then-execute runs sub-retrievals in parallel (latency ≈ longest branch, not the sum). |
| Black box | Log every sub-query + every source touched + a reasoning-chain hash. The iterative path is *more* auditable than single-shot when each hop is logged (Auditable RAG, Frontiers AI 2026 — which names the EU AI Act as the driver). |

## 3. The irony: Regenold is already the post's answer

Regenold's architecture was built around exactly these three constraints,
*before* this post:

- **Latency** — deterministic sub-10 ms p50 default; the LLM (Sonnet) Stage-2
  polish is env-gated, complexity-routed (~20% of questions), confidence-gated
  (R87-E), and single-round-trip (R81-A1, no open-ended ReAct loop).
- **Token bill** — the deterministic path is free; Stage-2 fires only on the
  rows that benefit, with an LRU cache (R28).
- **Governance** — a hash-chained, tamper-evident audit store
  (`app/evidence/store.py`) + a per-request `ReasoningTrace` (R50,
  `?include_reasoning=true`) that records scope, anchors, retrieval path, guards,
  confidence. That *is* the glass box.

## 4. What R110 took from the methodology

The one genuinely missing piece was the **Sufficient Context loop-gate** — the
part that drove Google's 0.66 → 0.90. R110 grafts it in *bounded* form
(see [`.planning/R110-PLAN.md`](../.planning/R110-PLAN.md)):

- **Sufficiency gate** — after the first retrieval, a deterministic missing-pieces
  analysis: did we cover every Article the question names + every sub-part a
  multi-part question asks? If not, fire **one bounded hop** of ≤3 deterministic
  sub-query retrievals and union the result.
- **Adaptive routing** — fires only on the ~20% `is_complex_question` path
  (Adaptive-RAG), so simple QA keeps the sub-10 ms path.
- **Auditability as a feature** — every sub-query + source touched + gate reason
  is logged to `ReasoningTrace.sub_queries` and the audit chain. The post's
  "black box" critique becomes Regenold's selling point.

Net: the accuracy methodology of the chart, with latency bounded (≤150 ms added,
on the complex path only), token cost zero (deterministic gate), and lineage
*increased*, not sacrificed.
