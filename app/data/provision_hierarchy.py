"""Pure, nesting-aware, verbatim provision hierarchy for the Neo4j seed.

Builds the full EU AI Act structural tree — Article/Annex → Paragraph → Point
→ SubPoint — from the CLEAN, SHA-pinned official source
(:mod:`app.data.provision_text` over ``OFFICIAL_ARTICLE_TEXT`` +
``OFFICIAL_TEXT_PATCHES``), NOT the NBSP-laden Ansvar corpus and NOT the
fabricated ``euairagtest/provisions.json``.

Why this module exists (vs the ad-hoc parsing that lived in
``app.engines.legal_ast``):

* **One source of truth.** ``legal_ast.ingest_legal_ast`` and the Neo4j
  seeder's dry-run accounting now both consume :func:`build_hierarchy_payload`,
  so the payload the ``--dry-run`` prints is the payload the live seed writes
  (the R290 audit's G4 gap: dry-run previously under-counted by ~⅓ because the
  Paragraph/Point ingest ran only in the live branch).
* **Faithful sub-point NESTING.** The wire parser ``provision_text._subpoints``
  flattens a paragraph's ``(a)…(h)`` list into one dict, which mislabels the
  roman carve-outs ``(i)(ii)(iii)`` (Art. 5(1)(c)/(h), Art. 13(3)(b)) as
  top-level letters AND collides the romans of two different letters. This
  module uses :func:`provision_text.subpoints_nested`, so Art. 5(1)(h)(iii) is
  a ``:SubPoint`` under Point ``(h)`` — not a scrambled sibling.

Node id scheme (STABLE — the live 2-hop / Art 6(3) consumers key on these):

* Article  ``article_<N>``            e.g. ``article_6``
* Annex    ``annex_<ROMAN-UPPER>``    e.g. ``annex_III``
* Paragraph ``<parentId>_<M>``        e.g. ``article_6_3`` / ``annex_III_1``
* Point    ``<paraId>_<letter>``      e.g. ``article_6_3_a``
* SubPoint ``<pointId>_<roman>``      e.g. ``article_5_1_h_iii``  (NEW)

Edges: ``(:Article|:Annex)-[:HAS_PARAGRAPH]->(:Paragraph)-[:HAS_POINT]->
(:Point)-[:HAS_SUBPOINT]->(:SubPoint)``.

Pure — no I/O, no driver, no network. Suitable for tests and the offline
``--dry-run`` accounting pass.
"""
from __future__ import annotations

import dataclasses
from typing import Iterable

from app.data.official_eu_ai_act import OFFICIAL_ARTICLE_TEXT
from app.data.provision_text import (
    article_body,
    _paragraphs,
    _annex_items,
    _definitions,
    subpoints_nested,
)


def _annex_roman(key: str) -> str:
    """``Annex III`` → ``III`` (uppercased to match the seeder id convention)."""
    return key[len("Annex "):].strip().upper()


@dataclasses.dataclass(frozen=True)
class HierarchyPayload:
    """The full provision tree, grouped by node/edge kind.

    Every ``*_nodes`` row is a ``dict`` of the MERGE parameters; every
    ``*_edges`` row is ``{"source_id": ..., "target_id": ...}``.
    """

    paragraph_nodes: list[dict]
    point_nodes: list[dict]
    subpoint_nodes: list[dict]
    has_paragraph_edges: list[dict]
    has_point_edges: list[dict]
    has_subpoint_edges: list[dict]

    def counts(self) -> dict[str, int]:
        return {
            "Paragraph": len(self.paragraph_nodes),
            "Point": len(self.point_nodes),
            "SubPoint": len(self.subpoint_nodes),
            "HAS_PARAGRAPH": len(self.has_paragraph_edges),
            "HAS_POINT": len(self.has_point_edges),
            "HAS_SUBPOINT": len(self.has_subpoint_edges),
        }

    @property
    def total_nodes(self) -> int:
        return (
            len(self.paragraph_nodes)
            + len(self.point_nodes)
            + len(self.subpoint_nodes)
        )

    @property
    def total_edges(self) -> int:
        return (
            len(self.has_paragraph_edges)
            + len(self.has_point_edges)
            + len(self.has_subpoint_edges)
        )

    def iter_text_nodes(self) -> Iterable[tuple[str, str]]:
        """Yield ``(id, text)`` for every node carrying verbatim prose.

        Used by the seeder's embedding pass to vectorise the hierarchy.
        """
        for n in self.paragraph_nodes:
            yield n["id"], n["text"]
        for n in self.point_nodes:
            yield n["id"], n["text"]
        for n in self.subpoint_nodes:
            yield n["id"], n["text"]


