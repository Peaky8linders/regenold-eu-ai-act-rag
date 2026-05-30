"""R97 — multi-turn LLM-routing A/B benchmark.

The best way to benchmark whether routing multi-turn / nuanced questions to
the Claude Max wrapper (Sonnet synthesis) beats the deterministic verbatim
dump is a clean A/B over the V2 probe set (25 multi-turn + 31 tricky
single-turn) with an LLM-as-judge on the quality axes:

  * **A (baseline)** — ``REGENOLD_ANSWER_ROUTER=0``: verbatim-only (R96).
    Sonnet never fires. Deterministic.
  * **B (R97 routing)** — ``REGENOLD_ANSWER_ROUTER=1``: multi-turn + nuanced
    questions route to Sonnet synthesis; simple QA stays verbatim.

The A/B is methodologically valid because the baseline run has Sonnet OFF
(deterministic) — we never diff two Sonnet runs against each other (which
would be confounded by Sonnet's non-determinism). Each run is scored
independently; the judge grades each row in isolation.

Both runs go through the **in-process TestClient** with the Claude Max
wrapper active (``OPENAI_API_BASE`` + ``P2P_GRAPH_RAG_PROVIDER=openai_wrapper``)
— per the project rule, evals use the wrapper, not the Anthropic SDK direct.

Metrics
-------
* **Coherence rate** (multi-turn) — runner_v2's formula: the final-turn
  answer cites ≥1 expected ref AND surfaces ≥50% of expected keywords AND
  is not a refusal AND has no transport error.
* **Ref Loose / Strict / Keyword recall / Tone / Latency** — per bucket.
* **Judge axes** (``--judge``) — correctness / refs-faithfulness /
  conciseness / tone via ``evals.judge.runner --provider wrapper``.

Usage (wrapper must be up at 127.0.0.1:8000)::

    $env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
    $env:OPENAI_API_KEY  = "dummy"
    .venv\\Scripts\\python.exe -m evals.regenold.multiturn_ab --label r97 --judge

Writes ``evals/bench/results/multiturn-ab-<label>.json`` and prints a delta
table. Reuse each round to re-confirm the routing pays off.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_RESULTS = Path("evals/bench/results")
_PY = sys.executable


def _run_v2(label: str, router_on: bool, *, multiturn_limit: int | None,
            tricky_limit: int | None, timeout: float) -> dict:
    """Run ``runner_v2 --local`` with the wrapper active and the router flag
    set, returning the parsed v2 sidecar."""
    env = dict(os.environ)
    # Production answer surface: verbatim ON. The router decides per-request
    # whether Stage-2 Sonnet synthesis fires under verbatim.
    env["REGENOLD_VERBATIM_ANSWER"] = "1"
    env["REGENOLD_ANSWER_ROUTER"] = "1" if router_on else "0"
    # Ensure the wrapper path is the Stage-2 provider for the TestClient run.
    env.setdefault("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    env.setdefault("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    env.setdefault("OPENAI_API_KEY", "dummy")
    cmd = [
        _PY, "-m", "evals.regenold.runner_v2",
        "--local", "--label", label, "--verbose",
    ]
    if multiturn_limit is not None:
        cmd += ["--multiturn-limit", str(multiturn_limit)]
    if tricky_limit is not None:
        cmd += ["--tricky-limit", str(tricky_limit)]
    print(f"\n[A/B] running v2 (router={'ON' if router_on else 'OFF'}) "
          f"label={label} ...", flush=True)
    subprocess.run(cmd, env=env, check=True, timeout=timeout)
    sidecar = _RESULTS / f"v2-{label}.json"
    return json.loads(sidecar.read_text(encoding="utf-8"))


def _run_judge(v2_label: str, judge_label: str, *, timeout: float) -> dict | None:
    """Grade a v2 sidecar with the LLM-as-judge (wrapper provider)."""
    env = dict(os.environ)
    env.setdefault("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    env.setdefault("OPENAI_API_KEY", "dummy")
    cmd = [
        _PY, "-m", "evals.judge.runner",
        "--bench-sidecar", str(_RESULTS / f"v2-{v2_label}.json"),
        "--label", judge_label, "--provider", "wrapper", "--concurrency", "1",
    ]
    print(f"\n[A/B] judging {v2_label} -> judge-{judge_label} ...", flush=True)
    try:
        subprocess.run(cmd, env=env, check=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"[A/B] judge failed for {v2_label}: {exc}", file=sys.stderr)
        return None
    jpath = _RESULTS / f"judge-{judge_label}.json"
    if not jpath.exists():
        return None
    return json.loads(jpath.read_text(encoding="utf-8"))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _delta_row(label: str, a, b) -> str:
    av, bv = _num(a), _num(b)
    if av is None or bv is None:
        return f"  {label:<26} A={a!s:>8}  B={b!s:>8}  Δ=     -"
    d = bv - av
    arrow = "up" if d > 1e-9 else ("dn" if d < -1e-9 else "==")
    return f"  {label:<26} A={av:>8.4f}  B={bv:>8.4f}  d={d:>+8.4f} {arrow}"


_JUDGE_AXES = ("correctness", "refs", "conciseness", "tone")


def _judge_aggregate(j: dict | None) -> dict:
    """Per-axis NON-ERROR pass rate (passes / (n - judge_errors)).

    Wrapper timeouts surface as judge errors; excluding them gives the
    true judgeable pass rate (the established convention in this repo's
    live judge analyses)."""
    if not j:
        return {}
    agg = j.get("aggregate") or {}
    out = {}
    for axis in _JUDGE_AXES:
        a = agg.get(axis) or {}
        n = a.get("n", 0)
        err = a.get("error", 0)
        passes = a.get("pass", 0)
        non_err = n - err
        out[axis] = round(passes / non_err, 4) if non_err else None
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="R97 multi-turn LLM-routing A/B.")
    p.add_argument("--label", required=True, help="run label, e.g. r97")
    p.add_argument("--multiturn-limit", type=int, default=None,
                   help="cap multi-turn scenarios (default: all 25)")
    p.add_argument("--tricky-limit", type=int, default=None,
                   help="cap tricky single-turn scenarios (default: all 31; "
                        "note 0 is falsy → runs all in runner_v2)")
    p.add_argument("--judge", action="store_true",
                   help="also run the LLM-as-judge on both modes (slow; "
                        "wrapper rate-limited)")
    p.add_argument("--run-timeout", type=float, default=2400.0)
    p.add_argument("--judge-timeout", type=float, default=3600.0)
    args = p.parse_args(argv)

    a_label = f"{args.label}-routerOFF"
    b_label = f"{args.label}-routerON"

    a = _run_v2(a_label, router_on=False, multiturn_limit=args.multiturn_limit,
                tricky_limit=args.tricky_limit, timeout=args.run_timeout)
    b = _run_v2(b_label, router_on=True, multiturn_limit=args.multiturn_limit,
                tricky_limit=args.tricky_limit, timeout=args.run_timeout)

    a_mt, b_mt = a["multiturn"]["summary"], b["multiturn"]["summary"]
    a_tr, b_tr = a["tricky"]["summary"], b["tricky"]["summary"]
    a_coh = a["multiturn"]["coherence_rate"]
    b_coh = b["multiturn"]["coherence_rate"]

    lines = [
        "=" * 78,
        f"R97 MULTI-TURN LLM-ROUTING A/B — label={args.label!r}",
        "  A = router OFF (verbatim-only, R96 baseline, deterministic)",
        "  B = router ON  (multi-turn / nuanced → Sonnet synthesis, R97)",
        "=" * 78,
        "",
        "[MULTI-TURN]",
        _delta_row("coherence_rate", a_coh, b_coh),
        _delta_row("ref_loose", a_mt.get("ref_loose"), b_mt.get("ref_loose")),
        _delta_row("ref_strict", a_mt.get("ref_strict"), b_mt.get("ref_strict")),
        _delta_row("keyword_recall", a_mt.get("keyword_recall"), b_mt.get("keyword_recall")),
        _delta_row("regulatory_tone", a_mt.get("regulatory_tone"), b_mt.get("regulatory_tone")),
        _delta_row("latency_p50_ms", a_mt.get("latency_p50_ms"), b_mt.get("latency_p50_ms")),
        "",
        "[TRICKY single-turn]",
        _delta_row("ref_loose", a_tr.get("ref_loose"), b_tr.get("ref_loose")),
        _delta_row("ref_strict", a_tr.get("ref_strict"), b_tr.get("ref_strict")),
        _delta_row("keyword_recall", a_tr.get("keyword_recall"), b_tr.get("keyword_recall")),
        _delta_row("regulatory_tone", a_tr.get("regulatory_tone"), b_tr.get("regulatory_tone")),
        _delta_row("latency_p50_ms", a_tr.get("latency_p50_ms"), b_tr.get("latency_p50_ms")),
    ]

    judge_a = judge_b = None
    if args.judge:
        judge_a = _run_judge(a_label, f"{args.label}-A", timeout=args.judge_timeout)
        judge_b = _run_judge(b_label, f"{args.label}-B", timeout=args.judge_timeout)
        ja, jb = _judge_aggregate(judge_a), _judge_aggregate(judge_b)
        lines += ["", "[LLM-JUDGE pass-rate (non-error)]"]
        for axis in ("correctness", "refs", "conciseness", "tone"):
            lines.append(_delta_row(axis, ja.get(axis), jb.get(axis)))

    report = "\n".join(lines)
    print("\n" + report)

    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"multiturn-ab-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label,
        "A_routerOFF": {"multiturn": a_mt, "tricky": a_tr, "coherence_rate": a_coh,
                        "judge": _judge_aggregate(judge_a)},
        "B_routerON": {"multiturn": b_mt, "tricky": b_tr, "coherence_rate": b_coh,
                       "judge": _judge_aggregate(judge_b)},
        "report": report,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nsidecar: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
