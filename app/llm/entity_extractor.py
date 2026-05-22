"""Entity extractor — stage-0.5 LLM article extraction for novel phrasings.

Fires inside ``_deterministic_parse()`` ONLY when the keyword map and
regex extraction return zero entities, BEFORE the chapter-scoped BM25
fallback (Optimization 1). Claude Haiku 4.5 (or Groq Llama 3.3 70B)
reads the question and extracts 1-3 canonical article references for
questions like "How long must records be retained?" or "Can AI assess
employees?" that share no literal tokens with the 370-entry keyword map.

## Why stage-0.5 vs extending the keyword map

The keyword map has ~370 literal phrases. Every new entry requires a
human to decide which article it maps to and to verify it does not
over-trigger. The tail of novel phrasings is unbounded. An LLM at
stage-0.5 generalises across paraphrases at inference time; it fires
only after the keyword map has already been tried (precision-safe) and
returns an empty list when uncertain (fail-soft).

## Activation

Auto-enables when a provider is wired:

* ``is_openai_wrapper_enabled()`` is True — uses the local Claude Max
  wrapper at 127.0.0.1:8000.
* ``is_groq_intent_provider_enabled()`` is True — uses Groq Llama 3.3
  70B at api.groq.com.

Disable explicitly via ``REGENOLD_ENTITY_EXTRACTOR=0``. The env gate
defaults to ``1`` (enabled) so that production deploys with a provider
wired activate the path automatically. The bench is unaffected because
the bench runner has no wrapper configured (neither env var set), so
``is_entity_extractor_enabled()`` returns False on the bench.

## Latency budget

* Cold call (no cache): 200-400 ms via Haiku 4.5.
* Cache hit: ~5 µs (in-memory LRU on SHA-256(question)).
* Provider down / circuit open: <1 ms (fail-soft None path).
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

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    get_groq_intent_provider,
    get_openai_wrapper_provider,
    is_groq_intent_provider_enabled,
    is_openai_wrapper_enabled,
)
from app.security.prompt_guard import sanitize_for_llm

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntityExtractionResult:
    """Structured output from the entity extractor LLM call."""

    articles: tuple[str, ...]  # validated canonical refs ("Art. N" / "Annex X")
    confidence: float          # 0.0–1.0 self-assessment from the model
    elapsed_ms: int
    cache_hit: bool = False
    model: str = ""


# ── Module-level config ───────────────────────────────────────────────────────

_DEFAULT_MODEL = os.getenv("REGENOLD_ENTITY_MODEL", "claude-haiku-4-5-20251001")
_DEFAULT_GROQ_MODEL = os.getenv(
    "REGENOLD_ENTITY_MODEL_GROQ", "llama-3.3-70b-versatile"
)
_TIMEOUT_SECONDS = float(os.getenv("REGENOLD_ENTITY_TIMEOUT", "2.5"))
_CACHE_MAX = int(os.getenv("REGENOLD_ENTITY_CACHE_MAX", "1024"))
_FAILURE_THRESHOLD = int(os.getenv("REGENOLD_ENTITY_FAILURE_THRESHOLD", "3"))
_FAILURE_WINDOW_SECONDS = float(
    os.getenv("REGENOLD_ENTITY_FAILURE_WINDOW", "60")
)
_MIN_CONFIDENCE = float(os.getenv("REGENOLD_ENTITY_MIN_CONFIDENCE", "0.6"))
# Env gate — ``0`` to disable even when provider is wired.
_ENABLED_ENV = os.getenv("REGENOLD_ENTITY_EXTRACTOR", "1").strip().lower()
_ENABLED_BY_ENV = _ENABLED_ENV not in ("0", "false", "no", "off")


# ── Circuit breaker ───────────────────────────────────────────────────────────


@dataclass
class _BreakerState:
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
                self.failures = 0
                return False
            return True


_BREAKER = _BreakerState()
_CACHE: "OrderedDict[str, EntityExtractionResult]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_key(question: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(b"entity_extractor\0")
    h.update(model.encode("utf-8"))
    h.update(b"\0")
    h.update(question.strip().lower().encode("utf-8"))
    return h.hexdigest()


def _cache_get(key: str) -> EntityExtractionResult | None:
    with _CACHE_LOCK:
        if key in _CACHE:
            value = _CACHE.pop(key)
            _CACHE[key] = value
            return value
    return None


def _cache_put(key: str, value: EntityExtractionResult) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = value
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


# ── Prompt ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an EU AI Act expert. Given a question, identify the 1-3 most relevant EU AI Act articles or annexes.

Output ONLY a JSON object (no prose, no markdown):
{"articles": ["Art. N", ...], "confidence": 0.0-1.0}

Rules:
- Each entry must be "Art. N" (Arabic numeral, e.g. "Art. 5") or "Annex X" (Roman numeral, e.g. "Annex III")
- List 1-3 entries, most relevant first
- confidence < 0.6 when genuinely uncertain about which article applies

Quick reference:
- Art. 3: Definitions of key terms
- Art. 5: Prohibited practices (subliminal manipulation, biometrics, social scoring, scraping)
- Art. 6 + Annex III: High-risk AI classification criteria
- Art. 9: Risk management system (high-risk AI providers)
- Art. 10: Training data governance (high-risk AI)
- Art. 12: Record-keeping / logging obligations (high-risk AI)
- Art. 13: Transparency and provision of information (high-risk AI)
- Art. 14: Human oversight (high-risk AI)
- Art. 15: Accuracy, robustness, cybersecurity (high-risk AI)
- Art. 16-25: Provider obligations (QMS, technical docs, registration, authorised rep)
- Art. 26: Deployer obligations
- Art. 27: Fundamental Rights Impact Assessment (FRIA)
- Art. 40-49: Conformity assessment, notified bodies, CE marking
- Art. 50: Limited-risk transparency (chatbots, deepfakes, synthetic media)
- Art. 51-55: General-purpose AI (GPAI) obligations and systemic risk
- Art. 57-61: Regulatory sandboxes and innovation support
- Art. 62-63: SME / startup provisions
- Art. 70-79: Market surveillance and post-market monitoring
- Art. 99-101: Penalties and fines
- Annex I: AI techniques and approaches (definition of AI system)
- Annex III: High-risk AI use cases (biometrics, infrastructure, education, employment, etc.)
- Annex IV: Technical documentation requirements

Examples:
Q: "How long must high-risk AI system logs be retained?" -> {"articles": ["Art. 12", "Art. 19"], "confidence": 0.9}
Q: "Can AI screen job applicants for hiring?" -> {"articles": ["Annex III", "Art. 6", "Art. 26"], "confidence": 0.88}
Q: "What disclosures are required when deploying a chatbot?" -> {"articles": ["Art. 50"], "confidence": 0.95}
Q: "What is the compute threshold for GPAI systemic risk?" -> {"articles": ["Art. 51", "Art. 55"], "confidence": 0.92}
Q: "Do we need a CE mark for our AI system?" -> {"articles": ["Art. 49", "Art. 43"], "confidence": 0.87}

OUTPUT ONLY the JSON object."""

