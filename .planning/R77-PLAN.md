# R77 Plan — issues from the R76 top-100 measurement + what a fresh session should do

This plan is the hand-off from the R76 representative top-100 run. It is
written so a **fresh session** can pick it up cold. Read it top to bottom.

## What R76 measured

A stratified, LLM-categorised representative top-100 over the real-world
davidath dataset (`evals/bench/representative_100.py`), run TWO ways and
LLM-judged each way (Sonnet, 4 axes, via `evals/judge/runner.py`):

* **Deterministic** — in-process TestClient, no Stage-2 polish, no Neo4j.
* **Live** — the production Railway endpoint (`?include_reasoning=true`,
  Regenold key → Cloudflare tunnel → Claude Max), Stage-2 polish + Neo4j
  2-hop active.

### Scorecard

| Signal | Deterministic | Live (production) |
| ------ | ------------- | ----------------- |
| Ans Strict (token-overlap) | 0.307 | 0.198 |
| Ref Loose | 0.655 | 0.545 |
| Ref Strict | 0.490 | 0.492 |
| Latency p50 | 31 ms | **17,126 ms** |
| Judge correctness (over non-error) | 0.63 | 0.55 |
| Judge refs-faithfulness | 0.23 | 0.20 |
| Judge conciseness | 0.53 | 0.41 |
| Judge tone | 0.85 | 0.76 |

**The live (Stage-2-polished, Max) path scores worse on every judge axis
AND on davidath token-overlap AND is 550× slower.** Sidecars:
`evals/bench/results/representative-100-r76{,-live}.json`,
`judge-r76-rep100.json`, `judge-r76-live.json`.

## The issues, ranked

### I1 — Stage-2 Claude Max polish is net-negative *(CRITICAL)*

Within the SAME live run, splitting the 100 rows by `stage2_polish`
(from the reasoning trace), judged by the same judge:

| Axis | Stage-2 ON (n=47) | Stage-2 OFF (n=53) |
| ---- | ----------------- | ------------------ |
| correctness | 0.568 | 0.535 |
| refs | **0.132** | **0.250** |
| conciseness | **0.231** | **0.551** |
| tone | **0.650** | **0.875** |
| latency p50 | **19,640 ms** | **5,595 ms** |

The polish loses on refs / conciseness / tone, is flat on correctness,
and is 3.5× slower. Judge failure modes on Stage-2 rows: *"sentence
count exceeds 4"*, *"pure boilerplate"*, *"incomplete/truncated
mid-thought"*, *"speculation beyond the regulation's text"*,
*"provider vs operator conflation"*. The deterministic-wire judge (all
100 rows, zero Stage-2) beats the live-wire judge on all 4 axes — the
same conclusion from the other direction.

Caveat to resolve first: the ON/OFF split is confounded — `_needs_
stage2_enhancement` routes the *harder* questions to Stage-2, so ON
rows are intrinsically harder. The deterministic-vs-live comparison
(same 100 Qs, Stage-2 the main answer-quality variable) is the cleaner
signal and agrees.

**R77 action:** A/B Stage-2 properly — run the SAME complex subset with
Stage-2 force-ON vs force-OFF, judge both. Strong prior: **disable
Stage-2** (`P2P_GRAPH_RAG_PROVIDER=cli`, or gate `_two_stage_generate`
off). One move fixes I1, halves latency (I3), and eliminates I8. If a
fresh session wants to keep an LLM polish, it must (a) hard-enforce the
≤4-sentence cap on the polished output, (b) ban the speculation /
provider-vs-operator drift, (c) not exceed ~2× the deterministic length.

### I2 — `"high-risk"` anchor shadows the specific obligation article *(CRITICAL)*

`KEYWORD_TO_ARTICLE` in `app/integrations/regenold/scope.py` maps bare
`"high-risk"` / `"high risk"` → `Art. 6`. Almost every provider /
deployer / importer obligation question contains the phrase "high-risk
AI system", so **Art. 6 wins the anchor and the actual topic article is
never surfaced.** Confirmed on the live reasoning traces:

| Row | Question | Gold | `anchors_used` | Cited |
| --- | -------- | ---- | -------------- | ----- |
| qa_024 | importers' obligations… | Art. 23 | `['Art. 6']` | Article 6 |
| qa_027 | obligations of deployers… | Art. 26 | `['Art. 6']` | Article 6 |
| qa_076 | obligations of downstream providers… | Art. 26 | `['Art. 6']` | Article 6 |
| qa_019 | transparency info to deployers… | Art. 13 | `['Art. 6']` | Article 6 |
| qa_015 | technical-documentation contents… | Art. 11 | `['Annex IV','Art. 6']` | Article 6, Annex IV.2 |

`engine_confidence` was 0.3 on all of them — the engine already knows it
is not confident. ≥8 of the 16 total ref-misses are this pattern.

**R77 action:** Remove the bare `"high-risk"` / `"high risk"` retrieval
anchor (it is a near-universal qualifier, not a topic). Add operator /
topic routes that win: `"importer" / "importers' obligations"` → Art. 23,
`"distributor"` → Art. 24, `"obligations of deployers" / "deployer
obligations"` → Art. 26, `"downstream provider"` → Art. 25, `"transparency
… to deployers" / "instructions"` → Art. 13, `"technical documentation"` →
Art. 11, `"record-keeping" / "logs" / "logging"` → Art. 12/19,
`"human oversight"` → Art. 14, `"accuracy / robustness / cybersecurity"` →
Art. 15. Verify against the R34 P0 OOS regression set + the 21-row OOS
probe. davidath A/B expected strongly positive on Ref Loose.

