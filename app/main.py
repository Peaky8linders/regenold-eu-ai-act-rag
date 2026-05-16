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

    # ─── Neo4j boot-time status ────────────────────────────────────────────
    # Mirror the LLM startup log. Operators who set ``NEO4J_URI`` want a
    # single boot-log line confirming the graph is reachable AND seeded,
    # without having to curl ``/healthz/graph`` from inside the cluster.
    # We deliberately keep the failure path quiet (one warning, no traceback)
    # so a misconfigured Neo4j never blocks startup — the engine just falls
    # back to its deterministic KB path.
    if os.getenv("NEO4J_URI"):
        try:
            from app.graph.client import get_graph_client
            _gc = get_graph_client()
            if _gc.enabled:
                _hc = _gc.health_check()
                if _hc.get("status") == "healthy":
                    try:
                        _stats = _gc.get_stats()
                        logger.info(
                            "regenold.startup graph_enabled=True "
                            "seed_version=%s node_count=%d edge_count=%d",
                            _stats.seed_version or "<unset>",
                            _stats.total_nodes,
                            _stats.total_edges,
                        )
                    except Exception as _se:  # noqa: BLE001
                        logger.warning(
                            "regenold.startup graph_enabled=True "
                            "stats_unavailable=%s",
                            _se,
                        )
                else:
                    logger.warning(
                        "regenold.startup graph_enabled=True but health_check "
                        "returned status=%s — engine will use deterministic "
                        "fallback. Hit /healthz/graph for details.",
                        _hc.get("status"),
                    )
            else:
                logger.warning(
                    "regenold.startup NEO4J_URI is set but the graph client "
                    "did not activate (driver missing or connect failed). "
                    "Engine will use deterministic fallback."
                )
        except Exception as _exc:  # noqa: BLE001 — boot log must never block startup
            logger.warning(
                "regenold.startup graph probe failed: %s — engine will use "
                "deterministic fallback",
                _exc,
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
    # failure surface. The openai_wrapper probe is fully live; the
    # anthropic probe uses ``client.models.list()`` which authenticates
    # the API key without burning a billable token; the Mistral probe
    # is shape-only because their models-list endpoint is rate-limited.
    if provider_label == "openai_wrapper":
        if not is_openai_wrapper_enabled():
            base["detail"] = (
                "P2P_GRAPH_RAG_PROVIDER=openai_wrapper but neither "
                "OPENAI_API_BASE nor OPENAI_API_KEY is set"
            )
            return base
        # Probe with the SAME model used for Stage-2 polish (the
        # load-bearing call) — the Haiku-only probe we shipped in
        # round 29 could pass while Sonnet was broken (different rate
        # limit pool, model-scoped auth scopes on some providers,
        # tunnel routing rules, etc.). Operators can still pin a
        # cheaper probe via REGENOLD_HEALTHZ_PROBE_MODEL.
        probe_model = (
            os.getenv("REGENOLD_HEALTHZ_PROBE_MODEL", "").strip()
            or settings.graph_rag.model
            or "claude-sonnet-4-6"
        )
        try:
            prov = get_openai_wrapper_provider()
            response = prov.complete(
                OpenAIWrapperRequest(
                    system="Reply with the exact word OK and nothing else.",
                    user="ping",
                    model=probe_model,
                    max_tokens=8,
                    temperature=0.0,
                    # Cap the probe at 10 s so an uptime monitor doesn't
                    # block forever on a hung wrapper — the singleton's
                    # 60 s default is for real Stage-2 calls.
                    timeout_seconds=10.0,
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
            return base
        try:
            import anthropic
        except ImportError:
            base["detail"] = "anthropic SDK not installed (pip install anthropic)"
            return base
        # Live probe — round-29 shipped a configured-only probe that
        # said llm_ok=True whenever the key was set, even if revoked /
        # malformed / pointed at the wrong tenant. We now call
        # ``models.list()`` which authenticates the key against the
        # Anthropic API but does NOT consume any input/output tokens
        # (it's a metadata endpoint, free per the pricing page). The
        # 10-second timeout caps the probe latency. Operators who want
        # the old "don't touch the network at health-check time"
        # behaviour can set REGENOLD_HEALTHZ_PROBE_ANTHROPIC=0.
        if os.getenv("REGENOLD_HEALTHZ_PROBE_ANTHROPIC", "1").strip() == "0":
            base["llm_ok"] = True
            base["detail"] = (
                "anthropic SDK installed + API key configured "
                "(REGENOLD_HEALTHZ_PROBE_ANTHROPIC=0, not probed live)"
            )
            return base
        import time as _time
        start = _time.perf_counter()
        try:
            client = anthropic.Anthropic(
                api_key=api_key.get_secret_value(),
                timeout=10.0,
            )
            client.models.list(limit=1)
        except Exception as exc:  # noqa: BLE001 — health probe must never raise
            # Anthropic raises typed exceptions (AuthenticationError,
            # APIConnectionError, etc.) but we don't want to depend on
            # the SDK's class hierarchy in main.py — the string is
            # enough for an operator to diagnose.
            base["detail"] = (
                f"anthropic_probe_failed: {type(exc).__name__}: {exc!s}"
            )[:200]
            base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
            return base
        base["llm_ok"] = True
        base["detail"] = "ok"
        base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
        base["model"] = settings.graph_rag.model
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


@app.get("/healthz/graph")
def healthz_graph() -> dict[str, object]:
    """Probe Neo4j connectivity + KB seed status.

    Returns HTTP 200 always — uptime monitors should alert on
    ``graph_ok=False`` (not on HTTP status), so a downed graph doesn't
    flap the uptime page when the engine's deterministic fallback is
    still serving requests fine.

    Three paths:

    * **disabled** — ``NEO4J_URI`` is unset, or the ``neo4j`` driver is
      not importable. Returns ``graph_enabled=False`` with a clear hint.
    * **unhealthy** — driver imports + connects but ``RETURN 1 AS ping``
      fails. Returns ``graph_ok=False`` with a truncated error.
    * **healthy** — full status: ping, seed_version, kb_version,
      per-label node counts, edge-type counts, total elapsed_ms.

    The probe runs read-only Cypher only. It never writes. All read
    queries inherit the driver's ``connection_timeout`` (5 s by default,
    see :class:`app.graph.config.GraphSettings`).
    """
    import time as _time

    from app.data.kb import KB_VERSION
    from app.graph.client import _STATS_LABELS, get_graph_client

    base: dict[str, object] = {
        "version": settings.version,
        "graph_enabled": False,
        "graph_ok": False,
        "detail": "",
        "elapsed_ms": 0,
        "seed_version": "",
        "kb_version": KB_VERSION,
        "node_counts": {},
        "edge_counts": {},
    }

    # ─── Disabled path ────────────────────────────────────────────────────
    if not os.environ.get("NEO4J_URI"):
        base["detail"] = "NEO4J_URI not set"
        return base

    start = _time.perf_counter()
    try:
        client = get_graph_client()
    except Exception as exc:  # noqa: BLE001 — health probe must never raise
        base["detail"] = f"graph_client_init_failed: {exc!s}"[:200]
        base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
        return base

    if not client.enabled:
        # NEO4J_URI was set but the client didn't activate (driver missing
        # or connection refused at __init__ time).
        base["detail"] = (
            "graph_disabled: NEO4J_URI is set but the neo4j driver is not "
            "installed or the connection was refused at init. Install with "
            "`pip install neo4j>=5.0` and verify the URI."
        )
        base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
        return base

    base["graph_enabled"] = True

    # ─── Unhealthy path — ping fails ──────────────────────────────────────
    try:
        hc = client.health_check()
    except Exception as exc:  # noqa: BLE001 — health probe must never raise
        base["detail"] = f"health_check_exception: {exc!s}"[:200]
        base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
        return base

    status = hc.get("status")
    if status != "healthy":
        err = hc.get("error") or hc.get("message") or "unknown"
        base["detail"] = f"unhealthy: {err}"[:200]
        base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
        return base

    # ─── Healthy path — collect seed info + counts ────────────────────────
    # Each individual Cypher is wrapped: a single label-count failure must
    # not break the overall probe. ``client.execute_read`` already swallows
    # driver-level errors and returns ``[]``.
    seed_version = ""
    try:
        meta = client.execute_read(
            "MATCH (m:KBMetadata) "
            "RETURN m.seed_version AS seed_version, m.kb_version AS kb_version "
            "LIMIT 1"
        )
        if meta:
            row = meta[0]
            seed_version = row.get("seed_version") or ""
            # Prefer the seed's recorded kb_version when present; falls back
            # to the in-process KB_VERSION (the seed and the code can drift
            # — that's exactly the kind of state an operator wants visible).
            kb_v = row.get("kb_version")
            if kb_v:
                base["kb_version"] = kb_v
    except Exception as exc:  # noqa: BLE001
        logger.debug("healthz_graph seed_version probe failed: %s", exc)

    node_counts: dict[str, int] = {}
    for label in _STATS_LABELS:
        try:
            rows = client.execute_read(
                f"MATCH (n:{label}) RETURN count(n) AS cnt"
            )
            if rows:
                cnt = int(rows[0].get("cnt") or 0)
                if cnt > 0:
                    # Skip empty labels — keeps the response readable.
                    node_counts[label] = cnt
        except Exception as exc:  # noqa: BLE001
            logger.debug("healthz_graph label=%s count failed: %s", label, exc)

    edge_counts: dict[str, int] = {}
    try:
        edge_rows = client.execute_read(
            "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt"
        )
        for row in edge_rows:
            rt = row.get("rel_type")
            cnt = int(row.get("cnt") or 0)
            if rt and cnt > 0:
                edge_counts[rt] = cnt
    except Exception as exc:  # noqa: BLE001
        logger.debug("healthz_graph edge count probe failed: %s", exc)

    base["graph_ok"] = True
    base["detail"] = "ok"
    base["seed_version"] = seed_version
    base["node_counts"] = node_counts
    base["edge_counts"] = edge_counts
    base["elapsed_ms"] = int((_time.perf_counter() - start) * 1000)
    return base


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "regenold-eu-ai-act-rag",
        "version": settings.version,
        "docs": "/docs",
        "ask_endpoint": "/api/v1/regenold/eu-ai-act/ask",
    }
