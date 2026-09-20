# R423 — need-proportional answer contract: paired hard-split gate (`r423-need4`)

**Question.** Does `REGENOLD_NEED_PROPORTIONAL_CONTRACT` make the Stage-2 answer shape follow the criteria the ask engages — and does it do so without costing correctness or gold references?

**Design.** 37 strided hard rows of the official 110 (`--stride 3` — the send order is front-loaded with easy rows, so a prefix is not the board) × **3 independent generations per row per arm** (`--repeats 3`), sequential arms, one Claude Max backend. Every generation runs with the route's response cache cleared, so a generation is a new draw rather than a replay (§Transport).

## Verdict — pre-registered rule

SHIP (default ON) requires, on the comparable subset: `ans_loose` and `ans_strict` no worse than −1.0 pp, answer length strictly down, and no more gold heads dropped by arm B than by arm A. Pre-registered before the run, in `docs/measurements/r423/need_gate.py`.

| axis (paired, median over 3 generations) | mean Δ | median Δ | 95 % CI | rows up / down / tied |
| :-- | --: | --: | :-- | :-- |
| `delta_ans_loose` | +0.00 pp | +0.00 | [+0.00, +0.00] | 0 / 0 / 27 |
| `delta_ans_strict` | +0.00 pp | +0.00 | [+0.00, +0.00] | 0 / 0 / 27 |
| `delta_answer_chars` | -2107.96 chars | -1967.00 | [-2499.26, -1751.52] | 0 / 27 / 0 |
| `delta_tone` | +0.00 pp | +0.00 | [+0.00, +0.00] | 0 / 0 / 27 |
| `delta_ref_strict` | +7.41 pp | +0.00 | [+0.00, +18.52] | 2 / 0 / 25 |

Gold heads dropped on the comparable subset: **A 1 (1 rows)** vs **B 0 (0 rows)**.

Every official axis on that SAME comparable subset, reduced the same way (median over the generations), including the aggregate the benchmark ranks on:

| metric | arm A (OFF) | arm B (ON) | Δ |
| :-- | --: | --: | --: |
| Ans. Correctness (Loose) | 96.97 | 96.97 | **+0.00** |
| Ans. Correctness (Strict) | 92.59 | 92.59 | **+0.00** |
| Ans. Conciseness | 23.09 | 61.94 | **+38.86** |
| Ref. Correctness (Loose) | 96.3 | 100.0 | **+3.70** |
| Ref. Correctness (Strict) | 72.22 | 77.78 | **+5.56** |
| Ref. Conciseness | 37.44 | 50.25 | **+12.80** |
| Regulatory Tone | 100.0 | 100.0 | **+0.00** |
| Resp. Speed | 63.73 | 74.5 | **+10.77** |
| **OVERALL (geometric mean)** | 65.62 | 79.56 | **+13.93** |

| pre-registered ship condition | met? | measured |
| :-- | :-- | --: |
| `ans_loose` no worse than −1.0 pp | yes | +0.00 pp |
| `ans_strict` no worse than −1.0 pp | yes | +0.00 pp |
| answer length strictly down | yes | -2108 chars |
| official overall no worse than −0.5 pp | yes | +13.93 pp |
| no more gold heads dropped than the baseline | yes | B 0 vs A 1 |

**Verdict: SHIP (default ON).**

## Scope of this verdict — what Stage-2 was actually told

Hard mode is graded on a multi-turn ask, and the shipped single-turn lever delivers the full system prompt only when `history_turn_count <= 1` (default ON). A hard row deep in the rolling conversation reads >= 9, so it gets the stripped persona (61 chars) — which is the configuration both arms were compared under. **But the rolling history starts empty**, so the first two rows of any run (or resume) read 0 and 1 and DO receive the full system prompt. That is an artifact of the harness, not of hard mode. The dispatched system lengths, measured on the arms' payload records:

| arm : leg | calls | dispatched the persona | system-payload distribution (chars × calls) |
| :-- | --: | --: | :-- |
| `A:fallback` | 5 | 0 of 5 | 59644 × 5 |
| `A:primary` | 21 | 17 of 21 | 61 × 17 · 6365 × 3 · 59644 × 1 |
| `B:fallback` | 3 | 0 of 3 | 1311 × 3 |
| `B:primary` | 293 | 168 of 293 | 61 × 168 · 132 × 5 · 1311 × 3 · 6365 × 117 |

