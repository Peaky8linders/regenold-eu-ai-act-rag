"""R429 — does COMPLETING a shallower wire coordinate move the graded axes?

R428 classified the 230 unmet gold sub-point expectations on the recorded hard
board and split them 138 depth / 79 generation-side / 4 R136 / 2 coverage. The
depth ones are where the wire carries the expected coordinate's PARENT but only
at a shallower grain — ``Annex IV.1`` shipped where the gold key is
``Annex IV.1.e``. R425 deliberately abstained on that shape, and its docstring
said why: "*A prefix means depth, not substitution ... rewriting it would replace
a graded coordinate with a deeper one the evaluator may not key on.*"

That premise is false and the rubric's own source says so:

    def _is_descendant(pred, expected):
        return pred == expected or pred.startswith(expected + ".")

A prediction STRICTLY MORE PRECISE than the key satisfies the key, and Ref.
Correctness (Strict) is per-question recall of the expected coordinates. So
completing a wire coordinate to a DEEPER coordinate of the same limb can only add
satisfied expectations — monotone by construction, not by measurement.

THE ARMS. These captures were recorded BEFORE the R425 merge landed (the gate
checkpoints are dated 2026-09-19/20, ``981ec6d`` merged 2026-09-20), which is
visible in the data: ``rg_007`` ships ``Article 50.3`` where its prose names
``Article 50(1)`` — the ungrounded sibling R425 exists to repair. So the recorded
``pred_refs`` / ``pushback_refs`` are the wire BEFORE the prose-grounding pass, and
applying the pass to them replays it. That gives three arms on identical inputs:

* ``shipped`` — the wire as recorded (pre-R425; not today's board),
* ``r425``    — ``pass(shipped)`` with the depth lever OFF = **today's board**,
* ``r429``    — ``pass(shipped)`` with the depth lever ON.

``r429 − r425`` is therefore R429's incremental effect and nothing else. Rows that
took the deterministic / curated path are EXCLUDED, because the route gates the
pass on ``_stage2_landed`` (R133/R425 doctrine) and a replay that grounds their
hand-validated wire would measure a change production never makes.

Scored with the REAL ``evals.official.rubric``, never a reimplementation, and the
count / folded-head-set invariance is asserted per row rather than argued.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r429.wire_depth_probe
"""

from __future__ import annotations

import json
import os
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
FLAG = "REGENOLD_GROUND_WIRE_DEPTH"
ARMS = ("shipped", "r425", "r429")


def _rows() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for pat in (
        "official-r424-*-hard*.ckpt.jsonl",
        "official-r423-need4-*-hard*.ckpt.jsonl",
        "official-r423-need3-*-hard*.ckpt.jsonl",
    ):
        for path in sorted(RESULTS.glob(pat)):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    out.append((f"{path.stem}:{row.get('id')}", row))
    return out


def _graded_pair(row: dict[str, Any]) -> tuple[str, list[str]]:
    """The turn the route's wire passes saw — the hard-mode graded turn."""
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
        )
    return row.get("pred_answer") or "", [str(x) for x in (row.get("pred_refs") or [])]


def _stage2_landed(row: dict[str, Any]) -> bool:
    """Whether the route would run the pass at all (the ``_stage2_landed`` gate)."""
    prov = row.get("provenance") or {}
    return bool(prov.get("stage2_polish"))


def _heads(refs: list[str]) -> set[str]:
    return {h for h in (ref_head(r) for r in refs) if h}


def _is_descendant(pred: str, expected: str) -> bool:
    return pred == expected or pred.startswith(expected + ".")


def _in_expected(ref: str, expected: list[str]) -> bool:
    return any(_is_descendant(ref.lower(), e.lower()) for e in expected)


