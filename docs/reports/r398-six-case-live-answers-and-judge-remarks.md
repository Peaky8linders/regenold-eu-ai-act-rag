# Regenold EU AI Act appendix: six cases, live re-run and judge remarks
- Live capture: `2026-09-09T11:28:38`, build `3007956`
- Judge: `claude-sonnet-5`, temperature 0.1, 3 repetitions, per-criterion majority, ties resolve to FAIL
- Stage-2 transport over the run: `{"primary_attempts": 9, "primary_ok": 9, "primary_failed": 0, "fallback_attempts": 0, "fallback_ok": 0, "fallback_failed": 0, "refused": 0, "refused_by_provider": {}}`
- Result: **17/17 printed criteria satisfied** (August 25: 1/17)
- Criteria and the August answers are verbatim from `report_antifragile_ai.pdf`, Appendix, pages 10 to 14.

---

## Q45 (rg_046, easy mode)

**Question**

> Under the EU AI Act, what must a provider of a high-risk AI system supply to the deployer in the instructions for use? List the required categories of information.

### August 25 answer (0/5 criteria)

References provided: `Article 6, Article 13` | Expected: `Article 13.3` | 425 chars | Ans. Conciseness 100.0

> The question asks what a provider of a high-risk AI system must include in the instructions for use. The Act does specify those categories in Article 13, but the materials available here do not permit a citation-supported enumeration of them. A complete answer to this question turns on Article 13 and, for the detailed content list, on the requirements it sets out for transparency and provision of information to deployers.

**Report judgement**

1. `[FAIL]` **Provider and if applicable authorised representative contact details**  
    _The candidate answer does not list any required category of information and does not mention provider or authorised representative contact details._
2. `[FAIL]` **Intended purpose and risks**  
    _The candidate answer refers generally to Article 13 and transparency requirements but does not identify intended purpose or risks as required categories._
3. `[FAIL]` **Human oversight measures**  
    _The candidate answer does not mention human oversight measures._
4. `[FAIL]` **Required computational resources/hardware, expected lifetime, maintaince measures**  
    _The candidate answer does not mention computational resources, hardware requirements, expected lifetime, or maintenance measures._
5. `[FAIL]` **Info about logging mechanisms**  
    _The candidate answer does not mention information about logging mechanisms._

### Current live answer (5/5 criteria)

References shipped: `Article 13.3, Article 9.5` | 1,695 chars | Ans. Conciseness 58.1 | latency 25.9s | judge spread [1.0, 1.0, 1.0]

> Article 13 requires the provider to design a high-risk AI system for sufficient operational transparency and to supply it with instructions for use in an appropriate digital or other format, concise, complete, correct and clear, in a language easily understood by deployers. Those instructions must contain six categories of information: the identity and contact details of the provider and, where applicable, its authorised representative, the characteristics, capabilities and limitations of performance of the system including its intended purpose, the levels of accuracy including accuracy metrics, robustness and cybersecurity required under Article 15, any known or foreseeable circumstances that may lead to risks to health, safety or fundamental rights, the technical capabilities to provide information relevant to explaining its output, performance as regards specific persons or groups on which the system is intended to be used and input data specifications, the changes to the system and its performance pre-determined by the provider at the moment of the initial conformity assessment, the human oversight measures under Article 14 including the technical measures enabling deployers to interpret output, the computational and hardware resources needed, the expected lifetime and the maintenance and care measures including software updates, and, where relevant, a description of the mechanisms allowing deployers to properly collect, store and interpret the logs generated under Article 12. Article 9 reinforces this by treating the provision of that information, and where appropriate training to deployers, as a risk management measure where risk cannot be eliminated by design.

**Judge remarks (this run)**

1. `[PASS]` **Provider and if applicable authorised representative contact details**  
    _States identity and contact details of provider and, where applicable, authorised representative._
2. `[PASS]` **Intended purpose and risks**  
    _States intended purpose and known/foreseeable circumstances that may lead to risks to health, safety or fundamental rights._
3. `[PASS]` **Human oversight measures**  
    _States human oversight measures under Article 14 including technical measures enabling deployers to interpret output._
4. `[PASS]` **Required computational resources/hardware, expected lifetime, maintaince measures**  
    _States computational and hardware resources needed, expected lifetime, and maintenance/care measures including software updates._
5. `[PASS]` **Info about logging mechanisms**  
    _States the mechanism description allowing deployers to collect, store and interpret logs under Article 12._

Tone: `PASS` _Professional third-person register throughout, though dense, with clearly enumerated categories a compliance professional could follow._

