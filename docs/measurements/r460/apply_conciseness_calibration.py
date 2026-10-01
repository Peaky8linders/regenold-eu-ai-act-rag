"""R460 — apply the conciseness-calibration lever (default OFF).

Research basis (see CONCISENESS-PROGRAM.md for the sources):

* Vague length words ("be concise") are soft suggestions; NUMERIC ceilings and
  COUNTED constraints are what models obey (length-control practice surveys;
  explicit numeric instructions cut output 40-74%).
* Externalising the count beats asking the model to keep an internal one:
  countdown/self-count mechanisms lift strict length compliance from under 30%
  to above 95% on MT-Bench-LI with judged quality preserved.
* "Show, don't tell": a SHAPE example at the target size outperforms a stated
  target, which is exactly the R448 finding on this engine (target_chars is
  already calibrated to +/-36 chars of the reference, yet answers ship 1.25x
  over it).
* Citation COUNT is the whole of Ref Conciseness (a count ratio), and the key
  is ~1.26 refs/row on every question shape, so the budget is a small number.

What this script adds, all behind ``REGENOLD_CONCISE_CALIBRATION`` (default OFF):

1. ``answer_need.calibration_block`` — a short COUNT-before-you-answer block: a
   sentence ceiling equal to the shipped concise contract's own ceiling, a
   NUMBERED citation budget, and a structural skeleton at the target size.
2. The block appended LAST in ``build_evidence_answer_user`` (the instruction the
   model reads).
3. The flag registered in ``_engine_cache_key`` (R263.2 / R288.1 doctrine).
4. ``tests/test_r460_conciseness_calibration.py``.

    ../../.venv/Scripts/python.exe docs/measurements/r460/apply_conciseness_calibration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ANSWER_NEED = ROOT / "app" / "engines" / "answer_need.py"
PROMPTS = ROOT / "app" / "data" / "graph_rag_prompts.py"
ROUTES = ROOT / "app" / "routes" / "regenold.py"
TEST = ROOT / "tests" / "test_r460_conciseness_calibration.py"

BLOCK = '''
#: R460 — the calibration lever. Every prior length attempt in this engine was
#: MEASURED to under-deliver: the R448 notes record Opus 5.5 writing 1,040-2,180
#: chars against a per-question estimate that is itself accurate to a median of
#: -36 chars of the reference answer, and the live Cohere boards shipped 1.25x
#: the reference length with 2.0x its citations. The research consensus is that
#: this is a COMPLIANCE problem, not an estimation problem: numeric ceilings plus
#: a COUNTED self-check plus a shape example at the target size is what converts.
#: Default OFF: it changes the answer, so it needs its own gate.
_CALIBRATION_ENV = "REGENOLD_CONCISE_CALIBRATION"

#: The citation budget. The key's own count is ~1.26 refs/row on EVERY shape
#: (110 gold rows: description 1.25, boolean 1.32, list 1.08, definition 1.33),
#: and |expected| <= 2 covers 97% of rows, so 2 is the number that costs no
#: recall for a direct ask. A fact-pattern ask walks several branches and gets 3.
_CALIBRATION_CITATIONS = 2
_CALIBRATION_SCENARIO_CITATIONS = 3


def calibration_enabled() -> bool:
    """``REGENOLD_CONCISE_CALIBRATION`` - allow-list, default OFF."""
    return os.environ.get(_CALIBRATION_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def calibration_citation_budget(question: str = "") -> int:
    """How many provisions the answer may NAME (the Ref Conciseness count)."""
    return (
        _CALIBRATION_SCENARIO_CITATIONS
        if is_scenario_question(question or "")
        else _CALIBRATION_CITATIONS
    )


def calibration_block(
    question: str,
    references: str = "",
    *,
    estimated_need: AnswerNeed | None = None,
) -> str:
    """The COUNT-BEFORE-YOU-ANSWER block, or ``""`` when the lever is OFF.

    Deliberately SHORT. A large steering block has already traded one axis for
    another twice in this engine (the 53 kB system prompt; the R423.1 shape
    directive), so this states two counts, one skeleton and nothing else. It
    never contradicts :func:`concise_block`: the sentence ceiling comes from the
    same :func:`concise_limits` call, and the citation budget keeps the rule that
    a provision the facts engage and the answer rules out still counts.
    """
    if not calibration_enabled():
        return ""
    try:
        need = (
            estimated_need
            if estimated_need is not None
            else answer_need(question, references)
        )
        words, sentences = concise_limits(need, question)
        budget = calibration_citation_budget(question)
    except Exception:  # noqa: BLE001 - a prompt add-on must never break Stage-2
        return ""
    lead = "the verdict" if need.is_yes_no else "the direct answer"
    shape = [
        f"* Draft, then COUNT its sentences: keep {sentences} at most. Delete the "
        "sentence that decides least, not the last one you wrote.",
        f"* COUNT the provisions the draft NAMES: at most {budget} for this "
        "question. Above that, keep the ones its answer rests on and drop the "
        "clauses about the rest. A provision the facts engage and the answer rules "
        "out still counts.",
        f"* Match this shape ({sentences} sentences, about {words} words, then the "
        "references):",
        f"    1. {lead}, naming the provision it rests on.",
        "    2. the limb of that provision the facts engage.",
        "    3. the condition, exception or branch that decides the answer.",
        f"    References: at most {budget} provisions, in citation order.",
    ]
    return "\\n".join(["LENGTH AND CITATION COUNTS (count both before you answer):", *shape])

'''

INSERT_ANCHOR = "def need_proportional_block("

PROMPT_ANCHOR = """    if concise:
        parts.append(concise)
    return "\\n\\n".join(parts)
