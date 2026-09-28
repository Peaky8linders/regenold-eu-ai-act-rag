# R448 — quality-first request telemetry design

**Date:** 2026-09-28  
**Status:** Design only; no runtime changes made.

## Decision hierarchy

The system and its experiments must be judged in this order:

1. **Answer correctness first.** The answer must state the legally correct substance, satisfy the question’s required parts, conditions and exceptions, and avoid material unsupported or contradictory claims.
2. **Reference correctness second.** The emitted references must identify the governing provisions at the required grain, support the claims, and retain the expected gold heads. A shorter answer or faster request cannot excuse a wrong, missing or misleading citation.
3. **Then the rest of the evaluation metrics.** Report every remaining rubric axis—answer conciseness, reference conciseness, regulatory tone and response speed—plus relevant multi-turn/coherence checks. These are secondary to correctness, not substitutes for it.
4. **Only then optimize operational performance.** Latency distributions, tokens, cache behavior, retries, fallbacks and cost are diagnostic and optimization measures. Choose among candidates that have cleared the quality gates; never trade an answer or reference regression for a speed or cost gain.

This document designs **operational telemetry only**. A request event can show what ran and what resources it used; it cannot determine whether the legal answer or its references are correct. The quality gates below are separate evaluation work and are a prerequisite to treating performance as an optimization objective. Do not turn telemetry into a legal-content logger or a purported quality score.

### Why the ordering matters for the current evidence

The R448 concise-contract screen used two questions, three generations per arm per question, and reconstructed gold. On its 12 valid generations, each arm passed all 30 listed criterion observations, with no criterion changes, while mean answer length fell **43.87%**. This is a small-sample observation—not a correctness lift, broad non-inferiority result, reference-correctness result, or token/cost/latency win. The separate 12-question list/scenario sample had 141/144 criterion observations pass in each arm and the same three Article 50(4) failures on `rg_103`; mean length fell **40.66%**. It also does not establish broad non-inferiority or reference correctness. Both artifacts use reconstructed gold, not original evaluator annotations.

The R403 semantic-layer comparison (`paired-L0-vs-L1.json`) reported answer-correctness deltas of **−0.77 pp loose** (95% CI [−4.18, +2.48]) and **−0.91 pp strict** ([−5.45, +3.64]), alongside reference-correctness gains of **+2.33 pp loose** ([0, +5.33]) and **+4.50 pp strict** ([+1, +9]); total gold-head drops changed 8→5 with no new drops in B. The reference result is promising, but the answer intervals crossing zero do **not** demonstrate non-inferiority. The paired `G0-vs-G1` sidecar reports a new gold-head drop on `rg_090` even though the aggregate count changes 5→4. Per-row regressions matter; an improved total must not hide a new loss.

These examples make the order concrete: inspect answer correctness first, references second, the rest of the rubric third, and only then use resource data to choose a faster or cheaper quality-qualified option. The R448 preflight of roughly 6.3–6.65 seconds for a 10-input-token/1-output-token request is a single observation, not a production latency distribution.

## Quality-evaluation contract (separate from telemetry)

### Measurement validity comes before interpreting any score

For an answer-changing comparison, use the same fixed question IDs in paired baseline/candidate arms. Preserve per-row answers, references, criterion verdicts and provenance; pin the application revision, flags, gold/rubric version, judge/model identity, repetition count, Stage-2 model and serving leg, and cache policy. Verify the intended treatment reached its real callsite and the graded answer came from the expected execution path. Confirm judge calls actually ran, parse/coverage is complete, and paired judgments share the intended judge identity/cache. Dead or incomplete judgments, deterministic fallback, unexpected fallback-serving, stale cache entries, or an inert lever can create plausible but vacuous deltas; report such runs as invalid/indeterminate, not as a pass or null result.

Use original evaluator annotations if they become available. Until then, explicitly label R388 criteria/reference keys and their scores **reconstructed**. A reconstructed key can be incomplete; a reconstructed judge can miss an extra unsupported claim or a criterion absent from the key. Do not report those results as official scores or proof of legal correctness. Do not invent a non-inferiority margin after observing results. A confidence interval that crosses zero or a non-significant test does not prove safety; where evidence cannot rule out a material answer regression, hold the change or obtain more/adjudicated evidence.

### Ordered gates and scorecard

