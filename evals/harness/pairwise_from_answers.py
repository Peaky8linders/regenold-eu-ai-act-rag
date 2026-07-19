"""Pairwise-judge two PRE-CAPTURED answer sets (the cross-process A/B path).

WHY THIS EXISTS
---------------
``ab_judge`` captures both arms IN ONE PROCESS by toggling env between them.
That is correct for a REGENOLD-side flag (read fresh per call) but IMPOSSIBLE
for a change that lives BEHIND a different ``OPENAI_API_BASE`` — the wrapper
provider (``app.llm.openai_wrapper_provider.get_openai_wrapper_provider``) binds
its base URL at FIRST construction of a process-wide singleton, and ``ab_judge``
never resets it, so arm B silently reuses arm A's base.

The wrapper system-prompt fix (``claude_cli.py`` — SDK 0.2.82 drops
``{"type":"text"}``; a plain str is honored, env-gated
``WRAPPER_FORWARD_SYSTEM_PROMPT``) is exactly such a change: OFF vs ON is two
wrapper INSTANCES on two ports. So each arm is captured by a SEPARATE
``easyhard_ab`` process pointed at its own ``OPENAI_API_BASE`` (each binds its
own singleton at start), and THIS module runs the identical position-swapped
pairwise judge over the two resulting sidecars.

It REUSES ``ab_judge`` wholesale — ``ArmAnswer``, ``_pairwise_verdict`` (both
orders must agree; a flip -> tie), ``AxisResult`` + the two-sided sign test, and
``pairwise_prompts`` — so the instrument is byte-identical to the in-process one;
only the answer SOURCE differs (a sidecar row instead of a live capture).

USAGE
-----
    # 1. capture each wrapper instance as its own single-arm scorecard
    OPENAI_API_BASE=http://127.0.0.1:8000/v1 ... \\
      python -m evals.harness.easyhard_ab --local --label t1-sysprompt-off
    OPENAI_API_BASE=http://127.0.0.1:8001/v1 ... \\
      python -m evals.harness.easyhard_ab --local --label t1-sysprompt-on
    # 2. pairwise-judge the two sidecars (baseline = A, branch = B)
    python -m evals.harness.pairwise_from_answers --label t1-sysprompt \\
      --baseline-sidecar evals/bench/results/easyhard-t1-sysprompt-off.json \\
      --branch-sidecar   evals/bench/results/easyhard-t1-sysprompt-on.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals.harness import pairwise_prompts
from evals.harness.ab_judge import ArmAnswer, AxisResult, _pairwise_verdict
from evals.harness.probe_set import ProbeRow, load_probe_set

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"


def _load_arm(path: str) -> dict[str, ArmAnswer]:
    """Build {id: ArmAnswer} from a single-arm easyhard_ab sidecar.

    A single-arm run (no --branch-env) writes its rows under ``baseline_rows``.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("baseline_rows") or data.get("branch_rows") or []
    out: dict[str, ArmAnswer] = {}
    for r in rows:
        if r.get("error") or not r.get("pred_answer"):
            continue
        out[r["id"]] = ArmAnswer(
            answer=str(r.get("pred_answer") or ""),
            refs=list(r.get("pred_refs") or []),
            latency_ms=float(r.get("latency_ms") or 0.0),
            http_status=int(r.get("http_status") or 200),
        )
    return out


def _probe_index(rows: list[ProbeRow]) -> dict[str, ProbeRow]:
    # probe_set ids are bare (mt_v4_005); easyhard sidecar ids are
    # "<source>:<id>" (paper_mt_v4:mt_v4_005). Index BOTH forms.
    idx: dict[str, ProbeRow] = {}
    for r in rows:
        idx[r.id] = r
        idx[f"{r.source}:{r.id}"] = r
    return idx


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--label", required=True)
    p.add_argument("--baseline-sidecar", required=True, help="A arm (e.g. sysprompt OFF)")
    p.add_argument("--branch-sidecar", required=True, help="B arm (e.g. sysprompt ON)")
    p.add_argument("--judge-provider", default="wrapper", choices=["wrapper", "anthropic", "groq"])
    p.add_argument("--judge-model", default="claude-sonnet-4-6")
    args = p.parse_args(argv)

    arm_a = _load_arm(args.baseline_sidecar)
    arm_b = _load_arm(args.branch_sidecar)
    idx = _probe_index(load_probe_set())

    common = [k for k in arm_a if k in arm_b and (k in idx)]
    if not common:
        print("[pairwise_from_answers] no aligned rows (id mismatch?)", file=sys.stderr)
        return 2

    from evals.judge.runner import (
        _load_article_summaries,
        _resolve_caller,
        set_judge_model,
    )

    set_judge_model(args.judge_model)
    caller = _resolve_caller(args.judge_provider)
    summaries = _load_article_summaries()
    axes = {ax: AxisResult(axis=ax) for ax in pairwise_prompts.AXES}
    per_row: list[dict[str, Any]] = []

    print(f"[pairwise_from_answers] rows={len(common)} judge={args.judge_model}", flush=True)
    for i, rid in enumerate(common):
        row = idx[rid]
        a, b = arm_a[rid], arm_b[rid]
        rd = {
            "question": row.live_question,
            "expected_keywords": list(row.expected_keywords),
            "expected_refs": list(row.expected_refs),
        }
        verdicts: dict[str, str] = {}
        for ax in pairwise_prompts.AXES:
            v = _pairwise_verdict(rd, ax, a, b, caller, summaries)
            verdicts[ax] = v
            if v == "B":
                axes[ax].wins_b += 1
            elif v == "A":
                axes[ax].wins_a += 1
            else:
                axes[ax].ties += 1
        per_row.append({"id": rid, "category": row.category, "verdicts": verdicts})
        print(f"  [judge] {i + 1}/{len(common)} {rid}  {verdicts}", flush=True)

    result = {
        "label": args.label,
        "tier": "live-pairwise-from-sidecars",
        "n_rows": len(common),
        "baseline_sidecar": args.baseline_sidecar,
        "branch_sidecar": args.branch_sidecar,
        "judge_model": args.judge_model,
        "axes": {
            ax: {
                "wins_branch": r.wins_b, "wins_baseline": r.wins_a, "ties": r.ties,
                "win_rate_branch": r.win_rate_b(), "p_value": r.p_value(),
                "verdict": r.verdict(),
            }
            for ax, r in axes.items()
        },
        "per_row": per_row,
    }

    print("\n" + "=" * 78)
    print(f"PAIRWISE-FROM-ANSWERS — label={args.label!r}  n={len(common)}")
    print(f"  A/baseline: {args.baseline_sidecar}")
    print(f"  B/branch  : {args.branch_sidecar}")
    print("=" * 78)
    print(f"  {'axis':<14} {'B-win':>5} {'A-win':>5} {'tie':>4} {'win%B':>7} {'p':>7}  verdict")
    for ax, r in result["axes"].items():
        wr = r["win_rate_branch"]
        wr_s = f"{wr:.3f}" if wr is not None else "  -  "
        print(f"  {ax:<14} {r['wins_branch']:>5} {r['wins_baseline']:>5} "
              f"{r['ties']:>4} {wr_s:>7} {r['p_value']:>7.3f}  {r['verdict']}")

    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"pairwise-from-answers-{args.label}.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nsidecar: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
