"""Append the Sonnet-vs-Opus gate pointer to ``CHECKPOINT.md`` (idempotent)."""
from __future__ import annotations

from pathlib import Path

P = Path(__file__).resolve().parent / "CHECKPOINT.md"
SECTION = """
---

## 2026-09-30 (later) -- Sonnet-vs-Opus Stage-2 gate is DONE, verdict HOLD

`SONNET-VS-OPUS55-GATE.md` carries the full result. Headlines: 37/37 rows both
arms, paired n=37, one shared judge cache; answer-strict -8.11 (3 rows, of which
rg_097 is a wrong verdict), references PASS (no new gold drops, A=2 -> B=0),
conciseness/tone PASS, board speed -15.47 but transport-contaminated (five
consecutive 60 s-deadline timeouts aborted the first Sonnet run at 28/37; it was
resumed with a 150 s deadline, which never binds the Opus arm). Token leg:
prompt tokens equal the user payload at exactly 4.00 chars/token, identical
across models and invariant to the 60,643-char system stack, so the payload cut
buys wire bytes, not tokens. Nothing was flipped;
`REGENOLD_STAGE2_ALLOW_NON_OPUS` stays default-OFF.
"""

src = P.read_text(encoding="utf-8")
if "Sonnet-vs-Opus Stage-2 gate is DONE" in src:
    print("already present")
else:
    P.write_text(src.rstrip("\n") + "\n" + SECTION, encoding="utf-8")
    print(f"appended {len(SECTION)} chars to {P.name}")
