"""R461 — record the PROMOTION in the round docs.

Five anchored edits to `COUNT-ONLY-CONFIRM.md` (the verdict, the decision, a new
section 9 with the doctrine, one caveat), one to `CONCISENESS-PROGRAM.md` (the
lever's entry in section 4 plus a new 5.2 for the promotion), and one append to
`CHECKPOINT.md`. Idempotent: see `patch_once` in `patch_docs_rule8`.

    ../../.venv/Scripts/python.exe -m docs.measurements.r461.patch_docs_promotion
"""
from __future__ import annotations

import sys
from pathlib import Path

from docs.measurements.r461.patch_docs_rule8 import append_once, patch_once

ROOT = Path(__file__).resolve().parents[3]

CONFIRM = ROOT / "docs" / "measurements" / "r461" / "COUNT-ONLY-CONFIRM.md"
PROGRAM = ROOT / "docs" / "measurements" / "r460" / "CONCISENESS-PROGRAM.md"
CHECKPOINT = ROOT / "docs" / "measurements" / "r460" / "CHECKPOINT.md"

CAVEATS_ANCHOR = "## 8. Caveats\n"

SECTION_9 = """## 9. The promotion — default ON (2026-10-01)

`REGENOLD_CONCISE_COUNT_ONLY` is promoted: no env means the citation budget is in
force, and `PROMOTION.md` is the record (evidence, doctrine, cache invalidation,
rollback, canary). Three mechanical consequences, all pinned by
`tests/test_r461_count_only_promoted.py`:

* **the OFF switch is a deny-list** — `0`/`false`/`no`/`off` (case/space
  tolerant) and nothing else, so a typo cannot silently disable a shipped lever,
  and the kill switch is byte-identical to the pre-lever Stage-2 message;
* **the cache key carries the RESOLVED mode** (`|concise=off|count|full`). The
  raw env spelling is empty both before and after a default flip, so without that
  term the promotion would have served pre-promotion (block-OFF) answers for the
  same question — the R263.2 stale-hit class with the promotion as the flip. The
  addition invalidates the pre-promotion cache wholesale, deliberately, and the
  raw entry stays in `engine_flags` for operator intent;
* **the R460 full block is now the explicit pair** (`COUNT_ONLY=0
  CALIBRATION=1`), because count-only still wins a mis-set one. Both gate
  launchers NAME their arms for the same reason: their OFF arms used to be "flags
  absent", which after this flip renders the block, so a re-run would have
  measured the block against itself.

Rollback is one environment variable, `REGENOLD_CONCISE_COUNT_ONLY=0`, with no
code deploy; it restores the pre-lever bytes and is a distinct cache regime.

"""

PROGRAM_SECTION_52_ANCHOR = "## 6. Caveats\n"

PROGRAM_SECTION_52 = """### 5.2 Promoted, on the evidence (R461, 2026-10-01)

`REGENOLD_CONCISE_COUNT_ONLY` is default ON. The refusal this program carried
through R460 and R461 was never a measured regression — the count half reproduced
on every transport it was tried on — and after §5.1's rule fix the arm meets
every target this program wrote in advance (five of five, §5.1's table), with the
one drop on the board landing on a row the block never served.

The promotion's record is `docs/measurements/r461/PROMOTION.md`: the deny-list OFF
switch, the cache invalidation (the RESOLVED mode in `_engine_cache_key`, because
a raw-spelling-only key cannot see a default flip and would serve pre-promotion
answers), the full block's new reachability as the explicit pair, the rollback
(`REGENOLD_CONCISE_COUNT_ONLY=0`, one variable, no redeploy), and the live canary
on the published endpoint. `tests/test_r461_count_only_promoted.py` pins the
promotion contract; the R460 suite's autouse fixture kills the promoted block so
that suite still tests the R460 arm, and both gate launchers now name their arms
instead of relying on "flags absent".

The refuted half is untouched: `REGENOLD_CONCISE_CALIBRATION` stays default OFF
and `promote_conciseness_calibration.py` stays unapplied.

"""

