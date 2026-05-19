"""FastAPI app — mounts the Regenold partner endpoint and a /healthz probe.

Stripped-down extract — only the surface needed to exercise
``POST /api/v1/regenold/eu-ai-act/ask`` end-to-end via TestClient or
``uvicorn app.main:app``.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.llm import resolve_provider
from app.rate_limit import limiter, rate_limit_handler
from app.routes.regenold import regenold_router

logger = logging.getLogger(__name__)

# Fail-loud at module-import on a typo in P2P_GRAPH_RAG_PROVIDER. Without
# this, a typo like "anthropc" silently degrades every request to the
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
        "Valid values: anthropic / cli / openai_wrapper / auto / "
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

    Operator-visible signal that the wrapper / Anthropic knobs took
    effect. We deliberately do NOT probe the wrapper live
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


# ─── Auto-seed on startup ────────────────────────────────────────────────
#
# When ``NEO4J_URI`` is set AND ``NEO4J_AUTO_SEED`` is not explicitly
# disabled, the boot path checks ``KBMetadata.seed_version`` against the
# in-process ``SEED_VERSION`` and fires the seeder in a daemon thread
# when they differ (or the graph is empty). The thread is fire-and-forget
# — uvicorn's startup never blocks on graph I/O. Multi-worker safety is
# handled by a process-local lock plus an opt-in Postgres advisory lock
# (when ``DATABASE_URL`` is set, only ONE worker actually performs the
# write; the others observe the seeded graph on their next health probe).

import threading as _threading

# Module-level guard so even within a single process two startup hooks
# can't both fire the seeder. ``daemon=True`` is critical — uvicorn
# exits cleanly even if the seed thread is mid-write.
_AUTO_SEED_LOCK = _threading.Lock()
_AUTO_SEED_STARTED = False


def _auto_seed_disabled_by_env() -> bool:
    """Return True when ``NEO4J_AUTO_SEED`` is explicitly off.

    Default is ON when ``NEO4J_URI`` is set — operators have to opt OUT
    rather than opt in (matches the user's expectation that "set the URI,
    get a seeded graph"). The off-toggle accepts the usual truthy /
    falsy spellings: ``0`` / ``false`` / ``no`` / ``off`` (any case).
    """
    raw = os.getenv("NEO4J_AUTO_SEED")
    if raw is None:
        return False
    # R39 eng-review F4: empty string is NOT a disable signal —
    # Railway / Docker `--env-file` overrides sometimes pass a blank
    # value and the user expects the default (ON) to kick in.
    return raw.strip().lower() in {"0", "false", "no", "off"}


def _acquire_postgres_advisory_lock() -> object | None:
    """Best-effort Postgres advisory lock — returns a context handle or None.

    When ``DATABASE_URL`` points at a real Postgres, we grab a
    session-scoped advisory lock so only ONE uvicorn worker actually
    runs the seed. The lock is released when the returned handle's
    ``release()`` is called (or when the connection closes).

    Returns ``None`` when:

    * ``DATABASE_URL`` is unset / non-Postgres (sqlite://, in-memory).
    * The ``psycopg`` driver is not importable.
    * The lock could not be acquired (another worker holds it — that's
      the GOOD path; the caller should skip seeding).
    * Any other error — we fall back to the process-local
      ``_AUTO_SEED_LOCK``, which is enough because ``MERGE``-based
      seeding is idempotent.

    The advisory lock key is a fixed 64-bit constant derived from
    ``"regenold_neo4j_auto_seed"`` — picked once and never collides
    with other Postgres advisory-lock users in the database.
    """
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn or not dsn.startswith("postgres"):
        return None

    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        # The seeder needs maybe 5-10 s total; a 30 s lock timeout is
        # plenty. Normalise the DSN the same way evidence store does.
        conn_dsn = dsn
        if conn_dsn.startswith("postgresql+psycopg://"):
            conn_dsn = "postgresql://" + conn_dsn[len("postgresql+psycopg://"):]
        conn = psycopg.connect(conn_dsn, connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.debug("auto-seed advisory-lock connect failed: %s", exc)
        return None

    # Fixed 64-bit advisory lock key. Hand-picked so it's deterministic
    # and stable across deploys; pg_try_advisory_lock returns False
    # when another session already holds the lock.
    LOCK_KEY = 7340518364729403841  # arbitrary, fixed
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
            row = cur.fetchone()
            acquired = bool(row and row[0])
        if not acquired:
            conn.close()
            return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("auto-seed advisory-lock acquire failed: %s", exc)
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        return None

    class _AdvisoryLockHandle:
        """Releases the lock + closes the connection."""

        def __init__(self, _conn: Any, _key: int) -> None:
            self._conn = _conn
            self._key = _key
            self._released = False

        def release(self) -> None:
            if self._released:
                return
            self._released = True
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (self._key,))
            except Exception as exc:  # noqa: BLE001
                logger.debug("auto-seed advisory-unlock failed: %s", exc)
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass

    return _AdvisoryLockHandle(conn, LOCK_KEY)


def _run_auto_seed_in_thread(reason: str) -> None:
    """Seed body — runs inside the daemon thread.

    Captures every exception so a misconfigured Neo4j (auth refused,
    schema drift, etc.) never escapes the thread and never affects
    request serving.
    """
    import time as _time

    started = _time.perf_counter()
    lock_handle = _acquire_postgres_advisory_lock()
    # If DATABASE_URL was set + we couldn't acquire the lock, another
    # worker is seeding. Skip + log. If DATABASE_URL was unset or the
    # driver is missing, ``lock_handle`` is None and we fall back to the
    # process-local lock — that's fine because MERGE is idempotent so
    # two workers racing is benign (just wasteful).
    if (
        lock_handle is None
        and os.getenv("DATABASE_URL", "").strip().startswith("postgres")
    ):
        logger.info(
            "regenold.startup auto_seed_skipped reason=advisory_lock_held "
            "(another worker is seeding)"
        )
        return

    try:
        from scripts.seed_neo4j_kb import run_seed

        result = run_seed(dry_run=False, clear=False, verbose=False)
        elapsed = _time.perf_counter() - started
        if result.get("status") == "ok":
            logger.info(
                "regenold.startup auto_seed_completed reason=%s nodes=%d "
                "edges=%d seed_version=%s elapsed_s=%.2f",
                reason,
                result.get("total_nodes", 0),
                result.get("total_edges", 0),
                result.get("seed_version", "<unset>"),
                elapsed,
            )
        else:
            logger.warning(
                "regenold.startup auto_seed_failed reason=%s status=%s "
                "elapsed_s=%.2f",
                reason,
                result.get("status"),
                elapsed,
            )
    except Exception as exc:  # noqa: BLE001 — best-effort, must never crash uvicorn
        logger.warning(
            "regenold.startup auto_seed_exception reason=%s err=%s — engine "
            "will use deterministic fallback",
            reason,
            exc,
        )
    finally:
        if lock_handle is not None:
            try:
                lock_handle.release()
            except Exception:  # noqa: BLE001
                pass


@app.on_event("startup")
def _maybe_auto_seed_neo4j() -> None:
    """Optionally seed Neo4j on boot — non-blocking, env-gated.

    Runs after :func:`_log_llm_provider_status` (registration order).
    Decision tree:

    1. No ``NEO4J_URI`` → log ``action=disabled-no-uri`` and return.
    2. ``NEO4J_AUTO_SEED=0/false/no/off`` → log ``action=disabled-by-env``.
    3. ``REGENOLD_AUTO_SEED_LEADER_ONLY=1`` (default) AND uvicorn passes
       a worker index env var > 0 → log ``action=skip-non-leader``.
    4. ``GraphClient`` disabled → log ``action=skip-graph-disabled``.
    5. Query ``KBMetadata``. If a row exists with matching
       ``seed_version``, log ``action=skip-current``.
    6. Otherwise → fire daemon thread to seed; log ``action=seed-started``.

    Skip entirely when ``REGENOLD_SKIP_STARTUP_LOG=1`` — tests use this
    to keep TestClient output clean (and to avoid spinning up the seeder
    background thread during fixture-heavy test runs).
    """
    global _AUTO_SEED_STARTED

    if os.getenv("REGENOLD_SKIP_STARTUP_LOG") == "1":
        return

    if not os.environ.get("NEO4J_URI"):
        logger.info(
            "regenold.startup auto_seed_check action=disabled-no-uri"
        )
        return

    if _auto_seed_disabled_by_env():
        logger.info(
            "regenold.startup auto_seed_check action=disabled-by-env "
            "NEO4J_AUTO_SEED=%s",
            os.getenv("NEO4J_AUTO_SEED", ""),
        )
        return

    # ── Leader-only gate ─────────────────────────────────────────────────
    # When uvicorn is launched with ``--workers N`` it forks N child
    # processes; each one runs the startup hook independently. Without
    # coordination, every worker would try to seed in parallel — wasteful
    # but ultimately safe (MERGE is idempotent). We still try to filter
    # down to the leader using whichever signal is available:
    #
    #   * Uvicorn doesn't expose worker index by default. Operators who
    #     want strict leader-only can set REGENOLD_WORKER_INDEX=0 on
    #     worker 0 and a non-zero value on the rest via gunicorn's
    #     post_fork hook.
    #
    # If the index is unset (the default), the Postgres advisory lock
    # acquired inside ``_run_auto_seed_in_thread`` handles the race.
    if os.getenv("REGENOLD_AUTO_SEED_LEADER_ONLY", "1").strip() == "1":
        worker_idx = os.getenv("REGENOLD_WORKER_INDEX", "").strip()
        if worker_idx and worker_idx != "0":
            logger.info(
                "regenold.startup auto_seed_check action=skip-non-leader "
                "worker_idx=%s",
                worker_idx,
            )
            return

    # ── Decide: seed or skip based on KBMetadata ────────────────────────
    try:
        from app.data.kb import KB_VERSION
        from app.graph.client import get_graph_client
        from scripts.seed_neo4j_kb import SEED_VERSION

        client = get_graph_client()
        if not client.enabled:
            logger.info(
                "regenold.startup auto_seed_check action=skip-graph-disabled "
                "(NEO4J_URI set but driver/connection unavailable)"
            )
            return

        meta_rows = client.execute_read(
            "MATCH (m:KBMetadata) "
            "RETURN m.seed_version AS v, m.kb_version AS kv LIMIT 1"
        )
        current_seed = (meta_rows[0].get("v") if meta_rows else "") or ""
        current_kb = (meta_rows[0].get("kv") if meta_rows else "") or ""

        if (
            current_seed == SEED_VERSION
            and current_kb == KB_VERSION
        ):
            logger.info(
                "regenold.startup neo4j_seed_current "
                "auto_seed_check action=skip-current seed_version=%s "
                "kb_version=%s",
                current_seed,
                current_kb,
            )
            return

        # Mark started under the process-local lock so two competing
        # startup hooks (rare — testharness reloads, dev reloads) don't
        # both spawn threads.
        with _AUTO_SEED_LOCK:
            if _AUTO_SEED_STARTED:
                logger.info(
                    "regenold.startup auto_seed_check "
                    "action=skip-already-started"
                )
                return
            _AUTO_SEED_STARTED = True

        if not current_seed:
            reason = "graph_empty"
        else:
            reason = (
                f"seed_drift current_seed={current_seed} "
                f"want_seed={SEED_VERSION} current_kb={current_kb} "
                f"want_kb={KB_VERSION}"
            )

        logger.info(
            "regenold.startup auto_seed_check action=seed-started "
            "reason=%s",
            reason,
        )
        thread = _threading.Thread(
            target=_run_auto_seed_in_thread,
            args=(reason,),
            name="regenold-auto-seed",
            daemon=True,
        )
        thread.start()
    except Exception as exc:  # noqa: BLE001 — boot must never block on this
        logger.warning(
            "regenold.startup auto_seed_check action=error err=%s — engine "
            "will use deterministic fallback",
            exc,
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
    # the API key without burning a billable token.
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

    # R63-F / R64 — only count labels that actually exist in the graph.
    # ``client.existing_labels`` probes ``db.labels()`` once and
    # intersects with the allowlist; on probe failure it falls back to a
    # SAFE subset (Article / Obligation / KBMetadata / RiskLevel /
    # AnnexIIICategory — all guaranteed by ``scripts/seed_neo4j_kb.py``)
    # so the f-string ``MATCH (n:LABEL)`` queries below never hit a
    # missing label and re-introduce the R63-F warning storm for the 5
    # orphan parent-CodexAI labels (Dimension / Question / RoadmapTask /
    # NISTSubcategory / ISOClause).
    existing_labels = client.existing_labels(_STATS_LABELS)

    node_counts: dict[str, int] = {}
    for label in sorted(existing_labels):
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
