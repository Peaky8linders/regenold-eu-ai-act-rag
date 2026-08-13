"""Unit tests for app/engines/query_complexity_router.py."""
from __future__ import annotations

from app.engines.query_complexity_router import (
    CLASS_0_PARAMS,
    CLASS_1_PARAMS,
    CLASS_2_PARAMS,
    classify_query_complexity,
    is_adaptive_router_enabled,
)


def test_is_adaptive_router_enabled_default(monkeypatch):
    """R329 — the HyPA adaptive router ships OPT-IN (default OFF).

    This assertion was inverted (default ON) when the router landed. The
    default was flipped after an in-place davidath 476 A/B
    (``r329-armA-hypaoff`` vs ``r329-armB-hypa``, identical dataset
    fingerprint) measured QA **Ref Conciseness -0.2094** and **Ref Strict
    -0.1137** with the router on, plus one dropped gold reference. The test
    is updated rather than removed so the opt-in contract stays pinned in
    both directions.
    """
    monkeypatch.delenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", raising=False)
    assert is_adaptive_router_enabled() is False


def test_is_adaptive_router_enabled_off(monkeypatch):
    monkeypatch.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "0")
    assert is_adaptive_router_enabled() is False


def test_is_adaptive_router_enabled_opt_in(monkeypatch):
    """The lever must still be reachable for the A/B it has not yet passed."""
    monkeypatch.setenv("REGENOLD_HYPA_ADAPTIVE_ROUTER", "1")
    assert is_adaptive_router_enabled() is True


def test_classify_simple_definition():
    params = classify_query_complexity("What is a provider?")
    assert params.complexity_class == 0
    assert params.class_label == "simple"
    assert params.top_k_dense == 3
    assert params.kg_depth == 1


def test_classify_substantive_what_is_query_not_simple():
    # Questions asking about obligations/requirements starting with "What is" must NOT be Class 0
    params = classify_query_complexity("What is required for high-risk AI systems?")
    assert params.complexity_class != 0


def test_classify_direct_article_with_subpoints_and_punctuation():
    params = classify_query_complexity("Article 13.1.")
    assert params.complexity_class == 0
    assert params.top_k_dense == 3


def test_classify_article_5_not_simple():
    # Article 5 is prohibited practices and must NOT be Class 0
    params = classify_query_complexity("Article 5")
    assert params.complexity_class != 0


def test_classify_standard_question():
    params = classify_query_complexity("What risk management system is required for high-risk AI?")
    assert params.complexity_class == 1
    assert params.class_label == "standard"
    assert params.top_k_dense == 5
    assert params.kg_depth == 2


def test_classify_complex_question():
    params = classify_query_complexity(
        "Are we a provider or deployer if we significantly configure a third party medical model under Article 25?"
    )
    assert params.complexity_class == 2
    assert params.class_label == "complex"
    # R329 — was 10, which is the paper's **2-class** value (Table 5, label 1).
    # The 3-class mapping this router implements specifies 7.
    assert params.top_k_dense == 7
    assert params.kg_depth == 3
    # R329 — these four now have real consumers; pin them so a future edit that
    # re-orphans them fails loudly rather than silently going decorative again.
    assert params.query_rewrites == 5
    assert params.kg_max_keywords == 5
    assert params.kg_max_units == 24
