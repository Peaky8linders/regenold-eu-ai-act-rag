"""R362 — per-request Cohere rerank call budget.

The reranker can fire up to 5 serial Cohere calls inside one request (the
R350-documented cascade: 4 per-expanded-query BM25-fallback reranks in one
``_deterministic_parse`` plus the Stage-2 kg-context rerank). The Cohere Trial
key is 10 calls/min, so an A/B paced at ``--min-call-gap 6.5`` runs at ~5x
that budget and 429s into a false INERT. ``reset_request_budget()`` gives each
request a fresh ceiling (default 2, ``REGENOLD_RERANK_REQUEST_BUDGET``) and
``rerank_documents`` refuses calls beyond it — fail-open, input order
unchanged, the wire never touched.

The default path (``REGENOLD_COHERE_RERANK`` off) must stay byte-identical:
the budget is only consulted after ``rerank_enabled()`` already returned True.
"""
from __future__ import annotations

import pytest

from app.engines import cohere_rerank as CR


class _FakeResp:
    status_code = 200

    def json(self):
        return {
            "results": [
                {"index": 0, "relevance_score": 0.9},
                {"index": 1, "relevance_score": 0.1},
            ]
        }


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url, **kwargs):  # noqa: ANN001, ARG002
        self.calls.append(kwargs)
        return _FakeResp()


@pytest.fixture(autouse=True)
def _clean_budget_and_stats(monkeypatch):
    """Isolate budget + stats state between tests (module-level globals)."""
    CR.reset_request_budget()
    CR.reset_rerank_stats()
    monkeypatch.setattr(CR, "_get_client", lambda: _FakeClient())
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")
    yield
    CR.reset_request_budget()
    CR.reset_rerank_stats()


def _call_documents(n: int) -> list[bool]:
    out = []
    for _ in range(n):
        out.append(CR.rerank_documents("q", ["doc a", "doc b"]) is not None)
    return out


def test_default_budget_caps_calls_per_request():
    """Default ceiling 2: third call is skipped, fail-open (None, not error)."""
    results = _call_documents(5)
    assert results == [True, True, False, False, False]
    stats = CR.rerank_stats()
    assert stats["attempts"] == 2
    assert stats["budget_skipped"] == 3
    assert stats["failed"] == 0


def test_budget_is_env_tunable(monkeypatch):
    monkeypatch.setenv("REGENOLD_RERANK_REQUEST_BUDGET", "1")
    CR.reset_request_budget()
    results = _call_documents(3)
    assert results == [True, False, False]
    stats = CR.rerank_stats()
    assert stats["attempts"] == 1
    assert stats["budget_skipped"] == 2


def test_reset_restores_budget_per_request():
    """The route/engine entry points reset per request — the load-bearing bit
    for a threadpool-reused thread."""
    assert _call_documents(1) == [True]
    CR.reset_request_budget()
    assert _call_documents(2) == [True, True]
    stats = CR.rerank_stats()
    assert stats["attempts"] == 3
    assert stats["budget_skipped"] == 0


def test_gate_off_never_touches_budget(monkeypatch):
    monkeypatch.delenv("REGENOLD_COHERE_RERANK", raising=False)
    CR.reset_request_budget()
    assert _call_documents(3) == [False, False, False]
    stats = CR.rerank_stats()
    assert stats["attempts"] == 0
    assert stats["budget_skipped"] == 0


def test_direct_caller_without_reset_gets_fresh_ceiling(monkeypatch):
    """A legacy/direct engine caller that never resets must not be silently
    disabled — first use grants a fresh ceiling (conservative, never OFF)."""
    monkeypatch.setenv("REGENOLD_RERANK_REQUEST_BUDGET", "1")
    # Note: NO reset_request_budget() here — simulates a caller that skips
    # the entry points. The fixture already reset, so simulate a fresh thread
    # by clearing the thread-local state directly.
    try:
        delattr(CR._request_budget_state, "remaining")
    except AttributeError:  # pragma: no cover — already absent
        pass
    results = _call_documents(2)
    assert results == [True, False]
    stats = CR.rerank_stats()
    assert stats["attempts"] == 1
    assert stats["budget_skipped"] == 1


def test_budget_does_not_affect_gate_off_rerank_pool(monkeypatch):
    """With the gate off, rerank_pool returns input unchanged and issues zero
    calls regardless of the budget — the byte-identical guarantee."""
    monkeypatch.delenv("REGENOLD_COHERE_RERANK", raising=False)
    refs = ["Article 6", "Article 43"]
    out, ok = CR.rerank_pool("q", refs, text_for=lambda r: f"text of {r}")
    assert out == refs
    assert ok is False
    stats = CR.rerank_stats()
    assert stats["attempts"] == 0
    assert stats["budget_skipped"] == 0


def test_stats_reset_zeroes_budget_skipped():
    CR.reset_request_budget()
    _call_documents(3)
    CR.reset_rerank_stats()
    stats = CR.rerank_stats()
    assert stats["attempts"] == 0
    assert stats["budget_skipped"] == 0
