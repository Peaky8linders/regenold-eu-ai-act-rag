"""R461 — apply the COUNT-ONLY conciseness lever (default OFF).

Why this exists
---------------
The R460 wrapper gate (`docs/measurements/r460/WRAPPER-CONFIRM.md`) refused the
calibration block on the transport that ships, but its two halves did not behave
alike. The counted CITATION BUDGET reproduced on both transports
(ref_conciseness +5.52 pp on the Claude Max wrapper, +4.76 pp on Bedrock, the
only axis whose CI excluded zero in either gate) while the LENGTH BATTERY
(sentence ceiling, word ceiling, shape skeleton) helped on `opus-4-6` and made
the answer *longer* on `opus-5-5` (-4.49 pp ans_conciseness).

So this script separates them: same numeric budget, same rule-out rule, same
citation-order line, and **no length clause of any kind** — no sentence count, no
word count, no shape skeleton, no ``concise_limits()`` call at all. The variant
is gated on its own against the same Shipped transport.

What it changes
---------------
1. ``answer_need._COUNT_ONLY_ENV`` = ``REGENOLD_CONCISE_COUNT_ONLY``, an
   allow-list flag, default OFF (every R460 lever's convention).
2. ``answer_need.count_only_enabled()`` and ``answer_need.conciseness_mode()``.
3. ``answer_need.count_only_block()`` — the three-line count block.
4. ``answer_need.calibration_block()`` dispatches on the mode. The two clauses it
   shares with the full block are factored into ``_COUNT_CLAUSE`` /
   ``_REFERENCES_CLAUSE`` so the ONLY difference between the two arms is which
   clauses are emitted, not a re-worded equivalent. The full block's rendering is
   byte-identical to R460's (asserted by the R460 suite, which is left untouched).
5. ``REGENOLD_CONCISE_COUNT_ONLY`` registered in ``_engine_cache_key``
   (R263.2 / R288.1 doctrine: an unkeyed prompt knob poisons an in-process A/B).
6. ``tests/test_r461_count_only_concise.py``.

    ../../.venv/Scripts/python.exe docs/measurements/r461/apply_count_only.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ANSWER_NEED = ROOT / "app" / "engines" / "answer_need.py"
ROUTES = ROOT / "app" / "routes" / "regenold.py"
TEST = ROOT / "tests" / "test_r461_count_only_concise.py"

# --------------------------------------------------------------------------- #
# answer_need.py — the flag, the mode, the shared clauses
# --------------------------------------------------------------------------- #

KNOB_ANCHOR = '''_CALIBRATION_CITATIONS = 2
_CALIBRATION_SCENARIO_CITATIONS = 3
'''

KNOB_NEW = '''_CALIBRATION_CITATIONS = 2
_CALIBRATION_SCENARIO_CITATIONS = 3

#: R461 - the COUNT-ONLY variant. The R460 wrapper gate (``WRAPPER-CONFIRM.md``)
#: split the block above into two halves that behaved differently on the model
#: that ships: the counted citation budget reproduced on BOTH transports
#: (+5.52 pp ref_conciseness on the wrapper, +4.76 pp on Bedrock) while the length
#: battery (sentence ceiling, word ceiling, shape skeleton) helped on opus-4-6 and
#: made the answer LONGER on opus-5-5 (-4.49 pp ans_conciseness). So the budget is
#: re-gated ALONE, with no length clause of any kind, on the shipped transport.
#: Default OFF and an allow-list like every R460 lever: it changes the answer, so
#: it needs its own gate.
_COUNT_ONLY_ENV = "REGENOLD_CONCISE_COUNT_ONLY"

#: The clauses the full block and the count-only variant SHARE. Factored so the
#: difference between the two gated arms is exactly "which clauses are emitted"
#: and never an accidental re-wording of the same instruction. ``{budget}`` is
#: filled per question. Byte-identical to the R460 full block's own text, which
#: the R460 suite pins.
_COUNT_CLAUSE = (
    "* COUNT the provisions the draft NAMES: at most {budget} for this "
    "question. Above that, keep the ones its answer rests on and drop the "
    "clauses about the rest. A provision the facts engage and the answer rules "
    "out still counts."
)
_REFERENCES_CLAUSE = "References: at most {budget} provisions, in citation order."
'''

MODE_ANCHOR = '''def calibration_enabled() -> bool:
    """``REGENOLD_CONCISE_CALIBRATION`` - allow-list, default OFF."""
    return os.environ.get(_CALIBRATION_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }
'''

MODE_NEW = '''def calibration_enabled() -> bool:
    """``REGENOLD_CONCISE_CALIBRATION`` - allow-list, default OFF."""
    return os.environ.get(_CALIBRATION_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def count_only_enabled() -> bool:
    """``REGENOLD_CONCISE_COUNT_ONLY`` - allow-list, default OFF."""
    return os.environ.get(_COUNT_ONLY_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def conciseness_mode() -> str:
    """Which calibration block renders: ``"off"``, ``"count"`` or ``"full"``.

    COUNT-ONLY WINS when both flags are set. The two blocks are alternatives, not
    layers - the full one is the arm whose paired verdict was negative on this
    transport - so a mis-set pair must not silently re-run the refuted arm.
    """
    if count_only_enabled():
        return "count"
    if calibration_enabled():
        return "full"
    return "off"
'''

DOC_ANCHOR = '''    """The COUNT-BEFORE-YOU-ANSWER block, or ``""`` when the lever is OFF.

    Deliberately SHORT. A large steering block has already traded one axis for
