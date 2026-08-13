# R329 — July-7 HARD batch, live answers (Opus 5, Stage-2 firing)

Source sidecar: `evals/bench/results/july7-r329-hard-prod.ckpt.jsonl`

Config: cloudflared tunnel (`wrapper.antifragile-ai.net`) + Cloudflare Access + `claude-opus-5` sent verbatim (`_model_alias_enabled()` False). `stage2_landed_rate 0.80`, latency p50 57.3 s / p95 90.6 s, `errors 0`.

HARD mode replays each conversation as **turn 1** (the question, fresh) then **turn 2** (our turn-1 answer + the recovered follow-up). 67 of the 111 conversations are genuine adversarial pushback. The graded turn is the post-pushback answer.

---

## 1. `july7-113`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 9.1s

### Question

> Does the technical documentation of a high-risk AI system require specifications regarding the required hardware?

### Turn 1 — our answer

Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).


**References:** Article 11, Annex IV

### Turn 2 — after pushback (THE GRADED TURN)

Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).


**References:** Article 11, Annex IV

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Yes. Under Article 11, a provider must draw up technical documentation containing the information set out in Annex IV, which expressly requires a description of the hardware on which the AI system is intended to run (Annex IV point 1(e)) and, as part of the system's development description, the computational resources used to develop, train, test and validate it (Annex IV point 2(c)).


**References:** Article 11


</details>


*Conceded under pushback:* **False**


---

## 2. `july7-119`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 57.7s

### Question

> I have a medical device that has an AI system as a safety component. The medical device is classified "medium-risk" and undergoes a 3rd party conformity assessment. Is the AI system "medium risk" too? If yes, why? If not, why not?

### Turn 1 — our answer

No. The AI Act does not operate a "medium risk" tier for AI systems, and the device's own risk class under the sectoral legislation does not carry across. Article 6(1) classifies an AI system as high-risk where it is intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in Annex I and that product is required to undergo a third-party conformity assessment with a view to its placing on the market, and Annex I lists Regulation (EU) 2017/745 on medical devices. Both conditions are satisfied here, so the AI system is high-risk irrespective of the device's medium-risk classification. Article 43(3) then folds the AI Act assessment into the sectoral procedure, so the requirements of Chapter III, Section 2 are examined by the notified body as part of the single Medical Devices Regulation conformity assessment rather than in a separate AI Act procedure.


**References:** Article 6, Article 43, Annex I

### Turn 2 — after pushback (THE GRADED TURN)

No. The AI Act does not use a "medium risk" tier, and a device's risk class under the medical devices legislation does not transfer to the AI system. The system is high-risk under Article 6(1), which classifies an AI system as high-risk where it is intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in Annex I and that product is required to undergo a third-party conformity assessment with a view to its placing on the market. Annex I lists Regulation (EU) 2017/745 on medical devices, so both conditions are met on the facts stated. The trigger is the existence of a third-party conformity assessment obligation, not the sectoral risk class, so the same result follows for any device class that requires notified-body involvement. Because the product falls under Section A of Annex I, Article 43(3) requires the AI Act requirements to be assessed as part of the sectoral conformity assessment procedure, which the notified body notified under that legislation may control.


**References:** Article 6, Article 43, Annex I

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning. The core of the prior analysis holds up. An AI system that is a safety component of a medical device which undergoes third-party conformity assessment satisfies both limbs of Article 6(1), so it is high-risk, and the MDR "medium-risk" label belongs to a separate regime that does not translate into an AI Act tier. Nothing in the references supports an intermediate tier. The answer below states the classification directly and grounds it only in the provisions supplied. No, the AI system is not "medium-risk," because the EU AI Act does not have a medium-risk tier. It is high-risk. Under the Annex I route in Article 6(1), an AI system is high-risk where it is a safety component of a product covered by the Union harmonisation legislation listed in Annex I and that product must undergo third-party conformity assessment under that sectoral legislation. Medical devices sit within the Annex I harmonisation legislation, and the operator's device already undergoes third-party conformity assessment, so both conditions are satisfied. The "medium-risk" label reflects the medical-device risk classification under the sectoral MDR regime, which is distinct from the AI Act's own tiers. The device's MDR class does not carry over to the AI system, and there is no intermediate AI Act tier between high-risk and the lighter Article 50 transparency duties.


**References:** Article 9, Article 6, Article 6.1, Article 50, Annex I


</details>


*Conceded under pushback:* **False**


---

## 3. `july7-125`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 54.2s

### Question

> We want to deploy an AI system that performs biometric verification solely to confirm that a specific natural person is the person he or she claims to be. Is this system prohibited? Is it high-risk?

### Turn 1 — our answer

An AI system used solely for biometric verification, whose sole purpose is to confirm that a specific natural person is the person he or she claims to be, is neither prohibited nor high-risk on that ground. It is not among the AI practices prohibited under Article 5, and Annex III, point 1(a) expressly carves it out of the biometrics high-risk category: the category covers remote biometric identification systems but "shall not include AI systems intended to be used for biometric verification the sole purpose of which is to confirm that a specific natural person is the person he or she claims to be". The carve-out holds only so long as that is genuinely the sole purpose; the system would be high-risk under Article 6 if, in addition, it performed biometric categorisation according to sensitive or protected attributes or characteristics based on the inference of those attributes or characteristics (Annex III, point 1(b)), performed emotion recognition (Annex III, point 1(c)), or were deployed within another Annex III use case such as employment and workers' management, or were a safety component of a product covered by Annex I.


**References:** Article 5, Article 6, Annex III, Annex I

### Turn 2 — after pushback (THE GRADED TURN)

Neither prohibited nor high-risk, provided that confirming a specific natural person is the person he or she claims to be is genuinely the sole purpose. Such a system is not among the AI practices exhaustively prohibited under Article 5, and Annex III, point 1(a) expressly excludes it from the biometrics high-risk category: that point covers remote biometric identification systems but "shall not include AI systems intended to be used for biometric verification the sole purpose of which is to confirm that a specific natural person is the person he or she claims to be". It would become high-risk under Article 6 only if it did something more, biometric categorisation according to sensitive or protected attributes or characteristics based on the inference of those attributes or characteristics (Annex III, point 1(b)), emotion recognition (Annex III, point 1(c)), use within another Annex III area such as employment, workers' management and access to self-employment, or use as a safety component of a product covered by Annex I harmonisation legislation. Where it interacts directly with natural persons, the Article 50 transparency obligation applies.


**References:** Article 5, Article 6, Article 50, Annex III, Annex I

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.


**References:** Article 9, Article 10, Annex III, Article 53, Article 14, Article 55, Article 43


</details>


*Conceded under pushback:* **False**


---

## 4. `july7-129`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 3.6s

### Question

> What documentation must a provider of a high-risk AI system keep available for national competent authorities, and for how long?

### Turn 1 — our answer

Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.


**References:** Article 18, Article 11, Article 17, Article 47, Article 19

### Turn 2 — after pushback (THE GRADED TURN)

Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.


**References:** Article 18, Article 11, Article 17, Article 47, Article 19

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Under Article 18, for ten years after the high-risk AI system is placed on the market or put into service, the provider must keep at the disposal of the national competent authorities the technical documentation (Article 11), the quality-management-system documentation (Article 17), the documentation of any changes approved by notified bodies, the decisions and other documents issued by notified bodies, and the EU declaration of conformity (Article 47). Separately, under Article 19 the automatically generated logs must be kept for a period appropriate to the intended purpose, of at least six months.


**References:** Article 18, Article 11, Article 17, Article 47, Article 19


</details>


*Conceded under pushback:* **False**


---

## 5. `july7-135`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 71.0s

### Question

> High-risk AI systems under Art. 5(1)(d) and Annex III, point 8 (Administration of justice and democratic processes) in the EU AI Act.

### Turn 1 — our answer

Two different tiers are engaged here, and Annex III, point 8 is not one of them being prohibited. Article 5(1)(d) prohibits the placing on the market, putting into service or use of an AI system for making risk assessments of natural persons in order to assess or predict the risk of a natural person committing a criminal offence, where that assessment is based solely on profiling or on assessing personality traits and characteristics. That predictive policing prohibition carries one carve-out: it does not apply to AI systems used to support a human assessment of a person's involvement in a criminal activity which is already based on objective and verifiable facts directly linked to a criminal activity. Annex III, point 8 instead classifies two use cases as high-risk under Article 6(2), which treats systems falling within an Annex III use case as high-risk. Those are AI systems intended to be used by a judicial authority or on their behalf to assist a judicial authority in researching and interpreting facts and the law and in applying the law to a concrete set of facts, or used in a similar way in alternative dispute resolution, and AI systems intended to be used for influencing the outcome of an election or referendum or the voting behaviour of natural persons in the exercise of their vote. The electoral limb expressly excludes AI systems to the output of which natural persons are not directly exposed, such as tools used to organise, optimise or structure political campaigns from an administrative or logistical point of view.


**References:** Annex III, Article 5.1.d, Article 6

### Turn 2 — after pushback (THE GRADED TURN)

The two provisions sit in different tiers, and a system caught by Article 5(1)(d) is never merely high-risk. Article 5(1)(d) prohibits the placing on the market, putting into service or use of an AI system for making risk assessments of natural persons in order to assess or predict the risk of a natural person committing a criminal offence, based solely on profiling or on assessing personality traits and characteristics, and the sole carve-out is for systems that support the human assessment of a person's involvement in criminal activity where that assessment is already based on objective and verifiable facts directly linked to criminal activity. Outside that prohibited predictive policing context, systems in this field are high-risk under Article 6(2), which classifies the Annex III use cases as high-risk. Annex III, point 8 contains two limbs: AI systems intended to be used by a judicial authority or on their behalf to assist a judicial authority in researching and interpreting facts and the law and in applying the law to a concrete set of facts, or to be used in a similar way in alternative dispute resolution, and AI systems intended to be used for influencing the outcome of an election or referendum or the voting behaviour of natural persons in the exercise of their vote. The second limb carries an express exclusion for AI systems to the output of which natural persons are not directly exposed, such as tools used to organise, optimise or structure political campaigns from an administrative or logistical point of view.


**References:** Article 5.1.d, Annex III, Article 6

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The prior turn answered a different, narrower scenario (a justice-sector risk-assessment tool straddling the Article 5(1)(d) profiling prohibition and the Annex III high-risk regime). The latest question is simply asking what the "Administration of justice and democratic processes" category actually enumerates. The risk of hallucination here is inventing sub-items or importing the Article 5 profiling material that does not belong to this Annex III heading. Annex III point 8 contains two use cases only: a judicial-assistance one and an election/referendum-influence one, the latter carrying an express carve-out for non-exposed administrative campaign tools. I will state both and not conflate them with the Article 5 prohibition tier. Under Annex III point 8, which Article 6(2) routes into the high-risk regime, "Administration of justice and democratic processes" lists two use cases. Second, AI systems intended to be used for influencing the outcome of an election or referendum, or the voting behaviour of natural persons in the exercise of their vote in elections or referenda. This second use case carries an express carve-out. Both fall within the eight Annex III high-risk categories, so a system in either use case is classified high-risk under Article 6(2) rather than prohibited.


**References:** Annex III, Annex III.8, Article 5, Article 5.1.d, Article 6, Article 6.2


</details>


*Conceded under pushback:* **False**


---

## 6. `july7-141`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 64.7s

### Question

> What obligations, if any, does the EU AI Act set in place for AI systems that interact directly with natural persons? What exceptions, if any, apply?

### Turn 1 — our answer

Yes. Under Article 50(1), providers must ensure that AI systems intended to interact directly with natural persons are designed and developed so that the natural persons concerned are informed that they are interacting with an AI system, and under Article 50(5) that information must be given in a clear and distinguishable manner at the latest at the time of the first interaction and must conform to the applicable accessibility requirements. Two exceptions apply. The disclosure duty does not arise where the AI nature of the interaction is obvious from the point of view of a natural person who is reasonably well-informed, observant and circumspect, taking into account the circumstances and the context of use. It also does not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties, but that law enforcement carve-out is itself reversed where the system is available for the public to report a criminal offence, in which case the disclosure obligation applies in full.


**References:** Article 50.1, Article 50.3

### Turn 2 — after pushback (THE GRADED TURN)

Yes, Article 50(1) sets a transparency obligation. Providers must ensure that AI systems intended to interact directly with natural persons are designed and developed so that the natural persons concerned are informed that they are interacting with an AI system, and Article 50(5) requires that information to be given in a clear and distinguishable manner at the latest at the time of the first interaction, conforming to the applicable accessibility requirements. Two exceptions apply. The obligation does not apply where the fact of interacting with an AI system is obvious from the point of view of a natural person who is reasonably well-informed, observant and circumspect, taking into account the circumstances and the context of use. It also does not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties, but that law enforcement exception is itself reversed where those systems are available for the public to report a criminal offence, in which case the disclosure duty applies.


**References:** Article 50.1, Article 50.3

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning. The prior answer was substantively accurate on the law-enforcement carve-out, but it was incomplete on the exceptions. Article 50(1) contains two exceptions, not one. The answer named the law-enforcement carve-out and its public-reporting reversal but omitted the primary exception: the duty does not apply where it is already obvious to a reasonably well-informed, observant, and circumspect person, given the context, that they are interacting with an AI. Stating "the Act sets one exception" understated the provision. I correct that below. Yes, a disclosure obligation applies. Providers must ensure that AI systems intended to interact directly with natural persons are designed so that the person is informed they are interacting with an AI system (Article 50(1)). This is a transparency duty that attaches to the direct-interaction function itself, so it can apply even where the system is not high-risk. Two exceptions apply. First, the obligation does not apply where it is obvious to a reasonably well-informed, observant, and circumspect natural person, taking account of the circumstances and context of use, that they are dealing with an AI system. Second, it does not apply to AI systems authorised by law to detect, prevent, investigate, or prosecute criminal offences, subject to appropriate safeguards for the rights and freedoms of third parties.


**References:** Article 9, Article 50, Article 50.1


</details>


*Conceded under pushback:* **False**


---

## 7. `july7-147`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 50.9s

### Question

> Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?

### Turn 1 — our answer

Yes, the Commission may add new use-cases to Annex III or modify those already listed, but only by delegated act adopted in accordance with Article 97 and only within the areas Annex III already covers: an added use-case must fall under one of those existing headings and pose a risk of harm to health, safety or fundamental rights equivalent to, or greater than, the risk posed by the use-cases already listed there. The power is corrective and evidence-bound rather than a free-standing power to extend the Regulation's scope, under the same Article 97 procedure the Commission may likewise amend the conditions in Article 6(3), second subparagraph, by adding new conditions or modifying them, where there is concrete and reliable evidence of the existence of AI systems that fall under the scope of Annex III but do not pose a significant risk of harm to the health, safety or fundamental rights of natural persons. Any such amendment operates directly on the classification perimeter, since AI systems referred to in Annex III are high-risk by force of Article 6(2).


