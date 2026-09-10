"""R408 — both judgements of one answer are grouped into ONE judge call.

Answer correctness and regulatory tone judge the SAME candidate answer, yet the
judge paid two calls per repetition for it: 6 calls per row at ``repeats=3``,
660 per 110-row arm. Grouped mode asks for the criteria verdicts and the tone
verdict in one reply, 3 calls per row.

Grouped verdicts carry their own judge identity, so they are never served from
or written into a split-call cache entry, and the split identity is byte-
identical to the pre-R408 string so existing caches still hit. Every
transport-guard invariant R393 pins for the split regime is pinned here for the
grouped one, by call count and parsed output rather than by source text.
"""
from __future__ import annotations

import pytest

from evals.official import judge as J

_BOTH = (
    '{"verdicts":[{"n":1,"satisfied":true,"why":"a"},'
    '{"n":2,"satisfied":false,"why":"b"}],'
    '"tone":{"appropriate":true,"clear":true,"why":"t"}}'
)


@pytest.fixture(autouse=True)
def _grouped_default(monkeypatch):
    monkeypatch.delenv("R388_JUDGE_GROUPED", raising=False)


def _recording_call(monkeypatch, reply):
    prompts: list[str] = []

    def fake_call(prompt, **_kwargs):
        prompts.append(prompt)
        return reply(prompt) if callable(reply) else reply

    monkeypatch.setattr(J, "_call", fake_call)
    return prompts


def test_grouped_is_the_default_and_costs_one_call_per_repeat(monkeypatch):
    prompts = _recording_call(monkeypatch, _BOTH)

    out = J.judge_row({"question": "Q", "answer": "A", "criteria": ["x", "y"]}, repeats=3)

    assert len(prompts) == 3, "grouped mode must make exactly one call per repetition"
    assert all("JUDGEMENT 1" in p and "JUDGEMENT 2" in p for p in prompts)
    assert out["criteria"] == [True, False]
    assert out["tone_ok"] is True
    assert out["_judge_runs"] == 3
    assert out["_tone_runs"] == 3
    assert out["_judge_errors"] == 0
    assert out["criterion_remarks"] == ["a", "b"]
    assert out["tone_remark"] == "t"


def test_split_mode_really_selects_two_calls_per_repeat(monkeypatch):
    """Two-sided: the escape hatch must not behave like the default."""
    monkeypatch.setenv("R388_JUDGE_GROUPED", "0")
    prompts = _recording_call(
        monkeypatch,
        lambda p: (
            '{"verdicts":[{"n":1,"satisfied":true,"why":"a"}]}'
            if "CRITERIA:" in p
            else '{"appropriate":true,"clear":true,"why":"t"}'
        ),
    )

    out = J.judge_row({"question": "Q", "answer": "A", "criteria": ["x"]}, repeats=3)

    assert len(prompts) == 6
    assert not any("JUDGEMENT 2" in p for p in prompts)
    assert out["criteria"] == [True]
    assert out["tone_ok"] is True


def test_grouped_dead_transport_is_reported_not_scored(monkeypatch):
    monkeypatch.setattr(J, "judge_grouped_once", lambda row: (None, None))

    out = J.judge_row({"id": "x", "criteria": ["a", "b", "c"]}, repeats=3)

    assert out["_judge_runs"] == 0, "a dead transport must be visible to the caller"
    assert out["_judge_errors"] == 3
    assert out["criteria"] == [False, False, False]
    assert out["tone_ok"] is False


def test_grouped_partial_failure_still_scores_from_the_live_runs(monkeypatch):
    seq = iter([(None, None), ([True, True], True), ([True, True], True)])
    monkeypatch.setattr(J, "judge_grouped_once", lambda row: next(seq))

    out = J.judge_row({"id": "x", "criteria": ["a", "b"]}, repeats=3)

    assert out["_judge_runs"] == 2
    assert out["_judge_errors"] == 1
    assert out["criteria"] == [True, True]
    assert out["tone_ok"] is True


@pytest.mark.parametrize("n_criteria", [0, 1, 5])
def test_grouped_dead_transport_shape_holds_for_any_criteria_count(monkeypatch, n_criteria):
    monkeypatch.setattr(J, "_call", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))

    out = J.judge_row({"id": "x", "criteria": ["c"] * n_criteria}, repeats=2)

    assert out["criteria"] == [False] * n_criteria
    assert out["_tone_runs"] == 0
    if n_criteria:
        assert out["_judge_runs"] == 0


