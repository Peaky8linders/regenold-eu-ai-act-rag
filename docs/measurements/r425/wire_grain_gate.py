"""R425 gate — what is prose-grounding the wire grain worth, on evidence?

> **SUPERSEDED, kept for a future full-board confirmation.** This 37-row ×
> 3-generation × 2-arm board was launched and then **stopped deliberately** once
> the lever's invariance was established: the rewrite runs after Stage-2 and edits
> list entries only, so the answer — and therefore both answer axes and Regulatory
> Tone — is byte-identical in both arms and re-drawing it measures exactly `0.00`
> for hours. The three reference axes are the emitted `references` against gold,
> with no LLM involved, so the population version of this measurement is the
> replay over already-drawn samples in ``wire_grain_grounding_probe.py``
> (336 comparable row-samples, each paired within its own draw), and the live leg
> that proves reachability is ``live_paired_read.py``. Run this file only if a
> full eight-axis board with a judge is wanted for the record.

The paired gate for a **wire-slot** lever. Arm A emits the pre-R425 reference
list, arm B runs ``_ground_wire_subpoints``: when the answer's own prose
sub-points a parent at one limb and the wire carries a DIFFERENT limb of the same
parent, the wire limb is rewritten in place onto the prose-named one. Both arms
run the same engine with the same flags, so NOTHING the transport sees differs —
identical system payloads, identical user payloads, identical request shape. That
is why the void guard is asked for the third slot
(``gate_validity.assess(..., lever_slot="wire")``): it must prove the two arms
EMITTED different reference sets, or an inert call site would read as a clean
null.

WHY THE DIRECTION IS EVIDENCE AND NOT PREFERENCE (``wire_grain_grounding_probe``,
replaying the R424 gate's six checkpoints with the real pass and the real
``evals.official.rubric``):

    106 substitutions across 20 rows
    wire limb IS gold / prose limb IS gold / both / neither:  0 / 7 / 8 / 91
    head set invariant, reference COUNT invariant
    ref_strict 65.28 -> 65.90 (+0.62 pp)   ref_loose +0.00   ref_conc +0.00

The wire limb is the gold one in **none** of them, so the pass can only move Ref.
Strict up or leave it alone; heads and count are invariant by construction, so
Hard Rule #8 and Ref. Conciseness cannot move at all.

PRE-REGISTERED RULE, fixed before the numbers were read. This is a fidelity
correction to the graded artifact, so the bar is "the board does not get worse" —
the mechanism evidence above is what justifies the direction, and this gate's job
is to prove the edit is harmless on a fresh paired draw:

  * both ANSWER axes within noise (they cannot move causally — the pass runs after
    Stage-2 and edits only the ``references`` field — so a move here is a bug);
  * ``ref_correctness_loose`` and ``ref_conciseness`` within noise (both are
    invariant by construction; a move is a wiring bug);
  * the targeted ``ref_correctness_strict`` not below −1.5 pp, reported with its
    CI95;
  * gold heads dropped B <= A (Hard Rule #8);
  * the official aggregate (geometric mean of the eight axes) >= −1.0 pp.

SHIP iff every one holds; otherwise the default reverts to ``0``.

Usage::

    # score the 6 checkpoints (3 generations x 2 arms), then aggregate
    .venv\\Scripts\\python.exe docs/measurements/r425/wire_grain_gate.py --score
    # aggregate only, from artifacts already on disk
    .venv\\Scripts\\python.exe docs/measurements/r425/wire_grain_gate.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
RESULTS = REPO / "evals" / "bench" / "results"

LABEL = "r425-wiregrain"
REPEATS = 3
ARMS = ("A", "B")  # A = OFF (pre-R425 wire), B = ON (prose-grounded grain)
COMPARABLE_FLOOR = 20
MIN_PRIMARY_SAMPLES = 2
#: The answer axes cannot move CAUSALLY (the pass edits only ``references``); the
#: loose bar is generation noise on an independently drawn answer, not slack for
#: the lever.
TOLERANCE_ANS_PP = -1.5
TOLERANCE_INVARIANT_PP = -1.5
TOLERANCE_OVERALL_PP = -1.0


def _ckpt(label: str, arm: str, sample: int) -> Path:
    stem = f"official-{label}-{arm}-hard"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def run_scores(label: str = LABEL) -> None:
    """Score each checkpoint with the R419/R423 board's exact instrument.

    Reuses the R424 driver, which pins the judge identity
    (``openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:r=3``) and its cache, so these
    absolute levels are readable against the published board instead of against a
    different judge.
    """
    from docs.measurements.r424 import hard_preamble_gate as r424

    assert r424.ARMS == ARMS and r424.REPEATS == REPEATS, "gate designs diverged"
    r424.run_scores(label)


def _gate_payload(label: str) -> dict[str, Any]:
    path = RESULTS / f"official-{label}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    from docs.measurements.r423 import need_gate as ng  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--score", action="store_true", help="score the 6 checkpoints first")
    ap.add_argument("--label", default=LABEL)
    a = ap.parse_args()

    assert ng.ARMS == ARMS and ng.REPEATS == REPEATS, "gate designs diverged"

    if a.score:
        run_scores(a.label)

    # ── 1. The void guard decides first ────────────────────────────────────
    payload = _gate_payload(a.label)
    guard = payload.get("gate") or {}
    print(f"lever_slot: {payload.get('lever_slot')}  "
          f"wire={payload.get('lever_changes_wire')}  "
          f"request={payload.get('lever_changes_request')}  "
          f"system={payload.get('lever_changes_system')}")
    for m, v in guard.items():
        for arm_label, arm in (v or {}).get("arms", {}).items():
            print(f"  [{m}] {arm_label}: wire_shape={arm.get('wire_shape')!r} "
                  f"legs={arm.get('legs')} fallback_attempts={arm.get('fallback_attempts')} "
                  f"primary_failed={arm.get('primary_failed')} refused={arm.get('refused')}")
    void_arms = [m for m, v in guard.items() if v and not v.get("valid")]
    if void_arms:
        print("=" * 88)
        print("VOID RUN — the runner's own gate guard refused these arms; no delta is reported.")
        for m in void_arms:
            for reason in guard[m].get("reasons") or []:
                print(f"  VOID: {reason}")
        print("=" * 88)
        raise SystemExit(2)
    if not guard:
        print(f"  WARNING: no gate verdict in official-{a.label}.json yet (still running?)")

    # ── 2. Load the judged artifacts ───────────────────────────────────────
    artifacts: dict[str, dict[int, dict[str, Any]]] = {}
    for arm in ARMS:
        artifacts[arm] = {}
        for sample in range(REPEATS):
            path = r424_score_artifact(a.label, arm, sample)
            if not path.exists():
                raise SystemExit(f"missing score artifact {path.name} (run with --score)")
            data = json.loads(path.read_text(encoding="utf-8"))
            artifacts[arm][sample] = {r["id"]: r for r in data["rows"]}
    ckpts = {
        arm: [ng._load_rows(_ckpt(a.label, arm, s)) for s in range(REPEATS)]
        for arm in ARMS
    }

    # ── 3. Symmetric comparability filter ──────────────────────────────────
    ids = [r["id"] for r in artifacts["A"][0].values()]
    comparable: list[str] = []
    dropped: dict[str, list[str]] = {}
    for row_id in ids:
        missing = any(
            row_id not in artifacts[arm][s] or row_id not in ckpts[arm][s]
            for arm in ARMS for s in range(REPEATS)
        )
        if missing:
            dropped.setdefault("missing_from_an_artifact", []).append(row_id)
            continue
        keep: dict[str, list[int]] = {}
        for arm in ARMS:
            served = [
                s for s in range(REPEATS)
                if ng._served_by(ckpts[arm][s][row_id]) == "primary"
            ]
            keep[arm] = served
            if len(served) < MIN_PRIMARY_SAMPLES:
                seen = sorted({
                    ng._served_by(ckpts[arm][s][row_id]) or "none" for s in range(REPEATS)
                })
                dropped.setdefault(f"arm_{arm}_not_primary[{'+'.join(seen)}]", []).append(row_id)
        if len(keep["A"]) < MIN_PRIMARY_SAMPLES or len(keep["B"]) < MIN_PRIMARY_SAMPLES:
            continue
        comparable.append(row_id)
        ng._PRIMARY_SAMPLES[row_id] = keep

    per_row: list[dict[str, Any]] = []
    for row_id in comparable:
        entry: dict[str, Any] = {"id": row_id}
        for arm in ARMS:
            samples = ng._PRIMARY_SAMPLES[row_id][arm]
            metrics = [ng._row_metrics(artifacts[arm][s][row_id]) for s in samples]
            for key in ("ans_loose", "ans_strict", "answer_chars", "tone", "ref_strict"):
                entry[f"{key}_{arm}"] = ng._median([m[key] for m in metrics])
            entry[f"n_primary_{arm}"] = len(samples)
            refs = artifacts[arm][samples[0]][row_id]
            entry[f"dropped_heads_{arm}"] = sorted(
                ng._heads(refs.get("expected_refs") or []) - ng._heads(refs.get("refs") or [])
            )
            entry[f"refs_{arm}"] = len(refs.get("refs") or [])
            # R425 — the emitted reference SET, so the coordinate rewrite is
            # visible per row rather than only in the aggregate.
            entry[f"wire_{arm}"] = sorted(str(x) for x in (refs.get("refs") or []))
        entry["delta_ans_loose"] = entry["ans_loose_B"] - entry["ans_loose_A"]
        entry["delta_ans_strict"] = entry["ans_strict_B"] - entry["ans_strict_A"]
        entry["delta_answer_chars"] = entry["answer_chars_B"] - entry["answer_chars_A"]
        entry["delta_tone"] = entry["tone_B"] - entry["tone_A"]
        entry["delta_ref_strict"] = entry["ref_strict_B"] - entry["ref_strict_A"]
        entry["delta_refs"] = entry["refs_B"] - entry["refs_A"]
        entry["wire_changed"] = entry["wire_A"] != entry["wire_B"]
        per_row.append(entry)

    char_axes = {"delta_answer_chars", "delta_refs"}

    def _agg(key: str) -> dict[str, Any]:
        deltas = [r[key] for r in per_row if r[key] == r[key]]
        if not deltas:
            return {"n": 0}
        scale = 1.0 if key in char_axes else 100.0
        lo, hi = ng._bootstrap_ci(deltas)
        return {
            "n": len(deltas),
            "units": "count" if scale == 1.0 else "pp",
            "mean_delta_pp": round(scale * statistics.fmean(deltas), 2),
            "median_delta_pp": round(scale * statistics.median(deltas), 2),
            "ci95_pp": [round(scale * lo, 2), round(scale * hi, 2)],
            "rows_improved": sum(1 for d in deltas if d > 1e-9),
            "rows_worsened": sum(1 for d in deltas if d < -1e-9),
            "rows_tied": sum(1 for d in deltas if abs(d) <= 1e-9),
        }

    board = ng.official_axes(artifacts, comparable, ng._gold_reference_answers())

    report: dict[str, Any] = {
        "label": a.label,
        "repeats": REPEATS,
        "lever_slot": payload.get("lever_slot"),
        "official_board": board,
        "guard": guard,
        "rows_requested": len(ids),
        "rows_comparable": len(comparable),
        "rows_with_a_changed_wire": sum(1 for r in per_row if r["wire_changed"]),
        "dropped": dropped,
        "comparable_floor": COMPARABLE_FLOOR,
        "min_primary_samples": MIN_PRIMARY_SAMPLES,
        "tolerance_ans_pp": TOLERANCE_ANS_PP,
        "tolerance_invariant_pp": TOLERANCE_INVARIANT_PP,
        "tolerance_overall_pp": TOLERANCE_OVERALL_PP,
        "axes": {
            key: _agg(key)
            for key in (
                "delta_ans_loose", "delta_ans_strict", "delta_answer_chars",
                "delta_tone", "delta_ref_strict", "delta_refs",
            )
        },
        "gold_head_drops": {
            "A": sum(len(r["dropped_heads_A"]) for r in per_row),
            "B": sum(len(r["dropped_heads_B"]) for r in per_row),
            "A_rows": sum(1 for r in per_row if r["dropped_heads_A"]),
            "B_rows": sum(1 for r in per_row if r["dropped_heads_B"]),
        },
        "wire_examples": [
            {"id": r["id"], "A": r["wire_A"], "B": r["wire_B"]}
            for r in per_row
            if r["wire_changed"]
        ][:12],
        "per_row": per_row,
    }
    (OUT / "wire_grain_gate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("=" * 88)
    print(f"R425 wire-grain gate  |  label={a.label}  generations={REPEATS}")
    print("=" * 88)
    print(f"rows requested {report['rows_requested']}  comparable {report['rows_comparable']} "
          f"(floor {COMPARABLE_FLOOR})  rows whose emitted set changed "
          f"{report['rows_with_a_changed_wire']}")
    for key, ids_ in report["dropped"].items():
        print(f"  dropped {key}: {len(ids_)}  {', '.join(ids_[:8])}{' ...' if len(ids_) > 8 else ''}")
    for key, agg in report["axes"].items():
        if not agg.get("n"):
            print(f"  {key:<22} no data")
            continue
        unit = agg.get("units", "pp")
        print(f"  {key:<22} {agg['mean_delta_pp']:+10.2f} {unit:<6}"
              f"(median {agg['median_delta_pp']:+.2f}, CI95 "
              f"[{agg['ci95_pp'][0]:+.2f}, {agg['ci95_pp'][1]:+.2f}])  "
              f"{agg['rows_improved']} up / {agg['rows_worsened']} down / {agg['rows_tied']} tied")
    print()
    print(f"  official board on the comparable subset (n={board['subset_n']}), "
          "per-axis MEDIAN over the generations:")
    print(f"    {'axis':<26}{'A off':>11}{'B on':>11}{'delta':>10}")
    for axis, vals in board["axes"].items():
        def _fmt(value: float | None, sign: bool = False) -> str:
            if value is None:
                return f"{'n/a':>11}"
            return f"{value:>+11.2f}" if sign else f"{value:>11.2f}"

        print(f"    {axis:<26}{_fmt(vals['A'])}{_fmt(vals['B'])}"
              f"{_fmt(vals['delta_pp'], sign=True)}")
    print()
    print(f"  gold head drops          A {report['gold_head_drops']['A']} "
          f"({report['gold_head_drops']['A_rows']} rows) vs "
          f"B {report['gold_head_drops']['B']} ({report['gold_head_drops']['B_rows']} rows)")
    print()
    if report["rows_comparable"] < COMPARABLE_FLOOR:
        print("!! REFUSING A VERDICT: fewer comparable rows than the floor. "
              "The sample cannot carry a delta.")
    else:
        ans_loose = report["axes"]["delta_ans_loose"]
        ans_strict = report["axes"]["delta_ans_strict"]
        ref_strict = report["axes"]["delta_ref_strict"]
        overall = board["axes"]["overall"]["delta_pp"]
        overall = float("-inf") if overall is None else overall
        ref_loose = board["axes"]["ref_correctness_loose"]["delta_pp"]
        ref_conc = board["axes"]["ref_conciseness"]["delta_pp"]
        checks = {
            f"ans_loose > {TOLERANCE_ANS_PP} pp": ans_loose["mean_delta_pp"] > TOLERANCE_ANS_PP,
            f"ans_strict > {TOLERANCE_ANS_PP} pp": ans_strict["mean_delta_pp"] > TOLERANCE_ANS_PP,
            f"ref_loose > {TOLERANCE_INVARIANT_PP} pp (invariant)": (
                ref_loose is None or ref_loose > TOLERANCE_INVARIANT_PP
            ),
            f"ref_conc > {TOLERANCE_INVARIANT_PP} pp (invariant)": (
                ref_conc is None or ref_conc > TOLERANCE_INVARIANT_PP
            ),
            f"ref_strict >= {TOLERANCE_INVARIANT_PP} pp (targeted axis)": (
                ref_strict["mean_delta_pp"] >= TOLERANCE_INVARIANT_PP
            ),
            f"official overall >= {TOLERANCE_OVERALL_PP} pp": overall >= TOLERANCE_OVERALL_PP,
            "gold heads dropped B <= A": (
                report["gold_head_drops"]["B"] <= report["gold_head_drops"]["A"]
            ),
        }
        for name, ok in checks.items():
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        verdict = "SHIP (the prose-grounded grain stays default ON)" if all(checks.values()) else (
            "REVERT THE DEFAULT TO 0 (the rewrite is not safe on this evidence)"
        )
        print(f"VERDICT: {verdict}  (ref_strict "
              f"{ref_strict['mean_delta_pp']:+.2f} pp, official overall "
              f"{board['axes']['overall']['A']} -> {board['axes']['overall']['B']}, "
              f"{overall:+.2f} pp)")
    print(f"\nwrote {OUT / 'wire_grain_gate.json'}")


def r424_score_artifact(label: str, arm: str, sample: int) -> Path:
    from evals.official.score_arm import OUT_DIR  # noqa: PLC0415

    return Path(OUT_DIR) / f"score-{label}-{arm}-s{sample}-hard.json"


if __name__ == "__main__":
    main()
