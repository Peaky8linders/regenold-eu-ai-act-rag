# R81 Plan — next steps after R80–R80.2 (Cloudflare tunnel + Claude Max)

Hand-off for a **fresh session** that uses the production Cloudflare
tunnel + Claude Max subscription path. Read top to bottom. The R80
trio shipped a major shift — Stage-2 polish via the Claude Max wrapper
is now ON by default on production (overturning the R77 doctrine),
and the latency knobs are baked as code defaults (no Railway dashboard
intervention required). Live measurement showed bench-level wins on
every reference + conciseness axis; the LLM judge run was only partial
because the Anthropic API credit balance ran out mid-run.

## State after R80–R80.2 (origin/main @ 72c5c29)

| PR | Round | What shipped |
| -- | ----- | ------------ |
| #106 | R78.1 | Cache no-poison guard — production-down hotfix |
| #109 | R80   | I4 narrow (`_answer_covers_ref` BM25 thresh 2→4 + literal cite check) · I-F (floor suppression in `zero_retrieval_fallback` + 14 new `KEYWORD_TO_ARTICLE` entries) |
| #110 | R80.1 | Stage-2 ON + latency knobs via `railway.toml [deploy.envs]` (silently overridden by Railway dashboard pin — see gotchas below) |
| #111 | **R80.2** | **Best config baked as CODE defaults**: `_stage2_polish_enabled` env default `"0"→"1"`; `max_tokens` 1024→512; `complex_thinking_tokens` 2500→1024. Railway picks them up with NO dashboard touch. |

**Code defaults now in play (per-deploy override via env still works):**

| Env var | Code default | Effect when unset |
| ------- | ------------ | ----------------- |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `"1"` (R80.2) | Stage-2 polish fires when a Stage-2 provider is wired |
| `P2P_GRAPH_RAG_MAX_TOKENS` | `512` (R80.2) | Stage-1/2 polish output cap |
| `P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS` | `1024` (R80.2, clamp floor) | Opus extended-thinking budget on complex rows |
| `REGENOLD_HARD_CHAR_CAP` | `"0"` (R78) | Hard 600-char truncate |
| `REGENOLD_QA_REF_BUDGET` | `"1"` (R77) | QA ref budget 3 (vs 5) |
| `REGENOLD_REF_DESCRIBE_AUG` | `"1"` (R77) | Per-ref description augmenter (Stage-2-OFF rows) |

## Step 0 — top up Anthropic credits + clean judge re-run

The r80.2-live judge run errored on 74-77 of 100 rows. Root cause from
the sidecar:

* **Credit balance exhaustion** — `"Your credit balance is too low to
  access the Anthropic API"` (HTTP 400, `invalid_request_error`).
* **Rate limit** — `"This request would exceed your organization's
  rate limit of 50 requests per minute"` + `"30,000 input tokens per
  minute"` (HTTP 429, `rate_limit_error`).

Concurrency 6 was bursting past the org-tier 50 req/min on the early
rows; mid-run, credit balance gave out.

Before any R81 measurement: **top up Anthropic credits at
console.anthropic.com → Plans & Billing**, then re-run with tighter
concurrency:

```powershell
$env:P2P_GRAPH_RAG_API_KEY = "sk-ant-..."
.venv\Scripts\python.exe -m evals.judge.runner `
  --bench-sidecar evals\bench\results\representative-100-r80.2-live.json `
  --label r80.2-live-rejudge --provider anthropic --concurrency 4 --verbose
```

(concurrency 4 stays comfortably under the 50 req/min cap on the full
4-axis × 100-row run.)

R80.2 baseline targets to beat (judge no-err pass rates):

| Axis | r80-live (Stage-2 OFF) | R77-R79 target | r80.2-live partial (n=23-26) |
| ---- | ---------------------- | -------------- | ---------------------------- |
| correctness | 0.595 | — | 0.654 (suggestive) |
| refs | 0.260 | 0.35+ | 0.308 (suggestive) |
| conciseness | 0.506 | 0.55+ | 0.435 (small-sample, **maybe regression**) |
| tone | 0.841 | 0.85+ | **0.952** (peak, above target) |

The conciseness signal is the most interesting unknown — bench-level
conciseness LIFTED (+0.038) but the judge partial sample DROPPED
(-0.071). Clean re-judge resolves whether this is small-sample noise
or a real regression from the "AT MOST 3 sentences" prompt tightening
(R80.1) being too aggressive.

