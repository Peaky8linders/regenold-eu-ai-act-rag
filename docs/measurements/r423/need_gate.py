"""R423 gate — does the need-proportional contract move the board, on evidence?

The paired gate for ``REGENOLD_NEED_PROPORTIONAL_CONTRACT``: 37 strided hard rows
(``--stride 3``) x 3 INDEPENDENT generations per row per arm, judged with the
official instrument. Three things make this a gate rather than a printout:

1. **The void guard decides first.** ``official-r423-need.json`` carries the
   runner's own :func:`evals.harness.gate_validity.assess` verdict, built from
   the transport counters this process incremented and the payloads it hashed. If
   it says VOID, nothing is reported (R412/R422: a null delta from a
   wrong-transport run is the same shape as a real null).

2. **Only rows that could move are scored, symmetrically.** The route answers
   ~30 % of the board deterministically before Stage-2 (81/110 primary-served on
   R419, 25 with no trace at all). A row that never reaches Stage-2 cannot
   respond to a prompt-side lever, so it is excluded from BOTH arms plus reported
   as a drop count, and the run refuses below a floor.

3. **Every number is a per-row MEDIAN over the 3 generations**, not a single
   draw. R419 measured two rows whose credited criteria are draw-dependent, and
   the R416 lever's whole answered movement was 2 criteria out of 87 — a single
   draw cannot separate that from generation noise. The gate reports the median
   delta, a bootstrap CI over rows, and the count of rows that moved each way.

Usage::

    # score the 6 checkpoints (3 samples x 2 arms) then aggregate
    .venv\\Scripts\\python.exe docs/measurements/r423/need_gate.py --score
    # aggregate only, from artifacts already on disk
    .venv\\Scripts\\python.exe docs/measurements/r423/need_gate.py
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
RESULTS = REPO / "evals" / "bench" / "results"
CACHE = OUT / "judge-cache-r423.jsonl"
GOLD = REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

#: R423 — the gate is judged with the R419 board's exact instrument
#: (`openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3`) so its absolute
#: levels can be read against the published board instead of against a different
#: judge. Two things made this a defect worth pinning:
#: 1. ``--repeats`` here is the JUDGE's repetitions, not the gate's generations.
#:    They are independent knobs with the same name.
#: 2. The judge identity (including ``:r=K``) is part of the cache KEY, so the
#:    earlier ``r=1`` setting silently produced a second, incompatible cache for
#:    the same rows — every verdict re-bought, and the ``_judge_runs=3``
#:    min-max bands the report quotes would have been n/a.
JUDGE_PROVIDER = "openrouter"
JUDGE_MODEL = "qwen/qwen3-235b-a22b-2507"
JUDGE_REPEATS = 3
#: Seed the gate's cache from the board's, so a row whose answer is unchanged
#: (every curated/deterministic row, which is ~30 % of the board) is not judged
#: twice. Identical answers share a key; different ones simply miss.
JUDGE_CACHE_SEED = REPO / "docs/measurements/r419/judge-cache-r419-qwen235.jsonl"

#: The CORRECTED run (R423 defects 5.1a/5.1b fixed): the first `r423-need` pair
#: had its generations replayed by the route cache and is kept on disk as the
#: void run.
LABEL = "r423-need3"
REPEATS = 3
ARMS = ("A", "B")  # A = lever OFF, B = lever ON
#: Below this many comparable rows the gate refuses to publish a delta. Set from
#: the measured Stage-2 reachability, not from taste: on R419, 81/110 rows were
#: primary-served, so a 37-row stride should yield ~21-26 comparable rows and 20
#: is the run-becoming-degenerate line.
COMPARABLE_FLOOR = 20
#: A row counts as comparable when the PRIMARY leg served the graded answer in at
#: least this many of its samples, in BOTH arms. Requiring all 3 would drop rows
#: for one transport hiccup out of six calls (each call is either the primary
#: transport or a degraded fallback, and a degraded answer cannot show a prompt
#: effect); requiring 1 would let a single lucky generation speak for the arm.
#: The threshold is symmetric, and every row either arm lost is reported.
MIN_PRIMARY_SAMPLES = 2
BOOTSTRAP = 4000


def _ckpt(label: str, arm: str, sample: int) -> Path:
    stem = f"official-{label}-{arm}-hard"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def _score_artifact(label: str, arm: str, sample: int, mode: str = "hard") -> Path:
    from evals.official.score_arm import OUT_DIR

    return Path(OUT_DIR) / f"score-{label}-{arm}-s{sample}-{mode}.json"


def run_scores(label: str = LABEL) -> None:
    """Score each checkpoint with the official instrument (cached judge calls).

    R423 — ``label`` is a PARAMETER, not the module constant. It used to read
    ``LABEL`` while ``main`` read ``--label`` for the sidecar, so
    ``--label r423-need3 --score`` graded r423-need2's checkpoints and then
    reported them against r423-need3's verdict: a scorer that silently answers a
    question about a different run than the one it printed.
    """
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
            print(f"  scoring {ckpt.name} -> {label}")
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


def _load_rows(path: Path) -> dict[str, dict[str, Any]]:
    return {
        json.loads(line)["id"]: json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _served_by(row: dict[str, Any]) -> str:
    return str((row.get("provenance") or {}).get("stage2_served_by") or "")


def _heads(refs: Iterable[str]) -> set[str]:
    from evals.bench import metrics as bench_metrics

    return set(bench_metrics.article_heads(list(refs)))


def _row_metrics(artifact_row: dict[str, Any]) -> dict[str, float]:
    criteria = artifact_row.get("criteria_text") or []
    passed = sum(1 for c in (artifact_row.get("criteria") or []) if c)
    n = len(criteria) or 0
    return {
        "ans_loose": (passed / n) if n else 0.0,
        "ans_strict": 1.0 if n and passed == n else 0.0,
        "answer_chars": float(artifact_row.get("answer_chars") or 0),
        "tone": 1.0 if artifact_row.get("tone_ok") else 0.0,
        "ref_strict": _ref_strict(artifact_row),
    }


def _ref_strict(row: dict[str, Any]) -> float:
    expected = [str(r).strip() for r in (row.get("expected_refs") or []) if str(r).strip()]
    if not expected:
        return float("nan")
    got = {str(r).strip() for r in (row.get("refs") or [])}
    hit = sum(1 for e in expected if e in got)
    return hit / len(expected)


def _median(values: list[float]) -> float:
    clean = [v for v in values if v == v]  # drop NaN
    return statistics.median(clean) if clean else float("nan")


def _bootstrap_ci(deltas: list[float], *, draws: int = BOOTSTRAP) -> tuple[float, float]:
    if len(deltas) < 5:
        return float("nan"), float("nan")
    rng = random.Random(20260917)
    means = []
    for _ in range(draws):
        sample = [deltas[rng.randrange(len(deltas))] for _ in deltas]
        means.append(statistics.fmean(sample))
    means.sort()
    return means[int(0.025 * draws)], means[int(0.975 * draws) - 1]


#: row id -> {arm: [sample indices served by the primary leg]}, filled during the
#: comparability pass so the per-row medians use only the samples that could show
#: the lever.
_PRIMARY_SAMPLES: dict[str, dict[str, list[int]]] = {}


def _gold_reference_answers() -> dict[str, str]:
    """Reference-answer text per row id.

    The score artifact stores ``reference_chars`` but not the reference text, and
    the answer-conciseness axis is measured AGAINST that text — so the board is
    recomputed against the same gold ``score_arm`` itself reads.
    """
    out: dict[str, str] = {}
    if not GOLD.exists():
        return out
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        gold_row = json.loads(line)
        out[str(gold_row.get("id"))] = gold_row.get("reference_answer") or ""
    return out


def official_axes(
    artifacts: dict[str, dict[int, dict[str, Any]]],
    comparable: list[str],
    gold_ref: dict[str, str],
) -> dict[str, Any]:
    """All EIGHT official axes on the paired comparable subset.

    The gate's headline axes are the ones the lever can plausibly move, but a
    lever that shortens answers can also cost reference conciseness or tone, and
    the official aggregate is a GEOMETRIC mean — so a win on one axis that is paid
    for on another has to be visible rather than inferred. Every axis is
    recomputed through :func:`evals.official.rubric.score_rows` on exactly the rows
    that passed the comparability filter, in both arms, then reduced per axis by a
    MEDIAN over the generations.
    """
    from evals.official.rubric import AXIS_ORDER, score_rows  # noqa: PLC0415

    def _board(arm: str, sample: int) -> dict[str, float]:
        rows = []
        for row_id in comparable:
            r = artifacts[arm][sample][row_id]
            rows.append(
                {
                    "criteria": r.get("criteria") or [],
                    "answer": r.get("answer") or "",
                    "reference_answer": gold_ref.get(row_id, ""),
                    "references": r.get("refs") or [],
                    "expected_refs": r.get("expected_refs") or [],
                    "tone_ok": r.get("tone_ok"),
                    "latency_s": r.get("latency_s"),
                }
            )
        return score_rows(rows)

    per_arm: dict[str, dict[str, list[float]]] = {arm: {} for arm in ARMS}
    for arm in ARMS:
        for sample in range(REPEATS):
            result = _board(arm, sample)
            for axis in (*AXIS_ORDER, "overall"):
                per_arm[arm].setdefault(axis, []).append(float(result[axis]))

    def _r(value: float) -> float | None:
        # A ref axis is undefined when BOTH arms' subset holds no annotated refs
        # in a generation. None keeps that out of the report as null instead of
        # writing a bare NaN, which is not valid JSON.
        return None if value != value else round(value, 2)

    axes: dict[str, Any] = {}
    for axis in (*AXIS_ORDER, "overall"):
        a_med = _median(per_arm["A"][axis])
        b_med = _median(per_arm["B"][axis])
        axes[axis] = {
            "A": _r(a_med),
            "B": _r(b_med),
            "delta_pp": _r(b_med - a_med),
            "A_by_sample": [_r(v) for v in per_arm["A"][axis]],
            "B_by_sample": [_r(v) for v in per_arm["B"][axis]],
        }
    return {"subset_n": len(comparable), "axes": axes}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--score", action="store_true", help="run score_arm on the 6 checkpoints first")
    ap.add_argument("--label", default=LABEL)
    a = ap.parse_args()

    if a.score:
        run_scores(a.label)

    # ── 1. The void guard decides first ────────────────────────────────────
    payload_path = RESULTS / f"official-{a.label}.json"
    guard: dict[str, Any] = {}
    if payload_path.exists():
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        guard = payload.get("gate") or {}
    for m, v in guard.items():
        for label, arm in (v or {}).get("arms", {}).items():
            # R423 — which LEG carried the full 53 kB system prompt, and how much
            # of each leg was dialled at all. Printed before the verdict so a
            # reader can see the transport shape the verdict was made on.
            legs = arm.get("legs") or {}
            lens = arm.get("leg_system_lengths") or {}
            if legs:
                shape = ", ".join(
                    f"{leg}={legs[leg]} (system "
                    f"{min(lens.get(leg) or [0])}-{max(lens.get(leg) or [0])} ch)"
                    for leg in sorted(legs)
                )
                print(f"  [{m}] {label}: {shape}; fallback_attempts="
                      f"{arm.get('fallback_attempts')}, primary_failed="
                      f"{arm.get('primary_failed')}, refused_by_provider="
                      f"{arm.get('refused_by_provider')}")
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
        print(f"  WARNING: no gate verdict in {payload_path.name} yet (still running?)")

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
        arm: [ _load_rows(_ckpt(a.label, arm, s)) for s in range(REPEATS) ] for arm in ARMS
    }

    # ── 3. Symmetric comparability filter ──────────────────────────────────
    ids = [r["id"] for r in (artifacts["A"][0].values())]
    comparable: list[str] = []
    dropped: dict[str, list[str]] = {}
    partial: dict[str, int] = {}

    def _drop(reason: str, row_id: str) -> None:
        dropped.setdefault(reason, []).append(row_id)

    for row_id in ids:
        missing = any(
            row_id not in artifacts[arm][s] or row_id not in ckpts[arm][s]
            for arm in ARMS for s in range(REPEATS)
        )
        if missing:
            _drop("missing_from_an_artifact", row_id)
            continue
        keep: dict[str, list[int]] = {}
        for arm in ARMS:
            served = [
                s for s in range(REPEATS)
                if _served_by(ckpts[arm][s][row_id]) == "primary"
            ]
            keep[arm] = served
            if len(served) < MIN_PRIMARY_SAMPLES:
                seen = sorted({
                    _served_by(ckpts[arm][s][row_id]) or "none" for s in range(REPEATS)
                })
                _drop(f"arm_{arm}_not_primary[{'+'.join(seen)}]", row_id)
        if len(keep['A']) < MIN_PRIMARY_SAMPLES or len(keep['B']) < MIN_PRIMARY_SAMPLES:
            continue
        if len(keep['A']) < REPEATS or len(keep['B']) < REPEATS:
            partial[row_id] = len(keep['A']), len(keep['B'])
        comparable.append(row_id)
        _PRIMARY_SAMPLES[row_id] = keep

    per_row: list[dict[str, Any]] = []
    for row_id in comparable:
        entry: dict[str, Any] = {"id": row_id}
        for arm in ARMS:
            samples = _PRIMARY_SAMPLES[row_id][arm]
            metrics = [_row_metrics(artifacts[arm][s][row_id]) for s in samples]
            for key in ("ans_loose", "ans_strict", "answer_chars", "tone", "ref_strict"):
                entry[f"{key}_{arm}"] = _median([m[key] for m in metrics])
            entry[f"n_primary_{arm}"] = len(samples)
            # R423 — draw-to-draw spread, per row. Two R419 rows had credited
            # criteria that flipped between generations, so a row whose credit
            # is not reproducible across samples must be visible rather than
            # silently contributing its median to the arm's mean.
            loose = [m["ans_loose"] for m in metrics]
            strict = [m["ans_strict"] for m in metrics]
            entry[f"ans_loose_spread_{arm}"] = round(max(loose) - min(loose), 4) if loose else 0.0
            entry[f"ans_strict_flip_{arm}"] = bool(len(set(strict)) > 1)
            refs = artifacts[arm][samples[0]][row_id]
            entry[f"dropped_heads_{arm}"] = sorted(
                _heads(refs.get("expected_refs") or []) - _heads(refs.get("refs") or [])
            )
        entry["delta_ans_loose"] = entry["ans_loose_B"] - entry["ans_loose_A"]
        entry["delta_ans_strict"] = entry["ans_strict_B"] - entry["ans_strict_A"]
        entry["delta_answer_chars"] = entry["answer_chars_B"] - entry["answer_chars_A"]
        entry["delta_tone"] = entry["tone_B"] - entry["tone_A"]
        entry["delta_ref_strict"] = entry["ref_strict_B"] - entry["ref_strict_A"]
        per_row.append(entry)

    #: Axes whose per-row delta is an absolute count, not a share. Scaling those
    #: by 100 turns "2048 fewer characters" into "204789 pp", which is what the
    #: first version of this report printed for `delta_answer_chars`.
    char_axes = {"delta_answer_chars"}

    def _agg(key: str) -> dict[str, Any]:
        deltas = [r[key] for r in per_row if r[key] == r[key]]
        if not deltas:
            return {"n": 0}
        scale = 1.0 if key in char_axes else 100.0
        lo, hi = _bootstrap_ci(deltas)
        return {
            "n": len(deltas),
            "units": "chars" if scale == 1.0 else "pp",
            "mean_delta_pp": round(scale * statistics.fmean(deltas), 2),
            "median_delta_pp": round(scale * statistics.median(deltas), 2),
            "ci95_pp": [round(scale * lo, 2), round(scale * hi, 2)],
            "rows_improved": sum(1 for d in deltas if d > 1e-9),
            "rows_worsened": sum(1 for d in deltas if d < -1e-9),
            "rows_tied": sum(1 for d in deltas if abs(d) <= 1e-9),
        }

    # ── 3b. The full official board on the SAME comparable subset ──────────
    board = official_axes(artifacts, comparable, _gold_reference_answers())

    report: dict[str, Any] = {
        "label": a.label,
        "repeats": REPEATS,
        "official_board": board,
        "guard": guard,
        "rows_requested": len(ids),
        "rows_comparable": len(comparable),
        "rows_with_a_partial_sample": partial,
        "dropped": dropped,
        "comparable_floor": COMPARABLE_FLOOR,
        "min_primary_samples": MIN_PRIMARY_SAMPLES,
        "axes": {
            key: _agg(key)
            for key in (
                "delta_ans_loose", "delta_ans_strict", "delta_answer_chars",
                "delta_tone", "delta_ref_strict",
            )
        },
        "level": {
            "mean_answer_chars_A": round(statistics.fmean(r["answer_chars_A"] for r in per_row), 1)
            if per_row else None,
            "mean_answer_chars_B": round(statistics.fmean(r["answer_chars_B"] for r in per_row), 1)
            if per_row else None,
            "median_answer_chars_A": round(statistics.median(r["answer_chars_A"] for r in per_row), 1)
            if per_row else None,
            "median_answer_chars_B": round(statistics.median(r["answer_chars_B"] for r in per_row), 1)
            if per_row else None,
            "mean_ans_loose_A": round(100 * statistics.fmean(r["ans_loose_A"] for r in per_row), 2)
            if per_row else None,
            "mean_ans_loose_B": round(100 * statistics.fmean(r["ans_loose_B"] for r in per_row), 2)
            if per_row else None,
            "mean_ans_strict_A": round(100 * statistics.fmean(r["ans_strict_A"] for r in per_row), 2)
            if per_row else None,
            "mean_ans_strict_B": round(100 * statistics.fmean(r["ans_strict_B"] for r in per_row), 2)
            if per_row else None,
        },
        "draw_dispersion": {
            "rows_with_unstable_criteria": {
                arm: sum(1 for r in per_row if r[f"ans_loose_spread_{arm}"] > 1e-9)
                for arm in ARMS
            },
            "rows_with_strict_flip": {
                arm: sum(1 for r in per_row if r[f"ans_strict_flip_{arm}"])
                for arm in ARMS
            },
            "mean_ans_loose_spread_pp": {
                arm: round(
                    100 * statistics.fmean(r[f"ans_loose_spread_{arm}"] for r in per_row), 2
                ) if per_row else None
                for arm in ARMS
            },
        },
        "gold_head_drops": {
            "A": sum(len(r["dropped_heads_A"]) for r in per_row),
            "B": sum(len(r["dropped_heads_B"]) for r in per_row),
            "A_rows": sum(1 for r in per_row if r["dropped_heads_A"]),
            "B_rows": sum(1 for r in per_row if r["dropped_heads_B"]),
        },
        "per_row": per_row,
    }
    (OUT / "need_gate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("=" * 88)
    print(f"R423 need-proportional gate  |  label={a.label}  repeats={REPEATS}")
    print("=" * 88)
    print(f"rows requested {report['rows_requested']}  comparable {report['rows_comparable']} "
          f"(floor {COMPARABLE_FLOOR})")
    for key, ids_ in report["dropped"].items():
        print(f"  dropped {key}: {len(ids_)}  {', '.join(ids_[:8])}{' ...' if len(ids_) > 8 else ''}")
    if report["rows_with_a_partial_sample"]:
        print(f"  partial samples (>= {MIN_PRIMARY_SAMPLES} primary of {REPEATS}): "
              f"{json.dumps(report['rows_with_a_partial_sample'])}")
    for key, agg in report["axes"].items():
        if not agg.get("n"):
            print(f"  {key:<22} no data")
            continue
        unit = agg.get("units", "pp")
        pad = "" if unit == "pp" else " "
        print(f"  {key:<22} {agg['mean_delta_pp']:+10.2f} {unit}{pad}  "
              f"(median {agg['median_delta_pp']:+.2f}, CI95 "
              f"[{agg['ci95_pp'][0]:+.2f}, {agg['ci95_pp'][1]:+.2f}])  "
              f"{agg['rows_improved']} up / {agg['rows_worsened']} down / {agg['rows_tied']} tied")
    print()
    print(f"  official board on the comparable subset (n={board['subset_n']}), "
          "per-axis MEDIAN over the generations:")
    print(f"    {'axis':<26}{'A (OFF)':>10}{'B (ON)':>10}{'delta':>10}")
    for axis, vals in board["axes"].items():
        def _fmt(value: float | None, sign: bool = False) -> str:
            if value is None:
                return f"{'n/a':>10}"
            return f"{value:>+10.2f}" if sign else f"{value:>10.2f}"

        print(f"    {axis:<26}{_fmt(vals['A'])}{_fmt(vals['B'])}"
              f"{_fmt(vals['delta_pp'], sign=True)}")
    print()
    for key, value in report["level"].items():
        print(f"  {key:<24}{value}")
    disp = report["draw_dispersion"]
    print(f"  draw dispersion          unstable-criteria rows A "
          f"{disp['rows_with_unstable_criteria']['A']} / B "
          f"{disp['rows_with_unstable_criteria']['B']} "
          f"(mean spread {disp['mean_ans_loose_spread_pp']['A']} / "
          f"{disp['mean_ans_loose_spread_pp']['B']} pp); strict-flip rows A "
          f"{disp['rows_with_strict_flip']['A']} / B {disp['rows_with_strict_flip']['B']}")
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
        chars = report["axes"]["delta_answer_chars"]
        # R423b — the official aggregate is a GEOMETRIC mean, so a shortening
        # lever that costs another axis has to be refused on the aggregate and
        # not only on the three axes it was aimed at.
        overall_delta = board["axes"]["overall"]["delta_pp"]
        if overall_delta is None:
            overall_delta = float("-inf")
        verdict = "SHIP (default ON)" if (
            ans_loose["mean_delta_pp"] > -1.0
            and ans_strict["mean_delta_pp"] > -1.0
            and chars["mean_delta_pp"] < 0
            and overall_delta >= -0.5
            and report["gold_head_drops"]["B"] <= report["gold_head_drops"]["A"]
        ) else "KEEP OFF"
        print(f"VERDICT: {verdict}  (official overall "
              f"{board['axes']['overall']['A']} -> "
              f"{board['axes']['overall']['B']}, {overall_delta:+.2f} pp)")
    print(f"\nwrote {OUT / 'need_gate.json'}")


if __name__ == "__main__":
    main()
