"""Single source of truth for the KB graph schema — node labels + edge types.

Before R121 the graph schema was declared in **four** places that could (and
did) drift apart:

* ``scripts/seed_neo4j_kb.py`` — the ``MERGE`` Cypher that actually writes the
  graph (the ground truth: what the nodes/edges are *named* in the store).
* ``app/graph/ontology.py::EdgeType`` / ``NodeType`` — the Pydantic enums.
* ``app/graph/schema_initializer.py`` — the ``apoc.schema.assert`` rel/label
  lists.
* ``app/data/graph_rag_prompts.py::CYPHER_TEMPLATES`` — the read queries.

The R99.1 production zero-retrieval bug was a direct consequence of that
drift: the ``obligations_for_article`` read query matched a ``REQUIRES`` edge
that the seeder never creates (it creates ``HAS_OBLIGATION``), so the query
silently returned ``[]`` on a healthy graph and the wire fell back to the
Art. 1/2 floor. ``schema_initializer.py`` *still* asserts that phantom
``REQUIRES`` relationship, and ``EdgeType.requires`` *still* carries the stale
value — neither is populated by the seeder.

This module is the **one** declaration of the schema. The consumers that can
import it (``ontology.py``, ``schema_initializer.py``) read their constants
from here; the seeder keeps its inline Cypher literals for readability but is
**pinned to this module by ``tests/test_graph_schema_consistency.py``** — a
mismatch fails CI instead of silently bypassing graph retrieval in production.

The values here mirror exactly what ``scripts/seed_neo4j_kb.py`` MERGEs.
Adding a node label or edge type to the seeder MUST add it here too (the
consistency test enforces the reverse direction).
"""

from __future__ import annotations

from typing import Final

# ── Node labels (exactly what the seeder MERGEs) ─────────────────────────────

NODE_ARTICLE: Final = "Article"
NODE_ANNEX: Final = "Annex"
NODE_RECITAL: Final = "Recital"
NODE_DEFINITION: Final = "Definition"
NODE_OBLIGATION: Final = "Obligation"
NODE_ANNEX_III_CATEGORY: Final = "AnnexIIICategory"
NODE_RISK_LEVEL: Final = "RiskLevel"
NODE_OPERATOR_ROLE: Final = "OperatorRole"
NODE_KB_METADATA: Final = "KBMetadata"
# Parent-CodexAI assessment schema (seeded but unused by the Regenold wire).
NODE_DIMENSION: Final = "Dimension"
NODE_QUESTION: Final = "Question"

#: Every node label the seeder writes. The single source of truth.
SEEDED_NODE_LABELS: Final[frozenset[str]] = frozenset(
    {
        NODE_ARTICLE,
        NODE_ANNEX,
        NODE_RECITAL,
        NODE_DEFINITION,
        NODE_OBLIGATION,
        NODE_ANNEX_III_CATEGORY,
        NODE_RISK_LEVEL,
        NODE_OPERATOR_ROLE,
        NODE_KB_METADATA,
        NODE_DIMENSION,
        NODE_QUESTION,
    }
)

# ── Edge / relationship types (exactly what the seeder MERGEs) ───────────────

#: Article → Obligation. THE drift-prone one (R99.1). The read query in
#: ``CYPHER_TEMPLATES["obligations_for_article"]`` and the seeder MUST agree on
#: this exact string. Historically a stale ``REQUIRES`` declaration disagreed.
REL_HAS_OBLIGATION: Final = "HAS_OBLIGATION"
REL_HAS_DEFINITION: Final = "HAS_DEFINITION"  # Article → Definition
REL_CROSS_REFERENCES: Final = "CROSS_REFERENCES"  # Article/Annex ↔ Article/Annex
REL_HAS_RECITAL_ANCHOR: Final = "HAS_RECITAL_ANCHOR"  # Article → Recital
REL_TRIGGERS_HIGH_RISK_UNDER: Final = "TRIGGERS_HIGH_RISK_UNDER"  # AnnexIIICategory → Article
REL_APPLIES_AT: Final = "APPLIES_AT"  # Obligation → RiskLevel
# Parent-CodexAI assessment schema (seeded but unused by the Regenold wire).
REL_BELONGS_TO: Final = "BELONGS_TO"  # Question → Dimension
REL_ASSESSES: Final = "ASSESSES"  # Question → Obligation

#: Every relationship type the seeder writes. The single source of truth.
#: NOTE: ``REQUIRES`` is deliberately ABSENT — the seeder never creates it
#: (the article→obligation edge is :data:`REL_HAS_OBLIGATION`). Any consumer
#: asserting / matching ``REQUIRES`` is the R99.1 drift bug.
SEEDED_REL_TYPES: Final[frozenset[str]] = frozenset(
    {
        REL_HAS_OBLIGATION,
        REL_HAS_DEFINITION,
        REL_CROSS_REFERENCES,
        REL_HAS_RECITAL_ANCHOR,
        REL_TRIGGERS_HIGH_RISK_UNDER,
        REL_APPLIES_AT,
        REL_BELONGS_TO,
        REL_ASSESSES,
    }
)

#: The canonical Article → Obligation edge name, named explicitly so read
#: queries and the seeder reference one symbol rather than a bare literal.
ARTICLE_OBLIGATION_EDGE: Final = REL_HAS_OBLIGATION
