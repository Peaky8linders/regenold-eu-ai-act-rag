# R423 checkpoint — the need-proportional answer contract

**Status: the lever is built and offline-calibrated; the first hard-split gate ran
to completion on both arms and was correctly VOIDED — and it falsified its own
"3 independent generations" claim on the way (§5.1). Both defects it exposed are
fixed, the fix is proven end-to-end on a live 2-row smoke (§5.2), and the corrected
gate is re-running. This file records the design, the measured basis, every
falsification, and the exact resume commands.**

## 1. What the lever is

`REGENOLD_NEED_PROPORTIONAL_CONTRACT` (**default OFF**) — one deterministic
estimate of what a question actually engages, rendered twice:

| rendering | where | what changes |
| :--- | :--- | :--- |
| the ANSWER SHAPE clause | `app/engines/answer_need.shape_directive`, appended by `graph_rag_prompts.build_evidence_answer_user` | the model is told how many items the ask engages, a target word count, and that members outside that set are context — not required content |
| the scoped closed-set skeleton | `_graph_rag_impl._render_closed_set_skeleton(engaged=...)` | engaged members keep their lead text; the rest keep only their coordinate, under a heading that says so |

One estimator feeds both, so the OFF arm is byte-identical to the shipped prompt
(pinned by `tests/test_r423_need_proportional_contract.py`), and the flag has one
reader (`answer_need.need_proportional_contract_enabled`) plus a cache-key entry
(`_engine_cache_key`), without which an in-process A/B would serve arm A's cached
engine output to arm B (the R263.2 bug).

## 2. Why: the R422 measurement this answers

From `docs/measurements/r422/CHECKPOINT.md`, all recomputed here from disk:

| fact | value |
| :--- | ---: |
| hard-mode answer, R390 → R419 (same generator) | 1139 → **2138** chars |
| `ans_conciseness`, same two boards | 62.02 → **44.19** |
| corr(gold criteria, gold reference length) | **+0.55** |
| corr(gold criteria, OUR answer length) | **+0.11** |
| `REGENOLD_CLOSED_SET_SKELETON` fires | **110/110** rows, mean **5,125** chars |

The 1-criteria rows were asked to scaffold 5,862 chars into a 1,122-char answer.
So the shipped contract is flat in exactly the place the axis is scored.

## 3. Two things measured BEFORE the live gate (zero API calls)

Both in `docs/measurements/r423/need_proportional_probe.py` → `need_proportional_probe.json`.

### 3.1 FALSIFIED: a per-row reference-length predictor

A ridge fit of the ask's own features (length, list/exception/conditions shape,
asked heads, cited heads, sub-point grain, plus `items`) reaches:

| feature set | in-sample r | LOO r | LOO ρ | LOO MAE |
| :--- | ---: | ---: | ---: | ---: |
| ask_len, is_list, is_exc, is_cond | 0.288 | 0.108 | 0.172 | 112.2 |
| + asked/cited heads | 0.334 | 0.124 | 0.183 | 110.9 |
| + items | 0.363 | 0.143 | 0.192 | 112.3 |

**Conclusion: do not predict the reference.** The first cut of this module *did* —
`target = 280 + 100*items` — and it was calibrated as if the predictor worked.
That version is deleted, and the negative result is recorded so it is not retried.

### 3.2 What the axis actually responds to: LEVEL

`ans_conciseness = min(1, reference/candidate)` per row, so projecting the gold's
own references against a target gives:

| target | projection |
| :--- | ---: |
| 400 | 0.987 |
| 550 | 0.960 |
| 650 (the reference mean) | 0.912 |
| 1000 | 0.649 |
| **the real R419 answers (2138 chars)** | **0.4419** |

0.4419 **recomputes the published board to four decimals**, which is the
cross-check that this projection is the right arithmetic.

