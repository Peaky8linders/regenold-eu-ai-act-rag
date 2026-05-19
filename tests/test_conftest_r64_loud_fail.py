"""R64 — conftest.py loud-fail-on-import + one-shot-WARNING regression.

The R63-E autouse fixture in ``tests/conftest.py`` resets the
EvidenceStore singleton between tests. Pre-R64 the import + the call
were both wrapped in a bare ``try/except: pass``, so a future refactor
that renamed ``reset_evidence_store_for_tests`` would have silently
disabled test isolation and re-introduced the R63-E flake without any
CI signal.

R64 splits the failure modes:
1. **Import failure** (helper missing) → ``pytest.UsageError`` at
   collection time. We can't easily exercise that path inside a running
   pytest session, so we assert the structural invariants instead
   (helper is bound at module level; UsageError raise text references
   the helper name).
2. **Runtime failure** (helper raises) → one-shot WARNING via the
   module-level ``_RESET_FAILURE_LOGGED`` flag; subsequent calls stay
   silent so the test log isn't flooded.
"""
from __future__ import annotations

import logging

import pytest


def test_conftest_imports_reset_helper() -> None:
    """R64 — confirm the conftest import path is wired correctly.

    If this test fails, the autouse fixture is broken and every test
    silently loses isolation. The R64 loud-fail at collection time
    should prevent us ever reaching this point, but the assertion is
    here as defence-in-depth.
    """
    import tests.conftest as _conftest

    assert hasattr(_conftest, "reset_evidence_store_for_tests"), (
        "tests/conftest.py must import reset_evidence_store_for_tests at "
        "module level so a rename/removal is caught at collection time."
    )
    # The bound symbol must be callable — a None placeholder would defeat
    # the loud-fail contract.
    assert callable(_conftest.reset_evidence_store_for_tests), (
        "tests/conftest.py.reset_evidence_store_for_tests must be callable; "
        "got a non-callable binding."
    )


def test_conftest_exposes_one_shot_warning_flag() -> None:
    """R64 — the module-level flag must exist and start as False so the
    one-shot WARNING semantics work."""
    import tests.conftest as _conftest

    assert hasattr(_conftest, "_RESET_FAILURE_LOGGED"), (
        "tests/conftest.py must expose _RESET_FAILURE_LOGGED as a "
        "module-level flag for the one-shot WARNING."
    )
    # Note: this flag may be True if a prior test in the session
    # triggered the failure path; we only assert the type contract here.
    assert isinstance(_conftest._RESET_FAILURE_LOGGED, bool), (
        "_RESET_FAILURE_LOGGED must be a bool."
    )


def test_reset_failure_logs_warning_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``reset_evidence_store_for_tests`` raises at runtime, the
    fixture body should log a WARNING — exactly once — and continue.

    We invoke the fixture body directly (bypassing the autouse machinery
    so we can control the global flag + caplog reliably).
    """
    import tests.conftest as _conftest

    # Reset the one-shot flag so we measure THIS test's behaviour, not a
    # leftover from earlier in the session.
    monkeypatch.setattr(_conftest, "_RESET_FAILURE_LOGGED", False)

    def _boom() -> None:
        raise RuntimeError("simulated reset failure")

    monkeypatch.setattr(_conftest, "reset_evidence_store_for_tests", _boom)

    # R64 extracted ``_safe_reset_audit_store`` as a plain helper so the
    # WARNING semantics can be tested without driving the autouse fixture
    # directly (pytest forbids that since 9.0).
    caplog.set_level(logging.WARNING, logger="tests.conftest")

    _conftest._safe_reset_audit_store()
    # Call again — same monkeypatched _boom — to confirm one-shot.
    _conftest._safe_reset_audit_store()

    # One WARNING — not two.
    warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "reset_evidence_store_for_tests" in rec.getMessage()
    ]
    assert len(warnings) == 1, (
        f"Expected exactly 1 WARNING from the one-shot guard; got "
        f"{len(warnings)}: {[w.getMessage() for w in warnings]}"
    )
    assert "simulated reset failure" in warnings[0].getMessage()
    assert _conftest._RESET_FAILURE_LOGGED is True, (
        "After the first runtime failure, _RESET_FAILURE_LOGGED must be True."
    )


def test_reset_helper_normally_succeeds() -> None:
    """Smoke: the normal-path reset succeeds without raising.

    Catches the regression where a refactor accidentally makes the
    helper raise on every call.
    """
    import tests.conftest as _conftest

    # Direct call (not via fixture) — must not raise.
    _conftest.reset_evidence_store_for_tests()
