# R448 — high-value architecture and performance audit

**Date:** 2026-09-28  
**Status:** Recommendations only; no application behavior changed.

## Executive summary

The highest-value optimization target is the **remote answer-generation path and the work sent to it**, not line-count reduction or speculative retrieval pruning. The current request can combine local lexical/ontology retrieval, vector and graph-semantic supplements, bounded KG context, conditional Stage-2 generation, transport fallback, and route-level reference repair. The expensive parts are remote calls and their prompt/output tokens; however, current artifacts do not provide a representative end-to-end latency/cost distribution. Measure that path first, then reduce calls and context behind paired quality gates.

Recommended order:

1. **Instrument the full request and establish a latency/token/cost baseline.** Attribute wall time, tokens, retries, cache hits, and degradation to each lane and model leg.
2. **Make Stage-2 dispatch a single policy boundary.** Apply one end-to-end deadline/retry budget across primary and fallback; test a lower-cost default composer and narrow deterministic skips against a held-out, stratified cohort. Do not assume model/token settings fix transport latency.
3. **Use the R448 concision signal to investigate token savings, not claim a quality or latency win.** The sampled answers became materially shorter, but these experiments did not measure tokens, dollars, or request latency and are too small to establish broad non-inferiority.
4. **Keep retrieval local-first and evidence-preserving.** Let BM25/ontology and TurboQuant discover candidate provisions; use KG relations for constrained expansion; resolve every answerable claim to canonical statutory text. Use a reranker only after mandatory evidence is protected. Do not promote graph dumps or apply an unmeasured global top-K cap.
5. **After measuring, make behavior-preserving architectural extractions.** Unify Stage-2 transport first, then establish a typed evidence/claim interface and one reference finalizer. Do not expect dead-code deletion to produce meaningful savings.

The target is a small, predictable pipeline: **local evidence retrieval → source-resolved evidence bundle → one low-cost synthesis call when needed → deterministic citation finalization**. More capable generation or optional remote retrieval should be reserved for query classes where a controlled evaluation demonstrates value.

## Scope and confidence

This is a targeted audit of the current request path, selected runtime modules, prior reviews, and measurement artifacts—not a line-by-line re-verification of every round. `docs/ROUNDS.md` is append-only and the inspected file ends at R403; later R448 evidence is in separate measurement artifacts. The audit checkout was `fix/r448-conciseness-followup`, one commit behind `origin/main` at review time. It already contained a modification to `app/engines/answer_completeness.py` and untracked R448 measurement material; those shared artifacts were preserved. No application file or measurement was changed or run for this report.

There was no production telemetry/credential check, representative deployed latency study, or controlled comparison to an external frontier system. Findings below distinguish observed results from hypotheses. Historical module-size and round findings are explicitly labeled as such; they are not asserted to be fresh measurements of this checkout.

## Current path and constraints

The active shape is approximately:

```text
route history/scope handling
  → deterministic query parsing
  → KB/ontology retrieval, with vector and constrained graph-semantic support
  → deterministic/curated answer where applicable
  → conditional Stage-2 synthesis/transport fallback
  → route normalization and reference reconciliation
```

The KB has lexical BM25 over statutory summaries and typed ontology/corpus material; SVD/TurboQuant and sentence-level vector components provide semantic recall. Graph-semantic functions add provision/hierarchy/definition context under constraints. `kg_context.py` supplies bounded, memoized, **non-citable** Stage-2 context. The route then normalizes the answer and reconciles wire references against the final prose. Consequently, generation-context changes can affect both answer text and the references ultimately emitted.

The project’s most important invariants remain sound:

- The pinned/canonical Act text, not a generated graph summary, is the citable legal authority.
- KG is additive; graph-primary retrieval has previously buried operative provisions.
- Mandatory/anchored evidence must survive any candidate budget or reranking.
- No global top-K trimming or positional reference cap: historical full-corpus simulations showed gold-reference loss.
- Keep heavy neural NLI/PyTorch out of the runtime path; historical testing found NLI slower and less accurate than lexical checks.
- Treat a flag or module as active only after confirming the production callsite. The history contains inert flags and retrieval layers that did not execute until wired.

## Evidence with direct optimization relevance

### R448 concision measurements

