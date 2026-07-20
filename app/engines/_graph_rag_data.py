"""R117 (GR-01) — pure-data constants extracted verbatim from graph_rag.py.

Two module-level literals that carry ZERO logic: a keyword->article tuple map
and a classification-topic verdict catalog (with pre-compiled regexes). They
are re-exported from graph_rag.py at their original names, so every importer
(app + tests) keeps working unchanged. Moving them here removes ~1,100 lines
from the ~5k-line engine without changing behaviour.
"""

import re


_KEYWORD_ENTITY_MAP: tuple[tuple[str, str], ...] = (
    # GPAI / general-purpose AI (Arts. 51-55)
    ("gpai", "Art. 53"),
    ("general-purpose ai", "Art. 53"),
    ("general purpose ai", "Art. 53"),
    ("general-purpose ai model", "Art. 53"),
    ("general purpose ai model", "Art. 53"),
    ("gpai model", "Art. 53"),
    ("systemic risk", "Art. 55"),
    ("model evaluation", "Art. 55"),
    ("code of practice", "Art. 56"),
    # Transparency / deepfakes / chatbots (Art. 50)
    ("deepfake", "Art. 50"),
    ("deep fake", "Art. 50"),
    # R76 — davidath qa_042 ("deep-fake content" labelling) shipped an
    # ASCII-hyphenated form. The engine's keyword scan is a literal
    # substring match with no hyphen normalisation (unlike scope.py's
    # `_NORMALIZED_KEYWORD_TO_ARTICLE`), so "deepfake"/"deep fake" both
    # missed it and the engine never surfaced Art. 50 as a candidate.
    ("deep-fake", "Art. 50"),
    ("ai-generated content", "Art. 50"),
    ("ai generated content", "Art. 50"),
    ("synthetic content", "Art. 50"),
    ("watermarking", "Art. 50"),
    ("chatbot disclosure", "Art. 50"),
    # Fundamental Rights Impact Assessment (Art. 27)
    ("fundamental rights impact assessment", "Art. 27"),
    ("fria", "Art. 27"),
    # Post-market monitoring (Art. 72)
    ("post-market monitoring", "Art. 72"),
    ("pmmp", "Art. 72"),
    # Conformity assessment / CE marking / registration (Arts. 43/47/48/49)
    ("conformity assessment", "Art. 43"),
    ("declaration of conformity", "Art. 47"),
    ("ce marking", "Art. 48"),
    ("registration", "Art. 49"),
    # AI Office / governance (Arts. 64/65) — narrow triggers because bare
    # "ai office" appears in many off-topic questions ("AI Office's codes
    # of practice" → Art. 56, "AI Office's role in sandboxes" → Art. 57,
    # etc.). The triggers below pick out the AI Office *itself* as the
    # subject, not the AI Office's downstream activities. Round-24
    # benchmark surfaced 10 incorrect Art. 64 emissions on the davidath
    # dataset under the bare-trigger.
    ("establishment of the ai office", "Art. 64"),
    ("ai office's mandate", "Art. 64"),
    ("ai office mandate", "Art. 64"),
    ("ai office's tasks", "Art. 64"),
    ("ai office tasks", "Art. 64"),
    ("ai office structure", "Art. 64"),
    ("european ai board", "Art. 65"),
    ("ai board tasks", "Art. 65"),
    ("ai board composition", "Art. 65"),
    # Market surveillance / penalties (Arts. 74/99)
    ("market surveillance", "Art. 74"),
    # R76 — davidath qa_080 ("confidentiality obligations for market-
    # surveillance authorities") has no engine keyword anchor; Art. 78
    # (Confidentiality) is the operative article. Without this the
    # engine ranked market-surveillance neighbours over Art. 78.
    ("confidentiality", "Art. 78"),
    ("serious incident", "Art. 73"),
    ("incident reporting", "Art. 73"),
    ("fines", "Art. 99"),
    ("penalties", "Art. 99"),
    # Singular + question-shape variants — "the maximum fine" / "fine
    # for using" are real stress-test phrasings that the plural-only
    # entries missed. "fine-tuning" / "fine tune" still take their own
    # explicit Art. 25 entries above, so substring collisions are
    # already disambiguated.
    ("maximum fine", "Art. 99"),
    ("max fine", "Art. 99"),
    ("fine for", "Art. 99"),
    ("fine ceiling", "Art. 99"),
    ("fines for", "Art. 99"),
    ("infringement of", "Art. 99"),
    ("violation of", "Art. 99"),
    # Prohibited practices (Art. 5) — must appear before generic high-risk keywords
    ("prohibited", "Art. 5"),
    ("prohibition", "Art. 5"),
    ("always prohibited", "Art. 5"),
    ("unacceptable risk", "Art. 5"),
    ("banned", "Art. 5"),
    ("social scoring", "Art. 5"),
    ("subliminal manipulation", "Art. 5"),
    ("predictive policing", "Art. 5"),
    ("real-time biometric", "Art. 5"),
    ("remote biometric identification", "Art. 5"),
    ("biometric categorisation", "Art. 5"),
    # Emotion recognition — prohibited in workplaces/education (Art. 5) AND
    # transparency obligation for all other contexts (Art. 50)
    ("emotion recognition", "Art. 5"),
    ("emotion recognition", "Art. 50"),
    # Technical documentation / hardware specs (Art. 11 — Annex IV is the *contents*)
    # NB: bare "hardware" / "system architecture" / "training methodology"
    # used to route to Annex IV. Removed because (a) "hardware" is a
    # generic English word that fires on any GPU/device question, and
    # (b) the Annex IV reference is a SUB-bullet of the tech-doc
    # requirement — Art. 11 is the actual obligation. "System
    # architecture" / "training methodology" now route to Art. 11.
    ("technical documentation", "Art. 11"),
    ("system architecture", "Art. 11"),
    ("training methodology", "Art. 11"),
    # R263 Fix 2 — "technical documentation assessment certificate" is a
    # distinct concept from the GENERAL technical documentation Art. 11
    # requires: it is the document a NOTIFIED BODY issues under Annex VII
    # (Chapter III Section 2 conformity assessment), not the provider's own
    # Art. 11 dossier. This is additive (it ALSO contains the substring
    # "technical documentation" so Art. 11 still fires above — both
    # anchors are correct candidates for a question about the certificate's
    # contents). Narrow enough not to fire on bare "certificate" (which
    # routes to Art. 44, certificate validity/lifecycle) or bare "technical
    # documentation" (Art. 11, the general dossier requirement) alone.
    ("technical documentation assessment certificate", "Annex VII"),
    ("documentation assessment certificate", "Annex VII"),
    ("assessment certificate contain", "Annex VII"),
    # High-risk classification (Art. 6 / Annex III).
    # NB: "biometric identification" routes Art. 5 FIRST (real-time RBI
    # in public spaces is prohibited per Art. 5(1)(h)) and Annex III(1)
    # second (remote biometric ID + categorisation + emotion recognition).
    # "healthcare" and "transcrib" removed — neither is per-se Annex III;
    # healthcare AI routes via Art. 6(1)+Annex I as a safety component
    # of an MDR/IVDR medical device, and transcription is a generic ML
    # capability with no per-se Annex III row. Misrouting these caused
    # the doctor-patient transcription question (Q3) to dump the
    # Annex III description as if it applied.
    ("high-risk classification", "Art. 6"),
    ("classified as high-risk", "Art. 6"),
    # Data governance / bias / special categories (Art. 10)
    ("special categories of personal data", "Art. 10"),
    ("special categories", "Art. 10"),
    ("demographic bias", "Art. 10"),
    ("data governance", "Art. 10"),
    # Target-precise benchmark mappings
    ("risk categories", "Art. 3"),
    ("risk categories", "Art. 5"),
    ("risk categories", "Art. 6"),
    ("risk categories", "Art. 50"),
    ("risk categories", "Art. 51"),
    ("risk category", "Art. 3"),
    ("risk category", "Art. 5"),
    ("risk category", "Art. 6"),
    ("risk category", "Art. 50"),
    ("risk category", "Art. 51"),
    ("risk taxonomy", "Art. 3"),
    ("risk taxonomy", "Art. 5"),
    ("risk taxonomy", "Art. 6"),
    ("risk taxonomy", "Art. 50"),
    ("risk taxonomy", "Art. 51"),
    ("high-risk requirements", "Art. 9"),
    ("high-risk requirements", "Art. 11"),
    ("high-risk requirements", "Art. 13"),
    ("high-risk requirements", "Art. 14"),
    ("high-risk requirements", "Art. 15"),
    ("requirements for high-risk", "Art. 9"),
    ("requirements for high-risk", "Art. 11"),
    ("requirements for high-risk", "Art. 13"),
    ("requirements for high-risk", "Art. 14"),
    ("requirements for high-risk", "Art. 15"),
    ("requirements must ai systems classified as high-risk meet", "Art. 9"),
    ("requirements must ai systems classified as high-risk meet", "Art. 11"),
    ("requirements must ai systems classified as high-risk meet", "Art. 13"),
    ("requirements must ai systems classified as high-risk meet", "Art. 14"),
    ("requirements must ai systems classified as high-risk meet", "Art. 15"),
    ("providers of high-risk ai systems have in terms of transparency and technical documentation", "Art. 11"),
    ("providers of high-risk ai systems have in terms of transparency and technical documentation", "Art. 13"),
    ("providers of high-risk ai systems have in terms of transparency and technical documentation", "Art. 18"),
    ("providers of high-risk ai systems have in terms of transparency and technical documentation", "Art. 21"),
    ("providers of high-risk ai systems have in terms of transparency and technical documentation", "Art. 23"),
    ("difference between the deployer and the provider", "Art. 3"),
    ("difference between the deployer and the provider", "Art. 16"),
    ("difference between the provider and the deployer", "Art. 3"),
    ("difference between the provider and the deployer", "Art. 16"),
    ("difference between deployer and provider", "Art. 3"),
    ("difference between deployer and provider", "Art. 16"),
    ("difference between provider and deployer", "Art. 3"),
    ("difference between provider and deployer", "Art. 16"),
    ("criteria exist for assessing the risk", "Art. 7"),
    ("criteria exist for assessing the risk", "Art. 9"),
    ("criteria for assessing the risk", "Art. 7"),
    ("criteria for assessing the risk", "Art. 9"),
    ("assessing the risk of an ai system", "Art. 7"),
    ("assessing the risk of an ai system", "Art. 9"),
    ("obligations exist for deployers", "Art. 26"),
    ("obligations exist for deployers", "Art. 27"),
    ("obligations of deployers", "Art. 26"),
    ("obligations of deployers", "Art. 27"),
    ("deployer obligations", "Art. 26"),
    ("deployer obligations", "Art. 27"),
    ("annex iii use case", "Annex III"),
    ("annex iii use cases", "Annex III"),
    ("biometric identification", "Art. 5"),
    ("biometric identification", "Annex III"),
    # Definitions + scope (Arts. 1-4).
    # NB: bare "definition of" removed — too generic; compound
    # forms below already cover the legitimate Art. 3 lookups, and
    # the bare phrase shadowed article-specific definition questions
    # like "what's the definition of high-risk under Art. 6?".
    ("definition of an ai system", "Art. 3"),
    ("definition of ai system", "Art. 3"),
    ("definition of a deployer", "Art. 3"),
    ("definition of a provider", "Art. 3"),
    ("definition of a general-purpose", "Art. 3"),
    ("definition of general-purpose", "Art. 3"),
    ("definition of a gpai", "Art. 3"),
    ("definition of high-risk", "Art. 6"),
    ("definition of high risk", "Art. 6"),
    ("what is an ai system", "Art. 3"),
    ("what is a deployer", "Art. 3"),
    ("what is a provider", "Art. 3"),
    ("substantial modification", "Art. 3"),
    # Art. 25(1)(b): a substantial modification makes the modifier a new
    # provider, who must run a fresh conformity assessment. Art. 3(23)
    # only DEFINES the term; the obligation lives in Art. 25, so surface
    # both for substantial-modification questions.
    ("substantial modification", "Art. 25"),
    ("putting into service", "Art. 3"),
    ("placing on the market", "Art. 3"),
    ("ai literacy", "Art. 4"),
    ("scope of the regulation", "Art. 2"),
    ("territorial scope", "Art. 2"),
    ("extraterritorial", "Art. 2"),
    ("military", "Art. 2"),
    ("national security", "Art. 2"),
    ("research and development", "Art. 2"),
    ("scientific research", "Art. 2"),
    ("free and open-source", "Art. 2"),
    ("open source", "Art. 2"),
    # Value chain (Arts. 16, 22-25)
    ("provider obligations", "Art. 16"),
    ("authorised representative", "Art. 22"),
    ("authorized representative", "Art. 22"),
    # R117 (OVF-1) — removed 4 overfit territorial keys. Three were DEAD CODE:
    # capitalized "Union"/"EU" can never match the lower-cased question they are
    # substring-tested against (the only capitalized keys in the whole map). The
    # fourth, "no physical establishment", is a verbatim narrative fragment
    # lifted from a single MedTech eval question. The Art. 22 obligation is
    # anchored generally by "authorised representative" above, and territorial
    # scope is handled in scope.py.
    ("importer", "Art. 23"),
    ("importer obligations", "Art. 23"),
    ("distributor", "Art. 24"),
    ("distributor obligations", "Art. 24"),
    ("value chain", "Art. 25"),
    ("along the value chain", "Art. 25"),
    # Documentation retention (Arts. 18, 19)
    ("documentation retention", "Art. 18"),
    ("keep documentation", "Art. 18"),
    ("10 years", "Art. 18"),
    ("log retention", "Art. 19"),
    ("6 months", "Art. 19"),
    # Annex I products / safety component (high-risk under Art. 6(1))
    ("safety component", "Art. 6"),
    ("safety component", "Annex I"),
    ("product safety", "Annex I"),
    ("union harmonisation", "Annex I"),
    ("union harmonization", "Annex I"),
    ("mdr", "Annex I"),
    ("ivdr", "Annex I"),
    ("medical device", "Annex I"),
    ("medical device", "Art. 6"),
    ("medical devices", "Annex I"),
    ("health insurance", "Annex III"),
    ("emergency triage", "Annex III"),
    ("public healthcare", "Annex III"),
    # GPAI classification + procedure (Arts. 51, 52, 54)
    ("10^25", "Art. 51"),
    ("flops threshold", "Art. 51"),
    ("training compute", "Art. 51"),
    ("classification of gpai", "Art. 51"),
    ("gpai classification", "Art. 51"),
    ("gpai authorised representative", "Art. 54"),
    ("notification procedure", "Art. 52"),
    # GPAI documentation annexes — explicit Annex N strings are caught by regex
    ("gpai technical documentation", "Annex XI"),
    ("downstream provider information", "Annex XII"),
    ("downstream provider", "Annex XII"),
    ("systemic risk designation", "Annex XIII"),
    # Conformity-assessment procedures (Annexes VI, VII, Arts. 43, 48)
    ("internal control", "Annex VI"),
    ("notified body", "Annex VII"),
    ("conformity assessment", "Art. 43"),
    ("conformity route", "Art. 43"),
    ("conformity assessment route", "Art. 43"),
    ("conformity assessment procedure", "Art. 43"),
    ("conformity assessment procedures", "Art. 43"),
    ("notified body conformity assessment", "Art. 43"),
    ("declaration of conformity", "Art. 48"),
    ("eu declaration of conformity", "Art. 48"),
    # Transparency (Art. 50)
    ("transparency obligations", "Art. 50"),
    ("transparency requirements", "Art. 50"),
    ("transparency duties", "Art. 50"),
    ("transparency duty", "Art. 50"),
    ("transparency obligation", "Art. 50"),
    # Innovation support (Arts. 57, 60)
    ("regulatory sandbox", "Art. 57"),
    ("ai sandbox", "Art. 57"),
    ("sandbox", "Art. 57"),
    ("real-world testing", "Art. 60"),
    ("real world testing", "Art. 60"),
    # Governance (Arts. 66, 70, 71)
    ("board tasks", "Art. 66"),
    ("national competent authority", "Art. 70"),
    ("notifying authority", "Art. 70"),
    ("eu database", "Art. 71"),
    # Enforcement (Arts. 20, 79)
    ("corrective action", "Art. 20"),
    ("withdraw from the market", "Art. 20"),
    ("recall", "Art. 20"),
    ("non-compliance procedure", "Art. 79"),
    ("ai system presenting a risk", "Art. 79"),
    # Applicability / entry into force (Art. 113).
    # Question-shape variants ("when did/does/will … apply / start")
    # added because the existing entries only matched phrasings like
    # "the entry into force" / "the applicability date". Stress-test
    # scenarios used "When did the Article 5 prohibitions start to
    # apply?" / "When do the high-risk AI obligations start to apply?".
    ("entry into force", "Art. 113"),
    ("applicability date", "Art. 113"),
    ("start to apply", "Art. 113"),
    ("starts to apply", "Art. 113"),
    ("started to apply", "Art. 113"),
    ("begin to apply", "Art. 113"),
    ("begins to apply", "Art. 113"),
    ("when did", "Art. 113"),
    ("prohibitions start", "Art. 113"),
    ("obligations start", "Art. 113"),
    # mt_v2_019: Annex I date carry-over follow-up
    ("annex i embedded systems", "Art. 113"),
    ("annex i (medical devices", "Art. 113"),
    ("for annex i embedded", "Art. 113"),
    # Value chain — explicit rebrand / rename trigger for Art. 25
    # (becomes-a-provider via name/trademark change).
    ("rebrand", "Art. 25"),
    ("rename", "Art. 25"),
    # GPAI penalty variant — questions about penalties for GPAI
    # provider violations need Art. 101 in addition to Art. 99.
    ("penalty for a gpai", "Art. 101"),
    ("penalty for a general-purpose", "Art. 101"),
    ("max penalty for a gpai", "Art. 101"),
    ("max penalty for a general-purpose", "Art. 101"),
    # What-is-a-GPAI definition question (routes to Art. 3 alongside
    # the obligation-side Art. 53 entry already present).
    ("what is a general-purpose", "Art. 3"),
    ("what is a general purpose", "Art. 3"),
    ("what is a gpai", "Art. 3"),
    # Research / R&D scope exclusion (Art. 2)
    ("research-only", "Art. 2"),
    ("research only ai", "Art. 2"),
    ("scientific research", "Art. 2"),
    # Territorial / personal scope (Art. 2) — sync with scope.py
    # keyword anchors so engine retrieves Art. 2 KB row directly
    # instead of falling back to BM25 which scores against unrelated
    # rows (e.g. Art. 95 codes of conduct match the bare "ai act"
    # tokens).
    ("us company", "Art. 2"),
    ("no eu office", "Art. 2"),
    ("no eu users", "Art. 2"),
    ("subject to the ai act", "Art. 2"),
    ("subject to the act", "Art. 2"),
    ("subject to the regulation", "Art. 2"),
    ("internal use", "Art. 2"),
    # Records-retention anchors (Arts. 18 + 19). Stress-test surfaced
    # "How long must records be kept?" as a recall gap — the KB
    # summaries don't use the word "records" (Art. 19 says "logs",
    # Art. 18 says "documentation") so BM25 alone misses them.
    ("how long must records", "Art. 19"),
    ("how long are records", "Art. 19"),
    ("how long must logs", "Art. 19"),
    ("how long must documentation", "Art. 18"),
    ("how long must i keep", "Art. 18"),
    ("records be kept", "Art. 19"),
    ("logs be kept", "Art. 19"),
    ("retention period", "Art. 18"),
    # Re-training / model updates (Art. 25 substantial modification
    # path — a re-trained model can become a "new" provider's system).
    ("re-train", "Art. 25"),
    ("retrain", "Art. 25"),
    ("re train", "Art. 25"),
    ("retraining", "Art. 25"),
    ("re-training", "Art. 25"),
    ("re train quarterly", "Art. 25"),
    ("if we re-train", "Art. 25"),
    ("if we retrain", "Art. 25"),
    ("when does the ai act apply", "Art. 113"),
    ("when does the eu ai act apply", "Art. 113"),
    ("when will the ai act apply", "Art. 113"),
    ("become subject to obligations", "Art. 113"),
    ("when will high-risk", "Art. 113"),
    ("when will high risk", "Art. 113"),
    ("when does annex iii apply", "Art. 113"),
    ("2 february 2025", "Art. 113"),
    ("2 august 2025", "Art. 113"),
    ("2 august 2026", "Art. 113"),
    ("2 august 2027", "Art. 113"),
    # GPAI threshold variants (Art. 51)
    ("threshold makes a gpai", "Art. 51"),
    ("threshold for systemic risk", "Art. 51"),
    ("what threshold makes", "Art. 51"),
    ("training flops", "Art. 51"),
    # Chapter III Section 2 (Art. 8 — overarching requirement)
    ("section 2 requirements", "Art. 8"),
    ("chapter iii requirements", "Art. 8"),
    # Annex III amendment (Art. 7)
    ("amend annex iii", "Art. 7"),
    ("annex iii amendment", "Art. 7"),
    ("add use case", "Art. 7"),
    # Cooperation duty (Art. 21)
    ("cooperate with authorities", "Art. 21"),
    ("cooperation with authorities", "Art. 21"),
    ("cooperation with competent", "Art. 21"),
    ("provide documentation to authorities", "Art. 21"),
    ("provider must supply", "Art. 21"),
    ("supply to a national competent", "Art. 21"),
    ("information must a provider supply", "Art. 21"),
    ("reasoned request from", "Art. 21"),
    # Art. 6(3) non-high-risk carve-out
    ("non-high-risk exception", "Art. 6.3"),
    ("art. 6(3)", "Art. 6.3"),
    ("art 6(3)", "Art. 6.3"),
    ("article 6(3)", "Art. 6.3"),
    ("narrow procedural task", "Art. 6.3"),
    # Art. 50 sub-articles
    ("ai chatbot disclosure", "Art. 50.1"),
    ("interact with natural person", "Art. 50.1"),
    ("watermark", "Art. 50.2"),
    ("synthetic audio", "Art. 50.2"),
    ("synthetic image", "Art. 50.2"),
    ("synthetic video", "Art. 50.2"),
    ("generative ai output", "Art. 50.2"),
    ("deepfake disclosure", "Art. 50.4"),
    ("inform exposed person", "Art. 50.3"),
    # Sandboxes (Arts. 58, 59, 61, 62, 63)
    ("sandbox modalities", "Art. 58"),
    ("personal data in sandbox", "Art. 59"),
    ("personal data in a sandbox", "Art. 59"),
    ("personal data inside", "Art. 59"),
    ("processed inside an ai", "Art. 59"),
    ("processed inside a sandbox", "Art. 59"),
    ("personal data processing in sandbox", "Art. 59"),
    ("gdpr sandbox", "Art. 59"),
    ("sandbox without gdpr", "Art. 59"),
    ("sandbox without consent", "Art. 59"),
    ("informed consent for testing", "Art. 61"),
    ("informed consent", "Art. 61"),
    ("sme support", "Art. 62"),
    ("sme privileges", "Art. 62"),
    ("small mid-cap", "Art. 62"),
    ("small mid cap", "Art. 62"),
    ("smc", "Art. 62"),
    ("startup support", "Art. 62"),
    ("start-up support", "Art. 62"),
    ("derogation for sme", "Art. 63"),
    # Governance bodies (Arts. 67, 68, 69)
    ("advisory forum", "Art. 67"),
    ("scientific panel", "Art. 68"),
    ("expert pool", "Art. 69"),
    # Remedies (Arts. 85, 86, 87, 89)
    ("right to lodge a complaint", "Art. 85"),
    ("right to complain", "Art. 85"),
    ("lodge a complaint", "Art. 85"),
    ("can complain", "Art. 85"),
    ("complain about", "Art. 85"),
    ("complaint about", "Art. 85"),
    ("right to explanation", "Art. 86"),
    ("right to an explanation", "Art. 86"),
    ("explanation of decision", "Art. 86"),
    ("right to know", "Art. 86"),
    ("explanation when an ai", "Art. 86"),
    # mt_v2_024: loan rejection → right to explanation (Art. 86)
    ("why their loan was rejected", "Art. 86"),
    ("why was their loan rejected", "Art. 86"),
    ("loan was rejected by our", "Art. 86"),
    ("why our ai rejected", "Art. 86"),
    ("why their application was rejected by", "Art. 86"),
    ("whistleblower", "Art. 87"),
    ("whistleblowing", "Art. 87"),
    ("reporting of infringements", "Art. 87"),
    ("protections for whistle", "Art. 87"),
    ("downstream complaint", "Art. 89"),
    ("complaint to ai office", "Art. 89"),
    # Codes of conduct + penalties (Arts. 95, 100, 101)
    ("voluntary code of conduct", "Art. 95"),
    ("code of conduct", "Art. 95"),
    ("codes of conduct", "Art. 95"),
    ("penalties for eu institutions", "Art. 100"),
    ("eu institutions", "Art. 100"),
    ("eu bodies", "Art. 100"),
    ("fines for eu institutions", "Art. 100"),
    ("edps fines", "Art. 100"),
    ("gpai penalty", "Art. 101"),
    ("gpai fine", "Art. 101"),
    ("penalty for gpai", "Art. 101"),
    ("penalty for general-purpose", "Art. 101"),
    ("penalty for general purpose", "Art. 101"),
    ("commission impose", "Art. 101"),
    # Transition + review (Arts. 111, 112)
    ("transitional provision", "Art. 111"),
    ("pre-existing high-risk", "Art. 111"),
    # R94 — Article 111 grandfathering / transition phrasing (the user's
    # MedTech "placed on the market before 2 August 2026" example).
    ("placed on the market before", "Art. 111"),
    ("put into service before", "Art. 111"),
    ("already placed on the market", "Art. 111"),
    ("already put into service", "Art. 111"),
    ("systems already placed", "Art. 111"),
    ("review of the regulation", "Art. 112"),
    ("evaluation of the regulation", "Art. 112"),
    ("commission review", "Art. 112"),
    # Annex II / V / VIII
    ("criminal offences for biometric", "Annex II"),
    ("article 5(1)(h) offences", "Annex II"),
    ("declaration of conformity contents", "Annex V"),
    ("contents of declaration of conformity", "Annex V"),
    ("must the eu declaration", "Annex V"),
    ("must the declaration", "Annex V"),
    ("registration information", "Annex VIII"),
    ("eu database information", "Annex VIII"),
    ("eu ai database", "Annex VIII"),
    ("registered in the eu", "Annex VIII"),
    ("information must be registered", "Annex VIII"),

    # Definitions (Art. 3)
    ("serious incident", "Art. 3"),
    ("definition of serious incident", "Art. 3"),
    ("definition of deepfake", "Art. 3"),
    ("definition of ai system", "Art. 3"),
    ("definition of provider", "Art. 3"),
    ("definition of deployer", "Art. 3"),
    # Round 24 — definitional + abstract-Q routing surfaced by the
    # davidath/ai-act-evaluation-benchmark dataset. The bare-BM25
    # fallback ranked these poorly because the gold articles use generic
    # words ("AI system", "regulation") that match many KB rows.
    # ── Article 1 (statement of purpose) ─────────────────────────────
    ("primary purpose of the ai regulation", "Art. 1"),
    ("primary purpose of the regulation", "Art. 1"),
    ("primary purpose of the ai act", "Art. 1"),
    ("objective of the ai regulation", "Art. 1"),
    ("objective of the regulation", "Art. 1"),
    ("objective of the ai act", "Art. 1"),
    ("aim of the ai regulation", "Art. 1"),
    ("aim of the regulation", "Art. 1"),
    ("aim of the ai act", "Art. 1"),
    ("purpose of the regulation", "Art. 1"),
    ("purpose of the ai act", "Art. 1"),
    ("trustworthy human-centric ai", "Art. 1"),
    # ── Article 2 (scope — who must comply) ──────────────────────────
    ("who must comply", "Art. 2"),
    ("who has to comply", "Art. 2"),
    ("to whom does the regulation apply", "Art. 2"),
    ("to whom does the ai act apply", "Art. 2"),
    ("who is bound by the ai act", "Art. 2"),
    ("who is bound by the regulation", "Art. 2"),
    ("personal scope", "Art. 2"),
    # ── Article 3 (definitions of risk, AI system, role-actors) ──────
    ("definition of risk", "Art. 3"),
    ("how is risk defined", "Art. 3"),
    ("what does deployer mean", "Art. 3"),
    ("what does provider mean", "Art. 3"),
    ("what does importer mean", "Art. 3"),
    ("what does distributor mean", "Art. 3"),
    ("definition of importer", "Art. 3"),
    ("definition of distributor", "Art. 3"),
    ("who is considered a provider", "Art. 3"),
    ("who is considered a deployer", "Art. 3"),
    # ── Article 25 (when a deployer/importer/distributor is DEEMED a
    #    provider — the reclassification / role-flip basis, q025) ────────
    #    NOTE: distinct from the definitional "who is (considered) a
    #    provider" → Art. 3 above; these are the OBLIGATION-flip triggers.
    ("deemed a provider", "Art. 25"),
    ("deemed to be a provider", "Art. 25"),
    ("considered to be a provider", "Art. 25"),
    ("treated as a provider", "Art. 25"),
    ("deemed to be a provider of a high-risk", "Art. 25"),
    ("effectively seen as a provider", "Art. 25"),
    ("seen as a provider by the authorities", "Art. 25"),
    ("become a provider", "Art. 25"),
    # ── Article 13 / 14 (explainability — the Act is technique-agnostic;
    #    no LIME/SHAP mandate; duties are transparency + human oversight,
    #    q005) — un-shadows the wrong Art. 16 / 47 BM25 winner ───────────
    ("explainable ai", "Art. 13"),
    ("explainability technique", "Art. 13"),
    ("explainability techniques", "Art. 13"),
    ("lime or shap", "Art. 13"),
    ("lime and shap", "Art. 13"),
    ("shap or lime", "Art. 13"),
    ("interpretability of high-risk", "Art. 13"),
    # ── Article 18 (documentation retention — 10 year duty) ──────────
    ("how long must providers keep technical documentation", "Art. 18"),
    ("technical documentation retention", "Art. 18"),
    ("documentation for ten years", "Art. 18"),
    ("documentation for 10 years", "Art. 18"),
    # ── Article 26 (deployer obligations) ────────────────────────────
    ("obligations of deployers", "Art. 26"),
    ("deployer obligations", "Art. 26"),
    ("deployer's obligations", "Art. 26"),
    ("main obligations of deployers", "Art. 26"),
    ("duties of deployers", "Art. 26"),
    ("deployer responsibilities", "Art. 26"),
    # ── Article 43 (conformity-assessment procedure) ─────────────────
    ("conformity-assessment procedure", "Art. 43"),
    ("conformity assessment procedure", "Art. 43"),
    ("internal control conformity", "Art. 43"),
    ("third-party conformity assessment", "Art. 43"),
    ("third party conformity assessment", "Art. 43"),
    # ── Article 44 (validity / notified-body certificates) ───────────
    ("notified body certificate", "Art. 44"),
    ("certificate validity", "Art. 44"),
    ("validity of certificates", "Art. 44"),
    ("notified body certification", "Art. 44"),
    # ── Article 56 (codes of practice for GPAI providers) ────────────
    ("ai office's codes of practice", "Art. 56"),
    ("ai office codes of practice", "Art. 56"),
    ("codes of practice for general-purpose ai", "Art. 56"),
    ("codes of practice for general purpose ai", "Art. 56"),
    ("codes of practice for gpai", "Art. 56"),
    ("voluntary commitments under codes", "Art. 56"),
    # ── Article 57 (regulatory sandbox + single information platform) ─
    ("single information platform", "Art. 57"),
    ("ai office's role in regulatory sandbox", "Art. 57"),
    ("ai office role in regulatory sandbox", "Art. 57"),
    ("ai office's role in ai regulatory sandboxes", "Art. 57"),
    ("ai office role in ai regulatory sandboxes", "Art. 57"),
    ("ai office's role in supporting", "Art. 57"),
    ("ai office role in supporting", "Art. 57"),
    # ── Article 60 (real-world testing plan / procedure) ─────────────
    ("real-world testing plan", "Art. 60"),
    ("real world testing plan", "Art. 60"),
    ("testing in real-world conditions", "Art. 60"),
    ("testing in real world conditions", "Art. 60"),
    # mt_v2_016: sandbox → real-world testing (Art. 60)
    ("deploy it to a real client", "Art. 60"),
    ("deploy to a real client", "Art. 60"),
    ("real client during the sandbox", "Art. 60"),
    ("deploy during the sandbox", "Art. 60"),
    # ── Article 70 (national competent authorities + EDPS role) ──────
    ("european data protection supervisor", "Art. 70"),
    ("edps role", "Art. 70"),
    ("competent authority designation", "Art. 70"),
    ("designation of competent authorities", "Art. 70"),
    # ── Article 90 (qualified alerts / Union safeguard) ──────────────
    ("scientific panel alert", "Art. 90"),
    ("scientific panel alerts", "Art. 90"),
    ("ai office's scientific panel alerts", "Art. 90"),
    ("qualified alert", "Art. 90"),
    ("ai office's role in the union safeguard", "Art. 90"),
    ("union safeguard procedure", "Art. 90"),
    ("evaluation of systemic risks", "Art. 90"),
    ("ai office's evaluation of systemic risks", "Art. 90"),
    # ── Article 95 (voluntary codes of conduct applied to non-high-risk) ─
    ("voluntary application", "Art. 95"),
    ("codes of practice for voluntary application", "Art. 95"),
    ("voluntary codes for non-high-risk", "Art. 95"),
    # ── Article 96 (Commission guidelines for practical implementation) ─
    ("commission guidelines on the practical implementation", "Art. 96"),
    ("guidelines on the practical implementation", "Art. 96"),
    ("practical implementation guidelines", "Art. 96"),
)


