# Judged subset: live answers with per-criterion judge remarks

- PARTIAL. The judging run was stopped early; 77 of 220 rows carry judge remarks. Metrics below are computed over the judged subset only and are NOT corpus figures. The complete-corpus values are in r390-full-110-live-answers-and-verdicts.json.
- Judge: Claude Sonnet 5 via OpenRouter, temperature 0.1, 3 repetitions for answer correctness and 3 for regulatory tone, per-criterion majority with ties resolving to FAIL, judged 9 September 2026.
- Capture: 2026-09-07, full live run of all 110 questions in both modes
- Answer key: reconstructed (evals/official/build_gold.py); criteria and reference answers are ours, not the evaluator's. The six appendix questions are the only ones with the evaluator's own printed criteria.

| | Easy | Hard |
|---|---:|---:|
| Rows judged | 77 of 110 | 0 of 110 |
| Ans. Correctness (Loose) | 85.283 | None |
| Ans. Correctness (Strict) | 71.4286 | None |
| Ans. Conciseness | 73.5246 | None |
| Ref. Correctness (Loose) | 96.4286 | None |
| Ref. Correctness (Strict) | 72.1429 | None |
| Ref. Conciseness | 59.8612 | None |

Subset figures only. Answer conciseness and the three reference metrics are computed by formula and carry no judge variance; the two answer-correctness rows depend on the judge.

---

# EASY MODE (77 rows judged)

## rg_001 (easy) - 2/2

> Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?

**AnsConc 100.0 | RefL None | RefS None | RefC None**

`refs: Article 11.1, Annex IV.2` | `expected: not annotated` | 387 chars | 4.52s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer begins with 'Yes'_
2. `[PASS]` Description of the hardware on which the AI system is intended to run (Annex IV.1.e)
    - _States hardware description requirement under Annex IV point 1(e)_

Tone: `PASS` _Professional, precise, well-structured answer citing specific provisions._

**Answer**

> Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).

## rg_002 (easy) - 2/2

> Does the obligation to indicate that deep-fakes are artificially generated apply when prosecuting a criminal offence?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 50.4` | `expected: Article 50.4` | 382 chars | 0.08s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No
    - _Answer states 'No' clearly as its position._
2. `[PASS]` Deep-fake disclosure exemption covers detection, prevention, investigation or prosecution of criminal offences
    - _Answer names detection, prevention, investigation, prosecution as the exemption scope._

Tone: `PASS` _Professional, well-structured, and directly answers the question with proper citation._

**Answer**

> No. Under Article 50(4), the deployer's duty to disclose that image, audio, or video content constituting a deep fake has been artificially generated or manipulated does not apply where the use is authorised by law to detect, prevent, investigate, or prosecute criminal offences. Absent that law-enforcement authorisation, the deployer must disclose that the content is a deep fake.

## rg_003 (easy) - 4/4

> When the intended use of an AI system is listed in Annex III of the EU AI Act, the AI system is automatically high-risk, isn't it? If not, can you explain when that is not the case?

**AnsConc 67.19 | RefL 100.0 | RefS 0.0 | RefC 33.33**

`refs: Annex III.7.b, Article 6.2, Article 49` | `expected: Article 6.3` | 1079 chars | 5.48s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No
    - _Answer states 'Not always', matching a No verdict._
2. `[PASS]` Exception applies where system does not pose significant risk of harm to health, safety or fundamental rights, including by not materially influencing outcome of decision making
    - _States exception applies when no significant risk of harm, including not materially influencing outcome._
3. `[PASS]` Exception requires one of: narrow procedural task; improving result of previously completed human activity; detecting deviations from prior decision-making patterns without replacing/influencing human assessment; preparatory task to an Annex III assessment
    - _Lists all four conditions: narrow procedural task, improving prior human activity, detecting deviations without influencing assessment, preparatory task._
4. `[PASS]` Exception never applies (system is always high-risk) if it performs profiling of natural persons
    - _States derogation never applies for profiling, which is always high-risk._

Tone: `PASS` _Professional, well-structured explanation of Article 6(3) derogation without self-reference or hedging._

**Answer**

> Not always. Under Article 6(2) an AI system falling within one of the lettered use cases listed under the eight areas of Annex III is high-risk, but Article 6(3) provides a derogation: such a system is not high-risk where it does not pose a significant risk of harm to health, safety or fundamental rights, including by not materially influencing the outcome of decision making, and it is intended to perform a narrow procedural task, to improve the result of a previously completed human activity, to detect decision-making patterns or deviations from prior decision-making patterns without being meant to replace or influence the previously completed human assessment without proper human review, or to perform a preparatory task to an assessment relevant to an Annex III use case. That derogation never applies where the system performs profiling of natural persons, in which case it is always high-risk. A provider relying on Article 6(3) must document that assessment before placing the system on the market and still register the system in the EU database under Article 49.

## rg_004 (easy) - 4/4

> I have a medical device that has an AI system as a safety component. The medical device is classified "medium-risk" and undergoes a 3rd party conformity assessment. Is the AI system "medium risk" too? If yes, why? If not, why not?

**AnsConc 76.48 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 6.1, Article 43.3, Annex I` | `expected: Article 6.1` | 897 chars | 7.51s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes - high-risk (AI Act has no "medium-risk" category)
    - _Answer confirms AI system is high-risk since no medium-risk tier exists._
2. `[PASS]` Condition (a): AI system is safety component of a product covered by Annex I legislation (medical devices under Regulation (EU) 2017/745)
    - _States AI system is safety component of product covered by MDR under Annex I._
3. `[PASS]` Condition (b): that product is required to undergo third-party conformity assessment
    - _States the product must undergo third-party conformity assessment._
4. `[PASS]` Both conditions cumulative under Article 6(1), irrespective of the device's own sectoral risk classification
    - _States both conditions are cumulative and device's own risk class is irrelevant._

Tone: `PASS` _Professional, well-structured explanation with clear legal reasoning._

**Answer**

> No, the AI system is high-risk, because the Act recognises no "medium risk" tier and does not import the sectoral risk class of the host product. Article 6(1) classifies an AI system as high-risk where both conditions are met: it is intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in Annex I, which includes the Medical Device Regulation (EU) 2017/745, and that product is required to undergo a third-party conformity assessment for its placing on the market. Both limbs are satisfied here, so the medical device's own "medium-risk" classification is irrelevant to the AI classification. The consequence is that the Chapter III Section 2 requirements apply to the AI system and, under Article 43(3), they are assessed as part of the MDR notified-body conformity assessment procedure, a single integrated procedure covering both regimes.

## rg_005 (easy) - 2/3  **FAILS**

> Does the EU AI Act explicitly requires to use explainable AI techniques such as LIME or SHAP to increase the trustworthiness of high-risk AI systems?

**AnsConc 100.0 | RefL 100.0 | RefS 0.0 | RefC 33.33**

`refs: Article 13.3, Article 14.4, Article 15.1` | `expected: Article 13.1` | 340 chars | 0.02s | judge spread [0.667, 0.667, 1.0]

1. `[PASS]` No
    - _Answer clearly states no technique is mandated._
2. `[PASS]` Article 13 requires sufficient transparency/interpretability for deployers, without naming a technique
    - _States Article 13 requires sufficient transparency for deployer interpretability without naming a technique._
3. `[FAIL]` Requirement is outcome-based and technology-neutral, leaving choice of method to the provider
    - _Does not state the requirement is outcome-based/technology-neutral with choice left to the provider._

Tone: `PASS` _Professional, direct, well-structured answer citing relevant articles._

**Answer**

> No, the EU AI Act mandates no specific explainable-AI technique such as LIME or SHAP, and Article 13 instead requires only that high-risk AI systems be sufficiently transparent for deployers to interpret their output. Article 14 requires effective human oversight, and Article 15 requires appropriate accuracy, robustness and cybersecurity.

## rg_006 (easy) - 1/3  **FAILS**

> Does the EU AI Act apply to AI systems or AI models or both?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 2.1.a, Article 3.1, Article 51.1` | `expected: Article 2.1.a` | 484 chars | 0.03s | judge spread [0.333, 0.333, 0.333]

1. `[PASS]` Both AI systems and AI models
    - _Answer explicitly covers both AI systems and GPAI models as regulated subjects._
2. `[FAIL]` Art 2(1)(a): providers placing/putting into service AI systems
    - _Answer only vaguely references Article 2 without stating providers placing on market or putting into service._
3. `[FAIL]` Art 2(1)(a): providers placing general-purpose AI models on the market
    - _Answer mentions provider obligations but does not state that models are placed on the market._

Tone: `PASS` _Professional, well-structured explanation distinguishing AI systems and AI models with clear statutory references._

**Answer**

> The EU AI Act's core regime governs AI systems, defined in Article 3(1) and brought within scope by Article 2, through the risk-based tiers (prohibited practices under Article 5, high-risk systems under Article 6, and limited-risk transparency duties under Article 50). General-purpose AI models are regulated separately under Chapter V (Articles 51 to 56), are defined in Article 3(63), and carry their own provider obligations with additional duties for models posing systemic risk.

## rg_007 (easy) - 3/3

> We want to deploy an AI system that performs biometric verification solely to confirm that a specific natural person is the person he or she claims to be. Is this system prohibited? Is it high-risk?

**AnsConc 43.34 | RefL 100.0 | RefS 100.0 | RefC 40.0**

`refs: Article 5.1.g, Article 6.2, Article 50.3, Annex III.1.a, Annex I` | `expected: Annex III.1.a, Article 5.1` | 1239 chars | 8.77s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No, not prohibited
    - _States it is not prohibited_
2. `[PASS]` No, not high-risk
    - _States it is not high-risk on the biometrics route_
3. `[PASS]` Falls within Annex III.1(a) biometric verification exclusion
    - _Explicitly cites the Annex III.1(a) exclusion for sole-purpose biometric verification_

Tone: `PASS` _Professional, structured analysis in neutral third-person register with clear legal reasoning._

**Answer**

> Not prohibited, and not high-risk on the biometrics route. Biometric verification whose sole purpose is to confirm that a specific natural person is the person he or she claims to be is expressly excluded from the remote biometric identification use case in Annex III(1)(a), so Article 6(2) does not classify it as high-risk on that basis, and it is none of the practices banned by Article 5, which reaches biometric categorisation only where the system deduces or infers race, political opinions, trade union membership, religious or philosophical beliefs, sex life or sexual orientation. It would nonetheless become high-risk if the verification function serves another listed Annex III use case, for example verifying candidates in recruitment or worker management under Annex III(4), or if under Article 6(1) it is a safety component of, or itself, a product covered by the Annex I Union harmonisation legislation requiring third-party conformity assessment. Absent those conditions the system is limited risk at most, since Article 50 imposes transparency duties only on the specified interaction, synthetic-content, emotion recognition and biometric categorisation scenarios, none of which a pure identity-confirmation check engages.

## rg_008 (easy) - 4/4

> Are AI safety components within medical devices of MDR class IIa, IIb, or III considered to be high-risk according to the EU AI Act? Why?

**AnsConc 69.31 | RefL 100.0 | RefS 0.0 | RefC 100.0**

`refs: Article 6.2, Annex I.19` | `expected: Article 6.1, Annex I.a.11` | 922 chars | 6.89s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer states 'Yes' as clear verdict._
2. `[PASS]` Condition: AI system is a safety component of a product covered by Union harmonisation legislation listed in Annex I (the MDR)
    - _States AI system as safety component of MDR product covered by Annex I._
3. `[PASS]` Condition: that product must undergo third-party (notified body) conformity assessment to be placed on the market (Article 6(1))
    - _States product must undergo third-party notified body conformity assessment before placing on market._
4. `[PASS]` MDR classes IIa, IIb, III require notified-body conformity assessment, so both cumulative conditions are met
    - _States classes IIa, IIb, III require notified-body assessment, satisfying both conditions._

Tone: `PASS` _Professional, well-structured, and legally coherent explanation without self-reference or hedging._

**Answer**

> Yes. An AI system intended to be used as a safety component of a medical device is high-risk under Article 6(1), because both cumulative conditions are met: the product is covered by the Union harmonisation legislation listed in Annex I, which includes Regulation (EU) 2017/745 (MDR) at point 11, and a device of MDR class IIa, IIb or III must undergo a third-party conformity assessment involving a notified body before being placed on the market or put into service. Class I devices, which self-certify without notified-body involvement, do not satisfy the Article 6(1)(b) condition and are therefore not high-risk on this route. The applicable conformity assessment for such a safety component is governed by Article 43, carried out within the notified-body procedure under the MDR itself, so the Chapter III Section 2 requirements are verified through the sectoral assessment rather than a separate parallel procedure.

## rg_009 (easy) - 5/5

> What documentation does a provider of a high-risk AI system needs to keep available for the national competent authorities, and for how long?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 20.0**

`refs: Article 18.1, Article 11.1, Article 17.1, Article 47.1, Article 19.1` | `expected: Article 18.1` | 606 chars | 0.02s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Technical documentation (Article 11)
    - _Technical documentation (Article 11) explicitly mentioned_
2. `[PASS]` Quality management system documentation (Article 17)
    - _Quality management system documentation (Article 17) mentioned_
3. `[PASS]` Notified body change documentation and decisions/other documents, where applicable
    - _Notified body change documentation and decisions/documents explicitly listed_
4. `[PASS]` EU declaration of conformity (Article 47)
    - _EU declaration of conformity (Article 47) mentioned_
5. `[PASS]` 10 years after the system is placed on the market or put into service
    - _States 10 years after placement on market or put into service_

Tone: `PASS` _Neutral, well-structured professional summary with correct citations and no self-reference._

**Answer**

> Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.

## rg_010 (easy) - 3/5  **FAILS**

> Which article of the EU AI Act governs human oversight measures?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 14.4` | `expected: Article 14` | 621 chars | 3.87s | judge spread [0.6, 0.6, 0.6]

1. `[PASS]` Article 14
    - _Explicitly names Article 14._
2. `[PASS]` Design for effective human oversight during use
    - _States systems must be designed for effective oversight during use._
3. `[FAIL]` Aim: prevent/minimise risks to health, safety, fundamental rights
    - _Does not mention the aim of preventing/minimising risks to health, safety or fundamental rights._
4. `[FAIL]` Measures built in by provider and/or implemented by deployer
    - _Does not mention that measures may be built in by the provider and/or implemented by the deployer._
5. `[PASS]` Overseers enabled to understand, monitor, interpret, override, and halt the system
    - _Lists understanding, monitoring, interpreting, overriding, and halting capabilities for overseers._

Tone: `PASS` _Professional, well-structured explanation with accurate legal register._

**Answer**

> Article 14 governs human oversight, requiring high-risk AI systems to be designed and developed, including with appropriate human-machine interface tools, so that they can be effectively overseen by natural persons during the period in which they are in use. The measures under Article 14(4) must enable those persons to understand the system's capabilities and limitations and monitor its operation, remain aware of automation bias, correctly interpret the output, decide not to use the system or disregard, override or reverse the output, and intervene or interrupt operation through a stop button or similar procedure.

## rg_011 (easy) - 2/3  **FAILS**

> What is the meaning and purpose of 'testing data' in the context of AI systems, and why is it important that it is not leaked during the training process?

**AnsConc 100.0 | RefL 100.0 | RefS 0.0 | RefC 50.0**

`refs: Article 3.32, Article 10.2` | `expected: Article 10.3` | 476 chars | 0.02s | judge spread [0.667, 0.667, 0.667]

