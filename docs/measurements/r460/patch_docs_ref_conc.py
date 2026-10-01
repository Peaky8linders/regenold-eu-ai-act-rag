"""Apply the Ref Conciseness round's findings to this round's own docs.

Idempotent (each patch asserts a single match), and every replacement is checked
before it is written.  Run from the worktree root:

    ../../.venv/Scripts/python.exe docs/measurements/r460/patch_docs_ref_conc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

R460 = Path(__file__).resolve().parent


def patch(path: Path, old: str, new: str, *, label: str) -> bool:
    raw = path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    if n and n in raw and o not in raw:
        print(f"  already applied: {label}")
        return False
    count = raw.count(o)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match in {path.name}, found {count}")
    path.write_text(raw.replace(o, n), encoding="utf-8")
    print(f"  applied: {label}")
    return True


COHERE_OLD = """Consequence for the plan: a **production Cohere key is required** before the R450
`density` live paired gate. A hard board makes ~4 rerank calls/row; pacing to
10/min would inflate Resp. Speed, which is a scored axis, so a paced run cannot
answer a promotion question."""

COHERE_NEW = """Consequence for the plan, CORRECTED later the same evening: the trial key is
**not** what blocks the R450 `density` gate. `run_official_batch._net_of_pacing`
subtracts the rerank pacer's sleep from every measured latency (R409 — R407
scored Resp. Speed on 13 s of pacing before it was fixed), so a paced arm keeps a
clean Speed axis: run it with `--min-rerank-gap 7` and
`--require-cohere-rerank` (which tolerates budget skips) and ~4 rerank calls/row
stay inside 10/min. What blocks the gate is **power**: R450 measured `density` at
+3/82 rows of gold-unit coverage, which at n=37 is ~1 row — below the house
detection floor. See `REF-CONCISENESS-LEVERAGE.md` §6 for the full correction and
§7 for the re-order."""

COHERE_CAVEAT_OLD = """* Cohere key is **trial** (10 calls/min, 1000/month). One hard board at natural
  pace fits the rate budget; nothing else may call Cohere concurrently, and the
  `density` gate needs a production key."""

COHERE_CAVEAT_NEW = """* Cohere key is **trial** (10 calls/min, 1000/month). One hard board at natural
  pace fits the rate budget, and nothing else may call Cohere concurrently. A
  *paced* arm is also valid for Speed: the harness nets the pacer's sleep out of
  every measured latency (see §1)."""

PLAN_STATUS_OLD = """**Status (evening): Tier-0 items 1-5 are DONE and verified live** —
`TIER0-FIXES.md` (deadline, slow-not-down probe, per-row usage capture,
wrapper root cause) and `COHERE-REBASELINE.md` (easy 87.35, hard 85.77,
shape measured per row). Tier-1 item 6 (the `density` live gate) is now
blocked only on a **production Cohere key**: the trial key allows 10 rerank
calls/min and pacing would corrupt the Speed axis, which is the axis the
gate's decision needs to be clean on."""

PLAN_STATUS_NEW = """**Status (evening): Tier-0 items 1-5 are DONE and verified live** —
`TIER0-FIXES.md` (deadline, slow-not-down probe, per-row usage capture,
wrapper root cause) and `COHERE-REBASELINE.md` (easy 87.35, hard 85.77,
shape measured per row). Tier-1 item 6 (the `density` live gate) is **no longer
blocked by the trial key** — a paced arm keeps a clean Speed axis because the
harness nets the pacer's sleep out of the measured latency — but it is
**underpowered at n=37** (+3/82 rows offline, ~1 row here). Item 10's premise is
corrected: Ref Conciseness is priced, screened and closed as a key-blind lever
(`REF-CONCISENESS-LEVERAGE.md`: +5.82 pp of headroom, +0.9 reachable), and
hard-mode Speed is a 0.04 tie, not a deficit. Nothing further in Tier 1 is worth
a board; the remaining scored lever is RESERVE, which needs the operator ruling."""

PLAN_ITEM6_OLD = """6. **`REGENOLD_EMIT_ALLOC=density` - live paired gate** (R450 evidence). It
   changes which provisions reach the evidence block, so it needs the
   correctness-first gate on hard + easy, not an offline sweep."""

PLAN_ITEM6_NEW = """6. **`REGENOLD_EMIT_ALLOC=density` - live paired gate** (R450 evidence). It
   changes which provisions reach the evidence block, so it needs the
   correctness-first gate on hard + easy, not an offline sweep. **Re-scoped
   later:** measure it at n=110 with `--repeats 3`, or ship it as a default
   behind a regression gate - at n=37 the expected effect (~1 row) is below the
   detection floor, and the trial key no longer blocks a *paced* arm
   (`REF-CONCISENESS-LEVERAGE.md` 6/7)."""

PLAN_ITEM9_OLD = """9. **Profile the non-Stage-2 half of a turn.** Opus turn p50 18.0 s vs ~9 s seam
   call (1.1). Instrument retrieval/KG, route, guards and the tail-repair pass
   on ~10 hard rows; the speed axis is the largest scored deficit (82.8 vs 86.7)
   and no model swap fixes it."""

PLAN_ITEM9_NEW = """9. **Profile the non-Stage-2 half of a turn.** Opus turn p50 18.0 s vs ~9 s seam
   call (1.1). Instrument retrieval/KG, route, guards and the tail-repair pass
   on ~10 hard rows. **Premise corrected:** the live hard board scores Speed
   86.66 against the frontier's 86.70 (a 0.04 tie, and easy is +6.5 ahead), so
   this is a latency-hygiene item now, not the largest scored deficit. Also note
   hard-mode Speed grades the **pushback** turn only
   (`score_arm._graded_latency_ms`): turn-1 latency on hard is unscored."""