So `items` is used as a monotone FLOOR (target `clamp(360, 300 + 75*items, 1000)`,
75 chars/item matching the R409 repair budget's own per-gap allowance), not as a
prediction. Mean target over the board: **584.8 chars** against a 649.3 reference
mean, projecting **0.897** — *if* the model obeys, which is precisely what the
gate must test, and what the R415 full-system-prompt arm warns about (it bought
+19.2 pp `ans_conc` and cost 7.7 pp `Ans. Strict`).

### 3.3 And the prompt really gets smaller

Also in the same probe, over the board's REAL wire refs:

| measure | value |
| :--- | ---: |
| shipped skeleton chars (37 rows of refs) | 44,587 |
| scoped skeleton chars | 17,980 |
| **saved** | **26,607 (ratio 0.403)** |
| engaged coordinates dropped by the scope | **0** (the anti-gold-drop invariant) |

## 4. Non-vacuity, proven at the provider seam first

`docs/measurements/r423/need_proportional_route_probe.py` runs the REAL route on
real hard-mode messages with the provider stubbed (the seam
`docs/measurements/r415/pushback_invariance_probe.py` established):

| row | OFF payload | ON payload | clause | skeleton |
| :--- | ---: | ---: | :---: | :--- |
| rg_064 | 42,782 | 41,412 | fires | 4 EXHAUSTIVE (3,404 ch) → 4 NOT-ENGAGED (952 ch) |
| rg_085 | 25,018 | 21,760 | fires | 5 EXHAUSTIVE (5,842 ch) → 5 NOT-ENGAGED (1,522 ch) |
| rg_001, rg_022 | — | — | no Stage-2 call at all (deterministic route) | |
| rg_043 | — | — | one non-answer Stage-2 call | |

Two of five sampled rows fire, both controls hold (the OFF arm carries the generic
completeness directive and no clause), and the scoping is exact. **Caveat, and it
is in the artifact**: each arm is a separate route invocation and retrieval is not
byte-stable across invocations (the same OFF row dispatched 19,206 then 42,782
chars on consecutive runs), so the per-row TOTAL delta is contaminated — only the
`sections` breakdown isolates the lever.

## 5. The gate

```
python -m evals.regenold.run_official_batch \
    --label r423-need --mode hard --stride 3 --repeats 3 \
    --baseline-env REGENOLD_NEED_PROPORTIONAL_CONTRACT=0 \
    --branch-env  REGENOLD_NEED_PROPORTIONAL_CONTRACT=1
```

* **37 strided rows** (representative: the full 110 are 46 % easy, `--limit 40` is
  68 % easy — R422), **3 independent generations per row per arm**.
* `--repeats` is new: sample 0 keeps the shipped checkpoint path and `--resume`
  contract, later samples land in `.r1`/`.r2` siblings with the same schema and a
  `sample` key (written by the runner, not patched on afterwards).
* Scored by `docs/measurements/r423/need_gate.py`: the runner's own
  `gate_validity` verdict decides first, then only rows whose Stage-2 landed on
  the PRIMARY leg in **every** sample of **both** arms are compared (symmetric
  exclusion + drop count + a floor of 20), and every number is a **per-row median
  over the 3 generations** with a bootstrap CI.

**Expected comparable rows: ~26** — measured from R419, where 81/110 rows were
primary-served before this lever existed (25 carried no trace, 4 were
deterministic).

## 5.1 The first run: VOID, and its predecessors were wrong about two things

Ran to completion (both arms, 37 rows, 3 generations, `errors=0`), and the runner
refused to print a single delta. Re-read from the checkpoints and the sidecar
(`evals/bench/results/official-r423-need.json`), not from the log:

| | arm A (lever OFF) | arm B (lever ON) |
| :--- | ---: | ---: |
| `answer_chars` (mean, n=37) | 2171.7 | **1204.9** |
| `n_refs` | 3.432 | 3.243 |
| `stage2_landed_rate` | 0.7297 | 0.7568 |
| `stage2_models` | `claude-opus-5` | `claude-opus-5` |
| latency p50 / p90 | 50.7 s / 81.5 s | 43.6 s / 58.7 s |
| `primary_ok` / `fallback_ok` | 107 / 0 | 73 / 0 |
| **fallback dials that answered nothing** | **20** | 0 |
| transport refusals | 3 | 0 |

The lever's *level* effect is therefore the shape the design predicted
(−44.5 % answer length). Whether it is a **win** was not established, because the
run was void: the refusal counter recorded a Stage-2 call blocked by the transport
policy on arm A only, i.e. a failure path was reached on one arm and not the other.
The guard was right to refuse. Two things about *how* it refused were not:

### (a) The "independent generations" were mostly REPLAYS

`--repeats 3` is a claim of three independent draws per row per arm. Measured on
the checkpoints:

| | arm A | arm B |
| :--- | ---: | ---: |
| generations byte-identical to generation 1 | **12/37** (r1), **16/37** (r2) | **23/37** (r1), **23/37** (r2) |
| p50 latency, generations 2 and 3 | 23.8 s, 21.2 s | **1.7 s, 1.6 s** |
| p50 latency, generation 1 | 50.7 s | 43.6 s |
| graded provider calls, whole arm | 131 | **73** |

The route answers from `app.routes.regenold._ENGINE_CACHE`, keyed on
(question, context, history depth, env) — and every generation of a row sends the
same key. Generation 2 and 3 of a cacheable row therefore never dialled a
provider: arm B made **73** calls across three generations whose total ask count
is **74 per generation**. A median over duplicated values reports a draw-to-draw
stability the run never measured, in exactly the shape R422 shipped (a void run
read as a null). Fixed in `run_official_batch._clear_engine_cache` + a
`_repeat_independence` self-check that warns and, in the gate, voids (§5.2).

### (b) "The fallback answered nothing" was invisible

Arm A dialled the Bedrock fallback leg **20 times and served 0 answers from it**
(the credential answers `api_key_invalid_403`), and the verdict did not mention
it: `fallback_ok` is 0 in that shape, so an arm whose tunnel failed repeatedly and
whose fallback is dead read exactly like an arm that never needed either. The same
run also could not say *which* provider the 3 refusals blocked — the counter keeps
`refused_by_provider`, but the reason string narrated "off-contract provider
attempted" instead of naming it, and the arm's payload record merged both legs, so
the 20 full-system (59,644-char) payloads could not be attributed to the leg that
carried them. All three now surface: `refused_by_provider`, `legs`,
`leg_system_lengths`, `fallback_attempts`, `primary_failed`.

## 5.2 The fixes, and the proof they work

| fix | where | evidence |
| :--- | :--- | :--- |
| clear the route response cache before EVERY sample | `run_official_batch._clear_engine_cache` | live 2-row × 2-generation smoke: generation 2 cleared **4** entries, and `rg_004` (primary-served both generations) came back **3144** vs **3480** chars — a real fresh draw, not a replay |
| report + void a replayed generation | `run_official_batch._repeat_independence`, `gate_validity.assess` | a majority-identical pair is now a VOID reason ("the generations were REPLAYS"); the ~24 % curated-intercept floor is tolerated |
| name the refused provider | `gate_validity.assess` | the reason now reads `groq×3` instead of narrating |
| expose failed fallback dials | `ArmProvenance.fallback_attempts` / `primary_failed` | asymmetric fallback pressure between arms is a VOID; symmetric pressure is a warning naming the counts |
| attribute the full system prompt to a leg | `_PayloadRecorder.leg_lengths` | `{'fallback': [59644, ...]}` — the 53 kB system is a leg fact, not a merged histogram |

12 new tests in `tests/test_r423_harness_repeats.py`; the R422 guard tests were
updated for the new provenance call shape.

## 5.3 The second run: VOID too — and this time the cause was the tunnel, not the harness

The corrected run (`r423-need2`) also ran to completion (both arms, 37 rows, 3
generations, `errors=0`) and also refused to print a delta. Read from the run log
and the six checkpoints:

```
233  wrapper_call_failed: network_error: [Errno 11001] getaddrinfo failed
  8  [WinError 10065] A socket operation was attempted to an unreachable host
  2  The read operation timed out
243  -> exactly the 243 Groq fallbacks the transport policy then refused
```

`getaddrinfo failed` means the wrapper hostname did not RESOLVE. The path is then
forced: the legacy Groq hatch is refused by the strict-transport policy (by
design), the Bedrock credential answers `api_key_invalid_403`, so every one of
those 243 calls shipped a deterministic Stage-1 draft. Per-generation provenance,
read from the checkpoints and not from the log:

| | primary | fallback | deterministic |
| :--- | ---: | ---: | ---: |
| A sample 1 | 28 | 0 | 0 |
| A sample 2 | 19 | 0 | 9 |
| A sample 3 | **0** | 0 | **28** |
| B sample 1..3 | **0** | 0 | **28** |

The void guard was right on every count — and this run is the case it was built
for. But it exposed two more holes, both in *how much the verdict can see*:

### (a) An arm-level total hid a fully degraded generation

`deterministic_graded` is computed from `sample 0`'s rows only, while every number
the gate publishes is a per-row MEDIAN across all three generations. So arm A read
**healthy** — 47 primary completions, `deterministic_graded=0` — while its third
generation was 28/28 drafts. That bias is silent and directional: the degraded
generation's answers are short (median 1083 chars against 2285 for A's healthy
sample 1), so it moves A's median length toward the deterministic draft and
contaminates the delta the gate is trying to measure. Had arm B been healthy, the
gate would have published that contaminated delta as a lever result.

