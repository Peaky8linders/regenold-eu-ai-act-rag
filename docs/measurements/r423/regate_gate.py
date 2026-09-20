"""R423.2 — re-derive a paired gate's verdict from the draws already on disk.

WHY THIS EXISTS. ``run_official_batch`` judges its own run with
``gate_validity.assess`` and persists that verdict inside
``evals/bench/results/official-<label>.json``. When the GUARD changes, the saved
verdict is stale — but the DRAWS are not. Every answer of the R423 need4 gate is
in its six checkpoints, and the transport counters are in the payload. This
script re-runs the guard over exactly that evidence, so a guard fix does not have
to be paid for with another five hours of live quota on identical rows.

WHAT CHANGED. ``assess`` used to void a whole paired run when a single row's
primary call failed and its Stage-2 fell through to a Stage-1 draft — even though
its own warning says such rows "belong in the excluded set, not averaged over",
and the gate's comparability filter had already dropped that row symmetrically.
It now accepts ``excluded_rows``: a count the caller must ACCOUNT for (each
excluded row absorbs at most one off-contract refusal; the set must stay a
minority of the arm). Measured on need4: one row (``rg_085``) on arm A, against
27 paired rows and five hours of live draws that the void discarded.

WHAT THIS CANNOT DO. It cannot invent or edit a draw, cannot change a counter,
and cannot improve a delta — it re-runs the SAME rules over the SAME evidence.
The original verdict is preserved under ``as_run`` and the excluded ids are
recorded, so the re-derivation is auditable after the fact.

Usage::

    .venv\\Scripts\\python.exe docs/measurements/r423/regate_gate.py \\
        --label r423-need4 --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.harness.gate_validity import ArmProvenance, assess, degraded_row_ids

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "evals" / "bench" / "results"

#: What the re-derivation is allowed to claim about itself.
REGATE_NOTE = (
    "re-derived by docs/measurements/r423/regate_gate.py: gate_validity.assess "
    "now accepts the transport-degraded rows the caller excluded from BOTH arms "
    "instead of voiding the whole paired run for them. Same draws, same counters, "
    "same rules otherwise."
)


def _ckpt(label: str, arm: str, mode: str, sample: int) -> Path:
    stem = f"official-{label}-{arm}-{mode}"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def regate(label: str, *, write: bool = False, arms: str = "A,B") -> int:
    payload_path = RESULTS / f"official-{label}.json"
    if not payload_path.exists():
        raise SystemExit(f"no payload at {payload_path}")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    suffixes = [s.strip() for s in arms.split(",") if s.strip()]
    if len(suffixes) != 2:
        raise SystemExit("--arms wants exactly two suffixes, OFF first (e.g. A,B)")
    repeats = int(payload.get("repeats", 1) or 1)
    lever_block = payload.get("lever_changes_system") or {}
    lever = (bool(lever_block.get("changes")), str(lever_block.get("why") or "unknown"))
    print(f"label={label}  repeats={repeats}  lever_changes_system={lever}")

    changed = 0
    payload["gate"] = payload.get("gate") or {}
    for mode, block in payload["gate"].items():
        if not isinstance(block, dict):
            continue
        base_label, branch_label = f"{label}-{suffixes[0]}", f"{label}-{suffixes[1]}"
        arm_dicts = block.get("arms") or {}
        if base_label not in arm_dicts or branch_label not in arm_dicts:
            print(f"  [{mode}] no arm payloads for {base_label}/{branch_label}; skipped")
            continue
        excluded: list[str] = []
        missing: list[str] = []
        for suffix in suffixes:
            for sample in range(repeats):
                path = _ckpt(label, suffix, mode, sample)
                if not path.exists():
                    missing.append(path.name)
                    continue
                excluded.extend(degraded_row_ids(_rows(path)))
        excluded = sorted(set(excluded))
        base = ArmProvenance.from_dict(arm_dicts[base_label])
        branch = ArmProvenance.from_dict(arm_dicts[branch_label])
        verdict = assess(
            base=base,
            branch=branch,
            lever=lever,
            excluded_rows=len(excluded),
        )
        before = bool(block.get("valid"))
        block.setdefault(
            "as_run",
            {
                "valid": block.get("valid"),
                "reasons": list(block.get("reasons") or []),
                "warnings": list(block.get("warnings") or []),
            },
        )
        block.update(verdict.as_dict())
        block["excluded_rows"] = excluded
        block["degraded_rows_missing_from_disk"] = missing
        block["regate"] = {"excluded_n": len(excluded), "note": REGATE_NOTE}
        changed += 1
        print(f"\n  [{mode}] valid {before} -> {verdict.valid}")
        print(f"    excluded (both arms): n={len(excluded)} {excluded}")
        if missing:
            print(f"    !! checkpoints missing, degraded set may be incomplete: {missing}")
        for reason in verdict.reasons:
            print(f"    VOID: {reason}")
        for warning in verdict.warnings:
            print(f"    (context) {warning}")

    if write and changed:
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"\nwrote {payload_path}")
    elif changed:
        print("\n(dry run; pass --write to persist)")
    return changed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="r423-need4")
    ap.add_argument("--arms", default="A,B", help="arm suffixes, lever-OFF first")
    ap.add_argument("--write", action="store_true", help="rewrite the payload's gate block")
    a = ap.parse_args()
    regate(a.label, write=a.write, arms=a.arms)


if __name__ == "__main__":
    main()
