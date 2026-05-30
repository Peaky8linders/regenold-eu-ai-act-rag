"""R97 — Adaptive answer-mode router (deterministic verbatim vs LLM synthesis).

Decides, per request, whether the wire answer should be the fast,
deterministic VERBATIM provision quote (R94) or an LLM-SYNTHESISED Sonnet
answer produced by the Stage-2 polish path (Claude Max wrapper).

Background
----------
R94 made verbatim exact-text the default answer surface; R96 then disabled
Stage-2 polish whenever verbatim was on, because the route REPLACES the
answer with the verbatim EUR-Lex text and discards any polished prose. That
coupling is correct for **simple single-turn QA** ("What does Article 13
require?" → quote Article 13 verbatim) but wrong for **multi-turn / nuanced**
conversations where the user needs synthesis across turns that a verbatim
dump cannot give — coreference ("does the regulator you mentioned require
X?"), role flips, two-article conflict reconciliation, cross-framework
questions. R97 routes those — and only those — to the LLM, keeping the fast
deterministic path for everything else.

This module is the single source of truth for that decision. Pure-stdlib,
module-level, ~µs per call. Fail-soft: any exception returns VERBATIM (the
safe deterministic default), so a router bug can never strand the route.
"""
from __future__ import annotations

import enum
import os
from dataclasses import dataclass

from app.engines.question_complexity import is_complex_question


class AnswerMode(enum.Enum):
    """The two answer-generation pathways."""

    VERBATIM = "verbatim"
    SYNTHESIS = "synthesis"


# Synthesis-heavy parsed intents — these require reasoning across multiple
# obligations / frameworks, not a single-provision quote.
_SYNTHESIS_INTENTS = frozenset({"gap_analysis", "cross_framework"})

# The route's multi-turn flatten marker (see
# ``routes/regenold.py::_build_question_from_history``). Present only when
# prior conversation turns exist, so it is the unambiguous multi-turn signal.
_MULTI_TURN_MARKER = "Conversation so far:"


@dataclass(frozen=True)
class RouteDecision:
    """Result of :func:`select_answer_mode`."""

    mode: AnswerMode
    reason: str

    @property
    def is_synthesis(self) -> bool:
        return self.mode is AnswerMode.SYNTHESIS


def _env_on(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def verbatim_enabled() -> bool:
    """``REGENOLD_VERBATIM_ANSWER`` — default ON since R94.

    Read fresh per call so a Railway env-var rebind takes effect on the next
    request — same contract as the route's verbatim block.
    """
    return _env_on("REGENOLD_VERBATIM_ANSWER", "1")


def answer_router_enabled() -> bool:
    """``REGENOLD_ANSWER_ROUTER`` — default ON (R97).

    Set to ``0`` to restore exact R96 behaviour: under verbatim mode,
    Stage-2 never runs (verbatim-only). This is the A/B baseline knob and a
    one-env rollback.
    """
    return _env_on("REGENOLD_ANSWER_ROUTER", "1")


def is_multi_turn(question: str, history_turn_count: int) -> bool:
    """True when the request carries prior conversation turns.

    The route prepends ``"Conversation so far:\\n…\\n\\nLatest question:\\n"``
    only when prior turns exist, so the marker is the primary signal.
    ``history_turn_count >= 2`` (≥1 prior user+assistant pair) is the
    fallback for callers that pass an un-flattened question.
    """
    if question and _MULTI_TURN_MARKER in question:
        return True
    return history_turn_count >= 2


def select_answer_mode(
    question: str,
    history_turn_count: int = 1,
    query: object | None = None,
) -> RouteDecision:
    """Route a request to VERBATIM (deterministic) or SYNTHESIS (LLM).

    Returns SYNTHESIS when ANY of:

    1. **multi-turn** — the verbatim dump cannot synthesise across turns
       (the user's primary concern: coreference, role flips, conflict
       reconciliation that span the conversation).
    2. **nuanced single-turn** — :func:`is_complex_question` fires
       (conflict, role-ambiguity, cross-framework, borderline-prohibition,
       GPAI boundary).
    3. **synthesis-heavy parsed intent** — ``query.intent`` in
       ``{gap_analysis, cross_framework}``.

    Else VERBATIM. Fail-soft: any exception returns VERBATIM.

    :param question: the (possibly flattened multi-turn) question string.
    :param history_turn_count: prior user+assistant turn count from the route.
    :param query: optional parsed ``GraphQuery`` with an ``intent`` attr.
    """
    try:
        if not question or not question.strip():
            return RouteDecision(AnswerMode.VERBATIM, "empty_question")
        if is_multi_turn(question, history_turn_count):
            return RouteDecision(AnswerMode.SYNTHESIS, "multi_turn")
        if is_complex_question(question, history_turn_count):
            return RouteDecision(AnswerMode.SYNTHESIS, "complex_question")
        intent = getattr(query, "intent", None)
        if intent in _SYNTHESIS_INTENTS:
            return RouteDecision(AnswerMode.SYNTHESIS, f"intent:{intent}")
        return RouteDecision(AnswerMode.VERBATIM, "simple_qa")
    except Exception:  # noqa: BLE001 — never break the route; default deterministic
        return RouteDecision(AnswerMode.VERBATIM, "router_error")
