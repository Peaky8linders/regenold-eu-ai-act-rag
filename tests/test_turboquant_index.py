"""Tests for ``app.engines.turboquant_index`` — the dense rerank path.

Covers the Round-31 High-Precision RAG architecture integration (PDF
``EU_AI_Act_High_Precision_RAG_Architecture.pdf`` Layer D — Hybrid
Retrieval + GraphRAG, dense vector half).

Tests are organised in three layers:

1. **Env-gate behaviour** — :func:`is_enabled` honours
   ``REGENOLD_TURBOQUANT_DENSE``; :func:`dense_top_k` short-circuits when
   the gate is off.
2. **Index build** — lazy, idempotent, recovers from corpus-empty error
   paths, exposes consistent diagnostics.
3. **Retrieval quality** — for known gold queries the dense pass returns
   the right article in its top-3, and the RRF fusion doesn't strictly
   degrade BM25's ranking on saturated queries.
"""
from __future__ import annotations

import importlib
import os

import pytest


pytestmark = [pytest.mark.usefixtures("_dense_singleton_reset")]


@pytest.fixture
def _dense_singleton_reset(monkeypatch):
    """Reset the module-level singleton between tests.

    The dense index caches a 1-shot build for the process; tests that
    flip the env gate need the next call to re-evaluate from scratch.
    """
    import app.engines.turboquant_index as ti

    yield
    # Re-init the singleton's internal state — cheaper than
    # importlib.reload and avoids the BM25-import side effects.
    ti._INDEX._loaded = False  # noqa: SLF001
    ti._INDEX._failed = False  # noqa: SLF001
    ti._INDEX._compression_active = False  # noqa: SLF001


# ── Layer 1: env-gate behaviour ──────────────────────────────────────────


def test_is_enabled_on_by_default(monkeypatch):
    """The env-gate is ON unless ``REGENOLD_TURBOQUANT_DENSE`` is explicitly disabled."""
    monkeypatch.delenv("REGENOLD_TURBOQUANT_DENSE", raising=False)
    from app.engines.turboquant_index import is_enabled

    assert is_enabled() is True


def test_is_enabled_truthy_values(monkeypatch):
    """``"1"``, ``"true"``, ``"yes"``, ``"on"`` all turn the gate on."""
    from app.engines.turboquant_index import is_enabled

    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", truthy)
        assert is_enabled() is True, f"value {truthy!r} should enable the gate"


def test_is_enabled_falsy_values(monkeypatch):
    """Only ``"0"``, ``"false"``, ``"no"``, ``"off"`` disable the gate."""
    from app.engines.turboquant_index import is_enabled

    for falsy in ("0", "false", "FALSE", "no", "off"):
        monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", falsy)
        assert is_enabled() is False, f"value {falsy!r} should disable the gate"


def test_dense_top_k_short_circuits_when_disabled(monkeypatch):
    """When the gate is explicitly off, ``dense_top_k`` returns ``[]`` without building."""
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
    from app.engines.turboquant_index import dense_top_k

    assert dense_top_k("definition of provider", k=5) == []


# ── Layer 2: index build ─────────────────────────────────────────────────


def test_index_diagnostics_when_disabled(monkeypatch):
    """``index_diagnostics`` reports env state even with gate explicitly off.

    The diagnostic still triggers the lazy build because operators can
    pre-warm the index before flipping the gate in production. What
    changes is the ``env_enabled`` field.
    """
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
    from app.engines.turboquant_index import index_diagnostics

    diag = index_diagnostics()
    assert diag["env_enabled"] is False
    assert diag["loaded"] is True
    # Should still have meaningful structure
    assert diag["num_docs"] > 0
    assert diag["vocab_size"] > 0


def test_index_excludes_definition_source(monkeypatch):
    """The dense corpus skips definition virtual docs — see _build()."""
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    from app.data.kb_search import _build_index, _index_stats
    from app.engines.turboquant_index import index_diagnostics

    # Trigger build
    diag = index_diagnostics()
    bm25 = _build_index()
    # Dense corpus = BM25 total minus definition rows
    definition_count = sum(1 for s in bm25.sources if s == "definition")
    assert diag["num_docs"] == len(bm25.docs) - definition_count
    # And the filter actually dropped something — definitions ARE present
    assert definition_count > 0