**References:** Annex III, Article 97, Article 6

### Turn 2 — after pushback (THE GRADED TURN)

Yes, the Commission may amend Annex III by delegated act, but only within the boundaries the Act itself sets. Under Article 6, the systems listed in Annex III are considered to be high-risk, and the Commission is empowered to adopt delegated acts in accordance with Article 97 to amend that list. The empowerment to remove or narrow entries is expressly conditioned: the Commission may amend the conditions in Article 6 by adding new conditions or modifying them only where there is concrete and reliable evidence of the existence of AI systems that fall under the scope of Annex III but do not pose a significant risk of harm to the health, safety or fundamental rights of natural persons. A related, non-amending duty falls on the Commission under the same article: after consulting the European Artificial Intelligence Board, and no later than 2 February 2026, it must provide guidelines specifying the practical implementation of Article 6, together with a comprehensive list of practical examples of use cases of AI systems that are high-risk and not high-risk. The current Annex III set the Commission would be amending comprises biometrics, critical infrastructure, education and vocational training, employment and worker management, and law enforcement, in so far as its use is permitted under relevant Union or national law.


**References:** Annex III, Article 6, Article 97

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Article 7 empowers the Commission to add, modify, or remove high-risk use-cases within Annex III by delegated act, so the eight existing categories (biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes) are not fixed. Substantively, any amendment must rest on the Article 7 criteria: the intended purpose of the system, the extent to which it is or is likely to be used, the nature and volume of data processed, the potential impact on health, safety, and fundamental rights, the severity and reversibility of possible harm, and the availability and effectiveness of redress. The power is also bounded in scope, since additions must concern systems operating within the areas already covered by the Annex III headings and are judged against the risk posed relative to the use-cases already listed. Procedurally, the exercise of this power is subject to the conditions governing delegated acts in Article 97, which frame how and for how long the delegation is conferred and preserve the Parliament's and Council's ability to object or revoke it. This power affects only the Annex III route to high-risk classification under Article 6(2). It does not reach the Annex I route under Article 6(1), where a system is high-risk because it is, or is a safety component of, a product covered by the Union harmonisation legislation in Annex I that must undergo third-party conformity assessment.


**References:** Annex III, Article 6, Article 6.2, Article 6.1, Annex I, Article 7, Article 97


</details>


*Conceded under pushback:* **False**


---

## 8. `july7-153`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 38.0s

### Question

> If a provider of a high-risk AI system confirms that the system achieves an appropriate level of accuracy, robustness, and cybersecurity at the time of development, then no further action is required by the provider on these aspects in the future. Correct?

### Turn 1 — our answer

No. Article 15 requires that a high-risk AI system achieve an appropriate level of accuracy, robustness and cybersecurity and that it perform consistently in those respects throughout its lifecycle, so the duty is continuing rather than discharged at the point of development. It is reinforced by the Article 9 risk management system, which must be established, implemented, documented and maintained across the lifecycle and must take account of post-market monitoring data, and by the Article 17 quality management system, whose examination, test and validation procedures must be carried out before, during and after development at a defined frequency. Under Article 13 the instructions for use must state the level of accuracy, including its metrics, robustness and cybersecurity against which the system has been tested and validated and which can be expected, together with any known and foreseeable circumstances that may have an impact on that expected level.


**References:** Article 15, Article 13, Article 9, Article 17

### Turn 2 — after pushback (THE GRADED TURN)

No. Article 15 requires high-risk AI systems to achieve an appropriate level of accuracy, robustness and cybersecurity and to perform consistently in those respects throughout their lifecycle, so a one-off confirmation at development time does not discharge the obligation. The risk management system under Article 9 must be established, implemented, documented and maintained as a continuous, iterative process across the lifecycle, including evaluation of post-market monitoring data and testing to ensure the system performs consistently for its intended purpose. Under Article 17 the provider's quality management system must cover examination, test and validation procedures to be carried out before, during and after development, together with the frequency at which they are repeated, and must include a strategy for managing modifications to the system. The declared levels of accuracy, the relevant accuracy metrics, robustness and cybersecurity, along with any known and foreseeable circumstances affecting them, must also be kept accurate in the instructions for use under Articles 15 and 13.


**References:** Article 15, Article 9, Article 17

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Yes. Article 15(1) requires a high-risk AI system to achieve an appropriate level of accuracy, robustness, and cybersecurity and to perform consistently in those respects throughout its lifecycle, so the obligation is a continuing one rather than a one-time confirmation at the point of placing on the market. The lifecycle standard means the provider must sustain those properties as the system operates, including resilience against errors, faults, or inconsistencies within the system or its environment under Article 15(4) and resilience against unauthorised third parties who attempt to alter its use, outputs, or performance by exploiting vulnerabilities under Article 15(3). Cybersecurity in particular must be maintained through appropriate technical and organisational measures such as access controls, encryption, and logging of access under Article 15(5), which are ongoing operational safeguards rather than design-time checkboxes. The declared accuracy metrics in the instructions for use under Article 15(2) set the benchmark against which continued performance is measured.


**References:** Article 9, Article 15


</details>


*Conceded under pushback:* **False**


---

## 9. `july7-159`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 35.0s

### Question

> Are AI systems that fall under one of the areas of Annex III, but not falling within a use-case within such areas, considered high-risk?

### Turn 1 — our answer

No. Annex III is organised into eight areas, namely biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes, but within each area it enumerates specific use cases, and Article 6(2) classifies an AI system as high-risk only where it falls within one of those listed use cases. A system used in an Annex III area but outside every use case listed for that area is not high-risk on that basis. It may still be high-risk on the separate Article 6(1) route, which covers a system that is a safety component of, or is itself, a product falling under the Union harmonisation legislation listed in Annex I where that product must undergo a third-party conformity assessment.


**References:** Annex III, Article 6, Annex I

### Turn 2 — after pushback (THE GRADED TURN)

No. Falling within one of the eight Annex III areas (biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes) is not by itself sufficient. Article 6(2) classifies a system as high-risk only where it falls within one of the use cases enumerated under those areas, so a system operating in an Annex III area without matching any listed use case is not high-risk on that route. It may still be high-risk under Article 6(1) where it is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I and that product must undergo a third-party conformity assessment. Conversely, a system that does match an Annex III use case is not high-risk where it poses no significant risk of harm and performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the previously completed human assessment, or performs a preparatory task, unless it performs profiling of natural persons, in which case it is always high-risk.


**References:** Annex III, Article 6, Annex I

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Annex I route (Article 6(1)): the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I AND that product must undergo a third-party conformity assessment under that sectoral legislation. Annex III route (Article 6(2)): the system falls within one of the eight Annex III use cases. Article 6(3) derogation: an Annex III system is NOT high-risk where it poses no significant risk of harm and meets one of four conditions (a narrow procedural task; improving the result of a previously completed human activity; detecting decision-making patterns or deviations without replacing or influencing the human assessment; or a preparatory task), unless it profiles natural persons, in which case it is always high-risk; the provider must document this self-assessment before placing the system on the market and still register it under Article 49(2). Real-time remote biometric identification by law enforcement is prohibited under Article 5 save for narrow, exhaustively-listed law-enforcement exceptions that each require prior judicial or administrative authorisation; under Article 5(5) Member States may enable those exceptions in national law and may set stricter national rules. Article 5(1)(c) carve-out: the social-scoring prohibition does not affect lawful evaluation practices of natural persons that are carried out for a specific purpose in accordance with Union and national law (Recital 31 final sentence). Article 5(1)(f) carve-out: emotion-recognition systems placed on the market strictly for medical or safety reasons, including systems intended for therapeutical use, fatigue detection in pilots/drivers for accident prevention, and pain/fatigue physical-state monitoring (which Recital 18 expressly excludes from the 'emotion' definition itself), are NOT prohibited (Recital 44 final sentence). Article 5(1)(g) carve-out: the biometric-categorisation prohibition does not cover lawful labelling, filtering or categorisation of biometric datasets acquired in line with Union or national law, including sorting by hair colour or eye colour, which is permitted in law-enforcement contexts (Recital 30).


**References:** Annex III, Article 6, Article 5, Annex I


</details>


*Conceded under pushback:* **False**


---

## 10. `july7-163`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 30.7s

### Question

> If I have an AI system that is high-risk because listed in the use cases of Annex III, and change it to a different use case that is not in Annex I or III, does it stay high-risk due to its historical provenance?

### Turn 1 — our answer

No. High-risk status attaches to the intended purpose of the system as placed on the market or put into service, not to its history. Article 6 classifies an AI system as high-risk on two routes only: the Annex I route, where the system is a safety component of, or is itself, a product covered by the listed Union harmonisation legislation and that product must undergo a third-party conformity assessment, and the Annex III route, where the system falls within one of the eight listed use cases (biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes). Once the intended purpose is changed to a use case outside both Annex I and Annex III, neither route is satisfied and the system is no longer high-risk, so the classification does not persist by provenance.


**References:** Annex III, Annex I, Article 6

### Turn 2 — after pushback (THE GRADED TURN)

No. High-risk status attaches to the system's intended purpose, not to its history. Article 6 classifies on two routes only: the Annex I route, where the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I and that product must undergo a third-party conformity assessment, and the Annex III route, where the system falls within one of the eight Annex III use cases. Once the intended purpose is changed to one falling outside both annexes, neither route is satisfied and the system is not high-risk, since classification must be assessed against the intended purpose under which the system is placed on the market or put into service rather than against a purpose it previously served.


**References:** Article 6, Annex III, Annex I

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning. The pushback does not identify an actual error. Article 6 classification is functional and use-case driven, not status-based or historical. There is no provision in the AI Act that preserves high-risk classification based on a system's past use. Article 43(4) requires a fresh conformity assessment on substantial modification, but that operates only while the system remains high-risk; it does not convert a now-out-of-scope use case back into a high-risk one. My prior answer holds, so I will restate it cleanly rather than revise the substance. Not high-risk, and historical provenance is irrelevant. Classification under Article 6 tracks whether the system's current use satisfies one of the two live routes, not any prior status. Under the Annex I route (Article 6(1)), the system must be, or be a safety component of, a product covered by the listed Union harmonisation legislation that itself requires third-party conformity assessment. Under the Annex III route (Article 6(2)), the use must fall within one of the eight listed categories, such as biometrics, employment, or law enforcement. If the changed use case sits in neither Annex I nor Annex III, neither route is met and the system is not high-risk, whatever its earlier classification.


**References:** Annex III, Annex I, Article 6, Article 6.1, Article 6.2, Article 43, Article 43.4


</details>


*Conceded under pushback:* **False**


---

## 11. `july7-169`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 75.0s

### Question

> Under the EU AI Act, which AI systems are classified as high-risk under Art. 6 and Annex III for decision-making in emergency call handling and medical triage?

### Turn 1 — our answer

High-risk. Article 6(2) classifies as high-risk any AI system falling within one of the eight Annex III use cases, and Annex III point 5(d), within the category of access to and enjoyment of essential private services and essential public services and benefits, expressly names AI systems intended to evaluate and classify emergency calls by natural persons, AI systems used to dispatch or to establish priority in the dispatching of emergency first response services including police, firefighters and medical aid, and emergency healthcare patient triage systems. Such a system escapes that classification only under the Article 6(3) derogation, which applies where it does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision making, and it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations from prior patterns without replacing or influencing the previously completed human assessment, or performs a preparatory task, and it is always high-risk where it performs profiling of natural persons. A triage system that is itself, or is a safety component of, a medical device covered by Regulation (EU) 2017/745 or Regulation (EU) 2017/746 in Annex I is independently high-risk under Article 6(1) where that product must undergo a third-party conformity assessment under that sectoral legislation.


**References:** Article 6, Annex III, Annex I

### Turn 2 — after pushback (THE GRADED TURN)

High-risk, on the Annex III route under Article 6(2). Annex III point 5(d), within the category on access to and enjoyment of essential private services and essential public services and benefits, covers AI systems intended to evaluate and classify emergency calls by natural persons, to dispatch or to establish priority in the dispatching of emergency first response services including by police, firefighters and medical aid, and emergency healthcare patient triage systems. That classification falls away only under the Article 6(3) derogation, which requires that the system pose no significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision making, and that it perform a narrow procedural task, improve the result of a previously completed human activity, detect decision-making patterns or deviations without being meant to replace or influence the previously completed human assessment, or perform a preparatory task, and it never applies where the system performs profiling of natural persons. A provider relying on that derogation must document the assessment before placing the system on the market and must still register it under Article 49(2). Independently of Annex III, a triage system that is itself a medical device, or a safety component of one, is high-risk under Article 6(1) where the product must undergo a third-party conformity assessment under the Annex I legislation, namely Regulation (EU) 2017/745 on medical devices or Regulation (EU) 2017/746 on in vitro diagnostic medical devices.


**References:** Article 6, Annex III, Annex I, Article 49

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The substance of the classification is sound. Annex III, in its essential private and public services category, does explicitly enumerate emergency-call and triage systems, so treating them as high-risk under the Annex III route is correct. What was off in the earlier answer was the framing: it opened on the Annex I medical-device route and the Article 6(3) derogation, which the current question does not ask about. Explicitly listed within the essential private and public services category of Annex III are AI systems intended to evaluate and classify emergency calls, AI systems used to dispatch or to establish priority in the dispatching of emergency first response services such as police, firefighters and medical aid, and emergency healthcare patient triage systems. Because these fall within one of the eight Annex III use cases, they are classified high-risk under Article 6(2), which treats any system within an Annex III use case as high-risk. As a consequence, the provider must subject the system to a conformity assessment under Article 43, which for an Annex III system applying harmonised standards runs through the internal-control procedure of Annex VI. The provider must also register the system in the EU database under Article 49 before placing it on the market or putting it into service.


**References:** Annex III, Article 43, Article 6, Article 6.3, Article 6.2, Article 49, Annex I, Annex VI


</details>


*Conceded under pushback:* **False**


---

## 12. `july7-175`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 3.6s

### Question

> Is an AI system used to detect decision-making patterns or deviations for a use case listed in Annex III considered high-risk?

### Turn 1 — our answer

Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.


**References:** Article 6.3, Article 6, Annex III

### Turn 2 — after pushback (THE GRADED TURN)

Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.


**References:** Article 6.3, Article 6, Annex III

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Not automatically. Even within an Annex III use case, Article 6(3)(c) provides that an AI system intended to detect decision-making patterns or deviations from prior decision-making patterns is not high-risk where it does not pose a significant risk of harm and is not meant to replace or influence a previously completed human assessment without proper human review. However, under Article 6(3) such a system is always high-risk where it performs profiling of natural persons.


