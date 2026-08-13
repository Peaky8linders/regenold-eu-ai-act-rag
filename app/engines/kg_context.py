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
import threading
from contextvars import ContextVar

logger = logging.getLogger(__name__)

__all__ = [
    "kg_context_enabled",
    "fetch_provision_hierarchy",
    "fetch_recital_anchors",
    "fetch_subpoint_detail",
    "fetch_deontic_context",
    "fetch_cross_regulatory_context",
    "render_kg_context",
    "reset_kg_context_memo",
    "reset_render_memo",
    "_RENDER_MEMO",
]

_DEFAULT_MAX_REFS = 8
_DEFAULT_MAX_UNITS = 24
_DEFAULT_UNIT_CHARS = 900
_DEFAULT_MAX_RECITALS = 5
#: Total ceiling across every block ``render_kg_context`` returns (R323, ported
#: from the RAG repo in R325). Without it a 12-ref scenario can inject an
#: unbounded wall of provision text that crowds the rest of the Stage-2 prompt.
_DEFAULT_MAX_CHARS = 16000
#: R327 — ceiling used only when the semantic vector layers contribute a block.
_DEFAULT_SEMANTIC_MAX_CHARS = 26000


def kg_context_enabled() -> bool:
    """``REGENOLD_KG_CONTEXT`` — DEFAULT ON per the operator directive.

    Fresh env read per call (R263.2). Setting it to ``0`` restores the
    pre-R313.1 behaviour exactly, since every other path is untouched.
    """
    return os.getenv("REGENOLD_KG_CONTEXT", "1").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _provenance_in_prompt_enabled() -> bool:
    """``REGENOLD_PROVENANCE_IN_PROMPT`` — DEFAULT OFF."""
    return os.getenv("REGENOLD_PROVENANCE_IN_PROMPT", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.getenv(name, ""))))
    except (TypeError, ValueError):
        return default


def _adaptive_int(field: str, name: str, default: int, lo: int, hi: int) -> int:
    """R329 — HyPA per-question value for a graph knob, else the env/default.

    Precedence is explicit env > adaptive > default (see
    :func:`app.engines.query_complexity_router.adaptive_int`). With the router
    off — the default — this is byte-identical to :func:`_int_env`.

    Soft-fails to :func:`_int_env` so a graph read can never break on an import
    problem in an optional routing module.
    """
    try:
        from app.engines.query_complexity_router import adaptive_int  # noqa: PLC0415

        return adaptive_int(field, name, default, lo, hi)
    except Exception:  # noqa: BLE001 — never let routing break graph context
        return _int_env(name, default, lo, hi)


# ── Ref parsing ──────────────────────────────────────────────────────────────

_ART_RE = re.compile(r"\bArt(?:s?\.|icles?|s)?\s*(\d{1,3})", re.IGNORECASE)
_ANNEX_RE = re.compile(r"\bAnnexe?s?\s+([IVXLCDM]{1,7})\b", re.IGNORECASE)


def _node_ids(refs: list[str], limit: int) -> list[str]:
    """Map citation strings to seeded node ids, order-preserving + deduped."""
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs or []:
        for m in _ART_RE.finditer(str(ref)):
            node_id = f"article_{int(m.group(1))}"
            if node_id not in seen:
                seen.add(node_id)
                out.append(node_id)
                if len(out) >= limit:
                    return out
        for m in _ANNEX_RE.finditer(str(ref)):
            node_id = f"annex_{m.group(1).upper()}"
            if node_id not in seen:
                seen.add(node_id)
                out.append(node_id)
                if len(out) >= limit:
                    return out
    return out


_HIERARCHY_CYPHER = """
UNWIND range(0, size($ids) - 1) AS i
WITH i, $ids[i] AS aid
MATCH (a) WHERE a.id = aid AND (a:Article OR a:Annex)
OPTIONAL MATCH (a)-[:HAS_PARAGRAPH|HAS_POINT]->(u)
WITH i, a, u ORDER BY toIntegerOrNull(u.number), u.number
WITH i, a, collect(u)[..$max_units] AS units
ORDER BY i
RETURN coalesce(a.strict_citation, a.id) AS cite,
       a.title AS title,
       [u IN units | {num: u.number, text: u.text}] AS units
"""

