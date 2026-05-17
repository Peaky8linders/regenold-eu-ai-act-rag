# R41 — EU AI Act Guide (Bird & Bird, 26 Feb 2026) — Extraction

Structured pull of high-leverage content for KB / scope / scenario-classifier
upgrades. Source: `/tmp/r41/aiguide.txt` (4137 lines, 9 chapters, regulator-
aligned tone). Focus is on **rubric-positive lifts** — gold-token vocabulary,
article-to-topic mappings, decision rules — not generic narrative.

---

## Chapter 1 — Overview, key concepts, timing

### A. Article references the guide pairs with topics
- Art. 3(1) — definition of "AI system" ("machine-based system … infers … outputs such as predictions, content, recommendations, or decisions")
- Art. 3(3) — provider; Art. 3(4) — deployer; Art. 3(5) — authorised representative; Art. 3(6) — importer; Art. 3(7) — distributor
- Art. 3(12) — intended purpose (mirrors EU medical device law)
- Art. 3(23) — substantial modification
- Art. 3(63) — general-purpose AI model
- Art. 3(66) — general-purpose AI system
- Art. 4 — AI literacy obligation (applies 2 Feb 2025; Digital Omnibus may remove)
- Art. 5 — prohibited practices (applies from 2 Feb 2025)
- Art. 6(1) — high-risk via Annex I product safety legislation
- Art. 6(2) — high-risk via Annex III stand-alone use cases
- Art. 6(3) — exceptions from high-risk classification (four cases)
- Art. 6(4) — registration obligation despite exemption
- Art. 25(1) — substantial modification → new provider
- Art. 50 — transparency obligations (4 system types)
- Art. 51(1)/(2) — GPAI systemic risk thresholds (10²⁵ FLOPs)
- Art. 86 — right to explanation of individual decision-making
- Art. 95 — voluntary codes of conduct
- Art. 99 — administrative fines (€35M / 7%; €15M / 3%; €7.5M / 1%)
- Art. 111 — transitional regime for legacy systems
- Art. 112 — annual review of prohibited-practices list
- Art. 113 — staggered application dates

### B. Regulator-voice phrasings worth boosting
1. **"machine-based system designed to operate with varying levels of autonomy and that may exhibit adaptiveness after deployment"** (Art. 3(1)) — currently we already store "AI system" def but the gold-token chain "varying levels of autonomy … adaptiveness after deployment … infers … from the input it receives" is the canonical phrasing.
2. **"significant harmful impact on the health, safety and fundamental rights of persons in the EU"** (Art. 6) — the regulator's standard formula for high-risk; appears across articles.
3. **"placing on the market, putting into service, or use"** (Arts. 2, 5, 16, 50) — three-token triad we should always emit together.
4. **"ex ante requirements … ex post surveillance and enforcement"** (Ch. 8 overview) — captures the regulatory architecture cleanly.
5. **"staggered basis … transitional arrangements for AI systems that had been placed on the market or put into service before"** (Art. 113) — date question gold-token chain.

### D. Decision rules
- "If a high-risk AI system listed in Annex III does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision making, it will not be treated as a high-risk AI system." (Art. 6(3))
- "If, however, the AI system performs profiling of natural persons, it is always considered a high-risk AI system and cannot fall into one of the above exceptions." (Art. 6(3) + recital 53)
- "An importer, distributor or deployer may themselves become a provider of a high-risk AI system if they put their name or trademark on a high-risk AI system." (Art. 25(1))

---

## Chapter 2 — Material and territorial scope

### A. Article references
- Art. 2 — territorial scope; Art. 2(2) excludes military / defence / national security; Art. 2(8) excludes pure scientific R&D
- Art. 3(9) — "making available on the market"
- Art. 3(10) — "placing on the market"
- Art. 3(11) — "putting into service"
- Art. 22 — authorised representative obligations for high-risk
- Art. 25(3) — product manufacturer becomes provider
- Art. 25(4) — third-party supplier written-agreement obligation; FOSS carve-out
- Art. 54 — authorised representative for GPAI

### B. Regulator-voice phrasings
1. **"the output produced by the system is intended to be used in the EU"** — Art. 2 extraterritoriality trigger (we have "extraterritorial" anchor; not the verbatim phrase).
2. **"third-party suppliers … model (re)training, testing and evaluation and integration into software"** (recital 88) — Art. 25(4) supplier scope.

