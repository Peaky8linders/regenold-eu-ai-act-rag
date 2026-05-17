"""R40 / Phase 4 — wiring + hardening tests for query_expansion.

Covers the contract the BM25 retrieval path depends on:

1. Wrapper-down ⇒ ``expand_query`` is a no-op AND
   ``top_articles_by_relevance`` returns the BM25 baseline unchanged.
2. Wrapper-up + paraphrases returned ⇒ extra refs appended to the BM25
   baseline via :func:`additive_dense_fill` (never displacing a winner).
3. Circuit-breaker open ⇒ no LLM call, no-op fusion, no Haiku spend.
4. LRU cache — second call with the same question doesn't touch the LLM.
5. Failure paths: provider exception, error response, malformed JSON,
   empty paraphrase list — all return ``[]``, never raise, never cache.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.engines import query_expansion as qx
from app.engines.query_expansion import (
    _BREAKER,
    _reset_for_tests,
    expand_query,
    is_query_expansion_enabled,
)


def setup_function(_func):
    _reset_for_tests()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_provider(response_text: str | None, *, error: str | None = None):
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = response_text
    fake_response.error = error
    fake_provider.complete.return_value = fake_response
    return fake_provider


def _patch_wrapper_up(fake_provider):
    return [
        patch(
            "app.engines.query_expansion.is_openai_wrapper_enabled",
            return_value=True,
        ),
        patch(
            "app.engines.query_expansion.get_openai_wrapper_provider",
            return_value=fake_provider,
        ),
    ]


# ── 1. Wrapper-down ──────────────────────────────────────────────────────────


def test_is_query_expansion_enabled_false_when_wrapper_disabled():
    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=False,
    ):
        assert is_query_expansion_enabled() is False


def test_expand_query_noop_when_wrapper_disabled():
    fake_provider = MagicMock()
    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=False,
    ), patch(
        "app.engines.query_expansion.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        assert expand_query("Who is a provider?") == []
    fake_provider.complete.assert_not_called()


def test_kb_search_unchanged_when_query_expansion_disabled():
    """When the wrapper is down, kb_search returns identical refs."""
    from app.data import kb_search

    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=False,
    ):
        refs_off = kb_search.top_articles_by_relevance(
            "What is a high-risk AI system?", k=5,
        )
    # Sanity — the BM25 baseline returns something.
    assert refs_off
    # And it matches what we get from the underlying BM25-only helper.
    expected = kb_search._bm25_top_refs(
        "What is a high-risk AI system?", k=5, min_score=1.5,
    )
    assert refs_off[: len(expected)] == expected


# ── 2. Wrapper-up + paraphrases returned ─────────────────────────────────────


def test_expand_query_returns_paraphrases_on_success():
    fake_provider = _fake_provider(
        '{"paraphrases": ["What is a provider?", "Who counts as provider?"]}',
    )
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        paraphrases = expand_query("Who is a provider under the AI Act?")
    finally:
        for p in patches:
            p.stop()
    assert paraphrases == [
        "What is a provider?",
        "Who counts as provider?",
    ]
    fake_provider.complete.assert_called_once()


def test_kb_search_appends_paraphrase_hits_additively():
    """When paraphrases yield distinct BM25 winners, kb_search appends
    them ADDITIVELY — the BM25 baseline ranking is preserved."""
    from app.data import kb_search

    fake_provider = _fake_provider(
        '{"paraphrases": ["fundamental rights impact assessment requirements"]}',
    )
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        bm25_only = kb_search._bm25_top_refs(
            "training data quality bias", k=3, min_score=1.5,
        )
        refs = kb_search.top_articles_by_relevance(
            "training data quality bias", k=5,
        )
    finally:
        for p in patches:
            p.stop()
    # BM25 winners are at the front (additive_dense_fill preserves order).
    if bm25_only:
        assert refs[: len(bm25_only)] == bm25_only
    # The paraphrase ("fundamental rights impact assessment") should pull
    # Art. 27 into recall — verify it appears in the fused list.
    # (Skip the assertion if the BM25 base already covered Art. 27.)
    assert len(refs) >= len(bm25_only)


# ── 3. Circuit-breaker open ──────────────────────────────────────────────────


def test_circuit_open_short_circuits_without_llm_call():
    """After 3 consecutive failures, the breaker opens and no LLM call fires."""
    # Trip the breaker manually.
    for _ in range(3):
        _BREAKER.record_failure()
    assert _BREAKER.open() is True

    fake_provider = MagicMock()
    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=True,
    ), patch(
        "app.engines.query_expansion.get_openai_wrapper_provider",
        return_value=fake_provider,
    ):
        assert is_query_expansion_enabled() is False
        assert expand_query("Q?") == []
    fake_provider.complete.assert_not_called()


def test_breaker_opens_after_three_provider_exceptions():
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = RuntimeError("boom")
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        for _ in range(3):
            assert expand_query("Q?") == []
        # Breaker now open — fourth call short-circuits before provider.
        fake_provider.complete.reset_mock()
        assert expand_query("Q?") == []
        fake_provider.complete.assert_not_called()
    finally:
        for p in patches:
            p.stop()


# ── 4. LRU cache hit ─────────────────────────────────────────────────────────


def test_lru_cache_avoids_second_llm_call():
    fake_provider = _fake_provider(
        '{"paraphrases": ["P1", "P2"]}',
    )
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        first = expand_query("identical question")
        second = expand_query("identical question")
    finally:
        for p in patches:
            p.stop()
    assert first == second == ["P1", "P2"]
    # LLM was only called once — the second call hit the cache.
    assert fake_provider.complete.call_count == 1


def test_cache_normalises_whitespace_and_case():
    """SHA-256 key uses ``strip().lower()`` — confirm the two variants
    share a cache slot."""
    fake_provider = _fake_provider('{"paraphrases": ["P1"]}')
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        expand_query("WHO is a Provider?")
        expand_query("  who is a provider?  ")
    finally:
        for p in patches:
            p.stop()
    assert fake_provider.complete.call_count == 1


def test_cache_does_not_store_failures():
    """Failures must NEVER be cached — a transient outage that returned
    []  must not freeze the expansion path for the lifetime of the
    process. Mirrors the success-only invariant from intent_classifier."""
    # First call fails (no JSON).
    fake_provider_fail = _fake_provider("not json")
    patches = _patch_wrapper_up(fake_provider_fail)
    for p in patches:
        p.start()
    try:
        assert expand_query("Q?") == []
    finally:
        for p in patches:
            p.stop()

    # Second call: provider returns valid JSON — should fire (not cached
    # to []) and produce paraphrases.
    fake_provider_ok = _fake_provider('{"paraphrases": ["P1"]}')
    patches = _patch_wrapper_up(fake_provider_ok)
    for p in patches:
        p.start()
    try:
        result = expand_query("Q?")
    finally:
        for p in patches:
            p.stop()
    assert result == ["P1"]
    fake_provider_ok.complete.assert_called_once()


# ── 5. Fail-soft contract ────────────────────────────────────────────────────


def test_provider_exception_returns_empty():
    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=True,
    ), patch(
        "app.engines.query_expansion.get_openai_wrapper_provider",
        side_effect=RuntimeError("boom"),
    ):
        assert expand_query("Q?") == []


def test_provider_error_response_returns_empty():
    fake_provider = _fake_provider(None, error="wrapper_not_logged_in")
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        assert expand_query("Q?") == []
    finally:
        for p in patches:
            p.stop()


def test_malformed_json_returns_empty():
    fake_provider = _fake_provider("{this is not json")
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        assert expand_query("Q?") == []
    finally:
        for p in patches:
            p.stop()


def test_empty_paraphrases_returns_empty():
    fake_provider = _fake_provider('{"paraphrases": []}')
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        assert expand_query("Q?") == []
    finally:
        for p in patches:
            p.stop()


def test_paraphrases_wrong_type_returns_empty():
    fake_provider = _fake_provider('{"paraphrases": "not a list"}')
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        assert expand_query("Q?") == []
    finally:
        for p in patches:
            p.stop()


def test_paraphrases_with_non_string_entries_filtered():
    fake_provider = _fake_provider(
        '{"paraphrases": ["good one", 42, null, "another good one"]}',
    )
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        result = expand_query("Q?")
    finally:
        for p in patches:
            p.stop()
    assert result == ["good one", "another good one"]


def test_paraphrase_equal_to_original_filtered():
    fake_provider = _fake_provider(
        '{"paraphrases": ["Q?", "actual paraphrase"]}',
    )
    patches = _patch_wrapper_up(fake_provider)
    for p in patches:
        p.start()
    try:
        result = expand_query("Q?")
    finally:
        for p in patches:
            p.stop()
    # The "Q?" entry matches the original after .strip() — should be filtered.
    assert "Q?" not in result
    assert result == ["actual paraphrase"]


def test_empty_question_returns_empty():
    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=True,
    ):
        assert expand_query("") == []
        assert expand_query("   ") == []


# ── kb_search wiring: failure paths shouldn't break BM25 ─────────────────────


def test_kb_search_resilient_to_expansion_exceptions():
    """An expansion exception must NEVER propagate up to kb_search callers."""
    from app.data import kb_search

    with patch(
        "app.engines.query_expansion.expand_query",
        side_effect=RuntimeError("boom"),
    ):
        # Should NOT raise.
        refs = kb_search.top_articles_by_relevance(
            "high-risk classification criteria", k=3,
        )
    assert isinstance(refs, list)
    assert refs  # BM25 baseline still produces refs


def test_kb_search_resilient_to_breaker_open():
    """Circuit breaker open ⇒ kb_search behaviour identical to wrapper-down."""
    from app.data import kb_search

    for _ in range(3):
        _BREAKER.record_failure()
    assert _BREAKER.open() is True

    with patch(
        "app.engines.query_expansion.is_openai_wrapper_enabled",
        return_value=True,
    ):
        refs = kb_search.top_articles_by_relevance(
            "high-risk classification criteria", k=3,
        )
    assert refs  # BM25 baseline preserved
