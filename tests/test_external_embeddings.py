"""Unit tests for ``app.engines.external_embeddings``."""
from __future__ import annotations

import pytest

import app.engines.external_embeddings as ee


def test_is_available_logic(monkeypatch):
    """is_available() is True if any of the API keys/bases are set."""
    # 1. All unset -> False
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert ee.is_available() is False
    assert ee._get_provider() is None

    # 2. Cohere set -> True
    monkeypatch.setenv("COHERE_API_KEY", "co-testkey")
    assert ee.is_available() is True
    assert ee._get_provider() == "cohere"

    # 3. OpenAI set -> True
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-testkey")
    assert ee.is_available() is True
    assert ee._get_provider() == "openai"


def test_get_embedding_cohere_mock(monkeypatch):
    """get_embedding handles Cohere HTTP requests correctly."""
    monkeypatch.setenv("COHERE_API_KEY", "co-testkey")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "embed-english-v3.0")

    mock_emb = [[0.1, 0.2, 0.3]]

    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"embeddings": mock_emb}

    def mock_post(self, url, headers, json, **kwargs):
        assert url == ee.COHERE_API_URL
        assert headers["Authorization"] == "Bearer co-testkey"
        assert json["texts"] == ["biometric systems"]
        assert json["model"] == "embed-english-v3.0"
        assert json["input_type"] == "search_query"
        return MockResponse()

    monkeypatch.setattr("httpx.Client.post", mock_post)

    emb = ee.get_embedding("biometric systems", is_query=True)
    assert emb is not None
    assert emb.shape == (3,)
    assert emb[0] == pytest.approx(0.1)


def test_get_embedding_openai_mock(monkeypatch):
    """get_embedding handles OpenAI HTTP requests correctly."""
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    # conftest.py pins ``OPENAI_API_BASE`` to a dead loopback as a no-live-calls
    # guard (R105); the production code honours it
    # (``api_base = os.getenv("OPENAI_API_BASE", OPENAI_API_URL)``), which would
    # make the request URL ``http://127.0.0.1:1/v1/embeddings`` instead of the
    # canonical endpoint this test asserts. Drop it so the code falls back to
    # ``OPENAI_API_URL`` — the test owns the base it verifies against.
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-testkey")
    monkeypatch.setenv("REGENOLD_EXTERNAL_EMBEDDING_MODEL", "text-embedding-3-small")

    mock_emb = [{"index": 0, "embedding": [0.5, 0.6]}]

    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": mock_emb}

    def mock_post(self, url, headers, json, **kwargs):
        assert url == ee.OPENAI_API_URL
        assert headers["Authorization"] == "Bearer sk-testkey"
        assert json["input"] == ["clinical notes"]
        assert json["model"] == "text-embedding-3-small"
        return MockResponse()

    monkeypatch.setattr("httpx.Client.post", mock_post)

    emb = ee.get_embedding("clinical notes", is_query=False)
    assert emb is not None
    assert emb.shape == (2,)
    assert emb[0] == pytest.approx(0.5)


def test_get_embedding_graceful_fallback(monkeypatch):
    """get_embedding returns None gracefully on any exception."""
    monkeypatch.setenv("COHERE_API_KEY", "co-testkey")

    def mock_post(*args, **kwargs):
        raise RuntimeError("Network timeout")

    monkeypatch.setattr("httpx.Client.post", mock_post)

    emb = ee.get_embedding("biometric systems")
    assert emb is None
