"""Unit tests for the paper-aligned eval metrics.

Verifies the metric helpers in :mod:`evals.regenold.runner` directly,
bypassing the full eval harness. Each test drives ``ScenarioResult``
fixtures so we can pin exact precision/recall/F1 numbers and confirm
edge cases (empty gold, empty predictions, perfect classifier).

Cited paper: Davvetas et al., arXiv:2603.09435v1, Section 5 / Table 4.
"""
from __future__ import annotations

from evals.regenold.runner import (
    RISK_CLASSES,
    ScenarioResult,
    _compute_classification_metrics,
    _compute_retrieval_metrics,
    _normalise_risk_label,
    _predict_risk_class,
    _predicted_ref_heads,
    _ref_head,
)


def _result(
    *,
    sid: str = "fixture",
    gold: str | None = None,
    pred: str | None = None,
    expected_refs: tuple[str, ...] = (),
    predicted_refs: tuple[str, ...] = (),
) -> ScenarioResult:
    """Build a minimal ScenarioResult for metric tests."""
    return ScenarioResult(
        scenario_id=sid,
        category="fixture",
        description="fixture",
        http_status=200,
        response_excerpt={},
        check_results=[],
        passed=True,
        duration_ms=0.0,
        risk_label_gold=gold,
        risk_label_pred=pred,
        expected_references=expected_refs,
        predicted_references=predicted_refs,
    )


# ── Classification metrics ───────────────────────────────────────────────


def test_classification_no_labeled_scenarios_returns_nulls() -> None:
    """No gold labels → all per-class F1s are None (NaN-equivalent)."""
    results = [_result(gold=None, pred="prohibited")]
    out = _compute_classification_metrics(results)
    assert out["labeled_scenarios"] == 0
    assert out["macro_f1"] is None
    assert all(v is None for v in out["per_class_f1"].values())
    assert all(v is None for v in out["per_class_precision"].values())
    assert all(v is None for v in out["per_class_recall"].values())
    assert out["confusion"] == {}


def test_classification_perfect_classifier_gives_f1_of_1() -> None:
    """A classifier that always predicts the gold class scores F1 = 1.0."""
    results = [
        _result(sid="a", gold="prohibited", pred="prohibited"),
        _result(sid="b", gold="prohibited", pred="prohibited"),
        _result(sid="c", gold="high_risk", pred="high_risk"),
        _result(sid="d", gold="refusal", pred="refusal"),
    ]
    out = _compute_classification_metrics(results)
    assert out["labeled_scenarios"] == 4
    assert out["per_class_f1"]["prohibited"] == 1.0
    assert out["per_class_f1"]["high_risk"] == 1.0
    assert out["per_class_f1"]["refusal"] == 1.0
    # Untouched classes are None, not 0.
    assert out["per_class_f1"]["limited"] is None
    assert out["per_class_f1"]["minimal"] is None
    # Macro is averaged only over scored classes.
    assert out["macro_f1"] == 1.0


def test_classification_perfect_recall_imperfect_precision() -> None:
    """Predict 'prohibited' for everything → P<1, R=1 on prohibited."""
    results = [
        _result(sid="a", gold="prohibited", pred="prohibited"),
        _result(sid="b", gold="high_risk", pred="prohibited"),
        _result(sid="c", gold="high_risk", pred="prohibited"),
    ]
    out = _compute_classification_metrics(results)
    # TP=1, FP=2, FN=0 for prohibited → P=1/3, R=1.0, F1=0.5.
    assert out["per_class_precision"]["prohibited"] == round(1 / 3, 4)
    assert out["per_class_recall"]["prohibited"] == 1.0
    f1_p = out["per_class_f1"]["prohibited"]
    assert f1_p is not None
    assert abs(f1_p - 0.5) < 1e-3
    # High-risk: TP=0, FN=2 → P=None? No — there were no positive
    # predictions either; tp+fn>0 means we DO score it.
    assert out["per_class_recall"]["high_risk"] == 0.0
    assert out["per_class_f1"]["high_risk"] == 0.0


def test_classification_out_of_scope_folds_to_refusal() -> None:
    """The 'out_of_scope' alias is collapsed to 'refusal' for matrix bucketing."""
    results = [
        _result(sid="a", gold="out_of_scope", pred="refusal"),
        _result(sid="b", gold="out_of_scope", pred="refusal"),
    ]
    out = _compute_classification_metrics(results)
    assert out["per_class_f1"]["refusal"] == 1.0
    # Confusion matrix shows refusal/refusal, not out_of_scope/refusal.
    assert out["confusion"] == {"refusal": {"refusal": 2}}


def test_classification_unpredicted_counts_as_miss() -> None:
    """A None prediction on a labeled gold counts as FN, never TP."""
    results = [
        _result(sid="a", gold="prohibited", pred=None),
        _result(sid="b", gold="prohibited", pred="prohibited"),
    ]
    out = _compute_classification_metrics(results)
    # TP=1, FP=0, FN=1 → P=1.0, R=0.5, F1=0.667.
    assert out["per_class_precision"]["prohibited"] == 1.0
    assert out["per_class_recall"]["prohibited"] == 0.5
    f1 = out["per_class_f1"]["prohibited"]
    assert f1 is not None
    assert abs(f1 - 2 / 3) < 1e-3


# ── Retrieval metrics ────────────────────────────────────────────────────


