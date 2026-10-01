"""R460 - the conciseness-calibration lever.

``REGENOLD_CONCISE_CALIBRATION`` appends a COUNT-before-you-answer block to the
Stage-2 user message: a sentence ceiling that equals the shipped concise
contract's own ceiling, a numeric citation budget, and a structural skeleton at
the target size. Default OFF, so every assertion here is paired with the
byte-identical-when-off check that the house doctrine requires.
"""
from __future__ import annotations

import pytest

from app.data.graph_rag_prompts import build_evidence_answer_user
from app.engines.answer_need import (
    answer_need,
    calibration_block,
    calibration_citation_budget,
    calibration_enabled,
    concise_limits,
)

QUESTION = "What transparency obligations does Article 13 impose on providers?"
SCENARIO = (
    "A hospital deploys an AI system to triage patients in its emergency "
    "department and asks which obligations bind it as a high-risk deployer."
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION", raising=False)
    monkeypatch.delenv("REGENOLD_CONCISE_CONTRACT", raising=False)
    monkeypatch.delenv("REGENOLD_NEED_PROPORTIONAL_CONTRACT", raising=False)
    monkeypatch.delenv("REGENOLD_USER_REF_MINIMALITY", raising=False)
    monkeypatch.delenv("REGENOLD_PROMPT_V2", raising=False)
    monkeypatch.delenv("REGENOLD_PROMPT_V3", raising=False)


def test_flag_is_deny_list(monkeypatch):
    assert calibration_enabled() is False
    for value in ("1", "true", "yes", "on", "ON"):
        monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", value)
        assert calibration_enabled() is True
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", value)
        assert calibration_enabled() is False


def test_off_renders_nothing_and_user_message_is_byte_identical(monkeypatch):
    assert calibration_block(QUESTION) == ""
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "0")
    assert calibration_block(QUESTION) == ""
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert build_evidence_answer_user(
        QUESTION, "Article 13 obligations..."
    ) != message


def test_ceiling_matches_the_shipped_concise_contract(monkeypatch):
    """The calibration ceiling is the concise contract's own ceiling, never a
    second, contradictory one."""
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    need = answer_need(QUESTION)
    words, sentences = concise_limits(need, QUESTION)
    block = calibration_block(QUESTION, estimated_need=need)
    assert f"keep {sentences} at most" in block
    assert f"about {words} words" in block


def test_citation_budget_is_the_key_count(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert calibration_citation_budget(QUESTION) == 2
    assert calibration_citation_budget(SCENARIO) == 3
    assert "at most 2 provisions" in calibration_block(QUESTION)
    assert "at most 3 provisions" in calibration_block(SCENARIO)


def test_block_never_drops_the_rule_out_rule(monkeypatch):
    """A ruled-out provision still counts, matching ``concise_block``."""
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    block = calibration_block(QUESTION)
    assert "rules out still counts" in block


def test_block_is_short_and_lands_in_the_user_message(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    block = calibration_block(QUESTION)
    assert len(block) < 1400, "a steering block this long has traded axes before"
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert block.splitlines()[0] in message
    assert message.rstrip().endswith(block.splitlines()[-1])


def test_flag_is_in_the_engine_cache_key():
    """An unkeyed prompt knob serves the wrong cached answer in an A/B."""
    import inspect

    from app.routes import regenold

    source = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_CONCISE_CALIBRATION" in source


def test_fail_soft_on_a_broken_estimator(monkeypatch):
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    monkeypatch.setattr(
        "app.engines.answer_need.concise_limits",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert calibration_block(QUESTION) == ""
