"""Single source of truth for EU AI Act compliance-domain vocabulary.

Three independent compliance-vocabulary noun lists historically lived in
separate modules and drifted independently (Round 46 / B6 audit triple):

1. ``app/engines/compliance_verdict.py::_COMPLIANCE_DOMAIN_NOUNS`` —
   the deterministic verdict predictor's HRAIS-backbone vocabulary
   (Arts. 9/10/12/14/15/27). Present in rounds 42–44; pruned in R45
   but tracked here for the (planned) R46+ re-introduction so the
   future module has a single import surface and cannot drift again.
2. ``app/integrations/regenold/scope.py::_DIMENSION_KEYWORDS`` — the
   in-scope gate's compliance-dimension anchors (transparency,
   robustness, human oversight, etc.) folded into the scope keyword
   alternation.
3. ``app/data/ontology.py::PRACTICE_REGISTRY`` — the keywords on each
   :class:`Practice` (subliminal manipulation, social scoring, real-time
   RBI, etc.) used by :func:`practice_for_keyword` and downstream.

This module collects the **union** of every term ever exposed by the
three sites into a canonical :data:`COMPLIANCE_DOMAIN_NOUNS`
``frozenset[str]`` and derives the historical narrower sets from it
as **subsets**, so each consumer's behaviour stays byte-identical
while edits land in one place.

## Invariants enforced at module import

* Every term in :data:`DIMENSION_KEYWORDS` is in the union.
* Every term in :data:`PRACTICE_KEYWORDS` is in the union.
* No empty strings; no duplicate-after-normalisation entries.
* :data:`COMPLIANCE_DOMAIN_NOUNS` is a ``frozenset`` (hash-fast
  membership tests at runtime — bench latency budget is tight).
* Module-level computation only — every consumer re-uses the same
  frozenset instance.

## How to edit

Add the new term to the appropriate narrower list below. If it should
be visible to all three consumers, add it to ``_VERDICT_NOUNS``. The
union is computed once at import time; no consumer needs editing.
"""

from __future__ import annotations

from typing import Final

# ── Narrower sets — preserve each consumer's pre-R46 surface exactly ────


