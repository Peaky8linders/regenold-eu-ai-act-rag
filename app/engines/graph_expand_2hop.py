"""Neo4j-backed 2-hop graph expansion — opt-in companion to the in-memory 1-hop path.

The Round-31.1 :mod:`app.engines.graphrag_expand` module walks the
:data:`app.data.kb_xrefs._build_xref_graph` 1-hop xref graph + a curated
HRAIS chain table in pure Python. That ships **on every request** and
covers the architecture-PDF "Art. 6 → Art. 9 + Art. 11 …" obligation
chain explicitly. It cannot surface **2-hop** connections that no single
xref entry encodes (e.g. an article only referenced from another's
recital, or a chain that takes two regex-extracted hops to reach).

This module fills that gap **via Neo4j** when a graph instance is
available:

* ``MATCH (a:Article {number:$n})-[:CROSS_REFERENCES*1..2]-(b:Article)``
* split results into 1-hop neighbours vs 2-hop-only neighbours
* fuse 2-hop-only additions onto the BM25 winner list, **additive only**

The hypothesis (per the parent task): a 2-hop expansion surfaces
non-obvious connections that BM25 + the in-memory 1-hop path miss —
especially for paraphrased / novel-form queries that don't share
keywords with the original articles. The bench can't measure this (the
davidath gold set is keyword-aligned with BM25's recall surface) so the
module ships **env-gated, default OFF**. Production deploy turns it on
once a seeded Neo4j is wired.

## Hard guarantees

* **Default OFF**: `REGENOLD_GRAPH_2HOP=1` is required to switch on.
  When unset (or any value other than ``"1"``), :func:`is_enabled`
  returns ``False`` and every public function is a passthrough.
* **Never raises**: every Neo4j call is wrapped — any exception, any
  timeout, any malformed response collapses to an empty
  :class:`GraphExpansion`. The route is route-safe under a downed /
  unseeded / misconfigured graph.
* **Additive fusion**: :func:`fuse_with_kb_xrefs` only **appends**
  2-hop neighbours to the BM25 winner list. It never reshuffles a
  winner's rank.
* **Existence-gated**: every 2-hop ref is validated against
  :data:`app.data.article_existence.ARTICLE_EXISTENCE` before it's
  surfaced. A malformed seed in Neo4j can't pollute the wire.

## Timeout strategy (Windows-aware)

The wrapper enforces ``timeout_ms`` via :mod:`concurrent.futures`
(``ThreadPoolExecutor`` with ``future.result(timeout=...)``). This is
chosen over :mod:`signal` because:

* ``signal.alarm`` is **POSIX-only** — it doesn't exist on Windows,
  which is the canonical dev path for this repo (see ``CLAUDE.md``).
* The Cypher query is read-only; a dangling thread on timeout costs a
  pool slot for a few hundred ms but doesn't corrupt state.

For Neo4j **server-side** timeout we set the Cypher driver's
configured per-tx timeout when available (the ``client.execute_read``
path doesn't expose this knob — the Python-side ``futures`` timeout is
the canonical guard).

## Wiring (NOT done in this module)

The parent task carves wiring out — the caller (likely
:func:`app.data.kb_search.top_articles_by_relevance`) calls
:func:`expand_2hop` to get a :class:`GraphExpansion`, then calls
:func:`fuse_with_kb_xrefs` on the BM25 winner list with the expansion.
That's a follow-up PR; this module just exports the primitives.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.data.article_existence import ARTICLE_EXISTENCE

if TYPE_CHECKING:  # pragma: no cover — typing only
    from concurrent.futures import ThreadPoolExecutor

    from app.graph.client import GraphClient

logger = logging.getLogger(__name__)

# ── Env gate ────────────────────────────────────────────────────────────────

_ENV_VAR = "REGENOLD_GRAPH_2HOP"


def _env_enabled() -> bool:
    """Return True iff the env-var is exactly ``"1"``.

    Strict equality so accidental ``"0"`` / ``""`` / ``"false"`` never
    flip the switch.
    """
    return os.environ.get(_ENV_VAR, "") == "1"


# ── Public dataclass ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GraphExpansion:
    """Result of a 2-hop expansion call.

    All four fields are populated even on the no-op / failure paths:

    * ``seed_articles`` echoes the input (in **internal** form,
      ``Art. N`` / ``Annex X``) so callers can sanity-check what was
      sent.
    * ``hop1_articles`` is the 1-hop neighbour set returned by Cypher.
      The route never APPENDS hop1 neighbours — the in-memory 1-hop
      path in :mod:`app.engines.graphrag_expand` already does that, and
      double-appending would over-cite. We surface hop1 for diagnostic
      logging.
    * ``hop2_articles`` is the **2-hop-only** set (in hop2 but NOT in
      hop1). These are the candidate additions for fusion.
    * ``elapsed_ms`` is the wall-clock cost of the Cypher call. Useful
      for production p50/p95 monitoring.
    """

    seed_articles: tuple[str, ...] = ()
    hop1_articles: tuple[str, ...] = ()
    hop2_articles: tuple[str, ...] = ()
    elapsed_ms: int = 0


# Module-level shared executor — one persistent thread is plenty for
# the Cypher call (each request runs one expansion). Created lazily so
# module import stays sub-1ms when the env-gate is off.
_EXECUTOR: Any = None


def _get_executor() -> "ThreadPoolExecutor":
    """Lazy executor accessor — single-worker pool, daemon threads.

    ``concurrent.futures`` pulls ``threading`` + ``queue`` (~40 ms cold
    import) so we defer it until the first ``expand_2hop`` call. Keeps
    module import sub-1ms when the env-gate is off (which is the
    default path).
    """
    global _EXECUTOR
    if _EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor

        _EXECUTOR = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="graph2hop",
        )
    return _EXECUTOR


# ── Ref normalisation ──────────────────────────────────────────────────────
#
# Neo4j stores the article identifier in a ``number`` property — we use
# the stripped numeric / Roman-numeral token (e.g. ``"6"``, ``"III"``)
# rather than the full ``"Art. 6"`` / ``"Annex III"`` so the Cypher
# query is editor-agnostic across seed schemas.

# R46 B8 — converter logic migrated to ``app.integrations.regenold.refs``.
# The Neo4j ``number`` property is the bare numeric / Roman tag of the
# parent (e.g. ``"6"`` / ``"III"``), so sub-points are stripped post-parse.
from app.integrations.regenold.refs import (  # noqa: E402
    InvalidRefError as _RefsInvalidRefError,
)
from app.integrations.regenold.refs import (  # noqa: E402
    parse as _refs_parse,
)


def _seed_to_num(seed: str) -> str | None:
    """Convert a seed ref into the Cypher ``number`` parameter.

    Accepts both internal (``Art. 6`` / ``Annex III``) and user-facing
    (``Article 6`` / ``Annex III``) forms. Strips sub-points (``Art.
    13.2`` → ``"13"``) because the xref graph collapses sub-points to
    the parent article.
    """
    if not seed:
        return None
    try:
        spec = _refs_parse(seed)
    except _RefsInvalidRefError:
        return None
    if spec.is_annex:
        return spec.annex_roman
    return str(spec.article_number)


def _num_to_internal(num: str) -> str | None:
    """Convert a Neo4j ``number`` value back to internal ref form.

    Arabic numerals → ``Art. N``. Roman numerals → ``Annex X``. Anything
    else → ``None`` (defensive — a malformed Neo4j row can't pollute
    the wire).
    """
    if not num:
        return None
    token = str(num).strip()
    if not token:
        return None
    # Arabic → article
    if token.isdigit():
        return f"Art. {token}"
    # Roman → annex
    if re.fullmatch(r"[IVXLCDM]+", token.upper()):
        return f"Annex {token.upper()}"
    return None


def _is_real_ref(internal_ref: str) -> bool:
    """Confidence-check against ``ARTICLE_EXISTENCE``.

    The xref graph collapses sub-points, so a 2-hop result like
    ``Art. 6`` should always match. A spurious ``Art. 200`` from a
    misseeded Neo4j won't pass this gate.
    """
    return internal_ref in ARTICLE_EXISTENCE


# ── Cypher ─────────────────────────────────────────────────────────────────

# Symmetric (undirected) variable-length match. Length 1..2 returns
# both hop1 + hop2 neighbours. We disambiguate hop tier via shortest
# path length so the caller can split.
#
# Bound vars only — never string-format user input into Cypher.
# R39 eng-review F6: previously matched only ``(a:Article)``, so Annex
# seeds (Roman-numeral ``number`` like ``"III"``) were silently
# dropped — even when an Annex was the top BM25 winner. Now matches
# any seed node (Article or Annex) by number, and returns any
# neighbour by number too. Annex III scenarios get their 2-hop
# expansion back.
_CYPHER_2HOP = """
MATCH (a)-[:CROSS_REFERENCES*1..2]-(b)
WHERE a.number IN $seed_nums AND b.number IS NOT NULL
  AND a.number <> b.number
  AND (a:Article OR a:Annex) AND (b:Article OR b:Annex)
