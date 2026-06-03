import os
import pytest
from unittest.mock import MagicMock, patch

from app.engines.graph_rag import (
    GraphContext,
    _stage2_provider_enabled,
    _llm_parse_query,
    _llm_generate_answer,
    _claude_max_enhance_answer,
)
from app.llm.openai_wrapper_provider import OpenAIWrapperResponse


class FakeGeminiProvider:
    def __init__(self, response_text="MOCK GEMINI RESPONSE", error=None, finish_reason="stop", completion_tokens=10):
        self.response_text = response_text
        self.error = error
        self.finish_reason = finish_reason
        self.completion_tokens = completion_tokens
        self.calls = []

    def complete(self, request):
        self.calls.append(request)
        return OpenAIWrapperResponse(
            text=self.response_text,
            error=self.error,
            model=request.model,
            finish_reason=self.finish_reason,
            completion_tokens=self.completion_tokens,
            prompt_tokens=5,
            elapsed_ms=120,
        )


def test_stage2_gemini_enabled(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "gemini")
    
    with patch("app.llm.openai_wrapper_provider.is_gemini_provider_enabled", return_value=True):
        assert _stage2_provider_enabled() is True
        
    with patch("app.llm.openai_wrapper_provider.is_gemini_provider_enabled", return_value=False):
        assert _stage2_provider_enabled() is False


def test_llm_parse_query_gemini(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "gemini")
    monkeypatch.setenv("REGENOLD_STAGE1_MODEL_GEMINI", "gemini-test-stage1")
    
    fake_provider = FakeGeminiProvider(response_text='{"intent": "prohibited_practices", "entities": ["Article 5"]}')
    
    with patch("app.llm.openai_wrapper_provider.get_gemini_provider", return_value=fake_provider):
        result = _llm_parse_query("Is article 5 violated?")
        
        assert len(fake_provider.calls) == 1
        assert fake_provider.calls[0].model == "gemini-test-stage1"
        assert result.intent == "prohibited_practices"
        assert result.entities == ["Article 5"]


def test_llm_generate_answer_gemini(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "gemini")
    monkeypatch.setenv("REGENOLD_STAGE2_MODEL_GEMINI", "gemini-test-stage2")
    
    fake_provider = FakeGeminiProvider(response_text="VERDICT: YES\nArticle 5 obligation.")
    
    context = GraphContext()
    # Populate context.obligations with a dummy value to avoid deterministic fallback on is_qa_shape and context.obligations empty check
    context.obligations = [{"text": "dummy"}]
    
    with patch("app.llm.openai_wrapper_provider.get_gemini_provider", return_value=fake_provider):
        result = _llm_generate_answer("Is article 5 violated?", context)
        
        assert len(fake_provider.calls) == 1
        assert fake_provider.calls[0].model == "gemini-test-stage2"
        # Since _llm_generate_answer validates and cleans, let's check it gets the clean text
        assert "VERDICT" in result


def test_claude_max_enhance_answer_gemini(monkeypatch):
    monkeypatch.setenv("P2P_GRAPH_RAG_PROVIDER", "gemini")
    monkeypatch.setenv("REGENOLD_STAGE2_MODEL_GEMINI", "gemini-test-enhance")
    
    context = GraphContext()
    
    # Test happy path
    fake_provider = FakeGeminiProvider(response_text="Polished answer with [Article 5(1)].")
    with patch("app.llm.openai_wrapper_provider.get_gemini_provider", return_value=fake_provider):
        with patch("app.llm.openai_wrapper_provider.is_gemini_provider_enabled", return_value=True):
            text = _claude_max_enhance_answer(
                question="Question text",
                kg_answer="Original answer",
                context=context
            )
            assert text == "Polished answer with [Article 5(1)]."
            assert fake_provider.calls[0].model == "gemini-test-enhance"

    # Test truncation length fallback
    fake_provider_truncated = FakeGeminiProvider(response_text="Polished answer truncated...", finish_reason="length")
    with patch("app.llm.openai_wrapper_provider.get_gemini_provider", return_value=fake_provider_truncated):
        with patch("app.llm.openai_wrapper_provider.is_gemini_provider_enabled", return_value=True):
            text = _claude_max_enhance_answer(
                question="Question text",
                kg_answer="Original answer",
                context=context
            )
            assert text is None

    # Test structural truncation fallback (ends mid-sentence/mid-word)
    fake_provider_struct = FakeGeminiProvider(response_text="Polished answer that ends like a sentenc", finish_reason="stop")
    with patch("app.llm.openai_wrapper_provider.get_gemini_provider", return_value=fake_provider_struct):
        with patch("app.llm.openai_wrapper_provider.is_gemini_provider_enabled", return_value=True):
            text = _claude_max_enhance_answer(
                question="Question text",
                kg_answer="Original answer",
                context=context
            )
            assert text is None
