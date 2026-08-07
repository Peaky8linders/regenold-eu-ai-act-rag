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

    #: Deliberately prefixed ``"Charter Art. N"``. In this repo a bare
    #: ``"Art. N"`` is an EU AI ACT reference, and Articles 1, 7, 8, 21 and 47
    #: ALL exist in the Act — so an unprefixed Charter id would sail through
    #: the ``ARTICLE_EXISTENCE`` lint (hard rule #5) and ship as a wrong AI Act
    #: citation the moment this module is wired to anything (hard rule #4).
    #: These must never reach the wire at all: hard rule #1 permits only
    #: ``Article N`` / ``Annex X``, and the Charter is not the Regulation.
    article_id: str  # e.g. "Charter Art. 1", "Charter Art. 21"
    title: str  # e.g., "Human Dignity"
    description: str


# The five primary EU Charter Articles mandated for FRIA evaluation
CHARTER_DIGNITY = CharterArticle(
    article_id="Charter Art. 1",
    title="Human Dignity",
    description="Human dignity is inviolable. It must be respected and protected.",
)
CHARTER_PRIVACY = CharterArticle(
    article_id="Charter Art. 7",
    title="Respect for Private and Family Life",
    description="Everyone has the right to respect for his or her private and family life, home and communications.",
)
CHARTER_DATA_PROTECTION = CharterArticle(
    article_id="Charter Art. 8",
    title="Protection of Personal Data",
    description="Everyone has the right to the protection of personal data concerning him or her.",
)
CHARTER_NON_DISCRIMINATION = CharterArticle(
    article_id="Charter Art. 21",
    title="Non-discrimination",
    description="Any discrimination based on any ground such as sex, race, colour, ethnic or social origin, genetic features, language, religion or belief, political or any other opinion, membership of a national minority, property, birth, disability, age or sexual orientation shall be prohibited.",
)
CHARTER_FAIR_TRIAL = CharterArticle(
    article_id="Charter Art. 47",
    title="Right to an Effective Remedy and to a Fair Trial",
    description="Everyone whose rights and freedoms guaranteed by the law of the Union are violated has the right to an effective remedy before a tribunal in compliance with the conditions laid down in this Article.",
)

CHARTER_CATALOG: dict[str, CharterArticle] = {
    "Charter Art. 1": CHARTER_DIGNITY,
    "Charter Art. 7": CHARTER_PRIVACY,
    "Charter Art. 8": CHARTER_DATA_PROTECTION,
    "Charter Art. 21": CHARTER_NON_DISCRIMINATION,
    "Charter Art. 47": CHARTER_FAIR_TRIAL,
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
    "biometrics": ("Charter Art. 1", "Charter Art. 7", "Charter Art. 8", "Charter Art. 21"),
    "critical_infrastructure": ("Charter Art. 1", "Charter Art. 7"),
    "education": ("Charter Art. 1", "Charter Art. 8", "Charter Art. 21"),
    "employment": ("Charter Art. 1", "Charter Art. 7", "Charter Art. 8", "Charter Art. 21"),
    "essential_services": ("Charter Art. 7", "Charter Art. 8", "Charter Art. 21"),
    "law_enforcement": ("Charter Art. 1", "Charter Art. 7", "Charter Art. 8", "Charter Art. 21", "Charter Art. 47"),
    "migration": ("Charter Art. 1", "Charter Art. 7", "Charter Art. 8", "Charter Art. 21", "Charter Art. 47"),
    "justice": ("Charter Art. 1", "Charter Art. 21", "Charter Art. 47"),
}

