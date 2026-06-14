"""Adapt an R118 live sidecar (``live_<label>.json``) into a judge-ready
sidecar (``{"rows": [...]}``) consumable by ``evals.judge.runner``.

The judge's ``render()`` reads: question, expected_keywords, expected_refs,
predicted_answer, pred_refs. Our live rows store ``gold_refs`` (not
``expected_refs``) and don't carry ``expected_keywords`` inline, so we join
back to the ground-truth / scenario modules by id.

Usage:
  python -m evals.regenold.build_judge_input \
      --live .evalout/r118/live_r118-af.json \
      --out evals/bench/results/judge-input-r118-af.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _af_keywords() -> dict[str, list[str]]:
    from evals.regenold.antifragile_groundtruth import ANTIFRAGILE_GT
    return {qid: gt.get("expected_keywords", []) for qid, gt in ANTIFRAGILE_GT.items()}


def _medtech_keywords() -> dict[str, list[str]]:
    try:
        from evals.regenold.scenarios_medtech_multiturn_r118 import MEDTECH_MULTITURN
    except ImportError:
        return {}
    return {s["id"]: s.get("expected_keywords", []) for s in MEDTECH_MULTITURN}


def build(live_path: Path) -> list[dict]:
    data = json.loads(live_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    af_kw = _af_keywords()
    for r in data.get("antifragile_rows", []):
        rows.append({
            "id": r["id"],
            "category": "antifragile",
            "question": r.get("question", ""),
            "expected_refs": r.get("gold_refs", []),
            "expected_keywords": af_kw.get(r["id"], []),
            "predicted_answer": r.get("predicted_answer", ""),
            "pred_refs": r.get("pred_refs", []),
        })
    mt_kw = _medtech_keywords()
    for r in data.get("medtech_rows", []):
        rows.append({
            "id": r["id"],
            "category": r.get("domain", "medtech"),
            "question": r.get("final_question", ""),
            "expected_refs": r.get("expected_refs", []),
            "expected_keywords": mt_kw.get(r["id"], []),
            "predicted_answer": r.get("predicted_answer", ""),
            "pred_refs": r.get("pred_refs", []),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    rows = build(args.live)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out} with {len(rows)} judge rows")


if __name__ == "__main__":
    main()
