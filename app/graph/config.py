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

from pydantic import SecretStr
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
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: SecretStr = SecretStr("")  # Set via NEO4J_PASSWORD env var
    database: str = "neo4j"
    max_connection_pool_size: int = 50
    connection_timeout: float = 5.0
    # Retry knobs — applied on ``ServiceUnavailable`` at session-acquire time.
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
