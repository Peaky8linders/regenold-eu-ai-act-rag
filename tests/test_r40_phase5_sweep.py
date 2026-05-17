"""R40 Phase 5 — eng-review sweep regression tests.

Covers the P2/P3 findings ported from the R39 eng-review:

* F5 — cache-key folds the R39 retrieval flags (PPR / PathRAG).
  Additional flag-specific tests live in
  ``tests/test_turboquant_index.py`` near the R31 dense-flag tests.
* F7 — dead ``_CONFIDENCE_FLOOR_FOR_ANSWER`` constant deleted.
* F11 — partial-seed guard logs node/edge progress on Neo4j seed failure.
* F18 — split the ``description`` ref-budget into
  ``description_short`` (3) and ``description_scenario`` (8); add
  ``intent_budget_for`` helper that picks based on scenario shape.

F13 / F14 / F16 / F17 are behaviour-preserving infrastructure (docstring,
import hoist, side-set membership); the existing 1300+ test suite
already covers their observable behaviour.
"""
from __future__ import annotations

import logging

import pytest


# ── F7: dead constant removed ──────────────────────────────────────────


def test_f7_confidence_floor_for_answer_constant_is_gone():
    """The constant was unused after the empty-refs branch became the
    sole refusal gate. Per R39 eng-review F7."""
    import app.routes.regenold as regenold_route

    assert not hasattr(regenold_route, "_CONFIDENCE_FLOOR_FOR_ANSWER"), (
        "R40/F7: _CONFIDENCE_FLOOR_FOR_ANSWER should be deleted from "
        "app.routes.regenold (dead code, only the comment trace remains)"
    )


# ── F18: description ref-budget split ──────────────────────────────────


def test_f18_intent_ref_budget_has_split_description_keys():
    """The split keys must exist with the spec values (3 short / 8 scenario).

    The plain ``description`` key continues to exist (alias for short)
    so callers that haven't migrated still get a sane value.
    """
    from app.integrations.regenold.models import INTENT_REF_BUDGET

    assert INTENT_REF_BUDGET["description_short"] == 3
    assert INTENT_REF_BUDGET["description_scenario"] == 8
    # Alias preserved for legacy callers
    assert INTENT_REF_BUDGET["description"] == 3, (
        "description must alias description_short so existing callers "
        "don't silently retain the over-wide 8-ref budget"
    )


def test_f18_intent_budget_for_description_picks_scenario_when_scenario_shape():
    from app.integrations.regenold.models import intent_budget_for

    assert intent_budget_for("description", is_scenario_shape=True) == 8
    assert intent_budget_for("description", is_scenario_shape=False) == 3


def test_f18_intent_budget_for_non_description_passes_through():
    """Other qtypes don't get the scenario/short split — they use their
    own per-intent budget regardless of question shape."""
    from app.integrations.regenold.models import intent_budget_for

    assert intent_budget_for("definition", is_scenario_shape=False) == 3
    assert intent_budget_for("definition", is_scenario_shape=True) == 3
    assert intent_budget_for("boolean", is_scenario_shape=True) == 4
    assert intent_budget_for("list", is_scenario_shape=False) == 5


def test_f18_intent_budget_for_unknown_qtype_returns_none():
    """An unknown qtype returns None so the caller can fall back to the
    route default budget instead of getting a stale value."""
    from app.integrations.regenold.models import intent_budget_for

    assert intent_budget_for(None, is_scenario_shape=False) is None
    assert intent_budget_for("not-a-real-qtype", is_scenario_shape=True) is None


# ── F11: partial-seed guard ────────────────────────────────────────────


def test_f11_seed_graph_logs_partial_state_on_failure(caplog):
    """A failure mid-batch must log the partial state (nodes/edges
    written so far) and re-raise. The caller must see the exception so
    auto-seed / CLI can decide retry / alerting; swallowing would
    silently leave the graph half-seeded."""
    from scripts import seed_neo4j_kb

    # Build a real payload (zero LLM, just stdlib). It's expensive
    # enough that we don't want to do it for every test.
    payload = seed_neo4j_kb.build_payload()

    # Fake client that succeeds for the first few labels then raises.
    class _Boom(RuntimeError):
        pass

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        def execute_write_batch(self, queries):
            self.calls += 1
            # Fail after several successful batches so the partial-state
            # log records both completed labels AND non-zero counts.
            # The seeder runs nodes first (Article=113, Annex=13, etc.)
            # — the default batch_size of 1000 puts each node label in
            # 1 batch. Failing on the 5th call means we've completed
            # Article + Annex + Recital + Definition before the error.
            if self.calls >= 5:
                raise _Boom("simulated mid-batch write failure")
            return None

    client = _FlakyClient()
    caplog.set_level(logging.ERROR, logger="scripts.seed_neo4j_kb")
    with pytest.raises(_Boom):
        seed_neo4j_kb.seed_graph(client, payload, verbose=False)

    # The error log must report partial state — nodes_written / edges_written
    # plus the completed_labels list.
    matching = [r for r in caplog.records if "partial_seed_state" in r.getMessage()]
    assert matching, (
        "expected a partial_seed_state log record; the seed must surface "
        "what completed before the mid-batch failure"
    )
    msg = matching[0].getMessage()
    assert "nodes_written=" in msg
    assert "edges_written=" in msg
    assert "completed_labels=" in msg
    # We failed on the 5th call so ~4 node labels completed before the
    # blow-up. nodes_written must be positive (>0); edges_written should
    # be 0 because the failure happened during node writes.
    assert "nodes_written=0" not in msg, (
        "F11 must show non-zero progress when several node labels "
        "completed before the failure — bare 'nodes_written=0' means "
        "the count aggregation broke"
    )


# ── F17: scope.py uses set-backed membership for anchor lists ──────────


def test_f17_scope_anchor_pool_preserves_order_under_repeats():
    """Side-set conversion must preserve list ordering (insertion order).

    The verdict's downstream consumers rely on first-mentioned anchors
    ranking higher; switching to a set-only data structure would have
    lost that ordering. Verify both anchors and prior_anchors are still
    list-ordered with no duplicates after a long conversation with
    repeating article mentions.
    """
    from app.integrations.regenold.scope import classify_conversation

    # 12-turn conversation with the same article mentioned repeatedly
    # in different shapes — exercises the per-turn anchor accumulator.
    messages = []
    for _ in range(6):
        messages.append({"role": "user", "content": "Tell me about Art. 13."})
        messages.append({
            "role": "assistant",
            "content": "Article 13 covers transparency.",
        })
    # Live turn references a different article so we have at least 2 anchors.
    messages.append({"role": "user", "content": "And what about Art. 50?"})

    verdict = classify_conversation(messages)
    # Both articles must appear exactly once each (no dupes)
    assert verdict.anchor_articles.count("Art. 13") == 1
    assert verdict.anchor_articles.count("Art. 50") == 1
    # Order preserved — Art. 13 mentioned first, Art. 50 second
    art_idx = verdict.anchor_articles.index("Art. 13")
    art50_idx = verdict.anchor_articles.index("Art. 50")
    assert art_idx < art50_idx, (
        "F17 fix must preserve list order — first-mentioned anchor "
        "ranks higher in the verdict"
    )
