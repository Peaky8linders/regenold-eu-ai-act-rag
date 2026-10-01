"""R461.1 — record the rule-#8 scope fix and the gate re-read in the round docs.

Eight anchored edits to `COUNT-ONLY-CONFIRM.md` (the verdict, the two tables that
name the veto, a pointer after section 4, a new section 5.1 with the before/after
re-read, the acceptance table, the decision, one caveat), one append to
`CHECKPOINT.md`, and one paragraph appended to `CONCISENESS-PROGRAM.md` section
5.1. Re-running the patcher is a no-op: see `patch_once` for why the shared
helper's idempotency test is not enough for edits that keep their anchor.

    ../../.venv/Scripts/python.exe -m docs.measurements.r461.patch_docs_rule8
"""
from __future__ import annotations

import sys
from pathlib import Path

from docs.measurements.r461.patch_docs import patch

ROOT = Path(__file__).resolve().parents[3]

CONFIRM = ROOT / "docs" / "measurements" / "r461" / "COUNT-ONLY-CONFIRM.md"
CHECKPOINT = ROOT / "docs" / "measurements" / "r460" / "CHECKPOINT.md"
PROGRAM = ROOT / "docs" / "measurements" / "r460" / "CONCISENESS-PROGRAM.md"

# --------------------------------------------------------------------------- #
# COUNT-ONLY-CONFIRM.md
# --------------------------------------------------------------------------- #
VERDICT_OLD = """**Verdict: NOT PROMOTED on this draw — every measured acceptance target is met
except hard rule #8, which one TRANSPORT-DEGRADED row trips, and this gate
demonstrates that rule #8's per-row veto is not itself draw-stable at n=37.**
Read the refusal as a rule application, not as a measured regression: on the
substance this is the strongest arm the conciseness program has produced, and the
§7 decision is stated for the reader rather than buried.
"""

VERDICT_NEW = """**Verdict: every measured acceptance target is now met, and the arm is still NOT
PROMOTED.** The one failing criterion was hard rule #8, tripped by a row whose
Stage-2 legs both failed — and §5.1 records the fix to the rule's OPERATING
DEFINITION plus the re-read of this gate under it: **rule #8 no longer fires on
this arm, the noise floor still does, and no drop leaves the record.** What
remains is a promotion decision, not a measurement (§7).
"""

GOLD_ROW_OLD = """| gold heads dropped | 2 | 1 | | | new in B: `rg_037` |
"""
GOLD_ROW_NEW = """| gold heads dropped | 2 | 1 | | | new in B: `rg_037`, reported OUT OF SCOPE (§5.1) |
"""

POINTER_ANCHOR = """## 5. The instrument finding: rule #8 is not draw-stable at n=37
"""

POINTER_NEW = """§4's row is not a veto any more: §5.1 re-reads this gate under rule #8's fixed
operating definition, where a row the lever never served cannot testify and
`rg_037` is excluded from the veto and reported in full.

## 5. The instrument finding: rule #8 is not draw-stable at n=37
"""

ACCEPT_ANCHOR = """## 6. Acceptance, against the targets CONCISENESS-PROGRAM.md §5 wrote in advance
"""

