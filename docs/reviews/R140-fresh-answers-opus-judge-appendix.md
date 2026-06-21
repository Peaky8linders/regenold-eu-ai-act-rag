# R140 - Fresh answers + Opus-4.8-judge issue analysis (per answer)
Three ground-truth sources, fresh answers generated live (Claude Opus 4.8 Stage-2, production env), `?include_reasoning=true`. Each entry: the **fresh answer**, the **reasoning log** summary, the **gold**, and the **issues** (deterministic signals + Opus-4.8-judge verdict where the judge fan-out returned before the session quota reset).

---

## Antifragile expert-review (docx ground truth + remarks)  (n=20)

### `q01` - kw=1.00 refL=1.00 refS=0.92 len=2312 (gold 402)
**Q:** What risk categories are provided for AI systems?

**Fresh answer:** The EU AI Act provides four risk tiers for AI systems, plus a parallel regime for general-purpose AI models, this is a framework question rather than a classification of a specific use-case, so the verdict is the structure itself. Unacceptable risk (prohibited). Under Article 5, eight categories of practice are banned outright, including (a) subliminal, manipulative, or deceptive techniques that cause significant harm, and (b) exploitation of vulnerabilities arising from age, disability, or socio-economic situation. Systems in this tier may not be placed on the market or used at all. High risk. Under Article 6, a system is classified as high-risk by either of two routes: (i) it is a safety component of, or is itself, a product covered by EU harmonisation legislation requiring third-party conformity assessment; or (ii) it falls within one of the eight use-case categories in Annex III (biometrics, critical infrastructure, education and vocational training, employment and worker management, and the further Annex III headings). High-risk classification triggers the Chapter III obligations, though those substantive duties are not detailed in the present references. Limited risk (transparency). Under Article 50, certain systems carry transparency duties only: providers must ensure systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format. Minimal risk. Systems falling outside the tiers above carry no mandatory obligations under the Act. Parallel regime, general-purpose AI models. Separately from the four tiers, Article 51 classifies a general-purpose AI model as posing systemic risk when it has high-impact capabilities (presumed when cumulative training compute exceeds 10²⁵ FLOPs) or when so designated by the Commission on the Annex XIII criteria. These models are governed under their own provisions rather than the use-case tiers above. Note the two tiers in Article 5 and Article 6 are distinct: a practice is prohibited under Article 5 only where it meets that article's harm and manipulation/exploitation conditions, whereas a system is instead merely high-risk under Article 6 where it falls within the Annex I or Annex III routes without crossing the Article 5 threshold.

**Refs:** pred `['Article 5', 'Article 6', 'Article 50', 'Article 50.1', 'Annex III', 'Article 51', 'Annex XIII', 'Annex I']` vs gold `['Article 5', 'Article 6', 'Annex I', 'Annex III', 'Article 50', 'Article 51']` - over-cited `['Annex XIII']`

**Gold answer:** The EU AI Act establishes a tiered risk framework. Article 5 sets the unacceptable-risk tier, banning eight prohibited practices outright. Article 6, via Annex I product-safety legislation and the Annex III use-case list, defines the high-risk tier. Limited-risk systems carry only Article 50 transparency duties, and general-purpose AI models are governed by a parallel regime under Articles 51 to 55.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [factual_error] Frames social scoring as 'by public authorities'; Art 5(1)(c) has no public-authority limit in the final Regulation.; [incomplete_enumeration] Lists only 5 of 8 Art 5 prohibitions (missing predictive-policing, facial-scraping, workplace emotion).; [missing_tier] Addresses only the unacceptable tier; omits high-risk, limited-risk transparency, and the GPAI Art 51-55 regime.; [missing_gpai] Omits the GPAI parallel regime entirely.

**Issue flags:** ['verbose', 'first_person']

### `q02` - kw=1.00 refL=1.00 refS=0.40 len=2718 (gold 612)
**Q:** What types of AI systems or practices are explicitly prohibited by the AI Act?

