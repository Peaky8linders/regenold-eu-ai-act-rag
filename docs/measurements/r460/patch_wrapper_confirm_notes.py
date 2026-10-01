"""R460 - two precision notes on WRAPPER-CONFIRM.md (idempotency-fixed).

1. Section 1: the arms differ by the flag ALONE (same `hard_preamble_digest` on
   every row of both arms, engine cache cleared per sample), which is what makes
   the paired reading legitimate.
2. Section 2: the length-controlled gap is NOT attributed, and why.

The first version of this patch guarded on a lower-case substring while the note
it inserts starts with a capital ``The``, so a second run appended the note
again. This version collapses that duplication and guards case-insensitively.

Run:  ../../.venv/Scripts/python.exe docs/measurements/r460/patch_wrapper_confirm_notes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOC = REPO / "docs" / "measurements" / "r460" / "WRAPPER-CONFIRM.md"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

SHAPE_NOTE = """* The arms differ by the flag ALONE and that is checkable on the artifacts:
  every row of both arms carries the same `hard_preamble_digest`
  (`cb85452c9c04`), the request shape is fixed mode, and the route's engine cache
  was cleared for the sample (so no arm answered from the other's generation).
"""

OLD_SHAPE_LINE = "* Both arms: **37/37 rows, 0 errors**, 16.6 / 18.4 min, p50 21.4 s / 22.0 s.\n"

LC_NOTE = """
Not attributed here, deliberately: the length-controlled gap (-12.6 pp) contains
the two degraded rows above (B's `rg_037` is all-False on both passes) and cutting
B's longer answers removes more text than it removes from A's, so the pass moves
which criteria are at risk as well as how many. It is reported because the round's
instrument exists to report it, not because this gate can price it.
"""

LC_ANCHOR = "| B (ON) | 93.33 | 42.96 | 91.89 | 40.54 | 100.0 | 28/37 |\n"
GUARD = "the arms differ by the flag alone"


def main() -> int:
    text = DOC.read_text(encoding="utf-8")

    # 1. collapse the duplication the first version introduced
    if text.count(SHAPE_NOTE) == 2:
        text = text.replace(SHAPE_NOTE, "", 1)
        print("repaired: duplicated request-shape note")
    assert text.count(SHAPE_NOTE) <= 1, "unexpected number of shape notes"

    # 2. insert it if absent (case-insensitive guard: the note starts uppercase)
    if GUARD in text.lower():
        print("already applied: request-shape note")
    else:
        assert text.count(OLD_SHAPE_LINE) == 1, "shape line not unique"
        text = text.replace(OLD_SHAPE_LINE, SHAPE_NOTE + OLD_SHAPE_LINE, 1)
        print("patched: request-shape note")

    # 3. the length-controlled caveat
    if "not attributed here, deliberately" in text.lower():
        print("already applied: LC caveat")
    else:
        assert text.count(LC_ANCHOR) == 1, "LC table anchor not unique"
        text = text.replace(LC_ANCHOR, LC_ANCHOR + LC_NOTE, 1)
        print("patched: LC caveat")

    DOC.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
