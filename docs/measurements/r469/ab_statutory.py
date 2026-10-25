"""R469 — paired A/B of the widened statutory-verdict detectors, on samples.

The measurement rule (AGENTS.md, operator directive 2026-10-25): a paired A/B
test on samples sized for significance, never a replay of the full official
110. Three question sets, none of them official:

* ``heldout`` — ``heldout_rephrasings.json``: questions written by a separate
  agent and committed before any R469 code change; the person changing the
  detectors did not read them until the change was frozen. ``target`` rows are
  rephrasings whose correct answer is the family's vetted position; ``control``
  rows share the family's vocabulary but need a different answer.
* ``dev`` — the R467 held-out set (``docs/measurements/r467/heldout_rephrasings.json``).
  R469's failing examples came from it, so it is reported, not used as evidence.
* ``pool`` — the false-positive control: every non-official question in the
  probe corpus, the R465 corpus and the test files whose route the change moves
  (``labels`` on both checkouts, then ``label-diff``).

Arms. A is production as deployed (``live``: one single-turn request per
question, sequential). B is this branch. The change only moves questions onto
a curated verdict, or changes a verdict's text, and a curated verdict skips
Stage-2, so for a question the branch answers with a curated verdict B is the
branch's offline answer, which is what production would serve. Every other
question keeps A's answer: its path through the code is unchanged, so it is a
tie by construction and is not judged.

``judge`` grades every changed pair with the position-swapped pairwise judge
(``evals.harness.ab_judge``; correctness, conciseness, tone) and, for target
rows, with the R467 absolute grade (correct / partly / incorrect against the
family's position in ``reference_positions.json``). Both judges are
``claude-sonnet-5`` over the local wrapper. ``report`` gives per set the changed
pairs, wins and losses, and a two-sided sign test.

Usage (this worktree's root; the wrapper on 127.0.0.1:8000 for live and judge):
  python docs/measurements/r469/ab_statutory.py live --set heldout --out A.json
  python docs/measurements/r469/ab_statutory.py route --set heldout --repo MAIN --out main.json
  python docs/measurements/r469/ab_statutory.py route --set heldout --repo . --out branch.json
  python docs/measurements/r469/ab_statutory.py pairs --set heldout --live A.json \
      --main main.json --branch branch.json --out pairs_heldout.json
  python docs/measurements/r469/ab_statutory.py judge pairs_heldout.json
  python docs/measurements/r469/ab_statutory.py labels --repo MAIN --out labels_main.json
  python docs/measurements/r469/ab_statutory.py labels --repo . --out labels_branch.json
  python docs/measurements/r469/ab_statutory.py label-diff --main labels_main.json \
      --branch labels_branch.json --out pool_questions.json
  python docs/measurements/r469/ab_statutory.py report pairs_heldout.json pairs_dev.json ...
"""
from __future__ import annotations

import argparse
import ast
import glob
import importlib.util
import inspect
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SETS = {
    # Held-out set 1 measured iteration 1 and was then read to design iteration 2.
    "heldout": HERE / "heldout_rephrasings.json",
    # Held-out set 2, written blind after iteration 1, measures iteration 2.
    "heldout2": HERE / "heldout_rephrasings_2.json",
    "dev": REPO / "docs" / "measurements" / "r467" / "heldout_rephrasings.json",
}
REFERENCES = HERE / "reference_positions.json"
R467_JUDGE = REPO / "docs" / "measurements" / "r467" / "heldout_judge.py"
BASE = "https://regenold-eu-ai-act-rag-production.up.railway.app"
UA = "regenold-r469-ab/1.0"
JUDGE_MODEL = "claude-sonnet-5"
AXES = ("correctness", "conciseness", "tone")
GRADE = {"correct": 2, "partly": 1, "incorrect": 0}
OFFLINE_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
}
#: This round's own test file: its questions are the dev rows, so it is not a
#: false-positive control.
OWN_TESTS = "test_r469_"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _rows(set_name: str, questions: Path | None = None) -> list[dict]:
    if set_name == "pool":
        if questions is None:
            raise SystemExit("--set pool needs --questions (label-diff output)")
        return [{"id": f"P{i:03d}", "family": None, "kind": "pool", "question": q}
                for i, q in enumerate(_load(questions)["questions"], 1)]
    rows = _load(SETS[set_name])["rows"]
    return [{"kind": "target", **row} for row in rows]


