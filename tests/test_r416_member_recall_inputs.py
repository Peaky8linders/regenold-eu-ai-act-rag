"""The recall audit must diagnose graded answers, never absent/turn-1 text."""
from __future__ import annotations

import json

import pytest

from docs.measurements.r411 import member_recall_probe as probe


def _inputs(monkeypatch, tmp_path, rows):
    checkpoint = tmp_path / "answers.jsonl"
    gold = tmp_path / "gold.jsonl"
    triage = tmp_path / "triage.json"
    checkpoint.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    gold.write_text(json.dumps({"id": "rg_test", "question": "List the items in Article 13(3)."}), encoding="utf-8")
    triage.write_text(json.dumps([{"id": "rg_test", "rc": "OMITTED_ENUMERATED_ITEM"}]), encoding="utf-8")
    monkeypatch.setattr(probe, "CKPT", checkpoint)
    monkeypatch.setattr(probe, "GOLD", gold)
    monkeypatch.setattr(probe, "TRIAGE", triage)
    monkeypatch.setattr(probe, "ROOT", tmp_path)


def test_graded_answer_wins_over_ungraded_alternatives(monkeypatch, tmp_path):
    _inputs(monkeypatch, tmp_path, [{
        "id": "rg_test", "pred_answer": "Article 13(3)(b) specifies characteristics.",
        "answer": "wrong alias", "final_answer": "wrong final alias", "turn1_answer": "wrong turn",
    }])
    answers, _, _ = probe._load()
    assert answers == {"rg_test": "Article 13(3)(b) specifies characteristics."}
    output = tmp_path / "report.json"
    assert probe.main(["--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["graded_answers"] == 1
    assert report["rows"][0]["gate"] == "ENGAGED"
    assert "Article 13.3.a" in report["rows"][0]["gaps"]
    assert all(len(sha) == 64 for sha in report["inputs"].values())


@pytest.mark.parametrize("graded", [None, "", "   ", [], 12])
def test_void_graded_answer_cannot_fall_back_or_report_success(monkeypatch, tmp_path, capsys, graded):
    _inputs(monkeypatch, tmp_path, [{"id": "rg_test", "pred_answer": graded, "answer": "has text", "turn1_answer": "has text"}])
    output = tmp_path / "report.json"
    assert probe.main(["--output", str(output)]) == 2
    assert "INDETERMINATE" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("rows", [
    [],
    [{"id": "other", "pred_answer": "unrelated answer"}],
    [{"id": "rg_test", "pred_answer": "a"}, {"id": "rg_test", "pred_answer": "b"}],
])
def test_missing_or_duplicate_target_answers_are_indeterminate(monkeypatch, tmp_path, rows):
    _inputs(monkeypatch, tmp_path, rows)
    assert probe.main([]) == 2


def test_empty_answer_is_an_input_error_even_for_non_list_question():
    with pytest.raises(ValueError, match="graded answer"):
        probe._gate_report("Is this allowed?", "")


def test_frozen_corpus_reaches_real_member_detector():
    if not all(p.exists() for p in (probe.CKPT, probe.GOLD, probe.TRIAGE)):
        pytest.skip("gitignored R407 competition checkpoint unavailable")
    answers, questions, _ = probe._load()
    assert len(answers) == 110
    # The old loader returned zero answers and falsely diagnosed these as
    # no_named_head. The actual detector finds omissions in both graded rows.
    for rid in ("rg_046", "rg_052"):
        assert probe._gate_report(questions[rid], answers[rid])[0] == "ENGAGED"
        assert probe.AC.missing_closed_set_members(questions[rid], answers[rid])
