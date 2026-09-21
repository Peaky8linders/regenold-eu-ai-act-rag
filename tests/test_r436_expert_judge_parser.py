from __future__ import annotations

from docs.measurements.r411.rejudge_current_answers import _parse_verdict


def test_expert_judge_parser_merges_appended_json_objects() -> None:
    raw = (
        '{"verdicts": [{"n": 1, "satisfied": true, "why": "yes"}]}'
        '{"tone": {"appropriate": true, "clear": true, "why": "clear"}}'
    )

    parsed = _parse_verdict(raw, 1)

    assert parsed["criteria_results"] == [True]
    assert parsed["tone_pass"] is True
    assert parsed["tone_why"] == "clear"


def test_expert_judge_parser_keeps_plain_json_behavior() -> None:
    parsed = _parse_verdict(
        '{"verdicts": [{"n": 1, "satisfied": false}], '
        '"tone": {"appropriate": false, "clear": true}}',
        1,
    )

    assert parsed["criteria_results"] == [False]
    assert parsed["tone_pass"] is False
