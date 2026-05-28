"""R93 — semantic-aware citation faithfulness on the Stage-2 path.

Covers the paraphrase-robust coverage signal added to
``app.integrations.regenold.grounded_prose`` plus its recall-safe
invariants. The route-level wire (``REGENOLD_STAGE2_REF_AUGMENT``) is
gated on ``stage2_landed`` so the deterministic davidath bench is
byte-identical by construction; these unit tests pin the building blocks
the wire depends on.

SOTA grounding: CiteFix (ACL 2025) keyword+semantic blend; FRONT
quote-first grounding; ReClaim one-cite-per-sentence. The semantic
signal is the fix to the R90 −0.21 ref_loose regression (BM25-vs-KB-
summary under-detecting coverage on Sonnet-paraphrased prose).
"""
from __future__ import annotations

import os

import pytest

from app.data.kb_search import _tokenize
from app.integrations.regenold.grounded_prose import (
    _answer_covers_ref,
    _sem_coverage_threshold,
    _SEM_COVERAGE_DEFAULT_THRESHOLD,
    augment_with_ref_descriptions,
    semantic_coverage_map,
)


# ── semantic_coverage_map ───────────────────────────────────────────────


def test_semantic_coverage_map_empty_input_returns_empty():
    assert semantic_coverage_map("") == {}
    assert semantic_coverage_map("   ") == {}


def test_semantic_coverage_map_never_raises():
    # Pathological inputs must collapse to {} rather than raise.
    for bad in ("\x00", "—" * 5000, "Article", "12345 67890"):
        out = semantic_coverage_map(bad)
        assert isinstance(out, dict)


def test_semantic_coverage_map_keys_are_internal_form():
    # When the embeddings assets are present, keys are internal refs
    # ("Art. N" / "Annex X"); when absent, {} — both are acceptable, but
    # if non-empty every key must be internal-form (never "Article N").
    out = semantic_coverage_map(
        "High-risk AI systems must keep automatically generated logs and "
        "maintain technical documentation demonstrating conformity."
    )
    assert isinstance(out, dict)
    for k, v in out.items():
        assert k.startswith("Art. ") or k.startswith("Annex "), k
        assert not k.startswith("Article "), k
        assert -1.0 <= v <= 1.0


# ── _sem_coverage_threshold env handling ────────────────────────────────


def test_sem_threshold_default(monkeypatch):
    monkeypatch.delenv("REGENOLD_REF_SEM_THRESHOLD", raising=False)
    assert _sem_coverage_threshold() == _SEM_COVERAGE_DEFAULT_THRESHOLD


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.6", 0.6),
        ("0.0", 0.0),
        ("1.0", 1.0),
        ("", _SEM_COVERAGE_DEFAULT_THRESHOLD),
        ("not-a-float", _SEM_COVERAGE_DEFAULT_THRESHOLD),
        ("-0.2", _SEM_COVERAGE_DEFAULT_THRESHOLD),  # out of range → default
        ("1.5", _SEM_COVERAGE_DEFAULT_THRESHOLD),   # out of range → default
    ],
)
def test_sem_threshold_env_override(monkeypatch, raw, expected):
    monkeypatch.setenv("REGENOLD_REF_SEM_THRESHOLD", raw)
    assert _sem_coverage_threshold() == expected


# ── _answer_covers_ref three-signal behaviour ───────────────────────────


def test_covers_ref_semantic_none_is_byte_identical():
    """semantic_covered=None must reproduce the pre-R93 two-signal path."""
    # Literal signal: answer names the article → covered regardless of map.
    toks = frozenset(_tokenize("Article 13 requires transparency."))
    assert _answer_covers_ref(
        toks, "Art. 13", answer_text="Article 13 requires transparency."
    ) is True
    assert _answer_covers_ref(
        toks,
        "Art. 13",
        answer_text="Article 13 requires transparency.",
        semantic_covered=None,
    ) is True


