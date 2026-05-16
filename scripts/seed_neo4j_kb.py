"""Neo4j KB seeder for the Regenold EU AI Act RAG bundle.

Pushes the bundle's deterministic KB surface (articles, annexes, recitals,
definitions, obligations, Annex III categories, risk levels, operator
roles) and the cross-reference / classification edges that connect them
into a Neo4j graph. Designed for the optional Layer-1 graph path that
``app.graph.reasoning`` queries against — when the graph is empty the
engine silently falls back to its in-process KB; once seeded, the same
queries gain typed multi-hop reasoning.

The script is route-safe under any environment:

* No ``NEO4J_URI`` set → ``GraphClient.enabled`` is False and we either
  refuse to write (default) or stay in ``--dry-run`` mode (prints the
  Cypher payload counts and exits 0). Tests rely on the dry-run path
  always working offline.
* ``NEO4J_URI`` set but ``neo4j`` driver missing → same disabled path,
  same dry-run availability.
* ``NEO4J_URI`` + driver live → batched, idempotent ``MERGE``-based
  writes. Re-running is a no-op against the same KB ``KB_VERSION``.

CLI:

    py -3.12 -m scripts.seed_neo4j_kb --dry-run
    py -3.12 -m scripts.seed_neo4j_kb --neo4j-uri bolt://localhost:7687
    py -3.12 -m scripts.seed_neo4j_kb --clear --verbose

Pure stdlib + existing project imports. Never adds Cypher injection
vectors — every parameter goes through driver-side parameter binding.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.definitions import _DEFINITIONS
from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT, ARTICLE_TITLE, RECITALS
from app.data.kb import EC_CHECKER_OBLIGATION_MAP, KB_VERSION
from app.data.kb_xrefs import MANUAL_XREFS, _build_xref_graph
from app.data.ontology import ANNEX_III_REGISTRY
from app.data.role_obligations import ROLE_OBLIGATIONS

logger = logging.getLogger(__name__)


# ─── Seed pin ─────────────────────────────────────────────────────────────

#: Bumped on each material change to the seeded shape (added node label,
#: new edge type, removed source, etc.). Surfaces in the ``KBMetadata``
#: node so consumers can detect a graph that's stale relative to the
#: currently-running code.
SEED_VERSION = "2026-05-16-r35"

#: Cap on per-transaction batch size to stay well clear of the Neo4j
#: 4194304-byte default transaction limit. The shape of our payloads
#: (short string properties, no embedded blobs) means 500 rows is well
#: under any realistic cap.
BATCH_SIZE = 500


# ─── Risk levels (closed taxonomy used by the engine) ─────────────────────

RISK_LEVELS: tuple[dict[str, str], ...] = (
    {
        "id": "risk_prohibited",
        "label": "prohibited",
        "description": (
            "Art. 5 prohibited AI practices. No conformity-assessment path "
            "exists; placement on the market or putting into service is "
            "outright banned."
        ),
    },
    {
        "id": "risk_high",
        "label": "high-risk",
        "description": (
            "Annex I safety-component + Annex III use-case high-risk "
            "systems per Art. 6. Trigger Arts. 9-15 essential requirements, "
            "Art. 43 conformity assessment, Art. 47 EU declaration, Art. 49 "
            "database registration."
        ),
    },
    {
        "id": "risk_limited",
        "label": "limited",
        "description": (
            "Transparency-only obligations under Art. 50 (chatbots, "
            "deepfakes, biometric categorisation, emotion recognition where "
            "permitted, AI-generated content disclosure)."
        ),
    },
    {
        "id": "risk_minimal",
        "label": "minimal",
        "description": (
            "Out-of-scope systems carrying voluntary code-of-conduct "
            "obligations only (Art. 95). Art. 4 AI literacy still applies "
            "to providers / deployers."
        ),
    },
)


# ─── Helpers ─────────────────────────────────────────────────────────────


_ART_NUMBER_RE = re.compile(r"^Art\.\s*(\d{1,3})$")
_ANNEX_NUMBER_RE = re.compile(r"^Annex\s+([IVXLC]+)$", re.IGNORECASE)


def _slug_term(term: str) -> str:
    """Normalise an Art. 3 term into a deterministic ID slug."""
    s = term.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "anon"


def _article_id(ref: str) -> str:
    """Map ``"Art. 5"`` → ``"article_5"``, ``"Annex III"`` → ``"annex_III"``."""
    m = _ART_NUMBER_RE.match(ref)
    if m:
        return f"article_{m.group(1)}"
    m = _ANNEX_NUMBER_RE.match(ref)
    if m:
        return f"annex_{m.group(1).upper()}"
    # Defensive: pass through untouched so a bad caller crashes loud.
    return ref.replace(" ", "_").replace(".", "")


def _article_number(ref: str) -> str:
    """Return the bare number / roman from a reference."""
    m = _ART_NUMBER_RE.match(ref)
    if m:
        return m.group(1)
    m = _ANNEX_NUMBER_RE.match(ref)
    if m:
        return m.group(1).upper()
    return ref


def _is_annex(ref: str) -> bool:
    return bool(_ANNEX_NUMBER_RE.match(ref))


def _short_title(ref: str) -> str:
    """Pull a usable title for an article / annex."""
    title = ARTICLE_TITLE.get(ref)
    if title:
        # Strip the NBSP runs the corpus is dotted with so the property
        # stays readable in Neo4j Browser. Pure cleanup, no semantic change.
        return title.replace("\xa0", " ").strip()
    # Fall back to first sentence of the full text, capped.
    body = ARTICLE_FULL_TEXT.get(ref, "")
    if body:
        first = re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0]
        first = first.replace("\xa0", " ").strip()
        return first[:200]
    return ref


def _classify_risk_for_article(num: str) -> str | None:
    """Return the RiskLevel ID an obligation under article ``num`` applies at.

    Closed mapping per the brief: Art. 5 → prohibited, Arts. 6-49 (the
    high-risk obligation cluster) → high-risk, Art. 50 → limited, Art. 4
    → minimal. Outside that band we return ``None`` and skip the edge —
    silence beats over-claiming.
    """
    try:
        n = int(num)
    except (TypeError, ValueError):
        return None
    if n == 5:
        return "risk_prohibited"
    if n == 4:
        return "risk_minimal"
    if n == 50:
        return "risk_limited"
    if 6 <= n <= 49:
        return "risk_high"
    return None


# ─── Seed-payload builder (pure, side-effect-free) ────────────────────────


@dataclasses.dataclass(frozen=True)
class SeedPayload:
    """Everything we want to push, grouped by Cypher template.

    Each entry is ``(label/relType, list[dict] of parameters)``. The
    runner translates these into ``MERGE`` Cypher and batches the writes;
    the dry-run path counts them and returns.
    """

    article_nodes: list[dict]
    annex_nodes: list[dict]
    recital_nodes: list[dict]
    definition_nodes: list[dict]
    obligation_nodes: list[dict]
    annex_iii_nodes: list[dict]
    risk_level_nodes: list[dict]
    operator_role_nodes: list[dict]
    metadata_node: dict

    has_obligation_edges: list[dict]
    has_definition_edges: list[dict]
    cross_reference_edges: list[dict]
    has_recital_anchor_edges: list[dict]
    triggers_high_risk_edges: list[dict]
    applies_at_edges: list[dict]

    @property
    def total_nodes(self) -> int:
        return (
            len(self.article_nodes)
            + len(self.annex_nodes)
            + len(self.recital_nodes)
            + len(self.definition_nodes)
            + len(self.obligation_nodes)
            + len(self.annex_iii_nodes)
            + len(self.risk_level_nodes)
            + len(self.operator_role_nodes)
            + 1  # metadata
        )

    @property
    def total_edges(self) -> int:
        return (
            len(self.has_obligation_edges)
            + len(self.has_definition_edges)
            + len(self.cross_reference_edges)
            + len(self.has_recital_anchor_edges)
            + len(self.triggers_high_risk_edges)
            + len(self.applies_at_edges)
        )

    def counts(self) -> dict[str, int]:
        return {
            "Article": len(self.article_nodes),
            "Annex": len(self.annex_nodes),
            "Recital": len(self.recital_nodes),
            "Definition": len(self.definition_nodes),
            "Obligation": len(self.obligation_nodes),
            "AnnexIIICategory": len(self.annex_iii_nodes),
            "RiskLevel": len(self.risk_level_nodes),
            "OperatorRole": len(self.operator_role_nodes),
            "KBMetadata": 1,
            "HAS_OBLIGATION": len(self.has_obligation_edges),
            "HAS_DEFINITION": len(self.has_definition_edges),
            "CROSS_REFERENCES": len(self.cross_reference_edges),
            "HAS_RECITAL_ANCHOR": len(self.has_recital_anchor_edges),
            "TRIGGERS_HIGH_RISK_UNDER": len(self.triggers_high_risk_edges),
            "APPLIES_AT": len(self.applies_at_edges),
        }


def build_payload() -> SeedPayload:
    """Build the full seed payload from the in-process KB modules.

    Pure function — no I/O, no driver use. Suitable for tests and for the
    ``--dry-run`` accounting pass.
    """
    # ── Articles (113) ────────────────────────────────────────────────
    article_nodes: list[dict] = []
    for ref in sorted(
        (r for r in ARTICLE_EXISTENCE if r.startswith("Art. ")),
        key=lambda r: int(_article_number(r)),
    ):
        num = _article_number(ref)
        article_nodes.append(
            {
                "id": _article_id(ref),
                "number": num,
                "title": _short_title(ref),
                "description": ARTICLE_FULL_TEXT.get(ref, "")[:2000],
                "chapter": "",
                "vector_chunk_ids": [],
            }
        )

    # ── Annexes (13) ──────────────────────────────────────────────────
    annex_nodes: list[dict] = []
    for ref in sorted(r for r in ARTICLE_EXISTENCE if r.startswith("Annex ")):
        roman = _article_number(ref)
        annex_nodes.append(
            {
                "id": _article_id(ref),
                "number": roman,
                "title": _short_title(ref),
                "description": ARTICLE_FULL_TEXT.get(ref, "")[:2000],
            }
        )

    # ── Recitals (180) ────────────────────────────────────────────────
    recital_nodes: list[dict] = []
    for n in sorted(RECITALS.keys()):
        text = RECITALS[n].replace("\xa0", " ").strip()
        recital_nodes.append(
            {
                "id": f"recital_{n}",
                "number": str(n),
                "text": text[:3000],
            }
        )

    # ── Definitions (Art. 3 catalogue) ────────────────────────────────
    definition_nodes: list[dict] = []
    has_definition_edges: list[dict] = []
    for defn in _DEFINITIONS:
        slug = _slug_term(defn.term)
        def_id = f"def_{slug}"
        definition_nodes.append(
            {
                "id": def_id,
                "kind": "Definition",
                "term": defn.term,
                "citation": defn.citation,
                "text": defn.description,
            }
        )
        has_definition_edges.append(
            {
                "source_id": _article_id("Art. 3"),
                "target_id": def_id,
            }
        )

    # ── Obligations (one per KB stub row) ─────────────────────────────
    obligation_nodes: list[dict] = []
    has_obligation_edges: list[dict] = []
    applies_at_edges: list[dict] = []
    for ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        # Skip annex rows — those land as Annex nodes already and don't
        # carry an article-style obligation in the graph schema.
        if _is_annex(ref):
            continue
        if ref not in ARTICLE_EXISTENCE:
            # Defensive — the lint floor should already catch this.
            continue
        num = _article_number(ref)
        obl_id = f"obl_{num}"
        obligation_nodes.append(
            {
                "id": obl_id,
                "article_ref": num,
                "text": entry.get("summary", "")[:3000],
                "mandatory": True,
                "paragraph_ref": "",
                "dimension": entry.get("dimension", ""),
            }
        )
        has_obligation_edges.append(
            {
                "source_id": _article_id(ref),
                "target_id": obl_id,
            }
        )
        risk_id = _classify_risk_for_article(num)
        if risk_id is not None:
            applies_at_edges.append(
                {
                    "source_id": obl_id,
                    "target_id": risk_id,
                }
            )

    # ── Annex III categories (8) ──────────────────────────────────────
    annex_iii_nodes: list[dict] = []
    triggers_high_risk_edges: list[dict] = []
    for cat_id, cat in ANNEX_III_REGISTRY.items():
        node_id = f"annex_iii_{cat_id}"
        annex_iii_nodes.append(
            {
                "id": node_id,
                "label": cat.short_name,
                "number": cat.number,
                "description": cat.description[:2000],
            }
        )
        triggers_high_risk_edges.append(
            {
                "source_id": node_id,
                "target_id": _article_id("Art. 6"),
            }
        )

    # ── Risk levels (4) ───────────────────────────────────────────────
    risk_level_nodes: list[dict] = [dict(row) for row in RISK_LEVELS]

    # ── Operator roles (canonical 5 — provider/deployer/importer/
    # distributor/authorised_representative). The role_obligations table
    # carries additional modifier roles (GPAI, extraterritorial,
    # small_mid_cap) that aren't part of the closed Layer-1 NLF role set.
    operator_role_nodes: list[dict] = []
    canonical = {
        "provider",
        "deployer",
        "importer",
        "distributor",
        "authorized_representative",
    }
    for row in ROLE_OBLIGATIONS:
        if row.get("id") not in canonical:
            continue
        operator_role_nodes.append(
            {
                "id": f"role_{row['id']}",
                "label": row.get("label", row["id"]),
                "art_3_definition": row.get("art_3_definition", ""),
                "summary": row.get("summary", "")[:1500],
            }
        )

    # ── Cross-reference edges (regex + manual). Build directly off the
    # merged xref graph so the seeder picks up future edge additions
    # automatically. We tag the source — regex vs manual — for forensic
    # traceability.
    xref_graph = _build_xref_graph()
    manual_pairs: set[tuple[str, str]] = {
        (s, t) for s, t, _ in MANUAL_XREFS
    }
    cross_reference_edges: list[dict] = []
    for source_ref, targets in xref_graph.items():
        if source_ref not in ARTICLE_EXISTENCE:
            continue
        for target_ref in targets:
            if target_ref not in ARTICLE_EXISTENCE:
                continue
            if source_ref == target_ref:
                continue
            cross_reference_edges.append(
                {
                    "source_id": _article_id(source_ref),
                    "target_id": _article_id(target_ref),
                    "edge_source": (
                        "manual" if (source_ref, target_ref) in manual_pairs
                        else "regex"
                    ),
                }
            )

    # ── Recital-anchor edges: pull explicit "Recital N" mentions out of
    # the obligation summaries. Cheap regex pass — the corpus uses the
    # form ``Recital 85`` consistently when it refers back to a recital.
    recital_re = re.compile(r"\bRecital\s+(\d{1,3})\b", re.IGNORECASE)
    has_recital_anchor_edges: list[dict] = []
    seen_recital_edges: set[tuple[str, str]] = set()
    for ref, entry in EC_CHECKER_OBLIGATION_MAP.items():
        if ref not in ARTICLE_EXISTENCE:
            continue
        summary = entry.get("summary", "")
        if not summary:
            continue
        for match in recital_re.finditer(summary):
            n = int(match.group(1))
            if n not in RECITALS:
                continue
            edge_key = (_article_id(ref), f"recital_{n}")
            if edge_key in seen_recital_edges:
                continue
            seen_recital_edges.add(edge_key)
            has_recital_anchor_edges.append(
                {
                    "source_id": edge_key[0],
                    "target_id": edge_key[1],
                }
            )

    # ── KBMetadata ────────────────────────────────────────────────────
    metadata_node = {
        "id": "kb_metadata",
        "seed_version": SEED_VERSION,
        "kb_version": KB_VERSION,
        "seeded_at": datetime.now(timezone.utc).isoformat(),
        # total_nodes / total_edges are filled in after the SeedPayload
        # is built (chicken-and-egg) — see ``_finalise_metadata`` below.
        "total_nodes": 0,
        "total_edges": 0,
    }

    payload = SeedPayload(
        article_nodes=article_nodes,
        annex_nodes=annex_nodes,
        recital_nodes=recital_nodes,
        definition_nodes=definition_nodes,
        obligation_nodes=obligation_nodes,
        annex_iii_nodes=annex_iii_nodes,
        risk_level_nodes=risk_level_nodes,
        operator_role_nodes=operator_role_nodes,
        metadata_node=metadata_node,
        has_obligation_edges=has_obligation_edges,
        has_definition_edges=has_definition_edges,
        cross_reference_edges=cross_reference_edges,
        has_recital_anchor_edges=has_recital_anchor_edges,
        triggers_high_risk_edges=triggers_high_risk_edges,
        applies_at_edges=applies_at_edges,
    )
    # Backfill the counts now that everything else is settled.
    metadata_node["total_nodes"] = payload.total_nodes
    metadata_node["total_edges"] = payload.total_edges
    return payload


# ─── Cypher templates (parametrised MERGE statements) ─────────────────────
#
# Every template is idempotent: re-running with the same parameters
# produces no new graph elements. ``MERGE`` matches on the keyed
# properties (``id`` for nodes, ``source_id`` + ``target_id`` for edges);
# subsequent ``SET`` updates mutable fields so a re-seed against a newer
# KB_VERSION refreshes property values without duplicating nodes.

_CYPHER_ARTICLE = """
MERGE (a:Article {id: $id})
SET a.number = $number,
    a.title = $title,
    a.description = $description,
    a.chapter = $chapter,
    a.vector_chunk_ids = $vector_chunk_ids
