"""Tests for the explicit 4-task router (Davvetas Layer B)."""
from __future__ import annotations

import pytest

from app.engines.task_router import (
    TASK_LABELS,
    classify_task_4way,
    task_pipeline_description,
)


def test_all_labels_have_descriptions():
    """Every label in :data:`TASK_LABELS` has a non-empty description."""
    for label in TASK_LABELS:
        desc = task_pipeline_description(label)
        assert desc, f"task {label!r} missing description"
        assert len(desc) >= 20, f"task {label!r} description too short: {desc!r}"


@pytest.mark.parametrize(
    "question,expected",
    [
        # Scenario shapes → risk
        ("We are a provider deploying biometric identification", "risk"),
        ("I am a deployer of credit-scoring AI", "risk"),
        ("Our company is building an AI system for hiring", "risk"),
        # Explicit risk-tier vocabulary → risk
        ("Is this AI system prohibited under the AI Act?", "risk"),
        ("What risk level applies to facial-recognition AI?", "risk"),
        ("How is high-risk AI classified?", "risk"),
        # Definition questions → article
        ("What is a provider?", "article"),
        ("How is deployer defined?", "article"),
        ("Definition of GPAI model", "article"),
        ("What does substantial modification mean?", "article"),
        # Article references → article
        ("What does Article 13 say?", "article"),
        ("Annex III categories", "article"),
        # Obligation verbs → obligation
        ("What documents must we keep?", "obligation"),
        ("What requirements apply to providers of high-risk AI?", "obligation"),
        ("Do I need conformity assessment?", "obligation"),
        ("What is the risk management system obligation?", "obligation"),
        # Open / fallback
        ("Explain how the AI Act applies extraterritorially.", "open"),
        ("How does this regulation compare to GDPR?", "open"),
        ("Tell me about the regulation history.", "open"),
    ],
)
def test_classify_task_4way_heuristics(question, expected):
    """The shape heuristics map known prototypes to the expected task."""
    assert classify_task_4way(question) == expected, (
        f"{question!r} should map to {expected!r}"
    )


def test_classify_task_4way_uses_intent_label_when_provided():
    """An explicit fine-grained intent label overrides shape heuristics."""
    # Without label — looks like a scenario → "risk"
    q = "We are a deployer; what records do we need to keep?"
    # Heuristic falls into "risk" because scenario marker fires first.
    assert classify_task_4way(q) == "risk"
    # With LLM intent label — collapses to "obligation"
    assert classify_task_4way(q, intent_label="role_obligations") == "obligation"
    # With LLM intent label that points elsewhere
    assert classify_task_4way(q, intent_label="incident_reporting") == "obligation"


def test_classify_task_4way_unknown_label_falls_through():
    """An unrecognised intent label falls through to shape heuristics."""
    q = "What is a provider?"
    assert classify_task_4way(q, intent_label="nonexistent_label") == "article"


def test_classify_task_4way_empty_question():
    """An empty question doesn't crash — falls through to ``open``."""
    assert classify_task_4way("") == "open"
    assert classify_task_4way("   ") == "open"
    assert classify_task_4way(None) == "open"  # type: ignore[arg-type]


def test_classify_task_4way_returns_only_canonical_labels():
    """Every output is one of the four canonical labels."""
    test_questions = [
        "Hello?", "asdf", "We are a provider", "What is X?",
        "Provide a list", "Random nonsense ksldjflksjdf",
    ]
    for q in test_questions:
        label = classify_task_4way(q)
        assert label in TASK_LABELS, f"{q!r} produced non-canonical label {label!r}"


def test_classify_task_4way_intent_label_case_insensitive():
    """Mixed-case intent labels are normalised before lookup."""
    q = "blah blah blah"
    assert classify_task_4way(q, intent_label="ROLE_OBLIGATIONS") == "obligation"
    assert classify_task_4way(q, intent_label="Role_Obligations") == "obligation"
