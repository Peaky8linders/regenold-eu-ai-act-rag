"""Explicit Four-Task Modular Pipeline router — Davvetas et al. 2026.

Closes Layer B of the High-Precision RAG architecture
(``EU_AI_Act_High_Precision_RAG_Architecture.pdf``):

> Queries must not be processed via a generic single-shot QA prompt.
> Instead, incoming system queries are captured by an intent-classification
> semantic router that branches execution into one of four domain-specific
> pipelines.

The four canonical tasks per the Davvetas benchmark paper
(``AI ACt reproducible benchmark.pdf``, §3.2 — Task taxonomy):

| Task                | What it does                                            |
| ------------------- | ------------------------------------------------------- |
| **risk**            | Risk-tier classification (prohibited/high/limited/min)  |
| **article**         | Article retrieval / verification — incl. definitions    |
| **obligation**      | Compile mandatory developer/deployer governance actions |
| **open**            | Free-form interpretive QA, scope edge-cases             |

The router is **deterministic, zero-cost, zero-dependency** — it reads the
question and the existing :data:`app.llm.intent_classifier.INTENT_LABELS`
fine-grained 15-way label (when available) and collapses to one of the
four task labels.

Why a separate module instead of folding into the route?

* Lets us **stamp the task label** into the audit chain entry for
  forensics — "this query went through the obligation pipeline" is a
  more useful trace than the implicit branch fanout.
* Future-proofs against per-task **metric reporting** in the bench
  runner (`evals/bench/runner.py` could break out per-task F1).
* Keeps the route file from sprouting another conditional cascade.

The router does NOT change the engine's behaviour — every task today
still routes through ``ask_compliance_question``; the dispatch is
**informational** (annotates the request) until we wire per-task
pipelines in a future round.
"""
from __future__ import annotations

import re
from typing import Literal


TaskLabel = Literal["risk", "article", "obligation", "open"]


# Canonical four-task surface, ordered by Davvetas Table 1 (prohibited
# scenarios) → Table 3 (QA pairs). The router returns one of these.
TASK_LABELS: tuple[TaskLabel, ...] = ("risk", "article", "obligation", "open")


# Fine-grained intent label → 4-task collapse. Sourced from
# :data:`app.llm.intent_classifier.INTENT_LABELS`. Any label missing
# from this map falls through to ``"open"`` (legal QA).
_INTENT_TO_TASK: dict[str, TaskLabel] = {
    # Risk-tier classification — the question (or scenario) asks
    # "what level of risk is this AI system?"
    "risk_classification": "risk",
    # Article retrieval / definition — the question names a specific
    # article or asks for a term's definition.
    "article_lookup": "article",
    "definition": "article",
    "timeline_question": "article",
    # Obligation generation — what must each operator do?
    "role_obligations": "obligation",
    "transparency_obligation": "obligation",
    "incident_reporting": "obligation",
    "fria": "obligation",
    "compliance_checklist": "obligation",
    "gpai_systemic": "obligation",
    "sandbox": "obligation",
    "penalty_inquiry": "obligation",  # technically about Art. 99, but
                                       # always pairs with "what do I need
                                       # to do to avoid the fine?"
    # Free-form QA / scope edge cases.
    "comparative": "open",
    "out_of_scope": "open",
    "other": "open",
}


# Direct shape detectors — used when no fine-grained intent label is
# available (LLM-classifier degraded / disabled) AND the question shape
# is unambiguous enough to skip the LLM call. These mirror the
# `_DEFINITION_TERM_PATTERNS` / scenario-shape heuristics elsewhere in
# the engine; we duplicate the simplest probes to keep this module a
# zero-dependency drop-in.

_SCENARIO_RE = re.compile(
    r"\b(?:we\s+are\s+(?:a|an|the)|i\s+am\s+(?:a|an|the)|"
    r"our\s+(?:company|team|organisation|firm|startup)\s+is)\b",
    re.IGNORECASE,
)

_RISK_TIER_RE = re.compile(
    r"\b(?:risk\s+(?:level|tier|category|classification)|"
    r"prohibited|high[-\s]?risk|limited[-\s]?risk|minimal[-\s]?risk|"
    r"is\s+this\s+(?:prohibited|allowed|banned))\b",
    re.IGNORECASE,
)

