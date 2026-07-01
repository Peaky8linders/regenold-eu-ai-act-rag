"""R263 — adversarial-triage pass for the live production-audit sidecar.

Distinct from the calibrated 4-axis judge in ``evals.judge.runner``
(correctness / refs / conciseness / tone, binary pass-fail). This module
is the FIRST stage of a find-then-verify pipeline: an aggressively
skeptical reviewer persona that hunts for concrete, evidence-backed
defects per row — legal errors, wrong sub-citations, role confusion
(provider vs deployer), incomplete enumeration, irrelevant citations,
hedging/refusal-when-shouldn't, tone drift, Regenold-rubric violations
(reference-format, answer length, latency-shape) — and reports them as
a structured list with a severity + confidence per finding.

The calibrated judge in ``evals.judge.runner`` is the impartial scorer
that runs SEPARATELY (does not see this triage output) so the two
passes stay independent — this triage's job is high-recall issue-
finding, the calibrated judge's job is unbiased rubric scoring; a
later synthesis step reconciles the two.

Reuses the wrapper-call plumbing from ``evals.judge.runner`` (so it
honours the same retry policy + provider routing) but issues ONE call
per row with a free-text JSON-list response shape, not 4 single-axis
binary calls.

CLI:
    python -m evals.judge.adversarial_triage \
        --sidecar .evalout/r263/sidecar.json \
        --raw-sidecar .evalout/r263/sidecar-raw.json \
        --label r263-triage --model claude-sonnet-5 --provider wrapper
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

from evals.judge.runner import (  # noqa: PLC0415 — same-package reuse
    _call_judge_anthropic,
    _call_judge_groq,
    _call_judge_sonnet,
    _call_judge_with_retry,
    _parse_judge_json,
    set_judge_model,
)


def _resolve_caller(provider: str, timeout_s: float):
    """Like ``evals.judge.runner._resolve_caller`` but with a
    configurable per-call timeout — Sonnet 5 + the live wrapper/tunnel
    routinely runs 20-60s per call (CLAUDE.md latency tables), well past
    the runner module's 30s judge default tuned for shorter axis prompts."""
    if provider == "anthropic":
        return lambda p: _call_judge_anthropic(p, timeout_s=timeout_s)
    if provider == "groq":
        return lambda p: _call_judge_groq(p, timeout_s=timeout_s)
    return lambda p: _call_judge_sonnet(p, timeout_s=timeout_s)

_TRIAGE_SYSTEM = (
    "You are an ADVERSARIAL, skeptical quality-assurance reviewer auditing "
    "an EU AI Act (Regulation 2024/1689) compliance Q&A system's live "
    "production answers. Your job is to find real problems, not to be "
    "agreeable. Assume nothing is correct until you have checked it against "
    "your own knowledge of the Regulation's text and structure. Be precise: "
    "cite the specific article/sub-point that is wrong or missing, not "
    "vague impressions. If the answer is genuinely solid, say so plainly — "
    "do not invent issues to seem thorough, but do not let a plausible-"
    "sounding answer pass without checking its substance.\n\n"
    "Respond with ONE JSON object only — no preamble, no markdown fences."
)


def _render_triage_prompt(row: dict[str, Any]) -> str:
    q = (row.get("question") or "")[:600]
    a = (row.get("predicted_answer") or "")[:1400]
    refs = row.get("pred_refs") or []
    return (
        "Audit this live EU AI Act Q&A answer against the Regulation's actual "
        "text and against the Regenold competition rubric (correctness vs "
        "the question, minimal-and-accurate references, professional "
        "1-4 sentence conciseness, regulator tone).\n\n"
        f"QUESTION: {q}\n"
        f"ANSWER: {a}\n"
        f"CITED REFERENCES: {refs}\n\n"
        "Find concrete issues. For EACH issue report:\n"
        "  - category: one of [factual_error, wrong_subcitation, "
        "role_confusion, incomplete_enumeration, irrelevant_citation, "
        "missing_citation, tone_violation, refusal_unwarranted, "
        "format_violation, over_citation, other]\n"
        "  - severity: critical | major | minor\n"
        "  - confidence: 0.0-1.0 (how sure you are this is a real defect, "
        "not a stylistic preference)\n"
        "  - evidence: a short, specific justification citing the actual "
        "Article/Annex text where relevant\n"
        "  - suggested_fix: one short phrase\n\n"
        "Respond with ONE JSON object only:\n"
        '{"issues":[{"category":"...","severity":"...","confidence":0.0,'
        '"evidence":"...","suggested_fix":"..."}],'
        '"overall_verdict":"solid"|"flawed"|"broken",'
        '"summary":"<one sentence>"}\n'
        "If there are truly no issues, return an empty issues list and "
        '"overall_verdict":"solid".'
    )


