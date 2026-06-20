"""R136 — fresh MedTech / life-sciences EU AI Act probe set (24 rows).

A brand-new, distinct evaluation surface authored for the R136 round to
measure the live wire on realistic medical-device, hospital-deployer,
pharma-GPAI, and life-sciences AI scenarios. IDs use the ``ls_`` prefix and
are disjoint from every existing eval set (``grb_*`` / ``gt_*`` / ``med_*`` /
``mt_*`` / ``mv*``).

Reference grounding is the verbatim EU AI Act (Regulation 2024/1689): the
Article 6(1) + Annex I medical-device safety-component route, the Annex III(5)
healthcare use cases (5(a) eligibility, 5(c) insurance pricing, 5(d) emergency
triage), Article 5(1)(f) workplace-emotion + 5(1)(g) biometric-categorisation
prohibitions, the Article 2(6) scientific-R&D exclusion, the Article 51/53/55
GPAI regime, Article 10 data governance, Article 14 human oversight, Article
43 conformity assessment, and Articles 22/23/24/25/26/27 across the value
chain.

Schema (mirrors ``scenarios_medtech_graphrag_v124.GROUND_TRUTH``):

    {"id", "question", "expected_refs", "expected_keywords", "gold_answer",
     "category", "reasoning_level", "notes"}

Run (local deterministic / live):
    python -m evals.regenold.run_medtech_lifesci_r136 --local --label X
    python -m evals.regenold.run_medtech_lifesci_r136 --endpoint <live> --label X
then judge with:
    python -m evals.judge.runner --bench-sidecar <sidecar> --label X
"""
from __future__ import annotations

