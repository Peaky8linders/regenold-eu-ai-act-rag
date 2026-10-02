# AUDIT: every published gate verdict through the fixed instrument (R461.4)

2026-10-02. Harness: `docs/measurements/r461/audit_published_gates.py`.
Record: `docs/measurements/r461/gate-verdict-audit.json`.

The question this answers, for every verdict the round records published:

    was this refusal decided by a gold-head drop on a row the lever never served?

R461.1 changed WHERE rule #8 is read (the rows arm B's own provenance says the
lever served); R461.3 changed WHAT a drop has to be (draw-stable). Both changes
can only ever CLEAR a veto, so any refusal published before them is a candidate
for having been decided by a row that cannot testify about the lever.

## 1. What was audited, and how

Every `*.json` under `docs/measurements` that carries `arm_a`/`arm_b` (the arms,
by score-payload name) and `axes` — the canonical reads written by
`evals.official.paired_ab`: **16 reads**. Each is re-read through the CURRENT
instrument three ways:

| reading | definition |
|---|---|
| `all` | the pre-R461 definition: every shared row carrying a gold key |
| `lever` | the fixed scope: rows arm B's provenance says a primary/fallback leg served |
| draw-stable | the same read against a third draw of arm A, **declared** on the command line |

Provenance is resolved exactly: the checkpoint path the score payload records, or
a copy with the SAME basename elsewhere in the records. Nothing is guessed, and a
re-draw is never inferred from a digest (see §6).

## 2. The result

| read | published | `all` | `lever` | classification |
|---|---|---|---|---|
| r403 `paired-C0-vs-C1` | gold −2 rows (`rg_067`, `rg_090`) | VETO | **downgraded** | **unverifiable** |
| r403 `paired-G0-vs-G1` | gold −1 row (`rg_090`) | VETO | **downgraded** | **unverifiable** |
| r403 `paired-L0-vs-L1` | clean | CLEAN | **downgraded** | **unverifiable** |
| r440 `…-s0` / `-s1` / `-s2` | A=0, B=0, no win | CLEAN | CLEAN | no rule-#8 refusal |
| r442 `…-opus55-opus55judge` | A=0, B=0 | CLEAN | **downgraded** | **unverifiable** |
| r442 `…-opus55-sonnet5judge` | A=0, B=0 | CLEAN | **downgraded** | **unverifiable** |
| r447 `…-keep-floor-s0/s1/s2` | NO WIN, `new_gold_head_drops: {}` | CLEAN | **downgraded** | **unverifiable** |
| r460 `paired-r460-conc-hard` | gold 2 → 2 (Bedrock gate) | CLEAN | CLEAN | no rule-#8 refusal |
| r460 `paired-r460-conc-wrapper` | gold 0 → 1 (`rg_037`) | **VETO** | **CLEAN** | **scope-decided refusal** |
| r460 `paired-r460-sonnet-vs-opus55-hard` | A=2, B=0 | CLEAN | CLEAN | no rule-#8 refusal |
| r461 `paired-r461-count-only-wrapper` | CLEAN (already scoped) | VETO | CLEAN | clean read, already scoped |
| r461 `…-drawstable` | CLEAN (already scoped) | VETO | CLEAN | clean read, already scoped |

8 unverifiable · 5 no rule-#8 refusal · 2 clean reads · 1 scope-decided refusal.

## 3. THE LIST: refusals decided by a row the lever never served

**1. R460 — the conciseness calibration block on the shipped transport
(`paired-r460-conc-wrapper.json`).** Its rule-#8 ground was one new gold head in
arm B on **`rg_037`**, and arm B's own provenance for that row is `prior_turn`:
the truncation guard kept the PREVIOUS TURN's answer, so the block under test was
never in the bytes the judge scored. Re-read under the fixed scope: **CLEAN**,
27 of 35 gold rows evaluated. The refusal still stands on its axis evidence —
`ans_conciseness` fell on opus-5-5 — but that half is not rule #8, and the
rule-#8 half is a row the lever never served. The round's own §3.3 had already
argued this by hand; the instrument now says it mechanically.

**2. R461 — the count-only block (`paired-r461-count-only-wrapper.json`).** Same
row, same direction, different transport event: `rg_037`'s arm-B provenance is
`deterministic` (both Stage-2 legs failed; the Stage-1 draft shipped). This is
the refusal that started R461.1. Re-read: **CLEAN**, 27/35. R461.3 adds the other
half: the drop **persists** in an independent OFF draw, so it is a real gold loss
on a row that cannot testify about the lever — two independent reasons not to
veto it, both now on the record.

