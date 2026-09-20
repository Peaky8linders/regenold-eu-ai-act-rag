# R423.3 — the hard-mode prompt scope was mis-stated, and `--resume` changed a row's modality

R423.2 shipped `REGENOLD_NEED_PROPORTIONAL_CONTRACT` default ON off a valid paired
gate. Its report carried a scope note saying both arms "dispatched the stripped
persona". **That claim was false**, and correcting it surfaced a real harness defect.
Nothing about the lever changed; the flag stays ON.

## 1. The falsified claim

The note inferred the dispatched system prompt from the modality's name. The
predicate in `_graph_rag_impl` is a property of the REQUEST:

```python
if history_turn_count is not None and history_turn_count <= 1 and _single_turn_full_system:
    _full_system = True
```

`history_turn_count` is "turns BEFORE the live question", so it reads 0 for a first
ask — and `run_official_batch._run_hard` keeps a **rolling conversation that starts
empty**. Its first two rows therefore read 0 and 1 and receive the full ~59.6 kB
system prompt; only from row 3 on does a hard run read >= 2.

### Decisive evidence — the same row, only its position changed

`docs/measurements/r423/graded_scope_probe.py` drives real hard rows through the real
route and records (row, turn, user chars, system chars) per dispatch, at the provider
seam.

| invocation | row | turn | history msgs | `history_turn_count<=1` | dispatched system |
| :-- | :-- | :-- | --: | :-- | --: |
| `--ids rg_004` | `rg_004` | t1 | 0 | **True** | **59 644 (FULL)** |
| `--ids rg_004` | `rg_004` | pb | 0 | True | 61 (persona) |
| `--ids rg_001,rg_004` | `rg_004` | t1 | 2 | **False** | **61 (persona)** |
| `--ids rg_001,rg_004` | `rg_004` | pb | 2 | False | 61 (persona) |

Same question, same harness, same flags: **position 1 → full prompt, position 2 →
persona.** The engine is correct (a request carrying 0 prior turns *is* a
single-turn ask); it was the claim about the scope that was wrong.

The 6-row sample (`rg_001, rg_004, rg_007, rg_010, rg_013, rg_016`) shows the ramp:
history 0, 2, 4, 6, 8, 8 — so only rows 1–2 can satisfy the predicate, and a row that
never reaches Stage-2 (a curated deterministic intercept) records no Stage-2
dispatch at all.

## 2. The defect it exposed: `--resume` changed a row's modality

`--resume` handed its pending rows a **brand-new empty history**, so a resumed arm's
first rows were re-graded as near-single-turn — a modality its uninterrupted
counterpart would never have had. That is a genuine difference between two arms of a
paired comparison, and the gate's own payload record shows it:

| leg | calls | distribution |
| :-- | --: | :-- |
| `A:primary` (resumed) | 21 | `61 × 17 · 6365 × 3 · 59644 × 1` |
| `A:fallback` | 5 | `59644 × 5` (Bedrock always receives the full `system`, R360) |
| `B:primary` (continuous) | 293 | `61 × 168 · 132 × 5 · 1311 × 3 · 6365 × 117` |

Arm A made exactly one full-prompt primary Stage-2 dispatch that arm B did not.

**Fix (general, not a patch for this run):**
`run_official_batch.seed_history_from_records` rebuilds the rolling conversation from
the rows already on disk, so a resumed hard run sends the same history an
uninterrupted one would. Only rows the runner actually rolled forward are seeded
(`_run_hard` guards the roll-forward with `if ans1`). A **fresh** run still starts
empty — that is the shipped baseline every board on record was measured with, and
seeding it would silently rebase them. Pinned in
`tests/test_r423_3_resume_modality.py` (8 tests, including the fresh-run invariance
and the exact wiring that only hard mode receives a seed).

## 3. The bound: could that one call have manufactured the +13.93 pp?

No, and it is bounded rather than argued.
`docs/measurements/r423/need_scope_sensitivity.py` re-scores the gate's own judged
rows on every leave-one-out subset of the 27 comparable rows:

```
as run                overall A=65.62  B=79.56  delta=+13.93 pp
worst single removal (drop rg_082)                delta=+13.42 pp
best  single removal (drop rg_061)                delta=+14.50 pp
```

Every single-row removal stays in **[+13.42, +14.50] pp**. No single row — degraded,
resumed or full-prompt — carries the win.

## 4. What was corrected

* `docs/reports/r423-need-proportional-gate.md` — scope section rewritten from the
  measured distribution; names the artifact, the position pair, and the bound. It
  also stopped quoting the **previous** gate's numbers as if they were this one's
  (`+45.91 pp` / `−7.41 pp` were the pre-fix gate's; this gate's are
  `+38.86 pp` / `+0.00 pp`), and both figures are now read off the artifact.
* `CLAUDE.md` — the R423 scope row carried the blanket claim and a stale
  `59644 × 1` distribution; replaced with the measured ramp and the fixed defect.
* `app/engines/_graph_rag_impl.py` — the R412 comment asserted "both hard-mode asks
  read >= 9". Qualified: that holds when the CALLER passes a 9-turn conversation,
  and any claim that a given benchmark run never sees the predicate must be measured
  on the dispatches.

## 5. Known deviation left on the record (NOT fixed)

A fresh hard run's first two rows are genuinely single-turn requests, while the
official hard modality is a pre-fixed 9-turn conversation with the question in turn
10. The rolling-history design is deliberate (`HARD_CONTEXT_EXCHANGES = 4`, R293),
and every board on record was measured with it, so changing it now would rebase them.
Recorded as a fidelity gap with its magnitude (2 rows of 37 in this gate's sample),
not silently averaged over.

## 6. Validation

* `docs/measurements/r423/graded_scope_probe.py` — the table in §1, run live.
* `docs/measurements/r423/need_scope_sensitivity.py` — the bound in §3.
* `tests/test_r423_3_resume_modality.py` — 8 tests: seed construction, the
  empty-answer skip, trimming to the context window, fresh-run invariance, the
  resumed-row history equality, and the wiring.
* `tests/test_r423_gate_report.py` — the corrected scope must render, must not
  blanket-claim the persona, must carry the artifact and the bound, and must not
  quote the pre-fix gate's numbers.
* `tests/test_r423_harness_repeats.py` — the cache-clear ordering assertion was
  rebased onto the contract (two dispatch call sites now) rather than one line's
  formatting.
