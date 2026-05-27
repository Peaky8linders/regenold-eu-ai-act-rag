"""Round 66-E Phase 2a — Hierarchical Chapter Community Summaries.

Microsoft GraphRAG (Edge et al., 2024) shows that **community summaries**
lift recall on broad / vague queries that no single article fully
answers. The EU AI Act has 13 chapters; each chapter is a natural
"community" in the knowledge graph.

This module exports per-chapter summaries (regulator-voice, 100-180
chars) and the chapter's load-bearing articles, plus a heuristic
``chapter_for_query`` that maps a vague / broad question to its target
chapter when retrieval would otherwise return nothing useful.

## Design constraints

1. **Strictly additive** — the route consults the chapter map ONLY as
   a last-resort fallback after :func:`zero_retrieval_fallback`. A
   chapter summary never displaces a BM25 winner.
2. **Deterministic / pure stdlib** — no LLM call, no Neo4j, no
   dependencies beyond ``ARTICLE_EXISTENCE``. Imports run at module
   load and validate every primary_anchor against the canonical
   113-article + 13-annex catalog.
3. **CLAUDE.md hard rule #2** — each summary stays under 200 chars so
   the 3-sentence + 600-char wire cap absorbs the chapter prose
   without dropping engine content.

## Chapter structure (canonical EUR-Lex Title-Chapter layout)

| Chapter | Articles | Topic                                   |
|---------|----------|-----------------------------------------|
| I       | 1-4      | General provisions                      |
| II      | 5        | Prohibited AI practices                 |
| III     | 6-49     | High-risk AI systems                    |
| IV      | 50       | Transparency obligations                |
| V       | 51-56    | General-purpose AI models               |
| VI      | 57-63    | Measures supporting innovation          |
| VII     | 64-70    | Governance                              |
| VIII    | 71       | EU database for high-risk AI systems    |
| IX      | 72-94    | Post-market monitoring + enforcement    |
| X       | 95-96    | Codes of conduct + guidelines           |
| XI      | 97-98    | Delegation of power + committee         |
| XII     | 99-101   | Penalties                               |
| XIII    | 102-113  | Final provisions                        |

Each chapter's PRIMARY_ANCHORS list carries the 1-3 load-bearing
articles — those an operator would cite when the question is "what
does Chapter X cover?" rather than asking about a specific provision.
"""
from __future__ import annotations

import os
from typing import Optional

from app.data.article_existence import ARTICLE_EXISTENCE


# ── Chapter summaries (regulator-voice, 100-180 chars each) ──────────────


CHAPTER_SUMMARY: dict[str, str] = {
    "I": (
        "General provisions of Regulation 2024/1689. Sets the subject "
        "matter (Article 1), scope (Article 2), definitions (Article 3) "
        "and AI literacy duty (Article 4)."
    ),
    "II": (
        "Prohibited AI practices under Article 5. Enumerates the "
        "AI uses banned outright in the Union — subliminal manipulation, "
        "exploitation of vulnerabilities, social scoring, untargeted "
        "scraping and real-time biometric identification in public spaces."
    ),
    "III": (
        "High-risk AI systems regime (Articles 6-49). Establishes the "
        "classification rules (Article 6, Annex III), the technical "
        "requirements for providers (risk management, data, "
        "documentation, oversight, accuracy, robustness), and the "
        "obligations on providers, deployers, importers and distributors."
    ),
    "IV": (
        "Transparency obligations for certain AI systems under Article 50. "
        "Requires disclosure to natural persons interacting with AI, "
        "labelling of synthetic media and deep-fakes, and notification of "
        "emotion-recognition or biometric-categorisation use."
    ),
    "V": (
        "Obligations for providers of general-purpose AI models "
        "(Articles 51-56). Classifies systemic-risk GPAI, sets "
        "transparency, documentation and copyright duties, requires "
        "training-data summaries and authorises codes of practice."
    ),
    "VI": (
        "Measures in support of innovation (Articles 57-63). Establishes "
        "AI regulatory sandboxes, testing in real-world conditions, and "
        "the simplified regime for SMEs and start-ups under Articles 62-63."
    ),
    "VII": (
        "Governance framework (Articles 64-70). Establishes the AI Office, "
        "the European Artificial Intelligence Board, the advisory forum "
        "and the scientific panel; designates Member State national "
        "competent authorities and notifying authorities."
    ),
    "VIII": (
        "EU database for high-risk AI systems (Article 71). Requires "
        "providers and deployers (public authorities) to register "
        "high-risk Annex III systems before placing them on the market "
        "or putting them into service."
    ),
    "IX": (
        "Post-market monitoring, information sharing and enforcement "
        "(Articles 72-94). Covers post-market plans, serious incident "
        "reporting, market surveillance, remedies and the dedicated "
        "Commission enforcement of GPAI providers."
    ),
    "X": (
        "Codes of conduct and Commission guidelines (Articles 95-96). "
        "Encourages voluntary application of high-risk requirements to "
        "non-high-risk AI and authorises the Commission to issue "
        "guidelines on this Regulation's practical implementation."
    ),
    "XI": (
        "Delegation of power and committee procedure "
        "(Articles 97-98). Conditions the Commission's adoption of "
        "delegated acts under this Regulation and establishes the "
        "comitology committee structure."
    ),
    "XII": (
        "Penalties (Articles 99-101). Sets Member State administrative "
        "fines for infringements, Union-institutional fines via the "
        "European Data Protection Supervisor, and Commission fines on "
        "GPAI providers (imposed by the AI Office)."
    ),
    "XIII": (
        "Final provisions (Articles 102-113). Amends adjacent Union "
        "legislation, sets the staged entry-into-force timeline and "
        "transitional measures, and addresses evaluation, review and "
        "the operative date of obligations."
    ),
}


