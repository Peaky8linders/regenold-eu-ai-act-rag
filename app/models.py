"""Minimal Pydantic models — only what the Regenold + Graph-RAG path uses.

Extracted from CodexAI's full ``app/models.py``. The GraphRAG types are
identical to the parent repo so the engine code copies verbatim.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """EU AI Act risk classification (Art. 5/6 & Title VIII)."""

    UNACCEPTABLE = "unacceptable"
    PROHIBITED = "prohibited"
    HIGH = "high"
    HIGH_RISK_ANNEX_I = "high_risk_annex_i"
    HIGH_RISK_ANNEX_III = "high_risk_annex_iii"
    LIMITED = "limited"
    MINIMAL = "minimal"
    GPAI = "gpai"
    GPAI_SYSTEMIC = "gpai_systemic"



class AssessmentAnswer(str, Enum):
    """KB question answer states."""

    YES = "yes"
    NO = "no"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class CitationNode(BaseModel):
    """A node from the compliance graph cited in the answer."""

    node_type: Literal["Obligation", "Article", "Dimension", "Gap"]
    node_id: str
    text: str
    article_ref: str = ""


# Upper bound on the flattened question the engine will accept.
#
# This used to be a hard 2 000 characters. That was never a model or
# provider limit — it was a self-imposed Pydantic bound, and on a real
# 18-20 turn conversation it silently amputated the history (and the
# route's own ``[Context anchors — ...]`` prefix) before retrieval ever
# ran. The 7 July 2026 evaluator batch showed 64 of 67 adversarial
# pushback turns pinned at exactly the old cap.
#
# 64 000 characters (~16k tokens) comfortably holds a 20-turn legal
# conversation while still bounding a hostile payload. Override with
# ``REGENOLD_MAX_QUESTION_CHARS`` (set it to 2000 to reproduce the
# pre-R314 behaviour for an A/B).
_MAX_QUESTION_CHARS = 64_000


class GraphRAGRequest(BaseModel):
    """Input to the graph-RAG engine."""

    question: str = Field(min_length=1, max_length=_MAX_QUESTION_CHARS)
    risk_level: RiskLevel | None = None
    system_description: str | None = Field(default=None, max_length=1_000)
    answers: dict[str, AssessmentAnswer] = Field(default_factory=dict)
    history_turn_count: int = Field(default=1, ge=0)
    """R51 — number of user+assistant turns BEFORE the live question.
    Threaded from the route's ``_build_question_from_history`` so the
    complex-question gate can fire on multi-turn finals (3+ turns +
    short coreferent). Default 1 keeps single-turn callers unaffected.
    """
    resolved_question: str | None = Field(default=None, max_length=_MAX_QUESTION_CHARS)
    bridging_context: list[str] = Field(default_factory=list)


class GraphRAGResponse(BaseModel):
    """Engine output — answer + citations + confidence + telemetry."""

    answer: str
    citations: list[CitationNode] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reasoning_trace: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    graph_stats: dict = Field(default_factory=dict)
    kg_answer: str = ""