1. `[PASS]` Testing data is one of the training/validation/testing data sets under Article 10(1), used to check the high-risk AI system against its intended purpose after training and validation
    - _States testing data checks the system's performance before deployment, consistent with post-training verification of intended purpose._
2. `[FAIL]` It must meet the Article 10(3) quality criteria: relevant, sufficiently representative, to the best extent possible free of errors, complete, and with appropriate statistical properties for the intended purpose
    - _Does not mention the Article 10(3) quality criteria (representativeness, error-free, completeness, statistical properties)._
3. `[PASS]` Leakage of training data into the testing set destroys the set's independence, so it can no longer reliably verify Article 10(3) compliance and instead yields inflated, misleading accuracy that masks errors, biases or gaps
    - _Explains leakage means system is assessed on seen data, inflating performance and defeating the independent check._

Tone: `PASS` _Professional, neutral, well-structured explanation with clear reasoning._

**Answer**

> Testing data is defined in Article 3(32) as data used to provide an independent evaluation of the AI system, in order to confirm its expected performance before it is placed on the market or put into service. If testing data leaks into the training process, the system is in effect assessed on data it has already seen, which inflates its apparent performance and defeats the purpose of the independent check that Article 10 requires for the datasets of a high-risk AI system.

## rg_012 (easy) - 3/3

> What are the high-risk uses of AI systems listed under 'Administration of justice and democratic processes' cited in the EU AI Act?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Annex III.8` | `expected: Annex III.8` | 691 chars | 0.01s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` AI systems assisting a judicial authority (or on its behalf) in researching/interpreting facts and law and applying law to facts, or used similarly in alternative dispute resolution
    - _Candidate states the judicial assistance and ADR use case matching the criterion._
2. `[PASS]` AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote
    - _Candidate states influencing election/referendum outcomes or voting behaviour, matching the criterion._
3. `[PASS]` Exclusion: does not cover AI systems whose output natural persons are not directly exposed to, e.g. tools organising/optimising/structuring political campaigns administratively or logistically
    - _Candidate gives the campaign-tool exclusion example, capturing the substance of the carve-out._

Tone: `PASS` _Neutral, well-structured summary of Annex III point 8 with clear enumeration._

**Answer**

> Annex III point 8 lists two high-risk use cases under administration of justice and democratic processes. Annex III point 8(a) covers AI systems intended to be used by a judicial authority, or on its behalf, to assist in researching and interpreting facts and the law and in applying the law to a concrete set of facts, or to be used similarly in alternative dispute resolution. Annex III point 8(b) covers AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, with a carve-out for tools that only organise, optimise or structure political campaigns from an administrative or logistical point of view.

## rg_013 (easy) - 5/5

> Under what conditions should providers of general-purpose AI models be subject to exceptions regarding transparency-related requirements, if any? And what do those exceptions not cover?

**AnsConc 72.37 | RefL 100.0 | RefS 100.0 | RefC 25.0**

`refs: Article 53.2, Article 51.1, Article 55.2, Annex XI.2` | `expected: Article 53.2` | 1075 chars | 0.02s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes, exceptions exist
    - _States exceptions exist under Article 53(2)_
2. `[PASS]` Condition: model released under free and open-source licence allowing access, usage, modification and distribution
    - _States condition of free and open-source licence allowing access, usage, modification, distribution_
3. `[PASS]` Condition: parameters (weights, architecture info, usage info) made publicly available
    - _States condition of publicly available parameters, weights, architecture and usage info_
4. `[PASS]` Exception covers only points (a) and (b) of Article 53(1), not (c)/(d)
    - _Explicitly limits exception to (a) and (b), notes (c) and (d) still apply_
5. `[PASS]` Exception does not apply to general-purpose AI models with systemic risk
    - _States exception does not apply to systemic risk models_

Tone: `PASS` _Professional, precise, well-structured legal exposition with clear enumeration of conditions and exclusions._

**Answer**

> The exceptions to the GPAI transparency-related obligations are set out in Article 53(2). The Article 53(1)(a) duty to draw up and keep up-to-date the technical documentation of the model (Annex XI) and the Article 53(1)(b) duty to provide information and documentation to downstream providers (Annex XII) do not apply to providers that release the model under a free and open-source licence allowing access, usage, modification and distribution, where the model parameters, including the weights, and information on the model architecture and usage, are made publicly available. The exception does not cover the remaining Article 53(1) obligations: the policy to comply with Union copyright law (Article 53(1)(c)) and the publicly available, sufficiently detailed summary of the training content (Article 53(1)(d)) apply regardless of the licence. The exception also does not apply to general-purpose AI models with systemic risk (Article 53(2), second subparagraph), which remain subject to the full Article 53 obligations together with the Article 55 systemic-risk duties.

## rg_014 (easy) - 4/4

> Which AI systems used in education or vocational training should be classified as high-risk according to the EU AI Act?

**AnsConc 47.95 | RefL None | RefS None | RefC None**

`refs: Article 6.2, Annex III.3` | `expected: not annotated` | 1293 chars | 7.47s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Access, admission, or assignment to educational/vocational training institutions at all levels
    - _States systems for access, admission, or assignment to institutions at all levels._
2. `[PASS]` Evaluating learning outcomes, including to steer the learning process
    - _States systems evaluating learning outcomes including steering the learning process._
3. `[PASS]` Assessing the appropriate level of education an individual will receive or can access
    - _States systems assessing appropriate level of education one can receive or access._
4. `[PASS]` Monitoring/detecting prohibited student behaviour during tests
    - _States systems monitoring/detecting prohibited student behaviour during tests._

Tone: `PASS` _Professional and neutral, though the final sentence is dense and could be split for readability._

**Answer**

> Four use cases under the education and vocational training area of Annex III are high-risk, and they are classified as such by Article 6(2), which makes any AI system listed in Annex III high-risk. They are systems intended to determine access or admission or to assign natural persons to educational and vocational training institutions at all levels, systems intended to evaluate learning outcomes, including where those outcomes are used to steer the learning process, systems intended to assess the appropriate level of education that an individual will receive or be able to access, and systems intended for monitoring and detecting prohibited behaviour of students during tests. Each applies in the context of or within educational and vocational training institutions at all levels. Under the Article 6(3) derogation such a system is not high-risk where it poses no significant risk of harm and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or performs a preparatory task, but it remains high-risk whenever it profiles natural persons, and the provider must document that self-assessment before placing the system on the market.

## rg_015 (easy) - 3/3

> What obligations, if any, does the EU AI Act set in place for AI systems that interact directly with natural persons? What exceptions, if any, apply?

**AnsConc 70.44 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 50.1, Article 50.3` | `expected: Article 50.1` | 1086 chars | 8.48s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Obligation: providers must design/develop the system so natural persons are informed they are interacting with an AI system
    - _States providers must design/develop systems so persons are informed they interact with an AI system_
2. `[PASS]` Exception: not required where obvious to a reasonably well-informed, observant and circumspect person, given the circumstances and context of use
    - _States the obviousness exception with the reasonably well-informed, observant and circumspect standard and context_
3. `[PASS]` Exception: AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to safeguards for third parties' rights and freedoms — unless available for the public to report a criminal offence
    - _States the law enforcement exception with safeguards and the carve-out for public crime-reporting systems_

Tone: `PASS` _Professional, well-structured, and specific regulatory explanation with correct register throughout._

**Answer**

> Providers must ensure that AI systems intended to interact directly with natural persons are designed and developed so that the persons concerned are informed they are interacting with an AI system, under the transparency obligation in Article 50(1), unless this is obvious from the point of view of a natural person who is reasonably well-informed, observant and circumspect, taking into account the circumstances and context of use. That information must be given to the natural persons concerned in a clear and distinguishable manner at the latest at the time of the first interaction or exposure, and must conform to the applicable accessibility requirements under Article 50(5). One exception applies: the disclosure duty does not attach to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties. That exception is itself reversed where such systems are available for the public to report a criminal offence, in which case the Article 50(1) disclosure is required.

## rg_016 (easy) - 2/2

> What are the administrative fines for non-compliance with the prohibition of the AI practices?

**AnsConc 31.05 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 99.3, Article 5.1.g` | `expected: Article 99.3` | 1024 chars | 6.7s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` EUR 35,000,000 or 7% of total worldwide annual turnover for the preceding financial year, whichever is higher
    - _States EUR 35,000,000 or 7% of worldwide annual turnover, whichever is higher._
2. `[PASS]` Applies to non-compliance with Article 5 prohibited AI practices
    - _Explicitly ties the fine to non-compliance with Article 5 prohibited AI practices._

Tone: `PASS` _Professional, well-organized, and directly answers with correct structure and no self-referential hedging._

**Answer**

> Non-compliance with the Article 5 prohibition of AI practices attracts administrative fines of up to EUR 35 000 000 or, where the offender is an undertaking, up to 7 % of its total worldwide annual turnover for the preceding financial year, whichever is higher, under Article 99(3). This is the highest of the three ceilings in the penalty regime, above the EUR 15 000 000 or 3 % tier in Article 99(4) for operator and notified-body breaches and the EUR 7 500 000 or 1 % tier in Article 99(5) for supplying incorrect, incomplete or misleading information to notified bodies or competent authorities. For SMEs, including start-ups, Article 99(6) reverses the rule so the applicable ceiling is the lower of the percentage or the fixed amount. Article 5 is the provision breached, prohibiting eight practices including subliminal or manipulative techniques causing significant harm, exploitation of vulnerabilities, social scoring, and real-time remote biometric identification in publicly accessible spaces by law enforcement.

## rg_017 (easy) - 3/3

> How does Annex II relate to prohibited uses of AI systems?

**AnsConc 42.11 | RefL 100.0 | RefS 50.0 | RefC 100.0**

`refs: Annex II, Article 5.1.h` | `expected: Article 5.1.h.iii, Annex II` | 1724 chars | 12.37s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Annex II lists criminal offences (does not itself prohibit anything)
    - _States Annex II does not itself prohibit anything and lists offences._
2. `[PASS]` Referenced in Article 5(1)(h)(iii) as basis for one exception to the Article 5(1)(h) prohibition on 'real-time' remote biometric identification in public spaces for law enforcement
    - _States Annex II is referenced in Article 5(1)(h)(iii) as basis for one exception to the prohibition._
3. `[PASS]` Exception (localising/identifying a suspect) applies only if the offence is listed in Annex II and punishable by a custodial sentence/detention order of max at least four years
    - _States offence must be listed in Annex II and punishable by custodial sentence of at least four years._

Tone: `PASS` _Professional, neutral, well-structured explanation without self-reference or hedging._

**Answer**

> Annex II does not itself prohibit anything. It operates as the closed list of serious criminal offences referred to in Article 5(1), first subparagraph, point (h)(iii), which is one of the three narrow exceptions to the Article 5 prohibition on real-time remote biometric identification in publicly accessible spaces for law enforcement purposes, and the offence must be punishable in the Member State concerned by a custodial sentence of at least four years. The listed offences are terrorism, trafficking in human beings, sexual exploitation of children and child pornography, illicit trafficking in narcotic drugs or psychotropic substances, illicit trafficking in weapons, munitions or explosives, murder, grievous bodily injury, illicit trade in human organs or tissue, illicit trafficking in nuclear or radioactive materials, kidnapping, illegal restraint or hostage-taking, crimes within the jurisdiction of the International Criminal Court, unlawful seizure of aircraft or ships, rape, environmental crime, organised or armed robbery, sabotage, and participation in a criminal organisation involved in one or more of those offences. Outside those exhaustively listed offences and the other two objectives in Article 5, namely the targeted search for victims of abduction, trafficking or sexual exploitation and for missing persons, and the prevention of a specific, substantial and imminent threat to life or physical safety or a genuine and foreseeable terrorist attack, the practice remains a prohibited practice. Annex II therefore has no bearing on the other prohibitions in Article 5, such as social scoring, untargeted scraping of facial images, or emotion recognition in workplaces and education institutions.

## rg_018 (easy) - 4/4

> Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?

**AnsConc 36.16 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Annex III.7.b, Article 97.2, Article 7.1` | `expected: Article 7.1` | 1474 chars | 7.59s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer states 'Yes' clearly._
2. `[PASS]` Condition: AI intended to be used in any of the areas listed in Annex III
    - _States AI must be intended for use in areas already listed in Annex III._
3. `[PASS]` Condition: posed risk is equal or greater than those already referred to in Annex III
    - _States risk must be equivalent or greater than existing high-risk systems._
4. `[PASS]` Both conditions must apply ("and" clause)
    - _States both conditions must be fulfilled cumulatively._

Tone: `PASS` _Professional, well-structured explanation of the legal mechanism without self-reference or hedging._

**Answer**

> Yes, the Commission may amend Annex III by adding or modifying use-cases of high-risk AI systems through delegated acts adopted in accordance with Article 97, under Article 7(1). Both conditions must be fulfilled cumulatively: the AI systems are intended to be used in one of the areas already listed in Annex III, and they pose a risk of harm to health and safety, or an adverse impact on fundamental rights, that is equivalent to or greater than the risk posed by the high-risk AI systems already referred to in Annex III. When assessing that second condition the Commission must weigh the Article 7(2) criteria, including the intended purpose, the extent of use, the nature and amount of data processed, the degree of autonomy, the severity and reversibility of harm, and the availability of redress. The Commission cannot create a new area, only add or modify use-cases within the existing areas, and Article 7(3) separately allows removal of a use-case where it no longer poses significant risks to fundamental rights, health or safety and the deletion does not decrease the overall level of protection under Union law. Procedurally, Article 97 confers the power for five years from 1 August 2024 with tacit extension, requires consultation of experts designated by each Member State before adoption, and the act enters into force only if neither the European Parliament nor the Council objects within three months of notification, extendable by a further three months.

## rg_019 (easy) - 4/4

> What is a deep fake according to the EU AI Act?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 3.60, Article 50.4` | `expected: Article 3.60` | 192 chars | 0.05s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` AI-generated or manipulated content
    - _States content is AI-generated or manipulated_
2. `[PASS]` Image, audio, or video
    - _Mentions image, audio or video content_
3. `[PASS]` Resembles existing persons, objects, places, entities or events
    - _States resemblance to existing persons, objects, places, entities or events_
4. `[PASS]` Falsely appears authentic or truthful to a person
    - _States it would falsely appear authentic or truthful to a person_

Tone: `PASS` _Concise, neutral definitional statement in professional register._

**Answer**

> AI-generated or manipulated image, audio or video content that resembles existing persons, objects, places, entities or events and would falsely appear to a person to be authentic or truthful.

## rg_020 (easy) - 3/3

> Should market surveilance authorities be provided with remote access to documentations and data sets used to develop a high-risk AI system?

**AnsConc 63.78 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 74.12` | `expected: Article 74.12` | 958 chars | 6.52s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer states 'Yes' as its position._
2. `[PASS]` Full access to documentation and to training, validation and testing data sets, granted by providers, limited to what is necessary for the authority's tasks
    - _States full access to documentation and training/validation/testing data sets, limited to what is necessary for tasks._
3. `[PASS]` Remote access (e.g. via API or other technical means) permitted only "where appropriate" and subject to security safeguards
    - _States remote access via API or other technical means only 'where appropriate' and subject to security safeguards._

Tone: `PASS` _Professional, well-structured, and directly answers with clear regulatory grounding._

**Answer**

> Yes, where relevant and limited to what is necessary for their tasks. Article 74(12) requires providers to grant market surveillance authorities full access to the documentation as well as the training, validation and testing data sets used for the development of high-risk AI systems, including, where appropriate and subject to security safeguards, through application programming interfaces or other relevant technical means and tools enabling remote access. This access power operates without prejudice to the powers under Regulation (EU) 2019/1020, which frames the authorities' investigation and corrective-measure powers. Source code is a narrower matter under Article 74(13): it is granted only upon a reasoned request, and only where it is necessary to assess conformity with the Chapter III, Section 2 requirements and where testing, auditing and verification based on the data and documentation provided have been exhausted or proved insufficient.

## rg_021 (easy) - 2/4  **FAILS**

> If a provider of a high-risk AI system confirms that the system achieves an appropriate level of accuracy, robustness, and cybersecurity at the time of development, then no further action is required by the provider on these aspects in the future. Correct?

**AnsConc 63.23 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 15.1, Article 9.2, Article 17.1` | `expected: Article 15.1` | 1096 chars | 12.71s | judge spread [0.5, 0.5, 0.5]

