"""R100 — GraphRAG-paper-benchmark A/B: verbatim vs synthesis-default.

R99.2 measured the verbatim-default answer surface at **0.25** on the LLM-judge
answer-correctness axis (a raw provision quote rarely matches the question's
synthesis-shaped gold). R100 demotes verbatim to explicit-quote-only and routes
simple factual QA to Sonnet synthesis. This harness measures the lift on the
10 GraphRAG-paper ground-truth questions (Appendix B.2):

  * **A (baseline)** — ``REGENOLD_SYNTHESIS_DEFAULT=0``: simple QA → verbatim
    quote (R97 behaviour, deterministic).
  * **B (R100)** — ``REGENOLD_SYNTHESIS_DEFAULT=1``: simple QA → Sonnet synthesis.

The A/B is methodologically valid because the baseline (A) routes the GT
questions to the deterministic verbatim path — we never diff two Sonnet runs.
Both runs go through the in-process TestClient with the Claude Max wrapper
active (per the project eval rule). Each GT row is graded in isolation by the
4-axis LLM-as-judge (correctness / refs / conciseness / tone).

Usage (wrapper must be up at 127.0.0.1:8000)::

    $env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
    $env:OPENAI_API_KEY  = "dummy"
    .venv\\Scripts\\python.exe -m evals.regenold.graphrag_ab --label r100 --judge

Writes ``evals/bench/results/graphrag-ab-<label>.json`` and prints a delta
table.
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
_JUDGE_AXES = ("correctness", "refs", "conciseness", "tone")


def _run_benchmark(label: str, synthesis_default: bool, *, timeout: float) -> dict:
    """Run ``run_graphrag_benchmark --local`` with the wrapper active and the
    synthesis-default flag set; return the parsed sidecar."""
    env = dict(os.environ)
    env["REGENOLD_VERBATIM_ANSWER"] = "1"
    env["REGENOLD_ANSWER_ROUTER"] = "1"
    env["REGENOLD_SYNTHESIS_DEFAULT"] = "1" if synthesis_default else "0"
    env.setdefault("P2P_GRAPH_RAG_PROVIDER", "openai_wrapper")
    env.setdefault("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    env.setdefault("OPENAI_API_KEY", "dummy")
    # Stage-2 must be allowed to fire for the synthesis path under TestClient.
    env["P2P_GRAPH_RAG_ENABLE_STAGE2"] = "1"
    cmd = [
        _PY, "-m", "evals.regenold.run_graphrag_benchmark",
        "--local", "--label", label,
    ]
    print(f"\n[A/B] benchmark (synthesis_default={'ON' if synthesis_default else 'OFF'}) "
          f"label={label} ...", flush=True)
    subprocess.run(cmd, env=env, check=True, timeout=timeout)
    return json.loads((_RESULTS / f"graphrag-bench-{label}.json").read_text(encoding="utf-8"))


def _write_judge_input(bench: dict, label: str) -> Path:
    """Adapt the GraphRAG sidecar's ground-truth rows into a judge-readable
    ``{"rows": [...]}`` sidecar (the judge reads the top-level ``rows`` bucket)."""
    rows = list(bench.get("ground_truth", {}).get("rows") or [])
    path = _RESULTS / f"graphrag-judge-input-{label}.json"
    path.write_text(json.dumps({"rows": rows}, indent=2, default=str), encoding="utf-8")
    return path


def _run_judge(judge_input: Path, judge_label: str, *, timeout: float) -> dict | None:
    env = dict(os.environ)
    env.setdefault("OPENAI_API_BASE", "http://127.0.0.1:8000/v1")
    env.setdefault("OPENAI_API_KEY", "dummy")
    cmd = [
        _PY, "-m", "evals.judge.runner",
        "--bench-sidecar", str(judge_input),
        "--label", judge_label, "--provider", "wrapper", "--concurrency", "1",
    ]
    print(f"\n[A/B] judging {judge_input.name} -> judge-{judge_label} ...", flush=True)
    try:
        subprocess.run(cmd, env=env, check=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"[A/B] judge failed: {exc}", file=sys.stderr)
        return None
    jpath = _RESULTS / f"judge-{judge_label}.json"
    return json.loads(jpath.read_text(encoding="utf-8")) if jpath.exists() else None


def _judge_aggregate(j: dict | None) -> dict:
    """Per-axis NON-ERROR pass rate (passes / (n - errors)) — the repo
    convention for live judge runs (wrapper timeouts excluded)."""
    if not j:
        return {}
    agg = j.get("aggregate") or {}
    out = {}
    for axis in _JUDGE_AXES:
        a = agg.get(axis) or {}
        n, err, passes = a.get("n", 0), a.get("error", 0), a.get("pass", 0)
        non_err = n - err
        out[axis] = round(passes / non_err, 4) if non_err else None
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _delta_row(label: str, a, b) -> str:
    av, bv = _num(a), _num(b)
    if av is None or bv is None:
        return f"  {label:<22} A={a!s:>9}  B={b!s:>9}  d=     -"
    d = bv - av
    arrow = "up" if d > 1e-9 else ("dn" if d < -1e-9 else "==")
    return f"  {label:<22} A={av:>9.4f}  B={bv:>9.4f}  d={d:>+8.4f} {arrow}"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    p = argparse.ArgumentParser(description="R100 GraphRAG-benchmark verbatim-vs-synthesis A/B.")
    p.add_argument("--label", required=True)
    p.add_argument("--judge", action="store_true", help="also run the 4-axis LLM-as-judge")
    p.add_argument("--run-timeout", type=float, default=2400.0)
    p.add_argument("--judge-timeout", type=float, default=3600.0)
    args = p.parse_args(argv)

    a_label, b_label = f"{args.label}-synthOFF", f"{args.label}-synthON"
    a = _run_benchmark(a_label, synthesis_default=False, timeout=args.run_timeout)
    b = _run_benchmark(b_label, synthesis_default=True, timeout=args.run_timeout)
    ag, bg = a["ground_truth"]["summary"], b["ground_truth"]["summary"]

    lines = [
        "=" * 78,
        f"R100 GRAPHRAG-BENCHMARK A/B — label={args.label!r}",
        "  A = synthesis_default OFF (simple QA → verbatim quote, R97)",
        "  B = synthesis_default ON  (simple QA → Sonnet synthesis, R100)",
        "=" * 78,
        "",
        "[GROUND-TRUTH deterministic metrics]",
        _delta_row("ref_loose", ag.get("ref_loose"), bg.get("ref_loose")),
        _delta_row("ref_strict", ag.get("ref_strict"), bg.get("ref_strict")),
        _delta_row("ref_conciseness", ag.get("ref_conciseness"), bg.get("ref_conciseness")),
        _delta_row("keyword_recall", ag.get("keyword_recall"), bg.get("keyword_recall")),
        _delta_row("regulatory_tone", ag.get("regulatory_tone"), bg.get("regulatory_tone")),
        _delta_row("refusal_rate", ag.get("refusal_rate"), bg.get("refusal_rate")),
        _delta_row("latency_p50_ms", ag["latency"]["p50"], bg["latency"]["p50"]),
    ]

    ja = jb = None
    if args.judge:
        ja_in = _write_judge_input(a, a_label)
        jb_in = _write_judge_input(b, b_label)
        ja = _judge_aggregate(_run_judge(ja_in, a_label, timeout=args.judge_timeout))
        jb = _judge_aggregate(_run_judge(jb_in, b_label, timeout=args.judge_timeout))
        lines += ["", "[LLM-JUDGE pass-rate (non-error), GT rows]"]
        for axis in _JUDGE_AXES:
            lines.append(_delta_row(axis, ja.get(axis), jb.get(axis)))

    report = "\n".join(lines)
    print("\n" + report)
    _RESULTS.mkdir(parents=True, exist_ok=True)
    out = _RESULTS / f"graphrag-ab-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label,
        "A_synthOFF": {"gt_summary": ag, "judge": ja},
        "B_synthON": {"gt_summary": bg, "judge": jb},
        "report": report,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nsidecar: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
