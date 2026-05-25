"""R89 live-probe scenarios — 40 representative questions spanning
the most important EU AI Act topics.

Authored 2026-05-26 for the post-R89-A live re-measurement against
the Railway production endpoint (Cloudflare tunnel + Claude Max
wrapper). Designed to exercise the **judged rubric** axes:
correctness, references-vs-gold, conciseness, tone, latency,
multi-turn coherence.

Coverage map (40 rows total):

* ``high_risk_classification`` (6) — Annex III, Art. 6 / Annex I
* ``provider_obligations`` (5) — Art. 16, 9, 10, 11, 17
* ``deployer_obligations`` (5) — Art. 26, 27 FRIA, 50 limited-risk
* ``prohibited_practices`` (5) — Art. 5 sub-points + carve-outs
* ``gpai_models`` (5) — Art. 51, 53, 55, FOSS carve-out, Codes
* ``governance_enforcement`` (4) — Art. 70, 99, 73, AI Office
* ``transparency_disclosure`` (3) — Art. 13, 50(2) deepfakes, 50(4)
* ``timeline_omnibus`` (3) — Art. 113 post-Digital-Omnibus dates
* ``multi_turn`` (4 × 3-turn scenarios) — coreferent drill-down

Each scenario has:
    * ``id``: stable identifier
    * ``question`` (single-turn) OR ``turns`` (multi-turn list)
    * ``expected_refs``: user-facing form, the gold citation set
    * ``expected_keywords``: literal substrings the answer should
       surface to score on the kw_recall axis
    * ``category``: bucket for per-category scorecard
    * ``notes``: why this row matters
"""

from __future__ import annotations


# ── Single-turn scenarios (36 rows) ─────────────────────────────────────


