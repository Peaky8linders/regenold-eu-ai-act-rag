from __future__ import annotations

import os

import pytest

from evals.regenold import run_official_batch as runner


def test_run_lock_rejects_live_owner_and_removes_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_RESULTS", tmp_path)
    runner._RUN_LOCK = None
    lock = runner.acquire_run_lock("unit-lock")
    assert lock.exists()
    with pytest.raises(RuntimeError, match="already owned"):
        runner.acquire_run_lock("unit-lock")
    lock.unlink()
    runner._RUN_LOCK = None

    stale = tmp_path / "official-stale.run.lock"
    stale.write_text("999999 0\n", encoding="utf-8")
    acquired = runner.acquire_run_lock("stale")
    assert acquired.exists()
    acquired.unlink()
    runner._RUN_LOCK = None


def test_run_lock_file_contains_current_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_RESULTS", tmp_path)
    runner._RUN_LOCK = None
    lock = runner.acquire_run_lock("pid")
    assert lock.read_text(encoding="utf-8").split()[0] == str(os.getpid())
    lock.unlink()
    runner._RUN_LOCK = None