**References:** Article 6.3, Article 6


</details>


*Conceded under pushback:* **False**


---

## 13. `july7-181`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 58.2s

### Question

> If an MSA reclassifies a non-high-risk AI system as high-risk, must the provider recall and suspend it without undue delay, or does the MSA provide a timeframe for corrective actions depending on gravity?

### Turn 1 — our answer

Immediately, and not necessarily by recall. Once a provider considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity, Article 20 requires it to take the necessary corrective actions immediately and to select the measure that is appropriate, namely bringing the system into conformity, withdrawing it, disabling it, or recalling it, and to inform the distributors and, where applicable, the deployers, the authorised representative and importers. The Act attaches no graduated deadline calibrated to the gravity of the non-conformity, and it does not condition the provider's timing on a period fixed by the market surveillance authority. Where the system also presents a risk within the meaning of Article 79(1), that is a risk to health or safety or to fundamental rights, the provider must immediately investigate the causes in collaboration with the reporting deployer and inform the competent market surveillance authorities and, where applicable, the notified body that issued a certificate for that system, in particular of the nature of the non-compliance and of any corrective action taken.


**References:** Article 20, Article 79

### Turn 2 — after pushback (THE GRADED TURN)

Immediate corrective action, but not automatically recall and suspension. Under Article 20, once a provider considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity, it must immediately take the necessary corrective actions to bring that system into conformity, to withdraw it, to disable it, or to recall it, as appropriate, and inform the distributors and, where applicable, the deployers, the authorised representative and the importers. The choice among those measures rests with the provider according to what is appropriate to the non-conformity, so reclassification triggers an immediate duty to act rather than an automatic recall. Where the system presents a risk within the meaning of Article 79(1), which treats an AI system presenting a risk to health, safety or fundamental rights as a product presenting a risk, the provider must also immediately investigate the causes in collaboration with the reporting deployer and inform the competent market surveillance authorities and, where applicable, the notified body that issued a certificate for that system, in particular of the nature of the non-compliance and of any corrective action taken. Article 20 fixes no graduated deadline calibrated to gravity, and no period is set for the authority to allow. The standard is immediacy.


**References:** Article 20, Article 79

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.


**References:** Article 9, Article 10, Annex III, Article 53, Article 14, Article 55, Article 43


</details>


*Conceded under pushback:* **False**


---

## 14. `july7-187`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 38.1s

### Question

> EU AI Act definition of AI regulatory sandbox: elements including purpose, setup authority, intended participants, activities, and duration.

### Turn 1 — our answer

An AI regulatory sandbox under Article 57 is a controlled environment that each Member State must establish at least one of at national level, in which providers develop, train, test and validate innovative AI systems for a limited time before they are placed on the market or put into service, under the supervision of the national competent authority that sets it up. The sandbox operates under a sandbox plan agreed with that authority, which provides regulatory guidance and supervises the identification and mitigation of risks arising in the sandbox. The European Data Protection Supervisor may also establish an AI regulatory sandbox for Union institutions, bodies, offices and agencies, and may exercise the roles and tasks of national competent authorities for it. Article 62 requires Member States to give SMEs, including start-ups, with a registered office or branch in the Union priority access to those sandboxes. As to duration, Article 57 fixes only that testing is for a limited time and requires national competent authorities to report annually to the AI Office and the Board from one year after establishment until termination, followed by a final report, so the Act does not prescribe a fixed maximum sandbox period.


**References:** Article 57, Article 62

### Turn 2 — after pushback (THE GRADED TURN)

An AI regulatory sandbox under Article 57 is a controlled environment that each Member State must establish, at least one at national level, for the development, training, testing and validation of innovative AI systems for a limited time before they are placed on the market or put into service, under regulatory guidance and supervision that includes identifying and mitigating risks. Article 57 also allows the European Data Protection Supervisor to establish a sandbox for Union institutions, bodies, offices and agencies, exercising the roles and tasks of national competent authorities. Participants are providers and prospective providers of innovative AI systems, with SMEs, including start-ups, having a registered office or branch in the Union entitled to priority access under Article 62. The Act frames duration only as a limited time agreed in the sandbox arrangement, and the sandbox itself runs from its establishment until its termination, during which national competent authorities must submit annual reports to the AI Office and the Board covering progress, results, best practices, incidents, lessons learnt and recommendations, followed by a final report, with those annual reports or abstracts made publicly available online.


**References:** Article 57, Article 62

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


An AI regulatory sandbox under Article 57 is a controlled environment for developing, training, testing, and validating innovative AI systems for a limited time before they are placed on the market or put into service, run under regulatory guidance with supervised mitigation of identified risks.


**References:** Article 9, Article 57


</details>


*Conceded under pushback:* **False**


---

## 15. `july7-191`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 3.7s

### Question

> Under the EU AI Act, when a high-risk AI system is found to conform with the requirements, what information must the Union technical documentation assessment certificate contain?

### Turn 1 — our answer

Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system.


**References:** Annex VII

### Turn 2 — after pushback (THE GRADED TURN)

Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system.


**References:** Annex VII

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Under Annex VII point 4.6, where the notified body finds the high-risk AI system conforms with the Chapter III Section 2 requirements, it issues a Union technical documentation assessment certificate. Per Annex VII point 4.6, that certificate must indicate the name and address of the provider, the conclusions of the examination, the conditions (if any) for its validity, and the data necessary for the identification of the AI system.


**References:** Article 9


</details>


*Conceded under pushback:* **False**


---

## 16. `july7-197`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 6.5s

### Question

> Provider under EU AI Act Art. 10(5): conditions and safeguards for processing special categories of personal data in high-risk AI systems for bias detection and correction.

### Turn 1 — our answer

Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict, documented access controls to prevent misuse (c); no transmission or transfer to other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).


**References:** Article 10.5, Article 10

### Turn 2 — after pushback (THE GRADED TURN)

Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict, documented access controls to prevent misuse (c); no transmission or transfer to other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).


**References:** Article 10.5, Article 10

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Under Article 10(5), a provider of a high-risk AI system may exceptionally process special categories of personal data only to the extent strictly necessary to ensure bias detection and correction, subject to appropriate safeguards. Article 10(5) requires all of the following: the bias work cannot be done with other data, including synthetic or anonymised data (a); technical limits on re-use plus state-of-the-art security and pseudonymisation (b); strict, documented access controls to prevent misuse (c); no transmission or transfer to other parties (d); deletion once the bias is corrected or the retention period ends, whichever is first (e); and records of processing documenting why it was strictly necessary (f).


**References:** Article 10.5


</details>


*Conceded under pushback:* **False**


---

## 17. `july7-203`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 78.1s

### Question

> Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information.

### Turn 1 — our answer

Article 13 is what governs this: the provider must design the high-risk AI system for sufficient operational transparency to the deployer and accompany it with instructions for use, and that provision sets a minimum content list. The instructions must contain at least the identity and contact details of the provider, the intended purpose, the characteristics, capabilities and limitations of performance of the system, any known or foreseeable circumstance related to use in accordance with the intended purpose or under conditions of reasonably foreseeable misuse which may lead to risks to health and safety or fundamental rights, the changes to the system and its performance pre-determined by the provider at the moment of the initial conformity assessment, if any, the human oversight measures required under Article 14 including the technical measures put in place to facilitate interpretation of the outputs by deployers, where applicable the information enabling deployers to interpret the output and use it appropriately, where relevant a description of the mechanisms included in the system that allow deployers to properly collect, store and interpret the logs kept under Article 12, and the expected lifetime of the system.


**References:** Article 13, Article 14, Article 12

### Turn 2 — after pushback (THE GRADED TURN)

Under Article 13, which requires a high-risk AI system to be designed for sufficient operational transparency to deployers and to be accompanied by instructions for use, the provider must supply instructions containing at least the identity and contact details of the provider, the characteristics, capabilities and limitations of performance of the system including its intended purpose, any known or foreseeable circumstance related to use in accordance with the intended purpose or under conditions of reasonably foreseeable misuse which may lead to risks to health and safety or to the fundamental rights referred to in Article 9(2), where applicable the information enabling deployers to interpret the output of the system and use it appropriately, the changes to the system and its performance pre-determined by the provider at the moment of the initial conformity assessment, the human oversight measures referred to in Article 14 including the technical measures put in place to facilitate interpretation of the outputs, where relevant a description of the mechanisms within the system allowing deployers to properly collect, store and interpret the logs in accordance with Article 12, and the expected lifetime of the system. These are minimum categories, so a provider may need to include further information where the system's characteristics require it.


**References:** Article 13, Article 9, Article 14, Article 12

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


A provider must supply instructions for use that are concise, complete, and comprehensible, and Article 13, which requires high-risk systems to be sufficiently transparent for deployers to interpret output and use the system appropriately, sets out the categories those instructions must contain. These are: the identity and contact details of the provider; the system's intended purpose; its capabilities and limitations, including the level of accuracy, robustness, and cybersecurity against which it was tested; and, under Article 13(3)(b)(ii), any known or foreseeable circumstances that may give rise to risks to health, safety, or fundamental rights. The instructions must also describe the human-oversight measures the deployer is to apply, the system's expected lifetime, and any required maintenance and care measures, including software updates, needed to keep it operating as intended. The governing principle in Article 13(2) is that the type and degree of transparency provided must be appropriate to enable both provider and deployer to meet their respective obligations.


**References:** Article 9, Article 13, Article 13.3.b.ii, Article 13.2


</details>


*Conceded under pushback:* **False**


---

## 18. `july7-209`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 41.9s

### Question

> Under the EU AI Act (Regulation (EU) 2024/1689) Article 95, who may draw up codes of conduct, and which bodies must encourage and facilitate their drawing up?

### Turn 1 — our answer

Codes of conduct may be drawn up by individual providers or deployers of AI systems, by organisations representing them, or by both, and may be developed with the involvement of any interested stakeholders and their representative organisations, including civil society organisations and academia. The bodies that must encourage and facilitate their drawing up are the AI Office and the Member States, which are also required to take into account the specific interests and needs of SMEs, including start-ups, when doing so. Those codes are intended to foster the voluntary application, to AI systems other than high-risk AI systems, of some or all of the requirements set out in Chapter III, Section 2, taking into account available technical solutions and industry best practices. A single code may cover one or more AI systems, taking into account the similarity of the intended purpose of the relevant systems (Article 95).


**References:** Article 95

### Turn 2 — after pushback (THE GRADED TURN)

Codes of conduct may be drawn up by individual providers or deployers of AI systems, by organisations representing them, or by both, including with the involvement of any interested stakeholders and their representative organisations such as civil society organisations and academia (Article 95). The bodies that must encourage and facilitate their drawing up are the AI Office and the Member States, whose task is to promote the voluntary application, to AI systems other than high-risk AI systems, of some or all of the requirements set out in Chapter III, Section 2, taking into account available technical solutions and industry best practices. In doing so, the AI Office and the Member States must take into account the specific interests and needs of SMEs, including start-ups. A single code of conduct may cover one or more AI systems, taking into account the similarity of the intended purpose of the relevant systems.


**References:** Article 95

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The pushback here is unfounded. My earlier answer tracks Article 95(1) accurately, and I should reaffirm it rather than second-guess a correct reading. The only wrinkle is that the knowledge-graph draft says "AI Office + Member States," but that conflates the Article 95 codes of conduct with the Article 56 codes of practice. The article-specific reference confirms the correct actors for Article 95 are the Commission and the Member States. Codes of practice under Article 56 are what the AI Office facilitates; codes of conduct under Article 95 are facilitated by the Commission and Member States. Under Article 95(1), codes of conduct may be drawn up by a broad range of actors, expressly including providers of non-high-risk AI systems, and the bodies required to encourage and facilitate their drawing up are the Commission and the Member States. These are voluntary codes under which providers of non-high-risk systems are encouraged to apply, in whole or in part, the Section 2 requirements otherwise mandatory for high-risk systems, adapted to the intended purpose and risk of the system. The codes must be based on clear objectives and key performance indicators that measure the achievement of those objectives, and their development should be inclusive. This provision applies from 2 August 2026, with the Commission evaluating its impact by 2 August 2028 and every three years thereafter.


**References:** Article 95, Article 95.1, Article 56


</details>


*Conceded under pushback:* **False**


---

## 19. `july7-215`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 59.2s

### Question

> Under the EU AI Act, what minimum elements must a provider's quality management system (QMS) for high-risk AI systems include? List the required elements.

### Turn 1 — our answer

A provider's quality management system must, at a minimum, cover a strategy for regulatory compliance, procedures for design and design verification, procedures for examination, testing and validation, post-market monitoring, and procedures for reporting serious incidents, and it must be put in place so as to ensure compliance with the Regulation and be documented in a systematic and orderly manner (Article 17(1)). Implementation of those aspects is proportionate to the size of the provider's organisation, but the provider must in any event respect the degree of rigour and the level of protection required to ensure its high-risk AI systems comply with the Regulation (Article 17(2)). Where a provider is already subject to quality management system obligations or an equivalent function under relevant sectoral Union law, it may include these aspects within that existing system (Article 17(3)). For providers that are financial institutions subject to internal governance requirements under Union financial services law, the obligation to put a quality management system in place is deemed fulfilled by complying with those internal governance rules, with the exception of points (g), (h) and (i) of Article 17(1) (Article 17(4)).


**References:** Article 17

### Turn 2 — after pushback (THE GRADED TURN)

Article 17 requires providers of high-risk AI systems to put in place a quality management system that ensures compliance with the Regulation and is documented in a systematic and orderly manner (Article 17(1)). At a minimum that system must cover a strategy for regulatory compliance, design verification, examination and test procedures, post-market monitoring, and incident-reporting workflows. Implementation of those aspects must be proportionate to the size of the provider's organisation, but the provider must in any event respect the degree of rigour and the level of protection needed to ensure its high-risk AI systems comply with the Regulation (Article 17(2)). Providers already subject to quality management system obligations or an equivalent function under sectoral Union law may incorporate these aspects into that existing system (Article 17(3)). For providers that are financial institutions subject to internal governance requirements under Union financial services law, compliance with those internal governance arrangements or processes is deemed to satisfy the quality management system obligation, with the exception of points (g), (h) and (i) of Article 17(1), and harmonised standards under Article 40 are to be taken into account (Article 17(4)).


**References:** Article 17, Article 40

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


