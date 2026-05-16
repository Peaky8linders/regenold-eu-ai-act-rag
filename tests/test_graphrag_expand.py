"""Tests for ``app.engines.graphrag_expand`` — Layer D auto-expand.

Architecture PDF: "when Article 6 is pulled, its dependent requirements
under Article 9 (Risk Management System) and Article 61 (Post-market
monitoring) are automatically pulled along the graph edge paths."
"""
from __future__ import annotations

import pytest

from app.engines.graphrag_expand import (
    _HRAIS_CHAINS,
    expand_citations,
    should_expand_for_question,
)


# ── should_expand_for_question ────────────────────────────────────────────


@pytest.mark.parametrize(
    "question,expected",
    [
        # Scenario shapes — expand
        ("We are a provider of high-risk AI", True),
        ("I am a deployer of credit scoring", True),
        ("Our company is building a hiring AI", True),
        ("role: provider, intended use: hiring", True),
        ("input data: biometric, domain: workplace", True),
        # QA shapes — don't expand
        ("What is a deployer?", False),
        ("Is emotion recognition prohibited?", False),
        ("What does Article 5 say?", False),
        ("How are providers regulated?", False),
        # Edge cases
        ("", False),
        (None, False),
    ],
)
def test_should_expand_for_question(question, expected):
    """Scenario shape triggers expansion; QA shape doesn't."""
    if question is None:
        assert should_expand_for_question("") is expected
    else:
        assert should_expand_for_question(question) is expected


# ── expand_citations ──────────────────────────────────────────────────────


def test_expand_empty_input_passthrough():
    """No input refs → empty output, never raises."""
    out = expand_citations([], budget=10, question="We are a provider")
    assert out == []


def test_expand_budget_zero_passthrough():
    """Budget already exhausted → no expansion."""
    refs = ["Article 6", "Article 9"]
    out = expand_citations(refs, budget=2, question="We are a provider")
    assert out == refs


def test_expand_skips_qa_shape_questions():
    """QA-shape question → no expansion (single-article gold protection)."""
    refs = ["Article 6"]
    out = expand_citations(refs, budget=10, question="What is high-risk AI?")
    assert out == refs


def test_expand_art6_pulls_obligation_chain():
    """Architecture-PDF Art. 6 → Art. 9 + Art. 11 etc."""
    refs = ["Article 6"]
    out = expand_citations(refs, budget=10, question="We are a provider")
    # The architecture-PDF-named chain MUST be present.
    assert "Article 6" in out
    # Spec calls out Art. 9 explicitly.
    assert "Article 9" in out
    # Plus other HRAIS chain members.
    chain_hits = sum(1 for r in out if r in {
        "Article 9", "Article 10", "Article 11", "Article 13",
        "Article 14", "Article 15", "Article 16", "Article 17",
        "Annex III", "Annex IV",
    })
    assert chain_hits >= 5, f"expected ≥5 chain hits, got {chain_hits} in {out}"


def test_expand_annex_iii_pulls_obligations():
    """Annex III hit → high-risk obligation chain pulled."""
    refs = ["Annex III"]
    out = expand_citations(refs, budget=10, question="We are a deployer")
    assert "Annex III" in out
    # Annex III maps to the same high-risk obligation chain.
    assert "Article 6" in out
    chain_hits = sum(1 for r in out if r in {
        "Article 6", "Article 9", "Article 11", "Article 13",
        "Article 16", "Article 26", "Article 27",
    })
    assert chain_hits >= 4, f"expected ≥4 chain hits, got {chain_hits} in {out}"


def test_expand_preserves_input_order():
    """Original refs stay at the head; expansion appends at tail."""
    refs = ["Article 5", "Article 6"]
    out = expand_citations(refs, budget=10, question="We are a provider")
    # First two outputs must be the original refs in original order.
    assert out[:2] == refs


def test_expand_deduplicates():
    """Duplicate xref targets are not double-counted."""
    refs = ["Article 6", "Annex III"]
    out = expand_citations(refs, budget=15, question="We are a provider")
    assert len(out) == len(set(out)), f"dupes in output: {out}"


def test_expand_respects_budget():
    """Output length never exceeds ``budget``."""
    refs = ["Article 6"]
    for budget in (1, 3, 5, 10, 20):
        out = expand_citations(refs, budget=budget, question="We are a provider")
        assert len(out) <= budget, f"budget {budget} exceeded: {out}"


def test_expand_passes_through_unknown_refs():
    """A malformed ref doesn't crash — it just doesn't expand."""
    refs = ["TotallyMadeUp 9999"]
    out = expand_citations(refs, budget=10, question="We are a provider")
    # The original survives; no expansion happened (no xref entries).
    assert out == refs


def test_hrais_chains_are_consistent():
    """Every chain entry should be a parseable user-facing ref."""
    import re
    valid = re.compile(r"^(?:Art\.\s+\d+(?:\.[\w.]+)?|Annex\s+[IVXLCDM]+(?:\.[\w.]+)?)$")
    for hub, chain in _HRAIS_CHAINS.items():
        assert valid.match(hub), f"hub {hub!r} not parseable"
        for ref in chain:
            assert valid.match(ref), f"chain ref {ref!r} (hub={hub}) not parseable"
            assert ref != hub, f"self-edge {hub} → {hub} in HRAIS chain"


def test_expand_question_none_keeps_expanding():
    """``question=None`` means "no shape gate" → expansion is applied."""
    refs = ["Article 6"]
    out = expand_citations(refs, budget=10, question=None)
    # No question gate → expand always (this is the bench-time / test path).
    assert len(out) > 1
    assert "Article 9" in out
