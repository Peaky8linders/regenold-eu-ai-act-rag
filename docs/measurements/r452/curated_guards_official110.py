"""R452c — the two curated-intercept guards on the official 110, offline.

Curated intercepts skip Stage-2, so their offline answer and references are
exactly what production ships (apart from live classifier passes). Every
official question is asked through the real route twice, with
REGENOLD_CURATED_HEAD_GRAIN / REGENOLD_CURATED_DECLARED_FIRST on and off, and
the rows whose references differ are scored with the real rubric against the
reconstructed gold keys.

    py -3.12 docs/measurements/r452/curated_guards_official110.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
os.environ.update({"REGENOLD_SKIP_DOTENV": "1", "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
                   "P2P_GRAPH_RAG_PROVIDER": "cli", "REGENOLD_EXTERNAL_EMBEDDINGS": "0"})
for k in ("NEO4J_URI", "COHERE_API_KEY"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)
from evals.regenold.official_batch import load_official_batch  # noqa: E402

FLAGS = ("REGENOLD_CURATED_HEAD_GRAIN", "REGENOLD_CURATED_DECLARED_FIRST")


def main() -> int:
    gold = {}
    for line in (REPO / "docs/measurements/r388/official_gold_n110.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g.get("expected_refs") or []
    from app.rate_limit import limiter  # noqa: PLC0415

    limiter.enabled = False  # an offline replay of 220 asks, not traffic
    client = TestClient(app)
    rows = list(load_official_batch())
    arms: dict[str, dict[str, list[str]]] = {"off": {}, "on": {}}
    for arm, value in (("off", "0"), ("on", "1")):
        for f in FLAGS:
            os.environ[f] = value
        for r in rows:
            resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                               json={"messages": [{"role": "user", "content": r.question}]})
            if resp.status_code != 200:
                raise SystemExit(f"{arm} {r.id}: HTTP {resp.status_code} {resp.text[:120]}")
            arms[arm][r.id] = resp.json().get("references") or []
    changed = [rid for rid in arms["off"] if arms["off"][rid] != arms["on"][rid]]
    print(f"official questions: {len(rows)}; reference lists changed by the curated guards: {len(changed)}")
    totals = {"off": [0.0, 0.0, 0.0, 0], "on": [0.0, 0.0, 0.0, 0]}
    for rid in changed:
        exp = gold.get(rid) or []
        line = [rid, "OFF", arms["off"][rid], "ON", arms["on"][rid], "gold", exp]
        print("  ", *line)
        if exp:
            for arm in ("off", "on"):
                pred = arms[arm][rid]
                totals[arm][0] += reference_correctness_strict(pred, exp) or 0.0
                totals[arm][1] += reference_correctness_loose(pred, exp) or 0.0
                totals[arm][2] += reference_conciseness(pred, exp) or 0.0
                totals[arm][3] += 1
    for arm in ("off", "on"):
        n = totals[arm][3] or 1
        print(f"{arm}: over {totals[arm][3]} changed gold rows  strict {100 * totals[arm][0] / n:.1f}"
              f"  loose {100 * totals[arm][1] / n:.1f}  conc {100 * totals[arm][2] / n:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