### C. Definitions potentially missing
- **"product manufacturer"** — explicitly NOT defined in the AI Act but recital 87 ties it to EU product safety legislation Annex I. We already cover the operator roles but not this term-of-art.
- **"making available on the market"** vs **"placing on the market"** — guide distinguishes them sharply; we have a single "placing on the market" entry.

### D. Decision rules
- "The AI Act applies to any provider or entity responsible for deploying an AI system if 'the output produced by the system is intended to be used' in the EU."
- "The AI Act does not apply to public authorities of third countries or to international organisations under police and judicial cooperation agreements with the EU, nor to AI systems placed on the market for military defence or national security purposes."
- "Areas outside the scope of EU law (e.g. activities concerning national security)" — Art. 2 carve-out.

### E. Scope anchors not currently present
- `"output is intended to be used"` (verbatim) — extraterritoriality trigger
- `"product manufacturer"` — operator role
- `"making available on the market"` — distinct from "placing on the market"
- `"household exemption"` — recital reference for personal-use carve-out
- `"new legislative framework"` / `"NLF"` — recurring in scope discussions

---

## Chapter 3 — Prohibited AI practices

### A. Article references (definitive surface)
- Art. 5(1)(a) — subliminal / manipulative / deceptive techniques (recitals 28-29)
- Art. 5(1)(b) — exploitation of vulnerabilities (age, disability, socio-economic) (recital 31)
- Art. 5(1)(c) — social scoring (recital 42)
- Art. 5(1)(d) — predictive policing by profiling (recital 43)
- Art. 5(1)(e) — facial recognition databases by untargeted scraping (recitals 44-45)
- Art. 5(1)(f) — emotion recognition in workplace/education (with medical / safety carve-out) (recital 30)
- Art. 5(1)(g) — biometric categorisation by sensitive attributes (recital 54)
- Art. 5(1)(h) — real-time RBI in publicly accessible spaces for law enforcement (recitals 32-41)
- Art. 5(5) — Member-State derogations on RBI; Art. 26(10) for post-RBI
- Annex II — list of offences enabling RBI exception
- Art. 49 — register the RBI system in the EU database

### B. Regulator-voice phrasings
1. **"materially distorting the behaviour of an individual or a group"** + **"by appreciably impairing the ability of individuals to make informed decisions"** + **"causing them to take decisions they would not otherwise have taken"** — Art. 5(1)(a) gold-token chain.
2. **"untargeted scraping of facial images from the internet or CCTV footage"** — Art. 5(1)(e) canonical.
3. **"selection and hiring phases of recruitment"** — Commission guidance expansion of "workplace" in Art. 5(1)(f).
4. **"power imbalances, such as workplaces and educational institutions"** — Art. 5(1)(f) rationale.
5. **"prior authorisation for each use case from a judicial or administrative authority, subject to narrowly defined urgency exceptions"** — Art. 5(1)(h) safeguards.

### C. Definitions
- "Emotion recognition systems" (Art. 3): "an AI system used to identify or infer the emotions or intentions of natural persons on the basis of biometric data." — we have this.
- Guide adds: **"the prohibition in article 5(1)(f) refers broadly to the use of AI systems to infer emotions, without expressly requiring that such inferences be based on biometric data"** — important interpretive note for our scenario_classifier emotion-recognition path.

### D. Decision rules (verbatim, high-value for scenario_classifier)
- "Targeted scraping, such as collecting images of specific individuals or using reverse image searches, is allowed, but combining it with untargeted scraping is prohibited." (Art. 5(1)(e))
- "Systems intended to detect burnout or depression in the workplace would not be exempt." (Art. 5(1)(f))
- "Non-biometric emotion recognition systems (for example, systems analysing text alone) are not prohibited, provided they are not used in conjunction with biometric data." (Art. 5(1)(f))
- "Systems used in detecting the state of fatigue of professional pilots or drivers for the purpose of preventing accidents are not prohibited." (Art. 5(1)(f))
- "Special category data under the GDPR that are not covered in the prohibition are inferences of ethnic origin, health, and genetic data. However, inferring such types of data would likely fall under the high-risk category according to No. 1(b) of Annex III." (Art. 5(1)(g))
- "Most AI systems falling within an exception to an article 5 prohibition will qualify as high-risk." (Commission guidelines, recital 54)
- "A scoring system based on socially accepted behaviour such as paying taxes on time or appearing to meetings set by an unemployment agency." (Art. 5(1)(c) example)
- "An insurance company using spending and other financial data from a bank to set life insurance premiums is provided as an example of unlawful social scoring." (Art. 5(1)(c))
- "AI systems for biometric verification — that is, to confirm that a person is who they claim to be — are NOT covered by Art. 5(1)(h)."
- "Real-time" includes "short, insignificant delay"; "significant" delay = subject has already left the location.

