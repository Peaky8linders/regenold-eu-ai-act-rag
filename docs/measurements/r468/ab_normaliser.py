"""R468 — paired A/B of the normaliser fixes on significant samples.

The measurement rule (AGENTS.md, operator directive 2026-10-25): a paired A/B
test on a seeded random sample sized for significance, never a replay of the
full official 110. Every pool here excludes the official 110's questions.

Two parts, each paired so only the change differs:

* ``live`` (fixes 1 and 2: list inlining, meta-leak word start). Each sampled
  question is asked ONCE through the in-process route with live Stage-2 (the
  local wrapper). The text entering the normaliser is captured, with the
  request-scoped switches in force at that moment, and put through both arms:
  ``REGENOLD_LIST_INLINE`` / ``REGENOLD_META_LEAK_WORD_START`` off (A) and on (B).
  Same generated text, so generation variance cannot enter the comparison.
* ``curated`` (fix 3: every curated sentence anchored). The answers are
  deterministic, so both arms run offline: arm A from an ``origin/main``
  worktree, arm B from this branch, on the same questions.

``judge`` sends each discordant pair to the position-swapped pairwise judge
(``evals.harness.ab_judge`` helpers; ``claude-sonnet-5`` over the wrapper) on the
correctness, conciseness and tone axes, and reports a two-sided sign test per
axis. Identical pairs are exact ties and are not judged.

Usage (repo root):
  .venv/Scripts/python.exe docs/measurements/r468/ab_normaliser.py live --n 120
  .venv/Scripts/python.exe docs/measurements/r468/ab_normaliser.py rearm ab_live.json
  .venv/Scripts/python.exe docs/measurements/r468/ab_normaliser.py curated-pool --n 60
  .venv/Scripts/python.exe docs/measurements/r468/ab_normaliser.py curated-arm \
      --repo PATH --questions POOL.json --out ARM.json
  .venv/Scripts/python.exe docs/measurements/r468/ab_normaliser.py curated-pairs \
      --a ARM_A.json --b ARM_B.json --out PAIRS.json
  .venv/Scripts/python.exe docs/measurements/r468/ab_normaliser.py judge PAIRS.json
"""
from __future__ import annotations

