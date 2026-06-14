"""Medtech & life-sciences MULTI-TURN evaluation scenarios (R118).

Each scenario is a 3–4 turn conversation ending on a user turn, with natural
coreference across turns ("it", "the system", "we", "in that case").

``expected_refs`` uses ``"Art. N"`` / ``"Annex N"`` (Roman) internal format so
that the standard validation check ``r not in ARTICLE_EXISTENCE`` passes.

DO NOT call any live endpoint when importing this module.
"""
from __future__ import annotations

MEDTECH_MULTITURN: list[dict] = [
    # ── 1 ─────────────────────────────────────────────────────────────────────
    # Medical-device safety component: MRI tumour-detection AI
    # Annex I (medical device) → Art 6(1) high-risk; Art 43(3) integrated MDR
    # conformity assessment; Art 14 human-oversight obligation.
    {
        "id": "mt_med_01",
        "domain": "medical_device_high_risk",
        "turns": [
            "We are developing an AI model that analyses MRI scans and flags"
            " potential tumour regions for a radiologist to review. The model"
            " will be embedded in our FDA/CE-marked MRI software as a"
            " diagnostic aid. Does EU AI Act apply to it?",
            "It is currently being CE-marked under MDR as a Class IIb medical"
            " device. How does that interact with the AI Act's conformity"
            " requirements?",
            "Given that integrated procedure, which specific human-oversight"
            " obligations must we meet as the provider of this system?",
        ],
        "expected_refs": ["Art. 6", "Art. 14", "Art. 43", "Annex I"],
        "expected_keywords": [
            "high-risk",
            "safety component",
            "conformity assessment",
            "notified body",
            "human oversight",
        ],
        "notes": (
            "Art 6(1)/Annex I: AI safety component of an MDR Class IIb device"
            " is high-risk. Art 43(3): single integrated notified-body procedure"
            " where a notified body already covers the regulated product. Art 14:"
            " human-oversight measures for high-risk systems."
        ),
    },
    # ── 2 ─────────────────────────────────────────────────────────────────────
    # Risk-tier escalation: wellness chatbot → surgical-triage tool
    {
        "id": "mt_med_02",
        "domain": "risk_tier_escalation",
        "turns": [
            "We offer a wellness app that provides general health tips and"
            " symptom-checker guidance. It clearly identifies itself as an"
            " AI chatbot. We think it is limited-risk under the AI Act — is"
            " that right?",
            "Our hospital partner wants to extend the same system to recommend"
            " whether a patient presenting in A&E needs immediate surgical"
            " intervention. We would keep the same AI backend. Does the"
            " risk classification change?",
            "So if we deploy that extended version in the hospital context,"
            " what obligations must we meet as the deployer, and what must"
            " the original provider meet?",
        ],
        "expected_refs": ["Art. 6", "Art. 50", "Annex III"],
        "expected_keywords": [
            "limited-risk",
            "high-risk",
            "Annex III",
            "transparency",
            "deployer",
        ],
        "notes": (
            "Initial wellness chatbot: limited-risk, Art 50 transparency only."
            " Extension into A&E triage: Annex III §5(a) (medical purpose"
            " affecting health/life) → Art 6 high-risk. Provider obligations"
            " (Art 16) and deployer obligations (Art 26) both apply."
        ),
    },
    # ── 3 ─────────────────────────────────────────────────────────────────────
    # Role flip via Art 25: hospital deployer substantially modifies → provider
    {
        "id": "mt_med_03",
        "domain": "role_flip_art25",
        "turns": [
            "We are a hospital that licensed a high-risk AI diagnostic system"
            " from MedTech Corp. We have been deploying it under our own brand"
            " name in our radiology department. What are our obligations so far?",
            "Our IT team has now retrained the model on 200,000 of our own"
            " patient scans to improve accuracy for our local population."
            " Does that change anything?",
            "If we are now considered the provider, what new steps must we"
            " take before we can continue using the system in our clinical"
            " workflow?",
        ],
        "expected_refs": ["Art. 16", "Art. 25", "Art. 26", "Annex IV"],
        "expected_keywords": [
            "substantial modification",
            "provider",
            "deployer",
            "technical documentation",
            "conformity",
        ],
        "notes": (
            "Initial position: hospital as deployer, Art 26 obligations."
            " Retraining on proprietary data: Art 25 substantial modification"
            " → hospital becomes provider. Art 16 provider obligations apply,"
            " including Annex IV technical documentation and new conformity"
            " assessment."
        ),
    },
    # ── 4 ─────────────────────────────────────────────────────────────────────
    # GPAI on genomic/biomedical data with compute scale-up crossing threshold
    {
        "id": "mt_med_04",
        "domain": "gpai_genomic_systemic_risk",
        "turns": [
            "We are building a large language model trained on biomedical"
            " literature and de-identified genomic sequences to support drug"
            " discovery. We expect to use about 10^23 FLOPs for the initial"
            " training run. What obligations apply under the AI Act?",
            "We have received Series B funding and now plan to scale the"
            " training to 10^25 FLOPs, and the model will be made available"
            " through an API to pharmaceutical companies. Does this change"
            " things?",
            "Given the systemic-risk designation, what specific additional"
            " obligations does that impose on us as the GPAI model provider?",
        ],
        "expected_refs": ["Art. 51", "Art. 53", "Art. 55"],
        "expected_keywords": [
            "general-purpose AI",
            "systemic risk",
            "10^25 FLOPs",
            "transparency",
            "model evaluation",
        ],
        "notes": (
            "Below 10^25 FLOPs: Art 53 GPAI obligations (transparency,"
            " technical documentation, copyright). At or above 10^25 FLOPs:"
            " Art 51 systemic-risk presumption → Art 55 additional obligations"
            " (adversarial testing, incident reporting to AI Office, cybersecurity)."
        ),
    },
    # ── 5 ─────────────────────────────────────────────────────────────────────
    # Scientific R&D exclusion → ends at market placement (Art 2(6)/(8))
    {
        "id": "mt_med_05",
        "domain": "rd_exclusion_market_placement",
        "turns": [
            "We are an academic spin-out running a clinical study to evaluate"
            " an AI-powered ECG interpretation tool. The study has ethics"
            " board approval and participants have given informed consent."
            " Does the EU AI Act apply to us yet?",
            "The study results are positive. We now want to license the"
            " algorithm to cardiac device manufacturers for integration"
            " into their CE-marked monitors. At what point does the AI Act"
            " start to apply?",
            "One manufacturer wants to run a limited pre-market technical"
            " validation on 500 patients before full CE marking. Does the"
            " Act apply during that validation phase?",
        ],
        "expected_refs": ["Art. 2", "Art. 6", "Annex I"],
        "expected_keywords": [
            "scientific research",
            "exclusion",
            "market placement",
            "pre-market testing",
            "high-risk",
        ],
        "notes": (
            "Art 2(6): research-only phase with no market placement excluded."
            " Art 2(8): pre-market testing carve-out applies during the"
            " manufacturer's validation. Full obligations from first placing"
            " on the market (Art 6/Annex I for an ECG cardiac-monitoring"
            " safety component)."
        ),
    },
    # ── 6 ─────────────────────────────────────────────────────────────────────
    # Hospital generative chatbot for patient queries: limited-risk, Art 50 only
    {
        "id": "mt_med_06",
        "domain": "hospital_patient_chatbot_limited_risk",
        "turns": [
            "Our hospital has deployed a generative AI chatbot on our patient"
            " portal so patients can ask questions about appointment preparation,"
            " medication side effects, and discharge instructions. The chatbot"
            " never makes clinical decisions. What are our obligations?",
            "Do we need to provide any disclosure to patients that they are"
            " interacting with an AI, and if so, what exactly must the"
            " disclosure say?",
            "We are the hospital operating the chatbot, not the company that"
            " built the underlying language model. Who owes what obligation"
            " — us or the model developer?",
        ],
        "expected_refs": ["Art. 50"],
        "expected_keywords": [
            "limited-risk",
            "transparency",
            "chatbot",
            "deployer",
            "disclosure",
        ],
        "notes": (
            "A patient-query chatbot that does not make clinical decisions is"
            " limited-risk. Art 50(3)/(4): the deployer (hospital) must inform"
            " users they are interacting with an AI (when the chatbot is not"
            " obviously an AI). Art 50(1)/(2): provider transparency"
            " obligations on the model developer. NOT Art 13 (high-risk"
            " transparency); NOT Annex III."
        ),
    },
    # ── 7 ─────────────────────────────────────────────────────────────────────
    # Biometric triage vs clinical-trial AI: Annex III §5 distinctions
    {
        "id": "mt_med_07",
        "domain": "biometric_triage_clinical_trial",
        "turns": [
            "We are building an AI that predicts ICU patient deterioration"
            " by analysing physiological time-series data including heart"
            " rate, oxygen saturation, and blood pressure. No facial or"
            " biometric identifiers are used. How is this classified?",
            "A separate system we are developing uses facial and gait"
            " analysis to stratify patients for a clinical trial based on"
            " predicted disease severity. Is this different?",
            "The second system also infers anxiety and stress levels from"
            " facial micro-expressions to assess whether a patient"
            " can give informed consent. Does that raise any prohibition"
            " concerns?",
        ],
        "expected_refs": ["Art. 5", "Art. 6", "Annex III"],
        "expected_keywords": [
            "high-risk",
            "Annex III",
            "biometric",
            "emotion recognition",
            "prohibition",
        ],
        "notes": (
            "ICU deterioration prediction: Annex III §5(a) (medical purpose),"
            " Art 6 high-risk. Clinical-trial stratification using biometrics:"
            " Annex III §5(d). Inferring emotional state to assess capacity:"
            " Art 5(1)(f) prohibition on emotion recognition — the medical/safety"
            " carve-out requires a genuine diagnostic necessity, not proxy"
            " assessment of consent capacity."
        ),
    },
    # ── 8 ─────────────────────────────────────────────────────────────────────
    # Emotion/stress monitoring of healthcare workers: Art 5(1)(f) + carve-out
    {
        "id": "mt_med_08",
        "domain": "emotion_monitoring_workplace_prohibition",
        "turns": [
            "We are developing a wearable for hospital staff that monitors"
            " physiological indicators of cognitive fatigue and stress during"
            " shifts, with the aim of alerting managers when a clinician may"
            " be impaired. Does the AI Act prohibit this?",
            "The vendor argues that because the purpose is occupational health"
            " and patient safety, this falls within the medical/safety"
            " exception. Is that correct?",
            "If we narrow the system so that alerts go only to the individual"
            " clinician and not to managers, and the system is deployed at"
            " the clinician's own request, does that change the prohibition"
            " analysis?",
        ],
        "expected_refs": ["Art. 5"],
        "expected_keywords": [
            "emotion recognition",
            "workplace",
            "prohibited",
            "carve-out",
            "safety",
        ],
        "notes": (
            "Art 5(1)(f): prohibits emotion-recognition in the workplace"
            " (including healthcare settings). The medical/safety carve-out"
            " is narrow — a general fatigue-alert system triggered by stress"
            " proxies and reported to managers does not clearly qualify."
            " Turn 3 (self-reporting only, at clinician request) is a closer"
            " case but the prohibition focus is on the employer-monitoring"
            " dynamic."
        ),
    },
    # ── 9 ─────────────────────────────────────────────────────────────────────
    # Cross-framework: AI Act + MDR + GDPR + Clinical Trials Regulation
    {
        "id": "mt_med_09",
        "domain": "cross_framework_mdr_gdpr_clinical_trials",
        "turns": [
            "We have a CE-marked AI-powered imaging device certified under MDR."
            " We now understand the EU AI Act also applies. Are our MDR"
            " obligations sufficient, or do we need to do additional work?",
            "Our system processes de-identified genomic and imaging data from"
            " clinical trial participants enrolled under the EU Clinical"
            " Trials Regulation. Our data processor agreement covers GDPR."
            " Does the AI Act impose any separate data-governance requirements"
            " on top of those?",
            "Specifically, what must our AI Act technical documentation cover"
            " that is not already in our MDR technical file?",
        ],
        "expected_refs": ["Art. 6", "Art. 10", "Art. 11", "Annex I", "Annex IV"],
        "expected_keywords": [
            "technical documentation",
            "data governance",
            "high-risk",
            "Annex IV",
            "training data",
        ],
        "notes": (
            "MDR certification does not fulfil AI Act obligations. Art 6/Annex I:"
            " still high-risk. Art 10: data-governance obligations (data quality,"
            " training/validation/testing sets, bias monitoring) are AI-Act-specific"
            " and not covered by GDPR or MDR alone. Art 11/Annex IV: the AI Act"
            " technical documentation has distinct requirements (architecture,"
            " training methodology, performance metrics) beyond the MDR technical"
            " file."
        ),
    },
    # ── 10 ────────────────────────────────────────────────────────────────────
    # Post-market monitoring + serious-incident reporting: Art 72 + Art 73
    {
        "id": "mt_med_10",
        "domain": "post_market_incident_reporting",
        "turns": [
            "Our high-risk AI system for detecting sepsis in ICU patients"
            " has been on the market for eight months. What post-market"
            " monitoring obligations do we have as the provider?",
            "We have identified a pattern where the system significantly"
            " under-predicts sepsis risk in patients with a particular"
            " genetic background, which has led to delayed treatment in"
            " three cases. Is this a serious incident we must report?",
            "Our device is also CE-marked under MDR. Do we report separately"
            " under MDR and the AI Act, or is there a combined procedure?",
        ],
        "expected_refs": ["Art. 72", "Art. 73"],
        "expected_keywords": [
            "post-market monitoring",
            "serious incident",
            "reporting",
            "market surveillance",
            "national authority",
        ],
        "notes": (
            "Art 72: providers of high-risk AI must maintain a post-market"
            " monitoring plan. Art 73: a serious incident (including unexpected"
            " risk to health — three delayed sepsis diagnoses) must be"
            " reported to the national market-surveillance authority without"
            " undue delay. Under MDR the serious-incident report to the"
            " competent authority runs in parallel; the AI Act has its own"
            " distinct reporting channel. No consolidated single-report"
            " procedure exists under current law."
        ),
    },
]
