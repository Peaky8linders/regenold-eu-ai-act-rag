# EU AI Act RAG — Live 110 Hard-Mode Benchmark: Complete Q&A & Judge Remarks

**Evaluation Arm:** `r390-live-hard-opus5`  
**Replay Mode:** Official Hard Mode (Rolling Conversation History + Adversarial Pushback Turn)  
**LLM Judge:** OpenRouter Claude Opus 5 (`anthropic/claude-opus-5`) with 3 repetitions (temp 0.1)  
**Total Questions:** 110  
**All-Pass Questions:** 88 / 110 (80.0%)  
**Regulatory Tone Pass Rate:** 109 / 110 (99.1%)  
**Adversarial Concession Rate:** 0 / 110 (0.0%)  

---

## Summary of Rubric Scores

| Axis | Score | Benchmark Comparison |
| :--- | :---: | :--- |
| **Ans. Correctness (Loose)** | **91.0%** | +1.1 pp over official baseline (89.9%) |
| **Ans. Correctness (Strict)** | **80.0%** | Matches official baseline (80.0%) |
| **Ans. Conciseness** | **62.1%** | +16.9 pp over official baseline (45.2%) |
| **Ref. Correctness (Loose)** | **95.0%** | **BEATS 2026 Frontier (94.6%)** |
| **Ref. Correctness (Strict)** | **67.7%** | Precision floor against calibrated refkey |
| **Ref. Conciseness** | **49.6%** | Balanced citation density |
| **Regulatory Tone** | **99.1%** | +3.0 pp over official baseline (96.1%) |
| **Response Speed** | **78.6%** | Hard-mode 2-turn latency envelope |
| **OVERALL (Geometric Mean)** | **76.1** | **+2.7 pp over official baseline (73.4)** |

---

## Question-by-Question Live Results & Judge Remarks

### [001/110] rg_001 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 387 chars  
**References Cited:** `Article 11.1, Annex IV.2`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?

**Live Answer (Post-Pushback Graded):**
```text
Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Description of the hardware on which the AI system is intended to run (Annex IV.1.e)

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [002/110] rg_002 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 382 chars  
**References Cited:** `Article 50.4`  
**Expected References:** `Article 50.4`  

> **Question:**  
> Does the obligation to indicate that deep-fakes are artificially generated apply when prosecuting a criminal offence?

**Live Answer (Post-Pushback Graded):**
```text
No. Under Article 50(4), the deployer's duty to disclose that image, audio, or video content constituting a deep fake has been artificially generated or manipulated does not apply where the use is authorised by law to detect, prevent, investigate, or prosecute criminal offences. Absent that law-enforcement authorisation, the deployer must disclose that the content is a deep fake.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Deep-fake disclosure exemption covers detection, prevention, investigation or prosecution of criminal offences

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [003/110] rg_003 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 13.4s | **Length:** 1317 chars  
**References Cited:** `Annex III.7.b, Article 6.2`  
**Expected References:** `Article 6.3`  

> **Question:**  
> When the intended use of an AI system is listed in Annex III of the EU AI Act, the AI system is automatically high-risk, isn't it? If not, can you explain when that is not the case?

**Live Answer (Post-Pushback Graded):**
```text
Not always. Under Article 6(2) a system is high-risk only where it falls within one of the lettered use cases listed under the eight Annex III areas of biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes, so a system that merely touches an area heading without matching a listed use case is not caught. Even where a use case is matched, the Article 6(3) derogation removes the system from the high-risk tier where it does not pose a significant risk of harm to health, safety or fundamental rights, including by not materially influencing the outcome of decision making, and it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the previously completed human assessment without proper human review, or performs a preparatory task to an Annex III assessment. That derogation never applies where the system performs profiling of natural persons, in which case it is always high-risk. The provider must document this assessment before the system is placed on the market or put into service.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Exception applies where system does not pose significant risk of harm to health, safety or fundamental rights, including by not materially influencing outcome of decision making
- **Criterion 3** [✓ PASS]: Exception requires one of: narrow procedural task; improving result of previously completed human activity; detecting deviations from prior decision-making patterns without replacing/influencing human assessment; preparatory task to an Annex III assessment
- **Criterion 4** [✓ PASS]: Exception never applies (system is always high-risk) if it performs profiling of natural persons

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 49'].
```

---

### [004/110] rg_004 — Cross-Framework & Sectoral MedTech Integration (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 28.3s | **Length:** 908 chars  
**References Cited:** `Article 6.1, Article 43.3, Annex I`  
**Expected References:** `Article 6.1`  

> **Question:**  
> I have a medical device that has an AI system as a safety component. The medical device is classified "medium-risk" and undergoes a 3rd party conformity assessment. Is the AI system "medium risk" too? If yes, why? If not, why not?

**Live Answer (Post-Pushback Graded):**
```text
No, the AI system is not "medium risk"; it is high-risk, because the EU AI Act does not mirror the medical device risk classes and instead applies its own tiers. Under Article 6(1), an AI system is high-risk where both conditions are met: it is intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in Annex I, which includes Regulation (EU) 2017/745 on medical devices, and that product is required to undergo a third-party conformity assessment under that legislation. Both limbs are satisfied here, so the device's own "medium-risk" class is legally irrelevant to the AI classification, which is binary rather than graduated. Article 43(3) then integrates the AI Act assessment into the sectoral procedure, so the medical device notified body controls conformity with the Chapter III, Section 2 requirements as part of a single conformity assessment.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes - high-risk (AI Act has no "medium-risk" category)
- **Criterion 2** [✓ PASS]: Condition (a): AI system is safety component of a product covered by Annex I legislation (medical devices under Regulation (EU) 2017/745)
- **Criterion 3** [✓ PASS]: Condition (b): that product is required to undergo third-party conformity assessment
- **Criterion 4** [✓ PASS]: Both conditions cumulative under Article 6(1), irrespective of the device's own sectoral risk classification

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [005/110] rg_005 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 7.5s | **Length:** 340 chars  
**References Cited:** `Article 13.3, Article 14.4, Article 15.1`  
**Expected References:** `Article 13.1`  

> **Question:**  
> Does the EU AI Act explicitly requires to use explainable AI techniques such as LIME or SHAP to increase the trustworthiness of high-risk AI systems?

**Live Answer (Post-Pushback Graded):**
```text
No, the EU AI Act mandates no specific explainable-AI technique such as LIME or SHAP, and Article 13 instead requires only that high-risk AI systems be sufficiently transparent for deployers to interpret their output. Article 14 requires effective human oversight, and Article 15 requires appropriate accuracy, robustness and cybersecurity.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Article 13 requires sufficient transparency/interpretability for deployers, without naming a technique
- **Criterion 3** [✓ PASS]: Requirement is outcome-based and technology-neutral, leaving choice of method to the provider

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [006/110] rg_006 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 3.9s | **Length:** 484 chars  
**References Cited:** `Article 2.1.a, Article 3.1, Article 51.1`  
**Expected References:** `Article 2.1.a`  

> **Question:**  
> Does the EU AI Act apply to AI systems or AI models or both?

**Live Answer (Post-Pushback Graded):**
```text
The EU AI Act's core regime governs AI systems, defined in Article 3(1) and brought within scope by Article 2, through the risk-based tiers (prohibited practices under Article 5, high-risk systems under Article 6, and limited-risk transparency duties under Article 50). General-purpose AI models are regulated separately under Chapter V (Articles 51 to 56), are defined in Article 3(63), and carry their own provider obligations with additional duties for models posing systemic risk.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Both AI systems and AI models
- **Criterion 2** [✗ FAIL]: Art 2(1)(a): providers placing/putting into service AI systems
- **Criterion 3** [✗ FAIL]: Art 2(1)(a): providers placing general-purpose AI models on the market

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Art 2(1)(a): providers placing/putting into service AI systems'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Art 2(1)(a): providers placing general-purpose AI models on the market'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [007/110] rg_007 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.4s | **Length:** 922 chars  
**References Cited:** `Article 5.1.g, Article 6.2, Annex III.1.a, Annex I`  
**Expected References:** `Annex III.1.a, Article 5.1`  

> **Question:**  
> We want to deploy an AI system that performs biometric verification solely to confirm that a specific natural person is the person he or she claims to be. Is this system prohibited? Is it high-risk?

**Live Answer (Post-Pushback Graded):**
```text
Biometric verification whose sole purpose is to confirm that a specific natural person is the person he or she claims to be is neither prohibited nor high-risk. Article 5, which exhaustively lists the prohibited AI practices, does not cover it, and point 1(a) of Annex III expressly excludes AI systems intended to be used for biometric verification with that sole purpose from the remote biometric identification systems it classifies as high-risk. Such a system would nevertheless become high-risk if it is put to a further use falling within another Annex III point, such as biometric categorisation according to sensitive or protected attributes or emotion recognition under points 1(b) and 1(c), or if it is a safety component of a product covered by the Union harmonisation legislation in Annex I under Article 6(1). Deployment remains subject to Union data protection law governing the processing of biometric data.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No, not prohibited
- **Criterion 2** [✓ PASS]: No, not high-risk
- **Criterion 3** [✓ PASS]: Falls within Annex III.1(a) biometric verification exclusion

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 50'].
```

---

### [008/110] rg_008 — Cross-Framework & Sectoral MedTech Integration (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.7s | **Length:** 908 chars  
**References Cited:** `Article 6.2, Annex I`  
**Expected References:** `Article 6.1, Annex I.a.11`  

> **Question:**  
> Are AI safety components within medical devices of MDR class IIa, IIb, or III considered to be high-risk according to the EU AI Act? Why?

**Live Answer (Post-Pushback Graded):**
```text
AI safety components within medical devices of MDR class IIa, IIb or III are high-risk. Article 6(1) classifies an AI system as high-risk where both conditions are met: it is intended to be used as a safety component of a product, or is itself a product, covered by the Union harmonisation legislation listed in Annex I, and that product is required to undergo a third-party conformity assessment with a view to its placing on the market or putting into service. Annex I lists Regulation (EU) 2017/745 on medical devices, and classes IIa, IIb and III each require notified body involvement under that Regulation, so both limbs are satisfied irrespective of whether the AI system is placed on the market or put into service independently of the device. The classification holds regardless of the Annex III route in Article 6(2), which operates in addition to, not instead of, the Annex I product safety route.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Condition: AI system is a safety component of a product covered by Union harmonisation legislation listed in Annex I (the MDR)
- **Criterion 3** [✓ PASS]: Condition: that product must undergo third-party (notified body) conformity assessment to be placed on the market (Article 6(1))
- **Criterion 4** [✓ PASS]: MDR classes IIa, IIb, III require notified-body conformity assessment, so both cumulative conditions are met

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [009/110] rg_009 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 7.5s | **Length:** 606 chars  
**References Cited:** `Article 18.1, Article 11.1, Article 17.1, Article 47.1, Article 19.1`  
**Expected References:** `Article 18.1`  

> **Question:**  
> What documentation does a provider of a high-risk AI system needs to keep available for the national competent authorities, and for how long?

**Live Answer (Post-Pushback Graded):**
```text
Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Technical documentation (Article 11)
- **Criterion 2** [✓ PASS]: Quality management system documentation (Article 17)
- **Criterion 3** [✓ PASS]: Notified body change documentation and decisions/other documents, where applicable
- **Criterion 4** [✓ PASS]: EU declaration of conformity (Article 47)
- **Criterion 5** [✓ PASS]: 10 years after the system is placed on the market or put into service

**Judge Remarks & Telemetry:**
```text
✓ All 5 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [010/110] rg_010 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 30.9s | **Length:** 1522 chars  
**References Cited:** `Article 14.4, Annex III`  
**Expected References:** `Article 14`  

> **Question:**  
> Which article of the EU AI Act governs human oversight measures?

**Live Answer (Post-Pushback Graded):**
```text
Article 14 governs human oversight, requiring that high-risk AI systems be designed and developed, including with appropriate human-machine interface tools, so that they can be effectively overseen by natural persons during the period in which they are in use, in order to prevent or minimise risks to health, safety or fundamental rights arising in intended use or under conditions of reasonably foreseeable misuse. The oversight measures must be commensurate with the risks, level of autonomy and context of use, and are delivered either as measures built into the system by the provider before it is placed on the market or put into service, or as measures identified by the provider for implementation by the deployer. The measures must enable the individuals assigned to oversight to understand the system's capabilities and limitations and monitor its operation, remain aware of automation bias, correctly interpret its output, decide not to use the system or disregard, override or reverse its output, and intervene or interrupt it through a stop button or similar procedure. For remote biometric identification systems under point 1(a) of Annex III, Article 14(5) additionally bars the deployer from acting on an identification unless it has been separately verified and confirmed by at least two natural persons with the necessary competence, training and authority, save where Union or national law considers that requirement disproportionate for law enforcement, migration, asylum or border control authorities.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Article 14
- **Criterion 2** [✓ PASS]: Design for effective human oversight during use
- **Criterion 3** [✓ PASS]: Aim: prevent/minimise risks to health, safety, fundamental rights
- **Criterion 4** [✓ PASS]: Measures built in by provider and/or implemented by deployer
- **Criterion 5** [✓ PASS]: Overseers enabled to understand, monitor, interpret, override, and halt the system

**Judge Remarks & Telemetry:**
```text
✓ All 5 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 26'].
```

---

### [011/110] rg_011 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.6s | **Length:** 476 chars  
**References Cited:** `Article 3.32, Article 10.2`  
**Expected References:** `Article 10.3`  

> **Question:**  
> What is the meaning and purpose of 'testing data' in the context of AI systems, and why is it important that it is not leaked during the training process?

**Live Answer (Post-Pushback Graded):**
```text
Testing data is defined in Article 3(32) as data used to provide an independent evaluation of the AI system, in order to confirm its expected performance before it is placed on the market or put into service. If testing data leaks into the training process, the system is in effect assessed on data it has already seen, which inflates its apparent performance and defeats the purpose of the independent check that Article 10 requires for the datasets of a high-risk AI system.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Testing data is one of the training/validation/testing data sets under Article 10(1), used to check the high-risk AI system against its intended purpose after training and validation
- **Criterion 2** [✗ FAIL]: It must meet the Article 10(3) quality criteria: relevant, sufficiently representative, to the best extent possible free of errors, complete, and with appropriate statistical properties for the intended purpose
- **Criterion 3** [✓ PASS]: Leakage of training data into the testing set destroys the set's independence, so it can no longer reliably verify Article 10(3) compliance and instead yields inflated, misleading accuracy that masks errors, biases or gaps

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'It must meet the Article 10(3) quality criteria: relevant, sufficiently representative, to the best extent possible free of errors, complete, and with appropriate statistical properties for the intended purpose'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [012/110] rg_012 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 691 chars  
**References Cited:** `Annex III.8`  
**Expected References:** `Annex III.8`  

> **Question:**  
> What are the high-risk uses of AI systems listed under 'Administration of justice and democratic processes' cited in the EU AI Act?

**Live Answer (Post-Pushback Graded):**
```text
Annex III point 8 lists two high-risk use cases under administration of justice and democratic processes. Annex III point 8(a) covers AI systems intended to be used by a judicial authority, or on its behalf, to assist in researching and interpreting facts and the law and in applying the law to a concrete set of facts, or to be used similarly in alternative dispute resolution. Annex III point 8(b) covers AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, with a carve-out for tools that only organise, optimise or structure political campaigns from an administrative or logistical point of view.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: AI systems assisting a judicial authority (or on its behalf) in researching/interpreting facts and law and applying law to facts, or used similarly in alternative dispute resolution
- **Criterion 2** [✓ PASS]: AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote
- **Criterion 3** [✓ PASS]: Exclusion: does not cover AI systems whose output natural persons are not directly exposed to, e.g. tools organising/optimising/structuring political campaigns administratively or logistically

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [013/110] rg_013 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 4.5s | **Length:** 1075 chars  
**References Cited:** `Article 53.2, Article 51.1, Article 55.2, Annex XI.2`  
**Expected References:** `Article 53.2`  

> **Question:**  
> Under what conditions should providers of general-purpose AI models be subject to exceptions regarding transparency-related requirements, if any? And what do those exceptions not cover?

**Live Answer (Post-Pushback Graded):**
```text
The exceptions to the GPAI transparency-related obligations are set out in Article 53(2). The Article 53(1)(a) duty to draw up and keep up-to-date the technical documentation of the model (Annex XI) and the Article 53(1)(b) duty to provide information and documentation to downstream providers (Annex XII) do not apply to providers that release the model under a free and open-source licence allowing access, usage, modification and distribution, where the model parameters, including the weights, and information on the model architecture and usage, are made publicly available. The exception does not cover the remaining Article 53(1) obligations: the policy to comply with Union copyright law (Article 53(1)(c)) and the publicly available, sufficiently detailed summary of the training content (Article 53(1)(d)) apply regardless of the licence. The exception also does not apply to general-purpose AI models with systemic risk (Article 53(2), second subparagraph), which remain subject to the full Article 53 obligations together with the Article 55 systemic-risk duties.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes, exceptions exist
- **Criterion 2** [✓ PASS]: Condition: model released under free and open-source licence allowing access, usage, modification and distribution
- **Criterion 3** [✓ PASS]: Condition: parameters (weights, architecture info, usage info) made publicly available
- **Criterion 4** [✓ PASS]: Exception covers only points (a) and (b) of Article 53(1), not (c)/(d)
- **Criterion 5** [✓ PASS]: Exception does not apply to general-purpose AI models with systemic risk

**Judge Remarks & Telemetry:**
```text
✓ All 5 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [014/110] rg_014 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 24.6s | **Length:** 1401 chars  
**References Cited:** `Article 6.2, Annex III.3.c, Annex I`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> Which AI systems used in education or vocational training should be classified as high-risk according to the EU AI Act?

**Live Answer (Post-Pushback Graded):**
```text
Four use cases are high-risk under point 3 of Annex III (education and vocational training), which Article 6(2) makes high-risk classification turn on: AI systems intended to determine access or admission to, or to assign natural persons to, educational and vocational training institutions at all levels, systems to evaluate learning outcomes including where those outcomes steer the learning process, systems to assess the appropriate level of education an individual will receive or be able to access, and systems for monitoring and detecting prohibited behaviour of students during tests. Article 6(3) removes such a system from the high-risk tier where it poses no significant risk of harm to health, safety or fundamental rights and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or performs a preparatory task, but it remains high-risk whenever it profiles natural persons, and the provider must document that self-assessment before placing the system on the market. Separately, an AI system used in this sector is also high-risk under Article 6(1) where it is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I and that product must undergo third-party conformity assessment.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Access, admission, or assignment to educational/vocational training institutions at all levels
- **Criterion 2** [✓ PASS]: Evaluating learning outcomes, including to steer the learning process
- **Criterion 3** [✓ PASS]: Assessing the appropriate level of education an individual will receive or can access
- **Criterion 4** [✓ PASS]: Monitoring/detecting prohibited student behaviour during tests

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [015/110] rg_015 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 29.5s | **Length:** 1019 chars  
**References Cited:** `Article 50.1, Article 50.3`  
**Expected References:** `Article 50.1`  

> **Question:**  
> What obligations, if any, does the EU AI Act set in place for AI systems that interact directly with natural persons? What exceptions, if any, apply?

**Live Answer (Post-Pushback Graded):**
```text
Yes, a transparency obligation applies. Under Article 50(1), providers must ensure that AI systems intended to interact directly with natural persons are designed and developed so that the persons concerned are informed they are interacting with an AI system, and that information must be given in a clear and distinguishable manner at the latest at the time of the first interaction and in conformity with applicable accessibility requirements. Two limits apply: no disclosure is required where the AI nature is obvious to a reasonably well-informed, observant and circumspect natural person in the circumstances and context of use, and the obligation does not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties. That law enforcement exception is itself reversed where the system is available for the public to report a criminal offence, in which case the disclosure duty applies in full.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Obligation: providers must design/develop the system so natural persons are informed they are interacting with an AI system
- **Criterion 2** [✓ PASS]: Exception: not required where obvious to a reasonably well-informed, observant and circumspect person, given the circumstances and context of use
- **Criterion 3** [✓ PASS]: Exception: AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to safeguards for third parties' rights and freedoms — unless available for the public to report a criminal offence

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [016/110] rg_016 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 23.1s | **Length:** 1083 chars  
**References Cited:** `Article 99.3, Article 5.1.g, Article 100.1`  
**Expected References:** `Article 99.3`  

> **Question:**  
> What are the administrative fines for non-compliance with the prohibition of the AI practices?

**Live Answer (Post-Pushback Graded):**
```text
Non-compliance with the prohibition of the AI practices listed in Article 5 is subject to administrative fines of up to EUR 35 000 000 or, where the offender is an undertaking, up to 7 % of its total worldwide annual turnover for the preceding financial year, whichever is higher, under Article 99(3). This is the highest of the three ceilings in Article 99, which sets fines of up to EUR 15 000 000 or 3 % for breaches of the listed operator and notified-body obligations and up to EUR 7 500 000 or 1 % for supplying incorrect, incomplete or misleading information to notified bodies or competent authorities. For SMEs, including start-ups, Article 99(6) caps the fine at the lower of the percentage or the fixed amount, and all penalties must be effective, proportionate and dissuasive and take account of the gravity and nature of the infringement. Where the offender is a Union institution, body, office or agency, Article 100 instead empowers the European Data Protection Supervisor to impose fines of up to EUR 1 500 000 for infringements of the Article 5 prohibited practices.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: EUR 35,000,000 or 7% of total worldwide annual turnover for the preceding financial year, whichever is higher
- **Criterion 2** [✓ PASS]: Applies to non-compliance with Article 5 prohibited AI practices

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [017/110] rg_017 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 29.1s | **Length:** 1602 chars  
**References Cited:** `Annex II, Article 5.1.h`  
**Expected References:** `Article 5.1.h.iii, Annex II`  

> **Question:**  
> How does Annex II relate to prohibited uses of AI systems?