| Order | What is evaluated | Required evidence / stop condition |
|---|---|---|
| **1 — Answer correctness** | Legal substance, all requested parts, conditions/exceptions, contradictions and unsupported material; report reconstructed loose and strict axes plus per-question/per-criterion changes. | Investigate candidate-side row/criterion regressions, not just the mean. A confirmed material answer regression blocks promotion. If the available proxy cannot resolve correctness risk, the result is inconclusive—not “no regression.” |
| **2 — Reference correctness** | Head-level recall, required coordinate/grain recall, canonical citation validity, relevance/precision, and whether cited text supports the answer. Keep this distinct from reference count. | Require **zero newly dropped gold heads** relative to baseline on paired rows. List the affected row/coordinate; do not net a new loss against an improvement elsewhere. A count or brevity gain cannot offset a reference-correctness loss. |
| **3 — All remaining evaluation metrics** | Report every other reconstructed axis and relevant multi-turn/coherence measure, row counts and uncertainty. Do not use geometric-mean overall as the sole result. | Answer conciseness, reference conciseness, regulatory tone and response speed are visible as separate metrics, but none overrides Gates 1–2. Remember the reconstructed conciseness formulas do not independently detect omissions. |
| **4 — Operational optimization** | Use telemetry for representative latency distributions, tokens/usage coverage, retries/fallbacks, cache effects and known metered-cost estimates. | Compare or optimize these only among candidates that have cleared Gates 1–3. Telemetry is execution/resource evidence, never a substitute for any quality gate. |

The reconstructed R388 rubric has eight axes: `ans_correctness_loose`, `ans_correctness_strict`, `ans_conciseness`, `ref_correctness_loose`, `ref_correctness_strict`, `ref_conciseness`, `regulatory_tone`, and `resp_speed`; `overall` is a geometric mean. Answer correctness loose micro-averages criterion checks; strict requires every criterion for an answer. Reference loose is head recall; strict is coordinate recall, with a more-specific descendant able to satisfy an expected coordinate. Conciseness formulas are length/count based; omissions are supposed to be caught by correctness. These formulas and their gold inputs are reconstructed.

### What the existing instruments can and cannot establish

- **`evals.official.score_arm` / `paired_ab`:** produces all eight reconstructed axes and paired row statistics when the gold, verdicts, judge identity and paired cache are valid. It does not recover original evaluator labels or turn a proxy into an official score. Use its row-level results and CI, not only `overall`.
- **Live `evals.harness.ab_judge`:** the project’s live pairwise gate for answer/prompt changes; it compares correctness, reference faithfulness, conciseness and tone with position swaps. Its correctness axis is a proxy based on reconstructed expected keywords/references; its reference prompts use KB summaries, not a complete independent Act-grounded reference gold. Its deterministic mode checks exact refs/keywords and cannot establish prose correctness.
- **`evals.harness.easyhard_ab`:** the project’s complementary gold-scored reference/strict-recall gate, including a hard gold-head-drop rule and per-row Stage-2 provenance. It is not a full substantive answer-correctness judge. Read the process exit code, not just its printed table: **0 PASS, 1 hard gold-head fail, 2 indeterminate, 3 VOID**. Its minimum row count rejects smoke runs; it is not a power guarantee.
- **`evals.judge.grounded`:** a separate post-hoc judge that grounds answer, reference and citation-faithfulness judgments in verbatim Act text. It is not independently gold-complete by default: answer grounding can fall back to provisions selected by predicted citations, and reference recall cannot be complete without independent gold coverage.
- **Request telemetry:** can confirm operational liveness, serving leg, retries, cache activity and resource use. It cannot score answer correctness, reference correctness, completeness or quality.

For behavior-changing proposals, run the repository-required live `ab_judge` and `easyhard_ab` gates and inspect the output artifacts and exit codes. These are necessary project checks, not sufficient proof of answer correctness or official-score non-inferiority. Pair them with row-level answer-correctness evidence and the separate reference gate above. If the available reconstructed/proxy evidence cannot substantiate the ordered quality checks, label the conclusion accordingly; do not relabel a telemetry result as quality evidence.

## Telemetry recommendation

Use a small **request-local telemetry record** carried in a `ContextVar`, timed with `time.perf_counter_ns()`, and emitted as one bounded structured log event after the ask response body has been handed to the ASGI server. Use the existing `structlog` dependency and deployment log pipeline. Instrument only useful boundaries and actual external-call choke points; do not time every helper in the large route/engine modules.

