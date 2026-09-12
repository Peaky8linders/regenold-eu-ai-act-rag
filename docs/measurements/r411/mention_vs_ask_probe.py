"""R411 — does each curated intercept key on the ASK, or merely on a MENTION?

Why this exists
---------------
Every detector wired into ``_is_curated_authoritative_intercept`` short-circuits
Stage-2 and ships a **stock curated verdict**. That is correct when the question
actually ASKS the intercept's question, and badly wrong when the question merely
MENTIONS the intercept's provision while asking something else: the user gets a
fluent answer to a different question.

Measured instance (2026-09-12, live production): *"If a provider relies on the
Article 6(3) derogation for an Annex III system, what documentation and
registration duties apply?"* was answered with the stock rg_031 classification
verdict ("No. Structuring or deduplicating information is a narrow procedural
task ..."), because ``_detect_article_6_3_inquiry``'s first alternative is the
bare designation ``art(?:icle)?\\s+6\\(3\\)``.

This instrument separates the two hypotheses without hand-authoring 30 cases:

* **MENTION carriers** — a realistic question that names a provision and asks a
  neutral "what does it say / what does it require" question. A detector that
  fires here is keyed on the mention.
* **ASK carriers** — the official corpus question the detector was written for.
  A detector that stops firing here has lost recall and must not be narrowed.

Deterministic: no LLM, no network.

    REGENOLD_SKIP_DOTENV=1 .venv/Scripts/python.exe \
        docs/measurements/r411/mention_vs_ask_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"

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

# Designations the intercepts key on. Keep in sync with the detectors above.
DESIGNATIONS = (
    "Article 6(3)",
    "Article 5",
    "Article 10(5)",
    "Article 11",
    "Article 26",
    "Article 27",
    "Article 49",
    "Article 50",
    "Article 53",
    "Article 60(7)",
    "Article 65",
    "Article 95",
    "Article 99",
    "Annex III",
    "Annex IV",
)

# Neutral carriers: they NAME a provision and ask a general question about it.
# They do not ask any of the intercepts' specific questions.
MENTION_CARRIERS = (
    "Under the EU AI Act, what does {ref} say?",
    "Please summarise {ref} of the EU AI Act.",
    "What documentation does {ref} of the EU AI Act require?",
)


def load_official_rows() -> list[dict]:
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

    questions = [
        (str(r.get("id") or "?"), str(r.get("question") or ""))
        for r in load_official_rows()
        if r.get("question")
    ]

    mention_keyed: list[tuple[str, list[str]]] = []
    for name in DETECTORS:
        fn = getattr(G, name, None)
        if fn is None:
            print(f"  !! {name} NOT importable — wiring drift")
            continue
        fires: list[str] = []
        for carrier in MENTION_CARRIERS:
            for ref in DESIGNATIONS:
                q = carrier.format(ref=ref)
                try:
                    if fn(q):
                        fires.append(q)
                except Exception:  # noqa: BLE001
                    pass
        if fires:
            mention_keyed.append((name, fires))

    print("=" * 92)
    print("MENTION-KEYED detectors (fire on a neutral question that only NAMES a provision)")
    print("=" * 92)
    if not mention_keyed:
        print("  none")
    for name, fires in mention_keyed:
        # Recall check: does it still fire on the official question it owns?
        corpus_fires = [rid for rid, q in questions if _safe(getattr(G, name), q)]
        print(f"\n{name}")
        print(f"  mention-only fires: {len(fires)}   |  official corpus fires: {corpus_fires or 'none'}")
        for q in fires[:4]:
            print(f"    ! {q}")
        if len(fires) > 4:
            print(f"    ... and {len(fires) - 4} more")

    print()
    print("=" * 92)
    print("ASK-keyed detectors (no mention-only fire): "
          f"{len(DETECTORS) - len(mention_keyed)} of {len(DETECTORS)}")
    print("=" * 92)
    return 0


def _safe(fn, q: str) -> bool:
    try:
        return bool(fn(q))
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    raise SystemExit(main())
