"""Runner for the fresh MedTech / life-sciences eval (R109).

Scores every ``MEDTECH_SCENARIOS`` row against its Article/Annex gold
(reference correctness loose/strict/conciseness, keyword recall, regulatory
tone, refusal rate, latency) and prints an overall + per-category breakdown.

Usage
-----
    # Local deterministic (TestClient, no wrapper):
    .venv\\Scripts\\python.exe -m evals.regenold.run_medtech --local \\
        --label r109-medtech-local --verbose

    # Live (Claude Max Stage-2 via the production endpoint — the eval rule):
    .venv\\Scripts\\python.exe -m evals.regenold.run_medtech \\
        --endpoint https://<railway>.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key $env:P2P_REGENOLD_API_KEY --label r109-medtech-live --verbose
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
from evals.regenold.scenarios_medtech_lifesci import MEDTECH_SCENARIOS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pct(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0}
    s = sorted(values)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"p50": round(median(s), 1), "p95": round(p95, 1)}


def run(
    *,
    endpoint: str,
    api_key: str | None,
    label: str,
    timeout: float,
    use_local: bool,
    scenarios: list[dict] | None = None,
) -> dict[str, Any]:
    transport = _post_local if use_local else _post
    if use_local:
        _ensure_local_auth(api_key)

    scenario_set = scenarios if scenarios is not None else MEDTECH_SCENARIOS
    rows: list[dict[str, Any]] = []
    for scn in scenario_set:
        # Multi-turn rows (rgn_mt_*) carry a full ``messages`` history whose
        # final user turn equals ``question``; single-turn rows fall back to
        # the historical one-message shape.
        history = scn.get("messages") or [
            {"role": "user", "content": scn["question"]}
        ]
        body, lat, status, err, _attempts, _retried = transport(
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
            "pred_refs": refs,
            "expected_keywords": scn["expected_keywords"],
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
        }
        rows.append(row)
        print(
            f"[MT] {scn['id']} cat={scn['category']:<26} "
            f"refL={ref['loose']:.2f} refS={ref['strict']:.2f} "
            f"kw={kw:.2f} tone={tone:.2f} lat={lat:.0f}ms"
            f"{' ERR=' + err if err else ''}"
        )

    scored = [r for r in rows if r["error"] is None]

    def _avg(key: str) -> float | None:
        return round(mean([r[key] for r in scored]), 4) if scored else None

    overall = {
        "n": len(rows),
        "n_scored": len(scored),
        "http_failures": sum(1 for r in rows if r["error"]),
        "ref_loose": _avg("ref_loose"),
        "ref_strict": _avg("ref_strict"),
        "ref_conciseness": _avg("ref_conciseness"),
        "keyword_recall": _avg("keyword_recall"),
        "regulatory_tone": _avg("regulatory_tone"),
        "refusal_rate": round(mean([1.0 if r["is_refusal"] else 0.0 for r in scored]), 4) if scored else None,
        "latency": _pct([r["latency_ms"] for r in scored]),
    }

    by_cat: dict[str, dict[str, Any]] = {}
    cat_rows: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        cat_rows[r["category"]].append(r)
    for cat, crs in sorted(cat_rows.items()):
        by_cat[cat] = {
            "n": len(crs),
            "ref_loose": round(mean([r["ref_loose"] for r in crs]), 3),
            "ref_strict": round(mean([r["ref_strict"] for r in crs]), 3),
            "keyword_recall": round(mean([r["keyword_recall"] for r in crs]), 3),
            "regulatory_tone": round(mean([r["regulatory_tone"] for r in crs]), 3),
        }

    payload = {
        "label": label,
        "mode": "medtech-local" if use_local else "medtech-live",
        "endpoint": endpoint,
        "started_at": _now_iso(),
        "overall": overall,
        "by_category": by_cat,
        "rows": rows,
    }

    out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"medtech-{label}.json"
    sidecar.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    payload["sidecar_path"] = str(sidecar)
    return payload


def _format(payload: dict[str, Any]) -> str:
    o = payload["overall"]
    out = [
        "=" * 78,
        f"MedTech / life-sciences eval — label={payload['label']!r}",
        f"endpoint: {payload['endpoint']}",
        f"mode: {payload['mode']}",
        "=" * 78,
        "",
        f"[OVERALL] n={o['n']} scored={o['n_scored']} http_failures={o['http_failures']}",
        f"    Ref Loose       : {o['ref_loose']}",
        f"    Ref Strict      : {o['ref_strict']}",
        f"    Ref Conciseness : {o['ref_conciseness']}",
        f"    Keyword Recall  : {o['keyword_recall']}",
        f"    Regulatory Tone : {o['regulatory_tone']}",
        f"    Refusal Rate    : {o['refusal_rate']}",
        f"    Latency p50/p95 : {o['latency']['p50']}ms / {o['latency']['p95']}ms",
        "",
        "[BY CATEGORY]",
    ]
    for cat, c in payload["by_category"].items():
        out.append(
            f"  {cat:<28} n={c['n']} refL={c['ref_loose']} "
            f"refS={c['ref_strict']} kw={c['keyword_recall']} tone={c['regulatory_tone']}"
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
    parser.add_argument(
        "--v2", action="store_true",
        help="Use the R116 fresh medtech/life-sciences V2 set instead of the R109 set.",
    )
    parser.add_argument(
        "--v3", action="store_true",
        help="Use the R120 fresh medtech/life-sciences V3 set.",
    )
    args = parser.parse_args(argv)

    scenarios = None
    if args.v2:
        from evals.regenold.scenarios_medtech_lifesci_v2 import MEDTECH_SCENARIOS_V2
        scenarios = MEDTECH_SCENARIOS_V2
    elif args.v3:
        from evals.regenold.scenarios_medtech_lifesci_v3 import MEDTECH_SCENARIOS_V3
        scenarios = MEDTECH_SCENARIOS_V3

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
        scenarios=scenarios,
    )
    print(_format(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
