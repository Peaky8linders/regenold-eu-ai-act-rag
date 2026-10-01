"""R460 - length-controlled judging in the official instrument.

The answer axes are judged from the answer text and judges credit length, so a
correctness edge can be verbosity. ``--length-control`` re-judges every answer cut
to its own reference length; these tests pin the cut (sentence boundary, never
expanding, never empty) and the row builder (an answer already within the
reference length is returned verbatim).
"""
from __future__ import annotations

import inspect

from evals.official.rubric import truncate_to_chars
from evals.official.score_arm import _length_controlled_rows


def test_returns_short_text_unchanged():
    for text, limit in (("Short.", 100), ("Exactly ten.", 13), ("", 10)):
        assert truncate_to_chars(text, limit) == text


def test_cuts_at_a_sentence_boundary():
    text = "First sentence here. Second sentence here. Third one runs on and on."
    # 43 chars covers both leading sentences; 40 lands inside the second one, so
    # the cut must fall back to the FIRST terminator that fits.
    assert truncate_to_chars(text, 43) == "First sentence here. Second sentence here."
    assert truncate_to_chars(text, 40) == "First sentence here."
    for limit in (20, 40, 43, 50):
        cut = truncate_to_chars(text, limit)
        assert len(cut) <= limit
        assert cut == cut.strip()


def test_never_cuts_below_one_sentence_or_leaks_past_the_limit():
    text = "A single very long sentence that has no early terminator at all"
    cut = truncate_to_chars(text, 20)
    assert cut == text[:20].strip()
    assert truncate_to_chars("No terminator anywhere in this text", 0) == ""


def test_non_positive_limit_is_empty():
    assert truncate_to_chars("anything", -5) == ""


def test_row_builder_cuts_only_over_length_answers():
    rows = [
        {"id": "a", "answer": "One. Two. Three.", "reference_answer": "One."},
        {"id": "b", "answer": "Short.", "reference_answer": "A much longer reference answer."},
        {"id": "c", "answer": "", "reference_answer": "Reference."},
        {"id": "d", "answer": "Answer without a reference answer.", "reference_answer": ""},
    ]
    out = _length_controlled_rows(rows)
    assert out[0]["answer"] == "One."            # cut to the 4-char reference
    assert out[1]["answer"] == "Short."          # already under: verbatim
    assert out[2]["answer"] == ""                # empty stays empty
    assert out[3]["answer"] == rows[3]["answer"]  # no reference: no control
    assert [r["id"] for r in out] == ["a", "b", "c", "d"]
    for original, capped in zip(rows, out, strict=True):
        assert capped["question"] if "question" in capped else True
        assert original is not capped  # a copy, never an in-place mutation


def test_length_control_block_runs_end_to_end(monkeypatch, tmp_path):
    """Exercise main() with the flag: two judge passes, a cut, a payload field.

    A static check cannot see a NameError raised only on this path (one shipped
    in the first draft of the block), so this runs the scorer with the judge
    transport faked and the repo's cache/out paths redirected to tmp_path.
    """
    import json as _json
    import sys as _sys

    import evals.official.score_arm as score_arm

    long_answer = "The provider must do a thing. " * 12
    rows = [
        {"id": "rg_900", "question": "Q1?", "pred_answer": long_answer,
         "pred_refs": ["Article 13"], "latency_ms": 1000},
        {"id": "rg_901", "question": "Q2?", "pred_answer": "Short.",
         "pred_refs": ["Article 6"], "latency_ms": 1000},
    ]
    ckpt = tmp_path / "arm-easy.ckpt.jsonl"
    ckpt.write_text(
        chr(10).join(_json.dumps(r) for r in rows) + chr(10), encoding="utf-8"
    )
    gold = {
        "rg_900": {"criteria": ["c1"], "reference_answer": "Short ref.",
                   "expected_refs": ["Article 13"]},
        "rg_901": {"criteria": ["c1"],
                   "reference_answer": "A reference answer far longer than the candidate.",
                   "expected_refs": ["Article 6"]},
    }
    monkeypatch.setattr(score_arm, "load_gold", lambda: gold)
    monkeypatch.setattr(score_arm, "OUT_DIR", tmp_path)
    monkeypatch.setattr(score_arm, "CACHE", tmp_path / "judge-cache.jsonl")
    monkeypatch.setattr(score_arm, "load_cache", lambda path: {})
    passes: list[list[str]] = []

    def fake_judge_rows(todo, workers=1, repeats=1, on_row=None):
        passes.append([r["answer"] for r in todo])
        return [
            {**r, "criteria": [True] * len(r["criteria_text"]), "tone_ok": True,
             "_judge_runs": repeats, "_tone_runs": repeats,
             "criterion_remarks": [], "tone_remark": ""}
            for r in todo
        ]

    monkeypatch.setattr(score_arm.official_judge, "judge_rows", fake_judge_rows)
    monkeypatch.setattr(_sys, "argv", [
        "score_arm", "--ckpt", str(ckpt), "--label", "lc-test", "--mode", "easy",
        "--length-control", "--repeats", "1",
    ])
    assert score_arm.main() == 0
    assert len(passes) == 2, "one raw pass and one length-controlled pass"
    assert passes[0][0].startswith("The provider must do a thing.")
    ref_len = len("Short ref.")
    assert passes[1][0] == long_answer[:ref_len].strip()  # cut to the reference length
    assert len(passes[1][0]) <= ref_len
    assert passes[1][1] == "Short.", "an answer under the reference length is verbatim"
    payload = _json.loads((tmp_path / "score-lc-test-easy.json").read_text(encoding="utf-8"))
    assert payload["length_controlled"]["cached"] is False
    assert payload["length_controlled"]["answers_cut"] == 1
    assert payload["axes"]["ans_correctness_loose"] == 100.0


def test_flag_is_wired_and_reported_in_the_payload():
    import evals.official.score_arm as score_arm

    source = inspect.getsource(score_arm)
    assert "--length-control" in source
    assert '"length_controlled": length_controlled' in source
    assert "LENGTH-CONTROL PASS DEGRADED" in source, "a dead judge must be loud"
