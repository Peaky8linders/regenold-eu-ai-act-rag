"""AWS Bedrock provider — thread-safe, async-compatible client.

Supports four authentication paths:
  1. Bearer Token via ``AWS_BEARER_TOKEN_BEDROCK`` (or ``AWS_BEDROCK_BEARER_TOKEN`` / ``BEDROCK_BEARER_TOKEN``)
     — uses ``botocore.UNSIGNED`` + ``Authorization: Bearer <token>`` header injection.
  2. Composite API key string via ``AWS_BEDROCK_API_KEY`` — format
     ``ACCESS_KEY:SECRET_KEY[:SESSION_TOKEN][:REGION]``.
  3. Direct IAM credentials via env: ``AWS_ACCESS_KEY_ID``,
     ``AWS_SECRET_ACCESS_KEY``, ``AWS_SESSION_TOKEN``, ``AWS_DEFAULT_REGION``.
  4. Default AWS credentials chain (``~/.aws/credentials``, IAM role,
     EC2/ECS instance profile).

Activate via env::

    P2P_GRAPH_RAG_PROVIDER=bedrock
    BEDROCK_REGION=eu-central-1             # or AWS_DEFAULT_REGION / AWS_REGION
    AWS_BEARER_TOKEN_BEDROCK=ABSK...        # OR standard AWS_* env vars
    BEDROCK_DEFAULT_MODEL=eu.anthropic.claude-opus-4-8

⚠ The Region and the model's geography prefix are ONE decision, not two. An
``eu.`` cross-region inference profile exists only in the EU geography's
Regions; sending it to ``us-east-1`` returns
``ValidationException: The provided model identifier is invalid`` — which reads
like a bad model name and is really a bad Region.

Thread-safety design (addresses CR-01 through CR-10 from adversarial review):
  * ``boto3.Session`` is created once under ``threading.Lock``, never implicitly.
  * ``boto3.client`` instances are shared process-wide — method calls are thread-safe.
  * Per-call overrides (timeout, model, temperature) NEVER mutate the shared client.
  * ``max_pool_connections`` scaled to 50 (not default 10) for concurrent FastAPI.
  * Stream iterators wrapped in ``try...finally: stream.close()`` for pool safety.
  * Async wrappers use ``asyncio.to_thread`` — never block the event loop.
  * Credentials are never logged in ``__repr__``, ``__str__``, or log messages.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass, field, replace
from typing import Any

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


# ── Request / Response dataclasses ───────────────────────────────────────────

@dataclass
class BedrockRequest:
    """Request payload for Bedrock Converse API calls.

    Mirrors ``OpenAIWrapperRequest`` interface for contract parity.
    """
    user: str
    system: str = ""
    model: str = ""
    max_tokens: int = 1024
    temperature: float = 0.0
    top_p: float | None = None
    stop_sequences: list[str] = field(default_factory=list)
    timeout_seconds: float | None = None
    """Per-call timeout override. When ``None``, uses the provider's default
    read_timeout (``BEDROCK_TIMEOUT_SECONDS`` env, 60 s fallback).
    Does NOT mutate the shared client — a separate client with the custom
    botocore Config is constructed if the override differs (CR-02)."""
    tool_config: dict[str, Any] | None = None
    """Bedrock Converse ``toolConfig`` dict — pass through as-is. See
    https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html"""

    thinking_budget: int = 0
    """R355 — extended-thinking budget for this call. ``> 0`` enables Claude
    extended thinking on the Converse request via
    ``additionalModelRequestFields.reasoning_config``
    (``type: enabled``, ``budget_tokens: N`` — Bedrock accepts the
    SNAKE_CASE form, not the Anthropic camelCase). ``0`` (default) sends no
    thinking config — plain fast mode, unchanged behaviour. Per-call only;
    no global state."""


@dataclass
class BedrockResponse:
    """Response from a Bedrock Converse API call.

    Matches ``OpenAIWrapperResponse`` shape for engine interop.
    """
    text: str = ""
    error: str | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0
    finish_reason: str | None = None
    thinking: str | None = None
    tool_use: list[dict[str, Any]] = field(default_factory=list)
    """Parsed tool use blocks from the Converse response, if any."""

    @property
    def prompt_tokens(self) -> int:
        """Alias for input_tokens (OpenAIWrapperResponse parity)."""
        return self.input_tokens

    @property
    def completion_tokens(self) -> int:
        """Alias for output_tokens (OpenAIWrapperResponse parity)."""
        return self.output_tokens


# ── Credential resolution ────────────────────────────────────────────────────

def _resolve_bearer_token() -> str | None:
    """Resolve Bearer token from environment variables."""
    for var_name in (
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_BEDROCK_BEARER_TOKEN",
        "BEDROCK_BEARER_TOKEN",
    ):
        token = os.getenv(var_name, "").strip()
        if token:
            return token

    # Check if AWS_BEDROCK_API_KEY is formatted as a single Bearer token (e.g. starting with ABSK)
    api_key = os.getenv("AWS_BEDROCK_API_KEY", "").strip()
    if api_key and ":" not in api_key:
        return api_key

    return None


def _parse_bedrock_api_key(api_key: str) -> dict[str, str]:
    """Parse a composite API key string into IAM credential components.

    Supported formats:
      * ``ACCESS_KEY:SECRET_KEY``
      * ``ACCESS_KEY:SECRET_KEY:REGION``
      * ``ACCESS_KEY:SECRET_KEY:SESSION_TOKEN:REGION``
    """
    parts = api_key.strip().split(":")
    if len(parts) < 2:
        raise ValueError(
            "AWS_BEDROCK_API_KEY must contain at least ACCESS_KEY:SECRET_KEY "
            f"(got {len(parts)} part(s))"
        )

    creds: dict[str, str] = {
        "aws_access_key_id": parts[0].strip(),
        "aws_secret_access_key": parts[1].strip(),
    }

    if len(parts) == 3:
        third = parts[2].strip()
        if "-" in third and len(third) <= 20:
            creds["region_name"] = third
        else:
            creds["aws_session_token"] = third
    elif len(parts) == 4:
        creds["aws_session_token"] = parts[2].strip()
        creds["region_name"] = parts[3].strip()
    elif len(parts) > 4:
        raise ValueError(
            f"AWS_BEDROCK_API_KEY has too many colon-separated parts ({len(parts)}). "
            "Expected ACCESS_KEY:SECRET_KEY[:SESSION_TOKEN][:REGION]"
        )

    return creds


def _resolve_credentials() -> dict[str, Any]:
    """Resolve AWS credentials from environment, returning kwargs for
    ``boto3.Session()``.

    Priority order:
      1. ``AWS_BEARER_TOKEN_BEDROCK`` / Bearer token — uses bearer auth handler.
      2. ``AWS_BEDROCK_API_KEY`` — composite key string (parsed).
      3. Standard ``AWS_ACCESS_KEY_ID`` + ``AWS_SECRET_ACCESS_KEY`` env vars.
      4. Default credentials chain (``~/.aws/credentials``, IAM role, etc.).
    """
    bearer_token = _resolve_bearer_token()
    if bearer_token:
        # Bearer token mode — region from env
        return {"region_name": _resolve_region(), "_bearer_token": bearer_token}

    api_key = os.getenv("AWS_BEDROCK_API_KEY", "").strip()
    if api_key and ":" in api_key:
        creds = _parse_bedrock_api_key(api_key)
        if "region_name" not in creds:
            creds["region_name"] = _resolve_region()
        return creds

    access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    session_kwargs: dict[str, Any] = {}

    if access_key and secret_key:
        session_kwargs["aws_access_key_id"] = access_key
        session_kwargs["aws_secret_access_key"] = secret_key
        session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
        if session_token:
            session_kwargs["aws_session_token"] = session_token

    session_kwargs["region_name"] = _resolve_region()
    return session_kwargs


EU_INFERENCE_REGIONS = frozenset({
    "eu-central-1", "eu-west-1", "eu-west-3",
    "eu-north-1", "eu-south-1", "eu-south-2",
})
"""Destination Regions of the ``eu.`` cross-region inference geography, as
returned by ``list_inference_profiles(typeEquals='SYSTEM_DEFINED')`` and
measured on 2026-08-11. A request carrying an ``eu.`` profile id MUST be sent
to one of these (or to London / Zurich, which route into the same geography).
Sending one to ``us-east-1`` fails with
``ValidationException: The provided model identifier is invalid`` — the
profile simply does not exist in that Region's catalog."""

