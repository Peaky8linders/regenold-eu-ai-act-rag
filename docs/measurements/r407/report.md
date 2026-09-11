# r407-direct-bedrock-cohere-v4-pro — live hard-mode evaluation

- Rows: **110**
- Judge: `bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:r=3`
- Checkpoint: `evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl`
- Capture log: `docs\measurements\r406\direct-bedrock-capture.log`
- Method: reconstructed R388 rubric; three judge repetitions at temperature 0.1.
- Caveat: criteria and reference keys are reconstructed, not evaluator-published gold.

## Scorecard and uplift

| Axis | This run | Prior live | Uplift | 2026 frontier | Gap |
|---|---:|---:|---:|---:|---:|
| Answer correctness (loose) | 90.69% | 91.22% | -0.53 pp | 92.00% | -1.31 pp |
| Answer correctness (strict) | 81.82% | 83.64% | -1.82 pp | 84.80% | -2.98 pp |
| Answer conciseness | 84.42% | 83.85% | +0.57 pp | 71.80% | +12.62 pp |
| Reference correctness (loose) | 95.50% | 97.00% | -1.50 pp | 94.60% | +0.90 pp |
| Reference correctness (strict) | 74.83% | 75.17% | -0.33 pp | 74.10% | +0.73 pp |
| Reference conciseness | 55.93% | 54.73% | +1.20 pp | 58.50% | -2.57 pp |
| Regulatory tone | 100.00% | 100.00% | +0.00 pp | 100.00% | +0.00 pp |
| Response speed | 71.65% | 90.53% | -18.88 pp | 86.70% | -15.05 pp |
| Overall (geometric mean) | 80.67% | 83.27% | -2.60 pp | — | — |

## Operational diagnostics

- Mean answer length: **757.2 characters**
- Mean references: **2.818**
- Mean latency: **28.422 seconds**
- Reference-scored rows: **100**
- Rows missing persisted criterion remarks: **0**

## Per-question judge report

### rg_001 — 2/2 criteria

> Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?

References: `Article 11.1, Annex IV.1`

1. **PASS** — Yes
   - Judge: the answer states 'Yes' as its position, which matches the required verdict
2. **PASS** — Description of the hardware on which the AI system is intended to run (Annex IV.1.e)
   - Judge: the answer explicitly provides the substance by stating that Annex IV requires a description of the hardware on which the AI system is intended to run

Tone: **PASS** — Professional, neutral third-person register with clear structure and direct reference to relevant provisions.

Answer:

> Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).

### rg_002 — 2/2 criteria

> Does the obligation to indicate that deep-fakes are artificially generated apply when prosecuting a criminal offence?

References: `Article 50.4`

1. **PASS** — No
   - Judge: the answer clearly states 'No' as its position, matching the required verdict
2. **PASS** — Deep-fake disclosure exemption covers detection, prevention, investigation or prosecution of criminal offences
   - Judge: the answer states the substance that the disclosure obligation does not apply when use is authorised for detection, prevention, investigation or prosecution of criminal offences

Tone: **PASS** — one short sentence

Answer:

> No. Under Article 50(4), the deployer's duty to disclose that image, audio, or video content constituting a deep fake has been artificially generated or manipulated does not apply where the use is authorised by law to detect, prevent, investigate, or prosecute criminal offences. Absent that law-enforcement authorisation, the deployer must disclose that the content is a deep fake.

### rg_003 — 4/4 criteria

> When the intended use of an AI system is listed in Annex III of the EU AI Act, the AI system is automatically high-risk, isn't it? If not, can you explain when that is not the case?

References: `Annex III.6.d, Article 6.2, Article 49.3`

1. **PASS** — No
   - Judge: candidate answer states 'No' as the initial response, matching the required verdict
2. **PASS** — Exception applies where system does not pose significant risk of harm to health, safety or fundamental rights, including by not materially influencing outcome of decision making
   - Judge: candidate answer includes the condition about not posing significant risk of harm to health, safety or fundamental rights, including by not materially influencing decision making
3. **PASS** — Exception requires one of: narrow procedural task; improving result of previously completed human activity; detecting deviations from prior decision-making patterns without replacing/influencing human assessment; preparatory task to an Annex III assessment
   - Judge: candidate answer lists all four conditions specified in the criterion, using equivalent phrasing
4. **PASS** — Exception never applies (system is always high-risk) if it performs profiling of natural persons
   - Judge: candidate answer explicitly states that the system is always high-risk if it performs profiling of natural persons, regardless of other conditions

Tone: **PASS** — Professional, neutral tone with clear structure and coherent explanation of exceptions and conditions under Article 6(3).

Answer:

> No, an AI system whose intended use is listed in Annex III is not automatically high-risk. Under Article 6(3), such a system is not considered high-risk if it does not pose a significant risk of harm to health, safety or fundamental rights and meets one of four conditions: it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns without replacing or influencing human assessment, or performs a preparatory task to an Annex III use case. However, the system is always high-risk if it performs profiling of natural persons, regardless of the other conditions. The provider must document this self-assessment before placing the system on the market and register it in the EU database under Article 49(2).

### rg_004 — 4/4 criteria

> I have a medical device that has an AI system as a safety component. The medical device is classified "medium-risk" and undergoes a 3rd party conformity assessment. Is the AI system "medium risk" too? If yes, why? If not, why not?

References: `Article 6.1, Article 43.3, Annex I.11, Article 48.4`

1. **PASS** — Yes - high-risk (AI Act has no "medium-risk" category)
   - Judge: The answer clearly states that the AI system is high-risk and explains that the AI Act does not use 'medium-risk' categories.
2. **PASS** — Condition (a): AI system is safety component of a product covered by Annex I legislation (medical devices under Regulation (EU) 2017/745)
   - Judge: The answer states that the AI system is a safety component of a medical device covered by Annex I legislation, specifically Regulation (EU) 2017/745.
3. **PASS** — Condition (b): that product is required to undergo third-party conformity assessment
   - Judge: The answer explicitly notes that the medical device undergoes third-party conformity assessment, satisfying condition (b).
4. **PASS** — Both conditions cumulative under Article 6(1), irrespective of the device's own sectoral risk classification
   - Judge: The answer explains that both conditions under Article 6(1) are cumulative and that the classification as high-risk applies regardless of the device's sectoral risk classification.

Tone: **PASS** — Professional, neutral tone with clear, structured explanation that aligns with regulatory language and logic.

Answer:

> High-risk. An AI system that is a safety component of a medical device requiring third-party conformity assessment is classified as high-risk under Article 6(1), regardless of the device’s sectoral risk classification such as "medium-risk". The EU AI Act does not adopt sectoral risk labels like "low", "medium", or "high" from underlying legislation such as the MDR; instead, it establishes a binary classification where AI systems are either high-risk or not, based on fulfilling both conditions in Article 6(1): (a) the AI system is a safety component of, or itself a product covered by, Annex I legislation (including Regulation (EU) 2017/745 on medical devices), and (b) that product is required to undergo third-party conformity assessment. Since the medical device in question undergoes such assessment, the AI system qualifies as high-risk under Article 6(1). The conformity assessment for the AI system is integrated into the MDR procedure under Article 43(3), resulting in a single CE marking under Article 48.

### rg_005 — 3/3 criteria

> Does the EU AI Act explicitly requires to use explainable AI techniques such as LIME or SHAP to increase the trustworthiness of high-risk AI systems?

References: `Article 13.3, Article 14.4, Article 15.1`

1. **PASS** — No
   - Judge: candidate answer states 'No' as the position, matching the criterion
2. **PASS** — Article 13 requires sufficient transparency/interpretability for deployers, without naming a technique
   - Judge: candidate answer states that Article 13 requires transparency for deployers to interpret output, without naming specific techniques
3. **PASS** — Requirement is outcome-based and technology-neutral, leaving choice of method to the provider
   - Judge: candidate answer describes the requirement as technique-agnostic and leaves method choice to the provider, conveying technology-neutral, outcome-based approach

Tone: **PASS** — Professional, neutral, and self-contained explanation in clear regulatory prose without self-reference or hedging.

Answer:

> No, the EU AI Act mandates no specific explainable-AI technique such as LIME or SHAP, and Article 13 instead requires only that high-risk AI systems be sufficiently transparent for deployers to interpret their output. Article 14 requires effective human oversight, and Article 15 requires appropriate accuracy, robustness and cybersecurity. The Act is technique-agnostic, so the choice of any interpretability method is left to the provider.

### rg_006 — 3/3 criteria

> Does the EU AI Act apply to AI systems or AI models or both?

References: `Article 2.1.a, Article 3.1, Article 51.1`

1. **PASS** — Both AI systems and AI models
   - Judge: the answer states that Article 2(1)(a) covers both AI systems and general-purpose AI models
2. **PASS** — Art 2(1)(a): providers placing/putting into service AI systems
   - Judge: the answer explicitly mentions providers placing AI systems on the market or putting them into service
3. **PASS** — Art 2(1)(a): providers placing general-purpose AI models on the market
   - Judge: the answer explicitly mentions providers placing general-purpose AI models on the market

Tone: **PASS** — Professional, neutral third-person register with clear structure and coherent prose.

Answer:

> Article 2(1)(a) covers providers placing AI systems on the Union market or putting them into service, and providers placing general-purpose AI models on the market, irrespective of where the providers are established. AI systems are defined in Article 3(1), while general-purpose AI models are regulated separately under Chapter V (Articles 51 to 56), are defined in Article 3(63), and carry their own provider obligations with additional duties for models posing systemic risk.

### rg_007 — 3/3 criteria

> We want to deploy an AI system that performs biometric verification solely to confirm that a specific natural person is the person he or she claims to be. Is this system prohibited? Is it high-risk?

References: `Article 5.1.d, Article 6.2, Article 50.1, Annex III.1.a`

1. **PASS** — No, not prohibited
   - Judge: The answer states the system is not prohibited, which matches the criterion's verdict of 'No, not prohibited'.
2. **PASS** — No, not high-risk
   - Judge: The answer explicitly states the system is not high-risk, satisfying the criterion.
3. **PASS** — Falls within Annex III.1(a) biometric verification exclusion
   - Judge: The answer states that the system is excluded from remote biometric identification under Annex III.1(a) because it performs biometric verification solely to confirm identity, capturing the substance of the exclusion.

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> Not prohibited and not high-risk. A biometric verification system whose sole purpose is to confirm that a specific natural person is the person they claim to be is explicitly excluded from the definition of remote biometric identification systems under Annex III.1(a), and therefore does not fall under the high-risk classification of Article 6(2). The system is not among the eight prohibited practices listed in Article 5, including biometric categorisation under Article 5(1)(g) or real-time remote biometric identification under Article 5(1)(h), as it does not infer sensitive attributes or enable broad surveillance. Since the system is neither prohibited nor high-risk, it is subject only to the limited transparency obligations under Article 50(1) if it interacts directly with natural persons, requiring the provider to ensure users are informed they are interacting with an AI system.

### rg_008 — 4/4 criteria

> Are AI safety components within medical devices of MDR class IIa, IIb, or III considered to be high-risk according to the EU AI Act? Why?

References: `Article 6.1, Annex I.19`

1. **PASS** — Yes
   - Judge: The answer states 'Yes' as its unambiguous position, matching the required verdict.
2. **PASS** — Condition: AI system is a safety component of a product covered by Union harmonisation legislation listed in Annex I (the MDR)
   - Judge: The answer states that the AI system is a safety component of a product covered by the MDR, which is listed in Annex I, conveying the substance of the condition.
3. **PASS** — Condition: that product must undergo third-party (notified body) conformity assessment to be placed on the market (Article 6(1))
   - Judge: The answer explicitly notes that these devices require third-party conformity assessment involving a notified body, which satisfies the condition about third-party assessment under Article 6(1).
4. **PASS** — MDR classes IIa, IIb, III require notified-body conformity assessment, so both cumulative conditions are met
   - Judge: The answer explains that MDR classes IIa, IIb, and III require notified-body assessment and concludes that both conditions are met, capturing the cumulative nature of the criteria.

Tone: **PASS** — Professional, neutral tone with clear, structured explanation referencing relevant legal provisions without self-reference or hedging.

Answer:

> Yes, AI safety components within medical devices of MDR class IIa, IIb, or III are considered high-risk under Article 6(1) of the EU AI Act. This is because such devices are covered by Regulation (EU) 2017/745 (MDR), which is listed in Annex I, and these classes require third-party conformity assessment involving a notified body. Article 6(1) establishes that an AI system is high-risk if it is intended as a safety component of a product covered by Annex I legislation and that product is subject to third-party conformity assessment. Since MDR class IIa, IIb, and III devices meet both conditions, their AI safety components are classified as high-risk. The provider must therefore undergo a conformity assessment under Article 43(3) in accordance with the MDR’s procedures, including involvement of a notified body.

### rg_009 — 5/5 criteria

> What documentation does a provider of a high-risk AI system needs to keep available for the national competent authorities, and for how long?

References: `Article 18.1, Article 11.1, Article 17.1, Article 47.1, Article 19.1`

1. **PASS** — Technical documentation (Article 11)
   - Judge: candidate answer states the provider must keep technical documentation (Article 11) available
2. **PASS** — Quality management system documentation (Article 17)
   - Judge: candidate answer states the provider must keep quality management system documentation (Article 17) available
3. **PASS** — Notified body change documentation and decisions/other documents, where applicable
   - Judge: candidate answer states the provider must keep documentation concerning changes approved by notified bodies and decisions/other documents issued by them, where applicable
4. **PASS** — EU declaration of conformity (Article 47)
   - Judge: candidate answer states the provider must keep the EU declaration of conformity (Article 47) available
5. **PASS** — 10 years after the system is placed on the market or put into service
   - Judge: candidate answer states the documentation must be kept for ten years after the system is placed on the market or put into service

Tone: **PASS** — Professional, third-person tone with clear structure and complete sentences that directly address the regulatory requirements without self-reference or ambiguity.

Answer:

> Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.

### rg_010 — 5/5 criteria

> Which article of the EU AI Act governs human oversight measures?

References: `Article 14.4, Annex III`

1. **PASS** — Article 14
   - Judge: candidate answer states Article 14 governs human oversight measures
2. **PASS** — Design for effective human oversight during use
   - Judge: candidate answer states systems must be designed for effective oversight during use
3. **PASS** — Aim: prevent/minimise risks to health, safety, fundamental rights
   - Judge: candidate answer implies risk prevention by stating oversight is required for high-risk systems and measures are commensurate to risks
4. **PASS** — Measures built in by provider and/or implemented by deployer
   - Judge: candidate answer refers to measures commensurate to risks and context, indicating provider-built and deployer-implemented options
5. **PASS** — Overseers enabled to understand, monitor, interpret, override, and halt the system
   - Judge: candidate answer lists all key oversight capabilities: understand, monitor, interpret, override, and stop the system

Tone: **PASS** — Professional, neutral, and self-contained explanation in clear regulatory prose without self-reference or informality.

Answer:

> Article 14 governs human oversight measures for high-risk AI systems. High-risk AI systems must be designed to allow effective oversight by natural persons during use, with measures commensurate to the risks, autonomy and context of use. These measures must enable oversight actors to understand the system's capabilities and limitations, monitor its operation, remain aware of automation bias, correctly interpret outputs, decide to disregard or override outputs, and intervene or stop the system. For remote biometric identification systems under Annex III(1)(a), no action may be taken based on the system's output unless verified by at least two qualified natural persons, except where Union or national law deems this disproportionate for law enforcement, migration, border control or asylum authorities.

### rg_011 — 3/3 criteria

> What is the meaning and purpose of 'testing data' in the context of AI systems, and why is it important that it is not leaked during the training process?

References: `Article 3.32, Article 10.3`

1. **PASS** — Testing data is one of the training/validation/testing data sets under Article 10(1), used to check the high-risk AI system against its intended purpose after training and validation
   - Judge: candidate states testing data is used to check the system against its intended purpose after training and validation
2. **PASS** — It must meet the Article 10(3) quality criteria: relevant, sufficiently representative, to the best extent possible free of errors, complete, and with appropriate statistical properties for the intended purpose
   - Judge: candidate explicitly lists the Article 10(3) quality criteria and attributes them to that provision
3. **PASS** — Leakage of training data into the testing set destroys the set's independence, so it can no longer reliably verify Article 10(3) compliance and instead yields inflated, misleading accuracy that masks errors, biases or gaps
   - Judge: candidate explains that leakage destroys independence and leads to inflated, misleading accuracy that hides errors and biases

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference; logically ordered and actionable for a compliance professional.

Answer:

> Testing data is one of the training, validation and testing data sets required by Article 10(1); under Article 3(32) it provides an independent evaluation of the system to confirm its expected performance against the intended purpose, after training and validation and before the system is placed on the market. Under Article 10(3) those sets must be relevant, sufficiently representative, and to the best extent possible free of errors and complete in view of the intended purpose, with the appropriate statistical properties. If training data leaks into the testing set, the set loses that independence: it can no longer verify Article 10(3) compliance and instead yields inflated, misleading accuracy that masks errors, biases and gaps.

### rg_012 — 3/3 criteria

> What are the high-risk uses of AI systems listed under 'Administration of justice and democratic processes' cited in the EU AI Act?

References: `Annex III.8`

1. **PASS** — AI systems assisting a judicial authority (or on its behalf) in researching/interpreting facts and law and applying law to facts, or used similarly in alternative dispute resolution
   - Judge: candidate answer states the substance of judicial AI systems assisting in research, interpretation, and application of law to facts, including in alternative dispute resolution
2. **PASS** — AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote
   - Judge: candidate answer clearly states that AI systems intended to influence election outcomes or voting behaviour are included
3. **PASS** — Exclusion: does not cover AI systems whose output natural persons are not directly exposed to, e.g. tools organising/optimising/structuring political campaigns administratively or logistically
   - Judge: candidate answer explicitly notes the exclusion for tools used administratively or logistically in political campaigns where natural persons are not directly exposed to the output

Tone: **PASS** — Professional, neutral tone with clear structure and complete sentences that directly address the regulatory provisions without self-reference or ambiguity.

Answer:

> Annex III point 8 lists two high-risk use cases under administration of justice and democratic processes. Annex III point 8(a) covers AI systems intended to be used by a judicial authority, or on its behalf, to assist in researching and interpreting facts and the law and in applying the law to a concrete set of facts, or to be used similarly in alternative dispute resolution. Annex III point 8(b) covers AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, with a carve-out for tools that only organise, optimise or structure political campaigns from an administrative or logistical point of view.

### rg_013 — 5/5 criteria

> Under what conditions should providers of general-purpose AI models be subject to exceptions regarding transparency-related requirements, if any? And what do those exceptions not cover?

References: `Article 53.2, Article 51.1, Article 55.2, Annex XI.2`

1. **PASS** — Yes, exceptions exist
   - Judge: The answer states that exceptions exist by describing the conditions under which certain obligations do not apply.
2. **PASS** — Condition: model released under free and open-source licence allowing access, usage, modification and distribution
   - Judge: The answer specifies that the model must be released under a free and open-source licence allowing access, usage, modification, and distribution.
3. **PASS** — Condition: parameters (weights, architecture info, usage info) made publicly available
   - Judge: The answer states that parameters, including weights, architecture information, and usage information, must be made publicly available.
4. **PASS** — Exception covers only points (a) and (b) of Article 53(1), not (c)/(d)
   - Judge: The answer explicitly notes that the exception covers only points (a) and (b) of Article 53(1), and not (c) or (d), which remain applicable.
5. **PASS** — Exception does not apply to general-purpose AI models with systemic risk
   - Judge: The answer clearly states that the exception does not apply to general-purpose AI models with systemic risk, which remain subject to full obligations.

Tone: **PASS** — Professional, neutral third-person register with logically structured and actionable information.

Answer:

> The exceptions to the GPAI transparency-related obligations are set out in Article 53(2). The Article 53(1)(a) duty to draw up and keep up-to-date the technical documentation of the model (Annex XI) and the Article 53(1)(b) duty to provide information and documentation to downstream providers (Annex XII) do not apply to providers that release the model under a free and open-source licence allowing access, usage, modification and distribution, where the model parameters, including the weights, and information on the model architecture and usage, are made publicly available. The exception does not cover the remaining Article 53(1) obligations: the policy to comply with Union copyright law (Article 53(1)(c)) and the publicly available, sufficiently detailed summary of the training content (Article 53(1)(d)) apply regardless of the licence. The exception also does not apply to general-purpose AI models with systemic risk (Article 53(2), second subparagraph), which remain subject to the full Article 53 obligations together with the Article 55 systemic-risk duties.

### rg_014 — 4/4 criteria

> Which AI systems used in education or vocational training should be classified as high-risk according to the EU AI Act?

References: `Annex III.3.c, Article 6.2, Article 49.3`

1. **PASS** — Access, admission, or assignment to educational/vocational training institutions at all levels
   - Judge: candidate answer states systems used to determine access or admission to educational and vocational training institutions are high-risk
2. **PASS** — Evaluating learning outcomes, including to steer the learning process
   - Judge: candidate answer includes evaluation of learning outcomes, including steering the learning process, as high-risk
3. **PASS** — Assessing the appropriate level of education an individual will receive or can access
   - Judge: candidate answer explicitly mentions assessing the appropriate level of education an individual will receive or can access as high-risk
4. **PASS** — Monitoring/detecting prohibited student behaviour during tests
   - Judge: candidate answer states systems monitoring and detecting prohibited student behaviour during tests are high-risk

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information for a compliance context.

Answer:

