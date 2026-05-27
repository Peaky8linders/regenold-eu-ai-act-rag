"""RushDB hybrid retrieval — intent + metadata + semantic search (Hybrid_RAG_Guide).

Env-gated ``REGENOLD_RUSHDB_HYBRID`` (default OFF). Purely additive: returns
internal article refs for kb_search to append without displacing BM25 winners.
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.data.article_existence import ARTICLE_EXISTENCE

logger = logging.getLogger(__name__)

_ART_NUM_RE = re.compile(r"^Art\.\s*(\d{1,3})$", re.IGNORECASE)
_ANNEX_ROMAN_RE = re.compile(r"^Annex\s+([IVXLC]+)$", re.IGNORECASE)


def is_hybrid_enabled() -> bool:
    flag = os.getenv("REGENOLD_RUSHDB_HYBRID", "0").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return False
    try:
        from app.graph.rushdb_client import is_enabled

        return is_enabled()
    except Exception:  # noqa: BLE001
        return False


def classify_query_intent(query: str) -> dict[str, Any]:
    """Lightweight intent router aligned with Hybrid_RAG_Guide §3."""
    q = query.lower()
    if any(t in q for t in ("article", "annex", "obligation", "provider", "deployer")):
        return {"intent": "regulatory_lookup", "source_types": ["regulation"]}
    if any(t in q for t in ("evidence", "prove", "audit", "log", "record")):
        return {"intent": "evidence_lookup", "source_types": ["regulation"]}
    if any(t in q for t in ("control", "mitigation", "implementation", "how do we")):
        return {"intent": "control_mapping", "source_types": ["regulation"]}
    return {"intent": "general", "source_types": ["regulation"]}


def _record_to_internal_ref(record: Any) -> str | None:
    """Map a RushDB Article/Annex record to internal BM25 ref form."""
    label = getattr(record, "label", None) or getattr(record, "_label", None)
    number = getattr(record, "number", None)
    if number is None and hasattr(record, "__dict__"):
        number = record.__dict__.get("number")
    rec_id = getattr(record, "id", None) or (
        record.__dict__.get("id") if hasattr(record, "__dict__") else None
    )
    if number is not None:
        num_str = str(number).strip()
        if label == "Annex" or (isinstance(label, str) and label.lower() == "annex"):
            return f"Annex {num_str.upper()}"
        if label == "Article" or (isinstance(label, str) and label.lower() == "article"):
            return f"Art. {num_str}"
    # Infer from id field when label/number missing
    if isinstance(rec_id, str):
        if rec_id.startswith("article_"):
            return f"Art. {rec_id.replace('article_', '')}"
        if rec_id.startswith("annex_"):
            return f"Annex {rec_id.replace('annex_', '').upper()}"
    return None


def _valid_ref(ref: str | None) -> bool:
    if not ref:
        return False
    if ref in ARTICLE_EXISTENCE:
        return True
    if _ART_NUM_RE.match(ref.replace("Art. ", "Art. ") if ref.startswith("Art") else ref):
        return ref in ARTICLE_EXISTENCE
    return ref in ARTICLE_EXISTENCE


def _semantic_search(client: Any, query: str, limit: int) -> list[str]:
    """Article-level semantic search on ``content`` then ``text``."""
    refs: list[str] = []
    if not hasattr(client, "ai") or not hasattr(client.ai, "search"):
        return refs
    for prop in ("content", "text"):
        try:
            res = client.ai.search(
                {
                    "labels": ["Article", "Annex"],
                    "propertyName": prop,
                    "query": query,
                    "limit": limit,
                }
            )
            data = getattr(res, "data", None) or []
            for row in data:
                ref = _record_to_internal_ref(row)
                if ref and ref in ARTICLE_EXISTENCE and ref not in refs:
                    refs.append(ref)
            if refs:
                break
        except Exception as exc:  # noqa: BLE001
            logger.debug("RushDB semantic search failed prop=%s: %s", prop, exc)
    return refs


def _metadata_search(client: Any, query: str, limit: int) -> list[str]:
    """Title/number substring match when AI search unavailable."""
    refs: list[str] = []
    q_lower = query.lower()
    try:
        res = client.records.find(
            {
                "labels": ["Article", "Annex"],
                "where": {
                    "$or": [
                        {"title": {"$contains": q_lower[:80]}},
                        {"number": {"$contains": q_lower[:20]}},
                        {"text": {"$contains": q_lower[:80]}},
                    ]
                },
                "limit": limit,
            }
        )
        data = getattr(res, "data", None) or []
        for row in data:
            ref = _record_to_internal_ref(row)
            if ref and ref in ARTICLE_EXISTENCE and ref not in refs:
                refs.append(ref)
    except Exception as exc:  # noqa: BLE001
        logger.debug("RushDB metadata search failed: %s", exc)
    return refs


def retrieve_article_refs(question: str, limit: int = 8) -> list[str]:
    """Parallel semantic + metadata retrieval; returns deduped internal refs."""
    if not is_hybrid_enabled():
        return []
    try:
        from app.graph.rushdb_client import _get_client
    except Exception:  # noqa: BLE001
        return []
    client = _get_client()
    if client is None:
        return []

    classify_query_intent(question)  # reserved for future weighting
    semantic: list[str] = []
    metadata: list[str] = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_sem = pool.submit(_semantic_search, client, question, limit)
        f_meta = pool.submit(_metadata_search, client, question, limit)
        for fut in as_completed((f_sem, f_meta)):
            try:
                hits = fut.result()
                if fut is f_sem:
                    semantic = hits
                else:
                    metadata = hits
            except Exception:  # noqa: BLE001
                continue

    # Fuse: semantic first, then metadata fill (simple RRF substitute).
    fused: list[str] = []
    for ref in semantic + metadata:
        if ref not in fused:
            fused.append(ref)
        if len(fused) >= limit:
            break
    return fused
