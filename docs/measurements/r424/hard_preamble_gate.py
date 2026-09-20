"""R424 gate — what was the hard-mode FIDELITY GAP worth, on evidence?

The paired gate for the request shape: arm A posts the shipped ROLLING
conversation (our own prior Q&A, starting empty), arm B posts the pre-fixed
9-exchange dialogue the official hard modality actually uses
(``evals.regenold.hard_preamble``). Both arms run the SAME engine with the same
flags, so this is a request-slot lever and the void guard checks the request slot
(``gate_validity.assess(..., lever_slot="request")``) rather than voiding on the
byte-identical system payloads that are the CORRECT outcome here.

Three things make this a gate rather than a printout, inherited from R423:

1. **The void guard decides first.** ``official-r424-preamble.json`` carries the
   runner's own ``assess`` verdict, built from the transport counters this process
   incremented and the request shapes it recorded. VOID means nothing is reported:
   a null delta from a wrong-transport run is the same shape as a real null.

2. **Only rows that could move are scored, symmetrically.** ~30 % of the board is
   answered deterministically before Stage-2, so a row that never reaches the model
   cannot respond to a request-shape change. Such rows are excluded from BOTH arms,
   reported as a drop count, and the run refuses below a floor.

3. **Every number is a per-row MEDIAN over the 3 generations.** The judged axes move
   by a criterion or two per row, and R419 measured rows whose credited criteria are
   draw-dependent, so one draw cannot separate a delta from generation noise.

Usage::

    # score the 6 checkpoints (3 generations x 2 arms), then aggregate
    .venv\\Scripts\\python.exe docs/measurements/r424/hard_preamble_gate.py --score
    # aggregate only, from artifacts already on disk
    .venv\\Scripts\\python.exe docs/measurements/r424/hard_preamble_gate.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
RESULTS = REPO / "evals" / "bench" / "results"
CACHE = OUT / "judge-cache-r424.jsonl"

#: The gate is judged with the R419/R423 board's exact instrument, so its absolute
#: levels can be read against the published board instead of against a different
#: judge. The identity (including ``:r=K``) is part of the judge cache key, so
#: changing either knob silently re-buys every verdict.
JUDGE_PROVIDER = "openrouter"
JUDGE_MODEL = "qwen/qwen3-235b-a22b-2507"
JUDGE_REPEATS = 3
JUDGE_CACHE_SEED = REPO / "docs/measurements/r419/judge-cache-r419-qwen235.jsonl"

LABEL = "r424-preamble"
REPEATS = 3
ARMS = ("A", "B")  # A = rolling (shipped board shape), B = fixed 9-turn dialogue
#: Below this many comparable rows the gate refuses to publish a delta — the same
#: line R423 used, set from measured Stage-2 reachability (~81/110 rows).
COMPARABLE_FLOOR = 20
#: A row is comparable when the PRIMARY leg served the graded answer in at least
#: this many of its samples, in BOTH arms. Symmetric, and every dropped row is
#: reported with its reason.
MIN_PRIMARY_SAMPLES = 2
BOOTSTRAP = 4000

#: PRE-REGISTERED decision rule, fixed BEFORE the numbers were read. This lever is
#: a fidelity correction, not an optimisation, so the bar is "the board does not get
#: worse": a request shape that costs correctness is not worth a more faithful
#: harness, and it must not be flipped on a win in conciseness alone.
#:
#:  * correctness may not fall by more than noise: both ans_loose and ans_strict
#:    mean deltas > -1.5 pp;
#:  * the official aggregate (geometric mean over the eight axes) may not fall by
#:    more than -1.0 pp;
#:  * gold heads dropped must not INCREASE (Hard Rule #8: drop zero gold refs).
TOLERANCE_ANS_PP = -1.5
TOLERANCE_OVERALL_PP = -1.0


def _ckpt(label: str, arm: str, sample: int) -> Path:
    stem = f"official-{label}-{arm}-hard"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def _score_artifact(label: str, arm: str, sample: int) -> Path:
    from evals.official.score_arm import OUT_DIR

    return Path(OUT_DIR) / f"score-{label}-{arm}-s{sample}-hard.json"


def run_scores(label: str = LABEL) -> None:
    """Score each checkpoint with the official instrument (cached judge calls)."""
    if not CACHE.exists() and JUDGE_CACHE_SEED.exists():
        CACHE.write_text(JUDGE_CACHE_SEED.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  judge cache seeded from {JUDGE_CACHE_SEED.name}")
    for arm in ARMS:
        for sample in range(REPEATS):
            ckpt = _ckpt(label, arm, sample)
            if not ckpt.exists():
                raise SystemExit(f"missing checkpoint {ckpt.name}; the gate has not finished")
            artifact = _score_artifact(label, arm, sample)
            if artifact.exists() and not artifact.name.endswith(".VOID.json"):
                print(f"  [skip] {artifact.name} already scored")
                continue
            label_i = f"{label}-{arm}-s{sample}"
            print(f"  scoring {ckpt.name} -> {label_i}", flush=True)
            proc = subprocess.run(
                [
                    sys.executable, "-m", "evals.official.score_arm",
                    "--ckpt", str(ckpt), "--label", label_i, "--mode", "hard",
                    "--repeats", str(JUDGE_REPEATS), "--workers", "1",
                    "--judge-provider", JUDGE_PROVIDER,
                    "--judge-model", JUDGE_MODEL,
                    "--cache-file", str(CACHE),
                ],
                cwd=str(REPO), check=False,
            )
            void = Path(str(artifact).replace(".json", ".VOID.json"))
            if proc.returncode != 0 and not void.exists():
                raise SystemExit(f"score_arm failed for {label_i} (exit {proc.returncode})")


def _gate_payload(label: str) -> dict[str, Any]:
    payload_path = RESULTS / f"official-{label}.json"
    if not payload_path.exists():
        return {}
    return json.loads(payload_path.read_text(encoding="utf-8"))


def main() -> None:
    from docs.measurements.r423 import need_gate as ng  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--score", action="store_true", help="run score_arm on the 6 checkpoints first")
    ap.add_argument("--label", default=LABEL)
    a = ap.parse_args()

    # `official_axes` reads ARMS/REPEATS from its own module: assert the two designs
    # agree rather than silently reporting over the wrong number of generations.
    assert ng.ARMS == ARMS and ng.REPEATS == REPEATS, "gate designs diverged"

    if a.score:
        run_scores(a.label)

    # ── 1. The void guard decides first ────────────────────────────────────
    payload = _gate_payload(a.label)
    guard = payload.get("gate") or {}
    print(f"lever_slot: {payload.get('lever_slot')}  "
          f"request={payload.get('lever_changes_request')}  "
          f"system={payload.get('lever_changes_system')}")
    for m, v in guard.items():
        for arm_label, arm in (v or {}).get("arms", {}).items():
            print(f"  [{m}] {arm_label}: request_shape={arm.get('request_shape')!r} "
                  f"legs={arm.get('legs')} fallback_attempts={arm.get('fallback_attempts')} "
                  f"primary_failed={arm.get('primary_failed')} "
                  f"refused={arm.get('refused')}")
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
            path = _score_artifact(a.label, arm, sample)
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
        entry["delta_ans_loose"] = entry["ans_loose_B"] - entry["ans_loose_A"]
        entry["delta_ans_strict"] = entry["ans_strict_B"] - entry["ans_strict_A"]
        entry["delta_answer_chars"] = entry["answer_chars_B"] - entry["answer_chars_A"]
        entry["delta_tone"] = entry["tone_B"] - entry["tone_A"]
        entry["delta_ref_strict"] = entry["ref_strict_B"] - entry["ref_strict_A"]
        entry["delta_refs"] = entry["refs_B"] - entry["refs_A"]
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
        "dropped": dropped,
        "comparable_floor": COMPARABLE_FLOOR,
        "min_primary_samples": MIN_PRIMARY_SAMPLES,
        "tolerance_ans_pp": TOLERANCE_ANS_PP,
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
        "per_row": per_row,
    }
    (OUT / "hard_preamble_gate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("=" * 88)
    print(f"R424 hard-preamble gate  |  label={a.label}  generations={REPEATS}")
    print("=" * 88)
    print(f"rows requested {report['rows_requested']}  comparable {report['rows_comparable']} "
          f"(floor {COMPARABLE_FLOOR})")
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
    print(f"    {'axis':<26}{'A rolling':>11}{'B fixed':>11}{'delta':>10}")
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
        overall = board["axes"]["overall"]["delta_pp"]
        overall = float("-inf") if overall is None else overall
        checks = {
            f"ans_loose > {TOLERANCE_ANS_PP} pp": ans_loose["mean_delta_pp"] > TOLERANCE_ANS_PP,
            f"ans_strict > {TOLERANCE_ANS_PP} pp": ans_strict["mean_delta_pp"] > TOLERANCE_ANS_PP,
            f"official overall >= {TOLERANCE_OVERALL_PP} pp": overall >= TOLERANCE_OVERALL_PP,
            "gold heads dropped B <= A": (
                report["gold_head_drops"]["B"] <= report["gold_head_drops"]["A"]
            ),
        }
        for name, ok in checks.items():
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        verdict = "SHIP (fixed becomes the default)" if all(checks.values()) else (
            "KEEP ROLLING (the fixed shape is not worth it on this evidence)"
        )
        print(f"VERDICT: {verdict}  (official overall "
              f"{board['axes']['overall']['A']} -> {board['axes']['overall']['B']}, "
              f"{overall:+.2f} pp; answer length "
              f"{report['axes']['delta_answer_chars']['mean_delta_pp']:+.0f} chars)")
    print(f"\nwrote {OUT / 'hard_preamble_gate.json'}")


if __name__ == "__main__":
    main()
