"""R427 — falsify the T1 equivalence gate: does it notice a behaviour change?

An equivalence harness that passes proves nothing until it is shown to FAIL on
the change it is meant to detect. This script perturbs exactly one thing — the
change T1 deliberately deferred (T1b: make ``PRESET_ANSWER`` apply the
structural-truncation rule) — re-runs the differential, and requires it to
report mismatches. It then restores ``app/llm/stage2.py`` and verifies the
restore by hash, so the shipped tree cannot be left modified.

Each run is its own PROCESS. That is not a style choice: ``app.engines.
_graph_rag_impl`` binds ``dispatch_leg2`` by name at import, so perturbing the
file inside one interpreter leaves the already-imported module — and the
engine's reference to it — untouched, and the probe would report a false
"gate is insensitive".

Usage::

    .venv\\Scripts\\python.exe -m docs.measurements.r427.sensitivity
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TARGET = REPO / "app" / "llm" / "stage2.py"
REPLAY = "docs.measurements.r427.t1_leg2_differential"
BEFORE = '        ok = bool((text or "").strip())'
AFTER = (
    '        ok = bool((text or "").strip())'
    ' and not structurally_truncated(text or "")'
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _replay() -> tuple[int, str]:
    """One differential run in its own process: (mismatch count, summary line)."""
    proc = subprocess.run(
        [sys.executable, "-m", REPLAY], cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    summary = ""
    for line in proc.stdout.splitlines():
        if "drives byte-identical" in line:
            summary = line.strip()
    return proc.returncode, summary


def main() -> int:
    original = TARGET.read_bytes()
    original_digest = _digest(original)
    source = original.decode("utf-8")
    if BEFORE not in source:
        print("PROBE BROKEN: could not find the answer-path verdict line")
        return 2

    print("=== unperturbed: the shipped move ===")
    baseline_rc, baseline = _replay()
    print(f"  {baseline}  (exit {baseline_rc})")
    if baseline_rc != 0:
        print("PROBE BROKEN: the shipped code already disagrees with HEAD")
        return 2

    perturbed_rc = -1
    perturbed = ""
    installed = False
    try:
        TARGET.write_text(source.replace(BEFORE, AFTER, 1), encoding="utf-8")
        installed = True
        print("=== perturbed: PRESET_ANSWER applies the truncation rule (the T1b change) ===")
        perturbed_rc, perturbed = _replay()
        print(f"  {perturbed}  (exit {perturbed_rc})")
    finally:
        TARGET.write_bytes(original)
        restored_ok = _digest(TARGET.read_bytes()) == original_digest
        print(
            f"restored app/llm/stage2.py: {'OK ' if restored_ok else 'FAIL'} "
            f"({original_digest})"
        )

    if not installed or not restored_ok:
        return 3
    if perturbed_rc == 0:
        print("VOID — the gate did NOT notice a real behaviour change")
        return 1
    print("SENSITIVE — the gate refused the deferred change, as a pure move must")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