---

## Q96 (rg_097, easy mode)

**Question**

> Name the areas of high-risk use cases. Is healthcare decision making one of them?

### August 25 answer (0/2 criteria)

References provided: `None` | Expected: `Annex III` | 375 chars | Ans. Conciseness 100.0

> I cannot answer your question from my Knowledge Graph, which address only obligations under Regulation (EU) 2024/1689 (the AI Act), such as AI literacy duties for providers and deployers (Article 4), coordination of notified bodies (Article 38), and access to the Scientific Panel's expert pool (Article 69). If you have a question about AI Act compliance, I am glad to help.

**Report judgement**

1. `[FAIL]` **(Shortened:) Biometrics; Critical infrastructure; Education; Employment; Access/enjoyment essential services; Law enforcement; Migration/asylum/border control; Justice/democracy administration**  
    _The candidate answer does not name any of the high-risk areas listed in the AI Act Annex III. It instead says it cannot answer and discusses unrelated AI Act obligations._
2. `[FAIL]` **No**  
    _The candidate answer does not address whether healthcare decision making is one of the high-risk areas. The correct evaluation expected here is `No', but the answer provides no such response._

### Current live answer (2/2 criteria)

References shipped: `Annex III, Article 6, Annex I` | 1,182 chars | Ans. Conciseness 54.7 | latency 14.1s | judge spread [1.0, 1.0, 1.0]

> Annex III lists eight high-risk areas: biometrics, critical infrastructure, education and vocational training, employment and worker management, access to and enjoyment of essential private services and essential public services and benefits, law enforcement, migration, asylum and border control management, and administration of justice and democratic processes. Healthcare decision making is not itself one of those areas, and under Article 6(2) only a listed lettered use-case within an area makes a system high-risk. Clinical decision making is nonetheless captured in part: Annex III point 5 covers systems used by or on behalf of public authorities to evaluate eligibility for essential public assistance benefits and services, including healthcare services, risk assessment and pricing in life and health insurance, and emergency healthcare patient triage systems. Separately, Article 6(1) classifies as high-risk an AI system that is a safety component of, or is itself, a product covered by the Union harmonisation legislation in Annex I, which includes the in vitro diagnostic medical devices Regulation, where that product must undergo third-party conformity assessment.

**Judge remarks (this run)**

1. `[PASS]` **(Shortened:) Biometrics; Critical infrastructure; Education; Employment; Access/enjoyment essential services; Law enforcement; Migration/asylum/border control; Justice/democracy administration**  
    _Answer lists all eight areas matching the criteria._
2. `[PASS]` **No**  
    _Answer states healthcare decision making is not itself one of the areas._

Tone: `PASS` _Professional, neutral third-person register with well-organized, coherent structure._

---

## Q17 (rg_018, easy mode)

**Question**

> Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?

### August 25 answer (1/4 criteria)

References provided: `Annex III, Article 97, Article 7.1, Article 7, Article 6` | Expected: `Article 7.1` | 678 chars | Ans. Conciseness 78.6

> The Commission is empowered to amend Annex III by adding new use cases or modifying existing ones through delegated acts adopted in accordance with Article 97, subject to the conditions set out in Article 7(1). Article 6(2) makes the Annex III use cases high-risk, and Article 6(6) empowers the Commission to adopt delegated acts to amend the derogation conditions in Article 6(3), but the power to amend the list of use cases in Annex III itself is conferred by a separate provision (Article 7) that the Act does not settle within the text supplied here. The Act does not specify the full conditions for amending Annex III within the provisions of Article 6 or Annex III alone.

**Report judgement**

1. `[PASS]` **Yes**  
    _The candidate answer clearly states that the Commission is empowered to amend Annex III by adding new use cases or modifying existing ones through delegated acts. This matches the required `Yes'._
2. `[FAIL]` **Condition: AI intended to be used in any of the areas listed in Annex III**  
    _The candidate answer refers generally to conditions in Article 7(1) but does not state the specific condition that the AI system must be intended to be used in one of the areas listed in Annex III. Because the required substantive condition is omitted, this aspect is not satisfied._
3. `[FAIL]` **Condition: posed risk is equal or greater than those already referred to in Annex III**  
    _The candidate answer does not state the specific threshold condition that the AI system must pose a risk of harm to health, safety, or fundamental rights that is equal to or greater than the risk posed by the high-risk AI systems already listed in Annex III. It only mentions unspecified conditions in Article 7(1)._
