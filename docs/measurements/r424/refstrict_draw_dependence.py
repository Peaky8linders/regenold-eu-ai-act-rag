"""R424 — is the `ref_correctness_strict` loss a cost of the fixed shape, or draw noise?

The gate (`hard_preamble_gate.py`, label ``r424-preamble``) shipped the fixed
9-turn preamble on a pre-registered rule, and its official board reads::

    ans_correctness_loose  97.09 ->  97.09   +0.00
    ans_correctness_strict 92.86 ->  92.86   +0.00
    ref_correctness_strict 74.40 ->  70.83   -3.57
    overall                78.44 ->  78.56   +0.11

Three of the eight axes move by generation noise; two of them (the answer axes) are
pinned at exactly +0.00 on all 28 comparable rows, and the reference axes are not.
``ref_correctness_strict`` is the one axis with a loss, so it gets this check: a
graded request shape is not worth a metric, and the pre-registered rule only
refuses the lever if the ANSWER axes or the aggregate fall.

What the loss actually is (two independent questions):

1. **Is the credited criterion reproducible across the arm's own generations?**
   R419 established that a row's credited criteria are draw-dependent, and that a
   single draw cannot separate a delta from generation noise. For each comparable
   row this prints arm A's and arm B's per-sample strict hit and flags the rows
   whose verdict is not constant within an arm. A row that is stable in A and
   unstable in B is a DRAW effect on B, not a systematic fidelity penalty.

2. **Where the wire reference disagrees with the answer's own prose.** The route
   recomputes the wire references from the prose, so the graded ``references``
   field is supposed to name what the answer describes. When the answer says
   ``(Article 99(3))`` and the wire records ``Article 99.4``, the sub-point the
   answer names has been replaced by a neighbouring limb of the same article —
   a reference-GRAIN defect that costs Ref Strict on any request shape, and the
   reason those rows read differently in the two arms.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r424.refstrict_draw_dependence
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

RESULTS = REPO / "evals" / "bench" / "results"
SCORES = REPO / "docs" / "measurements" / "r388"
GATE = Path(__file__).resolve().parent / "hard_preamble_gate.json"

LABEL = "r424-preamble"
ARMS = ("A", "B")
REPEATS = 3


def _ckpt_path(arm: str, sample: int) -> Path:
    stem = f"official-{LABEL}-{arm}-hard"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def _score_path(arm: str, sample: int) -> Path:
    return SCORES / f"score-{LABEL}-{arm}-s{sample}-hard.json"


def _ckpt_rows(arm: str, sample: int) -> dict[str, dict[str, Any]]:
    text = _ckpt_path(arm, sample).read_text(encoding="utf-8")
    return {r["id"]: r for r in (json.loads(line) for line in text.splitlines() if line.strip())}


def _score_rows(arm: str, sample: int) -> dict[str, dict[str, Any]]:
    data = json.loads(_score_path(arm, sample).read_text(encoding="utf-8"))
    return {r["id"]: r for r in data["rows"]}


def _strict_hit(row: dict[str, Any]) -> float:
    """1.0 when every expected sub-point reference is met, else the fraction met."""
    got = {s.strip().lower() for s in (row.get("refs") or [])}
    want = [s.strip().lower() for s in (row.get("expected_refs") or [])]
    if not want:
        return float("nan")
    heads = set()
    for token in want:
        m = re.match(r"(article\s+\d+\.[0-9a-z]+|annex\s+[ivxlc]+\.[0-9a-z]+)", token)
        heads.add(m.group(1) if m else token)
    met = sum(1 for h in heads if h in got)
    return met / len(heads)


def _prose_subpoints(answer: str) -> set[str]:
    """Sub-points the ANSWER names in statutory form (``Article 99(3)``)."""
    out: set[str] = set()
    for m in re.finditer(r"Article\s+(\d+)\((\d+)\)", answer or ""):
        out.add(f"article {m.group(1)}.{m.group(2)}")
    for m in re.finditer(r"Annex\s+([IVXLC]+)\((\d+)\)", answer or ""):
        out.add(f"annex {m.group(1).lower()}.{m.group(2)}")
    return out


def _wire_subpoints(refs: list[str]) -> set[str]:
    """Sub-points the WIRE references carry, in the same lower-case form."""
    out: set[str] = set()
    for raw in refs or []:
        m = re.match(r"\s*Article\s+(\d+)\.([0-9a-z]+)\s*$", str(raw), re.IGNORECASE)
        if m:
            out.add(f"article {m.group(1)}.{m.group(2)}")
            continue
        m = re.match(r"\s*Annex\s+([IVXLC]+)\.([0-9a-z]+)\s*$", str(raw), re.IGNORECASE)
        if m:
            out.add(f"annex {m.group(1).lower()}.{m.group(2)}")
    return out


def _substituted_limbs(prose: set[str], wire: set[str]) -> list[str]:
    """Wire sub-points of a parent the PROSE also sub-points, but at a DIFFERENT limb.

    This is the precise signature of the defect: the answer names ``Article 99(3)``
    and the wire records ``Article 99.4``. A wire sub-point of a parent the prose
    does not sub-point at all is *not* flagged — that is an ordinary additional
    citation, and counting it would overstate the finding.
    """
    out: list[str] = []
    for w in sorted(wire):
        parent, _, limb = w.partition(".")
        same_parent = {p for p in prose if p.split(".")[0] == parent}
        if same_parent and w not in same_parent:
            out.append(w)
    return out


def main() -> int:
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    comparable = [r["id"] for r in gate["per_row"]]
    print(f"comparable rows: {len(comparable)}")

    ck = {(arm, s): _ckpt_rows(arm, s) for arm in ARMS for s in range(REPEATS)}
    sc = {(arm, s): _score_rows(arm, s) for arm in ARMS for s in range(REPEATS)}

    unstable: list[str] = []
    prose_grain: list[tuple[str, str, str, list[str], list[str]]] = []
    for row_id in comparable:
        per_arm: dict[str, list[float]] = {}
        for arm in ARMS:
            per_arm[arm] = [_strict_hit(sc[(arm, s)][row_id]) for s in range(REPEATS)]
        if len({round(v, 4) for v in per_arm["B"]}) > 1 and len(
            {round(v, 4) for v in per_arm["A"]}
        ) == 1:
            unstable.append(row_id)

        # The graded answer is the pushed-back one (``pred_refs`` mirrors
        # ``pushback_refs``); compare the wire grain it recorded against the
        # sub-points its own prose names.
        for arm in ARMS:
            for s in range(REPEATS):
                row = ck[(arm, s)][row_id]
                prose = _prose_subpoints(row.get("pushback_answer") or "")
                wire = _wire_subpoints(row.get("pushback_refs") or [])
                if not prose or not wire:
                    continue
                substituted = _substituted_limbs(prose, wire)
                if substituted:
                    prose_grain.append(
                        (row_id, arm, str(s), sorted(prose), substituted)
                    )
                    break

    print(f"\nrows stable in A but not in B (draw effect on B): {unstable or 'none'}")
    print("rows whose graded wire SUBSTITUTED a neighbouring limb of a parent the "
          "prose itself sub-points:")
    print(f"  {sorted({p[0] for p in prose_grain}) or 'none'} "
          f"({len({(p[0], p[1]) for p in prose_grain})} arm-row occurrences)")
    for row_id, arm, sample, prose, substituted in prose_grain:
        print(f"  {row_id} {arm} s{sample}: prose names {prose}, wire recorded "
              f"{substituted} for the same parent")

    if unstable:
        print("\ndelta_ref_strict with those rows removed (draw-noise control):")
        kept = [r for r in gate["per_row"] if r["id"] not in unstable]
        import statistics

        vals = [r["delta_ref_strict"] for r in kept]
        print(f"  n={len(vals)}  mean {100 * statistics.fmean(vals):+.2f} pp  "
              f"median {100 * statistics.median(vals):+.2f} pp")
        vals_all = [r["delta_ref_strict"] for r in gate["per_row"]]
        print(f"  (all comparable: n={len(vals_all)}  "
              f"mean {100 * statistics.fmean(vals_all):+.2f} pp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