def test_a_reply_without_the_tone_half_keeps_the_criteria_and_shows_no_tone_run(monkeypatch):
    """The grouped-only failure: a judge drifting off the contract drops a half.

    The criteria must still score, and ``_tone_runs == 0`` is what lets
    ``score_arm`` refuse to present tone=False as a measurement.
    """
    _recording_call(monkeypatch, '{"verdicts":[{"n":1,"satisfied":true,"why":"a"}]}')

    out = J.judge_row({"question": "Q", "answer": "A", "criteria": ["x"]}, repeats=3)

    assert out["criteria"] == [True]
    assert out["_judge_runs"] == 3
    assert out["_tone_runs"] == 0
    assert out["tone_ok"] is False


def test_fenced_reply_with_zero_based_n_and_top_level_tone_is_parsed(monkeypatch):
    _recording_call(
        monkeypatch,
        '```json\n{"verdicts":[{"n":0,"satisfied":true,"why":"a"},{"n":1,"satisfied":true,"why":"b"}],'
        '"appropriate":true,"clear":false,"why":"fragments"}\n```',
    )

    out = J.judge_row({"question": "Q", "answer": "A", "criteria": ["x", "y"]}, repeats=1)

    assert out["criteria"] == [True, True]
    assert out["tone_ok"] is False
    assert out["tone_remark"] == "fragments"


def test_a_row_without_criteria_costs_only_the_tone_call(monkeypatch):
    prompts = _recording_call(monkeypatch, '{"appropriate":true,"clear":true,"why":"t"}')

    out = J.judge_row({"question": "Q", "answer": "A", "criteria": []}, repeats=3)

    assert len(prompts) == 3
    assert not any("CRITERIA:" in p for p in prompts)
    assert out["criteria"] == []
    assert out["tone_ok"] is True


def test_judge_remarks_are_persisted_from_one_grouped_reply(monkeypatch):
    replies = iter(
        ['{"verdicts":[{"n":1,"satisfied":true,"why":"States the rule."}],'
         '"tone":{"appropriate":true,"clear":true,"why":"Professional and clear."}}']
    )
    monkeypatch.setattr(J, "_call", lambda *_args, **_kwargs: next(replies))

    out = J.judge_row({"question": "Q", "answer": "A", "criteria": ["rule"]}, repeats=1)

    assert out["criterion_remarks"] == ["States the rule."]
    assert out["tone_remark"] == "Professional and clear."


def test_identity_separates_grouped_from_split_and_keeps_the_legacy_bytes(monkeypatch):
    from evals.official.score_arm import _key

    monkeypatch.setenv("R388_JUDGE_PROVIDER", "bedrock")
    monkeypatch.setattr(J, "MODEL", "qwen.qwen3-235b-a22b-2507-v1:0")
    monkeypatch.setattr(J, "TEMPERATURE", 0.1)
    monkeypatch.setattr(J, "REPEATS", 3)

    monkeypatch.setenv("R388_JUDGE_GROUPED", "0")
    split = J.judge_identity()
    monkeypatch.setenv("R388_JUDGE_GROUPED", "1")
    grouped = J.judge_identity()

    # The identity the R405 Qwen cache was written under, byte for byte.
    assert split == "bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:r=3"
    assert grouped == "bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3"
    # score_arm rebuilds the repeat suffix with rsplit(":r=", 1); the segment must survive it.
    assert grouped.rsplit(":r=", 1)[0] + ":r=3" == grouped
    assert _key("q1", "same answer", split) != _key("q1", "same answer", grouped)


@pytest.mark.parametrize(
    ("value", "grouped"),
    [("", True), ("1", True), ("yes", True), ("anything", True),
     ("0", False), ("false", False), ("No", False), ("OFF", False)],
)
def test_the_gate_is_deny_list(monkeypatch, value, grouped):
    monkeypatch.setenv("R388_JUDGE_GROUPED", value)
    assert J._grouped_enabled() is grouped


def test_configure_judge_selects_split_and_none_leaves_the_environment(monkeypatch):
    monkeypatch.setenv("R388_JUDGE_GROUPED", "0")
    J.configure_judge(grouped=None)
    assert J._grouped_enabled() is False

    J.configure_judge(grouped=True)
    assert J._grouped_enabled() is True

    J.configure_judge(grouped=False)
    assert J._grouped_enabled() is False
