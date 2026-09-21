"""R430 — compose the shipped levers onto the last full board, and label the seams.

The R419 live hard board (`score-r419-hard-hard.json`, n=110, 2026-09-15) is the
last measurement of the WHOLE benchmark. Every lever shipped since was gated on a
STRIDED HARD SUBSET, so no single artifact holds today's board. This file composes
them and is explicit about what that composition is and is not:

* It IS arithmetic over per-lever deltas that each came from a paired, gated run
  against the real ``evals.official.rubric`` on real draws.
* It is NOT a re-run of the 110 rows. Every delta here was measured on its own
  comparable subset (27–28 strided hard rows, per-row medians over 3 independent
  generations), and applying a subset delta to the full board ASSUMES it
  transports. The ``reach`` column states that assumption per lever; the
  conservative column removes it.

Deliberately conservative choices, so the number can only be too low:

* where a lever has both an offline paired figure and a live figure, the LIVE one
  is used (R429: +3.70 live against +7.13 offline on recorded draws);
* a lever is counted on an axis only if that axis was actually scored on the gate
  that shipped it, and its delta is taken as printed rather than re-weighted;
* the harness-fidelity correction (R424) is listed but NOT counted, because it
  improves the fidelity of the measurement rather than the system;
* no composition is applied to the single-turn (easy) split, which has no fresh
  full board — its last measurement is R390 and is reported as stale.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r430.projected_board
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

BOARD = REPO / "docs" / "measurements" / "r388" / "score-r419-hard-hard.json"

AXES = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
)

#: The 2026 frontier baseline as printed by the evaluator (hard mode).
FRONTIER = {
    "ans_correctness_loose": 92.0,
    "ans_correctness_strict": 84.8,
    "ans_conciseness": 71.8,
    "ref_correctness_loose": 94.6,
    "ref_correctness_strict": 74.1,
    "ref_conciseness": 58.5,
    "regulatory_tone": 100.0,
    "resp_speed": 86.7,
}

#: lever -> (flag, default, per-axis delta in pp, the population it was measured
#: on, and the artifact that carries it). A lever is only listed on an axis the
#: gate that shipped it actually scored.
LEVERS: tuple[dict[str, object], ...] = (
    {
        "round": "R420",
        "name": "Pushback prior-answer floor (never ship a thinner answer than the one already given)",
        "flag": "REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR",
        "population": "the 4 deterministic-leg rows of the R419 board, re-judged",
        "artifact": "docs/measurements/r419/CHECKPOINT.md §4",
        "delta": {"ans_correctness_loose": 2.13, "ans_correctness_strict": 0.91},
    },
    {
        "round": "R423.2",
        "name": "Need-proportional answer contract (answer length follows the engaged criteria)",
        "flag": "REGENOLD_NEED_PROPORTIONAL_CONTRACT",
        "population": "28 comparable strided hard rows, per-row medians over 3 generations",
        "artifact": "docs/measurements/r423/CHECKPOINT-r4231.md §9",
        "delta": {
            "ans_conciseness": 38.86,
            "ref_correctness_loose": 3.70,
            "ref_correctness_strict": 5.56,
            "ref_conciseness": 12.80,
            "resp_speed": 10.77,
        },
    },
    {
        "round": "R425",
        "name": "Wire limb grounded on the limb the prose names (sibling substitution)",
        "flag": "REGENOLD_GROUND_WIRE_SUBPOINTS",
        "population": "324 comparable row-samples of recorded hard draws",
        "artifact": "docs/measurements/r425/CHECKPOINT.md",
        "delta": {"ref_correctness_strict": 0.62},
    },
    {
        "round": "R429",
        "name": "Wire coordinate completed to the grain the prose names (depth completion)",
        "flag": "REGENOLD_GROUND_WIRE_DEPTH",
        "population": "27 comparable strided hard rows, 111 fresh live draws",
        "artifact": "docs/measurements/r429/gate-verdict.json",
        "delta": {"ref_correctness_strict": 3.70},
    },
)

#: Measured, but a change to the HARNESS rather than the system: reported, not counted.
FIDELITY = {
    "round": "R424",
    "name": "Fixed 9-turn synthetic preamble (hard-mode fidelity correction)",
    "delta": {
        "ans_conciseness": 1.86,
        "ref_correctness_loose": 1.79,
        "ref_correctness_strict": -3.57,
        "ref_conciseness": 1.86,
        "resp_speed": 0.42,
    },
    "artifact": "docs/measurements/r424/CHECKPOINT.md §6",
}


def _geomean(values: dict[str, float]) -> float:
    vals = [max(0.0, values[a]) for a in AXES]
    if any(v <= 0 for v in vals):
        return 0.0
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def main() -> int:
    board = json.loads(BOARD.read_text(encoding="utf-8"))["axes"]
    base = {a: float(board[a]) for a in AXES}

    composed = dict(base)
    counted: dict[str, list[str]] = {a: [] for a in AXES}
    for lever in LEVERS:
        for axis, delta in lever["delta"].items():  # type: ignore[union-attr]
            composed[axis] = min(100.0, composed[axis] + float(delta))
            counted[axis].append(f"{lever['round']} {float(delta):+.2f}")

    # Conservative: only the one lever whose population is the graded rows of the
    # board it moved (R420), i.e. the composition with no transport assumption.
    conservative = dict(base)
    for lever in LEVERS:
        if lever["round"] != "R420":
            continue
        for axis, delta in lever["delta"].items():  # type: ignore[union-attr]
            conservative[axis] = min(100.0, conservative[axis] + float(delta))

    b, c, k = _geomean(base), _geomean(composed), _geomean(conservative)
    print(f"R419 live hard board (n=110, 2026-09-15)   OVERALL {b:6.2f}")
    print(f"Composed projection (all shipped levers)   OVERALL {c:6.2f}   {c - b:+.2f} pp")
    print(f"Conservative (no transport assumption)     OVERALL {k:6.2f}   {k - b:+.2f} pp")
    print()
    hdr = f"{'axis':24}{'R419':>8}{'composed':>10}{'delta':>8}{'frontier':>10}{'gap':>8}   levers"
    print(hdr)
    print("-" * len(hdr))
    for a in AXES:
        gap = composed[a] - FRONTIER[a]
        print(
            f"{a:24}{base[a]:8.2f}{composed[a]:10.2f}{composed[a] - base[a]:+8.2f}"
            f"{FRONTIER[a]:10.1f}{gap:+8.2f}   {'; '.join(counted[a]) or '—'}"
        )
    print()
    won = [a for a in AXES if composed[a] >= FRONTIER[a] and base[a] < FRONTIER[a]]
    still = [a for a in AXES if composed[a] < FRONTIER[a]]
    print(f"axes that FLIP to at-or-above frontier: {', '.join(won) or 'none'}")
    print(f"axes still below frontier            : {', '.join(still) or 'none'}")
    print()
    print("NOT counted (harness fidelity, not a system gain):")
    for axis, delta in FIDELITY["delta"].items():  # type: ignore[union-attr]
        print(f"  {FIDELITY['round']} {axis:24} {float(delta):+6.2f}")
    fidelity = _geomean(
        {a: base[a] + float(FIDELITY["delta"].get(a, 0)) for a in AXES}  # type: ignore[union-attr]
    )
    print(f"  -> would move OVERALL by {fidelity - b:+.2f} pp")

    out = REPO / "docs" / "measurements" / "r430" / "PROJECTION.md"
    lines = [
        "# Composed board — R419 live board + every lever shipped since",
        "",
        "Generated by `docs/measurements/r430/projected_board.py`. Re-generated, not",
        "hand-edited, so the reports cannot drift from the arithmetic.",
        "",
        "| board | OVERALL (geometric mean of the eight axes) | vs R419 |",
        "| :-- | --: | --: |",
        f"| R419 live hard board (n=110, measured 2026-09-15) | {b:.2f} | — |",
        f"| **Composed projection (all shipped levers)** | **{c:.2f}** | **{c - b:+.2f} pp** |",
        f"| Conservative (no transport assumption, R420 only) | {k:.2f} | {k - b:+.2f} pp |",
        f"| 2026 frontier baseline (as printed) | {_geomean(FRONTIER):.2f} | {_geomean(FRONTIER) - b:+.2f} pp |",
        "",
        "## Per-axis",
        "",
        "| axis | R419 | composed | delta | frontier | gap | counted levers |",
        "| :-- | --: | --: | --: | --: | --: | :-- |",
    ]
    for a in AXES:
        gap = composed[a] - FRONTIER[a]
        lines.append(
            f"| `{a}` | {base[a]:.2f} | {composed[a]:.2f} | {composed[a] - base[a]:+.2f} | "
            f"{FRONTIER[a]:.1f} | {gap:+.2f} | {'; '.join(counted[a]) or '—'} |"
        )
    lines += [
        "",
        "## The levers, each with its own gate and population",
        "",
        "| round | lever | flag (default) | measured on | artifact |",
        "| :-- | :-- | :-- | :-- | :-- |",
    ]
    for lever in LEVERS:
        deltas = ", ".join(f"{a.split('_', 1)[-1]} {float(d):+.2f}" for a, d in lever["delta"].items())  # type: ignore[union-attr]
        lines.append(
            f"| {lever['round']} | {lever['name']} | `{lever['flag']}` (**1**) | "
            f"{lever['population']}<br>{deltas} | `{lever['artifact']}` |"
        )
    lines += [
        "",
        "## Reported but NOT counted",
        "",
        f"**{FIDELITY['round']} — {FIDELITY['name']}.** A change to the harness, not the",
        "system: it makes the measured modality a constant of the run instead of a",
        "function of a row's position. Counting it as an uplift would be dishonest, so it",
        f"is listed and excluded (it would move OVERALL by {fidelity - b:+.2f} pp). Source:",
        f"`{FIDELITY['artifact']}`.",
        "",
        "## What this is not",
        "",
        "It is not a re-run of the 110 rows. Each lever's delta came from its own",
        "comparable subset (27–28 strided hard rows, per-row medians over three",
        "independent generations), and applying a subset delta to the full board assumes",
        "it transports. The conservative row above removes that assumption and keeps only",
        "the one lever measured on the graded rows of the board it moved.",
        "",
        "The single-turn (easy) split has no fresh full board. Its last measurement is",
        "R390 and it is **stale** — the R412 full-system lever expects to move it",
        "(`ref_loose` +8.97, `ref_strict` +14.98, `ref_conc` +14.56, p50 latency",
        "−15.47 s on its own n=39 gate) and that is not reflected in any board here.",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {out.relative_to(REPO)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