RETURN DISTINCT b.number AS num,
       length(shortestPath((a)-[:CROSS_REFERENCES*]-(b))) AS hops
ORDER BY hops, num
LIMIT $cap
""".strip()


# ── Public API ──────────────────────────────────────────────────────────────


def is_enabled() -> bool:
    """True iff the env-var is set AND the graph client is connected.

    Both conditions must hold. The env-var alone isn't enough — if
    Neo4j is down or the driver isn't installed, the module stays in
    passthrough mode.
    """
    if not _env_enabled():
        return False
    # Lazy client import — defers the heavy ``app.graph.client`` load
    # until the first ``is_enabled()`` / ``expand_2hop`` call.
    try:
        from app.graph.client import get_graph_client
    except Exception:  # noqa: BLE001
        # Pathologically — if the graph subpackage itself can't import,
        # we treat it as disabled rather than letting the exception
        # propagate to the request path.
        logger.debug("graph_2hop client import failed", exc_info=True)
        return False
    try:
        client = get_graph_client()
    except Exception:  # noqa: BLE001
        logger.debug("graph_2hop get_graph_client failed", exc_info=True)
        return False
    return bool(getattr(client, "enabled", False))


def _empty_expansion(seeds: list[str]) -> GraphExpansion:
    """Build a no-op result preserving the seed echo."""
    seed_tuple = tuple(s for s in seeds if s)
    return GraphExpansion(
        seed_articles=seed_tuple,
        hop1_articles=(),
        hop2_articles=(),
        elapsed_ms=0,
    )


def _resolve_client() -> "GraphClient | None":
    """Lazy-load + return the graph client iff it's connected."""
    try:
        from app.graph.client import get_graph_client
    except Exception:  # noqa: BLE001
        logger.debug("graph_2hop client import failed", exc_info=True)
        return None
    try:
        client = get_graph_client()
    except Exception:  # noqa: BLE001
        logger.debug("graph_2hop get_graph_client failed", exc_info=True)
        return None
    if not getattr(client, "enabled", False):
        return None
    return client


