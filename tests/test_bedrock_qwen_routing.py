"""Tests for AWS Bedrock Qwen 3 235B / 32B routing and Cloudflare tunnel fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.llm.bedrock_client import (
    BedrockRequest,
    BedrockResponse,
    resolve_bedrock_model,
)
from app.engines._graph_rag_impl import (
    BEDROCK_RAG_MODEL,
    BEDROCK_COMPLEX_MODEL,
    _bedrock_complete_for_graph_rag,
    _openai_wrapper_complete_for_graph_rag,
    _claude_max_enhance_answer,
)


class TestBedrockQwenAliases:
    """Verify Qwen 3 32B and 235B aliases resolve correctly."""

    def test_qwen3_32b_aliases(self) -> None:
        expected = "qwen.qwen3-32b-v1:0"
        assert resolve_bedrock_model("qwen3-32b") == expected
        assert resolve_bedrock_model("qwen-32b") == expected
        assert resolve_bedrock_model("qwen") == expected
        assert resolve_bedrock_model("qwen.qwen3-32b-v1:0") == expected

    def test_qwen3_235b_aliases(self) -> None:
        expected = "qwen.qwen3-235b-a22b-2507-v1:0"
        assert resolve_bedrock_model("qwen3-235b") == expected
        assert resolve_bedrock_model("qwen-235b") == expected
        assert resolve_bedrock_model("qwen.qwen3-235b-a22b-2507-v1:0") == expected


class TestBedrockStage2QwenRouting:
    """Verify Stage-2 Bedrock completions route to Qwen 3 235B for complex and 32B for simple."""

    def test_default_models_are_qwen(self) -> None:
        assert BEDROCK_RAG_MODEL == "qwen.qwen3-32b-v1:0"
        assert BEDROCK_COMPLEX_MODEL == "qwen.qwen3-235b-a22b-2507-v1:0"

    def test_simple_question_routes_to_qwen_32b(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake-secret")

        with patch("app.llm.bedrock_client.complete_with_fallback") as mock_complete:
            mock_complete.return_value = BedrockResponse(
                text="Article 50 applies to limited risk systems.",
                model="qwen.qwen3-32b-v1:0",
            )

            result = _bedrock_complete_for_graph_rag(
                system="You are an EU AI Act expert.",
                user="Is a chatbot high-risk?",
                max_tokens=1024,
                temperature=0.0,
                complex_question=False,
                stage_name="Stage 2 (Polishing)",
            )

            assert result == "Article 50 applies to limited risk systems."
            assert mock_complete.called
            call_req = mock_complete.call_args[0][0]
            assert call_req.model == "qwen.qwen3-32b-v1:0"

    def test_complex_question_routes_to_qwen_235b(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake-secret")

        with patch("app.llm.bedrock_client.complete_with_fallback") as mock_complete:
            mock_complete.return_value = BedrockResponse(
                text="GPAI models with systemic risk must satisfy Article 51, 52, and 55 obligations.",
                model="qwen.qwen3-235b-a22b-2507-v1:0",
            )

            result = _bedrock_complete_for_graph_rag(
                system="You are an EU AI Act expert.",
                user="What are the cumulative compute thresholds under Article 51(2) and systemic risk duties?",
                max_tokens=1024,
                temperature=0.0,
                complex_question=True,
                stage_name="Stage 2 (Polishing)",
            )

            assert result == "GPAI models with systemic risk must satisfy Article 51, 52, and 55 obligations."
            assert mock_complete.called
            call_req = mock_complete.call_args[0][0]
            assert call_req.model == "qwen.qwen3-235b-a22b-2507-v1:0"


class TestCloudflareWrapperFallbackToBedrock:
    """Verify Cloudflare wrapper failure triggers automatic fallback to Bedrock Qwen."""

    def test_wrapper_failure_triggers_bedrock_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake-secret")

        # Mock wrapper failure
        mock_wrapper = MagicMock()
        mock_wrapper.complete.return_value = MagicMock(
            error="api_status_500: No response from Claude Code",
            text="",
            finish_reason=None,
        )

        with patch("app.llm.openai_wrapper_provider.get_openai_wrapper_provider", return_value=mock_wrapper), \
             patch("app.engines._graph_rag_impl._bedrock_complete_for_graph_rag") as mock_bedrock:

            mock_bedrock.return_value = "Bedrock Qwen synthesized compliance answer under Article 6(1)."

            result = _openai_wrapper_complete_for_graph_rag(
                system="Regulatory counsel",
                user="Is biometric identification prohibited?",
                max_tokens=1024,
                temperature=0.0,
                complex_question=True,
                stage_name="Stage 2 (Polishing)",
            )

            assert result == "Bedrock Qwen synthesized compliance answer under Article 6(1)."
            assert mock_bedrock.called
            assert mock_bedrock.call_args[1]["complex_question"] is True
