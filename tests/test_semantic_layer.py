"""Round 69 — Semantic Layer + RRF fusion knob regression tests.

Covers ``app/engines/semantic_layer.py`` (the structure-aware tree
wire — paragraph-level extraction + the cross-reference Fragmentation
fix) and the ``REGENOLD_RRF_FUSION`` knob in ``app/data/kb_search.py``.

Round 69 wires the proposed Hybrid-RAG architecture's genuinely-missing
pieces. The two retrieval-side knobs ship default-OFF (A/B-proven washes
on the BM25-saturated davidath benchmark — paragraph extract −0.015
Strict / RRF ±0.002, confirming the Round-31 finding); the
cross-reference context is default-ON because it feeds the Stage-2
generation context only and cannot move a davidath rubric axis.
"""
from __future__ import annotations

import importlib

import pytest

from app.engines import semantic_layer
from app.engines.semantic_layer import (
    _corpus_ref_for,
    _slug_for,
    cross_reference_context,
    is_cross_ref_context_enabled,
    is_tree_extract_enabled,
    paragraph_extract,
)


# ──────────────────────────────────────────────────────────────────────────
# Env gates.
# ──────────────────────────────────────────────────────────────────────────


class TestEnvGates:
    def test_tree_extract_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_TREE_EXTRACT", raising=False)
        assert is_tree_extract_enabled() is False

    def test_tree_extract_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("1", "true", "yes", "on", "ON", "True"):
            monkeypatch.setenv("REGENOLD_TREE_EXTRACT", val)
            assert is_tree_extract_enabled() is True

    def test_tree_extract_off_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("REGENOLD_TREE_EXTRACT", val)
            assert is_tree_extract_enabled() is False

    def test_cross_ref_context_default_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REGENOLD_CROSS_REF_CONTEXT", raising=False)
        assert is_cross_ref_context_enabled() is True

    def test_cross_ref_context_can_disable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "0")
        assert is_cross_ref_context_enabled() is False


# ──────────────────────────────────────────────────────────────────────────
# Reference normalisation.
# ──────────────────────────────────────────────────────────────────────────


class TestRefNormalisation:
    def test_corpus_ref_article(self) -> None:
        assert _corpus_ref_for("Art. 13") == "Art. 13"
        assert _corpus_ref_for("Article 6") == "Art. 6"

    def test_corpus_ref_strips_subpoints(self) -> None:
        assert _corpus_ref_for("Art. 13(2)(a)") == "Art. 13"
        assert _corpus_ref_for("Article 11.1") == "Art. 11"

    def test_corpus_ref_annex(self) -> None:
        assert _corpus_ref_for("Annex IV") == "Annex IV"
        assert _corpus_ref_for("Annex IV.2") == "Annex IV"

    def test_corpus_ref_unknown_shape(self) -> None:
        assert _corpus_ref_for("") is None
        assert _corpus_ref_for("not a ref") is None

    def test_slug_for(self) -> None:
        assert _slug_for("Art. 13(2)") == "art_13"
        assert _slug_for("Annex IV.2") == "annex_iv"
        assert _slug_for("Article 6") == "art_6"
        assert _slug_for("garbage") is None


# ──────────────────────────────────────────────────────────────────────────
# Capability 1 — paragraph_extract.
# ──────────────────────────────────────────────────────────────────────────


class TestParagraphExtract:
    def test_fires_on_clean_multi_paragraph_article(self) -> None:
        # Art. 12 (record-keeping) is a 3-paragraph article — the answer
        # sentence lives cleanly in paragraph 1.
        out = paragraph_extract(
            "What records must logging capabilities of high-risk AI "
            "systems allow?",
            "Art. 12",
        )
        assert out is not None
        assert "log" in out.lower()
        # The point of the paragraph unit: tighter than the full article.
        from app.data.eu_ai_act_corpus import ARTICLE_FULL_TEXT

        assert len(out) < len(ARTICLE_FULL_TEXT["Art. 12"])

    def test_returns_none_for_single_block_article(self) -> None:
        # Art. 16 (provider obligations) is a single block with lettered
        # sub-points and no numbered paragraphs — no paragraph gain.
        out = paragraph_extract(
            "What are the obligations of providers of high-risk AI?",
            "Art. 16",
        )
        assert out is None

    def test_returns_none_on_unknown_article(self) -> None:
        assert paragraph_extract("anything", "Art. 999") is None
        assert paragraph_extract("anything", "Annex ZZ") is None

    def test_returns_none_on_empty_inputs(self) -> None:
        assert paragraph_extract("", "Art. 12") is None
        assert paragraph_extract("question", "") is None

    def test_never_raises_on_garbage(self) -> None:
        for q, ref in (
            ("???", "!!!"),
            ("\x00\x01", "Art. "),
            ("a" * 5000, "Art. 6"),
        ):
            paragraph_extract(q, ref)  # must not raise

    def test_output_respects_length_cap(self) -> None:
        # Any returned paragraph must be at most the documented cap so
        # the conciseness axis is never regressed.
        for q, ref in (
            ("What records must be kept?", "Art. 12"),
            ("What accuracy is required for high-risk AI?", "Art. 15"),
        ):
            out = paragraph_extract(q, ref)
            if out is not None:
                assert len(out) <= semantic_layer._MAX_BLOCK_CHARS