def _triage_row(row: dict[str, Any], caller) -> dict[str, Any]:
    prompt = _render_triage_prompt(row)
    result, attempts, retried = _call_judge_with_retry(caller, prompt)
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "question": row.get("question"),
        "triage": result,
        "attempts": attempts,
        "retried_errors": retried,
    }


def run(
    *,
    sidecar: Path,
    label: str,
    rows_limit: int | None,
    concurrency: int,
    verbose: bool,
    provider: str,
    model: str,
    timeout_s: float = 90.0,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    set_judge_model(model)
    caller = _resolve_caller(provider, timeout_s)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = payload.get("rows") or []
    if rows_limit:
        rows = rows[:rows_limit]

    print(
        f"[triage] {len(rows)} rows, 1 adversarial call each "
        f"(provider={provider}, model={model}, concurrency={concurrency})",
        flush=True,
    )
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    t0 = time.monotonic()
    out: list[dict[str, Any] | None] = [None] * len(rows)
    completed = 0
    lock = threading.Lock()

    def _worker(idx: int, row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return idx, _triage_row(row, caller)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_worker, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futures):
            idx, result = fut.result()
            out[idx] = result
            with lock:
                completed += 1
                if verbose:
                    t = result.get("triage", {})
                    n_issues = len(t.get("issues") or []) if isinstance(t, dict) else -1
                    verdict = t.get("overall_verdict", "?") if isinstance(t, dict) else "ERROR"
                    print(
                        f"[triage] {completed}/{len(rows)} {result['id']:<10} "
                        f"verdict={verdict:<8} issues={n_issues}",
                        flush=True,
                    )

    elapsed_s = round(time.monotonic() - t0, 2)
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows_out = [r for r in out if r is not None]

    # Aggregate
    n_solid = n_flawed = n_broken = n_error = 0
    by_category: dict[str, int] = {}
    high_conf_critical: list[dict[str, Any]] = []
    for r in rows_out:
        t = r.get("triage") or {}
        if not isinstance(t, dict) or t.get("judge_error"):
            n_error += 1
            continue
        verdict = t.get("overall_verdict")
        if verdict == "solid":
            n_solid += 1
        elif verdict == "flawed":
            n_flawed += 1
        elif verdict == "broken":
            n_broken += 1
        for issue in t.get("issues") or []:
            cat = issue.get("category", "other")
            by_category[cat] = by_category.get(cat, 0) + 1
            if issue.get("severity") == "critical" and float(issue.get("confidence") or 0) >= 0.7:
                high_conf_critical.append({
                    "id": r.get("id"),
                    "question": r.get("question"),
                    **issue,
                })

    summary = {
        "label": label,
        "source_sidecar": str(sidecar),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_s": elapsed_s,
        "provider": provider,
        "model": model,
        "concurrency": concurrency,
        "rows": rows_out,
        "aggregate": {
            "n_rows": len(rows_out),
            "n_solid": n_solid,
            "n_flawed": n_flawed,
            "n_broken": n_broken,
            "n_error": n_error,
            "issues_by_category": by_category,
            "high_confidence_critical_count": len(high_conf_critical),
        },
        "high_confidence_critical_issues": high_conf_critical,
    }

    if out_dir is None:
        out_dir = Path("evals/bench/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"triage-{label}.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[triage] sidecar written to {out_path}", flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--rows-limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--provider", choices=("wrapper", "anthropic", "groq"), default="wrapper")
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    summary = run(
        sidecar=args.sidecar,
        label=args.label,
        rows_limit=args.rows_limit,
        concurrency=args.concurrency,
        verbose=args.verbose,
        provider=args.provider,
        model=args.model,
        timeout_s=args.timeout,
    )
    agg = summary["aggregate"]
    print("=" * 78)
    print(f"Triage run — label={args.label!r} elapsed={summary['elapsed_s']}s")
    print(
        f"rows={agg['n_rows']} solid={agg['n_solid']} flawed={agg['n_flawed']} "
        f"broken={agg['n_broken']} error={agg['n_error']}"
    )
    print(f"high-confidence critical issues: {agg['high_confidence_critical_count']}")
    print("issues by category:", agg["issues_by_category"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
