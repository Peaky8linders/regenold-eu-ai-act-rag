"""R440/R442 — one live runner per evaluation label.

R442 replaced the R440 PID-file lock with an OS-held lock; see
``evals/regenold/run_lock.py`` for the measured Windows defect. The properties
pinned here are the ones R440 set out to guarantee — a live owner is refused, a
dead owner's lock is recoverable, the owner's PID is on record — plus the one
its unit tests could not reach: the owner living in ANOTHER process that is not
attached to the test's console, and dying by a hard kill.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from evals.regenold import run_lock
from evals.regenold import run_official_batch as runner

_REPO = Path(__file__).resolve().parents[1]

_OWNER = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from evals.regenold import run_lock
run_lock.acquire(Path(sys.argv[2]), sys.argv[3])
Path(sys.argv[2], "owner.ready").write_text("ok", encoding="utf-8")
time.sleep(120)
"""

_PROBER = r"""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from evals.regenold import run_lock
try:
    run_lock.acquire(Path(sys.argv[2]), sys.argv[3])
    out = "ACQUIRED"
except RuntimeError as exc:
    out = "REFUSED " + str(exc)
Path(sys.argv[2], "prober.out").write_text(out, encoding="utf-8")
"""


def _spawn_in_own_console(code: str, *args: str) -> subprocess.Popen:
    """A process with its OWN (hidden) console on Windows — two runners started
    from two terminals, the R440 incident — and a plain child elsewhere.

    The BASE interpreter, not the venv's: on Windows the venv ``python.exe`` is
    a launcher that spawns the real interpreter as a grandchild, so killing it
    would orphan the actual lock holder. ``run_lock`` is stdlib-only.
    """
    python = getattr(sys, "_base_executable", "") or sys.executable
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        kwargs.update(creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
    return subprocess.Popen([python, "-c", code, str(_REPO), *args], **kwargs)


@pytest.fixture(autouse=True)
def _no_lock_leaks():
    run_lock.release()
    yield
    run_lock.release()


def test_run_lock_rejects_live_owner_and_removes_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_RESULTS", tmp_path)
    lock = runner.acquire_run_lock("unit-lock")
    assert lock.exists()
    with pytest.raises(RuntimeError, match="already owned"):
        runner.acquire_run_lock("unit-lock")
    run_lock.release()
    # Released: the label is free again, and nothing had to be unlinked.
    assert runner.acquire_run_lock("unit-lock").exists()
    run_lock.release()

    # A leftover file from a dead owner is not a live lock, whatever it says.
    stale = tmp_path / "official-stale.run.lock"
    stale.write_text("999999 0\n", encoding="utf-8")
    assert runner.acquire_run_lock("stale").exists()


def test_run_lock_file_contains_current_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_RESULTS", tmp_path)
    lock = runner.acquire_run_lock("pid")
    # Written past the locked byte, so any process can read it.
    assert run_lock.owner_note(lock).split()[0] == str(os.getpid())
    with pytest.raises(RuntimeError, match=str(os.getpid())):
        runner.acquire_run_lock("pid")


def test_a_live_owner_in_another_console_is_refused_until_it_is_killed(tmp_path):
    """R442 — the R440 lock let the prober ACQUIRE here (os.kill -> WinError 87).

    Two-sided, measured on the same topology: main's PID-file lock printed
    ``ACQUIRED`` over the live owner; this lock refuses and names it.
    """
    owner = _spawn_in_own_console(_OWNER, str(tmp_path), "cross")
    try:
        deadline = time.monotonic() + 60
        while not (tmp_path / "owner.ready").exists():
            assert owner.poll() is None, "lock-owner process exited early"
            assert time.monotonic() < deadline, "lock-owner process never became ready"
            time.sleep(0.1)
        prober = _spawn_in_own_console(_PROBER, str(tmp_path), "cross")
        prober.wait(timeout=60)
        verdict = (tmp_path / "prober.out").read_text(encoding="utf-8")
        assert verdict.startswith("REFUSED"), verdict
        assert "already owned" in verdict
    finally:
        owner.kill()  # a hard kill: no atexit and no finally run in the owner
        owner.wait(timeout=30)
    assert run_lock.acquire(tmp_path, "cross").exists()
