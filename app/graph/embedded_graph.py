"""Embedded property-graph backend — Orbit-inspired, Neo4j-free 2-hop.

## Why this exists

The Round-35 :mod:`app.engines.graph_expand_2hop` 2-hop CROSS_REFERENCES
traversal needs a graph backend. Historically that was **Neo4j Aura** —
a hosted graph DB that has been a documented production liability:

* ~20× duplicate nodes from repeated seed runs (R98).
* the R99.1 *"graph returns empty → Art. 1/2 floor"* bug (a seed/Cypher
  schema mismatch the engine had to defend against).
* free-tier limits (the reason RushDB was dropped before it).
* network availability + an auto-seed ops burden on every deploy.

Our KB graph is **505 nodes / ~500 edges — tiny and static**; it does
not justify a hosted graph DB. This module is the
`GitLab Orbit <https://github.com/gitlabhq/orbit-knowledge-graph>`_
"local mode" pattern applied to us: build the property graph **in
process** from the same in-process source the Neo4j seeder reads
(:func:`app.data.kb_xrefs._build_xref_graph` / :func:`all_edges`), store
it in a single-file **SQLite** property graph, and serve the 2-hop
traversal as a recursive SQL CTE.

Versus Neo4j this is **strictly better for our scale**:

* zero external service, zero network, zero seed step;
* always in sync with ``KB_VERSION`` (rebuilt from the live registries,
  never a stale seed → no duplicate-node drift);
* it can never return the R99.1 empty-graph failure (it is always
  built);
* deterministic sub-ms queries.

It mirrors the seeded-Neo4j ``CROSS_REFERENCES`` edge set exactly
(``_build_xref_graph`` IS the source the seeder pulls those edges from —
including the R47-A orphan-rescue backfill), so the embedded 2-hop
returns the same neighbours the Neo4j 2-hop would — without Aura.

## Single ontology source of truth (Orbit pattern #2)

:data:`ONTOLOGY` is the one declarative schema both the builder and the
traversal read. The R99.1 production bug was schema drift — a Cypher
template matched a ``REQUIRES`` edge the seeder never created
(``HAS_OBLIGATION``). Here the node labels + edge types live in one
constant, so that class of mismatch is structurally impossible. The
import-time :func:`_self_check` fails loud on drift (same posture as
:mod:`app.engines.entity_extractor` / ``zero_retrieval_fallback``).

## Typed traversal helper (Orbit pattern #3)

:meth:`EmbeddedGraph.neighbors` / :meth:`EmbeddedGraph.two_hop` are
typed methods, not hand-written Cypher strings copy-pasted across
modules (the drift R63-F / R99.1 kept finding).

## Selection

Opt-in via ``REGENOLD_GRAPH_BACKEND=embedded`` (default: the historical
Neo4j path). Default-OFF keeps the davidath bench byte-identical and the
change fully reversible. Promote to default once validated in
production.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading

from app.data import kb_xrefs
from app.data.article_existence import ARTICLE_EXISTENCE

logger = logging.getLogger(__name__)


# ── Ontology — single source of truth for the embedded schema ────────────────

ONTOLOGY: dict[str, frozenset[str]] = {
    "node_labels": frozenset({"Article", "Annex"}),
    "edge_types": frozenset({"CROSS_REFERENCES"}),
}

_EDGE_TYPE = "CROSS_REFERENCES"
_MAX_HOP_DEFAULT = 2


# ── Node derivation — internal ref ("Art. 6" / "Annex III") → (label, num) ───


def _derive_node(ref: str) -> tuple[str, str]:
    """Split a canonical internal ref into ``(label, number)``.

    ``"Art. 6"`` → ``("Article", "6")``; ``"Annex III"`` →
    ``("Annex", "III")``. Raises ``ValueError`` on any other form so
    :func:`_self_check` catches a new ``ARTICLE_EXISTENCE`` entry shape
    the builder can't parse, at import, rather than silently dropping
    nodes.
    """
    if ref.startswith("Art. "):
        return "Article", ref[len("Art. ") :].strip()
    if ref.startswith("Annex "):
        return "Annex", ref[len("Annex ") :].strip()
    raise ValueError(f"unrecognised ref form: {ref!r}")


# ── The embedded property graph ──────────────────────────────────────────────


class EmbeddedGraph:
    """In-process SQLite property graph over the EU AI Act KB.

    Schema (per :data:`ONTOLOGY`)::

        nodes(id TEXT PK, label TEXT, number TEXT)   -- id == internal ref
        edges(src TEXT, dst TEXT, type TEXT)         -- undirected (stored
                                                        both directions)

    Built once at construction from :data:`ARTICLE_EXISTENCE` (the 126
    canonical Article/Annex nodes) and
    :func:`app.data.kb_xrefs.all_edges` (the full xref graph, the same
    source the Neo4j seeder pulls ``CROSS_REFERENCES`` from). Never
    raises on build failure — :attr:`enabled` reports the outcome and a
    failed build degrades the 2-hop path to a no-op (route-safe).
    """

    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        try:
            self._build()
        except Exception:  # noqa: BLE001 — never break import / the route
            logger.warning("embedded_graph build failed", exc_info=True)
            self._conn = None

    # ─── Build ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ``check_same_thread=False`` + a per-instance lock: one shared
        # in-memory connection serves the FastAPI threadpool. Reads are
        # sub-ms and serialised by the lock (no contention at our scale).
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.executescript(
            """
            CREATE TABLE nodes (id TEXT PRIMARY KEY, label TEXT NOT NULL,
                                number TEXT NOT NULL);
            CREATE TABLE edges (src TEXT NOT NULL, dst TEXT NOT NULL,
                                type TEXT NOT NULL);
            CREATE INDEX idx_edges_src ON edges(src, type);
            CREATE INDEX idx_nodes_number ON nodes(number);
            """
        )

        node_ids = set(ARTICLE_EXISTENCE)
        conn.executemany(
            "INSERT INTO nodes (id, label, number) VALUES (?, ?, ?)",
            [(ref, *_derive_node(ref)) for ref in sorted(node_ids)],
        )

        # Undirected edges, deduped, both endpoints existence-gated. The
        # xref graph collapses sub-points to parents, so every endpoint
        # that resolves is a canonical node; anything else is dropped
        # (a malformed xref can never pollute the graph).
        seen: set[tuple[str, str]] = set()
        for src, dst in kb_xrefs.all_edges():
            if src == dst or src not in node_ids or dst not in node_ids:
                continue
            for a, b in ((src, dst), (dst, src)):
                if (a, b) not in seen:
                    seen.add((a, b))
        conn.executemany(
            "INSERT INTO edges (src, dst, type) VALUES (?, ?, ?)",
            [(a, b, _EDGE_TYPE) for (a, b) in seen],
        )
        conn.commit()
        self._conn = conn

    # ─── Introspection ────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        """True iff the graph built successfully."""
        return self._conn is not None

    def node_count(self) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])

    def edge_count(self) -> int:
        """Directed edge count (undirected edges stored both ways)."""
        if self._conn is None:
            return 0
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])

    def directed_edges(self) -> list[tuple[str, str]]:
        """Every stored ``(src, dst)`` edge — internal-ref form."""
        if self._conn is None:
            return []
        with self._lock:
            return [
                (r[0], r[1])
                for r in self._conn.execute("SELECT src, dst FROM edges").fetchall()
            ]

    # ─── Typed traversal (Orbit pattern #3) ──────────────────────────────

    def neighbors(self, ref: str, *, hops: int = 1) -> list[str]:
        """Refs reachable within ``hops`` of ``ref`` (excluding ``ref``).

        Human-facing: takes and returns canonical internal refs
        (``"Art. 6"`` / ``"Annex III"``). Undirected traversal (mirrors
        the Cypher ``CROSS_REFERENCES*1..N``). Deterministic order.
        """
        if self._conn is None or not ref or hops <= 0:
            return []
        sql = """
        WITH RECURSIVE walk(id, h) AS (
            SELECT e.dst, 1 FROM edges e WHERE e.src = ? AND e.type = ?
            UNION
            SELECT e.dst, w.h + 1 FROM edges e JOIN walk w ON e.src = w.id
                WHERE e.type = ? AND w.h < ?
        )
        SELECT DISTINCT id FROM walk WHERE id != ? ORDER BY id
        """
        with self._lock:
            cur = self._conn.execute(sql, (ref, _EDGE_TYPE, _EDGE_TYPE, hops, ref))
            return [r[0] for r in cur.fetchall()]

    def two_hop(self, seed_nums: list[str], cap: int) -> list[dict]:
        """2-hop expansion in number-space — drop-in for the Cypher path.

        Returns ``[{"num": <bare token>, "hops": <1|2>}, ...]`` — the
        exact row shape :func:`app.engines.graph_expand_2hop.expand_2hop`
        consumes from ``execute_read``. ``seed_nums`` are bare tokens
        (``"6"`` / ``"III"``). Excludes seeds, reports min-hops, ordered
        ``(hops, num)`` lexicographically (matching the Cypher
        ``ORDER BY hops, num``), capped at ``cap``.
        """
        if self._conn is None or cap <= 0:
            return []
        nums = [str(n).strip() for n in seed_nums if str(n).strip()]
        if not nums:
            return []
        placeholders = ",".join("?" for _ in nums)
        sql = f"""
        WITH RECURSIVE
          seeds(id) AS (SELECT id FROM nodes WHERE number IN ({placeholders})),
          walk(id, hops) AS (
            SELECT e.dst, 1 FROM edges e JOIN seeds s ON e.src = s.id
                WHERE e.type = ?
            UNION
            SELECT e.dst, w.hops + 1 FROM edges e JOIN walk w ON e.src = w.id
                WHERE e.type = ? AND w.hops < ?
          ),
          best(id, hops) AS (SELECT id, MIN(hops) AS hops FROM walk GROUP BY id)
        SELECT n.number AS num, b.hops AS hops
          FROM best b JOIN nodes n ON n.id = b.id
         WHERE b.id NOT IN (SELECT id FROM seeds)
         ORDER BY b.hops, n.number
         LIMIT ?
        """
        params = [*nums, _EDGE_TYPE, _EDGE_TYPE, _MAX_HOP_DEFAULT, cap]
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [{"num": r[0], "hops": int(r[1])} for r in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 — best-effort
                pass
            self._conn = None


# ── Singleton ────────────────────────────────────────────────────────────────

_SINGLETON: EmbeddedGraph | None = None
_SINGLETON_LOCK = threading.Lock()


def get_embedded_graph() -> EmbeddedGraph:
    """Process-wide pooled embedded graph. Thread-safe, double-checked."""
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = EmbeddedGraph()
    return _SINGLETON


def _reset_embedded_graph_for_tests() -> None:
    """Drop the cached singleton. Test-only — not part of the public API."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is not None:
            _SINGLETON.close()
        _SINGLETON = None


