"""Regression tests for the easyhard_ab paired-subset A/B read.

The R282 live easy run lost 36 of 95 branch rows to wrapper 429s, so the two
full-arm aggregates spanned different row sets (baseline n=95 vs branch n=59)
and were not comparable — the honest read (n=59 paired) had to be recomputed by
hand. `_paired` makes that intersection automatic; these tests pin it.
"""
from __future__ import annotations

from evals.harness.easyhard_ab import _LEVERAGE, _paired


def _row(rid, hard, scores, pred, gold, error=None):
    r = {
        "id": rid,
        "is_multiturn": hard,
        "pred_refs": pred,
        "gold_refs": gold,
    }
    if error:
        r["error"] = error
    else:
        r["scores"] = scores
    return r


_S = {"ref_loose": 1.0, "ref_strict": 0.5, "ref_conc": 0.4, "tone": 1.0, "kw_recall": 1.0}
_S2 = {"ref_loose": 1.0, "ref_strict": 0.6, "ref_conc": 0.5, "tone": 1.0, "kw_recall": 1.0}


def test_paired_intersects_on_rows_ok_in_both_arms():
    # baseline scores 3 easy rows; branch 429s on e2 → paired must be {e1, e3}.
    a = [
        _row("e1", False, _S, ["Article 6", "Article 9"], ["Article 6"]),
        _row("e2", False, _S, ["Article 6"], ["Article 6"]),
        _row("e3", False, _S, ["Article 6", "Article 9"], ["Article 6"]),
    ]
    b = [
        _row("e1", False, _S2, ["Article 6"], ["Article 6"]),
        _row("e2", False, None, [], ["Article 6"], error="http_429"),
        _row("e3", False, _S2, ["Article 6"], ["Article 6"]),
    ]
    easy = _paired(a, b)["easy"]
    assert easy["n"] == 2  # NOT 3 — e2 excluded
    # baseline means over the SAME 2 rows the branch completed
    assert easy["baseline"]["ref_strict"] == 0.5
    assert easy["branch"]["ref_strict"] == 0.6
    # pred:gold over the paired subset: baseline 4/2=2.0, branch 2/2=1.0
    assert easy["baseline"]["pred_gold_ratio"] == 2.0
    assert easy["branch"]["pred_gold_ratio"] == 1.0


def test_paired_uplift_is_leverage_weighted():
    a = [_row("e1", False, _S, ["Article 6"], ["Article 6"])]
    b = [_row("e1", False, _S2, ["Article 6"], ["Article 6"])]
    easy = _paired(a, b)["easy"]
    expected = (
        _LEVERAGE["ref_strict"] * (0.6 - 0.5) * 100
        + _LEVERAGE["ref_conc"] * (0.5 - 0.4) * 100
        + _LEVERAGE["ref_loose"] * (1.0 - 1.0) * 100
    )
    assert abs(easy["uplift_pp"] - expected) < 1e-9


def test_paired_equals_full_agg_when_no_rows_lost():
    # Clean A/B (both arms complete every row) → paired n == arm n.
    a = [_row(f"h{i}", True, _S, ["Article 6"], ["Article 6"]) for i in range(4)]
    b = [_row(f"h{i}", True, _S2, ["Article 6"], ["Article 6"]) for i in range(4)]
    hard = _paired(a, b)["hard"]
    assert hard["n"] == 4
    assert hard["branch"]["ref_strict"] == 0.6


def test_paired_splits_easy_vs_hard():
    a = [
        _row("e1", False, _S, ["Article 6"], ["Article 6"]),
        _row("h1", True, _S, ["Article 6"], ["Article 6"]),
    ]
    b = [
        _row("e1", False, _S2, ["Article 6"], ["Article 6"]),
        _row("h1", True, _S2, ["Article 6"], ["Article 6"]),
    ]
    out = _paired(a, b)
    assert out["easy"]["n"] == 1
    assert out["hard"]["n"] == 1
