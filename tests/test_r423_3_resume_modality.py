"""R423.3 — a resume must not change a row's MODALITY, only its draw.

WHY THIS FILE EXISTS
--------------------
``docs/measurements/r423/graded_scope_probe.py`` falsified the R423 scope note by
driving real hard rows through the real route and recording the system prompt each
dispatch actually carried. The finding: ``_run_hard`` keeps a ROLLING conversation
that starts EMPTY, so the first two rows of a run read ``history_turn_count`` 0 and
1 and their Stage-2 dispatches receive the FULL ~59.6 kB system prompt. Every later
row reads >= 2 and receives the 61-char persona.

The engine is right about this — a request carrying 0 prior turns genuinely IS a
single-turn ask. The HARNESS was wrong: ``--resume`` handed its pending rows a
brand-new empty history, so a resumed arm's first rows were re-graded as
near-single-turn, which is a modality its uninterrupted counterpart would never
have had. In the R423 need4 gate that cost arm A exactly one full-prompt primary
dispatch that arm B did not make, i.e. it put a real difference in the SYSTEM slot
between the two arms of a paired comparison.

``seed_history_from_records`` rebuilds the rolling conversation from the rows
already on disk, so a resume now measures what the first run would have measured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import evals.regenold.run_official_batch as ROB
from evals.regenold import hard_preamble as hp
from evals.regenold.official_batch import HARD_CONTEXT_EXCHANGES


def _record(i: int, *, turn1: str = "", pushback: str = "") -> dict:
    return {
        "id": f"rg_{i:03d}",
        "question": f"question {i}",
        "turn1_answer": turn1,
        "pushback_answer": pushback,
        "pred_answer": pushback or turn1,
    }


class TestSeedHistory:
    def test_it_rebuilds_user_and_assistant_pairs_in_order(self) -> None:
        seed = ROB.seed_history_from_records(
            [_record(1, turn1="first", pushback="first-after-pushback")]
        )
        assert seed == [
            {"role": "user", "content": "question 1"},
            {"role": "assistant", "content": "first-after-pushback"},
        ]

    def test_it_falls_back_to_turn_one_when_no_pushback_landed(self) -> None:
        """``_run_hard`` rolls forward on ``ans2 or ans1``, so mirror that."""
        seed = ROB.seed_history_from_records([_record(1, turn1="only turn 1")])
        assert seed[-1]["content"] == "only turn 1"

    def test_a_record_with_no_turn_one_answer_contributes_nothing(self) -> None:
        """Only rows the runner actually rolled forward may be seeded.

        ``_run_hard`` guards the roll-forward with ``if ans1``, so a row whose
        turn 1 came back empty never added an exchange to the conversation.
        Inventing one here would give the resumed run a history the original
        never had — the exact class of bug this module exists to remove.
        """
        seed = ROB.seed_history_from_records(
            [_record(1, turn1="kept"), _record(2), _record(3, turn1="also kept")]
        )
        assert [m["content"] for m in seed if m["role"] == "user"] == [
            "question 1",
            "question 3",
        ]

    def test_it_is_trimmed_to_the_context_window(self) -> None:
        records = [_record(i, turn1=f"a{i}") for i in range(1, 9)]
        seed = ROB.seed_history_from_records(records)
        assert len(seed) == 2 * HARD_CONTEXT_EXCHANGES
        # and it is the TAIL that survives, matching ``trim_history``
        assert seed[-2]["content"] == "question 8"

    def test_no_records_is_an_empty_history_not_an_error(self) -> None:
        assert ROB.seed_history_from_records([]) == []


class _HardRow:
    """The minimum a row needs for the HARD path, so the arm can run offline."""

    def __init__(self, i: int) -> None:
        self.id = f"rg_{i:03d}"
        self.question = f"question {i}"
        self.difficulty = "HARD"
        self.difficulty_category = "multi-turn"
        self.jul07_answer = "a reference answer"
        self.jul07_refs = ["Article 3"]

    def pushback_content(self) -> str:
        return f"pushback {self.question}"


@pytest.fixture()
def hard_calls(monkeypatch, tmp_path: Path):
    """Run ``_arm`` in hard mode offline, recording every request's HISTORY LENGTH.

    The history length is the whole point: ``history_turn_count`` — and therefore
    which system prompt the engine picks — is a function of it.

    R424 flips the harness DEFAULT to the pre-fixed 9-turn dialogue, whose history
    is the fixture rather than a rolling window — so the module pins the ROLLING
    shape explicitly. The invariants below are properties of that shape, and a
    fixture that let the default drift would have silently stopped testing them
    (which is exactly what happened before the pin was added).
    """
    monkeypatch.setenv(hp.HARD_PREAMBLE_ENV, hp.MODE_ROLLING)
    monkeypatch.setattr(ROB, "_RESULTS", tmp_path)
    monkeypatch.setattr(ROB, "_clear_engine_cache", lambda: (0, None))
    history_lengths: list[int] = []

    def _run(rows, *, resume: bool, repeats: int = 1):
        def poster(_url, _key, msgs, _timeout):
            history_lengths.append(len(msgs))
            body = {"answer": "an answer", "references": ["Article 3"]}
            return body, 1000, 200, None, 1, None

        return ROB._arm(
            "tt",
            "hard",
            rows,
            poster=poster,
            url="local://probe",
            api_key=None,
            timeout=1.0,
            arm_env={},
            suffix="-A",
            resume=resume,
            repeats=repeats,
        )

    return tmp_path, history_lengths, _run


def test_a_fresh_hard_run_still_starts_from_an_empty_history(hard_calls) -> None:
    """The fix must not change an UNRESUMED run: that is the shipped baseline.

    A fresh run's first rows reading as near-single-turn is the harness's
    documented rolling-conversation behaviour, and every board on record was
    measured with it. Seeding a FRESH run would silently rebase those numbers.
    """
    tmp_path, lengths, run = hard_calls
    rows = [_HardRow(i) for i in (1, 2, 3)]
    run(rows, resume=False)

    # row 1 turn 1 (1 msg), row 1 pushback (3), row 2 t1 (3), row 2 pb (5), ...
    assert lengths[0] == 1, f"a fresh run must start with no prior turns: {lengths}"
    assert lengths[1] == 3
    assert lengths[2] == 3, "row 2 carries exactly one prior exchange"


def test_a_resumed_hard_run_seeds_the_conversation_it_lost(hard_calls) -> None:
    """THE FIX. A resumed first row must not be re-graded as single-turn.

    Before R423.3 the resumed run's first request carried 1 message — a
    ``history_turn_count`` of 0, so the engine delivered the full system prompt and
    the row was graded in a modality the uninterrupted run never used.
    """
    tmp_path, lengths, run = hard_calls
    rows = [_HardRow(i) for i in (1, 2, 3)]

    run(rows, resume=False)
    fresh_first_row_first_request = lengths[0]
    lengths.clear()

    # Lose everything after row 1, as a restart does.
    for name in ("official-tt-A-hard.ckpt.jsonl",):
        path = tmp_path / name
        path.write_text(
            "\n".join(path.read_text(encoding="utf-8").splitlines()[:1]) + "\n",
            encoding="utf-8",
        )

    run(rows, resume=True)

    assert len(lengths) == 4, f"rows 2 and 3, two turns each: {lengths}"
    resumed_first = lengths[0]
    assert resumed_first > fresh_first_row_first_request, (
        "the resumed run's first row must carry the prior conversation, not an "
        f"empty one: {lengths}"
    )
    # Row 2 sat behind exactly one completed exchange, so it must read 3 messages
    # — byte-identical to what the uninterrupted run sent for that same row.
    assert resumed_first == 3, (
        f"a resumed row 2 must carry the same history as a fresh row 2: {lengths}"
    )


def test_the_runner_threads_the_seed_only_for_hard_mode(hard_calls) -> None:
    """Pin the wiring: an easy resume has no rolling conversation to seed.

    R424 — asserted on the SYMBOLS the wiring needs rather than on one line's
    formatting. The seed is now conditional on the request shape (a ``fixed`` arm
    has no rolling conversation to restore), so a string match on the old
    assignment would have failed while the contract still held.
    """
    src = (
        Path(ROB.__file__).read_text(encoding="utf-8")
    )
    assert "seed_history_from_records(previous)" in src
    # The fixed shape must NOT seed: its history is the fixture, which is what
    # makes a resumed fixed run identical to an uninterrupted one.
    assert "MODE_FIXED" in src
    assert "resuming hard with" in src
    # Exactly ONE call site threads a seed. If easy mode ever grows one, a
    # format-stable run would start depending on a conversation it does not keep.
    assert src.count("seed_history=seed") == 1
    # And the module exposes the seed on the HARD runner only.
    from inspect import signature

    assert "seed_history" in signature(ROB._run_hard).parameters
    assert "seed_history" not in signature(ROB._run_easy).parameters