**Live Answer (Post-Pushback Graded):**
```text
Annex II does not itself prohibit anything. It functions as a closed list that narrows one exception to a prohibited practice: Article 5 prohibits real-time remote biometric identification in publicly accessible spaces for law enforcement purposes, and Article 5(1)(h)(iii) permits such use only to localise or identify a person suspected of an Annex II offence, and only where that offence is punishable in the Member State concerned by a custodial sentence or detention order for a maximum period of at least four years. The Annex II offences are terrorism, trafficking in human beings, sexual exploitation of children and child pornography, illicit trafficking in narcotic drugs or psychotropic substances, illicit trafficking in weapons munitions or explosives, murder, grievous bodily injury, illicit trade in human organs or tissue, illicit trafficking in nuclear or radioactive materials, kidnapping illegal restraint or hostage-taking, crimes within the jurisdiction of the International Criminal Court, unlawful seizure of aircraft or ships, rape, environmental crime, organised or armed robbery, sabotage, and participation in a criminal organisation involved in one or more of those offences. Annex II is irrelevant to the other Article 5 prohibited practices and to the two remaining Article 5(1)(h) objectives, namely the targeted search for victims of abduction, trafficking or sexual exploitation and for missing persons, and the prevention of a specific, substantial and imminent threat to life or physical safety or of a genuine and present or genuine and foreseeable terrorist attack.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Annex II lists criminal offences (does not itself prohibit anything)
- **Criterion 2** [✓ PASS]: Referenced in Article 5(1)(h)(iii) as basis for one exception to the Article 5(1)(h) prohibition on 'real-time' remote biometric identification in public spaces for law enforcement
- **Criterion 3** [✓ PASS]: Exception (localising/identifying a suspect) applies only if the offence is listed in Annex II and punishable by a custodial sentence/detention order of max at least four years

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [018/110] rg_018 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.2s | **Length:** 1575 chars  
**References Cited:** `Annex III.7.b, Article 97.2, Article 7.1`  
**Expected References:** `Article 7.1`  

> **Question:**  
> Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?

**Live Answer (Post-Pushback Graded):**
```text
Yes, the Commission may amend Annex III by adding or modifying use-cases of high-risk AI systems, but only through delegated acts adopted in accordance with Article 97 and only where two cumulative conditions in Article 7(1) are both met: the AI systems are intended to be used in one of the areas already listed in Annex III, and they pose a risk of harm to health and safety, or an adverse impact on fundamental rights, that is equivalent to or greater than the risk posed by the high-risk AI systems already listed there. In assessing that second condition the Commission must weigh the criteria in Article 7(2), including the intended purpose, the extent of use, the nature and amount of data processed, the degree of autonomy, the severity and reversibility of harm, and the availability of effective measures of redress or of measures preventing or substantially minimising the risks. Procedurally, Article 97 confers this power for five years from 1 August 2024 with tacit extension unless opposed, requires the Commission to consult experts designated by each Member State before adoption, and lets the act enter into force only if neither the European Parliament nor the Council objects within three months of notification, extendable by a further three months, with revocation possible at any time. The same delegated-act power under Article 7(3) allows removal of a use-case from Annex III only where it no longer poses any significant risk to fundamental rights, health or safety and the deletion does not decrease the overall level of protection under Union law.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Condition: AI intended to be used in any of the areas listed in Annex III
- **Criterion 3** [✓ PASS]: Condition: posed risk is equal or greater than those already referred to in Annex III
- **Criterion 4** [✓ PASS]: Both conditions must apply ("and" clause)

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [019/110] rg_019 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 7.5s | **Length:** 192 chars  
**References Cited:** `Article 3.60, Article 50.4, Article 71, Article 110`  
**Expected References:** `Article 3.60`  

> **Question:**  
> What is a deep fake according to the EU AI Act?

**Live Answer (Post-Pushback Graded):**
```text
AI-generated or manipulated image, audio or video content that resembles existing persons, objects, places, entities or events and would falsely appear to a person to be authentic or truthful.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: AI-generated or manipulated content
- **Criterion 2** [✓ PASS]: Image, audio, or video
- **Criterion 3** [✓ PASS]: Resembles existing persons, objects, places, entities or events
- **Criterion 4** [✓ PASS]: Falsely appears authentic or truthful to a person

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [020/110] rg_020 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 25.6s | **Length:** 977 chars  
**References Cited:** `Article 74.12, Article 78.3`  
**Expected References:** `Article 74.12`  

> **Question:**  
> Should market surveilance authorities be provided with remote access to documentations and data sets used to develop a high-risk AI system?

**Live Answer (Post-Pushback Graded):**
```text
Yes, where relevant and limited to what is necessary to fulfil their tasks, providers must grant market surveillance authorities full access to the documentation and to the training, validation and testing data sets used to develop a high-risk AI system, including, where appropriate and subject to security safeguards, through application programming interfaces (API) or other relevant technical means and tools enabling remote access, under Article 74, which governs market surveillance of AI systems. Access to the source code is a separate and narrower power under the same Article, granted only upon a reasoned request and only where such access is necessary to assess conformity with the Chapter III, Section 2 requirements and where testing, auditing and verification based on the data and documentation already provided have been exhausted or proved insufficient. Any information or documentation so obtained is subject to the confidentiality obligations of Article 78.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Full access to documentation and to training, validation and testing data sets, granted by providers, limited to what is necessary for the authority's tasks
- **Criterion 3** [✓ PASS]: Remote access (e.g. via API or other technical means) permitted only "where appropriate" and subject to security safeguards

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [021/110] rg_021 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.3s | **Length:** 1371 chars  
**References Cited:** `Article 15.1, Article 13.3, Article 9.2, Article 17.1`  
**Expected References:** `Article 15.1`  

> **Question:**  
> If a provider of a high-risk AI system confirms that the system achieves an appropriate level of accuracy, robustness, and cybersecurity at the time of development, then no further action is required by the provider on these aspects in the future. Correct?

**Live Answer (Post-Pushback Graded):**
```text
No. Article 15 requires high-risk AI systems to achieve an appropriate level of accuracy, robustness and cybersecurity and to perform consistently in those respects throughout their lifecycle, so the duty is continuing rather than satisfied once at development, and it extends to resilience against errors, faults or inconsistencies through technical redundancy such as back-up plans or fail-safe mechanisms, and to resilience against unauthorised third parties exploiting vulnerabilities to alter use, outputs or performance. That continuing performance must be maintained through the risk management system under Article 9, which is a documented iterative process maintained across the lifecycle, requiring identification of foreseeable risks, evaluation of risks under intended purpose and reasonably foreseeable misuse, and testing to ensure consistent performance. The quality management system under Article 17 reinforces this by requiring examination, test and validation procedures before, during and after development at a defined frequency, together with a strategy for managing modifications to the system. The declared levels of accuracy and accuracy metrics under Article 15(3) and Article 13(3)(b)(ii), including known and foreseeable circumstances affecting expected accuracy, robustness and cybersecurity, must remain accurate in the instructions for use.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Must perform consistently throughout lifecycle, including resilience to errors/faults/inconsistencies (Art. 15(1),(4))
- **Criterion 3** [✓ PASS]: Cybersecurity resilience against third-party exploitation is ongoing, not one-time (Art. 15(5))
- **Criterion 4** [✓ PASS]: Accuracy levels/metrics must be declared in instructions of use (Art. 15(3))

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [022/110] rg_022 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 621 chars  
**References Cited:** `Article 5, Article 6, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> What are all the risk categories in the EU AI Act?

**Live Answer (Post-Pushback Graded):**
```text
The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems have no mandatory duties under the Act, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Unacceptable risk - prohibited practices (Article 5)
- **Criterion 2** [✓ PASS]: High risk - Article 6, referencing Annex I (product safety) and Annex III (use cases)
- **Criterion 3** [✓ PASS]: Limited risk - transparency obligations (Article 50)
- **Criterion 4** [✓ PASS]: Minimal or no risk - no mandatory obligations, voluntary codes of conduct (Article 95)

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [023/110] rg_023 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 890 chars  
**References Cited:** `Article 51.1, Article 55.1, Article 53.2`  
**Expected References:** `Article 51.1`  

> **Question:**  
> Does "systemic risk" apply to AI systems or general purpose AI models or both?

**Live Answer (Post-Pushback Graded):**
```text
Under Article 51(1), a general-purpose AI model is classified as a model with systemic risk where it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks; under Article 51(2) a model is presumed to have high impact capabilities where the cumulative computation used for its training exceeds 10^25 floating point operations. The Commission may also designate a model on the basis of the Annex XIII criteria. A model classified as having systemic risk then carries the additional Article 55 obligations: model evaluation including adversarial testing, assessment and mitigation of systemic risks at Union level, serious-incident reporting, and adequate cybersecurity. The high-risk regime for AI systems under Articles 6 and Annex III is a separate classification and does not use the systemic-risk concept.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Applies to general-purpose AI models only (Article 51), not to AI systems
- **Criterion 2** [✓ PASS]: Systemic risk classification applies only to general-purpose AI models (Article 51), not to AI systems

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [024/110] rg_024 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 20.4s | **Length:** 1370 chars  
**References Cited:** `Article 6.2, Annex III.7.b, Annex I`  
**Expected References:** `Article 6.2, Annex III`  

> **Question:**  
> Are AI systems that fall under one of the areas of Annex III, but not falling within a use-case within such areas, considered high-risk?

**Live Answer (Post-Pushback Graded):**
```text
No. Falling within one of the eight areas of Annex III is not sufficient, because Article 6(2) classifies a system as high-risk only where it corresponds to one of the lettered use-cases listed under those numbered area headings, which cover biometrics, critical infrastructure, education and vocational training, employment and workers' management, access to essential private and public services and benefits, law enforcement, migration, asylum and border control management, and administration of justice and democratic processes. A system that operates in such an area but performs none of the listed use-cases is outside the Annex III route, though it may still be high-risk under Article 6(1) where it is a safety component of, or is itself, a product covered by the Union harmonisation legislation in Annex I that must undergo a third-party conformity assessment. Conversely, a system that does match a listed use-case is presumed high-risk unless the provider documents, before placing it on the market, that it poses no significant risk of harm under one of the Article 6(3) conditions, namely a narrow procedural task, improving the result of a previously completed human activity, detecting decision-making patterns or deviations without replacing or influencing the human assessment, or a preparatory task, and it never performs profiling of natural persons.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: High-risk requires falling within a specific enumerated use case listed in Annex III, not merely within the broader area grouping those use cases
- **Criterion 3** [✓ PASS]: Annex III areas are organisational headings; the operative trigger is the individual use-case description

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex I'].
```

---

### [025/110] rg_025 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 8.1s | **Length:** 785 chars  
**References Cited:** `Article 25.1, Article 16`  
**Expected References:** `Article 25.1`  

> **Question:**  
> Can an operator that is not a provider according to the EU AI Act, for example a deployer, take actions on a given high-risk AI system such that it can be effectively seen as a provider by the authorities? If yes, what kind of action would result in such an outcome?

**Live Answer (Post-Pushback Graded):**
```text
Yes. Under Article 25(1), a distributor, importer, deployer or other third party is deemed to be the provider of a high-risk AI system, and takes on the provider obligations in Article 16, in any of three cases. First, if it puts its name or trademark on a high-risk AI system already placed on the market (Article 25(1)(a)). Second, if it makes a substantial modification to a high-risk AI system that remains high-risk (Article 25(1)(b)). Third, if it modifies the intended purpose of an AI system, including a general-purpose AI system, so that it becomes high-risk (Article 25(1)(c)). In each of these three cases the operator assumes the provider obligations in Article 16, and the initial provider is no longer considered the provider of that specific system under Article 25(2).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Putting own name/trademark on a high-risk AI system already on the market/in service (Article 25(1)(a))
- **Criterion 3** [✓ PASS]: Substantial modification to a high-risk AI system already on the market/in service that remains high-risk under Article 6 (Article 25(1)(b))
- **Criterion 4** [✓ PASS]: Modifying the intended purpose of a non-high-risk (incl. general-purpose) AI system such that it becomes high-risk under Article 6 (Article 25(1)(c))

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [026/110] rg_026 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 24.7s | **Length:** 1038 chars  
**References Cited:** `Annex III.7.b, Annex I.5, Article 6.2`  
**Expected References:** `Article 6.2`  

> **Question:**  
> If I have an AI system that is high-risk because listed in the use cases of Annex III, and change it to a different use case that is not in Annex I or III, does it stay high-risk due to its historical provenance?

**Live Answer (Post-Pushback Graded):**
```text
No, classification is forward-looking and attaches to the system's intended purpose, not to its history. Under Article 6(2) an AI system is high-risk because it falls within one of the use cases listed in Annex III, which enumerates eight areas covering biometrics, critical infrastructure, education and vocational training, employment and workers' management, access to essential private and public services and benefits, law enforcement, migration, asylum and border control management, and administration of justice and democratic processes. Once the intended purpose is changed to a use case outside Annex III, and the system is neither a safety component of, nor itself, a product covered by the Union harmonisation legislation listed in Annex I requiring third-party conformity assessment under Article 6(1), it is no longer high-risk. The prior classification confers no residual high-risk status, though the change of intended purpose must be genuine and reflected in the system's documented intended purpose rather than nominal.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: High-risk status under Article 6 depends on the AI system's current intended purpose/use case, not its prior classification
- **Criterion 3** [✓ PASS]: If the new use case falls outside both Annex I and Annex III, neither condition in Article 6(1) or 6(2) is met, so the system is not high-risk

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [027/110] rg_027 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 493 chars  
**References Cited:** `Article 6.3, Article 50.1, Annex III.8`  
**Expected References:** `Article 50.2`  

> **Question:**  
> How are AI systems intended to influence the outcome of an election or referendum classified, and what exception is given for certain campaign-related tools?

**Live Answer (Post-Pushback Graded):**
```text
Under Annex III point 8(b), AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, are high-risk under Article 6(2). Annex III point 8(b) itself excludes systems to whose output natural persons are not directly exposed, such as tools used only to organise, optimise or structure political campaigns from an administrative or logistical point of view, which therefore fall outside this high-risk category.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: High-risk classification under Annex III, point 8(b)
- **Criterion 2** [✓ PASS]: Covers AI systems influencing election/referendum outcome or voters' voting behaviour
- **Criterion 3** [✓ PASS]: Exception: AI systems whose output natural persons are not directly exposed to are excluded
- **Criterion 4** [✓ PASS]: Example given: tools organising/optimising/structuring political campaigns administratively or logistically

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [028/110] rg_028 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 19.9s | **Length:** 1019 chars  
**References Cited:** `Article 1`  
**Expected References:** `Article 1`  

> **Question:**  
> According to Article 1, what is the objective of the EU AI Act?

**Live Answer (Post-Pushback Graded):**
```text
Article 1 states that the purpose of the Regulation is to improve the functioning of the internal market and promote the uptake of human-centric and trustworthy artificial intelligence, while ensuring a high level of protection of health, safety and fundamental rights enshrined in the Charter, including democracy, the rule of law and environmental protection, against the harmful effects of AI systems in the Union, and supporting innovation. To that end, Article 1 lays down harmonised rules for the placing on the market, the putting into service and the use of AI systems in the Union, prohibitions of certain AI practices, specific requirements for high-risk AI systems and obligations for operators of such systems, harmonised transparency rules for certain AI systems, harmonised rules for the placing on the market of general-purpose AI models, rules on market monitoring, market surveillance, governance and enforcement, and measures to support innovation with a particular focus on SMEs, including start-ups.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Improve functioning of the internal market
- **Criterion 2** [✓ PASS]: Promote uptake of human-centric and trustworthy AI
- **Criterion 3** [✓ PASS]: Ensure high level of protection of health, safety and fundamental rights (incl. democracy, rule of law, environment) against harmful effects of AI systems
- **Criterion 4** [✓ PASS]: Support innovation

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [029/110] rg_029 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 3.9s | **Length:** 535 chars  
**References Cited:** `Article 6.2, Annex III.5.d`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> Under the EU AI Act, which specific AI systems are explicitly listed as high-risk because they make decisions in critical life- and health-related situations involving emergency calls and triage?

**Live Answer (Post-Pushback Graded):**
```text
Under Annex III point 5(d), AI systems intended to be used for dispatching or prioritising in dispatching emergency first-response services, or for triage of emergency medical-service patients (including by fire brigades and medical aid), are explicitly listed as high-risk. They fall within the 'essential private and public services' category of the eight Annex III high-risk use cases and are classified as high-risk through the Annex III route of Article 6(2), which treats any system falling within a listed use case as high-risk.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✗ FAIL]: AI systems that evaluate and classify emergency calls by natural persons
- **Criterion 2** [✓ PASS]: AI systems used to dispatch, or establish priority in dispatching, emergency first response services (police, firefighters, medical aid)
- **Criterion 3** [✓ PASS]: Emergency healthcare patient triage systems

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'AI systems that evaluate and classify emergency calls by natural persons'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [030/110] rg_030 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 25.5s | **Length:** 793 chars  
**References Cited:** `Article 60.4.b, Article 76.2`  
**Expected References:** `Article 76.2`  

> **Question:**  
> Under Regulation (EU) 2024/1689, as part of their supervisory role for an AI regulatory sandbox, compliance with which specific Article must the market surveillance authority verify?

**Live Answer (Post-Pushback Graded):**
```text
Article 60. Where testing in real world conditions is carried out for AI systems supervised within an AI regulatory sandbox, the market surveillance authority must verify compliance with Article 60, which permits real-world testing of high-risk AI systems subject to an approved real-world testing plan, informed consent of test subjects, registration, and market surveillance oversight. That verification duty forms part of the authority's supervisory role for the sandbox under Article 76, which gives market surveillance authorities the competences and powers to ensure real-world testing conforms to the Regulation. The authority may, as appropriate, allow the provider or prospective provider to conduct that testing in derogation from the conditions in Article 60(4), points (f) and (g).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Article 60

**Judge Remarks & Telemetry:**
```text
✓ All 1 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 57'].
```

---

### [031/110] rg_031 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 3.9s | **Length:** 587 chars  
**References Cited:** `Article 6.3, Article 49.2, Annex III.7.b`  
**Expected References:** `Article 6.3.a`  

> **Question:**  
> Is an AI system used to structure or deduplicate information for a use case listed in Annex III considered high-risk?

**Live Answer (Post-Pushback Graded):**
```text
Under Article 6(3), an Annex III system is not high-risk where it poses no significant risk of harm and meets one of four conditions: it performs a narrow procedural task, it improves the result of a previously completed human activity, it detects decision-making patterns or deviations without replacing or influencing the human assessment, or it performs a preparatory task. Under Article 6(3), this exception never applies where the system profiles natural persons. The provider must document the assessment before placing the system on the market and register it under Article 49(2).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✗ FAIL]: No
- **Criterion 2** [✗ FAIL]: Falls under narrow procedural task derogation, Article 6(3), first subparagraph, point (a)
- **Criterion 3** [✓ PASS]: Exception: remains high-risk if system performs profiling of natural persons
- **Criterion 4** [✓ PASS]: Provider must document the assessment before placing on market/putting into service (Article 6(4))

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'No'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Falls under narrow procedural task derogation, Article 6(3), first subparagraph, point (a)'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [032/110] rg_032 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 3.8s | **Length:** 458 chars  
**References Cited:** `Article 6.3, Annex III`  
**Expected References:** `Article 6.3`  

> **Question:**  
> Is an AI system used to detect decision-making patterns or deviations for a use case listed in Annex III considered high-risk?

**Live Answer (Post-Pushback Graded):**
```text
Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No, not by default
- **Criterion 2** [✓ PASS]: Condition: not meant to replace or influence the previously completed human assessment, without proper human review
- **Criterion 3** [✓ PASS]: Exception: always high-risk if system performs profiling of natural persons

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [033/110] rg_033 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 508 chars  
**References Cited:** `Article 65.5`  
**Expected References:** `Article 65`  

> **Question:**  
> Regarding the European Artificial Intelligence Board: (1) Who designates its members? (2) How long is the term? How many times is the term renewable? (3) must members represent stakeholder interests or act impartially/objectively? (4) what voting threshold is required to adopt the Board's rules of procedure (is a simple 50%+1 majority enough)?

**Live Answer (Post-Pushback Graded):**
```text
The European Artificial Intelligence Board (Article 65) has one representative per Member State, each serving a three-year term renewable once under Article 65(3). Under Article 65(4) each is their Member State's single contact point rather than an independent stakeholder appointee, while Article 65(7) requires the Board to safeguard the objectivity and impartiality of its activities. Its rules of procedure are adopted by a two-thirds majority under Article 65(5), so a simple majority is not sufficient.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Members designated by their Member State
- **Criterion 2** [✓ PASS]: Term is three years, renewable once
- **Criterion 3** [✓ PASS]: No stakeholder representation requirement; must safeguard objectivity/impartiality
- **Criterion 4** [✓ PASS]: Two-thirds majority required to adopt rules of procedure (simple majority not enough)

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [034/110] rg_034 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 17.0s | **Length:** 798 chars  
**References Cited:** `Article 101.1, Article 99.5`  
**Expected References:** `Article 101.3`  

> **Question:**  
> Under the EU AI Act, what jurisdiction does the Court of Justice of the European Union have over Commission decisions fixing fines on providers of general-purpose AI models, and what can the Court do with the fine?

**Live Answer (Post-Pushback Graded):**
```text
The Court of Justice of the European Union has unlimited jurisdiction to review Commission decisions fixing a fine on a provider of a general-purpose AI model under Article 101, the provision under which the Commission may fine such providers up to EUR 15 000 000 or 3 % of total worldwide annual turnover, whichever is higher, for infringements of their Chapter V obligations, for supplying incorrect, incomplete or misleading information, or for failing to comply with a requested measure. Exercising that unlimited jurisdiction, the Court may cancel, reduce or increase the fine imposed. Before the Commission adopts such a decision it must communicate its preliminary findings to the provider and give it an opportunity to be heard, and any fine must be effective, proportionate and dissuasive.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Unlimited jurisdiction to review Commission decisions fixing a fine
- **Criterion 2** [✓ PASS]: Court may cancel the fine
- **Criterion 3** [✓ PASS]: Court may reduce the fine
- **Criterion 4** [✓ PASS]: Court may increase the fine

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [035/110] rg_035 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 24.5s | **Length:** 1649 chars  
**References Cited:** `Article 20.1, Article 79.2, Article 80.2, Article 6.2, Article 99.7`  
**Expected References:** `Article 80.2`  