> High-risk AI systems in education or vocational training are those that fall under the specific use cases listed in Annex III(3) of the EU AI Act. These include: (a) systems used to determine access or admission to educational and vocational training institutions; (b) systems used to evaluate learning outcomes, including when those outcomes are used to steer the learning process; (c) systems used to assess the appropriate level of education an individual will receive or be able to access; and (d) systems used to monitor and detect prohibited behaviour of students during tests. Article 6(2) classifies these systems as high-risk. However, under Article 6(3), an Annex III system is not high-risk if it poses no significant risk of harm and meets one of four conditions: it performs a narrow procedural task, improves a previously completed human activity, detects decision-making patterns without replacing human assessment, or performs a preparatory task. Notably, if the system performs profiling of natural persons, it is always classified as high-risk. Providers of such systems must document their self-assessment and register the system in the EU database under Article 49(2).

### rg_015 — 2/3 criteria

> What obligations, if any, does the EU AI Act set in place for AI systems that interact directly with natural persons? What exceptions, if any, apply?

References: `Article 50.1, Article 50.3`

1. **PASS** — Obligation: providers must design/develop the system so natural persons are informed they are interacting with an AI system
   - Judge: The answer states that providers must design systems so natural persons are informed they are interacting with an AI system, as required by Article 50(1).
2. **FAIL** — Exception: not required where obvious to a reasonably well-informed, observant and circumspect person, given the circumstances and context of use
   - Judge: The answer does not mention the exception for when it is obvious to a reasonably well-informed, observant and circumspect person, given the circumstances and context of use.
3. **PASS** — Exception: AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to safeguards for third parties' rights and freedoms — unless available for the public to report a criminal offence
   - Judge: The answer correctly states the exception for AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to safeguards, unless available for public crime reporting.

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> Limited risk. AI systems that interact directly with natural persons are subject to the transparency obligations in Article 50, which apply regardless of the system's risk tier. Deployers of emotion recognition or biometric categorisation systems must inform exposed persons, and deployers of deep fakes must disclose the artificial generation or manipulation, with exceptions for artistic, creative, satirical or fictional works where disclosure must not hamper enjoyment. The Article 50(1) provider obligation does not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to safeguards, unless those systems are available to the public to report crimes. The Article 50(3) deployer obligation does not apply where such systems are used for criminal offence detection under legal authorisation with safeguards.

### rg_016 — 2/2 criteria

> What are the administrative fines for non-compliance with the prohibition of the AI practices?

References: `Article 99.3, Article 5.1.g`

1. **PASS** — EUR 35,000,000 or 7% of total worldwide annual turnover for the preceding financial year, whichever is higher
   - Judge: the candidate answer states the fine amount as EUR 35 million or 7% of total worldwide annual turnover, whichever is higher, which matches the substance of the criterion
2. **PASS** — Applies to non-compliance with Article 5 prohibited AI practices
   - Judge: the candidate answer explicitly links the fines to non-compliance with prohibited AI practices under Article 5, satisfying the criterion's substance

Tone: **PASS** — one short sentence

Answer:

> Administrative fines for non-compliance with the prohibited AI practices under Article 5 are up to EUR 35 million or 7% of the offender’s total worldwide annual turnover, whichever is higher, under Article 99(3). These fines apply to violations of the eight prohibited practices, including subliminal manipulation, exploitation of vulnerabilities, social scoring, criminal-risk profiling, untargeted facial-image scraping, emotion recognition in workplaces and educational institutions, biometric categorisation by sensitive attributes, and real-time remote biometric identification in public spaces by law enforcement (excluding narrow exceptions).

### rg_017 — 3/3 criteria

> How does Annex II relate to prohibited uses of AI systems?

References: `Annex II, Article 5.1.h, Article 27.1, Article 49.3`

1. **PASS** — Annex II lists criminal offences (does not itself prohibit anything)
   - Judge: The answer states that Annex II specifies a list of criminal offences, clarifying it does not itself prohibit anything but serves as a qualifying list for an exception.
2. **PASS** — Referenced in Article 5(1)(h)(iii) as basis for one exception to the Article 5(1)(h) prohibition on 'real-time' remote biometric identification in public spaces for law enforcement
   - Judge: The answer explicitly links Annex II to Article 5(1)(h)(iii) as the basis for the exception to the prohibition on real-time remote biometric identification in public spaces for law enforcement purposes.
3. **PASS** — Exception (localising/identifying a suspect) applies only if the offence is listed in Annex II and punishable by a custodial sentence/detention order of max at least four years
   - Judge: The answer includes the condition that the offence must be punishable by at least four years’ custodial sentence, which matches the criterion's requirement.

Tone: **PASS** — Professional, neutral tone with clear, structured explanation of regulatory conditions and limitations.

Answer:

> Annex II specifies the list of criminal offences that qualify for the narrow exception permitting real-time remote biometric identification by law enforcement under Article 5(1)(h)(iii), including terrorism, trafficking in human beings, sexual exploitation of children, illicit trafficking in narcotic drugs or weapons, murder, kidnapping, rape, environmental crime, organised crime, and participation in a criminal organisation, provided the offence is punishable by at least four years’ custodial sentence in the relevant Member State. This list directly enables the use of otherwise prohibited AI systems for locating suspects of serious crimes, but only after fulfilling strict safeguards under Article 5(2)-(4), including prior fundamental rights impact assessment under Article 27, registration in the EU database under Article 49, and prior judicial or independent administrative authorisation. The use must be strictly necessary and proportionate, limited to what is strictly required in terms of time, geography and personal scope, and no adverse decision may be based solely on the system’s output. Member States may authorise such use in national law under Article 5(5), but must notify the Commission and may not introduce less restrictive rules than those set out in the Regulation.

### rg_018 — 4/4 criteria

> Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?

References: `Annex III.7.b, Article 7.1, Article 97`

1. **PASS** — Yes
   - Judge: The answer states 'Yes, the European Commission may amend Annex III...' which clearly affirms the possibility of amendment.
2. **PASS** — Condition: AI intended to be used in any of the areas listed in Annex III
   - Judge: The answer specifies that the AI systems 'must be intended for use in one of the areas already listed in Annex III,' which captures the substance of the first condition in Article 7(1)(a).
3. **PASS** — Condition: posed risk is equal or greater than those already referred to in Annex III
   - Judge: The answer states the risk must be 'equivalent to or greater than the risks posed by existing Annex III systems,' which matches the substance of Article 7(1)(b) regarding the level of risk.
4. **PASS** — Both conditions must apply ("and" clause)
   - Judge: The answer explicitly refers to 'two cumulative conditions' and uses 'and,' indicating that both conditions must be satisfied together, which reflects the 'and' clause in Article 7(1).

Tone: **PASS** — Professional, neutral, and self-contained explanation using precise regulatory language without meta-commentary or hedging.

Answer:

> Yes, the European Commission may amend Annex III to add or modify high-risk AI use-cases under Article 7(1), provided two cumulative conditions are met: the AI systems must be intended for use in one of the areas already listed in Annex III, and they must pose a risk to health, safety, or fundamental rights that is equivalent to or greater than the risks posed by existing Annex III systems. The Commission must assess the latter condition using the criteria in Article 7(2), including the system’s intended purpose, extent of use, nature of data processed, autonomy, severity and reversibility of harm, and availability of redress. Any amendment is subject to the delegated act procedure under Article 97, requiring consultation with Member State experts, adoption by the Commission, and potential veto by the European Parliament or Council within a three-month scrutiny period. The Commission may also remove use-cases from Annex III under Article 7(3) if they no longer pose significant risks and deletion does not reduce overall protection levels.

### rg_019 — 4/4 criteria

> What is a deep fake according to the EU AI Act?

References: `Article 3.60, Article 50.4`

1. **PASS** — AI-generated or manipulated content
   - Judge: the candidate answer states that deep fake means AI-generated or manipulated content, which matches the substance of criterion 1
2. **PASS** — Image, audio, or video
   - Judge: the candidate answer specifies image, audio or video content, which matches the substance of criterion 2
3. **PASS** — Resembles existing persons, objects, places, entities or events
   - Judge: the candidate answer includes that the content resembles existing persons, objects, places, entities or events, which matches the substance of criterion 3
4. **PASS** — Falsely appears authentic or truthful to a person
   - Judge: the candidate answer states the content would falsely appear to a person to be authentic or truthful, which matches the substance of criterion 4

Tone: **PASS** — one short sentence

Answer:

> ‘deep fake’ means AI-generated or manipulated image, audio or video content that resembles existing persons, objects, places, entities or events and would falsely appear to a person to be authentic or truthful;

### rg_020 — 3/3 criteria

> Should market surveilance authorities be provided with remote access to documentations and data sets used to develop a high-risk AI system?

References: `Article 74.12`

1. **PASS** — Yes
   - Judge: answer states 'Yes' and confirms remote access may be provided, matching the required verdict
2. **PASS** — Full access to documentation and to training, validation and testing data sets, granted by providers, limited to what is necessary for the authority's tasks
   - Judge: answer includes full access to documentation and data sets, granted by providers, and limits it to what is necessary for the authority's tasks
3. **PASS** — Remote access (e.g. via API or other technical means) permitted only "where appropriate" and subject to security safeguards
   - Judge: answer specifies remote access is permitted only where appropriate and subject to security safeguards, citing APIs and other technical means

Tone: **PASS** — Professional, neutral, and self-contained explanation in regulatory prose without meta-commentary or informality.

Answer:

> Yes, market surveillance authorities may be provided with remote access to the documentation and data sets used to develop a high-risk AI system, where relevant and limited to what is necessary for their tasks. Article 74.12 mandates that providers grant market surveillance authorities full access to the technical documentation and to the training, validation, and testing data sets used for the development of high-risk AI systems, including, where appropriate and subject to security safeguards, through APIs or other technical means enabling remote access. Article 74.13 further clarifies that access to the source code is a separate and narrower power, available only upon a reasoned request and only when data- and documentation-based verification has been exhausted or proved insufficient.

### rg_021 — 3/4 criteria

> If a provider of a high-risk AI system confirms that the system achieves an appropriate level of accuracy, robustness, and cybersecurity at the time of development, then no further action is required by the provider on these aspects in the future. Correct?

References: `Article 15.1, Article 13.3, Article 9`

1. **PASS** — No
   - Judge: candidate answer clearly states 'No' as the position
2. **PASS** — Must perform consistently throughout lifecycle, including resilience to errors/faults/inconsistencies (Art. 15(1),(4))
   - Judge: candidate answer states the system must perform consistently throughout lifecycle, covering robustness and resilience
3. **PASS** — Cybersecurity resilience against third-party exploitation is ongoing, not one-time (Art. 15(5))
   - Judge: candidate answer refers to ongoing obligations including testing and verification, implying continuous cybersecurity resilience
4. **FAIL** — Accuracy levels/metrics must be declared in instructions of use (Art. 15(3))
   - Judge: candidate mentions documentation of accuracy but does not state that accuracy levels/metrics must be declared in instructions of use

Tone: **PASS** — Professional, neutral, and self-contained explanation using precise references to the EU AI Act without self-reference or hedging.

Answer:

> No. Article 15(1) requires high-risk AI systems to perform consistently in terms of accuracy, robustness, and cybersecurity throughout their lifecycle. Article 9(6) and Article 9(8) mandate ongoing testing to identify and address risks, ensuring continued compliance. Article 13(3)(b)(ii) obliges providers to document the expected level of accuracy and any circumstances that may affect it, which must be updated as needed. Providers must therefore maintain and verify these aspects continuously, not just at the time of development.

### rg_022 — 4/4 criteria

> What are all the risk categories in the EU AI Act?

References: `Article 5, Article 6, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56`

1. **PASS** — Unacceptable risk - prohibited practices (Article 5)
   - Judge: candidate answer states that unacceptable-risk practices are prohibited under Article 5
2. **PASS** — High risk - Article 6, referencing Annex I (product safety) and Annex III (use cases)
   - Judge: candidate answer identifies high-risk systems under Article 6 and references both Annex I and Annex III
3. **PASS** — Limited risk - transparency obligations (Article 50)
   - Judge: candidate answer states that limited-risk systems have transparency duties under Article 50
4. **PASS** — Minimal or no risk - no mandatory obligations, voluntary codes of conduct (Article 95)
   - Judge: candidate answer mentions minimal-risk systems have no mandatory obligations and notes voluntary codes under Article 95

Tone: **PASS** — Professional, neutral, and structurally coherent with clear delineation of risk categories and corresponding provisions.

Answer:

> The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems avoid Chapter III high-risk requirements but retain Article 4 AI literacy duties, with voluntary codes under Article 95, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.

### rg_023 — 2/2 criteria

> Does "systemic risk" apply to AI systems or general purpose AI models or both?

References: `Article 51.1, Article 55.1, Article 53.2`

1. **PASS** — Applies to general-purpose AI models only (Article 51), not to AI systems
   - Judge: The answer states that systemic risk applies to general-purpose AI models, not to AI systems, which matches the substance of the criterion.
2. **PASS** — Systemic risk classification applies only to general-purpose AI models (Article 51), not to AI systems
   - Judge: The answer clearly limits systemic risk classification to general-purpose AI models and distinguishes it from the high-risk regime for AI systems, satisfying the criterion's substance.

Tone: **PASS** — Professional, neutral third-person register with clear structure and coherent explanation of legal distinctions.

Answer:

> Systemic risk applies to general-purpose AI models, not to AI systems. Under Article 51(1), a general-purpose AI model is classified as a model with systemic risk where it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks; under Article 51(2) a model is presumed to have high impact capabilities where the cumulative computation used for its training exceeds 10^25 floating point operations. The Commission may also designate a model on the basis of the Annex XIII criteria. A model classified as having systemic risk then carries the additional Article 55 obligations: model evaluation including adversarial testing, assessment and mitigation of systemic risks at Union level, serious-incident reporting, and adequate cybersecurity. The high-risk regime for AI systems under Articles 6 and Annex III is a separate classification and does not use the systemic-risk concept.

### rg_024 — 3/3 criteria

> Are AI systems that fall under one of the areas of Annex III, but not falling within a use-case within such areas, considered high-risk?

References: `Annex III.6.d, Article 6.2`

1. **PASS** — No
   - Judge: the answer clearly states 'No' as its position, matching the required verdict
2. **PASS** — High-risk requires falling within a specific enumerated use case listed in Annex III, not merely within the broader area grouping those use cases
   - Judge: the answer explains that high-risk status requires correspondence with a specific enumerated use-case, not just the broader area
3. **PASS** — Annex III areas are organisational headings; the operative trigger is the individual use-case description
   - Judge: the answer identifies that the areas in Annex III are organizational and that the actual trigger is the specific use-case listed under them

Tone: **PASS** — Professional, neutral tone with clear structure and coherent explanation aligned with regulatory language.

Answer:

> No. An AI system falling under one of the eight areas of Annex III is not automatically high-risk unless it corresponds to a specific use-case listed under that area. Article 6(2) classifies AI systems as high-risk only if they fall within one of the enumerated use-cases in Annex III, not merely because they operate in a broad area covered by the annex. Additionally, Article 6(3) provides a derogation: even listed Annex III systems are not high-risk if they perform a narrow procedural task, improve a prior human activity, detect decision-making patterns without influencing outcomes, or perform a preparatory task, unless they profile natural persons, in which case they are always high-risk. The provider must document this assessment under Article 6(4) if relying on the derogation.

### rg_025 — 4/4 criteria

> Can an operator that is not a provider according to the EU AI Act, for example a deployer, take actions on a given high-risk AI system such that it can be effectively seen as a provider by the authorities? If yes, what kind of action would result in such an outcome?

References: `Article 25.1, Article 16`

1. **PASS** — Yes
   - Judge: The answer explicitly states 'Yes' as the first word and maintains that position throughout.
2. **PASS** — Putting own name/trademark on a high-risk AI system already on the market/in service (Article 25(1)(a))
   - Judge: The answer states the substance of putting one's name or trademark on a high-risk AI system already on the market or in service.
3. **PASS** — Substantial modification to a high-risk AI system already on the market/in service that remains high-risk under Article 6 (Article 25(1)(b))
   - Judge: The answer clearly describes making a substantial modification to a high-risk AI system that remains high-risk under Article 6.
4. **PASS** — Modifying the intended purpose of a non-high-risk (incl. general-purpose) AI system such that it becomes high-risk under Article 6 (Article 25(1)(c))
   - Judge: The answer explains modifying the intended purpose of a non-high-risk AI system, including general-purpose, so that it becomes high-risk under Article 6.

Tone: **PASS** — Professional, neutral third-person register with clear structure and coherent prose.

Answer:

> Yes. Under Article 25(1), a distributor, importer, deployer or other third party is deemed to be the provider of a high-risk AI system, and takes on the provider obligations in Article 16, in any of three cases. First, if it puts its name or trademark on a high-risk AI system already placed on the market (Article 25(1)(a)). Second, if it makes a substantial modification to a high-risk AI system that remains high-risk (Article 25(1)(b)). Third, if it modifies the intended purpose of an AI system, including a general-purpose AI system, so that it becomes high-risk (Article 25(1)(c)). In each of these three cases the operator assumes the provider obligations in Article 16, and the initial provider is no longer considered the provider of that specific system under Article 25(2).

### rg_026 — 3/3 criteria

> If I have an AI system that is high-risk because listed in the use cases of Annex III, and change it to a different use case that is not in Annex I or III, does it stay high-risk due to its historical provenance?

References: `Annex III.6.d, Annex I.5, Article 6.2`

1. **PASS** — No
   - Judge: the answer clearly states 'No' as the position, matching the criterion
2. **PASS** — High-risk status under Article 6 depends on the AI system's current intended purpose/use case, not its prior classification
   - Judge: the answer states that classification depends on current use case, not prior classification
3. **PASS** — If the new use case falls outside both Annex I and Annex III, neither condition in Article 6(1) or 6(2) is met, so the system is not high-risk
   - Judge: the answer explains that if the new use case is outside Annex I and III, the system no longer meets Article 6(1) or 6(2) criteria

Tone: **PASS** — Professional, neutral tone with clear, coherent structure that directly addresses the regulatory question without self-reference or hedging.

Answer:

> No. A high-risk classification under Annex III is contingent on the system's current use case, not its historical function. Under Article 6(2), an AI system is classified as high-risk only if it falls within one of the use cases listed in Annex III. If the system is reconfigured to a use case not listed in Annex I or III, it no longer meets the criteria for high-risk classification under the EU AI Act. Article 6(3) further provides that an Annex III system is not high-risk if it does not pose a significant risk of harm and meets one of the four conditions outlined in that provision, such as performing a preparatory task. The system's historical provenance does not affect its current risk classification.

### rg_027 — 4/4 criteria

> How are AI systems intended to influence the outcome of an election or referendum classified, and what exception is given for certain campaign-related tools?

References: `Article 6.3, Article 50.1, Annex III.8`

1. **PASS** — High-risk classification under Annex III, point 8(b)
   - Judge: candidate states that AI systems under Annex III, point 8(b) are high-risk
2. **PASS** — Covers AI systems influencing election/referendum outcome or voters' voting behaviour
   - Judge: candidate specifies that the systems influence election/referendum outcomes or voters' voting behaviour
3. **PASS** — Exception: AI systems whose output natural persons are not directly exposed to are excluded
   - Judge: candidate clearly states the exception for systems not directly exposed to natural persons
4. **PASS** — Example given: tools organising/optimising/structuring political campaigns administratively or logistically
   - Judge: candidate provides the exact example of administrative or logistical campaign tools

Tone: **PASS** — Professional, neutral third-person register with clear structure and precise reference to legal provisions.

Answer:

> Under Annex III point 8(b), AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, are high-risk under Article 6(2). Annex III point 8(b) itself excludes systems to whose output natural persons are not directly exposed, such as tools used only to organise, optimise or structure political campaigns from an administrative or logistical point of view, which therefore fall outside this high-risk category.

### rg_028 — 4/4 criteria

> According to Article 1, what is the objective of the EU AI Act?

References: `Article 1`

1. **PASS** — Improve functioning of the internal market
   - Judge: the candidate answer explicitly states the objective to improve the functioning of the internal market
2. **PASS** — Promote uptake of human-centric and trustworthy AI
   - Judge: the candidate answer explicitly states the objective to promote uptake of human-centric and trustworthy AI
3. **PASS** — Ensure high level of protection of health, safety and fundamental rights (incl. democracy, rule of law, environment) against harmful effects of AI systems
   - Judge: the candidate answer explicitly states the objective to ensure a high level of protection of health, safety, and fundamental rights, including democracy, rule of law, and environmental protection, against harmful effects of AI systems
4. **PASS** — Support innovation
   - Judge: the candidate answer explicitly states the objective of supporting innovation

Tone: **PASS** — one short sentence

Answer:

> The objective of the EU AI Act, as stated in Article 1, is to improve the functioning of the internal market and promote the uptake of human-centric and trustworthy artificial intelligence (AI), while ensuring a high level of protection of health, safety, and fundamental rights enshrined in the Charter, including democracy, the rule of law, and environmental protection, against the harmful effects of AI systems in the Union and supporting innovation.

### rg_029 — 3/3 criteria

> Under the EU AI Act, which specific AI systems are explicitly listed as high-risk because they make decisions in critical life- and health-related situations involving emergency calls and triage?

References: `Article 6.2, Annex III.5.d`

1. **PASS** — AI systems that evaluate and classify emergency calls by natural persons
   - Judge: the candidate answer explicitly states that AI systems evaluating and classifying emergency calls by natural persons are listed as high-risk
2. **PASS** — AI systems used to dispatch, or establish priority in dispatching, emergency first response services (police, firefighters, medical aid)
   - Judge: the candidate answer explicitly includes AI systems used to dispatch or establish priority in dispatching emergency first response services as high-risk
3. **PASS** — Emergency healthcare patient triage systems
   - Judge: the candidate answer directly names emergency healthcare patient triage systems as explicitly listed high-risk AI systems

Tone: **PASS** — Professional, neutral, and self-contained explanation in clear regulatory prose without meta-commentary or fragmentation.

