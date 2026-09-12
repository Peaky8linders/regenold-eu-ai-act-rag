"""R411 — deterministic corpus A/B over the OFFICIAL 110 questions.

Answers a narrow, cheap question that keeps costing this repo rounds: *does
flipping this env flag change the answer or the reference set on the frozen
corpus, and on which rows?* Runs the real route with the LLM transport pointed
at a dead port, so the deterministic Stage-1 path is what is measured — no
network, no LLM, seconds per arm, and the comparison is like-for-like because
both arms share the same offline environment.

Usage:

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe \
        docs/measurements/r411/corpus_ab.py \
        --flag REGENOLD_GENERAL_VERDICT_V2 --baseline 0 --branch 1

Prints the rows whose answer or references changed, the reference-axis deltas
(loose / strict / conciseness, using the official rubric) and the count of rows
whose expected reference heads would be LOST or GAINED — the hard-rule-#8 read.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Deterministic offline environment — identical to the R409 frontier instrument.
os.environ["REGENOLD_SKIP_DOTENV"] = "1"
os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1/v1"
os.environ["REGENOLD_QUERY_DENOISER"] = "0"
os.environ["REGENOLD_EXTERNAL_EMBEDDINGS"] = "0"
for _f in (
    "REGENOLD_CLOSED_SET_COMPLETENESS_GUARD",
    "REGENOLD_EXCEPTION_LIMB_GUARD",
    "REGENOLD_VERDICT_LEAD_GUARD",
    "REGENOLD_PUSHBACK_KEEP_CONTRACT",
    "REGENOLD_GOVERNING_PROVISION_CLAUSE",
):
    os.environ[_f] = "1"


def _load_corpus() -> list[dict]:
    return [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_arm_inprocess(rows: list[dict]) -> dict[str, dict]:
    """Run one arm under the CURRENT environment (used by the --worker mode).

    Each arm must run in a FRESH subprocess: several gates are read once at
    import/config time, so mutating ``os.environ`` between two arms in one
    interpreter measures a mix of the two configurations (observed: the second
    arm 500s on rows whose gates were captured at import).
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import limiter

    # The route's anon bucket is 30/min; this probe walks all 110 rows back to
    # back, so it must opt out of the limiter or the tail of the corpus reads as
    # 429 rather than as an answer. Measurement-only; the app is untouched.
    limiter.enabled = False

    client = TestClient(app)
    out: dict[str, dict] = {}
    for r in rows:
        resp = client.post(
            "/api/v1/regenold/eu-ai-act/ask",
            json=[{"role": "user", "content": r["question"]}],
        )
        data = resp.json() if resp.status_code == 200 else {}
        out[r["id"]] = {
            "answer": data.get("answer", "") or "",
            "references": [str(x).strip() for x in (data.get("references") or [])],
            "status": resp.status_code,
        }
    return out


def _run_arm_subprocess(flag: str, value: str, tmp: Path) -> dict[str, dict]:
    """Run one arm in a clean subprocess with the flag set before any import."""
    import subprocess

    env = dict(os.environ)
    env[flag] = value
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(tmp)]
    proc = subprocess.run(
        cmd, env=env, capture_output=True, text=True, cwd=str(REPO), check=False
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        raise SystemExit(f"arm {flag}={value} failed (exit {proc.returncode})")
    return json.loads(tmp.read_text(encoding="utf-8"))


def _ref_head(ref: str) -> str:
    from evals.official.rubric import ref_head

    return ref_head(ref) or ref


def main() -> int:
    import tempfile

    ap = argparse.ArgumentParser()
    ap.add_argument("--flag", default="")
    ap.add_argument("--baseline", default="0")
    ap.add_argument("--branch", default="1")
    ap.add_argument("--max-print", type=int, default=25)
    ap.add_argument("--worker", default="", help=argparse.SUPPRESS)
    args = ap.parse_args()

    rows = _load_corpus()

    if args.worker:
        out = _run_arm_inprocess(rows)
        Path(args.worker).write_text(json.dumps(out), encoding="utf-8")
        return 0

    if not args.flag:
        ap.error("--flag is required (unless --worker)")

    print(f"corpus rows: {len(rows)}   flag: {args.flag}  {args.baseline} -> {args.branch}")

    arms: list[dict[str, dict]] = []
    with tempfile.TemporaryDirectory() as td:
        for i, val in enumerate((args.baseline, args.branch)):
            print(f"\n--- running arm {args.flag}={val} (subprocess) ...", flush=True)
            arms.append(
                _run_arm_subprocess(args.flag, val, Path(td) / f"arm{i}.json")
            )

    base, branch = arms
    errs = sorted(
        {
            r["id"]
            for r in rows
            if base[r["id"]].get("status") != 200
            or branch[r["id"]].get("status") != 200
        }
    )
    if errs:
        print(f"\nWARNING non-200 rows: {len(errs)}: {errs[:12]}")
    changed = [r for r in rows if base[r["id"]] != branch[r["id"]]]
    print(f"\nrows changed: {len(changed)} / {len(rows)}")

    from evals.official.rubric import (
        reference_conciseness,
        reference_correctness_loose,
        reference_correctness_strict,
    )

    def agg(arm: dict[str, dict]) -> tuple[float, float, float, int]:
        lo = st = co = 0.0
        n = 0
        for r in rows:
            exp = r.get("expected_refs") or []
            if not exp or arm[r["id"]].get("status") != 200:
                continue
            refs = arm[r["id"]]["references"]
            rlo = reference_correctness_loose(refs, exp)
            rst = reference_correctness_strict(refs, exp)
            rco = reference_conciseness(refs, exp)
            if rlo is None or rst is None or rco is None:
                continue
            n += 1
            lo += rlo
            st += rst
            co += rco
        return (lo / n, st / n, co / n, n)

    bl, bs, bc, bn = agg(base)
    nl, ns, nc, _ = agg(branch)
    print(f"\nreference axes (rows with expected refs = {bn}):")
    print(f"  ref_loose  {bl:.4f} -> {nl:.4f}  ({nl - bl:+.4f})")
    print(f"  ref_strict {bs:.4f} -> {ns:.4f}  ({ns - bs:+.4f})")
    print(f"  ref_conc   {bc:.4f} -> {nc:.4f}  ({nc - bc:+.4f})")

    # Hard rule #8 — expected reference HEADS lost / gained.
    lost = gained = 0
    for r in rows:
        exp = {_ref_head(x) for x in (r.get("expected_refs") or [])}
        if not exp:
            continue
        b = {_ref_head(x) for x in base[r["id"]]["references"]}
        n = {_ref_head(x) for x in branch[r["id"]]["references"]}
        # An expected head the BASELINE already carried and the branch drops is a
        # gold loss (hard rule #8); the reverse is a gain.
        lost += len((exp & b) - n)
        gained += len((exp & n) - b)
    print(f"\nhard rule #8: expected heads LOST = {lost}   GAINED = {gained}")

    print(f"\nchanged rows (first {args.max_print}):")
    for r in changed[: args.max_print]:
        b, n = base[r["id"]], branch[r["id"]]
        print("=" * 96)
        print(f"[{r['id']}] {r['question'][:100]}")
        print(f"   base  refs: {b['references']}")
        print(f"   branch refs: {n['references']}")
        if b["answer"] != n["answer"]:
            print(f"   base  ans: {b['answer'][:190]}")
            print(f"   branch ans: {n['answer'][:190]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
