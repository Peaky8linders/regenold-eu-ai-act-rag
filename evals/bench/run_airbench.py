"""Standalone AIR-Bench 2024 ``eu_mandatory`` eval runner.

Loads the Stanford CRFM AIR-Bench ``eu_mandatory`` subset (3,400 adversarial
prompts) and measures the engine's Refusal Correctness — the fraction of
prohibited-practice prompts that the system correctly refuses.

**Gate**: requires ``REGENOLD_AIRBENCH=1`` env var. The prompts are
adversarial; don't run this in production or in automated CI without
explicit opt-in.

CLI:
    # Set the gate env var first
    $env:REGENOLD_AIRBENCH = "1"
    .venv\\Scripts\\python.exe -m evals.bench.run_airbench
    .venv\\Scripts\\python.exe -m evals.bench.run_airbench --label r60-airbench
    .venv\\Scripts\\python.exe -m evals.bench.run_airbench --limit 50  # smoke

The runner uses FastAPI's TestClient (in-process, no real network or LLM
needed for the deterministic path) — identical to ``evals.bench.runner``.
Results are written to ``evals/bench/results/<label>_airbench.json``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.main import app
from app.rate_limit import limiter

from evals.bench import airbench_2024
from evals.bench import metrics
from evals.bench import storage


_EVAL_KEY = "regenold-bench-eval-key"
_RESULTS_DIR = Path(__file__).parent / "results"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ask(client: TestClient, prompt: str) -> tuple[dict, float, int]:
    """Single-turn request. Returns ``(body, latency_ms, http_status)``."""
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass
    payload = [{"role": "user", "content": prompt}]
    start = time.perf_counter()
    resp = client.post("/api/v1/regenold/eu-ai-act/ask", json=payload)
    elapsed = (time.perf_counter() - start) * 1000.0
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"answer": "", "references": [], "reasoning": None}
    if not isinstance(body, dict):
        body = {"answer": "", "references": [], "reasoning": None}
    return body, elapsed, resp.status_code


def run(
    *,
    label: str = "adhoc",
    limit: int | None = None,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    """Run the AIR-Bench eu_mandatory eval and return the persisted payload.

    Args:
        label:     Result sidecar label (written to results/<label>_airbench.json).
        limit:     If set, cap the row count (e.g. limit=50 for a smoke run).
        cache_dir: HuggingFace cache directory override for load_eu_mandatory().

    Returns:
        The persisted result payload dict (includes sidecar_path).
    """
    env_gate = os.environ.get("REGENOLD_AIRBENCH", "").strip().lower()
    if env_gate not in ("1", "true", "yes", "on"):
        raise RuntimeError(
            "REGENOLD_AIRBENCH is not set. "
            "Set REGENOLD_AIRBENCH=1 to run adversarial AIR-Bench prompts."
        )

    rows_raw = airbench_2024.load_eu_mandatory(cache_dir=cache_dir)
    if not rows_raw:
        warnings.warn(
            "AIR-Bench eu_mandatory returned 0 rows — is 'datasets' installed? "
            "Run: pip install datasets",
            UserWarning,
            stacklevel=2,
        )

    if limit is not None:
        rows_raw = rows_raw[:limit]

    started_at = _now_iso()
    prev_key = settings.regenold.api_key
    settings.regenold.api_key = SecretStr(_EVAL_KEY)

    result_rows: list[dict[str, Any]] = []
    try:
        with TestClient(
            app, headers={"X-Regenold-Api-Key": _EVAL_KEY}
        ) as client:
            for idx, raw in enumerate(rows_raw):
                prompt = raw["prompt"]
                cate_idx = raw["cate_idx"]
                l3_name = raw["l3_name"]
                gold_refs = airbench_2024.derive_gold_refs(cate_idx)

                body, latency_ms, http_status = _ask(client, prompt)
                answer = body.get("answer") or ""
                pred_refs = body.get("references") or []

                score = airbench_2024.score_row(
                    answer=answer,
                    refs=pred_refs,
                    gold_refs=gold_refs,
                )

                result_rows.append(
                    {
                        "item_id": f"air_{idx:05d}",
                        "cate_idx": cate_idx,
                        "l3_name": l3_name,
                        "prompt_preview": prompt[:200],
                        "gold_refs": gold_refs,
                        "pred_answer_preview": answer[:300],
                        "pred_refs": pred_refs,
                        "http_status": http_status,
                        "latency_ms": round(latency_ms, 2),
                        "refused": score["refused"],
                        "ref_loose": score["ref_loose"],
                    }
                )
    finally:
        settings.regenold.api_key = prev_key

    finished_at = _now_iso()

    # Aggregate
    refused_flags = [r["refused"] for r in result_rows]
    ref_loose_scores = [r["ref_loose"] for r in result_rows]
    latencies = [r["latency_ms"] for r in result_rows]
    n = len(result_rows)

    refusal_rate = metrics.refusal_correctness(refused_flags)
    avg_ref_loose = sum(ref_loose_scores) / n if n else 0.0

    # Per-category breakdown
    category_stats: dict[str, dict[str, Any]] = {}
    for r in result_rows:
        prefix = (r["cate_idx"] or "?")[:2]  # top-level like "1.", "2.", "3."
        if prefix not in category_stats:
            category_stats[prefix] = {
                "n": 0, "refused": 0, "ref_loose_sum": 0.0
            }
        category_stats[prefix]["n"] += 1
        category_stats[prefix]["refused"] += int(r["refused"])
        category_stats[prefix]["ref_loose_sum"] += r["ref_loose"]

    category_summary = {
        prefix: {
            "n": s["n"],
            "refusal_rate": round(s["refused"] / s["n"], 4) if s["n"] else 0.0,
            "ref_loose": round(s["ref_loose_sum"] / s["n"], 4) if s["n"] else 0.0,
        }
        for prefix, s in sorted(category_stats.items())
    }

    summary = {
        "n": n,
        "refusal_correctness": round(refusal_rate, 4),
        "ref_correctness_loose": round(avg_ref_loose, 4),
        "latency_p50_ms": round(metrics.percentile(latencies, 50), 2),
        "latency_p95_ms": round(metrics.percentile(latencies, 95), 2),
        "latency_max_ms": round(max(latencies) if latencies else 0.0, 2),
        "category_breakdown": category_summary,
    }

    # Sanitise label for filename
    slug = "".join(c if c.isalnum() or c in "._-" else "_" for c in label)
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sidecar_path = _RESULTS_DIR / f"{slug}_airbench.json"

    payload: dict[str, Any] = {
        "label": label,
        "dataset": "stanford-crfm/air-bench-2024",
        "subset": "eu_mandatory",
        "started_at": started_at,
        "finished_at": finished_at,
        "summary": summary,
        "rows": result_rows,
    }
    sidecar_path.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    payload["sidecar_path"] = str(sidecar_path)
    return payload


def _format_human_summary(payload: dict[str, Any]) -> str:
    """Render a one-screen scorecard for the terminal."""
    s = payload.get("summary") or {}
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(
        f"AIR-Bench 2024 eu_mandatory — label={payload.get('label')!r}"
    )
    lines.append("=" * 78)
    lines.append(f"dataset : {payload.get('dataset')!r}")
    lines.append(f"subset  : {payload.get('subset')!r}")
    lines.append("")
    lines.append(f"[OVERALL] n={s.get('n', 0)}")
    lines.append(f"  Refusal Correctness   : {s.get('refusal_correctness', '-')}")
    lines.append(f"  Ref Correctness Loose : {s.get('ref_correctness_loose', '-')}")
    lines.append(
        f"  Latency: p50={s.get('latency_p50_ms','-')}ms  "
        f"p95={s.get('latency_p95_ms','-')}ms  "
        f"max={s.get('latency_max_ms','-')}ms"
    )
    lines.append("")
    cat = s.get("category_breakdown") or {}
    if cat:
        lines.append("[BY CATEGORY PREFIX]")
        for prefix, stats in sorted(cat.items()):
            lines.append(
                f"  {prefix!r:6s}  n={stats['n']:4d}  "
                f"refusal={stats['refusal_rate']:.3f}  "
                f"refL={stats['ref_loose']:.3f}"
            )
    lines.append("")
    lines.append(f"sidecar : {payload.get('sidecar_path', '?')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="adhoc")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of rows (e.g. 50 for a smoke run). None = all.",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="HuggingFace cache directory override.",
    )
    args = parser.parse_args(argv)

    try:
        payload = run(
            label=args.label,
            limit=args.limit,
            cache_dir=args.cache_dir,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(_format_human_summary(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
