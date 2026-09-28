# R448 — lightweight request telemetry design

**Date:** 2026-09-28  
**Status:** Design only; no runtime changes made.

## Goal

Collect enough trustworthy data to answer, by request class and serving path:

- Where request wall time goes (p50/p95 by phase and end to end).
- Which LLM and retrieval calls actually ran; how long each took; whether there were retries, timeouts, fallbacks, or degraded answers.
- What the engine cache did (hit/miss/write/skip) and whether external calls were avoided.
- How many input/output tokens providers reported and what metered spend can reasonably be estimated.

Do this without storing question/answer text, prompts, legal citations, model reasoning, credentials, IP addresses, or user/tenant identifiers; without changing the response schema; and without adding a metrics service or runtime dependency.

## Recommendation

Use a small **request-local telemetry record** carried in a `ContextVar`, measured with `time.perf_counter_ns()`, and emitted as one bounded structured log event after the ask response body has been handed to the ASGI server. Use the existing `structlog` dependency and deployment log pipeline. Add spans only at meaningful boundaries and actual external-call choke points—do not time every helper in the large route/engine modules.

A pure-ASGI middleware on the root `app` (outside the mounted `api_v1`) should own the request start time, random log-only `request_id`, status code, sampling decision, and final emission. It should filter to `POST /api/v1/regenold/eu-ai-act/ask`; it must not inspect or log request/response bodies or headers. Put a **mutable collector object** in the `ContextVar` before dispatch and mutate that object in place from the synchronous route/engine. FastAPI propagates context into the worker thread, but replacing the `ContextVar` value inside that thread is not a reliable way to return updates to the outer ASGI middleware. Make bounded collector writes thread-safe (for example, a short lock around appends/counter updates; never hold it over I/O), because optional retrieval work may run in worker threads. Add tests proving the shared collector is visible in FastAPI’s thread-pool route, concurrent child records are not lost/corrupted, and state is reset on all exits. Middleware `finally` captures validation/auth/rate-limit errors and early scope/refusal returns as well as normal answers.

Do not export by writing to the evidence store, adding a public telemetry endpoint, adding fields to `RegenoldAskResponse`, or invoking a live health probe. `include_telemetry` is a partner response option, and `include_reasoning` can carry subqueries, free-text notes, or model thinking; neither is a suitable operational event channel.

## Event schema

