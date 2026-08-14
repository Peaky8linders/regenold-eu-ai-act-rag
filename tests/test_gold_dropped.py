"""Tests for gold_dropped_head metric and easyhard_ab harness integration (R332)."""
from __future__ import annotations

from evals.bench.metrics import gold_dropped_head
from evals.harness.easyhard_ab import _aggregate, _paired, _score_row
from evals.harness.probe_set import ProbeRow


class TestGoldDroppedHead:
    def test_head_match_zero_dropped(self):
        res = gold_dropped_head(["Article 5"], ["Article 5"])
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

    def test_subpoint_prediction_covers_head(self):
        # A more-precise prediction than gold does NOT drop gold at head grain
        res = gold_dropped_head(["Article 5.1.f"], ["Article 5"])
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

    def test_annex_subpoint_prediction_covers_head(self):
        res = gold_dropped_head(["Annex III.5.a"], ["Annex III"])
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

    def test_missing_ref_counts_as_dropped(self):
        res = gold_dropped_head(["Article 6"], ["Article 5"])
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 1
        assert res["dropped_refs"] == ["Article 5"]

    def test_partial_coverage(self):
        res = gold_dropped_head(["Article 5"], ["Article 5", "Annex III"])
        assert res["gold_count"] == 2
        assert res["dropped_count"] == 1
        assert res["dropped_refs"] == ["Annex III"]

    def test_empty_prediction(self):
        res = gold_dropped_head([], ["Article 5", "Annex III"])
        assert res["gold_count"] == 2
        assert res["dropped_count"] == 2
        assert res["dropped_refs"] == ["Annex III", "Article 5"]

    def test_empty_gold(self):
        res = gold_dropped_head(["Article 5"], [])
        assert res["gold_count"] == 0
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

    def test_integer_gold_format(self):
        res = gold_dropped_head(["Article 5"], 5)
        assert res["gold_count"] == 1
        assert res["dropped_count"] == 0
        assert res["dropped_refs"] == []

    def test_list_integer_gold_format(self):
        res = gold_dropped_head(["Article 5"], [5, 6])
        assert res["gold_count"] == 2
        assert res["dropped_count"] == 1
        assert res["dropped_refs"] == ["Article 6"]


class TestEasyHardWiring:
    def test_score_row_includes_gold_dropped_keys(self):
        row = ProbeRow(
            id="test_01",
            source="test",
            category="test",
            is_multiturn=False,
            messages=[{"role": "user", "content": "What is Article 5?"}],
            expected_refs=["Article 5"],
            expected_keywords=["prohibited"],
        )
        scores = _score_row(row, "Prohibited AI practices.", ["Article 5.1.a"])
        assert "gold_dropped_head" in scores
        assert "gold_dropped_head_gold_count" in scores
        assert "gold_dropped_head_refs" in scores
        assert scores["gold_dropped_head"] == 0.0
        assert scores["gold_dropped_head_gold_count"] == 1.0
        assert scores["gold_dropped_head_refs"] == []

    def test_aggregate_sums_gold_dropped(self):
        rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {
                    "ref_loose": 1.0,
                    "ref_strict": 1.0,
                    "ref_conc": 1.0,
                    "tone": 1.0,
                    "kw_recall": 1.0,
                    "gold_dropped_head": 0.0,
                    "gold_dropped_head_gold_count": 1.0,
                },
                "pred_refs": ["Article 5"],
                "gold_refs": ["Article 5"],
                "latency_ms": 100,
            },
            {
                "id": "e2",
                "is_multiturn": False,
                "scores": {
                    "ref_loose": 0.0,
                    "ref_strict": 0.0,
                    "ref_conc": 0.0,
                    "tone": 1.0,
                    "kw_recall": 1.0,
                    "gold_dropped_head": 1.0,
                    "gold_dropped_head_gold_count": 1.0,
                },
                "pred_refs": ["Article 6"],
                "gold_refs": ["Article 5"],
                "latency_ms": 100,
            },
        ]
        agg = _aggregate(rows)
        # Gold dropped MUST be summed (0 + 1 = 1), not averaged (0.5)
        assert agg["gold_dropped_head"] == 1
        assert agg["gold_dropped_head_gold_count"] == 2

    def test_aggregate_backward_compat_missing_key(self):
        # Rows without gold_dropped_head (pre-R332 checkpoints) should aggregate cleanly
        rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {
                    "ref_loose": 1.0,
                    "ref_strict": 1.0,
                    "ref_conc": 1.0,
                    "tone": 1.0,
                    "kw_recall": 1.0,
                },
                "pred_refs": ["Article 5"],
                "gold_refs": ["Article 5"],
                "latency_ms": 100,
            }
        ]
        agg = _aggregate(rows)
        assert agg["gold_dropped_head"] == 0
        assert agg["gold_dropped_head_gold_count"] == 0

    def test_paired_sums_gold_dropped(self):
        a_rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {
                    "ref_loose": 1.0,
                    "ref_strict": 1.0,
                    "ref_conc": 1.0,
                    "tone": 1.0,
                    "kw_recall": 1.0,
                    "gold_dropped_head": 0.0,
                },
                "pred_refs": ["Article 5"],
                "gold_refs": ["Article 5"],
            }
        ]
        b_rows = [
            {
                "id": "e1",
                "is_multiturn": False,
                "scores": {
                    "ref_loose": 0.0,
                    "ref_strict": 0.0,
                    "ref_conc": 0.0,
                    "tone": 1.0,
                    "kw_recall": 1.0,
                    "gold_dropped_head": 1.0,
                },
                "pred_refs": ["Article 6"],
                "gold_refs": ["Article 5"],
            }
        ]
        p = _paired(a_rows, b_rows)
        assert p["easy"]["baseline"]["gold_dropped_head"] == 0
        assert p["easy"]["branch"]["gold_dropped_head"] == 1