_RECITAL_CYPHER = """
UNWIND $ids AS aid
MATCH (a) WHERE a.id = aid AND (a:Article OR a:Annex)
MATCH (a)-[:HAS_RECITAL_ANCHOR]->(r:Recital)
RETURN DISTINCT r.number AS num, r.text AS text
ORDER BY toIntegerOrNull(r.number)
LIMIT $max_recitals
"""

_SUBPOINT_CYPHER = """
UNWIND $ids AS aid
MATCH (a) WHERE a.id = aid AND (a:Article OR a:Annex)
MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)-[:HAS_POINT]->(pt:Point)-[:HAS_SUBPOINT]->(sp:SubPoint)
RETURN coalesce(a.strict_citation, a.id) AS cite,
       p.number AS para,
       pt.number AS letter,
       sp.id AS sid,
       sp.roman AS roman,
       sp.text AS text
ORDER BY cite, toIntegerOrNull(p.number), letter, sid
LIMIT $max_units
"""

_DEONTIC_CYPHER = """
CALL () {
    MATCH (a:Article) WHERE a.id IN $ids
    OPTIONAL MATCH (pr:Practice)-[:PROHIBITED_UNDER]->(a)
    OPTIONAL MATCH (cat:AnnexIIICategory)-[:TRIGGERS_HIGH_RISK_UNDER]->(a)
    OPTIONAL MATCH (ro:OperatorRole)-[hoa:HAS_OBLIGATION_ARTICLE]->(a)
    OPTIONAL MATCH (ph:LifecyclePhase)-[:APPLIES_TO]->(a)
    RETURN coalesce(a.strict_citation, a.id) AS cite,
           collect(DISTINCT coalesce(pr.short_name, pr.id)) AS practices,
           collect(DISTINCT coalesce(cat.label, cat.id)) AS annex_iii,
           collect(DISTINCT coalesce(ro.label, ro.id) + ' (' + coalesce(hoa.tier,'') + ')') AS roles,
           collect(DISTINCT coalesce(ph.label, ph.id) + ' from ' + coalesce(ph.effective_date,'')) AS phases
    UNION
    MATCH (cat:AnnexIIICategory)
    WHERE 'annex_III' IN $ids
    RETURN 'Annex III' AS cite,
           [] AS practices,
           collect(DISTINCT coalesce(cat.label, cat.id)) AS annex_iii,
           [] AS roles,
           [] AS phases
}
RETURN cite, practices, annex_iii, roles, phases
LIMIT $limit
"""

_MEMO_VAR: ContextVar[dict[str, list[dict]] | None] = ContextVar(
    "kg_context_memo", default=None
)
_RENDER_MEMO = _MEMO_VAR


def reset_kg_context_memo() -> None:
    """Clear per-request query cache. Call at request start."""
    _MEMO_VAR.set({})


def reset_render_memo() -> None:
    """Alias for reset_kg_context_memo for test compatibility."""
    reset_kg_context_memo()


def _memoized_read(cache_key: str, cypher: str, params: dict) -> list[dict]:
    memo = _MEMO_VAR.get()
    if memo is not None and cache_key in memo:
        return memo[cache_key]
    rows = _bounded_execute_read(cypher, params)
    if memo is not None and not getattr(rows, "failed", False):
        memo[cache_key] = rows
    return rows


_EXECUTOR: object | None = None
_EXECUTOR_LOCK = threading.Lock()
_KG_MAX_INFLIGHT = _int_env("REGENOLD_KG_MAX_INFLIGHT", 4, 1, 8)
_KG_ADMISSION = threading.BoundedSemaphore(_KG_MAX_INFLIGHT)


class _ReadRows(list):
    """List-compatible result that distinguishes errors from empty matches."""

    def __init__(self, rows=(), *, failed: bool = False):
        super().__init__(rows)
        self.failed = failed


def _get_kg_executor():
    """Lazy, module-private bounded worker pool."""
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

                _EXECUTOR = ThreadPoolExecutor(
                    max_workers=_KG_MAX_INFLIGHT,
                    thread_name_prefix="kgctx",
                )
    return _EXECUTOR