The paid paired screen used two reconstructed-gold questions with three draws per arm. It produced 12 valid answers, all triple-judged; 15 attempts were made, with three invalid/degraded attempts. All 30 criterion observations per arm passed, with no criterion changes. Mean answer length fell from **2,126.33 to 1,193.50 characters (−43.87%)**. With only two questions, this is a useful signal, not a general quality result.

The stratified list/scenario run used 12 questions (six per stratum), three draws per arm and yielded 72 valid answers and 216 grouped judge calls. Each arm had 144 criterion observations: 141 passed, three failed, and none were unknown. The same Article 50(4) criterion failed on `rg_103` in both arms; there were no gains or losses. Mean length fell from **1,657.56 to 983.58 characters (−40.66%; −673.97 characters)**. The fixed cohort and repeated draws are useful, but the cohort is small and there is no confidence interval.

Both runs use **reconstructed** gold, not the original evaluator annotations. They establish a sizeable observed length difference with no observed criterion movement in these cohorts; they do **not** establish correctness improvement, broad non-inferiority, token/cost savings, or lower latency. Character count is not a substitute for provider-reported token counts. In the stratified results, all valid runs were labeled `kb_fallback`; that label alone does not establish that ontology, graph, or other supplements were absent.

### Latency clues and older controlled work

- The R448 Stage-2-primary preflight reported **6,645 ms** for a tiny 10-input-token/1-completion-token request. A judge preflight reported 866 ms. These are single preflight observations, not normal-answer latency distributions, but they are a strong reason to measure network/transport overhead before tuning generation settings.
- The repository’s operational notes record that fast-mode/thinking-token changes did not resolve the wrapper/CLI latency floor. Avoid repeating that as an unmeasured latency experiment.
- R403’s 110-row graph-semantic comparison reported RefStrict **+4.50 percentage points** (95% CI [+1, +9]) and `gold_dropped_head` improving 8→5; answer-axis intervals crossed zero. Keep the measured useful layer unless a larger controlled study changes the trade-off.
- In a separate R403 gloss comparison, gloss-on had marginal/unproven quality impact and slower responses on 72/110 rows; the response-speed difference was −0.95 pp (95% CI [−1.88, +0.06]). Gloss remains OFF. This is a useful example of not paying for an optional context layer without demonstrated benefit.
- R421’s historical sample attributed 49/51 engine-gap criteria to evidence already present in emitted references—suggesting generation/context use rather than raw recall was often the remaining failure. This is a sample, not a current population estimate; it argues against solving every miss by adding more retrieval.
- R423 reported a positive need-proportional answer-contract result in a 27-row hard split with three generations (+13.93 pp overall in that sample). R422 attributed verbosity to a closed-set skeleton instruction rather than prompt size. Together these favor answering to the requested evidence/number of items, not imposing a universal short-answer template.

## Ranked findings and proposals

### 1. Remote Stage-2 transport is the first latency/cost investigation

**Impact:** Very high potential. **Confidence:** High that it merits measurement; medium on the size of production impact.

The path has a primary Stage-2 transport and Bedrock fallback, and Stage-2 model choice, context, retries, and fallback all affect latency/cost. R448’s single 6.6-second preflight is not enough to estimate p50/p95, but it shows the fixed cost can be material even for a tiny payload. Repeated retry/fallback policy spread across two wrappers is also a reliability and tail-latency risk.

**Proposal:**

- Add per-request spans for route/engine, retrieval lanes, prompt assembly, primary Stage-2, fallback, retries, post-processing, and total wall time. Record provider/model/leg, prompt and completion tokens, retry count, cache status, and degraded outcome; aggregate p50/p95 and dollar cost by question class.
- Introduce one Stage-2 dispatch contract with a **single total deadline** and explicit per-leg budget. Retry only within that budget; record why fallback occurred and which leg produced the answer. Keep the existing tunnel-primary → Bedrock fallback semantics until a measured policy change is approved.
- In the same harness, compare the current model to a lower-cost default composer on a fixed, stratified paired cohort. Route to a higher-capability model only when the query class and evaluation show the extra spend is justified. This is a proposal, not a claim that a smaller model is already adequate.
- Retain deterministic/curated Stage-2 skips that have an explicit guard and evidence. Test additional narrow skips only as an isolated treatment. Do **not** disable Stage-2 globally for “simple” questions: prior universal skip proposals are unsupported and can lose multi-part obligations or caveats.

The R426 architecture review had already identified duplicated Stage-2 transport as its highest-value pure extraction (roughly 1,400 lines in that historical snapshot). That extraction should preserve behavior first; the measured optimization is the deadline/model/call policy, not the code move itself.

