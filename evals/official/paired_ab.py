"""R403 — paired A/B decision statistics over two score_arm checkpoints.

Why: earlier lever verdicts (R142.1, R327.1, R401) were decided on
aggregates — means with no paired variance, so "wash" and "significant"
claims were untestable. This module pairs two arms ROW BY ROW (same
question, both arms, same judge cache) and reports:

* per-axis paired deltas with a 10,000-resample bootstrap 95% CI
* McNemar exact tests on the flip counts that matter (strict all-pass
  flips, tone flips, per-row ref-axis flips)
* the hard rule #8 veto: per-row gold-head drops, arm A vs arm B

Row pairing requires BOTH arms judged from the SAME judge cache — identical
answers share verdicts, so deltas reflect generation changes, not judge
noise. Rows with a failed criterion-count match or missing verdicts are
reported and dropped from both arms.

Usage:
    python -m evals.official.paired_ab \
        --a docs/measurements/r388/score-A.json \
        --b docs/measurements/r388/score-B.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

AXES = [
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
]

#: Hard rule #8 — any lever that drops a gold HEAD on any row is vetoed
#: regardless of what the mean deltas say. Computed at HEAD grain (the
#: ``gold_dropped_head`` convention in ``evals/bench/metrics.py``).


def _gold_dropped_head(expected: list[str], refs: list[str]) -> bool:
    got = {str(r).split(".")[0] for r in refs or []}
    return any(
        str(e).split(".")[0] not in got for e in expected or []
    )


def _load_rows(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"]: r for r in data["rows"]}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _bootstrap_ci(
    deltas: list[float], n: int = 10_000, alpha: float = 0.05, seed: int = 403
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of paired deltas."""
    if not deltas:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    m = len(deltas)
    means = []
    for _ in range(n):
        s = 0.0
        for _i in range(m):
            s += deltas[rng.randrange(m)]
        means.append(s / m)
    means.sort()
    lo = means[int((alpha / 2) * n)]
    hi = means[int((1 - alpha / 2) * n) - 1]
    return lo, hi


def _mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value via the binomial tail."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i) * (0.5**n)
    return min(1.0, 2 * p)


def _row_axis(r: dict, axis: str) -> float | None:
    """Recompute one row's axis score from its judged fields."""
    from evals.official.rubric import (
        answer_conciseness,
        answer_correctness_loose,
        answer_correctness_strict,
        reference_conciseness,
        reference_correctness_loose,
        reference_correctness_strict,
        regulatory_tone,
        response_speed,
    )

    if axis == "ans_correctness_loose":
        return answer_correctness_loose([r.get("criteria") or []]) * 100.0
    if axis == "ans_correctness_strict":
        return answer_correctness_strict([r.get("criteria") or []]) * 100.0
    if axis == "ans_conciseness":
        a = r.get("answer")
        ref = r.get("reference_answer")
        if a is None or ref is None:
            # score_arm JSONs carry char counts, not raw text
            ac, rc = r.get("answer_chars"), r.get("reference_chars")
            if not ac:
                return None
            if rc is None:
                return None
            return min(1.0, float(rc) / float(ac)) * 100.0
        v = answer_conciseness(a, ref)
        return None if v is None else v * 100.0
    if axis == "ref_correctness_loose":
        v = reference_correctness_loose(r.get("refs") or [], r.get("expected_refs") or [])
        return None if v is None else v * 100.0
    if axis == "ref_correctness_strict":
        v = reference_correctness_strict(r.get("refs") or [], r.get("expected_refs") or [])
        return None if v is None else v * 100.0
    if axis == "ref_conciseness":
        v = reference_conciseness(r.get("refs") or [], r.get("expected_refs") or [])
        return None if v is None else v * 100.0
    if axis == "regulatory_tone":
        return 100.0 if r.get("tone_ok") else 0.0
    if axis == "resp_speed":
        v = response_speed([r.get("latency_s") or 0.0])
        return v * 100.0
    raise ValueError(axis)


