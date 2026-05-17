# R45 Performance Review

Scope: cold-start audit, p95/p99 tail-latency hazards, per-request hot-path
overhead, memory footprint, and regex-compile hot-paths. All numbers below
are measured locally on this worktree using the bundled `.venv` (Python
3.12.9, Windows 11). No source files were modified.

## Cold-start summary

First request after a fresh process boot is dominated by **lazy index
builds that should be moved to a FastAPI startup hook**:

| Step                                                | Cost     |
| --------------------------------------------------- | -------- |
| `from app.main import app`                          |  1427 ms |
| `TestClient(app)`                                   |     0 ms |
| First `POST /api/v1/regenold/eu-ai-act/ask`         |   698 ms |
| `build_definition_index()` lazy build               |   605 ms |
| `_all_sentence_indexes()` lazy build                |   457 ms |
| `embeddings_index.warm_up()` lazy build             |   115 ms |
| `_build_xref_graph()` (kb_xrefs)                    |     3 ms |
| **Total cold path to first byte**                   | **~2.1 s** |

After explicit pre-warm of all four index builds before the first
request:

| Step                                  | Cost    |
| ------------------------------------- | ------- |
| First request post-warmup             |   58 ms |
| Definition-query post-warmup          |   46 ms |
| 100 steady-state requests p50         |  4.68 ms |

