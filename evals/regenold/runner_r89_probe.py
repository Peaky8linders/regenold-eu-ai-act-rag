"""R89 live-probe runner — hits a Regenold endpoint with 40 EU AI Act
representative questions spanning high-risk classification, GPAI,
prohibited practices, transparency, deployer obligations, governance,
and Digital-Omnibus timeline rows.

Usage (live, against Railway via Cloudflare tunnel + Claude Max):

    .venv/Scripts/python.exe -m evals.regenold.runner_r89_probe \\
        --endpoint https://<railway>.up.railway.app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true \\
        --api-key $env:P2P_REGENOLD_API_KEY \\
        --label r89a-live

Usage (local TestClient):

    .venv/Scripts/python.exe -m evals.regenold.runner_r89_probe \\
        --local --label r89a-local

Scoring (per the Regenold rubric):
  * ref_loose / ref_strict / ref_conciseness  — same shape as runner_v2
  * keyword_recall                            — case-insensitive substring
  * regulatory_tone                           — bench_metrics.regulatory_tone
  * latency p50/p95/max
  * multi_turn coherence_rate (refL > 0 AND kw >= 0.5 AND not refusal)

Writes ``evals/bench/results/r89-probe-<label>.json``.
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
from evals.bench._http_retry import post_json_with_retry

from evals.regenold.runner_v2 import (  # reuse local-mode plumbing
    _local_endpoint_url,
    _post_local,
    _USER_AGENT,
    _REFUSAL_MARKERS,
)
from evals.regenold.scenarios_r89_live_probe import (
    SINGLE_TURN,
    MULTI_TURN,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _post_live(
    endpoint: str,
    api_key: str | None,
    history: list[dict[str, str]],
    timeout: float,
) -> tuple[dict[str, Any], float, int, str | None, int, list[str]]:
    """Live HTTP POST with one-shot retry (R47-D helper)."""
    return post_json_with_retry(
        endpoint, history, api_key, timeout,
        user_agent=_USER_AGENT,
    )


def _gold_head_set(expected_refs: list[str]) -> set[str]:
    """Project user-facing refs to article-head form."""
    out: set[str] = set()
    for r in expected_refs:
        head = bench_metrics.article_head(r)
        if head:
            out.add(head)
    return out


def _ref_metrics(pred_refs: list[str], expected_refs: list[str]) -> dict[str, float]:
    """Compute loose / strict / conciseness — mirrors runner_v2._ref_metrics."""
    pred_heads = bench_metrics.article_heads(pred_refs)
    gold_heads = _gold_head_set(expected_refs)
    if not gold_heads and not pred_heads:
        loose = strict = 1.0
    elif not gold_heads or not pred_heads:
        loose = strict = 0.0
    else:
        overlap = len(pred_heads & gold_heads)
        loose = overlap / len(gold_heads)
        if overlap == 0:
            strict = 0.0
        else:
            precision = overlap / len(pred_heads)
            recall = overlap / len(gold_heads)
            strict = 2 * precision * recall / (precision + recall)
    lp = len(pred_heads)
    lg = len(gold_heads)
    if lg == 0:
        conciseness = 1.0 if lp == 0 else 0.0
    elif lp == 0:
        conciseness = 0.0
    else:
        ratio = min(lp, lg) / max(lp, lg)
        conciseness = ratio * ratio
    return {"loose": loose, "strict": strict, "conciseness": conciseness}


def _keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    """Case-insensitive substring fraction (mirrors runner_v2._keyword_recall)."""
    if not expected_keywords:
        return 1.0
    low = answer.lower()
    hits = sum(1 for k in expected_keywords if k.lower() in low)
    return hits / len(expected_keywords)


def _score_single_turn(
    scenario: dict,
    body: dict[str, Any],
    latency_ms: float,
    err: str | None,
    attempts: int,
    retried_errors: list[str],
) -> dict[str, Any]:
    answer = body.get("answer") or ""
    refs = body.get("references") or []
    expected_refs = scenario.get("expected_refs", [])
    expected_kw = scenario.get("expected_keywords", [])
    rm = _ref_metrics(refs, expected_refs)
    kw = _keyword_recall(answer, expected_kw)
    tone = bench_metrics.regulatory_tone(answer)
    is_refusal = any(m in answer.lower() for m in _REFUSAL_MARKERS)
    return {
        "id": scenario["id"],
        "category": scenario.get("category", "?"),
        "question": scenario["question"],
        "expected_refs": expected_refs,
        "pred_refs": refs,
        "expected_keywords": expected_kw,
        "answer_preview": answer[:600],
        "predicted_answer": answer,
        "ref_loose": rm["loose"],
        "ref_strict": rm["strict"],
        "ref_conciseness": rm["conciseness"],
        "keyword_recall": kw,
        "regulatory_tone": tone,
        "latency_ms": latency_ms,
        "is_refusal": is_refusal,
        "error": err,
        "attempts": attempts,
        "retried_errors": retried_errors,
    }


def _score_multi_turn(
    scenario: dict,
    final_body: dict[str, Any],
    final_latency_ms: float,
    err: str | None,
    attempts: int,
    retried_errors: list[str],
) -> dict[str, Any]:
    answer = final_body.get("answer") or ""
    refs = final_body.get("references") or []
    expected_refs = scenario.get("expected_final_refs", [])
    expected_kw = scenario.get("expected_final_keywords", [])
    rm = _ref_metrics(refs, expected_refs)
    kw = _keyword_recall(answer, expected_kw)
    tone = bench_metrics.regulatory_tone(answer)
    is_refusal = any(m in answer.lower() for m in _REFUSAL_MARKERS)
    is_coherent = (
        rm["loose"] > 0.0
        and kw >= 0.5
        and not is_refusal
        and err is None
    )
    return {
        "id": scenario["id"],
        "category": scenario.get("category", "multi_turn"),
        "n_turns": len(scenario.get("turns", [])),
        "expected_final_refs": expected_refs,
        "pred_refs": refs,
        "expected_keywords": expected_kw,
        "answer_preview": answer[:600],
        "predicted_answer": answer,
        "ref_loose": rm["loose"],
        "ref_strict": rm["strict"],
        "ref_conciseness": rm["conciseness"],
        "keyword_recall": kw,
        "regulatory_tone": tone,
        "latency_ms": final_latency_ms,
        "is_refusal": is_refusal,
        "is_coherent": is_coherent,
        "error": err,
        "attempts": attempts,
        "retried_errors": retried_errors,
    }


def _aggregate(rows: list[dict], coh_field: str | None = None) -> dict[str, Any]:
    """Compute axis-wise + per-category aggregate from scored rows."""
    clean = [r for r in rows if r.get("error") is None]
    n = len(clean)
    base = {"n_total": len(rows), "n_clean": n, "n_errors": len(rows) - n}
    if not clean:
        return base
    base["ref_loose"] = round(mean(r["ref_loose"] for r in clean), 4)
    base["ref_strict"] = round(mean(r["ref_strict"] for r in clean), 4)
    base["ref_conciseness"] = round(mean(r["ref_conciseness"] for r in clean), 4)
    base["keyword_recall"] = round(mean(r["keyword_recall"] for r in clean), 4)
    base["regulatory_tone"] = round(mean(r["regulatory_tone"] for r in clean), 4)
    base["latency_p50_ms"] = round(median(r["latency_ms"] for r in clean), 2)
    sorted_lat = sorted(r["latency_ms"] for r in clean)
    base["latency_p95_ms"] = round(sorted_lat[int(0.95 * len(sorted_lat))] if sorted_lat else 0, 2)
    base["latency_max_ms"] = round(max(r["latency_ms"] for r in clean), 2)
    if coh_field:
        coh = sum(1 for r in clean if r.get(coh_field))
        base["coherence_rate"] = round(coh / n if n else 0, 4)
        base["coherent_count"] = coh
    # Per-category breakdown
    cats: dict[str, list[dict]] = {}
    for r in clean:
        cats.setdefault(r.get("category", "?"), []).append(r)
    by_cat = {}
    for cat, rs in cats.items():
        if not rs:
            continue
        by_cat[cat] = {
            "n": len(rs),
            "ref_loose": round(mean(r["ref_loose"] for r in rs), 4),
            "ref_strict": round(mean(r["ref_strict"] for r in rs), 4),
            "keyword_recall": round(mean(r["keyword_recall"] for r in rs), 4),
            "regulatory_tone": round(mean(r["regulatory_tone"] for r in rs), 4),
        }
    base["by_category"] = by_cat
    return base


def _run_single_turn(
    scenarios: list[dict],
    *,
    endpoint: str,
    api_key: str | None,
    timeout: float,
    post_fn,
    verbose: bool,
) -> list[dict]:
    rows: list[dict] = []
    for i, sc in enumerate(scenarios, 1):
        history = [{"role": "user", "content": sc["question"]}]
        body, latency_ms, status, err, attempts, retried = post_fn(
            endpoint, api_key, history, timeout
        )
        if err is None and status >= 400:
            err = f"http_{status}"
        row = _score_single_turn(sc, body, latency_ms, err, attempts, retried)
        rows.append(row)
        if verbose:
            print(f"[{i}/{len(scenarios)}] {sc['id']} refL={row['ref_loose']:.2f} "
                  f"kw={row['keyword_recall']:.2f} latency={latency_ms:.0f}ms "
                  f"err={err}")
    return rows


def _run_multi_turn(
    scenarios: list[dict],
    *,
    endpoint: str,
    api_key: str | None,
    timeout: float,
    post_fn,
    verbose: bool,
) -> list[dict]:
    rows: list[dict] = []
    for i, sc in enumerate(scenarios, 1):
        # Build the full conversation history — all prior turns + final user msg.
        history: list[dict] = []
        for turn in sc.get("turns", []):
            history.append({"role": turn["role"], "content": turn["content"]})
        body, latency_ms, status, err, attempts, retried = post_fn(
            endpoint, api_key, history, timeout
        )
        if err is None and status >= 400:
            err = f"http_{status}"
        row = _score_multi_turn(sc, body, latency_ms, err, attempts, retried)
        rows.append(row)
        if verbose:
            coh = "T" if row["is_coherent"] else "F"
            print(f"[mt {i}/{len(scenarios)}] {sc['id']} refL={row['ref_loose']:.2f} "
                  f"kw={row['keyword_recall']:.2f} coh={coh} "
                  f"latency={latency_ms:.0f}ms err={err}")
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="R89 live-probe runner.")
    p.add_argument("--endpoint", default=None,
                   help="Full /ask endpoint URL (live mode).")
    p.add_argument("--api-key", default=None)
    p.add_argument("--label", required=True,
                   help="Label for the sidecar filename.")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--local", action="store_true",
                   help="Use FastAPI TestClient transport instead of live HTTP.")
    p.add_argument("--single-turn-only", action="store_true")
    p.add_argument("--multi-turn-only", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    # Resolve endpoint + post function
    if args.local:
        endpoint = _local_endpoint_url()
        post_fn = _post_local
    else:
        if not args.endpoint:
            print("ERROR: --endpoint required (or use --local).")
            return 2
        endpoint = args.endpoint
        post_fn = _post_live

    started = _now_iso()
    print("=" * 78)
    print(f"R89 live-probe runner — label='{args.label}'")
    print(f"Endpoint: {endpoint}")
    print(f"Started: {started}")
    print("=" * 78)

    single_rows: list[dict] = []
    multi_rows: list[dict] = []

    if not args.multi_turn_only:
        print(f"\n[SINGLE-TURN] n={len(SINGLE_TURN)}")
        single_rows = _run_single_turn(
            SINGLE_TURN, endpoint=endpoint, api_key=args.api_key,
            timeout=args.timeout, post_fn=post_fn, verbose=args.verbose,
        )

    if not args.single_turn_only:
        print(f"\n[MULTI-TURN] n={len(MULTI_TURN)}")
        multi_rows = _run_multi_turn(
            MULTI_TURN, endpoint=endpoint, api_key=args.api_key,
            timeout=args.timeout, post_fn=post_fn, verbose=args.verbose,
        )

    finished = _now_iso()
    single_agg = _aggregate(single_rows) if single_rows else {}
    multi_agg = _aggregate(multi_rows, coh_field="is_coherent") if multi_rows else {}

    # Print summary
    print("\n" + "=" * 78)
    if single_rows:
        print(f"[SINGLE-TURN] n={single_agg['n_clean']}/{single_agg['n_total']}")
        for k in ("ref_loose", "ref_strict", "ref_conciseness", "keyword_recall",
                  "regulatory_tone", "latency_p50_ms", "latency_p95_ms"):
            v = single_agg.get(k)
            if v is not None:
                print(f"  {k:<20} : {v}")
        print(f"  by_category:")
        for cat, m in single_agg.get("by_category", {}).items():
            print(f"    {cat:<28} n={m['n']:<3}  refL={m['ref_loose']:.3f}  "
                  f"refS={m['ref_strict']:.3f}  kw={m['keyword_recall']:.3f}")
    if multi_rows:
        print(f"\n[MULTI-TURN] n={multi_agg['n_clean']}/{multi_agg['n_total']}  "
              f"coh_rate={multi_agg.get('coherence_rate', 0):.3f}  "
              f"({multi_agg.get('coherent_count', 0)}/{multi_agg['n_clean']})")
        for k in ("ref_loose", "ref_strict", "keyword_recall", "regulatory_tone",
                  "latency_p50_ms"):
            v = multi_agg.get(k)
            if v is not None:
                print(f"  {k:<20} : {v}")

    # Persist sidecar
    out_dir = Path(__file__).parent.parent / "bench" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"r89-probe-{args.label}.json"
    sidecar = {
        "label": args.label,
        "mode": "local" if args.local else "live",
        "endpoint": endpoint,
        "started_at": started,
        "finished_at": finished,
        "single_turn": {"summary": single_agg, "rows": single_rows},
        "multi_turn": {"summary": multi_agg, "rows": multi_rows},
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2, ensure_ascii=False)
    print(f"\nsidecar: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
