"""Route-safe additive recall module using the local sentence-level embedding index.

This module surfaces article candidates that BM25 may miss by leveraging
the sentence-level TF-IDF+SVD embedding index. It is purely additive and
does not depend on Neo4j or external services.

It respects two environment variables (read fresh per call):
- REGENOLD_GRAPH_VECTOR_RECALL: If "1", activates the recall path. Default OFF.
- REGENOLD_VECTOR_MIN_SIM: The similarity floor for candidates. Default "0.35".
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


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


def recall_articles(question: str, *, top_k: int = 3) -> list[str]:
    """Return up to `top_k` unique article refs matching the question.

    Queries the local sentence-level embeddings index and collapses
    the hits to unique article references by taking the maximum
    similarity score per article.

    Returns `[]` on every error path (route-safe). Filters hits by the
    `REGENOLD_VECTOR_MIN_SIM` threshold and verifies the article exists
    in `ARTICLE_EXISTENCE`.
    """
    if not is_enabled():
        return []

    try:
        from app.engines import embeddings_index
        from app.data import article_existence
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
        hits = embeddings_index.query(question, top_k=50, threshold=min_sim)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: embeddings_index.query failed: %s", exc)
        return []

    try:
        article_scores = {}
        for hit in hits:
            ref = hit.article_ref
            if ref not in article_scores:
                article_scores[ref] = hit.similarity
            else:
                article_scores[ref] = max(article_scores[ref], hit.similarity)

        sorted_refs = sorted(article_scores.keys(), key=lambda r: article_scores[r], reverse=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: failed to process hits: %s", exc)
        return []

    try:
        valid_refs = set(article_existence.ARTICLE_EXISTENCE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_recall: failed to access ARTICLE_EXISTENCE: %s", exc)
        return []

    results = []
    for ref in sorted_refs:
        if ref in valid_refs:
            results.append(ref)
            if len(results) >= top_k:
                break

    return results

__all__ = [
    "is_enabled",
    "recall_articles",
]
