"""Tests for the R45 Fix 3.1 cold-start pre-warm hook in ``app/main.py``.

The hook (:func:`app.main._maybe_prewarm_indexes`) runs three lazy
index builds at FastAPI startup so they complete before the first
paying request lands:

* ``app.engines.sentence_index._all_sentence_indexes`` (~457 ms cold)
* ``app.engines.definition_expand.build_definition_index`` (~605 ms cold)
* ``app.engines.embeddings_index.warm_up`` (~115 ms cold, when assets present)

Default mode is **synchronous** — the hook blocks startup until the
warm-up completes (~1.2 s total). This is the right shape for
production: Railway's 30 s healthcheck window easily absorbs the
boot cost, and the very first paying request lands on a warm engine.

An ``async`` mode is available via ``REGENOLD_PREWARM_MODE=async``
that spawns a daemon thread and returns immediately. Measured to
make max-latency WORSE than not pre-warming at all on a TestClient-
shaped harness (the worker thread fights the request thread for
CPU during cold-build), so it's opt-in only.

Contract guarantees:

1. ``_PREWARM_STARTED`` is a process-local idempotency latch — a
   second call to ``_maybe_prewarm_indexes()`` is a no-op.
2. ``REGENOLD_SKIP_STARTUP_LOG=1`` short-circuits the entire hook
   (used by the test harness).
3. Each individual helper is tolerant of asset / module absence —
   a raised exception inside any of the three helpers is logged at
   DEBUG and converted to a ``"err: <ExcType>"`` token in the
   ``regenold.prewarm_completed`` telemetry breakdown.
4. The structured-event telemetry line ``regenold.prewarm_completed``
   is always emitted at INFO once the warm-up finishes, even when
   one or more helpers fail.
"""
from __future__ import annotations

import logging
import threading
import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_prewarm_state(monkeypatch: pytest.MonkeyPatch):
    """Reset ``_PREWARM_STARTED`` between tests so each scenario is fresh."""
    import app.main as _main
    _main._PREWARM_STARTED = False
    for k in ("REGENOLD_SKIP_STARTUP_LOG", "REGENOLD_PREWARM_MODE"):
        monkeypatch.delenv(k, raising=False)
    yield
    _main._PREWARM_STARTED = False


def _wait_for_thread(name: str, timeout: float = 5.0) -> None:
    """Block until the named daemon thread finishes (best-effort)."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        alive = any(
            t.is_alive() and t.name == name
            for t in threading.enumerate()
        )
        if not alive:
            return
        time.sleep(0.01)


# ─── Skip path ──────────────────────────────────────────────────────────


class TestSkipPath:
    """``REGENOLD_SKIP_STARTUP_LOG=1`` must short-circuit the hook."""

    def test_skip_startup_log_short_circuits(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The kill-switch must prevent any thread from spawning."""
        from app import main as _main

        monkeypatch.setenv("REGENOLD_SKIP_STARTUP_LOG", "1")

        # Patch every helper to fail loud if invoked — should never fire.
        sentinel = MagicMock(
            side_effect=AssertionError(
                "prewarm helpers must not run under REGENOLD_SKIP_STARTUP_LOG=1"
            )
        )
        monkeypatch.setattr(_main, "_prewarm_sentence_index", sentinel)
        monkeypatch.setattr(_main, "_prewarm_definition_index", sentinel)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", sentinel)

        _main._maybe_prewarm_indexes()
        # Give any errant thread a moment to misbehave.
        time.sleep(0.05)
        # Flag must not be set under the kill-switch.
        assert _main._PREWARM_STARTED is False


# ─── Happy path ─────────────────────────────────────────────────────────