Answer:

> Under Annex III point 5(d), AI systems intended to evaluate and classify emergency calls by natural persons, or to be used to dispatch or to establish priority in the dispatching of emergency first response services (including by police, firefighters and medical aid), as well as emergency healthcare patient triage systems, are explicitly listed as high-risk. They fall within the 'essential private and public services' category of the eight Annex III high-risk areas and are classified as high-risk through the Annex III route of Article 6(2), which treats any system falling within a listed use case as high-risk. That classification triggers the Chapter III Section 2 obligations for high-risk systems.

### rg_030 — 1/1 criteria

> Under Regulation (EU) 2024/1689, as part of their supervisory role for an AI regulatory sandbox, compliance with which specific Article must the market surveillance authority verify?

References: `Article 76.2, Article 60.4.b`

1. **PASS** — Article 60
   - Judge: The candidate answer explicitly states that market surveillance authorities must verify compliance with Article 60 as part of their supervisory role for an AI regulatory sandbox, which matches the substance of the criterion.

Tone: **PASS** — one short sentence

Answer:

> Market surveillance authorities must verify compliance with Article 60 when performing their supervisory role for an AI regulatory sandbox, as specified in Article 76(2). This includes ensuring that the real-world testing plan has been submitted and approved by the relevant authority, and that all conditions for testing in real-world conditions are met.

### rg_031 — 4/4 criteria

> Is an AI system used to structure or deduplicate information for a use case listed in Annex III considered high-risk?

References: `Article 6.3.a, Article 49.2, Annex III.7.b`

1. **PASS** — No
   - Judge: candidate answer states 'No' as the verdict, matching the required position
2. **PASS** — Falls under narrow procedural task derogation, Article 6(3), first subparagraph, point (a)
   - Judge: candidate answer states that structuring or deduplicating is a narrow procedural task and falls under Article 6(3) first subparagraph point (a) derogation
3. **PASS** — Exception: remains high-risk if system performs profiling of natural persons
   - Judge: candidate answer explicitly states the derogation does not apply where the system profiles natural persons
4. **PASS** — Provider must document the assessment before placing on market/putting into service (Article 6(4))
   - Judge: candidate answer states provider must document the assessment before market placement or putting into service under Article 6(4)

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information in well-ordered prose.

Answer:

> No. Structuring or deduplicating information is a narrow procedural task, so the system falls under the Article 6(3) first subparagraph point (a) derogation and is not high-risk, provided it poses no significant risk of harm to health, safety or fundamental rights and does not materially influence the outcome of decision making; the other limbs are (b) improving the result of a previously completed human activity, (c) detecting decision-making patterns or deviations without replacing or influencing the human assessment, and (d) performing a preparatory task, and the derogation never applies where the system profiles natural persons. Under Article 6(4) a provider relying on the derogation must document the assessment before the system is placed on the market or put into service, and register it under Article 49(2).

### rg_032 — 3/3 criteria

> Is an AI system used to detect decision-making patterns or deviations for a use case listed in Annex III considered high-risk?

References: `Article 6.3, Annex III`

1. **PASS** — No, not by default
   - Judge: the answer states that such an AI system is not automatically considered high-risk, which matches the 'No, not by default' criterion
2. **PASS** — Condition: not meant to replace or influence the previously completed human assessment, without proper human review
   - Judge: the answer includes the condition that the system must not be meant to replace or influence the prior human assessment without proper human review
3. **PASS** — Exception: always high-risk if system performs profiling of natural persons
   - Judge: the answer explicitly states that the system is always high-risk if it performs profiling of natural persons

Tone: **PASS** — Professional, neutral tone with clear reference to specific articles and conditions, logically structured for regulatory interpretation.

Answer:

> Not automatically. Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.

### rg_033 — 4/4 criteria

> Regarding the European Artificial Intelligence Board: (1) Who designates its members? (2) How long is the term? How many times is the term renewable? (3) must members represent stakeholder interests or act impartially/objectively? (4) what voting threshold is required to adopt the Board's rules of procedure (is a simple 50%+1 majority enough)?

References: `Article 65.5`

1. **PASS** — Members designated by their Member State
   - Judge: states that members are designated by their Member State
2. **PASS** — Term is three years, renewable once
   - Judge: specifies three-year term renewable once
3. **PASS** — No stakeholder representation requirement; must safeguard objectivity/impartiality
   - Judge: explains no stakeholder representation and requirement for objectivity/impartiality
4. **PASS** — Two-thirds majority required to adopt rules of procedure (simple majority not enough)
   - Judge: states two-thirds majority required, simple majority not enough

Tone: **PASS** — one short sentence

Answer:

> The European Artificial Intelligence Board (Article 65) has one representative per Member State, each serving a three-year term renewable once under Article 65(3). Under Article 65(4) each is their Member State's single contact point rather than an independent stakeholder appointee, while Article 65(7) requires the Board to safeguard the objectivity and impartiality of its activities. Its rules of procedure are adopted by a two-thirds majority under Article 65(5), so a simple majority is not sufficient.

### rg_034 — 4/4 criteria

> Under the EU AI Act, what jurisdiction does the Court of Justice of the European Union have over Commission decisions fixing fines on providers of general-purpose AI models, and what can the Court do with the fine?

References: `Article 101, Article 99.4, Article 91.3, Article 93.3, Article 92.1`

1. **PASS** — Unlimited jurisdiction to review Commission decisions fixing a fine
   - Judge: The answer states the Court has 'unlimited jurisdiction to review Commission decisions fixing fines,' which matches the substance of criterion 1.
2. **PASS** — Court may cancel the fine
   - Judge: The answer explicitly states the Court 'may cancel the fine,' which matches the substance of criterion 2.
3. **PASS** — Court may reduce the fine
   - Judge: The answer explicitly states the Court 'may reduce the fine,' which matches the substance of criterion 3.
4. **PASS** — Court may increase the fine
   - Judge: The answer explicitly states the Court 'may increase the fine,' which matches the substance of criterion 4.

Tone: **PASS** — Professional, neutral tone with clear, well-structured prose that directly addresses the jurisdiction and powers of the Court without self-reference or hedging.

Answer:

> The Court of Justice of the European Union has unlimited jurisdiction to review Commission decisions fixing fines on providers of general-purpose AI models under Article 101(5). It may cancel, reduce or increase the fine imposed. This judicial review applies to fines levied for intentional or negligent breaches of Chapter V obligations, failure to comply with information requests under Article 91, non-compliance with measures under Article 93, or refusal to grant access to a model for evaluation under Article 92. The Commission’s fining power under Article 101(1) is capped at EUR 15 000 000 or 3% of total worldwide annual turnover, whichever is higher.

### rg_035 — 2/3 criteria

> Consider the situation in which a market surveillance authority (MSA) determines that an AI system, originally classified as non-high-risk by the provider, is in fact high-risk. Does the provider need to recall and suspend the use of the system without undue delay, or does the MSA provide a timeframe within which the provider can take corrective actions? Or does this depend on the gravity of the situation?

References: `Article 80.2, Article 6.2, Article 79.2`

1. **PASS** — MSA sets a compliance/corrective-action period for the provider, rather than an automatic without-undue-delay recall/suspension duty
   - Judge: The answer states the MSA prescribes a period for corrective action rather than imposing an automatic recall or suspension.
2. **PASS** — Provider must bring the system into compliance and take corrective action within that MSA-prescribed period (Article 80(2) and 80(4))
   - Judge: The answer specifies the provider must bring the system into compliance within the MSA-prescribed period, citing Article 80(2).
3. **FAIL** — Failure to comply within that period triggers fines under Article 99 (and Article 79(5)-(9) applies), not gravity-based variation of the timeframe
   - Judge: The answer claims the period must reflect the gravity of non-compliance, implying gravity affects the timeframe, which contradicts the criterion that failure to comply triggers fines regardless of gravity.

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information in compliance with regulatory prose standards.

Answer:

> The provider does not need to recall or suspend the system without undue delay; instead, the market surveillance authority (MSA) must first carry out an evaluation under Article 80(1) if the system was classified as non-high-risk under the Article 6(3) derogation. Where the MSA finds the system is in fact high-risk, it shall without undue delay require the provider to take corrective actions to bring the system into compliance within a period prescribed by the authority, as set out in Article 80(2). The authority may impose provisional measures under Article 79(5) only if the provider fails to act adequately within that timeframe. The prescribed period must be proportionate to the risk, reflecting the gravity of the non-compliance.

### rg_036 — 1/3 criteria

> Under the EU AI Act, what presumption applies when a high-risk AI system is trained and tested on data that reflects the specific geographical, behavioural, contextual or functional setting in which it is intended to be used?

References: `Article 42.1, Article 10.4`

1. **FAIL** — Presumed compliant with Article 10(3) representativeness/quality requirement for that setting
   - Judge: The candidate answer refers to Article 10(4), not Article 10(3); the criterion requires a statement about presumed compliance with the representativeness/quality requirement in Article 10(3), which is not addressed.
2. **PASS** — Presumption is limited to the extent required by the intended purpose
   - Judge: The answer states the presumption applies 'to the extent that the data sets account for the characteristics or elements particular to the intended setting, as required by the system's purpose,' which captures the limitation based on intended purpose.
3. **FAIL** — Not an exemption from other Article 10 obligations (e.g., bias examination/mitigation)
   - Judge: The candidate answer does not state that the presumption does not exempt the system from other Article 10 obligations, such as bias examination or mitigation; it only mentions compliance with Article 10(4) without clarifying that other requirements still apply.

Tone: **PASS** — Professional, neutral tone with clear reference to the relevant article and condition; logically structured and actionable.

Answer:

> Article 42(1) presumes that high-risk AI systems trained and tested on data reflecting the specific geographical, behavioural, contextual, or functional setting in which they are intended to be used comply with the relevant data-governance requirements of Article 10(4). This presumption applies to the extent that the data sets account for the characteristics or elements particular to the intended setting, as required by the system's purpose.

### rg_037 — 0/5 criteria

> When registering a high-risk AI system in the EU database under the EU AI Act, what specific information must the provider submit? List the required items.

References: `Article 49.4, Annex VIII.12, Article 71.5, Annex III.7.b`

1. **FAIL** — Registration confined to secure, non-public section of EU database (Article 71)
   - Judge: The answer mentions the database is established under Article 71 but does not state it is confined to a secure, non-public section.
2. **FAIL** — Annex VIII Section A points 1-10, excluding 6, 8 and 9
   - Judge: The answer omits points 6, 8, and 9 from Section A but does not explicitly state they are excluded; it only lists included items, not the full scope of Section A minus those points.
3. **FAIL** — Annex VIII Section B points 1-5, 8 and 9
   - Judge: The answer does not mention any information from Annex VIII Section B points 1-5, 8, or 9.
4. **FAIL** — Annex VIII Section C points 1-3
   - Judge: The answer does not mention Annex VIII Section C points 1-3.
5. **FAIL** — Annex IX points 1, 2, 3 and 5
   - Judge: The answer does not mention Annex IX points 1, 2, 3, or 5.

Tone: **PASS** — Professional, neutral third-person register with well-structured, actionable prose aligned with regulatory guidelines.

Answer:

> Providers must submit the information listed in Section A of Annex VIII to register a high-risk AI system in the EU database under Article 49(1). This includes the provider’s name, address and contact details; where applicable, the authorised representative’s details; the AI system’s trade name and identifying reference; a description of the intended purpose, components and functions; a basic description of the system’s inputs and operating logic; the system’s status (on market, in service, etc.); the type, number and expiry date of the conformity assessment certificate; a scanned copy of that certificate; and a copy of the EU declaration of conformity. Electronic instructions for use must also be provided, except for systems in the areas of law enforcement, migration, asylum and border control listed in Annex III points 1, 6 and 7. The database, established under Article 71, is managed by the Commission and contains personal data only as necessary for registration.

### rg_038 — 4/4 criteria

> Under the EU AI Act, what is an "AI regulatory sandbox"? Provide the definition elements (what it is, who sets it up, for whom it is intended, to do what, for how long).

References: `Article 3.55, Article 57.5, Article 1, Article 4`

1. **PASS** — Controlled environment established by a national competent authority (or jointly with other Member States, or by the EDPS for Union bodies)
   - Judge: the answer states a controlled framework set up by a competent authority, which matches the substance of a controlled environment established by a national competent authority or jointly with others
2. **PASS** — Intended for providers or prospective providers of AI systems
   - Judge: the answer explicitly mentions providers or prospective providers of AI systems as the intended participants
3. **PASS** — Purpose: fosters innovation and facilitates development, training, testing and validation of innovative AI systems (may include supervised real-world testing)
   - Judge: the answer includes development, training, validation, and testing of innovative AI systems, including real-world conditions, which captures the stated purpose
4. **PASS** — Time-limited, prior to market placement/putting into service, pursuant to a specific sandbox plan agreed with the competent authority
   - Judge: the answer specifies 'for a limited time' and 'pursuant to a sandbox plan', which conveys the time-limited nature and requirement of a pre-agreed plan before market placement

Tone: **PASS** — one short sentence

Answer:

> ‘AI regulatory sandbox’ means a controlled framework set up by a competent authority which offers providers or prospective providers of AI systems the possibility to develop, train, validate and test, where appropriate in real-world conditions, an innovative AI system, pursuant to a sandbox plan for a limited time under regulatory supervision;

### rg_039 — 3/3 criteria

> Under the EU AI Act, what transparency obligation applies to deployers when they use an AI system to generate or manipulate text for the purpose of informing the public on matters of public interest, and what are the two exceptions where this obligation does not apply?

References: `Article 50.4`

1. **PASS** — Deployers must disclose that the text has been artificially generated or manipulated
   - Judge: candidate states deployers must disclose artificially generated or manipulated text
2. **PASS** — Exception 1: use authorised by law to detect, prevent, investigate or prosecute criminal offences
   - Judge: candidate states the exception for use authorised by law for criminal offences
3. **PASS** — Exception 2: AI-generated content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for the publication
   - Judge: candidate states the exception involving human review and editorial responsibility

Tone: **PASS** — one short sentence

Answer:

> Under Article 50(4), a deployer that uses an AI system to generate or manipulate text published to inform the public on matters of public interest must disclose that the text has been artificially generated or manipulated. Under Article 50(4), that disclosure duty does not apply in two cases: first, where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences; and second, where the AI-generated content has undergone a process of human review or editorial control and a natural or legal person holds editorial responsibility for the publication of the content.

### rg_040 — 2/2 criteria

> Under the EU AI Act, when a high-risk AI system is found to conform with the requirements, what information must the Union technical documentation assessment certificate contain?

References: `Article 44.1, Annex VII.4`

1. **PASS** — Language: drawn up in a language easily understood by the relevant authorities of the Member State where the notified body is established
   - Judge: the candidate answer states the certificate must be drawn up in a language easily understood by the relevant authorities of the Member State where the notified body is established, which matches the substance of the criterion
2. **PASS** — Validity period stated: not exceeding five years (Annex I systems) or four years (Annex III systems)
   - Judge: the candidate answer specifies that the validity period may not exceed five years for Annex I systems and four years for Annex III systems, conveying the required limits

Tone: **PASS** — Professional, neutral, and self-contained explanation with clear structure and no meta-commentary.

Answer:

> Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system. Under Article 44(1) the certificate must be drawn up in a language which can be easily understood by the relevant authorities in the Member State in which the notified body is established, and under Article 44(2) it is valid for the period it indicates, which may not exceed five years for AI systems covered by Annex I and four years for AI systems covered by Annex III.

### rg_041 — 3/3 criteria

> Under the EU AI Act, is there a simplified way for SMEs (including startups) to provide the technical documentation for high-risk AI systems, and who must accept it for conformity assessment?

References: `Article 11.1, Annex IV.2`

1. **PASS** — Yes
   - Judge: the answer states 'Yes' as the position, which matches the required verdict
2. **PASS** — AI Office develops a simplified technical documentation form for SMEs/microenterprises, including start-ups, covering the Annex IV elements
   - Judge: the answer states that the Commission is required to establish a simplified form for small and micro enterprises, which conveys the substance that the AI Office (acting under the Commission) develops the form
3. **PASS** — The notified body assessing conformity of the high-risk AI system must accept that simplified form
   - Judge: the answer explicitly states that the notified body must accept the simplified form when used by an SME

Tone: **PASS** — one short sentence

Answer:

> Yes. Under Article 11(1), SMEs, including start-ups, may provide the technical documentation elements set out in Annex IV in a simplified manner, using a simplified form the Commission is required to establish for the needs of small and micro enterprises. Where an SME opts to use that form, the notified body performing the conformity assessment must accept it.

### rg_042 — 4/4 criteria

> Under the EU AI Act, must an employer inform affected workers and workers' representatives before putting into service or using a high-risk AI system in the workplace?
> If so, should possibly specific rules or procedures be followed to provide this information?

References: `Article 26.7`

1. **PASS** — Yes
   - Judge: the answer states 'Yes' as the verdict, matching the required position
2. **PASS** — Timing: before putting into service or using the system at the workplace
   - Judge: the answer specifies the timing as 'before putting a high-risk AI system into service or using it at the workplace'
3. **PASS** — Recipients: workers' representatives and affected workers
   - Judge: the answer identifies both workers' representatives and affected workers as recipients
4. **PASS** — Procedure: follow applicable Union/national law and practice on informing workers, where applicable (no separate free-standing procedure)
   - Judge: the answer states that information must be provided in accordance with applicable Union and national law and practice, where applicable, and does not suggest a separate procedure

Tone: **PASS** — one short sentence

Answer:

> Yes. Under Article 26(7), a deployer that is an employer must, before putting a high-risk AI system into service or using it at the workplace, inform the workers' representatives and the affected workers that they will be subject to the use of that high-risk AI system. Under Article 26(7), that information must be provided, where applicable, in accordance with the rules and procedures laid down in Union and national law and practice on the information of workers and their representatives.

### rg_043 — 6/6 criteria

> Under Article 10(5) of the EU AI Act, when may a provider of a high-risk AI system process special categories of personal data for bias detection and correction, and what key safeguards/conditions must be met?

References: `Article 10.5`

1. **PASS** — Only where strictly necessary for bias detection/correction under Art 10(2)(f)-(g), and cannot be effectively achieved with other data (incl. synthetic/anonymised)
   - Judge: answer states processing is allowed only when strictly necessary and cannot be effectively fulfilled with other data, including synthetic or anonymised
2. **PASS** — Technical re-use limitations plus state-of-the-art security/privacy-preserving measures, including pseudonymisation
   - Judge: answer includes technical limitations on re-use and state-of-the-art security measures, including pseudonymisation
3. **PASS** — Strict, documented access controls limited to authorised persons under confidentiality obligations, with no transmission/transfer/access by other parties
   - Judge: answer specifies strict, documented access controls limited to authorised persons under confidentiality obligations and prohibits transmission or access by other parties
4. **PASS** — Deletion once bias corrected or retention period ends, whichever is first
   - Judge: answer states data must be deleted once bias is corrected or retention period ends, whichever comes first
5. **PASS** — Processing records document necessity and why other data would not suffice
   - Judge: answer notes records must include reasons why processing was strictly necessary and why other data would not suffice
6. **PASS** — Additional to, not a substitute for, obligations under GDPR, EUDPR and the Law Enforcement Directive
   - Judge: answer explicitly states the conditions are in addition to, not a substitute for, GDPR, EUDPR and Law Enforcement Directive obligations

Tone: **PASS** — Professional, neutral tone with clear, structured exposition of conditions and safeguards under Article 10(5).

Answer:

> Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. These conditions apply in addition to, and not instead of, Regulation (EU) 2016/679, Regulation (EU) 2018/1725 and Directive (EU) 2016/680. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict controls and documentation of access so that only authorised persons under appropriate confidentiality obligations can reach the data (c); the data are not transmitted, transferred or otherwise accessed by other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).

### rg_044 — 4/4 criteria

> Under the EU AI Act, what specific information must a provider/prospective provider submit (and keep up to date) regarding testing of a high-risk AI system in real-world conditions outside an AI regulatory sandbox?

References: `Article 60.4.c, Article 13.3, Annex IX.2, Annex III.7.b, Article 49.4`

1. **PASS** — Real-world testing plan submitted to (and approved by) the market surveillance authority of the Member State of testing
   - Judge: The answer states that a real-world testing plan must be submitted to and approved by the market surveillance authority of the Member State where testing occurs.
2. **PASS** — Registration of the testing with a Union-wide unique single identification number
   - Judge: The answer explicitly mentions registration with a Union-wide unique single identification number.
3. **PASS** — General rule: registration under Article 71(4) with information specified in Annex IX
   - Judge: The answer refers to registration under Article 71(4) with information specified in Annex IX as the general rule.
4. **PASS** — Exceptions: Annex III points 1, 6, 7 (law enforcement/migration/asylum/border control) register in secure non-public EU database section per Article 49(4)(d); Annex III point 2 systems register per Article 49(5)
   - Judge: The answer identifies the exceptions for Annex III points 1, 6, 7 (law enforcement/migration/asylum/border control) registering in the secure non-public section per Article 49(4)(d), and implies the separate treatment for point 2 by omission while correctly stating the general rule.

Tone: **PASS** — Professional, neutral, and well-structured response with clear enumeration of obligations under the relevant articles, suitable for a regulatory compliance context.

Answer:

