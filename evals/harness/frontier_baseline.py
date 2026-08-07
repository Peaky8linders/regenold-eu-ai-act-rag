"""R317 — frontier-model baseline arm (the "are we SOTA?" measurement).

WHY THIS EXISTS
---------------
R280 ran the only valid frontier head-to-head this project has: the same
questions, the same scorer, arm A = our RAG, arm B = a raw frontier model with
NO retrieval and NO web search. It found our retrieval BEATS a frontier model
(Ref Strict 55.1 vs 46.8) while our answer layer LOSES to it (keyword recall
78.6 vs 88.6).

That runner was never committed. ``git log --all -- '**/run_frontier_baseline.py'``
is empty; it lived in an untracked ``scratchpad/`` that no longer exists, so only
its output sidecars survived and the measurement could not be reproduced. This
module is the committed replacement, so the comparison is repeatable.

WHAT IT MEASURES, HONESTLY
--------------------------
The frontier arm is DELIBERATELY HANDICAPPED: no retrieval, no web search, no
tools -- just the model's parametric knowledge of Regulation (EU) 2024/1689.
That is the correct control for "does our retrieval layer earn its keep?", and
it makes a frontier win STRONGER evidence against us, not weaker. It is NOT a
claim about what a frontier model with search would score.

Both arms are scored by the SAME functions the competition gate uses
(``evals.bench.metrics``) against the SAME gold, so the comparison is apples to
apples on references. The answer axis uses keyword recall as a proxy -- the
official answer formula is not disclosed (R280 s5), so do not read the answer
numbers as the official ones.

MODEL-NAME CAVEAT (R290)
------------------------
The wrapper echoes the requested ``model`` back in its response. That echo is
NOT proof of which model actually served the request -- R290 found an in-wrapper
alias silently downgrading opus-5 to opus-4-8 while still echoing opus-5. The
echo is recorded per row for audit, but treat the arm's identity as "what we
asked for", and verify separately with ``claude -p --model X`` if it matters.

USAGE
-----
    # frontier arm
    .venv/Scripts/python.exe -m evals.harness.frontier_baseline \\
        --model claude-opus-5 --label r317-frontier-opus5

    # then compare against a recorded arm of OURS
    .venv/Scripts/python.exe -m evals.harness.frontier_baseline --compare \\
        --ours evals/bench/results/easyhard-r282-fullprod-clean-A.ckpt.jsonl \\
        --theirs evals/bench/results/frontier-r317-frontier-opus5.ckpt.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics as st
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.bench.metrics import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)
from evals.harness.probe_set import load_probe_set  # noqa: E402

RESULTS = REPO / "evals/bench/results"

# The frontier arm gets the SAME output contract our wire must satisfy, so the
# reference format is comparable. It gets NO retrieved context -- that is the
# point of the control.
SYSTEM = (
    "You are an expert on Regulation (EU) 2024/1689 (the EU AI Act). Answer the "
    "user's question accurately and concisely from your own knowledge of the "
    "Regulation.\n\n"
    "Return ONLY a JSON object, no prose around it:\n"
    '{"answer": "<a concise answer, at most 4 sentences>", '
    '"references": ["Article 6", "Annex III"]}\n\n'
    "references MUST be the MINIMAL set of provisions that actually govern the "
    "answer. Use exactly the forms 'Article N' (Arabic) or 'Annex X' (Roman, "
    "uppercase); a sub-point may be given as 'Article 6.3' or 'Annex IV.2'. "
    "Do not cite provisions that merely relate to the topic."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_REF_RE = re.compile(r"\b(?:Article|Annex)\s+(?:[0-9]{1,3}|[IVXLC]{1,6})"
                     r"(?:\.[0-9a-zA-Z]+)*", re.IGNORECASE)


def _parse(text: str) -> tuple[str, list[str]]:
    """Extract (answer, references) from the model's reply, fail-soft."""
    m = _JSON_RE.search(text or "")
    if m:
        try:
            d = json.loads(m.group(0))
            ans = str(d.get("answer") or "").strip()
            refs = [str(x).strip() for x in (d.get("references") or []) if str(x).strip()]
            if ans:
                return ans, refs
        except Exception:
            pass
    # Fallback: keep the prose, scrape any citations out of it.
    return (text or "").strip(), sorted(set(_REF_RE.findall(text or "")))


