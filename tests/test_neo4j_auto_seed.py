"""Tests for the Neo4j auto-seed startup hook in ``app/main.py``.

The hook (``_maybe_auto_seed_neo4j``) fires from a FastAPI startup
event and:

* Skips entirely when ``NEO4J_URI`` is unset, when ``NEO4J_AUTO_SEED``
  is explicitly off, or when ``REGENOLD_SKIP_STARTUP_LOG=1``.
* Reads ``KBMetadata.seed_version`` + ``kb_version`` via
  ``get_graph_client().execute_read``; if both match the current
  ``SEED_VERSION`` + ``KB_VERSION``, logs ``neo4j_seed_current`` and
  returns without writing.
* Otherwise fires ``threading.Thread(daemon=True)`` to invoke
  ``scripts.seed_neo4j_kb.run_seed`` in the background — uvicorn boot
  is never blocked on graph I/O.
* Catches and logs every exception in the seeder thread so a downed
  Neo4j never affects request serving.

Tests mock the graph client + the seeder module so we can drive every
branch without spinning up Neo4j or actually writing.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────


class _FakeClient:
    """Minimal stand-in for ``GraphClient`` for the auto-seed hook."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        seed_version: str | None = None,
        kb_version: str | None = None,
        raise_on_read: bool = False,
    ) -> None:
        self.enabled = enabled
        self._seed_version = seed_version
        self._kb_version = kb_version
        self._raise_on_read = raise_on_read
        self.execute_read_calls: list[str] = []

    def execute_read(self, query: str, parameters: dict | None = None) -> list[dict]:
        self.execute_read_calls.append(query)
        if self._raise_on_read:
            raise RuntimeError("simulated neo4j read failure")
        if self._seed_version is None:
            return []
        return [{"v": self._seed_version, "kv": self._kb_version or ""}]


@pytest.fixture(autouse=True)
def _reset_auto_seed_module_state(monkeypatch: pytest.MonkeyPatch):
    """Reset the module-level ``_AUTO_SEED_STARTED`` flag between tests.

    The flag latches True after the first seed-trigger so a second test
    in the same process would otherwise short-circuit on
    ``action=skip-already-started``.
    """
    import app.main as _main
    _main._AUTO_SEED_STARTED = False
    # Strip the env vars the hook reads so each test starts blank.
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


def _call_hook() -> None:
    """Invoke the startup hook synchronously (it's a plain function)."""
    from app.main import _maybe_auto_seed_neo4j
    _maybe_auto_seed_neo4j()


# ─── Skip-paths (no Neo4j touch) ────────────────────────────────────────