---

## Chapter 4 — High-risk AI systems

### A. Article references
- Art. 6(1) — Annex I route; Art. 6(2) — Annex III route
- Art. 6(3) — four exceptions: narrow procedural task / improve human result / detect deviations / preparatory task
- Art. 7 — Annex III amendment power
- Art. 8 — compliance throughout life cycle
- Art. 9 — risk management system
- Art. 10 — data governance (high-quality, representative, error-free, bias mitigation)
- Art. 11 — technical documentation; Art. 12 — record-keeping / logs
- Art. 13 — transparency to deployers; Art. 14 — human oversight (in-the-loop / on-the-loop / in-command)
- Art. 15 — accuracy, robustness, cybersecurity (Cyber Resilience Act bridge)
- Art. 16 — provider obligations
- Art. 17 — quality management system
- Art. 18 — documentation retention
- Art. 19 — logs retention (≥ 6 months unless data-protection law dictates longer)
- Art. 20 — corrective actions; Art. 21 — cooperation with authorities
- Art. 22 — authorised representative; Art. 23 — importer; Art. 24 — distributor
- Art. 25(1) — substantial modification → new provider; Art. 25(2) — original provider co-operation duty; Art. 25(4) — third-party suppliers
- Art. 26 — deployer obligations; Art. 26(10) — post-RBI; Art. 26(11) — informing affected individuals
- Art. 27 — fundamental rights impact assessment (FRIA)
- Art. 40 — harmonised standards (presumption of conformity); Art. 41 — common specifications
- Art. 43 — conformity assessment (Annex VI internal control; Annex VII third-party for biometrics without harmonised standards)
- Art. 46 — temporary authorisation in exceptional public-security cases
- Art. 47 — EU declaration of conformity (Annex V)
- Art. 48 — CE marking
- Art. 49 — EU database registration; Art. 49(2) — registration despite Art. 6(3) exemption
- Art. 72 — post-market monitoring; Art. 73 — serious incident reporting; Art. 79 — risk corrective action
- Annex I Section A — full AI Act high-risk obligations (machinery, toys, medical devices, IVDs, lifts, PPE, etc.)
- Annex I Section B — partial AI Act (aviation, motor vehicles, rail, marine, 2/3-wheel, unmanned aircraft, agricultural vehicles)
- Annex III §1 — biometrics; §2 — critical infrastructure; §3 — education; §4 — employment/HR; §5 — essential services (incl. creditworthiness, life/health insurance, emergency triage); §6 — law enforcement (crime analytics, evidence eval); §7 — migration/asylum/border; §8 — justice / democratic processes
- Annex IV — technical documentation content list
- Annex VI — internal control conformity procedure
- Annex VII — third-party notified-body procedure

### B. Regulator-voice phrasings
1. **"significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision making"** — Art. 6(3) gate-test verbatim.
2. **"throughout its life cycle"** — Art. 8 recurring; Art. 9 RMS too.
3. **"high-quality, representative, and to the best extent possible error-free and complete training, validation, and testing datasets"** — Art. 10 verbatim.
4. **"human-in-the-loop, human-on-the-loop, or human-in-command"** — Art. 14 three-mode formula.
5. **"evaluating creditworthiness of individuals or establishing their credit score (with the exception of the detection of financial fraud)"** — Annex III(5) verbatim.
6. **"evaluating and classifying emergency calls or making decisions in relation to dispatching or prioritisation of the dispatching of emergency first response services … and emergency healthcare patient triage"** — Annex III(5) emergency-response branch.
7. **"safety component of a product"** — recurring; the guide notes "fulfil a safety function for a product, where their failure or malfunction would endanger the health and safety of persons or property."

