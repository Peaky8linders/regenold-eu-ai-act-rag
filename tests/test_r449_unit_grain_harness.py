"""R449 — retrieval-grain harness contracts.

The harness decides which changes deserve a live gate, so its own arithmetic
has to be pinned: a coordinate that normalises to the wrong head would silently
turn a retrieval miss into a hit, and an additions count that never fires would
report "the dense stage adds nothing" for a stage that changed 30 references.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.retrieval import unit_grain as ug

# ── Reference normalisation ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("wire", "head"),
    [
        ("Article 13.3.b.iv", "Art. 13"),
        ("Article 6", "Art. 6"),
        ("Art. 13", "Art. 13"),
        ("Annex III.5.b", "Annex III"),
        ("Annex III", "Annex III"),
        ("Annex IV.1.e", "Annex IV"),
        ("Annex X", "Annex X"),
        ("Annex 4", "Annex IV"),
        ("garbage", ""),
    ],
)
def test_canonical_head(wire: str, head: str) -> None:
    assert ug.canonical_head(wire) == head


@pytest.mark.parametrize(
    ("wire", "unit"),
    [
        ("Article 13.3", "3"),
        ("Article 13.3.b.iv", "3"),
        ("Article 50.4", "4"),
        ("Annex IV.1.e", "1"),
        ("Annex III.2", "2"),
        ("Annex I.A.11", "11"),  # section-tagged → printed continuous point
        ("Annex VIII.a", None),  # lettered annex items are not gradable here
        ("Article 6", None),
    ],
)
def test_gold_unit_key(wire: str, unit: str | None) -> None:
    assert ug.gold_unit_key(wire) == unit


# ── Ranking metrics ──────────────────────────────────────────────────────────


def test_ref_recall_and_precision() -> None:
    assert ug.ref_recall(["Art. 13", "Art. 6"], ["Art. 13", "Art. 5"]) == (1, 2)
    assert ug.precision_at_k(["Art. 13", "Art. 6"], ["Art. 13"]) == 0.5
    assert ug.precision_at_k([], ["Art. 13"]) == 0.0
    assert ug.f1(0.5, 0.5) == pytest.approx(0.5)
    assert ug.f1(0.0, 0.0) == 0.0


def test_ndcg_is_one_on_a_perfect_ranking_and_lower_when_late() -> None:
    gold = ["Art. 13", "Art. 6"]
    assert ug.ndcg_at_k(["Art. 13", "Art. 6"], gold) == pytest.approx(1.0)
    late = ug.ndcg_at_k(["Art. 99", "Art. 6", "Art. 13"], gold)
    assert 0.0 < late < 1.0
    assert ug.ndcg_at_k([], gold) == 0.0


def test_ndcg_rewards_rank_not_membership() -> None:
    """Ordering is the point: RRF differs from additive fill only here."""
    gold = ["Art. 13"]
    better = ug.ndcg_at_k(["Art. 13", "Art. 99"], gold)
    worse = ug.ndcg_at_k(["Art. 99", "Art. 13"], gold)
    assert better > worse


# ── Gold loading ─────────────────────────────────────────────────────────────


def test_load_gold_resolves_heads(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps({"id": "r1", "question": "Q one?", "expected_refs": ["Article 13.3", "Annex IV.1.e"]})
        + "\n"
        + json.dumps({"id": "r2", "question": "Q two?", "expected_refs": ["Annex I.A.11"]})
        + "\n",
        encoding="utf-8",
    )
    rows = ug.load_gold(gold)
    assert [r.row_id for r in rows] == ["r1", "r2"]
    assert rows[0].gold_heads == ("Annex IV", "Art. 13")
    assert rows[1].gold_heads == ("Annex I",)


def test_load_gold_limit(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        "".join(
            json.dumps({"id": f"r{i}", "question": "q", "expected_refs": ["Article 1"]}) + "\n"
            for i in range(5)
        ),
        encoding="utf-8",
    )
    assert len(ug.load_gold(gold, limit=2)) == 2


# ── Addition accounting ──────────────────────────────────────────────────────


def _result(name: str, rows: list[tuple[str, list[str], list[str]]]) -> ug.ArmResult:
    detail = [
        ug.RowDetail(
            row_id=row_id,
            gold_heads=gold,
            retrieved=retrieved,
            added_over_bm25=[],
            unit_gold=None,
            unit_overlap_top1=None,
            unit_overlap_coverage=None,
            unit_bm25_top1=None,
            unit_svd_top1=None,
        )
        for row_id, gold, retrieved in rows
    ]
    return ug.ArmResult(
        name=name, note="", env={}, k=8, n_rows=len(detail),
        head_recall=0.0, row_all_head_recall=0.0, head_precision=0.0, head_f1=0.0,
        ndcg=0.0, excess_refs_mean=0.0, context_chars_mean=0.0, detail=detail,
    )


def test_apply_additions_attributes_new_refs_to_the_baseline() -> None:
    # Baseline misses the gold head; the dense arm adds it.
    baseline = _result("bm25", [("r1", ["Art. 13"], ["Art. 99"])])
    other = _result("dense_b", [("r1", ["Art. 13"], ["Art. 13", "Art. 99"])])
    ug._apply_additions([baseline, other])

    assert other.added_total == 1
    assert other.added_gold == 1
    assert other.added_precision == pytest.approx(1.0)
    assert other.detail[0].added_over_bm25 == ["Art. 13"]
    # The baseline itself never reports additions against itself.
    assert baseline.added_total == 0


def test_apply_additions_counts_non_gold_refs_as_imprecision() -> None:
    baseline = _result("bm25", [("r1", ["Art. 13"], ["Art. 13"])])
    other = _result("score", [("r1", ["Art. 13"], ["Art. 13", "Art. 99", "Art. 77"])])
    ug._apply_additions([baseline, other])
    assert other.added_total == 2
    assert other.added_gold == 0
    assert other.added_precision == 0.0


def test_apply_additions_is_a_noop_without_a_baseline() -> None:
    other = _result("dense_b", [("r1", ["Art. 13"], ["Art. 13", "Art. 6"])])
    ug._apply_additions([other])
    assert other.added_total == 0


# ── Reporting + arm wiring ───────────────────────────────────────────────────


def test_markdown_table_has_one_row_per_arm() -> None:
    results = [
        _result("bm25", [("r1", ["Art. 13"], ["Art. 13"])]),
        _result("dense_b", [("r1", ["Art. 13"], ["Art. 13"])]),
    ]
    table = ug.markdown_table(results)
    assert "`bm25`" in table and "`dense_b`" in table
    assert table.count("\n") >= 3


def test_arms_are_index_isolated_by_default() -> None:
    """Any arm that changes the INDEX must not be combined in one process.

    The CLI isolates arms in subprocesses; this pins the reason so a future
    "optimisation" back to in-process execution fails loudly instead of
    reporting a false no-op.
    """
    index_flags = {"REGENOLD_CONTEXTUAL_FIELDS", "REGENOLD_EXTERNAL_EMBEDDINGS"}
    #: Arms allowed to shape the index — each must be safe to run in its own
    #: process, which is what the CLI does for every arm anyway.
    allowed = {"ctx_fields", "ctx_fields_dense", "dense_ext"}
    names = {a.name for a in ug.ARMS}
    for arm in ug.ARMS:
        if arm.env.keys() & index_flags:
            assert arm.name in allowed, arm.name
    assert allowed <= names


def test_offline_env_pins_the_deterministic_flags() -> None:
    for flag in (
        "REGENOLD_SKIP_DOTENV",
        "REGENOLD_EXTERNAL_EMBEDDINGS",
        "REGENOLD_GRAPH_2HOP",
        "REGENOLD_COHERE_RERANK",
        "REGENOLD_CONTEXTUAL_FIELDS",
    ):
        assert flag in ug._OFFLINE_ENV, flag
    assert ug._OFFLINE_ENV["REGENOLD_EXTERNAL_EMBEDDINGS"] == "0"
