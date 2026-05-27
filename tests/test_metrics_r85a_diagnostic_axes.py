"""R85-A — diagnostic precision / F1 / length-ratio axes on metrics.py.

The competition rubric defines Loose=Jaccard / Strict=Recall; those
formulas are pinned. R85-A adds three diagnostic axes so analysts can
decompose the "verbose vs gold-missing" direction of the answer gap
without re-running the numbers by hand.

These tests pin:
1. Each new function's empty-input / perfect-overlap / no-overlap edges.
2. The math identity ``Jaccard <= F1 <= max(P,R)`` and the formal
   inversion ``Loose < Strict`` when |pred| > |gold| and overlap > 0.
3. The new fields land in ``RowScore.to_dict`` and the aggregate.
"""
from __future__ import annotations

from evals.bench.metrics import (
    _tokens,
    aggregate,
    answer_correctness_f1,
    answer_correctness_loose,
    answer_correctness_precision,
    answer_correctness_strict,
    pred_gold_token_ratio,
    score_row,
)


class TestPrecision:
    def test_empty_pred(self) -> None:
        assert answer_correctness_precision("", "Article 13 requires logs.") == 0.0

    def test_empty_gold(self) -> None:
        assert answer_correctness_precision("Article 13 requires logs.", "") == 0.0

    def test_both_empty(self) -> None:
        assert answer_correctness_precision("", "") == 0.0

    def test_perfect_overlap(self) -> None:
        # Identical pred and gold → every pred token is in gold → 1.0
        text = "Article 13 requires transparency for high-risk AI providers."
        assert answer_correctness_precision(text, text) == 1.0

    def test_no_overlap(self) -> None:
        # Disjoint vocabularies → 0.0 (subject to the tokenizer's filtering).
        pred = "banana mango pineapple kiwi"
        gold = "Article 99 imposes penalties on providers."
        assert answer_correctness_precision(pred, gold) == 0.0

    def test_partial_overlap_matches_formula(self) -> None:
        # Compute the precision by formula, compare to the function.
        pred = "Article 13 requires logs and transparency"
        gold = "Article 13 mandates transparency"
        pt = _tokens(pred)
        gt = _tokens(gold)
        expected = len(pt & gt) / len(pt) if pt and gt else 0.0
        assert answer_correctness_precision(pred, gold) == expected
        # Sanity: there IS overlap, so it's strictly between 0 and 1.
        assert 0.0 < expected < 1.0


class TestF1:
    def test_empty_pred(self) -> None:
        assert answer_correctness_f1("", "Article 13 requires logs.") == 0.0

    def test_empty_gold(self) -> None:
        assert answer_correctness_f1("Article 13 requires logs.", "") == 0.0

    def test_both_empty(self) -> None:
        assert answer_correctness_f1("", "") == 0.0

    def test_perfect_overlap(self) -> None:
        text = "Article 13 requires transparency for high-risk AI providers."
        assert answer_correctness_f1(text, text) == 1.0

    def test_no_overlap_disjoint(self) -> None:
        # Hand-construct a row where pred and gold share zero tokens.
        pred = "banana mango pineapple"
        gold = "Article 99 imposes penalties"
        assert answer_correctness_f1(pred, gold) == 0.0

    def test_hand_computed_f1_case_1(self) -> None:
        # pred = "transparency logs records"; gold = "transparency logs"
        # tokens(pred) ⊇ tokens(gold) (so recall = 1.0)
        # but pred has extra "records" → precision < 1.
        pred = "transparency logs records"
        gold = "transparency logs"
        pt = _tokens(pred)
        gt = _tokens(gold)
        overlap = len(pt & gt)
        p = overlap / len(pt)
        r = overlap / len(gt)
        expected = 2 * p * r / (p + r)
        assert answer_correctness_f1(pred, gold) == expected

    def test_hand_computed_f1_case_2(self) -> None:
        # The classic SQuAD-shape: partial overlap both ways.
        pred = "providers must register their high-risk AI"
        gold = "deployers must conduct fundamental rights impact assessment"
        pt = _tokens(pred)
        gt = _tokens(gold)
        overlap = len(pt & gt)
        if overlap == 0:
            assert answer_correctness_f1(pred, gold) == 0.0
        else:
            p = overlap / len(pt)
            r = overlap / len(gt)
            expected = 2 * p * r / (p + r)
            assert answer_correctness_f1(pred, gold) == expected


class TestPredGoldTokenRatio:
    def test_empty_gold(self) -> None:
        assert pred_gold_token_ratio("anything", "") == 0.0

    def test_ratio_1_when_same_tokens(self) -> None:
        # Identical text → ratio is exactly 1.0.
        text = "Article 13 requires transparency"
        assert pred_gold_token_ratio(text, text) == 1.0

    def test_ratio_2_when_pred_doubles_gold(self) -> None:
        # Build a pred whose token-set count is exactly 2× gold's.
        # gold gives 2 unique substantive tokens.
        gold = "article requires"
        # pred carries those 2 + 2 new tokens → 4 / 2 = 2.0
        pred = "article requires transparency providers"
        gt = _tokens(gold)
        pt = _tokens(pred)
        assert len(gt) == 2
        assert len(pt) == 4
        assert pred_gold_token_ratio(pred, gold) == 2.0


