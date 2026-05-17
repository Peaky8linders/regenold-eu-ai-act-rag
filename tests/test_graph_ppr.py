"""R39 HippoRAG 2 Personalized PageRank over Neo4j (Issue B6)."""
from unittest.mock import patch, MagicMock

from app.engines.graph_ppr import (
    is_ppr_available,
    ppr_candidates,
)


def test_returns_empty_when_flag_off(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAPH_PPR", raising=False)
    assert ppr_candidates(seed_articles=["Art. 5"], top_k=10) == []


def test_returns_empty_when_neo4j_disabled(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_PPR", "1")
    with patch("app.engines.graph_ppr.get_graph_client") as gc:
        client = MagicMock()
        client.enabled = False
        gc.return_value = client
        assert ppr_candidates(seed_articles=["Art. 5"], top_k=10) == []


def test_returns_empty_on_gds_plugin_missing(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_PPR", "1")
    with patch("app.engines.graph_ppr.get_graph_client") as gc:
        client = MagicMock()
        client.enabled = True
        client.execute_read.side_effect = RuntimeError("Unknown function gds.pageRank.stream")
        gc.return_value = client
        out = ppr_candidates(seed_articles=["Art. 5"], top_k=10)
        assert out == []


def test_ppr_returns_top_k_articles(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_PPR", "1")
    with patch("app.engines.graph_ppr.get_graph_client") as gc:
        client = MagicMock()
        client.enabled = True
        client.execute_read.return_value = [
            {"num": 13, "score": 0.95},
            {"num": 6, "score": 0.80},
            {"num": 9, "score": 0.65},
        ]
        gc.return_value = client
        out = ppr_candidates(seed_articles=["Art. 5"], top_k=2)
        assert out == ["Art. 13", "Art. 6"]


def test_is_ppr_available_respects_flag(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAPH_PPR", raising=False)
    assert is_ppr_available() is False
    monkeypatch.setenv("REGENOLD_GRAPH_PPR", "1")
    assert is_ppr_available() is True
