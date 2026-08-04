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

Our KB graph is tiny and static — this module builds the **126
``CROSS_REFERENCES`` nodes (113 articles + 13 annexes) / ~216 undirected
edges** the 2-hop traversal actually walks (the full Neo4j seed carries
505 nodes incl. recitals / definitions / obligations, but those are not
part of the article↔article xref graph). It does
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
        # Bind ``self._conn`` to a local INSIDE the lock and re-check for None
        # so a concurrent ``close()`` (which also takes the lock) can't null
        # the attribute between the guard and the execute → AttributeError.
        with self._lock:
            conn = self._conn
            if conn is None:
                return 0
            return int(conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])

    def edge_count(self) -> int:
        """Directed edge count (undirected edges stored both ways)."""
        with self._lock:
            conn = self._conn
            if conn is None:
                return 0
            return int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])

    def directed_edges(self) -> list[tuple[str, str]]:
        """Every stored ``(src, dst)`` edge — internal-ref form."""
        with self._lock:
            conn = self._conn
            if conn is None:
                return []
            return [
                (r[0], r[1])
                for r in conn.execute("SELECT src, dst FROM edges").fetchall()
            ]

    # ─── Typed traversal (Orbit pattern #3) ──────────────────────────────

    def neighbors(self, ref: str, *, hops: int = 1) -> list[str]:
        """Refs reachable within ``hops`` of ``ref`` (excluding ``ref``).

        Human-facing: takes and returns canonical internal refs
        (``"Art. 6"`` / ``"Annex III"``). Undirected traversal (mirrors
        the Cypher ``CROSS_REFERENCES*1..N``). Deterministic order.
        """
        if not ref or hops <= 0:
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
            conn = self._conn
            if conn is None:
                return []
            cur = conn.execute(sql, (ref, _EDGE_TYPE, _EDGE_TYPE, hops, ref))
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
        if cap <= 0:
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
            conn = self._conn
            if conn is None:
                return []
            cur = conn.execute(sql, params)
            return [{"num": r[0], "hops": int(r[1])} for r in cur.fetchall()]

    def close(self) -> None:
        # Acquire the read lock so ``close()`` cannot null ``self._conn``
        # while another thread holds it mid-query (the read methods bind the
        # connection to a local under this same lock). Without this, a
        # concurrent reader could hit ``Cannot operate on a closed database``.
        with self._lock:
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
_DEFAULT_BACKEND = "neo4j"


def graph_backend() -> str:
    """Resolve the active graph backend.

    **R313.1 — the default is ``neo4j`` (hosted Aura) again, per an explicit
    operator directive: always use the knowledge graph and Neo4j Aura.**

    This is a deliberate reversal of R127, and the reasoning that produced R127
    is worth keeping straight rather than deleting. R127 chose ``embedded``
    because Aura was pure operational drag (R98 ~20x duplicate nodes, R99.1
    empty-graph zero-retrieval, boot auto-seed, free-tier limits) for a graph
    whose only consumer was a 2-hop CROSS_REFERENCES walk over ~126 nodes —
    something the in-process SQLite mirror does identically, sub-ms and for
    free. Given that consumer, ``embedded`` was the right call.

    What changed is the consumer, not the cost calculus. The seeded Aura
    instance is no longer a ~126-node xref mirror: measured this round it holds
    113 Article / 13 Annex / 656 Paragraph / 416 Point / 180 Recital / 68
    Definition nodes and 1838 edges (seed ``2026-07-24-r291-fullseed``,
    kb_version ``2024.1689.v18``). The HAS_PARAGRAPH / HAS_POINT / HAS_SUBPOINT
    / HAS_RECITAL_ANCHOR hierarchy is real content the embedded mirror does not
    carry, and :mod:`app.engines.kg_context` now consumes it on the answer path.
    The R98/R99.1 hazards were duplicate-node drift and empty-graph
    zero-retrieval; the instance is currently clean (counts verified above) and
    the R99.1 empty-success KB fallback remains in place as the backstop.

    NOTE the coupling that makes this flip load-bearing rather than cosmetic:
    ``GraphClient._should_activate`` gates the driver on this selector, so with
    ``embedded`` the Neo4j client is disabled outright and ``kg_context`` would
    silently render nothing — the R256 inert-feature trap.

    Returns one of ``neo4j`` (default), ``embedded``, ``rushdb``. Unknown /
    empty values resolve to the default. Set
    ``REGENOLD_GRAPH_BACKEND=embedded`` to restore the R127 behaviour (which is
    also the correct choice for any deploy without Aura credentials — the
    client simply stays disabled and every graph consumer fails soft to the
    pre-R313.1 path). The davidath bench leaves ``REGENOLD_GRAPH_2HOP`` unset,
    so the 2-hop is off there regardless of backend → byte-identical.
    """
    val = os.getenv(_BACKEND_ENV, _DEFAULT_BACKEND).strip().lower()
    return val or _DEFAULT_BACKEND


def embedded_backend_selected() -> bool:
    """True iff the embedded in-process graph backend is active (R127 default)."""
    return graph_backend() == "embedded"


def neo4j_backend_selected() -> bool:
    """True iff the hosted Neo4j Aura backend is EXPLICITLY selected.

    R127 — Aura now activates only on an explicit
    ``REGENOLD_GRAPH_BACKEND=neo4j``; the unset default is ``embedded``.
    ``app.graph.client._should_activate`` gates the Neo4j driver on this so a
    deploy that still carries ``NEO4J_URI`` in its dashboard does NOT pay the
    Aura retrieval / boot-seed network cost unless it opts back in.
    """
    return graph_backend() == "neo4j"


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
    "graph_backend",
    "embedded_backend_selected",
    "neo4j_backend_selected",
]