**Fresh answer:** Article 5 of the AI Act explicitly prohibits eight categories of AI practice, regardless of risk tier. Subliminal, manipulative, or deceptive techniques that materially distort behaviour and cause or are likely to cause significant harm (Article 5(1)(a)). Exploitation of vulnerabilities arising from age, disability, or a specific social or economic situation to distort behaviour and cause significant harm (Article 5(1)(b)); this expressly captures systems that leverage the developmental or cognitive vulnerabilities of minors. Social scoring of natural persons where the score leads to detrimental treatment in unrelated social contexts or to treatment that is unjustified or disproportionate (Article 5(1)(c)); lawful evaluation carried out for a specific purpose under Union or national law is not affected. Criminal-risk profiling that assesses or predicts the likelihood of offending based solely on personality traits, with an exception for systems that support a human assessment grounded in objective, verifiable facts (Article 5(1)(d)). Untargeted scraping of facial images from the internet or CCTV to build or expand facial-recognition databases (Article 5(1)(e)). Emotion inference in the workplace and in educational institutions, save for systems placed on the market strictly for medical or safety reasons such as therapeutic use or driver/pilot fatigue detection (Article 5(1)(f)). Biometric categorisation that classifies persons by sensitive attributes (race, ethnicity, political opinions, religious or philosophical beliefs, trade-union membership, sex life, or sexual orientation), excluding lawful labelling or filtering of lawfully acquired biometric datasets (Article 5(1)(g)). Real-time remote biometric identification in publicly accessible spaces for law-enforcement purposes (Article 5(1)(h)), permitted only for three exhaustively listed objectives (targeted search for abduction/trafficking/exploitation victims and missing persons; prevention of a substantial and imminent threat to life or a foreseeable terrorist attack; and localisation of suspects of serious Annex II offences punishable by at least four years' custody). The law-enforcement exception is narrow and procedurally heavy: it requires a prior fundamental rights impact assessment (Article 27, the deployer assessment covering affected persons, specific risks, and human-oversight measures), registration in the EU database before use (Article 49), and prior judicial or independent administrative authorisation, with an urgency carve-out requiring authorisation within 24 hours or immediate cessation. Under Article 5(5), Member States may legislate to enable these exceptions and may impose stricter national rules.

**Refs:** pred `['Article 5', 'Article 27', 'Article 49', 'Annex II']` vs gold `['Article 5']` - over-cited `['Annex II', 'Article 27', 'Article 49']`

**Gold answer:** Article 5 prohibits eight categories of AI practice: subliminal or manipulative techniques causing significant harm; exploitation of vulnerabilities based on age, disability or socio-economic situation; social scoring leading to unjustified detrimental treatment; predictive policing based solely on profiling; untargeted scraping of facial images to build recognition databases; emotion inference in workplaces and educational institutions; biometric categorisation inferring sensitive attributes; and real-time remote biometric identification in public spaces for law enforcement, subject to narrow exceptions.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [incomplete_enumeration] States eight but lists only three prohibitions.; [factual_error] 'social scoring by public authorities' — same public-authority error as Q1.; [irrelevant_citation] Cites Annex II and Article 27, both irrelevant to prohibitions.

**Issue flags:** ['verbose', 'over_citation']

### `q03` - kw=1.00 refL=1.00 refS=0.86 len=1704 (gold 487)
**Q:** What is the definition of high risk?

**Fresh answer:** An AI system is high-risk under one of two routes in Article 6, which sets the classification rules. Under the Annex I route (Article 6(1)), the system is high-risk if it is itself, or is a safety component of, a product covered by the Union harmonisation legislation listed in Annex I (Section A New Legislative Framework instruments such as machinery, toys, radio equipment, medical devices and lifts; Section B instruments covering civil aviation, motor vehicles, marine equipment, rail and agricultural vehicles), and that product must undergo a third-party conformity assessment under that sectoral legislation. Under the Annex III route (Article 6(2)), the system is high-risk if it falls within one of the eight listed use-case categories: biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes. A narrow exception applies: under the Article 6(3) derogation, an Annex III system is not high-risk where it poses no significant risk of harm and meets one of four conditions (it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or carries out a preparatory task), unless it profiles natural persons, in which case it remains high-risk. A provider relying on this derogation must document the self-assessment before placing the system on the market and still register it under Article 49(2), which requires registration of Annex III high-risk systems.

**Refs:** pred `['Article 6', 'Annex I', 'Annex III', 'Article 49', 'Article 49.2']` vs gold `['Article 6', 'Annex I', 'Annex III']` - over-cited `['Article 49']`

**Gold answer:** Under Article 6 an AI system is high-risk by either of two routes. First, where it is a safety component of, or itself is, a product covered by Annex I Union harmonisation legislation that must undergo third-party conformity assessment (Article 6(1)). Second, where it falls within an Annex III use-case category (Article 6(2)). Article 6(3) exempts Annex III systems that perform only narrow procedural, preparatory or human-review-supporting tasks, unless they profile natural persons.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [omission] Omits that the Annex I route requires third-party conformity assessment (Art 6(1)(b)).; [omission] Omits the Art 6(3) carve-outs for non-high-risk Annex III tasks.; [missing_citation] Citations omit Annex I despite the answer targeting that route.

**Issue flags:** ['verbose', 'first_person']

### `q04` - kw=1.00 refL=1.00 refS=0.86 len=1638 (gold 496)
**Q:** Which sectors or applications are considered high-risk under the regulation?

**Fresh answer:** High-risk classification runs on two routes. The Annex III route (Article 6(2)) covers eight use-case categories: biometrics; critical infrastructure; education and vocational training; employment and worker management (recruitment, task allocation, promotion and termination decisions, and performance evaluation affecting workers' fundamental rights); essential private and public services; law enforcement; migration, asylum and border control; and the administration of justice and democratic processes (Annex III). The Annex I route (Article 6(1)) instead classifies a system as high-risk when it is, or is a safety component of, a product covered by the Union harmonisation legislation listed in Annex I (Section A New Legislative Framework items such as machinery, toys, radio equipment, medical devices and lifts; Section B items such as civil aviation, motor vehicles, marine equipment, rail and agricultural vehicles) and that product must undergo a third-party conformity assessment under that sectoral legislation. Falling within Annex III is not automatically decisive: the Article 6(3) derogation removes a system from high-risk status where it poses no significant risk of harm and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or carries out a preparatory task, unless it profiles natural persons, in which case it remains high-risk; the provider must document this self-assessment before placing the system on the market and still register it under Article 49(2).

**Refs:** pred `['Article 6', 'Annex III', 'Annex I', 'Article 49', 'Article 49.2']` vs gold `['Article 6', 'Annex III', 'Annex I']` - over-cited `['Article 49']`

**Gold answer:** High-risk classification follows two routes under Article 6. The Annex III route covers eight use-case areas: biometrics, critical infrastructure, education, employment and worker management, essential private and public services, law enforcement, migration and border control, and administration of justice and democratic processes. The Annex I route covers AI that is a safety component of regulated products such as medical devices and machinery that require third-party conformity assessment.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [structural_omission] Omits the Annex I product-safety route entirely.; [irrelevant_citation] Cites Article 25 (value-chain), unrelated to which sectors are high-risk.

**Issue flags:** ['verbose', 'first_person']

### `q05` - kw=0.83 refL=1.00 refS=1.00 len=887 (gold 502)
**Q:** How should users be informed when interacting with AI systems?

**Fresh answer:** This disclosure should be made in a clear and distinguishable manner at the latest at the point of first interaction. A narrow carve-out applies under Article 50(1) to AI systems authorised by law to detect, prevent, or investigate criminal offences, subject to appropriate safeguards for third-party rights; that exception is itself reversed where the system is available to the public to report a criminal offence, so disclosure remains required. Note that Article 50 also imposes related but distinct transparency duties: providers of systems generating synthetic content must mark outputs in a machine-readable format detectable as artificially generated or manipulated (Article 50(2)), while deployers must inform persons exposed to emotion-recognition or biometric-categorisation systems (Article 50(3)) and label deepfakes as artificially generated or manipulated (Article 50(4)).

**Refs:** pred `['Article 50.1', 'Article 50']` vs gold `['Article 50']`

**Gold answer:** Article 50 sets transparency duties split by role. Providers must ensure systems intended to interact directly with people disclose their AI nature unless obvious (Article 50(1)), and must mark machine-generated synthetic content in a detectable, machine-readable format (Article 50(2)). Deployers of emotion-recognition or biometric-categorisation systems must inform exposed persons (Article 50(3)), and deployers of deepfakes must disclose that the content is artificially generated (Article 50(4)).

**Missed keywords:** `['exposed persons']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [role_error] Puts Art 50(3) (emotion/biometric disclosure) on providers; it is a deployer duty.; [conflation] Conflates Art 50(2) provider marking and Art 50(4) deployer deepfake disclosure.

**Issue flags:** ['term_miss']

### `q06` - kw=0.83 refL=1.00 refS=0.75 len=805 (gold 365)
**Q:** What are AI systems with minimal risks?

**Fresh answer:** Minimal-risk AI systems are the residual category: any system that is not prohibited under Article 5 (which bans practices such as harmful subliminal or manipulative techniques and the exploitation of vulnerabilities based on age, disability, or socio-economic situation), not high-risk under Article 6 (as an Annex I safety component or an Annex III use case), and not caught by the Article 50 transparency duties (which require, for example, disclosing that a person is interacting with an AI system and marking AI-generated synthetic content in a machine-readable format). Typical examples include AI-enabled spam filters, inventory-management tools, and AI in video games. They carry no mandatory obligations under the Regulation, though providers and deployers may voluntarily adopt codes of conduct.

**Refs:** pred `['Article 5', 'Article 6', 'Article 50', 'Annex I', 'Annex III']` vs gold `['Article 5', 'Article 6', 'Article 50']` - over-cited `['Annex I', 'Annex III']`

**Gold answer:** Minimal-risk is the residual category: AI systems that are neither prohibited under Article 5, nor high-risk under Annex I or Annex III, nor subject to Article 50 transparency duties, nor general-purpose AI models. Such systems carry no mandatory obligations under the Act beyond the cross-cutting AI-literacy duty, though voluntary codes of conduct are encouraged.

**Missed keywords:** `['neither']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [irrelevant_citation] All six citations (Annex III, Arts 9/12/13/14/27) attach to high-risk systems, not minimal-risk.; [partial_definition] Defines minimal-risk only as 'outside the 8 high-risk categories'; misses prohibited/transparency/GPAI exclusions.

**Issue flags:** ['verbose', 'term_miss', 'first_person']

### `q07` - kw=1.00 refL=1.00 refS=1.00 len=1070 (gold 370)
**Q:** What are the guiding principles established by the AI Act?

**Fresh answer:** The EU AI Act establishes seven guiding principles that flow from Article 1's stated purpose of promoting human-centric and trustworthy AI while ensuring a high level of protection of health, safety, fundamental rights, democracy, and the rule of law: human agency and oversight; technical robustness and safety; privacy and data governance; transparency; diversity, non-discrimination and fairness; social and environmental wellbeing; and accountability. These principles are not free-standing obligations but inform the Act's operative regime, which Article 1 frames by laying down harmonised rules for placing AI systems on the market, putting them into service, and using them, including prohibitions, high-risk requirements, transparency duties, and rules for general-purpose AI. Article 4 operationalises the principles at the workforce level, requiring providers and deployers to ensure a sufficient level of AI literacy among staff and others operating AI systems on their behalf, taking account of their technical knowledge, experience, education, and training.

**Refs:** pred `['Article 1', 'Article 4']` vs gold `['Article 1', 'Article 4']`

**Gold answer:** The Act's guiding principles for trustworthy AI, set out in Recital 27, are: human agency and oversight; technical robustness and safety; privacy and data governance; transparency; diversity, non-discrimination and fairness; social and environmental well-being; and accountability. These inform the Act's purpose under Article 1 and the AI-literacy duty under Article 4.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.7` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [wrong_answer] Answered about GPAI authorised representative — entirely off-topic.; [wrong_citations] Cited GPAI/authrep articles; should anchor on the trustworthy-AI principles.

**Issue flags:** ['verbose']

### `q08` - kw=1.00 refL=1.00 refS=1.00 len=655 (gold 375)
**Q:** What is the definition of a "system of artificial intelligence"?

**Fresh answer:** Under Article 3, which defines the terms used in the Regulation, an "AI system" is a machine-based system designed to operate with varying levels of autonomy, that may exhibit adaptiveness after deployment, and that, for explicit or implicit objectives, infers from the input it receives how to generate outputs such as predictions, content, recommendations, or decisions that can influence physical or virtual environments. The defining features are therefore machine-based operation, autonomy of varying degrees, possible post-deployment adaptiveness, and the capacity to infer from inputs how to generate outputs affecting real or virtual environments.

**Refs:** pred `['Article 3.1']` vs gold `['Article 3']`

**Gold answer:** Under Article 3(1) an AI system is a machine-based system designed to operate with varying levels of autonomy, that may exhibit adaptiveness after deployment, and that, for explicit or implicit objectives, infers from the input it receives how to generate outputs such as predictions, content, recommendations or decisions that can influence physical or virtual environments.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.7` answer_route=synthesis:synthesis_default

**Issue flags:** - clean

### `q09` - kw=0.83 refL=1.00 refS=0.67 len=892 (gold 359)
**Q:** What are the penalties for violating the provisions of the regulation for high-risk AI systems?

**Fresh answer:** Penalties for high-risk AI system violations are governed by Article 99, which sets a tiered administrative fine regime. For non-compliance by providers, deployers, importers, or distributors with the high-risk obligations (all obligations other than the Article 5 prohibited practices), Article 99(4) caps fines at up to EUR 15 000 000 or, for an undertaking, up to 3 % of total worldwide annual turnover for the preceding financial year, whichever is higher. The Article 5 prohibited practices carry the higher ceiling under Article 99(3) of EUR 35 000 000 or 7 % of worldwide annual turnover, so most high-risk breaches fall under the 3 % tier rather than this top band. Under Article 99(6), where the offender is an SME or start-up, each fine is capped at the lower of the applicable percentage or fixed amount, and in all cases penalties must be effective, proportionate, and dissuasive.

**Refs:** pred `['Article 99', 'Article 5']` vs gold `['Article 99']` - over-cited `['Article 5']`

**Gold answer:** For infringements relating to high-risk AI systems, Article 99(4) sets fines of up to EUR 15 000 000 or 3% of total worldwide annual turnover, whichever is higher. For SMEs and start-ups, Article 99(6) applies the lower of the two amounts. The most severe tier, Article 99(3) up to EUR 35 000 000 or 7%, is reserved for breaches of the Article 5 prohibitions.

**Missed keywords:** `['3%']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.7` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [omission] Recites generic Art 99(1); the high-risk-specific ceiling is Art 99(4) (EUR 15M/3%).; [omission] Omits the SME lower-of-two-amounts rule (Art 99(6)).

**Issue flags:** ['verbose', 'term_miss']

### `q10` - kw=0.40 refL=0.50 refS=0.33 len=1367 (gold 458)
**Q:** What is the difference between the deployer and the provider?

**Fresh answer:** The provider and the deployer are distinct actors: the provider develops an AI system (or has one developed) and places it on the market or puts it into service under its own name, whereas the deployer uses an AI system under its authority in a professional capacity. Article 3 sets out these defining terms, and the practical difference is the weight of obligations each bears. Under Article 16, providers of high-risk AI systems carry the principal compliance burden: ensuring the system meets the Chapter III Section 2 requirements and bears their identity, operating a quality-management system (Article 17, covering regulatory-compliance strategy, design verification, testing, post-market monitoring, and incident reporting), keeping the technical documentation and the system's automatically generated logs (Article 19 requires retaining those logs for at least six months), conducting conformity assessment, drawing up the EU declaration of conformity, affixing the CE marking, registering the system, taking corrective action, and demonstrating compliance to authorities on request. Deployers, by contrast, are subject to the narrower duties of Articles 26 and 27, which govern use of the system and, in defined cases, a fundamental-rights impact assessment, rather than the design, conformity-assessment, and market-entry obligations that fall on providers.

**Refs:** pred `['Article 3', 'Article 16', 'Article 17', 'Article 19']` vs gold `['Article 3', 'Article 25']` - over-cited `['Article 16', 'Article 17', 'Article 19']` - MISSING `['Article 25']`

**Gold answer:** Under Article 3, a provider develops an AI system (or has one developed) and places it on the market or puts it into service under its own name, while a deployer uses the system under its own authority, except for purely personal non-professional use. Under Article 25 a deployer becomes a provider with full Article 16 obligations if it puts its name on a high-risk system, substantially modifies it, or changes its intended purpose so it becomes high-risk.

**Missed keywords:** `['places on the market', 'own authority', 'Article 25']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [suboptimal_citation] Cites Art 17 (QMS) and 19 (logs) which are provider duties, not definitions; should add Art 25 role transition.

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss']

### `q11` - kw=0.60 refL=1.00 refS=1.00 len=976 (gold 377)
**Q:** Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?

**Fresh answer:** Yes. The technical documentation of a high-risk AI system must include specifications regarding the required hardware. Under Article 11, which requires the technical documentation to be drawn up before the system is placed on the market or put into service, kept up to date, and to contain at a minimum the information set out in Annex IV, the provider must cover the system's design specifications and system architecture. Annex IV, which enumerates the required documentation contents (system description, design specifications, system architecture, data and training methodology, human oversight, risk-management measures, validation and testing procedures, and the post-market monitoring system), encompasses the general description of the system and its design, including the computational and hardware resources used to develop, train, test and run it. Providers that are SMEs may supply these elements in the simplified form provided by the Commission under Article 11.

**Refs:** pred `['Annex IV', 'Article 11', 'Annex IV.1.e']` vs gold `['Article 11', 'Annex IV']`

**Gold answer:** Yes. Under Article 11 providers must draw up technical documentation meeting Annex IV before placing a high-risk system on the market. Hardware specifications fall within Annex IV point 1(e), the description of the hardware on which the system runs, and Annex IV point 2(c) additionally requires the computational resources used to develop, train, test and validate the system.

**Missed keywords:** `['1(e)', 'computational resources']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.7` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [wrong_subcitation] Cites Annex IV.2.a (development methods); hardware is Annex IV point 1(e).; [missing_subcitation] Should also reference Annex IV.2(c) (computational resources).

**Issue flags:** ['verbose', 'term_miss']

### `q12` - kw=0.50 refL=1.00 refS=1.00 len=1631 (gold 320)
**Q:** Are AI systems intended for emotion recognition from biometric data always prohibited?

**Fresh answer:** No, emotion recognition AI is prohibited only when used in the workplace or in education and training institutions; outside those two settings it is not banned but is regulated as high-risk. The operative provision is Article 5, which enumerates the prohibited practices. The prohibition on emotion recognition is confined to AI systems used to infer emotions of natural persons in the areas of workplace and education institutions, and even there a narrow exception applies where the system is placed on the market for medical or safety reasons (for example, monitoring the fatigue or alertness of a person for safety purposes). It is therefore not an absolute, context-independent prohibition. Where the use does not fall within the workplace/education scenario, the system is not prohibited but is captured by Annex III, which lists biometrics among the eight high-risk use-case categories, placing emotion recognition in the high-risk tier (subject to the standard Annex III qualifications). Note that a high-risk classification under Annex III triggers the Chapter III obligations, but those obligations are not substantiated in the references provided here and are not asserted on that basis. In addition, Article 50 imposes transparency duties: deployers of an emotion recognition system must inform the natural persons exposed to it of the system's operation, independent of the high-risk classification. In short: prohibited only in workplace and educational settings (Article 5, subject to the medical/safety exception); otherwise high-risk under Annex III with Article 50 transparency obligations toward exposed persons.

**Refs:** pred `['Article 5', 'Article 5.1.f', 'Article 50.3', 'Annex III.1.c', 'Article 50']` vs gold `['Article 5', 'Annex III', 'Article 50']`

**Gold answer:** No. Emotion recognition is prohibited only in workplaces and educational institutions under Article 5(1)(f), subject to a narrow medical or safety exception. Elsewhere it is high-risk under Annex III point 1(c) (biometrics) and triggers Article 50(3) transparency duties toward the natural persons exposed to the system.

**Missed keywords:** `['not always', '5(1)(f)', '50(3)']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [wrong_subcitation] Cites Annex III.5; emotion recognition is at Annex III point 1(c).; [imprecise_subcitation] Art 50 should be the precise 50(3).

**Issue flags:** ['verbose', 'term_miss']

### `q13` - kw=1.00 refL=1.00 refS=0.89 len=2852 (gold 351)
**Q:** Is an AI that transcribes doctor–patient conversations prohibited? Or is it high-risk as per the use cases of Annex III of the AI Act?

**Fresh answer:** Neither prohibited nor a standalone Annex III high-risk use case, transcribing doctor, patient conversations is not banned under Article 5 and is not listed among the high-risk categories of Annex III; whether it becomes high-risk turns on a single deciding fact under Article 6. Why it is not prohibited (Article 5). Article 5 forbids only eight discrete practices, subliminal, manipulative, or deceptive techniques causing significant harm, and exploitation of vulnerabilities arising from age, disability, or socio-economic situation, among the others enumerated. A system that passively converts speech to text performs none of these functions. Transcription would fall within Article 5 only if the system were deliberately engineered to deploy a manipulative or deceptive technique, or to exploit a patient's vulnerability, so as to materially distort behaviour and cause significant harm, a context defined by the prohibited technique, not by the clinical setting. Absent that, the prohibition tier does not engage. Why it is not high-risk by use case (Annex III). Annex III lists specific high-risk use-case areas (biometrics, critical infrastructure, education and vocational training, employment and worker management, among the eight). Clinical transcription corresponds to none of them. It therefore cannot be classified high-risk via the Annex III route (Article 6(2)). The deciding condition (Article 6(1) read with Annex I). It depends: the system is high-risk only if it functions as a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I (notably the Medical Devices Regulation or the In Vitro Diagnostic Regulation) and that product is required to undergo third-party conformity assessment. If the transcription tool is a mere documentation aid with no medical-device safety function, this route is not triggered and the system is not high-risk. If it is integrated into, or constitutes, an Annex I medical device subject to third-party conformity assessment, it is high-risk under Article 6(1). Residual transparency tier (Article 50). Independently of the above, where the system interacts directly with the patient as a natural person, the provider must ensure the person is informed they are interacting with an AI system (Article 50(1)); and to the extent the system generates synthetic audio or other AI-generated content, that content must be marked in a machine-readable, detectable format. These limited-risk transparency duties can apply even when the system is neither prohibited nor high-risk. Bottom line: not prohibited, not Annex III high-risk; high-risk only under Article 6(1)/Annex I if it is a medical-device safety component requiring third-party conformity assessment, otherwise limited-risk, with Article 50 transparency obligations potentially applicable.

**Refs:** pred `['Annex III', 'Article 6', 'Article 6.2', 'Article 6.1', 'Article 5', 'Annex I', 'Article 50', 'Article 50.1']` vs gold `['Article 6', 'Annex I', 'Article 5', 'Article 50']` - over-cited `['Annex III']`

**Gold answer:** Transcribing doctor-patient conversations is neither prohibited under Article 5 nor listed as a high-risk use case in Annex III. It becomes high-risk under Article 6 only if deployed as a safety component of a medical device covered by Annex I (MDR or IVDR). Otherwise Article 50 transparency duties may apply where the system interacts with patients.

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Expert remarks (original answer):** [contradictory_citation] Cites Annex III.5 even though the answer says the system is NOT in Annex III.

**Issue flags:** ['verbose', 'first_person']

### `q14` - kw=0.57 refL=1.00 refS=0.46 len=765 (gold 449)
**Q:** We are a medical device manufacturer building an AI system to analyze X-rays to detect tumors. Is this system classified as high-risk, and what conformity assessment is required?

**Fresh answer:** An AI system that is a safety component of, or is itself, a product covered by the Union harmonisation legislation in Annex I (for example a medical device under the MDR or IVDR), where that product must undergo a third-party conformity assessment, is high-risk under Article 6(1). The applicable conformity-assessment procedure is set out in Article 43, carried out under the relevant sectoral legislation with notified-body involvement where that legislation requires it. The full Chapter III Section 2 provider obligations then stack on top of the sectoral requirements, including effective human oversight by qualified operators under Article 14 and continuous post-market monitoring under Article 72 alongside the equivalent medical-device surveillance duties.

**Refs:** pred `['Article 6', 'Article 43', 'Annex I', 'Annex III', 'Article 5', 'Article 9', 'Article 10', 'Article 11', 'Article 12', 'Article 13']` vs gold `['Article 6', 'Annex I', 'Article 43']` - over-cited `['Annex III', 'Article 10', 'Article 11', 'Article 12', 'Article 13', 'Article 5', 'Article 9']`

**Gold answer:** Yes, it is high-risk under Article 6(1): an AI system that is a safety component of a medical device covered by Annex I (MDR/IVDR) is high-risk where the device requires third-party conformity assessment, which a tumour-detecting X-ray device does. Under Article 43(3) the AI Act conformity assessment is integrated into the MDR notified-body procedure as a single assessment, and the full Chapter III Section 2 obligations (Articles 9 to 15) apply.

**Missed keywords:** `['notified body', '43(3)', 'integrated']`

**Reasoning log:** path=`logic_rag` stage2_polish=`False` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Expert remarks (original answer):** [generic_application] States the rule but does not apply it to the X-ray case (device class, Art 43(3) integrated MDR assessment).; [irrelevant_citation] Cites Art 5 and Annex III, irrelevant to the Art 6(1)/Annex I scenario.

**Issue flags:** ['over_citation', 'term_miss', 'first_person']

### `q15` - kw=0.50 refL=1.00 refS=0.86 len=651 (gold 566)
**Q:** Can a hospital use an AI system to sort patients based on their biometric data to determine priority for an experimental clinical trial?

**Fresh answer:** AI used for emergency healthcare patient triage, or to dispatch or prioritise emergency first-response services, is high-risk under Annex III(5)(d) (Article 6(2)). Selecting or prioritising patients for a clinical trial is not itself a listed Annex III use case, so it is high-risk only where it determines access to or eligibility for essential healthcare services, or where it categorises natural persons by sensitive attributes (Annex III(1)(b)). Such biometric categorisation is prohibited under Article 5(1)(g) where it deduces race, political opinions, trade-union membership, religious or philosophical beliefs, sex life, or sexual orientation.

**Refs:** pred `['Article 5.1.g', 'Article 5', 'Article 6', 'Annex III', 'Annex I']` vs gold `['Article 5', 'Annex III', 'Article 6']` - over-cited `['Annex I']`

**Gold answer:** It depends on the function. Annex III point 5(d) covers emergency triage and dispatch, not clinical-trial selection; trial selection may instead fall under Annex III point 5(a) (eligibility for essential healthcare services) or outside Annex III entirely, governed by the Medical Devices and Clinical Trials Regulations. Separately, it is prohibited under Article 5(1)(g) only if the biometric categorisation infers an attribute on the closed list: race, political opinions, trade-union membership, religious or philosophical beliefs, sex life or sexual orientation.

**Missed keywords:** `['5(a)', '5(d)', 'closed list']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`False` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [wrong_subpoint] Anchors on Annex III 5(d) (emergency triage); clinical-trial selection is not 5(d), likely 5(a) or outside Annex III.; [imprecise] Art 5(1)(g) conditional correct but does not name the closed list of sensitive attributes.

**Issue flags:** ['term_miss']

### `q16` - kw=1.00 refL=0.33 refS=0.40 len=3226 (gold 487)
**Q:** Our life sciences startup developed a general-purpose AI model trained on massive amounts of genomic data. What transparency obligations apply to us?

**Fresh answer:** Under Article 53, GPAI providers must maintain Annex XI documentation, supply downstream-provider information, and publish a training-data summary; the Article 53(2) carve-out means each documentation obligation does not apply to free and open-source models below the systemic threshold. Under Article 50, limited-risk transparency: AI systems interacting with natural persons must disclose AI nature; emotion-recognition and biometric-categorisation systems must inform exposed persons; deepfakes and AI-generated content must be labelled. GPAI provider obligations: maintain technical documentation per Annex XI, supply downstream-provider information per Annex XII, implement a copyright policy, and publish a sufficiently detailed training-data summary. Where the model meets the Article 51 systemic-risk threshold (10^25 FLOPs cumulative training compute), the additional Article 55 obligations apply on top. Training-data content summary, the Commission adopted the mandatory disclosure template on 24 July 2025. GPAI providers must publish a publicly available summary covering: public datasets, scraped web content, user data, synthetic data and licensed content. GPAI models placed on the market before 2 August 2025 are grandfathered until 2 August 2027. Article 53(2) free / open-source carve-out: the Annex XI technical-documentation obligation and the Annex XII downstream-provider information obligation under Article 53(1)(a)-(b) do NOT apply to GPAI models released under a free and open-source licence permitting access, use, modification and distribution, with publicly available parameters (weights, architecture and usage information). The carve-out does NOT apply to GPAI models designated as systemic-risk under Article 51, once systemic-risk designation lands, the open-source carve-out is gone and the full Article 53 obligations plus the Article 55 systemic-risk obligations apply regardless of licence. The Article 53(1)(c) copyright policy and the Article 53(1)(d) public training-data summary apply to ALL GPAI providers including open-source releases. Transparency obligations split by actor: providers must ensure AI systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format (Article 50(2)); deployers must inform exposed persons when operating emotion-recognition or biometric-categorisation systems (Article 50(3)) and must label deepfakes as artificially generated or manipulated (Article 50(4)). Classifies a general-purpose AI model as having 'systemic risk' when it has high-impact capabilities (presumed when cumulative training compute exceeds 10^25 FLOPs) or when so designated by the Commission based on Annex XIII criteria. Commission's 18 July 2025 GPAI Guidelines presume a model is general-purpose (Article 3(63)) when training compute exceeds 10^23 FLOPs and the model can generate language, image, audio, or video output. Fine-tuned or modified models become new providers under Article 25 when their additional training compute exceeds one-third of the base model's compute (or one-third of the 10^25 systemic threshold, ~3.3×10^24 FLOPs, when base compute is unknown).

**Refs:** pred `['Article 53', 'Article 53.1', 'Article 50']` vs gold `['Article 53', 'Article 51', 'Article 55']` - over-cited `['Article 50']` - MISSING `['Article 51', 'Article 55']`

**Gold answer:** As a general-purpose AI model provider you must, under Article 53(1): keep technical documentation (Annex XI), provide downstream-provider information (Annex XII), implement a copyright policy, and publish a sufficiently detailed training-data summary. Whether the additional systemic-risk obligations of Article 55 apply turns on the Article 51 threshold, presumed at 10^25 FLOPs of cumulative training compute; a startup model typically falls below it, but that is the gating question.

**Reasoning log:** path=`logic_rag` stage2_polish=`False` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Expert remarks (original answer):** [irrelevant_sentence] Adds an Art 113 entry-into-force sentence unrelated to the question.; [omission] Should name the Art 51 systemic-risk threshold (10^25 FLOPs) and Art 55 obligations as the gating question.

**Issue flags:** ['verbose', 'under_citation']

### `q17` - kw=1.00 refL=1.00 refS=1.00 len=840 (gold 462)
**Q:** We are a university lab developing an AI model exclusively for scientific research and development into new life science drugs. Does the AI Act apply to our model before it is released to the market?

**Fresh answer:** No, the AI Act does not apply to the operator's model while it remains in pure research and development. Under Article 2, the Regulation reaches providers and deployers only once an AI system is placed on the EU market or put into service, and Article 2(6) excludes AI systems and models, including their output, specifically developed and put into service for the sole purpose of scientific research and development. Article 2(8) likewise excludes any research, testing, or development activity carried out prior to the system being placed on the market or put into service, with the sole exception of testing in real-world conditions. The Act's obligations therefore attach only when the operator's model leaves R&D and is placed on the market or put into service, at which point the applicable duties will follow its risk classification.

**Refs:** pred `['Article 2', 'Article 2.6', 'Article 2.8']` vs gold `['Article 2']`

**Gold answer:** No. Article 2(6) excludes AI systems and models developed and used solely for scientific research and development, so the model is outside the Act while used only for that purpose and not placed on the market or put into service. The exclusion ends on market placement or putting into service, at which point the Act's obligations attach according to the model's risk classification; Article 2(8) separately preserves pre-market testing in real-world conditions.

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.7` answer_route=synthesis:complex_question

**Expert remarks (original answer):** [precision] Could cite the precise Art 2(6) (R&D exclusion) and Art 2(8) (pre-market testing).

**Issue flags:** - clean

### `q18` - kw=0.50 refL=1.00 refS=1.00 len=719 (gold 487)
**Q:** We are developing a generative AI chatbot that will be deployed on a hospital website to answer general patient queries. What transparency obligations apply?

**Fresh answer:** Yes, transparency obligations apply, and they fall on you as the provider on two fronts. First, because the chatbot interacts directly with patients, the operator must design it so that each person is informed they are dealing with an AI system rather than a human (Article 50(1)). Second, because it generates content, its outputs must be marked in a machine-readable format and detectable as artificially generated (Article 50(2)). The deployer-facing duties in Article 50, namely disclosure for emotion-recognition or biometric-categorisation systems (Article 50(3)) and labelling of deepfakes (Article 50(4)), do not arise on the facts stated, since a general patient-query chatbot performs none of those functions.

**Refs:** pred `['Article 50.1', 'Article 50']` vs gold `['Article 50']`

**Gold answer:** First classify it: a general patient-query chatbot is most likely limited-risk, not high-risk, so Article 13 high-risk transparency does not apply and Article 50 governs alone. Under Article 50(1) the provider must ensure each user is told they are interacting with an AI system, and under Article 50(2) any generated content must be marked in a machine-readable format. The hospital deploying a third-party chatbot is the deployer, so deployer duties such as Article 50(4) attach to it.

**Missed keywords:** `['limited-risk', 'classify', 'not high-risk']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.5` answer_route=synthesis:complex_question

**Expert remarks (original answer):** [missing_classification] Asserts cumulative Art 13 + Art 50 without classifying the chatbot; it is most likely limited-risk (Art 50 alone).; [role_confusion] Uses 'operator' for both provider and deployer duties; the hospital is the deployer.; [unaddressed_citation] Cites Annex I and Art 6 but does not address them in the body.

**Issue flags:** ['term_miss']

### `q19` - kw=1.00 refL=1.00 refS=0.50 len=1177 (gold 422)
**Q:** A pharmaceutical company wants to use an AI system to monitor the emotions and stress levels of their manufacturing line workers to improve efficiency. Is this allowed?

**Fresh answer:** No, this is prohibited. Article 5(1)(f) bans the use of AI to infer emotions of natural persons in the workplace, and monitoring manufacturing line workers' emotions and stress levels to improve efficiency falls squarely within that prohibition. The narrow carve-out for emotion-recognition systems placed on the market strictly for medical or safety reasons (for example therapeutic use or fatigue detection for accident prevention) does not apply here, because the stated purpose is efficiency rather than a primary medical or safety objective, and the carve-out cannot be retrofitted post-hoc. Because the practice is prohibited outright, no downstream compliance route (deployer measures under Article 5, accuracy and robustness under Article 15, or worker-information duties under Article 26) can render it lawful; the use must not be deployed. If the company instead genuinely needs physical-state monitoring for worker safety, only a system whose primary purpose at market placement is safety (such as fatigue or pain detection, which Recital 18 excludes from the "emotion" definition) could be lawful, and that would shift the analysis out of the Article 5 prohibition.

**Refs:** pred `['Article 5.1.f', 'Article 5', 'Article 15', 'Article 26']` vs gold `['Article 5']` - over-cited `['Article 15', 'Article 26']`

**Gold answer:** No. Article 5(1)(f) prohibits AI systems that infer the emotions of workers in workplace settings, and deploying one to improve manufacturing efficiency falls squarely within the ban. The only carve-out is for systems placed on the market strictly for medical or safety reasons, such as fatigue detection to prevent accidents, which must be the primary purpose at market placement; efficiency improvement does not qualify.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose']

### `q20` - kw=0.43 refL=0.50 refS=0.44 len=1798 (gold 416)
**Q:** Is an AI system intended to be used as a safety component in robotic surgery considered high-risk under the AI Act?

**Fresh answer:** Likely high-risk under Article 6(1). An AI system intended to be used as a safety component of a product covered by the Union harmonisation legislation listed in here, a medical device governed by the Medical Device Regulation, is classified as high-risk where that product is required to undergo a third-party conformity assessment. Robotic surgery equipment is a medical device, and devices of this class are subject to notified-body (third-party) conformity assessment under the sectoral medical-device legislation; both limbs of the Article 6(1) test are therefore met, and the AI safety component inherits high-risk status. The deciding condition is the third-party conformity-assessment requirement: classification under Article 6(1) holds because the underlying medical device may not be self-certified. If, exceptionally, a given device fell into a class permitting self-assessment without notified-body involvement, the Article 6(1) route would not be triggered on that basis. Consequent to high-risk classification, Article 43 governs the conformity-assessment obligation, carried out under the relevant sectoral (medical-device) legislation with notified-body involvement where that legislation so requires; Annex I is the operative list identifying the medical-device legislation that brings the product within scope. Note that this is the Article 6(1) (Annex I) route, distinct from the Annex III route, so the Annex III categories and the Article 49 registration carve-out are not the operative basis here. The high-risk classification additionally triggers the Chapter III provider obligations (Articles 9 to 15 and related), which stack on top of the sectoral medical-device requirements; the specific content of those obligations is not substantiated by the provisions cited above.

**Refs:** pred `['Article 6', 'Article 6.1', 'Article 43', 'Annex I', 'Article 49', 'Annex III']` vs gold `['Article 6', 'Annex I', 'Article 14', 'Article 72']` - over-cited `['Annex III', 'Article 43', 'Article 49']` - MISSING `['Article 14', 'Article 72']`

**Gold answer:** Yes. A robotic-surgery AI safety component is part of a medical device that is typically Class IIb or III under MDR and requires notified-body conformity assessment, so it is high-risk under Article 6(1). Beyond the rule, real-time involvement in the surgical control loop engages the Article 14 human-oversight design requirements and layered post-market monitoring under AI Act Article 72 alongside MDR Article 83.

**Missed keywords:** `['notified body', 'human oversight', 'Article 14', 'Article 72']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Expert remarks (original answer):** [generic_application] Generic medical-device rule; does not engage robotic-surgery specifics (Art 14 human oversight, Art 72 post-market).

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss', 'first_person']

---

## GraphRAG-paper (Aggio et al.) answers + citations  (n=23)

### `gt_01` - kw=1.00 refL=0.75 refS=0.55 len=2312 (gold 196)
**Q:** What risk categories are provided for AI systems?

**Fresh answer:** The EU AI Act provides four risk tiers for AI systems, plus a parallel regime for general-purpose AI models, this is a framework question rather than a classification of a specific use-case, so the verdict is the structure itself. Unacceptable risk (prohibited). Under Article 5, eight categories of practice are banned outright, including (a) subliminal, manipulative, or deceptive techniques that cause significant harm, and (b) exploitation of vulnerabilities arising from age, disability, or socio-economic situation. Systems in this tier may not be placed on the market or used at all. High risk. Under Article 6, a system is classified as high-risk by either of two routes: (i) it is a safety component of, or is itself, a product covered by EU harmonisation legislation requiring third-party conformity assessment; or (ii) it falls within one of the eight use-case categories in Annex III (biometrics, critical infrastructure, education and vocational training, employment and worker management, and the further Annex III headings). High-risk classification triggers the Chapter III obligations, though those substantive duties are not detailed in the present references. Limited risk (transparency). Under Article 50, certain systems carry transparency duties only: providers must ensure systems interacting with natural persons disclose their AI nature (Article 50(1)) and must mark synthetic AI-generated content in a machine-readable, detectable format. Minimal risk. Systems falling outside the tiers above carry no mandatory obligations under the Act. Parallel regime, general-purpose AI models. Separately from the four tiers, Article 51 classifies a general-purpose AI model as posing systemic risk when it has high-impact capabilities (presumed when cumulative training compute exceeds 10²⁵ FLOPs) or when so designated by the Commission on the Annex XIII criteria. These models are governed under their own provisions rather than the use-case tiers above. Note the two tiers in Article 5 and Article 6 are distinct: a practice is prohibited under Article 5 only where it meets that article's harm and manipulation/exploitation conditions, whereas a system is instead merely high-risk under Article 6 where it falls within the Annex I or Annex III routes without crossing the Article 5 threshold.

**Refs:** pred `['Article 5', 'Article 6', 'Article 50', 'Article 50.1', 'Annex III', 'Article 51', 'Annex XIII', 'Annex I']` vs gold `['Article 3', 'Article 5', 'Article 6', 'Article 50']` - over-cited `['Annex I', 'Annex III', 'Annex XIII', 'Article 51']` - MISSING `['Article 3']`

**Gold answer:** The AI Act establishes a risk-based framework, categorising AI systems based on their potential for harm. Here are the risk categories: Unacceptable Risk, High Risk, Limited Risk and Minimal Risk.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'first_person']

### `gt_02` - kw=1.00 refL=1.00 refS=0.40 len=2718 (gold 647)
**Q:** What types of AI systems or practices are explicitly prohibited by the AI Act?

**Fresh answer:** Article 5 of the AI Act explicitly prohibits eight categories of AI practice, regardless of risk tier. Subliminal, manipulative, or deceptive techniques that materially distort behaviour and cause or are likely to cause significant harm (Article 5(1)(a)). Exploitation of vulnerabilities arising from age, disability, or a specific social or economic situation to distort behaviour and cause significant harm (Article 5(1)(b)); this expressly captures systems that leverage the developmental or cognitive vulnerabilities of minors. Social scoring of natural persons where the score leads to detrimental treatment in unrelated social contexts or to treatment that is unjustified or disproportionate (Article 5(1)(c)); lawful evaluation carried out for a specific purpose under Union or national law is not affected. Criminal-risk profiling that assesses or predicts the likelihood of offending based solely on personality traits, with an exception for systems that support a human assessment grounded in objective, verifiable facts (Article 5(1)(d)). Untargeted scraping of facial images from the internet or CCTV to build or expand facial-recognition databases (Article 5(1)(e)). Emotion inference in the workplace and in educational institutions, save for systems placed on the market strictly for medical or safety reasons such as therapeutic use or driver/pilot fatigue detection (Article 5(1)(f)). Biometric categorisation that classifies persons by sensitive attributes (race, ethnicity, political opinions, religious or philosophical beliefs, trade-union membership, sex life, or sexual orientation), excluding lawful labelling or filtering of lawfully acquired biometric datasets (Article 5(1)(g)). Real-time remote biometric identification in publicly accessible spaces for law-enforcement purposes (Article 5(1)(h)), permitted only for three exhaustively listed objectives (targeted search for abduction/trafficking/exploitation victims and missing persons; prevention of a substantial and imminent threat to life or a foreseeable terrorist attack; and localisation of suspects of serious Annex II offences punishable by at least four years' custody). The law-enforcement exception is narrow and procedurally heavy: it requires a prior fundamental rights impact assessment (Article 27, the deployer assessment covering affected persons, specific risks, and human-oversight measures), registration in the EU database before use (Article 49), and prior judicial or independent administrative authorisation, with an urgency carve-out requiring authorisation within 24 hours or immediate cessation. Under Article 5(5), Member States may legislate to enable these exceptions and may impose stricter national rules.

**Refs:** pred `['Article 5', 'Article 27', 'Article 49', 'Annex II']` vs gold `['Article 5']` - over-cited `['Annex II', 'Article 27', 'Article 49']`

**Gold answer:** Subliminal techniques beyond a person's consciousness to materially distort behaviour in a way that causes harm. Exploiting vulnerabilities of specific groups (e.g., age, disability) to materially distort behaviour and cause harm. Social scoring systems can lead to detrimental treatment in unrelated social contexts or disproportionate treatment. Real-time remote biometric identification systems in publicly accessible spaces for law enforcement purposes, except for specific exceptions. AI systems used by or on behalf of law enforcement to make risk assessments for predicting criminal offenses based solely on profiling or personality traits.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'over_citation']

### `gt_03` - kw=0.33 refL=1.00 refS=0.40 len=1704 (gold 421)
**Q:** What is the definition of high risk?

**Fresh answer:** An AI system is high-risk under one of two routes in Article 6, which sets the classification rules. Under the Annex I route (Article 6(1)), the system is high-risk if it is itself, or is a safety component of, a product covered by the Union harmonisation legislation listed in Annex I (Section A New Legislative Framework instruments such as machinery, toys, radio equipment, medical devices and lifts; Section B instruments covering civil aviation, motor vehicles, marine equipment, rail and agricultural vehicles), and that product must undergo a third-party conformity assessment under that sectoral legislation. Under the Annex III route (Article 6(2)), the system is high-risk if it falls within one of the eight listed use-case categories: biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration, asylum and border control, and administration of justice and democratic processes. A narrow exception applies: under the Article 6(3) derogation, an Annex III system is not high-risk where it poses no significant risk of harm and meets one of four conditions (it performs a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or carries out a preparatory task), unless it profiles natural persons, in which case it remains high-risk. A provider relying on this derogation must document the self-assessment before placing the system on the market and still register it under Article 49(2), which requires registration of Annex III high-risk systems.

**Refs:** pred `['Article 6', 'Annex I', 'Annex III', 'Article 49', 'Article 49.2']` vs gold `['Article 6']` - over-cited `['Annex I', 'Annex III', 'Article 49']`

**Gold answer:** The AI Act defines 'high risk' in the context of AI systems that pose significant risks to the health and safety or the fundamental rights of persons. This determination considers both the severity of the possible harm and the probability of its occurrence. The Act specifically outlines two main categories of high-risk AI systems: AI Systems Integrated into Products and Stand-alone High-Risk AI Systems. See Annex III.

**Missed keywords:** `['health', 'fundamental rights']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'over_citation', 'term_miss', 'first_person']

### `gt_04` - kw=1.00 refL=1.00 refS=0.40 len=1638 (gold 504)
**Q:** Which sectors or applications are considered high-risk under the regulation?

**Fresh answer:** High-risk classification runs on two routes. The Annex III route (Article 6(2)) covers eight use-case categories: biometrics; critical infrastructure; education and vocational training; employment and worker management (recruitment, task allocation, promotion and termination decisions, and performance evaluation affecting workers' fundamental rights); essential private and public services; law enforcement; migration, asylum and border control; and the administration of justice and democratic processes (Annex III). The Annex I route (Article 6(1)) instead classifies a system as high-risk when it is, or is a safety component of, a product covered by the Union harmonisation legislation listed in Annex I (Section A New Legislative Framework items such as machinery, toys, radio equipment, medical devices and lifts; Section B items such as civil aviation, motor vehicles, marine equipment, rail and agricultural vehicles) and that product must undergo a third-party conformity assessment under that sectoral legislation. Falling within Annex III is not automatically decisive: the Article 6(3) derogation removes a system from high-risk status where it poses no significant risk of harm and performs only a narrow procedural task, improves the result of a previously completed human activity, detects decision-making patterns or deviations without replacing or influencing the human assessment, or carries out a preparatory task, unless it profiles natural persons, in which case it remains high-risk; the provider must document this self-assessment before placing the system on the market and still register it under Article 49(2).

**Refs:** pred `['Article 6', 'Annex III', 'Annex I', 'Article 49', 'Article 49.2']` vs gold `['Article 6']` - over-cited `['Annex I', 'Annex III', 'Article 49']`

**Gold answer:** An AI system shall be considered high-risk where both of the following conditions are fulfilled: (a) the AI system is intended to be used as a safety component of a product, or is itself a product, covered by the Union harmonisation legislation listed in Annex I; (b) the product is required to undergo a third-party conformity assessment before being placed on the market or put into service under that Annex I legislation. In addition, AI systems referred to in Annex III shall be considered high-risk.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'over_citation', 'first_person']

### `gt_05` - kw=0.00 refL=1.00 refS=1.00 len=887 (gold 607)
**Q:** How should users be informed when interacting with AI systems?

**Fresh answer:** This disclosure should be made in a clear and distinguishable manner at the latest at the point of first interaction. A narrow carve-out applies under Article 50(1) to AI systems authorised by law to detect, prevent, or investigate criminal offences, subject to appropriate safeguards for third-party rights; that exception is itself reversed where the system is available to the public to report a criminal offence, so disclosure remains required. Note that Article 50 also imposes related but distinct transparency duties: providers of systems generating synthetic content must mark outputs in a machine-readable format detectable as artificially generated or manipulated (Article 50(2)), while deployers must inform persons exposed to emotion-recognition or biometric-categorisation systems (Article 50(3)) and label deepfakes as artificially generated or manipulated (Article 50(4)).

**Refs:** pred `['Article 50.1', 'Article 50']` vs gold `['Article 50']`

**Gold answer:** When interacting with an AI system, natural persons should be informed that they are interacting with an AI system unless it is obvious. Deployers of emotion recognition or biometric categorisation systems should inform natural persons exposed to the system of its operation. Deployers of an AI system that generates or manipulates text published to inform the public on matters of public interest shall disclose that the text has been artificially generated or manipulated. Information should be provided in a clear and distinguishable manner at the latest at the time of the first interaction or exposure.

**Missed keywords:** `['informed', 'interacting', 'disclose']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['term_miss']

### `gt_06` - kw=0.33 refL=0.00 refS=0.00 len=805 (gold 506)
**Q:** What are AI systems with minimal risks?

**Fresh answer:** Minimal-risk AI systems are the residual category: any system that is not prohibited under Article 5 (which bans practices such as harmful subliminal or manipulative techniques and the exploitation of vulnerabilities based on age, disability, or socio-economic situation), not high-risk under Article 6 (as an Annex I safety component or an Annex III use case), and not caught by the Article 50 transparency duties (which require, for example, disclosing that a person is interacting with an AI system and marking AI-generated synthetic content in a machine-readable format). Typical examples include AI-enabled spam filters, inventory-management tools, and AI in video games. They carry no mandatory obligations under the Regulation, though providers and deployers may voluntarily adopt codes of conduct.

**Refs:** pred `['Article 5', 'Article 6', 'Article 50', 'Annex I', 'Annex III']` vs gold `[]` - over-cited `['Annex I', 'Annex III', 'Article 5', 'Article 50', 'Article 6']`

**Gold answer:** AI systems may be developed for purposes that do not pose significant risks to health, safety, or fundamental rights. These include: a system that transforms unstructured data into structured data; one that classifies incoming documents into categories; one used to detect duplicates among many applications; one that improves the language used in documents without changing their substance; one that detects decision-making patterns or deviations; and one that performs tasks preparatory to an assessment.

**Missed keywords:** `['structured data', 'duplicates']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['over_citation', 'term_miss', 'first_person']

### `gt_07` - kw=1.00 refL=0.00 refS=0.00 len=1070 (gold 117)
**Q:** What are the guiding principles established by the AI Act?

**Fresh answer:** The EU AI Act establishes seven guiding principles that flow from Article 1's stated purpose of promoting human-centric and trustworthy AI while ensuring a high level of protection of health, safety, fundamental rights, democracy, and the rule of law: human agency and oversight; technical robustness and safety; privacy and data governance; transparency; diversity, non-discrimination and fairness; social and environmental wellbeing; and accountability. These principles are not free-standing obligations but inform the Act's operative regime, which Article 1 frames by laying down harmonised rules for placing AI systems on the market, putting them into service, and using them, including prohibitions, high-risk requirements, transparency duties, and rules for general-purpose AI. Article 4 operationalises the principles at the workforce level, requiring providers and deployers to ensure a sufficient level of AI literacy among staff and others operating AI systems on their behalf, taking account of their technical knowledge, experience, education, and training.

**Refs:** pred `['Article 1', 'Article 4']` vs gold `[]` - over-cited `['Article 1', 'Article 4']`

**Gold answer:** Protection of fundamental rights, including democracy, the rule of law, environmental protection, health, and safety.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.7`

**Issue flags:** ['verbose']

### `gt_08` - kw=1.00 refL=1.00 refS=1.00 len=655 (gold 354)
**Q:** What is the definition of a "system of artificial intelligence"?

**Fresh answer:** Under Article 3, which defines the terms used in the Regulation, an "AI system" is a machine-based system designed to operate with varying levels of autonomy, that may exhibit adaptiveness after deployment, and that, for explicit or implicit objectives, infers from the input it receives how to generate outputs such as predictions, content, recommendations, or decisions that can influence physical or virtual environments. The defining features are therefore machine-based operation, autonomy of varying degrees, possible post-deployment adaptiveness, and the capacity to infer from inputs how to generate outputs affecting real or virtual environments.

**Refs:** pred `['Article 3.1']` vs gold `['Article 3']`

**Gold answer:** A machine-based system that is designed to operate with varying levels of autonomy and that may exhibit adaptiveness after deployment, and that, for explicit or implicit objectives, infers, from the input it receives, how to generate outputs such as predictions, content, recommendations, or decisions that can influence physical or virtual environments.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.7`

**Issue flags:** - clean

### `gt_09` - kw=1.00 refL=1.00 refS=0.67 len=892 (gold 256)
**Q:** What are the penalties for violating the provisions of the regulation for high-risk AI systems?

**Fresh answer:** Penalties for high-risk AI system violations are governed by Article 99, which sets a tiered administrative fine regime. For non-compliance by providers, deployers, importers, or distributors with the high-risk obligations (all obligations other than the Article 5 prohibited practices), Article 99(4) caps fines at up to EUR 15 000 000 or, for an undertaking, up to 3 % of total worldwide annual turnover for the preceding financial year, whichever is higher. The Article 5 prohibited practices carry the higher ceiling under Article 99(3) of EUR 35 000 000 or 7 % of worldwide annual turnover, so most high-risk breaches fall under the 3 % tier rather than this top band. Under Article 99(6), where the offender is an SME or start-up, each fine is capped at the lower of the applicable percentage or fixed amount, and in all cases penalties must be effective, proportionate, and dissuasive.

**Refs:** pred `['Article 99', 'Article 5']` vs gold `['Article 99']` - over-cited `['Article 5']`

**Gold answer:** Breaches of provisions concerning high-risk AI systems, including transparency obligations for providers and deployers, can result in administrative fines of up to 15,000,000 EUR or 3% of the offender's total worldwide annual turnover, whichever is higher.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.7`

**Issue flags:** ['verbose']

### `gt_10` - kw=0.67 refL=1.00 refS=0.67 len=1367 (gold 569)
**Q:** What is the difference between the deployer and the provider?

**Fresh answer:** The provider and the deployer are distinct actors: the provider develops an AI system (or has one developed) and places it on the market or puts it into service under its own name, whereas the deployer uses an AI system under its authority in a professional capacity. Article 3 sets out these defining terms, and the practical difference is the weight of obligations each bears. Under Article 16, providers of high-risk AI systems carry the principal compliance burden: ensuring the system meets the Chapter III Section 2 requirements and bears their identity, operating a quality-management system (Article 17, covering regulatory-compliance strategy, design verification, testing, post-market monitoring, and incident reporting), keeping the technical documentation and the system's automatically generated logs (Article 19 requires retaining those logs for at least six months), conducting conformity assessment, drawing up the EU declaration of conformity, affixing the CE marking, registering the system, taking corrective action, and demonstrating compliance to authorities on request. Deployers, by contrast, are subject to the narrower duties of Articles 26 and 27, which govern use of the system and, in defined cases, a fundamental-rights impact assessment, rather than the design, conformity-assessment, and market-entry obligations that fall on providers.

**Refs:** pred `['Article 3', 'Article 16', 'Article 17', 'Article 19']` vs gold `['Article 3', 'Article 16']` - over-cited `['Article 17', 'Article 19']`

**Gold answer:** The Provider is a natural or legal person, public authority, agency or other body that develops an AI system or a general-purpose AI model (or has one developed) and places it on the market or puts it into service under its own name or trademark. The Deployer is a natural or legal person, public authority, agency or other body using an AI system under its authority, except for personal non-professional activity. The provider bears primary responsibility for AI Act compliance, especially for high-risk systems; the deployer uses the system for its intended purpose.

**Missed keywords:** `['trademark']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'term_miss']

### `ng_01` - kw=0.50 refL=1.00 refS=0.57 len=1768 (gold 317)
**Q:** What criteria exist for assessing the risk of an AI system?

**Fresh answer:** The criteria fall into two distinct layers. First, for classifying whether an AI system belongs in a high-risk category, Article 7 lets the Commission add, modify, or remove Annex III use-cases by delegated act using criteria such as the system's intended purpose, the extent of its use, its impact on health, safety, or fundamental rights, the severity and reversibility of potential harm, and the availability of redress; Annex III itself fixes the eight current high-risk use-case categories (biometrics; critical infrastructure; education and vocational training; employment and worker management; essential private and public services; law enforcement; migration, asylum, and border control; and administration of justice and democratic processes). Second, once a system is high-risk, Article 9 requires a documented, iterative risk-management system running across the lifecycle, under which providers must identify and analyse known and reasonably foreseeable risks to health, safety, or fundamental rights (Article 9(2)(a)), estimate and evaluate risks arising both from intended use and reasonably foreseeable misuse (Article 9(2)(b)), test the system to identify the most appropriate targeted mitigation measures and to confirm consistent performance (Article 9(5)), and judge each residual risk and the overall residual risk acceptable, communicating them to the deployer (Article 9(6)); Article 9(4) further requires weighing the combined effect and interaction of the various requirements to balance and minimise risk. Supporting assessments feed this system, including the data-quality and bias-examination criteria for training, validation, and test datasets under Article 10, and the operational-transparency criteria toward deployers under Article 13.

**Refs:** pred `['Article 7', 'Article 9', 'Article 10', 'Article 13', 'Annex III']` vs gold `['Article 7', 'Article 9']` - over-cited `['Annex III', 'Article 10', 'Article 13']`

**Gold answer:** The criteria for assessing the risk of an AI system under the AI Act include: intended purpose, context and extent of use, nature and amount of data processed, system autonomy, likelihood and severity of harm to health/fundamental rights, risks to vulnerable groups (like children), and availability of legal redress.

**Missed keywords:** `['likelihood of harm', 'vulnerable groups']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `ng_02` - kw=0.75 refL=1.00 refS=0.22 len=1558 (gold 307)
**Q:** What are the sanctions for violating the provisions of the regulation for transparency risk systems?

**Fresh answer:** Violations of the transparency obligations for providers and deployers under Article 50 (which require disclosing that a system is AI when it interacts with people, marking synthetic content in machine-readable form, informing persons exposed to emotion-recognition or biometric-categorisation systems, and labelling deepfakes) fall under Article 99(4): an administrative fine of up to EUR 15 000 000 or, if the offender is a company, up to 3% of total worldwide annual turnover for the preceding financial year, whichever is higher. Article 99(4) groups these Article 50 transparency breaches with a closed list of other operator and notified-body infringements (provider obligations under Article 16, authorised-representative obligations under Article 22, importer obligations under Article 23, distributor obligations under Article 24, deployer obligations under Article 26, and notified-body requirements under Articles 31, 33(1), (3) and (4), and 34), all sharing the same 15M/3% ceiling. Under Article 99(6), where the offender is an SME or start-up, the applicable ceiling is the lower of the percentage or the fixed amount, and all penalties must be effective, proportionate and dissuasive and set in line with the gravity and nature of the infringement. For context, this is distinct from the higher tier in Article 99(3) (up to EUR 35M or 7% for the Article 5 prohibited practices) and the lower tier in Article 99(5) (up to EUR 7.5M or 1% for supplying incorrect, incomplete or misleading information to notified bodies or competent authorities).

**Refs:** pred `['Article 99', 'Article 50', 'Article 16', 'Article 22', 'Article 23', 'Article 24', 'Article 26', 'Article 5']` vs gold `['Article 99']` - over-cited `['Article 16', 'Article 22', 'Article 23', 'Article 24', 'Article 26', 'Article 5', 'Article 50']`

**Gold answer:** Sanctions for violating transparency obligations under Article 50 include administrative fines of up to 15,000,000 EUR or 3% of the offender's total worldwide annual turnover for the preceding financial year, whichever is higher. Penalties must be effective, proportionate, and dissuasive, considering SMEs.

**Missed keywords:** `['effectiveness']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `ng_03` - kw=0.80 refL=1.00 refS=0.57 len=1959 (gold 374)
**Q:** What obligations exist for deployers of high-risk AI systems?

**Fresh answer:** Deployers of high-risk AI systems carry duties under Article 26: take appropriate technical and organisational measures to use the system in accordance with its instructions of use (Article 26(1)), assign human oversight to competent and trained natural persons, monitor the system's operation against those instructions and inform the provider of serious incidents (Article 26(5)), and retain the automatically generated logs that are under their control (Article 26(6)). They must also cooperate with market-surveillance authorities. Two workplace-specific duties attach where the deployer is an employer: before putting a high-risk system into service, inform the workers' representatives and the affected workers (Article 26(7)), and existing Union and national worker-information rules continue to apply alongside this. A sector carve-out applies to deployers that are financial institutions subject to Union financial-services internal-governance requirements: they satisfy the monitoring obligation (Article 26(5)) and the log-retention obligation (Article 26(6)) by complying with the governance arrangements under that financial-services law. Separately, deployers of the Annex III high-risk systems referred to in Article 6(2), together with public-sector deployers, must perform a Fundamental Rights Impact Assessment before first use, covering the deployment process, the affected persons, the specific risks, the human-oversight measures, and the complaints workflows (Article 27). Finally, a deployer assumes the full set of provider obligations (including the quality-management, conformity-assessment, declaration-of-conformity and CE-marking duties) only if it crosses into provider status under Article 25, that is, by putting its name or trademark on the system, making a substantial modification, or changing the intended purpose so that the system becomes high-risk; absent any of these, the provider-only duties do not bind the deployer.

**Refs:** pred `['Article 26', 'Article 27', 'Article 25', 'Annex III', 'Article 6', 'Article 6.2']` vs gold `['Article 26', 'Article 27']` - over-cited `['Annex III', 'Article 25', 'Article 6']`

**Gold answer:** Obligations for deployers of high-risk AI systems include: taking appropriate technical and organizational measures, using systems in accordance with provided instructions, monitoring system operation, keeping automatically generated logs for at least six months, performing a Fundamental Rights Impact Assessment (FRIA), and informing natural persons exposed to the system.

**Missed keywords:** `['instructions for use']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `ng_04` - kw=1.00 refL=1.00 refS=0.62 len=2622 (gold 381)
**Q:** What requirements must AI systems classified as high-risk meet?

**Fresh answer:** High-risk AI systems must meet the Chapter III requirements in Articles 9 to 15, triggered automatically by classification under Article 6 (Annex I safety components subject to third-party conformity assessment, or one of the eight Annex III use cases). Specifically, the provider must. Risk management (Article 9): establish, document and maintain an iterative, lifecycle risk-management system that identifies and analyses known and foreseeable risks to health, safety and fundamental rights, estimates risks under intended use and reasonably foreseeable misuse, evaluates post-market data, and adopts targeted mitigation measures; the system must be tested to ensure consistent performance, and residual risks must be judged acceptable and communicated to the deployer. Data governance (Article 10): ensure training, validation and test datasets are relevant, representative, error-free and complete, with governance practices covering provenance, preparation, bias examination and mitigation, and special-category data handling. Technical documentation (Article 11 and Annex IV): draw up documentation before the system is placed on the market, keep it up to date, and demonstrate conformity to the essential requirements, with the minimum content set out in Annex IV (SMEs may use the simplified form). Transparency to deployers (Article 13): design the system to be sufficiently transparent for deployers to interpret and use its output appropriately, accompanied by instructions for use covering provider identity, intended purpose, capabilities and limitations, accuracy/robustness/cybersecurity levels, human-oversight measures and maintenance. Human oversight (Article 14): enable effective oversight by competent natural persons, including capability/limitation awareness, automation-bias safeguards, correct interpretation of output, and the ability to override or intervene. Accuracy, robustness and cybersecurity (Article 15): achieve appropriate levels across the lifecycle, with accuracy metrics declared in the instructions for use and resilience against errors and against data-poisoning, evasion, model-confidentiality and adversarial attacks. One qualification on classification: under the Article 6(3) derogation, an Annex III system is not high-risk (and so not bound by these requirements) where it poses no significant risk of harm and performs only a narrow procedural, preparatory, result-improving or pattern-detection task, unless it profiles natural persons, in which case it remains high-risk; the provider must document that self-assessment and still register the system under Article 49(2).

**Refs:** pred `['Article 6', 'Article 6.3', 'Article 9', 'Article 11', 'Article 13', 'Article 10', 'Article 14', 'Article 15', 'Article 49', 'Article 49.2', 'Annex I', 'Annex III', 'Annex IV']` vs gold `['Article 9', 'Article 11', 'Article 13', 'Article 14', 'Article 15']` - over-cited `['Annex I', 'Annex III', 'Annex IV', 'Article 10', 'Article 49', 'Article 6']`

**Gold answer:** High-risk AI systems must meet mandatory requirements: establishing a comprehensive risk management system; ensuring high data quality and governance standards; preparing detailed technical documentation; maintaining automatic record-keeping (logs); ensuring transparency and clear instructions; enabling human oversight; and achieving high robustness, accuracy, and cybersecurity.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'first_person']