_USER_TEMPLATE = "Question: {q}\n\nJSON:"

# ── Validation ────────────────────────────────────────────────────────────────

_ARTICLE_SHAPE_RE = re.compile(
    r"^(?:Art\.\s*\d{1,3}|Annex\s+[IVXLC]+)$",
    re.IGNORECASE,
)


def _normalise_article(raw: str) -> str | None:
    """Validate and normalise to 'Art. N' or 'Annex X'. Returns None on bad shape."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not _ARTICLE_SHAPE_RE.match(s):
        return None
    if s.lower().startswith("annex"):
        parts = s.split(None, 1)
        if len(parts) < 2:
            return None
        roman = parts[1].upper()
        return f"Annex {roman}"
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return None
    return f"Art. {int(digits)}"


def _parse_extraction_json(text: str) -> EntityExtractionResult | None:
    """Extract and validate the JSON from the model response."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    blob = text[start : end + 1]
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None

    raw_articles = data.get("articles") or []
    if not isinstance(raw_articles, list):
        return None

    # Import lazily to avoid circular at module load.
    try:
        from app.data.article_existence import ARTICLE_EXISTENCE  # noqa: PLC0415
    except ImportError:
        ARTICLE_EXISTENCE = None  # type: ignore[assignment]

    validated: list[str] = []
    for entry in raw_articles[:3]:
        if not isinstance(entry, str):
            continue
        norm = _normalise_article(entry)
        if norm is None:
            continue
        # Reject hallucinated refs that don't appear in the canonical catalog.
        if ARTICLE_EXISTENCE is not None and norm not in ARTICLE_EXISTENCE:
            logger.debug("entity_extractor_invalid_ref rejected: %r", norm)
            continue
        if norm not in validated:
            validated.append(norm)

    if not validated:
        return None

    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    return EntityExtractionResult(
        articles=tuple(validated),
        confidence=conf,
        elapsed_ms=0,
        cache_hit=False,
    )


