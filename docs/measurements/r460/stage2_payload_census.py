"""R460 — where the Stage-2 payload's characters actually sit (no live LLM).

WHAT THIS MEASURES, AND WHY IT IS THE FIRST STEP.

``docs/measurements/r455/CHECKPOINT.md`` recorded the Stage-2 request at the
provider seam on a single turn: ``system 59,647 + user 54,789 ~= 114,436``
characters. That number is the target of the R460 evidence-bundle cut, but a
TOTAL cannot say which bytes are removable. R448's audit recommendation 4 is
explicit that the extraction must be lossless FIRST and gated SECOND, so this
probe answers, per row and in aggregate:

* the split between the STATIC system instruction stack and the DYNAMIC user
  payload (two different levers with two different gates);
* inside the user payload, how many characters are evidence versus instruction;
* inside the EVIDENCE, which sections dominate, and how many of their
  characters are provably redundant (a provision rendered twice) or explicitly
  marked non-enumerable (a "NOT ENGAGED ... do NOT enumerate" member list).

HOW IT RUNS. The real route, the real retrieval, the real prompt builders - with
the Stage-2 provider stubbed at the provider seam (the R423 probe's pattern).
No network, no spend. ``REGENOLD_QUERY_DENOISER=0`` and
``REGENOLD_EXTERNAL_EMBEDDINGS=0`` remove the two network-dependent legs so runs
are comparable (the same baseline R422/R423 established).

WHAT IT DOES NOT CLAIM. Chars are not tokens. This probe ranks the payload for
the cut and proves what a section contains; the token/latency claim needs a live
gate. Retrieval is not byte-stable across invocations (R423 measured the same
row dispatching 19,206 then 42,782 chars), so per-row totals move with retrieval
and only the AGGREGATE and the section SHARES are read.

Usage::

    R460_ROWS=12 R460_STRIDE=5 .venv\\\\Scripts\\\\python.exe docs/measurements/r460/stage2_payload_census.py
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = Path(__file__).resolve().parent
_PARSED = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["transparency", "instructions for use"],
        "reasoning": "stub parse for the R460 payload census",
    }
)
_ANSWER = (
    "Under Article 13(1) the provider must ensure the system is designed so that "
    "its operation is sufficiently transparent. References: Article 13, Article 13.1."
)
PROBE_BASELINE = {
    "REGENOLD_QUERY_DENOISER": "0",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
}

#: Ordered user-payload sections. Each entry is ``(label, marker)``; the section
#: runs from its marker to the next marker's offset. The first entry has no
#: marker and starts at offset 0.
_USER_MARKERS: tuple[tuple[str, str | None], ...] = (
    ("header", None),
    ("evidence", "EU AI ACT REFERENCES:"),
    ("answer_contract", "ANSWER CONTRACT"),
    ("answer_shape", "ANSWER SHAPE ("),
    ("ref_minimality", " REFERENCE MINIMALITY:"),
    ("subparagraph", " SUB-PARAGRAPH DISCIPLINE:"),
    ("route_keep", " CURATED ROUTE KEEP:"),
    ("length_limit", "LENGTH LIMIT"),
    ("coordinates", "VALID COORDINATES"),
    ("provisions_to_name", "PROVISIONS TO NAME:"),
    ("final_sentence", "COMPLETENESS OF THE FINAL SENTENCE:"),
)

#: Evidence sub-sections, in render order.
_EVIDENCE_SECTIONS: tuple[str, ...] = (
    "APPLICABLE OBLIGATIONS",
    "ARTICLE-SPECIFIC OBLIGATIONS",
    "BACKGROUND OBLIGATIONS",
    "DIMENSION DETAILS",
    "KNOWLEDGE-GRAPH SUB-POINT DETAIL",
    "KNOWLEDGE-GRAPH CROSS-REGULATORY MAPPINGS",
    "VERBATIM PROVISION TEXT",
    "REFERENCED ANNEXES AND RECITALS",
)

_NOT_ENGAGED = "NOT ENGAGED by this question"
_STRUCTURE_OF = "STRUCTURE of "


class _Recorder:
    """Records the TEXT of every payload the engine would dispatch."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def complete(self, request: Any, *_a: Any, **_k: Any) -> SimpleNamespace:
        user = str(getattr(request, "user", "") or "")
        system = str(getattr(request, "system", "") or "")
        stage2 = ("EU AI ACT REFERENCES:" in user) or ("ANSWER CONTRACT" in user)
        self.payloads.append({"stage2": stage2, "system": system, "user": user})
        return SimpleNamespace(
            error=None, text=_ANSWER if stage2 else _PARSED, thinking="",
            finish_reason="stop", model="probe-stub", usage=None,
            latency_ms=1, headers=None,
        )