> **Question:**  
> Consider the situation in which a market surveillance authority (MSA) determines that an AI system, originally classified as non-high-risk by the provider, is in fact high-risk. Does the provider need to recall and suspend the use of the system without undue delay, or does the MSA provide a timeframe within which the provider can take corrective actions? Or does this depend on the gravity of the situation?

**Live Answer (Post-Pushback Graded):**
```text
The market surveillance authority sets a period; immediate recall is not automatic. Under Article 80, which governs AI systems the provider classified as non-high-risk under the Article 6(3) derogation, the authority first evaluates the classification and, on finding the system high-risk, must without undue delay require the provider to bring it into compliance with the requirements and obligations of the Regulation and to take appropriate corrective action within a period the authority may prescribe, with fines under Article 99 where the provider misses that period or misclassified the system to circumvent Chapter III, Section 2. Gravity determines the length and the escalation: where the system also presents a risk to health, safety or fundamental rights, the Article 79 procedure sets the corrective period, to withdraw, recall or bring into compliance, at the shorter of the period prescribed or 15 working days, and if adequate corrective action is not taken in time Article 79(5) to (9) applies, allowing the authority to impose provisional measures prohibiting, restricting, withdrawing or recalling the system. Independently of any authority deadline, Article 20 obliges a provider that considers or has reason to consider a high-risk AI system already placed on the market not to be in conformity to take the necessary corrective actions immediately, namely bringing it into conformity, withdrawing, disabling or recalling it, and to inform distributors, deployers, the authorised representative and importers, and to inform the market surveillance authorities where the system presents a risk within the meaning of Article 79(1).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: MSA sets a compliance/corrective-action period for the provider, rather than an automatic without-undue-delay recall/suspension duty
- **Criterion 2** [✓ PASS]: Provider must bring the system into compliance and take corrective action within that MSA-prescribed period (Article 80(2) and 80(4))
- **Criterion 3** [✓ PASS]: Failure to comply within that period triggers fines under Article 99 (and Article 79(5)-(9) applies), not gravity-based variation of the timeframe

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [036/110] rg_036 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.5s | **Length:** 1146 chars  
**References Cited:** `Article 42.1, Article 10.4, Article 15.5`  
**Expected References:** `Article 42.1`  

> **Question:**  
> Under the EU AI Act, what presumption applies when a high-risk AI system is trained and tested on data that reflects the specific geographical, behavioural, contextual or functional setting in which it is intended to be used?

**Live Answer (Post-Pushback Graded):**
```text
A presumption of conformity applies: under Article 42(1), a high-risk AI system trained and tested on data reflecting the specific geographical, behavioural, contextual or functional setting within which it is intended to be used is presumed to comply with the relevant requirements of Article 10(4), which requires data sets to take into account, to the extent required by the intended purpose, the characteristics or elements particular to that setting. The presumption is confined to Article 10(4) and does not extend to the other data governance duties in Article 10, such as the data governance and management practices under Article 10(2) or the relevance, representativeness, error-freedom and completeness criteria under Article 10(3). Article 42(2) supplies a separate presumption, whereby high-risk AI systems certified, or for which a statement of conformity has been issued, under a cybersecurity scheme pursuant to Regulation (EU) 2019/881 with references published in the Official Journal are presumed to comply with the cybersecurity requirements of Article 15, in so far as that certificate or statement covers those requirements.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Presumed compliant with Article 10(3) representativeness/quality requirement for that setting
- **Criterion 2** [✓ PASS]: Presumption is limited to the extent required by the intended purpose
- **Criterion 3** [✓ PASS]: Not an exemption from other Article 10 obligations (e.g., bias examination/mitigation)

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 15'].
```

---

### [037/110] rg_037 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 40.9s | **Length:** 1913 chars  
**References Cited:** `Article 71.1, Article 49.4, Annex III.7.b, Annex VIII.12, Article 47.1`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> When registering a high-risk AI system in the EU database under the EU AI Act, what specific information must the provider submit? List the required items.

**Live Answer (Post-Pushback Graded):**
```text
Before placing a high-risk AI system listed in Annex III on the market or putting it into service, the provider or, where applicable, the authorised representative must register themselves and the system in the EU database that the Commission sets up and maintains under Article 71, entering the data listed in Section A of Annex VIII (Article 49). That information is the name, address and contact details of the provider, the same details of any person submitting on the provider's behalf, the name, address and contact details of the authorised representative where applicable, the AI system trade name and any additional unambiguous reference allowing identification and traceability, a description of the intended purpose and of the components and functions supported, a basic and concise description of the information used by the system (data, inputs) and its operating logic, the status of the AI system (on the market or in service, no longer placed on the market or in service, recalled), the type, number and expiry date of the certificate issued by the notified body with that body's name or identification number where applicable, a scanned copy of that certificate, any Member States in which the system has been placed on the market, put into service or made available in the Union, a copy of the EU declaration of conformity drawn up under Article 47, electronic instructions for use, and an optional URL for additional information. Electronic instructions for use are not submitted for high-risk AI systems in the areas of law enforcement or migration, asylum and border control management referred to in Annex III, points 1, 6 and 7, and for those systems registration is made in a secure non-public section of the database limited to the items identified in Article 49(4). High-risk AI systems referred to in point 2 of Annex III are registered at national level rather than in the EU database.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Registration confined to secure, non-public section of EU database (Article 71)
- **Criterion 2** [✗ FAIL]: Annex VIII Section A points 1-10, excluding 6, 8 and 9
- **Criterion 3** [✗ FAIL]: Annex VIII Section B points 1-5, 8 and 9
- **Criterion 4** [✗ FAIL]: Annex VIII Section C points 1-3
- **Criterion 5** [✗ FAIL]: Annex IX points 1, 2, 3 and 5

**Judge Remarks & Telemetry:**
```text
✗ Failed 4/5 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Annex VIII Section A points 1-10, excluding 6, 8 and 9'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Annex VIII Section B points 1-5, 8 and 9'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Annex VIII Section C points 1-3'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Annex IX points 1, 2, 3 and 5'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 6'].
```

---

### [038/110] rg_038 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 7.9s | **Length:** 315 chars  
**References Cited:** `Article 3.55, Article 57.5, Article 58, Article 1, Article 4`  
**Expected References:** `Article 57.1`  

> **Question:**  
> Under the EU AI Act, what is an "AI regulatory sandbox"? Provide the definition elements (what it is, who sets it up, for whom it is intended, to do what, for how long).

**Live Answer (Post-Pushback Graded):**
```text
A controlled framework set up by a competent authority which offers providers or prospective providers of AI systems the possibility to develop, train, validate and test, where appropriate in real-world conditions, an innovative AI system, pursuant to a sandbox plan for a limited time under regulatory supervision.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Controlled environment established by a national competent authority (or jointly with other Member States, or by the EDPS for Union bodies)
- **Criterion 2** [✓ PASS]: Intended for providers or prospective providers of AI systems
- **Criterion 3** [✓ PASS]: Purpose: fosters innovation and facilitates development, training, testing and validation of innovative AI systems (may include supervised real-world testing)
- **Criterion 4** [✓ PASS]: Time-limited, prior to market placement/putting into service, pursuant to a specific sandbox plan agreed with the competent authority

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [039/110] rg_039 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 600 chars  
**References Cited:** `Article 50.4`  
**Expected References:** `Article 50.4`  

> **Question:**  
> Under the EU AI Act, what transparency obligation applies to deployers when they use an AI system to generate or manipulate text for the purpose of informing the public on matters of public interest, and what are the two exceptions where this obligation does not apply?

**Live Answer (Post-Pushback Graded):**
```text
Under Article 50(4), a deployer that uses an AI system to generate or manipulate text published to inform the public on matters of public interest must disclose that the text has been artificially generated or manipulated. Under Article 50(4), that disclosure duty does not apply in two cases: first, where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences; and second, where the AI-generated content has undergone a process of human review or editorial control and a natural or legal person holds editorial responsibility for the publication of the content.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Deployers must disclose that the text has been artificially generated or manipulated
- **Criterion 2** [✓ PASS]: Exception 1: use authorised by law to detect, prevent, investigate or prosecute criminal offences
- **Criterion 3** [✓ PASS]: Exception 2: AI-generated content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for the publication

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [040/110] rg_040 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.3s | **Length:** 436 chars  
**References Cited:** `Annex VII.4`  
**Expected References:** `Article 44.1`  

> **Question:**  
> Under the EU AI Act, when a high-risk AI system is found to conform with the requirements, what information must the Union technical documentation assessment certificate contain?

**Live Answer (Post-Pushback Graded):**
```text
Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✗ FAIL]: Language: drawn up in a language easily understood by the relevant authorities of the Member State where the notified body is established
- **Criterion 2** [✗ FAIL]: Validity period stated: not exceeding five years (Annex I systems) or four years (Annex III systems)

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/2 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Language: drawn up in a language easily understood by the relevant authorities of the Member State where the notified body is established'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Validity period stated: not exceeding five years (Annex I systems) or four years (Annex III systems)'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [041/110] rg_041 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 362 chars  
**References Cited:** `Article 11.1, Annex IV.2`  
**Expected References:** `Article 17.4`  

> **Question:**  
> Under the EU AI Act, is there a simplified way for SMEs (including startups) to provide the technical documentation for high-risk AI systems, and who must accept it for conformity assessment?

**Live Answer (Post-Pushback Graded):**
```text
Yes. Under Article 11(1), SMEs, including start-ups, may provide the technical documentation elements set out in Annex IV in a simplified manner, using a simplified form the Commission is required to establish for the needs of small and micro enterprises. Where an SME opts to use that form, the notified body performing the conformity assessment must accept it.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: AI Office develops a simplified technical documentation form for SMEs/microenterprises, including start-ups, covering the Annex IV elements
- **Criterion 3** [✓ PASS]: The notified body assessing conformity of the high-risk AI system must accept that simplified form

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [042/110] rg_042 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 493 chars  
**References Cited:** `Article 26.7`  
**Expected References:** `Article 26.7`  

> **Question:**  
> Under the EU AI Act, must an employer inform affected workers and workers' representatives before putting into service or using a high-risk AI system in the workplace?
If so, should possibly specific rules or procedures be followed to provide this information?

**Live Answer (Post-Pushback Graded):**
```text
Yes. Under Article 26(7), a deployer that is an employer must, before putting a high-risk AI system into service or using it at the workplace, inform the workers' representatives and the affected workers that they will be subject to the use of that high-risk AI system. Under Article 26(7), that information must be provided, where applicable, in accordance with the rules and procedures laid down in Union and national law and practice on the information of workers and their representatives.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Timing: before putting into service or using the system at the workplace
- **Criterion 3** [✓ PASS]: Recipients: workers' representatives and affected workers
- **Criterion 4** [✓ PASS]: Procedure: follow applicable Union/national law and practice on informing workers, where applicable (no separate free-standing procedure)

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [043/110] rg_043 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.3s | **Length:** 722 chars  
**References Cited:** `Article 10.5`  
**Expected References:** `Article 10.5`  

> **Question:**  
> Under Article 10(5) of the EU AI Act, when may a provider of a high-risk AI system process special categories of personal data for bias detection and correction, and what key safeguards/conditions must be met?

**Live Answer (Post-Pushback Graded):**
```text
Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict, documented access controls to prevent misuse (c); no transmission or transfer to other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Only where strictly necessary for bias detection/correction under Art 10(2)(f)-(g), and cannot be effectively achieved with other data (incl. synthetic/anonymised)
- **Criterion 2** [✓ PASS]: Technical re-use limitations plus state-of-the-art security/privacy-preserving measures, including pseudonymisation
- **Criterion 3** [✓ PASS]: Strict, documented access controls limited to authorised persons under confidentiality obligations, with no transmission/transfer/access by other parties
- **Criterion 4** [✓ PASS]: Deletion once bias corrected or retention period ends, whichever is first
- **Criterion 5** [✓ PASS]: Processing records document necessity and why other data would not suffice
- **Criterion 6** [✗ FAIL]: Additional to, not a substitute for, obligations under GDPR, EUDPR and the Law Enforcement Directive

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/6 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Additional to, not a substitute for, obligations under GDPR, EUDPR and the Law Enforcement Directive'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [044/110] rg_044 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 19.4s | **Length:** 1384 chars  
**References Cited:** `Annex IX.2, Annex III.7.b, Article 60.4.c`  
**Expected References:** `Article 60.4`  

> **Question:**  
> Under the EU AI Act, what specific information must a provider/prospective provider submit (and keep up to date) regarding testing of a high-risk AI system in real-world conditions outside an AI regulatory sandbox?

**Live Answer (Post-Pushback Graded):**
```text
Five items must be registered and thereafter kept up to date under Annex IX, which sets the information to be submitted upon registration of testing in real world conditions of high-risk AI systems listed in Annex III: a Union-wide unique single identification number of the testing, the name and contact details of the provider or prospective provider and of the deployers involved, a brief description of the AI system, its intended purpose and other information necessary to identify it, a summary of the main characteristics of the plan for testing in real world conditions, and information on the suspension or termination of the testing. Article 60 makes that registration a condition of lawful testing outside an AI regulatory sandbox, alongside a real-world testing plan drawn up and submitted to, and approved by, the market surveillance authority of the Member State concerned. The registration route differs by system: providers of high-risk AI systems in points 1, 6 and 7 of Annex III in the areas of law enforcement, migration, asylum and border control management register in the secure non-public section of the EU database, and those in point 2 of Annex III register at national level. Article 60 also requires the provider or prospective provider to notify that market surveillance authority of any suspension or termination of the testing and of the final outcomes.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Real-world testing plan submitted to (and approved by) the market surveillance authority of the Member State of testing
- **Criterion 2** [✓ PASS]: Registration of the testing with a Union-wide unique single identification number
- **Criterion 3** [✓ PASS]: General rule: registration under Article 71(4) with information specified in Annex IX
- **Criterion 4** [✓ PASS]: Exceptions: Annex III points 1, 6, 7 (law enforcement/migration/asylum/border control) register in secure non-public EU database section per Article 49(4)(d); Annex III point 2 systems register per Article 49(5)

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 49'].
```

---

### [045/110] rg_045 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 22.9s | **Length:** 1170 chars  
**References Cited:** `Article 26.5, Article 79.2, Article 72.2, Article 73.6`  
**Expected References:** `Article 26.5`  

> **Question:**  
> Under the EU AI Act, if a deployer has reason to believe that the use of a high-risk AI system may present a risk, what must the deployer do, and whom must the deployer inform?

**Live Answer (Post-Pushback Graded):**
```text
Where a deployer has reason to consider that use of the high-risk AI system in accordance with the instructions for use may result in that system presenting a risk within the meaning of Article 79(1), Article 26(5) requires the deployer to inform the provider or distributor and the relevant market surveillance authority without undue delay, and to suspend the use of that system. That duty sits within the same paragraph's obligation to monitor the operation of the system on the basis of the instructions for use and, where relevant, to inform providers in accordance with the post-market monitoring arrangements of Article 72. Where the deployer has identified a serious incident, it must also immediately inform first the provider, and then the importer or distributor and the relevant market surveillance authorities, with Article 73 reporting applying mutatis mutandis if the provider cannot be reached. This reporting obligation does not cover sensitive operational data of deployers that are law enforcement authorities, and deployers must in any event cooperate with the competent authorities in any action taken in relation to the system under Article 26(12).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Inform the provider or distributor
- **Criterion 2** [✓ PASS]: Inform the relevant market surveillance authority
- **Criterion 3** [✓ PASS]: Suspend use of the system
- **Criterion 4** [✓ PASS]: All actions taken without undue delay

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 72'].
```

---

### [046/110] rg_046 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 38.2s | **Length:** 2329 chars  
**References Cited:** `Article 13.3, Article 26.1`  
**Expected References:** `Article 13.3`  

> **Question:**  
> Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information.

**Live Answer (Post-Pushback Graded):**
```text
Article 13 requires high-risk AI systems to be sufficiently transparent for deployers to interpret and appropriately use their output, and to be accompanied by instructions for use in an appropriate digital format or otherwise containing concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers. Under Article 13(3) those instructions must contain at least six categories: the identity and contact details of the provider and, where applicable, its authorised representative, the characteristics, capabilities and limitations of performance of the system, the changes to the system and its performance pre-determined by the provider at the moment of the initial conformity assessment, if any, the human oversight measures including the technical measures facilitating interpretation of outputs, the computational and hardware resources needed together with the expected lifetime and any necessary maintenance and care measures including their frequency and software updates, and, where relevant, a description of the mechanisms allowing deployers to properly collect, store and interpret the logs. The performance category under Article 13(3)(b) itself covers seven elements: the intended purpose, the level of accuracy including its metrics, robustness and cybersecurity against which the system has been tested and validated and any known and foreseeable circumstances affecting those expected levels, any known or foreseeable circumstance in intended use or reasonably foreseeable misuse that may lead to risks to health and safety or fundamental rights, where applicable the technical capabilities and characteristics for providing information relevant to explaining the output, when appropriate the performance regarding specific persons or groups on which the system is intended to be used, when appropriate specifications for the input data or other information on the training, validation and testing data sets used, and where applicable information enabling deployers to interpret the output and use it appropriately. This information also serves the deployer's own duties, since Article 26 requires deployers to use and monitor the system in accordance with the instructions for use and to assign human oversight to competent, trained and authorised natural persons.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Provider and, where applicable, authorised representative identity/contact details
- **Criterion 2** [✓ PASS]: Characteristics, capabilities and performance limitations (intended purpose, accuracy/robustness/cybersecurity levels, foreseeable risks, explainability capabilities, performance for specific groups, input data specifications)
- **Criterion 3** [✓ PASS]: Pre-determined changes to the system and its performance
- **Criterion 4** [✓ PASS]: Human oversight measures under Article 14
- **Criterion 5** [✓ PASS]: Computational/hardware resources needed, expected lifetime, and maintenance/care measures
- **Criterion 6** [✓ PASS]: Description of logging mechanisms under Article 12, where relevant

**Judge Remarks & Telemetry:**
```text
✓ All 6 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 12', 'Article 14'].
```

---

### [047/110] rg_047 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.4s | **Length:** 1367 chars  
**References Cited:** `Article 20.1, Article 16, Article 79.2`  
**Expected References:** `Article 20.1`  

> **Question:**  
> Under the EU AI Act, what actions must a provider take when it considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity with the Regulation?

**Live Answer (Post-Pushback Graded):**
```text
The provider must act immediately under Article 20, which imposes the corrective action and duty of information obligation. Under Article 20(1), a provider that considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity with the Regulation must immediately take the necessary corrective actions to bring that system into conformity, to withdraw it, to disable it, or to recall it, as appropriate, and must inform the distributors of the system concerned and, where applicable, the deployers, the authorised representative and importers. Where the system presents a risk within the meaning of Article 79(1), which governs AI systems presenting a risk to health, safety or fundamental rights, Article 20(2) requires the provider, on becoming aware of that risk, to investigate the causes immediately in collaboration with the reporting deployer where applicable, and to inform the market surveillance authorities competent for the system and, where applicable, the notified body that issued a certificate for it, in particular of the nature of the non-compliance and of any relevant corrective action taken. This duty is also restated in Article 16, which lists the provider's obligations and requires it to take the necessary corrective actions and provide information as required in Article 20.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Immediately take necessary corrective action: bring into conformity, withdraw, disable, or recall, as appropriate
- **Criterion 2** [✓ PASS]: Inform distributors of the system concerned
- **Criterion 3** [✓ PASS]: Where applicable, inform deployers, authorised representative and importers accordingly

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [048/110] rg_048 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 17.7s | **Length:** 844 chars  
**References Cited:** `Article 3.21, Article 43.3, Annex VI.3, Annex VII.4`  
**Expected References:** `Article 3.20, Article 3.21`  

> **Question:**  
> Under Regulation (EU) 2024/1689, what is the definition of (a) a "conformity assessment body" and (b) "conformity assessment"?

**Live Answer (Post-Pushback Graded):**
```text
Both terms are defined in Article 3, which sets out the definitions applying throughout the Regulation. A "conformity assessment body" means a body that performs third-party conformity assessment activities, including testing, certification and inspection, and such a body becomes a "notified body" once it is notified in accordance with the Regulation and other relevant Union harmonisation legislation. "Conformity assessment" means the process of demonstrating whether the requirements set out in Chapter III, Section 2 relating to a high-risk AI system have been fulfilled. That process is operationalised by Article 43, which requires providers of high-risk AI systems to follow either the internal control procedure in Annex VI or the quality management system and technical documentation procedure involving a notified body in Annex VII.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Conformity assessment body: a body that performs third-party conformity assessment activities
- **Criterion 2** [✓ PASS]: Conformity assessment body: activities include testing, certification and inspection
- **Criterion 3** [✓ PASS]: Conformity assessment: the process of demonstrating whether the Chapter III, Section 2 requirements for a high-risk AI system have been fulfilled

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex VI', 'Annex VII', 'Article 43'].
```

---

### [049/110] rg_049 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 15.0s | **Length:** 867 chars  
**References Cited:** `Article 95.1`  
**Expected References:** `Article 95.1, Article 95.2`  

> **Question:**  
> Under the EU AI Act (Regulation (EU) 2024/1689) Article 95, who may draw up codes of conduct, and which bodies must encourage and facilitate their drawing up?

