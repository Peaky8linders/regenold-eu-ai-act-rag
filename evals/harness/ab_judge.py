"""R138-eval — the live pairwise-judge A/B win-measure.

Runs each consolidated probe row (``probe_set``) through the route under TWO
env-defined arms (baseline vs branch), then a POSITION-SWAPPED pairwise judge
aggregates a per-axis WIN-RATE + two-sided sign-test p-value. This is the
reliable, repeatable, PRE-merge answer to "did this change actually beat
baseline on the rubric axes davidath can't see" — replacing the manual
"confirm post-deploy" ritual.

WHY PAIRWISE (the variance crux): Sonnet Stage-2 is non-deterministic. The
existing absolute judge scores each arm separately, so a branch-vs-baseline
diff is dominated by generation + judge noise (R72-live saw mt-coherence swing
0.16-0.32 on the SAME code). Pairwise presents BOTH answers in ONE call (the
judge's own variance is shared, not differenced), position-swaps to cancel
position bias, and aggregates a win-rate whose CI shrinks with n.

TWO TIERS
* LIVE pairwise (default, needs the Claude Max wrapper at 127.0.0.1:8000):
  both arms generated through the in-process TestClient + wrapper (Stage-2
  fires), pairwise-judged. The right tool for Stage-2 / prompt / synthesis
  changes.
* DETERMINISTIC (``--deterministic`` or wrapper-down fallback): both arms run
  ``provider=cli`` (no Sonnet) and are scored with the exact reference /
  keyword metrics — free + reliable, the right tool for retrieval / scope /
  budget changes (~70% of rounds). NEVER substitutes token-overlap as a "win"
  proxy on the live tier (that poisons signal, R82).

Reuses: ``runner_v2._ensure_local_auth`` / ``_post_local`` (in-process route),
``evals.judge.runner`` (judge call + retry + parse + KB summaries),
``evals.bench.metrics`` (deterministic-tier scoring),
``app.routes.regenold._ENGINE_CACHE`` (cleared between arms).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.harness import pairwise_prompts
from evals.harness.probe_set import ProbeRow, category_counts, load_probe_set

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"
_WRAPPER_AUTH_URL = "http://127.0.0.1:8000/v1/auth/status"


# ──────────────────────────────────────────────────────────────────────────
# Env arm + cache helpers.
# ──────────────────────────────────────────────────────────────────────────


def _parse_env_pairs(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or ():
        if "=" not in p:
            raise ValueError(f"--*-env expects KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    return out


def _clear_engine_cache() -> None:
    """Drop the route LRU so an arm never serves the other arm's cached blob."""
    try:
        from app.routes.regenold import _ENGINE_CACHE  # noqa: PLC0415
        clear = getattr(_ENGINE_CACHE, "clear", None)
        if callable(clear):
            clear()
    except Exception:  # noqa: BLE001
        pass


