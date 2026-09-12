"""R411 — precision audit of the curated-authoritative Stage-2 intercepts.

Why this exists
---------------
The recurring engine-failure class in this repo is an *over-matching detector*:
a curated intercept that latches onto words anywhere in the question, fires on
a question it was never written for, and then SHORT-CIRCUITS Stage-2 — shipping
a narrow curated verdict in place of a synthesised answer. The medtech-triage
regex, the Art. 5(1)(g) gatekeeper and the verdict-lead detector have each been
fixed for exactly this shape.

This instrument measures the class rather than one instance of it: it runs every
detector wired into ``_is_curated_authoritative_intercept`` over the OFFICIAL
110-question corpus and prints, per detector, the questions it fires on. A
detector whose fires are off-topic for the question is a false positive that
costs an entire Stage-2 answer.

Deterministic: no LLM, no network. Safe to run in CI.

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe \
        docs/measurements/r411/intercept_precision_audit.py [--verbose]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

# Every detector OR-ed together inside _is_curated_authoritative_intercept.
DETECTORS = (
    "_detect_guiding_principles_inquiry",
    "_detect_minimal_risk_inquiry",
    "_detect_article_6_3_inquiry",
    "_detect_research_scope_inquiry",
    "_detect_high_risk_penalty_inquiry",
    "_detect_emotion_classification_inquiry",
    "_detect_systems_or_models_inquiry",
    "_detect_annex_iii_8_admin_justice_inquiry",
    "_detect_annex_iii_8_election_inquiry",
    "_detect_explainability_inquiry",
    "_detect_reclassification_inquiry",
    "_detect_ai_board_governance_inquiry",
    "_detect_sme_simplified_doc_inquiry",
    "_detect_workplace_worker_notification_inquiry",
    "_detect_art50_text_public_interest_inquiry",
    "_detect_risk_framework_inquiry",
    "_detect_prohibited_practices_inquiry",
    "_detect_deepfake_criminal_exception_inquiry",
    "_detect_testing_data_definition_inquiry",
    "_detect_retention_docs_inquiry",
    "_detect_special_data_bias_inquiry",
    "_detect_tech_doc_certificate_inquiry",
    "_detect_hardware_techdoc_inquiry",
    "_detect_deviation_detection_inquiry",
    "_detect_role_difference_inquiry",
    "_detect_user_information_inquiry",
    "_detect_gpai_transparency_exception_inquiry",
    "_detect_systemic_risk_scope_inquiry",
    "_detect_emergency_triage_inquiry",
    "_detect_health_insurance_inquiry",
    "_detect_hospital_deployer_inquiry",
    "_detect_provider_pre_market_inquiry",
    "_detect_robotic_surgery_inquiry",
)


def load_questions() -> list[dict]:
    rows = []
    with GOLD.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.path.insert(0, str(ROOT))

    from app.engines import _graph_rag_impl as G  # noqa: PLC0415

    verbose = "--verbose" in sys.argv
    rows = load_questions()
    questions = []
    for r in rows:
        q = r.get("question") or r.get("q") or ""
        if q:
            questions.append((str(r.get("id") or r.get("row_id") or "?"), q))

    print(f"corpus: {len(questions)} official questions from {GOLD.name}\n")

    total_fires = 0
    for name in DETECTORS:
        fn = getattr(G, name, None)
        if fn is None:
            print(f"  !! {name} is NOT importable — wiring drift")
            continue
        fired = []
        for rid, q in questions:
            try:
                if fn(q):
                    fired.append((rid, q))
            except Exception as exc:  # noqa: BLE001
                fired.append((rid, f"<raised {type(exc).__name__}: {exc}>"))
        total_fires += len(fired)
        if not fired:
            continue
        print(f"### {name}: {len(fired)}/{len(questions)} fires")
        for rid, q in fired:
            print(f"    [{rid}] {q[:160]}")
        print()

    # Whole-gate view: rows where the OR fires (Stage-2 is skipped).
    gate = getattr(G, "_is_curated_authoritative_intercept")
    hits = [(rid, q) for rid, q in questions if gate(q)]
    print("=" * 90)
    print(f"_is_curated_authoritative_intercept fired on {len(hits)}/{len(questions)} rows")
    for rid, q in hits:
        print(f"    [{rid}] {q[:170]}")
    print(f"\nsum of per-detector fires (overlaps counted twice): {total_fires}")
    if not verbose:
        print("\n(--verbose accepted; default output is already per-fire)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