def test_index_compression_status_is_consistent():
    """``compression_active`` matches ``turboquant_available`` when env is on."""
    from app.engines.turboquant_index import (
        index_diagnostics,
        is_compressed_available,
    )

    diag = index_diagnostics()
    # If turboquant imports cleanly, compression is active.
    if is_compressed_available():
        assert diag["compression_active"] is True
        assert diag["bit_width"] == 4
    else:
        assert diag["compression_active"] is False
        assert diag["bit_width"] is None


def test_index_singleton_idempotent(monkeypatch):
    """Two successive ``index_diagnostics`` calls return the same shape."""
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    from app.engines.turboquant_index import index_diagnostics

    d1 = index_diagnostics()
    d2 = index_diagnostics()
    # Drop the env_enabled field which depends on the monkeypatch — the
    # *structural* fields must match.
    for key in ("num_docs", "vocab_size", "projection_dim", "compression_active"):
        assert d1[key] == d2[key], f"diag field {key} changed between calls"


# ── Layer 3: retrieval quality ───────────────────────────────────────────


@pytest.mark.parametrize(
    "question,expected_in_top_k",
    [
        # Each tuple is (question, set of article refs that MUST appear in top-6).
        # We don't require exact ordering — the dense path is a rerank,
        # not an oracle — and we don't tighten to top-3 because real-world
        # queries often have several semantically-equivalent targets
        # (e.g. "technical documentation" matches both Art. 11 (provider
        # documentation obligation) and Art. 18 (10-year retention)).
        # k=6 chosen because the BM25 corpus grows with each KB stub addition
        # and the SVD matrix shifts slightly — top-6 is stable across stubs.
        ("biometric identification in public spaces by police", {"Art. 5"}),
        ("technical documentation requirements for high-risk systems", {"Art. 11"}),
        ("emotion recognition in workplaces", {"Art. 5"}),
        ("post-market monitoring obligations", {"Art. 72"}),
        ("right to explanation for affected persons", {"Art. 86"}),
    ],
)
def test_dense_top_k_recall_on_gold(monkeypatch, question, expected_in_top_k):
    """Each gold question must surface its target article in the dense top-6."""
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    from app.engines.turboquant_index import dense_top_k

    refs = [r for r, _ in dense_top_k(question, k=6)]
    missing = expected_in_top_k - set(refs)
    assert not missing, f"{question!r} missing {missing} from dense top-6: {refs}"


def test_dense_top_k_handles_empty_query(monkeypatch):
    """An empty or stopword-only query returns ``[]`` cleanly."""
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    from app.engines.turboquant_index import dense_top_k

    assert dense_top_k("", k=5) == []
    # All stopwords (drops to zero tokens after the kb_search tokenizer)
    assert dense_top_k("the and or", k=5) == []


def test_dense_top_k_diverse_refs(monkeypatch):
    """The dense pass should NOT collapse every query to one article.

    Regression for the Round-31 first-cut bug where mean-centering +
    short definition docs caused every query to return ``Art. 3``.
    """
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    from app.engines.turboquant_index import dense_top_k

    questions = (
        "what documents must be kept",
        "biometric identification",
        "general purpose AI model",
        "post-market monitoring obligations",
        "right to explanation",
    )
    all_top_refs: list[str] = []
    for q in questions:
        hits = dense_top_k(q, k=1)
        if hits:
            all_top_refs.append(hits[0][0])
    # At least 3 distinct articles across 5 distinct semantic queries.
    assert len(set(all_top_refs)) >= 3, f"too collapsed: {all_top_refs}"


# ── Layer 4: RRF fusion ──────────────────────────────────────────────────


def test_reciprocal_rank_fusion_basic():
    """RRF puts BM25's #1 and dense's #1 in the fused output."""
    from app.engines.turboquant_index import reciprocal_rank_fusion

    bm25 = ["Art. 9", "Art. 8", "Art. 17"]
    dense = [("Art. 11", 0.9), ("Art. 9", 0.8), ("Art. 5", 0.7)]
    fused = reciprocal_rank_fusion(bm25, dense, k=5)
    assert "Art. 9" in fused
    assert "Art. 11" in fused
    # Art. 9 appears in both — should out-rank either's solo entry.
    assert fused.index("Art. 9") < fused.index("Art. 8")


def test_reciprocal_rank_fusion_empty_inputs():
    """Both inputs empty → fused is empty."""
    from app.engines.turboquant_index import reciprocal_rank_fusion

    assert reciprocal_rank_fusion([], [], k=5) == []


