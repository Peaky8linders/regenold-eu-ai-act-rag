"""Fundamental Rights Impact Assessment (FRIA) Evaluator under Article 27 of the EU AI Act.

Maps Annex III high-risk deployer scenarios to specific EU Charter of Fundamental Rights
Articles (Art 1 Human Dignity, Art 7 Privacy, Art 8 Data Protection, Art 21 Non-discrimination,
Art 47 Fair Trial / Effective Remedy) and evaluates deployer obligations under Article 27.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CharterArticle:
    """Represents an EU Charter of Fundamental Rights Article."""

    article_id: str  # e.g., "Art. 1", "Art. 7", "Art. 8", "Art. 21", "Art. 47"
    title: str  # e.g., "Human Dignity"
    description: str


# The five primary EU Charter Articles mandated for FRIA evaluation
CHARTER_DIGNITY = CharterArticle(
    article_id="Art. 1",
    title="Human Dignity",
    description="Human dignity is inviolable. It must be respected and protected.",
)
CHARTER_PRIVACY = CharterArticle(
    article_id="Art. 7",
    title="Respect for Private and Family Life",
    description="Everyone has the right to respect for his or her private and family life, home and communications.",
)
CHARTER_DATA_PROTECTION = CharterArticle(
    article_id="Art. 8",
    title="Protection of Personal Data",
    description="Everyone has the right to the protection of personal data concerning him or her.",
)
CHARTER_NON_DISCRIMINATION = CharterArticle(
    article_id="Art. 21",
    title="Non-discrimination",
    description="Any discrimination based on any ground such as sex, race, colour, ethnic or social origin, genetic features, language, religion or belief, political or any other opinion, membership of a national minority, property, birth, disability, age or sexual orientation shall be prohibited.",
)
CHARTER_FAIR_TRIAL = CharterArticle(
    article_id="Art. 47",
    title="Right to an Effective Remedy and to a Fair Trial",
    description="Everyone whose rights and freedoms guaranteed by the law of the Union are violated has the right to an effective remedy before a tribunal in compliance with the conditions laid down in this Article.",
)

CHARTER_CATALOG: dict[str, CharterArticle] = {
    "Art. 1": CHARTER_DIGNITY,
    "Art. 7": CHARTER_PRIVACY,
    "Art. 8": CHARTER_DATA_PROTECTION,
    "Art. 21": CHARTER_NON_DISCRIMINATION,
    "Art. 47": CHARTER_FAIR_TRIAL,
}


@dataclass(frozen=True)
class FRIARequirement:
    """Article 27 FRIA obligation specification for deployers of high-risk AI systems."""

    article_id: str = "Art. 27"
    is_required: bool = False
    impacted_charter_articles: tuple[str, ...] = field(default_factory=tuple)
    risk_mitigations: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


@dataclass(frozen=True)
class FRIAEvaluation:
    """Outcome of a Fundamental Rights Impact Assessment evaluation."""

    is_annex_iii: bool
    annex_iii_category: str | None
    role: str  # "deployer", "provider", etc.
    fria_required: bool
    charter_articles: tuple[CharterArticle, ...]
    impacted_rights: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    summary: str


# Annex III Category -> Charter Articles Mapping
_ANNEX_III_CHARTER_MAP: dict[str, tuple[str, ...]] = {
    "biometrics": ("Art. 1", "Art. 7", "Art. 8", "Art. 21"),
    "critical_infrastructure": ("Art. 1", "Art. 7"),
    "education": ("Art. 1", "Art. 8", "Art. 21"),
    "employment": ("Art. 1", "Art. 7", "Art. 8", "Art. 21"),
    "essential_services": ("Art. 7", "Art. 8", "Art. 21"),
    "law_enforcement": ("Art. 1", "Art. 7", "Art. 8", "Art. 21", "Art. 47"),
    "migration": ("Art. 1", "Art. 7", "Art. 8", "Art. 21", "Art. 47"),
    "justice": ("Art. 1", "Art. 21", "Art. 47"),
}

# Regex patterns for Annex III classification in FRIA evaluator
_ANNEX_III_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:biometric|emotion recognition)\b", re.I), "biometrics"),
    (re.compile(r"\b(?:critical infrastructure|safety component)\b", re.I), "critical_infrastructure"),
    (re.compile(r"\b(?:education|school|exam|vocational)\b", re.I), "education"),
    (re.compile(r"\b(?:recruitment|cv screening|resume|worker|hiring|employment|promotion|termination)\b", re.I), "employment"),
    (re.compile(r"\b(?:credit|loan|insurance|social benefits|essential service)\b", re.I), "essential_services"),
    (re.compile(r"\b(?:law enforcement|police|crime prediction|evidence|prosecution)\b", re.I), "law_enforcement"),
    (re.compile(r"\b(?:asylum|border|migration|visa|passport)\b", re.I), "migration"),
    (re.compile(r"\b(?:justice|judicial|court|democratic process|election)\b", re.I), "justice"),
)

# Art 27 Deployer trigger patterns: public body, public service, credit, health insurance
_ART27_TRIGGER_PATTERNS = (
    "public body", "public law", "public authority", "public agency", "government",
    "public service", "providing public services", "hospital", "healthcare",
    "credit scoring", "credit rating", "credit evaluation", "creditworthiness",
    "insurance pricing", "life insurance", "health insurance", "risk assessment for insurance",
)


def get_charter_mapping(annex_iii_category: str) -> list[str]:
    """Return the list of Charter article IDs mapped to the given Annex III category."""
    return list(_ANNEX_III_CHARTER_MAP.get(annex_iii_category.lower(), ("Art. 1", "Art. 7", "Art. 8", "Art. 21")))


def evaluate_fria(scenario_text: str, role: str = "deployer") -> FRIAEvaluation:
    """Evaluate a scenario for Fundamental Rights Impact Assessment (FRIA) requirements under Article 27.

    Maps Annex III high-risk deployer scenarios to Charter Articles (Art 1 Dignity,
    Art 7/8 Privacy/Data Protection, Art 21 Non-discrimination, Art 47 Fair Trial).
    """
    if not scenario_text:
        return FRIAEvaluation(
            is_annex_iii=False,
            annex_iii_category=None,
            role=role,
            fria_required=False,
            charter_articles=(),
            impacted_rights=(),
            recommended_actions=(),
            summary="Empty scenario provided.",
        )

    low = scenario_text.lower()

    # 1. Detect Annex III category
    detected_category: str | None = None
    for pattern, category in _ANNEX_III_PATTERNS:
        if pattern.search(low):
            detected_category = category
            break

    is_annex_iii = detected_category is not None

    # 2. Check if FRIA under Article 27 is required
    # Art 27 applies to deployers of Annex III high-risk AI systems who are public bodies,
    # public service providers, or evaluating credit / life/health insurance.
    is_deployer = role.lower() == "deployer" or "deployer" in low or "we deploy" in low or "we use" in low
    has_trigger = any(t in low for t in _ART27_TRIGGER_PATTERNS) or is_deployer
    fria_required = is_annex_iii and has_trigger

    # 3. Get mapped Charter Articles
    if is_annex_iii and detected_category:
        charter_ids = _ANNEX_III_CHARTER_MAP.get(detected_category, ("Art. 1", "Art. 7", "Art. 8", "Art. 21"))
    else:
        charter_ids = ()

    charter_articles = tuple(CHARTER_CATALOG[cid] for cid in charter_ids if cid in CHARTER_CATALOG)
    impacted_rights = tuple(f"{art.article_id} ({art.title})" for art in charter_articles)

    # 4. Generate recommended actions for Article 27 compliance
    recommended: list[str] = []
    if fria_required:
        recommended.append("Perform a Fundamental Rights Impact Assessment prior to putting the system into service (Article 27(1)).")
        recommended.append("Assess human oversight arrangements, deployer processes, and specific target group risks (Article 27(1)(a)-(c)).")
        recommended.append("Notify the relevant market surveillance authority of the assessment results (Article 27(2)).")
        recommended.append("Establish a continuous risk management and monitoring plan for fundamental rights (Articles 9, 27).")

    summary_prose = (
        f"FRIA evaluation under Article 27: {'REQUIRED' if fria_required else 'NOT REQUIRED'}. "
        + (f"Annex III category '{detected_category}' impacts: {', '.join(charter_ids)}. " if is_annex_iii else "No Annex III high-risk category detected. ")
        + ("Deployer must complete an Article 27 assessment." if fria_required else "Standard compliance monitoring applies.")
    )

    return FRIAEvaluation(
        is_annex_iii=is_annex_iii,
        annex_iii_category=detected_category,
        role=role,
        fria_required=fria_required,
        charter_articles=charter_articles,
        impacted_rights=impacted_rights,
        recommended_actions=tuple(recommended),
        summary=summary_prose,
    )
