"""Tests for RushDB config + client (mocked — no live API)."""
from __future__ import annotations

import os
from unittest import mock

import pytest


class TestRushdbConfig:
    def test_resolve_auth_token_prefers_auth_token(self, monkeypatch):
        monkeypatch.setenv("RUSHDB_AUTH_TOKEN", "tok-a")
        monkeypatch.setenv("RUSHDB_API_KEY", "tok-b")
        from app.graph.rushdb_config import resolve_auth_token

        assert resolve_auth_token() == "tok-a"

    def test_resolve_auth_token_falls_back_to_api_key(self, monkeypatch):
        monkeypatch.delenv("RUSHDB_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("RUSHDB_API_KEY", "key-only")
        from app.graph.rushdb_config import resolve_auth_token

        assert resolve_auth_token() == "key-only"

    def test_create_rushdb_client_uses_api_key_signature(self, monkeypatch):
        monkeypatch.setenv("RUSHDB_AUTH_TOKEN", "secret")
        monkeypatch.setenv("RUSHDB_BASE_URL", "https://example.test/v1")

        fake_rushdb = mock.MagicMock()
        fake_client = mock.MagicMock()
        fake_rushdb.RushDB.return_value = fake_client

        with mock.patch.dict("sys.modules", {"rushdb": fake_rushdb}):
            from app.graph import rushdb_config as cfg

            client = cfg.create_rushdb_client()

        assert client is fake_client
        fake_rushdb.RushDB.assert_called_once_with(
            api_key="secret",
            base_url="https://example.test/v1",
        )

    def test_create_rushdb_client_legacy_signature_on_type_error(self, monkeypatch):
        monkeypatch.setenv("RUSHDB_API_KEY", "legacy-key")

        fake_rushdb = mock.MagicMock()
        legacy_client = mock.MagicMock()

        def rushdb_ctor(*args, **kwargs):
            if kwargs.get("api_key") is not None or "api_key" in kwargs:
                raise TypeError("api_key")
            return legacy_client

        fake_rushdb.RushDB.side_effect = rushdb_ctor

        with mock.patch.dict("sys.modules", {"rushdb": fake_rushdb}):
            from app.graph import rushdb_config as cfg

            client = cfg.create_rushdb_client()

        assert client is legacy_client
        assert fake_rushdb.RushDB.call_count == 2


class TestRushdbClient:
    def setup_method(self):
        import app.graph.rushdb_client as rc

        rc._RUSHDB_CLIENT = None
        rc._INIT_ATTEMPTED = False

    def test_is_enabled_false_without_auth(self, monkeypatch):
        monkeypatch.delenv("RUSHDB_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("RUSHDB_API_KEY", raising=False)

        fake_rushdb = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"rushdb": fake_rushdb}):
            from app.graph.rushdb_client import is_enabled

            assert is_enabled() is False

    def test_expand_2hop_returns_hop_counts(self, monkeypatch):
        monkeypatch.setenv("RUSHDB_AUTH_TOKEN", "t")

        doc13 = mock.MagicMock(cross_refs=["article_9", "article_14"])
        doc9 = mock.MagicMock(cross_refs=["article_6"])

        client = mock.MagicMock()
        client.records.find.side_effect = [
            mock.MagicMock(data=[doc13]),
            mock.MagicMock(data=[doc9]),
        ]

        with mock.patch("app.graph.rushdb_client._get_client", return_value=client):
            from app.graph.rushdb_client import expand_2hop

            out = expand_2hop(["13"], cap=10, timeout_ms=5000)

        nums = {row["num"] for row in out}
        assert "9" in nums
        assert "14" in nums
        assert all(row["hops"] in (1, 2) for row in out)

    def test_lookup_definition_by_term_slug_match(self, monkeypatch):
        monkeypatch.setenv("RUSHDB_AUTH_TOKEN", "t")

        doc = mock.MagicMock(text="An AI system is ...")
        client = mock.MagicMock()
        client.records.find.return_value = mock.MagicMock(data=[doc])

        with mock.patch("app.graph.rushdb_client._get_client", return_value=client):
            from app.graph.rushdb_client import lookup_definition_by_term

            text = lookup_definition_by_term("AI system", timeout_ms=5000)

        assert text == "An AI system is ..."

    def test_get_stats_uses_metadata_totals(self, monkeypatch):
        monkeypatch.setenv("RUSHDB_AUTH_TOKEN", "t")

        meta_doc = {
            "seed_version": "2026-05-25-rushdb-v1",
            "kb_version": "2024.1689.v6",
            "total_nodes": 505,
            "total_edges": 351,
        }

        with mock.patch("app.graph.rushdb_client.get_metadata", return_value=meta_doc):
            from app.graph.rushdb_client import get_stats

            stats = get_stats()

        assert stats["graph_ok"] is True
        assert stats["total_nodes"] == 505
        assert stats["seed_version"] == "2026-05-25-rushdb-v1"