class TestSkipPaths:
    """Decision-tree branches that exit BEFORE touching the graph client."""

    def test_no_neo4j_uri_skips_entirely(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # ``NEO4J_URI`` unset by autouse fixture.
        from app import main as _main

        # Sentinel that fails loud if the hook tries to reach the client.
        def _explode_get_client() -> Any:
            raise AssertionError(
                "get_graph_client() must not be called when NEO4J_URI is unset"
            )

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", _explode_get_client
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=disabled-no-uri" in caplog.text

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off"])
    def test_auto_seed_env_off_skips(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        value: str,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        monkeypatch.setenv("NEO4J_AUTO_SEED", value)

        def _explode_get_client() -> Any:
            raise AssertionError(
                "get_graph_client() must not be called when "
                "NEO4J_AUTO_SEED is off"
            )

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", _explode_get_client
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=disabled-by-env" in caplog.text

    def test_skip_startup_log_short_circuits(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """REGENOLD_SKIP_STARTUP_LOG=1 must skip the entire hook body.

        This is the same kill-switch the LLM startup hook honours so the
        test harness never accidentally hits Neo4j.
        """
        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")
        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")

        def _explode_get_client() -> Any:
            raise AssertionError(
                "get_graph_client() must not be called under "
                "REGENOLD_SKIP_STARTUP_LOG=1"
            )

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", _explode_get_client
        )

        _call_hook()  # must not raise

    def test_non_leader_worker_skips(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        monkeypatch.setenv("REGENOLD_AUTO_SEED_LEADER_ONLY", "1")
        monkeypatch.setenv("REGENOLD_WORKER_INDEX", "1")

        def _explode_get_client() -> Any:
            raise AssertionError(
                "Non-leader workers must not call get_graph_client()"
            )

        monkeypatch.setattr(
            "app.graph.client.get_graph_client", _explode_get_client
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=skip-non-leader" in caplog.text
        assert "worker_idx=1" in caplog.text

    def test_leader_worker_proceeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Worker index 0 (the leader) MUST proceed past the worker gate."""
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        monkeypatch.setenv("REGENOLD_AUTO_SEED_LEADER_ONLY", "1")
        monkeypatch.setenv("REGENOLD_WORKER_INDEX", "0")

        fake = _FakeClient(
            enabled=False
        )  # short-circuit on graph_disabled instead
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=skip-graph-disabled" in caplog.text

    def test_graph_disabled_skips(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(enabled=False)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=skip-graph-disabled" in caplog.text
        # The hook should not have queried the graph since the client
        # is disabled.
        assert fake.execute_read_calls == []


# ─── Seed-current path ──────────────────────────────────────────────────


class TestSeedCurrent:
    def test_matching_seed_version_skips_write(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main
        from app.data.kb import KB_VERSION
        from scripts.seed_neo4j_kb import SEED_VERSION

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(
            enabled=True,
            seed_version=SEED_VERSION,
            kb_version=KB_VERSION,
        )
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        # If the seeder thread were spawned it would call run_seed —
        # patch run_seed so we can assert it was NOT invoked.
        run_seed_mock = MagicMock()
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", run_seed_mock
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "neo4j_seed_current" in caplog.text
        assert "action=skip-current" in caplog.text
        # Critical: no thread should have been spawned.
        run_seed_mock.assert_not_called()


# ─── Seed-needed path ───────────────────────────────────────────────────


class TestSeedNeeded:
    def _wait_for_thread(self, name: str, timeout: float = 2.0) -> None:
        """Block until the named daemon thread completes (best-effort)."""
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            alive = any(
                t.is_alive() and t.name == name
                for t in threading.enumerate()
            )
            if not alive:
                return
            time.sleep(0.01)

    def test_empty_graph_triggers_seed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(
            enabled=True, seed_version=None, kb_version=None
        )
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        run_seed_mock = MagicMock(
            return_value={
                "status": "ok",
                "total_nodes": 505,
                "total_edges": 351,
                "seed_version": "2026-05-16-r35",
                "kb_version": "2024.1689.v2",
                "counts": {"Article": 113},
            }
        )
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", run_seed_mock
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=seed-started" in caplog.text
        assert "reason=graph_empty" in caplog.text

        # Wait for the daemon thread to finish so we can assert against
        # the seeder mock.
        self._wait_for_thread("regenold-auto-seed")
        run_seed_mock.assert_called_once_with(
            dry_run=False, clear=False, verbose=False
        )
        assert "auto_seed_completed" in caplog.text
        assert "nodes=505" in caplog.text
        assert "edges=351" in caplog.text

    def test_seed_drift_triggers_seed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A non-matching seed_version must trigger a re-seed."""
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(
            enabled=True,
            seed_version="2025-01-01-OLD",
            kb_version="ancient",
        )
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        run_seed_mock = MagicMock(
            return_value={
                "status": "ok",
                "total_nodes": 505,
                "total_edges": 351,
                "seed_version": "2026-05-16-r35",
                "kb_version": "2024.1689.v2",
                "counts": {},
            }
        )
        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", run_seed_mock
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _call_hook()
        assert "action=seed-started" in caplog.text
        assert "reason=seed_drift" in caplog.text
        assert "current_seed=2025-01-01-OLD" in caplog.text

        self._wait_for_thread("regenold-auto-seed")
        run_seed_mock.assert_called_once()


# ─── Error-handling ─────────────────────────────────────────────────────


class TestErrorHandling:
    def _wait_for_thread(self, name: str, timeout: float = 2.0) -> None:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            alive = any(
                t.is_alive() and t.name == name
                for t in threading.enumerate()
            )
            if not alive:
                return
            time.sleep(0.01)

    def test_seeder_exception_caught(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(enabled=True, seed_version=None)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        def _exploding_seed(**kwargs: Any) -> Any:
            raise RuntimeError("simulated seed crash")

        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed", _exploding_seed
        )

        caplog.set_level(logging.WARNING, logger=_main.__name__)
        _call_hook()
        self._wait_for_thread("regenold-auto-seed")
        # The exception must have been caught + logged, never raised.
        assert "auto_seed_exception" in caplog.text
        assert "simulated seed crash" in caplog.text

    def test_seeder_failed_status_logged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(enabled=True, seed_version=None)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        monkeypatch.setattr(
            "scripts.seed_neo4j_kb.run_seed",
            MagicMock(return_value={"status": "graph_disabled"}),
        )

        caplog.set_level(logging.WARNING, logger=_main.__name__)
        _call_hook()
        self._wait_for_thread("regenold-auto-seed")
        assert "auto_seed_failed" in caplog.text
        assert "status=graph_disabled" in caplog.text

    def test_read_query_exception_caught_at_top(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """An exception thrown by execute_read must not crash the hook."""
        from app import main as _main

        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(enabled=True, raise_on_read=True)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        caplog.set_level(logging.WARNING, logger=_main.__name__)
        _call_hook()  # must not raise
        assert "auto_seed_check action=error" in caplog.text


# ─── Latency invariant ──────────────────────────────────────────────────


class TestLatency:
    def test_hook_does_not_block_on_seeder(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Startup latency must stay sub-100ms even when the seed runs.

        We simulate a slow seeder (sleeps 500ms) — the hook itself must
        still return well within 100ms because the seeder runs in a
        daemon thread.
        """
        monkeypatch.setenv("NEO4J_URI", "neo4j+s://test:7687")
        fake = _FakeClient(enabled=True, seed_version=None)
        monkeypatch.setattr(
            "app.graph.client.get_graph_client", lambda: fake
        )

        slow_seed_invoked = threading.Event()

        def _slow_seed(**kwargs: Any) -> dict[str, Any]:
            slow_seed_invoked.set()
            time.sleep(0.5)
            return {
                "status": "ok",
                "total_nodes": 1,
                "total_edges": 0,
                "seed_version": "x",
                "kb_version": "y",
                "counts": {},
            }

        monkeypatch.setattr("scripts.seed_neo4j_kb.run_seed", _slow_seed)

        start = time.perf_counter()
        _call_hook()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, (
            f"startup hook took {elapsed*1000:.1f}ms — should be sub-100ms "
            "because the seeder runs in a daemon thread"
        )
        # Sanity check — the seeder actually fired (rules out a silent
        # bail-out making the latency assertion trivially pass).
        assert slow_seed_invoked.wait(timeout=2.0), (
            "the seeder thread should have started running by now"
        )


# ─── run_seed() entrypoint (library-mode wrapper) ────────────────────────


class TestRunSeedEntrypoint:
    """Ensure the new ``run_seed()`` callable behaves correctly."""

    def test_dry_run_returns_payload_counts(self) -> None:
        from scripts.seed_neo4j_kb import KB_VERSION, SEED_VERSION, run_seed

        result = run_seed(dry_run=True)
        assert result["status"] == "dry_run"
        assert result["seed_version"] == SEED_VERSION
        assert result["kb_version"] == KB_VERSION
        assert result["total_nodes"] > 100  # 113 articles + ...
        assert result["total_edges"] > 50
        assert "counts" in result

    def test_graph_disabled_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When GraphClient is disabled, run_seed must report it cleanly."""
        from scripts import seed_neo4j_kb

        class _Disabled:
            enabled = False

            def __init__(self, *a: Any, **kw: Any) -> None:
                pass

            def close(self) -> None:
                pass

            def clear_graph(self) -> None:
                pass

        # Strip NEO4J_URI so the real client init path is blocked too.
        monkeypatch.delenv("NEO4J_URI", raising=False)
        import app.graph.client as gc_mod

        monkeypatch.setattr(gc_mod, "GraphClient", _Disabled)

        result = seed_neo4j_kb.run_seed(dry_run=False)
        assert result["status"] == "graph_disabled"
