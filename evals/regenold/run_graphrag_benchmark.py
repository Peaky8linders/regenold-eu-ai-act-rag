"""Runner for the GraphRAG-paper Appendix-B.2 benchmark (R99 add-on).

Scores the 10 ground-truth questions against the paper's Article-level gold
(reference correctness loose/strict, keyword recall, regulatory tone) and
runs the 10 no-ground-truth questions live, reporting the engine's predicted
references + tone + latency (no scoring — there is no gold).

Recital-only ground-truth rows (gt_06, gt_07) are EXCLUDED from the
reference-correctness aggregate (the wire emits Articles/Annexes only); their
keyword recall + tone are still reported.

Usage
-----
    # Live (Claude Max wrapper via the production endpoint — the eval rule):
    .venv\\Scripts\\python.exe -m evals.regenold.run_graphrag_benchmark \\
        --endpoint https://<railway>.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key $env:P2P_REGENOLD_API_KEY --label r99-graphrag-live --verbose

    # Local deterministic (TestClient, no wrapper):
    .venv\\Scripts\\python.exe -m evals.regenold.run_graphrag_benchmark \\
        --local --label r99-graphrag-local --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from evals.bench import metrics as bench_metrics
from evals.regenold.runner_v2 import (
    _ensure_local_auth,
    _keyword_recall,
    _local_endpoint_url,
    _post,
    _post_local,
    _ref_metrics,
    _REFUSAL_MARKERS,
)
from evals.regenold.scenarios_graphrag_benchmark import GROUND_TRUTH, NO_GROUND_TRUTH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pct(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0}
    s = sorted(values)
    p50 = median(s)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"p50": round(p50, 1), "p95": round(p95, 1)}


def run(
    *,
    endpoint: str,
    api_key: str | None,
    label: str,
    timeout: float,
    use_local: bool,
) -> dict[str, Any]:
    transport = _post_local if use_local else _post
    if use_local:
        _ensure_local_auth(api_key)

    # ── Group 1: ground truth ────────────────────────────────────────────
    gt_rows: list[dict[str, Any]] = []
    for scn in GROUND_TRUTH:
        history = [{"role": "user", "content": scn["question"]}]
        body, lat, status, err, attempts, retried = transport(
            endpoint, api_key, history, timeout
        )
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        answer = body.get("answer") or ""
        refs = body.get("references") or []
        ref = _ref_metrics(refs, scn["expected_refs"])
        kw = _keyword_recall(answer, scn["expected_keywords"])
        tone = bench_metrics.regulatory_tone(answer)
        is_refusal = any(m in answer.lower() for m in _REFUSAL_MARKERS)
        row = {
            "id": scn["id"],
            "category": scn["category"],
            "question": scn["question"],
            "expected_refs": scn["expected_refs"],
            "paper_refs": scn["paper_refs"],
            "recital_only": scn["recital_only"],
            "pred_refs": refs,
            "expected_keywords": scn["expected_keywords"],
            "predicted_answer": answer,
            "answer_preview": answer[:400],
            "ref_loose": ref["loose"],
            "ref_strict": ref["strict"],
            "ref_conciseness": ref["conciseness"],
            "keyword_recall": kw,
            "regulatory_tone": tone,
            "is_refusal": is_refusal,
            "latency_ms": lat,
            "error": err,
        }
        gt_rows.append(row)
        print(
            f"[GT] {scn['id']} cat={scn['category']:<22} "
            f"refL={ref['loose']:.2f} refS={ref['strict']:.2f} "
            f"kw={kw:.2f} tone={tone:.2f} lat={lat:.0f}ms"
            f"{' [recital-only]' if scn['recital_only'] else ''}"
            f"{' ERR=' + err if err else ''}"
        )

    # ── Group 2: no ground truth (report-only) ───────────────────────────
    ng_rows: list[dict[str, Any]] = []
    for scn in NO_GROUND_TRUTH:
        history = [{"role": "user", "content": scn["question"]}]
        body, lat, status, err, attempts, retried = transport(
            endpoint, api_key, history, timeout
        )
        if err is None and not (200 <= status < 300):
            err = f"http_{status}"
        answer = body.get("answer") or ""
        refs = body.get("references") or []
        tone = bench_metrics.regulatory_tone(answer)
        is_refusal = any(m in answer.lower() for m in _REFUSAL_MARKERS)
        row = {
            "id": scn["id"],
            "question": scn["question"],
            "doctrinal_anchor": scn["doctrinal_anchor"],
            "pred_refs": refs,
            "predicted_answer": answer,
            "answer_preview": answer[:400],
            "regulatory_tone": tone,
            "is_refusal": is_refusal,
            "latency_ms": lat,
            "error": err,
        }
        ng_rows.append(row)
        print(
            f"[NG] {scn['id']} pred_refs={refs} tone={tone:.2f} "
            f"refusal={is_refusal} lat={lat:.0f}ms"
            f"{' ERR=' + err if err else ''}"
        )

    # ── Aggregates ───────────────────────────────────────────────────────
    scored = [r for r in gt_rows if not r["recital_only"] and r["error"] is None]
    all_kw = [r for r in gt_rows if r["error"] is None]
    gt_summary = {
        "n": len(gt_rows),
        "n_scored_refs": len(scored),
        "n_recital_only_excluded": sum(1 for r in gt_rows if r["recital_only"]),
        "http_failures": sum(1 for r in gt_rows if r["error"]),
        "ref_loose": round(mean([r["ref_loose"] for r in scored]), 4) if scored else None,
        "ref_strict": round(mean([r["ref_strict"] for r in scored]), 4) if scored else None,
        "ref_conciseness": round(mean([r["ref_conciseness"] for r in scored]), 4) if scored else None,
        "keyword_recall": round(mean([r["keyword_recall"] for r in all_kw]), 4) if all_kw else None,
        "regulatory_tone": round(mean([r["regulatory_tone"] for r in all_kw]), 4) if all_kw else None,
        "refusal_rate": round(mean([1.0 if r["is_refusal"] else 0.0 for r in all_kw]), 4) if all_kw else None,
        "latency": _pct([r["latency_ms"] for r in gt_rows if r["error"] is None]),
    }
    ng_summary = {
        "n": len(ng_rows),
        "http_failures": sum(1 for r in ng_rows if r["error"]),
        "regulatory_tone": round(mean([r["regulatory_tone"] for r in ng_rows if r["error"] is None]), 4)
        if any(r["error"] is None for r in ng_rows) else None,
        "refusal_rate": round(mean([1.0 if r["is_refusal"] else 0.0 for r in ng_rows if r["error"] is None]), 4)
        if any(r["error"] is None for r in ng_rows) else None,
        "latency": _pct([r["latency_ms"] for r in ng_rows if r["error"] is None]),
    }

    payload = {
        "label": label,
        "mode": "graphrag-benchmark-local" if use_local else "graphrag-benchmark-live",
        "endpoint": endpoint,
        "started_at": _now_iso(),
        "ground_truth": {"rows": gt_rows, "summary": gt_summary},
        "no_ground_truth": {"rows": ng_rows, "summary": ng_summary},
    }

    out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"graphrag-bench-{label}.json"
    sidecar.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["sidecar_path"] = str(sidecar)
    return payload


def _format(payload: dict[str, Any]) -> str:
    g = payload["ground_truth"]["summary"]
    n = payload["no_ground_truth"]["summary"]
    out = [
        "=" * 78,
        f"GraphRAG-paper benchmark — label={payload['label']!r}",
        f"endpoint: {payload['endpoint']}",
        f"mode: {payload['mode']}",
        "=" * 78,
        "",
        f"[GROUND TRUTH] n={g['n']}  http_failures={g['http_failures']}",
        f"  Reference correctness scored over {g['n_scored_refs']} rows "
        f"({g['n_recital_only_excluded']} recital-only rows excluded):",
        f"    Ref Loose       : {g['ref_loose']}",
        f"    Ref Strict      : {g['ref_strict']}",
        f"    Ref Conciseness : {g['ref_conciseness']}",
        f"  Keyword Recall (all {g['n']} rows) : {g['keyword_recall']}",
        f"  Regulatory Tone                    : {g['regulatory_tone']}",
        f"  Refusal Rate                       : {g['refusal_rate']}",
        f"  Latency p50/p95                    : {g['latency']['p50']}ms / {g['latency']['p95']}ms",
        "",
        f"[NO GROUND TRUTH] n={n['n']}  http_failures={n['http_failures']} "
        "(report-only — no gold)",
        f"  Regulatory Tone : {n['regulatory_tone']}",
        f"  Refusal Rate    : {n['refusal_rate']}",
        f"  Latency p50/p95 : {n['latency']['p50']}ms / {n['latency']['p95']}ms",
        "  Predicted refs per question:",
    ]
    for r in payload["no_ground_truth"]["rows"]:
        out.append(
            f"    {r['id']} {r['pred_refs']}  (expert anchor: {r['doctrinal_anchor']})"
        )
    out.append("")
    out.append(f"sidecar: {payload.get('sidecar_path', '-')}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--label", required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.local:
        endpoint = _local_endpoint_url("include_reasoning=true")
    elif args.endpoint:
        endpoint = args.endpoint
    else:
        parser.error("--endpoint is required unless --local is set")
        return 2

    payload = run(
        endpoint=endpoint,
        api_key=args.api_key,
        label=args.label,
        timeout=args.timeout,
        use_local=args.local,
    )
    print(_format(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
