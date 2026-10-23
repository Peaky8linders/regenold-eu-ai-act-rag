"""R409 — eval-instrument accounting the R407 hard-mode scorecard got wrong.

* Resp. Speed was scored on turn 1 PLUS the pushback turn, and on a 13 s Cohere
  pacing sleep that runs inside the in-process request.
* A judge verdict that lost a repetition was cached as if complete.
"""
import pytest

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


def test_score_arm_refuses_explicitly_degraded_stage2_rows():
    degraded = [
        {"id": "det", "provenance": {"stage2_served_by": "deterministic", "stage2_polish": False}},
        {"id": "fallback", "provenance": {"stage2_served_by": "fallback", "stage2_polish": True}},
        {"id": "prior", "provenance": {"stage2_served_by": "prior_turn", "stage2_polish": True}},
        {"id": "dropped", "provenance": {"stage2_served_by": "primary", "stage2_polish": False}},
    ]
    assert sa._rejected_rows(degraded) == [
        ("det", "stage2_served_by=deterministic"),
        ("fallback", "stage2_served_by=fallback"),
        ("prior", "stage2_served_by=prior_turn"),
        ("dropped", "stage2_polish=false"),
    ]


def test_score_arm_accepts_only_recognized_intentional_skips_or_primary_polish():
    rows = [
        {
            "id": "curated",
            "provenance": {
                "stage2_polish": False,
                "stage2_served_by": "",
                "stage2_skip_reason": "stage2_skipped_curated_authoritative",
            },
        },
        {"id": "primary", "provenance": {"stage2_polish": True, "stage2_served_by": "primary"}},
        {"id": "legacy", "provenance": {}},
        {"id": "missing"},
        {"id": "unknown_skip", "provenance": {"stage2_polish": False, "stage2_skip_reason": "some-other-reason"}},
    ]
    assert sa._rejected_rows(rows) == [
        ("legacy", "stage2_polish_unknown"),
        ("missing", "missing_provenance"),
        ("unknown_skip", "unrecognized_stage2_skip_reason=some-other-reason"),
    ]


def test_hard_mode_turn_capture_keeps_independent_provenance_and_cache_identity(tmp_path):
    import json

    ckpt = tmp_path / "hard.jsonl"
    record = {
        "id": "rg_037",
        "question": "q",
        "pred_answer": "pushback",
        "pred_refs": ["Article 49.1"],
        "turn1_answer": "first",
        "turn1_refs": ["Article 49.1"],
        "pushback_answer": "pushback",
        "pushback_refs": ["Article 49.1"],
        "turn1_latency_ms": 11,
        "pushback_latency_ms": 22,
        "provenance": {"stage2_polish": True, "stage2_served_by": "primary"},
        "turn1_provenance": {"stage2_polish": True, "stage2_served_by": "primary"},
        "pushback_provenance": {"stage2_polish": False, "stage2_served_by": "deterministic"},
    }
    ckpt.write_text(json.dumps(record), encoding="utf-8")

    first = sa.load_ckpt(ckpt, turn="turn1")[0]
    pushback = sa.load_ckpt(ckpt, turn="pushback")[0]
    assert first["answer"] == "first" and first["latency_s"] == 0.011
    assert first["provenance"]["stage2_served_by"] == "primary"
    assert pushback["answer"] == "pushback" and pushback["latency_s"] == 0.022
    assert pushback["provenance"]["stage2_served_by"] == "deterministic"
    assert sa._row_cache_key(first, "judge") != sa._row_cache_key(pushback, "judge")
    assert sa._stage2_row_rejection_reason(pushback) == "stage2_served_by=deterministic"


def test_score_arm_rejects_missing_or_degraded_turn_provenance():
    assert sa._rejected_rows([{"id": "missing", "provenance": None}]) == [
        ("missing", "missing_provenance")
    ]
    assert sa._rejected_rows([{"id": "dropped", "provenance": {"stage2_polish": False}}]) == [
        ("dropped", "stage2_polish=false")
    ]
    assert sa._rejected_rows([{"id": "unverified", "provenance": {"stage2_polish": True}}]) == [
        ("unverified", "unverified_stage2_served_by=missing")
    ]


_PRIMARY = {"stage2_polish": True, "stage2_served_by": "primary", "stage2_skip_reason": ""}
_LEGACY_CURATED = {"stage2_polish": False, "stage2_served_by": ""}  # no skip-reason key
_LEGACY_NO_LEG = {"stage2_polish": True, "stage2_served_by": ""}  # captured before R417