class TestInversionInvariant:
    """The math identities that surface the Loose-vs-Strict inversion."""

    def test_math_identities_when_overlap_positive(self) -> None:
        # Construct a verbose pred (covers all of gold + extra tokens).
        pred = (
            "the the the the the the the cat sat on the mat "
            "with extra prose providers must keep records "
            "and document the system thoroughly today"
        )
        gold = "cat sat on the mat"

        loose = answer_correctness_loose(pred, gold)
        strict = answer_correctness_strict(pred, gold)
        precision = answer_correctness_precision(pred, gold)
        f1 = answer_correctness_f1(pred, gold)

        # Pred contains every gold substantive token → recall (strict) = 1.0.
        assert strict == 1.0
        # Pred has many extra non-gold tokens → precision < 1.
        assert 0.0 < precision < 1.0
        # Math identity: Jaccard <= F1 always.
        assert loose <= f1 + 1e-9
        # Math identity: F1 lives between min(P,R) and max(P,R).
        assert min(precision, strict) - 1e-9 <= f1 <= max(precision, strict) + 1e-9

    def test_loose_strictly_less_than_strict_when_pred_longer(self) -> None:
        """The whole reason R85-A exists: pin the Jaccard inversion.

        When pred is much longer than gold AND contains all gold
        substantive tokens, Strict (recall) hits 1.0 but Loose
        (Jaccard) collapses below 1.0 because the union balloons.
        """
        pred = (
            "Article 13 requires transparency for high-risk AI providers "
            "including documentation logs records technical assessments "
            "and many more obligations along the value chain processes."
        )
        gold = "Article 13 transparency"

        loose = answer_correctness_loose(pred, gold)
        strict = answer_correctness_strict(pred, gold)
        # Pred has every gold token AND many extras → recall = 1.0.
        assert strict == 1.0
        # Jaccard < 1.0 because of all the extra pred tokens.
        assert loose < strict


class TestScoreRowFields:
    def test_to_dict_carries_new_keys(self) -> None:
        row = score_row(
            pred_answer="Article 13 requires transparency for high-risk providers.",
            pred_refs=["Article 13"],
            gold_answer="Article 13 mandates transparency.",
            gold_articles=13,
            latency_ms=12.34,
        )
        d = row.to_dict()
        assert "ans_correctness_precision" in d
        assert "ans_correctness_f1" in d
        assert "pred_gold_token_ratio" in d
        # Types: round() in to_dict returns float for the first two
        # (already-bounded) and float for the ratio.
        assert isinstance(d["ans_correctness_precision"], float)
        assert isinstance(d["ans_correctness_f1"], float)
        assert isinstance(d["pred_gold_token_ratio"], float)
        # Sanity: precision is in [0, 1].
        assert 0.0 <= d["ans_correctness_precision"] <= 1.0
        # Sanity: F1 is in [0, 1].
        assert 0.0 <= d["ans_correctness_f1"] <= 1.0
        # Sanity: ratio is >= 0.
        assert d["pred_gold_token_ratio"] >= 0.0

    def test_legacy_fields_still_present(self) -> None:
        """R85-A is purely additive — the legacy keys must still ship."""
        row = score_row(
            pred_answer="Article 13 requires transparency.",
            pred_refs=["Article 13"],
            gold_answer="Article 13 mandates transparency.",
            gold_articles=13,
            latency_ms=12.34,
        )
        d = row.to_dict()
        for key in (
            "ans_correctness_loose",
            "ans_correctness_strict",
            "ans_conciseness",
            "ref_correctness_loose",
            "ref_correctness_strict",
            "ref_conciseness",
            "latency_ms",
            "regulatory_tone",
            "ans_correctness_loose_legacy",
            "ans_correctness_strict_legacy",
        ):
            assert key in d, f"R85-A regressed legacy field {key!r}"


class TestAggregateSummary:
    def test_aggregate_carries_new_keys(self) -> None:
        rows = [
            score_row(
                pred_answer="Article 13 requires transparency for high-risk providers.",
                pred_refs=["Article 13"],
                gold_answer="Article 13 mandates transparency.",
                gold_articles=13,
                latency_ms=10.0,
            ),
            score_row(
                pred_answer="Article 99 sets out penalties for providers.",
                pred_refs=["Article 99"],
                gold_answer="Article 99 imposes penalties on providers.",
                gold_articles=99,
                latency_ms=20.0,
            ),
        ]
        agg = aggregate(rows)
        assert "ans_correctness_precision" in agg
        assert "ans_correctness_f1" in agg
        assert "pred_gold_token_ratio" in agg
        # All three are floats (mean values rounded to 4dp).
        assert isinstance(agg["ans_correctness_precision"], float)
        assert isinstance(agg["ans_correctness_f1"], float)
        assert isinstance(agg["pred_gold_token_ratio"], float)
        # Sanity bounds.
        assert 0.0 <= agg["ans_correctness_precision"] <= 1.0
        assert 0.0 <= agg["ans_correctness_f1"] <= 1.0
        assert agg["pred_gold_token_ratio"] >= 0.0