A provider of a high-risk AI system must operate a quality management system that ensures compliance with the Regulation, documented in a systematic and orderly manner through written policies, procedures and instructions (Article 17). That system must include, at a minimum, the following thirteen elements. A strategy for regulatory compliance, including compliance with conformity assessment procedures and procedures for the management of modifications to the high-risk AI system. Techniques, procedures and systematic actions for the design, design control and design verification of the system. Techniques, procedures and systematic actions for the development, quality control and quality assurance of the system. Examination, test and validation procedures to be carried out before, during and after development, and the frequency with which they are performed. Technical specifications, including standards, to be applied, and the means used to ensure compliance where harmonised standards are not applied in full. The risk management system required under Article 9. The setting-up, implementation and maintenance of a post-market monitoring system in accordance with Article 72. Procedures for the reporting of serious incidents in accordance with Article 73. The handling of communication with national competent authorities, other relevant authorities, notified bodies, other operators, customers and other interested parties.


**References:** Article 9, Article 17, Article 72, Article 73


</details>


*Conceded under pushback:* **False**


---

## 20. `july7-221`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 74.4s

### Question

> Under the EU AI Act, what are the specific exceptions permitting law enforcement to use real-time remote biometric identification in publicly accessible spaces? List the permitted objectives.

### Turn 1 — our answer

Only three exhaustive objectives permit it. Article 5(1)(h) prohibits the use of real-time remote biometric identification systems in publicly accessible spaces for the purposes of law enforcement except where strictly necessary for one of the following: targeted search for specific victims of abduction, trafficking in human beings and sexual exploitation of human beings, and search for missing persons, prevention of a specific, substantial and imminent threat to the life or physical safety of natural persons or of a genuine and foreseeable terrorist attack, and localisation or identification of a person suspected of a criminal offence listed in Annex II punishable in the Member State concerned by a custodial sentence of at least four years, Annex II covering terrorism, trafficking in human beings, sexual exploitation of children, illicit trafficking in narcotic drugs, weapons and nuclear material, murder, kidnapping, rape, armed robbery, organised crime, participation in a criminal organisation and environmental crime. Each deployment requires prior authorisation by a judicial or independent administrative authority, subject to a narrow urgency carve-out permitting use to start before authorisation provided authorisation is requested without undue delay and obtained within 24 hours, failing which the use must stop immediately. The relevant market surveillance authority and national data protection authority must be notified. Under Article 5(5) these carve-outs are not self-executing: a Member State must first decide to authorise such use in national law and specify which of the point (h) objectives and which Annex II offences its competent authorities may invoke, and it may adopt more restrictive rules. Where the use falls outside Article 5(1)(h) rather than within it, the practice is not thereby unregulated: remote biometric identification systems are listed in point 1(a) of Annex III and are therefore high-risk under the Annex III route in Article 6(2), in so far as their use is permitted under relevant Union or national law.


**References:** Article 5, Annex II, Annex III

### Turn 2 — after pushback (THE GRADED TURN)

Three exhaustive objectives, and nothing else. Article 5(1)(h) treats real-time remote biometric identification in publicly accessible spaces for law enforcement purposes as a prohibited practice unless the use is strictly necessary for one of the following: targeted searches for specific victims of abduction, trafficking in human beings or sexual exploitation and for missing persons, prevention of a specific, substantial and imminent threat to the life or physical safety of natural persons or of a genuine and foreseeable terrorist attack, and the localisation or identification of a person suspected of an offence listed in Annex II and punishable in the Member State concerned by a custodial sentence of at least four years. Annex II sets out that closed list of offences, comprising terrorism, trafficking in human beings, sexual exploitation of children, illicit trafficking in narcotic drugs, weapons and nuclear material, murder, kidnapping, rape, armed robbery, organised crime, participation in a criminal organisation and environmental crime. Each deployment must be authorised in advance by a judicial or independent administrative authority, subject to an urgency exception under which authorisation may be requested during use but must be obtained within 24 hours, failing which the use must stop immediately and the data be deleted. Article 5(5) further makes the whole carve-out optional at national level, since a Member State must legislate to permit such use and must specify in national law which of the point (h) objectives, and which Annex II offences, its competent authorities may invoke. Use also requires a fundamental rights impact assessment under Article 27 before first deployment, registration in the EU database under Article 49, and notification of each use to the relevant market surveillance authority and the national data protection authority.


**References:** Article 5, Annex II, Article 27, Article 49

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The earlier framing was defective. It enumerated the objectives as "First" and "Third" and omitted the second entirely, so only two of the three exhaustive law-enforcement objectives under Article 5(1)(h) were stated. The corrected answer restores the full closed set of three. Real-time remote biometric identification in publicly accessible spaces by law enforcement is prohibited as a rule under Article 5, and permitted only under the strictly necessary, exhaustive carve-out in Article 5(1)(h) for three law-enforcement objectives. Third, the localisation or identification of a person suspected of having committed a criminal offence listed in Annex II, for the purpose of a criminal investigation or prosecution, where that offence is punishable in the relevant Member State by a custodial sentence of at least four years. These are the only permitted objectives, and each use remains subject to the safeguards attached to the carve-out. The deployer must complete a Fundamental Rights Impact Assessment under Article 27 before first use, register the system in the EU database under Article 49, and obtain prior authorisation from a judicial or independent administrative authority, with the urgency exception that authorisation may be sought within 24 hours and use must stop immediately if it is refused. Use must also be notified to the relevant market-surveillance authority and the national data-protection authority. Note the separate treatment across risk tiers.


**References:** Article 5, Article 5.1.h, Article 27, Article 49, Annex II


</details>


*Conceded under pushback:* **False**


---

## 21. `july7-225`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 42.6s

### Question

> Who is entitled to lodge a complaint about an infringement, and to which authority must the complaint be submitted?

### Turn 1 — our answer

Any natural or legal person having grounds to consider that there has been an infringement of the Regulation may submit a complaint, and it must be submitted to the relevant market surveillance authority (Article 85). The complainant need not be personally affected by the infringement, and the right is without prejudice to other administrative or judicial remedies. Such complaints are taken into account for the purpose of conducting market surveillance activities under Regulation (EU) 2019/1020 and are handled in line with the dedicated procedures the market surveillance authorities have established for them.


**References:** Article 85

### Turn 2 — after pushback (THE GRADED TURN)

Any natural or legal person who has grounds to consider that there has been an infringement of the Regulation may submit a complaint, and the complaint goes to the relevant market surveillance authority (Article 85). The complainant does not need to be personally affected by the infringement, and this right is without prejudice to other administrative or judicial remedies. In accordance with Regulation (EU) 2019/1020, such complaints are taken into account for the purpose of conducting market surveillance activities and are handled in line with the dedicated procedures established for them by the market surveillance authorities.


**References:** Article 85

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Any natural or legal person may lodge a complaint, and it must be submitted to the relevant market surveillance authority. Under Article 85, which establishes the right to lodge a complaint about an infringement of the AI Act, this right is broader than GDPR Article 77.


**References:** Article 9, Article 85, Article 77


</details>


*Conceded under pushback:* **False**


---

## 22. `july7-231`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 76.0s

### Question

> Provider of high-risk AI system: three mandatory actions under EU AI Act upon identifying serious incident during real-world testing (Art. 61, Art. 72).

### Turn 1 — our answer

Three actions are mandatory once the incident is identified. First, report the serious incident to the market surveillance authority of the Member State where it occurred, as Article 73 requires of providers of high-risk AI systems. The deadline is tiered: immediately and in any event within two days of becoming aware where the incident involves a widespread infringement or a disruption of critical infrastructure, within ten days in the case of death, and within fifteen days for other serious incidents, or immediately once a causal link is established. Second, following that report, without delay perform the necessary investigations into the incident and the AI system concerned under Article 73, which must include a risk assessment of the incident and corrective action. The provider must cooperate with the competent authorities and, where relevant, the notified body, and must not carry out any investigation that alters the AI system in a way which may affect a subsequent evaluation of the causes of the incident before informing those authorities of that action. Third, channel the incident, its analysis and the resulting corrective action through the post-market monitoring system that Article 72 requires the provider to establish and document proportionately to the risks of the system, and which must actively and systematically collect, document and analyse relevant performance data. Throughout, the Article 61 guarantees for subjects of testing in real-world conditions continue to apply, so subjects may withdraw at any time without any resulting detriment and may use the arrangements for requesting the reversal or the disregarding of the AI system's predictions, recommendations or decisions.


**References:** Article 61, Article 72, Article 73

### Turn 2 — after pushback (THE GRADED TURN)

Three actions are mandatory. First, report the serious incident to the market surveillance authorities of the Member State where it occurred, under Article 73, which sets tiered deadlines of immediately and in any event within 2 days of awareness for a widespread infringement or a serious and irreversible disruption of critical infrastructure, 10 days for death, and 15 days for other serious incidents, or immediately once the causal link is established. Second, without delay perform the necessary investigations into the incident and the AI system concerned, including a risk assessment of the incident and corrective action, cooperating with the competent authorities and, where relevant, the notified body, and performing no investigation that alters the system in a way which may affect subsequent evaluation of the causes of the incident before informing those authorities (Article 73). Third, channel the incident, its analysis and the resulting corrective action through the documented post-market monitoring system required by Article 72, which must actively and systematically collect, document and analyse relevant data, including data provided by deployers. In the real-world testing setting itself, Article 61 continues to govern the subjects, who keep the right to withdraw at any time without any resulting detriment and without justification, and the arrangements for requesting the reversal or disregarding of the system's predictions, recommendations or decisions, and the testing remains subject to the real-world testing plan and market surveillance authority oversight under Article 60. Note that the Article 73 reporting duty is expressed for providers of high-risk AI systems placed on the Union market, whereas testing in real-world conditions under Article 60 does not itself qualify as placing on the market.


**References:** Article 61, Article 72, Article 73, Article 60

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The prior answer was indeed off. It described general safeguards for real-world testing (suspension, subject protection, reversibility drawn from the consent and testing-conditions regime) rather than the specific set of actions the AI Act attaches to a serious incident during such testing. Those specific actions live in Article 60's real-world-testing regime and route through the Article 73 serious-incident mechanism, and they form a distinct trio: report, mitigate or suspend, and provide for recall. The earlier framing conflated tiers and did not cleanly identify three actions, so a correction is warranted. Under Article 60, which permits testing of high-risk AI systems in real-world conditions outside a sandbox subject to an approved testing plan and market-surveillance oversight, the provider must take three actions upon identifying a serious incident. First, it must report the serious incident to the national market surveillance authority of the Member State where the testing takes place, using the serious-incident reporting mechanism that Article 73 establishes for providers of high-risk systems. Second, it must adopt immediate mitigation measures, and failing that, suspend the testing until such mitigation is in place or otherwise terminate it. Third, it must establish a procedure for the prompt recall of the AI system where the testing is terminated.


**References:** Article 9, Article 60, Article 73


</details>


*Conceded under pushback:* **False**


---

## 23. `july7-237`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 17.1s

### Question

> Under Article 2(1) of Regulation (EU) 2024/1689 (EU AI Act), which categories of actors/persons does the Act apply to? List the categories.

### Turn 1 — our answer

Article 2(1) applies the Regulation to seven categories: providers placing AI systems on the market or putting them into service, or placing general-purpose AI models on the market in the Union, whether established in the Union or in a third country, deployers of AI systems established or located in the Union, providers and deployers established or located in a third country where the output produced by the AI system is used in the Union, importers and distributors of AI systems, product manufacturers placing on the market or putting into service an AI system together with their product and under their own name or trademark, authorised representatives of providers not established in the Union, and affected persons located in the Union. Article 2 does not apply to obligations of deployers who are natural persons using AI systems in the course of a purely personal non-professional activity, and it leaves other Union consumer protection and product safety rules unaffected.


**References:** Article 2.1

### Turn 2 — after pushback (THE GRADED TURN)

Article 2(1) applies the Regulation to seven categories of actors: providers placing AI systems on the market or putting them into service, or placing general-purpose AI models on the market, in the Union, irrespective of whether they are established in the Union or a third country; deployers of AI systems established or located within the Union; providers and deployers established or located in a third country where the output produced by the AI system is used in the Union; importers and distributors of AI systems; product manufacturers placing an AI system on the market or putting it into service together with their product and under their own name or trademark; authorised representatives of providers not established in the Union; and affected persons located in the Union. Article 2 qualifies that scope by excluding obligations of deployers who are natural persons using AI systems in the course of a purely personal non-professional activity, as well as military, defence and national security uses and scientific research and development. The Regulation applies without prejudice to other Union law on consumer protection and product safety.


**References:** Article 2.1

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The prior answer was not so much hallucinated as incomplete. It named only two categories and was cut off before listing the third that the scope provision actually covers. Article 2(1) as substantiated in the references reaches providers regardless of where they are established, deployers located in the EU, and a third group: providers and deployers established in a third country where the system's output is used in the EU. That third category is the one most often overlooked, so the answer should state all three. Under Article 2(1), which fixes the Regulation's scope, the Act applies to the following categories of actors. Providers that place AI systems on the market or put them into service in the EU, whether those providers are established in the EU or in a third country. Deployers of AI systems that are established or located within the EU. Providers and deployers established or located in a third country where the output produced by the AI system is used in the EU.


**References:** Article 2.1, Article 2


</details>


*Conceded under pushback:* **False**


---

## 24. `july7-243`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 83.7s

### Question

> Under the EU AI Act, what is the EU database for high-risk AI systems, what categories of information must it contain, and who is the controller of that database?

### Turn 1 — our answer

The EU database is the central Union register that the Commission sets up and maintains in collaboration with the Member States under Article 71, covering high-risk AI systems registered in accordance with Article 49, which obliges providers, authorised representatives and public-authority deployers to register themselves and their system before it is placed on the market or put into service, and testing in real world conditions registered in accordance with Article 60. It must contain the data listed in Sections A and B of Annex VIII, entered by the provider or, where applicable, by the authorised representative, together with the information specified in Annex IX for registered real world testing. It may contain personal data only in so far as necessary for collecting and processing information under the Regulation, and that information includes the names and contact details of the natural persons responsible for registering the system who have the legal authority to represent the provider or the deployer. The registered data is machine-readable, navigable and searchable and is publicly accessible, save for the secure non-public section required by Article 49(4) for high-risk AI systems in the areas of law enforcement, migration, asylum and border control management, where a reduced set of Annex VIII and Annex IX entries is filed and access is limited to the Commission and the designated national authorities. The Commission is the controller of the database, and it must consult the relevant experts when setting the functional specifications and the Board when updating them.


**References:** Article 71, Article 49, Article 60

### Turn 2 — after pushback (THE GRADED TURN)

