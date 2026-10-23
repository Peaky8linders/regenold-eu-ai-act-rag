"""R467 — ask the 30 R465 paraphrases on production, then mark which path answered.

The ten review questions are answered from statutory verdicts. This asks the
30 independently written paraphrases from the R465 pairwise A/B corpus
(``scratch/r465_ab_corpus.json``, three per question family) as single user
turns against the deployed endpoint, sequentially, and records answer,
references and latency. ``--offline`` then replays the same questions through
the app with no model reachable: a live answer byte-identical to its offline
replay is the engine's deterministic composition, anything else came through
Stage-2.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r467/paraphrase_rerun.py            # live
    .venv/Scripts/python.exe docs/measurements/r467/paraphrase_rerun.py --offline  # replay
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
CORPUS = REPO / "scratch" / "r465_ab_corpus.json"
LIVE_OUT = HERE / "paraphrase_rerun.json"
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
UA = "regenold-r467-paraphrase-rerun/1.0"


def _paraphrases() -> list[dict]:
    rows = json.loads(CORPUS.read_text(encoding="utf-8"))
    return [r for r in rows if not r["id"].endswith("_0")]


def live() -> int:
    from dotenv import dotenv_values

    key = dotenv_values(REPO / ".env").get("P2P_REGENOLD_API_KEY") or ""
    if not key:
        raise SystemExit("P2P_REGENOLD_API_KEY missing from .env")
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/healthz", headers={"User-Agent": UA}), timeout=30) as resp:
        commit = json.loads(resp.read().decode("utf-8")).get("commit")
    run = {"started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "commit": commit, "rows": []}
    for row in _paraphrases():
        body = json.dumps([{"role": "user", "content": row["question"]}]).encode("utf-8")
        req = urllib.request.Request(BASE + "/api/v1/regenold/eu-ai-act/ask", data=body, headers={
            "Content-Type": "application/json", "X-Regenold-Api-Key": key, "User-Agent": UA})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = {"id": row["id"], "family": row["family"], "question": row["question"],
                   "answer": data.get("answer"), "references": data.get("references"),
                   "latency_s": round(time.time() - t0, 2)}
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            out = {"id": row["id"], "family": row["family"], "question": row["question"],
                   "error": repr(exc)[:300]}
        run["rows"].append(out)
        print(f"{row['id']}: {out.get('latency_s')}s refs={out.get('references')} "
              f"err={out.get('error')}", flush=True)
    run["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    LIVE_OUT.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


def offline() -> int:
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

    run = json.loads(LIVE_OUT.read_text(encoding="utf-8"))
    client = TestClient(app)
    for row in run["rows"]:
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json=[{"role": "user", "content": row["question"]}])
        body = resp.json() if resp.status_code == 200 else {}
        row["offline_identical"] = (body.get("answer") == row.get("answer")
                                    and body.get("references") == row.get("references"))
        print(f"{row['id']}: deterministic={row['offline_identical']}", flush=True)
    LIVE_OUT.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    sys.exit(offline() if ap.parse_args().offline else live())
