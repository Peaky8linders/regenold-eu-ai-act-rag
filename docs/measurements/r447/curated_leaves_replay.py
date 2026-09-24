"""R447 — REGENOLD_CURATED_KEEP_DECLARED_LEAVES, two arms, through the real route.

A curated intercept skips Stage-2, so its wire references are deterministic:
this offline replay IS the production behaviour for every row the flag can
touch (the flag only acts when ``_is_curated_authoritative_intercept`` fires).
Each question is asked twice through the real route with the flag OFF (the
R87-C re-emission runs) and ON (it is skipped for curated intercepts), and
every row whose wire references differ is scored with the official rubric
against its gold: the reconstructed refkey for the official 110, the expert
``expected_refs`` for the 28 expert-review rows.

Run from the repo root:
  .venv/Scripts/python.exe docs/measurements/r447/curated_leaves_replay.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
sys.path.insert(0, os.getcwd())

import app  # noqa: E402

assert Path(app.__file__).resolve().is_relative_to(Path.cwd().resolve()), app.__file__

from fastapi.testclient import TestClient  # noqa: E402

from app.engines.graph_rag import _is_curated_authoritative_intercept  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.routes import regenold as route  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

limiter.enabled = False
FLAG = "REGENOLD_CURATED_KEEP_DECLARED_LEAVES"
EXTRA = [
    # The R447 review's compound-role and emotion phrasings, and the role route.
    ("review_compound_q04", "We are both a provider and a deployer of a chatbot. How must a "
     "natural person be informed that they are interacting with an AI system?", None),
    ("review_compound_hr", "As both the provider and the deployer of an HR chatbot, how must "
     "a natural person be informed that they are interacting with an AI system?", None),
    ("review_emotion", "How should users be informed about the use of emotion recognition?", None),
    # The second review: a scenario shape runs expand_citations, which adds a
    # bare Article 50 BEFORE the R87-C re-emission.
    ("review2_scenario", "We are both a provider and a deployer of a chatbot used by our bank. "
     "What is its risk classification? How must a natural person be informed that they "
     "are interacting with an AI system?", None),
]


def corpus() -> list[tuple[str, str, list[str] | None]]:
    key = {
        json.loads(line)["id"]: json.loads(line)["expected"]
        for line in open("docs/measurements/r388/official_refkey_n110.jsonl", encoding="utf-8")
    }
    out = [
        (r["id"], r["question"], key.get(r["id"]))
        for r in (
            json.loads(line)
            for line in open("docs/measurements/r388/official_gold_n110.jsonl", encoding="utf-8")
        )
    ]
    expert = json.load(
        open("docs/measurements/r436/expert-review-bedrock-qwen235.json", encoding="utf-8")
    )["rows"]
    out += [(r["id"], r["question"], r.get("expected_refs")) for r in expert]
    from evals.harness.probe_set import load_probe_set  # noqa: PLC0415

    out += [(p.id, p.live_question, list(p.expected_refs) or None) for p in load_probe_set()
            if not p.is_multiturn]
    return out + EXTRA


def ask(client: TestClient, question: str, flag: str) -> list[str]:
    os.environ[FLAG] = flag
    route._ENGINE_CACHE.clear()
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=[{"role": "user", "content": question}])
    return list(resp.json().get("references") or [])


rows = corpus()
curated = changed = 0
totals = {"off": [0.0, 0.0, 0.0], "on": [0.0, 0.0, 0.0]}
scored = 0
with TestClient(fastapi_app) as client:
    for rid, question, gold in rows:
        if not _is_curated_authoritative_intercept(question):
            continue
        curated += 1
        off, on = ask(client, question, "0"), ask(client, question, "1")
        if off == on:
            continue
        changed += 1
        line = f"  {rid}: OFF={off}\n  {' ' * len(rid)}  ON ={on}"
        if gold:
            scored += 1
            for arm, refs in (("off", off), ("on", on)):
                totals[arm][0] += reference_correctness_loose(refs, gold) or 0.0
                totals[arm][1] += reference_correctness_strict(refs, gold) or 0.0
                totals[arm][2] += reference_conciseness(refs, gold) or 0.0
            line += (
                f"\n  {' ' * len(rid)}  gold={gold}  strict {reference_correctness_strict(off, gold):.2f}"
                f" -> {reference_correctness_strict(on, gold):.2f}, conc "
                f"{reference_conciseness(off, gold):.2f} -> {reference_conciseness(on, gold):.2f}"
            )
        print(line)
os.environ.pop(FLAG, None)
print(f"\nrows: {len(rows)}; curated-intercept rows: {curated}; wire changed: {changed}; "
      f"changed rows with gold: {scored}")
if scored:
    for arm in ("off", "on"):
        loose, strict, conc = (v / scored for v in totals[arm])
        print(f"  {arm.upper():3} mean over changed+gold rows: ref_loose {loose:.3f}  "
              f"ref_strict {strict:.3f}  ref_conc {conc:.3f}")
