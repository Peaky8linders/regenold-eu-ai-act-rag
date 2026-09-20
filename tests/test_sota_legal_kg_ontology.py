"""Unit tests for the SOTA Legal Knowledge Graph / ontology enhancements (R426).

Covers:
1. Dotted statutory sub-point recognition in ``_surface_prose_subpoints``
   (``Article 13.3.a``, ``Annex IV.1.e``), including rejection of coordinates the
   Regulation does not have.
2. Ontology-guided citable base expansion — and, since R428, its DEFAULT.
3. The shadow-node bridge in ``_DEONTIC_CYPHER``, including the cite fallback.

R428 note on why the expansion cases set the flag EXPLICITLY: R426 shipped
``REGENOLD_ONTOLOGY_CITABLE_EXPANSION`` default ON, but its only consumer
(``REGENOLD_CITABLE_BASE_GUARD``) defaults OFF and the expansion's measured
effect in the state where it fires is 190 excess references to 1 gold one
(``docs/measurements/r428/ontology_expansion_probe.py``). The default is now OFF,
so a test that wants the expansion must ask for it — and the test that asserts
the default is OFF is here too, so the flip cannot be undone silently.

The cross-reference case is deliberately asked WITHOUT any GPAI keyword: the
function has a hardcoded GPAI list that also contains ``Article 53`` and
``Annex XIII``, so asking a GPAI question made the original test pass whether or
not the cross-reference graph worked at all.
"""
from __future__ import annotations

from pathlib import Path

from app.engines.kg_context import _DEONTIC_CYPHER
from app.routes.regenold import (
    _expand_citable_bases_with_ontology,
    _ground_wire_subpoints,
    _ontology_citable_expansion_enabled,
    _surface_prose_subpoints,
)

REPO = Path(__file__).resolve().parents[1]


# ── 1. dotted statutory sub-points ──────────────────────────────────────────
#
# R426 mined the dotted prose form (``Article 6.3``) in TWO places. Only the
# count-neutral one survives R428. Replaying 630 recorded hard draws through the
# real passes and the real official rubric (``docs/measurements/r428/
# dotted_subpoint_probe.py``): the ADD in ``_surface_prose_subpoints`` contributed
# 13 references of which 11 were excess, moved Ref. Strict / Ref. Loose on **0
# rows**, and cost Ref. Conciseness. The dotted form is still mined by
# ``_prose_named_subpoints`` → ``_ground_wire_subpoints`` for the rewrite path,
# which is 1:1 and cannot change the count or the folded head set. These tests pin
# both halves.


def test_dotted_prose_reaches_the_count_neutral_rewrite():
    """The surviving owner: a wire LIMB the prose contradicts is rewritten 1:1."""
    answer = "The provider must comply at Article 6.3 for this category."
    out = _ground_wire_subpoints(answer, ["Article 6", "Article 6.2"])
    assert "Article 6.3" in out
    assert "Article 6.2" not in out, "the ungrounded sibling limb must not survive"
    assert len(out) == 2, "a rewrite is count-neutral"


def test_annex_dotted_prose_reaches_the_rewrite_too():
    answer = "The technical documentation requires Annex IV.1.e hardware descriptions."
    out = _ground_wire_subpoints(answer, ["Annex IV.2"])
    assert "Annex IV.1.e" in out, "a DIFFERENT limb of the same parent is a substitution"
    assert "Annex IV.2" not in out
    assert len(out) == 1
    # A shallower coordinate of the SAME limb is depth, not substitution: R425
    # deliberately keeps it, and R428 does not change that.
    assert _ground_wire_subpoints(answer, ["Annex IV.1"]) == ["Annex IV.1"]


def test_dotted_prose_is_not_surfaced_by_the_additive_pass():
    """R428 — the measured-null ADD stays removed.

    The additive pass must not grow the wire from a dotted mention: that is the
    additive form the probe found to be 0 on both correctness axes and negative on
    Ref. Conciseness. Note this is scoped to the DOTTED form — the parenthesised
    form still takes the R133 route (asserted below so the distinction is pinned).
    """
    dotted = "Requires Annex IV.1.e hardware descriptions."
    assert _surface_prose_subpoints(dotted, ["Annex IV"]) == ["Annex IV"]
    # The parenthesised form is R133's, untouched by R428.
    parenthesised = "Requires Annex IV point 1(e), per the documentation duty."
    assert _surface_prose_subpoints(parenthesised, ["Annex IV"]) != ["Annex IV"]


