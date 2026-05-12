"""Scope filter for the Regenold ask API.

Pure-functional pre-retrieval gate that refuses to answer questions
that are out-of-scope for the EU AI Act (Regulation 2024/1689). The
engine's KB-fallback path will cheerfully answer ANY question with a
generic "Under the EU AI Act, N compliance dimensions are in scope for
this question..." blurb because every retrieval defaults to
``risk="high"`` and surfaces the full dimension catalog. The filter
catches this BEFORE retrieval so we ship a tailored refusal instead.

Five refusal classes are surfaced (with distinct copy):

* ``other_regulation``    — pure GDPR / HIPAA / CCPA / DMA / DSA / NIST
  / ISO 27001 questions with no AI Act anchor.
* ``non_existent_article``— ``Art. 200``, ``Annex XX``, ``Annex 99``
  references the regulation doesn't have. Refusal copy includes the
  real upper bound (113 articles, 13 annexes) + closest valid
  neighbours so the partner sees an actionable signal.
* ``conversational``      — small talk, greetings, generic-knowledge
  questions ("what's the weather", "capital of France"). Refusal
  copy points the user at the EU AI Act surface.
* ``prompt_injection``    — adversarial inputs aiming to extract the
  system prompt or bypass the scope. The input_validator middleware
  catches the high-severity ones at the front door; this layer adds a
  defensive substring scan for the lower-severity patterns
  (e.g. "ignore previous instructions") that didn't trip the validator.
* ``empty_or_nonsense``   — payload too short or no alphabetic content.

Scope IS-IN-SCOPE rules:

* Mentions an Article number 1-113 OR Annex I-XIII (case-insensitive,
  via :func:`extract_referenced_articles`).
* Mentions any AI Act anchor keyword (deployer / provider / GPAI /
  high-risk / FRIA / Annex III / etc — see :data:`_AI_ACT_ANCHORS`).
* Mentions any compliance-dimension keyword from the KB (transparency,
  data governance, human oversight, robustness, etc).

A question that mentions BOTH an in-scope anchor AND an out-of-scope
regulation (e.g. "Compare GDPR Art. 17 vs EU AI Act Art. 17") stays
in-scope — the AI Act side is answerable, the prompt-tightening rules
the LLM into not authoritatively interpreting GDPR.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.data.article_existence import ARTICLE_EXISTENCE

# ── Refusal classes ──────────────────────────────────────────────────────


class ScopeReason(str, Enum):
    """Why a question is out-of-scope (drives the refusal copy)."""

    IN_SCOPE = "in_scope"
    OTHER_REGULATION = "other_regulation"
    NON_EXISTENT_ARTICLE = "non_existent_article"
    CONVERSATIONAL = "conversational"
    PROMPT_INJECTION = "prompt_injection"
    EMPTY_OR_NONSENSE = "empty_or_nonsense"


@dataclass(frozen=True)
class ScopeVerdict:
    """Result of :func:`classify_scope`.

    ``in_scope`` is the boolean gate the route checks.
    ``reason`` enumerates why the question was rejected (or ``IN_SCOPE``
    if the gate passed). ``evidence`` carries a short human-readable
    explanation that the route can include in the refusal copy + the
    audit chain. ``referenced_articles`` lists every valid Art./Annex
    reference parsed from the question; ``unknown_articles`` lists the
    raw mentions that look like article references but aren't in
    :data:`ARTICLE_EXISTENCE`.
    """

    in_scope: bool
    reason: ScopeReason
    evidence: str = ""
    referenced_articles: tuple[str, ...] = ()
    unknown_articles: tuple[str, ...] = ()


# ── Article reference extraction ─────────────────────────────────────────


# Match `Art. 13`, `Article 13`, `Art 13`, `art.13`, `art 13(1)(a)` etc.
# Also accepts the German "Artikel 13" / French "article 13" form so
# multi-language partial queries land on the right anchor (Regenold's
# audience is EU-wide; partner agents may pass non-English fragments).
# Capture group 1 = the article number (decimal int).
_ARTICLE_REF_RE = re.compile(
    r"\b(?:Art(?:icle|ikel)?\.?)\s*(-?\d+)\b",
    re.IGNORECASE,
)
# Match `Annex IV`, `Annex 99`, `annex iii`, etc. Captures group 1 =
# raw number/Roman text after `Annex `. The validator below interprets
# Roman numerals 1-13 OR Arabic numerals (rejected).
_ANNEX_REF_RE = re.compile(
    r"\bAnnex\s+([IVXLCDMivxlcdm]+|\d{1,3})\b",
    re.IGNORECASE,
)


_ROMAN_NUMERAL_VALUES = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13,
}


def _roman_to_int(s: str) -> int | None:
    """Tiny Roman-numeral validator covering the ranges in the EU AI Act.

    Returns ``None`` when ``s`` is malformed (case-insensitive). Only
    handles values 1-13 — the regulation has 13 annexes; we don't need
    a generic Roman parser.
    """
    return _ROMAN_NUMERAL_VALUES.get(s.lower())


# Patterns that "claim" the next Article reference belongs to a different
# regulation. ``GDPR Article 17`` looks like a valid EU AI Act ref because
# the AI Act has Art. 17 (QMS) — without disambiguation we'd surface QMS
# obligations for a GDPR question. The regex ranges 60 chars before the
# Article token so multi-word framings like ``Compare GDPR with EU AI Act
# Art. 17`` still land correctly (the AI Act mention takes precedence).
#
# Multi-article-tail support (round 3 hardening, eng-review H6):
# ``GDPR Articles 17 and 22`` previously claimed only Art. 17 — Art. 22
# slipped through as a "valid EU AI Act ref" and shipped a confident
# Art. 22 EU-rep answer for a GDPR question. The regex now also claims
# the optional ``\s*(?:and|,|&)\s*\d+`` tail so both numbers land in the
# claimed span.
_OTHER_REGULATION_BEFORE_ARTICLE_RE = re.compile(
    r"(?:GDPR|HIPAA|CCPA|CPRA|DSA|DMA|SOX|GLBA|FERPA|"
    r"general\s+data\s+protection|sarbanes[- ]oxley|"
    r"california\s+consumer\s+privacy|digital\s+(?:markets?|services?)\s+act)"
    r"\s+(?:Art(?:icle)?s?\.?|Annex|Section|§|Sec\.?)\s*"
    r"\d+(?:\s*(?:and|,|&|/|\bor\b)\s*\d+){0,5}",
    re.IGNORECASE,
)


def _claimed_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Pre-scan the text for ``<other-reg-tag>+article`` units.

    Returns a tuple of ``(start, end)`` index pairs. Any article/annex
    reference whose position falls inside one of these spans belongs to
    the OTHER regulation, not the EU AI Act. Pre-scanning once is more
    robust than a per-reference window check — the latter falsely
    claimed ``EU AI Act Art. 17`` when ``GDPR Article 17`` appeared
    earlier in the same text (the window happened to include both).
    """
    return tuple(
        (m.start(), m.end()) for m in _OTHER_REGULATION_BEFORE_ARTICLE_RE.finditer(text)
    )


def _position_in_any_span(pos: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= pos < end for start, end in spans)