_OBLIGATION_RE = re.compile(
    r"\b(?:what\s+(?:obligations?|requirements?|documents?|records?)\b|"
    r"what\s+must\s+\w+|"
    r"what\s+(?:do|does)\s+(?:we|i|providers?|deployers?|importers?|"
    r"distributors?|operators?)\s+(?:need|have)\s+to|"
    r"compliance(?:\s+(?:with|requirement))|"
    r"conformity\s+assessment|"
    r"declaration\s+of\s+conformity|"
    r"risk\s+management\s+system|"
    r"(?:notify|notification|notifying)\s+the\s+(?:authority|authorities|"
    r"market\s+surveillance))\b",
    re.IGNORECASE,
)

_DEFINITION_RE = re.compile(
    r"\b(?:what\s+is\s+(?:a|an|the)?\s*\w+\??\s*$|"  # "What is a deployer?"
    r"what\s+is\s+(?:a|an|the)\s+\w+(?:\s+under\b|\s+in\b)|"
    r"how\s+is\s+\w+\s+defined|"
    r"definition\s+of\s+\w+|"
    r"what\s+does\s+(?:.+?)\s+mean\b)",   # allow multi-word terms
    re.IGNORECASE,
)

_ARTICLE_REF_RE = re.compile(
    r"\b(?:art(?:icle)?\.?\s*\d+|annex\s+(?:[IVX]+|\d+))\b",
    re.IGNORECASE,
)


def classify_task_4way(
    question: str,
    *,
    intent_label: str | None = None,
) -> TaskLabel:
    """Collapse the question + optional fine-grained intent into one of 4 tasks.

    Priority order (highest first):

    1. Fine-grained ``intent_label`` (from :mod:`app.llm.intent_classifier`)
       — when present and recognised, use the mapping table above.
    2. Question-shape heuristics — scenario shape → risk; explicit
       article reference → article; obligation verbs → obligation.
    3. Default fallthrough → ``"open"``.

    The router NEVER raises — every input maps to one of the four labels.

    Examples:

    >>> classify_task_4way("We are a provider deploying biometric ID")
    'risk'
    >>> classify_task_4way("What is a deployer?")
    'article'
    >>> classify_task_4way("What documents must we keep?")
    'obligation'
    >>> classify_task_4way("Is the AI Act extraterritorial?")
    'open'
    """
    # 1. LLM-classified fine label takes priority.
    if intent_label:
        mapped = _INTENT_TO_TASK.get(intent_label.strip().lower())
        if mapped is not None:
            return mapped

    # 2. Question-shape heuristics. Order matters — obligation verbs
    # outrank risk-tier vocabulary because "what requirements apply to
    # providers of high-risk AI" is fundamentally an obligation question
    # despite the "high-risk" keyword in it. Definition outranks article
    # ref because "What is a provider?" and "What does Article 13 say?"
    # are both article-retrieval but the definition path is more specific.
    q = (question or "").strip()
    if not q:
        return "open"

    # 2a. Scenario shape ("We are a provider deploying X...") → risk.
    if _SCENARIO_RE.search(q):
        return "risk"
    # 2b. Obligation verbs / compliance vocabulary → obligation. Must
    # precede risk-tier check so "high-risk obligations" routes correctly.
    if _OBLIGATION_RE.search(q):
        return "obligation"
    # 2c. Explicit risk-tier vocabulary → risk.
    if _RISK_TIER_RE.search(q):
        return "risk"
    # 2d. Definition shape → article (article-retrieval, definition variant).
    if _DEFINITION_RE.search(q):
        return "article"
    # 2e. Explicit Article / Annex reference → article (verification).
    if _ARTICLE_REF_RE.search(q):
        return "article"

    # 3. Default: open legal QA.
    return "open"


def task_pipeline_description(task: TaskLabel) -> str:
    """One-line human-readable description of each task pipeline.

    Used by the audit-chain payload to stamp **why** a particular
    pipeline branch fired — turns a 4-letter task code into useful
    forensic context.
    """
    return {
        "risk": "Risk-tier classification — prohibited/high/limited/minimal",
        "article": "Article retrieval — exact article match or definition lookup",
        "obligation": "Obligation generation — operator governance actions",
        "open": "Open legal QA — interpretive / scope edge cases",
    }[task]


__all__ = [
    "TASK_LABELS",
    "TaskLabel",
    "classify_task_4way",
    "task_pipeline_description",
]
