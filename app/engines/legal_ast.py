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

    queries: list[tuple[str, dict]] = []

    from app.data.official_eu_ai_act import OFFICIAL_ARTICLE_TEXT
    from app.data.provision_text import (
        article_body,
        _paragraphs,
        _subpoints,
        _annex_items,
        _definitions,
    )

    logger.info(f"Seeding full Legal AST for {len(OFFICIAL_ARTICLE_TEXT)} top-level provisions...")

    for key in OFFICIAL_ARTICLE_TEXT.keys():
        body = article_body(key)
        if not body:
            continue
            
        if key.startswith("Article "):
            # e.g. "Article 6"
            n_str = key[len("Article "):].strip()
            if not n_str.isdigit():
                continue
            n = int(n_str)
            article_id = f"article_{n}"
            
            # Merge Article node
            queries.append((
                "MERGE (a:Article {id: $id})",
                {"id": article_id}
            ))

            if n == 3:
                units = _definitions(body)
            else:
                units = _paragraphs(body)
                
            # If no paragraphs, it's a single-block article, but we might still have subpoints 
            # (e.g. Article 16 (a)...(n) without a paragraph 1).
            # We'll map those as points under a virtual paragraph '1' or just as points on the article.
            # But according to standard formatting, most have paragraphs. Let's handle the common case.
            if not units:
                subs = _subpoints(body)
                if subs:
                    # Treat the main body as Paragraph 1
                    para_id = f"{article_id}_1"
                    queries.append((
                        """
                        MERGE (p:Paragraph {id: $id})
                        SET p.number = '1', p.text = $text
                        WITH p
                        MATCH (a:Article {id: $article_id})
                        MERGE (a)-[:HAS_PARAGRAPH]->(p)
                        """,
                        {"id": para_id, "text": body, "article_id": article_id}
                    ))
                    for letter, sub_text in subs.items():
                        point_id = f"{para_id}_{letter}"
                        queries.append((
                            """
                            MERGE (pt:Point {id: $id})
                            SET pt.letter = $letter, pt.text = $text
                            WITH pt
                            MATCH (p:Paragraph {id: $para_id})
                            MERGE (p)-[:HAS_POINT]->(pt)
                            """,
                            {"id": point_id, "letter": letter, "text": sub_text, "para_id": para_id}
                        ))
                continue

            for m, p_text in units.items():
                para_id = f"{article_id}_{m}"
                queries.append((
                    """
                    MERGE (p:Paragraph {id: $id})
                    SET p.number = $num, p.text = $text
                    WITH p
                    MATCH (a:Article {id: $article_id})
                    MERGE (a)-[:HAS_PARAGRAPH]->(p)
                    """,
                    {"id": para_id, "num": str(m), "text": p_text, "article_id": article_id}
                ))

                # Check for points
                points = _subpoints(p_text)
                for letter, sub_text in points.items():
                    point_id = f"{para_id}_{letter}"
                    queries.append((
                        """
                        MERGE (pt:Point {id: $id})
                        SET pt.letter = $letter, pt.text = $text
                        WITH pt
                        MATCH (p:Paragraph {id: $para_id})
                        MERGE (p)-[:HAS_POINT]->(pt)
                        """,
                        {"id": point_id, "letter": letter, "text": sub_text, "para_id": para_id}
                    ))

        elif key.startswith("Annex "):
            roman = key[len("Annex "):].strip()
            # Match the seeder convention (scripts/seed_neo4j_kb.py::_article_id):
            # ``Annex III`` -> ``:Annex {id: 'annex_III'}`` (UPPERCASE roman).
            # legal_ast previously created ``:Article {id: 'annex_iii'}`` — a
            # mislabeled, case-mismatched duplicate orphaned from the seeded
            # :Annex node + the ontology FALLS_UNDER edges. Use the same label
            # and id so paragraphs/points attach to the seeded annex node.
            annex_id = f"annex_{roman.upper()}"

            queries.append((
                "MERGE (a:Annex {id: $id})",
                {"id": annex_id}
            ))

            items = _annex_items(body)
            if not items:
                # E.g. Annex III has lists like (a)... but under a single unnumbered paragraph.
                subs = _subpoints(body)
                if subs:
                    # Treat the main body as Paragraph 1
                    para_id = f"{annex_id}_1"
                    queries.append((
                        """
                        MERGE (p:Paragraph {id: $id})
                        SET p.number = '1', p.text = $text
                        WITH p
                        MATCH (a:Annex {id: $article_id})
                        MERGE (a)-[:HAS_PARAGRAPH]->(p)
                        """,
                        {"id": para_id, "text": body, "article_id": annex_id}
                    ))
                    for letter, sub_text in subs.items():
                        point_id = f"{para_id}_{letter}"
                        queries.append((
                            """
                            MERGE (pt:Point {id: $id})
                            SET pt.letter = $letter, pt.text = $text
                            WITH pt
                            MATCH (p:Paragraph {id: $para_id})
                            MERGE (p)-[:HAS_POINT]->(pt)
                            """,
                            {"id": point_id, "letter": letter, "text": sub_text, "para_id": para_id}
                        ))
                continue

            for m, item_text in items.items():
                para_id = f"{annex_id}_{m}"
                queries.append((
                    """
                    MERGE (p:Paragraph {id: $id})
                    SET p.number = $num, p.text = $text
                    WITH p
                    MATCH (a:Annex {id: $article_id})
                    MERGE (a)-[:HAS_PARAGRAPH]->(p)
                    """,
                    {"id": para_id, "num": str(m), "text": item_text, "article_id": annex_id}
                ))

                points = _subpoints(item_text)
                for letter, sub_text in points.items():
                    point_id = f"{para_id}_{letter}"
                    queries.append((
                        """
                        MERGE (pt:Point {id: $id})
                        SET pt.letter = $letter, pt.text = $text
                        WITH pt
                        MATCH (p:Paragraph {id: $para_id})
                        MERGE (p)-[:HAS_POINT]->(pt)
                        """,
                        {"id": point_id, "letter": letter, "text": sub_text, "para_id": para_id}
                    ))

    # Send batches to Neo4j to avoid huge transaction
    batch_size = 500
    for i in range(0, len(queries), batch_size):
        client.execute_write_batch(queries[i:i+batch_size])
        
    logger.info(f"Successfully ingested {len(queries)} Legal AST nodes into Neo4j graph.")

