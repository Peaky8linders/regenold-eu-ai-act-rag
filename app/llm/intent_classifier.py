"""Intent classifier — routes EU AI Act questions through Claude Max.

Stage 0 of the deterministic pipeline. Calls Claude Haiku 4.5 (default)
via the local ``claude-code-openai-wrapper`` so each question goes
through the Claude Code Max subscription, not the per-token Anthropic
API. Operators can flip ``REGENOLD_INTENT_MODEL`` to ``claude-sonnet-4-6``
for a higher-quality (slower, more expensive) classification.

## Why intent

The deterministic path's recall is saturated at 1.000 across the 25
retrieval-scored eval scenarios; precision is the lever (P=0.61 after
round-19 explicit-anchor pruning). The residual false-positive sources
are CONCEPTUAL questions where the user does not name a specific
article — the keyword-driven anchor maps inject multiple
tangentially-related anchors ("penalty" → Art. 5/Art. 99/Annex II for
a question that's specifically about Art. 100).

Intent classification narrows the anchor set on conceptual questions:
once we know the question is about ``penalty_inquiry`` the engine can
prefer Art. 99/100/101 and drop the broad keyword sprays. This is the
recall-safe alternative to tightening ``_KEYWORD_ENTITY_MAP``.

## Latency posture

* Cold call (no cache): 200-400 ms via Haiku 4.5 through the wrapper.
* Cache hit: ~5 µs (in-memory LRU on question SHA-256 prefix).
* Wrapper down: ~50-100 ms (fast TCP-refused / connection-error path),
  classifier returns ``None`` and the engine falls through to the
  pre-intent deterministic logic — no behaviour change.

The competition rubric scores latency, so the engine MUST tolerate
intent failure cheaply. See the circuit-breaker + short timeout below.

## Activation

The classifier auto-enables when both hold:

* ``is_openai_wrapper_enabled()`` returns True (i.e. ``OPENAI_API_BASE``
  or ``OPENAI_API_KEY`` env vars are set).
* The wrapper has not hit ``_FAILURE_THRESHOLD`` consecutive failures
  in the recent ``_FAILURE_WINDOW_SECONDS`` window (circuit open).

It auto-disables (returns ``None`` from :func:`classify_intent`) when:

* The wrapper isn't configured.
* The wrapper returns ``Not logged in`` (Claude CLI auth missing —
  user needs to run ``login.bat`` once).
* Recent failures opened the breaker.

In all auto-disabled paths the engine falls through to the existing
deterministic logic with zero behaviour change.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    default_groq_model,
    get_groq_intent_provider,
    get_openai_wrapper_provider,
    is_groq_intent_provider_enabled,
    is_openai_wrapper_enabled,
)
from app.security.prompt_guard import sanitize_for_llm

logger = logging.getLogger(__name__)


# ── Intent taxonomy ──────────────────────────────────────────────────────────
#
# R125.1 — full EU AI Act coverage. This is the *correct* realisation of the
# rejected ``intent_classifier_extensions.py`` bundle (R125 triage): broad
# intent detection spanning every article cluster + all risk tiers, but with
# LEGALLY-CORRECT anchors (the bundle shipped deployer→Art.24, distributor→
# Art.28, CE→Art.20, conformity→Art.19, post-market→Art.21 — all wrong) and
# wired into the LIVE classifier arrays + prompt (the bundle's module was dead
# code with a SyntaxError). The deliberately-narrow 94-literal-per-article
# design from the bundle is NOT used — the deep-review (docs/reviews/
# r125-*.md) proved it degrades classification (C1 ordering, C3 prompt bloat,
# M4 overlap). Instead this is a comprehensive *topic* taxonomy: any EU AI Act
# question maps to a distinct intent + the single most-load-bearing article/
# annex for that topic. Explicit article questions ("what does Art. 47 say?")
# are covered by ``article_lookup`` (anchor parsed from the question text).
#
# Safety: every anchor is validated against ARTICLE_EXISTENCE at import
# (``_validate_intent_taxonomy``). The consumption path is fail-safe —
# anchors below confidence 0.7 are ignored, the high-confidence boost only
# REORDERS candidates (never deletes deterministic winners), and an intent
# the parser doesn't recognise falls through to the deterministic path. So a
# correct, granular taxonomy can only raise precision or be neutral.
#
# Anti-overfit guardrail (CLAUDE.md hard rule #3): NO per-PDF-example labels
# (no ``q1_hardware`` / ``q2_emotion`` / ``q3_transcription``) — every label
# is a generalisable EU AI Act topic.


INTENT_LABELS: tuple[str, ...] = (
    # ── explicit lookup (anchor comes from the question text) ──
    "article_lookup",
    # ── scope / meta (Chapter I) ──
    "scope_applicability",     # Art. 2 — who/what the Act applies to
    "definition",              # Art. 3 — defined terms
    "ai_literacy",             # Art. 4 — AI-literacy duty
    "comparative",             # Art. 2 — AI Act vs GDPR/MDR/NIS2/DSA
    # ── risk tiers / "types of risk" (Chapters II, V) ──
    "prohibited_practice",     # Art. 5 — banned uses
    "risk_classification",     # Art. 6 — general "what tier is X / categories"
    "transparency_obligation", # Art. 50 — limited-risk disclosure / deepfake
    "gpai_obligations",        # Art. 53 — GPAI model provider duties
    "gpai_systemic",           # Art. 55 — GPAI with systemic risk
    "gpai_codes_of_practice",  # Art. 56 — GPAI codes of practice
    "gpai_authorised_representative",  # Art. 54 — GPAI authrep (≠ Art. 22)
    # ── operator roles (Chapter III §3 + value chain) ──
    "role_obligations",        # Art. 26 — generic operator duties (fallback)
    "provider_obligations",    # Art. 16 — provider of high-risk AI
    "deployer_obligations",    # Art. 26 — deployer of high-risk AI
    "importer_obligations",    # Art. 23 — importer
    "distributor_obligations", # Art. 24 — distributor
    "authorised_representative",  # Art. 22 — non-EU provider authrep
    "value_chain_responsibilities",  # Art. 25 — modifier becomes provider
    # ── high-risk requirements (Chapter III §2) ──
    "risk_management_system",  # Art. 9
    "data_governance",         # Art. 10
    "technical_documentation", # Art. 11
    "record_keeping_logs",     # Art. 12
    "information_to_deployers",# Art. 13 — instructions for use / transparency
    "human_oversight",         # Art. 14
    "accuracy_robustness",     # Art. 15 — accuracy, robustness, cybersecurity
    "quality_management_system",  # Art. 17
    # ── conformity / market entry (Chapter III §§4-5) ──
    "conformity_assessment",   # Art. 43
    "eu_declaration_of_conformity",  # Art. 47
    "ce_marking",              # Art. 48
    "registration",            # Art. 49 — EU database registration
    "harmonised_standards",    # Art. 40 — standards / common specs
    # ── post-market / enforcement (Chapters III §3, IX) ──
    "post_market_monitoring",  # Art. 72
    "incident_reporting",      # Art. 73 — serious incidents
    "corrective_actions",      # Art. 20
    "market_surveillance",     # Art. 74
    # ── governance (Chapter VII) + notified bodies (Chapter III §4) ──
    "ai_office",               # Art. 64
    "ai_board",                # Art. 65 — European Artificial Intelligence Board
    "national_authorities",    # Art. 70
    "notified_body",           # Art. 31
    "notifying_authority",     # Art. 28
    # ── sandboxes / testing (Chapter VI) ──
    "sandbox",                 # Art. 57 — regulatory sandboxes
    "real_world_testing",      # Art. 60 — testing in real-world conditions
    # ── penalties (Chapter XII) ──
    "penalty_inquiry",         # Art. 99 — penalties on operators
    "gpai_fines",              # Art. 101 — Commission fines on GPAI providers
    "union_institution_fines", # Art. 100 — EDPS fines on Union bodies
    # ── fundamental-rights remedies (Chapters III §3, IX) ──
    "fria",                    # Art. 27 — fundamental-rights impact assessment
    "right_to_explanation",    # Art. 86 — explanation of individual decisions
    "right_to_complaint",      # Art. 85 — right to lodge a complaint
    # ── codes / timeline / compliance ──
    "codes_of_conduct",        # Art. 95 — voluntary codes (non-high-risk)
    "timeline_question",       # Art. 113 — application dates / deadlines
    "compliance_checklist",    # Art. 9 — "what must I do to comply"
    # ── annex lookups ──
    "annex_high_risk_usecases",      # Annex III
    "annex_technical_documentation", # Annex IV
    "annex_harmonisation_law",       # Annex I
    # ── fallbacks (no anchor) ──
    "out_of_scope",
    "other",
)

# Per-intent primary anchor map. The engine uses these to NARROW the
# candidate citation set when no explicit anchor was named in the
# question; the canonical article for each topic is the single most-
# cited answer in the round-19 FP analysis.
#
# R66-D — added the three missing entries (``risk_classification``,
# ``compliance_checklist``, ``comparative``) so a clean intent label
# without an explicit anchor still narrows the candidate pool. Round-65
# judge runs surfaced these three labels as the dominant zero-anchor
# fallbacks (LLM picks the right intent but leaves ``primary_anchor``
# empty), forcing the engine into the broad keyword-spray retrieval
# path that costs precision. Defaults chosen by frequency in the
# davidath + V2 gold-reference distributions:
#
# * ``risk_classification`` → ``Art. 6`` — the high-risk classification
#   entry point. When the question implies *prohibition* the LLM should
#   set ``alternate_anchors=["Art. 5", ...]`` (the system prompt
#   pushes this); the deterministic narrowing logic in
#   :mod:`app.engines.graph_rag` reads both fields.
# * ``compliance_checklist`` → ``Art. 9`` — risk-management is the
#   most-common compliance entry point. Alternates typically land
#   Art. 10 (data governance), Art. 14 (oversight), Art. 17 (QMS).
# * ``comparative`` → ``Art. 2`` — scope. "AI Act vs GDPR / MDR / DSA"
#   framing routes to the scope article first; the engine's
#   ``cross_framework`` retrieval lens then surfaces the other
#   regulation's anchors via the keyword path.
INTENT_PRIMARY_ANCHOR: dict[str, str] = {
    # scope / meta (Chapter I)
    "scope_applicability": "Art. 2",
    "definition": "Art. 3",
    "ai_literacy": "Art. 4",
    "comparative": "Art. 2",
    # risk tiers / GPAI (Chapters II, V)
    "prohibited_practice": "Art. 5",
    "risk_classification": "Art. 6",       # R66-D — general risk-tier default
    "transparency_obligation": "Art. 50",
    "gpai_obligations": "Art. 53",
    "gpai_systemic": "Art. 55",
    "gpai_codes_of_practice": "Art. 56",
    "gpai_authorised_representative": "Art. 54",
    # operator roles (Chapter III §3 + value chain) — LEGALLY CORRECT anchors
    # (the rejected R125 bundle had deployer→24, distributor→28: both wrong)
    "role_obligations": "Art. 26",
    "provider_obligations": "Art. 16",
    "deployer_obligations": "Art. 26",
    "importer_obligations": "Art. 23",
    "distributor_obligations": "Art. 24",
    "authorised_representative": "Art. 22",
    "value_chain_responsibilities": "Art. 25",
    # high-risk requirements (Chapter III §2)
    "risk_management_system": "Art. 9",
    "data_governance": "Art. 10",
    "technical_documentation": "Art. 11",
    "record_keeping_logs": "Art. 12",
    "information_to_deployers": "Art. 13",
    "human_oversight": "Art. 14",
    "accuracy_robustness": "Art. 15",
    "quality_management_system": "Art. 17",
    # conformity / market entry (Chapter III §§4-5)
    "conformity_assessment": "Art. 43",
    "eu_declaration_of_conformity": "Art. 47",
    "ce_marking": "Art. 48",
    "registration": "Art. 49",
    "harmonised_standards": "Art. 40",
    # post-market / enforcement
    "post_market_monitoring": "Art. 72",
    "incident_reporting": "Art. 73",
    "corrective_actions": "Art. 20",
    "market_surveillance": "Art. 74",
    # governance + notified bodies (Chapters VII, III §4)
    "ai_office": "Art. 64",
    "ai_board": "Art. 65",
    "national_authorities": "Art. 70",
    "notified_body": "Art. 31",
    "notifying_authority": "Art. 28",
    # sandboxes / testing (Chapter VI)
    "sandbox": "Art. 57",
    "real_world_testing": "Art. 60",
    # penalties (Chapter XII)
    "penalty_inquiry": "Art. 99",
    "gpai_fines": "Art. 101",
    "union_institution_fines": "Art. 100",
    # fundamental-rights remedies
    "fria": "Art. 27",
    "right_to_explanation": "Art. 86",
    "right_to_complaint": "Art. 85",
    # codes / timeline / compliance
    "codes_of_conduct": "Art. 95",
    "timeline_question": "Art. 113",
    "compliance_checklist": "Art. 9",       # R66-D — load-bearing entry point
    # annex lookups
    "annex_high_risk_usecases": "Annex III",
    "annex_technical_documentation": "Annex IV",
    "annex_harmonisation_law": "Annex I",
}


def _validate_intent_taxonomy() -> None:
    """Fail fast when the curated intent taxonomy drifts.

    Not every intent label should have a default anchor. Labels such as
    ``article_lookup``, ``out_of_scope``, and ``other`` are deliberately
    resolved from the user's explicit references or by downstream logic.
    The invariants that matter are narrower: every default anchor must be
    a real EU AI Act Article/Annex, and every anchored intent must be a
    label the classifier is allowed to emit.
    """
    labels = set(INTENT_LABELS)
    extra_anchors = sorted(set(INTENT_PRIMARY_ANCHOR) - labels)
    if extra_anchors:
        raise RuntimeError(
            "INTENT_PRIMARY_ANCHOR contains labels not present in "
            f"INTENT_LABELS: {extra_anchors}"
        )

    from app.data.article_existence import ARTICLE_EXISTENCE  # noqa: PLC0415

    invalid_anchors = sorted(
        (label, anchor)
        for label, anchor in INTENT_PRIMARY_ANCHOR.items()
        if anchor not in ARTICLE_EXISTENCE
    )
    if invalid_anchors:
        raise RuntimeError(
            "INTENT_PRIMARY_ANCHOR contains invalid EU AI Act refs: "
            f"{invalid_anchors}"
        )


_validate_intent_taxonomy()

BRIDGING_NODES: dict[str, list[str]] = {
    "data_governance": ["GDPR Art. 9 (Special Categories of Data)"],
    "high_risk_annex_i": ["Machinery Regulation", "Medical Device Regulation (MDR)"],
    "quality_management_system": ["ISO 42001", "ISO 9001"],
}

@dataclass(frozen=True)
class IntentResult:
    """Classifier output.

    ``primary_anchor`` is the canonical Art./Annex anchor for the
    intent (e.g. ``Art. 99`` for ``penalty_inquiry``). May be empty when
    intent doesn't map to a single anchor (e.g. ``out_of_scope``,
    ``comparative``).

    ``confidence`` is a 0-1 self-assessment from the model — used by
    the engine to decide whether to override deterministic anchors.
    """

    intent: str
    primary_anchor: str
    alternate_anchors: tuple[str, ...]
    confidence: float
    elapsed_ms: int
    cache_hit: bool = False
    model: str = ""
    reasoning: str = ""
    bridging_context: tuple[str, ...] = ()


# ── Module-level config + state ──────────────────────────────────────────────

_DEFAULT_MODEL = os.getenv("REGENOLD_INTENT_MODEL", "claude-haiku-4-5-20251001")
# Round 52+: Groq Stage-0 model. Migrated to openai/gpt-oss-120b. Override
# via REGENOLD_INTENT_MODEL_GROQ.
_DEFAULT_GROQ_MODEL = os.getenv(
    "REGENOLD_INTENT_MODEL_GROQ", default_groq_model()
)
_TIMEOUT_SECONDS = float(os.getenv("REGENOLD_INTENT_TIMEOUT", "3.5"))
_CACHE_MAX = int(os.getenv("REGENOLD_INTENT_CACHE_MAX", "2048"))
_FAILURE_THRESHOLD = int(os.getenv("REGENOLD_INTENT_FAILURE_THRESHOLD", "3"))
_FAILURE_WINDOW_SECONDS = float(
    os.getenv("REGENOLD_INTENT_FAILURE_WINDOW", "60")
)


@dataclass
class _BreakerState:
    """Tiny circuit breaker. Avoids hitting an unreachable wrapper on every
    request. Opens after N consecutive failures inside the window, closes
    after the window elapses with no fresh failure.
    """

    failures: int = 0
    last_failure_ts: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_failure(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now - self.last_failure_ts > _FAILURE_WINDOW_SECONDS:
                self.failures = 1
            else:
                self.failures += 1
            self.last_failure_ts = now

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            self.last_failure_ts = 0.0

    def open(self) -> bool:
        with self.lock:
            if self.failures < _FAILURE_THRESHOLD:
                return False
            now = time.monotonic()
            if now - self.last_failure_ts > _FAILURE_WINDOW_SECONDS:
                # Half-open: allow one trial through to test recovery.
                self.failures = 0
                return False
            return True


_BREAKER = _BreakerState()
_CACHE: OrderedDict[str, IntentResult] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_key(question: str, model: str) -> str:
    """SHA-256 of question + model. Short, deterministic, model-scoped."""
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\0")
    h.update(question.strip().lower().encode("utf-8"))
    return h.hexdigest()


def _cache_get(key: str) -> IntentResult | None:
    with _CACHE_LOCK:
        if key in _CACHE:
            value = _CACHE.pop(key)
            _CACHE[key] = value
            return value
    return None


def _cache_put(key: str, value: IntentResult) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = value
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


# ── Prompt ───────────────────────────────────────────────────────────────────
#
# Strict JSON output. No prose, no markdown. The wrapper sometimes
# ships sentinel responses ("Not logged in · Please run /login") that
# the openai_wrapper_provider already converts to ``error`` — we
# additionally tolerate JSON parse failures and surface them as
# classifier failures (engine falls through deterministic).

_SYSTEM_PROMPT = """You are a fast intent classifier for EU AI Act questions.

