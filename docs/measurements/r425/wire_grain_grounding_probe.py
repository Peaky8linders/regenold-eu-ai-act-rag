"""R425 — measure the wire-grain substitution before trusting it.

The R424 gate left one open finding: the graded ``references`` field ships a limb
of a parent the ANSWER's prose sub-points at a DIFFERENT limb (``rg_100``'s
answer names ``Article 6(3)`` while the wire recorded ``Article 6.2``). The
route's contract is that the wire is recomputed from the prose, but
``_surface_prose_subpoints`` only ADDS a prose-named leaf when the BARE PARENT is
on the list — so a list that already carries a SIBLING limb never receives the
grounded one.

This module drives the **real** pass
(``app.routes.regenold._ground_wire_subpoints``) over the R424 gate's six
checkpoints and scores the result with the **real** official rubric
(``evals.official.rubric``), so the projected delta is the graded axis and not a
re-implementation of it. Nothing here is a live call: it replays captured rows.

It answers three questions with evidence:

1. **How many pairs are true substitutions?** A wire leaf whose coordinate is a
   prefix of a prose-named coordinate is a grain-depth difference
   (``Article 13.3`` against prose ``Article 13(3)(b)``) and is not one.
2. **Which limb is the gold one?** If the wire limb were gold and the prose limb
   not, "trust the prose" would LOSE Ref Strict and the lever must not ship.
3. **What does the pass do to the graded axes?** Ref Strict must rise; Ref
   Conciseness must be unchanged (count-neutral); the folded head set must be
   invariant (Hard Rule #8 by construction).

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r425.wire_grain_grounding_probe
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

from app.routes.regenold import (  # noqa: E402
    _ground_wire_subpoints,
)
from evals.official.rubric import (  # noqa: E402
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
)

RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
GATE = REPO / "docs" / "measurements" / "r424" / "hard_preamble_gate.json"

LABELS = ("r424-preamble", "r423-need4")
ARMS = ("A", "B")
REPEATS = 3


def _head_of(ref: str) -> str:
    m = re.match(r"\s*(Article\s+\d{1,3}|Annex\s+[IVXLC]+)", str(ref), re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip().lower() if m else str(ref).lower()


def _head_set(refs: list[str]) -> set[str]:
    return {_head_of(r) for r in refs or []}


def _load_gold() -> dict[str, dict[str, Any]]:
    return {
        r["id"]: r
        for r in (
            json.loads(line)
            for line in GOLD.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _ckpt(label: str, arm: str, sample: int) -> dict[str, dict[str, Any]]:
    stem = f"official-{label}-{arm}-hard"
    p = RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")
    if not p.exists():
        return {}
    return {r["id"]: r for r in (json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip())}


def _applied_pairs(refs: list[str], after: list[str]) -> list[tuple[str, str]]:
    """The (from, to) pairs the pass ACTUALLY applied.

    Derived from the pass's own output, not from a re-derivation of its guards:
    the rewrite is order-preserving and 1:1, so a positional diff of the list it
    returned is the applied set by definition. An earlier version of this probe
    enumerated candidate pairs from ``_prose_named_subpoints`` instead, which
    over-counts — it lists pairs the pass considers and then filters by
    ``coordinate_exists`` and the one-rewrite-per-leaf cap. Attribution must not
    drift from the shipped semantics, so it now reads the rewrite off the result.
    """
    if len(refs) != len(after):
        return []
    return [
        (str(a).strip(), str(b).strip())
        for a, b in zip(refs, after, strict=True)
        if str(a).strip() != str(b).strip()
    ]


def main() -> int:
    gold = _load_gold()
    comparable = {r["id"] for r in json.loads(GATE.read_text(encoding="utf-8"))["per_row"]}

    n_rows_total = 0
    n_rows_rewritten = 0
    pairs_total = 0
    rows: set[str] = set()
    wire_is_gold = prose_is_gold = both = neither = 0
    head_mismatch = count_mismatch = 0
    axes_before: dict[str, list[float]] = {"loose": [], "strict": [], "conc": []}
    axes_after: dict[str, list[float]] = {"loose": [], "strict": [], "conc": []}
    moved: list[str] = []
    examples: list[str] = []
    legs: dict[str, int] = {}
    import collections

    legs = collections.Counter()

    for label in LABELS:
        for arm in ARMS:
            for s in range(REPEATS):
                ck = _ckpt(label, arm, s)
                if not ck:
                    continue
                for rid, row in sorted(ck.items()):
                    # The GRADED pair, and the same pair the route's own pass sees on
                    # that turn. Falling back to the turn-1 fields must be all-or-
                    # nothing: mixing a pushback ref list with a turn-1 answer would
                    # pair prose with references from a different turn.
                    if row.get("pushback_answer") or row.get("pushback_refs"):
                        answer = row.get("pushback_answer") or ""
                        refs = [str(x) for x in (row.get("pushback_refs") or [])]
                    else:
                        answer = row.get("pred_answer") or ""
                        refs = [str(x) for x in (row.get("pred_refs") or [])]
                    g = gold.get(rid) or {}
                    exp = [str(x) for x in (g.get("expected_refs") or [])]
                    after = _ground_wire_subpoints(answer, refs)

                    if rid not in comparable:
                        continue  # only the paired comparable subset carries the axes
                    n_rows_total += 1
                    if after != refs:
                        n_rows_rewritten += 1
                        rows.add(rid)
                        # Count the leg on the REWRITTEN subset only: the gate's
                        # argument for its ``_stage2_landed`` guard is that every
                        # measured rewrite happened on a Stage-2-served row.
                        legs[str((row.get("provenance") or {}).get("stage2_served_by"))] += 1
                        if _head_set(after) != _head_set(refs):
                            head_mismatch += 1
                        if len(after) != len(refs):
                            count_mismatch += 1

                    pairs = _applied_pairs(refs, after)
                    if pairs and after != refs:
                        pairs_total += len(pairs)
                        exps = [e.lower() for e in exp]
                        for wire_leaf, prose_leaf in pairs:
                            w = wire_leaf.lower()
                            p = prose_leaf.lower()
                            wg = any(w == e or w.startswith(e + ".") or e.startswith(w + ".") for e in exps)
                            pg = any(p == e or p.startswith(e + ".") or e.startswith(p + ".") for e in exps)
                            if wg and pg:
                                both += 1
                            elif wg:
                                wire_is_gold += 1
                            elif pg:
                                prose_is_gold += 1
                            else:
                                neither += 1

                    for name, fn in (
                        ("loose", reference_correctness_loose),
                        ("strict", reference_correctness_strict),
                        ("conc", reference_conciseness),
                    ):
                        b, a = fn(refs, exp), fn(after, exp)
                        if b is None or a is None:
                            continue
                        axes_before[name].append(b)
                        axes_after[name].append(a)
                        if name == "strict" and abs(a - b) > 1e-9:
                            moved.append(
                                f"  {label} {arm} s{s} {rid}: strict {b:.2f} -> {a:.2f} "
                                f"  {refs} -> {after}"
                            )
                    if after != refs and len(examples) < 8:
                        examples.append(
                            f"  {rid} {arm} s{s}: {' '.join(str(x) for x in refs)}"
                            f"  ->  {' '.join(after)}"
                        )

    print(f"comparable row-samples scored: {n_rows_total}")
    print(f"row-samples rewritten by the pass: {n_rows_rewritten} ({len(rows)} distinct rows)")
    print(f"true substitutions: {pairs_total} across {len(rows)} rows")
    print(f"  wire limb IS gold / prose limb IS gold / both / neither: "
          f"{wire_is_gold} / {prose_is_gold} / {both} / {neither}")
    print(f"  legs that served the REWRITTEN row-samples: {dict(legs)}")
    print(f"head set invariant where rewritten: "
          f"{'YES' if head_mismatch == 0 else f'NO ({head_mismatch})'}")
    print(f"reference COUNT invariant where rewritten: "
          f"{'YES' if count_mismatch == 0 else f'NO ({count_mismatch})'}")
    print("\nofficial reference axes (mean over the same rows, real rubric):")
    for name in ("loose", "strict", "conc"):
        b = 100 * sum(axes_before[name]) / len(axes_before[name])
        a = 100 * sum(axes_after[name]) / len(axes_after[name])
        print(f"  ref_{name:6} {b:7.2f} -> {a:7.2f}  ({a - b:+.2f} pp)   n={len(axes_before[name])}")
    if moved:
        print("\nrows whose Ref Strict moved:")
        for line in moved:
            print(line)
    print("\nexamples of the rewrite:")
    for line in examples:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
