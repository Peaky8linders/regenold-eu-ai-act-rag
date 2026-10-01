# R460 — the conciseness-calibration gate on the SHIPPED transport (wrapper, Opus 5.5)

**Verdict: `REGENOLD_CONCISE_CALIBRATION` stays DEFAULT OFF. Not promoted.**

The mechanism reproduces — the citation-count axis moves the same way on both
transports (+5.52 pp here, +4.76 pp on the Bedrock gate, both CIs excluding zero) —
but on the transport and model that actually ship, the lever makes answers
**longer** (+65 chars, 17/26 rows, CI [+10, +119]) and the board **drops overall
86.90 -> 86.09**. The promotion criterion was "does the conciseness direction
reproduce"; the answer-axis half of it reproduces *in reverse*, and the
conciseness objective the lever exists for (`ans_conciseness`) is the axis it
loses. A prepared promotion patch is on disk, **deliberately unapplied**
(`promote_conciseness_calibration.py`).

## 1. Why this run exists, and what it is not

`GATE-CONCISENESS-BEDROCK.md` confirmed the mechanism on an inverted transport
contract and on `eu.anthropic.claude-opus-4-6-v1`, not on the shipped
configuration. The stated confirmation step was the same paired A/B on the
Claude Max wrapper with `claude-opus-5-5`.

* Both arms run the **shipped** transport and model. No env inversion: the
  primary is the tunnel, and the harness's own transport guard is armed
  (no `--allow-degraded-transport`).
* Tunnel liveness was probed before spending an arm
  (`wrapper_tunnel_probe.py`: `claude-opus-5-5` answered, 7.3 s, stop).
* n=37 again (`--stride 3`, the same representative sample as every board in
  this round), one generation per row. This is a **transport confirmation, not a
  second power study**: the deltas it reports are all-or-nothing on direction,
  and the one that decides the verdict is systematic at the row level (§3.2).
  Replicates 2-3 are a one-command top-up (`run_gate_wrapper.sh 3` resumes the
  existing checkpoints) and were not spent against a tunnel the operator had
  already flagged as low on quota.

```bash
# generation (both arms, sequential, paced -- trial Cohere key: 10 rerank/min)
bash docs/measurements/r460/run_gate_wrapper.sh 1
#   arm A  r460-tunnel-off-s3   (flag absent -> OFF)
#   arm B  r460-tunnel-on-s3    (REGENOLD_CONCISE_CALIBRATION=1)
#   --mode hard --stride 3 --require-cohere-rerank --cohere-rerank-min-gap 7
# judge + decision (Bedrock judge: the tunnel's budget belongs to GENERATION)
bash docs/measurements/r460/score_gate_wrapper.sh
```