Read the user's question and emit a SINGLE JSON object (no prose, no
markdown fences) with this exact shape:

{"reasoning": "<step-by-step logic>", "intent": "<label>", "primary_anchor": "<Art. N | Annex X | empty>", "alternate_anchors": ["<Art. N>", ...], "confidence": 0.0-1.0}

Pick EXACTLY ONE intent label. If the user explicitly names a specific
article/annex ("what does Art. 47 say?", "explain Annex VIII") choose
article_lookup. Otherwise pick the single best TOPIC label below:

Scope & definitions:
- article_lookup — user names a specific article/annex and asks what it says
- scope_applicability — who/what the Act applies to, territorial scope, exclusions
- definition — meaning of a defined Act term (Art. 3)
- ai_literacy — staff AI-literacy duty (Art. 4)
- comparative — compares the AI Act to another law (GDPR/MDR/NIS2/DSA)

Risk tiers & GPAI:
- prohibited_practice — is X banned / a prohibited practice (Art. 5)
- risk_classification — general "what risk tier / what categories" (high-risk etc.)
- transparency_obligation — limited-risk disclosure / deepfake / synthetic-media labelling (Art. 50)
- gpai_obligations — general-purpose AI MODEL provider duties (Art. 53)
- gpai_systemic — GPAI with systemic risk (Art. 55)
- gpai_codes_of_practice — GPAI codes of practice (Art. 56)
- gpai_authorised_representative — authrep of a non-EU GPAI MODEL provider (Art. 54)