### `ng_05` - kw=1.00 refL=0.80 refS=0.50 len=2582 (gold 342)
**Q:** What obligations do providers of high-risk AI systems have in terms of transparency and technical documentation?

**Fresh answer:** Providers of high-risk AI systems carry two distinct sets of obligations here, technical documentation and transparency. Technical documentation. Under Article 11, the provider must draw up technical documentation before the system is placed on the market or put into service and keep it up to date, demonstrating conformity with the Section-2 requirements; its content must cover, at a minimum, the elements set out in Annex IV (system description and architecture, design specifications, data and training methodology, human oversight, risk-management measures, validation and testing procedures, and the post-market monitoring system), with SMEs permitted to supply these elements in the simplified form provided by the Commission. Article 18 then requires the provider to retain that documentation, together with the quality-management-system documentation (Article 17), any notified-body documents, and the EU declaration of conformity (Article 47), for 10 years after placement on the market and to make it available to national competent authorities on request. On a reasoned request, Article 21 obliges the provider to hand over all information and documentation needed to demonstrate conformity in an official Union language, with that material protected as confidential under Article 78. Transparency. Article 13 requires the system to be designed for sufficient operational transparency to enable deployers to interpret and appropriately use its output, and to be accompanied by instructions for use stating the provider's identity, the intended purpose, the system's capabilities and limitations, expected lifetime, human-oversight measures, required maintenance, and (per Article 13(3)(b)(ii)) the foreseeable circumstances that may create risks to health, safety or fundamental rights along with the levels of accuracy, robustness and cybersecurity. Separately, Article 50 imposes provider-level transparency to end users: systems interacting with natural persons must disclose their AI nature, and AI-generated synthetic content must be marked in a machine-readable, detectable format; where an Annex-III biometric-identification, emotion-recognition or biometric-categorisation system is involved, Article 26(11) preserves these Article 50 end-user duties on top of the Article 13 transparency owed to deployers. If the provider is established outside the EU, Article 22 additionally requires appointing an authorised representative empowered to verify the documentation was drawn up, keep it available for 10 years, and supply it to authorities on reasoned request.

