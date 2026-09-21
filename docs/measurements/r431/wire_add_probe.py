"""R431 — does ADDING the limb the answer and the question both engage move the board?

Arms, on identical recorded input (the R419 full hard board, 110 rows, plus every
strided hard capture), scored with the REAL ``evals.official.rubric``:

* ``off`` — ``_ground_wire_subpoints`` with the ADD disabled: today's shipped board
  (R425 substitution + R429 depth completion).
* ``add`` — the same pass with ``REGENOLD_GROUND_WIRE_ADD=1``.

The ADD only ever appends a coordinate whose PARENT is already on the wire, so the
folded head set cannot change. That is asserted PER ROW here rather than argued, and
it is what makes Ref. Correctness (Loose) and Hard Rule #8 invariant by
construction. Ref. Correctness (Strict) is asserted NON-DECREASING per row (recall
at full grain can only gain). Ref. Conciseness is a pure count ratio and is the one
axis this can cost — so it is reported, not hidden.

The window where the lever is even reachable is 18 of the 110 rows, which are the
rows on which it fires at all. The board column is what it does to the whole board.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r431.wire_add_probe
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("REGENOLD_SKIP_DOTENV", "1")

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

BOARD = "official-r419-hard-hard.ckpt.jsonl"
EXTRA = (
    "official-r424-*-hard*.ckpt.jsonl",
    "official-r423-need4-*-hard*.ckpt.jsonl",
)
FLAG = "REGENOLD_GROUND_WIRE_ADD"


def _rows() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(RESULTS.glob(BOARD)):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append((f"{path.stem}:{json.loads(line)['id']}", json.loads(line)))
    for pat in EXTRA:
        for path in sorted(RESULTS.glob(pat)):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append((f"{path.stem}:{json.loads(line)['id']}", json.loads(line)))
    return out


def _graded_pair(row: dict[str, Any]) -> tuple[str, list[str]]:
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
        )
    return row.get("pred_answer") or "", [str(x) for x in (row.get("pred_refs") or [])]


def main() -> int:
    # Imported AFTER the flag env is set, so each arm re-reads it per call (the
    # helpers are env readers, not module constants — no reload needed).
    from app.routes import regenold as R  # noqa: PLC0415
    from evals.official.rubric import (  # noqa: PLC0415
        ref_head,
        reference_conciseness,
        reference_correctness_loose,
        reference_correctness_strict,
    )

    gold: dict[str, Any] = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g

    axes = ("loose", "strict", "conc")
    # per arm: per-row values; and a board-only view restricted to the R419 board.
    per_arm: dict[str, dict[str, list[float]]] = {
        "off": {a: [] for a in axes},
        "add": {a: [] for a in axes},
    }
    board_only: dict[str, dict[str, list[float]]] = {
        "off": {a: [] for a in axes},
        "add": {a: [] for a in axes},
    }
    head_violations = 0
    strict_regressions = 0
    rows_fired = 0
    additions = 0
    additions_gold = 0
    count_deltas: list[int] = []
    examples: list[str] = []

    for key, row in _rows():
        rid = str(row.get("id"))
        if rid not in gold:
            continue
        answer, refs = _graded_pair(row)
        if not refs:
            continue
        question = str(row.get("question") or "")
        expected = [str(x) for x in gold[rid]["expected_refs"]]

        os.environ[FLAG] = "0"
        base = R._ground_wire_subpoints(answer, list(refs), question)
        os.environ[FLAG] = "1"
        wire = R._ground_wire_subpoints(answer, list(refs), question)

        # What the ADD itself contributed: everything in `wire` that the
        # substitution-only pass did not produce. `base` is today's board.
        remaining = list(base)
        extra: list[str] = []
        for ref in wire:
            if ref in remaining:
                remaining.remove(ref)
            else:
                extra.append(ref)

        values = {}
        for arm, refs_arm in (("off", base), ("add", wire)):
            values[arm] = {
                "loose": reference_correctness_loose(refs_arm, expected) or 0.0,
                "strict": reference_correctness_strict(refs_arm, expected) or 0.0,
                "conc": reference_conciseness(refs_arm, expected) or 0.0,
                "refs": refs_arm,
            }
        for a in axes:
            per_arm["off"][a].append(values["off"][a])
            per_arm["add"][a].append(values["add"][a])
            if key.startswith(BOARD.split(".")[0]):
                board_only["off"][a].append(values["off"][a])
                board_only["add"][a].append(values["add"][a])

        if extra:
            rows_fired += 1
            additions += len(extra)
            additions_gold += sum(
                1
                for x in extra
                if any(
                    x.lower() == e.lower() or x.lower().startswith(e.lower() + ".")
                    for e in expected
                )
            )
            if len(examples) < 10:
                examples.append(f"  {key} {base} -> {wire}  (added {extra})")

        # The two construction guarantees, asserted per row.
        #
        # The head invariant is a SET invariant, not a multiset one, and that is
        # not a convenience: `reference_correctness_loose` reads
        # `set(_heads(pred))`, so a second reference under a head already present
        # cannot move the axis. Asserting multiset equality would flag every
        # correct ADD as a violation (measured: 53 such false violations before
        # this assertion was scoped to what the axis actually reads).
        if {ref_head(r) for r in wire} != {ref_head(r) for r in base}:
            head_violations += 1
        if values["add"]["strict"] < values["off"]["strict"] - 1e-9:
            strict_regressions += 1
        count_deltas.append(len(extra))

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    print(f"rows scored          : {len(per_arm['off']['loose'])}")
    print(f"rows the ADD fired on: {rows_fired}")
    print(f"coordinates added    : {additions}  (gold {additions_gold}, "
          f"precision {additions_gold / additions * 100 if additions else 0:.1f}%)")
    print()
    print("CONSTRUCTION GUARANTEES (asserted per row, not argued):")
    print(f"  folded-head-SET violations      : {head_violations}")
    print(f"  Ref. Strict regressions         : {strict_regressions}")
    print(
        f"  max refs added on any row       : {max(count_deltas) if count_deltas else 0}"
        f"  (cap {max(0, min(6, int(os.getenv('REGENOLD_GROUND_WIRE_ADD_MAX', '2') or 2)))})"
    )
    print()
    print(f"{'axis':8}{'off':>9}{'add':>9}{'delta':>9}")
    for a in axes:
        offs, adds = _mean(per_arm["off"][a]), _mean(per_arm["add"][a])
        print(f"{a:8}{offs * 100:9.2f}{adds * 100:9.2f}{(adds - offs) * 100:+9.2f}")
    if board_only["off"]["loose"]:
        print()
        print("R419 BOARD ONLY (the 110-row benchmark):")
        for a in axes:
            offs, adds = _mean(board_only["off"][a]), _mean(board_only["add"][a])
            print(f"  {a:6}{offs * 100:9.2f}{adds * 100:9.2f}{(adds - offs) * 100:+9.2f}")
    print()
    print("examples:")
    for line in examples:
        print(line)
    return 0 if not (head_violations or strict_regressions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