This first slice is an observability-only, behavior-preserving change. It must not change answer generation, retrieval, prompt, reference finalization, cache policy, response shape, or error handling. It must not be described as improving or protecting correctness. Quality changes remain separately gated as above.

A pure-ASGI middleware on the root `app` (outside the mounted `api_v1`) should own request start time, random log-only `request_id`, status code, sampling decision, and final emission. Filter strictly to `POST /api/v1/regenold/eu-ai-act/ask`; do not inspect or log request/response bodies or headers. Wrap `send` only to observe response status and the final body frame; never buffer response content. The route sets an allowlisted operational outcome (`answered`, `no_match`, `scope_refusal`) at known return paths. Middleware maps auth/validation/rate-limit/uncaught failures from status or exception type without parsing a body. Middleware ordering in the mounted-app setup must be tested before relying on context propagation.

Put a **mutable collector object** in the `ContextVar` before dispatch and mutate it in place from the synchronous route/engine. FastAPI propagates context into its worker thread, but replacing the `ContextVar` value inside that thread is not a reliable way to return updates to the outer ASGI middleware. Reset the context token in middleware `finally`; atomically seal/snapshot before reset. Late writes from timed-out or abandoned workers must be discarded so an event cannot mutate after emission or leak into a later request. Bound and synchronize collector writes (a short lock around appends/counter updates; never hold it across I/O), since optional retrieval work may use worker threads. Test thread-pool visibility, concurrent child records, sealing/late-write discard, reset on all exits, and capture of early returns/errors.

Do not write telemetry to the evidence store, add a public telemetry endpoint, add fields to `RegenoldAskResponse`, or invoke a live health probe. `include_telemetry` is a partner response option and `include_reasoning` can carry subqueries, free-text notes or model thinking; neither is an operational event channel.

## Event schema

Emit one event named `regenold.request.complete`, schema version `1`. Keys and values are bounded; dimensions have low cardinality. The event contains **no evaluation score or answer/reference content**. Example (illustrative values; `task_shape` and `turn_bucket` are omitted by default):

```json
{
  "event": "regenold.request.complete",
  "schema_version": 1,
  "request_id": "random-uuid",
  "service_version": "build-version",
  "worker_pid": 1234,
  "status_code": 200,
  "outcome": "answered",
  "sample_reason": "random",
  "total_ms": 6840,
  "cache": {
    "lookup": "miss",
    "lookup_ms": 0.04,
    "write": true,
    "skip_reason": null
  },
  "stage_ms": {
    "history_scope": 82,
    "intent": 0,
    "retrieval": 44,
    "context_render": 118,
    "prompt_build": 2,
    "answer_generation": 6509,
    "route_finalize": 7,
    "evidence_persist": 5
  },
  "retrieval": {
    "backend": "kb",
    "bm25_candidates": 4,
    "vector_candidates": 0,
    "graph_reads": 2,
    "graph_timeouts": 0,
    "context_chars_bucket": "4k-8k"
  },
  "provider_calls": [
    {
      "purpose": "stage2",
      "provider": "openai_wrapper",
      "leg": "primary",
      "model": "model-id-from-allowlist",
      "attempt": 1,
      "retry_kind": null,
      "duration_ms": 6500,
      "result": "ok",
      "error_kind": null,
      "finish_reason": "stop",
      "input_tokens": 4120,
      "output_tokens": 235,
      "usage_reported": true,
      "items_submitted": null,
      "billing_mode": "flat_subscription",
      "billing_region": null
    }
  ],
  "usage_coverage": {
    "calls_with_reported_usage": 1,
    "calls_without_usage": 0,
    "potentially_billable_calls_without_usage": 0
  },
  "stage2": {
    "served_by": "primary",
    "degraded": false
  },
  "rerank": {
    "calls": 0,
    "budget_skipped": 0,
    "failures": 0
  }
}
```

`stage_ms` values are wall-clock spans: parent spans include child spans, so **do not add them together**. Emit a bounded list of actual provider calls (for example, at most 12) and include a truncation count if a pathological fallback chain exceeds it. The list represents physical outbound calls, including retries and Bedrock model candidates—not merely the logical operation or final successful call. Sampling controls event emission, not in-flight collection, so forced failure/fallback events retain that request’s call history. Avoid exact prompt/output lengths; a coarse context-size bucket is sufficient if operationally needed. Allocate a small bounded collector per request; do not serialize an event for unsampled requests.