SINGLE_TURN: list[dict] = [
    # ─────────────────────────────────────────────────────────────────
    # HIGH-RISK CLASSIFICATION (6)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_hrc_01",
        "question": "Is a CV-screening AI for shortlisting job candidates considered high-risk under the EU AI Act?",
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": ["high-risk", "employment", "recruitment"],
        "category": "high_risk_classification",
        "notes": "Annex III §4 — employment / worker management; recruitment-and-selection use case.",
    },
    {
        "id": "live_hrc_02",
        "question": "We're deploying an AI system to triage 911 emergency calls. Does this fall under Annex III?",
        "expected_refs": ["Annex III", "Article 6"],
        "expected_keywords": ["dispatching", "emergency", "high-risk"],
        "category": "high_risk_classification",
        "notes": "Annex III §5(d) — emergency response triage.",
    },
    {
        "id": "live_hrc_03",
        "question": "Does an AI-driven credit-scoring tool for consumer loans count as high-risk?",
        "expected_refs": ["Annex III", "Article 6"],
        "expected_keywords": ["creditworthiness", "credit score", "high-risk"],
        "category": "high_risk_classification",
        "notes": "Annex III §5(b) — creditworthiness assessment.",
    },
    {
        "id": "live_hrc_04",
        "question": "Our embedded AI is a safety component of a power-train control unit in a car. Is it high-risk under Article 6(1)?",
        "expected_refs": ["Article 6", "Annex I"],
        "expected_keywords": ["safety component", "Annex I", "high-risk"],
        "category": "high_risk_classification",
        "notes": "Art. 6(1) Annex I embedded-product path (vehicle safety).",
    },
    {
        "id": "live_hrc_05",
        "question": "Can a system fall in Annex III but escape high-risk classification if its output is purely informational?",
        "expected_refs": ["Article 6"],
        "expected_keywords": ["narrow procedural", "preparatory", "not pose"],
        "category": "high_risk_classification",
        "notes": "Art. 6(3) — Annex III exemption pathway for narrow / preparatory tasks.",
    },
    {
        "id": "live_hrc_06",
        "question": "Is biometric verification (1:1 face match) high-risk under Annex III §1?",
        "expected_refs": ["Annex III", "Article 6"],
        "expected_keywords": ["biometric", "identification", "verification"],
        "category": "high_risk_classification",
        "notes": "Annex III §1 explicitly covers remote biometric ID + categorisation; 1:1 verification is excluded.",
    },

    # ─────────────────────────────────────────────────────────────────
    # PROVIDER OBLIGATIONS (5)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_prov_01",
        "question": "As a high-risk AI provider, what are my core obligations under Article 16?",
        "expected_refs": ["Article 16"],
        "expected_keywords": ["provider", "obligations", "conformity"],
        "category": "provider_obligations",
        "notes": "Art. 16 enumerates the provider obligation chain.",
    },
    {
        "id": "live_prov_02",
        "question": "What does the Article 9 risk-management system have to cover throughout the AI lifecycle?",
        "expected_refs": ["Article 9"],
        "expected_keywords": ["risk management", "iterative", "lifecycle"],
        "category": "provider_obligations",
        "notes": "Art. 9 — iterative risk-management process spanning entire lifecycle.",
    },
    {
        "id": "live_prov_03",
        "question": "How does Article 10 govern the training, validation, and testing datasets used by high-risk AI?",
        "expected_refs": ["Article 10"],
        "expected_keywords": ["data governance", "relevant", "representative"],
        "category": "provider_obligations",
        "notes": "Art. 10 — data + data governance, statistical properties, bias mitigation.",
    },
    {
        "id": "live_prov_04",
        "question": "What technical documentation does Article 11 require providers of high-risk AI to maintain?",
        "expected_refs": ["Article 11", "Annex IV"],
        "expected_keywords": ["technical documentation", "Annex IV", "demonstrate"],
        "category": "provider_obligations",
        "notes": "Art. 11 + Annex IV — full technical documentation contents.",
    },
    {
        "id": "live_prov_05",
        "question": "What quality management system does Article 17 require from providers of high-risk AI systems?",
        "expected_refs": ["Article 17"],
        "expected_keywords": ["quality management", "documented", "policies"],
        "category": "provider_obligations",
        "notes": "Art. 17 QMS — strategy for regulatory compliance, design controls, etc.",
    },

    # ─────────────────────────────────────────────────────────────────
    # DEPLOYER OBLIGATIONS (5)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_dep_01",
        "question": "What does Article 26 require of deployers of high-risk AI systems?",
        "expected_refs": ["Article 26"],
        "expected_keywords": ["deployer", "instructions", "human oversight"],
        "category": "deployer_obligations",
        "notes": "Art. 26 — deployer use-per-instructions + oversight + monitoring.",
    },
    {
        "id": "live_dep_02",
        "question": "When must a deployer conduct a fundamental rights impact assessment, and what does it cover?",
        "expected_refs": ["Article 27"],
        "expected_keywords": ["FRIA", "fundamental rights", "affected persons"],
        "category": "deployer_obligations",
        "notes": "Art. 27 FRIA — public-authority deployers + certain Annex III categories.",
    },
    {
        "id": "live_dep_03",
        "question": "We're deploying a customer-service chatbot on our website. Do Article 50 disclosure rules apply?",
        "expected_refs": ["Article 50"],
        "expected_keywords": ["disclose", "AI", "interacting"],
        "category": "deployer_obligations",
        "notes": "Art. 50(1) — AI interacting with natural persons must disclose AI nature.",
    },
    {
        "id": "live_dep_04",
        "question": "Do we need to inform our workers' representatives before deploying a high-risk AI system in the workplace?",
        "expected_refs": ["Article 26"],
        "expected_keywords": ["workers", "inform", "representatives"],
        "category": "deployer_obligations",
        "notes": "Art. 26(7) — workers + representatives must be informed before workplace HRAIS deployment.",
    },
    {
        "id": "live_dep_05",
        "question": "How long must a deployer retain the automatically generated logs of a high-risk AI system?",
        "expected_refs": ["Article 26", "Article 19"],
        "expected_keywords": ["logs", "six months", "retain"],
        "category": "deployer_obligations",
        "notes": "Art. 26(6) refers back to Art. 19 — minimum 6 months log retention.",
    },

    # ─────────────────────────────────────────────────────────────────
    # PROHIBITED PRACTICES (5)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_proh_01",
        "question": "Is using AI to detect emotional state of call-centre agents prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["emotion recognition", "workplace", "prohibited"],
        "category": "prohibited_practices",
        "notes": "Art. 5(1)(f) — emotion recognition in workplace / education is prohibited.",
    },
    {
        "id": "live_proh_02",
        "question": "Can we use AI to infer protected characteristics like race or political views from biometric data?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["biometric categorisation", "race", "prohibited"],
        "category": "prohibited_practices",
        "notes": "Art. 5(1)(g) — biometric categorisation by sensitive attributes is prohibited.",
    },
    {
        "id": "live_proh_03",
        "question": "Is real-time facial recognition by police in public spaces always prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["real-time", "judicial", "exceptions"],
        "category": "prohibited_practices",
        "notes": "Art. 5(1)(h) — prohibited by default; narrow exceptions need prior judicial authorisation.",
    },
    {
        "id": "live_proh_04",
        "question": "Is a government-run AI social-scoring system that affects access to public services prohibited?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["social scoring", "detrimental", "prohibited"],
        "category": "prohibited_practices",
        "notes": "Art. 5(1)(c) — social scoring leading to detrimental treatment is prohibited.",
    },
    {
        "id": "live_proh_05",
        "question": "Does the prohibition on emotion recognition have any medical-device carve-out?",
        "expected_refs": ["Article 5"],
        "expected_keywords": ["medical", "safety", "exception"],
        "category": "prohibited_practices",
        "notes": "Art. 5(1)(f) — narrow medical / safety carve-out exists.",
    },

    # ─────────────────────────────────────────────────────────────────
    # GPAI MODELS (5)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_gpai_01",
        "question": "When does a general-purpose AI model become classified as having systemic risk under Article 51?",
        "expected_refs": ["Article 51"],
        "expected_keywords": ["systemic risk", "10²⁵", "high-impact"],
        "category": "gpai_models",
        "notes": "Art. 51 — high-impact capabilities, 10²⁵ FLOPs presumption.",
    },
    {
        "id": "live_gpai_02",
        "question": "What are the obligations of providers of GPAI models under Article 53?",
        "expected_refs": ["Article 53"],
        "expected_keywords": ["technical documentation", "downstream", "training-data summary"],
        "category": "gpai_models",
        "notes": "Art. 53 — Annex XI docs + Annex XII downstream info + copyright policy + training-data summary.",
    },
    {
        "id": "live_gpai_03",
        "question": "Does Article 53 apply to free and open-source GPAI models that don't have systemic risk?",
        "expected_refs": ["Article 53"],
        "expected_keywords": ["open-source", "carve-out", "does not apply"],
        "category": "gpai_models",
        "notes": "Art. 53(2) FOSS carve-out — documentation duties don't apply below systemic threshold.",
    },
    {
        "id": "live_gpai_04",
        "question": "What additional duties does Article 55 impose on GPAI models with systemic risk?",
        "expected_refs": ["Article 55"],
        "expected_keywords": ["systemic", "model evaluation", "incident"],
        "category": "gpai_models",
        "notes": "Art. 55 — model eval, systemic-risk mitigation, incident tracking, cybersecurity.",
    },
    {
        "id": "live_gpai_05",
        "question": "How can a GPAI provider demonstrate compliance with Articles 53 and 55 without signing a Code of Practice?",
        "expected_refs": ["Article 56"],
        "expected_keywords": ["adequate means", "alternative", "demonstrate"],
        "category": "gpai_models",
        "notes": "Art. 56 — Codes voluntary; alternative adequate means accepted.",
    },

    # ─────────────────────────────────────────────────────────────────
    # GOVERNANCE & ENFORCEMENT (4)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_gov_01",
        "question": "What's the maximum fine for placing a prohibited AI practice on the EU market?",
        "expected_refs": ["Article 99"],
        "expected_keywords": ["€35M", "7%", "global"],
        "category": "governance_enforcement",
        "notes": "Art. 99(3) — €35M or 7% of worldwide annual turnover, whichever is higher.",
    },
    {
        "id": "live_gov_02",
        "question": "Which national authority is responsible for market surveillance under Article 70?",
        "expected_refs": ["Article 70"],
        "expected_keywords": ["market surveillance", "competent", "designate"],
        "category": "governance_enforcement",
        "notes": "Art. 70 — each Member State designates competent + market-surveillance authorities.",
    },
    {
        "id": "live_gov_03",
        "question": "How quickly must a provider report a serious incident under Article 73?",
        "expected_refs": ["Article 73"],
        "expected_keywords": ["serious incident", "15 days", "market surveillance"],
        "category": "governance_enforcement",
        "notes": "Art. 73 — within 15 days of awareness (shorter for fatalities / critical infra).",
    },
    {
        "id": "live_gov_04",
        "question": "Can the European AI Office directly fine providers of GPAI models?",
        "expected_refs": ["Article 101"],
        "expected_keywords": ["AI Office", "Commission", "fine"],
        "category": "governance_enforcement",
        "notes": "Art. 101 — Commission via AI Office is sole direct-fining authority for GPAI providers.",
    },

    # ─────────────────────────────────────────────────────────────────
    # TRANSPARENCY & DISCLOSURE (3)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_trans_01",
        "question": "What information must a high-risk AI provider give to the deployer under Article 13?",
        "expected_refs": ["Article 13"],
        "expected_keywords": ["transparency", "instructions", "deployers"],
        "category": "transparency_disclosure",
        "notes": "Art. 13 — instructions for use + transparency information for deployers.",
    },
    {
        "id": "live_trans_02",
        "question": "Do we have to label AI-generated synthetic content like deepfakes?",
        "expected_refs": ["Article 50"],
        "expected_keywords": ["deepfake", "labelled", "AI-generated"],
        "category": "transparency_disclosure",
        "notes": "Art. 50(4) — deepfakes + AI-generated content must be labelled.",
    },
    {
        "id": "live_trans_03",
        "question": "Must a generative AI provider mark its outputs as machine-readable AI-generated content?",
        "expected_refs": ["Article 50"],
        "expected_keywords": ["machine-readable", "AI-generated", "marked"],
        "category": "transparency_disclosure",
        "notes": "Art. 50(2) — generative AI outputs must be marked in machine-readable form.",
    },

    # ─────────────────────────────────────────────────────────────────
    # TIMELINE / OMNIBUS (3)
    # ─────────────────────────────────────────────────────────────────
    {
        "id": "live_time_01",
        "question": "After the Digital Omnibus, when do Annex III high-risk obligations actually start applying?",
        "expected_refs": ["Article 113"],
        "expected_keywords": ["2 December 2027", "Annex III", "Digital Omnibus"],
        "category": "timeline_omnibus",
        "notes": "Post-Omnibus deferral — Annex III HRAIS to 2 Dec 2027.",
    },
    {
        "id": "live_time_02",
        "question": "Did the 7 May 2026 Digital Omnibus push back Article 5 prohibitions?",
        "expected_refs": ["Article 5", "Article 113"],
        "expected_keywords": ["prohibitions", "2 February 2025", "still"],
        "category": "timeline_omnibus",
        "notes": "Prohibitions were NOT deferred — they applied from 2 Feb 2025.",
    },
    {
        "id": "live_time_03",
        "question": "What's the new deadline for Annex I embedded-product high-risk obligations?",
        "expected_refs": ["Article 113"],
        "expected_keywords": ["2 August 2028", "Annex I", "embedded"],
        "category": "timeline_omnibus",
        "notes": "Post-Omnibus deferral — Annex I embedded-product to 2 Aug 2028.",
    },
]


