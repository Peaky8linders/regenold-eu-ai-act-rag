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
from dataclasses import dataclass, field
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
    tool_use: list[dict[str, Any]] = field(default_factory=list)
    """Parsed tool use blocks from the Converse response, if any."""


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
    if name.startswith(("us.", "eu.", "ap.", "global.", "arn:", "anthropic.", "amazon.", "meta.")):
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

    return kwargs


def _parse_converse_response(
    response: dict[str, Any], model_id: str, elapsed_ms: int
) -> BedrockResponse:
    """Parse a Converse API response into a ``BedrockResponse``."""
    output = response.get("output", {})
    message = output.get("message", {})
    content_blocks = message.get("content", [])

    text_parts: list[str] = []
    tool_use_blocks: list[dict[str, Any]] = []

    for block in content_blocks:
        if "text" in block:
            text_parts.append(block["text"])
        elif "toolUse" in block:
            tool_use_blocks.append(block["toolUse"])

    usage = response.get("usage", {})
    stop_reason = response.get("stopReason", "")

    return BedrockResponse(
        text="\n".join(text_parts),
        model=model_id,
        input_tokens=usage.get("inputTokens", 0),
        output_tokens=usage.get("outputTokens", 0),
        elapsed_ms=elapsed_ms,
        finish_reason=stop_reason or None,
        tool_use=tool_use_blocks,
    )


def _classify_client_error(exc: ClientError) -> str:
    """Map botocore ClientError to a categorised error string."""
    code = exc.response.get("Error", {}).get("Code", "Unknown")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)

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
        client = _TIMEOUT_CLIENTS.get(key)
        if client is None:
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
