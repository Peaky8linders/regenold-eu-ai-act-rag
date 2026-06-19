"""Live medtech GraphRAG-bench (v124) eval with EXACT sub-point scoring (R130).

Posts the 24 v124 medtech questions to the deployed endpoint and scores, per
row: head-level Ref correctness (``_ref_metrics`` — collapses to article heads)
AND sub-point-EXACT Ref correctness against the golden dataset's own sub-point
citations (``medtech_subpoint_gold``). Also Ans-strict vs the v124 gold answer,
keyword recall, regulatory tone, latency. Emits a judge-compatible sidecar.

Usage:
    set P2P_REGENOLD_API_KEY=...
    python -m evals.regenold.run_medtech_subpoint_eval --label r130-medtech-subpoint
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from evals.bench import metrics as M
from evals.regenold.antifragile_live import (
    LIVE_ENDPOINT,
    _load_api_key,
    _norm,
    _parse_reasoning,
    _subpoint_metrics,
)
from evals.regenold.medtech_subpoint_gold import MEDTECH_SUBPOINT_GOLD
from evals.regenold.runner_v2 import _keyword_recall, _post, _ref_metrics
from evals.regenold.scenarios_medtech_graphrag_v124 import GROUND_TRUTH

REFUSAL = ("i only answer", "please ask", "no matching obligation", "try rephrasing",
           "outside the scope", "cannot answer")


def _mean(xs: list[float]) -> float:
    return round(statistics.mean(xs), 4) if xs else 0.0


def _score(row: dict, body: dict, lat: float, err: str | None) -> dict:
    ans = body.get("answer") or ""
    refs = body.get("references") or []
    gold = row.get("gold_answer", "")
    head_gold = row.get("expected_refs", [])
    sp_gold = MEDTECH_SUBPOINT_GOLD.get(row["id"], {}).get("refs", head_gold)
    refm = _ref_metrics(refs, head_gold)
    refm_sp = _subpoint_metrics(refs, sp_gold)
    return {
        "id": row["id"], "category": row.get("category"),
        "reasoning_level": row.get("reasoning_level"),
        "question": row["question"],
        "expected_refs": head_gold, "gold_subpoint_refs": sp_gold, "pred_refs": refs,
        "predicted_answer": ans, "answer_preview": ans[:300],
        "ans_strict": M.answer_correctness_strict(ans, gold),
        "ans_conciseness": M.answer_conciseness(ans, gold),
        "ref_loose": refm["loose"], "ref_strict": refm["strict"],
        "ref_subpoint_loose": refm_sp["loose"], "ref_subpoint_strict": refm_sp["strict"],
        "ref_subpoint_conciseness": refm_sp["conciseness"],
        "regulatory_tone": M.regulatory_tone(ans),
        "keyword_recall": _keyword_recall(ans, row.get("expected_keywords", [])),
        "has_subpoint_gold": row["id"] in MEDTECH_SUBPOINT_GOLD,
        "is_refusal": any(m in _norm(ans) for m in REFUSAL),
        "latency_ms": round(lat, 1), "error": err,
        "reasoning": _parse_reasoning(body.get("reasoning")),
        "expected_keywords": row.get("expected_keywords", []),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="r130-medtech-subpoint")
    ap.add_argument("--endpoint", default=LIVE_ENDPOINT)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--throttle", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    key = _load_api_key()
    ep = args.endpoint if "?" in args.endpoint else args.endpoint + "?include_reasoning=true"
    rows: list[dict] = []
    gt = GROUND_TRUTH[: args.limit] if args.limit else GROUND_TRUTH
    print(f"endpoint={ep}\nrows={len(gt)} (subpoint-gold rows={len(MEDTECH_SUBPOINT_GOLD)})\n")
    for r in gt:
        body, lat, status, err, attempts, _ = _post(
            ep, key, [{"role": "user", "content": r["question"]}], args.timeout)
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        row = _score(r, body, lat, err)
        rows.append(row)
        sp = f" SPstrict={row['ref_subpoint_strict']:.2f}" if row["has_subpoint_gold"] else ""
        print(f"[{r['id']}] {status} {row['latency_ms']:.0f}ms refL={row['ref_loose']:.2f} "
              f"refS={row['ref_strict']:.2f}{sp} ansS={row['ans_strict']:.2f} refs={row['pred_refs']}")
        time.sleep(args.throttle)

    ok = [r for r in rows if not r["error"]]
    sp_rows = [r for r in ok if r["has_subpoint_gold"]]
    summary = {
        "n": len(rows), "n_ok": len(ok),
        "ref_loose": _mean([r["ref_loose"] for r in ok]),
        "ref_strict": _mean([r["ref_strict"] for r in ok]),
        "ans_strict": _mean([r["ans_strict"] for r in ok]),
        "keyword_recall": _mean([r["keyword_recall"] for r in ok]),
        "regulatory_tone": _mean([r["regulatory_tone"] for r in ok]),
        "subpoint_n": len(sp_rows),
        "ref_subpoint_loose": _mean([r["ref_subpoint_loose"] for r in sp_rows]),
        "ref_subpoint_strict": _mean([r["ref_subpoint_strict"] for r in sp_rows]),
        "stage2_polish": sum(1 for r in ok if r["reasoning"].get("stage2_polish")),
    }
    out = {"label": args.label, "endpoint": ep, "summary": summary, "rows": rows}
    p = Path("evals/bench/results") / f"medtech-subpoint-{args.label}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nSUMMARY:", json.dumps(summary, indent=2))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
