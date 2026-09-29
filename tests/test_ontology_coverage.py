from __future__ import annotations

from pathlib import Path

import pytest

from evals.official.ontology_coverage import (
    CoordinateResolution,
    QuestionCoverageStatus,
    _lettered_annex_sections,
    build_coverage_report,
    load_official_gold,
    resolve_coordinate,
)


def _row(question_id: str, refs: list[str]) -> dict[str, object]:
    return {
        "id": question_id,
        "question": f"Question {question_id}?",
        "expected_refs": refs,
        "criteria": ["A supported answer criterion"],
    }


@pytest.mark.parametrize(
    "reference, expected",
    [
        ("Article 13.3.b.iv", CoordinateResolution.EXACT),
        ("Article 13.3.z", CoordinateResolution.INVALID),
        ("Annex VIII.a", CoordinateResolution.EXACT),
        ("Annex VIII.b.1", CoordinateResolution.EXACT),
        ("Annex VIII.b.99", CoordinateResolution.INVALID),
        ("Annex XI.1", CoordinateResolution.PARENT_ONLY),
        ("Annex XI.3", CoordinateResolution.EXACT),
        ("Article 3.1.a", CoordinateResolution.PARENT_ONLY),
        ("Annex VIII.99", CoordinateResolution.INVALID),
        ("Article 999.1", CoordinateResolution.INVALID),
        ("not a citation", CoordinateResolution.INVALID),
    ],
)
def test_coordinate_resolution_distinguishes_exact_parent_only_and_invalid(
    reference: str, expected: CoordinateResolution
) -> None:
    assert resolve_coordinate(reference).resolution is expected


def test_lettered_annex_sections_are_derived_from_the_section_parser() -> None:
    sections = _lettered_annex_sections()
    assert "annex viii.a" in sections
    assert 1 in sections["annex viii.a"]
    assert resolve_coordinate("Annex VIII.b.1").resolution is CoordinateResolution.EXACT
    assert resolve_coordinate("Annex VIII.b.99").resolution is CoordinateResolution.INVALID
    assert resolve_coordinate("Annex VIII.a").resolution is CoordinateResolution.EXACT


def test_cq_report_links_question_criteria_to_exact_evidence_and_exposes_gaps() -> None:
    report = build_coverage_report(
        [
            _row("exact", ["Article 13.3.b.iv"]),
            _row("parent", ["Article 3.1.a"]),
            _row("bad", ["Article 13.9"]),
            _row("no-ref", []),
        ]
    )

    assert report.question_count == 4
    assert report.status_counts == {
        "supported": 1,
        "partial": 1,
        "unresolved": 1,
        "unannotated": 1,
    }
    assert report.evidence_counts == {"exact": 1, "parent_only": 1, "invalid": 1}
    assert report.questions[0].criteria == ("A supported answer criterion",)
    assert report.questions[0].evidence[0].canonical_reference == "Article 13.3.b.iv"
    assert report.as_dict()["untracked_dimensions"]


def test_duplicate_question_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_coverage_report([_row("same", []), _row("same", [])])


def test_official_gold_corpus_is_represented_without_relabeling_unannotated_rows() -> None:
    gold_path = Path(__file__).parents[1] / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"
    report = build_coverage_report(load_official_gold(gold_path))

    assert report.question_count == 110
    assert report.status_counts[QuestionCoverageStatus.UNANNOTATED.value] > 0
    assert report.status_counts[QuestionCoverageStatus.SUPPORTED.value] > 0
    assert report.status_counts[QuestionCoverageStatus.UNRESOLVED.value] == 0, [
        (question.question_id, question.evidence)
        for question in report.questions
        if question.status is QuestionCoverageStatus.UNRESOLVED
    ]
    # rg_037's coarse section-level key is a known Section A coordinate, not a
    # paragraph or point reference inferred from its parent's existence.
    # The rubric's Annex I alias is also checked against its adopted-text point.
    section_alias = next(question for question in report.questions if question.question_id == "rg_004")
    assert section_alias.evidence[1].canonical_reference == "Annex I.11"
    assert section_alias.evidence[1].resolution is CoordinateResolution.EXACT
    row = next(question for question in report.questions if question.question_id == "rg_037")
    assert row.evidence[0].resolution is CoordinateResolution.EXACT
