# R359 — NICD paper deep-dive: gaps found + fine-grained CRAG judge

**Paper:** Wedge, Stutter, Dixon & Cała, "Reducing Hallucinations in Complex
Question Answering using Simple Graph-based Retrieval-Augmented Generation"
(NICD / Newcastle University, long version, 25 pp incl. Appendices A–C).

**Constraint honoured:** the live judge run uses **AWS Bedrock only**
(`claude-sonnet-4-6`, no extended thinking). The Claude-Max cloudflared
tunnel is never touched — `scratch/live_ab_env.py` forces
`P2P_GRAPH_RAG_PROVIDER=bedrock` + `REGENOLD_BEDROCK_WRAPPER_FALLBACK=0`.

---

## 1. The paper's methodology, distilled

The paper's contribution is a **lightweight document graph + a curated
toolset** over vector RAG for complex (multi-hop / cross-document /
multi-entity) QA, evaluated on MoNaCo. The transferable machinery:

1. **Curated handwritten tools, never LLM-generated Cypher.** The agent is
   exposed to pre-written queries (title search → section titles/infoboxes →
   get sections → windowing → backlinks → shortest path) so it never writes
   graph queries — removing the query-generation failure + injection surface
   and encouraging multi-hop-in-one-query over CoT step-by-step retrieval.
2. **Safe-refusal prompting.** The agent is explicitly told to return
   "unknown" when the KB does not contain the answer — and CRAG scoring
   treats a refusal as 0 (neutral), NOT as a fail: an honest refusal is
   strictly better than a hallucinated answer (−1).
3. **Token discipline.** Section-titles-first navigation (title search →
   section titles → get sections) replaced whole-article reads; measured
   input-token savings without losing recall.
4. **Evaluation = fine-grained CRAG truthfulness (Appendix C.2.2).** The
   headline metric is a 5-level scale on the ANSWER:
   `+1.0 fully correct | +0.5 subset-clean | 0.0 refused | −0.5 mixed |
   −1.0 all-wrong`, with **truthfulness = sum of scores** (accurate −
   hallucinated). This is asymmetric BY DESIGN: a hallucinated extra costs
   more than a missing claim, and a refusal is neutral.
5. **Judge self-preference avoidance.** The judge was a different model
   family (Llama-4-Maverick) than the generator (GPT-5.4), and 3-run
   min/median/max reporting to absorb stochasticity.

**Key results:** vector+graph RAG >2× factual-correctness precision/recall
vs vector-only, ~80% higher fine-grained truthfulness, roughly halved
hallucinated answers, and — because retrieval got better — *fewer* refusals
at the same time (better evidence → less need to refuse).

## 2. Cross-reference: what the current implementation already has

| Paper element | Current implementation (main repo) |
|---|---|
| Curated retrieval over a graph | ✅ `neo4j_semantic_graph.py`, `graph_semantic.py`, `graph_aware_retrieval.py`, `graph_expand_2hop.py`, `path_rag.py`; deterministic Stage-1 retrieval (no LLM-written queries) |
| Query rewriting / don't-search-the-question-text | ✅ `query_expansion.py` (R328 port), `frames_rewriter.py`, `hybrid_rrf_retriever.py` |
| Sufficient-context hop (re-retrieve before refusing) | ✅ `sufficient_context.py` — FRAMES-style bounded decomposition (`_maybe_sufficient_context_hop`), exactly the paper's "call the tools again before saying you don't know" |
| Safe-refusal / never invent | ✅ prompt rules 4 & 11 (`graph_rag_prompts.py`): "If the supplied references don't cover the question, say so plainly; never invent content", closed-world refusals for out-of-Act provisions, `zero_retrieval_fallback.py` |
| References as structured output | ✅ wire `references` (minimal set), R356/R358 curated intercepts seed refs to gold heads |
| Token/truncation discipline | ✅ R357 post-generation truncation guard + tail repair; conciseness axis |
| Faithfulness / citation verification | ✅ `faithfulness_verify.py`, `crag_nli_verifier.py`, `stage2_fidelity.py` wired into the two-stage path |
| Anti-sycophancy grounding | ✅ `legal_v2._ANTI_SYCOPHANCY` + quote-or-retract |

## 3. Real gaps found (with respect to the paper)

**GAP-1 (the big one) — no answer-level fine-grained CRAG scoring.**
The repo's `ref_crag_fine` (R329) applies the paper's scale to the
REFERENCE SET; the LLM judge axes are binary pass/fail per axis. The
paper's headline metric — the 5-level scale applied to the ANSWER, with
truthfulness = sum of scores — did not exist anywhere. Consequences,
measured in the R355 report:

* **Refusal ≠ hallucination.** The binary judge failed honest refusals
  (0.0) exactly like fabricated answers (−1.0). The paper's whole point is
  that a refusal is *neutral* and a hallucination is *harmful*; the binary
  ruler could not reward the former or penalise the latter asymmetrically.
