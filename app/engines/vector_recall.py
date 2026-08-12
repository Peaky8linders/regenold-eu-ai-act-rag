"""Route-safe additive recall module using Neo4j vector indexes and local SVD embedding index.

This module surfaces article/annex candidates that BM25 may miss by leveraging:
1. Neo4j native vector indexes (`v_article_embedding`, `v_annex_embedding`) when active.
2. Local sentence-level TF-IDF+SVD embedding index as a fail-soft fallback.

It is purely additive and route-safe (returns `[]` on any exception).
It respects two environment variables (read fresh per call):
- REGENOLD_GRAPH_VECTOR_RECALL: If "1", activates the recall path. Default OFF.
- REGENOLD_VECTOR_MIN_SIM: The similarity floor for candidates. Default "0.35".
"""
from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ANNEX_ARABIC_TO_ROMAN = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
    6: "VI",
    7: "VII",
    8: "VIII",
    9: "IX",
    10: "X",
    11: "XI",
    12: "XII",
    13: "XIII",
}


@dataclass(frozen=True)
class RecallHit:
    """A validated recall result with auditable retrieval provenance."""

    ref: str
    score: float
    source: str


def _norm_ref(r: str) -> str:
    r = str(r).strip()
    m_art = re.search(r"(?i)\b(?:Art\.?|Article|article_)\s*(\d+)", r)
    if m_art:
        return f"Art. {m_art.group(1)}"
    m_ann_arabic = re.search(r"(?i)\b(?:Annex\s+|annex_)(\d{1,2})\b", r)
    if m_ann_arabic:
        roman = _ANNEX_ARABIC_TO_ROMAN.get(int(m_ann_arabic.group(1)))
        if roman is not None:
            # Recall validates and returns provision heads. Any paragraph/item
            # suffix is therefore collapsed consistently with Article refs.
            return f"Annex {roman}"
    m_ann = re.search(r"(?i)\b(?:Annex|annex_)\s*([IVXLCDM]+)", r)
    if m_ann:
        return f"Annex {m_ann.group(1).upper()}"
    return r


def is_enabled() -> bool:
    """Return True if the vector recall path is enabled via env and assets exist."""
    if os.environ.get("REGENOLD_GRAPH_VECTOR_RECALL") != "1":
        return False

    try:
        from app.engines import embeddings_index
        return embeddings_index.is_available()
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: is_available check failed: %s", exc)
        return False


def _query_neo4j_vector_index(question: str, top_k: int, min_sim: float) -> list[RecallHit]:
    """Query both Neo4j vector indexes and retain index provenance."""
    try:
        from app.graph.client import get_graph_client  # noqa: PLC0415
        client = get_graph_client()
        if not getattr(client, "enabled", False):
            return []

        from app.engines.embeddings_index import _embed_query  # noqa: PLC0415
        from app.engines.kg_context import _bounded_execute_read  # noqa: PLC0415

        vec = _embed_query(question)
        if vec is None:
            return []

        emb_list = [float(x) for x in vec]
        hits: list[RecallHit] = []
        per_index_k = max(1, min(100, int(top_k) * 2))
        for index_name in ("v_article_embedding", "v_annex_embedding"):
            cypher = f"""
            CALL db.index.vector.queryNodes('{index_name}', $k, $emb)
            YIELD node, score
            RETURN coalesce(node.strict_citation, node.id) AS ref, score
            """
            rows = _bounded_execute_read(
                cypher,
                {"k": per_index_k, "emb": emb_list},
            )
            for row in rows or []:
                ref = str(row.get("ref") or "").strip()
                try:
                    score = float(row.get("score") or 0.0)
                except (TypeError, ValueError):
                    continue
                if ref and math.isfinite(score) and score >= min_sim:
                    hits.append(
                        RecallHit(ref=ref, score=score, source=f"neo4j:{index_name}")
                    )

        return hits
    except Exception as exc:  # noqa: BLE001
        logger.debug("vector_recall: neo4j vector query skipped/failed: %s", exc)
        return []


def recall_articles_with_provenance(
    question: str,
    *,
    top_k: int = 3,
) -> list[RecallHit]:
    """Return validated article/annex hits with source and similarity.

    Queries Neo4j vector indexes first if active; falls back to the local sentence-level
    embeddings index.

    Returns `[]` on every error path (route-safe). Filters hits by the
    `REGENOLD_VECTOR_MIN_SIM` threshold and verifies the article exists
    in `ARTICLE_EXISTENCE`.
    """
    if not is_enabled() or top_k <= 0:
        return []

    try:
        from app.data import article_existence
        from app.engines import embeddings_index
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: failed to import dependencies: %s", exc)
        return []

    try:
        min_sim_str = os.environ.get("REGENOLD_VECTOR_MIN_SIM", "0.35")
        min_sim = float(min_sim_str)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: failed to parse REGENOLD_VECTOR_MIN_SIM: %s", exc)
        min_sim = 0.35

    try:
        valid_refs = set(article_existence.ARTICLE_EXISTENCE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: failed to load valid refs: %s", exc)
        return []

    hits_by_ref: dict[str, RecallHit] = {}

    # 1. Primary path: Try Neo4j native vector search
    n4j_hits = _query_neo4j_vector_index(question, top_k=top_k, min_sim=min_sim)
    for hit in n4j_hits:
        ref = _norm_ref(hit.ref)
        if ref not in valid_refs:
            continue
        previous = hits_by_ref.get(ref)
        if previous is None or hit.score > previous.score:
            hits_by_ref[ref] = RecallHit(ref=ref, score=hit.score, source=hit.source)

    # 2. Fallback path: native garbage is not availability. Fall back unless
    # Neo4j produced at least one canonical, corpus-valid provision.
    if not hits_by_ref:
        try:
            hits = embeddings_index.query(question, top_k=50, threshold=min_sim)
            for hit in hits:
                ref = _norm_ref(hit.article_ref)
                try:
                    score = float(hit.similarity)
                except (TypeError, ValueError):
                    continue
                if ref not in valid_refs or not math.isfinite(score) or score < min_sim:
                    continue
                previous = hits_by_ref.get(ref)
                if previous is None or score > previous.score:
                    hits_by_ref[ref] = RecallHit(
                        ref=ref,
                        score=score,
                        source="local:svd_sentence",
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vector_recall: embeddings_index.query failed: %s", exc)
            return []

    try:
        return sorted(hits_by_ref.values(), key=lambda hit: hit.score, reverse=True)[:top_k]
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: failed to process hits: %s", exc)
        return []


def recall_articles(question: str, *, top_k: int = 3) -> list[str]:
    """Compatibility wrapper returning only canonical provision refs."""
    return [
        hit.ref
        for hit in recall_articles_with_provenance(question, top_k=top_k)
    ]


__all__ = [
    "RecallHit",
    "is_enabled",
    "recall_articles",
    "recall_articles_with_provenance",
]
