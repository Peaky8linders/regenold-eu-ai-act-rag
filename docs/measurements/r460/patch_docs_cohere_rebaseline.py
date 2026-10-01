"""Doc touch-ups for the Cohere re-baseline. Idempotent."""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent

CP = OUT / "CHECKPOINT.md"
cp = CP.read_text(encoding="utf-8")
MARK = "## 2026-09-30 (Cohere) -- re-baseline is in"
SECTION = f"""
---

{MARK}

`COHERE-REBASELINE.md`: easy **87.35** (frontier 80.9, ahead on all 8 axes),
hard **85.77** (frontier 81.7; +2.86 ref_loose, +2.38 ref_strict, tone 100,
speed 86.66 vs 86.7 - the only axis still behind, by 0.04). Both n=37, 0 errors,
Opus 5.5, all Tier-1 knobs at default, with the Tier-0 instrumentation live.
Live shapes: easy rows send the full 60.6k stack (turns=1); hard rows send the
61-char persona on EVERY dispatch (fixed fixture, turns=20), so the hard board
never carries the stack. Prompt counter is `len(user)/4.0` to the digit
(easy 9,236.5 median, hard 8,360). Hard `rg_049` is deterministic-served and
reported. The Cohere key is TRIAL (10 rerank calls/min): one board fits at
natural pace, nothing may run alongside it, and the R450 `density` live gate
needs a production key (pacing would corrupt the Speed axis). The first hard
attempt aborted because my own rate-limit burst stole the minute's budget, not
because of the board.
"""
if MARK in cp:
    print("checkpoint already updated")
else:
    CP.write_text(cp.rstrip("\n") + "\n" + SECTION, encoding="utf-8")
    print("checkpoint updated")

A = OUT / "ANALYSIS-AND-PLAN.md"
a = A.read_text(encoding="utf-8")
ANCHOR = (
    "Ordered by what unblocks the most evidence per unit of work. Every item names\n"
    "the artifact that already justifies it.\n"
)
STATUS = (
    "**Status (evening): Tier-0 items 1-5 are DONE and verified live** —\n"
    "`TIER0-FIXES.md` (deadline, slow-not-down probe, per-row usage capture,\n"
    "wrapper root cause) and `COHERE-REBASELINE.md` (easy 87.35, hard 85.77,\n"
    "shape measured per row). Tier-1 item 6 (the `density` live gate) is now\n"
    "blocked only on a **production Cohere key**: the trial key allows 10 rerank\n"
    "calls/min and pacing would corrupt the Speed axis, which is the axis the\n"
    "gate's decision needs to be clean on.\n"
)
if STATUS in a:
    print("plan status already present")
else:
    assert a.count(ANCHOR) == 1, a.count(ANCHOR)
    A.write_text(a.replace(ANCHOR, ANCHOR + "\n" + STATUS), encoding="utf-8")
    print("plan status added")
