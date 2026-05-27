"""Shared RushDB connection settings (Hybrid RAG Guide §2)."""
from __future__ import annotations

import os
from typing import Any

DEFAULT_RUSHDB_BASE_URL = "https://api.rushdb.com/api/v1"


def resolve_auth_token() -> str | None:
    """Return ``RUSHDB_AUTH_TOKEN`` or ``RUSHDB_API_KEY`` (either works)."""
    token = os.environ.get("RUSHDB_AUTH_TOKEN") or os.environ.get("RUSHDB_API_KEY")
    if not token:
        return None
    token = token.strip()
    return token or None


def resolve_base_url() -> str:
    """Base URL for the RushDB API (``RUSHDB_BASE_URL`` or legacy ``RUSHDB_URL``)."""
    raw = os.environ.get("RUSHDB_BASE_URL") or os.environ.get("RUSHDB_URL")
    return (raw or DEFAULT_RUSHDB_BASE_URL).strip()


def create_rushdb_client() -> Any | None:
    """Construct a RushDB client or return ``None`` when auth is missing."""
    token = resolve_auth_token()
    if not token:
        return None

    import rushdb

    base_url = resolve_base_url()
    try:
        return rushdb.RushDB(api_key=token, base_url=base_url)
    except TypeError:
        # Older rushdb wheels use positional auth_token + url= keyword.
        return rushdb.RushDB(token, url=base_url)


def is_configured() -> bool:
    """True when an auth env var is set (does not verify connectivity)."""
    return resolve_auth_token() is not None
