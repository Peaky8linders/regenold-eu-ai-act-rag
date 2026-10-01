"""One-word correction so the earlier CHECKPOINT entry does not contradict the
root cause found since (no truncation: the wrapper spills to a file for both
models; the gap is model adherence). Idempotent.
"""
from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parent / "CHECKPOINT.md"
src = P.read_text(encoding="utf-8")
OLD = "Cohere and re-baseline, per-row token/byte capture, capture-shape parity, and\nlocating the long-system truncation for Sonnet."
NEW = "Cohere and re-baseline, per-row token/byte capture, capture-shape parity, and\ncharacterising the long-system behaviour for Sonnet."
if NEW in src:
    print("already fixed")
else:
    assert src.count(OLD) == 1, src.count(OLD)
    P.write_text(src.replace(OLD, NEW), encoding="utf-8")
    print("fixed")