def _bounded_execute_read(cypher: str, params: dict) -> list[dict]:
    from app.graph.timeouts import (  # noqa: PLC0415
        graph_circuit_open,
        record_graph_failure,
        record_graph_success,
        resolve_graph_timeout_ms,
    )

    if graph_circuit_open():
        logger.debug("kg_context: skipped — graph circuit open")
        return _ReadRows(failed=True)

    from app.graph.client import get_graph_client  # noqa: PLC0415

    client = get_graph_client()
    if not getattr(client, "enabled", False):
        return _ReadRows(failed=True)

    def _call() -> list[dict]:
        strict_read = getattr(client, "execute_read_strict", None)
        if callable(strict_read):
            return list(strict_read(cypher, params) or [])
        return list(client.execute_read(cypher, params) or [])

    from concurrent.futures import TimeoutError as _FutTimeout  # noqa: PLC0415

    budget_ms = resolve_graph_timeout_ms()
    _admit_budget_s = max(budget_ms, 1) / 1000.0
    if not _KG_ADMISSION.acquire(timeout=_admit_budget_s):
        record_graph_failure()
        logger.info(
            "kg_context: graph worker admission saturated after %.0fms",
            _admit_budget_s * 1000.0,
        )
        return _ReadRows(failed=True)

    fut = None
    try:
        fut = _get_kg_executor().submit(_call)
        fut.add_done_callback(lambda _done: _KG_ADMISSION.release())
        rows = fut.result(timeout=max(budget_ms, 1) / 1000.0)
        record_graph_success()
        return _ReadRows(rows)
    except _FutTimeout:
        if fut is not None:
            fut.cancel()
        record_graph_failure()
        logger.info("kg_context: cypher timeout budget=%dms", budget_ms)
        return _ReadRows(failed=True)
    except Exception:  # noqa: BLE001
        if fut is None:
            _KG_ADMISSION.release()
        record_graph_failure()
        logger.debug("kg_context: bounded read failed", exc_info=True)
        return _ReadRows(failed=True)


def fetch_provision_hierarchy(refs: list[str]) -> list[dict]:
    """Paragraph/point breakdown of cited provisions from Neo4j."""
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 20)
    max_units = _adaptive_int("kg_max_units", "REGENOLD_KG_MAX_UNITS", _DEFAULT_MAX_UNITS, 1, 100)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    cache_key = f"h:{','.join(ids)}:u{max_units}"
    return _memoized_read(
        cache_key,
        _HIERARCHY_CYPHER,
        {"ids": ids, "max_units": max_units},
    )


def fetch_recital_anchors(refs: list[str]) -> list[dict]:
    """Interpretive recitals for cited provisions."""
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 20)
    max_recitals = _int_env("REGENOLD_KG_MAX_RECITALS", _DEFAULT_MAX_RECITALS, 1, 20)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    cache_key = f"r:{','.join(ids)}:r{max_recitals}"
    return _memoized_read(
        cache_key,
        _RECITAL_CYPHER,
        {"ids": ids, "max_recitals": max_recitals},
    )


def fetch_subpoint_detail(refs: list[str]) -> list[dict]:
    """Sub-point detail (paragraph -> point -> subpoint) for cited provisions."""
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 20)
    max_units = _adaptive_int("kg_max_units", "REGENOLD_KG_MAX_UNITS", _DEFAULT_MAX_UNITS, 1, 100)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    cache_key = f"sp:{','.join(ids)}:u{max_units}"
    return _memoized_read(
        cache_key,
        _SUBPOINT_CYPHER,
        {"ids": ids, "max_units": max_units},
    )


def fetch_deontic_context(refs: list[str]) -> list[dict]:
    """Regulatory classifications attached to cited provisions."""
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, 20)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    cache_key = f"de:{','.join(ids)}"
    return _memoized_read(
        cache_key,
        _DEONTIC_CYPHER,
        {"ids": ids},
    )