def _score_main(monkeypatch, tmp_path, rows, *extra, mode="easy"):
    """Drive ``score_arm.main`` with a faked judge; return (outcome, judge_calls, out_dir)."""
    import json
    import sys

    gold = {
        row["id"]: {"criteria": ["c1"], "reference_answer": "ref", "expected_refs": ["Article 13"]}
        for row in rows
    }
    ckpt = tmp_path / f"arm-{mode}.ckpt.jsonl"
    ckpt.write_text(
        chr(10).join(json.dumps(r) for r in rows) + chr(10), encoding="utf-8"
    )
    calls: list[int] = []

    def fake_judge_rows(todo, workers=1, repeats=1, on_row=None):
        calls.append(len(todo))
        return [
            {**r, "criteria": [True] * len(r["criteria_text"]), "tone_ok": True,
             "_judge_runs": repeats, "_tone_runs": repeats,
             "criterion_remarks": [], "tone_remark": ""}
            for r in todo
        ]

    monkeypatch.setattr(sa, "load_gold", lambda: gold)
    monkeypatch.setattr(sa, "OUT_DIR", tmp_path)
    monkeypatch.setattr(sa, "CACHE", tmp_path / "judge-cache.jsonl")
    monkeypatch.setattr(sa, "load_cache", lambda path: {})
    monkeypatch.setattr(sa.official_judge, "judge_rows", fake_judge_rows)
    monkeypatch.setattr(
        sys, "argv",
        ["score_arm", "--ckpt", str(ckpt), "--label", "gate", "--mode", mode,
         "--repeats", "1", "--no-deepen", *extra],
    )
    try:
        outcome = sa.main()
    except SystemExit as exc:
        outcome = str(exc.code)
    return outcome, calls, tmp_path


def _row(row_id, provenance, **extra):
    row = {"id": row_id, "question": "q", "pred_answer": "An answer.", "pred_refs": ["Article 13"],
           "latency_ms": 1000}
    if provenance is not None:
        row["provenance"] = provenance
    return {**row, **extra}


def test_older_capture_without_evidence_is_scored_and_disclosed(monkeypatch, tmp_path, capsys):
    """A checkpoint from before provenance / skip reasons existed must stay scoreable.

    A curated row has ``stage2_polish`` False and (pre skip-reason) no recorded
    reason; refusing it would refuse every older board and every ``--resume``.
    """
    import json

    rows = [
        _row("rg_900", _LEGACY_CURATED),
        _row("rg_901", _LEGACY_NO_LEG),
        _row("rg_902", None),
        _row("rg_903", _PRIMARY),
    ]
    outcome, calls, out_dir = _score_main(monkeypatch, tmp_path, rows)
    assert outcome == 0 and calls == [4]
    assert "UNVERIFIED" in capsys.readouterr().out
    payload = json.loads((out_dir / "score-gate-easy.json").read_text(encoding="utf-8"))
    assert payload["stage2_unverified_rows"] == ["rg_900", "rg_901", "rg_902"]


@pytest.mark.parametrize(
    "provenance",
    [
        {"stage2_polish": True, "stage2_served_by": "fallback"},
        {"stage2_polish": False, "stage2_served_by": "deterministic"},
        {"stage2_polish": True, "stage2_served_by": "prior_turn"},
        # captured AFTER skip reasons existed: no reason recorded means none was emitted
        {"stage2_polish": False, "stage2_served_by": "", "stage2_skip_reason": ""},
        # contradictory: a serve leg is named yet the polish did not land
        {"stage2_polish": False, "stage2_served_by": "primary"},
    ],
)
def test_positive_evidence_of_degradation_refuses_before_any_judge_call(
    monkeypatch, tmp_path, provenance
):
    outcome, calls, _ = _score_main(
        monkeypatch, tmp_path, [_row("rg_900", _PRIMARY), _row("rg_901", provenance)]
    )
    assert "refusing to grade rows" in str(outcome) and "rg_901" in str(outcome)
    assert calls == []


def test_a_per_turn_run_refuses_a_row_with_no_provenance_for_that_turn(monkeypatch, tmp_path):
    row = _row("rg_900", _PRIMARY, pushback_answer="Revised.", turn1_answer="First.")
    outcome, calls, _ = _score_main(
        monkeypatch, tmp_path, [row], "--turn", "pushback", mode="hard"
    )
    assert "refusing to grade rows" in str(outcome) and "rg_900" in str(outcome)
    assert calls == []


def test_an_existing_score_artifact_is_refused_before_the_judge_runs(monkeypatch, tmp_path):
    (tmp_path / "score-gate-easy.json").write_text("{}", encoding="utf-8")
    outcome, calls, _ = _score_main(monkeypatch, tmp_path, [_row("rg_900", _PRIMARY)])
    assert "refusing to overwrite score artifact" in str(outcome)
    assert calls == []
    assert (tmp_path / "score-gate-easy.json").read_text(encoding="utf-8") == "{}"
