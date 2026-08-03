"""R299 — Unit tests for Move 1 (OPERATIVE/BACKGROUND partitioning) and Move 2 (completeness verifier).

Validates:
1. OPERATIVE vs BACKGROUND reference partitioning logic (`partition_context_references`).
2. References block formatting with OPERATIVE PROVISIONS and BACKGROUND CONTEXT sections.
3. Prompt clause inclusion in Stage-2 USER message.
4. Deterministic enumerated completeness verifier (`verify_and_enrich_enumerated_completeness`).
5. Off-switches (`REGENOLD_REF_PARTITION=0` and `REGENOLD_COMPLETENESS_VERIFIER=0`).
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from app.data.graph_rag_prompts import (
    completeness_verifier_enabled,
    user_ref_partition_enabled,
)
from app.engines._graph_rag_impl import (
    GraphContext,
    _build_context_references_block,
    partition_context_references,
)
from app.engines.completeness_verifier import (
    is_enumerated_set_question,
    verify_and_enrich_enumerated_completeness,
)


def test_toggles_defaults(monkeypatch):
    """R300 — REF_PARTITION flipped default ON -> OFF. R306 — so did the verifier.

    R299 shipped the partition default-ON with no live ``ab_judge`` gate. The
    R300 review measured it demoting the GOVERNING provision to a "do NOT
    cite" BACKGROUND block on 53% of the real graded batch, which the R72
    prose reconcile then converts into an actual wire deletion of gold
    references (``rg_001``: 4 refs -> 1). Default OFF restores the last
    A/B-validated state; ``REGENOLD_REF_PARTITION=1`` re-enables it for the
    A/B it still owes. See ``user_ref_partition_enabled`` for the full record.

    R306 applied the same judgement to the completeness verifier, which
    R299 also shipped default-ON with no live ``ab_judge`` gate. Measured
    over 1,134 distinct recorded live answers it fires on 29 (2.6%),
    concentrated on the graded July-7 rows, and the supplement it appends
    is routinely inverted law: Article 6(3) derogation conditions
    presented as requirements (12 rows), Article 5 prohibitions presented
    as requirements with degenerate duplicate labels (10 rows), Article 1
    subject-matter and Article 99 fine-tier lists likewise. A
    confidently-wrong legal claim is hard rule #4, the worst defect class
    in this codebase. ``REGENOLD_COMPLETENESS_VERIFIER=1`` re-enables it
    for the A/B it still owes.

    Pinned so that re-enabling either by default is a deliberate,
    visible act.
    """
    monkeypatch.delenv("REGENOLD_REF_PARTITION", raising=False)
    monkeypatch.delenv("REGENOLD_COMPLETENESS_VERIFIER", raising=False)
    assert user_ref_partition_enabled() is False
    assert completeness_verifier_enabled() is False


def test_partition_opt_in_still_works(monkeypatch):
    """The feature must remain reachable for its pending A/B."""
    monkeypatch.setenv("REGENOLD_REF_PARTITION", "1")
    assert user_ref_partition_enabled() is True


def test_toggles_off_switch(monkeypatch):
    monkeypatch.setenv("REGENOLD_REF_PARTITION", "0")
    monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "0")
    assert user_ref_partition_enabled() is False
    assert completeness_verifier_enabled() is False


def test_partition_context_references_role():
    ctx = GraphContext()
    ctx.obligations = [
        {"id": "ob_1", "text": "Importer verification", "article": "23"},
        {"id": "ob_2", "text": "Risk management system", "article": "9"},
        {"id": "ob_3", "text": "Classification rule", "article": "6"},
    ]
    q = "What are the verification obligations of an importer under the EU AI Act?"
    op, bg = partition_context_references(ctx, q)
    assert "Article 23" in op or "23" in op or "Art. 23" in op
    assert "Article 6" in bg or "6" in bg or "Art. 6" in bg
    assert "Article 9" in bg or "9" in bg or "Art. 9" in bg


def test_partition_context_references_explicit_article():
    ctx = GraphContext()
    ctx.obligations = [
        {"id": "ob_1", "text": "Transparency obligations", "article": "50"},
        {"id": "ob_2", "text": "High risk classification", "article": "6"},
    ]
    q = "What are the transparency requirements under Article 50?"
    op, bg = partition_context_references(ctx, q)
    assert any("50" in ref for ref in op)
    assert any("6" in ref for ref in bg)


def test_build_context_references_block_partitioned(monkeypatch):
    monkeypatch.setenv("REGENOLD_REF_PARTITION", "1")
    ctx = GraphContext()
    ctx.obligations = [
        {"id": "ob_1", "text": "Importer verification duties", "article": "23"},
        {"id": "ob_2", "text": "High risk classification", "article": "6"},
    ]

    q = "What are the verification duties of an importer?"
    block = _build_context_references_block(ctx, question=q)
    assert "OPERATIVE PROVISIONS" in block
    assert "BACKGROUND CONTEXT" in block
    assert "Article: 23" in block
    assert "Article: 6" in block


def test_is_enumerated_set_question():
    assert is_enumerated_set_question("What are the importer obligations?") is True
    assert is_enumerated_set_question("List the prohibited practices.") is True
    assert is_enumerated_set_question("Which risk tiers exist?") is True
    assert is_enumerated_set_question("Is a chatbot high risk?") is False


def test_completeness_verifier_appends_missing_points(monkeypatch):
    monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "1")
    q = "What are the obligations of an importer under Article 23?"
    # Answer only mentions point (a)
    answer = "Article 23 requires importers to verify that the provider has carried out conformity assessment (a)."
    res = verify_and_enrich_enumerated_completeness(q, answer, None)
    assert "including points" in res or res != answer
    assert "Article 23" in res


def test_completeness_verifier_disabled_returns_raw(monkeypatch):
    monkeypatch.setenv("REGENOLD_COMPLETENESS_VERIFIER", "0")
    q = "What are the obligations of an importer under Article 23?"
    answer = "Article 23 requires importers to verify conformity assessment (a)."
    res = verify_and_enrich_enumerated_completeness(q, answer, None)
    assert res == answer
