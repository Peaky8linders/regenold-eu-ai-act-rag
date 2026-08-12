"""R293 — pin the official July-7 difficulty taxonomy and its join.

The taxonomy is generated from the evaluator batch export, which is NOT in the
repo (a ~1 MB untracked markdown). These tests are therefore the only thing
standing between a silent regeneration error and a corrupted stratified
scorecard, so they check the counts the export itself publishes.
"""
from __future__ import annotations

from collections import Counter

from evals.regenold import july7_difficulty as jd
from evals.regenold.official_batch import load_official_batch


# ── the published summary, reproduced exactly ────────────────────────────────


def test_single_turn_split_is_52_easy_59_hard():
    """The export's headline claim over the 111 single-turn REQUESTS.

    110 unique questions here (one easy question was sent twice), so this is
    51/59 by hash. Both numbers are asserted so a future regeneration that
    silently drops or duplicates a row fails loudly.
    """
    c = Counter(d for d, _ in jd.QUESTION_DIFFICULTY.values())
    assert c["EASY"] == 51, c
    assert c["HARD"] == 59, c
    assert sum(c.values()) == 110


def test_hard_category_counts_match_the_export():
    cats = Counter(cat for d, cat in jd.QUESTION_DIFFICULTY.values() if d == "HARD")
    assert cats["Complex Decision Boundary"] == 44
    assert cats["GPAI & Systemic Risk Boundary"] == 7
    assert cats["Cross-Framework & Sectoral MedTech Integration"] == 5
    assert cats["Two-Article Conflict & Reconciliation"] == 2
    assert cats["Borderline Prohibition & Exception"] == 1
    assert sum(cats.values()) == 59


def test_easy_rows_all_share_the_lookup_category():
    easy = {cat for d, cat in jd.QUESTION_DIFFICULTY.values() if d == "EASY"}
    assert easy == {"Easy Mode (Direct Statutory Lookup)"}


# ── the join into OfficialRow ────────────────────────────────────────────────


def test_every_snapshot_row_gets_a_label():
    """A miss here means the stratified scorecard silently grows an
    '(unlabelled)' bucket, which reads like a data class rather than a bug."""
    rows = load_official_batch()
    assert len(rows) == 110
    unlabelled = [r.id for r in rows if not r.difficulty]
    assert not unlabelled, f"{len(unlabelled)} rows failed to join: {unlabelled[:5]}"


def test_labels_on_rows_match_the_taxonomy_counts():
    rows = load_official_batch()
    c = Counter(r.difficulty for r in rows)
    assert c["EASY"] == 51 and c["HARD"] == 59


def test_to_dict_carries_the_labels():
    """The sidecar is what the judge and any later analysis read."""
    row = load_official_batch()[0]
    d = row.to_dict()
    assert d["difficulty"] in {"EASY", "HARD"}
    assert d["difficulty_category"]


# ── the contract that keeps difficulty from becoming a row filter ────────────


def test_classify_returns_empty_for_unknown_rather_than_guessing():
    assert jd.classify("0" * 64) == ("", "")


def test_multi_turn_is_always_hard_coreference():
    d, c = jd.classify("0" * 64, multi_turn=True)
    assert d == "HARD"
    assert c == "Multi-Turn Context & Coreference"


def test_difficulty_is_not_a_replay_selector():
    """Both difficulties must appear among single-turn rows.

    If a future change made `load_official_batch` return only EASY rows, the
    easy-mode replay would quietly stop covering 59 graded questions while
    still looking like a full run. This is the guard against that.
    """
    rows = load_official_batch()
    assert {r.difficulty for r in rows} == {"EASY", "HARD"}