**Refs:** pred `['Annex IV', 'Article 11', 'Article 13', 'Article 13.3.b.ii', 'Article 18', 'Annex IV.2', 'Article 17', 'Article 47', 'Article 21', 'Article 78', 'Article 50', 'Article 26', 'Article 26.11', 'Article 22']` vs gold `['Article 11', 'Article 13', 'Article 18', 'Article 21', 'Article 23']` - over-cited `['Annex IV', 'Article 17', 'Article 22', 'Article 26', 'Article 47', 'Article 50', 'Article 78']` - MISSING `['Article 23']`

**Gold answer:** Providers of high-risk AI systems must prepare comprehensive technical documentation before market placement, keep it up-to-date for 10 years, design systems to ensure transparency, provide clear instructions for use (identity, capabilities, and risks), and supply all necessary documentation to competent authorities upon a reasoned request.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'under_citation']

### `ng_06` - kw=0.75 refL=1.00 refS=0.75 len=1247 (gold 339)
**Q:** What does a conformity assessment consist of?

**Fresh answer:** A conformity assessment is the procedure by which a provider of a high-risk AI system demonstrates, before placing it on the market, that the system meets the high-risk requirements, and Article 43 offers two routes. Where the provider has applied harmonised standards or common specifications to an Annex III system, it follows the internal-control procedure of Annex VI: the provider itself verifies that its quality management system conforms to Article 17, examines the technical documentation, and confirms the design, development, and post-market monitoring plan, with no notified body involved. Otherwise, or for Annex III biometric systems where those standards are not fully applied, the provider must use the Annex VII procedure, under which a notified body audits the quality management system, examines the technical documentation, and issues an EU technical-documentation assessment certificate. For AI that is a safety component of a product already covered by sectoral Union law, Article 43(3) folds the AI Act assessment into that sector's existing third-party procedure, so a single assessment covers both regimes. A fresh conformity assessment is required whenever the system undergoes a substantial modification (Article 43(4)).

