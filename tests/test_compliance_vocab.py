"""Regression test for R46 B6 — single compliance-vocabulary registry.

Asserts the invariants the canonical
:mod:`app.data.compliance_vocab` module guarantees, so a future edit
to any of the three downstream sites can't silently de-tune the
others:

* The union covers every term that was in any of the three sites
  before the refactor (preserve the historical surface byte-for-byte).
* Each derived narrower set is a subset of the union.
* No duplicates after normalisation, no empty strings.
* Module-level constants only — no per-call rebuild.
"""

from __future__ import annotations

from app.data import compliance_vocab
from app.data.compliance_vocab import (
    COMPLIANCE_DOMAIN_NOUNS,
    DIMENSION_KEYWORDS,
    PRACTICE_KEYWORDS,
    VERDICT_DOMAIN_NOUNS,
)
from app.data.ontology import PRACTICE_REGISTRY
from app.integrations.regenold import scope as _scope_mod


# ── Pre-refactor surfaces (every term that USED to live in the three sites) ──

# Source: app/integrations/regenold/scope.py::_DIMENSION_KEYWORDS, raw entries
# before the lower-case + hyphen→space normalisation.
_PRE_REFACTOR_DIMENSION = frozenset(
    s.lower().replace("-", " ") for s in (
        "transparency",
        "transparent",
        "explainability",
        "explainable",
        "interpretability",
        "data quality",
        "training data",
        "test data",
        "validation data",
        "bias",
        "fairness",
        "discrimination",
        "accuracy",
        "robustness",
        "adversarial",
        "human oversight",
        "human-in-the-loop",
        "audit trail",
    )
)

# Source: app/engines/compliance_verdict.py::_COMPLIANCE_DOMAIN_NOUNS as of
# Round 42 (the version pre-R45 deletion). The verdict predictor is being
# re-introduced in R46+ and must read its vocabulary from the canonical
# surface — pinning the historical contents here prevents regression.
_PRE_REFACTOR_VERDICT = frozenset((
    "risk-management", "risk management", "data governance", "data-governance",
    "bias-mitigation", "bias mitigation", "human oversight", "human-in-the-loop",
    "human-on-the-loop", "human review", "human review step",
    "automatic event recording", "event recording", "logging", "log retention",
    "traceability", "audit trail", "technical documentation", "robustness",
    "accuracy", "cybersecurity", "adversarial testing", "adversarial perturbations",
    "fundamental rights", "post-market monitoring", "transparency",
    "conformity assessment", "training data", "validation", "test set",
    "training, validation", "data quality", "model output", "operator override",
    "confidence indicator", "rationale", "autonomous mode", "officer dispatch",
    "interpreting outputs", "overseeing", "training, validation and test",
    "training/validation/test", "inference api", "inference endpoint",
    "signed model", "model artefacts", "tls-encrypted", "documentation",
    "operators", "deployer",
))


def test_union_covers_every_pre_refactor_term() -> None:
    """No term in any of the three sites was dropped by the refactor."""
    pre_refactor_practice = frozenset(
        kw for practice in PRACTICE_REGISTRY.values() for kw in practice.keywords
    )
    missing_dim = _PRE_REFACTOR_DIMENSION - COMPLIANCE_DOMAIN_NOUNS
    missing_verdict = _PRE_REFACTOR_VERDICT - COMPLIANCE_DOMAIN_NOUNS
    missing_practice = pre_refactor_practice - COMPLIANCE_DOMAIN_NOUNS
    assert not missing_dim, f"Lost dimension terms: {sorted(missing_dim)!r}"
    assert not missing_verdict, f"Lost verdict terms: {sorted(missing_verdict)!r}"
    assert not missing_practice, f"Lost practice terms: {sorted(missing_practice)!r}"


def test_dimension_subset_of_union() -> None:
    assert DIMENSION_KEYWORDS <= COMPLIANCE_DOMAIN_NOUNS


def test_practice_subset_of_union() -> None:
    assert PRACTICE_KEYWORDS <= COMPLIANCE_DOMAIN_NOUNS


def test_verdict_subset_of_union() -> None:
    assert frozenset(VERDICT_DOMAIN_NOUNS) <= COMPLIANCE_DOMAIN_NOUNS


def test_dimension_keywords_byte_identical_to_pre_refactor() -> None:
    """scope.py's narrower set is preserved EXACTLY (post-normalisation)."""
    assert DIMENSION_KEYWORDS == _PRE_REFACTOR_DIMENSION


def test_practice_keywords_byte_identical_to_pre_refactor() -> None:
    """Every per-Practice keyword tuple still maps into the canonical set."""
    pre = frozenset(
        kw for practice in PRACTICE_REGISTRY.values() for kw in practice.keywords
    )
    assert PRACTICE_KEYWORDS == pre


def test_verdict_domain_nouns_byte_identical_to_pre_refactor() -> None:
    """R42 verdict-predictor vocab is preserved in full (tuple form)."""
    assert frozenset(VERDICT_DOMAIN_NOUNS) == _PRE_REFACTOR_VERDICT


def test_no_empty_strings() -> None:
    assert "" not in COMPLIANCE_DOMAIN_NOUNS
    assert "" not in DIMENSION_KEYWORDS
    assert "" not in PRACTICE_KEYWORDS
    assert "" not in VERDICT_DOMAIN_NOUNS


def test_verdict_tuple_has_no_duplicates() -> None:
    """The verdict noun list iterates as a tuple; duplicates would inflate counts."""
    assert len(VERDICT_DOMAIN_NOUNS) == len(set(VERDICT_DOMAIN_NOUNS))


def test_module_level_constants_only_no_rebuild() -> None:
    """Repeated attribute access must return the SAME frozenset instance."""
    a = compliance_vocab.COMPLIANCE_DOMAIN_NOUNS
    b = compliance_vocab.COMPLIANCE_DOMAIN_NOUNS
    assert a is b
    assert compliance_vocab.DIMENSION_KEYWORDS is compliance_vocab.DIMENSION_KEYWORDS
    assert compliance_vocab.PRACTICE_KEYWORDS is compliance_vocab.PRACTICE_KEYWORDS


def test_canonical_membership_is_frozenset() -> None:
    """Hash-fast O(1) membership tests on the hot path."""
    assert isinstance(COMPLIANCE_DOMAIN_NOUNS, frozenset)
    assert isinstance(DIMENSION_KEYWORDS, frozenset)
    assert isinstance(PRACTICE_KEYWORDS, frozenset)
    assert isinstance(VERDICT_DOMAIN_NOUNS, tuple)


def test_scope_module_imports_canonical_dimension_keywords() -> None:
    """scope.py reads its narrower set from the canonical registry."""
    assert _scope_mod._DIMENSION_KEYWORDS is DIMENSION_KEYWORDS


def test_scope_anchor_vocab_unchanged_by_refactor() -> None:
    """_ANCHOR_VOCAB ordering and contents must be preserved (longest-first)."""
    vocab = _scope_mod._ANCHOR_VOCAB
    assert all(isinstance(s, str) for s in vocab)
    # Sorted DESC by length — substring-shadowing depends on this.
    lengths = [len(s) for s in vocab]
    assert lengths == sorted(lengths, reverse=True), (
        "anchor vocab must be sorted longest-first for substring shadowing"
    )
    # Every dimension keyword is reachable through the combined alternation.
    for term in DIMENSION_KEYWORDS:
        assert term in vocab, f"dimension keyword {term!r} dropped from _ANCHOR_VOCAB"
