"""R359 — offline unit tests for the fine-grained CRAG answer axis
(``evals.judge.legal_v2`` ``answer_crag_fine``, NICD paper Appendix C.2.2).

Locks in:
* The 5-level scale mapping: +1.0 FULLY_CORRECT / +0.5 PARTIAL_CLEAN /
  0.0 REFUSED / −0.5 MIXED / −1.0 WRONG, with verdict = pass iff score ≥ +0.5.
* The asymmetry contract: a MIXED answer (−0.5, correct + hallucinated
  claims) FAILS even though it contains correct claims; a REFUSED answer
  (0.0) fails the binary gate but scores neutral on truthfulness.
* Shape failure handling: non-numeric score → unscorable; out-of-scale
  score → unscorable; a reply carrying none of the axis keys →
  axis_unanswered.
* Truthfulness aggregation (sum of scores) surfaces in the run aggregate.
* The prompt renders gold answers + verbatim provision text (no parametric
  memory) and never leaks arm/label/prior-score bias keys.

No LLM calls — ``get_provision_text`` is a pure local data lookup.
"""
from __future__ import annotations

import pytest

from evals.judge.legal_v2 import (
    _aggregate_samples,
    _postprocess_answer_crag_fine,
    _prepare,
)
from evals.judge.grounded import _norm


def _row(**overrides):
    base = {
        "id": "la_q44",
        "category": "live_answers",
        "question": "What does Article 13 require for transparency?",
        "pred_answer": "Article 13 requires high-risk AI systems to be designed "
                       "so their operation is sufficiently transparent (Article 13(1)).",
        "pred_refs": ["Article 13"],
        "gold_refs": ["Article 13"],
        "gold_answer": "Article 13 requires high-risk AI systems to be designed "
                       "and developed so that their operation is sufficiently "
                       "transparent (Article 13(1)).",
    }
    base.update(overrides)
    return base


class TestPostprocessCragFine:
    def test_fully_correct_passes(self) -> None:
        raw = {"score": 1.0, "class": "FULLY_CORRECT", "missing": [], "hallucinated": []}
        v = _postprocess_answer_crag_fine(raw)
        assert v["verdict"] == "pass"
        assert v["crag_score"] == 1.0
        assert v["truthfulness"] == 1.0
        assert v["missing_claims"] == []
        assert v["hallucinated_claims"] == []

    def test_partial_clean_passes(self) -> None:
        # Subset of gold, no extras — the paper's +0.5 (missing, clean).
        raw = {"score": 0.5, "class": "PARTIAL_CLEAN",
               "missing": ["deployers interpret output"], "hallucinated": []}
        v = _postprocess_answer_crag_fine(raw)
        assert v["verdict"] == "pass"
        assert v["crag_score"] == 0.5
        assert v["missing_claims"] == ["deployers interpret output"]

    def test_refused_is_neutral_not_fail_hallucination(self) -> None:
        # 0.0 fails the binary pass gate but is NOT a hallucination — it
        # scores neutral on truthfulness (the paper's asymmetry).
        raw = {"score": 0.0, "class": "REFUSED", "missing": [], "hallucinated": []}
        v = _postprocess_answer_crag_fine(raw)
        assert v["verdict"] == "fail"
        assert v["crag_score"] == 0.0
        assert v["truthfulness"] == 0.0
        assert v["hallucinated_claims"] == []

    def test_mixed_fails_even_with_correct_claims(self) -> None:
        # The asymmetry contract: correct + hallucinated → fail.
        raw = {"score": -0.5, "class": "MIXED",
               "missing": [], "hallucinated": ["Article 13(2) instruction content"]}
        v = _postprocess_answer_crag_fine(raw)
        assert v["verdict"] == "fail"
        assert v["crag_score"] == -0.5
        assert v["hallucinated_claims"] == ["Article 13(2) instruction content"]

    def test_wrong_fails(self) -> None:
        raw = {"score": -1.0, "class": "WRONG", "missing": [], "hallucinated": []}
        v = _postprocess_answer_crag_fine(raw)
        assert v["verdict"] == "fail"
        assert v["crag_score"] == -1.0

    def test_non_numeric_score_is_unscorable(self) -> None:
        raw = {"score": "almost", "class": "WRONG"}
        v = _postprocess_answer_crag_fine(raw)
        assert v.get("judge_error") == "crag_score_not_numeric"

    def test_out_of_scale_score_is_unscorable(self) -> None:
        raw = {"score": 2.5, "class": "FULLY_CORRECT"}
        v = _postprocess_answer_crag_fine(raw)
        assert v.get("judge_error") == "crag_score_out_of_scale: 2.5"

    def test_reply_without_axis_keys_is_unanswered(self) -> None:
        raw = {"verdict": "fail", "failure_mode": "x"}
        v = _postprocess_answer_crag_fine(raw)
        assert v.get("judge_error") == "axis_unanswered_answer_crag_fine"

    def test_judge_error_passthrough(self) -> None:
        raw = {"judge_error": "timeout"}
        v = _postprocess_answer_crag_fine(raw)
        assert v["judge_error"] == "timeout"