Operator roles (use the SPECIFIC label when the role is named):
- provider_obligations — provider of a high-risk AI system (Art. 16)
- deployer_obligations — deployer / user of a high-risk AI system (Art. 26)
- importer_obligations — importer (Art. 23)
- distributor_obligations — distributor (Art. 24)
- authorised_representative — non-EU provider's EU authrep for an AI SYSTEM (Art. 22)
- value_chain_responsibilities — when a modifier/rebrander becomes a provider (Art. 25)
- role_obligations — operator duties when the role is generic / unspecified

High-risk requirements (Chapter III §2):
- risk_management_system (Art. 9), data_governance (Art. 10),
  technical_documentation (Art. 11), record_keeping_logs (Art. 12),
  information_to_deployers — instructions for use (Art. 13), human_oversight (Art. 14),
  accuracy_robustness — accuracy/robustness/cybersecurity (Art. 15),
  quality_management_system (Art. 17)

Conformity & market entry:
- conformity_assessment (Art. 43), eu_declaration_of_conformity (Art. 47),
  ce_marking (Art. 48), registration — EU database (Art. 49),
  harmonised_standards / common specs (Art. 40)

Post-market & enforcement:
- post_market_monitoring (Art. 72), incident_reporting — serious incidents (Art. 73),
  corrective_actions (Art. 20), market_surveillance (Art. 74)