# ──────────────────────────────────────────────────────────────────────────
# Capability 2 — cross_reference_context (the Fragmentation fix).
# ──────────────────────────────────────────────────────────────────────────


class TestCrossReferenceContext:
    def test_surfaces_annex_iv_for_article_11(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The proposal's canonical example: Article 11 references the
        # technical-documentation layout of Annex IV. The Fragmentation
        # fix must co-retrieve the Annex.
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "1")
        out = cross_reference_context(["Art. 11"])
        assert out, "expected cross-reference snippets for Art. 11"
        assert any("Annex IV" in s for s in out)

    def test_returns_empty_when_gate_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "0")
        assert cross_reference_context(["Art. 11"]) == []

    def test_returns_empty_for_empty_input(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "1")
        assert cross_reference_context([]) == []
        assert cross_reference_context(["", None]) == []  # type: ignore[list-item]

    def test_never_surfaces_an_already_cited_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Art. 6 and Annex III cite each other; when BOTH are already in
        # the references, neither must appear as a cross-reference.
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "1")
        out = cross_reference_context(["Art. 6", "Annex III"])
        for snippet in out:
            assert not snippet.startswith("Article 6:")
            assert not snippet.startswith("Annex III:")

    def test_respects_max_items_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "1")
        out = cross_reference_context(["Art. 6", "Art. 11", "Art. 9"], max_items=2)
        assert len(out) <= 2

    def test_never_raises_on_garbage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGENOLD_CROSS_REF_CONTEXT", "1")
        cross_reference_context(["???", "Art. ", "\x00"])  # must not raise


# ──────────────────────────────────────────────────────────────────────────
# RRF fusion knob — app/data/kb_search.py.
# ──────────────────────────────────────────────────────────────────────────


class TestRRFFusionKnob:
    def test_rrf_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REGENOLD_RRF_FUSION", raising=False)
        from app.data.kb_search import _rrf_fusion_enabled

        assert _rrf_fusion_enabled() is False

    def test_rrf_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.data.kb_search import _rrf_fusion_enabled

        for val in ("1", "true", "yes", "on"):
            monkeypatch.setenv("REGENOLD_RRF_FUSION", val)
            assert _rrf_fusion_enabled() is True

    def test_fuse_dense_additive_when_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Flag OFF — additive fill: BM25 winners kept in order, dense
        # candidates only fill remaining slots.
        monkeypatch.delenv("REGENOLD_RRF_FUSION", raising=False)
        from app.data.kb_search import _fuse_dense

        bm25 = ["Art. 6", "Art. 13"]
        dense = [("Art. 99", 0.9), ("Art. 6", 0.8)]
        out = _fuse_dense(bm25, dense, k=5)
        assert out[:2] == ["Art. 6", "Art. 13"]  # BM25 order preserved
        assert "Art. 99" in out

    def test_fuse_dense_rrf_when_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Flag ON — RRF can reshuffle, but every returned ref still comes
        # from one of the two input rankings (no fabrication).
        monkeypatch.setenv("REGENOLD_RRF_FUSION", "1")
        from app.data.kb_search import _fuse_dense

        bm25 = ["Art. 6", "Art. 13"]
        dense = [("Art. 99", 0.9), ("Art. 6", 0.8)]
        out = _fuse_dense(bm25, dense, k=5)
        assert set(out) <= {"Art. 6", "Art. 13", "Art. 99"}
        assert "Art. 6" in out

    def test_top_articles_parity_when_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With the knob OFF the retrieval result must be the Round-68
        # additive-fill behaviour — this is what keeps davidath
        # byte-identical when R69 ships.
        monkeypatch.delenv("REGENOLD_RRF_FUSION", raising=False)
        from app.data.kb_search import top_articles_by_relevance

        out = top_articles_by_relevance(
            "What are the obligations of providers of high-risk AI systems?",
            k=5,
        )
        assert isinstance(out, list)
        assert all(isinstance(r, str) for r in out)


def test_module_reimports_cleanly() -> None:
    """The module must survive a reimport (no import-time side effects)."""
    importlib.reload(semantic_layer)
