"""R412 — paired-gate scorer with explicit VALID-ROW selection.

WHY THIS IS NOT A ONE-LINER OVER THE CHECKPOINT FILES
-----------------------------------------------------
The harness opens each arm's ``.ckpt.jsonl`` with ``"a"`` (append), so a re-run
of the same ``--label`` lands *after* whatever a previous run of that label
wrote. That matters because a previous attempt of this exact label is VOID:

    REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN rewrites the system slot only on the
    WRAPPER leg of Stage-2. When the Claude-Max wrapper is down the engine falls
    back to Bedrock, and ``_bedrock_complete_for_graph_rag`` always receives the
    full ``system``. Both arms are then byte-identical and the A/B can only
    measure sampling noise.

The void-ness is a MEASUREMENT, not an assertion: the run's log carried **189**
``bedrock_auto_fallback`` lines, while the valid re-run carries **0**.

So this scorer takes the LAST ``--n`` rows of each arm (the appended re-run)
rather than "all rows", and it prints the row id lists so the selection is
auditable.

    .venv/Scripts/python.exe docs/measurements/r412/score_paired_gate.py \
        --label r411-fullsys-singleturn-easy --n 95
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[3] / "evals" / "bench" / "results"

AXES = ("ref_loose", "ref_strict", "ref_conc", "kw_recall", "tone")


def _load(path: Path, n: int | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-n:] if n else rows


def _agg(rows: list[dict]) -> dict:
    out: dict[str, float | int | None] = {}
    for axis in AXES:
        vals = [
            r["scores"][axis]
            for r in rows
            if r.get("scores") and r["scores"].get(axis) is not None
        ]
        out[axis] = sum(vals) / len(vals) if vals else None
    out["gold_dropped_head"] = sum(
        int(r["scores"].get("gold_dropped_head") or 0) for r in rows if r.get("scores")
    )
    lat = sorted(r["latency_ms"] / 1000.0 for r in rows if r.get("latency_ms"))
    out["lat_p50"] = lat[len(lat) // 2] if lat else None
    out["lat_mean"] = sum(lat) / len(lat) if lat else None
    out["errors"] = sum(1 for r in rows if r.get("http_status") != 200)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument(
        "--n",
        type=int,
        default=None,
        help="take the LAST n rows of each arm (the appended valid re-run)",
    )
    ap.add_argument("--out", help="write the JSON verdict here")
    args = ap.parse_args()

    a_path = RESULTS / f"easyhard-{args.label}-A.ckpt.jsonl"
    b_path = RESULTS / f"easyhard-{args.label}-B.ckpt.jsonl"
    a_rows, b_rows = _load(a_path, args.n), _load(b_path, args.n)
    ids_a = [r["id"] for r in a_rows]
    ids_b = {r["id"] for r in b_rows}
    unpaired = sorted(set(ids_a) - ids_b)
    if unpaired:
        print(f"WARNING: {len(unpaired)} arm-A rows have no arm-B partner: {unpaired[:5]}")

    a, b = _agg(a_rows), _agg(b_rows)
    print(f"arm A rows={len(a_rows)} (last from {a_path.name})")
    print(f"arm B rows={len(b_rows)} (last from {b_path.name})")
    print(f"\n{'metric':18} {'A baseline':>12} {'B branch':>12} {'delta':>10}")
    for key in (*AXES, "gold_dropped_head", "lat_p50", "lat_mean", "errors"):
        va, vb = a[key], b[key]
        if isinstance(va, float):
            print(f"{key:18} {va:12.4f} {vb:12.4f} {vb - va:+10.4f}")
        else:
            print(f"{key:18} {va:12} {vb:12} {vb - va:+10}")

    by_id_b = {r["id"]: r for r in b_rows}
    faster = sum(
        1
        for r in a_rows
        if r["id"] in by_id_b
        and (by_id_b[r["id"]].get("latency_ms") or 1e18) < (r.get("latency_ms") or 0)
    )
    print(f"\nrows where B is faster: {faster}/{len(a_rows)}")

    verdict = {
        "label": args.label,
        "n": args.n,
        "arm_a": a,
        "arm_b": b,
        "faster_rows": faster,
        "unpaired": unpaired,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
