"""R442 — the R440 pooled read with the harness-voided (fallback-served) pairs removed.

Same per-row axis function (``evals.official.paired_ab._row_axis``) and the same
row-clustered bootstrap (10,000 resamples, seed 440) as
``docs/measurements/r440/branch_cluster_gate.pooled``. Prints the published read
first, which must reproduce CHECKPOINT.md (ans_conciseness -3.14 [-6.55, -0.10],
ref_correctness_strict +1.59) — true only with the COMMITTED
``evals/official/rubric.py``; an uncommitted scorer change moves the strict read.

Checkpoints are gitignored: run from the repo root of a checkout that holds
``evals/bench/results/official-r440c-branch-cluster-*.ckpt.jsonl``.
"""
import json
import random
import sys

sys.path.insert(0, ".")
from evals.official.paired_ab import AXES, _row_axis  # noqa: E402

SAMPLES = range(3)


def rows(arm: str, sample: int) -> dict[str, dict]:
    path = f"docs/measurements/r388/score-r440c-branch-cluster-{arm}-hard-s{sample}-hard.json"
    with open(path, encoding="utf-8") as fh:
        return {r["id"]: r for r in json.load(fh)["rows"]}


def served(arm: str, sample: int) -> dict[str, str | None]:
    suffix = "" if sample == 0 else f".r{sample}"
    path = f"evals/bench/results/official-r440c-branch-cluster-{arm}-hard{suffix}.ckpt.jsonl"
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            out[record["id"]] = (record.get("provenance") or {}).get("stage2_served_by")
    return out


def pooled(per_row: list[list[float]]) -> tuple[float, float, float, int]:
    flat = [d for ds in per_row for d in ds]
    rng = random.Random(440)
    means = []
    for _ in range(10_000):
        acc: list[float] = []
        for _i in range(len(per_row)):
            acc.extend(per_row[rng.randrange(len(per_row))])
        means.append(sum(acc) / len(acc))
    means.sort()
    return sum(flat) / len(flat), means[250], means[9749], len(flat)


A = [rows("A", s) for s in SAMPLES]
B = [rows("B", s) for s in SAMPLES]
SA = [served("A", s) for s in SAMPLES]
SB = [served("B", s) for s in SAMPLES]
ids = sorted(set(A[0]) & set(B[0]))
degraded = {
    (i, s)
    for s in SAMPLES
    for i in ids
    if SA[s].get(i) == "fallback" or SB[s].get(i) == "fallback"
}
print("fallback-served pairs:", len(degraded))
for label, excluded in (("as published", set()), ("fallback pairs dropped", degraded)):
    print(f"-- {label}")
    for axis in AXES:
        per_row = []
        for i in ids:
            deltas = []
            for s in SAMPLES:
                if (i, s) in excluded:
                    continue
                try:
                    va, vb = _row_axis(A[s][i], axis), _row_axis(B[s][i], axis)
                except Exception:  # noqa: BLE001 — an unscorable row is skipped, as the gate does
                    continue
                if va is None or vb is None:
                    continue
                deltas.append(vb - va)
            if deltas:
                per_row.append(deltas)
        delta, lo, hi, n = pooled(per_row)
        print(f"   {axis:24} n={n:2} delta={delta:+6.2f}  CI[{lo:+6.2f}, {hi:+6.2f}]")
