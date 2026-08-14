"""Adversarial stress-test suite for evals/bench/metrics.py and evals/harness/easyhard_ab.py.

Tests cover:
1. `gold_dropped_head` and surrounding reference functions under edge-case inputs:
   - None, empty string, malformed strings, integer 0, negative ints, floats, booleans.
   - Heterogeneous/mixed-type gold reference containers.
   - Duplicates, casing variations, non-standard citations.
2. `easyhard_ab.py` harness functions (_score_row, _aggregate, _paired, _report, _report_paired):
   - All rows erroring out (100% error rate).
   - One arm with 0 rows or 100% errors.
   - Division by zero safety for pred_gold_ratio.
   - Strict typing (int vs float) and JSON serialization.
   - Missing keys / backward compatibility.
3. Answer correctness, conciseness, tone, latency percentile, and refusal metrics.
"""
from __future__ import annotations

import io
import json
import math
import sys
from typing import Any
import pytest

from evals.bench import metrics
from evals.harness import easyhard_ab
from evals.harness.probe_set import ProbeRow


# ════════════════════════════════════════════════════════════════════════════
# 1. Gold Dropped Head & Reference Scorer Adversarial Tests
# ════════════════════════════════════════════════════════════════════════════


class TestGoldDroppedHeadAdversarial:
    """Stress tests for `gold_dropped_head` and `_gold_ref_set`."""

    def test_gold_dropped_head_standard_hit(self):
        res = metrics.gold_dropped_head(["Article 5"], ["Article 5"])
        assert res == {
            "gold_count": 1,
            "dropped_count": 0,
            "dropped_refs": [],
        }
        assert isinstance(res["gold_count"], int)
        assert isinstance(res["dropped_count"], int)
        assert isinstance(res["dropped_refs"], list)

    def test_gold_dropped_head_empty_and_none_inputs(self):
        # Empty prediction, empty gold
        assert metrics.gold_dropped_head([], []) == {
            "gold_count": 0,
            "dropped_count": 0,
            "dropped_refs": [],
        }
        # None prediction, None gold
        assert metrics.gold_dropped_head(None, None) == {  # type: ignore[arg-type]
            "gold_count": 0,
            "dropped_count": 0,
            "dropped_refs": [],
        }
        # None pred, non-empty gold
        assert metrics.gold_dropped_head(None, ["Article 5"]) == {  # type: ignore[arg-type]
            "gold_count": 1,
            "dropped_count": 1,
            "dropped_refs": ["Article 5"],
        }
        # Non-empty pred, None gold
        assert metrics.gold_dropped_head(["Article 5"], None) == {
            "gold_count": 0,
            "dropped_count": 0,
            "dropped_refs": [],
        }

    def test_gold_dropped_head_single_string_gold_behavior(self):
        """Audits behavior when gold_articles is passed as a bare string."""
        res = metrics.gold_dropped_head(["Article 5"], "Article 5")  # type: ignore[arg-type]
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

        res_bare_num = metrics.gold_dropped_head(["Article 5"], "5")  # type: ignore[arg-type]
        assert res_bare_num["gold_count"] == 1
        assert res_bare_num["dropped_count"] == 0

    def test_gold_dropped_head_int_and_list_int_gold(self):
        # Single int
        res = metrics.gold_dropped_head(["Article 5"], 5)
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0

        # List of ints
        res = metrics.gold_dropped_head(["Article 5"], [5, 6])
        assert res["gold_count"] == 2
        assert res["dropped_count"] == 1
        assert res["dropped_refs"] == ["Article 6"]

    def test_gold_dropped_head_zero_and_negative_gold(self):
        # Integer 0
        res = metrics.gold_dropped_head(["Article 0"], 0)
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0

        # List with 0
        res_list0 = metrics.gold_dropped_head([], [0])
        assert res_list0["gold_count"] == 1
        assert res_list0["dropped_count"] == 1
        assert res_list0["dropped_refs"] == ["Article 0"]

        # Negative integer - article_head does not match negative numbers
        res_neg = metrics.gold_dropped_head(["Article -5"], -5)
        assert res_neg["gold_count"] == 1
        # pred_heads is empty because "Article -5" regex fails
        assert res_neg["dropped_count"] == 1
        assert res_neg["dropped_refs"] == ["Article -5"]

    def test_gold_dropped_head_float_and_bool_inputs(self):
        # Float is neither int nor list -> returns empty set
        res_float = metrics.gold_dropped_head(["Article 5"], 5.0)  # type: ignore[arg-type]
        assert res_float["gold_count"] == 0

        # In Python bool is a subclass of int: isinstance(True, int) is True
        res_bool = metrics.gold_dropped_head(["Article 1"], True)  # type: ignore[arg-type]
        assert res_bool["gold_count"] == 1
        assert res_bool["dropped_refs"] == ["Article True"]

    def test_gold_dropped_head_mixed_list_vulnerabilities(self):
        """Heterogeneous list edge cases in _gold_ref_set."""
        # [None]
        res = metrics.gold_dropped_head(["Article 5"], [None])  # type: ignore[list-item]
        assert res["gold_count"] == 0

        # ["", "Article 5"] (starts with string "")
        res_empty_lead = metrics.gold_dropped_head(["Article 5"], ["", "Article 5"])
        assert res_empty_lead["gold_count"] == 1
        assert res_empty_lead["dropped_count"] == 0

        # [None, "Article 5"] (mixed None and string handled safely)
        res_none_lead = metrics.gold_dropped_head(["Article 5"], [None, "Article 5"])  # type: ignore[list-item]
        assert res_none_lead["gold_count"] == 1
        assert res_none_lead["dropped_count"] == 0

        # [5, "Article 6"] (mixed int and string handled safely)
        res_mixed = metrics.gold_dropped_head(["Article 5", "Article 6"], [5, "Article 6"])  # type: ignore[list-item]
        assert res_mixed["gold_count"] == 2
        assert res_mixed["dropped_count"] == 0

    def test_gold_dropped_head_malformed_and_non_article_pred_refs(self):
        malformed_preds = [
            "",
            "   ",
            "not-a-citation",
            "Article",
            "Annex",
            "Article ABC",
            "Annex 3",  # Arabic instead of Roman
            "Art. 13",  # Abbreviated
            None,
            123,
            45.67,
        ]
        res = metrics.gold_dropped_head(malformed_preds, ["Article 5", "Annex III"])  # type: ignore[arg-type]
        assert res["gold_count"] == 2
        assert res["dropped_count"] == 2
        assert res["dropped_refs"] == ["Annex III", "Article 5"]

    def test_gold_dropped_head_bare_string_pred_refs(self):
        """Passing pred_refs as a string instead of a list iterates characters."""
        res = metrics.gold_dropped_head("Article 5", ["Article 5"])  # type: ignore[arg-type]
        # Characters 'A', 'r', 't'... return None in article_head
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 1
        assert res["dropped_refs"] == ["Article 5"]

    def test_gold_dropped_head_duplicates_and_casing(self):
        preds = [
            "article 5",
            "ARTICLE 5.1.a",
            "Article 5",
            "annex iii",
            "Annex III.2",
        ]
        golds = ["Article 5", "Annex III"]
        res = metrics.gold_dropped_head(preds, golds)
        assert res["gold_count"] == 2
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

    def test_gold_dropped_head_json_serializable(self):
        res = metrics.gold_dropped_head(["Article 5"], ["Article 5", "Article 6"])
        dumped = json.dumps(res)
        loaded = json.loads(dumped)
        assert loaded == {
            "gold_count": 2,
            "dropped_count": 1,
            "dropped_refs": ["Article 6"],
        }
        assert isinstance(loaded["gold_count"], int)
        assert isinstance(loaded["dropped_count"], int)


