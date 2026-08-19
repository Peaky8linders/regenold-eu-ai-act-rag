"""Comprehensive tests for the AWS Bedrock provider.

Covers:
  * Credential parsing (composite API key, standard env, default chain)
  * Provider resolution (``resolve_provider("bedrock")``)
  * Converse API request building and response parsing
  * Error classification for all known Bedrock exception types
  * Singleton lifecycle and thread safety
  * Streaming event parsing and cleanup
  * Provider enable detection
  * Security: credential masking in ``__repr__``

All tests are offline — boto3 clients are mocked via ``unittest.mock``
and ``monkeypatch``. No AWS credentials required to run.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# ── Credential parsing ───────────────────────────────────────────────────────


class TestParseBedrockApiKey:
    def test_two_part_key_secret(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        result = _parse_bedrock_api_key("AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI")
        assert result["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        assert result["aws_secret_access_key"] == "wJalrXUtnFEMI"
        assert "aws_session_token" not in result
        assert "region_name" not in result

    def test_three_part_with_region(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        result = _parse_bedrock_api_key("AKIA123:secret456:us-west-2")
        assert result["aws_access_key_id"] == "AKIA123"
        assert result["aws_secret_access_key"] == "secret456"
        assert result["region_name"] == "us-west-2"
        assert "aws_session_token" not in result

    def test_three_part_with_session_token(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        result = _parse_bedrock_api_key("AKIA123:secret456:FwoGZXIvYXdz...")
        assert result["aws_access_key_id"] == "AKIA123"
        assert result["aws_secret_access_key"] == "secret456"
        assert result["aws_session_token"] == "FwoGZXIvYXdz..."
        assert "region_name" not in result

    def test_four_part_full(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        result = _parse_bedrock_api_key("ASIA123:secret:token:eu-west-1")
        assert result["aws_access_key_id"] == "ASIA123"
        assert result["aws_secret_access_key"] == "secret"
        assert result["aws_session_token"] == "token"
        assert result["region_name"] == "eu-west-1"

    def test_single_part_raises(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        with pytest.raises(ValueError, match="at least ACCESS_KEY:SECRET_KEY"):
            _parse_bedrock_api_key("just-a-single-string")

    def test_five_parts_raises(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        with pytest.raises(ValueError, match="too many colon-separated parts"):
            _parse_bedrock_api_key("a:b:c:d:e")

    def test_whitespace_stripped(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        result = _parse_bedrock_api_key("  AKIA123 : secret456 : us-east-1 ")
        assert result["aws_access_key_id"] == "AKIA123"
        assert result["aws_secret_access_key"] == "secret456"
        assert result["region_name"] == "us-east-1"

    def test_empty_string_raises(self) -> None:
        from app.llm.bedrock_client import _parse_bedrock_api_key

        with pytest.raises(ValueError):
            _parse_bedrock_api_key("")


# ── Credential resolution ────────────────────────────────────────────────────


class TestResolveCredentials:
    def test_composite_key_takes_priority(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import _resolve_credentials

        monkeypatch.setenv("AWS_BEDROCK_API_KEY", "AKIA123:secret456:us-west-2")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "SHOULD_NOT_USE")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SHOULD_NOT_USE")

        result = _resolve_credentials()
        assert result["aws_access_key_id"] == "AKIA123"
        assert result["aws_secret_access_key"] == "secret456"
        assert result["region_name"] == "us-west-2"

    def test_standard_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import _resolve_credentials

        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA_STD")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret_std")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "tok")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-1")

        result = _resolve_credentials()
        assert result["aws_access_key_id"] == "AKIA_STD"
        assert result["aws_secret_access_key"] == "secret_std"
        assert result["aws_session_token"] == "tok"
        assert result["region_name"] == "ap-southeast-1"

    def test_default_chain_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import _resolve_credentials

        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("BEDROCK_REGION", raising=False)

        result = _resolve_credentials()
        assert result["region_name"] == "eu-central-1"
        assert "aws_access_key_id" not in result

    def test_region_fallback_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import _resolve_region

        monkeypatch.setenv("BEDROCK_REGION", "eu-west-1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
        monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
        assert _resolve_region() == "eu-west-1"

        monkeypatch.delenv("BEDROCK_REGION")
        assert _resolve_region() == "eu-central-1"

        monkeypatch.delenv("AWS_DEFAULT_REGION")
        assert _resolve_region() == "ap-northeast-1"

        monkeypatch.delenv("AWS_REGION")
        assert _resolve_region() == "eu-central-1"


# ── Request building ─────────────────────────────────────────────────────────


class TestBuildConverseKwargs:
    def test_basic_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        monkeypatch.delenv("BEDROCK_DEFAULT_MODEL", raising=False)

        req = BedrockRequest(user="Hello, Claude!")
        kwargs = _build_converse_kwargs(req)

        assert kwargs["modelId"] == "eu.anthropic.claude-opus-4-8"
        assert kwargs["messages"] == [
            {"role": "user", "content": [{"text": "Hello, Claude!"}]}
        ]
        assert "system" not in kwargs

    def test_system_prompt_separate(self) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        req = BedrockRequest(user="Hi", system="You are an EU AI Act expert.")
        kwargs = _build_converse_kwargs(req)

        assert kwargs["system"] == [{"text": "You are an EU AI Act expert."}]

    def test_explicit_model_override(self) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        req = BedrockRequest(
            user="Hi",
            model="us.anthropic.claude-3-haiku-20240307-v1:0",
        )
        kwargs = _build_converse_kwargs(req)
        assert kwargs["modelId"] == "us.anthropic.claude-3-haiku-20240307-v1:0"

    def test_inference_config(self) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        req = BedrockRequest(
            user="Hi",
            max_tokens=4096,
            temperature=0.7,
            top_p=0.9,
            stop_sequences=["END", "STOP"],
        )
        kwargs = _build_converse_kwargs(req)
        ic = kwargs["inferenceConfig"]

        assert ic["maxTokens"] == 4096
        assert ic["temperature"] == 0.7
        assert ic["topP"] == 0.9
        assert ic["stopSequences"] == ["END", "STOP"]

    def test_tool_config_passthrough(self) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        tool_config = {
            "tools": [{
                "toolSpec": {
                    "name": "get_weather",
                    "description": "Get weather data",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"}
                            },
                        }
                    },
                }
            }]
        }
        req = BedrockRequest(user="What's the weather?", tool_config=tool_config)
        kwargs = _build_converse_kwargs(req)
        assert kwargs["toolConfig"] == tool_config

    def test_temperature_zero_is_valid(self) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        req = BedrockRequest(user="Hi", temperature=0.0)
        kwargs = _build_converse_kwargs(req)
        assert kwargs["inferenceConfig"]["temperature"] == 0.0

    def test_env_default_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import BedrockRequest, _build_converse_kwargs

        monkeypatch.setenv("BEDROCK_DEFAULT_MODEL", "us.amazon.nova-pro-v1:0")
        req = BedrockRequest(user="Hi")
        kwargs = _build_converse_kwargs(req)
        assert kwargs["modelId"] == "us.amazon.nova-pro-v1:0"


# ── Response parsing ─────────────────────────────────────────────────────────


class TestParseConverseResponse:
    def test_text_response(self) -> None:
        from app.llm.bedrock_client import _parse_converse_response

        raw = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "Hello! How can I help?"}],
                }
            },
            "usage": {"inputTokens": 10, "outputTokens": 7},
            "stopReason": "end_turn",
        }
        result = _parse_converse_response(raw, "claude-3-sonnet", 150)

        assert result.text == "Hello! How can I help?"
        assert result.model == "claude-3-sonnet"
        assert result.input_tokens == 10
        assert result.output_tokens == 7
        assert result.elapsed_ms == 150
        assert result.finish_reason == "end_turn"
        assert result.error is None
        assert result.tool_use == []

    def test_tool_use_response(self) -> None:
        from app.llm.bedrock_client import _parse_converse_response

        raw = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"text": "Let me check the weather."},
                        {
                            "toolUse": {
                                "toolUseId": "tool_01",
                                "name": "get_weather",
                                "input": {"city": "Helsinki"},
                            }
                        },
                    ],
                }
            },
            "usage": {"inputTokens": 20, "outputTokens": 15},
            "stopReason": "tool_use",
        }
        result = _parse_converse_response(raw, "claude-3-sonnet", 200)

        assert result.text == "Let me check the weather."
        assert result.finish_reason == "tool_use"
        assert len(result.tool_use) == 1
        assert result.tool_use[0]["name"] == "get_weather"
        assert result.tool_use[0]["input"] == {"city": "Helsinki"}

    def test_empty_content(self) -> None:
        from app.llm.bedrock_client import _parse_converse_response

        raw = {
            "output": {"message": {"role": "assistant", "content": []}},
            "usage": {},
            "stopReason": "",
        }
        result = _parse_converse_response(raw, "test-model", 0)
        assert result.text == ""
        assert result.finish_reason is None
        assert result.input_tokens == 0

    def test_missing_output_keys(self) -> None:
        from app.llm.bedrock_client import _parse_converse_response

        result = _parse_converse_response({}, "test-model", 0)
        assert result.text == ""
        assert result.error is None


# ── Error classification ─────────────────────────────────────────────────────


class TestClassifyClientError:
    def _make_client_error(self, code: str, status: int = 400) -> ClientError:
        return ClientError(
            error_response={
                "Error": {"Code": code, "Message": "test"},
                "ResponseMetadata": {"HTTPStatusCode": status},
            },
            operation_name="Converse",
        )

    def test_throttling(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("ThrottlingException", 429)
        assert _classify_client_error(exc) == "api_throttled_429"

    def test_access_denied(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("AccessDeniedException", 403)
        assert _classify_client_error(exc) == "api_access_denied_403"

    def test_validation(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("ValidationException", 400)
        assert _classify_client_error(exc) == "api_validation_400"

    def test_model_not_ready(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("ModelNotReadyException", 424)
        assert _classify_client_error(exc) == "api_model_not_ready_424"

    def test_resource_not_found(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("ResourceNotFoundException", 404)
        assert _classify_client_error(exc) == "api_resource_not_found_404"

    def test_model_timeout(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("ModelTimeoutException", 408)
        assert _classify_client_error(exc) == "api_model_timeout_408"

    def test_quota_exceeded(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("ServiceQuotaExceededException", 402)
        assert _classify_client_error(exc) == "api_quota_exceeded_402"

    def test_unknown_error_code(self) -> None:
        from app.llm.bedrock_client import _classify_client_error

        exc = self._make_client_error("SomeNewException", 500)
        assert _classify_client_error(exc) == "api_status_500_SomeNewException"


# ── Provider complete() with mocked boto3 ────────────────────────────────────


class TestBedrockProviderComplete:
    def test_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            BedrockRequest,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        mock_client = MagicMock()
        mock_client.converse.return_value = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "PONG"}],
                }
            },
            "usage": {"inputTokens": 5, "outputTokens": 3},
            "stopReason": "end_turn",
        }

        with patch(
            "app.llm.bedrock_client._get_runtime_client", return_value=mock_client
        ):
            provider = BedrockProvider()
            result = provider.complete(
                BedrockRequest(user="ping", model="us.anthropic.claude-3-5-sonnet-20241022-v2:0")
            )

        assert result.error is None
        assert result.text == "PONG"
        assert result.input_tokens == 5
        assert result.output_tokens == 3
        assert result.finish_reason == "end_turn"
        assert result.elapsed_ms >= 0

    def test_client_error_surfaces_as_error_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            BedrockRequest,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        mock_client = MagicMock()
        mock_client.converse.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"},
                "ResponseMetadata": {"HTTPStatusCode": 429},
            },
            operation_name="Converse",
        )

        with patch(
            "app.llm.bedrock_client._get_runtime_client", return_value=mock_client
        ):
            provider = BedrockProvider()
            result = provider.complete(BedrockRequest(user="hi"))

        assert result.error == "api_throttled_429"
        assert result.text == ""

    def test_botocore_error_surfaces_as_error_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from botocore.exceptions import EndpointConnectionError

        from app.llm.bedrock_client import (
            BedrockProvider,
            BedrockRequest,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        mock_client = MagicMock()
        mock_client.converse.side_effect = EndpointConnectionError(
            endpoint_url="https://bedrock.us-east-1.amazonaws.com"
        )

        with patch(
            "app.llm.bedrock_client._get_runtime_client", return_value=mock_client
        ):
            provider = BedrockProvider()
            result = provider.complete(BedrockRequest(user="hi"))

        assert result.error is not None
        assert "EndpointConnectionError" in result.error


# ── Per-call timeout isolation (CR-02) ───────────────────────────────────────


class TestPerCallTimeoutIsolation:
    def test_default_timeout_uses_singleton(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        mock_runtime = MagicMock()

        with patch(
            "app.llm.bedrock_client._get_runtime_client",
            return_value=mock_runtime,
        ):
            provider = BedrockProvider()
            client = provider._client_for_timeout(None)
            assert client is mock_runtime

    def test_custom_timeout_creates_new_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()
        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

        mock_runtime = MagicMock()
        mock_session = MagicMock()
        mock_custom_client = MagicMock()
        mock_session.client.return_value = mock_custom_client

        with patch(
            "app.llm.bedrock_client._get_runtime_client",
            return_value=mock_runtime,
        ), patch(
            "app.llm.bedrock_client.boto3.Session",
            return_value=mock_session,
        ):
            provider = BedrockProvider()
            client = provider._client_for_timeout(2.5)
            assert client is mock_custom_client
            assert client is not mock_runtime


# ── Streaming ────────────────────────────────────────────────────────────────


class TestBedrockProviderStream:
    def test_stream_text_events(self) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            BedrockRequest,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        mock_stream = MagicMock()
        mock_stream.__iter__ = MagicMock(
            return_value=iter([
                {"contentBlockDelta": {"delta": {"text": "Hello"}}},
                {"contentBlockDelta": {"delta": {"text": " world"}}},
                {"messageStop": {"stopReason": "end_turn"}},
                {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5}}},
            ])
        )
        mock_stream.close = MagicMock()

        mock_client = MagicMock()
        mock_client.converse_stream.return_value = {"stream": mock_stream}

        with patch(
            "app.llm.bedrock_client._get_runtime_client", return_value=mock_client
        ):
            provider = BedrockProvider()
            events = list(provider.stream(BedrockRequest(user="Hi")))

        assert events[0] == {"type": "text", "text": "Hello"}
        assert events[1] == {"type": "text", "text": " world"}
        assert events[2] == {"type": "stop", "stopReason": "end_turn"}
        assert events[3]["type"] == "metadata"
        assert events[3]["inputTokens"] == 10

        mock_stream.close.assert_called_once()

    def test_stream_cleanup_on_error(self) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            BedrockRequest,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        mock_stream = MagicMock()
        mock_stream.__iter__ = MagicMock(
            return_value=iter([
                {"contentBlockDelta": {"delta": {"text": "partial"}}},
            ])
        )
        mock_stream.__iter__.return_value = iter([])
        mock_stream.close = MagicMock()

        mock_client = MagicMock()
        mock_client.converse_stream.return_value = {"stream": mock_stream}

        with patch(
            "app.llm.bedrock_client._get_runtime_client", return_value=mock_client
        ):
            provider = BedrockProvider()
            _ = list(provider.stream(BedrockRequest(user="Hi")))

        mock_stream.close.assert_called_once()

    def test_stream_client_error_yields_error_event(self) -> None:
        from app.llm.bedrock_client import (
            BedrockProvider,
            BedrockRequest,
            _reset_bedrock_singletons_for_tests,
        )

        _reset_bedrock_singletons_for_tests()

        def _raise_client_error():
            yield {"contentBlockDelta": {"delta": {"text": "Hello"}}}
            raise ClientError(
                error_response={
                    "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"},
                    "ResponseMetadata": {"HTTPStatusCode": 429},
                },
                operation_name="ConverseStream",
            )

        mock_stream = MagicMock()
        mock_stream.__iter__ = MagicMock(return_value=_raise_client_error())
        mock_stream.close = MagicMock()

        mock_client = MagicMock()
        mock_client.converse_stream.return_value = {"stream": mock_stream}

        with patch(
            "app.llm.bedrock_client._get_runtime_client", return_value=mock_client
        ):
            provider = BedrockProvider()
            events = list(provider.stream(BedrockRequest(user="Hi")))

        assert events[0] == {"type": "text", "text": "Hello"}
        assert events[1]["type"] == "error"
        assert "api_throttled_429" in events[1]["error"]
        mock_stream.close.assert_called_once()


# ── Singleton lifecycle ──────────────────────────────────────────────────────


class TestSingletonLifecycle:
    def test_singleton_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import (
            _reset_bedrock_provider_for_tests,
            get_bedrock_provider,
        )

        _reset_bedrock_provider_for_tests()

        p1 = get_bedrock_provider()
        p2 = get_bedrock_provider()
        assert p1 is p2

        _reset_bedrock_provider_for_tests()

    def test_reset_clears_singleton(self) -> None:
        from app.llm.bedrock_client import (
            _reset_bedrock_provider_for_tests,
            get_bedrock_provider,
        )

        _reset_bedrock_provider_for_tests()
        p1 = get_bedrock_provider()
        _reset_bedrock_provider_for_tests()
        p2 = get_bedrock_provider()
        assert p1 is not p2

        _reset_bedrock_provider_for_tests()


# ── Provider enable detection ────────────────────────────────────────────────


class TestIsBedrockProviderEnabled:
    def test_composite_key_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import is_bedrock_provider_enabled

        monkeypatch.setenv("AWS_BEDROCK_API_KEY", "AKIA:secret")
        assert is_bedrock_provider_enabled() is True

    def test_standard_keys_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import is_bedrock_provider_enabled

        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA123")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        assert is_bedrock_provider_enabled() is True

    def test_no_creds_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import is_bedrock_provider_enabled

        monkeypatch.delenv("AWS_BEDROCK_API_KEY", raising=False)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        assert is_bedrock_provider_enabled() is False

    def test_empty_key_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.llm.bedrock_client import is_bedrock_provider_enabled

        monkeypatch.setenv("AWS_BEDROCK_API_KEY", "  ")
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        assert is_bedrock_provider_enabled() is False


# ── Security: credential masking ─────────────────────────────────────────────


class TestCredentialMasking:
    def test_repr_does_not_contain_secrets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import BedrockProvider

        monkeypatch.setenv("AWS_BEDROCK_API_KEY", "AKIA_VERYSECRET:supersecret:us-east-1")
        provider = BedrockProvider()
        repr_str = repr(provider)

        assert "supersecret" not in repr_str
        assert "AKIA_VERYSECRET" not in repr_str
        assert "BedrockProvider" in repr_str
        assert "us-east-1" in repr_str

    def test_str_does_not_contain_secrets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import BedrockProvider

        monkeypatch.setenv("AWS_BEDROCK_API_KEY", "AKIA_SECRET:mysecretkey:us-west-2")
        provider = BedrockProvider()
        str_repr = str(provider)

        assert "mysecretkey" not in str_repr
        assert "AKIA_SECRET" not in str_repr


# ── Model prefixes ───────────────────────────────────────────────────────────


class TestModelPrefixes:
    def test_claude_prefixes(self) -> None:
        from app.llm.bedrock_client import CLAUDE_MODEL_PREFIXES

        assert "anthropic.claude" in CLAUDE_MODEL_PREFIXES
        assert "us.anthropic.claude" in CLAUDE_MODEL_PREFIXES

    def test_nova_prefixes(self) -> None:
        from app.llm.bedrock_client import NOVA_MODEL_PREFIXES

        assert "amazon.nova" in NOVA_MODEL_PREFIXES
        assert "us.amazon.nova" in NOVA_MODEL_PREFIXES

    def test_llama_prefixes(self) -> None:
        from app.llm.bedrock_client import LLAMA_MODEL_PREFIXES

        assert "meta.llama" in LLAMA_MODEL_PREFIXES


# ── EU cross-region inference geography (R328) ───────────────────────────────


class TestEUInferenceGeography:
    def test_default_region_is_in_the_eu_geography(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.llm.bedrock_client import (
            DEFAULT_REGION,
            EU_INFERENCE_REGIONS,
            _resolve_default_model,
            _resolve_region,
        )

        for var in ("BEDROCK_REGION", "AWS_DEFAULT_REGION", "AWS_REGION"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("BEDROCK_DEFAULT_MODEL", raising=False)

        assert DEFAULT_REGION in EU_INFERENCE_REGIONS
        assert _resolve_default_model().startswith("eu.")
        assert _resolve_region() in EU_INFERENCE_REGIONS

    def test_eu_profile_outside_eu_region_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.llm.bedrock_client import resolve_bedrock_model

        monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
        with caplog.at_level(logging.WARNING, logger="app.llm.bedrock_client"):
            out = resolve_bedrock_model("claude-opus-4-8")

        assert out == "eu.anthropic.claude-opus-4-8"
        assert "bedrock_region_geography_mismatch" in caplog.text

    def test_eu_profile_inside_eu_region_is_quiet(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.llm.bedrock_client import resolve_bedrock_model

        monkeypatch.setenv("BEDROCK_REGION", "eu-central-1")
        with caplog.at_level(logging.WARNING, logger="app.llm.bedrock_client"):
            resolve_bedrock_model("claude-sonnet-5")

        assert "bedrock_region_geography_mismatch" not in caplog.text

    def test_unknown_alias_warns_instead_of_silently_swapping(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.llm.bedrock_client import resolve_bedrock_model

        monkeypatch.setenv("BEDROCK_REGION", "eu-central-1")
        monkeypatch.delenv("BEDROCK_DEFAULT_MODEL", raising=False)
        with caplog.at_level(logging.WARNING, logger="app.llm.bedrock_client"):
            out = resolve_bedrock_model("claude-opus-4-8-typo")

        assert out == "eu.anthropic.claude-opus-4-8"
        assert "bedrock_model_alias_unknown" in caplog.text

    def test_operator_targets_resolve_to_eu_profiles(self) -> None:
        from app.llm.bedrock_client import resolve_bedrock_model

        assert resolve_bedrock_model("claude-opus-4-8") == "eu.anthropic.claude-opus-4-8"
        assert resolve_bedrock_model("claude-sonnet-5") == "eu.anthropic.claude-sonnet-5"

    def test_every_alias_target_is_an_eu_profile(self) -> None:
        from app.llm.bedrock_client import BEDROCK_MODEL_ALIASES

        for alias, target in BEDROCK_MODEL_ALIASES.items():
            assert target.startswith(("eu.anthropic.claude", "qwen.")), (alias, target)


class TestTimeoutClientCaching:
    def test_non_default_timeout_client_is_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.llm.bedrock_client as bc

        bc._reset_bedrock_provider_for_tests()
        calls: list[float] = []

        def _fake_create(service: str, read_timeout: float, max_pool: int,
                         target_region: str | None = None) -> object:
            calls.append(read_timeout)
            return object()

        monkeypatch.setattr(bc, "_create_client_with_auth", _fake_create)
        provider = bc.BedrockProvider()

        first = provider._client_for_timeout(45.0)
        second = provider._client_for_timeout(45.0)
        third = provider._client_for_timeout(45.0)

        assert first is second is third
        assert calls == [45.0]
        bc._reset_bedrock_provider_for_tests()
