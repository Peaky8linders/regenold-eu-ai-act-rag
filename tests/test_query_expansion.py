"""R39 RAG-Fusion + RRF query expansion (Issue B8)."""
from unittest.mock import patch, MagicMock

from app.engines.query_expansion import (
    expand_query,
    reciprocal_rank_fusion,
)


def test_expand_query_returns_original_plus_paraphrases():
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
        queries = expand_query("Who is a provider under the AI Act?", intent_label="definition")
    assert queries[0] == "Who is a provider under the AI Act?"  # original first
    assert len(queries) >= 2


def test_expand_query_returns_only_original_on_wrapper_disabled():
    with patch("app.engines.query_expansion.is_openai_wrapper_enabled",
               return_value=False):
        queries = expand_query("Who is a provider?", intent_label="definition")
    assert queries == ["Who is a provider?"]


def test_expand_query_falls_soft_on_provider_exception():
    with patch("app.engines.query_expansion.is_openai_wrapper_enabled",
               return_value=True), \
         patch("app.engines.query_expansion.get_openai_wrapper_provider",
               side_effect=RuntimeError("boom")):
        queries = expand_query("Q?", intent_label="definition")
    assert queries == ["Q?"]


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