Under Article 71, the EU database for high-risk AI systems is the register that the Commission sets up and maintains in collaboration with the Member States, and the Commission is the controller of that database. It contains information on Annex III high-risk AI systems registered under Article 49, which obliges the provider or authorised representative to register themselves and the system before it is placed on the market or put into service, with the exception of systems referred to in point 2 of Annex III. It also covers AI systems that the provider considers not to be high-risk under the Article 6(3) derogation and registers under Article 6(4) and Article 49, and testing in real world conditions registered under Article 60 with a Union-wide unique single identification number and the information specified in Annex IX. The categories of information are those listed in Sections A and B of Annex VIII, covering the information to be submitted by providers of high-risk AI systems, and the database contains personal data only in so far as necessary for collecting and processing information under the Regulation, namely the names and contact details of the natural persons responsible for registering the system who have legal authority to represent the provider or the deployer. For the law enforcement, migration, asylum and border control management systems in points 1, 6 and 7 of Annex III, Article 49(4) requires registration in a secure non-public section limited to the listed points of Sections A, B and C of Annex VIII and of Annex IX, to which only the Commission and the national authorities referred to in Article 74(8) have access.


**References:** Article 71, Article 49, Article 60, Annex III, Article 6

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The EU database under Article 71 is the central register of high-risk AI systems (together with GPAI models), which providers populate when they register their systems under Article 49 before market placement, alongside real-world testing entries logged under Article 60. The Commission sets up and manages it, so the Commission is the controller. It has two content layers. A public section makes registration data openly accessible and machine-readable, navigable and searchable, so that the public and stakeholders can see which high-risk systems are on the market. A restricted-access section holds the more sensitive registration and oversight data, available only to the Commission and the competent national authorities rather than the general public. The registration obligation that feeds this database attaches to systems classified as high-risk under Article 6, whether through the Annex I route (a safety component of, or itself, a product under the Union harmonisation legislation listed in Annex I that must undergo third-party conformity assessment) or the Annex III route (one of the eight listed use cases such as biometrics, critical infrastructure, employment and worker management, and law enforcement). Even a provider that relies on the Article 6(3) derogation to treat an Annex III system as not high-risk must still document that self-assessment and register the system under Article 49(2), so the entry appears in this database.


**References:** Annex III, Article 71, Article 49, Article 49.2, Annex I, Article 6, Article 6.3, Article 60


</details>


*Conceded under pushback:* **False**


---

## 25. `july7-249`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 90.6s

### Question

> Provider/distributor/importer obligations under EU AI Act Art. 16/23/26 to ensure AI system conformity, including when risk-tier (e.g., high-risk) is undisclosed.

### Turn 1 — our answer

Conformity is never presumed from silence. Each actor must verify it against the documentary evidence the Act requires, and the absence of that evidence is itself the trigger to withhold the system and act. The provider carries the primary duty under Article 16 to ensure the high-risk AI system complies with the Section 2 requirements and bears the provider's identity, to operate a quality management system covering regulatory compliance strategy, design verification and testing (Article 17), to keep the technical documentation and, where under its control, the automatically generated logs for at least six months (Article 19), to have the system undergo the relevant Article 43 conformity assessment before it is placed on the market, to draw up the EU declaration of conformity (Article 47), affix the CE marking (Article 48), register the system in the EU database (Article 49), take corrective action where the system is not in conformity (Article 20), and demonstrate conformity upon a reasoned request of a national competent authority (Article 21). Before placing the system on the market, the importer must verify under Article 23 that the provider carried out the Article 43 conformity assessment, drew up the technical documentation in accordance with Article 11 and Annex IV, that the system bears the CE marking and is accompanied by the EU declaration of conformity and instructions for use, and that an authorised representative was appointed under Article 22, and must supply that documentation to competent authorities on reasoned request in a language they easily understand. Before making the system available, the distributor must verify under Article 24 the CE marking, the copy of the EU declaration of conformity and the instructions for use, and that the provider and importer met their respective obligations. The deployer must take appropriate technical and organisational measures to use the system in accordance with the instructions for use, assign human oversight to competent and trained natural persons, monitor operation, and retain the automatically generated logs under its control (Article 26). Where the risk tier is undisclosed, the verification duties are the operative safeguard rather than the classification itself. A distributor that considers, on the basis of the information in its possession, that the system is not in conformity must not make it available until it is brought into conformity, and must inform the provider or importer where the system presents an Article 79(1) risk (Article 24(2)). A deployer with reason to consider that use in accordance with the instructions may present such a risk must, without undue delay, suspend use and inform the provider or distributor and the relevant market surveillance authority, and must immediately inform the provider first and then the importer or distributor and the authorities of any serious incident (Article 26(5)). Finally, a distributor, importer or deployer that puts its own name or trademark on the system, substantially modifies it, or modifies the intended purpose so that the system becomes high-risk is itself treated as the provider and assumes the full Article 16 obligations, with the initial provider required to furnish the information, technical access and assistance needed for that new provider's conformity assessment (Article 25).


**References:** Article 16, Article 17, Article 19, Article 23

### Turn 2 — after pushback (THE GRADED TURN)

Non-disclosure of the risk tier by an upstream actor does not suspend any of these duties, because each of Articles 16, 23 and 24 is framed as an objective verification duty owed before the system is placed on the market or made available, not as a duty conditional on what the previous actor declared. As provider of a high-risk AI system the operator must ensure it is compliant with the requirements set out in Section 2 and bears the operator's identity, operate a quality management system covering regulatory compliance strategy, design control and verification, and examination, test and validation procedures (Article 17), keep the technical documentation, keep the logs automatically generated by the system where under the operator's control for a period appropriate to the intended purpose and at least six months (Article 19), ensure the system undergoes the relevant conformity assessment procedure under Article 43 prior to placing on the market, draw up the EU declaration of conformity (Article 47), affix the CE marking (Article 48), register the system in the EU database (Article 49), take corrective action where it is not in conformity (Article 20), ensure compliance with the accessibility requirements, and upon a reasoned request of a national competent authority demonstrate conformity with the Section 2 requirements. A provider established outside the Union must in addition appoint an authorised representative by written mandate before placing the system on the market, empowered to verify and keep the declaration of conformity and technical documentation available for ten years, supply them to authorities on reasoned request, and cooperate with market surveillance authorities (Article 22). An importer must verify, before placing the system on the market, that the provider carried out the Article 43 conformity assessment, drew up the technical documentation in accordance with Article 11 and Annex IV, that the system bears the required CE marking and is accompanied by the EU declaration of conformity and instructions for use, and that an authorised representative has been appointed, and must indicate its identity on the system, ensure storage and transport conditions do not jeopardise compliance, and supply competent authorities on reasoned request with the information and documentation needed to demonstrate conformity, in a language easily understood by them (Article 23). A distributor must verify the CE marking, a copy of the EU declaration of conformity and the instructions for use, and that the provider and importer complied with their respective obligations, and where it considers or has reason to consider on the basis of the information in its possession that the system is not in conformity it must not make it available until the system has been brought into conformity, and must inform the provider or importer where the system presents a risk within the meaning of Article 79(1) (Article 24). That "reason to consider" test is what governs the undisclosed-tier case, and it is reinforced by Article 25(1), under which a distributor, importer, deployer or other third party is itself treated as a provider subject to Article 16 where it puts its name or trademark on the system, makes a substantial modification, or modifies the intended purpose so that the system becomes high-risk, with the initial provider obliged under Article 25(2) to make available the necessary information and reasonably expected technical access and assistance so the new provider can meet those obligations, in particular the conformity assessment. A deployer must take appropriate technical and organisational measures to use the system in accordance with the instructions for use, assign human oversight to competent and trained natural persons, monitor operation on the basis of the instructions for use and inform the provider of serious incidents, suspend use and inform the provider or distributor and the relevant market surveillance authority without undue delay where it has reason to consider that use in accordance with the instructions may result in a risk within the meaning of Article 79(1), keep the automatically generated logs to the extent they are under its control, and cooperate with market surveillance authorities (Article 26). Deployers that are financial institutions subject to internal governance requirements under Union financial services law fulfil the Article 26(5) monitoring duty and the Article 26(6) log-retention duty by complying with those governance arrangements, and a deployer that is an employer must inform workers' representatives and the affected workers before putting the high-risk system into service (Article 26(7)).


**References:** Article 16, Article 17, Article 19, Article 26, Article 48, Article 23

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The one point worth checking is which operator carries the duty not to jeopardise conformity through storage and transport. That duty is not the importer's alone. Article 24 places the same storage and transport obligation on distributors while a high-risk system is under their responsibility, and Article 23 places it on importers. Attributing it only to the importer would understate the distributor's position, so the answer below states it for both. Yes, where the system is high-risk. As a distributor of a high-risk AI system, the operator must ensure that, while the system is under the operator's responsibility, storage or transport conditions do not jeopardise its compliance, alongside the operator's duty under Article 24 to verify before making it available that it bears the CE marking and is accompanied by the EU declaration of conformity and the instructions for use. The fact that you were not told the tier does not remove this. Article 24 applies to distributors of high-risk systems, and the classification follows from whether the system falls within the high-risk criteria, not from any label the provider chooses to disclose, so the operator should treat the system as high-risk and verify these elements where the criteria are met. As an importer, the same non-jeopardy duty applies to the operator under Article 23, which additionally requires you, before placing the system on the market, to verify that the provider carried out the conformity assessment and that the system conforms with the Regulation.


**References:** Article 24, Article 23


</details>


*Conceded under pushback:* **False**


---

## 26. `july7-255`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 39.7s

### Question

> Does an AI system intended as a toy qualify as a high-risk AI system under the EU AI Act, and if so, under what conditions?

### Turn 1 — our answer

An AI system intended as a toy is high-risk only where it is intended to be used as a safety component of a toy, or is itself a toy, falling within Directive 2009/48/EC on the safety of toys, and where that product is required to undergo a third-party conformity assessment before being placed on the market or put into service. Both conditions in Article 6(1) must be met cumulatively: the toy safety directive is listed in Annex I as Union harmonisation legislation, so the first limb is satisfied by an AI-enabled toy or an AI safety component of one; the second limb turns on whether that particular toy must undergo third-party conformity assessment under that directive rather than manufacturer self-assessment. Where the toy falls within a category the toy safety directive permits to be assessed by the manufacturer's own internal production control, the second condition is not fulfilled and the system is not high-risk on the Article 6(1) route, the classification applies irrespective of whether the AI system is placed on the market or put into service independently of the toy itself. Where both conditions are met, the conformity assessment obligation in Article 43 applies to the provider.


**References:** Article 6, Annex I

### Turn 2 — after pushback (THE GRADED TURN)

An AI system intended as a toy is high-risk only where it is intended to be used as a safety component of a toy, or is itself a toy, falling within Directive 2009/48/EC on the safety of toys, which is listed in and that product is required to undergo a third-party conformity assessment with a view to being placed on the market or put into service. Both conditions in Article 6(1) must be fulfilled cumulatively, and this holds irrespective of whether the AI system is placed on the market or put into service independently of the toy. Where the toy manufacturer may instead rely on internal production control under the toy safety legislation, typically where harmonised standards have been applied in full, the second condition is not met and the system is not high-risk on this route. Where both conditions are fulfilled, the conformity assessment follows Article 43, carried out together with the assessment required under Directive 2009/48/EC.


**References:** Article 6

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The operative provision is Article 6(1), which classifies an AI system as high-risk where it is itself, or is a safety component of, a product covered by the Union harmonisation legislation listed in Annex I, which includes the toy-safety legislation, and where that product is required to undergo a third-party conformity assessment under that same legislation before being placed on the market.


**References:** Article 9, Article 6, Article 6.1, Annex I


</details>


*Conceded under pushback:* **False**


---

## 27. `july7-259`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 6.3s

### Question

> Does the EU AI Act (Regulation (EU) 2024/1689) prohibit all AI systems for emotion recognition from biometric data? If not, specify prohibited contexts, exceptions, and risk-tier classification for permitted systems.

### Turn 1 — our answer

Real-time remote biometric identification by law enforcement is prohibited under Article 5 save for narrow, exhaustively-listed law-enforcement exceptions that each require prior judicial or administrative authorisation; under Article 5(5) Member States may enable those exceptions in national law and may set stricter national rules. Transparency obligations split by actor: providers must ensure AI systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format (Article 50(2)); deployers must inform exposed persons when operating emotion-recognition or biometric-categorisation systems (Article 50(3)) and must label deepfakes as artificially generated or manipulated (Article 50(4)). Article 50(4) also requires deployers who use an AI system to generate or manipulate text published to inform the public on matters of public interest to disclose that the text was artificially generated or manipulated; this disclosure duty does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences, or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for publishing it. Deployers of certain high-risk AI systems (Annex III + public-sector deployers) must perform a Fundamental Rights Impact Assessment before first use, covering deployment process, affected persons, specific risks, human-oversight measures, and complaints workflows.


**References:** Article 5, Article 5.1.f, Article 50.3, Article 27, Article 49

### Turn 2 — after pushback (THE GRADED TURN)

Real-time remote biometric identification by law enforcement is prohibited under Article 5 save for narrow, exhaustively-listed law-enforcement exceptions that each require prior judicial or administrative authorisation; under Article 5(5) Member States may enable those exceptions in national law and may set stricter national rules. Transparency obligations split by actor: providers must ensure AI systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format (Article 50(2)); deployers must inform exposed persons when operating emotion-recognition or biometric-categorisation systems (Article 50(3)) and must label deepfakes as artificially generated or manipulated (Article 50(4)). Article 50(4) also requires deployers who use an AI system to generate or manipulate text published to inform the public on matters of public interest to disclose that the text was artificially generated or manipulated; this disclosure duty does not apply where the use is authorised by law to detect, prevent, investigate or prosecute criminal offences, or where the content has undergone human review or editorial control and a natural or legal person holds editorial responsibility for publishing it. Deployers of certain high-risk AI systems (Annex III + public-sector deployers) must perform a Fundamental Rights Impact Assessment before first use, covering deployment process, affected persons, specific risks, human-oversight measures, and complaints workflows.


**References:** Article 5, Article 5.1.f, Article 50.3, Article 27, Article 49

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Emotion recognition is not categorically prohibited under the AI Act; the prohibition in Article 5 only applies in workplaces and educational institutions, with a narrow medical/safety exception. Elsewhere the system is high-risk under Annex III.1(c) and triggers Article 50(3) transparency duties toward exposed persons.


**References:** Article 5, Article 50.3, Article 5.1.f, Article 9, Article 10


</details>


*Conceded under pushback:* **False**


---

## 28. `july7-265`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 6.5s

### Question

> Under Regulation (EU) 2024/1689 (EU AI Act), how is "risk" defined?

### Turn 1 — our answer

The combination of the probability of an occurrence of harm and the severity of that harm.


**References:** Article 3.2

### Turn 2 — after pushback (THE GRADED TURN)

Defines 68 terms used in the Regulation, including 'AI system' (machine-based, varying autonomy, possibly adaptive, inferring from input how to generate output influencing physical/virtual environments), 'provider', 'deployer', 'placing on the market', 'putting into service', 'substantial modification', 'general-purpose AI model', 'general-purpose AI system', 'systemic risk'.