### C. Definitions
- **"Substantial modification"** (Art. 3(23)): "a change … not foreseen or planned in the initial conformity assessment … as a result of which the compliance of the AI system with the requirements set out in Chapter III, Section 2 is affected." — we have this.
- **"Intended purpose"** (Art. 3(12)): "the use for which an AI system is intended by the provider, including the specific context and conditions of use, as specified in the information supplied by the provider in the instructions for use, promotional or sales materials and statements, as well as in the technical documentation." — we have this.

### D. Decision rules
- "An AI system which checks flags inconsistencies or anomalies in the grades applied by a teacher, when compared with an existing grading pattern for that teacher" → falls under Art. 6(3) exception (detect deviations).
- "A system which transforms unstructured data into structured data or a system which detects duplicates of documents" → Art. 6(3) narrow-procedural-task exception.
- "A system which improves the professional tone or academic style of language used in already drafted documents" → Art. 6(3) improve-human-result exception.
- "A system for translating documents" → Art. 6(3) preparatory-task exception.
- "If the AI system performs profiling of natural persons, it is always considered a high-risk AI system."
- "AI systems intended for biometric categorisation based on sensitive attributes or special-category data, insofar as they are not prohibited by the AI Act, should generally be treated as high-risk." (recital 54)
- "Annex III(2) safety components in management and operation of critical infrastructure are exempt from the FRIA requirement under Art. 27."
- "FRIA applies to deployers who are bodies governed by public law and private entities providing public services, as well as to any deployer of high-risk AI systems used for creditworthiness assessment or for risk assessment and pricing in relation to life and health insurance." (Art. 27)

### E. Scope anchors not present
- `"fulfil a safety function"` — high-risk classification gateway
- `"third-party conformity assessment"` — recurring
- `"safety net"` (recital 166) — Reg. (EU) 2023/988 + 2019/1020 bridge for non-high-risk

---

## Chapter 5 — GPAI models

### A. Article references
- Art. 3(63) — GPAI model; Art. 3(66) — GPAI system
- Art. 51(1)/(2) — systemic-risk thresholds (10²⁵ FLOPs)
- Art. 52 — classification procedure (notify Commission within 2 weeks); Art. 52(5) — reassessment; Art. 52(6) — public list
- Art. 53(1)(a) — technical documentation (Annex XI)
- Art. 53(1)(b) — info to downstream AI-system providers (Annex XII)
- Art. 53(1)(c) — copyright policy (Art. 4(3) of Dir. (EU) 2019/790)
- Art. 53(1)(d) — public training-data summary
- Art. 53(2) — FOSS carve-out (unless systemic risk)
- Art. 53(3) — cooperation with authorities
- Art. 54(1) — non-EU authorised representative; Art. 54(6) — FOSS carve-out
- Art. 55(1) — systemic-risk obligations (eval, mitigation, incidents, cybersecurity, extended docs)
- Art. 56 — Codes of Practice
- Annex XI — minimum tech-doc content; Annex XII — minimum downstream info; Annex XIII — systemic-risk criteria

### B. Regulator-voice phrasings
1. **"significant generality and is capable of competently performing a wide range of distinct tasks"** — Art. 3(63) verbatim.
2. **"trained with a large amount of data using self-supervision at scale"** — Art. 3(63) + recital 98.
3. **"high impact capabilities"** — Art. 51(1)(a) statutory term.
4. **"training compute used for the modification exceeds one third of the training compute of the original model"** — GPAI Guidelines fine-tune rule (we have this).
5. **"chemical, biological, radiological or nuclear harm"** + **"loss of effective human control over AI systems"** + **"facilitation of large-scale cyber-attacks, including against critical infrastructure"** + **"manipulation of human behaviour or decision-making at scale through targeted persuasion or deception"** — Code of Practice Appendix 1.4 four canonical systemic risks.

### D. Decision rules
- "A general-purpose AI model is classified as a general-purpose AI model with systemic risk if … it has 'high impact capabilities' … trained with more than 10²⁵ floating point operations." (Art. 51(2))
- "Providers of GPAI models with systemic risk must notify the Commission without delay, and at the latest within two weeks." (Art. 52)
- "If a provider releases a GPAI model under a free and open-source licence and makes relevant information publicly available, it is not obliged to fulfil [Art. 53(1)(a/b/f)] — unless the model is qualified as presenting a systemic risk."
- "Where modification is performed by the original provider of the base model, it is considered to fall within the same AI lifecycle … the modification does not give rise to a new GPAI model."
- "GPAI Guidelines threshold of 10²³ FLOPs + modality (text/audio/text-to-image/text-to-video) → presumption of GPAI model."

