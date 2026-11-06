from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

_regenold_header = APIKeyHeader(name="X-Regenold-Api-Key", auto_error=False)


def _configured_key() -> str | None:
    if not settings.regenold.api_key:
        return None
    return settings.regenold.api_key.get_secret_value()


def validate_regenold_api_key(api_key: str) -> bool:
    configured = _configured_key()
    if not configured:
        return False
    # R112 — never let a malformed header crash the route.
    # ``secrets.compare_digest`` raises TypeError on non-ASCII str input;
    # HTTP header bytes are latin-1-decoded by Starlette, so a raw
    # 0x80-0xFF octet in X-Regenold-Api-Key arrives here as a non-ASCII
    # str and previously 500'd every request on a configured deploy.
    # Compare as UTF-8 bytes (timing-safe for bytes of any content) and
    # fail closed on any residual encode/compare error — the dependency
    # then raises the documented 403 instead of an unhandled 500.
    try:
        return secrets.compare_digest(
            api_key.encode("utf-8"), configured.encode("utf-8")
        )
    except Exception:  # noqa: BLE001 — fail-closed, never 500 the route
        return False


async def require_regenold_api_key(
    api_key: Annotated[str | None, Security(_regenold_header)] = None,
) -> str:
    """Strict-auth dep: only the configured partner key passes.

    Guards the Q&A route and the diagnostics routes. 503 when no key is
    configured, 401 when none is sent, 403 when it does not match.
    """
    if not _configured_key():
        # Staged-but-inactive posture (same pattern as OAuth): ship code
        # before provisioning the partner key in Railway.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "regenold_not_configured",
                "message": "Regenold integration is not configured on this deployment.",
            },
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "regenold_api_key_missing",
                "message": "Missing API key. Provide it via X-Regenold-Api-Key.",
            },
        )
    if not validate_regenold_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "regenold_api_key_invalid",
                "message": "Invalid API key.",
            },
        )
    return api_key


RequireRegenold = Depends(require_regenold_api_key)
