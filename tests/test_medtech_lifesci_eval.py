"""Validate the fresh R109 MedTech / life-sciences eval set.

Pure-data checks (no wire call): every expected_ref resolves in
ARTICLE_EXISTENCE, ids are unique, keywords non-empty, and the set is
genuinely distinct from the existing med_01..07 GraphRAG-benchmark rows.
"""
from __future__ import annotations

import re

from app.data.article_existence import ARTICLE_EXISTENCE
from evals.regenold.scenarios_medtech_lifesci import MEDTECH_SCENARIOS
from evals.regenold.scenarios_graphrag_benchmark import GROUND_TRUTH

_ART_RE = re.compile(r"^Article\s+(\d+)$")
_ANNEX_RE = re.compile(r"^Annex\s+([IVXLC]+)$")


def _resolves(ref: str) -> bool:
    m = _ART_RE.match(ref)
    if m:
        return f"Art. {m.group(1)}" in ARTICLE_EXISTENCE
    m = _ANNEX_RE.match(ref)
    if m:
        return f"Annex {m.group(1)}" in ARTICLE_EXISTENCE
    return False


def test_nonempty_set():
    assert len(MEDTECH_SCENARIOS) >= 15


def test_unique_ids():
    ids = [s["id"] for s in MEDTECH_SCENARIOS]
    assert len(ids) == len(set(ids))


def test_every_expected_ref_resolves():
    for s in MEDTECH_SCENARIOS:
        assert s["expected_refs"], f"{s['id']} has no expected_refs"
        for ref in s["expected_refs"]:
            assert _resolves(ref), f"{s['id']} expected_ref {ref!r} does not resolve"


def test_keywords_and_category_present():
    for s in MEDTECH_SCENARIOS:
        assert s["expected_keywords"], f"{s['id']} has no keywords"
        assert s["category"], f"{s['id']} has no category"
        assert s["question"].strip()


def test_distinct_from_graphrag_medtech_rows():
    existing = {g["question"].strip().lower() for g in GROUND_TRUTH}
    for s in MEDTECH_SCENARIOS:
        assert s["question"].strip().lower() not in existing, (
            f"{s['id']} duplicates an existing GraphRAG-benchmark question"
        )
