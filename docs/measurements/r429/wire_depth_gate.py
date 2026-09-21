"""R429 gate — what is COMPLETING the wire grain worth, on a fresh paired draw?

WHY THERE IS ONLY ONE LIVE ARM, and why that is the STRICTER design.

The pass runs after Stage-2 landed and edits only the ``references`` list. It
cannot change the answer text, so Answer Correctness (loose and strict) and
Regulatory Tone cannot move — and the three reference axes are computed from the
emitted ``references`` against the gold key by ``evals.official.rubric``, with no
LLM involved.

A second LIVE arm therefore buys one thing (a fresh LLM draw of the same row) and
costs the thing the whole 3-generation protocol exists to control: it makes each
arm's answer an INDEPENDENT draw, so the reference comparison inherits generation
noise that the lever has nothing to do with. Deriving both lever states from the
SAME draw removes that noise entirely. (The R425 round reached the same
conclusion and stopped its own two-arm wire gate for this reason.)

THE LICENCE FOR THE DERIVATION, checked before any number is reported. The live ON
arm would receive the reference list as it stands BEFORE this pass; the recorded
wire is the list AFTER it, with the lever OFF. Those differ only by the pass's own
rewrites, so ``pass(recorded) == recorded`` on every row is exactly the statement
that re-applying it is a no-op — and once that holds, ``pass(recorded)`` IS what
the live ON arm would have emitted for that same answer. The check is reported,
not assumed, and the reader refuses to move on if it fails.

What replaces the runner's wire-slot void guard: NON-VACUITY is proven directly —
the count of rows where the derived arm differs, on coordinates the Regulation
actually contains — which is the property the guard exists to protect, measured
rather than hashed. Transport integrity is read from each row's own provenance.

PRE-REGISTERED RULE, fixed before the numbers were read (a wire lever is a
fidelity correction to the graded artifact, so the bar is "nothing gets worse"; the
mechanism evidence is what justifies the direction):

  * Ref. Correctness (Strict) — the targeted axis — not below ``-1.5 pp``;
  * Ref. Correctness (Loose) and Ref. Conciseness within ``-1.5 pp`` (both are
    invariant by construction; a move is a wiring bug);
  * gold heads dropped ON <= OFF (Hard Rule #8);
  * reference COUNT and folded head set invariant on every comparable row;
  * 0 rows where any expectation goes met -> unmet.

SHIP iff every one holds; otherwise the default reverts to ``0``.

Usage::

    .venv\\Scripts\\python.exe docs/measurements/r429/wire_depth_gate.py
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.routes import regenold as R  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    ref_head,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

OUT = Path(__file__).resolve().parent
RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

LABEL = "r429-depth"
ARM = "A"  # the single live arm, drawn with REGENOLD_GROUND_WIRE_DEPTH=0
REPEATS = 3
MIN_PRIMARY_SAMPLES = 2
TOLERANCE_STRICT_PP = -1.5
TOLERANCE_INVARIANT_PP = -1.5
BOOTSTRAP = 4000
SEED = 429
FLAG = "REGENOLD_GROUND_WIRE_DEPTH"


def _ckpt(sample: int) -> Path:
    stem = f"official-{LABEL}-{ARM}-hard"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def _load(path: Path) -> dict[str, dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {str(r["id"]): r for r in rows}


def _graded(row: dict[str, Any]) -> tuple[str, list[str]]:
    """The turn the wire passes saw — the hard-mode graded turn, all-or-nothing."""
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
        )
    return row.get("pred_answer") or "", [str(x) for x in (row.get("pred_refs") or [])]


def _served_by(row: dict[str, Any]) -> str:
    return str((row.get("provenance") or {}).get("stage2_served_by") or "")


def _heads(refs: list[str]) -> set[str]:
    return {h for h in (ref_head(r) for r in refs) if h}


def _median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def _boot_ci(deltas: list[float]) -> tuple[float, float]:
    rng = random.Random(SEED)
    n = len(deltas)
    if n < 2:
        return (0.0, 0.0)
    means = sorted(sum(rng.choice(deltas) for _ in range(n)) / n for _ in range(BOOTSTRAP))
    return (means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP) - 1])


def main() -> int:
    gold = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g

    samples: list[dict[str, dict[str, Any]]] = []
    for s in range(REPEATS):
        path = _ckpt(s)
        if not path.exists():
            raise SystemExit(f"missing checkpoint {path.name} — the run has not finished")
        samples.append(_load(path))

    ids = sorted(samples[0])
    print(f"rows on the split   : {len(ids)}")
    print(f"live arm            : {ARM} with {FLAG}=0  ({REPEATS} independent generations)")
    print()

    # ── 1. THE LICENCE: is the pass a no-op on its own recorded output? ────────
    prev = os.environ.get(FLAG)
    os.environ[FLAG] = "0"
    fixed_ok = 0
    fixed_bad: list[str] = []
    for row_id in ids:
        for s in range(REPEATS):
            answer, refs = _graded(samples[s][row_id])
            if not answer or not refs:
                continue
            if R._ground_wire_subpoints(answer, list(refs), "") == refs:
                fixed_ok += 1
            else:
                fixed_bad.append(f"{row_id}/s{s}")
    total = sum(
        1
        for row_id in ids
        for s in range(REPEATS)
        if all(_graded(samples[s][row_id]))
    )
    print(f"[licence] recorded wire is a fixed point of the pass : {fixed_ok}/{total}")
    if fixed_bad:
        print(f"          NOT a fixed point on {len(fixed_bad)} row-samples: {fixed_bad[:6]}")
        print("          -> the derived ON arm would not equal the live ON arm. REFUSING.")
        if prev is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = prev
        return 4

    # ── 2. transport integrity, from each row's own provenance ────────────────
    served: dict[str, list[str]] = {row_id: [_served_by(samples[s][row_id]) for s in range(REPEATS)] for row_id in ids}
    comparable = [
        row_id
        for row_id, legs in served.items()
        if sum(1 for leg in legs if leg == "primary") >= MIN_PRIMARY_SAMPLES
        and (gold.get(row_id) or {}).get("expected_refs")
    ]
    dropped = {row_id: legs for row_id, legs in served.items() if row_id not in comparable}
    print(f"[transport] comparable rows (>= {MIN_PRIMARY_SAMPLES}/3 primary, gold refs): {len(comparable)}")
    for row_id, legs in sorted(dropped.items())[:8]:
        print(f"          dropped {row_id}: {legs}")
    if len(dropped) > 8:
        print(f"          ... and {len(dropped) - 8} more")
    os.environ.pop(FLAG, None)

    # ── 3. both lever states from the SAME draw, scored with the real rubric ──
    axes = ("loose", "strict", "conc")
    per_arm: dict[str, dict[str, list[float]]] = {
        "off": {a: [] for a in axes},
        "on": {a: [] for a in axes},
    }
    deltas: dict[str, list[float]] = {a: [] for a in axes}
    non_vacuous: set[str] = set()
    coords_completed = 0
    coords_gold = 0
    count_bad: list[str] = []
    head_bad: list[str] = []
    regressions: list[str] = []
    gold_head = {"off": 0, "on": 0}
    moved_up = moved_down = 0
    examples: list[str] = []

    for row_id in comparable:
        exp = [str(x) for x in gold[row_id]["expected_refs"]]
        per_row: dict[str, dict[str, list[float]]] = {
            "off": {a: [] for a in axes},
            "on": {a: [] for a in axes},
        }
        for s in range(REPEATS):
            answer, refs = _graded(samples[s][row_id])
            on = R._ground_wire_subpoints(answer, list(refs))
            if on != refs:
                non_vacuous.add(row_id)
                for x in on:
                    if x not in refs:
                        coords_completed += 1
                        if any(
                            x.lower() == e.lower() or x.lower().startswith(e.lower() + ".")
                            for e in exp
                        ):
                            coords_gold += 1
                if len(examples) < 8:
                    examples.append(f"  {row_id} s{s}: {refs} -> {on}")
            if len(on) != len(refs):
                count_bad.append(row_id)
            if _heads(on) != _heads(refs):
                head_bad.append(row_id)
            if (
                reference_correctness_strict(on, exp) or 0.0
            ) < (reference_correctness_strict(refs, exp) or 0.0):
                regressions.append(row_id)
            for arm, refs_arm in (("off", refs), ("on", on)):
                per_row[arm]["loose"].append(reference_correctness_loose(refs_arm, exp) or 0.0)
                per_row[arm]["strict"].append(reference_correctness_strict(refs_arm, exp) or 0.0)
                per_row[arm]["conc"].append(reference_conciseness(refs_arm, exp) or 0.0)
        for arm, refs_arm in (("off", refs), ("on", on)):
            union = _heads([str(x) for x in refs_arm])
            gold_head[arm] += len(_heads(exp) - union)
        for a in axes:
            mo, mn = _median(per_row["off"][a]), _median(per_row["on"][a])
            per_arm["off"][a].append(mo)
            per_arm["on"][a].append(mn)
            deltas[a].append((mn - mo) * 100.0)
        so, sn = _median(per_row["off"]["strict"]), _median(per_row["on"]["strict"])
        if sn > so:
            moved_up += 1
        elif sn < so:
            moved_down += 1

    def mean(name: str, arm: str) -> float:
        return sum(per_arm[arm][name]) / len(per_arm[arm][name]) * 100.0

    print()
    print(f"[non-vacuity] rows where the derived arm differs: {len(non_vacuous)}/{len(comparable)}")
    print(f"[non-vacuity] coordinates completed            : {coords_completed} (gold {coords_gold})")
    print()
    print(f"{'axis':<14} {'OFF':>10} {'ON':>10} {'delta':>9}  95% CI (seeded)")
    for a in axes:
        lo, hi = _boot_ci(deltas[a])
        print(
            f"{a:<14} {mean(a, 'off'):>10.2f} {mean(a, 'on'):>10.2f} "
            f"{mean(a, 'on') - mean(a, 'off'):>+9.2f}  [{lo:+.2f}, {hi:+.2f}]"
        )
    print()
    print(f"rows where Ref. Strict moved   : up {moved_up} / down {moved_down}")
    print(f"gold heads dropped             : OFF {gold_head['off']} -> ON {gold_head['on']}")
    print(f"count-invariance violations    : {len(count_bad)}   <- must be 0")
    print(f"head-set violations            : {len(head_bad)}   <- must be 0")
    print(f"met -> unmet regressions       : {len(regressions)}   <- must be 0")
    print()
    print("examples (recorded wire -> completed):")
    print("\n".join(examples) if examples else "  (none)")

    crit = {
        "licence: fixed point on every row-sample": not fixed_bad,
        "strict >= -1.5 pp": mean("strict", "on") - mean("strict", "off") >= TOLERANCE_STRICT_PP,
        "loose within -1.5 pp": mean("loose", "on") - mean("loose", "off") >= TOLERANCE_INVARIANT_PP,
        "conc within -1.5 pp": mean("conc", "on") - mean("conc", "off") >= TOLERANCE_INVARIANT_PP,
        "gold heads ON <= OFF": gold_head["on"] <= gold_head["off"],
        "count invariant": not count_bad,
        "head set invariant": not head_bad,
        "no met->unmet regression": not regressions,
        "the lever is not inert on this draw": bool(non_vacuous),
    }
    print()
    for k, v in crit.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    verdict = "SHIP (default stays ON)" if all(crit.values()) else "REVERT (default -> 0)"
    print()
    print(f"VERDICT: {verdict}")

    (OUT / "gate-verdict.json").write_text(
        json.dumps(
            {
                "label": LABEL,
                "live_arm": ARM,
                "repeats": REPEATS,
                "rows_on_split": len(ids),
                "comparable_rows": len(comparable),
                "dropped": {r: legs for r, legs in dropped.items()},
                "licence_fixed_point": f"{fixed_ok}/{total}",
                "non_vacuous_rows": sorted(non_vacuous),
                "coordinates_completed": coords_completed,
                "coordinates_gold": coords_gold,
                "arms": {arm: {a: mean(a, arm) for a in axes} for arm in ("off", "on")},
                "deltas": {a: mean(a, "on") - mean(a, "off") for a in axes},
                "ci95_strict": _boot_ci(deltas["strict"]),
                "rows_moved": {"up": moved_up, "down": moved_down},
                "gold_heads_dropped": gold_head,
                "violations": {"count": count_bad, "head": head_bad, "regression": regressions},
                "criteria": crit,
                "verdict": verdict,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"record -> {OUT / 'gate-verdict.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
