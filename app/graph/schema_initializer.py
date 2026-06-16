#!/usr/bin/env python
"""Create required relationship types and node labels in Neo4j if they do not exist.

This script is idempotent – running it multiple times is safe. It uses the
APOC procedure `apoc.schema.assert` when available; otherwise it silently
ignores errors (e.g., when APOC is not installed).
"""
import os
from neo4j import GraphDatabase

from app.graph.schema import SEEDED_NODE_LABELS, SEEDED_REL_TYPES

def _driver() -> GraphDatabase.driver:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password))

def ensure_schema() -> None:
    # R121 — derive the asserted schema from the single source of truth
    # (app/graph/schema.py), which mirrors what scripts/seed_neo4j_kb.py
    # MERGEs. Pre-R121 this asserted a phantom ``REQUIRES`` relationship the
    # seeder never creates (the article→obligation edge is ``HAS_OBLIGATION``)
    # and omitted the 6 edges that ARE created — the same drift class that
    # caused the R99.1 production zero-retrieval bug.
    rels = sorted(SEEDED_REL_TYPES)
    labels = sorted(SEEDED_NODE_LABELS)
    with _driver() as driver:
        with driver.session() as session:
            for rel in rels:
                try:
                    session.run(
                        "CALL apoc.schema.assert({type: 'relationship', name: $rel}, {})",
                        {"rel": rel},
                    )
                except Exception:
                    # APOC not available or other error – ignore
                    pass
            for lbl in labels:
                try:
                    session.run(
                        "CALL apoc.schema.assert({type: 'node', name: $lbl}, {})",
                        {"lbl": lbl},
                    )
                except Exception:
                    pass
    print("Neo4j schema ensured.")

if __name__ == "__main__":
    ensure_schema()
