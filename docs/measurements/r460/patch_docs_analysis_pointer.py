"""Final doc touch-ups: kill the stale "wire bytes, not tokens" phrasing, and
point CHECKPOINT.md at ANALYSIS-AND-PLAN.md. Idempotent.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent

GATE = OUT / "SONNET-VS-OPUS55-GATE.md"
gate = GATE.read_text(encoding="utf-8")
OLD = (
    "   cut therefore removes **wire bytes, not tokens** (-65.8 % of the payload is\n"
    "   the static system). The only token-billed lever is the evidence block, where\n"
    "   the census found 0.2-1.6 % provably removable."
)
NEW = (
    "   cut therefore removes **wire bytes only** (-65.8 % of the payload is the\n"
    "   static system), and nothing the usage counter can see. The only part of\n"
    "   the payload the counter prices is the evidence block, where the census\n"
    "   found 0.2-1.6 % provably removable."
)
if NEW in gate:
    print("gate doc already updated")
else:
    assert gate.count(OLD) == 1, ("gate", gate.count(OLD))
    GATE.write_text(gate.replace(OLD, NEW), encoding="utf-8")
    print("gate doc updated")

CP = OUT / "CHECKPOINT.md"
cp = CP.read_text(encoding="utf-8")
MARK = "## 2026-09-30 (final) -- analysis + plan"
SECTION = f"""
---

{MARK}

`ANALYSIS-AND-PLAN.md` consolidates the round and lists the next work in tiers.
Two findings landed after the gate doc: the system-delivery canary shows the
wrapper DOES deliver the system at short/mid sizes, delivers the 60,774-char
stack to Opus 5.5 but not to Sonnet 5, and the wrapper's `usage` is
`round(len(user)/4.0)` (a character heuristic, blind to the system). Tier 0 of
the plan is measurement/transport: Stage-2 deadline + abort semantics, restore
Cohere and re-baseline, per-row token/byte capture, capture-shape parity, and
locating the long-system truncation for Sonnet.
"""
if MARK in cp:
    print("checkpoint already updated")
else:
    CP.write_text(cp.rstrip("\n") + "\n" + SECTION, encoding="utf-8")
    print("checkpoint updated")
