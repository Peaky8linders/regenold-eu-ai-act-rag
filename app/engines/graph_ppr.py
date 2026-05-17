"""Personalized PageRank over the Neo4j article graph (R39 / B6).

When `REGENOLD_GRAPH_PPR=1` and Neo4j+GDS are wired, surface additional
article candidates by Personalized PageRank seeded from query-anchored
articles. Replaces the R28 in-degree log-curve boost with a principled
PPR weight. Strictly additive — caller merges PPR candidates into the
BM25 pool, never displaces a BM25 winner.

Fail-soft: missing flag, Neo4j disabled, GDS plugin absent, query
timeout, any exception -> return [].
"""
from __future__ import annotations

import logging
import os
import re

from app.data.article_existence import ARTICLE_EXISTENCE
from app.graph.client import get_graph_client

logger = logging.getLogger(__name__)

_FLAG_VAR = "REGENOLD_GRAPH_PPR"
_TIMEOUT_MS = 50  # hard cap per /healthz/graph budget


def is_ppr_available() -> bool:
    return os.getenv(_FLAG_VAR, "0") in ("1", "true", "yes", "on")


_ART_NUM_RE = re.compile(r"Art(?:icle|\.)\s+(\d+)", re.I)


def _seed_nums(seed_articles: list[str]) -> list[int]:
    nums: list[int] = []
    for s in seed_articles or []:
        m = _ART_NUM_RE.search(s)
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                continue
    return nums


_PPR_CYPHER = """
MATCH (a:Article) WHERE a.number IN $seed_nums
WITH collect(id(a)) AS source_ids
CALL gds.pageRank.stream(
  'eu_ai_act_graph',
  { sourceNodes: source_ids, maxIterations: 20, dampingFactor: 0.85 }
)
YIELD nodeId, score
MATCH (n:Article) WHERE id(n) = nodeId AND n.number IS NOT NULL
  AND NOT n.number IN $seed_nums
RETURN n.number AS num, score
ORDER BY score DESC LIMIT $cap
"""


def ppr_candidates(
    seed_articles: list[str],
    top_k: int = 10,
) -> list[str]:
    """Return up to `top_k` additional Article refs ranked by PPR score.

    Returns `[]` on any non-happy path (flag off, Neo4j down, GDS
    missing, exception).
    """
    if not is_ppr_available():
        return []
    seed_nums = _seed_nums(seed_articles)
    if not seed_nums:
        return []
    client = get_graph_client()
    if not getattr(client, "enabled", False):
        return []
    try:
        rows = client.execute_read(
            _PPR_CYPHER,
            {"seed_nums": seed_nums, "cap": top_k},
        )
    except Exception as exc:  # noqa: BLE001 - fail-soft
        logger.debug("graph_ppr_exception: %s", str(exc)[:200])
        return []
    out: list[str] = []
    for row in rows or []:
        try:
            num = int(row["num"])
        except (KeyError, TypeError, ValueError):
            continue
        ref = f"Art. {num}"
        if ref in ARTICLE_EXISTENCE and ref not in out:
            out.append(ref)
            if len(out) >= top_k:
                break
    return out