1. `[PASS]` No
    - _Answer's clear position is 'No.'_
2. `[FAIL]` Must perform consistently throughout lifecycle, including resilience to errors/faults/inconsistencies (Art. 15(1),(4))
    - _States consistency throughout lifecycle but omits resilience to errors/faults/inconsistencies (Art. 15(4))._
3. `[FAIL]` Cybersecurity resilience against third-party exploitation is ongoing, not one-time (Art. 15(5))
    - _Does not mention ongoing cybersecurity resilience against third-party exploitation attempts._
4. `[PASS]` Accuracy levels/metrics must be declared in instructions of use (Art. 15(3))
    - _States accuracy levels/metrics must be declared in instructions of use._

Tone: `PASS` _Professional, well-structured explanation grounded in specific articles without self-reference or hedging._

**Answer**

> No. Article 15(1) requires high-risk AI systems to achieve an appropriate level of accuracy, robustness and cybersecurity and to perform consistently in those respects throughout their lifecycle, so a single confirmation at the development stage does not discharge the obligation. Article 9(1) requires the risk management system to be established, implemented, documented and maintained as a continuous, iterative process across the whole lifecycle, including evaluation of data gathered from post-market monitoring, and Article 9(5) requires testing to ensure the system performs consistently for its intended purpose. The quality management system under Article 17 must include examination, test and validation procedures to be carried out before, during and after development, together with the frequency at which they are performed, and procedures for the management of modifications to the system. The accuracy levels and relevant accuracy metrics declared in the accompanying instructions of use under Article 15 must accordingly remain accurate as to the performance that can be expected.

## rg_022 (easy) - 3/4  **FAILS**

> What are all the risk categories in the EU AI Act?

**AnsConc 100.0 | RefL None | RefS None | RefC None**

`refs: Article 5, Article 6, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56` | `expected: not annotated` | 621 chars | 0.06s | judge spread [1.0, 0.75, 0.75]

1. `[PASS]` Unacceptable risk - prohibited practices (Article 5)
    - _States unacceptable-risk practices prohibited under Article 5._
2. `[PASS]` High risk - Article 6, referencing Annex I (product safety) and Annex III (use cases)
    - _States high-risk classification under Article 6 referencing Annex I and Annex III._
3. `[PASS]` Limited risk - transparency obligations (Article 50)
    - _States limited-risk systems have Article 50 transparency duties._
4. `[FAIL]` Minimal or no risk - no mandatory obligations, voluntary codes of conduct (Article 95)
    - _States minimal-risk systems have no mandatory duties but omits the voluntary codes of conduct under Article 95._

Tone: `PASS` _Professional, well-structured, and legally grounded explanation of the risk tiers._

**Answer**

> The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems have no mandatory duties under the Act, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.

## rg_023 (easy) - 2/2

> Does "systemic risk" apply to AI systems or general purpose AI models or both?

**AnsConc 76.52 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 51.1, Article 55.1, Article 53.2` | `expected: Article 51.1` | 890 chars | 0.03s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Applies to general-purpose AI models only (Article 51), not to AI systems
    - _States systemic risk applies to GPAI models and explicitly excludes AI systems' high-risk regime._
2. `[PASS]` Systemic risk classification applies only to general-purpose AI models (Article 51), not to AI systems
    - _Explicitly states the high-risk AI systems regime is separate and doesn't use the systemic-risk concept._

Tone: `PASS` _Professional, neutral, well-structured answer directly addressing the question._

**Answer**

> Under Article 51(1), a general-purpose AI model is classified as a model with systemic risk where it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks; under Article 51(2) a model is presumed to have high impact capabilities where the cumulative computation used for its training exceeds 10^25 floating point operations. The Commission may also designate a model on the basis of the Annex XIII criteria. A model classified as having systemic risk then carries the additional Article 55 obligations: model evaluation including adversarial testing, assessment and mitigation of systemic risks at Union level, serious-incident reporting, and adequate cybersecurity. The high-risk regime for AI systems under Articles 6 and Annex III is a separate classification and does not use the systemic-risk concept.

## rg_024 (easy) - 3/3

> Are AI systems that fall under one of the areas of Annex III, but not falling within a use-case within such areas, considered high-risk?

**AnsConc 78.6 | RefL 100.0 | RefS 100.0 | RefC 66.67**

`refs: Annex III.7.b, Article 6.2, Annex I.19` | `expected: Article 6.2, Annex III` | 874 chars | 8.34s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No
    - _Answer states 'No' as its clear verdict._
2. `[PASS]` High-risk requires falling within a specific enumerated use case listed in Annex III, not merely within the broader area grouping those use cases
    - _States high-risk requires matching a lettered use-case, not just the area heading._
3. `[PASS]` Annex III areas are organisational headings; the operative trigger is the individual use-case description
    - _States the numbered area headings are not themselves operative triggers, only the use-case entries are._

Tone: `PASS` _Professional, well-structured explanation with clear reasoning and no self-referential hedging._

**Answer**

> No. Article 6(2) classifies a system as high-risk only where it falls within one of the use-cases specifically listed under the eight areas of Annex III, so a numbered area heading such as biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, or administration of justice and democratic processes is not itself an operative trigger. A system merely operating in such a sector, without matching a lettered use-case entry, is not high-risk on the Annex III route. It may still be high-risk on the separate Annex I route under Article 6(1), where it is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I and that product must undergo a third-party conformity assessment.

## rg_025 (easy) - 4/4

> Can an operator that is not a provider according to the EU AI Act, for example a deployer, take actions on a given high-risk AI system such that it can be effectively seen as a provider by the authorities? If yes, what kind of action would result in such an outcome?

**AnsConc 90.57 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 25.1, Article 16` | `expected: Article 25.1` | 785 chars | 0.03s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer clearly states yes._
2. `[PASS]` Putting own name/trademark on a high-risk AI system already on the market/in service (Article 25(1)(a))
    - _States putting own name/trademark on a high-risk AI system already on the market qualifies._
3. `[PASS]` Substantial modification to a high-risk AI system already on the market/in service that remains high-risk under Article 6 (Article 25(1)(b))
    - _States substantial modification to a high-risk AI system that remains high-risk qualifies._
4. `[PASS]` Modifying the intended purpose of a non-high-risk (incl. general-purpose) AI system such that it becomes high-risk under Article 6 (Article 25(1)(c))
    - _States modifying intended purpose of an AI system (incl. GPAI) so it becomes high-risk qualifies._

Tone: `PASS` _Professional, well-organized, third-person regulatory prose citing specific provisions._

**Answer**

> Yes. Under Article 25(1), a distributor, importer, deployer or other third party is deemed to be the provider of a high-risk AI system, and takes on the provider obligations in Article 16, in any of three cases. First, if it puts its name or trademark on a high-risk AI system already placed on the market (Article 25(1)(a)). Second, if it makes a substantial modification to a high-risk AI system that remains high-risk (Article 25(1)(b)). Third, if it modifies the intended purpose of an AI system, including a general-purpose AI system, so that it becomes high-risk (Article 25(1)(c)). In each of these three cases the operator assumes the provider obligations in Article 16, and the initial provider is no longer considered the provider of that specific system under Article 25(2).

## rg_026 (easy) - 3/3

> If I have an AI system that is high-risk because listed in the use cases of Annex III, and change it to a different use case that is not in Annex I or III, does it stay high-risk due to its historical provenance?

**AnsConc 61.08 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Annex III, Annex I.5, Article 6.2` | `expected: Article 6.2` | 1002 chars | 11.24s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No
    - _Answer clearly states 'No'_
2. `[PASS]` High-risk status under Article 6 depends on the AI system's current intended purpose/use case, not its prior classification
    - _States classification depends on intended purpose at the relevant time, not history_
3. `[PASS]` If the new use case falls outside both Annex I and Annex III, neither condition in Article 6(1) or 6(2) is met, so the system is not high-risk
    - _States that if new use case is in neither Annex I nor III, it is not high-risk going forward_

Tone: `PASS` _Professional, well-structured legal analysis with no self-reference or hedging._

**Answer**

> No, high-risk status does not attach as a matter of historical provenance. Classification under Article 6 is assessed against the system's intended purpose at the relevant time, so a system is high-risk only where it is a safety component of, or itself, a product covered by the Union harmonisation legislation in Annex I that must undergo a third-party conformity assessment under that sectoral legislation (Article 6(1)), or where it falls within one of the lettered use cases under the eight areas of Annex III (Article 6(2)). Once the intended purpose is genuinely changed to a use case listed in neither Annex I nor Annex III, and the system is no longer intended for the former Annex III use case, it is not high-risk going forward. The reclassification must be reflected in the intended purpose as declared and in the instructions for use, and it does not retroactively cure any non-compliance during the period the system was placed on the market or put into service for the Annex III use case.

## rg_027 (easy) - 4/4

> How are AI systems intended to influence the outcome of an election or referendum classified, and what exception is given for certain campaign-related tools?

**AnsConc 100.0 | RefL 100.0 | RefS 0.0 | RefC 33.33**

`refs: Article 6.3, Article 50.1, Annex III.8` | `expected: Article 50.2` | 493 chars | 0.07s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` High-risk classification under Annex III, point 8(b)
    - _States Annex III point 8(b) high-risk classification_
2. `[PASS]` Covers AI systems influencing election/referendum outcome or voters' voting behaviour
    - _Covers influencing election/referendum outcome or voting behaviour_
3. `[PASS]` Exception: AI systems whose output natural persons are not directly exposed to are excluded
    - _States exclusion for systems whose output persons are not directly exposed to_
4. `[PASS]` Example given: tools organising/optimising/structuring political campaigns administratively or logistically
    - _Gives example of tools organising/optimising/structuring campaigns administratively or logistically_

Tone: `PASS` _Neutral, well-structured professional prose explaining the classification and exception clearly._

**Answer**

> Under Annex III point 8(b), AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, are high-risk under Article 6(2). Annex III point 8(b) itself excludes systems to whose output natural persons are not directly exposed, such as tools used only to organise, optimise or structure political campaigns from an administrative or logistical point of view, which therefore fall outside this high-risk category.

## rg_028 (easy) - 4/4

> According to Article 1, what is the objective of the EU AI Act?

**AnsConc 51.21 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 1` | `expected: Article 1` | 994 chars | 4.66s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Improve functioning of the internal market
    - _States improving internal market functioning_
2. `[PASS]` Promote uptake of human-centric and trustworthy AI
    - _States promoting uptake of human-centric and trustworthy AI_
3. `[PASS]` Ensure high level of protection of health, safety and fundamental rights (incl. democracy, rule of law, environment) against harmful effects of AI systems
    - _States high level of protection of health, safety, fundamental rights incl. democracy, rule of law, environment_
4. `[PASS]` Support innovation
    - _States supporting innovation_

Tone: `PASS` _Professional, neutral, well-structured summary of Article 1's provisions._

**Answer**

> Article 1(1) states that the purpose of the Regulation is to improve the functioning of the internal market and promote the uptake of human-centric and trustworthy artificial intelligence, while ensuring a high level of protection of health, safety and fundamental rights enshrined in the Charter, including democracy, the rule of law and environmental protection, against the harmful effects of AI systems in the Union, and supporting innovation. To that end, Article 1(2) lays down harmonised rules for the placing on the market, putting into service and use of AI systems, prohibitions of certain AI practices, specific requirements for high-risk AI systems and obligations for their operators, harmonised transparency rules for certain AI systems, harmonised rules for the placing on the market of general-purpose AI models, rules on market monitoring, market surveillance, governance and enforcement, and measures to support innovation with a particular focus on SMEs, including start-ups.

## rg_029 (easy) - 2/3  **FAILS**

> Under the EU AI Act, which specific AI systems are explicitly listed as high-risk because they make decisions in critical life- and health-related situations involving emergency calls and triage?

**AnsConc 100.0 | RefL None | RefS None | RefC None**

`refs: Article 6.2, Annex III.5.d` | `expected: not annotated` | 535 chars | 0.02s | judge spread [0.667, 0.667, 0.667]

1. `[FAIL]` AI systems that evaluate and classify emergency calls by natural persons
    - _Answer does not mention evaluating/classifying emergency calls._
2. `[PASS]` AI systems used to dispatch, or establish priority in dispatching, emergency first response services (police, firefighters, medical aid)
    - _Answer states dispatching/prioritising emergency first-response services including police, firefighters, medical aid._
3. `[PASS]` Emergency healthcare patient triage systems
    - _Answer explicitly mentions triage of emergency medical-service patients._

Tone: `PASS` _Professional, well-structured explanation citing the relevant Annex III provision._

**Answer**

> Under Annex III point 5(d), AI systems intended to be used for dispatching or prioritising in dispatching emergency first-response services, or for triage of emergency medical-service patients (including by fire brigades and medical aid), are explicitly listed as high-risk. They fall within the 'essential private and public services' category of the eight Annex III high-risk use cases and are classified as high-risk through the Annex III route of Article 6(2), which treats any system falling within a listed use case as high-risk.

## rg_030 (easy) - 1/1

> Under Regulation (EU) 2024/1689, as part of their supervisory role for an AI regulatory sandbox, compliance with which specific Article must the market surveillance authority verify?

**AnsConc 47.86 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 60.4, Article 76.2` | `expected: Article 76.2` | 725 chars | 6.18s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Article 60
    - _Answer explicitly states Article 60 as the provision to verify compliance with._

Tone: `PASS` _Professional, well-structured, and directly answers with proper legal citations._

**Answer**

> Article 60, which governs testing of high-risk AI systems in real world conditions and sets the conditions for it, including an approved real-world testing plan submitted to the market surveillance authority, informed consent of test subjects, and registration in the EU database. Article 76(2) makes this explicit: where testing in real world conditions is conducted for AI systems supervised within an AI regulatory sandbox, the market surveillance authorities verify compliance with Article 60 as part of their supervisory role for that sandbox. Those authorities may, as appropriate, allow the provider or prospective provider to conduct the testing in derogation from the conditions in Article 60(4), points (f) and (g).

## rg_031 (easy) - 3/4  **FAILS**

> Is an AI system used to structure or deduplicate information for a use case listed in Annex III considered high-risk?

**AnsConc 100.0 | RefL 100.0 | RefS 0.0 | RefC 33.33**

`refs: Article 6.3, Article 49.2, Annex III.7.b` | `expected: Article 6.3.a` | 587 chars | 0.02s | judge spread [0.75, 1.0, 0.5]

1. `[FAIL]` No
    - _The answer never gives a clear 'No' verdict, only describes the general framework._
2. `[PASS]` Falls under narrow procedural task derogation, Article 6(3), first subparagraph, point (a)
    - _It lists 'performs a narrow procedural task' as one of the Article 6(3)(a) conditions._
3. `[PASS]` Exception: remains high-risk if system performs profiling of natural persons
    - _States the exception never applies where the system profiles natural persons._