def _wrapper_up(timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(_WRAPPER_AUTH_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


# ──────────────────────────────────────────────────────────────────────────
# Arm capture — POST every probe row through the route under one env arm.
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class ArmAnswer:
    answer: str
    refs: list[str]
    latency_ms: float
    http_status: int


def _capture_arm(
    rows: list[ProbeRow],
    env_overrides: dict[str, str],
    *,
    timeout: float,
    label: str,
) -> dict[str, ArmAnswer]:
    """Set the arm env, then POST each probe row in-process; capture answer+refs.

    Env is restored on exit. The engine cache is cleared before the arm so a
    prior arm's blob can't bleed across.
    """
    from evals.regenold.runner_v2 import _ensure_local_auth, _post_local

    saved: dict[str, str | None] = {k: os.environ.get(k) for k in env_overrides}
    for k, v in env_overrides.items():
        os.environ[k] = v
    _clear_engine_cache()
    key = _ensure_local_auth()
    out: dict[str, ArmAnswer] = {}
    try:
        for i, row in enumerate(rows):
            body, latency, status, _err, _att, _retried = _post_local(
                "x://local?include_reasoning=true",
                key,
                [dict(m) for m in row.messages],
                timeout,
            )
            out[row.id] = ArmAnswer(
                answer=str(body.get("answer") or ""),
                refs=list(body.get("references") or []),
                latency_ms=float(latency),
                http_status=int(status),
            )
            print(f"  [{label}] {i + 1}/{len(rows)} {row.id}", flush=True)
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        _clear_engine_cache()
    return out


# ──────────────────────────────────────────────────────────────────────────
# Pairwise judge — position-swapped, both orders must agree for a decisive win.
# ──────────────────────────────────────────────────────────────────────────


def _judge_one(caller, prompt: str) -> str:
    """Return 'A' | 'B' | 'tie' (or 'tie' on any judge error)."""
    from evals.judge.runner import _call_judge_with_retry

    result, _attempts, _retried = _call_judge_with_retry(caller, prompt)
    if not isinstance(result, dict) or result.get("judge_error"):
        return "tie"
    w = str(result.get("winner") or "").strip().upper()
    return w if w in ("A", "B") else "tie"


def _pairwise_verdict(
    row_dict: dict[str, Any],
    axis: str,
    a: ArmAnswer,
    b: ArmAnswer,
    caller,
    summaries: dict[str, str],
) -> str:
    """Position-swapped pairwise verdict for one axis.

    Returns 'A' (baseline) / 'B' (branch) / 'tie'. A decisive win requires BOTH
    orderings to agree; a position-flip → 'tie' (cancels position bias).
    """
    # Order 1: prompt-A = arm-A, prompt-B = arm-B.
    p1 = pairwise_prompts.render(
        axis, row_dict, answer_a=a.answer, refs_a=a.refs,
        answer_b=b.answer, refs_b=b.refs, article_summaries=summaries,
    )
    w1 = _judge_one(caller, p1)
    # Order 2 (swapped): prompt-A = arm-B, prompt-B = arm-A.
    p2 = pairwise_prompts.render(
        axis, row_dict, answer_a=b.answer, refs_a=b.refs,
        answer_b=a.answer, refs_b=a.refs, article_summaries=summaries,
    )
    w2_raw = _judge_one(caller, p2)
    # Translate order-2 back to arm space.
    w2 = {"A": "B", "B": "A", "tie": "tie"}[w2_raw]
    if w1 == w2 and w1 in ("A", "B"):
        return w1
    return "tie"


# ──────────────────────────────────────────────────────────────────────────
# Aggregation — win-rate + two-sided sign test.
# ──────────────────────────────────────────────────────────────────────────


def _sign_test_two_sided(wins_b: int, wins_a: int) -> float:
    """Two-sided exact binomial sign test p-value over decisive pairs (p=0.5).

    Ties are excluded (standard sign test). Returns 1.0 when there are no
    decisive pairs.
    """
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = max(wins_a, wins_b)
    # P(X >= k) + P(X <= n-k) under Binomial(n, 0.5), two-sided.
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    p = min(1.0, 2.0 * tail)
    return round(p, 4)


@dataclass
class AxisResult:
    axis: str
    wins_b: int = 0   # branch beats baseline
    wins_a: int = 0   # baseline beats branch
    ties: int = 0

    def win_rate_b(self) -> float | None:
        dec = self.wins_a + self.wins_b
        return round(self.wins_b / dec, 4) if dec else None

    def p_value(self) -> float:
        return _sign_test_two_sided(self.wins_b, self.wins_a)

    def verdict(self) -> str:
        wr = self.win_rate_b()
        if wr is None:
            return "no-decisive-pairs"
        p = self.p_value()
        if wr > 0.5 and p < 0.05:
            return "BRANCH wins (sig)"
        if wr < 0.5 and p < 0.05:
            return "BASELINE wins (sig)"
        if wr > 0.5:
            return "branch leans (ns)"
        if wr < 0.5:
            return "baseline leans (ns)"
        return "even"


# ──────────────────────────────────────────────────────────────────────────
# Deterministic tier — exact reference/keyword scoring, no Sonnet.
# ──────────────────────────────────────────────────────────────────────────


def _deterministic_scores(rows: list[ProbeRow], arm: dict[str, ArmAnswer]) -> dict[str, float]:
    from evals.bench import metrics

    rl = rs = kw = 0.0
    kw_n = 0
    for row in rows:
        ans = arm.get(row.id)
        if ans is None:
            continue
        # reference_correctness_* accept a list[str] gold via _gold_ref_set.
        rl += metrics.reference_correctness_loose(ans.refs, list(row.expected_refs))
        rs += metrics.reference_correctness_strict(ans.refs, list(row.expected_refs))
        k = metrics.answer_keyword_recall(ans.answer, list(row.expected_keywords))
        if k is not None:
            kw += k
            kw_n += 1
    n = max(1, len(rows))
    return {
        "ref_loose": round(rl / n, 4),
        "ref_strict": round(rs / n, 4),
        "keyword_recall": round(kw / kw_n, 4) if kw_n else 0.0,
        "n": len(rows),
    }


# ──────────────────────────────────────────────────────────────────────────
# Orchestration.
# ──────────────────────────────────────────────────────────────────────────


def run_ab(
    *,
    baseline_env: dict[str, str],
    branch_env: dict[str, str],
    rows: list[ProbeRow],
    deterministic: bool,
    judge_provider: str,
    timeout: float,
    label: str,
) -> dict[str, Any]:
    live = not deterministic and _wrapper_up()
    if not deterministic and not live:
        print("[ab_judge] WRAPPER DOWN at 127.0.0.1:8000 — skipping the live "
              "pairwise tier; running the DETERMINISTIC tier only. (Never "
              "substituting token-overlap as a live win proxy.)", file=sys.stderr)
        deterministic = True

    # In live mode both arms must run with a Stage-2 provider wired; in
    # deterministic mode both run cli. The caller's env dicts carry the actual
    # A/B knob (e.g. REGENOLD_SEMANTIC_CONTRACT 0 vs 1); we layer the mode env
    # underneath so the knob is the only difference.
    mode_env = (
        {"P2P_GRAPH_RAG_PROVIDER": "cli"} if deterministic
        else {
            "P2P_GRAPH_RAG_PROVIDER": "openai_wrapper",
            "OPENAI_API_BASE": os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8000/v1"),
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "dummy"),
            "P2P_GRAPH_RAG_ENABLE_STAGE2": "1",
        }
    )
    a_env = {**mode_env, **baseline_env}
    b_env = {**mode_env, **branch_env}

    print(f"[ab_judge] tier={'deterministic' if deterministic else 'live-pairwise'} "
          f"rows={len(rows)}  baseline_env={baseline_env}  branch_env={branch_env}",
          flush=True)
    arm_a = _capture_arm(rows, a_env, timeout=timeout, label="A/baseline")
    arm_b = _capture_arm(rows, b_env, timeout=timeout, label="B/branch")

    result: dict[str, Any] = {
        "label": label,
        "tier": "deterministic" if deterministic else "live-pairwise",
        "n_rows": len(rows),
        "category_counts": category_counts(rows),
        "baseline_env": baseline_env,
        "branch_env": branch_env,
    }

    if deterministic:
        a_sc = _deterministic_scores(rows, arm_a)
        b_sc = _deterministic_scores(rows, arm_b)
        result["deterministic"] = {
            "baseline": a_sc,
            "branch": b_sc,
            "delta": {k: round(b_sc[k] - a_sc[k], 4) for k in ("ref_loose", "ref_strict", "keyword_recall")},
        }
        return result

    # LIVE pairwise judge.
    from evals.judge.runner import _load_article_summaries, _resolve_caller, set_judge_model

    model = os.environ.get("REGENOLD_AB_JUDGE_MODEL", "claude-sonnet-4-6")
    set_judge_model(model)
    caller = _resolve_caller(judge_provider)
    summaries = _load_article_summaries()
    axes = {ax: AxisResult(axis=ax) for ax in pairwise_prompts.AXES}
    per_row: list[dict[str, Any]] = []

    for i, row in enumerate(rows):
        a, b = arm_a.get(row.id), arm_b.get(row.id)
        if a is None or b is None:
            continue
        rd = {"question": row.live_question,
              "expected_keywords": list(row.expected_keywords),
              "expected_refs": list(row.expected_refs)}
        row_verdicts: dict[str, str] = {}
        for ax in pairwise_prompts.AXES:
            v = _pairwise_verdict(rd, ax, a, b, caller, summaries)
            row_verdicts[ax] = v
            if v == "B":
                axes[ax].wins_b += 1
            elif v == "A":
                axes[ax].wins_a += 1
            else:
                axes[ax].ties += 1
        per_row.append({"id": row.id, "category": row.category, "verdicts": row_verdicts})
        print(f"  [judge] {i + 1}/{len(rows)} {row.id}  {row_verdicts}", flush=True)

    result["judge_model"] = model
    result["axes"] = {
        ax: {
            "wins_branch": r.wins_b, "wins_baseline": r.wins_a, "ties": r.ties,
            "win_rate_branch": r.win_rate_b(), "p_value": r.p_value(),
            "verdict": r.verdict(),
        }
        for ax, r in axes.items()
    }
    result["per_row"] = per_row
    return result


def _format(result: dict[str, Any]) -> str:
    lines = ["=" * 78, f"AB-JUDGE — label={result['label']!r}  tier={result['tier']}",
             f"rows={result['n_rows']}  categories={result['category_counts']}",
             f"  A/baseline env: {result['baseline_env']}",
             f"  B/branch   env: {result['branch_env']}", "=" * 78]
    if result["tier"] == "deterministic":
        d = result["deterministic"]
        lines.append("[DETERMINISTIC tier — exact ref/keyword scoring, no Sonnet]")
        for k in ("ref_loose", "ref_strict", "keyword_recall"):
            lines.append(f"  {k:<16} A={d['baseline'][k]:.4f}  B={d['branch'][k]:.4f}  "
                         f"d={d['delta'][k]:+.4f}")
    else:
        lines.append(f"[LIVE PAIRWISE — judge={result['judge_model']}, position-swapped]")
        lines.append(f"  {'axis':<14} {'B-win':>5} {'A-win':>5} {'tie':>4} "
                     f"{'win%B':>7} {'p':>7}  verdict")
        for ax, r in result["axes"].items():
            wr = r["win_rate_branch"]
            wr_s = f"{wr:.3f}" if wr is not None else "  -  "
            lines.append(f"  {ax:<14} {r['wins_branch']:>5} {r['wins_baseline']:>5} "
                         f"{r['ties']:>4} {wr_s:>7} {r['p_value']:>7.3f}  {r['verdict']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    p = argparse.ArgumentParser(description="R138 live pairwise-judge A/B win-measure.")
    p.add_argument("--label", required=True)
    p.add_argument("--baseline-env", nargs="*", default=[], metavar="KEY=VAL",
                   help="env overrides defining the A/baseline arm (e.g. REGENOLD_SEMANTIC_CONTRACT=0)")
    p.add_argument("--branch-env", nargs="*", default=[], metavar="KEY=VAL",
                   help="env overrides defining the B/branch arm (e.g. REGENOLD_SEMANTIC_CONTRACT=1)")
    p.add_argument("--sources", nargs="*", default=None,
                   help="restrict probe sources (paper_st_v4 paper_tricky_v4 paper_mt_v4 tricky_v2 mt_v2)")
    p.add_argument("--categories", nargs="*", default=None)
    p.add_argument("--multiturn", choices=["only", "exclude"], default=None)
    p.add_argument("--limit", type=int, default=None, help="cap probe rows (cheap smoke)")
    p.add_argument("--deterministic", action="store_true",
                   help="run both arms provider=cli + exact ref/keyword scoring (no Sonnet)")
    p.add_argument("--judge-provider", default="wrapper", choices=["wrapper", "anthropic", "groq"])
    p.add_argument("--timeout", type=float, default=90.0)
    args = p.parse_args(argv)

    mt = {"only": True, "exclude": False}.get(args.multiturn or "")
    rows = load_probe_set(
        sources=tuple(args.sources) if args.sources else None,
        categories=tuple(args.categories) if args.categories else None,
        multiturn=mt,
        limit=args.limit,
    )
    if not rows:
        print("[ab_judge] no probe rows after filtering.", file=sys.stderr)
        return 2

    result = run_ab(
        baseline_env=_parse_env_pairs(args.baseline_env),
        branch_env=_parse_env_pairs(args.branch_env),
        rows=rows,
        deterministic=args.deterministic,
        judge_provider=args.judge_provider,
        timeout=args.timeout,
        label=args.label,
    )
    print("\n" + _format(result))
    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"ab-judge-{args.label}.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nsidecar: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
