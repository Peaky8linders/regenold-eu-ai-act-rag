"""R50 — LLM-as-Judge runner.

Reads a bench JSON sidecar (from ``evals.bench.runner`` or
``evals.regenold.runner_v2``) and grades each row across 4 axes
(correctness, refs, conciseness, tone) via Sonnet 4.6 calls through
the existing openai_wrapper provider. Writes a judge sidecar
``evals/bench/results/judge-<label>.json`` with per-row verdicts and
per-axis aggregates.

Stdlib + same-package imports only.

CLI:
    python -m evals.judge.runner --bench-sidecar evals/bench/results/v2-r49-live.json \
                                 --label r49-live \
                                 --rows-limit 10  # for smoke

Concurrency: ThreadPoolExecutor (4 axes × N rows). The openai_wrapper
provider is httpx-based + thread-safe.

Stops cleanly on wrapper outage — every judge call is wrapped so a
single 429 / network failure doesn't kill the run; the row is marked
``judge_error`` with the failure reason and the aggregator counts it
as 'unknown' on that axis.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.judge.prompts import AXES, render

# ── Article-summary lookup (for the refs-faithfulness prompt) ───────────


def _load_article_summaries() -> dict[str, str]:
    """Build a dict from user-facing ref form (``Article N`` / ``Annex X``)
    to the article's KB summary, used to prime the refs-faithfulness
    judge prompt.

    Maps both ``Art. N`` (internal) and ``Article N`` (user-facing).
    """
    from app.data.kb import EC_CHECKER_OBLIGATION_MAP  # local import — heavy
    out: dict[str, str] = {}
    for internal_ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        if isinstance(entry, dict):
            summary = entry.get("summary") or ""
        else:
            summary = getattr(entry, "summary", "") or ""
        if not summary:
            continue
        # internal form (e.g. "Art. 13")
        out[internal_ref] = summary
        # user-facing form (e.g. "Article 13")
        if internal_ref.startswith("Art. "):
            out["Article " + internal_ref[len("Art. "):]] = summary
        elif internal_ref.startswith("Annex "):
            out[internal_ref] = summary  # already user-facing
    return out


# ── Judge call ──────────────────────────────────────────────────────────


_JUDGE_SYSTEM = (
    "You are an expert legal evaluator for EU AI Act Q&A systems. "
    "Respond with ONE JSON object only — no preamble, no markdown fences, "
    "no explanation outside the JSON."
)


def _call_judge_sonnet(prompt: str, timeout_s: float = 30.0) -> dict[str, Any]:
    """Send the judge prompt through the openai_wrapper provider and
    parse the model's JSON response. Returns the parsed dict on
    success, or ``{"judge_error": "..."}`` on any failure.

    The wrapper handles auth + 429 retry-after upstream; this function
    just unwraps the response and parses the model's JSON.
    """
    try:
        from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
            OpenAIWrapperRequest,
            get_openai_wrapper_provider,
            is_openai_wrapper_enabled,
        )
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"wrapper_unavailable: {exc}"}
    if not is_openai_wrapper_enabled():
        return {"judge_error": "wrapper_not_configured"}
    provider = get_openai_wrapper_provider()
    req = OpenAIWrapperRequest(
        system=_JUDGE_SYSTEM,
        user=prompt,
        model="claude-sonnet-4-6",
        max_tokens=400,
        temperature=0.0,
        timeout_seconds=timeout_s,
    )
    try:
        resp = provider.complete(req)
    except Exception as exc:  # noqa: BLE001
        return {"judge_error": f"call_failed: {exc}"}
    if resp is None:
        return {"judge_error": "wrapper_returned_none"}
    if resp.error:
        return {"judge_error": f"wrapper_error: {resp.error[:160]}"}
    return _parse_judge_json(resp.text or "")


def _parse_judge_json(text: str) -> dict[str, Any]:
    """Extract the first balanced JSON object from ``text``. The
    prompts ask for "ONE JSON object only" but Sonnet occasionally
    wraps in markdown fences or prepends a thinking sentence."""
    if not text:
        return {"judge_error": "empty_response"}
    # Strip a code fence if present
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json\n"):
            s = s[5:]
    # Find first { ... } balanced
    start = s.find("{")
    if start < 0:
        return {"judge_error": "no_json", "raw": text[:200]}
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                blob = s[start:i + 1]
                try:
                    return json.loads(blob)
                except Exception as exc:  # noqa: BLE001
                    return {"judge_error": f"parse_failed: {exc}", "raw": blob[:200]}
    return {"judge_error": "unbalanced_json", "raw": text[:200]}


# ── Per-row driver ──────────────────────────────────────────────────────


def _judge_row(
    row: dict[str, Any], article_summaries: dict[str, str],
) -> dict[str, Any]:
    """Run all 4 axes on a single bench row. Returns the original row
    augmented with ``judge`` field containing per-axis verdicts."""
    verdicts: dict[str, Any] = {}
    for axis in AXES:
        prompt = render(axis, row, article_summaries=article_summaries)
        result = _call_judge_sonnet(prompt)
        verdicts[axis] = result
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "verdicts": verdicts,
    }


def _run_judge(
    rows: list[dict[str, Any]], concurrency: int, verbose: bool,
) -> list[dict[str, Any]]:
    article_summaries = _load_article_summaries()
    out: list[dict[str, Any] | None] = [None] * len(rows)
    completed = 0
    lock = threading.Lock()

    def _worker(idx: int, row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return idx, _judge_row(row, article_summaries)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_worker, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futures):
            idx, judged = fut.result()
            out[idx] = judged
            with lock:
                completed += 1
                if verbose:
                    summary = ", ".join(
                        f"{axis[:4]}={(judged['verdicts'].get(axis) or {}).get('verdict', '?')}"
                        for axis in AXES
                    )
                    print(
                        f"[judge] {completed}/{len(rows)} {judged.get('id', '?'):<14} "
                        f"cat={judged.get('category', '-'):<22} {summary}",
                        flush=True,
                    )
    return [r for r in out if r is not None]


# ── Aggregation (per-axis pass rate + failure-mode buckets) ─────────────


def _aggregate_judge(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_axis: dict[str, dict[str, Any]] = {}
    for axis in AXES:
        total = len(rows)
        passes = 0
        fails = 0
        errors = 0
        modes: dict[str, int] = {}
        for r in rows:
            v = (r.get("verdicts") or {}).get(axis) or {}
            if v.get("judge_error"):
                errors += 1
                continue
            verdict = (v.get("verdict") or "").lower()
            if verdict == "pass":
                passes += 1
            elif verdict == "fail":
                fails += 1
                mode = (v.get("failure_mode") or "(unspecified)")[:80]
                modes[mode] = modes.get(mode, 0) + 1
            else:
                errors += 1
        # Top-N failure modes for the per-axis report
        top_modes = sorted(modes.items(), key=lambda kv: -kv[1])[:10]
        per_axis[axis] = {
            "n": total,
            "pass": passes,
            "fail": fails,
            "error": errors,
            "pass_rate": round(passes / total, 4) if total else 0.0,
            "top_failure_modes": top_modes,
        }
    return per_axis


# ── Top-level ───────────────────────────────────────────────────────────


def run(
    *,
    bench_sidecar: Path,
    label: str,
    rows_limit: int | None = None,
    concurrency: int = 4,
    verbose: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = json.loads(bench_sidecar.read_text(encoding="utf-8"))

    # Flatten rows from the V2 sidecar (tricky + multiturn) OR the davidath
    # sidecar (qa + scenarios). We handle both shapes.
    rows: list[dict[str, Any]] = []
    for bucket_key in ("tricky", "multiturn", "qa", "scenarios", "rows"):
        bucket = payload.get(bucket_key)
        if isinstance(bucket, dict):
            rows.extend(bucket.get("rows") or [])
        elif isinstance(bucket, list):
            rows.extend(bucket)

    if rows_limit:
        rows = rows[:rows_limit]
    print(f"[judge] {len(rows)} rows × {len(AXES)} axes against {bench_sidecar.name}",
          flush=True)
    t0 = time.monotonic()
    judged = _run_judge(rows, concurrency, verbose)
    elapsed_s = round(time.monotonic() - t0, 2)
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    aggregate = _aggregate_judge(judged)

    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"judge-{label}.json"
    summary = {
        "label": label,
        "source_sidecar": str(bench_sidecar),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_s": elapsed_s,
        "axes": list(AXES),
        "rows": judged,
        "aggregate": aggregate,
    }
    sidecar.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[judge] sidecar written to {sidecar}", flush=True)
    return summary


def _format(summary: dict[str, Any]) -> str:
    """Pretty-printer for the CLI."""
    out: list[str] = []
    out.append("=" * 78)
    out.append(f"Judge run — label={summary['label']!r}")
    out.append(f"source: {summary['source_sidecar']}")
    out.append(f"elapsed: {summary['elapsed_s']}s")
    out.append("=" * 78)
    agg = summary.get("aggregate") or {}
    for axis in summary.get("axes", []):
        a = agg.get(axis) or {}
        out.append(
            f"\n[{axis.upper()}] n={a.get('n', 0)} "
            f"pass={a.get('pass', 0)} fail={a.get('fail', 0)} "
            f"error={a.get('error', 0)} "
            f"pass_rate={a.get('pass_rate', 0.0)}"
        )
        top = a.get("top_failure_modes") or []
        if top:
            out.append("  top failure modes:")
            for mode, count in top:
                out.append(f"    {count:>3}× {mode}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-sidecar", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--rows-limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    summary = run(
        bench_sidecar=args.bench_sidecar,
        label=args.label,
        rows_limit=args.rows_limit,
        concurrency=args.concurrency,
        verbose=args.verbose,
    )
    print(_format(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
