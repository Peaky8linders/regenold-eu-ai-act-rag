"""PathRAG relational-path retrieval + pruning (R39 / B7).

PathRAG (arXiv 2502.14902) retrieves SPECIFIC paths between query-
anchored entities rather than all 1- and 2-hop neighbours, then prunes
redundant overlapping paths via edge-set Jaccard similarity. Targets
the R31.1 ref-conciseness regression (over-citation cost when scenarios
auto-expand to 10 refs).

Fail-soft: flag off / Neo4j down / GDS missing / timeout / exception
-> return [].
"""
from __future__ import annotations

import logging
import os
import re

from app.data.article_existence import ARTICLE_EXISTENCE
from app.graph.client import get_graph_client

logger = logging.getLogger(__name__)

_FLAG_VAR = "REGENOLD_PATH_RAG"
_TIMEOUT_MS = 50

Path = list[tuple[str, str]]


def is_pathrag_available() -> bool:
    return os.getenv(_FLAG_VAR, "0") in ("1", "true", "yes", "on")


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def prune_redundant_paths(
    paths: list[Path],
    jaccard_threshold: float = 0.8,
) -> list[Path]:
    """Drop paths whose edge set is >= `jaccard_threshold` similar to a
    surviving path.
    """
    out: list[Path] = []
    seen_edgesets: list[set[tuple[str, str]]] = []
    for path in paths:
        edges = set(path)
        if any(_jaccard(edges, prev) >= jaccard_threshold for prev in seen_edgesets):
            continue
        out.append(path)
        seen_edgesets.append(edges)
    return out


_ART_NUM_RE = re.compile(r"Art(?:icle|\.)\s+(\d+)", re.I)

# R39 eng-review F2: the previous Cypher used `nodes(r)` on a
# *relationship list* from a variable-length pattern, which is a type
# error in Cypher (`nodes()` requires a Path). Bind a path variable
# `p` and call `nodes(p)` instead. Also: seeder stores `Article.number`
# as STRING, so the parameter must be `list[str]` (eng-review F1).
_PATHS_CYPHER = """
MATCH p = (a:Article)-[r:CROSS_REFERENCES*1..2]-(b:Article)
WHERE a.number IN $seed_nums AND b.number IS NOT NULL
  AND a.number <> b.number
RETURN
  a.number AS src,
  [n IN nodes(p) | n.number] AS path_nodes,
  length(p) AS hops
ORDER BY hops, b.number LIMIT $cap
"""


def pathrag_candidates(
    seed_articles: list[str],
    top_k: int = 10,
) -> list[str]:
    """Return article refs reachable via curated cross-reference paths.

    Returns `[]` on any non-happy path.
    """
    if not is_pathrag_available():
        return []
    # R39 eng-review F1: keep numbers as STRINGS — Article.number is
    # stored as string in Neo4j by the seeder, so int comparison fails.
    seed_nums: list[str] = []
    for s in seed_articles or []:
        m = _ART_NUM_RE.search(s)
        if m:
            num_str = m.group(1)
            if num_str and num_str not in seed_nums:
                seed_nums.append(num_str)
    if not seed_nums:
        return []
    client = get_graph_client()
    if not getattr(client, "enabled", False):
        return []
    try:
        rows = client.execute_read(
            _PATHS_CYPHER,
            {"seed_nums": seed_nums, "cap": top_k * 3},  # over-fetch, prune
        )
    except Exception as exc:  # noqa: BLE001 - fail-soft
        logger.debug("path_rag_exception: %s", str(exc)[:200])
        return []
    # Build path edge sets
    paths: list[Path] = []
    for row in rows or []:
        nodes = row.get("path_nodes") or []
        if len(nodes) < 2:
            continue
        edges: Path = [
            (f"Art. {a}", f"Art. {b}")
            for a, b in zip(nodes, nodes[1:], strict=False)
        ]
        paths.append(edges)
    paths = prune_redundant_paths(paths, jaccard_threshold=0.8)
    # Flatten to dedup candidate refs (target of each path)
    out: list[str] = []
    for path in paths[:top_k]:
        if path:
            tgt = path[-1][1]
            if tgt in ARTICLE_EXISTENCE and tgt not in out:
                out.append(tgt)
    return out
