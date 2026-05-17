"""slowapi limiter — per-tier rate-limit buckets.

The Regenold route uses a callable ``limit_value`` that resolves the
limit string from the bucket key (60/min for ``regenold-key:`` buckets,
30/min for ``regenold-anon:`` buckets). See ``app/routes/regenold.py``.
"""
from __future__ import annotations

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings

logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.rate_limit.storage_uri,
    default_limits=[settings.rate_limit.default_limit],
)


# R45 Fix 1.2 — multi-worker / memory-storage warning.
#
# slowapi's default ``memory://`` storage keeps counters in process-local
# state. Under multi-worker deploys each fork has its OWN counter dict, so
# per-IP limits multiply by the worker count. Detect this at boot and warn
# loudly so the operator either (a) raises the limit, (b) moves to Redis
# via ``P2P_RATELIMIT_STORAGE_URI``, or (c) drops back to one worker.
#
# Heuristic worker-count sources (in order):
#   1. WEB_CONCURRENCY env var (gunicorn / uvicorn convention)
#   2. UVICORN_WORKERS env var
#   3. Railway-style ``--workers N`` arg sniff (best-effort; we can't see
#      the uvicorn CLI from here, so we only warn when env says >1).
def _detect_worker_count() -> int:
    for env_name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            value = int(raw.strip())
        except ValueError:
            continue
        if value > 0:
            return value
    return 1


def _warn_if_multiworker_memory_storage() -> None:
    """Boot-time check: shout if memory:// is paired with multi-worker."""
    storage = settings.rate_limit.storage_uri
    worker_count = _detect_worker_count()
    if storage.startswith("memory://") and worker_count >= 2:
        logger.warning(
            "Rate limit storage uri = memory:// — multi-worker config "
            "will double effective limits (workers=%d). Move to Redis "
            "via P2P_RATELIMIT_STORAGE_URI=redis://... or set workers=1.",
            worker_count,
        )


_warn_if_multiworker_memory_storage()


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "code": "rate_limited",
            "message": f"Rate limit exceeded: {exc.detail}",
        },
    )