def test_retrieval_no_labeled_scenarios_returns_nulls() -> None:
    """Empty gold across the board → labeled_scenarios=0 and None metrics."""
    results = [_result(expected_refs=(), predicted_refs=("Article 13",))]
    out = _compute_retrieval_metrics(results)
    assert out["labeled_scenarios"] == 0
    assert out["weighted_precision"] is None
    assert out["weighted_recall"] is None
    assert out["weighted_f1"] is None


def test_retrieval_perfect_match_gives_1_0() -> None:
    """Predicted == gold → P=R=F1=1.0."""
    results = [
        _result(
            sid="a",
            expected_refs=("Article 13",),
            predicted_refs=("Article 13",),
        ),
        _result(
            sid="b",
            expected_refs=("Article 5",),
            predicted_refs=("Article 5",),
        ),
    ]
    out = _compute_retrieval_metrics(results)
    assert out["labeled_scenarios"] == 2
    assert out["weighted_precision"] == 1.0
    assert out["weighted_recall"] == 1.0
    assert out["weighted_f1"] == 1.0


def test_retrieval_precision_zero_when_predicted_empty() -> None:
    """Empty predicted refs → precision = 0 (recall is also 0 → F1=0)."""
    results = [
        _result(
            sid="a",
            expected_refs=("Article 13",),
            predicted_refs=(),
        ),
    ]
    out = _compute_retrieval_metrics(results)
    assert out["weighted_precision"] == 0.0
    assert out["weighted_recall"] == 0.0
    assert out["weighted_f1"] == 0.0


def test_retrieval_recall_one_when_gold_subset_of_predicted() -> None:
    """Gold ⊂ Predicted → recall = 1.0; precision < 1 (extras)."""
    results = [
        _result(
            sid="a",
            expected_refs=("Article 13",),
            predicted_refs=("Article 13", "Article 26"),
        ),
    ]
    out = _compute_retrieval_metrics(results)
    assert out["weighted_recall"] == 1.0
    assert out["weighted_precision"] == 0.5
    # F1 = 2 * 0.5 * 1.0 / 1.5 = 0.6667
    f1 = out["weighted_f1"]
    assert f1 is not None
    assert abs(f1 - 2 / 3) < 1e-3


def test_retrieval_weighted_mean_across_scenarios() -> None:
    """Two scenarios with different precision → mean of both."""
    results = [
        _result(
            sid="a",
            expected_refs=("Article 13",),
            predicted_refs=("Article 13",),  # P=R=F1=1.0
        ),
        _result(
            sid="b",
            expected_refs=("Article 5",),
            predicted_refs=("Article 99",),  # P=R=F1=0.0
        ),
    ]
    out = _compute_retrieval_metrics(results)
    assert out["weighted_precision"] == 0.5
    assert out["weighted_recall"] == 0.5
    assert out["weighted_f1"] == 0.5


# ── Helper predicates ────────────────────────────────────────────────────


def test_ref_head_strips_subsegments() -> None:
    assert _ref_head("Article 13.1.a") == "Article 13"
    assert _ref_head("Article 5") == "Article 5"
    assert _ref_head("Annex IV.2.c") == "Annex IV"
    assert _ref_head("Annex IV") == "Annex IV"
    assert _ref_head("garbage") is None
    assert _ref_head(None) is None  # type: ignore[arg-type]


def test_predicted_ref_heads_dedupes() -> None:
    body = {"references": ["Article 13.1", "Article 13.2.a", "Annex IV"]}
    assert _predicted_ref_heads(body) == ("Article 13", "Annex IV")


def test_predicted_ref_heads_handles_missing_or_malformed() -> None:
    assert _predicted_ref_heads({}) == ()
    assert _predicted_ref_heads({"references": None}) == ()
    assert _predicted_ref_heads({"references": "not a list"}) == ()


def test_normalise_risk_label_collapses_alias() -> None:
    assert _normalise_risk_label("out_of_scope") == "refusal"
    assert _normalise_risk_label("refusal") == "refusal"
    assert _normalise_risk_label("prohibited") == "prohibited"
    assert _normalise_risk_label(None) is None


def test_predict_risk_class_prohibited_marker() -> None:
    body = {
        "answer": "Social scoring is prohibited under Article 5(1)(c).",
        "references": ["Article 5"],
    }
    assert _predict_risk_class(body) == "prohibited"


def test_predict_risk_class_high_risk_marker() -> None:
    body = {
        "answer": "Credit scoring AI is high-risk under Annex III.",
        "references": ["Annex III"],
    }
    assert _predict_risk_class(body) == "high_risk"


def test_predict_risk_class_negative_high_risk_returns_none() -> None:
    """'X is not high-risk' must not trip the high-risk predictor."""
    body = {
        "answer": "This system is not high-risk because it's not in Annex III.",
        "references": ["Annex III"],
    }
    assert _predict_risk_class(body) != "high_risk"


def test_predict_risk_class_refusal_with_empty_refs() -> None:
    body = {
        "answer": "Article 200 does not appear in the EU AI Act.",
        "references": [],
    }
    assert _predict_risk_class(body) == "refusal"


def test_predict_risk_class_refusal_via_http_status() -> None:
    body = {"answer": "validation error", "references": [], "__http_status": 422}
    assert _predict_risk_class(body) == "refusal"


def test_risk_classes_includes_all_four_tiers_plus_refusal() -> None:
    """Smoke test — the four paper tiers + refusal must all be enumerated."""
    assert set(RISK_CLASSES) == {
        "prohibited",
        "high_risk",
        "limited",
        "minimal",
        "refusal",
    }