**Fixed:** `ArmProvenance.sample_deterministic` (per-generation counts, written by
the runner via `probe.provenance(sample_rows=replicates)`), and `assess` now voids
a gate when ANY generation is majority-deterministic — the same majority rule it
already applied at arm level, applied where the medians actually come from. The
measured shape above is a regression test.

### (b) 90 minutes and 243 calls were spent finding out

The void guard can only say "this run is unreadable" *after* the sample is gone,
and a degraded run is not a lever result at any sample size. So the runner now
guards the transport itself:

* **Pre-flight** — one real 16-token completion through the wrapper before the
  first row is spent. It exercises DNS, CF Access and the OAuth token in one call,
  and it is the check that would have aborted this run at minute zero.
* **Abort on outage** — the batch stops after **5 consecutive** Stage-2 calls fail
  to reach a leg. The streak resets on any success, so it fires on an outage and
  not on noise.
* Opt out with `--allow-degraded-transport`, for a run that deliberately measures
  the degradation path.

Proven on the real path: pre-flight returned
`Stage-2 transport preflight OK (model=claude-opus-4-8)` with the tunnel up, and
refuses with `network_error: [Errno 11001] getaddrinfo failed` when it is not.

## 5.4 The third run (`r423-need3`) — and why it is slower by design

Re-launched with the guard armed. It is *legitimately* slower than the voided
run: 26.8 s and 118.6 s for the first two rows against the voided run's median
24 s. That gap is the R423 sample-cache fix working — with the route cache now
cleared before every generation, generations 2 and 3 are real provider draws
instead of 1.6 s replays. Cheaper was not better here; it was the bug.