## R81 work queue (prioritise from clean Step-0 judge data)

### A — Latency: live p50 16 s → target < 6 s

Live r80.2-live p50 = **15,962 ms** / p95 = 36,873 ms / max =
51,299 ms. Well above the original R77-R79 target (< 6 s).
Multiple levers, each measurable in isolation:

* **A1 — Disable Opus complex path** (highest-leverage, easiest):
  set `GraphRAGSettings.complex_model = ""` as code default in
  `app/config.py`. Removes the worst-case Opus extended-thinking
  outliers. Risk: loses R51's structured-reasoning win on
  conflict + borderline-prohibition rows (r69-live conflict refS
  0.95, borderline refL 1.0 — both above-target).
* **A2 — Selectively narrow `_needs_stage2_enhancement`** — currently
  fires on multi-turn OR `≥ 2` entities OR > 200 chars OR complex
  keywords, which catches ~60-80% of rep-100. Narrow to multi-turn
  + complex-keyword only → Stage-2 fires on ~20-30%, cuts mean
  latency materially.
* **A3 — Hybrid model routing**: Sonnet 4.6 for complex Stage-2
  rows, Haiku 4.5 for simple ones. Haiku is ~2-3× faster on the
  short polish. Risk: Haiku quality on regulatory prose untested at
  scale.
* **A4 — Further `max_tokens` trim**: 512 → 256-384. A 3-sentence
  answer is ~150-200 tokens typical; 256 still gives headroom. Risk:
  cuts off the occasional legitimate longer answer mid-thought.

Measure each via local tunnel (`evals.bench.representative_100` with
no `--endpoint`) before pushing to production.

### B — Refs faithfulness: judge no-err 0.31 → target 0.35+

