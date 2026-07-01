"""R263 — fresh live re-probe of the Antifragile-20 questions + the 6
R257-deferred production-audit questions against the CURRENT system.

The captured ``Live answer`` text in the source markdown predates many
fix rounds (R109-R261 per CLAUDE.md); judging that stale text re-
litigates already-fixed bugs. This script re-asks the exact same
questions through the in-process route (TestClient + the live Claude
Max wrapper), single-turn, and writes a fresh judge-compatible sidecar
so the calibrated judge scores what the system ACTUALLY answers today.

Mirrors evals/regenold/runner_v2.py's ``_post_local`` / in-process auth
pattern. Pure stdlib + the app import graph (heavy — lazy-imported).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def _post_one(question: str, timeout: float = 90.0) -> dict[str, Any]:
    from evals.regenold.runner_v2 import _ensure_local_auth, _post_local

    key = _ensure_local_auth()
    body, latency_ms, status, err, attempts, retried = _post_local(
        "x://local?include_reasoning=true",
        key,
        [{"role": "user", "content": question}],
        timeout,
    )
    return {
        "answer": str(body.get("answer") or ""),
        "refs": list(body.get("references") or []),
        "latency_ms": latency_ms,
        "http_status": status,
        "error": err,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-sidecar", required=True, type=Path)
    parser.add_argument("--ids", nargs="*", default=None, help="restrict to these row ids")
    args = parser.parse_args()

    payload = json.loads(args.source_sidecar.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    if args.ids:
        wanted = set(args.ids)
        rows = [r for r in rows if r["id"] in wanted]

    out_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        q = row["question"]
        t0 = time.monotonic()
        result = _post_one(q)
        elapsed = round(time.monotonic() - t0, 1)
        out_rows.append({
            "id": row["id"],
            "category": row["category"],
            "question": q,
            "predicted_answer": result["answer"],
            "pred_refs": result["refs"],
            "expected_keywords": [],
            "expected_refs": [],
            "stale_answer": row.get("predicted_answer"),
            "stale_pred_refs": row.get("pred_refs"),
            "live_latency_ms": result["latency_ms"],
            "live_http_status": result["http_status"],
            "live_error": result["error"],
        })
        print(
            f"[reprobe] {i + 1}/{len(rows)} {row['id']:<10} "
            f"{elapsed:>6.1f}s status={result['http_status']} "
            f"refs={result['refs']}",
            flush=True,
        )

    sidecar = {
        "role": "live_reprobe_fresh",
        "label": "r263-live-reprobe",
        "rows": out_rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(sidecar, indent=2, default=str), encoding="utf-8")
    print(f"[reprobe] wrote {args.out} ({len(out_rows)} rows)")


if __name__ == "__main__":
    main()
