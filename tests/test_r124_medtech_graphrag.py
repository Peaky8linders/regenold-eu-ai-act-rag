"""R124 — fresh medtech/healthcare/life-sciences GraphRAG-Bench-themed
benchmark: dataset integrity + distinctness + judge-compatibility.

Pure data tests — no network, no wire, no LLM.
"""
from __future__ import annotations

import pytest

from evals.regenold.scenarios_medtech_graphrag_v124 import GROUND_TRUTH
from evals.regenold.validate_medtech_graphrag_v124 import validate


def test_dataset_validates_clean():
    """Every expected_ref resolves, ids unique + grb_-prefixed, every row has a
    gold_answer + keywords + a valid reasoning level."""
    errors = validate()
    assert errors == [], "dataset validation problems:\n" + "\n".join(errors)


def test_has_enough_rows_and_all_four_reasoning_levels():
    assert len(GROUND_TRUTH) >= 24
    levels = {r["reasoning_level"] for r in GROUND_TRUTH}
    assert levels == {"L1", "L2", "L3", "L4"}  # full GraphRAG-Bench taxonomy


def test_ids_are_grb_prefixed_and_unique():
    ids = [r["id"] for r in GROUND_TRUTH]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("grb_") for i in ids)


def test_ids_disjoint_from_existing_eval_sets():
    """The grb_ ids must not collide with any existing eval set so a combined
    judge run never silently overwrites rows."""
    existing: set[str] = set()
    for mod_name, attr in (
        ("evals.regenold.scenarios_graphrag_benchmark", "GROUND_TRUTH"),
        ("evals.regenold.scenarios_medtech_lifesci", "SCENARIOS"),
        ("evals.regenold.scenarios_medtech_multiturn_r118", "SCENARIOS"),
    ):
        try:
            mod = __import__(mod_name, fromlist=[attr])
        except Exception:  # noqa: BLE001 — optional set, skip if absent
            continue
        for candidate in (attr, "GROUND_TRUTH", "SCENARIOS"):
            data = getattr(mod, candidate, None)
            if isinstance(data, list):
                for r in data:
                    if isinstance(r, dict) and "id" in r:
                        existing.add(str(r["id"]))
    ours = {r["id"] for r in GROUND_TRUTH}
    assert ours.isdisjoint(existing), f"id collision: {sorted(ours & existing)}"


def test_rows_are_judge_compatible():
    """Each row must carry the fields evals.judge.runner's prompt renderers
    read (question / expected_keywords / expected_refs / gold_answer)."""
    for r in GROUND_TRUTH:
        assert r["question"].strip()
        assert isinstance(r["expected_refs"], list) and r["expected_refs"]
        assert isinstance(r["expected_keywords"], list) and r["expected_keywords"]
        assert r["gold_answer"].strip()
        assert r["category"].strip()
        assert r["graphrag_theme"].strip()


def test_gold_answers_are_concise():
    """Gold answers are the regulator-voice reference — keep them tight
    (the conciseness axis is scored against them). 1-5 sentences, < 700 chars."""
    for r in GROUND_TRUTH:
        gold = r["gold_answer"]
        assert len(gold) < 700, f"{r['id']} gold too long ({len(gold)} chars)"


@pytest.mark.parametrize(
    "term,must_resolve_ref",
    [
        ("emotion", "Article 5"),       # 5(1)(f) medical carve-out
        ("triage", "Annex III"),         # §5(d) emergency triage
        ("10^25 FLOPs", "Article 51"),   # GPAI systemic risk
    ],
)
def test_key_medical_themes_present(term, must_resolve_ref):
    """Spot-check that the load-bearing medical themes are actually in the set
    and cite the right anchor."""
    hits = [
        r for r in GROUND_TRUTH
        if term.lower() in (r["question"] + " " + r["gold_answer"]).lower()
    ]
    assert hits, f"no row covers theme {term!r}"
    assert any(must_resolve_ref in r["expected_refs"] for r in hits), (
        f"theme {term!r} present but none of its rows cite {must_resolve_ref}"
    )
