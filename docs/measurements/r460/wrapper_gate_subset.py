"""R460 wrapper confirmation -- is the regression an artifact of the transport split?

Arm B hit the wrapper's degenerate-completion path more often than arm A (17 vs
5 events, 8 vs 2 Bedrock fallback ATTEMPTS). Because the graded (post-pushback)
turn's leg is recorded per row, the confound is testable rather than merely
mentionable: recompute the paired deltas on the rows whose graded turn was
polished by the tunnel PRIMARY in BOTH arms.

Answer correctness uses the rubric's own predicates on the recorded per-criterion
booleans; the conciseness axes are the rubric's own one-sided ratios -- reference
divided by candidate (`min(1, len(reference)/len(candidate))`), so an answer
SHORTER than the reference is not penalised -- taken from the recorded char and
ref counts.

Run (module form, so the WORKTREE's evals/ is imported):
    ../../.venv/Scripts/python.exe -m docs.measurements.r460.wrapper_gate_subset
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "evals" / "bench" / "results"
SCORES = REPO / "docs" / "measurements" / "r388"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ARMS = {"A (OFF)": "r460-tunnel-off-s3", "B (ON)": "r460-tunnel-on-s3"}


def _leg(label: str) -> dict[str, str]:
    path = RESULTS / f"official-{label}-hard.ckpt.jsonl"
    return {
        r["id"]: str((r.get("provenance") or {}).get("stage2_served_by") or "")
        for r in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _rows(label: str) -> dict[str, dict]:
    path = SCORES / f"score-{label}-hard.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"]: r for r in data["rows"]}


def _conciseness(numerator: int | None, denominator: int | None) -> float:
    """``min(1, numerator/denominator)`` in percent -- the rubric's own form.

    The numerator is the KEY's size (reference chars / expected refs) and the
    denominator the ARM's size (answer chars / provided refs); swapping them
    inflates the axis, which this docstring exists to prevent.
    """
    if not numerator or not denominator:
        return 0.0
    return 100.0 * min(1.0, numerator / denominator)


def main() -> int:
    import evals.official.rubric as rubric  # noqa: PLC0415

    legs = {k: _leg(v) for k, v in ARMS.items()}
    rows = {k: _rows(v) for k, v in ARMS.items()}
    shared = sorted(set(rows["A (OFF)"]) & set(rows["B (ON)"]))
    a_leg, b_leg = legs["A (OFF)"], legs["B (ON)"]

    # Sanity: the recomputation must reproduce the payload's own axis, or the
    # subset numbers below are not comparable to the board.
    for arm, label in ARMS.items():
        vals = [
            _conciseness(r.get("reference_chars"), r.get("answer_chars"))
            for r in rows[arm].values()
        ]
        board = {
            "A (OFF)": 82.32,
            "B (ON)": 77.84,
        }[arm]
        got = sum(vals) / len(vals)
        print(f"recompute check {arm}: {got:.2f} vs board ans_conc {board:.2f}")
        assert abs(got - board) < 0.05, "recomputation drifted from the scored axis"

    subsets = {
        "all rows": lambda i: True,
        "graded turn PRIMARY in BOTH arms": lambda i: a_leg.get(i) == b_leg.get(i) == "primary",
        "same leg label in both arms": lambda i: a_leg.get(i) == b_leg.get(i),
    }
    ks = ["ans_loose", "ans_strict", "ans_conc", "ref_conc", "ans_chars", "refs"]

    def axes(r: dict) -> dict[str, float]:
        crit = [bool(x) for x in (r.get("criteria") or [])]
        return {
            "ans_loose": rubric.answer_correctness_loose([crit]) * 100.0,
            "ans_strict": rubric.answer_correctness_strict([crit]) * 100.0,
            "ans_conc": _conciseness(r.get("reference_chars"), r.get("answer_chars")),
            "ref_conc": _conciseness(len(r.get("expected_refs") or []), len(r.get("refs") or [])),
            "ans_chars": float(r.get("answer_chars") or 0),
            "refs": float(len(r.get("refs") or [])),
        }

    for name, keep in subsets.items():
        ids = [i for i in shared if keep(i)]
        if not ids:
            continue
        print(f"\n== {name}  (n={len(ids)})")
        aa: dict[str, list[float]] = {k: [] for k in ks}
        bb: dict[str, list[float]] = {k: [] for k in ks}
        for i in ids:
            x, y = axes(rows["A (OFF)"][i]), axes(rows["B (ON)"][i])
            for k in ks:
                aa[k].append(x[k])
                bb[k].append(y[k])
        for k in ks:
            ma, mb = sum(aa[k]) / len(ids), sum(bb[k]) / len(ids)
            print(f"  {k:<10} A={ma:9.2f} B={mb:9.2f} delta={mb - ma:+8.2f}")

    for arm in ARMS:
        lost = sorted(
            i
            for i in shared
            if {str(e).split(".")[0] for e in rows[arm][i].get("expected_refs") or []}
            - {str(r).split(".")[0] for r in rows[arm][i].get("refs") or []}
        )
        print(f"rows where {arm} misses a gold head: {len(lost)} {lost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