import argparse
import ast
import glob
import inspect
import json
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SEED = 468
FLAGS = ("REGENOLD_LIST_INLINE", "REGENOLD_META_LEAK_WORD_START")
AXES = ("correctness", "conciseness", "tone")
JUDGE_MODEL = "claude-sonnet-5"
OFFLINE_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "cli",
    "OPENAI_API_BASE": "http://127.0.0.1:1/v1",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
}
LIVE_ENV = {
    "REGENOLD_SKIP_DOTENV": "1",
    "P2P_GRAPH_RAG_PROVIDER": "openai_wrapper",
    "OPENAI_API_BASE": "http://127.0.0.1:8000/v1",
    "OPENAI_API_KEY": "dummy",
    "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
}
#: Questions that ask for a set of items: where a model answer lists.
LIST_ASK_RE = re.compile(
    r"\b(?:list|what (?:are|must|should|do|does)|which|obligations?|requirements?|duties|"
    r"include|contain|conditions?|steps|elements|categories|criteria|areas)\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _official_questions() -> set[str]:
    path = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.add(_norm(json.loads(line)["question"]))
    return out


def _probe_questions() -> list[str]:
    sys.path.insert(0, str(REPO))
    from evals.harness.probe_set import load_probe_set

    return [row.messages[-1]["content"] for row in load_probe_set(multiturn=False)]


def _corpus_rephrasings() -> list[str]:
    path = REPO / "scratch" / "r465_ab_corpus.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [r["question"] for r in rows if not r["id"].endswith("_0")]


def _test_questions() -> list[str]:
    out = set()
    for f in glob.glob(str(REPO / "tests" / "*.py")):
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                if 20 <= len(s) <= 300 and s.endswith("?") and "\n" not in s:
                    out.add(s)
    return sorted(out)


def _sample(pool: list[str], n: int) -> list[str]:
    official = _official_questions()
    unique = sorted({q for q in pool if _norm(q) not in official})
    rng = random.Random(SEED)
    return unique if len(unique) <= n else sorted(rng.sample(unique, n))


def _set_env(env: dict[str, str]) -> None:
    os.environ.update(env)
    for name in ("NEO4J_URI", "COHERE_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
                 "AWS_BEARER_TOKEN_BEDROCK"):
        os.environ.pop(name, None)


# ── live: capture once, normalise twice ──────────────────────────────────────


def live(n: int, out_path: Path) -> int:
    _set_env(LIVE_ENV)
    sys.path.insert(0, str(REPO))
    from fastapi.testclient import TestClient

    import app.routes.regenold as route
    from app.engines._graph_rag_impl import _is_curated_authoritative_intercept
    from app.integrations.regenold import models
    from app.main import app
    from app.rate_limit import limiter

    # Curated intercepts skip Stage-2, so they cannot carry a model-written list.
    pool = [q for q in _probe_questions() + _corpus_rephrasings() + _test_questions()
            if LIST_ASK_RE.search(q) and not _is_curated_authoritative_intercept(q)]
    questions = _sample(pool, n)
    print(f"live pool {len(set(pool))} list asks, sample {len(questions)}", flush=True)

    original = route.normalise_answer_for_regenold
    slot: dict = {}

    def spy(text, *args, **kwargs):
        if "text" not in slot:
            slot.update(text=text, args=args, kwargs=kwargs,
                        no_cap=models.answer_no_cap_active(),
                        full_text=models.curated_full_text_active())
        return original(text, *args, **kwargs)

    route.normalise_answer_for_regenold = spy
    limiter.enabled = False
    client = TestClient(app)
    rows = []
    try:
        for i, q in enumerate(questions, 1):
            slot.clear()
            route._ENGINE_CACHE.clear()
            resp = client.post("/api/v1/regenold/eu-ai-act/ask",
                               json=[{"role": "user", "content": q}], timeout=300)
            body = resp.json() if resp.status_code == 200 else {}
            if "text" not in slot:
                print(f"{i}: no normaliser call ({resp.status_code})", flush=True)
                continue
            arms = {}
            for arm, value in (("A", "0"), ("B", "1")):
                for flag in FLAGS:
                    os.environ[flag] = value
                models.set_answer_no_cap(slot["no_cap"])
                models.set_curated_full_text(slot["full_text"])
                arms[arm] = original(slot["text"], *slot["args"], **slot["kwargs"])
            for flag in FLAGS:
                os.environ.pop(flag, None)
            rows.append({"question": q, "raw": slot["text"], "A": arms["A"], "B": arms["B"],
                         "references": body.get("references") or [],
                         "no_cap": slot["no_cap"], "discordant": arms["A"] != arms["B"]})
            print(f"{i}/{len(questions)} discordant={arms['A'] != arms['B']}", flush=True)
    finally:
        route.normalise_answer_for_regenold = original
    out = {"part": "live", "seed": SEED, "n_sampled": len(questions), "rows": rows,
           "discordant": sum(r["discordant"] for r in rows)}
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}: {out['discordant']} discordant of {len(rows)}")
    return 0


