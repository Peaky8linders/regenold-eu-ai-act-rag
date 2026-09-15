"""R419 — the R416 KG point-text lever's Ans Strict delta, re-scored for credit
reproducibility.

WHAT THIS PINS
--------------
The R416 easy board read ``ans_correctness_strict`` +8.0 pp and named two rows as
the mechanism. R419 re-scored it and found that the entire answer-correctness
movement of that lever is **two criteria out of 87**, and that neither survives
resampling — so the published strict delta collapses to ``+0.00`` on the
surviving rows and the combined Overall moves from ``+0.6`` to ``-0.42``.

Those are now claims other work will build on (a default flip would follow from
them), so they are pinned here in two layers:

1. **The rule functions**, at unit level: sign conventions, the refused silent
   zero, the dropped-repetition case, and the statistical bar that separates a
   real rate gap from a tie.
2. **The artifacts**, end to end: the numbers the checkpoint and the
   ``_kg_point_text_enabled`` docstring quote must be the ones the on-disk
   evidence actually produces. If a re-run of the driver changes them, this test
   fails rather than letting a stale number stand in a docstring.

The resample artifact is *required* by this test: the generation-level exclusion
is the load-bearing half of the finding, and a missing one would silently degrade
rule G to its cited fallback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from docs.measurements.r418 import kg_lever_ans_strict_repro as krs  # noqa: E402

R418 = REPO / "docs" / "measurements" / "r418"
REPRO_JSON = R418 / "kg-lever-ans-strict-repro.json"
RESAMPLE_JSON = R418 / "kgpt-credit-resample.json"


def _load(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not on disk")
    return json.loads(path.read_text(encoding="utf-8"))


# ── 1. the rule functions ───────────────────────────────────────────────────


def test_strict_requires_every_criterion() -> None:
    assert krs._strict([True, True]) is True
    assert krs._strict([True, False]) is False
    # A question with no criteria cannot be "all satisfied" — the rubric's own rule.
    assert krs._strict([]) is False


def test_rep_strict_maps_runs_and_keeps_dropped_reps_visible() -> None:
    runs = [[True, True], [True, False], None]
    assert krs._rep_strict(runs) == [True, False, None]


def test_unanimity_ignores_dropped_repetitions() -> None:
    # Two live draws that agree are unanimous; a dropped draw is not a disagreement.
    assert krs._unanimous([True, True, None]) is True
    # The rg_045 shape: the strict verdict depends on which draw you get.
    assert krs._unanimous([False, True, True]) is False
    assert krs._unanimous([False, False, False]) is True


def test_frac_never_reads_a_malformed_cell_as_a_zero_rate() -> None:
    assert krs._frac("3/5") == (3, 5)
    assert krs._frac("") == (0, 0)
    assert krs._frac("nonsense") == (0, 0)


def test_fisher_bar_separates_a_tie_from_a_separation() -> None:
    # Identical rates (the rg_010 shape) cannot clear any alpha.
    assert krs._fisher_p(3, 5, 3, 5) == pytest.approx(1.0)
    # 1/5 vs 2/5 (the rg_045 shape at n=5) is not a separation either.
    assert krs._fisher_p(2, 5, 1, 5) > krs.GEN_ALPHA
    # 0/10 vs 10/10 is.
    assert krs._fisher_p(10, 10, 0, 10) < krs.GEN_ALPHA


def test_rule_g_is_measured_from_the_resample_and_degrades_honestly(monkeypatch) -> None:
    assert RESAMPLE_JSON.exists(), "the resample artifact is required by the audit"
    data = json.loads(RESAMPLE_JSON.read_text(encoding="utf-8"))
    monkeypatch.setattr(krs, "RESAMPLE", RESAMPLE_JSON)
    for rid in data:
        ok, note = krs._generation_rule(rid)
        assert ok is True, f"{rid}: a row present only in the resample is not a mover"

    # A mover with resample data: the answer is the measurement, not a citation.
    ok, note = krs._generation_rule("rg_010")
    assert ok is False and "measured" in note

    # No resample and no cited evidence -> assumed reproducible, and SAID so.
    monkeypatch.setattr(krs, "RESAMPLE", R418 / "does-not-exist.json")
    ok, note = krs._generation_rule("rg_999")
    assert ok is True and "assumed" in note


# ── 2. the artifacts ────────────────────────────────────────────────────────


def test_repro_artifact_carries_the_published_and_corrected_readings() -> None:
    res = _load(REPRO_JSON)
    v = res["variants"]

    # The published instrument, unchanged — the audit re-scored, it did not re-run.
    assert v["published_all_rows"]["n"] == 25
    assert v["published_all_rows"]["arm_a"]["ans_correctness_strict"] == 88.0
    assert v["published_all_rows"]["arm_b"]["ans_correctness_strict"] == 96.0
    assert v["published_all_rows"]["delta_pp"]["ans_correctness_strict"] == 8.0

    # Both rows excluded: the arms are row-for-row identical on strict — the
    # delta is exactly zero, not merely "not significant".
    assert v["excl_both"]["n"] == 23
    assert v["excl_both"]["delta_pp"]["ans_correctness_strict"] == 0.0
    assert v["excl_both"]["arm_a"]["ans_correctness_strict"] == v["excl_both"]["arm_b"][
        "ans_correctness_strict"
    ]

    # The instrument's own repetition bound never reaches zero, which is why the
    # reproducibility test — not the min-max band — is the one that decides.
    assert res["rep_level_bounds"]["delta_min_pp"] == 4.0
    assert res["rep_level_bounds"]["delta_max_pp"] == 8.0


def test_repro_artifact_names_exactly_the_two_movers_and_their_exclusions() -> None:
    res = _load(REPRO_JSON)
    assert {m["id"] for m in res["strict_movers"]} == {"rg_010", "rg_045"}
    # rg_045 is dropped by the judge's own repetitions; rg_010 by fresh generations.
    assert res["excluded_judge_unstable"] == ["rg_045"]
    assert set(res["excluded_generation_unstable"]) == {"rg_010", "rg_045"}
    assert res["resample_artifact"] == "kgpt-credit-resample.json"


def test_corrected_board_moves_the_overall_negative() -> None:
    res = _load(REPRO_JSON)
    board = res["corrected_board"]
    assert board["published_overall"]["delta_pp"] == pytest.approx(0.6)
    assert board["delta_pp"]["ans_correctness_strict"] == 0.0
    assert board["delta_pp"]["ans_correctness_loose"] == 0.0
    # The only axes left non-flat are the conciseness cost and its speed offset.
    assert board["delta_pp"]["ans_conciseness"] == pytest.approx(-3.3)
    assert board["delta_pp"]["ref_correctness_loose"] == 0.0
    assert board["delta_pp"]["overall"] == pytest.approx(-0.42)


def test_resample_artifact_is_significant_and_primary_served() -> None:
    data = _load(RESAMPLE_JSON)
    assert set(data) == {"rg_010|KG=0", "rg_010|KG=1", "rg_045|KG=0", "rg_045|KG=1"}
    for cell, v in data.items():
        # The R415/R416 doctrine: only primary-transport samples may be read.
        assert v["n_fallback_excluded"] == 0, f"{cell} was served by the fallback leg"
        assert v["n_primary"] >= 10, f"{cell} is under-sampled for a rate claim"
    def _rate(cell: str) -> float:
        k, n = (int(x) for x in data[cell]["focal_credit_majority"].split("/"))
        return k / n

    # rg_010: the aim limb is credited at the SAME rate on both arms — the
    # 4/5 vs 5/5 split the published arm pair shows is one draw each. Both the
    # rate gap and the audit's own decision are pinned, so a future re-run that
    # finds separation fails here instead of quietly changing the conclusion.
    assert abs(_rate("rg_010|KG=1") - _rate("rg_010|KG=0")) <= 0.2
    assert krs._generation_rule("rg_010")[0] is False
    # rg_045: the ON arm leans higher but nowhere near the bar — the row is a
    # coin flip on the baseline arm, which is why a 1-vs-1 pair can credit it.
    assert 0.0 < _rate("rg_045|KG=0") <= 0.4
    assert krs._generation_rule("rg_045")[0] is False