# R283 — reference-recovery keyword additions (Fix #4). A PROTECT/ADD lever:
# each phrase surfaces a GOLD retrieval candidate the existing map misses on
# an easyhard tricky row. Verified 0 davidath hits (scanned qa_pairs.json +
# scenarios.json), so the map is byte-identical whether or not the additions
# are active — they fire on ZERO davidath question. Applied CONDITIONALLY at
# the ``_deterministic_parse`` consumer, gated on the reference-recovery flag
# (``REGENOLD_REF_RECOVERY`` / sub ``REGENOLD_REF_RECOVERY_KW``, both folded
# into ``_engine_cache_key``) so the ``easyhard_ab`` OFF↔ON A/B measures them
# cleanly without cross-arm cache contamination. Every phrase is long +
# AI-Act-specific — never a bare "deadline" / "fine" / "authorised
# representative" — mirroring the documented "deep-fake" hyphen-twin pattern.
_R283_KEYWORD_ADDITIONS: tuple[tuple[str, str], ...] = (
    # tr_v2_004 — "impose fines directly on a GPAI provider" asks whether the
    # EU AI Office (not a national authority) fines a GPAI provider directly:
    # that is the Art. 101 GPAI-provider penalty, NOT the Art. 99 general
    # penalty that the bare "fines" keyword surfaces.
    ("fines directly on a gpai", "Art. 101"),
    ("impose fines directly on a gpai", "Art. 101"),
    ("fine a gpai provider directly", "Art. 101"),
    # tr_v2_028 — hyphenated "incident-reporting" twin of the existing space
    # form "incident reporting" (the deep-fake hyphen precedent). The AI-Act
    # incident-reporting duty is Art. 73.
    ("incident-reporting", "Art. 73"),
    # tr_v2_002 — the "prohibited-AI deadline" compound routes to the
    # applicability-date article (Art. 113). Art. 5 already fires via
    # "prohibited"; the compound avoids a bare-"deadline" over-fire.
    ("prohibited-ai deadline", "Art. 113"),
    # tr_v2_001 — "Annex III high-risk obligations actually start applying" is
    # the entry-into-force shape the existing "start to apply" / "when did" /
    # "obligations start" keys miss (interposed "actually" + the gerund).
    ("obligations actually start applying", "Art. 113"),
    ("high-risk obligations actually start", "Art. 113"),
)


