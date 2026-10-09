"""R460 - length-controlled judging in the official instrument.

The answer axes are judged from the answer text and judges credit length, so a
correctness edge can be verbosity. ``--length-control`` re-judges every answer cut
to its own reference length; these tests pin the cut (sentence boundary, never
expanding, never empty) and the row builder (an answer already within the
reference length is returned verbatim).
"""
from __future__ import annotations

import json
import re
import sys

import pytest

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
    # R461: with no sentence end in reach the cut is a WHOLE-WORD prefix. It used to
    # be ``text[:20].strip()`` ("A single very long s"), a mid-word cut that
    # measures fluency damage, which is what the sentence-boundary rule exists to
    # avoid. The new assertion is stricter, not looser.
    assert cut == "A single very long"
    assert truncate_to_chars("No terminator anywhere in this text", 0) == ""


def test_non_positive_limit_is_empty():
    assert truncate_to_chars("anything", -5) == ""


def test_row_builder_cuts_only_over_length_answers():
    rows = [
        {"id": "a", "question": "Q?", "answer": "One. Two. Three.",
         "reference_answer": "One."},
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
    # R463 - this used to read `assert capped["question"] if "question" in capped
    # else True`. No row carried a "question", so the condition was always False and
    # the statement asserted the literal True: it could never fail. Row a now
    # carries one, so the carry-through the old line claimed to guard is real.
    assert out[0]["question"] == "Q?", "row fields carried through survive the copy"
    for original, capped in zip(rows, out, strict=True):
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
    # No sentence end fits in 10 chars, so the cut is the whole-word prefix (R461:
    # it used to be the mid-word ``long_answer[:ref_len].strip()`` = "The provid").
    assert passes[1][0] == "The"
    assert len(passes[1][0]) <= ref_len
    assert passes[1][1] == "Short.", "an answer under the reference length is verbatim"
    payload = _json.loads((tmp_path / "score-lc-test-easy.json").read_text(encoding="utf-8"))
    assert payload["length_controlled"]["cached"] is False
    assert payload["length_controlled"]["answers_cut"] == 1
    assert payload["axes"]["ans_correctness_loose"] == 100.0


def test_the_flag_wires_the_length_controlled_payload_field(monkeypatch, tmp_path):
    """The flag must be WIRED to the payload field, not merely present in the file.

    R463: this test used to scan ``inspect.getsource(score_arm)`` for the literals
    ``"length_controlled": length_controlled`` and ``--length-control``. A source
    scan fails on a harmless rename and passes on a behavioural regression (right
    key, wrong value), which is the opposite of what this file's other tests do —
    the house rule is to assert on the WRITTEN payload. So drive ``main()`` twice
    over one checkpoint: with the flag off the field is the pre-R460 ``None``, with
    it on the field carries the pass's own accounting.
    """
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER, "Short."])

    def fake_call_json(prompt, *a, **k):
        return {
            "verdicts": [{"n": 1, "satisfied": True, "why": "x"},
                         {"n": 2, "satisfied": True, "why": "y"}],
            "tone": {"appropriate": True, "clear": True, "why": "ok"},
        }

    monkeypatch.setattr(score_arm.official_judge, "_call_json", fake_call_json)

    def run(label, *extra):
        monkeypatch.setattr(sys, "argv", [
            "score_arm", "--ckpt", str(ckpt), "--label", label, "--mode", "easy",
            "--workers", "1", "--repeats", "1", *extra,
        ])
        assert score_arm.main() == 0
        return json.loads(
            (tmp_path / f"score-{label}-easy.json").read_text(encoding="utf-8")
        )

    assert run("lc-off")["length_controlled"] is None, (
        "flag off: the pre-R460 payload shape, no controlled axes field"
    )
    on = run("lc-on", "--length-control")["length_controlled"]
    assert on["cached"] is False
    assert on["n"] == 2
    assert on["answers_cut"] == 1
    assert set(on["axes"]) == {
        "ans_correctness_loose",
        "ans_correctness_strict",
        "ans_conciseness",
        "regulatory_tone",
    }


