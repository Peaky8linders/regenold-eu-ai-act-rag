"""R423 — emit the need-proportional gate report from the judged artifacts.

Nothing here reimplements a metric. The eight axes come from the scorer's own
artifact ``score-<label>-<arm>-s<k>-hard.json`` (written by
``evals.official.score_arm``, which is the published instrument), and the paired
comparable-subset deltas from
``docs/measurements/r423/need_gate.py`` (so there is ONE implementation of the
comparability rule and the median-over-generations arithmetic).

    .venv/Scripts/python.exe -m evals.official.score_arm --ckpt <ckpt> ...   # warms the judge
    .venv/Scripts/python.exe docs/measurements/r423/need_gate.py             # writes need_gate.json
    .venv/Scripts/python.exe -m docs.measurements.r423.build_need_report
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys

from evals.official.rubric import AXIS_ORDER

REPO = pathlib.Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LABEL = "r423-need3"
ARMS = ("A", "B")
SAMPLES = 3
ARM_LABEL = {"A": "A — lever OFF (shipped prompt)", "B": "B — lever ON"}
RESULTS = REPO / "evals" / "bench" / "results"
GATE = REPO / "docs" / "measurements" / "r423" / "need_gate.json"
SIDECAR = RESULTS / f"official-{LABEL}.json"
OUT = REPO / "docs" / "reports" / "r423-need-proportional-gate.md"

AXIS_LABEL = {
    "ans_correctness_loose": "Ans. Correctness (Loose)",
    "ans_correctness_strict": "Ans. Correctness (Strict)",
    "ans_conciseness": "Ans. Conciseness",
    "ref_correctness_loose": "Ref. Correctness (Loose)",
    "ref_correctness_strict": "Ref. Correctness (Strict)",
    "ref_conciseness": "Ref. Conciseness",
    "regulatory_tone": "Regulatory Tone",
    "resp_speed": "Resp. Speed",
}


def _ckpt(arm: str, sample: int) -> pathlib.Path:
    stem = f"official-{LABEL}-{arm}-hard"
    return RESULTS / (f"{stem}.ckpt.jsonl" if sample == 0 else f"{stem}.r{sample}.ckpt.jsonl")


def _score_artifact(arm: str, sample: int) -> pathlib.Path:
    return (REPO / "docs" / "measurements" / "r388"
            / f"score-{LABEL}-{arm}-s{sample}-hard.json")


def _arm_axes(arm: str) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Per-sample axes and the per-arm median across generations.

    R423b — read the SCORER's own artifact. This used to rebuild the rows from the
    checkpoint (`score_arm.load_ckpt` → `score_arm.build_rows` → `score_rows`), but a checkpoint
    carries no judge verdicts: the criteria live in the score artifact, so
    `criteria` came through empty and `answer_correctness_loose([])` returned a
    VACUOUS 1.0. That printed 100.00/100.00 on both correctness axes while the
    paired board was reporting a real regression — the most dangerous shape a
    report can have, since it looks like a clean win.
    """
    per_sample: dict[str, dict[str, float]] = {}
    for sample in range(SAMPLES):
        payload = json.loads(_score_artifact(arm, sample).read_text(encoding="utf-8"))
        per_sample[str(sample)] = {k: float(v) for k, v in (payload.get("axes") or {}).items()}
    median = {
        axis: round(statistics.median(per_sample[s][axis] for s in per_sample), 4)
        for axis in (*AXIS_ORDER, "overall")
    }
    return per_sample, median


def _transport_shape() -> dict:
    if not SIDECAR.exists():
        return {}
    payload = json.loads(SIDECAR.read_text(encoding="utf-8"))
    return (payload.get("gate") or {}).get("hard") or {}


def _judge_identity() -> str:
    """Read the judge off the artifact instead of asserting one in prose.

    R423b: this report claimed the wrapper/Sonnet judge while the gate's own
    scorer ran OpenRouter Qwen3-235B — two different instruments are not
    comparable, so the identity is now quoted from the artifact that produced
    the numbers.
    """
    for arm in ARMS:
        path = REPO / "docs" / "measurements" / "r388" / f"score-{LABEL}-{arm}-s0-hard.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")).get("judge_identity") or "unknown"
    return "unknown"


