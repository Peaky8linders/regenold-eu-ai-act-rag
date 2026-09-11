"""R409 — eval-instrument accounting the R407 hard-mode scorecard got wrong.

* Resp. Speed was scored on turn 1 PLUS the pushback turn, and on a 13 s Cohere
  pacing sleep that runs inside the in-process request.
* A judge verdict that lost a repetition was cached as if complete.
"""
from evals.official import score_arm as sa
from evals.regenold import run_official_batch as rob


def test_hard_checkpoint_scores_the_graded_turn_not_the_sum():
    row = {
        "latency_ms": 30000,
        "turn1_latency_ms": 14000,
        "pushback_latency_ms": 16000,
        "turn1_answer": "Yes.",
        "pushback_answer": "Yes.",
    }
    assert sa._graded_latency_ms(row) == 16000
    # A pushback that failed still took that time: never score it at turn-1 speed.
    assert sa._graded_latency_ms({**row, "pushback_answer": ""}) == 16000
    # No turn-1 answer means no pushback was sent.
    assert sa._graded_latency_ms({**row, "turn1_answer": "", "pushback_latency_ms": 0}) == 14000
    # Checkpoints written before the per-turn fields keep the old reading.
    assert sa._graded_latency_ms({"latency_ms": 30000}) == 30000


def test_pacing_sleep_is_not_response_latency(monkeypatch):
    monkeypatch.setattr(rob, "_PACING_SLEPT_S", [5.0])
    result = ({"answer": "x"}, 20000.0, 200, None, 1, None)
    rob._PACING_SLEPT_S[0] += 12.5  # the pacer slept inside this request
    assert rob._net_of_pacing(result, 5.0)[1] == 7500.0
    # No sleep since the snapshot: the result is untouched.
    assert rob._net_of_pacing(result, rob._PACING_SLEPT_S[0]) is result


def test_cached_verdict_must_match_the_criteria_and_grounding_it_judged():
    row = {
        "criteria_text": ["Yes", "Article 26(4) deployer duty"],
        "expected_refs": ["Article 26.4"],
        "_revised": None,
    }
    fresh = {"_basis_sha": sa._judge_basis_sha(row)}
    assert sa._criteria_match(fresh, row)
    # Same criteria COUNT, different text: the pre-R409 key replayed this.
    assert not sa._criteria_match(fresh, {**row, "criteria_text": ["Yes", "Article 10(3) provider duty"]})
    # Refkey-only correction: same criteria, but the judge is grounded on other text.
    assert not sa._criteria_match(fresh, {**row, "expected_refs": ["Article 24.1"]})
    # Lines without a basis hash: trusted only while the gold row is unrevised.
    assert sa._criteria_match({}, row)
    assert not sa._criteria_match({"_criteria_sha": "abc"}, {**row, "_revised": "R409"})


def test_only_complete_verdicts_are_cacheable():
    assert sa._verdict_complete({"_judge_runs": 3, "_tone_runs_raw": [True, True, False]}, 3)
    assert not sa._verdict_complete({"_judge_runs": 2, "_tone_runs_raw": [True, True, True]}, 3)
    assert not sa._verdict_complete({"_judge_runs": 3, "_tone_runs_raw": [True, None, True]}, 3)
    assert not sa._verdict_complete({"_judge_runs": 3, "_tone_runs": 0}, 3)
    # Cache lines that predate tone accounting stay usable.
    assert sa._verdict_complete({"_judge_runs": 3}, 3)
