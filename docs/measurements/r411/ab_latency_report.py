"""R411 — per-arm latency + reference summary from `easyhard_ab` checkpoints.

Why this exists separately from the harness report: `easyhard_ab` aggregates the
three *reference* axes and prints a p50 that it explicitly marks as confounded in
A/B mode. `Resp. Speed` is 1 of the 8 official geometric-mean axes and is a plain
mean of `100 - latency_s`, so the lever that moves it needs a clean, auditable
per-arm latency read — from the machine-written checkpoint, not from a scraped
log.

    .venv/Scripts/python.exe docs/measurements/r411/ab_latency_report.py \
        easyhard-r411-fullsys-easy
    # or with a pair of explicit paths
    .venv/Scripts/python.exe docs/measurements/r411/ab_latency_report.py \
        docs/measurements/r411/ckpt-r411-probe-n12-armA.jsonl \
        docs/measurements/r411/ckpt-r411-probe-n12-armB.jsonl
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "evals" / "bench" / "results"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def graded_latency_s(row: dict) -> float | None:
    """Latency of the GRADED response — mirrors evals/official/score_arm.py.

    In hard mode the checkpoint's ``latency_ms`` is turn 1 PLUS the pushback turn,
    while only the pushback answer is graded. Prefer the per-turn field.
    """
    if "pushback_latency_ms" in row or "turn1_latency_ms" in row:
        value = row.get("pushback_latency_ms") if row.get("turn1_answer") else row.get("turn1_latency_ms")
    else:
        value = row.get("latency_ms")
    return (float(value) / 1000.0) if value else None


def summarise(label: str, rows: list[dict]) -> dict:
    lat = [s for s in (graded_latency_s(r) for r in rows) if s is not None]
    # ``pred_refs`` is the checkpoint's name for the wire reference list.
    refs = [len(r.get("pred_refs") or r.get("references") or []) for r in rows]
    chars = [len(r.get("answer") or r.get("pred_answer") or "") for r in rows]
    return {
        "label": label,
        "n": len(rows),
        "lat_mean": statistics.fmean(lat) if lat else 0.0,
        "lat_p50": statistics.median(lat) if lat else 0.0,
        "lat_max": max(lat) if lat else 0.0,
        "speed": statistics.fmean([max(0.0, 100.0 - s) for s in lat]) if lat else 0.0,
        "refs": statistics.fmean(refs) if refs else 0.0,
        "chars": statistics.fmean(chars) if chars else 0.0,
    }


def _fmt(a: dict, b: dict) -> None:
    print(f"{'metric':<14}{'A (baseline)':>14}{'B (branch)':>14}{'delta':>12}")
    print("-" * 54)
    for key, name, unit in (
        ("lat_mean", "lat mean s", "s"),
        ("lat_p50", "lat p50 s", "s"),
        ("lat_max", "lat max s", "s"),
        ("speed", "resp_speed", "pp"),
        ("refs", "refs/row", ""),
        ("chars", "answer chars", ""),
    ):
        av, bv = a[key], b[key]
        print(f"{name:<14}{av:>14.2f}{bv:>14.2f}{bv - av:>+11.2f}{unit}")
    print()
    print(f"n = {a['n']} (A) / {b['n']} (B)")


def main() -> int:
    args = sys.argv[1:]
    if len(args) == 2 and args[0].endswith(".jsonl"):
        a_path, b_path = Path(args[0]), Path(args[1])
    elif len(args) == 1:
        a_path = RESULTS / f"{args[0]}-A.ckpt.jsonl"
        b_path = RESULTS / f"{args[0]}-B.ckpt.jsonl"
    else:
        print(__doc__)
        return 2

    a_rows, b_rows = load(a_path), load(b_path)
    if not a_rows or not b_rows:
        print(f"missing checkpoint data\n  A: {a_path} ({len(a_rows)} rows)\n  B: {b_path} ({len(b_rows)} rows)")
        return 1

    a, b = summarise("A", a_rows), summarise("B", b_rows)
    _fmt(a, b)

    # Paired read: the honest per-row comparison.
    a_by = {r.get("id"): r for r in a_rows}
    paired = [(a_by[r["id"]], r) for r in b_rows if r.get("id") in a_by]
    faster = slower = 0
    for ra, rb in paired:
        la, lb = graded_latency_s(ra), graded_latency_s(rb)
        if la is None or lb is None:
            continue
        if lb < la:
            faster += 1
        elif lb > la:
            slower += 1
    print(f"paired rows: {len(paired)}   branch faster: {faster}   slower: {slower}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
