"""R428 — does R426's dotted sub-point ADD defeat R425's count-neutral REWRITE?

R426 added a second prose miner to ``_surface_prose_subpoints``: a dotted form
(``Article 6.3``) that ``_PROSE_SUBPOINT_RE`` cannot see. That pass runs at
``regenold.py:12156`` — BEFORE ``_ground_wire_subpoints`` (R425, ``:12718``).

The R425 pass is a REWRITE: for a wire leaf of a prose-sub-pointed parent it
replaces the ungrounded limb with the prose-named one, 1:1, so the reference
COUNT and the folded head set are invariant. But it abstains when the prose-named
coordinate is ALREADY on the wire ("a grounded limb is already on the wire: not a
rewrite"). So if the R426 ADD runs first and puts the prose limb on the list
beside the ungrounded sibling, R425 must abstain — and a count-neutral rewrite
becomes a count-increasing addition.

This module drives the **real** passes over the R424/R423 recorded draws and
scores each arm with the **real** official rubric (``evals.official.rubric``), so
the delta is the graded axis and not a re-implementation of it. No live calls.

The dotted regex is read at CALL time by both passes, so it can be switched per
call, which isolates the two owners of the change:

* ``C`` — regex OFF everywhere: the pre-R426 wire.
* ``M`` — regex ON for the R425 rewrite only: my R425 miner, which is
  count-neutral by construction.

``M − C`` is therefore R425's incremental effect once it can see dotted prose.

R426's ADD is measured as its own pair of cells, because the route has a THIRD
pass between the two (``_collapse_parent_when_subpoint_cited``, R381, default
ON, ``:12621``) and reading the ADD without it would be a biased reading: the
additive pass mints a head+leaf cluster, which is precisely what R381 collapses.
So the pair is

* ``add0`` — R426's ADD with the collapse NOT modelled (the upper bound on harm), and
* ``add1`` — R426's ADD with the real order modelled: surface → collapse → ground.

Each of these is scored against the SAME row as its no-ADD twin, so nothing is
draw-confounded.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r428.dotted_subpoint_probe
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.routes import regenold as R  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
NEVER = re.compile(r"(?!x)x")  # a pattern that can never match


def _rows() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    pats = (
        "official-r424-*-hard*.ckpt.jsonl",
        "official-r423-need4-*-hard*.ckpt.jsonl",
        "official-r423-need3-*-hard*.ckpt.jsonl",
    )
    for pat in pats:
        for p in sorted(RESULTS.glob(pat)):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append((f"{p.stem}:{json.loads(line)['id']}", json.loads(line)))
    return out


def _graded_pair(row: dict[str, Any]) -> tuple[str, list[str]]:
    """The turn the route's wire passes actually saw — all-or-nothing."""
    if row.get("pushback_answer") or row.get("pushback_refs"):
        return row.get("pushback_answer") or "", [str(x) for x in (row.get("pushback_refs") or [])]
    return row.get("pred_answer") or "", [str(x) for x in (row.get("pred_refs") or [])]



def _classify_unmet(
    why: dict[str, int],
    answer: str,
    expected: str,
    refs: list[str],
    m1: list[str],
    bump: Any,
) -> None:
    """Why is this gold sub-point unmet? Names the OWNER of the deficit.

    Each bucket routes to different engineering work, and the distinction that
    matters most is whether the wire carries the coordinate's parent at all and
    at what grain:

    * the prose never names the coordinate → generation-side (Stage 2 must say it),
    * named, and **no coordinate of that parent is on the wire** → a coverage pass,
    * named, and the only coordinate present is a **shallower prefix** of the
      expected one → a DEPTH problem (R386's deepener remit, not coverage),
    * named, the bare parent head is on the wire, and R136's ``>=3 sub-points of
      one parent`` minimal-cover rule dropped the bucket → a deliberate trade.
    """
    el = expected.lower()
    named = any(hit.lower() == el or hit.lower().startswith(el + ".") for hit in _prose_coords(answer))
    if not named:
        bump("prose_never_names_it")
        return
    parent = el.split(".")[0]
    present = [
        str(r).strip().lower()
        for r in m1
        if str(r).strip().lower() == parent
        or str(r).strip().lower().startswith(parent + ".")
    ]
    if not present:
        bump("named_no_coord_of_parent_on_wire")
        return
    if any(p == parent for p in present):
        wanted = R._prose_named_subpoints(answer)
        if len(wanted.get(parent, [])) >= 3:
            bump("named_R136_suppressed")
            return
        bump("named_bare_head_other")
        return
    bump("named_only_a_shallower_grain")