4. `[FAIL]` **Both condition must apply ("and" clause)**  
    _The candidate answer does not explain that both conditions must be met cumulatively. It references Article 7(1) in general terms but does not articulate the conjunctive requirement._

### Current live answer (4/4 criteria)

References shipped: `Annex III.7.b, Article 97.2, Article 7.1` | 1,542 chars | Ans. Conciseness 34.6 | latency 12.4s | judge spread [1.0, 1.0, 1.0]

> Yes, the Commission may amend Annex III by adding or modifying use-cases of high-risk AI systems, but only through delegated acts adopted in accordance with Article 97 and only where two conditions are cumulatively fulfilled under Article 7(1): the AI systems are intended to be used in one of the areas already listed in Annex III, and they pose a risk of harm to health and safety, or an adverse impact on fundamental rights, that is equivalent to or greater than that posed by the high-risk AI systems already listed there. Neither limb alone suffices, and in assessing the second the Commission must weigh the criteria in Article 7(2), including the intended purpose, the extent of use, the nature and amount of data processed, the degree of autonomy, the severity and reversibility of harm, and the availability of effective measures of redress or of measures to prevent or substantially minimise the risks. Article 97 frames the procedure: the delegation runs for five years from 1 August 2024 with tacit extension unless the European Parliament or the Council opposes it, the Commission must consult experts designated by each Member State before adoption, and the act enters into force only if neither institution objects within three months of notification, extendable by a further three months. Article 7(3) separately allows removal of a use-case from Annex III where it no longer poses any significant risk to fundamental rights, health or safety and the deletion does not decrease the overall level of protection under Union law.

**Judge remarks (this run)**

1. `[PASS]` **Yes**  
    _Answer clearly states 'Yes' as its position._
2. `[PASS]` **Condition: AI intended to be used in any of the areas listed in Annex III**  
    _States AI systems must be intended to be used in one of the areas listed in Annex III._
3. `[PASS]` **Condition: posed risk is equal or greater than those already referred to in Annex III**  
    _States the risk must be equivalent to or greater than that posed by high-risk AI systems already in Annex III._
4. `[PASS]` **Both condition must apply ("and" clause)**  
    _States the two conditions are 'cumulatively fulfilled' and 'neither limb alone suffices'._

Tone: `PASS` _Professional, well-structured third-person explanation with no self-reference or hedging._

---

## Q74 (rg_075, hard mode)

**Question**

> I generated audio with AI for my artistic work (sole purpose). Do I need to provide some marking of its artificial nature? I feel that would compromise the enjoyment of the work.

### August 25 answer (0/2 criteria)

References provided: `Article 9, Article 50.2, Article 50, Article 50.4` | Expected: `Article 50.4` | 859 chars | Ans. Conciseness 68.3

> Yes. The provider of an AI system generating synthetic audio must ensure the outputs are marked in a machine-readable format and detectable as artificially generated or manipulated, with technical solutions that are effective, interoperable, robust and reliable, under Article 50(2). Artistic purpose is not a carve-out from that marking duty, which is displaced only to the extent the system performs an assistive function for standard editing or does not substantially alter the input data or its semantics, or where authorised by law to detect, prevent, investigate or prosecute criminal offences. The artistic, creative, satirical or fictional limitation applies to the separate deployer duty to disclose deep fake content under Article 50(4), where disclosure is limited to an appropriate manner that does not hamper the display or enjoyment of the work.

**Report judgement**

1. `[FAIL]` **No need of marking that would compromise enjoyment**  
    _The candidate answer says `Yes' and states that the provider must ensure synthetic audio outputs are marked under Article 50(2), and explicitly says artistic purpose is not a carve-out from that marking duty. This does not reflect the required point that there is no need for marking in a way that would compromise enjoyment of the artistic work._
2. `[FAIL]` **Still required: other form of disclosure that such content exist (must be unambiguous in the answer)**  
    _The answer does mention the artistic/creative limitation for the separate deployer duty under Article 50(4), saying disclosure is limited to an appropriate manner that does not hamper display or enjoyment. However, it does not unambiguously answer the user's practical question as `no, not that kind of marking, but yes, some other disclosure is still required.' Instead, it foregrounds a `Yes' to marking and frames the enjoyment-safe disclosure only as a secondary distinction. So the required unambiguous statement is not satisfied._

### Current live answer (2/2 criteria)

References shipped: `Article 50.4` | 984 chars | Ans. Conciseness 59.7 | latency 30.6s | judge spread [0.5, 1.0, 1.0]

