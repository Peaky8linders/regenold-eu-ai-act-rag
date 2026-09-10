"""R403 — intelligent rule #8: gold-drop attribution beyond a raw count.

The hard rule stands: a lever that drops a stable gold HEAD on any row is
vetoed. What was dumb was the INSTRUMENT: it counted drops without asking

  1. is this gold entry STABLE? The R388 refkey carries an ``unstable``
     flag — the evaluator's own key marks rows whose expected references
     are not reliably recoverable. A drop of an unstable gold ref is
     noise, not a violation (score_arm already excludes unstable rows
     from the ref axes; the veto now matches that).
  2. what KIND of change happened on the row? A drop can be
       * PRUNED      — B cites strictly less than A (subset), pure loss
       * SUBSTITUTED — B cites something else instead (traded gold X
                       for extra Y)
       * MIXED       — both directions on different refs
     Substitution rows are recoverable by tuning; pruned rows are the
     lever eating references.
  3. is it RECOVERABLE? If B also cites the gold ref's PARENT or a
     SUBPOINT of it, the head is arguable — flagged, not vetoed.
  4. what is the NET? Paired flips in BOTH directions + the axis
     leverage weights give an estimated net-Overall, so a lever that
     loses one gold head while gaining three elsewhere is judged on
     evidence, not panic. (The veto on stable drops remains absolute —
     this estimate informs whether to iterate on the lever, not whether
     to override the veto.)

Usage:
    python -m evals.official.rule8_audit --a score-A.json --b score-B.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Geometric-mean axis leverage in HARD mode: d ln(Overall)/d(axis pp).
#: Derived from the official axis values (score_arm.OFFICIAL["hard"]).
LEVERAGE_HARD = {
    "ref_correctness_loose": 0.0895,
    "ref_correctness_strict": 0.0894,
    "ref_conciseness": 0.0917,
    "ans_correctness_loose": 0.0898,
    "ans_correctness_strict": 0.0899,
    "ans_conciseness": 0.2032,
    "regulatory_tone": 0.0894,
    "resp_speed": 0.0894,
}


def _load_refkey() -> dict[str, dict]:
    path = REPO / "docs" / "measurements" / "r388" / "official_refkey_n110.jsonl"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            out[r["id"]] = r
    return out


def _head(ref: str) -> str:
    return str(ref).split(".")[0]


def _parent(ref: str) -> str | None:
    """Article 24.4 -> Article 24; Annex III.5.d -> Annex III.5; None for heads."""
    parts = str(ref).split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else None


def _related(ref: str) -> set[str]:
    """Parents and descendant-coordinate prefixes that make a drop recoverable."""
    out: set[str] = set()
    head = _head(ref)
    parts = str(ref).split(".")
    for i in range(1, len(parts) + 1):
        out.add(".".join(parts[:i]))
    out.add(head)
    return out


def audit_row(
    qid: str,
    expected: list[str],
    refs_a: list[str],
    refs_b: list[str],
    refkey: dict[str, dict],
) -> dict:
    """Classify one row's gold-drop situation between arm A and arm B.

    The unit of comparison is the DROP DELTA: a head is a "new drop" only
    when arm B drops it AND arm A did NOT. Rows where both arms miss the
    same gold head are pre-existing failures of the arm pair, not the
    lever's doing — the earlier draft of this audit compared B against the
    empty set and flagged those phantom "swaps", which raw-data inspection
    falsified on every flagged row.
    """
    exp_heads = {_head(e) for e in expected or []}
    unstable = bool((refkey.get(qid) or {}).get("unstable"))
    got_a = {_head(r) for r in refs_a or []}
    got_b = {_head(r) for r in refs_b or []}
    drops_a = exp_heads - got_a if exp_heads else set()
    drops_b = exp_heads - got_b if exp_heads else set()
    new_drops = sorted(drops_b - drops_a)
    healed = sorted(drops_a - drops_b)
    if not new_drops:
        return {
            "id": qid,
            "dropped": False,
            "unstable": unstable,
            "new_drops": [],
            "healed": healed,
        }
    classified = []
    for d in new_drops:
        exact_gold = [e for e in (expected or []) if _head(e) == d]
        recoverable = False
        for g in exact_gold:
            rel = _related(g)
            if any(r in rel for r in (refs_b or [])):
                recoverable = True
                break
        kind = "pruned" if set(refs_b or []) < set(refs_a or []) else (
            "substituted" if set(refs_b or []) - set(refs_a or []) else "mixed"
        )
        classified.append(
            {"gold_head": d, "kind": kind, "recoverable": recoverable}
        )
    return {
        "id": qid,
        "dropped": True,
        "unstable": unstable,
        "new_drops": classified,
        "healed": healed,
    }


def audit(
    a_path: Path, b_path: Path
) -> dict:
    from evals.official.paired_ab import AXES, _load_rows, _mean

    refkey = _load_refkey()
    ra, rb = _load_rows(a_path), _load_rows(b_path)
    shared = sorted(set(ra) & set(rb))

    # Axis leverage deltas for the net estimate (paired, per-row).
    from evals.official.paired_ab import _row_axis

    per_axis: dict[str, float] = {}
    for axis in AXES:
        deltas = []
        for qid in shared:
            va = _row_axis(ra[qid], axis)
            vb = _row_axis(rb[qid], axis)
            if va is None or vb is None:
                continue
            deltas.append(vb - va)
        per_axis[axis] = _mean(deltas)

    net_overall_pp = sum(
        LEVERAGE_HARD.get(axis, 0.0) * per_axis.get(axis, 0.0) for axis in AXES
    )

    audits = []
    healed_total = 0
    for qid in shared:
        ea = ra[qid].get("expected_refs") or []
        if not ea:
            continue
        row = audit_row(
            qid, ea, ra[qid].get("refs") or [], rb[qid].get("refs") or [], refkey
        )
        healed_total += len(row.get("healed") or [])
        audits.append(row)

    dropped_rows = [a for a in audits if a["dropped"]]
    stable_drops = [a for a in dropped_rows if not a["unstable"]]
    unstable_drops = [a for a in dropped_rows if a["unstable"]]
    recoverable = [
        a
        for a in dropped_rows
        if any(c["recoverable"] for c in a["new_drops"])
    ]
    kinds: dict[str, int] = {}
    for a in dropped_rows:
        for c in a["new_drops"]:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1

    veto = bool(stable_drops) and not all(
        c["recoverable"]
        for a in stable_drops
        for c in a["new_drops"]
    )

    return {
        "arm_a": str(a_path.name),
        "arm_b": str(b_path.name),
        "rows_compared": len(shared),
        "axis_deltas": per_axis,
        "est_net_overall_pp": round(net_overall_pp, 3),
        "gold_dropped_rows": {
            "total": len(dropped_rows),
            "stable": len(stable_drops),
            "unstable": len(unstable_drops),
            "recoverable_head": len(recoverable),
            "kinds": kinds,
            "healed_in_b": healed_total,
        },
        "stable_drop_rows": [a["id"] for a in stable_drops],
        "unstable_drop_rows": [a["id"] for a in unstable_drops],
        "detail": audits,
        "VERDICT": (
            "VETO (stable, non-recoverable gold head dropped)"
            if veto
            else "PASS (no stable non-recoverable gold-head drops)"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    res = audit(Path(args.a), Path(args.b))
    print(f"\nRULE-8 INTELLIGENT AUDIT (n={res['rows_compared']})")
    print(f"  A={res['arm_a']}  B={res['arm_b']}")
    gd = res["gold_dropped_rows"]
    print(
        f"  NEW dropped rows in B: total {gd['total']}  stable {gd['stable']}"
        f"  unstable {gd['unstable']}  recoverable-head {gd['recoverable_head']}"
        f"  healed-in-B heads {gd.get('healed_in_b', 0)}"
    )
    print(f"  kinds: {gd['kinds']}")
    print(f"  est net Overall: {res['est_net_overall_pp']:+.2f} pp")
    print(f"  {res['VERDICT']}")
    if res["stable_drop_rows"]:
        print(f"  stable drop rows: {res['stable_drop_rows']}")
    if res["unstable_drop_rows"]:
        print(f"  unstable drop rows (noise, not veto): {res['unstable_drop_rows']}")
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