def _emit_points(
    parent_para_id: str,
    para_text: str,
    point_nodes: list[dict],
    subpoint_nodes: list[dict],
    has_point_edges: list[dict],
    has_subpoint_edges: list[dict],
) -> None:
    """Parse ``para_text`` into nested Points/SubPoints under ``parent_para_id``."""
    for letter, node in subpoints_nested(para_text).items():
        point_id = f"{parent_para_id}_{letter}"
        # ``para_id`` is inert to the MERGE ($id/$letter/$text) but documents
        # parentage and is asserted by test_article_6_3_verbatim_coverage.
        point_nodes.append(
            {
                "id": point_id,
                "letter": letter,
                "text": node["text"],
                "para_id": parent_para_id,
            }
        )
        has_point_edges.append(
            {"source_id": parent_para_id, "target_id": point_id}
        )
        for roman, sub_text in node["subs"].items():
            sub_id = f"{point_id}_{roman}"
            subpoint_nodes.append(
                {
                    "id": sub_id,
                    "roman": roman,
                    "text": sub_text,
                    "point_id": point_id,
                }
            )
            has_subpoint_edges.append(
                {"source_id": point_id, "target_id": sub_id}
            )


def build_hierarchy_payload() -> HierarchyPayload:
    """Build the complete Article/Annex → Paragraph → Point → SubPoint tree."""
    paragraph_nodes: list[dict] = []
    point_nodes: list[dict] = []
    subpoint_nodes: list[dict] = []
    has_paragraph_edges: list[dict] = []
    has_point_edges: list[dict] = []
    has_subpoint_edges: list[dict] = []

    for key in OFFICIAL_ARTICLE_TEXT:
        body = article_body(key)
        if not body:
            continue

        if key.startswith("Article "):
            n_str = key[len("Article "):].strip()
            if not n_str.isdigit():
                continue
            parent_id = f"article_{int(n_str)}"
            # Art. 3 is a definition catalogue: one Paragraph per ``(N)`` def.
            if int(n_str) == 3:
                units = _definitions(body)
            else:
                units = _paragraphs(body)

            if not units:
                # Single-block article — no numbered paragraphs. Emit a
                # Paragraph "1" only when it carries a lettered list (e.g.
                # Art. 16 (a)…(n)); otherwise the full text lives on the
                # Article node (untruncated) and no Paragraph is created.
                sub_tree = subpoints_nested(body)
                if sub_tree:
                    para_id = f"{parent_id}_1"
                    paragraph_nodes.append(
                        {"id": para_id, "number": "1", "text": body}
                    )
                    has_paragraph_edges.append(
                        {"source_id": parent_id, "target_id": para_id}
                    )
                    _emit_points(
                        para_id, body, point_nodes, subpoint_nodes,
                        has_point_edges, has_subpoint_edges,
                    )
                continue

            for m, p_text in units.items():
                para_id = f"{parent_id}_{m}"
                paragraph_nodes.append(
                    {"id": para_id, "number": str(m), "text": p_text}
                )
                has_paragraph_edges.append(
                    {"source_id": parent_id, "target_id": para_id}
                )
                # Art. 3 definitions carry no lettered sub-list.
                if int(n_str) != 3:
                    _emit_points(
                        para_id, p_text, point_nodes, subpoint_nodes,
                        has_point_edges, has_subpoint_edges,
                    )

        elif key.startswith("Annex "):
            parent_id = f"annex_{_annex_roman(key)}"
            items = _annex_items(body)
            if not items:
                sub_tree = subpoints_nested(body)
                if sub_tree:
                    para_id = f"{parent_id}_1"
                    paragraph_nodes.append(
                        {"id": para_id, "number": "1", "text": body}
                    )
                    has_paragraph_edges.append(
                        {"source_id": parent_id, "target_id": para_id}
                    )
                    _emit_points(
                        para_id, body, point_nodes, subpoint_nodes,
                        has_point_edges, has_subpoint_edges,
                    )
                continue

            for m, item_text in items.items():
                para_id = f"{parent_id}_{m}"
                paragraph_nodes.append(
                    {"id": para_id, "number": str(m), "text": item_text}
                )
                has_paragraph_edges.append(
                    {"source_id": parent_id, "target_id": para_id}
                )
                _emit_points(
                    para_id, item_text, point_nodes, subpoint_nodes,
                    has_point_edges, has_subpoint_edges,
                )

    return HierarchyPayload(
        paragraph_nodes=paragraph_nodes,
        point_nodes=point_nodes,
        subpoint_nodes=subpoint_nodes,
        has_paragraph_edges=has_paragraph_edges,
        has_point_edges=has_point_edges,
        has_subpoint_edges=has_subpoint_edges,
    )