### Field rules

- `request_id`: random UUID for log correlation only; never a metric label and never joined to a user, tenant, evaluation row, evidence-chain ID or account.
- `service_version`, `worker_pid`: build and worker attribution. Process-local counters/health snapshots are per worker; do not read one worker as deployment-wide totals.
- `outcome`: fixed enum such as `answered`, `no_match`, `scope_refusal`, `validation_error`, `rate_limited`, `server_error`. It is an operational route outcome, **not a correctness label**.
- `task_shape`: omit by default. Even a coarse class (`definition`, `direct_article`, `list`, `exception`, `scenario`, `multi_turn`, `other`) may expose subject/intent. Include only after privacy review establishes a need; never log domain-specific classes, roles or classifier evidence. Use `unknown` rather than an LLM call just to populate telemetry.
- `turn_bucket`: omit by default or use only after privacy review; if ever needed, allowlist `single`, `2-3`, `4+`, `unknown`. Never store turns or message contents.
- `cache.lookup`: `hit`, `miss`, `not_reached`; `skip_reason` from a small enum such as `degraded_serve`, `low_confidence`, `empty_retrieval`, `not_eligible`, or `null`. Do not log cache key, hash or value.
- `retrieval.backend`, provider and model values are normalized against a fixed allowlist; unknown values map to `other`. Do not log full endpoint URLs or raw environment variables.
- Token counts are nullable, not fabricated zeroes. `usage_reported` distinguishes provider-reported zero from absent usage. For non-token APIs, capture numeric units such as rerank documents. Record counts only, never content or thinking.
- `retry_kind`, `result`, `error_kind` and `finish_reason` are bounded enums. Map errors to categories (`timeout`, `rate_limited`, `unauthorized`, `forbidden`, `server_error`, `connection_error`, `decode_error`, `empty_completion`, `degenerate_completion`, `truncated`, `provider_disabled`, `circuit_open`, `other`). Never include exception strings, response bodies, `Retry-After` values or arbitrary model error messages.
- `billing_mode`: `metered`, `flat_subscription`, `not_billable`, or `unknown`; include a normalized allowlisted region only where it changes the rate. Do not calculate dollar amounts in the request process. A central log consumer may join token/unit counts to a versioned provider/model/region/effective-date price schedule and must report pricing/usage coverage. Never invent a per-call marginal cost for a flat Claude Max subscription or call a billing API on the request path.

## Measurement boundaries and current runtime seams

1. **ASGI boundary — `app/main.py` / mounted `api_v1`:** total application time, status, log-only request ID, operational outcome, sampling reason. Filter only the ask route, not health endpoints. Observe status and final-body timing without inspecting body content.
2. **Route — `app/routes/regenold.py`:** history/scope/safety and intent duration; cache lookup/result; `ask_compliance_question`; route finalization and evidence-store write. Record whether cached/written/skipped and a controlled skip reason. The process-local 512-entry `_ENGINE_CACHE` has a per-request lookup result; prefer it to deltas of shared hit/miss counters.
3. **Engine — `app/engines/_graph_rag_impl.py`:** parse, total retrieval, context/prompt build and Stage-2 spans; optional sufficient-context hop counts. Use existing `GraphContext`/`graph_stats` for path/node/Stage-2 operational metadata. Do not infer from `retrieval_path="kb_fallback"` that no graph or semantic supplement ran.
4. **Stage-2 physical calls — `app/llm/openai_wrapper_provider.py`, `app/llm/bedrock_client.py`, and Stage-2 policy:** capture each actual HTTP/SDK dial, including internal 429/degeneracy retries and every Bedrock fallback candidate. Record physical dials separately from the logical primary/fallback disposition so calls are neither double-counted nor hidden. Track the actual serving leg separately from attempts. Provider response models currently default some token counts to zero; preserve a parse-time `usage_reported` bit so missing usage is not interpreted as zero tokens.
5. **Retrieval/context external work:** record aggregate `render_kg_context`, graph-read counts/timeouts at the graph-client execution boundary (or a common wrapper only after confirming all callers use it), and local vector/TurboQuant recall separately from external embedding calls when active. Record read-kind enums and row counts only. Component construction does not prove a component was called.
6. **Reranking — `app/engines/cohere_rerank.py`:** instrument at the actual network boundary for duration, outcome and budget skip. `rerank_stats()` and Stage-2 transport counters are process-global; never reset them per request or compute concurrent per-request deltas. Add request-local events at the call site.

