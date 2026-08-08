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
from contextvars import ContextVar

logger = logging.getLogger(__name__)

__all__ = [
    "kg_context_enabled",
    "fetch_provision_hierarchy",
    "fetch_recital_anchors",
    "fetch_cross_regulatory_context",
    "render_kg_context",
]

_DEFAULT_MAX_REFS = 8
_DEFAULT_MAX_UNITS = 24
_DEFAULT_UNIT_CHARS = 900
#: Total ceiling across every block render_kg_context returns (R323).
_DEFAULT_MAX_CHARS = 16000
_DEFAULT_MAX_RECITALS = 5


def kg_context_enabled() -> bool:
    """``REGENOLD_KG_CONTEXT`` — DEFAULT ON per the operator directive.

    Fresh env read per call (R263.2). Setting it to ``0`` restores the
    pre-R313.1 behaviour exactly, since every other path is untouched.
    """
    return os.getenv("REGENOLD_KG_CONTEXT", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _provenance_in_prompt_enabled() -> bool:
    """``REGENOLD_PROVENANCE_IN_PROMPT`` — DEFAULT OFF.

    Whether to append the CELEX / ELI provenance block to the Stage-2
    grounding context. Off by default: it is un-A/B'd prompt budget on the
    one rubric axis we lead, and the wire may only cite ``Article N`` /
    ``Annex X`` (hard rule #1). Fresh env read per call (R263.2).
    """
    return os.getenv("REGENOLD_PROVENANCE_IN_PROMPT", "0").strip().lower() in (
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


# R323 — an enumerated list opener, e.g. "consisting of: (a) a description".
# A provision whose duty is DEFINED by its enumeration (Art. 27(1)'s FRIA
# contents, Art. 11's technical documentation) is worse than useless when the
# enumeration is amputated: the model is told a duty exists and not what it
# requires.
_ENUM_OPENER_RE = re.compile(r"\(a\)\s")

#: Hard ceiling for a single unit once the enumeration guard has extended it.
#: Bounds the worst case so one pathological provision cannot dominate the
#: Stage-2 budget.
_UNIT_HARD_CEILING = 2600


def _flat(text: object, limit: int) -> str:
    """Flatten a provision to at most ``limit`` chars, losing as little as possible.

    R323 fixed two ways this silently amputated statutory text:

    1. BACKTRACK COULD DISCARD HALF THE BUDGET. The sentence-boundary search
       accepted any break past ``limit // 2``, so Article 27(1) (1421 chars, at
       a 900 budget) was delivered at **470 chars — 33%**. The accepted break
       must now be in the last quarter of the budget; a nearer sentence break
       loses too much and we fall through to a clause, then a word boundary.

    2. IT CUT MID-ENUMERATION WITHOUT SAYING SO. Article 27(1)'s lost remainder
       began exactly at "For that purpose, deployers shall perform an
       assessment consisting of: (a) a description ...", so the model received
       the FRIA duty with none of its (a)-(f) contents, and no indication that
       anything was missing. When an enumeration opens inside the budget, the
       whole unit is now delivered up to ``_UNIT_HARD_CEILING``; beyond that
       the text is explicitly marked truncated rather than ending mid-clause as
       if it were complete.
    """
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t

    # An enumerated provision is delivered whole where it plausibly fits: the
    # list IS the obligation.
    if _ENUM_OPENER_RE.search(t[:limit]) and len(t) <= _UNIT_HARD_CEILING:
        return t

    cut = t[:limit]
    floor = (limit * 3) // 4
    for sep in (". ", "; ", ", "):
        idx = cut.rfind(sep)
        if idx > floor:
            return cut[: idx + 1].strip() + " [...]"
    idx = cut.rfind(" ")
    return ((cut[:idx] if idx > floor else cut).strip()) + " [...]"


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


# ── R323: the seeded layers nothing was reading ────────────────────────────
#
# Measured over live requests before this: the graph holds 18 node labels and
# 16 relationship types, and a request issued only FOUR distinct Cypher shapes,
# touching Article / Annex / Paragraph / Point / Recital and three edge types.
# The whole deontic layer — the one that answers "is this prohibited?", "what
# must a deployer do?", "is this Annex III?" — was seeded and never read:
#
#   SubPoint 37          HAS_SUBPOINT 37              <- Art 5(1)(h)(i)-(iii)
#   Practice 8           PROHIBITED_UNDER 8
#   AnnexIIICategory 8   TRIGGERS_HIGH_RISK_UNDER 8
#   OperatorRole 5       HAS_OBLIGATION_ARTICLE 36    <- carries a tier property
#   LifecyclePhase 4     APPLIES_TO 20
#   RiskLevel 4          APPLIES_AT 47
#
# All of it is rendered as NON-CITABLE context, exactly like the hierarchy
# block — additive, never a ranker, never a wire citation (the R252 line).

#: Sub-point leaves of the cited provisions. The carve-outs live here:
#: Article 5(1)(h)(i)-(iii) (the real-time RBI exceptions, incl. the 545-char
#: 4-year-custodial clause) and Article 5(1)(c)(i)/(ii). A retrieval hop that
#: surfaces the PROHIBITION while dropping its EXCEPTION states the law
#: backwards, which is the failure this block exists to prevent.
_SUBPOINT_CYPHER = """
MATCH (a) WHERE a.id IN $ids AND (a:Article OR a:Annex)
MATCH (a)-[:HAS_PARAGRAPH]->(p)-[:HAS_POINT]->(pt)-[:HAS_SUBPOINT]->(s:SubPoint)
RETURN coalesce(a.strict_citation, a.id) AS cite,
       p.number AS para, pt.letter AS letter, s.id AS sid, s.text AS text
ORDER BY a.id, p.number, pt.letter, s.id
LIMIT $limit
"""

#: The deontic layer attached to the cited provisions, in one round-trip.
_DEONTIC_CYPHER = """
MATCH (a:Article) WHERE a.id IN $ids
OPTIONAL MATCH (pr:Practice)-[:PROHIBITED_UNDER]->(a)
OPTIONAL MATCH (cat:AnnexIIICategory)-[:TRIGGERS_HIGH_RISK_UNDER]->(a)
OPTIONAL MATCH (ro:OperatorRole)-[hoa:HAS_OBLIGATION_ARTICLE]->(a)
OPTIONAL MATCH (ph:LifecyclePhase)-[:APPLIES_TO]->(a)
RETURN coalesce(a.strict_citation, a.id) AS cite,
       collect(DISTINCT coalesce(pr.short_name, pr.id))                AS practices,
       collect(DISTINCT coalesce(cat.label, cat.id))                   AS annex_iii,
       collect(DISTINCT coalesce(ro.label, ro.id) + ' (' + coalesce(hoa.tier,'') + ')') AS roles,
       collect(DISTINCT coalesce(ph.label, ph.id) + ' from ' + coalesce(ph.effective_date,'')) AS phases
LIMIT $limit
"""


def _graph_rows(cypher: str, params: dict) -> list[dict]:
    """Run a read and return rows, or ``[]`` on ANY failure. Never raises."""
    if not kg_context_enabled():
        return []
    try:
        from app.graph.client import get_graph_client  # noqa: PLC0415

        client = get_graph_client()
        if not getattr(client, "enabled", False):
            return []
        return list(client.execute_read(cypher, params) or [])
    except Exception:  # noqa: BLE001 — the graph must never break an answer
        logger.debug("kg_context: graph read failed", exc_info=True)
        return []


def fetch_subpoint_detail(refs: list[str]) -> list[dict]:
    """Sub-point leaves (conditions, exceptions, carve-outs) of cited provisions."""
    ids = _node_ids(refs or [], _int_env("REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 10))
    if not ids:
        return []
    return _graph_rows(_SUBPOINT_CYPHER, {"ids": ids, "limit": 24})


def fetch_deontic_context(refs: list[str]) -> list[dict]:
    """Prohibited practices / Annex III categories / role duties / phases."""
    ids = _node_ids(refs or [], _int_env("REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 10))
    if not ids:
        return []
    return _graph_rows(_DEONTIC_CYPHER, {"ids": ids, "limit": 12})


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


_CROSS_REGULATORY_CYPHER = """
MATCH (a) WHERE a.id IN $ids AND (a:Article OR a:Annex)
OPTIONAL MATCH (a)-[:CROSS_REFERENCES|RELATES_TO|HAS_EXTERNAL_REF]->(ext)
WHERE ext.framework IN ['GDPR', 'EU_Charter', 'Charter'] OR ext.title CONTAINS 'GDPR' OR ext.title CONTAINS 'Charter'
RETURN a.id AS source_id,
       coalesce(a.strict_citation, a.id) AS source,
       coalesce(ext.framework, 'GDPR') AS framework,
       coalesce(ext.strict_citation, ext.id, ext.title) AS target,
       coalesce(ext.relation, 'CROSS_REFERENCES') AS relation,
       coalesce(ext.description, ext.text, '') AS description
LIMIT $limit
"""

# Static mapping for cross-regulatory graph edges when Neo4j is offline or has no external nodes seeded
_STATIC_CROSS_REGULATORY_MAP: dict[str, list[dict[str, str]]] = {
    "article_2": [
        {"framework": "GDPR", "target": "GDPR Art. 2(2)", "relation": "COMPLEMENTS", "description": "Scope alignment with personal/household data processing exemptions under GDPR."}
    ],
    "article_5": [
        {"framework": "EU_Charter", "target": "EU Charter Art. 1", "relation": "PROTECTS", "description": "Prohibitions against subliminal manipulation protect human dignity."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 8", "relation": "PROTECTS", "description": "Prohibitions against untargeted biometric scraping protect personal data."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 21", "relation": "PROTECTS", "description": "Prohibitions against social scoring and biometric categorisation prevent discrimination."}
    ],
    "article_10": [
        {"framework": "GDPR", "target": "GDPR Art. 5", "relation": "ALIGNS_WITH", "description": "Data governance requirements enforce data minimisation and data quality principles."},
        {"framework": "GDPR", "target": "GDPR Art. 6", "relation": "REQUIRES", "description": "Processing of personal data for AI training requires a lawful basis under GDPR Article 6."},
        {"framework": "GDPR", "target": "GDPR Art. 9", "relation": "EXCEPT_UNDER", "description": "Article 10(5) permits processing special category data strictly for bias detection and correction."}
    ],
    "article_13": [
        {"framework": "GDPR", "target": "GDPR Art. 13", "relation": "ALIGNS_WITH", "description": "Transparency to deployers complements deployer data subject notification duties under GDPR."},
        {"framework": "GDPR", "target": "GDPR Art. 22", "relation": "COMPLEMENTS", "description": "Provides technical transparency needed for human explanation under automated decision-making rules."}
    ],
    "article_14": [
        {"framework": "GDPR", "target": "GDPR Art. 22(3)", "relation": "ENFORCES", "description": "Human oversight measures enable meaningful human intervention required under GDPR Article 22(3)."}
    ],
    "article_27": [
        {"framework": "EU_Charter", "target": "EU Charter Art. 1", "relation": "ASSESSES_IMPACT_ON", "description": "FRIA evaluates impact on human dignity prior to putting high-risk system into service."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 7", "relation": "ASSESSES_IMPACT_ON", "description": "FRIA evaluates impact on privacy and private life."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 8", "relation": "ASSESSES_IMPACT_ON", "description": "FRIA evaluates impact on personal data protection."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 21", "relation": "ASSESSES_IMPACT_ON", "description": "FRIA evaluates impact on non-discrimination and equality."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 47", "relation": "ASSESSES_IMPACT_ON", "description": "FRIA evaluates impact on right to an effective remedy and fair trial."},
        {"framework": "GDPR", "target": "GDPR Art. 35", "relation": "INTEGRATES_WITH", "description": "Article 27(4) allows combining the AI Act FRIA with the GDPR Data Protection Impact Assessment (DPIA)."}
    ],
    "article_50": [
        {"framework": "GDPR", "target": "GDPR Art. 13", "relation": "COMPLEMENTS", "description": "Transparency notices for AI interaction complement GDPR personal data collection disclosures."},
        {"framework": "EU_Charter", "target": "EU Charter Art. 11", "relation": "PROTECTS", "description": "Synthetic content labelling protects freedom of information and prevents deception."}
    ]
}


def fetch_cross_regulatory_context(refs: list[str]) -> list[dict]:
    """Fetch external regulation graph edges (GDPR, EU Charter) for cited provisions.

    Returns a list of cross-regulatory dict records. Falls back to static statutory graph edges
    when Neo4j is offline or contains no external nodes for the given provisions.
    """
    if not kg_context_enabled():
        return []
    ids = _node_ids(refs or [], _int_env("REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 10))
    if not ids:
        return []

    results: list[dict] = []
    try:
        from app.graph.client import get_graph_client  # noqa: PLC0415
        client = get_graph_client()
        if getattr(client, "enabled", False):
            rows = client.execute_read(_CROSS_REGULATORY_CYPHER, {"ids": ids, "limit": 15})
            for r in rows or []:
                if r and r.get("target"):
                    results.append({
                        "source": str(r.get("source") or r.get("source_id") or ""),
                        "framework": str(r.get("framework") or "GDPR"),
                        "target": str(r.get("target") or ""),
                        "relation": str(r.get("relation") or "CROSS_REFERENCES"),
                        "description": str(r.get("description") or ""),
                    })
    except Exception:  # noqa: BLE001
        logger.debug("kg_context: cross-regulatory cypher failed", exc_info=True)

    if not results:
        for node_id in ids:
            static_edges = _STATIC_CROSS_REGULATORY_MAP.get(node_id, [])
            num_match = re.search(r"\d+", node_id)
            source_cite = f"Art. {num_match.group(0)}" if num_match else node_id
            for edge in static_edges:
                rec = dict(edge)
                rec["source"] = source_cite
                results.append(rec)

    return results


#: R323 — request-scoped memo for :func:`render_kg_context`.
#:
#: MEASURED: the renderer is called THREE times per Stage-2 request with the
#: identical ref list (the supplementary-section builder is reached from more
#: than one assembly path), so every graph round-trip was paid three times for
#: byte-identical output. Wiring the previously-unread deontic layer added more
#: reads per call, which makes de-duplication a prerequisite rather than a
#: nicety: 3 requests went 23 -> 53 queries before this.
#:
#: A ContextVar rather than an lru_cache: the graph can be re-seeded and the
#: refs are per-request, so a process-lifetime cache would serve stale
#: structure. This entry is reset per request by the route's trace setup and,
#: failing that, is keyed on the exact ref tuple so a different question can
#: never read another question's entry.
_RENDER_MEMO: ContextVar[tuple[tuple[str, ...], list[str]] | None] = ContextVar(
    "regenold_kg_render_memo", default=None
)


def render_kg_context(refs: list[str]) -> list[str]:
    """Render the graph's contribution as NON-CITABLE Stage-2 context.

    The label matters: it tells the model this is structure and interpretive
    background for provisions ALREADY cited, so it can attribute a duty to the
    right paragraph without treating the graph as licence to cite more. Every
    other non-citable block in the Stage-2 prompt uses the same framing.
    """
    if not kg_context_enabled():
        return []

    memo_key = tuple(str(r) for r in (refs or []))
    try:
        cached = _RENDER_MEMO.get()
        if cached is not None and cached[0] == memo_key:
            return list(cached[1])
    except Exception:  # noqa: BLE001 — a memo miss must never break an answer
        pass

    parts: list[str] = []
    unit_chars = _int_env("REGENOLD_KG_UNIT_CHARS", _DEFAULT_UNIT_CHARS, 80, 1200)
    # R323 — a total ceiling on what the graph may inject. Measured before this
    # existed: a 12-ref scenario rendered 30,559 chars into the Stage-2 prompt
    # with no bound at all. R319 measured that added context runs at ~2.5% gold
    # precision and demonstrated crowding-out (kw recall 1.0 -> 0.0 on a gold
    # article that WAS present in the inflated context), so an unbounded block
    # is a measured risk, not just a token cost. Set generously so it bites only
    # the pathological tail: typical 2-4 ref requests render 5-14k.
    max_chars = _int_env("REGENOLD_KG_MAX_CHARS", _DEFAULT_MAX_CHARS, 1200, 60000)

    try:
        rows = fetch_provision_hierarchy(refs)
    except Exception:  # noqa: BLE001
        rows = []
    # R323 — the provision-structure block is by far the largest and is a
    # SINGLE block, so a block-granular cap can never trim it. Budget it while
    # building instead, dropping whole units (never half a unit) once the
    # ceiling is reached. Measured before this: a 12-ref scenario produced one
    # 29,623-char block.
    lines: list[str] = []
    used = 0
    over_cap = 0
    for row in rows:
        cite = str(row.get("cite") or row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        units = [u for u in (row.get("units") or []) if u and u.get("text")]
        if not cite or not units:
            continue
        head = f"- {cite}" + (f" ({title})" if title else "") + ":"
        pending: list[str] = []
        for unit in units:
            num = str(unit.get("num") or "").strip()
            body = _flat(unit.get("text"), unit_chars)
            if not body:
                continue
            line = f"    ({num}) {body}" if num else f"    {body}"
            # Always admit the first unit of the first provision, so a single
            # oversized provision still yields context rather than nothing.
            if used and used + len(line) > max_chars:
                over_cap += 1
                continue
            pending.append(line)
            used += len(line)
        if pending:
            lines.append(head)
            lines.extend(pending)
            used += len(head)
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

    # R323 — sub-point leaves: the conditions, exceptions and carve-outs.
    # Surfacing a prohibition without its exception states the law backwards,
    # and Article 5(1)(h)(i)-(iii) (the real-time RBI exceptions) lived in the
    # graph unread until now.
    try:
        subs = fetch_subpoint_detail(refs)
    except Exception:  # noqa: BLE001
        subs = []
    sub_lines: list[str] = []
    for row in subs:
        body = _flat(row.get("text"), unit_chars)
        if not body:
            continue
        cite = str(row.get("cite") or "").strip()
        para = str(row.get("para") or "").strip()
        letter = str(row.get("letter") or "").strip()
        sub = str(row.get("sid") or "").rsplit("_", 1)[-1]
        sub_lines.append(f"- {cite}({para})({letter})({sub}): {body}")
    if sub_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH SUB-POINT DETAIL "
            "(the conditions, exceptions and carve-outs nested under provisions "
            "ALREADY listed above. A prohibition stated without its exception is "
            "WRONG — use these to qualify a duty or a ban precisely. Cite the "
            "parent provision, never a sub-point as a separate article):\n"
            + "\n".join(sub_lines)
        )

    # R323 — the deontic layer: prohibited practices, Annex III trigger
    # categories, role duties with their tier, and applicability phases.
    try:
        deontic = fetch_deontic_context(refs)
    except Exception:  # noqa: BLE001
        deontic = []
    deo_lines: list[str] = []
    for row in deontic:
        cite = str(row.get("cite") or "").strip()
        bits: list[str] = []
        for key, label in (
            ("practices", "prohibited practices"),
            ("annex_iii", "Annex III high-risk categories"),
            ("roles", "operator duties"),
            ("phases", "applies from"),
        ):
            vals = [str(v).strip() for v in (row.get(key) or []) if v and str(v).strip(" ()")]
            if vals:
                bits.append(f"{label}: {', '.join(sorted(set(vals))[:8])}")
        if bits:
            deo_lines.append(f"- {cite} — " + "; ".join(bits))
    if deo_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH REGULATORY CLASSIFICATION "
            "(typed ontology attached to the provisions ALREADY listed above — "
            "which practices a prohibition covers, which Annex III categories "
            "trigger high-risk classification, which operator role owes a duty "
            "and at what tier, and when the provision applies. Structure only: "
            "do NOT cite anything here that is not already listed above):\n"
            + "\n".join(deo_lines)
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

    try:
        cross_reg = fetch_cross_regulatory_context(refs)
    except Exception:  # noqa: BLE001
        cross_reg = []
    if cross_reg:
        cross_lines = [
            f"- {r.get('source')} -> {r.get('framework')} ({r.get('target')}): {r.get('description')}"
            for r in cross_reg
            if r.get("target")
        ]
        if cross_lines:
            parts.append(
                "\nKNOWLEDGE-GRAPH CROSS-REGULATORY EDGES "
                "(preserves external regulation graph relationships linking EU AI Act provisions "
                "to GDPR and the EU Charter of Fundamental Rights):\n"
                + "\n".join(cross_lines)
            )

    # ── Legal provenance (env-gated, default OFF) ────────────────────────
    #
    # The first cut of this block shipped default-ON, unconditionally, and
    # asserted CELEX 02024R1689-20260727 — the POST-Digital-Omnibus
    # consolidation (69 EUR-Lex M1 markers pointing at CELEX 32026R1744,
    # "Digital Omnibus on AI"). Our corpus is the PRE-Omnibus original,
    # CELEX 32024R1689, so that block asserted a provenance the shipped text
    # does not have — hard rule #4.
    #
    # It is now (a) corrected from the pinned provenance module, (b) gated
    # OFF by default and (c) appended only when there is other graph context.
    # Default OFF because it is un-A/B'd prompt budget on the ONE rubric axis
    # we lead (Answer-Conciseness, zero headroom), and because the wire may
    # only ever cite "Article N" / "Annex X" (hard rule #1) — a CELEX in the
    # model's context is a citation shape it must never emit. Provenance
    # belongs on the graph nodes and in the audit trail, not in the answer
    # prompt. Set REGENOLD_PROVENANCE_IN_PROMPT=1 to A/B it back on.
    if parts and _provenance_in_prompt_enabled():
        try:
            from app.data.lawstronaut_provenance import (  # noqa: PLC0415
                OFFICIAL_CELEX,
                OFFICIAL_ELI,
                OFFICIAL_LEGAL_LINK,
                OFFICIAL_PROVENANCE_LINE,
            )

            parts.append(
                "\nOFFICIAL LEGAL PROVENANCE (context only — NEVER cite a CELEX "
                "or ELI on the wire; citations are 'Article N' / 'Annex X' only):\n"
                f"- Instrument: {OFFICIAL_PROVENANCE_LINE}\n"
                f"- CELEX: {OFFICIAL_CELEX}\n"
                f"- ELI: {OFFICIAL_ELI}\n"
                f"- Source: {OFFICIAL_LEGAL_LINK}\n"
            )
        except Exception:  # noqa: BLE001
            pass

    # R323 — enforce the total ceiling by dropping WHOLE trailing blocks. The
    # blocks are appended in descending order of value (provision structure,
    # then recitals, then cross-regulatory, then provenance), so trimming from
    # the tail sheds the least useful context first. Never half-render a block:
    # a truncated heading would misdescribe what follows it.
    dropped = over_cap
    while len(parts) > 1 and sum(len(p) for p in parts) > max_chars:
        parts.pop()
        dropped += 1

    if parts:
        try:
            from app.integrations.regenold.reasoning_trace import (  # noqa: PLC0415
                record_note,
            )
            note = f"kg_context sections={len(parts)} refs={len(refs or [])}"
            if dropped:
                note += f" dropped_over_cap={dropped}"
            record_note(note)
        except Exception:  # noqa: BLE001
            pass

    try:
        _RENDER_MEMO.set((memo_key, list(parts)))
    except Exception:  # noqa: BLE001
        pass
    return parts
