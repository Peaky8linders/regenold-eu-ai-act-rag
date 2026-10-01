"""Fold the system-delivery canary result into ``SONNET-VS-OPUS55-GATE.md``.

The first draft of the gate doc said the delivery question was settled by the
R411/R412 effect and that a canary was "not run here". The canary was then run
(`system_delivery_canary.py`): delivery is real at short/mid sizes, Opus gets the
60,774-char stack, Sonnet does not. Idempotent.
"""
from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parent / "SONNET-VS-OPUS55-GATE.md"
src = P.read_text(encoding="utf-8")

R1_OLD = "1. **The 60,643-char system stack is not billed.** On `rg_003`, substituting the"
R1_NEW = (
    "1. **The usage counter ignores the system stack - but the model does not.** On\n"
    "   `rg_003`, substituting the"
)

R2_OLD = """   Note the R411/R412 result that delivering the full system *changes* answers
   (length 0.199x, p50 latency -15.5 s). Taken together the likeliest reading is
   that the wrapper's usage accounting excludes the system message rather than
   the model never receiving it; settling that needs the canary test, which is
   **not** run here."""
R2_NEW = """   What the counter cannot show, the canary settles
   (`system_delivery_canary.py`, run after this section was first drafted): the
   system message **is** delivered - both models obey a canary written only into
   the system at 129 and 3,131 chars - and at **60,774 chars Opus 5.5 still
   obeys it while Sonnet 5 does not** (its reply paraphrases the head of the
   stack: "This system serves as an EU AI Act Legal Specialist...", and misses
   the tail canary). Consequences: the payload cut is a *behavioral* lever
   wherever the stack is delivered (the single-turn shape: easy mode and the
   first two hard dispatches of a run), not an inert byte reduction; and
   Sonnet's long-system handling is a second, config-level reason not to
   promote it."""

R3_OLD = "so the lever is safe to keep as a tested option; it is not safe to promote."
R3_NEW = (
    "so the lever is safe to keep as a tested option; it is not safe to promote.\n"
    "Independently of the axes: at production system length the wrapper delivers\n"
    "the stack to Opus and a degraded (head-only) version to Sonnet, so promoting\n"
    "Sonnet would silently change what the easy-board Stage-2 calls see."
)

R4_OLD = "* Worktree is uncommitted: no default was changed, nothing was pushed."
R4_NEW = """* The wrapper's `usage` is `round(len(user)/4.0)`, a character heuristic; it
  cannot price the system stack. The canary is n=6 calls (3 sizes x 2 models).
* Worktree is uncommitted: no default was changed, nothing was pushed."""

changes = 0
for old, new in ((R1_OLD, R1_NEW), (R2_OLD, R2_NEW), (R3_OLD, R3_NEW), (R4_OLD, R4_NEW)):
    if new in src:
        continue
    assert src.count(old) == 1, (old[:60], src.count(old))
    src = src.replace(old, new)
    changes += 1

P.write_text(src, encoding="utf-8")
print(f"patched {P.name}: {changes} change(s)")
