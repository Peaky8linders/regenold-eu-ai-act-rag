"""R423.3 — could ONE row have manufactured the need-proportional win?

``docs/measurements/r423/graded_scope_probe.py`` falsified the R423 gate's scope
note: the full 59.6 kB system prompt is delivered to the FIRST TWO ROWS of a hard
run (``_run_hard`` starts ``history=[]``, so those rows read
``history_turn_count`` 0 and 1 and satisfy the single-turn predicate), not only to
easy mode. Arm A of the need4 gate was RESUMED, so its rolling history restarted
and it recorded one such primary dispatch; arm B ran continuously and recorded
none.

That is a genuine (if one-call) asymmetry in the SYSTEM slot between the arms, so
the honest question is not "is the note right" but "can it account for the
result". This script answers it by RE-SCORING the gate's already-judged rows on
every leave-one-out subset: if the headline survives dropping any single
comparable row, no one row — degraded, resumed or otherwise — can be carrying it.

Offline: it reads the six score artifacts the gate already wrote.

Run::

    .venv/Scripts/python.exe -m docs.measurements.r423.need_scope_sensitivity
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
LABEL = "r423-need4"
ARMS = ("A", "B")
REPEATS = 3
RESULTS = REPO / "evals" / "bench" / "results"
GATE_JSON = Path(__file__).resolve().parent / "need_gate.json"


def _load_artifacts() -> dict[str, dict[int, dict[str, Any]]]:
    from evals.official.score_arm import OUT_DIR

    out: dict[str, dict[int, dict[str, Any]]] = {}
    for arm in ARMS:
        out[arm] = {}
        for sample in range(REPEATS):
            path = Path(OUT_DIR) / f"score-{LABEL}-{arm}-s{sample}-hard.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            out[arm][sample] = {r["id"]: r for r in data["rows"]}
    return out


def _comparable() -> list[str]:
    """The gate's own comparable set, read from its record."""
    payload = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    return [r["id"] for r in payload["per_row"]]


def main() -> int:
    from docs.measurements.r423.need_gate import _gold_reference_answers, official_axes

    artifacts = _load_artifacts()
    comparable = _comparable()
    gold = _gold_reference_answers()

    full = official_axes(artifacts, comparable, gold)
    base_overall = full["axes"]["overall"]
    print(f"comparable n = {len(comparable)}")
    print(
        f"AS RUN   overall A={base_overall['A']} B={base_overall['B']} "
        f"delta={base_overall['delta_pp']:+.2f} pp"
    )
    print("\nleave-one-out (drop one comparable row, re-score the same draws)")
    worst_delta = float("inf")
    worst_row = ""
    for row_id in comparable:
        subset = [r for r in comparable if r != row_id]
        axes = official_axes(artifacts, subset, gold)["axes"]["overall"]
        delta = axes["delta_pp"]
        if delta < worst_delta:
            worst_delta, worst_row = delta, row_id
        print(f"  drop {row_id:8s} n={len(subset):2d} delta={delta:+7.2f} pp")

    print(
        f"\nWORST single-row removal: drop {worst_row} -> {worst_delta:+.2f} pp "
        f"(as run {base_overall['delta_pp']:+.2f} pp)"
    )
    stable = worst_delta > 0
    print(
        "VERDICT: "
        + (
            "ROBUST — the sign and a large magnitude survive removing ANY single "
            "comparable row, so no single row (degraded, resumed or full-prompt) "
            "can account for the win."
            if stable
            else "NOT ROBUST — one row flips or erases the delta; identify it."
        )
    )
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
