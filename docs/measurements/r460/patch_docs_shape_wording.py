"""Precision fixes with exact anchors. Idempotent."""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent

A = OUT / "ANALYSIS-AND-PLAN.md"
a = A.read_text(encoding="utf-8")
PAIRS_A = [
    (
        "the live hard board the rolling history means only the **first two dispatches of\n"
        "a run** carry the full stack (`history_turn_count <= 1`, R411/R412's gate); every\n"
        "later dispatch carries the 61-char persona.",
        "the live hard board the rolling history means only the **opening dispatches of a\n"
        "run** carry the full stack (`history_turn_count <= 1`, R411/R412's gate: R423.3\n"
        "measures rows 1-2 reading 0 and 1, and row 1's pushback also reads 1 - roughly\n"
        "2-3 of 74 dispatches); every later dispatch carries the 61-char persona.",
    ),
    (
        'payload is the static system stack" describes **easy mode and the first two hard',
        'payload is the static system stack" describes **easy mode and the opening hard',
    ),
    (
        "system=60,643 + user 15,975..40,700, and only the user part is billed.",
        "system=60,643 + user 15,975..40,700, and only the user part is counted by the\n"
        "wrapper's usage.",
    ),
]
fixes = 0
for old, new in PAIRS_A:
    if new in a:
        continue
    assert a.count(old) == 1, ("analysis", old[:50], a.count(old))
    a = a.replace(old, new)
    fixes += 1
if fixes:
    A.write_text(a, encoding="utf-8")
    print(f"analysis doc: {fixes} fix(es)")
else:
    print("analysis doc already fixed")

G = OUT / "SONNET-VS-OPUS55-GATE.md"
g = G.read_text(encoding="utf-8")
G_OLD = "   first two hard dispatches of a run), not an inert byte reduction; and"
G_NEW = "   opening hard dispatches of a run), not an inert byte reduction; and"
if G_NEW in g:
    print("gate doc already fixed")
else:
    assert g.count(G_OLD) == 1, ("gate", g.count(G_OLD))
    G.write_text(g.replace(G_OLD, G_NEW), encoding="utf-8")
    print("gate doc fixed")
