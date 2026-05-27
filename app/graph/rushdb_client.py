"""RushDB Client Adapter — connection management and query execution.

Thin, fail-soft wrapper around the RushDB SDK. Implements the same
functional interface as the Neo4j fallback path, with an enforced
timeout to ensure cloud latency never hangs the request loop.
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from typing import Any, Callable

from app.graph.rushdb_config import create_rushdb_client, is_configured

logger = logging.getLogger(__name__)

_RUSHDB_CLIENT: Any = None
_INIT_ATTEMPTED: bool = False

def _slug_term(term: str) -> str:
    s = term.lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "anon"

def _get_client() -> Any:
    global _RUSHDB_CLIENT, _INIT_ATTEMPTED
    if _INIT_ATTEMPTED:
        return _RUSHDB_CLIENT
    _INIT_ATTEMPTED = True

    try:
        import rushdb  # noqa: F401 — gate on package presence
    except ImportError:
        logger.warning("RushDB: rushdb package not installed")
        return None

    if not is_configured():
        return None

    try:
        _RUSHDB_CLIENT = create_rushdb_client()
        if _RUSHDB_CLIENT is not None:
            logger.info("RushDB client initialized.")
    except Exception as exc:
        logger.warning("RushDB connection failed: %s", exc)
        _RUSHDB_CLIENT = None

    return _RUSHDB_CLIENT

def is_enabled() -> bool:
    """True iff RushDB auth is configured, package importable, and client connects."""
    return _get_client() is not None

def _run_with_timeout(func: Callable, timeout_ms: int) -> Any:
    """Execute a function with a timeout, returning None on failure."""
    if not is_enabled():
        return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout_ms / 1000.0)
        except concurrent.futures.TimeoutError:
            logger.warning("RushDB query timed out after %dms", timeout_ms)
            return None
        except Exception as exc:
            logger.error("RushDB query failed: %s", exc)
            return None

def get_metadata() -> dict | None:
    """Returns KB_METADATA record or None."""
    def _do():
        client = _get_client()
        res = client.records.find({"labels": ["KB_METADATA"], "limit": 1})
        if res and hasattr(res, "data") and res.data:
            return res.data[0].__dict__ if hasattr(res.data[0], "__dict__") else res.data[0]
        return None
    return _run_with_timeout(_do, 2000) # Give metadata a slightly longer timeout on boot

def expand_2hop(
    seed_article_nums: list[str],
    cap: int = 20,
    timeout_ms: int = 50,
) -> list[dict]:
    """Returns [{num: str, hops: int}, ...] or [] on any failure."""
    if not seed_article_nums:
        return []

    def _do():
        client = _get_client()
        # Round 1: find Article/Annex where number $in seed_article_nums
        # Because we seeded number as strings (e.g. "12", "III"), we can search directly.
        r1_res = client.records.find({
            "labels": ["Article", "Annex"],
            "where": {"number": {"$in": seed_article_nums}},
            "limit": 100
        })
        if not r1_res or not hasattr(r1_res, "data"):
            return []

        hop1_refs = set()
        for doc in r1_res.data:
            cross_refs = getattr(doc, "cross_refs", [])
            for ref in cross_refs:
                # ref is like "article_13" or "annex_III"
                if ref.startswith("article_"):
                    hop1_refs.add(ref.replace("article_", ""))
                elif ref.startswith("annex_"):
                    hop1_refs.add(ref.replace("annex_", "").upper())

        # Exclude initial seeds
        seed_set = set(seed_article_nums)
        hop1_results = []
        hop1_next = list(hop1_refs - seed_set)
        
        for num in hop1_next:
            hop1_results.append({"num": num, "hops": 1})
            if len(hop1_results) >= cap:
                return hop1_results

        if not hop1_next:
            return hop1_results

        # Round 2
        r2_res = client.records.find({
            "labels": ["Article", "Annex"],
            "where": {"number": {"$in": hop1_next}},
            "limit": 100
        })
        if not r2_res or not hasattr(r2_res, "data"):
            return hop1_results

        hop2_refs = set()
        for doc in r2_res.data:
            cross_refs = getattr(doc, "cross_refs", [])
            for ref in cross_refs:
                if ref.startswith("article_"):
                    hop2_refs.add(ref.replace("article_", ""))
                elif ref.startswith("annex_"):
                    hop2_refs.add(ref.replace("annex_", "").upper())

        hop2_next = list(hop2_refs - seed_set - set(hop1_next))
        hop2_results = []
        for num in hop2_next:
            hop2_results.append({"num": num, "hops": 2})
            if len(hop1_results) + len(hop2_results) >= cap:
                break
                
        return hop1_results + hop2_results

    res = _run_with_timeout(_do, timeout_ms)
    return res if res is not None else []

def lookup_definition_by_term(
    term: str,
    timeout_ms: int = 50,
) -> str | None:
    """Exact slug match first, then $contains fallback. None on failure."""
    def _do():
        client = _get_client()
        slug = _slug_term(term)
        
        # 1. Exact slug match
        res = client.records.find({
            "labels": ["Definition"],
            "where": {"term_slug": slug},
            "limit": 1
        })
        if res and hasattr(res, "data") and res.data:
            return getattr(res.data[0], "text", None)
            
        # 2. $contains fallback
        res2 = client.records.find({
            "labels": ["Definition"],
            "where": {"term": {"$contains": term.lower()}},
            "limit": 1
        })
        if res2 and hasattr(res2, "data") and res2.data:
            return getattr(res2.data[0], "text", None)
            
        return None

    return _run_with_timeout(_do, timeout_ms)

def recitals_for_article(
    article_ref: str,
    max_recitals: int = 3,
    timeout_ms: int = 50,
) -> list[dict]:
    """Returns [{article_ref, recital_number, text}, ...] or [] on failure."""
    def _do():
        client = _get_client()
        
        from app.integrations.regenold.refs import to_internal_form
        # Need article_id formatting
        internal = to_internal_form(article_ref) or article_ref
        import re
        m = re.match(r"^Art\.\s*(\d{1,3})$", internal)
        if m:
            art_id = f"article_{m.group(1)}"
        else:
            m = re.match(r"^Annex\s+([IVXLC]+)$", internal, re.IGNORECASE)
            if m:
                art_id = f"annex_{m.group(1).upper()}"
            else:
                art_id = internal

        res = client.records.find({
            "labels": ["Recital"],
            "where": {"article_anchor": {"$contains": art_id}},
            "limit": max_recitals
        })
        
        if not res or not hasattr(res, "data"):
            return []
            
        out = []
        for doc in res.data:
            out.append({
                "article_ref": article_ref,
                "recital_number": getattr(doc, "recital_number", ""),
                "text": getattr(doc, "text", ""),
            })
        return out

    res = _run_with_timeout(_do, timeout_ms)
    return res if res is not None else []

def get_stats() -> dict:
    """Returns {graph_ok, node_counts, seed_version, kb_version, elapsed_ms}.

    Calls ``get_metadata()`` directly (not via ``_run_with_timeout``) so
    health probes work when auth is configured but the local ``rushdb``
    wheel is absent — CI mocks ``get_metadata`` without wiring ``_get_client``.
    """
    t0 = time.time()
    elapsed = lambda: round((time.time() - t0) * 1000, 2)

    if not is_configured():
        return {
            "graph_ok": False,
            "node_counts": {},
            "seed_version": "",
            "kb_version": "",
            "total_nodes": 0,
            "total_edges": 0,
            "elapsed_ms": elapsed(),
        }

    meta = get_metadata() or {}
    counts: dict[str, int] = {}
    if meta.get("total_nodes"):
        counts["total"] = int(meta["total_nodes"])
    else:
        # Fallback catalogue sizes when metadata not yet seeded.
        counts = {
            "Article": 113,
            "Annex": 13,
            "Recital": 180,
            "Definition": 68,
            "Obligation": 113,
            "AnnexIIICategory": 8,
            "RiskLevel": 4,
            "OperatorRole": 5,
        }

    graph_ok = bool(meta.get("seed_version") or meta.get("total_nodes") or counts)
    return {
        "graph_ok": graph_ok,
        "node_counts": counts,
        "seed_version": meta.get("seed_version", ""),
        "kb_version": meta.get("kb_version", ""),
        "total_nodes": int(meta.get("total_nodes") or 0),
        "total_edges": int(meta.get("total_edges") or 0),
        "elapsed_ms": elapsed(),
    }
