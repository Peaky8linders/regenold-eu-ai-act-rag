"""Tests for evals/bench/metrics.py — the rubric scorers."""
from __future__ import annotations

from evals.bench import metrics


class TestArticleHeads:
    def test_article_dot_chain(self):
        assert metrics.article_head("Article 13.1.a") == "Article 13"

    def test_bare_article(self):
        assert metrics.article_head("Article 13") == "Article 13"

    def test_annex_roman(self):
        assert metrics.article_head("Annex III") == "Annex III"

    def test_annex_with_subpoint(self):
        assert metrics.article_head("Annex IV.2") == "Annex IV"

    def test_malformed_returns_none(self):
        assert metrics.article_head("not-a-ref") is None

    def test_non_string_returns_none(self):
        assert metrics.article_head(None) is None  # type: ignore[arg-type]


class TestAnswerCorrectness:
    def test_exact_match_strict(self):
        gold = "The provider must maintain technical documentation."
        pred = "The provider must maintain technical documentation."
        assert metrics.answer_correctness_strict(pred, gold) == 1.0

    def test_loose_robust_to_phrasing(self):
        gold = "Providers must keep documentation."
        pred = "The provider needs to maintain documentation."
        s = metrics.answer_correctness_loose(pred, gold)
        assert s > 0.0

    def test_empty_pred_scores_zero(self):
        assert metrics.answer_correctness_loose("", "something") == 0.0
        assert metrics.answer_correctness_strict("", "something") == 0.0


class TestConciseness:
    def test_equal_length_perfect(self):
        assert metrics.answer_conciseness("12345", "abcde") == 1.0

    def test_double_length_penalised(self):
        # 2x length → ratio 0.5 → quadratic = 0.25.
        s = metrics.answer_conciseness("a" * 200, "a" * 100)
        assert s == pytest_approx(0.25)

    def test_empty_pred_zero(self):
        assert metrics.answer_conciseness("", "anything") == 0.0


class TestReferenceCorrectness:
    def test_single_gold_hit(self):
        assert metrics.reference_correctness_loose(["Article 13"], 13) == 1.0

    def test_multi_gold_partial_recall(self):
        # Gold = [5, 10, 16], pred = [5] → recall 1/3.
        s = metrics.reference_correctness_loose(["Article 5"], [5, 10, 16])
        assert s == pytest_approx(1.0 / 3.0)

    def test_strict_over_citation_penalised(self):
        # Gold = {Article 5}, pred = {Article 5, Article 6} → P=0.5 R=1 → F1=2/3
        s = metrics.reference_correctness_strict(
            ["Article 5", "Article 6"], 5
        )
        assert s == pytest_approx(2.0 / 3.0)

    def test_empty_predictions(self):
        assert metrics.reference_correctness_loose([], 5) == 0.0
        assert metrics.reference_correctness_strict([], 5) == 0.0

    def test_reference_correctness_exact_strict(self):
        # Exact match with normalized citation forms
        assert metrics.reference_correctness_exact_strict(["Article 5(1)(a)"], ["Article 5.1.a"]) == 1.0
        assert metrics.reference_correctness_exact_strict(["Article 10"], ["Article 10"]) == 1.0
        
        # Sub-clause mismatch
        assert metrics.reference_correctness_exact_strict(["Article 5.1.h"], ["Article 5.1.a"]) == 0.0
        
        # Over-citation: pred = {Art 5.1.a, Art 6}, gold = {Art 5.1.a} -> P=0.5, R=1.0 -> F1=2/3
        s = metrics.reference_correctness_exact_strict(["Article 5.1.a", "Article 6"], ["Article 5.1.a"])
        assert s == pytest_approx(2.0 / 3.0)
        
        # Empty sets
        assert metrics.reference_correctness_exact_strict([], []) == 1.0
        assert metrics.reference_correctness_exact_strict([], ["Article 5.1.a"]) == 0.0

    def test_reference_correctness_hierarchical(self):
        # Tier 1: Exact sub-clause match -> 1.0
        assert metrics.reference_correctness_hierarchical(["Article 5.1.a"], ["Article 5(1)(a)"]) == 1.0
        
        # Tier 2: Sub-section match -> 0.7
        s_sub = metrics.reference_correctness_hierarchical(["Article 5.1.b"], ["Article 5.1.a"])
        assert s_sub == pytest_approx(0.7)
        
        s_dot = metrics.reference_correctness_hierarchical(["Article 5.1"], ["Article 5.1.a"])
        assert s_dot == pytest_approx(0.7)
        
        # Tier 3: Macro head match -> 0.4
        s_macro = metrics.reference_correctness_hierarchical(["Article 5"], ["Article 5.1.a"])
        assert s_macro == pytest_approx(0.4)
        
        s_diff_sub = metrics.reference_correctness_hierarchical(["Article 5.2"], ["Article 5.1.a"])
        assert s_diff_sub == pytest_approx(0.4)
        
        # Tier 4: Mismatch -> 0.0
        assert metrics.reference_correctness_hierarchical(["Article 6"], ["Article 5.1.a"]) == 0.0
        
        # Empty sets
        assert metrics.reference_correctness_hierarchical([], []) == 1.0
        assert metrics.reference_correctness_hierarchical([], ["Article 5.1.a"]) == 0.0


