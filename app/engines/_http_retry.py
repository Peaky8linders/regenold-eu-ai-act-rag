"""R407 — shared transient-failure retry for the Cohere HTTP clients.

Why: the deep-code review (docs/reviews/) found that both Cohere clients
(``cohere_rerank.rerank_documents``, ``external_embeddings.get_embedding``)
paid ONE POST per logical call, so a single transient 429/5xx (trial keys
rate-limit at 10 calls/min) silently degraded that retrieval step — and in a
fail-closed eval run (``--require-cohere``) it killed the whole 110-row
capture (measured twice in r406). This module gives both clients the same
bounded retry: exponential backoff, ``Retry-After`` honoured (capped), only
retrying statuses that are actually transient.

Contract preserved: callers keep their fail-open (production) / fail-closed
(eval guard) semantics — this helper never raises and never retries a
permanent 4xx.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable

logger = logging.getLogger(__name__)

#: Worth retrying: rate limits (429) and transient upstream failures (5xx).
#: 4xx authorization/model errors are permanent — fail immediately.
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

_BASE_DELAY_S = 2.0
_MAX_DELAY_S = 20.0
_MAX_ATTEMPTS_CAP = 5


def attempts_from_env(env: str, default: int) -> int:
    """Fresh-read the retry-attempt ceiling from ``env``.

    ``<1`` clamps to 1 (no retry), values above the cap clamp to the cap —
    a misconfigured env var can never spin unbounded.
    """
    raw = os.getenv(env, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:  # noqa: BLE001
        return default
    return max(1, min(value, _MAX_ATTEMPTS_CAP))


def delay_seconds(retry_after: str | None, attempt: int) -> float:
    """Honour a numeric ``Retry-After`` hint, else exponential backoff."""
    if retry_after:
        try:
            hinted = float(retry_after.strip())
            if hinted > 0:
                return min(hinted, _MAX_DELAY_S)
        except ValueError:  # noqa: BLE001
            pass
    return min(_BASE_DELAY_S * (2 ** (attempt - 1)), _MAX_DELAY_S)


def post_transient_retry(
    post: Callable[[], object],
    *,
    max_attempts: int,
    log_prefix: str,
) -> object:
    """Drive ``post()`` with bounded retries on transient failures.

    ``post`` is a zero-arg callable performing one HTTP POST and returning a
    response object with ``status_code``/``headers`` (httpx), or raising.
    Returns the final response — ``None`` only when EVERY attempt raised.
    A non-200 response is returned as-is so the caller applies its own
    failure accounting exactly once per logical call.
    """
    ceiling = max(1, int(max_attempts))
    last_exc: Exception | None = None
    for attempt in range(1, ceiling + 1):
        resp = None
        try:
            resp = post()
        except Exception as exc:  # noqa: BLE001 — caller owns fail-open/closed
            last_exc = exc
            logger.debug(
                "%s: POST failed (attempt %s/%s): %s",
                log_prefix, attempt, ceiling, exc,
            )
        status = getattr(resp, "status_code", None)
        if resp is not None and status == 200:
            return resp
        transient = resp is None or status in TRANSIENT_STATUSES
        if not transient or attempt >= ceiling:
            if resp is not None or last_exc is None:
                return resp
            raise last_exc
        wait = delay_seconds(
            getattr(resp, "headers", {}).get("Retry-After"), attempt
        )
        logger.debug(
            "%s: %s — retrying in %.1fs (attempt %s/%s)",
            log_prefix,
            f"http {status}" if resp is not None else "POST failed",
            wait, attempt, ceiling,
        )
        time.sleep(wait)
    return None  # pragma: no cover — loop returns inside