_ENUM_OPENER_RE = re.compile(r"(?:\(?[a-hA-H1-9]\)\s|[1-9]\.\s)")
_UNIT_HARD_CEILING = 2600


def _flat(text: object, limit: int) -> str:
    """Flatten provision text, preserving enumerations and marking truncation."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t

    if _ENUM_OPENER_RE.search(t[:limit]):
        if len(t) <= _UNIT_HARD_CEILING:
            return t
        limit = _UNIT_HARD_CEILING

    cut = t[:limit]
    floor = (limit * 3) // 4
    for sep in (". ", "; ", ", "):
        idx = cut.rfind(sep)
        if idx > floor:
            return cut[: idx + 1].strip() + " [...]"
    idx = cut.rfind(" ")
    return ((cut[:idx] if idx > floor else cut).strip()) + " [...]"


def _render_semantic_layers(question: str, refs: list[str]) -> list[str]:
    """R327 — the five vector indexes, as non-citable context."""
    if not question:
        return []
    try:
        from app.engines.graph_semantic import (  # noqa: PLC0415
            fetch_definition_and_recital_context,
            fetch_focused_subprovisions,
            semantic_layers_enabled,
        )

        if not semantic_layers_enabled():
            return []
    except Exception:  # noqa: BLE001
        return []

    parts: list[str] = []
    unit_chars = _int_env("REGENOLD_KG_UNIT_CHARS", _DEFAULT_UNIT_CHARS, 80, 1200)

    try:
        focused = fetch_focused_subprovisions(question, refs)
    except Exception:  # noqa: BLE001
        focused = []
    focus_lines: list[str] = []
    for row in focused:
        text = _flat(row.get("text"), unit_chars)
        if not text:
            continue
        layer = str(row.get("layer") or "unit").lower()
        focus_lines.append(
            f"- {row.get('cite')} [{layer} {row.get('uid')}]: {text}"
        )
    if focus_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH QUESTION-FOCUSED SUB-PROVISIONS "
            "(the paragraphs, points and sub-points OF THE PROVISIONS ALREADY "
            "LISTED ABOVE that are closest to this question, ranked by the "
            "graph's own vector indexes. Use them to attribute the duty to the "
            "right sub-provision. They add NO new provision — every one belongs "
            "to a provision already cited — so do NOT cite anything new here):\n"
            + "\n".join(focus_lines)
        )

    try:
        gloss = fetch_definition_and_recital_context(question, refs)
    except Exception:  # noqa: BLE001
        gloss = []
    def_lines: list[str] = []
    rec_lines: list[str] = []
    for row in gloss:
        text = _flat(row.get("text"), unit_chars)
        if not text:
            continue
        if str(row.get("layer")) == "Definition":
            cite = str(row.get("cite") or "").strip()
            suffix = f" ({cite})" if cite else ""
            def_lines.append(f"- '{row.get('label')}'{suffix}: {text}")
        else:
            rec_lines.append(f"- Recital {row.get('label')}: {text}")
    if def_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH DEFINITIONS "
            "(Article 3 definitions semantically closest to this question — "
            "use them for the correct legal meaning of a term. Definitional "
            "background only: do NOT add a citation just because a definition "
            "appears here):\n"
            + "\n".join(def_lines)
        )
    if rec_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH RECITAL CONTEXT "
            "(interpretive background retrieved semantically. Recitals are NOT "
            "operative provisions and must NEVER appear as an Article/Annex "
            "citation):\n"
            + "\n".join(rec_lines)
        )
    return parts


_R326_RESERVED_MARKERS = (
    "KNOWLEDGE-GRAPH SUB-POINT DETAIL",
    "KNOWLEDGE-GRAPH REGULATORY CLASSIFICATION",
    "KNOWLEDGE-GRAPH QUESTION-FOCUSED SUB-PROVISIONS",
    "KNOWLEDGE-GRAPH DEFINITIONS",
    "KNOWLEDGE-GRAPH RECITAL CONTEXT",
    "KNOWLEDGE-GRAPH RECITAL ANCHORS",
    "OFFICIAL LEGAL PROVENANCE",
)


def _fit_complete_lines(block: str, budget: int) -> tuple[str, bool]:
    if len(block) <= budget:
        return block, False
    lines = block.splitlines()
    kept: list[str] = []
    curr = 0
    for line in lines:
        needed = len(line) + 1
        if curr + needed > budget:
            break
        kept.append(line)
        curr += needed
    if not kept:
        return "", True
    res = "\n".join(kept).strip()
    return res, True


def _budget_context_parts(parts: list[str], total_limit: int) -> tuple[list[str], bool]:
    if not parts:
        return [], False

    res_parts: list[str] = []
    oth_parts: list[str] = []

    for p in parts:
        if any(m in p for m in _R326_RESERVED_MARKERS):
            res_parts.append(p)
        else:
            oth_parts.append(p)

    if not res_parts:
        out: list[str] = []
        rem = total_limit
        any_trimmed = False
        for p in parts:
            if rem <= 0:
                any_trimmed = True
                break
            fitted, trimmed = _fit_complete_lines(p, rem)
            if fitted:
                out.append(fitted)
                rem -= len(fitted) + 2
            if trimmed:
                any_trimmed = True
        return out, any_trimmed

    res_budget = max(4000, total_limit // 2)
    oth_budget = total_limit - res_budget

    out_res: list[str] = []
    rem_res = res_budget
    res_trimmed = False
    for p in res_parts:
        if rem_res <= 0:
            res_trimmed = True
            break
        fitted, tr = _fit_complete_lines(p, rem_res)
        if fitted:
            out_res.append(fitted)
            rem_res -= len(fitted) + 2
        if tr:
            res_trimmed = True

    oth_budget += max(0, rem_res)

    out_oth: list[str] = []
    rem_oth = oth_budget
    oth_trimmed = False
    for p in oth_parts:
        if rem_oth <= 0:
            oth_trimmed = True
            break
        fitted, tr = _fit_complete_lines(p, rem_oth)
        if fitted:
            out_oth.append(fitted)
            rem_oth -= len(fitted) + 2
        if tr:
            oth_trimmed = True

    res_budget_left = max(0, rem_res)
    if res_budget_left > 0 and oth_trimmed and oth_parts:
        extra_out: list[str] = []
        rem_extra = res_budget_left
        for p in oth_parts:
            if p in out_oth:
                continue
            if rem_extra <= 0:
                break
            fitted, tr = _fit_complete_lines(p, rem_extra)
            if fitted:
                extra_out.append(fitted)
                rem_extra -= len(fitted) + 2
        out_oth.extend(extra_out)

    final_parts: list[str] = []
    for p in parts:
        for candidate in out_oth + out_res:
            if p.startswith(candidate[:40]) and candidate not in final_parts:
                final_parts.append(candidate)
                break

    if not final_parts:
        final_parts = out_oth + out_res

    return final_parts, (res_trimmed or oth_trimmed)


def fetch_cross_regulatory_context(refs: list[str]) -> list[dict]:
    """Cross-regulatory mappings (e.g. GDPR, EU Charter, MDR/IVDR) for cited provisions."""
    if not kg_context_enabled():
        return []
    ids = _node_ids(refs, limit=8)
    if not ids:
        return []
    out: list[dict] = []
    if "article_10" in ids:
        out.append({"cite": "Article 10", "framework": "GDPR", "ref": "GDPR Art. 35", "topic": "Data Governance"})
    if "article_27" in ids:
        out.append({"cite": "Article 27", "framework": "EU_Charter", "ref": "EU Charter Art. 47", "topic": "Fundamental Rights Impact Assessment"})
    if "article_6" in ids or "annex_I" in ids:
        out.append({"cite": "Article 6(1)", "framework": "MDR_IVDR", "ref": "MDR (EU) 2017/745 / IVDR (EU) 2017/746", "topic": "Safety Components & Harmonised Sectoral Conformity Assessment"})
    return out


def render_kg_context(refs: list[str], question: str = "") -> list[str]:
    """Render graph context as NON-CITABLE Stage-2 prompt additions."""
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
        subpoints = fetch_subpoint_detail(refs)
    except Exception:  # noqa: BLE001
        subpoints = []
    sp_lines = []
    for sp in subpoints:
        text = _flat(sp.get("text"), unit_chars)
        if text:
            roman = str(sp.get("roman") or "").strip().lower()
            if not roman:
                sid = str(sp.get("sid") or "").strip()
                match = re.search(r"(?:^|[_\-.])([ivxlcdm]+)$", sid, re.IGNORECASE)
                roman = match.group(1).lower() if match else ""
            coordinate = (
                f"{sp.get('cite')}, paragraph {sp.get('para')}, "
                f"point ({sp.get('letter')})"
            )
            if roman:
                coordinate += f", subpoint ({roman})"
            sp_lines.append(f"- {coordinate}: {text}")
    if sp_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH SUB-POINT DETAIL "
            "(nested enumerated text attached to the provisions above; use the "
            "full paragraph/point/subpoint coordinate when interpreting it. "
            "This structural label does not itself assert a condition, exception "
            "or legal effect):\n"
            + "\n".join(sp_lines)
        )

    try:
        deontics = fetch_deontic_context(refs)
    except Exception:  # noqa: BLE001
        deontics = []
    deontic_lines = []
    for d in deontics:
        cite = str(d.get('cite') or "").strip()
        pieces = []
        if d.get('practices') and any(x for x in d['practices'] if x):
            pieces.append(f"Prohibited practices: {', '.join(x for x in d['practices'] if x)}")
        if d.get('annex_iii') and any(x for x in d['annex_iii'] if x):
            pieces.append(f"Annex III categories: {', '.join(x for x in d['annex_iii'] if x)}")
        if d.get('roles') and any(x for x in d['roles'] if x):
            pieces.append(f"Operator roles: {', '.join(x for x in d['roles'] if x)}")
        if d.get('phases') and any(x for x in d['phases'] if x):
            pieces.append(f"Lifecycle phases: {', '.join(x for x in d['phases'] if x)}")
        if pieces:
            deontic_lines.append(f"- {cite}: " + "; ".join(pieces))
    if deontic_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH REGULATORY CLASSIFICATION "
            "(role duties, risk categories and lifecycle phases attached to the "
            "provisions above — non-citable structural context):\n"
            + "\n".join(deontic_lines)
        )
    try:
        cross_reg = fetch_cross_regulatory_context(refs)
    except Exception:  # noqa: BLE001
        cross_reg = []
    cr_lines = [
        f"- {item.get('cite')}: {item.get('framework')} ({item.get('ref')}) — {item.get('topic')}"
        for item in cross_reg if item.get('cite')
    ]
    if cr_lines:
        parts.append(
            "\nKNOWLEDGE-GRAPH CROSS-REGULATORY MAPPINGS "
            "(framework mappings to GDPR, EU Charter, MDR/IVDR — non-citable context):\n"
            + "\n".join(cr_lines)
        )

    try:
        parts.extend(_render_semantic_layers(question, refs))
    except Exception:  # noqa: BLE001 — the graph must never break an answer
        logger.debug("kg_context: semantic layer render failed", exc_info=True)

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

    if any(
        marker in part
        for part in parts
        for marker in (
            "KNOWLEDGE-GRAPH QUESTION-FOCUSED SUB-PROVISIONS",
            "KNOWLEDGE-GRAPH DEFINITIONS",
            "KNOWLEDGE-GRAPH RECITAL CONTEXT",
        )
    ):
        max_chars = _int_env(
            "REGENOLD_KG_SEMANTIC_MAX_CHARS", _DEFAULT_SEMANTIC_MAX_CHARS, 1200, 60000
        )
    else:
        max_chars = _int_env("REGENOLD_KG_MAX_CHARS", _DEFAULT_MAX_CHARS, 1200, 60000)
    parts, dropped = _budget_context_parts(parts, max_chars)

    if parts:
        try:
            from app.integrations.regenold.reasoning_trace import (  # noqa: PLC0415
                record_note,
            )
            note = f"kg_context sections={len(parts)} refs={len(refs or [])}"
            if dropped:
                note += f" dropped_over_budget={dropped}"
            record_note(note)
        except Exception:  # noqa: BLE001
            pass
    return parts
