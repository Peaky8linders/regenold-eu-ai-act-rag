"""R136 — integrity tests for the fresh MedTech / life-sciences probe set."""
from __future__ import annotations

import re

from app.data.article_existence import ARTICLE_EXISTENCE
from evals.regenold.scenarios_medtech_lifesci_r136 import GROUND_TRUTH, question_ids

_VALID_LEVELS = {"L1", "L2", "L3", "L4"}


def _existence_key(ref: str) -> str:
    m = re.match(r"Article\s+(\d+)", ref)
    if m:
        return "Art. " + m.group(1)
    n = re.match(r"Annex\s+([IVXLC]+)", ref)
    if n:
        return "Annex " + n.group(1)
    return ref


def test_row_count_and_unique_ids():
    assert len(GROUND_TRUTH) == 24
    ids = question_ids()
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("ls_") for i in ids)


def test_all_expected_refs_resolve():
    for r in GROUND_TRUTH:
        assert r["expected_refs"], r["id"]
        for ref in r["expected_refs"]:
            assert _existence_key(ref) in ARTICLE_EXISTENCE, (r["id"], ref)


def test_ids_disjoint_from_existing_sets():
    # Disjoint from the v124 / graphrag / antifragile / medtech ID spaces.
    other: set[str] = set()
    try:
        from evals.regenold.scenarios_medtech_graphrag_v124 import GROUND_TRUTH as V124
        other |= {r["id"] for r in V124}
    except Exception:  # pragma: no cover
        pass
    try:
        from evals.regenold.antifragile_groundtruth import ANTIFRAGILE_GT
        other |= set(ANTIFRAGILE_GT)
    except Exception:  # pragma: no cover
        pass
    try:
        from evals.regenold.scenarios_graphrag_benchmark import GROUND_TRUTH as GRB
        other |= {r["id"] for r in GRB}
    except Exception:  # pragma: no cover
        pass
    assert set(question_ids()).isdisjoint(other)


def test_judge_field_compatibility():
    for r in GROUND_TRUTH:
        for field in ("id", "question", "expected_refs", "expected_keywords",
                      "gold_answer", "category", "reasoning_level"):
            assert field in r, (r["id"], field)
        assert r["reasoning_level"] in _VALID_LEVELS, r["id"]
        assert len(r["gold_answer"]) > 40, r["id"]
        assert r["expected_keywords"], r["id"]