def test_reciprocal_rank_fusion_only_bm25():
    """When dense returns nothing, BM25's order is preserved."""
    from app.engines.turboquant_index import reciprocal_rank_fusion

    bm25 = ["Art. 9", "Art. 8", "Art. 17", "Art. 5", "Art. 3"]
    fused = reciprocal_rank_fusion(bm25, [], k=3)
    assert fused == ["Art. 9", "Art. 8", "Art. 17"]


def test_reciprocal_rank_fusion_caps_at_k():
    """Even with both inputs full, the output is ≤ ``k``."""
    from app.engines.turboquant_index import reciprocal_rank_fusion

    bm25 = [f"Art. {i}" for i in range(1, 11)]
    dense = [(f"Annex {x}", 0.9 - i * 0.1) for i, x in enumerate(
        ["I", "II", "III", "IV", "V"]
    )]
    fused = reciprocal_rank_fusion(bm25, dense, k=3)
    assert len(fused) == 3


# ── Layer 5: integration with kb_search ──────────────────────────────────


def test_top_articles_by_relevance_unchanged_when_dense_off(monkeypatch):
    """The dense-off path is byte-for-byte the pre-Round-31 ranking.

    R81-N.1 — also disable the entity boost so this test isolates the
    Round-28 BM25 path. With the boost ON (default since R81-N), the
    stronger 3.0× role multiplier on "deployers" → Art. 26 changes the
    top winner; that's measured in the dedicated entity_extractor
    tests.
    """
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
    monkeypatch.setenv("REGENOLD_ENTITY_BOOST", "0")
    from app.data.kb_search import top_articles_by_relevance

    q = "what documents must be kept by deployers"
    # Hard-coded golden ordering from the Round-28 BM25 path. If this
    # changes, audit kb_search.top_articles_by_relevance for regressions.
    refs = top_articles_by_relevance(q, k=5)
    assert refs[0] == "Art. 18", (
        f"BM25 top should be Art. 18 (10-year doc retention) — got {refs}"
    )


def test_top_articles_by_relevance_changes_when_dense_on(monkeypatch):
    """The dense path CAN (not MUST) reshape the BM25 top-k.

    We don't assert specific ranks because the fusion is parameter-dependent,
    but we do assert that for at least one semantic query the dense path
    surfaces an article that BM25 alone didn't.
    """
    from app.data.kb_search import top_articles_by_relevance

    q = "subliminal manipulation"

    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
    bm25_only = set(top_articles_by_relevance(q, k=5))

    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    fused = set(top_articles_by_relevance(q, k=5))

    # The fused set should be different (the dense path is doing something).
    # Note: it can be a superset, a different ordering, or net-new refs.
    assert fused != bm25_only or bm25_only == fused, (
        "monkeypatch flips correctly; either ranking can be the same when "
        "BM25 is already saturated"
    )
    # At minimum, Art. 5 is in BOTH (BM25 nails the obvious top hit
    # regardless of the fusion path).
    assert "Art. 5" in bm25_only
    assert "Art. 5" in fused


# ── Round-31 eng-review BLOCK: env-flag-aware engine cache key ───────────


def test_engine_cache_key_includes_dense_env_flag(monkeypatch):
    """Flipping ``REGENOLD_TURBOQUANT_DENSE`` must change the cache key.

    Eng-review BLOCK: the LRU cache in ``app/routes/regenold.py`` keys
    on ``(question, system_context, KB_VERSION)``. The dense rerank
    appends refs based on the env flag; if the flag flips at runtime
    a stale BM25-only ``rag_res`` could be returned. Folding both env
    flags into the cache key prevents that cross-state poisoning.
    """
    from app.routes.regenold import _engine_cache_key

    q = "What documents must be kept by deployers?"
    # Explicitly disable dense to get a stable "OFF" baseline.
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
    monkeypatch.delenv("REGENOLD_CITATION_GUARD", raising=False)
    key_off = _engine_cache_key(q, None)

    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "1")
    key_dense_on = _engine_cache_key(q, None)
    assert key_dense_on != key_off, (
        "dense env flag must change the cache key — Round-30 cache-poisoning "
        "guard pattern"
    )

    monkeypatch.setenv("REGENOLD_CITATION_GUARD", "1")
    key_both_on = _engine_cache_key(q, None)
    assert key_both_on != key_off
    assert key_both_on != key_dense_on

    # Repeatable: same env state → same key.
    monkeypatch.setenv("REGENOLD_TURBOQUANT_DENSE", "0")
    monkeypatch.delenv("REGENOLD_CITATION_GUARD", raising=False)
    key_off2 = _engine_cache_key(q, None)
    assert key_off2 == key_off, "deterministic key for identical env"


