"""Build an auditable Markdown scorecard with every per-criterion judge remark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


AXES = (
    ("ans_correctness_loose", "Answer correctness (loose)"),
    ("ans_correctness_strict", "Answer correctness (strict)"),
    ("ans_conciseness", "Answer conciseness"),
    ("ref_correctness_loose", "Reference correctness (loose)"),
    ("ref_correctness_strict", "Reference correctness (strict)"),
    ("ref_conciseness", "Reference conciseness"),
    ("regulatory_tone", "Regulatory tone"),
    ("resp_speed", "Response speed"),
    ("overall", "Overall (geometric mean)"),
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(value: object) -> str:
    return "—" if value is None else f"{float(value):.2f}%"


def _quote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in str(text).splitlines()]


def build_report(
    score: dict,
    *,
    baseline: dict | None = None,
    capture_path: Path | None = None,
) -> str:
    axes = score["axes"]
    base_axes = (baseline or {}).get("axes") or {}
    official = score.get("official_reference") or {}
    frontier = official.get("frontier_2026") or {}
    lines = [
        f"# {score['label']} — live hard-mode evaluation",
        "",
        f"- Rows: **{axes.get('n', 0)}**",
        f"- Judge: `{score.get('judge_identity', 'unknown')}`",
        f"- Checkpoint: `{score.get('ckpt', '')}`",
    ]
    if capture_path:
        lines.append(f"- Capture log: `{capture_path}`")
    lines.extend(
        [
            "- Method: reconstructed R388 rubric; three judge repetitions at temperature 0.1.",
            "- Caveat: criteria and reference keys are reconstructed, not evaluator-published gold.",
            "",
            "## Scorecard and uplift",
            "",
            "| Axis | This run | Prior live | Uplift | 2026 frontier | Gap |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for key, label in AXES:
        current = axes.get(key)
        prior = base_axes.get(key)
        front = frontier.get(key)
        delta = None if current is None or prior is None else float(current) - float(prior)
        gap = None if current is None or front is None else float(current) - float(front)
        lines.append(
            f"| {label} | {_cell(current)} | {_cell(prior)} | "
            f"{'—' if delta is None else f'{delta:+.2f} pp'} | {_cell(front)} | "
            f"{'—' if gap is None else f'{gap:+.2f} pp'} |"
        )

    live_rows = [r for r in score.get("rows") or [] if r.get("criteria") is not None]
    judge_errors = sum(1 for r in live_rows if not r.get("criterion_remarks"))
    lines.extend(
        [
            "",
            "## Operational diagnostics",
            "",
            f"- Mean answer length: **{axes.get('_mean_answer_chars', 0):.1f} characters**",
            f"- Mean references: **{axes.get('_mean_refs_per_row', 0):.3f}**",
            f"- Mean latency: **{axes.get('_mean_latency_s', 0):.3f} seconds**",
            f"- Reference-scored rows: **{axes.get('n_ref_scored', 0)}**",
            f"- Rows missing persisted criterion remarks: **{judge_errors}**",
            "",
            "## Per-question judge report",
            "",
        ]
    )
    for row in score.get("rows") or []:
        verdicts = list(row.get("criteria") or [])
        criteria = list(row.get("criteria_text") or [])
        remarks = list(row.get("criterion_remarks") or [])
        passed = sum(1 for value in verdicts if value)
        lines.extend(
            [
                f"### {row['id']} — {passed}/{len(criteria)} criteria",
                "",
                *(_quote(row.get("question") or "")),
                "",
                f"References: `{', '.join(row.get('refs') or []) or 'none'}`",
                "",
            ]
        )
        for idx, criterion in enumerate(criteria):
            ok = verdicts[idx] if idx < len(verdicts) else False
            remark = remarks[idx] if idx < len(remarks) else ""
            lines.append(f"{idx + 1}. **{'PASS' if ok else 'FAIL'}** — {criterion}")
            if remark:
                lines.append(f"   - Judge: {remark}")
        lines.extend(
            [
                "",
                f"Tone: **{'PASS' if row.get('tone_ok') else 'FAIL'}**"
                + (f" — {row['tone_remark']}" if row.get("tone_remark") else ""),
                "",
                "Answer:",
                "",
                *(_quote(row.get("answer") or "")),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(
        _load(args.score),
        baseline=_load(args.baseline) if args.baseline else None,
        capture_path=args.capture,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