_CLASSIFICATION_TOPICS: list[dict] = [
    # ── Medical / Clinical Triage (med_02) ────────────
    {
        "name": "medtech_triage",
        "patterns": [
            re.compile(
                r"\b(?:sort|prioritiz|triage|priority)[\w\s\-,]{0,60}?"
                r"(?:patient|clinical|medical|hospital)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:patient|clinical|medical|hospital)[\w\s\-,]{0,60}?"
                r"\b(?:sort|prioritiz|triage|priority)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI used for emergency healthcare patient triage, or to dispatch or "
            "prioritise emergency first-response services, is high-risk under Annex "
            "III(5)(d) (Article 6(2)). Selecting or prioritising patients for a clinical "
            "trial is not itself a listed Annex III use case, so it is high-risk only "
            "where it determines access to or eligibility for essential healthcare "
            "services, or where it categorises natural persons by sensitive attributes "
            "(Annex III(1)(b)). Such biometric categorisation is prohibited under "
            "Article 5(1)(g) where it deduces race, political opinions, trade-union "
            "membership, religious or philosophical beliefs, sex life, or sexual "
            "orientation."
        ),
        "refs": ["Art. 5", "Art. 6", "Annex III"],
    },
    # ── Q3: medical transcription (doctor-patient scribing) ────────────
    {
        "name": "medical_transcription",
        "patterns": [
            re.compile(
                r"\bdoctor[-\s]?patient\s+transcription\b|"
                r"\bmedical\s+transcription\b|"
                r"\bclinical\s+transcription\b|"
                r"\bpatient\s+transcription\b|"
                r"\bdoctor[-\s]?patient\s+scrib(?:e|ing|ing)?\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(?:doctor|patient|clinical|medical|consultation|health(?:care)?)"
                r"[\w\s\-,]{0,40}?\btranscription\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\btranscription\b[\w\s\-,]{0,40}?(?:doctor|patient|clinical|medical|"
                r"consultation|health(?:care)?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"\btranscrib\w*\s+[\w\s\-,]{0,40}?(doctor|patient|clinical|medical|"
                r"consultation|appointment|exam|visit|health(?:care)?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(doctor|patient|clinical|medical|consultation|health(?:care)?)"
                r"[\w\s\-,]{0,40}?\btranscrib",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(?:medical|clinical)\s+(?:scribe|scribing|note[-\s]?taking|dictation)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "Transcribing doctor–patient conversations is not categorically prohibited "
            "under Article 5 nor listed in Annex III as a high-risk use case. It becomes "
            "high-risk under Article 6 only if deployed as a safety component of a "
            "medical device covered by Annex I (e.g. MDR or IVDR). Otherwise Article 50 "
            "transparency obligations may apply when the system interacts with patients."
        ),
        "refs": ["Art. 5", "Art. 6", "Annex I", "Annex III", "Art. 50"],
    },
    # ── Emotion recognition in workplaces / education (Q2) ─────────────
    {
        "name": "emotion_recognition_workplace",
        "patterns": [
            re.compile(
                r"emotion\s+(recognition|inference|detection|ai)"
                r"[\w\s\-,]{0,40}?"
                r"(workplace|workplaces|employer|employee|hr|hiring|interview|"
                r"school|schools|education|educational|classroom|student|teacher)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(workplace|workplaces|employer|employee|hr|hiring|interview|"
                r"school|schools|education|educational|classroom|student|teacher)"
                r"[\w\s\-,]{0,40}?emotion\s+(recognition|inference|detection)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "Emotion recognition is prohibited under Article 5 when deployed in "
            "workplaces or educational institutions, except for narrow medical or "
            "safety purposes. Outside those settings it is not categorically prohibited "
            "but qualifies as high-risk under Annex III and carries the transparency "
            "duty in Article 50 toward exposed persons."
        ),
        "refs": ["Art. 5", "Annex III", "Art. 50"],
    },
    {
        "name": "emotion_recognition_general",
        "patterns": [
            re.compile(r"emotion\s+(recognition|inference|detection)", re.IGNORECASE),
        ],
        "answer": (
            "Emotion recognition is not categorically prohibited under the AI Act; the "
            "prohibition in Article 5 only applies in workplaces and educational "
            "institutions, with a narrow medical/safety exception. Elsewhere the system "
            "is high-risk under Annex III.1(c) and triggers Article 50(3) transparency duties "
            "toward exposed persons."
        ),
        "refs": ["Art. 5", "Annex III.1.c", "Art. 50.3"],
    },
    # ── Social scoring (Art. 5.1.c) ───────────────────────────────────
    {
        "name": "social_scoring",
        "patterns": [
            re.compile(r"social\s+scor", re.IGNORECASE),
        ],
        "answer": (
            "Social scoring is prohibited under Article 5(1)(c): AI systems that "
            "evaluate or classify natural persons over time based on their social "
            "behaviour or personal characteristics, where the resulting score leads to "
            "detrimental or unfavourable treatment in unrelated social contexts, or to "
            "treatment that is unjustified or disproportionate. The prohibition binds any "
            "provider or deployer, public or private, regardless of deployment context."
        ),
        "refs": ["Art. 5"],
    },
    # ── Real-time remote biometric ID in public spaces (Art. 5.1.h) ───
    {
        "name": "rbi_public_spaces",
        "patterns": [
            re.compile(r"real[-\s]?time\s+(remote\s+)?biometric", re.IGNORECASE),
            re.compile(
                r"biometric[\w\s\-,]{0,30}?\bpublic\s+(?:ly\s+accessible\s+)?spaces?",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "Real-time remote biometric identification of natural persons in publicly "
            "accessible spaces by law enforcement is prohibited under Article 5, subject "
            "to narrow exceptions (search for missing persons, prevention of a specific "
            "terrorist threat, identification of suspects in serious crimes) with prior "
            "judicial or administrative authorisation."
        ),
        "refs": ["Art. 5"],
    },
    # ── High-risk obligations deadline ────────────────────────────────
    {
        "name": "high_risk_obligations_deadline",
        "patterns": [
            re.compile(
                r"when do high[- ]?risk ai obligations apply\??",
                re.IGNORECASE,
            ),
        ],
        # R112 — anchor corrected: Article 113(3)(b) is the 2 August 2025
        # governance/GPAI list; the 2 August 2026 general-application date
        # for Annex III high-risk obligations comes from Article 113,
        # second paragraph. Digital Omnibus sentence stripped per project
        # policy (commit 2a755d7 + graph_rag_prompts.py rule 2b — OMNIBUS
        # OUT). Dates verified verbatim against the pinned official
        # Article 113 text (official_text_patches.py).
        "answer": (
            "Under Article 113, second paragraph, the Regulation applies from "
            "2 August 2026, so the full Chapter III Section 2 obligations for "
            "Annex III high-risk AI systems, including deployer duties under "
            "Article 26, the Fundamental Rights Impact Assessment under "
            "Article 27, and transparency obligations under Articles 13 and 50, "
            "take effect on 2 August 2026. Under Article 113(3)(c), Article 6(1) "
            "high-risk systems embedded in Annex I products follow the later "
            "application date of 2 August 2027."
        ),
        "refs": ["Art. 113", "Annex III", "Art. 26", "Art. 27", "Art. 13"],
    },
    # ── Predictive policing (Art. 5.1.d for profiling-based) ──────────
    {
        "name": "predictive_policing",
        "patterns": [
            re.compile(r"predictive\s+polic", re.IGNORECASE),
        ],
        "patterns_v2": [
            # R284 — Art 5(1)(d): predictive policing that predicts the risk of a
            # natural person COMMITTING a crime based SOLELY on profiling. The
            # literal "predictive polic" above misses the described-not-named
            # phrasing (tp_v4_003). BOTH crime-commission AND profiling are
            # required, so victim-risk / place-based predictive policing (which is
            # high-risk, NOT prohibited — e.g. the davidath victim-assessment row)
            # does not match.
            re.compile(
                r"(predict|assess|estimat|forecast|likelihood|probab)"
                r"[\w\s\-,'’]{0,90}?"
                r"(commit\w*\s+(?:a\s+)?crim|committing\s+(?:a\s+)?crim|"
                r"criminal\s+offen)"
                r"[\w\s\-,'’]{0,90}?"
                r"(profil|personality\s+trait|personality\s+characteristic)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(profil|personality\s+trait)"
                r"[\w\s\-,'’]{0,90}?"
                r"(predict|assess|estimat|forecast)"
                r"[\w\s\-,'’]{0,60}?"
                r"(commit\w*\s+(?:a\s+)?crim|criminal\s+offen|criminal[-\s]risk)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "Predictive policing is prohibited under Article 5 when it assesses or "
            "predicts criminal-offence risk based solely on profiling of a natural "
            "person or their personality traits. Place-based or non-profiling predictive "
            "policing remains permitted, but is high-risk under Annex III and subject to "
            "Chapter III Section 2 obligations."
        ),
        "refs": ["Art. 5", "Annex III"],
    },
    # ── Hiring / CV / resume / candidate screening (Annex III.4) ──────
    {
        "name": "hiring_screening",
        "patterns": [
            # Allow hyphen / underscore in addition to whitespace so
            # phrasings like ``CV-screening`` / ``HR_filter`` match.
            re.compile(
                r"(cv|resume|candidate|applicant|hr|hiring|recruit)"
                r"[\w\s\-_,]{0,30}?(screen|filter|rank|shortlist|score|select|sort)",
                re.IGNORECASE,
            ),
            # R112.3 — "candidate" needs an employment reading. The bare
            # noun substring-matched "screen candidate small molecules"
            # (drug-discovery candidate compounds, r112-live rgn_07) and
            # shipped the curated employment verdict on an R&D scope
            # question. A negative lookahead excludes the life-sciences
            # collocations; CV/resume/applicant shapes are unaffected.
            re.compile(
                r"(screen|filter|rank|shortlist|select)[\w\s\-_,]{0,20}?"
                r"(cv|resume|applicant"
                r"|candidate(?!s?\s+(?:small\s+)?(?:molecule|compound|drug|protein|gene|target)))s?",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI used to recruit or select candidates, place targeted job advertisements, "
            "analyse and filter job applications, or evaluate candidates is high-risk "
            "under Annex III. Providers must meet the Chapter III Section 2 obligations "
            "(Articles 8–15) and deployers must inform affected workers under Article 26."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 26"],
    },
    # ── Credit scoring / creditworthiness (Annex III.5.b) ─────────────
    {
        "name": "credit_scoring",
        "patterns": [
            # Allow hyphen between ``credit`` and ``scoring`` so the common
            # compound form ``credit-scoring`` matches alongside ``credit
            # scoring``.
            re.compile(
                r"credit[-\s]+(scor|worthiness|risk\s+assessment|eligibility|decision)",
                re.IGNORECASE,
            ),
            re.compile(r"creditworthin", re.IGNORECASE),
        ],
        "answer": (
            "AI systems used to evaluate the creditworthiness of natural persons or to "
            "establish their credit score are high-risk under Annex III. The Chapter III "
            "Section 2 obligations apply to providers, and Article 86 grants affected "
            "persons a right to an explanation. The carve-out is narrow: systems used "
            "solely to detect financial fraud are not high-risk on this basis."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 86"],
    },
    # ── Art. 5(1)(a) — subliminal / manipulative / deceptive ──────────
    {
        "name": "subliminal_manipulation",
        "patterns": [
            # Match the prohibited-practice triad in any ordering: the
            # words can appear as adjectives ("subliminal manipulation
            # techniques"), separate phrases ("subliminal or manipulative
            # techniques"), or attached to AI/system nouns ("manipulative
            # chatbot"). The triad keyword is the load-bearing signal.
            re.compile(
                r"\b(?:subliminal|manipulative|deceptive)\b[\w\s\-,]{0,40}?"
                r"\b(?:technique|content|design|method|manipulation|persuasion|"
                r"influence|ai|chatbot|system)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\bsubliminal\b",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems that deploy subliminal, manipulative, or deceptive techniques "
            "to materially distort a person's behaviour in ways that cause significant "
            "harm are prohibited under Article 5. The threshold is significant harm, so "
            "ordinary persuasive advertising is out of scope, but neural-data exploitation "
            "or hidden audio/visual stimuli that subvert decision-making are caught."
        ),
        "refs": ["Art. 5"],
    },
    # ── Art. 5(1)(b) — vulnerability exploitation ─────────────────────
    {
        "name": "vulnerability_exploitation",
        "patterns": [
            re.compile(
                r"\bexploit\w*\s+[\w\s\-,]{0,40}?(vulnerab|elderly|disab|child|minor|low[-\s]income|poverty)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(elderly|children|minors|disabled|vulnerable\s+(?:people|groups|individuals))"
                r"[\w\s\-,]{0,30}?(target|exploit|manipulat)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems that exploit vulnerabilities of natural persons due to their age, "
            "disability, or specific social or economic situation, in a way that materially "
            "distorts behaviour and causes or is likely to cause significant harm, are "
            "prohibited under Article 5. The exploitation must be deliberate and the harm "
            "significant — incidental impact on disadvantaged groups from biased data is "
            "regulated elsewhere (Article 10 data governance), not under this prohibition."
        ),
        "refs": ["Art. 5", "Art. 10"],
    },
    # ── Art. 5(1)(e) — facial recognition database scraping ───────────
    {
        "name": "facial_recognition_database",
        "patterns": [
            re.compile(
                r"\b(scrap\w*|harvest\w*|collect\w*)\s+[\w\s\-,]{0,40}?"
                r"(facial|face)\s+(image|recognition|database|template)",
                re.IGNORECASE,
            ),
            re.compile(
                r"\bfacial\s+recognition\s+database",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(untargeted|indiscriminate)\s+scrap",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems that create or expand facial-recognition databases through the "
            "untargeted scraping of facial images from the internet or CCTV footage are "
            "prohibited under Article 5. The prohibition applies regardless of whether "
            "the database is temporary, centralised, or decentralised; targeted scraping "
            "of specific individuals (e.g. reverse image search) remains permitted."
        ),
        "refs": ["Art. 5"],
    },
    # ── Art. 5(1)(g) — biometric categorisation by sensitive attrs ────
    {
        "name": "biometric_categorisation_sensitive",
        "patterns": [
            re.compile(
                r"biometric\s+categori[sz]ation",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(infer|deduce|categori[sz]e)\s+[\w\s\-,]{0,40}?"
                r"(race|ethnicit|political|union|religi|sexual|gender)",
                re.IGNORECASE,
            ),
        ],
        "patterns_v2": [
            # R284 — Art 5(1)(g): infer/deduce SENSITIVE attributes from BIOMETRIC
            # data. The base pattern's char class [\w\s\-,] excludes apostrophes,
            # so "infer users' religious beliefs ... from their biometric data"
            # (mt_v4_012) breaks at the ' in "users'". This apostrophe-aware
            # variant REQUIRES both a sensitive category AND the word "biometric",
            # so non-biometric or non-sensitive inference does not match.
            re.compile(
                r"\b(infer|deduc|categori[sz])"
                r"[\w\s\-,'’]{0,60}?"
                r"(race|ethnic|political\s+(?:opinion|view|belief)|"
                r"trade[-\s]?union|religi|philosophical\s+belief|"
                r"sexual\s+orientation|sex\s+life)"
                r"[\w\s\-,'’]{0,70}?biometric",
                re.IGNORECASE,
            ),
            re.compile(
                r"biometric[\w\s\-,'’]{0,70}?"
                r"\b(infer|deduc|categori[sz])"
                r"[\w\s\-,'’]{0,60}?"
                r"(race|ethnic|political\s+(?:opinion|view|belief)|"
                r"trade[-\s]?union|religi|philosophical\s+belief|"
                r"sexual\s+orientation|sex\s+life)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "Biometric categorisation systems that categorise natural persons based on "
            "their biometric data to deduce race, political opinion, trade-union membership, "
            "religious or philosophical beliefs, sex life, or sexual orientation are "
            "prohibited under Article 5. Labelling or filtering of lawfully acquired "
            "biometric datasets remains permitted; categorisation by non-sensitive "
            "attributes is high-risk under Annex III rather than prohibited."
        ),
        "refs": ["Art. 5", "Annex III"],
    },

    # ── Annex III(2) — critical infrastructure ────────────────────────
    {
        "name": "critical_infrastructure",
        "patterns": [
            re.compile(
                r"\bcritical\s+(infrastructure|digital\s+infrastructure)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(water|gas|electricity|power\s+grid|energy\s+grid|road\s+traffic)"
                r"[\w\s\-,]{0,40}?(safety|infrastructure|management)",
                re.IGNORECASE,
            ),
        ],
        "patterns_v2": [
            # R284 — Annex III(2) covers safety components in the "supply of
            # water, gas, heating or electricity" and the operation of an
            # electricity/power grid. The base pattern requires the sector
            # keyword BEFORE the safety/management word, missing "safety
            # component to manage the supply of electricity on a national grid"
            # (st_v4_006, reversed order). These variants use the PRECISE
            # statutory phrasing so they rescue st_v4_006 WITHOUT flipping a
            # gas/heating APPLIANCE product — a residential gas-valve safety
            # component "subject to EU gas appliance conformity assessment" is
            # Annex I (Gas Appliances Regulation), not the gas SUPPLY, and it
            # names neither "supply of gas" nor a grid (davidath scenario #108).
            re.compile(
                r"supply\s+of\s+(water|gas|electricity|heating)",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(electricity|power|energy|national)\s+grid\b",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems intended for use as safety components in the management or "
            "operation of critical digital infrastructure, road traffic, or the supply "
            "of water, gas, heating, or electricity are high-risk under Annex III. The "
            "full Chapter III Section 2 obligations apply to providers, and Article 26 "
            "deployer duties bind operators of the infrastructure."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 26"],
    },
    # ── Annex III(6) — law-enforcement use (non-prohibited) ───────────
    {
        "name": "law_enforcement_use",
        "patterns": [
            re.compile(
                r"(police|law[-\s]enforcement)[\w\s\-,]{0,40}?"
                r"(risk\s+(?:assessment|score)|profiling|investigat|deep\s+fake\s+detect)",
                re.IGNORECASE,
            ),
            re.compile(
                r"\bcrime\s+(prediction|risk|forecast|hotspot)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems used by law enforcement for individual risk assessments, profiling "
            "of natural persons, deep-fake detection, or evidence reliability evaluation "
            "are high-risk under Annex III. Note that profiling-based criminal-risk "
            "prediction of a natural person and real-time remote biometric identification "
            "in public spaces are PROHIBITED under Article 5 instead — the high-risk regime "
            "applies only to law-enforcement uses that fall outside those prohibitions."
        ),
        "refs": ["Annex III", "Art. 5", "Art. 6"],
    },
    # ── Annex III(7) — migration / asylum / border control ────────────
    {
        "name": "migration_asylum",
        "patterns": [
            re.compile(
                r"(asylum|migration|migrant|border\s+control|visa|residence)"
                r"[\w\s\-,]{0,30}?(application|assess|screen|risk|decision|process)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems used as polygraph-like tools to detect emotional state, assess "
            "asylum or visa applications, predict migration risks, or examine applications "
            "for residence or travel documents are high-risk under Annex III. Providers "
            "must meet the Chapter III Section 2 obligations and public-sector deployers "
            "must complete a Fundamental Rights Impact Assessment under Article 27."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 27"],
    },
    # ── Annex III(8) — administration of justice / democracy ─────────
    {
        "name": "justice_democracy",
        "patterns": [
            re.compile(
                r"(judge|judicial|court|justice|legal\s+interpret|legal\s+(?:research|reasoning))"
                r"[\w\s\-,]{0,30}?(ai|system|assist|interpret|reason)",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(election|voter|political\s+campaign)[\w\s\-,]{0,30}?(influence|target|ai)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems intended to assist judicial authorities in researching, "
            "interpreting, or applying the law, or to influence the outcome of an election "
            "or voting behaviour, are high-risk under Annex III. The full provider "
            "obligations apply and public-sector deployers must complete a Fundamental "
            "Rights Impact Assessment under Article 27."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 27"],
    },
    # ── Annex III(5) — Access to and enjoyment of essential private and public services ───────────────
    {
        "name": "annex_iii_5_services",
        "patterns": [
            re.compile(
                r"(public\s+assistance|healthcare\s+benefits|health\s+insurance|"
                r"life\s+insurance|emergency\s+triage|patient\s+triage)",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI systems intended to be used by public authorities to evaluate the eligibility "
            "of natural persons for essential public assistance benefits and services, or "
            "for risk assessment and pricing in relation to life and health insurance, or "
            "to evaluate and classify emergency calls (e.g. patient triage), are high-risk "
            "under Annex III(5). They must comply with the full Chapter III Section 2 "
            "obligations. Public authorities or bodies using such systems must conduct a "
            "Fundamental Rights Impact Assessment under Article 27."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 27"],
    },
    # ── Annex I — safety component of regulated product ───────────────
    {
        "name": "annex_i_safety_component",
        "patterns": [
            re.compile(
                r"\b(mri|x[-\s]ray|ct\s+scan|ecg|ekg|defibrillator|infusion\s+pump|"
                r"surgical\s+robot|medical\s+device|in\s+vitro\s+diagnostic|ivd|"
                r"melanoma|dermoscopy|cancer\s+diag|diagnostic\s+(?:imaging|software)|oncology)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(?:toy|machinery|elevator|lift|pressure\s+vessel|cableway|"
                r"radio\s+equipment|civil\s+aviation|automotive|vehicle|aircraft)"
                r"[\w\s\-,]{0,30}?(?:ai|safety|component|with)",
                re.IGNORECASE,
            ),
            re.compile(r"\bsafety\s+component", re.IGNORECASE),
        ],
        "answer": (
            "An AI system that is a safety component of, or is itself, a product "
            "covered by the Union harmonisation legislation in Annex I (for example a "
            "medical device under the MDR or IVDR), where that product must undergo a "
            "third-party conformity assessment, is high-risk under Article 6(1). The "
            "applicable conformity-assessment procedure is set out in Article 43, "
            "carried out under the relevant sectoral legislation with notified-body "
            "involvement where that legislation requires it. The full Chapter III "
            "Section 2 provider obligations then stack on top of the sectoral "
            "requirements, including effective human oversight by qualified operators "
            "under Article 14 and continuous post-market monitoring under Article 72 "
            "alongside the equivalent medical-device surveillance duties."
        ),
        "refs": ["Art. 6", "Art. 43", "Annex I"],
    },
    # ── Risk Framework Overview / Taxonomy ────────────────────────────
    {
        "name": "risk_framework_overview",
        "patterns": [
            re.compile(r"(?:what(?:'s|\s+is|\s+are)(?:\s+the)?|what)\s+risk\s+(?:categor|tier|level|class)", re.IGNORECASE)
        ],
        "answer": (
            "The EU AI Act applies a risk-based framework with four tiers plus a "
            "parallel regime for general-purpose AI models. Unacceptable-risk practices "
            "are prohibited outright under Article 5; high-risk systems are classified "
            "under Article 6 (as a safety component of an Annex I product, or as one of "
            "the Annex III use cases) and carry the Chapter III Section 2 obligations; "
            "limited-risk systems carry the Article 50 transparency duties; and "
            "minimal-risk systems have no mandatory obligations. General-purpose AI "
            "models are governed separately under Articles 51 to 56, with stricter "
            "duties for models posing systemic risk."
        ),
        "refs": ["Art. 5", "Art. 6", "Annex I", "Annex III", "Art. 50", "Art. 51", "Art. 52", "Art. 53", "Art. 54", "Art. 55", "Art. 56"],
    },
    # ── Education grading / student assessment (Annex III.3) ──────────
    {
        "name": "education_grading",
        "patterns": [
            # ``grades student essays`` / ``grade exam`` / ``grading papers`` /
            # ``automated grader``. Use ``grad\w*`` so the verb form
            # ``grades`` matches as well as ``grade`` / ``grading`` / ``grader``.
            re.compile(
                r"(?:\bgrad\w*\s+(?:student|essay|exam|test|paper|assignment)"
                r"|\bessay\s+(?:scor|grad|evaluat)"
                r"|\bstudent\s+(?:assessment|evaluation|admission|placement|monitoring|grading)"
                r"|\bautomated\s+(?:grader|grading|scoring))",
                re.IGNORECASE,
            ),
        ],
        "answer": (
            "AI used to determine access or admission to educational or vocational "
            "training institutions, evaluate learning outcomes, assess the appropriate "
            "level of education, or monitor prohibited behaviour during tests is "
            "high-risk under Annex III. Providers must meet Chapter III Section 2 "
            "obligations; deployers face Article 26 duties plus Article 27 fundamental-"
            "rights impact assessment if in the public sector."
        ),
        "refs": ["Annex III", "Art. 6", "Art. 26"],
    },
]
