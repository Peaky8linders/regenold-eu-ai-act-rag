"""R425 — the targeted live read (judge-free).

WHY THIS IS THE SMART SAMPLE, AND WHAT IT CAN AND CANNOT SAY. The three REFERENCE
axes of the official board are computed entirely from the emitted ``references``
and the gold key — no LLM involved — and R425's lever provably cannot change the
ANSWER: it is a route pass that runs after Stage-2 and rewrites list entries only
(asserted byte-identical on a live request in
``tests/test_r425_wire_grain_grounding.py``). Two consequences follow, and this
file is built around them:

1. A cross-arm comparison at ``--repeats 1`` is **not** a lever measurement. Each
   arm draws its own Stage-2 sample, so the two wires differ because the DRAWS
   differ. The valid pairing is **within a draw**: take the wire a row actually
   shipped and compare it against the pass applied to *that same* answer and wire
   (``_ground_wire_subpoints`` is a pure function of them). That counterfactual is
   paired by construction — nothing varies but the pass.
2. Non-vacuity is therefore proven per ARM, not across arms. If the OFF arm's
   recorded wires are all still rewritable, the OFF wire really is pre-pass; if
   the ON arm's are all already fixed, the shipped wire **is** the pass's output,
   i.e. the call site fired on the live transport. An inert call site would leave
   both arms rewritable.

The POPULATION-level axis numbers come from the replay over the R424 gate's six
checkpoints (336 comparable row-samples of real draws, identical-draw pairing for
every one) in ``wire_grain_grounding_probe.py``. This leg exists to show the pass
reaches the LIVE wire, with live Stage-2 prose, and is harmless there.

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r425.live_paired_read
"""
from __future__ import annotations

import collections
import json
import re
import statistics
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

OUT = Path(__file__).resolve().parent
RESULTS = REPO / "evals" / "bench" / "results"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "r425-live"
ARMS = ("A", "B")
REPEATS = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def _rows(arm: str, sample: int = 0) -> dict[str, dict[str, Any]]:
    stem = f"official-{LABEL}-{arm}-hard"
    path = RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")
    if not path.exists():
        raise SystemExit(f"missing checkpoint {path.name}")
    return {
        r["id"]: r
        for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())
    }


def _graded(row: dict[str, Any]) -> tuple[str, list[str], str]:
    """(answer, references, turn) for the turn the board grades.

    All-or-nothing: pairing a pushback ref list with a turn-1 answer would pair
    prose with references from a different turn.
    """
    if row.get("pushback_refs") or row.get("pushback_answer"):
        return (
            row.get("pushback_answer") or "",
            [str(x) for x in (row.get("pushback_refs") or [])],
            "pushback",
        )
    return (
        row.get("turn1_answer") or row.get("pred_answer") or "",
        [str(x) for x in (row.get("turn1_refs") or row.get("pred_refs") or [])],
        "turn1",
    )


