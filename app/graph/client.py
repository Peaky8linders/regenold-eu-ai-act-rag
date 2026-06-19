"""Neo4j Graph Client — connection management and query execution.

Port of the parent CodexAI client, adapted to the Regenold bundle:

* Singleton pattern (matching ``get_evidence_store()`` / ``get_drift_detector()``
  in the parent repo).
* **Opt-in activation.** The client wires up a real Neo4j driver only
  when ``NEO4J_URI`` is set in the environment AND the optional ``neo4j``
  Python driver is importable. Otherwise ``enabled`` stays ``False`` and
  the engine takes its deterministic KB-fallback path (BM25 + curated
  keyword + obligation map). This is the disabled default in this bundle.
* ``neo4j`` is treated as an **optional dependency**. The import is deferred
  to inside the activation guard, so this module loads cleanly even when
  the package isn't installed.
* Pooled session usage and bounded retry on ``ServiceUnavailable`` so a
  transient cluster blip doesn't take the request path down.

The wire-side public API is intentionally stable: ``enabled``,
``execute_read(query, parameters)``, ``execute_write(query, parameters)``,
``close()``. The engine only depends on ``enabled`` + ``execute_read``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from app.graph.config import GraphSettings
from app.graph.ontology import GraphStats

logger = logging.getLogger(__name__)

_client: GraphClient | None = None
_client_lock = threading.Lock()

# Allowlist of node labels for stats queries (never from user input).
_STATS_LABELS = frozenset([
    "Article", "Obligation", "Dimension", "Question",
    "RiskLevel", "AnnexIIICategory", "RoadmapTask",
    "NISTSubcategory", "ISOClause", "KBMetadata",
])


def _neo4j_available() -> bool:
    """Return True if the optional ``neo4j`` driver package is importable."""
    try:
        import neo4j  # noqa: F401
        return True
    except ImportError:
        return False


def _should_activate(settings: GraphSettings) -> bool:
    """Hard activation gate.

    Activates only when ``NEO4J_URI`` is set in the process environment
    AND the ``neo4j`` driver is importable. The pydantic ``enabled`` flag
    is treated as advisory — the env-var presence is what flips the
    switch for this bundle. This keeps the disabled default
    non-negotiable for the eval/test envs that don't set ``NEO4J_URI``.
    """
    # R127 — Aura activates only when the embedded graph is NOT the active
    # backend (i.e. an explicit ``REGENOLD_GRAPH_BACKEND=neo4j``). The
    # default backend is now ``embedded`` (in-process SQLite), so a deploy
    # that still carries ``NEO4J_URI`` in its dashboard does not pay the Aura
    # retrieval / boot-seed network cost unless it opts back in. Lazy import
    # to avoid a hard dependency cycle at module load.
    try:
        from app.graph.embedded_graph import neo4j_backend_selected
        if not neo4j_backend_selected():
            return False
    except Exception:  # noqa: BLE001 — never let the gate break activation logic
        # Fail-OPEN to the historical Neo4j path, but log it: an embedded_graph
        # import failure here silently re-enables Aura (with no other signal),
        # so make that backend-flip traceable instead of invisible.
        logger.warning(
            "graph backend selector import failed — falling back to the Neo4j "
            "activation gate; the embedded-graph default could not be read.",
            exc_info=True,
        )
    if not os.environ.get("NEO4J_URI"):
        return False
    if not _neo4j_available():
        logger.warning(
            "NEO4J_URI is set but the 'neo4j' driver package is not installed — "
            "graph features remain disabled. Install with: pip install neo4j>=5.0"
        )
        return False
    # Honour an explicit opt-out even when URI + driver are both present.
    if not settings.enabled and os.environ.get("NEO4J_ENABLED", "").lower() in {"0", "false", "no"}:
        return False
    return True


class GraphClient:
    """Neo4j driver wrapper with connection pooling, retry, and health checks."""

    def __init__(self, settings: GraphSettings) -> None:
        self._settings = settings
        self._driver: Any = None

        if not _should_activate(settings):
            # Disabled stub path — driver stays ``None`` and ``enabled``
            # reports ``False``. The engine takes the KB-fallback path.
            return

        try:
            # Deferred import — ``neo4j`` is an optional dependency. The
            # ``_should_activate`` guard above already confirmed it's
            # importable, so failures here are environmental.
            import neo4j

            self._driver = neo4j.GraphDatabase.driver(
                settings.uri,
                auth=(settings.username, settings.password.get_secret_value()),
                max_connection_pool_size=settings.max_connection_pool_size,
                connection_timeout=settings.connection_timeout,
            )
            logger.info("Neo4j driver initialized: %s", settings.uri)
        except Exception as exc:  # noqa: BLE001
            # Catch-all so a misconfigured driver never breaks request
            # serving. We log and fall back to disabled.
            logger.warning("Neo4j connection failed: %s — graph features disabled", exc)
            self._driver = None

    @property
    def enabled(self) -> bool:
        return self._driver is not None

    # ─── Internal helpers ────────────────────────────────────────────────

    def _service_unavailable_class(self) -> type[BaseException] | None:
        """Resolve the ``ServiceUnavailable`` exception class lazily.

        We can't import this at module top because ``neo4j`` is optional.
        Returns ``None`` if the package is unavailable.
        """
        try:
            from neo4j.exceptions import ServiceUnavailable  # type: ignore[import-not-found]
            return ServiceUnavailable
        except Exception:  # noqa: BLE001
            return None

    def _run_read(self, query: str, parameters: dict | None) -> list[dict]:
        """Single attempt at a read query within a pooled session."""
        # ``with driver.session(...)`` returns a session from the pool.
        with self._driver.session(database=self._settings.database) as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    # ─── Public API ──────────────────────────────────────────────────────

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        """Execute a read-only Cypher query and return results as dicts.

        Retries up to ``settings.max_retries`` times on
        ``ServiceUnavailable`` with a linear backoff. Any other exception
        is logged and an empty list is returned so the engine can fall
        back gracefully without leaking driver internals to the wire.
        """
        if self._driver is None:
            return []

        unavailable = self._service_unavailable_class()
        attempts = max(1, self._settings.max_retries + 1)
        last_exc: BaseException | None = None

        for attempt in range(attempts):
            try:
                return self._run_read(query, parameters)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # Only retry the well-known transient class.
                if unavailable is not None and isinstance(exc, unavailable) and attempt < attempts - 1:
                    backoff = self._settings.retry_backoff_seconds * (attempt + 1)
                    logger.info(
                        "Neo4j read transient failure (attempt %d/%d), backing off %.2fs: %s",
                        attempt + 1, attempts, backoff, exc,
                    )
                    time.sleep(backoff)
                    continue
                logger.warning("Neo4j execute_read failed: %s", exc)
                return []

        # Should be unreachable — every loop branch either returns or
        # continues. Defensive only.
        logger.warning("Neo4j execute_read exhausted retries: %s", last_exc)
        return []

    def execute_write(self, query: str, parameters: dict | None = None) -> list[dict]:
        """Execute a write Cypher query within a managed transaction."""
        if self._driver is None:
            return []

        def _work(tx: Any) -> list[dict]:
            result = tx.run(query, parameters or {})
            return [dict(record) for record in result]

        try:
            with self._driver.session(database=self._settings.database) as session:
                return session.execute_write(_work)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j execute_write failed: %s", exc)
            return []

    def execute_write_batch(self, queries: list[tuple[str, dict]]) -> None:
        """Execute multiple write queries in a single transaction."""
        if self._driver is None:
            return
        try:
            with self._driver.session(database=self._settings.database) as session:
                with session.begin_transaction() as tx:
                    for query, params in queries:
                        tx.run(query, params)
                    tx.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j execute_write_batch failed: %s", exc)
            raise

    def health_check(self) -> dict[str, Any]:
        """Check Neo4j connectivity and return status."""
        if not self.enabled:
            return {"status": "disabled", "message": "NEO4J_URI not set or neo4j driver missing"}
        try:
            result = self.execute_read("RETURN 1 AS ping")
            return {"status": "healthy", "ping": result[0]["ping"] if result else None}
        except Exception:  # noqa: BLE001
            logger.warning("Neo4j health check failed", exc_info=True)
            return {"status": "unhealthy", "error": "Graph database unavailable"}

    def existing_labels(self, allowlist: frozenset[str] | set[str]) -> set[str]:
        """Return the subset of ``allowlist`` that actually exists in the graph.

        Probes ``CALL db.labels()`` once and intersects with the allowlist.
        On probe failure (procedure unavailable, network blip, etc.) falls
        back to a SAFE subset known to always be populated by the seeder —
        so the f-string ``MATCH (n:LABEL)`` queries that follow never hit a
        label that doesn't exist, even in the degraded path.

        R64 — fix for [I5+I6] (R63-F partial regression on fallback path).
        Pre-R64 both ``get_stats`` and ``/healthz/graph`` had inline,
        duplicated probe-and-intersect blocks that fell back to the FULL
        ``_STATS_LABELS`` allowlist on probe failure — which re-introduced
        the R63-F warning storm for the 5 orphan labels (Dimension /
        Question / RoadmapTask / NISTSubcategory / ISOClause) the
        Regenold seeder doesn't populate. The shared helper here uses a
        SAFE fallback subset of labels that ``scripts/seed_neo4j_kb.py``
        guarantees on every successful seed run.
        """
        # Labels the seeder ALWAYS writes (verified against
        # ``scripts/seed_neo4j_kb.py`` ``MERGE`` node statements:
        # Article, Annex, Recital, Definition, Obligation,
        # AnnexIIICategory, RiskLevel, OperatorRole, KBMetadata).
        # We intersect with ``_STATS_LABELS`` below, so labels not in
        # the allowlist (Annex / Recital / Definition / OperatorRole)
        # drop out naturally — the operationally-meaningful fallback is
        # ``Article``, ``Obligation``, ``KBMetadata``, ``RiskLevel``,
        # ``AnnexIIICategory``, all in ``_STATS_LABELS``.
        safe_fallback = {
            "Article",
            "Obligation",
            "KBMetadata",
            "RiskLevel",
            "AnnexIIICategory",
        }
        if not self.enabled:
            return set()
        try:
            rows = self.execute_read("CALL db.labels() YIELD label RETURN label")
            existing = {r["label"] for r in rows if r.get("label")}
            return set(allowlist) & existing
        except Exception as exc:  # noqa: BLE001
            logger.debug("graph_existing_labels_probe_failed error=%s", exc)
            # R64 — safe fallback. Pre-R64 we fell back to the FULL
            # ``_STATS_LABELS`` allowlist, which re-introduced the R63-F
            # warning storm (the 5 parent-CodexAI orphan labels the
            # Regenold seeder doesn't populate). Intersect the allowlist
            # with only labels the seeder ALWAYS writes.
            return set(allowlist) & safe_fallback

    def get_stats(self) -> GraphStats:
        """Return graph summary statistics.

        The parent repo projects the in-process KB into a ``GraphStats``
        shape when the cache is cold. The Regenold bundle ships only the
        Q&A surface and doesn't include the framework/agentic-taxonomy
        modules the parent projection reads from, so when disabled we
        return an empty ``GraphStats`` with ``healthy=False`` — the
        engine never calls ``get_stats`` on the request path, so this is
        observational only.
        """
        if not self.enabled:
            return GraphStats(healthy=False)

        # Per-label node counts via the static allowlist (the
        # ``db.stats.retrieve`` procedure isn't available on every Neo4j
        # edition, so we go straight to the per-label path which works
        # on Community as well as Enterprise).
        #
        # R63-F / R64 — only count labels that actually exist in the
        # graph. ``existing_labels`` probes ``db.labels()`` once and
        # intersects with the allowlist; on probe failure it falls back
        # to a SAFE subset (Article / Obligation / KBMetadata /
        # RiskLevel / AnnexIIICategory) so the f-string ``MATCH (n:LABEL)``
        # queries that follow never hit a missing label.
        existing = self.existing_labels(_STATS_LABELS)

        nodes_by_type: dict[str, int] = {}
        for label in sorted(existing):
            try:
                # Labels are from a hardcoded allowlist ∩ live db.labels()
                # — never from user input.
                result = self.execute_read(
                    f"MATCH (n:{label}) RETURN count(n) AS cnt"
                )
                if result:
                    nodes_by_type[label] = result[0]["cnt"]
            except Exception as exc:  # noqa: BLE001
                logger.debug("graph_stats_label_count_failed label=%s error=%s", label, exc)

        edges_by_type: dict[str, int] = {}
        try:
            edge_results = self.execute_read(
                "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt"
            )
            edges_by_type = {r["rel_type"]: r["cnt"] for r in edge_results}
        except Exception as exc:  # noqa: BLE001
            logger.debug("graph_stats_edge_count_failed error=%s", exc)

        seed_version = ""
        try:
            meta = self.execute_read(
                "MATCH (m:KBMetadata) RETURN m.seed_version AS v LIMIT 1"
            )
            if meta:
                seed_version = meta[0]["v"] or ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("graph_stats_seed_version_failed error=%s", exc)

        return GraphStats(
            total_nodes=sum(nodes_by_type.values()),
            total_edges=sum(edges_by_type.values()),
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
            seed_version=seed_version,
            healthy=True,
        )

    def clear_graph(self) -> None:
        """Delete all nodes and edges. Use with caution."""
        if not self.enabled:
            return
        self.execute_write("MATCH (n) DETACH DELETE n")

    def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neo4j driver close failed: %s", exc)
            self._driver = None


def get_graph_client() -> GraphClient:
    """Get or create the singleton graph client (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                # Re-read settings on first access so a late env-var
                # rebind (e.g. via Railway) still takes effect.
                _client = GraphClient(GraphSettings())
    return _client


def _reset_singleton_for_tests() -> None:
    """Test hook — drop the cached singleton so a fresh ``GraphSettings``
    is read on the next ``get_graph_client()`` call. Not part of the
    public API."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
