"""Validate the fresh R120 MedTech / life-sciences V3 eval set.

Pure-data checks (no wire call): every expected_ref resolves in
ARTICLE_EXISTENCE, ids are unique, keywords non-empty, and the set is
genuinely DISTINCT from the prior sets and GraphRAG-benchmark rows.
"""
from __future__ import annotations

import re

from app.data.article_existence import ARTICLE_EXISTENCE
from evals.regenold.scenarios_medtech_lifesci import MEDTECH_SCENARIOS
from evals.regenold.scenarios_medtech_lifesci_v2 import MEDTECH_SCENARIOS_V2
from evals.regenold.scenarios_medtech_lifesci_v3 import MEDTECH_SCENARIOS_V3
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
    assert len(MEDTECH_SCENARIOS_V3) >= 15


def test_unique_ids():
    ids = [s["id"] for s in MEDTECH_SCENARIOS_V3]
    assert len(ids) == len(set(ids))


def test_every_expected_ref_resolves():
    for s in MEDTECH_SCENARIOS_V3:
        assert s["expected_refs"], f"{s['id']} has no expected_refs"
        for ref in s["expected_refs"]:
            assert _resolves(ref), (
                f"{s['id']} expected_ref {ref!r} does not resolve in ARTICLE_EXISTENCE"
            )


def test_keywords_and_category_present():
    for s in MEDTECH_SCENARIOS_V3:
        assert s["expected_keywords"], f"{s['id']} has no keywords"
        assert s["category"], f"{s['id']} has no category"
        assert s["question"].strip()


def test_distinct_from_prior_sets():
    """No V3 question may duplicate a prior medtech row or a GraphRAG ground-truth row."""
    prior = {g["question"].strip().lower() for g in GROUND_TRUTH}
    prior |= {s["question"].strip().lower() for s in MEDTECH_SCENARIOS}
    prior |= {s["question"].strip().lower() for s in MEDTECH_SCENARIOS_V2}
    for s in MEDTECH_SCENARIOS_V3:
        assert s["question"].strip().lower() not in prior, (
            f"{s['id']} duplicates a prior medtech/benchmark question"
        )


def test_unique_ids_vs_prior():
    prior_ids = {s["id"] for s in MEDTECH_SCENARIOS}
    prior_ids |= {s["id"] for s in MEDTECH_SCENARIOS_V2}
    v3_ids = {s["id"] for s in MEDTECH_SCENARIOS_V3}
    assert not (prior_ids & v3_ids), "V3 ids collide with the prior sets"


def test_multiturn_messages_well_formed():
    multiturn = [s for s in MEDTECH_SCENARIOS_V3 if "messages" in s]
    for s in multiturn:
        msgs = s["messages"]
        assert len(msgs) >= 3, f"{s['id']}: multi-turn needs >= 3 messages"
        for i, m in enumerate(msgs):
            expected_role = "user" if i % 2 == 0 else "assistant"
            assert m["role"] == expected_role, (
                f"{s['id']} message {i}: role {m['role']!r}, expected {expected_role!r}"
            )
            assert m["content"].strip(), f"{s['id']} message {i} is empty"
        assert msgs[-1]["role"] == "user", f"{s['id']} must end on a user turn"
        assert msgs[-1]["content"].strip() == s["question"].strip(), (
            f"{s['id']}: final user turn must equal the 'question' field"
        )