# ════════════════════════════════════════════════════════════════════════════
# 2. Reference Scorer Family Adversarial Tests
# ════════════════════════════════════════════════════════════════════════════


class TestReferenceMetricsAdversarial:
    def test_reference_correctness_loose_adversarial(self):
        # Both empty -> 1.0
        assert metrics.reference_correctness_loose([], []) == 1.0
        assert metrics.reference_correctness_loose(None, None) == 1.0  # type: ignore[arg-type]

        # Gold empty, pred non-empty -> 0.0
        assert metrics.reference_correctness_loose(["Article 5"], []) == 0.0

        # Pred empty, gold non-empty -> 0.0
        assert metrics.reference_correctness_loose([], ["Article 5"]) == 0.0

        # Full recall with distractor
        s = metrics.reference_correctness_loose(
            ["Article 5", "Article 99"], ["Article 5"]
        )
        assert s == 1.0

    def test_reference_correctness_strict_adversarial(self):
        # Both empty -> 1.0
        assert metrics.reference_correctness_strict([], []) == 1.0
        assert metrics.reference_correctness_strict(None, None) == 1.0  # type: ignore[arg-type]

        # One empty -> 0.0
        assert metrics.reference_correctness_strict(["Article 5"], []) == 0.0
        assert metrics.reference_correctness_strict([], ["Article 5"]) == 0.0

        # Precision penalty for extra refs
        # Pred: {Art 5, Art 6}, Gold: {Art 5} -> TP=1, P=0.5, R=1.0 -> F1 = 2/3
        s = metrics.reference_correctness_strict(["Article 5", "Article 6"], 5)
        assert abs(s - 2.0 / 3.0) < 1e-6

        # Zero TP -> 0.0 (division by zero prevented)
        assert metrics.reference_correctness_strict(["Article 6"], 5) == 0.0

    def test_reference_conciseness_adversarial(self):
        # Both empty -> 1.0
        assert metrics.reference_conciseness([], []) == 1.0
        assert metrics.reference_conciseness(None, None) == 1.0  # type: ignore[arg-type]

        # One empty -> 0.0
        assert metrics.reference_conciseness(["Article 5"], []) == 0.0
        assert metrics.reference_conciseness([], ["Article 5"]) == 0.0

        # Exact count -> 1.0
        assert metrics.reference_conciseness(["Article 5"], ["Article 6"]) == 1.0

        # 2x too many citations -> ratio 0.5 -> squared = 0.25
        assert abs(metrics.reference_conciseness(["Article 5", "Article 6"], ["Article 5"]) - 0.25) < 1e-6

    def test_reference_exact_strict_and_hierarchical_adversarial(self):
        # Exact strict with empty sets
        assert metrics.reference_correctness_exact_strict([], []) == 1.0
        assert metrics.reference_correctness_exact_strict([], ["Article 5"]) == 0.0
        assert metrics.reference_correctness_exact_strict(["Article 5"], []) == 0.0

        # Hierarchical with empty sets
        assert metrics.reference_correctness_hierarchical([], []) == 1.0
        assert metrics.reference_correctness_hierarchical([], ["Article 5"]) == 0.0
        assert metrics.reference_correctness_hierarchical(["Article 5"], []) == 0.0

        # Hierarchical with duplicates in pred
        # Pred: ["Article 5.1.a", "Article 5.1.a"], Gold: ["Article 5.1.a"]
        # Max score for each pred is 1.0 -> precision = 2.0 / 2 = 1.0
        # Max score for gold is 1.0 -> recall = 1.0 / 1 = 1.0 -> F1 = 1.0
        score_dup = metrics.reference_correctness_hierarchical(
            ["Article 5.1.a", "Article 5.1.a"], ["Article 5.1.a"]
        )
        assert score_dup == 1.0