**References:** Article 3.2

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Classifies an AI system as high-risk on two routes. Article 3 defines 68 terms used in the Regulation, including 'AI system'. Article 9 requires a documented, iterative risk-management system across the AI system's lifecycle.


**References:** Article 3.2, Article 9, Article 10, Annex III, Article 53


</details>


*Conceded under pushback:* **False**


---

## 29. `july7-271`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 53.6s

### Question

> A provider becomes aware of a risk (within the meaning of Article 79(1)) for their high-risk AI system. Does the provider need to take immediate corrective action OR immediately investigate the causes OR both? For example, perhaps it's the market surveillance authority that must investigate the cause, and the provider can help later.

### Turn 1 — our answer

Both, and they are separate duties that run in parallel. Under Article 20, a provider that considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity must immediately take the necessary corrective actions to bring the system into conformity, to withdraw it, to disable it, or to recall it, as appropriate, and must inform the distributors and, where applicable, the deployers, the authorised representative and importers. Where that system presents a risk within the meaning of Article 79(1) and the provider becomes aware of the risk, Article 20 additionally requires the provider to immediately investigate the causes, in collaboration with the reporting deployer where applicable, and to inform the competent market surveillance authorities and, where applicable, the notified body that issued a certificate for the system, in particular of the nature of the non-compliance and of any corrective action taken. The market surveillance authority's role does not displace either duty and does not come first. Under Article 79 the authority carries out its own evaluation of the system where it has sufficient reason to consider that the system presents such a risk, and where it finds non-compliance it requires the operator without undue delay to take corrective action, to withdraw the system, or to recall it within a prescribed period. The provider's investigation and corrective action are self-triggered on awareness, not on being told; the provider's obligation under Article 79 is to cooperate as necessary with the market surveillance authority and with the relevant national fundamental-rights authorities. Separately, where the risk has materialised as a serious incident, Article 73 requires the provider to report it to the market surveillance authorities of the Member State where it occurred, immediately once a causal link or its reasonable likelihood is established and in any event within 15 days of awareness, or within 10 days in the event of a person's death.


**References:** Article 79.1, Article 20, Article 73

### Turn 2 — after pushback (THE GRADED TURN)

Both, and the two duties run in parallel rather than in sequence. Under Article 20, a provider that considers or has reason to consider that a high-risk AI system it has placed on the market or put into service is not in conformity must immediately take the necessary corrective actions to bring it into conformity, withdraw it, disable it, or recall it, and inform the distributors and, where applicable, the deployers, the authorised representative and importers. Where the system presents a risk within the meaning of Article 79(1) and the provider becomes aware of that risk, the same article requires the provider to immediately investigate the causes, in collaboration with the reporting deployer where applicable, and to inform the competent market surveillance authorities and, where applicable, the notified body that issued the certificate for that system, in particular of the nature of the non-compliance and of any relevant corrective action taken. The market surveillance authority's own evaluation under Article 79, which can result in it requiring the operator to take corrective action, to withdraw, or to recall within a prescribed period, does not displace or postpone the provider's duties. It sits alongside them, and the provider must cooperate as necessary with that authority and with the national fundamental-rights bodies referred to in Article 77(1).


**References:** Article 79.1, Article 20, Article 77

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Corrective action, not a standalone cause-investigation duty. Under Article 20, once a provider considers or has reason to consider that its high-risk AI system placed on the market is not in conformity, it must immediately take the necessary corrective actions to bring the system into conformity, withdraw it, disable it, or recall it as appropriate, and inform the distributors, deployers, authorised representative, and importers of that system. Article 20 frames the trigger in terms of non-conformity rather than prescribing a discrete "investigate the cause" step, so where awareness of a risk under Article 79(1) reflects an underlying non-conformity, the operative obligation is to act to remedy it and notify the relevant operators. This sits alongside, and does not displace, the market-surveillance route of Article 79, under which the authority evaluates the system and may itself require withdrawal, recall, or restriction within a period proportionate to the risk.


**References:** Article 79.1, Article 79, Article 20


</details>


*Conceded under pushback:* **False**


---

## 30. `july7-277`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 68.9s

### Question

> As a distributor of high-risk AI systems under the EU AI Act, do transport conditions affect compliance obligations for software-based systems (Art. 16, Art. 25)?

### Turn 1 — our answer

Only where such conditions can actually arise. Article 24 obliges a distributor to ensure that, while a high-risk AI system is under its responsibility, storage or transport conditions, where applicable, do not jeopardise the system's compliance with the requirements set out in Section 2, and that "where applicable" qualifier is what governs here: a system supplied purely as software, with no physical carriage or medium, ordinarily presents no transport conditions capable of jeopardising conformity, so that limb of the duty has no practical content. The remainder of Article 24 is unaffected, so before making the system available on the market the operator must still verify that it bears the required CE marking, that it is accompanied by a copy of the EU declaration of conformity and the instructions for use, and that the provider and the importer have complied with their respective obligations. Article 16 places the compliance, quality management and documentation duties on providers of high-risk AI systems rather than on distributors, so it does not bind you in the operator's distributor capacity. It binds you only if the operator becomes a provider under Article 25 by putting the operator's name or trademark on the system, making a substantial modification to it, or changing its intended purpose.


**References:** Article 16, Article 25, Article 24

### Turn 2 — after pushback (THE GRADED TURN)

Yes, but only where such conditions are applicable. Article 24 requires a distributor to ensure that, while a high-risk AI system is under its responsibility, storage or transport conditions, where applicable, do not jeopardise the system's compliance with the requirements set out in Section 2, and that "where applicable" qualifier is what does the work for software delivered without any physical carrier, since there are then no transport conditions to control. The duty is not switched off in the abstract, so it still bites where the system reaches the market on a physical medium or through a distribution channel whose integrity you control. The operator's operative obligations therefore remain those in Article 24: before making the system available on the market, verify that it bears the required CE marking, that it is accompanied by a copy of the EU declaration of conformity and the instructions for use, and that the provider and the importer have complied with their respective obligations. Article 16 sets out providers' obligations and does not bind you as a distributor unless the operator becomes a provider under Article 25 by putting the operator's name or trademark on the system, making a substantial modification, or changing its intended purpose.


**References:** Article 16, Article 25, Article 24

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The operator's model was not hallucinating. Article 24, which governs distributors of high-risk AI systems, does require the distributor to ensure that, while the system is under its responsibility, storage or transport conditions do not jeopardise the system's compliance with the applicable requirements. The same provision separately obliges the distributor to verify, before making the system available, that it bears the CE marking, is accompanied by the EU declaration of conformity, and carries the instructions for use. The storage and transport duty is drafted to apply only where relevant, so for a high-risk system supplied purely as software with no tangible medium in transit it will have limited practical effect, but the obligation is real and the operator's model stated it correctly.


**References:** Article 9, Article 24


</details>


*Conceded under pushback:* **False**


---

## 31. `july7-283`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 76.1s

### Question

> Does the EU AI Act classify AI in drones for remote biometric identification or other uses as prohibited, high-risk, or exempt if the drone is a toy? Art. 5, Art. 6, Annex III.

### Turn 1 — our answer

AI in a drone that performs ‘real-time’ remote biometric identification in publicly accessible spaces for the purposes of law enforcement is a prohibited practice under Article 5(1)(h), permitted only in so far as strictly necessary for one of the exhaustively listed objectives, including under point (h)(iii) the localisation or identification of a person suspected of an offence referred to in Annex II punishable in the Member State concerned by at least four years' custody; that prohibition is without prejudice to Article 9 of Regulation (EU) 2016/679 where biometric data are processed for purposes other than law enforcement. The same drone-borne identification outside that law enforcement context, post-remote identification, or use by any other actor, is instead high-risk under Article 6 by operation of point 1(a) of Annex III, which covers remote biometric identification systems but not systems used for biometric verification whose sole purpose is to confirm that a specific natural person is the person he or she claims to be. The drone being a toy is not an exemption: Directive 2009/48/EC on the safety of toys is listed in Annex I, so an AI system that is a safety component of the toy drone, or is itself such a product, is high-risk on Article 6's product route where that product must undergo third-party conformity assessment. A toy drone whose AI performs remote biometric identification remains high-risk on the Annex III route regardless of the platform, and escapes it only under the Article 6(3) derogation, a narrow procedural task, improvement of a previously completed human activity, detection of decision-making patterns or deviations, or a preparatory task, which never applies where the system performs profiling of natural persons. A toy drone with neither a biometric nor a safety-component function falls outside both tiers and is subject only to the Article 50 transparency obligation to inform natural persons that they are interacting with an AI system, unless that is obvious in the circumstances.


**References:** Article 5, Annex II, Article 6, Annex III, Annex I

### Turn 2 — after pushback (THE GRADED TURN)

A drone-mounted "real-time" remote biometric identification system is a prohibited practice under Article 5(1)(h) where it is used in publicly accessible spaces for the purposes of law enforcement, unless and in so far as such use is strictly necessary for one of the objectives exhaustively listed there, including the localisation or identification of a person suspected of having committed an offence referred to in Annex II punishable in the Member State concerned by a custodial sentence or detention order of at least four years, that point being without prejudice to Article 9 of Regulation (EU) 2016/679 for processing of biometric data for purposes other than law enforcement. Used outside that law-enforcement setting, the same capability is instead high-risk, remote biometric identification systems being listed in point 1(a) of Annex III, which does not extend to biometric verification the sole purpose of which is to confirm that a person is who he or she claims to be; the Article 6(3) derogation for narrow procedural, result-improving, pattern-detecting or preparatory tasks offers little scope here, since an Annex III system that performs profiling of natural persons is always high-risk. Toy status confers no exemption. Directive 2009/48/EC on the safety of toys is Union harmonisation legislation listed in Annex I, so AI intended to be used as a safety component of a toy drone, or which is itself such a product, is high-risk under Article 6 where that product must undergo a third-party conformity assessment under that Directive; and the Article 5(1)(h) prohibition attaches to the practice, not to the platform, so a toy-classified drone performing that use is equally caught. Drone AI put to other uses that is neither an Annex I safety component of the kind described nor within an Annex III use case is not high-risk, and is subject principally to the Article 50 transparency obligations where the system is intended to interact directly with natural persons.


**References:** Article 5, Annex II, Annex III, Annex I, Article 6

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Real-time remote biometric identification in publicly accessible spaces is a prohibited practice under Article 5(1)(h) only when carried out for law enforcement, and even then it is permitted under the exhaustive carve-out for three objectives: the targeted search for abduction, trafficking and sexual-exploitation victims and missing persons, the prevention of a specific imminent threat to life or a foreseeable terrorist attack, and the localisation of suspects of Annex II offences punishable by at least four years. That carved-out law-enforcement use additionally requires a prior Fundamental Rights Impact Assessment (Article 27), Article 49 registration in the EU database, prior judicial or independent-administrative authorisation with a 24-hour urgency exception, and notification of the market-surveillance and data-protection authorities.


**References:** Article 5, Article 5.1.h, Article 27, Article 49, Annex II


</details>


*Conceded under pushback:* **False**


---

## 32. `july7-287`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 94.8s

### Question

> Under Art. 9 EU AI Act, list the five harm categories and their mapping to prohibited, high-risk, limited-risk, minimal-risk, and systemic-risk AI systems.

### Turn 1 — our answer

No such five harm categories exist under Article 9, and Article 9 maps to a single tier rather than to five: it requires that a risk management system be established, implemented, documented and maintained in relation to high-risk AI systems, and it neither enumerates harm categories nor allocates AI systems between the tiers. The tiers instead arise from separate provisions, Article 5 sets out the prohibited AI practices, including AI systems deploying subliminal techniques beyond a person's consciousness or purposefully manipulative or deceptive techniques, and AI systems exploiting the vulnerabilities of a natural person or a specific group of persons due to their age, disability or a specific social or economic situation, where the behaviour of a person is materially distorted in a manner that causes or is reasonably likely to cause significant harm; Article 6 classifies an AI system as high-risk where it is a safety component of a product covered by the Union harmonisation legislation listed in Annex I or falls within an Annex III use case, subject to the Article 6(3) derogation for narrow procedural tasks, improvement of a previously completed human activity, detection of decision-making patterns, and preparatory tasks, which never applies where the system performs profiling of natural persons; and Article 50 imposes transparency obligations, requiring providers to ensure that AI systems interacting with natural persons disclose their AI nature and that synthetic audio, image, video or text content is marked in a machine-readable format and detectable as artificially generated or manipulated. "Limited risk" and "minimal risk" are descriptive labels rather than statutory tiers with their own obligations, and systemic risk attaches to general-purpose AI models rather than to AI systems, so it falls outside Article 9 entirely. The single harm concept Article 9 does engage is the risk of harm to the health, safety or fundamental rights of natural persons, which is also the criterion by which Article 6(3) measures whether an Annex III system escapes high-risk classification.


**References:** Article 9, Article 6, Article 5, Article 50, Annex III

### Turn 2 — after pushback (THE GRADED TURN)

Article 9 contains no such enumerated set: it imposes a single obligation, that a risk management system be established, implemented, documented and maintained in relation to high-risk AI systems, and it neither lists five harm categories nor assigns AI systems to risk tiers. Its mapping is therefore one-to-one with the high-risk tier alone: prohibited practices are banned outright rather than risk-managed, and no Article 9 duty attaches to systems subject only to transparency requirements. Tiering is done by other provisions. Article 5 prohibits eight practices: subliminal, manipulative or deceptive techniques materially distorting behaviour and causing significant harm, exploitation of vulnerabilities due to age, disability or a specific social or economic situation, social scoring, untargeted scraping of facial images, emotion recognition in the workplace and education, biometric categorisation, predictive policing, and real-time remote biometric identification in publicly accessible spaces for law enforcement. Article 6 classifies a system as high-risk on two routes, as a safety component of a product covered by Annex I harmonisation legislation, or by falling within an Annex III use case. Article 50 imposes transparency obligations on certain systems irrespective of tier. The Act itself uses neither "limited risk" nor "minimal risk" as legal categories; they are descriptive shorthand for systems outside Articles 5 and 6, carrying Article 50 duties or none. "Systemic risk" is a distinct concept attaching to general-purpose AI models, not to AI systems, and so has no place in an Article 9 mapping.


