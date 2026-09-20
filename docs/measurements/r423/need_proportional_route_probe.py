"""R423 — does the need-proportional contract actually reach the wire? (no live LLM)

The cheap proof that must precede the expensive one. ``REGENOLD_NEED_PROPORTIONAL_CONTRACT``
is a PROMPT-side lever, and this repo has paid five times for levers that "read
correctly in the diff and make zero calls" (R329 rerank, R330 semantic layer, R366
parent collapse, R393 skeleton, R397 coordinate guard). Grepping the call site is
not evidence — the DATA SHAPE the call site really produces is, which is why the
R393 lesson is written into ``provision_hierarchy._parent_id``.

So: run the REAL route on the REAL hard-mode messages with the Stage-2 provider
stubbed at the provider seam (``_installed``/``_restore``), for one row and both
arms, and read the payload the model would have received.

Reports per row:

* whether the ON arm's dispatched user payload carries the answer-shape clause
  (``ANSWER SHAPE``) and the scoped completeness header, and that the OFF arm
  carries neither;
* the user-payload length delta ON - OFF, and the skeleton heading present in
  each arm, so the "scoped, not pruned" claim is measured;
* NON-VACUITY: a row where neither arm fired a graded Stage-2 call is reported
  ``vacuous`` and excluded, never read as "no change".

⚠ WHAT THIS PROBE CAN AND CANNOT ISOLATE. Each arm is a separate route
invocation, and this repo's retrieval is not byte-stable across invocations
(MEASURED in the first run of this probe: the same OFF arm dispatched 19,206
chars for ``rg_064``, then 42,782 on the next run). So the per-row TOTAL delta is
contaminated by retrieval variance and must not be quoted as the lever's effect.
The ``sections`` breakdown IS isolated: the closed-set headings and the indented
skeleton chars are produced by exactly one function, and that function is the one
under test. ``REGENOLD_QUERY_DENOISER=0`` / ``REGENOLD_EXTERNAL_EMBEDDINGS=0``
remove the two network-dependent legs so both arms at least share a retrieval
PATH.

Usage::

    R423_ROWS=5 R423_STRIDE=21 .venv\\\\Scripts\\\\python.exe docs/measurements/r423/need_proportional_route_probe.py
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
_STAGE2_MARKERS = ("EU AI ACT REFERENCES:", "ANSWER CONTRACT")
_ANSWER = (
    "Under Article 13(1) the provider must ensure the system is designed so that "
    "its operation is sufficiently transparent. References: Article 13, Article 13.1."
)
_PARSED = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["transparency", "instructions for use"],
        "reasoning": "stub parse for the need-proportional route probe",
    }
)
#: Held identical across arms so the ONLY thing that can move the payload is the
#: lever: Stage-0 makes its own live calls and the external embedding path is a
#: network dependency. Same invariants R422 established.
PROBE_BASELINE = {
    "REGENOLD_QUERY_DENOISER": "0",
    "REGENOLD_EXTERNAL_EMBEDDINGS": "0",
}


class _Recorder:
    """Records the TEXT of every payload the engine would dispatch."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def complete(self, request: Any, *_a: Any, **_k: Any) -> SimpleNamespace:
        user = str(getattr(request, "user", "") or "")
        system = str(getattr(request, "system", "") or "")
        self.payloads.append(
            {
                "stage2": any(m in user for m in _STAGE2_MARKERS),
                "system_len": len(system),
                "user_len": len(user),
                "user_sha": hashlib.sha256(user.encode("utf-8")).hexdigest()[:16],
                # R423.1 — the clause has TWO shapes now (anchored / unanchored),
                # so detection keys on the invariant marker, not on one branch's
                # heading. Matching the proportional heading alone reported the
                # unanchored clause as "no clause" and read as a VACUOUS probe.
                "has_clause": "ANSWER SHAPE (" in user,
                "has_engaged_completeness": "COMPLETENESS DIRECTIVE (scoped to the" in user,
                "has_generic_completeness": "COMPLETENESS DIRECTIVE: an obligation and its" in user,
                "scoped_heading": "NOT ENGAGED by this question" in user,
                "unanchored_heading": "names no provision" in user,
                "engaged_heading": "ENGAGED members of" in user,
                "exhaustive_heading": "this list is EXHAUSTIVE" in user,
                "text": user,
            }
        )
        stage2 = any(m in user for m in _STAGE2_MARKERS)
        return SimpleNamespace(
            error=None, text=_ANSWER if stage2 else _PARSED, thinking="",
            finish_reason="stop", model="probe-stub", usage=None,
            latency_ms=1, headers=None,
        )


