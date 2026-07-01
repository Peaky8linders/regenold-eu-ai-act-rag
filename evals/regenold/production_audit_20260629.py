"""R263 — parses the user-supplied production audit dump + Antifragile
expert-review set into a judge-compatible row list.

Source: ``regenold_questions_and_live_answers.md`` (user-attached, two
sections):

1. 99-row production ``/ask`` audit dump (2026-06-29) — live captured
   answer + references, no gold.
2. 20-row Antifragile AI expert review — live answer + citations +
   a free-text expert critique (kept as auxiliary signal for the
   adversarial-triage pass only; the calibrated 4-axis judge never
   sees it, to stay unbiased / blind per the R257 precedent).

Output rows match the schema ``evals/judge/runner.py`` expects:
``id / category / question / predicted_answer / pred_refs``
(``expected_keywords`` / ``expected_refs`` left empty — judged on the
model's own EU AI Act knowledge, same as R257).

Pure stdlib. No network calls.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _split_refs(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw.lower() in ("(none)", "none", "—", "-"):
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


_PROD_ENTRY_RE = re.compile(
    r"^##\s+(\d+)\.\s+\[(?P<ts>[^\]]+)\]\s+—\s+(?P<status>.+?)\s*$\n"
    r"\n+\*\*Q:\*\*\s+(?P<q>.+?)\n"
    r"\n+\*\*Live answer:\*\*\s+(?P<a>.+?)\n"
    r"\n+\*\*References:\*\*\s+(?P<refs>.+?)\s*$",
    re.MULTILINE | re.DOTALL,
)

_ANTIFRAGILE_HEADER_RE = re.compile(r"^##\s+Q(\d+)\.\s+(?P<q>.+?)\s*$", re.MULTILINE)
_AF_LIVE_ANSWER_RE = re.compile(r"\*\*Live answer:\*\*\s+(?P<a>.+?)\n\n+\*\*Citations:\*\*", re.DOTALL)
_AF_CITATIONS_RE = re.compile(r"\*\*Citations:\*\*\s+(?P<refs>.+?)(?:\n\n+\*\*Antifragile review:\*\*\s+(?P<review>.+))?\s*$", re.DOTALL)
# Source-quirk: 3 of 20 entries (Q9/Q15/Q18) embed the reviewer's critique
# INLINE inside the "Live answer" field (e.g. "... Analysis: Wrong by
# omission. ...") instead of under a separate "**Antifragile review:**"
# heading. Split the live-answer text at that inline marker so the
# PREDICTED ANSWER fed to the judge is the system's answer only, never
# the reviewer's own critique glued onto it.
_AF_INLINE_ANALYSIS_RE = re.compile(r"\s+Analysis:\s+(?P<review>.+)$", re.DOTALL)


def _parse_antifragile_entry(num: int, body: str) -> dict[str, Any]:
    m_live = _AF_LIVE_ANSWER_RE.search(body)
    assert m_live, f"Q{num}: no Live answer / Citations boundary found"
    a_raw = m_live.group("a")
    m_cit = _AF_CITATIONS_RE.search(body)
    assert m_cit, f"Q{num}: no Citations field found"
    refs_raw = m_cit.group("refs")
    review = (m_cit.group("review") or "").strip()
    if not review:
        # Inline-embedded critique case (Q9/Q15/Q18 source quirk).
        m_inline = _AF_INLINE_ANALYSIS_RE.search(a_raw)
        if m_inline:
            review = m_inline.group("review")
            a_raw = a_raw[: m_inline.start()]
    return {
        "answer": " ".join(a_raw.split()),
        "refs": _split_refs(" ".join(refs_raw.split())),
        "review": " ".join(review.split()),
    }


def parse_source(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    # Split into File 1 / File 2 sections on the H1 markers.
    file1_marker = "# File 1 — Production audit dump"
    file2_marker = "# File 2 — Antifragile AI Review"
    i1 = text.find(file1_marker)
    i2 = text.find(file2_marker)
    assert i1 != -1 and i2 != -1, "source markdown shape changed"
    file1_text = text[i1:i2]
    file2_text = text[i2:]

    prod_rows: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for m in _PROD_ENTRY_RE.finditer(file1_text):
        num = int(m.group(1))
        status = m.group("status").strip()
        q = " ".join(m.group("q").split())
        a = " ".join(m.group("a").split())
        refs = _split_refs(" ".join(m.group("refs").split()))
        # Dedup exact-duplicate questions — keep first occurrence,
        # the later identical asks are a known R256-era non-determinism
        # artifact already documented/fixed, not a fresh finding.
        key = q.lower().strip()
        is_dup = key in seen_questions
        seen_questions.add(key)
        prod_rows.append({
            "id": f"prod_{num:03d}",
            "category": "production_audit",
            "question": q,
            "predicted_answer": a,
            "pred_refs": refs,
            "expected_keywords": [],
            "expected_refs": [],
            "source_status": status,
            "timestamp": m.group("ts"),
            "is_duplicate_question": is_dup,
        })

    af_rows: list[dict[str, Any]] = []
    headers = list(_ANTIFRAGILE_HEADER_RE.finditer(file2_text))
    for i, hm in enumerate(headers):
        num = int(hm.group(1))
        q = " ".join(hm.group("q").split())
        start = hm.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(file2_text)
        body = file2_text[start:end]
        parsed_entry = _parse_antifragile_entry(num, body)
        af_rows.append({
            "id": f"af_q{num:02d}",
            "category": "antifragile_review",
            "question": q,
            "predicted_answer": parsed_entry["answer"],
            "pred_refs": parsed_entry["refs"],
            "expected_keywords": [],
            "expected_refs": [],
            "expert_review_auxiliary": parsed_entry["review"],
        })

    return {
        "source": str(md_path),
        "production_rows": prod_rows,
        "antifragile_rows": af_rows,
        "production_total": len(prod_rows),
        "production_unique": sum(1 for r in prod_rows if not r["is_duplicate_question"]),
        "antifragile_total": len(af_rows),
    }


def build_judge_sidecar(parsed: dict[str, Any], *, dedup: bool = True) -> dict[str, Any]:
    """Build a sidecar shaped like the bench/v2 runners produce, so
    ``evals.judge.runner`` can consume it unmodified via the
    ``rows`` bucket key."""
    rows: list[dict[str, Any]] = []
    for r in parsed["production_rows"]:
        if dedup and r["is_duplicate_question"]:
            continue
        rows.append({k: v for k, v in r.items() if k != "is_duplicate_question"})
    for r in parsed["antifragile_rows"]:
        # Strip the auxiliary review field for the BLIND calibrated judge —
        # it must not see the expert critique, only question + answer + refs.
        row = {k: v for k, v in r.items() if k != "expert_review_auxiliary"}
        rows.append(row)
    return {
        "role": "live_production_eval",
        "win_measure": "this judge run + evals.harness.ab_judge for any shipped fix",
        "label": "r263-production-audit-20260629",
        "rows": rows,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--no-dedup", action="store_true")
    args = parser.parse_args()

    parsed = parse_source(args.source)
    print(
        f"production: {parsed['production_total']} rows "
        f"({parsed['production_unique']} unique) | "
        f"antifragile: {parsed['antifragile_total']} rows"
    )
    sidecar = build_judge_sidecar(parsed, dedup=not args.no_dedup)
    print(f"sidecar rows: {len(sidecar['rows'])}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    # Also dump the raw parse (with auxiliary review text) for the
    # adversarial-triage pass.
    raw_out = args.out.with_name(args.out.stem + "-raw.json")
    raw_out.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    print(f"wrote {args.out} + {raw_out}")


if __name__ == "__main__":
    main()
