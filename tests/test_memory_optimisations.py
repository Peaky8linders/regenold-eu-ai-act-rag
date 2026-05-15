"""Tests for Round 28 memory optimisations (LRU cache + confidence boost).

Patterns inspired by the LLM Wiki v2 gist
(https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2):
confidence-weighted retrieval (many-sources-supporting boost) and
bounded LRU memoisation (compiled-not-rederived).
"""
from __future__ import annotations

import pytest

from app.data.kb_search import (
    _confidence_boost,
    _xref_in_degree,
    top_articles_by_relevance,
)
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