R80-D narrow tightened the augmenter coverage check (BM25 threshold
2 → 4 + literal cite). But the augmenter `skip` gate at
`app/routes/regenold.py:2864` excludes rows where `stage2_landed=True`.
With R80.2's Stage-2-ON default, the augmenter NEVER fires on the
polished rows — Stage-2 polish writes its own description. Yet the
judge still finds "Article N cited but not described" failures
(per the r80.2-live judge sidecar's failure-mode tally).

Options to lift refs:

* **B1 — Run augmenter AFTER Stage-2 polish too**: drop the
  `stage2_landed` exclusion. Augmenter would catch refs the polish
  omitted. Risk: Sonnet polish was tuned to be self-sufficient;
  augmenter could append clauses that duplicate Sonnet's prose.
  Verify via local A/B before shipping.
* **B2 — Strengthen Stage-2 prompt rule 10** further: turn "every
  cited Article MUST be described" into an explicit checklist
  (`"Before finalising, verify each ref in the references field is
  named + briefly described in your prose. If any ref is unnamed,
  rewrite to include it"`). Forces Sonnet to self-audit.
* **B3 — R80-D aggressive (replace-sentence augmenter)** for
  Stage-2-OFF complement rows (when wrapper degraded / Pro
  rate-limit). Currently augmenter only appends and gets trimmed
  by the 3-sentence cap; redesign to swap a sentence for an
  augmenter clause when at the cap.

### C — Conciseness clawback: bench +0.038 vs judge partial −0.071

The "AT MOST 3 sentences" prompt tightening (R80.1) lifted
bench-level conciseness +0.038 vs r80-live. But the partial judge
sample (n=23) measured -0.071. Either:

* Small-sample noise — the bench-level signal across 100 rows is
  more reliable; clean judge re-run (Step 0) resolves.
* OR the prompt change made Sonnet output too dense — packing 3
  refs into 3 sentences leaves no room to "describe" each.
* OR the judge's "describes every ref" criterion is stricter than
  bench-level token overlap; tight answers fail it.

Get clean Step-0 judge first. If conciseness still drops, walk
back the prompt change (or soften to "ideally 3, at most 4"):

```python
# Reverse the R80.1 tightening in app/data/graph_rag_prompts.py
# AND app/engines/graph_rag.py line ~3240
```

### D — Multi-turn coherence: bench multi_turn ans_strict 0.249

Multi-turn rows are the weakest answer-quality category in r80.2-live
(ans_strict 0.249 vs overall 0.248 — flat). Stage-2 polish helps
marginally on these rows. R60-C added the `[Context anchors] ...`
prefix; R57-A added the "we / our / now we" multi-turn fact-pattern
rescue. The remaining headroom is in how the engine BUILDS the answer
across turns.

Genuine multi-turn surgery:

* Pre-resolve all anchors from prior turns into a single anchor pool
  BEFORE retrieval (currently history is appended to the question
  string; retrieval scores it as one big BM25 query).
* Stage-2 prompt: emphasise "answer the LATEST question; don't
  re-summarise the conversation". The R69-rule-10 push toward
  describing every ref can make Sonnet over-describe in the
  multi-turn case.

### E — Cache hit rate (production observability)

R28 cache + R78.1 no-poison guard + R79 cache-key fix (incl.
`P2P_GRAPH_RAG_ENABLE_STAGE2`) are all in place. Production traffic
should hit the cache for repeat questions. We don't currently log
cache-hit-rate. Add a `/healthz/cache` endpoint that surfaces the
`_ENGINE_CACHE` hit/miss counters → measure live hit rate.

### F — Anthropic SDK direct as Pro-tier fallback (R56 reactivation)

The Claude Max subscription is the primary path. R56 wired the
Anthropic SDK direct path as the Pro-tier fallback (per-token billed,
no Max quota constraints). If Max quota tightens or the user
downgrades from Max to Pro, R56 should be ready to activate:

```bash
railway variables --set P2P_GRAPH_RAG_PROVIDER=anthropic
railway variables --set P2P_GRAPH_RAG_API_KEY=sk-ant-...
```

Test the path locally first via the same env vars — it should be a
1-line provider swap on production.

## Verification gates (every R81 PR)

* `pytest -q` stays green (R80.2 baseline: **2,433 pass + 1 skip**).
* `evals.bench.runner` davidath — no regression:
  Ref Loose ≥ 0.575, Ref Strict ≥ 0.464, Ans Strict ≥ 0.300,
  Tone 1.0, multi-turn 20/20.
* `evals.regenold.runner` — 276/276.
* `evals.regenold.runner_v2 --local --probe-oos` — 21/21 PASS,
  0 leaks.

## Load-bearing context / gotchas

* **Railway dashboard variables OVERRIDE `railway.toml [deploy.envs]`**
  (R80.1 discovery). Future production config changes should follow
  the R80.2 pattern: **bake into code defaults**, not railway.toml.
  Dashboard-pinned vars can only be cleared via
  `railway login` + `railway variables --set` (interactive auth
  required — can't be done from a session sub-shell).
* **Anthropic API credit balance** — r80.2-live judge hit exhaustion.
  Top up before judge runs. Use `--concurrency 4` not 6 for full
  100-row runs to stay under the 50 req/min org tier.
* **Wrapper Max quota** — live rep-100 with Stage-2 ON burns Max
  session quota (~80 Sonnet 4.6 polish calls per run). Don't
  back-to-back without quota reset; partial-run errors look like
  rate-limit but are actually quota exhaustion.
* **Stage-2 fires on ~60-80% of rep-100 rows now** — that's why p50
  jumped 0.3 s → 16 s. The A2 / A3 levers target this.
* **The 51 s max latency** in r80.2-live is the Opus complex path.
  R80.2 already trimmed thinking 2500 → 1024 (clamp floor).
  Further: disable Opus entirely (A1).
* **davidath is BM25-saturated** (R31/R59/R69/R77 — five
  confirmations). Retrieval / anchor / scope changes come back
  byte-identical on the local bench. The bench is the regression
  guard; wins land on the live judge.
* **Stage-2 polish output is the load-bearing prose** now that the
  master switch is ON by default. Every change to the Stage-2 prompt
  in `app/data/graph_rag_prompts.py` or the Stage-2 user-message in
  `app/engines/graph_rag.py` is a live-quality lever.
* **Multi-agent repo**: `main` advances mid-session. `git fetch` +
  base off `origin/main`. Place worktrees OUTSIDE the repo tree
  (sibling dir), e.g. `D:/Claude Projects/regenold-r81-<topic>`.
* CLAUDE.md hard rules still bind: `Article N` / `Annex X` ref
  format; `MAX_ANSWER_SENTENCES = 3` + 600-char soft cap; no
  overfit to the 3 PDF example questions; KB stubs ship faithful
  prose; every citation must resolve in `ARTICLE_EXISTENCE`.

## R80.2 baseline numbers (the bar to beat)

### Bench-level r80.2-live (davidath rep-100, n=100, 100% rows good)

| Axis | r80-live (R79+OFF) | **r80.2-live (R80.2 ON)** | Δ |
| ---- | ------------------ | ------------------------- | --- |
| Ans Strict | 0.2363 | 0.2482 | +0.012 |
| Ans Conciseness | 0.4288 | **0.4669** | **+0.038** ✓ |
| Ref Loose | 0.555 | 0.615 | +0.060 ✓ |
| Ref Strict | 0.5063 | **0.5763** | **+0.070** ✓✓ |
| Ref Conciseness | 0.4978 | **0.5642** | **+0.066** ✓✓ |
| Regulatory Tone | 1.0 | 1.0 | flat ✓ |
| p50 latency | 307 ms | 15,962 ms | +51× |
| p95 latency | 5,970 ms | 36,872 ms | +30s |
| max latency | 14,924 ms | 51,298 ms | +36s (Opus complex path) |

### Judge r80.2-live (partial, n=23-26, credit-balance-blocked)

| Axis | r80-live no-err | **r80.2-live no-err (small sample)** | Δ |
| ---- | --------------- | ------------------------------------- | --- |
| correctness | 0.595 | 0.654 | +0.059 |
| refs | 0.260 | 0.308 | +0.048 |
| conciseness | 0.506 | 0.435 | **-0.071** (small-sample!) |
| **tone** | 0.841 | **0.952** | **+0.111 — project-peak** |

### Davidath full bench (n=476) — unchanged from R80

R80.2 default flip is invisible to TestClient because the provider
gate (`_stage2_provider_enabled`) returns False without a wrapper
env, so Stage-2 doesn't fire:

* Ref Loose 0.5776, Ref Strict 0.4654, Ans Strict 0.3018,
  Tone 1.0, MT 20/20.
* `pytest -q`: 2,433 pass + 1 skip.

## How to reproduce R80.2's measurement points

```powershell
# Smoke test first
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m evals.bench.runner --label r81-baseline

# Local Stage-2-ON measurement via tunnel (no Max-quota production hit
# — and runs against your local working tree, so it reflects R81 code
# changes before deploy):
$env:P2P_GRAPH_RAG_PROVIDER       = "openai_wrapper"
$env:OPENAI_API_BASE              = "https://wrapper.antifragile-ai.net/v1"
$env:OPENAI_API_KEY               = "dummy"
$env:P2P_GRAPH_RAG_MODEL          = "claude-sonnet-4-6"
$env:P2P_REGENOLD_API_KEY         = "dk5mhZqpDYhbhz-h5QNUrachCY2Eknz2nOKRwoRT-dE"
$env:P2P_GRAPH_RAG_API_KEY        = "sk-ant-..."   # for judge later
.venv\Scripts\python.exe -m evals.bench.representative_100 --label r81-local-tunnel --verbose

# Live rep-100 against deployed Railway (POST-Step-0 only — burns
# Max quota and partner-tier 60/min budget):
.venv\Scripts\python.exe -m evals.bench.representative_100 `
  --label r81-live --verbose `
  --endpoint "https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true" `
  --api-key dk5mhZqpDYhbhz-h5QNUrachCY2Eknz2nOKRwoRT-dE

# Judge (after Step-0 Anthropic credit top-up):
$env:P2P_GRAPH_RAG_API_KEY = "sk-ant-..."
.venv\Scripts\python.exe -m evals.judge.runner `
  --bench-sidecar evals\bench\results\representative-100-r81-live.json `
  --label r81-live --provider anthropic --concurrency 4 --verbose
```

## Suggested R81 round shape

1. **R81-A1** (latency) — disable Opus complex path as code default,
   re-measure live; ship as a single small PR.
2. **R81-Step-0** (data) — clean judge re-run on top of A1. Now we
   have the post-A1 quality + latency numbers.
3. **R81-B / R81-C / R81-D** — pick the highest-leverage from the
   Step-0 data. Don't bundle; each lands as its own PR for clear
   attribution.

If the user is willing to top up Anthropic credits, do Step 0 BEFORE
A1 to get a clean comparison point. If not, A1 + new live numbers
gives a noisy-but-directional answer.