> A provider or prospective provider of a high-risk AI system must submit and maintain a real-world testing plan to the market surveillance authority in the Member State where the testing is to be conducted (Article 60.4.a). This plan must be approved by the authority, with tacit approval assumed if no response is received within 30 days, unless national law prohibits this (Article 60.4.b). Additionally, the provider must register the testing in the EU database with a Union-wide unique single identification number and the information specified in Annex IX, unless the system falls under Annex III points 1, 6, or 7, in which case registration occurs in a secure non-public section under Article 49(4) (Article 60.4.c). If the testing involves cooperation with deployers or prospective deployers, the provider must ensure they are informed of all relevant aspects and provided with instructions for use under Article 13, and an agreement must be concluded specifying roles and responsibilities (Article 60.4.h). The provider must also ensure informed consent from test subjects, including the right to withdraw without detriment, and implement safeguards for data transfers to third countries (Article 60.4.e, 60.4.g). The testing must not pose significant risks to health, safety, or fundamental rights, and any serious incidents must be reported to the national market surveillance authority (Article 60.7). Finally, the provider must notify the authority of the testing’s suspension, termination, or final outcomes (Article 60.8).

### rg_045 — 4/4 criteria

> Under the EU AI Act, if a deployer has reason to believe that the use of a high-risk AI system may present a risk, what must the deployer do, and whom must the deployer inform?

References: `Article 79.2, Article 26.5`

1. **PASS** — Inform the provider or distributor
   - Judge: The answer states the deployer must inform the provider or distributor.
2. **PASS** — Inform the relevant market surveillance authority
   - Judge: The answer states the deployer must inform the relevant market surveillance authority.
3. **PASS** — Suspend use of the system
   - Judge: The answer states the deployer must suspend use of the system.
4. **PASS** — All actions taken without undue delay
   - Judge: The answer specifies that the actions must be taken without undue delay.

Tone: **PASS** — Professional, neutral tone with clear, structured prose that aligns with regulatory guidance format.

Answer:

> Where a deployer has reason to believe that the use of a high-risk AI system may present a risk within the meaning of Article 79(1), it must immediately suspend use and inform both the provider or distributor and the relevant market surveillance authority without undue delay. If the deployer identifies a serious incident, it must first inform the provider, then the importer or distributor and the relevant market surveillance authorities. The deployer must also monitor the system’s operation based on the instructions for use and retain automatically generated logs under its control for at least six months under Article 26(6). This obligation does not apply to sensitive operational data of law enforcement deployers.

### rg_046 — 1/6 criteria

> Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information.

References: `Article 13.3`

1. **FAIL** — Provider and, where applicable, authorised representative identity/contact details
   - Judge: The candidate answer does not mention provider or authorised representative identity and contact details.
2. **PASS** — Characteristics, capabilities and performance limitations (intended purpose, accuracy/robustness/cybersecurity levels, foreseeable risks, explainability capabilities, performance for specific groups, input data specifications)
   - Judge: The answer includes all listed sub-elements of characteristics, capabilities, and performance limitations, using different phrasing but conveying the substance.
3. **FAIL** — Pre-determined changes to the system and its performance
   - Judge: The candidate answer omits any reference to pre-determined changes to the system and its performance.
4. **FAIL** — Human oversight measures under Article 14
   - Judge: The answer does not mention human oversight measures under Article 14 or technical measures to facilitate interpretation by deployers.
5. **FAIL** — Computational/hardware resources needed, expected lifetime, and maintenance/care measures
   - Judge: The answer does not include computational/hardware resources, expected lifetime, or maintenance/care measures.
6. **FAIL** — Description of logging mechanisms under Article 12, where relevant
   - Judge: The answer does not mention a description of logging mechanisms under Article 12.

Tone: **PASS** — Professional, neutral third-person register with well-structured, actionable prose listing all required information categories in logical order.

Answer:

> The provider must supply instructions for use containing the following categories of information: the intended purpose of the high-risk AI system, the level of accuracy including its metrics, robustness and cybersecurity against which the system has been tested and validated and any known or foreseeable circumstances affecting that level, any known or foreseeable circumstances related to use in accordance with the intended purpose or reasonably foreseeable misuse that may lead to risks to health, safety or fundamental rights, where applicable, technical capabilities and characteristics to explain the system’s output, when appropriate, performance regarding specific persons or groups on which the system is intended to be used, when appropriate, specifications for input data or other relevant information on training, validation and testing datasets, and where applicable, information enabling deployers to interpret the output and use it appropriately. These requirements are specified in Article 13(3)(b)(i) to (vii).

### rg_047 — 3/3 criteria

> Under the EU AI Act, what actions must a provider take when it considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity with the Regulation?

References: `Article 20.1, Article 16, Article 79.2, Article 44.3`

1. **PASS** — Immediately take necessary corrective action: bring into conformity, withdraw, disable, or recall, as appropriate
   - Judge: candidate states the requirement to immediately take corrective actions to bring into conformity, withdraw, disable, or recall as appropriate
2. **PASS** — Inform distributors of the system concerned
   - Judge: candidate states the requirement to inform distributors
3. **PASS** — Where applicable, inform deployers, authorised representative and importers accordingly
   - Judge: candidate states the requirement to inform deployers, authorised representatives, and importers accordingly

Tone: **PASS** — Professional, neutral, and self-contained explanation in regulatory prose with clear structure and no meta-commentary.

Answer:

> Providers of high-risk AI systems that consider or have reason to consider that a system placed on the market or put into service is not in conformity must immediately take corrective actions to bring it into conformity, withdraw it, disable it, or recall it as appropriate under Article 20(1). They must inform distributors, deployers, authorised representatives, and importers accordingly. Where the system presents a risk within the meaning of Article 79(1), the provider must investigate the causes, in collaboration with the deployer if applicable, and immediately notify the relevant market surveillance authority and, where relevant, the notified body that issued the certificate under Article 44, providing details of the non-compliance and any corrective actions taken under Article 20(2). These obligations are part of the provider’s broader duties under Article 16(j) to act on non-conformity and demonstrate compliance to competent authorities upon reasoned request under Article 16(k).

### rg_048 — 3/3 criteria

> Under Regulation (EU) 2024/1689, what is the definition of (a) a "conformity assessment body" and (b) "conformity assessment"?

References: `Article 3.21`

1. **PASS** — Conformity assessment body: a body that performs third-party conformity assessment activities
   - Judge: the candidate answer states that a conformity assessment body performs third-party conformity assessment activities
2. **PASS** — Conformity assessment body: activities include testing, certification and inspection
   - Judge: the candidate answer specifies that the activities include testing, certification, and inspection
3. **PASS** — Conformity assessment: the process of demonstrating whether the Chapter III, Section 2 requirements for a high-risk AI system have been fulfilled
   - Judge: the candidate answer states that conformity assessment is the process of demonstrating whether the Chapter III, Section 2 requirements for a high-risk AI system have been fulfilled

Tone: **PASS** — one short sentence

Answer:

> (a) A "conformity assessment body" is defined in Article 3(21) as a body that performs third-party conformity assessment activities, including testing, certification, and inspection. (b) "Conformity assessment" is defined in Article 3(20) as the process of demonstrating whether the requirements set out in Chapter III, Section 2 relating to a high-risk AI system have been fulfilled.

### rg_049 — 3/3 criteria

> Under the EU AI Act (Regulation (EU) 2024/1689) Article 95, who may draw up codes of conduct, and which bodies must encourage and facilitate their drawing up?

References: `Article 95.3`

1. **PASS** — Codes of conduct may be drawn up by individual providers or deployers of AI systems, by organisations representing them, or both
   - Judge: the answer states that codes may be drawn up by individual providers or deployers or by organisations representing them, which matches the substance of criterion 1
2. **PASS** — May involve interested stakeholders and their representative organisations, including civil society and academia
   - Judge: the answer explicitly mentions involvement of interested stakeholders such as civil society and academia
3. **PASS** — The AI Office and the Member States must encourage and facilitate the drawing up of codes of conduct
   - Judge: the answer clearly states that the AI Office and Member States must encourage and facilitate the drawing up of codes of conduct

Tone: **PASS** — one short sentence

Answer:

> Codes of conduct may be drawn up by individual providers or deployers of AI systems, or by organisations representing them, including with the involvement of interested stakeholders such as civil society organisations and academia (Article 95.3). The AI Office and the Member States are responsible for encouraging and facilitating the drawing up of such codes (Article 95.1).

### rg_050 — 2/2 criteria

> Under the EU AI Act, which AI systems in the financial services area are classified as high-risk under Annex III(5)(b), and what explicit exceptions are listed?

References: `Article 6.3.d, Annex III.5.b`

1. **PASS** — AI systems evaluating creditworthiness or establishing credit score of natural persons
   - Judge: the candidate answer states that AI systems evaluating creditworthiness or establishing credit score of natural persons are classified as high-risk under Annex III(5)(b)
2. **PASS** — Exception: AI systems used for detecting financial fraud
   - Judge: the candidate answer explicitly notes the exception for AI systems used solely for detecting financial fraud

Tone: **PASS** — Professional, neutral tone with clear structure and coherent prose suitable for regulatory guidance.

Answer:

> High-risk. AI systems intended to evaluate the creditworthiness of natural persons or establish their credit score are classified as high-risk under Annex III(5)(b) when used in the financial services area, pursuant to Article 6(2). The explicit exception under Annex III(5)(b) excludes AI systems used solely for the purpose of detecting financial fraud from this high-risk classification. Such systems are not automatically high-risk if they perform only a narrow procedural task, improve a previously completed human activity, detect decision-making patterns without replacing human assessment, or perform a preparatory task, provided they do not profile natural persons, as specified in Article 6(3).

### rg_051 — 2/3 criteria

> Under the EU AI Act, what must a provider established outside the EU do in order to place a high-risk AI system on the Union market?

References: `Article 22.3, Article 9.10, Annex IV.2, Article 43.1, Article 13.3`

1. **PASS** — Appoint an authorised representative established in the Union, by written mandate
   - Judge: candidate states the provider must appoint an authorised representative established in the Union by written mandate
2. **PASS** — Must occur prior to making the system available on the Union market
   - Judge: candidate states the appointment must occur before placing the system on the market
3. **FAIL** — Representative empowered per Article 22(3) tasks (verify conformity documentation, retain records 10 years, provide information/log access to authorities, cooperate with authorities, handle registration)
   - Judge: candidate mentions record retention and cooperation with authorities but does not state all tasks listed in Article 22(3), such as verifying conformity documentation or providing log access

Tone: **PASS** — Professional, neutral third-person register with logically structured and actionable information.

Answer:

> A provider established outside the EU must appoint, by written mandate, an authorised representative established in the Union before placing a high-risk AI system on the market, as required by Article 22. The provider must ensure the system complies with the high-risk obligations of Articles 9 to 15, including a risk management system (Article 9), data governance (Article 10), technical documentation per Annex IV (Article 11), automatic logging (Article 12), transparency and instructions for use (Article 13), human oversight (Article 14), and accuracy and cybersecurity (Article 15). The provider must also establish a quality management system (Article 17), undergo conformity assessment (Article 43), draw up the EU declaration of conformity (Article 47), affix the CE marking (Article 48), and register the system in the EU database (Article 49). The authorised representative must keep the declaration of conformity, technical documentation, and contact details available for 10 years and cooperate with national authorities (Article 22.3).

### rg_052 — 6/6 criteria

> Under the EU AI Act, what minimum elements must a provider's quality management system (QMS) for high-risk AI systems include? List the required elements.

References: `Article 9.10, Article 17.1`

1. **PASS** — Regulatory compliance strategy incl. conformity assessment and modification management
   - Judge: The answer includes 'a strategy for regulatory compliance' which covers conformity assessment and modification management as required by Article 17(1)(a).
2. **PASS** — Design, development, quality control and verification techniques/procedures
   - Judge: The answer mentions 'techniques and procedures for design and development' and implicitly covers quality control and verification through reference to design and development processes listed in Article 17(1)(b) and (c).
3. **PASS** — Examination, test and validation procedures and their frequency
   - Judge: The answer refers to 'examination and test procedures', which corresponds to examination, test, and validation procedures and their frequency as required in Article 17(1)(d).
4. **PASS** — Data management procedures across data lifecycle
   - Judge: The answer explicitly includes 'data management systems', covering the full data lifecycle as required under Article 17(1)(f).
5. **PASS** — Article 9 risk management system and Article 72 post-market monitoring system
   - Judge: The answer directly references both the 'risk management system under Article 9' and 'post-market monitoring', satisfying the requirement to include both systems as per Article 17(1)(g) and (h).
6. **PASS** — Record-keeping and accountability framework for management/staff
   - Judge: The answer includes 'record-keeping systems' and 'an accountability framework', which correspond to the requirements in Article 17(1)(k) and (m).

Tone: **PASS** — Professional, neutral, and self-contained explanation structured around legal provisions without self-reference or informality.

Answer:

> A provider's quality management system for high-risk AI systems must include a strategy for regulatory compliance, techniques and procedures for design and development, examination and test procedures, technical specifications, data management systems, the risk management system under Article 9, post-market monitoring, incident reporting procedures, communication handling with national authorities, record-keeping systems, resource management, and an accountability framework (Article 17(1)). The implementation must be proportionate to the provider’s size while ensuring the required level of protection (Article 17(2)). Providers subject to sectoral Union law on quality management systems may integrate the required aspects into those existing systems (Article 17(3)). Financial institutions subject to Union financial services law are deemed to fulfil the obligation if they comply with their internal governance rules, except for the requirements on risk management, post-market monitoring, and incident reporting (Article 17(4)).

### rg_053 — 4/4 criteria

> Under the EU AI Act, what additional obligations apply to providers of a general-purpose AI model that is classified as a model with systemic risk?

References: `Article 53.1, Article 55.1, Annex XI.2, Annex XII.2, Article 56.2`

1. **PASS** — Perform state-of-the-art model evaluation including documented adversarial testing to identify/mitigate systemic risks
   - Judge: The answer states the requirement to perform model evaluation with adversarial testing to identify and mitigate systemic risks, using state-of-the-art methods.
2. **PASS** — Assess and mitigate possible Union-level systemic risks, including their sources
   - Judge: The answer explicitly mentions assessing and mitigating possible systemic risks at Union level, including their sources.
3. **PASS** — Track, document and report serious incidents and corrective measures to the AI Office/national competent authorities without undue delay
   - Judge: The answer includes tracking, documenting, and reporting serious incidents and corrective measures to the AI Office and national authorities without undue delay.
4. **PASS** — Ensure adequate cybersecurity protection for the model and its physical infrastructure
   - Judge: The answer clearly states the obligation to ensure adequate cybersecurity protection for the model and its physical infrastructure.

Tone: **PASS** — Professional, neutral tone with logically structured and actionable obligations clearly delineated.

Answer:

> Providers of a general-purpose AI model with systemic risk must comply with the baseline obligations under Article 53, technical documentation per Annex XI, downstream provider information per Annex XII, a copyright policy, and a public training-data summary, and in addition face four enhanced obligations under Article 55. These additional obligations are: (a) perform model evaluation using standardised protocols and tools reflecting the state of the art, including conducting and documenting adversarial testing to identify and mitigate systemic risks; (b) assess and mitigate possible systemic risks at Union level, including their sources, arising from the model’s development, market placement, or use; (c) keep track of, document, and report without undue delay to the AI Office and, as appropriate, national competent authorities, relevant information about serious incidents and possible corrective measures; (d) ensure an adequate level of cybersecurity protection for both the model and its physical infrastructure. Providers may rely on codes of practice under Article 56 to demonstrate compliance with these Article 55 obligations until harmonised standards are published.

### rg_054 — 4/4 criteria

> Under the EU AI Act, what are the four grounds on which non-compliance with the Act may be alleged (as listed in Article 79(6))?

References: `Article 79.6, Article 5.1.h, Article 50`

1. **PASS** — Non-compliance with prohibition of AI practices under Article 5
   - Judge: the candidate answer explicitly states non-compliance with the prohibition of AI practices under Article 5
2. **PASS** — Failure of high-risk AI system to meet Chapter III, Section 2 requirements
   - Judge: the candidate answer explicitly states failure of a high-risk AI system to meet requirements in Chapter III, Section 2
3. **PASS** — Shortcomings in harmonised standards/common specifications under Articles 40-41
   - Judge: the candidate answer explicitly states shortcomings in harmonised standards or common specifications under Articles 40 and 41
4. **PASS** — Non-compliance with Article 50
   - Judge: the candidate answer explicitly states non-compliance with Article 50

Tone: **PASS** — Professional, neutral tone with clear, well-structured prose that directly answers the question in regulatory terms without self-reference or informality.

Answer:

> The four grounds on which non-compliance with the EU AI Act may be alleged, as listed in Article 79(6), are: (a) non-compliance with the prohibition of the AI practices referred to in Article 5; (b) a failure of a high-risk AI system to meet the requirements set out in Chapter III, Section 2; (c) shortcomings in the harmonised standards or common specifications referred to in Articles 40 and 41 conferring a presumption of conformity; and (d) non-compliance with Article 50. These grounds must be included in the notification by the market surveillance authority when provisional measures are taken against a non-compliant AI system.

### rg_055 — 3/3 criteria

> Under the EU AI Act, in which specific situations may law enforcement use 'real-time' remote biometric identification in publicly accessible spaces for law-enforcement purposes (i.e., the exceptions to the prohibition)? List the permitted objectives.

References: `Article 5.1.h, Annex II, Article 27.1, Article 49.4`

1. **PASS** — Targeted search for victims of abduction, trafficking, sexual exploitation, or missing persons
   - Judge: answer states the targeted search for victims of abduction, trafficking, sexual exploitation, or missing persons
2. **PASS** — Prevention of specific, substantial and imminent threat to life/physical safety, or genuine terrorist attack threat
   - Judge: answer includes prevention of specific, substantial and imminent threat to life/physical safety and genuine terrorist attack threat
3. **PASS** — Localisation/identification of a suspect for investigation, prosecution, or executing a penalty for an Annex II offence punishable by at least 4 years custodial sentence/detention order
   - Judge: answer specifies localisation/identification of a suspect for an Annex II offence punishable by at least four years' custodial sentence

Tone: **PASS** — Professional, neutral, and self-contained explanation in regulatory prose with clear structure and no meta-commentary.

Answer:

> The use of real-time remote biometric identification in publicly accessible spaces for law-enforcement purposes is permitted only in three specific situations under Article 5(1)(h): (i) the targeted search for victims of abduction, trafficking in human beings or sexual exploitation, and missing persons; (ii) the prevention of a specific, substantial and imminent threat to life or physical safety, or a genuine and foreseeable terrorist attack; (iii) the localisation or identification of a suspect of a criminal offence listed in Annex II that is punishable by a custodial sentence of at least four years in the relevant Member State. Such use is strictly conditioned on necessity, proportionality, prior fundamental rights impact assessment under Article 27, and registration in the EU database under Article 49, with limited exceptions for urgent deployment.

### rg_056 — 3/3 criteria

> Under Article 32 of Regulation (EU) 2024/1689, when is a conformity assessment body presumed to comply with the requirements in Article 31?

References: `Article 31.7, Article 32`

1. **PASS** — Body demonstrates conformity with relevant harmonised standards (or parts thereof)
   - Judge: candidate states that the body must demonstrate conformity with relevant harmonised standards or parts thereof
2. **PASS** — Condition: references to those standards published in the Official Journal of the European Union
   - Judge: candidate specifies that the references to those standards must be published in the Official Journal of the European Union
3. **PASS** — Presumption limited to the extent those standards cover the Article 31 requirements
   - Judge: candidate explicitly notes the presumption is limited to the extent the standards cover the Article 31 requirements

Tone: **PASS** — one short sentence

Answer:

> A conformity assessment body is presumed to comply with the requirements in Article 31 where it demonstrates conformity with the criteria laid down in the relevant harmonised standards (or parts thereof) whose references have been published in the Official Journal of the European Union. This presumption applies only to the extent that those harmonised standards cover the requirements set out in Article 31 (Article 32).

### rg_057 — 2/3 criteria

> Who is entitled to lodge a complaint about an infringement, and to which authority must the complaint be submitted?

References: `Article 85, Article 86, Annex III.7.c`

1. **PASS** — Any natural or legal person
   - Judge: candidate states 'Any natural or legal person may lodge a complaint'
2. **FAIL** — Grounds to consider there has been an infringement of the Regulation
   - Judge: candidate does not mention the requirement of having grounds to consider there has been an infringement
3. **PASS** — Submitted to the relevant market surveillance authority
   - Judge: candidate states complaint must be submitted to the relevant market surveillance authority

Tone: **PASS** — one short sentence

Answer:

> Any natural or legal person may lodge a complaint about an infringement of the EU AI Act with the relevant market surveillance authority under Article 85. The authority must inform the complainant of the progress and outcome of the complaint within a reasonable time, including any judicial remedies under Article 86. Article 86 grants affected persons the right to obtain clear and meaningful explanations from the deployer if a high-risk AI system listed in Annex III (excluding point 2) produces legal effects or significantly adverse effects on their health, safety, or fundamental rights, provided this right is not already covered by other Union law.

### rg_058 — 5/5 criteria

> Under the EU AI Act, what must providers of AI systems that generate or manipulate synthetic content do to enable identification of AI-generated/manipulated output, and what quality criteria must that solution meet?

References: `Article 50.2, Article 17.1`

1. **PASS** — Marking must be machine-readable format
   - Judge: answer states marking must be in machine-readable format
2. **PASS** — Marking must be detectable as artificially generated or manipulated
   - Judge: answer states marking must be detectable as artificially generated or manipulated
3. **PASS** — Solution must be effective, interoperable, robust and reliable, as far as technically feasible
   - Judge: answer states solution must be effective, interoperable, robust and reliable as far as technically feasible
4. **PASS** — Feasibility judged against content-type specificities/limitations, implementation costs, and state of the art
   - Judge: answer mentions taking into account content specificities, costs, and state of the art
5. **PASS** — Exemptions: assistive editing, no substantial alteration of input data/semantics, or law-enforcement authorisation
   - Judge: answer lists all three exemptions: assistive editing, no substantial alteration, and law enforcement authorization

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information in well-ordered prose.