### I3 — Production latency p50 17 s *(HIGH)*

Latency is a scored axis. p50 17 s; Stage-2 rows 20 s, non-Stage-2 rows
**5.6 s**, multi-turn 47–86 s. Disabling Stage-2 (I1) drops p50 to
~5.6 s. The residual 5.6 s on non-Stage-2 rows is network + Railway +
the Stage-0 intent-classifier LLM call — investigate: is Stage-0 on the
hot path synchronous? Can it be cached harder / made deterministic /
moved to Groq (R52)? Multi-turn pays 2× because it issues two wire
calls — unavoidable for the coherence probe but note it.

### I4 — Refs-faithfulness is the floor axis (0.20–0.23) *(HIGH)*

Both wires: the engine **cites** the right-ish articles but the prose
does not **describe** them. Judge failure modes: *"Article 11 cited but
not described"*, *"cites 10 refs, describes 3"*, *"predicted references
not described in answer prose"*. The deterministic engine emits article
numbers without per-article descriptive prose.

**R77 action:** For every surfaced reference, stitch one faithful
descriptive clause from its KB summary into the answer (the KB already
has summaries; `grounded_prose.stitch_grounded_prose` does this for the
consistency-guard path — make an always-on variant for the main answer).
Then every cited article is described → the judge's worst axis lifts.
This composes with disabling Stage-2 (the deterministic answer becomes
the shipped answer, so its prose must carry the descriptions).

### I5 — Neo4j 2-hop path under-performs *(MEDIUM)*

Live `retrieval_path` distribution: `neo4j` 60 rows (Ref Loose **0.49**),
`consistency_guard` 22 (0.68), `deterministic` 12 (0.58),
`zero_retrieval_fallback` 6 (0.50). The Neo4j 2-hop path carries the
majority of live rows and the worst recall. It is production-only
(`REGENOLD_GRAPH_2HOP=1`) so the local davidath bench never sees it.

**R77 action:** A/B a live re-run with `REGENOLD_GRAPH_2HOP=0`. Likely
the 2-hop expansion adds neighbour articles that push gold refs past the
reference cap. If confirmed, disable it or make the expansion additive-
only-below-cap.

### I6 — Reference cardinality mismatch *(MEDIUM)*

Pred refs mean 5.7 vs gold mean 8.3. 38 rows over-cite (QA — gold is 1
article, we cite ~5), 36 under-cite (scenarios — gold ~9, we cite ~5).
The ref budget is not shape-aware enough.

**R77 action:** Tighten the QA budget toward 1–3; widen the scenario
budget toward the davidath gold cardinality (~9). The QA-vs-scenario
shape is already detected (`_is_scenario_question`) — make the budget
track it.

### I7 — `zero_retrieval_fallback` fired on 6 in-scope rows *(MEDIUM)*

6 genuine in-scope QA rows had retrieval return nothing → the Art. 1/2/3
floor shipped → gold missed. Mostly the same root cause as I2 (the
specific article was never retrieved). Fixing I2 shrinks this set.

### I8 — `consistency_guard` fired on 22 % of live rows *(MEDIUM)*

22 rows had Stage-2 emit refusal-marker contradictions → the grounded-
prose substitute fired. 22 % is high. Disabling Stage-2 (I1) eliminates
this entirely.

## Suggested R77 execution order

1. **I2** — `"high-risk"` anchor fix + operator-obligation routes.
   Pure retrieval, davidath-A/B-able locally, biggest Ref-Loose lever,
   zero LLM dependency. Do this first.
2. **I1** — A/B Stage-2 ON vs OFF on the complex subset; disable if the
   prior holds. Fixes latency + 3 judge axes at once.
3. **I4** — always-on per-reference descriptive stitching → refs-
   faithfulness.
4. **I5** — live A/B `REGENOLD_GRAPH_2HOP=0`.
5. **I6** — shape-aware reference budget.
6. Re-run the representative-100 (deterministic + live) + judge; compare
   to this baseline.

## Verification gates for R77

* `pytest -q` stays green (R76 left it at 2354 pass / 1 skip).
* `evals.bench.runner` davidath — Ref Loose must not regress below
  0.5818 (the R76 number); target +0.03–0.05 from I2.
* `evals.regenold.runner` — 276/276.
* OOS probe 21/21 — every new I2 keyword verified non-leaking.
* Re-run `evals.bench.representative_100` (deterministic + `--endpoint`
  live) + `evals.judge.runner`; the target is the live judge axes
  climbing toward the deterministic numbers (refs 0.20→0.35+,
  conciseness 0.41→0.55+, tone 0.76→0.85+) and live p50 latency
  17 s → <6 s.

## How to reproduce the R76 measurement

```
# deterministic
py -3.12 -m evals.bench.representative_100 --label r77 --verbose
# live (Max via tunnel)
py -3.12 -m evals.bench.representative_100 --label r77-live --verbose \
  --endpoint "https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true" \
  --api-key <REGENOLD_API_KEY>
# judge either sidecar (Anthropic SDK — reliable; the Max wrapper
# degrades past ~12 rows under the 400-call judge volume)
py -3.12 -m evals.judge.runner --provider anthropic --concurrency 6 \
  --bench-sidecar evals/bench/results/representative-100-r77-live.json --label r77-live
```

The 100-row selection is reproducible: the Sonnet categorisation is
cached in `evals/bench/data/representative_pool_categorized.json` and
the selection is order-based (no RNG).
