"""R461 PROMOTION — ``REGENOLD_CONCISE_COUNT_ONLY`` is default ON.

The lever's own suite (`test_r461_count_only_concise.py`) pins what the block
RENDERS; this file pins what the PROMOTION did, which is a different set of
claims:

* the default moved, and only that default: no env means the block is in force
  and reaches the Stage-2 user message;
* the OFF switch is a DENY-LIST, so a typo cannot silently disable a shipped
  lever, and the kill switch is byte-identical to the pre-lever text;
* the full R460 block did not become reachable by accident — it is the explicit
  pair, and count-only still wins a mis-set one;
* the cache key carries the RESOLVED mode, which is what makes the flip
  invalidate the pre-promotion cache instead of serving its block-OFF answers
  (an unset env contributes the empty string to the raw-spelling blob both
  before and after the flip — the R263.2 stale-hit class);
* the two gates' launchers NAME their arms, because after the flip "flags
  absent" is no longer the OFF arm and a re-run would compare the block against
  itself.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from app.data.graph_rag_prompts import build_evidence_answer_user
from app.engines.answer_need import (
    calibration_block,
    calibration_enabled,
    conciseness_mode,
    count_only_block,
    count_only_enabled,
)

REPO = Path(__file__).resolve().parents[1]
QUESTION = "What transparency obligations does Article 13 impose on providers?"
SCENARIO = (
    "A hospital deploys an AI system to triage patients in its emergency "
    "department and asks which obligations bind it as a high-risk deployer."
)

#: The promoted flag and everything it outranks, cleared per test.
PROMOTION_ENV = "REGENOLD_CONCISE_COUNT_ONLY"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(PROMOTION_ENV, raising=False)
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION", raising=False)


def test_the_default_is_on_and_the_block_reaches_the_message():
    """No env at all: the promotion's whole point."""
    assert count_only_enabled() is True
    assert conciseness_mode() == "count"
    block = count_only_block(QUESTION)
    assert block.startswith("CITATION COUNT (count the provisions before you answer):")
    assert "at most 2 provisions" in block
    assert build_evidence_answer_user(QUESTION, "Article 13 obligations...").rstrip().endswith(
        block.splitlines()[-1]
    )


def test_the_kill_switch_is_a_deny_list_not_an_allow_list(monkeypatch):
    """A malformed value must not be able to disable a shipped lever."""
    for value in ("0", "false", "no", "off", "FALSE", " off ", "Off"):
        monkeypatch.setenv(PROMOTION_ENV, value)
        assert count_only_enabled() is False, value
        assert conciseness_mode() == "off"
    for value in ("1", "true", "yes", "on", "", "  ", "banana", "0.0"):
        monkeypatch.setenv(PROMOTION_ENV, value)
        assert count_only_enabled() is True, value
        assert conciseness_mode() == "count"


def test_the_kill_switch_is_byte_identical_to_the_pre_lever_message(monkeypatch):
    """The rollback must not leave anything behind on the wire."""
    monkeypatch.setenv(PROMOTION_ENV, "0")
    killed = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert count_only_block(QUESTION) == ""
    assert calibration_block(QUESTION) == ""
    assert "CITATION COUNT" not in killed
    for value in ("0", "false", "no", "off"):
        monkeypatch.setenv(PROMOTION_ENV, value)
        assert build_evidence_answer_user(QUESTION, "Article 13 obligations...") == killed


def test_a_flag_read_that_raises_keeps_the_promoted_default(monkeypatch):
    """Fail-soft points at the PROMOTED state: an exception must not disable it."""

    class _Exploding(dict):
        def get(self, *_args, **_kwargs):  # noqa: D102 - test double
            raise RuntimeError("boom")

    monkeypatch.setattr(os, "environ", _Exploding())
    assert count_only_enabled() is True