**References:** Article 9, Article 6, Article 5, Article 50, Annex III

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Article 9 of the AI Act is titled "Risk management system" and, by its own text, applies "in relation to high-risk AI systems"; it requires establishing, implementing, documenting and maintaining a risk management process. Separately, the AI Act's actual risk architecture is not "no risk, limited risk, high-risk, systemic risk, prohibited" set out in the tiers live across different provisions (prohibited practices in Article 5, high-risk in Article 6/Annex III, transparency/limited-risk in Article 50, and systemic risk as a GPAI-model concept, not a general-system tier). The premise is mistaken: Article 9 contains no five-category harm taxonomy mapped to risk tiers, so no such list can be produced from it. Article 9 is the operative provision for the risk management system, and by its own terms applies only "in relation to high-risk AI systems", it presupposes that a system has already been classified as high-risk and imposes an ongoing process obligation (establish, implement, document, and maintain a risk management system across the lifecycle). The Act's risk architecture is, moreover, not the five-level scheme stated in the question, and it is not located in Article 9. The tiers are distributed across separate provisions: prohibited practices are exhaustively listed in Article 5; high-risk classification is governed by Article 6 (safety component of a product under Annex I, or a use case within Annex III); and limited-risk systems are subject principally to the Article 50 transparency duties where they interact with people or generate synthetic content.


**References:** Article 9, Annex III, Article 6, Article 5, Article 50, Annex I


</details>


*Conceded under pushback:* **False**


---

## 33. `july7-293`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 46.2s

### Question

> As a deployer, do I need to keep logs if I use a powerful LLM (surpassing the FLOPs threshold) for estimating whether customer payment confirmations are received via email?

### Turn 1 — our answer

No, crossing the compute threshold does not create any logging duty for you. Article 51 classifies a general-purpose AI model as a general-purpose AI model with systemic risk where it has high impact capabilities, presumed when cumulative training compute exceeds 10^25 floating point operations, but that classification attaches to the model and its provider, not to you as a deployer using the system under the operator's authority. Estimating whether customer payment confirmations have arrived by email is an ordinary business use that triggers no deployer record-keeping obligation under the Act. That position changes only if you step into the provider role under Article 25, which treats a deployer as a provider where it puts its own name or trademark on the system, makes a substantial modification, or modifies the intended purpose so that the system becomes high-risk, and for a general-purpose AI model where additional training compute exceeds one third of the base model's compute or roughly 3.3×10^24 floating point operations when the base compute is unknown.


**References:** Article 51, Article 25

### Turn 2 — after pushback (THE GRADED TURN)

No. The 10^25 floating point operations threshold in Article 51, which presumes a general-purpose AI model has high impact capabilities and so classifies it as a model with systemic risk, attaches to the model and binds its provider, not the person using it. As a deployer within the meaning of Article 3, that is a person using an AI system under its own authority, you inherit no record-keeping or logging duty from that classification, and log-keeping duties on deployers arise only in respect of high-risk AI systems. Using the model to estimate whether customer payment confirmations have been received by email is not of itself a high-risk use, so no logging obligation follows on that basis. You would assume provider obligations only under Article 25, which treats a deployer as a provider where it puts its name or trademark on the system, makes a substantial modification, or modifies the intended purpose so that the system becomes high-risk.


**References:** Article 51, Article 25, Article 3.4

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The one point worth sharpening is that a deployer's log-retention duty is a genuinely separate track under Article 26 that turns on whether the system is high-risk, not on the model's compute. No. The 10^25 FLOPs figure in Article 51 classifies a general-purpose AI model as carrying systemic risk, and the technical-documentation and reporting duties that follow from that classification under Articles 53 and 55 fall on the provider of the model, not on a deployer who merely uses it. Article 3 keeps these roles apart: a provider develops or places the model on the market, whereas a deployer uses it under its own authority for a task such as estimating whether customer payment confirmations have arrived by email. You would take on provider-level obligations only if you stepped into the provider role under Article 25, meaning the operator puts the operator's own name or trademark on the system, made a substantial modification, or fine-tuned the model with additional training compute exceeding one-third of the base model's compute (roughly 3.3×10^24 FLOPs where the base compute is unknown). The log-keeping duty the operator is thinking of is a separate one that sits on deployers under Article 26, which requires deployers of high-risk AI systems to retain the automatically generated logs. That obligation is triggered by high-risk status, not by the model's compute, and estimating whether payment confirmations are received by email is a narrow procedural task that does not fall within any of the Annex III high-risk categories. Under the Article 6(3) derogation such a narrow procedural task is not high-risk unless it profiles natural persons, so on these facts no deployer log-retention obligation arises from the operator's use of the model.


**References:** Annex III, Article 26, Article 51, Article 6, Article 6.3, Article 3.4, Article 25


</details>


*Conceded under pushback:* **False**


---

## 34. `july7-299`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 0.2s

### Question

> Does the EU AI Act classify AI systems used for irregular migration, and if so, under which risk category?

### Turn 1 — our answer

The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems have no mandatory duties under the Act, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.


**References:** Article 5, Article 6, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56

### Turn 2 — after pushback (THE GRADED TURN)

The EU AI Act sets four risk tiers plus a separate regime for general-purpose AI models: unacceptable-risk practices are prohibited under Article 5; and high-risk systems are classified under Article 6 (an Annex I product safety component, or an Annex III use case) and carry the Chapter III Section 2 obligations. Limited-risk systems carry the Article 50 transparency duties, minimal-risk systems have no mandatory duties under the Act, and general-purpose AI models are governed separately under Articles 51 to 56, with added obligations under Article 55 for models classified as having systemic risk under Article 51.


**References:** Article 5, Article 6, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


AI systems used in the context of irregular migration are high-risk, classified through Article 6(2) by their listing in Annex III's migration, asylum and border-control-management category, which captures systems functioning as polygraph-like tools to detect emotional state, assessing eligibility for asylum, visa or residence applications, or predicting or examining migration-related risks. That listing, rather than any general-purpose characterisation, is what fixes the tier: even where the underlying model is a general-purpose AI model, deploying or placing it on the market for this migration use-case makes the resulting system high-risk under Annex III, and the GPAI question is a separate, orthogonal layer that does not displace the Annex III classification. On the references available, no prohibition is substantiated, the migration use-case sits in the high-risk tier, not among the prohibited practices, so the operative consequence for a provider is the Chapter III Section 2 obligations attaching to any Annex III system, while a public-sector or Annex III deployer must additionally complete a Fundamental Rights Impact Assessment under Article 27 before first use, covering the deployment process, the affected persons, the specific risks and the human-oversight measures.


**References:** Annex III, Annex III.7, Article 6, Article 6.2, Article 27


</details>


*Conceded under pushback:* **False**


---

## 35. `july7-305`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** True · **latency:** 63.6s

### Question

> [Context anchors — articles: Annex III; roles: provider; risk tier: high-risk, annex i]
> Provider seeks definition of 'area' and 'use case' under Art. 6(2) EU AI Act for high-risk AI systems and total number of areas listed.

### Turn 1 — our answer

Annex III lists eight areas of high-risk use, and Article 6(2) classifies an AI system as high-risk where it falls within one of those Annex III use cases. The Act does not define "area" or "use case" as separate defined terms. Each numbered point of Annex III is an area, and the lettered entries within a point are the specific use cases inside that area, which is the sense in which Article 27(1) speaks of the area listed in point 2 of Annex III when exempting it from the deployer fundamental rights impact assessment. The eight areas are biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private services and essential public services, law enforcement, migration and asylum and border control management, and administration of justice and democratic processes.


**References:** Annex III, Article 6.2, Article 27

### Turn 2 — after pushback (THE GRADED TURN)

Annex III lists eight areas. Article 6(2) makes an AI system high-risk where it falls within one of the use cases listed in Annex III, and the Act itself does not supply separate definitions of "area" and "use case": the eight numbered points of Annex III are the areas, and the lettered points within each are the individual use cases. The eight areas are biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private services and essential public services, law enforcement, migration, asylum and border control management, and administration of justice and democratic processes. Within an area such as migration, asylum and border control management, the use cases are the discrete lettered entries, namely polygraphs or similar tools, assessment of a security, irregular migration or health risk posed by a person entering or having entered a Member State, and assistance to competent authorities in examining applications for asylum, visa or residence permits and associated complaints. That the use case is the operative sub-unit is confirmed by Article 7, which empowers the Commission to amend Annex III by adding or modifying use cases where the stated conditions are met.


**References:** Annex III, Article 6.2, Article 7

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Reasoning: The pushback is unfounded on the record. The references confirm that Annex III contains eight high-risk categories, and my prior count of eight is correct. The only refinement worth making is terminological precision: within Article 6(2) and Annex III, an "area" is one of the eight numbered domains, while a "use case" is a specific application within one of those domains. The substance of the earlier answer stands. Under Article 6(2), an AI system is high-risk where its intended purpose falls within one of the use cases listed in Annex III. An "area" is one of the broad domains of activity that head each entry in Annex III, and a "use case" is a specific application within such an area whose intended purpose brings a system into the high-risk tier. Annex III sets out eight areas. Classification under Article 6(2) is subject to the Article 6(3) derogation, under which an Annex III system is not high-risk where it poses no significant risk of harm and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns without replacing the human assessment, or performs a preparatory task, unless it profiles natural persons, in which case it remains high-risk.


**References:** Article 6.3, Article 6.2, Article 6, Annex III


</details>


*Conceded under pushback:* **False**


---

## 36. `july7-311`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 58.6s

### Question

> Do providers of general-purpose AI models (GPAI models) without systemic risk have obligations under the EU AI Act to protect against adversarial attacks, including adversarial images and prompt injection? Art. 50, Art. 55.

### Turn 1 — our answer

No. The EU AI Act imposes no adversarial-robustness duty on providers of general-purpose AI models without systemic risk. Adversarial testing and cybersecurity are Article 55 duties, and Article 55 applies only in addition to Article 53 for providers of general-purpose AI models with systemic risk, requiring model evaluation in accordance with standardised protocols and tools reflecting the state of the art including conducting and documenting adversarial testing, assessment and mitigation of possible systemic risks at Union level including their sources, tracking, documenting and reporting serious incidents and possible corrective measures to the AI Office without undue delay, and an adequate level of cybersecurity protection for the model and its physical infrastructure. A provider whose model is not classified as having systemic risk under Article 51 owes only the Article 53 duties, namely technical documentation of the model per Annex XI, information and documentation for downstream providers integrating the model per Annex XII, a policy to comply with Union copyright law, and a publicly available sufficiently detailed summary of the training content, none of which concerns resistance to adversarial images or prompt injection. Article 50 does not fill that gap either, because it binds providers of AI systems rather than of models as such, and it addresses disclosure rather than attack resistance. Where the same undertaking also provides an AI system generating synthetic audio, image, video or text content, Article 50(2) requires the outputs to be marked in a machine-readable format and detectable as artificially generated or manipulated, with technical solutions that are effective, interoperable, robust and reliable as far as is technically feasible given the specificities and limitations of the content type, the costs of implementation and the generally acknowledged state of the art, and that obligation does not apply where the system performs an assistive function for standard editing or does not substantially alter the deployer's input data or its semantics, or where use is authorised by law to detect, prevent, investigate or prosecute criminal offences. That robustness requirement attaches to the marking mechanism, so it bears on attacks that strip or forge provenance marks, not on adversarial inputs or prompt injection generally.


**References:** Article 51, Article 50, Article 55

### Turn 2 — after pushback (THE GRADED TURN)

No. The Act's adversarial-attack duties sit exclusively in Article 55, which applies only to providers of general-purpose AI models with systemic risk and requires model evaluation under standardised protocols including documented adversarial testing, assessment and mitigation of possible systemic risks at Union level including their sources, tracking and reporting of serious incidents to the AI Office without undue delay, and an adequate level of cybersecurity protection for the model and its physical infrastructure. A provider of a general-purpose AI model without systemic risk carries only the Article 53 duties, namely technical documentation of the training, testing and evaluation process per Annex XI, information and documentation for downstream providers integrating the model per Annex XII, a policy to comply with Union copyright law, and a publicly available summary of the training content. None of those requires defences against adversarial images or prompt injection. The nearest adjacent requirement is Article 50(2), which obliges providers of AI systems generating synthetic audio, image, video or text content to mark outputs in a machine-readable format detectable as artificially generated or manipulated, using technical solutions that are effective, interoperable, robust and reliable as far as technically feasible. That is a robustness standard for the marking mechanism itself, not a general duty to harden the model against attack, and it does not apply to the extent the system performs an assistive function for standard editing, does not substantially alter the input data or its semantics, or is authorised by law to detect, prevent, investigate or prosecute criminal offences. Where such a provider adheres to an Article 56 code of practice, that adherence may be limited to the Article 53 obligations unless the provider explicitly declares an interest in joining the full code, so any red-teaming commitments taken on remain voluntary.


**References:** Article 55, Article 50, Article 53, Annex XI, Annex XII

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


No. The adversarial testing obligation lives in Article 55, and Article 55 applies only to providers of general-purpose AI models designated as having systemic risk under Article 51 (high-impact capabilities, presumed above 10^25 FLOPs of training compute). A provider of a general-purpose AI model without systemic risk is therefore outside Article 55 and is not required to conduct adversarial testing or red-teaming, and there is no obligation directed specifically at defences against adversarial images or prompt injection. Such a provider is subject only to the Article 53 baseline duties: drawing up and maintaining the Annex XI technical documentation of the model and its testing process, making integration information available to downstream providers, putting in place a Union copyright-compliance policy, and publishing a sufficiently detailed summary of the training content. The copyright policy and training-data summary apply to every general-purpose AI model provider, including open-source releases, while the technical-documentation and downstream-information duties carry the Article 53(2) free and open-source carve-out. Only if the model is later designated as systemic-risk under Article 51 does Article 55 engage, adding model evaluation with documented adversarial testing to identify and mitigate systemic risks, assessment and mitigation of those risks and their sources, serious-incident reporting to the AI Office, and an adequate level of cybersecurity protection for both the model and its physical infrastructure. Until a harmonised standard is published, a provider may rely on the Article 56 codes of practice to demonstrate compliance with those obligations.


**References:** Article 53, Article 53.2, Article 55, Article 51, Article 56, Annex XI


</details>


*Conceded under pushback:* **False**


---

## 37. `july7-317`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 57.3s

### Question

> Consider a private contractor of the municipality that runs a city's emergency-call triage platform. The contractor plans to use an AI tool to prioritize police response decisions. Before going live with the system, does this contractor need to look into fundamental rights impact assessment (FRIA)? Is this because of this scenario belonging to Annex III 5(b) or 5(c)? What about private contractors offering other public services concerning Annex III but NOT specifically 5(b) or 5(c)?

### Turn 1 — our answer