CHECKPOINT_ENTRY = """

---

## 2026-10-01 (R461.2 — REGENOLD_CONCISE_COUNT_ONLY PROMOTED to default ON, with a live canary)

The R461.1 re-read left one thing undone: the arm met every target and the rule
that refused it had been fixed, so the decision was a promotion, not another
measurement. `PROMOTION.md`; applier `promote_count_only.py` (idempotent,
verifies its own effect from a fresh interpreter); contract tests
`tests/test_r461_count_only_promoted.py`.

* **The flip.** No env means ON; the OFF switch is a DENY-LIST
  (`0`/`false`/`no`/`off`, case/space tolerant) so a malformed value cannot
  silently disable a shipped lever, and the kill switch is byte-identical to the
  pre-lever Stage-2 user message. The other levers are untouched:
  `REGENOLD_CONCISE_CALIBRATION` stays default OFF and
  `promote_conciseness_calibration.py` stays unapplied.
* **Cache invalidation, the part a default flip needs.** `_engine_cache_key`
  folded the RAW env spelling, which is `""` both before and after the flip, so a
  pre-promotion entry (block OFF) would have answered a block-ON question for the
  same text — the R263.2 stale-hit class with the promotion itself as the flip.
  The RESOLVED mode is now keyed (`|concise=off|count|full`), which invalidates
  the pre-promotion cache wholesale (the R81-N.1 effect, deliberately) and keeps
  the three regimes distinct; the raw entry stays for operator intent.
* **Two owned consequences, both fixed rather than suffered.** The full R460
  block is reachable now only as the explicit pair (`COUNT_ONLY=0
  CALIBRATION=1`), because count-only wins a mis-set one; and both gate launchers
  NAME their arms, because their OFF arms were "flags absent", which after the
  flip renders the block — a re-run of either gate would have measured the block
  against itself. The R460 suite's autouse fixture kills the promoted block, so
  it still tests the R460 arm.
* **Canary.** `production_canary.py`, 8 fixed official-board questions against the
  published endpoint, PRE and POST around the deploy, gates on deploy commit,
  health, transport, budget and answer integrity. Results in `CANARY.md` and
  section 4 of `PROMOTION.md`; rollback is one env var.
* **What is not claimed.** n=37 decides direction, rule #8 is still not
  draw-stable at that n, production passes through the route's own reference
  budget (the canary reads the wire, which is what a user sees), and one
  replicate remains the way to price the draw band.
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("COUNT-ONLY-CONFIRM.md:")
    patch_once(
        CONFIRM,
        """**Verdict: every measured acceptance target is now met, and the arm is still NOT
PROMOTED.** The one failing criterion was hard rule #8, tripped by a row whose
Stage-2 legs both failed — and §5.1 records the fix to the rule's OPERATING
DEFINITION plus the re-read of this gate under it: **rule #8 no longer fires on
this arm, the noise floor still does, and no drop leaves the record.** What
remains is a promotion decision, not a measurement (§7).
""",
        """**Verdict: PROMOTED — `REGENOLD_CONCISE_COUNT_ONLY` is default ON
(2026-10-01).** Every target this round wrote in advance is met (§6), the one
that was failing was a rule rather than a measurement and the rule is fixed
(§5.1), and §9 records the promotion itself: the deny-list OFF switch, the cache
invalidation the flip requires, and the live canary on the published endpoint.
`PROMOTION.md` is the full record.
""",
        label="header verdict",
        marker="**Verdict: PROMOTED — `REGENOLD_CONCISE_COUNT_ONLY` is default ON",
    )
    patch_once(
        CONFIRM,
        """**Not promoted in this commit** — `calibration_enabled()` and `count_only_enabled()`
both keep their allow-lists, nothing is default-ON, and
`promote_conciseness_calibration.py` stays unapplied. What has changed is that the
RULE is no longer the reason.""",
        """**PROMOTED (2026-10-01).** `REGENOLD_CONCISE_COUNT_ONLY` is default ON — see
