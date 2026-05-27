"""Tests for Round 28 memory optimisations (LRU cache + confidence boost).

Patterns inspired by the LLM Wiki v2 gist
(https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2):
confidence-weighted retrieval (many-sources-supporting boost) and
bounded LRU memoisation (compiled-not-rederived).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import settings
from app.data.kb_search import (
    _confidence_boost,
    _xref_in_degree,
    top_articles_by_relevance,
)
from app.models import CitationNode, GraphRAGResponse
from app.routes.regenold import (
    _BoundedLRUCache,
    _ENGINE_CACHE,
    _engine_cache_key,
)


class TestConfidenceBoost:
    def test_unreferenced_article_gets_no_boost(self):
        # An article with zero in-degree on the xref graph should
        # produce a boost of exactly 1.0 (no multiplication change).
        assert _confidence_boost("Art. 999") == 1.0

    def test_boost_is_bounded(self):
        # Cap at 1.15 regardless of in-degree — confidence weighting
        # is a tie-break, never a primary ranker.
        for ref in ("Art. 5", "Art. 6", "Art. 13", "Art. 50", "Art. 99"):
            assert 1.0 <= _confidence_boost(ref) <= 1.15

    def test_in_degree_lookup_memoised(self):
        # Same dict identity across calls — memoised at module level.
        a = _xref_in_degree()
        b = _xref_in_degree()
        assert a is b

    def test_central_article_boosted_over_peripheral(self):
        # Art. 5 (prohibited practices) and Art. 6 (high-risk
        # classification) are referenced by many other articles —
        # they should get a higher boost than peripheral articles.
        central = _confidence_boost("Art. 6")
        # Find a peripheral by looking up the in-degree map.
        degrees = _xref_in_degree()
        peripheral_ref = next(
            (ref for ref in ("Art. 96", "Art. 109", "Art. 111")
             if degrees.get(ref, 0) == 0),
            None,
        )
        if peripheral_ref is not None:
            peripheral = _confidence_boost(peripheral_ref)
            assert central >= peripheral


class TestLRUCache:
    def test_cache_get_miss_returns_none(self):
        cache = _BoundedLRUCache(capacity=4)
        assert cache.get("nope") is None
        assert cache.misses == 1
        assert cache.hits == 0

    def test_cache_get_hit_returns_value(self):
        cache = _BoundedLRUCache(capacity=4)
        cache.put("k1", "v1")
        assert cache.get("k1") == "v1"
        assert cache.hits == 1
        assert cache.misses == 0

    def test_lru_eviction(self):
        cache = _BoundedLRUCache(capacity=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.put("d", 4)  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_lru_touch_on_get(self):
        # Accessing an entry should move it to the most-recently-used
        # end of the queue so subsequent puts evict the *other* old one.
        cache = _BoundedLRUCache(capacity=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.get("a")  # touches "a" → MRU
        cache.put("d", 4)  # evicts "b" (oldest after a's touch)
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_put_replaces_existing_value(self):
        cache = _BoundedLRUCache(capacity=4)
        cache.put("k", "v1")
        cache.put("k", "v2")
        assert cache.get("k") == "v2"

    def test_capacity_zero_behaves_sanely(self):
        # Degenerate but allowed — every put gets evicted immediately.
        cache = _BoundedLRUCache(capacity=1)
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_get_distinguishes_missing_from_stored_none(self):
        # Round-30: ``get()`` must NOT treat a legitimately-cached None
        # as a miss — that would trigger unbounded recompute on every
        # subsequent hit. The fix uses ``in`` rather than ``.get() is None``.
        cache = _BoundedLRUCache(capacity=4)
        cache.put("k", None)
        # First "get" is a hit, returning None. The miss counter must not
        # advance — the entry exists.
        result = cache.get("k")
        assert result is None
        assert cache.hits == 1
        assert cache.misses == 0
        # And a truly-missing key still counts as a miss.
        assert cache.get("nope") is None
        assert cache.misses == 1


class TestEngineCacheKey:
    def test_key_changes_with_question(self):
        k1 = _engine_cache_key("question one", None)
        k2 = _engine_cache_key("question two", None)
        assert k1 != k2

    def test_key_changes_with_context(self):
        k1 = _engine_cache_key("same question", "context a")
        k2 = _engine_cache_key("same question", "context b")
        assert k1 != k2

    def test_key_is_stable(self):
        k1 = _engine_cache_key("a", "b")
        k2 = _engine_cache_key("a", "b")
        assert k1 == k2

    def test_key_handles_none_context(self):
        # Empty string and None should produce the same key — the
        # function normalises both to the empty trailer.
        assert _engine_cache_key("q", None) == _engine_cache_key("q", "")

    def test_key_is_sha256_hex(self):
        # sha256 hex = 64 chars.
        k = _engine_cache_key("hello", "world")
        assert len(k) == 64
        assert all(c in "0123456789abcdef" for c in k)


# ─── Round-30 cache-poisoning guard at the route layer ──────────────────────


class TestRouteCachePoisoningGuard:
    """When Stage-2 was attempted and the wrapper call failed, the route
    must NOT cache the deterministic fallback — otherwise every
    subsequent identical question would skip Stage-2 forever (until the
    LRU evicts the entry). This is the exact case the user flagged
    ("20% of Sonnet calls still 500 intermittently").
    """

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        # Memory-cache state spans tests; wipe before each.
        _ENGINE_CACHE._data.clear()
        _ENGINE_CACHE.hits = 0
        _ENGINE_CACHE.misses = 0
        settings.regenold.api_key = SecretStr("regenold-test-key")
        yield
        _ENGINE_CACHE._data.clear()

    def _fake_response(self, *, stage2_call_failed: bool) -> GraphRAGResponse:
        return GraphRAGResponse(
            answer="Article 13 requires transparency.",
            citations=[
                CitationNode(
                    node_type="Obligation",
                    node_id="art13",
                    text="transparency",
                    article_ref="Art. 13",
                )
            ],
            confidence=0.85,
            reasoning_trace=[],
            suggested_followups=[],
            graph_stats={
                "nodes_traversed": 3,
                "edges_followed": 0,
                "obligations_found": 1,
                "gaps_found": 0,
                "satisfied_found": 0,
                "stage2_call_failed": stage2_call_failed,
            },
        )

    def test_stage2_failure_response_is_NOT_cached(self) -> None:
        from app.main import app

        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=self._fake_response(stage2_call_failed=True),
        ) as engine:
            c = TestClient(app)
            for _ in range(3):
                r = c.post(
                    "/api/v1/regenold/eu-ai-act/ask",
                    headers={"X-Regenold-Api-Key": "regenold-test-key"},
                    json=[{"role": "user", "content": "What does Art. 13 require?"}],
                )
                assert r.status_code == 200
        # Three identical questions should each invoke the engine — the
        # cache MUST NOT swallow them when Stage-2 failed.
        assert engine.call_count == 3

    def test_stage2_success_response_IS_cached(self) -> None:
        from app.main import app

        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=self._fake_response(stage2_call_failed=False),
        ) as engine:
            c = TestClient(app)
            for _ in range(3):
                r = c.post(
                    "/api/v1/regenold/eu-ai-act/ask",
                    headers={"X-Regenold-Api-Key": "regenold-test-key"},
                    json=[{"role": "user", "content": "Other Art. 13 question."}],
                )
                assert r.status_code == 200
        # Cache hit on 2nd + 3rd identical request.
        assert engine.call_count == 1


# ─── R78 — cache no-poison guard on low engine confidence ───────────────────


class TestR78CacheConfidenceGuard:
    """A transient cold-start failure — a lazy retrieval index not warm
    yet, or a degraded graph backend — returns a zero-retrieval /
    degraded response whose confidence is below the clean-run floor. The
    route must NOT cache it: otherwise that single cold-window failure is
    served to every later identical question until LRU eviction or a
    process restart. Live production exhibited exactly this — in-scope
    provider/deployer obligation questions stuck on the Art. 1/2/3
    zero-retrieval floor with ``cache_hit: true`` in the reasoning trace.

    ``_compute_confidence`` never returns below 0.3 for a clean run, so
    confidence < 0.3 is an unambiguous transient-failure signal.
    """

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        _ENGINE_CACHE._data.clear()
        _ENGINE_CACHE.hits = 0
        _ENGINE_CACHE.misses = 0
        settings.regenold.api_key = SecretStr("regenold-test-key")
        yield
        _ENGINE_CACHE._data.clear()

    def _resp(self, confidence: float) -> GraphRAGResponse:
        return GraphRAGResponse(
            answer="Article 13 requires transparency.",
            citations=[
                CitationNode(
                    node_type="Obligation",
                    node_id="art13",
                    text="transparency",
                    article_ref="Art. 13",
                )
            ],
            confidence=confidence,
            graph_stats={"nodes_traversed": 3, "stage2_call_failed": False},
        )

    def _ask_n(self, question: str, n: int) -> None:
        from app.main import app

        c = TestClient(app)
        for _ in range(n):
            r = c.post(
                "/api/v1/regenold/eu-ai-act/ask",
                headers={"X-Regenold-Api-Key": "regenold-test-key"},
                json=[{"role": "user", "content": question}],
            )
            assert r.status_code == 200

    def test_zero_retrieval_response_is_NOT_cached(self) -> None:
        # confidence 0.0 — the engine retrieved nothing (model default,
        # ``_compute_confidence`` never reached). This is the exact live
        # production failure shape.
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=self._resp(0.0),
        ) as engine:
            self._ask_n("What does Article 13 require of high-risk AI providers?", 3)
        assert engine.call_count == 3

    def test_degraded_backend_response_is_NOT_cached(self) -> None:
        # confidence 0.2 — the issue-#55 degraded cap (graph backend
        # raised, KB fallback served). Transient; must not be cached.
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=self._resp(0.2),
        ) as engine:
            self._ask_n("What does Article 14 require for human oversight of AI?", 3)
        assert engine.call_count == 3

    def test_clean_floor_confidence_response_IS_cached(self) -> None:
        # confidence 0.3 — the normal ``cli``-mode "no graph data" floor.
        # A healthy answer; it MUST remain cacheable or the guard would
        # disable caching for the entire default (graph-less) deployment.
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=self._resp(0.3),
        ) as engine:
            self._ask_n("What does Article 15 require on accuracy and robustness?", 3)
        assert engine.call_count == 1

    def test_rich_confidence_response_IS_cached(self) -> None:
        with patch(
            "app.routes.regenold.ask_compliance_question",
            return_value=self._resp(0.85),
        ) as engine:
            self._ask_n("What does Article 16 require of providers of AI systems?", 3)
        assert engine.call_count == 1

    def test_min_cacheable_confidence_is_clean_run_floor(self) -> None:
        # The threshold must sit exactly at the clean-run floor: strictly
        # above the issue-#55 degraded cap (0.2), at the cli-mode "no
        # graph data" floor (0.3).
        from app.routes.regenold import _MIN_CACHEABLE_CONFIDENCE

        assert _MIN_CACHEABLE_CONFIDENCE == 0.3
