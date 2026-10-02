"""R461 promotion - ``REGENOLD_CONCISE_COUNT_ONLY`` allow-list -> default ON.

APPLIED 2026-10-01, after the round's own hard gate met every pre-registered
target once hard rule #8 was read on the rows the lever actually served
(``COUNT-ONLY-CONFIRM.md`` §5.1/§6, ``RULE8-SCOPE-REREAD.md``), and after the
live canary on the published endpoint (``PROMOTION.md``):

* ref_conciseness 56.62 -> 64.31 (+7.69, CI [+1.41, +15.05], McNemar 10/2
  p=0.0386) — the count mechanism's third reproduction (+5.52 wrapper, +4.76
  Bedrock);
* answer axes flat to +0.00, ans_conciseness +0.10 where the FULL block lost
  4.49, answers +6.6 chars where the full block added 64.0;
* overall +3.80 [+0.58, +9.01] on 20/35 rows, against a noise floor of -0.56
  [-6.99, +5.79] measured on byte-identical prompts;
* no gold head dropped on any row the block served (the one drop was a
  transport-degraded row, excluded and reported by the fixed rule).

Three mechanical consequences of the flip, all of them in this patch:

1. **Deny-list, not allow-list.** A blank or malformed value keeps the ON
   behaviour, so no typo can silently disable a shipped lever; only
   ``0``/``false``/``no``/``off`` render nothing, and that path is
   byte-identical to the pre-lever Stage-2 user message (asserted).
2. **Cache invalidation.** ``_engine_cache_key`` folded only the RAW env spelling
   (empty when unset), so after the flip an entry cached with the block OFF would
   still match a block-ON question — the R263.2 stale-hit class with the
   promotion itself as the flip. The RESOLVED ``conciseness_mode()`` is now in
   ``flag_bits``, which invalidates the pre-promotion cache wholesale (the
   R81-N.1 effect, deliberately) and also covers the count/full/off precedence.
3. **The full block is now the explicit pair.** ``count_only`` wins when both
   flags are set (R461, unchanged), so with the default ON the R460 full block is
   reachable only as ``REGENOLD_CONCISE_COUNT_ONLY=0
   REGENOLD_CONCISE_CALIBRATION=1`` — which is the correct reading of a refuted
   arm, and is pinned by test. The R460 suite's autouse fixture therefore kills
   the promoted block, so every test in it still selects the R460 arm rather than
   silently measuring the count block.
4. **The arms on disk become explicit.** ``run_gate_wrapper.sh`` and
   ``run_gate_count_only.sh`` defined their OFF arms as "flags absent", which
   after the flip means the block is IN FORCE: re-running either gate would have
   compared the block against itself. Both launchers now name every flag
   (``=0`` for the OFF arm), so the recorded arm definitions stay reproducible.

Rollback: set ``REGENOLD_CONCISE_COUNT_ONLY=0`` in the deploy environment. It is
one variable, needs no redeploy of code, and restores the pre-lever bytes.

Idempotent and single-match asserted, because this worktree cannot be edited
through the editor tools.

Run:  ../../.venv/Scripts/python.exe docs/measurements/r461/promote_count_only.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ANSWER_NEED = REPO / "app" / "engines" / "answer_need.py"
ROUTES = REPO / "app" / "routes" / "regenold.py"
TESTS = REPO / "tests" / "test_r461_count_only_concise.py"

try:  # Windows console is cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# --------------------------------------------------------------------------- #
# 1. the flag: allow-list default OFF -> deny-list default ON
# --------------------------------------------------------------------------- #
OLD_COMMENT = """#: Default OFF and an allow-list like every R460 lever: it changes the answer, so
#: it needs its own gate.
_COUNT_ONLY_ENV = "REGENOLD_CONCISE_COUNT_ONLY\""""

