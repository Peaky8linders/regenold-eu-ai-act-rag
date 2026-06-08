"""Fresh MedTech / life-sciences eval set (R109).

The domain Regenold actually serves. These 18 scenarios are DISTINCT from the
``med_01..07`` rows already in ``scenarios_graphrag_benchmark.py`` — they probe
the same real-world fact patterns (SaMD / IVD classification + conformity,
clinical decision support, deployer duties, GPAI on biomedical data, emotion /
biometric edges, the research carve-out, post-market + incident reporting,
substantial modification, penalties) with new wording so the engine cannot be
graded on memorised phrasing.

Each row's ``expected_refs`` are wire-form ("Article N" / "Annex R") and every
one resolves in ``app.data.article_existence.ARTICLE_EXISTENCE`` (validated by
``tests/test_medtech_lifesci_eval.py``). ``expected_keywords`` are the
substantive gold tokens a faithful answer should surface.

Run:
    # Local deterministic (TestClient, no wrapper):
    .venv\\Scripts\\python.exe -m evals.regenold.run_medtech --local --label r109-medtech-local --verbose
    # Live (Claude Max Stage-2 via the production endpoint — the eval rule):
    .venv\\Scripts\\python.exe -m evals.regenold.run_medtech \\
        --endpoint https://<railway>.up.railway.app/api/v1/regenold/eu-ai-act/ask \\
        --api-key $env:P2P_REGENOLD_API_KEY --label r109-medtech-live --verbose
"""
from __future__ import annotations