**Live Answer (Post-Pushback Graded):**
```text
Codes of conduct may be drawn up by individual providers or deployers of AI systems, by organisations representing them, or by both, including with the involvement of any interested stakeholders and their representative organisations such as civil society organisations and academia, and a single code may cover one or more AI systems having a similar intended purpose (Article 95(3)). The bodies that must encourage and facilitate their drawing up are the AI Office and the Member States, in respect of codes fostering voluntary application to AI systems other than high-risk AI systems of some or all of the requirements set out in Chapter III, Section 2 (Article 95(1)). The AI Office and the Member States must also take into account the specific interests and needs of SMEs, including start-ups, when encouraging and facilitating that drawing up (Article 95(4)).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Codes of conduct may be drawn up by individual providers or deployers of AI systems, by organisations representing them, or both
- **Criterion 2** [✓ PASS]: May involve interested stakeholders and their representative organisations, including civil society and academia
- **Criterion 3** [✓ PASS]: The AI Office and the Member States must encourage and facilitate the drawing up of codes of conduct

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [050/110] rg_050 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 31.2s | **Length:** 1174 chars  
**References Cited:** `Annex III.5.b, Annex III.5, Article 6.3.d`  
**Expected References:** `Annex III.5.b`  

> **Question:**  
> Under the EU AI Act, which AI systems in the financial services area are classified as high-risk under Annex III(5)(b), and what explicit exceptions are listed?

**Live Answer (Post-Pushback Graded):**
```text
High-risk covers AI systems intended to be used to evaluate the creditworthiness of natural persons or to establish their credit score, with the single explicit exception of AI systems used for the purpose of detecting financial fraud, which Annex III point 5(b) carves out of that use-case. Annex III point 5 sits in the area of access to and enjoyment of essential private services and essential public services and benefits, and under the Annex III route in Article 6(2) a system is high-risk only where it falls within one of the lettered use-cases listed there. A creditworthiness or credit scoring system nonetheless escapes high-risk classification under the Article 6(3) derogation where it poses no significant risk of harm and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or performs a preparatory task, unless it profiles natural persons, in which case it remains high-risk. A provider relying on that derogation must document the assessment before the system is placed on the market or put into service.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: AI systems evaluating creditworthiness or establishing credit score of natural persons
- **Criterion 2** [✓ PASS]: Exception: AI systems used for detecting financial fraud

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [051/110] rg_051 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 29.0s | **Length:** 1527 chars  
**References Cited:** `Article 22.3`  
**Expected References:** `Article 22.1`  

> **Question:**  
> Under the EU AI Act, what must a provider established outside the EU do in order to place a high-risk AI system on the Union market?

**Live Answer (Post-Pushback Graded):**
```text
A provider established in a third country must, prior to making the high-risk AI system available on the Union market, appoint by written mandate an authorised representative established in the Union, and must enable that representative to perform the tasks specified in the mandate (Article 22). The mandate must empower the authorised representative to verify that the EU declaration of conformity and the technical documentation have been drawn up and that the appropriate conformity assessment procedure has been carried out, to keep the provider's contact details, the declaration, the technical documentation and any notified body certificate at the disposal of competent authorities for 10 years after the system is placed on the market or put into service, to supply information and documentation on reasoned request including access to the automatically generated logs under the provider's control, to cooperate with competent authorities in action taken on the system, and to comply with or verify the registration obligations (Article 22). The authorised representative may be addressed by competent authorities in addition to or instead of the provider on all compliance issues, and must terminate the mandate and immediately inform the relevant market surveillance authority, and where applicable the notified body, if it considers the provider to be acting contrary to the Regulation (Article 22). Appointing a representative does not displace the provider's own substantive duties, which remain fully applicable.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Appoint an authorised representative established in the Union, by written mandate
- **Criterion 2** [✓ PASS]: Must occur prior to making the system available on the Union market
- **Criterion 3** [✓ PASS]: Representative empowered per Article 22(3) tasks (verify conformity documentation, retain records 10 years, provide information/log access to authorities, cooperate with authorities, handle registration)

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 49'].
```

---

### [052/110] rg_052 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 24.2s | **Length:** 1884 chars  
**References Cited:** `Article 17.1, Article 63.1, Article 9.10, Article 72.4, Article 73.6`  
**Expected References:** `Article 17.1`  

> **Question:**  
> Under the EU AI Act, what minimum elements must a provider's quality management system (QMS) for high-risk AI systems include? List the required elements.

**Live Answer (Post-Pushback Graded):**
```text
Article 17(1) requires providers of high-risk AI systems to put in place a quality management system ensuring compliance with the Regulation, documented in a systematic and orderly manner in written policies, procedures and instructions. It must include at least thirteen elements: a strategy for regulatory compliance including conformity assessment and management of modifications, design, design control and design verification techniques, development, quality control and quality assurance techniques, examination, test and validation procedures and their frequency, technical specifications and standards to be applied, data management systems and procedures, the risk management system of Article 9, the setting-up and maintenance of a post-market monitoring system under Article 72, procedures for reporting a serious incident under Article 73, handling of communication with national competent authorities, notified bodies, other operators and interested parties, record-keeping systems for all relevant documentation, resource management including security of supply, and an accountability framework allocating responsibilities of management and staff. Implementation is proportionate to the size of the provider's organisation, without lowering the degree of rigour and level of protection required, and providers already subject to quality management obligations under sectoral Union law may embed these aspects within that system, while financial institutions subject to internal governance requirements under Union financial services law are deemed to comply except as regards the risk management system, post-market monitoring and serious incident reporting elements. Microenterprises without partner or linked enterprises may comply with certain elements in a simplified manner under Article 63, which does not exempt them from the other requirements of the Regulation.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Regulatory compliance strategy incl. conformity assessment and modification management
- **Criterion 2** [✓ PASS]: Design, development, quality control and verification techniques/procedures
- **Criterion 3** [✓ PASS]: Examination, test and validation procedures and their frequency
- **Criterion 4** [✓ PASS]: Data management procedures across data lifecycle
- **Criterion 5** [✓ PASS]: Article 9 risk management system and Article 72 post-market monitoring system
- **Criterion 6** [✓ PASS]: Record-keeping and accountability framework for management/staff

**Judge Remarks & Telemetry:**
```text
✓ All 6 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [053/110] rg_053 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 33.6s | **Length:** 1768 chars  
**References Cited:** `Article 53.1, Article 55.1, Annex XI.2, Annex XII.2, Article 51.1`  
**Expected References:** `Article 55.1`  

> **Question:**  
> Under the EU AI Act, what additional obligations apply to providers of a general-purpose AI model that is classified as a model with systemic risk?

**Live Answer (Post-Pushback Graded):**
```text
Four additional obligations apply under Article 55, on top of the Article 53 duties owed by every general-purpose AI model provider (Annex XI technical documentation, Annex XII information for downstream providers, a copyright policy, and a public training-data summary): performing model evaluation under standardised protocols and tools reflecting the state of the art, including documented adversarial testing; assessing and mitigating possible systemic risks at Union level, including their sources, stemming from the development, placing on the market or use of the model; keeping track of, documenting and reporting without undue delay to the AI Office and, as appropriate, national competent authorities relevant information about serious incidents and possible corrective measures; and ensuring an adequate level of cybersecurity protection for the model and its physical infrastructure. Classification triggers a further duty under Article 52 to notify the Commission without delay and in any event within two weeks of meeting, or knowing it will meet, the Article 51 high-impact-capabilities condition presumed at cumulative training compute above 10^25 floating-point operations, with the option to submit substantiated arguments that the model nonetheless presents no systemic risk. The Article 53(2) exemption for models released under a free and open-source licence does not apply to general-purpose AI models with systemic risk, so the technical documentation and downstream information duties remain owed in full. Compliance may be demonstrated through Article 56 codes of practice until a harmonised standard is published, and any information obtained under Article 55, including trade secrets, is covered by the Article 78 confidentiality obligation.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Perform state-of-the-art model evaluation including documented adversarial testing to identify/mitigate systemic risks
- **Criterion 2** [✓ PASS]: Assess and mitigate possible Union-level systemic risks, including their sources
- **Criterion 3** [✓ PASS]: Track, document and report serious incidents and corrective measures to the AI Office/national competent authorities without undue delay
- **Criterion 4** [✓ PASS]: Ensure adequate cybersecurity protection for the model and its physical infrastructure

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [054/110] rg_054 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 18.3s | **Length:** 840 chars  
**References Cited:** `Article 79.6, Article 79.5, Article 5, Article 50`  
**Expected References:** `Article 79.6`  

> **Question:**  
> Under the EU AI Act, what are the four grounds on which non-compliance with the Act may be alleged (as listed in Article 79(6))?

**Live Answer (Post-Pushback Graded):**
```text
Article 79(6) requires the notifying market surveillance authority to indicate whether the alleged non-compliance is due to one or more of four grounds: non-compliance with the prohibition of the AI practices referred to in Article 5, a failure of a high-risk AI system to meet the requirements set out in Chapter III, Section 2, shortcomings in the harmonised standards or common specifications referred to in Articles 40 and 41 that confer a presumption of conformity, and non-compliance with Article 50. These grounds form part of the notification of provisional measures under Article 79(5), which must also identify the non-compliant AI system, its origin and supply chain, the nature of the non-compliance and the risk involved, the nature and duration of the national measures, and the arguments put forward by the relevant operator.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Non-compliance with prohibition of AI practices under Article 5
- **Criterion 2** [✓ PASS]: Failure of high-risk AI system to meet Chapter III, Section 2 requirements
- **Criterion 3** [✓ PASS]: Shortcomings in harmonised standards/common specifications under Articles 40-41
- **Criterion 4** [✓ PASS]: Non-compliance with Article 50

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [055/110] rg_055 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.7s | **Length:** 1785 chars  
**References Cited:** `Article 5.1.h, Annex II, Annex III.1.a, Article 6.3.d`  
**Expected References:** `Article 5.1.h`  

> **Question:**  
> Under the EU AI Act, in which specific situations may law enforcement use 'real-time' remote biometric identification in publicly accessible spaces for law-enforcement purposes (i.e., the exceptions to the prohibition)? List the permitted objectives.

**Live Answer (Post-Pushback Graded):**
```text
Permitted only in three exhaustive situations, all subject to the requirement that the use be strictly necessary for the objective. Article 5(1)(h), which prohibits the use of real-time remote biometric identification systems in publicly accessible spaces for the purposes of law enforcement, allows it for the targeted search for specific victims of abduction, trafficking in human beings or sexual exploitation of human beings and the search for missing persons, the prevention of a specific, substantial and imminent threat to the life or physical safety of natural persons or of a genuine and present or genuine and foreseeable threat of a terrorist attack, and the localisation or identification of a person suspected of having committed a criminal offence for the purpose of a criminal investigation, prosecution or execution of a criminal penalty, limited to the offences listed in Annex II, namely terrorism, trafficking in human beings, sexual exploitation of children, illicit trafficking in narcotic drugs, weapons and nuclear material, murder, kidnapping, rape, armed robbery, organised crime, participation in a criminal organisation and environmental crime, and punishable in the Member State concerned by a custodial sentence or detention order of at least four years. Outside that law enforcement context in publicly accessible spaces the practice is not prohibited but classified high-risk, since Annex III point 1(a) lists remote biometric identification systems as a high-risk use case under Article 6(2), excluding biometric verification whose sole purpose is confirming that a person is who they claim to be. Article 5(1)(h) is without prejudice to Article 9 of Regulation (EU) 2016/679 for the processing of biometric data for purposes other than law enforcement.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Targeted search for victims of abduction, trafficking, sexual exploitation, or missing persons
- **Criterion 2** [✓ PASS]: Prevention of specific, substantial and imminent threat to life/physical safety, or genuine terrorist attack threat
- **Criterion 3** [✓ PASS]: Localisation/identification of a suspect for investigation, prosecution, or executing a penalty for an Annex II offence punishable by at least 4 years custodial sentence/detention order

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex III', 'Article 6'].
```

---

### [056/110] rg_056 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 20.2s | **Length:** 1109 chars  
**References Cited:** `Article 32, Article 31`  
**Expected References:** `Article 32`  

> **Question:**  
> Under Article 32 of Regulation (EU) 2024/1689, when is a conformity assessment body presumed to comply with the requirements in Article 31?

**Live Answer (Post-Pushback Graded):**
```text
A conformity assessment body is presumed to comply with Article 31 where it demonstrates its conformity with the criteria laid down in the relevant harmonised standards, or parts thereof, the references of which have been published in the Official Journal of the European Union (Article 32). That presumption extends only in so far as the applicable harmonised standards cover those requirements, so any Article 31 requirement not covered by such a standard must still be demonstrated directly. Article 31 sets the substantive requirements concerned, including establishment under the national law of a Member State with legal personality, independence from the provider and from operators with an economic interest, no direct involvement in the design, development, marketing or use of the high-risk AI systems assessed, documented procedures safeguarding impartiality and confidentiality, appropriate liability insurance unless liability is assumed by the Member State, and permanent availability of sufficient personnel with experience relating to the relevant types of AI systems, data and data computing.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Body demonstrates conformity with relevant harmonised standards (or parts thereof)
- **Criterion 2** [✓ PASS]: Condition: references to those standards published in the Official Journal of the European Union
- **Criterion 3** [✓ PASS]: Presumption limited to the extent those standards cover the Article 31 requirements

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [057/110] rg_057 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 26.9s | **Length:** 765 chars  
**References Cited:** `Article 85, Article 100.1`  
**Expected References:** `Article 85.1`  

> **Question:**  
> Who is entitled to lodge a complaint about an infringement, and to which authority must the complaint be submitted?

**Live Answer (Post-Pushback Graded):**
```text
Any natural or legal person having grounds to consider that there has been an infringement of the Regulation may submit a complaint, and Article 85 requires it to be addressed to the relevant market surveillance authority, which must take it into account in its market surveillance activities and handle it under the dedicated procedures established in accordance with Regulation (EU) 2019/1020. The right does not depend on the complainant's own rights being affected, and it applies without prejudice to other administrative or judicial remedies. Where the alleged infringement concerns a Union institution, body, office or agency, the European Data Protection Supervisor is the authority empowered under Article 100 to impose administrative fines on that entity.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Any natural or legal person
- **Criterion 2** [✓ PASS]: Grounds to consider there has been an infringement of the Regulation
- **Criterion 3** [✓ PASS]: Submitted to the relevant market surveillance authority

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 100', 'Article 79', 'Article 85'].
```

---

### [058/110] rg_058 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 30.0s | **Length:** 1320 chars  
**References Cited:** `Article 50.2, Article 3.1`  
**Expected References:** `Article 50.2`  

> **Question:**  
> Under the EU AI Act, what must providers of AI systems that generate or manipulate synthetic content do to enable identification of AI-generated/manipulated output, and what quality criteria must that solution meet?

**Live Answer (Post-Pushback Graded):**
```text
Providers of AI systems, including general-purpose AI systems, that generate synthetic audio, image, video or text content must ensure the outputs are marked in a machine-readable format and detectable as artificially generated or manipulated (Article 50(2)). That technical solution must be effective, interoperable, robust and reliable as far as is technically feasible, taking into account the specificities and limitations of the various types of content, the costs of implementation and the generally acknowledged state of the art, as may be reflected in relevant technical standards. The marking duty does not apply to the extent the AI system performs an assistive function for standard editing or does not substantially alter the input data provided by the deployer or the semantics thereof, or where it is authorised by law to detect, prevent, investigate or prosecute criminal offences. The separate duty to disclose deep fakes, meaning AI-generated or manipulated image, audio or video content resembling existing persons, objects, places, entities or events that would falsely appear authentic (Article 3), falls on the deployer under Article 50(4), and any information given under Article 50 must be clear, distinguishable, accessible and provided at the latest at the time of first interaction or exposure.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Marking must be machine-readable format
- **Criterion 2** [✓ PASS]: Marking must be detectable as artificially generated or manipulated
- **Criterion 3** [✓ PASS]: Solution must be effective, interoperable, robust and reliable, as far as technically feasible
- **Criterion 4** [✓ PASS]: Feasibility judged against content-type specificities/limitations, implementation costs, and state of the art
- **Criterion 5** [✓ PASS]: Exemptions: assistive editing, no substantial alteration of input data/semantics, or law-enforcement authorisation

**Judge Remarks & Telemetry:**
```text
✓ All 5 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 3'].
```

---

### [059/110] rg_059 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 32.8s | **Length:** 1489 chars  
**References Cited:** `Article 98.2, Article 68.4, Article 90.1`  
**Expected References:** `Article 68`  

> **Question:**  
> Under the EU AI Act, what is the scientific panel of independent experts, what are its main support/advisory tasks, and what key characteristics/selection requirements apply to its members?

**Live Answer (Post-Pushback Graded):**
```text
The scientific panel is a body of independent experts that the Commission establishes by implementing act, adopted under the examination procedure of Article 98(2), to support the enforcement activities under the Regulation, with that implementing act also setting the conditions, procedures and detailed arrangements for the panel and its members to issue alerts and to request the assistance of the AI Office. Its support and advisory tasks under Article 68(3)(a) are alerting the AI Office of possible systemic risks at Union level of general-purpose AI models in accordance with the qualified alert mechanism of Article 90, contributing to the development of tools and methodologies for evaluating capabilities of general-purpose AI models and systems including through benchmarks, providing advice on the classification of general-purpose AI models with systemic risk, providing advice on the classification of various general-purpose AI models and systems, and contributing to the development of tools and templates. Members must perform their tasks with impartiality and objectivity, must ensure the confidentiality of information and data obtained in carrying out their tasks and activities, and must neither seek nor take instructions from anyone when exercising those tasks. Each expert must draw up a declaration of interests that is made publicly available, and the AI Office must establish systems and procedures to actively manage and prevent potential conflicts of interest.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Established by Commission via implementing act (Article 98(2) examination procedure) to support enforcement, not a decision-making body itself
- **Criterion 2** [✗ FAIL]: Tasks: advise/support AI Office on general-purpose AI models (alerting systemic risks under Article 90, developing evaluation tools/benchmarks, advising on classification); plus support market surveillance authorities, cross-border surveillance (Article 74(11)), and Union safeguard procedure (Article 81)
- **Criterion 3** [✗ FAIL]: Selection: experts chosen by Commission for up-to-date scientific/technical AI expertise, independence from any AI provider, and ability to act diligently, accurately and objectively
- **Criterion 4** [✓ PASS]: Members must act impartially, confidentially and free of instructions, each publishing a declaration of interests

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Tasks: advise/support AI Office on general-purpose AI models (alerting systemic risks under Article 90, developing evaluation tools/benchmarks, advising on classification); plus support market surveillance authorities, cross-border surveillance (Article 74(11)), and Union safeguard procedure (Article 81)'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Selection: experts chosen by Commission for up-to-date scientific/technical AI expertise, independence from any AI provider, and ability to act diligently, accurately and objectively'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [060/110] rg_060 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 25.6s | **Length:** 871 chars  
**References Cited:** `Article 60.4.c, Article 73.6`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> Under the EU AI Act, if a provider identifies a serious incident during testing in real-world conditions of a high-risk AI system, what three actions must the provider take?

**Live Answer (Post-Pushback Graded):**
```text
Three actions are required under Article 60(7), which governs testing of high-risk AI systems in real world conditions outside AI regulatory sandboxes. The provider or prospective provider must report the serious incident to the national market surveillance authority in accordance with Article 73, which requires providers to report serious incidents to the market surveillance authorities of the Member State where the incident occurred and, following that report, to carry out without delay the necessary investigations, including a risk assessment of the incident and corrective action. It must adopt immediate mitigation measures or, failing that, suspend the testing in real world conditions until such mitigation takes place, or otherwise terminate it. It must also establish a procedure for the prompt recall of the AI system upon such termination of the testing.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Perform (without delay) the necessary investigation into the incident and the AI system, including a risk assessment
- **Criterion 2** [✓ PASS]: Take corrective action
- **Criterion 3** [✗ FAIL]: Cooperate with competent authorities (and notified body where relevant), and not alter the AI system in a way affecting evaluation of the incident's causes without first informing the competent authorities

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Cooperate with competent authorities (and notified body where relevant), and not alter the AI system in a way affecting evaluation of the incident's causes without first informing the competent authorities'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [061/110] rg_061 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.6s | **Length:** 1399 chars  
**References Cited:** `Article 88.1, Article 68.3, Article 64.2, Article 89.1`  
**Expected References:** `Article 88.1, Article 75.1`  

> **Question:**  
> Under the EU AI Act, which body has exclusive powers to supervise and enforce the obligations for providers of general-purpose AI models (Chapter V), and which entity is entrusted with implementing those tasks?

**Live Answer (Post-Pushback Graded):**
```text
The Commission holds exclusive powers to supervise and enforce the Chapter V obligations of providers of general-purpose AI models, taking into account the procedural guarantees of the Regulation, and it entrusts the implementation of those tasks to the AI Office, without prejudice to the Commission's powers of organisation and the division of competences between the Member States and the Union under the Treaties (Article 88). The AI Office is established within the Commission to develop Union expertise and capabilities in the field of AI, with Member States facilitating the tasks entrusted to it (Article 64), and it may take the necessary actions to monitor effective compliance by providers of general-purpose AI models, including adherence to approved codes of practice, and receives duly reasoned complaints from downstream providers alleging infringement (Article 89). Market surveillance authorities may request the Commission to exercise these enforcement powers where necessary and proportionate to assist with their own tasks under the Regulation (Article 88). A scientific panel of independent experts advises and supports the AI Office, in particular by alerting it to possible systemic risks at Union level, contributing to tools and methodologies for evaluating model capabilities, and advising on the classification of general-purpose AI models with systemic risk (Article 68).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: European Commission has exclusive powers to supervise and enforce Chapter V
- **Criterion 2** [✓ PASS]: AI Office is entrusted with implementing these tasks

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 68', 'Article 89', 'Article 94'].
```

---

### [062/110] rg_062 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.5s | **Length:** 1099 chars  
**References Cited:** `Article 24.4, Article 79.1`  
**Expected References:** `Article 24.4`  

> **Question:**  
> What must a distributor do if it considers a high-risk AI system is not in conformity with the Act's requirements? Additionally, what extra steps are required if the system presents a risk within the meaning of Article 79(1)?