# Regex patterns for Annex III classification in FRIA evaluator
_ANNEX_III_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:biometric|emotion recognition)\b", re.I), "biometrics"),
    (re.compile(r"\b(?:critical infrastructure|safety component)\b", re.I), "critical_infrastructure"),
    (re.compile(r"\b(?:education|school|exam|vocational)\b", re.I), "education"),
    (re.compile(r"\b(?:recruitment|cv screening|resume|worker|hiring|employment|promotion|termination)\b", re.I), "employment"),
    # R321 — "credit" with a trailing \b cannot match "creditworthiness", which
    # is the Act's OWN word in Annex III 5(b) ("evaluate the creditworthiness of
    # natural persons or establish their credit score"). Measured: the bank
    # credit-scoring scenario — the case Article 27(1) names explicitly — was
    # classified as NOT Annex III at all. Use a prefix match for the credit
    # family and keep \b only where the whole word is the term.
    # Annex III point 5 — "Access to and enjoyment of essential private services
    # and essential public services and benefits". Terms taken from the Act's own
    # wording for 5(a) (eligibility for essential public assistance benefits and
    # services, including healthcare), 5(b) (creditworthiness / credit score) and
    # 5(c) (risk assessment and pricing for life and health insurance).
    (
        re.compile(
            r"credit\w*"
            r"|\b(?:loan|insurance)\b"
            r"|\bpublic assistance\b"
            r"|\bsocial (?:benefit|security)\w*\b"
            r"|\bwelfare benefit\w*\b"
            r"|\bessential (?:public|private) (?:service|benefit)\w*\b"
            r"|\bessential service\w*\b"
            r"|\beligibility (?:of|for)\b",
            re.I,
        ),
        "essential_services",
    ),
    (re.compile(r"\b(?:law enforcement|police|crime prediction|evidence|prosecution)\b", re.I), "law_enforcement"),
    (re.compile(r"\b(?:asylum|border|migration|visa|passport)\b", re.I), "migration"),
    (re.compile(r"\b(?:justice|judicial|court|democratic process|election)\b", re.I), "justice"),
)

# ── Article 27(1) trigger, verbatim ─────────────────────────────────────────
#
# "Prior to deploying a high-risk AI system referred to in Article 6(2), WITH
#  THE EXCEPTION OF high-risk AI systems intended to be used in the area listed
#  in point 2 of Annex III, deployers that are bodies governed by public law, or
#  are private entities providing public services, AND deployers of high-risk AI
#  systems referred to in points 5 (b) and (c) of Annex III, shall perform an
#  assessment of the impact on fundamental rights..."
#
# So the duty binds iff ALL of:
#   (1) the system is Annex III high-risk (Art. 6(2)); AND
#   (2) it is NOT in Annex III point 2 (critical infrastructure) — an explicit
#       carve-out the previous implementation did not have; AND
#   (3) EITHER the deployer is a body governed by public law / a private entity
#       providing public services, OR the system is Annex III 5(b)
#       (creditworthiness, credit score) or 5(c) (risk assessment and pricing
#       for life and health insurance).
#
# Being a "deployer" is a PRECONDITION, never a trigger. The previous code did
# ``has_trigger = any(...) or is_deployer`` with role defaulting to "deployer",
# which made the trigger unconditionally true — so an ordinary private company
# screening its own job applicants was told a FRIA was required (it is not),
# while a bank doing credit scoring was told it was not (it is).

#: (3a) deployer is a body governed by public law, or a PRIVATE entity
#: providing public services. The second limb is not a guess: Recital 96 names
#: the areas verbatim — "Private entities providing such public services are
#: linked to tasks in the public interest such as in the areas of education,
#: healthcare, social services, housing, administration of justice."
_ART27_PUBLIC_DEPLOYER_PATTERNS = (
    # bodies governed by public law
    "public body", "public law", "public authority", "public authorities",
    "public agency", "government", "municipal", "ministry", "state agency",
    # private entities providing public services (generic)
    "public service", "public services", "providing public services",
    # ...and the areas Recital 96 lists as tasks in the public interest
    "hospital", "clinic", "healthcare provider", "health service",
    "school", "university", "college", "education provider",
    "social services", "social housing", "housing association",
    "administration of justice", "court",
)

#: (3b) the system itself is Annex III 5(b) or 5(c) — in scope regardless of
#: who the deployer is.
_ART27_ANNEX_III_5BC_PATTERNS = (
    "creditworthiness", "credit score", "credit scoring", "credit rating",
    "credit evaluation", "evaluate the credit",
    "life insurance", "health insurance", "insurance pricing",
    "risk assessment and pricing", "risk assessment for insurance",
)

