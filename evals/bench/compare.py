"""Side-by-side comparison of two benchmark runs.

CLI:
    py -3.12 -m evals.bench.compare baseline post_optimisation
    py -3.12 -m evals.bench.compare baseline post_optimisation --json

Reads JSON sidecars from ``evals/bench/results/<label>.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


_AXES = (
    ("ans_correctness_loose", "Ans Correctness (Loose)"),
    ("ans_correctness_strict", "Ans Correctness (Strict)"),
    ("ans_conciseness", "Ans Conciseness"),
    ("ref_correctness_loose", "Ref Correctness (Loose)"),
    ("ref_correctness_strict", "Ref Correctness (Strict)"),
    ("ref_conciseness", "Ref Conciseness"),
    ("regulatory_tone", "Regulatory Tone"),
    ("latency_p50_ms", "Latency p50 (ms)"),
    ("latency_p95_ms", "Latency p95 (ms)"),
)


def _load(label: str) -> dict:
    path = RESULTS_DIR / f"{label}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No benchmark sidecar at {path}. Run "
            f"`py -3.12 -m evals.bench.runner --label {label}` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_text(a: dict, b: dict, *, label_a: str, label_b: str) -> str:
    """Render a side-by-side text table."""
    lines: list[str] = []
    lines.append("=" * 92)
    lines.append(
        f"Comparison: {label_a!r}  →  {label_b!r}"
    )
    lines.append("=" * 92)
    summary_a = a.get("summary") or a.get("scores") or {}
    summary_b = b.get("summary") or b.get("scores") or {}
    for source in ("qa", "scenarios", "overall"):
        sa = summary_a.get(source, {})
        sb = summary_b.get(source, {})
        if not sa or not sb:
            continue
        lines.append("")
        lines.append(
            f"[{source.upper()}] n={sb.get('n','?')}"
        )
        for key, label in _AXES:
            va = sa.get(key)
            vb = sb.get(key)
            if va is None and vb is None:
                continue
            if va is None or vb is None:
                lines.append(f"  {label:<26}  {va!r} → {vb!r}")
                continue
            delta = vb - va
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
            # For latency, lower is better, so flip the arrow semantics.
            if "Latency" in label:
                better = delta < 0
            else:
                better = delta > 0
            marker = "✓" if better else (" " if delta == 0 else "✗")
            lines.append(
                f"  {label:<26}  {va:>8}  →  {vb:>8}   {arrow} {delta:+.4f} {marker}"
            )
    # Multi-turn coherence
    ma = summary_a.get("multiturn_coherence") or {}
    mb = summary_b.get("multiturn_coherence") or {}
    if ma or mb:
        lines.append("")
        lines.append(
            f"[MULTI-TURN] coherence_rate:  "
            f"{ma.get('coherence_rate','?')}  →  {mb.get('coherence_rate','?')}"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label_a")
    parser.add_argument("label_b")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON delta dict instead of the text table.",
    )
    args = parser.parse_args(argv)
    a = _load(args.label_a)
    b = _load(args.label_b)
    if args.json:
        out: dict[str, dict[str, float]] = {}
        summary_a = a.get("summary") or a.get("scores") or {}
        summary_b = b.get("summary") or b.get("scores") or {}
        for source in ("qa", "scenarios", "overall"):
            sa = summary_a.get(source, {})
            sb = summary_b.get(source, {})
            section: dict[str, float] = {}
            for key, _ in _AXES:
                va = sa.get(key)
                vb = sb.get(key)
                if va is None or vb is None:
                    continue
                section[f"{key}_delta"] = round(vb - va, 4)
                section[f"{key}_before"] = va
                section[f"{key}_after"] = vb
            if section:
                out[source] = section
        print(json.dumps(out, indent=2))
    else:
        print(_emit_text(a, b, label_a=args.label_a, label_b=args.label_b))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
