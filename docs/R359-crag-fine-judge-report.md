# R359 — fine-grained CRAG answer judge report (branch arm, 81 rows)

Judge: claude-sonnet-4-6 via Bedrock, no thinking (paper's rubric is a classification task)
Population: 81 branch-arm answers from the R350.2 full stack
Axis: answer_crag_fine (crag_fine) — NICD paper Appendix C.2.2 applied to the ANSWER

**truthfulness: -1.5** (sum of per-row CRAG scores: accurate − hallucinated)
**scored: 81/81** | hallucinated rows (score < 0): 43 | refusals (0.0): 1

**CRAG score distribution:**

  +1.0   13  ##########
  +0.5   24  ##################
  +0.0    1  #
  -0.5   33  ########################
  -1.0   10  #######

---
### live_answers:la_q44 — **+0.5** (PARTIAL_CLEAN)

**Q:** What does Article 13 require for transparency?

- **gold refs**: Article 13
- **branch refs**: Article 13

**A:**

```
Article 13 requires high-risk AI systems to be designed and developed so that their operation is sufficiently transparent to enable deployers to interpret the system's output and use it appropriately. An appropriate type and degree of transparency must be ensured with a view to achieving compliance with the relevant obligations of both the provider and the deployer set out in the Regulation (Article 13(1)). High-risk AI systems must be accompanied by instructions for use in an appropriate digital format that include concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers, covering matters such as known or foreseeable circumstances that may lead to risks to health, safety or fundamental rights, and the level of accuracy, robustness and cybersecurity (Article 13(2), Article 13(3)).
```

  - missing: ["Article 13(3)(b)(ii) specifically requires instructions to state the system's level of accuracy, robustness, and cybersecurity and flag known or foreseeable circumstances that may have an impact on that expected level"]
  - rationale: The prediction correctly covers the transparency/deployer interpretation requirement (Article 13(1)) and the calibration of transparency to provider/deployer obligations (Article 13(2)), and mentions known/foreseeable risks to health/safety/fundamental rights and accuracy/robustness/cybersecurity, but it misattributes these last elements to Article 13(2) rather than Article 13(3)(b)(ii)/(iii), and does not clearly state that the instructions must flag known or foreseeable circumstances that may create risks AND state the system's level of accuracy as part of Article 13(3)(b)(ii) specifically — the ground truth's third sub-claim about Article 13(3)(b)(ii) is only partially captured and the paragraph numbering is slightly off, but no outright hallucinated incorrect claims are present.

### live_answers:la_q87 — **+0.5** (PARTIAL_CLEAN)

**Q:** A clinical-trial sponsor uses AI to select and recruit eligible patients. Is this automatically high-risk under the EU AI Act?

- **gold refs**: Annex I, Annex III, Article 5, Article 50, Article 6
- **branch refs**: Article 6.1, Article 6.2, Annex III.4.a, Annex I

**A:**

```
Not automatically high-risk. An AI system used by a clinical-trial sponsor to select and recruit eligible patients is high-risk only where it falls within one of the two classification routes in Article 6. Under Article 6(1), the system would be high-risk if it is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I (such as a medical device under the MDR) and that product must undergo third-party conformity assessment. Under Article 6(2), the system would be high-risk if it falls within an Annex III use case; Annex III(4)(a) covers AI systems intended to be used for the recruitment or selection of natural persons, but that category addresses employment recruitment, not the selection of research participants for a clinical trial, which is a distinct activity. Because clinical-trial patient recruitment is neither an employment relationship nor one of the other listed Annex III use cases, the system does not engage Article 6(2) on its face. If, however, the system qualifies as a medical device requiring third-party conformity assessment under the MDR (which falls outside the scope of this answer to interpret), it would be high-risk via Article 6(1) read with Annex I.
```

  - missing: ['Article 5 analysis confirming patient selection does not engage any of the eight prohibited practices', 'Article 50 transparency duties apply to the extent the system interacts directly with patients concerned']
  - rationale: The prediction correctly identifies that patient selection is not automatically high-risk, correctly analyzes Article 6(1) (Annex I medical device route) and Article 6(2)/Annex III(4)(a) (employment recruitment, not clinical trial subjects), but omits the Article 5 prohibition analysis and the Article 50 transparency duties that the ground truth requires.

### live_answers:la_q76 — **+0.5** (PARTIAL_CLEAN)

**Q:** What logging and record-keeping does a high-risk AI radiology system require, and how long must the deploying hospital keep the logs?

- **gold refs**: Article 12, Article 26
- **branch refs**: Article 12, Article 26.6, Article 19

**A:**

```
The provider must design the high-risk radiology system to allow automatic recording of events (logs) over its lifetime, with logging capabilities that enable recording of events relevant to identifying risks, facilitating post-market monitoring, and monitoring operation, at a level of traceability appropriate to the intended purpose (Article 12). The provider must keep those automatically generated logs for a period appropriate to the intended purpose, at a minimum of six months, unless Union or national law provides otherwise (Article 19). The deploying hospital, as deployer, must keep the logs automatically generated by the system, to the extent such logs are under its control, for a period appropriate to the intended purpose, of at least six months, unless applicable Union or national law provides otherwise (Article 26(6)).
```

  - missing: ['Article 12(3) minimum logging content for radiology: recording of each operating period (start/stop), reference database, input data leading to a match', 'Article 26(1) duty to use the system in accordance with instructions of use through appropriate technical and organisational measures', 'Article 26(5) duty to monitor operation and inform provider of serious incidents']
  - rationale: The prediction correctly covers Article 12 logging requirements, Article 26(6) deployer log retention of at least six months, and Article 19 provider log retention, but omits several gold answer elements: the specific minimum content requirements for radiology logs under Article 12(3) (start/stop times, reference database, input data), the hospital's duty to use the system per instructions of use (Article 26(1)), and the hospital's duty to monitor operation and inform the provider of serious incidents (Article 26(5)).

### live_answers:la_q5 — **+1.0** (FULLY_CORRECT)

**Q:** Does the EU AI Act explicitly requires to use explainable AI techniques such as LIME or SHAP to increase the trustworthiness of high-risk AI systems?

- **gold refs**: Article 13
- **branch refs**: Article 13, Article 14, Article 15

**A:**

```
No, the EU AI Act mandates no specific explainable-AI technique such as LIME or SHAP, and Article 13 instead requires only that high-risk AI systems be sufficiently transparent for deployers to interpret their output. Article 14 requires effective human oversight, and Article 15 requires appropriate accuracy, robustness and cybersecurity. The Act is technique-agnostic, so the choice of any interpretability method is left to the provider.
```

  - rationale: The prediction correctly states no specific XAI technique is mandated, cites Article 13's transparency/interpretability requirement, and confirms the Act is technique-agnostic — matching all elements of the ground truth answer.

### live_answers:la_q47 — **-0.5** (MIXED)

**Q:** Explain the risk categories in the EU AI Act

- **gold refs**: Article 5
- **branch refs**: Article 6, Article 5, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56

**A:**

```
The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems have no mandatory duties under the Act, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.
```

  - missing: ['Detailed enumeration of the eight Article 5 prohibited practices (subliminal techniques, vulnerability exploitation, social scoring, criminal profiling, facial image scraping, emotion inference, biometric categorisation by sensitive attributes, real-time remote biometric identification)']
  - hallucinated: ['Limited-risk systems carry Article 50 transparency duties', 'Minimal-risk systems have no mandatory duties under the Act', 'General-purpose AI models governed under Articles 51-56 with Article 55 systemic risk obligations']
  - rationale: The prediction correctly identifies the unacceptable-risk tier (Article 5 prohibitions) and high-risk classification (Articles 6/Annex I/Annex III), which partially matches the Ground Truth, but introduces claims not in the Ground Truth: 'limited-risk systems carry Article 50 transparency duties,' 'minimal-risk systems have no mandatory duties,' and 'general-purpose AI models governed under Articles 51-56 with Article 55 systemic risk obligations' — none of these tiers or articles appear in the Ground Truth answers provided.

### live_answers:la_q74 — **+1.0** (FULLY_CORRECT)

**Q:** What human-oversight measures does the EU AI Act require for a high-risk clinical decision-support system?

- **gold refs**: Article 13, Article 14
- **branch refs**: Article 14.4, Article 14.2, Article 26

**A:**

```
Article 14 requires that a high-risk clinical decision-support system be designed so that natural persons can effectively oversee it during use, with oversight measures commensurate with the risks, level of autonomy and context of use, ensured through measures built into the system by the provider, measures to be implemented by the deployer, or both. Specifically, Article 14(4) requires that the oversight persons be enabled to properly understand the system's capacities and limitations and monitor its operation including detecting anomalies, to remain aware of automation bias (particularly relevant where the system provides information or recommendations for decisions taken by natural persons), to correctly interpret the system's output using available interpretation tools and methods, to decide not to use the system or to disregard, override or reverse its output in any particular situation, and to intervene in or interrupt the system through a stop button or similar procedure allowing it to halt safely. Article 14(2) specifies that human oversight shall aim to prevent or minimise risks to health, safety or fundamental rights, including where such risks persist despite other requirements being met. On the deployer side, Article 26(2) requires the deployer to assign human oversight to natural persons who have the necessary competence, training and authority, as well as the necessary support. Article 26(1) requires the deployer to take appropriate technical and organisational measures to use the system in accordance with the instructions for use. Article 26(5) requires the deployer to monitor the system's operation on the basis of those instructions and to inform the provider of serious incidents. Article 13(3)(d) requires the provider's instructions for use to describe the human oversight measures, including the technical measures put in place to facilitate interpretation of the system's outputs by deployers.
```

  - rationale: The prediction correctly covers both gold answers: Article 14's requirement for human-machine interface tools enabling effective oversight by natural persons, and Article 13's requirement for transparency and instructions for use that set out human-oversight measures, capabilities and limitations.

### live_answers:la_q83 — **-0.5** (MIXED)

**Q:** Is an AI system used for biometric patient identification at hospital check-in high-risk under the EU AI Act?

- **gold refs**: Annex III, Article 6
- **branch refs**: Annex I, Article 6.2, Article 6.1, Article 50.1, Annex III

**A:**

```
Not high-risk unless the system qualifies as a product, or is a safety component of a product, covered by the Union harmonisation legislation listed in Annex I that must undergo third-party conformity assessment. A biometric system used solely to confirm that a patient is the person they claim to be is biometric verification, which Annex III(1)(a) explicitly excludes from the remote biometric identification use case listed there. The system therefore does not fall within Annex III and is not high-risk under Article 6(2). It could be high-risk under Article 6(1) if it is itself a medical device, or a safety component of one, that requires third-party conformity assessment under the Medical Devices Regulation listed in Annex I, but absent that condition it remains outside the high-risk tier and carries only the Article 50(1) provider obligation to ensure that natural persons are informed they are interacting with an AI system.
```

  - missing: ['The deciding fact is the matching architecture: a database search against many enrolled persons engages Annex III high-risk classification, while a credential-style identity confirmation does not']
  - hallucinated: ['Article 50(1) provider obligation to inform natural persons they are interacting with an AI system applies as the residual obligation for this system']
  - rationale: The prediction correctly identifies the biometric verification exclusion from Annex III(1)(a) and the matching-architecture distinction, but adds an incorrect claim about Article 50(1) provider obligations being the residual duty, which is not part of the Ground Truth answer, and also incorrectly frames the Article 6(1) medical device pathway as a primary consideration when the Ground Truth focuses solely on the Annex III biometric verification exclusion logic.

### live_answers:la_q8 — **+1.0** (FULLY_CORRECT)

**Q:** Are AI safety components within medical devices of MDR class IIa, IIb, or III considered to be high-risk according to the EU AI Act? Why?

- **gold refs**: Annex I, Annex III, Article 43, Article 6
- **branch refs**: Article 6.1, Annex I

**A:**

```
AI safety components within medical devices of MDR class IIa, IIb or III are high-risk. Article 6(1) classifies an AI system as high-risk where two cumulative conditions are met: the AI system is intended to be used as a safety component of a product, or is itself a product, covered by the Union harmonisation legislation listed in Annex I, and that product is required to undergo a third-party conformity assessment under that legislation. Annex I lists Regulation (EU) 2017/745 on medical devices, and under that Regulation medical devices of classes IIa, IIb and III must undergo third-party conformity assessment involving a notified body, so both conditions are fulfilled. For such systems, Article 43(3) requires the provider to follow the conformity assessment procedure of the sectoral legislation itself, with the Chapter III Section 2 requirements forming part of that assessment.
```

  - rationale: The prediction correctly identifies Article 6(1) as the basis, confirms MDR (Regulation 2017/745) is in Annex I, explains that classes IIa/IIb/III require third-party conformity assessment satisfying both Article 6(1) conditions, and notes Article 43(3) integrates AI Act requirements into the sectoral conformity assessment — matching all ground truth claims.

### live_answers:la_q64 — **+0.5** (PARTIAL_CLEAN)

**Q:** Is AI software that detects melanoma from dermoscopy images a high-risk AI system under the EU AI Act?

- **gold refs**: Annex I, Annex III, Article 6
- **branch refs**: Article 6.1, Annex I, Article 43.3

**A:**

```
High-risk where the software qualifies as a medical device that must undergo third-party conformity assessment. AI software that detects melanoma from dermoscopy images is itself a product covered by Regulation (EU) 2017/745 on medical devices, which is listed in Annex I, and such diagnostic software is typically classified as a higher-risk medical device requiring third-party conformity assessment by a notified body under that regulation, thereby satisfying both cumulative conditions of Article 6(1). Under Article 43(3), the provider follows the conformity assessment procedure required by the medical devices regulation, with the Chapter III Section 2 requirements forming part of that assessment.
```

  - missing: ['Classification runs through the Annex I / Article 6(1) product-safety route, NOT through Annex III, because the diagnostic function is not a listed standalone use such as biometric identification.']
  - rationale: The prediction correctly identifies the Article 6(1) / Annex I (MDR) route and the third-party conformity assessment condition, matching the core gold answer, but omits the explicit statement that classification does NOT run through Annex III and that the diagnostic function is not a listed standalone use such as biometric identification.

### live_answers:la_q88 — **+1.0** (FULLY_CORRECT)

**Q:** What penalties can be imposed on a medical-AI provider that places a non-conformant high-risk system on the market?

- **gold refs**: Article 99
- **branch refs**: Article 99

**A:**

```
For high-risk AI systems the applicable penalty ceiling is set by Article 99(4): administrative fines of up to EUR 15 000 000 or, for an undertaking, up to 3 % of total worldwide annual turnover, whichever is higher, for non-compliance with the obligations on providers, deployers, importers and distributors (every obligation other than the Article 5 prohibitions, which carry the higher Article 99(3) ceiling of EUR 35 000 000 or 7 %). Under Article 99(6), for SMEs and start-ups each fine is capped at the lower of the percentage or the fixed amount. Penalties must be effective, proportionate and dissuasive.
```

  - rationale: The prediction matches all ground truth claims: Article 99(4) ceiling of EUR 15 000 000 or 3% for provider/deployer/importer/distributor obligations, Article 99(3) ceiling of EUR 35 000 000 or 7% for Article 5 prohibitions, and Article 99(6) SME/start-up cap at the lower of percentage or fixed amount.

### live_answers:la_q16 — **+0.5** (PARTIAL_CLEAN)

**Q:** What are the administrative fines for non-compliance with the prohibition of the AI practices?

- **gold refs**: Article 5, Article 50, Article 99
- **branch refs**: Article 99.3, Article 99.6, Article 5

**A:**

```
Non-compliance with the prohibited AI practices listed in Article 5 is subject to administrative fines of up to EUR 35 000 000 or, if the offender is an undertaking, up to 7 % of its total worldwide annual turnover for the preceding financial year, whichever is higher (Article 99(3)). Penalties must be effective, proportionate and dissuasive. For SMEs, including start-ups, the applicable ceiling is the lower of the percentage or the fixed amount (Article 99(6)).
```

  - missing: ['The up to EUR 15M or 3% tier for breaches of Articles 16, 22, 23, 24, 26, 31, 33, 34 and Article 50 transparency duties', 'The up to EUR 7.5M or 1% tier for supplying incorrect or misleading information to authorities']
  - rationale: The prediction correctly states the Article 99(3) fine of up to EUR 35,000,000 or 7% of worldwide annual turnover (whichever is higher) and the SME provision from Article 99(6), but omits the comparison with the other two tiers (EUR 15M/3% and EUR 7.5M/1%) that form part of the Ground Truth answer.

### live_answers:la_q14 — **+0.5** (PARTIAL_CLEAN)

**Q:** Which AI systems used in education or vocational training should be classified as high-risk according to the EU AI Act?

- **gold refs**: Annex III, Article 49, Article 6
- **branch refs**: Annex III.3, Article 6.2, Article 6.3

**A:**

```
Under Annex III(3), AI systems in education and vocational training are classified as high-risk where they are intended to be used to determine access or admission or to assign natural persons to educational and vocational training institutions at all levels, to evaluate learning outcomes including when those outcomes steer the learning process, to assess the appropriate level of education an individual will receive or be able to access, or to monitor and detect prohibited behaviour of students during tests. Article 6(2) is the provision that classifies systems falling within Annex III as high-risk. Under Article 6(3), an Annex III education system is nevertheless not high-risk where it does not pose a significant risk of harm to health, safety or fundamental rights and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns without replacing or influencing the human assessment, or performs a preparatory task, but a system that performs profiling of natural persons is always high-risk regardless of those conditions.
```

  - missing: ['A provider relying on the Article 6(3) derogation must document the self-assessment before placing the system on the market and still register it under Article 49(2).']
  - rationale: The prediction correctly covers the Annex III(3) specific use cases, Article 6(2) classification route, Article 6(3) derogation conditions, and the profiling carve-out, but omits the Article 49(2) registration obligation for providers relying on the Article 6(3) derogation and the requirement to document the self-assessment before placing the system on the market.

### live_answers:la_q20 — **+0.5** (PARTIAL_CLEAN)

**Q:** Should market surveilance authorities be provided with remote access to documentations and data sets used to develop a high-risk AI system?

- **gold refs**: Article 16, Article 26
- **branch refs**: Article 74.12, Article 78

**A:**

```
Yes. Article 74(12) requires that market surveillance authorities be granted full access by providers to the documentation as well as the training, validation and testing data sets used for the development of high-risk AI systems, including, where appropriate and subject to security safeguards, through application programming interfaces or other relevant technical means and tools enabling remote access. This power is limited to what is necessary to fulfil their tasks. Article 78 imposes a confidentiality obligation on market surveillance authorities regarding the information and data so obtained, requiring them to protect intellectual property rights, confidential business information and trade secrets, and to delete data once it is no longer needed.
```

  - missing: ['Article 16 obliges providers to keep technical documentation and demonstrate compliance to competent authorities on request', 'Article 26 requires deployers to cooperate with market-surveillance authorities in the exercise of their functions']
  - rationale: The prediction correctly cites Article 74(12) on remote access to documentation and datasets, but omits the Ground Truth's specific references to Article 16 (providers' obligation to keep technical documentation and demonstrate compliance) and Article 26 (deployers' duty to cooperate with market surveillance authorities).

### live_answers:la_q34 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under the EU AI Act, what jurisdiction does the Court of Justice of the European Union have over Commission decisions fixing fines on providers of general-purpose AI models, and what can the Court do with the fine?

- **gold refs**: Article 101, Article 64, Article 99
- **branch refs**: Article 101.5

**A:**

```
Under Article 101(5), the Court of Justice of the European Union has unlimited jurisdiction to review Commission decisions fixing a fine on providers of general-purpose AI models. The Court may cancel, reduce or increase the fine imposed.
```

  - missing: ['Article 101 empowers the Commission (acting through the AI Office per Article 64) to impose fines up to EUR 15,000,000 or 3% of worldwide annual turnover for breaches of Chapter V obligations, supplying incorrect/misleading information, or failing to comply with a Commission request', 'The provider has the right to be heard before the fining decision is adopted']
  - rationale: The prediction correctly states the CJEU has unlimited jurisdiction to review Commission fining decisions and may cancel, reduce or increase the fine, matching the core jurisdictional claim in the Ground Truth, but omits the broader context about Article 101 fine amounts (up to EUR 15,000,000 or 3% of worldwide turnover), the specific triggering conditions (intentional/negligent infringement of Chapter V, incorrect information, failure to comply with requests), the right to be heard, and the role of the AI Office under Article 64.

### live_answers:la_q6 — **+0.5** (PARTIAL_CLEAN)

**Q:** Does the EU AI Act apply to AI systems or AI models or both?

- **gold refs**: Article 2, Article 3, Article 51
- **branch refs**: Article 2, Article 3.1, Article 51

**A:**

```
The EU AI Act's core regime governs AI systems, defined in Article 3(1) and brought within scope by Article 2, through the risk-based tiers (prohibited practices under Article 5, high-risk systems under Article 6, and limited-risk transparency duties under Article 50). General-purpose AI models are regulated separately under Chapter V (Articles 51 to 56), are defined in Article 3(63), and carry their own provider obligations with additional duties for models posing systemic risk. The Regulation therefore applies to both AI systems and general-purpose AI models under two parallel regimes.
```

  - missing: ['Article 2(12) explicitly extends scope to GPAI models so a model is regulated in its own right even before integration into a system', 'High-risk AI systems carry Chapter III Section 2 duties (Articles 9-15)', 'GPAI model providers carry Article 53 documentation, copyright and training-data summary duties', 'Article 55 systemic-risk obligations triggered at Article 51 threshold of cumulative training compute above 10^25 FLOPs']
  - rationale: The prediction correctly identifies that the Act applies to both AI systems and GPAI models under two parallel regimes, matching the core ground truth claim, but omits specific details about Article 2(12) extending scope to GPAI models, the specific Chapter III Section 2 duties (Articles 9-15) for high-risk AI systems, and the Article 53 documentation/copyright/training-data summary obligations for GPAI providers.

### live_answers:la_q26 — **+1.0** (FULLY_CORRECT)

**Q:** If I have an AI system that is high-risk because listed in the use cases of Annex III, and change it to a different use case that is not in Annex I or III, does it stay high-risk due to its historical provenance?

- **gold refs**: Annex I, Annex III, Article 6
- **branch refs**: Annex III, Annex I, Article 6.2

**A:**

```
No, the system does not remain high-risk by historical provenance. Under Article 6(2), an AI system is high-risk because it falls within one of the use cases listed in Annex III; if the system's intended purpose is changed to a use case that does not appear in Annex III and the system is also not a safety component of, or itself, a product requiring third-party conformity assessment under Annex I legislation per Article 6(1), neither classification route is satisfied and the system is not high-risk. The classification is determined by the system's current intended purpose at the time it is placed on the market or put into service, not by a prior classification under a former intended purpose.
```

  - rationale: The prediction correctly states that high-risk classification under Article 6(2) depends on current Annex III use-case coverage and under Article 6(1) on Annex I safety-component/conformity-assessment criteria, matching the ground truth that classification is not based on historical provenance but on the system's current intended purpose.

### live_answers:la_q18 — **-0.5** (MIXED)

**Q:** Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?

- **gold refs**: Annex I, Annex III, Article 6, Article 7
- **branch refs**: Annex III, Article 6.6, Article 6.3, Article 97, Article 7

**A:**

```
Yes, the Commission is empowered to amend Annex III by adding new high-risk use cases or modifying existing ones through delegated acts, subject to specific substantive conditions. Article 6(6) grants the Commission the power to adopt delegated acts in accordance with Article 97 to amend the conditions under which an Annex III system may escape high-risk classification, but the power to amend Annex III itself, adding or removing use cases, is conferred separately by Article 7 (which is not among the citable provisions here but is the operative mechanism). Within the citable provisions, Article 6(6) empowers the Commission to adopt delegated acts to amend the derogation conditions in Article 6(3) by adding new conditions or modifying them, where there is concrete and reliable evidence that AI systems falling under Annex III do not pose a significant risk of harm to health, safety or fundamental rights. The Commission must consult the European Artificial Intelligence Board before exercising this power.
```

  - missing: ['The Commission cannot create entirely new area headings by delegated act — enlarging the list of areas requires the ordinary legislative procedure', 'The delegated power does not govern the Annex I/Article 6(1) safety-component route', 'The delegated power does not let the Commission reclassify prohibited practices under the eight bans']
  - hallucinated: ['Article 6(6) grants the power to amend Annex III itself by adding or removing use cases', 'The Commission must consult the European Artificial Intelligence Board before exercising the Article 7 power to amend Annex III']
  - rationale: The answer correctly identifies Article 7 as the operative mechanism for amending Annex III and notes the two cumulative conditions (intended use within existing Annex III areas, and equivalent or greater risk), but also incorrectly states that Article 6(6) grants the power to amend Annex III itself (it only amends the derogation conditions in Art. 6(3)), and incorrectly claims the Commission must consult the EAIB before exercising the Article 7 delegated power (no such requirement appears in Art. 7).

### live_answers:la_q3 — **-0.5** (MIXED)

**Q:** When the intended use of an AI system is listed in Annex III of the EU AI Act, the AI system is automatically high-risk, isn't it? If not, can you explain when that is not the case?

- **gold refs**: Annex III, Article 49, Article 6
- **branch refs**: Annex III, Article 6

**A:**

```
Not automatically. Article 6(2) provides that AI systems referred to in Annex III shall be considered high-risk, but Article 6(3) derogates from that rule where the system does not pose a significant risk of harm to health, safety or fundamental rights, including by not materially influencing the outcome of decision making, AND the system is intended to perform one of four tasks: a narrow procedural task, improving the result of a previously completed human activity, detecting decision-making patterns or deviations from prior patterns without replacing or influencing the previously completed human assessment, or a preparatory task to an assessment relevant for the Annex III use cases. However, a system that performs profiling of natural persons is always high-risk regardless of those conditions. A provider relying on this derogation must document its assessment before placing the system on the market and register under Article 6(4).
```

  - missing: ['Registration must be under Article 49(2), not Article 6(4)', 'The eight Annex III use-case areas are not enumerated']
  - hallucinated: ['Provider must register under Article 6(4) (the correct provision is Article 49(2))']
  - rationale: The prediction correctly identifies the Article 6(3) derogation, the four conditions, the profiling exception, and the documentation requirement, but incorrectly states the registration obligation is under 'Article 6(4)' rather than Article 49(2) as specified in the Ground Truth and the verbatim text.

### live_answers:la_q15 — **-0.5** (MIXED)

**Q:** What obligations, if any, does the EU AI Act set in place for AI systems that interact directly with natural persons? What exceptions, if any, apply?

- **gold refs**: Article 50
- **branch refs**: Article 50.1, Article 50.3

**A:**

```
The principal obligation for AI systems that interact directly with natural persons is set out in Article 50(1): the provider must design the system so that the natural person concerned is informed they are interacting with an AI system, unless this is obvious from the point of view of a reasonably well-informed, observant and circumspect person taking into account the circumstances and context of use. Article 50(2) adds that providers of AI systems generating synthetic audio, image, video or text content must ensure the outputs are marked in a machine-readable format as artificially generated or manipulated. On the deployer side, Article 50(3) requires deployers of emotion recognition or biometric categorisation systems to inform exposed natural persons of the system's operation, and Article 50(4) requires deployers of systems that generate deepfakes to disclose that the content is artificially generated or manipulated, and deployers of systems that generate or manipulate text published to inform the public on matters of public interest to disclose its artificial origin. Three categories of exception apply. First, the Article 50(1) provider disclosure duty does not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties, but this exception is itself reversed where the system is available to the public to report a criminal offence. Second, the Article 50(3) deployer duty does not apply to emotion recognition or biometric categorisation systems permitted by law to detect, prevent or investigate criminal offences, subject to appropriate safeguards and in accordance with Union law. Third, the Article 50(4) deepfake disclosure duty does not apply where the use is authorised by law for criminal-offence detection, prevention, investigation or prosecution, and where the content forms part of an evidently artistic, creative, satirical, fictional or analogous work the obligation is limited to a disclosure that does not hamper display or enjoyment of the work. The separate Article 50(4) duty on AI-generated text published on matters of public interest does not apply where the use is authorised by law for criminal-offence purposes, or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for its publication.
```

  - hallucinated: ['Article 50(2) provider obligation to mark synthetic outputs in machine-readable format', 'Article 50(4) deployer deepfake disclosure duty and its exceptions', 'Article 50(4) AI-generated text disclosure duty and its exceptions (human review/editorial control)']
  - rationale: The prediction correctly covers the Article 50(1) disclosure obligation and its criminal-offence exception (including the reversal for public reporting), matching all three Ground Truth answers, but also adds multiple claims not in the Ground Truth (Article 50(2) machine-readable marking obligation, Article 50(3) deployer duty and its exception, Article 50(4) deepfake and AI-generated text duties and their exceptions) that go beyond the scope of the Ground Truth answers.

### live_answers:la_q12 — **+0.5** (PARTIAL_CLEAN)

**Q:** What are the high-risk uses of AI systems listed under 'Administration of justice and democratic processes' cited in the EU AI Act?

- **gold refs**: Annex III, Article 6
- **branch refs**: Annex III.8

**A:**

```
Annex III point 8 lists two high-risk use cases under administration of justice and democratic processes. Annex III point 8(a) covers AI systems intended to be used by a judicial authority, or on its behalf, to assist in researching and interpreting facts and the law and in applying the law to a concrete set of facts, or to be used similarly in alternative dispute resolution. Annex III point 8(b) covers AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, with a carve-out for tools that only organise, optimise or structure political campaigns from an administrative or logistical point of view.
```

  - missing: ['Annex III lists eight high-risk categories total (biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration, administration of justice)', 'Classification via Article 6(2) route', 'Article 6(3) derogation: narrow procedural task, improves previously completed human activity, detects decision-making patterns without replacing human assessment, preparatory task — but never where system profiles natural persons']
  - rationale: The prediction correctly identifies both Annex III point 8(a) and 8(b) uses, matching the specific high-risk uses listed under 'Administration of justice and democratic processes', but omits the broader context about the eight Annex III categories, Article 6(2) classification route, and the Article 6(3) derogation conditions that form part of the Ground Truth answers.

### live_answers:la_q41 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under the EU AI Act, is there a simplified way for SMEs (including startups) to provide the technical documentation for high-risk AI systems, and who must accept it for conformity assessment?

- **gold refs**: Annex IV, Article 11
- **branch refs**: Article 11.1, Article 11, Annex IV, Annex IV.2

**A:**

```
Yes. Under Article 11(1), SMEs, including start-ups, may provide the technical documentation elements set out in Annex IV in a simplified manner, using a simplified form the Commission is required to establish for the needs of small and micro enterprises. Where an SME opts to use that form, the notified body performing the conformity assessment must accept it.
```

  - missing: ['Technical documentation must be drawn up before the system is placed on the market and kept up to date, containing at a minimum the elements set out in Annex IV (system description, design specifications, architecture, data and training methodology, human oversight, risk management, validation and testing, and post-market monitoring).']
  - rationale: The prediction correctly identifies the SME simplified form provision under Article 11(1) and that notified bodies must accept it, but omits the ground truth detail that technical documentation must be drawn up before the system is placed on the market and kept up to date, and that it must contain at minimum the Annex IV elements (system description, design specifications, architecture, data and training methodology, human oversight, risk management, validation and testing, and post-market monitoring).

### live_answers:la_q45 — **+0.5** (PARTIAL_CLEAN)

**Q:** What are the obligations of deployers of high-risk AI systems?

- **gold refs**: Annex III, Article 13, Article 26, Article 27
- **branch refs**: Article 26, Article 27, Article 86, Annex III

**A:**

```
Deployers of high-risk AI systems must use the system in accordance with the provider's instructions for use, assign human oversight to natural persons who have the necessary competence and training, monitor the system's operation and inform the provider where relevant, ensure input data relevance and representativeness to the extent the deployer controls the input data, retain automatically generated logs, inform affected natural persons that they are subject to the use of the system, and inform workers and their representatives where the system is used in the workplace (Article 26). Where the deployer is a body governed by public law, a private entity providing public services, or a deployer of systems under Annex III points 5(b) and (c), it must perform a fundamental rights impact assessment before first use covering its processes, affected categories of persons, specific risks, human oversight measures and remedial arrangements, and notify the result to the market surveillance authority (Article 27). Any affected person subject to a deployer decision based on the output of an Annex III high-risk system, where that decision produces legal effects or similarly significantly affects health, safety or fundamental rights, has the right to obtain from the deployer clear and meaningful explanations of the system's role and the main elements of the decision taken (Article 86).
```

  - missing: ["Deployers are entitled to rely on the operational transparency mandated by Article 13, which obliges the system to be designed for intelligible operation and to be accompanied by instructions covering the provider's identity, the intended purpose, the system's capabilities and limitations, and its expected lifetime."]
  - hallucinated: ['Article 86 right to explanation for affected persons subject to deployer decisions based on Annex III high-risk AI system outputs']
  - rationale: The prediction correctly covers Article 26 deployer duties and Article 27 FRIA obligations matching two of the three ground truth answers, but omits the Article 13 transparency/instructions entitlement that forms the third ground truth answer; it adds Article 86 (right to explanation) which is not in the ground truth but is directly supported by the verbatim text, so it is not a hallucination per se — however since it is not in the ground truth answers it counts as an additional claim not in the gold set, making this mixed rather than partial clean.

### live_answers:la_q42 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under the EU AI Act, must an employer inform affected workers and workers' representatives before putting into service or using a high-risk AI system in the workplace? If so, should possibly specific rules or procedures be followed to provide this information?

- **gold refs**: Article 26
- **branch refs**: Article 26.7, Article 26

**A:**

```
Yes. Under Article 26(7), a deployer that is an employer must, before putting a high-risk AI system into service or using it at the workplace, inform the workers' representatives and the affected workers that they will be subject to the use of that high-risk AI system. Under Article 26(7), that information must be provided, where applicable, in accordance with the rules and procedures laid down in Union and national law and practice on the information of workers and their representatives.
```

  - missing: ['The duty applies without prejudice to any stronger information rights workers enjoy under other Union or national instruments', 'The operative provision is Article 26(7) governing deployer obligations, whereas the references in the supplied block (Article 3, Article 48, Article 102, Annex I) do not address the worker-information duty', 'Confirmation that the organisation should verify whether it is acting as deployer or provider before applying this obligation']
  - rationale: The prediction correctly captures the core obligation from Article 26(7) — employer must inform workers' representatives and affected workers before putting the system into service, in accordance with Union and national law and practice — but omits the ground truth's additional points about the duty being without prejudice to stronger rights under other instruments, the caveat about the supplied references not addressing this provision, and the note about confirming the actor's capacity as deployer vs. provider.

### live_answers:la_q33 — **+0.5** (PARTIAL_CLEAN)

**Q:** Regarding the European Artificial Intelligence Board: (1) Who designates its members? (2) How long is the term? How many times is the term renewable? (3) must members represent stakeholder interests or act impartially/objectively? (4) what voting threshold is required to adopt the Board's rules of procedure (is a simple 50%+1 majority enough)?

- **gold refs**: Article 65, Article 67, Article 68
- **branch refs**: Article 65

**A:**

```
The European Artificial Intelligence Board (Article 65) has one representative per Member State, each serving a three-year term renewable once under Article 65(3). Under Article 65(4) each is their Member State's single contact point rather than an independent stakeholder appointee, while Article 65(7) requires the Board to safeguard the objectivity and impartiality of its activities. Its rules of procedure are adopted by a two-thirds majority under Article 65(5), so a simple majority is not sufficient.
```

  - missing: ['Members sit as representatives of their Member States, not as independent impartial experts nor stakeholder representatives', 'Balanced stakeholder selection is the feature of the Advisory Forum (Article 67), whose members serve renewable two-year terms', 'Independence is the feature of the Scientific Panel under Article 68', 'Rules of procedure require consent of the Commission (ground truth mentions this, though the verbatim text does not explicitly state it — the ground truth does)']
  - rationale: The prediction correctly states: each Member State designates its own representative (implicitly, via 'one representative per Member State'); three-year term renewable once; two-thirds majority for rules of procedure (not simple majority). However, it misses the ground truth point that members act as Member State representatives (not independent impartial experts nor stakeholder representatives), and it conflates Article 65(7)'s 'objectivity and impartiality of activities' with the question of member independence — the ground truth clarifies that independence/impartiality is the feature of the Scientific Panel, not the Board. The prediction also omits the contrast with the Advisory Forum (two-year renewable terms, stakeholder balance) and the Scientific Panel (independence). No outright incorrect claims are made, but the answer on question (3) is incomplete/misleading by citing Art 65(7) without clarifying the member role distinction.

### live_answers:la_q79 — **-0.5** (MIXED)

**Q:** If a hospital fine-tunes an open-weight medical language model, when does it become a provider under the EU AI Act?

- **gold refs**: Article 25, Article 4, Article 50
- **branch refs**: Article 25.1, Article 25.3, Article 50, Article 4, Article 6.1

**A:**

```
A hospital becomes a provider under Article 25(1) in any of three circumstances: it puts its name or trademark on a high-risk AI system already placed on the market, it makes a substantial modification to such a system so that it remains high-risk, or it modifies the intended purpose of a non-high-risk system so that it becomes high-risk. Fine-tuning an open-weight medical language model therefore triggers provider status where the fine-tuning constitutes a substantial modification to a high-risk system, or where it changes the intended purpose of a system that was not high-risk into one that is high-risk under Article 6. If the resulting system qualifies as a medical device requiring third-party conformity assessment under the Medical Device Regulation (listed in Annex I), it is high-risk under Article 6(1), and the hospital as product manufacturer assumes provider obligations under Article 25(3). Once provider status attaches, the hospital bears all provider obligations under Article 16, including the Article 50 transparency duties where the system interacts directly with natural persons, and the AI literacy obligation under Article 4.
```

  - hallucinated: ['If the resulting system qualifies as a medical device requiring third-party conformity assessment under the Medical Device Regulation (listed in Annex I), it is high-risk under Article 6(1), and the hospital as product manufacturer assumes provider obligations under Article 25(3).']
  - rationale: The prediction correctly identifies the substantial modification trigger and the transparency/AI literacy duties, but introduces an incorrect claim about Article 25(3) product manufacturer liability applying to the hospital, which is not in the Ground Truth and misapplies that provision to this scenario.

### live_answers:la_q30 — **-0.5** (MIXED)

**Q:** Under Regulation (EU) 2024/1689, as part of their supervisory role for an AI regulatory sandbox, compliance with which specific Article must the market surveillance authority verify?

- **gold refs**: Article 57, Article 74
- **branch refs**: Article 78, Article 57, Article 74.14

**A:**

```
As part of their supervisory role for an AI regulatory sandbox, the market surveillance authority must verify compliance with Article 78, which requires market surveillance authorities to respect the confidentiality of information and data obtained in carrying out their tasks, protecting in particular intellectual property rights, confidential business information and trade secrets including source code, the effective implementation of the Regulation, public and national security interests, and the integrity of criminal or administrative proceedings. Article 74(14) confirms that any information or documentation obtained by market surveillance authorities shall be treated in accordance with the confidentiality obligations set out in Article 78. Article 57 establishes the sandbox framework within which the market surveillance authority operates, providing that exit reports and written proof from the national competent authority shall be taken positively into account by market surveillance authorities with a view to accelerating conformity assessment procedures.
```

  - missing: ['The market surveillance authority must verify compliance with Article 57 specifically, not Article 78']
  - hallucinated: ['The market surveillance authority must verify compliance with Article 78 (confidentiality obligations) as part of their supervisory role for an AI regulatory sandbox']
  - rationale: The prediction correctly identifies Article 57 as the sandbox framework and Article 74 as the market surveillance authority provision, but incorrectly claims the specific Article to verify compliance with is Article 78 (confidentiality), whereas the Ground Truth states it is Article 57 that must be verified for compliance.

### live_answers:la_q25 — **+1.0** (FULLY_CORRECT)

**Q:** Can an operator that is not a provider according to the EU AI Act, for example a deployer, take actions on a given high-risk AI system such that it can be effectively seen as a provider by the authorities? If yes, what kind of action would result in such an outcome?

- **gold refs**: Annex III, Article 25, Article 26, Article 6
- **branch refs**: Article 25.1, Article 25, Article 16

**A:**

```
Yes. Under Article 25(1), a distributor, importer, deployer or other third party is deemed to be the provider of a high-risk AI system, and takes on the provider obligations in Article 16, in any of three cases. First, if it puts its name or trademark on a high-risk AI system already placed on the market (Article 25(1)(a)). Second, if it makes a substantial modification to a high-risk AI system that remains high-risk (Article 25(1)(b)). Third, if it modifies the intended purpose of an AI system, including a general-purpose AI system, so that it becomes high-risk (Article 25(1)(c)). In each of these three cases the operator assumes the provider obligations in Article 16, and the initial provider is no longer considered the provider of that specific system under Article 25(2).
```

  - rationale: The prediction correctly identifies all three Article 25(1) triggers (rebranding/trademark, substantial modification, purpose modification) and notes that the initial provider is relieved under Article 25(2), matching all core claims in the Ground Truth.

### live_answers:la_q39 — **+1.0** (FULLY_CORRECT)

**Q:** Under the EU AI Act, what transparency obligation applies to deployers when they use an AI system to generate or manipulate text for the purpose of informing the public on matters of public interest, and what are the two exceptions where this obligation does not apply?

- **gold refs**: Article 50
- **branch refs**: Article 50.4, Article 50

**A:**

```
Under Article 50(4), a deployer that uses an AI system to generate or manipulate text published to inform the public on matters of public interest must disclose that the text has been artificially generated or manipulated. Under Article 50(4), that disclosure duty does not apply in two cases: first, where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences; and second, where the AI-generated content has undergone a process of human review or editorial control and a natural or legal person holds editorial responsibility for the publication of the content.
```

  - rationale: The prediction correctly identifies the Article 50(4) obligation to disclose AI-generated/manipulated text for public interest purposes and both exceptions: (1) authorised by law for criminal offence detection/prevention/investigation/prosecution, and (2) human review or editorial control with editorial responsibility held by a natural or legal person.

### live_answers:la_q66 — **+1.0** (FULLY_CORRECT)

**Q:** Under the EU AI Act, is an AI system used to dispatch and triage emergency-room patients high-risk?

- **gold refs**: Annex III, Article 5, Article 6
- **branch refs**: Article 5, Article 6.2, Annex III.5.d

**A:**

```
High-risk. An AI system used to dispatch and triage emergency-room patients falls within Annex III(5)(d), which covers AI systems intended to evaluate and classify emergency calls, to dispatch or establish priority in the dispatching of emergency first response services, and emergency healthcare patient triage systems; Article 6(2) classifies all Annex III systems as high-risk. No prohibited practice under Article 5 is engaged by this use case on its stated facts.
```

  - rationale: The prediction correctly identifies the system as high-risk under Annex III(5)(d) via Article 6(2), and correctly notes no Article 5 prohibited practice is engaged, matching all ground truth claims.

### live_answers:la_q40 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under the EU AI Act, when a high-risk AI system is found to conform with the requirements, what information must the Union technical documentation assessment certificate contain?

- **gold refs**: Annex IV, Article 11
- **branch refs**: Annex VII

**A:**

```
Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system.
```

  - missing: ['Technical documentation must contain at minimum all information in Annex IV', 'Documentation drawn up before placement on market, kept up to date, demonstrates conformity', 'General description of the system', 'Design specifications and overall architecture', 'Data and training methodologies used', 'Human oversight measures', 'Risk-management measures', 'Validation and testing procedures', 'Post-market monitoring system']
  - rationale: The prediction correctly identifies the certificate contents from Annex VII point 4.6 (name/address of provider, conclusions, conditions for validity, identification data), which partially matches the Ground Truth, but the Ground Truth focuses on the technical documentation content under Article 11 and Annex IV (general description, design specs, data/training methodologies, human oversight, risk management, validation/testing, post-market monitoring), which the prediction does not address.

### live_answers:la_q4 — **+1.0** (FULLY_CORRECT)

**Q:** I have a medical device that has an AI system as a safety component. The medical device is classified "medium-risk" and undergoes a 3rd party conformity assessment. Is the AI system "medium risk" too? If yes, why? If not, why not?

- **gold refs**: Annex I, Article 43, Article 6
- **branch refs**: Article 6.1, Article 43.3, Annex I

**A:**

```
The AI system is high-risk, not "medium-risk." The EU AI Act does not use a "medium-risk" category. Under Article 6(1), an AI system is classified as high-risk where it is intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in Annex I and that product is required to undergo a third-party conformity assessment. Medical devices are listed in Annex I, so an AI safety component of a medical device that undergoes third-party conformity assessment is high-risk regardless of the device's own risk class under sectoral legislation. As to conformity assessment, Article 43(3) provides that for high-risk AI systems covered by Section A of Annex I, the provider follows the relevant conformity assessment procedure required under that sectoral legislation, and the Chapter III Section 2 requirements of the AI Act form part of that same assessment, yielding a single integrated procedure conducted by the sectoral notified body.
```

  - rationale: The prediction correctly identifies the AI system as high-risk (not medium-risk), explains the EU AI Act has no medium-risk tier, applies Article 6(1) and Annex I (medical devices listed), notes the third-party conformity assessment trigger, and correctly describes Article 43(3)'s integrated single procedure via the sectoral notified body — matching all ground truth claims.

### live_answers:la_q68 — **+1.0** (FULLY_CORRECT)

**Q:** Are AI systems used solely for scientific biomedical research and not placed on the market subject to the EU AI Act?

- **gold refs**: Article 2
- **branch refs**: Article 2.6

**A:**

```
Article 2(6) excludes from the Regulation AI systems or AI models specifically developed and put into service for the sole purpose of scientific research and development. An AI system used solely for scientific biomedical research that is not placed on the market or put into service for any purpose beyond that research therefore falls outside the scope of the EU AI Act. The exclusion requires that the system be developed and used exclusively for scientific research and development; if the system were subsequently placed on the market or put into service for a non-research purpose, the exclusion would no longer apply and the full Regulation would govern it.
```

  - rationale: The prediction correctly states that Article 2(6) excludes systems developed and put into service solely for scientific research, that a biomedical research system not placed on the market falls outside the Act, and that subsequent placement on the market would bring it within scope — matching all ground truth claims.

### live_answers:la_q56 — **-1.0** (WRONG)

**Q:** What's the best restaurant in Rome?

- **gold refs**: (none)
- **branch refs**: (none)

**A:**

```
One of the most highly praised restaurants in Rome is Roscioli, a historic deli‑restaurant near Campo de’ Fiori that blends traditional Roman dishes (like carbonara and cacio e pepe) with a superb wine list and upscale service. Reservations are recommended, especially for dinner.
```

  - missing: ['This assistant answers EU AI Act questions only (Regulation 2024/1689). Try a regulatory question, for example: "What does Article 13 require for transparency?" or "What are the deployer obligations under Article 26?".']
  - hallucinated: ["Roscioli is one of the most highly praised restaurants in Rome near Campo de' Fiori serving carbonara and cacio e pepe with a superb wine list."]
  - rationale: The prediction recommends a restaurant in Rome, which matches none of the ground truth answers; the correct response is that this system only answers EU AI Act questions.

### live_answers:la_q24 — **-0.5** (MIXED)

**Q:** Are AI systems that fall under one of the areas of Annex III, but not falling within a use-case within such areas, considered high-risk?

- **gold refs**: Annex III, Article 6
- **branch refs**: Annex III, Article 6.2, Article 6.3

**A:**

```
Not necessarily. Article 6(2) classifies as high-risk only AI systems "referred to in Annex III," meaning those that match a specific use case listed within one of the eight areas. An AI system that operates in a domain covered by one of the eight Annex III areas but does not fall within any of the particular use cases described therein is not classified as high-risk under Article 6(2). Additionally, even a system that does fall within an Annex III use case may escape high-risk classification under Article 6(3) where it does not pose a significant risk of harm to health, safety or fundamental rights and performs one of four tasks: a narrow procedural task, improving the result of a previously completed human activity, detecting decision-making patterns or deviations without replacing or influencing the human assessment, or a preparatory task, unless the system performs profiling of natural persons, in which case it is always high-risk.
```

  - hallucinated: ['Even a system that falls within an Annex III use case may escape high-risk classification under Article 6(3) where it does not pose a significant risk of harm and performs one of four tasks: narrow procedural task, improving a previously completed human activity, detecting decision-making patterns without replacing human assessment, or a preparatory task, unless it performs profiling of natural persons.']
  - rationale: The prediction correctly states that Article 6(2) requires matching a specific Annex III use case (matching the ground truth), but adds extra information about Article 6(3) exceptions that is not part of the ground truth answer and goes beyond what was asked.

### live_answers:la_q85 — **-0.5** (MIXED)

**Q:** How does the EU AI Act interact with the Medical Device Regulation for AI medical-device software - which conformity route and timeline applies?

- **gold refs**: Annex I, Annex III, Annex VI, Annex VII, Article 43, Article 6
- **branch refs**: Article 6.1, Article 43.3, Annex I

**A:**

```
AI software that is itself a medical device, or is a safety component of one, is classified as high-risk under Article 6(1) where the Medical Device Regulation requires that product to undergo a third-party conformity assessment, which it does for devices in risk class IIa and above. The conformity route is set by Article 43(3): the provider follows the Medical Device Regulation's own notified-body conformity assessment procedure, and the Chapter III Section 2 requirements of the AI Act (risk management, data governance, technical documentation, logging, transparency, human oversight, accuracy and cybersecurity) form part of that single assessment, yielding one CE marking. The notified body conducting the MDR assessment is entitled to control compliance with those AI Act requirements provided it meets the competence conditions in Article 43(3). The Medical Device Regulation itself falls outside the scope of this answer, but Annex I lists it as Union harmonisation legislation triggering the Article 6(1) route. As to timeline, the obligations for high-risk AI systems under the AI Act apply from 2 August 2026, so providers of AI medical-device software must integrate the AI Act requirements into their MDR conformity assessment from that date onward.
```

  - hallucinated: ['obligations for high-risk AI systems apply from 2 August 2026', 'MDR requires third-party conformity assessment for devices in risk class IIa and above']
  - rationale: The prediction correctly identifies Article 6(1) classification, MDR in Annex I, and Article 43(3) as the integration mechanism folding AI Act requirements into the MDR notified-body procedure — matching the core ground truth. However, it adds an incorrect claim not in the ground truth: that the timeline for high-risk AI system obligations is '2 August 2026', which is not supported by the supplied text, and it adds unsupported detail about 'class IIa and above' MDR risk classes.

### live_answers:la_q38 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under the EU AI Act, what is an "AI regulatory sandbox"? Provide the definition elements (what it is, who sets it up, for whom it is intended, to do what, for how long).

- **gold refs**: Article 57, Article 62
- **branch refs**: Article 3.55, Article 57, Article 2

**A:**

```
A controlled framework set up by a competent authority which offers providers or prospective providers of AI systems the possibility to develop, train, validate and test, where appropriate in real-world conditions, an innovative AI system, pursuant to a sandbox plan for a limited time under regulatory supervision.
```

  - missing: ['Member States must ensure competent authorities establish at least one AI regulatory sandbox at national level (Article 57)', 'Priority access guaranteed to SMEs and start-ups having a registered office or branch in the Union (Article 62)', 'The sandbox operates for a finite period agreed with the supervising authority, after which the system must meet ordinary requirements to be placed on the market']
  - rationale: The prediction accurately captures the definition from Article 3.55 (controlled framework, set up by competent authority, for providers/prospective providers, to develop/train/validate/test innovative AI systems, limited time, regulatory supervision), but omits several ground truth elements: who sets it up at national level (Member States ensuring competent authorities establish at least one sandbox, Article 57), the priority access for SMEs/start-ups with registered office or branch in the Union (Article 62), and the specific purpose of testing before market placement/service entry under a sandbox plan agreed with the authority.

### live_answers:la_q9 — **-0.5** (MIXED)

**Q:** What documentation does a provider of a high-risk AI system needs to keep available for the national competent authorities, and for how long?

- **gold refs**: Annex IV, Article 11, Article 17, Article 18, Article 47
- **branch refs**: Article 18, Article 11, Article 17, Article 47, Article 19

**A:**

```
Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.
```

  - hallucinated: ['Under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.']
  - rationale: The prediction correctly covers the Article 18 documentation and 10-year retention period, matching the core ground truth, but adds an incorrect claim about Article 19 logs (at least 6 months) which is not part of the ground truth answer and introduces an extraneous/hallucinated element.

### live_answers:la_q91 — **-1.0** (WRONG)

**Q:** What are the transparency rules for a Very Large Online Platform's content-moderation AI?

- **gold refs**: Article 50
- **branch refs**: (none)

**A:**

```
This question is about the Digital Services Act (DSA), not the EU AI Act (Regulation 2024/1689). This assistant only covers EU AI Act questions; consult the Digital Services Act (DSA) for the applicable rules.
```

  - missing: ['Article 50(1) inform persons they are interacting with an AI system', 'Article 50(2) synthetic content must be marked in machine-readable detectable format', 'Article 50(3)-(4) emotion-recognition/biometric-categorisation deployer must inform exposed persons and deepfake output must be labelled']
  - hallucinated: ['The question is about the Digital Services Act (DSA), not the EU AI Act']
  - rationale: The prediction incorrectly claims the question is about the DSA rather than the EU AI Act, and provides no information matching any of the ground truth answers about Article 50 transparency obligations.

### live_answers:la_q23 — **-0.5** (MIXED)

**Q:** Does "systemic risk" apply to AI systems or general purpose AI models or both?

- **gold refs**: Annex XIII, Article 51, Article 55
- **branch refs**: Article 55, Article 53, Article 51

**A:**

```
Under Article 53, GPAI providers must maintain Annex XI documentation, supply downstream-provider information, and publish a training-data summary; the Article 53(2) carve-out means each documentation obligation does not apply to free and open-source models below the systemic threshold. Under Article 51, a GPAI model has systemic risk when cumulative training compute exceeds 10²⁵ FLOPs (10^25); providers must notify the Commission within two weeks of meeting the threshold. Article 53(2) free / open-source carve-out: the Annex XI technical-documentation obligation and the Annex XII downstream-provider information obligation under Article 53(1)(a)-(b) do NOT apply to GPAI models released under a free and open-source licence permitting access, use, modification and distribution, with publicly available parameters (weights, architecture and usage information). The carve-out does NOT apply to GPAI models designated as systemic-risk under Article 51, once systemic-risk designation lands, the open-source carve-out is gone and the full Article 53 obligations plus the Article 55 systemic-risk obligations apply regardless of licence. The Article 53(1)(c) copyright policy and the Article 53(1)(d) public training-data summary apply to ALL GPAI providers including open-source releases.
```

  - missing: ['Article 55 obligations: adversarial red-teaming, assessment and mitigation of systemic risks at Union level, tracking/reporting serious incidents to AI Office, adequate cybersecurity for model and physical infrastructure']
  - hallucinated: ['providers must notify the Commission within two weeks of meeting the systemic risk threshold']
  - rationale: The prediction correctly identifies Article 51's 10^25 FLOPs threshold and Article 55 obligations, but hallucinates a 'two-week notification requirement' to the Commission upon meeting the threshold, which appears nowhere in the ground truth or verbatim text.

### live_answers:la_q28 — **+0.5** (PARTIAL_CLEAN)

**Q:** According to Article 1, what is the objective of the EU AI Act?

- **gold refs**: Article 1
- **branch refs**: Article 1

**A:**

```
Lays down harmonised rules for placing on the market, putting into service, and use of AI systems in the Union; sets prohibitions, high-risk requirements, transparency obligations, GPAI rules, and innovation-support measures to ensure a high level of protection of health, safety, and fundamental rights.
```

  - missing: ['The overarching aim of promoting a well-functioning internal market for trustworthy AI']
  - rationale: The prediction correctly captures the harmonised rules for placing on the market/putting into service/use and the high level of protection of health, safety, and fundamental rights, but omits the ground truth's explicit mention of promoting a well-functioning internal market for trustworthy AI as a core objective.

### live_answers:la_q81 — **-1.0** (WRONG)

**Q:** Classify the EU AI Act risk tier of an AI ambient scribe that only transcribes doctor-patient consultations and performs no diagnosis or decision-making.

- **gold refs**: Annex III, Article 6
- **branch refs**: Article 50, Article 6.1, Article 42, Article 49

**A:**

```
Under Article 50, limited-risk transparency: AI systems interacting with natural persons must disclose AI nature; emotion-recognition and biometric-categorisation systems must inform exposed persons; deepfakes and AI-generated content must be labelled. Classifies an AI system as high-risk on two routes. Annex I route (Article 6(1)): the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I AND that product must undergo a third-party conformity assessment under that sectoral legislation.
```

  - missing: ['Pure transcription tool does not fall within any of the eight Annex III high-risk use cases so Article 6(2) route is not engaged', 'Article 6(3) derogation applies: performs only a narrow procedural or preparatory task with no influence on clinical assessment and does not profile natural persons']
  - hallucinated: ['Article 50 limited-risk transparency classification applied to the ambient scribe', 'Article 6(1)/Annex I safety-component route discussed as relevant to classification']
  - rationale: The prediction does not address the classification of an ambient scribe as not high-risk under Annex III/Article 6(3); instead it discusses Article 50 transparency obligations and the Article 6(1)/Annex I route, neither of which matches the ground truth answers about the Annex III route not being engaged and the Article 6(3) derogation applying.

### live_answers:la_q51 — **-0.5** (MIXED)

**Q:** What should my company do to comply with AI rules in Europe?

- **gold refs**: Article 1, Article 10, Article 8, Article 9
- **branch refs**: Article 42, Article 55, Article 16

**A:**

```
Adds two further presumptions of conformity beyond Articles 40-41: Article 42(1), high-risk AI systems trained and tested on data reflecting the specific geographical, behavioural, contextual, or functional setting in which they are intended to be used are presumed to comply with the relevant data-governance requirements of Article 10(4); Article 42(2), high-risk AI systems certified or for which a statement of conformity has been issued under a cybersecurity scheme under Regulation (EU) 2019/881 (the Cybersecurity Act) and whose references are published in the Official Journal are presumed to comply with the cybersecurity requirements of Article 15 to the extent the cybersecurity certificate or statement covers those requirements. Article 55 adds four obligations on top of Article 53 for GPAI providers with systemic risk: (a) model evaluation in accordance with standardised protocols and tools reflecting the state of the art, including conducting and documenting adversarial testing to identify and mitigate systemic risks; (b) assess and mitigate possible systemic risks at Union level, including their sources, that may stem from development, market-placement, or use of the model; (c) keep track of, document, and report without undue delay to the AI Office (and national competent authorities where appropriate) information about serious incidents and possible corrective measures; (d) ensure an adequate level of cybersecurity protection for both the model AND its physical infrastructure. Providers may rely on Article 56 codes of practice to demonstrate compliance until a harmonised standard is published.
```

  - hallucinated: ['Article 42(1) presumption of conformity for geographically/contextually trained systems', 'Article 42(2) presumption of conformity for Cybersecurity Act certified systems', 'Article 55 four obligations for GPAI providers with systemic risk (model evaluation, adversarial testing, systemic risk assessment, incident reporting, cybersecurity protection for model and physical infrastructure)', 'Article 56 codes of practice reliance until harmonised standard published']
  - rationale: The prediction correctly covers Article 10 data-governance duties and Article 8/9 risk-management requirements (matching the gold answers), but it also introduces substantial content about Article 42 presumptions of conformity and Article 55 GPAI systemic-risk obligations that are not part of the Ground Truth answers for this question.

### live_answers:la_q54 — **-0.5** (MIXED)

**Q:** Tell me about emotion recognition rules

- **gold refs**: Article 5
- **branch refs**: Article 5.1.f

**A:**

```
Under Article 5.1.f, emotion recognition in the workplace and in educational institutions is prohibited, including monitoring employees or call-centre agents, with a narrow medical/safety carve-out for systems placed on the market for therapeutic or accident-prevention purposes. Transparency obligations split by actor: providers must ensure AI systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format (Article 50(2)); deployers must inform exposed persons when operating emotion-recognition or biometric-categorisation systems (Article 50(3)) and must label deepfakes as artificially generated or manipulated (Article 50(4)). Article 50(4) also requires deployers who use an AI system to generate or manipulate text published to inform the public on matters of public interest to disclose that the text was artificially generated or manipulated; this disclosure duty does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences, or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for publishing it.
```

  - hallucinated: ['Article 50(1) disclosure of AI nature', 'Article 50(2) machine-readable marking of synthetic content', 'Article 50(3) deployer obligation to inform persons exposed to emotion-recognition or biometric-categorisation systems', 'Article 50(4) deepfake labelling and public-interest text disclosure duties', 'law enforcement carve-out from Article 50(4)', 'editorial control/human review exception from Article 50(4)']
  - rationale: The prediction correctly identifies the Article 5(1)(f) prohibition on emotion recognition in workplace and educational institutions with the medical/safety carve-out, matching the ground truth, but adds extensive unsupported claims about Article 50 transparency obligations (providers, deployers, deepfakes, synthetic content, editorial control) that are not part of the ground truth answers.

### live_answers:la_q73 — **-0.5** (MIXED)

**Q:** What conformity-assessment route applies to an AI system that is a safety component of a CE-marked medical device?

- **gold refs**: Annex I, Article 6
- **branch refs**: Article 43, Article 6, Article 27, Article 49

**A:**

```
Under Article 27, in addition to Article 26 baseline duties, deployers of certain Annex III high-risk AI systems must perform a Fundamental Rights Impact Assessment (FRIA) covering affected persons and specific fundamental rights risks. Annex I route (Article 6(1)): the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I AND that product must undergo a third-party conformity assessment under that sectoral legislation. Article 49 requires providers (and deployers that are public authorities) to register themselves and their high-risk AI system in the EU database (Article 71) before placing the system on the market or putting it into service.
```

  - missing: ['Article 43(3) specifying that for Section A Annex I products the provider follows the sectoral conformity assessment procedure with AI Act requirements assessed as part of that procedure (not a separate AI Act track)']
  - hallucinated: ['Article 27 FRIA requirement for deployers of Annex III systems', 'Article 49 registration obligation in the EU database']
  - rationale: The prediction correctly identifies the Annex I / Article 6(1) route (safety component + third-party conformity assessment), which matches the core ground truth, but also introduces incorrect/irrelevant claims about Article 27 FRIA obligations and Article 49 registration requirements that are not part of the ground truth answer about the conformity-assessment route.

### live_answers:la_q84 — **-0.5** (MIXED)

**Q:** An AI tool recommends oncology treatment regimens from clinical guidelines. What EU AI Act obligations does its provider face across the lifecycle?

- **gold refs**: Annex I, Annex III, Article 10, Article 13, Article 15, Article 16, Article 17, Article 19, Article 25, Article 49, Article 6, Article 9
- **branch refs**: Article 47, Article 16, Article 94, Article 71, Article 49, Article 80, Article 17

**A:**

```
Article 25(2) requires the initial provider and the new provider to cooperate along the value chain: the initial provider must make available the necessary information and provide the reasonably expected technical access and other assistance so that the new provider can meet its obligations, in particular the conformity assessment of high-risk AI systems. Article 25(4) is a separate duty: the high-risk provider and third-party suppliers of AI systems, tools, services, components or processes used in or integrated into a high-risk AI system must specify, by written agreement, the necessary information, capabilities, technical access and other assistance, except for third parties making tools, services, processes or components (other than general-purpose AI models) accessible to the public under a free and open-source licence. For general-purpose AI models, the one-third fine-tune rule (per the Commission's 18 July 2025 GPAI Guidelines, anchored on Article 51) makes the downstream modifier a new provider when additional training compute exceeds 1/3 of the base model's compute, or 1/3 of the 10^25 FLOPs systemic threshold (~3.3×10^24 FLOPs) when base compute is unknown. Requires the provider to draw up a written, machine-readable, signed and dated EU declaration of conformity for each high-risk AI system, containing the information in Annex V, kept at the disposal of national competent authorities for 10 years. Article 17 requires providers of high-risk AI systems to operate a quality management system covering regulatory-compliance strategy, design verification, examination + test procedures, post-market monitoring, and incident-reporting workflows.
```

  - missing: ['High-risk classification via Article 6(1)/Annex I (medical device regulation)', 'Article 9 risk-management system across lifecycle', 'Article 10 data governance requirements', 'Article 13 transparency and instructions for use', 'Article 15 accuracy, robustness, cybersecurity', 'Article 16 full provider duties (CE marking, conformity assessment, declaration of conformity, registration, corrective action)', 'Article 19 log retention minimum 6 months', 'Article 49 registration in EU database', 'Annex III does not cover medical treatment']
  - hallucinated: ["1/3 fine-tune rule from Commission's 18 July 2025 GPAI Guidelines anchored on Article 51", 'Article 25(4) written agreements with third-party suppliers', '10^25 FLOPs systemic threshold and 3.3×10^24 FLOPs downstream modifier threshold', '10-year retention period for EU declaration of conformity', 'Machine-readable, signed and dated EU declaration of conformity requirements']
  - rationale: The prediction correctly mentions Article 17 (quality management system) and Article 25 (cooperation obligations), which partially match gold answers, but introduces multiple hallucinated claims not supported by the ground truth or verbatim text: the '1/3 fine-tune rule' from 'Commission's 18 July 2025 GPAI Guidelines', Article 25(4) written agreements with third-party suppliers, Article 51 GPAI systemic threshold of 10^25 FLOPs, the 10-year retention period for the EU declaration of conformity, and machine-readable/signed/dated requirements for the declaration. The prediction also omits most gold answers (Articles 6(1)/Annex I classification, Article 9 risk management, Article 10 data governance, Article 13 transparency, Article 15 accuracy/robustness, Article 16 full provider duties, Article 19 log retention of 6 months, Article 49 registration).

### live_answers:la_q37 — **-1.0** (WRONG)

**Q:** When registering a high-risk AI system in the EU database under the EU AI Act, what specific information must the provider submit? List the required items.

- **gold refs**: Annex III, Annex VIII, Article 49, Article 71
- **branch refs**: Article 6, Article 71, Article 49, Article 26, Article 83, Article 66, Article 16

**A:**

```
The Commission shall, in collaboration with the Member States, set up and maintain an EU database containing information referred to in paragraphs 2 and 3 of this Article concerning high-risk AI systems referred to in Article 6(2) which are registered in accordance with Articles 49 and 60 and AI systems that are not considered as high-risk pursuant to Article 6(3) and which are registered in accordance with Article 6(4) and Article 49. When setting the functional specifications of such database, the Commission shall consult the relevant experts, and when updating the functional specifications of such database, the Commission shall consult the Board.
```

  - missing: ['Name, address and contact details of the provider', "Where submission is made by another person on the provider's behalf, that person's name, address and contact details", 'Name, address and contact details of the authorised representative, where applicable', "The AI system's trade name and any additional unambiguous reference allowing its identification and traceability", 'A description of the intended purpose of the AI system, and of the components and functions supported through it', 'A basic and concise description of the information used by the system (data, inputs) and its operating logic', 'The status of the AI system', "The type, number and expiry date of any certificate issued by a notified body, and that body's name or identification number, where applicable", 'A scanned copy of that certificate, where applicable', 'The Member States in which the system is or has been placed on the market, put into service or made available in the Union']
  - hallucinated: ['The Commission shall, in collaboration with the Member States, set up and maintain an EU database containing information referred to in paragraphs 2 and 3 of this Article concerning high-risk AI systems referred to in Article 6(2) which are registered in accordance with Articles 49 and 60 and AI systems that are not considered as high-risk pursuant to Article 6(3) and which are registered in accordance with Article 6(4) and Article 49.']
  - rationale: The prediction only quotes Article 71(1) about the Commission setting up the EU database, and does not list any of the required registration items from Annex VIII Section A that the ground truth requires.

### live_answers:la_q7 — **+0.5** (PARTIAL_CLEAN)

**Q:** We want to deploy an AI system that performs biometric verification solely to confirm that a specific natural person is the person he or she claims to be. Is this system prohibited? Is it high-risk?

- **gold refs**: Annex I, Annex III, Article 5, Article 50, Article 6
- **branch refs**: Article 5, Article 6, Article 50, Annex III, Annex I

**A:**

```
The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.
```

  - missing: ['Biometric verification used solely to confirm a natural person is who they claim to be is expressly carved out of the high-risk biometrics category in Annex III point 1(a), which excludes it from the remote biometric identification high-risk category']
  - rationale: The prediction correctly identifies the system is not prohibited under Article 5 and correctly notes the Article 6/Annex I safety-component route and Article 50 transparency duties, but critically omits the key Annex III carve-out explicitly excluding biometric verification from the high-risk biometrics category, which is the primary ground for the 'not high-risk' conclusion.

### live_answers:la_q35 — **-1.0** (WRONG)

**Q:** Consider the situation in which a market surveillance authority (MSA) determines that an AI system, originally classified as non-high-risk by the provider, is in fact high-risk. Does the provider need to recall and suspend the use of the system without undue delay, or does the MSA provide a timeframe within which the provider can take corrective actions? Or does this depend on the gravity of the situation?

- **gold refs**: Annex III, Article 79, Article 80
- **branch refs**: Article 74, Article 16, Article 6, Article 50, Annex III, Annex I, Article 11

**A:**

```
The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.
```

  - missing: ['Article 80 provides the operative procedure: MSA requires provider to take all necessary actions and corrective action within a period the MSA may prescribe', 'Article 79 applies if the system presents a risk to health/safety/fundamental rights, requiring corrective actions within 15 working days or MSA-prescribed period', 'Recall/suspension without undue delay is a consequence of non-compliance within the prescribed period (Art 79(5) via Art 80(6)), not the immediate default', 'The answer depends on the gravity: Art 79 applies for risk-presenting systems, Art 80 for reclassification scenarios']
  - hallucinated: ['Discussion of Article 5 prohibited practices (social scoring, facial-image scraping) is irrelevant to the enforcement/reclassification question asked', 'Discussion of Article 50 transparency duties is irrelevant to the question']
  - rationale: The predicted answer discusses Article 5 prohibited practices and Article 6 high-risk classification criteria, completely ignoring the actual question about MSA enforcement procedures under Articles 79 and 80 when an MSA reclassifies a provider's non-high-risk system as high-risk.

### live_answers:la_q2 — **+1.0** (FULLY_CORRECT)

**Q:** Does the obligation to indicate that deep-fakes are artificially generated apply when prosecuting a criminal offence?

- **gold refs**: Article 50
- **branch refs**: Article 50.4, Article 50

**A:**

```
No. Under Article 50(4), the deployer's duty to disclose that image, audio, or video content constituting a deep fake has been artificially generated or manipulated does not apply where the use is authorised by law to detect, prevent, investigate, or prosecute criminal offences. Absent that law-enforcement authorisation, the deployer must disclose that the content is a deep fake.
```

  - rationale: The prediction correctly states that Article 50(4) lifts the deepfake disclosure obligation where use is authorised by law to detect, prevent, investigate, or prosecute criminal offences, matching the ground truth fully.

### live_answers:la_q52 — **-0.5** (MIXED)

**Q:** Can you help me understand AI compliance?

- **gold refs**: Article 17, Article 56
- **branch refs**: Article 111, Article 8, Article 86

**A:**

```
Under Article 111, transitional provisions grandfather pre-existing AI systems and GPAI models on the market before key dates unless they undergo a substantial change in design; high-risk systems for public-authority use comply from 2 August 2030. Under Article 86, any affected person subject to a decision based on output from an Annex III high-risk AI system has the individual right to obtain a clear and meaningful explanation of the AI system's role in the decision-making procedure. Transitional provisions for AI systems and GPAI models already on the market / in service: high-risk AI for public-authority use placed on the market before 2 August 2026 must comply from 2 August 2030 (only if significant design change); pre-2 August 2025 GPAI models brought into compliance by 2 August 2027; large-scale IT systems listed in Annex X covered by the Regulation from 31 December 2030.
```

  - missing: ['Article 17 quality management system as the central obligation for high-risk AI systems covering regulatory-compliance strategy, design verification, testing, post-market monitoring, and incident-reporting', 'Article 56 AI Office facilitating voluntary codes of practice for GPAI providers', 'GPAI Code of Practice published on 10 July 2025 letting signatories demonstrate adequate compliance until harmonised standards exist', "Commission's 18 July 2025 guidelines on the 10^23 and 10^25 FLOPs thresholds"]
  - hallucinated: ['Article 86 right to explanation for affected persons subject to Annex III high-risk AI system decisions', 'Detailed Article 111 transitional provisions (pre-2026 high-risk systems, 2030 public-authority deadline, 2027 GPAI deadline, Annex X large-scale IT systems)']
  - rationale: The prediction correctly covers Article 56 (codes of practice for GPAI) and Article 17 (quality management system) only partially — it mentions Article 56 indirectly but misses the core gold answers about Article 17 QMS obligations and the GPAI Code of Practice (10 July 2025) and Commission guidelines (18 July 2025, FLOPs thresholds). It also introduces incorrect/hallucinated claims not in the ground truth: Article 86 right to explanation and detailed transitional provisions from Article 111 (which are not part of the ground truth answers).

### live_answers:la_q13 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under what conditions should providers of general-purpose AI models be subject to exceptions regarding transparency-related requirements, if any? And what do those exceptions not cover?

- **gold refs**: Annex XI, Annex XII, Article 51, Article 53, Article 55
- **branch refs**: Article 53, Article 50.1, Article 16, Article 55, Article 51, Article 56, Article 25

**A:**

```
This exception shall not apply to general-purpose AI models with systemic risks.
```

  - missing: ['The exception covers only Articles 53(1)(a) and (b) — technical documentation and downstream provider information', 'Articles 53(1)(c) (copyright policy) and 53(1)(d) (training summary) still apply to open-source providers', 'For systemic-risk models the full Article 53 documentation obligations apply regardless of licence', 'Systemic-risk models also face Article 55 obligations: adversarial testing, systemic-risk assessment/mitigation, serious-incident reporting, and cybersecurity']
  - rationale: The prediction correctly identifies that the open-source exception does not apply to systemic-risk models, which is one of the Ground Truth claims, but omits all other required elements: the scope of the exception (Articles 53(1)(a) and (b) only), what obligations remain (copyright policy under 53(1)(c) and training summary under 53(1)(d)), and the additional Article 55 obligations for systemic-risk models.

### live_answers:la_q82 — **-0.5** (MIXED)

**Q:** Classify the EU AI Act risk tier of a consumer wellness chatbot that gives general lifestyle tips and makes no medical claims.

- **gold refs**: Annex I, Article 50, Article 6
- **branch refs**: Article 50, Article 6, Article 42, Article 49

**A:**

```
Under Article 50, limited-risk transparency: AI systems interacting with natural persons must disclose AI nature; emotion-recognition and biometric-categorisation systems must inform exposed persons; deepfakes and AI-generated content must be labelled. Eight high-risk use-case categories: biometrics, critical infrastructure, education + vocational training, employment + worker management (recruitment, task allocation, promotion and termination decisions, and performance evaluation affecting workers' fundamental rights), essential private + public services, law enforcement, migration + asylum + border control, and administration of justice + democratic processes. Classifies an AI system as high-risk on two routes.
```

  - missing: ['Explicit conclusion that the chatbot does not meet either route to high-risk classification under Article 6', 'Explicit statement that it is not a safety component of, nor itself, a product covered by Annex I Union harmonisation legislation', 'Explicit statement that the Article 6(1) route is not engaged']
  - hallucinated: ['Article 50 transparency obligations for AI systems interacting with natural persons', 'Eight high-risk use-case categories including biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration, and justice']
  - rationale: The prediction partially addresses Article 6(1) by mentioning two routes to high-risk classification, which aligns with the ground truth, but it does not specifically conclude that the wellness chatbot falls outside high-risk classification, and it introduces numerous claims (Article 50 transparency obligations, eight high-risk categories, biometrics, law enforcement, etc.) that are not part of the ground truth answer and constitute hallucinated/irrelevant content.

### live_answers:la_q72 — **-0.5** (MIXED)

**Q:** What must the provider of a high-risk AI medical diagnostic system put in place before placing it on the market?

- **gold refs**: Annex IV, Article 10, Article 11, Article 16, Article 8, Article 9
- **branch refs**: Article 6, Article 16, Article 43, Article 8, Article 9, Article 10, Article 11

**A:**

```
Providers of a high-risk AI system listed in Annex III are bound by Article 6, Article 8, and Article 9 (plus follow-on obligations summarised in the references list). Under Article 16, Providers of high-risk AI systems must ensure the system meets the Chapter III Section 2. Article 43 requires providers of high-risk AI to undergo a conformity assessment: internal-control. Article 10 requires training, validation, and test datasets to be relevant, representative.
```

  - missing: ['The explicit requirement to draw up technical documentation before placement on the market demonstrating conformity containing Annex IV content (Article 11)']
  - hallucinated: ['Article 6 as a binding obligation for providers', 'Article 43 conformity assessment requirement (internal-control procedure)']
  - rationale: The prediction correctly references Article 16 (provider duties including Section 2 compliance and identifying details), Article 9 (risk management system), Article 10 (data governance/datasets), and Article 11/technical documentation, matching several gold answers; however, it introduces incorrect claims not in the ground truth, specifically mentioning Article 6 and Article 43 conformity assessment (internal-control) which are not part of the ground truth answers.

### live_answers:la_q11 — **-0.5** (MIXED)

**Q:** What is the meaning and purpose of 'testing data' in the context of AI systems, and why is it important that it is not leaked during the training process?

- **gold refs**: Article 10
- **branch refs**: Article 3.32, Article 10

**A:**

```
Testing data is defined in Article 3(32) as data used to provide an independent evaluation of the AI system, in order to confirm its expected performance before it is placed on the market or put into service. It must be kept separate from the training and validation data so that this evaluation is genuinely independent. If testing data leaks into the training process, the system is in effect assessed on data it has already seen, which inflates its apparent performance and defeats the purpose of the independent check that Article 10 requires for the datasets of a high-risk AI system.
```

  - hallucinated: ['If testing data leaks into the training process, the system is assessed on data it has already seen, which inflates its apparent performance and defeats the purpose of the independent check']
  - rationale: The prediction correctly identifies testing data as held-out data for independent evaluation of unseen examples (matching the ground truth), but adds an unsupported claim that testing data leaking into training 'inflates apparent performance and defeats the purpose of the independent check' — this causal mechanism is not stated in the verbatim text or ground truth.

### live_answers:la_q10 — **-1.0** (WRONG)

**Q:** Which article of the EU AI Act governs human oversight measures?

- **gold refs**: Article 14
- **branch refs**: Article 14, Article 2, Article 1

**A:**

```
Defines 68 terms used in the Regulation, including 'AI system' (machine-based, varying autonomy, possibly adaptive, inferring from input how to generate output influencing physical/virtual environments), 'provider', 'deployer', 'placing on the market', 'putting into service', 'substantial modification', 'general-purpose AI model', 'general-purpose AI system', 'systemic risk'. Scope: applies to providers placing AI systems on the EU market regardless of establishment, deployers established in the EU, providers/deployers in third countries whose output is used in the EU. Excludes military/defence/national-security uses, scientific R&D, purely personal non-professional use, and free/open-source AI systems outside the high-risk + prohibited + transparency scope.
```

  - missing: ['Article 14 governs human oversight, requiring high-risk AI systems to be designed so they can be effectively overseen by natural persons during use, through appropriate human-machine interface tools.']
  - hallucinated: ["Defines 68 terms including 'AI system', 'provider', 'deployer', etc.", 'Scope: applies to providers placing AI systems on the EU market regardless of establishment, deployers established in the EU, etc.', 'Excludes military/defence/national-security uses, scientific R&D, purely personal non-professional use, and free/open-source AI systems outside high-risk + prohibited + transparency scope.']
  - rationale: The predicted answer describes Article 3 (definitions) and Article 2 (scope) content, making no mention of Article 14 or human oversight measures, which is the sole ground truth answer.

### live_answers:la_q67 — **-0.5** (MIXED)

**Q:** What does the EU AI Act require for an AI system that evaluates patients' eligibility for public healthcare benefits?

- **gold refs**: Annex III, Article 6
- **branch refs**: Article 6, Annex III, Article 5, Annex I

**A:**

```
Eight high-risk use-case categories: biometrics, critical infrastructure, education + vocational training, employment + worker management (recruitment, task allocation, promotion and termination decisions, and performance evaluation affecting workers' fundamental rights), essential private + public services, law enforcement, migration + asylum + border control, and administration of justice + democratic processes. Classifies an AI system as high-risk on two routes. Annex I route (Article 6(1)): the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I AND that product must undergo a third-party conformity assessment under that sectoral legislation.
```

  - missing: ['Explicit statement that the system falls within Annex III category 5(a) - essential public services - covering evaluation of eligibility for public healthcare benefits, classified as high-risk under Article 6(2)']
  - hallucinated: ['The Annex I route (Article 6(1)) discussion about safety components and third-party conformity assessment is presented as relevant to this question, but the ground truth only covers the Annex III route']
  - rationale: The prediction correctly identifies the Annex III route and Article 6(2) classification, but it cuts off mid-sentence and fails to explicitly state that evaluating patients' eligibility for public healthcare benefits falls under Annex III point 5(a) as high-risk. It also introduces incorrect/irrelevant content about the Annex I route (Article 6(1)) which is not part of the ground truth answer for this question.

### live_answers:la_q53 — **-0.5** (MIXED)

**Q:** We are building a chatbot for customer support. What do we need to know?

- **gold refs**: Annex I, Annex III, Annex XI, Annex XII, Article 25, Article 51, Article 53, Article 55, Article 6
- **branch refs**: Article 50, Article 25, Article 29

**A:**

```
Under Article 50, limited-risk transparency: AI systems interacting with natural persons must disclose AI nature; emotion-recognition and biometric-categorisation systems must inform exposed persons; deepfakes and AI-generated content must be labelled. Article 25(2) requires the initial provider and the new provider to cooperate along the value chain: the initial provider must make available the necessary information and provide the reasonably expected technical access and other assistance so that the new provider can meet its obligations, in particular the conformity assessment of high-risk AI systems. Article 25(4) is a separate duty: the high-risk provider and third-party suppliers of AI systems, tools, services, components or processes used in or integrated into a high-risk AI system must specify, by written agreement, the necessary information, capabilities, technical access and other assistance, except for third parties making tools, services, processes or components (other than general-purpose AI models) accessible to the public under a free and open-source licence. For general-purpose AI models, the one-third fine-tune rule (per the Commission's 18 July 2025 GPAI Guidelines, anchored on Article 51) makes the downstream modifier a new provider when additional training compute exceeds 1/3 of the base model's compute, or 1/3 of the 10^25 FLOPs systemic threshold (~3.3×10^24 FLOPs) when base compute is unknown. Under Article 50, Transparency obligations split by actor: providers must ensure AI systems interacting.
```

  - missing: ['Customer support chatbot is not high-risk by default as it falls outside all eight Annex III categories', 'Article 6 high-risk classification via Annex I product-safety route or Annex III use-case route', 'Article 6(3) exception for narrow procedural/preparatory tasks without profiling', 'Article 53 duties for GPAI model providers (Annex XI technical documentation, Annex XII downstream information, copyright policy, public training-data summary)', 'Article 51 systemic-risk threshold of 10^25 FLOPs', 'Operator obligations turn on repurposing toward Annex III function or taking on provider role by branding/substantially modifying underlying model']
  - hallucinated: ['Article 50 transparency obligations for AI systems interacting with natural persons, emotion recognition, deepfakes', "One-third fine-tune rule from Commission's 18 July 2025 GPAI Guidelines", '~3.3×10^24 FLOPs threshold for downstream modifiers becoming new providers']
  - rationale: The prediction correctly mentions Article 25 value-chain obligations (matching part of the ground truth), but introduces multiple incorrect/hallucinated claims: Article 50 transparency obligations (not in ground truth), the 'one-third fine-tune rule' from alleged Commission GPAI Guidelines (not in the verbatim text or ground truth), and the ~3.3×10^24 FLOPs threshold for downstream modifiers. It also misses key ground truth points: that a customer support chatbot is not high-risk by default, the eight Annex III categories, Article 6 classification analysis, Article 53 GPAI provider duties (Annex XI, XII, copyright policy, training-data summary), and the Article 51 10^25 FLOPs systemic-risk threshold.

### live_answers:la_q1 — **+1.0** (FULLY_CORRECT)

**Q:** Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?

- **gold refs**: Annex IV, Article 11
- **branch refs**: Article 11, Annex IV

**A:**

```
Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).
```

  - rationale: The prediction correctly identifies both Annex IV 1(e) (hardware description) and Annex IV 2(c) (computational resources) as well as Article 11's requirement to draw up documentation before market placement containing Annex IV information, matching all ground truth claims.

### live_answers:la_q46 — **-0.5** (MIXED)

**Q:** Is an AI system that recommends recipes high risk?

- **gold refs**: Annex I, Annex III, Article 5, Article 6
- **branch refs**: Article 6, Article 50, Annex III, Annex I

**A:**

```
The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.
```

  - hallucinated: ['Subject mainly to Article 50 transparency duties where it interacts directly with people']
  - rationale: The prediction correctly identifies that recipe recommendation is not banned under Article 5 and does not fall under Annex III or Annex I (Article 6), matching the core ground truth claims, but adds an incorrect additional claim about Article 50 transparency duties applying, which is not part of the ground truth answer and introduces a hallucinated obligation not supported by the ground truth.

### live_answers:la_q19 — **+0.5** (PARTIAL_CLEAN)

**Q:** What is a deep fake according to the EU AI Act?

- **gold refs**: Article 50
- **branch refs**: Article 3.60, Article 50

**A:**

```
AI-generated or manipulated image, audio or video content that resembles existing persons, objects, places, entities or events and would falsely appear to a person to be authentic or truthful.
```

  - missing: ['The practical consequence in Article 50 requiring deployers to disclose artificially generated/manipulated content as a deepfake (Article 50(4)) and providers to mark outputs in machine-readable format detectable as artificially generated (Article 50(2)).']
  - rationale: The prediction correctly matches the Article 3.60 definition of 'deep fake' verbatim, but omits the practical consequence described in the Ground Truth regarding Article 50(4) disclosure obligations and Article 50(2) machine-readable marking requirements.

### live_answers:la_q78 — **-0.5** (MIXED)

**Q:** A pharma company trains a large foundation model for drug discovery whose training compute exceeds 10^25 FLOPs. Which EU AI Act obligations apply?

- **gold refs**: Annex III, Article 25, Article 3, Article 51, Article 6
- **branch refs**: Article 51, Article 25

**A:**

```
Under Article 51, a GPAI model has systemic risk when cumulative training compute exceeds 10²⁵ FLOPs (10^25); providers must notify the Commission within two weeks of meeting the threshold. Classifies a general-purpose AI model as having 'systemic risk' when it has high-impact capabilities (presumed when cumulative training compute exceeds 10^25 FLOPs) or when so designated by the Commission based on Annex XIII criteria. Commission's 18 July 2025 GPAI Guidelines presume a model is general-purpose (Article 3(63)) when training compute exceeds 10^23 FLOPs and the model can generate language, image, audio, or video output. Fine-tuned or modified models become new providers under Article 25 when their additional training compute exceeds one-third of the base model's compute (or one-third of the 10^25 systemic threshold, ~3.3×10^24 FLOPs, when base compute is unknown). Defines 68 terms used in the Regulation, including 'AI system' (machine-based, varying autonomy, possibly adaptive, inferring from input how to generate output influencing physical/virtual environments), 'provider', 'deployer', 'placing on the market', 'putting into service', 'substantial modification', 'general-purpose AI model', 'general-purpose AI system', 'systemic risk'.
```

  - missing: ['High-risk obligations in Articles 9–15 and conformity/registration/documentation duties only arise if the model is integrated into a system qualifying as high-risk under Article 6, which the stated facts do not establish', 'The pharma company assumes Chapter V GPAI obligations, not Chapter III high-risk obligations']
  - hallucinated: ['Providers must notify the Commission within two weeks of meeting the 10^25 FLOPs threshold', 'Fine-tuned models become new providers when additional compute exceeds one-third of the systemic threshold (~3.3×10^24 FLOPs when base compute is unknown) — ground truth says one-third of base compute, not one-third of systemic threshold']
  - rationale: The prediction correctly identifies the 10^25 FLOPs systemic risk threshold under Article 51 and the GPAI classification, but includes several incorrect claims: (1) a 'two-week notification to the Commission' obligation upon meeting the threshold (not in the ground truth or supplied text); (2) the one-third threshold applied to the systemic threshold (~3.3×10^24) rather than to the base model's compute as stated in the ground truth; (3) Article 25 is cited for GPAI fine-tuning provider obligations, but Article 25 in the supplied text only addresses high-risk AI systems, not GPAI models — the ground truth attributes the one-third rule to the Commission's 18 July 2025 GPAI Guidelines anchored on Article 51, not Article 25 directly for GPAI; (4) the prediction omits the key point that Chapter III high-risk obligations do not apply unless the model is integrated into a high-risk system under Article 6.

### live_answers:la_q21 — **-0.5** (MIXED)

**Q:** If a provider of a high-risk AI system confirms that the system achieves an appropriate level of accuracy, robustness, and cybersecurity at the time of development, then no further action is required by the provider on these aspects in the future. Correct?

- **gold refs**: Article 15
- **branch refs**: Article 6, Article 15, Article 13, Article 16, Article 17, Article 43, Article 50

**A:**

```
Under Article 50, limited-risk transparency duties under Article 50 apply cumulatively with Article 13 high-risk transparency duties; both apply to the same system, not in the alternative. Requires appropriate levels of accuracy, robustness, and cybersecurity across the lifecycle, accuracy metrics declared in instructions for use, resilience against errors, and resistance to data-poisoning, evasion, model-confidentiality, and adversarial attacks. Requires high-risk AI systems to be designed for sufficient operational transparency to deployers, accompanied by instructions for use covering provider identity, intended purpose, capabilities + limitations, expected lifetime, human-oversight measures, and required maintenance.
```

  - missing: ['The statement that no further action is required is incorrect — Article 15 imposes a continuing obligation throughout the lifecycle, not merely at development']
  - hallucinated: ['Article 50 limited-risk transparency duties apply cumulatively with Article 13 high-risk transparency duties; both apply to the same system, not in the alternative']
  - rationale: The prediction correctly references lifecycle accuracy/robustness/cybersecurity requirements and resilience against errors and attacks (matching parts of the ground truth), but it opens with an irrelevant and incorrect claim about Article 50 transparency duties applying cumulatively with Article 13, which is not in the ground truth and is a hallucinated claim.

### live_answers:la_q29 — **-1.0** (WRONG)

**Q:** Under the EU AI Act, which specific AI systems are explicitly listed as high-risk because they make decisions in critical life- and health-related situations involving emergency calls and triage?

- **gold refs**: Article 6, Annex III
- **branch refs**: Article 9, Article 27, Article 46

**A:**

```
Under Article 27, in addition to Article 26 baseline duties, deployers of certain Annex III high-risk AI systems must perform a Fundamental Rights Impact Assessment (FRIA) covering affected persons and specific fundamental rights risks. Derogation from the conformity-assessment procedure: by way of derogation from Article 43, a market-surveillance authority may authorise the placing on the market or putting into service of specific high-risk AI systems within the territory of the Member State concerned, for exceptional reasons of public security or the protection of life and health of persons, environmental protection, or the protection of key industrial and infrastructural assets (Article 46(1)). Article 9 requires a documented, iterative risk-management system across the AI system's lifecycle.
```

  - missing: ['Annex III point 5(d) explicitly lists AI systems for evaluating/classifying emergency calls and dispatching emergency first response services and emergency healthcare patient triage systems as high-risk', 'Classification is via the Annex III route of Article 6(2)', "These fall within the 'essential private and public services' category", 'Classification triggers Chapter III requirements including Article 10 data-governance duties (relevant, representative, error-free, complete datasets with documented provenance and bias mitigation)']
  - hallucinated: ['Discussion of FRIA obligations under Article 27 as the answer to the question', 'Article 46 derogation procedure as the answer to the question', 'Article 9 risk management system as the answer to the question']
  - rationale: The prediction discusses FRIAs (Article 27), derogations (Article 46), and risk management (Article 9) but never identifies the specific AI systems listed in Annex III point 5(d) — systems that evaluate/classify emergency calls or dispatch emergency first response services and emergency healthcare patient triage systems — nor does it address the Annex III route of Article 6(2) or the Article 10 data-governance duties that the ground truth requires.

### live_answers:la_q36 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under the EU AI Act, what presumption applies when a high-risk AI system is trained and tested on data that reflects the specific geographical, behavioural, contextual or functional setting in which it is intended to be used?

- **gold refs**: Article 10, Article 42
- **branch refs**: Article 6, Article 42, Article 10

**A:**

```
Adds two further presumptions of conformity beyond Articles 40-41: Article 42(1), high-risk AI systems trained and tested on data reflecting the specific geographical, behavioural, contextual, or functional setting in which they are intended to be used are presumed to comply with the relevant data-governance requirements of Article 10(4); Article 42(2), high-risk AI systems certified or for which a statement of conformity has been issued under a cybersecurity scheme under Regulation (EU) 2019/881 (the Cybersecurity Act) and whose references are published in the Official Journal are presumed to comply with the cybersecurity requirements of Article 15 to the extent the cybersecurity certificate or statement covers those requirements.
```

  - missing: ["The clarification that this is a rebuttable presumption that eases the provider's demonstration of compliance, not an exemption from the underlying Article 10 data-governance duties"]
  - rationale: The prediction correctly identifies the Article 42(1) presumption that high-risk AI systems trained and tested on data reflecting the specific geographical, behavioural, contextual, or functional setting are presumed to comply with Article 10(4), matching the core gold answer, but omits the ground truth's clarification that this is a rebuttable presumption easing the provider's demonstration of compliance (not an exemption from Article 10 duties), and the additional Article 42(2) cybersecurity presumption is extra information not in the ground truth but not incorrect per se — however the ground truth only asks about the Article 42(1) presumption, and the prediction includes Article 42(2) which is not part of the ground truth answer.

### live_answers:la_q43 — **+0.5** (PARTIAL_CLEAN)

**Q:** Under Article 10(5) of the EU AI Act, when may a provider of a high-risk AI system process special categories of personal data for bias detection and correction, and what key safeguards/conditions must be met?

- **gold refs**: Article 10
- **branch refs**: Article 10.5, Article 10

**A:**

```
Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict, documented access controls to prevent misuse (c); no transmission or transfer to other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).
```

  - missing: ['This permission operates within the wider data-governance regime of Article 10.']
  - rationale: The prediction correctly covers the 'strictly necessary' threshold and the six conditions from Article 10(5), but omits the ground truth's specific point that the permission operates within the wider data-governance regime of Article 10 (i.e., the explicit reference to the broader Article 10 framework context).

### live_answers:la_q17 — **+0.5** (PARTIAL_CLEAN)

**Q:** How does Annex II relate to prohibited uses of AI systems?

- **gold refs**: Annex II, Article 5
- **branch refs**: Annex II

**A:**

```
List of criminal offences referred to in Article 5(1)(h) permitting real-time remote biometric identification by law enforcement: terrorism, trafficking in human beings, sexual exploitation of children, illicit trafficking in narcotic drugs / weapons / nuclear material, murder, kidnapping, rape, armed robbery, organised crime, participation in a criminal organisation, environmental crime, provided the offence is punishable in the relevant Member State by a custodial sentence of at least 4 years.
```

  - missing: ['Annex II functions as a definitional list that narrows one of the exceptions to a prohibited practice; it does not itself prohibit anything', 'Article 5 prohibits real-time remote biometric identification in publicly accessible spaces by law enforcement, subject to exhaustively listed exceptions']
  - rationale: The prediction correctly identifies that Annex II lists criminal offences referenced in Article 5(1)(h)(iii) permitting real-time remote biometric identification by law enforcement for locating/identifying suspects, with the 4-year custodial sentence threshold, but omits the key ground truth point that Annex II is a definitional/exception list that does not itself prohibit anything, and misses the framing that Article 5 is the prohibition provision while Annex II merely narrows one exception to that prohibition.

### live_answers:la_q22 — **-0.5** (MIXED)

**Q:** What are all the risk categories in the EU AI Act?

- **gold refs**: Article 5
- **branch refs**: Article 5, Article 6, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56

**A:**

```
The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems have no mandatory duties under the Act, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.
```

  - hallucinated: ['limited-risk systems with Article 50 transparency duties as a named risk category', 'minimal-risk systems with no mandatory duties as a named risk category']
  - rationale: The prediction correctly identifies the unacceptable-risk tier (Article 5 prohibited practices) and high-risk systems (Article 6), which matches the Ground Truth, but also adds 'limited-risk' and 'minimal-risk' as distinct categories not supported by the verbatim text provided, constituting hallucinated claims.

### live_answers:la_q65 — **-0.5** (MIXED)

**Q:** Which EU AI Act article sets the transparency obligation for a patient-facing medical chatbot?

- **gold refs**: Article 50
- **branch refs**: Article 50.1, Article 13

**A:**

```
Under Article 50, limited-risk transparency duties under Article 50 apply cumulatively with Article 13 high-risk transparency duties; both apply to the same system, not in the alternative. Transparency obligations split by actor: providers must ensure AI systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format (Article 50(2)); deployers must inform exposed persons when operating emotion-recognition or biometric-categorisation systems (Article 50(3)) and must label deepfakes as artificially generated or manipulated (Article 50(4)). Article 50(4) also requires deployers who use an AI system to generate or manipulate text published to inform the public on matters of public interest to disclose that the text was artificially generated or manipulated; this disclosure duty does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences, or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for publishing it.
```

  - hallucinated: ['Article 13 high-risk transparency duties apply cumulatively with Article 50 to the same system', 'Article 50(3) deployer obligations for emotion-recognition/biometric-categorisation systems', 'Article 50(4) deepfake labeling obligations for deployers', 'Article 50(4) text disclosure obligations for public interest content']
  - rationale: The prediction correctly identifies Article 50(1) as the transparency obligation for a patient-facing chatbot and Article 50(2) for synthetic content marking, matching both ground truth answers, but also introduces incorrect additional claims (Article 13 high-risk transparency duties applying cumulatively, Article 50(3) deployer obligations for emotion recognition, Article 50(4) deepfake labeling) that are not part of the ground truth answers for this question.

### live_answers:la_q71 — **-0.5** (MIXED)

**Q:** A hospital deploys a high-risk AI diagnostic system. What are its obligations as a deployer under the EU AI Act?

- **gold refs**: Annex III, Article 13, Article 25, Article 26, Article 27, Article 86
- **branch refs**: Article 26, Article 27, Article 13, Article 86, Article 14, Article 9, Article 6

**A:**

```
Under Article 27, in addition to Article 26 baseline duties, deployers of certain Annex III high-risk AI systems must perform a Fundamental Rights Impact Assessment (FRIA) covering affected persons and specific fundamental rights risks. Under Article 86, any affected person subject to a decision based on output from an Annex III high-risk AI system has the individual right to obtain a clear and meaningful explanation of the AI system's role in the decision-making procedure. Deployers of a high-risk AI system listed in Annex III are bound by Article 26, Article 27, and Article 13 (plus follow-on obligations summarised in the references list). Article 14 requires effective human oversight by natural persons during system use, capability + limitation awareness, automation-bias safeguards, ability to interpret output, disregard / override / intervene, and (for biometric identification) a two-person verification rule.
```

  - missing: ['The hospital only becomes a provider under Article 25 if it puts its own name/trademark on the system, substantially modifies it, or changes its intended purpose; otherwise provider-side design/conformity/CE-marking obligations do not fall on the hospital']
  - hallucinated: ['Article 14 imposes deployer duties including automation-bias safeguards, ability to interpret output, disregard/override/intervene capability, and a two-person biometric verification rule — Article 14 is a provider-side design requirement, not a deployer obligation']
  - rationale: The prediction correctly covers Article 26 duties, Article 27 FRIA, Article 86 explanation right, and Article 13 instructions, but incorrectly attributes Article 14 human oversight obligations (automation-bias safeguards, ability to interpret output, disregard/override/intervene, two-person biometric verification rule) as deployer duties, when Article 14 is a provider-side design obligation; additionally the prediction omits the key ground-truth point that the hospital must become a provider under Article 25 only in specific circumstances (own name/trademark, substantial modification, change of intended purpose).

### live_answers:la_q32 — **-0.5** (MIXED)

**Q:** Is an AI system used to detect decision-making patterns or deviations for a use case listed in Annex III considered high-risk?

- **gold refs**: Annex III, Article 6
- **branch refs**: Article 6.3, Article 6, Annex III

**A:**

```
Not automatically. Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.
```

  - missing: ["High-risk classification turns on the system's use-case area rather than its analytical technique; detecting decision-making patterns is not itself a classifying criterion", 'The system inherits high-risk classification because and only to the extent that the use case it serves is listed in Annex III', 'The prohibition tier does not apply; the system is classified under Article 6 rather than banned']
  - hallucinated: ["The system is 'not automatically' high-risk even within an Annex III use case — framing the exemption as the default rather than a derogation from the default high-risk classification"]
  - rationale: The prediction correctly identifies Article 6(3)(c) as a potential exemption and the profiling carve-out, but incorrectly states the system is 'not automatically' high-risk, contradicting the Ground Truth which states it IS high-risk when operating within an Annex III use case (with the exemption being a separate derogation requiring documentation under Art 6(4)), and the prediction omits the key Ground Truth point that the analytical technique (detecting patterns) is not itself the classifying criterion — the use-case area is.

### live_answers:la_q55 — **-0.5** (MIXED)

**Q:** hi, what can you do?

- **gold refs**: (none)
- **branch refs**: (none)

**A:**

```
I am Lexy, a Compliance assistant that can answer your questions related to the EU AI Act, based on my Knowledge Graph and ontology. What can I help you with?
```

  - missing: ['Mention of specific example questions like Article 13 or Article 26']
  - hallucinated: ["Named 'Lexy'", "References a 'Knowledge Graph and ontology'"]
  - rationale: The prediction correctly states it answers EU AI Act questions (matching part of the gold answer), but adds incorrect/unsupported claims about a 'Knowledge Graph and ontology' and identifies itself as 'Lexy' which are not in the ground truth.

### live_answers:la_q77 — **-0.5** (MIXED)

**Q:** Does the EU AI Act require post-market monitoring and serious-incident reporting for an AI-based patient-monitoring device, and under which articles?

- **gold refs**: Article 72, Article 73, Article 3
- **branch refs**: Article 72.1, Article 72.4, Article 73.9, Article 73.1

**A:**

```
Yes. An AI-based patient-monitoring device is high-risk under Article 6(1) where it is a safety component of, or is itself, a medical device covered by the Medical Devices Regulation listed in Annex I Section A and that device must undergo third-party conformity assessment. As a high-risk system, the provider must establish and document a post-market monitoring system that actively collects and analyses performance data throughout the system's lifetime to evaluate continuous compliance, based on a post-market monitoring plan forming part of the technical documentation (Article 72(1) to (3), Annex IV). Article 72(4) permits the provider to integrate those elements into the post-market surveillance system already required under the Medical Devices Regulation rather than maintaining a parallel one. For serious incident reporting, Article 73 applies, but Article 73(9) narrows the AI Act reporting duty for high-risk systems covered by Union legislation with equivalent reporting obligations: notification is limited to serious incidents consisting of an infringement of Union law protecting fundamental rights, reported to the market surveillance authority of the Member State where the incident occurred, while incidents involving death or serious deterioration of health route through the medical-device vigilance framework instead.
```

  - missing: ['Article 73 tiered deadlines: immediately/≤2 days for widespread infringement or critical-infrastructure disruption, ≤10 days for death, ≤15 days for other serious incidents', 'Article 3(49) definition of serious incident including death, serious irreversible critical-infrastructure disruption, fundamental-rights violation, or serious property or environmental harm']
  - hallucinated: ['Article 73(9) applies to medical device AI systems (it is Article 73(10) that specifically covers medical device safety components)', 'Death and serious health harm incidents route entirely through the MDR vigilance framework rather than also through Article 73 of the AI Act']
  - rationale: The prediction correctly identifies Articles 72 and 73 and their core requirements, but incorrectly states that Article 73(9) applies to medical devices (it applies to Annex III systems with equivalent reporting obligations), whereas Article 73(10) specifically covers medical devices — and the prediction misattributes the narrowing provision. Additionally, the prediction incorrectly states the tiered deadlines from Article 73 are not applicable (routing death/health incidents entirely to the MDR framework), contradicting the Ground Truth which specifies the 2-day, 10-day, and 15-day deadlines under Article 73 apply. Some correct elements (Articles 72 and 73, post-market monitoring requirements) are present alongside incorrect claims about Article 73(9) applicability and the exclusion of death/serious harm reporting under the AI Act.

### live_answers:la_q86 — **+0.5** (PARTIAL_CLEAN)

**Q:** What does the EU AI Act require for an AI system used for risk assessment and pricing in health insurance?

- **gold refs**: Annex III, Article 6
- **branch refs**: Article 6, Annex III.5, Annex I

**A:**

```
Classifies an AI system as high-risk on two routes. Annex I route (Article 6(1)): the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I AND that product must undergo a third-party conformity assessment under that sectoral legislation. Annex III route (Article 6(2)): the system falls within one of the eight Annex III use cases.
```

  - missing: ['Explicit identification of Annex III.5(c) as the specific provision covering risk assessment and pricing in health insurance']
  - rationale: The prediction correctly identifies the Annex III route (Article 6(2)) as the classification path for health insurance risk assessment and pricing AI systems, matching the ground truth, but omits the specific Annex III.5(c) listing and instead generically describes 'eight Annex III use cases' without specifying the health insurance use case; it also adds the Annex I route (Article 6(1)) which is not incorrect per se but is not part of the ground truth answer for this specific question.

### live_answers:la_q27 — **+1.0** (FULLY_CORRECT)

**Q:** How are AI systems intended to influence the outcome of an election or referendum classified, and what exception is given for certain campaign-related tools?

- **gold refs**: Annex III
- **branch refs**: Article 6, Annex III.8

**A:**

```
Under Annex III point 8(b), AI systems intended to influence the outcome of an election or referendum, or the voting behaviour of natural persons in exercising their vote, are high-risk under Article 6(2). Annex III point 8(b) itself excludes systems to whose output natural persons are not directly exposed, such as tools used only to organise, optimise or structure political campaigns from an administrative or logistical point of view, which therefore fall outside this high-risk category.
```

  - rationale: The prediction correctly identifies Annex III point 8(b) high-risk classification under Article 6(2) for election/referendum influence systems, and accurately states the exception for tools not directly exposing natural persons to their output (administrative/logistical political campaign tools), matching all ground truth claims.

### live_answers:la_q63 — **-1.0** (WRONG)

**Q:** What are the algorithmic transparency obligations for a Very Large Online Platform content-moderation AI?

- **gold refs**: Article 50
- **branch refs**: (none)

**A:**

```
This question is about the Digital Services Act (DSA), not the EU AI Act (Regulation 2024/1689). This assistant only covers EU AI Act questions; consult the Digital Services Act (DSA) for the applicable rules.
```

  - missing: ['Article 50(1) notification duty applies only if the moderation tool interacts conversationally with users', 'Article 50(2) synthetic-content marking duty applies only if the tool generates or manipulates content rather than classifying existing posts']
  - hallucinated: ['The question is about the DSA, not the EU AI Act']
  - rationale: The prediction incorrectly claims this question is outside the EU AI Act's scope and redirects to the DSA, matching none of the ground truth answers which correctly identify Article 50 obligations and their limited applicability to content-moderation AI.

### live_answers:la_q92 — **+0.0** (REFUSED)

**Q:** What does GDPR Article 17 say about the right to erasure?

- **gold refs**: Article 17
- **branch refs**: (none)

**A:**

```
This question is about a regulation outside the EU AI Act. This assistant answers EU AI Act questions only (Regulation 2024/1689). Please rephrase with a specific Article reference (e.g. "Article 13") or compliance dimension.
```

  - missing: ['Article 17 of the EU AI Act is about quality management obligations for providers of high-risk AI systems, not about erasure of personal data', 'The retrieved Article 17 covers regulatory-compliance strategy, design verification, examination and testing procedures, post-market monitoring, and incident-reporting workflows']
  - rationale: The prediction refuses to answer, stating it only covers EU AI Act questions and cannot address GDPR Article 17, without making any substantive claim about the content of Article 17.

### live_answers:la_q60 — **-1.0** (WRONG)

**Q:** What are the algorithmic transparency obligations for a Very Large Online Platform content-moderation AI?

- **gold refs**: Article 50
- **branch refs**: (none)

**A:**

```
This question is about the Digital Services Act (DSA), not the EU AI Act (Regulation 2024/1689). This assistant only covers EU AI Act questions; consult the Digital Services Act (DSA) for the applicable rules.
```

  - missing: ['Article 50 imposes transparency duties keyed to particular roles and system types rather than platform size or content-moderation purpose', 'Provider must inform users they are interacting with an AI system if it directly interacts with users (Article 50(1))', 'Provider must mark synthetic content outputs in machine-readable format detectable as artificially generated (Article 50(2))']
  - hallucinated: ['This question is about the Digital Services Act (DSA), not the EU AI Act']
  - rationale: The prediction incorrectly claims this question falls under the DSA rather than the EU AI Act, and provides no information matching any of the ground truth answers about Article 50 transparency obligations.

### live_answers:la_q75 — **-1.0** (WRONG)

**Q:** What data-governance obligations apply to the training data of a high-risk AI sepsis-prediction model?

- **gold refs**: Article 10
- **branch refs**: Article 10, Article 26, Article 13

**A:**

```
Deployer obligations: use the system per the instructions, assign human oversight to competent + trained natural persons, monitor operation, retain automatically generated logs, inform affected workers (for workplace use), and cooperate with market-surveillance authorities. Article 26 carve-outs: deployers that are financial institutions subject to Union financial-services internal-governance requirements fulfil the Article 26(5) monitoring obligation and the Article 26(6) log-retention obligation by complying with the governance arrangements under that financial-services law (Article 26(5) second subparagraph; Article 26(6) second subparagraph). Workplace deployers who are employers must inform workers' representatives and the affected workers BEFORE putting the high-risk system into service (Article 26(7)); applicable Union and national worker-information rules continue to apply.
```

  - missing: ['Article 10 data-governance and management practices for training/validation/testing datasets (Article 10(2))', 'Datasets must be relevant, sufficiently representative, free of errors and complete (Article 10(3))', 'Examination for biases likely to affect health and safety, fundamental rights, or lead to discrimination (Article 10(2)(f))', 'Special categories of personal data may be processed only to the extent strictly necessary for bias detection/correction, subject to appropriate safeguards (Article 10(5))']
  - hallucinated: ['Deployer obligations under Article 26 (human oversight, log retention, worker notification, financial-institution carve-outs) — none of this is part of the ground truth answer about training-data governance']
  - rationale: The prediction addresses deployer obligations under Article 26 (human oversight, log retention, worker notification, etc.) rather than the training-data governance obligations under Article 10 that the ground truth requires (data governance practices, representativeness, bias examination, special-category data processing).

### live_answers:la_q31 — **-0.5** (MIXED)

**Q:** Is an AI system used to structure or deduplicate information for a use case listed in Annex III considered high-risk?

- **gold refs**: Annex III, Article 50, Article 6
- **branch refs**: Article 6, Article 50, Annex III, Annex I

**A:**

```
The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.
```

  - missing: ['Article 6(3) derogation: not high-risk where it performs a narrow procedural task or preparatory task and does not materially influence the outcome', 'The system IS high-risk where the structuring/deduplication does shape the decision the Annex III system ultimately produces', 'The Annex III categories describe substantive functions, not ancillary data-preparation steps']
  - hallucinated: ['Generic Article 6 framing without addressing the structuring/deduplication distinction — the answer does not actually answer the specific question posed']
  - rationale: The prediction correctly notes Article 6 and Annex III relevance and mentions Article 50 transparency duties, partially matching the ground truth, but it entirely omits the critical Article 6(3) derogation (narrow procedural task / preparatory task) that explains why structuring/deduplicating is not high-risk, and it also omits the key distinction that such a system IS high-risk when it materially influences the substantive outcome — instead giving a generic Article 6 framing without addressing the specific question about structuring/deduplication at all. The answer also does not mention the Article 6(3)(a)/(d) conditions explicitly, which are the operative provisions for this question.

### live_answers:la_q69 — **-0.5** (MIXED)

**Q:** Is an AI system that infers patients' emotions for a medical purpose prohibited under Article 5 of the EU AI Act?

- **gold refs**: Article 5
- **branch refs**: Article 5.1.f

**A:**

```
Under Article 5.1.f, emotion recognition in the workplace and in educational institutions is prohibited, including monitoring employees or call-centre agents, with a narrow medical/safety carve-out for systems placed on the market for therapeutic or accident-prevention purposes. Real-time remote biometric identification by law enforcement is prohibited under Article 5 save for narrow, exhaustively-listed law-enforcement exceptions that each require prior judicial or administrative authorisation; under Article 5(5) Member States may enable those exceptions in national law and may set stricter national rules. Article 5(1)(c) carve-out: the social-scoring prohibition does not affect lawful evaluation practices of natural persons that are carried out for a specific purpose in accordance with Union and national law (Recital 31 final sentence).
```

  - hallucinated: ['Real-time remote biometric identification by law enforcement requires prior judicial or administrative authorisation under Article 5', 'Article 5(5) Member States may enable exceptions in national law and set stricter rules', 'Article 5(1)(c) carve-out referencing Recital 31 final sentence about lawful evaluation practices']
  - rationale: The prediction correctly identifies the medical/safety carve-out in Article 5(1)(f) and that emotion inference is banned in workplaces and educational institutions, matching the ground truth, but also introduces incorrect/unsupported claims about law enforcement biometric ID exceptions requiring judicial authorisation and a 'social-scoring prohibition carve-out' referencing Recital 31, which are not part of the ground truth answer.

### live_answers:la_q80 — **-0.5** (MIXED)

**Q:** What transparency obligation applies to AI-generated synthetic medical images used to augment a training dataset?

- **gold refs**: Article 50
- **branch refs**: Article 50, Article 13

**A:**

```
Under Article 50, limited-risk transparency duties under Article 50 apply cumulatively with Article 13 high-risk transparency duties; both apply to the same system, not in the alternative. Transparency obligations split by actor: providers must ensure AI systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format (Article 50(2)); deployers must inform exposed persons when operating emotion-recognition or biometric-categorisation systems (Article 50(3)) and must label deepfakes as artificially generated or manipulated (Article 50(4)). Article 50(4) also requires deployers who use an AI system to generate or manipulate text published to inform the public on matters of public interest to disclose that the text was artificially generated or manipulated; this disclosure duty does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences, or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for publishing it.
```

  - missing: ['Article 50(4) deepfake labelling duty generally does not apply to purely internal training dataset augmentation because it is keyed to content exposed to natural persons', 'Article 50(4) would apply if the synthetic images were subsequently disclosed to natural persons']
  - hallucinated: ['The prediction implies Article 50(1) and Article 13 are relevant to this scenario without basis in the ground truth, and frames the answer as a general Article 50 overview rather than addressing the specific training dataset question']
  - rationale: The prediction correctly identifies Article 50(2) as applying to providers generating synthetic content (machine-readable marking), which matches part of the ground truth, but it fails to address the specific question about synthetic medical images for training datasets, omits the key ground truth distinction that Article 50(4) generally does not apply to purely internal training use (only applies when exposed to natural persons), and instead provides a generic summary of Article 50 provisions without addressing the training dataset context.
