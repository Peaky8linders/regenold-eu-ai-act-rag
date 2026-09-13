"""Recount the pasted audit's claims on named frozen inputs; no model calls.

This is a descriptive audit, not a quality gate or a production snapshot.
Run from the repository root with .venv/Scripts/python.exe and this file path.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HARD = ROOT / "evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl"
KEY = ROOT / "docs/measurements/r388/official_refkey_n110.jsonl"
TRIAGE = ROOT / "docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json"


def main() -> int:
    rows = [json.loads(line) for line in HARD.read_text(encoding="utf-8").splitlines() if line.strip()]
    gold = [json.loads(line) for line in KEY.read_text(encoding="utf-8").splitlines() if line.strip()]
    triage = json.loads(TRIAGE.read_text(encoding="utf-8"))
    if len(rows) != 110 or len({r["id"] for r in rows}) != 110:
        raise ValueError("expected 110 unique frozen prediction rows")
    if len(gold) != 110 or {r["id"] for r in rows} != {r["id"] for r in gold}:
        raise ValueError("prediction and reference-key ids do not match")
    if not all(isinstance(r.get("pred_answer"), str) and r["pred_answer"].strip() for r in rows):
        raise ValueError("every frozen prediction needs a non-empty graded answer")

    def grain(refs: list[str]) -> dict:
        # These two sources store canonical Article N / Annex X coordinates.
        # A dot after the head denotes paragraph/point grain; do not use head
        # folding, which erases precisely the property being counted.
        detailed = sum("." in ref for ref in refs)
        return {"total": len(refs), "subpoint": detailed,
                "subpoint_pct": round(100 * detailed / len(refs), 2) if refs else None}

    engine = [r for r in triage if r["cls"] == "ENGINE_GAP"]
    result = {
        "scope": "frozen R407 hard predictions and R388 reference key; not current production",
        "inputs": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (HARD, KEY, TRIAGE)},
        "triage_classes": dict(Counter(r["cls"] for r in triage)),
        "engine_criteria_with_provision_in_emitted_refs": sum(bool(r["inrefs"]) for r in engine),
        "retrieved_context_present": "not measured by inrefs; requires captured Stage-2 context",
        "predicted_grain": grain([ref for r in rows for ref in r["pred_refs"]]),
        "expected_grain": grain([ref for r in gold for ref in r["expected"]]),
        "stored_stage1_drafts": sum(bool(r.get("kg_answer") or r.get("draft")) for r in rows),
        "stage1_preservation_gate": "not evaluable here: turn1_answer is a prior conversational answer, not Stage-1 draft",
    }
    output = Path(__file__).with_name("frozen-summary.json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
