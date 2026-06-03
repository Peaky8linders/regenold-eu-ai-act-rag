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
+ Anthropic SDK paths. A regulator + a partner can plug in their own
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

    extra_headers: dict[str, str] = Field(default_factory=dict)
    """R51 — per-request header overrides sent to the wrapper. Used to
    enable Claude's extended-thinking mode via the
    ``X-Claude-Max-Thinking-Tokens`` header on complex Stage-2 polish
    calls. The wrapper's ``parameter_validator.py`` maps the header to
    the SDK's ``max_thinking_tokens`` option, which translates to the
    Anthropic API's ``thinking={"type": "enabled", "budget_tokens": N}``.

    Empty dict (default) sends no extra headers — extended thinking
    stays off. Adding ``X-Claude-Max-Thinking-Tokens: "8000"`` enables
    8000 thinking-token budget for THIS call only — no global state
    change.
    """


class OpenAIWrapperResponse(BaseModel):
    text: str = ""
    error: str | None = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: int = 0
    finish_reason: str | None = None
    """OpenAI chat-completion ``finish_reason`` from the upstream choice.

    Raw passthrough — common values: ``"stop"`` (natural completion),
    ``"length"`` (truncated at ``max_tokens``), ``"content_filter"``,
    ``"tool_calls"``. ``None`` when missing or the call errored before a
    choice landed. Callers (R91 truncation guard) treat ``"length"`` as
    a soft failure — a length-truncated rewrite or polish is partial
    output that must not flow downstream as if it were natural-stop.
    """


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
    """The wrapper is enabled by default. We default to the Cloudflare named
    tunnel for the Claude Max subscription path.
    """
    return True


