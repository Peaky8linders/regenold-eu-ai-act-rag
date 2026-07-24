"""Does the scorer actually separate GOLD references from NON-GOLD ones?

This is the decisive question, and it is upstream of every threshold/policy
choice. A filter can only help if the score it filters on RANKS gold above
non-gold. If the ROC-AUC is ~0.5 the score is noise and no threshold, floor or
policy can recover it — tuning would just be overfitting the sweep.

Reads the ``per_row_scores`` block written by ``nli_refprecision_sim`` and
labels every (row, ref) pair gold / non-gold at HEAD level (which is the
granularity ``evals.bench.metrics`` scores at), then reports:

  * ROC-AUC              — rank separation; 0.5 = coin flip
  * mean gold / non-gold — absolute separation
  * "recoverable" count  — non-gold refs ranked BELOW every gold ref in their
    own row, i.e. the over-citations a per-row relative filter could actually
    remove without touching gold. This is the realistic ceiling of the method.

Usage:
    .venv/Scripts/python.exe -m evals.harness.nli_discriminative_power \\
        evals/bench/results/nli-sim-r288-lexical-mentions.json ...
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

from evals.bench import metrics as bench_metrics

_RESULTS = Path(__file__).resolve().parents[1] / "bench" / "results"


def _auc(pos: list[float], neg: list[float]) -> float:
    """Rank-based ROC-AUC (Mann-Whitney U), ties counted as 0.5."""
    if not pos or not neg:
        return float("nan")
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks: list[float] = [0.0] * len(allv)
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    rsum = sum(r for r, (_, lab) in zip(ranks, allv) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (rsum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def analyse(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    per_row = data.get("per_row_scores") or {}
    sidecar = Path(data.get("sidecar", ""))
    if not sidecar.exists():
        sidecar = _RESULTS / "easyhard-r282-fullprod-clean.json"
    rows = json.loads(sidecar.read_text(encoding="utf-8")).get("baseline_rows") or []
    by_id = {r["id"]: r for r in rows}

    gold_scores: list[float] = []
    non_scores: list[float] = []
    recoverable = 0
    total_non = 0
    rows_seen = 0

    for rid, scores in per_row.items():
        row = by_id.get(rid)
        if not row:
            continue
        rows_seen += 1
        gold_heads = bench_metrics.article_heads(row.get("gold_refs") or [])
        g, n = [], []
        for ref, s in scores.items():
            head = bench_metrics.article_head(ref) or ref
            (g if head in gold_heads else n).append((ref, float(s)))
        gold_scores.extend(v for _, v in g)
        non_scores.extend(v for _, v in n)
        total_non += len(n)
        if g and n:
            min_gold = min(v for _, v in g)
            recoverable += sum(1 for _, v in n if v < min_gold)

    return {
        "label": data.get("label"),
        "scorer": data.get("scorer"),
        "formulation": data.get("formulation"),
        "rows": rows_seen,
        "n_gold": len(gold_scores),
        "n_nongold": len(non_scores),
        "auc": _auc(gold_scores, non_scores),
        "mean_gold": st.fmean(gold_scores) if gold_scores else float("nan"),
        "mean_nongold": st.fmean(non_scores) if non_scores else float("nan"),
        "median_gold": st.median(gold_scores) if gold_scores else float("nan"),
        "median_nongold": st.median(non_scores) if non_scores else float("nan"),
        "recoverable_nongold": recoverable,
        "total_nongold": total_non,
        "recoverable_pct": (recoverable / total_non * 100) if total_non else 0.0,
        "ms_per_pair": data.get("ms_per_pair"),
    }


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]]
    if not paths:
        paths = sorted(_RESULTS.glob("nli-sim-*.json"))
    if not paths:
        print("no nli-sim-*.json sidecars found")
        return 1

    hdr = (f"{'label':32s} {'form':10s} {'AUC':>6s} {'mGold':>7s} {'mNon':>7s} "
           f"{'recov%':>7s} {'ms/pair':>8s}")
    print(hdr)
    print("-" * len(hdr))
    out = []
    for p in paths:
        try:
            a = analyse(p)
        except Exception as e:  # noqa: BLE001
            print(f"{p.name}: ERROR {e}")
            continue
        out.append(a)
        print(f"{str(a['label'])[:32]:32s} {str(a['formulation'])[:10]:10s} "
              f"{a['auc']:>6.3f} {a['mean_gold']:>7.4f} {a['mean_nongold']:>7.4f} "
              f"{a['recoverable_pct']:>6.1f}% {(a['ms_per_pair'] or 0):>7.1f}")
    print()
    print("AUC 0.50 = coin flip (no threshold can help).  "
          "recov% = non-gold refs a per-row relative filter could remove\n"
          "without touching gold -- the realistic ceiling of the method.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
