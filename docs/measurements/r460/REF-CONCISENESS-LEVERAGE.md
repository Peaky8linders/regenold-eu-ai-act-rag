# R460 — Ref Conciseness: priced, screened, and locked behind the key

The Cohere re-baseline re-ranked the eight axis gaps. This round prices the
largest one — **Ref Conciseness**, the lowest axis on both boards and the
highest-leverage axis in the geometric mean — and screens every key-blind rule
that could capture it. Verdict: **+5.8 pp of headroom exists, +0.9 is reachable,
and every rule that removes more refs than that pays for it on the correctness
axes.** Two premises elsewhere in this round's docs are also corrected (hard-mode
Speed, and the pacing/trial-key blocker).

Scripts (offline, read-only, reproduce the scored boards exactly):

    ../../.venv/Scripts/python.exe docs/measurements/r460/ref_conc_leverage.py   # ceiling + cap policies
    ../../.venv/Scripts/python.exe docs/measurements/r460/ref_prune_screen.py    # key-blind rules + 2x2

## 1. Why this axis, on the NEW board

Geometric-mean elasticity `overall / (8 * axis)` — the overall points bought by
one point of the axis:

| axis | hard | elasticity | easy | elasticity |
| :-- | --: | --: | --: | --: |
| ans_correctness_loose | 94.07 | 0.114 | 97.78 | 0.112 |
| ans_correctness_strict | 89.19 | 0.120 | 94.59 | 0.115 |
| ans_conciseness | 81.54 | 0.132 | 81.30 | 0.134 |
| ref_correctness_loose | 98.57 | 0.109 | 98.57 | 0.111 |
| ref_correctness_strict | 84.76 | 0.127 | 84.76 | 0.129 |
| **ref_conciseness** | **59.14** | **0.181** | **61.10** | **0.179** |
| regulatory_tone | 100.00 | 0.107 | 100.00 | 0.109 |
| resp_speed | 86.66 | 0.124 | 88.34 | 0.124 |
| **overall** | **85.77** | | **87.36** | |

Ref Conciseness is 40 pp below every other axis and carries 1.4-1.7x the
elasticity of any of them. Its frontier value is also the frontier's weakest
number (58.5 hard / 51.9 easy), so it is the one axis on which a real gain opens
a gap rather than closing one.

## 2. What the axis actually measures — and why pruning is free

`rubric.reference_conciseness = min(1, |expected| / |provided|)`: a **pure count
ratio**, one-sided (fewer than the key scores 1.0, so citing too little is never
punished here). Nothing about which refs.

The two correctness axes are per-question **recall** at head grain (`loose`) and
full grain (`strict`, credited when a provided ref equals or refines an expected
one). So a pruner that keeps every key-relevant ref cannot move them.

**The answer axes cannot move either.** `judge.judge_correctness_once` and the
grouped correctness+tone call both build `{provisions}` from
`row["expected_refs"]` — the KEY's provisions — and pass the candidate answer
text; the arm's own ref list is never in the prompt. In this instrument, ref-list
pruning is therefore **answer-preserving**: the only thing at risk is recall on
the two reference axes. (The official evaluator's prompt is not visible to us;
that caveat stands.)

Both scripts re-derive the scored ref axes from the checkpoints — 59.14 / 61.10 /
85.77 / 87.35 reproduce exactly (same gold key, same R388 grain deepener,
`rows_changed=1`).

## 3. The count structure: the axis is decided by 1-ref questions

Hard board, per row (`E` = key refs, `S` = supplied):

| E | S=1 | S=2 | S=3 | S=4 | S=5 |
| --: | --: | --: | --: | --: | --: |
| 1 | 6 | 10 | 6 | 4 | 1 |
| 2 | 1 | 4 | - | 1 | 1 |
| 3 | - | - | - | - | 1 |

* 27 of 35 rows have **E = 1**, and 20 of those 27 are over-supplied. Emitting
  2 refs on an E=1 row caps that row at 0.5; 3 refs caps it at 0.33.
* 24/35 rows over-supplied; **88 supplied vs 44 expected (2.00x)**; easy 85 vs 44
  (1.93x). Mean 2.51 refs/row (hard) against `_mean_expected_per_row` 1.257.
* R407's audit measured the same mechanism (2.818 emitted vs 1.270 expected,
  "systematic reference sprawl") and named the pairs the engine adds: Annex III,
  Annex I, Article 6, Article 50, Article 5, Article 49, Article 79.

## 4. Every key-blind rule, screened

`d_overall` is the geometric mean with the answer, tone and speed axes frozen at
their scored values, so every delta is attributable to the ref list.

| rule | hard ref_l / ref_s / ref_c | hard | easy | note |
| :-- | :-- | --: | --: | :-- |
| shipped | 98.57 / 84.76 / 59.14 | 85.77 | 87.35 | |
| **mention** (keep refs the answer prose names) | 98.57 / 84.76 / 62.24 | **+0.55** | **+0.54** | zero cost on both correctness axes |
| dedupe head (one ref per article/annex) | 98.57 / 84.76 / 59.14 | +0.00 | +0.19 | barely fires |
| drop redundant parent (a ref its own child refines) | 98.57 / 84.76 / 59.14 | +0.00 | +0.00 | **no row carries such a pair** |
| cap@2 (first two, engine order) | 88.57 / 82.38 / 72.86 | +0.36 | −0.11 | buys conciseness with strict recall |
| cap@3 | 95.71 / 83.33 / 62.86 | +0.16 | +0.24 | |
| cap@1 | 70.00 / 64.29 / 100.00 | −1.00 | −1.83 | the key ref is lost on ~30% of rows |
| mention + cap@2 | 88.57 / 82.38 / 72.86 | +0.79 | −0.11 | |
| *CEIL* min preserving subsequence | 91.43 / 84.76 / 100.00 | +4.96 | +4.68 | needs the key |
| *CEIL* oracle match filter | 84.29 / 77.62 / 100.00 | +3.06 | +2.75 | needs the key |
| *CEIL* rc = 100 at shipped ref_l / ref_s | 98.57 / 84.76 / 100.00 | **+5.82** | **+5.55** | perfect necessity model, ~1.26 refs/row |

