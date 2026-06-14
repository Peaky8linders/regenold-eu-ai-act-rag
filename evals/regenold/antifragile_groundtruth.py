"""Ground truth for the 20 Antifragile expert-review Q&A (R118).

Source: "Antifragile AI Review Questions and Answers.docx" — 20 questions, each
with the system's original ("Lexy") answer, its citations, and an EU-AI-Act
legal expert's verdict + the specific mistakes flagged. This module encodes the
GOLD (corrected) reference set, a synthesized concise-correct gold answer, the
expert verdict, and a machine-checkable list of the flagged mistakes so a live
re-run can measure (a) the Regenold rubric metrics vs gold and (b) how many of
the expert-flagged mistakes the current deployed system has fixed.

`gold_refs` are head-level wire form ("Article N" / "Annex N"); sub-citation
errors (e.g. Annex IV.1(e) vs IV.2.a) are captured in `mistakes` instead.

Each mistake has `verify = {"present": [...], "absent": [...]}`: the mistake is
counted RESOLVED in a new answer when every `present` substring appears
(case-insensitive) AND no `absent` substring appears. These are proxies; the
final human read confirms. `verdict` is the expert's overall grade of the
ORIGINAL answer.
"""
from __future__ import annotations

ANTIFRAGILE_GT: dict[str, dict] = {
    "q01": {
        "question": "What risk categories are provided for AI systems?",
        "verdict": "partially_wrong_incomplete_error",
        "gold_refs": ["Article 5", "Article 6", "Annex I", "Annex III", "Article 50", "Article 51"],
        "gold_answer": (
            "The EU AI Act establishes a tiered risk framework. Article 5 sets the "
            "unacceptable-risk tier, banning eight prohibited practices outright. "
            "Article 6, via Annex I product-safety legislation and the Annex III "
            "use-case list, defines the high-risk tier. Limited-risk systems carry "
            "only Article 50 transparency duties, and general-purpose AI models are "
            "governed by a parallel regime under Articles 51 to 55."
        ),
        "expected_keywords": ["unacceptable", "prohibited", "high-risk", "limited", "transparency", "general-purpose", "tier"],
        "lexy_refs": ["Article 6", "Annex III", "Annex I", "Article 5"],
        "mistakes": [
            {"id": "q01_m1", "type": "factual_error",
             "desc": "Frames social scoring as 'by public authorities'; Art 5(1)(c) has no public-authority limit in the final Regulation.",
             "verify": {"present": [], "absent": ["social scoring by public authorities", "scoring by public authorities"]}},
            {"id": "q01_m2", "type": "incomplete_enumeration",
             "desc": "Lists only 5 of 8 Art 5 prohibitions (missing predictive-policing, facial-scraping, workplace emotion).",
             "verify": {"present": ["scrap", "emotion"], "absent": []}},
            {"id": "q01_m3", "type": "missing_tier",
             "desc": "Addresses only the unacceptable tier; omits high-risk, limited-risk transparency, and the GPAI Art 51-55 regime.",
             "verify": {"present": ["high-risk"], "absent": []}},
            {"id": "q01_m4", "type": "missing_gpai",
             "desc": "Omits the GPAI parallel regime entirely.",
             "verify": {"present": ["general-purpose"], "absent": []}},
        ],
    },
    "q02": {
        "question": "What types of AI systems or practices are explicitly prohibited by the AI Act?",
        "verdict": "half_right_partial_enumeration",
        "gold_refs": ["Article 5"],
        "gold_answer": (
            "Article 5 prohibits eight categories of AI practice: subliminal or "
            "manipulative techniques causing significant harm; exploitation of "
            "vulnerabilities based on age, disability or socio-economic situation; "
            "social scoring leading to unjustified detrimental treatment; predictive "
            "policing based solely on profiling; untargeted scraping of facial images "
            "to build recognition databases; emotion inference in workplaces and "
            "educational institutions; biometric categorisation inferring sensitive "
            "attributes; and real-time remote biometric identification in public "
            "spaces for law enforcement, subject to narrow exceptions."
        ),
        "expected_keywords": ["eight", "subliminal", "social scoring", "scraping", "emotion", "biometric", "real-time"],
        "lexy_refs": ["Article 5", "Annex II", "Article 27"],
        "mistakes": [
            {"id": "q02_m1", "type": "incomplete_enumeration",
             "desc": "States eight but lists only three prohibitions.",
             "verify": {"present": ["scrap", "emotion", "biometric categor"], "absent": []}},
            {"id": "q02_m2", "type": "factual_error",
             "desc": "'social scoring by public authorities' — same public-authority error as Q1.",
             "verify": {"present": [], "absent": ["scoring by public authorities", "social scoring by public"]}},
            {"id": "q02_m3", "type": "irrelevant_citation",
             "desc": "Cites Annex II and Article 27, both irrelevant to prohibitions.",
             "verify": {"present": [], "absent": []}, "ref_absent": ["Annex II", "Article 27"]},
        ],
    },
    "q03": {
        "question": "What is the definition of high risk?",
        "verdict": "mostly_correct_omissions",
        "gold_refs": ["Article 6", "Annex I", "Annex III"],
        "gold_answer": (
            "Under Article 6 an AI system is high-risk by either of two routes. "
            "First, where it is a safety component of, or itself is, a product covered "
            "by Annex I Union harmonisation legislation that must undergo third-party "
            "conformity assessment (Article 6(1)). Second, where it falls within an "
            "Annex III use-case category (Article 6(2)). Article 6(3) exempts Annex III "
            "systems that perform only narrow procedural, preparatory or "
            "human-review-supporting tasks, unless they profile natural persons."
        ),
        "expected_keywords": ["two", "safety component", "Annex I", "Annex III", "conformity assessment", "Article 6(3)"],
        "lexy_refs": ["Article 6", "Annex III"],
        "mistakes": [
            {"id": "q03_m1", "type": "omission",
             "desc": "Omits that the Annex I route requires third-party conformity assessment (Art 6(1)(b)).",
             "verify": {"present": ["conformity assessment"], "absent": []}},
            {"id": "q03_m2", "type": "omission",
             "desc": "Omits the Art 6(3) carve-outs for non-high-risk Annex III tasks.",
             "verify": {"present": ["6(3)"], "absent": []}},
            {"id": "q03_m3", "type": "missing_citation",
             "desc": "Citations omit Annex I despite the answer targeting that route.",
             "verify": {"present": [], "absent": []}, "ref_present": ["Annex I"]},
        ],
    },
    "q04": {
        "question": "Which sectors or applications are considered high-risk under the regulation?",
        "verdict": "half_right_structural_omission",
        "gold_refs": ["Article 6", "Annex III", "Annex I"],
        "gold_answer": (
            "High-risk classification follows two routes under Article 6. The Annex III "
            "route covers eight use-case areas: biometrics, critical infrastructure, "
            "education, employment and worker management, essential private and public "
            "services, law enforcement, migration and border control, and "
            "administration of justice and democratic processes. The Annex I route "
            "covers AI that is a safety component of regulated products such as medical "
            "devices and machinery that require third-party conformity assessment."
        ),
        "expected_keywords": ["Annex III", "Annex I", "eight", "biometrics", "employment", "safety component"],
        "lexy_refs": ["Article 6", "Annex I", "Article 25", "Annex III"],
        "mistakes": [
            {"id": "q04_m1", "type": "structural_omission",
             "desc": "Omits the Annex I product-safety route entirely.",
             "verify": {"present": ["Annex I"], "absent": []}},
            {"id": "q04_m2", "type": "irrelevant_citation",
             "desc": "Cites Article 25 (value-chain), unrelated to which sectors are high-risk.",
             "verify": {"present": [], "absent": []}, "ref_absent": ["Article 25"]},
        ],
    },
    "q05": {
        "question": "How should users be informed when interacting with AI systems?",
        "verdict": "mostly_right_role_error",
        "gold_refs": ["Article 50"],
        "gold_answer": (
            "Article 50 sets transparency duties split by role. Providers must ensure "
            "systems intended to interact directly with people disclose their AI nature "
            "unless obvious (Article 50(1)), and must mark machine-generated synthetic "
            "content in a detectable, machine-readable format (Article 50(2)). Deployers "
            "of emotion-recognition or biometric-categorisation systems must inform "
            "exposed persons (Article 50(3)), and deployers of deepfakes must disclose "
            "that the content is artificially generated (Article 50(4))."
        ),
        "expected_keywords": ["provider", "deployer", "50(1)", "50(3)", "transparency", "exposed persons"],
        "lexy_refs": ["Article 50", "Article 50"],
        "mistakes": [
            {"id": "q05_m1", "type": "role_error",
             "desc": "Puts Art 50(3) (emotion/biometric disclosure) on providers; it is a deployer duty.",
             "verify": {"present": ["deployer"], "absent": []}},
            {"id": "q05_m2", "type": "conflation",
             "desc": "Conflates Art 50(2) provider marking and Art 50(4) deployer deepfake disclosure.",
             "verify": {"present": ["50(2)", "50(4)"], "absent": []}},
        ],
    },
    "q06": {
        "question": "What are AI systems with minimal risks?",
        "verdict": "half_right_irrelevant_citations",
        "gold_refs": ["Article 5", "Article 6", "Article 50"],
        "gold_answer": (
            "Minimal-risk is the residual category: AI systems that are neither "
            "prohibited under Article 5, nor high-risk under Annex I or Annex III, nor "
            "subject to Article 50 transparency duties, nor general-purpose AI models. "
            "Such systems carry no mandatory obligations under the Act beyond the "
            "cross-cutting AI-literacy duty, though voluntary codes of conduct are "
            "encouraged."
        ),
        "expected_keywords": ["residual", "neither", "prohibited", "high-risk", "transparency", "no mandatory"],
        "lexy_refs": ["Annex III", "Article 14", "Article 13", "Article 27", "Article 12", "Article 9"],
        "mistakes": [
            {"id": "q06_m1", "type": "irrelevant_citation",
             "desc": "All six citations (Annex III, Arts 9/12/13/14/27) attach to high-risk systems, not minimal-risk.",
             "verify": {"present": [], "absent": []}, "ref_absent": ["Article 14", "Article 13", "Article 27", "Article 12", "Article 9"]},
            {"id": "q06_m2", "type": "partial_definition",
             "desc": "Defines minimal-risk only as 'outside the 8 high-risk categories'; misses prohibited/transparency/GPAI exclusions.",
             "verify": {"present": ["residual"], "absent": []}},
        ],
    },
    "q07": {
        "question": "What are the guiding principles established by the AI Act?",
        "verdict": "wrong_topic_shift",
        "gold_refs": ["Article 1", "Article 4"],
        "gold_answer": (
            "The Act's guiding principles for trustworthy AI, set out in Recital 27, "
            "are: human agency and oversight; technical robustness and safety; privacy "
            "and data governance; transparency; diversity, non-discrimination and "
            "fairness; social and environmental well-being; and accountability. These "
            "inform the Act's purpose under Article 1 and the AI-literacy duty under "
            "Article 4."
        ),
        "expected_keywords": ["human", "oversight", "robustness", "privacy", "transparency", "non-discrimination", "accountability"],
        "lexy_refs": ["Article 54", "Article 22", "Article 3", "Article 53", "Article 47", "Article 11"],
        "mistakes": [
            {"id": "q07_m1", "type": "wrong_answer",
             "desc": "Answered about GPAI authorised representative — entirely off-topic.",
             "verify": {"present": ["oversight", "accountability"], "absent": ["authorised representative", "authorized representative"]}},
            {"id": "q07_m2", "type": "wrong_citations",
             "desc": "Cited GPAI/authrep articles; should anchor on the trustworthy-AI principles.",
             "verify": {"present": [], "absent": []}, "ref_absent": ["Article 54", "Article 22"]},
        ],
    },
    "q08": {
        "question": 'What is the definition of a "system of artificial intelligence"?',
        "verdict": "correct",
        "gold_refs": ["Article 3"],
        "gold_answer": (
            "Under Article 3(1) an AI system is a machine-based system designed to "
            "operate with varying levels of autonomy, that may exhibit adaptiveness "
            "after deployment, and that, for explicit or implicit objectives, infers "
            "from the input it receives how to generate outputs such as predictions, "
            "content, recommendations or decisions that can influence physical or "
            "virtual environments."
        ),
        "expected_keywords": ["machine-based", "autonomy", "adaptiveness", "infers", "outputs", "objectives"],
        "lexy_refs": ["Article 3", "Article 2"],
        "mistakes": [],
    },
    "q09": {
        "question": "What are the penalties for violating the provisions of the regulation for high-risk AI systems?",
        "verdict": "wrong_by_omission",
        "gold_refs": ["Article 99"],
        "gold_answer": (
            "For infringements relating to high-risk AI systems, Article 99(4) sets "
            "fines of up to EUR 15 000 000 or 3% of total worldwide annual turnover, "
            "whichever is higher. For SMEs and start-ups, Article 99(6) applies the "
            "lower of the two amounts. The most severe tier, Article 99(3) up to EUR "
            "35 000 000 or 7%, is reserved for breaches of the Article 5 prohibitions."
        ),
        "expected_keywords": ["99(4)", "15", "3%", "SME", "99(6)", "turnover"],
        "lexy_refs": ["Article 99"],
        "mistakes": [
            {"id": "q09_m1", "type": "omission",
             "desc": "Recites generic Art 99(1); the high-risk-specific ceiling is Art 99(4) (EUR 15M/3%).",
             "verify": {"present": ["99(4)"], "absent": []}},
            {"id": "q09_m2", "type": "omission",
             "desc": "Omits the SME lower-of-two-amounts rule (Art 99(6)).",
             "verify": {"present": ["99(6)"], "absent": []}},
        ],
    },
    "q10": {
        "question": "What is the difference between the deployer and the provider?",
        "verdict": "correct_substance",
        "gold_refs": ["Article 3", "Article 25"],
        "gold_answer": (
            "Under Article 3, a provider develops an AI system (or has one developed) "
            "and places it on the market or puts it into service under its own name, "
            "while a deployer uses the system under its own authority, except for purely "
            "personal non-professional use. Under Article 25 a deployer becomes a "
            "provider with full Article 16 obligations if it puts its name on a "
            "high-risk system, substantially modifies it, or changes its intended "
            "purpose so it becomes high-risk."
        ),
        "expected_keywords": ["provider", "deployer", "places on the market", "own authority", "Article 25"],
        "lexy_refs": ["Article 3", "Article 19", "Article 17", "Article 16"],
        "mistakes": [
            {"id": "q10_m1", "type": "suboptimal_citation",
             "desc": "Cites Art 17 (QMS) and 19 (logs) which are provider duties, not definitions; should add Art 25 role transition.",
             "verify": {"present": [], "absent": []}, "ref_present": ["Article 25"]},
        ],
    },
    "q11": {
        "question": "Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?",
        "verdict": "correct_substance_wrong_subcitation",
        "gold_refs": ["Article 11", "Annex IV"],
        "gold_answer": (
            "Yes. Under Article 11 providers must draw up technical documentation "
            "meeting Annex IV before placing a high-risk system on the market. Hardware "
            "specifications fall within Annex IV point 1(e), the description of the "
            "hardware on which the system runs, and Annex IV point 2(c) additionally "
            "requires the computational resources used to develop, train, test and "
            "validate the system."
        ),
        "expected_keywords": ["Annex IV", "Article 11", "hardware", "1(e)", "computational resources"],
        "lexy_refs": ["Annex IV", "Article 11", "Annex IV.2.a"],
        "mistakes": [
            {"id": "q11_m1", "type": "wrong_subcitation",
             "desc": "Cites Annex IV.2.a (development methods); hardware is Annex IV point 1(e).",
             "verify": {"present": ["1(e)"], "absent": []}},
            {"id": "q11_m2", "type": "missing_subcitation",
             "desc": "Should also reference Annex IV.2(c) (computational resources).",
             "verify": {"present": ["2(c)", "computational resources"], "absent": []}},
        ],
    },
    "q12": {
        "question": "Are AI systems intended for emotion recognition from biometric data always prohibited?",
        "verdict": "correct_substance_wrong_subcitation",
        "gold_refs": ["Article 5", "Annex III", "Article 50"],
        "gold_answer": (
            "No. Emotion recognition is prohibited only in workplaces and educational "
            "institutions under Article 5(1)(f), subject to a narrow medical or safety "
            "exception. Elsewhere it is high-risk under Annex III point 1(c) "
            "(biometrics) and triggers Article 50(3) transparency duties toward the "
            "natural persons exposed to the system."
        ),
        "expected_keywords": ["not always", "workplace", "education", "5(1)(f)", "high-risk", "50(3)"],
        "lexy_refs": ["Article 5.1.f", "Article 50", "Annex III.5", "Article 5", "Annex III"],
        "mistakes": [
            {"id": "q12_m1", "type": "wrong_subcitation",
             "desc": "Cites Annex III.5; emotion recognition is at Annex III point 1(c).",
             "verify": {"present": ["1(c)"], "absent": []}},
            {"id": "q12_m2", "type": "imprecise_subcitation",
             "desc": "Art 50 should be the precise 50(3).",
             "verify": {"present": ["50(3)"], "absent": []}},
        ],
    },
    "q13": {
        "question": "Is an AI that transcribes doctor–patient conversations prohibited? Or is it high-risk as per the use cases of Annex III of the AI Act?",
        "verdict": "correct_contradictory_citation",
        "gold_refs": ["Article 6", "Annex I", "Article 5", "Article 50"],
        "gold_answer": (
            "Transcribing doctor-patient conversations is neither prohibited under "
            "Article 5 nor listed as a high-risk use case in Annex III. It becomes "
            "high-risk under Article 6 only if deployed as a safety component of a "
            "medical device covered by Annex I (MDR or IVDR). Otherwise Article 50 "
            "transparency duties may apply where the system interacts with patients."
        ),
        "expected_keywords": ["not prohibited", "not", "Annex III", "safety component", "medical device", "Annex I", "Article 50"],
        "lexy_refs": ["Annex III.5", "Annex III", "Article 6", "Article 5", "Annex I"],
        "mistakes": [
            {"id": "q13_m1", "type": "contradictory_citation",
             "desc": "Cites Annex III.5 even though the answer says the system is NOT in Annex III.",
             "verify": {"present": [], "absent": []}, "ref_absent": []},
        ],
    },
    "q14": {
        "question": "We are a medical device manufacturer building an AI system to analyze X-rays to detect tumors. Is this system classified as high-risk, and what conformity assessment is required?",
        "verdict": "correct_rule_generic_application",
        "gold_refs": ["Article 6", "Annex I", "Article 43"],
        "gold_answer": (
            "Yes, it is high-risk under Article 6(1): an AI system that is a safety "
            "component of a medical device covered by Annex I (MDR/IVDR) is high-risk "
            "where the device requires third-party conformity assessment, which a "
            "tumour-detecting X-ray device does. Under Article 43(3) the AI Act "
            "conformity assessment is integrated into the MDR notified-body procedure "
            "as a single assessment, and the full Chapter III Section 2 obligations "
            "(Articles 9 to 15) apply."
        ),
        "expected_keywords": ["high-risk", "6(1)", "notified body", "43(3)", "MDR", "integrated", "conformity assessment"],
        "lexy_refs": ["Article 6", "Article 43", "Annex I", "Annex III", "Article 5", "Article 9", "Article 10", "Article 11", "Article 12", "Article 13"],
        "mistakes": [
            {"id": "q14_m1", "type": "generic_application",
             "desc": "States the rule but does not apply it to the X-ray case (device class, Art 43(3) integrated MDR assessment).",
             "verify": {"present": ["43(3)"], "absent": []}},
            {"id": "q14_m2", "type": "irrelevant_citation",
             "desc": "Cites Art 5 and Annex III, irrelevant to the Art 6(1)/Annex I scenario.",
             "verify": {"present": [], "absent": []}, "ref_absent": ["Article 5", "Annex III"]},
        ],
    },
    "q15": {
        "question": "Can a hospital use an AI system to sort patients based on their biometric data to determine priority for an experimental clinical trial?",
        "verdict": "half_right",
        "gold_refs": ["Article 5", "Annex III", "Article 6"],
        "gold_answer": (
            "It depends on the function. Annex III point 5(d) covers emergency triage "
            "and dispatch, not clinical-trial selection; trial selection may instead "
            "fall under Annex III point 5(a) (eligibility for essential healthcare "
            "services) or outside Annex III entirely, governed by the Medical Devices "
            "and Clinical Trials Regulations. Separately, it is prohibited under "
            "Article 5(1)(g) only if the biometric categorisation infers an attribute "
            "on the closed list: race, political opinions, trade-union membership, "
            "religious or philosophical beliefs, sex life or sexual orientation."
        ),
        "expected_keywords": ["5(a)", "5(d)", "clinical trial", "5(1)(g)", "closed list", "biometric categorisation"],
        "lexy_refs": ["Article 5.1.g", "Article 6", "Annex III", "Article 5", "Annex I"],
        "mistakes": [
            {"id": "q15_m1", "type": "wrong_subpoint",
             "desc": "Anchors on Annex III 5(d) (emergency triage); clinical-trial selection is not 5(d), likely 5(a) or outside Annex III.",
             "verify": {"present": ["5(a)"], "absent": []}},
            {"id": "q15_m2", "type": "imprecise",
             "desc": "Art 5(1)(g) conditional correct but does not name the closed list of sensitive attributes.",
             "verify": {"present": ["closed list"], "absent": []}},
        ],
    },
    "q16": {
        "question": "Our life sciences startup developed a general-purpose AI model trained on massive amounts of genomic data. What transparency obligations apply to us?",
        "verdict": "correct_substance_omissions",
        "gold_refs": ["Article 53", "Article 51", "Article 55"],
        "gold_answer": (
            "As a general-purpose AI model provider you must, under Article 53(1): keep "
            "technical documentation (Annex XI), provide downstream-provider information "
            "(Annex XII), implement a copyright policy, and publish a sufficiently "
            "detailed training-data summary. Whether the additional systemic-risk "
            "obligations of Article 55 apply turns on the Article 51 threshold, "
            "presumed at 10^25 FLOPs of cumulative training compute; a startup model "
            "typically falls below it, but that is the gating question."
        ),
        "expected_keywords": ["53(1)", "technical documentation", "copyright", "training-data summary", "51", "55", "systemic"],
        "lexy_refs": ["Article 53", "Article 113", "Article 53.1", "Article 51", "Article 55"],
        "mistakes": [
            {"id": "q16_m1", "type": "irrelevant_sentence",
             "desc": "Adds an Art 113 entry-into-force sentence unrelated to the question.",
             "verify": {"present": [], "absent": ["entry into force", "1 august 2024", "in force"]}},
            {"id": "q16_m2", "type": "omission",
             "desc": "Should name the Art 51 systemic-risk threshold (10^25 FLOPs) and Art 55 obligations as the gating question.",
             "verify": {"present": ["51", "systemic"], "absent": []}},
        ],
    },
    "q17": {
        "question": "We are a university lab developing an AI model exclusively for scientific research and development into new life science drugs. Does the AI Act apply to our model before it is released to the market?",
        "verdict": "correct",
        "gold_refs": ["Article 2"],
        "gold_answer": (
            "No. Article 2(6) excludes AI systems and models developed and used solely "
            "for scientific research and development, so the model is outside the Act "
            "while used only for that purpose and not placed on the market or put into "
            "service. The exclusion ends on market placement or putting into service, "
            "at which point the Act's obligations attach according to the model's risk "
            "classification; Article 2(8) separately preserves pre-market testing in "
            "real-world conditions."
        ),
        "expected_keywords": ["2(6)", "scientific research", "excludes", "market", "2(8)"],
        "lexy_refs": ["Article 2"],
        "mistakes": [
            {"id": "q17_m1", "type": "precision",
             "desc": "Could cite the precise Art 2(6) (R&D exclusion) and Art 2(8) (pre-market testing).",
             "verify": {"present": ["2(6)"], "absent": []}},
        ],
    },
    "q18": {
        "question": "We are developing a generative AI chatbot that will be deployed on a hospital website to answer general patient queries. What transparency obligations apply?",
        "verdict": "half_right_missing_classification",
        "gold_refs": ["Article 50"],
        "gold_answer": (
            "First classify it: a general patient-query chatbot is most likely "
            "limited-risk, not high-risk, so Article 13 high-risk transparency does not "
            "apply and Article 50 governs alone. Under Article 50(1) the provider must "
            "ensure each user is told they are interacting with an AI system, and under "
            "Article 50(2) any generated content must be marked in a machine-readable "
            "format. The hospital deploying a third-party chatbot is the deployer, so "
            "deployer duties such as Article 50(4) attach to it."
        ),
        "expected_keywords": ["limited-risk", "classify", "50(1)", "50(2)", "deployer", "not high-risk"],
        "lexy_refs": ["Article 13", "Article 50", "Annex III", "Annex I", "Article 6"],
        "mistakes": [
            {"id": "q18_m1", "type": "missing_classification",
             "desc": "Asserts cumulative Art 13 + Art 50 without classifying the chatbot; it is most likely limited-risk (Art 50 alone).",
             "verify": {"present": ["limited"], "absent": []}},
            {"id": "q18_m2", "type": "role_confusion",
             "desc": "Uses 'operator' for both provider and deployer duties; the hospital is the deployer.",
             "verify": {"present": ["deployer"], "absent": []}},
            {"id": "q18_m3", "type": "unaddressed_citation",
             "desc": "Cites Annex I and Art 6 but does not address them in the body.",
             "verify": {"present": [], "absent": []}, "ref_absent": ["Annex I"]},
        ],
    },
    "q19": {
        "question": "A pharmaceutical company wants to use an AI system to monitor the emotions and stress levels of their manufacturing line workers to improve efficiency. Is this allowed?",
        "verdict": "correct",
        "gold_refs": ["Article 5"],
        "gold_answer": (
            "No. Article 5(1)(f) prohibits AI systems that infer the emotions of "
            "workers in workplace settings, and deploying one to improve manufacturing "
            "efficiency falls squarely within the ban. The only carve-out is for "
            "systems placed on the market strictly for medical or safety reasons, such "
            "as fatigue detection to prevent accidents, which must be the primary "
            "purpose at market placement; efficiency improvement does not qualify."
        ),
        "expected_keywords": ["prohibited", "5(1)(f)", "workplace", "emotion", "medical", "safety"],
        "lexy_refs": ["Article 5"],
        "mistakes": [],
    },
    "q20": {
        "question": "Is an AI system intended to be used as a safety component in robotic surgery considered high-risk under the AI Act?",
        "verdict": "correct_rule_generic_application",
        "gold_refs": ["Article 6", "Annex I", "Article 14", "Article 72"],
        "gold_answer": (
            "Yes. A robotic-surgery AI safety component is part of a medical device "
            "that is typically Class IIb or III under MDR and requires notified-body "
            "conformity assessment, so it is high-risk under Article 6(1). Beyond the "
            "rule, real-time involvement in the surgical control loop engages the "
            "Article 14 human-oversight design requirements and layered post-market "
            "monitoring under AI Act Article 72 alongside MDR Article 83."
        ),
        "expected_keywords": ["high-risk", "6(1)", "notified body", "Class", "human oversight", "Article 14", "Article 72"],
        "lexy_refs": ["Article 6", "Annex I"],
        "mistakes": [
            {"id": "q20_m1", "type": "generic_application",
             "desc": "Generic medical-device rule; does not engage robotic-surgery specifics (Art 14 human oversight, Art 72 post-market).",
             "verify": {"present": ["14"], "absent": []}, "ref_present": ["Article 14", "Article 72"]},
        ],
    },
}


def question_ids() -> list[str]:
    return list(ANTIFRAGILE_GT.keys())
