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


# R112 — Claude Code CLI failure shapes the wrapper can relay as an
# HTTP 200 completion body. Matched case-insensitively as substrings of
# the completion text. Every entry must be a phrase that can NEVER occur
# in a legitimate EU AI Act answer (CLI/tooling vocabulary only) — a
# false positive here silently downgrades a good Sonnet answer to the
# deterministic fallback.
_WRAPPER_CLI_ERROR_SENTINELS: tuple[str, ...] = (
    # Model-resolution failure (observed live 2026-06-10: "There's an
    # issue with the selected model (fable-5). It may not exist or you
    # may not have access to it. Run --model to pick a different model.")
    "there's an issue with the selected model",
    "there is an issue with the selected model",
    "run --model to pick a different model",
    # Wrapper-internal process failures relayed as completion text.
    "no response from claude code",
    "claude code process exited",
    # Anthropic-side auth/quota strings relayed verbatim by the CLI.
    "invalid api key",
    "credit balance is too low",
)


# R300 — wrapper model-alias map.
#
# The 2026-07-30 truncation commit (757f0cb) introduced a HARDCODED rewrite of
# every ``opus``-family model name to ``claude-opus-4-6`` inline in
# ``complete()``: no env gate, no log line, and unmentioned in its commit
# message. It silently reverted R292's shipped Opus 5 Stage-2 and made the
# ``?include_reasoning=true`` trace LIE — the trace reports
# ``stage2_model=claude-opus-5`` while the transport sends ``claude-opus-4-6``,
# which would silently corrupt any future model A/B (the R263.2 class of
# measurement bug).
#
# Verified 2026-07-30 against the live wrapper: ``claude-opus-4-8``,
# ``claude-opus-5`` AND ``claude-opus-4-6`` all return HTTP 200, so the rewrite
# is NOT repairing a wrapper error. It is kept as the DEFAULT only because
# flipping it is an answer-affecting change that needs the hard-rule-#6 live
# ``ab_judge`` gate — but it is now env-gated, logged once per distinct
# rewrite, and reported truthfully on the wire.
#
# Set ``REGENOLD_WRAPPER_MODEL_ALIAS=0`` to send the requested model verbatim
# (the arm a future A/B should measure).
_WRAPPER_MODEL_ALIASES: dict[str, str] = {
    "claude-opus-5": "claude-opus-4-6",
    "claude-5-opus": "claude-opus-4-6",
    "opus-5": "claude-opus-4-6",
    "claude-opus-5.0": "claude-opus-4-6",
    "opus": "claude-opus-4-6",
    "claude-opus-4-8": "claude-opus-4-6",
}

_ALIAS_LOGGED: set[str] = set()


