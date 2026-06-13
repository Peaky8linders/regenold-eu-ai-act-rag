"""Fresh MedTech / life-sciences eval set V3 (R120).

A third, fully-distinct probe set for the domain Regenold actually serves.
This dataset tests the intersection of the EU AI Act and Medical Device Regulation (MDR),
In Vitro Diagnostic Regulation (IVDR), General-Purpose AI (GPAI), and clinical use.
"""
from __future__ import annotations

MEDTECH_SCENARIOS_V3: list[dict] = [
    {
        "id": "mv3_01",
        "question": (
            "We are developing an AI-driven robotic surgical assistant designed to execute "
            "autonomous tissue suturing under surgeon supervision. The host robotic platform is a "
            "Class III medical device requiring a notified body conformity assessment under the MDR. "
            "How does the AI Act classify this AI module, and which conformity route applies?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I"],
        "expected_keywords": [
            "high-risk", "safety component", "MDR", "notified body", "conformity assessment"
        ],
        "category": "surgical_robotics_conformity",
    },
    {
        "id": "mv3_02",
        "question": (
            "Our digital health platform uses a machine learning algorithm to analyze smartwatch "
            "ECG data for real-time arrhythmia detection, and is CE-marked as a Class IIb device "
            "under the MDR. Under which AI Act risk tier does this model fall, and what conformity "
            "assessment is required?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I"],
        "expected_keywords": [
            "high-risk", "safety component", "notified body", "conformity assessment", "Annex I"
        ],
        "category": "ecg_arrhythmia_samd",
    },
    {
        "id": "mv3_03",
        "question": (
            "We build an AI tool that scans electronic health records to automatically match "
            "patients to active clinical trials based on inclusion criteria. It does not perform "
            "any diagnosis or treatment recommendations. Does this qualify as high-risk, and does "
            "the scientific research exemption apply here?"
        ),
        "expected_refs": ["Article 2", "Article 6", "Annex III"],
        "expected_keywords": [
            "not high-risk", "scientific research", "does not apply", "Article 2", "placing on the market"
        ],
        "category": "clinical_trial_matching",
    },
    {
        "id": "mv3_04",
        "question": (
            "Our system is an AI-powered insulin delivery pump that dynamically calculates "
            "insulin doses based on continuous glucose monitor readings. The pump is a Class III "
            "device under the MDR. How does the AI Act classify it, and does it require a "
            "separate CE marking under the AI Act?"
        ),
        "expected_refs": ["Article 6", "Article 48", "Annex I"],
        "expected_keywords": [
            "high-risk", "safety component", "CE marking", "single", "not separate"
        ],
        "category": "combination_insulin_pump",
    },
    {
        "id": "mv3_05",
        "question": (
            "We are launching a software-as-a-medical-device (SaMD) that analyzes digital "
            "pathology slides of biopsy tissue to assist pathologists in grading breast cancer. "
            "It requires a Class III certificate under the IVDR. How is this AI categorized "
            "under the AI Act, and what conformity route applies?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I"],
        "expected_keywords": [
            "high-risk", "IVDR", "safety component", "notified body", "conformity assessment"
        ],
        "category": "pathology_samd_oncology",
    },
    {
        "id": "mv3_06",
        "question": (
            "A metropolitan hospital deploys a third-party CE-marked AI software to prioritize "
            "radiology scans in the emergency department. As a healthcare organization deploying "
            "this high-risk AI system, what are our legal obligations regarding fundamental "
            "rights and human oversight?"
        ),
        "expected_refs": ["Article 26", "Article 27"],
        "expected_keywords": [
            "deployer", "human oversight", "fundamental rights impact assessment", "Article 26", "Article 27"
        ],
        "category": "hospital_deployer_obligations",
    },
    {
        "id": "mv3_07",
        "question": (
            "We sell an AI scribe that listens to physician-patient consultations in the "
            "examination room and auto-generates structured clinical notes. It does not recommend "
            "diagnoses or dosages. What classification and transparency requirements apply to this tool?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "not high-risk", "transparency", "Article 50", "inform", "interact"
        ],
        "category": "scribe_transparency_duty",
    },
    {
        "id": "mv3_08",
        "question": (
            "We developed a large biology foundation model trained on 10^26 FLOPs of genomic "
            "and proteomic sequence data to predict protein folding and design drug candidates. "
            "What obligations apply to us under the general-purpose AI (GPAI) regime?"
        ),
        "expected_refs": ["Article 51", "Article 53", "Article 55"],
        "expected_keywords": [
            "general-purpose", "systemic risk", "10^25", "FLOPs", "Article 55", "adversarial testing", "model evaluation"
        ],
        "category": "gpai_biology_foundation",
    },
    {
        "id": "mv3_09",
        "question": (
            "Our wellness app uses machine learning to track sleep quality, calorie intake, "
            "and heart rate to provide lifestyle recommendations. It does not make any "
            "diagnostic or therapeutic claims. How is this classified in the AI Act risk pyramid?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "minimal", "not high-risk", "wellness", "Annex III", "not listed"
        ],
        "category": "wellness_app_boundary",
    },
    {
        "id": "mv3_10",
        "question": (
            "We act as the EU importer for a US-developed high-risk medical AI system designed "
            "for oncology treatment planning. What are our key verification and compliance "
            "obligations before placing this system on the Union market?"
        ),
        "expected_refs": ["Article 23"],
        "expected_keywords": [
            "importer", "CE marking", "conformity assessment", "technical documentation", "EU declaration of conformity", "Article 23"
        ],
        "category": "importer_medtech_obligations",
    },
    {
        "id": "mv3_11",
        "question": (
            "As a commercial distributor reselling an AI-powered diagnostic software for lung "
            "nodule detection to European hospitals, what compliance checks are we mandated to "
            "perform before making the system available?"
        ),
        "expected_refs": ["Article 24"],
        "expected_keywords": [
            "distributor", "CE marking", "instructions for use", "before making it available", "Article 24"
        ],
        "category": "distributor_medtech_obligations",
    },
    {
        "id": "mv3_12",
        "question": (
            "A Canadian startup has developed an AI software for clinical decision support. "
            "They want to place it on the EU market but have no physical establishment in "
            "the Union. What must they do before placing the AI system on the market?"
        ),
        "expected_refs": ["Article 22"],
        "expected_keywords": [
            "authorised representative", "established", "mandate", "before", "Article 22"
        ],
        "category": "authorised_rep_obligation",
    },
    {
        "id": "mv3_13",
        "question": (
            "A hospital that has deployed a high-risk cardiac monitoring AI retrains the "
            "neural network on its local patient population, significantly modifying its "
            "clinical performance and intended use. Does this trigger new conformity assessment "
            "requirements, and who is responsible?"
        ),
        "expected_refs": ["Article 25", "Article 43"],
        "expected_keywords": [
            "substantial modification", "new provider", "Article 25", "conformity assessment", "Article 43"
        ],
        "category": "substantial_modification_clinical",
    },
    {
        "id": "mv3_14",
        "question": (
            "We are training a high-risk medical diagnosis AI system and need to process health "
            "and genetic datasets to detect and correct demographic bias. Under what conditions "
            "does the AI Act permit processing of special categories of personal data?"
        ),
        "expected_refs": ["Article 10"],
        "expected_keywords": [
            "data governance", "bias", "special categories", "GDPR", "Article 10", "safeguards"
        ],
        "category": "data_governance_bias",
    },
    {
        "id": "mv3_15",
        "question": (
            "We want to use an AI model in a psychiatric clinic that infers patients' emotional "
            "states from facial micro-expressions to assist in diagnosing clinical depression. "
            "How does the AI Act regulate this emotion recognition system?"
        ),
        "expected_refs": ["Article 5", "Annex III", "Article 50"],
        "expected_keywords": [
            "emotion recognition", "workplace", "not categorically prohibited", "clinical", "Annex III", "Article 50"
        ],
        "category": "emotion_recognition_clinical",
    },
    {
        "id": "mv3_16",
        "question": (
            "Our high-risk clinical decision support AI is already CE-marked and active in "
            "hospitals. What are our post-market monitoring and serious-incident reporting "
            "obligations under the AI Act?"
        ),
        "expected_refs": ["Article 72", "Article 73"],
        "expected_keywords": [
            "post-market monitoring", "Article 72", "serious incident", "Article 73", "report", "market surveillance"
        ],
        "category": "postmarket_incident_reporting",
    },
    {
        "id": "mv3_17",
        "question": (
            "What are the maximum financial penalties that a medical device company faces "
            "if they place a prohibited AI practice on the EU market, versus breaching "
            "their obligations for a high-risk AI system?"
        ),
        "expected_refs": ["Article 99"],
        "expected_keywords": [
            "Article 99(3)", "35", "7%", "Article 99(4)", "15", "3%", "worldwide annual turnover"
        ],
        "category": "financial_penalties",
    },
    {
        "id": "mv3_18",
        "question": (
            "As a provider of high-risk medical software, what quality management system (QMS) "
            "requirements are we required to document and maintain under the AI Act?"
        ),
        "expected_refs": ["Article 17"],
        "expected_keywords": [
            "quality management system", "Article 17", "procedures", "documentation", "systematic"
        ],
        "category": "quality_management_system",
    },
]
