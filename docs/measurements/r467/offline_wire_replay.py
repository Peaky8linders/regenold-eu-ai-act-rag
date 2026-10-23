"""R467 — replay the ten review questions through the app OFFLINE and compare.

No model is reachable in this regime (``P2P_GRAPH_RAG_PROVIDER=cli``, a dead
``OPENAI_API_BASE``, ``.env`` not loaded), so every answer is the engine's own
deterministic composition. If a production answer is byte-identical to this
one, the production text did not come from an LLM.

Usage (repo root):
    .venv/Scripts/python.exe docs/measurements/r467/offline_wire_replay.py PRODUCTION_JSON
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
for name in ("NEO4J_URI", "COHERE_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
             "AWS_BEARER_TOKEN_BEDROCK", "P2P_GRAPH_RAG_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(name, None)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def main() -> int:
    prod = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    client = TestClient(app)
    out = []
    for row in prod["rows"]:
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json=[{"role": "user", "content": row["question"]}])
        body = resp.json() if resp.status_code == 200 else {}
        same_answer = body.get("answer") == row.get("answer")
        same_refs = body.get("references") == row.get("references")
        out.append({"id": row["id"], "status": resp.status_code,
                    "answer_identical": same_answer, "references_identical": same_refs,
                    "offline_references": body.get("references")})
        print(f"{row['id']}: status={resp.status_code} answer_identical={same_answer} "
              f"refs_identical={same_refs}", flush=True)
    target = Path(sys.argv[1]).with_name("offline_wire_replay.json")
    target.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
