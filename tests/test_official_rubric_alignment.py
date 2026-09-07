"""R391 — pin the local rubric against the OFFICIAL report's own definitions.

Source of truth: ``report_antifragile_ai.pdf`` (2026-08-25), "Evaluation
methodology" and Tables 1-3. Every constant below is transcribed verbatim from
that document; every assertion restates one sentence of Table 1.

Why this file exists: the eight axes and their geometric mean are the
instrument every lever in this repo is gated on, and until now NOTHING pinned
them. A silent edit to :mod:`evals.official.rubric` would have moved every
historical score with no test failing. The strongest available check is that
the rubric reproduces the report's OWN printed Overall for all six published
rows — two baselines and us, across both modes — from the report's own
per-axis numbers.
"""
from __future__ import annotations

import pytest

from evals.official.rubric import (
    AXIS_ORDER,
    answer_conciseness,
    answer_correctness_loose,
    answer_correctness_strict,
    overall,
    reference_conciseness,
    reference_correctness_loose,
    reference_correctness_strict,
    regulatory_tone,
    response_speed,
    score_rows,
)

# Table 2 (easy) and Table 3 (hard), transcribed verbatim.
# order: Ans Cor L, Ans Cor S, Ans Conc, Ref L, Ref S, Ref Conc, Tone, Speed
PRINTED: dict[str, tuple[float, list[float]]] = {
    "easy/2026-frontier": (80.9, [94.4, 89.1, 67.9, 96.1, 78.5, 51.9, 100.0, 81.8]),
    "easy/2025-baseline": (70.1, [83.8, 70.9, 51.1, 79.9, 52.0, 48.7, 99.1, 95.3]),
    "easy/antifragile": (75.1, [89.7, 81.2, 51.9, 89.4, 68.3, 50.4, 99.1, 87.6]),
    "hard/2026-frontier": (81.7, [92.0, 84.8, 71.8, 94.6, 74.1, 58.5, 100.0, 86.7]),
    "hard/2025-baseline": (74.8, [87.6, 76.7, 58.8, 82.7, 55.4, 56.8, 99.7, 95.9]),
    "hard/antifragile": (73.4, [89.9, 80.0, 45.2, 89.5, 70.7, 49.8, 96.1, 85.7]),
}


# -- the aggregate -----------------------------------------------------------


@pytest.mark.parametrize("row", sorted(PRINTED))
def test_geometric_mean_reproduces_every_printed_overall(row):
    """"An aggregated score is also reported by taking the geometric mean
    across all metrics." — report, Evaluation methodology.

    Rounding in the printed table is to 0.1 pp, so 0.06 pp is the tightest
    band the published figures can support.
    """
    printed, axes = PRINTED[row]
    assert abs(overall(axes) - printed) < 0.06, (row, overall(axes), printed)


def test_a_single_zero_axis_zeroes_the_score():
    """"penalises low scores in any single metric" — the point of a GM."""
    assert overall([100.0] * 7 + [0.0]) == 0.0


def test_axis_order_is_the_report_table_order():
    assert AXIS_ORDER == (
        "ans_correctness_loose",
        "ans_correctness_strict",
        "ans_conciseness",
        "ref_correctness_loose",
        "ref_correctness_strict",
        "ref_conciseness",
        "regulatory_tone",
        "resp_speed",
    )


# -- Table 1, one test per printed Description -------------------------------


def test_ans_loose_is_percentage_of_individual_criteria():
    """"Percentage of individual correctness criteria satisfied by the
    candidate answers." — a MICRO average: a 5-criterion question outweighs a
    2-criterion one.
    """
    # 5 satisfied of 7 individual criteria across two questions.
    assert answer_correctness_loose([[True] * 4 + [False], [True, False]]) == 5 / 7


def test_ans_strict_is_percentage_of_questions_with_ALL_criteria():
    """"Percentage of questions for which ALL required correctness criteria
    are satisfied by the candidate answer."
    """
    assert answer_correctness_strict([[True, True], [True, False], [True]]) == 2 / 3


def test_a_question_with_no_criteria_is_not_a_free_pass():
    assert answer_correctness_strict([[], [True]]) == 1.0


def test_ans_conciseness_is_inverted_verbosity_vs_the_reference_answer():
    """"Inverted measure of answer verbosity relative to the reference
    answers."  Recovered as min(1, len(reference)/len(candidate)).
    """
    assert answer_conciseness("x" * 1000, "y" * 500) == pytest.approx(0.5)


