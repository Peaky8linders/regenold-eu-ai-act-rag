"""R414 — a judge leg that answered nothing must WITHHOLD the judged axes.

MEASURED (R413). The wrapper's Claude-Max OAuth expired mid-run, so 39 of 39
rows returned NO live judge run. ``score_arm`` printed

    JUDGE TRANSPORT DEGRADED: 39/39 rows (100%) returned NO live judge run and
    were scored all-False.

and then printed the axis table anyway (`ans_correctness_loose` 3.76 %,
`regulatory_tone` 2.5 %), which the paired gate parsed into a delta table.
Detection without REFUSAL is what let a dead judge read as a result: the R412
lesson (a void run and a real null have the same shape) applied to the judge leg
rather than the transport leg.

These tests pin the refusal decision itself. The gate's own exit-code handling is
exercised by the live run that produced `docs/measurements/r413` §7.
"""

from __future__ import annotations

import pytest

from evals.official.score_arm import JUDGE_VOID_FRAC, judge_void_reason


def _live() -> dict:
    return {"_judge_runs": 3, "_tone_runs": 3}


class TestJudgeVoidReason:
    def test_all_rows_dead_is_void(self) -> None:
        reason = judge_void_reason([{"_judge_runs": 0}] * 39, 3)
        assert "39/39" in reason
        assert "NO live judge run" in reason

    def test_a_healthy_leg_publishes(self) -> None:
        assert judge_void_reason([_live()] * 40, 3) == ""

    def test_missing_tone_is_void_even_when_criteria_parsed(self) -> None:
        # The R408 shape: grouped judging returns criteria but drops the tone
        # object, so tone reads as a quiet all-False.
        rows = [{"_judge_runs": 3, "_tone_runs": 0}] * 40
        reason = judge_void_reason(rows, 3)
        assert "NO live tone run" in reason

    def test_transient_failures_stay_below_the_bar(self) -> None:
        # A couple of rows lost to a retry is not a broken instrument; those rows
        # are simply not cached (``_verdict_complete``).
        rows = [{"_judge_runs": 0}, *([_live()] * 39)]
        assert judge_void_reason(rows, 3) == ""

    def test_the_bar_is_a_fraction_not_a_count(self) -> None:
        assert JUDGE_VOID_FRAC == pytest.approx(0.2)
        # 9 of 10 dead (90 %) is void; 2 of 10 (20 %) is exactly at the bar and
        # still publishes (the check is strict >).
        assert judge_void_reason([{"_judge_runs": 0}] * 9 + [_live()], 3) != ""
        assert judge_void_reason([{"_judge_runs": 0}] * 2 + [_live()] * 8, 3) == ""

    def test_no_judged_rows_is_not_a_void_run(self) -> None:
        # A fully cached arm judges nothing; that is a cache hit, not a failure.
        assert judge_void_reason([], 3) == ""

    def test_missing_run_counter_is_treated_as_dead(self) -> None:
        # ``judge_row`` omits ``_judge_runs`` only when it never ran.
        assert judge_void_reason([{}] * 10, 3) != ""
