"""R461 - the COUNT-ONLY conciseness lever.

``REGENOLD_CONCISE_COUNT_ONLY`` renders the citation-budget half of the R460
calibration block and none of the length battery. The whole point of the lever is
that the two halves differ, so these tests pin the ABSENCE of every length clause
as hard as they pin the presence of the budget, and they pin that the shared
clauses are byte-identical to the full block's - otherwise the gate would be
comparing a re-wording, not a removal.

Default OFF: the flag is an allow-list, so every rendering
assertion is paired with the byte-identical-when-off check the house doctrine
requires.
"""
from __future__ import annotations

import pytest

from app.data.graph_rag_prompts import build_evidence_answer_user
from app.engines.answer_need import (
    calibration_block,
    calibration_citation_budget,
    calibration_enabled,
    concise_limits,
    conciseness_mode,
    count_only_block,
    count_only_enabled,
)
from app.engines.answer_need import answer_need

QUESTION = "What transparency obligations does Article 13 impose on providers?"
SCENARIO = (
    "A hospital deploys an AI system to triage patients in its emergency "
    "department and asks which obligations bind it as a high-risk deployer."
)

#: Every clause of the R460 length battery. None of these may appear in the
#: count-only block: removing them is the entire experimental manipulation.
LENGTH_CLAUSES = (
    "sentences",
    "words",
    "Match this shape",
    "Draft, then COUNT",
    "LENGTH AND CITATION",
    "Delete the sentence",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION", raising=False)
    monkeypatch.delenv("REGENOLD_CONCISE_COUNT_ONLY", raising=False)
    monkeypatch.delenv("REGENOLD_CONCISE_CONTRACT", raising=False)
    monkeypatch.delenv("REGENOLD_NEED_PROPORTIONAL_CONTRACT", raising=False)
    monkeypatch.delenv("REGENOLD_USER_REF_MINIMALITY", raising=False)


def test_flag_is_an_allow_list(monkeypatch):
    assert count_only_enabled() is False
    for value in ("1", "true", "yes", "on", "ON"):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_enabled() is True
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_enabled() is False


def test_off_renders_nothing_and_the_user_message_is_byte_identical(monkeypatch):
    """The off arm of the gate must be the shipped bytes, exactly."""
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert count_only_block(QUESTION) == ""
    assert calibration_block(QUESTION) == ""
    for value in ("0", "false", "off", ""):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_block(QUESTION) == ""
        assert build_evidence_answer_user(
            QUESTION, "Article 13 obligations..."
        ) == message


def test_block_carries_no_length_clause_at_all(monkeypatch):
    """THE manipulation: budget in, length battery out."""
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    block = count_only_block(QUESTION)
    assert block
    for clause in LENGTH_CLAUSES:
        assert clause not in block, f"length clause leaked into the count-only block: {clause!r}"


def test_block_is_the_budget_and_the_existing_rules_only(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    assert calibration_citation_budget(QUESTION) == 2
    assert calibration_citation_budget(SCENARIO) == 3
    assert "at most 2 provisions" in count_only_block(QUESTION)
    assert "at most 3 provisions" in count_only_block(SCENARIO)
    # The rule-out rule and the citation-order line are shared with the shipped
    # contract; dropping either would contradict ``concise_block``.
    block = count_only_block(QUESTION)
    assert "rules out still counts" in block
    assert "in citation order" in block


def test_shared_clauses_are_byte_identical_to_the_full_block(monkeypatch):
    """The gate compares a REMOVAL, not a re-wording."""
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    count = count_only_block(QUESTION)
    monkeypatch.delenv("REGENOLD_CONCISE_COUNT_ONLY")
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full = calibration_block(QUESTION)
    count_lines = [ln for ln in count.splitlines() if ln.startswith("* COUNT the provisions")]
    full_lines = [ln for ln in full.splitlines() if ln.startswith("* COUNT the provisions")]
    assert count_lines and count_lines == full_lines
    assert "References: at most 2 provisions, in citation order." in count
    assert "References: at most 2 provisions, in citation order." in full


def test_count_only_wins_when_both_flags_are_set(monkeypatch):
    """The full block is the arm this transport REFUTED; a mis-set pair must not
    silently re-run it."""
    assert conciseness_mode() == "off"
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    assert conciseness_mode() == "count"
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert conciseness_mode() == "count"
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)


def test_count_only_does_not_depend_on_the_length_estimator(monkeypatch):
    """No ``answer_need`` and no ``concise_limits`` on the path: a broken length
    estimate must not be able to take the citation budget down with it."""
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))  # noqa: E731
    monkeypatch.setattr("app.engines.answer_need.answer_need", boom)
    monkeypatch.setattr("app.engines.answer_need.concise_limits", boom)
    block = count_only_block(QUESTION)
    assert block
    assert "at most 2 provisions" in block
    # The estimator handed in by the caller is ignored, so passing one changes
    # nothing - which is the mechanical statement of "no length battery".
    assert calibration_block(QUESTION, estimated_need="not a need") == block


def test_fail_soft_on_a_broken_budget(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    monkeypatch.setattr(
        "app.engines.answer_need.is_scenario_question",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert count_only_block(QUESTION) == ""
    assert calibration_block(QUESTION) == ""


def test_block_is_short_and_lands_last_in_the_user_message(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    block = count_only_block(QUESTION)
    assert 0 < len(block) < 400, "the count-only block is three lines by design"
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert block.splitlines()[0] in message
    assert message.rstrip().endswith(block.splitlines()[-1])


def test_the_block_is_additive_to_the_shipped_contract(monkeypatch):
    """Turning the lever on appends the block and changes nothing else."""
    base = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    on = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    block = count_only_block(QUESTION)
    assert on == base + "\n\n" + block


def test_concise_contract_defaults_are_untouched(monkeypatch):
    """This lever moves no other default: R447's ceiling is still the one the
    full block quotes, and the calibration flag is still OFF."""
    assert calibration_enabled() is False
    assert count_only_enabled() is False
    need = answer_need(QUESTION)
    words, sentences = concise_limits(need, QUESTION)
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full = calibration_block(QUESTION, estimated_need=need)
    assert f"keep {sentences} at most" in full
    assert f"about {words} words" in full


def test_both_flags_are_in_the_engine_cache_key():
    """An unkeyed prompt knob serves the wrong cached answer in an A/B."""
    import inspect

    from app.routes import regenold

    source = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_CONCISE_COUNT_ONLY" in source
    assert "REGENOLD_CONCISE_CALIBRATION" in source