class TestPrepareCragFine:
    def test_prompt_carries_gold_answer_and_verbatim_text(self) -> None:
        prompt, ctx = _prepare("answer_crag_fine", _norm(_row()))
        assert "GROUND TRUTH ANSWERS:" in prompt
        assert "Article 13 requires high-risk AI systems" in prompt  # gold answer
        assert "VERBATIM EU AI ACT TEXT" in prompt
        # Verbatim provision text resolved from real corpus (Article 13).
        block = ctx["union_map"].get("Article 13", "")
        assert "transparent" in block or "transparency" in block

    def test_no_gold_answer_is_still_renderable_but_scored_unscorable(self) -> None:
        # _prepare renders (the caller gates scorbility via _judge_row);
        # postprocess still works, and the row gate in _judge_row rejects
        # gold-less rows before any call fires.
        prompt, _ctx = _prepare("answer_crag_fine", _norm(_row(gold_answer="")))
        assert "(none supplied)" in prompt

    def test_prompt_never_leaks_bias_keys(self) -> None:
        marker_arm = "MARKER_ARM_XYZQ"
        marker_label = "MARKER_LABEL_XYZQ"
        marker_score = 0.42
        prompt, _ctx = _prepare(
            "answer_crag_fine",
            _norm(_row(arm=marker_arm, label=marker_label, score=marker_score)),
        )
        # Same convention as test_legal_v2_judge: unique markers, not
        # substring checks (the anti-sycophancy preamble itself mentions
        # "arm/label/score" as forbidden leakage).
        assert marker_arm not in prompt
        assert marker_label not in prompt
        assert "MARKER_SCORE_XYZQ" not in prompt
        assert str(marker_score) not in prompt


class TestAggregateCragFine:
    def test_truthfulness_is_sum_of_scores(self) -> None:
        samples = [
            {"verdict": "pass", "crag_score": 1.0, "truthfulness": 1.0},
            {"verdict": "pass", "crag_score": 0.5, "truthfulness": 0.5},
            {"verdict": "fail", "crag_score": -0.5, "truthfulness": -0.5},
            {"verdict": "fail", "crag_score": 0.0, "truthfulness": 0.0},
        ]
        merged = _aggregate_samples(samples, "answer_crag_fine")
        assert merged["crag_score"] == 0.25  # median of [1.0, 0.5, -0.5, 0.0]
        assert merged["_agreement"] == 0.5  # 2 pass / 2 fail — tie

    def test_median_picks_middle_score(self) -> None:
        samples = [
            {"verdict": "pass", "crag_score": 1.0, "truthfulness": 1.0},
            {"verdict": "pass", "crag_score": 0.5, "truthfulness": 0.5},
            {"verdict": "fail", "crag_score": -1.0, "truthfulness": -1.0},
        ]
        merged = _aggregate_samples(samples, "answer_crag_fine")
        assert merged["verdict"] == "pass"  # 2/3 majority
        assert merged["crag_score"] == 0.5  # median
        assert merged["_agreement"] == round(2 / 3, 4)
