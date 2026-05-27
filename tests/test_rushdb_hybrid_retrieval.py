"""Tests for RushDB hybrid retrieval env gate and ref mapping."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engines import rushdb_hybrid_retrieval as rh


class TestHybridEnabled:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("REGENOLD_RUSHDB_HYBRID", raising=False)
        assert rh.is_hybrid_enabled() is False

    def test_on_requires_client(self, monkeypatch):
        monkeypatch.setenv("REGENOLD_RUSHDB_HYBRID", "1")
        monkeypatch.setattr(
            "app.graph.rushdb_client.is_enabled",
            lambda: False,
        )
        assert rh.is_hybrid_enabled() is False


class TestRecordToRef:
    def test_article_record(self):
        rec = SimpleNamespace(label="Article", number="13", id="article_13")
        assert rh._record_to_internal_ref(rec) == "Art. 13"

    def test_annex_record(self):
        rec = SimpleNamespace(label="Annex", number="III", id="annex_III")
        assert rh._record_to_internal_ref(rec) == "Annex III"

    def test_id_fallback(self):
        rec = SimpleNamespace(id="article_6")
        assert rh._record_to_internal_ref(rec) == "Art. 6"


class TestClassifyIntent:
    def test_regulatory_lookup(self):
        intent = rh.classify_query_intent("What are deployer obligations under Article 26?")
        assert intent["intent"] == "regulatory_lookup"

    def test_general_fallback(self):
        intent = rh.classify_query_intent("hello world")
        assert intent["intent"] == "general"