**Refs:** pred `['Article 43', 'Article 43.3', 'Article 43.4', 'Annex VI', 'Annex VII', 'Article 17', 'Annex III']` vs gold `['Article 43', 'Annex VI', 'Annex VII']` - over-cited `['Annex III', 'Article 17']`

**Gold answer:** A conformity assessment consists of procedures to verify and demonstrate compliance with high-risk requirements. Providers can choose between internal control (Annex VI) or a quality management system and technical documentation assessment by a notified body (Annex VII), resulting in a certificate of conformity or assessment certificate.

**Missed keywords:** `['internal control']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'term_miss']

### `ng_07` - kw=1.00 refL=0.50 refS=0.67 len=842 (gold 278)
**Q:** What does systemic-risk mean?

**Fresh answer:** Systemic risk is a defined term under Article 3, the Regulation's definitions provision, where it refers to a risk specific to the high-impact capabilities of general-purpose AI models, having a significant impact on the Union market due to the model's reach or actual or reasonably foreseeable negative effects on public health, safety, public security, fundamental rights, or society as a whole, capable of being propagated at scale across the value chain. In practice this concept attaches to general-purpose AI models (also defined in Article 3) that meet the high-impact threshold, triggering the heightened provider duties for such models set out in the General-Purpose AI obligations (Articles 51-56), which govern classification of models with systemic risk and their attendant evaluation, risk-mitigation, and reporting requirements.

**Refs:** pred `['Article 3.65']` vs gold `['Article 3', 'Article 55']` - MISSING `['Article 55']`

**Gold answer:** Systemic risk is a risk specific to the high-impact capabilities of general-purpose AI models that can propagate at scale across the value chain, causing actual or foreseeable negative effects on public health, safety, public security, fundamental rights, or society as a whole.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.7` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'under_citation']

### `ng_08` - kw=0.00 refL=1.00 refS=0.40 len=861 (gold 295)
**Q:** What is the definition of General-purpose AI?

**Fresh answer:** Article 3 separately defines a "general-purpose AI system," meaning an AI system based on such a model that itself serves a variety of purposes, whether used directly or integrated into other systems. For practical scoping, the Commission's 18 July 2025 GPAI Guidelines presume a model is general-purpose under Article 3 when its cumulative training compute exceeds 10^23 FLOPs and it can generate language, image, audio, or video output. A general-purpose model crosses into the "systemic risk" tier (Article 3, classified under Article 51) when it has high-impact capabilities, presumed once cumulative training compute exceeds 10^25 FLOPs or upon Commission designation, which triggers the additional Article 55 obligations (model evaluation, systemic-risk mitigation, incident reporting, and cybersecurity) on top of the baseline Article 53 provider duties.

**Refs:** pred `['Article 3.63', 'Article 53', 'Article 51', 'Article 55']` vs gold `['Article 3']` - over-cited `['Article 51', 'Article 53', 'Article 55']`

**Gold answer:** A general-purpose AI model is an AI model that exhibits significant generality, is capable of competently performing a wide range of distinct tasks, and can be integrated into various downstream applications. A general-purpose AI system is built on such a model and serves a variety of purposes.

**Missed keywords:** `['general-purpose ai model', 'generality', 'distinct tasks', 'self-supervision']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `ng_09` - kw=0.50 refL=1.00 refS=0.29 len=1312 (gold 311)
**Q:** What are the components of a quality management system?

**Fresh answer:** Under Article 17, providers of high-risk AI systems must put in place a documented quality management system, set out systematically and in writing, that ensures compliance with the Regulation. Its components include: a strategy for regulatory compliance, including conformity assessment and management of modifications; techniques and procedures for design, design control, and design verification; procedures for development, quality control, and quality assurance; examination, test, and validation procedures carried out before, during, and after development; the post-market monitoring system required under Article 72; and procedures for reporting serious incidents under Article 73. These quality-management obligations sit within the broader provider duties under Article 16, which also require keeping technical documentation and the automatically generated logs (the latter retained for at least six months under Article 19), conformity assessment, the EU declaration of conformity, CE marking, EU-database registration, corrective action, and demonstrating compliance on request. For SMEs, Article 63 permits simplified compliance with these Article 17 obligations in a manner appropriate to the provider's size and market stage, without lowering the level of protection or the Section 2 requirements.

**Refs:** pred `['Article 17', 'Article 63', 'Article 16', 'Article 72', 'Article 73', 'Article 19']` vs gold `['Article 17']` - over-cited `['Article 16', 'Article 19', 'Article 63', 'Article 72', 'Article 73']`

**Gold answer:** A quality management system must include: regulatory compliance strategy; design control and verification; testing and validation procedures; data management systems (acquisition, collection, labeling); technical specifications/standards; risk management; post-market monitoring; and serious incident reporting.

**Missed keywords:** `['data management', 'testing']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `ng_10` - kw=0.80 refL=0.50 refS=0.25 len=1575 (gold 290)
**Q:** What are the requirements for documenting bias mitigation measures in AI models?

**Fresh answer:** Bias mitigation must be documented as part of the high-risk system's data governance and technical documentation duties. Article 10 requires providers to apply data-governance practices to training, validation, and testing datasets, including examination for possible biases likely to affect health and safety, harm fundamental rights, or lead to discrimination (Article 10(2)(f)), and where strictly necessary providers may process special categories of personal data to ensure bias detection and correction (Article 10(5)). These examination and mitigation measures, along with the datasets' relevance, representativeness, and completeness (Article 10(3)), must be captured in the technical documentation drawn up before market placement and kept up to date under Article 11, with content per Annex IV, which expressly covers data and training methodology, validation and testing procedures, and risk-management measures. Bias also feeds the documented, iterative risk-management system under Article 9: providers must identify and analyse foreseeable risks to fundamental rights including discrimination (Article 9(2)(a)), test for the most targeted mitigation measures (Article 9(5)), and judge and communicate residual risks to the deployer (Article 9(6)). Where bias manifests as automation bias in use, Article 14 requires human-oversight measures that keep operators aware of the tendency to over-rely on output (Article 14(4)(b)), and these oversight measures are themselves documented in the Annex IV technical documentation and the Article 13 instructions for use.

**Refs:** pred `['Article 10', 'Article 9', 'Article 14', 'Article 14.4.b', 'Article 11', 'Article 13', 'Annex IV']` vs gold `['Article 10', 'Article 15']` - over-cited `['Annex IV', 'Article 11', 'Article 13', 'Article 14', 'Article 9']` - MISSING `['Article 15']`

**Gold answer:**  document bias mitigation, providers must ensure data sets are subject to high governance, including assessing and mitigating biases affecting health, safety, or fundamental rights. Targeted measures must be documented, and continuous-learning models must mitigate loops of biased feedback.

**Missed keywords:** `['mitigate']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss']

### `gt_11` - kw=0.75 refL=1.00 refS=1.00 len=976 (gold 264)
**Q:** Does the technical documentation of a high-risk AI system require to provide specifications regarding the required hardware?

**Fresh answer:** Yes. The technical documentation of a high-risk AI system must include specifications regarding the required hardware. Under Article 11, which requires the technical documentation to be drawn up before the system is placed on the market or put into service, kept up to date, and to contain at a minimum the information set out in Annex IV, the provider must cover the system's design specifications and system architecture. Annex IV, which enumerates the required documentation contents (system description, design specifications, system architecture, data and training methodology, human oversight, risk-management measures, validation and testing procedures, and the post-market monitoring system), encompasses the general description of the system and its design, including the computational and hardware resources used to develop, train, test and run it. Providers that are SMEs may supply these elements in the simplified form provided by the Commission under Article 11.

**Refs:** pred `['Annex IV', 'Article 11', 'Annex IV.1.e']` vs gold `['Article 11', 'Annex IV']`

**Gold answer:** Yes. Article 11 requires high-risk systems to have technical documentation. Annex IV specifies that this documentation must include a general description of the system, including its architecture and the specifications of required hardware and computing resources.

**Missed keywords:** `['computing resources']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.7`

**Issue flags:** ['verbose', 'term_miss']

### `gt_12` - kw=0.80 refL=1.00 refS=0.50 len=1631 (gold 206)
**Q:** Are AI systems intended for emotion recognition from biometric data always prohibited?

**Fresh answer:** No, emotion recognition AI is prohibited only when used in the workplace or in education and training institutions; outside those two settings it is not banned but is regulated as high-risk. The operative provision is Article 5, which enumerates the prohibited practices. The prohibition on emotion recognition is confined to AI systems used to infer emotions of natural persons in the areas of workplace and education institutions, and even there a narrow exception applies where the system is placed on the market for medical or safety reasons (for example, monitoring the fatigue or alertness of a person for safety purposes). It is therefore not an absolute, context-independent prohibition. Where the use does not fall within the workplace/education scenario, the system is not prohibited but is captured by Annex III, which lists biometrics among the eight high-risk use-case categories, placing emotion recognition in the high-risk tier (subject to the standard Annex III qualifications). Note that a high-risk classification under Annex III triggers the Chapter III obligations, but those obligations are not substantiated in the references provided here and are not asserted on that basis. In addition, Article 50 imposes transparency duties: deployers of an emotion recognition system must inform the natural persons exposed to it of the system's operation, independent of the high-risk classification. In short: prohibited only in workplace and educational settings (Article 5, subject to the medical/safety exception); otherwise high-risk under Annex III with Article 50 transparency obligations toward exposed persons.

**Refs:** pred `['Article 5', 'Article 5.1.f', 'Article 50.3', 'Annex III.1.c', 'Article 50']` vs gold `['Article 5']` - over-cited `['Annex III', 'Article 50']`

**Gold answer:** No, they are not always prohibited. Under Article 5, they are specifically prohibited when used in the workplace or educational institutions, unless they are installed or used for medical or safety reasons.

**Missed keywords:** `['not always prohibited']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'term_miss']

### `gt_13` - kw=0.60 refL=1.00 refS=0.89 len=2852 (gold 512)
**Q:** Is an AI that transcribes doctor–patient conversations prohibited? Or is it high-risk as per the use cases of Annex III of the AI Act?

