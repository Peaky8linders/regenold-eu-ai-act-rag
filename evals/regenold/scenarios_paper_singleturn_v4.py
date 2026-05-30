"""Paper-grounded single-turn QA eval set (V4) — fresh R99 generation.

Source: Davvetas et al. arXiv:2603.09435 "AI Act Evaluation Benchmark".
Dataset tasks covered: risk-level classification, relevant-article retrieval,
obligation generation, and question-answering — all four paper tasks.

This is a FRESH, distinct probe set from the R98 V3 sets — no question text is
reused. The risk-tier → article mapping follows the paper's four hypotheses:

* Hypothesis 1 — prohibited  → Article 5 (the eight bans)
* Hypothesis 2 — high-risk   → Article 6 + Annex III + obligation chain
* Hypothesis 3 — limited     → Articles 50 (transparency) & 10 (data governance)
* Hypothesis 4 — minimal     → residual (not prohibited, not high-risk, no
  Art. 50/10 trigger)

Distribution: prohibited (5), high_risk (6), limited (5), minimal (4) = 20.

Schema (matches runner_v2 tricky schema exactly):

    {
        "id": str,
        "question": str,
        "expected_refs": list[str],   # "Article N" / "Annex N" user-facing form
        "expected_keywords": list[str],
        "category": str,              # risk tier or task label
        "notes": str,
    }

Every ref in ``expected_refs`` is validated against
``app.data.article_existence.ARTICLE_EXISTENCE`` by ``validate_paper_v4.py``.
"""
from __future__ import annotations

