"""R50 — ReasoningTrace unit tests.

The trace is a ContextVar-backed per-request scratch pad. These tests
lock in:
* Default-OFF behaviour (no overhead when not activated)
* Recorder helpers populate the right fields
* JSON serialisation drops empty / unset fields
* Schema version is stable
* Thread safety (the ContextVar contract)
"""
from __future__ import annotations

import json
import threading

from app.integrations.regenold.reasoning_trace import (
    SCHEMA_VERSION,
    ReasoningTrace,
    activate,
    current,
    deactivate,
    record_anchors,
    record_cache_hit,
    record_compound_roles,
    record_confidence,
    record_graph_2hop,
    record_guard,
    record_intent,
    record_note,
    record_retrieval_path,
    record_scope,
    record_stage2,
    record_top_k,
    record_xref_expand,
)


class TestDefaultOff:
    def test_current_is_none_by_default(self) -> None:
        deactivate()
        assert current() is None

    def test_recorders_are_noops_when_inactive(self) -> None:
        """Every recorder must short-circuit silently when no trace is
        active. This is the core "zero overhead when off" guarantee."""
        deactivate()
        # Should NOT raise:
        record_scope("in_scope", "x")
        record_anchors(["Article 13"])
        record_intent("obligational")
        record_retrieval_path("normal")
        record_top_k([{"ref": "Article 13", "score": 12.4, "source": "kb"}])
        record_xref_expand(["Article 14"])
        record_graph_2hop(["Article 15"])
        record_compound_roles(["provider", "deployer"])
        record_guard("r48_consistency")
        record_stage2(True)
        record_confidence(0.81)
        record_cache_hit(False)
        record_note("test note")
        # Sanity — still inactive:
        assert current() is None


class TestActivation:
    def test_activate_creates_fresh_trace(self) -> None:
        deactivate()
        trace = activate()
        assert trace is not None
        assert isinstance(trace, ReasoningTrace)
        assert current() is trace
        deactivate()

    def test_deactivate_clears_trace(self) -> None:
        activate()
        assert current() is not None
        deactivate()
        assert current() is None


class TestRecorders:
    def setup_method(self) -> None:
        deactivate()
        self.trace = activate()

    def teardown_method(self) -> None:
        deactivate()

    def test_record_scope_with_evidence(self) -> None:
        record_scope("in_scope", "Article 13 anchor", near_oos_framework="")
        assert self.trace.scope == {
            "verdict": "in_scope",
            "evidence": "Article 13 anchor",
        }

    def test_record_scope_with_near_oos_framework(self) -> None:
        record_scope(
            "near_oos",
            "DSA lookalike",
            near_oos_framework="Digital Services Act",
        )
        assert self.trace.scope["near_oos_framework"] == "Digital Services Act"

    def test_record_anchors_overwrites(self) -> None:
        record_anchors(["Article 13", "Article 14"])
        record_anchors(["Article 15"])  # last write wins
        assert self.trace.anchors_used == ["Article 15"]

    def test_record_intent_skips_empty_label(self) -> None:
        record_intent("")
        assert self.trace.intent_label is None
        record_intent(None)
        assert self.trace.intent_label is None
        record_intent("obligational")
        assert self.trace.intent_label == "obligational"

    def test_record_top_k_caps_at_eight(self) -> None:
        big = [{"ref": f"Article {i}", "score": 1.0, "source": "kb"}
               for i in range(20)]
        record_top_k(big)
        assert len(self.trace.top_k_bm25) == 8

    def test_record_guard_deduplicates(self) -> None:
        record_guard("r48_consistency")
        record_guard("r48_consistency")
        record_guard("r49a_grounded_prose")
        assert self.trace.guards_fired == [
            "r48_consistency",
            "r49a_grounded_prose",
        ]

    def test_record_note_caps_count_and_length(self) -> None:
        for i in range(50):
            record_note(f"note {i}")
        assert len(self.trace.notes) == 12  # cap enforced
        long = "x" * 500
        record_note(long)  # would be #13 — dropped
        assert len(self.trace.notes) == 12
        # Length cap of 200 — check existing entries are bounded
        for n in self.trace.notes:
            assert len(n) <= 200

    def test_record_confidence_rounds(self) -> None:
        record_confidence(0.81234567)
        assert self.trace.engine_confidence == 0.812


class TestSerialisation:
    def setup_method(self) -> None:
        deactivate()

    def teardown_method(self) -> None:
        deactivate()

    def test_empty_trace_serialises_only_schema_version(self) -> None:
        trace = activate()
        out = trace.to_json_dict()
        assert out == {"schema_version": SCHEMA_VERSION}

    def test_full_trace_round_trip(self) -> None:
        trace = activate()
        record_scope("in_scope", "Article 13 anchor")
        record_anchors(["Article 13"])
        record_intent("obligational")
        record_retrieval_path("normal")
        record_top_k([
            {"ref": "Article 13", "score": 12.4, "source": "kb"},
            {"ref": "Article 9", "score": 9.1, "source": "corpus"},
        ])
        record_xref_expand(["Article 14"])
        record_compound_roles(["provider", "deployer"])
        record_guard("r48_consistency")
        record_stage2(True)
        record_confidence(0.81)
        record_cache_hit(False)
        record_note("Sonnet polish landed")

        rendered = trace.to_json_string()
        parsed = json.loads(rendered)

        assert parsed["schema_version"] == SCHEMA_VERSION
        assert parsed["scope"]["verdict"] == "in_scope"
        assert parsed["intent_label"] == "obligational"
        assert parsed["retrieval_path"] == "normal"
        assert len(parsed["top_k_bm25"]) == 2
        assert parsed["compound_roles"] == ["provider", "deployer"]
        assert parsed["guards_fired"] == ["r48_consistency"]
        assert parsed["stage2_polish"] is True
        assert parsed["engine_confidence"] == 0.81
        assert parsed["cache_hit"] is False
        assert parsed["notes"] == ["Sonnet polish landed"]

    def test_empty_collections_dropped(self) -> None:
        """The JSON should NOT carry empty lists / dicts — keeps the
        wire payload compact and the judge prompt focused."""
        trace = activate()
        record_intent("obligational")  # only one field set
        out = trace.to_json_dict()
        assert "top_k_bm25" not in out
        assert "anchors_used" not in out
        assert "guards_fired" not in out
        assert out["intent_label"] == "obligational"


class TestContextVarIsolation:
    """ContextVar must give each request its own trace — a module-level
    singleton would leak state between concurrent FastAPI requests.

    These tests simulate request isolation by activating/deactivating
    in a controlled sequence. True async / threading isolation is
    handled by Python's ContextVar implementation itself; we just
    confirm we didn't accidentally use a module global.
    """

    def test_threads_get_independent_traces(self) -> None:
        results: dict[int, str | None] = {}
        barrier = threading.Barrier(2)

        def worker(thread_id: int) -> None:
            deactivate()  # belt-and-braces — start with no trace
            trace = activate()
            record_intent(f"intent_thread_{thread_id}")
            barrier.wait()  # ensure both threads have set their value
            # Each thread should see ITS OWN intent, not the other's.
            trace_now = current()
            results[thread_id] = (
                trace_now.intent_label if trace_now else None
            )
            deactivate()

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # ContextVar's thread-local behaviour: each thread inherits the
        # parent context but its `set()` is local. So each thread sees
        # its own value, not cross-contamination.
        assert results[1] == "intent_thread_1"
        assert results[2] == "intent_thread_2"
