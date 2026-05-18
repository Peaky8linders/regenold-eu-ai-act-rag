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
    get_groq_intent_provider,
    get_openai_wrapper_provider,
    is_groq_intent_provider_enabled,
    is_openai_wrapper_enabled,
)
from app.security.prompt_guard import sanitize_for_llm

logger = logging.getLogger(__name__)


# ── Intent taxonomy ──────────────────────────────────────────────────────────
#
# Coarse 10-way classification. Each label maps to ONE primary article /
# annex anchor (or a short set for the small ``role_obligations`` /
# ``gpai_systemic`` clusters). The engine reads ``intent.primary_anchor``
# to narrow the candidate citation set on conceptual questions.
#
# Anti-overfit guardrail: the taxonomy intentionally avoids
# per-PDF-example labels (no ``q1_hardware``, ``q2_emotion``,
# ``q3_transcription``). CLAUDE.md hard rule #3 — generalisation > overfit.


INTENT_LABELS: tuple[str, ...] = (
    "article_lookup",
    "risk_classification",
    "role_obligations",
    "definition",
    "penalty_inquiry",
    "timeline_question",
    "transparency_obligation",
    "incident_reporting",
    "sandbox",
    "gpai_systemic",
    "fria",
    "comparative",
    "compliance_checklist",
    "out_of_scope",
    "other",
)

# Per-intent primary anchor map. The engine uses these to NARROW the
# candidate citation set when no explicit anchor was named in the
# question; the canonical article for each topic is the single most-
# cited answer in the round-19 FP analysis.
INTENT_PRIMARY_ANCHOR: dict[str, str] = {
    "penalty_inquiry": "Art. 99",
    "transparency_obligation": "Art. 50",
    "incident_reporting": "Art. 73",
    "sandbox": "Art. 57",
    "fria": "Art. 27",
    "gpai_systemic": "Art. 55",
    "role_obligations": "Art. 26",
    "definition": "Art. 3",
    "timeline_question": "Art. 113",
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


# ── Module-level config + state ──────────────────────────────────────────────

_DEFAULT_MODEL = os.getenv("REGENOLD_INTENT_MODEL", "claude-haiku-4-5-20251001")
# Round 52: Groq fallback model. Llama 3.3 70B Versatile is the most-tested
# Groq endpoint for legal-RAG tasks (per Reddit r/legaltech Oct 2025
# survey + Vals.ai LegalBench). Override via REGENOLD_INTENT_MODEL_GROQ.
_DEFAULT_GROQ_MODEL = os.getenv(
    "REGENOLD_INTENT_MODEL_GROQ", "llama-3.3-70b-versatile"
)
_TIMEOUT_SECONDS = float(os.getenv("REGENOLD_INTENT_TIMEOUT", "2.5"))
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
_CACHE: "OrderedDict[str, IntentResult]" = OrderedDict()
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

{"intent": "<label>", "primary_anchor": "<Art. N | Annex X | empty>", "alternate_anchors": ["<Art. N>", ...], "confidence": 0.0-1.0}

Valid intent labels (pick exactly one):
- article_lookup        — user explicitly names an article/annex and asks what it says
- risk_classification   — user asks if X is prohibited / high-risk / limited / minimal
- role_obligations      — user asks about provider / deployer / importer / distributor duties
- definition            — user asks for a definition of an Act term
- penalty_inquiry       — user asks about fines / sanctions / max penalty
- timeline_question     — user asks about applicability dates / deadlines / review clauses
- transparency_obligation — user asks about Art. 50 disclosure / deepfake labelling / synthetic media marking
- incident_reporting    — user asks about serious incident reporting (Art. 73)
- sandbox               — user asks about regulatory sandboxes / testing (Arts. 57-61)
- gpai_systemic         — user asks about GPAI / general-purpose AI / systemic risk (Arts. 51-55)
- fria                  — user asks about Fundamental Rights Impact Assessment (Art. 27)
- comparative           — user compares the EU AI Act to another regulation (GDPR, DMA, etc.)
- compliance_checklist  — user asks "what do I need to do to comply"
- out_of_scope          — question is NOT about the EU AI Act
- other                 — falls through

primary_anchor must be ONE of:
- "Art. N" where N is the article number (e.g. "Art. 13")
- "Annex X" where X is a Roman numeral (e.g. "Annex IV")
- "" (empty string) when no single anchor applies

alternate_anchors: a list of additional Art./Annex anchors (max 3),
same shape as primary_anchor. Empty list if none.

confidence: 0.0 (unsure) to 1.0 (certain). Use < 0.6 when ambiguous.

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
    if len(trimmed) > 1500:
        trimmed = trimmed[-1500:]

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
                max_tokens=160,
                temperature=0.0,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft contract
        _BREAKER.record_failure()
        logger.debug("intent_classifier_exception: %s", str(exc)[:200])
        return None
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if response.error:
        _BREAKER.record_failure()
        logger.debug("intent_classifier_failure: %s", response.error[:120])
        return None

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