4. `[PASS]` Provider must document the assessment before placing on market/putting into service (Article 6(4))
    - _States provider must document the assessment before placing the system on the market._

Tone: `PASS` _Neutral, well-structured legal explanation with no self-reference or hedging._

**Answer**

> Under Article 6(3), an Annex III system is not high-risk where it poses no significant risk of harm and meets one of four conditions: it performs a narrow procedural task, it improves the result of a previously completed human activity, it detects decision-making patterns or deviations without replacing or influencing the human assessment, or it performs a preparatory task. Under Article 6(3), this exception never applies where the system profiles natural persons. The provider must document the assessment before placing the system on the market and register it under Article 49(2).

## rg_032 (easy) - 3/3

> Is an AI system used to detect decision-making patterns or deviations for a use case listed in Annex III considered high-risk?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 6.3, Annex III` | `expected: Article 6.3` | 458 chars | 0.01s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No, not by default
    - _States the system is not high-risk when conditions met, implying no default high-risk status._
2. `[PASS]` Condition: not meant to replace or influence the previously completed human assessment, without proper human review
    - _Explicitly states the condition about not replacing/influencing human assessment without proper human review._
3. `[PASS]` Exception: always high-risk if system performs profiling of natural persons
    - _Explicitly states profiling always makes it high-risk._

Tone: `PASS` _Neutral, professional register with clear, well-structured legal exposition._

**Answer**

> Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.

## rg_033 (easy) - 4/4

> Regarding the European Artificial Intelligence Board: (1) Who designates its members? (2) How long is the term? How many times is the term renewable? (3) must members represent stakeholder interests or act impartially/objectively? (4) what voting threshold is required to adopt the Board's rules of procedure (is a simple 50%+1 majority enough)?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 65.5` | `expected: Article 65` | 508 chars | 0.02s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Members designated by their Member State
    - _Implies each representative is that Member State's own designee/contact point, indicating Member States designate them._
2. `[PASS]` Term is three years, renewable once
    - _States three-year term, renewable once._
3. `[PASS]` No stakeholder representation requirement; must safeguard objectivity/impartiality
    - _Notes representatives are contact points not stakeholder appointees, and Board must safeguard objectivity/impartiality._
4. `[PASS]` Two-thirds majority required to adopt rules of procedure (simple majority not enough)
    - _States two-thirds majority required, simple majority insufficient._

Tone: `PASS` _Professional, structured, directly answers each sub-question without editorializing._

**Answer**

> The European Artificial Intelligence Board (Article 65) has one representative per Member State, each serving a three-year term renewable once under Article 65(3). Under Article 65(4) each is their Member State's single contact point rather than an independent stakeholder appointee, while Article 65(7) requires the Board to safeguard the objectivity and impartiality of its activities. Its rules of procedure are adopted by a two-thirds majority under Article 65(5), so a simple majority is not sufficient.

## rg_034 (easy) - 4/4

> Under the EU AI Act, what jurisdiction does the Court of Justice of the European Union have over Commission decisions fixing fines on providers of general-purpose AI models, and what can the Court do with the fine?

**AnsConc 36.11 | RefL 100.0 | RefS 0.0 | RefC 50.0**

`refs: Article 99.5, Article 101.1` | `expected: Article 101.3` | 889 chars | 6.82s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Unlimited jurisdiction to review Commission decisions fixing a fine
    - _States CJEU has unlimited jurisdiction to review Commission fine decisions._
2. `[PASS]` Court may cancel the fine
    - _States the Court may cancel the fine._
3. `[PASS]` Court may reduce the fine
    - _States the Court may reduce the fine._
4. `[PASS]` Court may increase the fine
    - _States the Court may increase the fine._

Tone: `PASS` _Professional, well-structured, directly answers with correct legal register despite an awkward leading fragment._

**Answer**

> Unlimited jurisdiction to review. Article 101(5) confers on the Court of Justice of the European Union unlimited jurisdiction to review Commission decisions fixing a fine on a provider of a general-purpose AI model under that Article, and it may cancel, reduce or increase the fine imposed. Those fines are the Commission's own enforcement measure against general-purpose AI model providers of up to EUR 15 000 000 or 3 % of total worldwide annual turnover, whichever is higher, for infringements of the Chapter V obligations, for supplying incorrect, incomplete or misleading information, or for failure to comply with a requested measure. Before adopting such a decision the Commission must communicate its preliminary findings to the provider and give it an opportunity to be heard under Article 101(2), and the fine must be effective, proportionate and dissuasive under Article 101(3).

## rg_035 (easy) - 2/3  **FAILS**

> Consider the situation in which a market surveillance authority (MSA) determines that an AI system, originally classified as non-high-risk by the provider, is in fact high-risk. Does the provider need to recall and suspend the use of the system without undue delay, or does the MSA provide a timeframe within which the provider can take corrective actions? Or does this depend on the gravity of the situation?

**AnsConc 51.42 | RefL 100.0 | RefS 100.0 | RefC 25.0**

`refs: Article 20.1, Article 79.2, Article 80.2, Article 6.2` | `expected: Article 80.2` | 1272 chars | 13.3s | judge spread [0.667, 0.667, 0.667]

1. `[PASS]` MSA sets a compliance/corrective-action period for the provider, rather than an automatic without-undue-delay recall/suspension duty
    - _States MSA prescribes timeframe rather than automatic recall duty._
2. `[PASS]` Provider must bring the system into compliance and take corrective action within that MSA-prescribed period (Article 80(2) and 80(4))
    - _States provider must bring system into compliance and take corrective action within MSA-prescribed period per Article 80(2)._
3. `[FAIL]` Failure to comply within that period triggers fines under Article 99 (and Article 79(5)-(9) applies), not gravity-based variation of the timeframe
    - _Does not mention Article 99 fines for non-compliance; instead asserts gravity does matter, contradicting the criterion._

Tone: `PASS` _Professional third-person register with well-structured, actionable regulatory explanation._

**Answer**

> The market surveillance authority prescribes the timeframe, and immediate recall is not automatically required. Under Article 80(2), where the authority's evaluation finds that a system the provider classified as non-high-risk under the Article 6(3) derogation is in fact high-risk, it must without undue delay require that provider to take all necessary actions to bring the system into compliance with this Regulation and to take appropriate corrective action within a period the authority may prescribe. The gravity of the situation does matter, because where the system also presents a risk to health, safety or fundamental rights, Article 79(2) requires the authority to order corrective action, withdrawal from the market or recall within a period it may prescribe, and in any event within the shorter of 15 working days or the period laid down in the relevant Union harmonisation legislation. Independently of any order, Article 20 obliges the provider, once it considers or has reason to consider the high-risk AI system non-conforming, to immediately take the necessary corrective actions to bring it into conformity, withdraw it, disable it or recall it, and to inform the distributors, the deployers, the authorised representative and the importers accordingly.

## rg_036 (easy) - 2/3  **FAILS**

> Under the EU AI Act, what presumption applies when a high-risk AI system is trained and tested on data that reflects the specific geographical, behavioural, contextual or functional setting in which it is intended to be used?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 10.4, Article 42.1` | `expected: Article 42.1` | 454 chars | 5.12s | judge spread [0.667, 0.667, 0.667]

1. `[PASS]` Presumed compliant with Article 10(3) representativeness/quality requirement for that setting
    - _States presumption of compliance with the setting-specific data quality requirement (labelled Art 10(4) but matching that substance)._
2. `[FAIL]` Presumption is limited to the extent required by the intended purpose
    - _Does not mention the presumption being limited to the extent required by the intended purpose._
3. `[PASS]` Not an exemption from other Article 10 obligations (e.g., bias examination/mitigation)
    - _States the presumption extends only to that requirement, not to the rest of Article 10._

Tone: `PASS` _Professional, neutral, and clearly structured explanation with correct legal referencing._

**Answer**

> Such a system is presumed to comply with the relevant requirements of Article 10(4), which requires data sets to take into account the characteristics or elements particular to the specific geographical, contextual, behavioural or functional setting in which the high-risk AI system is intended to be used. This presumption of conformity arises under Article 42(1) and extends only to that data governance requirement, not to the remainder of Article 10.

## rg_037 (easy) - 0/5  **FAILS**

> When registering a high-risk AI system in the EU database under the EU AI Act, what specific information must the provider submit? List the required items.

**AnsConc 34.53 | RefL None | RefS None | RefC None**

`refs: Article 71.1, Article 49.4, Annex VIII.12, Annex III.7.b, Article 6.2` | `expected: not annotated` | 1752 chars | 19.92s | judge spread [0.0]

1. `[FAIL]` Registration confined to secure, non-public section of EU database (Article 71)
    - _Answer never mentions that registration is limited to the secure, non-public section of the database under Article 71._
2. `[FAIL]` Annex VIII Section A points 1-10, excluding 6, 8 and 9
    - _Answer lists all ten Section A items (including description of data, certificate, and instructions for use) rather than the required subset excluding points 6, 8 and 9._
3. `[FAIL]` Annex VIII Section B points 1-5, 8 and 9
    - _No mention of Annex VIII Section B items or the associated registration scenario._
4. `[FAIL]` Annex VIII Section C points 1-3
    - _No mention of Annex VIII Section C items._
5. `[FAIL]` Annex IX points 1, 2, 3 and 5
    - _No mention of Annex IX or its specific points._

Tone: `PASS` _Professional, neutral, and well-structured despite dense sentence length._

**Answer**

> The provider, or where applicable the authorised representative, must register itself and the system and enter the Annex VIII Section A data into the EU database that the Commission sets up and maintains under Article 71, and must do so under Article 49(1) before the high-risk AI system listed in Annex III is placed on the market or put into service. The required items are the name, address and contact details of the provider, the same details of any person submitting the information on the provider's behalf, the name, address and contact details of the authorised representative where applicable, the AI system trade name and any additional unambiguous reference allowing identification and traceability of the AI system, a description of the intended purpose of the system and of the components and functions supported through it, a basic and concise description of the information used by the system (data, inputs) and its operating logic, the status of the AI system (on the market, in service, no longer placed on the market or in service, recalled), the certificate issued by the notified body together with a scanned copy of that certificate where applicable, electronic instructions for use, and, optionally, a URL for additional information. Electronic instructions for use are not provided for high-risk AI systems in the areas of law enforcement or migration, asylum and border control management referred to in Annex III points 1, 6 and 7. Systems referred to in point 2 of Annex III fall outside this registration and are registered at national level under Article 49(5), while a provider that has concluded under Article 6(3) that its Annex III system is not high-risk must still register itself and that system under Article 49(2).

## rg_038 (easy) - 3/4  **FAILS**

> Under the EU AI Act, what is an "AI regulatory sandbox"? Provide the definition elements (what it is, who sets it up, for whom it is intended, to do what, for how long).

**AnsConc 100.0 | RefL 100.0 | RefS 0.0 | RefC 33.33**

`refs: Article 3.55, Article 57.5, Article 1` | `expected: Article 57.1` | 315 chars | 0.07s | judge spread [0.75, 0.75, 0.75]

1. `[PASS]` Controlled environment established by a national competent authority (or jointly with other Member States, or by the EDPS for Union bodies)
    - _Answer states it's a controlled framework set up by a competent authority._
2. `[PASS]` Intended for providers or prospective providers of AI systems
    - _Answer specifies providers or prospective providers of AI systems as target._
3. `[PASS]` Purpose: fosters innovation and facilitates development, training, testing and validation of innovative AI systems (may include supervised real-world testing)
    - _Answer covers development, training, validation, testing and real-world conditions for innovative AI systems._
4. `[FAIL]` Time-limited, prior to market placement/putting into service, pursuant to a specific sandbox plan agreed with the competent authority
    - _Answer mentions time-limited and sandbox plan but omits that it occurs prior to market placement/putting into service._

Tone: `PASS` _Professional, neutral, single well-formed sentence covering all requested definition elements._

**Answer**

> A controlled framework set up by a competent authority which offers providers or prospective providers of AI systems the possibility to develop, train, validate and test, where appropriate in real-world conditions, an innovative AI system, pursuant to a sandbox plan for a limited time under regulatory supervision.

## rg_039 (easy) - 3/3

> Under the EU AI Act, what transparency obligation applies to deployers when they use an AI system to generate or manipulate text for the purpose of informing the public on matters of public interest, and what are the two exceptions where this obligation does not apply?

**AnsConc 98.33 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 50.4` | `expected: Article 50.4` | 600 chars | 0.02s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Deployers must disclose that the text has been artificially generated or manipulated
    - _States deployers must disclose text was artificially generated or manipulated_
2. `[PASS]` Exception 1: use authorised by law to detect, prevent, investigate or prosecute criminal offences
    - _States exception for use authorised by law for criminal offence detection/prevention/investigation/prosecution_
3. `[PASS]` Exception 2: AI-generated content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for the publication
    - _States exception for human review/editorial control with editorial responsibility_

Tone: `PASS` _Professional, neutral, well-structured prose with clear enumeration of the two exceptions._

**Answer**

> Under Article 50(4), a deployer that uses an AI system to generate or manipulate text published to inform the public on matters of public interest must disclose that the text has been artificially generated or manipulated. Under Article 50(4), that disclosure duty does not apply in two cases: first, where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences; and second, where the AI-generated content has undergone a process of human review or editorial control and a natural or legal person holds editorial responsibility for the publication of the content.

## rg_040 (easy) - 0/2  **FAILS**

> Under the EU AI Act, when a high-risk AI system is found to conform with the requirements, what information must the Union technical documentation assessment certificate contain?

**AnsConc 100.0 | RefL 0.0 | RefS 0.0 | RefC 100.0**

`refs: Annex VII.4` | `expected: Article 44.1` | 436 chars | 0.02s | judge spread [0.0, 0.0, 0.0]

1. `[FAIL]` Language: drawn up in a language easily understood by the relevant authorities of the Member State where the notified body is established
    - _Answer does not mention language requirement for the certificate_
2. `[FAIL]` Validity period stated: not exceeding five years (Annex I systems) or four years (Annex III systems)
    - _Answer only vaguely mentions 'conditions for validity' without stating the five/four year validity periods_

Tone: `PASS` _Professional, neutral, well-structured prose citing the relevant provision clearly._

**Answer**

> Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system.

## rg_041 (easy) - 2/3  **FAILS**

> Under the EU AI Act, is there a simplified way for SMEs (including startups) to provide the technical documentation for high-risk AI systems, and who must accept it for conformity assessment?

**AnsConc 100.0 | RefL 0.0 | RefS 0.0 | RefC 50.0**

`refs: Article 11.1, Annex IV.2` | `expected: Article 17.4` | 362 chars | 0.02s | judge spread [0.667, 0.667, 0.667]

1. `[PASS]` Yes
    - _Answer opens with 'Yes'._
2. `[FAIL]` AI Office develops a simplified technical documentation form for SMEs/microenterprises, including start-ups, covering the Annex IV elements
    - _Answer attributes the simplified form to the Commission rather than the AI Office, though it does mention Annex IV coverage._
3. `[PASS]` The notified body assessing conformity of the high-risk AI system must accept that simplified form
    - _States the notified body performing conformity assessment must accept the simplified form._

Tone: `PASS` _Professional, neutral, well-structured prose directly answering the question._

**Answer**

> Yes. Under Article 11(1), SMEs, including start-ups, may provide the technical documentation elements set out in Annex IV in a simplified manner, using a simplified form the Commission is required to establish for the needs of small and micro enterprises. Where an SME opts to use that form, the notified body performing the conformity assessment must accept it.

## rg_042 (easy) - 4/4