'''

DOC_NEW = '''    """The COUNT-BEFORE-YOU-ANSWER block, or ``""`` when the lever is OFF.

    Dispatches on :func:`conciseness_mode`: ``"count"`` renders
    :func:`count_only_block` (the R461 variant - citation budget only), ``"full"``
    renders the R460 block below, ``"off"`` renders nothing.

    Deliberately SHORT. A large steering block has already traded one axis for
'''

BODY_ANCHOR = '''    if not calibration_enabled():
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

BODY_NEW = '''    mode = conciseness_mode()
    if mode == "count":
        return count_only_block(question)
    if mode == "off":
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
        _COUNT_CLAUSE.format(budget=budget),
        f"* Match this shape ({sentences} sentences, about {words} words, then the "
        "references):",
        f"    1. {lead}, naming the provision it rests on.",
        "    2. the limb of that provision the facts engage.",
        "    3. the condition, exception or branch that decides the answer.",
        f"    {_REFERENCES_CLAUSE.format(budget=budget)}",
    ]
    return "\\n".join(["LENGTH AND CITATION COUNTS (count both before you answer):", *shape])


def count_only_block(question: str = "") -> str:
    """The CITATION-COUNT-only block, or ``""`` when the knob is OFF.

    R461. The half of the R460 calibration block that survived TWO transports: a
    numeric budget on the provisions the answer may NAME, the rule that a
    provision the facts engage and the answer rules out still counts, and the
    citation-order line - and nothing else.

    It deliberately calls NEITHER :func:`answer_need` NOR :func:`concise_limits`,
    so the length battery cannot leak back in and a broken length estimate cannot
    take the citation budget down with it. Same fail-soft rule as the full block:
    a prompt add-on must never break Stage-2.
    """
    if not count_only_enabled():
        return ""
    try:
        budget = calibration_citation_budget(question)
    except Exception:  # noqa: BLE001 - a prompt add-on must never break Stage-2
        return ""
    return "\\n".join([
        "CITATION COUNT (count the provisions before you answer):",
        _COUNT_CLAUSE.format(budget=budget),
        f"* {_REFERENCES_CLAUSE.format(budget=budget)}",
    ])
'''

# --------------------------------------------------------------------------- #
# routes/regenold.py — the cache key
# --------------------------------------------------------------------------- #

CACHE_ANCHOR = '''            # in-process two-arm A/B serve arm A's cached answer to arm B.
            "REGENOLD_CONCISE_CALIBRATION",
'''

CACHE_NEW = '''            # in-process two-arm A/B serve arm A's cached answer to arm B.
            "REGENOLD_CONCISE_CALIBRATION",
            # R461 — the count-only variant of that same block. It renders a
            # DIFFERENT block (the citation budget alone, no length battery and no
            # skeleton) and takes precedence when both are set, so an A/B that
            # flips it must never replay the other arm's cached answer.
            "REGENOLD_CONCISE_COUNT_ONLY",
'''

TEST_SOURCE = '''"""R461 - the COUNT-ONLY conciseness lever.

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
    assert on == base + "\\n\\n" + block


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
    patch(ANSWER_NEED, KNOB_ANCHOR, KNOB_NEW, label="_COUNT_ONLY_ENV + shared clauses")
    patch(ANSWER_NEED, MODE_ANCHOR, MODE_NEW, label="count_only_enabled / conciseness_mode")
    patch(ANSWER_NEED, DOC_ANCHOR, DOC_NEW, label="calibration_block docstring")
    patch(ANSWER_NEED, BODY_ANCHOR, BODY_NEW, label="dispatch + count_only_block")
    print("regenold.py:")
    patch(ROUTES, CACHE_ANCHOR, CACHE_NEW, label="cache key")
    print("tests:")
    if TEST.exists() and "REGENOLD_CONCISE_COUNT_ONLY" in TEST.read_text(encoding="utf-8"):
        print("  already applied: test file")
    else:
        TEST.write_text(TEST_SOURCE, encoding="utf-8")
        print("  wrote tests/test_r461_count_only_concise.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