* The arms differ by the flag ALONE and that is checkable on the artifacts:
  every row of both arms carries the same `hard_preamble_digest`
  (`cb85452c9c04`), the request shape is fixed mode, and the route's engine cache
  was cleared for the sample (so no arm answered from the other's generation).
* Both arms: **37/37 rows, 0 errors**, 16.6 / 18.4 min, p50 21.4 s / 22.0 s.
* Judge identity `bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`,
  shared cache `judge-cache-r460-bedrock.jsonl` — the same instrument as the
  R436 / R419 boards, the Bedrock conciseness arms and the wrapper re-baseline.
* `--length-control` on both arms (the R460 instrument), so the answer axes are
  readable at equal length.

## 2. The board (paired, n=37, `paired-r460-conc-wrapper.json`)

| axis | A (OFF) | B (ON) | delta | 95% CI | McNemar |
| :-- | --: | --: | --: | :-- | :-- |
| ans_correctness_loose | 95.72 | 94.82 | −0.90 | [−8.11, +5.41] | 1/1 |
| ans_correctness_strict | 91.89 | 91.89 | +0.00 | [−8.11, +8.11] | 1/1 |
| ans_conciseness | 82.32 | 77.84 | **−4.49** | **[−8.77, −0.68]** | 8/17 p=0.108 |
| ref_correctness_loose | 100.00 | 97.14 | −2.86 | [−8.57, +0.00] | 0/1 |
| ref_correctness_strict | 84.76 | 84.76 | +0.00 | [0, 0] | 0/0 |
| ref_conciseness | 58.43 | 63.95 | **+5.52** | **[+0.71, +11.90]** | 7/1 p=0.070 |
| regulatory_tone | 100.00 | 97.30 | −2.70 | [−8.11, +0.00] | 0/1 |
| resp_speed | 90.16 | 88.21 | **−1.96** | **[−3.58, −0.44]** | 6/31 p<0.0001 |
| **overall (geo mean)** | **86.90** | **86.09** | **−0.81** | | |

`gold_dropped_head` A=0, B=1 (`rg_037`). Mean answer chars 803 -> 867; mean refs
per row 2.78 -> 2.51.

Length-controlled (answers cut to their own reference length):

| arm | raw ans_loose | LC ans_loose | raw ans_strict | LC ans_strict | ans_conc | answers cut |
| :-- | --: | --: | --: | --: | --: | --: |
| A (OFF) | 96.30 | 55.56 | 91.89 | 54.05 | 100.0 | 27/37 |
| B (ON) | 93.33 | 42.96 | 91.89 | 40.54 | 100.0 | 28/37 |

Not attributed here, deliberately: the length-controlled gap (-12.6 pp) contains
the two degraded rows above (B's `rg_037` is all-False on both passes) and cutting
B's longer answers removes more text than it removes from A's, so the pass moves
which criteria are at risk as well as how many. It is reported because the round's
instrument exists to report it, not because this gate can price it.

## 3. What each delta is actually made of

The board alone would mislead here, twice. Both attributions below are computed
from the recorded per-row data (`wrapper_gate_subset.py`,
`wrapper_gate_leg_split.py`), and the recomputation is asserted against the
scored axis before it is used.

### 3.1 `ref_conciseness` — LEVER. Reproduces.

+5.52 [+0.71, +11.90], 7/1 row flips, and the underlying count falls in the
intended direction (2.78 -> 2.51 refs/row, B cites fewer provisions on 7 rows,
more on 1). This is the axis the block's numeric budget targets, it is computed
from the reference LISTS and never touches the judge, and it reproduces the
Bedrock gate's +4.76 [+0.29, +10.43] almost exactly. The count mechanism is real
and transport-invariant.

### 3.2 `ans_conciseness` — LEVER. Reverses.

−4.49 [−8.77, −0.68]. Not a single-row artifact and not the transport split:
on the 26 rows whose graded (post-pushback) turn was polished by the tunnel
primary in BOTH arms, the delta is −4.15, with answers **+65.5 chars
(17/26 rows longer, median +51, bootstrap CI [+10, +119])**. On the Bedrock
gate the same lever SHORTENED answers (786.7 -> 755.8 chars, ans_conc +1.97).
The length half of the block therefore has a transport/model-dependent sign:
helpful on `opus-4-6`, harmful on the shipped `opus-5-5`, which writes a longer
answer while still naming fewer provisions.

This is why the lever is not promoted: the round's stated goal was to move
**answer and reference conciseness** past the frontier, and on the shipped
transport the lever moves one of the two the wrong way.

### 3.3 Correctness, tone and the gold-head "drop" — NOT the lever.

The macro answer delta (−0.90) is carried by exactly **two rows**, and both are
transport-degradation events:

| row | leg A | leg B | criteria A | criteria B |
| :-- | :-- | :-- | --: | --: |
| `rg_037` | primary | **prior_turn** | 6/6 | 0/6 |
| `rg_049` | **deterministic** | primary | 1/3 | 3/3 |

`prior_turn` means B's graded turn never landed and the pre-pushback answer
shipped (its refs are `Article 49.4/71.4/6.3` against the key's `Annex VIII.a`);
`deterministic` means A fell to a Stage-1 draft. On the other 35 rows the
judged criteria vectors are identical between arms — the suite's own verdict, not
a lenient reading. Net of those two events the correctness axes are a dead heat.

Same reading on tone (−2.70, one row) and `ref_correctness_loose` (−2.86, the
same row). The Bedrock gate's `gold_dropped_head` 2 -> 2 was the clean reading of
this mechanism; here the "drop" is one degraded generation, not the budget.

### 3.4 `resp_speed` — CONFOUNDED, do not read as a lever result.

−1.96 with p<0.0001 is the largest flip count in the board (6/31) and it is not
attributable: the two arms did not have the same transport health. Arm B logged
**17** `wrapper_degenerate_completion` events (5 in A) and **8**
`bedrock_auto_fallback` attempts (2 in A), i.e. B's draw spent more of its
latency budget on retries. A retry-heavy arm is slower for reasons the prompt
cannot be blamed for. Reporting it as a lever cost would be exactly the error
the leg-awareness work (R431/R460) exists to prevent.

## 4. Verdict and what is deliberately NOT done

* `REGENOLD_CONCISE_CALIBRATION` stays **default OFF**; `calibration_enabled()`
  is unchanged (allow-list).
* `promote_conciseness_calibration.py` is written but **NOT applied**. It exists
  so the successor lever does not have to re-derive the patch, and it carries the
  evidence summary in its comment block.
* Nothing in `CONCISENESS-PROGRAM.md`'s acceptance targets is claimed as met.

## 5. What the evidence says to build next

The gate separates the block into two halves that behaved differently, and the
separation is the useful finding:

1. **The citation budget** (a counted "at most N provisions") — works on both
   transports at ~+5 pp `ref_conciseness`, costs nothing on the other axes, and
   is the one part of the lever that survived a transport + model change.
2. **The length battery** (sentence count, word ceiling, shape skeleton) —
   helped on `opus-4-6`, hurt on `opus-5-5` on the very axis it targets.

The obvious next gate is therefore the count-only variant: same block with the
length clauses removed, promoted only if it reproduces `ref_conciseness` without
touching `ans_conciseness` on the shipped transport. That is a smaller, cheaper
arm than the one this document reports.

## 6. Artifacts

| artifact | what it is |
| :-- | :-- |
| `run_gate_wrapper.sh` | launcher (both arms, `--repeats` arg, resumable) |
| `wrapper_tunnel_probe.py` | one-call tunnel + model liveness probe |
| `score_gate_wrapper.sh` | Bedrock judging + `paired_ab` decision |
| `WRAPPER-GATE-RUN.log` | arm timings and exit codes |
| `score-gate-wrapper.log` | judge identity, per-row checkpoints, paired table |
| `evals/bench/results/official-r460-tunnel-{off,on}-s3-hard.ckpt.jsonl` | raw draws |
| `docs/measurements/r388/score-r460-tunnel-{off,on}-s3-hard.json` | scored payloads (raw + `length_controlled`) |
| `paired-r460-conc-wrapper.json` | paired axes, CIs, McNemar, gold-head veto |
| `wrapper_gate_subset.py` | same-leg subset recomputation (asserted against the scored axis) |
| `wrapper_gate_leg_split.py` | per-leg / per-arm answer aggregates |
| `promote_conciseness_calibration.py` | prepared promotion patch, **NOT APPLIED** |