> Under the EU AI Act, must an employer inform affected workers and workers' representatives before putting into service or using a high-risk AI system in the workplace?
If so, should possibly specific rules or procedures be followed to provide this information?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 26.7` | `expected: Article 26.7` | 493 chars | 0.02s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer states Yes_
2. `[PASS]` Timing: before putting into service or using the system at the workplace
    - _States timing as before putting into service or using the system at the workplace_
3. `[PASS]` Recipients: workers' representatives and affected workers
    - _Names workers' representatives and affected workers as recipients_
4. `[PASS]` Procedure: follow applicable Union/national law and practice on informing workers, where applicable (no separate free-standing procedure)
    - _States information follows Union/national law and practice, where applicable_

Tone: `PASS` _Professional, neutral, and clearly structured explanation of Article 26(7) obligations._

**Answer**

> Yes. Under Article 26(7), a deployer that is an employer must, before putting a high-risk AI system into service or using it at the workplace, inform the workers' representatives and the affected workers that they will be subject to the use of that high-risk AI system. Under Article 26(7), that information must be provided, where applicable, in accordance with the rules and procedures laid down in Union and national law and practice on the information of workers and their representatives.

## rg_043 (easy) - 3/6  **FAILS**

> Under Article 10(5) of the EU AI Act, when may a provider of a high-risk AI system process special categories of personal data for bias detection and correction, and what key safeguards/conditions must be met?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 10.5` | `expected: Article 10.5` | 722 chars | 0.02s | judge spread [0.5, 0.5, 0.5]

1. `[PASS]` Only where strictly necessary for bias detection/correction under Art 10(2)(f)-(g), and cannot be effectively achieved with other data (incl. synthetic/anonymised)
    - _States processing allowed only if strictly necessary for bias detection/correction and other data (incl. synthetic/anonymised) insufficient._
2. `[PASS]` Technical re-use limitations plus state-of-the-art security/privacy-preserving measures, including pseudonymisation
    - _Mentions technical re-use limits plus state-of-the-art security and pseudonymisation._
3. `[FAIL]` Strict, documented access controls limited to authorised persons under confidentiality obligations, with no transmission/transfer/access by other parties
    - _Mentions strict documented access controls and no transmission/transfer, but omits limitation to authorised persons and confidentiality obligations, and access by other parties._
4. `[PASS]` Deletion once bias corrected or retention period ends, whichever is first
    - _States deletion occurs once bias corrected or retention period ends, whichever first._
5. `[FAIL]` Processing records document necessity and why other data would not suffice
    - _Only mentions documenting strict necessity, omitting the requirement to document why other data would not suffice._
6. `[FAIL]` Additional to, not a substitute for, obligations under GDPR, EUDPR and the Law Enforcement Directive
    - _Does not mention that these conditions are in addition to GDPR, EUDPR, and Law Enforcement Directive obligations._

Tone: `PASS` _Neutral, well-structured professional summary of the conditions without self-reference or hedging._

**Answer**

> Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict, documented access controls to prevent misuse (c); no transmission or transfer to other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).

## rg_044 (easy) - 2/4  **FAILS**

> Under the EU AI Act, what specific information must a provider/prospective provider submit (and keep up to date) regarding testing of a high-risk AI system in real-world conditions outside an AI regulatory sandbox?

**AnsConc 76.77 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 60.4.c` | `expected: Article 60.4` | 973 chars | 14.34s | judge spread [0.5, 0.5, 0.5]

1. `[PASS]` Real-world testing plan submitted to (and approved by) the market surveillance authority of the Member State of testing
    - _States plan submitted to and approved by market surveillance authority of the Member State of testing._
2. `[PASS]` Registration of the testing with a Union-wide unique single identification number
    - _States registration yields a Union-wide unique single identification number._
3. `[FAIL]` General rule: registration under Article 71(4) with information specified in Annex IX
    - _Does not mention Article 71(4) or Annex IX information specifically, only vague 'dedicated section of the EU database'._
4. `[FAIL]` Exceptions: Annex III points 1, 6, 7 (law enforcement/migration/asylum/border control) register in secure non-public EU database section per Article 49(4)(d); Annex III point 2 systems register per Article 49(5)
    - _No mention of exceptions for Annex III points 1,6,7 or point 2 systems and their specific registration routes._

Tone: `PASS` _Professional, neutral, well-structured explanation citing Article 60 requirements clearly._

**Answer**

> The provider or prospective provider must draw up a real world testing plan and submit it to the market surveillance authority of the Member State where the testing is to be conducted, and the testing may proceed only in accordance with that approved plan under Article 60. Article 60 further requires the testing in real world conditions, and the provider or prospective provider conducting it, to be registered in the dedicated section of the EU database, which yields a Union-wide unique single identification number and the information accompanying that registration. That registered information must be kept up to date for the duration of the testing, including any suspension or termination and the outcome of the testing. Article 60 also conditions the testing on the informed consent of the test subjects and on supervision by the market surveillance authority, and the Commission specifies the detailed elements of the real world testing plan by implementing acts.

## rg_045 (easy) - 4/4

> Under the EU AI Act, if a deployer has reason to believe that the use of a high-risk AI system may present a risk, what must the deployer do, and whom must the deployer inform?

**AnsConc 34.45 | RefL 100.0 | RefS 100.0 | RefC 25.0**

`refs: Article 26.5, Article 79.2, Article 72.2, Article 73.4` | `expected: Article 26.5` | 1077 chars | 8.43s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Inform the provider or distributor
    - _States deployer must inform provider or distributor_
2. `[PASS]` Inform the relevant market surveillance authority
    - _States deployer must inform relevant market surveillance authority_
3. `[PASS]` Suspend use of the system
    - _States deployer must suspend use of the system_
4. `[PASS]` All actions taken without undue delay
    - _States actions taken without undue delay_

Tone: `PASS` _Professional, well-structured regulatory explanation citing relevant articles without self-reference or hedging._

**Answer**

> The deployer must, without undue delay, inform the provider or distributor and the relevant market surveillance authority, and must suspend the use of that system, under Article 26(5), which applies where the deployer has reason to consider that use in accordance with the instructions for use may result in the system presenting a risk within the meaning of Article 79(1), namely a risk to health, safety or fundamental rights. That same paragraph requires the deployer to monitor the operation of the high-risk AI system on the basis of the instructions for use and, where relevant, to inform the provider in accordance with Article 72 on post-market monitoring. Where the deployer has identified a serious incident, it must immediately inform first the provider, and then the importer or distributor and the relevant market surveillance authorities. If the provider cannot be reached, Article 73 on serious incident reporting applies mutatis mutandis, and the notification duty does not extend to sensitive operational data of deployers that are law enforcement authorities.

## rg_046 (easy) - 6/6

> Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information.

**AnsConc 57.94 | RefL 100.0 | RefS 100.0 | RefC 25.0**

`refs: Article 13.3, Article 9.2, Article 14.4, Article 12.3` | `expected: Article 13.3` | 1700 chars | 19.27s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Provider and, where applicable, authorised representative identity/contact details
    - _States provider and authorised representative identity/contact details._
2. `[PASS]` Characteristics, capabilities and performance limitations (intended purpose, accuracy/robustness/cybersecurity levels, foreseeable risks, explainability capabilities, performance for specific groups, input data specifications)
    - _Covers intended purpose, accuracy/robustness/cybersecurity, foreseeable risks, group-specific performance, and input data specs, substantially matching the category._
3. `[PASS]` Pre-determined changes to the system and its performance
    - _Mentions pre-determined changes to system and performance at initial conformity assessment._
4. `[PASS]` Human oversight measures under Article 14
    - _States human oversight measures under Article 14 including technical measures for output interpretation._
5. `[PASS]` Computational/hardware resources needed, expected lifetime, and maintenance/care measures
    - _Includes computational/hardware resources, expected lifetime, and maintenance/care measures._
6. `[PASS]` Description of logging mechanisms under Article 12, where relevant
    - _Mentions logging mechanism description per Article 12 where relevant._

Tone: `PASS` _Professional and accurate in tone, though dense, it is grammatically coherent and logically ordered._

**Answer**

> Article 13 requires a high-risk AI system to be sufficiently transparent for deployers to interpret its output and use it appropriately, and Article 13(3) prescribes the minimum content of the accompanying instructions for use. That content comprises the identity and contact details of the provider and, where applicable, its authorised representative, the characteristics, capabilities and limitations of performance including the intended purpose, the level of accuracy, robustness and cybersecurity, any known or foreseeable circumstance related to use in accordance with the intended purpose or under conditions of reasonably foreseeable misuse which may lead to risks to health and safety or fundamental rights referred to in Article 9(2), the system's performance as regards the persons or groups on which it is intended to be used, specifications for the input data, information enabling deployers to interpret the output and use it appropriately, the changes to the system and its performance pre-determined by the provider at the moment of the initial conformity assessment, the human oversight measures referred to in Article 14 including the technical measures put in place to facilitate interpretation of outputs, the computational and hardware resources needed together with the expected lifetime and the necessary maintenance and care measures including software updates, and, where relevant, a description of the mechanisms within the system allowing deployers to properly collect, store and interpret the logs in accordance with Article 12. This information must be provided in a concise, complete, correct and clear form that is relevant, accessible and comprehensible to deployers.

## rg_047 (easy) - 3/3

> Under the EU AI Act, what actions must a provider take when it considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity with the Regulation?

**AnsConc 51.07 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 20.1, Article 16, Article 79.2` | `expected: Article 20.1` | 985 chars | 14.62s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Immediately take necessary corrective action: bring into conformity, withdraw, disable, or recall, as appropriate
    - _States immediate corrective action: bring into conformity, withdraw, disable, or recall as appropriate_
2. `[PASS]` Inform distributors of the system concerned
    - _States must inform distributors of the system concerned_
3. `[PASS]` Where applicable, inform deployers, authorised representative and importers accordingly
    - _States where applicable must inform deployers, authorised representative and importers_

Tone: `PASS` _Professional, well-structured prose citing specific articles without self-reference or hedging._

**Answer**

> The provider must immediately take the necessary corrective actions to bring the system into conformity, to withdraw it, to disable it, or to recall it, as appropriate, under Article 20.1. It must inform the distributors of the high-risk AI system concerned and, where applicable, the deployers, the authorised representative and the importers. Where that system presents a risk within the meaning of Article 79.1 and the provider becomes aware of the risk, Article 20.2 requires it to immediately investigate the causes in collaboration with the reporting deployer, and to inform the market surveillance authorities competent for the system and, where applicable, the notified body that issued a certificate for it, in particular of the nature of the non-compliance and of any relevant corrective action taken. Article 16 anchors these duties in the provider's core obligations, requiring it to take the necessary corrective actions and provide the information required by Article 20.

## rg_048 (easy) - 3/3

> Under Regulation (EU) 2024/1689, what is the definition of (a) a "conformity assessment body" and (b) "conformity assessment"?

**AnsConc 100.0 | RefL 100.0 | RefS 50.0 | RefC 100.0**

`refs: Article 3.21` | `expected: Article 3.20, Article 3.21` | 375 chars | 3.31s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Conformity assessment body: a body that performs third-party conformity assessment activities
    - _States body performs third-party conformity assessment activities._
2. `[PASS]` Conformity assessment body: activities include testing, certification and inspection
    - _Lists testing, certification and inspection as activities._
3. `[PASS]` Conformity assessment: the process of demonstrating whether the Chapter III, Section 2 requirements for a high-risk AI system have been fulfilled
    - _States process of demonstrating fulfillment of Chapter III, Section 2 requirements for high-risk AI system._

Tone: `PASS` _Professional, neutral, well-structured definitions with clear article citations._

**Answer**

> A "conformity assessment body" is defined in Article 3(21) as a body that performs third-party conformity assessment activities, including testing, certification and inspection. "Conformity assessment" is defined in Article 3(20) as the process of demonstrating whether the requirements set out in Chapter III, Section 2 relating to a high-risk AI system have been fulfilled.

## rg_049 (easy) - 3/3

> Under the EU AI Act (Regulation (EU) 2024/1689) Article 95, who may draw up codes of conduct, and which bodies must encourage and facilitate their drawing up?

**AnsConc 46.21 | RefL 100.0 | RefS 50.0 | RefC 100.0**

`refs: Article 95.1` | `expected: Article 95.1, Article 95.2` | 937 chars | 7.02s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Codes of conduct may be drawn up by individual providers or deployers of AI systems, by organisations representing them, or both
    - _States codes may be drawn up by individual providers/deployers, representative organisations, or both_
2. `[PASS]` May involve interested stakeholders and their representative organisations, including civil society and academia
    - _Mentions involvement of interested stakeholders including civil society and academia_
3. `[PASS]` The AI Office and the Member States must encourage and facilitate the drawing up of codes of conduct
    - _States AI Office and Member States must encourage and facilitate drawing up of codes_

Tone: `PASS` _Professional, neutral, well-structured prose citing specific provisions clearly._

**Answer**

> Codes of conduct may be drawn up under Article 95(3) by individual providers or deployers of AI systems, by organisations representing them, or by both, including with the involvement of any interested stakeholders and their representative organisations, such as civil society organisations and academia. The AI Office and the Member States must encourage and facilitate their drawing up under Article 95(1), including the related governance mechanisms, to foster voluntary application to AI systems other than high-risk AI systems of some or all of the requirements in Chapter III, Section 2, taking account of available technical solutions and industry best practices. Under Article 95(4) the AI Office and the Member States must take into account the specific interests and needs of SMEs, including start-ups, when doing so. A single code may cover one or more AI systems, taking into account the similarity of their intended purpose.

## rg_050 (easy) - 2/2

> Under the EU AI Act, which AI systems in the financial services area are classified as high-risk under Annex III(5)(b), and what explicit exceptions are listed?

**AnsConc 42.14 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Annex III.5.b, Annex III.5.c, Article 6.3.d` | `expected: Annex III.5.b` | 757 chars | 7.61s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` AI systems evaluating creditworthiness or establishing credit score of natural persons
    - _States AI systems evaluating creditworthiness or establishing credit score of natural persons are high-risk._
2. `[PASS]` Exception: AI systems used for detecting financial fraud
    - _States the exception for AI systems used to detect financial fraud._

Tone: `PASS` _Professional, well-structured, and legally precise without hedging or self-reference._

**Answer**

> AI systems intended to be used to evaluate the creditworthiness of natural persons or to establish their credit score are high-risk under Annex III(5)(b), which sits within the Annex III area on access to and enjoyment of essential private services and essential public services and benefits, and is classified high-risk through the Annex III use-case route in Article 6(2). The single explicit exception stated in that point is for AI systems used for the purpose of detecting financial fraud, which therefore falls outside Annex III(5)(b). Separately, insurance-related pricing is addressed in its own point, Annex III(5)(c), covering AI systems used for risk assessment and pricing in relation to natural persons in the case of life and health insurance.

## rg_051 (easy) - 2/3  **FAILS**

> Under the EU AI Act, what must a provider established outside the EU do in order to place a high-risk AI system on the Union market?

**AnsConc 100.0 | RefL 100.0 | RefS 0.0 | RefC 100.0**

`refs: Article 22.3` | `expected: Article 22.1` | 645 chars | 10.87s | judge spread [0.667, 0.667, 0.667]

1. `[PASS]` Appoint an authorised representative established in the Union, by written mandate
    - _States written mandate appointing EU-established authorised representative._
2. `[PASS]` Must occur prior to making the system available on the Union market
    - _States this must occur before making the system available on the Union market._
