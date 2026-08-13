"""HyPA-RAG Adaptive Query Complexity Router.

Applies the 3-class query complexity classification and adaptive parameter selection
methodology from HyPA-RAG (Kalra et al., 2025, arXiv:2409.09046v2).

Dynamically maps user questions to parameter configurations for:
- Dense/Sparse retrieval top_k (k: 3 -> 5 -> 10)
- Multi-turn / coreferent query rewrites (Q: 0 -> 2 -> 3)
- Knowledge Graph max keywords per query (K: 3 -> 4 -> 5)
- Knowledge Graph sequence traversal depth (S: 1 -> 2 -> 3)
- Knowledge Graph max provision units (K_units: 12 -> 18 -> 24)

Env feature flag: REGENOLD_HYPA_ADAPTIVE_ROUTER (default ON).
"""
from __future__ import annotations

import os
import re
from contextvars import ContextVar
from dataclasses import dataclass

from app.engines.question_complexity import is_complex_question

# Simple definition / single-concept detection regexes (Class 0 signals).
# Excludes substantive obligation/penalty/timeline questions starting with "what is".
_DEFINITION_QUERY_RE = re.compile(
    r"^\s*(?:"
    r"(?:what\s+is|define|meaning\s+of)\s+(?:a\s+|an\s+|the\s+)?(?!required|penalties?|penalty|obligations?|duties|requirements?|timeline|fine|sanctions?)\w+(?:\s+\w+){0,3}\s*[\?\.!]?|"
    r"what\s+does\s+.+?\s+mean\b"
    r")\s*$",
    re.IGNORECASE,
)

# Article lookup regex (Class 0 signal when single non-prohibited article/annex asked directly).
# Excludes Article 5 (Prohibited practices) which requires full complex context.
# R329 SECURITY — the tail was ``\s*(?:say|state|require|cover)?\s*[\?\.!]?\s*$``:
# three ``\s*`` separated by optionals, so a run of N spaces could be partitioned
# across them in O(N^3) ways whenever the ``$`` anchor failed. Measured on the raw
# regex: 5.3 s at 1,000 spaces, 41 s at 2,000, 146 s at 3,000. The
# ``len(words) <= 10`` gate does NOT protect — "Article 1" + " "*N + "X" is three
# words at any N.
#
# Two changes: the tail now carries a single ``\s*``, and the caller normalises
# whitespace before matching (see ``classify_query_complexity``), so long runs
# cannot reach the engine at all.
_DIRECT_ARTICLE_RE = re.compile(
    r"^\s*(?:what\s+does\s+)?(?:article\s+(?!(?:5|05)\b)\d+(?:\.\d+|\(\d+\))*|annex\s+(?:[ivxlcdm]+|\d+)(?:\.\d+|\(\d+\))*)\s*(?:say|state|require|cover)?[\?\.!]?$",
    re.IGNORECASE,
)

#: R329 — collapse whitespace runs before any regex sees the question.
_WS_RUN_RE = re.compile(r"\s+")



@dataclass(frozen=True)
class ComplexityParameters:
    """HyPA adaptive parameters associated with a classified query complexity level."""

    complexity_class: int  # 0: Simple, 1: Standard, 2: Complex
    class_label: str  # "simple", "standard", "complex"
    top_k_dense: int  # k: candidate retrieval depth
    query_rewrites: int  # Q: number of query reformulations
    kg_max_keywords: int  # K: max keywords for KG retrieval
    kg_depth: int  # S: max depth for KG sequence traversal
    kg_max_units: int  # K_units: max paragraph/point units in KG context


# Predefined HyPA-RAG parameter mapping table (3-class configuration).
#
# R329 — reconciled against the paper's Tables 5 and 6 (Appendix A.6), 3-class
# column. Two values had drifted:
#   * ``top_k_dense`` class 2 was 10, which is the **2-class** table's value
#     (Table 5, label 1). The 3-class table says 7.
#   * ``query_rewrites`` was 0/2/3 against the paper's 3/5/7. The real consumer,
#     ``sufficient_context.max_sub_queries``, clamps to [1, 5], so the paper's
#     ladder cannot be reproduced verbatim. Scaled to 2/3/5, preserving the
#     paper's monotonic ordering and pinning class 1 to the current production
#     default (3) so standard-tier traffic is unchanged by the wiring.
# ``kg_max_keywords`` and ``kg_depth`` already matched the paper exactly.
# ``kg_max_units`` is not a paper parameter; it maps to this repo's existing
# ``REGENOLD_KG_MAX_UNITS`` ceiling, whose default is 24.
CLASS_0_PARAMS = ComplexityParameters(
    complexity_class=0,
    class_label="simple",
    top_k_dense=3,
    query_rewrites=2,
    kg_max_keywords=3,
    kg_depth=1,
    kg_max_units=12,
)

CLASS_1_PARAMS = ComplexityParameters(
    complexity_class=1,
    class_label="standard",
    top_k_dense=5,
    query_rewrites=3,
    kg_max_keywords=4,
    kg_depth=2,
    kg_max_units=18,
)

