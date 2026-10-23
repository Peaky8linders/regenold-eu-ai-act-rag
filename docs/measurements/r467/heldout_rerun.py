"""R467 — ask the held-out rephrasings on production, then mark which path answered.

Same protocol as ``paraphrase_rerun.py``, on ``heldout_rephrasings.json`` (frozen
before any R467 code change): one single-turn request per question, sequential,
and ``--offline`` replays them through the app with no model reachable so a live
answer byte-identical to its replay is known to be a statutory answer.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r467/heldout_rerun.py --out PATH            # live
    .venv/Scripts/python.exe docs/measurements/r467/heldout_rerun.py --out PATH --offline  # replay
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
HELDOUT = HERE / "heldout_rephrasings.json"
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
UA = "regenold-r467-heldout-rerun/1.0"


def live(out: Path) -> int:
    from dotenv import dotenv_values

    key = dotenv_values(REPO / ".env").get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/healthz", headers={"User-Agent": UA}), timeout=30) as resp:
        commit = json.loads(resp.read().decode("utf-8")).get("commit")
    run = {"started_utc": datetime.now(UTC).isoformat(timespec="seconds"), "commit": commit, "rows": []}
    for row in json.loads(HELDOUT.read_text(encoding="utf-8"))["rows"]:
        body = json.dumps([{"role": "user", "content": row["question"]}]).encode("utf-8")
        req = urllib.request.Request(BASE + "/api/v1/regenold/eu-ai-act/ask", data=body, headers={
            "Content-Type": "application/json", "X-Regenold-Api-Key": key, "User-Agent": UA})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            item = {**row, "answer": data.get("answer"), "references": data.get("references"),
                    "latency_s": round(time.time() - t0, 2)}
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            item = {**row, "error": repr(exc)[:300]}
        run["rows"].append(item)
        print(f"{row['id']}: {item.get('latency_s')}s refs={item.get('references')} err={item.get('error')}",
              flush=True)
    run["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    out.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


def offline(out: Path) -> int:
    os.environ["REGENOLD_SKIP_DOTENV"] = "1"
    os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
    os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
    os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
    for name in ("NEO4J_URI", "COHERE_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
                 "AWS_BEARER_TOKEN_BEDROCK", "P2P_GRAPH_RAG_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(REPO))
    from fastapi.testclient import TestClient

    from app.main import app

    run = json.loads(out.read_text(encoding="utf-8"))
    client = TestClient(app)
    for row in run["rows"]:
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json=[{"role": "user", "content": row["question"]}])
        body = resp.json() if resp.status_code == 200 else {}
        row["offline_identical"] = (body.get("answer") == row.get("answer")
                                    and body.get("references") == row.get("references"))
        print(f"{row['id']}: statutory={row['offline_identical']}", flush=True)
    out.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    target = Path(args.out)
    sys.exit(offline(target) if args.offline else live(target))
