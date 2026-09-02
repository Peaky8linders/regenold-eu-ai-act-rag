"""Simplification B: Native Dual-Pass Retrieval for Multi-Turn Conversations.

Eliminates Stage-0 LLM rewriting by performing deterministic dual-pass retrieval:
- Pass 1 (Immediate / Operative): Extracts provisions directly asked in the live question
  (e.g., 'fines' -> Article 99, 'deployers' -> Article 26).
- Pass 2 (Contextual / Topic): Extracts provisions from prior user turns / context anchors
  (e.g., 'emotion recognition' -> Article 5(1)(f), 'biometric' -> Annex III).
- Fusion: Combines candidates (Pass 1 leads, Pass 2 follows) without parsing raw assistant prose,
  completely eliminating multi-turn history bleed.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engines.graph_rag.models import GraphQuery

logger = logging.getLogger(__name__)

_DUAL_PASS_ENV = "REGENOLD_DUAL_PASS_RETRIEVAL"


def is_dual_pass_retrieval_enabled() -> bool:
    """Return True if Dual-Pass Retrieval is enabled.

    Default OFF ('0') per Hard Rule #8 until cleared via live evaluation.
    Set REGENOLD_DUAL_PASS_RETRIEVAL=1 to enable.
    """
    return os.environ.get(_DUAL_PASS_ENV, "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def extract_context_anchors_text(context_question: str) -> str:
    """Extract the context anchors text or first user turn from the full prompt.

    Excludes any assistant turns to prevent multi-turn history bleed.
    """
    if not context_question:
        return ""
    # 1. Match explicit [Context anchors — ...] prefix if present
    anchor_match = re.search(r"\[Context anchors\s*—\s*([^\]]+)\]", context_question, re.IGNORECASE)
    if anchor_match:
        return anchor_match.group(0)

    # 2. Extract first user turn if present (skipping assistant turns)
    user_match = re.search(r"(?:^|\n)User:\s*([^\n]+)", context_question, re.IGNORECASE)
    if user_match:
        return user_match.group(1).strip()

    return ""


def build_context_retrieval_text(
    anchor_line: str,
    prior_turns: Iterable[Any],
    *,
    max_user_turns: int = 4,
    max_chars: int = 4_000,
) -> str:
    """Build the clean input for contextual retrieval.

    Retrieval needs the prior users' *subject matter* as well as explicit
    article/role/risk anchors.  The compact anchor line alone cannot recover
    a prior statement such as ``emotion recognition in workplaces`` when the
    user did not name Article 5.  Keep the recent user turns, never assistant
    prose, and bound the result so long conversations do not become a second
    unbounded retrieval prompt.  Formal anchors from older turns remain in
    ``anchor_line``.
    """
    user_turns = [
        str(getattr(turn, "content", "") or "").strip()
        for turn in prior_turns
        if getattr(turn, "role", "") == "user"
        and str(getattr(turn, "content", "") or "").strip()
    ]
    recent_turns = user_turns[-max_user_turns:]
    parts = [anchor_line.strip()] if anchor_line.strip() else []
    parts.extend(f"User: {turn}" for turn in recent_turns)
    return "\n".join(parts)[:max_chars]


def dual_pass_parse(
    resolved_question: str,
    context_question: str,
    deterministic_parse_fn: Callable[[str], GraphQuery],
    context_retrieval_text: str | None = None,
) -> GraphQuery:
    """Execute dual-pass deterministic parse.

    Pass 1 (Immediate Operative): parse resolved_question (the live user turn).
    Pass 2 (Contextual Anchors): parse anchor text extracted from context_question
    without parsing assistant responses.

    Returns a fused GraphQuery where operative provisions lead.
    """
    pass1_query = deterministic_parse_fn(resolved_question)

    # ``context_retrieval_text`` is supplied by the route from prior USER
    # turns only.  The fallback keeps direct engine callers backward
    # compatible with the existing formatted-history input.
    anchor_text = context_retrieval_text or extract_context_anchors_text(context_question)
    pass2_query = deterministic_parse_fn(anchor_text) if anchor_text else None

    # Order-preserving deduplication: Pass 1 operative entities lead, Pass 2 context follows
    combined_entities: list[str] = list(pass1_query.entities)
    if pass2_query:
        for ent in pass2_query.entities:
            if ent not in combined_entities:
                combined_entities.append(ent)

    query = pass1_query
    query.entities = combined_entities

    # Inherit risk context from prior turn if live turn does not specify one
    if pass2_query and pass2_query.risk_context and not query.risk_context:
        query.risk_context = pass2_query.risk_context

    return query