### 2. Turn the R448 concision signal into an actual cost experiment

**Impact:** High potential for output-token and downstream UX savings. **Confidence:** Medium for shorter outputs on these cohorts; low for cost/latency or broad safety impact.

A roughly 41–44% reduction in answer characters is promising. It may lower completion tokens and improve usability, but the current runs do not include token usage, actual cost, or request timing. Shortening also risks omitting a limb in list/scenario questions; the unchanged Article 50(4) failure shows that concision did not repair the known gap.

**Proposal:** Continue paired ON/OFF measurements on a larger, fixed cohort stratified by definition, direct article, list, exception, scenario, and multi-turn questions. Capture actual input/output tokens, provider cost, end-to-end latency, and judge criteria. Review failure cases manually, especially statutory lists and exception limbs. Keep each prompt/answer change isolated; do not infer that fewer characters imply fewer prompt tokens or faster completion.

The desired policy is **need-proportional completeness**: cover every requested item and legal condition, but do not pad with unrelated provisions or restate the same evidence. Preserve explicit list coverage and exact caveats over a character target.

### 3. Make retrieval local-first, staged, and evidence-preserving

**Impact:** Medium-to-high potential; reduces avoidable network work and context noise. **Confidence:** Medium for architecture; low for any specific lane removal without fresh ablation.

Current components cover lexical BM25, typed ontology material, TurboQuant/SVD semantic recall, constrained graph semantics, optional external embeddings, and reranking. The source review confirms gated/optional remote retrieval exists; this audit does not assert every lane runs on every request. Adding a lane indiscriminately can add latency and noise, while removing one without callsite and recall tests can silently drop rare provisions.

**Proposal:** Evaluate a cascade against the actual active call graph:

1. Start with exact article/annex anchors plus local BM25 and ontology expansion.
2. Use TurboQuant/SVD semantic recall where lexical coverage is weak or the question requires paraphrase/concept matching; keep its candidates tied to canonical source IDs.
3. Expand via KG only from relevant/anchored candidates; use it for relations, subpoints, hierarchy, or useful non-citable explanation—not as the primary legal-text ranker.
4. Apply a reranker only to a bounded candidate pool **after protecting explicit anchors and mandatory related provisions**. Compare local ranking to any Cohere/external call on both quality and cost. Keep external embeddings separately opt-in unless they have a demonstrated net benefit.
5. Resolve selected evidence to exact operative text before generation; send a deduplicated, token-budgeted evidence bundle. Budget optional summaries/context first, never silently cut required statutory limbs.

This is a measurement hypothesis, not authorization to turn off vector/graph/reranking flags. Use relevance/recall and gold-reference retention at each stage; no global top-K cap.

### 4. Separate evidence selection, answer claims, and wire-reference finalization

**Impact:** High correctness/debuggability; indirect performance impact via less duplicate work and clearer token budgeting. **Confidence:** High on architectural duplication from prior audit; exact current savings unmeasured.

The engine drafts/grounds an answer, while the route applies separate answer and reference passes. This makes the reference result depend on prose and has historically required fixes in multiple layers. A typed evidence object can also stop graph summaries and candidate snippets from being confused with canonical legal text.

**Proposal:** Define a behavior-preserving interface around a single request-scoped `EvidenceBundle`: canonical source ID, exact text/version, provision/subpoint, retrieval provenance, and mandatory/optional status. Have a claim plan refer to evidence IDs; let one finalizer produce prose-linked wire references from the claim/evidence structure. Keep a compatibility adapter for the existing response contract during migration. This is a staged extraction, not a rewrite of citation rules in the same change.

Use byte-for-byte replay of recorded draws to gate the move. Only then test a structured claim-output format or changes to reference reconciliation as separate behavior changes.

### 5. Simplify large modules by extracting seams, not deleting code

**Impact:** High maintenance and change-safety value; low direct request-time savings. **Confidence:** High for the historical snapshot; current LOC should be re-counted before implementation.

The R426 audit found that two large modules were dominated by a few oversized functions; only two unused top-level functions totalling 14 LOC were identified in its top-20 scan. It measured a 3,660-line route handler, a 986-line cache-key function, and substantial duplicated Stage-2 transport (historical counts). This is not a large dead-code cleanup opportunity. `_engine_cache_key` being long is a maintainability risk, but computing fewer Python lines is unlikely to move latency beside a remote model call.

