"""R419 — the full 110-question live HARD run as a readable report.

WHAT THIS PRODUCES
------------------
``docs/reports/r419-live-hard-questions-and-answers.md``: for every row of the
official 110, the question, the VERBATIM pushback the official template sent as
turn 2, both answers, the wire references, the serving leg and latency — and, when
:mod:`evals.official.score_arm` has run, the judge's per-criterion verdicts with
its remarks and the tone verdict.

Two sources, neither re-derived:

* the run checkpoint (``evals/bench/results/official-r419-hard-hard.ckpt.jsonl``)
  for what was actually sent and returned;
* ``evals.regenold.official_batch.load_official_batch()`` for the question and the
  pushback text, so the report cannot paraphrase a prompt the evaluator will
  compare against;
* ``docs/measurements/r388/score-r419-hard-hard.json`` (optional) for the verdicts
  — the same artifact the axis table is computed from, so the report and the
  scorecard can never disagree about a row.

    # answers only (no judge needed)
    .venv/Scripts/python.exe -m docs.measurements.r419.build_qa_report

    # with the judged verdicts appended
    .venv/Scripts/python.exe -m docs.measurements.r419.build_qa_report --scores docs/measurements/r388/score-r419-hard-hard.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

CKPT = REPO / "evals" / "bench" / "results" / "official-r419-hard-hard.ckpt.jsonl"
SUMMARY = REPO / "evals" / "bench" / "results" / "official-r419-hard.json"
#: The judge-free half (reference axes, conciseness, speed, gold-head retention,
#: serving-leg mix) — written by ``live_sample_read``, not recomputed here.
DETERMINISTIC_READ = REPO / "docs" / "measurements" / "r419" / "live_hard_read.json"
OUT = REPO / "docs" / "reports" / "r419-live-hard-questions-and-answers.md"

_LEG = {"primary": "Claude-Max wrapper (tunnel)", "fallback": "Bedrock fallback",
        "deterministic": "deterministic Stage-1", "": "—"}


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _leg(prov: dict[str, Any]) -> str:
    raw = str(prov.get("stage2_served_by") or "")
    model = str(prov.get("stage2_model") or "")
    base = _LEG.get(raw, raw or "—")
    return f"{base} ({model})" if model else base


def _quote(text: str) -> str:
    body = (text or "").strip() or "_(empty answer)_"
    return body.replace("\r\n", "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(CKPT))
    ap.add_argument("--scores", default=None, help="score_arm output JSON (adds the verdicts)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    from evals.regenold.official_batch import load_official_batch  # noqa: PLC0415

    rows = _load_jsonl(Path(a.ckpt))
    official = {r.id: r for r in load_official_batch()}
    judged: dict[str, dict] = {}
    if a.scores and Path(a.scores).exists():
        sc = json.loads(Path(a.scores).read_text(encoding="utf-8"))
        judged = {r["id"]: r for r in sc.get("rows") or []}
        axes = sc.get("axes") or {}
    else:
        sc = {}
        axes = {}

    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    run_stats = (summary.get("baseline") or summary.get("branch") or {}).get("hard") or {}
    det = (
        json.loads(DETERMINISTIC_READ.read_text(encoding="utf-8")).get("multi_turn_hard", {})
        if DETERMINISTIC_READ.exists()
        else {}
    )
    det_signals = det.get("signals") or {}
    det_axes = det.get("axes_served_rows") or {}

    # Derive the header stats from the ARTIFACTS (the checkpoint and the
    # judge-free read) so the report never prints a placeholder for a number
    # that is sitting in the row data. The summary, when it carries a field,
    # still wins — it is the only source for the no-call signals.
    _answers = [(r.get("pred_answer") or "") for r in rows]
    _derived = {
        "errors": sum(1 for r in rows if r.get("http_status") not in (200, None))
        or sum(1 for a in _answers if not a.strip()),
        "n_refs": (sum(len(r.get("pred_refs") or []) for r in rows) / len(rows))
        if rows
        else 0.0,
        "answer_chars": (sum(len(a) for a in _answers) / len(rows)) if rows else 0.0,
        "stage2_landed_rate": round(
            100.0
            * sum(
                1
                for r in rows
                if (r.get("provenance") or {}).get("stage2_polish") is True
            )
            / len(rows),
            2,
        )
        if rows
        else 0.0,
    }
    for _k, _v in det_signals.items():
        if _k in ("refusal_rate", "errors"):
            _derived[_k] = _v
    run_stats = {**_derived, **{k: v for k, v in run_stats.items() if v not in (None, "")}}

    lines: list[str] = []
    lines.append("# Antifragile AI — R419 live HARD run: 110 questions, answers and verdicts")
    lines.append("")
    lines.append(
        "**Run** `r419-hard` · hard mode (rolling multi-turn, then the official adversarial "
        "pushback) · in-process engine on merged `main` (`7ef9df05`) · Stage-2 primary = the "
        "Claude-Max wrapper via the cloudflared tunnel."
    )
    lines.append("")
    lines.append(
        f"**Rows** {len(rows)} · **errors** {run_stats.get('errors', '—')} · "
        f"**refusal rate** {run_stats.get('refusal_rate', '—')} · "
        f"**Stage-2 landed** {run_stats.get('stage2_landed_rate', '—')} · "
        f"**mean refs** {round(run_stats.get('n_refs', 0), 2) or '—'} · "
        f"**mean answer chars** {round(run_stats.get('answer_chars', 0)) or '—'} · "
        f"**pushback changed the reference set** on "
        f"{sum(1 for r in rows if (r.get('pushback') or {}).get('ref_heads_changed'))} rows."
    )
    lines.append("")
    if det_axes:
        lines.append(
            "**Judge-free axes** (same run, computed from the checkpoint and the gold): "
            f"ref_loose {det_axes.get('ref_correctness_loose')} · "
            f"ref_strict {det_axes.get('ref_correctness_strict')} · "
            f"ref_conc {det_axes.get('ref_conciseness')} · "
            f"ans_conc {det_axes.get('ans_conciseness')} · "
            f"speed {det_axes.get('resp_speed')}"
        )
        lines.append("")
    if det_signals:
        legs = det_signals.get("leg_mix") or {}
        lines.append(
            "**Serving leg** "
            + " · ".join(f"{k} {v}" for k, v in sorted(legs.items()))
            + f" · **gold heads dropped** {det_signals.get('gold_head_dropped_total')} "
            f"({', '.join(r['id'] for r in det_signals.get('gold_head_dropped_rows') or []) or 'none'})"
            f" · **conceded** {det_signals.get('conceded_rows')}"
            f" · **head Jaccard** {det_signals.get('mean_ref_head_jaccard')}"
        )
        lines.append("")
    lines.append("")
    if axes:
        lines.append("## Judged axes (this run)")
        lines.append("")
        lines.append("| axis | value |")
        lines.append("| :--- | ---: |")
        for k in (
            "ans_correctness_loose",
            "ans_correctness_strict",
            "ans_conciseness",
            "ref_correctness_loose",
            "ref_correctness_strict",
            "ref_conciseness",
            "regulatory_tone",
            "resp_speed",
            "overall",
        ):
            if k in axes:
                lines.append(f"| {k} | {axes[k]:.2f} |")
        lines.append("")
        lines.append(
            f"_Instrument: {sc.get('judge_identity', '—')}. Criteria and reference answers are "
            "reconstructed — compare arms under this instrument, not with the evaluator's own "
            "figures._"
        )
        lines.append("")
    lines.append("---")
    lines.append("")

    for r in rows:
        o = official.get(r["id"])
        prov = r.get("provenance") or {}
        pb = r.get("pushback") or {}
        t1, graded = r.get("turn1_answer") or "", r.get("pred_answer") or ""
        j = judged.get(r["id"])
        head = (
            f"### {r['id']} · {r.get('difficulty_category') or '—'} · "
            f"turn-1 {len(t1):,} chars → graded {len(graded):,} chars"
        )
        if j is not None:
            n = len(j.get("criteria") or [])
            passed = j.get("n_criteria_passed")
            head += f" · **judge {passed}/{n}** · tone {'PASS' if j.get('tone_ok') else 'FAIL'}"
        lines.append(head)
        lines.append("")
        lines.append("**Question**")
        lines.append("")
        lines.append("> " + (r.get("question") or "").strip().replace("\n", "\n> "))
        lines.append("")
        if o is not None:
            lines.append("**Pushback sent as turn 2 (official template, verbatim)**")
            lines.append("")
            lines.append("> " + o.pushback_content().strip().replace("\n", "\n> "))
            lines.append("")
        lines.append(
            f"**Turn-1 answer** — refs: {', '.join(r.get('turn1_refs') or []) or '—'} · "
            f"{r.get('turn1_latency_ms', 0) / 1000:.1f} s"
        )
        lines.append("")
        lines.append(_quote(t1))
        lines.append("")
        lines.append(
            f"**Graded answer (turn 2)** — served by **{_leg(prov)}** · polish "
            f"{'yes' if prov.get('stage2_polish') else 'no'} · "
            f"{r.get('pushback_latency_ms', 0) / 1000:.1f} s · "
            f"refs: {', '.join(r.get('pred_refs') or []) or '—'}"
        )
        lines.append("")
        lines.append(_quote(graded))
        lines.append("")
        if j is not None:
            lines.append("**Judge verdict**")
            lines.append("")
            lines.append("| # | criterion | verdict | remark |")
            lines.append("| ---: | :--- | :---: | :--- |")
            for i, (crit, ok) in enumerate(
                zip(j.get("criteria_text") or [], j.get("criteria") or [], strict=False),
                start=1,
            ):
                remark = (j.get("criterion_remarks") or [""] * i)[i - 1] or ""
                remark = str(remark).replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {i} | {str(crit).replace('|', chr(92) + '|')} | "
                             f"{'✅' if ok else '❌'} | {remark} |")
            lines.append("")
            lines.append(f"_Tone: {'PASS' if j.get('tone_ok') else 'FAIL'} — "
                         f"{str(j.get('tone_remark') or '').replace(chr(10), ' ')}_")
            lines.append("")
        if pb:
            lines.append(
                f"<sub>pushback effect: answer_changed={pb.get('answer_changed')} · "
                f"ref_heads_changed={pb.get('ref_heads_changed')} · "
                f"head Jaccard {pb.get('ref_head_jaccard')} · conceded={pb.get('conceded')}</sub>"
            )
            lines.append("")
        lines.append("---")
        lines.append("")

    dest = Path(a.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines), encoding="utf-8")
    # ``dest`` may be given as a relative path (the CLI default), which
    # ``relative_to`` rejects against an absolute REPO — fall back to the
    # path as given rather than failing after the report is already written.
    try:
        _shown = dest.relative_to(REPO)
    except ValueError:
        _shown = dest
    print(f"wrote {_shown}  ({len(rows)} rows, judged {len(judged)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
