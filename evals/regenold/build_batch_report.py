"""R290 — assemble every answered batch question into one markdown report.

Reads the checkpoint sidecars written by
:mod:`evals.regenold.run_official_batch` (easy + hard) and
:mod:`evals.regenold.run_june_batch`, and emits a single markdown file
containing every question with its live answer and references.

Reads the ``.ckpt.jsonl`` checkpoints rather than the final ``.json``
summaries, so a partially-completed or interrupted run still produces a
complete report of everything answered so far.

Usage
-----
    python -m evals.regenold.build_batch_report \\
        --label r290-live \\
        --out docs/reviews/R290-live-batch-answers.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_RESULTS = _REPO / "evals" / "bench" / "results"


def _read_ckpt(path: Path) -> list[dict[str, Any]]:
    """Read a checkpoint jsonl, keeping the LAST record per id (re-runs win)."""
    if not path.exists():
        return []
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = str(rec.get("id") or len(by_id))
        if rid not in by_id:
            order.append(rid)
        by_id[rid] = rec
    return [by_id[r] for r in order]


def _fmt_refs(refs: list[str]) -> str:
    return ", ".join(str(r) for r in refs) if refs else "_(none)_"


_AXIS_LABEL = {
    "answer_correctness": "Answer",
    "reference_correctness": "References",
    "citation_faithfulness": "Citation faithfulness",
}


def _load_judge(path: Path) -> dict[str, dict[str, Any]]:
    """Map row-id -> per-axis verdicts from a ``grounded-<label>.json``."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("rows") or []:
        rid = str(row.get("id") or "")
        if rid:
            out[rid] = row.get("verdicts") or {}
    return out


def _judge_block(verdicts: dict[str, Any]) -> list[str]:
    """Render the grounded-judge remarks for one answer."""
    if not verdicts:
        return []
    cells: list[str] = []
    for axis, label in _AXIS_LABEL.items():
        v = verdicts.get(axis) or {}
        verdict = str(v.get("verdict") or "?").lower()
        mark = "PASS" if verdict == "pass" else ("FAIL" if verdict == "fail" else "?")
        bits: list[str] = []
        if axis == "reference_correctness":
            if v.get("precision") is not None:
                bits.append(f"P={v['precision']}")
            if v.get("recall") is not None:
                bits.append(f"R={v['recall']}")
            if v.get("wrong"):
                bits.append(f"wrong={v['wrong']}")
            if v.get("missing"):
                bits.append(f"missing={v['missing']}")
        elif axis == "answer_correctness":
            for k in ("incorrect", "unsupported", "missing"):
                if v.get(k):
                    bits.append(f"{k}={v[k]}")
        else:
            if v.get("mismatched"):
                bits.append(f"mismatched={v['mismatched']}")
        fm = str(v.get("failure_mode") or "").strip()
        if fm and fm.lower() not in ("none", "n/a", "-"):
            bits.append(fm)
        detail = (" — " + "; ".join(bits)) if bits else ""
        cells.append(f"{label}: **{mark}**{detail}")
    return ["\n**Judge (grounded, Sonnet-5 vs verbatim Act text):**\n"] + [
        f"\n- {c}\n" for c in cells
    ]


def _judge_rollup(rows: list[dict[str, Any]], judge: dict[str, dict[str, Any]]) -> str:
    """One-line pass-rate rollup across the three grounded axes."""
    if not judge:
        return ""
    parts: list[str] = []
    for axis, label in _AXIS_LABEL.items():
        seen = [judge.get(str(r.get("id"))) for r in rows]
        vals = [
            str(((v or {}).get(axis) or {}).get("verdict") or "").lower()
            for v in seen
            if v
        ]
        graded = [x for x in vals if x in ("pass", "fail")]
        if graded:
            rate = sum(1 for x in graded if x == "pass") / len(graded)
            parts.append(f"{label} {rate:.0%} ({sum(1 for x in graded if x == 'pass')}/{len(graded)})")
    return ("\n\n**Grounded-judge pass rates:** " + " · ".join(parts) + "\n") if parts else ""


