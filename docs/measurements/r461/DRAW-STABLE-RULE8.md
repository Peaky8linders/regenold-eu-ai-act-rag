# DRAW-STABLE RULE #8 — the drop has to be a fact, not a draw (R461.3)

2026-10-02. Branch `feat/r461-count-only-concise`. Instrument: `evals/official/paired_ab.py`.
Harness: `evals/regenold/run_official_batch.py`. Tests: `tests/test_r461_3_draw_stable_rule8.py` (29).

## 1. The finding this answers

Hard rule #8 vetoes a lever that drops a gold HEAD on a row it actually served.
R461.1 (committed) fixed WHICH ROWS testify: a drop on a row the lever never
served is a transport event, not a lever verdict. This round fixes the other
half of the same mistake, and it is the half the R461 gate itself measured:

    at n=37, a SECOND draw of an UNCHANGED OFF arm drops gold heads the first
    draw did not (COUNT-ONLY-CONFIRM.md §5).

So "arm B lacks a head arm A held" is not yet a loss. It is a claim about ONE
sample of the baseline, and the baseline's own head-set moves draw to draw. A
rule that reads it as a fact vetoes null pairs — which is exactly what the
R461 noise floor pair did.

## 2. The rule

```
a gold head arm B lacks vetoes only if an INDEPENDENT re-draw of arm A
carries that head too
```

`--redraw` names that re-draw. The reference has to hold the head
REPRODUCIBLY before its absence can be called a loss.

