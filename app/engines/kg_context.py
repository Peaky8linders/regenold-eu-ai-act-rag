"""R313.1 — put the Neo4j Aura knowledge graph back on the answer path.

OPERATOR DIRECTIVE (2026-08-04): *always* use the knowledge graph and Neo4j
Aura. This module is that wiring.

WHAT WAS ACTUALLY WRONG
=======================

The graph was never broken — it was BYPASSED. Measured this round against the
live instance (``151d4e69``, seed ``2026-07-24-r291-fullseed``, kb_version
``2024.1689.v18``):

    Article 113   Annex 13   Paragraph 656   Point 416   Recital 180
    Definition 68   nodes 1746   edges 1838
    rels: HAS_PARAGRAPH, HAS_POINT, HAS_SUBPOINT, HAS_RECITAL_ANCHOR,
          CROSS_REFERENCES, HAS_DEFINITION, HAS_OBLIGATION, ...

Healthy, complete, and contributing NOTHING to an answer, for three independent
reasons found by audit:

  1. ``graph_backend()`` defaulted to ``"embedded"``, so the hosted instance was
     not even selected;
  2. ``_kb_primary_retrieval_enabled()`` (R252, default ON) short-circuits
     ``_retrieve_from_graph`` to ``_retrieve_from_kb`` BEFORE the Neo4j branch,
     so the Cypher obligation/gap/dimension populators are dead by default;
  3. the surviving graph-dependent populators (compliance gaps, the Article 6(3)
     AST evaluation) additionally require ``request.answers``, which the
     Regenold route deliberately never sets — so they no-op even when Neo4j is
     reachable.

Net effect measured on a live request: ``retrieval_path='kb_fallback'`` and a
5037-char Stage-2 block whose every section was computed in-process.

WHY THIS DOES NOT SIMPLY UNDO R252
==================================

R252 demoted the graph from PRIMARY retriever for a good measured reason: the
blunt ``obligations_for_risk_level`` Cypher dumps the generic high-risk chain
(Arts. 9-15) for any risk tier, which buried the operative article on
transparency / role / topic questions (the live symptom was a gold Article 50
question answered with Articles 10/11/12). Re-enabling graph-primary retrieval
would re-break that.

So this module does the opposite of what R252 removed. It never ranks, never
retrieves candidates and never contributes a wire citation. It uses the graph
for the one thing the flat KB genuinely cannot do — walk the PROVISION
HIERARCHY and the RECITAL ANCHORS of the provisions we have already decided to
cite — and renders that as explicitly NON-CITABLE Stage-2 context.

That is also precisely the evidence the R313 faithfulness verifier needs: four
of R312's five citation failures are sub-provision misattribution (Article 6(3)
credited with Article 6(4)'s duty, Article 6(2) mischaracterised, Article 3
cited for a definition Article 3(1) does not contain), and the graph holds 656
Paragraph + 416 Point nodes keyed exactly at that grain.

SAFETY
======

* Additive only: it appends a context section. It cannot displace a BM25
  winner (it never enters ranking) and cannot add a citation (the section is
  labelled non-citable and the wire reference list is built elsewhere).
* Bounded: capped refs, capped paragraphs per ref, capped chars, one query,
  short timeout.
* Fail-soft: any driver error, timeout, missing label or disabled client
  returns ``[]`` and the answer path is byte-identical to before.
* Stage-2 only ⇒ the deterministic davidath bench never reaches it.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

__all__ = [
    "kg_context_enabled",
    "fetch_provision_hierarchy",
    "render_kg_context",
]

_DEFAULT_MAX_REFS = 4
_DEFAULT_MAX_UNITS = 8
_DEFAULT_UNIT_CHARS = 320
_DEFAULT_MAX_RECITALS = 3


def kg_context_enabled() -> bool:
    """``REGENOLD_KG_CONTEXT`` — DEFAULT ON per the operator directive.

    Fresh env read per call (R263.2). Setting it to ``0`` restores the
    pre-R313.1 behaviour exactly, since every other path is untouched.
    """
    return os.getenv("REGENOLD_KG_CONTEXT", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.getenv(name, ""))))
    except (TypeError, ValueError):
        return default


# ── Ref parsing ──────────────────────────────────────────────────────────────
#
# The seeded node ids are ``article_<n>`` / ``annex_<ROMAN>``, and Article.number
# is a STRING property (verified against the live instance), so both are matched
# as strings rather than ints.

_ART_RE = re.compile(r"\bArt(?:s?\.|icles?|s)?\s*(\d{1,3})", re.IGNORECASE)
_ANNEX_RE = re.compile(r"\bAnnexe?s?\s+([IVXLCDM]{1,7})\b", re.IGNORECASE)


def _node_ids(refs: list[str], limit: int) -> list[str]:
    """Map citation strings to seeded node ids, order-preserving + deduped."""
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs or []:
        node_id = None
        m = _ART_RE.search(str(ref))
        if m:
            node_id = f"article_{int(m.group(1))}"
        else:
            m = _ANNEX_RE.search(str(ref))
            if m:
                node_id = f"annex_{m.group(1).upper()}"
        if node_id and node_id not in seen:
            seen.add(node_id)
            out.append(node_id)
        if len(out) >= limit:
            break
    return out


# ── Cypher ───────────────────────────────────────────────────────────────────
#
# One query, one round trip. HAS_PARAGRAPH / HAS_POINT / HAS_SUBPOINT is the
# seeded hierarchy; HAS_RECITAL_ANCHOR is the interpretive anchor. Both verified
# present on the live instance this round.

_HIERARCHY_CYPHER = """
MATCH (a) WHERE a.id IN $ids AND (a:Article OR a:Annex)
OPTIONAL MATCH (a)-[:HAS_PARAGRAPH|HAS_POINT]->(u)
WITH a, u ORDER BY a.id, u.number
WITH a, collect({num: u.number, text: u.text})[..$max_units] AS units
RETURN a.id AS id,
       coalesce(a.strict_citation, a.id) AS cite,
       a.title AS title,
       units AS units