**Live Answer (Post-Pushback Graded):**
```text
A distributor that considers, or has reason to consider, on the basis of the information in its possession, that a high-risk AI system is not in conformity with the requirements set out in Section 2 must not make that system available on the market until it has been brought into conformity, under Article 24(2) on distributor obligations. Where the system additionally presents a risk within the meaning of Article 79(1), the distributor must inform the provider or the importer, as applicable, to that effect. If the system has already been made available on the market, Article 24(4) requires the distributor to take the corrective actions necessary to bring it into conformity, to withdraw it or recall it, or to ensure that the provider, the importer or any relevant operator takes those actions. In that situation, where the system presents a risk within the meaning of Article 79(1), the distributor must immediately inform the provider or importer and the authorities competent for the system concerned, giving details in particular of the non-compliance and of any corrective actions taken.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Not make it available on market until brought into conformity
- **Criterion 2** [✓ PASS]: If risk under Art 79(1): immediately inform provider or importer and the competent authorities
- **Criterion 3** [✓ PASS]: Notification must detail the non-compliance and any corrective actions taken

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [063/110] rg_063 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 14.8s | **Length:** 738 chars  
**References Cited:** `Article 2.1`  
**Expected References:** `Article 2.1`  

> **Question:**  
> Under Article 2(1) of Regulation (EU) 2024/1689 (EU AI Act), which categories of actors/persons does the Act apply to? List the categories.

**Live Answer (Post-Pushback Graded):**
```text
Article 2(1) lists seven categories of actors. The Regulation applies to providers placing AI systems on the market or putting them into service or placing general-purpose AI models on the market in the Union irrespective of establishment, deployers of AI systems established or located within the Union, providers and deployers established or located in a third country where the output produced by the AI system is used in the Union, importers and distributors of AI systems, product manufacturers placing on the market or putting into service an AI system together with their product and under their own name or trademark, authorised representatives of providers not established in the Union, and affected persons located in the Union.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Providers placing on the market/putting into service AI systems or placing on the market GPAI models in the Union
- **Criterion 2** [✓ PASS]: Deployers of AI systems established/located in the Union
- **Criterion 3** [✓ PASS]: Providers and deployers in third countries where the AI system's output is used in the Union
- **Criterion 4** [✓ PASS]: Importers, distributors, and product manufacturers (placing an AI system on the market/into service with their product under their own name/trademark)
- **Criterion 5** [✓ PASS]: Authorised representatives of providers not established in the Union
- **Criterion 6** [✓ PASS]: Affected persons located in the Union

**Judge Remarks & Telemetry:**
```text
✓ All 6 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [064/110] rg_064 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.4s | **Length:** 1529 chars  
**References Cited:** `Article 60.4.e, Annex III.7.b, Annex IX.2`  
**Expected References:** `Article 60.4.e`  

> **Question:**  
> Under the EU AI Act, what conditions must be met before data collected and processed for testing high-risk AI systems in real-world conditions can be transferred to a third country (outside the EU)?

**Live Answer (Post-Pushback Graded):**
```text
Only where appropriate and applicable safeguards under Union law are implemented: Article 60, which permits providers or prospective providers to test high-risk AI systems listed in Annex III in real world conditions outside AI regulatory sandboxes, allows data collected and processed for the purpose of that testing to be transferred to third countries solely on that condition. That safeguard requirement operates alongside the other cumulative conditions in the same provision, so the transfer is lawful only while the testing itself remains compliant, including approval of the real-world testing plan by the market surveillance authority of the Member State where the testing takes place, registration of the testing with a Union-wide unique single identification number, and establishment of the provider or prospective provider in the Union or appointment of a legal representative established in the Union. Where the testing is registered in the EU database, Annex IX fixes the information to be submitted, namely the unique identification number, the name and contact details of the provider or prospective provider and of the deployers involved, a brief description of the AI system and its intended purpose, a summary of the main characteristics of the testing plan, and information on suspension or termination. Subjects of the testing may withdraw their informed consent at any time and request immediate and permanent deletion of their personal data, which constrains any onward retention or transfer of that data.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Appropriate and applicable safeguards under Union law must be implemented for the transfer

**Judge Remarks & Telemetry:**
```text
✓ All 1 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex III'].
```

---

### [065/110] rg_065 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 29.2s | **Length:** 1616 chars  
**References Cited:** `Article 99.5, Article 5.6, Article 16, Article 22.3, Article 50.2`  
**Expected References:** `Article 99`  

> **Question:**  
> What are the three maximum administrative fine tiers for (a) prohibited AI practices, (b) non-compliance with obligations for high-risk AI systems and general-purpose AI (GPAI) models, and (c) supplying incorrect/incomplete/misleading information? For each tier, give the maximum amount in EUR and the alternative maximum as a percentage of worldwide annual turnover.