#: (2) the Annex III point 2 carve-out — critical infrastructure is EXCLUDED
#: from the FRIA duty by the opening clause of Article 27(1).
_ART27_EXCLUDED_CATEGORIES = frozenset({"critical_infrastructure"})


def get_charter_mapping(annex_iii_category: str) -> list[str]:
    """Return the list of Charter article IDs mapped to the given Annex III category."""
    return list(_ANNEX_III_CHARTER_MAP.get(annex_iii_category.lower(), ("Charter Art. 1", "Charter Art. 7", "Charter Art. 8", "Charter Art. 21")))


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

    # 2. Article 27(1). See the verbatim quote above _ART27_PUBLIC_DEPLOYER_PATTERNS.
    #    Three conjunctive conditions; being a deployer is a PRECONDITION, not a
    #    trigger (the old `or is_deployer` made the trigger always true).
    is_deployer = (
        role.lower() == "deployer"
        or "deployer" in low
        or "we deploy" in low
        or "we use" in low
    )
    #    (2) Annex III point 2 (critical infrastructure) is carved out.
    is_excluded_area = detected_category in _ART27_EXCLUDED_CATEGORIES
    #    (3a) public-law body / private provider of public services.
    is_public_deployer = any(t in low for t in _ART27_PUBLIC_DEPLOYER_PATTERNS)
    #    (3b) Annex III 5(b) creditworthiness or 5(c) life/health insurance —
    #         in scope whoever the deployer is.
    is_annex_iii_5bc = any(t in low for t in _ART27_ANNEX_III_5BC_PATTERNS)

    fria_required = bool(
        is_annex_iii
        and is_deployer
        and not is_excluded_area
        and (is_public_deployer or is_annex_iii_5bc)
    )

    # 3. Get mapped Charter Articles
    if is_annex_iii and detected_category:
        charter_ids = _ANNEX_III_CHARTER_MAP.get(detected_category, ("Charter Art. 1", "Charter Art. 7", "Charter Art. 8", "Charter Art. 21"))
    else:
        charter_ids = ()

    charter_articles = tuple(CHARTER_CATALOG[cid] for cid in charter_ids if cid in CHARTER_CATALOG)
    impacted_rights = tuple(f"{art.article_id} ({art.title})" for art in charter_articles)

    # 4. Generate recommended actions for Article 27 compliance
    recommended: list[str] = []
    if fria_required:
        # Every citation below is verbatim-checked against the pinned official
        # text via app.data.provision_text.get_provision_text (hard rule #4).
        recommended.append(
            "Perform the fundamental rights impact assessment before deploying the "
            "system (Article 27(1))."
        )
        recommended.append(
            "Cover all six elements: the deployer's processes, the period and "
            "frequency of intended use, the categories of natural persons and "
            "groups affected, the specific risks of harm, the human oversight "
            "measures implemented, and the measures to take if those risks "
            "materialise including internal governance and complaint mechanisms "
            "(Article 27(1)(a) to (f))."
        )
        # R321 — was cited as Article 27(2). Verbatim Article 27(3): "Once the
        # assessment ... has been performed, the deployer shall notify the market
        # surveillance authority of its results". Article 27(2) is the first-use /
        # reuse / update rule, not the notification duty.
        recommended.append(
            "Notify the market surveillance authority of the results, submitting "
            "the filled-out template, unless exempt under Article 46(1) "
            "(Article 27(3))."
        )
        recommended.append(
            "The obligation attaches to the first use; a previously conducted "
            "assessment may be relied on in similar cases, and must be updated "
            "when any element is no longer up to date (Article 27(2))."
        )
        recommended.append(
            "Where a data protection impact assessment under Article 35 of "
            "Regulation (EU) 2016/679 already meets any of these obligations, the "
            "fundamental rights impact assessment complements it (Article 27(4))."
        )

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