# -- R461: the pass must grade against the GOLD, not against the first verdicts --

GOLD_CRITERIA = [
    "States that the provider must draw up technical documentation",
    "Mentions Annex IV",
]
REFERENCE = "A reference answer of some length here."
LONG_ANSWER = "The provider must draw up technical documentation. " * 12


def _stage(monkeypatch, tmp_path, answers):
    """Point score_arm at a tmp checkpoint of ``answers``; judge transport untouched."""
    import evals.official.score_arm as score_arm

    rows = [
        {"id": f"rg_{900 + i}", "question": f"Q{i}?", "pred_answer": a,
         "pred_refs": ["Article 13"], "latency_ms": 1000}
        for i, a in enumerate(answers)
    ]
    ckpt = tmp_path / "arm-easy.ckpt.jsonl"
    ckpt.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    gold = {
        r["id"]: {"criteria": list(GOLD_CRITERIA), "reference_answer": REFERENCE,
                  "expected_refs": ["Article 13"]}
        for r in rows
    }
    monkeypatch.setattr(score_arm, "load_gold", lambda: gold)
    monkeypatch.setattr(score_arm, "OUT_DIR", tmp_path)
    monkeypatch.setattr(score_arm, "CACHE", tmp_path / "judge-cache.jsonl")
    monkeypatch.setattr(score_arm, "load_cache", lambda path: {})
    monkeypatch.setattr(score_arm.official_judge, "configure_judge", lambda *a, **k: None)
    return score_arm, ckpt


def _run_main(monkeypatch, score_arm, ckpt, *extra):
    monkeypatch.setattr(sys, "argv", [
        "score_arm", "--ckpt", str(ckpt), "--label", "lc", "--mode", "easy",
        "--length-control", "--workers", "1", *extra,
    ])
    return score_arm.main()


def test_length_control_pass_is_judged_against_gold_criteria_not_verdict_booleans(
    monkeypatch, tmp_path
):
    """Stub ONLY the judge transport and assert on the BYTES the judge is sent.

    ``test_length_control_block_runs_end_to_end`` cannot see this class: its fake
    ``judge_rows`` sizes the verdicts from ``criteria_text`` and never inspects what
    a judge would be handed. Before R461 the second pass was handed the first
    pass's verdict booleans as its criteria, so the judge was asked whether the
    answer satisfied the strings "True" and "False", and the recorded R460
    "94.07 -> 54.81" headline was a measurement of that, not of length.
    """
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER, "Short."])
    prompts: list[str] = []

    def fake_call_json(prompt, *a, **k):
        prompts.append(prompt)
        # A MIXED verdict: if it leaked into the next pass the block would read
        # "1. True / 2. False" rather than the gold text.
        return {
            "verdicts": [{"n": 1, "satisfied": True, "why": "x"},
                         {"n": 2, "satisfied": False, "why": "y"}],
            "tone": {"appropriate": True, "clear": True, "why": "ok"},
        }

    monkeypatch.setattr(score_arm.official_judge, "_call_json", fake_call_json)
    assert _run_main(monkeypatch, score_arm, ckpt, "--repeats", "1") == 0
    assert len(prompts) == 4, "two rows x (raw pass + length-control pass)"
    expected = "1. " + GOLD_CRITERIA[0] + "\n2. " + GOLD_CRITERIA[1]
    for i, prompt in enumerate(prompts):
        block = re.search(r"CRITERIA:\n(.*?)\n\nCANDIDATE ANSWER", prompt, re.S).group(1)
        assert block == expected, f"prompt {i} ({'raw' if i < 2 else 'LC'} pass): {block!r}"
    # The second pass really did dispatch the CUT answer for the long row, and the
    # short row verbatim.
    assert LONG_ANSWER.strip() in prompts[0]
    assert LONG_ANSWER.strip() not in prompts[2]
    assert "Short." in prompts[3]