One caveat, and it is run-invariant: the first Cohere embedding call returns
HTTP 429 and the dense index warms up on the SVD path
(`turboquant_index: external embeddings returned None, falling back to SVD path`).
The same two lines appear in the voided run, so it is not a regression — and it
cannot bias the paired delta, because both arms retrieve through the same index
inside one run. It does mean the absolute board is an SVD-index board, which is
the condition every prior gate on this box has also run under.

## 5.5 The fourth launch (`r423-need3`, resumed) — the restart cost nothing

The machine restarted 2.5 of 3 hours into the third launch. What was on disk:
arm A held all three generations (37 rows each), arm B held one complete
generation plus 15 of 37 rows of the second. Re-launching re-drew **zero** of
that: the four complete generations printed `resuming: 37 complete, 0 pending`,
and arm B's half-finished generation printed `resuming: 15 complete, 22
pending`. Two harness defects made that possible, and both were real:

* **Resume was gated on `k == 0`**, so replicas always started from scratch. A
  re-launch would have discarded four finished generations (~1.5 h of live
  provider draws). The validator is per FILE and a replica file holds each row id
  once — the ids repeat ACROSS samples, not within one — so the repeated-id check
  that catches a truncated checkpoint is unaffected by resuming a replica.
* **The gate's zero-completion rule read only in-process counters**, so a resumed
  arm (`primary_ok=0, fallback_ok=0, calls=0`, 37 graded rows) was VOIDed as
  "ZERO Stage-2 completions" — the guard would have refused a valid run on a
  restart. The graded rows already record which leg served them
  (`provenance.stage2_served_by`), which is the same evidence the per-sample and
  per-arm determinism rules read, so the rule now accepts it. It is unchanged in
  the outage it was written for: there, no row names a leg either, and a row
  naming the fallback leg still VOIDs.

## 5.6 The gate result (`r423-need3`) — VALID, and the lever KEEPS OFF

37 strided hard rows × 3 independent generations × 2 arms, judged by
`openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3` (the R419 board's
exact instrument, cache seeded from it). **The void guard is clean**: no
fallback-served row, no refusal, `fallback_attempts=0`, `primary_failed=0`,
byte-identical rates **27 % / 24 %** (the curated deterministic floor).

**27 of 37 rows are comparable** — primary-served in ≥2 of the 3 generations in
BOTH arms. The 10 dropped rows are dropped SYMMETRICALLY (9 rows never reach
Stage-2 at all in either arm, `rg_085` degraded in arm A), so the lever is not
being credited with the rows it cannot touch.

Every number below is a per-row **median over the three generations** on that
same 27-row subset:

| axis | A (OFF) | B (ON) | Δ |
| :-- | --: | --: | --: |
| Ans. Correctness (Loose) | 96.97 | 92.93 | **−4.04** |
| Ans. Correctness (Strict) | 92.59 | 85.19 | **−7.41** |
| Ans. Conciseness | 22.18 | 68.09 | **+45.91** |
| Ref. Correctness (Loose) | 98.15 | 96.30 | −1.85 |
| Ref. Correctness (Strict) | 70.37 | 75.93 | +5.56 |
| Ref. Conciseness | 37.35 | 57.96 | **+20.62** |
| Regulatory Tone | 100.00 | 96.30 | −3.70 |
| Resp. Speed | 65.95 | 76.32 | +10.37 |
| **OVERALL (geometric mean)** | 65.04 | 79.96 | **+14.91** |

Paired per-row deltas: `ans_loose` −3.95 pp (0 up / 2 down / 25 tied),
`ans_strict` −7.41 pp (same 2 rows), answer length **−2047.9 chars** (27 of 27 rows
shorter), `ref_strict` +9.26 pp (3 up / 0 down). Gold heads dropped: A 1
(`rg_061` / Article 75) vs B 1 (`rg_106` / Annex III) — the lever trades one drop
for another, it does not reduce drops.

**Verdict: KEEP OFF.** The pre-registered rule (correctness no worse than −1.0 pp)
refuses it on `ans_loose` −3.95 and `ans_strict` −7.41. The whole correctness cost
is **two rows**, both reproducible in all three generations, and both a length
starvation rather than an extraction failure:

| row | A chars | B chars | A loose | B loose | what it is |
| :-- | --: | --: | --: | --: | :-- |
| `rg_010` | 2763 | 379 | 100 % | 60 % | "which article governs human oversight" — 4 criteria, read as a one-item ask |
| `rg_106` | 2651 | 442 | 100 % | 33 % | supermarket anomaly tool — needs the risk-tier analysis; B also loses `Annex III` |

So the honest reading is: the mechanism works (conciseness +45.9 pp, overall
+14.9 pp, speed +10.4 pp) and the estimator's item count is the part that is
wrong — exactly what the offline calibration said (59/110 rows called "1 item"
while only 4 rows truly have 1 criterion). The fix that follows is a
content-preservation contract tied to the Stage-1 draft's own engaged set, not a
bigger length target. Report: `docs/reports/r423-need-proportional-gate.md`.

## 5.7 Caveat — the gate measured the STRIPPED-prompt path, and live single-turn

already answers like the lever's ON arm

The post-deploy live check (commit `dd87fd45e3ae`) asked `rg_010`'s question to
production, single-turn, with no history:

```
"Which article of the EU AI Act governs human oversight measures?"
  -> 316 chars, refs ['Article 14.1'], stage2_served_by=primary, 19.9 s