def test_covers_ref_semantic_signal_fires_when_lexical_fails():
    """A strong semantic match marks coverage even when literal+BM25 miss."""
    # An answer that does NOT name Art. 99 and shares ~no tokens with its
    # KB stub. Without the semantic map → not covered (BM25 overlap < 4,
    # no literal mention). With a high semantic sim → covered.
    answer = "The xylophone repairs quietly under moonlit harbours."
    toks = frozenset(_tokenize(answer))
    assert (
        _answer_covers_ref(toks, "Art. 99", answer_text=answer) is False
    )
    assert (
        _answer_covers_ref(
            toks,
            "Art. 99",
            answer_text=answer,
            semantic_covered={"Art. 99": 0.95},
        )
        is True
    )


def test_covers_ref_semantic_below_threshold_falls_through():
    """A weak semantic sim does NOT count as coverage."""
    answer = "The xylophone repairs quietly under moonlit harbours."
    toks = frozenset(_tokenize(answer))
    # 0.10 is well below the 0.45 default → must not flip to covered via
    # the semantic signal (and lexical/literal both fail here).
    assert (
        _answer_covers_ref(
            toks,
            "Art. 99",
            answer_text=answer,
            semantic_covered={"Art. 99": 0.10},
        )
        is False
    )


def test_covers_ref_literal_still_wins_over_semantic():
    """Literal mention is sufficient even with no semantic map entry."""
    answer = "Penalties are set out in Article 99."
    toks = frozenset(_tokenize(answer))
    assert (
        _answer_covers_ref(
            toks, "Art. 99", answer_text=answer, semantic_covered={}
        )
        is True
    )


def test_covers_ref_threshold_respected(monkeypatch):
    answer = "Some unrelated prose about gardening tools."
    toks = frozenset(_tokenize(answer))
    monkeypatch.setenv("REGENOLD_REF_SEM_THRESHOLD", "0.80")
    # 0.6 < 0.8 → not covered.
    assert (
        _answer_covers_ref(
            toks, "Art. 13", answer_text=answer, semantic_covered={"Art. 13": 0.6}
        )
        is False
    )
    # 0.85 >= 0.8 → covered.
    assert (
        _answer_covers_ref(
            toks, "Art. 13", answer_text=answer, semantic_covered={"Art. 13": 0.85}
        )
        is True
    )


# ── augment_with_ref_descriptions recall-safe invariants ────────────────


def test_augment_accepts_semantic_param_and_is_recall_safe():
    answer = "Article 13 requires transparency for high-risk AI systems."
    out = augment_with_ref_descriptions(
        answer,
        ["Article 13", "Article 26"],
        question="What transparency duties apply?",
        semantic_covered={"Art. 13": 0.9, "Art. 26": 0.9},
    )
    # Recall-safe: never empties, never raises, returns a string.
    assert isinstance(out, str)
    assert out.strip()


def test_augment_semantic_covered_suppresses_redundant_append():
    """When the semantic map marks every ref covered, no clause is added."""
    answer = "Article 13 requires transparency for high-risk AI systems."
    # Both refs marked strongly semantically covered → augmenter should
    # leave the answer unchanged (no redundant describing clause).
    out = augment_with_ref_descriptions(
        answer,
        ["Article 13"],
        question="",
        semantic_covered={"Art. 13": 0.99},
    )
    assert out == answer


def test_augment_none_semantic_is_unchanged_default_behaviour():
    """semantic_covered defaulting to None must not change legacy output."""
    answer = "High-risk providers carry obligations."
    refs = ["Article 16"]
    out_default = augment_with_ref_descriptions(answer, refs, question="")
    out_explicit_none = augment_with_ref_descriptions(
        answer, refs, question="", semantic_covered=None
    )
    assert out_default == out_explicit_none


def test_augment_never_raises_on_bad_semantic_map():
    answer = "Article 99 sets penalties."
    out = augment_with_ref_descriptions(
        answer,
        ["Article 99"],
        question="",
        semantic_covered={"Art. 99": "not-a-float"},  # type: ignore[dict-item]
    )
    assert isinstance(out, str)
    assert out.strip()
