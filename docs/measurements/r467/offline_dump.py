"""R467 — dump the offline wire (answer + references) for a question set.

Used to measure a change's blast radius exactly: the offline route is
deterministic (no model reachable), so dumping before and after a change and
diffing shows every answer and citation list the change moves.

Sets: the official 110 (``docs/measurements/r388/official_gold_n110.jsonl``) and
the 40-question R465 review corpus (``scratch/r465_ab_corpus.json``).

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r467/offline_dump.py OUT.json
    .venv/Scripts/python.exe docs/measurements/r467/offline_dump.py --diff BEFORE.json AFTER.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _questions() -> list[tuple[str, str]]:
    rows = []
    with (REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                item = json.loads(line)
                rows.append((item["id"], item["question"]))
    for item in json.loads((REPO / "scratch" / "r465_ab_corpus.json").read_text(encoding="utf-8")):
        rows.append((f"corpus:{item['id']}", item["question"]))
    return rows


def dump(out: Path) -> None:
    os.environ["REGENOLD_SKIP_DOTENV"] = "1"
    os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
    os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
    os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
    os.environ["P2P_GRAPH_RAG_ENABLE_STAGE2"] = "0"
    for name in ("NEO4J_URI", "COHERE_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
                 "AWS_BEARER_TOKEN_BEDROCK", "P2P_GRAPH_RAG_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(REPO))
    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    client = TestClient(app)
    result = {}
    for rid, question in _questions():
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json={"messages": [{"role": "user", "content": question}]})
        body = resp.json() if resp.status_code == 200 else {}
        result[rid] = {"question": question, "status": resp.status_code,
                       "answer": body.get("answer"), "references": body.get("references")}
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({len(result)} rows)")


def diff(before: Path, after: Path) -> None:
    a = json.loads(before.read_text(encoding="utf-8"))
    b = json.loads(after.read_text(encoding="utf-8"))
    changed_answer = [k for k in a if a[k]["answer"] != b.get(k, {}).get("answer")]
    changed_refs = [k for k in a if a[k]["references"] != b.get(k, {}).get("references")]
    print(f"rows {len(a)} | answers changed {len(changed_answer)} | references changed {len(changed_refs)}")
    for k in sorted(set(changed_answer) | set(changed_refs)):
        la, lb = len(a[k]["answer"] or ""), len(b[k]["answer"] or "")
        print(f"  {k}: answer {'CHANGED' if k in changed_answer else 'same'} ({la} -> {lb} chars) | "
              f"refs {a[k]['references']} -> {b[k]['references']}")


if __name__ == "__main__":
    if sys.argv[1] == "--diff":
        diff(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        dump(Path(sys.argv[1]))