def _section(
    title: str,
    note: str,
    rows: list[dict[str, Any]],
    judge: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    judge = judge or {}
    out: list[str] = [f"\n---\n\n# {title}\n", f"{note}\n"]
    ok = [r for r in rows if not r.get("error")]
    errs = [r for r in rows if r.get("error")]

    if rows:
        lats = [r["latency_ms"] for r in ok if r.get("latency_ms")]
        refcounts = [len(r.get("pred_refs") or []) for r in ok]
        out.append(
            f"**{len(ok)} answered** · {len(errs)} errored · "
            f"mean refs {statistics.mean(refcounts):.2f} · "
            f"p50 latency {statistics.median(lats) / 1000:.1f}s\n"
            if ok
            else f"**0 answered** · {len(errs)} errored\n"
        )
        out.append(_judge_rollup(ok, judge))

    for i, rec in enumerate(rows, 1):
        qid = rec.get("id", f"row_{i}")
        out.append(f"\n## {i}. `{qid}`\n")
        out.append(f"**Q:** {rec.get('question', '').strip()}\n")
        if rec.get("error"):
            out.append(f"\n**ERROR:** `{rec['error']}` (HTTP {rec.get('http_status')})\n")
            continue
        answer = (rec.get("pred_answer") or "").strip()
        out.append(f"\n**A:** {answer}\n")
        out.append(f"\n**References:** {_fmt_refs(rec.get('pred_refs') or [])}\n")

        # Hard mode records both turns. ``pred_answer`` above is already the
        # post-pushback answer (the graded one); show turn 1 for the diff.
        if rec.get("pushback_answer"):
            turn1 = (rec.get("turn1_answer") or "").strip()
            if turn1 and turn1 != answer:
                out.append(f"\n<details><summary>Turn 1 (pre-pushback)</summary>\n\n{turn1}\n\n")
                out.append(f"References: {_fmt_refs(rec.get('turn1_refs') or [])}\n\n</details>\n")
            pb = rec.get("pushback") or {}
            conceded = pb.get("conceded")
            if conceded is not None:
                out.append(f"\n**Conceded to pushback:** `{conceded}`\n")

        out.extend(_judge_block(judge.get(str(qid)) or {}))

        meta = []
        if rec.get("latency_ms"):
            meta.append(f"{rec['latency_ms'] / 1000:.1f}s")
        vs = rec.get("vs_june") or rec.get("vs_jul07")
        if vs:
            added = vs.get("ref_head_added") or []
            dropped = vs.get("ref_head_dropped") or []
            if added:
                meta.append(f"refs added vs prior: {', '.join(added)}")
            if dropped:
                meta.append(f"refs dropped vs prior: {', '.join(dropped)}")
        if meta:
            out.append(f"\n<sub>{' · '.join(meta)}</sub>\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--endpoint", default="(live production wire)")
    args = ap.parse_args()

    sources = [
        (
            _RESULTS / f"official-{args.label}-easy.ckpt.jsonl",
            _RESULTS / f"grounded-{args.label}-easy.json",
            "Batch 1 — Regenold official set, EASY mode",
            "Each question asked standalone (single turn), exactly as the "
            "graded 2026-07-07 run posed it.",
        ),
        (
            _RESULTS / f"official-{args.label}-hard.ckpt.jsonl",
            _RESULTS / f"grounded-{args.label}-hard.json",
            "Batch 2 — Regenold official set, HARD mode",
            "The same questions inside a growing multi-turn conversation, "
            "followed by the adversarial pushback turn "
            "(*\"I don't think this is correct. Perhaps your answer contains "
            "hallucinations...\"*). The graded answer is the post-pushback one.",
        ),
        (
            _RESULTS / f"june-{args.label}.ckpt.jsonl",
            _RESULTS / f"grounded-{args.label}-june.json",
            "Batch 3 — end-of-June set (2026-06-29 production audit + Antifragile review)",
            "The question set captured in `regenold_questions_and_live_answers.md`, "
            "re-asked against the current deployment so June and now can be diffed.",
        ),
    ]

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc: list[str] = [
        f"# Regenold live batch answers + grounded-judge remarks — `{args.label}`\n",
        f"\nGenerated {stamp} · endpoint: {args.endpoint}\n",
        "\n## How to read this (fresh-session context)\n",
        "\nEvery question below was asked against the **live production wire** and the "
        "answer recorded verbatim with its reference list. This is a live "
        "measurement, not a local bench run — the deterministic davidath bench "
        "(`python -m evals.bench.runner`) is only the regression guard and cannot "
        "see Stage-2 behaviour at all (it runs `provider=cli`).\n",
        "\n**EASY vs HARD.** The Regenold graded run poses each question twice: once "
        "standalone (easy), and once inside a growing multi-turn conversation "
        "followed by an adversarial pushback turn (*\"I don't think this is correct. "
        "Perhaps your answer contains hallucinations... Let's try again:\"*). The "
        "graded hard answer is the **post-pushback** one, so `conceded=True` on any "
        "row means the system abandoned a correct answer under pressure — the single "
        "most important failure mode in that set.\n",
        "\n**The judge.** `evals/judge/grounded.py` (Sonnet-5) scores each answer "
        "against the **verbatim EU AI Act text** (`app.data.provision_text`), not "
        "against a gold label set — so an incomplete gold list cannot penalise a "
        "correct-but-broader citation, nor reward a wrong one the gold happens to "
        "omit. Three independent axes, each pass/fail with a short `failure_mode`:\n",
        "\n- **Answer** — is the substance correct per the Act's text?\n",
        "- **References** — of the cited provisions, which genuinely GOVERN the "
        "question (precision), and which governing provisions are MISSING (recall)?\n",
        "- **Citation faithfulness** — does the prose actually describe each cited "
        "provision (the cite-and-mismatch check)?\n",
        "\nReproduce with:\n",
        "\n```bash\npython -m evals.regenold.run_official_batch --label <lbl> --mode both "
        "--endpoint <url> --api-key $REGENOLD_API_KEY\n"
        "python -m evals.judge.grounded --sidecar evals/bench/results/official-<lbl>-easy.ckpt.jsonl "
        "--label <lbl>-easy --provider wrapper\n"
        "python -m evals.regenold.build_batch_report --label <lbl> --out <path.md>\n```\n",
    ]

    totals: list[str] = []
    all_sections: list[str] = []
    for path, judge_path, title, note in sources:
        rows = _read_ckpt(path)
        if not rows:
            totals.append(f"- {title}: _not run_")
            continue
        judge = _load_judge(judge_path)
        ok = sum(1 for r in rows if not r.get("error"))
        jn = f" · judged {len(judge)}" if judge else " · _not judged_"
        totals.append(f"- {title}: **{ok} answered** / {len(rows)} rows{jn}")
        all_sections.extend(_section(title, note, rows, judge))

    doc.append("\n## Contents\n\n" + "\n".join(totals) + "\n")
    doc.extend(all_sections)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _REPO / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(doc), encoding="utf-8")
    print(f"wrote {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")
    for t in totals:
        print("  " + t)


if __name__ == "__main__":
    main()
