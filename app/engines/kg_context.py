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
#: Upper bound for ``REGENOLD_KG_MAX_REFS``, declared once. R416: the two
#: readers of this knob had drifted, so a value of 21-24 was silently clamped on
#: the keyword reads but honoured on the focused-subprovision read. The pre-R416
#: ceilings were 10 in ``graph_semantic`` and 20 here, so unifying them at 24 is
#: NOT inert above 10 — an operator setting 11-24 now feeds more provisions into
#: ``fetch_focused_subprovisions`` than before (at the default 8 nothing moves).
#: R418: ``graph_semantic`` now reads the knob through the SAME ``_adaptive_int``
#: helper the keyword reads use, so the two layers agree on ``max_refs`` even
#: when the HyPA router scales ``kg_max_keywords``.
_MAX_REFS_CEILING = 24
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


def _kg_deontic_enabled() -> bool:
    """``REGENOLD_KG_DEONTIC`` — DEFAULT OFF (R330 Z3a).

    :data:`_DEONTIC_CYPHER` ends ``LIMIT $limit`` but the caller bound only
    ``{"ids": ids}``, so live Aura answered
    ``Neo.ClientError.Statement.ParameterMissing``,
    :meth:`GraphClient.execute_read` swallowed it and returned ``[]``, and
    :func:`_bounded_execute_read` then took its **success** branch — the
    failure was invisible to the circuit breaker and to telemetry, and the
    empty result was memoized. The ``KNOWLEDGE-GRAPH REGULATORY
    CLASSIFICATION`` block has therefore **never rendered in production**,
    while still costing a measured **130-158 ms of Aura round-trip per
    request**.

    The missing parameter is bound below so the query is correct when someone
    flips this on, but the flip is NOT zero-risk: it injects Annex III
    category labels, operator roles and Art. 113 application dates (whose
    prose names ``Annex I``, ``Article 4``, ``Article 5``) into the prompt on
    rows that retrieved none of them — a live over-citation vector on Ref
    Conciseness, the axis we are losing. So the call ships OFF: output is
    byte-identical to today and the wasted round-trip disappears.
    """
    return os.getenv("REGENOLD_KG_DEONTIC", "0").strip().lower() in (
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

# R380 — Point nodes carry ``.letter`` (421/421 on the live graph, per the
# seeder's ``_MERGE_POINT``/``pt.letter``), never ``.number``. Selecting bare
# ``pt.number AS letter`` always returned null, so the R330 "Z2" renderer
# guard (below, in ``render_kg_context``) silently omitted the point segment
# on every sub-point coordinate instead of restoring it. ``coalesce(...,
# pt.number)`` keeps the query defensive if a future seed ever sets the other
# property. ``sp.roman AS roman`` was already correct — SubPoint carries
# ``.roman`` (``_MERGE_SUBPOINT``), never ``.number``.
#
# R408 — the inner ``MATCH (pt)-[:HAS_SUBPOINT]->(sp)`` required a SubPoint,
# but the live graph has 421 Points (all with ``.text``) and only 37
# SubPoints, so every point WITHOUT one — all of Article 25(1), most of
# Article 13(3) — never reached Stage-2. The sub-point hop is now OPTIONAL and
# a bare point contributes its own text.
#
# R409 — R408 kept ONE global ``LIMIT $max_units`` under ``ORDER BY cite``.
# ``"Annex" < "Article"`` and Annex III alone has 24 point rows, the default
# budget, so any context citing Annex III lost EVERY Article's point text.
# Measured on live Aura over the R407 official-110 refs: a cited provision's
# point text was evicted on 42 of the 97 rows that have any, and on 14 rows it
# removed text the pre-R408 query had delivered (Article 5 on 7 of them). Rows
# now carry the caller's ref order and the budget is shared in Python by
# ``_allocate_units``. The ceiling only guards against a runaway seed: the
# whole graph holds 449 such rows.
#
# Both behaviours sit behind ``REGENOLD_KG_POINT_TEXT`` (**default ON since R416**):
# OFF is now the opt-out and runs ``_SUBPOINT_CYPHER_LEGACY``, the exact pre-R408
# query. See ``_kg_point_text_enabled`` for the paired reading that flipped it.
_SUBPOINT_ROW_CEILING = 600

_SUBPOINT_CYPHER_LEGACY = """
UNWIND $ids AS aid
MATCH (a) WHERE a.id = aid AND (a:Article OR a:Annex)
MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)-[:HAS_POINT]->(pt:Point)-[:HAS_SUBPOINT]->(sp:SubPoint)
RETURN coalesce(a.strict_citation, a.id) AS cite,
       p.number AS para,
       coalesce(pt.letter, pt.number) AS letter,
       sp.id AS sid,
       sp.roman AS roman,
       sp.text AS text
ORDER BY cite, toIntegerOrNull(p.number), letter, sid
LIMIT $max_units
"""


_KG_TURN_COUNT_VAR: ContextVar[int | None] = ContextVar(
    "kg_render_turn_count", default=None
)


def set_render_turn_count(history_turn_count: int | None):
    """R416 — scope the render to the request's modality; returns a token.

    ``_kg_point_text_enabled`` is a leaf decision consumed by a function
    (``fetch_subpoint_detail``) that NINE test fakes monkeypatch with a
    one-argument lambda, so a new keyword on that seam would be swallowed by
    ``render_kg_context``'s ``except Exception`` and silently degrade the block
    to empty. A ``ContextVar`` — the mechanism this module already uses for the
    render memo — carries the conversation depth across every intermediate
    layer without changing any signature. Mirror it with
    :func:`reset_render_turn_count` in a ``finally``.
    """
    return _KG_TURN_COUNT_VAR.set(history_turn_count)


def reset_render_turn_count(token) -> None:
    """Undo :func:`set_render_turn_count`."""
    _KG_TURN_COUNT_VAR.reset(token)


def _kg_point_text_enabled(history_turn_count: int | None = None) -> bool:
    """``REGENOLD_KG_POINT_TEXT`` — R408/R409 point text in the sub-point block.

    **DEFAULT ON since R416** (deny-list, like the repo's other default-ON gates:
    only an explicit ``0``/``false``/``no``/``off`` selects the legacy query).
    ON: every Point reaches the block (a bare point carries its own text) and the
    unit budget is shared across the cited provisions. OFF: the pre-R408 query,
    which only returns points that carry a SubPoint.

    R416 flipped it on a paired read of the reconstructed official gold, over the
    rows Stage-2 actually answers, both arms tunnel-served, wrapper judge
    ``claude-sonnet-5`` at temp 0.1 with 3 repeats
    (``docs/measurements/r415/official-lever-paired-kgpt.json``, 25 paired rows):

    | axis | OFF | ON | delta |
    | :--- | ---: | ---: | ---: |
    | ans_correctness_loose | 96.6 | 98.9 | **+2.3** |
    | ans_correctness_strict | 88.0 | 96.0 | **+8.0** |
    | ans_conciseness | 47.8 | 44.5 | -3.3 |
    | ref_correctness_loose | 100.0 | 100.0 | 0.0 |
    | ref_correctness_strict | 70.8 | 70.8 | 0.0 |
    | ref_conciseness | 51.6 | 52.2 | +0.6 |
    | regulatory_tone | 60.0 | 60.0 | 0.0 |
    | resp_speed | 70.4 | 71.3 | +0.9 |
    | **OVERALL (geo mean)** | 70.7 | **71.3** | **+0.6** |

    The two preconditions this docstring used to name are met: `ref_loose` is
    unchanged at **100.0** on both arms, so no expected head is dropped (hard rule
    #8), and Speed moves UP (mean latency 29.6 s -> 28.7 s). The correctness gain
    has a named mechanism rather than being a swing: the only two rows that
    changed are ``rg_010`` (4/5 -> 5/5, the *aim* clause of Art. 14) and
    ``rg_045`` (3/4 -> 4/4, the scope of "without undue delay") — exactly the two
    the R415 system-prompt compression had broken — and a reach probe over the
    same 26 rows shows the block changing on **23** of them (units 26 -> 384, text
    5,201 -> 81,391 chars) with the legacy query returning **0** units for
    ``rg_010``.

    The cost is answer length (mean 1,425 -> 1,543 chars), which is where the
    -3.3 pp of conciseness comes from.

    R419 RE-SCORE — THE +8.0 IS A SINGLE-DRAW PAIR, NOT A REPRODUCIBLE GAIN
    ---------------------------------------------------------------------
    The whole answer-correctness movement above is the same two criteria:
    across all 25 paired rows (87 criteria) exactly ``rg_010``'s *aim* limb and
    ``rg_045``'s "without undue delay" limb changed, which is both the +8.0 pp of
    strict and the +2.3 pp of loose (2/87). Neither survives resampling
    (``docs/measurements/r418/kg_lever_ans_strict_repro.py``):

    * ``rg_045`` — the judge credited the limb in only 2 of its own 3 repetitions
      (``F T T``), so the row's strict verdict is draw-dependent. The arm's
      published min-max bound on Ans Strict (92.0-96.0) is this one row.
    * ``rg_010`` — judge-stable on that pair, but **10 fresh generations per arm**
      credit the aim limb at the SAME rate on both arms (KG=0 3/5, KG=1 3/5;
      9/15 atomic judge draws each). The 4/5 vs 5/5 was two draws from one
      distribution.

    Re-scored on the surviving rows, Ans Strict is **95.65 vs 95.65 (+0.0 pp)** and
    Ans Loose is **98.72 vs 98.72 (+0.0 pp)**.

    Nor is the -3.3 pp conciseness "cost" above a measured cost. It is answer
    length, and on the same 25 paired rows the ON arm is longer on only **14 of
    25** (mean 1,426 -> 1,543 chars; sign-test p=0.69, Wilcoxon p=0.23) — a few
    large rows move the mean, and the resample above shows one row returning
    450-1,492 chars at FIXED input and arm, so a mean-only reading is unsafe.
    Substituting the corrected correctness axes into the published board moves the
    combined Overall from +0.6 pp to -0.42 pp, but that residual is itself this
    unsupported length difference: **on this corpus, every axis of this lever is
    within single-draw noise.** The deterministic reach evidence below stands
    unchanged (it describes what the flag puts in the prompt, not what it scored),
    and so does the hard-split scope: that read is independent of this one.

    CONSEQUENCE FOR THE DEFAULT: this audit does not support - or refute - the
    flip. It removes the measured JUSTIFICATION for it; the case for ON now rests
    on the grounding evidence (the legacy query returns 0 units for bare points
    such as those carrying Art. 5(1)(a)-(h)) rather than on a scored gain, and the
    case for OFF rests on the same absence. Do not requote the +8.0.

    R416 HARD-SPLIT READ — THE LEVER IS MODALITY-RESTRICTED
    ------------------------------------------------------
    R416's residual named this gate and its revert. It was run (paired, 32
    tunnel-served rows after the symmetric fallback exclusion, floor 30, both
    arms served by the primary wrapper transport; wrapper judge, 3 repeats):

    | axis | OFF | ON | delta |
    | :--- | ---: | ---: | ---: |
    | ref_correctness_loose | 80.21 | 75.52 | **-4.69** |
    | ref_correctness_strict | 43.18 | 40.24 | -2.95 |
    | ref_conciseness | 22.19 | 19.85 | -2.34 |
    | regulatory_tone | 100.0 | 100.0 | 0.0 |
    | keyword_recall | 81.25 | 79.69 | -1.56 |
    | **gold_dropped_head** | **12** | **14** | **+2** |

    HARD RULE #8 FAILS on the hard split: the branch newly drops ``Article 5``
    (mt_v4:001), ``Article 51`` (mt_v2:008), ``Article 113`` (mt_v2:020) and
    ``Article 24`` (mt_v2:025) — turn-1 expected heads the adversarial pushback
    is graded on keeping. Six of 32 rows moved and only three of those moves were
    favourable, so this is not a swing that averages out: it is the same failure
    mode (gold loss) that the R415 lever had to be modality-scoped for.

    The easy board says the opposite (+8.0 ans_correctness_strict, +0.6 overall,
    ``ref_loose`` flat at 100.0 on 25 paired rows). Both readings are real, and
    they are not in conflict once the predicate is added: the easy board is
    SINGLE-TURN and the loss is on multi-turn pushbacks. So the lever is scoped
    by modality exactly as its sibling
    ``REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`` is — ON requires a KNOWN turn
    count ``<= 1``, and an explicit multi-turn count selects the legacy query,
    which is byte-identical to ``REGENOLD_KG_POINT_TEXT=0`` and therefore
    reproduces the measured baseline arm above.

    ``history_turn_count=None`` means the count was not threaded. It keeps the
    shipped default ON so that entry points which do not thread a conversation
    (``logic_rag``, direct engine calls, tests) are unchanged by this scoping.
    ``REGENOLD_KG_POINT_TEXT_SINGLE_TURN=0`` removes the restriction (the
    pre-R416 unconditional behaviour, which the hard gate above falsifies).
    """
    if os.getenv("REGENOLD_KG_POINT_TEXT", "1").strip().lower() in (
        "0", "false", "no", "off",
    ):
        return False
    unrestricted = os.getenv(
        "REGENOLD_KG_POINT_TEXT_SINGLE_TURN", "1"
    ).strip().lower() in ("0", "false", "no", "off")
    if unrestricted:
        return True
    if history_turn_count is None:
        history_turn_count = _KG_TURN_COUNT_VAR.get()
    if history_turn_count is None:
        return True
    return history_turn_count <= 1

_SUBPOINT_CYPHER = """
UNWIND range(0, size($ids) - 1) AS i
WITH i, $ids[i] AS aid
MATCH (a) WHERE a.id = aid AND (a:Article OR a:Annex)
MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)-[:HAS_POINT]->(pt:Point)
OPTIONAL MATCH (pt)-[:HAS_SUBPOINT]->(sp:SubPoint)
RETURN i AS ref_index,
       coalesce(a.strict_citation, a.id) AS cite,
       p.number AS para,
       coalesce(pt.letter, pt.number) AS letter,
       sp.id AS sid,
       sp.roman AS roman,
       coalesce(sp.text, pt.text) AS text
ORDER BY ref_index, toIntegerOrNull(p.number), letter, sid
LIMIT $max_rows
"""


def _allocate_units(rows: list[dict], max_units: int) -> list[dict]:
    """Share ``max_units`` round-robin across cited provisions, in ref order.

    ``rows`` arrive grouped by ``ref_index`` (the caller's, reranked, ref order)
    and in document order within a provision. One unit is taken from each
    provision per round until the budget is spent, so no cited provision is
    starved by a long one, and the kept units are emitted grouped by provision.
    Rows without ``ref_index`` fall into one group, which degrades to a plain
    ``rows[:max_units]``.
    """
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(int(row.get("ref_index") or 0), []).append(row)
    order = sorted(groups)
    kept = dict.fromkeys(order, 0)
    budget = max(0, int(max_units))
    progressed = True
    while budget and progressed:
        progressed = False
        for k in order:
            if budget and kept[k] < len(groups[k]):
                kept[k] += 1
                budget -= 1
                progressed = True
    return [row for k in order for row in groups[k][: kept[k]]]

# R428 — the cite fallback must branch on WHICH node family matched.
#
# R426 widened the MATCH to admit legacy ``ART<N>`` shadow nodes alongside the
# canonical ``article_<N>`` ones, and applied the shadow-only id transform to the
# RETURN unconditionally. ``substring('article_6', 3)`` is ``'icle_6'``, so any
# matched node without ``strict_citation`` rendered as the non-provision label
# **"Article icle_6"** into the Stage-2 context (measured; the canonical nodes get
# ``strict_citation`` from the seeder, so this is latent today and wrong the
# moment a node is missing it). The transform is now guarded by the same family
# test the MATCH uses, and canonical nodes fall back to the value they always did.
#
# WHAT THE WIDENED MATCH IS AND IS NOT (R428, measured live on Aura). It is a
# compatibility shim, not a data unlock:
#
# * The 17 shadow nodes carry 125 ``REQUIRES`` and 23 ``APPLIES_TO_ROLE`` edges,
#   but this query reads PROHIBITED_UNDER / TRIGGERS_HIGH_RISK_UNDER /
#   HAS_OBLIGATION_ARTICLE / APPLIES_TO, and every one of those counts is **0** on
#   the shadows. So a shadow contributes no annotation a canonical node does not.
# * Two nodes can be eligible for one canonical id, yet the result cannot grow:
#   the projection collects into aggregates keyed on ``cite``, so rows sharing a
#   cite merge. Verified for the 10 ids whose shadows exist — 10 rows unwidened,
#   10 widened, zero differing (``tests/test_sota_legal_kg_ontology.py::
#   test_deontic_widening_cannot_duplicate_a_cite``).
# * Its residual value is the canonical-missing case: a shadow still yields the
#   provision's ``cite`` instead of dropping the row entirely.
#
# The legacy edges themselves stay unread: no live query reads ``REQUIRES`` (the
# schema calls that type deliberately unseeded and R99.1 is the bug it caused) and
# none reads ``APPLIES_TO_ROLE``. Closing that architecture gap is a consumer
# problem, not a query-widening problem.
_DEONTIC_CYPHER = """
CALL () {
    MATCH (a:Article) WHERE a.id IN $ids OR (a.id STARTS WITH 'ART' AND ('article_' + substring(a.id, 3)) IN $ids)
    OPTIONAL MATCH (pr:Practice)-[:PROHIBITED_UNDER]->(a)
    OPTIONAL MATCH (cat:AnnexIIICategory)-[:TRIGGERS_HIGH_RISK_UNDER]->(a)
    OPTIONAL MATCH (ro:OperatorRole)-[hoa:HAS_OBLIGATION_ARTICLE]->(a)
    OPTIONAL MATCH (ph:LifecyclePhase)-[:APPLIES_TO]->(a)
    RETURN coalesce(
               a.strict_citation,
               CASE WHEN a.id STARTS WITH 'ART'
                    THEN 'Article ' + substring(a.id, 3)
                    ELSE a.id END
           ) AS cite,
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


def kg_local_mirror_enabled() -> bool:
    """R376 — in-process hierarchy mirror when Neo4j is offline/timed out. Default ON."""
    return os.getenv("REGENOLD_KG_LOCAL_MIRROR", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


_MIRROR_LOCK = threading.Lock()
_MIRROR_CACHE: dict | None = None


def _unit_sort_key(num) -> int:
    """Numeric sort key matching the Cypher's ``coalesce(toInteger(n), MAXINT)``."""
    try:
        return int(str(num).strip())
    except (TypeError, ValueError):
        return 2147483647


def _cite_for_node(node_id: str) -> str:
    """``article_6`` -> ``Article 6``; ``annex_III`` -> ``Annex III``."""
    nid = (node_id or "").strip()
    if nid.startswith("article_"):
        return f"Article {nid[len('article_'):]}"
    if nid.startswith("annex_"):
        return f"Annex {nid[len('annex_'):]}"
    return nid


def _mirror_index() -> dict:
    """Build (once per process) the ``node_id -> hierarchy`` index."""
    global _MIRROR_CACHE  # noqa: PLW0603
    if _MIRROR_CACHE is not None:
        return _MIRROR_CACHE
    with _MIRROR_LOCK:
        if _MIRROR_CACHE is not None:
            return _MIRROR_CACHE
        index: dict = {}
        try:
            from app.data.provision_hierarchy import (  # noqa: PLC0415
                build_hierarchy_payload,
            )

            payload = build_hierarchy_payload()

            para_by_id = {n["id"]: n for n in payload.paragraph_nodes}
            point_by_id = {n["id"]: n for n in payload.point_nodes}
            subpoint_by_id = {n["id"]: n for n in payload.subpoint_nodes}

            for edge in payload.has_paragraph_edges:
                index.setdefault(
                    edge["source_id"], {"units": [], "subpoints": [], "points": []}
                )
                node = para_by_id.get(edge["target_id"])
                if node is None:
                    continue
                index[edge["source_id"]]["units"].append(
                    {
                        "num": str(node.get("number") or ""),
                        "text": node.get("text") or "",
                        "_id": node["id"],
                    }
                )

            for edge in payload.has_point_edges:
                parent = edge["source_id"]
                node = point_by_id.get(edge["target_id"])
                if node is None:
                    continue
                if parent in index or parent in para_by_id:
                    if parent in para_by_id:
                        continue
                index.setdefault(
                    parent, {"units": [], "subpoints": [], "points": []}
                )
                index[parent]["units"].append(
                    {
                        "num": str(node.get("letter") or node.get("number") or ""),
                        "text": node.get("text") or "",
                        "_id": node["id"],
                    }
                )

            points_by_para: dict[str, list[dict]] = {}
            for edge in payload.has_point_edges:
                node = point_by_id.get(edge["target_id"])
                if node is not None:
                    points_by_para.setdefault(edge["source_id"], []).append(node)
            subs_by_point: dict[str, list[dict]] = {}
            for edge in payload.has_subpoint_edges:
                node = subpoint_by_id.get(edge["target_id"])
                if node is not None:
                    subs_by_point.setdefault(edge["source_id"], []).append(node)

            # R418 — the POINT-level rows, in the shape ``_SUBPOINT_CYPHER``
            # returns. ``subpoints`` below only holds Points that HAVE a
            # SubPoint (37 in the live graph), so a mirror built from it alone
            # could not answer the R409 all-Points query — during an outage the
            # single-turn arm silently reverted to the legacy shape. Bare
            # Points and their text are kept here so the mirror can serve EITHER
            # shape.
            for edge in payload.has_paragraph_edges:
                root, para_id = edge["source_id"], edge["target_id"]
                para = para_by_id.get(para_id)
                if para is None:
                    continue
                for point in points_by_para.get(para_id, []):
                    index.setdefault(
                        root, {"units": [], "subpoints": [], "points": []}
                    )
                    index[root]["points"].append(
                        {
                            "para": str(para.get("number") or ""),
                            "letter": str(
                                point.get("letter") or point.get("number") or ""
                            ),
                            "pid": point.get("id") or "",
                            "text": point.get("text") or "",
                        }
                    )
                    for sub in subs_by_point.get(point["id"], []):
                        index.setdefault(
                            root, {"units": [], "subpoints": [], "points": []}
                        )
                        index[root]["subpoints"].append(
                            {
                                "para": str(para.get("number") or ""),
                                "letter": str(point.get("letter") or ""),
                                "roman": str(sub.get("roman") or ""),
                                "sid": sub.get("id") or "",
                                "text": sub.get("text") or "",
                            }
                        )
        except Exception:  # noqa: BLE001
            # R418 — do NOT cache the failure. ``_MIRROR_CACHE = {}`` made a
            # single transient fault permanent: a boot-order import problem or
            # one malformed node returned ``[]`` for the rest of the process
            # while the warning was logged once, so the mirror silently stopped
            # being a fallback at all. Not caching re-attempts the build on the
            # next consult; the mirror is only ever consulted after a real graph
            # read failure, so the retry cannot slow a healthy request.
            logger.warning(
                "kg_context: local hierarchy mirror unavailable (will retry)",
                exc_info=True,
            )
            return {}
        _MIRROR_CACHE = index
        return _MIRROR_CACHE


def _mirror_note(kind: str, n: int) -> None:
    """Record that the mirror, not Aura, supplied a layer."""
    logger.info("kg_context.local_mirror_served layer=%s rows=%d", kind, n)
    try:
        from app.integrations.regenold.reasoning_trace import (  # noqa: PLC0415
            record_note as _rn,
        )
        _rn(f"kg_local_mirror_served layer={kind} rows={n}")
    except Exception:  # noqa: BLE001
        pass


def _mirror_hierarchy(ids: list[str], max_units: int) -> list[dict]:
    """Hierarchy rows for ``ids`` from the in-process mirror, Cypher-shaped."""
    index = _mirror_index()
    if not index:
        return []
    out: list[dict] = []
    for node_id in ids:
        entry = index.get(node_id)
        if not entry or not entry["units"]:
            continue
        units = sorted(
            entry["units"],
            key=lambda u: (_unit_sort_key(u.get("num")), str(u.get("num") or "")),
        )[:max_units]
        out.append(
            {
                "id": node_id,
                "cite": _cite_for_node(node_id),
                "title": None,
                "units": [{"num": u["num"], "text": u["text"]} for u in units],
            }
        )
    return out


def _mirror_point_units(ids: list[str], max_units: int) -> list[dict]:
    """``_SUBPOINT_CYPHER``-shaped rows from the in-process mirror (R418).

    One row per Point, and per SubPoint where the Point has any — the same
    ``OPTIONAL MATCH … coalesce(sp.text, pt.text)`` semantics the R409 query
    has, including the ``ref_index`` the round-robin allocator groups on. During
    an Aura outage this is what the single-turn arm must be served; reverting it
    to :func:`_mirror_subpoints` (SubPoint rows only, greedy fill in ref order)
    shipped a different prompt and re-introduced the R408 "a long first
    provision evicts the rest" defect.
    """
    index = _mirror_index()
    if not index:
        return []
    rows: list[dict] = []
    for ref_index, node_id in enumerate(ids):
        entry = index.get(node_id)
        if not entry:
            continue
        cite = _cite_for_node(node_id)
        subs_by_point: dict[tuple[str, str], list[dict]] = {}
        for sub in entry.get("subpoints", ()):
            subs_by_point.setdefault(
                (str(sub.get("para") or ""), str(sub.get("letter") or "")), []
            ).append(sub)
        for point in sorted(
            entry.get("points", ()),
            key=lambda p: (_unit_sort_key(p.get("para")), str(p.get("letter") or "")),
        ):
            para = str(point.get("para") or "")
            letter = str(point.get("letter") or "")
            point_text = str(point.get("text") or "")
            subs = sorted(
                subs_by_point.get((para, letter), []),
                key=lambda sp: (
                    _unit_sort_key(sp.get("para")),
                    str(sp.get("letter") or ""),
                    str(sp.get("sid") or ""),
                ),
            )
            if not subs:
                rows.append(
                    {
                        "ref_index": ref_index,
                        "cite": cite,
                        "para": para,
                        "letter": letter,
                        "sid": None,
                        "roman": None,
                        "text": point_text,
                    }
                )
                continue
            for sub in subs:
                rows.append(
                    {
                        "ref_index": ref_index,
                        "cite": cite,
                        "para": str(sub.get("para") or para),
                        "letter": str(sub.get("letter") or letter),
                        "sid": sub.get("sid") or None,
                        "roman": sub.get("roman") or None,
                        "text": str(sub.get("text") or "") or point_text,
                    }
                )
    return _allocate_units(rows, max_units)


def _mirror_subpoints(ids: list[str], limit: int) -> list[dict]:
    """Sub-point rows for ``ids`` from the in-process mirror, Cypher-shaped."""
    index = _mirror_index()
    if not index:
        return []
    out: list[dict] = []
    for node_id in ids:
        entry = index.get(node_id)
        if not entry:
            continue
        cite = _cite_for_node(node_id)
        for sub in sorted(
            entry["subpoints"],
            key=lambda sp: (
                _unit_sort_key(sp.get("para")),
                str(sp.get("letter") or ""),
                str(sp.get("sid") or ""),
            ),
        ):
            out.append({"cite": cite, **sub})
            if len(out) >= limit:
                return out
    return out


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
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, _MAX_REFS_CEILING)
    max_units = _adaptive_int("kg_max_units", "REGENOLD_KG_MAX_UNITS", _DEFAULT_MAX_UNITS, 1, 100)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    cache_key = f"h:{','.join(ids)}:u{max_units}"
    rows = _memoized_read(
        cache_key,
        _HIERARCHY_CYPHER,
        {"ids": ids, "max_units": max_units},
    )
    # R418 — consult the local mirror ONLY on a real read failure. ``_ReadRows``
    # carries ``failed`` precisely to tell an error apart from an empty match,
    # and a healthy empty result is a legitimate answer. The old guard
    # (``if rows and not failed``) treated ``[]`` from a WORKING graph as an
    # outage, so the mirror — built from the in-process regex parser, not the
    # seeded graph — served text the graph does not hold, and logged it as
    # ``kg_local_mirror_served``. That silently mixes two prompt shapes into any
    # A/B that spans an ordinary empty match.
    if not getattr(rows, "failed", False):
        return list(rows)
    if not kg_local_mirror_enabled():
        return list(rows)
    mirrored = _mirror_hierarchy(ids, max_units)
    if mirrored:
        _mirror_note("hierarchy", len(mirrored))
    return mirrored