def extract_referenced_articles(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Pull every ``Art. N`` / ``Annex X`` reference out of ``text``.

    Returns ``(known, unknown)`` — both are tuples of canonical
    ``Art. N`` / ``Annex X`` forms (catalog form, not the user's spelling).

    * ``known`` rows are present in :data:`ARTICLE_EXISTENCE` AND not
      explicitly tagged with a non-AI-Act regulation prefix
      (``GDPR Art. 17`` → not added to known; only the AI Act side
      counts).
    * ``unknown`` rows look like article references but the regulation
      doesn't have them (e.g. ``Art. 200``, ``Annex XX``, ``Annex 99``).
      The route uses these to drive the ``non_existent_article``
      refusal copy.

    Examples
    --------

    >>> extract_referenced_articles("What does Art. 13 require?")
    (('Art. 13',), ())
    >>> extract_referenced_articles("Summarise Art. 200 and Annex XX.")
    ((), ('Art. 200', 'Annex XX'))
    >>> extract_referenced_articles("Compare Art. 13 with Annex IV(2).")
    (('Annex IV', 'Art. 13'), ())
    >>> # GDPR-prefixed: drops to neither known nor unknown — the
    >>> # other-regulation branch handles the refusal.
    >>> extract_referenced_articles("What does GDPR Article 17 say?")
    ((), ())
    """
    known: list[str] = []
    unknown: list[str] = []
    claimed = _claimed_spans(text)

    for m in _ARTICLE_REF_RE.finditer(text):
        try:
            num = int(m.group(1))
        except (ValueError, TypeError):
            continue
        if _position_in_any_span(m.start(), claimed):
            # Non-AI-Act regulation owns this reference — skip it. The
            # ``other_regulation`` branch in classify_scope picks it up
            # via the regulation-keyword check and ships the right
            # refusal copy.
            continue
        # Round-3 hardening (eng-review H8): capture sub-paragraph
        # chains like ``(2)(c)`` or ``.2.c`` so the anchor carries the
        # full specificity for downstream surfacing. Without this, the
        # deterministic-fallback path emits only the bare article ref
        # (``Art. 13``) even when the user explicitly cited
        # ``Art. 13(1)(a)`` — losing the sub-point in the wire response.
        sub_chain = _capture_subpoint_chain(text, m.end())
        ref = f"Art. {num}{sub_chain}"
        # Existence gate uses bare ref (catalog only stores ``Art. N``);
        # but we PRESERVE the sub-chain on the emitted ref so the route's
        # surfacing path can ship ``Article N.x.y`` not just ``Article N``.
        if f"Art. {num}" in ARTICLE_EXISTENCE:
            if ref not in known:
                known.append(ref)
        else:
            if f"Art. {num}" not in unknown:
                unknown.append(f"Art. {num}")

    for m in _ANNEX_REF_RE.finditer(text):
        if _position_in_any_span(m.start(), claimed):
            continue
        raw = m.group(1)
        # Arabic numeral = always invalid (the regulation uses Roman).
        if raw.isdigit():
            ref = f"Annex {raw}"
            if ref not in unknown:
                unknown.append(ref)
            continue
        roman_int = _roman_to_int(raw)
        if roman_int is None:
            # Not a valid Roman numeral in the 1-13 range — definitely unknown.
            ref = f"Annex {raw.upper()}"
            if ref not in unknown:
                unknown.append(ref)
            continue
        # Reconstruct the canonical Roman form (uppercase) and check the catalog.
        canonical_roman = raw.upper()
        # Round-3 hardening (eng-review H8): same sub-paragraph capture
        # for Annexes — ``Annex IV(2)(c)`` survives intact through the
        # anchor pipeline.
        sub_chain = _capture_subpoint_chain(text, m.end())
        ref = f"Annex {canonical_roman}{sub_chain}"
        bare = f"Annex {canonical_roman}"
        if bare in ARTICLE_EXISTENCE:
            if ref not in known:
                known.append(ref)
        else:
            if bare not in unknown:
                unknown.append(bare)

    # Sort known refs for deterministic output (Article first by number, then Annex by Roman).
    return tuple(sorted(known, key=_sort_key)), tuple(unknown)


# Sub-paragraph capture regex used by `extract_referenced_articles` to
# preserve specificity on extracted refs. Matches a chain of ``(N)`` /
# ``(a)`` / ``.N`` / ``.a`` segments immediately after an article or
# annex token. Whitespace between segments is allowed (typed users
# sometimes write ``Art. 13 (1) (a)``). Non-greedy on segment count to
# avoid over-consuming into the next sentence.
_SUBPOINT_CHAIN_RE = re.compile(
    r"^(?:\s*\(\s*[A-Za-z0-9]+\s*\)){0,5}",
)


def _capture_subpoint_chain(text: str, start_pos: int) -> str:
    """Capture an ``(N)(a)`` / ``.N.a`` chain starting at ``start_pos``.

    Returns either an empty string (no chain found) or the captured
    chain in canonical paren form (e.g. ``"(2)(c)"``). Used to preserve
    sub-paragraph specificity on extracted article + annex anchors so
    the wire response surfaces ``Article 13.1.a`` instead of degrading
    to ``Article 13``.

    Round-3 hardening (eng-review H8): the LatticeFlow Atlas Article 15
    decomposition ships paragraph anchors in ``15(1)`` / ``15(2)`` /
    ``15(4)`` / ``15(5)`` form, and Regenold-spec output requires
    ``Article 13.1.a`` / ``Annex IV.2.c`` shapes — both rely on the
    sub-chain surviving anchor extraction.
    """
    if start_pos >= len(text):
        return ""
    tail = text[start_pos:start_pos + 64]  # bounded — annex chains rarely exceed 16 chars
    m = _SUBPOINT_CHAIN_RE.match(tail)
    if not m or not m.group(0).strip():
        return ""
    # Normalise: extract every ``[A-Za-z0-9]+`` token from the matched
    # span and re-emit as canonical paren-form ``(N)(a)``.
    tokens = re.findall(r"[A-Za-z0-9]+", m.group(0))
    if not tokens:
        return ""
    # Discard the entire chain when ANY numeric token is out of the plausible
    # EU AI Act sub-paragraph range (≤ 20). "(z)(99)" has "99" → clearly
    # fabricated; "(2)(c)" has "2" → real. This prevents user-planted bogus
    # sub-refs like "Art. 47(z)(99)" from anchoring as "Article 47.z.99" in
    # the wire response while preserving legitimate deep refs like Annex IV(2)(c).
    if any(t.isdigit() and int(t) > 20 for t in tokens):
        return ""
    return "".join(f"({t})" for t in tokens)


def _sort_key(ref: str) -> tuple[int, int]:
    """Sort key for ``Art. N`` / ``Annex X``: Annex first, then by number."""
    if ref.startswith("Annex "):
        roman = ref[len("Annex ") :]
        return (0, _roman_to_int(roman) or 99)
    if ref.startswith("Art. "):
        try:
            return (1, int(ref[len("Art. ") :]))
        except ValueError:
            return (1, 99)
    return (2, 0)


# ── Out-of-scope keyword sets ────────────────────────────────────────────


# Other regulations / frameworks. When ANY of these is present AND no
# AI Act anchor is present, classify as ``other_regulation``. Patterns
# match whole-word so "GDPR" matches but "AGDPR" doesn't. "AI Act"
# itself is treated as an anchor below.
_OTHER_REGULATION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bGDPR\b", re.IGNORECASE),
    re.compile(r"\bgeneral\s+data\s+protection\s+regulation\b", re.IGNORECASE),
    re.compile(r"\bHIPAA\b", re.IGNORECASE),
    re.compile(r"\bCCPA\b", re.IGNORECASE),
    re.compile(r"\bcalifornia\s+consumer\s+privacy\b", re.IGNORECASE),
    re.compile(r"\bCPRA\b", re.IGNORECASE),
    re.compile(r"\bDigital\s+Markets?\s+Act\b", re.IGNORECASE),
    re.compile(r"\bDigital\s+Services?\s+Act\b", re.IGNORECASE),
    re.compile(r"\bDMA\b"),
    re.compile(r"\bDSA\b"),
    re.compile(r"\bSOX\b"),
    re.compile(r"\bSarbanes[- ]Oxley\b", re.IGNORECASE),
    re.compile(r"\bGLBA\b"),
    re.compile(r"\bFERPA\b"),
)


# AI Act anchor keywords. ANY of these flips a question into in-scope
# even without an explicit Art./Annex reference. Drawn from the KB
# vocabulary + colloquial AI Act terms.
_AI_ACT_ANCHORS: frozenset[str] = frozenset(
    s.lower().replace("-", " ") for s in (
        # Direct regulation references
        "EU AI Act",
        "AI Act",
        "Regulation 2024/1689",
        "Regulation (EU) 2024/1689",
        "AI regulation",
        # Operator roles (Art. 3 definitions)
        "deployer",
        "provider",
        "importer",
        "distributor",
        "authorised representative",
        "authorized representative",
        # Risk taxonomy (Arts. 5/6)
        "high-risk",
        "high risk",
        "limited-risk",
        "limited risk",
        "minimal risk",
        "minimal-risk",
        "low risk",
        "low-risk",
        "unacceptable risk",
        "prohibited practice",
        "prohibited ai",
        "risk classification",
        "risk classifications",
        "annex iii",
        # Documentation surfaces
        "annex iv",
        "technical documentation",
        "fundamental rights impact assessment",
        "FRIA",
        "conformity assessment",
        "declaration of conformity",
        "post-market monitoring",
        "PMMP",
        # GPAI
        "GPAI",
        "general-purpose ai",
        "general purpose ai",
        "systemic risk",
        "code of practice",
        # Compliance dimensions (KB)
        "data governance",
        "human oversight",
        "transparency obligation",
        "transparency requirement",
        "record-keeping",
        "record keeping",
        "logging",
        "robustness",
        "cybersecurity",
        "quality management",
        "QMS",
        "harmonised standard",
        "harmonized standard",
        # Sector triggers
        "biometric categorisation",
        "biometric categorization",
        "remote biometric",
        "social scoring",
        "emotion recognition",
        # Misc
        "AI literacy",
        "fundamental rights",
        "notified body",
        "CE marking",
        "EU database",
        "serious incident",
        "incident",  # broader than "serious incident" — caught when phrasing splits
        # ── Round-2 expansion (Regenold competition coverage) ────────
        # Additional anchors so the in-scope check fires on questions
        # that don't carry an explicit Art./Annex token but DO mention
        # an AI Act surface.
        "deepfake",
        "ai-generated",
        "synthetic content",
        "watermarking",
        "extraterritorial",
        "extraterritoriality",
        "research and development",
        "regulatory sandbox",
        "real-world testing",
        "real world testing",
        "military",
        "defence",
        "defense",
        "law enforcement exemption",
        "national security",
        "substantial modification",
        "substantial modifications",
        "fine-tune",
        "fine-tuned",
        "fine-tuning",
        "fine tune",
        "fine tuning",
        "harmonised standards",
        "harmonized standards",
        "presumption of conformity",
        "ai office",
        "european ai board",
        "market surveillance",
        "value chain",
        "downstream provider",
        "open-weights",
        "open weights",
        "ai system",  # weak anchor; only fires when the question doesn't already trip a stronger one
        "ai tool",
        "ai application",
        "ai applications",
        "ai-system",
        "ai model",
        "ai models",
        # Vendor / procurement context — "third-party HR-screening AI" and
        # similar buy/vendor framings are core deployer scenarios under Art. 26.
        "third party ai",
        "third-party ai",
        "screening ai",
        "scoring ai",
        "ai vendor",
        "ai supplier",
        "buy ai",
        "buy an ai",
        "buying ai",
        "in scope",  # "Is X in scope of the regulation?" — scope-of-regulation framing
        "scope of",
        "ai act",  # final catch — most direct possible regulatory anchor
        "high-risk ai",
        "high risk ai",
        "general purpose ai model",
        "general-purpose ai model",
        # ── Round-10 anchor surfacing (stress-test gap closers) ─────────
        # Prohibited-practice + Annex-III concept phrases that ought to
        # mark a question as plainly AI-Act-shaped even without an
        # explicit ``Art. 5`` / ``Annex III`` token. Mirrors the
        # KEYWORD_TO_ARTICLE additions made in the same round.
        "facial recognition",
        "facial recognition database",
        "scraping facial",
        "subliminal",
        "manipulative technique",
        "deceptive technique",
        "exploit vulnerabilities",
        "exploit the vulnerabilities",
        "exploits the vulnerabilities",
        "exploiting vulnerabilities",
        "vulnerable groups",
        "csam",
        "ai-generated csam",
        "nudification",
        "non-consensual intimate",
        "intimate imagery",
        "critical infrastructure",
        "asylum",
        "migration",
        "visa application",
        "border control",
        "judicial",
        "court",
        "legal interpretation",
        "election",
        "voting behaviour",
        "voting behavior",
        "essential public services",
        "essential private services",
        "creditworthiness",
        "credit scoring",
        "predictive policing",
        "predicting criminality",
        "criminal risk",
        "criminal-risk",
        "scientific research",
        "research only",
        "research-only",
        "rebrand",
    )
)


# Compliance dimension keywords (broader set — matches the KB labels +
# their plural / verb forms). When NO Article/Annex/anchor is present
# but a dimension keyword is, the question is ambiguous-but-in-scope:
# e.g. "How do I think about transparency?" → in-scope, generic.
# Keyword → canonical Article reference. When a question mentions
# ``FRIA`` / ``GPAI`` / etc. without an explicit ``Art. N`` token, surface
# the canonical EU AI Act article so the citation list is grounded
# rather than empty. The mapping is conservative — we only emit articles
# that are an unambiguous primary anchor for the keyword.
KEYWORD_TO_ARTICLE: dict[str, str] = {
    # Lowercased substrings → canonical Art. ref
    "fria": "Art. 27",
    "fundamental rights impact assessment": "Art. 27",
    "gpai": "Art. 53",
    "general-purpose ai": "Art. 53",
    "general purpose ai": "Art. 53",
    "code of practice": "Art. 56",
    "systemic risk": "Art. 55",
    "annex iv": "Annex IV",
    "annex iii": "Annex III",
    "annex i": "Annex I",
    "annex ii": "Annex II",
    "annex v": "Annex V",
    "annex vi": "Annex VI",
    "annex vii": "Annex VII",
    "annex viii": "Annex VIII",
    "annex ix": "Annex IX",
    "annex x": "Annex X",
    "annex xi": "Annex XI",
    "annex xii": "Annex XII",
    "annex xiii": "Annex XIII",
    "post-market monitoring": "Art. 72",
    "pmmp": "Art. 72",
    "post-market monitoring plan": "Art. 72",
    "ce marking": "Art. 48",
    "declaration of conformity": "Art. 47",
    "eu declaration of conformity": "Art. 47",
    "conformity assessment": "Art. 43",
    "quality management system": "Art. 17",
    "qms": "Art. 17",
    "technical documentation": "Annex IV",
    "human oversight": "Art. 14",
    "data governance": "Art. 10",
    "transparency obligation": "Art. 13",
    "transparency requirement": "Art. 13",
    "record-keeping": "Art. 12",
    "record keeping": "Art. 12",
    "logging": "Art. 12",
    "robustness": "Art. 15",
    "cybersecurity": "Art. 15",
    "accuracy and robustness": "Art. 15",
    "ai literacy": "Art. 4",
    "deployer obligation": "Art. 26",
    "deployer obligations": "Art. 26",
    "importer obligation": "Art. 23",
    "importer obligations": "Art. 23",
    "distributor obligation": "Art. 24",
    "distributor obligations": "Art. 24",
    "provider obligation": "Art. 16",
    "provider obligations": "Art. 16",
    "social scoring": "Art. 5",
    "biometric categorisation": "Art. 5",
    "biometric categorization": "Art. 5",
    "remote biometric": "Art. 5",
    "real-time biometric": "Art. 5",
    "real time biometric": "Art. 5",
    # Bare "biometric identification" anchors Art. 5(1)(h) — real-time
    # remote biometric ID in public spaces by law enforcement is the
    # prohibited practice. Non-real-time / non-public-space variants are
    # high-risk under Annex III(1) but the prohibition is the more
    # specific anchor for verdict-style questions.
    "biometric identification": "Art. 5",
    "emotion recognition": "Art. 5",
    "prohibited practice": "Art. 5",
    # ── Round-10 anchor surfacing (stress-test gap closers) ──────────
    # Each phrase is a real stress-test failure where the question was
    # plainly about an Art. 5 prohibited practice but scope refused as
    # "no anchor". Conservative — each phrase anchors the single
    # article the practice belongs to under Art. 5.
    "facial recognition database": "Art. 5",
    "scraping facial": "Art. 5",
    "scraping of facial": "Art. 5",
    "subliminal technique": "Art. 5",
    "subliminal manipulation": "Art. 5",
    "manipulative technique": "Art. 5",
    "deceptive technique": "Art. 5",
    "exploit vulnerabilities": "Art. 5",
    "exploit the vulnerabilities": "Art. 5",
    "exploiting vulnerabilities": "Art. 5",
    "vulnerable groups": "Art. 5",
    "csam": "Art. 5",
    "ai-generated csam": "Art. 5",
    "ai generated csam": "Art. 5",
    "nudification": "Art. 5",
    "non-consensual intimate": "Art. 5",
    "non consensual intimate": "Art. 5",
    "intimate imagery": "Art. 5",
    # Annex III categories — scope anchors for high-risk verdicts
    "critical infrastructure": "Annex III",
    "asylum application": "Annex III",
    "asylum applications": "Annex III",
    "migration risk": "Annex III",
    "visa application": "Annex III",
    "border control": "Annex III",
    "judicial authority": "Annex III",
    "judicial authorities": "Annex III",
    "assist judges": "Annex III",
    "legal interpretation": "Annex III",
    "election outcome": "Annex III",
    "voting behaviour": "Annex III",
    "voting behavior": "Annex III",
    "essential public services": "Annex III",
    "essential private services": "Annex III",
    "creditworthiness": "Annex III",
    "credit scoring": "Annex III",
    # Content-lookup anchors that the stress test surfaced
    "maximum fine": "Art. 99",
    "max fine": "Art. 99",
    "fine for": "Art. 99",
    "fine ceiling": "Art. 99",
    "definition of an ai system": "Art. 3",
    "definition of ai system": "Art. 3",
    "definition of a deployer": "Art. 3",
    "definition of a provider": "Art. 3",
    "definition of a general-purpose": "Art. 3",
    "definition of general-purpose": "Art. 3",
    "definition of a gpai": "Art. 3",
    "definition of high-risk": "Art. 6",
    "research-only": "Art. 2",
    "research only ai": "Art. 2",
    "scientific research": "Art. 2",
    "rebrand": "Art. 25",
    "rename": "Art. 25",
    "third-party ai": "Art. 25",
    "third party ai": "Art. 25",
    "prohibited ai": "Art. 5",
    "prohibited practices": "Art. 5",
    "high-risk ai system": "Art. 6",
    "high-risk classification": "Art. 6",
    "serious incident": "Art. 73",
    "notified body": "Art. 31",
    "eu database": "Art. 71",
    # ── Orphan-article anchors (this PR — Regenold round 2) ──────────
    # Articles that previously had no keyword path so a question that
    # didn't carry an explicit `Art. N` token would fall through to the
    # LLM with no defensive citation. The mapping is conservative — each
    # phrase maps to the ONE article it's the unambiguous primary anchor
    # for; broader-meaning phrases stay unmapped to avoid mis-anchoring.
    "scope of the regulation": "Art. 2",
    "extraterritorial": "Art. 2",
    "extraterritoriality": "Art. 2",
    # NOTE: bare "definitions" removed — too generic (e.g. "what
    # definitions does Art. 26 use?" is about Art. 26, not Art. 3).
    # Compound forms below stay because they unambiguously target Art. 3.
    "substantial modification": "Art. 3",
    "ai system definition": "Art. 3",
    "definition of ai": "Art. 3",
    "risk management system": "Art. 9",
    "risk management": "Art. 9",
    "data and data governance": "Art. 10",
    "training data": "Art. 10",
    "test data": "Art. 10",
    "validation data": "Art. 10",
    "data quality": "Art. 10",
    "automatic logging": "Art. 12",
    "instructions for use": "Art. 13",
    "instructions of use": "Art. 13",
    "accuracy metrics": "Art. 15",
    "value chain": "Art. 25",
    "rebrand": "Art. 25",
    "third-party provider": "Art. 25",
    "third party provider": "Art. 25",
    "deployer information": "Art. 26",
    "automated logs": "Art. 26",
    "informed consent": "Art. 26",
    "registration": "Art. 49",
    "deepfake": "Art. 50",
    "ai-generated content": "Art. 50",
    "ai generated content": "Art. 50",
    "synthetic content": "Art. 50",
    "watermarking": "Art. 50",
    "chatbot disclosure": "Art. 50",
    "transparency for users": "Art. 50",
    "10^25": "Art. 51",
    "10²⁵": "Art. 51",
    "flops threshold": "Art. 51",
    "systemic risk threshold": "Art. 51",
    "designation": "Art. 51",
    "model documentation": "Art. 53",
    "downstream provider": "Art. 53",
    "open-source": "Art. 53",
    "open source ai": "Art. 53",
    "model evaluation": "Art. 55",
    "regulatory sandbox": "Art. 57",
    "real-world testing": "Art. 60",
    "real world testing": "Art. 60",
    "ai office": "Art. 64",
    "european ai board": "Art. 65",
    "national competent authority": "Art. 70",
    "market surveillance": "Art. 74",
    "withdrawal": "Art. 79",
    "fines": "Art. 99",
    "penalties": "Art. 99",
    "penalty": "Art. 99",
    "applicable date": "Art. 113",
    "entry into force": "Art. 113",
    "entry into application": "Art. 113",
    "compliance deadline": "Art. 113",
    "harmonised standard": "Art. 40",
    "harmonized standard": "Art. 40",
    "presumption of conformity": "Art. 40",
    "common specification": "Art. 41",
    "fundamental rights": "Art. 27",
    "annex iv documentation": "Annex IV",
    "technical file": "Annex IV",
    # ── Round-2 anchor surfacing (Regenold competition gap-closers) ──
    # Each phrase below was a real eval failure — the question passed
    # scope but didn't surface a defensive citation because no keyword
    # matched. Conservative: each phrase maps to its UNAMBIGUOUS
    # primary article. The substring-shadowing guard means longer
    # phrases above still win where they overlap (e.g. "fine-tuning"
    # with "training data" — different anchors, no overlap).
    "high-risk": "Art. 6",
    "high risk": "Art. 6",
    "deploy a third-party": "Art. 26",
    "deploy a third party": "Art. 26",
    # NOTE: bare "deploys" / "deploying" removed — too generic
    # (e.g. "We deploy our model to AWS — does Art. 11 apply?" is
    # about Art. 11, not Art. 26). The compound forms above stay.
    "deploy a high-risk": "Art. 26",
    "deploy a high risk": "Art. 26",
    "fine-tune": "Art. 25",
    "fine-tuned": "Art. 25",
    "fine-tuning": "Art. 25",
    "fine tune": "Art. 25",
    "fine tuning": "Art. 25",
    "obligations apply": "Art. 113",
    "obligation apply": "Art. 113",
    # NOTE: "applicable" / "applies on" / "in scope" / "definition" /
    # "definitions" alone are too generic — they appear in legitimate
    # questions about completely different articles (e.g. "Is Art. 26
    # applicable to a deployer?", "What is the definition of high-risk
    # under Art. 6?") and would surface Art. 113 / Art. 3 as spurious
    # defensive citations, polluting Regenold's "minimal set" reference
    # spec. Removed in the round-3 hardening pass after eng-review.
    # The compound forms upstream ("compliance deadline" / "entry into
    # force" / "applicable date") stay — they're scoped enough to
    # disambiguate.
    "applicable from": "Art. 113",
    "defence": "Art. 2",
    "defense": "Art. 2",
    "military": "Art. 2",
    "national security": "Art. 2",
    "research and development": "Art. 2",
    "r&d": "Art. 2",
    "personal use": "Art. 2",
    "non-professional": "Art. 2",
    # NOTE: bare "definition" / "definition of" removed — too generic.
    # The compound "definition of ai" / "ai system definition" / "ai act
    # definition" stay because they unambiguously target Art. 3.
    "ai act definition": "Art. 3",
    "is defined under": "Art. 3",
    "deep fake": "Art. 50",
    "ai-generated": "Art. 50",
    "ai generated": "Art. 50",
    "label ai": "Art. 50",
    # NOTE: bare "incident" removed — too generic (e.g. "we had a
    # production incident with Art. 26 logging" is about Art. 26, not
    # Art. 73). The compound forms below stay because they unambiguously
    # target Art. 73 serious-incident reporting.
    "report an incident": "Art. 73",
    "serious ai incident": "Art. 73",
    "incident reporting": "Art. 73",
    "incident notification": "Art. 73",
    # NOTE: bare "in scope" removed — too generic. Most "in scope"
    # questions are about WHICH article applies, not Art. 6 specifically.
    "is it high-risk": "Art. 6",
    "is it high risk": "Art. 6",
    # Education / employment / law-enforcement / biometrics — Annex III triggers
    "grades student": "Annex III",
    "grades students": "Annex III",
    "student grading": "Annex III",
    "essay grading": "Annex III",
    "education grading": "Annex III",
    "credit scoring": "Annex III",
    "cv screening": "Annex III",
    "cv-screening": "Annex III",
    "resume screening": "Annex III",
    "candidate screening": "Annex III",
    "hr screening": "Annex III",
    # Predictive policing: Art. 5(1)(d) PROHIBITS profiling-based predictive
    # policing of natural persons; only place-based / non-profiling
    # predictive policing falls under Annex III(6)(d). Anchor on the
    # prohibition first — Annex III routing was misleading users into
    # thinking such systems were merely "high-risk" rather than banned.
    "predictive policing": "Art. 5",
    # GPAI numerical anchors
    "10 to the 25": "Art. 51",
    "1e25": "Art. 51",
    "ten to the": "Art. 51",
    # ── Round-8 anchor surfacing (Regenold sycophancy / leading-premise
    # gap-closers). Each phrase below is a real eval failure where the
    # question carried in-scope signal but no concrete article anchor.
    "minimal risk": "Art. 6",
    "low risk": "Art. 6",
    "risk classification": "Art. 6",
    "chatbot": "Art. 50",
    "subject to the ai act": "Art. 2",
    "subject to the act": "Art. 2",
    "subject to the regulation": "Art. 2",
    "us company": "Art. 2",
    "no eu office": "Art. 2",
    "no eu users": "Art. 2",
    "internal use": "Art. 2",
    "deploy internally": "Art. 26",
    "vendor takes": "Art. 26",
    "vendor liability": "Art. 26",
    "buy a third party": "Art. 26",
    "buy a third party ai": "Art. 26",
    "third party ai": "Art. 26",
    "medical device": "Art. 6",
    "diagnostic ai": "Art. 6",
    # NB: "linear regression" / "weighted score" / "weighted score
    # calculator" / "ec faq" / "european commission faq" removed —
    # algorithm class and meta-document phrases do not determine risk
    # class. A linear regression is high-risk only if its USE CASE is
    # in Annex I/III; anchoring the keyword without that context made
    # the engine assert Art. 6 applicability for any mention of these
    # techniques. The "ec faq" entries were over-eager catches on
    # documents-as-source, not regulatory anchors.
    "wrapper": "Art. 25",
    # ── Round-9 anchor surfacing (May 2026 KB expansion + Digital Omnibus) ──
    # Articles added in this round: 21, 50.1-4, 58, 59, 61-63, 67-69, 85-87,
    # 89, 95, 100, 101, 111, 112. Plus Digital Omnibus political-agreement
    # context. Keywords map to the UNAMBIGUOUS primary article each phrase
    # uniquely anchors. Overlap-resolved by length-DESC sort in the regex.
    # Art. 21 — cooperation duty
    "cooperate with national": "Art. 21",
    "cooperation with national": "Art. 21",
    "cooperate with the authorities": "Art. 21",
    "supply to a national competent": "Art. 21",
    "supply to a competent authority": "Art. 21",
    "must a provider supply": "Art. 21",
    "must provide to a competent": "Art. 21",
    "reasoned request": "Art. 21",
    # Art. 6(3) carve-out
    "non-high-risk exception": "Art. 6",
    "non high risk exception": "Art. 6",
    "narrow procedural task": "Art. 6",
    "preparatory task": "Art. 6",
    # Sandbox detail (Arts. 58, 59, 61, 62, 63)
    "sandbox modalities": "Art. 58",
    "personal data in a sandbox": "Art. 59",
    "personal data inside an ai": "Art. 59",
    "sandbox without gdpr": "Art. 59",
    "consent for real-world testing": "Art. 61",
    "consent for real world testing": "Art. 61",
    "sme support": "Art. 62",
    "small mid-cap": "Art. 62",
    "small mid cap": "Art. 62",
    "smc": "Art. 62",
    "startup support": "Art. 62",
    "start-up support": "Art. 62",
    "sme derogation": "Art. 63",
    # Governance bodies (Arts. 67-69)
    "advisory forum": "Art. 67",
    "scientific panel": "Art. 68",
    "expert pool": "Art. 69",
    # Remedies (Arts. 85, 86, 87, 89)
    "right to lodge a complaint": "Art. 85",
    "right to complain": "Art. 85",
    "lodge a complaint": "Art. 85",
    "can complain": "Art. 85",
    "complain about an ai": "Art. 85",
    "complain about the ai act": "Art. 85",
    "right to explanation": "Art. 86",
    "right to an explanation": "Art. 86",
    "explanation of the decision": "Art. 86",
    "ai-driven decision": "Art. 86",
    "ai driven decision": "Art. 86",
    "whistleblower": "Art. 87",
    "whistleblowing": "Art. 87",
    "downstream-provider complaint": "Art. 89",
    "complaint to ai office": "Art. 89",
    # Codes of conduct (Art. 95)
    "voluntary code of conduct": "Art. 95",
    "code of conduct": "Art. 95",
    "codes of conduct": "Art. 95",
    # Penalties (Arts. 100, 101)
    "edps fine": "Art. 100",
    "edps penalties": "Art. 100",
    "edps penalty": "Art. 100",
    "penalties for eu institutions": "Art. 100",
    "fines on eu institutions": "Art. 100",
    "fines for eu institutions": "Art. 100",
    "fines apply to eu institutions": "Art. 100",
    "fines for eu bodies": "Art. 100",
    "gpai penalty": "Art. 101",
    "gpai fine": "Art. 101",
    "penalty on a gpai": "Art. 101",
    "penalty on gpai": "Art. 101",
    "commission impose on a gpai": "Art. 101",
    "commission impose on gpai": "Art. 101",
    # Transition + review (Arts. 111, 112)
    "transitional provision": "Art. 111",
    "pre-existing high-risk": "Art. 111",
    "pre-existing ai system": "Art. 111",
    "review of the regulation": "Art. 112",
    "review the eu ai act": "Art. 112",
    "review of the eu ai act": "Art. 112",
    "evaluation of the regulation": "Art. 112",
    "commission review": "Art. 112",
    "commission evaluation": "Art. 112",
    "review clause": "Art. 112",
    # Art. 113 "when will X become subject" routing (round 9.1 hotfix)
    "become subject to obligations": "Art. 113",
    "become subject to the obligations": "Art. 113",
    "when will the obligations": "Art. 113",
    "when will high-risk": "Art. 113",
    "when will high risk": "Art. 113",
    "when does annex iii apply": "Art. 113",
    # Art. 51 GPAI threshold variants (round 9.1 hotfix)
    "threshold makes a gpai": "Art. 51",
    "threshold for systemic risk": "Art. 51",
    "what threshold makes": "Art. 51",
    "training flops": "Art. 51",
    # Annex II / V / VIII anchors
    "criminal offences": "Annex II",
    "annex ii offences": "Annex II",
    "declaration of conformity contents": "Annex V",
    "contents of declaration of conformity": "Annex V",
    "contents of the declaration": "Annex V",
    "must the eu declaration": "Annex V",
    "must the declaration of conformity": "Annex V",
    "must be registered in the eu": "Annex VIII",
    "registration information": "Annex VIII",
    "eu ai database": "Annex VIII",
    "information must be registered": "Annex VIII",
    "registered in the eu ai database": "Annex VIII",
    # Digital Omnibus (May 2026 political agreement)
    "digital omnibus": "Art. 113",
    "2 december 2027": "Art. 113",
    "2 august 2028": "Art. 113",
    "ai-generated csam": "Art. 5",
    "ai csam": "Art. 5",
    "non-consensual intimate": "Art. 5",
    "non consensual intimate": "Art. 5",
    "nudification": "Art. 5",
    "intimate imagery": "Art. 5",
}


# Pre-compiled regex alternation over every keyword in KEYWORD_TO_ARTICLE.
# Built once at module load — replaces the previous per-call sort + O(N*M)
# substring scan loop. ``re.finditer`` walks the input once; the
# alternation's left-to-right semantics combined with sorting keywords by
# length DESC give us the same substring-shadowing guarantee (longer
# phrases win on overlapping spans because re.finditer advances past
# the matched span before considering the next match).
#
# Eng-review round-6 perf finding: parent CLAUDE.md flagged the O(N*M)
# walk as a deferred optimisation. Closed here.
_NORMALIZED_KEYWORD_TO_ARTICLE: dict[str, str] = {
    k.replace("-", " "): v for k, v in KEYWORD_TO_ARTICLE.items()
}
_KEYWORD_ALTERNATION_RE = re.compile(
    "(" + "|".join(
        re.escape(k)
        for k in sorted(_NORMALIZED_KEYWORD_TO_ARTICLE.keys(), key=len, reverse=True)
    ) + ")",
    re.IGNORECASE,
)


def derive_anchor_articles_from_keywords(text: str) -> tuple[str, ...]:
    """Map well-known anchor keywords (FRIA, GPAI, …) to canonical refs.

    Returns a tuple of ``Art. N`` / ``Annex X`` strings (catalog form),
    in stable insertion order. Empty when no keyword matches.

    Used by :func:`classify_conversation` to surface anchor articles
    even when the question doesn't carry an explicit Article number —
    so a question like ``"Do I need a FRIA?"`` produces ``Art. 27`` as
    a defensive citation in the route's response.

    Substring-shadowing: longer keywords win on overlapping spans because
    the pre-compiled alternation is sorted DESC by keyword length and
    ``re.finditer`` advances past each matched span. ``"Summarise Annex
    IV"`` matches only ``annex iv``, never the shorter ``annex i`` that
    sits inside it.
    """
    if not text:
        return ()
    out: list[str] = []
    seen: set[str] = set()
    # Normalize hyphens to spaces so "HR-screening" matches "hr screening".
    # The keyword regex and lookup dict have been pre-normalized to match.
    norm = text.lower().replace("-", " ")
    for m in _KEYWORD_ALTERNATION_RE.finditer(norm):
        ref = _NORMALIZED_KEYWORD_TO_ARTICLE.get(m.group(0))
        if ref and ref in ARTICLE_EXISTENCE and ref not in seen:
            seen.add(ref)
            out.append(ref)
    return tuple(out)


_DIMENSION_KEYWORDS: frozenset[str] = frozenset(
    s.lower().replace("-", " ") for s in (
        "transparency",
        "transparent",
        "explainability",
        "explainable",
        "interpretability",
        "data quality",
        "training data",
        "test data",
        "validation data",
        "bias",
        "fairness",
        "discrimination",
        "accuracy",
        "robustness",
        "adversarial",
        "human oversight",
        "human-in-the-loop",
        "audit trail",
    )
)


# Conversational fillers. Match start-of-text or a short standalone
# phrase. Combined with the no-anchor rule below to fire only on
# pure-filler questions ("Hi how are you?"), not on filler-prefixed
# real questions ("Hi, what does Art. 13 require?" → in-scope).
_CONVERSATIONAL_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|greetings)\b[!?.,]*\s*",
               re.IGNORECASE),
    re.compile(r"^\s*(thanks|thank\s+you|cheers|ty)\b[!?.,]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(bye|goodbye|see\s+you|see\s+ya)\b[!?.,]*\s*$", re.IGNORECASE),
    re.compile(r"^\s*(how\s+are\s+you|how\s+r\s+u|sup|what's\s+up)\b", re.IGNORECASE),
    re.compile(r"^\s*(who\s+are\s+you|what\s+can\s+you\s+do)\b", re.IGNORECASE),
)

# Generic-knowledge / off-topic question stems with no AI Act content.
_GENERIC_KNOWLEDGE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\b(weather|temperature)\b", re.IGNORECASE),
    re.compile(r"\bcapital\s+of\s+\w+", re.IGNORECASE),
    re.compile(r"\bjoke\b", re.IGNORECASE),
    re.compile(r"\bpoem\b", re.IGNORECASE),
    re.compile(r"\brecipe\b", re.IGNORECASE),
    re.compile(r"\b(write|generate|compose)\s+(?:me\s+)?(?:a\s+)?(?:song|poem|story|haiku|essay)\b",
               re.IGNORECASE),
)

# Prompt-injection patterns the input_validator middleware doesn't catch
# (lower severity / broader phrasing). The validator's high-severity
# tier blocks the heavy artillery; this layer is the last-mile mop-up.
_INJECTION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bignore\s+(?:all\s+|the\s+|your\s+|previous\s+|prior\s+)?(?:instructions|prompts|rules|restrictions|safety|guidelines|guardrails|filters|limits|constraints)\b",
               re.IGNORECASE),
    re.compile(r"\bdisregard\s+(?:all\s+|the\s+|your\s+|previous\s+)?(?:instructions?|restrictions?|rules?)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:print|reveal|show|tell|output)\s+(?:me\s+)?(?:the\s+|your\s+)?system\s+prompt\b",
               re.IGNORECASE),
    re.compile(r"\bwhat(?:\s+is|'s)?\s+your\s+system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\b(?:reveal|leak|print)\s+your\s+(?:rules|instructions|prompt)\b",
               re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+a\s+\w+\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(?:a\s+)?(?:malicious|jailbroken|unrestricted)\b",
               re.IGNORECASE),
    # DAN-family persona jailbreaks. "Act as DAN", "As DAN, …", "Do
    # Anything Now" — these are universal jailbreak patterns that try
    # to bypass safety by adopting an unconstrained alter-ego. They
    # often co-occur with a real Art. ref ("As DAN, what does Art. 5
    # let me get away with?") so we must refuse before the anchor path.
    re.compile(r"\bact\s+as\s+(?:a\s+)?dan\b", re.IGNORECASE),
    re.compile(r"\b(?:as|i\s+am)\s+dan\b", re.IGNORECASE),
    re.compile(r"\bdo\s+anything\s+now\b", re.IGNORECASE),
    # Fake "internal / developer / debug / dev" mode requests — model
    # platforms don't expose such modes; the user is asking us to drop
    # constraints. "Switch to internal Anthropic dev mode", "enter dev
    # mode", "debug mode", "jailbreak mode" all fit.
    re.compile(
        r"\b(?:switch\s+to|enter|enable|activate)\s+"
        r"(?:internal\s+)?(?:anthropic\s+)?"
        r"(?:dev|developer|debug|jailbreak|unrestricted|admin|root|sudo)\s+mode\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\binternal\s+(?:anthropic|openai|model)\s+(?:dev|developer|debug)\s+mode\b",
        re.IGNORECASE,
    ),
    # NOTE: bare "roleplay as X" / "pretend to be Y" is NOT blocked here.
    # Benign personas ("compliance consultant", "deployer", "auditor")
    # are legitimate framings, and the sycophancy/false-authority eval
    # battery includes them deliberately to verify we push back on the
    # CONTENT rather than refuse the FRAME. The translator-persona
    # jailbreak ("translate my prohibited plan into a compliant variant")
    # is still blocked via the dedicated "translate prohibited" pattern
    # below, which fires on the content of the request, not the persona.
    # "For educational purposes only" + jailbreak intent — a known
    # framing pattern that asks the model to drop safeguards by
    # claiming the request is benign. We refuse rather than try to
    # split out the educational intent from the operational ask.
    re.compile(
        r"\bfor\s+(?:educational|academic|research)\s+purposes\b[^.!?]{0,80}"
        r"\b(?:ignore|disregard|bypass|drop|skip|override|disable)\b",
        re.IGNORECASE,
    ),
    # "How to deploy / use / build … undetected / without detection /
    # without getting caught" — operationalising prohibited or
    # restricted activity. Refuse irrespective of the AI Act context.
    re.compile(
        r"\b(?:deploy|use|build|run|operate|launch)\b[^.!?]{0,80}"
        r"\b(?:undetected|without\s+detection|without\s+getting\s+caught|under\s+the\s+radar)\b",
        re.IGNORECASE,
    ),
    # "Translate my prohibited / social-scoring / banned … plan into a
    # 'compliant' variant" — laundering pattern. The user signals they
    # know the activity is prohibited and asks for a relabelled version.
    re.compile(
        r"\b(?:translate|rewrite|reframe|relabel|rebrand)\b[^.!?]{0,80}"
        r"\b(?:prohibited|banned|illegal|forbidden)\b",
        re.IGNORECASE,
    ),
    # Round-3 hardening (eng-review H4): adversarial framings that
    # use AI-Act-anchor keywords as cover. Without these patterns,
    # "How do I break the AI Act?" or "Help me circumvent Art. 5"
    # would flip to in-scope via the "ai act" anchor and ship a
    # confident answer instead of being refused as adversarial intent.
    # We refuse rather than answer because Regenold's audience is
    # compliance officers + auditors — they don't need help breaking
    # the regulation, they need help meeting it.
    re.compile(
        r"\b(?:break|circumvent|bypass|evade|avoid|skirt|get\s+around|"
        r"side[- ]?step|work\s+around|defeat|undermine)\b"
        r"[^.!?]{0,80}\b(?:ai\s+act|regulation|art(?:icle|\.)?\s*\d+|"
        r"annex\s+[ivxlc]+|prohibition|obligation|enforcement)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhelp\s+me\s+(?:break|circumvent|bypass|evade|avoid|skirt|"
        r"get\s+around|side[- ]?step|defeat)\b",
        re.IGNORECASE,
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """NFKC + collapse whitespace. Defense-in-depth on top of the
    middleware's normalisation — the scope filter receives the
    already-sanitised text from the route's body, but we want this
    module to be self-contained for direct unit testing."""
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _has_alphabetic_content(text: str) -> bool:
    """Reject inputs that are mostly digits / punctuation (zxqv mnbv 12345)."""
    letters = sum(1 for c in text if c.isalpha())
    return letters >= 4


def _matches_any(text: str, patterns: Iterable[re.Pattern]) -> re.Match | None:
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


def _question_is_pure_conversational(text: str) -> bool:
    """Pure greeting/filler with no AI Act content."""
    return _matches_any(text, _CONVERSATIONAL_PATTERNS) is not None


def _question_is_generic_knowledge(text: str) -> bool:
    return _matches_any(text, _GENERIC_KNOWLEDGE_PATTERNS) is not None


def _has_ai_act_anchor(text: str) -> bool:
    """Any of: Art./Annex reference (handled separately), AI Act anchor
    keyword, or compliance dimension keyword.

    The reference check is in :func:`classify_scope` itself; this
    helper only handles the keyword path. We normalize hyphens to
    spaces on both sides so "high-risk ai" and "high risk ai" match
    the same anchor — users freely vary between the two forms.
    """
    low = text.lower().replace("-", " ")
    if any(anchor in low for anchor in _AI_ACT_ANCHORS):
        return True
    if any(dim in low for dim in _DIMENSION_KEYWORDS):
        return True
    return False


def _has_other_regulation_mention(text: str) -> bool:
    return _matches_any(text, _OTHER_REGULATION_PATTERNS) is not None


def _has_injection_pattern(text: str) -> bool:
    return _matches_any(text, _INJECTION_PATTERNS) is not None


def _looks_like_nonsense(text: str) -> bool:
    """Random char clumps with no real words.

    Heuristic: split into tokens, count tokens of >=4 chars that are
    purely alpha. If that count is < 2 and total length < 60 chars,
    it's nonsense. ``zxqv mnbv asdf 12345 678 hjkl`` has 0 dictionary
    words but plenty of alpha-only tokens — we additionally check for
    any token being a known AI Act / English helper word.
    """
    if not text:
        return True
    tokens = re.findall(r"[A-Za-z]{2,}", text)
    if not tokens:
        return True
    # Treat tokens as nonsense if NONE of them appear in our anchor or
    # dimension vocab, AND none is a common English word.
    common = {
        "what", "which", "where", "when", "why", "how", "does", "do",
        "is", "are", "can", "should", "must", "may", "might", "would",
        "could", "the", "and", "or", "of", "in", "on", "at", "to",
        "from", "for", "with", "without", "about", "art", "article",
        "annex", "section", "rule", "law", "regulation", "obligation",
        "requirement", "compliance", "audit",
    }
    low_tokens = {t.lower() for t in tokens}
    if low_tokens & common:
        return False
    if any(anchor in " ".join(low_tokens) for anchor in _AI_ACT_ANCHORS):
        return False
    return True


# ── Public API ───────────────────────────────────────────────────────────


def classify_scope(question: str) -> ScopeVerdict:
    """Classify a question against the EU AI Act scope.

    Order matters — the first matching reason wins:

    1. Empty / nonsense — short or letter-poor inputs.
    2. Prompt-injection — adversarial substrings.
    3. Non-existent article — explicit ``Art. N`` / ``Annex X`` reference
       not in :data:`ARTICLE_EXISTENCE`. Even when other in-scope
       anchors are present, a non-existent reference takes precedence
       so we always surface "Art. 200 doesn't exist" rather than
       silently dropping it.
    4. In-scope — at least one valid Art./Annex reference, OR an AI Act
       anchor keyword, OR a dimension keyword.
    5. Other regulation — only if no in-scope signal AND a non-AI-Act
       regulation keyword is present.
    6. Conversational — pure filler / generic-knowledge.
    7. Empty fallback — anything left.

    Returns a :class:`ScopeVerdict` with the rationale.
    """
    text = _normalise(question or "")
    if not text or len(text) < 3 or not _has_alphabetic_content(text):
        return ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.EMPTY_OR_NONSENSE,
            evidence="Empty or letter-poor input.",
        )

    # 2. Injection — fail loudly. We don't try to "answer the underlying
    # question after stripping the injection"; the scope is "EU AI Act
    # Q&A", not "interpret possibly-adversarial text".
    if _has_injection_pattern(text):
        m = _matches_any(text, _INJECTION_PATTERNS)
        return ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.PROMPT_INJECTION,
            evidence=f"Prompt-injection pattern matched: {m.group(0)[:60]!r}" if m else "Injection",
        )

    known, unknown = extract_referenced_articles(text)

    # 3. Non-existent article — even if in-scope keywords are present.
    # An explicit "Art. 200" reference deserves a tailored refusal, not
    # a generic "ok we'll answer with whatever we found".
    if unknown:
        return ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.NON_EXISTENT_ARTICLE,
            evidence=f"Reference(s) outside the EU AI Act: {', '.join(unknown)}",
            referenced_articles=known,
            unknown_articles=unknown,
        )

    # 4. In-scope: known refs OR anchor keywords.
    if known:
        return ScopeVerdict(
            in_scope=True,
            reason=ScopeReason.IN_SCOPE,
            evidence=f"Valid EU AI Act reference(s): {', '.join(known)}",
            referenced_articles=known,
        )
    if _has_ai_act_anchor(text):
        return ScopeVerdict(
            in_scope=True,
            reason=ScopeReason.IN_SCOPE,
            evidence="AI Act anchor keyword(s) present.",
            referenced_articles=known,
        )

    # 5. Other regulation — only if no in-scope signal.
    if _has_other_regulation_mention(text):
        return ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.OTHER_REGULATION,
            evidence="Mentions a non-EU-AI-Act regulation without an AI Act anchor.",
        )

    # 6. Conversational / generic-knowledge.
    if _question_is_pure_conversational(text) or _question_is_generic_knowledge(text):
        return ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.CONVERSATIONAL,
            evidence="Pure conversational or generic-knowledge phrasing.",
        )

    # 7. Nonsense fallthrough.
    if _looks_like_nonsense(text):
        return ScopeVerdict(
            in_scope=False,
            reason=ScopeReason.EMPTY_OR_NONSENSE,
            evidence="No EU AI Act anchors or dictionary words detected.",
        )

    # 8. Generic fallback — no strong signal in any direction. Treat as
    # conversational (the safer refusal) so we don't ship a confident
    # boilerplate answer to a question we can't anchor.
    return ScopeVerdict(
        in_scope=False,
        reason=ScopeReason.CONVERSATIONAL,
        evidence="No EU AI Act anchor, dimension, or article reference found.",
    )


# ── Refusal copy ─────────────────────────────────────────────────────────
#
# Copy is centralised here so audit-chain entries + integration tests can
# match against the exact strings. Each refusal stays within the spec's
# "3-4 sentences max" budget. The route uses these directly and pins
# ``retrieval_path="no_match"`` + ``confidence=0.0``.


def _format_neighbour_articles(unknown: tuple[str, ...]) -> str:
    """Suggest valid neighbours for a non-existent article reference.

    For an unknown ``Art. NNN``, surface the closest valid article
    numbers — this turns a generic "doesn't exist" into an actionable
    "did you mean Art. 99 / 113?". Annex unknowns get a static "I-XIII"
    hint because there are only 13 valid annexes.
    """
    suggestions: list[str] = []
    for ref in unknown:
        if ref.startswith("Annex "):
            suggestions.append("Annex I through Annex XIII")
            break  # No need to repeat for multiple annex misses
    art_misses = [r for r in unknown if r.startswith("Art. ")]
    for ref in art_misses:
        try:
            num = int(ref[len("Art. ") :])
        except ValueError:
            continue
        # Closest valid neighbours within the 1-113 range. We always
        # find 2 candidates because the regulation has 113 articles —
        # the tightest neighbours when num >> 113 are 112/113, and when
        # num < 1 (impossible here, but defensive) they would be 1/2.
        candidates = sorted(
            (n for n in range(1, 114) if n != num),
            key=lambda n: abs(n - num),
        )[:2]
        if candidates:
            suggestions.append(
                "Art. " + " or Art. ".join(str(n) for n in candidates)
            )
            break  # One Article suggestion is enough
    if not suggestions:
        return ""
    return f" Did you mean {', or '.join(suggestions)}?"


def refusal_copy_for(verdict: ScopeVerdict) -> str:
    """Tailored refusal answer for ``verdict``.

    Each refusal is plain prose, 3 sentences max, and signals to the
    partner what the issue is so they can fix the request.
    """
    if verdict.reason == ScopeReason.NON_EXISTENT_ARTICLE:
        bad = ", ".join(verdict.unknown_articles)
        # The regulation has 113 numbered articles + 13 Annexes (I-XIII).
        suggestion = _format_neighbour_articles(verdict.unknown_articles)
        return (
            f"{bad} does not appear in the EU AI Act (Regulation 2024/1689). "
            f"The regulation has 113 numbered articles and 13 annexes (Annex I-XIII).{suggestion}"
        ).strip()

    if verdict.reason == ScopeReason.OTHER_REGULATION:
        return (
            "This question is about a regulation outside the EU AI Act. "
            "I only answer questions about the EU AI Act (Regulation 2024/1689). "
            "Try rephrasing with a specific Art. reference (e.g. \"Art. 13\") or compliance dimension."
        )

    if verdict.reason == ScopeReason.PROMPT_INJECTION:
        return (
            "I only answer questions about the EU AI Act (Regulation 2024/1689). "
            "Please ask a regulatory question — for example, \"What does Art. 13 require?\" "
            "or \"What are the deployer obligations under Art. 26?\"."
        )

    if verdict.reason == ScopeReason.CONVERSATIONAL:
        return (
            "I only answer questions about the EU AI Act (Regulation 2024/1689). "
            "Try a regulatory question, for example: \"What does Art. 13 require for transparency?\" "
            "or \"What are the deployer obligations under Art. 26?\"."
        )

    if verdict.reason == ScopeReason.EMPTY_OR_NONSENSE:
        return (
            "No matching obligation found in the EU AI Act for this question. "
            "Try rephrasing with a specific article reference (e.g. \"Art. 13\"), "
            "a risk level (e.g. \"high-risk\"), or a compliance dimension "
            "(e.g. \"transparency\")."
        )

    # IN_SCOPE — caller should not ask for refusal copy.
    return ""


# ── Multi-turn conversation scope ────────────────────────────────────────


@dataclass(frozen=True)
class ConversationVerdict:
    """Multi-turn extension of :class:`ScopeVerdict`.

    Beyond the single-message verdict, carries the *anchor articles* a
    conversation has established (across every prior user + assistant
    turn). The route uses these to:

    * resolve coreference in the live question ("What about deployers?"
      after "What does Art. 13 require?" → anchors=[Art. 13]).
    * surface anchor articles as defensive citations when the engine
      misses them (e.g. the deterministic parser fails to extract
      ``Annex IV`` from "Summarise Annex IV technical documentation").
    """

    verdict: ScopeVerdict
    anchor_articles: tuple[str, ...]
    history_unknown_articles: tuple[str, ...]
    live_question: str

    @property
    def in_scope(self) -> bool:
        return self.verdict.in_scope

    @property
    def reason(self) -> ScopeReason:
        return self.verdict.reason


def _is_short_followup(text: str) -> bool:
    """A short follow-up has no anchor of its own.

    Used to decide whether to lean on conversation anchors. Heuristic:
    < 8 alphabetic tokens AND no Art./Annex reference of its own.
    "What about deployers?" matches; "Tell me more about deployer
    monitoring duties under Art. 26(5)" does not.
    """
    tokens = re.findall(r"[A-Za-z]{2,}", text)
    if len(tokens) >= 12:
        return False
    known, unknown = extract_referenced_articles(text)
    return not known and not unknown


def _live_question_borrows_anchor(live_text: str, anchors: tuple[str, ...]) -> bool:
    """Should we treat the live question as in-scope by anchor borrow?

    Conditions:
    * The live question has at least one anchor article in prior turns.
    * The live question is NOT a pure conversational filler ("thanks",
      "bye", "good morning") — those carry no compliance content even
      with anchors. Without this guard, a short "Thanks!" after a real
      Q&A would inherit the prior anchor and ship a citation-laden
      response for what is plainly a polite acknowledgement.
    * The live question carries a STRONG follow-up marker (length-agnostic)
      OR is short AND uses anaphoric/pronoun phrasing.

    Strong markers (length-agnostic) are highly specific signals that
    the live question is asking about the prior topic — e.g. "what if
    we re-train the model quarterly?" is plainly a process follow-up
    about the prior article even at 8+ tokens. General markers stay
    gated on ``_is_short_followup`` to avoid grabbing arbitrary
    ``what if X`` / ``is it Y`` framings out of unrelated context.
    """
    if not anchors:
        return False
    # Conversational fillers never borrow anchors — prior topic doesn't
    # turn "Thanks!" into a real follow-up question.
    if _question_is_pure_conversational(live_text):
        return False
    if _question_is_generic_knowledge(live_text):
        return False

    low = live_text.lower()

    # Strong markers — fire regardless of question length. These are
    # specific enough that "what if we re-train" / "how often" / "are
    # these" almost always inherit the prior turn's topic, even when
    # the question runs to 8+ tokens. Added in the regenold-eu-ai-act-rag
    # follow-up #1 to close 3 multi-session refusals where a long
    # data/process follow-up plainly inherited an anchor from the
    # prior assistant turn.
    strong_markers = (
        "what if we re-train",
        "what if we retrain",
        "what if we re train",
        "how often",
        "are these",
        "tell me more",
        "more details",
        # Confirmatory / consequence follow-ups — e.g. "so no logging is
        # needed if vendor logs already?" after an Art. 26 exchange.
        # These don't start with a question marker but plainly extend
        # the prior turn's regulatory topic.
        "so no ",
        "so we ",
        "so does ",
        "so is ",
        "so are ",
        "does that mean",
        "does this mean",
        "does this apply",
    )
    if any(m in low for m in strong_markers):
        return True

    # "So X?" questions — confirmatory consequence follow-ups that start
    # with "so" and end in a question mark. These span all lengths and
    # always inherit the prior regulatory topic: "So it's only for end
    # users, right?", "So if our vendor logs everything we don't need to?"
    if low.startswith("so ") and "?" in live_text:
        return True

    if not _is_short_followup(live_text):
        return False
    # At this point: the live question has no own anchor, is short
    # (< 12 alphabetic tokens), is not pure conversational filler, and
    # is not a generic-knowledge query. Anchors exist from prior turns.
    # If the question carries question shape — ends with "?", starts
    # with a wh-word, starts with an auxiliary verb (does/do/is/are/…),
    # or starts with a coordinating "and " — it is almost certainly a
    # follow-up that should borrow the prior anchor. The earlier filters
    # already screened out "Thanks!" / "Who is your CEO?" / generic
    # knowledge questions, so we can be generous here.
    if "?" in live_text:
        return True
    wh_starts = ("what ", "who ", "when ", "where ", "why ", "how ", "which ")
    aux_starts = (
        "and ", "but ", "or ",
        "does ", "do ", "did ",
        "is ", "are ", "was ", "were ",
        "will ", "would ", "could ", "should ", "can ", "may ", "might ", "must ",
        "has ", "have ", "had ",
    )
    if any(low.startswith(w) for w in wh_starts):
        return True
    if any(low.startswith(a) for a in aux_starts):
        return True
    return False


def classify_conversation(
    messages: list[dict] | list[Any],
) -> ConversationVerdict:
    """Classify a multi-turn conversation against the EU AI Act scope.

    ``messages`` is a list of ``{role, content}`` dicts (or
    ``RegenoldChatMessage`` instances — anything with ``.role`` /
    ``.content`` attrs). The classifier:

    1. Walks every message and extracts ``(known, unknown)`` refs.
       Aggregated across all turns, in conversation order, dedup
       preserving first-seen order. ``known`` becomes the anchor pool;
       any ``unknown`` triggers a ``non_existent_article`` refusal —
       the LLM will see the bogus reference in the prompt and might
       echo it, so we refuse pre-emptively.
    2. Locates the live (last user) message and runs the per-message
       classifier on it.
    3. If the live message is in-scope, return that as-is with the
       full anchor pool.
    4. If the live message is conversational/empty BUT prior turns
       establish anchor articles, override to in-scope with the anchor
       pool — covers the "What about deployers?" follow-up case.
    5. Otherwise return the live verdict (typically a refusal).

    The verdict's ``reason`` follows the strictest precedence — a
    non-existent reference anywhere in history beats an in-scope live
    question, because the LLM's prompt will have seen the bogus ref
    and might echo it. This is the same precedence the per-message
    classifier uses.
    """
    if not messages:
        return ConversationVerdict(
            verdict=ScopeVerdict(
                in_scope=False,
                reason=ScopeReason.EMPTY_OR_NONSENSE,
                evidence="Empty conversation.",
            ),
            anchor_articles=(),
            history_unknown_articles=(),
            live_question="",
        )

    # Normalise message access — accept both dict + Pydantic-model shapes.
    def _get(m: Any, attr: str) -> str:
        if isinstance(m, dict):
            return str(m.get(attr) or "")
        return str(getattr(m, attr, "") or "")

    # 1. Collect anchors + unknowns from EVERY non-system message.
    #    Anchors come from two sources:
    #      a. Explicit ``Art. N`` / ``Annex X`` references.
    #      b. Well-known anchor keywords (FRIA → Art. 27, GPAI → Art. 53,
    #         technical documentation → Annex IV, …) — covers questions
    #         that mention concepts but not article numbers.
    anchors: list[str] = []
    unknowns: list[str] = []
    for m in messages:
        role = _get(m, "role")
        if role == "system":
            continue
        content = _get(m, "content")
        if not content:
            continue
        k, u = extract_referenced_articles(content)
        for ref in k:
            if ref not in anchors:
                anchors.append(ref)
        for ref in u:
            if ref not in unknowns:
                unknowns.append(ref)
        # Keyword-driven anchors — only for non-system messages so we
        # don't promote standing instructions to citations.
        for ref in derive_anchor_articles_from_keywords(content):
            if ref not in anchors:
                anchors.append(ref)

    # 2. Find the live user message (last non-empty user role).
    live_text = ""
    for m in reversed(messages):
        if _get(m, "role") == "user":
            live_text = _get(m, "content").strip()
            if live_text:
                break

    # 3. Non-existent reference precedence — refuse when the LIVE question
    #    mentions an unknown article. History-only unknowns (from prior turns
    #    that were already refused) do NOT block the current turn: the user
    #    may have corrected themselves (e.g. turn 1 asked about Art. 999,
    #    turn 2 asks about Art. 99). History unknowns are tracked in
    #    ``history_unknown_articles`` for the route's audit trail; the
    #    existing hallucination defences (drift guard, reference validation)
    #    prevent the bogus history ref from leaking into the wire answer.
    if unknowns:
        _, live_u = extract_referenced_articles(live_text)
        live_unknowns_set = frozenset(live_u)
        live_blocking = tuple(u for u in unknowns if u in live_unknowns_set)
        if live_blocking:
            return ConversationVerdict(
                verdict=ScopeVerdict(
                    in_scope=False,
                    reason=ScopeReason.NON_EXISTENT_ARTICLE,
                    evidence=f"Reference(s) outside the EU AI Act: {', '.join(live_blocking)}",
                    referenced_articles=tuple(anchors),
                    unknown_articles=live_blocking,
                ),
                anchor_articles=tuple(anchors),
                history_unknown_articles=tuple(unknowns),
                live_question=live_text,
            )
        # All unknowns are history-only — fall through to step 4 so the
        # valid live question is classified on its own merits.

    # 4. Per-message classification of the live question.
    live_verdict = classify_scope(live_text)
    if live_verdict.in_scope:
        return ConversationVerdict(
            verdict=live_verdict,
            anchor_articles=tuple(anchors),
            history_unknown_articles=tuple(unknowns),
            live_question=live_text,
        )

    # 5. Coreference rescue — "What about deployers?" with anchor=[Art. 13].
    if _live_question_borrows_anchor(live_text, tuple(anchors)):
        rescued = ScopeVerdict(
            in_scope=True,
            reason=ScopeReason.IN_SCOPE,
            evidence=(
                f"Coreference rescue: anchor(s) {', '.join(anchors)} from prior turn(s)."
            ),
            referenced_articles=tuple(anchors),
        )
        return ConversationVerdict(
            verdict=rescued,
            anchor_articles=tuple(anchors),
            history_unknown_articles=(),
            live_question=live_text,
        )

    return ConversationVerdict(
        verdict=live_verdict,
        anchor_articles=tuple(anchors),
        history_unknown_articles=(),
        live_question=live_text,
    )