Answer:

> Providers of AI systems that generate or manipulate synthetic content must ensure that the outputs are marked in a machine-readable format and detectable as artificially generated or manipulated under Article 50(2). This obligation applies to synthetic audio, image, video, or text content and requires technical solutions to be effective, interoperable, robust, and reliable, taking into account the specificities and limitations of the content, implementation costs, and the state of the art. The obligation does not apply where the AI system performs an assistive function for standard editing, does not substantially alter the input data or its semantics, or is authorised by law for criminal detection or prevention. Additionally, providers must ensure their quality management systems, as required under Article 17, include procedures for the development, quality control, and quality assurance of the high-risk AI system.

### rg_059 — 4/4 criteria

> Under the EU AI Act, what is the scientific panel of independent experts, what are its main support/advisory tasks, and what key characteristics/selection requirements apply to its members?

References: `Article 68.3`

1. **PASS** — Established by Commission via implementing act (Article 98(2) examination procedure) to support enforcement, not a decision-making body itself
   - Judge: states the panel is established by Commission via implementing act to support enforcement
2. **PASS** — Tasks: advise/support AI Office on general-purpose AI models (alerting systemic risks under Article 90, developing evaluation tools/benchmarks, advising on classification); plus support market surveillance authorities, cross-border surveillance (Article 74(11)), and Union safeguard procedure (Article 81)
   - Judge: covers key advisory tasks including systemic risk alerts, evaluation tools, classification advice, and support to market surveillance and safeguard procedures
3. **PASS** — Selection: experts chosen by Commission for up-to-date scientific/technical AI expertise, independence from any AI provider, and ability to act diligently, accurately and objectively
   - Judge: mentions selection based on AI expertise, independence from providers, and ability to act diligently and objectively
4. **PASS** — Members must act impartially, confidentially and free of instructions, each publishing a declaration of interests
   - Judge: states members must declare interests and ensure confidentiality, implying impartiality and independence from external instructions

Tone: **PASS** — Professional, neutral third-person register with coherent structure and no self-reference or hedging.

Answer:

> The EU AI Act establishes a Scientific Panel of independent experts under Article 68 to support enforcement activities related to general-purpose AI (GPAI) models. The panel's main tasks include alerting the AI Office to potential systemic risks, contributing to the development of tools and methodologies for evaluating GPAI model capabilities, and providing advice on the classification of GPAI models with systemic risk. Panel members must possess particular expertise and competence in AI, maintain independence from AI system providers, and demonstrate the ability to perform their duties diligently and objectively. They are required to declare conflicts of interest and ensure the confidentiality of sensitive information. The panel operates under an implementing act adopted by the Commission, which outlines procedures for issuing alerts and requesting assistance from the AI Office.

### rg_060 — 1/3 criteria

> Under the EU AI Act, if a provider identifies a serious incident during testing in real-world conditions of a high-risk AI system, what three actions must the provider take?

References: `Article 73.6`

1. **FAIL** — Perform (without delay) the necessary investigation into the incident and the AI system, including a risk assessment
   - Judge: The candidate answer does not mention performing an investigation or a risk assessment.
2. **PASS** — Take corrective action
   - Judge: Adopting mitigation measures or suspending testing constitutes corrective action.
3. **FAIL** — Cooperate with competent authorities (and notified body where relevant), and not alter the AI system in a way affecting evaluation of the incident's causes without first informing the competent authorities
   - Judge: The candidate answer does not mention cooperation with competent authorities or refraining from altering the system without informing them.

Tone: **PASS** — one short sentence

Answer:

> Report the serious incident to the national market surveillance authority in accordance with Article 73. Adopt immediate mitigation measures to address the incident. If mitigation is not possible, suspend or terminate the testing in real-world conditions and establish a procedure for the prompt recall of the AI system.

### rg_061 — 2/2 criteria

> Under the EU AI Act, which body has exclusive powers to supervise and enforce the obligations for providers of general-purpose AI models (Chapter V), and which entity is entrusted with implementing those tasks?

References: `Article 88.1`

1. **PASS** — European Commission has exclusive powers to supervise and enforce Chapter V
   - Judge: The candidate answer states that the Commission has exclusive powers to supervise and enforce Chapter V, which matches the substance of criterion 1.
2. **PASS** — AI Office is entrusted with implementing these tasks
   - Judge: The candidate answer states that the implementation of these tasks is entrusted to the AI Office, which matches the substance of criterion 2.

Tone: **PASS** — Professional, neutral third-person register with clear structure and coherent prose.

Answer:

> The Commission has exclusive powers to supervise and enforce the obligations for providers of general-purpose AI models under Chapter V of the EU AI Act, as stated in Article 88(1). The implementation of these tasks is entrusted to the AI Office. Article 88(2) further provides that market surveillance authorities may request the Commission to exercise these powers when necessary and proportionate to assist with their tasks under the Regulation.

### rg_062 — 2/3 criteria

> What must a distributor do if it considers a high-risk AI system is not in conformity with the Act's requirements? Additionally, what extra steps are required if the system presents a risk within the meaning of Article 79(1)?

References: `Article 24.4, Article 79.1, Article 81.1`

1. **FAIL** — Not make it available on market until brought into conformity
   - Judge: The answer does not state that the distributor must not make the system available on the market until it is brought into conformity; it only mentions taking corrective actions, withdrawal, or recall, but not withholding availability as a requirement.
2. **PASS** — If risk under Art 79(1): immediately inform provider or importer and the competent authorities
   - Judge: The answer clearly states that if there is a risk under Article 79(1), the distributor must immediately inform the provider or importer and the competent authorities.
3. **PASS** — Notification must detail the non-compliance and any corrective actions taken
   - Judge: The answer specifies that the notification must include details of the non-compliance and any corrective actions taken.

Tone: **PASS** — Professional, neutral tone with logically structured and actionable information in compliance with regulatory drafting standards.

Answer:

> A distributor must not make a non-conforming high-risk AI system available on the market and shall take corrective action to bring it into conformity, withdraw it, or recall it under Article 24(4). Where the system presents a risk within the meaning of Article 79(1), the distributor shall immediately inform the provider or importer and the competent authorities, providing details of the non-compliance and any corrective actions taken, as required by Article 24(4). The competent market surveillance authority shall then carry out an evaluation under Article 79(2) and, if non-compliance is confirmed, require corrective actions or adopt provisional measures such as withdrawal or restriction of the system. If the operator fails to act, the authority shall notify the Commission and other Member States under Article 79(5), triggering the Union safeguard procedure under Article 81 where applicable.

### rg_063 — 6/6 criteria

> Under Article 2(1) of Regulation (EU) 2024/1689 (EU AI Act), which categories of actors/persons does the Act apply to? List the categories.

References: `Article 2.1`

1. **PASS** — Providers placing on the market/putting into service AI systems or placing on the market GPAI models in the Union
   - Judge: candidate answer states providers placing on the market or putting into service AI systems or GPAI models in the Union, matching the criterion
2. **PASS** — Deployers of AI systems established/located in the Union
   - Judge: candidate answer includes deployers of AI systems established or located in the Union
3. **PASS** — Providers and deployers in third countries where the AI system's output is used in the Union
   - Judge: candidate answer covers providers and deployers in third countries where the AI output is used in the Union
4. **PASS** — Importers, distributors, and product manufacturers (placing an AI system on the market/into service with their product under their own name/trademark)
   - Judge: candidate answer mentions importers, distributors, and product manufacturers placing AI systems on the market under their own name or trademark
5. **PASS** — Authorised representatives of providers not established in the Union
   - Judge: candidate answer refers to authorised representatives of non-EU providers, equivalent to providers not established in the Union
6. **PASS** — Affected persons located in the Union
   - Judge: candidate answer explicitly includes affected persons located in the Union

Tone: **PASS** — Professional, neutral third-person register with clear structure and complete sentences.

Answer:

> The EU AI Act applies to the following categories of actors: (a) providers placing on the market or putting into service AI systems or general-purpose AI models in the Union, regardless of their establishment; (b) deployers of AI systems established or located in the Union; (c) providers and deployers in third countries where the AI system’s output is used in the Union; (d) importers and distributors of AI systems; (e) product manufacturers placing AI systems on the market under their own name or trademark; (f) authorised representatives of non-EU providers; and (g) affected persons located in the Union. (Article 2.1) It does not apply to natural persons using AI systems for purely personal, non-professional activities (Article 2.10).

### rg_064 — 1/1 criteria

> Under the EU AI Act, what conditions must be met before data collected and processed for testing high-risk AI systems in real-world conditions can be transferred to a third country (outside the EU)?

References: `Article 60.4.e`

1. **PASS** — Appropriate and applicable safeguards under Union law must be implemented for the transfer
   - Judge: the candidate answer states that appropriate and applicable safeguards under Union law must be implemented for the transfer, which matches the substance of the criterion

Tone: **PASS** — one short sentence

Answer:

> Data collected and processed for testing high-risk AI systems in real-world conditions may be transferred to third countries only if appropriate and applicable safeguards under Union law are implemented, as required by Article 60(4)(e).

### rg_065 — 3/3 criteria

> What are the three maximum administrative fine tiers for (a) prohibited AI practices, (b) non-compliance with obligations for high-risk AI systems and general-purpose AI (GPAI) models, and (c) supplying incorrect/incomplete/misleading information? For each tier, give the maximum amount in EUR and the alternative maximum as a percentage of worldwide annual turnover.

References: `Article 99.5, Article 5.6, Article 50.2, Article 101.1`

1. **PASS** — Prohibited AI practices (Article 5): up to EUR 35,000,000 or 7% of total worldwide annual turnover, whichever higher
   - Judge: candidate states the fine for prohibited AI practices as up to EUR 35,000,000 or 7% of turnover, whichever higher
2. **PASS** — High-risk/GPAI obligations (Articles 16, 22, 23, 24, 26, 31, 33(1)(3)(4), 34, 50): up to EUR 15,000,000 or 3% of total worldwide annual turnover, whichever higher
   - Judge: candidate states the fine for high-risk/GPAI obligations as up to EUR 15,000,000 or 3% of turnover, whichever higher
3. **PASS** — Incorrect/incomplete/misleading information to notified bodies or national competent authorities: up to EUR 7,500,000 or 1% of total worldwide annual turnover, whichever higher
   - Judge: candidate states the fine for incorrect/incomplete/misleading information as up to EUR 7,500,000 or 1% of turnover, whichever higher

Tone: **PASS** — Professional, neutral tone with clear structure and precise citation of provisions, avoiding self-reference or fragmentation.

Answer:

> The three maximum administrative fine tiers under the EU AI Act are as follows. For non-compliance with prohibited AI practices under Article 5, the fine is up to EUR 35 000 000 or 7% of total worldwide annual turnover, whichever is higher (Article 99(3)). For non-compliance with obligations concerning high-risk AI systems or general-purpose AI (GPAI) models, including provider, deployer, importer, distributor, notified body, and Article 50 transparency obligations, the fine is up to EUR 15 000 000 or 3% of total worldwide annual turnover, whichever is higher (Article 99(4)). For supplying incorrect, incomplete, or misleading information to notified bodies or national competent authorities, the fine is up to EUR 7 500 000 or 1% of total worldwide annual turnover, whichever is higher (Article 99(5)). Additionally, for GPAI model providers, the Commission may impose fines under Article 101 of up to EUR 15 000 000 or 3% of total worldwide annual turnover for breaches of Chapter V, including failure to comply with information requests or systemic risk obligations.

### rg_066 — 3/3 criteria

> Under the EU AI Act, what is the EU database for high-risk AI systems, what categories of information must it contain, and who is the controller of that database?

References: `Article 71.1, Article 49.4, Article 60.4.c, Article 6.2, Annex VIII.12`

1. **PASS** — EU database (set up/maintained by Commission with Member States) covers high-risk AI systems under Art 6(2) registered per Arts 49 and 60, and non-high-risk Art 6(3) systems registered per Art 6(4) and 49
   - Judge: The answer states the EU database is maintained by the Commission and covers high-risk systems under Art 6(2) registered per Arts 49 and 60, and non-high-risk Art 6(3) systems registered per Art 6(4) and 49.
2. **PASS** — Categories: Annex VIII Sections A and B entered by provider/authorised representative; Section C entered by deployer that is/acts on behalf of a public authority, agency or body
   - Judge: The answer specifies that Sections A and B of Annex VIII are entered by the provider or authorised representative, and implies Section C is entered by deployers acting for public authorities by noting secure registration for law enforcement, migration, and border control under Art 49(3) and (4), which aligns with Section C requirements.
3. **PASS** — Controller: the Commission
   - Judge: The answer explicitly states that the Commission is the controller of the database.

Tone: **PASS** — Professional, neutral, and self-contained explanation with clear structure and no meta-commentary or fragmentation.

Answer:

> The EU database for high-risk AI systems is established and maintained by the European Commission under Article 71. It contains information on high-risk AI systems registered in accordance with Articles 49 and 60, as well as AI systems not considered high-risk under Article 6(3) and registered under Article 49. The database includes data from Sections A and B of Annex VIII, entered by the provider or their authorised representative, and personal data only to the extent necessary for collecting and processing information under the Regulation. The Commission is the controller of the database. For high-risk AI systems in law enforcement, migration, and border control, registration occurs in a secure non-public section of the database under Article 49(4), accessible only to the Commission and specified national authorities.

### rg_067 — 3/3 criteria

> What are the conditions to classify general-purpose AI (GPAI) model as "GPAI model with systemic risk"? Do all need to be met at the same time?

References: `Article 55.1, Annex XIII`

1. **PASS** — Condition (a): high impact capabilities per Article 51(1)(a), presumed when training compute exceeds 10^25 FLOPs
   - Judge: The answer states the substance of condition (a) and includes the presumption based on training compute exceeding 10^25 FLOPs.
2. **PASS** — Condition (b): Commission decision (ex officio or following qualified alert from scientific panel) that capabilities/impact are equivalent, per Annex XIII criteria
   - Judge: The answer clearly explains condition (b), including the Commission's role and the reference to Annex XIII criteria.
3. **PASS** — No, not cumulative - either condition alone suffices
   - Judge: The answer explicitly states that not all conditions need to be met and that either (a) or (b) suffices.

Tone: **PASS** — Professional, neutral tone with clear, structured explanation of criteria and logical flow suitable for regulatory application.

Answer:

> A general-purpose AI model is classified as having systemic risk if it meets either of two conditions: (a) it has high-impact capabilities evaluated using appropriate technical tools and methodologies, including benchmarks and indicators; or (b) the European Commission decides, ex officio or following a qualified alert from the scientific panel, that it has capabilities or an impact equivalent to those in point (a), considering the criteria in Annex XIII. A model is presumed to have high-impact capabilities under condition (a) when its cumulative training compute exceeds 10^25 floating-point operations (FLOPs). Not all conditions must be met simultaneously, satisfying either (a) or (b) is sufficient. This classification triggers additional obligations under Article 55, including model evaluation, systemic risk mitigation, incident reporting, and cybersecurity protection.

### rg_068 — 0/3 criteria

> For a high-risk AI system, who is responsible for ensuring that input data is relevant and sufficiently representative for the system's intended purpose, and under what condition does that responsibility apply?

References: `Article 26.1, Article 6.2, Article 10.3`

1. **FAIL** — Provider of the high-risk AI system
   - Judge: The candidate answer states the deployer is responsible, not the provider, and thus does not state the substance of criterion 1.
2. **FAIL** — Applies whenever the system is developed using techniques involving training AI models with data (Art. 10(1))
   - Judge: The candidate answer does not mention that the responsibility applies when the system is developed using training techniques, nor does it reference Article 10(1).
3. **FAIL** — For systems not using such training techniques, applies only to testing data sets (Art. 10(6))
   - Judge: The candidate answer does not address systems not using training techniques or the limited application to testing data sets under Article 10(6).

Tone: **PASS** — Professional, neutral, and self-contained explanation that clearly allocates responsibilities between deployer and provider without self-reference or hedging.

Answer:

> The deployer is responsible for ensuring that input data is relevant and sufficiently representative for the system's intended purpose, but only to the extent that the deployer exercises control over the input data, as specified in Article 26(4). This obligation applies specifically to high-risk AI systems and complements the provider's duties under Article 10(3) and (4) regarding training, validation, and testing data. The provider must still ensure data quality during development, including representativeness and error mitigation, under Article 10. However, the deployer’s responsibility arises during use and is limited to the data they control in operational conditions.

### rg_069 — 2/3 criteria

> I am a distributor of an AI systems. Do I have obligation not to jeopardize its conformity? I was not told if the system is high-risk or not. What if am I am importer instead?

References: `Article 24.1, Article 23.1, Article 16, Article 79.2`

1. **FAIL** — Yes, obligation applies regardless of high-risk knowledge
   - Judge: The answer states obligations only apply if the system is high-risk and explicitly says 'if the system is not confirmed as high-risk, these obligations do not apply,' contradicting the criterion that the obligation applies regardless of knowledge.
2. **PASS** — Distributor: storage/transport must not jeopardise Section 2 compliance (Article 24(3))
   - Judge: The answer states that distributors must ensure storage or transport does not jeopardize compliance with Section 2 requirements, which matches the substance of Article 24(3).
3. **PASS** — Importer: same obligation applies (Article 23(4))
   - Judge: The answer states that importers must ensure storage or transport conditions do not jeopardize compliance with Section 2 requirements, which matches the substance of Article 23(4).

Tone: **PASS** — Professional, third-person tone without self-reference or hedging; logically structured and actionable for a compliance professional.

Answer:

> Yes, distributors must not jeopardize the conformity of a high-risk AI system. Under Article 24, before making a high-risk AI system available on the market, distributors must verify it bears the CE marking, is accompanied by the EU declaration of conformity and instructions for use, and that the provider and importer have complied with their obligations under Article 16 and Article 23(3). Where a distributor has reason to believe the system is not in conformity, it must not make it available until conformity is restored and must inform the provider or importer, particularly if the system presents a risk under Article 79(1). If the system is not confirmed as high-risk, these obligations do not apply. As an importer, under Article 23, the operator must verify the provider carried out the conformity assessment, drew up technical documentation, affixed the CE marking, and appointed an authorised representative if required, and the operator must ensure storage or transport conditions do not jeopardize compliance with Section 2 requirements.

### rg_070 — 4/4 criteria

> Under the EU AI Act, is an AI system that is a safety component of a medical device classified as MDR Class I (non-sterile, non-measuring, non-reusable surgical) automatically a high-risk AI system? Explain your reasoning.

References: `Article 6.1, Annex I`

1. **PASS** — No
   - Judge: The answer explicitly states 'No' as the conclusion, matching the required verdict.
2. **PASS** — Article 6(1)(a) and (b) are cumulative conditions
   - Judge: The answer states that both conditions must be met, referring to the requirements as 'cumulative' by explaining that both must be fulfilled.
3. **PASS** — MDR Class I (non-sterile, non-measuring, non-reusable surgical) devices undergo manufacturer self-assessment, not third-party conformity assessment
   - Judge: The answer clearly states that MDR Class I devices are self-certified and do not require third-party conformity assessment.
4. **PASS** — Condition (b) fails, so Article 6(1) does not apply
   - Judge: The answer explains that because the second condition (third-party assessment) is not met, Article 6(1) does not apply, directly stating that condition (b) fails.

Tone: **PASS** — Professional, neutral tone with clear logical structure and no self-reference or hedging.

Answer:

> No. An AI system that is a safety component of a medical device classified as MDR Class I (non-sterile, non-measuring, non-reusable surgical) is not automatically a high-risk AI system under Article 6(1). High-risk classification under the Annex I route requires both that the AI system is a safety component of a product covered by Union harmonisation legislation (such as Regulation (EU) 2017/745 on medical devices, listed in Annex I.11) and that the product is required to undergo third-party conformity assessment. MDR Class I devices are self-certified and do not require third-party conformity assessment, so the second condition of Article 6(1)(b) is not fulfilled. Absent inclusion in Annex III or another high-risk route, such a system is not classified as high-risk.

### rg_071 — 3/3 criteria

> Under Regulation (EU) 2024/1689 (EU AI Act), can the same AI system be subject both to the Act's "high-risk AI system" obligations and to the transparency obligations sometimes described informally as "limited risk"? Explain briefly.

References: `Article 50.4, Article 6.2`

1. **PASS** — Yes
   - Judge: the answer states 'Yes' as the unambiguous position, matching the criterion
2. **PASS** — Article 50(6): Article 50(1)-(4) transparency duties do not affect Chapter III high-risk obligations
   - Judge: the answer states that Article 50(6) says the transparency requirements do not affect Chapter III high-risk obligations, conveying the substance
3. **PASS** — Obligations are cumulative, not mutually exclusive
   - Judge: the answer explicitly states that the obligations apply cumulatively and that the transparency duties apply in addition to high-risk obligations

Tone: **PASS** — Professional, neutral tone with clear, structured explanation that a compliance professional could act upon.

Answer:

> Yes. A high-risk AI system can also be subject to the transparency obligations informally described as "limited risk" under Article 50. Article 50(6) explicitly states that its transparency requirements do not affect the obligations set out in Chapter III, which governs high-risk systems. Therefore, a system classified as high-risk under Article 6 must comply with both the full set of high-risk obligations (e.g., risk management, data governance, human oversight) and the specific transparency duties in Article 50 where applicable, such as provider disclosures when the system interacts with natural persons (Article 50(1)), marking synthetic content (Article 50(2)), or deployer disclosures for deepfakes (Article 50(4)). These Article 50 duties apply cumulatively, unless a specific exception in paragraphs 1 to 4 applies.

### rg_072 — 4/4 criteria

> Under the EU AI Act, can an AI system intended to be used as a toy qualify as a high-risk AI system, and if so under what conditions?

References: `Annex I, Article 6.2`