Avoid spans for deterministic Python helpers until evidence shows local compute is material. Stage-0/scope provider calls use the same bounded `provider_calls` representation with an allowlisted purpose (`scope`, `intent`, `rewrite`, `stage2`, `rerank`, `embedding`). For non-token APIs record billable units. `/healthz/llm` counters are a per-worker health diagnostic, not request latency/billing truth; its probe can make a paid call and must not be invoked to populate this series.

### Minimal first instrumentation slice

If and when the quality-evaluation contract is in place, keep the first observability release small: (1) root ASGI total duration/status/outcome and sampling, (2) route cache hit/miss/write-or-skip, (3) engine retrieval span plus Stage-2 total/serving leg, and (4) per-dial provider duration/result/usage across primary, retry and fallback. Add local graph/vector/rerank detail only if this baseline shows it is necessary to explain an operational issue. Do not initially add per-function tracing, a pricing database, durable request storage or a new metrics dependency.

## Cost and resource accounting

Capture provider-reported usage and billable units at the actual call boundary; estimate spend downstream, not on the request path:

- Maintain a versioned price map keyed by normalized provider, model, region and effective date. Apply cached-token tiers only when separately reported.
- Report priced subtotals with usage/pricing coverage. Missing usage or an unmapped model contributes to unknown/unpriced counts; do not substitute zero or present a partial subtotal as total spend.
- Claude Max tunnel traffic is subscription-backed. Record token volume and `billing_mode=flat_subscription`, not per-call marginal dollars. Any amortized allocation needs a separate finance decision and a reliable billing-period denominator.
- For rerank/external embedding APIs priced per request/document, record counts and estimate only against a maintained schedule. For Aura/graph reads and local vector operations, report usage/latency; use the service bill for shared infrastructure cost.
- Include every physical call in metered totals, including failed attempts that were billed, if usage and pricing are known. The final successful model is not the whole request cost.

Provider usage and invoices remain authoritative. The event is an engineering estimate, not an accounting ledger and not a quality signal.

## Privacy, security and retention

**Never record:** request/response bodies; raw/normalized questions or history; question hashes; answer/citations/evidence snippets; prompt/system/context text; model `thinking`; reasoning-trace notes/subqueries; auth headers/API keys; IP or IP hash; user/tenant/email; full endpoint URLs; raw exceptions or provider response bodies. Task/turn classes are potentially sensitive and omitted unless explicitly justified and privacy-reviewed.

The opt-in reasoning trace and evidence chain serve different purposes and can contain request text or answer material. Do not copy them into operational telemetry or attach their IDs to the event. This design does not revise existing evidence-store retention/access policy. It also does **not** make existing logs safe: code has log sites that include raw exception strings/provider errors. Inventory and redact those separately before claiming the entire log stream is privacy-safe.

Keep request-level operational events access-controlled, use a short retention period (initial suggested maximum: 14 days), and retain only aggregates longer. Review actual log redaction and retention before enabling production sampling. Construct events from an explicit allowlist; never serialize `Request`, headers, provider response/exception objects or `ReasoningTrace`. Normalize model/provider values. Telemetry must fail-soft: serialization/logging failure cannot change the answer or status.

## Sampling and operational views

Use an independent random request sample (suggested initial **10%**) for complete events. Always emit a bounded event for provider failure/fallback, timeout, degraded serve, server error or a slow request over a pre-set threshold. Mark `sample_reason` as `random`, `failure`, `fallback` or `slow`. Use only the unbiased random sample for p50/p95; forced anomaly events are diagnostic because they over-sample the tail. Do not sample on request text/hash.

Aggregate in the existing log pipeline; do not add Prometheus/OpenTelemetry dependencies in the first tranche. Useful low-cardinality operational charts include:

- request count and end-to-end `request_duration_ms` histograms by operational outcome, cache result and serving leg;
- stage/provider latency distributions by provider, normalized model, purpose and result;
- input/output token totals and unknown-usage counts;
- primary attempts, physical retries, fallback attempts/successes, deterministic degraded serves, timeouts and truncated/degenerate completions;
- cache hit/miss/write/skip, graph calls/timeouts/rows, rerank/embedding calls/failures/budget skips;
- known metered cost subtotal by price-schedule version plus completeness/unknown-call coverage, and separate flat-subscription token volume.