# ── Backend selector ─────────────────────────────────────────────────────────

_BACKEND_ENV = "REGENOLD_GRAPH_BACKEND"


def embedded_backend_selected() -> bool:
    """True iff ``REGENOLD_GRAPH_BACKEND=embedded`` (default: not selected).

    Default-OFF: unset / ``neo4j`` / anything else keeps the historical
    Neo4j path. The davidath bench never sets this, so it stays
    byte-identical.
    """
    return os.getenv(_BACKEND_ENV, "").strip().lower() == "embedded"


# ── Import-time fail-loud self-check (cheap; no SQLite) ───────────────────────


def _self_check() -> None:
    """Validate the ontology + node-derivation against the live registry.

    Cheap (pure Python, no SQLite build): asserts the ontology is
    well-formed and every canonical ``ARTICLE_EXISTENCE`` entry derives a
    valid ``(label, number)`` whose label is declared. A new entry shape
    the deriver can't parse fails the module import — the same fail-loud
    posture as ``entity_extractor._self_check`` — instead of silently
    dropping nodes at runtime.
    """
    if not ONTOLOGY["node_labels"] or not ONTOLOGY["edge_types"]:
        raise RuntimeError("embedded_graph ONTOLOGY is empty")
    if _EDGE_TYPE not in ONTOLOGY["edge_types"]:
        raise RuntimeError(f"embedded_graph edge type {_EDGE_TYPE!r} not in ONTOLOGY")
    if not ARTICLE_EXISTENCE:
        raise RuntimeError("embedded_graph: ARTICLE_EXISTENCE is empty")
    for ref in ARTICLE_EXISTENCE:
        label, number = _derive_node(ref)  # raises on unrecognised form
        if label not in ONTOLOGY["node_labels"]:
            raise RuntimeError(
                f"embedded_graph: node {ref!r} label {label!r} not in ONTOLOGY"
            )
        if not number:
            raise RuntimeError(f"embedded_graph: node {ref!r} has empty number")


_self_check()


__all__ = [
    "ONTOLOGY",
    "EmbeddedGraph",
    "get_embedded_graph",
    "embedded_backend_selected",
]