NEW_COMMENT = """#: R461 PROMOTION (2026-10-01) - default ON (deny-list), promoted on evidence, not
#: on argument. The paired hard gate on the SHIPPED transport
#: (``COUNT-ONLY-CONFIRM.md``), read under hard rule #8's fixed operating
#: definition (the rows the lever actually served): ref_conciseness 56.62 ->
#: 64.31 (+7.69, CI [+1.41, +15.05], McNemar 10/2 p=0.0386), ans_correctness
#: flat to +0.00, ans_conciseness +0.10 where the full block lost 4.49, answers
#: +6.6 chars where the full block added 64.0, overall +3.80 [+0.58, +9.01]
#: against a noise floor of -0.56 [-6.99, +5.79] on byte-identical prompts: five
#: of five pre-registered targets, and no gold head dropped on any row the block
#: served. ``REGENOLD_CONCISE_COUNT_ONLY=0`` restores the pre-lever bytes exactly
#: and is the rollback; the live evidence is ``docs/measurements/r461/PROMOTION.md``.
_COUNT_ONLY_ENV = "REGENOLD_CONCISE_COUNT_ONLY\""""

OLD_FN = '''def count_only_enabled() -> bool:
    """``REGENOLD_CONCISE_COUNT_ONLY`` - allow-list, default OFF."""
    return os.environ.get(_COUNT_ONLY_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }'''

NEW_FN = '''def count_only_enabled() -> bool:
    """``REGENOLD_CONCISE_COUNT_ONLY`` - default ON (deny-list), R461 promotion.

    Mirrors :func:`need_proportional_contract_enabled`: a blank or unexpected
    value keeps the ON behaviour, so a malformed value cannot silently disable a
    shipped lever, and only ``0``/``false``/``no``/``off`` render nothing - which
    leaves the Stage-2 user message byte-identical to the pre-lever text.

    Promoted on the round's own hard gate (see the constant above). The RESOLVED
    mode is keyed in ``_engine_cache_key``, so the flip invalidates the
    pre-promotion cache rather than serving its block-OFF answers.
    """
    try:
        return os.environ.get(_COUNT_ONLY_ENV, "1").strip().lower() not in _FALSY
    except Exception:  # noqa: BLE001 - a flag read must never break the route
        return True'''

OLD_MODE_DOC = '''    """Which calibration block renders: ``"off"``, ``"count"`` or ``"full"``.

    COUNT-ONLY WINS when both flags are set. The two blocks are alternatives, not
    layers - the full one is the arm whose paired verdict was negative on this
    transport - so a mis-set pair must not silently re-run the refuted arm.
    """'''

NEW_MODE_DOC = '''    """Which calibration block renders: ``"off"``, ``"count"`` or ``"full"``.

    COUNT-ONLY WINS when both flags are set. The two blocks are alternatives, not
    layers - the full one is the arm whose paired verdict was negative on this
    transport - so a mis-set pair must not silently re-run the refuted arm. After
    the R461 promotion (count-only default ON) that precedence is what keeps the
    refuted arm off the wire: it is reachable only as the explicit pair
    ``REGENOLD_CONCISE_COUNT_ONLY=0 REGENOLD_CONCISE_CALIBRATION=1``, and it is
    keyed as ``concise=full``. This function is the cache key's own term for the
    promotion: the raw env spelling is empty both before and after the flip.
    """'''

# --------------------------------------------------------------------------- #
# 2. the cache key: the RESOLVED mode, not just the raw spelling
# --------------------------------------------------------------------------- #
OLD_TUPLE_ENTRY = """            # R461 — the count-only variant of that same block. It renders a
            # DIFFERENT block (the citation budget alone, no length battery and no
            # skeleton) and takes precedence when both are set, so an A/B that
            # flips it must never replay the other arm's cached answer.
            "REGENOLD_CONCISE_COUNT_ONLY","""

NEW_TUPLE_ENTRY = """            # R461 — the count-only variant of that same block. It renders a
            # DIFFERENT block (the citation budget alone, no length battery and no
            # skeleton) and takes precedence when both are set, so an A/B that
            # flips it must never replay the other arm's cached answer. This
            # entry tracks the operator's RAW spelling; since the R461 promotion
            # the value is empty both before and after the default flip, so the
            # invalidation that flip requires comes from the RESOLVED mode keyed
            # in ``flag_bits`` below.
            "REGENOLD_CONCISE_COUNT_ONLY","""

OLD_FLAG_BITS = """    hypa_bits = f"{int(is_adaptive_router_enabled())}{int(is_rrf_retrieval_enabled())}"
    flag_bits = ("""

