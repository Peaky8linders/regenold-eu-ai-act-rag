"""OpenAI-compatible-endpoint provider — Claude-Max-via-wrapper bridge.

Targets the local ``claude-code-openai-wrapper`` (an OpenAI Chat
Completions facade over a Claude Max subscription / Anthropic API key).
Default endpoint: ``http://127.0.0.1:8000/v1`` per the wrapper's
upstream defaults.

Activate via env:
    P2P_GRAPH_RAG_PROVIDER=openai_wrapper
    OPENAI_API_BASE=http://127.0.0.1:8000/v1   (optional override)
    OPENAI_API_KEY=dummy                       (any non-empty string)

Why this exists in the bundle:
The Regenold eval round-5 plan A/Bs Sonnet 4.6 against the deterministic
+ Mistral paths. A regulator + a partner can plug in their own
``OPENAI_API_BASE`` (any OpenAI-spec endpoint — OpenAI, OpenRouter,
the wrapper, etc.) and exercise the same eval suite end-to-end.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OpenAIWrapperRequest(BaseModel):
    system: str = ""
    user: str = Field(min_length=1)
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024
    temperature: float = 0.0
    timeout_seconds: float | None = None
    """Per-call timeout override. When ``None``, uses the provider
    singleton's default (``OPENAI_TIMEOUT_SECONDS`` env, 60 s fallback).
    The intent classifier sets a short 2.5 s timeout via this so its
    failure path is fast, without poisoning the singleton's timeout for
    Stage-1/2 Sonnet calls that take 10-20 s.
    """


class OpenAIWrapperResponse(BaseModel):
    text: str = ""
    error: str | None = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: int = 0


# Cap on Retry-After we'll honour. The Regenold latency budget is
# sub-second p95 on the deterministic path; a 60 s sleep mid-Stage-2
# would block the request thread for far longer than any partner is
# willing to wait. On anything above this cap we surface api_status_429
# and let the engine fall back to deterministic immediately.
_MAX_RETRY_AFTER_SECONDS = float(os.getenv("OPENAI_MAX_RETRY_AFTER", "8"))


def _parse_retry_after(header_value: str | None) -> float:
    """Parse the Retry-After header per RFC 7231 §7.1.3.

    Returns 0.0 when missing or unparseable. Honours both the
    ``delta-seconds`` integer form (slowapi's default) and an
    HTTP-date — we don't bother with HTTP-date because the upstream
    wrapper's slowapi always emits integer seconds.
    """
    if not header_value:
        return 0.0
    try:
        return max(0.0, float(header_value.strip()))
    except (TypeError, ValueError):
        return 0.0


def is_openai_wrapper_enabled() -> bool:
    """The wrapper is enabled when any non-empty base URL OR a non-default
    OPENAI_API_KEY is present. We don't network-probe at import time —
    callers will hit ``error`` on a missing endpoint.
    """
    return bool(
        os.getenv("OPENAI_API_BASE", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


class _OpenAIWrapperProvider:
    """OpenAI Chat Completions client. One pooled httpx.Client per process."""

    def __init__(self) -> None:
        self._base_url = (
            os.getenv("OPENAI_API_BASE", "").strip().rstrip("/")
            or "http://127.0.0.1:8000/v1"
        )
        self._api_key = os.getenv("OPENAI_API_KEY", "dummy")
        # 60 s default — Claude Sonnet 4.6 Stage-2 polish through the
        # claude-code-openai-wrapper takes 10-20 s for non-trivial
        # questions; the deterministic Stage-1 already landed, so the
        # caller is willing to wait for the polish. On timeout the wrapper
        # returns an error and the engine falls back to Stage-1. The 8-s
        # bound that was here before was a competition-rubric leftover and
        # killed every real Sonnet call in production. Per-call shorter
        # budgets (e.g. intent classifier's 2.5 s) come via
        # ``OpenAIWrapperRequest.timeout_seconds``, not by mutating env.
        self._timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
        # Pooled client — see mistral_provider.py for the rationale.
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
            ),
        )
        import atexit
        atexit.register(self._close)

    def _close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — atexit best-effort
            pass

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def complete(self, req: OpenAIWrapperRequest) -> OpenAIWrapperResponse:
        body = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.system} if req.system else None,
                {"role": "user", "content": req.user},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "stream": False,
        }
        body["messages"] = [m for m in body["messages"] if m is not None]

        # Per-request timeout override — the intent classifier wants a
        # short 2.5 s budget for its fast-fail behaviour but the
        # Stage-1/2 Sonnet calls need 60 s. Without this knob a single
        # caller setting OPENAI_TIMEOUT_SECONDS via env would poison the
        # singleton for everyone (the bug that killed bench round 29).
        request_timeout: float | httpx.Timeout = (
            req.timeout_seconds if req.timeout_seconds is not None
            else self._timeout
        )
        # Issue #48: end-to-end deadline. The caller's `timeout_seconds`
        # is a budget for the WHOLE call (including any 429 backoff),
        # not just one HTTP attempt. Track a wall-clock deadline so a
        # Retry-After sleep can't blow past the caller's budget.
        if isinstance(request_timeout, (int, float)):
            budget_seconds = float(request_timeout)
        else:
            budget_seconds = self._timeout

        start = time.perf_counter()
        deadline = start + budget_seconds
        try:
            response = self._client.post(
                "/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=request_timeout,
            )
        except httpx.HTTPError as exc:
            return OpenAIWrapperResponse(
                error=f"network_error: {exc!s}"[:200],
                model=req.model,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )

        # One-shot retry on HTTP 429 (the upstream wrapper's slowapi
        # gate defaults to RATE_LIMIT_CHAT_PER_MINUTE=10, which is easy
        # to brush past on benchmark runs or bursty partner traffic).
        # We honour the Retry-After hint capped at _MAX_RETRY_AFTER so
        # we don't block the request thread longer than the engine's
        # latency budget tolerates. Single attempt — if the second call
        # also 429s the caller falls back to deterministic.
        if response.status_code == 429:
            retry_after = _parse_retry_after(
                response.headers.get("Retry-After")
            )
            if retry_after > 0 and retry_after <= _MAX_RETRY_AFTER_SECONDS:
                # Issue #48: skip the retry if Retry-After + a ~250 ms
                # network allowance would push past the caller's budget.
                # Surface api_status_429 immediately so the engine falls
                # back to deterministic instead of waiting past the
                # caller's deadline.
                remaining = deadline - time.perf_counter()
                if retry_after + 0.250 >= remaining:
                    logger.info(
                        "openai_wrapper.429_skip_retry "
                        "retry_after=%.1fs remaining=%.2fs",
                        retry_after,
                        remaining,
                    )
                else:
                    logger.info(
                        "openai_wrapper.429_retry_after=%.1fs "
                        "(capped at %.0fs, remaining=%.2fs)",
                        retry_after,
                        _MAX_RETRY_AFTER_SECONDS,
                        remaining,
                    )
                    time.sleep(retry_after)
                    # Retry POST inherits the SHORTENED remaining budget.
                    retry_timeout = max(
                        0.001, deadline - time.perf_counter()
                    )
                    try:
                        response = self._client.post(
                            "/chat/completions",
                            headers=self._headers(),
                            json=body,
                            timeout=retry_timeout,
                        )
                    except httpx.HTTPError as exc:
                        return OpenAIWrapperResponse(
                            error=f"network_error_on_retry: {exc!s}"[:200],
                            model=req.model,
                            elapsed_ms=int((time.perf_counter() - start) * 1000),
                        )

        if response.status_code != 200:
            return OpenAIWrapperResponse(
                error=f"api_status_{response.status_code}: {response.text[:200]}",
                model=req.model,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )

        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            return OpenAIWrapperResponse(
                error=f"decode_error: {exc!s}"[:200],
                model=req.model,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )

        # The wrapper sometimes ships sentinel responses like
        # ``"Not logged in · Please run /login"`` with HTTP 200. Surface
        # those as errors so the engine falls back to deterministic
        # instead of shipping the sentinel as the answer text.
        if "Not logged in" in text or "Please run /login" in text:
            return OpenAIWrapperResponse(
                error=f"wrapper_not_logged_in: {text[:120]}",
                model=req.model,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )

        usage = payload.get("usage") or {}
        return OpenAIWrapperResponse(
            text=text,
            model=payload.get("model", req.model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            elapsed_ms=int((time.perf_counter() - start) * 1000),
        )


_SINGLETON: _OpenAIWrapperProvider | None = None
_SINGLETON_LOCK = threading.Lock()


def get_openai_wrapper_provider() -> _OpenAIWrapperProvider:
    """Return the process-wide pooled provider. Thread-safe on first call.

    Without the lock, two concurrent cold-start requests could each
    construct an ``_OpenAIWrapperProvider``; the first's pooled
    ``httpx.Client`` would be silently leaked (its atexit close still
    fires, but the in-flight requests using it have no path back to
    the leaked instance). Double-checked locking keeps the hot path
    lock-free after init.
    """
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = _OpenAIWrapperProvider()
    return _SINGLETON