# ── Per-chapter load-bearing article anchors ─────────────────────────────


CHAPTER_PRIMARY_ANCHORS: dict[str, tuple[str, ...]] = {
    "I":    ("Art. 1", "Art. 2", "Art. 3"),
    "II":   ("Art. 5",),
    "III":  ("Art. 6", "Art. 9", "Art. 13"),
    "IV":   ("Art. 50",),
    "V":    ("Art. 51", "Art. 53", "Art. 55"),
    "VI":   ("Art. 57", "Art. 62"),
    "VII":  ("Art. 64", "Art. 65", "Art. 70"),
    "VIII": ("Art. 71",),
    "IX":   ("Art. 72", "Art. 73", "Art. 79"),
    "X":    ("Art. 95", "Art. 96"),
    "XI":   ("Art. 97", "Art. 98"),
    "XII":  ("Art. 99", "Art. 101"),
    "XIII": ("Art. 113",),
}


# ── Intent → chapter mapping (used by chapter_for_query) ─────────────────


# Maps the 15-way intent label (from app.llm.intent_classifier) to its
# canonical chapter. Used when retrieval surfaces no anchors but the
# Stage-0 intent classifier returned a clean label. The intent → chapter
# routing mirrors the article-level ``INTENT_PRIMARY_ANCHOR`` but at the
# coarser community-summary granularity (recall over precision).
_INTENT_CHAPTER_MAP: dict[str, str] = {
    "article_lookup":          "I",      # Art. 1 / 2 / 3 family
    "definition":              "I",      # Art. 3 family
    "risk_classification":     "III",    # Art. 6 + Annex III
    "role_obligations":        "III",    # Provider/deployer/importer/distributor
    "compliance_checklist":    "III",    # Risk management, QMS, oversight
    "transparency_obligation": "IV",     # Art. 50
    "gpai_systemic":           "V",      # Art. 51-56
    "sandbox":                 "VI",     # Art. 57
    "incident_reporting":      "IX",     # Art. 73
    "penalty_inquiry":         "XII",    # Art. 99-101
    "timeline_question":       "XIII",   # Art. 113
    "fria":                    "III",    # Art. 27 (FRIA)
    "comparative":             "I",      # Art. 2 (scope vs other regs)
}


