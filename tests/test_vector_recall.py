import os
os.environ["NEO4J_AUTO_SEED"] = "0"

import pytest
from app.engines import vector_recall


def test_recall_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAPH_VECTOR_RECALL", raising=False)
    assert vector_recall.recall_articles("What are the prohibited practices?") == []


def test_is_enabled_gate(monkeypatch):
    monkeypatch.delenv("REGENOLD_GRAPH_VECTOR_RECALL", raising=False)
    assert not vector_recall.is_enabled()
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    assert vector_recall.is_enabled()


def test_recall_enabled_returns_articles(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    res = vector_recall.recall_articles("What are the prohibited practices?")
    assert isinstance(res, list)
    assert len(res) > 0


def test_recall_respects_min_sim(monkeypatch):
    monkeypatch.setenv("REGENOLD_GRAPH_VECTOR_RECALL", "1")
    monkeypatch.setenv("REGENOLD_VECTOR_MIN_SIM", "0.99")
    res = vector_recall.recall_articles("What are the prohibited practices?")
    assert res == []