def test_the_full_block_is_the_explicit_pair_and_count_only_outranks_it(monkeypatch):
    """Keep the refuted arm reachable without letting it onto the wire by accident."""
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert conciseness_mode() == "count"  # the mis-set pair
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)

    monkeypatch.setenv(PROMOTION_ENV, "0")
    assert conciseness_mode() == "full"
    full = calibration_block(QUESTION)
    assert "LENGTH AND CITATION" in full
    assert "at most 2 provisions" in full  # the same budget both blocks share

    monkeypatch.setenv(PROMOTION_ENV, "1")
    assert conciseness_mode() == "count"


def test_the_promotion_moved_no_other_default(monkeypatch):
    assert calibration_enabled() is False
    monkeypatch.setenv(PROMOTION_ENV, "0")
    assert calibration_enabled() is False
    assert conciseness_mode() == "off"


def test_budget_and_shape_survive_the_promotion():
    """The promoted block is the gated one: budget per shape, no length battery."""
    assert "at most 2 provisions" in count_only_block(QUESTION)
    assert "at most 3 provisions" in count_only_block(SCENARIO)
    assert 0 < len(count_only_block(QUESTION)) < 400
    for clause in ("sentences", "words", "Match this shape", "Delete the sentence"):
        assert clause not in count_only_block(QUESTION)


# --------------------------------------------------------------------------- #
# the cache key: the flip must invalidate, and the arms must stay distinct
# --------------------------------------------------------------------------- #
def _key(question: str = QUESTION) -> str:
    from app.routes import regenold

    return regenold._engine_cache_key(question, None)


def test_the_key_carries_the_resolved_mode_not_only_the_raw_spelling():
    """The term that makes the promotion invalidate anything at all."""
    from app.routes import regenold

    source = inspect.getsource(regenold._engine_cache_key)
    assert "conciseness_mode" in source
    assert "|concise=" in source
    assert PROMOTION_ENV in source  # operator intent still tracked, raw


def test_the_promotion_changes_the_cache_key(monkeypatch):
    """Unset vs killed must never share an entry: that IS the invalidation."""
    default_key = _key()
    monkeypatch.setenv(PROMOTION_ENV, "0")
    killed_key = _key()
    assert default_key != killed_key

    monkeypatch.setenv(PROMOTION_ENV, "1")
    assert _key() != killed_key


def test_the_full_block_and_the_off_state_are_distinct_cache_regimes(monkeypatch):
    monkeypatch.setenv(PROMOTION_ENV, "0")
    off_key = _key()
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full_key = _key()
    assert off_key != full_key


def test_the_key_is_stable_for_the_promoted_default(monkeypatch):
    """Same regime, same key — twice, and across a function rebuild."""
    first = _key()
    assert _key() == first
    assert os.environ.get(PROMOTION_ENV) is None


# --------------------------------------------------------------------------- #
# the gates' arms are named, not implied
# --------------------------------------------------------------------------- #
def test_the_gate_launchers_name_their_arms():
    """A default flip silently redefines "flags absent" as the ON arm.

    Both gate launchers used to define arm A as "flags absent", which after the
    promotion renders the block — the gate would have measured the block against
    itself. The OFF arm is now the kill switch on both.
    """
    count_gate = (REPO / "docs" / "measurements" / "r461" / "run_gate_count_only.sh").read_text(
        encoding="utf-8"
    )
    assert f"{PROMOTION_ENV}=0 $PY" in count_gate
    assert f"{PROMOTION_ENV}=1 $PY" in count_gate
    assert "flags absent" not in count_gate

    wrapper_gate = (REPO / "docs" / "measurements" / "r460" / "run_gate_wrapper.sh").read_text(
        encoding="utf-8"
    )
    assert f"{PROMOTION_ENV}=0 $PY" in wrapper_gate
    assert f"{PROMOTION_ENV}=0 REGENOLD_CONCISE_CALIBRATION=1 $PY" in wrapper_gate


def test_the_promotion_record_and_rollback_are_on_disk():
    """A promotion with no recorded rollback is an incident waiting to happen."""
    record = (REPO / "docs" / "measurements" / "r461" / "PROMOTION.md").read_text(
        encoding="utf-8"
    )
    assert f"{PROMOTION_ENV}=0" in record
    assert "Rollback" in record or "rollback" in record
