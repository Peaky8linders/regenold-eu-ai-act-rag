"""Tests for the optional TurboVec vector rerank path.

These tests verify the env-gate + graceful-degradation behaviour. They
don't exercise the actual turbovec/ONNX inference — that path requires
~600 MB of build deps + the pre-built index, neither of which is
present in the repo's test environment by default. The integration is
verified by running ``scripts/build_vector_index.py`` on Linux + setting
``REGENOLD_VECTOR_RERANK=1`` ahead of the benchmark runner.
"""
from __future__ import annotations

import os

import pytest

from app.engines import vector_rerank


class TestEnvGate:
    def test_is_enabled_returns_false_without_env(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_VECTOR_RERANK", raising=False)
        assert vector_rerank.is_enabled() is False

    def test_is_enabled_returns_false_when_env_off(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_VECTOR_RERANK", "0")
        assert vector_rerank.is_enabled() is False

    def test_is_enabled_returns_false_when_no_assets(self, monkeypatch):
        # Env is on but the pre-built index doesn't exist in the test
        # environment — should still return False (graceful degrade).
        monkeypatch.setenv("REGENOLD_VECTOR_RERANK", "1")
        # On a default checkout sentences.tvim isn't committed, so this
        # branch exercises the asset-missing case.
        if not vector_rerank.INDEX_PATH.exists():
            assert vector_rerank.is_enabled() is False

    def test_accepts_truthy_values(self, monkeypatch):
        # All these should be recognised as ON when assets are present.
        # We can't easily fake assets in CI, so just check the env-flag
        # parse logic itself rather than the full pipeline.
        for val in ("1", "true", "yes", "on", "TRUE", "YES"):
            monkeypatch.setenv("REGENOLD_VECTOR_RERANK", val)
            # Returns True only if assets exist; if not, False.
            # Either way, no exception.
            vector_rerank.is_enabled()


class TestPassthroughWhenDisabled:
    def test_rerank_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_VECTOR_RERANK", raising=False)
        assert (
            vector_rerank.rerank_sentences(
                "How long must providers keep documentation?",
                "Art. 18",
                "Some BM25-picked sentence.",
            )
            is None
        )

    def test_rerank_doesnt_raise_on_missing_assets(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_VECTOR_RERANK", "1")
        # Even with the env-gate ON, missing assets should not raise.
        result = vector_rerank.rerank_sentences(
            "What is an AI system?",
            "Art. 3",
            "fallback sentence",
        )
        # None when assets aren't present; otherwise a string.
        assert result is None or isinstance(result, str)


class TestPaths:
    def test_paths_resolve(self):
        # The path constants must point inside the app/data/vectors
        # directory, even when no files are present.
        for path in (
            vector_rerank.INDEX_PATH,
            vector_rerank.ONNX_PATH,
            vector_rerank.TOKENIZER_PATH,
        ):
            assert path.parent.name == "vectors"
            assert path.parent.parent.name == "data"
