"""Data-integrity tests for evals.regenold.evaluator_batch_july7.

Pure parsing tests against the real ``REGENOLD_JULY_7_EVALUATOR_BATCH.md``
export at the repo root — no network, no LLM. Skips cleanly if the file is
absent (it is untracked and large; not every checkout will have it).
"""
from __future__ import annotations

import pytest

from evals.regenold.evaluator_batch_july7 import (
    PUSHBACK_PREAMBLE,
    _DEFAULT_PATH,
    easy_rows,
    group_conversations,
    hard_pushback_rows,
    hard_turn1_rows,
    load_batch,
    pairing_report,
    stats,
)

pytestmark = pytest.mark.skipif(
    not _DEFAULT_PATH.exists(),
    reason="REGENOLD_JULY_7_EVALUATOR_BATCH.md is untracked / not present in this checkout",
)


def test_load_batch_parses_all_333_rows() -> None:
    rows = load_batch()
    assert len(rows) == 333


def test_three_history_groups_are_111_each() -> None:
    rows = load_batch()
    by_turns: dict[int, int] = {}
    for r in rows:
        by_turns[r.history_turns] = by_turns.get(r.history_turns, 0) + 1
    assert by_turns == {0: 111, 18: 111, 20: 111}


def test_group_accessor_functions_match_counts() -> None:
    assert len(easy_rows()) == 111
    assert len(hard_turn1_rows()) == 111
    assert len(hard_pushback_rows()) == 111
    assert all(r.history_turns == 0 for r in easy_rows())
    assert all(r.history_turns == 18 for r in hard_turn1_rows())
    assert all(r.history_turns == 20 for r in hard_pushback_rows())


def test_category_counts_match_the_official_breakdown() -> None:
    """From the file's own 'Executive Summary & Difficulty Breakdown' header."""
    counts = stats()["by_category"]
    assert counts == {
        "Multi-Turn Context & Coreference": 222,
        "Easy Mode (Direct Statutory Lookup)": 52,
        "Complex Decision Boundary": 44,
        "GPAI & Systemic Risk Boundary": 7,
        "Cross-Framework & Sectoral MedTech Integration": 5,
        "Two-Article Conflict & Reconciliation": 2,
        "Borderline Prohibition & Exception": 1,
    }


def test_difficulty_counts() -> None:
    counts = stats()["by_difficulty"]
    assert counts == {"EASY": 52, "HARD": 281}


def test_every_row_has_a_non_empty_question() -> None:
    rows = load_batch()
    assert all(r.question.strip() for r in rows)


def test_ids_are_unique() -> None:
    rows = load_batch()
    ids = [r.id for r in rows]
    assert len(ids) == len(set(ids)) == 333


def test_request_ids_correlation_ids_are_unique() -> None:
    rows = load_batch()
    ids = [r.request_id for r in rows]
    assert len(ids) == len(set(ids)) == 333


def test_seq_is_1_through_333_in_send_order() -> None:
    rows = load_batch()
    assert [r.seq for r in rows] == list(range(1, 334))


def test_easy_rows_never_contain_the_flatten_markers() -> None:
    """history_turns == 0 rows are the raw single-turn text, never our own
    app's multi-turn flatten scaffolding."""
    for r in easy_rows():
        assert "Latest question:\n" not in r.question
        assert "Let's try again:\n" not in r.question


def test_pushback_template_detected_on_expected_count() -> None:
    """R285 established this is ONE fixed template. Verified directly against
    this file: 67 of the 111 turn-2 rows carry it verbatim; the other 44 are
    ordinary multi-turn follow-ups, not pushback challenges."""
    report = pairing_report()
    assert report["pushback_preamble_verbatim_count"] == 67
    assert report["pushback_preamble_total"] == 111


def test_pushback_preamble_constant_matches_recovered_text() -> None:
    rows = hard_pushback_rows()
    marked = [r for r in rows if "I don't think this is correct" in r.question]
    assert len(marked) == 67
    prefix = PUSHBACK_PREAMBLE.split("{question}")[0]
    matches = sum(
        1 for r in marked
        if prefix in r.question
    )
    assert matches == 67


def test_group_conversations_pairs_every_turn2_row() -> None:
    convos = group_conversations()
    assert len(convos) == 111
    # every turn1 used at most once, every turn2 used exactly once
    turn1_ids = [c.turn1.id for c in convos]
    turn2_ids = [c.turn2.id for c in convos]
    assert len(set(turn1_ids)) == 111
    assert len(set(turn2_ids)) == 111
    for c in convos:
        assert c.turn1.history_turns == 18
        assert c.turn2.history_turns == 20
        assert c.pairing_method in ("text_match", "positional")


def test_group_conversations_pairing_match_rate() -> None:
    """Documents the measured pairing quality (see the module docstring):
    text-match recovers ~27%; positional (send-order adjacency, verified
    100% reliable for this dataset) accounts for the rest."""
    report = pairing_report()
    assert report["total_conversations"] == 111
    assert report["text_match"] + report["positional_fallback"] == 111
    assert report["text_match"] == 30
    assert report["positional_fallback"] == 81


def test_every_conversation_pairs_adjacent_seq_numbers() -> None:
    """Ground-truth check: every turn-2 row in this export is immediately
    preceded, in send order, by its turn-1 row. The positional fallback
    should therefore reproduce that adjacency for every non-text-match pair."""
    convos = group_conversations()
    for c in convos:
        assert c.turn2.seq == c.turn1.seq + 1


def test_stats_shape() -> None:
    s = stats()
    assert s["total"] == 333
    assert sum(s["by_difficulty"].values()) == 333
    assert sum(s["by_category"].values()) == 333
    assert s["by_history_turns"] == {0: 111, 18: 111, 20: 111}


def test_july7_fields_populated() -> None:
    rows = load_batch()
    row = rows[0]
    assert row.july7_answer
    assert isinstance(row.july7_refs, tuple)
    assert row.july7_retrieval_path == "kb_fallback"
    assert row.july7_scope_reason


def test_load_batch_missing_file_raises_clear_error(tmp_path) -> None:
    missing = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError, match="REGENOLD_JULY_7_EVALUATOR_BATCH"):
        load_batch(missing)