```

That is the **lever's ON shape**, not its OFF shape. In the gate:

| | turn 1 (3 generations) | pushback (3 generations) |
| :-- | :-- | :-- |
| `rg_010` arm A (OFF) | 2772 / 2702 / 2805 | 2776 / 2715 / 2763 |
| `rg_010` arm B (ON) | 317 / 378 / 460 | 379 / 324 / 467 |

and across the comparable subset the lever compresses both turns by the same
amount (turn 1: 3111 → 1068 chars mean; pushback: 3092 → 1028). The reason is the
configuration, not the lever: a hard-mode request dispatches the **61-char
persona** (`leg_system_lengths` in the gate sidecar is 61 for 108 of 109 primary
calls, with a single 59,644-char call), while live single-turn gets the FULL
53 kB system prompt through `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=1` (R412) —
which is itself the prompt that R412 measured as compressing answers ~58 %.

So the honest scope of this gate: **it measures hard mode under the stripped
prompt.** The +45.91 pp conciseness win and the −7.41 pp strict loss both belong to
that configuration, and the live single-turn path already reaches a comparable
shape on this row without the lever. What is NOT measured, and is the next
question, is the lever's incremental effect where production actually lives (the
full-prompt single-turn path), and the hard path with the full prompt delivered
(R411 gap 3.1). Neither changes the verdict for the hard board as it ships today.

## 6. Defects found and fixed on the way

* **`--help` was broken on the whole runner.** `--stride`'s help contained a bare
  `%`; argparse interpolates help strings, so `--help` raised
  `TypeError: must be real number, not dict`. Escaped, and pinned.
* **Replica resume**, and **row-level Stage-2 evidence in the void guard** — see
  §5.5. Both are pinned by `tests/test_r423_harness_repeats.py`
  (`TestAResumedArmIsNotVoided`) and
  `test_a_restart_resumes_finished_replica_generations`.
* **The report's per-arm correctness axes were VACUOUSLY 100.** `build_need_report`
  rebuilt the rows from the checkpoint (`load_ckpt` → `build_rows` → `score_rows`),
  but a checkpoint carries no judge verdicts — the criteria live in the score
  artifact — so `criteria` came through empty and `answer_correctness_loose([])`
  returned 1.0. It printed 100.00/100.00 on both correctness axes while the paired
  board was reporting a real regression: the most dangerous shape a report can have,
  because it looks like a clean win. The per-arm board now reads the scorer's own
  artifact.
* **The paired report scaled an absolute count by 100.** `delta_answer_chars` was
  printed as "−204789 pp" for what is −2048 characters; the aggregation now carries
  units per axis.
* **The gate reported only the axes it was aimed at.** `need_gate --score` judged
  answer correctness, answer length, tone and reference strictness, but the
  official aggregate is a GEOMETRIC mean over all eight axes: a lever that
  shortens answers while paying for it in reference conciseness or speed is not a
  win, and four axes were not in the report at all. `official_axes` now recomputes
  the official instrument (`evals.official.rubric.score_rows`) on exactly the
  comparable subset, per arm and per generation, and reduces each axis by a median
  across generations — so the gate publishes all eight axes plus `overall`, and
  the ship rule refuses an aggregate regression of more than 0.5 pp.
* **`score_arm` keeps a judge cache keyed on the answer**, so 3 generations cost
  3 cache entries per row, not 3x the calls on a re-run — which is what makes a
  3-generation gate affordable at all.

## 7. Artifacts

| path | what |
| :--- | :--- |
| `app/engines/answer_need.py` | the estimator, the clause, the flag |
| `app/data/graph_rag_prompts.py` | the scoped completeness directive + clamp wiring |
| `app/engines/_graph_rag_impl.py` | the scoped skeleton render and the per-request estimate |
| `docs/measurements/r423/need_proportional_probe.py` | M1/M1b/M1c/M2/M3, offline |
| `docs/measurements/r423/need_proportional_route_probe.py` | provider-seam non-vacuity |
| `docs/measurements/r423/need_gate.py` | the paired gate scorer; all eight official axes on the comparable subset |
| `evals/regenold/run_official_batch.py` | `--repeats`, `sample` on every row, the Stage-2 transport pre-flight + `--allow-degraded-transport` |
| `evals/harness/gate_validity.py` | `sample_deterministic` + the degraded-generation VOID |
| `tests/test_r423_need_proportional_contract.py` | 27 tests |
| `tests/test_r423_harness_repeats.py` | repetitiveness + the degraded-sample VOID |
| `tests/test_r423_stage2_transport_guard.py` | the pre-flight and the abort-on-outage |
| `tests/test_r423_gate_report.py` | the eight-axis board: median over generations, excluded ref rows |

## 8. Resume

```bash
# the gate checkpoints per row, EVERY generation included; continue where it stopped
python -m evals.regenold.run_official_batch --label r423-need3 --mode hard \
    --stride 3 --repeats 3 --resume \
    --baseline-env REGENOLD_NEED_PROPORTIONAL_CONTRACT=0 \
    --branch-env  REGENOLD_NEED_PROPORTIONAL_CONTRACT=1
