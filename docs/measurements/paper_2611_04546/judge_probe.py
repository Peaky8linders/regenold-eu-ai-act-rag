"""Offline synthetic probes for the November 2026 paper/judge audit.

No model calls, official questions, or production requests. Run from repo root:
    python docs/measurements/paper_2611_04546/judge_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from evals.harness.ab_judge import (  # noqa: E402
    ArmAnswer,
    _judge_one_ok,
    _pairwise_verdict_detail,
)
from evals.official.judge import _majority  # noqa: E402
from evals.official.paired_ab import _row_axis  # noqa: E402
from evals.official.rubric import (  # noqa: E402
    answer_correctness_loose,
    answer_correctness_strict,
)
from evals.official.score_arm import _judge_basis_sha  # noqa: E402


def run() -> dict:
    # One one-criterion item improves, one five-criterion item regresses twice.
    baseline = [[False], [True] * 5]
    branch = [[True], [False, False, True, True, True]]
    delta_micro = 100 * (
        answer_correctness_loose(branch) - answer_correctness_loose(baseline)
    )
    delta_paired = sum(
        _row_axis({"criteria": b}, "ans_correctness_loose")
        - _row_axis({"criteria": a}, "ans_correctness_loose")
        for a, b in zip(baseline, branch, strict=True)
    ) / len(baseline)

    a = ArmAnswer("Candidate A.", [], 0, 200)
    b = ArmAnswer("Candidate B.", [], 0, 200)
    # Caller is a local function returning a dictionary: it cannot reach a model.
    def invalid_caller(_prompt):
        return {"winner": "banana"}

    invalid_one = _judge_one_ok(invalid_caller, "synthetic prompt")
    invalid_pair = _pairwise_verdict_detail(
        {"question": "Synthetic question"}, "tone", a, b, invalid_caller, {}
    )

    repetitions = [[True, False], [True, True], [False, True]]
    majority = _majority(repetitions, 2)
    # Each repetition judges the same single two-criterion item.
    mean_loose = sum(answer_correctness_loose([r]) for r in repetitions) / 3
    mean_strict = sum(answer_correctness_strict([r]) for r in repetitions) / 3

    cache_row = {
        "question": "Original question",
        "criteria_text": ["Synthetic criterion"],
        "expected_refs": ["Article 6.2"],
    }
    changed_question = {**cache_row, "question": "A changed question"}
    return {
        "scope": "synthetic offline examples; not an effectiveness evaluation",
        "criterion_weighting_sign_reversal": {
            "baseline_criteria": baseline,
            "branch_criteria": branch,
            "paper_micro_delta_pp": delta_micro,
            "local_paired_macro_delta_pp": delta_paired,
        },
        "malformed_winner": {
            "payload": {"winner": "banana"},
            "one_call_verdict_and_valid": list(invalid_one),
            "pair_verdict_and_swap_agreement": list(invalid_pair),
        },
        "majority_vs_mean_repetitions": {
            "runs": repetitions,
            "majority_criteria": majority,
            "majority_loose": answer_correctness_loose([majority]),
            "majority_strict": answer_correctness_strict([majority]),
            "mean_run_loose": mean_loose,
            "mean_run_strict": mean_strict,
        },
        "cache_basis_omits_question": {
            "same_basis_after_question_change": (
                _judge_basis_sha(cache_row) == _judge_basis_sha(changed_question)
            ),
        },
    }


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload, indent=2))
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
