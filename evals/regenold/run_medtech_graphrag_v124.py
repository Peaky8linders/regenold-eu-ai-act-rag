"""Runner for the fresh medical/healthcare/life-sciences benchmark (R124).

Scores the 24 ``scenarios_medtech_graphrag_v124.GROUND_TRUTH`` rows against
their Article-level gold (reference correctness loose/strict/conciseness,
keyword recall, regulatory tone, latency) and writes a **judge-compatible**
sidecar (``ground_truth.rows`` — ``evals.judge.runner`` reads it directly).

Mirrors ``evals.regenold.run_graphrag_benchmark`` (same ``runner_v2`` scoring
helpers + ``_post`` / ``_post_local`` transport) and adds per-reasoning-level
(L1-L4) + per-category aggregates so the GraphRAG-Bench reasoning taxonomy
shows up in the scorecard.

Usage
-----
    # Live (Claude Max wrapper via the production endpoint — the eval rule):
    .venv\\Scripts\\python.exe -m evals.regenold.run_medtech_graphrag_v124 \\
        --endpoint https://<railway>.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key $env:P2P_REGENOLD_API_KEY --label r124-medgrb-live --verbose

    # Local (TestClient; deterministic unless the wrapper env is wired):
    .venv\\Scripts\\python.exe -m evals.regenold.run_medtech_graphrag_v124 \\
        --local --label r124-medgrb-local --verbose

Then judge:
    .venv\\Scripts\\python.exe -m evals.judge.runner \\
        --bench-sidecar evals/bench/results/medtech-graphrag-v124-<label>.json \\
        --label r124-medgrb --provider wrapper --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from dotenv import load_dotenv
load_dotenv()


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
from evals.regenold.scenarios_medtech_graphrag_v124 import GROUND_TRUTH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pct(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0}
    s = sorted(values)
    p50 = median(s)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"p50": round(p50, 1), "p95": round(p95, 1)}


def _grouped(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """Aggregate the per-row metrics by ``key`` (reasoning_level / category)."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["error"] is None:
            buckets[str(r.get(key) or "?")].append(r)
    out: dict[str, dict[str, Any]] = {}
    for k, rs in sorted(buckets.items()):
        out[k] = {
            "n": len(rs),
            "ref_loose": round(mean(r["ref_loose"] for r in rs), 4),
            "ref_strict": round(mean(r["ref_strict"] for r in rs), 4),
            "keyword_recall": round(mean(r["keyword_recall"] for r in rs), 4),
            "regulatory_tone": round(mean(r["regulatory_tone"] for r in rs), 4),
        }
    return out


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

    rows: list[dict[str, Any]] = []
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
        rows.append({
            "id": scn["id"],
            "category": scn["category"],
            "graphrag_theme": scn["graphrag_theme"],
            "reasoning_level": scn["reasoning_level"],
            "question": scn["question"],
            "expected_refs": scn["expected_refs"],
            "expected_keywords": scn["expected_keywords"],
            "gold_answer": scn["gold_answer"],
            "pred_refs": [str(r) for r in refs],
            "predicted_answer": answer,
            "answer_preview": answer[:400],
            "reasoning": body.get("reasoning"),
            "ref_loose": ref["loose"],
            "ref_strict": ref["strict"],
            "ref_conciseness": ref["conciseness"],
            "keyword_recall": kw,
            "regulatory_tone": tone,
            "is_refusal": is_refusal,
            "latency_ms": lat,
            "error": err,
        })
        print(
            f"[GRB] {scn['id']} {scn['reasoning_level']} "
            f"cat={scn['category']:<28} "
            f"refL={ref['loose']:.2f} refS={ref['strict']:.2f} "
            f"kw={kw:.2f} tone={tone:.2f} lat={lat:.0f}ms"
            f"{' ERR=' + err if err else ''}"
        )

    scored = [r for r in rows if r["error"] is None]
    summary = {
        "n": len(rows),
        "http_failures": sum(1 for r in rows if r["error"]),
        "ref_loose": round(mean(r["ref_loose"] for r in scored), 4) if scored else None,
        "ref_strict": round(mean(r["ref_strict"] for r in scored), 4) if scored else None,
        "ref_conciseness": round(mean(r["ref_conciseness"] for r in scored), 4) if scored else None,
        "keyword_recall": round(mean(r["keyword_recall"] for r in scored), 4) if scored else None,
        "regulatory_tone": round(mean(r["regulatory_tone"] for r in scored), 4) if scored else None,
        "refusal_rate": round(mean(1.0 if r["is_refusal"] else 0.0 for r in scored), 4) if scored else None,
        "latency": _pct([r["latency_ms"] for r in scored]),
        "by_reasoning_level": _grouped(rows, "reasoning_level"),
        "by_category": _grouped(rows, "category"),
    }

    payload = {
        "label": label,
        "benchmark": "medtech-graphrag-v124",
        "dataset_grounding": "GraphRAG-Bench/GraphRAG-Bench medical (arXiv 2506.05690, MIT) + MedMCQA/MIRAGE themes; refs grounded in verbatim EU AI Act (Reg 2024/1689)",
        "mode": "medtech-graphrag-v124-local" if use_local else "medtech-graphrag-v124-live",
        "endpoint": endpoint,
        "started_at": _now_iso(),
        # ``ground_truth.rows`` bucket — the judge runner reads it directly.
        "ground_truth": {"rows": rows, "summary": summary},
    }

    out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"medtech-graphrag-v124-{label}.json"
    sidecar.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["sidecar_path"] = str(sidecar)
    return payload


def _format(payload: dict[str, Any]) -> str:
    s = payload["ground_truth"]["summary"]
    out = [
        "=" * 78,
        f"MedTech-GraphRAG-v124 benchmark — label={payload['label']!r}",
        f"endpoint: {payload['endpoint']}",
        f"mode: {payload['mode']}",
        f"grounding: {payload['dataset_grounding']}",
        "=" * 78,
        f"n={s['n']}  http_failures={s['http_failures']}",
        f"  Ref Loose       : {s['ref_loose']}",
        f"  Ref Strict      : {s['ref_strict']}",
        f"  Ref Conciseness : {s['ref_conciseness']}",
        f"  Keyword Recall  : {s['keyword_recall']}",
        f"  Regulatory Tone : {s['regulatory_tone']}",
        f"  Refusal Rate    : {s['refusal_rate']}",
        f"  Latency p50/p95 : {s['latency']['p50']}ms / {s['latency']['p95']}ms",
        "",
        "  By reasoning level (refL / refS / kw):",
    ]
    for lvl, agg in s["by_reasoning_level"].items():
        out.append(
            f"    {lvl:<4} n={agg['n']:<3} {agg['ref_loose']} / "
            f"{agg['ref_strict']} / {agg['keyword_recall']}"
        )
    out.append("")
    out.append(f"sidecar: {payload.get('sidecar_path', '-')}")
    out.append(
        "judge:   python -m evals.judge.runner --bench-sidecar "
        f"{payload.get('sidecar_path', '-')} --label {payload['label']}"
    )
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
    parser.add_argument("--timeout", type=float, default=120.0)
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