3. `[FAIL]` Representative empowered per Article 22(3) tasks (verify conformity documentation, retain records 10 years, provide information/log access to authorities, cooperate with authorities, handle registration)
    - _Only references that tasks are 'specified in the mandate' without stating any of the specific Article 22(3) tasks._

Tone: `PASS` _Professional, neutral, well-structured prose citing relevant provisions clearly._

**Answer**

> A provider established in a third country must, by written mandate, appoint an authorised representative established in the Union before making its high-risk AI system available on the Union market (Article 22(1)). The provider must enable that authorised representative to perform the tasks specified in the mandate (Article 22(2)). The mandate is not merely formal: the authorised representative must terminate it, and immediately inform the relevant market surveillance authority and, where applicable, the notified body, if it has reason to consider the provider to be acting contrary to its obligations under the Regulation (Article 22(4)).

## rg_052 (easy) - 6/6

> Under the EU AI Act, what minimum elements must a provider's quality management system (QMS) for high-risk AI systems include? List the required elements.

**AnsConc 45.26 | RefL 100.0 | RefS 100.0 | RefC 25.0**

`refs: Article 17.1, Article 9.2, Article 72.4, Article 73.9` | `expected: Article 17.1` | 2119 chars | 22.97s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Regulatory compliance strategy incl. conformity assessment and modification management
    - _States regulatory compliance strategy including conformity assessment and modification management_
2. `[PASS]` Design, development, quality control and verification techniques/procedures
    - _States design, design control/verification and development quality control/assurance techniques_
3. `[PASS]` Examination, test and validation procedures and their frequency
    - _States examination, test and validation procedures and their frequency_
4. `[PASS]` Data management procedures across data lifecycle
    - _States data management procedures covering acquisition, collection, analysis, labelling, storage, filtration, mining, aggregation, retention_
5. `[PASS]` Article 9 risk management system and Article 72 post-market monitoring system
    - _Mentions Article 9 risk management system and Article 72 post-market monitoring system_
6. `[PASS]` Record-keeping and accountability framework for management/staff
    - _States record-keeping systems and accountability framework for management/staff_

Tone: `PASS` _Content is professional but the enumeration is presented as one dense run-on sentence rather than a readable list, hindering clarity._

**Answer**

> Article 17(1) requires providers of high-risk AI systems to put in place a quality management system that ensures compliance with the Regulation, documented in a systematic and orderly manner in written policies, procedures and instructions. Its minimum elements are a strategy for regulatory compliance including compliance with conformity assessment procedures and procedures for the management of modifications, techniques and procedures for design, design control and design verification, techniques and procedures for development, quality control and quality assurance, examination, test and validation procedures to be carried out before, during and after development and their frequency, technical specifications including standards to be applied, systems and procedures for data management covering acquisition, collection, analysis, labelling, storage, filtration, mining, aggregation and retention, the risk management system required by Article 9, the setting-up, implementation and maintenance of a post-market monitoring system under Article 72, procedures for the reporting of a serious incident under Article 73, the handling of communication with national competent authorities, other relevant authorities, notified bodies and other operators, systems and procedures for record-keeping of all relevant documentation and information, resource management including security-of-supply measures, and an accountability framework setting out the responsibilities of management and other staff. Under Article 17(2) implementation of those aspects must be proportionate to the size of the provider's organisation, while respecting in any event the degree of rigour and level of protection needed for compliance. Providers already subject to quality management obligations or an equivalent function under sectoral Union law may include these aspects in that system under Article 17(3), and under Article 17(4) financial institutions complying with internal governance arrangements or processes under Union financial services law are deemed to fulfil the obligation, with the exception of points (g), (h) and (i).

## rg_053 (easy) - 4/4

> Under the EU AI Act, what additional obligations apply to providers of a general-purpose AI model that is classified as a model with systemic risk?

**AnsConc 45.64 | RefL 100.0 | RefS 100.0 | RefC 14.29**

`refs: Article 53.1, Article 55.1, Article 51.1, Annex XIII, Annex XI.2, Annex XII.2, Article 56.2` | `expected: Article 55.1` | 1687 chars | 9.0s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Perform state-of-the-art model evaluation including documented adversarial testing to identify/mitigate systemic risks
    - _States state-of-the-art evaluation with documented adversarial testing to identify/mitigate systemic risks_
2. `[PASS]` Assess and mitigate possible Union-level systemic risks, including their sources
    - _States assessing and mitigating Union-level systemic risks including sources_
3. `[PASS]` Track, document and report serious incidents and corrective measures to the AI Office/national competent authorities without undue delay
    - _States tracking, documenting and reporting serious incidents/corrective measures without undue delay to AI Office/national authorities_
4. `[PASS]` Ensure adequate cybersecurity protection for the model and its physical infrastructure
    - _States ensuring adequate cybersecurity for the model and its physical infrastructure_

Tone: `PASS` _Professional, well-organized, and dense but coherent regulatory prose._

**Answer**

> Providers of a general-purpose AI model with systemic risk must comply with four obligations under Article 55 in addition to the baseline Article 53 duties, namely performing model evaluation in accordance with standardised protocols and tools reflecting the state of the art, including conducting and documenting adversarial testing to identify and mitigate systemic risks, assessing and mitigating possible systemic risks at Union level including their sources arising from development, placing on the market or use of the model, keeping track of, documenting and reporting without undue delay to the AI Office and, as appropriate, to national competent authorities relevant information about serious incidents and possible corrective measures, and ensuring an adequate level of cybersecurity protection for the model and for its physical infrastructure. Classification as a model with systemic risk follows Article 51, either through high-impact capabilities, presumed where cumulative training compute exceeds 10^25 floating point operations, or by Commission decision on the Annex XIII criteria. The Article 53 baseline continues to apply, meaning technical documentation of the model per Annex XI, information and documentation for downstream providers per Annex XII, a policy to comply with Union copyright law, and a publicly available sufficiently detailed summary of the training content, and the Article 53(2) exemption for free and open-source models from the documentation duties does not extend to models with systemic risk. Compliance may be demonstrated through the codes of practice facilitated by the AI Office under Article 56 until a harmonised standard is published.

## rg_054 (easy) - 4/4

> Under the EU AI Act, what are the four grounds on which non-compliance with the Act may be alleged (as listed in Article 79(6))?

**AnsConc 67.51 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 79.6, Article 5.1.h, Article 50` | `expected: Article 79.6` | 791 chars | 7.12s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Non-compliance with prohibition of AI practices under Article 5
    - _States non-compliance with Article 5 prohibited practices_
2. `[PASS]` Failure of high-risk AI system to meet Chapter III, Section 2 requirements
    - _States failure to meet Chapter III, Section 2 requirements_
3. `[PASS]` Shortcomings in harmonised standards/common specifications under Articles 40-41
    - _States shortcomings in harmonised standards/common specifications under Articles 40-41_
4. `[PASS]` Non-compliance with Article 50
    - _States non-compliance with Article 50_

Tone: `PASS` _Professional, neutral tone with clear enumeration of the four grounds and supporting context._

**Answer**

> Article 79.6 requires the notifying market surveillance authority to indicate whether the alleged non-compliance is due to one or more of four grounds: non-compliance with the prohibition of the AI practices referred to in Article 5, a failure of a high-risk AI system to meet the requirements set out in Chapter III, Section 2, shortcomings in the harmonised standards or common specifications referred to in Articles 40 and 41 conferring a presumption of conformity, and non-compliance with Article 50. These indications accompany the notification details identifying the non-compliant AI system, its origin and supply chain, the nature of the non-compliance and risk involved, the nature and duration of the national measures taken, and the arguments put forward by the relevant operator.

## rg_055 (easy) - 3/3

> Under the EU AI Act, in which specific situations may law enforcement use 'real-time' remote biometric identification in publicly accessible spaces for law-enforcement purposes (i.e., the exceptions to the prohibition)? List the permitted objectives.

**AnsConc 51.6 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 5.1.h, Annex II` | `expected: Article 5.1.h` | 1593 chars | 10.69s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Targeted search for victims of abduction, trafficking, sexual exploitation, or missing persons
    - _States targeted search for victims of abduction, trafficking, sexual exploitation, and missing persons._
2. `[PASS]` Prevention of specific, substantial and imminent threat to life/physical safety, or genuine terrorist attack threat
    - _States prevention of specific, substantial, imminent threat to life/safety or genuine terrorist attack threat._
3. `[PASS]` Localisation/identification of a suspect for investigation, prosecution, or executing a penalty for an Annex II offence punishable by at least 4 years custodial sentence/detention order
    - _States localisation/identification of a suspect for investigation, prosecution, or execution of penalty for Annex II offence with ≥4 year custodial threshold._

Tone: `PASS` _Professional third-person register with dense but coherent, well-ordered legal detail._

**Answer**

> Three exhaustive objectives only, and each use must be strictly necessary. Article 5(1)(h) permits real-time remote biometric identification in publicly accessible spaces for law enforcement purposes solely for the targeted search for specific victims of abduction, trafficking in human beings or sexual exploitation as well as the search for missing persons, the prevention of a specific, substantial and imminent threat to the life or physical safety of natural persons or of a genuine and foreseeable threat of a terrorist attack, and the localisation or identification of a person suspected of having committed a criminal offence for the purpose of conducting a criminal investigation, prosecution or executing a criminal penalty. That third objective is confined to the offences listed in Annex II, which enumerates terrorism, trafficking in human beings, sexual exploitation of children, illicit trafficking in narcotic drugs, weapons or nuclear material, murder, kidnapping, rape, armed robbery, organised crime, participation in a criminal organisation and environmental crime, and only where the offence is punishable in the Member State concerned by a custodial sentence of at least four years. Any such deployment further requires prior judicial or independent administrative authorisation, with an urgency exception allowing use to begin before authorisation provided it is requested without undue delay and within 24 hours, failing which use must stop immediately, and the deployer must notify the relevant market surveillance authority and the national data protection authority.

## rg_056 (easy) - 3/3

> Under Article 32 of Regulation (EU) 2024/1689, when is a conformity assessment body presumed to comply with the requirements in Article 31?

**AnsConc 57.22 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 31.7, Article 32` | `expected: Article 32` | 963 chars | 5.9s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Body demonstrates conformity with relevant harmonised standards (or parts thereof)
    - _States body demonstrates conformity with relevant harmonised standards or parts thereof_
2. `[PASS]` Condition: references to those standards published in the Official Journal of the European Union
    - _States references must be published in the Official Journal of the EU_
3. `[PASS]` Presumption limited to the extent those standards cover the Article 31 requirements
    - _States presumption extends only insofar as the standards cover those requirements_

Tone: `PASS` _Professional, neutral prose accurately summarizing the presumption mechanism, though densely packed into long sentences._

**Answer**

> A conformity assessment body is presumed to comply with Article 31 where it demonstrates its conformity with the criteria laid down in the relevant harmonised standards, or parts thereof, the references of which have been published in the Official Journal of the European Union, and that presumption extends only in so far as those applicable harmonised standards cover those requirements (Article 32). Article 31 sets the substantive requirements so presumed, including establishment under the national law of a Member State with legal personality, independence from the provider and from the AI system assessed, no involvement in the design, marketing or use of the systems assessed, safeguards against conflicts of interest, documented confidentiality procedures, sufficient permanent personnel with competences in AI technologies, data and computing, adequate cybersecurity, and appropriate liability insurance unless liability is assumed by the Member State.

## rg_057 (easy) - 3/3

> Who is entitled to lodge a complaint about an infringement, and to which authority must the complaint be submitted?

**AnsConc 78.26 | RefL 100.0 | RefS 0.0 | RefC 100.0**

`refs: Article 85` | `expected: Article 85.1` | 621 chars | 5.13s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Any natural or legal person
    - _States any natural or legal person may submit a complaint_
2. `[PASS]` Grounds to consider there has been an infringement of the Regulation
    - _States grounds to consider there has been an infringement of the Regulation_
3. `[PASS]` Submitted to the relevant market surveillance authority
    - _States it must be submitted to the relevant market surveillance authority_

Tone: `PASS` _Professional, well-structured prose with clear regulatory attribution._

**Answer**

> Any natural or legal person having grounds to consider that there has been an infringement of the Regulation may submit a complaint, and it must be submitted to the relevant market surveillance authority under Article 85. The right is not limited to infringements affecting the complainant's own rights, and it operates without prejudice to other administrative or judicial remedies. Such complaints must be taken into account for the purpose of conducting market surveillance activities and handled in line with the dedicated procedures established by the market surveillance authorities under Regulation (EU) 2019/1020.

## rg_058 (easy) - 5/5

> Under the EU AI Act, what must providers of AI systems that generate or manipulate synthetic content do to enable identification of AI-generated/manipulated output, and what quality criteria must that solution meet?

**AnsConc 74.09 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 50.2` | `expected: Article 50.2` | 1158 chars | 8.28s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Marking must be machine-readable format
    - _States marking must be machine-readable_
2. `[PASS]` Marking must be detectable as artificially generated or manipulated
    - _States marking must be detectable as artificially generated or manipulated_
3. `[PASS]` Solution must be effective, interoperable, robust and reliable, as far as technically feasible
    - _States solution must be effective, interoperable, robust and reliable as far as technically feasible_
4. `[PASS]` Feasibility judged against content-type specificities/limitations, implementation costs, and state of the art
    - _Lists content-type specificities/limitations, implementation costs, and state of the art_
5. `[PASS]` Exemptions: assistive editing, no substantial alteration of input data/semantics, or law-enforcement authorisation
    - _Lists all three exemptions: assistive editing, no substantial alteration, law enforcement authorisation_

Tone: `PASS` _Professional, well-organized regulatory summary with clear structure and no self-referential hedging._

**Answer**

> Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video or text content must ensure under Article 50(2) that the outputs are marked in a machine-readable format and detectable as artificially generated or manipulated. That technical solution must be effective, interoperable, robust and reliable as far as is technically feasible, taking into account the specificities and limitations of the various types of content, the costs of implementation and the generally acknowledged state of the art, as may be reflected in relevant technical standards. The marking duty does not apply to the extent the AI system performs an assistive function for standard editing or does not substantially alter the input data provided by the deployer or the semantics thereof, nor where the system is authorised by law to detect, prevent, investigate or prosecute criminal offences. Where information is owed to natural persons, Article 50(5) requires it to be given in a clear and distinguishable manner at the latest at the time of the first interaction or exposure, and to conform to the applicable accessibility requirements.

## rg_059 (easy) - 2/4  **FAILS**

> Under the EU AI Act, what is the scientific panel of independent experts, what are its main support/advisory tasks, and what key characteristics/selection requirements apply to its members?