NEW_FLAG_BITS = """    hypa_bits = f"{int(is_adaptive_router_enabled())}{int(is_rrf_retrieval_enabled())}"
    # R461 PROMOTION — the conciseness block's RESOLVED mode belongs in the key,
    # not only the raw env spelling. ``engine_flags`` below folds raw values (so
    # an unset flag contributes ""), which means a DEFAULT FLIP is invisible to
    # it: an entry cached pre-promotion with the block OFF would answer a
    # block-ON request for the same question — the R263.2 stale-hit class, with
    # the promotion itself as the flip. Keying the resolved mode invalidates the
    # pre-promotion cache wholesale (the R81-N.1 effect, deliberately), keeps a
    # rolled-back build distinct from a promoted one, and covers the
    # count/full/off precedence as well.
    from app.engines.answer_need import conciseness_mode as _conciseness_mode  # noqa: PLC0415
    flag_bits = ("""

OLD_FLAG_TAIL = """        f"|bedrock_wrapper_fallback={int(_bedrock_wrapper_fallback)}"
    )"""

NEW_FLAG_TAIL = """        f"|bedrock_wrapper_fallback={int(_bedrock_wrapper_fallback)}"
        # R461 — 'off' | 'count' | 'full', resolved (see the comment above).
        f"|concise={_conciseness_mode()}"
    )"""

# --------------------------------------------------------------------------- #
# 3. the tests that pinned the pre-promotion default
# --------------------------------------------------------------------------- #
OLD_DOC_HEADER = """Default OFF: the flag is an allow-list, so every rendering
assertion is paired with the byte-identical-when-off check the house doctrine
requires.
\"\"\""""

NEW_DOC_HEADER = """Default ON since the R461 promotion (deny-list), so the
byte-identical-when-off check the house doctrine requires is taken against the
explicit ``=0`` kill switch, and the default itself is pinned. The promotion's own
contract - the resolved mode in the cache key, the full block's new reachability -
is pinned in ``test_r461_count_only_promoted.py``.
\"\"\""""

OLD_FLAG_TEST = '''def test_flag_is_an_allow_list(monkeypatch):
    assert count_only_enabled() is False
    for value in ("1", "true", "yes", "on", "ON"):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_enabled() is True
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_enabled() is False'''

NEW_FLAG_TEST = '''def test_flag_is_a_deny_list_and_defaults_on(monkeypatch):
    """Promoted: no env means ON, and only a falsy value turns it off."""
    assert count_only_enabled() is True
    for value in ("0", "false", "no", "off", "FALSE", " off "):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_enabled() is False
    for value in ("1", "true", "yes", "on", "", "banana"):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_enabled() is True'''

OLD_OFF_TEST = '''def test_off_renders_nothing_and_the_user_message_is_byte_identical(monkeypatch):
    """The off arm of the gate must be the shipped bytes, exactly."""
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert count_only_block(QUESTION) == ""
    assert calibration_block(QUESTION) == ""
    for value in ("0", "false", "off", ""):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_block(QUESTION) == ""
        assert build_evidence_answer_user(
            QUESTION, "Article 13 obligations..."
        ) == message'''

NEW_OFF_TEST = '''def test_the_kill_switch_renders_nothing_and_the_bytes_are_the_shipped_ones(monkeypatch):
    """The rollback must be the pre-lever bytes, exactly."""
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")
    message = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    assert count_only_block(QUESTION) == ""
    assert calibration_block(QUESTION) == ""
    assert conciseness_mode() == "off"
    for value in ("0", "false", "no", "off"):
        monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", value)
        assert count_only_block(QUESTION) == ""
        assert build_evidence_answer_user(
            QUESTION, "Article 13 obligations..."
        ) == message'''

OLD_SHARED_HEAD = '''    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    count = count_only_block(QUESTION)
    monkeypatch.delenv("REGENOLD_CONCISE_COUNT_ONLY")
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full = calibration_block(QUESTION)'''

NEW_SHARED_HEAD = '''    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    count = count_only_block(QUESTION)
    # The full block is reachable only as the explicit pair after the promotion:
    # count-only is ON by default, so the kill switch has to come first.
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full = calibration_block(QUESTION)'''

