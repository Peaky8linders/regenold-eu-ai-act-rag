"""R423 — the gate must publish all EIGHT axes, on the rows it actually compares.

The gate's headline axes are the ones the lever aims at (answer correctness,
answer length, reference strictness). The official aggregate is a GEOMETRIC mean
though, so a lever that shortens answers while it costs reference conciseness or
regulatory tone is not a win — and reading only the aimed-at axes cannot tell.
`need_gate.official_axes` recomputes the official instrument on exactly the rows
that passed the comparability filter, in both arms, per generation.

These tests pin the properties the verdict depends on:

* every axis of the official rubric is present, including `overall`;
* the per-axis reduction is the MEDIAN over generations, so one odd generation
  cannot move the arm;
* an axis that is undefined on the subset (no annotated references anywhere after
  the filter) reports ``null`` rather than a bare ``NaN``, which is not valid
  JSON and which a reader would silently compare as a number.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AXES = (
    "ans_correctness_loose",
    "ans_correctness_strict",
    "ans_conciseness",
    "ref_correctness_loose",
    "ref_correctness_strict",
    "ref_conciseness",
    "regulatory_tone",
    "resp_speed",
)


def _gate():
    path = REPO / "docs" / "measurements" / "r423" / "need_gate.py"
    spec = importlib.util.spec_from_file_location("need_gate_r423", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(
    *,
    criteria: list[bool],
    answer: str,
    refs: list[str],
    expected: list[str],
    latency_s: float = 1.0,
) -> dict:
    return {
        "id": "x",
        "criteria": criteria,
        "criteria_text": ["a", "b"][: len(criteria)],
        "answer": answer,
        "refs": refs,
        "expected_refs": expected,
        "tone_ok": True,
        "latency_s": latency_s,
    }


def _artifacts(a_rows: dict[str, dict], b_rows: dict[str, dict], samples: int = 3):
    return {
        arm: {s: dict(rows) for s in range(samples)}
        for arm, rows in (("A", a_rows), ("B", b_rows))
    }


def test_the_board_covers_every_official_axis_and_is_a_median_over_generations() -> None:
    gate = _gate()
    a_rows = {
        "rg_001": _row(criteria=[True, False], answer="a" * 400, refs=["Article 6"],
                       expected=["Article 6"]),
    }
    b_rows = {
        "rg_001": _row(criteria=[True, True], answer="b" * 200, refs=["Article 6"],
                       expected=["Article 6"]),
    }
    artifacts = _artifacts(a_rows, b_rows)
    # Generation 3 of arm A is an outlier on BOTH axes: it drops a criterion and
    # loses the expected reference. The median must not follow it.
    artifacts["A"][2]["rg_001"] = _row(
        criteria=[False, False], answer="a" * 5000, refs=["Article 9"], expected=["Article 6"]
    )

    board = gate.official_axes(artifacts, ["rg_001"], {"rg_001": "reference text"})
    assert board["subset_n"] == 1
    assert tuple(board["axes"]) == (*AXES, "overall"), board["axes"]

    loose = board["axes"]["ans_correctness_loose"]
    assert loose["A"] == 50.0, "median of (50, 50, 0) is 50"
    assert loose["B"] == 100.0
    assert loose["delta_pp"] == 50.0
    assert loose["A_by_sample"] == [50.0, 50.0, 0.0]

    # Arm B answers half as long against the same gold: the conciseness axis has
    # to move, and it is the axis the lever was aimed at.
    assert board["axes"]["ans_conciseness"]["B"] > board["axes"]["ans_conciseness"]["A"]
    # Both arms cite the one expected reference in 2 of 3 generations, so the
    # reference axes are ties — the outlier generation is dropped by the median
    # rather than averaged in.
    assert board["axes"]["ref_correctness_strict"]["A"] == 100.0
    assert board["axes"]["ref_correctness_strict"]["delta_pp"] == 0.0
    assert board["axes"]["ref_conciseness"]["delta_pp"] == 0.0


def test_a_subset_with_no_annotated_references_reports_the_instruments_own_zero() -> None:
    """Pin the excluded-rows rule rather than inventing a friendlier one.

    The report's rule is "questions without annotated expected references are
    excluded from the reference metrics". The shipped instrument implements
    exclusion by returning ``None`` per row and filtering the ``None``s, so a
    subset in which NOTHING is annotated yields ``_mean([])`` = 0.0 — not
    ``NaN``, and not a silent pass. The gate must reproduce that, because the
    official aggregate reads it, and a reader comparing 0.0 with 0.0 (delta 0)
    is reading the same thing the benchmark would.
    """
    gate = _gate()
    a_rows = {"rg_001": _row(criteria=[True], answer="a" * 100, refs=[], expected=[])}
    b_rows = {"rg_001": _row(criteria=[True], answer="b" * 100, refs=[], expected=[])}
    board = gate.official_axes(_artifacts(a_rows, b_rows), ["rg_001"], {})

    for axis in (
        "ref_correctness_loose",
        "ref_correctness_strict",
        "ref_conciseness",
    ):
        assert board["axes"][axis]["A"] == 0.0, axis
        assert board["axes"][axis]["delta_pp"] == 0.0, axis
    # Whatever the instrument reports must survive a JSON round-trip unaltered.
    assert json.loads(json.dumps(board)) == board


def _report_module():
    path = REPO / "docs" / "measurements" / "r423" / "build_need_report.py"
    spec = importlib.util.spec_from_file_location("build_need_report_r423", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_verdict_carries_its_scope_from_the_measured_payloads() -> None:
    """A delta published without its dispatch scope is the R422 failure mode.

    R423.3 — the first version of this section claimed both arms "dispatched the
    stripped persona" as a blanket statement. That is FALSE: ``_run_hard`` keeps a
    rolling conversation that starts empty, so the first two rows of a run read
    ``history_turn_count`` 0 and 1 and receive the FULL system prompt. The scope
    must state the measured distribution, name that artifact, and carry the bound
    that proves it does not manufacture the result — and it has to appear BEFORE
    the eight-axis board, because it qualifies every number on it.
    """
    # The committed REPORT carries the section, so this half holds in a clean clone
    # where the gitignored sidecar is absent — it never silently skips.
    text = (REPO / "docs" / "reports" / "r423-need-proportional-gate.md").read_text(
        encoding="utf-8"
    )
    scope_heading = "## Scope of this verdict"
    axes_heading = "## All eight official axes, per arm"
    assert scope_heading in text, "the verdict must state its scope"
    assert axes_heading in text
    assert text.index(scope_heading) < text.index(axes_heading), (
        "the scope must precede the board it qualifies"
    )
    assert "dispatched the persona" in text, (
        "the scope must report the dispatched persona share, not narrate it"
    )
    # The falsified blanket claim must not come back.
    assert "so both dispatched the stripped persona" not in text, (
        "the scope must not blanket-claim the persona: the leading rows of a "
        "hard run receive the full system prompt"
    )
    # The artifact, its cause, and the bound on it all have to be on the record.
    assert "rolling history starts empty" in text, (
        "the scope must name WHY a hard row can read as single-turn"
    )
    assert "+13.42 pp" in text and "+14.50 pp" in text, (
        "the scope must carry the leave-one-out bound on the one full-prompt "
        "asymmetry between the arms"
    )
    # R423.3 — the scope qualifies a board, so it must quote THIS gate's board.
    # It used to quote the PREVIOUS gate's +45.91 pp / −7.41 pp, i.e. the numbers
    # from the run whose correctness cost was subsequently fixed.
    assert "−7.41" not in text and "-7.41" not in text, (
        "the scope must not quote the pre-fix gate's strict-correctness loss"
    )
    assert "+45.91" not in text, (
        "the scope must not quote the pre-fix gate's conciseness gain"
    )
    assert "+38.86 pp" in text, (
        "the scope must quote the shipped ans-conciseness delta"
    )

    # And when the raw payload record IS present, the figure in the report must be
    # the one the record holds — i.e. the section is measured, not hand-typed.
    report = _report_module()
    if not report.SIDECAR.exists():
        return
    leg = report._prompt_scope()["legs"]["B:primary"]
    assert leg["n"] > 0
    assert leg["persona"] > 0
    assert f"{leg['persona']} of {leg['n']}" in text, (
        "the dispatched-persona count must come from the arm's own payload record"
    )