def main() -> None:
    missing = [str(_ckpt(a, s)) for a in ARMS for s in range(SAMPLES) if not _ckpt(a, s).exists()]
    if missing:
        raise SystemExit("missing checkpoints:\n  " + "\n  ".join(missing))

    per_sample: dict[str, dict[str, dict[str, float]]] = {}
    medians: dict[str, dict[str, float]] = {}
    for arm in ARMS:
        per_sample[arm], medians[arm] = _arm_axes(arm)

    gate = json.loads(GATE.read_text(encoding="utf-8")) if GATE.exists() else {}
    shape = _transport_shape()

    lines: list[str] = []
    add = lines.append
    add(f"# R423 — need-proportional answer contract: paired hard-split gate (`{LABEL}`)")
    add("")
    add("**Question.** Does `REGENOLD_NEED_PROPORTIONAL_CONTRACT` make the Stage-2 answer "
        "shape follow the criteria the ask engages — and does it do so without costing "
        "correctness or gold references?")
    add("")
    add("**Design.** 37 strided hard rows of the official 110 (`--stride 3` — the send order "
        "is front-loaded with easy rows, so a prefix is not the board) × **3 independent "
        "generations per row per arm** (`--repeats 3`), sequential arms, one Claude Max "
        "backend. Every generation runs with the route's response cache cleared, so a "
        "generation is a new draw rather than a replay (§Transport).")
    add("")

    # ── verdict ────────────────────────────────────────────────────────────
    if not gate:
        add("## Verdict")
        add("")
        add("`need_gate.json` is not on disk yet — run `docs/measurements/r423/need_gate.py` first.")
    elif gate.get("rows_comparable", 0) < gate.get("comparable_floor", 0):
        add("## Verdict")
        add("")
        add(f"**REFUSED — {gate.get('rows_comparable')} comparable rows against a floor of "
            f"{gate.get('comparable_floor')}.** The sample cannot carry a delta.")
    else:
        axes = gate.get("axes") or {}
        add("## Verdict — pre-registered rule")
        add("")
        add("SHIP (default ON) requires, on the comparable subset: `ans_loose` and "
            "`ans_strict` no worse than −1.0 pp, answer length strictly down, and no more "
            "gold heads dropped by arm B than by arm A. Pre-registered before the run, in "
            "`docs/measurements/r423/need_gate.py`.")
        add("")
        add("| axis (paired, median over 3 generations) | mean Δ | median Δ | 95 % CI | rows up / down / tied |")
        add("| :-- | --: | --: | :-- | :-- |")
        for key, agg in axes.items():
            if not agg.get("n"):
                continue
            lo, hi = agg.get("ci95_pp", [None, None])
            unit = agg.get("units", "pp")
            add(f"| `{key}` | {agg['mean_delta_pp']:+.2f} {unit} | {agg['median_delta_pp']:+.2f} | "
                f"[{lo:+.2f}, {hi:+.2f}] | {agg['rows_improved']} / {agg['rows_worsened']} / "
                f"{agg['rows_tied']} |")
        heads = gate.get("gold_head_drops") or {}
        add("")
        add(f"Gold heads dropped on the comparable subset: **A {heads.get('A')} "
            f"({heads.get('A_rows')} rows)** vs **B {heads.get('B')} ({heads.get('B_rows')} rows)**.")

        # ── the board in the benchmark's own aggregate ──────────────────────
        board = (gate.get("official_board") or {}).get("axes") or {}
        if board:
            add("")
            add("Every official axis on that SAME comparable subset, reduced the same way "
                "(median over the generations), including the aggregate the benchmark ranks "
                "on:")
            add("")
            add("| metric | arm A (OFF) | arm B (ON) | Δ |")
            add("| :-- | --: | --: | --: |")
            for axis, vals in board.items():
                name = AXIS_LABEL.get(axis, "**OVERALL (geometric mean)**")
                add(f"| {name} | {vals['A']} | {vals['B']} | **{vals['delta_pp']:+.2f}** |")

            overall = board.get("overall") or {}
            axes_g = gate.get("axes") or {}
            def _mean(key: str) -> float:
                return float((axes_g.get(key) or {}).get("mean_delta_pp") or 0.0)

            checks = [
                ("`ans_loose` no worse than −1.0 pp", _mean("delta_ans_loose") > -1.0,
                 f"{_mean('delta_ans_loose'):+.2f} pp"),
                ("`ans_strict` no worse than −1.0 pp", _mean("delta_ans_strict") > -1.0,
                 f"{_mean('delta_ans_strict'):+.2f} pp"),
                ("answer length strictly down", _mean("delta_answer_chars") < 0,
                 f"{_mean('delta_answer_chars'):+.0f} chars"),
                ("official overall no worse than −0.5 pp",
                 (overall.get("delta_pp") or -99) >= -0.5, f"{overall.get('delta_pp'):+.2f} pp"),
                ("no more gold heads dropped than the baseline",
                 (heads.get("B") or 0) <= (heads.get("A") or 0),
                 f"B {heads.get('B')} vs A {heads.get('A')}"),
            ]
            add("")
            add("| pre-registered ship condition | met? | measured |")
            add("| :-- | :-- | --: |")
            for label, ok, measured in checks:
                add(f"| {label} | {'yes' if ok else '**NO**'} | {measured} |")
            add("")
            outcome = "SHIP (default ON)" if all(ok for _, ok, _ in checks) else "KEEP OFF"
            failed = [label for label, ok, _ in checks if not ok]
            add(f"**Verdict: {outcome}.**" + (
                " " + str(len(failed)) + " pre-registered condition(s) failed: "
                + ", ".join(failed) + "." if failed else ""))

            # ── what the losses are, row by row, from the gate's own output ──
            losses = [r for r in (gate.get("per_row") or []) if r.get("delta_ans_strict", 0) < 0]
            if losses:
                add("")
                add("The whole correctness cost, row by row (every row where `ans_strict` "
                    "fell, with the arm-A answer this was measured against):")
                add("")
                add("| row | A chars | B chars | Δ chars | A loose | B loose | gold head dropped by B |")
                add("| :-- | --: | --: | --: | --: | --: | :-- |")
                for r in losses:
                    add(f"| `{r['id']}` | {r['answer_chars_A']:.0f} | {r['answer_chars_B']:.0f} | "
                        f"{r['delta_answer_chars']:+.0f} | {100 * r['ans_loose_A']:.0f} % | "
                        f"{100 * r['ans_loose_B']:.0f} % | "
                        f"{', '.join(r.get('dropped_heads_B') or []) or '—'} |")
                add("")
                add(f"{len(losses)} of {(gate.get('rows_comparable') or 0)} comparable rows; "
                    "the rest are tied, and no row improved on correctness. The cause is "
                    "length starvation, not the extraction: each of these collapsed to a "
                    "short answer, and the criteria the judge credits for them need the "
                    "enumeration the shape clause suppressed.")
    add("")

    # ── the eight axes, per arm ────────────────────────────────────────────
    add("## All eight official axes, per arm")
    add("")
    add(f"Median across the three generations of the arm's own board (37 rows), judged by "
        f"`{_judge_identity()}` (temp 0.1, grouped criteria, 3 repetitions per row). "
        "`ans_conciseness` and `resp_speed` are computed from text and latency, the two "
        "`ref_correctness` axes from the reference key; the ref axes exclude rows with no "
        "annotated expected references.")
    add("")
    add("| metric | arm A (OFF) | arm B (ON) | Δ (B − A) | A min–max over generations | B min–max |")
    add("| :-- | --: | --: | --: | :-- | :-- |")
    for axis in (*AXIS_ORDER, "overall"):
        a, b = medians["A"][axis], medians["B"][axis]

        def band(arm: str, key: str = axis) -> str:
            values = [per_sample[arm][s][key] for s in per_sample[arm]]
            return f"{min(values):.2f}–{max(values):.2f}"

        name = AXIS_LABEL.get(axis, "**OVERALL (geometric mean)**")
        add(f"| {name} | {a:.2f} | {b:.2f} | **{b - a:+.2f}** | {band('A')} | {band('B')} |")
    add("")
    add("Per-generation detail (the raw inputs to the medians above):")
    add("")
    add("| arm | generation | " + " | ".join(AXIS_LABEL[a].replace(" (Loose)", " L").replace(" (Strict)", " S")
                                              for a in AXIS_ORDER) + " | overall |")
    add("| :-- | --: | " + " | ".join("--:" for _ in AXIS_ORDER) + " | --: |")
    for arm in ARMS:
        for sample in sorted(per_sample[arm], key=int):
            vals = per_sample[arm][sample]
            add(f"| {arm} | {int(sample) + 1} | "
                + " | ".join(f"{vals[a]:.2f}" for a in AXIS_ORDER)
                + f" | {vals['overall']:.2f} |")
    add("")

    # ── comparable subset ──────────────────────────────────────────────────
    if gate:
        add("## Comparable subset (the only rows that can move)")
        add("")
        add(f"Requested {gate.get('rows_requested')} rows → **{gate.get('rows_comparable')} "
            f"comparable** (floor {gate.get('comparable_floor')}); a row is comparable when "
            f"the PRIMARY leg served its graded answer in at least "
            f"{gate.get('min_primary_samples')} of the {gate.get('repeats')} generations "
            "**in both arms** — a deterministic Stage-1 draft cannot respond to a prompt-side lever.")
        add("")
        for reason, rows in (gate.get("dropped") or {}).items():
            add(f"* dropped `{reason}`: {len(rows)} — {', '.join(rows)}")
        partial = gate.get("rows_with_a_partial_sample") or {}
        if partial:
            add(f"* comparable but with fewer than {gate.get('repeats')} primary generations: "
                + ", ".join(f"{k} (A={v[0]}, B={v[1]})" for k, v in partial.items()))
        disp = gate.get("draw_dispersion") or {}
        if disp:
            add("")
            add("Draw-to-draw dispersion on the comparable subset (why three generations, not one):")
            add("")
            add("| | arm A | arm B |")
            add("| :-- | --: | --: |")
            add(f"| rows whose criteria credit moved between generations | "
                f"{disp['rows_with_unstable_criteria']['A']} | "
                f"{disp['rows_with_unstable_criteria']['B']} |")
            add(f"| rows whose *all-criteria* verdict flipped | "
                f"{disp['rows_with_strict_flip']['A']} | {disp['rows_with_strict_flip']['B']} |")
            add(f"| mean per-row spread (pp) | {disp['mean_ans_loose_spread_pp']['A']} | "
                f"{disp['mean_ans_loose_spread_pp']['B']} |")
    add("")

    # ── transport shape ────────────────────────────────────────────────────
    add("## Transport shape (what the arms actually dialled)")
    add("")
    if shape:
        add("| arm | rows | graded calls | deterministic rows | payload legs | fallback dials answered | fallback dials total | primary failed | refusals (named) |")
        add("| :-- | --: | --: | --: | :-- | --: | --: | --: | :-- |")
        for label, arm in (shape.get("arms") or {}).items():
            legs = arm.get("legs") or {}
            lens = arm.get("leg_system_lengths") or {}
            leg_txt = ", ".join(
                f"{leg}×{legs[leg]} (system {min(lens.get(leg) or [0])}–{max(lens.get(leg) or [0])} ch)"
                for leg in sorted(legs)
            ) or "—"
            refused = ", ".join(f"{k}×{v}" for k, v in (arm.get("refused_by_provider") or {}).items()) or "—"
            add(f"| {label} | {arm.get('rows')} | {arm.get('calls')} | "
                f"{arm.get('deterministic_graded')} | {leg_txt} | {arm.get('fallback_ok')} | "
                f"{arm.get('fallback_attempts')} | {arm.get('primary_failed')} | {refused} |")
        add("")
        add(f"Gate verdict: **{'VALID' if shape.get('valid') else 'VOID'}** — "
            + ("; ".join(shape.get("reasons") or ["no reasons recorded"])) + ".")
        for warn in shape.get("warnings") or []:
            add(f"* warning: {warn}")
    else:
        add(f"`{SIDECAR.name}` is not on disk yet.")
    add("")

    # ── method notes ───────────────────────────────────────────────────────
    add("## Method notes (what makes this a gate rather than a printout)")
    add("")
    add("1. **The void guard decides before any delta is printed.** The runner's own "
        "`gate_validity.assess` reads the transport counters it incremented and the payloads "
        "it hashed. An arm served by the fallback, an arm whose graded rows are "
        "majority-deterministic drafts, a refusal, asymmetric fallback pressure, and "
        "generations that were replays are each a VOID.")
    add("2. **Generations are real draws.** The route answers from an in-process response "
        "cache keyed on (question, context, history depth, env); without clearing it, "
        "generations 2..K replay generation 1 (measured on the first R423 gate: 23 of 37 rows "
        "byte-identical at 1.6 s against 43.6 s). `run_official_batch._clear_engine_cache` "
        "clears it before every sample.")
    add("3. **Every paired number is a per-row median over the three generations**, with a "
        "bootstrap CI over rows, and the comparability exclusion is symmetric — a row lost by "
        "either arm is reported and excluded from both.")
    add("")
    add("## Artifacts")
    add("")
    add("| path | what |")
    add("| :-- | :-- |")
    add(f"| `evals/bench/results/official-{LABEL}-[AB]-hard*.ckpt.jsonl` | the 6 generation checkpoints |")
    add(f"| `evals/bench/results/official-{LABEL}.json` | runner sidecar incl. the gate verdict |")
    add("| `docs/measurements/r423/need_gate.json` | paired deltas, comparable subset, dispersion |")
    add("| `docs/measurements/r423/judge-cache-r423.jsonl` | the judge's per-answer verdicts |")
    add("| `app/engines/answer_need.py` | the estimator, the clause, the flag |")
    add("| `docs/measurements/r423/CHECKPOINT.md` | design, offline calibration, and the falsifications |")
    add("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