# then score + aggregate (all eight axes, void guard first)
python docs/measurements/r423/need_gate.py --score
```

A resumed launch re-uses the generations already on disk for the arm, the sample
and the row they were drawn for. It re-draws nothing, and the verdict is built
from the rows rather than from what this process happened to see (§5.5).

---

# R423.1 — the fix that makes the lever shippable: no anchor is NOT a small ask

## 9.1 What the first gate actually lost, read at the criterion level

§3 kept the lever OFF on a two-row correctness cost. Read from the judge cache
(`judge-cache-r423.jsonl`) rather than from the aggregate, both lost rows are rows
where the estimator found **no anchor at all** — `asked` and `engaged` are BOTH
empty — and each failure is a mechanism, not a statistic:

| row | ask | reference | ON arm, all 3 generations | expected criteria |
| :--- | :--- | ---: | :--- | :--- |
| `rg_010` | "Which article of the EU AI Act governs human oversight measures?" | 759 ch | `[T,T,F,T,F]`, `[T,T,F,F,F]`, `[T,T,F,T,F]` — 14(2)'s **aim** and 14(4)'s five **overseer capabilities** omitted, in every draw | the substance of Article 14(1)-(4) |
| `rg_106` | a supermarket bag-check scenario asking whether it is high-risk | 781 ch | `[T,F,F]` ×3 — "focuses on Article 5 instead", **`Annex III` dropped from the wire refs** | Annex III.6's law-enforcement confinement |

So the estimator did not merely mis-size these two asks. It asserted the MINIMUM
target (375 chars, via a fall-through `items = 1`) **and** — because an empty scope
was rendered as the shipped "NOT ENGAGED by this question: context only, do NOT
enumerate or list them" — it ordered the model not to enumerate the members of the
very provision each question is about. Both rows' whole criteria are those members.

That is a category error in the module, and the honest statement of it is:
**empty engagement is ABSENCE OF SIGNAL, not evidence of a small ask.** The
detector is the R410 question-side rule, deliberately strict because it gates a
completeness DEMAND (it cut false positives 7/71 → 0/71). Strictness is right for
demanding and wrong for sizing and for forbidding.

## 9.2 The no-signal state is not a corner case

`need_floor_projection.py`, section A, offline:

```
unanchored rows: 80/110 (73% of the board)
their reference answers: mean=646 median=657 p25=553 p75=747 min=160 max=985
```

73 % of the board. So the level is not a patch for two rows — it IS the lever,
which is exactly why it had to be chosen on the subgroup rather than on the rows
that exposed the bug. (It also retires a framing from §1: on this board the
"proportional" mechanism is inert on 73 % of rows and the axis moves on LEVEL.
`need_gate.json`'s comparable set agrees — 22 of its 27 rows are unanchored.)

## 9.3 The fix (three coordinated changes, one root cause)

1. **`answer_need` gains `anchored`.** False when the ask names no coordinate AND
   engages no closed set.
2. **The no-signal target is the subgroup's own central reference length**
   (`_TARGET_NO_SIGNAL_CHARS = 650`, subgroup median 657 / mean 646), applied as a
   FLOOR, not a replacement: an unanchored ask that still asks for an exception or
   a condition keeps the larger of the two. The exception path now fails OPEN
   (650) rather than to the minimum, because an estimator that could not run has
   no evidence of a small ask either.
3. **An unanchored scope is no longer a prohibition.** The skeleton's
   coordinates-only branch still fires, but its header becomes "this question
   names no provision, so none is individually required: context for wording and
   citation grain — state and cite the member your answer relies on". The shipped
   prohibition is kept for the case that earns it: an ask that engages a DIFFERENT
   provision (a real signal). The clause gains an unanchored shape that names the
   governing provision first and demands the limbs of THAT provision, because on
   these asks the graded criteria ARE those requirements.

## 9.4 The level choice, and the alternatives that were falsified

`need_floor_projection.py` section B, projected with the only measured per-row
lengths that exist (the first gate's ON arm) and **restricted to rows the lever
can actually reach** (Stage-2 primary-served; a curated-intercept row is answered
identically in both arms and no floor can move it — the first cut of the probe
included 7 such rows and reported `rg_076` as a 75 pp casualty of a floor it never
sees; the route probe measured **0** Stage-2 dispatches for it in either arm):

| floor | mean Ans. Conciseness | rows moved | worst row |
| ---: | ---: | ---: | :--- |
| 375 (shipped) | 71.29 % | 0 | — |
| 450 | 71.29 % | 2 | `rg_010` +0 pp |
| 550 | 71.29 % | 4 | `rg_010` +0 pp |
| **650 (chosen)** | **70.07 %** | 4 | `rg_091` −14 pp |
| 750 | 67.87 % | 7 | `rg_091` −26 pp |
| 850 | 64.10 % | 10 | `rg_091` −34 pp |

The cost of the chosen floor is **−1.22 pp on one axis** over the 23 reachable
unanchored rows, and it is **free below 550** (those rows' own references sit above
the floor, so the extra room is correctness headroom nobody pays for). It is worth
stating why the floor survives at all rather than being dropped: `Ans. Conciseness`
is `min(1, ref/candidate)`, so it **saturates** — a candidate under the reference
scores exactly what one at the reference scores. Undershooting a reference-length
answer therefore buys zero conciseness and costs correctness.

**A graded floor was tested and REJECTED** (section C): nothing the estimator can
see predicts an unanchored ask's reference length — corr(ask length, ref length)
= **+0.23** Pearson / +0.16 Spearman over the 80 rows, and the one feature that
does predict it (criteria count, r = **+0.56**) is not available at inference. A
ridge fit of the ask's own features was already falsified leave-one-out at
r = 0.10–0.14. A formula keyed on any of that would be a number nobody measured,
which is the defect the module's first calibration actually was.

## 9.5 Non-vacuity, then two live screens, then the gate

**Provider seam** (`need_proportional_route_probe.py`, stubbed, no live call) —
`R423_IDS` is new so the rows a gate lost can be revisited by name instead of by
stride luck. On `rg_010, rg_046, rg_076, rg_106`: clause fires 4/4, OFF arm inert
4/4, the unanchored header reaches the wire, `do NOT enumerate` appears in neither
arm (the OFF arm renders the EXHAUSTIVE demand instead), and the OFF arm's
skeleton is still byte-identical in role. Payload delta −408 / −3,103 / +282 ch
(skeleton 2,908 → 816 ch on `rg_010`).

**Live screen 1** — `--ids rg_010,rg_106,rg_082,rg_091,rg_094,rg_007,rg_079`,
one generation per arm. Arm A completed; arm B was aborted at row 5/7 by the R423
transport guard (5 consecutive read timeouts — the guard doing its job). Both
target rows completed:

| row | prior gate B | screen 1 B | movement |
| :--- | :--- | :--- | :--- |
| `rg_010` | 379 ch, 3/5 | 769 ch, **4/5** | the 14(2) aim clause came back; 14(4) still omitted |
| `rg_106` | 442 ch, 1/3 | 876 ch, **3/3** | **fixed**, and `Annex III.6.d` is back on the wire |

`rg_010`'s remaining gap was pinned by ask, not assumed: **both arms' dispatched
payloads already carry Article 14(4)'s verbatim text** ("enabled, as appropriate
and proportionate"; "understand the relevant capacities"), so it was a budgeting
failure, not a retrieval one — 4 of 4 draws missed it. The unanchored clause was
sharpened to name what has to fit ("one short clause each … a limb the evidence
carries and the answer leaves unstated is a failed criterion").

**Live screen 2** — `--ids rg_010`, judged with the board's own instrument
(`openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3`):

| arm | chars | criteria | wire refs |
| :--- | ---: | :--- | :--- |
| A (OFF) | 2,563 | **5/5** | `Article 14.4`, `Annex III` |
| B (ON) | 1,359 | **5/5** | `Article 14.4`, `Annex III` |

Both rows the first gate lost are therefore restored, at 1.36 kb against the OFF
arm's 2.56 kb on that row.

## 9.6 What is still unproven, and what decides it

The screens are 1 generation on 2–7 rows. The clause change applies to **all 80
unanchored rows**, so its broad cost is not settled by two rows, and it is the one
change whose size response cannot be projected offline. The decision instrument is
the pre-registered gate re-run on the SAME sample and the same instrument as §3
(37 strided rows × 3 independent generations × 2 arms)

## 10. R423.1 and R423.2

The OFF verdict above was correct and is superseded by a correction of the
estimator, not of the rule: `docs/measurements/r423/CHECKPOINT-r4231.md`.
Short version — both lost rows are rows where the estimator found NO anchor, and
an empty anchor is absence of signal, not a small ask; the re-run gate and its
pre-registered accept rule are staged there.

**R423.2 — the re-run (`r423-need4`) SHIPPED the lever; it is now default ON.**
All five pre-registered conditions held on the 27 comparable rows: correctness
`+0.00 / +0.00` pp (the cost above is gone), answers `−2107.96` chars, official
aggregate **65.62 → 79.56 (+13.93 pp)**, gold heads dropped `1 → 0`. The same
re-run also forced a guard fix — a single transport-degraded row (`rg_085`) was
voiding the whole paired run, so `gate_validity.assess` now accepts an ACCOUNTED
symmetric exclusion (`excluded_rows`). See `CHECKPOINT-r4231.md` §9–§11,
`docs/reports/r423-need-proportional-gate.md` (the `r423-need3` KEEP-OFF report is
preserved verbatim as `docs/reports/r423-need-proportional-gate-need3.md`).
