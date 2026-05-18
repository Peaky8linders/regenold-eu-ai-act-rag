"""R50 — LLM-as-Judge unit tests (no live LLM calls).

Locks in:
* All 4 axis prompts render against a sample row without raising.
* render(axis) dispatches correctly.
* Unknown axes raise.
* _parse_judge_json handles markdown fences, leading thinking,
  unbalanced braces, and clean JSON.
* _aggregate_judge correctly buckets passes / fails / errors and
  ranks failure modes by frequency.
"""
from __future__ import annotations

import pytest

from evals.judge.prompts import (
    AXES,
    render,
    render_axis_conciseness,
    render_axis_correctness,
    render_axis_refs,
    render_axis_tone,
)
from evals.judge.runner import (
    _aggregate_judge,
    _parse_judge_json,
)


_SAMPLE_ROW = {
    "id": "tr_v2_001",
    "category": "omnibus",
    "question": "After the 7 May 2026 Digital Omnibus agreement, when do Annex III high-risk obligations apply?",
    "expected_refs": ["Article 113"],
    "expected_keywords": ["2 December 2027", "Annex III"],
    "pred_refs": ["Article 113"],
    "answer_preview": (
        "Per Article 113 as amended by the Digital Omnibus agreement, "
        "Annex III high-risk obligations apply from 2 December 2027."
    ),
}

_SAMPLE_SUMMARIES = {
    "Article 113": (
        "Application timeline: Art. 5 prohibitions from 2 February 2025; "
        "GPAI provisions from 2 August 2025; Annex III high-risk from "
        "2 December 2027 (Digital Omnibus update); Annex I embedded-product "
        "from 2 August 2028."
    ),
}


# ── Prompt rendering ────────────────────────────────────────────────────


class TestPromptRendering:
    def test_correctness_prompt_includes_gold_and_predicted(self) -> None:
        p = render_axis_correctness(_SAMPLE_ROW)
        assert "Article 113" in p  # gold ref
        assert "2 December 2027" in p  # gold keyword
        assert "Annex III high-risk obligations apply" in p  # predicted answer
        assert "JSON" in p  # output instruction

    def test_refs_prompt_includes_kb_summaries(self) -> None:
        p = render_axis_refs(_SAMPLE_ROW, _SAMPLE_SUMMARIES)
        assert "Article 113" in p
        # KB summary should appear
        assert "Application timeline" in p
        # JSON instruction
        assert "JSON" in p

    def test_refs_prompt_handles_missing_summaries(self) -> None:
        """Missing KB summaries should not crash; the prompt should
        still render with a graceful 'no KB summaries available' note."""
        p = render_axis_refs(_SAMPLE_ROW, {})
        assert "Article 113" in p
        assert "no KB summaries" in p or "summary" in p.lower()

    def test_conciseness_prompt_carries_predicted_length(self) -> None:
        p = render_axis_conciseness(_SAMPLE_ROW)
        # Predicted answer length should be quoted in chars
        assert "chars" in p
        assert "1..4" in p  # spec range

    def test_tone_prompt_carries_anchor_examples(self) -> None:
        p = render_axis_tone(_SAMPLE_ROW)
        # The three anchor examples are baked in
        assert "Providers of high-risk AI systems" in p
        assert "fundamental rights impact assessment" in p
        assert "Article 5 prohibits" in p

    def test_dispatch_renders_each_axis(self) -> None:
        for axis in AXES:
            p = render(axis, _SAMPLE_ROW, article_summaries=_SAMPLE_SUMMARIES)
            assert isinstance(p, str)
            assert len(p) > 100

    def test_dispatch_raises_on_unknown_axis(self) -> None:
        with pytest.raises(ValueError):
            render("bogus_axis", _SAMPLE_ROW)


# ── JSON parser ─────────────────────────────────────────────────────────


class TestParseJudgeJson:
    def test_clean_json_parses(self) -> None:
        result = _parse_judge_json(
            '{"verdict":"pass","correct":3,"failure_mode":""}'
        )
        assert result == {"verdict": "pass", "correct": 3, "failure_mode": ""}

    def test_markdown_fence_stripped(self) -> None:
        text = '```json\n{"verdict":"fail","failure_mode":"cite-mismatch"}\n```'
        result = _parse_judge_json(text)
        assert result.get("verdict") == "fail"
        assert result.get("failure_mode") == "cite-mismatch"

    def test_leading_thinking_skipped(self) -> None:
        text = (
            'Let me think about this carefully.\n'
            '{"verdict":"pass","correct":2,"failure_mode":""}'
        )
        result = _parse_judge_json(text)
        assert result.get("verdict") == "pass"

    def test_empty_response_returns_error(self) -> None:
        assert _parse_judge_json("").get("judge_error") == "empty_response"

    def test_no_json_returns_error(self) -> None:
        result = _parse_judge_json("This is just prose, no JSON at all.")
        assert "judge_error" in result

    def test_unbalanced_braces_returns_error(self) -> None:
        result = _parse_judge_json('{"verdict":"pass", "extra":{"inner":1')
        assert "judge_error" in result

    def test_invalid_json_returns_error(self) -> None:
        result = _parse_judge_json('{"verdict": pass}')  # unquoted value
        assert "judge_error" in result


# ── Aggregation ─────────────────────────────────────────────────────────


class TestAggregation:
    def test_empty_rows_yields_zeros(self) -> None:
        agg = _aggregate_judge([])
        for axis in AXES:
            a = agg[axis]
            assert a["n"] == 0
            assert a["pass"] == 0
            assert a["fail"] == 0
            assert a["error"] == 0
            assert a["pass_rate"] == 0.0

    def test_mixed_verdicts_bucket_correctly(self) -> None:
        rows = [
            {"id": "r1", "verdicts": {
                "correctness": {"verdict": "pass"},
                "refs": {"verdict": "fail", "failure_mode": "cite-mismatch"},
                "conciseness": {"verdict": "pass"},
                "tone": {"verdict": "pass"},
            }},
            {"id": "r2", "verdicts": {
                "correctness": {"verdict": "fail", "failure_mode": "stale-KB"},
                "refs": {"verdict": "fail", "failure_mode": "cite-mismatch"},
                "conciseness": {"judge_error": "wrapper_down"},
                "tone": {"verdict": "pass"},
            }},
        ]
        agg = _aggregate_judge(rows)
        # correctness: 1 pass, 1 fail
        assert agg["correctness"]["pass"] == 1
        assert agg["correctness"]["fail"] == 1
        assert agg["correctness"]["pass_rate"] == 0.5
        # refs: 0 pass, 2 fail — failure mode dedup
        assert agg["refs"]["fail"] == 2
        assert agg["refs"]["top_failure_modes"][0] == ("cite-mismatch", 2)
        # conciseness: 1 pass, 1 error (wrapper down)
        assert agg["conciseness"]["pass"] == 1
        assert agg["conciseness"]["error"] == 1

    def test_top_failure_modes_capped_at_ten(self) -> None:
        rows = []
        for i in range(20):
            rows.append({"id": f"r{i}", "verdicts": {
                "tone": {"verdict": "fail", "failure_mode": f"mode_{i}"},
            }})
        agg = _aggregate_judge(rows)
        assert len(agg["tone"]["top_failure_modes"]) <= 10