1. **PASS** — Yes
   - Judge: The answer states that an AI system intended to be used as a toy can qualify as high-risk, which affirms 'Yes' as the verdict.
2. **PASS** — Condition: AI system is a toy or safety component of a toy covered by Directive 2009/48/EC (Annex I harmonisation legislation)
   - Judge: The answer specifies that the AI system must be a safety component of, or itself be, a toy covered by Directive 2009/48/EC, which is listed in Annex I.
3. **PASS** — Condition: that toy is required to undergo third-party conformity assessment under the Directive
   - Judge: The answer states the condition that the toy must be subject to third-party conformity assessment under Directive 2009/48/EC.
4. **PASS** — Both conditions cumulative (Article 6(1))
   - Judge: The answer presents both conditions as required for high-risk classification under Article 6(1), indicating they are cumulative.

Tone: **PASS** — Professional, neutral tone with clear, structured explanation referencing specific legal provisions without self-reference or fragmentation.

Answer:

> An AI system intended to be used as a toy can qualify as a high-risk AI system only if it is a safety component of, or itself, a product covered by the Union harmonisation legislation listed in Annex I and that product is required to undergo a third-party conformity assessment under that legislation. Specifically, Directive 2009/48/EC on the safety of toys (Annex I.2) is the relevant harmonisation legislation. Therefore, an AI system qualifies as high-risk under Article 6(1) only if it is a safety component of a toy or is itself a toy subject to third-party conformity assessment under Directive 2009/48/EC. Article 6(2) and Annex III do not apply to toys, as they are not listed in Annex III. Article 6(3) derogations do not apply to toys, as they are not Annex III systems.

### rg_073 — 4/4 criteria

> Under the EU AI Act, can an AI system intended to be used as a safety component in a lift qualify as a high-risk AI system, and under what conditions?

References: `Article 6.1, Annex I.4`

1. **PASS** — Yes
   - Judge: The answer states 'Yes' as its unambiguous position.
2. **PASS** — Condition: AI system intended as safety component of a product covered by Annex I Union harmonisation legislation
   - Judge: The answer states the AI system must be intended as a safety component of a product covered by Annex I legislation, specifying Directive 2014/33/EU on lifts.
3. **PASS** — Condition: that product (or the AI system itself as a product) required to undergo third-party conformity assessment under that legislation
   - Judge: The answer states the product or its safety component must be required to undergo third-party conformity assessment under the relevant legislation.
4. **PASS** — Both conditions cumulative
   - Judge: The answer explicitly states that both conditions must be fulfilled for the system to be classified as high-risk.

Tone: **PASS** — Professional, neutral tone with clear reference to relevant provisions and conditions without self-reference or hedging.

Answer:

> Yes, an AI system intended to be used as a safety component in a lift can qualify as a high-risk AI system under the EU AI Act, provided it meets the conditions set out in Article 6(1). Specifically, the AI system must be covered by the Union harmonisation legislation listed in Annex I (here, Directive 2014/33/EU on lifts and safety components for lifts), and the product (or its safety component) must be required to undergo a third-party conformity assessment under that legislation. If both conditions are fulfilled, the system is classified as high-risk under Article 6(1). Article 43 then governs the required conformity assessment procedure, which will depend on whether harmonised standards or common specifications are applied.

### rg_074 — 4/4 criteria

> Under the EU AI Act (Regulation (EU) 2024/1689), are AI systems intended for emotion recognition from biometric data always prohibited? If not, in which contexts are they prohibited, what exception applies, and how are they classified when not prohibited?

References: `Article 5.1.f, Article 50.3, Annex III.1.c`

1. **PASS** — No
   - Judge: candidate answer states emotion recognition is not categorically prohibited, which aligns with 'No'
2. **PASS** — Prohibited context: inferring emotions of natural persons in workplace and education institutions (Article 5(1)(f))
   - Judge: candidate answer specifies prohibition applies in workplaces and educational institutions
3. **PASS** — Exception: use intended for medical or safety reasons
   - Judge: candidate answer mentions the medical/safety exception
4. **PASS** — When not prohibited, classified as high-risk under Annex III (emotion recognition/biometrics category)
   - Judge: candidate answer states the system is high-risk under Annex III.1(c) when not prohibited

Tone: **PASS** — one short sentence

Answer:

> Emotion recognition is not categorically prohibited under the AI Act; the prohibition in Article 5 only applies in workplaces and educational institutions, with a narrow medical/safety exception. Elsewhere the system is high-risk under Annex III.1(c) and triggers Article 50(3) transparency duties toward exposed persons.

### rg_075 — 2/3 criteria

> I generated audio with AI for my artistic work (sole purpose). Do I need to provide some marking of its artificial nature? I feel that would compromise the enjoyment of the work.

References: `Article 50.4, Article 50.2`

1. **FAIL** — Yes, disclosure still required
   - Judge: The answer states that disclosure is not needed in a way that compromises enjoyment, but does not affirm that disclosure is still required in some form, so it does not state the substance that disclosure is still required.
2. **PASS** — No need for marking that hampers enjoyment
   - Judge: The answer clearly states that marking which compromises enjoyment is not required, aligning with the criterion.
3. **PASS** — Must disclose existence of AI-generated content in appropriate/unobtrusive manner
   - Judge: The answer specifies that disclosure must be made in an appropriate manner that does not hamper enjoyment, which matches the requirement to disclose existence unobtrusively.

Tone: **PASS** — Professional, neutral tone with clear reference to the relevant provision and balanced explanation consistent with regulatory guidance.

Answer:

> No, you do not need to mark the artificial nature of AI-generated audio used solely for an artistic work in a way that compromises its enjoyment. Under Article 50(4), deployers of AI systems that generate or manipulate audio content constituting a deep fake must disclose the artificial origin, but this obligation is limited for artistic, creative, satirical or fictional works: the disclosure must be made in an appropriate manner that does not hamper the display or enjoyment of the work. Since the operator's use is purely artistic, the transparency requirement is relaxed to preserve the integrity of the work.

### rg_076 — 1/1 criteria

> Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?

References: `Article 3.2`

1. **PASS** — Combination of probability of occurrence of harm and severity of that harm
   - Judge: one short sentence

Tone: **PASS** — one short sentence

Answer:

> ‘risk’ means the combination of the probability of an occurrence of harm and the severity of that harm;

### rg_077 — 3/3 criteria

> For AI systems that fit within the use cases listed in Annex III but are considered non-high-risk by the provider, do they need to be registered in the EU database?

References: `Article 6.2, Annex III.7.b, Article 49.1, Article 71.1, Annex VIII.12`

1. **PASS** — Yes
   - Judge: The answer explicitly states 'Yes' as the position, matching the required verdict.
2. **PASS** — Registration required under Article 49(2)
   - Judge: The answer states the system must be registered under Article 49(2), conveying the substance of the requirement.
3. **PASS** — Registered in EU database referred to in Article 71
   - Judge: The answer clearly states the system must be registered in the database established under Article 71, which conveys the required substance.

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information for a compliance context.

Answer:

> Yes, where the provider concludes the system is not high-risk under Article 6(3). AI systems falling within an Annex III use case must be registered in the EU database under Article 49(2) if the provider determines, in accordance with Article 6(3), that the system does not pose a significant risk of harm and meets one of the four derogation conditions, such as performing a narrow procedural task, improving a previously completed human activity, detecting decision-making patterns without influencing outcomes, or performing a preparatory task, provided it does not profile natural persons. The provider must document this assessment before market placement and register the system in the database established under Article 71, entering the information specified in Section B of Annex VIII. Notwithstanding any derogation, an Annex III system that performs profiling of natural persons is always high-risk and subject to the standard high-risk registration under Article 49(1).

### rg_078 — 2/3 criteria

> Do I need informed consent to test a high-risk AI system in real-world conditions outside a regulatory sandbox?

References: `Article 60.4.i, Article 61.1`

1. **PASS** — Yes
   - Judge: the answer states 'Yes, you need informed consent' which matches the required verdict
2. **PASS** — Consent must be freely given and informed, obtained prior to participation, covering nature/objectives/inconveniences, conditions and duration, rights to refuse/withdraw without detriment or justification, reversal/disregard arrangements, and the unique ID plus provider contact details
   - Judge: the answer covers the substance of all required elements: freely given and informed consent, obtained prior to participation, and includes information on nature/objectives, duration, rights to withdraw without detriment, and clear information about the testing
3. **FAIL** — Consent must be dated, documented, and a copy given to the subject or their legal representative
   - Judge: the answer mentions consent must be documented but does not state it must be dated, nor that a copy must be given to the subject or legal representative

Tone: **PASS** — Professional, neutral tone with clear reference to specific articles and requirements, structured in coherent prose suitable for regulatory guidance.

Answer:

> Yes, you need informed consent to test a high-risk AI system in real-world conditions outside a regulatory sandbox. Article 61 mandates that test subjects must give freely, specifically, informed, unambiguous, and prior consent, including the right to withdraw without detriment. This consent must be documented and provided with concise, clear, relevant, and understandable information about the testing's nature, objectives, duration, and the subject's rights. Article 60(4)(i) further requires that the subjects of the testing have given this informed consent in accordance with Article 61.

### rg_079 — 4/4 criteria

> A provider becomes aware of a risk (within the meaning of Article 79(1)) for their high-risk AI system. Does the provider need to take immediate corrective action OR immediately investigate the causes OR both? For example, perhaps it's the market surveillance authority that must investigate the cause, and the provider can help later.

References: `Article 79.1, Article 79.2, Article 20.2`

1. **PASS** — Both
   - Judge: The answer states the provider must both investigate the causes and take corrective actions, satisfying 'both'.
2. **PASS** — Immediate corrective action required under Article 20(1) where system is non-compliant
   - Judge: The answer explicitly states the provider must take immediate corrective actions under Article 20(1) if the system is non-compliant.
3. **PASS** — Immediate investigation of causes is the provider's own duty under Article 20(2)
   - Judge: The answer clearly assigns the duty of immediate investigation to the provider under Article 20(2), not to the market surveillance authority.
4. **PASS** — Investigation done in collaboration with reporting deployer where applicable, not deferred to market surveillance authority
   - Judge: The answer specifies that investigation is done in collaboration with the reporting deployer where applicable, and emphasizes the provider's duties are concurrent, not deferred to the authority.

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference; logically ordered and actionable prose.

Answer:

> Where a high-risk AI system presents a risk within the meaning of Article 79(1), the provider must immediately investigate the causes in collaboration with the reporting deployer, where applicable, and inform the market surveillance authorities and, where applicable, the notified body, of the nature of the non-compliance and any corrective action taken, under Article 20(2). The provider must also take immediate corrective actions, such as withdrawal, disabling, or recall, if the system is not in conformity, per Article 20(1). While market surveillance authorities have the power to evaluate the system and require corrective measures under Article 79(2), the provider’s duties to investigate and act are independent and concurrent, not deferred to the authority’s intervention.

### rg_080 — 4/4 criteria

> What is Article 50(4) about?

References: `Article 50.4`

1. **PASS** — Deployers of AI systems generating/manipulating image, audio or video constituting a deep fake must disclose the content is artificially generated or manipulated
   - Judge: candidate states deployers must disclose deep fake content
2. **PASS** — Exception where use is authorised by law to detect/prevent/investigate/prosecute criminal offences
   - Judge: candidate states exception for law enforcement purposes
3. **PASS** — For evidently artistic/creative/satirical/fictional/analogous works, obligation limited to disclosing existence of such content without hampering enjoyment/display
   - Judge: candidate explains limited disclosure for artistic or satirical works
4. **PASS** — Separate rule: deployers of AI systems generating/manipulating text published to inform the public on matters of public interest must disclose artificial generation, with exceptions for law-enforcement authorisation or human review/editorial responsibility
   - Judge: candidate describes separate text disclosure rule with correct exceptions

Tone: **PASS** — Professional, neutral third-person register with logically structured and actionable prose.

Answer:

> Article 50(4) requires deployers of AI systems that generate or manipulate image, audio or video content constituting a deep fake to disclose that the content has been artificially generated or manipulated. This obligation does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences. For content forming part of an evidently artistic, creative, satirical, fictional or analogous work, disclosure must be made in a manner that does not hamper the display or enjoyment of the work. Deployers of AI systems generating or manipulating text published to inform the public on matters of public interest must also disclose artificial generation or manipulation, unless the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for its publication.

### rg_081 — 4/4 criteria

> Is an AI system high-risk if it is used in a product that: is not listed in Annex I; use case not listed in Annex III; internally uses general purpose AI model with systemic risk due to high impact capabilities?

References: `Article 6.2, Article 50.4, Annex III, Annex I.19, Article 5.1.d`

1. **PASS** — No
   - Judge: the answer clearly states the AI system is not high-risk, matching the 'No' verdict
2. **PASS** — Article 6(1) not met: not an Annex I product/safety component requiring third-party conformity assessment
   - Judge: the answer explains that the product is not covered by Annex I and does not require third-party conformity assessment, covering the substance of Article 6(1)
3. **PASS** — Article 6(2) not met: use case not listed in Annex III
   - Judge: the answer explicitly states the use case is not listed in Annex III, addressing Article 6(2)
4. **PASS** — Internal use of a general-purpose AI model with systemic risk is not an Article 6 criterion
   - Judge: the answer states that internal use of a systemic-risk general-purpose AI model does not by itself make the system high-risk under Article 6, capturing the substance of the criterion

Tone: **PASS** — Professional, neutral tone with clear logical structure and no self-reference or hedging.

Answer:

> Not high-risk. An AI system is high-risk only under Article 6(1) if it is a safety component of, or itself a product covered by, Annex I legislation and that product requires third-party conformity assessment, or under Article 6(2) if it falls within one of the use cases listed in Annex III. The system described is neither covered by Annex I nor does it perform an Annex III use case, so it does not meet either high-risk classification route. The internal use of a general-purpose AI model with systemic risk does not, by itself, render the system high-risk under Article 6. Absent a prohibited practice under Article 5 or a high-risk classification, the system remains not high-risk, though it may still be subject to transparency obligations under Article 50 if it interacts with natural persons or generates synthetic content.

### rg_082 — 3/3 criteria

> My local small language model says that, as a distributor of high-risk AI systems, I must be careful that transport conditions do not jeopardize compliance. But AI is just software, isn't it? So I am pretty sure my model hallucinated. What do you say?

References: `Article 24.3`

1. **PASS** — No, not hallucinated
   - Judge: the answer clearly states the model did not hallucinate, affirming the concern is valid
2. **PASS** — Article 24(3) applies
   - Judge: the answer explicitly references Article 24(3) as the applicable provision
3. **PASS** — Duty applies only 'where applicable' (e.g., embedded/supplied hardware or physical media)
   - Judge: the answer acknowledges the duty applies 'where applicable' by stating the obligation is triggered when storage or transport could affect compliance

Tone: **PASS** — Professional, neutral tone without self-reference or hedging; clear, coherent explanation grounded in regulatory text.

Answer:

> Yes, the operator's small language model did not hallucinate. Article 24(3) of the EU AI Act requires distributors to ensure that, while a high-risk AI system is under their responsibility, storage or transport conditions, where applicable, do not jeopardise the system’s compliance with the requirements set out in Section 2 of Chapter III. This obligation applies regardless of the system being software, as the integrity of the AI system, including its deployment environment, configuration, and supporting documentation, must be preserved throughout the supply chain. The distributor must act where storage or transport could affect compliance, even for intangible software deployments.

### rg_083 — 4/4 criteria

> Given an AI system that is high-risk according to Annex III: if it is repurposed to a use case not in Annex III (nor Annex I), then:
> - the repurposed AI system is still high-risk due to reversibility of training into the original system
> - the repurposed AI system is no longer high-risk but it must be reported in the EU database
> - the repurposed AI system is no longer high-risk and there is no need to report it in the EU database

References: `Annex III.6.d, Annex I.5, Article 6.2, Article 71.1`

1. **PASS** — No longer high-risk (third option)
   - Judge: candidate answer selects the third option, stating the repurposed system is no longer high-risk
2. **PASS** — High-risk status attaches to intended purpose/use case under Article 6(2)/Annex III, not to the system or its training as such
   - Judge: answer implies high-risk status depends on the intended use case under Annex III, not inherent system properties
3. **PASS** — New use case outside Annex III and Annex I means neither limb of Article 6 is satisfied
   - Judge: answer states that outside Annex III (and implicitly Annex I), the system no longer meets Article 6 criteria for high-risk
4. **PASS** — No registration/EU database obligation (Article 49/Article 71) since system is not high-risk
   - Judge: answer explicitly states no database obligation under Article 71 for non-high-risk systems

Tone: **PASS** — Professional, neutral tone with clear reference to relevant articles and logical structure.

Answer:

> The repurposed AI system is no longer high-risk and there is no need to report it in the EU database. Under Article 6(3), an AI system referred to in Annex III is not considered high-risk if it does not pose a significant risk of harm and meets one of the conditions listed, such as performing a preparatory task. If the system is repurposed to a use case not in Annex III, it no longer falls under the high-risk classification. Furthermore, Article 71 does not require registration in the EU database for systems that are no longer high-risk.

### rg_084 — 3/3 criteria

> We have a phone system where the caller can press 1 if they consent to the call being recorded, 2 if they do not. We wish to replace this with an NLP system that understands a voice reply like "Yes", "Sure", "Please no", etc. Would such a system be considered high-risk? It's for our clinic.

References: `Article 6.2, Annex III.5.d, Annex I.19, Article 50.1`

1. **PASS** — No
   - Judge: the answer clearly states the system is not high-risk, which corresponds to 'No' as the verdict
2. **PASS** — Not biometric categorisation or emotion recognition under Annex III(1)(b)-(c), since the system parses semantic content (yes/no), not emotional or protected-attribute inference
   - Judge: the answer explains the system does not perform emotion recognition or biometric categorisation because it interprets verbal consent semantically, not emotional or protected-attribute inference
3. **PASS** — Not essential healthcare services under Annex III(5)(a), since consent capture for call recording is not an eligibility evaluation for benefits/services
   - Judge: the answer states the system does not relate to access to healthcare services under Annex III(5)(a), implying consent capture for recording is not an eligibility evaluation for services

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> Not high-risk. A natural-language processing system that interprets verbal consent in a clinic call system is not prohibited under Article 5 and does not fall under any Annex III high-risk use case, such as emotion recognition (Annex III.1(c)) or access to healthcare services (Annex III.5(a)). The system does not constitute a safety component of a medical device requiring third-party conformity assessment under Annex I, nor does it perform profiling of natural persons. As a result, it is not classified as high-risk under Article 6(1) or Article 6(2). The system remains subject to the transparency obligation under Article 50(1), requiring the provider to ensure users are informed they are interacting with an AI system.

### rg_085 — 4/4 criteria

> Does the AI Act prohibit or classifies as high-risk the use of AI in drones? Can I use AI in a drone to find who's around in town? And what if it's just a toy drone? And what about toy drones used for other applications?

References: `Annex III.7, Annex I.2, Article 5.1.h, Article 50`

1. **PASS** — No blanket prohibition/high-risk classification for drones as such — turns on AI system's intended use under Article 6
   - Judge: States that high-risk classification depends on intended use under Article 6, not drones as such.
2. **PASS** — Drone AI identifying people in public = remote biometric identification, high-risk under Annex III(1)(a), not the 1:1 verification exclusion
   - Judge: Explicitly identifies using AI in a drone to find people in town as remote biometric identification, high-risk under Annex III.1(a), and not covered by the verification exclusion.
3. **PASS** — Toy status irrelevant — classification depends on intended use, not the device
   - Judge: Clarifies that toy drone status alone does not determine classification; depends on intended use and conformity assessment requirements.
4. **PASS** — Toy drone used for other application is high-risk only if that use matches Annex III (or Article 6(1) safety-component/conformity-assessment criteria)
   - Judge: States that toy drones used for other applications are high-risk only if they fall under Annex I with third-party assessment or Annex III, aligning with the criterion.

Tone: **PASS** — Professional, neutral tone with clear, structured guidance that aligns with regulatory language and distinguishes risk categories without self-reference or ambiguity.

Answer:

> High-risk only where the AI system in a drone is used for a purpose listed in Annex III or is a safety component of a product requiring third-party conformity assessment under Annex I. Using AI in a drone to find who is around in town constitutes remote biometric identification, which is high-risk under Annex III.1(a) and subject to strict safeguards; it is not prohibited unless used in real time by law enforcement in publicly accessible spaces, which would be prohibited under Article 5(1)(h) absent one of the three narrow exceptions (e.g., search for missing persons under Article 5(1)(h)(i)). A toy drone covered by Directive 2009/48/EC (Annex I.2) is high-risk only if it requires third-party conformity assessment and the AI is a safety component; otherwise, it is not high-risk but may still trigger the Article 50 transparency obligation if it interacts directly with natural persons. Toy drones used for other applications remain subject to the same classification rules: high-risk if falling under Annex I with third-party assessment or Annex III, otherwise not high-risk but potentially subject to transparency duties under Article 50.

### rg_086 — 3/3 criteria

> Does the EU AI Act establish a "proportionality of need" requirement according to which very powerful but environmentally impactful models (e.g. LLMs) should not be used for simple tasks (e.g. sentiment recognition) when a simpler and performant model is available (e.g. BERT)? If yes, cite which Article or Annex mentions this.

References: `Article 2.1.a, Article 112.6`

1. **PASS** — No
   - Judge: The candidate answer clearly states that the EU AI Act does not establish such a requirement, matching the 'No' verdict.
2. **PASS** — No provision conditions use of a capable model on unavailability of a simpler/less resource-intensive alternative for the same task
   - Judge: The answer explains that no current obligation ties model use to the availability of simpler alternatives, directly stating the substance of the criterion.
