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


# =============================================================================
# R393 — closed-set member access for the Stage-2 evidence block.
#
# MEASURED motivation. ``provision_text.select_relevant_paragraphs`` is a
# lexical token-overlap ranker under a char budget, and its own docstring says
# "only WHICH sub-points are quoted is narrowed". So a question that asks what
# a provision REQUIRES is handed a PROPER SUBSET of a closed statutory set.
# Executed over the official 110-question batch at the live production budget
# (``_GROUNDING_REF_CHARS`` = 1200), counting the members of every provision
# the graded July-7 run cited:
#
#     closed-set member coverage delivered to Stage-2:  1340/3863 = 34.7%
#     86 of 110 questions receive under half the members they need
#
# No prompt instruction can recover a member that is not in the prompt, which
# is why R390 recorded the delivered coverage clause's closed-set rule as
# "demonstrably insufficient" and R391 measured the same family by hand
# (Annex IV 0/8, Article 17 4/13, Article 13 4/8).
#
# This accessor exposes the COMPLETE, ordered member list the hierarchy already
# computes, keyed by the wire coordinate the rubric scores against
# (``Article 13.3.a`` / ``Annex IV.1.e``), so the renderer can show the whole
# closed set cheaply instead of substituting whole provisions
# (``REGENOLD_FULL_PROVISION_EVIDENCE``, measured 3.93x the block).
#
# Pure and deterministic — no graph, no network. The Neo4j Paragraph/Point/
# SubPoint nodes are a MIRROR of this same payload (``hierarchy_merge_queries``
# writes them), so reading it locally is the same data without the driver, the
# latency or the failure mode.
# =============================================================================

_MEMBER_INDEX_CACHE: dict[str, list[tuple[str, str]]] | None = None


def _node_coordinate(node_id: str) -> str:
    """``article_13_3_a`` -> ``Article 13.3.a``; ``annex_IV_1_e`` -> ``Annex IV.1.e``.

    Emits the STRICT wire shape required by AGENTS.md invariant #1 —
    ``Article N(.subpoint)*`` / ``Annex X(.subpoint)*``, uppercase Roman for
    annexes — so a coordinate shown to the model is one it may legally cite.
    """
    parts = node_id.split("_")
    if not parts:
        return node_id
    kind = "Article" if parts[0] == "article" else "Annex"
    return f"{kind} {'.'.join(parts[1:])}"


def _build_member_index() -> dict[str, list[tuple[str, str]]]:
    """Map ``article_13`` / ``annex_IV`` -> ordered [(coordinate, text), ...].

    Document order, parents before their children, so the rendered skeleton
    reads as the statute reads.
    """
    payload = build_hierarchy_payload()
    by_parent: dict[str, list[dict]] = {}
    for node in payload.paragraph_nodes:
        by_parent.setdefault(str(node["id"]).rsplit("_", 1)[0], []).append(node)
    points_by_para: dict[str, list[dict]] = {}
    for node in payload.point_nodes:
        points_by_para.setdefault(str(node["id"]).rsplit("_", 1)[0], []).append(node)
    subs_by_point: dict[str, list[dict]] = {}
    for node in payload.subpoint_nodes:
        subs_by_point.setdefault(str(node["id"]).rsplit("_", 1)[0], []).append(node)

    def _key(node: dict) -> tuple:
        # Numeric paragraphs must sort 2 < 10, not "10" < "2".
        tail = str(node["id"]).rsplit("_", 1)[-1]
        return (0, int(tail)) if tail.isdigit() else (1, tail)

    index: dict[str, list[tuple[str, str]]] = {}
    for parent, paragraphs in by_parent.items():
        members: list[tuple[str, str]] = []
        for para in sorted(paragraphs, key=_key):
            pid = str(para["id"])
            members.append((_node_coordinate(pid), _flatten(para.get("text"))))
            for point in sorted(points_by_para.get(pid, []), key=_key):
                ptid = str(point["id"])
                members.append((_node_coordinate(ptid), _flatten(point.get("text"))))
                for sub in sorted(subs_by_point.get(ptid, []), key=_key):
                    members.append(
                        (_node_coordinate(str(sub["id"])), _flatten(sub.get("text")))
                    )
        index[parent] = members
    return index


def _flatten(text: object) -> str:
    return " ".join(str(text or "").split())


def _parent_id(ref: str) -> str | None:
    """``Article 13`` / ``Art. 13`` -> ``article_13``; ``Annex IV`` -> ``annex_IV``.

    Returns ``None`` for anything that is not a bare head — a ref that already
    carries a sub-coordinate is bounded, so it needs no closed-set expansion.

    ⚠ **R394 — accepts the INTERNAL short form, and that is load-bearing.**
    The route does not pass the long wire form: ``_context_article_refs``
    (``app/routes/regenold.py``) normalises every reference to ``Art. N``, and
    that is what reaches ``_render_grounding_text``. A matcher that only
    accepted ``Article N`` returned ``[]`` for every live call, so the R393
    closed-set skeleton rendered NOTHING in production while its unit tests
    passed — they built their own fixture using the long form — and its n=110
    live gate measured a no-op as though it were the lever.

    That is the sixth instance in this repo of a feature that reads correctly in
    the diff and makes zero calls (R329 rerank x3, R330 semantic layer, R366
    parent collapse). The lesson the earlier five did not teach: grepping the
    call site is not enough — assert on the DATA SHAPE the call site actually
    produces. ``tests/test_r393_closed_set_skeleton.py`` now drives
    ``_context_article_refs`` rather than hand-writing refs.
    """
    import re  # noqa: PLC0415 — module-local, keeps the hot import list lean

    stripped = ref.strip()
    if re.match(r"art\.?\s", stripped, re.IGNORECASE):
        stripped = "Article " + re.sub(r"^art\.?\s+", "", stripped, flags=re.IGNORECASE)
    m = re.fullmatch(r"Article\s+(\d{1,3})", stripped)
    if m:
        return f"article_{int(m.group(1))}"
    m = re.fullmatch(r"Annex\s+([IVXLCDM]+)", stripped, re.IGNORECASE)
    if m:
        return f"annex_{m.group(1).upper()}"
    return None


def closed_set_members(ref: str) -> list[tuple[str, str]]:
    """Every member of ``ref``'s closed statutory set, in document order.

    ``closed_set_members("Article 13")`` ->
    ``[("Article 13.1", "High-risk AI systems shall be designed ..."), ...,
       ("Article 13.3.a", "the identity and the contact details ..."), ...]``

    Returns ``[]`` for a ref that is not a bare Article/Annex head, that does
    not resolve, or that has no enumerated members (a single-block article is
    not a closed set and the shipped selector already renders it whole).
    """
    global _MEMBER_INDEX_CACHE  # noqa: PLW0603 — process-lifetime memo
    if _MEMBER_INDEX_CACHE is None:
        _MEMBER_INDEX_CACHE = _build_member_index()
    parent = _parent_id(ref)
    if parent is None:
        return []
    return list(_MEMBER_INDEX_CACHE.get(parent, ()))