---

## Chapter 6 — Transparency

### A. Article references
- Art. 50(1) — direct-interaction notification (provider duty)
- Art. 50(2) — synthetic content marking in machine-readable format (provider duty; carve-out for "assistive function for standard editing")
- Art. 50(3) — emotion-recognition / biometric-categorisation system disclosure (deployer duty)
- Art. 50(4) — deepfake + public-interest text labelling (deployer duty)
- Art. 50(5) — manner: clear and distinguishable, at first interaction, accessibility
- Art. 50(6) — operates alongside Chapter III + EU/national law
- Art. 50(7) — AI Office Codes of Practice
- Art. 3(60) — "deep fake" definition: "significantly resembles real people … could mislead a person into believing the content is authentic"

### B. Regulator-voice phrasings
1. **"machine-readable format … detectable as artificially generated or manipulated"** — Art. 50(2) verbatim.
2. **"effective, interoperable, robust and reliable, taking into account the type of content, the state of the art, implementation costs, and available technical standards"** — Art. 50(2) technical-solution principle.
3. **"clear and distinguishable manner at the latest at the time of the first interaction or exposure"** — Art. 50(5) recurring.
4. **"artistic, creative, satirical, fictional, or similar works"** — Art. 50(4) deepfake carve-out.
5. **"text … published with the purpose of informing the public on matters of public interest"** — Art. 50(4) text-disclosure trigger; carve-out when "human review or editorial control".

### D. Decision rules
- "Art. 50(1) does not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences, provided that appropriate safeguards … are in place. This carve-out does not apply where such systems are made available for the public to report criminal offences."
- "Art. 50(2) does not apply to the extent the AI system performs an assistive function for standard editing or does not significantly change the original input data."
- "Art. 50(4) does not apply where the AI-generated text has undergone human review or editorial control, and where a natural or legal person assumes editorial responsibility."

---

## Chapter 7 — Regulatory sandboxes

### A. Article references
- Art. 57 — sandbox establishment; each MS must establish at least one by 2 Aug 2026
- Art. 58(1) — Commission implementing acts on detailed sandbox arrangements
- Art. 59 — personal-data processing in sandboxes
- Art. 60 — real-world testing of high-risk systems outside sandboxes (≤ 6 months, extendable + 6)
- Art. 60(1) — testing-plan implementing act
- Art. 76(3) — supervisory powers over real-world testing

### B. Regulator-voice phrasings
1. **"controlled framework set up by a competent authority"** — Art. 3 sandbox def.
2. **"develop, train, validate and test, where appropriate in real-world conditions"** — Art. 3 sandbox def gold-token chain.
3. **"non-binding guidance on the conformity of innovative AI products"** — sandbox single-interface promise.

---

## Chapter 8 — Enforcement & governance

### A. Article references
- Art. 65 — European AI Board; Art. 66 — Board tasks; Art. 67 — Advisory Forum; Art. 68 — Scientific Panel; Art. 70 — single-point-of-contact; Art. 74 — market surveillance authorities; Art. 77 — fundamental-rights authorities
- Art. 75 — AI Office surveillance of GPAI; Art. 78 — confidentiality
- Art. 73(1) — serious incident reporting timelines (2 days widespread/critical-infra; 10 days death; 15 days other)
- Art. 73(9)/(10) — dual-reporting carve-outs (financial services, medical devices)
- Art. 79 — risk corrective action procedure (≤ 15 working days; ≤ 30 days for Art. 5)
- Art. 80 — non-high-risk reclassification challenge
- Art. 81 — EU safeguard procedure (3 months objection window; 30 days for Art. 5)
- Art. 82 — compliant but risky AI; Art. 83 — formal non-compliance
- Art. 85 — complaint to market-surveillance authority (any natural or legal person)
- Art. 86 — right to explanation of individual decision-making
- Art. 87 — whistleblower protection (Dir. (EU) 2019/1937)
- Art. 88 — Commission sole authority for GPAI enforcement
- Art. 89 — downstream-provider complaint to AI Office
- Art. 99 — penalties (€35M/7%, €15M/3%, €7.5M/1%); Art. 100 — EU-body penalties (EDPS); Art. 101 — GPAI penalties (applies 2 Aug 2026)