def _sections(text: str) -> dict[str, int]:
    """Char count per top-level user section, keyed by label."""
    offsets: list[tuple[str, int]] = []
    for label, marker in _USER_MARKERS:
        if marker is None:
            offsets.append((label, 0))
            continue
        idx = text.find(marker)
        if idx < 0:
            continue
        offsets.append((label, idx))
    offsets.sort(key=lambda kv: kv[1])
    out: dict[str, int] = {}
    for i, (label, start) in enumerate(offsets):
        end = offsets[i + 1][1] if i + 1 < len(offsets) else len(text)
        out[label] = end - start
    return out


def _evidence_breakdown(evidence: str) -> dict[str, Any]:
    """Sub-sections + redundancy inside the ``EU AI ACT REFERENCES:`` block."""
    bounds: list[tuple[str, int]] = []
    for head in _EVIDENCE_SECTIONS:
        idx = evidence.find(head)
        if idx >= 0:
            bounds.append((head, idx))
    bounds.sort(key=lambda kv: kv[1])
    per_section: dict[str, int] = {}
    for i, (head, start) in enumerate(bounds):
        end = bounds[i + 1][1] if i + 1 < len(bounds) else len(evidence)
        per_section[head] = end - start

    # NOT-ENGAGED member coordinate lists: a heading says "do NOT enumerate",
    # then the members are spelled out anyway. Count the heading and the
    # indented coordinate lines that follow it.
    not_engaged_headings = 0
    not_engaged_coord_chars = 0
    not_engaged_coord_lines = 0
    pending = False
    for line in evidence.splitlines():
        stripped = line.strip()
        if _NOT_ENGAGED in line and _STRUCTURE_OF in line:
            not_engaged_headings += 1
            pending = True
            continue
        if pending:
            if line.startswith("    ") and stripped:
                not_engaged_coord_chars += len(line) + 1
                not_engaged_coord_lines += 1
                continue
            pending = False

    # Duplicate bullet TEXT (ignore the ``- [id] `` prefix): the same provision
    # surfaced under two node ids is one provision.
    seen: set[str] = set()
    dup_chars = 0
    dup_lines = 0
    for line in evidence.splitlines():
        if not line.startswith("- ["):
            continue
        body = line.split("]", 1)[-1].strip()
        key = " ".join(body.split())
        if len(key) < 60:
            continue
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if digest in seen:
            dup_lines += 1
            dup_chars += len(line) + 1
        else:
            seen.add(digest)

    return {
        "sections": per_section,
        "not_engaged_headings": not_engaged_headings,
        "not_engaged_coord_lines": not_engaged_coord_lines,
        "not_engaged_coord_chars": not_engaged_coord_chars,
        "duplicate_bullet_lines": dup_lines,
        "duplicate_bullet_chars": dup_chars,
        "total_chars": len(evidence),
    }


def _history(depth: int) -> list[dict[str, str]]:
    from evals.regenold.official_batch import trim_history

    history: list[dict[str, str]] = []
    for i in range(depth):
        history = trim_history(
            [
                *history,
                {"role": "user", "content": f"Prior question {i + 1} about the EU AI Act."},
                {"role": "assistant", "content": _ANSWER},
            ]
        )
    return history


def _route(row: Any, depth: int) -> dict[str, Any]:
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider
    from evals.regenold.official_batch import build_hard_messages
    from evals.regenold.runner_v2 import _post_local

    provider = get_openai_wrapper_provider()
    original = provider.complete
    recorder = _Recorder()
    provider.complete = recorder.complete  # type: ignore[method-assign]
    try:
        body, _elapsed, status, err, *_ = _post_local(
            "local://app.main:app/api/v1/regenold/eu-ai-act/ask",
            None,
            build_hard_messages(row, _history(depth)),
            180.0,
        )
    finally:
        provider.complete = original  # type: ignore[method-assign]

    graded = [p for p in recorder.payloads if p["stage2"]]
    if not graded:
        notes: list[str] = []
        reasoning = body.get("reasoning") if isinstance(body, dict) else None
        if isinstance(reasoning, dict):
            notes = [str(n) for n in (reasoning.get("notes") or [])]
        return {
            "vacuous": True,
            "status": status,
            "err": err,
            "skip_note": next((n for n in notes if n.startswith("stage2_skipped")), None),
        }

    payload = graded[-1]
    user = payload["user"]
    system = payload["system"]
    sections = _sections(user)
    e_start = user.find("EU AI ACT REFERENCES:")
    e_end = user.find("ANSWER CONTRACT")
    if e_start >= 0 and e_end > e_start:
        evidence_text = user[e_start:e_end]
    else:
        evidence_text = ""
    return {
        "vacuous": False,
        "system_chars": len(system),
        "user_chars": len(user),
        "total_chars": len(system) + len(user),
        "user_sections": sections,
        "evidence": _evidence_breakdown(evidence_text),
        "evidence_share": round(len(evidence_text) / max(len(user), 1), 4),
    }


