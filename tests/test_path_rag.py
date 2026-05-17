"""R39 PathRAG relational-path pruning (Issue B7)."""
from unittest.mock import patch, MagicMock

from app.engines.path_rag import (
    prune_redundant_paths,
    pathrag_candidates,
)


def test_prune_drops_redundant_overlapping_paths():
    # Path A: 5 -> 6 -> 9
    # Path B: 5 -> 6 -> 10 (shares 2/3 edges with A — different leaf, KEEP)
    # Path C: 5 -> 6 -> 9 (identical to A — DROP)
    paths = [
        [("Art. 5", "Art. 6"), ("Art. 6", "Art. 9")],
        [("Art. 5", "Art. 6"), ("Art. 6", "Art. 10")],
        [("Art. 5", "Art. 6"), ("Art. 6", "Art. 9")],
    ]
    out = prune_redundant_paths(paths, jaccard_threshold=0.8)
    assert len(out) == 2  # A and B survive; C dropped


def test_prune_keeps_disjoint_paths():
    paths = [
        [("Art. 5", "Art. 6")],
        [("Art. 50", "Art. 73")],
    ]
    out = prune_redundant_paths(paths, jaccard_threshold=0.5)
    assert len(out) == 2


def test_pathrag_candidates_returns_empty_when_flag_off(monkeypatch):
    monkeypatch.delenv("REGENOLD_PATH_RAG", raising=False)
    assert pathrag_candidates(seed_articles=["Art. 5"]) == []


def test_pathrag_candidates_fails_soft_on_neo4j_error(monkeypatch):
    monkeypatch.setenv("REGENOLD_PATH_RAG", "1")
    with patch("app.engines.path_rag.get_graph_client") as gc:
        client = MagicMock()
        client.enabled = True
        client.execute_read.side_effect = RuntimeError("connection refused")
        gc.return_value = client
        assert pathrag_candidates(seed_articles=["Art. 5"]) == []