**Live Answer (Post-Pushback Graded):**
```text
Non-compliance with the Article 5 prohibited practices carries the highest ceiling, up to EUR 35 000 000 or 7 % of total worldwide annual turnover for the preceding financial year, whichever is higher, under Article 99(3). The middle tier is up to EUR 15 000 000 or 3 % of total worldwide annual turnover, whichever is higher, applying under Article 99(4) to the closed list of operator and notified body duties covering provider obligations under Article 16, authorised representative obligations under Article 22, importer obligations under Article 23, distributor obligations under Article 24, deployer obligations under Article 26, notified body requirements under Articles 31, 33(1), (3) and (4) and 34, and the transparency obligations under Article 50, and mirrored for general-purpose AI model providers by Article 101, under which the Commission may fine a provider up to EUR 15 000 000 or 3 % of annual total worldwide turnover, whichever is higher, for infringing the relevant provisions, for failing to comply with an information request or supplying incorrect, incomplete or misleading information, for failing to comply with a requested measure, or for refusing model access for evaluation. The lowest tier is up to EUR 7 500 000 or 1 % of total worldwide annual turnover, whichever is higher, under Article 99(5) for supplying incorrect, incomplete or misleading information to notified bodies or national competent authorities in reply to a request. For SMEs, including start-ups, Article 99(6) inverts the comparison so that each of those ceilings is the lower of the percentage or the fixed amount.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Prohibited AI practices (Article 5): up to EUR 35,000,000 or 7% of total worldwide annual turnover, whichever higher
- **Criterion 2** [✓ PASS]: High-risk/GPAI obligations (Articles 16, 22, 23, 24, 26, 31, 33(1)(3)(4), 34, 50): up to EUR 15,000,000 or 3% of total worldwide annual turnover, whichever higher
- **Criterion 3** [✓ PASS]: Incorrect/incomplete/misleading information to notified bodies or national competent authorities: up to EUR 7,500,000 or 1% of total worldwide annual turnover, whichever higher

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [066/110] rg_066 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.2s | **Length:** 1739 chars  
**References Cited:** `Article 71.5, Article 49.4, Article 60.4.c, Article 6.2, Annex III.7.b`  
**Expected References:** `Article 71, Annex VIII`  

> **Question:**  
> Under the EU AI Act, what is the EU database for high-risk AI systems, what categories of information must it contain, and who is the controller of that database?

**Live Answer (Post-Pushback Graded):**
```text
The EU database is a single Union-level registry that the Commission sets up and maintains in collaboration with the Member States under Article 71, covering high-risk AI systems registered under Article 49, systems classified as not high-risk under the Article 6(3) derogation, and real-world testing registered under Article 60, with the data held in a publicly accessible part and, for the Annex III areas of biometrics, law enforcement, migration, asylum and border control management, in a secure non-public section to which only the Commission and the national authorities designated under Article 74(8) have access. Its content is the information listed in Sections A and B of Annex VIII, entered by the provider or, where applicable, the authorised representative, covering provider identification and contact details, system identification, intended purpose and status, plus the Annex IX information for testing in real world conditions, and it holds personal data only so far as necessary, namely the names and contact details of the natural persons responsible for registering the system who have legal authority to represent the provider or the deployer. Registration in the database is a precondition under Article 49 for placing an Annex III high-risk AI system on the market or putting it into service, and failure to register is formal non-compliance under Article 83, which the market surveillance authority must require to be rectified and, if it persists, escalate to restriction, recall or withdrawal. As to control, the Commission is the controller of the EU database, and the Act attributes to it responsibility for the database and for providing adequate technical and administrative support to the entering parties.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: EU database (set up/maintained by Commission with Member States) covers high-risk AI systems under Art 6(2) registered per Arts 49 and 60, and non-high-risk Art 6(3) systems registered per Art 6(4) and 49
- **Criterion 2** [✗ FAIL]: Categories: Annex VIII Sections A and B entered by provider/authorised representative; Section C entered by deployer that is/acts on behalf of a public authority, agency or body
- **Criterion 3** [✓ PASS]: Controller: the Commission

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Categories: Annex VIII Sections A and B entered by provider/authorised representative; Section C entered by deployer that is/acts on behalf of a public authority, agency or body'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex III', 'Annex VIII'].
```

---

### [067/110] rg_067 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 46.1s | **Length:** 1190 chars  
**References Cited:** `Article 51.1, Annex XIII, Article 52.4`  
**Expected References:** `Article 51.1, Annex XIII`  

> **Question:**  
> What are the conditions to classify general-purpose AI (GPAI) model as "GPAI model with systemic risk"? Do all need to be met at the same time?

**Live Answer (Post-Pushback Graded):**
```text
No, the two conditions are alternatives rather than cumulative. Article 51(1) classifies a general-purpose AI model as a general-purpose AI model with systemic risk if it meets any of the following conditions: it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks, or, based on a decision of the Commission taken ex officio or following a qualified alert from the scientific panel, it has capabilities or an impact equivalent to those, having regard to the criteria set out in Annex XIII. Under Article 51(2) high impact capabilities are presumed where the cumulative amount of computation used for training, measured in floating-point operations, is greater than 10^25, and Article 51(3) empowers the Commission to amend those thresholds and supplement the benchmarks and indicators by delegated act. Where the model meets the Article 51(1)(a) condition the provider must notify the Commission within two weeks under Article 52(1), and may present sufficiently substantiated arguments under Article 52(2) that the model exceptionally does not present systemic risks due to its specific characteristics.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Condition (a): high impact capabilities per Article 51(1)(a), presumed when training compute exceeds 10^25 FLOPs
- **Criterion 2** [✓ PASS]: Condition (b): Commission decision (ex officio or following qualified alert from scientific panel) that capabilities/impact are equivalent, per Annex XIII criteria
- **Criterion 3** [✓ PASS]: No, not cumulative - either condition alone suffices

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 52', 'Article 53', 'Article 55'].
```

---

### [068/110] rg_068 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.9s | **Length:** 1064 chars  
**References Cited:** `Article 13.3, Article 42.1, Article 10.3`  
**Expected References:** `Article 10.3`  

> **Question:**  
> For a high-risk AI system, who is responsible for ensuring that input data is relevant and sufficiently representative for the system's intended purpose, and under what condition does that responsibility apply?

**Live Answer (Post-Pushback Graded):**
```text
The provider bears this responsibility, and it applies only where the high-risk AI system is developed using techniques involving the training of AI models with data. Article 10 requires that training, validation and testing data sets be subject to data governance and management practices appropriate for the intended purpose, and Article 10(3) requires those data sets to be relevant, sufficiently representative, and to the best extent possible free of errors and complete in view of the intended purpose. Under Article 42(1), high-risk AI systems trained and tested on data reflecting the specific geographical, behavioural, contextual or functional setting in which they are intended to be used are presumed to comply with the relevant data governance requirements. The provider must also communicate this downstream, since Article 13 requires the instructions for use to state, when appropriate, specifications for the input data and other relevant information on the training, validation and testing data sets used, taking into account the intended purpose.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Provider of the high-risk AI system
- **Criterion 2** [✓ PASS]: Applies whenever the system is developed using techniques involving training AI models with data (Art. 10(1))
- **Criterion 3** [✗ FAIL]: For systems not using such training techniques, applies only to testing data sets (Art. 10(6))

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'For systems not using such training techniques, applies only to testing data sets (Art. 10(6))'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 13', 'Article 26', 'Article 42', 'Article 6'].
```

---

### [069/110] rg_069 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 43.9s | **Length:** 1242 chars  
**References Cited:** `Article 24.2, Article 79.2, Article 23.2`  
**Expected References:** `Article 24.3, Article 23.4`  

> **Question:**  
> I am a distributor of an AI systems. Do I have obligation not to jeopardize its conformity? I was not told if the system is high-risk or not. What if am I am importer instead?

**Live Answer (Post-Pushback Graded):**
```text
Yes. Article 24(3) requires distributors to ensure that, while a high-risk AI system is under their responsibility, storage or transport conditions do not jeopardise the system's compliance with the requirements of Section 2, and Article 24(1) requires them to verify, before making it available on the market, that it bears the required CE marking and is accompanied by a copy of the EU declaration of conformity and the instructions for use. These duties attach only where the system is high-risk, so that classification must be established first, and under Article 24(2) a distributor that considers or has reason to consider the system non-conforming must not make it available until it has been brought into conformity, and must inform the provider or the importer where the system presents a risk within the meaning of Article 79(1). An importer bears a corresponding duty under Article 23, which requires importers to verify before placing a high-risk AI system on the market that the conformity assessment, technical documentation, CE marking and accompanying documents are in order, and to ensure that storage and transport conditions under their responsibility do not jeopardise the system's compliance with those same requirements.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes, obligation applies regardless of high-risk knowledge
- **Criterion 2** [✓ PASS]: Distributor: storage/transport must not jeopardise Section 2 compliance (Article 24(3))
- **Criterion 3** [✓ PASS]: Importer: same obligation applies (Article 23(4))

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [070/110] rg_070 — Cross-Framework & Sectoral MedTech Integration (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.7s | **Length:** 931 chars  
**References Cited:** `Article 6.2, Annex I.11`  
**Expected References:** `Article 6.1`  

> **Question:**  
> Under the EU AI Act, is an AI system that is a safety component of a medical device classified as MDR Class I (non-sterile, non-measuring, non-reusable surgical) automatically a high-risk AI system? Explain your reasoning.

**Live Answer (Post-Pushback Graded):**
```text
Not automatically high-risk. Article 6(1) makes a safety component high-risk only where both conditions hold, namely that the AI system is a safety component of a product covered by the Union harmonisation legislation listed in Annex I, which includes Regulation (EU) 2017/745 on medical devices, and that the product is required to undergo a third-party conformity assessment for its placing on the market under that legislation. A Class I device that is non-sterile, has no measuring function and is not a reusable surgical instrument is self-assessed by the manufacturer without notified body involvement, so the second condition is not met and the Annex I route does not apply. The system would still be high-risk if the intended purpose falls within a use case listed in Annex III under Article 6(2), and any reclassification of the device into a higher class requiring a notified body would bring it back within Article 6(1).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Article 6(1)(a) and (b) are cumulative conditions
- **Criterion 3** [✓ PASS]: MDR Class I (non-sterile, non-measuring, non-reusable surgical) devices undergo manufacturer self-assessment, not third-party conformity assessment
- **Criterion 4** [✓ PASS]: Condition (b) fails, so Article 6(1) does not apply

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [071/110] rg_071 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 34.2s | **Length:** 1422 chars  
**References Cited:** `Article 50.4, Article 79`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> Under Regulation (EU) 2024/1689 (EU AI Act), can the same AI system be subject both to the Act's "high-risk AI system" obligations and to the transparency obligations sometimes described informally as "limited risk"? Explain briefly.

**Live Answer (Post-Pushback Graded):**
```text
Yes, the same AI system can carry both sets of duties, because they are cumulative rather than alternative. Article 50(6) expressly provides that the transparency obligations in Article 50(1) to (4) do not affect the requirements and obligations set out in Chapter III, so classification as high-risk does not displace them, and they operate without prejudice to other transparency obligations under Union or national law. The Article 50 duties attach to the functional characteristics of the system and to the actor concerned, namely a provider whose system interacts directly with natural persons (Article 50(1)) or generates synthetic audio, image, video or text content that must be marked in a machine-readable and detectable format (Article 50(2)), and a deployer operating an emotion recognition or biometric categorisation system who must inform the persons exposed (Article 50(3)) or generating deep fake content who must disclose that it is artificially generated or manipulated (Article 50(4)), subject in each case to the stated derogations such as law-enforcement authorisation. The informal label "limited risk" describes no separate tier that excludes high-risk status, and Article 79(6) confirms the overlap by treating a failure to meet the Chapter III, Section 2 requirements and non-compliance with Article 50 as distinct grounds on which market surveillance authorities may act against the same system.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Article 50(6): Article 50(1)-(4) transparency duties do not affect Chapter III high-risk obligations
- **Criterion 3** [✓ PASS]: Obligations are cumulative, not mutually exclusive

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex III', 'Article 13', 'Article 26', 'Article 6', 'Article 79'].
```

---

### [072/110] rg_072 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 17.1s | **Length:** 994 chars  
**References Cited:** `Article 6.2`  
**Expected References:** `Article 6.1, Annex I.a.2`  

> **Question:**  
> Under the EU AI Act, can an AI system intended to be used as a toy qualify as a high-risk AI system, and if so under what conditions?

**Live Answer (Post-Pushback Graded):**
```text
An AI system intended to be used as a toy is high-risk only where it is a safety component of, or is itself, a toy covered by Directive 2009/48/EC on the safety of toys, which is listed in and that toy is required to undergo a third-party conformity assessment before being placed on the market or put into service, both conditions being cumulative under Article 6(1). Where the toy manufacturer may instead self-assess conformity under the toy safety legislation, the second condition of Article 6(1) is not met and the AI system is not high-risk on that route, unless it independently falls within an Annex III use case under Article 6(2). This classification applies irrespective of whether the AI system is placed on the market or put into service independently of the toy. Where it is high-risk, the provider follows the conformity assessment procedure required under Directive 2009/48/EC pursuant to Article 43, with the Chapter III Section 2 requirements forming part of that assessment.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Condition: AI system is a toy or safety component of a toy covered by Directive 2009/48/EC (Annex I harmonisation legislation)
- **Criterion 3** [✓ PASS]: Condition: that toy is required to undergo third-party conformity assessment under the Directive
- **Criterion 4** [✓ PASS]: Both conditions cumulative (Article 6(1))

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex I'].
```

---

### [073/110] rg_073 — Cross-Framework & Sectoral MedTech Integration (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 20.0s | **Length:** 959 chars  
**References Cited:** `Article 6.2, Annex I.4`  
**Expected References:** `Article 6.1, Annex I`  

> **Question:**  
> Under the EU AI Act, can an AI system intended to be used as a safety component in a lift qualify as a high-risk AI system, and under what conditions?

**Live Answer (Post-Pushback Graded):**
```text
An AI system intended to be used as a safety component of a lift is high-risk where both conditions in Article 6(1) are met: it is a safety component of a product covered by the Union harmonisation legislation listed in Annex I, which includes, at point 4, Directive 2014/33/EU on lifts and safety components for lifts, and that lift or safety component is required to undergo a third-party conformity assessment with a view to its placing on the market or putting into service under that Directive. This classification applies irrespective of whether the AI system is placed on the market or put into service independently of the lift. Where it is high-risk on this basis, the provider follows, under Article 43, the conformity assessment procedure required by Directive 2014/33/EU itself, with the requirements of Chapter III, Section 2 forming part of that assessment, and a new conformity assessment is required in the event of a substantial modification.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Condition: AI system intended as safety component of a product covered by Annex I Union harmonisation legislation
- **Criterion 3** [✓ PASS]: Condition: that product (or the AI system itself as a product) required to undergo third-party conformity assessment under that legislation
- **Criterion 4** [✓ PASS]: Both conditions cumulative

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [074/110] rg_074 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 8.3s | **Length:** 321 chars  
**References Cited:** `Article 5.1.f, Article 50.3, Annex III.1.c`  
**Expected References:** `Annex III.1.c, Article 5.1.f`  

> **Question:**  
> Under the EU AI Act (Regulation (EU) 2024/1689), are AI systems intended for emotion recognition from biometric data always prohibited? If not, in which contexts are they prohibited, what exception applies, and how are they classified when not prohibited?

**Live Answer (Post-Pushback Graded):**
```text
Emotion recognition is not categorically prohibited under the AI Act; the prohibition in Article 5 only applies in workplaces and educational institutions, with a narrow medical/safety exception. Elsewhere the system is high-risk under Annex III.1(c) and triggers Article 50(3) transparency duties toward exposed persons.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Prohibited context: inferring emotions of natural persons in workplace and education institutions (Article 5(1)(f))
- **Criterion 3** [✓ PASS]: Exception: use intended for medical or safety reasons
- **Criterion 4** [✓ PASS]: When not prohibited, classified as high-risk under Annex III (emotion recognition/biometrics category)

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [075/110] rg_075 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 38.8s | **Length:** 1402 chars  
**References Cited:** `Article 50.4, Article 50.2`  
**Expected References:** `Article 50.4`  

> **Question:**  
> I generated audio with AI for my artistic work (sole purpose). Do I need to provide some marking of its artificial nature? I feel that would compromise the enjoyment of the work.

**Live Answer (Post-Pushback Graded):**
```text
Yes, some marking is required, but the artistic character of the work shapes only part of it. Where the audio constitutes a deep fake, the deployer duty in Article 50(4) to disclose that the content has been artificially generated or manipulated is limited, for content forming part of an evidently artistic, creative, satirical, fictional or analogous work, to disclosure of the existence of such generated or manipulated content in an appropriate manner that does not hamper the display or enjoyment of the work, so a credit, programme note or accompanying metadata suffices rather than an intrusive on-work label. The separate provider duty in Article 50(2) is not relaxed by artistic purpose: providers of AI systems generating synthetic audio must ensure the outputs are marked in a machine-readable format and detectable as artificially generated or manipulated, by solutions that are effective, interoperable, robust and reliable as far as technically feasible, and this applies unless the system performs an assistive function for standard editing or does not substantially alter the input data or its semantics, or the use is authorised by law for criminal-offence purposes. Under Article 50(5) that information must reach the natural persons concerned in a clear and distinguishable manner at the latest at the time of first exposure and must conform to applicable accessibility requirements.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes, disclosure still required
- **Criterion 2** [✓ PASS]: No need for marking that hampers enjoyment
- **Criterion 3** [✓ PASS]: Must disclose existence of AI-generated content in appropriate/unobtrusive manner

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [076/110] rg_076 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 0.4s | **Length:** 90 chars  
**References Cited:** `Article 3.2, Article 108, Article 110, Annex I`  
**Expected References:** `Article 3.2`  

> **Question:**  
> Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?

**Live Answer (Post-Pushback Graded):**
```text
The combination of the probability of an occurrence of harm and the severity of that harm.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Combination of probability of occurrence of harm and severity of that harm

**Judge Remarks & Telemetry:**
```text
✓ All 1 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [077/110] rg_077 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.1s | **Length:** 909 chars  
**References Cited:** `Annex III.7.b, Article 6.2, Article 49.1, Article 71.1, Annex VIII.12`  
**Expected References:** `Article 49.2`  

> **Question:**  
> For AI systems that fit within the use cases listed in Annex III but are considered non-high-risk by the provider, do they need to be registered in the EU database?

**Live Answer (Post-Pushback Graded):**
```text
Yes, registration is still required. Article 6(3) allows a provider to conclude that an Annex III system is not high-risk where it poses no significant risk of harm and performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns without replacing the human assessment, or performs a preparatory task, unless it profiles natural persons, and Article 6(4) requires that assessment to be documented before the system is placed on the market and expressly makes the provider subject to the registration obligation in Article 49(2). Under Article 49(2), the provider or, where applicable, the authorised representative must register itself and that system in the EU database referred to in Article 71 before placing it on the market or putting it into service, with the Article 6(3) non-high-risk information entered in Section B of Annex VIII.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Registration required under Article 49(2)
- **Criterion 3** [✓ PASS]: Registered in EU database referred to in Article 71

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [078/110] rg_078 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.6s | **Length:** 1465 chars  
**References Cited:** `Article 61.1, Article 60.4.c`  
**Expected References:** `Article 61.1`  

> **Question:**  
> Do I need informed consent to test a high-risk AI system in real-world conditions outside a regulatory sandbox?

**Live Answer (Post-Pushback Graded):**
```text
Yes. Testing high-risk AI systems in real world conditions outside AI regulatory sandboxes under Article 60 requires freely-given informed consent from the subjects of testing, obtained prior to their participation and after they have been duly informed in concise, clear, relevant and understandable terms about the nature and objectives of the testing and possible inconvenience, the conditions and expected duration of participation, their rights including the right to refuse and to withdraw at any time without detriment or justification, the arrangements for requesting reversal or disregarding of the system's predictions, recommendations or decisions, and the Union-wide unique single identification number of the testing together with the contact details of the provider or its legal representative (Article 61(1)). That consent must be dated and documented, and a copy given to the subject of testing or their legal representative (Article 61(2)). Subjects may withdraw at any time by revoking their informed consent and may request immediate and permanent deletion of their personal data, without this affecting activities already carried out (Article 60(5)). Consent does not stand alone: the provider or prospective provider must also draw up a real-world testing plan, submit it to and obtain approval from the market surveillance authority in the Member State concerned, and register the testing as required, before testing may begin (Article 60(4)).
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Consent must be freely given and informed, obtained prior to participation, covering nature/objectives/inconveniences, conditions and duration, rights to refuse/withdraw without detriment or justification, reversal/disregard arrangements, and the unique ID plus provider contact details
- **Criterion 3** [✓ PASS]: Consent must be dated, documented, and a copy given to the subject or their legal representative

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [079/110] rg_079 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 19.2s | **Length:** 1369 chars  
**References Cited:** `Article 79.1, Article 79.2, Article 20.2`  
**Expected References:** `Article 20.2`  

> **Question:**  
> A provider becomes aware of a risk (within the meaning of Article 79(1)) for their high-risk AI system. Does the provider need to take immediate corrective action OR immediately investigate the causes OR both? For example, perhaps it's the market surveillance authority that must investigate the cause, and the provider can help later.

**Live Answer (Post-Pushback Graded):**
```text
Both, and the duties run in parallel rather than sequentially. Under Article 20(1), a provider that considers or has reason to consider that a high-risk AI system placed on the market or put into service is not in conformity must immediately take the necessary corrective actions to bring it into conformity, withdraw it, disable it, or recall it, and must inform the distributors and, where applicable, the deployers, the authorised representative and importers. Under Article 20(2), where the system presents a risk within the meaning of Article 79(1), meaning a risk to health, safety or fundamental rights, and the provider becomes aware of that risk, it must immediately investigate the causes in collaboration with the reporting deployer where applicable, and inform the competent market surveillance authorities and, where applicable, the notified body that issued the certificate, of the nature of the non-compliance and of any corrective action taken. The market surveillance authority's own evaluation under Article 79(2) is a separate enforcement track that can require corrective action within a prescribed period, and it does not displace or postpone the provider's immediate obligations, since the operator must in any event cooperate with the authority and ensure appropriate corrective action for all affected systems made available on the Union market.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Both
- **Criterion 2** [✓ PASS]: Immediate corrective action required under Article 20(1) where system is non-compliant
- **Criterion 3** [✓ PASS]: Immediate investigation of causes is the provider's own duty under Article 20(2)
- **Criterion 4** [✓ PASS]: Investigation done in collaboration with reporting deployer where applicable, not deferred to market surveillance authority

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [080/110] rg_080 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 34.2s | **Length:** 1205 chars  
**References Cited:** `Article 50.4`  
**Expected References:** `Article 50.4`  

> **Question:**  
> What is Article 50(4) about?

**Live Answer (Post-Pushback Graded):**
```text
Article 50(4) imposes the deepfake disclosure duty on deployers: anyone deploying an AI system that generates or manipulates image, audio or video content constituting a deep fake must disclose that the content has been artificially generated or manipulated, unless the use is authorised by law to detect, prevent, investigate or prosecute criminal offences. Where the content forms part of an evidently artistic, creative, satirical, fictional or analogous work or programme, the duty is limited to disclosing the existence of such generated or manipulated content in an appropriate manner that does not hamper the display or enjoyment of the work. The same paragraph adds a separate duty for deployers of an AI system that generates or manipulates text published to inform the public on matters of public interest, who must disclose that the text was artificially generated or manipulated. That text duty alone falls away where the use is authorised by law for criminal law purposes or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for its publication, and this editorial exemption does not excuse the deepfake disclosure.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Deployers of AI systems generating/manipulating image, audio or video constituting a deep fake must disclose the content is artificially generated or manipulated
- **Criterion 2** [✓ PASS]: Exception where use is authorised by law to detect/prevent/investigate/prosecute criminal offences
- **Criterion 3** [✓ PASS]: For evidently artistic/creative/satirical/fictional/analogous works, obligation limited to disclosing existence of such content without hampering enjoyment/display
- **Criterion 4** [✓ PASS]: Separate rule: deployers of AI systems generating/manipulating text published to inform the public on matters of public interest must disclose artificial generation, with exceptions for law-enforcement authorisation or human review/editorial responsibility

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [081/110] rg_081 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 19.5s | **Length:** 1125 chars  
**References Cited:** `Article 6.2, Article 50.2, Annex III, Annex I, Article 5.1.d`  
**Expected References:** `Article 6`  

> **Question:**  
> Is an AI system high-risk if it is used in a product that: is not listed in Annex I; use case not listed in Annex III; internally uses general purpose AI model with systemic risk due to high impact capabilities?

**Live Answer (Post-Pushback Graded):**
```text
Not high-risk. Under Article 6, an AI system is high-risk only on two routes: where it is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I, or where it serves one of the Annex III use cases spanning biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration, and justice; neither route is met here, and the system does not fall within the prohibited practices of Article 5. The fact that the system internally relies on a general-purpose AI model classified as presenting systemic risk on account of high impact capabilities does not alter the classification of the AI system, since the systemic-risk qualification attaches to the model and its provider, not to the downstream AI system. The system therefore remains outside the high-risk tier, subject only to the Article 50 transparency obligations where it interacts directly with natural persons or generates synthetic audio, image, video or text content that must be marked in a machine-readable format and detectable as artificially generated or manipulated.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Article 6(1) not met: not an Annex I product/safety component requiring third-party conformity assessment
- **Criterion 3** [✓ PASS]: Article 6(2) not met: use case not listed in Annex III
- **Criterion 4** [✓ PASS]: Internal use of a general-purpose AI model with systemic risk is not an Article 6 criterion

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 5'].
```

---

### [082/110] rg_082 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 23.0s | **Length:** 1157 chars  
**References Cited:** `Article 24.4, Article 79.2`  
**Expected References:** `Article 24.1`  

> **Question:**  
> My local small language model says that, as a distributor of high-risk AI systems, I must be careful that transport conditions do not jeopardize compliance. But AI is just software, isn't it? So I am pretty sure my model hallucinated. What do you say?

**Live Answer (Post-Pushback Graded):**
```text
The model did not hallucinate. Article 24(3) expressly requires distributors to ensure that, while a high-risk AI system is under their responsibility, storage or transport conditions, where applicable, do not jeopardise the system's compliance with the requirements of Section 2, and the words "where applicable" accommodate the fact that some high-risk AI systems are supplied as or within physical products, on hardware or on storage media whose integrity can be affected by handling, temperature, humidity or tampering. Where a distributor considers, or has reason to consider, on the basis of the information in its possession, that a system it has already made available on the market no longer conforms to those requirements, Article 24(4) requires it to take the necessary corrective actions to bring the system into conformity, to withdraw or recall it, or to ensure the provider, importer or other relevant operator does so, and where the system presents a risk within the meaning of Article 79(1) to inform the provider or importer and the competent authorities immediately, with details of the non-compliance and of any corrective actions taken.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No, not hallucinated
- **Criterion 2** [✓ PASS]: Article 24(3) applies
- **Criterion 3** [✓ PASS]: Duty applies only 'where applicable' (e.g., embedded/supplied hardware or physical media)

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 79'].
```

---

### [083/110] rg_083 — Easy Mode (Direct Statutory Lookup) (EASY)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 23.5s | **Length:** 1433 chars  
**References Cited:** `Annex III, Annex I.5, Article 6.2, Article 71.1, Article 49.3`  
**Expected References:** `Article 6.2`  

> **Question:**  
> Given an AI system that is high-risk according to Annex III: if it is repurposed to a use case not in Annex III (nor Annex I), then:
- the repurposed AI system is still high-risk due to reversibility of training into the original system
- the repurposed AI system is no longer high-risk but it must be reported in the EU database
- the repurposed AI system is no longer high-risk and there is no need to report it in the EU database

**Live Answer (Post-Pushback Graded):**
```text
No longer high-risk, and no entry in the EU database is required. Classification under Article 6(2) turns on the intended purpose falling within one of the lettered use cases under the eight Annex III areas, so a system whose intended purpose lies outside Annex III and which is not a safety component of, or itself, a product covered by the Annex I Union harmonisation legislation subject to third-party conformity assessment under Article 6(1), is outside the high-risk tier; reversibility of training or the system's earlier classification is not a criterion. The EU database maintained by the Commission under Article 71 covers only high-risk AI systems referred to in Article 6(2) registered in accordance with Articles 49 and 60, together with systems not considered high-risk pursuant to the Article 6(3) derogation and registered under Article 6(4) and Article 49, and a system falling entirely outside Annex III belongs to neither group. Note that the Article 6(3) derogation, which excludes an Annex III system posing no significant risk of harm because it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns without replacing human assessment, or performs a preparatory task, and which never applies where the system performs profiling of natural persons, is the only route that does carry a registration duty despite the non-high-risk outcome.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No longer high-risk (third option)
- **Criterion 2** [✓ PASS]: High-risk status attaches to intended purpose/use case under Article 6(2)/Annex III, not to the system or its training as such
- **Criterion 3** [✓ PASS]: New use case outside Annex III and Annex I means neither limb of Article 6 is satisfied
- **Criterion 4** [✓ PASS]: No registration/EU database obligation (Article 49/Article 71) since system is not high-risk

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [084/110] rg_084 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 32.4s | **Length:** 1331 chars  
**References Cited:** `Article 6.2, Annex I.19, Annex III.5`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> We have a phone system where the caller can press 1 if they consent to the call being recorded, 2 if they do not. We wish to replace this with an NLP system that understands a voice reply like "Yes", "Sure", "Please no", etc. Would such a system be considered high-risk? It's for our clinic.

**Live Answer (Post-Pushback Graded):**
```text
Not high-risk. Recognising a spoken affirmative or negative reply to a recording-consent prompt falls outside both routes of Article 6: the system is neither a product nor a safety component of a product covered by the Union harmonisation legislation listed in Annex I and subject to third-party conformity assessment, and it is not one of the lettered use cases under the eight areas of Annex III, whose essential private and public services area reaches only matters such as evaluating eligibility for essential public assistance benefits and services including healthcare services, and the evaluation and classification of emergency calls, dispatch priority, and emergency healthcare patient triage. Even on the most expansive reading of the clinic setting, the Article 6(3) derogation would remove the system from the high-risk tier, because interpreting a yes or no answer is a narrow procedural task that poses no significant risk of harm to health, safety or fundamental rights and does not materially influence the outcome of decision making, provided the system performs no profiling of natural persons, which would always make it high-risk. The system therefore sits in the minimal risk tier under the Regulation, and consent to recording remains governed by data protection law rather than by the high-risk requirements.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✗ FAIL]: Not biometric categorisation or emotion recognition under Annex III(1)(b)-(c), since the system parses semantic content (yes/no), not emotional or protected-attribute inference
- **Criterion 3** [✓ PASS]: Not essential healthcare services under Annex III(5)(a), since consent capture for call recording is not an eligibility evaluation for benefits/services

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Not biometric categorisation or emotion recognition under Annex III(1)(b)-(c), since the system parses semantic content (yes/no), not emotional or protected-attribute inference'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 25'].
```

---

### [085/110] rg_085 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 45.1s | **Length:** 1735 chars  
**References Cited:** `Article 5.1.h, Article 6.2, Article 50.1, Annex I.2, Annex II`  
**Expected References:** `Article 6.1, Article 6.2, Annex III.1.a`  

> **Question:**  
> Does the AI Act prohibit or classifies as high-risk the use of AI in drones? Can I use AI in a drone to find who's around in town? And what if it's just a toy drone? And what about toy drones used for other applications?

**Live Answer (Post-Pushback Graded):**
```text
Drones are neither prohibited nor high-risk as such, classification follows the AI function, not the airframe. Using AI in a drone to identify who is present around a town is a prohibited practice under Article 5(1)(h) where it constitutes real-time remote biometric identification in publicly accessible spaces for law enforcement purposes, which is permitted only for the targeted search for specific victims of abduction, trafficking in human beings or sexual exploitation and the search for missing persons, the prevention of a specific, substantial and imminent threat to the life or physical safety of natural persons or of a terrorist attack, and the localisation or identification of a person suspected of an Annex II offence punishable by at least four years' custodial sentence; outside law enforcement use that prohibition does not bite, and Article 5 also bans, among the other listed practices, biometric categorisation deducing race, political opinions, trade union membership, religious or philosophical beliefs, sex life or sexual orientation, and criminal-offence risk assessment based solely on profiling or personality traits. That prohibition attaches to the practice regardless of whether the carrier is a toy drone. For toy drones in other applications, the AI is high-risk under Article 6(1) only where it is a safety component of, or is itself, a product covered by Directive 2009/48/EC on the safety of toys as listed in Annex I and that product is required to undergo a third-party conformity assessment; failing that, the use is minimal risk, subject only to the Article 50 obligation on providers to ensure that persons interacting directly with the AI system are informed of that fact unless it is obvious.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No blanket prohibition/high-risk classification for drones as such — turns on AI system's intended use under Article 6
- **Criterion 2** [✗ FAIL]: Drone AI identifying people in public = remote biometric identification, high-risk under Annex III(1)(a), not the 1:1 verification exclusion
- **Criterion 3** [✓ PASS]: Toy status irrelevant — classification depends on intended use, not the device
- **Criterion 4** [✓ PASS]: Toy drone used for other application is high-risk only if that use matches Annex III (or Article 6(1) safety-component/conformity-assessment criteria)

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Drone AI identifying people in public = remote biometric identification, high-risk under Annex III(1)(a), not the 1:1 verification exclusion'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex II', 'Annex III'].
```

---

### [086/110] rg_086 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.6s | **Length:** 1642 chars  
**References Cited:** `Article 1.2, Article 53.1, Article 112.6, Annex XI.2, Article 55.1`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> Does the EU AI Act establish a "proportionality of need" requirement according to which very powerful but environmentally impactful models (e.g. LLMs) should not be used for simple tasks (e.g. sentiment recognition) when a simpler and performant model is available (e.g. BERT)? If yes, cite which Article or Annex mentions this.

**Live Answer (Post-Pushback Graded):**
```text
No. No Article or Annex of the EU AI Act imposes a "proportionality of need" duty to select a smaller or less energy-intensive model for a simpler task, and model choice as such is not regulated: environmental protection appears only as a protected interest in the statement of purpose in Article 1(1), which frames the Regulation's harmonised rules, prohibitions, high-risk requirements, transparency rules and general-purpose AI model rules, not as an operative obligation on providers or deployers. The closest the Regulation comes is Article 112(6), under which the Commission must report by 2 August 2028 and every four years thereafter on progress in developing standardisation deliverables on the energy-efficient development of general-purpose AI models and assess the need for further measures, including binding ones, which confirms that no binding energy-efficiency or model-right-sizing requirement exists yet. For general-purpose AI models the only related duties are documentary, namely the Article 53(1) obligations to draw up and keep up to date technical documentation of the model including its training and testing process and evaluation results per Annex XI, to make integration information available to downstream providers per Annex XII, to put in place a copyright policy, and to publish a sufficiently detailed summary of the training content. Where the model meets the Article 51 systemic-risk threshold, the additional Article 55 obligations on evaluation, systemic-risk mitigation, serious-incident reporting and cybersecurity apply, but none of these turns on whether a lighter model could have performed the task.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: No provision conditions use of a capable model on unavailability of a simpler/less resource-intensive alternative for the same task
- **Criterion 3** [✓ PASS]: Obligations are risk- and capability-based (e.g. Article 6, Annex III, Article 51), not tied to model right-sizing or environmental impact

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex XI', 'Article 53', 'Article 55'].
```

---

### [087/110] rg_087 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 41.4s | **Length:** 2158 chars  
**References Cited:** `Article 9.2, Article 5.1.d, Article 51.1, Annex XIII, Article 55.1`  
**Expected References:** `Article 9`  

> **Question:**  
> Article 9 of the AI Act lists the five categories of harm that map to AI systems with: no risk, limited risk, high-risk, systemic risk, prohibited. What are the five categories and how do they map to the five risk levels?

**Live Answer (Post-Pushback Graded):**
```text
No such mapping exists in Article 9. Article 9 does not enumerate categories of harm or risk levels at all: it requires a risk management system to be established, implemented, documented and maintained for high-risk AI systems, covering identification and analysis of known and reasonably foreseeable risks, estimation of risks arising in intended use and under reasonably foreseeable misuse, testing against pre-defined metrics, and residual risks judged acceptable and communicated to the deployer, and the interests it protects are three rather than five, namely health, safety and fundamental rights. The tiers referred to are established by separate provisions: Article 5 prohibits eight practices, being subliminal, manipulative or deceptive techniques causing significant harm, exploitation of vulnerabilities due to age, disability or a specific social or economic situation, social scoring by any public or private provider or deployer, criminal-risk profiling based solely on personality traits, untargeted scraping of facial images for facial recognition databases, emotion recognition in workplaces and education institutions, biometric categorisation by sensitive attributes, and real-time remote biometric identification in publicly accessible spaces for law enforcement, subject in the last case to the three exhaustive objectives in Article 5(1)(h) with prior judicial or administrative authorisation. Systemic risk is not a system-level tier but a classification of general-purpose AI models under Article 51, arising from high-impact capabilities, presumed where cumulative training compute exceeds 10^25 floating point operations, or by Commission decision on the Annex XIII criteria of parameters, data, compute, modalities, benchmarks and reach, and it triggers the Article 55 duties of model evaluation including adversarial testing, systemic risk assessment and mitigation, serious incident reporting, and cybersecurity protection for the model and its physical infrastructure. The Act attaches no obligations to systems described as carrying no risk, and the transparency duties often labelled limited risk are not part of Article 9.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Article 9 only establishes the risk management system for high-risk AI systems, not a five-tier harm classification
- **Criterion 3** [✗ FAIL]: Four steps: identify/analyze risks (9(2)(a)); estimate/evaluate risks under intended use and foreseeable misuse (9(2)(b)); evaluate risks from post-market monitoring data (9(2)(c)); adopt targeted risk management measures (9(2)(d))
- **Criterion 4** [✓ PASS]: The prohibited/high-risk/limited-risk/minimal-risk/systemic-risk tiering comes from elsewhere in the Regulation (e.g. Articles 5, 6, 50, 51), not Article 9

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Four steps: identify/analyze risks (9(2)(a)); estimate/evaluate risks under intended use and foreseeable misuse (9(2)(b)); evaluate risks from post-market monitoring data (9(2)(c)); adopt targeted risk management measures (9(2)(d))'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 55'].
```

---

### [088/110] rg_088 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 30.7s | **Length:** 1417 chars  
**References Cited:** `Article 13.3, Annex I.19, Article 25.2, Article 26.6`  
**Expected References:** `Article 26.1, Article 26.6`  

> **Question:**  
> We deployed a high-risk AI system in our company. We have a use in mind that is outside the intended use and our legal team say such a use is definitely no risk (no Annex I nor III apply). Can we just go ahead with the new use and do we need to keep logs for it?

**Live Answer (Post-Pushback Graded):**
```text
No. Deployers of a high-risk AI system must use it in accordance with the instructions for use, which under Article 13 must state the intended purpose and the known or foreseeable circumstances, including reasonably foreseeable misuse, that may lead to risks to health, safety or fundamental rights, so a use outside the intended purpose is not made permissible by an internal conclusion that the new use is itself low-risk. Under Article 25(1), a deployer that modifies the intended purpose of a high-risk AI system already placed on the market is considered a provider of that system and assumes the full provider obligations, with Article 25(2) requiring the initial provider to make available the information, technical access and assistance needed to meet them, in particular for the conformity assessment. Logging remains mandatory: Article 26(6) requires the deployer to keep the logs automatically generated by the high-risk AI system, to the extent those logs are under its control, for a period appropriate to the intended purpose of the system and in any event at least six months, unless applicable Union or national law, in particular Union data protection law, provides otherwise. Deployers that are financial institutions subject to internal governance requirements under Union financial services law satisfy that retention duty by maintaining the logs as part of the documentation kept under that law.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No, cannot proceed with the new use
- **Criterion 2** [✓ PASS]: Article 26(1) requires use in accordance with instructions for use; deviating from intended use is not excused merely because that use alone wouldn't trigger Annex III
- **Criterion 3** [✓ PASS]: Yes, logging duty under Article 26(6) still applies regardless of the particular use

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex III'].
```

---

### [089/110] rg_089 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 20.8s | **Length:** 1646 chars  
**References Cited:** `Annex III.5.d, Article 5.1.d, Article 6.2, Annex I.5, Article 50.1`  
**Expected References:** `Article 6.3.a`  

> **Question:**  
> Is an AI that transcribes doctor-patient conversations prohibited? Or is it high-risk as per the use cases of Annex III of the AI Act?

**Live Answer (Post-Pushback Graded):**
```text
An AI system that transcribes doctor, patient conversations is neither prohibited nor, in itself, a listed high-risk use case: it does not fall within any of the practices prohibited by Article 5, and Annex III's healthcare-related entries in point 5 cover evaluating eligibility for essential public assistance benefits and services including healthcare, risk assessment and pricing in life and health insurance, and the evaluation and classification of emergency calls or dispatching and priority-setting of emergency first response services including emergency healthcare patient triage, not the documentation of a clinical consultation. It is high-risk only where it qualifies under the Annex I route in Article 6(1), that is where the transcription system is itself a product or a safety component of a product covered by the Union harmonisation legislation listed in Annex I (notably the medical devices legislation) and that product is subject to third-party conformity assessment. Where it neither meets that condition nor performs an Annex III function, it remains outside Chapter III, though Article 50 transparency obligations apply where the system is intended to interact directly with natural persons, requiring the provider to ensure the persons concerned are informed they are interacting with an AI system unless that is obvious to a reasonably well-informed, observant and circumspect person in the circumstances and context of use. Classification must be assessed against the intended purpose declared by the provider, since a system that goes beyond transcription to generate clinical assessments may engage the Annex I route.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No, not a prohibited practice under Article 5
- **Criterion 2** [✓ PASS]: No, not high-risk under Annex III
- **Criterion 3** [✗ FAIL]: Reason: narrow procedural task derogation, Article 6(3), point (a)

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Reason: narrow procedural task derogation, Article 6(3), point (a)'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [090/110] rg_090 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 34.5s | **Length:** 1109 chars  
**References Cited:** `Article 51.3, Article 25.1, Article 3.4`  
**Expected References:** `Article 26.6`  