§9 and `PROMOTION.md`. `calibration_enabled()` (the R460 full block) keeps its
allow-list and `promote_conciseness_calibration.py` stays unapplied, so exactly
one default moved and the refuted arm stays refuted by default. The three steps
below are the record of how the decision was reached, now closed.""",
        label="section 7 opening",
        marker="**PROMOTED (2026-10-01).** `REGENOLD_CONCISE_COUNT_ONLY` is default ON",
    )
    patch_once(
        CONFIRM,
        """3. **Then the promotion decision, on the evidence already on disk.** Every target
   the program wrote in advance is met on this draw (§6, five of five under the
   fixed rule), the ref_conciseness mechanism reproduces three times (+7.69 here,
   +5.52 on this transport in R460, +4.76 on Bedrock), and the full block's two
   costs are gone. A `promote_count_only.py` is still deliberately NOT written:
   the next commit should either promote on the record or spend the replicate,
   not do both at once.""",
        """3. **Done: promoted on that evidence.** `promote_count_only.py` applied the flip
   (deny-list OFF switch, resolved mode in the cache key, arms named),
   `PROMOTION.md` is the record, and `production_canary.py` measured it on the
   published endpoint. The evidence is unchanged from the two steps above — five
   of five targets, three reproductions of the mechanism, the full block's costs
   gone — which is why the decision could be taken on the record rather than on
   another draw.""",
        label="section 7 step 3",
        marker="**Done: promoted on that evidence.**",
    )
    patch_once(
        CONFIRM,
        CAVEATS_ANCHOR,
        SECTION_9 + CAVEATS_ANCHOR,
        label="section 9 the promotion",
        marker="## 9. The promotion — default ON (2026-10-01)",
    )
    patch_once(
        CONFIRM,
        """* §5.1's scope fix does not make rule #8 decidable at n=37: it removes the rows
  that cannot testify about the lever, and the noise floor still vetoes on two gold
  heads with no lever present. One draw still cannot decide the rule, and the
  replicate in §7.2 is what would price it.
""",
        """* §5.1's scope fix does not make rule #8 decidable at n=37: it removes the rows
  that cannot testify about the lever, and the noise floor still vetoes on two gold
  heads with no lever present. One draw still cannot decide the rule, and the
  replicate in §7.2 is what would price it.
* The canary (§9) is 8 fixed questions, one draw each, on the wire: a sanity gate
  with a rollback attached, not a board. The promotion's evidence is §2 and §6;
  the canary is what says the deployed build serves the promoted behaviour.
""",
        label="section 8 canary caveat",
        marker="* The canary (§9) is 8 fixed questions",
    )
    print("CONCISENESS-PROGRAM.md:")
    patch_once(
        PROGRAM,
        """default OFF, registered in `_engine_cache_key`, and byte-identically additive to
the shipped contract (asserted). Section 5.1 is its gate.
""",
        """PROMOTED to default ON (R461, 2026-10-01, §5.2): registered in
`_engine_cache_key` twice over — the raw spelling for operator intent and the
RESOLVED mode for the invalidation a default flip requires — and byte-identically
additive to the shipped contract when killed (asserted). Section 5.1 is its gate,
`PROMOTION.md` the record.
""",
        label="section 4 promoted lever",
        marker="PROMOTED to default ON (R461, 2026-10-01, §5.2)",
    )
    patch_once(
        PROGRAM,
        PROGRAM_SECTION_52_ANCHOR,
        PROGRAM_SECTION_52 + PROGRAM_SECTION_52_ANCHOR,
        label="section 5.2 the promotion",
        marker="### 5.2 Promoted, on the evidence (R461, 2026-10-01)",
    )
    print("CHECKPOINT.md:")
    append_once(CHECKPOINT, CHECKPOINT_ENTRY, label="R461.2 round entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