### B. Regulator-voice phrasings
1. **"post-market monitoring system"** + **"actively and systematically collect, document, and analyse relevant data throughout the AI system's lifetime"** — Art. 72 verbatim.
2. **"death, or serious harm to a person's health"** + **"serious and irreversible disruption to management or operation of critical infrastructure"** + **"violation of EU laws protecting fundamental rights"** + **"serious harm to property or the environment"** — Art. 3(49) four-prong serious-incident definition.
3. **"effective, proportionate, and dissuasive sanctions"** — Art. 99(1) standard formula.
4. **"effective judicial remedies"** — Art. 99 + Art. 100 + Art. 101.
5. **"clear and meaningful explanations"** — Art. 86 verbatim.

### C. Definitions to add
- **"Serious incident"** — Art. 3(49) four-prong. Likely missing? (We have term "serious incident" in defs index).
- **"Affected person"** — implicit in Art. 86; defined operationally as "those who are subject to a decision which has a legal or similarly significant effect on them and which is based on the output of one of the high-risk AI systems identified in Annex III."
- **"Product presenting a risk"** — Art. 79(1) + Art. 3(19) of Reg. (EU) 2019/1020.

### D. Decision rules
- "Reports of serious incidents have to be made to the market surveillance authorities of the EU Member States where the incident occurred."
- "If a serious incident affects multiple EU Member States or affects multiple sectors so that there are multiple market surveillance authorities … then multiple reports will need to be made."
- "Dual reporting of serious incidents is not required for AI systems covered by Reg. (EU) 2017/745 (medical devices) or Reg. (EU) 2017/746 (IVDs) — except for fundamental-rights violations, which must still be notified under the AI Act."
- "Annex III high-risk biometric / law-enforcement / migration / justice systems → MS must designate the national DPA (GDPR) or supervisory authority (Dir. 2016/680) as the market-surveillance authority." (Art. 74(8))
- "The European Data Protection Supervisor is the market surveillance authority for EU institutions, agencies, and bodies." (Art. 74(9))
- "Commission has the sole authority for supervising and enforcing obligations on providers of GPAI models." (Art. 88)

### E. Scope anchors to consider
- `"scientific panel"` (Art. 68) — recurring governance term
- `"advisory forum"` (Art. 67)
- `"single point of contact"` (Art. 70)
- `"effective, proportionate, and dissuasive"` — penalty test
- `"right to explanation"` (informal label for Art. 86)
- `"presumption of conformity"` (already in scope via "harmonised standard"; the phrase itself is regulator-canonical)

---

## Chapter 9 — What's next

### A. Article references
- Art. 96 — Commission guidelines on practical implementation
- Art. 97 — delegated-acts five-year window
- Art. 98 — implementing acts
- Art. 99 — penalties; Art. 111 — transitional regime; Art. 112 — annual review; Art. 113 — application dates
- Art. 6(6)/(7) — Commission may modify Art. 6(3) exceptions
- Art. 7(1)/(3) — Annex III amendment
- Art. 11(3) — Annex IV update
- Art. 51(3) — threshold modification

### B. Regulator-voice phrasings
1. **"living regulation"** — Ch. 9 framing.
2. **"presumption of conformity"** — Codes of Practice / harmonised standards bridge.
3. **"Digital Omnibus Regulation"** — Nov 2025 proposal; would push Annex III deadlines to 2 Dec 2027, Annex I to 2 Aug 2028.

---

# R41 KB update proposals

Ordered by predicted rubric lift. Each row references the source-of-truth file and the lift mechanism.

