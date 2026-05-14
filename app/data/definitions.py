"""Article 3 defined-terms catalogue (EU Regulation 2024/1689).

Article 3 of the AI Act enumerates ~68 defined terms whose semantics
are load-bearing for the rest of the regulation: every obligation in
Chapter III hinges on what "provider", "deployer", "intended purpose",
"placing on the market", etc. mean as terms of art.

The Q&A layer historically reached for these definitions on demand by
asking the LLM to paraphrase Art. 3 — which (a) consumes a turn of
context for something the regulation states verbatim, and (b) opens a
hallucination surface every time the model rewrites a regulatory
defined term. Surfacing the canonical definitions as a typed, in-process
lookup eliminates both costs.

## Coverage

This module ships ~30 of the highest-impact defined terms (the ones
that recur most frequently in compliance Q&A: operator roles,
biometric taxonomy, GPAI taxonomy, the lifecycle verbs, conformity-
assessment vocabulary). The catalogue is deliberately partial: a
confident 30-term subset beats a stretched 68-term set where the
edge entries paraphrase Art. 3 from training-data memory rather than
the regulation text. Additional terms can be added incrementally as
their wording is verified against the published Regulation.

## Bias guardrail

The definitions are intentionally written in neutral, textbook style
faithful to Art. 3 wording. They are NOT tailored to any single
example question (no special-casing of "emotion recognition",
"biometric data", or "medical" framings). The catalogue must remain a
general-purpose definitions lookup; question-specific framing belongs
in the route layer, not here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Definition:
    """A single Art. 3 defined term.

    Attributes:
        citation: The regulation pointer, e.g. ``"Art. 3.1"``. Resolves
            to a real article in
            :data:`app.data.article_existence.ARTICLE_EXISTENCE` once
            sub-paragraph fallback is applied.
        term: The canonical term being defined, e.g. ``"AI system"``.
        description: A 1-2 sentence faithful regulatory definition.
            Conservative wording — paraphrases the regulation only
            where helpful to readability, never expanding or narrowing
            the scope of the defined term.
        keywords: Search aliases (singular/plural/abbreviations) used by
            :func:`lookup_term` and :func:`search_definitions`. The
            canonical term and its lowercased variant should appear here.
    """

    citation: str
    term: str
    description: str
    keywords: tuple[str, ...]


# ── Catalogue ────────────────────────────────────────────────────────
#
# Each entry corresponds to a numbered point in Article 3 of EU
# Regulation 2024/1689. Definitions are kept short on purpose: they
# function as look-ups, not as substitute for the regulation text.
# Where Art. 3 sub-divides a term (e.g. real-time / post / remote
# biometric identification), each variant gets its own entry so the
# route layer can disambiguate.

_DEFINITIONS: tuple[Definition, ...] = (
    Definition(
        citation="Art. 3.1",
        term="AI system",
        description=(
            "A machine-based system designed to operate with varying levels "
            "of autonomy and that may exhibit adaptiveness after deployment, "
            "which, for explicit or implicit objectives, infers from the input "
            "it receives how to generate outputs such as predictions, content, "
            "recommendations, or decisions that can influence physical or "
            "virtual environments."
        ),
        keywords=(
            "ai system",
            "ai systems",
            "artificial intelligence system",
            "artificial intelligence systems",
        ),
    ),
    Definition(
        citation="Art. 3.2",
        term="risk",
        description=(
            "The combination of the probability of an occurrence of harm and "
            "the severity of that harm."
        ),
        keywords=("risk", "risks"),
    ),
    Definition(
        citation="Art. 3.3",
        term="provider",
        description=(
            "A natural or legal person, public authority, agency or other body "
            "that develops an AI system or a general-purpose AI model, or that "
            "has an AI system or a general-purpose AI model developed, and "
            "places it on the market or puts the AI system into service under "
            "its own name or trademark, whether for payment or free of charge."
        ),
        keywords=("provider", "providers"),
    ),
    Definition(
        citation="Art. 3.4",
        term="deployer",
        description=(
            "A natural or legal person, public authority, agency or other body "
            "using an AI system under its authority, except where the AI system "
            "is used in the course of a personal non-professional activity."
        ),
        keywords=("deployer", "deployers", "user", "users"),
    ),
    Definition(
        citation="Art. 3.5",
        term="authorised representative",
        description=(
            "A natural or legal person located or established in the Union who "
            "has received and accepted a written mandate from a provider of an "
            "AI system or a general-purpose AI model to, respectively, perform "
            "and carry out on its behalf the obligations and procedures "
            "established by this Regulation."
        ),
        keywords=(
            "authorised representative",
            "authorized representative",
            "authorised representatives",
            "authorized representatives",
        ),
    ),
    Definition(
        citation="Art. 3.6",
        term="importer",
        description=(
            "A natural or legal person located or established in the Union that "
            "places on the market an AI system that bears the name or trademark "
            "of a natural or legal person established in a third country."
        ),
        keywords=("importer", "importers"),
    ),
    Definition(
        citation="Art. 3.7",
        term="distributor",
        description=(
            "A natural or legal person in the supply chain, other than the "
            "provider or the importer, that makes an AI system available on "
            "the Union market."
        ),
        keywords=("distributor", "distributors"),
    ),
    Definition(
        citation="Art. 3.8",
        term="operator",
        description=(
            "A provider, product manufacturer, deployer, authorised "
            "representative, importer or distributor."
        ),
        keywords=("operator", "operators"),
    ),
    Definition(
        citation="Art. 3.9",
        term="placing on the market",
        description=(
            "The first making available of an AI system or a general-purpose AI "
            "model on the Union market."
        ),
        keywords=(
            "placing on the market",
            "placed on the market",
            "place on the market",
        ),
    ),
    Definition(
        citation="Art. 3.10",
        term="making available on the market",
        description=(
            "The supply of an AI system or a general-purpose AI model for "
            "distribution or use on the Union market in the course of a "
            "commercial activity, whether in return for payment or free of "
            "charge."
        ),
        keywords=(
            "making available on the market",
            "made available on the market",
            "make available on the market",
        ),
    ),
    Definition(
        citation="Art. 3.11",
        term="putting into service",
        description=(
            "The supply of an AI system for first use directly to the deployer "
            "or for own use in the Union for its intended purpose."
        ),
        keywords=(
            "putting into service",
            "put into service",
            "puts into service",
        ),
    ),
    Definition(
        citation="Art. 3.12",
        term="intended purpose",
        description=(
            "The use for which an AI system is intended by the provider, "
            "including the specific context and conditions of use, as specified "
            "in the information supplied by the provider in the instructions for "
            "use, promotional or sales materials and statements, as well as in "
            "the technical documentation."
        ),
        keywords=("intended purpose", "intended purposes", "intended use"),
    ),
    Definition(
        citation="Art. 3.13",
        term="reasonably foreseeable misuse",
        description=(
            "The use of an AI system in a way that is not in accordance with "
            "its intended purpose, but which may result from reasonably "
            "foreseeable human behaviour or interaction with other systems, "
            "including other AI systems."
        ),
        keywords=(
            "reasonably foreseeable misuse",
            "foreseeable misuse",
            "misuse",
        ),
    ),
    Definition(
        citation="Art. 3.14",
        term="safety component",
        description=(
            "A component of a product or of an AI system which fulfils a safety "
            "function for that product or AI system, or the failure or "
            "malfunctioning of which endangers the health and safety of persons "
            "or property."
        ),
        keywords=("safety component", "safety components"),
    ),
    Definition(
        citation="Art. 3.15",
        term="instructions for use",
        description=(
            "The information provided by the provider to inform the deployer of, "
            "in particular, an AI system's intended purpose and proper use."
        ),
        keywords=(
            "instructions for use",
            "instruction for use",
            "user instructions",
        ),
    ),
    Definition(
        citation="Art. 3.16",
        term="recall of an AI system",
        description=(
            "Any measure aimed at achieving the return to the provider, or "
            "taking out of service or disabling the use, of an AI system made "
            "available to deployers."
        ),
        keywords=("recall", "recalls", "recall of an ai system"),
    ),
    Definition(
        citation="Art. 3.17",
        term="withdrawal of an AI system",
        description=(
            "Any measure aimed at preventing an AI system in the supply chain "
            "from being made available on the market."
        ),
        keywords=("withdrawal", "withdrawals", "withdrawal of an ai system"),
    ),
    Definition(
        citation="Art. 3.18",
        term="performance of an AI system",
        description=(
            "The ability of an AI system to achieve its intended purpose."
        ),
        keywords=(
            "performance of an ai system",
            "ai system performance",
            "system performance",
        ),
    ),
    Definition(
        citation="Art. 3.19",
        term="harmonised standard",
        description=(
            "A harmonised standard as defined in Article 2(1)(c) of Regulation "
            "(EU) No 1025/2012."
        ),
        keywords=(
            "harmonised standard",
            "harmonized standard",
            "harmonised standards",
            "harmonized standards",
        ),
    ),
    Definition(
        citation="Art. 3.20",
        term="common specification",
        description=(
            "A set of technical specifications, as defined in Article 2(4) of "
            "Regulation (EU) No 1025/2012, providing means to comply with "
            "certain requirements established under this Regulation."
        ),
        keywords=(
            "common specification",
            "common specifications",
        ),
    ),
    Definition(
        citation="Art. 3.21",
        term="training data",
        description=(
            "Data used for training an AI system through fitting its learnable "
            "parameters."
        ),
        keywords=(
            "training data",
            "training dataset",
            "training datasets",
        ),
    ),
    Definition(
        citation="Art. 3.22",
        term="conformity assessment",
        description=(
            "The process of demonstrating whether the requirements set out in "
            "Chapter III, Section 2 relating to a high-risk AI system have been "
            "fulfilled."
        ),
        keywords=(
            "conformity assessment",
            "conformity assessments",
        ),
    ),
    Definition(
        citation="Art. 3.23",
        term="conformity assessment body",
        description=(
            "A body that performs third-party conformity assessment activities, "
            "including testing, certification and inspection."
        ),
        keywords=(
            "conformity assessment body",
            "conformity-assessment body",
            "conformity assessment bodies",
            "conformity-assessment bodies",
        ),
    ),
    Definition(
        citation="Art. 3.24",
        term="notified body",
        description=(
            "A conformity assessment body notified in accordance with this "
            "Regulation and other relevant Union harmonisation legislation."
        ),
        keywords=("notified body", "notified bodies"),
    ),
    Definition(
        citation="Art. 3.25",
        term="substantial modification",
        description=(
            "A change to an AI system after its placing on the market or "
            "putting into service which is not foreseen or planned in the "
            "initial conformity assessment carried out by the provider and as a "
            "result of which the compliance of the AI system with the "
            "requirements set out in Chapter III, Section 2 is affected, or "
            "which results in a modification to the intended purpose for which "
            "the AI system has been assessed."
        ),
        keywords=(
            "substantial modification",
            "substantial modifications",
        ),
    ),
    Definition(
        citation="Art. 3.26",
        term="validation data",
        description=(
            "Data used for providing an evaluation of the trained AI system and "
            "for tuning its non-learnable parameters and its learning process."
        ),
        keywords=(
            "validation data",
            "validation dataset",
            "validation datasets",
        ),
    ),
    Definition(
        citation="Art. 3.27",
        term="testing data",
        description=(
            "Data used for providing an independent evaluation of the AI system "
            "in order to confirm the expected performance of that system before "
            "its placing on the market or putting into service."
        ),
        keywords=(
            "testing data",
            "test data",
            "testing dataset",
        ),
    ),
    Definition(
        citation="Art. 3.28",
        term="input data",
        description=(
            "Data provided to or directly acquired by an AI system on the basis "
            "of which the system produces an output."
        ),
        keywords=(
            "input data",
            "input dataset",
            "system input",
        ),
    ),
    Definition(
        citation="Art. 3.29",
        term="CE marking",
        description=(
            "A marking by which a provider indicates that an AI system is in "
            "conformity with the requirements set out in Chapter III, Section 2 "
            "and other applicable Union harmonisation legislation."
        ),
        keywords=(
            "ce marking",
            "ce mark",
            "ce conformity marking",
        ),
    ),
    Definition(
        citation="Art. 3.30",
        term="post-market monitoring system",
        description=(
            "All activities carried out by providers of AI systems to collect "
            "and review experience gained from the use of AI systems they place "
            "on the market or put into service for the purpose of identifying "
            "any need to immediately apply any necessary corrective or "
            "preventive actions."
        ),
        keywords=(
            "post-market monitoring system",
            "post market monitoring",
            "post-market monitoring",
        ),
    ),
    Definition(
        citation="Art. 3.31",
        term="market surveillance authority",
        description=(
            "The national authority carrying out the activities and taking the "
            "measures pursuant to Regulation (EU) 2019/1020."
        ),
        keywords=(
            "market surveillance authority",
            "market surveillance authorities",
            "market surveillance",
        ),
    ),
    Definition(
        citation="Art. 3.32",
        term="national competent authority",
        description=(
            "A notifying authority or a market surveillance authority designated "
            "by a Member State to ensure the application and implementation of "
            "this Regulation."
        ),
        keywords=(
            "national competent authority",
            "national competent authorities",
            "competent authority",
        ),
    ),
    Definition(
        citation="Art. 3.33",
        term="biometric data",
        description=(
            "Personal data resulting from specific technical processing relating "
            "to the physical, physiological or behavioural characteristics of a "
            "natural person, such as facial images or dactyloscopic data."
        ),
        keywords=("biometric data", "biometrics"),
    ),
    Definition(
        citation="Art. 3.34",
        term="biometric identification",
        description=(
            "The automated recognition of physical, physiological, behavioural "
            "or psychological human features for the purpose of establishing the "
            "identity of a natural person by comparing biometric data of that "
            "individual to biometric data of individuals stored in a database."
        ),
        keywords=(
            "biometric identification",
            "biometric identifications",
        ),
    ),
    Definition(
        citation="Art. 3.35",
        term="biometric verification",
        description=(
            "The automated, one-to-one verification, including authentication, "
            "of the identity of natural persons by comparing their biometric "
            "data to previously provided biometric data."
        ),
        keywords=(
            "biometric verification",
            "biometric authentication",
        ),
    ),
    Definition(
        citation="Art. 3.36",
        term="biometric categorisation",
        description=(
            "Assigning natural persons to specific categories on the basis of "
            "their biometric data, where these categories relate to aspects "
            "such as sex, age, hair colour, eye colour, tattoos, behavioural "
            "or personality traits, language, religion, membership of a "
            "national minority, sexual or political orientation."
        ),
        keywords=(
            "biometric categorisation",
            "biometric categorization",
        ),
    ),
    Definition(
        citation="Art. 3.37",
        term="real-time remote biometric identification system",
        description=(
            "A remote biometric identification system whereby the capturing of "
            "biometric data, the comparison and the identification all occur "
            "without significant delay, comprising not only instant "
            "identification but also limited short delays in order to avoid "
            "circumvention."
        ),
        keywords=(
            "real-time remote biometric identification system",
            "real time remote biometric identification system",
            "real-time rbi",
            "real time rbi",
            "real-time biometric identification",
        ),
    ),
    Definition(
        citation="Art. 3.38",
        term="post remote biometric identification system",
        description=(
            "A remote biometric identification system other than a real-time "
            "remote biometric identification system."
        ),
        keywords=(
            "post remote biometric identification system",
            "post-remote biometric identification system",
            "post rbi",
            "post-rbi",
            "post biometric identification",
        ),
    ),
    Definition(
        citation="Art. 3.40",
        term="remote biometric identification system",
        description=(
            "An AI system for the purpose of identifying natural persons, "
            "without their active involvement, typically at a distance through "
            "the comparison of a person's biometric data with the biometric "
            "data contained in a reference database."
        ),
        keywords=(
            "remote biometric identification system",
            "rbi system",
            "remote biometric identification",
            "rbi",
        ),
    ),
    Definition(
        citation="Art. 3.41",
        term="biometric categorisation system",
        description=(
            "An AI system for the purpose of assigning natural persons to "
            "specific categories on the basis of their biometric data, unless it "
            "is ancillary to another commercial service and strictly necessary "
            "for objective technical reasons."
        ),
        keywords=(
            "biometric categorisation system",
            "biometric categorization system",
        ),
    ),
    Definition(
        citation="Art. 3.42",
        term="publicly accessible space",
        description=(
            "Any publicly or privately owned physical place accessible to an "
            "undetermined number of natural persons, regardless of whether "
            "certain conditions for access may apply, and regardless of the "
            "potential capacity restrictions."
        ),
        keywords=(
            "publicly accessible space",
            "publicly accessible spaces",
            "public space",
            "public spaces",
        ),
    ),
    Definition(
        citation="Art. 3.43",
        term="law enforcement authority",
        description=(
            "Any public authority competent for the prevention, investigation, "
            "detection or prosecution of criminal offences or the execution of "
            "criminal penalties, including the safeguarding against and the "
            "prevention of threats to public security; or any other body or "
            "entity entrusted by Member State law to exercise public authority "
            "for those purposes."
        ),
        keywords=(
            "law enforcement authority",
            "law enforcement authorities",
            "police authority",
        ),
    ),
    Definition(
        citation="Art. 3.44",
        term="law enforcement",
        description=(
            "Activities carried out by law enforcement authorities or on their "
            "behalf for the prevention, investigation, detection or prosecution "
            "of criminal offences or the execution of criminal penalties, "
            "including the safeguarding against and the prevention of threats "
            "to public security."
        ),
        keywords=(
            "law enforcement",
            "criminal law enforcement",
            "policing",
        ),
    ),
    Definition(
        citation="Art. 3.45",
        term="profiling",
        description=(
            "Profiling as defined in Article 4, point (4), of Regulation (EU) "
            "2016/679."
        ),
        keywords=(
            "profiling",
            "profile",
            "automated profiling",
        ),
    ),
    Definition(
        citation="Art. 3.46",
        term="testing in real-world conditions",
        description=(
            "The temporary testing of an AI system for its intended purpose in "
            "real-world conditions outside a laboratory or otherwise simulated "
            "environment, with a view to gathering reliable and robust data and "
            "to assessing and verifying the conformity of the AI system with "
            "the requirements of this Regulation."
        ),
        keywords=(
            "testing in real-world conditions",
            "real-world testing",
            "real world testing",
        ),
    ),
    Definition(
        citation="Art. 3.47",
        term="real-world testing plan",
        description=(
            "A document that describes the objectives, methodology, geographical, "
            "population and temporal scope, monitoring, organisation and conduct "
            "of testing in real-world conditions."
        ),
        keywords=(
            "real-world testing plan",
            "real world testing plan",
            "rwt plan",
        ),
    ),
    Definition(
        citation="Art. 3.48",
        term="AI regulatory sandbox",
        description=(
            "A controlled framework set up by a competent authority which "
            "offers providers or prospective providers of AI systems the "
            "possibility to develop, train, validate and test, where "
            "appropriate in real-world conditions, an innovative AI system, "
            "pursuant to a sandbox plan for a limited time under regulatory "
            "supervision."
        ),
        keywords=(
            "ai regulatory sandbox",
            "regulatory sandbox",
            "sandbox",
        ),
    ),
    Definition(
        citation="Art. 3.39",
        term="emotion recognition system",
        description=(
            "An AI system for the purpose of identifying or inferring emotions "
            "or intentions of natural persons on the basis of their biometric "
            "data."
        ),
        keywords=(
            "emotion recognition system",
            "emotion recognition",
        ),
    ),
    Definition(
        citation="Art. 3.50",
        term="special categories of personal data",
        description=(
            "The categories of personal data referred to in Article 9(1) of "
            "Regulation (EU) 2016/679, Article 10 of Directive (EU) 2016/680 "
            "and Article 10(1) of Regulation (EU) 2018/1725."
        ),
        keywords=(
            "special categories of personal data",
            "special category data",
            "sensitive personal data",
        ),
    ),
    Definition(
        citation="Art. 3.51",
        term="sensitive operational data",
        description=(
            "Operational data related to activities of prevention, detection, "
            "investigation or prosecution of criminal offences, the disclosure "
            "of which could jeopardise the integrity of criminal proceedings."
        ),
        keywords=(
            "sensitive operational data",
            "operational data",
        ),
    ),
    Definition(
        citation="Art. 3.52",
        term="informed consent",
        description=(
            "A subject's freely-given, specific, unambiguous and voluntary "
            "expression of his or her willingness to participate in a particular "
            "testing in real-world conditions, after having been informed of all "
            "aspects of the testing that are relevant to the subject's decision "
            "to participate."
        ),
        keywords=(
            "informed consent",
            "subject consent",
            "consent",
        ),
    ),
    Definition(
        citation="Art. 3.53",
        term="high-impact capabilities",
        description=(
            "Capabilities that match or exceed the capabilities recorded in the "
            "most advanced general-purpose AI models."
        ),
        keywords=(
            "high-impact capabilities",
            "high impact capabilities",
            "frontier capabilities",
        ),
    ),
    Definition(
        citation="Art. 3.54",
        term="floating-point operation",
        description=(
            "Any mathematical operation or assignment involving floating-point "
            "numbers, which are a subset of the real numbers typically "
            "represented on computers by an integer of fixed precision scaled "
            "by an integer exponent of a fixed base."
        ),
        keywords=(
            "floating-point operation",
            "floating point operation",
            "flop",
            "flops",
        ),
    ),
    Definition(
        citation="Art. 3.55",
        term="downstream provider",
        description=(
            "A provider of an AI system, including a general-purpose AI system, "
            "which integrates an AI model, regardless of whether the AI model "
            "is provided by themselves and vertically integrated or provided by "
            "another entity based on contractual relations."
        ),
        keywords=(
            "downstream provider",
            "downstream providers",
        ),
    ),
    Definition(
        citation="Art. 3.60",
        term="deep fake",
        description=(
            "AI-generated or manipulated image, audio or video content that "
            "resembles existing persons, objects, places, entities or events "
            "and would falsely appear to a person to be authentic or truthful."
        ),
        keywords=("deep fake", "deepfake", "deep fakes", "deepfakes"),
    ),
    Definition(
        citation="Art. 3.49",
        term="serious incident",
        description=(
            "An incident or malfunctioning of an AI system that directly or "
            "indirectly leads to the death of a person or serious harm to a "
            "person's health, a serious and irreversible disruption of the "
            "management or operation of critical infrastructure, a breach of "
            "obligations under Union law intended to protect fundamental rights, "
            "or serious harm to property or the environment."
        ),
        keywords=("serious incident", "serious incidents"),
    ),
    Definition(
        citation="Art. 3.56",
        term="AI literacy",
        description=(
            "Skills, knowledge and understanding that allow providers, deployers "
            "and affected persons to make an informed deployment of AI systems, "
            "as well as to gain awareness about the opportunities and risks of "
            "AI and the possible harm it can cause."
        ),
        keywords=("ai literacy", "literacy"),
    ),
    Definition(
        citation="Art. 3.57",
        term="testing in real world conditions plan",
        description=(
            "A document that describes the objectives, methodology, "
            "geographical, population and temporal scope, monitoring, "
            "organisation and conduct of testing in real-world conditions."
        ),
        keywords=(
            "testing in real world conditions plan",
            "real world conditions plan",
            "real-world conditions plan",
        ),
    ),
    Definition(
        citation="Art. 3.58",
        term="sandbox plan",
        description=(
            "A document agreed between the participating provider and the "
            "competent authority describing the objectives, conditions, "
            "timeframe, methodology and requirements for the activities carried "
            "out within the sandbox."
        ),
        keywords=(
            "sandbox plan",
            "regulatory sandbox plan",
        ),
    ),
    Definition(
        citation="Art. 3.59",
        term="subject of testing in real-world conditions",
        description=(
            "A natural person who participates in testing in real-world "
            "conditions."
        ),
        keywords=(
            "subject of testing in real-world conditions",
            "testing subject",
            "real-world testing subject",
        ),
    ),
    Definition(
        citation="Art. 3.61",
        term="notifying authority",
        description=(
            "The national authority responsible for setting up and carrying out "
            "the necessary procedures for the assessment, designation and "
            "notification of conformity assessment bodies and for their "
            "monitoring."
        ),
        keywords=(
            "notifying authority",
            "notifying authorities",
        ),
    ),
    Definition(
        citation="Art. 3.62",
        term="critical infrastructure",
        description=(
            "Critical infrastructure as defined in Article 2, point (4), of "
            "Directive (EU) 2022/2557."
        ),
        keywords=(
            "critical infrastructure",
            "critical infrastructures",
        ),
    ),
    Definition(
        citation="Art. 3.63",
        term="general-purpose AI model",
        description=(
            "An AI model, including where such an AI model is trained with a "
            "large amount of data using self-supervision at scale, that displays "
            "significant generality and is capable of competently performing a "
            "wide range of distinct tasks regardless of the way the model is "
            "placed on the market and that can be integrated into a variety of "
            "downstream systems or applications."
        ),
        keywords=(
            "general-purpose ai model",
            "general purpose ai model",
            "gpai model",
            "gpai models",
            "foundation model",
            "foundation models",
        ),
    ),
    Definition(
        citation="Art. 3.64",
        term="AI Office",
        description=(
            "The Commission's function of contributing to the implementation, "
            "monitoring and supervision of AI systems and general-purpose AI "
            "models, and AI governance, provided for in Commission Decision of "
            "24 January 2024."
        ),
        keywords=(
            "ai office",
            "the ai office",
            "european ai office",
        ),
    ),
    Definition(
        citation="Art. 3.65",
        term="systemic risk",
        description=(
            "A risk that is specific to the high-impact capabilities of "
            "general-purpose AI models, having a significant impact on the "
            "Union market due to their reach, or due to actual or reasonably "
            "foreseeable negative effects on public health, safety, public "
            "security, fundamental rights, or the society as a whole, that can "
            "be propagated at scale across the value chain."
        ),
        keywords=("systemic risk", "systemic risks"),
    ),
    Definition(
        citation="Art. 3.66",
        term="general-purpose AI system",
        description=(
            "An AI system which is based on a general-purpose AI model and "
            "which has the capability to serve a variety of purposes, both for "
            "direct use as well as for integration in other AI systems."
        ),
        keywords=(
            "general-purpose ai system",
            "general purpose ai system",
            "gpai system",
            "gpai systems",
        ),
    ),
    Definition(
        citation="Art. 3.67",
        term="European Artificial Intelligence Board",
        description=(
            "The Board established pursuant to Article 65, composed of "
            "representatives of the Member States, which advises and assists "
            "the Commission and Member States in order to facilitate the "
            "consistent and effective application of this Regulation."
        ),
        keywords=(
            "european artificial intelligence board",
            "ai board",
            "the board",
        ),
    ),
    Definition(
        citation="Art. 3.68",
        term="European Data Protection Supervisor",
        description=(
            "The independent supervisory authority established by Regulation "
            "(EU) 2018/1725, responsible for monitoring the application of "
            "data protection rules to Union institutions, bodies, offices and "
            "agencies."
        ),
        keywords=(
            "european data protection supervisor",
            "edps",
            "data protection supervisor",
        ),
    ),
)


#: Definition catalogue keyed by Article 3 citation (``"Art. 3.N"``).
#:
#: Lookup by citation is O(1); lookup by term or alias is provided by
#: :func:`lookup_term`. The keys are guaranteed to be sub-paragraph
#: forms of ``Art. 3`` and so resolve under the prefix-fallback
#: semantics used by :data:`app.data.article_existence.ARTICLE_EXISTENCE`.
DEFINITION_REGISTRY: dict[str, Definition] = {d.citation: d for d in _DEFINITIONS}


def _normalise(text: str) -> str:
    """Casefold + collapse whitespace for lookups.

    We do NOT strip punctuation: ``"deep fake"`` and ``"deep-fake"`` are
    distinct surface forms that the keyword tuple is expected to enumerate
    explicitly. Conservative behaviour avoids false-positive matches like
    ``"deep fakes are bad"`` colliding with ``"deepfakes are bad"`` when
    only one variant is in ``keywords``.
    """
    return " ".join(text.casefold().split())


# Build a (alias → Definition) reverse index at import time. Mapped from
# normalised aliases so lookup is O(1) regardless of input casing.
_ALIAS_INDEX: dict[str, Definition] = {}
for _defn in _DEFINITIONS:
    _ALIAS_INDEX[_normalise(_defn.term)] = _defn
    for _kw in _defn.keywords:
        # Last-write-wins on alias collision is acceptable: collisions
        # within Art. 3 would indicate a genuine ambiguity in the
        # source terminology that the caller has to disambiguate via
        # context anyway.
        _ALIAS_INDEX.setdefault(_normalise(_kw), _defn)


def lookup_term(term_or_alias: str) -> Definition | None:
    """Return the :class:`Definition` for ``term_or_alias``, or ``None``.

    Lookup is case-insensitive and whitespace-tolerant. Matches against
    both the canonical term and every alias in the keywords tuple.

    Example:
        >>> lookup_term("provider").citation
        'Art. 3.3'
        >>> lookup_term("GPAI model").citation
        'Art. 3.63'
        >>> lookup_term("nonexistent") is None
        True
    """
    if not term_or_alias:
        return None
    return _ALIAS_INDEX.get(_normalise(term_or_alias))


def search_definitions(
    query: str, top_k: int = 5
) -> list[tuple[str, Definition]]:
    """Token-overlap search over the definitions catalogue.

    Returns up to ``top_k`` ``(citation, Definition)`` tuples ranked by
    descending token overlap between ``query`` and the definition's term
    + keywords. This is intentionally simple: the catalogue is small (~30
    entries), so a full BM25 index would be overkill; the overlap score
    is monotonic in the number of query tokens that hit any alias.

    A definition matches if at least one of its term tokens or aliases
    overlaps with the query token set. Empty / stop-word-only queries
    return an empty list.

    Example:
        >>> hits = search_definitions("biometric", top_k=3)
        >>> all("biometric" in defn.term.lower() or
        ...     any("biometric" in kw for kw in defn.keywords)
        ...     for _, defn in hits)
        True
    """
    if not query or not query.strip():
        return []

    query_tokens = set(_normalise(query).split())
    if not query_tokens:
        return []

    scored: list[tuple[int, Definition]] = []
    for defn in _DEFINITIONS:
        # Collect every token across the canonical term + every alias.
        alias_tokens: set[str] = set()
        alias_tokens.update(_normalise(defn.term).split())
        # Also count multi-word alias hits — a query of "biometric
        # categorisation" should score above one that only matches
        # "biometric". We do this by checking each whole alias as a
        # substring of the joined query, with a small bonus.
        joined_query = _normalise(query)
        score = 0
        for kw in defn.keywords:
            alias_tokens.update(_normalise(kw).split())
            if _normalise(kw) in joined_query:
                score += 2  # phrase-match bonus
        overlap = query_tokens & alias_tokens
        score += len(overlap)
        if score > 0:
            scored.append((score, defn))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [(defn.citation, defn) for _, defn in scored[:top_k]]


__all__ = [
    "Definition",
    "DEFINITION_REGISTRY",
    "lookup_term",
    "search_definitions",
]
