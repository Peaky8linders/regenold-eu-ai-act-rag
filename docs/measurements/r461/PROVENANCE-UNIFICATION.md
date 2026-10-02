# R461.5 — one row-provenance predicate for every gate

## 1. The defect

Every gate decided what a checkpoint row's provenance means in code of its own,
over the same two fields (`provenance.stage2_served_by`,
`provenance.stage2_polish`):

| reader | the question it asked | the code that answered it |
|---|---|---|
| `evals/official/paired_ab.py` | is this row evidence about the LEVER (rule #8)? | `_row_scope_reason`, `_lever_ran` |
| `evals/harness/gate_validity.py` | did an arm ship Stage-1 drafts (R422)? which rows were not primary-served (R423)? what does a RESUMED arm's census say? | `count_deterministic_rows`, `degraded_row_ids`, `count_rows_served_by` |
| `evals/regenold/run_official_batch.py` | pool the exclusion over every generation of an arm | its own import of the R423 helper |

Read three ways, one row could narrow a veto on one gate and widen an exclusion
on another without either gate saying so. The audit that motivated this
(`GATE-VERDICT-AUDIT.md`) had to re-derive scope row by row to answer questions
the published payloads did not, which is exactly the cost of a duplicated
reading.

The readings are NOT all the same question, and keeping that honest is the
point — the shared module resolves the ROW once and exposes each gate's verdict
over that resolution:

| row's provenance | rule #8 `lever_ran` | R423 `transport_degraded` | R422 `deterministic_draft` | resume census |
|---|---|---|---|---|
| `primary` (or pre-field `polish=True`) | **yes** | no | no | `primary` |
| `fallback` | **YES** | **YES** | no | `fallback` |
| `deterministic` | no | yes | **yes** | `deterministic` |
| `prior_turn` | no | yes | no | `prior_turn` |
| a leg name the vocabulary does not know | **YES** | **YES** | no | the name |
| flag `False`, no leg name (curated/intercepted) | no | **no** | **YES** | `deterministic` |
| no leg, no flag / no provenance at all | no (UNDECIDED) | no | no | `unnamed` |

Three deliberate asymmetries, each pinned by a test:

1. **`fallback` is lever evidence AND a degraded transport.** The fallback
   receives the SAME request payload, so a payload-level lever ran there (rule
   #8 must not exempt it), and the draw did not come from the intended path
   (R423 must exclude it). Opposite directions, both correct.
2. **A curated intercept is a draft for R422 and NOT a degradation for R423.**
   The pre-R417 flag cannot tell "curated answer" from "Stage-1 draft"; the void
   guard counts it (conservative), while an exclusion list that dropped it would
   remove nine stable, byte-identical rows from every pair.
3. **A foreign leg name is a serve for rule #8 and non-primary for R423.** A new
   engine label must neither silently exempt a row a leg served, nor be trusted
   as the intended path.

## 2. The shared module

`evals/bench/row_provenance.py` (leaf: imports nothing from `evals`):

* `classify(prov) -> RowProvenance` — the ONE resolution. `kind` is the
  canonical reading (`primary` / `fallback` / `deterministic` / `prior_turn` /
  `unpolished` / `unrecognised` / `unknown` / `no_provenance`), `leg` the
  verbatim name, `polished` the strict tri-state of the legacy flag.
* predicates over it: `lever_ran` (rule #8), `transport_degraded` (R423),
  `deterministic_draft` (R422), `unreadable`, `closed`.
* projections: `scope_reason` (the report vocabulary, foreign name printed as
  `primary`), `lever_ran_reason` (reason-string form, foreign strings stay
  eligible), `served_leg` (census label).
* the row-list rules themselves: `count_rows_served_by`,
  `count_deterministic_rows`, `degraded_row_ids`.

## 3. The routing

The gates keep their public names; the names ARE the shared functions, so
there is no second implementation to drift (asserted by `is` identity in the
tests):

| public name | now |
|---|---|
| `paired_ab._row_scope_reason` | `row_provenance.scope_reason` |
| `paired_ab._lever_ran` | `row_provenance.lever_ran_reason` |
| `paired_ab.LEVER_RAN_LEGS` / `DEGRADED_LEGS` / `SCOPE_REASONS` | re-exported from the leaf |
| `gate_validity.count_rows_served_by` / `count_deterministic_rows` / `degraded_row_ids` | `row_provenance.*` |
| `run_official_batch.degraded_row_ids` | imported from `evals.bench.row_provenance` |

## 4. The scan

`tests/test_r461_5_provenance_unification.py` walks every `evals/**/*.py` with
`ast` and fails on any code that reads the raw fields — by string key
(`.get("stage2_served_by")`, subscripts) or through the leaf's `FIELD_*`
constants. The allowlist is by module + function, with the reason it is not a
gate rule:

| module | allowed readers | why |
|---|---|---|
| `evals/bench/row_provenance.py` | all | THE reader |
| `evals/harness/prompt_ab.py` | `main` | asserts the Bedrock CAPTURE arm landed, on a live response |
| `evals/regenold/run_official_batch.py` | `_provenance`, `observe`, `_aggregate` | writes the fields, watches the live leg, reports the landed rate |
| `evals/regenold/{antifragile_live,diff_hard_sample,run_medtech_subpoint_eval}.py` | one extractor/report function each | report-side consumers of a finished run |

The allowlist is itself tested for staleness: a renamed function that no longer
reads the fields fails the suite.

## 5. Behaviour preservation

* **Oracle equality, every shape.** The pre-move readers are carried verbatim
  in the test file; every helper is asserted equal for every provenance shape a
  checkpoint can carry (leg names, legacy flag, malformed values, missing
  provenance) and for every reason string in and out of the vocabulary.
* **Oracle equality, every row on disk.** All 16 checkpoints in
  `evals/bench/results/` (378 rows) read exactly as before the move: scope
  reason, R422 count, R423 exclusion list and the census are equal row by row.
* **End to end, the two published instruments.** Re-running
  `audit_published_gates.py --declared-redraw "READ=SCORE"` reproduces
  `gate-verdict-audit.json` byte for byte (md5 `091103ee…`), and re-running the
  draw-stable one-draw read reproduces every number and verdict in
  `paired-r461-count-only-wrapper-drawstable.json`. The only byte difference
  there was the R461.4 digest-is-shape wording, which post-dates the artifact's
  first write; the artifact was regenerated so the record quotes the fixed
  instrument (`ref_conciseness` +7.69 against a +1.81 floor, CLEAN 27/35).
* **Full suite.** 27 failed / 9226 passed — the same 27 environmental
  davidath-egress failures the triage identified, zero new.

## 6. The one deliberate divergence

A present-but-falsy leg value (`stage2_served_by = 0` or `False`) used to be
skipped by the R423 exclusion (`if served` is falsy) while rule #8 read the same
value as a named non-primary leg. The shared resolution reads any present value
as a leg name, so R423 now EXCLUDES such a row instead of grading it — the
conservative direction. Rule #8's reading is unchanged, and no checkpoint on
disk carries one (pinned by the on-disk oracle test). This is the only input
class where any behaviour changed.

## 7. Files

| file | what |
|---|---|
| `evals/bench/row_provenance.py` | the shared vocabulary, resolution and predicates |
| `evals/official/paired_ab.py` | rule #8 routed through the leaf; public names kept |
| `evals/harness/gate_validity.py` | census / R422 / R423 routed through the leaf |
| `evals/regenold/run_official_batch.py` | the exclusion list imported from the leaf |
| `tests/test_r461_5_provenance_unification.py` | 11 tests: vocabulary, asymmetry, identity, oracle on shapes and on 378 real rows, the AST scan |
| `docs/measurements/r461/apply_provenance_unification.py` | applier, 10 edits, idempotent |