def expand_2hop(
    seed_articles: list[str],
    *,
    max_hop2: int = 5,
    timeout_ms: int = 50,
) -> GraphExpansion:
    """Run a 2-hop Cypher expansion across the :Article CROSS_REFERENCES graph.

    Args:
        seed_articles: Refs to expand from. Internal (``Art. N`` /
            ``Annex X``) or user-facing (``Article N``) form — both
            are normalised to the Neo4j ``number`` property.
        max_hop2: Cap on the number of 2-hop-only refs returned. The
            Cypher ``LIMIT`` is ``max_hop2 * 2`` so we get headroom to
            filter out hop1 duplicates + invalid refs.
        timeout_ms: Wall-clock timeout (Python-side, via
            ``concurrent.futures``). Documented Windows-aware
            behaviour — ``signal.alarm`` is POSIX-only so we use the
            futures path uniformly across platforms. Any timeout
            collapses to an empty expansion.

    Returns:
        :class:`GraphExpansion`. Never raises — every error path
        produces an empty expansion with the original seeds echoed.
    """
    # Fast path: gate off → no work.
    if not _env_enabled():
        return _empty_expansion(seed_articles)
    if not seed_articles:
        return GraphExpansion()
    if max_hop2 <= 0:
        return _empty_expansion(seed_articles)

    client = _resolve_client()
    if client is None:
        return _empty_expansion(seed_articles)

    # Normalise seeds → numbers. Drop unparseable refs but keep the
    # echo in ``seed_articles``.
    seed_nums: list[str] = []
    seed_echo: list[str] = []
    for s in seed_articles:
        seed_echo.append(s)
        num = _seed_to_num(s)
        if num is not None:
            seed_nums.append(num)
    if not seed_nums:
        return _empty_expansion(seed_articles)

    cap = max(max_hop2 * 2, 4)

    started = time.perf_counter()

    # Run the Cypher inside the executor so we can enforce the
    # Python-side wall-clock timeout. ``execute_read`` already catches
    # its own exceptions and returns ``[]`` — we still wrap defensively
    # so a future implementation that raises doesn't escape.
    def _call() -> list[dict]:
        try:
            return client.execute_read(
                _CYPHER_2HOP,
                {"seed_nums": seed_nums, "cap": cap},
            )
        except Exception:  # noqa: BLE001
            logger.debug("graph_2hop execute_read raised", exc_info=True)
            return []

    # Defer the futures import to first use — see ``_get_executor`` docstring.
    from concurrent.futures import TimeoutError as _FutTimeout

    rows: list[dict] = []
    try:
        fut = _get_executor().submit(_call)
        rows = fut.result(timeout=max(timeout_ms, 1) / 1000.0)
    except _FutTimeout:
        logger.info(
            "graph_2hop cypher timeout seeds=%s budget=%dms",
            seed_nums, timeout_ms,
        )
        rows = []
    except Exception:  # noqa: BLE001
        logger.debug("graph_2hop submit/result failed", exc_info=True)
        rows = []

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # Split rows by hop tier + dedupe + existence-check.
    hop1: list[str] = []
    hop2: list[str] = []
    seen_internal: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        num = row.get("num")
        hops = row.get("hops")
        if num is None or hops is None:
            continue
        internal = _num_to_internal(str(num))
        if internal is None:
            continue
        if internal in seen_internal:
            continue
        if not _is_real_ref(internal):
            continue
        seen_internal.add(internal)
        try:
            hop_n = int(hops)
        except (TypeError, ValueError):
            continue
        if hop_n <= 1:
            hop1.append(internal)
        else:
            # 2-hop-only candidates — capped to max_hop2.
            if len(hop2) < max_hop2:
                hop2.append(internal)

    return GraphExpansion(
        seed_articles=tuple(seed_echo),
        hop1_articles=tuple(hop1),
        hop2_articles=tuple(hop2),
        elapsed_ms=elapsed_ms,
    )