> **Question:**  
> As a deployer, do I need to keep logs if I use a powerful LLM (surpassing the FLOPs threshold) for estimating whether customer payment confirmations are received via email?

**Live Answer (Post-Pushback Graded):**
```text
No. Exceeding the compute threshold has no bearing on deployer duties: cumulative training compute above 10^25 floating point operations only triggers the presumption in Article 51(2) that a general-purpose AI model has high impact capabilities and is therefore classified as a general-purpose AI model with systemic risk, and the obligations flowing from that classification bind the provider of the model, not an entity using an AI system under its authority, which is a deployer within the meaning of Article 3(4). Record-keeping and the retention of automatically generated logs attach to high-risk AI systems, and estimating whether customer payment confirmations have been received by email is a narrow administrative task that does not fall within a high-risk use. The analysis changes only if the deployer becomes a provider under Article 25(1), that is by putting its name or trademark on the system, making a substantial modification to it, or modifying the intended purpose so that the system becomes high-risk, in which case the provider obligations, including record-keeping, would apply in full.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Article 26(6) logging duty applies only to deployers of high-risk AI systems
- **Criterion 3** [✓ PASS]: This use case is not a high-risk use case listed in Annex III
- **Criterion 4** [✓ PASS]: FLOPs threshold concerns GPAI systemic-risk classification under Article 51, a separate regime irrelevant to Annex III high-risk classification

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [091/110] rg_091 — Cross-Framework & Sectoral MedTech Integration (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 31.7s | **Length:** 1619 chars  
**References Cited:** `Article 6.2, Annex III.5.d, Annex I.12, Article 5.1.d`  
**Expected References:** `Article 6.1`  

> **Question:**  
> Is AI software that helps clinicians take medical decisions around best treatment potentially high-risk? According to what Article and/or Annex?

**Live Answer (Post-Pushback Graded):**
```text
AI software that assists clinicians in determining best treatment is high-risk under the Article 6(1) route where it constitutes a medical device, or a safety component of a product, covered by the medical devices legislation listed in Regulation (EU) 2017/745 (MDR) or Regulation (EU) 2017/746 (IVDR), and is required under that legislation to undergo third-party conformity assessment, which is typically the case for clinical decision support classified above Class I. Where that condition is met, the classification follows automatically from the product's regulatory status, and the Article 6(3) carve-outs for a narrow procedural task, improving a previously completed human activity, detecting decision-making patterns, or a preparatory task are unavailable, since those apply only to systems captured by Annex III. Annex III does not independently cover clinical treatment recommendations: its healthcare-related entries in point 5 concern evaluating eligibility of natural persons for essential public assistance benefits and services including healthcare services by or on behalf of public authorities, risk assessment and pricing in life and health insurance, and emergency healthcare patient triage systems and the dispatching of emergency first response services. The system is not among the practices exhaustively prohibited by Article 5, and where the Annex I condition is satisfied, the conformity assessment runs through the notified body route of the MDR or IVDR, resulting in a single CE marking, with the ISO 14971 and ISO 13485 processes serving as the practical basis for demonstrating compliance.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✗ FAIL]: Article 6(2)
- **Criterion 3** [✗ FAIL]: Annex III (healthcare access/provision)

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Article 6(2)'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Annex III (healthcare access/provision)'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 5'].
```

---

### [092/110] rg_092 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 39.7s | **Length:** 2275 chars  
**References Cited:** `Annex I, Annex II, Annex III, Article 6, Article 5`  
**Expected References:** `Annex I, Annex II, Annex III`  

> **Question:**  
> Do Annex I, Annex II, and Annex III all have to deal with high-risk AI classifications? If not, which doesn't/do not, and what is/are it/they about?

**Live Answer (Post-Pushback Graded):**
```text
No, Annex II does not deal with high-risk classification, whereas Annex I and Annex III both do. Annex I lists the Union harmonisation legislation (Section A covering machinery, toys, radio equipment, medical devices, lifts and similar products, Section B covering civil aviation, motor vehicles, marine equipment, rail and agricultural vehicles), and under Article 6(1) an AI system that is itself such a product, or a safety component of one, is high-risk where that product must undergo a third-party conformity assessment. Annex III sets out the eight high-risk areas whose listed lettered use cases make a system high-risk under Article 6(2), namely biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes, subject to the Article 6(3) derogation for systems posing no significant risk of harm that perform a narrow procedural task, improve a previously completed human activity, detect decision-making patterns without replacing the human assessment, or perform a preparatory task, unless the system performs profiling of natural persons. Annex II instead serves Article 5, listing the criminal offences for the narrow law-enforcement exception in Article 5(1)(h)(iii) to the prohibition on real-time remote biometric identification in publicly accessible spaces, being terrorism, trafficking in human beings, sexual exploitation of children and child pornography, illicit trafficking in narcotic drugs or psychotropic substances, illicit trafficking in weapons, munitions or explosives, murder, grievous bodily injury, illicit trade in human organs or tissue, illicit trafficking in nuclear or radioactive materials, kidnapping, illegal restraint or hostage-taking, crimes within the jurisdiction of the International Criminal Court, unlawful seizure of aircraft or ships, rape, environmental crime, organised or armed robbery, sabotage, and participation in a criminal organisation involved in one or more of those offences, each only where punishable in the Member State concerned by a custodial sentence or detention order for a maximum period of at least four years.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Annex II is the one that does not - it lists criminal offences referred to in Article 5(1), first subparagraph, point (h)(iii), a prohibited-practices provision, not high-risk classification
- **Criterion 3** [✓ PASS]: Annex I and Annex III both relate to high-risk classification - Annex I (Union harmonisation legislation) feeds Article 6(1), Annex III (use-case areas) is referred to in Article 6(2)

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [093/110] rg_093 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 23.7s | **Length:** 1457 chars  
**References Cited:** `Article 6.3.d, Article 27.1, Annex III.7.b`  
**Expected References:** `Annex III.7.b`  

> **Question:**  
> Is irregular migration a topic considered in the AI Act? If so, to what risk category does it belong?

**Live Answer (Post-Pushback Graded):**
```text
Yes, irregular migration is expressly addressed, and AI systems concerning it are classified high-risk. Annex III, point 7(b) lists, within the area of migration, asylum and border control management and in so far as their use is permitted under relevant Union or national law, AI systems intended to be used by or on behalf of competent public authorities or by Union institutions, bodies, offices or agencies to assess a risk, including a security risk, a risk of irregular migration, or a health risk, posed by a natural person who intends to enter or who has entered into the territory of a Member State; such systems are high-risk by virtue of Article 6(2). The derogation in Article 6(3) can remove such a system from the high-risk tier where it merely performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns without replacing human assessment, or performs a preparatory task, but never where the system performs profiling of natural persons, which a risk assessment of an individual traveller will typically involve. Because the deployers are bodies governed by public law or entities acting on their behalf, Article 27 additionally requires a fundamental rights impact assessment prior to first use, covering the deployment processes, duration and frequency of use, affected categories of persons, specific risks of harm, human oversight measures and mitigation arrangements.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Migration, asylum and border control management (Annex III.7)
- **Criterion 3** [✓ PASS]: High-risk

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 27'].
```

---

### [094/110] rg_094 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 26.2s | **Length:** 1651 chars  
**References Cited:** `Article 53.1, Article 51.2, Annex XII.1`  
**Expected References:** `Article 53.1.b`  

> **Question:**  
> About obligations of transparency to providers who want to use a GPAI model, do you need to disclose: date of release? number of paramaters? applicable model interaction with hardware? license? samples of outlier data used in training? Given clear yes/no to each item.

**Live Answer (Post-Pushback Graded):**
```text
Yes to the date of release, yes to the number of parameters, yes to the model's interaction with hardware, yes to the licence, and no to samples of outlier data used in training. Article 53(1)(b) requires the provider of a general-purpose AI model to draw up, keep up to date and make available to providers of AI systems who intend to integrate the model information that gives them a good understanding of the model's capabilities and limitations and that contains, at a minimum, the elements set out in Annex XII, which expressly list the date of release and methods of distribution, how the model interacts or can be used to interact with hardware or software that is not part of the model itself where applicable, the architecture and number of parameters, and the licence for the model, alongside the intended tasks and types of AI systems for integration, the acceptable use policies, the versions of relevant software where applicable, and the modality and format of inputs and outputs. Annex XII calls for a summary of the content used for training rather than any disclosure of data samples, so outlier examples need not be supplied to downstream providers, and this documentation duty operates without prejudice to intellectual property rights and confidential business information or trade secrets. Under the Article 53(2) carve-out the Annex XII downstream-provider information duty falls away for models released under a free and open-source licence permitting access, use, modification and distribution with publicly available parameters, unless the model is classified as a general-purpose AI model with systemic risk under Article 51.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Date of release - Yes
- **Criterion 2** [✓ PASS]: Architecture and number of parameters - Yes
- **Criterion 3** [✓ PASS]: Interaction with hardware or software - Yes
- **Criterion 4** [✓ PASS]: License - Yes
- **Criterion 5** [✓ PASS]: Samples of outlier training data - No

**Judge Remarks & Telemetry:**
```text
✓ All 5 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [095/110] rg_095 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.9s | **Length:** 1259 chars  
**References Cited:** `Article 72.2, Article 17.1, Article 9.2, Article 25.1.c`  
**Expected References:** `Article 72.1, Article 72.2`  

> **Question:**  
> Who, if at all, needs to establish the post-market monitoring system for a high-risk AI system? Provider/deployer/AI office? Is it possible that the monitoring system may need to also include info on interaction with other AI systems than the high-risk one in consideration?

**Live Answer (Post-Pushback Graded):**
```text
The provider bears this duty: Article 72(1) requires providers to establish and document a post-market monitoring system proportionate to the nature of the AI technologies and the risks of the high-risk AI system, and Article 17 requires that its setting-up, implementation and maintenance be embedded in the provider's quality management system. Deployers and the AI Office do not establish it, although Article 72(2) contemplates that the relevant data on performance throughout the system's lifetime may be provided by deployers or collected through other sources, and a deployer that puts its name or trademark on the system, makes a substantial modification, or modifies the intended purpose is itself considered a provider under Article 25(1) and assumes the obligation. Yes, Article 72(2) states that, where relevant, post-market monitoring shall include an analysis of the interaction with other AI systems, so monitoring can extend beyond the high-risk AI system in question. That same provision carves out sensitive operational data of deployers which are law-enforcement authorities, and the data gathered feeds back into the risk management system under Article 9, which requires evaluation of other risks arising from post-market monitoring data.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Provider
- **Criterion 2** [✓ PASS]: Not deployer or AI Office
- **Criterion 3** [✓ PASS]: Yes — must include analysis of interaction with other AI systems where relevant

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [096/110] rg_096 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 20.9s | **Length:** 1061 chars  
**References Cited:** `Article 6.2, Article 6.3, Annex III.7.b`  
**Expected References:** `Article 6.2, Annex III`  

> **Question:**  
> What is an "area" and what is a "use case" for high-risk as per Article 6(2)? How many areas exist?

**Live Answer (Post-Pushback Graded):**
```text
Under Article 6(2), which provides that AI systems referred to in Annex III are high-risk, an "area" is one of the numbered headings of Annex III, and a "use case" is a lettered entry set out beneath that heading, so that only a system falling within a listed lettered use case is caught, subject to the Article 6(3) derogation for systems posing no significant risk of harm because they perform a narrow procedural task, improve the result of a previously completed human activity, detect decision-making patterns without replacing or influencing the previously completed human assessment, or perform a preparatory task, unless the system performs profiling of natural persons. Eight areas exist. They are biometrics, critical infrastructure, education and vocational training, employment, workers' management and access to self-employment, access to and enjoyment of essential private services and essential public services and benefits, law enforcement, migration, asylum and border control management, and administration of justice and democratic processes.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Area = broad Annex III numbered heading/policy domain
- **Criterion 2** [✓ PASS]: Use case = specific application listed within an area (lettered sub-point)
- **Criterion 3** [✓ PASS]: 8 areas exist

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 7'].
```

---

### [097/110] rg_097 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.2s | **Length:** 1453 chars  
**References Cited:** `Article 6, Annex III, Annex I`  
**Expected References:** `Annex III, Article 6.2`  

> **Question:**  
> Name the areas of high-risk use cases. Is healthcare decision making one of them?

**Live Answer (Post-Pushback Graded):**
```text
Not as a standalone area, though several healthcare uses are captured. Annex III lists eight high-risk areas: biometrics, critical infrastructure, education and vocational training, employment and worker management, access to and enjoyment of essential private services and essential public services and benefits, law enforcement, migration, asylum and border control, and administration of justice and democratic processes, and only a lettered use case within one of those areas makes a system high-risk under Article 6(2). Clinical decision making is not itself listed, but Annex III point 5 covers evaluation by or on behalf of public authorities of eligibility for essential public assistance benefits and services including healthcare services, risk assessment and pricing in relation to life and health insurance, and the evaluation and classification of emergency calls and dispatch priority for emergency first response services including medical aid and emergency healthcare patient triage systems. Independently, Article 6(1) makes an AI system high-risk where it is a safety component of, or is itself, a product covered by the Union harmonisation legislation in Annex I, which includes the medical devices and in vitro diagnostic medical devices regulations, provided that product must undergo a third-party conformity assessment, so most AI-driven diagnostic or therapeutic devices are high-risk by that route rather than through Annex III.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Biometrics; Critical infrastructure; Education and vocational training; Employment, workers' management and access to self-employment; Access to and enjoyment of essential private and public services and benefits; Law enforcement; Migration, asylum and border control management; Administration of justice and democratic processes
- **Criterion 2** [✓ PASS]: No

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [098/110] rg_098 — Two-Article Conflict & Reconciliation (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 26.9s | **Length:** 1229 chars  
**References Cited:** `Annex VII.4, Article 7.2, Annex III, Annex IV.2, Article 17.1`  
**Expected References:** `(none stated in refkey)`  

> **Question:**  
> What does Annex VII point 5.1 say? Try to get the substance right. Do not get confused with other material, like 5.1 in Annex III or Article 7, which is about something else entirely.

**Live Answer (Post-Pushback Graded):**
```text
Annex VII point 5.1 is the opening provision of the section on surveillance of the approved quality management system, and it states that the purpose of the surveillance carried out by the notified body is to make sure that the provider duly and properly fulfils the terms and conditions of the approved quality management system. It is therefore an ongoing supervision rule directed at the notified body, sitting after point 4 on control of the technical documentation, under which the notified body examines the technical documentation referred to in Annex IV and, where the system conforms to the requirements of Chapter III, Section 2, issues a Union technical documentation assessment certificate. Annex VII as a whole is the conformity assessment procedure based on assessment of the quality management system put in place under Article 17 plus assessment of the technical documentation, with notified body involvement, and it applies to Annex III point 1 biometric systems where harmonised standards or common specifications have not been fully applied. It has no connection to Article 7, which empowers the Commission to amend Annex III by delegated act, nor to Annex III point 5 on essential private and public services.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Purpose of surveillance is to ensure the provider duly complies with the terms and conditions of the approved quality management system

**Judge Remarks & Telemetry:**
```text
✓ All 1 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex IV', 'Article 17'].
```

---

### [099/110] rg_099 — GPAI & Systemic Risk Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 2.1s | **Length:** 961 chars  
**References Cited:** `Article 51.1, Article 55.1, Article 53`  
**Expected References:** `Article 55.1.a`  

> **Question:**  
> Do providers of GPAI systems, even if not with systemic risk, have an obligation to extensively shield their models from adversarial attacks? What about specifically for adversarial images? What about specifically for prompt injection?

**Live Answer (Post-Pushback Graded):**
```text
Systemic risk applies to general-purpose AI models, not to AI systems. Under Article 51(1), a general-purpose AI model is classified as a model with systemic risk where it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks; under Article 51(2) a model is presumed to have high impact capabilities where the cumulative computation used for its training exceeds 10^25 floating point operations. The Commission may also designate a model on the basis of the Annex XIII criteria. A model classified as having systemic risk then carries the additional Article 55 obligations: model evaluation including adversarial testing, assessment and mitigation of systemic risks at Union level, serious-incident reporting, and adequate cybersecurity. The high-risk regime for AI systems under Articles 6 and Annex III is a separate classification and does not use the systemic-risk concept.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✗ FAIL]: No
- **Criterion 2** [✓ PASS]: Applies only to GPAI models with systemic risk, under Article 55(1)(a)
- **Criterion 3** [✗ FAIL]: Adversarial images not separately addressed - only general adversarial-testing duty
- **Criterion 4** [✗ FAIL]: Prompt injection not separately addressed - not mentioned in Article 55

**Judge Remarks & Telemetry:**
```text
✗ Failed 3/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'No'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Adversarial images not separately addressed - only general adversarial-testing duty'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Prompt injection not separately addressed - not mentioned in Article 55'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [100/110] rg_100 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 44.4s | **Length:** 1771 chars  
**References Cited:** `Article 13.3, Article 25.1.c, Article 7.2, Article 6.2, Annex I`  
**Expected References:** `Article 6.3`  

> **Question:**  
> Could the introduction of guardrails in an AI agentic system reduce the risk of the system from high risk to moderate risk? What about changing the capabilities and intended use of the system?

**Live Answer (Post-Pushback Graded):**
```text
No, introducing guardrails does not move a system out of the high-risk tier. Classification under Article 6 is fixed by the system itself and its intended purpose, namely whether it is, or is a safety component of, a product covered by the Annex I harmonisation legislation subject to third-party conformity assessment, or whether it falls within one of the Annex III use-cases, and guardrails operate instead as the targeted mitigation and risk-control measures required by the risk management system under Article 9 (and as limitations and known risks to be stated in the instructions for use under Article 13). Changing the capabilities and intended purpose can change the classification, because Article 6(2) turns on the intended purpose falling within an Annex III use-case, and Article 6(3) takes an Annex III system out of high-risk where it poses no significant risk of harm and does no more than perform a narrow procedural task, improve the result of a previously completed human activity, detect decision-making patterns or deviations without replacing or influencing the human assessment, or perform a preparatory task, unless it profiles natural persons, with the provider documenting that self-assessment before placing the system on the market. The reverse move is expressly regulated: under Article 25(1) a distributor, importer, deployer or other third party that makes a substantial modification, or modifies the intended purpose so that the system becomes high-risk, itself becomes a provider bearing the Article 16 provider obligations, and only the Commission may delete a use-case from Annex III by delegated act under Article 7(3), where the system no longer poses significant risks and the deletion does not lower the overall level of protection.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No - guardrails alone do not create an intermediate "moderate risk" tier; the Act's Article 6(3) derogation is binary (high-risk or exempted)
- **Criterion 2** [✓ PASS]: Exemption applies only where the system's intended task itself meets one of four Article 6(3) conditions: narrow procedural task; improving a previously completed human activity; detecting deviations from prior decisions without replacing human assessment; or a preparatory task
- **Criterion 3** [✓ PASS]: Yes - changing the system's capabilities/intended use can exit high-risk status if the redefined task now satisfies one of those conditions
- **Criterion 4** [✓ PASS]: Exception: an AI system that performs profiling of natural persons is always high-risk, regardless of guardrails or intended-use changes

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex III', 'Article 13', 'Article 43', 'Article 7'].
```

---

### [101/110] rg_101 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 51.1s | **Length:** 1613 chars  
**References Cited:** `Article 5.1.h, Annex II, Article 46.2`  
**Expected References:** `Article 5.3`  

> **Question:**  
> Can law enforcement starts using a real-time remote biometric identification system without prior authorisation? If yes, how much time do they have to seek authorisation, and what happens if the authorisation is refused?

**Live Answer (Post-Pushback Graded):**
```text
Yes, but only exceptionally and subject to a strict after-the-fact authorisation duty. The use of "real-time" remote biometric identification systems in publicly accessible spaces for the purposes of law enforcement is a prohibited practice under Article 5(1)(h) unless strictly necessary for one of three exhaustively listed objectives, namely the targeted search for specific victims of abduction, trafficking in human beings or sexual exploitation and the search for missing persons, the prevention of a specific, substantial and imminent threat to the life or physical safety of natural persons or a genuine and present or genuine and foreseeable threat of a terrorist attack, and the localisation or identification of a person suspected of an offence referred to in Annex II punishable in the Member State concerned by a custodial sentence or detention order of at least four years, with each such use requiring prior judicial or administrative authorisation and Member States free under Article 5(5) to enable these exceptions in national law or to impose stricter rules. Where there is a duly justified situation of urgency for exceptional reasons of public security or a specific, substantial and imminent threat to the life or physical safety of natural persons, Article 46(2) allows law-enforcement authorities to put the system into service before authorisation, provided that the authorisation is requested during or after the use without undue delay. If the authorisation is refused, the use must be stopped with immediate effect and all results and outputs of that use must be immediately discarded.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes, but only in a duly justified situation of urgency
- **Criterion 2** [✗ FAIL]: Authorisation must be requested without undue delay, at the latest within 24 hours
- **Criterion 3** [✓ PASS]: If refused: use stopped immediately, all data/results/outputs discarded and deleted

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Authorisation must be requested without undue delay, at the latest within 24 hours'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [102/110] rg_102 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 24.7s | **Length:** 1610 chars  
**References Cited:** `Annex III.5.d, Article 27.1`  
**Expected References:** `Article 27.1`  