MEDTECH_SCENARIOS: list[dict] = [
    {
        "id": "mt_01",
        "question": (
            "We build the AI that controls insulin dosing inside an implantable "
            "pump that is a Class III medical device under the MDR. Is the AI "
            "high-risk, and which conformity-assessment route applies?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I"],
        "expected_keywords": [
            "high-risk", "safety component", "third-party conformity assessment",
            "Annex I", "MDR", "Article 43", "notified body",
        ],
        "category": "high_risk_medical_device",
    },
    {
        "id": "mt_02",
        "question": (
            "Our software-as-a-medical-device classifies skin lesions as benign "
            "or malignant from photos and is CE-marked Class IIa requiring a "
            "notified body. How does the AI Act classify it and which assessment "
            "applies?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I", "Annex VII"],
        "expected_keywords": [
            "safety component", "Annex I", "Medical Device Regulation",
            "third-party conformity assessment", "notified body", "high-risk",
        ],
        "category": "samd_classification",
    },
    {
        "id": "mt_03",
        "question": (
            "Our AI interprets results from an in-vitro diagnostic blood analyser "
            "regulated under the IVDR. Is it high-risk and how does the IVDR "
            "conformity assessment interact with the AI Act?"
        ),
        "expected_refs": ["Article 6", "Article 43", "Annex I"],
        "expected_keywords": [
            "in-vitro diagnostic", "IVDR", "Annex I", "safety component",
            "third-party conformity assessment", "high-risk",
        ],
        "category": "ivd_diagnostics",
    },
    {
        "id": "mt_04",
        "question": (
            "We supply a clinical decision support AI that recommends drug "
            "dosages to physicians who keep final prescribing authority. As the "
            "provider of a high-risk system, what human-oversight and "
            "transparency-to-deployer duties must we build in?"
        ),
        "expected_refs": ["Article 13", "Article 14", "Article 16"],
        "expected_keywords": [
            "human oversight", "transparency", "instructions for use",
            "provider", "high-risk",
        ],
        "category": "clinical_decision_support",
    },
    {
        "id": "mt_05",
        "question": (
            "A public hospital deploys a third-party CE-marked AI radiology "
            "triage system. Which obligations fall on the hospital as deployer "
            "rather than on the manufacturer?"
        ),
        "expected_refs": ["Article 26", "Article 27"],
        "expected_keywords": [
            "deployer", "Article 26", "human oversight", "instructions for use",
            "logs", "fundamental rights impact assessment", "Article 27",
        ],
        "category": "deployer_obligations",
    },
    {
        "id": "mt_06",
        "question": (
            "A digital-health startup fine-tunes an open-weights general-purpose "
            "model on clinical notes and ships it to other hospitals. When does "
            "the startup itself become a GPAI provider with Article 53 duties?"
        ),
        "expected_refs": ["Article 25", "Article 53"],
        "expected_keywords": [
            "one-third", "training compute", "new provider", "Article 25",
            "Article 53", "technical documentation", "training-data summary",
        ],
        "category": "gpai_value_chain",
    },
    {
        "id": "mt_07",
        "question": (
            "A wellness app infers a user's stress and mood from their voice "
            "during therapy-style chats. Is this emotion recognition prohibited, "
            "high-risk, or limited-risk?"
        ),
        "expected_refs": ["Article 5", "Annex III", "Article 50"],
        "expected_keywords": [
            "emotion recognition", "Article 5(1)(f)", "workplace",
            "not categorically prohibited", "Annex III", "Article 50", "inform",
        ],
        "category": "borderline_prohibition",
    },
    {
        "id": "mt_08",
        "question": (
            "A research consortium develops an AI model solely to study tumour "
            "genetics and never places it on the market. Does the EU AI Act "
            "apply to that model?"
        ),
        "expected_refs": ["Article 2"],
        "expected_keywords": [
            "Article 2", "scientific research and development", "sole purpose",
            "does not apply",
        ],
        "category": "research_exemption",
    },
    {
        "id": "mt_09",
        "question": (
            "What are the maximum administrative fines if a provider of a "
            "high-risk diagnostic AI breaches its Article 16 provider "
            "obligations, compared with deploying a prohibited Article 5 "
            "practice?"
        ),
        "expected_refs": ["Article 99"],
        "expected_keywords": [
            "Article 99(4)", "15", "3%", "high-risk", "Article 99(3)", "35",
            "7%", "worldwide annual turnover",
        ],
        "category": "penalties",
    },
    {
        "id": "mt_10",
        "question": (
            "Our general-purpose biomedical foundation model was trained with "
            "more than 10^25 FLOPs of compute. What systemic-risk obligations "
            "attach?"
        ),
        "expected_refs": ["Article 51", "Article 55"],
        "expected_keywords": [
            "systemic risk", "10^25", "FLOPs", "Article 55", "model evaluation",
            "adversarial testing", "serious incident",
        ],
        "category": "gpai_systemic",
    },
    {
        "id": "mt_11",
        "question": (
            "We generate synthetic patient-education videos that feature an "
            "AI-generated presenter and AI-produced narration. What labelling "
            "duty applies to this content?"
        ),
        "expected_refs": ["Article 50"],
        "expected_keywords": [
            "Article 50", "artificially generated", "marked", "machine-readable",
            "detectable", "AI-generated",
        ],
        "category": "synthetic_content_labelling",
    },
    {
        "id": "mt_12",
        "question": (
            "We are the provider of a high-risk AI diagnostic that is already on "
            "the market. What post-market monitoring and serious-incident "
            "reporting obligations apply?"
        ),
        "expected_refs": ["Article 72", "Article 73"],
        "expected_keywords": [
            "post-market monitoring", "Article 72", "serious incident",
            "Article 73", "report", "market surveillance",
        ],
        "category": "postmarket_incident",
    },
    {
        "id": "mt_13",
        "question": (
            "A hospital retrains and re-purposes a CE-marked diagnostic AI for a "
            "new intended use. Does the hospital become a provider, and is a "
            "fresh conformity assessment required?"
        ),
        "expected_refs": ["Article 25", "Article 43"],
        "expected_keywords": [
            "substantial modification", "Article 25", "new provider",
            "conformity assessment", "Article 43", "intended purpose",
        ],
        "category": "substantial_modification",
    },
    {
        "id": "mt_14",
        "question": (
            "We train a high-risk oncology-staging AI on genomic and imaging "
            "datasets. What data-governance and data-quality obligations apply "
            "to the training, validation and testing data?"
        ),
        "expected_refs": ["Article 10"],
        "expected_keywords": [
            "data governance", "Article 10", "representative", "relevant",
            "errors", "bias", "training, validation",
        ],
        "category": "data_governance",
    },
    {
        "id": "mt_15",
        "question": (
            "An AI tool flags suspicious cells on pathology slides, but a "
            "pathologist always makes the final diagnosis. Could the Article "
            "6(3) derogation make it not high-risk, and what must the provider "
            "do to rely on it?"
        ),
        "expected_refs": ["Article 6", "Annex III", "Article 49"],
        "expected_keywords": [
            "Article 6(3)", "derogation", "does not replace", "human assessment",
            "profiles natural persons", "document", "register", "Article 49(2)",
        ],
        "category": "high_risk_carveout",
    },
    {
        "id": "mt_16",
        "question": (
            "An emergency department uses AI to triage incoming patients and set "
            "treatment priority. Which risk tier applies and why?"
        ),
        "expected_refs": ["Article 6", "Annex III"],
        "expected_keywords": [
            "emergency", "patient triage", "Annex III", "high-risk",
            "Article 6(2)",
        ],
        "category": "emergency_triage",
    },
    {
        "id": "mt_17",
        "question": (
            "A mental-health support chatbot screens patients for suicide risk "
            "and routes high-risk cases to clinicians. How is it classified and "
            "what transparency duty applies toward the patient?"
        ),
        "expected_refs": ["Article 6", "Annex III", "Article 50"],
        "expected_keywords": [
            "high-risk", "Annex III", "essential", "Article 50", "interact",
            "informed",
        ],
        "category": "mental_health_triage",
    },
    {
        "id": "mt_18",
        "question": (
            "Our high-risk medical AI keeps automatically generated logs. How "
            "long must logs be retained and where is that obligation set out?"
        ),
        "expected_refs": ["Article 12", "Article 19"],
        "expected_keywords": [
            "logs", "automatically", "record-keeping", "Article 12",
            "Article 19", "traceability",
        ],
        "category": "logging_retention",
    },
]