def _model_alias_enabled() -> bool:
    """Fresh env read per call (R263.2).

    **DEFAULT OFF as of R308** (was ON). Operator directive 2026-08-03: Stage-2
    must run on Opus 5, not Sonnet 4.6 or Opus 4.6.

    WHY THE DEFAULT FLIPPED. ``GraphRAGSettings.stage2_model`` and
    ``complex_model`` have both been ``claude-opus-5`` since R292, but this
    table silently rewrote it to ``claude-opus-4-6`` on the way to the wire, so
    NO request has actually run on Opus 5. The rewrite arrived ungated and
    unlogged in an undisclosed rider to commit 757f0cb; R300 caught it, made it
    loggable and env-gated, but kept the default ON because flipping it needed
    evidence. That evidence now exists.

    MEASURED against the live wrapper 2026-08-03 (POST /v1/chat/completions,
    one tiny probe each):
        claude-opus-5              -> HTTP 200, model echoed 'claude-opus-5'
        claude-opus-4-6            -> HTTP 200
        claude-opus-4-8            -> HTTP 200
        claude-sonnet-5            -> HTTP 200
        definitely-not-a-model-xyz -> HTTP 500 "No response from Claude Code"
    A bogus name fails loudly, so the 200 on ``claude-opus-5`` is real
    acceptance and not silent coercion. The wrapper's ``/v1/models`` list stops
    at ``claude-opus-4-6``, but that list is STALE: the model string is passed
    through to the Claude Code CLI, which resolves it. Do not treat
    ``/v1/models`` as the source of truth for what the wrapper accepts.

    So the alias was downgrading a model that works. With it off, the model on
    the wire is exactly the model in the config - which also makes the
    ``?include_reasoning=true`` trace honest again (R300 found it reporting
    ``claude-opus-5`` while ``claude-opus-4-6`` was actually being sent, which
    would silently invalidate any model A/B read off the trace).

    The table and the gate are kept, not deleted: ``REGENOLD_WRAPPER_MODEL_ALIAS=1``
    restores the pre-R308 downgrade in one env var if an Opus 5 rollout has to
    be backed out without a code revert.
    """
    return os.environ.get("REGENOLD_WRAPPER_MODEL_ALIAS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def resolve_wrapper_model(requested: str) -> str:
    """Return the model name actually sent to the wrapper for ``requested``.

    Public so the engine can report the EFFECTIVE model in the reasoning
    trace instead of the requested one.
    """
    name = (requested or "").strip()
    if not _model_alias_enabled():
        return name
    target = _WRAPPER_MODEL_ALIASES.get(name.lower())
    if not target or target == name:
        return name
    if name not in _ALIAS_LOGGED:
        _ALIAS_LOGGED.add(name)
        logger.warning(
            "openai_wrapper.model_alias requested=%s sent=%s "
            "(REGENOLD_WRAPPER_MODEL_ALIAS=0 to disable)",
            name,
            target,
        )
    return target


# Backwards-compatible private alias.
_resolve_wrapper_model = resolve_wrapper_model


class OpenAIWrapperRequest(BaseModel):
    system: str = ""
    user: str = Field(min_length=1)
    model: str = "claude-opus-4-8"
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

    reasoning_effort: str = ""
    """R264 — OpenAI/Groq ``reasoning_effort`` passthrough for open reasoning
    models. Groq's ``qwen/qwen3.6-27b`` and ``openai/gpt-oss-*`` are hybrid
    reasoning models that, left unconstrained, spend the whole ``max_tokens``
    budget on a hidden reasoning trace and truncate (``finish_reason=length``)
    before emitting the JSON / rewrite — breaking the Stage-0 intent classifier
    and the multi-turn de-noiser. Setting this controls that: ``"none"``
    (Qwen — no reasoning) / ``"low"`` (GPT-OSS — minimal reasoning) restores
    fast, clean, complete output.

    Empty (default) + a Groq reasoning model → :meth:`_OpenAIWrapperProvider.complete`
    auto-injects the right value per model family. Empty + a Claude model
    (the wrapper path) sends nothing — ``reasoning_effort`` is not an Anthropic
    parameter, so it is NEVER attached to a ``claude-*`` request.
    """


class OpenAIWrapperResponse(BaseModel):
    text: str = ""
    thinking: str | None = None
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


# R112 (perf finding #33) — connect-class timeout bound. The documented
# 60 s default is a READ budget for slow Sonnet generation; passing it as
# a bare float made httpx apply 60 s to the CONNECT class too, so a
# black-holed wrapper host (stale DNS / dropped tunnel hostname) stalled
# a threadpool worker for the full 60 s at connection time. 5 s is ample
# for TCP+TLS to a healthy endpoint; the read/write/pool classes keep the
# caller's full budget.
_CONNECT_TIMEOUT_SECONDS = 5.0


# R277 — Cloudflare Access service-token support.
#
# The Claude Max wrapper is exposed to Railway over a named cloudflared
# tunnel at ``wrapper.antifragile-ai.net``. A Cloudflare Access (Zero
# Trust) application now fronts that hostname, so unauthenticated calls
# — including Railway's — get an HTML "Cloudflare Access" login page with
# HTTP 401 (``Cf-Access-Aud`` header present). The engine reads that as
# ``api_status_401`` and falls back to the deterministic path, i.e.
# production silently serves NO Claude Max at all.
#
# Access is worth keeping: the wrapper has no real auth of its own (its
# ``Authorization: Bearer`` check is a no-op), so anyone who discovers the
# hostname could burn the Max quota. The correct fix is a service token —
# Access stays up, and the backend is allowed through by presenting the
# ``CF-Access-Client-Id`` / ``CF-Access-Client-Secret`` header pair.
#
# SCOPING IS SECURITY-CRITICAL. This provider class is reused verbatim for
# Groq / Gemini / Mistral (see the singletons below), which point at
# third-party hosts. Attaching the token unconditionally would transmit a
# Cloudflare service-token SECRET to api.groq.com, api.mistral.ai and
# generativelanguage.googleapis.com. So the headers are attached only when
# the instance's base_url host matches the Access-protected host.
_CF_ACCESS_CLIENT_ID_ENV = "CF_ACCESS_CLIENT_ID"
_CF_ACCESS_CLIENT_SECRET_ENV = "CF_ACCESS_CLIENT_SECRET"
_CF_ACCESS_HOSTNAME_ENV = "CF_ACCESS_HOSTNAME"
_DEFAULT_WRAPPER_BASE = "https://wrapper.antifragile-ai.net/v1"
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").strip().lower()
    except Exception:  # noqa: BLE001 — never let a malformed URL break provider init
        return ""


def _resolve_cf_access_headers(base_url: str) -> dict[str, str]:
    """Cloudflare Access service-token headers for ``base_url``, or ``{}``.

    Returns ``{}`` — i.e. behaviour identical to pre-R277 — unless ALL hold:
      * both ``CF_ACCESS_CLIENT_ID`` and ``CF_ACCESS_CLIENT_SECRET`` are set;
      * ``base_url`` is not a local host (a local wrapper has no Cloudflare
        edge in front of it, so the token would be pointless and would leak
        into a local process);
      * ``base_url``'s host equals the Access-protected host — taken from
        ``CF_ACCESS_HOSTNAME`` when set, else the host of ``OPENAI_API_BASE``
        (else the default wrapper host). This is what keeps the secret off
        the Groq / Gemini / Mistral endpoints.

    Fail-soft by construction: any missing/mismatched value yields ``{}``.
    """
    client_id = os.getenv(_CF_ACCESS_CLIENT_ID_ENV, "").strip()
    client_secret = os.getenv(_CF_ACCESS_CLIENT_SECRET_ENV, "").strip()
    if not client_id or not client_secret:
        return {}

    host = _host_of(base_url)
    if not host or host in _LOCAL_HOSTS:
        return {}

    protected = _host_of(
        f"https://{os.getenv(_CF_ACCESS_HOSTNAME_ENV, '').strip()}"
    ) or _host_of(
        os.getenv("OPENAI_API_BASE", "").strip() or _DEFAULT_WRAPPER_BASE
    )
    if not protected or host != protected:
        return {}

    return {
        "CF-Access-Client-Id": client_id,
        "CF-Access-Client-Secret": client_secret,
    }


class _BudgetTimeout(httpx.Timeout):
    """``httpx.Timeout`` that compares equal to its read-budget float.

    R112 — the per-request timeout contract is documented (and pinned by
    ``tests/test_llm_providers.py``) as ``post(timeout=<budget>)`` where
    ``<budget>`` is the caller's float budget. Splitting the connect
    class would otherwise break that ``== 60.0`` / ``== 2.5`` contract,
    so this subclass keeps float equality against the read budget while
    carrying the short connect bound. httpx normalises it via
    ``Timeout(instance)`` (attribute copy), so the wire behaviour is a
    plain ``httpx.Timeout``.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, bool):
            return NotImplemented
        if isinstance(other, (int, float)):
            return self.read == float(other)
        return super().__eq__(other)

    __hash__ = httpx.Timeout.__hash__


def _split_connect_timeout(budget_seconds: float) -> _BudgetTimeout:
    """Build the per-request timeout: full budget on read/write/pool,
    connect capped at ``min(_CONNECT_TIMEOUT_SECONDS, budget)`` so a
    short caller budget (intent 2.5 s, de-noiser 1.0 s) is never
    loosened by the connect cap."""
    return _BudgetTimeout(
        budget_seconds,
        connect=min(_CONNECT_TIMEOUT_SECONDS, budget_seconds),
    )


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
    """The wrapper is enabled by default (the Cloudflare named tunnel for the
    Claude Max subscription path).

    R127 — EXCEPT when ``P2P_GRAPH_RAG_PROVIDER`` is explicitly ``cli``. That
    is the documented "pure deterministic pipeline — no LLM call, sub-10ms
    p50" mode, so the wrapper and everything gated on it (Stage-0 intent
    classification, Stage-2 polish, fusion) must be OFF. Without this, intent
    classification fired a wrapper round-trip even on the cli path — free on a
    healthy tunnel, but a ~2s/row dead-port connect timeout in the
    deterministic eval harness on Windows, and a violation of the cli
    contract. Production (``=openai_wrapper``), ``=anthropic`` and the
    unset/``auto`` default are unaffected.
    """
    if os.getenv("P2P_GRAPH_RAG_PROVIDER", "").strip().lower() == "cli":
        return False
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
        # R277 — resolved once per instance (env is read at construction, as
        # for every other setting here). Empty for the local wrapper and for
        # the Groq / Gemini / Mistral instances; see _resolve_cf_access_headers.
        self._cf_access_headers = _resolve_cf_access_headers(self._base_url)
        if self._cf_access_headers:
            logger.info(
                "cloudflare_access_service_token_active host=%s",
                _host_of(self._base_url),
            )
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
        # R112 — split timeout classes: the 60 s budget is for READ
        # (slow Sonnet generation); connect is bounded at 5 s so a
        # black-holed host can't stall a worker for the full budget.
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                self._timeout,
                connect=min(_CONNECT_TIMEOUT_SECONDS, self._timeout),
            ),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                # Keep the pooled TLS connection to the Cloudflare edge (or
                # the direct provider host) warm across sporadic requests.
                # httpx's default idle expiry is 5 s, so any gap > 5 s between
                # LLM calls re-pays the ~150-250 ms edge TLS handshake. 90 s
                # survives typical inter-request gaps and stays under the edge's
                # server-side idle close, so the pooled connection is almost
                # always still live on reuse. In the narrow race where the edge
                # closed it first, the reuse raises an httpx transport error
                # (RemoteProtocolError / ConnectError) that ``complete()`` catches
                # via ``except httpx.HTTPError`` and surfaces as a provider error
                # -> the engine falls back (Groq, then deterministic). Fail-soft,
                # never a 500; that one request just pays a fallback instead.
                keepalive_expiry=90.0,
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
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        # R277 — Cloudflare Access service token, when this instance points at
        # the Access-protected host. ``{}`` everywhere else, so every other
        # provider path stays byte-identical. ``getattr`` guards instances
        # built via ``__new__`` (the test suite bypasses ``__init__``); the
        # default fails CLOSED — no token — which is the safe direction for a
        # secret.
        headers.update(getattr(self, "_cf_access_headers", {}) or {})
        return headers

    def complete(self, req: OpenAIWrapperRequest) -> OpenAIWrapperResponse:
        model_name = _resolve_wrapper_model(req.model)

        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": req.system} if req.system else None,
                {"role": "user", "content": req.user},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "stream": False,
        }
        body["messages"] = [m for m in body["messages"] if m is not None]

        # R264 — reasoning_effort for Groq open reasoning models. Explicit
        # request value wins; else auto-inject per model family. NEVER attach
        # to a ``claude-*`` request (not an Anthropic parameter) so the Claude
        # Max wrapper path stays byte-identical.
        _model_lc = (req.model or "").lower()
        if not _model_lc.startswith("claude") and "claude-" not in _model_lc:
            effort = (req.reasoning_effort or "").strip().lower()
            if not effort:
                if "qwen" in _model_lc:
                    effort = "none"
                elif "gpt-oss" in _model_lc:
                    effort = "low"
            if effort and "compound" not in _model_lc:
                body["reasoning_effort"] = effort

        # Per-request timeout override — the intent classifier wants a
        # short 2.5 s budget for its fast-fail behaviour but the
        # Stage-1/2 Sonnet calls need 60 s. Without this knob a single
        # caller setting OPENAI_TIMEOUT_SECONDS via env would poison the
        # singleton for everyone (the bug that killed bench round 29).
        # Issue #48: end-to-end deadline. The caller's `timeout_seconds`
        # is a budget for the WHOLE call (including any 429 backoff),
        # not just one HTTP attempt. Track a wall-clock deadline so a
        # Retry-After sleep can't blow past the caller's budget.
        budget_seconds = (
            float(req.timeout_seconds) if req.timeout_seconds is not None
            else self._timeout
        )
        # R112 — connect-class split: read/write/pool keep the caller's
        # full budget; connect is capped (see _split_connect_timeout).
        request_timeout: httpx.Timeout = _split_connect_timeout(budget_seconds)

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
                    retry_budget = max(
                        0.001, deadline - time.perf_counter()
                    )
                    try:
                        response = self._client.post(
                            "/chat/completions",
                            headers=merged_headers,
                            json=body,
                            timeout=_split_connect_timeout(retry_budget),
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
            msg = choice["message"]
            text = msg.get("content") or ""
            thinking = msg.get("reasoning_content") or ""
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

        # R112 — the wrapper can also relay Claude Code CLI error text as
        # an HTTP 200 "completion" (observed live 2026-06-10: every
        # Stage-2 call returned "There's an issue with the selected model
        # (fable-5). It may not exist or you may not have access to it.
        # Run --model to pick a different model." and the bundle shipped
        # that CLI error as the wire answer on 339/339 bench scenarios).
        # Scan for the known CLI failure shapes and surface them as
        # provider errors so every consumer (Stage-0/1/2, de-noiser,
        # judge) falls back deterministically instead.
        lowered = text.lower() if isinstance(text, str) else ""
        for marker in _WRAPPER_CLI_ERROR_SENTINELS:
            if marker in lowered:
                return OpenAIWrapperResponse(
                    error=f"wrapper_cli_error: {text[:120]}",
                    model=req.model,
                    elapsed_ms=int((time.perf_counter() - start) * 1000),
                )

        usage = payload.get("usage") or {}
        return OpenAIWrapperResponse(
            text=text,
            thinking=thinking,
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

# R289 — the single source of truth for "which Groq model do we call".
#
# This value has now been changed twice by editing NINE separate literals, and
# the first of those swaps took production down:
#
#   8145be2  qwen/qwen3.6-27b -> groq/compound        (broke every Groq path)
#   5869eec  groq/compound    -> openai/gpt-oss-120b  (fixed it)
#
# The 413 is worth recording because the obvious diagnosis was wrong. A
# controlled before/after on the SAME /healthz probe — a ~50-char system prompt
# and a ~55-char user prompt — gave:
#
#   62ca878  {"status": "ok",    "model": "qwen/qwen3.6-27b"}
#   8145be2  {"status": "error", "model": "groq/compound", 413 request_too_large}
#   348ea6a  still 413
#   5869eec  {"status": "ok",    "model": "openai/gpt-oss-120b"}
#
# A ~100-character request cannot exceed a 131,072-token context window, so the
# payload was never the constraint. Groq's docs give the mechanism: "Rate limits
# for groq/compound are determined by the rate limits of the individual models
# that comprise them." compound is an agentic SYSTEM (router + built-in
# web-search/code-exec tools + synthesis model), so ONE external call fans out
# into several internal model calls drawing on the same account budget, and Groq
# reuses 413 / ``request_too_large`` for budget exhaustion. Two tempting wrong
# turns follow from misreading it as a size problem: truncation knobs cannot
# help (the existing 11,000-char truncation would never fire on a 100-char
# probe), and raising max_tokens makes it worse — 8145be2 also took the fallback
# completion cap 1024 -> 4096 on the premise that compound "supports larger
# context", conflating the context window with the completion cap and with the
# rate budget that actually binds.
#
# The default lives here so the next change is one line, not nine, and so it is
# reachable from _engine_cache_key. openai/gpt-oss-120b is the value verified
# live on production at 5869eec.
_GROQ_LIVE_VALIDATED_MODEL = "openai/gpt-oss-120b"


def default_groq_model() -> str:
    """Model id for every Groq call that has no more specific override.

    Read per-call (never at import) so an in-process A/B arm can actually
    change it — see the R263.2 note on ``_engine_cache_key``.
    """
    return (
        os.getenv("REGENOLD_GROQ_DEFAULT_MODEL", "").strip()
        or _GROQ_LIVE_VALIDATED_MODEL
    )


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


# ── Mistral provider (OpenAI-compatible) ─────────────────────────────────────
#
# R-Fusion — Mistral Large is a diverse non-Anthropic panel member for the
# Mixture-of-Agents fusion Stage-2 (see app/engines/fusion.py). Its OpenAI-spec
# Chat Completions endpoint lets the generic ``_OpenAIWrapperProvider`` drive it
# unchanged. Gated on ``MISTRAL_API_KEY``; default endpoint is Mistral's public
# OpenAI-compatible base (override via ``MISTRAL_API_BASE``).

_MISTRAL_DEFAULT_BASE = "https://api.mistral.ai/v1"
_MISTRAL_SINGLETON: _OpenAIWrapperProvider | None = None
_MISTRAL_SINGLETON_LOCK = threading.Lock()


def is_mistral_provider_enabled() -> bool:
    """True iff the Mistral provider is enabled — requires ``MISTRAL_API_KEY``."""
    return bool(os.getenv("MISTRAL_API_KEY", "").strip())


def get_mistral_provider() -> _OpenAIWrapperProvider:
    """Return the process-wide pooled Mistral provider.

    Same double-checked-locking shape as the default singleton. Reads
    ``MISTRAL_API_BASE`` (default ``https://api.mistral.ai/v1``) and
    ``MISTRAL_API_KEY`` at first construction.
    """
    global _MISTRAL_SINGLETON
    if _MISTRAL_SINGLETON is None:
        with _MISTRAL_SINGLETON_LOCK:
            if _MISTRAL_SINGLETON is None:
                _MISTRAL_SINGLETON = _OpenAIWrapperProvider(
                    base_url=(
                        os.getenv("MISTRAL_API_BASE", "").strip()
                        or _MISTRAL_DEFAULT_BASE
                    ),
                    api_key=os.getenv("MISTRAL_API_KEY", ""),
                    timeout=float(os.getenv("MISTRAL_TIMEOUT_SECONDS", "60")),
                )
    return _MISTRAL_SINGLETON


def _reset_mistral_singleton_for_tests() -> None:
    """Reset the Mistral singleton. Test-only — not part of the public API."""
    global _MISTRAL_SINGLETON
    with _MISTRAL_SINGLETON_LOCK:
        if _MISTRAL_SINGLETON is not None:
            try:
                _MISTRAL_SINGLETON._close()  # noqa: SLF001 — test hook
            except Exception:  # noqa: BLE001
                pass
        _MISTRAL_SINGLETON = None