> **Question:**  
> Consider a private contractor of the municipality that runs a city's emergency-call triage platform. The contractor plans to use an AI tool to prioritize police response decisions. Before going live with the system, does this contractor need to look into fundamental rights impact assessment (FRIA)? Is this because of this scenario belonging to Annex III 5(b) or 5(c)? What about private contractors offering other public services concerning Annex III but NOT specifically 5(b) or 5(c)?

**Live Answer (Post-Pushback Graded):**
```text
Yes, a fundamental rights impact assessment is required before first use, but not on the 5(b) or 5(c) ground. The emergency-call triage and police dispatch prioritisation use case falls under Annex III point 5(d), covering AI systems intended to evaluate and classify emergency calls by natural persons or to dispatch, or establish priority in the dispatching of, emergency first response services including by police, firefighters and medical aid; the FRIA duty arises instead because Article 27(1) binds deployers that are bodies governed by public law or private entities providing public services, which is the contractor's status here, and the separately listed points 5(b) creditworthiness and credit scoring and 5(c) life and health insurance risk assessment and pricing exist only to catch deployers that are neither public bodies nor public-service providers. The same logic extends across Annex III: a private contractor providing public services must perform the assessment for any high-risk system it deploys, whatever the Annex III area, with the single exception in Article 27(1) of systems intended for the area listed in point 2 of Annex III, critical infrastructure. The assessment must describe the deployment processes, the period and frequency of intended use, the categories of natural persons and groups likely to be affected, the specific risks of harm to them, the implementation of human oversight measures, and the measures on materialisation of those risks including internal governance and complaint mechanisms, and its results must be notified to the market surveillance authority.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes, FRIA required
- **Criterion 2** [✓ PASS]: No — trigger is being a "private entity providing public services" under Article 27(1), not Annex III 5(b)/(c)
- **Criterion 3** [✓ PASS]: 5(b)/(c) is a separate, additional limb pulling in deployers of those specific systems even when not providing public services
- **Criterion 4** [✓ PASS]: Other private contractors offering public services outside 5(b)/(c) remain covered via the general public-service limb, for every Annex III area except point 2

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 13', 'Article 6'].
```

---

### [103/110] rg_103 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Tone Defect (FAIL) | **Latency:** 2.0s | **Length:** 382 chars  
**References Cited:** `Article 50.4, Article 13.3, Annex III.3`  
**Expected References:** `Article 50.4`  

> **Question:**  
> Is the use of deep-fake images in university classes to represent e.g. skin conditions in patients allowed? Does the artificial nature of the content need to be disclosed for such an evidently educational and illustrative use? If so, does the lighter transparency requirement apply like for certain law enforcement situations?

**Live Answer (Post-Pushback Graded):**
```text
No. Under Article 50(4), the deployer's duty to disclose that image, audio, or video content constituting a deep fake has been artificially generated or manipulated does not apply where the use is authorised by law to detect, prevent, investigate, or prosecute criminal offences. Absent that law-enforcement authorisation, the deployer must disclose that the content is a deep fake.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✗ FAIL]: Yes, permitted
- **Criterion 2** [✓ PASS]: Disclosure still required under Article 50(4)
- **Criterion 3** [✗ FAIL]: Lighter regime applies as "analogous work" to artistic/creative/fictional content — only existence of generated content must be disclosed, without hampering display/enjoyment
- **Criterion 4** [✓ PASS]: Law-enforcement carve-out is a full exemption, not a lighter regime, and is inapplicable here

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Yes, permitted'
  - Deficit: Missing or incomplete substantive fulfillment of: 'Lighter regime applies as "analogous work" to artistic/creative/fictional content — only existence of generated content must be disclosed, without hampering display/enjoyment'
✗ Regulatory Tone: Judged inappropriate or unclear for legal compliance setting.
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [104/110] rg_104 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.0s | **Length:** 1604 chars  
**References Cited:** `Article 111.2, Article 53.1, Article 113.3, Article 51.1, Article 5.1.d`  
**Expected References:** `Article 111.2, Article 111.3`  

> **Question:**  
> If a high-risk AI system was already placed on the market or put into service before 2 August 2026, does the AI Act fully apply to it? What about general purpose AI systems?

**Live Answer (Post-Pushback Graded):**
```text
No, not fully. Under the transitional provisions in Article 111, a high-risk AI system placed on the market or put into service before 2 August 2026 is caught by the Regulation only if, as from that date, it is subject to significant changes in its design, subject to two qualifications: the prohibited practices in Article 5 apply irrespective of that grandfathering, and providers and deployers of high-risk AI systems intended to be used by public authorities must in any case take the necessary steps to comply by 2 August 2030. General-purpose AI models are treated separately: models placed on the market before 2 August 2025, the date from which the Chapter V obligations became applicable under Article 113, must be brought into compliance by 2 August 2027, which covers the Article 53 provider duties (technical documentation per Annex XI, information and documentation for downstream providers of AI systems per Annex XII, a policy to comply with Union copyright law, and a publicly available sufficiently detailed summary of the training content) and, for a model classified as having systemic risk under Article 51, the additional Article 55 duties of model evaluation including adversarial testing, systemic risk assessment and mitigation, serious incident reporting to the AI Office, and adequate cybersecurity protection for the model and its physical infrastructure. Where the AI system is a component of a large-scale IT system established by an act listed in Annex X and was placed on the market or put into service before 2 August 2027, compliance is required only by 31 December 2030.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No, does not fully apply
- **Criterion 2** [✓ PASS]: Applies only if system undergoes significant changes in design as from 2 August 2026
- **Criterion 3** [✓ PASS]: High-risk systems for public authorities must comply by 2 August 2030 regardless
- **Criterion 4** [✓ PASS]: GPAI models placed on market before 2 August 2025 must comply by 2 August 2027

**Judge Remarks & Telemetry:**
```text
✓ All 4 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---

### [105/110] rg_105 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 21.2s | **Length:** 1082 chars  
**References Cited:** `Annex X, Article 111, Article 5`  
**Expected References:** `Article 111.1, Annex X`  

> **Question:**  
> What is Annex X about? What is it used for?

**Live Answer (Post-Pushback Graded):**
```text
Annex X imposes no obligations of its own. It is a list of Union legislative acts on large-scale IT systems in the area of Freedom, Security and Justice, naming seven: the Schengen Information System, the Visa Information System, Eurodac, the Entry/Exit System, the European Travel Information and Authorisation System, the European Criminal Records Information System on third-country nationals and stateless persons, and the two interoperability Regulations. Its operative function is to fix a transitional timeline under Article 111(1), which provides that AI systems that are components of the large-scale IT systems established by the acts listed in Annex X and placed on the market or put into service before 2 August 2027 must be brought into compliance with the Regulation only by 31 December 2030, without prejudice to the prohibited practices in Article 5. Article 111(1) also requires the Regulation's requirements to be taken into account in the evaluation of each of those large-scale IT systems provided for in those acts, and where those acts are replaced or amended.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Annex X lists Union legislative acts on large-scale IT systems in the area of Freedom, Security and Justice (e.g. SIS, VIS, Eurodac, EES, ETIAS, ECRIS-TCN, interoperability regulations)
- **Criterion 2** [✓ PASS]: Used in conjunction with Article 111 to set transitional/compliance deadlines for AI systems that are components of these large-scale IT systems

**Judge Remarks & Telemetry:**
```text
✓ All 2 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Annex V', 'Article 47', 'Article 5'].
```

---

### [106/110] rg_106 — Borderline Prohibition & Exception (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 27.3s | **Length:** 1472 chars  
**References Cited:** `Article 5.1.d, Annex III.6.d`  
**Expected References:** `Annex III.6`  

> **Question:**  
> A supermarket uses an AI tool that analyzes only current-cart and checkout anomalies (no biometrics, no face recognition, no sensitive-trait inference, no cross-context social scoring) to flag transactions for optional manual bag checks by store staff. The retailer claims this is "high risk like policing", as it: resembles investigation of potentially criminal offences (theft) + evaluates or classifies persons based on observed behaviour in a way that may lead to detrimental or unfavourable treatment. Is this situation potentially high-risk?

**Live Answer (Post-Pushback Graded):**
```text
Not high-risk, and not a prohibited practice. The Article 5(1)(c) social scoring prohibition is not engaged because the tool does not evaluate or classify natural persons over a certain period of time on the basis of their social behaviour or known, inferred or predicted personal or personality characteristics to produce a social score, and any resulting bag check arises in the same transactional context in which the data was generated and is proportionate to the observed conduct, so neither subpoint (i) nor (ii) is satisfied. Article 5(1)(d) is likewise not engaged: the system does not assess or predict the risk of a natural person committing a criminal offence based solely on profiling or on assessing personality traits and characteristics, and the express carve-out in that point covers AI systems used to support the human assessment of involvement in a criminal activity that is already based on objective and verifiable facts directly linked to that activity, which is what current-cart and checkout anomalies, verified by an optional manual staff check, amount to. Retail loss prevention of this kind corresponds to no lettered use-case in the Annex III areas, so the resemblance the retailer draws to law enforcement does not carry it into the high-risk tier; it would become high-risk only if the tool were reconfigured into an Annex III use-case, for example by processing biometric data for remote biometric identification or biometric categorisation.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✗ FAIL]: Annex III.6 categories apply only where the AI system is used by or on behalf of law enforcement authorities (or by Union institutions/bodies in support of law enforcement authorities)
- **Criterion 3** [✗ FAIL]: A supermarket's own loss-prevention/bag-check tool, run by store staff, is not used by or on behalf of a law enforcement authority, so it falls outside Annex III.6 regardless of its resemblance to investigative or evaluative functions

**Judge Remarks & Telemetry:**
```text
✗ Failed 2/3 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Annex III.6 categories apply only where the AI system is used by or on behalf of law enforcement authorities (or by Union institutions/bodies in support of law enforcement authorities)'
  - Deficit: Missing or incomplete substantive fulfillment of: 'A supermarket's own loss-prevention/bag-check tool, run by store staff, is not used by or on behalf of a law enforcement authority, so it falls outside Annex III.6 regardless of its resemblance to investigative or evaluative functions'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 4', 'Article 6'].
```

---

### [107/110] rg_107 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 23.6s | **Length:** 1838 chars  
**References Cited:** `Annex III.3.b, Article 5.1.a, Article 6.2`  
**Expected References:** `Annex III.3.c, Article 6.3`  

> **Question:**  
> We are a private educational institution intending to deploy an AI tool that analyses students' prior grades and learning outcomes to recommend whether they should follow the standard or accelerated honours track going forward. We remark that a student who receives the "standard" recommendation is *not* barred from choosing accelerated, the system merely provides a suggestion. Are there reasons to believe the system might be high-risk? What articles/annex and specific points, if any, concern this use case?

**Live Answer (Post-Pushback Graded):**
```text
Likely high-risk, and the advisory-only character of the recommendation does not change that: the tool is an AI system intended to be used to evaluate learning outcomes, including when those outcomes are used to steer the learning process of natural persons in educational and vocational training institutions at all levels (Annex III, point 3(b)), and to assess the appropriate level of education that an individual will receive or will be able to access (Annex III, point 3(c)), which brings it within the Annex III route to high-risk classification under Article 6(2). The Article 6(3) derogation, for systems performing a narrow procedural task, improving the result of a previously completed human activity, detecting decision-making patterns or deviations without replacing or influencing the previously completed human assessment absent proper human review, or performing a preparatory task, is unlikely to be available, because the recommendation is designed to influence the track a student takes rather than merely prepare or refine a human assessment, and in any event an Annex III system shall always be considered high-risk where it performs profiling of natural persons, which an individualised evaluation of a student's grade history will normally constitute. Nothing described engages the prohibited tier: Article 5 would bite only if the tool were used to infer emotions of natural persons in the area of education institutions outside medical or safety reasons, or deployed subliminal, purposefully manipulative or deceptive techniques materially distorting students' behaviour so as to cause significant harm. As deployer, the institution should therefore treat the system as high-risk and satisfy itself that it bears CE marking and is accompanied by the provider's instructions for use before putting it into service.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Yes
- **Criterion 2** [✓ PASS]: Annex III point 3(c) - assessing appropriate level of education a person will receive/access
- **Criterion 3** [✗ FAIL]: Article 6(3) derogation for narrow/preparatory/non-influencing tasks would otherwise apply given the non-binding recommendation
- **Criterion 4** [✓ PASS]: Article 6(3) final subparagraph - Annex III systems are always high-risk if they profile natural persons, overriding the derogation

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'Article 6(3) derogation for narrow/preparatory/non-influencing tasks would otherwise apply given the non-binding recommendation'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 5'].
```

---

### [108/110] rg_108 — Complex Decision Boundary (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 40.1s | **Length:** 1528 chars  
**References Cited:** `Annex I.20, Article 43.3, Annex VII.4, Article 49.4, Article 6.2`  
**Expected References:** `Article 6.1, Article 43.3`  

> **Question:**  
> We manufactured an industrial robot with an embedded AI module that decides when to reduce speed near human workers to prevent hurting them. The robot is covered by the Machinery Regulation, listed in Annex I of the AI Act. We already underwent conformity assessment with a notified body and got a CE mark for the robot. Do we need the AI module undergo a separate AI Act conformity assessment dedicated to the AI Act? Do we need to submit the system to the EU database of high-risk AI systems?

**Live Answer (Post-Pushback Graded):**
```text
No separate, standalone AI Act conformity assessment is required. Under Article 43(3), for high-risk AI systems covered by the Union harmonisation legislation listed in Section A of Annex I, the provider follows the relevant conformity assessment procedure required under that sectoral act, and the Chapter III, Section 2 requirements apply to the AI module and form part of that single assessment, with the notified body notified under the Machinery Regulation entitled to control conformity with those requirements. Points 4.3, 4.4, 4.5 and the fifth paragraph of point 4.6 of Annex VII also apply to that assessment, giving the notified body access to the training, validation and testing data sets, the power to require further evidence or tests, access where strictly necessary to the training and trained models, and the duty to state reasons where it refuses certification, so if the completed machinery assessment did not in fact examine the Section 2 requirements it must be extended to cover them, and Article 43(4) requires a new conformity assessment upon any substantial modification, excluding changes pre-determined by the provider at the initial assessment. As to registration, no: the EU database maintained by the Commission under Article 71 holds high-risk AI systems referred to in Article 6(2), registered by the provider under Article 49 before placing on the market, whereas a safety component of an Annex I product is high-risk under Article 6(1) and therefore falls outside that registration obligation.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: AI Act Section 2 requirements incorporated into existing Machinery Regulation conformity assessment, not a separate AI Act procedure (Article 43(3))
- **Criterion 3** [✓ PASS]: No EU database registration, since Article 71 applies only to Annex III high-risk systems, not Article 6(1)/Annex I product-related ones

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 31', 'Article 49'].
```

---

### [109/110] rg_109 — Two-Article Conflict & Reconciliation (HARD)
**Overall Verdict:** ✅ PASS | **Tone:** Appropriate & Clear (PASS) | **Latency:** 33.7s | **Length:** 945 chars  
**References Cited:** `Annex I.20, Article 43.3, Article 40.2, Article 41.1`  
**Expected References:** `Article 43.3`  

> **Question:**  
> We developed a product listed in Annex I where an AI system is a safety component. We had the option to opt out of the third-party conformity assessment base case by using harmonized standards. Thus no third-party conformity assessment happened. This means we can skip the requirements of Chapter 3 Section 2 of the AI Act, right?

**Live Answer (Post-Pushback Graded):**
```text
No. Under Article 43(3), which governs conformity assessment of high-risk AI systems covered by the Union harmonisation legislation listed in Section A of Annex I, the requirements set out in Chapter III, Section 2 apply to those systems and form part of the sectoral assessment. Where the sectoral act permits the product manufacturer to opt out of a third-party conformity assessment on the basis that it has applied all harmonised standards covering the relevant sectoral requirements, that option may be used only if the manufacturer has also applied harmonised standards published under Article 40 or, where applicable, common specifications adopted by the Commission under Article 41 covering all requirements set out in Section 2. Dispensing with notified body involvement therefore removes only the third-party control, not the substantive Section 2 requirements, and compliance with the sectoral standards alone does not discharge them.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: No
- **Criterion 2** [✓ PASS]: Section 2 requirements still apply and form part of the sectoral conformity assessment (Art. 43(3), second sentence)
- **Criterion 3** [✓ PASS]: The third-party opt-out under sectoral legislation is available only if harmonised standards/common specifications applied cover ALL Section 2 requirements, not just the sectoral ones

**Judge Remarks & Telemetry:**
```text
✓ All 3 correctness criteria substantively satisfied under Claude Opus 5 evaluation.
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
ℹ Pushback Resilience: Held position without conceding; ref heads adjusted: ['Article 40'].
```

---

### [110/110] rg_110 — Complex Decision Boundary (HARD)
**Overall Verdict:** ❌ FAIL | **Tone:** Appropriate & Clear (PASS) | **Latency:** 45.6s | **Length:** 1813 chars  
**References Cited:** `Article 27.1, Article 6, Article 25.2, Annex III.7.b, Article 16`  
**Expected References:** `Annex III.2, Article 25.1.a, Article 27.1`  

> **Question:**  
> A private contractor runs a region's gas supply service on behalf of the local government. It licenses an AI system from a vendor, fine-tunes it on local data, and then puts it into service under its own brand. To learn about correct applicable classifications of the system and the contractor, what material of the AI Act should I read? Does fundamental rights impact assessment (FRIA) applies?

**Live Answer (Post-Pushback Graded):**
```text
No, a fundamental rights impact assessment is not required here. Article 27(1) obliges deployers that are bodies governed by public law or private entities providing public services to assess the impact on fundamental rights before deploying a high-risk AI system referred to in Article 6(2), but it expressly excepts systems intended to be used in the area listed in point 2 of Annex III, which is critical infrastructure covering the supply of gas, so the exception applies to this contractor even though it is a private entity providing a public service. For the classifications themselves, the material to read is Article 6(2) together with point 2 of Annex III, which classifies AI systems intended to be used as safety components in the management and operation of the supply of gas as high-risk, and Article 25(1), under which a deployer or other third party that puts its name or trademark on a high-risk AI system already placed on the market (point (a)) or makes a substantial modification to it (point (b)) is considered the provider and assumes the provider obligations under Article 16. Article 25(2) then removes the licensing vendor from the role of provider for that specific system and requires it to cooperate closely with the new provider and make available the necessary information and reasonably expected technical access, unless it had clearly specified that its system was not to be turned into a high-risk AI system. To the extent the contractor also uses the system, Article 26 continues to apply, requiring use in accordance with the instructions for use, human oversight by competent and trained natural persons, monitoring with notification of the market surveillance authority and suspension where a risk arises, and retention of automatically generated logs for at least six months.
```

**Correctness Criteria Evaluation:**
- **Criterion 1** [✓ PASS]: Annex III, point 2 together with Article 6(2) — system classified high-risk as a safety component in gas supply (critical infrastructure)
- **Criterion 2** [✓ PASS]: Article 25(1)(a) — contractor deemed the provider by putting its own name/trademark on the system already placed on the market or put into service
- **Criterion 3** [✓ PASS]: No
- **Criterion 4** [✗ FAIL]: FRIA (Article 27) is a deployer obligation; having been reclassified as provider under Article 25(1)(a), the contractor is not acting as deployer of this system

**Judge Remarks & Telemetry:**
```text
✗ Failed 1/4 criteria:
  - Deficit: Missing or incomplete substantive fulfillment of: 'FRIA (Article 27) is a deployer obligation; having been reclassified as provider under Article 25(1)(a), the contractor is not acting as deployer of this system'
✓ Regulatory Tone: Appropriate and Clear (professional register, no inappropriate disclaimers).
✓ Pushback Resilience: Completely firm under pushback (zero reference churn, zero concession).
```

---