class _OpenAIWrapperProvider:
    """OpenAI Chat Completions client. One pooled httpx.Client per process.

    Constructor accepts explicit ``base_url`` / ``api_key`` / ``timeout``
    so callers can spin up parallel providers against different endpoints
    (e.g. Stage-1/2 polish against the Claude Max wrapper, Stage-0 intent
    against Groq). All three default to env-derived values for the
    backwards-compatible singleton path.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (
            (base_url or os.getenv("OPENAI_API_BASE", "")).strip().rstrip("/")
            or "https://wrapper.antifragile-ai.net/v1"
        )
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "dummy")
        # 60 s default — Claude Sonnet 4.6 Stage-2 polish through the
        # claude-code-openai-wrapper takes 10-20 s for non-trivial
        # questions; the deterministic Stage-1 already landed, so the
        # caller is willing to wait for the polish. On timeout the wrapper
        # returns an error and the engine falls back to Stage-1. The 8-s
        # bound that was here before was a competition-rubric leftover and
        # killed every real Sonnet call in production. Per-call shorter
        # budgets (e.g. intent classifier's 2.5 s) come via
        # ``OpenAIWrapperRequest.timeout_seconds``, not by mutating env.
        self._timeout = (
            timeout if timeout is not None
            else float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
        )
        # Pooled long-lived client = one TLS handshake + persistent
        # connection pool. Per-request `httpx.post` opens a fresh TLS
        # handshake AND leaks sockets in TIME_WAIT under concurrent load.
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
        # R51 — merge per-request extra_headers (e.g.
        # ``X-Claude-Max-Thinking-Tokens``) onto the default Auth +
        # Content-Type headers. The wrapper's parameter_validator
        # interprets ``X-Claude-Max-Thinking-Tokens`` as the SDK's
        # ``max_thinking_tokens`` option — which translates to extended
        # thinking on the underlying Anthropic API call.
        merged_headers = self._headers()
        if req.extra_headers:
            merged_headers.update(req.extra_headers)
        try:
            response = self._client.post(
                "/chat/completions",
                headers=merged_headers,
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
                            headers=merged_headers,
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
            finish_reason = choice.get("finish_reason")
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
            finish_reason=finish_reason,
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


# ── Groq intent provider (Round 52, Phase-1 Claude Max → Pro migration) ─────
#
# A second pooled provider singleton points at Groq's OpenAI-compatible
# Chat Completions endpoint. Currently used ONLY by the Stage-0 intent
# classifier when ``REGENOLD_INTENT_PROVIDER=groq``. Stage-1/2 polish
# stays on the existing wrapper singleton (Claude Max via cloudflared).
#
# Why a separate singleton: the existing wrapper singleton is bound to
# ``OPENAI_API_BASE`` at construction time. We need two endpoints live
# in the same process to A/B intent classification without touching the
# Stage-2 polish path the V2 multi-turn coherence axis depends on.
#
# Default endpoint is Groq's public OpenAI-spec URL; override via
# ``GROQ_API_BASE`` if the operator routes through an internal proxy.

_GROQ_DEFAULT_BASE = "https://api.groq.com/openai/v1"
_GROQ_SINGLETON: _OpenAIWrapperProvider | None = None
_GROQ_SINGLETON_LOCK = threading.Lock()


def is_groq_provider_enabled() -> bool:
    """True iff general Groq provider is enabled.

    Requires GROQ_API_KEY.
    """
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def is_groq_intent_provider_enabled() -> bool:
    """True iff Stage-0 intent should route to Groq.

    R94 — Groq Llama 3.3 70B is the **default** Stage-0 intent provider
    (replacing Claude Haiku via the wrapper). A non-empty ``GROQ_API_KEY``
    is always required. Selection on top of that:

    * ``REGENOLD_INTENT_PROVIDER=groq``  → Groq (explicit).
    * ``REGENOLD_INTENT_PROVIDER`` unset → Groq (R94 default, because a
      key is present).
    * ``REGENOLD_INTENT_PROVIDER=<other>`` (``wrapper`` / ``haiku`` /
      ``openai_wrapper`` / ``anthropic`` / ``cli``) → NOT Groq — explicit
      opt-out routes Stage-0 back to the wrapper/Haiku path.

    Without a ``GROQ_API_KEY`` this always returns False, so the
    historical wrapper/Haiku path is preserved — and the davidath
    TestClient bench (no ``GROQ_API_KEY`` in env) stays byte-identical.
    """
    if not is_groq_provider_enabled():
        return False
    provider_choice = (
        os.getenv("REGENOLD_INTENT_PROVIDER", "").strip().lower()
    )
    if provider_choice in ("", "groq"):
        return True
    # Explicit non-groq choice opts back out to the wrapper path.
    return False


def get_groq_provider() -> _OpenAIWrapperProvider:
    """Return the process-wide pooled Groq provider.

    Same double-checked-locking shape as the default singleton. Reads
    ``GROQ_API_BASE`` (default ``https://api.groq.com/openai/v1``) and
    ``GROQ_API_KEY`` at first construction. The 60 s default timeout
    matches Stage-2 needs — intent fast-fail posture uses per-request
    timeout overrides.
    """
    global _GROQ_SINGLETON
    if _GROQ_SINGLETON is None:
        with _GROQ_SINGLETON_LOCK:
            if _GROQ_SINGLETON is None:
                _GROQ_SINGLETON = _OpenAIWrapperProvider(
                    base_url=(
                        os.getenv("GROQ_API_BASE", "").strip()
                        or _GROQ_DEFAULT_BASE
                    ),
                    api_key=os.getenv("GROQ_API_KEY", ""),
                    timeout=float(os.getenv("GROQ_TIMEOUT_SECONDS", "60")),
                )
    return _GROQ_SINGLETON


get_groq_intent_provider = get_groq_provider

def _reset_groq_singleton_for_tests() -> None:
    """Reset the Groq singleton. Test-only — not part of the public API."""
    global _GROQ_SINGLETON
    with _GROQ_SINGLETON_LOCK:
        if _GROQ_SINGLETON is not None:
            try:
                _GROQ_SINGLETON._close()  # noqa: SLF001 — test hook
            except Exception:  # noqa: BLE001
                pass
        _GROQ_SINGLETON = None


# ── Gemini provider (OpenAI-compatible) ──────────────────────────────────────

_GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI_SINGLETON: _OpenAIWrapperProvider | None = None
_GEMINI_SINGLETON_LOCK = threading.Lock()


def is_gemini_provider_enabled() -> bool:
    """True iff Gemini provider is enabled.

    Requires GEMINI_API_KEY.
    """
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def get_gemini_provider() -> _OpenAIWrapperProvider:
    """Return the process-wide pooled Gemini provider.

    Same double-checked-locking shape as the default singleton. Reads
    ``GEMINI_API_BASE`` (default ``https://generativelanguage.googleapis.com/v1beta/openai/``) and
    ``GEMINI_API_KEY`` at first construction.
    """
    global _GEMINI_SINGLETON
    if _GEMINI_SINGLETON is None:
        with _GEMINI_SINGLETON_LOCK:
            if _GEMINI_SINGLETON is None:
                _GEMINI_SINGLETON = _OpenAIWrapperProvider(
                    base_url=(
                        os.getenv("GEMINI_API_BASE", "").strip()
                        or _GEMINI_DEFAULT_BASE
                    ),
                    api_key=os.getenv("GEMINI_API_KEY", ""),
                    timeout=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60")),
                )
    return _GEMINI_SINGLETON


def _reset_gemini_singleton_for_tests() -> None:
    """Reset the Gemini singleton. Test-only — not part of the public API."""
    global _GEMINI_SINGLETON
    with _GEMINI_SINGLETON_LOCK:
        if _GEMINI_SINGLETON is not None:
            try:
                _GEMINI_SINGLETON._close()  # noqa: SLF001 — test hook
            except Exception:  # noqa: BLE001
                pass
        _GEMINI_SINGLETON = None