**Proposal/order:**

1. Extract one Stage-2 transport/policy seam, behavior-preserving.
2. Establish the evidence/claim bundle and finalizer seam.
3. Derive cache identity from an explicit registry of response-changing inputs instead of hand-transcribing a very large key. Preserve the existing cache-key completeness test and include all engine-side response-changing flags; do not key route-only passes that always run on cache hits unless they change the cached object.
4. Split the route orchestration into typed phases after concurrent edits to that module are clear.

Do not do a big-bang route rewrite, speculative dead-code deletion, or behavioral changes bundled with pure moves. Existing cache identity invariants remain mandatory.

## Target architecture

```text
request + short history
  → typed intent / answer need
  → local exact + BM25 + ontology recall
  → conditional TurboQuant semantic recall
  → constrained KG expansion and optional reranking
  → source-resolved, deduplicated EvidenceBundle
  → deterministic answer OR one low-cost LLM composition call
  → deterministic claim/reference finalizer
  → response + trace
```

A low-cost LLM should arrange grounded evidence, not decide what the law says from a risk-tier graph dump. Preserve exact Act text and source-version identity. Use semantic retrieval to find candidates, ontology/KG to express relationships, and reranking to order candidates—not to erase mandatory evidence. Keep agent loops out of the default path unless a measured use case requires them.

## Measurement and rollout gates

For every behavior-changing optimization, compare one lever at a time on the same fixed question set with randomized/paired arms and repeated generations. Stratify at minimum by direct provision, definitional, list, exception, scenario, semantic/paraphrase, and multi-turn questions. Record:

- p50/p95 end-to-end and per-stage latency, not just model-reported time;
- input/output tokens and cost per request, model/provider/leg, retries, timeouts, cache hits, and degraded/fallback rate;
- exact answer criteria, required-list/exception coverage, reference precision/recall and `gold_dropped_head`, answer need/conciseness, and unchanged-vs-changed cases.

Pre-register a non-inferiority margin for correctness and reference retention before comparing cost/latency. The R448 cohorts are too small to establish one. Use the project’s live `ab_judge` and `easyhard_ab` gates for prompt/answer changes, reading `easyhard_ab`’s exit code (only 0 passes; 1 fails; 2 is indeterminate). These instruments are still proxies: the reconstructed R388 gold is not the original official annotation, and neither harness alone proves superiority to the competition frontier. For pure extractions, run recorded-draw byte-identical replay (answer, reference set/order, and relevant trace), tracked-module/import checks, cache-key AST checks, and tests before any behavior experiment.

## Explicit non-recommendations

- No graph-primary retrieval or generic risk-tier graph dump.
- No global top-K/reference cap or positional trimming.
- No universal Stage-2 skip, blind switch to a cheaper model, or conclusion that a smaller prompt automatically improves latency.
- No external embedding/reranking enablement without a measured value/cost comparison.
- No NLI/PyTorch dependency, agent loop, or broad rewrite to make modules look smaller.
- No claim of official-frontier superiority, production p95, correctness lift, or cost reduction from the current R448 artifacts.

## Source map

- Runtime path and contracts: `app/routes/regenold.py`, `app/engines/_graph_rag_impl.py`, `app/llm/stage2.py`, `app/llm/stage2_policy.py`.
- Retrieval and evidence: `app/data/kb_search.py`, `app/engines/turboquant_index.py`, `app/engines/embeddings_index.py`, `app/engines/vector_recall.py`, `app/engines/graph_semantic.py`, `app/engines/kg_context.py`, `app/engines/cohere_rerank.py`.
- Historical architecture: `docs/reviews/r426-bigfile-architecture-audit.md`, `docs/reviews/r421-missed-issues-and-remediation-plan.md`, `docs/reviews/r411-architecture-audit.md`.
- Controlled findings: `docs/measurements/r403/CHECKPOINT.md`, `docs/measurements/r403/paired-G0-vs-G1.json`, `docs/measurements/r403/paired-L0-vs-L1.json`, `docs/measurements/r423/CHECKPOINT.md`.
- R448 paired artifacts: `docs/measurements/r448/paid-screen-rg037-rg085-20260927/` and `docs/measurements/r448/paid-stratified-list-scenario-20260928/`.
- Project gates and invariants: `AGENTS.md`.