PLAN_ITEM10_OLD = """10. **Decide on RESERVE** (R442 audit, `PR-AUDIT-456-460.md` §4): answering the
    verbatim pushback with the verified previous answer measures Speed 79.0 ->
    94.8 (~+1 to +2 pp overall) but drops gold heads on two pools and contradicts
    "always Stage-2". Needs an operator ruling; if approved, gate it."""

PLAN_ITEM10_NEW = """10. **Decide on RESERVE** (R442 audit, `PR-AUDIT-456-460.md` §4): answering the
    verbatim pushback with the verified previous answer measures Speed 79.0 ->
    94.8 (~+1 to +2 pp overall) but drops gold heads on two pools and contradicts
    "always Stage-2". Needs an operator ruling; if approved, gate it. **Now the
    only measured lever left above the detection floor** - Ref Conciseness was
    priced at +5.82 pp of headroom with +0.9 reachable
    (`REF-CONCISENESS-LEVERAGE.md`), and density is underpowered at n=37."""

CHECKPOINT_OLD = """Live shapes: easy rows send the full 60.6k stack (turns=1); hard rows send the
61-char persona on EVERY dispatch (fixed fixture, turns=20), so the hard board
never carries the stack."""

CHECKPOINT_NEW = """Live shapes: easy rows send the full 60.6k stack (turns=1); hard rows send the
61-char persona on EVERY dispatch (fixed fixture, turns=20), so the hard board
never carries the stack."""

NEXT_ENTRY = """
---

## 2026-09-30 (Ref Conciseness) -- priced, screened, closed

`REF-CONCISENESS-LEVERAGE.md` (+ `ref_conc_leverage.py`, `ref_prune_screen.py`,
both offline and exact: they reproduce 59.14 / 61.10 / 85.77 / 87.35 from the
checkpoints). Ref Conciseness is the lowest axis (59.14 hard) and the
highest-leverage one (elasticity 0.181 vs 0.107-0.132 for the rest); the ceiling
is +5.82 hard / +5.55 easy, and **+0.9 is what any key-blind rule can reach**.

* Exact structure: rc = `min(1, |expected|/|provided|)`, a count ratio; 27/35
  hard rows have a ONE-ref key, 24/35 are over-supplied, 88 supplied vs 44
  expected (2.00x). Because the judge prompt carries the KEY's provisions and the
  answer text only (never our ref list), ref pruning cannot move the answer axes
  - the only risk is the two reference axes.
* Screened: mention +0.55/+0.54 (bit-identical correctness axes), dedupe
  +0.00/+0.19, drop-redundant-parent a no-op (no row carries such a pair),
  cap@2 +0.36/-0.11, cap@1 -1.00/-1.83, mention+cap@2 +0.79/-0.11. Ceilings:
  min preserving subsequence +4.96/+4.68, oracle match +3.06/+2.75.
* Why the mention rule is weak: of supplied refs, 63.6% are NOT key-relevant but
  ARE named in the answer prose (only 3.4% are neither). `graph_rag_prompts.py`
  already says the same thing -- a pruner downstream of the prose is a no-op or
  drops gold; the count is decided in the generator, and the generator already
  carries the minimality contract (`USER_REF_MINIMALITY` V2 default ON).
* Two premises corrected: (1) hard-mode Speed grades the **pushback** turn only
  (`_graded_latency_ms`), so turn-1 latency on hard is unscored; (2) the rerank
  pacer's sleep is **netted out** of measured latency (`_net_of_pacing`, R409), so
  the trial key does not block a paced arm -- the R450 `density` gate is blocked
  by *power* at n=37 (~1 row), not by the key.
* Nothing changed a default; the `mention` candidate (+0.55) is below the n=37
  detection floor and was recorded, not run. RESERVE remains the only measured
  lever above the floor and still needs the operator ruling.
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("COHERE-REBASELINE.md:")
    p = R460 / "COHERE-REBASELINE.md"
    patch(p, COHERE_OLD, COHERE_NEW, label="density-gate blocker correction")
    patch(p, COHERE_CAVEAT_OLD, COHERE_CAVEAT_NEW, label="caveat: paced arm is valid")
    print("ANALYSIS-AND-PLAN.md:")
    p = R460 / "ANALYSIS-AND-PLAN.md"
    patch(p, PLAN_STATUS_OLD, PLAN_STATUS_NEW, label="status paragraph")
    patch(p, PLAN_ITEM6_OLD, PLAN_ITEM6_NEW, label="item 6 re-scope")
    patch(p, PLAN_ITEM9_OLD, PLAN_ITEM9_NEW, label="item 9 premise")
    patch(p, PLAN_ITEM10_OLD, PLAN_ITEM10_NEW, label="item 10 note")
    print("CHECKPOINT.md:")
    p = R460 / "CHECKPOINT.md"
    raw = p.read_text(encoding="utf-8")
    if "REF Conciseness) -- priced, screened, closed" in raw:
        print("  already applied: checkpoint entry")
    else:
        entry = NEXT_ENTRY.replace("\n", "\r\n") if "\r\n" in raw else NEXT_ENTRY
        p.write_text(raw.rstrip("\r\n") + ("\r\n" if "\r\n" in raw else "\n") + entry,
                     encoding="utf-8")
        print("  applied: checkpoint entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