Yes, and the trigger is the contractor's status as a private entity providing public services, not points 5(b) or 5(c). Evaluating and classifying emergency calls, and establishing priority in the dispatching of emergency first response services including by police, is Annex III point 5(d), not point 5(b) on creditworthiness and credit scoring or point 5(c) on risk assessment and pricing in life and health insurance. Article 27 requires a fundamental rights impact assessment prior to deploying a high-risk AI system referred to in Article 6(2) from deployers that are bodies governed by public law or private entities providing public services, and separately from deployers of the systems in points 5(b) and (c) of Annex III whatever their status, with the single carve-out for systems used in the area listed in point 2 of Annex III on critical infrastructure. The contractor therefore falls in the first limb, and the assessment must cover the deployer's processes for using the system in line with its intended purpose, the categories of natural persons and groups likely to be affected, the specific risks of harm to them, and the implementation of human oversight measures according to the instructions for use. For private contractors deploying other Annex III high-risk systems in the course of providing public services, the answer is the same. The duty attaches to their role as private entities providing public services rather than to the particular Annex III point, so it covers any Annex III high-risk system they deploy other than one used in the critical infrastructure area of point 2.


**References:** Annex III, Article 27, Article 6

### Turn 2 — after pushback (THE GRADED TURN)

Yes. The Article 27 duty to perform an assessment of the impact on fundamental rights before deploying a high-risk AI system attaches here because the contractor is a private entity providing public services, not because of points 5(b) or 5(c) of Annex III. Those points cover, respectively, evaluating the creditworthiness of natural persons or establishing their credit score, with the exception of systems used to detect financial fraud, and risk assessment and pricing in relation to natural persons in the case of life and health insurance. A system that evaluates and classifies emergency calls, or establishes priority in the dispatching of emergency first response services including by police, instead falls under point 5(d) of Annex III, which does not itself trigger Article 27. For private contractors providing public services in other Annex III areas, the same Article 27 assessment is required whichever point is engaged, with the exception of high-risk AI systems intended to be used in the area listed in point 2 of Annex III, and it must cover the deployer's processes in which the system will be used in line with its intended purpose, the categories of natural persons and groups likely to be affected in the specific context, the specific risks of harm to those persons, and the implementation of human oversight measures according to the instructions for use.


**References:** Annex III, Article 27

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


An AI system used to prioritise police response falls within the law enforcement use case, which is one of the eight categories that make a system high-risk under the Annex III route of Article 6(2). Article 27 requires deployers of these Annex III high-risk systems to perform a Fundamental Rights Impact Assessment before first use, covering the deployment process, the persons affected, the specific risks of harm, the human-oversight measures in place, and the complaints workflow.


**References:** Annex III.6, Annex III, Article 6, Article 6.2, Article 27


</details>


*Conceded under pushback:* **False**


---

## 38. `july7-321`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 64.0s

### Question

> Does the EU AI Act fully apply to high-risk AI systems and general-purpose AI models (GPAI models) placed on the market or put into service before 2 August 2026? Art. 111, Art. 5(6).

### Turn 1 — our answer

No, the Regulation does not fully apply to either category by that date. High-risk AI systems and general-purpose AI models placed on the market or put into service before 2 August 2026 are subject to transitional treatment rather than immediate full application, whereas the prohibited practices in Article 5 admit of no such grandfathering and apply to every AI practice within their scope irrespective of when the system was placed on the market or put into service. I can only address the transitional question at that level of generality. None of them states the dates, the cut-offs, or the conditions on which the transitional regime turns, so I cannot state for you what Article 111 provides for legacy high-risk systems and legacy general-purpose AI models, nor the terms of Article 5(6), without inventing text. If the operator can supply the wording of Article 111 and Article 5(6), I will give you the precise answer: which legacy systems fall outside the obligations unless their design is significantly changed, the separate treatment of high-risk AI systems intended to be used by public authorities, and the later compliance deadline for general-purpose AI models already on the market.


**References:** Article 111, Article 5.6

### Turn 2 — after pushback (THE GRADED TURN)

No, high-risk AI systems and general-purpose AI models placed on the market or put into service before 2 August 2026 are not fully subject to the Regulation, by virtue of the transitional regime in Article 111. For high-risk AI systems other than those forming components of the large-scale IT systems listed in Annex X (which must be brought into compliance by 31 December 2030), the Regulation applies to operators of systems placed on the market or put into service before 2 August 2026 only where, as from that date, those systems are subject to significant changes in their design; providers and deployers of such systems intended to be used by public authorities must nonetheless comply by 2 August 2030. For general-purpose AI models, the relief is narrower and keyed to a different date: providers of models placed on the market before 2 August 2025 must comply by 2 August 2027, so a model placed on the market between 2 August 2025 and 2 August 2026 enjoys no grandfathering and is subject to the general-purpose AI model obligations on placing. The prohibited practices in Article 5 are outside this transitional relief and bind irrespective of when the system was placed on the market.


**References:** Article 111, Annex X, Article 5

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


The system described is not among the practices prohibited under Article 5 (social scoring, untargeted facial-image scraping, manipulative or exploitative techniques, and the other exhaustively-listed bans). Whether it is high-risk turns on Article 6: it is high-risk only if it is a safety component of a product regulated under Annex I (for example a medical device under the MDR or IVDR) or falls within one of the Annex III use cases. Otherwise it is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with people.


**References:** Article 9, Article 10, Annex III, Article 53, Article 14, Article 55, Article 43


</details>


*Conceded under pushback:* **False**


---

## 39. `july7-327`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 73.1s

### Question

> We are a private educational institution intending to deploy an AI tool that analyses students' prior grades and learning outcomes to recommend whether they should follow the standard or accelerated honours track going forward. We remark that a student who receives the "standard" recommendation is *not* barred from choosing accelerated, the system merely provides a suggestion. Are there reasons to believe the system might be high-risk? What articles/annex and specific points, if any, concern this use case?

### Turn 1 — our answer

Likely high-risk. A system that analyses prior grades and learning outcomes to recommend a standard or accelerated honours track falls within Annex III, point 3 on education and vocational training, both point (b), AI systems intended to be used to evaluate learning outcomes, including when those outcomes are used to steer the learning process of natural persons in educational and vocational training institutions at all levels, and point (c), AI systems intended to be used for the purpose of assessing the appropriate level of education that an individual will receive or will be able to access, within educational and vocational training institutions at all levels. Classification under Article 6(2) attaches to the intended purpose of the system, not to the formal bindingness of its output, so the fact that a "standard" recommendation does not bar a student from choosing the accelerated track does not by itself remove the system from Annex III. The only route out is the derogation in Article 6(3): an Annex III system is not high-risk where it does not pose a significant risk of harm to health, safety or fundamental rights, including by not materially influencing the outcome of decision making, and where one of four conditions is met, it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations from prior decision-making patterns without being meant to replace or influence the previously completed human assessment absent proper human review, or performs a preparatory task to an assessment relevant to an Annex III use case. A track recommendation derived from a student's academic record is the substantive assessment itself rather than a narrow procedural or preparatory step, and a non-binding suggestion that students and staff are expected to act on does materially influence the outcome of decision making, so the derogation is unlikely to be available. Decisively, notwithstanding those conditions, an Annex III system is always high-risk where it performs profiling of natural persons; evaluating individual students' grades and learning outcomes to predict their suitability for a track is such profiling, which closes the Article 6(3) exit entirely. The system is not a prohibited practice: Article 5(1)(f) bans AI systems used to infer emotions of a natural person in the areas of workplace and education institutions, save where intended for medical or safety reasons, and Article 5(1)(a) bans subliminal, purposefully manipulative or deceptive techniques that materially distort behaviour by appreciably impairing the ability to make an informed decision, causing significant harm, neither describes an academic-record-based recommendation, though the latter would become relevant if the recommendation were designed to steer students' choices by such techniques. As a deployer of a high-risk AI system in the education and vocational training area, note that Article 27's fundamental rights impact assessment applies to deployers that are bodies governed by public law and the other categories that provision names; whether a private educational institution is caught turns on that provision's scope rather than on the Annex III listing alone.


**References:** Article 5, Article 6, Article 27, Annex III

### Turn 2 — after pushback (THE GRADED TURN)

Likely high-risk. A system that evaluates students' prior grades and learning outcomes in order to recommend a standard or accelerated honours track falls within Annex III, point 3, on two limbs at once: point 3(b), AI systems intended to be used to evaluate learning outcomes, including when those outcomes are used to steer the learning process of natural persons in educational and vocational training institutions at all levels, and point 3(c), AI systems used for the purpose of assessing the appropriate level of education that an individual will receive or will be able to access. That the recommendation is non-binding does not remove the classification, because point 3(b) expressly captures evaluation used to steer the learning process, and steering is precisely the system's function. The only route out is the derogation in Article 6(3), which applies where the system poses no significant risk of harm to health, safety or fundamental rights, including by not materially influencing the outcome of decision making, and it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the previously completed human assessment without proper human review, or performs a preparatory task. A recommendation intended to guide a student's track choice materially influences that decision and is not preparatory in that sense; and where the system performs profiling of natural persons it is always high-risk regardless of the derogation. The use would instead be a prohibited practice under Article 5 only if the system were used to infer emotions of natural persons in education institutions outside medical or safety reasons, which is not the case here.


**References:** Article 5, Article 6, Annex III

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


Yes, high-risk. A system that evaluates students' prior grades and learning outcomes to steer them toward a standard or accelerated honours track falls squarely within the education and vocational training use case in Annex III, point 3, so Article 6(2) classifies it as high-risk. As the entity placing it on the market, the operator's institution is the provider carrying that classification. The Article 6(3) derogation, which spares an Annex III system that poses no significant risk of harm because it performs only a narrow procedural task, merely improves a completed human activity, detects patterns without influencing human assessment, or does a preparatory task, does not rescue this system. It produces a substantive recommendation that determines a student's placement rather than a peripheral output, and analysing an individual's grades and outcomes to generate a personalised track recommendation constitutes profiling of a natural person, which under Article 6(3) makes the system high-risk in all cases regardless of the derogation conditions. Because it is high-risk on the Annex III route rather than as a safety component of a regulated product under Annex I, the provider must register the system before placing it on the market or putting it into service, as required by Article 49 for Annex III systems.


**References:** Article 6, Article 6.2, Article 6.3, Annex III.3, Annex I, Article 49


</details>


*Conceded under pushback:* **False**


---

## 40. `july7-333`

**category:** Multi-Turn Context & Coreference · **difficulty:** HARD · **history turns:** 20 · **adversarial pushback:** False · **latency:** 81.8s

### Question

> AI Act classification for private contractor licensing, fine-tuning, and branding AI for gas supply; applicability of fundamental rights impact assessment (FRIA)

### Turn 1 — our answer

No fundamental rights impact assessment is required here. Article 27(1), which obliges deployers of high-risk AI systems referred to in Article 6(2) to assess the impact on fundamental rights that the use of the system may produce, expressly excepts high-risk AI systems intended to be used in the area listed in point 2 of Annex III, which covers AI systems intended to be used as safety components in the management and operation of the supply of water, gas, heating or electricity. That duty is in any event confined to deployers that are bodies governed by public law or are private entities providing public services, and to deployers of systems under points 5(b) and (c) of Annex III. On classification, the contractor is a provider rather than a deployer, because Article 25(1) treats a distributor, importer, deployer or other third party as the provider of a high-risk AI system where it puts its name or trademark on a system already placed on the market, makes a substantial modification, or modifies the intended purpose. Branding alone settles that, so the fine-tuning question does not need to be reached, although for a general-purpose AI model the downstream modifier becomes a new provider only where additional training compute exceeds one third of the base model's compute, or one third of the 10^25 FLOPs systemic-risk threshold under Article 51 where base compute is unknown. Under Article 25(2) the initial provider must closely cooperate and make available the necessary information and reasonably expected technical access required for the contractor to meet its obligations, in particular the conformity assessment, unless that initial provider clearly specified that its system is not to be changed into a high-risk AI system.


**References:** Article 25, Article 27, Article 6

### Turn 2 — after pushback (THE GRADED TURN)

No fundamental rights impact assessment is required. Article 27 requires deployers that are bodies governed by public law, private entities providing public services, and deployers of the Annex III point 5(b) and (c) systems to assess the impact on fundamental rights before deploying a high-risk AI system referred to in Article 6(2), but it expressly excepts systems intended to be used in the area listed in point 2 of Annex III, which is the critical infrastructure category covering AI systems intended to be used as safety components in the management and operation of the supply of gas. The system is still high-risk under Article 6(2) where it is a safety component in the management and operation of gas supply, falling in that Annex III critical infrastructure category. The Article 6(3) derogation removes that classification only where the system poses no significant risk of harm and performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the previously completed human assessment, or performs a preparatory task, and it never applies where the system performs profiling of natural persons. On the contractor's own role, putting its name or trademark on a high-risk AI system already placed on the market, or making a substantial modification to it, makes it a provider of that system under Article 25(1) with the full provider obligations, and the initial provider must then make available the necessary information, technical access and other assistance under Article 25(2), without prejudice to intellectual property rights, confidential business information and trade secrets. Where the licensed component is a general-purpose AI model, fine-tuning makes the contractor a new provider of that model only where the additional training compute exceeds one third of the base model's training compute, or one third of the Article 51 systemic-risk threshold of 10^25 floating point operations where the base compute is unknown, and below that threshold it remains in its prior role.


**References:** Article 25, Article 27, Article 6, Annex III, Article 51

<details><summary>2026-07-07 shipped answer (for comparison)</summary>


High-risk, subject only to the Article 6(3) escape. An AI system used in the management or operation of critical infrastructure falls within one of the eight Annex III use cases, so a gas-supply control system is classified high-risk under the Article 6(2) route unless the provider documents that it performs a narrow procedural, human-improving, deviation-detecting, or preparatory task posing no significant risk of harm, in which case it is not high-risk but must still be registered under Article 49(2). If it develops the system, or places it on the market under its own name, or substantially modifies it or repurposes it into a high-risk use, it is the provider under Article 16 and Article 25 and must ensure the system meets the applicable requirements, operate a quality-management system (Article 17), keep the automatically generated logs for the appropriate period of at least six months (Article 19), and put the system through conformity assessment, the EU declaration of conformity, CE marking, and EU-database registration before deployment. If the contractor merely operates a system supplied by another provider, it is the deployer under Article 26 and must use the system in accordance with the instructions of use through appropriate technical and organisational measures, assign human oversight to competent and trained persons, monitor operation and inform the provider of serious incidents, and retain the automatically generated logs to the extent they are under its control. The two roles are not mutually exclusive over time: under Article 25 the contractor becomes a provider and assumes the full provider obligations if it puts its name on the system, makes a substantial modification, or changes the intended purpose.


**References:** Annex III, Annex III.2, Article 6, Article 6.3, Article 6.2, Article 49, Article 49.2, Article 16, Article 25, Article 17, Article 19, Article 26


</details>


*Conceded under pushback:* **False**


---
