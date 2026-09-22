"""Per-label exclusive ownership of a live evaluation draw (R440, rebuilt R442).

Checkpoint files are label-addressed, so two interpreters drawing the same label
interleave rows and turn a seemingly complete gate into garbage — the R436/R437
and R440 failure (duplicate ``rg_109``, an unparsed line in ``.r1``).

R442 — the R440 version recorded a PID in an ``O_EXCL`` file and treated the
lock as stale when ``os.kill(pid, 0)`` failed. On Windows that call is
``GenerateConsoleCtrlEvent``: it asks whether the process shares the CALLER'S
CONSOLE, not whether it is alive. MEASURED: with the owner in another console
(or detached) the check raised ``WinError 87``, the lock read as stale, and a
second runner printed ``ACQUIRED`` over a live draw. Its ``release()`` also
unlinked a lock a later runner had taken over.

Now the lock is a byte-range lock the OPERATING SYSTEM holds for the life of the
process (``msvcrt.locking`` / ``fcntl.flock``) on an fd that is never closed
while the draw runs. The kernel drops it on any exit — clean, exception,
Ctrl-C or ``taskkill /F`` — so there is no staleness to guess at, no PID to
trust, and nothing to unlink. The owner's PID is still written, PAST the locked
byte so other processes can read it, for the refusal message only; it never
decides anything.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

#: ``(lock path, fd)`` of the lock this process holds, if any.
_HELD: tuple[Path, int] | None = None


def _try_lock(fd: int) -> None:
    """Take a non-blocking exclusive lock on byte 0 of ``fd`` or raise OSError."""
    if os.name == "nt":
        import msvcrt  # noqa: PLC0415

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl  # noqa: PLC0415

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def owner_note(lock: Path) -> str:
    """The diagnostic ``<pid> <epoch>`` the owner wrote, or ``"?"``."""
    try:
        with open(lock, "rb") as fh:
            fh.seek(1)  # byte 0 is the locked byte; Windows refuses to read it
            return fh.read().decode("ascii", "replace").strip() or "?"
    except OSError:
        return "?"


def acquire(results: Path, label: str) -> Path:
    """Own ``label`` for this process's lifetime, or raise ``RuntimeError``."""
    global _HELD
    results.mkdir(parents=True, exist_ok=True)
    lock = results / f"official-{label}.run.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR)
    try:
        _try_lock(fd)
    except OSError:
        os.close(fd)
        raise RuntimeError(
            f"evaluation label {label!r} is already owned by a live runner "
            f"(owner: {owner_note(lock)}); lock file: {lock}"
        ) from None
    os.lseek(fd, 1, os.SEEK_SET)
    note = f"{os.getpid()} {time.time():.3f}\n".encode("ascii")
    os.write(fd, note)
    os.ftruncate(fd, 1 + len(note))
    _HELD = (lock, fd)
    return lock


def release() -> None:
    """Drop the lock early (the OS drops it at exit anyway). Never unlinks."""
    global _HELD
    if _HELD is None:
        return
    _lock, fd = _HELD
    _HELD = None
    try:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    finally:
        os.close(fd)


__all__ = ["acquire", "owner_note", "release"]