Why the mention rule is weak (hard): among supplied refs,

| key-relevant? | mentioned in answer? | share |
| :-- | :-- | --: |
| yes | yes | 29.5% |
| yes | no | 3.4% |
| **no** | **yes** | **63.6%** |
| no | no | 3.4% |

The engine's prose names what it cites, so "mentioned" has almost no
discriminating power — which is exactly what `graph_rag_prompts.py:72` already
says: *"Any pruner downstream of the prose is either a no-op (the refs are
described) or drops gold. The only place the ref count is decided is the
generator."*

## 5. Verdict

1. **The headroom is real and large**: +5.82 (hard) / +5.55 (easy) if a policy
   knew which of the ~1.3 extra refs per row are not in the key. No other open
   lever in this round is worth that much.
2. **No key-blind rule captures more than +0.9**, and every rule that removes
   more than the prose mentions pays for it on Ref Strict: the axis is a
   count ratio against a 1.26-ref key, our engine answers more of the question
   than the reference answer does, and the trade is monotone in the wrong
   direction past ~0.08 refs/row.
3. **The `mention` prune is the one safe candidate** (+0.55/+0.54, both
   correctness axes bit-identical). It is *below the n=37 detection floor*
   (~1.5 rows), so it can only be promoted by shipping it as a default with a
   regression gate, not by a promotion gate. Recorded as a candidate, not run.
4. **`ANALYSIS-AND-PLAN` item 10's framing needs a caveat**: the audit's "Ref
   Conciseness +1.34 pp if closed" is a real ceiling but not a reachable one;
   what is reachable is a third of one point. The generator-side levers
   (`REGENOLD_REF_MINIMALITY` rule 16 in the system stack, default OFF;
   `REGENOLD_USER_REF_MINIMALITY` V2 clause in the delivered user channel,
   default ON) are already the only place the count is decided, and the V2 clause
   already names the Article 49/47/48 and classification-apparatus pairs the
   audit blamed. Nothing is left to switch on.
5. **What would change the verdict**: a per-ref necessity signal that is not
   prose presence — i.e. "would removing this ref change the answer?" asked per
   ref (the RESERVE question, per ref), or a generator contract that trades
   coverage for minimality, which R367 already settled against.

## 6. Two corrections to this round's own docs

**(a) Hard-mode Speed is the graded PUSHBACK turn, not the whole exchange.**
`score_arm._graded_latency_ms` scores `pushback_latency_ms` whenever turn 1
produced an answer (R409: the official axis is per response; scoring turn1+pushback
would read ~2x the easy latency). So on the hard board, turn-1 latency is
**unscored**, and the 86.66 vs 86.70 gap is a pushback-turn number. Mean graded
latency 13.3 s.

**(b) The pacer's sleep is netted out of the measured latency — a paced run keeps
a clean Speed axis.** `run_official_batch._net_of_pacing` subtracts the rerank
pacer's sleep (process-wide counter, requests posted sequentially) from every
measured latency; R407 scored Resp. Speed on 13 s of pacing before R409 fixed it.
So the R450 `density` gate is **not** blocked by the trial key's 10 rerank
calls/min: run the arm paced (e.g. `--min-rerank-gap 7`, with
`--require-cohere-rerank`, which tolerates budget skips) and the Speed axis stays
clean. What actually blocks that gate is **power**: R450's offline instrument
measured `density` at +3/82 rows coverage (rescuing rg_033, rg_069, rg_088, zero
regressions, same emitted characters), which at `--stride 3`/n=37 is ~1 row — below
the house detection floor. The lever should be judged on its own n=82 instrument
and shipped as a default behind a regression gate, or measured at n=110 with
`--repeats 3`, not promoted from a 37-row board.

## 7. Proposed re-order of the plan

1. **`density`**: stop treating it as a promotion gate at n=37 (measured
   underpowered); either run it at n=110 with `--repeats 3` or ship as a default
   with a regression gate. Now that pacing is netted out, the trial key is no
   longer the blocker.
2. **Ref Conciseness**: closed as a key-blind transform (this doc). Reopen only
   with a per-ref necessity signal.
3. **Tier-2 item 12 (Sonnet strict-flip guards)** and **item 9 (turn profile)**:
   both now cheaper than they looked — item 9's premise (speed "the largest
   scored deficit, 82.8 vs 86.7") is stale: the live hard board is 86.66 vs 86.70,
   a 0.04 tie, and easy is +6.5 ahead of the frontier.
4. **RESERVE** stays the only lever with a measured +1 to +2 pp, and it still
   needs the operator ruling (it contradicts "always Stage-2" and drops gold
   heads on two pools).

## 8. Caveats

* n=37 (`--stride 3`), one generation per row, one board per arm; the ref axes are
  deterministic given the answered rows, so the ref screen itself is exact — the
  *inference* to other rows is what n=37 limits.
* The instrument's key is the R388 grain-calibrated reconstruction, not the
  evaluator's; the appendix cases reproduce the printed axis within 1.4 pp.
* Frozen-axis arithmetic: `overall` deltas are scenario arithmetic holding the
  answer/tone/speed axes at their scored values. They are exact for ref-only
  changes (which is what a pruner is), not a re-score.
* The `mention` rule was not implemented. Nothing in this round changed a default.
