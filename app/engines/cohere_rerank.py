"""R329 — cross-encoder reranking of candidate provisions (Cohere Rerank).

WHY THIS EXISTS
===============

The live HARD measurement (``docs/R329-SCORECARD-VS-FRONTIER.md``, grounded
Sonnet-5 judge, n=40) put reference **precision at 0.653** against recall 0.879.
Every sampled failure was an EXTRA reference, never a missing one:

    "over-citation of inapplicable transparency and product-safety provisions"
    "over-cited log-retention provision (Art 19) not tied to competent-authority
     documentation"

That is not a count problem. Only 2 of 40 rows exceeded 5 references — the mean
was 3.30. The damage is ~1.1 WRONG references inside an otherwise reasonable
set, and no count clamp can fix it: a cut cannot know *which* of three refs is
wrong. It is a ranking problem, which is why the five refuted trimmer families
(``.planning/R318-PLAN.md`` §1) all failed — they attacked the count.

WHY A MANAGED RERANKER, AND WHY THIS ONE
========================================

``AGENTS.md`` forbids PyTorch / heavy neural models in the runtime path, and
Railway is CPU-only. That constraint killed every previous reranker attempt here
(R32 built, R46 deleted as bench-negative; ``bge-reranker-large`` is torch+GPU).
A hosted cross-encoder sidesteps it entirely — no local model, no new heavy
dependency, one bounded HTTP call.

AWS Bedrock hosts the same class of model and would have kept inference inside
``eu-central-1``. It is NOT used here for a measured reason: Bedrock's Rerank API
lives in ``bedrock-agent-runtime``, which requires SigV4 and rejects the
``AWS_BEARER_TOKEN_BEDROCK`` API-key this deployment holds::

    ClientError IncompleteSignatureException: Authorization header requires
    'Credential' / 'Signature' / 'SignedHeaders' parameters

Both ``amazon.rerank-v1:0`` and ``cohere.rerank-v3-5:0`` ARE available in
``eu-central-1`` (verified; ``eu-west-1`` has neither), so the Bedrock path
becomes preferable the moment IAM credentials with ``bedrock:Rerank`` exist.
See ``.planning/R329-PLAN-RANKER-AND-OVERCITATION.md`` §2.3.

⚠ **Data-protection note.** This module sends to Cohere (``api.cohere.com``):

* **the rerank QUERY** — the user's live question, bounded at
  ``_MAX_RERANK_QUERY_CHARS`` (600), plus short repo-static context labels
  (intent / risk tier / dimension); and
* **the DOCUMENTS** — verbatim EU AI Act provision text, ≤4,000 chars each,
  ≤50 docs, optionally annotated with a curated cross-reference reason
  (≤240 chars, also repo-static).

The Act text is public law; the question is partner input. For an EU AI Act
compliance product that is a residency decision the operator must make
deliberately — which is why this ships **default OFF** and why the Bedrock path
is the preferred destination.

⚠ **Corrected R350.** This note used to say "the user's question", and that was
materially understated: on a MULTI-TURN request the engine question is the
FLATTENED conversation (``Conversation so far: …`` — every prior user and
assistant turn, up to 40 turns), and the 600-char cap applied only when a
context string was present. The ``rerank_references`` callers pass none, so
they sent it unbounded — measured, an entire 2,334-char conversation went out
verbatim, against a 64,000-char input ceiling. :func:`_rerank_query` now
extracts the LIVE turn and bounds every path. **If you change what goes into
the query, change this note in the same edit** — a residency decision made on a
stale description is not a decision.

DESIGN — REORDER ONLY, NEVER DROP
=================================

:func:`rerank_references` returns a PERMUTATION of its input. It never removes,
never adds, never rewrites a reference. That is deliberate and load-bearing:
R142.1 lost a live pairwise 11-0 (refs p=0.001) by dropping a gold reference.

The cut stays with the already-validated R281 ``adaptive_ref_clamp``
(``app/routes/regenold.py:4416``), which trims from the TAIL against a
per-question budget and measured +1.17pp with its own gold guard. This module
supplies the ORDER; that pass supplies the CUT. Composed, a wrong reference is
moved to the tail and then removed by a mechanism that already has a gold-drop
guard — neither half is a new trimmer family.

Fail-soft everywhere: any error, timeout, missing key or malformed response
returns the input order UNCHANGED. A reranker outage must never alter the
reference set.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Sequence
from typing import Any

import httpx

logger = logging.getLogger(__name__)

__all__ = [
    "rerank_enabled",
    "rerank_documents",
    "rerank_pool",
    "rerank_references",
    "rerank_query_context",
    "build_kg_candidate_pool",
    "build_kg_candidate_pool_with_reasons",
    "rerank_kg_candidates_enabled",
    "rerank_kg_hops",
    "rerank_stats",
    "reset_rerank_stats",
    "stabilize_anchor_tier",
]

#: R347 — hybrid-RAG candidate supplementation: the parse-level rerank may
#: rank the keyword entities TOGETHER with their 1-hop CROSS_REFERENCES
#: neighbours from the KG taxonomy (see :func:`build_kg_candidate_pool`), so
#: a genuinely cross-referenced provision can be promoted ahead of a keyword
#: hit. DEFAULT OFF — the A/B decides; the R340 permutation-only contract is
#: the baseline behaviour.
_RERANK_KG_ENV = "REGENOLD_RERANK_KG_CANDIDATES"


def rerank_kg_candidates_enabled() -> bool:
    """``REGENOLD_RERANK_KG_CANDIDATES`` — **DEFAULT OFF**, fresh read per call.

    Only meaningful when ``REGENOLD_COHERE_RERANK=1``: the KG expansion is
    applied to the pool the cross-encoder ranks, never to a gate-off parse.
    """
    return (
        os.getenv(_RERANK_KG_ENV, "0").strip().lower()
        in _TRUTHY
    )


_RERANK_KG_HOPS_ENV = "REGENOLD_RERANK_KG_HOPS"


def rerank_kg_hops() -> int:
    """``REGENOLD_RERANK_KG_HOPS`` — **1** by default, **2** optional.

    R348 — how deep the KG candidate expansion goes. Hop-2 neighbours ("the
    provisions those provisions point at") are genuinely different retrieval
    candidates, but a hub article's 2-hop closure floods the pool, so hop-2
    neighbours are capped at a fraction of the hop-1 budget (``max_extra``
    split 2:1 — see :func:`build_kg_candidate_pool`). Values outside ``1..2``
    clamp to 1. Fresh read per call; registered in ``_engine_cache_key`` so the
    A/B arm is cache-distinct.
    """
    try:
        hops = int(os.getenv(_RERANK_KG_HOPS_ENV, "1").strip() or "1")
    except (TypeError, ValueError):  # noqa: BLE001
        return 1
    return 2 if hops >= 2 else 1

COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"

_ENV_GATE = "REGENOLD_COHERE_RERANK"
_ENV_MODEL = "REGENOLD_COHERE_RERANK_MODEL"
_DEFAULT_MODEL = "rerank-v3.5"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Latency is a SCORED axis (Speed, 61.7% — our second-worst) and live p50 is
#: already ~57 s, so this call must be tightly bounded and must fail open.
_CLIENT_TIMEOUT = httpx.Timeout(6.0, connect=2.0)

_CLIENT_LOCK = threading.Lock()
_CLIENT: httpx.Client | None = None

# ── Call instrumentation (R331) ──────────────────────────────────────────────
#
# R329 tried three placements for this reranker. All three looked correct in
# the diff and all three made **ZERO calls**: two sat behind gates that never
# opened (``kb_search.top_articles_by_relevance`` is reached only when
# ``_deterministic_parse`` extracted no entities — see ``_graph_rag_impl.py``
# ``if not entities:`` at :2270), and the "budget cut" the third was routed
# through was already within budget. The A/B read +0.0000 on every axis, which
# is indistinguishable from "the lever does not work".
#
# Byte-identical output is what an INERT feature looks like. A number read off
# an unproven placement measures nothing, so every placement must assert
# ``rerank_stats()["attempts"] > 0`` before any A/B result is believed.
_STATS_LOCK = threading.Lock()
_STATS: dict[str, int] = {"attempts": 0, "reordered": 0, "failed": 0, "noop": 0}


def rerank_stats() -> dict[str, int]:
    """Snapshot of the call counters.

    ``attempts``  — network calls actually issued to Cohere.
    ``reordered`` — :func:`rerank_references` calls that CHANGED the order.
    ``failed``    — attempts that fell back to the input order.
    ``noop``      — attempts that returned the input order unchanged.

    ``attempts == 0`` means the feature never ran; treat any downstream metric
    as UNMEASURED, not as evidence of no effect.
    """
    with _STATS_LOCK:
        return dict(_STATS)


def reset_rerank_stats() -> None:
    """Zero the counters — per-arm reset for an A/B harness."""
    with _STATS_LOCK:
        for key in _STATS:
            _STATS[key] = 0


def _bump(field: str) -> None:
    with _STATS_LOCK:
        _STATS[field] = _STATS.get(field, 0) + 1


def _get_client() -> httpx.Client:
    """Module-level pooled client (R112 pattern — avoids per-call TLS setup)."""
    global _CLIENT
    client = _CLIENT
    if client is not None:
        return client
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = httpx.Client(
                timeout=_CLIENT_TIMEOUT,
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            )
        return _CLIENT


def rerank_enabled() -> bool:
    """``REGENOLD_COHERE_RERANK`` — **DEFAULT OFF**, fresh env read per call.

    Default OFF for three independent reasons, any one of which is sufficient:

    * it is unmeasured on this corpus (R325 measured that nothing beat the
      engine's own ``rank``, AUC 0.703 — though with a *lexical* reranker, not a
      cross-encoder, so this is a genuinely different arm);
    * it adds external egress of partner questions (see the module docstring);
    * this repo has just paid for an ungated default-ON retrieval change
      (R329 HyPA: Ref Conciseness −0.209).

    Fresh read per call (R263.2) so ``evals/harness/easyhard_ab.py`` can flip it
    between in-process arms.
    """
    if os.getenv(_ENV_GATE, "0").strip().lower() not in _TRUTHY:
        return False
    return bool(os.getenv("COHERE_API_KEY", "").strip())


def rerank_documents(
    query: str,
    documents: Sequence[str],
    *,
    top_n: int | None = None,
) -> list[tuple[int, float]] | None:
    """Return ``[(original_index, relevance_score), ...]`` best-first.

    Returns ``None`` on ANY failure so callers can keep their input order.
    Never raises.
    """
    if not rerank_enabled():
        return None
    docs = [str(d) for d in documents if str(d).strip()]
    if len(docs) < 2 or not str(query).strip():
        # Nothing to reorder — do not pay a network round-trip.
        return None

    key = os.getenv("COHERE_API_KEY", "").strip()
    model = os.getenv(_ENV_MODEL, "").strip() or _DEFAULT_MODEL
    payload: dict[str, Any] = {
        "model": model,
        "query": str(query),
        "documents": list(docs),
        "top_n": int(top_n) if top_n else len(docs),
    }
    _bump("attempts")
    try:
        resp = _get_client().post(
            COHERE_RERANK_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            logger.debug(
                "cohere_rerank: http %s (%s)", resp.status_code, resp.text[:160]
            )
            _bump("failed")
            return None
        body = resp.json()
    except Exception as exc:  # noqa: BLE001 — fail open, never break the answer
        logger.debug("cohere_rerank: call failed: %s", exc)
        _bump("failed")
        return None

    try:
        out: list[tuple[int, float]] = []
        for item in body.get("results") or []:
            idx = item.get("index")
            score = item.get("relevance_score")
            if isinstance(idx, int) and 0 <= idx < len(docs):
                out.append((idx, float(score) if score is not None else 0.0))
        if not out:
            _bump("failed")
            return None
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("cohere_rerank: malformed response: %s", exc)
        _bump("failed")
        return None


def rerank_query_context(
    *, intent: str = "", risk_context: str = "", dimension_hint: str = ""
) -> str:
    """R347 — deterministic rerank-query enrichment from the parse's own labels.

    A bare question string is a weak discriminator for a cross-encoder: the
    classifier already KNOWS the question is a ``prohibited_practice`` ask
    about a ``high``-risk system — telling the reranker the same in domain
    terms focuses its relevance signal. No LLM call; a few tokens.

    Returns a short ``"; ".join`` (e.g. ``"risk: high; intent: prohibited
    practice"``) that callers append to the rerank query. Empty string when
    nothing is available — the query stays exactly the question.
    """
    parts: list[str] = []
    if risk_context:
        parts.append(f"risk: {str(risk_context).strip().lower()}")
    if intent:
        parts.append(
            f"intent: {str(intent).strip().lower().replace('_', ' ')}"
        )
    if dimension_hint:
        parts.append(
            f"focus: {str(dimension_hint).strip().lower().replace('_', ' ')}"
        )
    return "; ".join(parts)


def _hop_budgets(max_extra: int, hops: int) -> tuple[int, int]:
    """Split ``max_extra`` between hop-1 and hop-2. One definition, both pools.

    At ``hops == 1`` there is no hop-2 to reserve for, so hop-1 gets the WHOLE
    budget — anything else makes the depth knob change the depth-1 result.
    At ``hops >= 2`` hop-1 keeps 2/3 so a hub article's 2-hop closure cannot
    starve the direct neighbours.
    """
    total = max(0, int(max_extra))
    if int(hops) < 2:
        return total, 0
    hop1 = max(1, total * 2 // 3)
    return hop1, max(0, total - hop1)


def build_kg_candidate_pool(
    references: Sequence[str],
    *,
    max_extra: int = 8,
    per_ref: int = 3,
    hops: int = 1,
) -> list[str]:
    """R347 — ``references`` + deduplicated CROSS_REFERENCES neighbours.

    The KG/taxonomy lever: each candidate's own cross-reference adjacency
    (incoming AND outgoing on the embedded undirected graph; the canonical
    ``kb_xrefs.cross_refs`` adjacency when the embedded backend is not
    selected) is appended to the pool, so the cross-encoder can PROMOTE a
    genuinely cross-referenced provision that the keyword map never saw —
    instead of only re-ordering a keyword-picked set.

    R348 — ``hops=2`` walks one level further ("the provisions those
    provisions point at"), on EITHER backend: the embedded graph's
    ``neighbors()`` when selected, else the composed ``cross_refs(cross_refs
    (ref))`` adjacency via the frontier walk below. Hop-2 closure floods the
    pool around a hub article, so the ``max_extra`` budget is split 2:1 —
    hop-1 neighbours get the first ``2/3`` slots, hop-2 the remaining
    ``1/3`` (which may go unused when the closure is thin).

    Appends only, deduplicated, capped at ``max_extra`` (a hub article like
    Art. 16 would otherwise flood the pool). The caller adopts the result
    only when the rerank call SUCCEEDED (see :func:`rerank_pool`'s ok bit),
    so a failure never leaks neighbours into the reference set. Never raises.
    """
    base = [r for r in (references or [])]
    extra: list[str] = []
    try:
        # Prefer the embedded graph (undirected — includes refs that POINT AT
        # our anchors, the "why is this relevant" signal); fall back to the
        # outgoing-only kb_xrefs adjacency when the neo4j backend is selected.
        from app.graph.embedded_graph import (  # noqa: PLC0415
            embedded_backend_selected,
            get_embedded_graph,
        )

        neighbors_of: Any = None
        graph_hops = max(1, int(hops))
        if embedded_backend_selected():
            try:
                g = get_embedded_graph()
                if g.enabled:
                    neighbors_of = g.neighbors
            except Exception:  # noqa: BLE001
                neighbors_of = None
        if neighbors_of is None:
            from functools import partial  # noqa: PLC0415

            from app.data.kb_xrefs import cross_refs  # noqa: PLC0415

            # Composed adjacency: hop-2 becomes cross_refs(cross_refs(ref))
            # via the frontier walk below.
            neighbors_of = partial(cross_refs, limit=per_ref)

        # Budget split (R348): hop-1 gets ~2/3 of ``max_extra``, hop-2 the
        # remaining 1/3 — a hub article's 2-hop closure must not starve the
        # direct neighbours. Each hop stops as soon as its own budget fills.
        #
        # ⚠ R350 — the split applies ONLY at hops>=2. It used to be computed
        # unconditionally, so ``hops=1`` silently capped the pool at 2/3 of
        # ``max_extra`` (5 of 8) even though there was no hop-2 to reserve for.
        # A depth knob must not change the depth-1 result, or "hops=1 is the
        # existing behaviour" stops being true and the A/B measures two things.
        hop1_budget, hop2_budget = _hop_budgets(max_extra, graph_hops)

        def _collect(frontier: list[str], budget: int) -> list[str]:
            """Neighbours of ``frontier`` not already seen, up to ``budget``."""
            out: list[str] = []
            for ref in frontier:
                try:
                    nbs = neighbors_of(ref)
                except Exception:  # noqa: BLE001 — one bad ref must not kill the pool
                    continue
                for nb in nbs:
                    if nb not in base and nb not in extra:
                        extra.append(nb)
                        out.append(nb)
                        if len(out) >= budget:
                            return out
            return out

        hop1 = _collect(list(base), hop1_budget)
        if graph_hops >= 2 and hop2_budget > 0 and len(extra) < max_extra:
            _collect(hop1, hop2_budget)
    except Exception:  # noqa: BLE001 — KG expansion must never break parse
        return base
    return base + extra


def build_kg_candidate_pool_with_reasons(
    references: Sequence[str],
    *,
    max_extra: int = 8,
    per_ref: int = 3,
    hops: int = 1,
) -> list[tuple[str, str]]:
    """R348 — like :func:`build_kg_candidate_pool`, but each neighbour carries
    the CURATED semantic reason for its edge (the KG's semantic layer).

    ``cross_refs_with_reason`` resolves ``(target, reason)`` pairs from the
    FULL graph — regex + manual + the R47-A backfill whose curated reasons
    are sentences like ``"Art. 26 → Art. 13: deployer reads provider's
    transparency schema"``. Feeding that reason into the rerank DOCUMENT (see
    ``rerank_pool(doc_reasons=...)``) tells the cross-encoder WHY the
    neighbour is relevant to the anchor, which is exactly the semantic signal
    a bare provision text omits.

    Deterministic, backend-independent, never raises: a reason-index failure
    degrades to the plain :func:`build_kg_candidate_pool` with a generic
    relation label. Returns ``(ref, reason)`` pairs in pool order.

    ⚠ R350 — this function grew the ``hops`` parameter it always needed. R348
    shipped ``REGENOLD_RERANK_KG_HOPS`` and wired it ONLY to
    :func:`build_kg_candidate_pool`, which the caller reaches solely in the
    ``else`` of ``if pairs:`` — and ``cross_refs_with_reason`` resolves a pair
    for essentially every entity, so that branch almost never ran. Measured:
    5/5 representative questions produced byte-identical pools at hops=1 and
    hops=2. The flag was registered in ``_engine_cache_key``, so the two arms
    were cache-DISTINCT and both genuinely re-ran — the fire check passed on
    Stage-2 noise and the harness would have printed an axis table for a depth
    change that never happened. That is the inert-feature trap arriving through
    the guard built to catch it. Hop-2 reasons are labelled ``"via <hop-1 ref>:
    …"`` so the cross-encoder can tell a direct edge from a transitive one.
    """
    base = [r for r in (references or [])]
    try:
        from app.data.kb_xrefs import cross_refs_with_reason  # noqa: PLC0415

        pairs: list[tuple[str, str]] = []
        seen: set[str] = set(base)
        graph_hops = max(1, int(hops))
        hop1_budget, hop2_budget = _hop_budgets(max_extra, graph_hops)

        def _collect(frontier: list[str], budget: int, *, via: bool) -> list[str]:
            """Reason-carrying neighbours of ``frontier``, up to ``budget``."""
            out: list[str] = []
            for ref in frontier:
                try:
                    edges = cross_refs_with_reason(ref, limit=per_ref)
                except Exception:  # noqa: BLE001 — one bad ref must not kill the pool
                    continue
                for target, reason in edges:
                    if target in seen:
                        continue
                    text = str(reason).strip() or "cross-referenced"
                    if via:
                        text = f"via {ref}: {text}"
                    seen.add(target)
                    pairs.append((target, text))
                    out.append(target)
                    if len(out) >= budget or len(pairs) >= max_extra:
                        return out
            return out

        hop1 = _collect(list(base), hop1_budget, via=False)
        if graph_hops >= 2 and hop2_budget > 0 and len(pairs) < max_extra:
            _collect(hop1, hop2_budget, via=True)
        return pairs
    except Exception:  # noqa: BLE001 — semantic layer must never break parse
        return []


def _pool_reasons(
    references: Sequence[str], pairs: Sequence[tuple[str, str]] | None
) -> dict[str, str] | None:
    """Merge KG reason-pairs into a ``ref -> reason`` map for doc enrichment.

    ``None`` when no pairs were supplied (the R340/permutation-only contract
    is unchanged). Never raises; malformed pairs are skipped.
    """
    if not pairs:
        return None
    out: dict[str, str] = {}
    for ref, reason in pairs:
        if ref and str(reason).strip():
            out[str(ref)] = str(reason).strip()[:240]
    return out or None


#: Ceiling on the rerank QUERY. Bounds both what the cross-encoder scores
#: against and what leaves the process — see :func:`_rerank_query`.
_MAX_RERANK_QUERY_CHARS = 600


def _rerank_query(question: str, query_context: str = "") -> str:
    """Build the cross-encoder query: the LIVE turn, plus the context labels.

    ⚠ R350 — this replaces ``f"{query} — {ctx}"[:600]``, which had two defects
    and one disclosure problem.

    1. **It sliced from the HEAD while the live question is at the TAIL.** The
       multi-turn question is flattened as ``…Conversation so far:\\n{history}
       \\n\\nLatest question:\\n{live}``. Measured on a 6-turn 2,334-char
       question, the 600 chars actually sent began ``"Conversation so far:
       User: In turn 0 …"`` and contained the live turn **not at all** — so the
       cross-encoder ordered the citation candidates against PRIOR-TURN text.
       Entity order decides which candidates survive the downstream slot cap.
    2. **It discarded the enrichment it exists to add.** ``ctx`` is appended at
       the tail, and at the parse-level call site ``ctx`` is ALWAYS non-empty
       (``intent`` defaults to ``general_compliance``), so on any question over
       600 chars the whole R347 intent/risk/dimension context was cut off the
       end — the feature silently removing itself.
    3. **The cap lived inside ``if ctx:``**, so the ``rerank_references``
       callers (no context) sent the query UNBOUNDED. Measured: the entire
       2,334-char flattened conversation — every prior user AND assistant turn
       — was POSTed to ``api.cohere.com``, against a ``_MAX_QUESTION_CHARS``
       ceiling of 64,000 and a route comment estimating ~10-25k for a 20-turn
       legal conversation. The module's data-protection note claimed only "the
       user's question" left the process.

    So: take the live turn first, bound THAT, and keep the context labels —
    they are short, repo-static, and the reason the query is enriched at all.
    """
    text = str(question or "").strip()
    # The flattened multi-turn shape puts the live turn last; prefer it.
    marker = "Latest question:"
    if marker in text:
        text = text.rsplit(marker, 1)[-1].strip()
    ctx = (query_context or "").strip()
    budget = max(0, _MAX_RERANK_QUERY_CHARS - (len(ctx) + 3 if ctx else 0))
    text = text[:budget]
    # R350.1 — clamp the RETURN, not just the question half. With a context
    # string at or over the ceiling the budget goes to 0, the question is
    # dropped entirely, and the result was still longer than the cap it is
    # named for — a bound the data-protection note asserts must actually hold.
    # Not reachable with today's short repo-static labels; enforced anyway.
    out = f"{text} — {ctx}" if ctx else text
    return out[:_MAX_RERANK_QUERY_CHARS]


def rerank_pool(
    question: str,
    references: Sequence[str],
    *,
    query_context: str = "",
    doc_reasons: dict[str, str] | None = None,
    text_for: Any = None,
) -> tuple[list[str], bool]:
    """R347 — the permutation core with an explicit SUCCESS bit.

    Identical guarantees to :func:`rerank_references` (output is a
    PERMUTATION of the input, unresolved refs keep relative order, any
    failure returns the input unchanged), plus ``ok``:

    * ``ok=True``  — the cross-encoder answered; the output order is its
      verdict. ``ok`` is True even when the verdict equals the input order
      (a successful noop).
    * ``ok=False`` — gate off, no scorable pair, network/timeout/malformed
      failure, or the permutation invariant broke. The input stands.

    The bit lets a caller that EXPANDED the pool (e.g.
    :func:`build_kg_candidate_pool`) adopt the expanded result only on real
    success — a rerank outage must never change the reference set.

    ``query_context`` (see :func:`rerank_query_context`) is appended to the
    rerank query — the cross-encoder discriminates on domain terms.
    ``doc_reasons`` (R348, a ``ref -> reason`` map from
    :func:`build_kg_candidate_pool_with_reasons`) annotates each doc with its
    curated KG edge reason (``"\nRelation: …"``) — the semantic-layer signal
    telling the cross-encoder why a KG-supplemented neighbour matters.

    :param text_for: callable ``ref -> str | None`` supplying the verbatim
        text of a provision. Defaults to
        :func:`app.data.provision_text.get_provision_text`.
    """
    refs = [r for r in (references or [])]
    if len(refs) < 2:
        return list(refs), False
    if not rerank_enabled():
        return list(refs), False

    if text_for is None:
        try:
            from app.data.provision_text import (  # noqa: PLC0415
                get_provision_text,
            )

            text_for = get_provision_text
        except Exception:  # noqa: BLE001
            return list(refs), False

    # R348 — a KG-supplemented neighbour carries its CURATED semantic reason
    # (e.g. "deployer reads provider's transparency schema"); appending it to
    # the doc tells the cross-encoder WHY the provision is relevant, which a
    # bare provision text omits. Reasons only ever ANNOTATE text that already
    # resolved — an unresolvable ref still falls out of the scored set.
    reasons = doc_reasons or {}

    # Only rows whose provision text resolves can be scored. Unresolved refs are
    # held aside and re-appended in their ORIGINAL relative order, so nothing is
    # lost and the transform stays a permutation.
    scorable: list[int] = []
    docs: list[str] = []
    for i, ref in enumerate(refs):
        try:
            txt = text_for(ref)
        except Exception:  # noqa: BLE001
            txt = None
        if txt and str(txt).strip():
            scorable.append(i)
            doc = str(txt).strip()[:4000]
            reason = reasons.get(str(ref))
            if reason:
                doc = f"{doc}\nRelation: {reason}"[:4100]
            docs.append(doc)

    if len(scorable) < 2:
        return list(refs), False

    query = _rerank_query(question, query_context)

    ranked = rerank_documents(query, docs)
    if not ranked:
        return list(refs), False

    seen: set[int] = set()
    ordered: list[str] = []
    for doc_idx, _score in ranked:
        if 0 <= doc_idx < len(scorable):
            orig = scorable[doc_idx]
            if orig not in seen:
                seen.add(orig)
                ordered.append(refs[orig])
    # Any scorable ref the API omitted, then every unscorable ref — both in
    # original order. This is what makes the result a permutation.
    for i, ref in enumerate(refs):
        if i in seen:
            continue
        if i in scorable and refs[i] in ordered and ordered.count(refs[i]) >= refs.count(refs[i]):
            continue
        ordered.append(ref)

    if sorted(ordered) != sorted(refs):  # pragma: no cover — invariant guard
        logger.debug("cohere_rerank: permutation invariant violated, keeping input")
        _bump("failed")
        return list(refs), False
    _bump("reordered" if ordered != list(refs) else "noop")
    return ordered, True


def rerank_references(
    question: str,
    references: Sequence[str],
    *,
    text_for: Any = None,
) -> list[str]:
    """Reorder ``references`` by cross-encoder relevance. **Never drops.**

    Thin wrapper over :func:`rerank_pool` keeping the historical signature;
    the guarantees are unchanged (permutation, unresolved refs keep relative
    order, any failure returns the input unchanged).
    """
    return rerank_pool(question, references, text_for=text_for)[0]


def stabilize_anchor_tier(
    ordered: Sequence[str],
    anchors: Sequence[str],
) -> list[str]:
    """R351 — restore the R347 superset guarantee at the CUT, not just the pool.

    ``rerank_pool`` is a permutation, so the KG-expanded pool (anchors +
    neighbours) is a true superset of the keyword entities — but the citation
    budget downstream cuts from the *reordered* entity order, and a
    cross-encoder can score a KG neighbour above a gold anchor, pushing the
    anchor out of the budget. The live R350 A/B (84 rows, graphrag + medtech +
    expert-review) measured exactly this: 5 rows lost gold heads (25 -> 27,
    hard-rule-#8 veto) where the displaced ref was a KG neighbour (Annex XI,
    Art. 49.2, Art. 25, Art. 47, Art. 17, Annex V) that had out-ranked a gold
    anchor (Art. 51.2, Annex III, Art. 9, Annex VI/VII).

    This function makes supplementation strictly ADDITIVE at the cut: every
    anchor precedes every neighbour, so a neighbour can only fill a slot the
    anchors did not take — it can never displace one. Rerank order is
    preserved WITHIN each tier, so the cross-encoder's ranking signal is not
    thrown away. Deterministic, idempotent, never raises, and a no-op when
    the input already satisfies the invariant or contains no anchors.
    """
    try:
        anchor_set = set(str(a) for a in anchors)
        if not anchor_set:
            return list(ordered)
        anchored: list[str] = []
        supplements: list[str] = []
        for r in ordered:
            (anchored if str(r) in anchor_set else supplements).append(r)
        return anchored + supplements
    except Exception:  # noqa: BLE001 — a stability failure must never change the cut
        return list(ordered)
