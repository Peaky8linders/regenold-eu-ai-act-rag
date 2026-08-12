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

logger = logging.getLogger(__name__)

__all__ = [
    "semantic_layers_enabled",
    "gloss_layers_enabled",
    "fetch_focused_subprovisions",
    "fetch_definition_and_recital_context",
]

_DEFAULT_MIN_SIM = 0.30
#: ANN fan-out per index before the provision constraint is applied. The
#: constraint is selective, so the fan-out has to be wide enough that units of a
#: cited provision actually appear in the global top-k.
_DEFAULT_ANN_FANOUT = 60
_DEFAULT_UNITS_KEPT = 6
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
    """``REGENOLD_GRAPH_SEMANTIC_LAYERS`` — default **ON** (constrained half only).

    R327.1 — enabled on the gate result, by operator decision. With
    ``REGENOLD_SEMANTIC_GLOSS`` OFF (its default) this reads
    ``v_paragraph_embedding`` / ``v_point_embedding`` / ``v_subpoint_embedding``
    constrained to already-cited provisions, which measured citation faithfulness
    0.900 -> 0.960 at baseline reference precision. See
    :func:`gloss_layers_enabled` for the full three-arm table.

    Set to ``0`` for instant rollback; the flag is in ``_engine_cache_key`` so an
    in-process A/B of it is real and not a cache replay.

    Fresh env read per call (R263.2).
    """
    return os.getenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
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


def fetch_focused_subprovisions(question: str, refs: list[str]) -> list[dict]:
    """ANN over the three unit indexes, constrained to already-cited provisions.

    Returns ``[]`` unless the feature is on, the graph is reachable and there is
    at least one resolvable cited provision. Never raises.
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
            _FOCUS_CYPHER,
            {
                "emb": emb,
                "ids": ids,
                "fanout": _int_env(
                    "REGENOLD_SEMANTIC_ANN_FANOUT", _DEFAULT_ANN_FANOUT, 10, 200
                ),
                "min_sim": _float_env(
                    "REGENOLD_SEMANTIC_MIN_SIM", _DEFAULT_MIN_SIM, 0.0, 1.0
                ),
                "limit": _int_env(
                    "REGENOLD_SEMANTIC_UNITS", _DEFAULT_UNITS_KEPT, 1, 20
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