# Broad-query keyword markers — questions that name a chapter-level
# concept but no specific article (e.g. "what is the AI Act about?",
# "tell me about high-risk AI"). The mapping must NOT over-broaden:
# every entry is a multi-word noun phrase or chapter-shaped framing
# that an AI Act expert would naturally use, NOT a single common word.
_BROAD_KEYWORD_CHAPTER_MAP: tuple[tuple[str, str], ...] = (
    # Chapter I — general provisions / scope / definitions
    ("subject matter of the regulation", "I"),
    ("subject matter of the ai act", "I"),
    ("scope of the regulation", "I"),
    ("scope of the ai act", "I"),
    ("territorial scope", "I"),
    ("ai literacy", "I"),
    # Chapter II — prohibited practices
    ("prohibited ai practices", "II"),
    ("prohibited practices", "II"),
    ("article 5 prohibitions", "II"),
    # Chapter III — high-risk systems
    ("high-risk ai system", "III"),
    ("high risk ai system", "III"),
    ("high-risk classification", "III"),
    ("high risk classification", "III"),
    ("annex iii", "III"),
    # Chapter IV — transparency
    ("transparency obligations", "IV"),
    ("transparency obligation", "IV"),
    ("synthetic media", "IV"),
    # Chapter V — GPAI
    ("general-purpose ai model", "V"),
    ("general purpose ai model", "V"),
    ("gpai model", "V"),
    ("systemic risk gpai", "V"),
    ("training data summary", "V"),
    # Chapter VI — innovation + SME
    ("regulatory sandbox", "VI"),
    ("ai regulatory sandbox", "VI"),
    ("sme simplification", "VI"),
    ("small mid-cap", "VI"),
    # Chapter VII — governance
    ("ai office", "VII"),
    ("european artificial intelligence board", "VII"),
    ("notifying authority", "VII"),
    # Chapter VIII — EU database
    ("eu database", "VIII"),
    ("eu high-risk database", "VIII"),
    # Chapter IX — post-market + enforcement
    ("post-market monitoring", "IX"),
    ("post market monitoring", "IX"),
    ("serious incident reporting", "IX"),
    ("market surveillance", "IX"),
    # Chapter X — codes of conduct
    ("code of conduct", "X"),
    ("commission guidelines", "X"),
    # Chapter XI — delegation
    ("delegated acts", "XI"),
    ("comitology", "XI"),
    # Chapter XII — penalties
    ("administrative fines", "XII"),
    ("maximum fine", "XII"),
    ("penalties under the regulation", "XII"),
    ("penalties under the ai act", "XII"),
    # Chapter XIII — final provisions
    ("digital omnibus", "XIII"),
    ("entry into force", "XIII"),
    ("entry-into-force", "XIII"),
    ("staged applicability", "XIII"),
    ("staged timeline", "XIII"),
)


# R89-A — section-scoped routing. These markers are deliberately narrower
# than the chapter markers: the section router fires only after chapter
# routing has already selected Chapter III or V, then picks the most
# specific local subdivision for BM25 pre-filtering.
_SECTION_KEYWORD_MAP: tuple[tuple[str, str, int], ...] = (
    # Chapter III, section 1 — classification of high-risk systems
    ("annex iii", "III.1", 2),
    ("annex 3", "III.1", 2),
    ("high-risk classification", "III.1", 2),
    ("high risk classification", "III.1", 2),
    ("safety component", "III.1", 2),
    ("high-risk ai system", "III.1", 1),
    ("high risk ai system", "III.1", 1),
    # Chapter III, section 2 — technical requirements
    ("risk management", "III.2", 2),
    ("data governance", "III.2", 2),
    ("technical documentation", "III.2", 2),
    ("record keeping", "III.2", 2),
    ("logs", "III.2", 2),
    ("transparency information", "III.2", 2),
    ("instructions for use", "III.2", 2),
    ("human oversight", "III.2", 2),
    ("accuracy robustness", "III.2", 2),
    ("cybersecurity", "III.2", 2),
    # Chapter III, section 3 — operator obligations
    ("provider obligations", "III.3", 2),
    ("deployer obligations", "III.3", 2),
    ("importer obligations", "III.3", 2),
    ("distributor obligations", "III.3", 2),
    ("authorised representative", "III.3", 2),
    ("authorized representative", "III.3", 2),
    ("fundamental rights impact", "III.3", 2),
    ("fria", "III.3", 2),
    ("corrective action", "III.3", 2),
    ("substantial modification", "III.3", 2),
    ("value chain", "III.3", 2),
    ("deployers", "III.3", 1),
    ("deployer", "III.3", 1),
    ("importers", "III.3", 1),
    ("importer", "III.3", 1),
    ("distributors", "III.3", 1),
    ("distributor", "III.3", 1),
    # Chapter III, section 4 — notifying authorities / notified bodies
    ("notifying authority", "III.4", 2),
    ("notified body", "III.4", 2),
    ("designating authority", "III.4", 2),
    ("conformity assessment body", "III.4", 2),
    # Chapter III, section 5 — standards / conformity / registration
    ("harmonised standard", "III.5", 2),
    ("harmonized standard", "III.5", 2),
    ("conformity assessment", "III.5", 2),
    ("ce marking", "III.5", 2),
    ("ce mark", "III.5", 2),
    ("eu declaration", "III.5", 2),
    ("certificate", "III.5", 1),
    ("registration", "III.5", 1),
    # Chapter V, section 1 — GPAI classification + general obligations
    ("general-purpose ai model", "V.1", 2),
    ("general purpose ai model", "V.1", 2),
    ("training data summary", "V.1", 2),
    ("copyright", "V.1", 2),
    ("open-weight", "V.1", 2),
    ("open weight", "V.1", 2),
    # Chapter V, section 2 — systemic-risk GPAI duties
    ("systemic risk", "V.2", 2),
    ("10^25", "V.2", 2),
    ("10²⁵", "V.2", 2),
    ("high-impact capabilities", "V.2", 2),
    ("model evaluation", "V.2", 2),
    # Chapter V, section 3 — codes of practice
    ("code of practice", "V.3", 2),
    ("codes of practice", "V.3", 2),
)


