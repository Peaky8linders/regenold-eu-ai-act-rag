"""R440 — score and decide the branch-guard hard-cluster gate.

The gate draws six passes (3 samples x 2 arms) over the 21 frozen cluster rows
with ``evals.regenold.run_official_batch``:

    --baseline-env REGENOLD_GROUNDED_BRANCH_GUARDS=0   (arm A)
    --branch-env   REGENOLD_GROUNDED_BRANCH_GUARDS=1   (arm B)

This driver consumes those checkpoints and produces the decision the round
pre-registered in ``PREFLIGHT.md``:

 1. ``score_arm`` on each checkpoint (reconstructed official rubric: the
    reference axes against the n=110 refkey, plus the judge for answer
    correctness and tone).
 2. ``paired_ab`` on each A/B sample pair — row pairings on the same judge
    cache, paired bootstrap 95% CIs, exact McNemar, gold-head veto.
 3. A per-row MEDIAN read across the three samples (one flaky sample must not
    decide the lever), then the refuse rule:

        REFUSE (keep the lever OFF) if ANY of
          * any row gains a gold-head drop in arm B (per-row, any sample)
          * ans_correctness_loose / ans_correctness_strict median delta < 0
          * ref_correctness_loose median delta < 0

        SHIP ON only if the refuse rule is clean AND at least one guard-relevant
        axis has a per-sample CI that excludes zero in B's favour on >=2 of 3
        samples.

Never scored concurrently with a live run: the judge and the gate's Stage-2
primary both drive the one local wrapper CLI (R440b died of exactly that).

Usage:
    python docs/measurements/r440/branch_cluster_gate.py --score
    python docs/measurements/r440/branch_cluster_gate.py --compare
    python docs/measurements/r440/branch_cluster_gate.py --verdict
    python docs/measurements/r440/branch_cluster_gate.py --score --compare --verdict
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RESULTS = REPO / "evals" / "bench" / "results"
SCORES = REPO / "docs" / "measurements" / "r388"
OUT = REPO / "docs" / "measurements" / "r440"

#: R436's judge identity, reused so the answer axes are read on the same
#: instrument as the published board. Bedrock is a genuinely concurrent
#: endpoint, so --workers can be >1 (the local wrapper could not).
JUDGE_PROVIDER = "bedrock"
JUDGE_MODEL = "qwen.qwen3-235b-a22b-2507-v1:0"
JUDGE_CACHE = OUT / "judge-cache-r440-bedrock.jsonl"

SAMPLE_SUFFIX = ["", ".r1", ".r2"]

#: Rows whose arm A and arm B inputs are byte-identical, measured in the
#: pre-flight against the guard text: a null here is "the router never fired".
VACUOUS: set[str] = set()

REFUSE_AXES = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ref_correctness_loose",
)
SHIP_AXES = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
)


def ckpt(label: str, arm: str, sample: int) -> Path:
    return RESULTS / f"official-{label}-{arm}-hard{SAMPLE_SUFFIX[sample]}.ckpt.jsonl"


def score_json(label: str, arm: str, sample: int) -> Path:
    return SCORES / f"score-{label}-{arm}-hard-s{sample}-hard.json"


def paired_json(label: str, sample: int) -> Path:
    return OUT / f"paired-{label}-s{sample}.json"


def run_score(label: str, arm: str, sample: int, workers: int, repeats: int) -> int:
    src = ckpt(label, arm, sample)
    if not src.exists():
        print(f"missing checkpoint: {src}")
        return 1
    # score_arm names its artifact from the label, so the arm/sample ride on it.
    tag = f"{label}-{arm}-hard-s{sample}"
    cmd = [
        sys.executable, "-m", "evals.official.score_arm",
        "--ckpt", str(src), "--label", tag, "--mode", "hard",
        "--workers", str(workers), "--repeats", str(repeats),
        "--judge-provider", JUDGE_PROVIDER, "--judge-model", JUDGE_MODEL,
        # One shared cache for both arms: paired_ab requires it, and identical
        # answers must not be judged twice.
        "--cache-file", str(JUDGE_CACHE),
    ]
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


def run_compare(label: str, samples: int) -> int:
    rc = 0
    for s in range(samples):
        a, b = score_json(label, "A", s), score_json(label, "B", s)
        if not (a.exists() and b.exists()):
            print(f"missing score artifact for sample {s}: {a.exists()=} {b.exists()=}")
            rc = 1
            continue
        cmd = [
            sys.executable, "-m", "evals.official.paired_ab",
            "--a", str(a), "--b", str(b), "--out", str(paired_json(label, s)),
        ]
        print("+", " ".join(cmd), flush=True)
        rc |= subprocess.call(cmd, cwd=str(REPO))
    return rc


def _rows(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["rows"]}


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return float("nan")
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2


def _axis_value(row: dict, axis: str) -> float | None:
    from evals.official.paired_ab import _row_axis  # noqa: PLC0415

    try:
        return _row_axis(row, axis)
    except Exception:
        return None


def pooled(label: str, samples: int, n_boot: int = 10_000, seed: int = 440) -> dict:
    """Pooled paired read over all samples, bootstrapped BY ROW.

    The R440 design draws %d samples per row, so the 21 x %d paired
    observations are not independent: three of them share a question and a
    retrieved context. Resampling ROWS (with their samples) is the honest
    interval; treating every observation as independent would narrow it
    artificially. Median-across-rows is not used for the decision because on
    the binary axes (criteria all-pass, gold heads present) a median of a 0/1
    column is degenerate and reads 100/100 in both arms.
    """
    import random  # noqa: PLC0415

    from evals.official.paired_ab import AXES, _mcnemar_exact  # noqa: PLC0415

    rows_a = [_rows(score_json(label, "A", s)) for s in range(samples)]
    rows_b = [_rows(score_json(label, "B", s)) for s in range(samples)]
    ids = sorted(set(rows_a[0]) & set(rows_b[0]))

    out: dict[str, dict] = {}
    for axis in AXES:
        per_row: list[list[float]] = []
        for i in ids:
            ds = []
            for s in range(samples):
                va, vb = (_axis_value(rows_a[s][i], axis), _axis_value(rows_b[s][i], axis))
                if va is None or vb is None:
                    continue
                ds.append(vb - va)
            if ds:
                per_row.append(ds)
        flat = [d for ds in per_row for d in ds]
        if not flat:
            out[axis] = {"n": 0}
            continue
        rng = random.Random(seed)
        means = []
        for _ in range(n_boot):
            acc = []
            for _i in range(len(per_row)):
                ds = per_row[rng.randrange(len(per_row))]
                acc.extend(ds)
            means.append(sum(acc) / len(acc))
        means.sort()
        lo = means[int(0.025 * n_boot)]
        hi = means[int(0.975 * n_boot) - 1]
        better_b = sum(1 for d in flat if d > 0)
        better_a = sum(1 for d in flat if d < 0)
        out[axis] = {
            "n": len(flat),
            "delta": sum(flat) / len(flat),
            "ci95": [lo, hi],
            "b_better": better_b,
            "a_better": better_a,
            "mcnemar_p": _mcnemar_exact(better_b, better_a),
        }
    # unpaired reference read, for the record
    out["_mean_answer_chars"] = {
        "a": _mean_chars(rows_a, ids),
        "b": _mean_chars(rows_b, ids),
    }
    return out


def per_row(label: str, samples: int) -> None:
    """Print the row-level read the round pre-registered: no netting over rows.

    Also the non-vacuity check — if the two arms' answers were identical the
    ON arm's guard text never reached the payload and every delta is a null of
    a different kind.
    """
    from evals.official.paired_ab import _gold_dropped_head  # noqa: PLC0415

    rows_a = [_rows(score_json(label, "A", s)) for s in range(samples)]
    rows_b = [_rows(score_json(label, "B", s)) for s in range(samples)]
    ids = sorted(set(rows_a[0]) & set(rows_b[0]))

    ident = sum(1 for s in range(samples) for i in ids
                if (rows_a[s][i].get("answer") or "") == (rows_b[s][i].get("answer") or ""))
    total = samples * len(ids)
    print(f"\nNON-VACUITY: {total - ident}/{total} pairs have distinct arm A/B answer text "
          f"({ident} identical)")

    print("\nPER-ROW READ (no netting over rows)")
    hdr = (f"{'id':<9}{'ansL A/B':>12}{'ansS A/B':>12}{'refS A/B':>12}"
           f"{'conc A/B':>14}{'chars A->B':>14}  notes")
    print(hdr)
    print("-" * len(hdr))
    for i in ids:
        def _pr(axis: str, rid: str = i) -> tuple[float, float]:
            va = [_axis_value(rows_a[s][rid], axis) for s in range(samples)]
            vb = [_axis_value(rows_b[s][rid], axis) for s in range(samples)]
            return (_median([v for v in va if v is not None]),
                    _median([v for v in vb if v is not None]))

        aL, bL = _pr("ans_correctness_loose")
        aS, bS = _pr("ans_correctness_strict")
        aR, bR = _pr("ref_correctness_strict")
        aC, bC = _pr("ans_conciseness")
        ca = _median([len(rows_a[s][i].get("answer") or "") for s in range(samples)])
        cb = _median([len(rows_b[s][i].get("answer") or "") for s in range(samples)])
        notes = []
        drops = []
        for s in range(samples):
            eb = rows_b[s][i].get("expected_refs") or []
            if eb and _gold_dropped_head(eb, rows_b[s][i].get("refs") or []):
                drops.append(f"dropB-s{s}")
        if drops:
            notes.append(",".join(drops))
        if bR < aR:
            notes.append("refS-down")
        if bS < aS:
            notes.append("ansS-down")
        if bL < aL:
            notes.append("ansL-down")
        if abs(bC - aC) >= 10:
            notes.append("conc-change")
        print(f"{i:<9}{aL:>6.0f}/{bL:<5.0f}{aS:>6.0f}/{bS:<5.0f}{aR:>6.0f}/{bR:<5.0f}"
              f"{aC:>7.1f}/{bC:<6.1f}{ca:>7.0f}->{cb:<6.0f}  {','.join(notes) or 'tie'}")


def _mean_chars(rows: list[dict[str, dict]], ids: list[str]) -> float:
    vals = [len(rows[s][i].get("answer") or "") for s in range(len(rows)) for i in ids if i in rows[s]]
    return sum(vals) / len(vals) if vals else float("nan")


def verdict(label: str, samples: int) -> int:
    from evals.official.paired_ab import AXES, _gold_dropped_head  # noqa: PLC0415

    per_sample = {}
    for s in range(samples):
        p = paired_json(label, s)
        if not p.exists():
            print(f"missing paired artifact: {p}")
            return 2
        per_sample[s] = json.loads(p.read_text(encoding="utf-8"))

    # ---- per-row medians across samples -------------------------------------
    rows_a = [_rows(score_json(label, "A", s)) for s in range(samples)]
    rows_b = [_rows(score_json(label, "B", s)) for s in range(samples)]
    ids = sorted(set().union(*[set(r) for r in rows_a], *[set(r) for r in rows_b]))
    ids = [i for i in ids if all(i in r for r in rows_a + rows_b)]

    print(f"\nPER-ROW MEDIANS ACROSS {samples} SAMPLES  (n={len(ids)} rows)")
    hdr = f"{'axis':<26}{'A':>9}{'B':>9}{'delta':>9}{'B better':>10}{'A better':>10}"
    print(hdr)
    print("-" * len(hdr))
    med = {}
    for axis in AXES:
        da, db = [], []
        better_b = better_a = 0
        for i in ids:
            va = _median([v for v in (_axis_value(r[i], axis) for r in rows_a) if v is not None])
            vb = _median([v for v in (_axis_value(r[i], axis) for r in rows_b) if v is not None])
            if va != va or vb != vb:
                continue
            da.append(va)
            db.append(vb)
            if vb > va:
                better_b += 1
            elif vb < va:
                better_a += 1
        med[axis] = {"a": _median(da), "b": _median(db), "delta": _median(db) - _median(da)
                     if da and db else float("nan"),
                     "b_better": better_b, "a_better": better_a}
        m = med[axis]
        print(f"{axis:<26}{m['a']:>9.2f}{m['b']:>9.2f}{m['delta']:>+9.2f}"
              f"{better_b:>10}{better_a:>10}")

    # ---- gold-head veto, per row, union over samples ------------------------
    new_drops: dict[str, list[int]] = {}
    for s in range(samples):
        ra, rb = rows_a[s], rows_b[s]
        for i in ids:
            ea = ra[i].get("expected_refs") or []
            eb = rb[i].get("expected_refs") or []
            if not ea and not eb:
                continue
            da_ = _gold_dropped_head(ea, ra[i].get("refs") or [])
            db_ = _gold_dropped_head(eb, rb[i].get("refs") or [])
            if db_ and not da_:
                new_drops.setdefault(i, []).append(s)

    # ---- per-sample CIs -----------------------------------------------------
    print("\nPER-SAMPLE PAIRED CIs")
    hdr2 = f"{'axis':<26}" + "".join(f"{f's{s} delta [95% CI]':>30}" for s in range(samples))
    print(hdr2)
    print("-" * len(hdr2))
    for axis in AXES:
        cells = []
        for s in range(samples):
            d = per_sample[s]["axes"][axis]
            cells.append(f"{d['delta']:>+7.2f} [{d['ci95'][0]:+.1f},{d['ci95'][1]:+.1f}]")
        print(f"{axis:<26}" + "".join(f"{c:>30}" for c in cells))

    pool = pooled(label, samples)
    print("\nPOOLED PAIRED READ (row-clustered bootstrap, all samples)")
    hdr3 = f"{'axis':<26}{'n':>5}{'delta':>9}{'95% CI (row-clustered)':>28}{'B/A flips':>12}{'McNemar p':>11}"
    print(hdr3)
    print("-" * len(hdr3))
    for axis in AXES:
        d = pool[axis]
        if not d.get("n"):
            print(f"{axis:<26}{'--':>5}{'no data':>9}")
            continue
        star = " B>" if d["ci95"][0] > 0 else (" A>" if d["ci95"][1] < 0 else "")
        ci_s = "[{:+.2f}, {:+.2f}]".format(d["ci95"][0], d["ci95"][1])
        flips = f"{d['b_better']}/{d['a_better']}"
        print(f"{axis:<26}{d['n']:>5}{d['delta']:>+9.2f}{ci_s:>28}{flips:>12}"
              f"{d['mcnemar_p']:>11.4f}{star}")
    mc = pool["_mean_answer_chars"]
    print(f"mean answer chars: A={mc['a']:.0f}  B={mc['b']:.0f}")
    if VACUOUS:
        print(f"vacuous rows (byte-identical arms, read as nulls): {sorted(VACUOUS)}")

    # ---- the pre-registered rule -------------------------------------------
    print("\n" + "=" * 88)
    refuse = []
    if new_drops:
        refuse.append(f"gold-head drops in B on {len(new_drops)} row(s): "
                      f"{ {k: v for k, v in sorted(new_drops.items())} }")
    for axis in REFUSE_AXES:
        neg_samples = [s for s in range(samples)
                       if per_sample[s]["axes"][axis]["delta"] < 0]
        if (pool[axis].get("n") and pool[axis]["delta"] < 0) or neg_samples:
            refuse.append(
                f"{axis} regression: pooled delta {pool[axis]['delta']:+.2f} pp, "
                f"negative in sample(s) {neg_samples}"
            )

    # A win needs BOTH reads: the pooled row-clustered CI off zero, and the
    # same direction on >=2 of the 3 samples. Either alone is too easy to buy.
    pooled_pos = sorted(a for a in SHIP_AXES
                        if pool[a].get("n") and pool[a]["ci95"][0] > 0)
    per_sample_pos = sorted(a for a in SHIP_AXES
                            if sum(1 for s in range(samples)
                                   if per_sample[s]["axes"][a]["ci95"][0] > 0) >= 2)
    positive = sorted(set(pooled_pos) & set(per_sample_pos))

    per_row(label, samples)

    total_a = sum(per_sample[s]["gold_dropped_head"]["arm_a"] for s in range(samples))
    total_b = sum(per_sample[s]["gold_dropped_head"]["arm_b"] for s in range(samples))
    print(f"gold_dropped_head across samples: A={total_a}  B={total_b}")
    print(f"pooled CI excludes 0 in B's favour: {pooled_pos or 'none'}")
    print(f"per-sample CI excludes 0 in B's favour on >=2/3 samples: {per_sample_pos or 'none'}")
    print(f"guard-relevant axes satisfying BOTH: {positive or 'none'}")

    if refuse:
        print("VERDICT: REFUSE — keep REGENOLD_GROUNDED_BRANCH_GUARDS OFF")
        for r in refuse:
            print(f"  * {r}")
        code = 1
    elif positive:
        print("VERDICT: SHIP ON — refuse rule clean and B wins on "
              f"{positive} under both reads")
        code = 0
    else:
        print("VERDICT: NO WIN — refuse rule clean but no axis separates from zero; "
              "leave the lever OFF (no measured gain to ship)")
        code = 0
    print("=" * 88)
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="r440c-branch-cluster")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--verdict", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-score even if the artifact exists")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    if a.score:
        for s in range(a.samples):
            for arm in ("A", "B"):
                if score_json(a.label, arm, s).exists() and not a.force:
                    print(f"skip (exists): {score_json(a.label, arm, s).name}")
                    continue
                rc |= run_score(a.label, arm, s, a.workers, a.repeats)
    if a.compare:
        rc |= run_compare(a.label, a.samples)
    if a.verdict:
        rc |= verdict(a.label, a.samples)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
