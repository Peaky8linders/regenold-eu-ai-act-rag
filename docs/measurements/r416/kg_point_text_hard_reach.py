"""R416 — does the KG point-text lever REACH the multi-turn hard split?

The R416 reading that flipped ``REGENOLD_KG_POINT_TEXT`` to default ON was taken
on the reconstructed official gold, which is SINGLE-TURN. The lever is not
modality-restricted (it edits the grounding text, and the full system prompt it
sits beside is the thing that IS restricted), so its hard-split movement is
unknown rather than zero — a residual the flag docstring names explicitly.

Before spending ~74 hard-mode calls (37 rows x 2 arms x ~30 s), establish REACH:
does the block this flag gates actually appear in the graded Stage-2 payload for a
hard row, and does it change between the arms? If the hard path never renders the
sub-point block, a paired run there can only measure sampling noise and would be
misread as a null.

The measurement is taken at the provider seam — ``OpenAIWrapperRequest.user``,
the text the model actually receives — because the block is assembled through
the route and the engine, and measuring the assembly function instead is the
trap ``evals.harness.gate_validity`` documents (it records pre-substitution text
and reports two arms as identical).

No model calls: the provider is patched to return a stage-appropriate canned
response (JSON for the parse, prose for the graded answer), so this is free.

Usage::

    set -a; . ./.env; set +a
    .venv/Scripts/python.exe docs/measurements/r416/kg_point_text_hard_reach.py
    .venv/Scripts/python.exe docs/measurements/r416/kg_point_text_hard_reach.py --limit 12
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "docs" / "measurements" / "r416"
FLAG = "REGENOLD_KG_POINT_TEXT"

#: The header ``render_kg_context`` writes around the point/subpoint block.
KG_MARKER = "KNOWLEDGE-GRAPH SUB-POINT DETAIL"

#: Stage-2 answer markers — the same filter ``gate_validity`` uses.
_STAGE2_MARKERS = ("EU AI ACT REFERENCES:", "ANSWER CONTRACT")

_PARSED = json.dumps(
    {
        "intent": "general_compliance",
        "entities": ["provider", "high-risk AI system"],
        "risk_context": "high_risk",
        "dimension_hint": "obligations",
        "keywords": ["emotion recognition", "workplace"],
        "reasoning": "stub parse for the hard reach probe",
    }
)

_ANSWER = (
    "Under Article 5(1)(f), AI systems inferring emotions of natural persons in "
    "the workplace are prohibited, subject to the narrow medical/safety carve-out. "
    "Article 6 and Annex III classify the residual case as high-risk, which brings "
    "Articles 9 to 15 into play. References: Article 5, Article 5.1.f, Article 6, "
    "Annex III."
)


class ProviderRecorder:
    """Records the payload actually dispatched, per call."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def complete(self, request, *args: Any, **kwargs: Any):  # noqa: ANN002, ANN003
        user = str(getattr(request, "user", "") or "")
        system = str(getattr(request, "system", "") or "")
        stage2 = any(m in user for m in _STAGE2_MARKERS)
        kg_len = 0
        kg_offset = user.find(KG_MARKER)
        if kg_offset >= 0:
            # The block runs to the next blank-line-delimited section header or the
            # end of the payload; length is what matters for a reach read.
            tail = user[kg_offset:]
            nxt = tail.find("\n\n", 120)
            kg_len = len(tail) if nxt < 0 else nxt
        self.payloads.append(
            {
                "graded_answer_call": stage2,
                "system_len": len(system),
                "user_len": len(user),
                "user_sha": hashlib.sha256(user.encode("utf-8")).hexdigest()[:16],
                "kg_block_len": kg_len,
            }
        )
        return SimpleNamespace(
            error=None,
            text=_ANSWER if stage2 else _PARSED,
            thinking="",
            finish_reason="stop",
            model="probe-stub",
            usage=None,
            latency_ms=1,
            headers=None,
        )