Do not create metric labels from request ID, PID, user/tenant, task text, prompt hashes, arbitrary model IDs or other unbounded values. Keep `request_id` only in sampled event records. Distinguish cache hits and intentional Stage-2 skips from failed/fallback-served requests. These charts support the later performance stage; they do not alter the quality gate order.

## Rollout and acceptance gates

### Phase 0 — establish the quality decision record

Before treating a performance baseline as a decision instrument, record a versioned, paired answer-correctness baseline and reference-correctness baseline for the exact tested application/configuration, with cohort/gold/rubric/judge provenance and the limitations above. Report all remaining reconstructed axes and relevant multi-turn checks. Require the project’s live gates for later behavior changes. If the available evidence cannot resolve answer or reference regression risk, mark the quality conclusion inconclusive; do not allow a future speed/cost result to fill that gap.

### Phase 1 — schema, privacy and isolation tests

Implement any collector behind `REGENOLD_REQUEST_TELEMETRY=0` by default. Test allowlisted serialization with sentinel question, answer, token, header and `thinking` strings; none may appear. Test bounded errors, nullable usage, normalized models, event/call-count limits and fail-soft behavior. Test shared collector visibility in FastAPI’s synchronous thread-pool route, concurrent child writes, sealing/late-write discard, reset on every exit, and no cross-request state leakage.

### Phase 2 — local/stubbed operational verification

With fake providers, assert durations/call records for cache hit/miss, no-Stage-2, primary success, physical primary retry, Bedrock fallback/model rollover, provider failure, rerank budget skip, graph timeout, validation/early refusal, and evidence-store failure. Verify per-request serving-leg provenance against the stubbed calls. Confirm normal and `include_telemetry=true` response bodies are unchanged; telemetry must not change status, cache or answer behavior.

### Phase 3 — telemetry-only canary

After privacy/retention review, enable a small sample (suggested 10%) on one canary build **without a behavior change**; forced events are for diagnosis only. Do not run live health probes to populate the series. Review event volume/size, redaction, log cost and worker attribution. Confirm no content/secrets, no cross-request state, and that primary/retry/fallback examples agree with the wire serving-leg record. Measure instrumentation overhead against a pre-agreed bound; do not invent an acceptable overhead after looking at results. Keep a rollback switch; disabling telemetry must leave the request path unchanged.

### Phase 4 — performance baseline for a quality-qualified build

Use only the unbiased random sample for p50/p95, stage distributions, usage coverage and cache rates. If the relevant cohort has too few random observations, report “insufficient sample” and collect longer—do not promote forced anomaly events into the percentile sample. Join metered token/unit usage to the versioned schedule downstream, document missing-usage/pricing coverage, and compare aggregate estimates to invoices before any budget decision. Keep flat-subscription volume separate. This phase measures performance; it does not establish correctness.

### Phase 5 — optimize only after quality gates pass

For a behavior-changing optimization, run one lever at a time on the same fixed/stratified paired rows and verify liveness/provenance. First decide answer correctness (including row-level regressions), then reference correctness (including zero newly dropped gold heads), then inspect every remaining rubric axis and applicable multi-turn checks. A confirmed answer regression or a new gold-head loss blocks promotion even if aggregate accuracy, conciseness, latency or cost improves. Do not treat intervals crossing zero or a non-significant test as a non-inferiority pass. After the quality gates pass, use the performance baseline to select a measured hotspot (Stage-2 tail, prompt token volume, unnecessary paid call, cache miss, external rerank). Pure code extraction requires recorded-draw byte-identical replay; behavior changes need the quality gates. Telemetry proves execution/resource use only.

## Scope and non-goals

This design does not implement quality scoring, an answer verifier, a cost ledger, content tracing, customer analytics, or a new endpoint. It assumes the existing `structlog` dependency/log pipeline and avoids new runtime dependencies, durable request storage and response-schema changes. It does not claim that the full existing application log stream is privacy-safe. The goal is to observe the request path safely so that performance can be understood **after** answer correctness, reference correctness and the rest of the evaluation metrics have been addressed.

Related review: `docs/reviews/r448-high-value-performance-audit-2026-09-28.md`.
