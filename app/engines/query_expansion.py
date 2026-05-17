"""RAG-Fusion query expansion + reciprocal rank fusion (R39 / B8, R40 hardened).

When the wrapper is wired, ask Haiku 4.5 for 3 paraphrases of the user's
question. Each paraphrase runs through the existing retrieval stack
independently; reciprocal rank fusion (RRF) combines the result lists.

Fail-soft: wrapper disabled / circuit open / any exception → return
[original] only (or `[]` from :func:`expand_query` for the paraphrase-
only public API).

R40 hardening (eng-review F10):

1. ``start = time.perf_counter()`` moved BEFORE the try block so the
   ``except`` branch can reference it for elapsed-time logging.
2. Success-only LRU cache (max 256 entries) keyed on SHA-256 of the
   trimmed question. Caches the list of paraphrases. Mirrors the
   success-only pattern in :mod:`app.llm.intent_classifier`; we NEVER
   cache failure paths (cache poisoning risk).
3. Circuit breaker with the same shape as the intent classifier — open
   after 3 consecutive failures inside a 60-second window, half-open
   after the window elapses with no fresh failure.
4. Public entry point ``expand_query(question)`` returns AT MOST 3
   paraphrases (the new wire-side contract — the original question is
   added separately by the caller). Never raises.
5. ``is_query_expansion_enabled()`` gates the call on the wrapper being
   wired AND the breaker being closed. No new env flag.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Iterable

from app.llm.openai_wrapper_provider import (
    OpenAIWrapperRequest,
    get_openai_wrapper_provider,
    is_openai_wrapper_enabled,
)

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You generate 2-3 paraphrases of EU AI Act questions for retrieval "
    "expansion. Each paraphrase keeps the same factual question but "
    "varies phrasing (formal/informal, specific/general). Respond with "
    'STRICT JSON: {"paraphrases": ["...", "..."]}. No prose.'
)

_USER_TEMPLATE = "Question: {q}\n\nReturn 2-3 paraphrases as JSON."

_TIMEOUT = 2.0  # short budget — paraphrase is opportunistic
_MODEL = "claude-haiku-4-5-20251001"
_MAX_PARAPHRASES = 3
_CACHE_MAX = 256
_FAILURE_THRESHOLD = 3
_FAILURE_WINDOW_SECONDS = 60.0


# ── Circuit breaker ──────────────────────────────────────────────────────────


@dataclass
class _BreakerState:
    """Tiny circuit breaker.

    Mirrors the shape used by :mod:`app.llm.intent_classifier`. Opens
    after ``_FAILURE_THRESHOLD`` consecutive failures inside the window,
    closes after the window elapses with no fresh failure (half-open:
    one trial through after the window).
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
                # Half-open — allow one trial through to test recovery.
                self.failures = 0
                return False
            return True


_BREAKER = _BreakerState()


# ── LRU cache (success-only) ─────────────────────────────────────────────────
#
# Keyed on SHA-256(trimmed_lower_question). Value is a list of
# paraphrases (NOT including the original). Lock-protected. Never cache
# failures — a transient wrapper outage that returned [] must not freeze
# the expansion path for the lifetime of the process. Mirrors the
# success-only pattern in ``clara_logic._LLM_CACHE`` /
# ``intent_classifier._CACHE``.

_CACHE: "OrderedDict[str, list[str]]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_key(question: str) -> str:
    h = hashlib.sha256()
    h.update(question.strip().lower().encode("utf-8"))
    return h.hexdigest()


def _cache_get(key: str) -> list[str] | None:
    with _CACHE_LOCK:
        if key in _CACHE:
            value = _CACHE.pop(key)
            _CACHE[key] = value
            # Defensive copy so callers can't mutate the cached value.
            return list(value)
    return None


def _cache_put(key: str, value: list[str]) -> None:
    if not value:
        # NEVER cache empties — they're indistinguishable from "wrapper
        # returned junk" failures and would poison subsequent calls.
        return
    with _CACHE_LOCK:
        _CACHE[key] = list(value)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


# ── Public gate ──────────────────────────────────────────────────────────────


