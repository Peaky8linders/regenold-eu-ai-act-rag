"""R474 - replay the non-official pool through ONE checkout's real route, offline.

Offline = ``P2P_GRAPH_RAG_PROVIDER=cli``, a dead ``OPENAI_API_BASE``, ``.env`` not
loaded: no model is reachable, so every answer is the engine's deterministic
composition. A curated verdict skips Stage-2, so for those questions this IS what
production serves; for every other question it is only a regression screen
(the three prose->refs passes are gated by ``stage2_landed`` and are skipped).

Usage (run once per checkout, with that checkout as cwd, then compare):
    python docs/measurements/r474/route_replay.py --out OUT.json [--questions Q.json] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.update({
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
})
for _n in ("NEO4J_URI", "COHERE_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
           "AWS_BEARER_TOKEN_BEDROCK", "P2P_GRAPH_RAG_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(_n, None)

HERE = Path(__file__).resolve().parent
CHECKOUT = Path.cwd().resolve()
sys.path.insert(0, str(CHECKOUT))
sys.path.insert(1, str(HERE))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--questions", help="JSON {'questions': [...]} instead of the full pool")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    client = TestClient(app)
    if args.questions:
        qs = json.loads(Path(args.questions).read_text(encoding="utf-8"))["questions"]
    else:
        import pool  # noqa: PLC0415
        qs, _ = pool.build()
    if args.limit:
        qs = qs[: args.limit]
    rows, t0 = [], time.time()
    for i, q in enumerate(qs, 1):
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json=[{"role": "user", "content": q}])
        body = resp.json() if resp.status_code == 200 else {}
        rows.append({"question": q, "status": resp.status_code,
                     "answer": body.get("answer", ""),
                     "references": body.get("references") or []})
        if i % 100 == 0:
            print(f"  {i}/{len(qs)}  {time.time() - t0:.0f}s", flush=True)
    Path(args.out).write_text(json.dumps(
        {"checkout": str(CHECKOUT), "n": len(rows), "rows": rows},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}: {len(rows)} rows in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