"""

_CYPHER_ANNEX = """
MERGE (a:Annex {id: $id})
SET a.number = $number,
    a.title = $title,
    a.description = $description
"""

_CYPHER_RECITAL = """
MERGE (r:Recital {id: $id})
SET r.number = $number,
    r.text = $text
"""

_CYPHER_DEFINITION = """
MERGE (d:Definition {id: $id})
SET d.kind = $kind,
    d.term = $term,
    d.citation = $citation,
    d.text = $text
"""

_CYPHER_OBLIGATION = """
MERGE (o:Obligation {id: $id})
SET o.article_ref = $article_ref,
    o.text = $text,
    o.mandatory = $mandatory,
    o.paragraph_ref = $paragraph_ref,
    o.dimension = $dimension
"""

_CYPHER_ANNEX_III = """
MERGE (c:AnnexIIICategory {id: $id})
SET c.label = $label,
    c.number = $number,
    c.description = $description
"""

_CYPHER_RISK_LEVEL = """
MERGE (rl:RiskLevel {id: $id})
SET rl.label = $label,
    rl.description = $description
"""

_CYPHER_OPERATOR_ROLE = """
MERGE (role:OperatorRole {id: $id})
SET role.label = $label,
    role.art_3_definition = $art_3_definition,
    role.summary = $summary