def test_ans_conciseness_is_one_sided():
    """An answer SHORTER than the reference is not penalised here; omission is
    scored on the two correctness axes.
    """
    assert answer_conciseness("x" * 100, "y" * 500) == 1.0


def test_ans_conciseness_needs_a_reference_answer():
    assert answer_conciseness("anything", "") is None


def test_ref_loose_is_scored_at_article_and_annex_level():
    """"Percentage of expected references met at the level of Article and
    Annex numbers (e.g. Article 6)."  A MORE precise prediction covers the
    head — which is exactly what the R386 grain deepener relies on.
    """
    assert reference_correctness_loose(["Article 6.2"], ["Article 6"]) == 1.0
    assert reference_correctness_loose(["Article 6"], ["Article 6"]) == 1.0
    assert reference_correctness_loose(["Article 7"], ["Article 6"]) == 0.0


def test_ref_strict_includes_subpoints():
    """"Like the above, but including subpoints within the Articles/Annexes
    (e.g. Article 6.1)."  The bare head does NOT satisfy a sub-point key —
    this is the axis the grain deepener targets.
    """
    assert reference_correctness_strict(["Article 6.1"], ["Article 6.1"]) == 1.0
    assert reference_correctness_strict(["Article 6"], ["Article 6.1"]) == 0.0


def test_ref_conciseness_is_excess_relative_to_expected():
    """"Excess references relative to expected references."  A pure COUNT
    ratio min(1, |expected|/|provided|): WHICH provisions are cited does not
    move this axis, only HOW MANY.
    """
    four = ["Article 6", "Article 9", "Article 10", "Annex III"]
    assert reference_conciseness(four, ["Article 6"]) == pytest.approx(0.25)
    # same count, completely different provisions -> identical score
    other = ["Article 50", "Article 99", "Annex IV", "Annex VIII"]
    assert reference_conciseness(other, ["Article 6"]) == pytest.approx(0.25)


def test_ref_conciseness_is_one_sided():
    """Citing FEWER references than the key still scores 1.0; under-citing is
    paid for on the correctness axes.
    """
    assert reference_conciseness(["Article 6"], ["Article 6", "Annex III"]) == 1.0


def test_questions_without_expected_references_are_excluded():
    """"Questions without annotated expected references are excluded from the
    reference metrics."
    """
    assert reference_conciseness(["A", "B", "C"], []) is None


def test_regulatory_tone_is_a_fraction_of_responses():
    """"Fraction of responses judged both appropriate and clear w.r.t. few
    shot examples."
    """
    assert regulatory_tone([True, True, False, True]) == 0.75


def test_resp_speed_is_100_minus_latency_seconds():
    """"Mean per-response score: 100 minus latency in seconds, clipped at
    zero."  Returned on the 0-1 scale; score_rows multiplies by 100 once.
    """
    assert response_speed([10.0]) == pytest.approx(0.90)
    assert response_speed([0.0]) == pytest.approx(1.0)


def test_resp_speed_is_clipped_at_zero():
    """A 250-second response scores 0, not -150."""
    assert response_speed([250.0]) == 0.0
    assert response_speed([10.0, 250.0]) == pytest.approx(0.45)


# -- end to end --------------------------------------------------------------


def test_score_rows_excludes_unannotated_rows_from_ref_axes_only():
    """The unannotated row still counts for answer, tone and speed."""
    rows = [
        {
            "criteria": [True, True],
            "answer": "a" * 600,
            "reference_answer": "r" * 600,
            "references": ["Article 6.1"],
            "expected_refs": ["Article 6.1"],
            "tone": True,
            "latency_s": 5.0,
        },
        {
            "criteria": [True, False],
            "answer": "a" * 1200,
            "reference_answer": "r" * 600,
            "references": ["Article 9", "Article 10", "Article 11"],
            "expected_refs": [],  # not annotated
            "tone": True,
            "latency_s": 5.0,
        },
    ]
    got = score_rows(rows)
    assert got["n"] == 2
    assert got["n_ref_scored"] == 1, "only the annotated row feeds the ref axes"
    # the annotated row is a perfect citation, so all three ref axes are 100
    assert got["ref_correctness_loose"] == pytest.approx(100.0)
    assert got["ref_correctness_strict"] == pytest.approx(100.0)
    assert got["ref_conciseness"] == pytest.approx(100.0)
    # both rows feed the answer axes: 3 of 4 criteria, 1 of 2 all-pass rows
    assert got["ans_correctness_loose"] == pytest.approx(75.0)
    assert got["ans_correctness_strict"] == pytest.approx(50.0)
    # speed: both at 5 s -> 95
    assert got["resp_speed"] == pytest.approx(95.0)
