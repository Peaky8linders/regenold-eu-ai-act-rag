"""R460 promotion - ``REGENOLD_CONCISE_CALIBRATION`` allow-list -> default ON.

**NOT APPLIED. The wrapper-transport confirmation REFUSED this promotion** (see
``WRAPPER-CONFIRM.md`` section 4): on the shipped transport the lever reverses
``ans_conciseness`` (-4.49) and drops the board overall (86.90 -> 86.09), while
its citation budget does reproduce (+5.52 ref_conciseness). Kept on disk as the
prepared patch for the count-only successor lever, which keeps this block's
numeric budget and removes its length battery.

Applied only after the wrapper-transport confirmation reproduced the conciseness
direction (see GATE-CONCISENESS-BEDROCK.md + WRAPPER-CONFIRM.md). Mirrors the
house deny-list pattern already used by ``REGENOLD_CONCISE_CONTRACT``: a blank
or unexpected value keeps the ON behaviour, and only ``0``/``false``/``no``/
``off`` render nothing -- in which case the Stage-2 user message is
byte-identical to the pre-lever text.

Idempotent and single-match asserted, because this worktree cannot be edited
through the editor tools.

Run:  ../../.venv/Scripts/python.exe docs/measurements/r460/promote_conciseness_calibration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ANSWER_NEED = REPO / "app" / "engines" / "answer_need.py"
TESTS = REPO / "tests" / "test_r460_conciseness_calibration.py"

try:  # Windows console is cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

OLD_COMMENT = "#: Default OFF: it changes the answer, so it needs its own gate.\n_CALIBRATION_ENV"
NEW_COMMENT = """#: R460 PROMOTION (2026-10-01) - default ON (deny-list), no longer gated off.
#: Promoted on the paired same-judge A/B measured on TWO transports, both n=37
#: (every 3rd official hard row, raw + length-controlled):
#:   * Bedrock leg ``eu.anthropic.claude-opus-4-6-v1`` (inverted transport
#:     contract, both arms alike): ref_conciseness 59.14 -> 63.90 (+4.76,
#:     CI [+0.29,+10.43], McNemar 7/1) -- the only axis whose CI excluded zero;
#:     ans_loose +2.25, ans_conciseness +1.97, ans_strict / ref_loose / tone
#:     flat, overall +0.95, gold heads unchanged. GATE-CONCISENESS-BEDROCK.md
#:   * the SHIPPED transport (Claude Max tunnel, ``claude-opus-5-5``), same
#:     protocol, same judge, same cache: WRAPPER-CONFIRM.md
#: ``REGENOLD_CONCISE_CALIBRATION=0`` restores the pre-lever bytes exactly.
_CALIBRATION_ENV"""

OLD_FN = '''def calibration_enabled() -> bool:
    """``REGENOLD_CONCISE_CALIBRATION`` - allow-list, default OFF."""
    return os.environ.get(_CALIBRATION_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }'''
NEW_FN = '''def calibration_enabled() -> bool:
    """``REGENOLD_CONCISE_CALIBRATION`` - default ON (deny-list), R460 promotion.

    Mirrors :func:`concise_contract_enabled`: a blank or unexpected value keeps
    the ON behaviour and only ``0``/``false``/``no``/``off`` disables the block,
    which then leaves the Stage-2 user message byte-identical to the pre-lever
    text.
    """
    return os.environ.get(_CALIBRATION_ENV, "1").strip().lower() not in _FALSY'''

OLD_DOCSTRING = """``REGENOLD_CONCISE_CALIBRATION`` appends a COUNT-before-you-answer block to the
Stage-2 user message: a sentence ceiling that equals the shipped concise
contract's own ceiling, a numeric citation budget, and a structural skeleton at
the target size. Default OFF, so every assertion here is paired with the
byte-identical-when-off check that the house doctrine requires."""
NEW_DOCSTRING = """``REGENOLD_CONCISE_CALIBRATION`` appends a COUNT-before-you-answer block to the
Stage-2 user message: a sentence ceiling that equals the shipped concise
contract's own ceiling, a numeric citation budget, and a structural skeleton at
the target size.

Default ON after the R460 promotion (deny-list, mirroring
``REGENOLD_CONCISE_CONTRACT``), so the OFF switch is an explicit ``=0`` and the
byte-identical-when-off check the house doctrine requires is taken against
that."""

OLD_FLAG_TEST = '''def test_flag_is_deny_list(monkeypatch):
    assert calibration_enabled() is False
    for value in ("1", "true", "yes", "on", "ON"):
        monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", value)
        assert calibration_enabled() is True
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", value)
        assert calibration_enabled() is False'''
NEW_FLAG_TEST = '''def test_flag_is_deny_list_and_defaults_on(monkeypatch):
    """R460 promotion: the lever ships ON; the env var is the OFF switch.

    Same contract as ``REGENOLD_CONCISE_CONTRACT``: blank and unexpected values
    keep the ON behaviour, so a typo cannot silently disable a lever an
    evidence gate promoted.
    """
    assert calibration_enabled() is True
    for value in ("0", "false", "no", "off", "OFF", "False"):
        monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", value)
        assert calibration_enabled() is False
    for value in ("1", "true", "yes", "on", "banana"):
        monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", value)
        assert calibration_enabled() is True
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "")
    assert calibration_enabled() is True
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION")
    assert calibration_enabled() is True


def test_default_on_renders_the_block_into_the_message():
    """The promotion's whole claim, asserted without touching the env var."""
    assert calibration_enabled() is True
    block = calibration_block(QUESTION)
    assert block.startswith("LENGTH AND CITATION COUNTS")
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert block.splitlines()[0] in message
    assert message.rstrip().endswith(block.splitlines()[-1])'''

OLD_OFF_TEST = '''def test_off_renders_nothing_and_user_message_is_byte_identical(monkeypatch):
    assert calibration_block(QUESTION) == ""
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "0")
    assert calibration_block(QUESTION) == ""
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert build_evidence_answer_user(
        QUESTION, "Article 13 obligations..."
    ) != message'''
NEW_OFF_TEST = '''def test_off_renders_nothing_and_user_message_is_byte_identical(monkeypatch):
    """The OFF switch is an explicit ``=0`` after the R460 promotion."""
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "0")
    assert calibration_block(QUESTION) == ""
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION")
    assert calibration_block(QUESTION) != ""
    assert build_evidence_answer_user(
        QUESTION, "Article 13 obligations..."
    ) != message'''

EDITS: list[tuple[Path, str, str]] = [
    (ANSWER_NEED, OLD_COMMENT, NEW_COMMENT),
    (ANSWER_NEED, OLD_FN, NEW_FN),
    (TESTS, OLD_DOCSTRING, NEW_DOCSTRING),
    (TESTS, OLD_FLAG_TEST, NEW_FLAG_TEST),
    (TESTS, OLD_OFF_TEST, NEW_OFF_TEST),
]


def main() -> int:
    changed = 0
    for path, old, new in EDITS:
        text = path.read_text(encoding="utf-8")
        if new in text and old not in text:
            print(f"already applied: {path.name}")
            continue
        count = text.count(old)
        assert count == 1, f"{path.name}: expected exactly 1 match, found {count}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"patched {path.relative_to(REPO)}")
        changed += 1
    print(f"{changed} file edit(s) applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