# ── Shared Cypher writer (used by legal_ast.ingest_legal_ast + the seeder) ──
#
# MERGE strings are pinned by ``tests/test_article_6_3_verbatim_coverage.py``
# and ``tests/test_ontology_leap_hardening.py`` — do not rename the labels or
# the ``$id`` parameter without updating those.

_MERGE_ROOT_ARTICLE = "MERGE (a:Article {id: $id})"
_MERGE_ROOT_ANNEX = "MERGE (a:Annex {id: $id})"
_MERGE_PARAGRAPH = """
MERGE (p:Paragraph {id: $id})
SET p.number = $number, p.text = $text
"""
_MERGE_POINT = """
MERGE (pt:Point {id: $id})
SET pt.letter = $letter, pt.text = $text
"""
_MERGE_SUBPOINT = """
MERGE (sp:SubPoint {id: $id})
SET sp.roman = $roman, sp.text = $text
"""
# Label-qualified per parent kind so the MATCH is index-backed and can never
# attach an annex paragraph to a mislabelled :Article node (the pre-R121 bug
# tests/test_ontology_leap_hardening guards against).
_MERGE_HAS_PARAGRAPH_ARTICLE = """
MATCH (a:Article {id: $source_id})
MATCH (p:Paragraph {id: $target_id})
MERGE (a)-[:HAS_PARAGRAPH]->(p)
"""
_MERGE_HAS_PARAGRAPH_ANNEX = """
MATCH (a:Annex {id: $source_id})
MATCH (p:Paragraph {id: $target_id})
MERGE (a)-[:HAS_PARAGRAPH]->(p)
"""
_MERGE_HAS_POINT = """
MATCH (p:Paragraph {id: $source_id})
MATCH (pt:Point {id: $target_id})
MERGE (p)-[:HAS_POINT]->(pt)
"""
_MERGE_HAS_SUBPOINT = """
MATCH (pt:Point {id: $source_id})
MATCH (sp:SubPoint {id: $target_id})
MERGE (pt)-[:HAS_SUBPOINT]->(sp)
"""


def hierarchy_merge_queries(
    payload: HierarchyPayload | None = None,
) -> list[tuple[str, dict]]:
    """Return the ordered ``(cypher, params)`` list that writes the tree.

    Nodes first (roots → paragraphs → points → subpoints) so the edge
    ``MATCH`` endpoints resolve within one batched transaction, then edges.
    Root Article/Annex nodes are MERGEd so the hierarchy attaches even when
    the base-seed nodes were written in a different transaction.
    """
    if payload is None:
        payload = build_hierarchy_payload()

    queries: list[tuple[str, dict]] = []

    # ── Root Article/Annex nodes (derive from the HAS_PARAGRAPH sources) ──
    roots: dict[str, str] = {}  # id -> "article" | "annex"
    for e in payload.has_paragraph_edges:
        sid = e["source_id"]
        roots.setdefault(sid, "annex" if sid.startswith("annex_") else "article")
    for root_id, kind in roots.items():
        cypher = _MERGE_ROOT_ANNEX if kind == "annex" else _MERGE_ROOT_ARTICLE
        queries.append((cypher, {"id": root_id}))

    # ── Nodes ──
    for n in payload.paragraph_nodes:
        queries.append((_MERGE_PARAGRAPH, n))
    for n in payload.point_nodes:
        queries.append((_MERGE_POINT, n))
    for n in payload.subpoint_nodes:
        queries.append((_MERGE_SUBPOINT, n))

    # ── Edges ──
    for e in payload.has_paragraph_edges:
        cypher = (
            _MERGE_HAS_PARAGRAPH_ANNEX
            if e["source_id"].startswith("annex_")
            else _MERGE_HAS_PARAGRAPH_ARTICLE
        )
        queries.append((cypher, e))
    for e in payload.has_point_edges:
        queries.append((_MERGE_HAS_POINT, e))
    for e in payload.has_subpoint_edges:
        queries.append((_MERGE_HAS_SUBPOINT, e))

    return queries