# ════════════════════════════════════════════════════════════════════════════
# 3. EasyHard A/B Harness Adversarial Tests
# ════════════════════════════════════════════════════════════════════════════


class TestEasyHardHarnessAdversarial:
    """Stress testing _score_row, _aggregate, _paired, _report, _report_paired."""

    def _sample_probe_row(self, **kwargs) -> ProbeRow:
        defaults = {
            "id": "row_001",
            "source": "test_src",
            "category": "test_cat",
            "is_multiturn": False,
            "messages": ({"role": "user", "content": "Explain Article 5"},),
            "expected_refs": ("Article 5",),
            "expected_keywords": ("prohibited", "subliminal"),
            "gold_answer": "Article 5 prohibits subliminal AI.",
        }
        defaults.update(kwargs)
        return ProbeRow(**defaults)

    def test_score_row_edge_cases(self):
        row = self._sample_probe_row()

        # Empty answer
        scores_empty_ans = easyhard_ab._score_row(row, "", ["Article 5"])
        assert scores_empty_ans["ref_loose"] == 1.0
        assert scores_empty_ans["tone"] == 0.0
        assert scores_empty_ans["kw_recall"] == 0.0
        assert scores_empty_ans["gold_dropped_head"] == 0.0
        assert scores_empty_ans["gold_dropped_head_gold_count"] == 1.0

        # None answer
        scores_none_ans = easyhard_ab._score_row(row, None, ["Article 5"])  # type: ignore[arg-type]
        assert scores_none_ans["tone"] == 0.0
        assert scores_none_ans["kw_recall"] == 0.0

        # None refs
        scores_none_refs = easyhard_ab._score_row(row, "Prohibited subliminal practices.", None)  # type: ignore[arg-type]
        assert scores_none_refs["ref_loose"] == 0.0
        assert scores_none_refs["gold_dropped_head"] == 1.0
        assert scores_none_refs["gold_dropped_head_refs"] == ["Article 5"]

        # None expected keywords
        row_no_kw = self._sample_probe_row(expected_keywords=None)  # type: ignore[arg-type]
        scores_no_kw = easyhard_ab._score_row(row_no_kw, "Some answer", ["Article 5"])
        assert scores_no_kw["kw_recall"] == 1.0

        # None expected refs
        row_no_refs = self._sample_probe_row(expected_refs=None)  # type: ignore[arg-type]
        scores_no_refs = easyhard_ab._score_row(row_no_refs, "Some answer", ["Article 5"])
        assert scores_no_refs["ref_loose"] == 0.0
        assert scores_no_refs["gold_dropped_head"] == 0.0
        assert scores_no_refs["gold_dropped_head_gold_count"] == 0.0

    def test_score_row_types_and_serialization(self):
        row = self._sample_probe_row()
        scores = easyhard_ab._score_row(row, "Article 5 prohibits subliminal manipulation.", ["Article 5"])
        
        # Verify types: float for counts in _score_row
        assert isinstance(scores["gold_dropped_head"], float)
        assert isinstance(scores["gold_dropped_head_gold_count"], float)
        assert isinstance(scores["gold_dropped_head_refs"], list)

        # Serialization to JSON
        dumped = json.dumps(scores)
        loaded = json.loads(dumped)
        assert loaded["gold_dropped_head"] == 0.0
        assert loaded["gold_dropped_head_gold_count"] == 1.0
        assert loaded["gold_dropped_head_refs"] == []

    def test_aggregate_empty_and_all_errors(self):
        # Empty rows list
        assert easyhard_ab._aggregate([]) == {"n": 0, "errors": 0}

        # 100% error rate
        err_rows = [
            {"id": "r1", "error": "timeout"},
            {"id": "r2", "error": "http_500"},
            {"id": "r3", "error": "empty_answer"},
        ]
        agg_err = easyhard_ab._aggregate(err_rows)
        assert agg_err == {"n": 0, "errors": 3}

    def test_aggregate_pred_gold_ratio_zero_division_safety(self):
        # Case 1: Gold refs empty across all rows
        rows_no_gold = [
            {
                "id": "r1",
                "scores": {
                    "ref_loose": 1.0, "ref_strict": 1.0, "ref_conc": 1.0,
                    "tone": 1.0, "kw_recall": 1.0,
                    "gold_dropped_head": 0.0, "gold_dropped_head_gold_count": 0.0,
                },
                "pred_refs": ["Article 5"],
                "gold_refs": [],
                "latency_ms": 50,
            }
        ]
        agg = easyhard_ab._aggregate(rows_no_gold)
        assert agg["pred_gold_ratio"] == 0.0

        # Case 2: Integer gold_refs vs string gold_refs in _aggregate
        # _aggregate uses _gold_ref_set, so integer gold_refs correctly counts n_gold=1
        rows_int_gold = [
            {
                "id": "r1",
                "scores": {
                    "ref_loose": 1.0, "ref_strict": 1.0, "ref_conc": 1.0,
                    "tone": 1.0, "kw_recall": 1.0,
                    "gold_dropped_head": 0.0, "gold_dropped_head_gold_count": 1.0,
                },
                "pred_refs": ["Article 5"],
                "gold_refs": [5],
                "latency_ms": 50,
            }
        ]
        agg_int = easyhard_ab._aggregate(rows_int_gold)
        assert agg_int["pred_gold_ratio"] == 1.0

    def test_aggregate_latencies_and_percentiles(self):
        # Single row
        r1 = {
            "id": "r1",
            "scores": {a: 1.0 for a in easyhard_ab._AXES},
            "pred_refs": ["Article 5"],
            "gold_refs": ["Article 5"],
            "latency_ms": 150.0,
        }
        agg1 = easyhard_ab._aggregate([r1])
        assert agg1["latency_p50_ms"] == 150.0
        assert agg1["latency_p90_ms"] == 150.0
        assert agg1["gold_dropped_head"] == 0
        assert isinstance(agg1["gold_dropped_head"], int)

        # Multiple rows
        r2 = dict(r1, id="r2", latency_ms=250.0)
        agg2 = easyhard_ab._aggregate([r1, r2])
        assert agg2["latency_p50_ms"] == 250.0  # index len // 2 = 1

    def test_paired_with_asymmetric_and_all_error_arms(self):
        a_rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {a: 1.0 for a in easyhard_ab._AXES} | {"gold_dropped_head": 0.0},
                "pred_refs": ["Article 5"],
                "gold_refs": ["Article 5"],
            },
            {
                "id": "h1",
                "is_multiturn": True,
                "scores": {a: 0.8 for a in easyhard_ab._AXES} | {"gold_dropped_head": 0.0},
                "pred_refs": ["Article 6"],
                "gold_refs": ["Article 6"],
            },
        ]

        # Arm B has 100% errors
        b_all_errors = [
            {"id": "e1", "is_multiturn": False, "error": "http_429"},
            {"id": "h1", "is_multiturn": True, "error": "timeout"},
        ]
        p_err = easyhard_ab._paired(a_rows, b_all_errors)
        assert p_err["easy"] == {"n": 0}
        assert p_err["hard"] == {"n": 0}

        # Arm B is empty
        p_empty = easyhard_ab._paired(a_rows, [])
        assert p_empty["easy"] == {"n": 0}
        assert p_empty["hard"] == {"n": 0}

        # Arm B has disjoint IDs
        b_disjoint = [
            {
                "id": "other_id",
                "is_multiturn": False,
                "scores": {a: 1.0 for a in easyhard_ab._AXES} | {"gold_dropped_head": 0.0},
                "pred_refs": ["Article 5"],
                "gold_refs": ["Article 5"],
            }
        ]
        p_disjoint = easyhard_ab._paired(a_rows, b_disjoint)
        assert p_disjoint["easy"] == {"n": 0}
        assert p_disjoint["hard"] == {"n": 0}

    def test_paired_gold_dropped_head_gold_count_asymmetry(self):
        """Audits whether gold_dropped_head_gold_count is present in _paired.

        _aggregate sets both 'gold_dropped_head' and 'gold_dropped_head_gold_count'.
        _paired sets 'gold_dropped_head' but currently omits 'gold_dropped_head_gold_count'.
        """
        a_rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {a: 1.0 for a in easyhard_ab._AXES} | {
                    "gold_dropped_head": 0.0,
                    "gold_dropped_head_gold_count": 1.0,
                },
                "pred_refs": ["Article 5"],
                "gold_refs": ["Article 5"],
            }
        ]
        b_rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {a: 1.0 for a in easyhard_ab._AXES} | {
                    "gold_dropped_head": 1.0,
                    "gold_dropped_head_gold_count": 1.0,
                },
                "pred_refs": ["Article 6"],
                "gold_refs": ["Article 5"],
            }
        ]
        p = easyhard_ab._paired(a_rows, b_rows)
        # Verify gold_dropped_head and gold_dropped_head_gold_count are computed
        assert p["easy"]["baseline"]["gold_dropped_head"] == 0
        assert p["easy"]["branch"]["gold_dropped_head"] == 1
        assert p["easy"]["baseline"]["gold_dropped_head_gold_count"] == 1
        assert p["easy"]["branch"]["gold_dropped_head_gold_count"] == 1

    def test_report_single_arm_and_all_errors(self, monkeypatch):
        # Capture stdout
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)

        # Single arm with n > 0
        base_ok = {
            "easy": {
                "n": 1, "errors": 0,
                "ref_loose": 1.0, "ref_strict": 1.0, "ref_conc": 1.0,
                "tone": 1.0, "kw_recall": 1.0, "pred_gold_ratio": 1.0,
                "gold_dropped_head": 0, "gold_dropped_head_gold_count": 1,
                "latency_p50_ms": 100.0,
            }
        }
        easyhard_ab._report("single_test", base_ok, None)
        out = buf.getvalue()
        assert "single_test — easy (n=1, errors=0)" in out
        assert "gold_drop_hd" in out

        # Single arm with 100% errors (n=0)
        buf.seek(0)
        buf.truncate(0)
        base_err = {"easy": {"n": 0, "errors": 5}}
        easyhard_ab._report("err_test", base_err, None)
        assert buf.getvalue() == ""  # Safely skipped

    def test_report_branch_arm_100_percent_error_vulnerability(self, monkeypatch):
        """Audits _report behavior when branch arm has 100% errors (n=0)."""
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        base_ok = {
            "easy": {
                "n": 2, "errors": 0,
                "ref_loose": 1.0, "ref_strict": 1.0, "ref_conc": 1.0,
                "tone": 1.0, "kw_recall": 1.0, "pred_gold_ratio": 1.0,
                "gold_dropped_head": 0, "gold_dropped_head_gold_count": 2,
                "latency_p50_ms": 100.0,
            }
        }
        branch_all_err = {"easy": {"n": 0, "errors": 2}}

        # Safely handled without KeyError
        easyhard_ab._report("ab_test", base_ok, branch_all_err)
        out = buf.getvalue()
        assert "Branch arm produced 0 successful rows" in out

    def test_report_paired_empty_and_normal(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)

        # Empty paired
        easyhard_ab._report_paired("test_p", {"easy": {"n": 0}, "hard": {"n": 0}})
        assert buf.getvalue() == ""  # Safely does not print

        # Non-empty paired
        paired_data = {
            "easy": {
                "n": 1,
                "baseline": {a: 0.8 for a in easyhard_ab._AXES} | {
                    "pred_gold_ratio": 1.0, "gold_dropped_head": 0
                },
                "branch": {a: 0.9 for a in easyhard_ab._AXES} | {
                    "pred_gold_ratio": 1.0, "gold_dropped_head": 0
                },
                "uplift_pp": 1.5,
            }
        }
        easyhard_ab._report_paired("test_p", paired_data)
        out = buf.getvalue()
        assert "test_p — easy PAIRED" in out
        assert "est. Overall uplift" in out