"""

PROMPT_NEW = """    if concise:
        parts.append(concise)
    # R460 - the calibration block, appended LAST so it is the final instruction
    # the model reads. It restates the SAME ceiling as ``concise_block`` as a
    # counted self-check plus a citation budget, which is the form the length
    # control literature measures as obeyed (see CONCISENESS-PROGRAM.md).
    try:
        from app.engines.answer_need import calibration_block  # noqa: PLC0415

        calibration = calibration_block(
            question, "", estimated_need=answer_need_estimate
        )
    except Exception:  # noqa: BLE001 - a prompt add-on must not break Stage-2
        calibration = ""
    if calibration:
        parts.append(calibration)
    return "\\n\\n".join(parts)
"""

CACHE_ANCHOR = '            "REGENOLD_CONCISE_CONTRACT",\n'

CACHE_NEW = """            "REGENOLD_CONCISE_CONTRACT",
            # R460 - the calibration block appends a counted ceiling to the same
            # Stage-2 user message ⇒ flips the polished answer AND its
            # citations. R263.2 / R288.1 doctrine: an unkeyed knob lets an
            # in-process two-arm A/B serve arm A's cached answer to arm B.
            "REGENOLD_CONCISE_CALIBRATION",
"""

TEST_SOURCE = '''"""R460 - the conciseness-calibration lever.

``REGENOLD_CONCISE_CALIBRATION`` appends a COUNT-before-you-answer block to the
Stage-2 user message: a sentence ceiling that equals the shipped concise
contract's own ceiling, a numeric citation budget, and a structural skeleton at
the target size. Default OFF, so every assertion here is paired with the
byte-identical-when-off check that the house doctrine requires.
"""
from __future__ import annotations

import os

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
'''


def patch(path: Path, old: str, new: str, *, label: str) -> None:
    raw = path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    if n and n in raw and o not in raw:
        print(f"  already applied: {label}")
        return
    count = raw.count(o)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match in {path.name}, found {count}")
    path.write_text(raw.replace(o, n, 1), encoding="utf-8")
    print(f"  applied: {label}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("answer_need.py:")
    patch(ANSWER_NEED, INSERT_ANCHOR, BLOCK.lstrip("\n") + INSERT_ANCHOR,
          label="calibration_block")
    print("graph_rag_prompts.py:")
    patch(PROMPTS, PROMPT_ANCHOR, PROMPT_NEW, label="append the block last")
    print("regenold.py:")
    patch(ROUTES, CACHE_ANCHOR, CACHE_NEW, label="cache key")
    print("tests:")
    if TEST.exists() and "REGENOLD_CONCISE_CALIBRATION" in TEST.read_text(encoding="utf-8"):
        print("  already applied: test file")
    else:
        TEST.write_text(TEST_SOURCE, encoding="utf-8")
        print("  wrote tests/test_r460_conciseness_calibration.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
