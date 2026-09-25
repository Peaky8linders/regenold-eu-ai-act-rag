"""R447b — REGENOLD_ROLE_DIFFERENCE_SKIP_INTENT_BOOST, two arms, live Stage-0 classifier.

The R66-E intent boost reads the Stage-0 intent classifier, which only runs
with a live provider configured. So this replay loads the full ``.env``
(``REGENOLD_SKIP_DOTENV=0``). That is the regime that reproduced production's
provider-vs-deployer wire exactly (``... Article 25.1, Article 26.5``). Every
curated-intercept row is asked through the real route twice, with the flag OFF
(the boost runs) and ON. Curated intercepts skip Stage-2, and each row's
classification is retried until it lands in the classifier's module-level LRU,
so both arms read the SAME classification and the boost is the only difference.

History: a first cut skipped the boost for EVERY curated intercept. Measured
with this script (31 of 36 curated rows classified), it changed 7 wires:
5 pure reorders, part1_q10 (Article 26.5 gone), and rg_040, where the injected
``Article 43`` happens to knock ``Annex VII.4`` off the wire. The blanket skip
cost that official row Ref. Conciseness 1.00 -> 0.50 against its
reconstructed gold, so the flag is scoped to the role-difference verdict.

Changed rows are scored with the official rubric against their gold: the
reconstructed refkey for the official 110, the expert ``expected_refs`` for the
28 expert rows, the probe corpus's own ``expected_refs``.

Run from the repo root (needs the live classifier's provider credentials):
  .venv/Scripts/python.exe docs/measurements/r447/curated_intent_boost_replay.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
os.environ["REGENOLD_SKIP_DOTENV"] = "0"

import app  # noqa: E402
import app.config  # noqa: E402,F401  (loads .env)

assert Path(app.__file__).resolve().is_relative_to(REPO.resolve()), app.__file__

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
FLAG = "REGENOLD_ROLE_DIFFERENCE_SKIP_INTENT_BOOST"
EXTRA = [
    ("review_compound_q04", "We are both a provider and a deployer of a chatbot. How must a "
     "natural person be informed that they are interacting with an AI system?", None),
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


def classify_with_retry(question: str, tries: int = 5):
    """The live classifier, retried: a failure returns ``None`` uncached.

    A success lands in the module-level LRU, so both arms of the route then
    read the SAME classification. Measured: without the retry 21 of 36 curated
    rows got no classification at all (provider rate limits), which would have
    read as "the boost changes nothing".
    """
    import time  # noqa: PLC0415

    from app.llm.intent_classifier import classify_intent  # noqa: PLC0415

    for attempt in range(tries):
        result = classify_intent(question)
        if result is not None:
            return result
        time.sleep(3 * (attempt + 1))
    return None


rows = corpus()
curated = changed = scored = boosting = unavailable = 0
totals = {"off": [0.0, 0.0, 0.0], "on": [0.0, 0.0, 0.0]}
with TestClient(fastapi_app) as client:
    for rid, question, gold in rows:
        if not _is_curated_authoritative_intercept(question):
            continue
        curated += 1
        intent = classify_with_retry(question)
        if intent is None:
            unavailable += 1
            print(f"  [{rid}] CLASSIFIER UNAVAILABLE after retries; not measured")
            continue
        conf = float(getattr(intent, "confidence", 0.0) or 0.0)
        anchor = getattr(intent, "primary_anchor", "") or ""
        boosting += conf >= route._INTENT_BOOST_MIN_CONFIDENCE and bool(anchor)
        # Every row's classification is printed: a classifier that failed (rate
        # limit, timeout) reads as "no boost", which must not pass for a null.
        print(f"  [{rid}] intent={getattr(intent, 'intent', '')} conf={conf:.2f} "
              f"anchor={anchor or '-'} source={getattr(intent, 'source', '')}")
        off, on = ask(client, question, "0"), ask(client, question, "1")
        if off == on:
            continue
        changed += 1
        line = (f"  {rid}: intent={getattr(intent, 'intent', '')} conf={conf:.2f} anchor={anchor}"
                f"\n    OFF={off}\n    ON ={on}")
        if gold:
            scored += 1
            for arm, refs in (("off", off), ("on", on)):
                totals[arm][0] += reference_correctness_loose(refs, gold) or 0.0
                totals[arm][1] += reference_correctness_strict(refs, gold) or 0.0
                totals[arm][2] += reference_conciseness(refs, gold) or 0.0
            line += (
                f"\n    gold={gold}  loose "
                f"{reference_correctness_loose(off, gold):.2f}->{reference_correctness_loose(on, gold):.2f}"
                f" strict {reference_correctness_strict(off, gold):.2f}->"
                f"{reference_correctness_strict(on, gold):.2f} conc "
                f"{reference_conciseness(off, gold):.2f}->{reference_conciseness(on, gold):.2f}"
            )
        print(line)
os.environ.pop(FLAG, None)
print(f"\nrows: {len(rows)}; curated rows: {curated}; classifier unavailable: {unavailable}; "
      f"classifier above the boost floor: {boosting}; wire changed: {changed}; "
      f"changed rows with gold: {scored}")
if scored:
    for arm in ("off", "on"):
        loose, strict, conc = (v / scored for v in totals[arm])
        print(f"  {arm.upper():3} mean over changed+gold rows: ref_loose {loose:.3f}  "
              f"ref_strict {strict:.3f}  ref_conc {conc:.3f}")