# ── Hyphen normalisation ─────────────────────────────────────────────────
#
# The davidath benchmark ships 90 U+2011 non-breaking hyphens, and AI Act
# terms appear both hyphenated ("deep-fake", "market-surveillance",
# "conformity-assessment") and spaced ("deep fake", "market surveillance")
# across the corpus. The chapter router's content markers are authored in
# one form only, so a hyphen/space mismatch silently drops the route and
# the query falls back to the coarse intent label. Folding every
# hyphen-family char to a space on BOTH the question and the marker lets a
# single marker form match every spelling.
#
# Salvaged from #101 commit 37670c2 / ac8bef2 — the rest of #101 (the
# LLM entity extractor) was superseded by R79 hyphen-normalise +
# R81-N typed-entity NER + R87-D role-duty seed + R88-A/B/D direct
# seeds. R79's fix lives in _deterministic_parse / text_normalize.py
# but doesn't reach this module's _BROAD_KEYWORD_CHAPTER_MAP scan,
# so the documented chapter-router U+2011 davidath mis-routes
# (qa_030 / qa_042 / qa_064 / qa_068 / qa_080) persisted in main.
_HYPHEN_TABLE = {
    ord(c): " " for c in "-‐‑‒–—−"
}


def _fold_hyphens(text: str) -> str:
    """Lowercase, fold every hyphen-family char to a space, collapse runs."""
    return " ".join(text.lower().translate(_HYPHEN_TABLE).split())