def _median(values: list[int]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from evals.regenold.official_batch import load_official_batch

    os.environ.update(PROBE_BASELINE)
    n_rows = int(os.environ.get("R460_ROWS", "12"))
    stride = int(os.environ.get("R460_STRIDE", "5"))
    depth = int(os.environ.get("R460_DEPTH", "0"))
    difficulty = os.environ.get("R460_DIFFICULTY", "HARD").strip().upper()
    forced = [x.strip() for x in (os.environ.get("R460_IDS") or "").split(",") if x.strip()]

    rows = list(load_official_batch())
    if forced:
        wanted = set(forced)
        rows = [r for r in rows if r.id in wanted]
        missing = wanted - {r.id for r in rows}
        if missing:
            raise SystemExit(f"R460_IDS not in the official batch: {sorted(missing)}")
    else:
        if difficulty in ("HARD", "EASY"):
            rows = [r for r in rows if (r.difficulty or "").upper() == difficulty]
        rows = rows[::stride][:n_rows]

    per_row: list[dict[str, Any]] = []
    for row in rows:
        result = _route(row, depth)
        result["id"] = row.id
        result["difficulty"] = row.difficulty
        per_row.append(result)

    graded = [r for r in per_row if not r.get("vacuous")]
    systems = [int(r["system_chars"]) for r in graded]
    users = [int(r["user_chars"]) for r in graded]
    totals = [int(r["total_chars"]) for r in graded]

    section_totals: dict[str, list[int]] = {}
    for r in graded:
        for label, chars in (r["user_sections"] or {}).items():
            section_totals.setdefault(label, []).append(int(chars))
    evidence_totals: dict[str, list[int]] = {}
    for r in graded:
        for label, chars in ((r["evidence"] or {}).get("sections") or {}).items():
            evidence_totals.setdefault(label, []).append(int(chars))

    report: dict[str, Any] = {
        "config": {
            "rows": len(per_row),
            "stride": stride,
            "depth": depth,
            "difficulty": difficulty,
            "baseline": PROBE_BASELINE,
        },
        "graded_rows": len(graded),
        "vacuous_rows": [r["id"] for r in per_row if r.get("vacuous")],
        "system_chars": {
            "median": _median(systems),
            "min": min(systems) if systems else None,
            "max": max(systems) if systems else None,
        },
        "user_chars": {
            "median": _median(users),
            "min": min(users) if users else None,
            "max": max(users) if users else None,
        },
        "total_chars": {
            "median": _median(totals),
            "min": min(totals) if totals else None,
            "max": max(totals) if totals else None,
        },
        "user_section_median_chars": {
            k: _median(v) for k, v in sorted(section_totals.items(), key=lambda kv: -statistics.median(kv[1]))
        },
        "evidence_section_median_chars": {
            k: _median(v) for k, v in sorted(evidence_totals.items(), key=lambda kv: -statistics.median(kv[1]))
        },
        "evidence_redundancy": {
            "median_duplicate_bullet_chars": _median([int((r["evidence"] or {}).get("duplicate_bullet_chars", 0)) for r in graded]),
            "median_duplicate_bullet_lines": _median([int((r["evidence"] or {}).get("duplicate_bullet_lines", 0)) for r in graded]),
            "median_not_engaged_headings": _median([int((r["evidence"] or {}).get("not_engaged_headings", 0)) for r in graded]),
            "median_not_engaged_coord_chars": _median([int((r["evidence"] or {}).get("not_engaged_coord_chars", 0)) for r in graded]),
        },
        "per_row": per_row,
    }
    (OUT / "stage2-payload-census.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(
        f"rows={report['config']['rows']} graded={report['graded_rows']} "
        f"vacuous={len(report['vacuous_rows'])} depth={depth} difficulty={difficulty}"
    )
    print(
        f"MEDIAN  system={report['system_chars']['median']}  "
        f"user={report['user_chars']['median']}  total={report['total_chars']['median']}"
    )
    print("user sections (median chars):")
    for k, v in report["user_section_median_chars"].items():
        print(f"   {k:22s} {v}")
    print("evidence sections (median chars):")
    for k, v in report["evidence_section_median_chars"].items():
        print(f"   {k:42s} {v}")
    print("evidence redundancy (median):")
    for k, v in report["evidence_redundancy"].items():
        print(f"   {k:32s} {v}")
    if report["vacuous_rows"]:
        print(f"vacuous ids: {report['vacuous_rows']}")
    print(f"wrote {OUT / 'stage2-payload-census.json'}")


if __name__ == "__main__":
    main()
