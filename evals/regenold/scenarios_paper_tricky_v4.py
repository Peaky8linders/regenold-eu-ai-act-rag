"""Paper-grounded tricky / nuanced eval set (V4) — fresh R99 generation.

Source: Davvetas et al. arXiv:2603.09435 "AI Act Evaluation Benchmark".

These probe the paper's §4.2 decision-boundary ambiguities (prohibited vs
high-risk, limited vs minimal) plus the obligation-generation and
article-retrieval tasks for roles the V3 tricky set did not exercise
(importer, distributor, authorised representative, GPAI systemic-risk).

All questions are fresh — no text is reused from the V3 tricky set.

Categories:
* borderline_prohibition (5) — Art. 5 boundary cases (§4.2 "subliminal"/
  "manipulation" ambiguity, private-vs-public actors, carve-outs)
* limited_vs_minimal      (4) — §5 confusion class (over/under-prediction)
* high_risk_vs_limited    (3) — Annex III gateway vs mere transparency
* obligation_generation   (4) — value-chain roles + GPAI
* article_retrieval       (4) — incident reporting, sandboxes, penalties, CE

Schema matches runner_v2 tricky schema (see scenarios_paper_singleturn_v4.py).
"""
from __future__ import annotations

SCENARIOS: list[dict] = [
    # ── borderline_prohibition (5) ────────────────────────────────────────
    {
        "id": "tp_v4_001",
        "question": (
            "A retail app fires brief haptic buzzes on the phone, timed by AI to "
            "moments of hesitation, to nudge users into completing in-app "
            "purchases they were about to abandon. Is this a prohibited "
            "subliminal technique or merely aggressive marketing?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["subliminal", "prohibited", "manipulat"],
        "category": "borderline_prohibition",
        "notes": (
            "Paper §4.2 'subliminal' decision-boundary edge case in a new "
            "modality (haptic). Art. 5(1)(a) subliminal/manipulative techniques."
        ),
    },
    {
        "id": "tp_v4_002",
        "question": (
            "A private insurance company runs an AI that aggregates customers' "
            "social-media activity into a general 'trustworthiness' score that "
            "limits their access to products. Does Article 5's social-scoring ban "
            "apply to a private actor like this?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["social scoring", "prohibited", "detrimental"],
        "category": "borderline_prohibition",
        "notes": (
            "Art. 5(1)(c) social scoring applies to public AND private actors — "
            "tests whether the engine confines the ban to governments."
        ),
    },
    {
        "id": "tp_v4_003",
        "question": (
            "An AI predicts the likelihood that an individual will commit a crime "
            "based solely on profiling their personality traits and background, "
            "with no objective facts tied to a specific offence. Prohibited or "
            "high-risk law-enforcement use?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["predict", "profiling", "prohibited"],
        "category": "borderline_prohibition",
        "notes": (
            "Art. 5(1)(d) — predictive policing based solely on profiling is "
            "prohibited; the engine must not down-grade it to Annex III(6) "
            "high-risk law enforcement."
        ),
    },
    {
        "id": "tp_v4_004",
        "question": (
            "Police want to use real-time facial recognition in a public square, "
            "but only to search for a suspect in an imminent terrorist threat. "
            "Is this allowed under the EU AI Act?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["real-time", "law enforcement", "exception"],
        "category": "borderline_prohibition",
        "notes": (
            "Art. 5(1)(h) carve-out — real-time RBI is prohibited save narrow "
            "law-enforcement exceptions (imminent terrorist threat). Tests the "
            "exception, not a flat ban."
        ),
    },
    {
        "id": "tp_v4_005",
        "question": (
            "An online-learning platform uses an AI webcam tool to detect when "
            "students look confused so teachers can intervene. The vendor says "
            "it is 'just adaptive learning'. How does the EU AI Act treat it?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["emotion recognition", "education", "prohibited"],
        "category": "borderline_prohibition",
        "notes": (
            "Art. 5(1)(f) — emotion recognition in education is prohibited; tests "
            "the 'adaptive learning' euphemism against the ban."
        ),
    },
    # ── limited_vs_minimal (4) ─────────────────────────────────────────────
    {
        "id": "tp_v4_006",
        "question": (
            "A photo-gallery app uses AI to automatically tag and group your own "
            "private photos by content. No output is shared. Limited-risk "
            "(transparency) or minimal-risk under the EU AI Act?"
        ),
        "expected_refs": ["Article 5", "Article 6"],
        "expected_keywords": ["minimal", "risk", "transparency"],
        "category": "limited_vs_minimal",
        "notes": (
            "Paper §5 limited-vs-minimal confusion. Private on-device tagging "
            "with no interaction/disclosure trigger → minimal residual."
        ),
    },
    {
        "id": "tp_v4_007",
        "question": (
            "An email client embeds an AI that translates incoming messages into "
            "the user's language. Does the EU AI Act impose any transparency or "
            "other obligations?"
        ),
        "expected_refs": ["Article 5", "Article 6"],
        "expected_keywords": ["minimal", "risk", "obligations"],
        "category": "limited_vs_minimal",
        "notes": (
            "Machine translation as a feature — minimal-risk residual; tests "
            "over-prediction of limited-risk on any 'AI feature'."
        ),
    },
    {
        "id": "tp_v4_008",
        "question": (
            "A marketing team uses generative AI to draft promotional copy that "
            "is then published. The drafts are AI-generated text shown to the "
            "public. Is a transparency obligation triggered, and which one?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": ["artificially generated", "marked", "text"],
        "category": "limited_vs_minimal",
        "notes": (
            "Art. 50(2) — published AI-generated text must be marked; tests "
            "under-prediction (treating it as minimal)."
        ),
    },
    {
        "id": "tp_v4_009",
        "question": (
            "A voice assistant on a smart speaker always announces 'I am a virtual "
            "assistant' before responding. Has it already satisfied its EU AI Act "
            "transparency duty, and under which article?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": ["inform", "interacting", "AI system"],
        "category": "limited_vs_minimal",
        "notes": (
            "Art. 50(1) — interaction-disclosure already met; tests that the "
            "engine identifies the right limited-risk article rather than minimal."
        ),
    },
    # ── high_risk_vs_limited (3) ───────────────────────────────────────────
    {
        "id": "tp_v4_010",
        "question": (
            "A university uses an AI to score and rank applicants for admission. "
            "The vendor markets it as 'just a recommendation tool'. Is it "
            "high-risk under the EU AI Act, and on what basis?"
        ),
        "expected_refs": ["Annex III", "Article 6"],
        "expected_keywords": ["high-risk", "education", "Annex III"],
        "category": "high_risk_vs_limited",
        "notes": (
            "Annex III(3) — education/admissions scoring is high-risk; tests the "
            "'recommendation tool' down-grade."
        ),
    },
    {
        "id": "tp_v4_011",
        "question": (
            "A bank uses an AI to pre-screen which loan applicants its staff "
            "should contact, calling it a 'marketing prioritisation' tool. Does "
            "the creditworthiness use make it high-risk?"
        ),
        "expected_refs": ["Annex III", "Article 6"],
        "expected_keywords": ["high-risk", "creditworthiness", "Annex III"],
        "category": "high_risk_vs_limited",
        "notes": (
            "Annex III(5)(b) — creditworthiness/credit-scoring is high-risk; "
            "tests the 'marketing' euphemism."
        ),
    },
    {
        "id": "tp_v4_012",
        "question": (
            "A hospital chatbot both answers patients' general questions AND "
            "triages the urgency of their symptoms to route care. Is the EU AI "
            "Act obligation a mere chatbot disclosure, or full high-risk "
            "treatment?"
        ),
        "expected_refs": ["Annex III", "Article 6"],
        "expected_keywords": ["high-risk", "Annex III", "health"],
        "category": "high_risk_vs_limited",
        "notes": (
            "Dual nature: Art. 50(1) chatbot disclosure AND Annex III/Art. 6 "
            "high-risk for the medical-triage function. Tests that the engine "
            "does not stop at limited-risk."
        ),
    },
    # ── obligation_generation (4) — value-chain roles + GPAI ───────────────
    {
        "id": "tp_v4_013",
        "question": (
            "We import a high-risk AI system made by a US company and place it on "
            "the EU market under our own brand. What are our obligations as the "
            "importer under the EU AI Act?"
        ),
        "expected_refs": ["Article 23"],
        "expected_keywords": ["importer", "conformity", "obligations"],
        "category": "obligation_generation",
        "notes": (
            "Art. 23 — importer obligations. Value-chain role the V3 tricky set "
            "did not cover."
        ),
    },
    {
        "id": "tp_v4_014",
        "question": (
            "We are a distributor that makes a high-risk AI system available on "
            "the EU market without modifying it. What does the EU AI Act require "
            "of us?"
        ),
        "expected_refs": ["Article 24"],
        "expected_keywords": ["distributor", "verify", "obligations"],
        "category": "obligation_generation",
        "notes": (
            "Art. 24 — distributor obligations. Value-chain role new to V4."
        ),
    },
    {
        "id": "tp_v4_015",
        "question": (
            "We provide a general-purpose AI model trained with more than 10^25 "
            "FLOPs of compute. What additional obligations does the EU AI Act "
            "impose because of systemic risk?"
        ),
        "expected_refs": ["Article 55", "Article 51"],
        "expected_keywords": ["systemic risk", "general-purpose", "model"],
        "category": "obligation_generation",
        "notes": (
            "Art. 51 systemic-risk classification (10^25 FLOPs) + Art. 55 "
            "systemic-risk GPAI obligations. GPAI path."
        ),
    },
    {
        "id": "tp_v4_016",
        "question": (
            "A provider established outside the EU offers a high-risk AI system "
            "to EU users. What must it appoint inside the Union, and under which "
            "article?"
        ),
        "expected_refs": ["Article 22"],
        "expected_keywords": ["authorised representative", "established", "Union"],
        "category": "obligation_generation",
        "notes": (
            "Art. 22 — authorised representative for non-EU providers of "
            "high-risk AI."
        ),
    },
    # ── article_retrieval (4) ──────────────────────────────────────────────
    {
        "id": "tp_v4_017",
        "question": (
            "Which EU AI Act article governs the reporting of serious incidents "
            "involving a high-risk AI system?"
        ),
        "expected_refs": ["Article 73"],
        "expected_keywords": ["serious incident", "report", "authorities"],
        "category": "article_retrieval",
        "notes": "Art. 73 — reporting of serious incidents.",
    },
    {
        "id": "tp_v4_018",
        "question": (
            "Which articles of the EU AI Act establish AI regulatory sandboxes to "
            "support innovation and SMEs?"
        ),
        "expected_refs": ["Article 57"],
        "expected_keywords": ["sandbox", "innovation", "competent"],
        "category": "article_retrieval",
        "notes": "Art. 57 — establishment of AI regulatory sandboxes.",
    },
    {
        "id": "tp_v4_019",
        "question": (
            "Which EU AI Act article sets out the administrative fines and "
            "penalties for non-compliance?"
        ),
        "expected_refs": ["Article 99"],
        "expected_keywords": ["penalties", "fines", "infringement"],
        "category": "article_retrieval",
        "notes": "Art. 99 — penalties.",
    },
    {
        "id": "tp_v4_020",
        "question": (
            "Which EU AI Act articles cover the conformity-assessment procedure, "
            "the EU declaration of conformity, and the CE marking for a high-risk "
            "AI system?"
        ),
        "expected_refs": ["Article 43", "Article 47", "Article 48"],
        "expected_keywords": ["conformity", "CE marking", "declaration"],
        "category": "article_retrieval",
        "notes": (
            "Art. 43 conformity assessment + Art. 47 EU declaration of conformity "
            "+ Art. 48 CE marking. Multi-article retrieval."
        ),
    },
]