def rearm(pairs_path: Path) -> int:
    """Re-normalise a ``live`` capture's saved text with the current code.

    The capture takes about an hour, so a normaliser change made after it
    started is measured by putting the same captured text through both arms
    again; the pairing still holds. Arm A runs with the flags off and must
    reproduce the stored arm A exactly, which checks that the reconstructed call
    (single-turn ``question=``, the captured uncap switch) is the captured one.
    """
    _set_env(OFFLINE_ENV)
    sys.path.insert(0, str(REPO))
    from app.integrations.regenold import models

    data = json.loads(pairs_path.read_text(encoding="utf-8"))
    mismatched = changed = 0
    for row in data["rows"]:
        arms = {}
        for arm, value in (("A", "0"), ("B", "1")):
            for flag in FLAGS:
                os.environ[flag] = value
            models.set_answer_no_cap(row["no_cap"])
            models.set_curated_full_text(False)
            arms[arm] = models.normalise_answer_for_regenold(row["raw"], question=row["question"])
        mismatched += arms["A"] != row["A"]
        if arms["B"] != row["B"]:
            changed += 1
            row.setdefault("B_at_capture", row["B"])
            row["B"] = arms["B"]
            row.pop("verdicts", None)
        row["discordant"] = row["A"] != row["B"]
    for flag in FLAGS:
        os.environ.pop(flag, None)
    if mismatched:
        raise SystemExit(f"arm A did not reproduce on {mismatched} rows; the call differs")
    data["discordant"] = sum(r["discordant"] for r in data["rows"])
    pairs_path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"rearmed {pairs_path}: arm A reproduced on all {len(data['rows'])} rows, "
          f"arm B changed on {changed}, {data['discordant']} discordant")
    return 0


# ── curated: same questions through main's engine and this branch's ──────────