**Fresh answer:** Neither prohibited nor a standalone Annex III high-risk use case, transcribing doctor, patient conversations is not banned under Article 5 and is not listed among the high-risk categories of Annex III; whether it becomes high-risk turns on a single deciding fact under Article 6. Why it is not prohibited (Article 5). Article 5 forbids only eight discrete practices, subliminal, manipulative, or deceptive techniques causing significant harm, and exploitation of vulnerabilities arising from age, disability, or socio-economic situation, among the others enumerated. A system that passively converts speech to text performs none of these functions. Transcription would fall within Article 5 only if the system were deliberately engineered to deploy a manipulative or deceptive technique, or to exploit a patient's vulnerability, so as to materially distort behaviour and cause significant harm, a context defined by the prohibited technique, not by the clinical setting. Absent that, the prohibition tier does not engage. Why it is not high-risk by use case (Annex III). Annex III lists specific high-risk use-case areas (biometrics, critical infrastructure, education and vocational training, employment and worker management, among the eight). Clinical transcription corresponds to none of them. It therefore cannot be classified high-risk via the Annex III route (Article 6(2)). The deciding condition (Article 6(1) read with Annex I). It depends: the system is high-risk only if it functions as a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I (notably the Medical Devices Regulation or the In Vitro Diagnostic Regulation) and that product is required to undergo third-party conformity assessment. If the transcription tool is a mere documentation aid with no medical-device safety function, this route is not triggered and the system is not high-risk. If it is integrated into, or constitutes, an Annex I medical device subject to third-party conformity assessment, it is high-risk under Article 6(1). Residual transparency tier (Article 50). Independently of the above, where the system interacts directly with the patient as a natural person, the provider must ensure the person is informed they are interacting with an AI system (Article 50(1)); and to the extent the system generates synthetic audio or other AI-generated content, that content must be marked in a machine-readable, detectable format. These limited-risk transparency duties can apply even when the system is neither prohibited nor high-risk. Bottom line: not prohibited, not Annex III high-risk; high-risk only under Article 6(1)/Annex I if it is a medical-device safety component requiring third-party conformity assessment, otherwise limited-risk, with Article 50 transparency obligations potentially applicable.

**Refs:** pred `['Annex III', 'Article 6', 'Article 6.2', 'Article 6.1', 'Article 5', 'Annex I', 'Article 50', 'Article 50.1']` vs gold `['Article 5', 'Article 6', 'Annex I', 'Annex III']` - over-cited `['Article 50']`

**Gold answer:** It is not inherently prohibited under Article 5. Whether it is high-risk depends on its exact classification. While it is not explicitly listed in Annex III as high-risk, if the transcription system is intended to be used as a medical device (or a safety component of one) covered by EU harmonisation legislation (Annex I, e.g., the Medical Device Regulation) and requires a third-party conformity assessment, it is classified as high-risk under Article 6. Otherwise, basic transcription is minimal/limited risk.

**Missed keywords:** `['MDR', 'general purpose']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`?` conf=`0.85`

**Issue flags:** ['verbose', 'term_miss', 'first_person']

---

## MedTech-GraphRAG-v124 (medical/life-sciences)  (n=24)

### `grb_01` - kw=1.00 refL=0.67 refS=0.44 len=3115 (gold 455)
**Q:** Is AI software that detects melanoma from dermoscopy images a high-risk AI system under the EU AI Act?

**Fresh answer:** Likely high-risk, because melanoma-detection software is a safety component of, or itself is, a medical device, which routes it through Article 6(1). Operative provision. Under Article 6, an AI system is high-risk on either of two routes. The first (Article 6(1)) applies where the AI system is itself a product, or a safety component of a product, covered by the Union harmonisation legislation listed in Annex I, and that product is required to undergo a third-party conformity assessment under that legislation. Diagnostic software that detects melanoma from dermoscopy images is a medical device governed by the EU medical-device framework, which is among the Annex I harmonisation acts. The second route (Article 6(2), read with Annex III) is the eight enumerated use-case categories (biometrics, critical infrastructure, education, employment, etc.); standalone clinical diagnosis is not one of them, so the classification here rests on Article 6(1) with Annex I, not on Annex III. The deciding condition. High-risk status under Article 6(1) is not automatic from medical-device status alone, it additionally requires that the device must undergo third-party (notified-body) conformity assessment under the applicable Annex I legislation. Melanoma-diagnosis software, as software with a diagnostic medical purpose, is ordinarily classified above the lowest risk class and therefore does require notified-body involvement; on that basis it meets both limbs of Article 6(1) and is high-risk. If a particular device were, exceptionally, in a class permitting self-assessment without a notified body, the Article 6(1) trigger would not be met. This is why the verdict is "likely" rather than categorical: it turns on the device's conformity-assessment class under the medical-device regulation. Not prohibited. Article 5 exhaustively bans eight practices, subliminal/manipulative or deceptive techniques causing significant harm, exploitation of vulnerabilities based on age, disability or socio-economic situation, and the other listed categories. Clinical melanoma detection is a diagnostic aid and falls within none of these; it is therefore not prohibited. Article 5 marks the tier above high-risk (outright bans), and is distinct from the Article 6 high-risk classification that applies here, the two should not be conflated. Consequences and transparency. A high-risk classification under Article 6 engages the Chapter III provider obligations (the references substantiate the existence of a risk management system under Article 9 for high-risk systems, but the detailed Article 9 to 15 duties are not further developed in the references and are not restated here). Separately, to the extent the software interacts directly with natural persons, the Article 50 transparency duty to disclose the system's AI nature applies in parallel; Article 50 obligations attach regardless of the high-risk tier. In short: high-risk via Article 6(1) and Annex I as a medical-device safety component/product, conditional on the device requiring third-party conformity assessment; not a prohibited practice under Article 5.

**Refs:** pred `['Article 6', 'Article 6.1', 'Article 6.2', 'Article 50', 'Annex III', 'Annex I', 'Article 5', 'Article 9']` vs gold `['Article 6', 'Annex I', 'Article 43']` - over-cited `['Annex III', 'Article 5', 'Article 50', 'Article 9']` - MISSING `['Article 43']`

**Gold answer:** Yes. Under Article 6(1) an AI system that is a medical device, or a safety component of one, covered by the Union harmonisation legislation in Annex I (the Medical Device Regulation) and required to undergo third-party conformity assessment is high-risk. Such a melanoma-detection system must therefore meet the Chapter III high-risk requirements and pass the conformity assessment under Article 43, integrated with the medical-device notified-body route.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'first_person']

### `grb_02` - kw=0.80 refL=1.00 refS=1.00 len=449 (gold 351)
**Q:** Which EU AI Act article sets the transparency obligation for a patient-facing medical chatbot?

**Fresh answer:** Article 50(1) is the operative provision: a patient-facing chatbot is an AI system intended to interact directly with natural persons, so its provider must ensure it is designed so the patient is informed they are interacting with an AI system rather than a human. If the chatbot also generates synthetic content, Article 50(2) additionally requires that those outputs be marked in a machine-readable format and detectable as artificially generated.

**Refs:** pred `['Article 50.1', 'Article 50', 'Article 50.2']` vs gold `['Article 50']`

**Gold answer:** Article 50 sets the transparency obligation: the provider must ensure the chatbot is designed so that natural persons are informed they are interacting with an AI system, unless that is obvious from the circumstances. If the chatbot also performs a medical-diagnostic function it is additionally high-risk and the Chapter III obligations apply on top.

**Missed keywords:** `['transparency']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.5` answer_route=synthesis:synthesis_default

**Issue flags:** ['term_miss']

### `grb_03` - kw=0.80 refL=1.00 refS=0.80 len=2069 (gold 302)
**Q:** Under the EU AI Act, is an AI system used to dispatch and triage emergency-room patients high-risk?

**Fresh answer:** High-risk. An AI system used to triage emergency-room patients and to dispatch or prioritise emergency first-response falls squarely within Annex III(5)(d), and is therefore classified as high-risk under Article 6(2). The operative route here is Annex III: Article 6(2) treats as high-risk any system deployed in one of the listed Annex III use-case categories, and emergency healthcare patient triage and the dispatching/prioritising of emergency first-response services are expressly enumerated under Annex III(5)(d). The classification turns on the function of the system, it allocates scarce, time-critical clinical attention among patients, and not on whether the tool is independently marketed as a medical device, so no further factual condition needs to be resolved to reach the high-risk verdict on these facts. Two distinctions are worth stating so the tiers are not conflated. This system is high-risk under Article 6, not prohibited under Article 5. Article 5 prohibits a closed set of practices (e.g. subliminal/manipulative techniques causing significant harm, and exploitation of vulnerabilities by age, disability, or socio-economic situation). Ordinary clinical triage does not engage those prohibitions. The analysis would only shift to the Article 5 tier if the triage logic categorised patients by sensitive attributes in the prohibited manner, a different practice from prioritising care on clinical need. Selecting or prioritising patients in a non-emergency, research context (e.g. for a clinical trial) is not itself a listed Annex III use case; such a system would be high-risk only where it determines access to or eligibility for essential healthcare services, or where it categorises natural persons by sensitive attributes under Annex III(1)(b). That conditional path is not what is presented here. As an Annex III / Article 6(2) high-risk system, it triggers the Chapter III provider obligations; the specific substantive duties are not detailed in the references supplied, so I do not enumerate them here beyond the classification itself.

**Refs:** pred `['Article 5', 'Article 6', 'Article 6.2', 'Annex III', 'Annex III.5.d', 'Annex III.1.b']` vs gold `['Article 6', 'Annex III']` - over-cited `['Article 5']`

**Gold answer:** Yes. Annex III point 5 lists AI systems used to dispatch, or to establish priority in dispatching, emergency first-response services including patient triage as high-risk, and Article 6(2) makes Annex III systems high-risk. The deployer and provider must meet the corresponding Chapter III obligations.

**Missed keywords:** `['essential services']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'term_miss', 'first_person']

### `grb_04` - kw=1.00 refL=1.00 refS=0.36 len=1618 (gold 353)
**Q:** What does the EU AI Act require for an AI system that evaluates patients' eligibility for public healthcare benefits?

**Fresh answer:** High-risk. An AI system evaluating patients' eligibility for public healthcare benefits falls within the Annex III "essential public services" category, which lists systems assessing access to public benefits, so it is classified as high-risk under the Annex III route of Article 6(2) (a system in one of the eight Annex III use cases is high-risk unless the narrow Article 6(3) derogation applies, and even then it is always high-risk if it profiles natural persons). As a high-risk system, the provider must undergo a conformity assessment before placing it on the market: the internal-control procedure (Annex VI) where harmonised standards or common specifications are applied, otherwise the notified-body procedure (Annex VII) (Article 43). Conformity with harmonised standards published in the Official Journal gives a presumption of conformity with the corresponding Chapter III requirements to the extent those standards cover them (Article 40). The provider, and any deployer that is a public authority, must register themselves and the system in the EU database before it is placed on the market or put into service (Article 49), that database being the Commission-managed register for high-risk systems with public and restricted-access sections (Article 71). By derogation from the standard procedure, a market-surveillance authority may authorise placing the system on the market for a limited period for exceptional reasons including the protection of life and health of persons while the conformity assessment is completed, subject to notification of the Commission and other Member States (Article 46).

**Refs:** pred `['Article 40', 'Article 49', 'Article 46', 'Article 6', 'Article 6.2', 'Article 6.3', 'Article 43', 'Article 71', 'Annex III', 'Annex VI', 'Annex VII']` vs gold `['Article 6', 'Annex III']` - over-cited `['Annex VI', 'Annex VII', 'Article 40', 'Article 43', 'Article 46', 'Article 49', 'Article 71']`

**Gold answer:** Annex III point 5(a) classifies AI used by or for public authorities to evaluate eligibility for essential public assistance benefits and services, including healthcare, as high-risk under Article 6(2). The system is therefore subject to the full Chapter III high-risk regime, including a fundamental-rights impact assessment by the deploying authority.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation']

### `grb_05` - kw=0.80 refL=1.00 refS=0.50 len=699 (gold 386)
**Q:** Are AI systems used solely for scientific biomedical research and not placed on the market subject to the EU AI Act?

**Fresh answer:** No. Article 2, which defines the Regulation's scope, excludes AI systems and models specifically developed and put into service solely for scientific research and development, so an AI system used purely for scientific biomedical research and not placed on the EU market or put into service falls outside the Act. This carve-out depends on the activity remaining genuinely confined to R&D: once such a system is placed on the market or put into service for actual use, the scope under Article 2 attaches and the corresponding obligations (for high-risk systems, EU database registration before placing on the market under Article 49 and a signed EU declaration of conformity under Article 47) apply.

**Refs:** pred `['Article 2', 'Article 49', 'Article 47']` vs gold `['Article 2']` - over-cited `['Article 47', 'Article 49']`

**Gold answer:** No. Article 2(6) excludes AI systems and models specifically developed and put into service for the sole purpose of scientific research and development, and Article 2(8) carves out research, testing and development activity prior to placing on the market or putting into service. Once such a system is placed on the market or deployed in real-world clinical use, the Regulation applies.

**Missed keywords:** `['excluded']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['term_miss']

### `grb_06` - kw=0.50 refL=1.00 refS=0.40 len=1134 (gold 387)
**Q:** Is an AI system that infers patients' emotions for a medical purpose prohibited under Article 5 of the EU AI Act?

**Fresh answer:** No. Article 5(1)(f) prohibits emotion-inference AI only in workplaces and educational institutions, and it contains an express carve-out for systems placed on the market strictly for medical or safety reasons; an emotion-recognition system whose primary purpose at market-placement is the medical treatment or monitoring of patients (for example therapeutical use) therefore falls outside the prohibition. The carve-out is narrow: the medical purpose must be the genuine primary purpose at the point the system is placed on the market, not a justification retrofitted afterward, and Recital 18 separately excludes pure physical-state monitoring such as pain or fatigue from the definition of "emotion" altogether. Note that escaping the Article 5 prohibition does not exempt the system from other obligations: a medical-use emotion-recognition system will typically be high-risk, so where it qualifies as such its provider must register it in the EU database before market-placement (Article 49) and a deploying public authority or Annex III deployer must complete a Fundamental Rights Impact Assessment before first use (Article 27).

**Refs:** pred `['Article 5.1.f', 'Article 5', 'Article 49', 'Article 27', 'Annex III']` vs gold `['Article 5']` - over-cited `['Annex III', 'Article 27', 'Article 49']`

**Gold answer:** No. Article 5(1)(f) prohibits AI that infers emotions in the workplace and education settings, but it expressly exempts systems placed on the market or put into service for medical or safety reasons. Emotion inference for a genuine medical purpose is therefore not prohibited, though it may still be high-risk and remains subject to the applicable transparency and high-risk obligations.

**Missed keywords:** `['emotion recognition', 'prohibited', 'exception']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `grb_07` - kw=0.80 refL=1.00 refS=0.44 len=1578 (gold 402)
**Q:** A hospital deploys a high-risk AI diagnostic system. What are its obligations as a deployer under the EU AI Act?

**Fresh answer:** A hospital deploying a high-risk AI diagnostic system takes on deployer obligations under Article 26: use the system in accordance with the provider's instructions for use, assign human oversight to competent and adequately trained natural persons, monitor the system's operation, and retain the logs it automatically generates. Because medical diagnostics fall within Annex III, the hospital must also conduct a Fundamental Rights Impact Assessment before first use under Article 27, covering the deployment process, the persons affected, the specific risks, and the human-oversight measures. It is entitled to rely on the operational transparency and instructions for use that Article 13 requires the provider to supply (provider identity, intended purpose, capabilities and limitations, and expected lifetime), which underpin the hospital's ability to operate and oversee the system correctly. Finally, under Article 86 any patient subject to a decision based on the system's output that produces legal or similarly significant adverse effects on their health may obtain from the hospital a clear and meaningful explanation of the AI system's role in the decision and the main elements of that decision. These are the deployer's duties; the Article 9 to 15 design requirements, conformity assessment, EU declaration of conformity, and CE marking remain provider obligations and do not bind the hospital unless it becomes a provider under Article 25, for example by putting its own name or trademark on the system, substantially modifying it, or changing its intended purpose.

**Refs:** pred `['Article 26', 'Article 27', 'Article 13', 'Article 86', 'Article 9', 'Article 25', 'Annex III']` vs gold `['Article 26', 'Article 27']` - over-cited `['Annex III', 'Article 13', 'Article 25', 'Article 86', 'Article 9']`

**Gold answer:** Under Article 26 the deploying hospital must use the system in accordance with the instructions for use, assign human oversight to competent staff, ensure input data is relevant, monitor operation and keep the automatically generated logs. As a public body providing an essential service it must also carry out a fundamental-rights impact assessment under Article 27 before putting the system into use.