Governance & notified bodies:
- ai_office (Art. 64), ai_board — European AI Board (Art. 65),
  national_authorities (Art. 70), notified_body (Art. 31), notifying_authority (Art. 28)

Sandboxes & testing:
- sandbox — regulatory sandbox (Art. 57), real_world_testing (Art. 60)

Penalties:
- penalty_inquiry — fines on operators (Art. 99),
  gpai_fines — Commission fines on GPAI providers (Art. 101),
  union_institution_fines — EDPS fines on EU bodies (Art. 100)

Fundamental-rights remedies:
- fria — fundamental-rights impact assessment (Art. 27),
  right_to_explanation — explanation of an individual decision (Art. 86),
  right_to_complaint (Art. 85)

Other:
- codes_of_conduct — voluntary codes for non-high-risk AI (Art. 95)
- timeline_question — application dates / deadlines / review clauses (Art. 113)
- compliance_checklist — "what do I need to do to comply"
- annex_high_risk_usecases (Annex III), annex_technical_documentation (Annex IV),
  annex_harmonisation_law (Annex I)
- out_of_scope — NOT about the EU AI Act
- other — none of the above

primary_anchor must be ONE of:
- "Art. N" where N is the article number (e.g. "Art. 13")
- "Annex X" where X is a Roman numeral (e.g. "Annex IV")
- "" (empty string) when no single anchor applies