GROUND_TRUTH: list[dict] = [
    # ── L1 — classification / fact retrieval ────────────────────────────────
    {
        "id": "ls_01",
        "question": (
            "Is AI software that flags early sepsis risk from ICU vital-sign "
            "streams a high-risk AI system under the EU AI Act?"
        ),
        "expected_refs": ["Article 6", "Annex I", "Article 43"],
        "expected_keywords": [
            "high-risk", "safety component", "medical device", "Annex I",
            "conformity assessment",
        ],
        "gold_answer": (
            "Yes. Under Article 6(1) an AI system that is a medical device, or a "
            "safety component of one, covered by the Annex I Union harmonisation "
            "legislation (the Medical Device Regulation) and required to undergo "
            "third-party conformity assessment is high-risk. A sepsis early-warning "
            "system meeting that description must satisfy the Chapter III "
            "requirements and pass the Article 43 conformity assessment integrated "
            "with the medical-device notified-body route."
        ),
        "category": "medtech_high_risk_classification",
        "reasoning_level": "L1",
        "notes": "",
    },
    {
        "id": "ls_02",
        "question": (
            "What is a 'safety component' for the purposes of the EU AI Act?"
        ),
        "expected_refs": ["Article 3"],
        "expected_keywords": ["safety", "component", "fails", "endanger", "health"],
        "gold_answer": (
            "Article 3(14) defines a safety component as a component of a product "
            "or system which fulfils a safety function for that product or system, "
            "or the failure or malfunctioning of which endangers the health and "
            "safety of persons or property."
        ),
        "category": "definition",
        "reasoning_level": "L1",
        "notes": "Sub-point gold: Article 3.14",
    },
    {
        "id": "ls_03",
        "question": (
            "A pharmaceutical company uses an AI model solely for internal "
            "pre-clinical drug-target discovery and never places it on the market. "
            "Does the EU AI Act apply to that model?"
        ),
        "expected_refs": ["Article 2"],
        "expected_keywords": [
            "scientific research", "excludes", "market", "research and development",
        ],
        "gold_answer": (
            "No. Article 2(6) excludes AI systems and models developed and used "
            "solely for scientific research and development. The model is outside "
            "the Act while used only for pre-clinical research and not placed on "
            "the market or put into service; the obligations attach on market "
            "placement according to its risk classification."
        ),
        "category": "scope_exclusion",
        "reasoning_level": "L1",
        "notes": "Sub-point gold: Article 2.6",
    },
    {
        "id": "ls_04",
        "question": (
            "An AI system on a hospital website answers general patient questions "
            "about opening hours and departments, with no diagnosis. What "
            "transparency obligation applies and is it high-risk?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "limited risk", "not high-risk", "interacting", "AI system", "provider",
        ],
        "gold_answer": (
            "It is limited-risk, not high-risk: a general patient-information "
            "chatbot performs no Annex III use case and is not a safety component, "
            "so Article 13 high-risk transparency does not apply. Article 50(1) "
            "alone governs: the provider must ensure each user is informed they are "
            "interacting with an AI system."
        ),
        "category": "transparency_limited_risk",
        "reasoning_level": "L1",
        "notes": "Sub-point gold: Article 50.1",
    },
    # ── L2 — multi-hop / value chain ────────────────────────────────────────
    {
        "id": "ls_05",
        "question": (
            "A public hospital deploys a third-party CE-marked AI that classifies "
            "diabetic-retinopathy severity from retinal scans. What are the "
            "hospital's obligations as the deployer?"
        ),
        "expected_refs": ["Article 26", "Article 27"],
        "expected_keywords": [
            "deployer", "human oversight", "instructions for use",
            "fundamental rights impact assessment", "monitor",
        ],
        "gold_answer": (
            "As a deployer of a high-risk AI system the hospital must, under "
            "Article 26, use the system in accordance with the provider's "
            "instructions, assign competent human oversight, monitor its operation, "
            "and keep the automatically generated logs. As a public body it must "
            "also carry out a fundamental rights impact assessment under Article 27 "
            "before first use."
        ),
        "category": "deployer_obligation",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "ls_06",
        "question": (
            "A US medtech firm with no EU establishment wants to make its "
            "tumour-segmentation AI available on the EU market. What does the AI "
            "Act require of it before doing so?"
        ),
        "expected_refs": ["Article 22", "Article 16"],
        "expected_keywords": [
            "authorised representative", "provider", "established in the Union",
            "written mandate",
        ],
        "gold_answer": (
            "Before placing the high-risk system on the Union market the non-EU "
            "provider must, under Article 22, appoint by written mandate an "
            "authorised representative established in the Union to verify and hold "
            "the technical documentation and cooperate with authorities. The "
            "provider remains bound by the full Article 16 provider obligations."
        ),
        "category": "extraterritorial_role",
        "reasoning_level": "L2",
        "notes": "Sub-point gold: Article 22",
    },
    {
        "id": "ls_07",
        "question": (
            "A biotech firm fine-tunes an open-weight general-purpose AI model on "
            "proprietary trial data, adding about 1x10^24 FLOPs of compute. Does it "
            "become a provider, and do systemic-risk obligations apply?"
        ),
        "expected_refs": ["Article 25", "Article 51", "Article 53"],
        "expected_keywords": [
            "one-third", "new provider", "10^25 FLOPs", "systemic risk",
            "general-purpose AI model",
        ],
        "gold_answer": (
            "Under Article 25 a downstream modifier becomes a new provider, "
            "assuming the GPAI provider duties, where the additional training "
            "compute exceeds one third of the base model's compute. Whether the "
            "Article 55 systemic-risk obligations apply turns on the Article 51 "
            "threshold, presumed at 10^25 FLOPs of cumulative training compute; "
            "1x10^24 FLOPs of fine-tune compute falls well below it, leaving the "
            "baseline Article 53 obligations."
        ),
        "category": "gpai_value_chain",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "ls_08",
        "question": (
            "A wellbeing app infers a person's likely ethnicity and religion from "
            "facial and retinal images to tailor health content. Is this permitted "
            "under the EU AI Act?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": [
            "prohibited", "biometric categorisation", "race", "ethnicity",
            "religious", "sensitive",
        ],
        "gold_answer": (
            "No. Article 5(1)(g) prohibits biometric categorisation systems that "
            "individually categorise natural persons based on their biometric data "
            "to deduce or infer sensitive attributes on a closed list, which "
            "includes race, ethnicity, and religious or philosophical beliefs. "
            "Inferring ethnicity and religion from facial and retinal images falls "
            "squarely within that ban."
        ),
        "category": "prohibited_biometric",
        "reasoning_level": "L2",
        "notes": "Sub-point gold: Article 5.1.g",
    },
    # ── L3 — boundary / decision-edge ───────────────────────────────────────
    {
        "id": "ls_09",
        "question": (
            "A hospital wants AI wristbands that monitor nurses' emotional and "
            "stress levels during shifts to reduce error rates. Is this allowed?"
        ),
        "expected_refs": ["Article 5"],
        "expected_keywords": [
            "prohibited", "emotion", "workplace", "medical", "safety",
        ],
        "gold_answer": (
            "No, as described. Article 5(1)(f) prohibits AI systems that infer the "
            "emotions of natural persons in the workplace. The only carve-out is "
            "for systems placed on the market strictly for medical or safety "
            "reasons, which must be the primary purpose; deploying it to improve "
            "error rates as a workforce-efficiency tool does not qualify."
        ),
        "category": "prohibited_emotion_carveout",
        "reasoning_level": "L3",
        "notes": "Sub-point gold: Article 5.1.f",
    },
    {
        "id": "ls_10",
        "question": (
            "An AI triages incoming emergency-department patients by acuity and "
            "dispatches ambulances accordingly. Is it high-risk, and on what "
            "basis?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "high-risk", "emergency", "triage", "dispatch", "first response",
        ],
        "gold_answer": (
            "Yes. Annex III point 5(d) lists AI intended for the triage of "
            "patients in need of emergency healthcare, or the dispatching or "
            "prioritising of emergency first-response services, as a high-risk use "
            "case, so under Article 6(2) the system is high-risk and the full "
            "Chapter III obligations apply."
        ),
        "category": "annex_iii_triage",
        "reasoning_level": "L3",
        "notes": "Sub-point gold: Annex III.5.d",
    },
    {
        "id": "ls_11",
        "question": (
            "An AI matches patients to experimental clinical trials from their "
            "electronic health records. Is this high-risk under Annex III(5)(d) "
            "emergency triage?"
        ),
        "expected_refs": ["Annex III", "Article 2"],
        "expected_keywords": [
            "not", "emergency", "triage", "clinical trial", "scientific research",
        ],
        "gold_answer": (
            "No. Annex III point 5(d) is narrow, covering only emergency patient "
            "triage and the dispatch of emergency first-response services; clinical-"
            "trial matching is not that use case and is not otherwise listed in "
            "Annex III. Where the matching is part of scientific research and "
            "development it falls under the Article 2(6) exclusion, and otherwise "
            "outside the high-risk regime unless it is a regulated medical device."
        ),
        "category": "annex_iii_boundary",
        "reasoning_level": "L3",
        "notes": "Distinguishes Annex III.5.d emergency triage from trial selection",
    },
    {
        "id": "ls_12",
        "question": (
            "A health insurer uses AI to set individual premiums and assess "
            "eligibility for cover from applicants' health and genetic data. Is "
            "this high-risk?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "high-risk", "life", "health insurance", "risk assessment", "pricing",
        ],
        "gold_answer": (
            "Yes. Annex III point 5(c) lists AI intended for risk assessment and "
            "pricing in relation to natural persons in the case of life and health "
            "insurance as a high-risk use case, so the system is high-risk under "
            "Article 6(2) and must meet the Chapter III obligations."
        ),
        "category": "annex_iii_insurance",
        "reasoning_level": "L3",
        "notes": "Sub-point gold: Annex III.5.c",
    },
    {
        "id": "ls_13",
        "question": (
            "An AI selects which patients are eligible for a publicly funded "
            "organ-transplant programme. Which high-risk use case does this engage?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "high-risk", "eligibility", "essential", "public", "healthcare",
        ],
        "gold_answer": (
            "Annex III point 5(a) covers AI intended to evaluate eligibility for "
            "essential public assistance benefits and services, including "
            "healthcare services, so an eligibility tool for a publicly funded "
            "transplant programme is high-risk under Article 6(2) and carries the "
            "Chapter III obligations."
        ),
        "category": "annex_iii_eligibility",
        "reasoning_level": "L3",
        "notes": "Sub-point gold: Annex III.5.a",
    },
    # ── L4 — synthesis / generation ─────────────────────────────────────────
    {
        "id": "ls_14",
        "question": (
            "An AI safety component controls instrument motion in real time during "
            "robotic surgery. Beyond being high-risk, what specific AI Act "
            "obligations are engaged?"
        ),
        "expected_refs": ["Article 6", "Annex I", "Article 14", "Article 72"],
        "expected_keywords": [
            "high-risk", "human oversight", "post-market", "notified body",
            "conformity assessment",
        ],
        "gold_answer": (
            "As a safety component of a medical device under Annex I it is "
            "high-risk under Article 6(1) and undergoes notified-body conformity "
            "assessment under Article 43. Real-time control of the surgical loop "
            "engages the Article 14 human-oversight design requirements, and the "
            "provider must operate post-market monitoring under Article 72 and "
            "report serious incidents under Article 73."
        ),
        "category": "robotic_surgery_synthesis",
        "reasoning_level": "L4",
        "notes": "",
    },
    {
        "id": "ls_15",
        "question": (
            "What technical documentation must a provider of a high-risk diagnostic "
            "AI prepare, and does it have to specify the hardware the system runs "
            "on?"
        ),
        "expected_refs": ["Article 11", "Annex IV"],
        "expected_keywords": [
            "technical documentation", "Annex IV", "hardware", "computational",
        ],
        "gold_answer": (
            "Under Article 11 the provider must draw up the technical documentation "
            "set out in Annex IV before placing the system on the market. Hardware "
            "is in scope: Annex IV point 1(e) requires a description of the hardware "
            "on which the system is intended to run, and point 2(c) requires the "
            "computational resources used to develop, train, test, and validate it."
        ),
        "category": "technical_documentation",
        "reasoning_level": "L4",
        "notes": "Sub-point gold: Annex IV.1.e, Annex IV.2.c",
    },
    {
        "id": "ls_16",
        "question": (
            "A life-sciences lab releases an open-weight general-purpose AI model "
            "for protein folding trained at 3x10^25 FLOPs. What obligations apply, "
            "and does the open-weight status change them?"
        ),
        "expected_refs": ["Article 55", "Article 53", "Article 51"],
        "expected_keywords": [
            "systemic risk", "10^25 FLOPs", "model evaluation", "adversarial",
            "open", "training-data summary",
        ],
        "gold_answer": (
            "At 3x10^25 FLOPs the model crosses the Article 51 systemic-risk "
            "threshold, so the Article 55 obligations apply: model evaluation and "
            "adversarial testing, systemic-risk assessment and mitigation, serious-"
            "incident tracking, and cybersecurity protection. The open-weight "
            "release relieves some Article 53 documentation duties but not the "
            "copyright policy, the training-data summary, or any Article 55 "
            "systemic-risk obligation."
        ),
        "category": "gpai_systemic",
        "reasoning_level": "L4",
        "notes": "",
    },
    {
        "id": "ls_17",
        "question": (
            "A continuous glucose monitor's AI insulin-dosing recommendation is "
            "retrained weekly on new patient data. Does each retraining trigger a "
            "fresh conformity assessment?"
        ),
        "expected_refs": ["Article 43", "Article 6"],
        "expected_keywords": [
            "substantial modification", "conformity assessment",
            "pre-determined", "change", "high-risk",
        ],
        "gold_answer": (
            "Under Article 43(4) a substantial modification of a high-risk system "
            "requires a fresh conformity assessment, but changes the provider has "
            "pre-determined and documented in the initial assessment, including a "
            "pre-defined plan for continued learning, are not substantial "
            "modifications. Weekly retraining within that pre-approved change-"
            "control plan does not trigger a new assessment; a change outside it "
            "does."
        ),
        "category": "substantial_modification",
        "reasoning_level": "L4",
        "notes": "",
    },
    {
        "id": "ls_18",
        "question": (
            "How may a provider process patients' genetic and health data "
            "specifically to detect and correct demographic bias in a diagnostic "
            "AI?"
        ),
        "expected_refs": ["Article 10"],
        "expected_keywords": [
            "special categories", "bias detection", "data governance",
            "strictly necessary", "safeguards",
        ],
        "gold_answer": (
            "Article 10(5) permits providers of high-risk AI systems to process "
            "special categories of personal data, including health and genetic "
            "data, to the extent strictly necessary to ensure bias detection and "
            "correction, subject to appropriate safeguards such as pseudonymisation, "
            "access controls, and a prohibition on transmission or sharing of that "
            "data."
        ),
        "category": "data_governance_bias",
        "reasoning_level": "L4",
        "notes": "Sub-point gold: Article 10.5",
    },
    {
        "id": "ls_19",
        "question": (
            "An EU medical-device distributor makes a high-risk diagnostic AI "
            "available on the market. What must the distributor verify before doing "
            "so?"
        ),
        "expected_refs": ["Article 24"],
        "expected_keywords": [
            "distributor", "CE marking", "instructions", "conformity",
            "documentation",
        ],
        "gold_answer": (
            "Under Article 24 the distributor must verify before making the "
            "high-risk system available that it bears the CE marking, is "
            "accompanied by the EU declaration of conformity and instructions for "
            "use, and that the provider and importer have met their obligations, "
            "and must not place it on the market if it has reason to consider it "
            "non-conforming."
        ),
        "category": "distributor_obligation",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "ls_20",
        "question": (
            "A non-EU manufacturer's high-risk diagnostic AI is imported into the "
            "EU by a medical wholesaler. What are the importer's obligations?"
        ),
        "expected_refs": ["Article 23"],
        "expected_keywords": [
            "importer", "conformity assessment", "CE marking",
            "technical documentation", "authorised representative",
        ],
        "gold_answer": (
            "Under Article 23 the importer must verify before placing the system on "
            "the market that the provider has carried out the conformity "
            "assessment, drawn up the technical documentation, affixed the CE "
            "marking, and appointed an authorised representative, and must indicate "
            "its details on the system and ensure storage and transport do not "
            "jeopardise compliance."
        ),
        "category": "importer_obligation",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "ls_21",
        "question": (
            "What automatic record-keeping must a high-risk medical AI provide, and "
            "how long must the deploying hospital keep those logs?"
        ),
        "expected_refs": ["Article 12", "Article 26"],
        "expected_keywords": [
            "logs", "automatically", "traceability", "six months", "retain",
        ],
        "gold_answer": (
            "Article 12 requires the high-risk system to automatically record "
            "events (logs) over its lifetime to ensure a level of traceability "
            "appropriate to its purpose. Under Article 26(6) the deployer must keep "
            "the logs automatically generated, to the extent under its control, for "
            "a period appropriate to the intended purpose of at least six months, "
            "unless other Union or national law provides otherwise."
        ),
        "category": "record_keeping",
        "reasoning_level": "L2",
        "notes": "",
    },
    {
        "id": "ls_22",
        "question": (
            "A serious incident involving patient harm occurs with a deployed "
            "high-risk diagnostic AI. Who must report what, and within what time?"
        ),
        "expected_refs": ["Article 73", "Article 26", "Article 72"],
        "expected_keywords": [
            "serious incident", "market surveillance", "report", "deployer",
            "post-market",
        ],
        "gold_answer": (
            "Under Article 73 the provider must report a serious incident to the "
            "market-surveillance authority of the Member State concerned "
            "immediately after establishing a causal link, and at the latest within "
            "set deadlines after becoming aware of it. The deployer must, under "
            "Article 26(5), inform the provider and the authority of a serious "
            "incident, all feeding the provider's Article 72 post-market monitoring "
            "system."
        ),
        "category": "incident_reporting",
        "reasoning_level": "L4",
        "notes": "",
    },
    {
        "id": "ls_23",
        "question": (
            "An AI scribe transcribes doctor-patient consultations into the medical "
            "record and does not diagnose or recommend treatment. Is it prohibited, "
            "high-risk, or limited-risk?"
        ),
        "expected_refs": ["Article 50", "Article 6"],
        "expected_keywords": [
            "not prohibited", "not", "Annex III", "limited", "safety component",
        ],
        "gold_answer": (
            "An AI scribe that only transcribes is neither prohibited under Article "
            "5 nor listed in Annex III, so it is not high-risk on those grounds. It "
            "is high-risk only if it is a safety component of a medical device under "
            "Article 6(1) and Annex I; otherwise it is limited-risk and the Article "
            "50 transparency duty to inform patients they are interacting with AI "
            "applies."
        ),
        "category": "transcription_boundary",
        "reasoning_level": "L3",
        "notes": "",
    },
    {
        "id": "ls_24",
        "question": (
            "Does AI software intended to detect diabetic retinopathy and that is a "
            "Class IIb medical device require a notified body, and how does the AI "
            "Act conformity assessment relate to the MDR one?"
        ),
        "expected_refs": ["Article 43", "Article 6", "Annex I"],
        "expected_keywords": [
            "notified body", "high-risk", "integrated", "Medical Device Regulation",
            "single",
        ],
        "gold_answer": (
            "Yes. As a Class IIb medical device it is high-risk under Article 6(1) "
            "and Annex I and requires a notified body. Under Article 43(3) the AI "
            "Act conformity assessment is carried out as part of the conformity "
            "assessment already required under the Medical Device Regulation, "
            "through the same notified body in a single integrated procedure rather "
            "than a separate AI Act assessment."
        ),
        "category": "conformity_assessment",
        "reasoning_level": "L4",
        "notes": "Sub-point gold: Article 43.3",
    },
]


def question_ids() -> list[str]:
    return [r["id"] for r in GROUND_TRUTH]
