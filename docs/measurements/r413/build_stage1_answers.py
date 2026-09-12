"""R413 — build the deterministic Stage-1 answers used by the truncation gate.

``_guard_stage2_truncation`` falls back to the deterministic Stage-1 answer when
it cannot repair a cut polish, so the gate must hand it the SAME text production
would hand it. This script runs the engine with Stage-2 disabled (dead
transport), which is the recorded R409/R411 offline pattern, and writes one row
per gold id.

Run as its own process: importing the offline env would kill the live Stage-2
pass that ``tail_repair_gate.py`` needs.

    .venv/Scripts/python.exe docs/measurements/r413/build_stage1_answers.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r413" / "stage1_answers.jsonl"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"


def main() -> int:
    # Deterministic offline environment (mirrors the R409 frontier-judge runner):
    # Stage-2 unreachable, denoiser off, embeddings off. No LLM, no network.
    os.environ["REGENOLD_SKIP_DOTENV"] = "1"
    os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
    os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
    os.environ["REGENOLD_QUERY_DENOISER"] = "0"
    os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"

    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    # The anon bucket is 30/min and this probe walks all 110 rows back to back,
    # so the tail would read as 429 rather than as an answer (the R411 corpus_ab
    # lesson). Measurement-only; the app is untouched.
    limiter.enabled = False

    gold = [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    client = TestClient(app)
    rows = []
    for g in gold:
        t0 = time.time()
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": g["question"]}],
        )
        dt = time.time() - t0
        if resp.status_code != 200:
            print(f"  {g['id']:<10} HTTP {resp.status_code}", flush=True)
            continue
        data = resp.json()
        rows.append(
            {
                "id": g["id"],
                "question": g["question"],
                "stage1_answer": data.get("answer", ""),
                "stage1_refs": data.get("references", []),
                "latency_s": round(dt, 3),
            }
        )
        print(f"  [{len(rows):3d}/{len(gold)}] {g['id']:<10} {dt:5.1f}s", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(REPO)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