3. **PASS** — Obligations are risk- and capability-based (e.g. Article 6, Annex III, Article 51), not tied to model right-sizing or environmental impact
   - Judge: The answer correctly identifies that obligations under the Act are based on risk and capability, not on model size or environmental efficiency, aligning with the criterion's substance.

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> No. The EU AI Act does not establish a "proportionality of need" requirement that restricts the use of powerful models for simple tasks based on environmental impact or model efficiency. While Article 112(6) mandates that the Commission report by 2 August 2028 and every four years thereafter on the progress of standardisation deliverables concerning the energy-efficient development of general-purpose AI models and assess the need for further measures, including binding ones, no current obligation in the Regulation compels providers or deployers to use the least complex or least resource-intensive model suitable for a given task. The Act’s environmental considerations are limited to future evaluation and potential policy development, not direct regulatory requirements on model selection or proportionality.

### rg_087 — 3/4 criteria

> Article 9 of the AI Act lists the five categories of harm that map to AI systems with: no risk, limited risk, high-risk, systemic risk, prohibited. What are the five categories and how do they map to the five risk levels?

References: `Article 51.1, Article 9.2, Article 5.1.d, Article 6.2, Article 50.4`

1. **PASS** — No
   - Judge: the candidate answer correctly states that the premise of the question is false, aligning with the 'No' verdict
2. **PASS** — Article 9 only establishes the risk management system for high-risk AI systems, not a five-tier harm classification
   - Judge: the candidate answer explicitly states that Article 9 only deals with risk management for high-risk systems, not a five-tier classification
3. **FAIL** — Four steps: identify/analyze risks (9(2)(a)); estimate/evaluate risks under intended use and foreseeable misuse (9(2)(b)); evaluate risks from post-market monitoring data (9(2)(c)); adopt targeted risk management measures (9(2)(d))
   - Judge: the candidate answer does not list or describe the four steps of the risk management process outlined in Article 9(2)
4. **PASS** — The prohibited/high-risk/limited-risk/minimal-risk/systemic-risk tiering comes from elsewhere in the Regulation (e.g. Articles 5, 6, 50, 51), not Article 9
   - Judge: the candidate answer correctly identifies that the risk tiering comes from other articles, naming Articles 5, 6, 50, and 51 as sources

Tone: **PASS** — Professional, neutral tone with clear, coherent structure that directly addresses the regulatory framework without self-reference or informality.

Answer:

> The EU AI Act does not define five categories of harm that map to the five risk levels as suggested. Instead, it establishes four risk tiers: prohibited AI practices under Article 5, high-risk systems under Article 6 (via Annex I or Annex III), limited-risk systems subject to transparency obligations under Article 50, and minimal-risk systems outside regulatory scope. Additionally, general-purpose AI models with systemic risk are governed under Articles 51 to 55, where systemic risk is defined in Article 3(65) as risks propagated at scale across the value chain due to high-impact capabilities, such as when cumulative training compute exceeds 10^25 FLOPs under Article 51(2). Article 9 requires high-risk AI systems to implement a risk management system addressing risks to health, safety, and fundamental rights, but it does not categorize harm into five types or link them to the risk levels.

### rg_088 — 3/3 criteria

> We deployed a high-risk AI system in our company. We have a use in mind that is outside the intended use and our legal team say such a use is definitely no risk (no Annex I nor III apply). Can we just go ahead with the new use and do we need to keep logs for it?

References: `Annex I.5, Annex III.7.b, Article 25.1.c, Article 26.6`

1. **PASS** — No, cannot proceed with the new use
   - Judge: The answer clearly states 'No' and explains that the deployer cannot proceed with the new use without reassessing compliance.
2. **PASS** — Article 26(1) requires use in accordance with instructions for use; deviating from intended use is not excused merely because that use alone wouldn't trigger Annex III
   - Judge: The answer states that Article 26(1) requires use in accordance with instructions for use and that deviating from intended purpose breaches this obligation, regardless of risk under Annex III.
3. **PASS** — Yes, logging duty under Article 26(6) still applies regardless of the particular use
   - Judge: The answer explicitly confirms that the logging duty under Article 26(6) applies regardless of the use case.

Tone: **PASS** — Professional, neutral tone with clear structure and actionable regulatory references without self-reference or hedging.

Answer:

> No. A deployer may not use a high-risk AI system outside its intended purpose without reassessing compliance, even if the new use appears unrelated to Annex I or Annex III. Under Article 25(1)(c), modifying the intended purpose of a system in a way that makes it high-risk renders the deployer a provider, triggering full provider obligations. Furthermore, Article 26(1) requires deployers to use high-risk systems strictly in accordance with the provider’s instructions for use, which are tied to the original intended purpose. Deviating from that purpose breaches this obligation. Additionally, Article 26(6) mandates that deployers keep automatically generated logs under their control for at least six months, regardless of the use case, unless otherwise provided by Union or national law. Therefore, both the change in use and the log retention requirement are governed by the Act.

### rg_089 — 2/3 criteria

> Is an AI that transcribes doctor-patient conversations prohibited? Or is it high-risk as per the use cases of Annex III of the AI Act?

References: `Annex III.5, Article 5.1.d, Annex I.5, Article 50.1`

1. **PASS** — No, not a prohibited practice under Article 5
   - Judge: The answer states the AI system is not one of the prohibited practices under Article 5, which includes a list that does not cover mere transcription.
2. **PASS** — No, not high-risk under Annex III
   - Judge: The answer explicitly states the system is not an Annex III use case, as it does not determine access to healthcare or support high-risk decisions.
3. **FAIL** — Reason: narrow procedural task derogation, Article 6(3), point (a)
   - Judge: The answer does not mention the narrow procedural task derogation in Article 6(3)(a) as the reason for not being high-risk; instead, it relies on absence from Annex III and limited-risk classification without invoking Article 6(3)(a).

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information in well-ordered prose.

Answer:

> Not prohibited and not high-risk. Mere transcription of doctor-patient conversations is none of the eight prohibited practices under Article 5, including social scoring, emotion recognition, or biometric categorisation. It is not an Annex III use case, as it does not determine access to healthcare, assess risk, or support triage or eligibility decisions. Absent integration into a safety component of a medical device requiring third-party conformity assessment under Annex I, the system is limited risk. As a limited-risk system interacting directly with natural persons, the provider must comply with the Article 50(1) transparency obligation to ensure users are informed they are interacting with an AI system, unless this is already obvious.

### rg_090 — 4/4 criteria

> As a deployer, do I need to keep logs if I use a powerful LLM (surpassing the FLOPs threshold) for estimating whether customer payment confirmations are received via email?

References: `Article 12.3, Article 25.1, Annex I.5, Article 50, Article 4`

1. **PASS** — No
   - Judge: answer clearly states 'no deployer log-keeping obligation'
2. **PASS** — Article 26(6) logging duty applies only to deployers of high-risk AI systems
   - Judge: answer implies logging duty applies only to high-risk systems by stating no obligation exists because the system is not high-risk
3. **PASS** — This use case is not a high-risk use case listed in Annex III
   - Judge: answer states the use case does not fall under Annex III’s high-risk use cases
4. **PASS** — FLOPs threshold concerns GPAI systemic-risk classification under Article 51, a separate regime irrelevant to Annex III high-risk classification
   - Judge: answer explains that surpassing FLOPs threshold does not make the downstream application high-risk or trigger systemic-risk obligations for the deployer

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> Not high-risk, so no deployer log-keeping obligation under Article 12. A system estimating customer payment confirmations via email does not fall under Annex III’s high-risk use cases, nor is it a safety component of a product requiring third-party conformity assessment under Annex I. The use of a powerful LLM surpassing the 10^25 FLOPs threshold does not, by itself, make the downstream application high-risk or trigger systemic-risk obligations for the deployer. Article 25 does not reclassify the deployer as a provider unless they modify the model’s intended purpose to make it high-risk, make a substantial modification, or place their name or trademark on the system. Absent such actions, the deployer retains only the limited transparency and AI literacy duties under Article 50 and Article 4, but no logging requirement.

### rg_091 — 1/3 criteria

> Is AI software that helps clinicians take medical decisions around best treatment potentially high-risk? According to what Article and/or Annex?

References: `Article 6.1, Annex III.5.d, Annex I.12`

1. **PASS** — Yes
   - Judge: the answer states 'Yes' as its unambiguous position, matching the required verdict
2. **FAIL** — Article 6(2)
   - Judge: The candidate answer refers to Article 6(2) but does not state that high-risk classification under Article 6(2) is based on the AI system falling under a use case in Annex III; it incorrectly suggests Article 6(2) itself contains the conditions, rather than stating the substance that Article 6(2) refers to Annex III for the criteria.
3. **FAIL** — Annex III (healthcare access/provision)
   - Judge: The candidate answer mentions Annex III(5)(a) and (d), which relate to access to healthcare and emergency triage, but does not state that decision support for best treatment falls under Annex III(5)(e), which specifically covers AI systems intended to assist in clinical decision-making; thus, it fails to state the substance of the correct Annex III use case.

Tone: **PASS** — Professional, neutral tone with clear reference to relevant Articles and Annexes, logically structured for regulatory application.

Answer:

> Yes, AI software that helps clinicians take medical decisions around best treatment can be high-risk under Article 6. It is high-risk under Article 6(1) if it is a safety component of, or itself, a medical device covered by Annex I (specifically Regulation (EU) 2017/745 on medical devices) and that device is subject to third-party conformity assessment. Alternatively, under Article 6(2), it may be high-risk if it falls under an Annex III use case, such as determining access to healthcare services under Annex III(5)(a) or supporting emergency triage under Annex III(5)(d). The system is not automatically high-risk if it performs only a narrow procedural task, improves a previously completed human activity, detects decision-making patterns without replacing human assessment, or performs a preparatory task, unless it profiles natural persons, per Article 6(3).

### rg_092 — 3/3 criteria

> Do Annex I, Annex II, and Annex III all have to deal with high-risk AI classifications? If not, which doesn't/do not, and what is/are it/they about?

References: `Annex III, Annex I, Annex II, Article 6, Article 5`

1. **PASS** — No
   - Judge: candidate answer states 'No' as the overall verdict, matching the criterion
2. **PASS** — Annex II is the one that does not - it lists criminal offences referred to in Article 5(1), first subparagraph, point (h)(iii), a prohibited-practices provision, not high-risk classification
   - Judge: candidate answer identifies Annex II as not dealing with high-risk classification and correctly explains it lists criminal offences for a prohibited-practices exception
3. **PASS** — Annex I and Annex III both relate to high-risk classification - Annex I (Union harmonisation legislation) feeds Article 6(1), Annex III (use-case areas) is referred to in Article 6(2)
   - Judge: candidate answer states both Annex I and Annex III relate to high-risk classification and correctly describes their roles under Article 6(1) and 6(2) respectively

Tone: **PASS** — Professional, neutral tone with clear structure and coherent explanation of each Annex's role.

Answer:

> No, not all of Annex I, Annex II, and Annex III deal with high-risk AI classifications. Annex I and Annex III are directly relevant to high-risk classification under Article 6, while Annex II does not. Annex I lists Union harmonisation legislation for products (such as machinery, medical devices, and vehicles) where AI systems that are safety components or themselves products must undergo third-party conformity assessment, classifying them as high-risk under Article 6(1). Annex III enumerates specific high-risk use cases across eight domains (biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration, and justice), making AI systems falling within these listed uses high-risk under Article 6(2). In contrast, Annex II lists criminal offences punishable by at least four years’ custodial sentence, which are relevant only for the narrow exceptions permitting real-time remote biometric identification by law enforcement under Article 5(1)(h)(iii), and does not concern high-risk AI classification.

### rg_093 — 3/3 criteria

> Is irregular migration a topic considered in the AI Act? If so, to what risk category does it belong?

References: `Article 6.4, Article 27.1, Annex III.7.b`

1. **PASS** — Yes
   - Judge: the answer states that irregular migration is considered in the EU AI Act, which affirms the substance of the 'Yes' criterion
2. **PASS** — Migration, asylum and border control management (Annex III.7)
   - Judge: the answer explicitly states that systems assessing risk of irregular migration fall under Annex III(7)(b), which covers migration, asylum and border control management
3. **PASS** — High-risk
   - Judge: the answer clearly states that such AI systems are classified as high-risk, satisfying the high-risk criterion

Tone: **PASS** — Professional, neutral tone with clear reference to relevant provisions and conditions without self-reference or hedging.

Answer:

> Yes, irregular migration is considered in the EU AI Act. AI systems intended to assess a risk of irregular migration are classified as high-risk under Annex III(7)(b), which covers migration, asylum and border control management. Such systems fall under Article 6(2) as high-risk AI systems, provided they are used by or on behalf of competent public authorities or Union bodies. Deployers that are public bodies or private entities providing public services must conduct a fundamental rights impact assessment under Article 27(1) before deployment, unless an exemption applies.

### rg_094 — 5/5 criteria

> About obligations of transparency to providers who want to use a GPAI model, do you need to disclose: date of release? number of paramaters? applicable model interaction with hardware? license? samples of outlier data used in training? Given clear yes/no to each item.

References: `Article 53.1, Annex XII.1, Annex XI.2`

1. **PASS** — Date of release - Yes
   - Judge: candidate states 'Yes, for release date' and mentions disclosing date of release, satisfying the substance
2. **PASS** — Architecture and number of parameters - Yes
   - Judge: candidate states 'Yes, for number of parameters' and explicitly confirms disclosure of number of parameters
3. **PASS** — Interaction with hardware or software - Yes
   - Judge: candidate states 'Yes, for model interaction with hardware' and confirms disclosure of interaction with hardware
4. **PASS** — License - Yes
   - Judge: candidate states 'Yes, for licence' and confirms disclosure of license
5. **PASS** — Samples of outlier training data - No
   - Judge: candidate states 'No, for samples of outlier data used in training' and clarifies that such disclosure is not required

Tone: **PASS** — Professional, neutral, and structured response with clear yes/no answers and precise references to regulatory provisions without self-reference or ambiguity.

Answer:

> Yes, for release date, number of parameters, model interaction with hardware, and licence. No, for samples of outlier data used in training. GPAI providers must disclose the date of release, number of parameters, how the model interacts with hardware, and the licence under Annex XII.1(c), (f), (d), and (h) respectively, as part of the information to downstream providers. Disclosure of outlier data samples is not required, though general data curation methodologies must be described under Annex XI.2(c).

### rg_095 — 3/3 criteria

> Who, if at all, needs to establish the post-market monitoring system for a high-risk AI system? Provider/deployer/AI office? Is it possible that the monitoring system may need to also include info on interaction with other AI systems than the high-risk one in consideration?

References: `Article 72.2, Article 9.2, Article 17.1`

1. **PASS** — Provider
   - Judge: The answer states that the provider must establish the post-market monitoring system.
2. **PASS** — Not deployer or AI Office
   - Judge: The answer explicitly states that the deployer and AI Office do not have this duty.
3. **PASS** — Yes — must include analysis of interaction with other AI systems where relevant
   - Judge: The answer confirms that the system must include analysis of interaction with other AI systems where relevant, as specified in Article 72(2).

Tone: **PASS** — Professional, third-person tone with clear attribution of duties and references to relevant articles, structured in coherent prose.

Answer:

> The provider must establish the post-market monitoring system for a high-risk AI system under Article 72(1), which requires a documented system proportionate to the risks and technologies involved. The system must actively collect and analyse performance data throughout the AI system’s lifetime, including, where relevant, an analysis of the interaction with other AI systems, as specified in Article 72(2). This obligation is integrated into the provider’s quality management system under Article 17(1)(h) and feeds into the ongoing risk management process under Article 9(2)(c). The deployer and AI Office do not have this duty; however, deployers may contribute data, and the AI Office oversees compliance but does not operate the system.

### rg_096 — 3/3 criteria

> What is an "area" and what is a "use case" for high-risk as per Article 6(2)? How many areas exist?

References: `Article 6.2, Article 6.3, Annex III.7.b`

1. **PASS** — Area = broad Annex III numbered heading/policy domain
   - Judge: The answer states that an 'area' is one of the eight numbered headings in Annex III, which matches the criterion's definition.
2. **PASS** — Use case = specific application listed within an area (lettered sub-point)
   - Judge: The answer defines a 'use case' as a specific lettered application listed under each area, which captures the substance of the criterion.
3. **PASS** — 8 areas exist
   - Judge: The answer explicitly states there are eight areas and lists them, satisfying the numerical criterion.

Tone: **PASS** — Professional, neutral explanation using precise regulatory terminology with clear structure and no self-reference or hedging.

Answer:

> An "area" under Article 6(2) refers to one of the eight numbered headings in Annex III that categorise high-risk AI use cases, while a "use case" is a specific lettered application listed under each area. The eight areas are: biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration and asylum and border control, and administration of justice and democratic processes. Each area contains specific use cases that, if matched, classify an AI system as high-risk under Article 6(2), unless the system falls under the Article 6(3) derogation for narrow procedural, preparatory, or human-assessment-support tasks that do not materially influence decision-making or involve profiling of natural persons.

### rg_097 — 1/2 criteria

> Name the areas of high-risk use cases. Is healthcare decision making one of them?

References: `Annex III, Article 6`

1. **PASS** — Biometrics; Critical infrastructure; Education and vocational training; Employment, workers' management and access to self-employment; Access to and enjoyment of essential private and public services and benefits; Law enforcement; Migration, asylum and border control management; Administration of justice and democratic processes
   - Judge: The candidate answer lists all eight high-risk areas as specified in Annex III, using substantially equivalent terms.
2. **FAIL** — No
   - Judge: The candidate answer explicitly states 'Yes, healthcare decision making is one of them,' which contradicts the required 'No' verdict in criterion 2.

Tone: **PASS** — Professional, neutral tone with clear structure and precise references to the regulatory text.

Answer:

> The eight high-risk areas listed in Annex III are biometrics, critical infrastructure, education and vocational training, employment and worker management, access to essential private and public services, law enforcement, migration and border control, and administration of justice and democratic processes. Yes, healthcare decision making is one of them, specifically under Annex III(5)(a) as AI systems used by or on behalf of public authorities to evaluate eligibility for, or grant, reduce, revoke or reclaim, essential public assistance benefits and services, including healthcare services. Emergency healthcare patient triage systems are also high-risk under Annex III(5)(d). These uses are classified as high-risk under Article 6(2) unless they meet the Article 6(3) derogation conditions and do not profile natural persons.

### rg_098 — 0/1 criteria

> What does Annex VII point 5.1 say? Try to get the substance right. Do not get confused with other material, like 5.1 in Annex III or Article 7, which is about something else entirely.

References: `Annex VII.5, Article 7.2, Annex III.8`

1. **FAIL** — Purpose of surveillance is to ensure the provider duly complies with the terms and conditions of the approved quality management system
   - Judge: The candidate answer does not state the substance of the purpose of surveillance as required by the criterion; instead, it disputes the existence of point 5.1 and describes audit activities without affirming the required purpose of ensuring compliance with the quality management system's terms and conditions.

Tone: **PASS** — Professional, neutral tone without self-reference or hedging; clear and grammatically coherent explanation that a compliance professional could act upon.

Answer:

> Annex VII point 5.1 does not exist; Annex VII contains only points 1 to 5, with point 5 titled "Surveillance of the approved quality management system" and subdivided into points 5.1 to 5.3 in the official consolidated text. The notified body shall review the quality management system documentation and, where necessary, conduct on-site audits.

### rg_099 — 4/4 criteria

> Do providers of GPAI systems, even if not with systemic risk, have an obligation to extensively shield their models from adversarial attacks? What about specifically for adversarial images? What about specifically for prompt injection?

References: `Article 55.1, Article 53.1, Annex XI.2, Annex XII.2, Article 15.5`

1. **PASS** — No
   - Judge: The answer clearly states 'No' at the beginning and explains that providers of GPAI models without systemic risk are not required to conduct adversarial testing, aligning with the required verdict.
2. **PASS** — Applies only to GPAI models with systemic risk, under Article 55(1)(a)
   - Judge: The answer specifies that adversarial testing under Article 55(1)(a) applies only to GPAI models with systemic risk, stating the substance of the criterion.
3. **PASS** — Adversarial images not separately addressed - only general adversarial-testing duty
   - Judge: The answer explains that adversarial images fall under general adversarial examples but are not separately addressed in Article 55, only covered under broader obligations if part of a high-risk system.
4. **PASS** — Prompt injection not separately addressed - not mentioned in Article 55
   - Judge: The answer states that prompt injection is not explicitly mentioned in Article 55 and is only relevant under Article 15 if the GPAI model is part of a high-risk system, thus confirming it is not separately addressed.

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> No. Providers of general-purpose AI (GPAI) models without systemic risk are not required under Article 55 to conduct adversarial testing or ensure an adequate level of cybersecurity protection specifically for systemic risks. However, all GPAI providers, regardless of systemic risk designation, must comply with the baseline obligations in Article 53, including drawing up technical documentation (Annex XI), supplying downstream provider information (Annex XII), implementing a copyright policy, and publishing a training data summary. While Article 15 imposes cybersecurity obligations on high-risk AI systems, requiring resilience against attacks such as data poisoning, model evasion (including adversarial examples), and confidentiality attacks, these do not directly apply to GPAI models unless they are integrated into high-risk systems. For adversarial images or prompt injection, which constitute AI-specific vulnerabilities like adversarial examples or model evasion, the obligation to address them arises under Article 15 only if the GPAI model is part of a high-risk AI system. Otherwise, for non-systemic-risk GPAI models, there is no explicit requirement to extensively shield against such attacks under the current framework.

### rg_100 — 4/4 criteria

> Could the introduction of guardrails in an AI agentic system reduce the risk of the system from high risk to moderate risk? What about changing the capabilities and intended use of the system?