def fetch_recital_anchors(refs: list[str]) -> list[dict]:
    """Interpretive recitals for cited provisions."""
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, _MAX_REFS_CEILING)
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


def fetch_subpoint_detail(
    refs: list[str], *, history_turn_count: int | None = None
) -> list[dict]:
    """Sub-point detail (paragraph -> point -> subpoint) for cited provisions.

    ``history_turn_count`` selects the query shape through
    :func:`_kg_point_text_enabled`: the R409 all-Points query on single-turn
    asks, the pre-R408 ``_SUBPOINT_CYPHER_LEGACY`` on multi-turn ones. When it
    is ``None`` the modality comes from :func:`set_render_turn_count`.
    """
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, _MAX_REFS_CEILING)
    max_units = _adaptive_int("kg_max_units", "REGENOLD_KG_MAX_UNITS", _DEFAULT_MAX_UNITS, 1, 100)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    if not _kg_point_text_enabled(history_turn_count):
        rows = _memoized_read(
            f"sp:{','.join(ids)}:u{max_units}",
            _SUBPOINT_CYPHER_LEGACY,
            {"ids": ids, "max_units": max_units},
        )
    else:
        # The R409 query does not depend on ``max_units``, so the memo holds the
        # full per-provision rows and the budget is applied after it.
        rows = _memoized_read(
            f"spt:{','.join(ids)}",
            _SUBPOINT_CYPHER,
            {"ids": ids, "max_rows": _SUBPOINT_ROW_CEILING},
        )
        if not getattr(rows, "failed", False):
            return _ReadRows(
                _allocate_units(rows, max_units), failed=False
            )
        # R418 — the ON branch's outage path must answer in the SAME shape. It
        # used to fall through to ``_mirror_subpoints``, which emits SubPoint
        # rows only (the pre-R408 legacy shape) and fills them greedily in ref
        # order, so a single-turn ask during an Aura outage silently received
        # the LEGACY block — a different Stage-2 prompt, logged only as
        # ``kg_local_mirror_served``.
        if not kg_local_mirror_enabled():
            return list(rows)
        mirrored_points = _mirror_point_units(ids, max_units)
        if mirrored_points:
            _mirror_note("subpoint_points", len(mirrored_points))
        return mirrored_points or list(rows)
    # R418 — same rule as ``fetch_provision_hierarchy``: a healthy empty match
    # is an answer, not an outage. This one matters most on MULTI-TURN asks,
    # where the legacy query legitimately returns no rows for the bare Points
    # (the live graph holds 421 Points and 37 SubPoints), so the mirror used to
    # inject unrequested text into the exact arm the R416 gate measured as
    # "byte-identical to REGENOLD_KG_POINT_TEXT=0".
    if not getattr(rows, "failed", False):
        return list(rows)
    if not kg_local_mirror_enabled():
        return list(rows)
    mirrored = _mirror_subpoints(ids, max_units)
    if mirrored:
        _mirror_note("subpoint", len(mirrored))
    return mirrored


