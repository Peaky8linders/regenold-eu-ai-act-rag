"""R471 — paired A/B of the corrected predictive-policing topic text, on samples.

Rows: every question in R470's blind held-out set and its development rows that
reaches the ``predictive_policing`` classification topic. None is official.

Arms. A ships the old text (patched into the topic), B the corrected one. On the
live path the text is Stage-2's draft, so both arms run through the real route in
one process with live Stage-2 (the local wrapper). The draft differs, so each arm
generates its own answer: unlike R470 there is no shared completion, and the pair
carries generation variance. Without Stage-2 the route ships the text verbatim,
which the unit tests pin.

Measured per row: whether an answer says place-based policing is high-risk (a
sentence with a place cue and "high-risk", no negation), and a position-swapped
pairwise correctness verdict (``claude-sonnet-5`` over the wrapper).

Usage (this worktree's root; the wrapper on 127.0.0.1:8000):
  python docs/measurements/r471/ab_topic.py live --out docs/measurements/r471/pairs.json
  python docs/measurements/r471/ab_topic.py judge docs/measurements/r471/pairs.json
  python docs/measurements/r471/ab_topic.py report docs/measurements/r471/pairs.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
JUDGE_MODEL = "claude-sonnet-5"
LIVE_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "openai_wrapper",
    "OPENAI_API_BASE": "http://127.0.0.1:8000/v1",
    "OPENAI_API_KEY": "dummy",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
}
OLD_TEXT = (
    "Predictive policing is prohibited under Article 5 when it assesses or "
    "predicts criminal-offence risk based solely on profiling of a natural "
    "person or their personality traits. Place-based or non-profiling predictive "
    "policing remains permitted, but is high-risk under Annex III and subject to "
    "Chapter III Section 2 obligations."
)
PLACE_CUE = re.compile(
    r"\b(?:place|location|area|geographic\w*)[- ]based\b|\bhot[- ]?spots?\b|"
    r"\bwhere or when\b|\bforecast\w*\s+(?:where|crime|locations?)\b", re.I,
)
NEGATION = re.compile(r"\b(?:not|no|neither|nor|never|outside)\b", re.I)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def calls_place_based_high_risk(answer: str) -> list[str]:
    """Sentences that say place-based policing is high-risk."""
    return [s for s in re.split(r"(?<=[.!?])\s+", answer or "")
            if PLACE_CUE.search(s) and "high-risk" in s and not NEGATION.search(s)]


def _questions() -> list[dict]:
    spec = importlib.util.spec_from_file_location(
        "r470_ab", REPO / "docs" / "measurements" / "r470" / "ab_policing.py")
    r470 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r470)
    from app.engines._graph_rag_impl import _detect_classification_topic

    return [row for row in r470._rows()
            if (_detect_classification_topic(row["question"]) or {}).get("name")
            == "predictive_policing"]


def live(out: Path) -> int:
    os.environ.update(LIVE_ENV)
    sys.path.insert(0, str(REPO))
    from fastapi.testclient import TestClient

    from app.engines import _graph_rag_data as data_mod
    from app.main import app
    from app.rate_limit import limiter
    from app.routes import regenold as route

    topic = next(t for t in data_mod._CLASSIFICATION_TOPICS if t["name"] == "predictive_policing")
    new_text = topic["answer"]
    limiter.enabled = False
    client = TestClient(app)
    data = _load(out) if out.exists() else {"rows": []}
    done = {(r["set"], r["id"]) for r in data["rows"]}
    try:
        for row in _questions():
            if (row["set"], row["id"]) in done:
                continue
            item = dict(row)
            for arm, text in (("A", OLD_TEXT), ("B", new_text)):
                topic["answer"] = text
                route._ENGINE_CACHE._data.clear()
                resp = client.post("/api/v1/regenold/eu-ai-act/ask", json={
                    "messages": [{"role": "user", "content": row["question"]}]})
                body = resp.json() if resp.status_code == 200 else {}
                item[arm] = body.get("answer", "")
                item[f"{arm}_refs"] = body.get("references") or []
                item[f"{arm}_status"] = resp.status_code
                item[f"{arm}_place_high_risk"] = calls_place_based_high_risk(item[arm])
                # Stage-2 did not land if the draft shipped verbatim.
                item[f"{arm}_verbatim_draft"] = text in item[arm]
            item["differs"] = (item["A"], item["A_refs"]) != (item["B"], item["B_refs"])
            data["rows"].append(item)
            _save(out, data)
            print(f"{row['set']}/{row['id']}: place-high-risk A {len(item['A_place_high_risk'])} "
                  f"B {len(item['B_place_high_risk'])} verbatim A {item['A_verbatim_draft']} "
                  f"B {item['B_verbatim_draft']}", flush=True)
    finally:
        topic["answer"] = new_text
    _save(out, data)
    return 0


def judge(pairs_path: Path) -> int:
    os.environ.update(LIVE_ENV)
    sys.path.insert(0, str(REPO))
    from evals.harness.ab_judge import ArmAnswer, _pairwise_verdict_detail
    from evals.judge.runner import _load_article_summaries, _resolve_caller, set_judge_model

    data = _load(pairs_path)
    set_judge_model(JUDGE_MODEL)
    resolved = _resolve_caller("wrapper", timeout_s=300)
    errors: list[str] = []

    def caller(prompt: str) -> dict:
        for _ in range(3):
            out = resolved(prompt)
            if "judge_error" not in out:
                return out
        errors.append(str(out["judge_error"])[:200])
        return out

    summaries = _load_article_summaries()
    for row in data["rows"]:
        if not row.get("differs") or "correctness" in row:
            continue
        a = ArmAnswer(answer=row["A"], refs=row["A_refs"], latency_ms=0.0, http_status=200)
        b = ArmAnswer(answer=row["B"], refs=row["B_refs"], latency_ms=0.0, http_status=200)
        rd = {"question": row["question"], "expected_keywords": [], "expected_refs": []}
        before = len(errors)
        verdict, agreed = _pairwise_verdict_detail(rd, "correctness", a, b, caller, summaries)
        if len(errors) > before:
            row["judge_failed"] = errors[-1]
        else:
            row.pop("judge_failed", None)
            row["correctness"] = {"verdict": verdict, "agreed": agreed}
        _save(pairs_path, data)
        print(f"{row['set']}/{row['id']}: {row.get('correctness', row.get('judge_failed'))}",
              flush=True)
    data["judge_model"] = JUDGE_MODEL
    data["judge_failed"] = sum(1 for r in data["rows"] if r.get("judge_failed"))
    _save(pairs_path, data)
    print(f"judge failed on {data['judge_failed']} pairs (excluded, not ties)")
    return 0


def _sign_p(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def report(pairs_path: Path) -> int:
    rows = _load(pairs_path)["rows"]
    judged = [r["correctness"]["verdict"] for r in rows if "correctness" in r]
    wins, losses = judged.count("B"), judged.count("A")
    print(f"rows {len(rows)}, differ {sum(r['differs'] for r in rows)}")
    print(f"answers calling place-based policing high-risk: "
          f"A {sum(bool(r['A_place_high_risk']) for r in rows)}, "
          f"B {sum(bool(r['B_place_high_risk']) for r in rows)}")
    print(f"draft shipped verbatim (Stage-2 did not land): "
          f"A {sum(r['A_verbatim_draft'] for r in rows)}, B {sum(r['B_verbatim_draft'] for r in rows)}")
    print(f"correctness B {wins} A {losses} tie {len(judged) - wins - losses} "
          f"p={_sign_p(wins, losses):.4f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("live").add_argument("--out", required=True)
    for name in ("judge", "report"):
        sub.add_parser(name).add_argument("pairs")
    args = ap.parse_args()
    if args.cmd == "live":
        return live(Path(args.out))
    if args.cmd == "judge":
        return judge(Path(args.pairs))
    return report(Path(args.pairs))


if __name__ == "__main__":
    sys.exit(main())