def test_row_builder_rebuilds_criteria_from_gold_and_drops_stale_verdicts():
    judged = {
        "id": "a", "answer": "One. Two. Three.", "reference_answer": "One.",
        "criteria": [True, False], "criteria_text": ["gold 1", "gold 2"],
        "criterion_remarks": ["x", "y"], "tone_ok": True, "tone_remark": "fine",
        "_judge_runs": 3, "_tone_runs": 3, "_corr_runs": [[True, False]] * 3,
        "_tone_runs_raw": [True] * 3, "_criteria_rate_min": 0.5,
        "_criteria_rate_max": 0.5, "_judge_errors": 0, "_judge_exception": "boom",
    }
    snapshot = json.loads(json.dumps(judged))
    (out,) = _length_controlled_rows([judged])
    assert out["criteria"] == ["gold 1", "gold 2"]
    assert out["criteria_text"] == ["gold 1", "gold 2"]
    assert out["answer"] == "One."
    for key in ("criterion_remarks", "tone_ok", "tone_remark", "_judge_runs", "_tone_runs",
                "_corr_runs", "_tone_runs_raw", "_criteria_rate_min", "_criteria_rate_max",
                "_judge_errors", "_judge_exception"):
        assert key not in out, f"stale verdict key {key!r} survived into the second pass"
    assert judged == snapshot, "the judged input row is never mutated"
    assert out is not judged
    assert out["criteria"] is not out["criteria_text"]


def test_row_builder_refuses_verdict_booleans_with_no_gold_to_rebuild_them_from():
    with pytest.raises(ValueError, match="no criteria_text"):
        _length_controlled_rows(
            [{"id": "x", "answer": "A.", "reference_answer": "B.", "criteria": [True, False]}]
        )
    # Rows that carry no criteria at all (the plain row-builder case) are fine.
    assert _length_controlled_rows([{"id": "y", "answer": "A."}])[0]["answer"] == "A."


# -- R461: a degraded length-control pass is VOID, like a degraded raw pass --


def _fake_judge_rows(calls, *, raw_dead=0, lc_dead=0, lc_runs=None):
    """Healthy first call (raw pass); the second call (LC pass) degraded as asked."""

    def fake(todo, workers=1, repeats=1, on_row=None):
        phase = len(calls)
        calls.append(len(todo))
        dead_n = raw_dead if phase == 0 else lc_dead
        out = []
        for i, r in enumerate(todo):
            dead = i < dead_n
            runs = 0 if dead else (lc_runs if (phase and lc_runs is not None) else repeats)
            out.append({
                **r, "criteria": [not dead] * len(r["criteria_text"]), "tone_ok": not dead,
                "_judge_runs": runs, "_tone_runs": runs,
                "criterion_remarks": [], "tone_remark": "",
            })
        return out

    return fake


def _lc_payload(tmp_path):
    return json.loads((tmp_path / "score-lc-easy.json").read_text(encoding="utf-8"))


def test_dead_lc_pass_is_void_not_a_measurement(monkeypatch, tmp_path):
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER] * 10)
    calls: list[int] = []
    monkeypatch.setattr(score_arm.official_judge, "judge_rows", _fake_judge_rows(calls, lc_dead=10))
    assert _run_main(monkeypatch, score_arm, ckpt, "--repeats", "1") == 3
    assert calls == [10, 10]
    payload = _lc_payload(tmp_path)
    assert payload["axes"]["ans_correctness_loose"] == 100.0, "the valid raw pass still ships"
    lc = payload["length_controlled"]
    assert lc["void"] and isinstance(lc["void"], str)
    assert lc["dead_rows"] == 10 and lc["n"] == 10 and lc["answers_cut"] == 10
    assert lc["axes"] is None, "the all-False controlled axes must not be published"