"""

_CYPHER_METADATA = """
MERGE (m:KBMetadata {id: $id})
SET m.seed_version = $seed_version,
    m.kb_version = $kb_version,
    m.seeded_at = $seeded_at,
    m.total_nodes = $total_nodes,
    m.total_edges = $total_edges
"""

_CYPHER_HAS_OBLIGATION = """
MATCH (a:Article {id: $source_id})
MATCH (o:Obligation {id: $target_id})
MERGE (a)-[:HAS_OBLIGATION]->(o)
"""

_CYPHER_HAS_DEFINITION = """
MATCH (a:Article {id: $source_id})
MATCH (d:Definition {id: $target_id})
MERGE (a)-[:HAS_DEFINITION]->(d)
"""

_CYPHER_CROSS_REFERENCES = """
MATCH (s {id: $source_id})
MATCH (t {id: $target_id})
MERGE (s)-[r:CROSS_REFERENCES]->(t)
SET r.source = $edge_source
"""

_CYPHER_HAS_RECITAL_ANCHOR = """
MATCH (a:Article {id: $source_id})
MATCH (r:Recital {id: $target_id})
MERGE (a)-[:HAS_RECITAL_ANCHOR]->(r)
"""

_CYPHER_TRIGGERS_HIGH_RISK = """
MATCH (c:AnnexIIICategory {id: $source_id})
MATCH (a:Article {id: $target_id})
MERGE (c)-[:TRIGGERS_HIGH_RISK_UNDER]->(a)
"""

_CYPHER_APPLIES_AT = """
MATCH (o:Obligation {id: $source_id})
MATCH (rl:RiskLevel {id: $target_id})
MERGE (o)-[:APPLIES_AT]->(rl)
"""


# ─── Runner ──────────────────────────────────────────────────────────────


def _batched(rows: list[dict], size: int) -> Iterable[list[dict]]:
    """Yield successive ``size``-row windows."""
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _write_rows(
    client: Any,
    cypher: str,
    rows: list[dict],
    *,
    batch_size: int,
    label: str,
    verbose: bool,
) -> int:
    """Push ``rows`` through ``cypher`` in batches via ``execute_write_batch``.

    Returns the total row count written. Each batch is one transaction;
    individual ``execute_write_batch`` calls are atomic, so a mid-batch
    failure rolls back the offending batch only (earlier batches stay).
    """
    written = 0
    for chunk in _batched(rows, batch_size):
        queries: list[tuple[str, dict]] = [(cypher, row) for row in chunk]
        client.execute_write_batch(queries)
        written += len(chunk)
        if verbose:
            logger.info("seeded %s batch=%d total=%d", label, len(chunk), written)
    return written


def seed_graph(
    client: Any,
    payload: SeedPayload,
    *,
    batch_size: int = BATCH_SIZE,
    verbose: bool = False,
) -> dict[str, int]:
    """Run the full seed against ``client``.

    The grouping mirrors the dependency graph: nodes first (so edge
    ``MATCH``es resolve), then edges. Per-label batches keep individual
    transactions small.
    """
    counts: dict[str, int] = {}

    # ── Nodes ─────────────────────────────────────────────────────────
    counts["Article"] = _write_rows(
        client, _CYPHER_ARTICLE, payload.article_nodes,
        batch_size=batch_size, label="Article", verbose=verbose,
    )
    counts["Annex"] = _write_rows(
        client, _CYPHER_ANNEX, payload.annex_nodes,
        batch_size=batch_size, label="Annex", verbose=verbose,
    )
    counts["Recital"] = _write_rows(
        client, _CYPHER_RECITAL, payload.recital_nodes,
        batch_size=batch_size, label="Recital", verbose=verbose,
    )
    counts["Definition"] = _write_rows(
        client, _CYPHER_DEFINITION, payload.definition_nodes,
        batch_size=batch_size, label="Definition", verbose=verbose,
    )
    counts["Obligation"] = _write_rows(
        client, _CYPHER_OBLIGATION, payload.obligation_nodes,
        batch_size=batch_size, label="Obligation", verbose=verbose,
    )
    counts["AnnexIIICategory"] = _write_rows(
        client, _CYPHER_ANNEX_III, payload.annex_iii_nodes,
        batch_size=batch_size, label="AnnexIIICategory", verbose=verbose,
    )
    counts["RiskLevel"] = _write_rows(
        client, _CYPHER_RISK_LEVEL, payload.risk_level_nodes,
        batch_size=batch_size, label="RiskLevel", verbose=verbose,
    )
    counts["OperatorRole"] = _write_rows(
        client, _CYPHER_OPERATOR_ROLE, payload.operator_role_nodes,
        batch_size=batch_size, label="OperatorRole", verbose=verbose,
    )
    counts["KBMetadata"] = _write_rows(
        client, _CYPHER_METADATA, [payload.metadata_node],
        batch_size=batch_size, label="KBMetadata", verbose=verbose,
    )

    # ── Edges ─────────────────────────────────────────────────────────
    counts["HAS_OBLIGATION"] = _write_rows(
        client, _CYPHER_HAS_OBLIGATION, payload.has_obligation_edges,
        batch_size=batch_size, label="HAS_OBLIGATION", verbose=verbose,
    )
    counts["HAS_DEFINITION"] = _write_rows(
        client, _CYPHER_HAS_DEFINITION, payload.has_definition_edges,
        batch_size=batch_size, label="HAS_DEFINITION", verbose=verbose,
    )
    counts["CROSS_REFERENCES"] = _write_rows(
        client, _CYPHER_CROSS_REFERENCES, payload.cross_reference_edges,
        batch_size=batch_size, label="CROSS_REFERENCES", verbose=verbose,
    )
    counts["HAS_RECITAL_ANCHOR"] = _write_rows(
        client, _CYPHER_HAS_RECITAL_ANCHOR, payload.has_recital_anchor_edges,
        batch_size=batch_size, label="HAS_RECITAL_ANCHOR", verbose=verbose,
    )
    counts["TRIGGERS_HIGH_RISK_UNDER"] = _write_rows(
        client, _CYPHER_TRIGGERS_HIGH_RISK, payload.triggers_high_risk_edges,
        batch_size=batch_size, label="TRIGGERS_HIGH_RISK_UNDER", verbose=verbose,
    )
    counts["APPLIES_AT"] = _write_rows(
        client, _CYPHER_APPLIES_AT, payload.applies_at_edges,
        batch_size=batch_size, label="APPLIES_AT", verbose=verbose,
    )

    return counts


def validate_payload(payload: SeedPayload) -> list[str]:
    """Return a list of error strings; empty list means the payload is sane.

    Catches dangling edges (source / target IDs that don't appear in any
    node bucket). Pure check — does not raise. The runner exits non-zero
    when this returns a non-empty list under ``--dry-run`` or live mode.
    """
    node_ids: set[str] = set()
    for bucket in (
        payload.article_nodes,
        payload.annex_nodes,
        payload.recital_nodes,
        payload.definition_nodes,
        payload.obligation_nodes,
        payload.annex_iii_nodes,
        payload.risk_level_nodes,
        payload.operator_role_nodes,
    ):
        for row in bucket:
            node_ids.add(row["id"])
    node_ids.add(payload.metadata_node["id"])

    errors: list[str] = []
    edge_buckets = (
        ("HAS_OBLIGATION", payload.has_obligation_edges),
        ("HAS_DEFINITION", payload.has_definition_edges),
        ("CROSS_REFERENCES", payload.cross_reference_edges),
        ("HAS_RECITAL_ANCHOR", payload.has_recital_anchor_edges),
        ("TRIGGERS_HIGH_RISK_UNDER", payload.triggers_high_risk_edges),
        ("APPLIES_AT", payload.applies_at_edges),
    )
    for name, edges in edge_buckets:
        for row in edges:
            if row["source_id"] not in node_ids:
                errors.append(
                    f"{name}: dangling source_id={row['source_id']!r}"
                )
            if row["target_id"] not in node_ids:
                errors.append(
                    f"{name}: dangling target_id={row['target_id']!r}"
                )
    return errors


# ─── CLI ─────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="seed_neo4j_kb",
        description=(
            "Seed the Regenold EU AI Act KB (articles, annexes, recitals, "
            "definitions, obligations, ontology, role × risk edges) into "
            "Neo4j. Idempotent — MERGE-based."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload counts and exit without writing to Neo4j.",
    )
    p.add_argument(
        "--clear",
        action="store_true",
        help="DETACH DELETE every node before seeding (DESTRUCTIVE).",
    )
    p.add_argument(
        "--neo4j-uri",
        default=None,
        help="Override the NEO4J_URI env var.",
    )
    p.add_argument(
        "--neo4j-user",
        default=None,
        help="Override the NEO4J_USER env var.",
    )
    p.add_argument(
        "--neo4j-password",
        default=None,
        help="Override the NEO4J_PASSWORD env var.",
    )
    p.add_argument(
        "--neo4j-database",
        default=None,
        help="Override the NEO4J_DATABASE env var.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Rows per write transaction (default {BATCH_SIZE}).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Log per-batch progress.",
    )
    return p


def _apply_env_overrides(args: argparse.Namespace) -> None:
    """Map CLI overrides into env vars before GraphSettings reads them."""
    if args.neo4j_uri:
        os.environ["NEO4J_URI"] = args.neo4j_uri
    if args.neo4j_user:
        os.environ["NEO4J_USER"] = args.neo4j_user
    if args.neo4j_password:
        os.environ["NEO4J_PASSWORD"] = args.neo4j_password
    if args.neo4j_database:
        os.environ["NEO4J_DATABASE"] = args.neo4j_database


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    payload = build_payload()

    # Sanity-check before we touch the driver. Dangling edges should fail
    # loud — they indicate the source modules have drifted out of sync.
    errors = validate_payload(payload)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print(
            f"Payload validation failed with {len(errors)} dangling edges; "
            "fix source modules before seeding.",
            file=sys.stderr,
        )
        return 2

    counts = payload.counts()
    print("---- Regenold KB seed payload ----")
    print(f"  seed_version : {SEED_VERSION}")
    print(f"  kb_version   : {KB_VERSION}")
    print(f"  total_nodes  : {payload.total_nodes}")
    print(f"  total_edges  : {payload.total_edges}")
    for label, count in counts.items():
        print(f"    {label:<28} = {count}")

    if args.dry_run:
        print("\n--dry-run: no writes performed. Exiting 0.")
        return 0

    _apply_env_overrides(args)

    # Deferred import so the offline / dry-run paths don't drag the
    # graph client (and its optional neo4j driver) into module import.
    from app.graph.client import GraphClient
    from app.graph.config import GraphSettings

    client = GraphClient(GraphSettings())
    if not client.enabled:
        print(
            "ERROR: GraphClient is disabled — set NEO4J_URI (and install "
            "the 'neo4j' driver) before seeding. Use --dry-run to inspect "
            "the payload offline.",
            file=sys.stderr,
        )
        return 1

    if args.clear:
        print("[--clear] Wiping graph (DETACH DELETE every node)...")
        client.clear_graph()

    written = seed_graph(
        client, payload, batch_size=args.batch_size, verbose=args.verbose
    )
    print("\n---- Seed complete ----")
    for label, count in written.items():
        print(f"    {label:<28} = {count}")
    client.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
