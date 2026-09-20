# R423 — need-proportional answer contract: paired hard-split gate (`r423-need3`)

**Question.** Does `REGENOLD_NEED_PROPORTIONAL_CONTRACT` make the Stage-2 answer shape follow the criteria the ask engages — and does it do so without costing correctness or gold references?

**Design.** 37 strided hard rows of the official 110 (`--stride 3` — the send order is front-loaded with easy rows, so a prefix is not the board) × **3 independent generations per row per arm** (`--repeats 3`), sequential arms, one Claude Max backend. Every generation runs with the route's response cache cleared, so a generation is a new draw rather than a replay (§Transport).

## Verdict — pre-registered rule

SHIP (default ON) requires, on the comparable subset: `ans_loose` and `ans_strict` no worse than −1.0 pp, answer length strictly down, and no more gold heads dropped by arm B than by arm A. Pre-registered before the run, in `docs/measurements/r423/need_gate.py`.

| axis (paired, median over 3 generations) | mean Δ | median Δ | 95 % CI | rows up / down / tied |
| :-- | --: | --: | :-- | :-- |
| `delta_ans_loose` | -3.95 pp | +0.00 | [-10.37, +0.00] | 0 / 2 / 25 |
| `delta_ans_strict` | -7.41 pp | +0.00 | [-18.52, +0.00] | 0 / 2 / 25 |
| `delta_answer_chars` | -2047.89 chars | -2209.00 | [-2371.07, -1731.30] | 0 / 27 / 0 |
| `delta_tone` | +0.00 pp | +0.00 | [+0.00, +0.00] | 0 / 0 / 27 |
| `delta_ref_strict` | +9.26 pp | +0.00 | [+0.00, +20.37] | 3 / 0 / 24 |

Gold heads dropped on the comparable subset: **A 1 (1 rows)** vs **B 1 (1 rows)**.

Every official axis on that SAME comparable subset, reduced the same way (median over the generations), including the aggregate the benchmark ranks on:

| metric | arm A (OFF) | arm B (ON) | Δ |
| :-- | --: | --: | --: |
| Ans. Correctness (Loose) | 96.97 | 92.93 | **-4.04** |
| Ans. Correctness (Strict) | 92.59 | 85.19 | **-7.41** |
| Ans. Conciseness | 22.18 | 68.09 | **+45.91** |
| Ref. Correctness (Loose) | 98.15 | 96.3 | **-1.85** |
| Ref. Correctness (Strict) | 70.37 | 75.93 | **+5.56** |
| Ref. Conciseness | 37.35 | 57.96 | **+20.62** |
| Regulatory Tone | 100.0 | 96.3 | **-3.70** |
| Resp. Speed | 65.95 | 76.32 | **+10.37** |
| **OVERALL (geometric mean)** | 65.04 | 79.96 | **+14.91** |

| pre-registered ship condition | met? | measured |
| :-- | :-- | --: |
| `ans_loose` no worse than −1.0 pp | **NO** | -3.95 pp |
| `ans_strict` no worse than −1.0 pp | **NO** | -7.41 pp |
| answer length strictly down | yes | -2048 chars |
| official overall no worse than −0.5 pp | yes | +14.91 pp |
| no more gold heads dropped than the baseline | yes | B 1 vs A 1 |

**Verdict: KEEP OFF.** 2 pre-registered condition(s) failed: `ans_loose` no worse than −1.0 pp, `ans_strict` no worse than −1.0 pp.

The whole correctness cost, row by row (every row where `ans_strict` fell, with the arm-A answer this was measured against):

| row | A chars | B chars | Δ chars | A loose | B loose | gold head dropped by B |
| :-- | --: | --: | --: | --: | --: | :-- |
| `rg_010` | 2763 | 379 | -2384 | 100 % | 60 % | — |
| `rg_106` | 2651 | 442 | -2209 | 100 % | 33 % | Annex III |