def _prose_coords(answer: str) -> list[str]:
    """Every user-facing coordinate the answer's prose names, both forms."""
    out = list(R._prose_named_subpoints(answer).values())
    return [x for bucket in out for x in bucket]


def main() -> int:
    gold = {
        r["id"]: r
        for r in (
            json.loads(x)
            for x in GOLD.read_text(encoding="utf-8").splitlines()
            if x.strip()
        )
    }
    # C/M are the no-ADD arms; --0 / --1 are the same rows WITH the ADD, before
    # and after the R381 collapse the route runs between the two passes.
    axes = {k: {"loose": [], "strict": [], "conc": []} for k in ("C", "M", "A0", "A1", "M1")}
    dotted_adds = 0
    dotted_gold = 0
    dotted_excess = 0
    dotted_survives_collapse = 0
    rewrite_dotted = 0
    rows_with_dotted_prose = 0
    moved_strict = 0
    deficit_rows = 0
    deficit_recovered = 0
    subpoint_gold_rows = 0
    subpoint_unmet = 0
    subpoint_recovered = 0
    # Where an unmet gold sub-point actually lives — the roadmap question.
    why: dict[str, int] = {}

    def _bump(k: str) -> None:
        why[k] = why.get(k, 0) + 1
    n = 0
    examples: list[str] = []
    orig = R._GROUND_PROSE_DOTTED_RE

    for key, row in _rows():
        rid = str(row.get("id"))
        g = gold.get(rid) or {}
        exp = [str(x) for x in (g.get("expected_refs") or [])]
        if not exp:
            continue
        answer, refs = _graded_pair(row)
        if not answer or not refs:
            continue
        n += 1

        if orig.search(answer):
            rows_with_dotted_prose += 1

        R._GROUND_PROSE_DOTTED_RE = NEVER
        c = R._ground_wire_subpoints(answer, R._surface_prose_subpoints(answer, refs))
        # Arm M: the R425 miner keeps its dotted sight, the additive pass does not.
        s_off = R._surface_prose_subpoints(answer, refs)
        R._GROUND_PROSE_DOTTED_RE = orig
        m = R._ground_wire_subpoints(answer, s_off)
        s_on = R._surface_prose_subpoints(answer, refs)
        a0 = R._ground_wire_subpoints(answer, s_on)
        a1 = R._ground_wire_subpoints(
            answer, R._collapse_parent_when_subpoint_cited(s_on)
        )
        m1 = R._ground_wire_subpoints(
            answer, R._collapse_parent_when_subpoint_cited(s_off)
        )

        for name, arm in (("C", c), ("M", m), ("A0", a0), ("M1", m1), ("A1", a1)):
            axes[name]["loose"].append(reference_correctness_loose(arm, exp))
            axes[name]["strict"].append(reference_correctness_strict(arm, exp))
            axes[name]["conc"].append(reference_conciseness(arm, exp))

        if reference_correctness_strict(m1, exp) != reference_correctness_strict(a1, exp):
            moved_strict += 1
        if reference_correctness_strict(m1, exp) is not None and reference_correctness_strict(m1, exp) < 1.0:
            deficit_rows += 1
            if reference_correctness_strict(a1, exp) > reference_correctness_strict(m1, exp):
                deficit_recovered += 1
        # The population the mechanism could actually win on: gold carries a
        # sub-point coordinate, and the no-ADD wire does NOT already satisfy it.
        subs = [e for e in exp if "." in e]
        if subs:
            subpoint_gold_rows += 1
            for e in subs:
                pred = [str(x).lower() for x in m1]
                el = e.lower()
                met = any(p == el or p.startswith(el + ".") for p in pred)
                if not met:
                    subpoint_unmet += 1
                    preda = [str(x).lower() for x in a1]
                    if any(p == el or p.startswith(el + ".") for p in preda):
                        subpoint_recovered += 1
                    _classify_unmet(why, answer, str(e), refs, m1, _bump)
        if m != c:
            rewrite_dotted += 1

        # Attribution: additions only the dotted ADD can be responsible for.
        dots = [x for x in a0 if x not in m]
        dotted_adds += len(dots)
        dotted_survives_collapse += len([x for x in a1 if x not in m1])
        a = a1
        exps = [e.lower() for e in exp]
        for x in dots:
            xl = x.lower()
            if any(xl == e or xl.startswith(e + ".") or e.startswith(xl + ".") for e in exps):
                dotted_gold += 1
            else:
                dotted_excess += 1
        if dots and len(examples) < 10:
            examples.append(f"  {key}\n    refs={refs}\n    M ={m}\n    A ={a}")

    def mean(xs: list[float | None]) -> float:
        vals = [float(x) for x in xs if x is not None]
        return sum(vals) / len(vals) * 100.0 if vals else 0.0

    print(f"rows scored (graded pair, gold refs present): {n}")
    print(f"rows whose answer contains a dotted citation: {rows_with_dotted_prose}")
    print(f"R425 rewrite fires on {rewrite_dotted} rows once it can see dotted prose (M != C)")
    print(f"R426 dotted ADD : {dotted_adds} refs  (gold {dotted_gold} / excess {dotted_excess})")
    if not dotted_adds:
        print(
            "  NOTE: 0 because the ADD was REMOVED in R428 — this run measures the shipped\n"
            "  tree. The pre-removal figures recorded in CHECKPOINT.md (13 refs, 2 gold / 11\n"
            "  excess, Ref. Conc -0.01 pp) reproduce at commit e879c8d, i.e. with the loop\n"
            "  back in ``_surface_prose_subpoints``; they are the audit of R426, not of today."
        )
    print(f"  ... of which survive the R381 parent collapse: {dotted_survives_collapse} refs")
    print(f"rows where the ADD moves Ref. Strict at all: {moved_strict}")
    print(f"rows still short of full Ref. Strict recall: {deficit_rows}; of those, recovered by the ADD: {deficit_recovered}")
    print(
        f"gold sub-point coords: {subpoint_gold_rows} rows carry one; {subpoint_unmet} are UNMET "
        f"without the ADD, and the ADD satisfies {subpoint_recovered} of them"
    )
    print("  why each unmet sub-point is unmet (and who owns the fix):")
    for k, v in sorted(why.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<36} {v}")
    print()
    print(f"{'arm':<4} {'ref_loose':>10} {'ref_strict':>11} {'ref_conc':>9}")
    for name in ("C", "M", "M1", "A0", "A1"):
        v = axes[name]
        print(
            f"{name:<4} {mean(v['loose']):>10.2f} {mean(v['strict']):>11.2f} {mean(v['conc']):>9.2f}"
        )
    print()
    for label, arm, base in (
        ("M-C   (R425 sees dotted prose)", "M", "C"),
        ("A0-M  (ADD, no collapse modelled)", "A0", "M"),
        ("A1-M1 (ADD, REAL route order)", "A1", "M1"),
    ):
        print(
            f"{label:<34} loose {mean(axes[arm]['loose']) - mean(axes[base]['loose']):+.2f}  "
            f"strict {mean(axes[arm]['strict']) - mean(axes[base]['strict']):+.2f}  "
            f"conc {mean(axes[arm]['conc']) - mean(axes[base]['conc']):+.2f}"
        )
    print()
    print("examples (M -> A):")
    print("\n".join(examples) if examples else "  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
