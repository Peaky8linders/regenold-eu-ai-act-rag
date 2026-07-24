"""Legal Abstract Syntax Tree (AST) definitions and evaluator.

This module models legal conditions and exceptions explicitly.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class ASTNode:
    pass

@dataclass
class Condition(ASTNode):
    text: str
    condition_id: str

@dataclass
class LogicalAnd(ASTNode):
    operands: list[ASTNode]

@dataclass
class LogicalOr(ASTNode):
    operands: list[ASTNode]

@dataclass
class ExceptionClause(ASTNode):
    base_clause: ASTNode
    exception_condition: ASTNode

def evaluate_ast(node: ASTNode, scenario: dict[str, Any]) -> bool | None:
    """Evaluate AST against a scenario. Returns True, False, or None (Unknown)."""
    if isinstance(node, Condition):
        return scenario.get(node.condition_id, None)
    elif isinstance(node, LogicalAnd):
        results = [evaluate_ast(op, scenario) for op in node.operands]
        if False in results: return False
        if None in results: return None
        return True
    elif isinstance(node, LogicalOr):
        results = [evaluate_ast(op, scenario) for op in node.operands]
        if True in results: return True
        if None in results: return None
        return False
    elif isinstance(node, ExceptionClause):
        base_res = evaluate_ast(node.base_clause, scenario)
        exc_res = evaluate_ast(node.exception_condition, scenario)
        if base_res is False: return False
        if exc_res is True: return False
        if base_res is None or exc_res is None: return None
        return True
    return None

def parse_article_to_ast(article_ref: str, tree_nodes: list[Any] = None) -> ASTNode | None:
    """A heuristic parser that converts structured list of paragraphs to AST.
    
    In a fully realized system, this might use an LLM pre-processor to 
    map strings like 'Art. 5(1)(a)' to conditions. Here we provide a
    stubbed representation mapping explicit articles to their AST.
    """
    if "Art. 5" in article_ref:
        return LogicalOr([
            ExceptionClause(
                Condition("Subliminal manipulation", "subliminal"),
                Condition("Medical treatment exception", "medical_exception")
            ),
            Condition("Vulnerability exploitation", "vulnerability"),
            ExceptionClause(
                Condition("Real-time RBI in public", "real_time_rbi"),
                Condition("Law enforcement exception", "law_enforcement_rbi")
            )
        ])
    return None

def ingest_legal_ast(client=None) -> None:
    """Ingests the hierarchical Legal AST representation into Neo4j.

    Creates the Article -> Paragraph -> Point and Annex -> Paragraph -> Point
    hierarchy for the entire EU AI Act, establishing the rigid structural
    backbone needed for deterministic Cypher traversals and exact citations.

    ``client`` lets a caller (e.g. ``scripts/seed_neo4j_kb.py::run_seed``)
    reuse an already-open :class:`~app.graph.client.GraphClient` rather than
    the lazily-acquired singleton. Article/Annex nodes are MERGEd by the same
    ``id`` convention the seeder uses (``article_<n>`` / ``annex_<ROMAN>``)
    so the paragraphs/points attach to the seeded nodes instead of creating
    duplicates.
    """
    from app.graph.client import get_graph_client
    import logging
    logger = logging.getLogger(__name__)

    if client is None:
        client = get_graph_client()
    if not client.enabled:
        logger.warning("Graph client disabled; skipping Legal AST ingestion.")
        return

    from app.graph.client import get_graph_client
    import logging
    logger = logging.getLogger(__name__)

    if client is None:
        client = get_graph_client()
    if not client.enabled:
        logger.warning("Graph client disabled; skipping Legal AST ingestion.")
        return

    # R291 — one source of truth: the nesting-aware, verbatim, clean-source
    # hierarchy builder. This produces the SAME Article/Annex -> Paragraph ->
    # Point tree as before PLUS the correctly-nested :SubPoint layer for the
    # roman carve-outs (Art. 5(1)(c)/(h)(i)(ii)(iii), Art. 13(3)(b)) that the
    # old flat parser mislabelled and collided.
    from app.data.provision_hierarchy import (
        build_hierarchy_payload,
        hierarchy_merge_queries,
    )

    payload = build_hierarchy_payload()
    queries = hierarchy_merge_queries(payload)
    logger.info(
        "Seeding full Legal AST hierarchy: %d paragraphs, %d points, %d subpoints",
        len(payload.paragraph_nodes),
        len(payload.point_nodes),
        len(payload.subpoint_nodes),
    )

    # Send batches to Neo4j to avoid a huge transaction.
    batch_size = 500
    for i in range(0, len(queries), batch_size):
        client.execute_write_batch(queries[i:i + batch_size])

    logger.info("Successfully ingested %d Legal AST hierarchy queries into Neo4j.", len(queries))