**3. R460 — the FULL BLOCK, recomputed in R461.1.** No `paired-*.json` of its
own (it was read in `RULE8-SCOPE-REREAD.md` from checkpoints that survive), same
`rg_037` / `prior_turn`; under the fixed scope, CLEAN. Listed here because it is
the third refusal whose rule-#8 ground is a non-served row, and because it is the
one that can still be re-derived from disk.

Nothing else in the 16 reads is a rule-#8 refusal at all (§4), and the three
r403 VETOs cannot be attributed either way (§5).

## 4. Refusals NOT decided by rule #8 (unaffected by the fix)

* **r440** (branch-guard cluster, 3 samples): A=0, B=0. The published verdict is
  a *powered null* on `ans_conciseness`, decided by the axes.
* **r442** (`opus55` screens): A=0, B=0.
* **r447** (`r442-keep-floor`, 3 samples): its own `gate-verdict.json` records
  `new_gold_head_drops: {}`; the published verdict is **NO WIN** on the axes.
* **r460 Bedrock** (`paired-r460-conc-hard`): gold 2 → 2, the "clean reading";
  this gate *confirmed* the mechanism on an inverted contract, it did not refuse.
* **r461** (both reads): published CLEAN under the fixed scope already.

## 5. Refusals that CANNOT be audited (and why that is the finding)

| read | why the scope cannot be computed |
|---|---|
| r403 `C0-vs-C1`, `G0-vs-G1`, `L0-vs-L1` | checkpoints gone: `evals/bench/results/official-r403-…ckpt.jsonl` no longer exists, and no same-basename copy survives in the records |
| r442 `opus55-opus55judge`, `opus55-sonnet5judge` | checkpoints gone (`official-r442-opus55-A-easy.ckpt.jsonl`) |
| r447 `keep-floor-s0/s1/s2` | checkpoints were written in ANOTHER worktree (`D:\Claude Projects\regenold-r447-wt\…`), which is not this checkout |

For all eight the instrument falls back to the legacy `all` scope and says so
(`scope_downgraded`, with the path it tried). The R403 VETOs are the painful
ones: `rg_067` / `rg_090` decided a refusal and nothing now says whether the
lever served those rows.

This is an auditability defect, not a mystery: **the per-row provenance a veto
reads lives in a gitignored checkpoint** (`evals/bench/results/`), so the moment
the checkpoint is gone the verdict's scope question is unanswerable. Reads
written since R461.1 carry the deciding rows' reasons inside the payload
(`drops_in_scope[].arm_a/arm_b`, `by_reason_a/b`), which makes *their* scope
question answerable from the record alone. The proposal that follows from this
audit: embed the CAPTURED roster in the veto block, so a future vision of the
rule can be re-applied to an old verdict without the checkpoint.

Implemented in R461.6: reads published since carry the captured roster
(`veto.roster`) and the audit falls back to it when the checkpoint is gone —
see `CAPTURED-ROSTER.md`. The eight verdicts above predate the capture and
remain unauditable: the fix is prospective, not a recovery.

## 6. Defects this audit found in the instrument it audits

1. **The digest was over-claimed.** R461.3 described `hard_preamble_digest` as
   proof that two arms were one configuration. The audit's first run nominated
   the SAME arm as a "digest-identical third draw" for reads from four different
   rounds: the digest is the REQUEST SHAPE (the hard-preamble fixture), not the
   lever. Fixed in `evals/official/paired_ab.py` (applier
   `apply_digest_is_shape.py`): a difference REFUTES a declaration, a match never
   establishes one, and the audit now only accepts a re-draw that is DECLARED
   (`--declared-redraw`) and not refuted.
2. **"Survives the fix" was claimed on an unauditable pair.** The classifier
   required BOTH readings to be downgraded before calling a pair unverifiable, so
   an r403 read whose LEVER read fell back to `all` was reported as a refusal
   that survives the scope change. Now a downgrade on either reading is
   `unverifiable` — the same class of mistake the audit exists to find, caught in
   the audit.

## 7. Re-running

```bash
python docs/measurements/r461/audit_published_gates.py \
  --declared-redraw "docs/measurements/r461/paired-r461-count-only-wrapper.json=score-r460-tunnel-off-s3-hard.json"
```

Writes `gate-verdict-audit.json` and prints the table. The declared re-draw is
the R461 gate's own control arm (an OFF draw, same protocol); the audit verifies
it and refuses the declaration if the rows disagree.