OLD_WINS_HEAD = '''    assert conciseness_mode() == "off"
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    assert conciseness_mode() == "count"
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert conciseness_mode() == "count"
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)'''

NEW_WINS_HEAD = '''    assert conciseness_mode() == "count"  # promoted default, no env set at all
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    assert conciseness_mode() == "count"
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    assert conciseness_mode() == "count"
    assert "LENGTH AND CITATION" not in calibration_block(QUESTION)
    # The refuted arm is still reachable, but only as an explicit pair.
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")
    assert conciseness_mode() == "full"
    assert "LENGTH AND CITATION" in calibration_block(QUESTION)'''

OLD_ADDITIVE = '''    base = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "1")
    on = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    block = count_only_block(QUESTION)
    assert on == base + "\\n\\n" + block'''

NEW_ADDITIVE = '''    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")
    base = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    monkeypatch.delenv("REGENOLD_CONCISE_COUNT_ONLY")
    on = build_evidence_answer_user(QUESTION, "Article 13 obligations...")
    block = count_only_block(QUESTION)
    assert on == base + "\\n\\n" + block'''

OLD_DEFAULTS = '''def test_concise_contract_defaults_are_untouched(monkeypatch):
    """This lever moves no other default: R447's ceiling is still the one the
    full block quotes, and the calibration flag is still OFF."""
    assert calibration_enabled() is False
    assert count_only_enabled() is False
    need = answer_need(QUESTION)
    words, sentences = concise_limits(need, QUESTION)
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full = calibration_block(QUESTION, estimated_need=need)'''

NEW_DEFAULTS = '''def test_the_promotion_moves_one_default_and_no_other(monkeypatch):
    """Count-only ON, the refuted full block still OFF, and R447's ceiling still
    the one that block quotes."""
    assert count_only_enabled() is True
    assert calibration_enabled() is False
    need = answer_need(QUESTION)
    words, sentences = concise_limits(need, QUESTION)
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")
    monkeypatch.setenv("REGENOLD_CONCISE_CALIBRATION", "1")
    full = calibration_block(QUESTION, estimated_need=need)'''

OLD_KEY_TEST = '''def test_both_flags_are_in_the_engine_cache_key():
    """An unkeyed prompt knob serves the wrong cached answer in an A/B."""
    import inspect

    from app.routes import regenold

    source = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_CONCISE_COUNT_ONLY" in source
    assert "REGENOLD_CONCISE_CALIBRATION" in source'''

NEW_KEY_TEST = '''def test_both_flags_and_the_resolved_mode_are_in_the_engine_cache_key():
    """An unkeyed prompt knob serves the wrong cached answer in an A/B — and after
    the promotion the RESOLVED mode is the term that makes the flip invalidate,
    because the raw spelling is empty both before and after it."""
    import inspect

    from app.routes import regenold

    source = inspect.getsource(regenold._engine_cache_key)
    assert "REGENOLD_CONCISE_COUNT_ONLY" in source
    assert "REGENOLD_CONCISE_CALIBRATION" in source
    assert "conciseness_mode" in source
    assert "|concise=" in source'''

# --------------------------------------------------------------------------- #
# 4. the R460 suite: its arm is now an explicit pair
# --------------------------------------------------------------------------- #
R460 = REPO / "tests" / "test_r460_conciseness_calibration.py"
GATE_RUNNER = REPO / "docs" / "measurements" / "r460" / "run_gate_wrapper.sh"
COUNT_RUNNER = REPO / "docs" / "measurements" / "r461" / "run_gate_count_only.sh"

OLD_R460_DOC = """contract's own ceiling, a numeric citation budget, and a structural skeleton at
the target size. Default OFF, so every assertion here is paired with the
byte-identical-when-off check that the house doctrine requires.
\"\"\""""

NEW_R460_DOC = """contract's own ceiling, a numeric citation budget, and a structural skeleton at
the target size. Default OFF, so every assertion here is paired with the
byte-identical-when-off check that the house doctrine requires.

R461 PROMOTION: ``REGENOLD_CONCISE_COUNT_ONLY`` is default ON and outranks this
block, so the autouse fixture below kills it. Every test here selects the R460
arm explicitly instead of silently measuring the count block;
``test_r461_count_only_promoted.py`` pins the precedence itself.
\"\"\""""