def _run_row(client, messages: list[dict]) -> None:
    body = [{"role": str(m.get("role")), "content": str(m.get("content") or "")} for m in messages]
    client.post("/api/v1/regenold/eu-ai-act/ask", json=body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="first N hard rows (default: all)")
    ap.add_argument("--offset", type=int, default=0, help="skip the first N rows")
    ap.add_argument("--out", default="kg-point-text-hard-reach.json")
    a = ap.parse_args()

    # Live provider config must come from .env (Neo4j creds are needed: the block
    # is read from Aura), but the model itself is stubbed below.
    os.environ.pop("REGENOLD_SKIP_DOTENV", None)

    from fastapi.testclient import TestClient

    from app.engines import _graph_rag_impl as impl  # noqa: F401 — engine import first
    from app.llm.openai_wrapper_provider import get_openai_wrapper_provider
    from app.main import app
    from app.rate_limit import limiter
    from evals.harness.probe_set import load_probe_set

    rows = load_probe_set(multiturn=True)
    if a.offset:
        rows = rows[a.offset :]
    if a.limit:
        rows = rows[: a.limit]

    limiter.enabled = False
    provider = get_openai_wrapper_provider()
    real_complete = provider.complete

    client = TestClient(app)
    results: list[dict] = []
    try:
        for i, pr in enumerate(rows, 1):
            per_arm: dict[str, dict] = {}
            for value in ("0", "1"):
                os.environ[FLAG] = value
                rec = ProviderRecorder()
                provider.complete = rec.complete  # type: ignore[method-assign]
                try:
                    _run_row(client, [dict(m) for m in pr.messages])
                except Exception as exc:  # noqa: BLE001 — a probe records, never dies
                    per_arm[value] = {"error": f"{type(exc).__name__}: {exc}"}
                    continue
                graded = [p for p in rec.payloads if p["graded_answer_call"]]
                best = max(graded, key=lambda p: p["kg_block_len"]) if graded else None
                per_arm[value] = best or {"graded": False}
            provider.complete = real_complete  # type: ignore[method-assign]

            off, on = per_arm.get("0", {}), per_arm.get("1", {})
            changed = bool(
                off.get("user_sha") and on.get("user_sha") and off["user_sha"] != on["user_sha"]
            )
            row = {
                "id": pr.id,
                "source": pr.source,
                "msgs": len(pr.messages),
                "gold_refs": len(pr.expected_refs or []),
                "graded_off": bool(off.get("graded_answer_call")),
                "graded_on": bool(on.get("graded_answer_call")),
                "kg_len_off": int(off.get("kg_block_len") or 0),
                "kg_len_on": int(on.get("kg_block_len") or 0),
                "user_len_off": int(off.get("user_len") or 0),
                "user_len_on": int(on.get("user_len") or 0),
                "payload_changed": changed,
            }
            results.append(row)
            print(
                f"  [{i:3d}/{len(rows)}] {pr.id:<26} graded="
                f"{'y' if row['graded_off'] and row['graded_on'] else 'n'} "
                f"kg {row['kg_len_off']:6d} -> {row['kg_len_on']:6d} "
                f"user {row['user_len_off']:6d} -> {row['user_len_on']:6d} "
                f"{'CHANGED' if changed else 'same'}",
                flush=True,
            )
    finally:
        provider.complete = real_complete  # type: ignore[method-assign]

    graded_rows = [r for r in results if r["graded_off"] and r["graded_on"]]
    changed_rows = [r for r in graded_rows if r["payload_changed"]]
    moved_kg = [r for r in graded_rows if r["kg_len_on"] != r["kg_len_off"]]
    summary = {
        "flag": FLAG,
        "split": "hard",
        "rows": len(results),
        "graded_rows": len(graded_rows),
        "payload_changed_rows": len(changed_rows),
        "kg_block_changed_rows": len(moved_kg),
        "kg_len_off_total": sum(r["kg_len_off"] for r in graded_rows),
        "kg_len_on_total": sum(r["kg_len_on"] for r in graded_rows),
        "payload_changed_ids": [r["id"] for r in changed_rows],
        "detail": results,
    }
    (OUT / a.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "-" * 78)
    print(f"ROWS {len(results)}   graded {len(graded_rows)}   "
          f"payload changed {len(changed_rows)}   kg block changed {len(moved_kg)}")
    print(f"kg block total chars  OFF {summary['kg_len_off_total']:,} -> "
          f"ON {summary['kg_len_on_total']:,}")
    print(f"wrote {(OUT / a.out).relative_to(REPO)}")
    if not graded_rows:
        print("\nNO GRADED CALL WAS RECORDED — the seam never fired; the probe is inert.")
        return 2
    if not changed_rows:
        print("\nLEVER INERT ON THE HARD SPLIT — a paired hard gate would measure noise.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
