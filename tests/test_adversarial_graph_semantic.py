"""Adversarial stress-testing for graph semantic layers and knowledge-graph context.

Audits:
1. `app.engines.graph_semantic` and `app.engines.kg_context`
2. Input robustness: special characters, Cypher injections, emojis, giant payloads, malformed refs.
3. Fail-soft behavior: embedding failure, Aura timeouts, network crashes, admission saturation, circuit breaker tripping.
4. Grounding and anti-leakage invariants: non-citable headers, allowlist exclusion, provision constraints.
5. Cache key identity and collision resistance in `app.routes.regenold._engine_cache_key`.
"""
from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import app.engines.graph_semantic as gs
import app.engines.kg_context as kg
from app.graph.timeouts import (
    GRAPH_BREAKER_THRESHOLD,
    graph_circuit_open,
    record_graph_failure,
    record_graph_success,
    reset_graph_circuit,
    resolve_graph_timeout_ms,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset memo and circuit breaker before and after each test."""
    kg.reset_kg_context_memo()
    reset_graph_circuit()
    yield
    kg.reset_kg_context_memo()
    reset_graph_circuit()


# ──────────────────────────────────────────────────────────────────────────
# 1. Adversarial Question & Ref Inputs
# ──────────────────────────────────────────────────────────────────────────


class TestAdversarialInputs:
    """Stress-test queries against extreme or malicious inputs."""

    @pytest.mark.parametrize(
        "bad_q",
        [
            "",
            "   ",
            "\n\t\r",
            "\x00\x01\x1f",
            "🤖 ⚖️ 🇪🇺 🚀" * 50,
            "'; MATCH (n) DETACH DELETE n; //",
            "\" OR 1=1 --",
            "$ids $fanout $emb $min_sim",
            "§ 5 Abs. 1 DSGVO i.V.m. Art. 6 Abs. 1 lit. c",
            "A" * 50_000,
        ],
        ids=[
            "empty",
            "whitespace",
            "newlines_tabs",
            "control_chars",
            "emojis",
            "cypher_injection",
            "sql_injection",
            "cypher_param_names",
            "unicode_legal_notation",
            "50k_long_text",
        ],
    )
    def test_fetch_focused_subprovisions_handles_extreme_questions(
        self, bad_q: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        # Should never raise regardless of question content
        res = gs.fetch_focused_subprovisions(bad_q, ["Art. 5", "Art. 50"])
        assert isinstance(res, list)

    @pytest.mark.parametrize(
        "bad_q",
        [
            "",
            "   ",
            "\x00",
            "'; DROP TABLE articles; --",
            "🤖" * 100,
            "B" * 20_000,
        ],
        ids=[
            "empty",
            "whitespace",
            "null_byte",
            "sql_injection",
            "emojis",
            "20k_long_text",
        ],
    )
    def test_fetch_gloss_context_handles_extreme_questions(
        self, bad_q: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_SEMANTIC_GLOSS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        res = gs.fetch_definition_and_recital_context(bad_q, ["Art. 5"])
        assert isinstance(res, list)

    @pytest.mark.parametrize(
        "bad_refs",
        [
            [],
            [None],
            ["", "   ", "\x00"],
            ["<script>alert('xss')</script>"],
            ["Article NaN", "Annex 9999", "Art -1", "Recital 4"],
            ["Article 999", "Annex ZZZ"],
            ["Art. 5"] * 500,  # Huge duplicate list
            [123, 45.6, object()],  # Non-string garbage
        ],
        ids=[
            "empty_list",
            "list_with_none",
            "whitespace_and_null",
            "xss_string",
            "invalid_format_refs",
            "nonexistent_refs",
            "500_duplicates",
            "non_string_objects",
        ],
    )
    def test_fetch_focused_subprovisions_handles_malformed_refs(
        self, bad_refs: list, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        res = gs.fetch_focused_subprovisions("What is prohibited?", bad_refs)  # type: ignore[arg-type]
        assert isinstance(res, list)

    def test_anchor_terms_extraction_adversarial(self) -> None:
        """Anchor terms must survive non-string, malformed, and injection refs."""
        assert gs._anchor_terms([]) == []
        assert gs._anchor_terms(None) == []  # type: ignore[arg-type]

        dirty_refs = [
            "Article 50.1",
            "Annex III",
            "Art. 5",
            None,
            123,
            "Article 50",  # Duplicate head
            "Article 50.2.a",
            "Invalid Ref Shape",
        ]
        anchors = gs._anchor_terms(dirty_refs)  # type: ignore[arg-type]
        assert isinstance(anchors, list)
        assert len(anchors) <= 8
        # Ensure deduped heads
        assert len(anchors) == len(set(anchors))


# ──────────────────────────────────────────────────────────────────────────
# 2. Environment Variable Clamping & Out-of-Bounds Sanitization
# ──────────────────────────────────────────────────────────────────────────


class TestEnvClamping:
    """Env vars controlling query limits must be strictly clamped."""

    def test_adaptive_fanout_bounds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clamped to [10, 200]
        monkeypatch.setenv("REGENOLD_SEMANTIC_ANN_FANOUT", "-50")
        assert gs._adaptive_fanout() == 10

        monkeypatch.setenv("REGENOLD_SEMANTIC_ANN_FANOUT", "99999")
        assert gs._adaptive_fanout() == 200

        monkeypatch.setenv("REGENOLD_SEMANTIC_ANN_FANOUT", "invalid")
        assert gs._adaptive_fanout() == 60  # Default

    def test_query_limits_clamped_in_cypher_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        monkeypatch.setenv("REGENOLD_SEMANTIC_MIN_SIM", "-2.0")
        monkeypatch.setenv("REGENOLD_SEMANTIC_UNITS", "999")
        monkeypatch.setenv("REGENOLD_SEMANTIC_UNITS_PER_PROVISION", "-5")

        captured_params: dict = {}

        def _mock_read(cypher, params):
            captured_params.update(params)
            return []

        monkeypatch.setattr(kg, "_bounded_execute_read", _mock_read)
        monkeypatch.setattr(gs, "_embed", lambda _q: [0.1] * 128)

        gs.fetch_focused_subprovisions("test question", ["Art. 5"])

        assert captured_params["min_sim"] == 0.0  # Clamped lo
        assert captured_params["limit"] == 20  # Clamped hi
        assert captured_params["per_provision"] == 1  # Clamped lo


# ──────────────────────────────────────────────────────────────────────────
# 3. Embedding Failure Fallback
# ──────────────────────────────────────────────────────────────────────────


class TestEmbeddingFailures:
    """Embedding failures must soft-fail without raising or breaking answers."""

    def test_embed_when_embeddings_index_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.engines.embeddings_index.is_available", lambda: False
        )
        assert gs._embed("What is high risk?") is None

    def test_embed_when_query_embed_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.engines.embeddings_index.is_available", lambda: True
        )
        monkeypatch.setattr(
            "app.engines.embeddings_index._embed_query", lambda _q: None
        )
        assert gs._embed("What is high risk?") is None

    def test_embed_when_query_embed_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _exploding_embed(_q):
            raise RuntimeError("SVD model failed to compute")

        monkeypatch.setattr(
            "app.engines.embeddings_index.is_available", lambda: True
        )
        monkeypatch.setattr(
            "app.engines.embeddings_index._embed_query", _exploding_embed
        )
        assert gs._embed("What is high risk?") is None

    def test_focused_subprovisions_handles_embed_failure_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        monkeypatch.setattr(gs, "_embed", lambda _q: None)

        res = gs.fetch_focused_subprovisions("test", ["Art. 5"])
        assert res == []


# ──────────────────────────────────────────────────────────────────────────
# 4. Aura Driver Failures, Timeouts & Circuit Breaker
# ──────────────────────────────────────────────────────────────────────────


class TestAuraCircuitBreakerAndFailures:
    """Test driver errors, timeouts, threadpool saturation, and circuit breaking."""

    def test_driver_exception_records_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FailingClient:
            enabled = True

            def execute_read_strict(self, cypher, params=None):
                raise ConnectionResetError("Neo4j Aura connection dropped")

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: FailingClient()
        )

        rows = kg._bounded_execute_read("RETURN 1", {})
        assert getattr(rows, "failed", False) is True
        assert rows == []

    def test_driver_timeout_cancels_and_fails_soft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class HangingClient:
            enabled = True

            def execute_read_strict(self, cypher, params=None):
                time.sleep(0.5)
                return [{"res": 1}]

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: HangingClient()
        )
        # Force a 10ms budget
        monkeypatch.setenv("REGENOLD_GRAPH_TIMEOUT_MS", "10")

        rows = kg._bounded_execute_read("RETURN 1", {})
        assert getattr(rows, "failed", False) is True
        assert rows == []

    def test_consecutive_failures_trip_circuit_breaker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class CrashingClient:
            enabled = True

            def execute_read_strict(self, cypher, params=None):
                raise RuntimeError("Aura unavailable")

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: CrashingClient()
        )

        assert graph_circuit_open() is False

        for i in range(GRAPH_BREAKER_THRESHOLD):
            kg._bounded_execute_read("RETURN 1", {})

        # Circuit breaker should now be OPEN
        assert graph_circuit_open() is True

        # Subsequent read must short-circuit without calling driver
        read_spy = MagicMock()
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", read_spy
        )
        rows = kg._bounded_execute_read("RETURN 1", {})
        assert getattr(rows, "failed", False) is True
        assert read_spy.call_count == 0

    def test_success_resets_circuit_breaker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record_graph_failure()
        record_graph_failure()
        assert graph_circuit_open() is False

        record_graph_success()

        # Another failure after success should not open breaker
        record_graph_failure()
        assert graph_circuit_open() is False

    def test_admission_saturation_fails_soft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When all admission slots are held, extra requests must fail-soft."""
        # Drain the admission semaphore
        slots = []
        try:
            for _ in range(kg._KG_MAX_INFLIGHT):
                acquired = kg._KG_ADMISSION.acquire(blocking=False)
                if acquired:
                    slots.append(True)

            # Next call cannot acquire admission within 10ms budget
            monkeypatch.setenv("REGENOLD_GRAPH_TIMEOUT_MS", "10")
            rows = kg._bounded_execute_read("RETURN 1", {})
            assert getattr(rows, "failed", False) is True
        finally:
            for _ in slots:
                kg._KG_ADMISSION.release()


# ──────────────────────────────────────────────────────────────────────────
# 5. Strict Grounding & Anti-Leakage Invariants
# ──────────────────────────────────────────────────────────────────────────


class TestGroundingAndAntiLeakage:
    """Ensure non-citable units cannot leak as wire citations or broaden allowlists."""

    def test_focused_subprovisions_constrained_to_cited_ids_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        monkeypatch.setattr(gs, "_embed", lambda _q: [0.5] * 128)

        captured_ids: list[str] = []

        def _mock_read(cypher, params):
            captured_ids.extend(params.get("ids", []))
            return [
                {
                    "cite": "Article 5",
                    "uid": "article_5_1_c",
                    "layer": "point",
                    "text": "Social scoring prohibition.",
                    "score": 0.88,
                }
            ]

        monkeypatch.setattr(kg, "_bounded_execute_read", _mock_read)

        # Retrieve with Article 5 cited
        res = gs.fetch_focused_subprovisions("social scoring", ["Art. 5"])
        assert captured_ids == ["article_5"]
        assert len(res) == 1
        assert res[0]["cite"] == "Article 5"

    def test_unretrieved_article_cannot_slip_into_focus_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If query retrieves Art 50, Art 5 is NOT queried or returned."""
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        monkeypatch.setattr(gs, "_embed", lambda _q: [0.5] * 128)

        captured_ids: list[str] = []

        def _mock_read(cypher, params):
            captured_ids.extend(params.get("ids", []))
            return []

        monkeypatch.setattr(kg, "_bounded_execute_read", _mock_read)

        gs.fetch_focused_subprovisions(
            "social scoring prohibited practice", ["Article 50"]
        )
        assert captured_ids == ["article_50"]
        assert "article_5" not in captured_ids

    def test_supplementary_sections_excludes_kg_when_include_kg_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When mining citation drift allowlist, include_kg=False MUST omit graph context."""
        import app.engines._graph_rag_impl as impl
        from app.engines.graph_rag.models import GraphContext

        called = []

        def _fake_render(refs, question=""):
            called.append(True)
            return ["\nKNOWLEDGE-GRAPH QUESTION-FOCUSED SUB-PROVISIONS:\n- Art 5"]

        monkeypatch.setattr(kg, "render_kg_context", _fake_render)

        ctx = GraphContext()
        ctx.question = "Prohibited social scoring?"
        ctx.article_info = [{"cite": "Art. 5", "title": "Prohibited practices", "text": "x"}]

        # Guard mining call
        guard_parts = impl._render_supplementary_sections(ctx, include_kg=False)
        assert len(called) == 0
        assert not any("KNOWLEDGE-GRAPH" in p for p in guard_parts)

        # Prompt generation call
        prompt_parts = impl._render_supplementary_sections(ctx, include_kg=True)
        assert len(called) == 1
        assert any("KNOWLEDGE-GRAPH" in p for p in prompt_parts)

    def test_subpoint_coordinate_omits_none_point(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A subpoint without a parent letter must never render 'point (None)'."""
        monkeypatch.setattr(kg, "fetch_provision_hierarchy", lambda _refs: [])
        monkeypatch.setattr(kg, "fetch_recital_anchors", lambda _refs: [])
        monkeypatch.setattr(kg, "fetch_deontic_context", lambda _refs: [])
        monkeypatch.setattr(
            kg,
            "fetch_subpoint_detail",
            lambda _refs: [
                {
                    "cite": "Article 5",
                    "para": "1",
                    "letter": None,
                    "roman": "ii",
                    "sid": "article_5_1_ii",
                    "text": "Subpoint detail without letter.",
                }
            ],
        )

        rendered = "\n".join(kg.render_kg_context(["Art. 5"]))
        assert "point (None)" not in rendered
        assert "Article 5, paragraph 1, subpoint (ii)" in rendered


# ──────────────────────────────────────────────────────────────────────────
# 6. Cache Key Identity & Collision Audit in app/routes/regenold.py
# ──────────────────────────────────────────────────────────────────────────


class TestCacheKeyIdentity:
    """Verify runtime flags are registered in _engine_cache_key to prevent cross-arm replay."""

    def test_semantic_layers_flag_flips_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "0")
        key_off = _engine_cache_key("What is AI?", None)

        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")
        key_on = _engine_cache_key("What is AI?", None)

        assert key_off != key_on, "REGENOLD_GRAPH_SEMANTIC_LAYERS collision!"

    def test_semantic_gloss_flag_flips_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_SEMANTIC_GLOSS", "0")
        key_off = _engine_cache_key("What is AI?", None)

        monkeypatch.setenv("REGENOLD_SEMANTIC_GLOSS", "1")
        key_on = _engine_cache_key("What is AI?", None)

        assert key_off != key_on, "REGENOLD_SEMANTIC_GLOSS collision!"

    def test_kg_context_flag_flips_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "0")
        key_off = _engine_cache_key("What is AI?", None)

        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        key_on = _engine_cache_key("What is AI?", None)

        assert key_off != key_on, "REGENOLD_KG_CONTEXT collision!"

    def test_kg_deontic_flag_flips_cache_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.routes.regenold import _engine_cache_key

        monkeypatch.setenv("REGENOLD_KG_DEONTIC", "0")
        key_off = _engine_cache_key("What is AI?", None)

        monkeypatch.setenv("REGENOLD_KG_DEONTIC", "1")
        key_on = _engine_cache_key("What is AI?", None)

        assert key_off != key_on, "REGENOLD_KG_DEONTIC collision!"


# ──────────────────────────────────────────────────────────────────────────
# 7. Cypher Syntax & Aura Vector Index Compatibility Check
# ──────────────────────────────────────────────────────────────────────────


class TestCypherSyntaxCompatibility:
    """Check that Cypher queries use non-deprecated Aura constructs."""

    def test_focus_cypher_uses_variable_scope_call(self) -> None:
        """CALL () { ... } is required on Neo4j 5.x Aura to avoid 01N00 warning."""
        assert "CALL () {" in gs._FOCUS_CYPHER
        assert gs._FOCUS_CYPHER.count("CALL () {") >= 1

    def test_gloss_cypher_uses_variable_scope_call(self) -> None:
        assert "CALL () {" in gs._GLOSS_CYPHER

    def test_focus_cypher_indexes_match_seeded_vector_indexes(self) -> None:
        """Verify vector index names match the 7 seeded indexes on Aura."""
        expected_focus_indexes = [
            "v_paragraph_embedding",
            "v_point_embedding",
            "v_subpoint_embedding",
        ]
        for idx in expected_focus_indexes:
            assert f"'{idx}'" in gs._FOCUS_CYPHER

    def test_gloss_cypher_indexes_match_seeded_vector_indexes(self) -> None:
        expected_gloss_indexes = [
            "v_definition_embedding",
            "v_recital_embedding",
        ]
        for idx in expected_gloss_indexes:
            assert f"'{idx}'" in gs._GLOSS_CYPHER


# ──────────────────────────────────────────────────────────────────────────
# 8. Context Budgeting & Text Flattening Adversarial Tests
# ──────────────────────────────────────────────────────────────────────────


class TestContextBudgetingAndFlattening:
    """Test string flattening, line fitting, and budget division under edge conditions."""

    def test_flat_handles_none_and_non_strings(self) -> None:
        assert kg._flat(None, 100) == ""
        assert kg._flat("", 100) == ""
        assert kg._flat(12345, 100) == "12345"
        assert kg._flat(["nested", "list"], 100) == "['nested', 'list']"

    def test_flat_preserves_legal_enumerations_under_ceiling(self) -> None:
        text = "(a) High-risk requirement 1. (b) High-risk requirement 2. " * 20
        flattened = kg._flat(text, 100)
        # Should expand up to hard ceiling if enumeration opener detected
        assert len(flattened) > 100

    def test_fit_complete_lines_zero_or_tiny_budget(self) -> None:
        block = "Line 1\nLine 2\nLine 3"
        res, trimmed = kg._fit_complete_lines(block, 0)
        assert res == ""
        assert trimmed is True

        res, trimmed = kg._fit_complete_lines(block, 3)
        assert res == ""
        assert trimmed is True

        res, trimmed = kg._fit_complete_lines(block, 10)
        assert res == "Line 1"
        assert trimmed is True

    def test_budget_context_parts_behavior_and_reserve_floor(self) -> None:
        """Empty input returns empty. Reserved markers have a 4000-char floor allocation."""
        assert kg._budget_context_parts([], 1000) == ([], False)

        # Unreserved section with zero limit gets trimmed to empty
        unreserved = ["\nUNRESERVED SECTION:\n- Some text here"]
        out_unres, trimmed = kg._budget_context_parts(unreserved, 0)
        assert out_unres == []
        assert trimmed is True

        # Reserved marker sections receive the max(4000, limit // 2) floor
        reserved = ["\nKNOWLEDGE-GRAPH DEFINITIONS:\n- Term: description"]
        out_res, trimmed_res = kg._budget_context_parts(reserved, 2000)
        assert len(out_res) == 1
        assert "KNOWLEDGE-GRAPH DEFINITIONS" in out_res[0]

    def test_render_kg_context_handles_empty_or_whitespace_question(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """render_kg_context must succeed when question is empty or none."""
        monkeypatch.setenv("REGENOLD_KG_CONTEXT", "1")
        monkeypatch.setenv("REGENOLD_GRAPH_SEMANTIC_LAYERS", "1")

        # Question empty -> semantic layers return []
        parts = kg.render_kg_context(["Art. 5"], question="")
        assert isinstance(parts, list)

        # Question None -> safe fallback
        parts_none = kg.render_kg_context(["Art. 5"], question=None)  # type: ignore[arg-type]
        assert isinstance(parts_none, list)

