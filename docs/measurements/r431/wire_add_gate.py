"""R431 gate — what is ADDING the engaged-but-missing limb worth, on a fresh draw?

WHY THERE IS ONLY ONE LIVE ARM. ``_ground_wire_subpoints`` runs after Stage-2 has
landed and edits only the ``references`` list. It cannot change the answer text, so
Answer Correctness (loose and strict) and Regulatory Tone cannot move at all, and
the three reference axes are computed from the emitted ``references`` against the
gold key by ``evals.official.rubric`` with no LLM involved. A second live arm would
therefore buy only a fresh LLM draw of the same row while making each arm's answer
an INDEPENDENT draw — importing generation noise the lever cannot be responsible
for. Deriving both lever states from the SAME draw removes that noise exactly; the
R425 and R429 rounds both reached this conclusion independently.

THE LICENCE, checked before any number is reported. The live run is drawn with
``REGENOLD_GROUND_WIRE_ADD=0``, so the recorded wire IS the OFF arm. Re-running the
pass with the flag off must be a no-op on that wire on every row-sample; when it is,
the ON arm for the SAME answer is precisely ``pass(recorded, ADD=1)``. The reader
refuses to continue if any row-sample fails that test.

WHAT THE ADD IS ALLOWED TO CHANGE, asserted per row-sample rather than argued:

* Ref. Correctness (Loose) reads ``set(_heads(pred))``, so the folded head SET is
  the invariant — not the multiset, which necessarily grows by one whenever a
  second reference lands under a head already present.
* Ref. Correctness (Strict) is recall at full grain, and the ADD only ever appends
  a coordinate whose parent is already on the wire, so it is monotone
  non-decreasing: asserted on every row-sample.
* Ref. Conciseness is ``min(1, |expected| / |provided|)`` — a pure COUNT ratio, and
  the one axis this can lose. Its tolerance is therefore larger and explicit.

GENERATIONS, and a transport outage that shortened the draw. The design is three
independent generations. The primary leg (`claude-code` upstream) began returning
HTTP 500 on every call part-way through generation 3 and the harness's own health
guard aborted the sample at 12/37 rather than let the rest be graded on deterministic
Stage-1 drafts. The reader therefore uses only the COMPLETE generations and states
how many it used; it refuses to mix a partial generation in. The pre-registered
tolerance criteria are unchanged, and the number of generations actually used is
recorded in the verdict so a later re-run to three cannot be mistaken for the same
measurement.

PRE-REGISTERED RULE, fixed before the numbers were read:

  * the lever is NOT inert on the draw;
  * Ref. Correctness (Strict) not below ``-1.5 pp`` (the targeted axis);
  * Ref. Correctness (Loose) within ``-1.5 pp`` (invariant by construction);
  * Ref. Conciseness within ``-2.5 pp`` (the tariff it is allowed to pay);
  * folded head set invariant on every row-sample;
  * the appended count per row-sample within ``[0, cap]``;
  * 0 row-samples where an expected reference goes met -> unmet;
  * gold heads dropped ON <= OFF (Hard Rule #8).

SHIP iff every one holds; otherwise the default reverts to ``0``.

Usage::

    .venv\\Scripts\\python.exe docs/measurements/r431/wire_add_gate.py
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

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

LABEL = "r431-add"
ARM = "A"
REPEATS = 3
MIN_PRIMARY_SAMPLES = 2
TOLERANCE_STRICT_PP = -1.5
TOLERANCE_LOOSE_PP = -1.5
TOLERANCE_CONC_PP = -2.5
BOOTSTRAP = 4000
SEED = 431
FLAG = "REGENOLD_GROUND_WIRE_ADD"
AXES = ("loose", "strict", "conc")


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


def _graded(row: dict[str, Any]) -> tuple[str, list[str], str]:
    """The turn the wire passes saw — the hard-mode graded turn, all-or-nothing.

    The QUESTION comes back with it, and that is not a convenience. The route calls
    ``_ground_wire_subpoints(answer, references, question)``, and R431's ADD arm reads
    the question as its second vote: a limb is appended only when BOTH the answer and
    the question discuss that limb's own statutory text above the floors. Driving the
    pass with an empty question — which the first version of this reader did — leaves
    ``q_recall`` at zero for every candidate and measures the lever as inert when it is
    not. The offline tariff table would have caught it; the gate on its own could not,
    which is exactly why the non-vacuity criterion exists.
    """
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
            str(row.get("question") or ""),
        )
    return (
        row.get("pred_answer") or "",
        [str(x) for x in (row.get("pred_refs") or [])],
        str(row.get("question") or ""),
    )


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
    means = sorted(
        sum(rng.choice(deltas) for _ in range(n)) / n for _ in range(BOOTSTRAP)
    )
    return (means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP) - 1])


def main() -> int:
    gold: dict[str, Any] = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g

    # Only COMPLETE generations are usable: a generation the transport guard aborted
    # part-way through carries no rows for the tail of the split, and folding it in
    # would silently shrink the row set instead of reporting the shorter draw.
    loaded: list[tuple[int, dict[str, dict[str, Any]]]] = []
    for s in range(REPEATS):
        path = _ckpt(s)
        if not path.exists():
            print(f"[generations] {path.name}: missing")
            continue
        rows = _load(path)
        loaded.append((s, rows))
        print(f"[generations] {path.name}: {len(rows)} rows")
    if not loaded:
        raise SystemExit("no checkpoints found — the run has not started")
    full = max(len(rows) for _, rows in loaded)
    samples = [rows for _, rows in loaded if len(rows) == full]
    if len(samples) < REPEATS:
        print(
            f"[generations] USING {len(samples)} of the pre-registered {REPEATS} "
            f"generations ({full} rows each); the others are incomplete and excluded."
        )
    if len(samples) < 2:
        raise SystemExit("fewer than 2 complete generations — nothing to pair")

    ids = sorted(samples[0])
    used = len(samples)
    cap = R._ground_wire_add_params()[2]
    print(f"rows on the split   : {len(ids)}")
    print(f"live arm            : {ARM} with {FLAG}=0  ({used} independent generations)")
    print(f"append cap per row  : {cap}")
    print()

    # ── 1. transport integrity, from each row's own provenance ────────────────
    # This comes FIRST because it defines the population the lever owns, and both
    # the licence below and the comparison run on exactly that population.
    #
    # WHY THE POPULATION MATTERS, measured rather than assumed: the first version of
    # this reader checked the licence over EVERY row and refused on 4 of 74 samples
    # (`rg_001`, `rg_025`). Those are the deterministic-leg rows — `stage2_polish:
    # false`, `stage2_served_by: ""` — whose wire the route builds on the Stage-1 path
    # and never submits to the wire passes. `_ground_wire_subpoints` therefore has no
    # OFF state to reproduce there, in the gate or in production. Checking them was a
    # scope error in the READER, not a defect in the lever.
    served = {
        row_id: [_served_by(samples[s][row_id]) for s in range(used)]
        for row_id in ids
    }
    min_primary = min(MIN_PRIMARY_SAMPLES, used)
    comparable = [
        row_id
        for row_id, legs in served.items()
        if sum(1 for leg in legs if leg == "primary") >= min_primary
        and (gold.get(row_id) or {}).get("expected_refs")
    ]
    dropped = {r: legs for r, legs in served.items() if r not in comparable}
    print(
        f"[transport] comparable rows (>= {min_primary}/{used} primary, gold refs): "
        f"{len(comparable)}"
    )
    leg_mix = sorted({leg for legs in served.values() for leg in legs})
    print(f"[transport] legs observed: {leg_mix or ['(none recorded)']}")
    for row_id, legs in sorted(dropped.items())[:8]:
        print(f"          dropped {row_id}: {legs}")
    if len(dropped) > 8:
        print(f"          ... and {len(dropped) - 8} more")

    # ── 2. THE LICENCE, on the population above: is the recorded wire the OFF
    #       state of the pass — i.e. is the OFF pass a no-op on its own output? ──
    prev = os.environ.get(FLAG)
    os.environ[FLAG] = "0"
    fixed_ok = 0
    fixed_bad: list[str] = []
    total = 0
    for row_id in comparable:
        for s in range(used):
            answer, refs, question = _graded(samples[s][row_id])
            if not answer or not refs:
                continue
            total += 1
            if R._ground_wire_subpoints(answer, list(refs), question) == refs:
                fixed_ok += 1
            else:
                fixed_bad.append(f"{row_id}/s{s}")
    print(f"[licence] recorded wire is a fixed point of the OFF pass : {fixed_ok}/{total}")
    if fixed_bad:
        print(f"          NOT a fixed point on {len(fixed_bad)}: {fixed_bad[:6]}")
        print("          -> the derived ON arm would not equal the live ON arm. REFUSING.")
        if prev is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = prev
        return 4

    # ── 3. both lever states from the SAME draw, scored with the real rubric ──
    per_arm: dict[str, dict[str, list[float]]] = {
        a: {"off": [], "on": []} for a in AXES
    }
    deltas: dict[str, list[float]] = {a: [] for a in AXES}
    non_vacuous: set[str] = set()
    added = added_gold = 0
    count_bad: list[str] = []
    head_bad: list[str] = []
    regressions: list[str] = []
    gold_head = {"off": 0, "on": 0}
    moved_up = moved_down = 0
    examples: list[str] = []

    for row_id in comparable:
        exp = [str(x) for x in gold[row_id]["expected_refs"]]
        per_row: dict[str, dict[str, list[float]]] = {
            a: {"off": [], "on": []} for a in AXES
        }
        for s in range(used):
            answer, refs, question = _graded(samples[s][row_id])
            os.environ[FLAG] = "0"
            off = R._ground_wire_subpoints(answer, list(refs), question)
            os.environ[FLAG] = "1"
            on = R._ground_wire_subpoints(answer, list(refs), question)
            extra = [x for x in on if x not in off]
            if on != off:
                non_vacuous.add(row_id)
                added += len(extra)
                added_gold += sum(
                    1
                    for x in extra
                    if any(
                        x.lower() == e.lower() or x.lower().startswith(e.lower() + ".")
                        for e in exp
                    )
                )
                if len(examples) < 8:
                    examples.append(f"  {row_id} s{s}: +{extra}  (wire {len(off)} refs)")
            # The one axis the ADD can move in the wrong direction is the count.
            if not 0 <= len(on) - len(off) <= cap:
                count_bad.append(f"{row_id}/s{s}")
            if _heads(on) != _heads(off):
                head_bad.append(f"{row_id}/s{s}")
            if (reference_correctness_strict(on, exp) or 0.0) < (
                reference_correctness_strict(off, exp) or 0.0
            ):
                regressions.append(f"{row_id}/s{s}")
            for arm, refs_arm in (("off", off), ("on", on)):
                per_row["loose"][arm].append(
                    reference_correctness_loose(refs_arm, exp) or 0.0
                )
                per_row["strict"][arm].append(
                    reference_correctness_strict(refs_arm, exp) or 0.0
                )
                per_row["conc"][arm].append(
                    reference_conciseness(refs_arm, exp) or 0.0
                )
        for arm in ("off", "on"):
            gold_head[arm] += len(_heads(exp) - _heads(off if arm == "off" else on))
        for a in AXES:
            mo, mn = _median(per_row[a]["off"]), _median(per_row[a]["on"])
            per_arm[a]["off"].append(mo)
            per_arm[a]["on"].append(mn)
            deltas[a].append((mn - mo) * 100.0)
        so, sn = _median(per_row["strict"]["off"]), _median(per_row["strict"]["on"])
        if sn > so:
            moved_up += 1
        elif sn < so:
            moved_down += 1

    os.environ.pop(FLAG, None)

    def mean(axis: str, arm: str) -> float:
        xs = per_arm[axis][arm]
        return sum(xs) / len(xs) * 100.0 if xs else 0.0

    print()
    print(f"[non-vacuity] rows where the derived arm differs: {len(non_vacuous)}/{len(comparable)}")
    print(f"[non-vacuity] coordinates appended            : {added} (gold {added_gold})")
    print()
    print(f"{'axis':<14} {'OFF':>10} {'ON':>10} {'delta':>9}  95% CI (seeded)")
    for a in AXES:
        lo, hi = _boot_ci(deltas[a])
        print(
            f"{a:<14} {mean(a, 'off'):>10.2f} {mean(a, 'on'):>10.2f} "
            f"{mean(a, 'on') - mean(a, 'off'):>+9.2f}  [{lo:+.2f}, {hi:+.2f}]"
        )
    print()
    print(f"rows where Ref. Strict moved   : up {moved_up} / down {moved_down}")
    print(f"gold heads dropped             : OFF {gold_head['off']} -> ON {gold_head['on']}")
    print(f"append-cap violations          : {len(count_bad)}   <- must be 0")
    print(f"head-set violations            : {len(head_bad)}   <- must be 0")
    print(f"met -> unmet regressions       : {len(regressions)}   <- must be 0")
    print()
    print("examples (OFF wire -> appended):")
    print("\n".join(examples) if examples else "  (none)")

    crit = {
        "licence: fixed point on every row-sample": not fixed_bad,
        "the lever is not inert on this draw": bool(non_vacuous),
        "strict >= -1.5 pp": mean("strict", "on") - mean("strict", "off")
        >= TOLERANCE_STRICT_PP,
        "loose within -1.5 pp": mean("loose", "on") - mean("loose", "off")
        >= TOLERANCE_LOOSE_PP,
        "conc within -2.5 pp": mean("conc", "on") - mean("conc", "off")
        >= TOLERANCE_CONC_PP,
        "gold heads ON <= OFF": gold_head["on"] <= gold_head["off"],
        "append cap respected": not count_bad,
        "head set invariant": not head_bad,
        "no met->unmet regression": not regressions,
    }
    verdict = "SHIP (default stays ON)" if all(crit.values()) else "REVERT (default -> 0)"
    out = {
        "label": LABEL,
        "rows": len(comparable),
        "repeats": used,
        "repeats_pre_registered": REPEATS,
        "generations_note": (
            "all pre-registered generations used"
            if used == REPEATS
            else (
                f"only {used} of {REPEATS} generations complete; the third was aborted by the "
                "harness transport guard when the primary leg returned HTTP 500 on every call"
            )
        ),
        "axes": {
            a: {
                "off": round(mean(a, "off"), 4),
                "on": round(mean(a, "on"), 4),
                "delta": round(mean(a, "on") - mean(a, "off"), 4),
                "ci95": [round(x, 4) for x in _boot_ci(deltas[a])],
            }
            for a in AXES
        },
        "non_vacuous_rows": sorted(non_vacuous),
        "appended": added,
        "appended_gold": added_gold,
        "gold_heads": gold_head,
        "criteria": crit,
        "verdict": verdict,
    }
    (Path(__file__).resolve().parent / "gate-verdict.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )

    print()
    for k, v in crit.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print()
    print(f"VERDICT: {verdict}")
    return 0 if all(crit.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
