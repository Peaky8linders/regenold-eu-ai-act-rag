"""FastAPI app — mounts the Regenold partner endpoint and a /healthz probe.

Stripped-down extract — only the surface needed to exercise
``POST /api/v1/regenold/eu-ai-act/ask`` end-to-end via TestClient or
``uvicorn app.main:app``.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.llm import resolve_provider
from app.rate_limit import limiter, rate_limit_handler
from app.routes.regenold import regenold_router

logger = logging.getLogger(__name__)

# Fail-loud at module-import on a typo in P2P_GRAPH_RAG_PROVIDER. Without
# this, a typo like "mistraal" silently degrades every request to the
# deterministic-fallback path with no operator-visible signal — the eval
# snapshot would "complete normally" but every scenario took the non-LLM
# path. Boot-time validation surfaces the typo before any traffic hits.
try:
    resolve_provider(
        os.getenv("P2P_GRAPH_RAG_PROVIDER"),
        default_when_auto="anthropic",
    )
except ValueError as _exc:
    raise RuntimeError(
        f"P2P_GRAPH_RAG_PROVIDER is misconfigured: {_exc}. "
        "Valid values: mistral / anthropic / cli / openai_wrapper / auto / "
        "(unset = auto). See app/llm/__init__.py::resolve_provider."
    ) from _exc


app = FastAPI(
    title="Regenold EU AI Act RAG",
    version=settings.version,
    description=(
        "Standalone bundle extracted from CodexAI / legit-ai for partner "
        "transparency review. Exposes the same Regenold grounded Q&A "
        "surface as the parent repo."
    ),
)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)


api_v1 = FastAPI(
    title="Regenold EU AI Act RAG — API v1",
    version=settings.version,
)
api_v1.state.limiter = limiter
api_v1.add_exception_handler(RateLimitExceeded, rate_limit_handler)
api_v1.add_middleware(SlowAPIMiddleware)
api_v1.include_router(regenold_router)


app.mount("/api/v1", api_v1)


@app.on_event("startup")
def _log_llm_provider_status() -> None:
    """Log the resolved LLM provider once at boot.

    Operator-visible signal that the wrapper / Mistral / Anthropic
    knobs took effect. We deliberately do NOT probe the wrapper live
    here — a long boot-time probe (the Claude CLI subprocess takes
    several seconds to spin up) would block uvicorn's startup and
    delay the first /healthz return. Operators who need a live probe
    hit /healthz/llm instead. Skip when REGENOLD_SKIP_STARTUP_LOG=1
    (test harness uses this to keep TestClient output clean).
    """
    if os.getenv("REGENOLD_SKIP_STARTUP_LOG") == "1":
        return
    provider_label = resolve_provider(
        os.getenv("P2P_GRAPH_RAG_PROVIDER"),
        default_when_auto="anthropic",
    )
    if provider_label == "openai_wrapper":
        base = (
            os.getenv("OPENAI_API_BASE", "").strip()
            or "http://127.0.0.1:8000/v1"
        )
        logger.info(
            "regenold.startup provider=openai_wrapper endpoint=%s "
            "intent_model=%s graph_rag_model=%s — hit /healthz/llm for a "
            "live probe",
            base,
            os.getenv("REGENOLD_INTENT_MODEL", "claude-haiku-4-5-20251001"),
            settings.graph_rag.model,
        )
    elif provider_label == "anthropic":
        configured = settings.graph_rag.api_key is not None
        logger.info(
            "regenold.startup provider=anthropic api_key_configured=%s model=%s",
            configured,
            settings.graph_rag.model,
        )
    elif provider_label == "mistral":
        logger.info(
            "regenold.startup provider=mistral api_key_configured=%s",
            bool(os.getenv("MISTRAL_API_KEY")),
        )
    else:
        logger.info(
            "regenold.startup provider=%s (deterministic path; no LLM calls)",
            provider_label,
        )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": settings.version}


@app.get("/healthz/llm")
def healthz_llm() -> dict[str, object]:
    """Live LLM-path probe — verifies the configured provider can actually answer.

    Without this, an operator who sets ``P2P_GRAPH_RAG_PROVIDER=openai_wrapper``
    has no way to know whether the wrapper is up + logged-in + actually
    returning tokens, vs. silently falling back to deterministic on every
    request. This endpoint fires a single ~5-token "reply OK" probe against
    the configured provider and returns the structured result.

    Always returns HTTP 200 (so an uptime monitor on /healthz/llm doesn't
    flap when the wrapper is down). The shape includes a ``llm_ok`` bool —
    consumers can alert on that instead.
    """
    from app.llm.openai_wrapper_provider import (
        OpenAIWrapperRequest,
        get_openai_wrapper_provider,
        is_openai_wrapper_enabled,
    )

    provider_label = resolve_provider(
        os.getenv("P2P_GRAPH_RAG_PROVIDER"),
        default_when_auto="anthropic",
    )

    base: dict[str, object] = {
        "version": settings.version,
        "provider": provider_label,
        "llm_ok": False,
        "detail": "",
    }

    # The probe is provider-specific because each path has its own
    # failure surface. We only implement the openai_wrapper probe live —
    # the other paths (anthropic SDK direct / Mistral) are pay-per-token
    # so we don't burn a request on every health check; for those we
    # only report "configured / not configured".
    if provider_label == "openai_wrapper":
        if not is_openai_wrapper_enabled():
            base["detail"] = (
                "P2P_GRAPH_RAG_PROVIDER=openai_wrapper but neither "
                "OPENAI_API_BASE nor OPENAI_API_KEY is set"
            )
            return base
        try:
            prov = get_openai_wrapper_provider()
            response = prov.complete(
                OpenAIWrapperRequest(
                    system="Reply with the exact word OK and nothing else.",
                    user="ping",
                    model=os.getenv(
                        "REGENOLD_INTENT_MODEL",
                        "claude-haiku-4-5-20251001",
                    ),
                    max_tokens=8,
                    temperature=0.0,
                )
            )
        except Exception as exc:  # noqa: BLE001 — health probe must never raise
            base["detail"] = f"probe_exception: {exc!s}"[:200]
            return base
        if response.error:
            base["detail"] = response.error[:200]
            base["elapsed_ms"] = response.elapsed_ms
            return base
        base["llm_ok"] = bool((response.text or "").strip())
        base["detail"] = "ok" if base["llm_ok"] else "empty_response"
        base["elapsed_ms"] = response.elapsed_ms
        base["model"] = response.model
        base["prompt_tokens"] = response.prompt_tokens
        base["completion_tokens"] = response.completion_tokens
        return base

    if provider_label == "anthropic":
        api_key = settings.graph_rag.api_key
        if not api_key:
            base["detail"] = "P2P_GRAPH_RAG_API_KEY not set"
        else:
            try:
                import anthropic  # noqa: F401
                base["llm_ok"] = True
                base["detail"] = "anthropic SDK installed + API key configured (not probed live)"
            except ImportError:
                base["detail"] = "anthropic SDK not installed (pip install anthropic)"
        return base

    if provider_label == "mistral":
        from app.llm import is_mistral_enabled
        if is_mistral_enabled():
            base["llm_ok"] = True
            base["detail"] = "MISTRAL_API_KEY set (not probed live)"
        else:
            base["detail"] = "MISTRAL_API_KEY not set"
        return base

    # cli / deterministic path
    base["llm_ok"] = True
    base["detail"] = "deterministic-only path — no LLM call required"
    return base


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "regenold-eu-ai-act-rag",
        "version": settings.version,
        "docs": "/docs",
        "ask_endpoint": "/api/v1/regenold/eu-ai-act/ask",
    }
