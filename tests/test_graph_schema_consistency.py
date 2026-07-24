"""R121 — pin the KB graph schema to a single source of truth (app/graph/schema.py).

These tests make the R99.1 drift class (a read query / schema-init asserting a
``REQUIRES`` edge the seeder never creates → empty graph → wire zero-retrieval
floor) structurally impossible: they parse the seeder's ACTUAL ``MERGE`` Cypher
(ground truth) and fail if it diverges from ``app/graph/schema.py``, and they
forbid the phantom ``REQUIRES`` from re-appearing in the read queries or the
schema initializer.

No Neo4j / neo4j-driver import is needed — the seeder + initializer are read
as source text, and only the pure-stdlib ``schema`` + pydantic ``ontology`` +
data ``graph_rag_prompts`` modules are imported.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.graph.schema import (
    ARTICLE_OBLIGATION_EDGE,
    SEEDED_NODE_LABELS,
    SEEDED_REL_TYPES,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEEDER = _REPO_ROOT / "scripts" / "seed_neo4j_kb.py"
# R291 — the Paragraph/Point/SubPoint hierarchy MERGEs live in the shared
# single-source writer, not inline in the seeder, so the schema scan must
# cover both writer surfaces.
_HIERARCHY = _REPO_ROOT / "app" / "data" / "provision_hierarchy.py"
_SCHEMA_INIT = _REPO_ROOT / "app" / "graph" / "schema_initializer.py"

# Matches a relationship type inside a Cypher edge pattern:
#   ``-[:HAS_OBLIGATION]->``  /  ``-[r:CROSS_REFERENCES]->``
_EDGE_RE = re.compile(r"-\[[^\]]*:([A-Z_]+)\][^\]]*->")
# Matches a node-creation MERGE label: ``MERGE (a:Article {`` (NOT edge MERGEs,
# which are ``MERGE (a)-[...``, nor MATCH endpoints).
_NODE_MERGE_RE = re.compile(r"MERGE\s*\(\s*\w+\s*:\s*(\w+)\s*\{")


def _seeder_src() -> str:
    """The union of every module that MERGEs graph nodes/edges."""
    return (
        _SEEDER.read_text(encoding="utf-8")
        + "\n"
        + _HIERARCHY.read_text(encoding="utf-8")
    )


def test_seeder_edges_are_exactly_the_schema_rel_types() -> None:
    """Every edge the seeder MERGEs is declared in schema.py, and vice-versa."""
    found = set(_EDGE_RE.findall(_seeder_src()))
    assert found, "regex found no edges in the seeder — pattern drift, fix the test"
    missing_from_schema = found - SEEDED_REL_TYPES
    assert not missing_from_schema, (
        f"seeder MERGEs edges absent from app/graph/schema.py: "
        f"{sorted(missing_from_schema)} — add them to SEEDED_REL_TYPES"
    )
    never_seeded = SEEDED_REL_TYPES - found
    assert not never_seeded, (
        f"schema.py declares edges the seeder never creates: "
        f"{sorted(never_seeded)} — phantom edges are the R99.1 drift bug"
    )


def test_seeder_node_labels_are_exactly_the_schema_node_labels() -> None:
    found = set(_NODE_MERGE_RE.findall(_seeder_src()))
    assert found, "regex found no node labels in the seeder — pattern drift"
    assert found == SEEDED_NODE_LABELS, (
        "seeder node labels diverge from app/graph/schema.py: "
        f"seeder-only={sorted(found - SEEDED_NODE_LABELS)} "
        f"schema-only={sorted(SEEDED_NODE_LABELS - found)}"
    )


def test_obligations_read_query_uses_canonical_edge_not_phantom_requires() -> None:
    """The R99.1 root cause: the read query must match the seeded edge name."""
    from app.data.graph_rag_prompts import CYPHER_TEMPLATES

    q = CYPHER_TEMPLATES["obligations_for_article"]
    assert ARTICLE_OBLIGATION_EDGE in q, (
        f"obligations_for_article must match {ARTICLE_OBLIGATION_EDGE!r}; got: {q}"
    )
    assert ":REQUIRES]" not in q, (
        "the phantom REQUIRES edge is back in obligations_for_article — R99.1 redux"
    )


def test_schema_initializer_has_no_phantom_requires_and_derives_from_schema() -> None:
    src = _SCHEMA_INIT.read_text(encoding="utf-8")
    assert '"REQUIRES"' not in src and "'REQUIRES'" not in src, (
        "schema_initializer still asserts the phantom REQUIRES relationship"
    )
    # It must derive from the single source of truth, not hand-list edges.
    assert "SEEDED_REL_TYPES" in src
    assert "SEEDED_NODE_LABELS" in src


def test_edgetype_enum_reflects_the_real_seeded_kb_edges() -> None:
    from app.graph.ontology import EdgeType

    values = {member.value for member in EdgeType}
    for real_edge in (
        "HAS_OBLIGATION",
        "HAS_DEFINITION",
        "CROSS_REFERENCES",
        "HAS_RECITAL_ANCHOR",
        "TRIGGERS_HIGH_RISK_UNDER",
        "APPLIES_AT",
    ):
        assert real_edge in values, (
            f"EdgeType is missing the real seeded edge {real_edge!r}"
        )


def test_schema_internal_consistency() -> None:
    assert ARTICLE_OBLIGATION_EDGE == "HAS_OBLIGATION"
    assert ARTICLE_OBLIGATION_EDGE in SEEDED_REL_TYPES
    assert "REQUIRES" not in SEEDED_REL_TYPES
    # The two parent-CodexAI assessment edges are seeded but Regenold-unused.
    assert {"BELONGS_TO", "ASSESSES"} <= SEEDED_REL_TYPES
