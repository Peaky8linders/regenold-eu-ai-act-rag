"""R39 RAG-Fusion + RRF query expansion (Issue B8). R40 contract update:
``expand_query`` now returns paraphrases ONLY (the original is folded in
by the caller in :mod:`app.data.kb_search`)."""
from unittest.mock import patch, MagicMock

from app.engines.query_expansion import (
    _reset_for_tests,
    expand_query,
    reciprocal_rank_fusion,
)


def setup_function(_func):
    _reset_for_tests()


def test_expand_query_returns_paraphrases():
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = (
        '{"paraphrases": ["What is a provider?", '
        '"Who counts as a provider?", "Define provider role."]}'
    )
    fake_response.error = None
    fake_provider.complete.return_value = fake_response
    with patch("app.engines.query_expansion.get_openai_wrapper_provider",
               return_value=fake_provider), \
         patch("app.engines.query_expansion.is_openai_wrapper_enabled",
               return_value=True):
        paraphrases = expand_query("Who is a provider under the AI Act?")
    assert len(paraphrases) >= 1
    assert all(isinstance(p, str) and p for p in paraphrases)
    assert "Who is a provider under the AI Act?" not in paraphrases


def test_expand_query_returns_empty_on_wrapper_disabled():
    with patch("app.engines.query_expansion.is_openai_wrapper_enabled",
               return_value=False):
        paraphrases = expand_query("Who is a provider?")
    assert paraphrases == []


def test_expand_query_falls_soft_on_provider_exception():
    with patch("app.engines.query_expansion.is_openai_wrapper_enabled",
               return_value=True), \
         patch("app.engines.query_expansion.get_openai_wrapper_provider",
               side_effect=RuntimeError("boom")):
        paraphrases = expand_query("Q?")
    assert paraphrases == []


def test_reciprocal_rank_fusion_combines_ranked_lists():
    # Doc A ranked 1st in list 1, 3rd in list 2 → score 1/1 + 1/3
    # Doc B ranked 2nd in both → 1/2 + 1/2
    # Doc C ranked 3rd in list 1, 1st in list 2 → 1/3 + 1/1
    lists = [["A", "B", "C"], ["C", "B", "A"]]
    out = reciprocal_rank_fusion(lists, k=0)
    # With k=0, A score = 1 + 1/3 = 1.333, B = 1/2 + 1/2 = 1, C = 1/3 + 1 = 1.333
    # Tie-break preserves insertion order, so A before C.
    assert out[0] in ("A", "C")
    assert "B" in out