SECTION_51 = """## 5.1 The fix, applied, and this gate re-read under it

Rule #8's operating definition was "any row", and that is what made a transport
event a lever verdict. It now reads **the rows where the lever actually served the
arm under test**: `evals/official/paired_ab.py` joins each arm's checkpoint
(`provenance.stage2_served_by`, the field `run_official_batch` writes) to the score
rows by id, and a row is eligible iff the arm under test was served by `primary`
or `fallback` — the two legs that carried the block's payload. On a checkpoint
written before `stage2_served_by` existed the only hint is `stage2_polish`, and
`True` is read as a Stage-2 leg.

Four properties were built in rather than assumed, because a scope that can only
narrow a veto is indistinguishable from an exemption:

* **every excluded row, and every drop on one, is reported** — with its reason, in
  the `veto` block of the payload and in the printed line; the all-rows
  `gold_dropped_head` counts are untouched, so the R461 refusal's own evidence is
  still in the artifact;
* **`--veto-scope all` reproduces the pre-R461 definition exactly**, so every
  published verdict stays re-derivable;
* **unreadable provenance does not lift a veto**: no checkpoint, a checkpoint that
  names no leg on any row (pre-R417), or a pair with no eligible row at all falls
  back to `all` and flags `scope_downgraded`; a single row whose provenance is
  missing or names nothing reads UNDECIDED, which is not CLEAN;
* **the axes, the all-rows drop counts and the answer lengths are identical under
  both scopes** (asserted per pair by the re-read), so the change moves the veto
  and nothing else.

Re-read from the round's existing checkpoints (`rule8_scope_reread.py` →
`RULE8-SCOPE-REREAD.md`, raw payloads in `rule8-scope-reread.json`):

| pair | scope=all (pre-R461) | scope=lever (now) |
| :-- | :-- | :-- |
| **the gate** R461-COUNT vs R461-OFF | **VETO** — `rg_037`, B=`deterministic` | **CLEAN** — 27/35 gold rows evaluated, `rg_037` reported out of scope |
| **noise floor** R461-OFF vs R460-OFF | **VETO** — `rg_061`, `rg_088` | **VETO** — both `primary`/`primary`, unchanged |
| **R460-FULL** vs R460-OFF | **VETO** — `rg_037`, B=`prior_turn` | **CLEAN** — same row, same reason |

The middle row is the one that matters: the fix removes the rows that cannot
testify and retains every drop that can. The rule stays undecidable at n=37 with
one draw — the noise floor still vetoes two gold heads with no lever present — and
that is the honest reading of it, not a reason to have left the definition alone.

The third row is a re-read of a SHIPPED round's record, not just of this one: the
full block's rule-#8 refusal rested on the same row id, where `prior_turn` means
the truncation guard kept the previous turn's answer. That refusal now reads
CLEAN — and it still does not promote the full block, which failed its other
targets (ans_conciseness -4.49 pp [-8.77, -0.68], answers +64.0 chars). What the
re-read corrects is the reason given, which is the part of the record a next
reader would otherwise trust.

Tests: `tests/test_r461_rule8_lever_scope.py`, 24 of them, pinning the reason
table, both scopes, the three downgrade paths, the UNDECIDED path, the legacy call
signature, and the three measured pairs above (skipped where the gitignored
checkpoints are absent).

"""

ACCEPT_ROW_OLD = """| no gold heads dropped | 0 new drops on the 36 rows the lever ran; 1 on a row the lever never ran | **no** |
"""
ACCEPT_ROW_NEW = """| no gold heads dropped | 0 in scope on the 27 lever-served gold rows; 1 reported out of scope (§5.1) | **yes** |
"""

ACCEPT_PROSE_OLD = """Four of five, and the fifth is a rule application rather than a measurement. For
comparison on the same instrument, the full block met two of five.
"""
ACCEPT_PROSE_NEW = """Five of five under the rule as fixed in §5.1 — and the fifth was a rule
application, not a measurement: it is now the rule that was fixed rather than the
lever that was waived. For comparison on the same instrument, the full block met
two of five.
"""

DECISION_OLD = """## 7. The decision

**Not promoted in this commit.** `calibration_enabled()` and
`count_only_enabled()` both keep their allow-lists; nothing default-ON, nothing
promoted. `promote_conciseness_calibration.py` stays unapplied, and a
`promote_count_only.py` is deliberately NOT written: the honest next step is not a
promotion script, it is one of these two, in this order.

1. **Fix the veto's operating definition, then re-read this gate from the
   checkpoints.** The count-only arm's own numbers say the lever cost no gold head
   anywhere it ran; the failing row is a degraded transport leg. Making rule #8
   conditional on `stage2_polish`/`stage2_served_by` is a change to the
   INSTRUMENT, it is justified by §5's measurement, and it must be made and
   reviewed on its own — not used as a retro-fit exemption for this lever.
2. **Spend one replicate when the tunnel allows.** `run_gate_count_only.sh 3`
   tops the gate up from the existing checkpoints one replicate at a time. If
   `rg_037` runs the lever in replicate 2, the veto lifts on the merits.

Only then does the count-only block become a promotion candidate, and the
evidence to promote it is already on disk.
"""

DECISION_NEW = """## 7. The decision

**Not promoted in this commit** — `calibration_enabled()` and `count_only_enabled()`
both keep their allow-lists, nothing is default-ON, and
`promote_conciseness_calibration.py` stays unapplied. What has changed is that the
RULE is no longer the reason.

1. **Done: the veto's operating definition, and this gate re-read under it.** See
   §5.1. The instrument change is `evals/official/paired_ab.py`; the tests are
   `tests/test_r461_rule8_lever_scope.py` (24); the re-read is
   `rule8_scope_reread.py` → `RULE8-SCOPE-REREAD.md`. It was made on §5's
   measurement — a missing gold head on a row the lever never served is not
   evidence about the lever — and it is explicitly NOT an exemption written for
   this lever: under it the noise-floor pair still vetoes, an unreadable checkpoint
   still vetoes, and a drop on a row whose provenance is unknown reads UNDECIDED,
   which is not a pass.
2. **Optional, and the only remaining measurement: one replicate.**
   `run_gate_count_only.sh 3` tops the gate up from the existing checkpoints one
   replicate at a time. It is no longer what lifts the veto — §5.1 does that, on
   the evidence — it is what would price the draw band on the deciding axis.
3. **Then the promotion decision, on the evidence already on disk.** Every target
   the program wrote in advance is met on this draw (§6, five of five under the
   fixed rule), the ref_conciseness mechanism reproduces three times (+7.69 here,
   +5.52 on this transport in R460, +4.76 on Bedrock), and the full block's two
   costs are gone. A `promote_count_only.py` is still deliberately NOT written:
   the next commit should either promote on the record or spend the replicate,
   not do both at once.
"""