# ── Multi-turn scenarios (4 × 3-turn each) ──────────────────────────────


MULTI_TURN: list[dict] = [
    {
        "id": "live_mt_01",
        "category": "multi_turn",
        "turns": [
            {"role": "user", "content": "We're a French hospital deploying an AI diagnostic assistant for triage."},
            {"role": "assistant", "content": "Understood — that sounds like an Annex III §5(d) high-risk healthcare AI deployment. As a deployer of a high-risk system, you fall under Article 26 baseline duties plus an Article 27 fundamental-rights impact assessment because you're a public-authority deployer."},
            {"role": "user", "content": "What does the FRIA need to cover?"},
        ],
        "expected_final_refs": ["Article 27"],
        "expected_final_keywords": ["FRIA", "affected persons", "fundamental rights"],
        "notes": "Coreferent drill-down: FRIA mentioned in T2, user asks for details in T3.",
    },
    {
        "id": "live_mt_02",
        "category": "multi_turn",
        "turns": [
            {"role": "user", "content": "We're a GPAI provider releasing a 50B-parameter open-weights model under an Apache-2.0 license."},
            {"role": "assistant", "content": "Article 53 lays out the GPAI provider duties: technical documentation per Annex XI, downstream-provider information per Annex XII, a copyright policy, and a publicly available training-data summary. If your model crosses the 10²⁵ FLOPs threshold, Article 51 also classifies it as having systemic risk."},
            {"role": "user", "content": "Does the open-weights release change which of those obligations apply?"},
        ],
        "expected_final_refs": ["Article 53"],
        "expected_final_keywords": ["carve-out", "open-source", "does not apply"],
        "notes": "Drill-down to Art. 53(2) FOSS carve-out.",
    },
    {
        "id": "live_mt_03",
        "category": "multi_turn",
        "turns": [
            {"role": "user", "content": "Our HR-tech SaaS lets enterprise customers configure a CV-screening AI for their hiring."},
            {"role": "assistant", "content": "That places the CV-screening system squarely in Annex III §4 (employment / worker management), so it's high-risk under Article 6. As a provider, you carry the Article 16 obligation chain; your customers, when they configure and deploy, become deployers under Article 26."},
            {"role": "user", "content": "If our customers substantially modify the model, do they become providers too?"},
        ],
        "expected_final_refs": ["Article 25"],
        "expected_final_keywords": ["substantial modification", "deployer", "provider"],
        "notes": "Drill-down to Art. 25(1) — substantial modification triggers provider role.",
    },
    {
        "id": "live_mt_04",
        "category": "multi_turn",
        "turns": [
            {"role": "user", "content": "Our generative video app produces deepfake-style content for film studios."},
            {"role": "assistant", "content": "Article 50 transparency rules apply: deepfakes and AI-generated synthetic content must be labelled as artificially generated under Article 50(4); generative AI outputs must also be marked in machine-readable form under Article 50(2)."},
            {"role": "user", "content": "When do the watermarking rules actually start applying?"},
        ],
        "expected_final_refs": ["Article 113"],
        "expected_final_keywords": ["2 August 2026", "general application"],
        "notes": "Art. 113 — general application date for Art. 50 transparency duties was 2 Aug 2026.",
    },
]


# ── Public API ───────────────────────────────────────────────────────────

ALL_SCENARIOS: list[dict] = SINGLE_TURN + MULTI_TURN
