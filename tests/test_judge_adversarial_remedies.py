"""Unit tests for adversarial judge remedies and WandB JudgeBench optimizations."""
from __future__ import annotations

import json
from typing import Any
import pytest

from evals.judge.legal_v2 import (
    _quote_substantiated,
    _postprocess_reference_correctness,
    _aggregate_samples,
)
from evals.judge.runner import _parse_judge_json
from evals.harness.ab_judge import AxisResult
from evals.harness.pairwise_prompts import _escape_xml, render


class TestQuoteSubstantiationContiguous:
    def test_exact_substring_passes(self):
        text = (
            "A risk management system shall be established, implemented, documented and "
            "maintained in relation to high-risk AI systems."
        )
        quote = "A risk management system shall be established, implemented, documented"
        assert _quote_substantiated(quote, text) is True

    def test_short_quote_fails(self):
        text = "A risk management system shall be established, implemented, documented."
        quote = "A risk management system"
        assert _quote_substantiated(quote, text, min_words=8) is False

    def test_bag_of_words_anagram_fails(self):
        text = (
            "A risk management system shall be established, implemented, documented and "
            "maintained in relation to high-risk AI systems."
        )
        # All words exist in text, but order and phrasing are scrambled/invented
        fabricated = "established risk testing systems shall be implemented to maintain provider compliance"
        assert _quote_substantiated(fabricated, text) is False

    def test_minor_whitespace_and_punctuation_passes(self):
        text = (
            "Providers of high-risk AI systems shall establish, implement, document and "
            "maintain a continuous risk management system."
        )
        quote = '“Providers of high-risk AI systems shall establish, implement, document and maintain”'
        assert _quote_substantiated(quote, text) is True


class TestGhostCitationGate:
    def test_non_existent_citation_fails_as_wrong(self):
        raw = {
            "classifications": [
                {"ref": "Article 999", "class": "WRONG", "quote": "no verbatim text resolved"}
            ],
            "missing_governing": [],
            "failure_mode": "fabricated citation",
        }
        pred_refs = ["Article 999"]
        pred_map = {"Article 999": ""}  # Empty text for unresolvable citation
        gold_map = {"Article 9": "A risk management system shall be established..."}

        res = _postprocess_reference_correctness(raw, pred_map, gold_map, pred_refs)
        assert res["verdict"] == "fail"
        assert "Article 999" in res["wrong_refs"]
        assert "Article 999" not in res["supporting_refs"]

    def test_valid_supporting_citation_with_unsubstantiated_wrong_downgrades(self):
        raw = {
            "classifications": [
                {"ref": "Article 14", "class": "WRONG", "quote": "some made up quote that is not in text"}
            ],
            "missing_governing": [],
            "failure_mode": "unsubstantiated claim",
        }
        pred_refs = ["Article 14"]
        pred_map = {"Article 14": "High-risk AI systems shall be designed and developed in such a way to enable human oversight."}
        gold_map = {"Article 13": "High-risk AI systems shall be designed and developed in such a way to ensure transparency."}

        res = _postprocess_reference_correctness(raw, pred_map, gold_map, pred_refs)
        assert res["verdict"] == "pass"
        assert "Article 14" in res["supporting_refs"]
        assert "Article 14" not in res["wrong_refs"]


class TestCoherentMedoidAggregation:
    def test_medoid_selection_preserves_consistency(self):
        samples = [
            {
                "verdict": "pass",
                "governing_refs": ["Article 9"],
                "focus_precision": 0.5,
                "legal_soundness_precision": 1.0,
            },
            {
                "verdict": "pass",
                "governing_refs": ["Article 9", "Annex IV"],
                "focus_precision": 1.0,
                "legal_soundness_precision": 1.0,
            },
            {
                "verdict": "pass",
                "governing_refs": ["Article 9", "Annex IV"],
                "focus_precision": 1.0,
                "legal_soundness_precision": 1.0,
            },
        ]
        res = _aggregate_samples(samples, "reference_correctness")
        assert res["verdict"] == "pass"
        assert res["_agreement"] == 1.0
        assert res["focus_precision"] == 1.0
        assert len(res["governing_refs"]) == 2


class TestResilientJsonParser:
    def test_fenced_json_with_trailing_prose(self):
        text = '```json\n{"winner": "B", "comparative_reasoning": "B is more precise"}\n```\nNote: Verified against Art 9.'
        res = _parse_judge_json(text)
        assert res.get("winner") == "B"

    def test_raw_newlines_in_json_strings(self):
        text = '{\n"verdict": "fail",\n"failure_mode": "Line 1: missing tier.\nLine 2: missing actor."\n}'
        res = _parse_judge_json(text)
        assert res.get("verdict") == "fail"

    def test_python_dict_syntax(self):
        text = "{'verdict': 'pass', 'factual_score': 1.0, 'omission_present': False}"
        res = _parse_judge_json(text)
        assert res.get("verdict") == "pass"
        assert res.get("factual_score") == 1.0

    def test_multi_root_json_picks_schema_target(self):
        text = (
            '{"step1_audit": "The answer is partially complete."}\n'
            '{"verdict": "pass", "failure_mode": "none", "factual_score": 0.9}'
        )
        res = _parse_judge_json(text)
        assert res.get("verdict") == "pass"
        assert res.get("factual_score") == 0.9


class TestPairwiseAndAxisResult:
    def test_xml_escaping(self):
        assert _escape_xml("Article 5 <prohibited> & Article 6") == "Article 5 &lt;prohibited&gt; &amp; Article 6"

    def test_effective_win_rate_with_ties(self):
        res = AxisResult(axis="correctness", wins_b=9, wins_a=1, ties=90)
        # Decisive win rate was 0.900, but effective win rate accounts for ties: (9 + 45) / 100 = 0.540
        assert res.win_rate_b() == 0.9
        assert res.effective_win_rate_b(100) == 0.54
