"""Tests for the sentence-level TF-IDF + SVD embedding index.

Covers:

* :func:`is_available` reflects asset presence on disk.
* :func:`query` returns sentences relevant to canonical regulatory
  queries (real-time biometric → Art. 5; post-market monitoring →
  Art. 72 / 71).
* Edge cases — empty query, all-stopword query, ``top_k=0``,
  unreachable threshold.
* Determinism — repeat calls return byte-identical results.
* ``top_k`` cap is honoured.
* :func:`asset_manifest` returns the expected shape.

The tests assume the assets have been built via
``scripts/build_embeddings_index.py``. The module ships with a
``skip_if_missing`` fixture so these tests skip cleanly on CI runners
that haven't generated the assets.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engines import embeddings_index as ei


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _skip_if_missing() -> None:
    """Skip every test in this module when the assets aren't built.

    The build artefacts live under ``app/engines/_assets/`` and are
    produced by ``scripts/build_embeddings_index.py``. When they're
    missing (clean clone, fresh CI) the runtime module's surface
    contract is ``is_available()==False`` + ``query()==[]`` — which we
    test separately. The substantive retrieval-quality tests need the
    real index, so we skip them here.
    """
    if not ei.is_available():
        pytest.skip("embedding assets not built — run scripts/build_embeddings_index.py")


@pytest.fixture(autouse=True)
def _reset_cache_for_clean_state() -> None:
    """Sanity guard — never tamper with the module cache from a test.

    The cache is intentionally process-wide so warm queries cost ~0.1
    ms. We don't reset it between tests; we just assert nobody else
    has flipped the ``load_failed`` sentinel.
    """
    yield
    # Post-condition: the sticky-fail flag should never be set during
    # a passing test run.
    assert ei._CACHE.load_failed is False  # noqa: SLF001 — module-internal sentinel


# ── is_available + asset_manifest ────────────────────────────────────────


def test_is_available_returns_bool() -> None:
    """``is_available`` returns a plain bool, not None."""
    result = ei.is_available()
    assert isinstance(result, bool)


def test_is_available_true_when_assets_present() -> None:
    """When all 5 files exist, ``is_available`` is True.

    Indirectly tested by the module-level ``_skip_if_missing`` fixture
    (every test in this file is gated on True). Re-asserted here so
    failure surfaces as a meaningful test name, not a skip.
    """
    assert ei.is_available() is True


def test_asset_manifest_shape() -> None:
    """Manifest has the expected keys from the build script."""
    m = ei.asset_manifest()
    assert isinstance(m, dict)
    assert m.get("version") == "1.0"
    assert "generated_date" in m
    assert "total_sentences" in m
    assert "vector_dim" in m
    assert "vocab_size" in m
    assert "sha256_hashes" in m
    # All four hashed assets should be present.
    hashes = m["sha256_hashes"]
    assert set(hashes.keys()) == {
        ei.EMBED_FILENAME,
        ei.META_FILENAME,
        ei.SVD_FILENAME,
        ei.VOCAB_FILENAME,
    }
    # Each hash is a 64-hex-char sha256.
    for name, h in hashes.items():
        assert isinstance(h, str), name
        assert len(h) == 64, name
        int(h, 16)  # raises ValueError on non-hex


def test_asset_manifest_vector_dim_128() -> None:
    """The SVD projection target is always 128 — pinned for reproducibility."""
    m = ei.asset_manifest()
    assert m["vector_dim"] == 128


def test_asset_manifest_total_sentences_positive() -> None:
    """The corpus produces a sane number of sentences (≈ 900)."""
    m = ei.asset_manifest()
    n = m["total_sentences"]
    assert isinstance(n, int)
    assert 500 < n < 5000, n  # 949 raw / 919 after filter — generous band


# ── query — semantic retrieval quality ───────────────────────────────────


def test_query_real_time_biometric_returns_art5() -> None:
    """A canonical Art. 5(1)(h) phrase routes to Art. 5 with similarity > 0.3.

    The task brief locked this assertion in — the dense path's main
    job is paraphrase recall on prohibited-practice queries.
    """
    hits = ei.query("real-time biometric")
    assert hits, "expected at least one hit for real-time biometric"
    # At least one of the top 10 hits is in Art. 5.
    art5_hits = [h for h in hits if h.article_ref == "Art. 5"]
    assert art5_hits, f"no Art. 5 in top-10: {[h.article_ref for h in hits]}"
    assert max(h.similarity for h in art5_hits) > 0.3


def test_query_post_market_monitoring_returns_art61_or_72() -> None:
    """Post-market monitoring is the named Art. 61 / Art. 72 obligation.

    The Round-31 corpus puts the substantive post-market monitoring
    clauses in Art. 72 (and the Chapter heading in Art. 71). Either is
    a valid hit — the lower-bound 0.2 captures both routings.
    """
    hits = ei.query("post-market monitoring")
    assert hits
    pm_hits = [h for h in hits if h.article_ref in {"Art. 61", "Art. 71", "Art. 72"}]
    assert pm_hits, f"expected Art. 61/71/72: {[h.article_ref for h in hits[:5]]}"
    assert max(h.similarity for h in pm_hits) > 0.2


def test_query_empty_string_returns_empty() -> None:
    """An empty query returns ``[]`` — no exception, no hits."""
    assert ei.query("") == []


def test_query_whitespace_only_returns_empty() -> None:
    """Whitespace-only queries collapse to no tokens → ``[]``."""
    assert ei.query("   \t\n  ") == []


def test_query_all_stopwords_returns_empty() -> None:
    """Queries that tokenise to zero in-vocab tokens return ``[]``.

    The shared stopword list strips every term — there's no signal to
    project so the query short-circuits before the SVD step.
    """
    # All terms in the local tokenizer's stopword set.
    assert ei.query("the and is of for to") == []


# ── Edge cases on knobs ──────────────────────────────────────────────────


def test_query_top_k_zero_returns_empty() -> None:
    """``top_k=0`` short-circuits before the matmul."""
    assert ei.query("biometric", top_k=0) == []


def test_query_top_k_caps_result_count() -> None:
    """The result length never exceeds the requested ``top_k``.

    Asserting ``len == top_k`` requires the corpus has at least
    ``top_k`` viable hits — for ``top_k=3`` on a broad regulatory query
    that's guaranteed (the 919-sentence corpus has thousands of
    above-zero matches for any common query).
    """
    hits = ei.query("data processing", top_k=3)
    assert len(hits) == 3
    # And the broader corpus has many more candidates.
    hits_wide = ei.query("data processing", top_k=50)
    assert len(hits_wide) >= 3
    assert len(hits_wide) <= 50


def test_query_threshold_above_one_returns_empty() -> None:
    """Cosine similarity is bounded by 1 — threshold=0.99 yields ``[]``.

    Not literally empty in 100% of corpora (some duplicate sentences
    can hit cosine 1.0), but for ANY query "biometric" the top hit
    won't exceed 0.95 cosine against our 128-D projection, so 0.99 is
    a safe upper bound for emptiness.
    """
    hits = ei.query("biometric", threshold=0.99)
    assert hits == []


def test_query_threshold_zero_keeps_everything() -> None:
    """A threshold of 0.0 (default) keeps non-anti-correlated hits."""
    hits = ei.query("biometric")
    assert hits
    assert all(h.similarity >= 0.0 for h in hits)


# ── Determinism ──────────────────────────────────────────────────────────


def test_query_is_deterministic_across_calls() -> None:
    """Same input → byte-identical output across 100 invocations.

    The TF-IDF + SVD path has no random state — the projection basis
    is fixed on disk, the cosine is a deterministic matmul. We rip 100
    calls to make sure (and to catch any future regression that
    introduces e.g. random tie-breaking).
    """
    baseline = ei.query("data processing high-risk", top_k=10)
    assert baseline, "fixture query must yield hits for determinism check"
    # Use a tuple-of-tuples key to compare cheaply.
    key0 = tuple(
        (h.article_ref, h.sent_idx, round(h.similarity, 6)) for h in baseline
    )
    for _ in range(100):
        h = ei.query("data processing high-risk", top_k=10)
        key_i = tuple(
            (x.article_ref, x.sent_idx, round(x.similarity, 6)) for x in h
        )
        assert key_i == key0


def test_query_sorted_descending_by_similarity() -> None:
    """The returned hits are sorted descending by ``similarity``."""
    hits = ei.query("post-market monitoring", top_k=10)
    assert len(hits) >= 2
    sims = [h.similarity for h in hits]
    assert sims == sorted(sims, reverse=True)


# ── EmbeddingHit dataclass invariants ────────────────────────────────────


def test_embedding_hit_is_frozen_dataclass() -> None:
    """``EmbeddingHit`` is immutable — protects against accidental mutation."""
    hit = ei.EmbeddingHit(
        article_ref="Art. 5", sent_idx=3, text="example", similarity=0.5
    )
    with pytest.raises((AttributeError, TypeError)):
        hit.similarity = 0.9  # type: ignore[misc]


def test_embedding_hit_similarity_in_range() -> None:
    """All returned similarities are in the cosine range [-1, 1]."""
    hits = ei.query("biometric identification system", top_k=20)
    for h in hits:
        assert -1.0001 <= h.similarity <= 1.0001, h


def test_embedding_hit_article_ref_matches_corpus() -> None:
    """Every hit's ``article_ref`` is a known key in ``ARTICLE_FULL_TEXT``."""
    from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT

    hits = ei.query("technical documentation", top_k=15)
    for h in hits:
        assert h.article_ref in ARTICLE_FULL_TEXT, h.article_ref


def test_warm_up_does_not_raise() -> None:
    """``warm_up`` is idempotent + non-raising even on repeat invocation."""
    ei.warm_up()
    ei.warm_up()
    ei.warm_up()
    assert ei.is_available()


# ── Asset-file consistency ───────────────────────────────────────────────


def test_assets_manifest_hash_matches_files() -> None:
    """SHA-256 in the manifest matches the on-disk asset bytes.

    Tampering or corruption would surface as a mismatch — catches a
    common deploy footgun (the operator forgot to re-run the builder
    after editing the corpus).
    """
    import hashlib

    m = ei.asset_manifest()
    assets_dir = Path(ei._ASSETS_DIR)  # noqa: SLF001 — read-only access
    for name, expected_hash in m["sha256_hashes"].items():
        path = assets_dir / name
        assert path.exists(), name
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        assert h.hexdigest() == expected_hash, name
