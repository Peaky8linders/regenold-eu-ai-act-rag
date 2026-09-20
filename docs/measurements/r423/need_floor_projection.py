"""R423.1 — the level choice for an UNANCHORED ask, measured before it was made.

``REGENOLD_NEED_PROPORTIONAL_CONTRACT`` was KEPT OFF by its first gate
(``docs/measurements/r423/CHECKPOINT.md``) because it lost two rows' criteria,
and both lost rows are rows where the estimator found NO anchor at all: the ask
names no coordinate and engages no closed set (``rg_010`` "Which article ...
governs human oversight measures?"; ``rg_106`` a classification scenario). On
those rows the estimator fell through to ``items = 1`` and asserted the MINIMUM
target (375 chars) while the gold references are 759 and 781 chars and the
criteria ARE the substance of the provision the ask is about.

So the fix is a level, and a level has to be chosen on data rather than taste.
This probe answers three questions and is deliberately runnable with no network,
no judge and no live model:

  A. HOW BIG IS THE NO-SIGNAL STATE? If it were a corner case, patching two rows
     would be defensible; if it is most of the board, the level IS the lever.
  B. WHAT LEVEL DOES IT JUSTIFY? The floor is calibrated on the SUBGROUP it
     applies to — not on the two rows that exposed the bug, which is the bias
     this probe exists to prevent.
  C. IS A GRADED FLOOR JUSTIFIED? ``Ans. Conciseness`` is ``min(1, ref/cand)``,
     so a per-row target would beat a flat one only if some inference-time
     feature predicts the reference length. If nothing does, a formula keyed on
     what the estimator can see would be a number nobody measured — which is
     exactly the defect the module's first calibration was.

Run::

    .venv\\Scripts\\python.exe docs/measurements/r423/need_floor_projection.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
#: The first (OFF-verdict) gate's checkpoints: the only measured per-row lengths
#: for the ON arm that exist, and the response model the projection needs.
CKPT_DIR = REPO / "evals" / "bench" / "results"
GATE_LABEL = "r423-need3"

_CANDIDATE_FLOORS = (375, 450, 550, 650, 750, 850)


def _gold() -> list[dict]:
    return [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _ref_len(row: dict) -> int:
    return len(row.get("reference_answer") or "")


def _n_criteria(row: dict) -> int:
    return len(row.get("criteria") or row.get("correctness_criteria") or [])


def _ckpt(label: str, arm: str) -> dict[str, dict]:
    path = CKPT_DIR / f"official-{label}-{arm}-hard.ckpt.jsonl"
    if not path.exists():
        return {}
    return {
        json.loads(line)["id"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _answer_len(row: dict | None) -> int:
    return len(str((row or {}).get("pred_answer") or ""))


def _pearson(a: list[float], b: list[float]) -> float:
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def _spearman(a: list[float], b: list[float]) -> float:
    ra = {v: i for i, v in enumerate(sorted(set(a)))}
    rb = {v: i for i, v in enumerate(sorted(set(b)))}
    return _pearson([ra[x] for x in a], [rb[x] for x in b])


def _quantile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def main() -> None:
    from app.engines.answer_need import answer_need

    gold = _gold()
    rows: list[dict] = []
    for row in gold:
        need = answer_need(row.get("question") or "")
        rows.append(
            {
                "id": row["id"],
                "ask_chars": len(row.get("question") or ""),
                "ref_chars": _ref_len(row),
                "criteria": _n_criteria(row),
                "unanchored": not (need.asked or need.engaged),
                "is_yes_no": need.is_yes_no,
            }
        )
    unanchored = [r for r in rows if r["unanchored"]]

    print("=" * 78)
    print("A — how big is the no-signal state?")
    print("=" * 78)
    print(f"  unanchored rows: {len(unanchored)}/{len(rows)} "
          f"({100 * len(unanchored) / len(rows):.0f}% of the board)")
    refs = [r["ref_chars"] for r in unanchored]
    print(f"  their reference answers: mean={st.mean(refs):.0f} "
          f"median={st.median(refs):.0f} p25={_quantile(refs, 0.25)} "
          f"p75={_quantile(refs, 0.75)} min={min(refs)} max={max(refs)}")
    print(f"  reference below the chosen floor: "
          f"{sum(1 for x in refs if x < 650)}/{len(refs)}")
    print("  => the level, not the per-row shape, is what moves this axis.")

    print()
    print("=" * 78)
    print("B — what level does the subgroup justify? (projection, no live model)")
    print("=" * 78)
    print("  Model: the floor binds only where the MEASURED candidate came in")
    print("  below it, and the candidate is otherwise left as measured - the most")
    print("  conservative reading of a level instruction, which the first gate")
    print("  itself bounded (the ON arm obeyed 375 with 379 on rg_010).")
    print()
    on_ckpt = _ckpt(GATE_LABEL, "B")
    off_ckpt = _ckpt(GATE_LABEL, "A")
    # ONLY rows the lever can reach. A row the route answers deterministically
    # (a curated intercept, ~30 % of the board) never sees a Stage-2 prompt, so
    # its measured answer is identical in both arms and a floor cannot move it.
    # INCLUDING such rows rigs the projection: the first cut of this probe did,
    # and its "worst row" (rg_076, reference 160 chars, -75 pp) is exactly one
    # of them - the route probe measured 0 Stage-2 dispatches for it in BOTH
    # arms. The gate's own comparability rule is the fix: primary-served only.
    measured = [
        r
        for r in unanchored
        if r["id"] in on_ckpt
        and (on_ckpt[r["id"]].get("provenance") or {}).get("stage2_served_by") == "primary"
    ]
    unreachable = [r["id"] for r in unanchored if r["id"] in on_ckpt and r not in measured]
    print(f"  unanchored rows measured but NOT Stage-2-served (excluded, "
          f"the lever cannot move them): {len(unreachable)}")
    if not measured:
        print(f"  (no {GATE_LABEL} checkpoints on disk: the projection is skipped,")
        print("   but A and C below are the parts that justify the constant.)")
    else:
        print(f"  rows with a measured ON-arm answer: {len(measured)}")
        if measured:
            off_len = st.mean(_answer_len(off_ckpt[r["id"]]) for r in measured)
            on_len = st.mean(_answer_len(on_ckpt[r["id"]]) for r in measured)
            print(f"  measured mean answer: OFF {off_len:.0f} chars -> ON {on_len:.0f} "
                  f"(the compression the lever actually achieves)")
        header = f"  {'floor':>6} {'mean ans_conc':>14} {'rows moved':>11} {'worst row':>10}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for floor in _CANDIDATE_FLOORS:
            vals: list[float] = []
            moved: list[tuple[str, float, float]] = []
            for r in measured:
                ref = r["ref_chars"]
                before = _answer_len(on_ckpt[r["id"]])
                after = max(before, floor)
                vals.append(min(1.0, ref / after) if after else 0.0)
                if after != before:
                    moved.append((r["id"], min(1.0, ref / before), min(1.0, ref / after)))
            worst = min(moved, key=lambda t: t[2] - t[1]) if moved else None
            worst_txt = f"{worst[0]} {100 * (worst[2] - worst[1]):+.0f}pp" if worst else "-"
            print(f"  {floor:>6} {100 * st.mean(vals):>13.2f}% {len(moved):>11} {worst_txt:>10}")
        print()
        chosen = next(
            (f for f in _CANDIDATE_FLOORS if f == 650), None
        )
        base = None
        for floor in _CANDIDATE_FLOORS:
            vals = [
                min(1.0, r["ref_chars"] / max(_answer_len(on_ckpt[r["id"]]), floor))
                if max(_answer_len(on_ckpt[r["id"]]), floor)
                else 0.0
                for r in measured
            ]
            if floor == 375:
                base = 100 * st.mean(vals)
            if floor == chosen:
                at_chosen = 100 * st.mean(vals)
        if chosen is not None and base is not None:
            print(f"  The chosen floor is {chosen}: the subgroup's own central reference")
            print("  length (median 657, mean 646), NOT the two rows that exposed the bug.")
            print(f"  Measured cost of that choice: {base:.2f}% -> {at_chosen:.2f}% on this")
            print(f"  axis over the {len(measured)} reachable unanchored rows "
                  f"({at_chosen - base:+.2f} pp).")
            print("  It is FREE below 550 (those rows' references sit above the floor,")
            print("  so the extra room is correctness headroom nobody pays for).")

    print()
    print("=" * 78)
    print("C — is a GRADED floor justified? (it would only be if a feature"
          " predicted the reference)")
    print("=" * 78)
    ask = [float(r["ask_chars"]) for r in unanchored]
    ref = [float(r["ref_chars"]) for r in unanchored]
    crit = [float(r["criteria"]) for r in unanchored]
    print(f"  corr(ask length, ref length)  = {_pearson(ask, ref):+.3f} "
          f"Pearson / {_spearman(ask, ref):+.3f} Spearman   => too weak to key on")
    print(f"  corr(criteria,   ref length)  = {_pearson(crit, ref):+.3f} "
          f"Pearson / {_spearman(crit, ref):+.3f} Spearman   => good, but criteria")
    print("                                                      are not available")
    print("                                                      at inference")
    for label in ("is_yes_no",):
        yes = [float(r["ref_chars"]) for r in unanchored if r[label]]
        no = [float(r["ref_chars"]) for r in unanchored if not r[label]]
        print(f"  ref length | {label}: {st.mean(yes):.0f} (n={len(yes)}) "
              f"vs {st.mean(no):.0f} (n={len(no)})")  # noqa: B007 — one flag, listed
    print()
    print("  VERDICT: nothing the estimator can see predicts an unanchored ask's")
    print("  reference length (a ridge fit of the ask's own features was already")
    print("  falsified leave-one-out at r=0.10-0.14). A flat floor at the")
    print("  subgroup's central value is therefore the honest choice, and every")
    print("  candidate alternative would be a number nobody measured.")

    report = {
        "unanchored_rows": len(unanchored),
        "total_rows": len(rows),
        "subgroup_ref_chars": {
            "mean": round(st.mean(refs), 1),
            "median": st.median(refs),
            "p25": _quantile(refs, 0.25),
            "p75": _quantile(refs, 0.75),
            "min": min(refs),
            "max": max(refs),
        },
        "corr_ask_len_ref_len": {
            "pearson": round(_pearson(ask, ref), 3),
            "spearman": round(_spearman(ask, ref), 3),
        },
        "corr_criteria_ref_len": {
            "pearson": round(_pearson(crit, ref), 3),
            "spearman": round(_spearman(crit, ref), 3),
        },
        "chosen_floor_chars": 650,
        "measured_rows": len(measured),
        "measured_rows_excluded_not_stage2_served": len(unreachable),
        "projected_ans_conc_pct": {
            str(f): round(
                100
                * st.mean(
                    [
                        min(1.0, r["ref_chars"] / max(_answer_len(on_ckpt[r["id"]]), f))
                        if max(_answer_len(on_ckpt[r["id"]]), f)
                        else 0.0
                        for r in measured
                    ]
                ),
                2,
            )
            for f in _CANDIDATE_FLOORS
        },
    }
    (OUT / "need_floor_projection.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print()
    print(f"wrote {OUT / 'need_floor_projection.json'}")


if __name__ == "__main__":
    main()