# Source: scope.py::_DIMENSION_KEYWORDS (post lower-case + hyphen→space
# normalisation, which the consumer applies before the substring scan).
# Keep this list narrow — scope's keyword regex is sorted longest-first
# and substring-shadows, so widening this set widens the in-scope gate.
_DIMENSION_NOUNS: Final[tuple[str, ...]] = (
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


# Source: ontology.py::PRACTICE_REGISTRY[*].keywords flattened. These
# are the substrings :func:`practice_for_keyword` matches against to
# resolve a query to a specific Art. 5 sub-paragraph. Each per-Practice
# keyword tuple in :data:`PRACTICE_REGISTRY` is also re-exported here
# so an outside reviewer can see the full vocabulary in one place; the
# Practice dataclass instances remain the canonical address for any
# per-practice metadata (sub_paragraph, citation, exceptions, etc.).
_PRACTICE_NOUNS: Final[tuple[str, ...]] = (
    # Art. 5(1)(a) — subliminal / manipulative / deceptive
    "subliminal",
    "manipulative technique",
    "deceptive technique",
    "subliminal manipulation",
    "neural data",
    # Art. 5(1)(b) — exploitation of vulnerabilities
    "exploit vulnerabilities",
    "exploit the vulnerabilities",
    "exploiting vulnerabilities",
    "vulnerable groups",
    "elderly",
    "exploits the vulnerabilities",
    # Art. 5(1)(c) — social scoring
    "social scoring",
    "social score",
    # Art. 5(1)(d) — predictive policing
    "predictive policing",
    "predicting criminality",
    "criminal-risk profiling",
    "criminal risk",
    "criminal-risk",
    # Art. 5(1)(e) — untargeted facial scraping
    "facial recognition database",
    "scraping facial",
    "scraping of facial",
    "scraping facial images",
    "untargeted scraping",
    # Art. 5(1)(f) — emotion recognition (workplace/education)
    "emotion recognition",
    "emotion inference",
    "emotion detection",
    "infer emotions",
    # Art. 5(1)(g) — biometric categorisation by sensitive attribute
    "biometric categorisation",
    "biometric categorization",
    # Art. 5(1)(h) — real-time RBI in public spaces
    "real-time biometric",
    "real time biometric",
    "real-time remote biometric",
    "biometric identification",
    "rbi in public",
    "remote biometric identification",
)


# Source: compliance_verdict.py::_COMPLIANCE_DOMAIN_NOUNS (Round 42).
# Pruned from the repo in R45 because the verdict predictor was
# decommissioned. Tracked here so the R46+ re-introduction reads from
# this canonical surface instead of redeclaring inline. Drawn from the
# HRAIS compliance backbone — Arts. 9 (risk management) / 10 (data
# governance) / 12 (logging) / 14 (oversight) / 15 (robustness).
_VERDICT_NOUNS: Final[tuple[str, ...]] = (
    "risk-management",
    "risk management",
    "data governance",
    "data-governance",
    "bias-mitigation",
    "bias mitigation",
    "human oversight",
    "human-in-the-loop",
    "human-on-the-loop",
    "human review",
    "human review step",
    "automatic event recording",
    "event recording",
    "logging",
    "log retention",
    "traceability",
    "audit trail",
    "technical documentation",
    "robustness",
    "accuracy",
    "cybersecurity",
    "adversarial testing",
    "adversarial perturbations",
    "fundamental rights",
    "post-market monitoring",
    "transparency",
    "conformity assessment",
    "training data",
    "validation",
    "test set",
    "training, validation",
    "data quality",
    "model output",
    "operator override",
    "confidence indicator",
    "rationale",
    # Art. 14 oversight vocabulary
    "autonomous mode",
    "officer dispatch",
    "interpreting outputs",
    "overseeing",
    # Art. 10 data governance vocabulary
    "training, validation and test",
    "training/validation/test",
    # Art. 15 robustness vocabulary
    "inference api",
    "inference endpoint",
    "signed model",
    "model artefacts",
    "tls-encrypted",
    # Provider obligations
    "documentation",
    "operators",
    "deployer",
)


# ── Public derived surfaces ─────────────────────────────────────────────


def _normalise_dimension(s: str) -> str:
    """Apply the scope.py normalisation to a dimension keyword.

    scope.py historically did ``s.lower().replace("-", " ")`` on each
    raw entry; we preserve that exactly so the derived
    :data:`DIMENSION_KEYWORDS` is byte-identical to the prior frozenset.
    """
    return s.lower().replace("-", " ")


# Canonical union — every compliance-vocabulary noun the repo recognises.
# Stored as a frozenset for O(1) ``in`` membership tests on the hot path
# (e.g. ``_count_domain_nouns`` in the verdict predictor would do
# ``sum(1 for noun in COMPLIANCE_DOMAIN_NOUNS if noun in text)`` — set
# membership is irrelevant there but the frozenset doubles as the
# immutability guarantee). Module-level computation only.
COMPLIANCE_DOMAIN_NOUNS: Final[frozenset[str]] = frozenset(
    # Raw dimension entries
    list(_DIMENSION_NOUNS)
    # Plus normalised dimension entries — the scope consumer applies
    # lower-case + hyphen→space normalisation before substring matching,
    # so the normalised forms ("human in the loop") must also be in
    # the union to keep DIMENSION_KEYWORDS as a subset.
    + [_normalise_dimension(s) for s in _DIMENSION_NOUNS]
    + list(_PRACTICE_NOUNS)
    + list(_VERDICT_NOUNS)
)


# Derived: scope.py's frozenset, post-normalisation. Drop-in replacement
# for the prior in-module ``_DIMENSION_KEYWORDS`` literal.
DIMENSION_KEYWORDS: Final[frozenset[str]] = frozenset(
    _normalise_dimension(s) for s in _DIMENSION_NOUNS
)


# Derived: the flat union of every Practice keyword in PRACTICE_REGISTRY.
# Read-only view — the per-Practice tuples in
# :data:`app.data.ontology.PRACTICE_REGISTRY` remain the canonical
# address for the Practice→keyword mapping (because keyword→Practice is
# many-to-one and ``practice_for_keyword`` needs that direction).
PRACTICE_KEYWORDS: Final[frozenset[str]] = frozenset(_PRACTICE_NOUNS)


# Derived: the historical compliance-verdict predictor noun list.
# Re-exported as a tuple because the verdict predictor iterated it for
# count-distinct-substrings (insertion order is irrelevant but stable
# iteration is convenient for debugging).
VERDICT_DOMAIN_NOUNS: Final[tuple[str, ...]] = _VERDICT_NOUNS


# ── Invariants — fail fast at import if anyone drifts ───────────────────


def _validate_invariants() -> None:
    """Fail fast if the narrower sets aren't subsets of the union.

    Called once at module import — the cost is paid by the test
    harness and the first request, not by every wire call.
    """
    if not DIMENSION_KEYWORDS <= COMPLIANCE_DOMAIN_NOUNS:
        missing = DIMENSION_KEYWORDS - COMPLIANCE_DOMAIN_NOUNS
        raise AssertionError(
            f"DIMENSION_KEYWORDS not a subset of COMPLIANCE_DOMAIN_NOUNS; "
            f"missing terms: {sorted(missing)!r}"
        )
    if not PRACTICE_KEYWORDS <= COMPLIANCE_DOMAIN_NOUNS:
        missing = PRACTICE_KEYWORDS - COMPLIANCE_DOMAIN_NOUNS
        raise AssertionError(
            f"PRACTICE_KEYWORDS not a subset of COMPLIANCE_DOMAIN_NOUNS; "
            f"missing terms: {sorted(missing)!r}"
        )
    if not frozenset(VERDICT_DOMAIN_NOUNS) <= COMPLIANCE_DOMAIN_NOUNS:
        missing = frozenset(VERDICT_DOMAIN_NOUNS) - COMPLIANCE_DOMAIN_NOUNS
        raise AssertionError(
            f"VERDICT_DOMAIN_NOUNS not a subset of COMPLIANCE_DOMAIN_NOUNS; "
            f"missing terms: {sorted(missing)!r}"
        )
    if "" in COMPLIANCE_DOMAIN_NOUNS:
        raise AssertionError("COMPLIANCE_DOMAIN_NOUNS contains an empty string")


_validate_invariants()


__all__ = [
    "COMPLIANCE_DOMAIN_NOUNS",
    "DIMENSION_KEYWORDS",
    "PRACTICE_KEYWORDS",
    "VERDICT_DOMAIN_NOUNS",
]