def is_query_expansion_enabled() -> bool:
    """True iff query expansion should run for this request.

    Returns False when the wrapper isn't wired OR the circuit breaker
    is open. Callers should bail before any LLM-flavoured work.
    """
    if not is_openai_wrapper_enabled():
        return False
    if _BREAKER.open():
        return False
    return True


# ── Public API ───────────────────────────────────────────────────────────────


def expand_query(question: str) -> list[str]:
    """Return up to 3 paraphrases of ``question`` via Haiku 4.5.

    R40 wire-side contract: returns paraphrases ONLY (the original is
    folded in by the caller — see
    :func:`app.data.kb_search.top_articles_by_relevance`). Returns ``[]``
    on any failure path (wrapper down, circuit open, parse error,
    timeout, malformed JSON).

    Cached by SHA-256(question) on success. NEVER raises.
    """
    if not question or not is_query_expansion_enabled():
        return []
    trimmed = question.strip()
    if not trimmed:
        return []
    key = _cache_key(trimmed)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # IMPORTANT (F10 fix): start the timer BEFORE the try block so the
    # ``except`` branch can reference it for elapsed-time logging.
    start = time.perf_counter()
    try:
        provider = get_openai_wrapper_provider()
        resp = provider.complete(OpenAIWrapperRequest(
            system=_SYSTEM_PROMPT,
            user=_USER_TEMPLATE.format(q=trimmed[:1000]),
            model=_MODEL,
            max_tokens=200,
            temperature=0.3,
            timeout_seconds=_TIMEOUT,
        ))
    except Exception as exc:  # noqa: BLE001 — fail-soft
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        _BREAKER.record_failure()
        logger.debug(
            "query_expansion_exception: %s (elapsed %d ms)",
            str(exc)[:160], elapsed_ms,
        )
        return []

    if resp.error:
        _BREAKER.record_failure()
        logger.debug("query_expansion_provider_error: %s", resp.error[:160])
        return []

    paraphrases: list[str] = []
    try:
        text = (resp.text or "").strip()
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            _BREAKER.record_failure()
            return []
        data = json.loads(text[start_idx:end_idx + 1])
        raw_list = data.get("paraphrases") if isinstance(data, dict) else None
        if not isinstance(raw_list, list):
            _BREAKER.record_failure()
            return []
        for entry in raw_list:
            if len(paraphrases) >= _MAX_PARAPHRASES:
                break
            if not isinstance(entry, str):
                continue
            p = entry.strip()
            if p and p != trimmed and p not in paraphrases:
                paraphrases.append(p)
    except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
        _BREAKER.record_failure()
        return []

    if not paraphrases:
        # Treat as a failure — the model returned a valid JSON envelope
        # but no usable paraphrases. Don't cache; don't claim success.
        _BREAKER.record_failure()
        return []

    _BREAKER.record_success()
    _cache_put(key, paraphrases)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.debug(
        "query_expansion_ok: %d paraphrases in %d ms",
        len(paraphrases), elapsed_ms,
    )
    return paraphrases


def reciprocal_rank_fusion(
    ranked_lists: Iterable[Iterable[str]],
    k: int = 60,
) -> list[str]:
    """Combine multiple ranked lists via RRF.

    score(d) = sum_l 1 / (k + rank_l(d)). Default k=60 per the
    canonical Cormack et al. 2009 paper.
    """
    scores: dict[str, float] = {}
    insertion_order: dict[str, int] = {}
    n_inserted = 0
    for lst in ranked_lists:
        for rank, doc in enumerate(lst, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
            if doc not in insertion_order:
                insertion_order[doc] = n_inserted
                n_inserted += 1
    return sorted(scores.keys(), key=lambda d: (-scores[d], insertion_order[d]))


# ── Test hook ────────────────────────────────────────────────────────────────


def _reset_for_tests() -> None:
    """Reset cache + breaker. Test-only — not part of the public API."""
    with _CACHE_LOCK:
        _CACHE.clear()
    with _BREAKER.lock:
        _BREAKER.failures = 0
        _BREAKER.last_failure_ts = 0.0


__all__ = [
    "expand_query",
    "is_query_expansion_enabled",
    "reciprocal_rank_fusion",
]
