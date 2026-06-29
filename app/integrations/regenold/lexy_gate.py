"""R256 — LLM scope gate for the ambiguous out-of-scope bucket.

A small, fail-soft helper the route consults for the ONE scope-gate
bucket the deterministic classifier cannot resolve: the step-8
``CONVERSATIONAL`` fallback (``ScopeVerdict.ambiguous == True``). A
genuine, keyword-less EU AI Act question ("Does the deep-fake disclosure
duty apply when prosecuting a crime?") and a clearly off-topic request
("What's the best restaurant in Rome?") both land there, so a keyword
classifier cannot tell them apart.

When a Claude Max wrapper provider is wired, :func:`decide_ambiguous_oos`
asks the model a binary question and either

* rescues the genuine question (``in_scope=True``) so the engine answers
  it — closing the R255 false-refusal class without re-enabling the broad
  keyword filter, OR
* confirms the off-topic request and returns a short verb phrase the
  route splices into the tailored Lexy decline ("I cannot *recommend a
  restaurant in Rome* from these materials, …").

Every failure mode (no provider, network error, malformed reply,
exception) returns ``(False, "")`` — refuse with the generic branded
copy. This keeps the route deterministic-safe: with no LLM (the bench /
``cli`` mode) the ambiguous bucket simply refuses, exactly the
topic-filter-ON behaviour, and the davidath bench (all in-scope) never
reaches this code path at all.
"""
from __future__ import annotations

import os
import threading

import structlog

logger = structlog.get_logger(__name__)

# Env gate — default ON. Set ``REGENOLD_LEXY_LLM_GATE=0`` to disable the
# LLM rescue/tailor entirely (the ambiguous bucket then always refuses
# with the generic copy when the topic filter is on).
_ENV_GATE = "REGENOLD_LEXY_LLM_GATE"

# The gate is a tiny binary classification — a short, fast call.
_GATE_TIMEOUT_SECONDS = 2.5
_GATE_MAX_TOKENS = 48

_SYSTEM = (
    "You are a strict scope gate for Lexy, an assistant that ONLY answers "
    "questions about the EU AI Act (Regulation (EU) 2024/1689) and AI "
    "regulatory compliance."
)

# Bounded result cache — identical ambiguous questions recur in
# production (re-asks, retries). Keyed by the raw question; success-only
# puts so a transient failure is retried next time.
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[bool, str]] = {}
_CACHE_MAX = 256


def _gate_enabled() -> bool:
    return os.getenv(_ENV_GATE, "1").strip().lower() in ("1", "true", "yes", "on")


def _build_user(question: str) -> str:
    return (
        f"User message:\n{question.strip()}\n\n"
        "Decide whether this message is a genuine question about the EU AI "
        "Act or AI regulatory compliance.\n"
        "- If YES, reply with exactly: IN_SCOPE\n"
        '- If NO (a greeting, small talk, or a request about any other '
        'topic), reply with: REFUSE: <a 2-7 word verb phrase completing '
        '"I cannot ___", e.g. "recommend a restaurant in Rome" or "tell '
        'you the capital of France">\n'
        "Reply with ONE line only."
    )


def _parse(text: str) -> tuple[bool, str]:
    """Parse the model reply into ``(in_scope, tailored_clause)``."""
    line = ""
    for raw in (text or "").splitlines():
        if raw.strip():
            line = raw.strip()
            break
    low = line.lower()
    if low.startswith("in_scope") or low == "in scope":
        return (True, "")
    if low.startswith("refuse"):
        # Strip the "REFUSE:" / "REFUSE -" prefix, keep the verb phrase.
        clause = line.split(":", 1)[1].strip() if ":" in line else ""
        return (False, clause)
    # Unrecognised shape — fail-soft to the generic refusal.
    return (False, "")


def decide_ambiguous_oos(question: str) -> tuple[bool, str]:
    """Return ``(in_scope, tailored_clause)`` for an ambiguous OOS question.

    ``in_scope=True`` means the route should ANSWER (a genuine AI Act
    question slipped past the keyword gate). ``in_scope=False`` means
    refuse; ``tailored_clause`` (possibly empty) is the verb phrase for
    the tailored Lexy decline. All failures return ``(False, "")``.
    """
    if not question or not question.strip():
        return (False, "")
    if not _gate_enabled():
        return (False, "")

    key = question.strip()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    try:
        # Lazy import — keep the wrapper (and its httpx pool) off the
        # route's import path; only touched when an ambiguous OOS question
        # actually arrives.
        from app.llm.openai_wrapper_provider import (
            OpenAIWrapperRequest,
            get_openai_wrapper_provider,
            is_openai_wrapper_enabled,
        )

        if not is_openai_wrapper_enabled():
            return (False, "")

        provider = get_openai_wrapper_provider()
        resp = provider.complete(
            OpenAIWrapperRequest(
                system=_SYSTEM,
                user=_build_user(key),
                max_tokens=_GATE_MAX_TOKENS,
                temperature=0.0,
                timeout_seconds=_GATE_TIMEOUT_SECONDS,
            )
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft to the generic refusal
        logger.debug("lexy_gate_exception", error=str(exc))
        return (False, "")

    if resp.error or not (resp.text or "").strip():
        logger.debug("lexy_gate_no_text", error=resp.error)
        return (False, "")

    result = _parse(resp.text)
    with _CACHE_LOCK:
        if key not in _CACHE and len(_CACHE) < _CACHE_MAX:
            _CACHE[key] = result
    return result


def reset_cache_for_tests() -> None:
    """Drop the result cache — used by tests to isolate the gate."""
    with _CACHE_LOCK:
        _CACHE.clear()