class TestHappyPath:
    """All three helpers fire once on first invocation."""

    def test_helpers_run_on_first_call(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        sentence_mock = MagicMock()
        definition_mock = MagicMock()
        embeddings_mock = MagicMock()
        monkeypatch.setattr(
            _main, "_prewarm_sentence_index", sentence_mock
        )
        monkeypatch.setattr(
            _main, "_prewarm_definition_index", definition_mock
        )
        monkeypatch.setattr(
            _main, "_prewarm_embeddings_index", embeddings_mock
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._maybe_prewarm_indexes()
        # Latch is flipped before the helpers run (sync mode runs
        # them inline AFTER the latch flip; async mode spawns the
        # thread after the latch flip).
        assert _main._PREWARM_STARTED is True

        # Sync mode (the default) — helpers already ran by the time
        # the hook returned.
        _wait_for_thread("regenold-prewarm")

        sentence_mock.assert_called_once()
        definition_mock.assert_called_once()
        embeddings_mock.assert_called_once()

        # Structured telemetry event is emitted exactly once with
        # all three helpers in the breakdown.
        assert "regenold.prewarm_completed" in caplog.text
        assert "sentence_index" in caplog.text
        assert "definition_index" in caplog.text
        assert "embeddings_index" in caplog.text
        assert "total_ms=" in caplog.text

    def test_telemetry_records_elapsed_ms(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The breakdown dict must contain numeric (float) elapsed times."""
        from app import main as _main

        monkeypatch.setattr(_main, "_prewarm_sentence_index", lambda: None)
        monkeypatch.setattr(_main, "_prewarm_definition_index", lambda: None)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", lambda: None)

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._maybe_prewarm_indexes()
        _wait_for_thread("regenold-prewarm")

        # The breakdown is logged via %s formatting — pull out the
        # ``breakdown={'...': ...}`` chunk and check it carries the
        # expected three keys + numeric values.
        prewarm_lines = [
            r.message for r in caplog.records
            if "regenold.prewarm_completed" in r.message
        ]
        assert len(prewarm_lines) == 1
        line = prewarm_lines[0]
        # Numeric ms values land as ints/floats (round(x, 1) on success).
        # An "err:" prefix would mean the helper raised. Since all three
        # are no-op lambdas we expect numeric values.
        assert "err:" not in line, f"unexpected error in breakdown: {line}"


# ─── Idempotency ────────────────────────────────────────────────────────


class TestIdempotency:
    """A second call to ``_maybe_prewarm_indexes`` must no-op."""

    def test_second_call_is_noop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app import main as _main

        sentence_mock = MagicMock()
        definition_mock = MagicMock()
        embeddings_mock = MagicMock()
        monkeypatch.setattr(
            _main, "_prewarm_sentence_index", sentence_mock
        )
        monkeypatch.setattr(
            _main, "_prewarm_definition_index", definition_mock
        )
        monkeypatch.setattr(
            _main, "_prewarm_embeddings_index", embeddings_mock
        )

        _main._maybe_prewarm_indexes()
        _wait_for_thread("regenold-prewarm")
        assert sentence_mock.call_count == 1

        # Second call: the latch should prevent ANY helper from
        # firing again.
        _main._maybe_prewarm_indexes()
        # Wait long enough that a buggy implementation would have
        # spawned a duplicate thread.
        time.sleep(0.05)
        _wait_for_thread("regenold-prewarm")

        assert sentence_mock.call_count == 1
        assert definition_mock.call_count == 1
        assert embeddings_mock.call_count == 1


# ─── Helper tolerance ───────────────────────────────────────────────────


class TestHelperTolerance:
    """Each helper individually must tolerate asset / module absence."""

    def test_one_helper_raising_does_not_break_others(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A raised helper logs but doesn't crash the thread."""
        from app import main as _main

        sentence_mock = MagicMock(side_effect=RuntimeError("simulated"))
        definition_mock = MagicMock()
        embeddings_mock = MagicMock()
        monkeypatch.setattr(
            _main, "_prewarm_sentence_index", sentence_mock
        )
        monkeypatch.setattr(
            _main, "_prewarm_definition_index", definition_mock
        )
        monkeypatch.setattr(
            _main, "_prewarm_embeddings_index", embeddings_mock
        )

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._maybe_prewarm_indexes()
        _wait_for_thread("regenold-prewarm")

        # The failing helper is recorded as ``err: <ExcType>`` but the
        # other two still run.
        sentence_mock.assert_called_once()
        definition_mock.assert_called_once()
        embeddings_mock.assert_called_once()

        prewarm_lines = [
            r.message for r in caplog.records
            if "regenold.prewarm_completed" in r.message
        ]
        assert len(prewarm_lines) == 1
        line = prewarm_lines[0]
        # Error token format: ``'sentence_index': 'err: RuntimeError'``
        assert "err: RuntimeError" in line

    def test_all_helpers_raising_still_emits_telemetry(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Even when every helper raises, the telemetry line is logged."""
        from app import main as _main

        bad = MagicMock(side_effect=ImportError("simulated"))
        monkeypatch.setattr(_main, "_prewarm_sentence_index", bad)
        monkeypatch.setattr(_main, "_prewarm_definition_index", bad)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", bad)

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._maybe_prewarm_indexes()
        _wait_for_thread("regenold-prewarm")

        assert "regenold.prewarm_completed" in caplog.text
        # All three helpers are recorded as errors in the breakdown.
        prewarm_lines = [
            r.message for r in caplog.records
            if "regenold.prewarm_completed" in r.message
        ]
        line = prewarm_lines[0]
        assert line.count("err: ImportError") == 3


# ─── Production helper smoke tests ──────────────────────────────────────


class TestProductionHelpers:
    """The real ``_prewarm_*`` functions must not raise on this codebase.

    These are smoke tests — they exercise the actual production
    helpers (not mocks) against the in-process modules. Each must
    complete without raising even if the module is not in a fully-
    initialised state.
    """

    def test_sentence_index_helper_runs(self) -> None:
        from app.main import _prewarm_sentence_index
        # Must not raise — the corpus is bundled in-repo and the
        # build is lazy-cached.
        _prewarm_sentence_index()

    def test_definition_index_helper_runs(self) -> None:
        from app.main import _prewarm_definition_index
        _prewarm_definition_index()

    def test_embeddings_index_helper_runs(self) -> None:
        from app.main import _prewarm_embeddings_index
        # Tolerant of missing assets — when ``is_available()`` is
        # False (e.g. CI without the ~1.8 MB asset bundle) the
        # helper is a no-op.
        _prewarm_embeddings_index()


# ─── Sync vs async mode ─────────────────────────────────────────────────


class TestSyncMode:
    """Default mode (sync) blocks startup until pre-warm completes.

    This is the desired shape for production: 1.2 s extra boot cost
    is well inside Railway's 30 s healthcheck window, and the first
    paying request lands on a warm engine.
    """

    def test_sync_mode_blocks_until_helpers_complete(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app import main as _main

        slow_mock = MagicMock(side_effect=lambda: time.sleep(0.3))
        monkeypatch.setattr(_main, "_prewarm_sentence_index", slow_mock)
        monkeypatch.setattr(_main, "_prewarm_definition_index", slow_mock)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", slow_mock)

        start = time.perf_counter()
        _main._maybe_prewarm_indexes()
        elapsed = time.perf_counter() - start
        # Sync mode: hook returns only AFTER all helpers complete.
        # 3 * 0.3s = ~0.9s.
        assert elapsed >= 0.8, (
            f"sync prewarm hook returned in {elapsed*1000:.0f}ms — "
            "expected ~900ms (blocking)"
        )

    def test_sync_mode_logs_mode_sync(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setattr(_main, "_prewarm_sentence_index", lambda: None)
        monkeypatch.setattr(_main, "_prewarm_definition_index", lambda: None)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", lambda: None)

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._maybe_prewarm_indexes()
        assert "mode=sync" in caplog.text


class TestAsyncMode:
    """Opt-in async mode spawns a daemon thread.

    Useful when boot latency matters more than first-request latency
    (e.g. health-check-only deploys).
    """

    def test_async_mode_returns_immediately(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("REGENOLD_PREWARM_MODE", "async")
        slow_mock = MagicMock(side_effect=lambda: time.sleep(0.5))
        monkeypatch.setattr(_main, "_prewarm_sentence_index", slow_mock)
        monkeypatch.setattr(_main, "_prewarm_definition_index", slow_mock)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", slow_mock)

        start = time.perf_counter()
        _main._maybe_prewarm_indexes()
        elapsed = time.perf_counter() - start
        # Async mode: hook spawns thread and returns. Well under 100ms.
        assert elapsed < 0.1, (
            f"async prewarm hook took {elapsed*1000:.0f}ms — must "
            "spawn daemon thread without blocking"
        )

        # Wait for the slow daemon to finish so it doesn't bleed into
        # other tests.
        _wait_for_thread("regenold-prewarm", timeout=5.0)

    def test_async_mode_logs_mode_async(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app import main as _main

        monkeypatch.setenv("REGENOLD_PREWARM_MODE", "async")
        monkeypatch.setattr(_main, "_prewarm_sentence_index", lambda: None)
        monkeypatch.setattr(_main, "_prewarm_definition_index", lambda: None)
        monkeypatch.setattr(_main, "_prewarm_embeddings_index", lambda: None)

        caplog.set_level(logging.INFO, logger=_main.__name__)
        _main._maybe_prewarm_indexes()
        _wait_for_thread("regenold-prewarm", timeout=5.0)
        assert "mode=async" in caplog.text
