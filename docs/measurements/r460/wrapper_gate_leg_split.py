"""R460 wrapper confirmation -- the transport split behind the A/B.

Arm B (calibration ON) hit the wrapper's degenerate-completion path ~3x as
often as arm A, so a share of its rows were served by the NATIVE BEDROCK LEG
(``eu.anthropic.claude-opus-4-6-v1``) instead of Opus 5.5 over the tunnel. That
is a confound on a transport confirmation, and it has to be quantified rather
than mentioned: this script reports the per-leg row counts and the answer-side
aggregates for each arm, plus the subsets needed to re-read the gate.

Run:  ../../.venv/Scripts/python.exe docs/measurements/r460/wrapper_gate_leg_split.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "evals" / "bench" / "results"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ARMS = {"off": "r460-tunnel-off-s3", "on": "r460-tunnel-on-s3"}


def load(label: str) -> list[dict]:
    path = RESULTS / f"official-{label}-hard.ckpt.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def s(row: dict) -> str:
    return str((row.get("provenance") or {}).get("stage2_served_by") or "?")


def main() -> int:
    arms = {k: load(v) for k, v in ARMS.items()}
    legs = {k: Counter(s(r) for r in rows) for k, rows in arms.items()}
    print("served_by per arm:")
    for k, c in legs.items():
        print(f"  {k}: {dict(c)}")

    for k, rows in arms.items():
        primary = [r for r in rows if s(r) == "primary"]
        fallback = [r for r in rows if s(r) == "fallback"]
        for name, sub in (("ALL", rows), ("primary-only", primary), ("fallback-only", fallback)):
            if not sub:
                continue
            print(
                f"  {k:>3} {name:<14} n={len(sub):<3} "
                f"ans_chars={mean([len(r.get('pred_answer') or '') for r in sub]):7.1f} "
                f"refs={mean([len(r.get('pred_refs') or []) for r in sub]):5.2f} "
                f"tone1_chars={mean([len(r.get('turn1_answer') or '') for r in sub]):7.1f} "
                f"p50_ms={sorted([r.get('pushback_latency_ms') or 0 for r in sub])[len(sub) // 2]:8.0f}"
            )

    # Same-leg subset: rows where BOTH arms were polished on the wrapper.
    shared_primary = sorted(
        {r["id"] for r in arms["off"] if s(r) == "primary"}
        & {r["id"] for r in arms["on"] if s(r) == "primary"}
    )
    print(f"\nboth-primary rows: n={len(shared_primary)}")
    for k, rows in arms.items():
        sub = [r for r in rows if r["id"] in set(shared_primary)]
        print(
            f"  {k:>3} ans_chars={mean([len(r.get('pred_answer') or '') for r in sub]):7.1f} "
            f"refs={mean([len(r.get('pred_refs') or []) for r in sub]):5.2f}"
        )
    on_fallback_off_primary = sorted(
        {r["id"] for r in arms["on"] if s(r) == "fallback"}
        - {r["id"] for r in arms["off"] if s(r) == "fallback"}
    )
    print(f"\nrows fallback in B but primary in A: n={len(on_fallback_off_primary)} "
          f"{on_fallback_off_primary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