def main() -> int:
    gold = {}
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            gold[str(g["id"])] = g

    axes: dict[str, dict[str, list[float | None]]] = {
        k: {"loose": [], "strict": [], "conc": []} for k in ARMS
    }
    n_rows = 0
    n_excluded = 0
    count_bad = 0
    head_bad = 0
    strict_regressions = 0
    loose_regressions = 0
    rows_depth = 0
    depth_rewrites = 0
    depth_gold = 0
    depth_excess = 0
    rows_moved_strict = 0
    multi_candidate = 0
    r425_rewrites = 0
    # Attribution, computed against TODAY'S board (the r425 arm).
    unmet_total = 0
    unmet_depth = 0
    depth_named_by_prose = 0
    depth_converted = 0
    depth_no_descendant = 0
    depth_desc_missed = 0
    depth_wire_is_head = 0
    depth_gold_tiebreak = 0
    unmet_substitution = 0
    unmet_coverage = 0
    unmet_other = 0
    examples: list[str] = []
    converted_examples: list[str] = []
    missed: list[str] = []

    prev = os.environ.get(FLAG)
    os.environ[FLAG] = "0"

    for key, row in _rows():
        rid = str(row.get("id"))
        g = gold.get(rid) or {}
        exp = [str(x) for x in (g.get("expected_refs") or [])]
        if not exp:
            continue
        answer, shipped = _graded_pair(row)
        if not answer or not shipped:
            continue
        if not _stage2_landed(row):
            n_excluded += 1
            continue
        n_rows += 1
        prose = R._prose_named_subpoints(answer)

        os.environ[FLAG] = "0"
        r425 = R._ground_wire_subpoints(answer, list(shipped))
        os.environ.pop(FLAG, None)
        assert R._ground_wire_depth_enabled() is True, "the lever must default ON"
        r429 = R._ground_wire_subpoints(answer, list(shipped))

        for a, b in ((shipped, r425), (r425, r429), (shipped, r429)):
            if len(a) != len(b):
                count_bad += 1
            if _heads(a) != _heads(b):
                head_bad += 1

        wire = {"shipped": shipped, "r425": r425, "r429": r429}
        for name in ARMS:
            axes[name]["loose"].append(reference_correctness_loose(wire[name], exp))
            axes[name]["strict"].append(reference_correctness_strict(wire[name], exp))
            axes[name]["conc"].append(reference_conciseness(wire[name], exp))

        s425 = reference_correctness_strict(r425, exp)
        s429 = reference_correctness_strict(r429, exp)
        if s425 != s429:
            rows_moved_strict += 1
        # THE SAFETY PROPERTY: a completion may add satisfied expectations and
        # may never remove one. Asserted per row, not argued.
        if s429 is not None and s425 is not None and s429 < s425:
            strict_regressions += 1
        l425 = reference_correctness_loose(r425, exp)
        l429 = reference_correctness_loose(r429, exp)
        if l429 is not None and l425 is not None and l429 < l425:
            loose_regressions += 1

        r425_rewrites += sum(1 for x in r425 if x not in shipped)
        completed = 0
        for before, after in zip(r425, r429, strict=False):
            if before == after:
                continue
            completed += 1
            if _in_expected(after, exp):
                depth_gold += 1
            else:
                depth_excess += 1
            # How often the tie-break between several prose-named descendants of
            # the wire's own limb had to decide.
            lc = R._leaf_coordinate(before)
            if lc is not None:
                desc = [
                    d for d in prose.get(lc[0], [])
                    if _is_descendant(d.lower(), before.lower())
                    and d.lower() != before.lower()
                ]
                if len(desc) > 1:
                    multi_candidate += 1
        if completed:
            rows_depth += 1
            depth_rewrites += completed
            if len(examples) < 8:
                examples.append(f"  {key}\n    r425={r425}\n    r429={r429}")

        # Attribution over the unmet gold sub-points on today's board.
        for e in exp:
            if "." not in e:
                continue
            if _in_expected_any(r425, e):
                continue
            unmet_total += 1
            parent = e.lower().split(".")[0]
            kin = [str(p).lower() for p in r425 if str(p).lower().split(".")[0] == parent]
            if not kin:
                unmet_coverage += 1
                continue
            coarser = [k for k in kin if _is_descendant(e.lower(), k) and k != e.lower()]
            other_limb = [k for k in kin if not _is_descendant(e.lower(), k)
                          and not _is_descendant(k, e.lower())]
            # A BARE HEAD is not a leaf coordinate, so this pass cannot reach it:
            # turning a head into a leaf is R386's deepener / R133's add, and it
            # is deliberately out of scope here. Counted separately so it is not
            # mistaken for a leaf-grain defect this lever failed to fix.
            if not any("." in k for k in kin):
                unmet_depth += 1
                depth_wire_is_head += 1
                continue
            if coarser:
                unmet_depth += 1
                named = prose.get(parent, [])
                desc = [x for x in named if _is_descendant(x.lower(), e.lower())]
                if desc:
                    depth_named_by_prose += 1
                converted = _in_expected_any(r429, e) and not _in_expected_any(
                    r425, e
                )
                if converted:
                    depth_converted += 1
                    # Did more than one prose-named descendant of the wire's own
                    # limb compete? Then the tie-break decided this win.
                    hit = next(
                        (
                            k for k in r425
                            if _is_descendant(str(k).lower(), e.lower())
                            or str(k).lower() == e.lower()
                        ),
                        None,
                    )
                    if hit is None:
                        lc_any = [
                            R._leaf_coordinate(k) for k in r425
                            if _is_descendant(e.lower(), str(k).lower())
                        ]
                        for lc in lc_any:
                            if lc is None:
                                continue
                            rivals = [
                                d for d in prose.get(lc[0], [])
                                if _is_descendant(d.lower(), e.lower())
                                and d.lower() != e.lower()
                            ]
                            if rivals:
                                depth_gold_tiebreak += 1
                                break
                    if len(converted_examples) < 8:
                        converted_examples.append(
                            f"  {key}  {e}   wire={r425}"
                        )
                elif not desc:
                    # Nothing in the prose names a deeper coordinate of this key:
                    # no 1:1 depth completion exists. Out of this lever's scope.
                    depth_no_descendant += 1
                else:
                    # The prose DOES name a descendant, so the completion existed
                    # but the pass shipped a different one (tie-break against a
                    # rival candidate, or the coordinate was already on the wire).
                    depth_desc_missed += 1
                    if len(missed) < 14:
                        missed.append(
                            f"  {key}\n      key={e}  wire={r425}\n"
                            f"      prose-of-parent={named}\n"
                            f"      prose-named-descendants-of-key={desc}"
                        )
            elif other_limb:
                unmet_substitution += 1
            else:
                unmet_other += 1

    if prev is None:
        os.environ.pop(FLAG, None)
    else:
        os.environ[FLAG] = prev

    def mean(xs: list[float | None]) -> float:
        vals = [float(x) for x in xs if x is not None]
        return sum(vals) / len(vals) * 100.0 if vals else 0.0

    print(f"flag : {FLAG} (default ON)")
    print(f"rows scored (graded pair, gold refs, Stage-2 landed) : {n_rows}")
    print(f"rows excluded (deterministic / curated path)         : {n_excluded}")
    print(f"count-invariance violations                          : {count_bad}")
    print(f"folded-head-set violations                           : {head_bad}")
    print(f"Ref. Strict REGRESSIONS (met -> unmet)                : "
          f"{strict_regressions}   <- must be 0")
    print(f"Ref. Loose  REGRESSIONS                               : "
          f"{loose_regressions}   <- must be 0")
    print()
    print(f"R425-only rewrites (already shipped, banked)         : {r425_rewrites}")
    print(f"rows R429 changes                                    : {rows_depth}")
    print(f"coordinates R429 completes                           : {depth_rewrites}"
          f"  (gold {depth_gold} / excess {depth_excess})")
    print(f"  ... of which the tie-break between candidates had to decide: "
          f"{multi_candidate}")
    print(f"rows where Ref. Strict moved                         : {rows_moved_strict}")
    print()
    print("gold sub-point expectations UNMET on today's board:")
    print(f"  total                                 : {unmet_total}")
    print(f"  ... wire ships a COARSER coordinate   : {unmet_depth}"
          f"   (prose names a descendant of the key: {depth_named_by_prose})")
    print(f"  ... same parent, other limb (R425's)  : {unmet_substitution}")
    print(f"  ... no coordinate of the parent       : {unmet_coverage}")
    print(f"  ... neither                           : {unmet_other}")
    print(f"  CONVERTED unmet -> met by R429        : {depth_converted}"
          f"   (of which a competing candidate had to lose: {depth_gold_tiebreak})")
    print(f"  ... reachable in principle but MISSED : {depth_desc_missed}")
    print(f"  ... no prose-named descendant to use  : {depth_no_descendant}")
    print(f"  ... wire ships the BARE HEAD (R386/R133 remit, out of scope): "
          f"{depth_wire_is_head}")
    print()
    print(f"{'arm':<8} {'ref_loose':>10} {'ref_strict':>11} {'ref_conc':>9}")
    for name in ARMS:
        v = axes[name]
        print(
            f"{name:<8} {mean(v['loose']):>10.2f} {mean(v['strict']):>11.2f} "
            f"{mean(v['conc']):>9.2f}"
        )
    print()
    print(
        f"DELTA r429-r425   loose "
        f"{mean(axes['r429']['loose']) - mean(axes['r425']['loose']):+.2f}"
        f"   strict {mean(axes['r429']['strict']) - mean(axes['r425']['strict']):+.2f}"
        f"   conc {mean(axes['r429']['conc']) - mean(axes['r425']['conc']):+.2f}"
    )
    print(
        f"(context) r425-shipped  loose "
        f"{mean(axes['r425']['loose']) - mean(axes['shipped']['loose']):+.2f}"
        f"   strict {mean(axes['r425']['strict']) - mean(axes['shipped']['strict']):+.2f}"
        f"   conc {mean(axes['r425']['conc']) - mean(axes['shipped']['conc']):+.2f}"
    )
    print()
    print("examples (today's board -> R429):")
    print("\n".join(examples) if examples else "  (none)")
    print()
    print("expectations CONVERTED:")
    print("\n".join(converted_examples) if converted_examples else "  (none)")
    print()
    print("depth cases the prose could reach but the pass MISSED (diagnostic):")
    print("\n".join(missed) if missed else "  (none)")
    return 0


def _in_expected_any(refs: list[str], expected: str) -> bool:
    el = expected.lower()
    return any(_is_descendant(str(r).lower(), el) for r in refs)


if __name__ == "__main__":
    raise SystemExit(main())
