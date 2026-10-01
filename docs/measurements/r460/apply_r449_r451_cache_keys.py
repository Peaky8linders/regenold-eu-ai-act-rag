"""R460 — register the transplanted R449/R450/R451 knobs in ``_engine_cache_key``.

origin/main does not key any of them. Unkeyed, the R451 in-process weight sweep
would serve arm A's cached response to every later cell and report a flat
"weights do not matter" for the whole grid — the R263.2 / R288.1 cache-poisoning
shape the R451 tests exist to catch. Exact asserted byte replacement, idempotent.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROUTES = REPO / "app" / "routes" / "regenold.py"

ANCHOR = '            "REGENOLD_STAGE2_ALLOW_NON_OPUS",\r\n'

BLOCK = (
    '            # R460 - transplant of the R449/R450/R451 contextual-field knobs.\r\n'
    '            # Each changes the BM25 admission ranking, hence query.entities,\r\n'
    '            # hence the wire references and the cached answer. The R451\r\n'
    '            # harness sweeps them IN-PROCESS, so an unkeyed knob would serve\r\n'
    '            # arm A cached response to every later cell and read as "weights\r\n'
    '            # do not matter". R263.2 / R288.1 doctrine.\r\n'
    '            "REGENOLD_CONTEXTUAL_FIELDS",\r\n'
    '            "REGENOLD_EMIT_ALLOC",\r\n'
    '            "REGENOLD_EMIT_SPLIT_TOP",\r\n'
    '            "REGENOLD_FIELD_WEIGHT_TITLE",\r\n'
    '            "REGENOLD_FIELD_WEIGHT_BODY",\r\n'
    '            "REGENOLD_FIELD_B_TITLE",\r\n'
    '            "REGENOLD_FIELD_B_BODY",\r\n'
)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = ROUTES.read_bytes()
    if b'"REGENOLD_FIELD_B_BODY"' in data:
        print("already applied")
        return
    anchor_b = ANCHOR.encode("utf-8")
    count = data.count(anchor_b)
    if count != 1:
        raise SystemExit(f"REFUSING: anchor matched {count} times (expected 1)")
    ROUTES.write_bytes(data.replace(anchor_b, (ANCHOR + BLOCK).encode("utf-8"), 1))
    print("patched: regenold.py")


if __name__ == "__main__":
    main()
