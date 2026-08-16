"""R327 — read EVERY seeded Neo4j vector index, each at the layer where it is safe.

The Aura instance carries **seven** ONLINE, fully-populated 128-dimensional
vector indexes (measured 2026-08-10 against ``0644b854``):

    v_article_embedding      113 nodes      <- read by app/engines/vector_recall.py
    v_annex_embedding         13 nodes      <- read by app/engines/vector_recall.py
    v_paragraph_embedding    658 nodes      <- was DARK
    v_point_embedding        421 nodes      <- was DARK
    v_subpoint_embedding      37 nodes      <- was DARK
    v_definition_embedding    68 nodes      <- was DARK
    v_recital_embedding      180 nodes      <- was DARK

Only the first two were ever queried, i.e. 126 of 1,490 embeddings — about 8% of
the seeded semantic surface. This module reads the other five.

WHY THE ACCESS MODE DIFFERS PER LAYER
-------------------------------------
Node embeddings are TF-IDF -> SVD-128 (``embeddings_index._embed_query``, the
same function the seeder used, so query and node vectors share one subspace).
Measured open-domain, that signal is WEAK: scores sit in 0.5-0.88 whether the hit
is right or wrong, so there is no discriminative margin. Two examples from the
live instance:

    "Is social scoring by a public authority allowed?"
        -> v_article_embedding rank 1 = Article 77 (0.73). The answer is Art. 5(1)(c).
    "Who counts as a deployer?"
        -> v_definition_embedding ranks def_provider (0.629) ABOVE def_deployer (0.615).

That is consistent with what CLAUDE.md already records: the R325 lexical re-ranker
was measured dead (best AUC 0.641 vs ``rank``'s 0.703), and dense rerank / RRF
fusion measured as washes three times. So this module does NOT use these indexes
as an open-domain retriever feeding citations.

Instead:

* **Paragraph / Point / SubPoint** are queried by ANN and then CONSTRAINED to
  units hanging off provisions the route ALREADY cites. That turns a weak
  open-domain retrieval into a strong within-provision selection — the candidate
  set is already grounded, so precision rises and citation drift is impossible.
  Measured on the live instance: Art. 50 -> 50(5), 50(3); Art. 12 -> 12(1) at
  0.891; Art. 5 -> the 5(1)(c) social-scoring sub-points.
* **Definition / Recital** are queried open-domain but are STRUCTURALLY
  NON-CITABLE. A recital is never a wire citation (hard rule #1 permits only
  ``Article N`` / ``Annex X``), and definitions are rendered as definitional
  background. Their weak precision therefore costs context budget, never a
  reference. Each gets its OWN quota so the higher-scoring layer cannot crowd
  the other out (recitals score ~0.70 vs definitions ~0.62, so a shared LIMIT
  returned zero definitions in every probe).

This also replaces a structurally dead query. ``kg_context.fetch_recital_anchors``
walks ``HAS_RECITAL_ANCHOR``, and the live graph has **5 such edges in total**
(article_5 -> recitals 18/30/31/44, article_52 -> recital 112), so 111 of 113
articles get no recital context at all while 180 embedded recitals sit unread.

SAFETY
------
* Everything here is **non-citable Stage-2 context**, per hard rule #10.
* ``_render_supplementary_sections(..., include_kg=False)`` is what mines the
  citation-drift allowlist, and it excludes these blocks — so adding layers
  cannot widen that allowlist (the R323 failure mode).
* Two bounded reads total, through ``kg_context._bounded_execute_read``, so the
  existing graph timeout budget and circuit breaker apply unchanged.
* Default **ON** as of R327.1, but only the CONSTRAINED half:
  ``REGENOLD_GRAPH_SEMANTIC_LAYERS=1`` with ``REGENOLD_SEMANTIC_GLOSS=0``. The
  grounded judge measured constrained-only at citation faithfulness 0.900 ->
  0.960 with reference precision back at baseline, while running the open-domain
  half as well cost 0.028 micro precision for no extra gain. Both flags are in
  ``_engine_cache_key``, so an in-process A/B of either is real.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

__all__ = [
    "semantic_layers_enabled",
    "gloss_layers_enabled",
    "semantic_coordinates_enabled",
    "coordinate_for_row",
    "fetch_focused_subprovisions",
    "fetch_definition_and_recital_context",
]

_DEFAULT_MIN_SIM = 0.30
#: ANN fan-out per index before the provision constraint is applied. The
#: constraint is selective, so the fan-out has to be wide enough that units of a
#: cited provision actually appear in the global top-k.
_DEFAULT_ANN_FANOUT = 60
_DEFAULT_UNITS_KEPT = 16
#: Max units drawn from any ONE cited provision, so a single provision cannot
#: consume the whole focused block (see the B.2 roll-up note on _FOCUS_CYPHER).
_DEFAULT_UNITS_PER_PROVISION = 2
_DEFAULT_DEFINITIONS_KEPT = 3
_DEFAULT_RECITALS_KEPT = 3


def gloss_layers_enabled() -> bool:
    """``REGENOLD_SEMANTIC_GLOSS`` — the OPEN-DOMAIN half. Default **OFF**.

    R327 gate result. The grounded judge over 50 live rows separated the two block
    families by sign:

    * the CONSTRAINED block (paragraph/point/subpoint, filtered to already-cited
      provisions) carries the win — citation faithfulness 0.900 -> 0.960 net +3,
      outright incorrect answer claims 5 -> 1 — and cannot introduce a citation at
      all, since every candidate already belongs to a cited provision;
    * the OPEN-DOMAIN blocks (definitions, recitals) carry the cost — wrong refs
      51 -> 55 at an unchanged reference count.

    ⚠ The obvious MECHANISM for that cost is falsified. Only **1 of 13** added
    wrong refs is actually named inside a rendered definition/recital block; 10
    appear in the layers-ON prose and in no gloss block. And the shape is
    SUBSTITUTION, not inflation: 131 -> 132 total refs but 4 more wrong and 3
    fewer correct (rg_020 went ['Article 74','Article 16','Article 10'] ->
    ['Article 26','Article 16'] — count DOWN). So the extra context shifts what
    Stage-2 chooses to discuss, and ``_reconcile_references_to_prose`` follows the
    prose. That is a GENERATION effect, not a plumbing bug — which is why the fix
    is to withhold the block, not to patch a promotion path.

    R327.1 GATE RESULT — measured, not assumed. Grounded judge, 50 live July-7
    rows per arm, all three arms against the same baseline:

                          ans(hist)  ref pass  ref MACRO  ref micro  wrong/total  cite
        layers OFF          0.880      0.380     0.675      0.611      51/131     0.900
        layers ON (both)    0.880      0.360     0.642      0.583      55/132     0.960
        CONSTRAINED ONLY    0.880      0.367     0.657      0.614      49/127     0.960

    Constrained-only keeps the ENTIRE citation-faithfulness win (+3 net, 5 up /
    2 down) while returning micro reference precision to baseline (+0.003) and
    cutting wrong refs 51 -> 49. Running both halves costs 0.028 micro precision
    for no additional gain. So the open-domain half is OFF.

    ⚠ Not significant at n=50 (p=0.453 on the best axis), and it ships 2 fewer
    judge-correct refs (80 -> 78) — with ``gold_coverage = 0.0`` on this batch
    there is no gold term, so hard rule #8's ``gold_dropped`` is UNMEASURED here.
    ``easyhard_ab`` is what can supply it.

    Fresh env read per call (R263.2).
    """
    return os.getenv("REGENOLD_SEMANTIC_GLOSS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def semantic_layers_enabled() -> bool:
    """``REGENOLD_GRAPH_SEMANTIC_LAYERS`` — **R330: default flipped ON -> OFF.**

    ⚠ **This flag has never done anything.** R330 found the only
    ``render_kg_context`` call site in ``app/``
    (``_graph_rag_impl.py``, in ``_render_supplementary_sections``) omitted the
    ``question`` argument, and ``kg_context._render_semantic_layers`` opens with
    ``if not question: return []``. So the constrained vector search below — and
    ``REGENOLD_SEMANTIC_GLOSS``, which lives inside the same function — emitted
    **zero** Stage-2 context on every request since R327, while this flag read
    ON, sat in ``_engine_cache_key``, and was documented as active in CLAUDE.md.

    R330 repairs the wiring (the question is now passed) and flips this default
    to **OFF in the same commit**. That pairing is deliberate:

    * Flipping to OFF is **byte-identical to the behaviour the bug produced**, so
      production is unchanged by this commit and nothing needs re-measuring.
    * Repairing the wiring WITHOUT flipping would silently activate an unmeasured
      feature in production the moment it merged — live Neo4j vector queries per
      request on a scored latency axis, plus extra Stage-2 grounding on the
      answer axes. That is exactly the R308/R299 mistake this project has made
      twice.

    ⚠ **The R327.1 evidence below was collected through the broken path**, so
    treat "faithfulness 0.900 -> 0.960" as UNVERIFIED, not as a reason to flip:
    with the layer inert, both arms of that measurement were the same arm.

    To flip it ON now: set ``REGENOLD_GRAPH_SEMANTIC_LAYERS=1`` and gate on
    ``ab_judge`` (it moves Stage-2 grounding, i.e. the ANSWER axes — not
    ``easyhard_ab``, which is the reference instrument), and watch p50: the graph
    blocks are non-citable (AGENTS.md invariant #3) so this cannot change a wire
    citation, but it can change the answer and it costs Aura round-trips.

    Historical note (R327.1, measured through the dead path — see above): with
    ``REGENOLD_SEMANTIC_GLOSS`` OFF this reads ``v_paragraph_embedding`` /
    ``v_point_embedding`` / ``v_subpoint_embedding`` constrained to
    already-cited provisions. See :func:`gloss_layers_enabled` for that
    three-arm table.

    The flag is in ``_engine_cache_key`` so an in-process A/B of it is real and
    not a cache replay. Fresh env read per call (R263.2).
    """
    return os.getenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def semantic_coordinates_enabled() -> bool:
    """``REGENOLD_SEMANTIC_COORDINATES`` — default **ON**. R329 P2.

    ⚠ DEFAULT FLIPPED ON by operator decision (2026-08-13), UNGATED. Railway's
    ``[deploy.envs]`` has never applied, so a default-OFF flag is dead code in
    production — the only way this reaches the deployment is as a code default.
    Off-switch ``REGENOLD_SEMANTIC_COORDINATES=0`` for instant rollback, and the
    flag stays so ``easyhard_ab`` can still A/B OFF↔ON. The measured baseline in
    CLAUDE.md predates this and no longer describes the running system.

    THE DEFECT THIS GATES. The constrained block exists to attribute a duty to
    the right SUB-provision, yet it could not express a sub-provision citation.
    ``_FOCUS_CYPHER`` walked ``(a)-[:HAS_PARAGRAPH|HAS_POINT|HAS_SUBPOINT*1..3]->
    (node)`` — a path that BINDS every node needed to name the coordinate — and
    then collected only ``{uid, layer, text, score}``, so the renderer emitted

        - Article 12 [paragraph para_12_1]: <text>

    i.e. sub-provision TEXT under a HEAD-level cite, with the legal coordinate
    ``Article 12.1`` thrown away one hop before it was needed.

    WHY IT IS WORTH A FLAG. ``routes/regenold.py:1190-1194`` measures, per
    over-citation cause, what removing it wholesale would cost. The last row:
    references that are THEMSELVES sub-points run 5 wrong : 28 correct — **85%**
    — against an overall reference precision of 0.696. Sub-point grain is the
    most accurate citation shape this system emits, and both the grounded judge
    and easyhard's ``expected_refs`` score at that grain. The *instruction* also
    already ships: ``REGENOLD_SUBPARAGRAPH_ATTRIBUTION`` is default ON, so the
    model is asked for sub-paragraph attribution while the block holding the
    sub-paragraph text withholds its coordinate.

    ⚠ SCOPE — this changes the rendered LABEL only, never citability. The block's
    framing stays "they add NO new provision … do NOT cite anything new here",
    per hard rule #10 (the graph is additive context, never a wire citation).
    Emitting a coordinate AND relaxing the framing would put the graph on the
    wire; that is a separate flag and a separate gate.

    Fresh env read per call (R263.2) — a module-level constant would make the
    in-process A/B inert. NOTE for the orchestrator: this is an ENGINE-level
    flag (it changes the Stage-2 grounding block), so it must also be listed in
    ``_engine_cache_key`` in ``app/routes/regenold.py`` beside
    ``REGENOLD_GRAPH_SEMANTIC_LAYERS``, or the paired A/B replays arm A's cache.
    """
    return os.getenv("REGENOLD_SEMANTIC_COORDINATES", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _float_env(name: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.getenv(name, ""))))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.getenv(name, ""))))
    except (TypeError, ValueError):
        return default


def _adaptive_int(field: str, name: str, default: int, lo: int, hi: int) -> int:
    """R329 — HyPA per-question value for a knob, else the env/default.

    Precedence: explicit env > adaptive > default. Byte-identical to
    :func:`_int_env` when the router is off (the default).
    """
    try:
        from app.engines.query_complexity_router import adaptive_int  # noqa: PLC0415

        return adaptive_int(field, name, default, lo, hi)
    except Exception:  # noqa: BLE001 — never let routing break a graph read
        return _int_env(name, default, lo, hi)


def _adaptive_fanout() -> int:
    """ANN fanout, scaled by the HyPA ``kg_depth`` class when the router is on.

    The paper's ``l`` (max knowledge-sequence length, Table 6: 1/2/3) has no
    literal analogue here — this repo does not walk variable-length KG paths, it
    does a single ANN probe over provision-unit embeddings. Traversal *breadth*
    is the honest equivalent, so ``kg_depth`` scales the fanout around its
    existing default: depth 1 -> 30, depth 2 -> 60, depth 3 -> 90. Class 1 maps
    to depth 2, which reproduces ``_DEFAULT_ANN_FANOUT`` exactly, so
    standard-tier traffic is unchanged by the wiring.

    An explicit ``REGENOLD_SEMANTIC_ANN_FANOUT`` still wins outright.
    """
    raw = os.getenv("REGENOLD_SEMANTIC_ANN_FANOUT", "").strip()
    if raw:
        return _int_env("REGENOLD_SEMANTIC_ANN_FANOUT", _DEFAULT_ANN_FANOUT, 10, 200)
    depth = _adaptive_int("kg_depth", "__unset__", 2, 1, 3)
    return max(10, min(200, (_DEFAULT_ANN_FANOUT // 2) * depth))


def _embed(question: str) -> list[float] | None:
    """Query vector in the SAME subspace the seeder wrote (TF-IDF -> SVD-128)."""
    try:
        from app.engines.embeddings_index import _embed_query, is_available  # noqa: PLC0415

        if not is_available():
            return None
        vec = _embed_query(question or "")
        if vec is None:
            return None
        return [float(x) for x in vec]
    except Exception as exc:  # noqa: BLE001 — the graph must never break an answer
        logger.debug("graph_semantic: embed failed: %s", exc)
        return None


# ── Read 1: sub-provision focus, CONSTRAINED to already-cited provisions ─────
#
# ``CALL () { ... }`` is the non-deprecated subquery form on this Aura version
# (a bare ``CALL {`` emits "CALL subquery without a variable scope clause is
# deprecated"). Verified executing against 0644b854.
#
# The variable-length ``*1..3`` walk reaches Paragraph (1 hop), Point (2) and
# SubPoint (3), so one query covers all three unit-level indexes.
_FOCUS_CYPHER = """
CALL () {
    CALL db.index.vector.queryNodes('v_paragraph_embedding', $fanout, $emb)
    YIELD node, score RETURN node, score
    UNION
    CALL db.index.vector.queryNodes('v_point_embedding', $fanout, $emb)
    YIELD node, score RETURN node, score
    UNION
    CALL db.index.vector.queryNodes('v_subpoint_embedding', $fanout, $emb)
    YIELD node, score RETURN node, score
}
WITH node, score WHERE score >= $min_sim
MATCH (a)-[:HAS_PARAGRAPH|HAS_POINT|HAS_SUBPOINT*1..3]->(node)
WHERE a.id IN $ids AND (a:Article OR a:Annex)
// R327 — PER-PROVISION CAP, not a flat global top-N.
//
// A flat `ORDER BY score DESC LIMIT n` lets one provision monopolise the block:
// measured, Article 50 took 3 of 5 slots and Article 26 nearly vanished, even
// though both were cited. The roll-up idiom is from the Cypher appendix of
// "Reducing Hallucinations in Complex Question Answering using Simple
// Graph-based RAG" (query B.2), which searches at chunk grain and then keeps the
// best-scoring chunk PER PARENT paragraph. Same shape here: rank units inside
// each cited provision, keep the top `$per_provision`, then order provisions by
// their own best unit. Coverage across the cited set is what this block is for —
// attributing a duty to the right sub-provision of EACH provision on the wire.
WITH a, node, score ORDER BY score DESC
WITH a,
     collect({uid: node.id, layer: head(labels(node)), text: node.text,
              score: score})[..$per_provision] AS units,
     max(score) AS best
ORDER BY best DESC
UNWIND units AS u
RETURN coalesce(a.strict_citation, a.id) AS cite,
       u.uid AS uid,
       u.layer AS layer,
       u.text AS text,
       u.score AS score
LIMIT $limit
"""

# ── Read 1b: the SAME query, plus the path numbering (R329 P2) ───────────────
#
# ⚠ ``_FOCUS_CYPHER`` above is deliberately left BYTE-IDENTICAL. This variant is
# selected only when ``REGENOLD_SEMANTIC_COORDINATES`` is on, so the default-OFF
# path runs exactly the query R327 gated and a defect here cannot reach it.
#
# The only change is that the walk is bound as ``path`` and the intermediate
# numbering is projected out of ``nodes(path)``. The graph shape is
#   Article/Annex -HAS_PARAGRAPH-> Paragraph -HAS_POINT-> Point -HAS_SUBPOINT-> SubPoint
# (``app/data/provision_hierarchy.py``), so ``nodes(path)`` is
#   [a] | [a, para] | [a, para, point] | [a, para, point, subpoint]
# and the properties are ``Paragraph.number`` / ``Point.letter`` /
# ``SubPoint.roman`` — the same three ``kg_context._SUBPOINT_CYPHER`` reads.
# No extra hop and no extra round trip: the path was already traversed.
#
# The projection is by LABEL (``[n IN chain WHERE n:Paragraph | n.number]``), not
# by position (``chain[1].number``). Same result on the seeded shape, but it does
# not assume the walk's depth ordering and it needs no ``size()``/``CASE`` guard:
# ``head()`` of an empty list is null, so a shallower path simply yields nulls
# for the levels it does not reach.
#
# ``toIntegerOrNull(para)`` in the tie-break is not decoration. ``Paragraph.number``
# is a STRING in this graph (as is ``Article.number``), and a bare sort over it is
# LEXICOGRAPHIC — the R318 defect that silently dropped Article 3's role
# definitions by ordering '1','10','11',…,'2'. Score is a float so exact ties are
# rare, but when they happen the cheap deterministic order must be the numeric one.
_FOCUS_COORD_CYPHER = """
CALL () {
    CALL db.index.vector.queryNodes('v_paragraph_embedding', $fanout, $emb)
    YIELD node, score RETURN node, score
    UNION
    CALL db.index.vector.queryNodes('v_point_embedding', $fanout, $emb)
    YIELD node, score RETURN node, score
    UNION
    CALL db.index.vector.queryNodes('v_subpoint_embedding', $fanout, $emb)
    YIELD node, score RETURN node, score
}
WITH node, score WHERE score >= $min_sim
MATCH path = (a)-[:HAS_PARAGRAPH|HAS_POINT|HAS_SUBPOINT*1..3]->(node)
WHERE a.id IN $ids AND (a:Article OR a:Annex)
WITH a, node, score, nodes(path) AS chain
WITH a, node, score,
     head([n IN chain WHERE n:Paragraph | n.number]) AS para,
     head([n IN chain WHERE n:Point | n.letter]) AS letter,
     head([n IN chain WHERE n:SubPoint | n.roman]) AS roman
ORDER BY score DESC, toIntegerOrNull(para), para
WITH a,
     collect({uid: node.id, layer: head(labels(node)), text: node.text,
              score: score, para: para, letter: letter,
              roman: roman})[..$per_provision] AS units,
     max(score) AS best
ORDER BY best DESC
UNWIND units AS u
RETURN coalesce(a.strict_citation, a.id) AS cite,
       u.uid AS uid,
       u.layer AS layer,
       u.text AS text,
       u.score AS score,
       u.para AS para,
       u.letter AS letter,
       u.roman AS roman
LIMIT $limit
"""

# ── Read 2: definitions + recitals, open-domain but NON-CITABLE ──────────────
#
# Per-branch ORDER BY + LIMIT gives each layer its own quota. With a single
# outer LIMIT the recital branch (~0.70) crowded out the definition branch
# (~0.62) on every probe question, so definitions were never returned at all.
#
# ``anchored`` ranks a recital that textually names one of the cited provisions
# above one that merely scores well — cheap provision-grounding for a layer that
# has almost no structural edges to constrain against.
_GLOSS_CYPHER = """
CALL () {
    CALL db.index.vector.queryNodes('v_definition_embedding', $fanout, $emb)
    YIELD node, score
    WITH node, score WHERE score >= $min_sim
    RETURN 'Definition' AS layer,
           coalesce(node.term, node.id) AS label,
           coalesce(node.citation, '') AS cite,
           node.text AS text, score, false AS anchored
    ORDER BY score DESC LIMIT $definitions_kept
    UNION
    CALL db.index.vector.queryNodes('v_recital_embedding', $fanout, $emb)
    YIELD node, score
    WITH node, score WHERE score >= $min_sim
    WITH node, score,
         any(t IN $anchor_terms WHERE node.text CONTAINS t) AS anchored
    RETURN 'Recital' AS layer,
           toString(node.number) AS label,
           '' AS cite,
           node.text AS text, score, anchored
    ORDER BY anchored DESC, score DESC LIMIT $recitals_kept
}
RETURN layer, label, cite, text, score, anchored
"""


# ── Coordinate reconstruction (R329 P2) ─────────────────────────────────────
#
# Hard rule #1 is the contract: ``Article N(.subpoint)*`` with an ARABIC article
# number, ``Annex X(.subpoint)*`` with an UPPERCASE ROMAN annex. Never ``Art. 12``,
# never ``Article 12(1)``, never ``Annex 3``.

#: The head must already be in wire form before a tail is appended to it.
_WIRE_HEAD_RE = re.compile(r"^(?:Article \d{1,3}|Annex [IVXLCDM]{1,7})$")

#: ``head(labels(node))`` → how many dot-separated tokens the coordinate needs.
#: A Point row that lost its letter must NOT degrade to the paragraph
#: coordinate: that would silently relabel 12(1)(a)'s text as "Article 12.1".
_LAYER_DEPTH = {"paragraph": 1, "point": 2, "subpoint": 3}


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _wire_head(cite: object) -> str | None:
    """``cite`` → ``Article 12`` / ``Annex III``, or ``None`` if it is neither.

    The query returns ``coalesce(a.strict_citation, a.id)``. ``strict_citation``
    is already the wire form (the seeder writes ``_ref_to_user_facing``), but the
    coalesce can fall through to the node id on a partially-seeded node, and
    ``article_12`` / ``annex_III`` are NOT wire-legal. Normalise those two known
    id shapes; reject anything else rather than guess.
    """
    raw = _clean(cite)
    if not raw:
        return None
    if raw.startswith("article_"):
        tail = raw[len("article_"):].split("_")[0]
        raw = f"Article {tail}" if tail.isdigit() else raw
    elif raw.startswith("annex_"):
        raw = f"Annex {raw[len('annex_'):].split('_')[0].upper()}"
    return raw if _WIRE_HEAD_RE.match(raw) else None


@lru_cache(maxsize=512)
def _paragraph_coordinate_resolves(ref: str) -> bool:
    """True iff ``ref`` (a head + ONE token) has verbatim text in the pinned Act.

    ⚠ THIS GUARD IS NOT DEFENSIVE PADDING — it catches a real fabrication.
    ``provision_hierarchy.build_hierarchy_payload`` synthesises a Paragraph
    numbered ``"1"`` for a single-block article whose body carries a lettered
    list, so the graph holds ``article_16 -> article_16_1 -> article_16_1_a``
    even though Article 16 has no paragraph 1 — its list is ``16(a)…(n)``.
    Reconstructing straight off the path would print ``Article 16.1.a``, a
    coordinate that does not exist, in the one block whose entire purpose is
    sub-provision precision. Measured against the pinned text: exactly 3 of 658
    Paragraph nodes are synthetic this way (``Article 16.1``, ``Article 66.1``,
    ``Annex XIII.1``). Those rows fall back to the head-level rendering.

    ``provision_exists`` cannot be used here — it is head-level LAX
    (``provision_exists("Article 3.999")`` is True). Only ``get_provision_text``
    returning non-None validates a coordinate, and it resolves exactly one
    sub-token deep (article paragraph / Art. 3 definition / annex item), which
    is the level the synthetic node lives at.
    """
    try:
        from app.data.provision_text import get_provision_text  # noqa: PLC0415

        return get_provision_text(ref) is not None
    except Exception:  # noqa: BLE001 — a failed guard must fall back, not raise
        return False


def coordinate_for_row(row: dict) -> str | None:
    """Rebuild the wire-format legal coordinate for one focused row.

    ``Article 12.1`` (paragraph) · ``Article 5.1.f`` (point) ·
    ``Article 5.1.h.iii`` (sub-point) · ``Annex III.2`` (annex item).

    Pure — no graph, no env read. Returns ``None`` whenever the coordinate
    cannot be reconstructed IN FULL, so the caller falls back to the existing
    head-level rendering rather than shipping a partial or guessed coordinate.
    ``None`` is returned for: a head that is not wire-legal, a missing or
    non-numeric paragraph number, a layer whose numbering is incomplete (a Point
    with no letter, a SubPoint with no roman), an unknown layer, a synthetic
    paragraph (see :func:`_paragraph_coordinate_resolves`), and anything
    ``reference_from_article_ref`` refuses to format.
    """
    head = _wire_head(row.get("cite"))
    if head is None:
        return None

    depth = _LAYER_DEPTH.get(_clean(row.get("layer")).lower())
    if depth is None:
        return None

    para = _clean(row.get("para"))
    if not para.isdigit():
        return None
    tokens = [para]
    if depth >= 2:
        letter = _clean(row.get("letter"))
        if not letter:
            return None
        tokens.append(letter)
    if depth >= 3:
        roman = _clean(row.get("roman"))
        if not roman:
            return None
        tokens.append(roman)

    if not _paragraph_coordinate_resolves(f"{head}.{para}"):
        return None

    try:
        from app.integrations.regenold.models import (  # noqa: PLC0415
            reference_from_article_ref,
        )

        # One formatter, one shape check. ``reference_from_article_ref`` gates on
        # ARTICLE_EXISTENCE, rejects an out-of-range or malformed sub-token
        # all-or-nothing, and re-validates the emission against the Regenold
        # output regex — so nothing malformed can leave this function.
        return reference_from_article_ref(f"{head}.{'.'.join(tokens)}")
    except Exception:  # noqa: BLE001
        return None


def fetch_focused_subprovisions(question: str, refs: list[str]) -> list[dict]:
    """ANN over the three unit indexes, constrained to already-cited provisions.

    Returns ``[]`` unless the feature is on, the graph is reachable and there is
    at least one resolvable cited provision. Never raises.

    With ``REGENOLD_SEMANTIC_COORDINATES`` on, each row additionally carries
    ``para`` / ``letter`` / ``roman`` from the bound path, which
    :func:`coordinate_for_row` turns into a wire-format coordinate.
    """
    if not semantic_layers_enabled():
        return []
    try:
        from app.engines.kg_context import (  # noqa: PLC0415
            _bounded_execute_read,
            _node_ids,
            kg_context_enabled,
        )

        if not kg_context_enabled():
            return []
        ids = _node_ids(refs or [], _int_env("REGENOLD_KG_MAX_REFS", 8, 1, 10))
        if not ids:
            return []
        emb = _embed(question)
        if emb is None:
            return []
        rows = _bounded_execute_read(
            _FOCUS_COORD_CYPHER if semantic_coordinates_enabled() else _FOCUS_CYPHER,
            {
                "emb": emb,
                "ids": ids,
                "fanout": _adaptive_fanout(),
                "min_sim": _float_env(
                    "REGENOLD_SEMANTIC_MIN_SIM", _DEFAULT_MIN_SIM, 0.0, 1.0
                ),
                "limit": _int_env(
                    "REGENOLD_SEMANTIC_UNITS", _DEFAULT_UNITS_KEPT, 1, 60
                ),
                "per_provision": _int_env(
                    "REGENOLD_SEMANTIC_UNITS_PER_PROVISION",
                    _DEFAULT_UNITS_PER_PROVISION,
                    1,
                    6,
                ),
            },
        )
        return list(rows or [])
    except Exception:  # noqa: BLE001 — the graph must never break an answer
        logger.debug("graph_semantic: focused sub-provision fetch failed", exc_info=True)
        return []


def _anchor_terms(refs: list[str]) -> list[str]:
    """Wire-form provision names to look for inside recital prose."""
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs or []:
        try:
            from app.integrations.regenold.models import (  # noqa: PLC0415
                reference_from_article_ref,
            )

            wire = reference_from_article_ref(str(ref)) or str(ref)
        except Exception:  # noqa: BLE001
            wire = str(ref)
        head = wire.split(".")[0].strip()
        if head and head not in seen:
            seen.add(head)
            out.append(head)
    return out[:8]


def fetch_definition_and_recital_context(
    question: str, refs: list[str]
) -> list[dict]:
    """ANN over the definition + recital indexes, each with its own quota.

    Open-domain by necessity: ``HAS_RECITAL_ANCHOR`` has 5 edges in the whole
    graph, so there is nothing structural to constrain recitals against. Safe
    because neither layer can become a wire citation.

    Gated by BOTH the master switch and :func:`gloss_layers_enabled`, so the
    open-domain half can be measured separately from the constrained half — see
    the R327 gate result in that docstring.
    """
    if not semantic_layers_enabled() or not gloss_layers_enabled():
        return []
    try:
        from app.engines.kg_context import (  # noqa: PLC0415
            _bounded_execute_read,
            kg_context_enabled,
        )

        if not kg_context_enabled():
            return []
        emb = _embed(question)
        if emb is None:
            return []
        rows = _bounded_execute_read(
            _GLOSS_CYPHER,
            {
                "emb": emb,
                "fanout": _int_env(
                    "REGENOLD_SEMANTIC_GLOSS_FANOUT", 20, 5, 100
                ),
                "min_sim": _float_env(
                    "REGENOLD_SEMANTIC_MIN_SIM", _DEFAULT_MIN_SIM, 0.0, 1.0
                ),
                "definitions_kept": _int_env(
                    "REGENOLD_SEMANTIC_DEFINITIONS", _DEFAULT_DEFINITIONS_KEPT, 0, 8
                ),
                "recitals_kept": _int_env(
                    "REGENOLD_SEMANTIC_RECITALS", _DEFAULT_RECITALS_KEPT, 0, 8
                ),
                "anchor_terms": _anchor_terms(refs),
            },
        )
        return list(rows or [])
    except Exception:  # noqa: BLE001 — the graph must never break an answer
        logger.debug("graph_semantic: gloss fetch failed", exc_info=True)
        return []
