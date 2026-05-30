"""Paper-grounded multi-turn eval set (V4) — fresh R99 generation.

Source: Davvetas et al. arXiv:2603.09435 "AI Act Evaluation Benchmark".

Twelve 3–5 turn conversations probing cross-turn coherence: risk-tier
escalation, role flips, obligation-chain building, and prohibited-practice
creep. Every conversation ends on a USER turn (the route flattens the last
few turns into the live question). Distinct from the R98 V3 multi-turn set.

Schema (matches runner_v2 multiturn schema):

    {
        "id": str,
        "turns": list[{"role": "user"|"assistant", "content": str}],
        "expected_final_refs": list[str],
        "expected_final_keywords": list[str],
        "notes": str,
    }

Coherence (runner_v2._score_multiturn_row) = the final answer cites >=1
expected ref AND surfaces >=50% of expected keywords AND is not a refusal.
"""
from __future__ import annotations

SCENARIOS: list[dict] = [
    # 1 — minimal → prohibited escalation (workplace emotion recognition)
    {
        "id": "mt_v4_001",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We run an internal AI tool that summarises team meeting "
                    "notes for our own staff. What risk level under the AI Act?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "An internal meeting-summary tool with no high-risk domain "
                    "and no public interaction is minimal-risk; no specific "
                    "obligations apply."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We're adding a feature that reads employees' facial "
                    "expressions during the meeting to score their engagement. "
                    "Does anything change?"
                ),
            },
        ],
        "expected_final_refs": ["Article 5"],
        "expected_final_keywords": ["emotion recognition", "workplace", "prohibited"],
        "notes": (
            "Minimal → prohibited. Adding workplace emotion recognition flips "
            "it to an Art. 5(1)(f) prohibited practice. Engine must update its "
            "prior minimal verdict."
        ),
    },
    # 2 — high-risk provider conformity chain
    {
        "id": "mt_v4_002",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We provide a high-risk AI system for sorting CVs in hiring. "
                    "We've already set up a risk-management system and data "
                    "governance. What's the next obligation?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "With risk management (Article 9) and data governance "
                    "(Article 10) in place, you next prepare technical "
                    "documentation and ensure logging and human oversight."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Documentation and oversight are done. Before we put it on "
                    "the market, what procedure must we pass and how is "
                    "conformity demonstrated?"
                ),
            },
        ],
        "expected_final_refs": ["Article 43"],
        "expected_final_keywords": ["conformity assessment", "high-risk", "market"],
        "notes": (
            "Obligation-chain build to the conformity-assessment step "
            "(Art. 43) before placing a high-risk AI on the market."
        ),
    },
    # 3 — GPAI compute scale-up → systemic risk
    {
        "id": "mt_v4_003",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We train a general-purpose AI model. What baseline AI Act "
                    "obligations apply to us as the model provider?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Providers of general-purpose AI models have transparency "
                    "and documentation obligations under Article 53, including "
                    "technical documentation and a training-data summary."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Our next training run used 3x10^25 FLOPs of compute. Does "
                    "that change our classification and obligations?"
                ),
            },
        ],
        "expected_final_refs": ["Article 51", "Article 55"],
        "expected_final_keywords": ["systemic risk", "10^25", "general-purpose"],
        "notes": (
            "GPAI standard → systemic-risk. 10^25 FLOPs crosses the Art. 51 "
            "systemic-risk threshold, adding Art. 55 obligations."
        ),
    },
    # 4 — deployer substantial modification → becomes provider
    {
        "id": "mt_v4_004",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We are a deployer of a third-party high-risk AI system for "
                    "credit scoring. What are our duties as a deployer?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "As a deployer you must use the system per its instructions, "
                    "ensure human oversight and monitor its operation under "
                    "Article 26."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We've now substantially modified the model and put our own "
                    "brand on it. Does our legal role change?"
                ),
            },
        ],
        "expected_final_refs": ["Article 25"],
        "expected_final_keywords": ["provider", "substantial modification", "obligations"],
        "notes": (
            "Role flip: substantial modification + rebrand makes the deployer "
            "a provider under Art. 25(1), inheriting provider obligations."
        ),
    },
    # 5 — limited → high-risk (education)
    {
        "id": "mt_v4_005",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We offer an AI tutoring chatbot that helps students study. "
                    "It tells users it's an AI. What risk level?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "An educational chatbot that discloses it is AI is "
                    "limited-risk under Article 50(1)."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We're extending it to score students' final exams and decide "
                    "who passes the course. Does the classification change?"
                ),
            },
        ],
        "expected_final_refs": ["Annex III", "Article 6"],
        "expected_final_keywords": ["high-risk", "education", "Annex III"],
        "notes": (
            "Limited → high-risk. Exam scoring that determines access to "
            "education is Annex III(3) high-risk via the Art. 6 gateway."
        ),
    },
    # 6 — non-EU provider responsibility chain (importer)
    {
        "id": "mt_v4_006",
        "turns": [
            {
                "role": "user",
                "content": (
                    "A high-risk AI system is built by a company in Japan with no "
                    "EU presence. We buy it and bring it into the EU market. Who "
                    "is responsible for AI Act compliance?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Bringing a third-country high-risk AI system onto the EU "
                    "market makes you the importer, with verification duties."
                ),
            },
            {
                "role": "user",
                "content": (
                    "What exactly must we, as the importer, verify before placing "
                    "it on the market?"
                ),
            },
        ],
        "expected_final_refs": ["Article 23"],
        "expected_final_keywords": ["importer", "conformity assessment", "verify"],
        "notes": (
            "Importer obligations (Art. 23): verify conformity assessment, CE "
            "marking, documentation before market placement."
        ),
    },
    # 7 — FRIA for a public-body deployer
    {
        "id": "mt_v4_007",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We are a municipal authority planning to deploy a high-risk "
                    "AI system that decides eligibility for housing benefit. "
                    "What's our headline obligation as a deployer?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "As a public-body deployer of a high-risk AI affecting access "
                    "to essential services, you have Article 26 deployer duties."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Is there a specific assessment we must run before we start, "
                    "given we are a public authority?"
                ),
            },
        ],
        "expected_final_refs": ["Article 27"],
        "expected_final_keywords": ["fundamental rights", "impact assessment", "deployer"],
        "notes": (
            "Public-body deployer of Annex III high-risk AI must run a "
            "fundamental-rights impact assessment (Art. 27)."
        ),
    },
    # 8 — data governance interplay
    {
        "id": "mt_v4_008",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Our high-risk recruitment AI is trained on historical hiring "
                    "data. We're worried it could be biased. Which AI Act article "
                    "governs the training data?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Article 10 governs data and data governance, including "
                    "examining datasets for bias and ensuring they are relevant "
                    "and representative."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Concretely, what data-quality and bias steps does that "
                    "article require us to take?"
                ),
            },
        ],
        "expected_final_refs": ["Article 10"],
        "expected_final_keywords": ["data governance", "bias", "representative"],
        "notes": (
            "Art. 10 data-governance obligations: bias examination, "
            "relevance/representativeness of training/validation/testing sets."
        ),
    },
    # 9 — post-market monitoring → serious incident
    {
        "id": "mt_v4_009",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Our high-risk AI medical-triage system is now live in "
                    "hospitals. What ongoing duty do we have after deployment?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Providers must operate a post-market monitoring system "
                    "under Article 72 to track the system's performance in use."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Last week the system caused a patient to be mis-triaged and "
                    "harmed. What must we do now under the AI Act?"
                ),
            },
        ],
        "expected_final_refs": ["Article 73"],
        "expected_final_keywords": ["serious incident", "report", "authorities"],
        "notes": (
            "Post-market monitoring (Art. 72) → a serious incident triggers the "
            "Art. 73 reporting duty to market-surveillance authorities."
        ),
    },
    # 10 — right to explanation
    {
        "id": "mt_v4_010",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We deploy a high-risk AI that decides who gets a loan. An "
                    "applicant was refused. What does the AI Act say we owe them?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Affected persons subject to high-risk AI decisions have "
                    "rights to information about the system's role in the "
                    "decision."
                ),
            },
            {
                "role": "user",
                "content": (
                    "The applicant now formally demands to know why the AI denied "
                    "them. Which article gives them that right?"
                ),
            },
        ],
        "expected_final_refs": ["Article 86"],
        "expected_final_keywords": ["explanation", "decision", "affected"],
        "notes": (
            "Art. 86 — right to explanation of individual decision-making for "
            "persons affected by high-risk AI."
        ),
    },
    # 11 — minimal stays minimal
    {
        "id": "mt_v4_011",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We sell an AI spam filter that sorts junk email for "
                    "businesses. What AI Act obligations apply?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "A spam filter is a textbook minimal-risk system; no specific "
                    "AI Act obligations apply beyond voluntary good practice."
                ),
            },
            {
                "role": "user",
                "content": (
                    "We added an AI that auto-suggests canned replies. Still "
                    "minimal, or have we crossed into a regulated tier?"
                ),
            },
        ],
        "expected_final_refs": ["Article 5", "Article 6"],
        "expected_final_keywords": ["minimal", "risk", "obligations"],
        "notes": (
            "Minimal stays minimal — a reply-suggestion feature does not trigger "
            "Art. 5 / Art. 6 / Art. 50. Tests over-escalation."
        ),
    },
    # 12 — prohibited practice creep (biometric categorisation)
    {
        "id": "mt_v4_012",
        "turns": [
            {
                "role": "user",
                "content": (
                    "We run an ad-targeting AI that groups users by their stated "
                    "interests for marketing. What risk level?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Interest-based ad targeting that does not infer protected "
                    "characteristics is generally limited or minimal-risk."
                ),
            },
            {
                "role": "user",
                "content": (
                    "To sharpen targeting we now infer users' religious beliefs "
                    "and political opinions from their biometric data. Is that a "
                    "problem?"
                ),
            },
        ],
        "expected_final_refs": ["Article 5"],
        "expected_final_keywords": ["biometric categorisation", "prohibited", "political"],
        "notes": (
            "Limited/minimal → prohibited. Inferring protected characteristics "
            "from biometric data is an Art. 5(1)(g) prohibited practice."
        ),
    },
]
