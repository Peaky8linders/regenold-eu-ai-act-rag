"""R461 promotion canary — the citation budget, on the LIVE published endpoint.

The gate (``COUNT-ONLY-CONFIRM.md``) decided the promotion; this answers a
different question, which no board can: **does the deployed build serve, does the
budget bite on the wire, and did anything collapse?** It is a canary, not a
verdict — 8 fixed questions, one draw each, read as a direction.

Three phases, run in this order around the merge:

    pre      production BEFORE the promotion is deployed (pre-R461 commit, no
             conciseness block at all)
    post     production AFTER Railway serves the merge commit
    compare  the before/after table and the gates

The question set is FIXED and drawn from the official hard board (six direct asks
whose gold head is 1-2 provisions, two fact-pattern asks), so the two phases are
the same questions on the same endpoint and the delta is the deploy. Each row's
budget comes from :func:`app.engines.answer_need.calibration_citation_budget`, the
lever's own definition, never a copy of it here.

Gates, all of them reported PASS/FAIL with the numbers behind them:

* ``deploy``    — ``/healthz`` commit is the expected one (``--expect-commit``)
* ``health``    — ``/healthz`` ok and ``/healthz/llm`` ``llm_ok``
* ``transport`` — every question answered 200, non-empty, not a refusal
* ``budget``    — mean references DOWN and the share within the stated budget
                  not down
* ``integrity`` — answers not collapsed (>= 70% of the pre-promotion mean chars)

Run from the worktree root:

    ../../.venv/Scripts/python.exe -m docs.measurements.r461.production_canary --phase pre
    ../../.venv/Scripts/python.exe -m docs.measurements.r461.production_canary --phase post
    ../../.venv/Scripts/python.exe -m docs.measurements.r461.production_canary --phase compare
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
HOST = "https://regenold-eu-ai-act-rag-production.up.railway.app"
ASK = HOST + "/api/v1/regenold/eu-ai-act/ask"

#: (id, question) — the official hard board's instruction (``--stride 3``) rows,
#: six direct asks and two fact-pattern asks, byte-identical in both phases.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("rg_028", "According to Article 1, what is the objective of the EU AI Act?"),
    (
        "rg_034",
        "Under the EU AI Act, what jurisdiction does the Court of Justice of the "
        "European Union have over Commission decisions fixing fines on providers of "
        "general-purpose AI models, and what can the Court do with the fine?",
    ),
    (
        "rg_040",
        "Under the EU AI Act, when a high-risk AI system is found to conform with "
        "the requirements, what information must the Union technical documentation "
        "assessment certificate contain?",
    ),
    (
        "rg_043",
        "Under Article 10(5) of the EU AI Act, when may a provider of a high-risk AI "
        "system process special categories of personal data for bias detection and "
        "correction, and what key safeguards/conditions must be met?",
    ),
    (
        "rg_049",
        "Under the EU AI Act (Regulation (EU) 2024/1689) Article 95, who may draw up "
        "codes of conduct, and which bodies must encourage and facilitate their "
        "drawing up?",
    ),
    (
        "rg_052",
        "Under the EU AI Act, what minimum elements must a provider's quality "
        "management system (QMS) for high-risk AI systems include? List the "
        "required elements.",
    ),
    (
        "rg_004",
        'I have a medical device that has an AI system as a safety component. The '
        'medical device is classified "medium-risk" and undergoes a 3rd party '
        'conformity assessment. Is the AI system "medium risk" too? If yes, why? If '
        "not, why not?",
    ),
    (
        "rg_007",
        "We want to deploy an AI system that performs biometric verification solely "
        "to confirm that a specific natural person is the person he or she claims to "
        "be. Is this system prohibited? Is it high-risk?",
    ),
)

_REFUSALS = ("outside the scope", "not part of the eu ai act", "i only answer")


def _budget(question: str) -> int:
    from app.engines.answer_need import calibration_citation_budget

    return calibration_citation_budget(question)


def _api_key(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        import app.config  # noqa: F401, PLC0415 — loads .env into os.environ
    except Exception:  # noqa: BLE001 — a key is optional; the anon tier exists
        pass
    return os.environ.get("P2P_REGENOLD_API_KEY") or os.environ.get("REGENOLD_API_KEY")


def _get_json(url: str, api_key: str | None, timeout: float) -> tuple[dict | None, int, str]:
    headers = {"Accept": "application/json", "User-Agent": "regenold-r461-canary"}
    if api_key:
        headers["X-Regenold-Api-Key"] = api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status, ""
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return None, exc.code, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001 — a probe must not raise
        return None, 0, f"{type(exc).__name__}: {exc}"


def _health(api_key: str | None, timeout: float) -> dict:
    out = {}
    for name, path in (("healthz", "/healthz"), ("llm", "/healthz/llm")):
        body, status, error = _get_json(HOST + path, api_key, timeout)
        out[name] = {"status": status, "error": error, "body": body or {}}
    return out


def _ask(api_key: str | None, question: str, timeout: float) -> dict:
    from evals.bench._http_retry import post_json_with_retry

    payload = [{"role": "user", "content": question}]
    start = time.time()
    body, latency_ms, status, error, attempts, _retried = post_json_with_retry(
        ASK, payload, api_key, timeout, user_agent="regenold-r461-canary"
    )
    answer = str((body or {}).get("answer") or "")
    refs = [str(r) for r in ((body or {}).get("references") or [])]
    return {
        "http_status": status,
        "error": error,
        "attempts": attempts,
        "latency_ms": round(latency_ms or (time.time() - start) * 1000.0, 1),
        "n_refs": len(refs),
        "refs": refs,
        "answer_chars": len(answer),
        "answer_head": answer[:200],
        "refusal": any(m in answer.lower() for m in _REFUSALS),
        "telemetry": {
            k: (body or {}).get(k)
            for k in ("confidence", "kb_version", "retrieval_path")
            if k in (body or {})
        },
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _summary(records: list[dict]) -> dict:
    rows = [r for r in records if r.get("kind") == "ask"]
    n = len(rows) or 1
    in_budget = [r for r in rows if r["n_refs"] <= r["budget"]]
    return {
        "rows": len(rows),
        "mean_refs": round(sum(r["n_refs"] for r in rows) / n, 3),
        "mean_answer_chars": round(sum(r["answer_chars"] for r in rows) / n, 1),
        "in_budget": len(in_budget),
        "in_budget_pct": round(100.0 * len(in_budget) / n, 1),
        "refs_by_row": {r["id"]: r["n_refs"] for r in rows},
        "budgets": {r["id"]: r["budget"] for r in rows},
    }


def _run_phase(phase: str, api_key: str | None, timeout: float) -> int:
    records: list[dict] = []
    health = _health(api_key, timeout)
    commit = str(health["healthz"]["body"].get("commit") or "")
    records.append(
        {
            "kind": "health",
            "phase": phase,
            "commit": commit,
            "deployment_id": health["healthz"]["body"].get("deployment_id"),
            "healthz_status": health["healthz"]["status"],
            "llm_ok": health["llm"]["body"].get("llm_ok"),
            "provider": health["llm"]["body"].get("provider"),
            "detail": health,
        }
    )
    print(f"[{phase}] /healthz commit={commit} llm_ok={health['llm']['body'].get('llm_ok')}")
    for qid, question in QUESTIONS:
        row = _ask(api_key, question, timeout)
        row.update(
            {"kind": "ask", "phase": phase, "id": qid, "budget": _budget(question),
             "question": question}
        )
        records.append(row)
        print(
            f"  {qid}  refs={row['n_refs']:>2}/{row['budget']}  "
            f"chars={row['answer_chars']:>5}  {row['latency_ms']:>8.0f} ms  "
            f"http={row['http_status']} {row['error'] or ''}"
        )
    _write_jsonl(OUT / f"canary-{phase}.jsonl", records)
    (OUT / f"canary-{phase}.json").write_text(
        json.dumps({"phase": phase, "commit": commit, "summary": _summary(records),
                    "health": health}, indent=1),
        encoding="utf-8",
    )
    print(f"wrote canary-{phase}.jsonl / .json")
    return 0


def _gate(label: str, ok: bool, detail: str) -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<10} {detail}")
    return ok


def _compare(expect_commit: str | None) -> int:
    pre_path, post_path = OUT / "canary-pre.jsonl", OUT / "canary-post.jsonl"
    for path in (pre_path, post_path):
        if not path.exists():
            raise SystemExit(f"missing {path.name}: run that phase first")
    pre_rows, post_rows = _read_jsonl(pre_path), _read_jsonl(post_path)
    pre, post = _summary(pre_rows), _summary(post_rows)
    pre_commit = next(r["commit"] for r in pre_rows if r["kind"] == "health")
    post_commit = next(r["commit"] for r in post_rows if r["kind"] == "health")
    post_llm = next(r for r in post_rows if r["kind"] == "health")

    print(f"\nR461 PROMOTION CANARY  pre={pre_commit}  post={post_commit}")
    print(f"  {'row':<8}{'budget':>7}{'pre refs':>9}{'post refs':>10}{'pre chars':>10}{'post chars':>11}")
    for qid, _q in QUESTIONS:
        print(
            f"  {qid:<8}{pre['budgets'].get(qid, 0):>7}"
            f"{pre['refs_by_row'].get(qid, 0):>9}{post['refs_by_row'].get(qid, 0):>10}"
            f"{next(r['answer_chars'] for r in pre_rows if r.get('id') == qid):>10}"
            f"{next(r['answer_chars'] for r in post_rows if r.get('id') == qid):>11}"
        )
    print(
        f"  mean refs {pre['mean_refs']} -> {post['mean_refs']}   "
        f"in budget {pre['in_budget']}/{pre['rows']} -> {post['in_budget']}/{post['rows']}   "
        f"mean chars {pre['mean_answer_chars']} -> {post['mean_answer_chars']}"
    )
    print("\ngates:")
    ok = True
    ok &= _gate(
        "deploy",
        bool(expect_commit) and post_commit.startswith(expect_commit[:12]) if expect_commit
        else post_commit != pre_commit,
        f"post commit {post_commit}"
        + (f" (expected {expect_commit[:12]})" if expect_commit else f" (pre was {pre_commit})"),
    )
    ok &= _gate("health", bool(post_llm.get("llm_ok")) and post_llm["healthz_status"] == 200,
                f"llm_ok={post_llm.get('llm_ok')} status={post_llm['healthz_status']}")
    bad = [r["id"] for r in post_rows if r.get("kind") == "ask"
           and (r["http_status"] != 200 or not r["answer_chars"] or r["refusal"])]
    ok &= _gate("transport", not bad, f"{post['rows']} answered, offenders={bad or 'none'}")
    ok &= _gate(
        "budget",
        post["mean_refs"] < pre["mean_refs"] and post["in_budget"] >= pre["in_budget"],
        f"mean refs {pre['mean_refs']}->{post['mean_refs']}, "
        f"in budget {pre['in_budget']}->{post['in_budget']}",
    )
    ok &= _gate(
        "integrity",
        post["mean_answer_chars"] >= 0.7 * pre["mean_answer_chars"]
        and post["mean_answer_chars"] > 300,
        f"mean chars {pre['mean_answer_chars']}->{post['mean_answer_chars']}",
    )
    print(f"\nCANARY {'PASS' if ok else 'FAIL'}")

    lines = [
        "# R461 promotion canary",
        "",
        f"Endpoint `{HOST}` — 8 fixed official hard-board questions, one draw each.",
        f"pre commit `{pre_commit}` → post commit `{post_commit}`.",
        "",
        "| row | budget | pre refs | post refs | pre chars | post chars |",
        "| :-- | --: | --: | --: | --: | --: |",
    ]
    for qid, _q in QUESTIONS:
        lines.append(
            f"| `{qid}` | {pre['budgets'].get(qid, 0)} | {pre['refs_by_row'].get(qid, 0)} |"
            f" {post['refs_by_row'].get(qid, 0)} |"
            f" {next(r['answer_chars'] for r in pre_rows if r.get('id') == qid)} |"
            f" {next(r['answer_chars'] for r in post_rows if r.get('id') == qid)} |"
        )
    lines += [
        "",
        f"mean refs **{pre['mean_refs']} → {post['mean_refs']}**, in budget"
        f" **{pre['in_budget']}/{pre['rows']} → {post['in_budget']}/{post['rows']}**,"
        f" mean chars {pre['mean_answer_chars']} → {post['mean_answer_chars']}.",
        "",
        f"Gates: **{'PASS' if ok else 'FAIL'}**"
        f" — pre `{pre_commit}`, post `{post_commit}`.",
        "",
    ]
    (OUT / "CANARY.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "canary-compare.json").write_text(
        json.dumps({"pre": pre, "post": post, "pre_commit": pre_commit,
                    "post_commit": post_commit, "pass": bool(ok)}, indent=1),
        encoding="utf-8",
    )
    print("wrote CANARY.md / canary-compare.json")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["pre", "post", "compare"], required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--expect-commit", default=None)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    if args.phase == "compare":
        return _compare(args.expect_commit)
    return _run_phase(args.phase, _api_key(args.api_key), args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
