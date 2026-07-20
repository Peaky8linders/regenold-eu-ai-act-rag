"""Generate + store one arm's answers for grounded re-judging.

easyhard_ab / ab_judge don't persist the generated answers, so a grounded
re-judge of a specific env config needs the answers captured to a ckpt jsonl
(the shape evals.judge.grounded reads: id/category/pred_answer/pred_refs/gold_refs).

Usage (env carries the arm config; run under the prod Stage-2 env):
    python -m evals.harness.gen_arm --label r284-H3H2 \
        --env REGENOLD_ANSWER_V2=1 --env REGENOLD_ANSWER_COMPLETE=0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--env", action="append", default=[], help="KEY=VAL arm env")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    for kv in a.env:
        k, _, v = kv.partition("=")
        os.environ[k.strip()] = v.strip()

    from evals.harness.probe_set import load_probe_set
    from evals.regenold.runner_v2 import _post_local

    url = "local://app.main:app/api/v1/regenold/eu-ai-act/ask"
    rows = load_probe_set()
    if a.limit:
        rows = rows[: a.limit]
    dest = Path("evals/bench/results") / f"easyhard-{a.label}.ckpt.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[gen] {len(rows)} rows  env={a.env}  -> {dest}", flush=True)
    with dest.open("w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            history = [dict(m) for m in r.messages]
            body, lat, status, err, _att, _ret = _post_local(url, None, history, a.timeout)
            ans = str((body or {}).get("answer") or "")
            refs = list((body or {}).get("references") or [])
            rec = {
                "id": r.id, "category": r.category, "is_multiturn": r.is_multiturn,
                "pred_answer": ans, "pred_refs": refs,
                "gold_refs": list(r.expected_refs or []),
                "latency_ms": lat, "http_status": status,
            }
            if err or not ans:
                rec["error"] = err or "empty_answer"
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            tag = "ERR " if rec.get("error") else "ok  "
            print(f"  [{i:3d}/{len(rows)}] {tag}{r.id:<34} {lat/1000:5.1f}s refs={len(refs)}", flush=True)
    print(f"[gen] wrote {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