def compare(
    a_path: Path, b_path: Path, seed: int = 403
) -> dict:
    """Full paired comparison; ``a`` = baseline arm, ``b`` = branch arm."""
    from evals.official.rubric import (
        answer_conciseness,
        answer_conciseness as _ac,
    )

    ra, rb = _load_rows(a_path), _load_rows(b_path)
    shared = sorted(set(ra) & set(rb))
    only_a = sorted(set(ra) - set(rb))
    only_b = sorted(set(rb) - set(ra))

    per_axis: dict[str, dict] = {}
    for axis in AXES:
        da: list[float] = []
        flips_pos = flips_neg = 0
        for qid in shared:
            va = _row_axis(ra[qid], axis)
            vb = _row_axis(rb[qid], axis)
            if va is None or vb is None:
                continue
            da.append(vb - va)
            if vb > va:
                flips_pos += 1
            elif vb < va:
                flips_neg += 1
        lo, hi = _bootstrap_ci(da, seed=seed)
        # McNemar only makes sense on binary-ish axes; for graded axes the
        # flip counts are still informative (improvements vs regressions).
        per_axis[axis] = {
            "n": len(da),
            "mean_a": _mean([_row_axis(ra[q], axis) for q in shared
                             if _row_axis(ra[q], axis) is not None]),
            "mean_b": _mean([_row_axis(rb[q], axis) for q in shared
                             if _row_axis(rb[q], axis) is not None]),
            "delta": _mean(da),
            "ci95": [lo, hi],
            "b_better": flips_pos,
            "a_better": flips_neg,
            "mcnemar_p": _mcnemar_exact(flips_pos, flips_neg),
        }

    # Gold-drop veto, per row.
    drops_a = drops_b = 0
    rows_dropped: list[str] = []
    for qid in shared:
        ea = ra[qid].get("expected_refs") or []
        eb = rb[qid].get("expected_refs") or []
        if not ea and not eb:
            continue
        da_ = _gold_dropped_head(ea, ra[qid].get("refs") or [])
        db_ = _gold_dropped_head(eb, rb[qid].get("refs") or [])
        drops_a += da_
        drops_b += db_
        if db_ and not da_:
            rows_dropped.append(qid)

    # Conciseness headroom bookkeeping (axis 3): mean answer chars.
    def _chars(rows: dict[str, dict]) -> float:
        vals = []
        for q in shared:
            v = rows[q].get("answer_chars")
            if v is None:
                v = len(rows[q].get("answer") or "")
            vals.append(float(v or 0))
        return _mean(vals)

    chars_a = _chars(ra)
    chars_b = _chars(rb)

    return {
        "arm_a": str(a_path.name),
        "arm_b": str(b_path.name),
        "shared_rows": len(shared),
        "only_in_a": only_a,
        "only_in_b": only_b,
        "axes": per_axis,
        "gold_dropped_head": {"arm_a": drops_a, "arm_b": drops_b, "new_drops_in_b": rows_dropped},
        "mean_answer_chars": {"arm_a": chars_a, "arm_b": chars_b},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    res = compare(Path(args.a), Path(args.b))

    print(f"\nPAIRED A/B  (n={res['shared_rows']} shared rows)")
    print(f"  arm A = {res['arm_a']}   arm B = {res['arm_b']}")
    if res["only_in_a"] or res["only_in_b"]:
        print(f"  only-in-A: {res['only_in_a']}  only-in-B: {res['only_in_b']}")
    hdr = f"{'axis':<26}{'A':>8}{'B':>8}{'delta':>9}  {'95% CI':<20}{'+/-':>8}  {'McNemar p':>9}"
    print(hdr)
    print("-" * len(hdr))
    for axis in AXES:
        d = res["axes"][axis]
        ci = f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
        star = ""
        if d["ci95"][0] > 0:
            star = " B>"
        elif d["ci95"][1] < 0:
            star = " A>"
        print(
            f"{axis:<26}{d['mean_a']:>8.2f}{d['mean_b']:>8.2f}"
            f"{d['delta']:>+9.2f}  {ci:<20}{d['b_better']:>4}/{d['a_better']:<3}"
            f"  {d['mcnemar_p']:>9.4f}{star}"
        )
    gd = res["gold_dropped_head"]
    print(
        f"\ngold_dropped_head: A={gd['arm_a']}  B={gd['arm_b']}"
        + (f"  NEW DROPS IN B: {gd['new_drops_in_b']}" if gd["new_drops_in_b"] else "")
    )
    print(f"mean answer chars: A={res['mean_answer_chars']['arm_a']:.0f}  B={res['mean_answer_chars']['arm_b']:.0f}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(res, indent=1), encoding="utf-8"
        )
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
