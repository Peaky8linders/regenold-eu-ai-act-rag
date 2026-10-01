# R460 — Cohere re-baseline: easy **87.35**, hard **85.77** (n=37 each)

Every live number in this round until now was an SVD-retrieval **floor** (the
trial key 429'd on `/v1/embed` and `/v1/rerank`). The key was replaced and both
boards were re-run on the shipped configuration — Stage-2 `claude-opus-5-5`, all
R449-R451 knobs at their defaults, evidence bundle OFF — now with the Tier-0
instrumentation live, so every row carries its own usage, payload shape and leg.

## 1. Cohere is real again

`embed` and `rerank` both return 200 (`rerank-v4.0-pro`). The easy board logged
**zero** 429s and zero `external embeddings returned None` fallbacks. The hard
board's *first* attempt aborted at row 2 — and the cause was **my own** rate-limit
diagnostic, a 12-call burst fired at the same minute, not the board: the trial key
allows **10 rerank calls/min**, which the burst consumed. Relaunched with
`--resume`, the board finished 37/37 with 0 errors and no further rerank failure.

Consequence for the plan, CORRECTED later the same evening: the trial key is
**not** what blocks the R450 `density` gate. `run_official_batch._net_of_pacing`
subtracts the rerank pacer's sleep from every measured latency (R409 — R407
scored Resp. Speed on 13 s of pacing before it was fixed), so a paced arm keeps a
clean Speed axis: run it with `--min-rerank-gap 7` and
`--require-cohere-rerank` (which tolerates budget skips) and ~4 rerank calls/row
stay inside 10/min. What blocks the gate is **power**: R450 measured `density` at
+3/82 rows of gold-unit coverage, which at n=37 is ~1 row — below the house
detection floor. See `REF-CONCISENESS-LEVERAGE.md` §6 for the full correction and
§7 for the re-order.

## 2. Hard board (`r460-cohere-hard-s3`, n=37)

| axis | Cohere ON | SVD floor | frontier | published us |
| :-- | --: | --: | --: | --: |
| ans_correctness_loose | 94.07 | 94.07 | 92.0 | 89.9 |
| ans_correctness_strict | 89.19 | 89.19 | 84.8 | 80.0 |
| ans_conciseness | 81.54 | 81.61 | 71.8 | 45.2 |
| ref_correctness_loose | **98.57** | 95.71 | 94.6 | 89.5 |
| ref_correctness_strict | **84.76** | 82.38 | 74.1 | 70.7 |
| ref_conciseness | 59.14 | 59.90 | 58.5 | 49.8 |
| regulatory_tone | **100.00** | 97.30 | 100.0 | 96.1 |
| resp_speed | **86.66** | 82.76 | 86.7 | 85.7 |
| **overall** | **85.77** | 84.52 | 81.7 | 73.4 |

Reading: the reranker buys the **reference axes** (+2.86 loose, +2.38 strict),
removes the single tone failure (`rg_088`), and cuts mean latency 17.2 s -> 13.3 s
(+3.90 speed). Answer correctness is byte-identical to the floor board
(94.07/89.19) — the reranker changes which provisions are cited, not what the
answers say. Against the frontier: **+4.07 overall**, and the only axis still
behind is Resp. Speed — by **0.04**.

## 3. Easy board (`r460-cohere-easy-s3`, n=37)

| axis | Cohere ON | frontier (easy) | published us |
| :-- | --: | --: | --: |
| ans_correctness_loose | 97.78 | 94.4 | 89.7 |
| ans_correctness_strict | 94.59 | 89.1 | 81.2 |
| ans_conciseness | 81.30 | 67.9 | 51.9 |
| ref_correctness_loose | 98.57 | 96.1 | 89.4 |
| ref_correctness_strict | 84.76 | 78.5 | 68.3 |
| ref_conciseness | 61.10 | 51.9 | 50.4 |
| regulatory_tone | 100.00 | 100.0 | 99.1 |
| resp_speed | 88.34 | 81.8 | 87.6 |
| **overall** | **87.35** | 80.9 | 75.1 |

**Ahead of the frontier on all eight axes** (+6.45 overall); mean latency 11.7 s,
mean answer 826 chars, 28/37 rows polished by Opus 5.5.

## 4. What the live rows now say about payload shape and tokens

The Tier-0 capture resolves the shape question with production data instead of a
replay harness:

| board | polished rows | `stage2_system_chars` | `stage2_history_turns` |
| :-- | --: | --: | --: |
| easy | 28 | 60,643 / 60,646 (full stack) | 1 |
| hard | 28 | **61 (persona)** | 20 (fixed fixture) |

So on the shipped hard board the 60,643-char stack is **never sent** — the
"fixed" request shape carries a constant 20-turn fixture, which is `> 1`, so the
R411/R412 gate substitutes the persona on every dispatch. The 60k stack only
ever rides the easy board (and any single-turn caller).

Per-row usage (median, live):

| board | prompt tokens | completion tokens | user chars | chars/token |
| :-- | --: | --: | --: | --: |
| easy | 9,236.5 | 213.5 | 36,945 | 4.00 |
| hard | 8,360.0 | 204.5 | 33,438 | 4.00 |

The prompt counter is `round(len(user)/4.0)` to the digit on the live wire, and
it is identical across the payload shapes — the system stack is not accounted at
all (the canary shows it is nonetheless *delivered* at these sizes to Opus).

## 5. Rows to report, not hide

* Hard `rg_049` — Stage-2 ran (`stage2_usage` present) but the graded answer is
  the **deterministic** draft (`stage2_served_by=deterministic`); a post-call
  guard rejected the polish. Every other polished hard row is
  `stage2_served_by=primary`.
* Both boards keep the 9 curated/deterministic rows with no Stage-2 call.
* `rg_088`'s tone failure on the SVD board disappears with rerank on.

## 6. Caveats

* `--stride 3`, n=37 per board, one generation per arm; the instrument
  reconstructs criteria and reference answers — these are not official scores.
* Judge identity pinned (`bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`),
  one shared cache; rows already judged in earlier arms were reused.
* Cohere key is **trial** (10 calls/min, 1000/month). One hard board at natural
  pace fits the rate budget, and nothing else may call Cohere concurrently. A
  *paced* arm is also valid for Speed: the harness nets the pacer's sleep out of
  every measured latency (see §1).
* Hard board rows 1 and 2 of the resumed run: row 1 was carried over from the
  aborted attempt under the identical config; `--resume` seeds the rolling
  history from disk (R423.3), but with the fixed fixture the history is the
  fixture either way.

## 7. Artifacts

* `evals/bench/results/official-r460-cohere-{easy,hard}-s3-{easy,hard}.ckpt.jsonl`
* `docs/measurements/r388/score-r460-cohere-{easy,hard}-s3-{easy,hard}.json`
* `docs/measurements/r460/score-r460-cohere-{easy,hard}-s3.log`
* judge cache `docs/measurements/r460/judge-cache-r460-bedrock.jsonl`
* `TIER0-FIXES.md` (instrumentation + transport), `ANALYSIS-AND-PLAN.md` (plan)
