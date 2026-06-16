"""Fresh MEDICAL / HEALTHCARE / LIFE-SCIENCES EU AI Act benchmark (R124).

Grounding
---------
The QUESTION themes + reasoning-level taxonomy are grounded in the public
**GraphRAG-Bench** dataset family and adjacent public medical-RAG benchmarks
(all open-licensed; we reuse only their *themes*, never their text):

* **GraphRAG-Bench/GraphRAG-Bench** — arXiv 2506.05690, MIT. Its ``medical``
  subset (2,060 rows) is sourced from **NCCN oncology clinical guidelines**
  (skin cancer + CNS lymphoma) and ships a 4-level reasoning taxonomy:
  **L1 Fact Retrieval · L2 Multi-hop Reasoning · L3 Contextual Summarization ·
  L4 Generation**. We carry that ``reasoning_level`` tag through.
* **MedMCQA** (arXiv 2203.14371, MIT/Apache-2.0) — 21 clinical subjects;
  breadth source for the non-oncology themes.
* **MIRAGE / MedRAG** (arXiv 2402.13178, CC-BY-4.0) — clinical + biomedical-
  literature blend.
* **PubMedQA** (1909.06146), **BioASQ** (CC-BY-2.5), **MedRGB** (2411.09213) —
  drug-target-disease + research-literature reasoning themes.

The 24 questions map each public-dataset medical theme onto its EU AI Act
classification + obligations. Reference grounding is the **verbatim EU AI Act
text** (Regulation 2024/1689), resolved in-repo via
``app.data.provision_text.get_provision_text`` (e.g. Annex III §5 healthcare
eligibility / emergency triage; Article 5(1)(f) medical emotion-recognition
carve-out; Article 6(1) + Annex I medical-device safety-component route;
Article 2(6) R&D exclusion). Every ``expected_refs`` entry is validated against
``ARTICLE_EXISTENCE`` by ``validate_medtech_graphrag_v124``.

``gold_answer`` is the regulator-voice reference each row is scored against. It
is author-written grounded in the verbatim provision text above; the companion
``ground_medtech_graphrag_v124.py`` regenerates / cross-checks it with **Claude
Sonnet 4.6** primed on the same verbatim text (the "use the LLM judge to ground
the answers" path) — a deterministic generate-once-then-pin artefact.

Distinctness
------------
IDs are prefixed ``grb_`` — disjoint from every existing eval set
(``gt_*`` GraphRAG-paper, ``med_*`` / ``mt_*`` MedTech-lifesci,
``mv2_*`` / ``mt_med_*`` multi-turn). The questions are freshly authored, not
copied from any existing scenario file.

Schema (mirrors ``scenarios_graphrag_benchmark.GROUND_TRUTH`` + provenance):

    {
        "id", "question", "expected_refs", "expected_keywords",
        "gold_answer", "category", "graphrag_theme", "reasoning_level",
        "notes",
    }

Run: ``python -m evals.regenold.run_medtech_graphrag_v124 --local --label X``
     (or ``--endpoint <live> --api-key $P2P_REGENOLD_API_KEY``); then judge with
     ``python -m evals.judge.runner --bench-sidecar <sidecar> --label X``.
"""
from __future__ import annotations