def test_nonexistent_dotted_subpoint_not_minted_on_the_wire():
    """A coordinate the Regulation lacks is never minted onto the wire."""
    refs = ["Article 999", "Article 999.1"]
    assert _ground_wire_subpoints(
        "Under Article 999.1.z, imaginary rules apply.", refs
    ) == refs
    assert _surface_prose_subpoints(
        "Under Article 999.1.z, imaginary rules apply.", ["Article 999"]
    ) == ["Article 999"]


# ── 2. ontology citable base expansion ──────────────────────────────────────


def test_ontology_citable_expansion_is_default_off(monkeypatch):
    """R428 — the shipped default, pinned so a flip has to be deliberate.

    Its only consumer is ``REGENOLD_CITABLE_BASE_GUARD`` (default OFF, rejected
    on a full live A/B in R401), so at default settings the expansion could only
    be computed and discarded.
    """
    monkeypatch.delenv("REGENOLD_ONTOLOGY_CITABLE_EXPANSION", raising=False)
    assert _ontology_citable_expansion_enabled() is False
    monkeypatch.setenv("REGENOLD_ONTOLOGY_CITABLE_EXPANSION", "1")
    assert _ontology_citable_expansion_enabled() is True


def test_disabled_expansion_passes_the_bases_through_unchanged(monkeypatch):
    monkeypatch.setenv("REGENOLD_ONTOLOGY_CITABLE_EXPANSION", "0")
    bases = frozenset({"Article 51", "Annex XI"})
    assert _expand_citable_bases_with_ontology(bases, question="GPAI") == bases


def test_ontology_citable_expansion_xrefs(monkeypatch):
    """1-hop cross-references, asked WITHOUT the GPAI keyword.

    ``Article 53`` and ``Annex XIII`` are genuine cross-references of
    ``Article 51`` — but they are ALSO in the function's hardcoded GPAI list, so
    a GPAI question cannot tell the two paths apart. With a neutral question only
    the cross-reference graph can supply them.
    """
    monkeypatch.setenv("REGENOLD_ONTOLOGY_CITABLE_EXPANSION", "1")
    expanded = _expand_citable_bases_with_ontology(
        frozenset({"Article 51"}), question="what does article 51 require"
    )
    assert "Article 53" in expanded, "the xref graph must supply Article 53"
    assert "Annex XIII" in expanded, "the xref graph must supply Annex XIII"
    # ``Article 52`` is a genuine REVERSE cross-reference of ``Article 51``
    # (Article 52 itself cites Article 51), so it cannot discriminate the two
    # paths — the original assertion that it must be absent was unsound. These
    # four are in the hardcoded GPAI list and are NOT 1-hop neighbours of
    # Article 51 in the cross-reference graph, so they are the discriminating
    # set: the GPAI branch is the only way any of them can appear.
    gpai_only = {"Article 54", "Article 55", "Annex XI", "Annex XII"}
    assert gpai_only.isdisjoint(expanded), (
        "the hardcoded GPAI list must NOT fire on a question without GPAI keywords"
    )


def test_ontology_citable_expansion_gpai_list_is_keyword_gated(monkeypatch):
    monkeypatch.setenv("REGENOLD_ONTOLOGY_CITABLE_EXPANSION", "1")
    expanded = _expand_citable_bases_with_ontology(
        frozenset({"Article 51"}), question="GPAI requirements"
    )
    for ref in ("Article 52", "Article 54", "Annex XI", "Annex XII"):
        assert ref in expanded


def test_ontology_citable_expansion_role_obligations(monkeypatch):
    monkeypatch.setenv("REGENOLD_ONTOLOGY_CITABLE_EXPANSION", "1")
    expanded = _expand_citable_bases_with_ontology(
        frozenset({"Article 51"}),
        question="As a deployer, do I need to keep logs if I use a powerful LLM?",
    )
    assert "Article 26" in expanded


# ── 3. the shadow-node bridge ───────────────────────────────────────────────


