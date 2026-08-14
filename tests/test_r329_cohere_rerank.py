"""R329 — safety invariants for the Cohere cross-encoder reranker.

The module ships **default OFF** and measured no benefit (see
``.planning/R329-PLAN-RANKER-AND-OVERCITATION.md`` §2.7), but it stays in the
tree as a measured negative result and a wired arm. These tests pin the
properties that make it harmless if anyone enables it — above all that it is a
PERMUTATION and can never drop a reference, which is the R142.1 failure mode
(a live pairwise lost 11-0, refs p=0.001, by dropping one gold ref).
"""
from __future__ import annotations

import pytest

from app.engines import cohere_rerank as CR


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test here may make a live call."""
    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("live rerank call attempted in a unit test")

    monkeypatch.setattr(CR, "_get_client", _boom)
    yield


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REGENOLD_COHERE_RERANK", raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "x")
    assert CR.rerank_enabled() is False


def test_enabled_needs_both_flag_and_key(monkeypatch):
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    assert CR.rerank_enabled() is False
    monkeypatch.setenv("COHERE_API_KEY", "x")
    assert CR.rerank_enabled() is True


def test_disabled_returns_input_order_untouched(monkeypatch):
    monkeypatch.delenv("REGENOLD_COHERE_RERANK", raising=False)
    refs = ["Article 6", "Article 43", "Annex I"]
    assert CR.rerank_references("q", refs) == refs


def test_result_is_a_permutation(monkeypatch):
    """THE load-bearing invariant: same multiset in, same multiset out."""
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")
    refs = ["Article 6", "Article 43", "Annex I", "Article 50.1"]
    # Reverse the order the API would return.
    monkeypatch.setattr(
        CR, "rerank_documents", lambda q, d, top_n=None: [(i, 1.0) for i in range(len(d) - 1, -1, -1)]
    )
    out = CR.rerank_references("q", refs, text_for=lambda r: f"text of {r}")
    assert sorted(out) == sorted(refs), out
    assert len(out) == len(refs)
    assert out != refs  # it really did reorder


def test_unresolvable_refs_are_never_dropped(monkeypatch):
    """A ref with no provision text must survive, in original relative order."""
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")
    refs = ["Article 6", "Article 999", "Annex I"]

    def _text(ref):
        return None if ref == "Article 999" else f"text of {ref}"

    monkeypatch.setattr(
        CR, "rerank_documents", lambda q, d, top_n=None: [(i, 1.0) for i in range(len(d) - 1, -1, -1)]
    )
    out = CR.rerank_references("q", refs, text_for=_text)
    assert sorted(out) == sorted(refs)
    assert "Article 999" in out


def test_api_failure_returns_input_unchanged(monkeypatch):
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")
    refs = ["Article 6", "Article 43"]
    monkeypatch.setattr(CR, "rerank_documents", lambda q, d, top_n=None: None)
    assert CR.rerank_references("q", refs, text_for=lambda r: f"t{r}") == refs


def test_fewer_than_two_refs_is_a_noop(monkeypatch):
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")
    assert CR.rerank_references("q", ["Article 6"]) == ["Article 6"]
    assert CR.rerank_references("q", []) == []


def test_duplicate_refs_preserved_in_count(monkeypatch):
    monkeypatch.setenv("REGENOLD_COHERE_RERANK", "1")
    monkeypatch.setenv("COHERE_API_KEY", "x")
    refs = ["Article 6", "Article 6", "Annex I"]
    monkeypatch.setattr(
        CR, "rerank_documents", lambda q, d, top_n=None: [(i, 1.0) for i in range(len(d))]
    )
    out = CR.rerank_references("q", refs, text_for=lambda r: f"t{r}")
    assert sorted(out) == sorted(refs)
    assert out.count("Article 6") == 2