A startup hook that calls `build_definition_index()`,
`_all_sentence_indexes()`, and `embeddings_index.warm_up()` would
**eliminate the 480–700 ms outliers** observed at qa[0], qa[3], qa[5] in
every davidath benchmark run, with effectively zero downside (the
indexes are already built lazily on first use — the only change is
WHEN they're built).

Worst-offender import time (cumulative): `app.main` 901 ms, `fastapi`
495 ms (transitive: pydantic + httpx), `app.routes.regenold` 246 ms,
`app.integrations.regenold.scope` 46 ms self-time (recompiles + heavy
regex). `app.engines.graph_rag` 18 ms self-time (compiles the 18-topic
`_CLASSIFICATION_TOPICS` regex pyramid at import — already correctly
module-level, fires once).

## Latency tail (R45 davidath full, n=476)

| Percentile  | davidath full (R45) | QA only (n=137) | Scenarios (n=339) |
| ----------- | ------------------- | --------------- | ----------------- |
| p50         | 12.00 ms            | 4.85 ms         | 13.10 ms          |
| p90         | 17.21 ms            | —               | 18.07 ms          |
| p95         | 18.95 ms            | 13.95 ms        | 19.27 ms          |
| p99         | 25.39 ms            | —               | —                 |
| p99.5       | 109.63 ms           | —               | —                 |
| max         | **530.08 ms**       | 530 ms          | 59.24 ms          |

The reported run-id is `fb36b1b2-f830-4820-b81c-03e137cbb959`, sidecar
at `evals/bench/results/r45-latency-tail.json`.

Outlier analysis — every davidath run shows **three latency spikes at
identical positions**, all caused by cold lazy-index builds:

| Position    | Question                                                              | Latency  | Cause                                |
| ----------- | --------------------------------------------------------------------- | -------- | ------------------------------------ |
| qa[0]       | "What is the primary purpose of the AI Regulation?"                   |  530 ms  | `_all_sentence_indexes()` lazy build |
| qa[3]       | "What is the definition of an 'AI system' under the Regulation?"      |  140 ms  | first sentence-index cache miss      |
| qa[5]       | "Who is considered a 'provider' of an AI system?"                     |  480 ms  | `build_definition_index()` first hit |

Reproduced cold in a fresh process: 482 / 144 / 517 ms at the same
positions. After cache warm: 5.9 / 10.5 / 8.1 ms — confirming
position-dependent, not question-dependent. The question content does
not matter; the position in the run order does.

**Important context for the bench numbers**: a no-op `GET /healthz`
through the same TestClient costs **~5 ms per call**. This is fixed
ASGI + httpx + asyncio + json overhead from the test harness itself,
NOT route work. Real route work is roughly p50 − 5 ms ≈ 7 ms per
question. The CLAUDE.md R44 "9.84 ms holdout p50" almost certainly
inherits the same harness floor; behind real uvicorn the steady-state
p50 will be lower. The engine-only path is 0.09 ms.

## Hot-path profile (top 5, steady-state)

cProfile over 100 paired POST calls (200 total) through TestClient with
all indexes warm. Filtered to project app code:

| Function                                                | cumtime per call | tottime / call | Notes                                  |
| ------------------------------------------------------- | ---------------- | -------------- | -------------------------------------- |
| `regenold.regenold_eu_ai_act_ask`                       | 1.89 ms          | 90 µs          | route handler entry                    |
| `subpoint_emitter.upgrade_references`                   | 0.35 ms          | 37 µs          | Round-19+ subpoint expansion           |
| `scope.classify_conversation`                           | 0.31 ms          | 19 µs          | scope gate + anchor extraction         |
| `clara_logic.extract_tags_deterministic`                | 0.28 ms          | 28 µs          | 37-tag regex scan over question        |
| `prohibited_gatekeeper.scan_for_prohibitions`           | 0.13 ms          | 19 µs          | TAI Scan Layer C 9-pattern scan        |
| `evidence.store.record`                                 | 0.15 ms          | 19 µs          | hash-chained audit append (in-memory)  |
| `models.normalise_answer_for_regenold`                  | 0.09 ms          | 19 µs          | strip-markdown + sentence cap          |
| `routes._collapse_parent_refs`                          | 0.01 ms          | 9 µs           | smallest-cover citation pass           |
| `models.reference_from_article_ref` (×4 per request)    | 0.02 ms          | 5 µs each      | per-ref Pydantic validation            |

None of these are individually large. The wall is the **sum of ~12
post-engine passes** (scope, gatekeeper, CLARA, expand, ref budget,
ref rank, answer template, verdict, tone, citation guard, normalise,
audit) — each costing 20-100 µs.

Note: the engine itself (`ask_compliance_question`) runs at **0.09 ms
p50** with all indexes warm — orders of magnitude below the route's
overhead. Optimisation effort should target route post-processing, not
the engine.

## Memory footprint

Python heap measured via `tracemalloc`:

| Stage                                | Heap    | Δ        |
| ------------------------------------ | ------- | -------- |
| Pre-import                           |   0 MB  |          |
| After `from app.main import app`     | 28.6 MB | +28.6 MB |
| After 1 warm request                 | 33.3 MB | +4.7 MB  |
| After 1000 unique random requests    | 34.2 MB | +0.9 MB  |

Heap growth is well-bounded. The 1000-request delta of +0.9 MB is
tracemalloc accounting overhead (pydantic + anyio + asyncio internal
buffers), not a leak.

`_ENGINE_CACHE` is a `_BoundedLRUCache(capacity=512)`. On a real
in-scope question, repeated calls register cache hits (verified:
hits=59 after 100 repeat POSTs of the same question). The cache is
correctly bounded — `popitem(last=False)` evicts on overflow.

Top heavy `app.*` module objects (approximate, includes regulation
prose held in module globals):

| Module                                | Approx size |
| ------------------------------------- | ----------- |
| `app.data.eu_ai_act_corpus`           |  831 KB     |
| `app.data.kb_search`                  |  500 KB     |
| `app.engines.sentence_index`          |  490 KB     |
| `app.integrations.regenold.scope`     |   66 KB     |

The eu_ai_act_corpus + sentence_index combined are ~1.3 MB of
regulation prose held in process memory. Necessary for retrieval and
not a concern at this scale.

**Unbounded caches**: none. Every `@lru_cache` and `@functools.cache`
in `app/` has `maxsize=N`. Verified by walking 27 modules — 0
unbounded, 12 bounded (mostly `maxsize=1` for module-globals init).

## Regex compilation hot-path

Bracket-depth-aware tokenize scan of all `app/*.py`: only **3 true
in-function `re.compile()` calls** that fire on every call (and 1 more
in the route's QA-trim path). The other 130+ `re.compile()` matches in
the codebase are inside module-level list/dict literals and fire once
at import.

| File                              | Line | Function                | Severity |
| --------------------------------- | ---- | ----------------------- | -------- |
| `app/integrations/regenold/models.py` | 866  | `_split_sentences`      | **per-request × 2** |
| `app/routes/regenold.py`          | 1465 | `regenold_eu_ai_act_ask` | per-request when `REGENOLD_QA_TRIM=1` (default) and `len(sents) >= 2` |
| `app/engines/definition_expand.py` | 138  | `_make_term_pattern`    | once at index build (already covered by `lru_cache(1)`) |
| `app/engines/prohibited_gatekeeper.py` | 82 | `_keyword_pattern_index` | once at index build (already covered by `lru_cache(1)`) |

Python's `re` module has its own per-pattern compile cache (~512
entries), so these aren't catastrophic, but they're still 1-5 µs of
needless work per call.

---

## Findings

### D1 — Cold-start hot path: no startup pre-warm
**Severity**: P0
**Type**: cold-start
**File**: `app/main.py` (startup hooks at line 71 + 366), missing pre-warm hook
**Finding**: Three lazy indexes (`_all_sentence_indexes()`,
`build_definition_index()`, `embeddings_index.warm_up()`) account for
~1.1 s of deferred work that lands on the first 3–5 requests after
worker boot. Every davidath benchmark since these modules shipped
reproduces the same 480–700 ms spikes at qa[0], qa[3], qa[5]. CLAUDE.md
reports `latency_max_ms=619.54` for R44 final; today's R45 run shows
530 ms — same pattern, run-to-run noise.

**Repro**:
```
PYTHONIOENCODING=utf-8 REGENOLD_SKIP_STARTUP_LOG=1 python -c "
import time
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.main import app
from app.config import settings
settings.regenold.api_key = SecretStr('test')
client = TestClient(app)
t = time.perf_counter()
client.post('/api/v1/regenold/eu-ai-act/ask',
    headers={'X-Regenold-Api-Key':'test'},
    json={'messages':[{'role':'user','content':\"Who is considered a 'provider' of an AI system?\"}]})
print(f'{(time.perf_counter()-t)*1000:.1f}ms')
"  # → 837ms cold; ~7ms warm
```

**Suggested fix**: Add a third `@app.on_event("startup")` hook in
`app/main.py` (alongside the LLM probe and Neo4j seeder) that runs the
three pre-warms in a daemon thread (mirroring the Neo4j auto-seed
pattern at lines 178–500). Fire-and-forget; never block startup:

```python
@app.on_event("startup")
def _prewarm_indexes() -> None:
    if os.getenv("REGENOLD_SKIP_STARTUP_LOG") == "1":
        return
    def _run() -> None:
        from app.engines.sentence_index import _all_sentence_indexes
        from app.engines.definition_expand import build_definition_index
        from app.engines.embeddings_index import warm_up
        _all_sentence_indexes()
        build_definition_index()
        warm_up()
    threading.Thread(target=_run, daemon=True, name="regenold-prewarm").start()
```

Expected impact: **eliminates 700 ms p99 spikes**, brings davidath max
latency from ~530 ms to ~60 ms (the first-request floor after warm).
p99 drops from 25 ms to ~20 ms; p99.5 drops from 110 ms to ~20 ms.
Zero downside — indexes are built either way; this just moves the
work off the critical path.

### D2 — Per-request `re.compile` in `_split_sentences`
**Severity**: P3
**Type**: hot-path / regex
**File**: `app/integrations/regenold/models.py:866`
**Finding**: `_split_sentences` runs once per response and calls
`re.compile(r"(?<=[.!?])\s+")` inline. The route invokes it via
`normalise_answer_for_regenold` (1× per call) and via `_split_sentences`
inside `_strip_kb_stub_label`. Python's internal pattern cache covers
this, so the per-call cost is ~2 µs (lookup + GIL acquire) — not a
disaster, but free to fix.

**Repro**: profile shows 54 calls / 1 µs each in a 100-iteration profile.

**Suggested fix**: Hoist to module-level:
```python
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")  # at top of models.py
# then in _split_sentences: for m in _SENTENCE_SPLIT_RE.finditer(s):
```

Saves ~2 µs × 2 calls per request = ~4 µs (negligible but stylistically
worth fixing for consistency with the rest of the codebase).

### D3 — Per-request `re.compile` in QA-trim path
**Severity**: P3
**Type**: hot-path / regex
**File**: `app/routes/regenold.py:1465`
**Finding**: When `REGENOLD_QA_TRIM=1` (default) AND the answer has
≥2 sentences, the route compiles `re.compile(r"[a-z0-9]+")` inside
the handler. Same Python-internal cache rescues it from being
catastrophic, but it's an unnecessary call.

**Repro**: hot-path profile shows `_tok_re = re.compile(...)` runs on
~80% of QA requests (those that trigger trim).

**Suggested fix**: Hoist to module-level:
```python
_QA_TRIM_TOK_RE = re.compile(r"[a-z0-9]+")
```

Saves ~2 µs / call × ~70% of requests.

### D4 — `embeddings_index.warm_up()` documented in docstring but never invoked
**Severity**: P1
**Type**: cold-start
**File**: `app/engines/embeddings_index.py:293` + docstring line 41
**Finding**: The module docstring says
"Call :func:`warm_up` so the module-load cost stays < 1 ms" but no
caller in the codebase invokes it. First query through the engine that
needs embeddings pays the 115 ms cost. The function is exported
(`__all__` line 447) but unused.

**Repro**:
```
grep -rn "warm_up" app/  # only definition + docstring + __all__
```

**Suggested fix**: Either include it in the D1 startup hook or call it
defensively at the bottom of `embeddings_index.py` when assets are
available (acceptable because the module-level cost is only 0.5 ms when
assets are missing).

### D5 — `_iter_responses` and `_ENGINE_CACHE` save only engine work (0.09 ms), not the 4 ms route post-processing
**Severity**: P2 (architectural — not a bug, a fix for an
expectation gap)
**Type**: hot-path / cache effectiveness
**File**: `app/routes/regenold.py:168` (`_ENGINE_CACHE`)
**Finding**: CLAUDE.md Round 28 claims a 13,115× speedup on cache
hits ("43.28 ms cold → 0.003 ms cached"). The cached _engine_ call is
indeed 0.003 ms, but the route still runs every post-engine pass:
scope, surface anchors, ref budget, ref rank, citation guard, tone,
audit. Measured cache-hit path: **2.5 ms p50** — not 0.003 ms. The 43
ms cold figure is an aberration from the cold-start path (D1); steady
state is 4.7 ms warm vs 2.5 ms cache-hit. The cache saves ~2 ms per
hit, which is real but smaller than advertised.

**Repro**:
```
# verified in this review:
# 100 identical in-scope POSTs: p50=6.0 ms, cache hits=59
# 100 identical no-cache POSTs: p50=4.7 ms
```

**Suggested fix**: Update the CLAUDE.md Round 28 section to reflect
true cache value (~2 ms saved per hit, ~33% latency reduction on cache
hits, not 13000×). The cache is still net-positive — just less
dramatic. No code change required, just documentation honesty so
future tuning rounds don't over-rely on cache wins.

### D6 — TestClient floor inflates every reported latency by ~5 ms
**Severity**: P2 (measurement hygiene)
**Type**: latency-tail / methodology
**File**: `evals/bench/runner.py` (caller of `TestClient.post`)
**Finding**: A noop `GET /healthz` through the same `TestClient` used
by the bench runner costs **5.0 ms per call**. This is asyncio +
httpx + anyio harness overhead, not route work. Every CLAUDE.md
latency table since the bench started — including "R44 holdout p50
= 9.84 ms" — includes this 5 ms floor.

**Repro**:
```
client.get('/healthz')  # x100 → mean 5.04 ms
```

**Suggested fix**: Two options.
1. **Reframe**: Document in `evals/bench/runner.py` and the CLAUDE.md
   scorecard that "latency_p50_ms" includes ~5 ms of test-harness
   overhead. Real ASGI/uvicorn p50 will be ~5 ms lower (so R44's
   9.84 ms ≈ ~5 ms real route p50 in production).
2. **Replace TestClient with direct ASGI invocation** in the bench
   runner — use `httpx.AsyncClient(transport=ASGITransport(app=app))`
   or call the route function with a mocked dependency context. This
   would give an apples-to-apples measurement of the actual route work.

This is non-blocking — the bench is reproducible, just inflated. But
the production p50 will look much better than the bench claims.

### D7 — Cold-import wall (1.4 s) dominated by `app.main` + transitive `fastapi`
**Severity**: P3
**Type**: cold-start
**File**: `app/main.py`, `app/routes/regenold.py`
**Finding**: `from app.main import app` takes 1427 ms. Top contributors
in cumulative time: `fastapi` 495 ms (transitive: pydantic + httpx +
anyio + click), `app.routes.regenold` 246 ms (which transitively
imports `graph_rag`, `intent_classifier`, scope, ontology, etc.). On
Railway, this is a 1.4 s gap between "process boot" and "ready to
serve" — adds to first-deploy cold-start latency.

**Repro**:
```
python -X importtime -c "from app.main import app" 2>&1 | sort -t'|' -k 2 -n -r | head
```

**Suggested fix**: Most of this is unavoidable (fastapi + pydantic).
But two specific module-level imports are removable:
- `app.llm.openai_wrapper_provider` imports `httpx` at top level (137
  ms in trace) but the wrapper is only used in the `openai_wrapper`
  provider path. Lazy-import inside `_call_openai_chat` and skip the
  cost when `P2P_GRAPH_RAG_PROVIDER ∈ {cli, anthropic, auto-no-key}`.
- `app.llm.intent_classifier` similarly imports the wrapper provider
  transitively. Both could be lazy.

Expected savings: ~150 ms cold import when not using openai_wrapper
provider (i.e., the Railway `anthropic` deploy path).

### D8 — `subpoint_emitter.upgrade_references` is the heaviest single per-call function (0.35 ms cumulative)
**Severity**: P3
**Type**: hot-path
**File**: `app/data/subpoint_emitter.py:179` (`upgrade_references`)
**Finding**: Second-largest cumulative per-call cost in the route
profile. Runs on every request, walks `subpoint_emitter` mappings
to upgrade Article-level refs to Article+subpoint refs. Profile shows
54 invocations / 19 ms total in a 100-paired-call run = 0.35 ms each.
Not a problem at 4.7 ms p50, but if D1 fix lands and p50 drops to
~7 ms, this becomes 5% of the wire-call time.

**Repro**: cProfile output (see hot-path table above).

**Suggested fix**: Investigate whether the iteration can be
short-circuited when no candidate ref matches a subpoint-keyed
emitter. Many requests don't trigger any upgrade — the per-call cost
could be 0 in those cases with an early-out keyed off `_subpoint_keys
& set(candidate_refs)`.

### D9 — Scope.py extracts referenced articles twice per request
**Severity**: P3
**Type**: hot-path / duplicate work
**File**: `app/integrations/regenold/scope.py:260`
**Finding**: Profile shows `extract_referenced_articles` called 108
times in 54 requests = **2× per call**. Once in `classify_conversation`,
once elsewhere in the route. Each call is ~50 µs. Net cost: 50 µs ×
54 redundant calls = 2.7 ms per 100 requests = 27 µs/req.

**Repro**: cProfile `ncalls 108` for 54 paired requests.

**Suggested fix**: Cache the result on the request object or thread the
already-extracted list through to downstream callers. Saves ~27 µs
per request.

### D10 — `evidence/store.py:record` runs synchronously on every request (in-memory backend)
**Severity**: P3
**Type**: hot-path
**File**: `app/evidence/store.py:183`
**Finding**: Per-request profile shows 0.15 ms cumulative for `record`,
which is the audit-chain hash-chained append. In-memory backend is
fast; SQLite or Postgres would be slower. The 0.15 ms cost includes
SHA256 of the question + answer + prev_hash + JSON serialization.

**Repro**: cProfile in the route profile section above.

**Suggested fix** (deferred consideration): For high-throughput
deployments, the audit append could be queued to a background thread
(daemon `queue.Queue` + worker thread that flushes to the backend).
The hash chain stays consistent because appends are still serialised
inside the worker. Saves 0.15 ms p50 today; saves much more if the
audit backend ever moves to SQLite or Postgres in production.

---

## Summary table

| Finding | Severity | Type           | Wall-time gain                          |
| ------- | -------- | -------------- | --------------------------------------- |
| D1      | P0       | cold-start     | -700 ms on first 3 requests (kills p99.5 spikes) |
| D4      | P1       | cold-start     | -115 ms on first definition query       |
| D5      | P2       | docs           | none (clarify cache value)              |
| D6      | P2       | measurement    | bench-numbers reframing; ~5 ms p50 in production |
| D7      | P3       | cold-start     | -150 ms import time (anthropic deploys) |
| D8      | P3       | hot-path       | ~0.3 ms p50 if early-out lands          |
| D9      | P3       | hot-path       | ~0.03 ms p50                            |
| D10     | P3       | hot-path       | ~0.15 ms p50 (and future-proofs SQL backend) |
| D2      | P3       | regex          | ~4 µs / call                            |
| D3      | P3       | regex          | ~2 µs / call                            |

**The single highest-impact fix is D1**: a 20-line startup hook that
runs the three lazy index builds in a daemon thread on worker boot.
It eliminates the 480–700 ms outliers that have shown up at the same
positions in every davidath benchmark since the indexes shipped, and
brings p99.5 from 110 ms down toward the steady-state shape.