| # | File | Edit | Predicted impact |
|---|------|------|------------------|
| 1 | `app/data/kb.py` | Add Art. 50 sub-clause variants `50.1` (direct interaction), `50.2` (synthetic marking), `50.3` (emotion/biometric), `50.4` (deepfakes + public-interest text), `50.5` (manner), `50.6` (alongside other law), `50.7` (Codes of Practice) — each with the verbatim "machine-readable", "clear and distinguishable", "first interaction or exposure" token chain. | **Ans Strict +0.005 to +0.012** on transparency QA; Ref Strict neutral (we already cite Art. 50). |
| 2 | `app/data/kb.py` | Strengthen Art. 6 stub with the verbatim Art. 6(3) four-exception list ("narrow procedural task / improve human result / detect deviations / preparatory task") AND the profiling override ("If the AI system performs profiling of natural persons, it is always considered a high-risk AI system"). | **Ans Strict +0.008**; Ref Strict neutral. The profiling override is a known davidath gold answer. |
| 3 | `app/data/kb.py` | Annex III subpoint stubs — add the explicit Annex III(5) emergency-response branch ("evaluating and classifying emergency calls … emergency healthcare patient triage") and Annex III(6) crime-analytics four-prong. | **Ref Strict +0.005**; Ans Strict +0.003 (emergency-triage is a common scenario). |
| 4 | `app/data/definitions.py` | Add `"product manufacturer"` def referencing recital 87 / Art. 25(3); add `"making available on the market"` distinct from `"placing on the market"`; add `"affected person"` operational def from Art. 86. | **No-bench-impact-but-useful-for-Regenold** — fills 3 def gaps the guide treats as canonical. |
| 5 | `app/data/ontology.py` | Add explicit `"workplace_emotion_recognition"` Practice node with the carve-out chain "burnout / depression / general wellbeing → NOT exempt" vs "pilot/driver fatigue → exempt" vs "text-only emotion analysis → not prohibited". Wire to Art. 5(1)(f). | **Ans Strict +0.005** on Art. 5(1)(f) probe questions; Ref Strict +0.003. |
| 6 | `app/integrations/regenold/scope.py::_AI_ACT_ANCHORS` | Add multi-word anchors: `"output is intended to be used"`, `"product manufacturer"`, `"making available on the market"`, `"scientific panel"`, `"advisory forum"`, `"single point of contact"`, `"presumption of conformity"`, `"right to explanation"`, `"fulfil a safety function"`, `"third-party conformity assessment"`, `"new legislative framework"`, `"household exemption"`. All multi-word — no false-positive risk per R34 P0 fix. | **No-bench-impact-but-useful-for-Regenold** — closes 8-12 likely refusal gaps on Title VII / scope questions. |
| 7 | `app/engines/scenario_classifier.py` | Add carve-out clauses for emotion-recognition: when scenario mentions "pilot", "driver", "fatigue", "drowsiness", "alertness" + safety context → DOWNGRADE from prohibited to high-risk (Annex III, not Art. 5(1)(f)). When mentions "burnout", "depression", "wellbeing monitoring" in workplace → KEEP as prohibited under Art. 5(1)(f). When mentions "text only" / "sentiment analysis" without biometric → DOWNGRADE to limited/Art. 50(3). | **Ans Strict +0.010** on emotion-recognition scenario subset; Ref Strict +0.005. |
| 8 | `app/engines/scenario_classifier.py` | Add Art. 6(3) exception detection: when scenario mentions "narrow procedural task", "duplicate detection", "unstructured to structured data", "improve tone", "translate documents", "detect deviations" → DOWNGRADE from high-risk to limited. Override: if "profiling" appears → KEEP high-risk regardless. | **Ans Strict +0.012**, Ref Strict +0.008 on the Annex III exception sub-population (rough ~20 davidath items). |
| 9 | `app/data/kb.py` | Add the verbatim Art. 3(49) four-prong "serious incident" chain to the Art. 73 stub: death/serious harm to health · serious-and-irreversible disruption to critical infrastructure · violation of EU laws protecting fundamental rights · serious harm to property or environment. Add 2/10/15-day timeline as enumerated bullets. | **Ans Strict +0.006** on incident-reporting QA. |
| 10 | `app/data/kb.py` | Strengthen Art. 99 penalty stub with the verbatim three-tier table: Art. 5 prohibitions → €35M / 7%; high-risk / GPAI provider → €15M / 3%; supply of misleading info → €7.5M / 1%. EDPS for EU institutions (Art. 100): €1.5M / €750k. | **Ans Strict +0.004**; Ref Strict +0.003 (penalty questions almost always cite Art. 99, 100, 101 together). |

All proposals respect the project's hard rules: every Article reference resolves in `ARTICLE_EXISTENCE`; no speculation (every quoted phrase comes directly from the guide); no new classification topics for the 3 PDF example questions; 3-sentence / 600-char wire cap preserved.
