"""FastAPI app — mounts the Regenold partner endpoint and a /healthz probe.

Stripped-down extract — only the surface needed to exercise
``POST /api/v1/regenold/eu-ai-act/ask`` end-to-end via TestClient or
``uvicorn app.main:app``.
"""
from __future__ import annotations

import logging
import os
import threading as _threading
import time
from typing import Any, Callable, TypeVar

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.llm import resolve_provider
from app.rate_limit import limiter, rate_limit_handler
from app.routes.regenold import regenold_router

logger = logging.getLogger(__name__)

# Wall-clock cap for any blocking call that hits Neo4j on the BOOT path.
# Railway's healthcheck window is 30 s; the neo4j driver's default
# connection timeout is 30 s. A 3 s budget per probe means even if
# every boot-time probe fans out (LLM log, auto-seed metadata, GDS
# probes) we stay well inside the healthcheck budget. The seed thread
# itself is unbounded (it's a daemon that runs in the background) —
# only the synchronous boot calls need the cap.
_BOOT_NEO4J_TIMEOUT_S = 3.0

T = TypeVar("T")


def _run_with_timeout(
    fn: Callable[[], T],
    *,
    timeout_s: float | None = None,
    label: str = "neo4j_boot_probe",
) -> tuple[bool, T | None, str]:
    """Run ``fn`` in a worker thread with a wall-clock cap.

    Returns ``(ok, value_or_none, status)`` where ``status`` is one of:

    * ``"ok"`` — function returned within budget; ``value`` is its return.
    * ``"timeout"`` — wall-clock cap hit; ``value`` is ``None``.
    * ``"error"`` — function raised; ``value`` is ``None`` and the
      exception message is logged at DEBUG.

    When ``timeout_s`` is ``None`` (the default) we resolve the module-
    level :data:`_BOOT_NEO4J_TIMEOUT_S` at call time so test harnesses
    that monkeypatch the constant actually take effect on every probe.

    Uses a bare daemon :class:`threading.Thread` rather than
    :class:`concurrent.futures.ThreadPoolExecutor` because the latter's
    ``shutdown(wait=False)`` still waits for in-progress workers in
    Python 3.9+ — fatal here since the whole point is to abandon a
    hung Neo4j call. With a bare daemon thread, when the parent
    returns the orphan thread keeps running in the background (the
    driver's own I/O timeout will reap it) but the parent's boot
    path is not blocked.
    """
    # Resolve the budget at CALL time, not at function-definition
    # time — a test that monkeypatches ``_BOOT_NEO4J_TIMEOUT_S`` to
    # 0.3 s must take effect on every call.
    budget = timeout_s if timeout_s is not None else _BOOT_NEO4J_TIMEOUT_S

    result: dict[str, Any] = {"value": None, "exc": None}
    done = _threading.Event()

    def _runner() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — must catch SystemExit too
            result["exc"] = exc
        finally:
            done.set()

    worker = _threading.Thread(
        target=_runner, name=label, daemon=True
    )
    worker.start()
    if not done.wait(timeout=budget):
        # The worker is still running; abandon it. It's a daemon so
        # process exit won't wait, and the underlying Neo4j driver
        # has its own connect_timeout that will eventually reap it.
        return False, None, "timeout"
    if result["exc"] is not None:
        logger.debug("%s raised: %s", label, result["exc"])
        return False, None, "error"
    return True, result["value"], "ok"

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
    #
    # Every Neo4j call below is wrapped in ``_run_with_timeout`` so an
    # unreachable graph (driver default connection_timeout is 30 s)
    # cannot stall uvicorn boot past Railway's 30 s healthcheck budget.
    # On timeout we emit a single warning and move on — the deterministic
    # KB path keeps serving requests regardless.
    if os.getenv("NEO4J_URI"):
        ok, _gc, status = _run_with_timeout(
            lambda: __import__(
                "app.graph.client", fromlist=["get_graph_client"]
            ).get_graph_client(),
            label="neo4j_boot_get_client",
        )
        if not ok or _gc is None:
            logger.warning(
                "regenold.startup graph probe %s within %.1fs — engine will "
                "use deterministic fallback",
                "timed out" if status == "timeout" else "failed",
                _BOOT_NEO4J_TIMEOUT_S,
            )
        elif _gc.enabled:
            ok_hc, _hc, status_hc = _run_with_timeout(
                lambda c=_gc: c.health_check(),
                label="neo4j_boot_health_check",
            )
            if not ok_hc or _hc is None:
                logger.warning(
                    "regenold.startup graph health_check %s within %.1fs "
                    "— engine will use deterministic fallback",
                    "timed out" if status_hc == "timeout" else "failed",
                    _BOOT_NEO4J_TIMEOUT_S,
                )
            elif _hc.get("status") == "healthy":
                ok_st, _stats, _ = _run_with_timeout(
                    lambda c=_gc: c.get_stats(),
                    label="neo4j_boot_get_stats",
                )
                if not ok_st or _stats is None:
                    logger.warning(
                        "regenold.startup graph_enabled=True stats probe "
                        "timed out or failed within %.1fs",
                        _BOOT_NEO4J_TIMEOUT_S,
                    )
                else:
                    ok_gds, gds_pair, _ = _run_with_timeout(
                        lambda c=_gc: _resolve_gds_status(c),
                        label="neo4j_boot_gds_probe",
                    )
                    if ok_gds and gds_pair is not None:
                        _gds_ok, _proj_ok = gds_pair
                    else:
                        _gds_ok, _proj_ok = False, False
                    logger.info(
                        "regenold.startup graph_enabled=True "
                        "seed_version=%s node_count=%d edge_count=%d "
                        "gds_available=%s gds_projection_exists=%s",
                        _stats.seed_version or "<unset>",
                        _stats.total_nodes,
                        _stats.total_edges,
                        _gds_ok,
                        _proj_ok,
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


# ─── Cold-start pre-warm (R45 Fix 3.1) ───────────────────────────────────
#
# Three lazy index builds fire on the FIRST 3-5 requests after a worker
# boot, costing ~1.2 s of latency that hits paying users:
#
#   * ``_all_sentence_indexes`` in app/engines/sentence_index.py (~457 ms)
#   * ``build_definition_index`` in app/engines/definition_expand.py (~605 ms)
#   * ``embeddings_index.warm_up`` in app/engines/embeddings_index.py (~115 ms)
#
# The pre-warm hook fires all three in a BACKGROUND daemon thread so
# they complete before the first paying request lands. Uvicorn boot is
# never blocked — the thread is fire-and-forget. Critically, every
# helper is wrapped in try/except: an asset-missing path (Windows dev
# without embeddings assets, Linux without the corpus) must log but
# never crash the thread, because the deterministic engine still works
# without these indexes pre-built.

_PREWARM_LOCK = _threading.Lock()
_PREWARM_STARTED = False


def _prewarm_sentence_index() -> None:
    """Force ``_all_sentence_indexes()`` to build by issuing a tiny query.

    Lazy-imports the module so the import cost itself runs inside the
    background thread (the import touches ARTICLE_FULL_TEXT which
    materialises the EUR-Lex prose dict).
    """
    from app.engines.sentence_index import select_answer_sentence
    # A tiny but well-formed query — picks Article 13's sentence index
    # if present, returning None on empty corpus (still triggers the
    # build pass for every article). The return value is discarded.
    select_answer_sentence("Art. 13", "warm")


def _prewarm_definition_index() -> None:
    """Force ``build_definition_index()`` to materialise."""
    from app.engines.definition_expand import build_definition_index
    build_definition_index()


def _prewarm_embeddings_index() -> None:
    """Eagerly load the embeddings assets when available.

    Honours ``is_available()`` — operators without the bundled assets
    (Windows dev, minimal Docker images) get a no-op rather than a
    failed asset-load log line. This is the SHORTEST of the three
    pre-warms (~115 ms cold) so the perf gain is modest, but it keeps
    the first paying query's tail latency from spiking.
    """
    from app.engines.embeddings_index import is_available, warm_up
    if is_available():
        warm_up()


def _run_prewarm_pass() -> dict[str, float | str]:
    """Run all three pre-warm helpers, returning a results dict.

    Each helper is wrapped in try/except so an asset-missing path
    (Windows dev without embeddings assets, Linux without the corpus)
    logs at DEBUG and gets a ``"err: <ExcType>"`` token in the result
    dict rather than crashing the caller.
    """
    results: dict[str, float | str] = {}
    for name, fn in (
        ("sentence_index", _prewarm_sentence_index),
        ("definition_index", _prewarm_definition_index),
        ("embeddings_index", _prewarm_embeddings_index),
    ):
        t0 = time.perf_counter()
        try:
            fn()
            results[name] = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as exc:  # noqa: BLE001 — must not crash caller
            results[name] = f"err: {type(exc).__name__}"
            logger.debug(
                "regenold.prewarm helper=%s failed: %s", name, exc
            )
    return results


def _maybe_prewarm_indexes() -> None:
    """Pre-warm the three lazy index builds before the first request.

    Idempotent — second invocation no-ops via ``_PREWARM_STARTED``.
    Skips entirely under ``REGENOLD_SKIP_STARTUP_LOG=1`` (same kill
    switch the LLM + auto-seed hooks honour, used by tests).

    Mode is controlled by ``REGENOLD_PREWARM_MODE``:

    * ``"sync"`` (default) — blocks startup until all three pre-warms
      complete. Total cost ~1.2 s. Railway / uvicorn boot stays well
      inside the 30 s healthcheck budget AND the very first paying
      request lands on warm indexes. This is the right shape for
      production: the cold-build cost is paid once at boot, not on
      a paying user's request.

    * ``"async"`` — spawns a daemon thread and returns immediately.
      Useful when boot latency matters more than first-request
      latency (e.g. health-check-only deploys). With ``async``,
      requests that land during the ~1.2 s warm-up still pay
      cold-build cost AND fight the warm-up thread for CPU — measured
      to make max-latency WORSE than not pre-warming at all, so
      ``async`` should only be used when you know your traffic
      pattern can absorb the slow first few requests.

    Either way, the structured-event telemetry line
    ``regenold.prewarm_completed`` is emitted at INFO once the work
    finishes, with a per-helper elapsed-ms breakdown.
    """
    global _PREWARM_STARTED

    if os.getenv("REGENOLD_SKIP_STARTUP_LOG") == "1":
        return

    with _PREWARM_LOCK:
        if _PREWARM_STARTED:
            return
        _PREWARM_STARTED = True

    mode = os.getenv("REGENOLD_PREWARM_MODE", "sync").strip().lower()

    if mode == "async":
        def _worker() -> None:
            thread_started = time.perf_counter()
            results = _run_prewarm_pass()
            total_ms = round(
                (time.perf_counter() - thread_started) * 1000, 1
            )
            logger.info(
                "regenold.prewarm_completed mode=async total_ms=%s "
                "breakdown=%s",
                total_ms,
                results,
            )

        _threading.Thread(
            target=_worker,
            name="regenold-prewarm",
            daemon=True,
        ).start()
        return

    # Sync mode (default) — block the startup hook until the
    # pre-warms complete. ~1.2 s extra boot time; first request
    # lands on a warm engine.
    sync_started = time.perf_counter()
    results = _run_prewarm_pass()
    total_ms = round((time.perf_counter() - sync_started) * 1000, 1)
    logger.info(
        "regenold.prewarm_completed mode=sync total_ms=%s breakdown=%s",
        total_ms,
        results,
    )


@app.on_event("startup")
def _startup_prewarm() -> None:
    """FastAPI startup hook — fire the pre-warm thread.

    Runs AFTER ``_log_llm_provider_status`` (registration order) but
    BEFORE ``_maybe_auto_seed_neo4j``. The daemon thread is
    fire-and-forget so the relative order doesn't matter for
    correctness — only for log readability.
    """
    _maybe_prewarm_indexes()


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


# Outcome codes for ``_acquire_postgres_advisory_lock``.
# R45 Fix 3.2: distinguish Postgres-down (operator MUST investigate)
# from lock-held (benign — another worker is seeding).
_PG_LOCK_NOT_APPLICABLE = "not_applicable"  # DATABASE_URL unset / non-pg
_PG_LOCK_DRIVER_MISSING = "driver_missing"  # psycopg not importable
_PG_LOCK_UNREACHABLE = "unreachable"        # connect failed (was silently None)
_PG_LOCK_HELD = "lock_held"                 # benign — another worker
_PG_LOCK_ACQUIRE_ERROR = "acquire_error"    # rare: SQL-side failure


def _acquire_postgres_advisory_lock() -> tuple[object | None, str, str]:
    """Best-effort Postgres advisory lock — returns ``(handle, status, detail)``.

    ``handle`` is non-None only when the lock was acquired (and must be
    released by the caller). ``status`` is one of the ``_PG_LOCK_*``
    constants above so the caller can distinguish the benign "another
    worker is seeding" case from the operationally-significant
    "Postgres is unreachable" case. ``detail`` carries a truncated
    error message (or empty string).

    When ``DATABASE_URL`` points at a real Postgres, we grab a
    session-scoped advisory lock so only ONE uvicorn worker actually
    runs the seed. ``MERGE``-based seeding is idempotent, so even when
    this returns ``not_applicable`` / ``driver_missing`` / ``unreachable``
    the caller may safely fall through to the process-local lock — at
    worst two workers race and burn an extra Cypher round-trip each.

    The advisory lock key is a fixed 64-bit constant — picked once and
    never collides with other Postgres advisory-lock users in the
    database.
    """
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn or not dsn.startswith("postgres"):
        return None, _PG_LOCK_NOT_APPLICABLE, ""

    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        return None, _PG_LOCK_DRIVER_MISSING, "psycopg not installed"

    try:
        # The seeder needs maybe 5-10 s total; a 30 s lock timeout is
        # plenty. Normalise the DSN the same way evidence store does.
        conn_dsn = dsn
        if conn_dsn.startswith("postgresql+psycopg://"):
            conn_dsn = "postgresql://" + conn_dsn[len("postgresql+psycopg://"):]
        # R45 Fix 3.2: tighten connect_timeout from 10 s to 5 s so the
        # boot path doesn't stall on a Postgres outage. The seeder
        # itself is async (daemon thread) so we don't need a long
        # connect window.
        conn = psycopg.connect(conn_dsn, connect_timeout=5)
    except psycopg.OperationalError as exc:
        # Operationally-significant: Postgres is up-but-rejecting or
        # entirely unreachable. Operator needs to see this — logging
        # at DEBUG isn't enough because they'll be chasing an empty
        # Neo4j and a "skip-non-leader" log line that turns out to be
        # a lie.
        return (
            None,
            _PG_LOCK_UNREACHABLE,
            f"{type(exc).__name__}: {exc!s}"[:200],
        )
    except Exception as exc:  # noqa: BLE001
        # Other connect failures (timeout, refused, bad DSN) get the
        # same treatment — they're not a "lock is held by another
        # worker" signal, so report them as unreachable.
        return (
            None,
            _PG_LOCK_UNREACHABLE,
            f"{type(exc).__name__}: {exc!s}"[:200],
        )

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
            return None, _PG_LOCK_HELD, ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("auto-seed advisory-lock acquire failed: %s", exc)
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        return (
            None,
            _PG_LOCK_ACQUIRE_ERROR,
            f"{type(exc).__name__}: {exc!s}"[:200],
        )

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

    return _AdvisoryLockHandle(conn, LOCK_KEY), "acquired", ""


def _run_auto_seed_in_thread(reason: str) -> None:
    """Seed body — runs inside the daemon thread.

    Captures every exception so a misconfigured Neo4j (auth refused,
    schema drift, etc.) never escapes the thread and never affects
    request serving.
    """
    started = time.perf_counter()
    lock_handle, lock_status, lock_detail = _acquire_postgres_advisory_lock()
    # R45 Fix 3.2: distinguish the benign "lock_held" case (another
    # worker is seeding — skip silently) from the operationally-
    # significant "unreachable" case (Postgres is down — operator
    # MUST see this so they can investigate why Neo4j is still empty
    # after a deploy). Driver-missing / not-applicable fall through to
    # the process-local lock since MERGE-based seeding is idempotent.
    if lock_status == _PG_LOCK_HELD:
        logger.info(
            "regenold.startup auto_seed_skipped reason=advisory_lock_held "
            "(another worker is seeding)"
        )
        return
    if lock_status == _PG_LOCK_UNREACHABLE:
        # Don't silently skip — log a warning AND continue with seeding
        # (the process-local lock is still in effect so we don't race
        # ourselves). Operator gets a single clear signal: "Postgres
        # advisory-lock coordination is unavailable; the seed may
        # run more than once across workers, but it WILL run."
        logger.warning(
            "regenold.startup auto_seed_blocked_postgres_unreachable "
            "error=%s — proceeding with process-local lock only "
            "(MERGE is idempotent so duplicate seeds are safe)",
            lock_detail,
        )
    elif lock_status == _PG_LOCK_ACQUIRE_ERROR:
        logger.warning(
            "regenold.startup auto_seed_advisory_lock_acquire_error "
            "error=%s — proceeding with process-local lock only",
            lock_detail,
        )

    try:
        from scripts.seed_neo4j_kb import run_seed

        result = run_seed(dry_run=False, clear=False, verbose=False)
        elapsed = time.perf_counter() - started
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
    # R45 Fix 3.3: the metadata pre-check runs on the boot path BEFORE
    # the daemon seed thread spawns. On an unreachable Neo4j the driver
    # blocks for ~30 s by default, blowing past Railway's healthcheck
    # window. Wall-clock cap at 3 s + assume seed is needed on timeout.
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

        ok_meta, meta_rows, status_meta = _run_with_timeout(
            lambda: client.execute_read(
                "MATCH (m:KBMetadata) "
                "RETURN m.seed_version AS v, m.kb_version AS kv LIMIT 1"
            ),
            label="neo4j_boot_metadata_precheck",
        )
        if not ok_meta:
            # On TIMEOUT, fall through to spawning the seed thread —
            # the seed itself is async so a slow Neo4j won't keep
            # blocking. The thread carries its own error handling.
            logger.warning(
                "regenold.startup auto_seed_check "
                "action=auto-seed-timeout-on-metadata-precheck "
                "status=%s timeout_s=%.1f — proceeding with seed thread; "
                "operator should investigate Neo4j reachability",
                status_meta,
                _BOOT_NEO4J_TIMEOUT_S,
            )
            current_seed = ""
            current_kb = ""
        else:
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

        if not ok_meta:
            # R45 Fix 3.3: precheck timed out — assume seed is needed
            # (a no-op idempotent re-seed is cheaper than skipping when
            # the graph is actually empty).
            reason = (
                f"metadata_precheck_timeout status={status_meta} "
                f"timeout_s={_BOOT_NEO4J_TIMEOUT_S}"
            )
        elif not current_seed:
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


_GDS_PROJECTION_NAME = "eu_ai_act_graph"

# Module-level cache for the GDS-availability probe. We resolve it lazily
# the first time ``/healthz/graph`` (or a consumer module) asks, then
# memoise — operators inevitably hit healthz on a tight loop from uptime
# monitors and we don't want every probe to fire two extra Cypher calls
# against the graph. The cache is invalidated only by a process restart;
# operators who install GDS post-deploy bounce the service to pick it up.
_GDS_AVAILABLE_CACHE: bool | None = None
_GDS_PROJECTION_CACHE: bool | None = None
_GDS_CACHE_LOCK = _threading.Lock()


def _probe_gds_available(client: Any) -> bool:
    """One-shot probe: does the bound Neo4j have the GDS plugin?

    Cypher: ``CALL gds.list() YIELD name RETURN name LIMIT 1``. On a
    Neo4j without GDS, the driver raises ``Unknown function 'gds.list'``
    which ``execute_read`` swallows and returns ``[]`` — equivalent to
    "not available" without exposing the error to the wire. Any other
    failure mode (driver disabled, connection refused, GDS but with a
    permission error) also degrades to ``False``. Never raises.
    """
    try:
        rows = client.execute_read(
            "CALL gds.list() YIELD name RETURN name LIMIT 1"
        )
    except Exception as exc:  # noqa: BLE001 — never raise from probe
        logger.debug("gds_available probe failed: %s", exc)
        return False
    return bool(rows)


def _probe_gds_projection_exists(client: Any) -> bool:
    """One-shot probe: does the ``eu_ai_act_graph`` projection exist?

    Returns ``False`` whenever GDS is missing OR the projection has not
    been created OR the probe fails. Never raises.
    """
    try:
        rows = client.execute_read(
            "CALL gds.graph.exists($name) YIELD exists RETURN exists",
            {"name": _GDS_PROJECTION_NAME},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("gds_projection_exists probe failed: %s", exc)
        return False
    if not rows:
        return False
    return bool(rows[0].get("exists"))


def _resolve_gds_status(client: Any) -> tuple[bool, bool]:
    """Resolve (gds_available, gds_projection_exists), cached.

    The cache is shared between the boot-time log line and the healthz
    handler so they never disagree.
    """
    global _GDS_AVAILABLE_CACHE, _GDS_PROJECTION_CACHE
    with _GDS_CACHE_LOCK:
        if _GDS_AVAILABLE_CACHE is None:
            _GDS_AVAILABLE_CACHE = _probe_gds_available(client)
        gds_ok = _GDS_AVAILABLE_CACHE
        if _GDS_PROJECTION_CACHE is None:
            # Only probe the projection when GDS is present — saves an
            # extra wasted Cypher round-trip on Aura tiers without GDS.
            _GDS_PROJECTION_CACHE = (
                _probe_gds_projection_exists(client) if gds_ok else False
            )
        proj_ok = _GDS_PROJECTION_CACHE
    return gds_ok, proj_ok


def _reset_gds_cache_for_tests() -> None:
    """Drop the GDS cache. Called from the healthz_graph tests so each
    test scenario starts from a known state. Not intended for production.
    """
    global _GDS_AVAILABLE_CACHE, _GDS_PROJECTION_CACHE
    with _GDS_CACHE_LOCK:
        _GDS_AVAILABLE_CACHE = None
        _GDS_PROJECTION_CACHE = None


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

    Two additional GDS-status fields are reported in every path so an
    operator can see at a glance whether the optional Personalized
    PageRank + PathRAG paths can run:

    * ``gds_available`` — ``True`` iff ``CALL gds.list()`` returns at
      least one row. ``False`` on Aura tiers without the plugin.
    * ``gds_projection_exists`` — ``True`` iff the ``eu_ai_act_graph``
      projection is materialised in the catalog. Only set by the seeder
      when GDS is present.

    Both GDS probes are cached at module level — see
    ``_resolve_gds_status`` — so the healthz handler stays fast on a
    tight monitor loop.

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
        "gds_available": False,
        "gds_projection_exists": False,
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

    # ─── GDS status probes (cached at module level) ──────────────────────
    # Both probes are best-effort. ``execute_read`` already swallows
    # driver-level errors and returns ``[]``; the helper layer above
    # converts every error path to ``False``. We honour the module-level
    # cache so a tight uptime-monitor loop doesn't fire two extra Cypher
    # round-trips per probe.
    try:
        gds_ok, projection_ok = _resolve_gds_status(client)
    except Exception as exc:  # noqa: BLE001
        logger.debug("healthz_graph gds_status probe failed: %s", exc)
        gds_ok, projection_ok = False, False

    base["graph_ok"] = True
    base["detail"] = "ok"
    base["seed_version"] = seed_version
    base["node_counts"] = node_counts
    base["edge_counts"] = edge_counts
    base["gds_available"] = gds_ok
    base["gds_projection_exists"] = projection_ok
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