def test_lc_pass_below_the_void_fraction_is_recorded_not_hidden(monkeypatch, tmp_path):
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER] * 10)
    monkeypatch.setattr(score_arm.official_judge, "judge_rows", _fake_judge_rows([], lc_dead=1))
    assert _run_main(monkeypatch, score_arm, ckpt, "--repeats", "1") == 0
    lc = _lc_payload(tmp_path)["length_controlled"]
    assert lc["dead_rows"] == 1 and "void" not in lc
    assert lc["axes"]["ans_correctness_loose"] == 90.0


def test_lc_partial_repeats_are_recorded(monkeypatch, tmp_path):
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER] * 10)
    monkeypatch.setattr(score_arm.official_judge, "judge_rows", _fake_judge_rows([], lc_runs=2))
    assert _run_main(monkeypatch, score_arm, ckpt, "--repeats", "3") == 0
    lc = _lc_payload(tmp_path)["length_controlled"]
    assert lc["partial_rows"] == 10 and lc["dead_rows"] == 0 and "void" not in lc
    assert lc["axes"]["ans_correctness_loose"] == 100.0, "scored on the live runs"


def test_healthy_lc_pass_records_zero_counts(monkeypatch, tmp_path):
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER] * 10)
    monkeypatch.setattr(score_arm.official_judge, "judge_rows", _fake_judge_rows([]))
    assert _run_main(monkeypatch, score_arm, ckpt, "--repeats", "1") == 0
    lc = _lc_payload(tmp_path)["length_controlled"]
    assert (lc["dead_rows"], lc["tone_dead_rows"], lc["partial_rows"]) == (0, 0, 0)
    assert "void" not in lc and lc["axes"]["ans_correctness_loose"] == 100.0


def test_a_void_raw_pass_still_wins_over_the_lc_pass(monkeypatch, tmp_path):
    score_arm, ckpt = _stage(monkeypatch, tmp_path, [LONG_ANSWER] * 10)
    monkeypatch.setattr(score_arm.official_judge, "judge_rows", _fake_judge_rows([], raw_dead=3))
    assert _run_main(monkeypatch, score_arm, ckpt, "--repeats", "1") == 3
    assert (tmp_path / "score-lc-easy.VOID.json").exists()
    assert not (tmp_path / "score-lc-easy.json").exists()


# -- R461: the cut lands on a real sentence end, never inside a coordinate or a word --


def test_does_not_cut_at_a_digit_dot():
    text = "Providers must meet the duties in Article 13.3 and the further duties that follow."
    cut = truncate_to_chars(text, 45)
    assert cut == "Providers must meet the duties in Article"
    cut = truncate_to_chars("See Annex XII.1(f) for details. More text follows here.", 14)
    assert not cut.endswith("XII.")
    assert cut == "See Annex"


def test_does_not_cut_at_an_abbreviation_dot():
    text = "Yes. The ban in Art. 5 applies to real-time remote biometric identification."
    assert truncate_to_chars(text, 60) == "Yes."


def test_terminator_at_the_window_edge_is_checked_against_the_real_next_char():
    # The "." ending the 11-char window is followed by "3": not a sentence end.
    assert truncate_to_chars("Article 13.3 sets duties. Next sentence follows.", 11) == "Article"


def test_no_terminator_cuts_on_a_word_boundary():
    text = "A single very long sentence that has no early terminator at all"
    assert truncate_to_chars(text, 20) == "A single very long"
    for limit in range(1, len(text)):
        cut = truncate_to_chars(text, limit)
        assert len(cut) <= limit
        assert text.startswith(cut)
        rest = text[len(cut):len(cut) + 1]
        assert rest == "" or rest.isspace() or cut == text[:limit].strip(), (limit, cut)
    # One giant token has no word boundary to fall back to: still capped at the limit.
    assert truncate_to_chars("A" * 30, 10) == "A" * 10


def test_closing_quote_is_kept_with_its_sentence():
    assert truncate_to_chars('He said "stop." Then left the room and more words here.', 20) == (
        'He said "stop."'
    )