def _sections(text: str) -> dict[str, int]:
    """Where the dispatched user payload's chars actually sit.

    A payload delta that does not come from the skeleton or the clause is not
    this lever, so the breakdown is reported per row rather than inferred from a
    total: skeleton blocks are the indented lines under a heading, and the clause
    is its own block.
    """
    skeleton_chars = 0
    in_skeleton = False
    headings = {"exhaustive": 0, "engaged": 0, "not_engaged": 0, "unanchored": 0}
    for line in text.splitlines():
        if line.startswith("  ") and "members" in line and line.rstrip().endswith(":"):
            in_skeleton = True
            if "EXHAUSTIVE" in line:
                headings["exhaustive"] += 1
            elif "ENGAGED members of" in line:
                headings["engaged"] += 1
            elif "NOT ENGAGED by" in line:
                headings["not_engaged"] += 1
            elif "names no provision" in line:
                headings["unanchored"] += 1
            continue
        if in_skeleton and line.startswith("    "):
            skeleton_chars += len(line)
            continue
        in_skeleton = False
    clause_chars = 0
    clause = text.split("ANSWER SHAPE (", 1)
    if len(clause) > 1:
        # The clause is its own bullet block; stop at the first line that is not
        # one of its bullets, otherwise this counts the whole tail as "the clause".
        # The heading line's remainder is dropped first: detection now splits on
        # the invariant prefix, not on a whole heading.
        tail = clause[1].split("\n", 1)
        block: list[str] = []
        for line in (tail[1] if len(tail) > 1 else "").splitlines():
            if line.startswith("*") or not line.strip():
                block.append(line)
                continue
            break
        clause_chars = len("\n".join(block).strip())
    return {
        **headings,
        "skeleton_chars": skeleton_chars,
        "clause_chars": clause_chars,
        "total_chars": len(text),
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


def _route(row: Any, env: dict[str, str], depth: int) -> dict[str, Any] | None:
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider
    from evals.regenold.official_batch import build_hard_messages
    from evals.regenold.runner_v2 import _post_local

    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    provider = get_openai_wrapper_provider()
    original = provider.complete
    recorder = _Recorder()
    provider.complete = recorder.complete  # type: ignore[method-assign]
    try:
        _post_local(
            "local://app.main:app/api/v1/regenold/eu-ai-act/ask",
            None,
            build_hard_messages(row, _history(depth)),
            180.0,
        )
    finally:
        provider.complete = original  # type: ignore[method-assign]
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    graded = [p for p in recorder.payloads if p["stage2"]]
    out: dict[str, Any] = {
        "dispatched": len(recorder.payloads),
        "stage2_dispatched": len(graded),
        "sections": _sections(graded[-1]["text"]) if graded else None,
    }
    if not graded:
        return out
    out.update({k: v for k, v in graded[-1].items()})
    return out


def main() -> None:
    from evals.regenold.official_batch import load_official_batch

    n_rows = int(os.environ.get("R423_ROWS", "5"))
    stride = int(os.environ.get("R423_STRIDE", "21"))
    depth = int(os.environ.get("R423_DEPTH", "9"))
    #: R423.1 — the two rows the first gate lost are named explicitly, because a
    #: stride can only reach them by luck and they are the whole reason for the
    #: change under test.
    forced = [x.strip() for x in (os.environ.get("R423_IDS") or "").split(",") if x.strip()]
    if forced:
        wanted = set(forced)
        rows = [r for r in load_official_batch() if r.id in wanted]
        missing = wanted - {r.id for r in rows}
        if missing:
            raise SystemExit(f"R423_IDS not in the official batch: {sorted(missing)}")
    else:
        rows = list(load_official_batch())[::stride][:n_rows]

    per_row: list[dict[str, Any]] = []
    for row in rows:
        off = _route(row, {**PROBE_BASELINE, "REGENOLD_NEED_PROPORTIONAL_CONTRACT": "0"}, depth)
        on = _route(row, {**PROBE_BASELINE, "REGENOLD_NEED_PROPORTIONAL_CONTRACT": "1"}, depth)
        fired = bool(
            on
            and on.get("has_clause")
            and "user_len" in on
            and not (off or {}).get("has_clause")
        )
        per_row.append(
            {
                "id": row.id,
                "off": off,
                "on": on,
                "fires": fired,
                "user_delta": (
                    int(on["user_len"]) - int(off["user_len"])
                    if off and on and "user_len" in off and "user_len" in on
                    else None
                ),
                "controls": bool(
                    off
                    and on
                    and "user_len" in off
                    and not off.get("has_clause")
                    and off.get("has_generic_completeness")
                ),
                #: R423.1 — the instruction that lost rg_010's 14(2)/14(4) and
                #: rg_106's Annex III. Reported per arm so "it stopped forbidding
                #: the provision" is measured, not asserted.
                "off_forbids": "do NOT enumerate" in str((off or {}).get("text") or ""),
                "on_forbids": "do NOT enumerate" in str((on or {}).get("text") or ""),
                "on_unanchored_header": "names no provision" in str((on or {}).get("text") or ""),
            }
        )

    fired = [r for r in per_row if r["fires"]]
    controls = [r for r in per_row if r["controls"]]
    deltas = [r["user_delta"] for r in fired if r["user_delta"] is not None]
    for r in per_row:
        for arm in ("off", "on"):
            payload = r[arm] or {}
            if "text" in payload:
                payload["text"] = payload["text"][:20000]
    report: dict[str, Any] = {
        "rows": len(per_row),
        "depth": depth,
        "arms_fired": len(fired),
        "controls_inert": len(controls),
        "vacuous_rows": [r["id"] for r in per_row if not r["fires"]],
        "mean_user_delta_chars": round(statistics.fmean(deltas), 1) if deltas else None,
        "min_user_delta_chars": min(deltas) if deltas else None,
        "max_user_delta_chars": max(deltas) if deltas else None,
        "on_arm_scoped_skeleton_rows": sum(1 for r in per_row if (r["on"] or {}).get("scoped_heading")),
        "on_arm_engaged_skeleton_rows": sum(1 for r in per_row if (r["on"] or {}).get("engaged_heading")),
        "on_arm_exhaustive_heading_rows": sum(
            1 for r in per_row if (r["on"] or {}).get("exhaustive_heading")
        ),
        "off_arm_exhaustive_heading_rows": sum(
            1 for r in per_row if (r["off"] or {}).get("exhaustive_heading")
        ),
        #: R423.1 — the correction under test. The shipped OFF arm never rendered
        #: this string (its skeleton asserts EXHAUSTIVE instead), so ``off_forbids``
        #: is the sanity check that the string is unique to the scoped branch, and
        #: ``on_forbids`` must be FALSE on the unanchored rows or the fix did not
        #: reach the wire.
        "on_arm_forbids_rows": sum(1 for r in per_row if r.get("on_forbids")),
        "off_arm_forbids_rows": sum(1 for r in per_row if r.get("off_forbids")),
        "on_arm_unanchored_header_rows": sum(
            1 for r in per_row if r.get("on_unanchored_header")
        ),
        "per_row": per_row,
    }
    (OUT / "need_proportional_route_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"rows={report['rows']} depth={depth}  arms_fired={report['arms_fired']}")
    print(f"clause fired on {report['arms_fired']}/{report['rows']} rows; "
          f"controls (OFF arm inert) {report['controls_inert']}/{report['rows']}")
    print(f"mean user-payload delta ON-OFF: {report['mean_user_delta_chars']} chars "
          f"(min {report['min_user_delta_chars']}, max {report['max_user_delta_chars']})")
    print(f"ON arm skeleton headings: scoped={report['on_arm_scoped_skeleton_rows']} "
          f"engaged={report['on_arm_engaged_skeleton_rows']} "
          f"exhaustive={report['on_arm_exhaustive_heading_rows']}")
    print(f"OFF arm exhaustive headings: {report['off_arm_exhaustive_heading_rows']}")
    print(f"'do NOT enumerate' present — OFF {report['off_arm_forbids_rows']}/{report['rows']} "
          f"ON {report['on_arm_forbids_rows']}/{report['rows']}")
    print(f"ON unanchored headers ('names no provision'): "
          f"{report['on_arm_unanchored_header_rows']}")
    for r in per_row:
        off, on = r["off"] or {}, r["on"] or {}
        print(f"  {r['id']:<10} fires={r['fires']!s:<5} control={r['controls']!s:<5} "
              f"user {off.get('user_len', '-'):>6} -> {on.get('user_len', '-'):>6} "
              f"(delta {r['user_delta']})  "
              f"dispatched off={off.get('dispatched', 0)} on={on.get('dispatched', 0)}")
        for arm, payload in (("off", off), ("on ", on)):
            sections = payload.get("sections")
            if sections:
                print(f"      {arm} sections {sections}")
    if not fired:
        print("\nVACUOUS — the lever did not reach the wire on any row; do NOT run the gate.")
    print(f"\nwrote {OUT / 'need_proportional_route_probe.json'}")


if __name__ == "__main__":
    # Source ``.env`` first (``set -a; . ./.env; set +a``) so the route sees the
    # same configuration the harness does; ``app.config`` loads it lazily on
    # first import, which is why the run command does it in the shell.
    main()