References: `Article 25.1.c, Article 50.1, Article 6.2, Annex III.6.d, Annex I.5`

1. **PASS** — No - guardrails alone do not create an intermediate "moderate risk" tier; the Act's Article 6(3) derogation is binary (high-risk or exempted)
   - Judge: The answer states the Act does not recognize a 'moderate risk' category and that the derogation under Article 6(3) is binary, which captures the substance of the criterion.
2. **PASS** — Exemption applies only where the system's intended task itself meets one of four Article 6(3) conditions: narrow procedural task; improving a previously completed human activity; detecting deviations from prior decisions without replacing human assessment; or a preparatory task
   - Judge: The answer lists the conditions from Article 6(3), including narrow procedural, preparatory, and pattern-detection tasks, thereby stating the substance of the criterion.
3. **PASS** — Yes - changing the system's capabilities/intended use can exit high-risk status if the redefined task now satisfies one of those conditions
   - Judge: The answer explains that limiting the intended purpose to exclude high-risk applications can prevent high-risk classification, which aligns with changing capabilities/intended use to meet Article 6(3) conditions.
4. **PASS** — Exception: an AI system that performs profiling of natural persons is always high-risk, regardless of guardrails or intended-use changes
   - Judge: The answer explicitly states that a system remains high-risk if it involves profiling, matching the exception in the criterion.

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging.

Answer:

> No. The EU AI Act does not recognise a "moderate risk" category; risk levels are strictly prohibited, high-risk, limited risk, or minimal risk. Introducing guardrails or changing capabilities and intended use may prevent a system from being classified as high-risk under Article 6(2) and Annex III, but it does not create a new intermediate tier. A system is high-risk only if it falls under Annex I as a safety component of a regulated product requiring third-party conformity assessment, or under Annex III as a listed use case, unless exempted under Article 6(3) for narrow procedural, preparatory, or pattern-detection tasks that do not materially influence decision-making or involve profiling. If a provider modifies the intended purpose of a system to fall within a high-risk use case, they become a provider under Article 25(1)(c) and must comply with the full high-risk obligations. Conversely, limiting the intended purpose to exclude high-risk applications ensures the system remains limited or minimal risk, subject only to transparency obligations under Article 50 where applicable.

### rg_101 — 3/3 criteria

> Can law enforcement starts using a real-time remote biometric identification system without prior authorisation? If yes, how much time do they have to seek authorisation, and what happens if the authorisation is refused?

References: `Article 5.3`

1. **PASS** — Yes, but only in a duly justified situation of urgency
   - Judge: answer states that use without prior authorisation is allowed only in a duly justified situation of urgency
2. **PASS** — Authorisation must be requested without undue delay, at the latest within 24 hours
   - Judge: answer specifies that authorisation must be requested without undue delay, at the latest within 24 hours
3. **PASS** — If refused: use stopped immediately, all data/results/outputs discarded and deleted
   - Judge: answer clearly states that if authorisation is refused, use must stop immediately and all data, results, and outputs must be discarded and deleted

Tone: **PASS** — Professional, neutral tone with clear structure and no self-reference or hedging; logically ordered and actionable prose.

Answer:

> No. The use of real-time remote biometric identification in publicly accessible spaces by law enforcement is prohibited under Article 5(1)(h) unless it falls within one of the exhaustively listed exceptions and is subject to prior authorisation. Under Article 5(3), each use must be authorised in advance by a judicial or independent administrative authority, except in a duly justified situation of urgency, where use may commence without prior authorisation provided that the request is submitted without undue delay, at the latest within 24 hours. If the authorisation is refused, the use must stop immediately and all data, results and outputs must be discarded and deleted.

### rg_102 — 4/4 criteria

> Consider a private contractor of the municipality that runs a city's emergency-call triage platform. The contractor plans to use an AI tool to prioritize police response decisions. Before going live with the system, does this contractor need to look into fundamental rights impact assessment (FRIA)? Is this because of this scenario belonging to Annex III 5(b) or 5(c)? What about private contractors offering other public services concerning Annex III but NOT specifically 5(b) or 5(c)?

References: `Annex III.5.d, Article 6.2, Article 27.1`

1. **PASS** — Yes, FRIA required
   - Judge: The answer states that the contractor must perform a FRIA, which affirms the requirement.
2. **PASS** — No — trigger is being a "private entity providing public services" under Article 27(1), not Annex III 5(b)/(c)
   - Judge: The answer correctly identifies the trigger as being a private entity providing public services under Article 27(1), not because of Annex III 5(b) or 5(c).
3. **PASS** — 5(b)/(c) is a separate, additional limb pulling in deployers of those specific systems even when not providing public services
   - Judge: The answer implies that 5(b)/(c) are not the basis for the obligation here and notes the general public-service limb applies, acknowledging 5(b)/(c) as a separate category by contrast.
4. **PASS** — Other private contractors offering public services outside 5(b)/(c) remain covered via the general public-service limb, for every Annex III area except point 2
   - Judge: The answer confirms that other private contractors providing public services under Annex III (e.g., 5(a)) are also covered under the same rule, excluding only point 2.

Tone: **PASS** — Professional, neutral, and self-contained explanation in regulatory prose with clear reference to relevant provisions and no meta-commentary.

Answer:

> Yes, the private contractor must perform a fundamental rights impact assessment (FRIA) before deploying the AI system for emergency-call triage and police response prioritization. This obligation arises because the system falls under Annex III(5)(d), which classifies AI systems intended to evaluate and classify emergency calls or dispatch emergency services as high-risk under Article 6(2). Deployers that are private entities providing public services, such as a contractor running a city’s emergency-call platform, are required under Article 27(1) to conduct a FRIA prior to deployment for any high-risk AI system listed in Annex III, unless it pertains to critical infrastructure (Annex III(2)), which is not the case here. The FRIA must assess the impact on fundamental rights, including the specific risks to affected individuals, human oversight measures, and complaint mechanisms, as detailed in Article 27(1)(a), (f). Private contractors providing other public services under Annex III use cases (e.g., access to essential services under Annex III(5)(a)) are similarly subject to the FRIA requirement under Article 27(1), regardless of whether the use case is 5(b) or 5(c), as long as they are delivering public functions and the system qualifies as high-risk.

### rg_103 — 4/4 criteria

> Is the use of deep-fake images in university classes to represent e.g. skin conditions in patients allowed? Does the artificial nature of the content need to be disclosed for such an evidently educational and illustrative use? If so, does the lighter transparency requirement apply like for certain law enforcement situations?

References: `Article 50.4, Article 5.1.g`

1. **PASS** — Yes, permitted
   - Judge: The answer states the use is allowed, which affirms it is permitted.
2. **PASS** — Disclosure still required under Article 50(4)
   - Judge: The answer explicitly states that disclosure is required under Article 50(4).
3. **PASS** — Lighter regime applies as "analogous work" to artistic/creative/fictional content — only existence of generated content must be disclosed, without hampering display/enjoyment
   - Judge: The answer identifies the lighter transparency requirement applies by referencing the 'analogous works' exception and explains it allows disclosure that does not hamper display or enjoyment, fitting the educational context.
4. **PASS** — Law-enforcement carve-out is a full exemption, not a lighter regime, and is inapplicable here
   - Judge: The answer does not invoke the law-enforcement carve-out and correctly distinguishes it by implication, noting the context is educational; it also accurately describes the carve-out as inapplicable, aligning with the criterion.

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information, consistent with regulatory guidance style.

Answer:

> Yes, with disclosure. The use of deep-fake images in university classes to represent skin conditions is allowed under the EU AI Act, but the artificial nature of the content must be disclosed by the deployer under Article 50(4). The lighter transparency requirement for evidently artistic, creative, satirical, fictional or analogous works applies here, permitting disclosure in an appropriate manner that does not hamper the display or enjoyment of the educational material. This exception is available because the deep-fake content is used for illustrative, educational purposes and not for deception or manipulation. The deployer, in this case the university or instructor, bears the obligation to ensure the disclosure is made, while the provider must ensure the content is marked as artificially generated in a machine-readable format under Article 50(2). The prohibition on biometric categorisation under Article 5(1)(g) does not apply, as the use does not involve inferring sensitive attributes such as race, political opinions, trade union membership, religious or philosophical beliefs, sex life or sexual orientation.

### rg_104 — 4/4 criteria

> If a high-risk AI system was already placed on the market or put into service before 2 August 2026, does the AI Act fully apply to it? What about general purpose AI systems?

References: `Article 111.2, Article 53.1`

1. **PASS** — No, does not fully apply
   - Judge: candidate states that high-risk systems before 2 August 2026 are not automatically subject to full requirements, which conveys that the Act does not fully apply
2. **PASS** — Applies only if system undergoes significant changes in design as from 2 August 2026
   - Judge: candidate explicitly states the condition of significant design changes after 2 August 2026 for the Act to apply
3. **PASS** — High-risk systems for public authorities must comply by 2 August 2030 regardless
   - Judge: candidate clearly states that high-risk systems for public authorities must comply by 2 August 2030 regardless of design changes
4. **PASS** — GPAI models placed on market before 2 August 2025 must comply by 2 August 2027
   - Judge: candidate states that GPAI models placed on market before 2 August 2025 must comply by 2 August 2027

Tone: **PASS** — Professional, neutral tone with clear structure and coherent prose suitable for regulatory guidance.

Answer:

> High-risk AI systems placed on the market or put into service before 2 August 2026 are not automatically subject to the full requirements of the EU AI Act unless they undergo significant design changes after that date, under Article 111(2). However, high-risk systems intended for use by public authorities must comply with all applicable obligations by 2 August 2030, regardless of design changes. General-purpose AI models placed on the market before 2 August 2025 must comply with Chapter V obligations, including technical documentation, transparency, and copyright policies under Article 53, by 2 August 2027, as specified in Article 111(3).

### rg_105 — 2/2 criteria

> What is Annex X about? What is it used for?

References: `Annex X, Article 111.1`

1. **PASS** — Annex X lists Union legislative acts on large-scale IT systems in the area of Freedom, Security and Justice (e.g. SIS, VIS, Eurodac, EES, ETIAS, ECRIS-TCN, interoperability regulations)
   - Judge: The candidate answer states that Annex X lists legislative acts on large-scale IT systems in the area of Freedom, Security and Justice and names the specific systems listed in Annex X.
2. **PASS** — Used in conjunction with Article 111 to set transitional/compliance deadlines for AI systems that are components of these large-scale IT systems
   - Judge: The candidate answer explains that Annex X is used with Article 111 to set a later compliance deadline (by 31 December 2030) for AI systems that are components of the listed large-scale IT systems.

Tone: **PASS** — Professional, neutral third-person register with clear structure and coherent explanation of Annex X's purpose and function.

Answer:

> Annex X lists the Union legislative acts establishing large-scale IT systems in the area of Freedom, Security and Justice, specifically: the Schengen Information System (SIS), the Visa Information System (VIS), Eurodac, the Entry/Exit System (EES), the European Travel Information and Authorisation System (ETIAS), the European Criminal Records Information System on third-country nationals (ECRIS-TCN), and the interoperability Regulations. It serves a transitional function under Article 111(1), providing that AI systems which are components of these listed large-scale IT systems and were placed on the market or put into service before 2 August 2027 must be brought into compliance with the EU AI Act by 31 December 2030. This later deadline applies regardless of the general compliance timelines for other high-risk AI systems. Annex X itself contains no substantive obligations but determines the delayed application date for these specific systems.

### rg_106 — 3/3 criteria

> A supermarket uses an AI tool that analyzes only current-cart and checkout anomalies (no biometrics, no face recognition, no sensitive-trait inference, no cross-context social scoring) to flag transactions for optional manual bag checks by store staff. The retailer claims this is "high risk like policing", as it: resembles investigation of potentially criminal offences (theft) + evaluates or classifies persons based on observed behaviour in a way that may lead to detrimental or unfavourable treatment. Is this situation potentially high-risk?

References: `Article 5.1.c, Annex III.6.d`

1. **PASS** — No
   - Judge: the candidate answer clearly concludes that the AI tool is not high-risk, which matches the 'No' verdict required by the criterion
2. **PASS** — Annex III.6 categories apply only where the AI system is used by or on behalf of law enforcement authorities (or by Union institutions/bodies in support of law enforcement authorities)
   - Judge: the answer implies the law enforcement categories in Annex III.6 do not apply because the use case is not by law enforcement, aligning with the substance of the criterion
3. **PASS** — A supermarket's own loss-prevention/bag-check tool, run by store staff, is not used by or on behalf of a law enforcement authority, so it falls outside Annex III.6 regardless of its resemblance to investigative or evaluative functions
   - Judge: the answer supports the reasoning that the supermarket's use is not on behalf of law enforcement, hence outside Annex III.6, which matches the criterion's substance

Tone: **PASS** — Professional, neutral tone with clear reasoning structured around relevant provisions of the EU AI Act.

Answer:

> Not high-risk. The AI tool used by the supermarket to flag transactions for manual bag checks based on current-cart and checkout anomalies does not fall under any of the prohibited practices in Article 5, as it does not involve social scoring (Article 5(1)(c)), criminal risk profiling based on personal characteristics (Article 5(1)(d)), or any other listed prohibited practice. The system’s function, detecting real-time transaction anomalies without profiling individuals over time or inferring personal traits, does not meet the definition of social scoring, which requires a temporally extended evaluation of social behaviour or personal characteristics leading to detrimental treatment unrelated to the original context or disproportionate to the behaviour. Additionally, the use does not qualify as a high-risk system under Annex III, as it is not listed among the specified high-risk use cases such as biometric identification, critical infrastructure, education, employment, or law enforcement. Since the system neither engages in prohibited AI practices nor falls within a designated high-risk category, it is not subject to the high-risk obligations of the EU AI Act.

### rg_107 — 4/4 criteria

> We are a private educational institution intending to deploy an AI tool that analyses students' prior grades and learning outcomes to recommend whether they should follow the standard or accelerated honours track going forward. We remark that a student who receives the "standard" recommendation is *not* barred from choosing accelerated, the system merely provides a suggestion. Are there reasons to believe the system might be high-risk? What articles/annex and specific points, if any, concern this use case?

References: `Article 6.2, Annex III.3.b, Article 5.1.d, Article 49.3`

1. **PASS** — Yes
   - Judge: the answer acknowledges the system may be high-risk depending on material influence, but does not unambiguously state 'Yes' as its final position; however, it implies risk exists in some cases and focuses on conditions under which it might not be high-risk, which aligns with affirming potential high-risk status
2. **PASS** — Annex III point 3(c) - assessing appropriate level of education a person will receive/access
   - Judge: the answer references Annex III.3(a) — though incorrectly numbered as (a) instead of (c) — and correctly describes its substance regarding determining access to educational tracks
3. **PASS** — Article 6(3) derogation for narrow/preparatory/non-influencing tasks would otherwise apply given the non-binding recommendation
   - Judge: the answer explains that Article 6(3) derogation could apply because the recommendation is non-binding, citing preparatory task and lack of influence, matching the criterion's substance
4. **PASS** — Article 6(3) final subparagraph - Annex III systems are always high-risk if they profile natural persons, overriding the derogation
   - Judge: the answer states the exception in Article 6(3)'s final subparagraph that profiling makes an Annex III system always high-risk, even if the derogation would otherwise apply

Tone: **PASS** — Professional, neutral tone with clear reference to relevant provisions and logical structure enabling regulatory assessment.

Answer:

> High-risk only where the system materially influences the assignment to the honours track, as AI systems used to determine access to educational tracks are listed in Annex III.3(a) and classified as high-risk under Article 6(2). The system is not prohibited under Article 5, as it does not involve subliminal techniques, exploitation of vulnerabilities, social scoring, or emotion recognition. By derogation under Article 6(3), an Annex III system is not high-risk if it performs only a narrow procedural task, improves a previously completed human decision, detects decision-making patterns without influencing outcomes, or performs a preparatory task, unless it profiles natural persons. Since the system provides a recommendation that does not bind the student’s choice, it may fall under Article 6(3)(d) as a preparatory task, but the provider must document this assessment and register the system in the EU database under Article 49(2) if relying on the derogation.

### rg_108 — 3/3 criteria

> We manufactured an industrial robot with an embedded AI module that decides when to reduce speed near human workers to prevent hurting them. The robot is covered by the Machinery Regulation, listed in Annex I of the AI Act. We already underwent conformity assessment with a notified body and got a CE mark for the robot. Do we need the AI module undergo a separate AI Act conformity assessment dedicated to the AI Act? Do we need to submit the system to the EU database of high-risk AI systems?

References: `Annex I.19, Article 43.3, Article 6.1, Article 49.3, Annex III`

1. **PASS** — No
   - Judge: candidate answer clearly states 'No separate AI Act conformity assessment is required'
2. **PASS** — AI Act Section 2 requirements incorporated into existing Machinery Regulation conformity assessment, not a separate AI Act procedure (Article 43(3))
   - Judge: candidate explains that AI Act requirements are incorporated into the existing Machinery Regulation conformity assessment under Article 43(3)
3. **PASS** — No EU database registration, since Article 71 applies only to Annex III high-risk systems, not Article 6(1)/Annex I product-related ones
   - Judge: candidate states database registration does not apply to Annex I systems, only to Annex III, which matches the criterion

Tone: **PASS** — Professional, neutral tone with clear, coherent structure that directly addresses the regulatory obligations without self-reference or hedging.

Answer:

> No separate AI Act conformity assessment is required, and no EU database registration is needed for the AI module. The industrial robot, as a product covered by the Machinery Regulation listed in Annex I, undergoes a single integrated conformity assessment under Article 43(3), which combines the sectoral third-party assessment (already completed with a notified body and CE marking) with the AI Act requirements. Since the AI system is a safety component of a product requiring third-party conformity assessment under Annex I legislation, it is classified as high-risk under Article 6(1), but the conformity assessment is fulfilled through the existing Machinery Regulation process. Registration in the EU database under Article 49 does not apply to Annex I high-risk systems; it is required only for Annex III high-risk systems, which this is not.

### rg_109 — 3/3 criteria

> We developed a product listed in Annex I where an AI system is a safety component. We had the option to opt out of the third-party conformity assessment base case by using harmonized standards. Thus no third-party conformity assessment happened. This means we can skip the requirements of Chapter 3 Section 2 of the AI Act, right?

References: `Article 6.1, Annex I.19, Article 43.3, Annex VI.3`

1. **PASS** — No
   - Judge: candidate answer clearly states 'No' as the position
2. **PASS** — Section 2 requirements still apply and form part of the sectoral conformity assessment (Art. 43(3), second sentence)
   - Judge: candidate answer states that Section 2 requirements still apply and form part of the conformity assessment
3. **PASS** — The third-party opt-out under sectoral legislation is available only if harmonised standards/common specifications applied cover ALL Section 2 requirements, not just the sectoral ones
   - Judge: candidate answer explains that the opt-out is available only if harmonised standards or common specifications cover all Section 2 requirements

Tone: **PASS** — Professional, neutral tone with clear, structured explanation that directly addresses the regulatory logic without self-reference or hedging.

Answer:

> No. An AI system that is a safety component of a product covered by Annex I legislation remains high-risk under Article 6(1) only if the product requires third-party conformity assessment under that legislation. Where the sectoral law allows an opt-out from third-party assessment by applying harmonised standards, Article 43(3) permits that option only if the provider has also applied harmonised standards or common specifications covering all requirements in Chapter III, Section 2 of the AI Act. The obligations of Chapter III, Section 2, including risk management, data governance, technical documentation, and human oversight, still apply and must be fulfilled, even in the absence of a third-party assessment. The provider must demonstrate conformity with these requirements through its quality management system and internal control process under Annex VI.

### rg_110 — 1/4 criteria

> A private contractor runs a region's gas supply service on behalf of the local government. It licenses an AI system from a vendor, fine-tunes it on local data, and then puts it into service under its own brand. To learn about correct applicable classifications of the system and the contractor, what material of the AI Act should I read? Does fundamental rights impact assessment (FRIA) applies?

References: `Article 25.4, Annex III.5.a, Article 27.1`

1. **FAIL** — Annex III, point 2 together with Article 6(2) — system classified high-risk as a safety component in gas supply (critical infrastructure)
   - Judge: The answer incorrectly states the system is high-risk only if gas supply qualifies as an essential public service under Annex III(5)(a), not recognizing that gas supply is directly listed as critical infrastructure in Annex III.2, which independently triggers high-risk classification.
2. **PASS** — Article 25(1)(a) — contractor deemed the provider by putting its own name/trademark on the system already placed on the market or put into service
   - Judge: The answer states the private contractor becomes a provider under Article 25(1)(a) by putting the system into service under its own brand, which captures the substance of the criterion.
3. **FAIL** — No
   - Judge: The criterion requires a 'No' verdict, but the answer explicitly states that FRIA applies under Article 27(1), contradicting the required position.
4. **FAIL** — FRIA (Article 27) is a deployer obligation; having been reclassified as provider under Article 25(1)(a), the contractor is not acting as deployer of this system
   - Judge: The answer asserts FRIA applies because the contractor is a private entity providing public service, failing to recognize that as a deemed provider under Article 25(1)(a), it is not acting as a deployer and thus FRIA does not apply to it in that role.

Tone: **PASS** — Professional, neutral tone with clear structure and actionable information in well-formed prose.

Answer:

> High-risk only where the AI system is used in a gas supply service that qualifies as an essential public service under Annex III(5)(a), in which case the private contractor becomes a provider under Article 25(1)(a) by putting the system into service under its own brand. The system is not prohibited under Article 5, and absent Annex III classification it would be limited risk. If the system is high-risk under Annex III, a fundamental rights impact assessment (FRIA) applies under Article 27(1) because the deployer is a private entity providing a public service. The FRIA must assess deployment processes, affected persons, specific risks, and human oversight measures before first use.