SCENARIOS: list[dict] = [
    # ─────────────────────────────────────────────────────────────────────
    # prohibited (5) — Article 5 (paper hypothesis 1). Each item targets a
    # distinct one of the eight Art. 5 bans NOT exercised by V3.
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "st_v4_001",
        "question": (
            "A company deploys an AI system that recognises employees' emotions "
            "from webcam feeds during work to flag who seems disengaged. Is this "
            "permitted under the EU AI Act?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["emotion recognition", "workplace", "prohibited"],
        "category": "prohibited",
        "notes": (
            "Art. 5(1)(f) — emotion recognition in the workplace is a prohibited "
            "practice (paper §3.1 ban list). Distinct from V3's online-learning "
            "emotion-recognition tricky row."
        ),
    },
    {
        "id": "st_v4_002",
        "question": (
            "An AI system categorises people by inferring their race, political "
            "opinions and sexual orientation from their facial images. Which EU "
            "AI Act article does this violate?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["biometric categorisation", "prohibited", "political"],
        "category": "prohibited",
        "notes": (
            "Art. 5(1)(g) — biometric categorisation inferring protected "
            "characteristics. Paper §3.1 ban list."
        ),
    },
    {
        "id": "st_v4_003",
        "question": (
            "A vendor builds a facial-recognition database by indiscriminately "
            "scraping images from the internet and CCTV footage. Is this a "
            "prohibited practice under the EU AI Act?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["facial recognition", "scraping", "prohibited"],
        "category": "prohibited",
        "notes": (
            "Art. 5(1)(e) — untargeted scraping of facial images to build "
            "recognition databases. Paper §3.1 ban list."
        ),
    },
    {
        "id": "st_v4_004",
        "question": (
            "An AI app targets elderly users with cognitive decline, exploiting "
            "their condition to push them toward expensive subscriptions. Does "
            "the EU AI Act prohibit this?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["exploit", "vulnerabilities", "prohibited"],
        "category": "prohibited",
        "notes": (
            "Art. 5(1)(b) — exploitation of vulnerabilities due to age or "
            "disability. Paper §3.1 ban list."
        ),
    },
    {
        "id": "st_v4_005",
        "question": (
            "Law enforcement wants to run real-time remote facial identification "
            "across cameras in a city square to scan all passers-by. What does "
            "the EU AI Act say about this?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": ["real-time", "biometric identification", "law enforcement"],
        "category": "prohibited",
        "notes": (
            "Art. 5(1)(h) — real-time remote biometric identification in publicly "
            "accessible spaces by law enforcement (prohibited save narrow "
            "exceptions). Paper §3.1 ban list."
        ),
    },
    # ─────────────────────────────────────────────────────────────────────
    # high_risk (6) — Article 6 + Annex III + obligation chain (hypothesis 2)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "st_v4_006",
        "question": (
            "An AI system is used as a safety component to manage the supply of "
            "electricity on a national grid. How is it classified and under which "
            "article?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": ["high-risk", "critical infrastructure", "Annex III"],
        "category": "high_risk",
        "notes": (
            "Annex III(2) — critical infrastructure (electricity supply). Art. 6 "
            "classification gateway. Risk-classification task."
        ),
    },
    {
        "id": "st_v4_007",
        "question": (
            "Before placing a high-risk AI system on the EU market, what "
            "conformity-assessment obligation must its provider complete under "
            "the EU AI Act?"
        ),
        "expected_refs": ["Article 43"],
        "expected_keywords": ["conformity assessment", "high-risk", "provider"],
        "category": "high_risk",
        "notes": (
            "Art. 43 — conformity assessment procedure for high-risk AI. "
            "Obligation-generation task."
        ),
    },
    {
        "id": "st_v4_008",
        "question": (
            "What accuracy, robustness and cybersecurity requirements does the EU "
            "AI Act impose on a high-risk AI system?"
        ),
        "expected_refs": ["Article 15"],
        "expected_keywords": ["accuracy", "robustness", "cybersecurity"],
        "category": "high_risk",
        "notes": (
            "Art. 15 — accuracy, robustness and cybersecurity for high-risk AI. "
            "Obligation-generation task."
        ),
    },
    {
        "id": "st_v4_009",
        "question": (
            "Does a provider of a stand-alone high-risk AI system have to register "
            "it anywhere before putting it into service in the EU, and under which "
            "article?"
        ),
        "expected_refs": ["Article 49"],
        "expected_keywords": ["registration", "EU database", "high-risk"],
        "category": "high_risk",
        "notes": (
            "Art. 49 — registration of high-risk AI systems in the EU database. "
            "Obligation / article-retrieval task."
        ),
    },
    {
        "id": "st_v4_010",
        "question": (
            "An AI system verifies travellers' identities using biometrics at a "
            "border crossing for migration control. How does the EU AI Act "
            "classify it?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": ["high-risk", "migration", "Annex III"],
        "category": "high_risk",
        "notes": (
            "Annex III(7) — migration, asylum and border-control management. "
            "Art. 6 gateway. Risk-classification task."
        ),
    },
    {
        "id": "st_v4_011",
        "question": (
            "A public authority intends to deploy a high-risk AI system that "
            "affects access to social benefits. What assessment must it carry out "
            "before deployment under the EU AI Act?"
        ),
        "expected_refs": ["Article 27"],
        "expected_keywords": ["fundamental rights", "impact assessment", "deployer"],
        "category": "high_risk",
        "notes": (
            "Art. 27 — fundamental rights impact assessment (FRIA) for deployers "
            "of certain high-risk AI. Obligation-generation task."
        ),
    },
    # ─────────────────────────────────────────────────────────────────────
    # limited (5) — Articles 50 & 10 (hypothesis 3)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "st_v4_012",
        "question": (
            "A media company publishes an AI-generated deepfake video of a public "
            "figure. What transparency obligation does the EU AI Act impose?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": ["deep fake", "disclose", "artificially generated"],
        "category": "limited",
        "notes": (
            "Art. 50(4) — deep-fake disclosure obligation. Limited-risk "
            "transparency. Obligation-generation task."
        ),
    },
    {
        "id": "st_v4_013",
        "question": (
            "An AI system generates synthetic audio and text content that is "
            "published online. How must this output be marked under the EU AI Act?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": ["artificially generated", "machine-readable", "marked"],
        "category": "limited",
        "notes": (
            "Art. 50(2) — providers of generative AI must mark outputs as "
            "artificially generated in a machine-readable format. Limited-risk "
            "transparency."
        ),
    },
    {
        "id": "st_v4_014",
        "question": (
            "What does Article 10 of the EU AI Act require regarding the training, "
            "validation and testing datasets used by a high-risk AI system?"
        ),
        "expected_refs": ["Article 10"],
        "expected_keywords": ["data governance", "training", "bias"],
        "category": "limited",
        "notes": (
            "Art. 10 — data and data governance (the paper grounds limited-risk "
            "data obligations here). Article-retrieval / QA task."
        ),
    },
    {
        "id": "st_v4_015",
        "question": (
            "A retailer's customer-support chatbot answers questions on its "
            "website. What does the EU AI Act require the chatbot to tell users?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": ["inform", "interacting", "AI system"],
        "category": "limited",
        "notes": (
            "Art. 50(1) — natural persons must be informed they are interacting "
            "with an AI system. Limited-risk transparency."
        ),
    },
    {
        "id": "st_v4_016",
        "question": (
            "An emotion-recognition AI is used in a market-research focus group "
            "(not a workplace or school). What obligation does the EU AI Act "
            "impose on its deployer?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": ["emotion recognition", "inform", "exposed"],
        "category": "limited",
        "notes": (
            "Art. 50(3) — outside the Art. 5(1)(f) workplace/education ban, an "
            "emotion-recognition system triggers a transparency duty to inform "
            "exposed persons. Limited-risk."
        ),
    },
    # ─────────────────────────────────────────────────────────────────────
    # minimal (4) — residual bucket (hypothesis 4). Paper §3.1 examples:
    # video games, spam filters. Engine should classify as minimal after
    # checking it is NOT Art. 5 / Art. 6 / Art. 50.
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "st_v4_017",
        "question": (
            "An AI spam filter automatically sorts incoming corporate email into "
            "junk and inbox folders. How does the EU AI Act classify it?"
        ),
        "expected_refs": ["Article 5", "Article 6"],
        "expected_keywords": ["minimal", "spam", "risk"],
        "category": "minimal",
        "notes": (
            "Paper §3.1 explicit minimal-risk example (spam filter). Residual "
            "bucket: not prohibited (Art. 5), not high-risk (Art. 6)."
        ),
    },
    {
        "id": "st_v4_018",
        "question": (
            "A warehouse uses an AI tool to forecast inventory demand and "
            "re-order stock. What risk level applies under the EU AI Act?"
        ),
        "expected_refs": ["Article 5", "Article 6"],
        "expected_keywords": ["minimal", "risk", "obligations"],
        "category": "minimal",
        "notes": (
            "Operational forecasting with no impact on fundamental rights — "
            "minimal-risk residual bucket. Risk-classification task."
        ),
    },
    {
        "id": "st_v4_019",
        "question": (
            "A word processor uses AI to check spelling and grammar as the user "
            "types. Does the EU AI Act impose any specific obligations?"
        ),
        "expected_refs": ["Article 5", "Article 6"],
        "expected_keywords": ["minimal", "risk", "no specific"],
        "category": "minimal",
        "notes": (
            "Productivity aid, no high-risk domain — minimal-risk residual "
            "bucket. Risk-classification task."
        ),
    },
    {
        "id": "st_v4_020",
        "question": (
            "What is the difference between a minimal-risk and a high-risk AI "
            "system under the EU AI Act's risk-based approach?"
        ),
        "expected_refs": ["Article 5", "Article 6"],
        "expected_keywords": ["high-risk", "minimal", "risk"],
        "category": "minimal",
        "notes": (
            "Conceptual QA on the paper's four-tier risk pyramid. Minimal is the "
            "residual after Art. 5 / Art. 6 checks."
        ),
    },
]
