"""R138 — unit tests for the live pairwise-judge A/B harness.

Covers the pure / mockable logic (probe-set loading, pairwise prompt
rendering, position-swap verdict aggregation, the sign test, deterministic
scoring). The live-wrapper path is exercised by the round's live demonstration,
not in unit tests.
"""
from __future__ import annotations

import pytest

from evals.harness import ab_judge, pairwise_prompts
from evals.harness.ab_judge import AxisResult, ArmAnswer, _sign_test_two_sided
from evals.harness.probe_set import ProbeRow, category_counts, load_probe_set


# ── probe_set ──────────────────────────────────────────────────────────────


def test_load_probe_set_nonempty_unique_ids():
    rows = load_probe_set()
    assert len(rows) >= 90, f"expected the consolidated ~108-row corpus, got {len(rows)}"
    ids = [r.id for r in rows]
    assert len(ids) == len(set(ids)), "probe ids must be globally unique"
    # Source prefixes keep cross-source ids distinct.
    assert all(":" in i for i in ids)


def test_probe_set_has_both_shapes_and_gold():
    rows = load_probe_set()
    assert any(r.is_multiturn for r in rows)
    assert any(not r.is_multiturn for r in rows)
    # Every row carries keyword-gold (the judge + deterministic tier need it).
    assert all(r.expected_refs or r.expected_keywords for r in rows)


def test_probe_set_filters():
    only_mt = load_probe_set(multiturn=True)
    assert only_mt and all(r.is_multiturn for r in only_mt)
    only_st = load_probe_set(multiturn=False)
    assert only_st and all(not r.is_multiturn for r in only_st)
    tricky = load_probe_set(sources=("tricky_v2",))
    assert tricky and all(r.source == "tricky_v2" for r in tricky)
    assert len(load_probe_set(limit=5)) == 5


def test_live_question_is_final_user_turn():
    mt = ProbeRow(
        id="x:1", source="mt_v2", category="role_flip", is_multiturn=True,
        messages=(
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ack"},
            {"role": "user", "content": "FINAL"},
        ),
        expected_refs=("Article 25",), expected_keywords=("provider",),
    )
    assert mt.live_question == "FINAL"


def test_category_counts():
    rows = load_probe_set(sources=("tricky_v2",))
    counts = category_counts(rows)
    assert sum(counts.values()) == len(rows)


# ── pairwise prompts ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("axis", pairwise_prompts.AXES)
def test_pairwise_prompt_contains_both_answers_and_json_tail(axis):
    row = {"question": "What must a deployer do?", "expected_keywords": ["Article 26"],
           "expected_refs": ["Article 26"]}
    p = pairwise_prompts.render(
        axis, row, answer_a="ANSWER_ALPHA", refs_a=["Article 26"],
        answer_b="ANSWER_BETA", refs_b=["Article 13"],
        article_summaries={"Article 26": "Deployer obligations."},
    )
    assert "ANSWER_ALPHA" in p and "ANSWER_BETA" in p
    assert '"winner"' in p and ("A" in p and "B" in p)


def test_unknown_axis_raises():
    with pytest.raises(ValueError):
        pairwise_prompts.render("bogus", {}, answer_a="", refs_a=[], answer_b="", refs_b=[])


# ── position-swap verdict ────────────────────────────────────────────────────


def _mock_caller_factory(monkeypatch, order1_winner: str, order2_winner: str):
    """Patch _call_judge_with_retry to return order1 then order2 winners."""
    seq = iter([order1_winner, order2_winner])

    def fake(caller, prompt):
        return ({"winner": next(seq)}, 1, [])

    monkeypatch.setattr("evals.judge.runner._call_judge_with_retry", fake)


def _verdict(a_ans="A-ans", b_ans="B-ans"):
    a = ArmAnswer(answer=a_ans, refs=["Article 26"], latency_ms=1.0, http_status=200)
    b = ArmAnswer(answer=b_ans, refs=["Article 13"], latency_ms=1.0, http_status=200)
    return ab_judge._pairwise_verdict(
        {"question": "q", "expected_keywords": [], "expected_refs": []},
        "correctness", a, b, caller=object(), summaries={},
    )


def test_both_orders_agree_branch_wins(monkeypatch):
    # order1: prompt-B (branch) wins → "B". order2 (swapped): branch is in the
    # prompt's A slot → "A". Both agree → branch ("B").
    _mock_caller_factory(monkeypatch, "B", "A")
    assert _verdict() == "B"


def test_both_orders_agree_baseline_wins(monkeypatch):
    _mock_caller_factory(monkeypatch, "A", "B")
    assert _verdict() == "A"


def test_position_flip_is_tie(monkeypatch):
    # Both orders pick the FIRST-shown answer (pure position bias) → tie.
    _mock_caller_factory(monkeypatch, "A", "A")
    assert _verdict() == "tie"


def test_judge_error_is_tie(monkeypatch):
    def fake(caller, prompt):
        return ({"judge_error": "timeout"}, 2, ["timeout"])
    monkeypatch.setattr("evals.judge.runner._call_judge_with_retry", fake)
    assert _verdict() == "tie"


# ── sign test + AxisResult ───────────────────────────────────────────────────


def test_sign_test_decisive_branch():
    assert _sign_test_two_sided(wins_b=10, wins_a=0) < 0.05


def test_sign_test_even_is_one():
    assert _sign_test_two_sided(wins_b=5, wins_a=5) == 1.0


def test_sign_test_no_pairs_is_one():
    assert _sign_test_two_sided(0, 0) == 1.0


def test_axis_result_verdicts():
    r = AxisResult(axis="refs", wins_b=12, wins_a=2, ties=4)
    assert r.win_rate_b() == round(12 / 14, 4)
    assert r.p_value() < 0.05
    assert r.verdict() == "BRANCH wins (sig)"
    even = AxisResult(axis="tone", wins_b=0, wins_a=0, ties=20)
    assert even.win_rate_b() is None
    assert even.verdict() == "no-decisive-pairs"


# ── deterministic tier ───────────────────────────────────────────────────────


def test_deterministic_scores_shape():
    rows = [
        ProbeRow(id="t:1", source="t", category="c", is_multiturn=False,
                 messages=({"role": "user", "content": "q"},),
                 expected_refs=("Article 26",), expected_keywords=("deployer",)),
    ]
    arm = {"t:1": ArmAnswer(answer="A deployer must follow Article 26.",
                            refs=["Article 26"], latency_ms=1.0, http_status=200)}
    sc = ab_judge._deterministic_scores(rows, arm)
    assert sc["ref_loose"] == 1.0  # gold Article 26 cited
    assert set(sc) >= {"ref_loose", "ref_strict", "keyword_recall", "n"}