# ── Provider resolution ───────────────────────────────────────────────────────


def _resolve_provider():  # type: ignore[return]
    """Select provider + model. Mirrors intent_classifier._resolve_intent_provider."""
    if is_groq_intent_provider_enabled():
        return get_groq_intent_provider(), _DEFAULT_GROQ_MODEL
    if is_openai_wrapper_enabled():
        return get_openai_wrapper_provider(), _DEFAULT_MODEL
    return None


# ── Public gate + API ─────────────────────────────────────────────────────────


def is_entity_extractor_enabled() -> bool:
    """True iff LLM entity extraction should run for this request.

    Checks the env gate, then whether any provider is configured, then
    the circuit breaker state. Never constructs singletons (issue #50
    hardening contract).
    """
    if not _ENABLED_BY_ENV:
        return False
    if not (is_groq_intent_provider_enabled() or is_openai_wrapper_enabled()):
        return False
    if _BREAKER.open():
        return False
    return True


def extract_entities(question: str) -> list[str]:
    """Return 1-3 validated article refs for ``question``, or [] on any failure.

    Fires only when :func:`is_entity_extractor_enabled` is True and the
    model has confidence >= ``_MIN_CONFIDENCE``. All failure paths return
    ``[]`` — callers MUST handle empty gracefully.
    """
    if not question or not is_entity_extractor_enabled():
        return []
    try:
        selection = _resolve_provider()
    except Exception as exc:  # noqa: BLE001
        _BREAKER.record_failure()
        logger.debug("entity_extractor_provider_resolve_failed: %s", str(exc)[:200])
        return []
    if selection is None:
        return []
    provider, model = selection

    sanitised = sanitize_for_llm(question.strip(), context_type="query")
    if not sanitised:
        return []
    trimmed = sanitised[-1500:] if len(sanitised) > 1500 else sanitised

    key = _cache_key(trimmed, model)
    cached = _cache_get(key)
    if cached is not None:
        if cached.confidence >= _MIN_CONFIDENCE:
            return list(cached.articles)
        return []

    start = time.perf_counter()
    try:
        response = provider.complete(
            OpenAIWrapperRequest(
                system=_SYSTEM_PROMPT,
                user=_USER_TEMPLATE.format(q=trimmed),
                model=model,
                max_tokens=80,
                temperature=0.0,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _BREAKER.record_failure()
        logger.debug("entity_extractor_call_exception: %s", str(exc)[:200])
        return []
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if response.error:
        _BREAKER.record_failure()
        logger.debug("entity_extractor_error: %s", response.error[:120])
        return []

    parsed = _parse_extraction_json(response.text or "")
    if parsed is None:
        _BREAKER.record_failure()
        logger.debug(
            "entity_extractor_parse_failed: %r",
            (response.text or "")[:200],
        )
        return []

    _BREAKER.record_success()
    result = EntityExtractionResult(
        articles=parsed.articles,
        confidence=parsed.confidence,
        elapsed_ms=elapsed_ms,
        cache_hit=False,
        model=response.model or model,
    )
    _cache_put(key, result)

    if result.confidence < _MIN_CONFIDENCE:
        logger.debug(
            "entity_extractor_low_confidence: conf=%.2f articles=%s",
            result.confidence, result.articles,
        )
        return []

    logger.debug(
        "entity_extractor_hit: articles=%s conf=%.2f elapsed_ms=%d",
        result.articles, result.confidence, elapsed_ms,
    )
    return list(result.articles)


# ── Test hook ─────────────────────────────────────────────────────────────────


def _reset_for_tests() -> None:
    """Reset cache + breaker. Test-only."""
    with _CACHE_LOCK:
        _CACHE.clear()
    with _BREAKER.lock:
        _BREAKER.failures = 0
        _BREAKER.last_failure_ts = 0.0


__all__ = [
    "EntityExtractionResult",
    "extract_entities",
    "is_entity_extractor_enabled",
    "_reset_for_tests",
]
