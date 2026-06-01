"""Graph database configuration — Neo4j connection settings.

Follows the pydantic-settings pattern used by ``app/config.py``. All
settings are overridable via ``NEO4J_*`` environment variables.

In the Regenold bundle the graph is **opt-in**: the client only activates
when ``NEO4J_URI`` is set AND the ``neo4j`` Python driver is importable
(see :mod:`app.graph.client`). Otherwise the engine takes the deterministic
KB-fallback path. These settings are kept faithful to the parent CodexAI
schema so a future operator can drop in Neo4j with a one-file env-var swap.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GraphSettings(BaseSettings):
    """Neo4j graph database configuration.

    Used for compliance knowledge graph storage and traversal.
    Set ``NEO4J_ENABLED=true`` to mark the operator's intent to enable
    graph-powered reasoning. The hard activation gate is whether
    ``NEO4J_URI`` resolves and the ``neo4j`` package is importable —
    see :class:`app.graph.client.GraphClient`.
    """

    model_config = SettingsConfigDict(env_prefix="NEO4J_", extra="ignore")

    enabled: bool = False
    # Default points at the Regenold Neo4j Aura instance (R98 — Aura is the
    # production graph backend). Overridable via ``NEO4J_URI``; the Railway
    # dashboard / local ``.env`` set the operative value. ``neo4j+s://``
    # uses TLS + routing and REQUIRES ``NEO4J_PASSWORD`` (username defaults
    # to the Aura ``neo4j``); without the password the client cannot
    # authenticate and the engine falls back to the deterministic KB path.
    uri: str = "neo4j+s://6fc3fff5.databases.neo4j.io"
    # R98 — accept BOTH ``NEO4J_USERNAME`` (the env_prefix default) and
    # ``NEO4J_USER`` (what the seeder CLI sets and what many Neo4j Aura
    # deploys / Railway dashboards use). The user's Railway instance names
    # the var "user", so without the alias the client would silently fall
    # back to the "neo4j" default. Aura's default username IS "neo4j" so
    # the practical blast radius is small, but the alias removes the
    # ambiguity. ``validation_alias`` bypasses ``env_prefix`` for this
    # field, so both full env-var names are listed explicitly.
    username: str = Field(
        default="neo4j",
        validation_alias=AliasChoices("NEO4J_USERNAME", "NEO4J_USER"),
    )
    password: SecretStr = SecretStr("")  # Set via NEO4J_PASSWORD env var
    database: str = "neo4j"
    max_connection_pool_size: int = 50
    connection_timeout: float = 5.0
    # Retry knobs — applied on ``ServiceUnavailable`` at session-acquire time.
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