* **Partial credit invisible.** A +0.5 "subset-clean" answer (missing some
  claims, no hallucination) scored identically to a −1.0 all-wrong answer
  on the binary axis — so the R350.2 optimisation loop could not see the
  difference between "needs more recall" and "is fabricating".
* **Hallucination rate unmeasurable.** Nothing in the aggregate reported
  how many rows shipped a MIXED/WRONG claim — the metric the paper uses to
  prove graph-augmented retrieval halves hallucinations.

**GAP-2 — judge model = same family as generator.** The paper explicitly
used a different model family for judging to avoid self-preference. Our
judge is Claude (opus-4-6 in R355) grading Claude-generated answers.
Mitigations already present (verbatim-text grounding, quote-or-retract,
anti-sycophancy preamble) narrow the bias; the cheap-tier sonnet judge used
for R359 also moves away from the generator tier. Residual risk documented,
not fully fixable within a Bedrock-only (Anthropic-only) constraint.

**GAP-3 — R355's judge run collapsed on the Opus thinking budget.**
`judge_r355_anscorr.py` used opus-4-6 + extended thinking (budget 256/1024)
and died against the Bedrock per-minute token quota after a few calls
(report: 79/81 errored). The paper's rubric is a *classification* task; the
paper itself used a 17B judge model. Sonnet-4-6 with **no thinking** is the
right tool: cheap enough to complete 81 rows, strong enough for the rubric,
and it sidesteps the quota collapse entirely.

**GAP-4 (minor) — 3-run stochasticity.** The paper runs each question 3×
(min/median/max). Our judge infrastructure supports `k` samples
(`_aggregate_samples`, median + agreement) but the R355-style scripts run
`k=1` for cost. Kept at k=1 for R359; the plumbing is there to raise it.

## 4. What shipped (R359)

### `evals/judge/legal_v2.py` — new `answer_crag_fine` axis (opt-in)

Port of the paper's Appendix C.2.2 rubric verbatim, applied to the ANSWER:

* **render** — question + gold answers (from the probe set) + verbatim
  provision text for the union of gold/pred refs (quote-or-retract
  grounding; the judge never leans on parametric legal memory). The 5-step
  rubric from the paper is embedded in the prompt, plus the 5-level scale.
* **postprocess** — clamps to the legal scale; non-numeric or out-of-scale
  scores are *unscorable* (not a verdict); verdict = pass iff score ≥ +0.5,
  so a MIXED (−0.5) or WRONG (−1.0) answer always fails even when it also
  contains correct claims, and a REFUSED (0.0) answer fails the binary gate
  but scores **neutral** on truthfulness — the paper's asymmetry.
* **aggregate** — `truthfulness` (sum of scores), `mean_crag_score`,
  `hallucinated_rows` (rows with score < 0) alongside the binary pass/fail.
* Kept OUT of the default `AXES` tuple (`test_exactly_four_axes` still
  passes): the axis is opt-in via direct `_judge_axis("answer_crag_fine")`
  dispatch, so standard 4-axis runs are byte-identical.

### `scratch/judge_r359_crag.py` — live judge run (Bedrock only)

* 81-row branch arm of `dynamic-ab-r350-live-answers.json` (the R350.2
  full-stack answers), gold answers from `scenarios_live_answers.py`.
* `claude-sonnet-4-6`, temp 0, no thinking, 700 max tokens — cheap enough
  to finish, and matches the paper's "small judge model" choice.
* Resume-aware sidecar (`r359-crag-fine-branch.json`), single-worker,
  throttled spread — same persistence contract as the R355 script.
* Report (`docs/R359-crag-fine-judge-report.md`) with the score
  distribution bar, truthfulness sum, hallucinated-row count, and per-row
  score/class/missing/hallucinated/rationale.

### `tests/test_r359_crag_fine_axis.py` (17 tests)

Scale mapping, the asymmetry contract (MIXED fails; REFUSED neutral),
shape failures (non-numeric / out-of-scale / unanswered), bias-key
non-leakage (marker-value convention, same as `test_legal_v2_judge`),
gold-answer + verbatim grounding in the prompt, and median/agreement
aggregation. All 72 judge-side tests pass (R359 + R305 + R329).

## 5. Honest residuals

* **Sonnet ≠ paper's cross-family judge.** Sonnet is still Anthropic; the
  paper's family-split judge would need a non-Claude provider, which the
  Bedrock-only constraint rules out for now.
* **k=1 sampling.** Median-over-3 would tighten the distribution numbers;
  the plumbing exists (`_aggregate_samples`) and costs 3× the Bedrock
  calls.
* **Reference-set CRAG vs answer CRAG coexist.** `ref_crag_fine` (R329)
  scores the citation set; `answer_crag_fine` (R359) scores the answer.
  They measure different defects (over-citation vs hallucination) and both
  stay, named distinctly, per the R327 "change the name" doctrine.
* The R350.2 answers were produced by the pre-R356 stack; a re-run of the
  full stack (now with the R356/R358 curated intercepts + R357 guard) is
  the natural next measurement — the CRAG judge is the right ruler for it.
