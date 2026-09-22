# R440 — branch-aware generation guard gate

**Status:** **VOID — no score.** The first launch was interrupted and the restart path
was accidentally duplicated by stale local Python processes; six concurrent runners
were found writing the same label/checkpoints and were stopped. No R440 delta is
publishable. The checkpoints must be discarded and a fresh owner-controlled launch
must use a single-process lock before any new draw.

## Scope

Frozen official hard rows: 21 rows covering Article 50 (5), biometric (5), and
medical-device/Annex I (11). Arms are `REGENOLD_GROUNDED_BRANCH_GUARDS=0` and
`=1`; hard mode uses the fixed pre-pinned 9-turn preamble; three independent
generations per row per arm are required.

## Validity rules

The gate is invalid if a checkpoint is incomplete, generations replay, a graded
row is fallback/degraded, or the request/system slots are identical when the
lever is supposed to alter the user payload. The ON arm may ship only if no row
loses answer-correctness criteria or gold heads, Ref. Loose does not fall, and
Answer/Reference Conciseness, tone, speed, and geometric mean are reported.

## Launch

```text
label: r440-branch-cluster
ids: rg_002, rg_004, rg_007, rg_008, rg_026, rg_055, rg_058, rg_070, rg_073,
     rg_074, rg_075, rg_080, rg_081, rg_083, rg_088, rg_092, rg_101, rg_103,
     rg_106, rg_108, rg_109
repeats: 3 per row per arm
preamble: fixed
log: /tmp/r440_gate.log
```

Stage-2 preflight passed on the configured Claude model. The local Cohere embed
quota returned 429 and the engine correctly fell back to its SVD retrieval path;
this is not a void condition for the branch-guard lever, but the gate records it
and will not claim a Cohere-specific result.

## Invalidated launch

The launch produced partial files, then the desktop restart/retry left six matching
`run_official_batch --label r440-branch-cluster` processes alive, including both
`.venv` and system Python copies. They were stopped before further scoring. This is
the same process-isolation failure documented in R436/R437. The partial checkpoints
are evidence of a harness failure only; they must not be resumed or scored. Before
the next launch, add an owner PID/lock check or run against the deployed HTTP
endpoint, and delete the partial R440 files so no stale rows can be mixed in.