def _offline(repo: Path) -> None:
    os.environ.update(OFFLINE_ENV)
    for name in ("NEO4J_URI", "COHERE_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
                 "AWS_BEARER_TOKEN_BEDROCK", "P2P_GRAPH_RAG_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(repo.resolve()))


def _labeller():
    """``question -> name of the curated answer that takes it, or None``."""
    from app.engines import _graph_rag_impl as engine
    from app.engines.statutory_precision import curated_statutory_verdict

    source = inspect.getsource(engine._is_curated_authoritative_intercept)
    detectors = re.findall(r"(_detect_\w+_inquiry)\(question\)", source)

    def label(question: str) -> str | None:
        verdict = curated_statutory_verdict(question)
        if verdict is not None:
            return verdict["name"]
        for name in detectors:
            if getattr(engine, name)(question):
                return name
        return None

    return label


# ── arm A: production ────────────────────────────────────────────────────────


def _api_key() -> str:
    """The production key from this checkout's ``.env``, else the main checkout's:
    a git worktree has no ``.env`` of its own, and copying the secret is worse."""
    from dotenv import dotenv_values

    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=REPO, capture_output=True, text=True).stdout.strip()
    for env in (REPO / ".env", Path(common).parent / ".env" if common else None):
        if env is not None and env.exists():
            key = dotenv_values(env).get("P2P_REGENOLD_API_KEY")
            if key:
                return key
    raise SystemExit("P2P_REGENOLD_API_KEY missing from .env (this checkout and the main one)")