2 of 27 comparable rows; the rest are tied, and no row improved on correctness. The cause is length starvation, not the extraction: each of these collapsed to a short answer, and the criteria the judge credits for them need the enumeration the shape clause suppressed.

## Scope of this verdict — the STRIPPED-prompt hard path

Both arms run hard mode, so both dispatched the stripped persona (61 chars) rather than the full system prompt, which reaches Stage-2 only on single-turn asks (`REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` default is ON; a hard-mode ask reads `history_turn_count > 1`, so it is excluded by the lever's own predicate). The dispatched system lengths, measured on the arms' payload records:

| arm : leg | calls | dispatched the persona | system-payload distribution (chars × calls) |
| :-- | --: | --: | :-- |
| `B:fallback` | 1 | 0 of 1 | 1311 × 1 |
| `B:primary` | 109 | 97 of 109 | 61 × 97 · 132 × 2 · 1311 × 1 · 6365 × 8 · 59644 × 1 |

The payload recorder wraps the provider, so those counts are every call on the leg — the Stage-2 polish **and** the auxiliary passes that pass their own system strings. The 61-char bucket is the hard-mode Stage-2 dispatch; the rest are that tail (and one single-turn full-system call). The arm without a bucket recorded was resumed from a pre-restart checkpoint, so its dispatch shape is bound by the same configuration but is not itself on record here.

**So the win and the loss both belong to that configuration.** The +45.91 pp answer-conciseness gain and the −7.41 pp strict-correctness loss describe hard mode under a stripped prompt. Two things are therefore NOT measured here, and neither changes the verdict for the hard board as it ships today: the lever's incremental effect on the **live single-turn path** (which already receives the full 53 kB prompt, itself measured at ~58 % shorter answers, R412), and hard mode with the full prompt delivered (R411 gap 3.1).

## All eight official axes, per arm

Median across the three generations of the arm's own board (37 rows), judged by `openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3` (temp 0.1, grouped criteria, 3 repetitions per row). `ans_conciseness` and `resp_speed` are computed from text and latency, the two `ref_correctness` axes from the reference key; the ref axes exclude rows with no annotated expected references.

| metric | arm A (OFF) | arm B (ON) | Δ (B − A) | A min–max over generations | B min–max |
| :-- | --: | --: | --: | :-- | :-- |
| Ans. Correctness (Loose) | 95.56 | 92.59 | **-2.96** | 94.81–95.56 | 88.15–94.81 |
| Ans. Correctness (Strict) | 91.89 | 86.49 | **-5.41** | 89.19–91.89 | 83.78–89.19 |
| Ans. Conciseness | 41.18 | 74.59 | **+33.42** | 41.10–43.10 | 73.76–75.01 |
| Ref. Correctness (Loose) | 98.57 | 95.71 | **-2.86** | 98.57–98.57 | 94.29–97.14 |
| Ref. Correctness (Strict) | 75.24 | 79.52 | **+4.29** | 72.38–75.24 | 77.62–80.48 |
| Ref. Conciseness | 43.15 | 58.29 | **+15.14** | 42.19–43.29 | 57.81–58.81 |
| Regulatory Tone | 100.00 | 97.30 | **-2.70** | 100.00–100.00 | 97.30–100.00 |
| Resp. Speed | 72.24 | 81.00 | **+8.75** | 70.50–73.07 | 80.69–81.18 |
| **OVERALL (geometric mean)** | 72.76 | 82.33 | **+9.56** | 72.75–73.88 | 81.10–83.06 |

Per-generation detail (the raw inputs to the medians above):

| arm | generation | Ans. Correctness L | Ans. Correctness S | Ans. Conciseness | Ref. Correctness L | Ref. Correctness S | Ref. Conciseness | Regulatory Tone | Resp. Speed | overall |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| A | 1 | 95.56 | 91.89 | 41.18 | 98.57 | 72.38 | 43.15 | 100.00 | 70.50 | 72.75 |
| A | 2 | 95.56 | 91.89 | 43.10 | 98.57 | 75.24 | 43.29 | 100.00 | 73.07 | 73.88 |
| A | 3 | 94.81 | 89.19 | 41.10 | 98.57 | 75.24 | 42.19 | 100.00 | 72.24 | 72.76 |
| B | 1 | 94.81 | 89.19 | 74.59 | 97.14 | 80.48 | 58.29 | 97.30 | 81.00 | 83.06 |
| B | 2 | 88.15 | 83.78 | 75.01 | 94.29 | 77.62 | 58.81 | 97.30 | 80.69 | 81.10 |
| B | 3 | 92.59 | 86.49 | 73.76 | 95.71 | 79.52 | 57.81 | 100.00 | 81.18 | 82.33 |

## Comparable subset (the only rows that can move)

Requested 37 rows → **27 comparable** (floor 20); a row is comparable when the PRIMARY leg served its graded answer in at least 2 of the 3 generations **in both arms** — a deterministic Stage-1 draft cannot respond to a prompt-side lever.

* dropped `arm_A_not_primary[none]`: 9 — rg_001, rg_013, rg_019, rg_022, rg_025, rg_031, rg_040, rg_043, rg_076
* dropped `arm_B_not_primary[none]`: 9 — rg_001, rg_013, rg_019, rg_022, rg_025, rg_031, rg_040, rg_043, rg_076
* dropped `arm_A_not_primary[deterministic]`: 1 — rg_085
* comparable but with fewer than 3 primary generations: rg_037 (A=3, B=2), rg_070 (A=2, B=3)

Draw-to-draw dispersion on the comparable subset (why three generations, not one):

| | arm A | arm B |
| :-- | --: | --: |
| rows whose criteria credit moved between generations | 1 | 2 |
| rows whose *all-criteria* verdict flipped | 1 | 1 |
| mean per-row spread (pp) | 0.74 | 2.59 |

## Transport shape (what the arms actually dialled)

| arm | rows | graded calls | deterministic rows | payload legs | fallback dials answered | fallback dials total | primary failed | refusals (named) |
| :-- | --: | --: | --: | :-- | --: | --: | --: | :-- |
| r423-need3-A | 37 | 0 | 10 | — | 0 | 0 | 0 | — |
| r423-need3-B | 37 | 98 | 9 | fallback×1 (system 1311–1311 ch), primary×109 (system 61–59644 ch) | 0 | 0 | 0 | — |

Gate verdict: **VALID** — no reasons recorded.

## Method notes (what makes this a gate rather than a printout)

1. **The void guard decides before any delta is printed.** The runner's own `gate_validity.assess` reads the transport counters it incremented and the payloads it hashed. An arm served by the fallback, an arm whose graded rows are majority-deterministic drafts, a refusal, asymmetric fallback pressure, and generations that were replays are each a VOID.
2. **Generations are real draws.** The route answers from an in-process response cache keyed on (question, context, history depth, env); without clearing it, generations 2..K replay generation 1 (measured on the first R423 gate: 23 of 37 rows byte-identical at 1.6 s against 43.6 s). `run_official_batch._clear_engine_cache` clears it before every sample.
3. **Every paired number is a per-row median over the three generations**, with a bootstrap CI over rows, and the comparability exclusion is symmetric — a row lost by either arm is reported and excluded from both.

## Artifacts

| path | what |
| :-- | :-- |
| `evals/bench/results/official-r423-need3-[AB]-hard*.ckpt.jsonl` | the 6 generation checkpoints |
| `evals/bench/results/official-r423-need3.json` | runner sidecar incl. the gate verdict |
| `docs/measurements/r423/need_gate.json` | paired deltas, comparable subset, dispersion |
| `docs/measurements/r423/judge-cache-r423.jsonl` | the judge's per-answer verdicts |
| `app/engines/answer_need.py` | the estimator, the clause, the flag |
| `docs/measurements/r423/CHECKPOINT.md` | design, offline calibration, and the falsifications |