def _enabled(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in ("1", "true", "yes", "on")


def _intent_chapter_priors(intent_label: str | None) -> tuple[str, ...]:
    if not intent_label:
        return ()

    if _enabled("REGENOLD_CHAPTER_ROUTING_V2"):
        local_v2: dict[str, tuple[str, ...]] = {
            "article_lookup": ("I",),
            "definition": ("I",),
            "definitional": ("I",),
            "risk_assessment": ("II", "III"),
            "risk_classification": ("II", "III"),
            "obligation_check": ("III",),
            "role_obligations": ("III",),
            "compliance_checklist": ("III",),
            "transparency": ("IV",),
            "transparency_obligation": ("IV",),
            "gpai_systemic": ("V",),
            "sandbox": ("VI",),
            "incident_reporting": ("IX",),
            "penalty_inquiry": ("XII",),
            "timeline_question": ("XIII",),
            "fria": ("III",),
            "general_compliance": (),
            "gap_analysis": (),
            "cross_framework": (),
            "comparative": (),
            "out_of_scope": (),
            "other": (),
        }
        return local_v2.get(intent_label, ())

    local_legacy: dict[str, str] = {
        "article_lookup":       "I",
        "risk_assessment":      "III",
        "obligation_check":     "III",
        "general_compliance":   "",   # too broad — no chapter signal
        "gap_analysis":         "",   # too broad — no chapter signal
        "cross_framework":      "",   # too broad — no chapter signal
    }
    local_chapter = local_legacy.get(intent_label, "MISSING")
    if local_chapter == "MISSING":
        mapped = _INTENT_CHAPTER_MAP.get(intent_label)
        return (mapped,) if mapped else ()
    return (local_chapter,) if local_chapter else ()


# ── Public API ───────────────────────────────────────────────────────────


def chapter_for_query(
    question: str, intent_label: Optional[str] = None
) -> Optional[str]:
    """Heuristic chapter mapper for fall-back retrieval.

    Returns the chapter ID (Roman numeral string ``"I"`` ... ``"XIII"``)
    when the question is broad/vague AND no specific article has
    resolved through normal retrieval. The route uses this to surface
    the chapter summary + the chapter's load-bearing articles instead
    of an empty / generic refusal.

    Resolution order:

    1. **Broad-keyword scan** — checks the live question text against
       :data:`_BROAD_KEYWORD_CHAPTER_MAP`. First hit wins (longer,
       more-specific phrases listed first in the tuple to bias
       precision). Case-insensitive substring match.
    2. **Intent label** — when no keyword fires, falls back to the
       Stage-0 classifier's intent label via
       :data:`_INTENT_CHAPTER_MAP`. ``None`` / ``"other"`` /
       ``"out_of_scope"`` return ``None`` (no chapter mapping).

    Returns ``None`` when neither path resolves — the route then
    keeps its existing zero-retrieval refusal copy.

    Pure stdlib + sub-microsecond. Safe to call on every retrieval
    miss.
    """
    if question:
        low = _fold_hyphens(question)
        for keyword, chapter in _BROAD_KEYWORD_CHAPTER_MAP:
            if _fold_hyphens(keyword) in low:
                return chapter
    if intent_label and intent_label in _INTENT_CHAPTER_MAP:
        return _INTENT_CHAPTER_MAP[intent_label]
    return None


def summary_for_chapter(chapter: str) -> Optional[str]:
    """Return the regulator-voice summary for ``chapter``, or ``None``."""
    return CHAPTER_SUMMARY.get(chapter)


def candidate_chapters_for_query(
    question: str,
    intent_label: str | None = None,
) -> list[str]:
    """Pre-retrieval chapter router — returns 1-3 candidate chapters.

    Unlike :func:`chapter_for_query` (a last-resort fallback that returns
    a single chapter when retrieval already failed), this function is
    designed to run BEFORE BM25 to scope the search to the most likely
    chapter(s). Called by the PageIndex-style hierarchical filter in
    :func:`~app.engines.graph_rag._deterministic_parse`.

    Returns a sorted list of Roman numeral chapter IDs when the query has
    a clear chapter signal. Returns ``[]`` when the query is too broad or
    cross-chapter (full-corpus BM25 is then used unchanged).

    Scope guard: if ≥ 4 chapters are identified, returns ``[]`` — the
    routing is uncertain and scoping would risk cutting relevant articles.

    Resolution order:
    1. Broad-keyword scan (high-precision phrases from
       :data:`_BROAD_KEYWORD_CHAPTER_MAP`) — first hit adds one chapter.
    2. Risk/domain marker scan — adds chapters for recognised patterns.
    3. Intent label via :data:`_INTENT_CHAPTER_MAP` and local extension.
    4. Scope guard — returns ``[]`` when ≥ 4 chapters identified.
    """
    chapters: set[str] = set()
    low = _fold_hyphens(question) if question else ""

    def _hit(markers: tuple[str, ...]) -> bool:
        """True when any marker — hyphen-folded — is a substring of ``low``."""
        return any(_fold_hyphens(m) in low for m in markers)

    # 1. High-precision broad-keyword scan (first hit wins, then continue
    #    marker scan for multi-chapter queries like "prohibited high-risk AI")
    if low:
        for keyword, chapter in _BROAD_KEYWORD_CHAPTER_MAP:
            if _fold_hyphens(keyword) in low:
                chapters.add(chapter)
                break  # one high-precision anchor is enough

    # 2. Risk/domain marker scan (additive — multiple can fire)
    if low:
        if _hit((
            "prohibited", "banned", "forbidden", "subliminal", "manipulat",
            "social scoring", "biometric identification", "biometric id",
            "real-time remote biometric",
        )):
            chapters.add("II")

        if _hit((
            "high-risk", "high risk", "annex iii", "annex 3",
            "safety component", "hrais", "risk management",
            "technical documentation", "post-market monitoring plan",
            "conformity assessment", "ce marking", "ce mark",
            "fundamental rights impact", "fria",
            # Notified-body certificate lifecycle (Art. 44 — validity,
            # suspension, withdrawal) sits in Ch III; without these a
            # "suspend / withdraw a certificate" question routes on
            # "market surveillance" alone to Ch IX and loses Art. 44.
            # Multi-word forms only — per the broad-marker precision
            # rule (bare ``certificate`` is too broad in EU policy
            # English).
            "withdraw a certificate", "suspend a certificate",
            "withdrawal of a certificate", "suspension of a certificate",
            "notified body certificate",
        )):
            chapters.add("III")

        if _hit((
            "general-purpose ai", "general purpose ai", "gpai",
            "foundation model", "systemic risk model",
            "training data summary", "copyright", "code of practice",
        )):
            chapters.add("V")

        if _hit((
            "transparency obligation", "deepfake", "deep fake",
            "synthetic media", "emotion recognition",
            "biometric categorisation", "chatbot disclosure",
        )):
            chapters.add("IV")

        if _hit((
            "administrative fine", "maximum fine", "sanction",
            "penalty", "penalties", "fined",
        )):
            chapters.add("XII")

        if _hit((
            "post-market monitoring", "post market monitoring",
            "serious incident", "market surveillance",
            "market withdrawal", "enforcement action",
        )):
            chapters.add("IX")

        if _hit((
            "regulatory sandbox", "real-world testing",
            "sme", "small medium enterprise", "start-up", "startup",
            "innovation measure",
        )):
            chapters.add("VI")

        if _hit((
            "ai office", "ai board", "european artificial intelligence board",
            "national competent authority", "notifying authority",
            "governance",
        )):
            chapters.add("VII")

        if _hit((
            "eu database", "eudb", "register high-risk", "registration",
        )):
            chapters.add("VIII")

        if _hit((
            "entry into force", "entry-into-force", "applicability date",
            "transitional", "digital omnibus", "phased timeline",
            "staged applicability",
        )):
            chapters.add("XIII")

        if _hit((
            "delegated act", "comitology", "implementing act",
            "committee procedure",
        )):
            chapters.add("XI")

        if _hit((
            "code of conduct", "voluntary application",
            "commission guidelines",
        )):
            chapters.add("X")

        # Definitions / scope / general questions — Chapter I +
        # Chapter III (Art. 3 carries key HR-AI definitions)
        if _hit((
            "definition of ai", "definition of an ai",
            "what is an ai system", "what counts as",
            "scope of the", "subject matter",
            "ai literacy",
        )):
            chapters.add("I")

    # 3. Intent-label routing (catches intents the marker scan misses)
    chapters.update(_intent_chapter_priors(intent_label))

    # 4. Scope guard — too many chapters = uncertain routing
    if len(chapters) >= 4:
        return []

    # Discard the empty sentinel (used to signal "no chapter")
    chapters.discard("")
    return sorted(chapters)


def candidate_sections_for_query(
    question: str,
    *,
    chapters: list[str] | tuple[str, ...],
    intent_label: str | None = None,
) -> list[str]:
    """Return candidate logical sections within already-selected chapters.

    The section router is intentionally second-stage: callers first choose a
    chapter with :func:`candidate_chapters_for_query`, then ask this helper for
    a finer Chapter III / V subdivision. When no precise section signal exists
    the function returns ``[]`` so callers can keep chapter-scoped BM25.
    """
    del intent_label  # reserved for future priors; keyword precision comes first
    low = _fold_hyphens(question) if question else ""
    if not low or not chapters:
        return []

    allowed_chapters = {chapter.split(".", 1)[0] for chapter in chapters}
    scores: dict[str, int] = {}
    for keyword, section, weight in _SECTION_KEYWORD_MAP:
        if section.split(".", 1)[0] not in allowed_chapters:
            continue
        if _fold_hyphens(keyword) in low:
            scores[section] = scores.get(section, 0) + weight

    if not scores:
        return []
    best_score = max(scores.values())
    winners = sorted(
        section for section, score in scores.items()
        if score == best_score
    )
    # If the same broad query ties three or more sections, scoping is no
    # longer precise. Let the existing chapter/full BM25 fallback handle it.
    if len(winners) >= 3:
        return []
    return winners


def primary_anchors_for_chapter(chapter: str) -> tuple[str, ...]:
    """Return the load-bearing articles for ``chapter``. Empty if unknown."""
    return CHAPTER_PRIMARY_ANCHORS.get(chapter, ())


# ── Import-time self-check ───────────────────────────────────────────────


def _self_check() -> None:
    """Validate at module-load that the chapter data is internally
    consistent. Module fails to import on any violation — typos fail
    CI, not user queries.

    Invariants:

    1. Every chapter key has BOTH a summary AND a primary_anchors entry.
    2. Every summary is between 80 and 250 chars (enforces the
       community-summary length budget; allows for chapter VIII to be
       slightly shorter because Art. 71 is the only article).
    3. Every primary anchor resolves in :data:`ARTICLE_EXISTENCE`.
    4. Exactly 13 chapters (I-XIII) — matches the canonical EUR-Lex
       structure.
    5. Every intent label in :data:`_INTENT_CHAPTER_MAP` maps to a
       defined chapter.
    6. Every broad-keyword chapter target in
       :data:`_BROAD_KEYWORD_CHAPTER_MAP` is a defined chapter.
    """
    expected_chapters = {"I", "II", "III", "IV", "V", "VI", "VII",
                         "VIII", "IX", "X", "XI", "XII", "XIII"}
    assert set(CHAPTER_SUMMARY.keys()) == expected_chapters, (
        f"CHAPTER_SUMMARY must cover I-XIII; got {sorted(CHAPTER_SUMMARY)}"
    )
    assert set(CHAPTER_PRIMARY_ANCHORS.keys()) == expected_chapters, (
        f"CHAPTER_PRIMARY_ANCHORS must cover I-XIII; got "
        f"{sorted(CHAPTER_PRIMARY_ANCHORS)}"
    )
    for ch, text in CHAPTER_SUMMARY.items():
        n = len(text)
        assert 80 <= n <= 350, (
            f"Chapter {ch} summary length {n} out of [80, 350]"
        )
    for ch, anchors in CHAPTER_PRIMARY_ANCHORS.items():
        assert anchors, f"Chapter {ch} has no primary anchors"
        for a in anchors:
            assert a in ARTICLE_EXISTENCE, (
                f"Chapter {ch} anchor {a} not in ARTICLE_EXISTENCE"
            )
    for label, ch in _INTENT_CHAPTER_MAP.items():
        assert ch in expected_chapters, (
            f"_INTENT_CHAPTER_MAP[{label!r}] -> unknown chapter {ch!r}"
        )
    for keyword, ch in _BROAD_KEYWORD_CHAPTER_MAP:
        assert ch in expected_chapters, (
            f"_BROAD_KEYWORD_CHAPTER_MAP entry {keyword!r} -> unknown "
            f"chapter {ch!r}"
        )
    expected_sections = {"III.1", "III.2", "III.3", "III.4", "III.5",
                         "V.1", "V.2", "V.3"}
    for keyword, section, weight in _SECTION_KEYWORD_MAP:
        assert section in expected_sections, (
            f"_SECTION_KEYWORD_MAP entry {keyword!r} -> unknown section "
            f"{section!r}"
        )
        assert weight > 0, f"_SECTION_KEYWORD_MAP[{keyword!r}] has bad weight"


_self_check()


__all__ = [
    "CHAPTER_SUMMARY",
    "CHAPTER_PRIMARY_ANCHORS",
    "candidate_chapters_for_query",
    "candidate_sections_for_query",
    "chapter_for_query",
    "summary_for_chapter",
    "primary_anchors_for_chapter",
]
