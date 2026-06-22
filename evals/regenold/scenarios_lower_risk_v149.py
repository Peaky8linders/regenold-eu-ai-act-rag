"""R149 — lower-risk-tier classification probe set (ab_judge win-measure).

Targets the deterministic-path weaknesses R149 fixes: "is X regulated / high-
risk?" asks about MINIMAL- and LIMITED-risk systems (which the engine answered
with a high-risk QA-dump instead of the tier verdict), and prohibited-practice
questions phrased with an in-subject disjunction ("are subliminal OR
manipulative techniques prohibited?", which the clause splitter mis-read as a
description and polluted with off-topic obligation prose).

Gold is grounded in the EU AI Act risk pyramid, NOT reverse-engineered from the
R149 branch answer:
  * minimal / limited systems are NOT prohibited (Art 5) and NOT high-risk
    (Art 6 / Annex III), so a correct answer states that, names the high-risk
    TEST (Art 6 + Annex III), and points to the Art 50 transparency duty that
    applies where the system interacts with people;
  * an Article-5 prohibited practice is prohibited under Art 5 regardless of
    how the question disjoins the practice names.

Consumed by ``evals.harness.probe_set`` (source tag ``lower_risk_v149``).
Pure data; no I/O at import.
"""
from __future__ import annotations

SCENARIOS: list[dict] = [
    # ── MINIMAL tier — the engine used to dump the high-risk routes ──────
    {
        "id": "lr_spam_filter",
        "category": "minimal_risk",
        "question": "Is an AI spam filter regulated under the AI Act?",
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": [
            "not", "prohibited", "high-risk", "minimal", "Article 50",
            "transparency",
        ],
    },
    {
        "id": "lr_inventory_tool",
        "category": "minimal_risk",
        "question": "Is an AI inventory-management tool high-risk under the AI Act?",
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": ["not", "high-risk", "minimal", "Annex III"],
    },
    {
        "id": "lr_video_game",
        "category": "minimal_risk",
        "question": "Is an AI opponent in a video game regulated under the AI Act?",
        "expected_refs": ["Article 5", "Article 6", "Article 50"],
        "expected_keywords": ["not", "prohibited", "minimal", "transparency"],
    },
    {
        "id": "lr_music_recommender",
        "category": "minimal_risk",
        "question": "Is a music recommendation AI high-risk under the AI Act?",
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": ["not", "high-risk", "minimal", "limited", "Article 50"],
    },
    # ── LIMITED tier — verdict must reach "limited / Article 50", not just
    #    recite the high-risk routes ──────────────────────────────────────
    {
        "id": "lr_chatbot",
        "category": "limited_risk",
        "question": "Is a customer service chatbot high-risk under the AI Act?",
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": [
            "not", "high-risk", "limited", "Article 50", "transparency",
        ],
    },
    {
        "id": "lr_translation",
        "category": "limited_risk",
        "question": "Is a translation AI high-risk under the AI Act?",
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": ["not", "high-risk", "limited", "minimal"],
    },
    {
        "id": "lr_image_generator",
        "category": "limited_risk",
        "question": "Is an AI image generator high-risk under the AI Act?",
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": ["not", "high-risk", "limited", "Article 50"],
    },
    # ── PROHIBITED with in-subject disjunction — the clause-split bug ─────
    {
        "id": "lr_subliminal_or_manipulative",
        "category": "prohibited_disjunction",
        "question": "Are subliminal or manipulative AI techniques prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": [
            "prohibited", "subliminal", "manipulative", "significant harm",
        ],
    },
    {
        "id": "lr_deceptive_or_manipulative",
        "category": "prohibited_disjunction",
        "question": "Are deceptive or manipulative AI systems prohibited under the AI Act?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["prohibited", "manipulative", "deceptive", "harm"],
    },
    {
        "id": "lr_scraping_or_database",
        "category": "prohibited_disjunction",
        "question": "Is untargeted scraping or harvesting of facial images prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["prohibited", "scraping", "facial", "database"],
    },
    # ── CONTROLS — "X or Y" disjunction that IS high-risk / a real
    #    practice must keep routing correctly (no fix-3 over-reach) ────────
    {
        "id": "lr_ctrl_recruitment_or_hiring",
        "category": "control_high_risk",
        "question": "Is a recruitment or hiring AI high-risk under the AI Act?",
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": ["high-risk", "Annex III", "recruit"],
    },
    {
        "id": "lr_ctrl_social_scoring",
        "category": "control_prohibited",
        "question": "Is social scoring prohibited or high-risk under the AI Act?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["prohibited", "social scoring"],
    },
]