DEFAULT_REGION = "eu-central-1"
"""EU default. NOT ``us-east-1``: the default model is an ``eu.`` profile, and
an ``eu.`` profile is unresolvable outside the EU geography (see above)."""


def _resolve_region() -> str:
    """Resolve AWS region from environment."""
    return (
        os.getenv("BEDROCK_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or DEFAULT_REGION
    )


def _resolve_default_model() -> str:
    """Resolve the default Bedrock model ID from environment."""
    return (
        os.getenv("BEDROCK_DEFAULT_MODEL", "").strip()
        or "eu.anthropic.claude-opus-4-8"
    )


# ── Thread-safe singleton clients (CR-01, CR-03, CR-05) ─────────────────────

_RUNTIME_CLIENT_LOCK = threading.Lock()
_CATALOG_CLIENT_LOCK = threading.Lock()
_RUNTIME_CLIENT: Any | None = None
_CATALOG_CLIENT: Any | None = None

_TIMEOUT_CLIENT_LOCK = threading.Lock()
_TIMEOUT_CLIENTS: dict[float, Any] = {}
"""Per-read-timeout runtime clients, keyed by timeout seconds. See
``BedrockProvider._client_for_timeout``."""

_DEFAULT_CONNECT_TIMEOUT = 5.0
_DEFAULT_READ_TIMEOUT = float(os.getenv("BEDROCK_TIMEOUT_SECONDS", "60"))
_DEFAULT_MAX_POOL = int(os.getenv("BEDROCK_MAX_POOL_CONNECTIONS", "50"))


def _create_client_with_auth(
    service_name: str,
    read_timeout: float,
    max_pool: int,
    target_region: str | None = None,
) -> Any:
    """Helper to instantiate a boto3 bedrock or bedrock-runtime client with appropriate auth and region."""
    creds = _resolve_credentials()
    bearer_token = creds.pop("_bearer_token", None)
    region = target_region or creds.get("region_name") or _resolve_region()

    if bearer_token:
        config = BotoConfig(
            region_name=region,
            signature_version=UNSIGNED,
            max_pool_connections=max_pool,
            connect_timeout=_DEFAULT_CONNECT_TIMEOUT,
            read_timeout=read_timeout,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        session = boto3.Session(region_name=region)
        client = session.client(service_name, config=config)

        def _add_bearer_header(request: Any, **_kwargs: Any) -> None:
            request.headers["Authorization"] = f"Bearer {bearer_token}"

        client.meta.events.register(f"before-send.{service_name}.*", _add_bearer_header)
        return client

    creds["region_name"] = region
    config = BotoConfig(
        max_pool_connections=max_pool,
        connect_timeout=_DEFAULT_CONNECT_TIMEOUT,
        read_timeout=read_timeout,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    session = boto3.Session(**creds)
    return session.client(service_name, config=config)


def _get_runtime_client() -> Any:
    """Return the process-wide, thread-safe ``bedrock-runtime`` client."""
    global _RUNTIME_CLIENT
    if _RUNTIME_CLIENT is None:
        with _RUNTIME_CLIENT_LOCK:
            if _RUNTIME_CLIENT is None:
                client = _create_client_with_auth("bedrock-runtime", _DEFAULT_READ_TIMEOUT, _DEFAULT_MAX_POOL)
                _RUNTIME_CLIENT = client
                logger.info(
                    "bedrock_runtime_client_init region=%s pool=%d read_timeout=%.1f",
                    _resolve_region(),
                    _DEFAULT_MAX_POOL,
                    _DEFAULT_READ_TIMEOUT,
                )
    return _RUNTIME_CLIENT


def _get_catalog_client() -> Any:
    """Return the process-wide ``bedrock`` (catalog) client for model listing."""
    global _CATALOG_CLIENT
    if _CATALOG_CLIENT is None:
        with _CATALOG_CLIENT_LOCK:
            if _CATALOG_CLIENT is None:
                client = _create_client_with_auth("bedrock", 10.0, 10)
                _CATALOG_CLIENT = client
    return _CATALOG_CLIENT


def _reset_bedrock_singletons_for_tests() -> None:
    """Reset both singletons. Test-only — not part of the public API."""
    global _RUNTIME_CLIENT, _CATALOG_CLIENT
    with _RUNTIME_CLIENT_LOCK:
        _RUNTIME_CLIENT = None
    with _CATALOG_CLIENT_LOCK:
        _CATALOG_CLIENT = None
    with _TIMEOUT_CLIENT_LOCK:
        _TIMEOUT_CLIENTS.clear()


# ── Model catalog discovery ──────────────────────────────────────────────────

CLAUDE_MODEL_PREFIXES = (
    "anthropic.claude",
    "us.anthropic.claude",
    "eu.anthropic.claude",
    "ap.anthropic.claude",
    "global.anthropic.claude",
)

NOVA_MODEL_PREFIXES = (
    "amazon.nova",
    "us.amazon.nova",
    "global.amazon.nova",
)

LLAMA_MODEL_PREFIXES = (
    "meta.llama",
    "us.meta.llama",
    "global.meta.llama",
)


def list_foundation_models(
    *,
    provider: str | None = None,
    output_modality: str | None = None,
) -> list[dict[str, Any]]:
    """List foundation models available in the Bedrock catalog."""
    client = _get_catalog_client()
    kwargs: dict[str, Any] = {}
    if provider:
        kwargs["byProvider"] = provider
    if output_modality:
        kwargs["byOutputModality"] = output_modality

    try:
        response = client.list_foundation_models(**kwargs)
        return response.get("modelSummaries", [])
    except ClientError as exc:
        logger.error("bedrock_list_models_failed: %s", exc.response["Error"]["Code"])
        raise


def get_claude_models() -> list[dict[str, Any]]:
    """Return only Anthropic Claude models from the catalog."""
    return list_foundation_models(provider="Anthropic")


def get_model_info(model_id: str) -> dict[str, Any] | None:
    """Get details for a specific model ID, or None if not found."""
    models = list_foundation_models()
    for m in models:
        if m.get("modelId") == model_id or m.get("modelArn", "").endswith(model_id):
            return m
    return None


# ── Bedrock Model Alias Resolution ──────────────────────────────────────────

BEDROCK_MODEL_ALIASES: dict[str, str] = {
    # ── Opus ────────────────────────────────────────────────────────────────
    "claude-opus-5": "eu.anthropic.claude-opus-5",
    "opus-5": "eu.anthropic.claude-opus-5",
    "claude-opus-4-8": "eu.anthropic.claude-opus-4-8",
    "opus-4-8": "eu.anthropic.claude-opus-4-8",
    "claude-opus-4-7": "eu.anthropic.claude-opus-4-7",
    "opus-4-7": "eu.anthropic.claude-opus-4-7",
    "claude-opus-4-6": "eu.anthropic.claude-opus-4-6-v1",
    "opus-4-6": "eu.anthropic.claude-opus-4-6-v1",
    "claude-opus-4-5": "eu.anthropic.claude-opus-4-5-20251101-v1:0",
    "opus": "eu.anthropic.claude-opus-4-8",

    # ── Sonnet ──────────────────────────────────────────────────────────────
    "claude-sonnet-5": "eu.anthropic.claude-sonnet-5",
    "sonnet-5": "eu.anthropic.claude-sonnet-5",
    "claude-sonnet-4-6": "eu.anthropic.claude-sonnet-4-6",
    "sonnet-4-6": "eu.anthropic.claude-sonnet-4-6",
    "claude-sonnet-4-5": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet": "eu.anthropic.claude-sonnet-5",

    # ── Haiku ───────────────────────────────────────────────────────────────
    "claude-haiku-4-5": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-haiku": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    "haiku": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
}
"""Right-hand sides verified ACTIVE on 2026-08-11 via
``list_inference_profiles(typeEquals='SYSTEM_DEFINED')`` in eu-central-1.

⚠ Two ID SHAPES coexist and neither is guessable — always read the catalog
rather than extrapolating:
  * Models from Sonnet 4.6 / Opus 4.7 onward carry a BARE id —
    ``eu.anthropic.claude-sonnet-5``, ``eu.anthropic.claude-opus-4-8``.
  * Older ones keep the dated ``-YYYYMMDD-v1:0`` tail —
    ``eu.anthropic.claude-sonnet-4-5-20250929-v1:0``. Opus 4.6 is a third
    shape again: ``eu.anthropic.claude-opus-4-6-v1``.

⚠ Listed-and-ACTIVE is NOT the same as invocable. The catalog reports what
exists in the Region; per-model ACCOUNT entitlement is separate and shows up
only at invoke time as
``AccessDeniedException: <model> is not available for this account``."""


def resolve_bedrock_model(model_name: str) -> str:
    """Resolve shorthand model name or requested model to active Bedrock inference profile ID."""
    name = (model_name or "").strip().lower()
    if not name:
        return _resolve_default_model()

    # If already a full profile ID / ARN
    if name.startswith(("us.", "eu.", "ap.", "global.", "arn:", "anthropic.", "amazon.", "meta.", "qwen.", "nvidia.", "mistral.", "cohere.", "ai21.", "deepseek.")):
        return _warn_on_geography_mismatch(model_name)

    resolved = BEDROCK_MODEL_ALIASES.get(name)
    if resolved is None:
        resolved = _resolve_default_model()
        # A typo'd alias silently running a DIFFERENT model is how a model A/B
        # measures nothing. Say so.
        logger.warning(
            "bedrock_model_alias_unknown name=%r falling_back_to=%s", model_name, resolved
        )
    return _warn_on_geography_mismatch(resolved)


def _warn_on_geography_mismatch(model_id: str) -> str:
    """Pass ``model_id`` through, logging LOUDLY if the configured Region cannot
    resolve it.

    An ``eu.`` profile sent to ``us-east-1`` does not fall back — it fails with
    ``ValidationException: The provided model identifier is invalid``, which
    reads like a bad model name rather than a bad Region. Naming the real cause
    here saves that misdiagnosis.
    """
    if model_id.lower().startswith("eu."):
        region = _resolve_region()
        if region not in EU_INFERENCE_REGIONS and region not in {"eu-west-2", "eu-central-2"}:
            logger.warning(
                "bedrock_region_geography_mismatch model=%s region=%s — an 'eu.' "
                "inference profile is not resolvable outside the EU geography; "
                "set BEDROCK_REGION/AWS_DEFAULT_REGION to one of %s",
                model_id,
                region,
                sorted(EU_INFERENCE_REGIONS),
            )
    return model_id


# ── Bedrock Converse API ─────────────────────────────────────────────────────

def _build_converse_kwargs(req: BedrockRequest) -> dict[str, Any]:
    """Build kwargs dict for ``bedrock-runtime.converse()``."""
    raw_model = req.model.strip() if req.model else _resolve_default_model()
    model_id = resolve_bedrock_model(raw_model)

    messages = [{"role": "user", "content": [{"text": req.user}]}]

    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
    }

    if req.system:
        kwargs["system"] = [{"text": req.system}]

    inference_config: dict[str, Any] = {}
    if req.max_tokens:
        inference_config["maxTokens"] = req.max_tokens
    inference_config["temperature"] = req.temperature
    if req.top_p is not None:
        inference_config["topP"] = req.top_p
    if req.stop_sequences:
        inference_config["stopSequences"] = req.stop_sequences
    if inference_config:
        kwargs["inferenceConfig"] = inference_config

    if req.tool_config:
        kwargs["toolConfig"] = req.tool_config

    if req.thinking_budget and req.thinking_budget > 0:
        # R355 — Bedrock Converse uses SNAKE_CASE for Claude extended-thinking
        # fields inside additionalModelRequestFields (camelCase "reasoningConfig"
        # is rejected: "Extra inputs are not permitted"), Claude requires
        # temperature == 1 when thinking is enabled (a plain 0 is rejected too),
        # and maxTokens must EXCEED the thinking budget (equal is a 400 as well).
        budget = max(256, int(req.thinking_budget))
        if int(inference_config.get("maxTokens") or 0) <= budget:
            inference_config["maxTokens"] = budget + 512
        inference_config["temperature"] = 1.0
        kwargs["additionalModelRequestFields"] = {
            "reasoning_config": {
                "type": "enabled",
                "budget_tokens": budget,
            }
        }

    return kwargs


def _parse_converse_response(
    response: dict[str, Any], model_id: str, elapsed_ms: int
) -> BedrockResponse:
    """Parse a Converse API response into a ``BedrockResponse``."""
    output = response.get("output") or {}
    message = output.get("message") or {}
    content_blocks = message.get("content") or []

    text_parts: list[str] = []
    tool_use_blocks: list[dict[str, Any]] = []
    thinking_parts: list[str] = []

    for block in content_blocks:
        if isinstance(block, dict):
            if "text" in block and block["text"] is not None:
                text_parts.append(str(block["text"]))
            elif "toolUse" in block and block["toolUse"] is not None:
                tool_use_blocks.append(block["toolUse"])
            elif block.get("reasoningContent"):
                # Extended-thinking blocks arrive as
                # {"reasoningContent": {"reasoningText": {"text": ...}}}.
                # Capture them so ``thinking`` is a real field rather than a
                # declared-but-never-populated one.
                reasoning = block["reasoningContent"]
                if isinstance(reasoning, dict):
                    rt = reasoning.get("reasoningText")
                    if isinstance(rt, dict) and rt.get("text"):
                        thinking_parts.append(str(rt["text"]))

    usage = response.get("usage") or {}
    stop_reason = response.get("stopReason", "")

    return BedrockResponse(
        text="\n".join(text_parts),
        model=model_id,
        input_tokens=usage.get("inputTokens", 0) if isinstance(usage, dict) else 0,
        output_tokens=usage.get("outputTokens", 0) if isinstance(usage, dict) else 0,
        elapsed_ms=elapsed_ms,
        finish_reason=stop_reason or None,
        thinking="\n".join(thinking_parts) or None,
        tool_use=tool_use_blocks,
    )


def _classify_client_error(exc: ClientError) -> str:
    """Map botocore ClientError to a categorised error string."""
    code = exc.response.get("Error", {}).get("Code", "Unknown")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
    message = str(exc.response.get("Error", {}).get("Message", ""))

    # R346.1 — a DEAD/EXPIRED ABSK key is NOT a per-model entitlement gap.
    # AWS rejects the credential itself on both the catalog and the runtime
    # endpoints with "Authentication failed: Please make sure your API Key
    # is valid." (long-term keys live exactly 30 days and are shown once at
    # creation). Classify it distinctly so that:
    #   * the operator sees "re-mint the key", not a confusing per-model 403;
    #   * the entitlement chain does NOT burn round-trips or cache per-model
    #     denials for a GLOBAL credential failure (a re-minted key must heal
    #     the process instantly — the 900 s denial memo would delay that);
    #   * the request fails fast instead of hop-ping to the Claude-Max wrapper
    #     (the tunnel the operator keeps for the live re-evaluation) on a
    #     credential problem.
    if code == "AccessDeniedException" and "authentication failed" in message.lower():
        return "api_key_invalid_403"

    error_map = {
        "ThrottlingException": f"api_throttled_{status}",
        "AccessDeniedException": f"api_access_denied_{status}",
        "ValidationException": f"api_validation_{status}",
        "ModelNotReadyException": f"api_model_not_ready_{status}",
        "ResourceNotFoundException": f"api_resource_not_found_{status}",
        "ModelTimeoutException": f"api_model_timeout_{status}",
        "ModelErrorException": f"api_model_error_{status}",
        "ServiceQuotaExceededException": f"api_quota_exceeded_{status}",
    }

    return error_map.get(code, f"api_status_{status}_{code}")


# ── Provider class ───────────────────────────────────────────────────────────

class BedrockProvider:
    """Thread-safe AWS Bedrock provider using the Converse API."""

    def __init__(self) -> None:
        self._default_model = _resolve_default_model()

    def complete(self, req: BedrockRequest) -> BedrockResponse:
        """Synchronous completion via Bedrock Converse API."""
        kwargs = _build_converse_kwargs(req)
        model_id = kwargs["modelId"]

        t0 = time.monotonic()
        try:
            client = self._client_for_timeout(req.timeout_seconds)
            response = client.converse(**kwargs)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            return _parse_converse_response(response, model_id, elapsed_ms)

        except ClientError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            error_str = _classify_client_error(exc)
            logger.error(
                "bedrock_converse_failed model=%s error=%s elapsed_ms=%d",
                model_id,
                error_str,
                elapsed_ms,
            )
            return BedrockResponse(
                error=error_str,
                model=model_id,
                elapsed_ms=elapsed_ms,
            )
        except BotoCoreError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            error_str = f"botocore_error: {type(exc).__name__}"
            logger.error(
                "bedrock_converse_botocore_error model=%s error=%s elapsed_ms=%d",
                model_id,
                error_str,
                elapsed_ms,
            )
            return BedrockResponse(
                error=error_str,
                model=model_id,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            error_str = f"unexpected_error: {type(exc).__name__}: {exc}"
            logger.error(
                "bedrock_converse_unexpected_error model=%s error=%s elapsed_ms=%d",
                model_id,
                error_str,
                elapsed_ms,
            )
            return BedrockResponse(
                error=error_str,
                model=model_id,
                elapsed_ms=elapsed_ms,
            )

    async def complete_async(self, req: BedrockRequest) -> BedrockResponse:
        """Async completion — offloads sync boto3 to thread pool (CR-06)."""
        return await asyncio.to_thread(self.complete, req)

    def stream(self, req: BedrockRequest) -> Iterator[dict[str, Any]]:
        """Synchronous streaming via Bedrock ``converse_stream``."""
        kwargs = _build_converse_kwargs(req)
        model_id = kwargs["modelId"]

        client = self._client_for_timeout(req.timeout_seconds)
        response = client.converse_stream(**kwargs)
        stream = response.get("stream")

        try:
            for event in stream:
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        yield {"type": "text", "text": delta["text"]}
                elif "messageStop" in event:
                    yield {
                        "type": "stop",
                        "stopReason": event["messageStop"].get("stopReason", ""),
                    }
                elif "metadata" in event:
                    usage = event["metadata"].get("usage", {})
                    yield {
                        "type": "metadata",
                        "inputTokens": usage.get("inputTokens", 0),
                        "outputTokens": usage.get("outputTokens", 0),
                    }
        except ClientError as exc:
            error_str = _classify_client_error(exc)
            logger.error("bedrock_stream_error model=%s error=%s", model_id, error_str)
            yield {"type": "error", "error": error_str}
        finally:
            if stream and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

    async def stream_async(
        self, req: BedrockRequest
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Async streaming adapter — wraps sync stream in thread pool (CR-09)."""
        sync_gen = self.stream(req)
        _sentinel = object()
        try:
            while True:
                event = await asyncio.to_thread(next, sync_gen, _sentinel)
                if event is _sentinel:
                    break
                yield event
        except GeneratorExit:
            raise
        finally:
            if hasattr(sync_gen, "close"):
                sync_gen.close()

    def _client_for_timeout(self, timeout_seconds: float | None) -> Any:
        """Return a client appropriate for the requested timeout.

        Non-default timeouts get their OWN cached client rather than a freshly
        built one per call — the judge passes ``timeout_s=45`` on every axis of
        every row, and building a client per call means a new connection pool
        per call (sockets never reused, pool never amortised).
        """
        if timeout_seconds is None or timeout_seconds == _DEFAULT_READ_TIMEOUT:
            return _get_runtime_client()

        key = float(timeout_seconds)
        with _TIMEOUT_CLIENT_LOCK:
            client = _TIMEOUT_CLIENTS.get(key)
            if client is None:
                client = _create_client_with_auth(
                    "bedrock-runtime", key, _DEFAULT_MAX_POOL
                )
                _TIMEOUT_CLIENTS[key] = client
            return client

    def __repr__(self) -> str:
        # Resolve the region the SAME way client construction does, so the repr
        # can't report one region while calls go to another: a composite
        # AWS_BEDROCK_API_KEY may carry its own region, which _resolve_region()
        # (env-only) never sees.
        try:
            region = _resolve_credentials().get("region_name") or _resolve_region()
        except Exception:  # noqa: BLE001 — a repr must never raise
            region = _resolve_region()
        return f"<BedrockProvider model={self._default_model!r} region={region!r}>"


# ── Connectivity check ───────────────────────────────────────────────────────

def check_connectivity_and_permissions(
    model_id: str | None = None,
) -> dict[str, Any]:
    """Diagnostic: verify Bedrock credentials and model access."""
    target = model_id or _resolve_default_model()
    provider = BedrockProvider()

    t0 = time.monotonic()
    try:
        result = provider.complete(
            BedrockRequest(
                user="Say OK.",
                model=target,
                max_tokens=5,
                temperature=0.0,
            )
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if result.error:
            if result.error == "api_key_invalid_403":
                return {
                    "status": "key_invalid",
                    "model": target,
                    "error": result.error,
                    "elapsed_ms": elapsed_ms,
                    "hint": (
                        "AWS rejects the ABSK credential itself, not a model "
                        "entitlement. Long-term Bedrock API keys expire after "
                        "30 days and are shown once at creation. Regenerate in "
                        "the Bedrock console (API keys) and update "
                        "AWS_BEARER_TOKEN_BEDROCK in .env — the code picks the "
                        "new key up on the next request with no restart."
                    ),
                }
            return {
                "status": "error",
                "model": target,
                "error": result.error,
                "elapsed_ms": elapsed_ms,
            }

        return {
            "status": "ok",
            "model": target,
            "response_text": result.text[:50],
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "status": "error",
            "model": target,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": elapsed_ms,
        }


# ── Singleton provider (same pattern as Groq/Gemini/Mistral) ────────────────

_BEDROCK_SINGLETON: BedrockProvider | None = None
_BEDROCK_SINGLETON_LOCK = threading.Lock()


def is_bedrock_provider_enabled() -> bool:
    """True iff the Bedrock provider is enabled."""
    if _resolve_bearer_token():
        return True
    if os.getenv("AWS_BEDROCK_API_KEY", "").strip():
        return True
    if (
        os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        and os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    ):
        return True
    return False


def get_bedrock_provider() -> BedrockProvider:
    """Return the process-wide singleton BedrockProvider."""
    global _BEDROCK_SINGLETON
    if _BEDROCK_SINGLETON is None:
        with _BEDROCK_SINGLETON_LOCK:
            if _BEDROCK_SINGLETON is None:
                _BEDROCK_SINGLETON = BedrockProvider()
    return _BEDROCK_SINGLETON


def _reset_bedrock_provider_for_tests() -> None:
    """Reset the Bedrock provider singleton. Test-only."""
    global _BEDROCK_SINGLETON
    with _BEDROCK_SINGLETON_LOCK:
        _BEDROCK_SINGLETON = None
    _reset_bedrock_singletons_for_tests()


# ── Entitlement fallback (R328.2) ────────────────────────────────────────────
#
# The R328 operator targets (opus-4-8 / opus-5 / sonnet-5) stay the pinned code
# defaults. Measured 2026-08-13 against the live ABSK key, ALL THREE return
# ``AccessDeniedException`` while opus-4-6-v1 / sonnet-4-6 invoke fine — a
# credential-vintage artefact, not an account block: a Bedrock API key carries
# an IAM policy fixed at creation, and granting model access afterwards does not
# widen an existing key.
#
# So the pins are the ASPIRATION and this chain is what actually ships: re-mint
# the key and the pinned tier resumes with zero code change; leave it and every
# request still succeeds one tier down. Both halves must be real — a fallback
# whose target equals the primary is the inert-feature trap.

# Anchored on the ``api_`` prefix that ``_classify_client_error`` emits. A bare
# substring match is unsafe: the blanket ``except Exception`` handler formats
# errors as ``unexpected_error: {TypeName}: {msg}``, so a botocore
# ``ParamValidationError`` or a pydantic ``ValidationError`` — a CODE BUG that
# fails identically on every model — would otherwise read as "entitlement" and
# burn the whole chain.
BEDROCK_ENTITLEMENT_ERROR_MARKERS: tuple[str, ...] = (
    "api_access_denied",       # 403 — this key lacks the entitlement
    "api_resource_not_found",  # 404 — the profile does not exist here
)
"""Per-MODEL failures. Durable for this credential → safe to remember."""

BEDROCK_TRANSIENT_SKIP_MARKERS: tuple[str, ...] = (
    "api_validation",  # 400
)
"""Advance the chain but DO NOT remember. ``ValidationException`` is overloaded:
it covers "this profile is unresolvable in this Region" (per-model) AND
"input too long / bad maxTokens / bad temperature" (per-REQUEST). Caching the
per-request case as a model denial lets ONE oversized prompt evict the only
invocable model for the whole TTL — a single long row poisoning the rest of a
judge batch.

R346.1 — ``api_key_invalid_403`` is deliberately in NEITHER tuple. It is a
GLOBAL credential failure: every model fails identically, so advancing the
chain only burns round-trips, and remembering per-model denials would delay
healing after the key is re-minted. Failing fast (``is_skippable_error``
False) also keeps a dead key from triggering the cross-provider wrapper hop
— the tunnel is the operator's reserved transport, not a recovery path for
an expired credential."""

BEDROCK_FALLBACK_CHAINS: dict[str, tuple[str, ...]] = {
    "opus": (
        "eu.anthropic.claude-opus-4-8",
        "eu.anthropic.claude-opus-5",
        "eu.anthropic.claude-opus-4-6-v1",
    ),
    "sonnet": (
        "eu.anthropic.claude-sonnet-5",
        "eu.anthropic.claude-sonnet-4-6",
        "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ),
}
"""Ordered degradation chains, most-capable first. Verified invocable tail as of
2026-08-13; the head entries are the R328 pins."""

_DENIED_TTL_SECONDS = 900.0
"""How long a 403 is remembered. Bounded so a re-minted key heals the process
without a redeploy — an unbounded memo would pin the degraded tier forever."""

_DENIED_MODELS: dict[str, float] = {}
_DENIED_LOCK = threading.Lock()


# ── Cross-PROVIDER last resort — ported from `regenold-eu-ai-act-rag` ────────
#
# The entitlement chain above degrades WITHIN the Bedrock family. When every
# member of the chain is unusable — the whole EU geography throttling, the key
# revoked, the endpoint unreachable — Bedrock has nothing left to offer and the
# RAG path returns None, which drops Stage-2 entirely.
#
# The sibling repo answers that with a fail-soft hop to the Claude-Max wrapper.
# Ported here, but placed at the END of `complete_with_fallback` rather than
# inside `BedrockProvider.complete`'s two exception handlers (where the sibling
# put it). Two reasons: it keeps ONE definition of "we have exhausted Bedrock"
# instead of two, and it guarantees the entitlement chain is fully spent before
# we leave the provider — the sibling's placement can hop to the wrapper on the
# FIRST model's throttle while a perfectly invocable tier sits further down.
#
# ⚠ THIS IS A MEASUREMENT EVENT, NOT JUST A RESILIENCE EVENT, and that is why it
# is louder here than in the sibling. The two providers are NOT interchangeable:
#   * Bedrock HONOURS the system prompt; the Claude-Max wrapper DROPS it 100% of
#     the time (claude_agent_sdk 0.2.82 discards a `{"type":"text"}` dict — see
#     CLAUDE.md and `.planning/R282-CHECKPOINT.md`; re-verified live 2026-08-14
#     with the ARRR probe: system slot -> "4", user slot -> "ARRR").
#   * So a silent hop changes ~12.8K tokens of delivered instruction. In a repo
#     whose PRODUCT is the measurement, that must reach the durable artifact.
# We therefore return the wrapper's answer with `model` prefixed `wrapper:`,
# which makes the EXISTING provenance in `_bedrock_complete_for_graph_rag` fire
# unchanged (`_served != model_id` -> `stage2_model=` + `bedrock_fallback` notes
# in the reasoning trace, which `run_official_batch._provenance` scrapes).
_WRAPPER_FALLBACK_MODELS: tuple[tuple[str, str], ...] = (
    ("opus-4-6", "claude-opus-4-6"),
    ("opus-4.6", "claude-opus-4-6"),
    ("sonnet-4-6", "claude-sonnet-4-6"),
    ("sonnet-4.6", "claude-sonnet-4-6"),
    ("opus", "claude-opus-4-8"),
    ("sonnet", "claude-sonnet-4-6"),
)
"""Bedrock profile substring -> wrapper model name. Ordered MOST specific first:
a bare `opus`/`sonnet` entry placed before `opus-4-6` would swallow it."""


def wrapper_fallback_enabled() -> bool:
    """R330 — hop to the Claude-Max wrapper when the whole Bedrock chain fails.

    DEFAULT **ON**. Off-switch: ``REGENOLD_BEDROCK_WRAPPER_FALLBACK=0``.

    Default-ON as a CODE default because `railway.toml [deploy.envs]` has never
    applied (CLAUDE.md gotcha), so an opt-in resilience flag would never reach
    the deployment — which is the one place it matters.

    Fresh env read per call so an in-process A/B is valid (R263.2 doctrine).
    """
    return os.environ.get(
        "REGENOLD_BEDROCK_WRAPPER_FALLBACK", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}


def wrapper_model_for(bedrock_model_id: str) -> str:
    """Map a Bedrock EU profile id onto the wrapper's model name."""
    low = (bedrock_model_id or "").lower()
    for needle, wrapper_model in _WRAPPER_FALLBACK_MODELS:
        if needle in low:
            return wrapper_model
    return "claude-sonnet-4-6"


def _try_wrapper_fallback(
    req: BedrockRequest, primary: str, last: BedrockResponse | None
) -> BedrockResponse | None:
    """Last resort: serve this request from the Claude-Max wrapper.

    Returns ``None`` when the hop is disabled, the wrapper is not wired, or it
    also fails — in which case the caller keeps Bedrock's real error string.
    """
    if not wrapper_fallback_enabled():
        return None
    try:
        from app.llm.openai_wrapper_provider import (  # noqa: PLC0415
            OpenAIWrapperRequest,
            get_openai_wrapper_provider,
            is_openai_wrapper_enabled,
        )

        if not is_openai_wrapper_enabled():
            return None
        target = wrapper_model_for(req.model or primary)
        resp = get_openai_wrapper_provider().complete(
            OpenAIWrapperRequest(
                user=req.user,
                system=req.system,
                model=target,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        )
        if resp.error or not resp.text:
            logger.warning(
                "bedrock_wrapper_fallback_failed primary=%s target=%s error=%s",
                primary, target, resp.error,
            )
            return None
        # LOUD, and greppable. `served_by=wrapper:` is the string to alert on:
        # its presence means the answer was NOT produced under the Bedrock
        # prompt contract, so the row is not comparable to a Bedrock-served one.
        logger.warning(
            "bedrock_wrapper_fallback_used primary=%s served_by=wrapper:%s "
            "bedrock_error=%s SYSTEM_PROMPT_DROPPED=1",
            primary, target, (last.error if last else "unknown"),
        )
        return BedrockResponse(
            text=resp.text,
            model=f"wrapper:{resp.model or target}",
            input_tokens=resp.prompt_tokens,
            output_tokens=resp.completion_tokens,
            elapsed_ms=resp.elapsed_ms,
            finish_reason=resp.finish_reason,
        )
    except Exception as exc:  # noqa: BLE001 — a fallback must never raise
        logger.debug("bedrock_wrapper_fallback_error: %s", exc)
        return None


def is_entitlement_error(error: str | None) -> bool:
    """True when ``error`` is a DURABLE per-model entitlement failure.

    These are the only errors worth REMEMBERING: a throttle or a timeout will
    hit the next model in the chain just as hard, so burning the chain on one
    would turn a transient blip into N failed calls.
    """
    if not error:
        return False
    low = error.lower()
    return any(marker in low for marker in BEDROCK_ENTITLEMENT_ERROR_MARKERS)


def is_skippable_error(error: str | None) -> bool:
    """True when ``error`` should advance the chain, durable or not."""
    if not error:
        return False
    low = error.lower()
    return is_entitlement_error(error) or any(
        marker in low for marker in BEDROCK_TRANSIENT_SKIP_MARKERS
    )


def _note_denied(model_id: str) -> None:
    with _DENIED_LOCK:
        _DENIED_MODELS[model_id] = time.monotonic()


def _is_denied(model_id: str) -> bool:
    with _DENIED_LOCK:
        at = _DENIED_MODELS.get(model_id)
        if at is None:
            return False
        if (time.monotonic() - at) > _DENIED_TTL_SECONDS:
            del _DENIED_MODELS[model_id]
            return False
        return True


def reset_bedrock_entitlement_cache() -> None:
    """Forget every remembered 403. Test-only / operator escape hatch."""
    with _DENIED_LOCK:
        _DENIED_MODELS.clear()


def fallback_chain_for(model_id: str) -> tuple[str, ...]:
    """Return the candidates to DEGRADE to, strictly below ``model_id``.

    The chain is ordered most-capable first, so the fallbacks for a model are
    the SUFFIX after its own position — never the whole chain. Returning the
    whole chain would ESCALATE a non-head pin: pinning sonnet-4-6 would retry
    on sonnet-5, i.e. silently promote to a costlier model the operator
    specifically did not choose.

    Unknown families, and models absent from their family's chain, get an empty
    tuple — we never guess a substitute for a model whose rank we do not know.
    """
    low = (model_id or "").lower()
    for family, chain in BEDROCK_FALLBACK_CHAINS.items():
        if family not in low:
            continue
        lowered = [c.lower() for c in chain]
        if low in lowered:
            return chain[lowered.index(low) + 1:]
        return ()
    return ()


def complete_with_fallback(
    req: BedrockRequest, *, fallbacks: tuple[str, ...] | None = None
) -> BedrockResponse:
    """``BedrockProvider.complete`` plus ordered entitlement failover.

    Tries the request's own model first, then each remaining candidate in its
    family chain, advancing ONLY on an entitlement error. Models already proven
    denied in this process are skipped outright, so the 403 round-trip is paid
    once per TTL rather than once per request.

    Returns the first success; otherwise the LAST response, so the caller still
    sees a real error string rather than a synthetic one.
    """
    provider = get_bedrock_provider()
    primary = resolve_bedrock_model(req.model) if req.model else _resolve_default_model()

    chain = fallbacks if fallbacks is not None else fallback_chain_for(primary)

    ordered: list[str] = []
    for candidate in (primary, *chain):
        resolved = resolve_bedrock_model(candidate)
        if resolved not in ordered:
            ordered.append(resolved)

    # Skip known-denied models, but never skip everything. When the whole chain
    # is cached-denied, re-probe the LAST entry, not the first: the head is the
    # pinned tier that is 403 by construction, so re-probing it just burns the
    # round-trip we cached to avoid. The tail is the most-likely-invocable.
    live = [m for m in ordered if not _is_denied(m)] or ordered[-1:]

    last: BedrockResponse | None = None
    for idx, model_id in enumerate(live):
        resp = provider.complete(replace(req, model=model_id))
        if not resp.error:
            if model_id != primary:
                logger.warning(
                    "bedrock_entitlement_fallback_used primary=%s served_by=%s",
                    primary,
                    model_id,
                )
            return resp
        last = resp
        if not is_skippable_error(resp.error):
            return resp
        # Only DURABLE denials are remembered. A ValidationException may be
        # about this request, not this model — caching it would evict a
        # working model for the whole TTL.
        if is_entitlement_error(resp.error):
            _note_denied(model_id)
        logger.warning(
            "bedrock_model_skipped model=%s error=%s durable=%s remaining=%d",
            model_id,
            resp.error,
            is_entitlement_error(resp.error),
            len(live) - idx - 1,
        )

    # Bedrock is exhausted. Try the cross-provider last resort before giving up
    # — but only now, so a working lower tier is never skipped in its favour.
    hopped = _try_wrapper_fallback(req, primary, last)
    if hopped is not None:
        return hopped

    return last or BedrockResponse(
        error="no_invocable_model", model=primary
    )
