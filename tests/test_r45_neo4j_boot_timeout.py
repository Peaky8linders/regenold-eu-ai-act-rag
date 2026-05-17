"""Tests for the R45 Fix 3.3 + 3.4 boot-path Neo4j timeout guard.

The boot path runs several synchronous Neo4j calls BEFORE the daemon
seed thread spawns:

* ``app.main._log_llm_provider_status`` issues 3+ blocking probes
  (get_graph_client / health_check / get_stats / GDS probes).
* ``app.main._maybe_auto_seed_neo4j`` runs a ``KBMetadata`` precheck
  before deciding whether to fire the seed thread.

On an unreachable Neo4j the driver's default ``connection_timeout`` is
~30 s. Without a wall-clock cap, uvicorn boot can stall past Railway's
30 s healthcheck window and the container gets killed before it can
serve a single request.

R45 Fix 3.3 wraps every boot-time Neo4j call in
:func:`app.main._run_with_timeout` with a 3 s budget. On timeout:

* ``_log_llm_provider_status`` emits ONE warning and continues (the
  startup log line is unavailable but the engine still serves).
* ``_maybe_auto_seed_neo4j`` assumes seed is needed and fires the
  daemon seed thread anyway (idempotent — re-seeding a current graph
  is a no-op MERGE pass; missing-seed-on-empty-graph would be worse).

Tests use a ``_BlockingClient`` stand-in whose ``execute_read`` /
``health_check`` block on a ``threading.Event`` so we can reproduce
the unreachable-driver pattern deterministically.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────


class _BlockingClient:
    """Simulates a Neo4j client whose every call blocks forever.

    Used to verify the boot-path timeout wrappers actually fire when
    the underlying driver hangs.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        block_event: threading.Event | None = None,
        block_timeout: float = 30.0,
    ) -> None:
        self.enabled = enabled
        # ``block_event`` is never set in these tests — the helpers
        # all wait on it up to ``block_timeout`` seconds (simulating
        # the neo4j driver's default ~30 s connection_timeout).
        self._event = block_event or threading.Event()
        self._block_timeout = block_timeout
        self.execute_read_calls: list[str] = []
        self.health_check_called = 0
        self.get_stats_called = 0

    def execute_read(self, query: str, parameters: Any = None) -> list[dict]:
        self.execute_read_calls.append(query)
        self._event.wait(timeout=self._block_timeout)
        return []

    def health_check(self) -> dict:
        self.health_check_called += 1
        self._event.wait(timeout=self._block_timeout)
        return {"status": "unhealthy", "error": "blocked"}

    def get_stats(self) -> Any:
        self.get_stats_called += 1
        self._event.wait(timeout=self._block_timeout)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch):
    """Fresh ``_AUTO_SEED_STARTED`` between tests."""
    import app.main as _main
    _main._AUTO_SEED_STARTED = False
    _main._PREWARM_STARTED = False
    # Drop GDS cache so the LLM startup log probe doesn't short-circuit.
    _main._reset_gds_cache_for_tests()
    for k in (
        "NEO4J_URI",
        "NEO4J_AUTO_SEED",
        "REGENOLD_AUTO_SEED_LEADER_ONLY",
        "REGENOLD_WORKER_INDEX",
        "REGENOLD_SKIP_STARTUP_LOG",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    yield
    _main._AUTO_SEED_STARTED = False
    _main._PREWARM_STARTED = False


def _wait_for_thread(name: str, timeout: float = 8.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        alive = any(
            t.is_alive() and t.name == name
            for t in threading.enumerate()
        )
        if not alive:
            return
        time.sleep(0.01)


# ─── _run_with_timeout core ─────────────────────────────────────────────


class TestRunWithTimeout:
    """The helper itself must honour the wall-clock cap."""

    def test_fast_call_returns_ok(self) -> None:
        from app.main import _run_with_timeout

        ok, value, status = _run_with_timeout(lambda: 42)
        assert ok is True
        assert value == 42
        assert status == "ok"

    def test_slow_call_times_out_within_budget(self) -> None:
        from app.main import _run_with_timeout

        def _slow() -> int:
            time.sleep(5.0)
            return 1

        start = time.perf_counter()
        ok, value, status = _run_with_timeout(_slow, timeout_s=0.5)
        elapsed = time.perf_counter() - start
        assert ok is False
        assert value is None
        assert status == "timeout"
        # Must respect the budget — give a generous margin for thread
        # scheduling but enforce that we did NOT wait 5 seconds.
        assert elapsed < 2.0, (
            f"timeout took {elapsed:.2f}s — expected <2.0s with 0.5s budget"
        )

    def test_raising_call_reports_error(self) -> None:
        from app.main import _run_with_timeout

        ok, value, status = _run_with_timeout(
            lambda: (_ for _ in ()).throw(ValueError("boom"))
        )
        assert ok is False
        assert value is None
        assert status == "error"


# ─── Auto-seed boot-path timeout ────────────────────────────────────────


class TestAutoSeedBootTimeout:
    """``_maybe_auto_seed_neo4j`` must not stall uvicorn boot."""

    def test_metadata_precheck_timeout_proceeds_with_seed_thread(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """An unreachable Neo4j must trigger the timeout branch.

        Contract: the precheck times out within ``_BOOT_NEO4J_TIMEOUT_S``,
        a warning is emitted, and the seed thread is spawned anyway
        (idempotent — a re-seed of a current graph is a no-op MERGE
        pass; missing-seed-on-empty-graph would be worse).
        """
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        # Force a tighter budget so the test runs fast.
        monkeypatch.setattr(_main, "_BOOT_NEO4J_TIMEOUT_S", 0.3)

        fake = _BlockingClient(enabled=True, block_timeout=10.0)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        run_seed_mock = MagicMock(
            return_value={
                "status": "ok",
                "total_nodes": 505,
                "total_edges": 351,
                "seed_version": "test",
                "kb_version": "test",
                "counts": {},
            }
        )
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", run_seed_mock
        )

        # Capture both INFO + WARNING so we see the
        # ``action=seed-started`` line too (it's logged at INFO).
        caplog.set_level(logging.INFO, logger=_main.__name__)
        start = time.perf_counter()
        _main._maybe_auto_seed_neo4j()
        boot_elapsed = time.perf_counter() - start

        # Boot path itself MUST return within ~3x the budget — even
        # under heavy scheduling noise this should hold. The seed
        # thread (slow) runs in the background.
        assert boot_elapsed < 1.5, (
            f"boot path took {boot_elapsed:.2f}s — expected <1.5s with "
            "0.3s timeout"
        )

        # Operator-visible signal: the timeout-on-metadata-precheck
        # log line is the *primary* observability surface here.
        assert "auto-seed-timeout-on-metadata-precheck" in caplog.text
        # The seed thread was spawned (proceed-with-seed semantics).
        assert "action=seed-started" in caplog.text
        assert "metadata_precheck_timeout" in caplog.text

        # Clean up — wait for the seed thread to finish so it
        # doesn't bleed into other tests.
        _wait_for_thread("regenold-auto-seed", timeout=5.0)
        run_seed_mock.assert_called_once()

    def test_hook_does_not_block_on_unreachable_neo4j(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Latency invariant — boot path must stay sub-second on
        a fully-unreachable Neo4j even though the driver itself
        would block for 30 s.
        """
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        monkeypatch.setattr(_main, "_BOOT_NEO4J_TIMEOUT_S", 0.3)

        fake = _BlockingClient(enabled=True, block_timeout=10.0)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )
        # Stub run_seed so the now-fired seed thread doesn't keep
        # blocking past the test.
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed",
            MagicMock(return_value={"status": "ok", "total_nodes": 0, "total_edges": 0}),
        )

        start = time.perf_counter()
        _main._maybe_auto_seed_neo4j()
        elapsed = time.perf_counter() - start
        assert elapsed < 1.5, (
            f"unreachable-neo4j boot path took {elapsed:.2f}s — must "
            "stay well under the 30s healthcheck budget"
        )

        _wait_for_thread("regenold-auto-seed", timeout=5.0)


# ─── LLM startup log boot-path timeout ──────────────────────────────────


class TestLLMStartupLogTimeout:
    """``_log_llm_provider_status`` must not stall on unreachable Neo4j.

    The hook makes 3+ blocking Neo4j round-trips (get_client / health
    / stats / GDS probes). On a dead graph, each defaults to ~30 s
    via the driver. R45 Fix 3.4 wraps each in ``_run_with_timeout``.
    """

    def test_unreachable_neo4j_does_not_block_startup_log(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        # Provider can be anything — the LLM half of the hook just
        # logs a config-only line, no network. The Neo4j half is what
        # we're stressing.
        monkeypatch.setattr(_main, "_BOOT_NEO4J_TIMEOUT_S", 0.3)

        fake = _BlockingClient(enabled=True, block_timeout=10.0)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        caplog.set_level(logging.WARNING, logger=_main.__name__)
        start = time.perf_counter()
        _main._log_llm_provider_status()
        elapsed = time.perf_counter() - start

        # 3 probes * 0.3 s = at most ~0.9 s worst-case. Generous
        # ceiling: 2 seconds.
        assert elapsed < 2.0, (
            f"startup log took {elapsed:.2f}s — expected <2.0s under "
            "0.3s per-probe budget"
        )

        # Operator-visible signal: at least one "timed out" warning
        # surfaces for the failing probe.
        assert "timed out" in caplog.text or "failed" in caplog.text

    def test_unreachable_client_init_short_circuits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When ``get_graph_client()`` itself hangs, we must time out
        and skip the downstream health/stats probes.
        """
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        monkeypatch.setattr(_main, "_BOOT_NEO4J_TIMEOUT_S", 0.3)

        def _hanging_get_client() -> Any:
            time.sleep(10.0)
            raise AssertionError("should not return")

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", _hanging_get_client
        )

        caplog.set_level(logging.WARNING, logger=_main.__name__)
        start = time.perf_counter()
        _main._log_llm_provider_status()
        elapsed = time.perf_counter() - start

        # Only one probe should fire (the get_client one) and it
        # should hit the 0.3s budget — so total elapsed under 1s.
        assert elapsed < 1.5, (
            f"startup log took {elapsed:.2f}s on hanging get_client "
            "— budget is 0.3s"
        )
        assert "graph probe" in caplog.text


# ─── Postgres-down distinction (R45 Fix 3.2) ────────────────────────────


class TestPostgresAdvisoryLockOutcomes:
    """``_acquire_postgres_advisory_lock`` must distinguish failure modes."""

    def test_no_database_url_returns_not_applicable(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app import main as _main

        # DATABASE_URL unset by the fixture.
        handle, status, detail = _main._acquire_postgres_advisory_lock()
        assert handle is None
        assert status == _main._PG_LOCK_NOT_APPLICABLE

    def test_unreachable_postgres_returns_unreachable_not_held(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A connect-refused must NOT route to the 'lock held' branch.

        The pre-R45 behaviour returned ``None`` for both "another
        worker is seeding" and "Postgres is unreachable" — operators
        chasing why Neo4j stayed empty were misled by a
        "skip-non-leader" log when actually nothing seeded.
        """
        from app import main as _main

        # Point at a TCP port that's guaranteed unreachable (RFC 5737
        # TEST-NET-1 address — won't route).
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://user:pass@192.0.2.1:5432/db?connect_timeout=1",
        )

        handle, status, detail = _main._acquire_postgres_advisory_lock()
        assert handle is None
        # Must NOT be reported as "lock_held" — that's the benign
        # branch the auto-seed treats as "another worker has it".
        assert status == _main._PG_LOCK_UNREACHABLE
        assert detail, "unreachable case must carry an error detail"

    def test_seed_thread_logs_postgres_unreachable_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When Postgres is unreachable, the seed thread emits the
        ``auto_seed_blocked_postgres_unreachable`` warning AND
        proceeds with the seed (using the process-local lock).
        """
        from app import main as _main

        # Force the advisory-lock acquire to return UNREACHABLE.
        def _fake_acquire() -> Any:
            return None, _main._PG_LOCK_UNREACHABLE, "OperationalError: refused"

        monkeypatch.setattr(
            _main, "_acquire_postgres_advisory_lock", _fake_acquire
        )

        run_seed_mock = MagicMock(
            return_value={
                "status": "ok",
                "total_nodes": 1,
                "total_edges": 1,
                "seed_version": "v",
                "kb_version": "kv",
                "counts": {},
            }
        )
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", run_seed_mock
        )

        caplog.set_level(logging.WARNING, logger=_main.__name__)
        _main._run_auto_seed_in_thread("test_reason")

        # Must NOT report lock_held (the false-positive that
        # motivated this fix).
        assert "advisory_lock_held" not in caplog.text
        # Operator-visible signal: the Postgres-unreachable warning.
        assert "auto_seed_blocked_postgres_unreachable" in caplog.text
        # Seed still proceeded.
        run_seed_mock.assert_called_once()

    def test_seed_thread_logs_lock_held_when_actually_held(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The benign 'lock held' case must STILL skip seeding silently."""
        from app import main as _main

        def _fake_acquire() -> Any:
            return None, _main._PG_LOCK_HELD, ""

        monkeypatch.setattr(
            _main, "_acquire_postgres_advisory_lock", _fake_acquire
        )

        run_seed_mock = MagicMock()
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", run_seed_mock
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._run_auto_seed_in_thread("test_reason")

        assert "advisory_lock_held" in caplog.text
        # Must NOT call run_seed when another worker has the lock.
        run_seed_mock.assert_not_called()