def _ask(model: str, question: str, timeout: float) -> dict:
    import httpx

    base = os.getenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
    key = os.getenv("OPENAI_API_KEY", "dummy")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for h in ("CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET"):
        v = os.getenv(h)
        if v:
            headers[h.replace("_", "-").title().replace("Cf-", "CF-")] = v
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": SYSTEM + "\n\nQUESTION:\n" + question}
        ],
        "max_tokens": 900,
    }
    t0 = time.time()
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{base}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        d = r.json()
    txt = (d.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return {"text": txt, "echoed_model": d.get("model"), "ms": int((time.time() - t0) * 1000)}


def run(model: str, label: str, *, limit: int | None, timeout: float) -> Path:
    rows = load_probe_set()
    if limit:
        rows = rows[:limit]
    out = RESULTS / f"frontier-{label}.ckpt.jsonl"
    done = set()
    if out.exists():  # resume (R280: a killed run must not lose everything)
        for line in out.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass
        print(f"resuming: {len(done)} rows already recorded in {out.name}")

    with out.open("a", encoding="utf-8") as fh:
        for i, p in enumerate(rows, 1):
            if p.id in done:
                continue
            users = [m["content"] for m in p.messages if m.get("role") == "user"]
            question = users[-1] if users else ""
            try:
                got = _ask(model, question, timeout)
                ans, refs = _parse(got["text"])
                rec = {"id": p.id, "source": p.source, "category": p.category,
                       "is_multiturn": p.is_multiturn, "question": question,
                       "pred_answer": ans, "pred_refs": refs,
                       "gold_refs": list(p.expected_refs),
                       "expected_keywords": list(p.expected_keywords),
                       "latency_ms": got["ms"], "echoed_model": got["echoed_model"],
                       "http_status": 200, "arm": "frontier", "model_requested": model}
            except Exception as exc:
                rec = {"id": p.id, "source": p.source, "category": p.category,
                       "question": question, "pred_answer": "", "pred_refs": [],
                       "gold_refs": list(p.expected_refs),
                       "expected_keywords": list(p.expected_keywords),
                       "http_status": 0, "error": str(exc)[:200],
                       "arm": "frontier", "model_requested": model}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()  # per-row durability
            print(f"  [{i}/{len(rows)}] {p.id} refs={len(rec['pred_refs'])} "
                  f"{rec.get('latency_ms', 0)}ms {'ERR' if rec['http_status'] != 200 else ''}")
    return out


def _kw_recall(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    low = (answer or "").lower()
    return sum(1 for k in keywords if k.lower() in low) / len(keywords)


def score(path: Path) -> dict:
    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("http_status") == 200]
    if not rows:
        return {}
    loose = [reference_correctness_loose(r["pred_refs"], r["gold_refs"]) for r in rows]
    strict = [reference_correctness_strict(r["pred_refs"], r["gold_refs"]) for r in rows]
    conc = [reference_conciseness(r["pred_refs"], r["gold_refs"]) for r in rows]
    kw = [_kw_recall(r.get("pred_answer", ""), r.get("expected_keywords") or []) for r in rows]
    lat = [r.get("latency_ms", 0) for r in rows if r.get("latency_ms")]
    return {"n": len(rows), "ref_loose": round(st.mean(loose), 4),
            "ref_strict": round(st.mean(strict), 4), "ref_conc": round(st.mean(conc), 4),
            "kw_recall": round(st.mean(kw), 4),
            "latency_p50_ms": int(st.median(lat)) if lat else None,
            "mean_pred_refs": round(st.mean([len(r["pred_refs"]) for r in rows]), 2),
            "_rows": {r["id"]: r for r in rows}}


def compare(ours: Path, theirs: Path) -> None:
    A, B = score(ours), score(theirs)
    if not A or not B:
        print("compare: one arm has no scorable rows")
        return
    shared = sorted(set(A["_rows"]) & set(B["_rows"]))
    print(f"\n=== FRONTIER HEAD-TO-HEAD   (paired on {len(shared)} shared rows)")
    print(f"    A = OURS    {ours.name}")
    print(f"    B = FRONTIER {theirs.name}  (no retrieval, no search)\n")
    print(f"{'axis':<22}{'ours':>10}{'frontier':>11}{'delta':>10}   winner")
    for axis, better_high in (("ref_loose", True), ("ref_strict", True),
                              ("ref_conc", True), ("kw_recall", True),
                              ("mean_pred_refs", False)):
        a = [x for i in shared for x in [None]]  # placeholder to keep loop simple
        av, bv = A[axis], B[axis]
        d = round(av - bv, 4)
        win = "OURS" if ((d > 0) == better_high and d != 0) else ("FRONTIER" if d != 0 else "tie")
        print(f"{axis:<22}{av:>10}{bv:>11}{d:>+10.4f}   {win}")
    print(f"{'latency_p50_ms':<22}{str(A['latency_p50_ms']):>10}{str(B['latency_p50_ms']):>11}")

    # per-row win counts on the reference axes (the honest granularity)
    for axis, fn in (("ref_strict", reference_correctness_strict),
                     ("ref_loose", reference_correctness_loose),
                     ("ref_conc", reference_conciseness)):
        ow = fw = tie = 0
        for rid in shared:
            ra, rb = A["_rows"][rid], B["_rows"][rid]
            sa = fn(ra["pred_refs"], ra["gold_refs"])
            sb = fn(rb["pred_refs"], rb["gold_refs"])
            ow += sa > sb; fw += sb > sa; tie += sa == sb
        print(f"  per-row {axis:<12} ours {ow:>3} | frontier {fw:>3} | tie {tie:>3}")
    ow = fw = tie = 0
    for rid in shared:
        ra, rb = A["_rows"][rid], B["_rows"][rid]
        sa = _kw_recall(ra.get("pred_answer", ""), ra.get("expected_keywords") or [])
        sb = _kw_recall(rb.get("pred_answer", ""), rb.get("expected_keywords") or [])
        ow += sa > sb; fw += sb > sa; tie += sa == sb
    print(f"  per-row kw_recall    ours {ow:>3} | frontier {fw:>3} | tie {tie:>3}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--label")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--ours")
    ap.add_argument("--theirs")
    a = ap.parse_args()

    if a.compare:
        compare(Path(a.ours), Path(a.theirs))
        return
    if not a.label:
        ap.error("--label is required when running an arm")
    p = run(a.model, a.label, limit=a.limit, timeout=a.timeout)
    s = score(p)
    s.pop("_rows", None)
    print("\nfrontier arm scored:", json.dumps(s, indent=1))
    print("sidecar:", p)


if __name__ == "__main__":
    main()
