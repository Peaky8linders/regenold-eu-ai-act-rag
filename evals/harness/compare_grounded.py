"""Paired comparison of two grounded-judge sidecars.

R313 — written because R312's ad-hoc comparison silently reported
``omission_present 0 / fabrication_present 0`` for BOTH arms: those fields
belong to ``evals.judge.legal_v2``, not to ``evals.judge.grounded``, so absent
was rendered as zero and a real conclusion was almost drawn from it. This script
therefore HARD-FAILS on an unknown or missing field instead of defaulting it.

Usage::

    python -m evals.harness.compare_grounded \
        --a evals/bench/results/grounded-<a>.json \
        --b evals/bench/results/grounded-<b>.json

Reports, per axis: both pass-rates, the delta, the per-row win/loss/tie split,
and a two-sided sign-test p-value over the DECISIVE rows. Rows are paired by
``id`` and any row missing from either arm is dropped (and counted).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# The grounded judge's schema. Anything else is a bug in the caller's
# expectations, not a zero.
AXES = ("answer_correctness", "reference_correctness", "citation_faithfulness")
_REQUIRED = {
    "answer_correctness": ("verdict", "correct", "incorrect", "unsupported", "missing"),
    "reference_correctness": ("verdict", "precision", "recall", "wrong_refs", "missing_refs"),
    "citation_faithfulness": ("verdict", "faithful", "mismatched"),
}


def _sign_test(wins: int, losses: int) -> float:
    """Two-sided exact binomial sign test at p=0.5 over decisive rows."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def _load(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, dict] = {}
    for row in data.get("rows", []):
        verdicts = row.get("verdicts") or {}
        for axis in AXES:
            block = verdicts.get(axis)
            if block is None:
                raise SystemExit(
                    f"{path.name}: row {row.get('id')!r} has no {axis!r} block. "
                    "Refusing to treat an absent axis as a value."
                )
            for field in _REQUIRED[axis]:
                if field not in block:
                    raise SystemExit(
                        f"{path.name}: row {row.get('id')!r} {axis!r} is missing "
                        f"{field!r}. The grounded schema changed; fix this script "
                        "rather than defaulting the field."
                    )
        rows[str(row.get("id"))] = row
    return rows


def _passed(row: dict, axis: str) -> bool:
    return row["verdicts"][axis].get("verdict") == "pass"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, type=Path, help="baseline sidecar")
    ap.add_argument("--b", required=True, type=Path, help="branch sidecar")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args()

    a_rows, b_rows = _load(args.a), _load(args.b)
    shared = [k for k in a_rows if k in b_rows]
    dropped = (len(a_rows) - len(shared)) + (len(b_rows) - len(shared))

    print(f"paired rows: {len(shared)}   dropped (present in only one arm): {dropped}")
    print(f"  A = {args.label_a}   ({args.a.name})")
    print(f"  B = {args.label_b}   ({args.b.name})\n")

    print(f"{'axis':<24} {'A':>7} {'B':>7} {'delta':>8}   {'B>A':>4} {'A>B':>4} {'tie':>4}  {'p':>6}")
    print("-" * 78)
    for axis in AXES:
        a_pass = sum(_passed(a_rows[k], axis) for k in shared)
        b_pass = sum(_passed(b_rows[k], axis) for k in shared)
        wins = sum(
            1 for k in shared if _passed(b_rows[k], axis) and not _passed(a_rows[k], axis)
        )
        losses = sum(
            1 for k in shared if _passed(a_rows[k], axis) and not _passed(b_rows[k], axis)
        )
        ties = len(shared) - wins - losses
        ra, rb = a_pass / len(shared), b_pass / len(shared)
        print(
            f"{axis:<24} {ra:7.3f} {rb:7.3f} {rb - ra:+8.3f}   "
            f"{wins:4d} {losses:4d} {ties:4d}  {_sign_test(wins, losses):6.3f}"
        )

    # Continuous companions — far lower variance than a binary gate at n=40.
    print()
    for name, axis, num, den in (
        ("mean factual score", "answer_correctness", "correct",
         ("correct", "incorrect", "unsupported", "missing")),
    ):
        for label, rows in ((args.label_a, a_rows), (args.label_b, b_rows)):
            vals = []
            for k in shared:
                blk = rows[k]["verdicts"][axis]
                total = sum(float(blk.get(f, 0) or 0) for f in den)
                if total > 0:
                    vals.append(float(blk.get(num, 0) or 0) / total)
            if vals:
                print(f"{name:<24} {label:<14} {sum(vals) / len(vals):.4f}  (n={len(vals)})")

    for label, rows in ((args.label_a, a_rows), (args.label_b, b_rows)):
        precs, recs = [], []
        for k in shared:
            blk = rows[k]["verdicts"]["reference_correctness"]
            precs.append(float(blk.get("precision", 0) or 0))
            recs.append(float(blk.get("recall", 0) or 0))
        print(
            f"{'ref precision / recall':<24} {label:<14} "
            f"{sum(precs) / len(precs):.4f} / {sum(recs) / len(recs):.4f}"
        )

    print("\nPer-row citation_faithfulness losses (B fails where A passed):")
    any_loss = False
    for k in shared:
        if _passed(a_rows[k], "citation_faithfulness") and not _passed(
            b_rows[k], "citation_faithfulness"
        ):
            any_loss = True
            fm = b_rows[k]["verdicts"]["citation_faithfulness"].get("failure_mode")
            print(f"  {k}: {fm}")
    if not any_loss:
        print("  (none)")

    print("\nPer-row answer_correctness flips:")
    for k in shared:
        pa, pb = _passed(a_rows[k], "answer_correctness"), _passed(b_rows[k], "answer_correctness")
        if pa != pb:
            side = "B WIN " if pb else "B LOSS"
            fm = (a_rows[k] if pb else b_rows[k])["verdicts"]["answer_correctness"].get("failure_mode")
            print(f"  {side} {k}: {fm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