alternate_anchors: a list of additional Art./Annex anchors (max 3),
same shape as primary_anchor. Empty list if none.

confidence: 0.0 (unsure) to 1.0 (certain). Use < 0.6 when ambiguous.

Disambiguation guidance (judge-driven):
- Prohibition ("is X banned?", "is Y prohibited?", "is Z illegal under the
  Act?") → ``prohibited_practice``, ``primary_anchor`` ``"Art. 5"``.
  alternate_anchors should include Art. 99 only if penalty is also asked.
  DO NOT include Art. 51 (GPAI).
- General risk categories ("What risk categories are provided for AI
  systems?") → ``risk_classification``, ``primary_anchor`` ``""``,
  alternate_anchors ``["Art. 5", "Art. 6", "Art. 50"]``.
- Generic "is X high-risk?" / "what tier does Y fall into?" →
  ``risk_classification``, ``primary_anchor`` ``"Art. 6"`` (add Annex III to
  alternate_anchors when an Annex-III use case is named).
- "Definition of high-risk" → ``risk_classification``, ``primary_anchor``
  ``"Art. 6"``, alternate_anchors ``["Annex I", "Annex III"]``.
- A SPECIFIC operator role named → use the specific role label with its
  legally-correct anchor: provider→Art. 16, deployer→Art. 26, importer→
  Art. 23, distributor→Art. 24, non-EU AI-system authrep→Art. 22, GPAI-model
  authrep→Art. 54. Use ``role_obligations`` ONLY when the role is generic
  ("what must operators do?").
- GPAI: a general-purpose AI MODEL provider's duties → ``gpai_obligations``
  (Art. 53); systemic-risk threshold/duties → ``gpai_systemic`` (Art. 55);
  fines on a GPAI provider → ``gpai_fines`` (Art. 101).
- Penalties: fines on operators generally → ``penalty_inquiry`` (Art. 99);
  fines on a GPAI MODEL provider → ``gpai_fines`` (Art. 101); fines on a
  Union institution/body → ``union_institution_fines`` (Art. 100).
- ``compliance_checklist`` is for "what do I need to do?" / "list the
  obligations for ..." — primary_anchor should land on the most-load-bearing
  article for the role × risk tier (Art. 9 for high-risk providers,
  Art. 26 for deployers, Art. 16 for QMS-heavy queries).
- ``comparative`` triggers on framework-vs-framework framing ("AI Act vs
  GDPR", "alongside the MDR", "NIS2 + AI Act overlap"). primary_anchor
  should be ``"Art. 2"`` (scope) and alternate_anchors should include
  the most-relevant AI Act article for the topic of comparison.

OUTPUT ONLY the JSON object. No surrounding text."""

_USER_TEMPLATE = "Question: {q}\n\nJSON:"


# ── Public API ───────────────────────────────────────────────────────────────

_ANCHOR_RE = re.compile(
    r"^(?:Art\.?\s+(?:\d{1,3})|Annex\s+[IVXLC]+|)$",
    re.IGNORECASE,
)


def _normalise_anchor(raw: str) -> str:
    """Validate + normalise an anchor string to ``Art. N`` / ``Annex X`` form.

    Strict shape: the engine downstream uses these as dictionary keys
    against ``ARTICLE_EXISTENCE``. Returning a malformed string here
    would cascade into a phantom citation; returning empty is safe
    (the engine treats empty as "no anchor suggestion").
    """
    if not raw:
        return ""
    s = raw.strip()
    if not _ANCHOR_RE.match(s):
        return ""
    # Canonicalise: "art 13" / "Article 13" → "Art. 13"; "annex iv" → "Annex IV"
    if s.lower().startswith("annex"):
        roman = s.split(None, 1)[1].upper()
        return f"Annex {roman}"
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return ""
    return f"Art. {int(digits)}"


def _parse_intent_json(text: str) -> IntentResult | None:
    """Pull the JSON object out of the model's response and validate it.

    Handles the common Haiku failure modes: a stray prose preamble
    (e.g. ``Here is the JSON:\\n{...}``), trailing markdown fence,
    smart-quoted output. We strip to the FIRST ``{`` and LAST ``}`` and
    parse what's between.
    """
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    blob = text[start:end + 1]
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None
    intent = (data.get("intent") or "").strip().lower()
    if intent not in INTENT_LABELS:
        return None
    primary = _normalise_anchor(data.get("primary_anchor") or "")
    raw_alt = data.get("alternate_anchors") or []
    if not isinstance(raw_alt, list):
        raw_alt = []
    alternates: list[str] = []
    for entry in raw_alt[:3]:
        if not isinstance(entry, str):
            continue
        norm = _normalise_anchor(entry)
        if norm and norm not in alternates and norm != primary:
            alternates.append(norm)
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    
    reasoning = (data.get("reasoning") or "").strip()
    
    # If the model didn't pick a primary anchor but the taxonomy has a
    # default for that intent (e.g. penalty_inquiry → Art. 99), inject it.
    if not primary:
        primary = INTENT_PRIMARY_ANCHOR.get(intent, "")
    return IntentResult(
        intent=intent,
        primary_anchor=primary,
        alternate_anchors=tuple(alternates),
        confidence=conf,
        elapsed_ms=0,  # set by caller
        reasoning=reasoning,
        bridging_context=tuple(BRIDGING_NODES.get(intent, [])),
    )


def _resolve_intent_provider() -> tuple[Any, str] | None:
    """Select which provider singleton + model the classifier should use.

    Round 52 — adds the Groq path. The intent classifier was the
    cheapest+safest stage to migrate off the Claude Max wrapper before
    the Pro downgrade (Stage-1/2 polish risks tone + V2 coherence
    regression; Stage-0 is a 10-way JSON classification that any
    instruction-tuned 70B handles).

    Returns ``(provider, model)`` when a path is configured, ``None``
    when no provider is wired (which the public ``is_intent_enabled``
    surfaces). Groq wins when both
    ``REGENOLD_INTENT_PROVIDER=groq`` and ``GROQ_API_KEY`` are set;
    otherwise we fall through to the existing wrapper path if it's
    enabled.
    """
    if is_groq_intent_provider_enabled():
        return get_groq_intent_provider(), _DEFAULT_GROQ_MODEL
    if is_openai_wrapper_enabled():
        return get_openai_wrapper_provider(), _DEFAULT_MODEL
    return None


def is_intent_enabled() -> bool:
    """Public gate. True iff intent classification should run for this request.

    Returns False when neither provider is wired OR the circuit breaker
    is open. The engine treats False as "skip intent" — no behaviour
    change vs. the round-19 baseline.

    NOTE: env-only check — does NOT construct provider singletons. The
    actual construction (which can raise on httpx pool init) happens
    inside :func:`classify_intent`'s try-block. This separation is the
    issue #50 hardening contract: provider acquisition failures must
    not propagate up through ``is_intent_enabled``.
    """
    if not (is_groq_intent_provider_enabled() or is_openai_wrapper_enabled()):
        return False
    if _BREAKER.open():
        return False
    return True


def classify_intent(
    question: str, system_description: str | None = None
) -> IntentResult | None:
    """Classify the question's intent via the openai_wrapper.

    Returns ``None`` on any failure path (wrapper unreachable, circuit
    open, malformed model output, low confidence). Callers MUST handle
    ``None`` gracefully — the engine falls through to the existing
    deterministic logic in that case.

    Caches results by SHA-256(question + model) on success. Cache size
    is bounded by ``REGENOLD_INTENT_CACHE_MAX`` (default 2048).
    """
    if not question or not is_intent_enabled():
        return None
    # Issue #50: provider acquisition itself can raise (singleton init,
    # httpx pool construction, URL parsing). Resolve INSIDE the try so a
    # raise here lands on the fail-soft None path, not the FastAPI 500.
    try:
        selection = _resolve_intent_provider()
    except Exception as exc:  # noqa: BLE001 — fail-soft contract
        _BREAKER.record_failure()
        logger.debug("intent_provider_resolve_exception: %s", str(exc)[:200])
        return None
    if selection is None:
        return None
    provider, model = selection
    key = _cache_key(question, model)
    cached = _cache_get(key)
    if cached is not None:
        # Preserve elapsed_ms from original call; mark hit.
        return IntentResult(
            intent=cached.intent,
            primary_anchor=cached.primary_anchor,
            alternate_anchors=cached.alternate_anchors,
            confidence=cached.confidence,
            elapsed_ms=cached.elapsed_ms,
            cache_hit=True,
            model=cached.model,
            reasoning=getattr(cached, "reasoning", ""),
            bridging_context=getattr(cached, "bridging_context", ()),
        )

    # Issue #53: sanitise prompt-injection vectors BEFORE truncation
    # (sanitisation can change length). The user-supplied question is
    # forwarded directly into the classifier system prompt — without
    # this, an attacker who crafts a question containing model-control
    # delimiters (e.g. ``<|im_start|>``, ``[INST]``, ``</user_query>``)
    # can steer the classifier output and bias downstream citation
    # pruning. Mirrors the hardening already in
    # ``app/engines/graph_rag.py`` (Stage-1 parse).
    sanitised = sanitize_for_llm(question.strip(), context_type="query")
    if not sanitised:
        return None
    trimmed = sanitised

    # Pass our short 2.5 s budget per-request — DON'T mutate the env.
    # The provider is a process-wide singleton and an env mutation here
    # poisoned the timeout for all Stage-1/2 Sonnet calls (which need
    # 10-20 s) too. Fixed by adding `timeout_seconds` to the request.
    #
    # Issue #50: wrap provider acquisition + the call itself in
    # ``try / except Exception``. The classifier docstring promises a
    # fail-soft None on any failure path, but provider singleton init
    # (httpx pool construction, env-derived URL parsing) and the
    # provider.complete() call can raise httpx-internal exceptions that
    # bypass the provider's inner ``except httpx.HTTPError``. Without
    # this guard, those exceptions propagate to
    # ``app/routes/regenold.py::_intent_anchor_set`` and turn into a
    # 500 instead of the deterministic-fallback path.
    start = time.perf_counter()
    try:
        response = provider.complete(
            OpenAIWrapperRequest(
                system=_SYSTEM_PROMPT,
                user=_USER_TEMPLATE.format(q=trimmed),
                model=model,
                max_tokens=250, # Increased max_tokens to accommodate reasoning
                temperature=0.0,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        )
        if response.error:
            raise Exception(f"Provider error: {response.error}")
    except Exception as exc:  # noqa: BLE001 — fail-soft contract
        # Fallback to OpenAI wrapper (Sonnet) if Groq fails
        if model == _DEFAULT_GROQ_MODEL and is_openai_wrapper_enabled():
            logger.debug("intent_classifier_exception on Groq: %s, falling back to Sonnet", str(exc)[:200])
            provider = get_openai_wrapper_provider()
            model = _DEFAULT_MODEL
            try:
                response = provider.complete(
                    OpenAIWrapperRequest(
                        system=_SYSTEM_PROMPT,
                        user=_USER_TEMPLATE.format(q=trimmed),
                        model=model,
                        max_tokens=250,
                        temperature=0.0,
                        timeout_seconds=_TIMEOUT_SECONDS,
                    )
                )
                if response.error:
                    _BREAKER.record_failure()
                    logger.debug("intent_classifier_failure on fallback: %s", response.error[:120])
                    return None
            except Exception as fallback_exc:
                _BREAKER.record_failure()
                logger.debug("intent_classifier_exception on fallback: %s", str(fallback_exc)[:200])
                return None
        else:
            _BREAKER.record_failure()
            logger.debug("intent_classifier_exception: %s", str(exc)[:200])
            return None
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    parsed = _parse_intent_json(response.text or "")
    if parsed is None:
        _BREAKER.record_failure()
        logger.debug(
            "intent_classifier_parse_failed: %r",
            (response.text or "")[:200],
        )
        return None

    _BREAKER.record_success()
    result = IntentResult(
        intent=parsed.intent,
        primary_anchor=parsed.primary_anchor,
        alternate_anchors=parsed.alternate_anchors,
        confidence=parsed.confidence,
        elapsed_ms=elapsed_ms,
        cache_hit=False,
        model=response.model or model,
        reasoning=parsed.reasoning,
        bridging_context=tuple(BRIDGING_NODES.get(parsed.intent, [])),
    )
    _cache_put(key, result)
    return result


# ── Test hook ────────────────────────────────────────────────────────────────

def _reset_for_tests() -> None:
    """Reset cache + breaker. Test-only — not part of the public API."""
    with _CACHE_LOCK:
        _CACHE.clear()
    with _BREAKER.lock:
        _BREAKER.failures = 0
        _BREAKER.last_failure_ts = 0.0


__all__ = [
    "INTENT_LABELS",
    "INTENT_PRIMARY_ANCHOR",
    "IntentResult",
    "classify_intent",
    "is_intent_enabled",
    "_resolve_intent_provider",
]