**Missed keywords:** `['monitoring']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `grb_08` - kw=0.60 refL=1.00 refS=0.35 len=2273 (gold 414)
**Q:** What must the provider of a high-risk AI medical diagnostic system put in place before placing it on the market?

**Fresh answer:** Before placing a high-risk AI medical diagnostic system on the market, the provider must have the full set of conformity measures in place, anchored by Article 16's overarching duty to ensure the system meets the Chapter III Section 2 requirements (Articles 9 to 15) and bears the provider's identifying details. Concretely, the provider must put the following in place. A documented, iterative risk-management system running across the lifecycle (Article 9), and data-governance practices ensuring training, validation, and test datasets are relevant, representative, sufficiently error-free, and complete, with bias examination and mitigation (Article 10). Technical documentation drawn up before market placement and kept up to date, demonstrating conformity and covering the Annex IV content (system description, architecture, data and training methodology, oversight, risk measures, validation and testing) (Article 11 and Annex IV). Automatic event logging capability, with logs retained for at least six months (Article 12); sufficient operational transparency with instructions for use stating provider identity, intended purpose, capabilities, limitations, and expected lifetime (Article 13); effective human-oversight measures including automation-bias safeguards and override ability (Article 14); and appropriate accuracy, robustness, and cybersecurity, with accuracy metrics declared in the instructions (Article 15). An operational quality-management system covering compliance strategy, design verification, testing, post-market monitoring, and incident reporting (Article 17), and a post-market monitoring plan documenting performance and feeding back into risk management (Article 72). To complete market access, the provider must then pass the applicable conformity assessment, using the Annex VI internal-control procedure where harmonised standards or common specifications are applied (Article 43); draw up a signed, dated, machine-readable EU declaration of conformity containing the Annex V information (Article 47); affix the CE marking visibly and indelibly, followed by the notified body's identification number where applicable (Article 48); and register both itself and the system in the EU database before placing it on the market (Article 49).

**Refs:** pred `['Article 9', 'Article 10', 'Article 11', 'Article 12', 'Article 13', 'Article 16', 'Article 14', 'Article 15', 'Article 17', 'Article 72', 'Article 43', 'Article 47', 'Article 48', 'Article 49']` vs gold `['Article 16', 'Article 9', 'Article 43']` - over-cited `['Article 10', 'Article 11', 'Article 12', 'Article 13', 'Article 14', 'Article 15', 'Article 17', 'Article 47', 'Article 48', 'Article 49', 'Article 72']`

**Gold answer:** Article 16 makes the provider responsible for the full high-risk compliance set: a risk-management system under Article 9, data governance, technical documentation, logging, transparency, human oversight and accuracy/robustness, plus a quality-management system. Before placing the device on the market the provider must pass the conformity assessment under Article 43 and draw up the EU declaration of conformity.

**Missed keywords:** `['risk management system', 'quality management']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `grb_09` - kw=0.60 refL=0.50 refS=0.40 len=867 (gold 367)
**Q:** What conformity-assessment route applies to an AI system that is a safety component of a CE-marked medical device?

**Fresh answer:** Through the medical device's own sectoral conformity assessment, not a standalone AI Act procedure. Under the Annex I route in Article 6(1), an AI system that is a safety component of a product covered by the Union harmonisation legislation listed in Annex I is high-risk where that product must undergo third-party conformity assessment under its sectoral legislation; medical devices fall within Annex I's New Legislative Framework list, so a CE-marked medical device that requires notified-body assessment pulls its AI safety component into the high-risk tier on this basis. The conformity assessment therefore runs through the medical device framework's existing third-party procedure, integrating the AI Act requirements into that single sectoral assessment rather than triggering the separate Annex III registration and self-assessment track under Article 6(2).

**Refs:** pred `['Article 6', 'Article 6.1', 'Article 6.2', 'Annex I', 'Annex III']` vs gold `['Article 43', 'Annex I']` - over-cited `['Annex III', 'Article 6']` - MISSING `['Article 43']`

**Gold answer:** Article 43(3) provides that where the high-risk AI system is a safety component of a product covered by the Annex I medical-device legislation, the AI Act conformity assessment is carried out as part of the single conformity-assessment procedure already required under that legislation, through the relevant notified body, rather than as a separate AI Act assessment.

**Missed keywords:** `['notified body', 'integrated']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'under_citation', 'term_miss', 'first_person']

### `grb_10` - kw=0.80 refL=1.00 refS=0.33 len=1216 (gold 360)
**Q:** What human-oversight measures does the EU AI Act require for a high-risk clinical decision-support system?

**Fresh answer:** For a high-risk clinical decision-support system, human oversight runs across the provider's design duties and the deployer's operational duties. Under Article 14, which requires high-risk systems to be designed with appropriate human-machine interface tools so that natural persons can effectively oversee them throughout the period of use, the system must enable a clinician to understand, monitor, and where necessary override or disregard its output. The provider must specify the corresponding human-oversight measures in the Article 13 instructions for use, which require the system to be sufficiently transparent for deployers to interpret its output and use it appropriately, together with its capabilities, limitations, and the foreseeable circumstances that may create risks to health, safety, or fundamental rights. Under Article 11 with Annex IV, the technical documentation must describe those human-oversight arrangements as part of demonstrating conformity. On the deployment side, Article 26 requires the deployer to assign oversight to competent and adequately trained natural persons, use the system in line with its instructions, monitor its operation, and retain the automatically generated logs.

**Refs:** pred `['Article 14', 'Article 13', 'Article 26', 'Article 11', 'Annex IV']` vs gold `['Article 14']` - over-cited `['Annex IV', 'Article 11', 'Article 13', 'Article 26']`

**Gold answer:** Article 14 requires high-risk systems to be designed so that natural persons can effectively oversee them: the oversight staff must be able to understand the system's output and limitations, remain aware of automation bias, correctly interpret the result, and decide not to use the system or to override, disregard or reverse its output and to stop the system.

**Missed keywords:** `['automation bias']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `grb_11` - kw=0.83 refL=1.00 refS=0.33 len=1420 (gold 362)
**Q:** What data-governance obligations apply to the training data of a high-risk AI sepsis-prediction model?

**Fresh answer:** Article 10 is the operative provision, and it applies in full: the training, validation, and testing datasets must be subject to data-governance and management practices appropriate to the system's intended purpose (Article 10(2)), covering provenance, data preparation, and an examination for possible biases that are likely to affect health and safety, harm fundamental rights, or lead to discrimination (Article 10(2)(f)). Those datasets must also be relevant, sufficiently representative, and to the best extent possible free of errors and complete in view of the intended purpose (Article 10(3)); where strictly necessary to detect and correct bias, the provider may process special categories of personal data subject to the safeguards in Article 10(5). A presumption of conformity is available under Article 42(1): a high-risk system trained and tested on data reflecting the specific geographical, behavioural, contextual, or functional setting of intended use is presumed to comply with the data-governance requirements of Article 10(4). The data and training methodology, together with the data-governance measures applied, must be recorded in the technical documentation per Annex IV and Article 11 (drawn up before placement on the market and kept up to date), and the bias and data-quality risks identified feed the documented, iterative risk-management system required across the lifecycle under Article 9.

**Refs:** pred `['Article 10', 'Article 42', 'Article 42.1', 'Article 11', 'Article 9', 'Annex IV']` vs gold `['Article 10']` - over-cited `['Annex IV', 'Article 11', 'Article 42', 'Article 9']`

**Gold answer:** Article 10 requires that training, validation and testing datasets be subject to data-governance practices and be relevant, sufficiently representative, and to the best extent possible free of errors and complete in view of the intended purpose, with examination for possible biases and appropriate handling of any sensitive data used to detect and correct them.

**Missed keywords:** `['data governance']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `grb_12` - kw=0.83 refL=0.67 refS=0.80 len=1368 (gold 351)
**Q:** What logging and record-keeping does a high-risk AI radiology system require, and how long must the deploying hospital keep the logs?

**Fresh answer:** As deployer, the hospital must retain the logs that the radiology system automatically generates, to the extent those logs are under its control (Article 26, deployer duty to keep automatically generated logs), and it must keep them for a period appropriate to the intended purpose of at minimum 6 months, unless Union or national law (here likely medical-device or health record-keeping rules) requires longer (Article 12(3) log-retention period). The logging itself is built into the system because high-risk AI must technically allow automatic recording of events over its lifetime, with traceability covering at least start/stop, input reference data, and events relevant to post-market monitoring (Article 12(1)-(2) automatic logging and traceability). Alongside log retention, the deployer must use the system in accordance with the instructions of use, assign human oversight to competent trained persons, and monitor operation, informing the provider of any serious incidents (Article 26 deployer obligations including monitoring under Article 26(5)). Note that the 6-month minimum is the floor: financial-institution deployers satisfy the retention duty through their sectoral governance rules (Article 26 carve-out), but a hospital does not fall within that carve-out, so the at-least-6-months rule and any longer national health-law retention period govern.

**Refs:** pred `['Article 12', 'Article 12.3', 'Article 12.1', 'Article 26', 'Article 26.5']` vs gold `['Article 12', 'Article 19', 'Article 26']` - MISSING `['Article 19']`

**Gold answer:** Article 12 requires the high-risk system to log events automatically over its lifetime for traceability, and Article 19 requires the provider to keep the logs it controls. Under Article 26(6) the deploying hospital must retain the automatically generated logs for at least six months, unless a longer period is set by applicable Union or national law.

**Missed keywords:** `['six months']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'under_citation', 'term_miss']

### `grb_13` - kw=0.80 refL=1.00 refS=0.80 len=1413 (gold 345)
**Q:** Does the EU AI Act require post-market monitoring and serious-incident reporting for an AI-based patient-monitoring device, and under which articles?

**Fresh answer:** Yes. For an AI-based patient-monitoring device that qualifies as a high-risk AI system, the provider must establish and document a post-market monitoring system proportionate to the technology and its risks, which actively and systematically collects, documents and analyses performance data over the system's lifetime and feeds corrective actions back into risk management (Article 72, including Articles 72(1) and 72(2)). Serious-incident reporting is also required: providers must report serious incidents to the market-surveillance authority of the Member State where the incident occurred, on tiered deadlines, immediately and no later than 2 days after awareness for widespread infringement or critical-infrastructure disruption, no later than 10 days for a death, and no later than 15 days for other serious incidents (or immediately once a causal link is established); a "serious incident" under Article 3(49) covers death, serious irreversible critical-infrastructure disruption, fundamental-rights violation, or serious property or environmental harm (Article 73). Note the medical-device carve-out: because patient-monitoring devices fall under the Medical Devices Regulation (Reg. 2017/745), the AI Act's serious-incident reporting is subject to a dual-reporting exemption to avoid duplication, except for incidents involving fundamental-rights infringements, which remain reportable under Article 73.

**Refs:** pred `['Article 72', 'Article 73', 'Article 73.1', 'Article 3.25']` vs gold `['Article 72', 'Article 73']` - over-cited `['Article 3']`

**Gold answer:** Yes. Article 72 requires the provider to set up and document a post-market monitoring system proportionate to the risks, actively collecting and reviewing the system's performance in use. Article 73 requires the provider to report any serious incident to the relevant market-surveillance authorities, within the deadlines that article specifies.

**Missed keywords:** `['market surveillance']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'term_miss']

### `grb_14` - kw=0.60 refL=0.33 refS=0.29 len=1521 (gold 523)
**Q:** A pharma company trains a large foundation model for drug discovery whose training compute exceeds 10^25 FLOPs. Which EU AI Act obligations apply?

**Fresh answer:** Yes, systemic-risk GPAI obligations apply: because cumulative training compute exceeds 10^25 FLOPs, the model is presumed to have high-impact capabilities and is classified as a general-purpose AI model with systemic risk under Article 51, which classifies a GPAI model as systemic-risk when it has high-impact capabilities (presumed at the 10^25 FLOPs threshold) or is so designated by the Commission on Annex XIII criteria. The pharma company is the provider of a general-purpose AI model within the meaning of Article 3, which defines 'general-purpose AI model', 'provider', and 'systemic risk' among its terms, and it therefore carries the full provider obligations attaching to that classification regardless of the drug-discovery purpose. Two points follow. First, if a downstream actor later fine-tunes or modifies this model, Article 25 (responsibilities along the value chain) read with the Commission's one-third compute rule makes that actor a new provider only when its additional training compute exceeds one-third of the base model's compute (or roughly 3.3×10^24 FLOPs where base compute is unknown); below that threshold the downstream actor stays a deployer or integrator and the provider obligations remain with the pharma company. Second, where this model is integrated into another provider's high-risk system, Article 25 also requires the pharma company, as upstream provider, to cooperate by supplying the information and technical access the integrator reasonably needs to meet its own obligations.

**Refs:** pred `['Article 51', 'Article 51.2', 'Article 25', 'Article 3.63', 'Annex XIII']` vs gold `['Article 51', 'Article 53', 'Article 55']` - over-cited `['Annex XIII', 'Article 25', 'Article 3']` - MISSING `['Article 53', 'Article 55']`

**Gold answer:** The model is a general-purpose AI model and, because its cumulative training compute exceeds 10^25 FLOPs, it is presumed under Article 51 to have systemic risk. The provider must meet the baseline GPAI obligations in Article 53 (technical documentation, information for downstream providers, a copyright policy and a training-content summary) and the additional systemic-risk obligations in Article 55 (model evaluation and adversarial testing, systemic-risk assessment and mitigation, incident tracking and cybersecurity).

**Missed keywords:** `['model evaluation', 'documentation']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`?` conf=`0.85` answer_route=synthesis:complex_question

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss']

### `grb_15` - kw=0.60 refL=1.00 refS=1.00 len=631 (gold 395)
**Q:** If a hospital fine-tunes an open-weight medical language model, when does it become a provider under the EU AI Act?

**Fresh answer:** Yes, when its fine-tuning amounts to a substantial modification or it puts its own name or trademark on the system. Under Article 25, a deployer or other third party becomes a provider, and assumes the full set of provider obligations, if it makes a substantial modification to a high-risk AI system or markets the system under its own name or trademark; a hospital that fine-tunes an open-weight model crosses that line at the point its changes qualify as substantial (or at the point it brands the output as its own), not merely by using or hosting it. Until then it remains a deployer, with the lighter duties that role carries.

**Refs:** pred `['Article 25']` vs gold `['Article 25']`

**Gold answer:** Under Article 25 a party that makes a substantial modification to an AI system, or puts its own name or trademark on a high-risk system, becomes the provider and takes on the provider obligations. For a general-purpose model the Commission's guidance treats a fine-tune that adds more than one third of the original training compute as making the modifier a new provider for the resulting model.

**Missed keywords:** `['new provider', 'one-third']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Issue flags:** ['term_miss']

### `grb_16` - kw=0.80 refL=1.00 refS=1.00 len=789 (gold 325)
**Q:** What transparency obligation applies to AI-generated synthetic medical images used to augment a training dataset?

**Fresh answer:** The marking obligation in Article 50(2) is the operative provision: a provider of an AI system that generates synthetic content must ensure its outputs are marked in a machine-readable format and detectable as artificially generated or manipulated, so synthetic medical images produced by such a system carry that marking. The deepfake labelling duty in Article 50(4), which requires deployers to disclose artificially generated or manipulated content, is not triggered here unless the images are published or otherwise exposed to natural persons rather than kept internal to dataset augmentation; likewise the Article 50(1) duty to inform persons that they are interacting with an AI system does not apply, as augmenting a training set involves no direct interaction with natural persons.

**Refs:** pred `['Article 50']` vs gold `['Article 50']`

**Gold answer:** Article 50(2) requires providers of AI systems that generate synthetic image, audio, video or text content to mark the outputs in a machine-readable format and make them detectable as artificially generated or manipulated. Synthetic medical images produced for data augmentation therefore have to be labelled as AI-generated.

**Missed keywords:** `['transparency']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.5` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'term_miss']

### `grb_17` - kw=0.60 refL=0.00 refS=0.00 len=1918 (gold 342)
**Q:** Classify the EU AI Act risk tier of an AI ambient scribe that only transcribes doctor-patient consultations and performs no diagnosis or decision-making.

**Fresh answer:** Not high-risk in itself: a system that only transcribes doctor-patient consultations and performs no diagnosis or decision-making does not fall within any of the eight Annex III high-risk use cases (biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration and asylum and border control, and administration of justice and democratic processes), so the Annex III route to high-risk under Article 6(2) is not engaged by the transcription function alone. It could still be high-risk through the Annex I route under Article 6(1) if it is placed on the market as, or as a safety component of, a medical device that is itself covered by the Union harmonisation legislation listed in Annex I and must undergo a third-party conformity assessment; a pure scribe with no clinical role would normally not meet that test, but the qualification under the relevant medical-device legislation is decisive. Even if the system were otherwise drawn into Annex III, the Article 6(3) derogation would likely remove it from high-risk because verbatim transcription is a narrow procedural or preparatory task that neither replaces nor influences the clinician's assessment, provided it poses no significant risk of harm and does not profile natural persons (profiling would make it high-risk regardless). Where a provider relies on this derogation, it must document that self-assessment before placing the system on the market and still register the system under Article 49(2). If the system is ultimately classified high-risk, downstream distributors must then verify that it bears the CE marking, is accompanied by the EU declaration of conformity and the instructions for use, and that the provider and importer have met their obligations, withholding it and informing the authorities where they consider it non-conforming.

**Refs:** pred `['Article 6.1', 'Article 49', 'Article 49.2', 'Annex III', 'Annex I']` vs gold `['Article 50']` - over-cited `['Annex I', 'Annex III', 'Article 49', 'Article 6']` - MISSING `['Article 50']`

**Gold answer:** A pure transcription tool with no diagnostic or decision function is not listed in Annex III and is not a medical-device safety component, so it is not high-risk. It is a limited-risk system whose operative obligation is the Article 50 transparency duty to make clear that people are interacting with, or content is produced by, an AI system.

**Missed keywords:** `['limited risk', 'transparency']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss', 'first_person']