**AnsConc 67.24 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 68.4, Article 98.2, Article 90.1` | `expected: Article 68` | 1465 chars | 11.56s | judge spread [0.5, 0.5, 0.5]

1. `[PASS]` Established by Commission via implementing act (Article 98(2) examination procedure) to support enforcement, not a decision-making body itself
    - _States establishment by Commission implementing act under Art 98(2) to support enforcement activities._
2. `[FAIL]` Tasks: advise/support AI Office on general-purpose AI models (alerting systemic risks under Article 90, developing evaluation tools/benchmarks, advising on classification); plus support market surveillance authorities, cross-border surveillance (Article 74(11)), and Union safeguard procedure (Article 81)
    - _Only mentions GPAI-related tasks (alerts, tools, classification advice) but omits support to market surveillance authorities, cross-border surveillance, and the Union safeguard procedure._
3. `[FAIL]` Selection: experts chosen by Commission for up-to-date scientific/technical AI expertise, independence from any AI provider, and ability to act diligently, accurately and objectively
    - _Does not mention selection criteria such as Commission's choice based on expertise, independence, or diligence/accuracy/objectivity._
4. `[PASS]` Members must act impartially, confidentially and free of instructions, each publishing a declaration of interests
    - _Covers impartiality, confidentiality, no instructions, and public declaration of interests as required._

Tone: `PASS` _Professional, third-person, well-structured explanation citing relevant provisions._

**Answer**

> The scientific panel is a body of independent experts established by Commission implementing act under Article 68(1), adopted in accordance with the examination procedure referred to in Article 98(2), and intended to support the enforcement activities under the Regulation. Its main support and advisory tasks centre on Chapter V general-purpose AI models: alerting the AI Office to systemic risks, contributing to the development of tools and methodologies for evaluating the capabilities of general-purpose AI models, and advising on the classification of general-purpose AI models with systemic risk. That alert function operates through the qualified alert to the AI Office under Article 90(1), where the panel has reason to suspect that a general-purpose AI model poses a concrete identifiable risk at Union level. As to members, Article 68(4) requires the experts to perform their tasks with impartiality and objectivity, to ensure the confidentiality of information and data obtained, and to neither seek nor take instructions from anyone in exercising those tasks, with each expert drawing up a publicly available declaration of interests and the AI Office establishing systems and procedures to actively manage and prevent potential conflicts of interest. The implementing act must also set the conditions, procedures and detailed arrangements for the panel and its members to issue alerts and to request the assistance of the AI Office, per Article 68(5).

## rg_060 (easy) - 3/3

> Under the EU AI Act, if a provider identifies a serious incident during testing in real-world conditions of a high-risk AI system, what three actions must the provider take?

**AnsConc 47.64 | RefL None | RefS None | RefC None**

`refs: Article 73.6` | `expected: not annotated` | 1291 chars | 12.37s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Perform (without delay) the necessary investigation into the incident and the AI system, including a risk assessment
    - _States provider must without delay perform necessary investigations including risk assessment._
2. `[PASS]` Take corrective action
    - _Explicitly mentions taking corrective action._
3. `[PASS]` Cooperate with competent authorities (and notified body where relevant), and not alter the AI system in a way affecting evaluation of the incident's causes without first informing the competent authorities
    - _States cooperation with competent authorities and notified body, and no alteration affecting cause evaluation without informing authorities._

Tone: `PASS` _Professional, well-structured, and directly enumerates the three actions with proper citations._

**Answer**

> The provider must first report the serious incident to the market surveillance authority of the Member State where the incident occurred under Article 73(1), within the tiered deadlines that run from awareness (immediately and no later than 2 days for a widespread infringement or serious and irreversible disruption of critical infrastructure, no later than 10 days where a death is involved, and no later than 15 days for other serious incidents). Second, under Article 73(6) the provider must without delay perform the necessary investigations in relation to the serious incident and the AI system concerned, including a risk assessment of the incident and corrective action. Third, the provider must cooperate with the competent authorities and, where relevant, the notified body concerned during those investigations, and must not perform any investigation involving alteration of the AI system in a way that may affect a subsequent evaluation of the causes of the incident before informing the competent authorities of such action. These duties operate alongside the conditions governing testing in real world conditions outside AI regulatory sandboxes under Article 60, which subjects such testing to an approved real-world testing plan and to market surveillance authority oversight.

## rg_061 (easy) - 2/2

> Under the EU AI Act, which body has exclusive powers to supervise and enforce the obligations for providers of general-purpose AI models (Chapter V), and which entity is entrusted with implementing those tasks?

**AnsConc 74.77 | RefL 50.0 | RefS 50.0 | RefC 100.0**

`refs: Article 88.1, Article 94` | `expected: Article 88.1, Article 75.1` | 646 chars | 6.22s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` European Commission has exclusive powers to supervise and enforce Chapter V
    - _States the Commission has exclusive powers to supervise and enforce Chapter V_
2. `[PASS]` AI Office is entrusted with implementing these tasks
    - _States implementation is entrusted to the AI Office_

Tone: `PASS` _Professional, well-structured prose directly answering the question with proper citations._

**Answer**

> The Commission has exclusive powers to supervise and enforce Chapter V, the obligations of providers of general-purpose AI models, taking into account the procedural guarantees under Article 94, and it entrusts the implementation of those tasks to the AI Office under Article 88(1). That allocation is without prejudice to the Commission's powers of organisation and the division of competences between the Member States and the Union under the Treaties. Under Article 88(2), market surveillance authorities may request the Commission to exercise those powers where necessary and proportionate to assist with their own tasks under the Regulation.

## rg_062 (easy) - 1/3  **FAILS**

> What must a distributor do if it considers a high-risk AI system is not in conformity with the Act's requirements? Additionally, what extra steps are required if the system presents a risk within the meaning of Article 79(1)?

**AnsConc 72.86 | RefL 100.0 | RefS 0.0 | RefC 50.0**

`refs: Article 24.2, Article 79.1` | `expected: Article 24.4` | 796 chars | 5.55s | judge spread [0.333, 0.333, 0.333]

1. `[PASS]` Not make it available on market until brought into conformity
    - _States distributor must not make the system available until brought into conformity._
2. `[FAIL]` If risk under Art 79(1): immediately inform provider or importer and the competent authorities
    - _Mentions informing provider or importer but omits informing competent authorities and 'immediately'._
3. `[FAIL]` Notification must detail the non-compliance and any corrective actions taken
    - _No mention that the notification must detail the non-compliance and corrective actions taken._

Tone: `PASS` _Professional, well-structured, and directly answers both parts in coherent regulatory prose._

**Answer**

> A distributor that considers, or has reason to consider on the basis of the information in its possession, that a high-risk AI system is not in conformity with the requirements set out in Section 2 must not make that system available on the market until it has been brought into conformity with those requirements, under Article 24(2). Where the high-risk AI system additionally presents a risk within the meaning of Article 79(1), Article 24(2) requires the distributor to inform the provider or the importer of the system, as applicable, to that effect. These duties sit alongside the distributor's pre-market verification obligation under Article 24(1) that the system bears the required CE marking and is accompanied by a copy of the EU declaration of conformity and the instructions for use.

## rg_063 (easy) - 6/6

> Under Article 2(1) of Regulation (EU) 2024/1689 (EU AI Act), which categories of actors/persons does the Act apply to? List the categories.

**AnsConc 93.73 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 2.1` | `expected: Article 2.1` | 766 chars | 4.77s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Providers placing on the market/putting into service AI systems or placing on the market GPAI models in the Union
    - _States providers placing/putting AI systems or GPAI models on market in Union_
2. `[PASS]` Deployers of AI systems established/located in the Union
    - _States deployers established or located in Union_
3. `[PASS]` Providers and deployers in third countries where the AI system's output is used in the Union
    - _States providers/deployers in third country where output used in Union_
4. `[PASS]` Importers, distributors, and product manufacturers (placing an AI system on the market/into service with their product under their own name/trademark)
    - _Lists importers, distributors, and product manufacturers with own name/trademark condition_
5. `[PASS]` Authorised representatives of providers not established in the Union
    - _States authorised representatives of providers not established in Union_
6. `[PASS]` Affected persons located in the Union
    - _States affected persons located in Union_

Tone: `PASS` _Professional, neutral enumeration in a single well-structured sentence listing all categories._

**Answer**

> Article 2(1) applies the Regulation to seven categories of actors: providers placing AI systems on the market or putting them into service, or placing general-purpose AI models on the market in the Union, irrespective of establishment in the Union or a third country, deployers of AI systems established or located within the Union, providers and deployers established or located in a third country where the output produced by the AI system is used in the Union, importers and distributors of AI systems, product manufacturers placing on the market or putting into service an AI system together with their product and under their own name or trademark, authorised representatives of providers not established in the Union, and affected persons located in the Union.

## rg_064 (easy) - 1/1

> Under the EU AI Act, what conditions must be met before data collected and processed for testing high-risk AI systems in real-world conditions can be transferred to a third country (outside the EU)?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 60.4.e` | `expected: Article 60.4.e` | 490 chars | 4.94s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Appropriate and applicable safeguards under Union law must be implemented for the transfer
    - _States that appropriate and applicable safeguards under Union law must be implemented for the transfer_

Tone: `PASS` _Professional, neutral, and well-structured explanation without self-reference or hedging._

**Answer**

> Only where appropriate and applicable safeguards under Union law are implemented. Article 60(4)(e) makes this one of the cumulative conditions that must all be met before a provider or prospective provider may conduct testing in real world conditions of a high-risk AI system outside an AI regulatory sandbox. Beyond that safeguards condition, Article 60 does not itself prescribe any further transfer-specific formality for the data collected and processed for the purpose of that testing.

## rg_065 (easy) - 3/3

> What are the three maximum administrative fine tiers for (a) prohibited AI practices, (b) non-compliance with obligations for high-risk AI systems and general-purpose AI (GPAI) models, and (c) supplying incorrect/incomplete/misleading information? For each tier, give the maximum amount in EUR and the alternative maximum as a percentage of worldwide annual turnover.

**AnsConc 53.9 | RefL 100.0 | RefS 100.0 | RefC 9.09**

`refs: Article 99.5, Article 5.6, Article 16, Article 22.3, Article 23.6, Article 24.4, Article 26.10, Article 31.4, Article 33, Article 34.2, Article 50.2` | `expected: Article 99` | 1525 chars | 11.56s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Prohibited AI practices (Article 5): up to EUR 35,000,000 or 7% of total worldwide annual turnover, whichever higher
    - _States EUR 35,000,000 or 7% whichever higher_
2. `[PASS]` High-risk/GPAI obligations (Articles 16, 22, 23, 24, 26, 31, 33(1)(3)(4), 34, 50): up to EUR 15,000,000 or 3% of total worldwide annual turnover, whichever higher
    - _States EUR 15,000,000 or 3% whichever higher, tied to the listed obligations_
3. `[PASS]` Incorrect/incomplete/misleading information to notified bodies or national competent authorities: up to EUR 7,500,000 or 1% of total worldwide annual turnover, whichever higher
    - _States EUR 7,500,000 or 1% whichever higher for misleading information_

Tone: `PASS` _Professional, well-structured prose covering each tier clearly, though dense._

**Answer**

> Non-compliance with the Article 5 prohibited practices carries administrative fines of up to EUR 35 000 000 or 7 % of total worldwide annual turnover for the preceding financial year, whichever is higher, under Article 99(3). Article 99(4) sets the second ceiling at up to EUR 15 000 000 or 3 %, whichever is higher, for breaches of the closed list of operator and notified-body duties: provider obligations under Article 16, authorised representative obligations under Article 22, importer obligations under Article 23, distributor obligations under Article 24, deployer obligations under Article 26, notified-body requirements under Article 31, Article 33(1), (3) and (4) or Article 34, and the transparency obligations of providers and deployers under Article 50. Supplying incorrect, incomplete or misleading information to notified bodies or national competent authorities in reply to a request is subject to up to EUR 7 500 000 or 1 %, whichever is higher, under Article 99(5). General-purpose AI model providers are fined separately by the Commission under Article 101, up to EUR 15 000 000 or 3 % of annual total worldwide turnover, whichever is higher, for intentional or negligent infringement of the relevant provisions, non-compliance with an information request or supply of incorrect, incomplete or misleading information, failure to comply with a requested measure, or refusal of model access for evaluation. For SMEs, including start-ups, Article 99(6) applies the lower of the percentage or the fixed amount.

## rg_066 (easy) - 2/3  **FAILS**

> Under the EU AI Act, what is the EU database for high-risk AI systems, what categories of information must it contain, and who is the controller of that database?

**AnsConc 48.96 | RefL 100.0 | RefS 100.0 | RefC 28.57**

`refs: Article 71.5, Annex III.7.b, Article 6.2, Article 49.4, Article 60.4.c, Annex VIII.12, Annex IX.5` | `expected: Article 71, Annex VIII` | 1348 chars | 16.64s | judge spread [0.667, 0.667, 0.667]

1. `[PASS]` EU database (set up/maintained by Commission with Member States) covers high-risk AI systems under Art 6(2) registered per Arts 49 and 60, and non-high-risk Art 6(3) systems registered per Art 6(4) and 49
    - _Candidate correctly describes coverage of both Art 6(2) high-risk (Arts 49/60) and Art 6(3) non-high-risk systems._
2. `[FAIL]` Categories: Annex VIII Sections A and B entered by provider/authorised representative; Section C entered by deployer that is/acts on behalf of a public authority, agency or body
    - _Candidate mentions Sections A and B entered by provider/authorised representative but omits Section C entered by deployer._
3. `[PASS]` Controller: the Commission
    - _Candidate states the Commission is the controller of the EU database._

Tone: `PASS` _Dense run-on sentences packed with citations make it hard to parse despite professional tone._

**Answer**

> The EU database is a central register of high-risk AI systems set up and maintained by the Commission in collaboration with the Member States under Article 71(1), covering the Annex III high-risk AI systems registered in accordance with Articles 49 and 60 as well as systems classified by their provider as not high-risk under the Article 6(3) derogation, with its data machine-readable, navigable and searchable and split between a publicly accessible part and restricted sections. Under Article 71(2) the provider or, where applicable, the authorised representative enters the information listed in Sections A and B of Annex VIII, while registration of testing in real world conditions under Article 60(4) carries a Union-wide unique single identification number and the information specified in Annex IX. Article 71(5) permits personal data only in so far as necessary, including the names and contact details of the natural persons responsible for registering the system who hold legal authority to represent the provider or the deployer. The Commission is the controller of the EU database, and for the law enforcement, migration, asylum and border control systems of Annex III points 1, 6 and 7 the registration sits in a secure non-public section under Article 49(4) accessible only to the Commission and the designated national authorities.

## rg_067 (easy) - 3/3

> What are the conditions to classify general-purpose AI (GPAI) model as "GPAI model with systemic risk"? Do all need to be met at the same time?