def _head_of(ref: str) -> str:
    m = re.match(r"\s*(Article\s+\d{1,3}|Annex\s+[IVXLC]+)", str(ref), re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip().lower() if m else str(ref).lower()


def _heads(refs: list[str]) -> set[str]:
    return {_head_of(r) for r in refs or []}


def _applied_pairs(refs: list[str], after: list[str]) -> list[tuple[str, str]]:
    """The (from, to) pairs the pass ACTUALLY applied on this live draw.

    Read off the pass's own output rather than re-derived from its guards: the
    rewrite is order-preserving and 1:1, so a positional diff IS the applied set.
    """
    if len(refs) != len(after):
        return []
    return [
        (str(a).strip(), str(b).strip())
        for a, b in zip(refs, after, strict=True)
        if str(a).strip() != str(b).strip()
    ]


def _gold_matches(leaf: str, expected: list[str]) -> bool:
    low = leaf.lower()
    return any(
        low == e or low.startswith(e + ".") or e.startswith(low + ".") for e in expected
    )


def main() -> int:
    gold = {
        r["id"]: r
        for r in (json.loads(x) for x in GOLD.read_text(encoding="utf-8").splitlines() if x.strip())
    }
    # Pool every generation of both arms: the reachability read is per (row, draw)
    # and is paired within a draw, so more generations is more evidence, not
    # duplication. The cross-arm descriptive read needs the arms to line up, so it
    # uses sample 0 only.
    rows_a = {r["id"]: r for s in range(REPEATS) for r in _rows("A", s).values()}
    rows_b = {r["id"]: r for s in range(REPEATS) for r in _rows("B", s).values()}
    if REPEATS > 1:
        # ``_graded`` keys by row id, so keep the pooled rows under a draw-qualified
        # key to avoid one generation overwriting another.
        rows_a = {
            f"{r['id']}#s{s}": r
            for s in range(REPEATS)
            for r in _rows("A", s).values()
        }
        rows_b = {
            f"{r['id']}#s{s}": r
            for s in range(REPEATS)
            for r in _rows("B", s).values()
        }
    payload_path = RESULTS / f"official-{LABEL}.json"
    payload = (
        json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else {}
    )

    per_row: list[dict[str, Any]] = []
    for rid in sorted(set(rows_a) & set(rows_b)):
        ra, rb = rows_a[rid], rows_b[rid]
        gold_id = rid.split("#")[0]
        ans_a, refs_a, turn = _graded(ra)
        ans_b, refs_b, _ = _graded(rb)
        exp = [str(x).lower() for x in ((gold.get(gold_id) or {}).get("expected_refs") or [])]
        entry: dict[str, Any] = {
            "id": rid,
            "turn": turn,
            "expected": exp,
            "answer_identical": ans_a == ans_b,
            "served_a": (ra.get("provenance") or {}).get("stage2_served_by"),
            "served_b": (rb.get("provenance") or {}).get("stage2_served_by"),
        }
        # ---- the valid pairing: each arm against the pass applied to ITS OWN draw
        for arm, ans, refs in (("a", ans_a, refs_a), ("b", ans_b, refs_b)):
            after = _ground_wire_subpoints(ans, refs)
            entry[f"wire_{arm}"] = refs
            entry[f"passed_{arm}"] = after
            entry[f"rewritable_{arm}"] = after != refs
            entry[f"head_invariant_{arm}"] = _heads(refs) == _heads(after)
            entry[f"count_invariant_{arm}"] = len(refs) == len(after)
            entry[f"gold_heads_dropped_{arm}"] = sorted(_heads(refs) - _heads(exp))
            for key, fn in (
                ("loose", reference_correctness_loose),
                ("strict", reference_correctness_strict),
                ("conc", reference_conciseness),
            ):
                shipped, passed = fn(refs, exp), fn(after, exp)
                entry[f"{key}_shipped_{arm}"] = shipped
                entry[f"{key}_passed_{arm}"] = passed
                if shipped is not None and passed is not None:
                    entry[f"{key}_gain_{arm}"] = passed - shipped
            subs = _applied_pairs(refs, after)
            entry[f"substitutions_{arm}"] = len(subs)
            entry[f"sub_wire_gold_{arm}"] = sum(
                1 for w, _ in subs if _gold_matches(w, exp)
            )
            entry[f"sub_prose_gold_{arm}"] = sum(
                1 for _, p in subs if _gold_matches(p, exp)
            )
        per_row.append(entry)

    def _mean_pct(vals: list[float]) -> float | None:
        return statistics.fmean(vals) * 100.0 if vals else None

    def _col(key: str, arm: str | None = None) -> list[float]:
        del arm  # arms are pooled for the within-draw reads
        return [r[key] for r in per_row if r.get(key) is not None]

    served = collections.Counter(
        [r["served_a"] for r in per_row] + [r["served_b"] for r in per_row]
    )
    report: dict[str, Any] = {
        "label": LABEL,
        "rows": len(per_row),
        "lever_slot": payload.get("lever_slot"),
        "lever_changes_wire": payload.get("lever_changes_wire"),
        "gate": payload.get("gate"),
        "served": dict(served),
        "answer_identical_rows": sum(1 for r in per_row if r["answer_identical"]),
        # cross-arm: descriptive only (independent draws at --repeats 1)
        "cross_arm_reference_axes": {
            key: {
                "A": _mean_pct(_col(f"{key}_shipped_a", "a")),
                "B": _mean_pct(_col(f"{key}_shipped_b", "b")),
            }
            for key in ("loose", "strict", "conc")
        },
        # within-draw counterfactual: the lever's own effect, paired by construction
        "within_draw_counterfactual": {
            key: {
                "shipped": _mean_pct(_col(f"{key}_shipped_a") + _col(f"{key}_shipped_b")),
                "passed": _mean_pct(_col(f"{key}_passed_a") + _col(f"{key}_passed_b")),
                "gain_pp": _mean_pct(_col(f"{key}_gain_a") + _col(f"{key}_gain_b")),
            }
            for key in ("loose", "strict", "conc")
        },
        "reachability": {
            arm: {
                "rows_rewritable": sum(1 for r in per_row if r[f"rewritable_{arm}"]),
                "rows": len(per_row),
                "substitutions": sum(r[f"substitutions_{arm}"] for r in per_row),
                "sub_wire_gold": sum(r[f"sub_wire_gold_{arm}"] for r in per_row),
                "sub_prose_gold": sum(r[f"sub_prose_gold_{arm}"] for r in per_row),
                "head_invariant": sum(1 for r in per_row if r[f"head_invariant_{arm}"]),
                "count_invariant": sum(1 for r in per_row if r[f"count_invariant_{arm}"]),
                "gold_heads_dropped": sum(
                    len(r[f"gold_heads_dropped_{arm}"]) for r in per_row
                ),
                # Must equal ``gold_heads_dropped`` exactly: the pass is
                # head-preserving, so it cannot change a gold-head drop. A
                # mismatch here is a wiring bug, not a trade.
                "gold_heads_dropped_after_pass": sum(
                    len(_heads(r[f"passed_{arm}"]) - _heads(r["expected"]))
                    for r in per_row
                ),
            }
            for arm in ("a", "b")
        },
        "per_row": per_row,
    }
    (OUT / "live_paired_read.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    def _f(v: float | None, width: int = 9, sign: bool = False) -> str:
        if v is None:
            return f"{'n/a':>{width}}"
        return f"{v:>+{width}.2f}" if sign else f"{v:>{width}.2f}"

    print("=" * 88)
    print(f"R425 targeted live read  |  label={LABEL}  rows={len(per_row)}")
    print("=" * 88)
    print(f"lever_slot={report['lever_slot']}  lever_changes_wire={report['lever_changes_wire']}")
    print(f"stage2 leg that served the rows: {report['served']}")
    print(
        "answer byte-identical across arms: "
        f"{report['answer_identical_rows']}/{len(per_row)}"
        "   <-- 0 means the two arms are INDEPENDENT draws (--repeats 1), so the"
    )
    print(
        "    cross-arm numbers below are DESCRIPTIVE, not a lever estimate."
        "  The lever's own"
    )
    print(
        "    effect is read WITHIN each draw (the pass applied to the same"
        " answer+wire)."
    )
    print()
    print("REACHABILITY — is the call site firing on the live route?")
    for arm, label in (("a", "OFF arm (recorded wire)"), ("b", "ON arm (shipped wire)")):
        r = report["reachability"][arm]
        print(
            f"  {label:<26} rewritable {r['rows_rewritable']}/{r['rows']}   "
            f"substitutions {r['substitutions']}   "
            f"head-invariant {r['head_invariant']}/{r['rows']}   "
            f"count-invariant {r['count_invariant']}/{r['rows']}   "
            f"gold heads dropped {r['gold_heads_dropped']} "
            f"(after the pass: {r['gold_heads_dropped_after_pass']})"
        )
        if r["substitutions"]:
            print(
                f"      of those applied rewrites: the limb we shipped was gold "
                f"{r['sub_wire_gold']}, the limb we ship instead is gold "
                f"{r['sub_prose_gold']} (limb- or head-level)"
            )
    print()
    print("WITHIN-DRAW COUNTERFACTUAL on these live rows (paired by construction):")
    print(f"  {'axis':<12}{'shipped':>9}{'passed':>9}{'gain pp':>10}")
    for key, vals in report["within_draw_counterfactual"].items():
        print(
            f"  ref_{key:<8}{_f(vals['shipped'])}{_f(vals['passed'])}"
            f"{_f(vals['gain_pp'], sign=True)}"
        )
    print()
    print("CROSS-ARM (descriptive only — independent draws):")
    print(f"  {'axis':<12}{'A off':>9}{'B on':>9}{'delta':>10}")
    for key, vals in report["cross_arm_reference_axes"].items():
        delta = (
            vals["B"] - vals["A"] if vals["A"] is not None and vals["B"] is not None else None
        )
        print(f"  ref_{key:<8}{_f(vals['A'])}{_f(vals['B'])}{_f(delta, sign=True)}")
    print()
    print("  per row (the turn the board grades):")
    for r in per_row:
        print(
            f"    {r['id']:<8} rewritable {int(r['rewritable_a'])}/{int(r['rewritable_b'])}"
            f"  served={r['served_a']}/{r['served_b']}"
        )
        for arm in ("a", "b"):
            if r[f"rewritable_{arm}"]:
                print(f"      {arm.upper()}: {' '.join(r[f'wire_{arm}'])}")
                print(f"         -> {' '.join(r[f'passed_{arm}'])}")
    print(f"\nwrote {OUT / 'live_paired_read.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