def curated_pool(n: int, out_path: Path) -> int:
    _set_env(OFFLINE_ENV)
    sys.path.insert(0, str(REPO))
    from app.engines import _graph_rag_impl as engine

    source = inspect.getsource(engine._is_curated_authoritative_intercept)
    detectors = [getattr(engine, d) for d in re.findall(r"(_detect_\w+_inquiry)\(question\)", source)]
    pool = _probe_questions() + _corpus_rephrasings() + _test_questions()
    hits = [q for q in pool if any(d(q) for d in detectors)]
    questions = _sample(hits, n)
    out_path.write_text(json.dumps({"seed": SEED, "pool": len(set(hits)), "questions": questions},
                                   indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"curated pool {len(set(hits))} (official 110 excluded), sample {len(questions)} -> {out_path}")
    return 0


def curated_arm(repo: Path, questions_path: Path, out_path: Path) -> int:
    _set_env(OFFLINE_ENV)
    sys.path.insert(0, str(repo))
    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    limiter.enabled = False
    client = TestClient(app)
    questions = json.loads(questions_path.read_text(encoding="utf-8"))["questions"]
    rows = []
    for q in questions:
        body = client.post("/api/v1/regenold/eu-ai-act/ask",
                           json=[{"role": "user", "content": q}]).json()
        rows.append({"question": q, "answer": body.get("answer", ""),
                     "references": body.get("references") or []})
    out_path.write_text(json.dumps({"repo": str(repo), "rows": rows}, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    print(f"wrote {out_path} ({len(rows)} rows from {repo})")
    return 0


def curated_pairs(a_path: Path, b_path: Path, out_path: Path) -> int:
    a = {r["question"]: r for r in json.loads(a_path.read_text(encoding="utf-8"))["rows"]}
    b = {r["question"]: r for r in json.loads(b_path.read_text(encoding="utf-8"))["rows"]}
    rows = []
    for q in a:
        rows.append({"question": q, "A": a[q]["answer"], "B": b[q]["answer"],
                     "references": b[q]["references"], "references_A": a[q]["references"],
                     "discordant": a[q]["answer"] != b[q]["answer"]})
    out = {"part": "curated", "seed": SEED, "n_sampled": len(rows), "rows": rows,
           "discordant": sum(r["discordant"] for r in rows),
           "references_changed": sum(r["references"] != r["references_A"] for r in rows)}
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}: {out['discordant']} discordant answers, "
          f"{out['references_changed']} reference lists changed, of {len(rows)}")
    return 0


# ── judge the discordant pairs ───────────────────────────────────────────────


def judge(pairs_path: Path) -> int:
    # The judge dials the wrapper through the Stage-2 provider, which is off
    # unless this environment is set. The first run of this script did not set
    # it: every call returned ``wrapper_not_configured``, ``ab_judge`` scored each
    # failed call as a tie, and the run printed 41 ties of 41.
    _set_env(LIVE_ENV)
    sys.path.insert(0, str(REPO))
    from evals.harness.ab_judge import ArmAnswer, AxisResult, _pairwise_verdict_detail
    from evals.judge.runner import _load_article_summaries, _resolve_caller, set_judge_model

    data = json.loads(pairs_path.read_text(encoding="utf-8"))
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
    axes = {ax: AxisResult(axis=ax) for ax in AXES}
    done = {r["question"]: r.get("verdicts") for r in data["rows"] if r.get("verdicts")}
    for i, row in enumerate(data["rows"], 1):
        if not row["discordant"]:
            continue
        if done.get(row["question"]):
            verdicts = done[row["question"]]
        else:
            a = ArmAnswer(answer=row["A"], refs=row["references"], latency_ms=0.0, http_status=200)
            b = ArmAnswer(answer=row["B"], refs=row["references"], latency_ms=0.0, http_status=200)
            rd = {"question": row["question"], "expected_keywords": [], "expected_refs": []}
            before = len(errors)
            verdicts = {}
            for ax in AXES:
                verdict, agreed = _pairwise_verdict_detail(rd, ax, a, b, caller, summaries)
                verdicts[ax] = {"verdict": verdict, "agreed": agreed}
            if len(errors) > before:
                # A failed call reads as a tie; never record it as a verdict.
                row["judge_failed"] = errors[-1]
                pairs_path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
                print(f"{i}: judge failed after retries: {errors[-1]}", flush=True)
                continue
            row.pop("judge_failed", None)
            row["verdicts"] = verdicts
            pairs_path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        for ax in AXES:
            v = verdicts[ax]["verdict"]
            r = axes[ax]
            r.wins_b += v == "B"
            r.wins_a += v == "A"
            r.ties += v not in ("A", "B")
            r.swap_agreements += bool(verdicts[ax]["agreed"])
        print(f"{i}: {({ax: verdicts[ax]['verdict'] for ax in AXES})}", flush=True)
    data["judge_model"] = JUDGE_MODEL
    data["axes"] = {ax: {"wins_B": r.wins_b, "wins_A": r.wins_a, "ties": r.ties,
                         "p_value": r.p_value(), "verdict": r.verdict()} for ax, r in axes.items()}
    data["judge_failed"] = sum(1 for r in data["rows"] if r.get("judge_failed"))
    pairs_path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(data["axes"], indent=1))
    print(f"judge failed on {data['judge_failed']} pairs (excluded, not ties)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("live")
    p.add_argument("--n", type=int, default=120)
    p.add_argument("--out", default=str(HERE / "ab_live.json"))
    p = sub.add_parser("rearm")
    p.add_argument("pairs")
    p = sub.add_parser("curated-pool")
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--out", default=str(HERE / "ab_curated_questions.json"))
    p = sub.add_parser("curated-arm")
    p.add_argument("--repo", required=True)
    p.add_argument("--questions", default=str(HERE / "ab_curated_questions.json"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("curated-pairs")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--out", default=str(HERE / "ab_curated.json"))
    p = sub.add_parser("judge")
    p.add_argument("pairs")
    args = ap.parse_args()
    if args.cmd == "live":
        return live(args.n, Path(args.out))
    if args.cmd == "rearm":
        return rearm(Path(args.pairs))
    if args.cmd == "curated-pool":
        return curated_pool(args.n, Path(args.out))
    if args.cmd == "curated-arm":
        return curated_arm(Path(args.repo), Path(args.questions), Path(args.out))
    if args.cmd == "curated-pairs":
        return curated_pairs(Path(args.a), Path(args.b), Path(args.out))
    return judge(Path(args.pairs))


if __name__ == "__main__":
    sys.exit(main())