* **Nothing leaves the record.** A drop the re-draw clears is reported in
  `draw_stability.drops_unstable` with the head and the reason ("the re-draw
  does not carry the head either: draw noise, not a loss"), and
  `gold_dropped_head` keeps its all-rows counts. A cleared drop is priced, not
  deleted.
* **The re-draw is verified, not trusted.** Per row, `hard_preamble_digest` must
  match arm A's. Different request bytes are a different arm. The digest is read
  from each arm's own **checkpoint** — `score_arm` payloads carry `refs`,
  `answer`, `criteria` and the judged axes and nothing about the request shape.
  (The first cut asked the score rows; every row would have failed closed and
  the re-draw could never clear anything. `tests/test_r461_3_draw_stable_rule8.py`
  caught it — a failure that hides inside fail-closed behaviour, because the
  gate still reads.)
* **Fail closed, and say why.** No re-draw (the single-draw reading stands —
  the STRICTER one, so the fallback can never lift a veto), a row missing from
  the re-draw, a row with no digest on one side, a row whose digest disagrees:
  all keep their drops in scope and are named in `draw_stability.unverified`.
  Stabilisation can only ever CLEAR a drop, never add one (test).

## 3. The noise floor is the same flag

Arm A against its own re-draw is **two independent draws of ONE configuration** —
the paired OFF/OFF control. That is the null every lever delta is read against,
and it is the same pair rule #8 needs, so one `--redraw` does both jobs:

* `noise_floor.axes[axis].floor_delta` sits beside every `lever_delta`, with
  `beyond_floor` and `ci_excludes_floor`;
* `--control` declares a read to BE the control pair instead of a lever read;
* `config_identity` is checked on the draws themselves (per-row
  `hard_preamble_digest`), and it is **tri-state**: `True` verified one
  configuration, `False` verified different bytes, `None` genuinely unknown
  (unreadable checkpoint, no shared row, or a row with no digest on one side).
  Conflating `False` with `None` was a defect the tests caught: a wrong floor
  was being refused for the wrong reason;
* a floor is **refused, not quoted**, when the pair is not one configuration or
  when the control still drops gold heads after stabilisation.

### The harness draws the control itself

`evals/regenold/run_official_batch.py` now draws the control arm automatically
for any gate (`--baseline-env`/`--branch-env`): the BASELINE env, suffix `-C`,
an independent draw under the same protocol, repeats and resume contract, and
`payload["control"]` records that it happened. `--no-control` is the only way
to skip it, and the payload then records the refusal. A floor assembled by hand
after the fact is one nobody can check.

## 4. What it does to the R461 gate (re-read, real data)

Read at
`docs/measurements/r461/paired-r461-count-only-wrapper-drawstable.json`
(`--redraw score-r460-tunnel-off-s3-hard.json`, the historical OFF draw at the
byte-identical request digest):

* **rule #8: CLEAN**, scope `lever`, 27/35 gold rows evaluated — the verdict
  R461.1 reached, now reached draw-stable.
* the gate's ONE raw drop (`rg_037`, head `Annex VIII`, arm B `deterministic`)
  **persisted** in the re-draw: 0 of 1 heads cleared. So that drop is a FACT
  about the baseline, and it is still out of scope because the lever never
  served the row — two different reasons not to veto it, both reported.
* **floor identity: all 37 shared rows served identical request bytes**, floor
  usable, its own rule-#8 read CLEAN.

| axis | lever (ON−OFF) | OFF/OFF floor | beyond the floor |
|---|---|---|---|
| ans_correctness_loose | +0.00 | +0.90 | no |
| ans_correctness_strict | +0.00 | +0.00 | no |
| ans_conciseness | +0.10 | +0.37 | no |
| ref_correctness_loose | +1.43 | +4.29 | no |
| ref_correctness_strict | +1.43 | +1.43 | no |
| ref_conciseness | **+7.69** | **+1.81** | **yes (4.2×)** |
| regulatory_tone | +0.00 | +2.70 | no |
| resp_speed | −0.62 | +3.35 | no |

Two things this table settles that the bare deltas could not:

1. **four of the eight axes move more between two draws of ONE configuration
   than the lever moved them** (tone +2.70, resp_speed +3.35, ref_loose +4.29,
   ans_conciseness +0.37 against a +0.10 lever). Only `ref_conciseness` clears
   its own floor.
2. `ref_conciseness` clears it by 4.2× **but the lever's own CI
   [+1.41, +15.05] covers the floor's observed +1.81** (`ci_excludes_floor:
   false`). One draw per arm cannot separate the lever from the draw on that
   axis alone. That is the gap the replicate top-up was for.

## 5. Blocked: the replicate top-up, and the production canary

Both live paths need provider draws, and the Claude Code wrapper's OAuth token
is dead — locally AND in production:

* local: `run_official_batch` aborted the top-up 2 rows into sample 2 —
  `Stage-2 PRIMARY transport is down: 5 consecutive primary calls failed
  ... "No response from Claude Code" ... aborted`. That is the R423 guard
  working: it refuses to grade deterministic Stage-1 drafts. The contaminated
  partial `official-r461-countoff-s3-hard.r1.ckpt.jsonl` was **deleted**, not
  resumed into.
* production: `/healthz/llm` reports `llm_ok: true` **through the fallback** —
  `primary offline (api_status_500: "No response from Claude Code"); bedrock
  fallback active`, deployment `265adb3e…`, commit `ca71879d7059`. A POST
  canary now would measure the Bedrock fallback, not the leg the gate measured,
  so it is **not** run: the canary's job is to confirm the shipped transport,
  and the shipped transport is not the one answering.

**Therefore, as of this commit, the R461 gate still has ONE draw per arm and no
replicate-stable verdict.** What IS established: the rule, the floor machinery,
the harness control, 29 tests, and the one-draw re-read above — whose
`ref_conciseness` result is 4.2× the measured floor but, on one draw, not
separable from it.

## 6. Files

| file | what |
|---|---|
| `evals/official/paired_ab.py` | draw-stable rule #8, `--redraw`/`--redraw-ckpt`, `noise_floor()`, `attach_noise_floor()`, `--control`, tri-state identity |
| `evals/regenold/run_official_batch.py` | the automatic control arm (`-C`, baseline env) + `--no-control` |
| `tests/test_r461_3_draw_stable_rule8.py` | 29 tests: the rule, the verification, the floor, the CLI, the harness |
| `docs/measurements/r461/apply_draw_stable.py` | applier, 18 edits, idempotent |
| `…/apply_draw_stable_digest_source.py` | applier, 11 edits — the digest comes from the checkpoint |
| `…/apply_draw_stable_identity_tristate.py` | applier, 2 edits — tri-state identity + the floor priced off the right pair |
| `…/apply_gate_control.py` | applier, 2 edits — the harness draws the control |
| `docs/measurements/r461/paired-r461-count-only-wrapper-drawstable.json` | the one-draw re-read above |

Appliers are idempotent **within their own change**; re-running an earlier one
after a later one has touched the same region is a hard error by design
(it reports the missing anchor, it does not duplicate an edit).

R461.5 note: the row-provenance reading this instrument was built on now lives
in `evals/bench/row_provenance.py` (see `PROVENANCE-UNIFICATION.md`). Re-running
the one-draw read under that change reproduced every number and verdict; the
artifact above was regenerated only to pick up the R461.4 digest-is-shape
wording, which post-dated its first write.

## 7. Resume protocol

1. re-seed the wrapper token (`login.bat`), verify with the `curl` the abort
   message prints;
2. `REGENOLD_CONCISE_COUNT_ONLY=0 $PY -m evals.regenold.run_official_batch
   --label r461-countoff-s3 --mode hard --stride 3 --require-cohere-rerank
   --cohere-rerank-min-gap 7 --repeats 3 --resume` (then the same for
   `r461-counton-s3` with `=1`): samples 2 and 3 only, one replicate at a time,
   `--resume` per sample;
3. score each new sample (`score_arm`, Bedrock judge, `--length-control`, the
   R461 judge cache), then re-read every replicate:
   `paired_ab --a <OFF rk> --b <ON rk> --redraw <OFF rj>` for k=1..3, plus
   `--control` on the OFF/OFF pair. The OFF replicates are themselves the fresh
   paired control (3 draws of one configuration = 3 OFF/OFF pairs), so the
   floor needs no extra run;
4. report the replicate-stable verdict, not the best replicate;
5. after a green deploy, `docs/measurements/r461/production_canary.py
   --phase post --expect-commit <merge sha>` and `--phase compare`.