def live(set_name: str, out: Path, questions: Path | None, ids: set[str] | None = None) -> int:
    """Ask production; with ``ids``, only those rows (the ones the change moves:
    every other row is a tie by construction and needs no production answer)."""
    key = _api_key()
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/healthz", headers={"User-Agent": UA}), timeout=30) as resp:
        commit = json.loads(resp.read().decode("utf-8")).get("commit")
    run = _load(out) if out.exists() else {
        "set": set_name, "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit, "rows": []}
    if run.get("commit") != commit:
        raise SystemExit(f"production moved from {run.get('commit')} to {commit}; start a new file")
    done = {r["id"] for r in run["rows"] if "answer" in r}
    run["rows"] = [r for r in run["rows"] if r["id"] in done]
    for row in _rows(set_name, questions):
        if row["id"] in done or (ids is not None and row["id"] not in ids):
            continue
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
        _save(out, run)
        print(f"{row['id']}: {item.get('latency_s')}s err={item.get('error')}", flush=True)
    run["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    _save(out, run)
    return 0


# ── offline route on a checkout ──────────────────────────────────────────────


def route(set_name: str, repo: Path, out: Path, questions: Path | None) -> int:
    _offline(repo)
    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    client = TestClient(app)
    label = _labeller()
    rows = []
    for row in _rows(set_name, questions):
        resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json=[{"role": "user", "content": row["question"]}])
        body = resp.json() if resp.status_code == 200 else {}
        rows.append({**row, "label": label(row["question"]), "answer": body.get("answer", ""),
                     "references": body.get("references") or [], "status": resp.status_code})
    _save(out, {"set": set_name, "repo": str(repo.resolve()), "rows": rows})
    print(f"wrote {out}: {sum(bool(r['label']) for r in rows)} of {len(rows)} curated")
    return 0


def labels(repo: Path, out: Path, corpus: Path) -> int:
    """Curated label of every non-official pool question, on one checkout."""
    _offline(repo)
    from evals.harness.probe_set import load_probe_set

    pool = [r.messages[-1]["content"] for r in load_probe_set(multiturn=False)]
    if corpus.exists():
        pool += [r["question"] for r in _load(corpus)]
    for f in glob.glob(str(REPO / "tests" / "*.py")):
        if Path(f).name.startswith(OWN_TESTS):
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                # "ORIGINAL QUESTION: ..." is a prompt fragment, not a question.
                if (20 <= len(s) <= 300 and s.endswith("?") and "\n" not in s
                        and not re.match(r"[A-Z][A-Z ]{3,}:", s)):
                    pool.append(s)
    official = {_norm(json.loads(line)["question"]) for line in
                (REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()}
    sets = {_norm(r["question"]) for name in SETS if SETS[name].exists()
            for r in _load(SETS[name])["rows"]}
    questions = sorted({q for q in pool if _norm(q) not in official | sets})
    label = _labeller()
    _save(out, {"repo": str(repo.resolve()), "labels": {q: label(q) for q in questions}})
    print(f"wrote {out}: {len(questions)} pool questions")
    return 0


def label_diff(main: Path, branch: Path, out: Path) -> int:
    a, b = _load(main)["labels"], _load(branch)["labels"]
    moved = sorted(q for q in a if q in b and a[q] != b[q])
    _save(out, {"pool": len(a), "questions": moved,
                "moves": {q: [a[q], b[q]] for q in moved}})
    print(f"wrote {out}: {len(moved)} of {len(a)} pool questions change route")
    return 0


#: The curated route each family's targets should take (a control should not).
FAMILY_ROUTES = {
    "Q74": {"deepfake_artistic_disclosure"},
    "Q16": {"workplace_emotion_and_stress"},
    "CASE_D": {"_detect_robotic_surgery_inquiry"},
    "Q45": {"instructions_for_use_categories"},
    "Q96": {"annex_iii_areas_healthcare"},
    "Q10": {"_detect_role_difference_inquiry", "_detect_reclassification_inquiry"},
    "Q17": {"annex_iii_amendment"},
    "Q95": {"annex_iii_area_vs_use_case"},
    "Q104": {"annex_x_overview"},
    "Q6": {"_detect_minimal_risk_inquiry"},
}


def routing(route_paths: list[Path]) -> int:
    """Per arm: targets that reach their family's vetted answer, and controls that do."""
    for path in route_paths:
        rows = _load(path)["rows"]
        targets = [r for r in rows if r["kind"] == "target"]
        controls = [r for r in rows if r["kind"] == "control"]
        hit = [r for r in targets if r["label"] in FAMILY_ROUTES.get(r["family"], set())]
        other = [r for r in targets if r["label"] and r not in hit]
        false = [r for r in controls if r["label"] in FAMILY_ROUTES.get(r["family"], set())]
        print(f"{path.name}: targets {len(hit)}/{len(targets)} reach their family's answer"
              f" (+{len(other)} another curated answer); controls {len(false)}/{len(controls)}"
              f" reach the family's answer")
    return 0


# ── pair the arms ────────────────────────────────────────────────────────────


def _same_offline(m: dict, b: dict) -> bool:
    return m["label"] == b["label"] and (m["answer"], m["references"]) == (
        b["answer"], b["references"])


def changed_ids(main_path: Path, branch_paths: list[Path], out: Path) -> int:
    """The rows any branch serves differently from main offline: what ``live`` asks."""
    main_rows = {r["id"]: r for r in _load(main_path)["rows"]}
    ids = sorted({r["id"] for path in branch_paths for r in _load(path)["rows"]
                  if not _same_offline(main_rows[r["id"]], r)})
    _save(out, {"main": str(main_path), "branches": [str(p) for p in branch_paths], "ids": ids})
    print(f"wrote {out}: {len(ids)} rows differ")
    return 0


def pairs(set_name: str, live_path: Path, main_path: Path, branch_path: Path, out: Path) -> int:
    live_rows = {r["id"]: r for r in _load(live_path)["rows"]}
    main_rows = {r["id"]: r for r in _load(main_path)["rows"]}
    branch_rows = {r["id"]: r for r in _load(branch_path)["rows"]}
    rows = []
    for rid, b in branch_rows.items():
        a, m = live_rows.get(rid, {}), main_rows[rid]
        row = {k: b[k] for k in ("id", "family", "kind", "question")}
        row.update(label_main=m["label"], label_branch=b["label"])
        if _same_offline(m, b):
            # The branch serves this question exactly as main does: a tie by
            # construction, so no production answer is needed.
            row.update(B_source="unchanged offline", changed=False)
            rows.append(row)
            continue
        if "answer" not in a:
            row.update(skipped="no production answer", changed=False)
            rows.append(row)
            continue
        row.update(A=a["answer"], A_refs=a["references"] or [])
        if b["label"] and not b["references"]:
            # A curated verdict always cites; no references means the offline
            # scope gate refused the question, which production's LLM gate may not.
            row.update(skipped="refused offline by the scope gate", changed=False)
            rows.append(row)
            continue
        elif b["label"]:
            row.update(B=b["answer"], B_refs=b["references"], B_source="branch offline")
        elif m["label"]:
            row.update(skipped="route lost on the branch", changed=False)
            rows.append(row)
            continue
        else:
            # Neither checkout answers it with a curated verdict, so live it takes
            # the same Stage-2 path in both arms. A different offline draft here
            # would mean the change reached the ordinary path; it is recorded.
            row.update(B=row["A"], B_refs=row["A_refs"], B_source="unchanged path",
                       offline_draft_differs=(m["answer"], m["references"])
                       != (b["answer"], b["references"]))
        # On a question main already answers with a curated verdict, production
        # should serve main's offline answer; a difference is recorded, not hidden.
        row["A_is_main_offline"] = bool(m["label"]) and row["A"] == m["answer"]
        row["changed"] = (row["A"], row["A_refs"]) != (row["B"], row["B_refs"])
        rows.append(row)
    data = {"set": set_name, "live": str(live_path), "commit": _load(live_path).get("commit"),
            "rows": rows, "changed": sum(r["changed"] for r in rows)}
    _save(out, data)
    print(f"wrote {out}: {data['changed']} changed of {len(rows)}")
    return 0


# ── judge ────────────────────────────────────────────────────────────────────


def _absolute_judge():
    spec = importlib.util.spec_from_file_location("r467_heldout_judge", R467_JUDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._judge


#: The pairwise judge dials the wrapper through the Stage-2 provider, which is
#: off unless this environment is set; ``ab_judge`` scores a failed call as a
#: tie. R468's first judge run lacked it and printed 41 ties of 41 with no call
#: made, so every failed call here is retried, then recorded as a failure.
JUDGE_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "openai_wrapper",
    "OPENAI_API_BASE": "http://127.0.0.1:8000/v1",
    "OPENAI_API_KEY": "dummy",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
}


def judge(pairs_path: Path) -> int:
    os.environ.update(JUDGE_ENV)
    sys.path.insert(0, str(REPO))
    from evals.harness.ab_judge import ArmAnswer, _pairwise_verdict_detail
    from evals.judge.runner import _load_article_summaries, _resolve_caller, set_judge_model

    data = _load(pairs_path)
    positions = _load(REFERENCES)["positions"]
    set_judge_model(JUDGE_MODEL)
    resolved = _resolve_caller("wrapper", timeout_s=300)
    errors: list[str] = []

    def caller(prompt: str) -> dict:
        # The CLI behind the wrapper sometimes ends a call with "Reached maximum
        # number of turns (1)"; a retry usually clears it.
        for _ in range(3):
            out = resolved(prompt)
            if "judge_error" not in out:
                return out
        errors.append(str(out["judge_error"])[:200])
        return out

    summaries = _load_article_summaries()
    absolute = _absolute_judge()
    for row in data["rows"]:
        if not row.get("changed"):
            continue
        if "pairwise" not in row:
            a = ArmAnswer(answer=row["A"], refs=row["A_refs"], latency_ms=0.0, http_status=200)
            b = ArmAnswer(answer=row["B"], refs=row["B_refs"], latency_ms=0.0, http_status=200)
            rd = {"question": row["question"], "expected_keywords": [], "expected_refs": []}
            before = len(errors)
            verdicts = {}
            for ax in AXES:
                verdict, agreed = _pairwise_verdict_detail(rd, ax, a, b, caller, summaries)
                verdicts[ax] = {"verdict": verdict, "agreed": agreed}
            if len(errors) > before:
                row["judge_failed"] = errors[-1]
                _save(pairs_path, data)
                print(f"{row['id']}: pairwise judge failed after retries: {errors[-1]}", flush=True)
                continue
            row.pop("judge_failed", None)
            row["pairwise"] = verdicts
            _save(pairs_path, data)
        if row["kind"] == "target" and "grade" not in row:
            reference = positions[row["family"]]
            grade = {}
            for arm in ("A", "B"):
                for _ in range(3):
                    try:
                        grade[arm] = absolute(row["question"], reference, row[arm])
                    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
                        grade[arm] = {"verdict": "judge_error", "error": repr(exc)[:200]}
                    if grade[arm].get("verdict") in GRADE:
                        break
            row["grade"] = grade
            _save(pairs_path, data)
        grades = {arm: row.get("grade", {}).get(arm, {}).get("verdict") for arm in ("A", "B")}
        print(f"{row['id']}: {({ax: row['pairwise'][ax]['verdict'] for ax in AXES})} {grades}",
              flush=True)
    data["judge_model"] = JUDGE_MODEL
    data["judge_failed"] = sum(1 for r in data["rows"] if r.get("judge_failed"))
    _save(pairs_path, data)
    print(f"judge failed on {data['judge_failed']} pairs (excluded, not ties)")
    return 0


# ── report ───────────────────────────────────────────────────────────────────


def _sign_p(wins: int, losses: int) -> float:
    """Exact two-sided sign test (ties excluded)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def report(paths: list[Path]) -> int:
    for path in paths:
        data = _load(path)
        rows = [r for r in data["rows"] if "skipped" not in r]
        for kind in sorted({r["kind"] for r in rows}):
            part = [r for r in rows if r["kind"] == kind]
            changed = [r for r in part if r["changed"]]
            print(f"\n## {data['set']} / {kind}: {len(part)} rows, curated on main "
                  f"{sum(bool(r['label_main']) for r in part)}, on the branch "
                  f"{sum(bool(r['label_branch']) for r in part)}, changed {len(changed)}")
            for ax in AXES:
                v = [r["pairwise"][ax]["verdict"] for r in changed if "pairwise" in r]
                wins, losses = v.count("B"), v.count("A")
                print(f"  pairwise {ax:<12} B {wins}  A {losses}  tie {len(v) - wins - losses}"
                      f"  p={_sign_p(wins, losses):.4f}")
            graded = [r for r in changed if "grade" in r]
            if graded:
                better = worse = 0
                for r in graded:
                    ga = GRADE.get(r["grade"]["A"].get("verdict"))
                    gb = GRADE.get(r["grade"]["B"].get("verdict"))
                    if ga is None or gb is None:
                        continue
                    better += gb > ga
                    worse += gb < ga
                dist = {arm: {g: sum(r["grade"][arm].get("verdict") == g for r in graded)
                              for g in (*GRADE, "judge_error", "unparsed")} for arm in ("A", "B")}
                print(f"  absolute A {dist['A']}")
                print(f"  absolute B {dist['B']}")
                print(f"  absolute better {better}  worse {worse}  p={_sign_p(better, worse):.4f}")
            failed = [r["id"] for r in changed if r.get("judge_failed")]
            if failed:
                print(f"  judge failed (excluded, not ties): {failed}")
            skipped = [r for r in data["rows"] if "skipped" in r and r["kind"] == kind]
            if skipped:
                print(f"  skipped: {[(r['id'], r['skipped']) for r in skipped]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("live", "route"):
        p = sub.add_parser(name)
        p.add_argument("--set", required=True, choices=("heldout", "heldout2", "dev", "pool"))
        p.add_argument("--out", required=True)
        p.add_argument("--questions")
        if name == "route":
            p.add_argument("--repo", required=True)
        else:
            p.add_argument("--ids-file", help="a changed-ids output: ask only those rows")
    p = sub.add_parser("changed")
    p.add_argument("--main", required=True)
    p.add_argument("--branch", required=True, action="append")
    p.add_argument("--out", required=True)
    p = sub.add_parser("pairs")
    p.add_argument("--set", required=True)
    p.add_argument("--live", required=True)
    p.add_argument("--main", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("judge")
    p.add_argument("pairs")
    p = sub.add_parser("labels")
    p.add_argument("--repo", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--corpus", default=str(REPO / "scratch" / "r465_ab_corpus.json"))
    p = sub.add_parser("label-diff")
    p.add_argument("--main", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("report")
    p.add_argument("pairs", nargs="+")
    p = sub.add_parser("routing")
    p.add_argument("routes", nargs="+")
    args = ap.parse_args()
    questions = Path(args.questions) if getattr(args, "questions", None) else None
    if args.cmd == "live":
        ids = set(_load(Path(args.ids_file))["ids"]) if args.ids_file else None
        return live(args.set, Path(args.out), questions, ids)
    if args.cmd == "changed":
        return changed_ids(Path(args.main), [Path(b) for b in args.branch], Path(args.out))
    if args.cmd == "route":
        return route(args.set, Path(args.repo), Path(args.out), questions)
    if args.cmd == "pairs":
        return pairs(args.set, Path(args.live), Path(args.main), Path(args.branch), Path(args.out))
    if args.cmd == "judge":
        return judge(Path(args.pairs))
    if args.cmd == "labels":
        return labels(Path(args.repo), Path(args.out), Path(args.corpus))
    if args.cmd == "label-diff":
        return label_diff(Path(args.main), Path(args.branch), Path(args.out))
    if args.cmd == "routing":
        return routing([Path(p) for p in args.routes])
    return report([Path(p) for p in args.pairs])


if __name__ == "__main__":
    sys.exit(main())
