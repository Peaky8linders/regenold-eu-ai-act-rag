"""V2 tricky single-turn eval scenarios — harder than scenarios_tricky_extended.

Each scenario probes an edge case the davidath benchmark + the existing
extended set don't already cover. Distribution across categories:

* ``omnibus`` (6)               — May 2026 Digital Omnibus changes
* ``role_ambiguity`` (5)        — system is BOTH provider AND deployer
* ``conflict`` (4)              — clash between two AI Act articles
* ``borderline_prohibition`` (5)— Art. 5 carve-outs / Recital 16 boundaries
* ``gpai`` (5)                  — fine-tune thresholds, open-weights edges
* ``cross_framework`` (3)       — AI Act + GDPR / MDR / NIS2 / DSA overlap
* ``near_oos`` (3)              — looks like AI Act but is DSA / NIS2 / PLD

Schema (dict, NOT Scenario dataclass — feeds a future scoring pass):

    {
        "id": str,
        "question": str,
        "expected_refs": list[str],    # user-facing form, "Article N" / "Annex N"
        "expected_keywords": list[str],
        "category": str,
        "notes": str,
    }
"""
from __future__ import annotations


SCENARIOS: list[dict] = [
    # ─────────────────────────────────────────────────────────────────────
    # omnibus (6)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_001",
        "question": "After the 7 May 2026 Digital Omnibus agreement, when do Annex III high-risk obligations actually start applying?",
        "expected_refs": ["Article 113"],
        "expected_keywords": ["2 December 2027", "Annex III"],
        "category": "omnibus",
        "notes": "Post-Omnibus Annex III date is 2 Dec 2027 (was 2 Aug 2026). Engine must NOT cite the older date.",
    },
    {
        "id": "tr_v2_002",
        "question": "Did the Digital Omnibus push back the prohibited-AI deadline?",
        "expected_refs": ["Article 5", "Article 113"],
        "expected_keywords": ["2 February 2025", "still", "applies"],
        "category": "omnibus",
        "notes": "Art. 5 prohibitions were NOT deferred. Engine must reject the implicit deferral framing.",
    },
    {
        "id": "tr_v2_003",
        "question": "What's the new GPAI compute threshold from the Commission's July 2025 Guidelines?",
        "expected_refs": ["Article 51"],
        "expected_keywords": ["10", "FLOPs", "general-purpose"],
        "category": "omnibus",
        "notes": "Post-Guidelines threshold: 10²³ FLOPs to qualify as GPAI under Art. 51, 10²⁵ for systemic risk. Engine must surface 10²³.",
    },
    {
        "id": "tr_v2_004",
        "question": "Is the EU AI Office allowed to impose fines directly on a GPAI provider, or only national authorities?",
        "expected_refs": ["Article 101"],
        "expected_keywords": ["Commission", "fines", "directly"],
        "category": "omnibus",
        "notes": "Art. 101 — Commission imposes fines on GPAI providers. Different from Art. 99 national-authority route.",
    },
    {
        "id": "tr_v2_005",
        "question": "We grew from a 30-employee SME to a 220-employee company last quarter. Do we lose AI Act SME privileges?",
        "expected_refs": ["Article 62", "Article 63"],
        "expected_keywords": ["small mid-cap", "preserve", "extended"],
        "category": "omnibus",
        "notes": "Digital Omnibus extended SME privileges to small mid-caps (Art. 62/63). Engine must NOT say privileges are lost on graduation from SME.",
    },
    {
        "id": "tr_v2_006",
        "question": "We're a GPAI provider that fine-tuned another model with 35% of the base model's compute. Did we become the new provider?",
        "expected_refs": ["Article 25", "Article 51"],
        "expected_keywords": ["one-third", "modifier", "provider"],
        "category": "omnibus",
        "notes": "Digital Omnibus 1/3 fine-tune rule. 35% > 1/3 → modifier becomes new provider. Engine must apply the rule.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # role_ambiguity (5)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_007",
        "question": "We built an internal AI for our own HR use — never released externally. Are we a provider or just a deployer?",
        "expected_refs": ["Article 3", "Article 16", "Article 26"],
        "expected_keywords": ["both", "provider", "deployer"],
        "category": "role_ambiguity",
        "notes": "Internal-only builder is BOTH provider (because they built it) AND deployer (because they use it). Engine must address both stacks.",
    },
    {
        "id": "tr_v2_008",
        "question": "A non-EU company sells AI to EU customers but has no EU establishment. Who is liable on the EU side?",
        "expected_refs": ["Article 22"],
        "expected_keywords": ["authorised representative", "established", "mandate"],
        "category": "role_ambiguity",
        "notes": "Art. 22 forces non-EU providers to appoint an authorised representative — that representative carries EU-side obligations.",
    },
    {
        "id": "tr_v2_009",
        "question": "An importer rebrands a high-risk AI under its own name before selling it on. Do they become the provider?",
        "expected_refs": ["Article 25"],
        "expected_keywords": ["name", "trademark", "provider"],
        "category": "role_ambiguity",
        "notes": "Art. 25(1)(a) — putting name/trademark on a high-risk AI flips importer/distributor into provider.",
    },
    {
        "id": "tr_v2_010",
        "question": "Our SaaS lets enterprise customers configure a CV-screening AI for their hiring. Are we the provider or are they?",
        "expected_refs": ["Article 3", "Article 25"],
        "expected_keywords": ["provider", "configure", "intended purpose"],
        "category": "role_ambiguity",
        "notes": "If customer significantly configures intended purpose, they become the provider via Art. 25 substantial-modification path. Engine must surface that the role is not pre-determined.",
    },
    {
        "id": "tr_v2_011",
        "question": "We resell a CE-marked high-risk biometric AI without modifying it. What are our obligations as distributor?",
        "expected_refs": ["Article 24"],
        "expected_keywords": ["distributor", "verify", "CE marking"],
        "category": "role_ambiguity",
        "notes": "Art. 24 distributor obligations. Engine must NOT confuse with importer (Art. 23) or provider (Art. 16).",
    },
    # ─────────────────────────────────────────────────────────────────────
    # conflict (4)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_012",
        "question": "If my chatbot is also a high-risk medical-triage AI, does Article 13 transparency or Article 50 chatbot-disclosure apply?",
        "expected_refs": ["Article 13", "Article 50"],
        "expected_keywords": ["both", "cumulative", "apply"],
        "category": "conflict",
        "notes": "Both apply cumulatively. Art. 13 (provider→deployer) and Art. 50 (provider→user) target different stakeholders.",
    },
    {
        "id": "tr_v2_013",
        "question": "Our Annex IV technical documentation contains trade secrets. Article 78 says authorities must keep them confidential — can we refuse to share them under Article 11?",
        "expected_refs": ["Article 11", "Article 78"],
        "expected_keywords": ["confidentiality", "obligation", "still required"],
        "category": "conflict",
        "notes": "Confidentiality under Art. 78 does NOT relieve the documentation obligation under Art. 11. Engine must reject the false choice.",
    },
    {
        "id": "tr_v2_014",
        "question": "A FRIA under Article 27 and a conformity assessment under Article 43 cover overlapping fundamental-rights checks. Can we skip one?",
        "expected_refs": ["Article 27", "Article 43"],
        "expected_keywords": ["distinct", "both", "deployer"],
        "category": "conflict",
        "notes": "FRIA is deployer-side, conformity assessment is provider-side. Engine must not let the user collapse them.",
    },
    {
        "id": "tr_v2_015",
        "question": "Article 13 says transparency, Article 86 says right to explanation. Aren't they the same thing?",
        "expected_refs": ["Article 13", "Article 86"],
        "expected_keywords": ["different", "provider", "individual"],
        "category": "conflict",
        "notes": "Art. 13 is structural (provider designs transparency mechanism); Art. 86 is individual-rights (affected person gets per-decision explanation). Engine must distinguish.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # borderline_prohibition (5)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_016",
        "question": "Is biometric categorization for age detection in a retail store prohibited under Article 5(1)(g)?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["age", "not", "permitted"],
        "category": "borderline_prohibition",
        "notes": "Age categorization is NOT in the Art. 5(1)(g) prohibited list (race, political opinion, trade-union, religion, sex life, sexual orientation). Engine must NOT over-prohibit.",
    },
    {
        "id": "tr_v2_017",
        "question": "We use emotion recognition in a medical-device AI to monitor pain in non-verbal patients. Is that prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["medical", "carve-out", "permitted"],
        "category": "borderline_prohibition",
        "notes": "Art. 5(1)(f) prohibits emotion recognition in workplace/education, but carves out medical and safety reasons. Engine must surface the carve-out.",
    },
    {
        "id": "tr_v2_018",
        "question": "Is real-time RBI in public spaces prohibited for police investigating ongoing terrorist attacks?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["terrorist", "exception", "authorisation"],
        "category": "borderline_prohibition",
        "notes": "Art. 5(1)(h)(iii) — imminent threat / terrorist attack carve-out, subject to prior authorisation. Engine must apply the exception.",
    },
    {
        "id": "tr_v2_019",
        "question": "We scrape facial images from publicly available CCTV footage to build a recognition database. Is that prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["untargeted", "scraping", "prohibited"],
        "category": "borderline_prohibition",
        "notes": "Art. 5(1)(e) prohibits untargeted scraping of facial images from internet OR CCTV for facial-recognition databases. Engine must NOT miss the CCTV branch (commonly overlooked vs. the internet-scraping branch).",
    },
    {
        "id": "tr_v2_020",
        "question": "We use AI to score creditworthiness on a 1-10 scale used internally only — not shared, not affecting public services. Is that social scoring?",
        "expected_refs": ["Article 5", "Annex III"],
        "expected_keywords": ["credit", "not", "Annex III"],
        "category": "borderline_prohibition",
        "notes": "Credit scoring is Annex III(5)(b) high-risk, NOT social scoring (Art. 5(1)(c)). The distinction: social scoring uses unrelated context to disadvantage. Engine must NOT mis-route to Art. 5 prohibition.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # gpai (5)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_021",
        "question": "Our GPAI is open-weights but we trained at exactly 1×10²⁵ FLOPs. Do we still get the Article 53(2) open-weights carve-out?",
        "expected_refs": ["Article 53", "Article 55"],
        "expected_keywords": ["systemic", "carve-out", "not apply"],
        "category": "gpai",
        "notes": "Art. 53(2) open-weights carve-out does NOT apply to systemic-risk GPAI. At 10²⁵ FLOPs, the model is systemic-risk per Art. 51(2). Engine must rebut.",
    },
    {
        "id": "tr_v2_022",
        "question": "We fine-tune a third-party GPAI with 30% of the base compute. Are we now the provider?",
        "expected_refs": ["Article 25", "Article 51"],
        "expected_keywords": ["one-third", "below", "not"],
        "category": "gpai",
        "notes": "30% is BELOW the 1/3 fine-tune threshold per Commission Guidelines + Digital Omnibus. Modifier does NOT become provider. Boundary opposite of tr_v2_006.",
    },
    {
        "id": "tr_v2_023",
        "question": "Does the AI Act require GPAI providers to disclose training data sources?",
        "expected_refs": ["Article 53"],
        "expected_keywords": ["training data", "summary", "sufficiently detailed"],
        "category": "gpai",
        "notes": "Art. 53(1)(d) — sufficiently detailed summary of training content. Distinct from the 'list all data sources' framing the user may carry.",
    },
    {
        "id": "tr_v2_024",
        "question": "If we use a GPAI as a component in our high-risk AI, do GPAI obligations transfer to us?",
        "expected_refs": ["Article 25", "Article 53"],
        "expected_keywords": ["value chain", "cooperation", "provider"],
        "category": "gpai",
        "notes": "Art. 25 + Art. 53(3) — value-chain cooperation obligation. The integrating provider takes on its own obligations but the GPAI provider's obligations remain with the GPAI provider.",
    },
    {
        "id": "tr_v2_025",
        "question": "We're a GPAI provider with no EU establishment. Can we appoint our European customer as our authorised representative?",
        "expected_refs": ["Article 54"],
        "expected_keywords": ["GPAI", "authorised representative", "established"],
        "category": "gpai",
        "notes": "Art. 54 — GPAI authorised representative is a SEPARATE provision from Art. 22 (high-risk authorised rep). Engine must cite the GPAI-specific Article 54.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # cross_framework (3)
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_026",
        "question": "Our medical-device AI is already CE-marked under MDR. Do we still need a separate AI Act conformity assessment?",
        "expected_refs": ["Article 43", "Annex I"],
        "expected_keywords": ["integrated", "MDR", "Annex I"],
        "category": "cross_framework",
        "notes": "Art. 43(3) + Annex I — for Annex I product safety AI, AI Act conformity assessment integrates with existing sectoral conformity (e.g., MDR). Engine must explain the integration, not duplicate.",
    },
    {
        "id": "tr_v2_027",
        "question": "Does our existing GDPR Article 35 DPIA satisfy the Article 27 FRIA requirement?",
        "expected_refs": ["Article 27"],
        "expected_keywords": ["does not", "FRIA", "in addition"],
        "category": "cross_framework",
        "notes": "A DPIA does NOT replace a FRIA. The FRIA can build on the DPIA but Art. 27 requires its own deliverable. Engine must reject the substitution.",
    },
    {
        "id": "tr_v2_028",
        "question": "Our high-risk AI provides cybersecurity for critical infrastructure. We already report incidents under NIS2. Do AI Act incident-reporting obligations still apply?",
        "expected_refs": ["Article 73"],
        "expected_keywords": ["serious incident", "in addition", "AI Act"],
        "category": "cross_framework",
        "notes": "NIS2 + AI Act incident reporting are PARALLEL, not substitutive. Art. 73 is AI-specific serious-incident reporting. Engine must keep them distinct.",
    },
    # ─────────────────────────────────────────────────────────────────────
    # near_oos (3) — looks like AI Act, isn't
    # ─────────────────────────────────────────────────────────────────────
    {
        "id": "tr_v2_029",
        "question": "What are the algorithmic transparency obligations for a Very Large Online Platform's content-moderation AI?",
        "expected_refs": [],
        "expected_keywords": ["Digital Services Act", "DSA", "not the EU AI Act"],
        "category": "near_oos",
        "notes": "VLOP algorithmic-transparency is DSA (Art. 27, Art. 39 DSA), NOT AI Act. Engine should refuse-with-pointer rather than answer with AI Act citations.",
    },
    {
        "id": "tr_v2_030",
        "question": "If a high-risk AI causes property damage to a customer, what AI-Act liability rules apply?",
        "expected_refs": [],
        "expected_keywords": ["Product Liability", "PLD", "not the EU AI Act"],
        "category": "near_oos",
        "notes": "AI civil liability is governed by the revised Product Liability Directive + (eventually) the AI Liability Directive, NOT the AI Act itself. The AI Act regulates compliance, not damages.",
    },
    {
        "id": "tr_v2_031",
        "question": "We're a designated essential-services entity using AI for SOC operations. What cyber-resilience obligations apply to the AI itself?",
        "expected_refs": [],
        "expected_keywords": ["NIS2", "Cyber Resilience Act", "not the EU AI Act"],
        "category": "near_oos",
        "notes": "Cyber-resilience for essential-services SOCs is NIS2 / CRA territory. AI Act covers AI-specific risks but not entity-level cyber resilience. Engine should refuse-with-pointer.",
    },
]


if __name__ == "__main__":
    print(len(SCENARIOS))