The payload recorder wraps the provider, so those counts are every call on the leg — the Stage-2 polish **and** the auxiliary passes that pass their own system strings. The 61-char bucket is the hard-mode Stage-2 dispatch and the auxiliary tail is the rest. The ~59.6 kB bucket is the full system prompt, and it appears on three distinct routes, which is why its count is not a Stage-2 measure on its own: the **fallback leg always receives it** (R360 — Bedrock is dialled with the full ``system``, and arm A's dead credential was dialled 5 times), an auxiliary pass, and the leading rows of a run's still-empty rolling history.

### The one asymmetry this created, and its bound

Arm A was **resumed** from a pre-restart checkpoint. ``--resume`` handed its pending rows a brand-new empty history, so its first rows were re-graded as near-single-turn and it made one full-prompt primary Stage-2 dispatch that arm B (continuous) did not. That is a real difference in the system slot between the arms — so the result was re-scored leaving out each comparable row in turn (`need_scope_sensitivity.py`): the overall delta moves only between **+13.42 pp** and **+14.50 pp** against **+13.93 pp** as run. No single row, degraded or full-prompt, carries the win. The resume defect itself is now fixed for future gates: a resumed hard run seeds its rolling conversation from the rows already on disk (``seed_history_from_records``), so a resume can no longer change a row's modality.

**So the measured movement belongs to that configuration.** On the comparable subset this gate published an answer-conciseness delta of +38.86 pp (23.09 → 61.94) and a strict answer-correctness delta of +0.00 pp (92.59 → 92.59) — both describe hard mode under a stripped prompt. Two things are therefore NOT measured here, and neither changes the verdict for the hard board as it ships today: the lever's incremental effect on the **live single-turn path** (which already receives the full 53 kB prompt, itself measured at ~58 % shorter answers, R412), and hard mode with the full prompt delivered (R411 gap 3.1).

## All eight official axes, per arm

Median across the three generations of the arm's own board (37 rows), judged by `openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3` (temp 0.1, grouped criteria, 3 repetitions per row). `ans_conciseness` and `resp_speed` are computed from text and latency, the two `ref_correctness` axes from the reference key; the ref axes exclude rows with no annotated expected references.

| metric | arm A (OFF) | arm B (ON) | Δ (B − A) | A min–max over generations | B min–max |
| :-- | --: | --: | --: | :-- | :-- |
| Ans. Correctness (Loose) | 95.56 | 97.78 | **+2.22** | 95.56–95.56 | 97.78–98.52 |
| Ans. Correctness (Strict) | 91.89 | 94.59 | **+2.70** | 91.89–91.89 | 94.59–94.59 |
| Ans. Conciseness | 41.84 | 69.04 | **+27.20** | 41.61–42.13 | 68.79–69.41 |
| Ref. Correctness (Loose) | 97.14 | 100.00 | **+2.86** | 95.71–100.00 | 98.57–100.00 |
| Ref. Correctness (Strict) | 76.67 | 80.95 | **+4.29** | 72.38–76.67 | 79.52–82.38 |
| Ref. Conciseness | 40.84 | 50.71 | **+9.88** | 40.03–44.24 | 50.67–52.38 |
| Regulatory Tone | 100.00 | 100.00 | **+0.00** | 100.00–100.00 | 97.30–100.00 |
| Resp. Speed | 70.21 | 79.10 | **+8.90** | 70.02–71.16 | 79.10–79.27 |
| **OVERALL (geometric mean)** | 72.72 | 82.07 | **+9.34** | 71.86–73.94 | 82.01–82.37 |

Per-generation detail (the raw inputs to the medians above):

| arm | generation | Ans. Correctness L | Ans. Correctness S | Ans. Conciseness | Ref. Correctness L | Ref. Correctness S | Ref. Conciseness | Regulatory Tone | Resp. Speed | overall |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| A | 1 | 95.56 | 91.89 | 41.84 | 97.14 | 76.67 | 40.84 | 100.00 | 70.02 | 72.72 |
| A | 2 | 95.56 | 91.89 | 41.61 | 95.71 | 72.38 | 40.03 | 100.00 | 70.21 | 71.86 |
| A | 3 | 95.56 | 91.89 | 42.13 | 100.00 | 76.67 | 44.24 | 100.00 | 71.16 | 73.94 |
| B | 1 | 98.52 | 94.59 | 69.04 | 100.00 | 79.52 | 52.38 | 100.00 | 79.10 | 82.37 |
| B | 2 | 97.78 | 94.59 | 68.79 | 100.00 | 82.38 | 50.71 | 97.30 | 79.10 | 82.01 |
| B | 3 | 97.78 | 94.59 | 69.41 | 98.57 | 80.95 | 50.67 | 100.00 | 79.27 | 82.07 |

## Comparable subset (the only rows that can move)

Requested 37 rows → **27 comparable** (floor 20); a row is comparable when the PRIMARY leg served its graded answer in at least 2 of the 3 generations **in both arms** — a deterministic Stage-1 draft cannot respond to a prompt-side lever.

* dropped `arm_A_not_primary[none]`: 9 — rg_001, rg_013, rg_019, rg_022, rg_025, rg_031, rg_040, rg_043, rg_076
* dropped `arm_B_not_primary[none]`: 9 — rg_001, rg_013, rg_019, rg_022, rg_025, rg_031, rg_040, rg_043, rg_076
* dropped `arm_A_not_primary[deterministic]`: 1 — rg_085

Draw-to-draw dispersion on the comparable subset (why three generations, not one):

| | arm A | arm B |
| :-- | --: | --: |
| rows whose criteria credit moved between generations | 0 | 1 |
| rows whose *all-criteria* verdict flipped | 0 | 0 |
| mean per-row spread (pp) | 0.0 | 1.23 |

## Transport shape (what the arms actually dialled)

| arm | rows | graded calls | deterministic rows | payload legs | fallback dials answered | fallback dials total | primary failed | refusals (named) |
| :-- | --: | --: | --: | :-- | --: | --: | --: | :-- |
| r423-need4-A | 37 | 23 | 10 | fallback×5 (system 59644–59644 ch), primary×21 (system 61–59644 ch) | 0 | 1 | 1 | groq×1 |
| r423-need4-B | 37 | 168 | 9 | fallback×3 (system 1311–1311 ch), primary×293 (system 61–6365 ch) | 0 | 0 | 0 | — |

Gate verdict: **VALID** — no reasons recorded.
* warning: r423-need4-A: the fallback leg was dialled 1 time(s) and answered 0 (primary_failed=1) — a dead or failing fallback credential. Rows that shipped a draft because of it belong in the excluded set, not averaged over.
* warning: 1 transport-degraded row(s) were excluded from BOTH arms by the caller (of r423-need4-A 37 row(s), r423-need4-B 37 row(s)); the deltas are reported on the survivors, and the caller owns the drop count.

## Method notes (what makes this a gate rather than a printout)

1. **The void guard decides before any delta is printed.** The runner's own `gate_validity.assess` reads the transport counters it incremented and the payloads it hashed. An arm served by the fallback, an arm whose graded rows are majority-deterministic drafts, a refusal, asymmetric fallback pressure, and generations that were replays are each a VOID.
2. **Generations are real draws.** The route answers from an in-process response cache keyed on (question, context, history depth, env); without clearing it, generations 2..K replay generation 1 (measured on the first R423 gate: 23 of 37 rows byte-identical at 1.6 s against 43.6 s). `run_official_batch._clear_engine_cache` clears it before every sample.
3. **Every paired number is a per-row median over the three generations**, with a bootstrap CI over rows, and the comparability exclusion is symmetric — a row lost by either arm is reported and excluded from both.

## Artifacts

| path | what |
| :-- | :-- |
| `evals/bench/results/official-r423-need4-[AB]-hard*.ckpt.jsonl` | the 6 generation checkpoints |
| `evals/bench/results/official-r423-need4.json` | runner sidecar incl. the gate verdict |
| `docs/measurements/r423/need_gate.json` | paired deltas, comparable subset, dispersion |
| `docs/measurements/r423/judge-cache-r423.jsonl` | the judge's per-answer verdicts |
| `app/engines/answer_need.py` | the estimator, the clause, the flag |
| `docs/measurements/r423/CHECKPOINT.md` | design, offline calibration, and the falsifications |