"""

_RECITAL_CYPHER = """
MATCH (a)-[:HAS_RECITAL_ANCHOR]->(r:Recital)
WHERE a.id IN $ids
RETURN a.id AS id, r.number AS num, r.text AS text
ORDER BY a.id, r.number
LIMIT $limit
"""


def _flat(text: object, limit: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for sep in (". ", "; ", ", "):
        idx = cut.rfind(sep)
        if idx > limit // 2:
            return cut[: idx + 1].strip()
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > limit // 2 else cut).strip()


def fetch_provision_hierarchy(refs: list[str]) -> list[dict]:
    """Paragraph/point breakdown of the cited provisions, straight from Aura.

    Returns ``[]`` on ANY failure — disabled gate, no driver, unreachable
    instance, unseeded labels, timeout. Never raises.
    """
    if not kg_context_enabled():
        return []
    ids = _node_ids(refs or [], _int_env("REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 10))
    if not ids:
        return []
    max_units = _int_env("REGENOLD_KG_MAX_UNITS", _DEFAULT_MAX_UNITS, 1, 30)
    try:
        from app.graph.client import get_graph_client  # noqa: PLC0415

        client = get_graph_client()
        if not getattr(client, "enabled", False):
            return []
        rows = client.execute_read(_HIERARCHY_CYPHER, {"ids": ids, "max_units": max_units})
        return list(rows or [])
    except Exception:  # noqa: BLE001 — the graph must never break an answer
        logger.debug("kg_context: hierarchy fetch failed", exc_info=True)
        return []


def fetch_recital_anchors(refs: list[str]) -> list[dict]:
    """Recitals anchored to the cited provisions (interpretive context only)."""
    if not kg_context_enabled():
        return []
    ids = _node_ids(refs or [], _int_env("REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 10))
    if not ids:
        return []
    limit = _int_env("REGENOLD_KG_MAX_RECITALS", _DEFAULT_MAX_RECITALS, 0, 10)
    if limit <= 0:
        return []
    try:
        from app.graph.client import get_graph_client  # noqa: PLC0415

        client = get_graph_client()
        if not getattr(client, "enabled", False):
            return []
        return list(client.execute_read(_RECITAL_CYPHER, {"ids": ids, "limit": limit}) or [])
    except Exception:  # noqa: BLE001
        logger.debug("kg_context: recital fetch failed", exc_info=True)
        return []


def render_kg_context(refs: list[str]) -> list[str]:
    """Render the graph's contribution as NON-CITABLE Stage-2 context.

    The label matters: it tells the model this is structure and interpretive
    background for provisions ALREADY cited, so it can attribute a duty to the
    right paragraph without treating the graph as licence to cite more. Every
    other non-citable block in the Stage-2 prompt uses the same framing.
    """
    if not kg_context_enabled():
        return []
    parts: list[str] = []
    unit_chars = _int_env("REGENOLD_KG_UNIT_CHARS", _DEFAULT_UNIT_CHARS, 80, 1200)

    try:
        rows = fetch_provision_hierarchy(refs)
    except Exception:  # noqa: BLE001
        rows = []
    lines: list[str] = []
    for row in rows:
        cite = str(row.get("cite") or row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        units = [u for u in (row.get("units") or []) if u and u.get("text")]
        if not cite or not units:
            continue
        head = f"- {cite}" + (f" ({title})" if title else "") + ":"
        lines.append(head)
        for unit in units:
            num = str(unit.get("num") or "").strip()
            body = _flat(unit.get("text"), unit_chars)
            if body:
                lines.append(f"    ({num}) {body}" if num else f"    {body}")
    if lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH PROVISION STRUCTURE "
            "(from the seeded EU AI Act graph — the paragraph and point "
            "breakdown of provisions ALREADY listed above. Use it to attribute "
            "a duty to the CORRECT paragraph, and to state a condition or "
            "derogation at the right sub-provision. Do NOT cite anything here "
            "that is not already listed above, and do NOT cite a paragraph "
            "number as a separate provision):\n"
            + "\n".join(lines)
        )

    try:
        recitals = fetch_recital_anchors(refs)
    except Exception:  # noqa: BLE001
        recitals = []
    rec_lines = [
        f"- Recital {r.get('num')}: {_flat(r.get('text'), unit_chars)}"
        for r in recitals
        if r.get("text")
    ]
    if rec_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH RECITAL ANCHORS "
            "(interpretive context only — recitals are NOT operative provisions "
            "and must NEVER appear as an Article/Annex citation):\n"
            + "\n".join(rec_lines)
        )

    if parts:
        try:
            from app.integrations.regenold.reasoning_trace import (  # noqa: PLC0415
                record_note,
            )
            record_note(f"kg_context sections={len(parts)} refs={len(refs or [])}")
        except Exception:  # noqa: BLE001
            pass
    return parts