class TestRegulatoryTone:
    def test_clean_regulator_voice_scores_high(self):
        text = (
            "Providers must maintain technical documentation under "
            "Article 11 and Annex IV."
        )
        assert metrics.regulatory_tone(text) >= 0.9

    def test_ai_preamble_penalised(self):
        bad = "As an AI assistant, I think Article 11 might apply."
        good = "Article 11 applies. The provider must maintain documentation."
        assert metrics.regulatory_tone(bad) < metrics.regulatory_tone(good)

    def test_first_person_penalised(self):
        # "I think" is a 0.25 demerit; the cite anchors add 0.15. Result
        # is 1.0 - 0.25 + 0.15 = 0.90 vs the equivalent regulator-voice
        # answer which would score 1.0.
        bad = "I think the provider should consider Article 11."
        clean = "The provider must consider Article 11."
        assert metrics.regulatory_tone(bad) < metrics.regulatory_tone(clean)

    def test_regulatory_as_an_ai_system_not_penalised(self):
        # R93 — "as an AI system" is a verbatim EUR-Lex phrase (Art. 2(12),
        # Art. 25 etc.), NOT the "As an AI assistant, I ..." preamble the
        # demerit targets. It must not trip the 0.40 assistant-preamble
        # demerit (coverage200/davidath qa_100 open-source carve-out).
        text = (
            "This Regulation does not apply unless placed on the market as "
            "an AI system that falls under Article 5 or 50."
        )
        assert metrics.regulatory_tone(text) >= 0.9
        # The genuine assistant preamble still scores below it.
        preamble = "As an AI assistant, I cannot answer that."
        assert metrics.regulatory_tone(preamble) < metrics.regulatory_tone(text)


class TestAggregation:
    def test_empty_returns_empty(self):
        assert metrics.aggregate([]) == {}

    def test_basic_aggregation(self):
        rows = [
            metrics.score_row(
                pred_answer="Article 5 prohibits subliminal AI.",
                pred_refs=["Article 5"],
                gold_answer="Article 5 prohibits subliminal AI.",
                gold_articles=5,
                latency_ms=4.2,
            )
        ]
        agg = metrics.aggregate(rows)
        assert agg["n"] == 1
        assert agg["ans_correctness_loose"] == 1.0
        assert agg["ans_correctness_strict"] == 1.0
        assert agg["ref_correctness_loose"] == 1.0
        assert agg["latency_p50_ms"] == 4.2


def pytest_approx(expected, rel=1e-3):
    """Tiny pytest.approx shim so the tests don't need a pytest fixture for it."""
    import pytest as _pytest
    return _pytest.approx(expected, rel=rel)