Emit a single event named `regenold.request.complete`, schema version `1`. Keep keys fixed, values bounded, and all metric dimensions low-cardinality. Example (illustrative values):

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
  "task_shape": "list",
  "turn_bucket": "single",
  "cache": {
    "lookup": "miss",
    "lookup_ms": 0.04,
    "write": true,
    "skip_reason": null
  },
  "stage_ms": {
    "history_scope": 82,
    "intent": 0,
    "engine_parse": 3,
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
      "model": "claude-opus-5-5",
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
      "estimated_cost_usd": null,
      "price_schedule": null
    }
  ],
  "usage_coverage": {
    "calls_with_reported_usage": 1,
    "calls_without_usage": 0,
    "potentially_billable_calls_without_usage": 0
  },
  "billing_mode_counts": {
    "flat_subscription": 1,
    "metered": 0,
    "unknown": 0
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

The final schema may flatten stage durations to avoid nested JSON depth. `stage_ms` values are wall-clock spans: parent spans include child spans, so **do not add them together**. Emit only a bounded list of actual provider calls (for example, up to 12); include a truncation count if a pathological fallback chain exceeds it. Avoid exact prompt/output text lengths unless needed; a coarse context-size bucket is enough to investigate prompt growth. Allocate a small bounded collector for every request so forced failure/fallback/slow events have full call history; apply random sampling only to event emission. Record inexpensive enums/counts even on unsampled requests, but avoid formatting/serializing an event unless it will be emitted.

### Field rules

- `request_id`: cryptographically random UUID for log correlation only; never a metric label and never joined to a user/tenant or evidence-chain id.
- `service_version`, `worker_pid`: identify the deployed build and worker. Process-local counters/health snapshots are per worker; do not interpret one worker as deployment-wide totals.
- `outcome`: fixed enum such as `answered`, `no_match`, `scope_refusal`, `validation_error`, `rate_limited`, `server_error`.
- `task_shape`: allowlisted coarse class: `definition`, `direct_article`, `list`, `exception`, `scenario`, `multi_turn`, `other`, `unknown`. If the current deterministic classifier cannot supply one cheaply, use `unknown`; do not call an LLM just to instrument.
- `turn_bucket`: `single`, `2-3`, `4+`, `unknown`; never store turns or message contents.
- `cache.lookup`: `hit`, `miss`, `not_reached`; `skip_reason`: a small enum such as `degraded_serve`, `low_confidence`, `empty_retrieval`, `not_eligible`, or `null`. No key, key hash, or cache value is logged.
- `retrieval.backend` and provider/model values are normalized against a fixed allowlist; unknown values map to `other`. Do not log a full endpoint URL or raw environment variable.
- `provider_calls[].input_tokens` / `output_tokens`: nullable, not fabricated zeroes. `usage_reported` distinguishes “provider reported zero” from “usage absent.” `items_submitted` can capture rerank/document counts when token usage is not reported. Store only numeric counts, never content or thinking. The array represents physical outbound calls, including retries and Bedrock model candidates—not merely the final successful logical operation.
- `retry_kind`, `result`, `error_kind`, and `finish_reason`: bounded enums. `error_kind` maps exceptions/statuses to categories (`timeout`, `rate_limited`, `unauthorized`, `forbidden`, `server_error`, `connection_error`, `decode_error`, `empty_completion`, `degenerate_completion`, `truncated`, `provider_disabled`, `circuit_open`, `other`). Do not include exception strings, response bodies, `Retry-After` header contents, or arbitrary model error messages.
- `billing_mode`: `metered`, `flat_subscription`, `not_billable`, or `unknown`; include a normalized, allowlisted region only where it changes the rate. Do not calculate dollar amounts in the request process. The collector records tokens/units, billing mode, provider, normalized model, and region; the central log consumer joins those fields to a versioned price schedule and reports known totals plus usage/pricing coverage. Never invent a per-request price for a flat Claude Max subscription or call a billing API from the request path.

## Measurement boundaries and existing seams

1. **ASGI request boundary — `app/main.py` / mounted `api_v1`:** total application time, status, request ID, outcome, sample decision. This includes pre-route handling and guarantees a record for early returns. Filter strictly to the ask endpoint, not health endpoints.
2. **Route preparation and scope — `app/routes/regenold.py`:** history/scope/safety and intent-classifier duration; cache lookup duration/outcome; `ask_compliance_question` duration; route finalization and evidence-store write duration. Record whether the result was cached, written, or skipped and the controlled skip reason. The route currently has a process-local 512-entry `_ENGINE_CACHE`; its per-request get result is better telemetry than subtracting shared hit/miss counters.
3. **Engine — `app/engines/_graph_rag_impl.py`:** parse, retrieval, optional sufficient-context hop, context/prompt construction, deterministic answer, and Stage-2 total spans. Use existing `GraphContext`/`graph_stats` fields for retrieval path, node counts, Stage-2 landed/failed/serving-leg; do not infer that `retrieval_path="kb_fallback"` means no graph or semantic supplement ran.
4. **Stage-2 physical calls — `app/llm/openai_wrapper_provider.py` and `app/llm/bedrock_client.py`:** capture one event per actual HTTP/SDK dial, including 429 retry, wrapper degenerate retry, and each Bedrock model candidate in a fallback chain. Responses already carry elapsed time and (when supplied) usage counts, but the OpenAI-compatible provider’s retry is internal and the Bedrock chain may make multiple dials. Capture both physical dial count and logical primary/fallback outcome so the two are not conflated. Track actual `stage2_served_by` separately from attempted legs.
5. **Retrieval/context external work:** add an aggregate `render_kg_context` span and graph-read counts/timeouts at a shared bounded-read seam; record only read-kind enums and row counts. Time local vector/TurboQuant recall separately from external embedding calls if those are active. Do not treat constructing optional components as proof they were called.
6. **Reranking — `app/engines/cohere_rerank.py`:** instrument at the actual network choke point and record call duration, outcome, and budget skip. `rerank_stats()` and Stage-2 transport counters are process-global; do not reset them per request or compute concurrent per-request deltas from them. Add request-local counts at the call itself.

Avoid detailed spans for deterministic Python helpers until the boundary data shows local compute is material. Stage-0/scope provider calls should use the same `provider_calls` format with a bounded `purpose` enum (`scope`, `intent`, `rewrite`, `stage2`, `rerank`, `embedding`). For non-token APIs, record their billable units (for example, rerank documents) and model/provider. The `/healthz/llm` counters remain a health diagnostic, not the request latency or billing source of truth; its counters are per worker and it can issue a paid probe.

## Cost accounting

Capture usage and billable units at the provider-call boundary; estimate spend in the log consumer, not in the request:

- Maintain a small, versioned pricing map keyed by normalized provider, model, region, and effective date. For a known metered model, compute `input_tokens × input_rate + output_tokens × output_rate`; account for cached-token tiers only if the provider reports them distinctly.
- Report priced subtotals together with coverage. Missing usage or an unmapped model contributes to an `unknown`/`unpriced` count; never substitute zero or present a partial subtotal as total spend.
- Claude Max tunnel traffic is subscription-backed. Record token volume and `billing_mode=flat_subscription`, but do not assign a per-call marginal cost. Amortized subscription cost needs a separate finance decision and reliable billing-period denominator.
- For Cohere reranking, external embeddings, or other APIs priced by request/document rather than tokens, record request/document counts and estimate only against a maintained price schedule. For Aura/graph reads and local vector operations, record calls and latency; use the relevant service bill for actual shared infrastructure cost rather than mislabeling a per-request estimate.
- Sum costs over **all physical calls**, including failed/denied attempts that were billed, where usage/pricing is known. The final successful model alone is not the full request cost.

The provider’s usage and the provider invoice remain authoritative; this event is an engineering estimate, not accounting.

## Privacy, security, and retention

**Never record:** request/response bodies; raw or normalized question/history; question hashes (guessable and linkable); answer/citations or evidence snippets; prompt/system/context text; model `thinking`; free-form reasoning-trace notes/subqueries; raw auth headers/API keys; IP or IP hash; user/tenant/email; full endpoint URLs; raw provider exceptions or response bodies.

The existing opt-in reasoning trace and evidence chain have different purposes and can carry request text or answer material. Do not copy them into operational telemetry, and do not attach their ids to the new request event. This design does not revise the existing evidence-store retention/access policy; it ensures the new latency/cost stream does not duplicate its content. It also does **not** retroactively make existing application logs safe: the codebase has log sites that include raw exception strings and provider errors. Inventory and redact those separately before describing the entire log stream as privacy-safe. Keep request-level operational events access-controlled, set a short retention period (suggested initial maximum: 14 days), and retain only aggregate histograms/counters longer. Review the platform’s log redaction and retention settings before enabling the production sample.

Use a schema-construction allowlist rather than serializing `Request`, headers, provider response objects, exception objects, or `ReasoningTrace`. Sanitize model/provider names to known ids. Telemetry must fail-soft: serialization or logging failure must not change the answer or status.

## Sampling and aggregate metrics

Use a random request sample (suggested initial **10%**) for the complete event. Always emit a bounded event for provider failure/fallback, timeout, degraded serve, server error, or a slow request over a pre-set threshold. Mark `sample_reason` as `random`, `failure`, `fallback`, or `slow`; use only the unbiased `random` sample to calculate p50/p95, and use forced events for diagnosis (otherwise the tail is intentionally over-sampled). Do not use request text/hash to choose a sample.

Aggregate from the existing log pipeline; do not add Prometheus/OpenTelemetry dependencies in the first tranche. Suggested low-cardinality charts/counters:

- request count and `request_duration_ms` histogram by `outcome`, `task_shape`, cache result, and serving leg;
- per-stage and provider-call latency histograms (p50/p95), separated by provider, normalized model, purpose, and result;
- input/output token totals and unknown-usage count by provider/model/purpose;
- primary attempts, physical retries, fallback attempts/successes, deterministic degraded serves, timeouts, and truncation/degenerate rejection counts;
- engine cache hit/miss/write/skip counts; graph-read calls/timeouts/rows; rerank and embedding calls/failures/budget skips;
- known metered cost subtotal by provider/model/price-schedule version, its completeness/unknown-call coverage, plus separate subscription token volume.

Never use `request_id`, PID, question class text, prompt hash, tenant, or arbitrary model id as unbounded metric labels. Use `request_id` only in individual sampled log events. Ensure outcome breakdowns distinguish cache hits and intentional Stage-2 skips from failed or fallback-served answers.

## Rollout and acceptance gates

### Phase 0 — schema and privacy tests

Implement the collector and event schema behind `REGENOLD_REQUEST_TELEMETRY=0` by default. Add tests for allowlisted serialization (sentinel question, answer, token, header, and `thinking` strings never appear), error redaction, nullable token usage, model normalization, bounds on event size/call count, and no exception escaping the telemetry layer.

### Phase 1 — local/stubbed verification

With fake provider responses, assert accurate spans for cache hit/miss, no-Stage-2, primary success, physical primary retry, Bedrock fallback/model rollover, provider failure, rerank budget skip, graph timeout, validation/early refusal, and evidence-store failure. Test concurrent requests and ContextVar reset to prove no data crosses between requests. Verify the normal and `include_telemetry=true` HTTP response bodies are unchanged.

### Phase 2 — low-rate canary

Enable 10% sampling on one canary deployment for a fixed period (for example, seven days), with forced failure/fallback/slow events. Do not run live health probes to populate the series. Review actual event volume/size, logging cost, redaction, and worker attribution. Proposed acceptance: no request/response text or secrets in the event; no cross-request state leakage; telemetry-specific overhead below 1% of observed request p95 and no material response-size change; every primary/fallback/retry example agrees with the wire serving-leg record.

### Phase 3 — establish baseline

Use the unbiased random sample for p50/p95, token distributions, cache hit rate, and per-class service time. If a class has too few random observations to estimate a percentile, report “insufficient sample” and extend collection—do not promote forced anomaly events into the percentile sample. In the existing log consumer, join metered token/unit usage to the versioned price map and compare aggregate estimates with invoices; document usage/pricing coverage and error before using estimates for budget decisions. Keep flat-subscription usage separate from metered spend.

### Phase 4 — optimize one measured hotspot at a time

Use this baseline to select work (e.g., Stage-2 transport/fallback tail, excessive context tokens, external rerank calls, cache misses). Change one lever per paired run. Bind telemetry to the existing live `ab_judge` / `easyhard_ab` and gold-retention gates for answer-changing changes; the telemetry itself proves execution and resource consumption, not answer quality. For pure extraction, require recorded-draw byte-identical replay. Keep the rollback switch available; disabling telemetry must leave the answer/cache behavior unchanged.

## Scope and non-goals

This design creates operational observability, not tracing of legal content, a new cost-accounting ledger, quality scoring, or a customer analytics product. It assumes the currently present `structlog` dependency and log pipeline; it intentionally avoids a Prometheus/OpenTelemetry package, database writes, and a new endpoint. First measure request boundaries and paid/network calls; do not instrument thousands of helpers or change model, retrieval, timeout, cache, prompt, or answer policies in the instrumentation rollout.

Related review: `docs/reviews/r448-high-value-performance-audit-2026-09-28.md`.