# ════════════════════════════════════════════════════════════════════════════
# 4. Answer Correctness, Conciseness, Tone & Aggregate Metric Tests
# ════════════════════════════════════════════════════════════════════════════


class TestBenchMetricsAdversarial:
    def test_answer_correctness_all_variants_empty_inputs(self):
        assert metrics.answer_correctness_loose("", "") == 0.0
        assert metrics.answer_correctness_strict("", "") == 0.0
        assert metrics.answer_correctness_precision("", "") == 0.0
        assert metrics.answer_correctness_f1("", "") == 0.0
        assert metrics.pred_gold_token_ratio("", "") == 0.0

        assert metrics.answer_correctness_loose("Some answer", "") == 0.0
        assert metrics.answer_correctness_loose("", "Some gold") == 0.0

    def test_answer_correctness_stopwords_only(self):
        # Stopwords only ("the is and") -> empty token sets after filter
        assert metrics.answer_correctness_loose("the is and", "for with as") == 0.0
        assert metrics.answer_correctness_strict("the is and", "for with as") == 0.0
        assert metrics.answer_correctness_precision("the is and", "for with as") == 0.0
        assert metrics.answer_correctness_f1("the is and", "for with as") == 0.0
        assert metrics.pred_gold_token_ratio("the is and", "for with as") == 0.0

    def test_pred_gold_token_ratio_zero_division_guard(self):
        # Empty gold -> 0.0
        assert metrics.pred_gold_token_ratio("long answer with tokens", "") == 0.0
        # Empty pred -> 0.0
        assert metrics.pred_gold_token_ratio("", "gold answer with tokens") == 0.0

    def test_answer_keyword_recall_adversarial(self):
        assert metrics.answer_keyword_recall("any text", None) is None
        assert metrics.answer_keyword_recall("any text", []) is None
        # Keyword list with only stopwords
        assert metrics.answer_keyword_recall("any text", ["the", "is"]) is None
        # Empty pred with valid keywords -> 0.0
        assert metrics.answer_keyword_recall("", ["prohibited", "subliminal"]) == 0.0

    def test_answer_conciseness_adversarial(self):
        # Both empty -> 1.0
        assert metrics.answer_conciseness("", "") == 1.0
        assert metrics.answer_conciseness(None, None) == 1.0  # type: ignore[arg-type]

        # One empty -> 0.0
        assert metrics.answer_conciseness("text", "") == 0.0
        assert metrics.answer_conciseness("", "text") == 0.0

        # Asymmetric quadratic falloff: 3x difference -> ratio 1/3 -> 1/9
        s_3x = metrics.answer_conciseness("a" * 300, "a" * 100)
        assert abs(s_3x - 1.0 / 9.0) < 1e-6

    def test_regulatory_tone_adversarial_patterns(self):
        # Empty text -> 0.0
        assert metrics.regulatory_tone("") == 0.0
        assert metrics.regulatory_tone(None) == 0.0  # type: ignore[arg-type]

        # AI Assistant preambles vs EUR-Lex "as an AI system"
        t_assistant = metrics.regulatory_tone("As an AI assistant, I recommend Article 5.")
        t_system = metrics.regulatory_tone("Placing on the market as an AI system under Article 5.")
        assert t_system > t_assistant

        # Severe penalties: emoji + conversational filler + hedging
        t_casual = metrics.regulatory_tone("Hey there! 😊 I think maybe this might be prohibited under **Article 5**.")
        assert t_casual < 0.60

        # High score: clean regulator prose
        t_clean = metrics.regulatory_tone("Providers shall maintain technical documentation pursuant to Article 11 and Annex IV.")
        assert t_clean >= 0.95

    def test_percentile_adversarial(self):
        assert metrics.percentile([], 50) == 0.0
        assert metrics.percentile([10.0], 50) == 10.0
        assert metrics.percentile([10.0, 20.0, 30.0], 0) == 10.0
        assert metrics.percentile([10.0, 20.0, 30.0], 100) == 30.0
        assert metrics.percentile([10.0, 20.0, 30.0], -10) == 10.0
        assert metrics.percentile([10.0, 20.0, 30.0], 150) == 30.0

    def test_refusal_correctness_adversarial(self):
        assert metrics.refusal_correctness([]) == 0.0
        assert metrics.refusal_correctness([True, True, True]) == 1.0
        assert metrics.refusal_correctness([False, False]) == 0.0
        assert metrics.refusal_correctness([True, False]) == 0.5

    def test_batch_aggregate_adversarial(self):
        # Empty rows
        assert metrics.aggregate([]) == {}

        # Row with keyword recall
        r = metrics.score_row(
            pred_answer="Article 5 prohibits subliminal manipulation.",
            pred_refs=["Article 5"],
            gold_answer="Article 5 prohibits subliminal AI.",
            gold_articles=5,
            latency_ms=12.5,
            expected_keywords=["subliminal", "prohibits"],
        )
        agg = metrics.aggregate([r])
        assert agg["n"] == 1
        assert agg["ans_keyword_recall"] == 1.0
        assert "pred_gold_token_ratio" in agg
        assert "ans_correctness_f1" in agg
        assert "ans_correctness_precision" in agg