GROUND_TRUTH: list[dict] = [
    # ── L1 — Fact retrieval / risk classification ───────────────────────────
    {
        "id": "grb_01",
        "question": (
            "Is AI software that detects melanoma from dermoscopy images a "
            "high-risk AI system under the EU AI Act?"
        ),
        "expected_refs": ["Article 6", "Annex I", "Article 43"],
        "expected_keywords": [
            "high-risk", "safety component", "medical device", "Annex I",
            "conformity assessment", "notified body",
        ],
        "gold_answer": (
            "Yes. Under Article 6(1) an AI system that is a medical device, or a "
            "safety component of one, covered by the Union harmonisation "
            "legislation in Annex I (the Medical Device Regulation) and required "
            "to undergo third-party conformity assessment is high-risk. Such a "
            "melanoma-detection system must therefore meet the Chapter III "
            "high-risk requirements and pass the conformity assessment under "
            "Article 43, integrated with the medical-device notified-body route."
        ),
        "category": "medtech_high_risk_classification",
        "graphrag_theme": "cancer diagnosis from medical imaging (GraphRAG-Bench medical / NCCN oncology, skin cancer)",
        "reasoning_level": "L1",
        "notes": "",
    },
    {
        "id": "grb_02",
        "question": (
            "Which EU AI Act article sets the transparency obligation for a "
            "patient-facing medical chatbot?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "transparency", "interact", "natural persons", "informed",
            "AI system",
        ],
        "gold_answer": (
            "Article 50 sets the transparency obligation: the provider must "
            "ensure the chatbot is designed so that natural persons are informed "
            "they are interacting with an AI system, unless that is obvious from "
            "the circumstances. If the chatbot also performs a medical-diagnostic "
            "function it is additionally high-risk and the Chapter III "
            "obligations apply on top."
        ),
        "category": "medtech_transparency",
        "graphrag_theme": "mental-health / patient-facing conversational AI (MedMCQA Psychiatry)",
        "reasoning_level": "L1",
        "notes": "",
    },
    {
        "id": "grb_03",
        "question": (
            "Under the EU AI Act, is an AI system used to dispatch and triage "
            "emergency-room patients high-risk?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "high-risk", "Annex III", "emergency", "triage", "essential services",
        ],
        "gold_answer": (
            "Yes. Annex III point 5 lists AI systems used to dispatch, or to "
            "establish priority in dispatching, emergency first-response services "
            "including patient triage as high-risk, and Article 6(2) makes "
            "Annex III systems high-risk. The deployer and provider must meet the "
            "corresponding Chapter III obligations."
        ),
        "category": "medtech_high_risk_classification",
        "graphrag_theme": "emergency-department patient triage (EU AI Act Annex III §5(d))",
        "reasoning_level": "L1",
        "notes": "",
    },
    {
        "id": "grb_04",
        "question": (
            "What does the EU AI Act require for an AI system that evaluates "
            "patients' eligibility for public healthcare benefits?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "high-risk", "Annex III", "eligibility", "essential public",
            "healthcare", "benefits",
        ],
        "gold_answer": (
            "Annex III point 5(a) classifies AI used by or for public authorities "
            "to evaluate eligibility for essential public assistance benefits and "
            "services, including healthcare, as high-risk under Article 6(2). The "
            "system is therefore subject to the full Chapter III high-risk regime, "
            "including a fundamental-rights impact assessment by the deploying "
            "authority."
        ),
        "category": "medtech_high_risk_classification",
        "graphrag_theme": "health-benefit eligibility scoring (EU AI Act Annex III §5(a))",
        "reasoning_level": "L1",
        "notes": "",
    },
    {
        "id": "grb_05",
        "question": (
            "Are AI systems used solely for scientific biomedical research and "
            "not placed on the market subject to the EU AI Act?"
        ),
        "expected_refs": ["Article 2"],
        "expected_keywords": [
            "scientific research", "development", "excluded", "market",
            "scope",
        ],
        "gold_answer": (
            "No. Article 2(6) excludes AI systems and models specifically "
            "developed and put into service for the sole purpose of scientific "
            "research and development, and Article 2(8) carves out research, "
            "testing and development activity prior to placing on the market or "
            "putting into service. Once such a system is placed on the market or "
            "deployed in real-world clinical use, the Regulation applies."
        ),
        "category": "medtech_scope",
        "graphrag_theme": "drug-discovery / biomedical research (PubMedQA, BioASQ)",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_06",
        "question": (
            "Is an AI system that infers patients' emotions for a medical "
            "purpose prohibited under Article 5 of the EU AI Act?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": [
            "emotion recognition", "prohibited", "medical", "exception",
            "workplace", "safety",
        ],
        "gold_answer": (
            "No. Article 5(1)(f) prohibits AI that infers emotions in the "
            "workplace and education settings, but it expressly exempts systems "
            "placed on the market or put into service for medical or safety "
            "reasons. Emotion inference for a genuine medical purpose is therefore "
            "not prohibited, though it may still be high-risk and remains subject "
            "to the applicable transparency and high-risk obligations."
        ),
        "category": "medtech_borderline_prohibition",
        "graphrag_theme": "emotion / affect recognition in patient care (Art 5(1)(f) medical carve-out)",
        "reasoning_level": "L2",
        "notes": "tricky carve-out",
    },
    # ── L2 — Multi-hop / obligations ────────────────────────────────────────
    {
        "id": "grb_07",
        "question": (
            "A hospital deploys a high-risk AI diagnostic system. What are its "
            "obligations as a deployer under the EU AI Act?"
        ),
        "expected_refs": ["Article 26", "Article 27"],
        "expected_keywords": [
            "deployer", "instructions for use", "human oversight",
            "fundamental rights impact assessment", "monitoring",
        ],
        "gold_answer": (
            "Under Article 26 the deploying hospital must use the system in "
            "accordance with the instructions for use, assign human oversight to "
            "competent staff, ensure input data is relevant, monitor operation "
            "and keep the automatically generated logs. As a public body "
            "providing an essential service it must also carry out a "
            "fundamental-rights impact assessment under Article 27 before putting "
            "the system into use."
        ),
        "category": "medtech_deployer_obligations",
        "graphrag_theme": "clinical decision support — deployer duties (MedQA, MIRAGE)",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_08",
        "question": (
            "What must the provider of a high-risk AI medical diagnostic system "
            "put in place before placing it on the market?"
        ),
        "expected_refs": ["Article 16", "Article 9", "Article 43"],
        "expected_keywords": [
            "provider", "risk management system", "quality management",
            "conformity assessment", "technical documentation",
        ],
        "gold_answer": (
            "Article 16 makes the provider responsible for the full high-risk "
            "compliance set: a risk-management system under Article 9, data "
            "governance, technical documentation, logging, transparency, human "
            "oversight and accuracy/robustness, plus a quality-management system. "
            "Before placing the device on the market the provider must pass the "
            "conformity assessment under Article 43 and draw up the EU "
            "declaration of conformity."
        ),
        "category": "medtech_provider_obligations",
        "graphrag_theme": "diagnostic device provider lifecycle (NCCN oncology CDS)",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_09",
        "question": (
            "What conformity-assessment route applies to an AI system that is a "
            "safety component of a CE-marked medical device?"
        ),
        "expected_refs": ["Article 43", "Annex I"],
        "expected_keywords": [
            "conformity assessment", "notified body", "medical device",
            "integrated", "Annex I",
        ],
        "gold_answer": (
            "Article 43(3) provides that where the high-risk AI system is a "
            "safety component of a product covered by the Annex I medical-device "
            "legislation, the AI Act conformity assessment is carried out as part "
            "of the single conformity-assessment procedure already required under "
            "that legislation, through the relevant notified body, rather than as "
            "a separate AI Act assessment."
        ),
        "category": "medtech_conformity",
        "graphrag_theme": "medical-device software (SaMD) conformity route",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_10",
        "question": (
            "What human-oversight measures does the EU AI Act require for a "
            "high-risk clinical decision-support system?"
        ),
        "expected_refs": ["Article 14"],
        "expected_keywords": [
            "human oversight", "natural persons", "override", "interpret",
            "automation bias",
        ],
        "gold_answer": (
            "Article 14 requires high-risk systems to be designed so that natural "
            "persons can effectively oversee them: the oversight staff must be "
            "able to understand the system's output and limitations, remain aware "
            "of automation bias, correctly interpret the result, and decide not "
            "to use the system or to override, disregard or reverse its output "
            "and to stop the system."
        ),
        "category": "medtech_human_oversight",
        "graphrag_theme": "clinical decision support oversight (MedQA management vignettes)",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_11",
        "question": (
            "What data-governance obligations apply to the training data of a "
            "high-risk AI sepsis-prediction model?"
        ),
        "expected_refs": ["Article 10"],
        "expected_keywords": [
            "data governance", "training", "representative", "relevant",
            "errors", "bias",
        ],
        "gold_answer": (
            "Article 10 requires that training, validation and testing datasets "
            "be subject to data-governance practices and be relevant, "
            "sufficiently representative, and to the best extent possible free of "
            "errors and complete in view of the intended purpose, with examination "
            "for possible biases and appropriate handling of any sensitive data "
            "used to detect and correct them."
        ),
        "category": "medtech_data_governance",
        "graphrag_theme": "sepsis / deterioration early-warning prediction (PubMedQA predictive-model literature)",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_12",
        "question": (
            "What logging and record-keeping does a high-risk AI radiology "
            "system require, and how long must the deploying hospital keep the "
            "logs?"
        ),
        "expected_refs": ["Article 12", "Article 19", "Article 26"],
        "expected_keywords": [
            "logging", "logs", "automatically", "traceability", "six months",
            "retain",
        ],
        "gold_answer": (
            "Article 12 requires the high-risk system to log events automatically "
            "over its lifetime for traceability, and Article 19 requires the "
            "provider to keep the logs it controls. Under Article 26(6) the "
            "deploying hospital must retain the automatically generated logs for "
            "at least six months, unless a longer period is set by applicable "
            "Union or national law."
        ),
        "category": "medtech_record_keeping",
        "graphrag_theme": "imaging diagnosis traceability / record-keeping (MedMCQA Radiology)",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "grb_13",
        "question": (
            "Does the EU AI Act require post-market monitoring and serious-"
            "incident reporting for an AI-based patient-monitoring device, and "
            "under which articles?"
        ),
        "expected_refs": ["Article 72", "Article 73"],
        "expected_keywords": [
            "post-market monitoring", "serious incident", "report",
            "market surveillance", "provider",
        ],
        "gold_answer": (
            "Yes. Article 72 requires the provider to set up and document a "
            "post-market monitoring system proportionate to the risks, actively "
            "collecting and reviewing the system's performance in use. Article 73 "
            "requires the provider to report any serious incident to the relevant "
            "market-surveillance authorities, within the deadlines that article "
            "specifies."
        ),
        "category": "medtech_post_market",
        "graphrag_theme": "remote patient monitoring / wearables (clinical-AI deployment surveys)",
        "reasoning_level": "L2",
        "notes": "",
    },
    # ── L3 — GPAI / summarization / classification verdicts ─────────────────
    {
        "id": "grb_14",
        "question": (
            "A pharma company trains a large foundation model for drug discovery "
            "whose training compute exceeds 10^25 FLOPs. Which EU AI Act "
            "obligations apply?"
        ),
        "expected_refs": ["Article 51", "Article 53", "Article 55"],
        "expected_keywords": [
            "general-purpose AI model", "systemic risk", "10^25 FLOPs",
            "model evaluation", "documentation",
        ],
        "gold_answer": (
            "The model is a general-purpose AI model and, because its cumulative "
            "training compute exceeds 10^25 FLOPs, it is presumed under Article 51 "
            "to have systemic risk. The provider must meet the baseline GPAI "
            "obligations in Article 53 (technical documentation, information for "
            "downstream providers, a copyright policy and a training-content "
            "summary) and the additional systemic-risk obligations in Article 55 "
            "(model evaluation and adversarial testing, systemic-risk assessment "
            "and mitigation, incident tracking and cybersecurity)."
        ),
        "category": "medtech_gpai",
        "graphrag_theme": "drug discovery / molecule generation foundation model (GPAI in pharma; BioASQ drug-target)",
        "reasoning_level": "L3",
        "notes": "",
    },
    {
        "id": "grb_15",
        "question": (
            "If a hospital fine-tunes an open-weight medical language model, when "
            "does it become a provider under the EU AI Act?"
        ),
        "expected_refs": ["Article 25"],
        "expected_keywords": [
            "substantial modification", "new provider", "fine-tune",
            "one-third", "obligations",
        ],
        "gold_answer": (
            "Under Article 25 a party that makes a substantial modification to an "
            "AI system, or puts its own name or trademark on a high-risk system, "
            "becomes the provider and takes on the provider obligations. For a "
            "general-purpose model the Commission's guidance treats a fine-tune "
            "that adds more than one third of the original training compute as "
            "making the modifier a new provider for the resulting model."
        ),
        "category": "medtech_role_ambiguity",
        "graphrag_theme": "clinical LLM fine-tune / value chain (open-weight medical models)",
        "reasoning_level": "L3",
        "notes": "",
    },
    {
        "id": "grb_16",
        "question": (
            "What transparency obligation applies to AI-generated synthetic "
            "medical images used to augment a training dataset?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "synthetic", "artificially generated", "marked", "machine-readable",
            "transparency",
        ],
        "gold_answer": (
            "Article 50(2) requires providers of AI systems that generate "
            "synthetic image, audio, video or text content to mark the outputs in "
            "a machine-readable format and make them detectable as artificially "
            "generated or manipulated. Synthetic medical images produced for "
            "data augmentation therefore have to be labelled as AI-generated."
        ),
        "category": "medtech_transparency",
        "graphrag_theme": "synthetic-content / data augmentation (GenAI in medical imaging)",
        "reasoning_level": "L3",
        "notes": "",
    },
    {
        "id": "grb_17",
        "question": (
            "Classify the EU AI Act risk tier of an AI ambient scribe that only "
            "transcribes doctor-patient consultations and performs no diagnosis "
            "or decision-making."
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "limited risk", "transparency", "transcription", "not high-risk",
            "Annex III",
        ],
        "gold_answer": (
            "A pure transcription tool with no diagnostic or decision function is "
            "not listed in Annex III and is not a medical-device safety component, "
            "so it is not high-risk. It is a limited-risk system whose operative "
            "obligation is the Article 50 transparency duty to make clear that "
            "people are interacting with, or content is produced by, an AI system."
        ),
        "category": "medtech_risk_classification",
        "graphrag_theme": "ambient clinical documentation / scribe (EHR documentation)",
        "reasoning_level": "L3",
        "notes": "limited-risk boundary; established repo verdict is Article 50, NOT Annex III",
    },
    {
        "id": "grb_18",
        "question": (
            "Classify the EU AI Act risk tier of a consumer wellness chatbot that "
            "gives general lifestyle tips and makes no medical claims."
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "minimal risk", "limited risk", "transparency", "not high-risk",
            "wellness",
        ],
        "gold_answer": (
            "A general consumer-wellness chatbot that makes no medical claims is "
            "neither prohibited nor high-risk under Annex III; it falls outside "
            "the high-risk medical categories. Its only specific obligation is the "
            "Article 50 transparency duty to inform users they are interacting "
            "with an AI system; otherwise it is minimal-risk."
        ),
        "category": "medtech_risk_classification",
        "graphrag_theme": "consumer wellness chatbot (minimal-risk boundary)",
        "reasoning_level": "L3",
        "notes": "minimal/limited boundary",
    },
    {
        "id": "grb_19",
        "question": (
            "Is an AI system used for biometric patient identification at "
            "hospital check-in high-risk under the EU AI Act?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "biometric", "remote biometric identification", "verification",
            "Annex III", "high-risk",
        ],
        "gold_answer": (
            "It depends on the mode. Annex III point 1(a) makes remote biometric "
            "identification systems high-risk, but it expressly excludes biometric "
            "verification whose sole purpose is to confirm a person is who they "
            "claim to be. One-to-one check-in verification is therefore outside "
            "the high-risk category, while one-to-many identification of patients "
            "would be high-risk under Article 6(2)."
        ),
        "category": "medtech_borderline_classification",
        "graphrag_theme": "biometric patient identification (EU AI Act Annex III §1(a))",
        "reasoning_level": "L3",
        "notes": "verification-vs-identification carve-out",
    },
    # ── L4 — Generation / interpretive synthesis ────────────────────────────
    {
        "id": "grb_20",
        "question": (
            "An AI tool recommends oncology treatment regimens from clinical "
            "guidelines. What EU AI Act obligations does its provider face across "
            "the lifecycle?"
        ),
        "expected_refs": ["Article 6", "Article 9", "Article 43", "Annex III"],
        "expected_keywords": [
            "high-risk", "risk management", "conformity assessment",
            "post-market monitoring", "human oversight", "data governance",
        ],
        "gold_answer": (
            "A treatment-recommendation system is high-risk, either as a "
            "medical-device safety component under Article 6(1) and Annex I or "
            "under the Annex III healthcare categories. Across the lifecycle the "
            "provider must run a risk-management system under Article 9 with data "
            "governance, technical documentation, logging, transparency and human "
            "oversight, pass the Article 43 conformity assessment, and operate "
            "post-market monitoring after deployment."
        ),
        "category": "medtech_provider_obligations",
        "graphrag_theme": "oncology treatment recommendation (GraphRAG-Bench medical / NCCN guidelines, core)",
        "reasoning_level": "L4",
        "notes": "",
    },
    {
        "id": "grb_21",
        "question": (
            "How does the EU AI Act interact with the Medical Device Regulation "
            "for AI medical-device software — which conformity route and timeline "
            "applies?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I"],
        "expected_keywords": [
            "medical device", "MDR", "integrated", "conformity assessment",
            "notified body", "transition",
        ],
        "gold_answer": (
            "AI software that is a medical device or its safety component is "
            "high-risk under Article 6(1) because the Medical Device Regulation "
            "sits in Annex I. Under Article 43(3) the AI Act requirements are "
            "assessed through the single, integrated MDR notified-body conformity "
            "procedure rather than a separate AI Act assessment, and the high-risk "
            "obligations apply on the timeline set for Annex I products."
        ),
        "category": "medtech_cross_framework",
        "graphrag_theme": "SaMD / MDR interplay (medical-device software classification)",
        "reasoning_level": "L4",
        "notes": "cross-framework",
    },
    {
        "id": "grb_22",
        "question": (
            "What does the EU AI Act require for an AI system used for risk "
            "assessment and pricing in health insurance?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "high-risk", "Annex III", "risk assessment", "pricing",
            "health insurance", "essential services",
        ],
        "gold_answer": (
            "Annex III point 5(c) classifies AI used for risk assessment and "
            "pricing in relation to natural persons in the case of life and health "
            "insurance as high-risk under Article 6(2). The provider and deployer "
            "must therefore meet the Chapter III high-risk obligations, including "
            "data governance, human oversight and, for the deployer, a "
            "fundamental-rights impact assessment."
        ),
        "category": "medtech_high_risk_classification",
        "graphrag_theme": "health-insurance risk / pricing (EU AI Act Annex III §5(c))",
        "reasoning_level": "L4",
        "notes": "",
    },
    {
        "id": "grb_23",
        "question": (
            "A clinical-trial sponsor uses AI to select and recruit eligible "
            "patients. Is this automatically high-risk under the EU AI Act?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "not automatically", "Annex III", "eligibility", "healthcare services",
            "research", "scope",
        ],
        "gold_answer": (
            "Not automatically. Annex III point 5 covers AI that decides "
            "eligibility for essential healthcare services and benefits or that "
            "performs emergency triage, not research recruitment as such, so "
            "trial-participant selection is not high-risk merely by being clinical "
            "AI. It would become high-risk only if it determines access to "
            "healthcare services, and pure research use may fall under the "
            "Article 2 research carve-out."
        ),
        "category": "medtech_borderline_classification",
        "graphrag_theme": "clinical-trial patient recruitment / selection (PubMedQA trial literature)",
        "reasoning_level": "L4",
        "notes": "tricky — not unconditionally Annex III",
    },
    {
        "id": "grb_24",
        "question": (
            "What penalties can be imposed on a medical-AI provider that places a "
            "non-conformant high-risk system on the market?"
        ),
        "expected_refs": ["Article 99"],
        "expected_keywords": [
            "penalties", "fines", "15 000 000", "3 %", "high-risk",
            "turnover",
        ],
        "gold_answer": (
            "Article 99 sets the penalty ceilings. Non-compliance with the "
            "high-risk obligations is subject under Article 99(4) to fines of up "
            "to EUR 15 000 000 or 3 % of total worldwide annual turnover, "
            "whichever is higher, while breaching the Article 5 prohibitions "
            "carries the higher ceiling of EUR 35 000 000 or 7 % under "
            "Article 99(3). Fines must take the interests of SMEs into account."
        ),
        "category": "medtech_enforcement",
        "graphrag_theme": "penalties / enforcement for medical AI (MedMCQA clinical-knowledge framing)",
        "reasoning_level": "L4",
        "notes": "",
    },
]

# No separate no-ground-truth group — every row is scored.
NO_GROUND_TRUTH: list[dict] = []
