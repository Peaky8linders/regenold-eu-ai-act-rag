"""R442 — score and decide the keep-contract precision-floor gate.

R447 — re-homed from the uncommitted R442 copy in the shared checkout so the
never-judged R442 draws could be scored. The artefact directory and the
judge-cache name changed, and one defect was fixed: the verdict read
``r440.AXES``, which the R440 driver never defines (``AXES`` lives in
``evals.official.paired_ab``), so the script had never reached a verdict. The
rows, the arms and the pre-registered verdict rule below are the R442 text,
unedited.

Gate draws (3 samples x 2 arms) over 14 frozen rows — the 12 rows the R436 judge
fails plus the 2 passing rows the floor keeps as real fires (rg_057, rg_071) —
with ``evals.regenold.run_official_batch``:

    --baseline-env REGENOLD_PUSHBACK_KEEP_CONTRACT=0                      (arm A)
    --branch-env   REGENOLD_PUSHBACK_KEEP_CONTRACT=1 \
                   REGENOLD_KEEP_MIN_GAPS=2                               (arm B)

Reuses the R440 driver's validated machinery (``score_arm`` per checkpoint with
the R436 Bedrock judge identity, ``paired_ab`` per sample, the row-clustered
pooled bootstrap) by importing it and redirecting its artifact paths. The
verdict rule is the keep lever's own, pre-registered before the run:

    REFUSE (keep the contract OFF) if
      * any row gains a gold-head drop in arm B (per row, any sample), or
      * ans_correctness_loose / ans_correctness_strict / ref_correctness_loose
        regress (pooled delta < 0, or negative in any sample).

    SHIP ON if refuse is clean AND ans_correctness_strict separates: the pooled
    row-clustered 95 % CI excludes zero in B's favour AND the same direction on
    >= 2 of 3 samples. Correctness recovery is the lever's whole point — a
    conciseness-only win is NOT a win here.

    NO WIN otherwise (lever stays OFF; a null is recorded as a null).

Never scored concurrently with a live Stage-2 run (one local wrapper CLI; the
R440b outage taught this).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_OUT = REPO / "docs" / "measurements" / "r447"
_LABEL = "r442-keep-floor"
FAILING_COHORT = (
    "rg_035", "rg_036", "rg_037", "rg_062", "rg_069", "rg_075",
    "rg_085", "rg_087", "rg_088", "rg_089", "rg_091", "rg_103",
)


def _load_r440():
    spec = importlib.util.spec_from_file_location(
        "r440_gate", REPO / "docs" / "measurements" / "r440" / "branch_cluster_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=_LABEL)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--verdict", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-score even if the artifact exists")
    a = ap.parse_args()

    r440 = _load_r440()
    # Redirect every artifact path to this round's directory, including the
    # judge cache (a shared cache is required for paired judging; a r442 cache
    # keeps the round self-contained and replayable).
    r440.OUT = _OUT
    r440.JUDGE_CACHE = _OUT / "judge-cache-r447-keep-floor-bedrock.jsonl"

    rc = 0
    if a.score:
        for arm in ("A", "B"):
            for s in range(a.samples):
                out = r440.score_json(a.label, arm, s)
                if out.exists() and not a.force:
                    print(f"score exists, skipping: {out}")
                    continue
                rc |= r440.run_score(a.label, arm, s, a.workers, a.repeats)
    if a.compare:
        rc |= r440.run_compare(a.label, a.samples)
    if a.verdict:
        rc |= keep_verdict(r440, a.label, a.samples)
    return rc


def failing_cohort_criteria(r440, label: str, samples: int) -> dict:
    """Failed-criterion count per failing row, A vs B, medians across samples."""
    rows_a = [r440._rows(r440.score_json(label, "A", s)) for s in range(samples)]
    rows_b = [r440._rows(r440.score_json(label, "B", s)) for s in range(samples)]
    out: dict[str, dict] = {}
    for rid in FAILING_COHORT:
        if rid not in rows_a[0]:
            continue
        fa, fb = [], []
        for s in range(samples):
            crits_a = rows_a[s][rid].get("criteria") or []
            crits_b = rows_b[s][rid].get("criteria") or []
            fa.append(sum(1 for c in crits_a if not c))
            fb.append(sum(1 for c in crits_b if not c))
        out[rid] = {
            "failed_a": sorted(fa),
            "failed_b": sorted(fb),
            "median_a": r440._median([float(x) for x in fa]),
            "median_b": r440._median([float(x) for x in fb]),
        }
    return out


def keep_verdict(r440, label: str, samples: int) -> int:
    from evals.official.paired_ab import AXES, _gold_dropped_head  # noqa: PLC0415

    per_sample = {}
    for s in range(samples):
        p = r440.paired_json(label, s)
        if not p.exists():
            print(f"missing paired artifact: {p}")
            return 2
        per_sample[s] = json.loads(p.read_text(encoding="utf-8"))

    rows_a = [r440._rows(r440.score_json(label, "A", s)) for s in range(samples)]
    rows_b = [r440._rows(r440.score_json(label, "B", s)) for s in range(samples)]
    ids = sorted(set().union(*[set(r) for r in rows_a], *[set(r) for r in rows_b]))
    ids = [i for i in ids if all(i in r for r in rows_a + rows_b)]

    pool = r440.pooled(label, samples)

    print("\nPOOLED PAIRED READ (row-clustered bootstrap, all samples)")
    for axis in AXES:
        d = pool[axis]
        if not d.get("n"):
            print(f"  {axis:<26} no data")
            continue
        star = " B>" if d["ci95"][0] > 0 else (" A>" if d["ci95"][1] < 0 else "")
        print(f"  {axis:<26} n={d['n']:<4} delta={d['delta']:+6.2f} "
              f"CI[{d['ci95'][0]:+.2f},{d['ci95'][1]:+.2f}] {star}")

    # ---- gold-head veto, per row, union over samples ------------------------
    new_drops: dict[str, list[int]] = {}
    for s in range(samples):
        for i in ids:
            ea = rows_a[s][i].get("expected_refs") or []
            eb = rows_b[s][i].get("expected_refs") or []
            if not ea and not eb:
                continue
            da_ = _gold_dropped_head(ea, rows_a[s][i].get("refs") or [])
            db_ = _gold_dropped_head(eb, rows_b[s][i].get("refs") or [])
            if db_ and not da_:
                new_drops.setdefault(i, []).append(s)

    # ---- the failing cohort's criteria --------------------------------------
    cohort = failing_cohort_criteria(r440, label, samples)
    print("\nFAILING-COHORT CRITERIA (failed count, A -> B medians across samples)")
    for rid, d in cohort.items():
        print(f"  {rid:<9} {d['median_a']:.1f} -> {d['median_b']:.1f}"
              f"  (draws A={d['failed_a']} B={d['failed_b']})")
    rec_total = sum(max(0.0, d["median_a"] - d["median_b"]) for d in cohort.values())
    rec_rows = sum(1 for d in cohort.values() if d["median_b"] < d["median_a"])
    print(f"  criteria recovered (sum of per-row median drops): {rec_total:.1f} on {rec_rows} rows")

    # ---- per-sample direction on the correctness axes -----------------------
    def per_sample_delta(axis: str, s: int) -> float:
        return per_sample[s]["axes"][axis]["delta"]

    refuse = []
    if new_drops:
        refuse.append(f"gold-head drops in B on {len(new_drops)} row(s): "
                      f"{ {k: v for k, v in sorted(new_drops.items())} }")
    for axis in r440.REFUSE_AXES:
        neg_samples = [s for s in range(samples) if per_sample_delta(axis, s) < 0]
        if (pool[axis].get("n") and pool[axis]["delta"] < 0) or neg_samples:
            refuse.append(
                f"{axis} regression: pooled delta {pool[axis]['delta']:+.2f} pp, "
                f"negative in sample(s) {neg_samples}"
            )

    strict = pool["ans_correctness_strict"]
    strict_pooled = bool(strict.get("n")) and strict["ci95"][0] > 0
    strict_samples = sum(
        1 for s in range(samples) if per_sample[s]["axes"]["ans_correctness_strict"]["ci95"][0] > 0
    )

    print("\n" + "=" * 88)
    if refuse:
        print("VERDICT: REFUSE — keep REGENOLD_PUSHBACK_KEEP_CONTRACT OFF")
        for r in refuse:
            print(f"  * {r}")
        code = 1
    elif strict_pooled and strict_samples >= 2:
        print("VERDICT: SHIP ON — refuse clean and ans_correctness_strict separates "
              f"(pooled CI > 0, {strict_samples}/3 samples)")
        code = 0
    else:
        print("VERDICT: NO WIN — refuse clean but ans_correctness_strict does not separate "
              f"(pooled {strict_pooled}, samples {strict_samples}/3); leave the contract OFF")
        code = 0
    print("=" * 88)

    (_OUT / "gate-verdict.json").write_text(json.dumps({
        "label": label,
        "pooled": pool,
        "failing_cohort": cohort,
        "criteria_recovered_median_sum": rec_total,
        "new_gold_head_drops": new_drops,
        "strict_pooled_positive": strict_pooled,
        "strict_samples_positive": strict_samples,
        "refuse": refuse,
    }, indent=1), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