CAVEAT_OLD = """* Arm A of this gate is a second OFF draw, not the recorded one. The R460 OFF arm
  remains the arm of record for R460's own verdict; §2's third pair is the bridge.
"""
CAVEAT_NEW = """* Arm A of this gate is a second OFF draw, not the recorded one. The R460 OFF arm
  remains the arm of record for R460's own verdict; §2's third pair is the bridge.
* §5.1's scope fix does not make rule #8 decidable at n=37: it removes the rows
  that cannot testify about the lever, and the noise floor still vetoes on two gold
  heads with no lever present. One draw still cannot decide the rule, and the
  replicate in §7.2 is what would price it.
"""

# --------------------------------------------------------------------------- #
# CHECKPOINT.md
# --------------------------------------------------------------------------- #
CHECKPOINT_ENTRY = """

---

## 2026-10-01 (R461.1 — hard rule #8's OPERATING DEFINITION fixed, and the gate re-read from its checkpoints)

The R461 refusal's stated first next step, taken on its own merits and in its own
commit: rule #8 read "any row", so a row whose Stage-2 output the transport
discarded could veto a lever that was never in the answer. The veto now reads the
rows where the lever actually served the arm under test.
`RULE8-SCOPE-REREAD.md` (+ `rule8-scope-reread.json`); harness
`rule8_scope_reread.py`, tests `tests/test_r461_rule8_lever_scope.py` (24).

* **The contract.** `evals/official/paired_ab.py` joins each arm's checkpoint
  (`provenance.stage2_served_by`, else `stage2_polish is True` on a pre-R417
  checkpoint) to the score rows by id, over the `ckpt` path each score payload
  records (`--a-ckpt`/`--b-ckpt` override). Eligible = arm B served by
  `primary`/`fallback` — the legs that carried the lever's payload. `deterministic`,
  `prior_turn` and "no Stage-2 call" rows cannot testify; every excluded row and
  every drop on one is REPORTED, and the all-rows `gold_dropped_head` block is
  unchanged. `--veto-scope all` reproduces the pre-R461 reading exactly.
* **Fail-closed, three ways**, because a scope that can only narrow a veto is an
  exemption: unreadable provenance - no checkpoint, a checkpoint that names no leg
  on any row (the pre-R417 arms on disk), or no eligible row at all - falls back
  to `all` with `scope_downgraded` set; a row whose provenance is missing or names
  nothing reads UNDECIDED, which is not CLEAN; and the axes, drop counts and answer
  lengths are asserted identical under both scopes.
* **Re-read, before -> after.** THE GATE R461-COUNT vs R461-OFF: VETO (`rg_037`,
  B=`deterministic`) -> **CLEAN**, 27/35 gold rows evaluated with the excluded row
  reported. NOISE FLOOR R461-OFF vs R460-OFF: VETO -> **VETO** (`rg_061`, `rg_088`,
  both `primary`/`primary`) - the draw-instability finding survives the fix, which
  is the test of whether the fix removed rows rather than drops. R460-FULL vs
  R460-OFF: VETO (`rg_037`, B=`prior_turn`) -> **CLEAN** - a SHIPPED round's
  rule-#8 reason was also a degraded row; its other targets (ans_conciseness -4.49
  pp, +64.0 chars) are untouched, so R460-FULL is still not promoted.
* **Verdict for the count-only block: five of five acceptance targets met on this
  draw, still NOT PROMOTED.** Nothing default-ON, `promote_conciseness_calibration.py`
  still unapplied, still no `promote_count_only.py` written: what remains is the
  promotion decision (or one replicate to price the draw band), not a measurement.
"""

# --------------------------------------------------------------------------- #
# CONCISENESS-PROGRAM.md — section 5.1
# --------------------------------------------------------------------------- #
PROGRAM_ANCHOR = """effect. The fix the evidence supports is to evaluate the veto only on rows where
the lever ran, or to require the drop to persist across an OFF re-draw — a change
to the instrument, to be made on its own merits and not as a retro-fit exemption
for this lever.
"""

