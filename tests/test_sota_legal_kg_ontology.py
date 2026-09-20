"""Unit tests for SOTA Legal Knowledge Graph, Ontologies, and Semantic Layer enhancements.

Validates:
1. Dotted statutory sub-point recognition in _surface_prose_subpoints (Article 13.3.a, Annex IV.1.e).
2. Ontology-guided citable base expansion (cross-references, role obligations, GPAI systemic risk).
3. Shadow Article node bridging in _DEONTIC_CYPHER.
"""

from __future__ import annotations

import os
from app.routes.regenold import (
    _surface_prose_subpoints,
    _expand_citable_bases_with_ontology,
    _ontology_citable_expansion_enabled,
)
from app.engines.kg_context import _DEONTIC_CYPHER


def test_dotted_prose_subpoint_surfaced():
    """Verify that when Stage-2 prose cites a dotted coordinate (Article 13.3.a),
    it is properly surfaced into references alongside the parent."""
    answer = (
        "Under Article 13.3.a, providers must ensure transparency instructions "
        "include the identity and contact details of the provider."
    )
    refs = ["Article 13"]
    out = _surface_prose_subpoints(answer, refs)
    assert "Article 13.3.a" in out
    assert out.index("Article 13.3.a") == out.index("Article 13") + 1


def test_annex_dotted_subpoint_surfaced():
    """Verify that dotted Annex subpoints (e.g. Annex IV.1.e) are surfaced."""
    answer = "The technical documentation requires Annex IV.1.e hardware descriptions."
    refs = ["Annex IV"]
    out = _surface_prose_subpoints(answer, refs)
    assert "Annex IV.1.e" in out


def test_nonexistent_dotted_subpoint_not_surfaced():
    """Verify that invalid/hallucinated dotted subpoints are rejected by coordinate_exists."""
    answer = "Under Article 999.1.z, imaginary rules apply."
    refs = ["Article 999"]
    out = _surface_prose_subpoints(answer, refs)
    assert "Article 999.1.z" not in out


def test_ontology_citable_expansion_xrefs():
    """Verify that 1-hop cross-references from kb_xrefs expand the citable universe."""
    bases = frozenset({"Article 51"})
    expanded = _expand_citable_bases_with_ontology(bases, question="GPAI requirements")
    # Annex XIII is a direct cross-reference of Article 51 in the EU AI Act
    assert "Annex XIII" in expanded
    assert "Article 53" in expanded


def test_ontology_citable_expansion_role_obligations():
    """Verify that operator role obligations are included when the question mentions a role."""
    bases = frozenset({"Article 51"})
    # Question asks about deployer duties (e.g. rg_090)
    expanded = _expand_citable_bases_with_ontology(
        bases,
        question="As a deployer, do I need to keep logs if I use a powerful LLM?",
    )
    assert "Article 26" in expanded


def test_deontic_cypher_includes_shadow_bridge():
    """Verify that _DEONTIC_CYPHER includes the bridge to ART<N> shadow nodes."""
    assert "a.id STARTS WITH 'ART'" in _DEONTIC_CYPHER
    assert "('article_' + substring(a.id, 3)) IN $ids" in _DEONTIC_CYPHER
