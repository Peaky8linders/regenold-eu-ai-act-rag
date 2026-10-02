# R461.6 — the captured roster: a published verdict stays re-auditable

## 1. The defect this closes

The R461.4 audit found that the per-row provenance a scope decision reads lives
in `evals/bench/results/` — **gitignored**. When that checkpoint is gone,
"was this refusal decided by a row the lever never served?" is unanswerable
forever; r403's three VETOs (`rg_067`, `rg_090`) are the measured cost, and
r442's two plus half of r447's cannot be checked either. The audit's own
proposal: embed the captured roster in the veto block.

## 2. What a read now carries

`compare()` embeds `veto.roster`:

* `arm_a` / `arm_b`: `captured` (was the checkpoint readable), `source` (the
  file it was read from, or why it could not be), and `reasons` — the row-id to
  eligibility-reason map the scope was decided on, in the same vocabulary the
  report prints;
* `considered`: the row set the scope was actually evaluated over, which no
  roster lookup can reconstruct.

## 3. How the audit uses it

Per arm, in order: the live checkpoint (recorded path, then a same-basename
copy in the records) → the read's CAPTURED roster → nothing (UNVERIFIABLE, as
before). A live file always wins; the capture is evidence, not authority — the
audit re-applies the CURRENT eligibility rule to the CAPTURED rows, which is
exactly what re-auditable means: the rule may change, the evidence may not.

## 4. Evidence

* 6 tests in `tests/test_r461_6_captured_roster.py`, including the end-to-end
  case: a real `compare()` payload published with the legacy refusal, its
  checkpoints **deleted**, re-audited — same classification, same eligible row
  count, same moved row as the file-backed read, with the provenance line
  naming the capture. The live-file precedence is pinned in both directions.
* The audit record re-runs **byte-identical** for the 16 published reads
  (`gate-verdict-audit.json`, md5 `091103ee`): old reads carry no roster and
  their checkpoints are gone, so the eight unauditable verdicts remain
  unauditable. The capture is prospective; claiming otherwise would be the same
  class of mistake the audit exists to find.
* The canonical R461 one-draw read was regenerated with the capture attached:
  the ONLY structural change is the added `veto.roster` block (37 rows per
  arm) — every number, verdict and price is otherwise equal.
* 142 tests pass across the R461 / R422 / R423 suites; the R461.5 unification
  scan still passes (the raw fields remain read only in the shared module).

## 5. Files

| file | what |
|---|---|
| `evals/official/paired_ab.py` | `veto.roster` capture; `a_roster`/`b_roster` fallback in `compare()` |
| `docs/measurements/r461/audit_published_gates.py` | captured-roster fallback in provenance resolution |
| `tests/test_r461_6_captured_roster.py` | 6 tests: publication, fallback, live-file precedence, old reads unchanged |
| `docs/measurements/r461/apply_captured_roster.py` | applier, 9 edits, idempotent |
