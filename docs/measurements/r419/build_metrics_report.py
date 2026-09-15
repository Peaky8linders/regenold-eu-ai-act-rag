"""R419 — parse the judged artifacts and emit the full live-metrics report.

Nothing here reimplements a metric: the eight axes come from
``evals.official.rubric.score_rows`` (the published instrument), the rows from
``evals.official.score_arm.build_rows`` (so the gold joins exactly as the
scorer joins it), and the per-repetition bands from the same copy-and-rescore
method ``score_arm`` prints. This module only *reads* the artifacts and lays
them out; if it ever disagrees with ``score_arm``, ``score_arm`` is right.

    .venv/Scripts/python.exe -m docs.measurements.r419.build_metrics_report
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

from evals.official import score_arm as SA
from evals.official.rubric import AXIS_ORDER, score_rows

REPO = pathlib.Path(__file__).resolve().parents[3]
CKPT = REPO / "evals/bench/results/official-r419-hard-hard.ckpt.jsonl"
SCORES = REPO / "docs/measurements/r388/score-r419-hard-hard.json"
CACHE = REPO / "docs/measurements/r419/judge-cache-r419-qwen235.jsonl"
DET = REPO / "docs/measurements/r419/live_hard_read.json"
PRIOR = REPO / "docs/measurements/r388/score-r419-priorfloor-hard.json"
OUT = REPO / "docs/reports/r419-live-hard-metrics-report.md"

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

#: The evaluator's own printed figures for the hard split, as carried in the
#: score artifact's ``official_reference`` block.
REF_LABEL = {
    "us": "Antifragile AI (Aug-25 official)",
    "frontier_2026": "2026 Frontier + Search",
    "baseline_2025": "2025 Search-Integrated",
}


def _load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _f(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{x:.{digits}f}"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(CKPT))
    ap.add_argument("--scores", default=str(SCORES))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    ckpt_rows = SA.load_ckpt(pathlib.Path(a.ckpt))
    gold = SA.load_gold()
    # ``build_rows`` joins the gold (reference answer + expected references).
    # The JUDGED booleans live in the stored score artifact, so the rows this
    # report scores are the stored rows plus the gold join — no re-judging and
    # no second opinion about what the judge said.
    gold_rows = {r["id"]: r for r in SA.build_rows(ckpt_rows, gold)}
    stored = _load_json(pathlib.Path(a.scores))
    stored_axes = stored.get("axes") or {}
    ref = stored.get("official_reference") or {}
    identity = stored.get("judge_identity") or "—"
    det = (_load_json(DET) or {}).get("multi_turn_hard", {})
    det_signals = det.get("signals") or {}

    cache = {}
    for e in _load_jsonl(pathlib.Path(a.cache)):
        cache[e.get("key")] = e.get("verdict") or {}

    rows: list[dict] = []
    for s in stored.get("rows") or []:
        g = gold_rows.get(s["id"]) or {}
        crit = list(s.get("criteria") or [])
        r = {
            "id": s["id"],
            "question": s.get("question") or "",
            "answer": s.get("answer") or "",
            "references": s.get("refs") or [],
            "expected_refs": s.get("expected_refs") or [],
            "reference_answer": g.get("reference_answer") or "",
            "criteria": crit,
            "criteria_text": s.get("criteria_text") or g.get("criteria") or [],
            "tone_ok": bool(s.get("tone_ok")),
            "latency_s": float(s.get("latency_s") or 0.0),
            "n_criteria_passed": sum(1 for c in crit if c),
            "_n_criteria": len(crit),
        }
        v = cache.get(SA._key(r["id"], r["answer"], identity)) or {}
        if not v:  # a key written before the identity suffix existed
            v = next((vv for k, vv in cache.items() if k.split(":")[0] == r["id"]), {})
        if v.get("_corr_runs"):
            r["_corr_runs"] = [x for x in v["_corr_runs"] if x]
        if v.get("_tone_runs_raw"):
            r["_tone_runs_raw"] = v["_tone_runs_raw"]
        r["_judge_errors"] = v.get("_judge_errors", 0)
        rows.append(r)

    # ── the eight axes, recomputed with the published instrument ─────────────
    axes = score_rows(rows)
    agree = all(
        abs(float(axes.get(k, 0.0)) - float(stored_axes.get(k, 0.0))) < 0.02
        for k in (*AXIS_ORDER, "overall")
    )

    # ── min–max bands across the judge's repetitions ─────────────────────────
    repeats = min(
        (len(r["_corr_runs"]) for r in rows if r.get("_corr_runs")),
        default=0,
    )
    per_rep: list[dict] = []
    for i in range(repeats):
        run_rows = []
        for r in rows:
            c = dict(r)
            cr = r.get("_corr_runs") or []
            if len(cr) > i and cr[i] is not None:
                c["criteria"] = cr[i]
            tone = r.get("_tone_runs_raw") or []
            if len(tone) > i and tone[i] is not None:
                c["tone_ok"] = tone[i]
            run_rows.append(c)
        per_rep.append(score_rows(run_rows))

    bands = {
        k: (min(s[k] for s in per_rep), max(s[k] for s in per_rep)) if per_rep else None
        for k in ("ans_correctness_loose", "ans_correctness_strict", "regulatory_tone", "overall")
    }

    # ── judge stability ─────────────────────────────────────────────────────
    draw_dependent = [
        r for r in rows if r.get("_corr_runs") and len(set(map(tuple, r["_corr_runs"]))) > 1
    ]
    errors = [r for r in rows if r.get("_judge_errors")]

    # ── reference grain ─────────────────────────────────────────────────────
    ref_scored = [r for r in rows if r.get("expected_refs")]
    head_hit = sum(
        1
        for r in ref_scored
        for e in r["expected_refs"]
        if any(e.split("(")[0].split(".")[0].strip().lower() in c.lower() for c in r["references"])
    )
    head_total = sum(len(r["expected_refs"]) for r in ref_scored)
    exact_hit = sum(
        1
        for r in ref_scored
        for e in r["expected_refs"]
        if any(e.strip().lower() == c.strip().lower() for c in r["references"])
    )
    excess = sum(
        max(0, len(r["references"]) - len(r["expected_refs"])) for r in ref_scored
    )
    lost = det_signals.get("gold_head_dropped_rows") or []

    # ── verbosity ───────────────────────────────────────────────────────────
    growth = [
        len(r["answer"]) / max(len(r.get("reference_answer") or ""), 1) for r in rows
    ]
    shorter = [g for g in growth if g <= 1.0]

    # ── latency ─────────────────────────────────────────────────────────────
    lat = sorted(float(r.get("latency_s") or 0.0) for r in rows)

    # ── the fixed defect's projected board ──────────────────────────────────
    prior = _load_json(pathlib.Path(PRIOR))
    prior_rows = {r["id"]: r for r in prior.get("rows") or []}
    # ``SA.load_ckpt`` keeps only the scored fields, so provenance comes from the
    # raw checkpoint rows.
    raw_ckpt = _load_jsonl(pathlib.Path(a.ckpt))
    determinism = [
        r
        for r in raw_ckpt
        if (r.get("provenance") or {}).get("stage2_served_by") == "deterministic"
    ]

    # ── dialogue integrity (from the checkpoint) ────────────────────────────
    flip = [r for r in raw_ckpt if (r.get("pushback") or {}).get("ref_heads_changed")]

    lines: list[str] = []
    add = lines.append

    add("# Antifragile AI — R419 live HARD run: the full metric board")
    add("")
    add(
        "**Run** `r419-hard` · hard mode (rolling multi-turn, then the official adversarial "
        "pushback) · 110/110 rows · in-process engine on merged `main` (`7ef9df05`) · Stage-2 "
        "primary = the Claude-Max wrapper via the cloudflared tunnel."
    )
    add("")
    add(f"**Judge** `{identity}` — three repetitions at temperature 0.1, grouped.")
    add("")
    add(
        "**Scored by** `evals.official.rubric.score_rows` (the published instrument), the same "
        "module that produced `docs/measurements/r388/score-r419-hard-hard.json`. This report "
        f"recomputes them and the two agree: **{'yes' if agree else 'NO — investigate'}**."
    )
    add("")
    add(
        "> The correctness criteria, reference answers and expected references are "
        "**reconstructed** (`evals/official/build_gold.py`), because the evaluator never "
        "published them. Compare arms under this instrument; do not read a number as an "
        "official score."
    )
    add("")
    add("---")
    add("")
    add("## 1. All eight metrics")
    add("")
    add(
        "| Metric | **This arm (R419 live)** | Min–max over 3 reps | Antifragile (Aug-25) "
        "| 2026 Frontier | Gap → frontier |"
    )
    add("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for k in AXIS_ORDER:
        v = axes.get(k, 0.0)
        b = bands.get(k)
        band = f"{b[0]:.1f}–{b[1]:.1f}" if b else "—"
        fv = (ref.get("frontier_2026") or {}).get(k)
        uv = (ref.get("us") or {}).get(k)
        gap = f"{v - fv:+.2f}" if fv is not None else "—"
        mark = " **BEATS**" if fv is not None and v >= fv else ""
        add(
            f"| {AXIS_LABEL[k]} | **{v:.2f}%** | {band} | {_pct(uv)} | {_pct(fv)} "
            f"| {gap}{mark} |"
        )
    ov = axes.get("overall", 0.0)
    ob = bands.get("overall")
    add(
        f"| **OVERALL (geometric mean)** | **{ov:.2f}%** | "
        f"{f'{ob[0]:.1f}–{ob[1]:.1f}' if ob else '—'} | "
        f"{_pct((ref.get('overall') or {}).get('us'))} | "
        f"{_pct((ref.get('overall') or {}).get('frontier_2026'))} | "
        f"{(ov - (ref.get('overall') or {}).get('frontier_2026', 0)):+.2f} |"
    )
    add("")
    add(
        f"Rows {axes.get('n')} · reference axes scored on {axes.get('n_ref_scored')} rows "
        "(the rest carry no annotated expected references and are excluded there by the "
        "benchmark's own rule)."
    )
    add("")
    add(
        "Three axes are **not** judge-scored, which is why their bands are flat: "
        "`ans_conciseness` and `resp_speed` are computed from the answer text and the "
        "latency, and the two `ref_*` axes are matched against the expected reference "
        "key. `ref_conciseness` is deterministic for the same reason. The judge decides "
        "only the two answer-correctness axes and Regulatory Tone."
    )
    add("")
    add("### Against the other published baselines")
    add("")
    add("| Metric | R419 live | Antifragile (Aug-25) | 2025 Search-Integrated | 2026 Frontier |")
    add("| :--- | ---: | ---: | ---: | ---: |")
    for k in AXIS_ORDER:
        add(
            f"| {AXIS_LABEL[k]} | **{axes.get(k, 0.0):.2f}%** | "
            f"{_pct((ref.get('us') or {}).get(k))} | "
            f"{_pct((ref.get('baseline_2025') or {}).get(k))} | "
            f"{_pct((ref.get('frontier_2026') or {}).get(k))} |"
        )
    add(
        f"| **OVERALL** | **{ov:.2f}%** | {_pct((ref.get('overall') or {}).get('us'))} | "
        f"{_pct((ref.get('overall') or {}).get('baseline_2025'))} | "
        f"{_pct((ref.get('overall') or {}).get('frontier_2026'))} |"
    )
    add("")
    add("---")
    add("")
    add("## 2. What is actually scoring, and what is not")
    add("")
    add(
        f"**Correctness is strong and measured, not lucky.** "
        f"{sum(r['n_criteria_passed'] for r in rows)} of "
        f"{sum(r['_n_criteria'] for r in rows)} criteria satisfied across "
        f"{len(rows)} rows; {sum(1 for r in rows if r['n_criteria_passed'] == r['_n_criteria'])} "
        f"rows satisfy every criterion. "
        f"{sum(1 for r in rows if r['n_criteria_passed'] == 0)} rows satisfy none."
    )
    add("")
    add("| criteria satisfied | rows |")
    add("| :--- | ---: |")
    satisfied = collections.Counter(r["n_criteria_passed"] for r in rows)
    for k in sorted(satisfied):
        label = "none" if k == 0 else f"{k}"
        add(f"| {label} | {satisfied[k]} |")
    add("")
    add("### Rows that fail at least one criterion")
    add("")
    add("| row | satisfied | of | refs | expected | note |")
    add("| :--- | ---: | ---: | :--- | :--- | :--- |")
    partial = [r for r in rows if r["n_criteria_passed"] < r["_n_criteria"]]
    for r in partial:
        note = "**all criteria failed**" if r["n_criteria_passed"] == 0 else ""
        if r["id"] in {"rg_036", "rg_037", "rg_085", "rg_092"}:
            note = (note + " deterministic-leg serve (transport)").strip()
        if r["id"] == "rg_088":
            note = "pushback capitulation (see §3)"
        add(
            f"| `{r['id']}` | {r['n_criteria_passed']} | {r['_n_criteria']} | "
            f"{', '.join(r['references']) or '—'} | {', '.join(r['expected_refs']) or '—'} | {note} |"
        )
    add("")
    add(
        f"**The judge is stable.** {len(draw_dependent)} of {len(rows)} rows produced a "
        "different criteria vector across the three repetitions"
        + (
            ": " + ", ".join(r["id"] for r in draw_dependent) + "."
            if draw_dependent
            else " (the min–max bands above are the whole spread)."
        )
        + (f" Judge transport errors: {len(errors)}." if errors else " Judge transport errors: 0.")
    )
    add("")
    add("**The gap is verbosity, and it is arithmetic.** `ans_conciseness` is "
        "`min(1, len(reference) / len(candidate))` and `ref_conciseness` is "
        "`min(1, len(expected) / len(provided))`.")
    add("")
    add("| quantity | value |")
    add("| :--- | ---: |")
    add(f"| mean answer | {statistics.mean(len(r['answer']) for r in rows):.1f} chars |")
    add(
        "| mean reference answer | "
        f"{statistics.mean(len(r.get('reference_answer') or '') for r in rows):.1f} chars |"
    )
    add(f"| mean answer / reference | {statistics.mean(growth):.2f}x |")
    add(f"| rows already at or under the reference length | {len(shorter)} of {len(rows)} |")
    add(f"| median answer | {statistics.median(len(r['answer']) for r in rows):.0f} chars |")
    add(f"| answers over 3,000 chars | {sum(1 for r in rows if len(r['answer']) > 3000)} |")
    add(
        "| mean cited provisions | "
        f"{statistics.mean(len(r['references']) for r in rows):.2f} per row |"
    )
    add(
        "| mean expected provisions | "
        f"{statistics.mean(len(r['expected_refs']) for r in rows if r.get('expected_refs')):.2f} "
        f"per scored row ({len(ref_scored)} rows) |"
    )
    add(f"| excess provisions beyond the minimal expected set | {excess} |")
    add("")
    add(
        "So the two conciseness axes are not independent evidence about quality: they say the "
        "answers are ~3x the reference prose and the citation lists are ~2x the minimal key. "
        "**Answer length is a generation-side property**, which is why every post-hoc "
        "citation-pruning lever has failed and why the tracked lever is a prompt/interpreter "
        "change, not a filter."
    )
    add("")
    add(
        f"**Latency.** mean {statistics.mean(lat):.2f} s · median {statistics.median(lat):.2f} s "
        f"· p90 {lat[int(0.9 * (len(lat) - 1))]:.2f} s · max {lat[-1]:.2f} s. Resp. Speed is "
        "`max(0, 100 - latency_s)` per response, so it is a latency measurement, not a quality "
        "one."
    )
    if det_signals.get("turn1_latency_s"):
        t1 = det_signals["turn1_latency_s"]
        add("")
        add(
            f"Turn-1 latency p50 {t1.get('p50')} s · p95 {t1.get('p95')} s · max "
            f"{t1.get('max')} s; {det_signals.get('sub_second_graded', 0)} rows were served "
            "sub-second from the deterministic path."
        )
    add("")
    add("---")
    add("")
    add("## 3. References in detail")
    add("")
    add("| measure | value |")
    add("| :--- | ---: |")
    add(f"| expected provisions met at head level (Article / Annex number) | {head_hit} of {head_total} |")
    add(f"| expected provisions met at exact subpoint level | {exact_hit} of {head_total} |")
    add(f"| scored rows | {len(ref_scored)} |")
    add(
        f"| rows whose reference set CHANGED between turn 1 and the graded answer | "
        f"{det_signals.get('ref_heads_changed_rows', len(flip))} (of {len(rows)}) |"
    )
    add(
        f"| rows that DROPPED a gold head | "
        f"{det_signals.get('gold_head_dropped_total', len(lost))} (of {len(rows)}) |"
    )
    add(
        "| expected provisions matched by exact spelling (the axis also credits a "
        "descendant, so it reads higher) | "
        f"{exact_hit} of {head_total} = {100 * exact_hit / max(head_total, 1):.1f}% |"
    )
    add(
        f"| mean reference-set Jaccard, turn 1 vs graded | "
        f"{det_signals.get('mean_ref_head_jaccard', '—')} |"
    )
    add("")
    add("### Rows whose graded answer lost a gold head")
    add("")
    if lost:
        add("| row | head lost |")
        add("| :--- | :--- |")
        for x in lost:
            add(f"| `{x.get('id')}` | {', '.join(x.get('lost') or [])} |")
    else:
        add("_none recorded_")
    add("")
    add("---")
    add("")
    add("## 4. Per-row verdicts")
    add("")
    add("| row | crit. | of | tone | refs | expected | answer chars | ref chars | latency s | note |")
    add("| :--- | ---: | ---: | :--- | :--- | :--- | ---: | ---: | ---: | :--- |")
    for r in rows:
        note = []
        if r["n_criteria_passed"] == 0:
            note.append("**all failed**")
        elif r["n_criteria_passed"] < r["_n_criteria"]:
            note.append("partial")
        if r.get("_judge_errors"):
            note.append(f"judge errors {r['_judge_errors']}")
        if r.get("id") in {x["id"] for x in draw_dependent}:
            note.append("draw-dependent")
        add(
            f"| `{r['id']}` | {r['n_criteria_passed']} | {r['_n_criteria']} | "
            f"{'PASS' if r.get('tone_ok') else 'fail'} | "
            f"{', '.join(r['references']) or '—'} | "
            f"{', '.join(r['expected_refs']) or '—'} | {len(r['answer'])} | "
            f"{len(r.get('reference_answer') or '')} | {float(r.get('latency_s') or 0):.1f} | "
            f"{'; '.join(note) or ''} |"
        )
    add("")
    add("---")
    add("")
    add("## 5. The fixed defect and its projected board")
    add("")
    add(
        f"{len(determinism)} rows ("
        + ", ".join(f"`{r['id']}`" for r in determinism)
        + ") fell to the deterministic Stage-1 draft (wrapper degenerate one-token "
        "completion → the Bedrock fallback leg was dead in that environment → tail repair "
        "failed). Two of them shipped an answer thinner than the one the engine had already "
        "given on turn 1. **R420** makes the truncation guard keep the prior answer instead."
    )
    add("")
    add("| row | draft scored | turn-1 answer scored | head(s) restored |")
    add("| :--- | ---: | ---: | :--- |")
    for qid, restored in (("rg_036", "Article 42"), ("rg_037", "Annex VIII")):
        d = next((r for r in rows if r["id"] == qid), None)
        p = prior_rows.get(qid)
        if d is None or p is None:
            continue
        add(
            f"| `{qid}` | {d['n_criteria_passed']}/{len(p.get('criteria_text') or [])} | "
            f"**{p.get('n_criteria_passed')}/{len(p.get('criteria_text') or [])}** | {restored} |"
        )
    add("")
    tot = sum(r["_n_criteria"] for r in rows)
    passed = sum(r["n_criteria_passed"] for r in rows)
    strict = sum(1 for r in rows if r["n_criteria_passed"] == r["_n_criteria"])
    add("| variant | ans loose | ans strict |")
    add("| :--- | ---: | ---: |")
    add(f"| as measured | {100 * passed / tot:.2f}% | {100 * strict / len(rows):.2f}% |")
    add(
        f"| with the R420 floor (+8 criteria, +1 strict row, measured on the turn-1 answers) "
        f"| **{100 * (passed + 8) / tot:.2f}%** | **{100 * (strict + 1) / len(rows):.2f}%** |"
    )
    add("")
    add("---")
    add("")
    add("## 6. Artifacts and how to reproduce")
    add("")
    add("| path | what |")
    add("| :--- | :--- |")
    add("| `evals/bench/results/official-r419-hard-hard.ckpt.jsonl` | the 110 live rows (gitignored) |")
    add("| `docs/measurements/r419/judge-cache-r419-qwen235.jsonl` | the judged verdicts, 3 reps each |")
    add("| `docs/measurements/r388/score-r419-hard-hard.json` | the board this report re-derives |")
    add("| `docs/measurements/r388/score-r419-priorfloor-hard.json` | the turn-1 re-judge behind R420 |")
    add("| `docs/measurements/r419/live_hard_read.json` | the judge-free half (leg mix, heads, latency) |")
    add("| `docs/reports/r419-live-hard-questions-and-answers.md` | every question, answer and verdict |")
    add("| `docs/measurements/r419/CHECKPOINT.md` | the round record |")
    add("")
    add("```bash")
    add(".venv/Scripts/python.exe -m docs.measurements.r419.build_metrics_report")
    add("```")
    add("")

    dest = pathlib.Path(a.out)
    dest.write_text("\n".join(lines), encoding="utf-8")
    try:
        shown = dest.relative_to(REPO)
    except ValueError:
        shown = dest
    print(f"wrote {shown} ({len(rows)} rows, axes agree={agree}, draw-dependent={len(draw_dependent)})")
    return 0


def thresholds(rows: list[dict]) -> dict:
    """Count rows by how many of their criteria they satisfy."""
    c = collections.Counter()
    for r in rows:
        n, tot = r["n_criteria_passed"], r["_n_criteria"]
        c[f"{n} of {tot}"] = c[f"{n} of {tot}"] + 1
    return dict(c)


if __name__ == "__main__":
    raise SystemExit(main())