def fuse_with_kb_xrefs(
    bm25_winners: list[str],
    graph_expansion: GraphExpansion,
    *,
    budget: int = 10,
) -> list[str]:
    """Additive fusion — append 2-hop-only refs to ``bm25_winners``.

    Behaviour:

    * **BM25 winners always survive.** Their order is preserved; no
      ranking shuffle. This honours the Round-31 finding that
      displacing a BM25 winner via dense recall costs Strict F1 more
      than it gains in Loose Recall.
    * **Hop1 refs are dropped from fusion.** The in-memory 1-hop path
      in :mod:`app.engines.graphrag_expand` already covers them, and
      double-appending would over-cite.
    * **Hop2-only refs are deduplicated against the BM25 winners**
      before append (a winner that's also a 2-hop neighbour stays at
      its winner rank, not appended a second time).
    * **Budget cap.** Output length never exceeds ``budget``.
    * **Refs accepted in either form** — internal (``Art. 6``) or
      user-facing (``Article 6``). Comparison is form-aware (we never
      treat ``Art. 6`` and ``Article 6`` as the same string).

    Args:
        bm25_winners: The BM25 ranking — preserved verbatim.
        graph_expansion: Result from :func:`expand_2hop`. Only the
            ``hop2_articles`` field is consumed.
        budget: Cap on the total output length.

    Returns:
        New list — never mutates input. Empty input + empty expansion
        returns ``[]``.
    """
    out: list[str] = list(bm25_winners or [])
    if budget <= len(out):
        # No room to fuse — return BM25 winners (possibly truncated to
        # the budget for symmetry with the expansion path).
        return out[:budget]

    if not graph_expansion or not graph_expansion.hop2_articles:
        return out[:budget]

    seen: set[str] = set(out)
    remaining = budget - len(out)
    for ref in graph_expansion.hop2_articles:
        if remaining <= 0:
            break
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
        remaining -= 1
    return out[:budget]


__all__ = [
    "GraphExpansion",
    "is_enabled",
    "expand_2hop",
    "fuse_with_kb_xrefs",
]