**AnsConc 48.66 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 51.1, Article 53.1, Article 55.1, Annex XIII` | `expected: Article 51.1, Annex XIII` | 1383 chars | 20.78s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Condition (a): high impact capabilities per Article 51(1)(a), presumed when training compute exceeds 10^25 FLOPs
    - _States high impact capabilities condition and the 10^25 FLOPs presumption_
2. `[PASS]` Condition (b): Commission decision (ex officio or following qualified alert from scientific panel) that capabilities/impact are equivalent, per Annex XIII criteria
    - _States Commission decision route ex officio or via qualified alert per Annex XIII criteria_
3. `[PASS]` No, not cumulative - either condition alone suffices
    - _Explicitly says conditions are not cumulative and either alone suffices_

Tone: `PASS` _Professional, well-structured legal explanation directly answering both parts of the question._

**Answer**

> Article 51(1) classifies a general-purpose AI model as a general-purpose AI model with systemic risk on either of two alternative conditions: it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks, or the Commission decides, ex officio or following a qualified alert from the scientific panel, that it has capabilities or an impact equivalent to those high impact capabilities, having regard to the criteria set out in Annex XIII. No, the conditions are not cumulative, because Article 51(1) requires only that the model meet any of those conditions, so either route alone suffices. Article 51(2) adds a rebuttable presumption of high impact capabilities where the cumulative amount of computation used for training, measured in floating point operations, is greater than 10^25 FLOPs. Once so classified, the provider owes the Article 55 obligations, namely state-of-the-art model evaluation including documented adversarial testing, assessment and mitigation of systemic risks at Union level, reporting of serious incidents to the AI Office without undue delay, and adequate cybersecurity protection for the model and its physical infrastructure, in addition to the Article 53 duties on technical documentation, downstream-provider information, copyright policy, and the training-content summary.

## rg_068 (easy) - 0/3  **FAILS**

> For a high-risk AI system, who is responsible for ensuring that input data is relevant and sufficiently representative for the system's intended purpose, and under what condition does that responsibility apply?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 33.33**

`refs: Article 6.2, Article 26.1, Article 10.3` | `expected: Article 10.3` | 515 chars | 9.42s | judge spread [0.0, 0.0, 0.0]

1. `[FAIL]` Provider of the high-risk AI system
    - _Answer attributes responsibility to the deployer, not the provider._
2. `[FAIL]` Applies whenever the system is developed using techniques involving training AI models with data (Art. 10(1))
    - _Answer does not mention the condition of training AI models with data under Art. 10(1)._
3. `[FAIL]` For systems not using such training techniques, applies only to testing data sets (Art. 10(6))
    - _Answer does not address the Art. 10(6) exception limited to testing data sets._

Tone: `PASS` _Professional, well-structured, and directly answers the question with clear conditions._

**Answer**

> The deployer bears that responsibility. Article 26 sets out the deployer's obligations for high-risk AI systems, including ensuring that input data is relevant and sufficiently representative in view of the system's intended purpose. That duty applies only to the extent the deployer exercises control over the input data. It is distinct from the provider's data governance duty under Article 10, which requires training, validation and testing data sets to be relevant, representative, free of errors and complete.

## rg_069 (easy) - 0/3  **FAILS**

> I am a distributor of an AI systems. Do I have obligation not to jeopardize its conformity? I was not told if the system is high-risk or not. What if am I am importer instead?

**AnsConc 53.57 | RefL 100.0 | RefS 0.0 | RefC 66.67**

`refs: Article 24.1, Article 23.1, Article 43.3` | `expected: Article 24.3, Article 23.4` | 1120 chars | 20.28s | judge spread [0.0, 0.0, 0.0]

1. `[FAIL]` Yes, obligation applies regardless of high-risk knowledge
    - _Answer says obligation applies only if high-risk, not regardless of knowledge, contradicting the criterion._
2. `[FAIL]` Distributor: storage/transport must not jeopardise Section 2 compliance (Article 24(3))
    - _Answer discusses CE marking/documentation checks under Art 24, not storage/transport conditions affecting Section 2 compliance._
3. `[FAIL]` Importer: same obligation applies (Article 23(4))
    - _Answer cites Art 23 conformity assessment verification, not the storage/transport condition obligation under Art 23(4)._

Tone: `PASS` _Professional, neutral, and well-structured explanation of distributor and importer obligations._

**Answer**

> Yes, where the system is high-risk. Article 24 requires the distributor, before making a high-risk AI system available on the market, to verify that it bears the required CE marking, that it is accompanied by a copy of the EU declaration of conformity and the instructions for use, and that the provider and the importer have complied with their respective obligations. Article 24 also bars the distributor from making the system available where it considers, or has reason to consider on the basis of the information in its possession, that the system does not conform with the Section 2 requirements, until conformity is restored, and it must inform the provider or the importer where the system presents a risk. Because these duties attach only to high-risk AI systems, the distributor should establish the classification with the provider before making the system available. Acting instead as an importer, the operator's duties sit in Article 23, which requires it to verify before placing the high-risk AI system on the market that the relevant conformity assessment procedure under Article 43 has been carried out.

## rg_070 (easy) - 4/4

> Under the EU AI Act, is an AI system that is a safety component of a medical device classified as MDR Class I (non-sterile, non-measuring, non-reusable surgical) automatically a high-risk AI system? Explain your reasoning.

**AnsConc 58.47 | RefL 100.0 | RefS 0.0 | RefC 50.0**

`refs: Article 6.2, Annex I.19` | `expected: Article 6.1` | 1192 chars | 7.92s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No
    - _Answer states 'No, not automatically.'_
2. `[PASS]` Article 6(1)(a) and (b) are cumulative conditions
    - _States both conditions must be met (cumulative)._
3. `[PASS]` MDR Class I (non-sterile, non-measuring, non-reusable surgical) devices undergo manufacturer self-assessment, not third-party conformity assessment
    - _States Class I device is self-certified without notified body involvement._
4. `[PASS]` Condition (b) fails, so Article 6(1) does not apply
    - _States condition (b) fails and the Annex I route does not classify it as high-risk._

Tone: `PASS` _Professional, well-structured legal reasoning without self-reference or hedging._

**Answer**

> No, not automatically. Article 6(1) makes a safety component high-risk only where both conditions are met: the AI system is a safety component of a product covered by the Union harmonisation legislation listed in Annex I, which includes Regulation (EU) 2017/745 on medical devices at Annex I point 11, and that product is required to undergo a third-party conformity assessment for its placing on the market under that sectoral legislation. A Class I device that is non-sterile, without a measuring function and not reusable surgical is self-certified by the manufacturer without notified body involvement, so the second condition in Article 6(1)(b) fails and the Annex I route does not classify the system as high-risk. The system could still be high-risk on the separate route in Article 6(2) if its intended purpose falls within one of the lettered use cases under the eight areas of Annex III, such as biometrics or critical infrastructure. Absent that, it is not high-risk, and any reclassification of the device to Class IIa, IIb or III, or the addition of a sterile, measuring or reusable surgical characteristic triggering notified body assessment, would bring it within Article 6(1).

## rg_071 (easy) - 3/3

> Under Regulation (EU) 2024/1689 (EU AI Act), can the same AI system be subject both to the Act's "high-risk AI system" obligations and to the transparency obligations sometimes described informally as "limited risk"? Explain briefly.

**AnsConc 65.45 | RefL None | RefS None | RefC None**

`refs: Article 50.4` | `expected: not annotated` | 1152 chars | 11.66s | judge spread [0.667, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer opens with 'Yes' as its clear position._
2. `[PASS]` Article 50(6): Article 50(1)-(4) transparency duties do not affect Chapter III high-risk obligations
    - _States transparency duties apply alongside, not instead of, high-risk obligations, capturing the substance of Art.50(6)._
3. `[PASS]` Obligations are cumulative, not mutually exclusive
    - _States the two regimes 'apply cumulatively' rather than exclusively._

Tone: `PASS` _Professional, well-structured explanation with correct legal register._

**Answer**

> Yes, the two regimes apply cumulatively to the same system. The transparency obligations in Article 50 attach to a system's characteristics rather than to its risk tier, so a high-risk AI system that also exhibits one of those characteristics must satisfy both sets of duties. Concretely, the provider must design a system intended to interact directly with natural persons so that the person is informed they are interacting with an AI system (Article 50(1)) and must mark synthetic outputs in a machine-readable format detectable as artificially generated or manipulated (Article 50(2)), while the deployer must inform natural persons exposed to an emotion recognition or biometric categorisation system (Article 50(3)) and disclose image, audio or video content constituting a deep fake (Article 50(4)). The deep fake disclosure does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences, and where the content forms part of an evidently artistic, creative, satirical, fictional or analogous work it is limited to disclosure in a manner that does not hamper the display or enjoyment of the work.

## rg_072 (easy) - 4/4

> Under the EU AI Act, can an AI system intended to be used as a toy qualify as a high-risk AI system, and if so under what conditions?

**AnsConc 66.7 | RefL 100.0 | RefS 0.0 | RefC 100.0**

`refs: Article 6.2, Annex I.18` | `expected: Article 6.1, Annex I.a.2` | 1135 chars | 20.04s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer opens with 'Yes'._
2. `[PASS]` Condition: AI system is a toy or safety component of a toy covered by Directive 2009/48/EC (Annex I harmonisation legislation)
    - _States AI system as toy or safety component of toy under Directive 2009/48/EC in Annex I._
3. `[PASS]` Condition: that toy is required to undergo third-party conformity assessment under the Directive
    - _States toy must require third-party conformity assessment under the Directive._
4. `[PASS]` Both conditions cumulative (Article 6(1))
    - _States both conditions of Article 6(1) must be satisfied together._

Tone: `PASS` _Professional and substantively focused, though one run-on sentence with a stray period slightly mars readability without destroying overall clarity._

**Answer**

> Yes, where both conditions of Article 6(1) are satisfied: the AI system is intended to be used as a safety component of a toy, or is itself a toy, covered by Directive 2009/48/EC on the safety of toys, which appears at point 2 of Annex I as Union harmonisation legislation. The second, deciding condition is that the toy must be required to undergo a third-party conformity assessment with a view to its placing on the market or putting into service under that Directive. If the toy may instead be self-assessed by the manufacturer, the Article 6(1) route is not triggered and the AI system is not high-risk on that basis, irrespective of whether it is placed on the market independently of the toy. Where the classification does bite, the provider must undergo the conformity assessment under Article 43, and a new conformity assessment is required upon any substantial modification under Article 43(4), while pre-determined changes already documented at the initial assessment do not count as such., so the practical test in each case is whether Directive 2009/48/EC itself mandates notified-body involvement for that particular toy.

## rg_073 (easy) - 4/4

> Under the EU AI Act, can an AI system intended to be used as a safety component in a lift qualify as a high-risk AI system, and under what conditions?

**AnsConc 60.27 | RefL 100.0 | RefS 50.0 | RefC 100.0**

`refs: Article 6.2, Annex I.4` | `expected: Article 6.1, Annex I` | 1037 chars | 8.3s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer states 'Yes, high-risk'_
2. `[PASS]` Condition: AI system intended as safety component of a product covered by Annex I Union harmonisation legislation
    - _States AI system must be intended as safety component of a product covered by Annex I legislation, citing lifts directive_
3. `[PASS]` Condition: that product (or the AI system itself as a product) required to undergo third-party conformity assessment under that legislation
    - _States the product or AI system as product must undergo third-party conformity assessment under that legislation_
4. `[PASS]` Both conditions cumulative
    - _Explicitly states both conditions are cumulative_

Tone: `PASS` _Professional, well-structured explanation of the two-condition test with no self-reference or hedging._

**Answer**

> Yes, high-risk, provided both cumulative conditions in Article 6(1) are satisfied. The first condition is met because the AI system is intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in Annex I, which includes at point 4 Directive 2014/33/EU on lifts and safety components for lifts. The second condition is that the lift, or the safety component itself as a product, must be required to undergo a third-party conformity assessment with a view to its placing on the market or putting into service under that Directive; absent that third-party assessment requirement, the Article 6(1) route is not triggered. This classification applies irrespective of whether the AI system is placed on the market or put into service independently of the lift, and the provider must then pass the conformity assessment under Article 43, which is carried out under the sectoral lifts procedure, with a fresh conformity assessment required upon any substantial modification under Article 43(4).

## rg_074 (easy) - 4/4

> Under the EU AI Act (Regulation (EU) 2024/1689), are AI systems intended for emotion recognition from biometric data always prohibited? If not, in which contexts are they prohibited, what exception applies, and how are they classified when not prohibited?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 66.67**

`refs: Article 5.1.f, Article 50.3, Annex III.1.c` | `expected: Annex III.1.c, Article 5.1.f` | 321 chars | 0.09s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` No
    - _States not categorically prohibited._
2. `[PASS]` Prohibited context: inferring emotions of natural persons in workplace and education institutions (Article 5(1)(f))
    - _Names workplace and educational institutions as prohibited contexts._
3. `[PASS]` Exception: use intended for medical or safety reasons
    - _States medical/safety exception._
4. `[PASS]` When not prohibited, classified as high-risk under Annex III (emotion recognition/biometrics category)
    - _States high-risk classification under Annex III.1(c) when not prohibited._

Tone: `PASS` _Concise, neutral, well-structured professional explanation._

**Answer**

> Emotion recognition is not categorically prohibited under the AI Act; the prohibition in Article 5 only applies in workplaces and educational institutions, with a narrow medical/safety exception. Elsewhere the system is high-risk under Annex III.1(c) and triggers Article 50(3) transparency duties toward exposed persons.

## rg_075 (easy) - 3/3

> I generated audio with AI for my artistic work (sole purpose). Do I need to provide some marking of its artificial nature? I feel that would compromise the enjoyment of the work.

**AnsConc 50.87 | RefL 100.0 | RefS 100.0 | RefC 50.0**

`refs: Article 50.4, Article 50.2` | `expected: Article 50.4` | 1154 chars | 10.09s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes, disclosure still required
    - _Answer explicitly states 'Yes, marking is required'._
2. `[PASS]` No need for marking that hampers enjoyment
    - _States transparency obligation limited so as not to hamper display or enjoyment of the work._
3. `[PASS]` Must disclose existence of AI-generated content in appropriate/unobtrusive manner
    - _States disclosure limited to disclosing existence of generated content in an appropriate manner._

Tone: `PASS` _Professional, well-structured explanation directly addressing the legal question without self-reference or hedging._

**Answer**

> Yes, marking is required, though the artistic purpose relaxes the form of disclosure rather than removing it. As provider of the generative AI system, Article 50(2) requires the synthetic audio outputs to be marked in a machine-readable format and detectable as artificially generated or manipulated, with exemptions only for standard editing functions that do not substantially alter the input data and for legally authorised criminal-investigation use, so the artistic character of the work does not displace that machine-readable marking. Where the audio constitutes a deep fake, the deployer's disclosure duty under Article 50(4) applies, but for content forming part of an evidently artistic, creative, satirical or fictional work that transparency is limited to disclosing the existence of generated or manipulated content in an appropriate manner that does not hamper the display or enjoyment of the work. In practice the machine-readable marking sits in the file metadata or watermark and stays invisible to the audience, while any human-facing notice can be placed in credits or accompanying material rather than within the listening experience.

## rg_076 (easy) - 1/1

> Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?

**AnsConc 100.0 | RefL 100.0 | RefS 100.0 | RefC 100.0**

`refs: Article 3.2` | `expected: Article 3.2` | 90 chars | 0.01s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Combination of probability of occurrence of harm and severity of that harm
    - _Matches the statutory definition exactly._

Tone: `PASS` _Concise, professional, accurate paraphrase of the statutory definition with no meta-commentary._

**Answer**

> The combination of the probability of an occurrence of harm and the severity of that harm.

## rg_077 (easy) - 3/3

> For AI systems that fit within the use cases listed in Annex III but are considered non-high-risk by the provider, do they need to be registered in the EU database?

**AnsConc 60.5 | RefL 100.0 | RefS 0.0 | RefC 20.0**

`refs: Annex III.7.b, Article 6.2, Article 49.1, Article 71.1, Annex VIII.12` | `expected: Article 49.2` | 1010 chars | 7.51s | judge spread [1.0, 1.0, 1.0]

1. `[PASS]` Yes
    - _Answer begins with 'Yes.'_
2. `[PASS]` Registration required under Article 49(2)
    - _States Article 49(2) requires registration for these systems._
3. `[PASS]` Registered in EU database referred to in Article 71
    - _States registration is entered in the EU database under Article 71._

Tone: `PASS` _Professional, well-structured explanation citing relevant articles without self-reference or hedging._

**Answer**

> Yes. Where a provider concludes under Article 6(3) that an Annex III system is not high-risk, because it performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the previously completed human assessment, or performs a preparatory task, and it does not profile natural persons, Article 49(2) still requires that provider or its authorised representative to register themselves and that system in the EU database before placing it on the market or putting it into service. The registration is entered in the EU database established and maintained by the Commission under Article 71, which expressly covers systems not considered high-risk pursuant to Article 6(3). The information to be supplied is Section B of Annex VIII, the section dedicated to Article 6(3) non-high-risk assessments, alongside the provider's documented self-assessment made before placing the system on the market.