def fetch_deontic_context(refs: list[str]) -> list[dict]:
    """Regulatory classifications attached to cited provisions."""
    if not kg_context_enabled():
        return []
    max_refs = _adaptive_int("kg_max_keywords", "REGENOLD_KG_MAX_REFS", _DEFAULT_MAX_REFS, 1, _MAX_REFS_CEILING)
    ids = _node_ids(refs, limit=max_refs)
    if not ids:
        return []

    # R330 Z3 — ``_DEONTIC_CYPHER`` ends ``LIMIT $limit``; binding only ``ids``
    # made every live execution a ``ParameterMissing`` error. Reuse ``max_refs``
    # (the query emits one row per article, so it is capped by refs — NOT by
    # ``max_units``), and fold it into the cache key so a changed budget cannot
    # be served from a memo taken under the old one.
    cache_key = f"de:{','.join(ids)}:l{max_refs}"
    return _memoized_read(
        cache_key,
        _DEONTIC_CYPHER,
        {"ids": ids, "limit": max_refs},
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
        # R416 — never swallow silently: a signature mismatch at this seam
        # degrades the whole point-text block to empty, which reads as "the
        # graph had nothing" rather than "the call failed".
        logger.debug("kg_context subpoint render failed", exc_info=True)
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
            # R330 Z2 — a SubPoint whose parent Point carries no letter used to
            # render the literal string ``point (None)``: 39 occurrences across
            # 7 of the 15 captured failing Stage-2 prompts, including
            # july7-221's ``Article 5, paragraph 1, point (None), subpoint
            # (ii)`` — exactly the coordinate the judge says that answer
            # misstated. Emit the point segment only when there is a letter.
            coordinate = f"{sp.get('cite')}, paragraph {sp.get('para')}"
            letter = str(sp.get("letter") or "").strip()
            if letter:
                coordinate += f", point ({letter})"
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
        # R330 Z3a — gated OFF by default. The block has never rendered (see
        # `_kg_deontic_enabled`), so skipping the call is output-identical and
        # removes 130-158 ms of Aura round-trip from every request.
        deontics = fetch_deontic_context(refs) if _kg_deontic_enabled() else []
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