OLD_R460_FIXTURE = """@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION", raising=False)"""

NEW_R460_FIXTURE = """@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # R461 PROMOTION — reaching the R460 block is an explicit pair now: the
    # count-only block is default ON and wins when both flags are set.
    monkeypatch.setenv("REGENOLD_CONCISE_COUNT_ONLY", "0")
    monkeypatch.delenv("REGENOLD_CONCISE_CALIBRATION", raising=False)"""

# --------------------------------------------------------------------------- #
# 5. the launchers: name every flag, or the OFF arm is the block itself
# --------------------------------------------------------------------------- #
# Single-line anchors, deliberately: these are shell files whose arm lines end in
# a backslash, and a line-level edit cannot mistranscribe one.
LAUNCHER_LINES: list[tuple[Path, str, str]] = [
    # R460 wrapper gate: arm A was "flags absent" (the no-block arm); after the
    # flip that renders the promoted block, so both arms name COUNT_ONLY.
    (
        GATE_RUNNER,
        'echo "START arm A (flag OFF) repeats=$REPS $(date -Is)" >> "$LOG"',
        'echo "START arm A (REGENOLD_CONCISE_COUNT_ONLY=0) repeats=$REPS $(date -Is)" >> "$LOG"',
    ),
    (
        GATE_RUNNER,
        "$PY -m evals.regenold.run_official_batch --label r460-tunnel-off-s3 $COMMON ",
        "REGENOLD_CONCISE_COUNT_ONLY=0 $PY -m evals.regenold.run_official_batch"
        " --label r460-tunnel-off-s3 $COMMON ",
    ),
    (
        GATE_RUNNER,
        'echo "START arm B (REGENOLD_CONCISE_CALIBRATION=1) repeats=$REPS $(date -Is)" >> "$LOG"',
        'echo "START arm B (REGENOLD_CONCISE_COUNT_ONLY=0'
        ' REGENOLD_CONCISE_CALIBRATION=1) repeats=$REPS $(date -Is)" >> "$LOG"',
    ),
    (
        GATE_RUNNER,
        "REGENOLD_CONCISE_CALIBRATION=1 $PY -m evals.regenold.run_official_batch ",
        "REGENOLD_CONCISE_COUNT_ONLY=0 REGENOLD_CONCISE_CALIBRATION=1"
        " $PY -m evals.regenold.run_official_batch ",
    ),
    # R461 count-only gate: arm A was "flags absent"; the kill switch is now what
    # makes it the OFF arm, or the gate would compare the block against itself.
    (
        COUNT_RUNNER,
        'echo "  arm A = flags absent | arm B = REGENOLD_CONCISE_COUNT_ONLY=1" >> "$LOG"',
        'echo "  arm A = REGENOLD_CONCISE_COUNT_ONLY=0'
        ' | arm B = REGENOLD_CONCISE_COUNT_ONLY=1" >> "$LOG"',
    ),
    (
        COUNT_RUNNER,
        'echo "START arm A (flags absent) repeats=$REPS $(date -Is)" >> "$LOG"',
        'echo "START arm A (REGENOLD_CONCISE_COUNT_ONLY=0) repeats=$REPS $(date -Is)" >> "$LOG"',
    ),
    (
        COUNT_RUNNER,
        "$PY -m evals.regenold.run_official_batch --label r461-countoff-s3 $COMMON ",
        "REGENOLD_CONCISE_COUNT_ONLY=0 $PY -m evals.regenold.run_official_batch"
        " --label r461-countoff-s3 $COMMON ",
    ),
]

def patch_launchers() -> int:
    """Name every flag in the two gate launchers (see the promotion docstring)."""
    changed = 0
    for path, old, new in LAUNCHER_LINES:
        text = path.read_text(encoding="utf-8")
        # Same trap, inverted: these edits PREFIX an env var to a line, so the new
        # line contains the old one. The applied state is the new line itself.
        if new in text:
            print(f"  already applied: {path.name}")
            continue
        assert old in text, f"{path.name}: anchor not found: {old[:60]!r}"
        assert text.count(old) == 1, f"{path.name}: {old[:60]!r} is not unique"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  patched {path.relative_to(REPO)}")
        changed += 1
    return changed