### `grb_18` - kw=0.40 refL=0.00 refS=0.00 len=1372 (gold 319)
**Q:** Classify the EU AI Act risk tier of a consumer wellness chatbot that gives general lifestyle tips and makes no medical claims.

**Fresh answer:** Not high-risk. A consumer wellness chatbot that offers general lifestyle tips and makes no medical claims falls outside both routes to high-risk classification under Article 6: it is not a safety component of, or itself, a product covered by the Union harmonisation legislation in Annex I (machinery, toys, radio equipment, medical devices, lifts, and the Section B transport sectors), and it does not fall within any of the eight Annex III use-case categories (biometrics, critical infrastructure, education and vocational training, employment and worker management, essential private and public services, law enforcement, migration and asylum and border control, and administration of justice and democratic processes). Because no medical claim is made, the system does not engage the medical-device leg of Annex I, which would otherwise pull it into the high-risk tier. Two caveats on classification. If a downstream actor were to modify the intended purpose in a way that brought the system within a high-risk use case, or put its own name or trademark on it, Article 25(1) would make that actor a provider of a high-risk system with the corresponding obligations. And the Annex III route is the only one in play for a conversational product of this kind, so absent a change of purpose into one of those eight categories, the system remains outside the high-risk tier.

**Refs:** pred `['Article 25', 'Article 25.1', 'Article 6', 'Annex I', 'Annex III']` vs gold `['Article 50']` - over-cited `['Annex I', 'Annex III', 'Article 25', 'Article 6']` - MISSING `['Article 50']`

**Gold answer:** A general consumer-wellness chatbot that makes no medical claims is neither prohibited nor high-risk under Annex III; it falls outside the high-risk medical categories. Its only specific obligation is the Article 50 transparency duty to inform users they are interacting with an AI system; otherwise it is minimal-risk.

**Missed keywords:** `['minimal risk', 'limited risk', 'transparency']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss', 'first_person']

### `grb_19` - kw=1.00 refL=1.00 refS=0.57 len=2757 (gold 379)
**Q:** Is an AI system used for biometric patient identification at hospital check-in high-risk under the EU AI Act?

**Fresh answer:** **It depends, and the deciding fact is whether the system performs one-to-many remote biometric identification or one-to-one *biometric verification***, under Article 6(2) read with Annex III(1), only the former is high-risk. The operative route here is Article 6(2): an AI system is high-risk if it falls within one of the Annex III use-case categories. Biometrics is the first of those categories. However, the Annex III biometrics heading captures remote biometric identification systems, i.e. systems that identify a person by matching their biometric data against many entries in a reference database (one-to-many). It expressly does not extend to systems whose sole purpose is to confirm that a person is who they claim to be (biometric verification, one-to-one authentication). Applying that distinction to hospital check-in. If the system captures a patient's biometric and searches it against a population/patient database to determine who the person is (one-to-many identification), it falls within Annex III(1) and is high-risk under Article 6(2). If the patient first asserts an identity (card, booking reference, name) and the system merely confirms that the live biometric matches that single stored record (one-to-one verification), it is outside the Annex III biometrics category and is therefore not high-risk on this route. Two boundary points to keep distinct. This use is not prohibited under Article 5. The Article 5 bans on biometric practices are exhaustive (e.g. untargeted scraping of facial images to build recognition databases, and the narrowly-drawn restrictions on certain real-time identification in publicly accessible spaces for law-enforcement purposes). Consensual patient identification at a hospital desk is not among the eight listed prohibitions, so it sits in the high-risk-or-below tiers, not the prohibited tier. A separate high-risk route exists under Article 6(1): if the biometric component is a safety component of a product covered by the Annex I Union harmonisation legislation (for example, a medical device under the MDR/IVDR), it would be high-risk on that basis independently of Annex III. On the facts given (administrative check-in), that route is unlikely to apply, but it should be confirmed against the product's regulatory status. Regardless of the high-risk determination, where the system interacts directly with patients the Article 50 transparency duty applies: persons must be informed that they are interacting with an AI system. To resolve the classification definitively, establish one fact: does the system match against many records to find an identity (one-to-many → high-risk under Article 6(2)/Annex III), or verify a single asserted identity (one-to-one → not high-risk on that route)?

**Refs:** pred `['Article 6', 'Article 6.2', 'Article 6.1', 'Article 50', 'Annex III', 'Annex III.1', 'Annex I', 'Article 5']` vs gold `['Article 6', 'Annex III']` - over-cited `['Annex I', 'Article 5', 'Article 50']`

**Gold answer:** It depends on the mode. Annex III point 1(a) makes remote biometric identification systems high-risk, but it expressly excludes biometric verification whose sole purpose is to confirm a person is who they claim to be. One-to-one check-in verification is therefore outside the high-risk category, while one-to-many identification of patients would be high-risk under Article 6(2).

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'first_person']

### `grb_20` - kw=0.33 refL=0.75 refS=0.32 len=2524 (gold 438)
**Q:** An AI tool recommends oncology treatment regimens from clinical guidelines. What EU AI Act obligations does its provider face across the lifecycle?

**Fresh answer:** Likely high-risk, so the provider carries the full Chapter III lifecycle burden. An AI tool recommending oncology regimens falls to be classified under Article 6, which treats a system as high-risk either where it is a safety component of a product already subject to third-party conformity assessment under Annex I sectoral law (the route relevant to medical software) or where it falls within one of the eight Annex III use cases; the narrow Article 6(3) derogation for purely procedural, preparatory, or human-confirming tasks will rarely rescue a tool that influences clinical assessment. Once high-risk, the provider must, across the lifecycle. Operate a documented, iterative risk-management system (Article 9) that identifies and analyses foreseeable risks to health, safety and fundamental rights (9(2)(a)), evaluates risks under intended use and reasonably foreseeable misuse (9(2)(b)), tests to select targeted measures and ensure consistent performance (9(5)), and judges and communicates residual risks to the deployer (9(6)). Govern its data (Article 10) so training, validation and test datasets are relevant, representative, error-free and complete, with provenance, bias examination and mitigation, and proper handling of special-category data. Achieve and maintain appropriate accuracy, robustness and cybersecurity (Article 15), declaring accuracy metrics in the instructions for use (15(2)), building resilience against errors and faults including fail-safe mechanisms (15(4)), and protecting against unauthorised alteration and attacks through access controls, encryption and access logging (15(3), 15(5)). Provide operational transparency to deployers (Article 13) via instructions covering provider identity, intended purpose, capabilities, limitations, human-oversight measures and required maintenance. Meet the overarching provider duties in Article 16: run a quality-management system (Article 17), keep technical documentation and the system's automatically generated logs for at least six months (Article 19), undergo conformity assessment (Article 43), draw up the EU declaration of conformity (Article 47), affix the CE marking (Article 48), register the system in the EU database (Article 49), take corrective action on non-conformity (Article 20), and demonstrate compliance to authorities on request (Article 21). Where the Annex III route applies, the provider must document any Article 6(3) self-assessment before placing the system on the market and still register it under Article 49(2).

**Refs:** pred `['Article 15', 'Article 9', 'Article 16', 'Article 6', 'Article 6.3', 'Article 10', 'Article 13', 'Article 17', 'Article 19', 'Article 43', 'Article 47', 'Article 48', 'Article 49', 'Article 49.2', 'Article 20', 'Article 21', 'Annex I']` vs gold `['Article 6', 'Article 9', 'Article 43', 'Annex III']` - over-cited `['Annex I', 'Article 10', 'Article 13', 'Article 15', 'Article 16', 'Article 17', 'Article 19', 'Article 20', 'Article 21', 'Article 47', 'Article 48', 'Article 49']` - MISSING `['Annex III']`

**Gold answer:** A treatment-recommendation system is high-risk, either as a medical-device safety component under Article 6(1) and Annex I or under the Annex III healthcare categories. Across the lifecycle the provider must run a risk-management system under Article 9 with data governance, technical documentation, logging, transparency and human oversight, pass the Article 43 conformity assessment, and operate post-market monitoring after deployment.

**Missed keywords:** `['risk management', 'post-market monitoring', 'human oversight', 'data governance']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Issue flags:** ['verbose', 'over_citation', 'under_citation', 'term_miss', 'first_person']

### `grb_21` - kw=1.00 refL=1.00 refS=0.67 len=1176 (gold 394)
**Q:** How does the EU AI Act interact with the Medical Device Regulation for AI medical-device software — which conformity route and timeline applies?

**Fresh answer:** A single integrated conformity assessment applies, run through the Medical Device Regulation notified body rather than as a separate AI Act procedure. AI software that is itself a medical device, or a safety component of one, is high-risk under the Annex I route of Article 6(1), because medical devices are listed in the Union harmonisation legislation in Annex I (Section A, New Legislative Framework) and must already undergo third-party conformity assessment under the MDR. Article 43(3) therefore folds the AI Act assessment into that sectoral third-party procedure, so the MDR notified body assesses conformity against both regimes in one procedure rather than the internal-control (Annex VI) or separate notified-body (Annex VII) routes that govern Annex III systems. Any substantial modification to the system requires a fresh conformity assessment under Article 43(4). On timeline, the references here establish only the route, not the transitional dates, so I cannot cite a specific applicability deadline from this material; the operative point is that compliance is demonstrated through the existing MDR notified-body pathway rather than a standalone AI Act track.

**Refs:** pred `['Article 6', 'Article 6.1', 'Article 43', 'Article 43.3', 'Article 43.4', 'Annex I', 'Annex VI', 'Annex VII', 'Annex III']` vs gold `['Article 6', 'Article 43', 'Annex I']` - over-cited `['Annex III', 'Annex VI', 'Annex VII']`

**Gold answer:** AI software that is a medical device or its safety component is high-risk under Article 6(1) because the Medical Device Regulation sits in Annex I. Under Article 43(3) the AI Act requirements are assessed through the single, integrated MDR notified-body conformity procedure rather than a separate AI Act assessment, and the high-risk obligations apply on the timeline set for Annex I products.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'first_person']

### `grb_22` - kw=0.67 refL=1.00 refS=0.40 len=1713 (gold 367)
**Q:** What does the EU AI Act require for an AI system used for risk assessment and pricing in health insurance?

**Fresh answer:** Likely high-risk. Annex III lists essential private and public services among its eight high-risk use-case categories, and AI used to assess risk and set pricing in health insurance falls within that category, so it is captured by the Annex III route to high-risk classification under Article 6(2). The narrow Article 6(3) derogation (no significant risk of harm where the system performs only a procedural, preparatory, or pattern-detection task that does not replace human assessment) does not rescue this system: that carve-out never applies where the AI profiles natural persons, and risk-scoring and pricing of individual policyholders is precisely such profiling, so the system is always high-risk; the provider would still have to register it under Article 49(2). Before the system is placed on the market or put into service it must undergo a conformity assessment under Article 43: the internal-control procedure (Annex VI) where the relevant harmonised standards or common specifications have been applied, otherwise the notified-body procedure (Annex VII), which audits the quality-management system and technical documentation. Conformity with harmonised standards whose references are published in the Official Journal gives a presumption of conformity with the corresponding Chapter III requirements (Article 40). By way of derogation from Article 43, a market-surveillance authority may authorise placing a specific high-risk system on the market for a limited period for exceptional reasons such as the protection of life and health of persons while the conformity assessment is being completed (Article 46), but this is an exceptional route, not the ordinary path for an insurance pricing system.

**Refs:** pred `['Article 46', 'Article 40', 'Article 6', 'Article 6.2', 'Article 6.3', 'Article 49', 'Article 49.2', 'Article 43', 'Annex III', 'Annex VI', 'Annex VII']` vs gold `['Article 6', 'Annex III']` - over-cited `['Annex VI', 'Annex VII', 'Article 40', 'Article 43', 'Article 46', 'Article 49']`

**Gold answer:** Annex III point 5(c) classifies AI used for risk assessment and pricing in relation to natural persons in the case of life and health insurance as high-risk under Article 6(2). The provider and deployer must therefore meet the Chapter III high-risk obligations, including data governance, human oversight and, for the deployer, a fundamental-rights impact assessment.

**Missed keywords:** `['risk assessment', 'essential services']`

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.85` answer_route=synthesis:synthesis_default

**Issue flags:** ['verbose', 'over_citation', 'term_miss']

### `grb_23` - kw=0.33 refL=1.00 refS=0.57 len=2442 (gold 414)
**Q:** A clinical-trial sponsor uses AI to select and recruit eligible patients. Is this automatically high-risk under the EU AI Act?

**Fresh answer:** Not automatically high-risk, patient selection and recruitment for a clinical trial does not fall within any Annex III use case merely because it involves "recruitment," and its classification turns on Article 6. The deciding point is that the Annex III "employment + worker management" category (the recruitment-related use case) concerns the recruitment and selection of workers, applicants and employees in an employment relationship. Recruiting trial subjects is not employment recruitment, so the superficial "recruitment" label does not by itself bring the system within Annex III. The query profile's "recruitment & employment" tag is therefore not dispositive here. Classification instead proceeds under Article 6, on its two routes. Annex I safety-component route (Article 6(1)): the system is high-risk if it is used as a safety component of, or is itself, a product covered by the Union harmonisation legislation listed in Annex I (for instance, a medical device under the MDR or IVDR). Whether patient-selection software meets that condition is a fact-specific question about its regulatory status and intended purpose under that legislation. Annex III use-case route (Article 6(2)): the system is high-risk only if it falls within one of the eight enumerated use cases. Selecting and recruiting eligible patients does not, on its face, map onto any of them (it is not employment/worker recruitment, biometrics, education, etc.). For completeness, the system is not prohibited: it does not match any of the eight exhaustively listed practices in Article 5 (e.g. subliminal/manipulative or deceptive techniques causing significant harm, or exploitation of vulnerabilities by age, disability or socio-economic situation), these are a distinct and higher tier from the high-risk classification under Article 6 and should not be conflated with it. If neither Article 6 route is satisfied, the system is limited- or minimal-risk, subject mainly to the Article 50 transparency duties where it interacts directly with natural persons (disclosure of its AI nature) or generates synthetic content (machine-readable marking). Bottom line: it depends, high-risk only if the system qualifies as, or is a safety component of, an Annex I product requiring the relevant conformity assessment (Article 6(1)), or otherwise falls within an Annex III use case (Article 6(2)); the mere fact that it "recruits" does not engage the employment use case.

**Refs:** pred `['Article 6', 'Article 6.1', 'Article 6.2', 'Article 50', 'Annex III', 'Annex I', 'Article 5']` vs gold `['Article 6', 'Annex III']` - over-cited `['Annex I', 'Article 5', 'Article 50']`

**Gold answer:** Not automatically. Annex III point 5 covers AI that decides eligibility for essential healthcare services and benefits or that performs emergency triage, not research recruitment as such, so trial-participant selection is not high-risk merely by being clinical AI. It would become high-risk only if it determines access to healthcare services, and pure research use may fall under the Article 2 research carve-out.

**Missed keywords:** `['eligibility', 'healthcare services', 'research', 'scope']`

**Reasoning log:** path=`logic_rag` stage2_polish=`True` model=`claude-opus-4-8 complex=True` conf=`0.85` answer_route=synthesis:complex_question

**Issue flags:** ['verbose', 'over_citation', 'term_miss', 'first_person']

### `grb_24` - kw=1.00 refL=1.00 refS=0.67 len=715 (gold 379)
**Q:** What penalties can be imposed on a medical-AI provider that places a non-conformant high-risk system on the market?

**Fresh answer:** A medical-AI provider that places a non-conformant high-risk system on the market faces administrative fines under Article 99(4), which sets a ceiling of up to EUR 15 000 000 or, for an undertaking, up to 3 % of total worldwide annual turnover, whichever is higher, for breaching the provider obligations attaching to high-risk systems. This is the regime's middle tier: only the Article 5 prohibited-practice breaches carry the higher Article 99(3) ceiling of EUR 35 000 000 or 7 % of worldwide turnover. Under Article 99(6), where the provider is an SME or start-up each fine is capped at the lower of the fixed amount or the turnover percentage, and all penalties must be effective, proportionate and dissuasive.

**Refs:** pred `['Article 99', 'Article 5']` vs gold `['Article 99']` - over-cited `['Article 5']`

**Gold answer:** Article 99 sets the penalty ceilings. Non-compliance with the high-risk obligations is subject under Article 99(4) to fines of up to EUR 15 000 000 or 3 % of total worldwide annual turnover, whichever is higher, while breaching the Article 5 prohibitions carries the higher ceiling of EUR 35 000 000 or 7 % under Article 99(3). Fines must take the interests of SMEs into account.

**Reasoning log:** path=`kb_fallback` stage2_polish=`True` model=`claude-opus-4-8 complex=False` conf=`0.7` answer_route=synthesis:synthesis_default

**Issue flags:** - clean