CLASS_2_PARAMS = ComplexityParameters(
    complexity_class=2,
    class_label="complex",
    top_k_dense=7,
    query_rewrites=5,
    kg_max_keywords=5,
    kg_depth=3,
    kg_max_units=24,
)


# ── Per-request active parameters ────────────────────────────────────────
#
# R329 — the router originally computed all five fields but only ``top_k_dense``
# had a consumer, so the paper's distinguishing claim (§7: the classifier tunes
# knowledge-graph and rewriter parameters, not just top-k) was unimplemented.
# The other four DO have real consumer surfaces in this repo; they are simply
# read from the environment deep inside kg_context / graph_semantic /
# sufficient_context, far from where the classification happens. A ContextVar
# carries the classification to them without threading arguments through every
# intermediate call, and is per-request (never leaks across requests, safe under
# the FastAPI threadpool).
_ACTIVE_PARAMS: ContextVar[ComplexityParameters | None] = ContextVar(
    "hypa_active_params", default=None
)


def set_active_parameters(params: ComplexityParameters | None):
    """Bind the classified parameters for the current request. Returns a token."""
    return _ACTIVE_PARAMS.set(params)


def reset_active_parameters(token) -> None:
    """Restore the previous binding (always call in a ``finally``)."""
    try:
        _ACTIVE_PARAMS.reset(token)
    except (ValueError, LookupError):  # pragma: no cover — foreign context
        pass


def adaptive_int(field: str, env_name: str, default: int, lo: int, hi: int) -> int:
    """Resolve an integer knob with **explicit env winning over adaptation**.

    Precedence: explicit environment override > adaptive per-question value >
    static default. Env must win so the in-process A/B harness
    (``evals/harness/ab_judge.py``), which flips env between arms in the SAME
    process, can still pin a knob; otherwise an arm would silently measure the
    adaptive value instead of the one it set.

    Returns ``default`` unchanged when the router is disabled, which keeps the
    default code path byte-identical to pre-R329 behaviour.
    """
    raw = os.environ.get(env_name, "").strip()
    if raw:
        try:
            return max(lo, min(hi, int(raw)))
        except ValueError:
            return default

    if not is_adaptive_router_enabled():
        return default
    params = _ACTIVE_PARAMS.get()
    if params is None:
        return default
    value = getattr(params, field, None)
    if not isinstance(value, int):
        return default
    return max(lo, min(hi, value))


def is_adaptive_router_enabled() -> bool:
    """Check if the HyPA adaptive query router is enabled via environment variable.

    R329 — default flipped ON -> OFF. Measured on davidath 476 in place
    (``r329-armA-hypaoff`` vs ``r329-armB-hypa``, identical dataset
    fingerprint, arm A reproducing the documented baseline byte-for-byte):
    enabling this path cost QA **Ref Conciseness -0.2094** (0.4390 ->
    0.2296) and **Ref Strict -0.1137**, for +0.0438 Ref Loose. Per-row
    attribution: 73/137 QA rows changed, +138 net references, and one GOLD
    reference dropped (``qa_041`` lost ``Article 50``) -- the R142.1 red
    line. Over-citation is the single axis a frontier model still beats us
    on (.planning/R318-PLAN.md), so this trades away the one thing we were
    trying to win.

    Kept as an opt-in knob rather than deleted: ``top_k_dense`` inside the
    zero-entity BM25 fallback is a genuinely untested slice.
    """
    return os.environ.get("REGENOLD_HYPA_ADAPTIVE_ROUTER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def classify_query_complexity(
    question: str, history_turn_count: int = 1
) -> ComplexityParameters:
    """Classify a question into 3 complexity classes and return HyPA parameter mapping.

    :param question: raw or history-flattened user question text.
    :param history_turn_count: number of prior turns in the conversation.
    :return: ComplexityParameters instance.
    """
    if not question or not question.strip():
        return CLASS_1_PARAMS

    # R329 SECURITY — collapse whitespace runs before any regex runs. Together
    # with the simplified `_DIRECT_ARTICLE_RE` tail this removes the O(N^3)
    # backtracking a padded question could otherwise trigger. Semantically inert
    # for real traffic: word count and token order are unchanged.
    clean_q = _WS_RUN_RE.sub(" ", question.strip())

    # 1. Check for Class 2 (Complex): Multi-context / situational / coreferent / cross-framework / Art 5 / Art 99
    if is_complex_question(clean_q, history_turn_count):
        return CLASS_2_PARAMS

    if re.search(r"\b(?:article\s+(?:5|05|99|099)|prohibited|penalties?|fines?|sanctions?)\b", clean_q, re.IGNORECASE):
        return CLASS_2_PARAMS

    # 2. Check for Class 0 (Simple): Single definition, single direct article query (excluding Art 5/99), short text (<10 words, single question mark)
    words = clean_q.split()
    if len(words) <= 10 and clean_q.count("?") <= 1:
        if _DEFINITION_QUERY_RE.search(clean_q) or _DIRECT_ARTICLE_RE.search(clean_q):
            return CLASS_0_PARAMS

    # 3. Default to Class 1 (Standard): Single-topic compliance/obligation queries
    return CLASS_1_PARAMS
