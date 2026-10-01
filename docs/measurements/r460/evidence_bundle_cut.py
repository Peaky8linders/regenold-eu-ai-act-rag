"""R460 — measure the payload cut over the RECORDED draws (no route, no LLM).

Reads ``stage2-payloads.jsonl`` (written by ``capture_payloads.py``) and reports,
per draw and in aggregate, exactly what each gated lever removes:

* ``system_compact`` — ``REGENOLD_PROMPT_COMPACT=1`` swaps the 60.6k accreted
  system stack for ``COMPACT_ANSWER_SYSTEM``. The USER payload is untouched.
* ``bundle_l1`` / ``bundle_l2`` — the R460 evidence minifier applied to the
  ``EU AI ACT REFERENCES:`` block only. Level 1 drops a provision rendered twice
  under two node ids; level 2 also drops the member lines under a structure
  heading that itself says "NOT ENGAGED ... do NOT enumerate".

Nothing is judged here. This is the SIZE leg; the quality legs (answer,
references, other axes) are the live R448 gate order and are NOT run by this
script. Chars are not tokens — the token column is chars/4 and is labelled as
the rough estimate it is.

Usage::

    .venv\\\\Scripts\\\\python.exe docs/measurements/r460/evidence_bundle_cut.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
CAPTURE = OUT / "stage2-payloads.jsonl"
HEADER = "EU AI ACT REFERENCES:"
CONTRACT_MARKERS = ("ANSWER CONTRACT", "LENGTH LIMIT")


def _evidence_span(user: str) -> tuple[int, int]:
    """Offsets of the evidence block inside the user payload."""
    start = user.find(HEADER)
    if start < 0:
        return -1, -1
    start += len(HEADER)
    if start < len(user) and user[start] == "\n":
        start += 1
    end = len(user)
    for marker in CONTRACT_MARKERS:
        idx = user.find(marker, start)
        if 0 <= idx < end:
            end = idx
    return start, end


def _rows() -> list[dict[str, Any]]:
    if not CAPTURE.exists():
        raise SystemExit(f"missing capture at {CAPTURE}; run capture_payloads.py first")
    return [json.loads(line) for line in CAPTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pct(before: int, after: int) -> float:
    return round(100.0 * (before - after) / before, 2) if before else 0.0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from app.data.graph_rag_prompts import COMPACT_ANSWER_SYSTEM
    from app.engines.evidence_bundle import parse_evidence_block

    compact_system = len(COMPACT_ANSWER_SYSTEM)
    rows = _rows()
    per_row: list[dict[str, Any]] = []
    for row in rows:
        user = row["user"]
        system = row["system"]
        start, end = _evidence_span(user)
        bundle = parse_evidence_block(user)
        bundle.verify()
        evidence_before = bundle.raw
        l1 = bundle.minified(level=1)
        l2 = bundle.minified(level=2)
        user_l1 = user[:start] + l1 + user[end:] if start >= 0 else user
        user_l2 = user[:start] + l2 + user[end:] if start >= 0 else user
        sys_after = compact_system
        per_row.append(
            {
                "id": row["id"],
                "system_before": len(system),
                "system_after": sys_after,
                "evidence_before": len(evidence_before),
                "evidence_l1": len(l1),
                "evidence_l2": len(l2),
                "user_before": len(user),
                "user_bundle_l1": len(user_l1),
                "user_bundle_l2": len(user_l2),
                "total_before": len(system) + len(user),
                "total_compact_system": sys_after + len(user),
                "total_compact_bundle_l2": sys_after + len(user_l2),
                "redundant_items_removed": len(bundle.items) - len(parse_evidence_block(l1).items),
                "l1_lossless_subsequence": l1 == evidence_before
                or _subsequence(l1.split("\n"), list(bundle.lines)),
                "l2_lossless_subsequence": _subsequence(l2.split("\n"), list(bundle.lines)),
            }
        )

    def med(key: str) -> float:
        vals = [int(r[key]) for r in per_row]
        return round(statistics.median(vals), 1)

    totals_before = [int(r["total_before"]) for r in per_row]
    totals_bundle = [int(r["total_compact_bundle_l2"]) for r in per_row]
    report: dict[str, Any] = {
        "draws": len(per_row),
        "compact_system_chars": compact_system,
        "median": {
            "system_before": med("system_before"),
            "system_after": med("system_after"),
            "evidence_before": med("evidence_before"),
            "evidence_l1": med("evidence_l1"),
            "evidence_l2": med("evidence_l2"),
            "user_before": med("user_before"),
            "total_before": med("total_before"),
            "total_compact_system": med("total_compact_system"),
            "total_compact_bundle_l2": med("total_compact_bundle_l2"),
        },
        "median_reduction_pct": {
            "system_compact_only": _pct(med("total_before"), med("total_compact_system")),
            "compact_plus_bundle_l2": _pct(med("total_before"), med("total_compact_bundle_l2")),
            "bundle_l1_on_evidence": _pct(med("evidence_before"), med("evidence_l1")),
            "bundle_l2_on_evidence": _pct(med("evidence_before"), med("evidence_l2")),
        },
        "worst_case_total_before": max(totals_before),
        "worst_case_total_after": max(totals_bundle),
        "all_draws_lossless": all(
            r["l1_lossless_subsequence"] and r["l2_lossless_subsequence"] for r in per_row
        ),
        "token_estimate_chars_div_4": {
            "median_before": round(med("total_before") / 4, 0),
            "median_after": round(med("total_compact_bundle_l2") / 4, 0),
        },
        "per_row": per_row,
    }
    (OUT / "evidence-bundle-cut.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"draws={report['draws']}  compact system={compact_system} chars")
    print(f"median total before      : {report['median']['total_before']}")
    print(f"  system (median)        : {report['median']['system_before']}")
    print(f"  evidence (median)      : {report['median']['evidence_before']}")
    print(f"median total compact sys : {report['median']['total_compact_system']} "
          f"({report['median_reduction_pct']['system_compact_only']}% cut)")
    print(f"median total + bundle L2 : {report['median']['total_compact_bundle_l2']} "
          f"({report['median_reduction_pct']['compact_plus_bundle_l2']}% cut)")
    print(f"evidence cut, L1 / L2    : {report['median_reduction_pct']['bundle_l1_on_evidence']}% / "
          f"{report['median_reduction_pct']['bundle_l2_on_evidence']}%")
    print(f"worst-case total         : {report['worst_case_total_before']} -> "
          f"{report['worst_case_total_after']}")
    print(f"all draws lossless       : {report['all_draws_lossless']}")
    print(f"rough tokens (chars/4)   : {report['token_estimate_chars_div_4']['median_before']} -> "
          f"{report['token_estimate_chars_div_4']['median_after']}")
    print(f"wrote {OUT / 'evidence-bundle-cut.json'}")


def _subsequence(kept: list[str], raw: list[str]) -> bool:
    cursor = 0
    for line in kept:
        while cursor < len(raw) and raw[cursor] != line:
            cursor += 1
        if cursor >= len(raw):
            return False
        cursor += 1
    return True


if __name__ == "__main__":
    main()