def test_deontic_cypher_includes_shadow_bridge():
    """The bridge admits legacy ``ART<N>`` nodes for the same canonical id."""
    assert "a.id STARTS WITH 'ART'" in _DEONTIC_CYPHER
    assert "('article_' + substring(a.id, 3)) IN $ids" in _DEONTIC_CYPHER


def test_deontic_cypher_cite_branches_on_the_node_family():
    """R428 — the cite fallback may not apply the SHADOW transform to canonical ids.

    ``substring('article_6', 3)`` is ``'icle_6'``, so the unconditional form
    rendered **"Article icle_6"** into the Stage-2 context for any matched node
    lacking ``strict_citation``. The query cannot run offline, so this is a
    source-shape assertion: it pins the branch, and pins that the unconditional
    transform is gone.
    """
    assert "CASE WHEN a.id STARTS WITH 'ART'" in _DEONTIC_CYPHER
    assert "coalesce(a.strict_citation, 'Article ' + substring(a.id, 3))" not in _DEONTIC_CYPHER
    # Canonical ids still fall back to the value they always did.
    assert "ELSE a.id END" in _DEONTIC_CYPHER


def test_deontic_widening_cannot_duplicate_a_cite():
    """R428 — why the widened MATCH is safe, measured rather than assumed.

    Admitting shadow nodes makes TWO nodes eligible for one canonical id. They do
    not produce two rows in the result: the projection collects into aggregates
    keyed on ``cite``, so rows sharing a cite merge. Verified live on Aura for the
    10 ids whose shadows exist — unwidened 10 rows, widened 10 rows, zero rows
    differing. This test pins the property that makes that true, so a future edit
    that drops the aggregation cannot silently double the context.
    """
    assert _DEONTIC_CYPHER.count("collect(") >= 4, "the per-cite aggregation is what merges the twins"
    assert "RETURN cite, practices, annex_iii, roles, phases" in _DEONTIC_CYPHER


def test_shadow_bridge_arc_follows_the_article_to_role_direction():
    """R428 — the bridge's ``APPLIES_TO_ROLE`` clause had the arc REVERSED.

    Measured on Aura: all 23 existing edges are outgoing
    ``(Article)-[:APPLIES_TO_ROLE]->(OperatorRole)`` and the incoming count is 0, so
    the old clause matched nothing and would have written an unused arc had it ever
    matched. ``app/graph/ontology.py`` declares the same direction; the schema
    constant's comment used to disagree and is corrected, which this pins.
    """
    seeder = (REPO / "scripts" / "seed_neo4j_kb.py").read_text(encoding="utf-8")
    assert "OPTIONAL MATCH (shadow)-[atr:APPLIES_TO_ROLE]->(role)" in seeder
    assert "MERGE (canonical)-[:APPLIES_TO_ROLE]->(role)" in seeder
    assert "(role)-[atr:APPLIES_TO_ROLE]->(shadow)" not in seeder
    assert "MERGE (role)-[:APPLIES_TO_ROLE]->(canonical)" not in seeder

    from app.graph import ontology as onto
    from app.graph import schema as sch

    assert sch.REL_APPLIES_TO_ROLE == onto.EdgeType.applies_to_role
    schema_src = (REPO / "app" / "graph" / "schema.py").read_text(encoding="utf-8")
    assert "Article → OperatorRole" in schema_src
    assert "# OperatorRole → canonical Article" not in schema_src


def test_legacy_requires_edges_are_still_not_mirrored():
    """The 125 legacy ``REQUIRES`` edges must not be propagated (R427.1, R428).

    ``app/graph/schema.py`` states the type is deliberately unseeded and that any
    consumer matching it is the R99.1 zero-retrieval drift bug. R426's bridge
    mirrored it onto the nodes production reads; it stays removed even though the
    edges exist on the shadows, because no live query reads ``REQUIRES`` and
    re-propagating it is the exact drift the schema note forbids.
    """
    seeder = (REPO / "scripts" / "seed_neo4j_kb.py").read_text(encoding="utf-8")
    assert "MERGE (canonical)-[:REQUIRES]->" not in seeder
    from app.graph.schema import SEEDED_REL_TYPES

    assert "REQUIRES" not in SEEDED_REL_TYPES
    assert "REQUIRES" not in _DEONTIC_CYPHER
