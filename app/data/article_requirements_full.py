"""EU AI Act Article Requirements — Regulation 2024/1689.

Structured article-level requirements for compliance gap analysis.
Sources: Official Journal of the EU L 2024/1689, legaldatahunter.com.

Each article maps to KB dimensions and provides paragraph-level
requirements with remediation guidance and effort estimates.
"""

from __future__ import annotations

# ─── Article Requirement Structure ──────────────────────────────────────


ARTICLE_REQUIREMENTS: dict[str, dict] = {

    # ─── Chapter II: Prohibited AI Practices ─────────────────────────

    "Art. 5": {
        "title": "Prohibited Artificial Intelligence Practices",
        "chapter": "II",
        "enforcement": "2025-02-02",
        "kb_dimensions": [],
        "paragraphs": {
            "5(1)(a)": {
                "text": "Placing on the market, putting into service or use of AI that deploys subliminal, manipulative or deceptive techniques to distort behaviour causing significant harm.",
                "remediation": "Remove or redesign AI features that could manipulate user behaviour through subliminal techniques.",
                "effort_hours": 8,
            },
            "5(1)(b)": {
                "text": "AI that exploits vulnerabilities of persons due to age, disability or specific social or economic situation.",
                "remediation": "Implement vulnerability safeguards and age/disability detection with protective measures.",
                "effort_hours": 8,
            },
            "5(1)(c)": {
                "text": "Social scoring by public authorities leading to detrimental or unfavourable treatment.",
                "remediation": "Ensure AI system does not perform social scoring. Document intended use boundaries.",
                "effort_hours": 4,
            },
            "5(1)(d)": {
                "text": "Real-time remote biometric identification in publicly accessible spaces for law enforcement (with exceptions).",
                "remediation": "Verify biometric use case falls within permitted exceptions or remove capability.",
                "effort_hours": 16,
            },
        },
    },

    # ─── Chapter III, Section 2: Requirements for High-Risk AI ────────

    "Art. 9": {
        "title": "Risk Management System",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["risk_mgmt"],
        "paragraphs": {
            "9(1)": {
                "text": "A risk management system shall be established, implemented, documented and maintained in relation to high-risk AI systems.",
                "remediation": "Create a risk register documenting identified risks, their likelihood, severity, and mitigation measures.",
                "effort_hours": 8,
            },
            "9(2)(a)": {
                "text": "Identification and analysis of the known and reasonably foreseeable risks that the high-risk AI system can pose to health, safety or fundamental rights.",
                "remediation": "Conduct risk identification workshop covering health, safety, and fundamental rights impacts.",
                "effort_hours": 6,
            },
            "9(2)(b)": {
                "text": "Estimation and evaluation of the risks that may emerge when the high-risk AI system is used in accordance with its intended purpose and under conditions of reasonably foreseeable misuse.",
                "remediation": "Document intended use and reasonably foreseeable misuse scenarios with risk scores.",
                "effort_hours": 6,
            },
            "9(4)": {
                "text": "Risk management measures shall give due consideration to the effects and possible interactions resulting from the combined application of the requirements, with a view to minimising risks more effectively whilst achieving an appropriate balance.",
                "remediation": "Cross-reference risk mitigations to ensure no conflicting or compounding effects.",
                "effort_hours": 4,
            },
            "9(5)": {
                "text": "High-risk AI systems shall be tested for the purposes of identifying the most appropriate and targeted risk management measures. Testing shall ensure that high-risk AI systems perform consistently for their intended purpose.",
                "remediation": "Implement risk-targeted test suite with documented test-to-risk mapping.",
                "effort_hours": 8,
            },
            "9(6)": {
                "text": "Residual risks associated with each hazard as well as the overall residual risk of the high-risk AI system shall be judged acceptable and communicated to the deployer.",
                "remediation": "Document residual risks and create deployer communication package.",
                "effort_hours": 4,
            },
        },
    },

    "Art. 10": {
        "title": "Data and Data Governance",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["data_gov"],
        "paragraphs": {
            "10(2)": {
                "text": "Training, validation and testing data sets shall be subject to data governance and management practices appropriate for the intended purpose of the high-risk AI system.",
                "remediation": "Implement data governance framework with versioning, lineage tracking, and quality checks.",
                "effort_hours": 12,
            },
            "10(2)(f)": {
                "text": "Examination in view of possible biases that are likely to affect the health and safety of persons, have a negative impact on fundamental rights or lead to discrimination.",
                "remediation": "Run bias assessment using AIF360/Fairlearn on training data across protected attributes.",
                "effort_hours": 8,
            },
            "10(3)": {
                "text": "Training, validation and testing data sets shall be relevant, sufficiently representative, and to the best extent possible, free of errors and complete in view of the intended purpose.",
                "remediation": "Document dataset composition, validate representativeness, implement data quality checks.",
                "effort_hours": 8,
            },
            "10(5)": {
                "text": "To the extent that it is strictly necessary for the purposes of ensuring bias detection and correction, providers may process special categories of personal data.",
                "remediation": "If processing sensitive data for bias correction, document legal basis and necessity assessment.",
                "effort_hours": 4,
            },
        },
    },

    "Art. 11": {
        "title": "Technical Documentation",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["tech_docs"],
        "paragraphs": {
            "11(1)": {
                "text": "The technical documentation of a high-risk AI system shall be drawn up before that system is placed on the market or put into service and shall be kept up-to-date.",
                "remediation": "Create technical documentation package covering system design, development, capabilities, and monitoring per Annex IV.",
                "effort_hours": 16,
            },
            "11(2)": {
                "text": "The technical documentation shall contain, at a minimum, the information set out in Annex IV. SMEs may provide simplified elements.",
                "remediation": "Complete Annex IV documentation checklist. SMEs may use simplified format.",
                "effort_hours": 12,
            },
        },
    },

    "Art. 12": {
        "title": "Record-Keeping",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["logging"],
        "paragraphs": {
            "12(1)": {
                "text": "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the lifetime of the system.",
                "remediation": "Implement automatic event logging with structured output covering inputs, outputs, decisions, and errors.",
                "effort_hours": 8,
            },
            "12(2)": {
                "text": "Logging capabilities shall provide a level of traceability appropriate to the intended purpose of the AI system, including at a minimum: start/stop, input reference data, and events relevant for post-market monitoring.",
                "remediation": "Ensure logs capture start/stop events, input hashes, output summaries, and monitoring-relevant events.",
                "effort_hours": 6,
            },
            "12(3)": {
                "text": "Logs shall be kept for a period appropriate to the intended purpose, of at least 6 months unless provided otherwise in Union or national law.",
                "remediation": "Configure log retention policy with minimum 6-month retention and tamper-resistant storage.",
                "effort_hours": 4,
            },
        },
    },

    "Art. 13": {
        "title": "Transparency and Provision of Information to Deployers",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["transparency"],
        "paragraphs": {
            "13(1)": {
                "text": "High-risk AI systems shall be designed and developed in such a way as to ensure that their operation is sufficiently transparent to enable deployers to interpret a system's output and use it appropriately.",
                "remediation": "Create instructions for use document covering capabilities, limitations, and interpretation guidance.",
                "effort_hours": 8,
            },
            "13(2)": {
                "text": "An appropriate type and degree of transparency shall be ensured, with a view to achieving compliance with the relevant obligations of the provider and deployer.",
                "remediation": "Document transparency measures proportionate to the system's risk and complexity.",
                "effort_hours": 4,
            },
            "13(3)(b)(ii)": {
                "text": "Instructions for use shall include known or foreseeable circumstances that may lead to risks to health, safety or fundamental rights, and the level of accuracy, robustness and cybersecurity.",
                "remediation": "Add performance metrics, known limitations, and risk scenarios to user documentation.",
                "effort_hours": 6,
            },
        },
    },

    "Art. 14": {
        "title": "Human Oversight",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["human_oversight", "decision_governance"],
        "paragraphs": {
            "14(1)": {
                "text": "High-risk AI systems shall be designed and developed in such a way that they can be effectively overseen by natural persons during the period in which they are in use.",
                "remediation": "Design oversight interface enabling human monitors to understand and control the AI system.",
                "effort_hours": 12,
            },
            "14(4)(a)": {
                "text": "Measures shall enable the individuals to properly understand the relevant capabilities and limitations of the high-risk AI system and be able to duly monitor its operation.",
                "remediation": "Build dashboards showing AI capabilities, current performance, and operational status.",
                "effort_hours": 8,
            },
            "14(4)(b)": {
                "text": "Measures shall enable the individuals to remain aware of the possible tendency of automatically relying or over-relying on the output (automation bias).",
                "remediation": "Implement automation bias countermeasures: random sampling, confidence alerts, periodic human validation.",
                "effort_hours": 6,
            },
            "14(4)(c)": {
                "text": "Measures shall enable the individuals to be able to correctly interpret the high-risk AI system's output.",
                "remediation": "Add explainability features: confidence scores, contributing factors, decision reasoning.",
                "effort_hours": 8,
            },
            "14(4)(d)": {
                "text": "Measures shall enable the individuals to be able to decide, in any particular situation, not to use the high-risk AI system or to otherwise disregard, override or reverse the output.",
                "remediation": "Implement override mechanism allowing humans to reject, modify, or override AI decisions.",
                "effort_hours": 6,
            },
            "14(4)(e)": {
                "text": "Measures shall enable the individuals to be able to intervene in the operation of the high-risk AI system or interrupt the system through a 'stop' button or a similar procedure.",
                "remediation": "Implement kill switch / emergency stop mechanism that halts AI operations immediately.",
                "effort_hours": 4,
            },
        },
    },

    "Art. 15": {
        "title": "Accuracy, Robustness and Cybersecurity",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["security", "access_control", "infra_mlops"],
        "paragraphs": {
            "15(1)": {
                "text": "High-risk AI systems shall be designed and developed in such a way as to achieve an appropriate level of accuracy, robustness and cybersecurity, and to perform consistently in those respects throughout their lifecycle.",
                "remediation": "Define and document accuracy thresholds, implement performance monitoring, set up drift detection.",
                "effort_hours": 10,
            },
            "15(2)": {
                "text": "The levels of accuracy and the relevant accuracy metrics shall be declared in the accompanying instructions of use.",
                "remediation": "Document accuracy metrics (precision, recall, F1, AUC) and declare them in user documentation.",
                "effort_hours": 4,
            },
            "15(3)": {
                "text": "High-risk AI systems shall be resilient against attempts by unauthorised third parties to alter their use, outputs or performance by exploiting system vulnerabilities.",
                "remediation": "Implement adversarial robustness testing, input validation, and security hardening.",
                "effort_hours": 12,
            },
            "15(4)": {
                "text": "High-risk AI systems shall be resilient as regards errors, faults or inconsistencies within the system or the environment. Technical redundancy solutions may include back-up plans or fail-safe mechanisms.",
                "remediation": "Add error handling, fallback mechanisms, and graceful degradation for system failures.",
                "effort_hours": 8,
            },
            "15(5)": {
                "text": "Appropriate technical and organisational measures shall be taken to ensure cybersecurity, including access controls, encryption, and logging of access.",
                "remediation": "Implement RBAC, encrypt data at rest and in transit, set up access logging and MFA.",
                "effort_hours": 12,
            },
        },
    },

    "Art. 17": {
        "title": "Quality Management System",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["quality_management"],
        "paragraphs": {
            "17(1)": {
                "text": "Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, documented in a systematic and orderly manner.",
                "remediation": "Create QMS documentation: policies, procedures, roles, resource allocation, and review schedule.",
                "effort_hours": 16,
            },
        },
    },

    # ─── Chapter III, Section 4: Deployers ───────────────────────────

    "Art. 26": {
        "title": "Obligations of Deployers",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["deployer_obligations"],
        "paragraphs": {
            "26(1)": {
                "text": "Deployers shall take appropriate technical and organisational measures to ensure they use high-risk AI systems in accordance with the instructions of use.",
                "remediation": "Review provider instructions, train operators, document usage procedures.",
                "effort_hours": 6,
            },
            "26(5)": {
                "text": "Deployers shall monitor the operation of the high-risk AI system on the basis of the instructions of use and inform the provider of serious incidents.",
                "remediation": "Set up operational monitoring and incident reporting pipeline to provider.",
                "effort_hours": 8,
            },
            "26(7)": {
                "text": "Deployers shall keep the logs automatically generated by that high-risk AI system to the extent such logs are under their control.",
                "remediation": "Configure log storage with retention policy and access controls.",
                "effort_hours": 4,
            },
        },
    },

    "Art. 27": {
        "title": "Fundamental Rights Impact Assessment",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["deployer_obligations"],
        "paragraphs": {
            "27(1)": {
                "text": "Deployers of high-risk AI systems referred to in Article 6(2) shall perform an assessment of the impact on fundamental rights that the use of such system may produce.",
                "remediation": "Conduct FRIA covering affected rights, risk to groups, mitigation, and oversight measures.",
                "effort_hours": 12,
            },
        },
    },

    # ─── Chapter IV: Transparency Obligations ────────────────────────

    "Art. 50": {
        "title": "Transparency Obligations for Certain AI Systems",
        "chapter": "IV",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["transparency", "content_transparency"],
        "paragraphs": {
            "50(1)": {
                "text": "Providers shall ensure that AI systems intended to interact directly with natural persons are designed so that the natural person is informed they are interacting with an AI system.",
                "remediation": "Add AI disclosure notice at interaction start point.",
                "effort_hours": 2,
            },
            "50(2)": {
                "text": "Providers of AI systems that generate synthetic content shall ensure the outputs are marked in a machine-readable format and detectable as artificially generated or manipulated.",
                "remediation": "Implement C2PA-compatible content labeling for AI-generated outputs.",
                "effort_hours": 6,
            },
        },
    },

    # ─── Chapter V: GPAI Models ──────────────────────────────────────

    "Art. 53": {
        "title": "Obligations for Providers of GPAI Models",
        "chapter": "V",
        "enforcement": "2025-08-02",
        "kb_dimensions": ["gpai"],
        "paragraphs": {
            "53(1)(a)": {
                "text": "Draw up and keep up-to-date the technical documentation of the model, including its training and testing process and the results of its evaluation, per Annex XI.",
                "remediation": "Create Annex XI-compliant technical documentation covering training, testing, and evaluation.",
                "effort_hours": 16,
            },
            "53(1)(b)": {
                "text": "Draw up, keep up-to-date and make available information and documentation to providers of AI systems who intend to integrate the GPAI model into their AI systems.",
                "remediation": "Create downstream provider documentation package with capabilities, limitations, and integration guidance.",
                "effort_hours": 8,
            },
            "53(1)(c)": {
                "text": "Put in place a policy to comply with Union law on copyright.",
                "remediation": "Document copyright compliance policy for training data, including opt-out mechanisms.",
                "effort_hours": 4,
            },
            "53(1)(d)": {
                "text": "Draw up and make publicly available a sufficiently detailed summary about the content used for training of the GPAI model.",
                "remediation": "Publish training data summary describing sources, types, and volumes (without trade secrets).",
                "effort_hours": 6,
            },
        },
    },

    "Art. 55": {
        "title": "Obligations for Providers of GPAI Models with Systemic Risk",
        "chapter": "V",
        "enforcement": "2025-08-02",
        "kb_dimensions": ["gpai_systemic_risk"],
        "paragraphs": {
            "55(1)(a)": {
                "text": "Perform model evaluation in accordance with standardised protocols and tools, including adversarial testing (red-teaming).",
                "remediation": "Conduct red-team exercises and document vulnerabilities found with remediation steps.",
                "effort_hours": 16,
            },
            "55(1)(b)": {
                "text": "Assess and mitigate possible systemic risks including their sources.",
                "remediation": "Document systemic risks (misuse at scale, bias amplification) with mitigation measures.",
                "effort_hours": 8,
            },
            "55(1)(c)": {
                "text": "Ensure an adequate level of cybersecurity protection for the GPAI model with systemic risk and the physical infrastructure.",
                "remediation": "Implement model-specific security: access controls, encryption, penetration testing.",
                "effort_hours": 12,
            },
        },
    },

    # ─── Chapter IX: Post-Market Monitoring ──────────────────────────

    "Art. 72": {
        "title": "Post-Market Monitoring by Providers",
        "chapter": "IX",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["decision_governance"],
        "paragraphs": {
            "72(1)": {
                "text": "Providers shall establish and document a post-market monitoring system proportionate to the nature of the AI technologies and the risks of the high-risk AI system.",
                "remediation": "Create post-market monitoring plan with drift detection, incident tracking, and periodic review.",
                "effort_hours": 10,
            },
            "72(2)": {
                "text": "The post-market monitoring system shall actively and systematically collect, document and analyse relevant data which may be provided by deployers or which may be collected through other sources.",
                "remediation": "Implement data collection pipeline for post-deployment performance metrics and user feedback.",
                "effort_hours": 8,
            },
        },
    },

    # ─── Chapter XII: Voluntary Codes ────────────────────────────────

    "Art. 95": {
        "title": "Voluntary Codes of Conduct",
        "chapter": "XII",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["voluntary_codes"],
        "paragraphs": {
            "95(1)": {
                "text": "The Commission and the Member States shall encourage and facilitate the drawing up of codes of conduct, including by providers of non-high-risk AI systems.",
                "remediation": "Adopt voluntary code of conduct covering sustainability, literacy, diversity, and accessibility.",
                "effort_hours": 6,
            },
        },
    },
    # ─── Chapter I: General Provisions ──────────────────────────────

    "Art. 4": {
        "title": "AI Literacy",
        "chapter": "I",
        "enforcement": "2025-02-02",
        "kb_dimensions": ["ai_literacy"],
        "paragraphs": {
            "4(1)": {
                "text": "Providers and deployers of AI systems shall take measures to ensure, to the best extent possible, a sufficient level of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf.",
                "remediation": "Create AI literacy training programme covering capabilities, limitations, and risks of the AI system.",
                "effort_hours": 8,
            },
        },
    },

    # ─── Chapter III, Section 5: Conformity Assessment ────────────

    "Art. 43": {
        "title": "Conformity Assessment",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["conformity_assessment"],
        "paragraphs": {
            "43(1)": {
                "text": "For high-risk AI systems listed in point 1 of Annex III, where the provider has applied harmonised standards or common specifications, the provider shall follow the conformity assessment procedure based on internal control as referred to in Annex VI.",
                "remediation": "Define conformity assessment path (internal control or third-party) based on risk classification and Annex III category.",
                "effort_hours": 12,
            },
            "43(4)": {
                "text": "High-risk AI systems that have already been subject to a conformity assessment procedure shall undergo a new conformity assessment procedure in the event of a substantial modification.",
                "remediation": "Implement substantial modification detection and re-assessment trigger in CI/CD pipeline.",
                "effort_hours": 8,
            },
        },
    },

    # ─── Supply Chain / Art. 25 ───────────────────────────────────

    "Art. 25": {
        "title": "Responsibilities Along the AI Value Chain",
        "chapter": "III",
        "enforcement": "2026-08-02",
        "kb_dimensions": ["supply_chain"],
        "paragraphs": {
            "25(1)": {
                "text": "A distributor, importer, deployer or other third party shall be considered to be a provider of a high-risk AI system if they put their name or trademark on a high-risk AI system already placed on the market, make a substantial modification, or modify the intended purpose.",
                "remediation": "Document all third-party AI components, their providers, and any modifications made. Maintain supply chain inventory.",
                "effort_hours": 8,
            },
        },
    },
}