PROGRAM_ADDITION = """effect. The fix the evidence supports is to evaluate the veto only on rows where
the lever ran, or to require the drop to persist across an OFF re-draw — a change
to the instrument, to be made on its own merits and not as a retro-fit exemption
for this lever.

**The fix, applied, and the same gate re-read (R461.1).** `paired_ab` now reads
rule #8 on the rows where the lever's payload served the arm under test
(`stage2_served_by` in `primary`/`fallback`; `stage2_polish is True` on a
pre-`stage2_served_by` checkpoint), joined off the checkpoint each score payload
records. Every excluded row and every drop on one is reported; a drop on a row
whose provenance is missing or names nothing reads UNDECIDED, never CLEAN; an
unreadable checkpoint falls back to the pre-R461 definition (the stricter one) and
says so; `--veto-scope all` reproduces the old reading exactly.
`RULE8-SCOPE-REREAD.md`, `rule8_scope_reread.py`,
`tests/test_r461_rule8_lever_scope.py`.

| pair, re-read from the existing checkpoints | scope=all | scope=lever |
| :-- | :-- | :-- |
| the gate, R461-COUNT vs R461-OFF | VETO (`rg_037`, B=`deterministic`) | **CLEAN** |
| noise floor, R461-OFF vs R460-OFF | VETO (`rg_061`, `rg_088`) | **VETO**, unchanged |
| R460-FULL vs R460-OFF | VETO (`rg_037`, B=`prior_turn`) | **CLEAN** |

So the fifth acceptance target in this section is met on this draw: the fix
removes the rows that cannot testify and retains every drop that can, and the
axes, drop counts and answer lengths are asserted identical under both scopes.
Still nothing default-ON — promoting the count-only block is now a decision on the
record (`COUNT-ONLY-CONFIRM.md` §7), and one replicate remains the way to price
the draw band.
"""


def patch_once(path: Path, old: str, new: str, *, label: str, marker: str) -> None:
    """``patch`` for edits that INSERT around an anchor they do not consume.

    The shared helper's idempotency test cannot tell an applied edit from an
    unapplied one here, because these edits deliberately leave their anchor in
    place (section 4's pointer and section 5.1 are inserted BEFORE a heading).
    ``marker`` is a phrase that exists only in the added text, so its presence is
    the applied state.
    """
    raw = path.read_text(encoding="utf-8")
    if marker in raw:
        print(f"  already applied: {label}")
        return
    patch(path, old, new, label=label)


def append_once(path: Path, block: str, *, label: str) -> None:
    """Append a block, unless it is already the tail of the file."""
    raw = path.read_text(encoding="utf-8")
    if raw.endswith(block):
        print(f"  already applied: {label}")
        return
    patch(path, "", block, label=label, append=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("COUNT-ONLY-CONFIRM.md:")
    patch_once(
        CONFIRM,
        VERDICT_OLD,
        VERDICT_NEW,
        label="header verdict",
        marker="**Verdict: every measured acceptance target is now met",
    )
    patch_once(
        CONFIRM,
        GOLD_ROW_OLD,
        GOLD_ROW_NEW,
        label="section 2 gold-head row",
        marker="reported OUT OF SCOPE (§5.1)",
    )
    patch_once(
        CONFIRM,
        POINTER_ANCHOR,
        POINTER_NEW,
        label="section 4 pointer",
        marker="§4's row is not a veto any more",
    )
    patch_once(
        CONFIRM,
        ACCEPT_ANCHOR,
        SECTION_51 + ACCEPT_ANCHOR,
        label="section 5.1 re-read",
        marker="## 5.1 The fix, applied, and this gate re-read under it",
    )
    patch_once(
        CONFIRM,
        ACCEPT_ROW_OLD,
        ACCEPT_ROW_NEW,
        label="section 6 acceptance row",
        marker="0 in scope on the 27 lever-served gold rows",
    )
    patch_once(
        CONFIRM,
        ACCEPT_PROSE_OLD,
        ACCEPT_PROSE_NEW,
        label="section 6 prose",
        marker="Five of five under the rule as fixed in §5.1",
    )
    patch_once(
        CONFIRM,
        DECISION_OLD,
        DECISION_NEW,
        label="section 7 decision",
        marker="What has changed is that the",
    )
    patch_once(
        CONFIRM,
        CAVEAT_OLD,
        CAVEAT_NEW,
        label="section 8 caveat",
        marker="§5.1's scope fix does not make rule #8 decidable",
    )
    print("CHECKPOINT.md:")
    append_once(CHECKPOINT, CHECKPOINT_ENTRY, label="R461.1 round entry")
    print("CONCISENESS-PROGRAM.md:")
    patch_once(
        PROGRAM,
        PROGRAM_ANCHOR,
        PROGRAM_ADDITION,
        label="section 5.1 the fix and re-read",
        marker="**The fix, applied, and the same gate re-read (R461.1).**",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