_Turn 1 before pushback: 1,202 chars, refs `Article 50.4`_

> Yes, marking is required, but it need not intrude on the work. As the provider of the AI system generating synthetic audio, Article 50(2) requires the output to be marked in a machine-readable format and detectable as artificially generated or manipulated, using solutions that are effective, interoperable, robust and reliable, with exemptions only for standard editing functions that do not substantially alter the input data or for use authorised by law to detect, prevent, investigate or prosecute criminal offences. That marking is embedded metadata or watermarking rather than a visible or audible notice, so it does not affect how the audience experiences the work. Where the audio also constitutes a deep fake, the separate deployer disclosure under Article 50(4) applies, and for content forming part of an evidently artistic, creative, satirical or fictional work that disclosure is limited to an appropriate manner that does not hamper the display or enjoyment of the work.

**Judge remarks (this run)**

1. `[PASS]` **No need of marking that would compromise enjoyment**  
    _States artistic-work disclosure is limited to a manner that does not hamper display/enjoyment of the work._
2. `[PASS]` **Still required: other form of disclosure that such content exist (must be unambiguous in the answer)**  
    _Answer states the Article 50(4) deployer disclosure still applies to artistic content, just limited to an appropriate manner._

Tone: `PASS` _Professional third-person register with well-ordered, coherent explanation of applicable marking and disclosure obligations._

---

## Q95 (rg_096, hard mode)

**Question**

> What is an "area" and what is a "use case" for high-risk as per Article 6(2)? How many areas exist?

### August 25 answer (0/2 criteria)

References provided: `Article 6.3, Article 6, Article 6.2, Annex III` | Expected: `Article 6.2, Annex III` | 1,456 chars | Ans. Conciseness 40.9

> Classifies an AI system as high-risk on two routes. Annex I route (Article 6(1)): the system is a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I AND that product must undergo a third-party conformity assessment under that sectoral legislation. Annex III route (Article 6(2)): the system falls within one of the eight Annex III use cases. Article 6(3) derogation: an Annex III system is NOT high-risk where it poses no significant risk of harm and meets one of four conditions (a narrow procedural task; improving the result of a previously completed human activity; detecting decision-making patterns or deviations without replacing or influencing the human assessment; or a preparatory task), unless it profiles natural persons, in which case it is always high-risk; the provider must document this self-assessment before placing the system on the market and still register it under Article 49(2). Carve-out: an Annex-III system is NOT high-risk if it doesn't pose a significant risk of harm AND one of four conditions is met, (a) performs a narrow procedural task; (b) improves the result of a previously completed human activity; (c) detects decision-making patterns or deviations without replacing the human assessment; (d) performs a preparatory task to an Annex-III use case. Provider must document the assessment before placing on market and still register the system per Article 49(2).

**Report judgement**

1. `[FAIL]` **Area contain use cases**  
    _The candidate answer mentions the `eight Annex III use cases' but does not explain that an `area' is a broader Annex III category that contains one or more specific use cases. It therefore does not correctly distinguish area vs use case._
