"""Minimal Pydantic models — only what the Regenold + Graph-RAG path uses.

Extracted from CodexAI's full ``app/models.py``. The GraphRAG types are
identical to the parent repo so the engine code copies verbatim.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """EU AI Act risk classification (Art. 5/6)."""

    UNACCEPTABLE = "unacceptable"
    HIGH = "high"
    LIMITED = "limited"
    MINIMAL = "minimal"


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


class GraphRAGRequest(BaseModel):
    """Input to the graph-RAG engine."""

    question: str = Field(min_length=1, max_length=2_000)
    risk_level: RiskLevel | None = None
    system_description: str | None = Field(default=None, max_length=1_000)
    answers: dict[str, AssessmentAnswer] = Field(default_factory=dict)
    history_turn_count: int = Field(default=1, ge=0)
    """R51 — number of user+assistant turns BEFORE the live question.
    Threaded from the route's ``_build_question_from_history`` so the
    complex-question gate can fire on multi-turn finals (3+ turns +
    short coreferent). Default 1 keeps single-turn callers unaffected.
    """


class GraphRAGResponse(BaseModel):
    """Engine output — answer + citations + confidence + telemetry."""

    answer: str
    citations: list[CitationNode] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reasoning_trace: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    graph_stats: dict = Field(default_factory=dict)