# ─── Dimension → Article Mapping ──────────────────────────────────────

DIMENSION_TO_ARTICLES: dict[str, list[str]] = {}
for art_id, art_data in ARTICLE_REQUIREMENTS.items():
    for dim_id in art_data.get("kb_dimensions", []):
        DIMENSION_TO_ARTICLES.setdefault(dim_id, []).append(art_id)


# ─── Prompt Templates per Article ────────────────────────────────────

REMEDIATION_PROMPT_TEMPLATES: dict[str, str] = {
    "Art. 9": """You are implementing EU AI Act Art. 9 Risk Management System.

## Context
{context}

## Requirements (Art. 9)
- 9(1): Establish, document, and maintain a risk management system
- 9(2)(a): Identify and analyse known and foreseeable risks
- 9(2)(b): Evaluate risks under intended use and foreseeable misuse
- 9(5): Risk-targeted testing for consistent performance
- 9(6): Document and communicate residual risks to deployer

## Tasks
1. Create a risk register (JSON/YAML) with risk entries: component, category, likelihood (1-5), severity (1-5), mitigation
2. Document intended use boundaries and foreseeable misuse scenarios
3. Map each risk to a test case that validates the mitigation
4. Create a residual risk summary for deployer communication
5. Add risk review schedule (quarterly recommended)

## Acceptance Criteria
- [ ] Risk register exists with at least 5 identified risks
- [ ] Each risk has likelihood, severity, and mitigation documented
- [ ] At least one test per high/critical risk
- [ ] Residual risk communication document exists
""",

    "Art. 10": """You are implementing EU AI Act Art. 10 Data Governance.

## Context
{context}

## Requirements (Art. 10)
- 10(2): Data governance practices for training/validation/test sets
- 10(2)(f): Bias examination across protected attributes
- 10(3): Data relevance, representativeness, error-free, completeness
- 10(5): Special category data processing for bias correction

## Tasks
1. Document data provenance: source, collection method, date, volume
2. Implement data quality checks: null rates, schema validation, duplicate detection
3. Run bias assessment on training data across gender, age, ethnicity
4. Document train/validation/test split rationale and stratification
5. If using sensitive data for bias correction, document Art. 10(5) legal basis

## Acceptance Criteria
- [ ] Data provenance document exists
- [ ] Data quality pipeline runs before training
- [ ] Bias report generated with disparate impact ratios
- [ ] Data split documented with rationale
""",

    "Art. 12": """You are implementing EU AI Act Art. 12 Record-Keeping.

## Context
{context}

## Requirements (Art. 12)
- 12(1): Automatic recording of events over system lifetime
- 12(2): Traceability including start/stop, input reference data, monitoring events
- 12(3): Minimum 6-month log retention

## Tasks
1. Implement structured event logging (structlog or equivalent)
2. Log: system start/stop, each inference request/response, errors, overrides
3. Add input hashing for privacy-preserving traceability
4. Implement tamper-resistant log chain (hash chaining)
5. Configure retention policy (minimum 6 months, configurable)

## Acceptance Criteria
- [ ] Structured logging captures all required event types
- [ ] Logs include timestamps, request IDs, input hashes
- [ ] Log chain integrity verifiable
- [ ] Retention policy documented and enforced
""",

    "Art. 14": """You are implementing EU AI Act Art. 14 Human Oversight.

## Context
{context}

## Requirements (Art. 14(4))
(a) Understand AI capabilities and limitations
(b) Monitor operation and detect anomalies (automation bias safeguards)
(c) Correctly interpret AI output
(d) Decide not to use, disregard, override, or reverse AI output
(e) Intervene or interrupt through a stop mechanism

## Tasks
1. Add confidence threshold checks before AI decisions execute
2. Implement escalation queue for low-confidence or high-impact decisions
3. Add kill switch / emergency stop mechanism
4. Log all override decisions with user ID and reasoning
5. Create monitoring dashboard showing AI decision patterns

## Acceptance Criteria
- [ ] Confidence threshold configurable via environment variable
- [ ] Decisions below threshold routed to human review
- [ ] Kill switch endpoint exists and is tested
- [ ] Override events logged to audit trail
- [ ] Tests cover all oversight paths
""",

    "Art. 15": """You are implementing EU AI Act Art. 15 Accuracy, Robustness and Cybersecurity.

## Context
{context}

## Requirements (Art. 15)
- 15(1): Appropriate accuracy, robustness, cybersecurity throughout lifecycle
- 15(2): Declared accuracy metrics in instructions of use
- 15(3): Resilience against adversarial attacks
- 15(4): Resilience against errors, faults, inconsistencies
- 15(5): Cybersecurity: access controls, encryption, logging

## Tasks
1. Define and measure accuracy metrics (precision, recall, F1)
2. Implement drift detection for ongoing accuracy monitoring
3. Run adversarial testing (input fuzzing, prompt injection)
4. Add error handling with graceful degradation
5. Implement RBAC, encrypt secrets, enable access logging, enforce MFA

## Acceptance Criteria
- [ ] Accuracy metrics documented with thresholds
- [ ] Drift detection alerts on performance degradation
- [ ] Adversarial test suite exists
- [ ] Error handling prevents information leakage
- [ ] Security controls tested (auth, encryption, rate limiting)
""",
}

# Default template for articles without a specific one
_DEFAULT_PROMPT_TEMPLATE = """You are implementing EU AI Act {article} — {title}.

## Context
{context}

## Requirements
{requirements}

## Tasks
{tasks}

## Acceptance Criteria
{criteria}
"""


def get_prompt_template(article: str) -> str:
    """Get the remediation prompt template for an article."""
    return REMEDIATION_PROMPT_TEMPLATES.get(article, _DEFAULT_PROMPT_TEMPLATE)


def get_article_requirements(article: str) -> dict | None:
    """Get requirements for a specific article."""
    return ARTICLE_REQUIREMENTS.get(article)


def get_articles_for_dimension(dimension_id: str) -> list[str]:
    """Get all articles that apply to a KB dimension."""
    return DIMENSION_TO_ARTICLES.get(dimension_id, [])