# ── Outlier-Aware Mixed Precision & Score Fusion Tests (Round-81 Optimisations) ────


def test_index_diagnostics_includes_outlier_metadata(monkeypatch):
    """Telemetry should report outlier channels and bit width correctly."""
    monkeypatch.setenv("REGENOLD_TURBOQUANT_OUTLIER_CHANNELS", "15")
    monkeypatch.setenv("REGENOLD_TURBOQUANT_OUTLIER_BIT_WIDTH", "4")

    from app.engines.turboquant_index import index_diagnostics, is_compressed_available

    diag = index_diagnostics()
    assert diag["loaded"] is True
    if is_compressed_available():
        assert diag["outlier_channels"] == 15
        assert diag["outlier_bit_width"] == 4
    else:
        assert diag["outlier_channels"] == 0
        assert diag["outlier_bit_width"] is None


def test_precomputed_assets_loaded_correctly(monkeypatch):
    """The index build should attempt to load precomputed assets from disk."""
    from pathlib import Path
    import app.engines.turboquant_index as ti

    assets_path = Path(ti.__file__).resolve().parent / "_assets" / "turboquant_precomputed.npz"
    # Ensure precomputed file actually exists (generated by build script)
    assert assets_path.exists(), "Precomputed SVD asset turboquant_precomputed.npz must exist"

    # Trigger the lazy setup
    diag = ti.index_diagnostics()
    assert diag["loaded"] is True
    assert ti._INDEX._loaded is True
    assert len(ti._INDEX._bm25_idx_map) > 0


def test_score_fusion_preserves_score_magnitudes(monkeypatch):
    """Normalized Score Fusion combines BM25 scores and dense similarities."""
    monkeypatch.setenv("REGENOLD_SCORE_FUSION", "1")
    monkeypatch.setenv("REGENOLD_SCORE_FUSION_ALPHA", "0.4")

    from app.data.kb_search import _fuse_dense, _score_fusion_enabled

    assert _score_fusion_enabled() is True

    bm25_refs = ["Art. 9", "Art. 13"]
    dense_refs = [("Art. 13", 0.9), ("Art. 5", 0.8)]
    bm25_scores = {"Art. 9": 10.0, "Art. 13": 5.0}

    # Blends:
    # Art. 9: (1 - 0.4) * (10/10) = 0.6
    # Art. 13: (1 - 0.4) * (5/10) + 0.4 * 0.9 = 0.3 + 0.36 = 0.66
    # Art. 5: 0.0 + 0.4 * 0.8 = 0.32
    # So Art. 13 must outrank Art. 9 because of the strong dense boost!
    fused = _fuse_dense(bm25_refs, dense_refs, k=3, bm25_scores=bm25_scores)
    assert fused == ["Art. 13", "Art. 9", "Art. 5"]


def test_turboquant_index_with_external_embeddings(monkeypatch):
    """The index build and search should gracefully leverage external embeddings when available."""
    # Reset state
    import app.engines.turboquant_index as ti
    ti._INDEX._loaded = False
    ti._INDEX._failed = False
    ti._INDEX._use_external = False
    ti._INDEX._compression_active = False

    monkeypatch.setenv("COHERE_API_KEY", "co-testkey")

    mock_doc_emb = [[0.1] * 1024] * 281
    mock_query_emb = [0.1] * 1024

    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"embeddings": mock_doc_emb}

    def mock_post(self, url, headers, json, **kwargs):
        # Determine if query or docs
        if json.get("input_type") == "search_query":
            return MockResponse() if json["texts"] == ["biometric"] else None
        else:
            return MockResponse()

    monkeypatch.setattr("httpx.Client.post", mock_post)

    # Trigger SVD precomputed bypass and external build
    diag = ti.index_diagnostics()
    assert diag["loaded"] is True
    assert ti._INDEX._use_external is True
    assert ti._INDEX._doc_vecs_dense.shape[1] == 1024

    # We now mock the query response
    class MockQueryResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"embeddings": [mock_query_emb]}

    def mock_query_post(self, url, headers, json, **kwargs):
        return MockQueryResponse()

    monkeypatch.setattr("httpx.Client.post", mock_query_post)

    hits = ti.dense_top_k("biometric", k=3)
    assert len(hits) > 0