2. `[FAIL]` **8 areas exist**  
    _The candidate answer states that the system falls within `one of the eight Annex III use cases.' This is incorrect for the asked distinction: Annex III has eight areas/categories, not eight use cases._

### Current live answer (2/2 criteria)

References shipped: `Article 6.2, Annex III.7.b, Article 7.1, Article 112.11` | 1,171 chars | Ans. Conciseness 50.9 | latency 23.7s | judge spread [1.0, 1.0, 1.0]

_Turn 1 before pushback: 1,205 chars, refs `Article 6.2, Article 6.3, Annex III`_

> Under Article 6(2), which classifies as high-risk the AI systems listed in Annex III, an "area" is a numbered heading of Annex III identifying a sector or context of deployment, and a "use case" is a lettered entry beneath that heading describing a specific intended purpose, so a system is high-risk only where it matches a listed use case within an area, not merely because it operates in that area. Annex III contains eight areas: biometrics, critical infrastructure, education and vocational training, employment and workers' management and access to self-employment, access to and enjoyment of essential private services and essential public services and benefits, law enforcement, migration and asylum and border control management, and administration of justice and democratic processes. The distinction matters operationally because Article 7 empowers the Commission to add or modify use cases only within the areas already listed in Annex III and only where the risk is equivalent to or greater than that of the systems already listed, while Article 112 reserves the extension of existing area headings or the addition of new ones to the periodic review process.

**Judge remarks (this run)**

1. `[PASS]` **Area contain use cases**  
    _Answer states areas are headings and use cases are entries beneath them, i.e. areas contain use cases._
2. `[PASS]` **8 areas exist**  
    _Answer explicitly states Annex III contains eight areas._

Tone: `PASS` _Professional, well-structured prose with clear third-person exposition and no self-referential hedging._

---

## Q104 (rg_105, hard mode)

**Question**

> What is Annex X about? What is it used for?

### August 25 answer (0/2 criteria)

References provided: `Annex X` | Expected: `Article 111.1, Annex X` | 2,154 chars | Ans. Conciseness 29.0

> Annex X sets the information that providers (and, where applicable, authorised representatives) and public-authority deployers must enter in the EU database when registering high-risk AI systems referred to in Article 49: provider / authorised-representative / deployer identity + contact details, system name + trade name + additional unambiguous reference, intended purpose, status of the system (on the market / in service / no longer placed on the market / recalled), type + number of the conformity-assessment certificate + identity of the issuing notified body where applicable, Member States in which the system is placed on the market or put into service, and a copy of the EU declaration of conformity (Article 47) + the instructions for use. Public-access carve-outs in Annex X apply to law-enforcement, migration, asylum, and border-control systems. GPAI provider obligations: maintain technical documentation per Annex XI, supply downstream-provider information per Annex XII, implement a copyright policy, and publish a sufficiently detailed training-data summary. Where the model meets the Article 51 systemic-risk threshold (10^25 FLOPs cumulative training compute), the additional Article 55 obligations apply on top. Training-data content summary, the Commission adopted the mandatory disclosure template on 24 July 2025. Article 53(2) free / open-source carve-out: the Annex XI technical-documentation obligation and the Annex XII downstream-provider information obligation under Article 53(1)(a)-(b) do NOT apply to GPAI models released under a free and open-source licence permitting access, use, modification and distribution, with publicly available parameters (weights, architecture and usage information). The carve-out does NOT apply to GPAI models designated as systemic-risk under Article 51, once systemic-risk designation lands, the open-source carve-out is gone and the full Article 53 obligations plus the Article 55 systemic-risk obligations apply regardless of licence. The Article 53(1)(c) copyright policy and the Article 53(1)(d) public training-data summary apply to ALL GPAI providers including open-source releases.

**Report judgement**

1. `[FAIL]` **Annex X lists Union legal acts for large-scale IT systems**  
    _The candidate answer describes Annex X as setting information for registration of high-risk AI systems in the EU database under Article 49. That is not what Annex X is about under the EU AI Act for this question. It does not mention the list of Union legal acts for large-scale IT systems._
2. `[FAIL]` **Used to define systems with specific transition and compliance timelines**  
    _The candidate answer says Annex X is used for EU database registration fields and then discusses GPAI obligations. It does not explain that Annex X is used to identify systems subject to particular transition/compliance timing rules._

### Current live answer (2/2 criteria)

References shipped: `Annex X, Article 111.1, Article 5.1.d` | 1,068 chars | Ans. Conciseness 58.5 | latency 20.3s | judge spread [1.0, 1.0, 1.0]

_Turn 1 before pushback: 1,230 chars, refs `Annex X, Article 111.1, Article 5.1.d`_

> Annex X is a list of Union legislative acts establishing large-scale IT systems in the area of Freedom, Security and Justice, and it imposes no obligations of its own. It names the Schengen Information System, the Visa Information System, Eurodac, the Entry/Exit System, the European Travel Information and Authorisation System, the European Criminal Records Information System on third-country nationals and stateless persons, and the two interoperability Regulations. Its operative use is in Article 111(1) on transitional arrangements, under which AI systems that are components of the large-scale IT systems established by the acts listed in Annex X and placed on the market or put into service before 2 August 2027 must be brought into compliance with the Regulation only by 31 December 2030, without prejudice to the prohibited practices in Article 5. Article 111(1) also requires the Regulation's requirements to be taken into account in the evaluation of each such large-scale IT system provided for in those acts, and where those acts are replaced or amended.

**Judge remarks (this run)**

1. `[PASS]` **Annex X lists Union legal acts for large-scale IT systems**  
    _States Annex X lists Union legislative acts establishing large-scale IT systems, naming them._
2. `[PASS]` **Used to define systems with specific transition and compliance timelines**  
    _States it's used in Article 111(1) transitional arrangements with the 31 Dec 2030 compliance deadline._

Tone: `PASS` _Professional, neutral, well-structured prose that a compliance professional could act on._

---
