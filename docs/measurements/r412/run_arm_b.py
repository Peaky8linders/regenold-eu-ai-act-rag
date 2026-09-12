"""R412 — run ONLY the branch arm of a paired gate (quota-efficient pairing).

WHY THIS EXISTS
---------------
`evals.harness.easyhard_ab` always runs arm A and then arm B, so re-gating a
lever re-pays for the baseline even when the baseline rows are already measured.
Every Stage-2 call costs Claude-Max quota, and both arms hairpin to the SAME
local Claude Max, so the calls are the scarce resource.

When arm A has already answered the first N easy rows (and its log proves it was
wrapper-served, not Bedrock-served), the only calls still needed are arm B's N.
This runner drives the harness's OWN `_run_arm` so env handling, checkpointing,
scoring and row shape are byte-identical to the full harness — it simply skips
the arm it does not need.

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe \
        docs/measurements/r412/run_arm_b.py \
        --label r411-fullsys-singleturn-easy --limit 39 \
        --branch-env REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evals.harness.easyhard_ab import (  # noqa: E402
    _RESULTS,
    _parse_env,
    _run_arm,
    _score_row,  # noqa: F401  (kept: documents that scoring stays the harness's)
)
from evals.harness.probe_set import load_probe_set  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--limit", type=int, required=True)
    ap.add_argument("--branch-env", action="append", default=[])
    ap.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    # Read the transport counters fresh so a liveness read is about THIS run.
    try:
        from app.llm.stage2_policy import reset_transport_stats

        reset_transport_stats()
    except Exception:  # noqa: BLE001
        pass

    branch_env = _parse_env(args.branch_env)
    probe = load_probe_set(multiturn=False, limit=args.limit)
    print(f"arm B only: {len(probe)} easy rows, env={branch_env}")

    _RESULTS.mkdir(parents=True, exist_ok=True)
    b_rows = _run_arm(
        probe,
        endpoint=None,
        api_key=None,
        local=True,
        timeout=args.timeout,
        arm_env=branch_env,
        ckpt_path=_RESULTS / f"easyhard-{args.label}-B.ckpt.jsonl",
    )
    print(f"\narm B rows written: {len(b_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
