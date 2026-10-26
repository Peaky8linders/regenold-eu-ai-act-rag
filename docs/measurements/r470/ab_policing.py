"""R470 — paired A/B of the place-based exclusion on Article 5(1)(d), on samples.

Sets, none of them official (AGENTS.md, operator directive 2026-10-25):

* ``heldout`` — ``heldout_policing.json``: 12 place-based targets and 12
  person-based controls, written by a separate agent that did not read the code,
  committed before the fix.
* ``dev`` — R469's N17_t2 and the probe/pool questions that name predictive
  policing.

Arms. A is ``REGENOLD_PLACE_BASED_POLICING=0`` (main), B is the default. Both run
in one process through the real route with live Stage-2 (the local wrapper). The
gatekeeper runs after Stage-2, so the Stage-2 completion is memoised: B reuses
A's completion whenever its request is identical, and only the gatekeeper's
output differs. A row whose gatekeeper scan is the same in both arms is a tie by
construction and is not asked (``scan``).

``judge`` grades every changed pair on correctness only, with the
position-swapped pairwise judge (``claude-sonnet-5`` over the wrapper): the fix
removes or keeps a sentence, so length is reported instead of a conciseness
verdict.

Usage (this worktree's root; the wrapper on 127.0.0.1:8000 for live and judge):
  python docs/measurements/r470/ab_policing.py scan --out docs/measurements/r470/scan.json
  python docs/measurements/r470/ab_policing.py live --scan docs/measurements/r470/scan.json \
      --out docs/measurements/r470/pairs.json
  python docs/measurements/r470/ab_policing.py judge docs/measurements/r470/pairs.json
  python docs/measurements/r470/ab_policing.py report docs/measurements/r470/pairs.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FLAG = "REGENOLD_PLACE_BASED_POLICING"
JUDGE_MODEL = "claude-sonnet-5"
LIVE_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "openai_wrapper",
    "OPENAI_API_BASE": "http://127.0.0.1:8000/v1",
    "OPENAI_API_KEY": "dummy",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
}
DEV = [
    ("N17_t2", "target",
     "If place-based predictive policing tools (forecasting where crime will happen rather "
     "than who will commit it) prove harmful, could the Commission bring them into Annex III "
     "by delegated act, and what has to happen before such an act takes effect?"),
    ("P_pp1", "control", "Can predictive policing tools rely on the Article 6(3) exemption?"),
    ("P_pp2", "control", "Is predictive policing prohibited under the AI Act?"),
    ("P_pp3", "control", "Is predictive policing prohibited?"),
    ("P_pp4", "control", "What's the Recital 16 carve-out for predictive policing?"),
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _rows() -> list[dict]:
    rows = [{"set": "heldout", "id": r["id"], "kind": r["kind"], "question": r["question"]}
            for r in _load(HERE / "heldout_policing.json")["rows"]]
    rows += [{"set": "dev", "id": i, "kind": k, "question": q} for i, k, q in DEV]
    return rows


def scan(out: Path) -> int:
    sys.path.insert(0, str(REPO))
    from app.engines.prohibited_gatekeeper import scan_for_prohibitions

    rows = []
    for row in _rows():
        arms = {}
        for arm, value in (("A", "0"), ("B", "1")):
            os.environ[FLAG] = value
            arms[arm] = [sub for _parent, sub in scan_for_prohibitions(row["question"])]
        rows.append({**row, "scan_A": arms["A"], "scan_B": arms["B"],
                     "changed": arms["A"] != arms["B"]})
    _save(out, {"rows": rows})
    for name in ("heldout", "dev"):
        for kind in ("target", "control"):
            part = [r for r in rows if r["set"] == name and r["kind"] == kind]
            if not part:
                continue
            on_a = sum("Art. 5.1.d" in r["scan_A"] for r in part)
            on_b = sum("Art. 5.1.d" in r["scan_B"] for r in part)
            print(f"{name}/{kind}: {len(part)} rows; Art. 5.1.d matched A {on_a}, B {on_b}")
    print(f"wrote {out}: {sum(r['changed'] for r in rows)} rows change")
    return 0


def live(scan_path: Path, out: Path) -> int:
    os.environ.update(LIVE_ENV)
    sys.path.insert(0, str(REPO))
    from fastapi.testclient import TestClient

    from app.llm import openai_wrapper_provider as owp
    from app.main import app
    from app.rate_limit import limiter
    from app.routes import regenold as route

    original = owp._OpenAIWrapperProvider.complete
    memo: dict[str, object] = {}
    counts = {"calls": 0, "hits": 0}

    def complete(self, req):
        key = json.dumps([req.system, req.user, req.model, req.max_tokens, req.temperature],
                         ensure_ascii=False)
        if key in memo:
            counts["hits"] += 1
            return memo[key]
        counts["calls"] += 1
        memo[key] = original(self, req)
        return memo[key]

    owp._OpenAIWrapperProvider.complete = complete
    limiter.enabled = False
    client = TestClient(app)
    data = _load(out) if out.exists() else {"rows": []}
    done = {(r["set"], r["id"]) for r in data["rows"]}
    try:
        for row in _load(scan_path)["rows"]:
            if not row["changed"] or (row["set"], row["id"]) in done:
                continue
            item = dict(row)
            for arm, value in (("A", "0"), ("B", "1")):
                os.environ[FLAG] = value
                route._ENGINE_CACHE._data.clear()
                before = counts["calls"]
                resp = client.post("/api/v1/regenold/eu-ai-act/ask", json={
                    "messages": [{"role": "user", "content": row["question"]}]})
                body = resp.json() if resp.status_code == 200 else {}
                item[arm] = body.get("answer", "")
                item[f"{arm}_refs"] = body.get("references") or []
                item[f"{arm}_status"] = resp.status_code
                item[f"{arm}_fresh_calls"] = counts["calls"] - before
            # B made no provider call of its own when every request was A's.
            item["paired_generation"] = item["B_fresh_calls"] == 0
            item["differs"] = (item["A"], item["A_refs"]) != (item["B"], item["B_refs"])
            data["rows"].append(item)
            _save(out, data)
            print(f"{row['set']}/{row['id']}: differs={item['differs']} "
                  f"paired={item['paired_generation']} A calls={item['A_fresh_calls']}",
                  flush=True)
    finally:
        owp._OpenAIWrapperProvider.complete = original
    data["provider_calls"], data["memo_hits"] = counts["calls"], counts["hits"]
    _save(out, data)
    return 0


JUDGE_ENV = {**LIVE_ENV}


def judge(pairs_path: Path) -> int:
    os.environ.update(JUDGE_ENV)
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


def _mean(values: list[int]) -> int:
    return round(sum(values) / len(values)) if values else 0


def report(pairs_path: Path) -> int:
    data = _load(pairs_path)
    for name in ("heldout", "dev"):
        for kind in ("target", "control"):
            part = [r for r in data["rows"] if r["set"] == name and r["kind"] == kind]
            if not part:
                continue
            judged = [r["correctness"]["verdict"] for r in part if "correctness" in r]
            wins, losses = judged.count("B"), judged.count("A")
            differs = [r for r in part if r["differs"]]
            print(f"{name}/{kind}: asked {len(part)}, differ {len(differs)}, paired generation "
                  f"{sum(r['paired_generation'] for r in part)}; correctness B {wins} A {losses} "
                  f"tie {len(judged) - wins - losses} p={_sign_p(wins, losses):.4f}; mean chars "
                  f"A {_mean([len(r['A']) for r in differs])} "
                  f"B {_mean([len(r['B']) for r in differs])}")
    print(f"provider calls {data.get('provider_calls')}, memo hits {data.get('memo_hits')}, "
          f"judge failed {data.get('judge_failed')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--out", required=True)
    p = sub.add_parser("live")
    p.add_argument("--scan", required=True)
    p.add_argument("--out", required=True)
    for name in ("judge", "report"):
        sub.add_parser(name).add_argument("pairs")
    args = ap.parse_args()
    if args.cmd == "scan":
        return scan(Path(args.out))
    if args.cmd == "live":
        return live(Path(args.scan), Path(args.out))
    if args.cmd == "judge":
        return judge(Path(args.pairs))
    return report(Path(args.pairs))


if __name__ == "__main__":
    sys.exit(main())
