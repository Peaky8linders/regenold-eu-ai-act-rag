"""Summarize Easy and Hard mode scores and min-max ranges from official JSON results."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = [
    ("EASY", REPO / "docs/measurements/r388/score-r388-remediated-easy-easy.json"),
    ("HARD", REPO / "docs/measurements/r388/score-r388-remediated-hard-hard.json"),
]

for mode, path in RESULTS:
    if not path.exists():
        print(f"{mode}: {path.name} not found")
        continue
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    rows = d.get("rows", [])
    mins = [r.get("_criteria_rate_min", r["n_criteria_passed"] / max(1, len(r["criteria"]))) for r in rows if r.get("criteria")]
    maxs = [r.get("_criteria_rate_max", r["n_criteria_passed"] / max(1, len(r["criteria"]))) for r in rows if r.get("criteria")]
    means = [r["n_criteria_passed"] / max(1, len(r["criteria"])) for r in rows if r.get("criteria")]

    axes = d.get("axes", {})
    ans_l = axes.get("ans_correctness_loose", 0.0)
    ans_s = axes.get("ans_correctness_strict", 0.0)
    ans_c = axes.get("ans_conciseness", 0.0)
    ref_l = axes.get("ref_correctness_loose", 0.0)
    ref_s = axes.get("ref_correctness_strict", 0.0)
    ref_c = axes.get("ref_conciseness", 0.0)
    tone = axes.get("regulatory_tone", 0.0)
    speed = axes.get("resp_speed", 0.0)
    ov = axes.get("overall", 0.0)

    min_l = 100 * sum(mins) / max(1, len(mins))
    max_l = 100 * sum(maxs) / max(1, len(maxs))

    print(f"=== {mode} MODE (n={len(rows)}) ===")
    print(f"  Ans Cor L:       {ans_l:5.1f}%  [{min_l:.1f}% - {max_l:.1f}%]")
    print(f"  Ans Cor S:       {ans_s:5.1f}%")
    print(f"  Ans Conciseness: {ans_c:5.1f}%")
    print(f"  Ref Cor L:       {ref_l:5.1f}%")
    print(f"  Ref Cor S:       {ref_s:5.1f}%")
    print(f"  Ref Conciseness: {ref_c:5.1f}%")
    print(f"  Regulatory Tone: {tone:5.1f}%")
    print(f"  Resp Speed:      {speed:5.1f}%")
    print(f"  OVERALL (Geo):   {ov:5.1f}%")
    print()
