"""Round 69 — Structured query payload (proposed architecture, Section 3A).

The proposed Hybrid-RAG "Semantic Layer" parses a raw question into a
structured intent payload:

    {target_actor, actor_location, market_location, ai_application,
     implied_risk_level, legal_concept_sought}

The codebase already extracts intent (a 15-way label —
``app/llm/intent_classifier.py``), a primary anchor, a risk context and,
on the scenario path, an operator role. The audit found two genuinely
missing dimensions: ``actor_location`` (is the operator inside or
outside the EU?) and ``market_location`` (where is the system placed on
the market?) — the extraterritorial axis the EU AI Act's Article 2
scope turns on, never elevated into a structured field anywhere.

This module is a pure-deterministic extractor for the full payload. It
feeds a one-line ``QUERY PROFILE`` hint into the Stage-2 generation
context — additive, Stage-2-only, so it cannot move a davidath rubric
axis (the deterministic bench never runs Stage-2). It exists to sharpen
cross-border / role-ambiguity answers, which the V2 live probe set
measures and davidath does not.

Pure stdlib. No I/O, no LLM call, no new pip deps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "StructuredQuery",
    "analyse_query",
    "profile_line",
]


@dataclass(frozen=True)
class StructuredQuery:
    """The proposal's Section 3A structured query payload.

    Every field is ``""`` when the deterministic extractor finds no
    confident signal — the profile hint then simply omits that line.
    """

    target_actor: str = ""        # provider | deployer | importer | …
    actor_location: str = ""      # non-EU | EU
    market_location: str = ""     # EU | non-EU
    ai_application: str = ""      # short application-domain label
    implied_risk_level: str = ""  # prohibited | high-risk | limited | …
    legal_concept: str = ""       # short legal-concept label

    def is_empty(self) -> bool:
        return not any(
            (
                self.target_actor,
                self.actor_location,
                self.market_location,
                self.ai_application,
                self.implied_risk_level,
                self.legal_concept,
            )
        )


# ──────────────────────────────────────────────────────────────────────────
# Detection tables — ordered; first match wins within each dimension.
# ──────────────────────────────────────────────────────────────────────────


# target_actor — the EU AI Act operator roles (Art. 3 definitions).
_ACTOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("authorised representative",
     re.compile(r"\bauthoris?ed\s+representative", re.IGNORECASE)),
    ("provider", re.compile(r"\bprovid(?:er|ers|e|ing)\b", re.IGNORECASE)),
    ("deployer", re.compile(r"\bdeploy(?:er|ers|ing|s)?\b", re.IGNORECASE)),
    ("importer", re.compile(r"\bimport(?:er|ers|ing|s)?\b", re.IGNORECASE)),
    ("distributor",
     re.compile(r"\bdistribut(?:or|ors|e|ing)\b", re.IGNORECASE)),
    ("affected person",
     re.compile(r"\baffected\s+person|\bsubject\s+to\s+(?:a\s+)?decision",
                re.IGNORECASE)),
)

# actor_location — is the operator inside or outside the EU?
# A non-EU nationality/country adjective immediately before an operator
# noun ("a US provider", "Chinese AI company") OR an explicit
# outside-the-Union phrase.
_NON_EU_ACTOR_RE = re.compile(
    r"\b(?:non[-\s]?eu|outside\s+the\s+(?:eu|union)|third[-\s]country|"
    r"us[-\s]based|u\.s\.[-\s]?based|based\s+in\s+the\s+us\b|"
    r"established\s+(?:outside|in\s+a\s+third)|"
    r"not\s+established\s+in\s+the\s+(?:eu|union)|"
    r"(?:us|u\.s\.|american|chinese|china|uk|british|japanese|indian|"
    r"canadian|swiss|israeli|korean|singaporean)\s+(?:-?\s*based\s+)?"
    r"(?:ai\s+)?(?:compan|provider|deployer|importer|distributor|firm|"
    r"developer|vendor|start[-\s]?up|tech\b|business|organisation|"
    r"organization))",
    re.IGNORECASE,
)
_EU_ACTOR_RE = re.compile(
    r"\b(?:eu[-\s]based|established\s+in\s+the\s+(?:eu|union)|"
    r"based\s+in\s+(?:germany|france|spain|italy|ireland|the\s+netherlands))",
    re.IGNORECASE,
)

# market_location — placed on / sold into / used in the Union.
_EU_COUNTRIES = (
    r"france|germany|spain|italy|ireland|the\s+netherlands|netherlands|"
    r"poland|belgium|portugal|austria|sweden|denmark|finland|greece|"
    r"czechia|romania|hungary|the\s+eu|the\s+union|the\s+european\s+union"
)
_EU_MARKET_RE = re.compile(
    r"\b(?:on\s+the\s+(?:eu|union)\s+market|"
    r"placed?\s+on\s+the\s+(?:union|eu)\s+market|"
    r"(?:in|into|across|onto|to)\s+(?:the\s+)?(?:eu\b|union\b|"
    r"european\s+union|" + _EU_COUNTRIES + r"))",
    re.IGNORECASE,
)

# ai_application — domain of use. Annex III-shaped buckets.
_APPLICATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("recruitment & employment",
     re.compile(r"\b(?:recruit|hir(?:e|ing)|cv[-\s]?screen|resume|"
                r"job\s+applicant|employee|hr\s+(?:tool|analytics|system)|"
                r"candidate)", re.IGNORECASE)),
    ("creditworthiness & credit scoring",
     re.compile(r"\b(?:credit\s*(?:worth|scor|risk)|loan\s+(?:approv|elig)|"
                r"creditworthiness)", re.IGNORECASE)),
    ("biometric identification",
     re.compile(r"\b(?:biometric|facial\s+recognition|face\s+recognition|"
                r"remote\s+identif)", re.IGNORECASE)),
    ("emotion recognition",
     re.compile(r"\bemotion(?:al)?\s+recognition|\bemotion\s+detect",
                re.IGNORECASE)),
    ("medical & health",
     re.compile(r"\b(?:medical\s+device|diagnos|health(?:care)?|"
                r"patient|clinical)", re.IGNORECASE)),
    ("education & vocational training",
     re.compile(r"\b(?:education|student|exam|admission|vocational\s+train|"
                r"grading)", re.IGNORECASE)),
    ("law enforcement",
     re.compile(r"\b(?:law\s+enforcement|police|predictive\s+polic|"
                r"criminal\s+(?:risk|justice))", re.IGNORECASE)),
    ("critical infrastructure",
     re.compile(r"\bcritical\s+infrastructure|\b(?:water|gas|electricity)"
                r"\s+supply", re.IGNORECASE)),
    ("deepfakes & synthetic media",
     re.compile(r"\bdeep[-\s]?fake|\bsynthetic\s+(?:media|content)|"
                r"\bgenerat(?:e|es|ed)\s+.{0,20}(?:image|audio|video)",
                re.IGNORECASE)),
    ("general-purpose AI model",
     re.compile(r"\b(?:general[-\s]purpose\s+ai|gpai|foundation\s+model|"
                r"large\s+language\s+model)", re.IGNORECASE)),
    ("conversational AI",
     re.compile(r"\b(?:chatbot|conversational\s+ai|customer[-\s]service\s+ai|"
                r"virtual\s+assistant)", re.IGNORECASE)),
)

# implied_risk_level.
_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prohibited",
     re.compile(r"\b(?:prohibit|banned|unacceptable\s+risk|"
                r"social\s+scoring|subliminal)", re.IGNORECASE)),
    ("high-risk",
     re.compile(r"\bhigh[-\s]risk\b", re.IGNORECASE)),
    ("GPAI",
     re.compile(r"\b(?:general[-\s]purpose\s+ai|gpai|systemic\s+risk)",
                re.IGNORECASE)),
    ("limited-risk / transparency",
     re.compile(r"\b(?:limited\s+risk|specific\s+transparency)",
                re.IGNORECASE)),
    ("minimal-risk",
     re.compile(r"\bminimal\s+risk\b", re.IGNORECASE)),
)

# legal_concept_sought — the obligation/concept the question targets.
_CONCEPT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("data & data governance",
     re.compile(r"\bdata\s+governance|\btraining\s+data\s+(?:quality|"
                r"requirement)", re.IGNORECASE)),
    ("human oversight",
     re.compile(r"\bhuman\s+oversight", re.IGNORECASE)),
    ("technical documentation",
     re.compile(r"\btechnical\s+documentation|\bannex\s+iv", re.IGNORECASE)),
    ("transparency obligations",
     re.compile(r"\btransparency", re.IGNORECASE)),
    ("conformity assessment",
     re.compile(r"\bconformity\s+assessment|\bce\s+mark", re.IGNORECASE)),
    ("risk-management system",
     re.compile(r"\brisk[-\s]management\s+system", re.IGNORECASE)),
    ("record-keeping & logging",
     re.compile(r"\b(?:record[-\s]keeping|logging|logs\b)", re.IGNORECASE)),
    ("post-market monitoring",
     re.compile(r"\bpost[-\s]market\s+monitor", re.IGNORECASE)),
    ("registration in the EU database",
     re.compile(r"\b(?:eu\s+database|register(?:ed|ing|ation)?\b)",
                re.IGNORECASE)),
    ("fundamental-rights impact assessment",
     re.compile(r"\b(?:fundamental[-\s]rights\s+impact|fria)\b",
                re.IGNORECASE)),
    ("penalties & fines",
     re.compile(r"\b(?:penalt|fine[sd]?\b|sanction)", re.IGNORECASE)),
    ("accuracy, robustness & cybersecurity",
     re.compile(r"\b(?:accuracy|robustness|cybersecurity|cyber\s+resilien)",
                re.IGNORECASE)),
)


def _first_match(
    text: str, table: tuple[tuple[str, re.Pattern[str]], ...]
) -> str:
    for label, pattern in table:
        if pattern.search(text):
            return label
    return ""


def analyse_query(question: str) -> StructuredQuery:
    """Extract the structured query payload from a raw question.

    Pure-deterministic — regex/keyword detection over each of the six
    dimensions. Every dimension defaults to ``""`` when no confident
    signal is found. Never raises.
    """
    q = (question or "").strip()
    if not q:
        return StructuredQuery()

    actor_location = ""
    if _NON_EU_ACTOR_RE.search(q):
        actor_location = "non-EU"
    elif _EU_ACTOR_RE.search(q):
        actor_location = "EU"

    market_location = "EU" if _EU_MARKET_RE.search(q) else ""

    return StructuredQuery(
        target_actor=_first_match(q, _ACTOR_PATTERNS),
        actor_location=actor_location,
        market_location=market_location,
        ai_application=_first_match(q, _APPLICATION_PATTERNS),
        implied_risk_level=_first_match(q, _RISK_PATTERNS),
        legal_concept=_first_match(q, _CONCEPT_PATTERNS),
    )


_PROFILE_FIELDS: tuple[tuple[str, str], ...] = (
    ("target_actor", "actor"),
    ("actor_location", "actor location"),
    ("market_location", "market"),
    ("ai_application", "application"),
    ("implied_risk_level", "risk level"),
    ("legal_concept", "concept sought"),
)


def profile_line(sq: StructuredQuery) -> str:
    """Render the payload as a single ``QUERY PROFILE:`` context line.

    Returns ``""`` when the payload is empty — the caller then omits the
    line entirely rather than emitting a blank profile.
    """
    if sq.is_empty():
        return ""
    parts = []
    for attr, label in _PROFILE_FIELDS:
        value = getattr(sq, attr, "")
        if value:
            parts.append(f"{label}={value}")
    if not parts:
        return ""
    return "QUERY PROFILE: " + "; ".join(parts)