EDITS: list[tuple[Path, str, str]] = [
    (ANSWER_NEED, OLD_COMMENT, NEW_COMMENT),
    (ANSWER_NEED, OLD_FN, NEW_FN),
    (ANSWER_NEED, OLD_MODE_DOC, NEW_MODE_DOC),
    (ROUTES, OLD_TUPLE_ENTRY, NEW_TUPLE_ENTRY),
    (ROUTES, OLD_FLAG_BITS, NEW_FLAG_BITS),
    (ROUTES, OLD_FLAG_TAIL, NEW_FLAG_TAIL),
    (TESTS, OLD_DOC_HEADER, NEW_DOC_HEADER),
    (TESTS, OLD_FLAG_TEST, NEW_FLAG_TEST),
    (TESTS, OLD_OFF_TEST, NEW_OFF_TEST),
    (TESTS, OLD_SHARED_HEAD, NEW_SHARED_HEAD),
    (TESTS, OLD_WINS_HEAD, NEW_WINS_HEAD),
    (TESTS, OLD_ADDITIVE, NEW_ADDITIVE),
    (TESTS, OLD_DEFAULTS, NEW_DEFAULTS),
    (TESTS, OLD_KEY_TEST, NEW_KEY_TEST),
    (R460, OLD_R460_DOC, NEW_R460_DOC),
    (R460, OLD_R460_FIXTURE, NEW_R460_FIXTURE),
]


def apply_edits() -> int:
    changed = 0
    for path, old, new in EDITS:
        text = path.read_text(encoding="utf-8")
        # The applied state is the ADDED text being present, not the anchor being
        # absent: several edits below add around an anchor they keep (the module
        # docstrings, the fixtures), so `new` legitimately CONTAINS `old` and an
        # anchor-based test would apply them twice.
        marker = new[len(old):] if new.startswith(old) else new
        if marker and marker in text:
            print(f"  already applied: {path.name}")
            continue
        count = text.count(old)
        assert count == 1, f"{path.name}: expected exactly 1 match, found {count}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  patched {path.relative_to(REPO)}")
        changed += 1
    return changed


def verify() -> int:
    """Prove the flip from a FRESH interpreter, not from this process."""
    # Read every value BEFORE mutating the environment: reading a flag after the
    # last setenv measures the probe, not the promotion.
    probe = (
        "import os, json;"
        "os.environ.pop('REGENOLD_CONCISE_COUNT_ONLY', None);"
        "from app.engines.answer_need import count_only_enabled, conciseness_mode,"
        " count_only_block;"
        "q = 'Under Article 13, what must providers do?';"
        "default_on, mode = count_only_enabled(), conciseness_mode();"
        "block = count_only_block(q);"
        "os.environ['REGENOLD_CONCISE_COUNT_ONLY'] = '0';"
        "killed_on, killed_mode = count_only_enabled(), conciseness_mode();"
        "killed = count_only_block(q);"
        "print(json.dumps({'default_on': default_on, 'mode': mode,"
        " 'block_chars': len(block), 'killed_on': killed_on,"
        " 'killed_mode': killed_mode, 'killed_chars': len(killed)}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=REPO
    )
    print(out.stdout.strip() or out.stderr.strip())
    assert out.returncode == 0, "verification probe failed"
    import json as _json

    data = _json.loads(out.stdout.strip().splitlines()[-1])
    ok = (
        data["default_on"] is True
        and data["mode"] == "count"
        and data["block_chars"] > 0
        and data["killed_on"] is False
        and data["killed_mode"] == "off"
        and data["killed_chars"] == 0
    )
    print(f"  {'VERIFIED' if ok else 'NOT VERIFIED'}: promoted default renders the "
          f"block; the kill switch renders nothing")
    return 0 if ok else 1


def main() -> int:
    print("R461 promotion — REGENOLD_CONCISE_COUNT_ONLY -> default ON")
    changed = apply_edits() + patch_launchers()
    print(f"{changed} file edit(s) applied")
    rc = verify()
    print("Promotion applied. Rollback: REGENOLD_CONCISE_COUNT_ONLY=0")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
