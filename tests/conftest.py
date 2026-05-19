"""Project-wide pytest fixtures.

R63-E (2026-05-19) — autouse fixture that resets the EvidenceStore
singleton before each test. Fixes test-order pollution where
test_consistency_guard.py + other audit-writing tests leak state into
test_regenold_integration.py::test_authenticated_request_writes_partner_tenant_chain_entry
(captures ``before = len(...)`` then asserts ``after > before`` — a
dirty singleton inflates ``before`` and breaks the strict-monotonic
assertion).

The reset is cheap: it just drops a module-level singleton ref. The
next call to ``get_evidence_store()`` rebuilds from env (DATABASE_URL
etc.), which in the standard pytest run is unset → in-memory backend.

Tests that own their own DSNs (e.g. ``test_sqlite_audit_store.py``)
compose cleanly because they call ``reset_evidence_store_for_tests()``
explicitly inside the test body — the autouse fixture runs first, the
test's own reset runs second (idempotent).

R64 (2026-05-19) — distinguish import failures from runtime failures:

* **Import failure** (``reset_evidence_store_for_tests`` is renamed,
  moved, or removed) → raise ``pytest.UsageError`` at collection time.
  Without this helper, the R63-E autouse fixture can't isolate test
  state and the flake silently returns; loud-fail surfaces the
  regression immediately in CI.
* **Runtime failure** (helper raises) → log a WARNING once per session
  and continue. We never want a transient cleanup failure to mask the
  real test outcome, but silently swallowing every call hides
  systematic degradation.
"""
from __future__ import annotations

import logging

import pytest

logger = logging.getLogger(__name__)

# R64 — module-level import. If this fails, every test loses isolation
# and the R63-E flake returns invisibly; raise loudly at collection time
# so the regression is caught immediately in CI. AttributeError is NOT
# caught here — a test env that intentionally stubs out the helper can
# still rebind the symbol on this module after import.
try:
    from app.evidence.store import reset_evidence_store_for_tests
except ImportError as _import_exc:  # pragma: no cover — collection-time guard
    raise pytest.UsageError(
        "tests/conftest.py — required import failed: "
        f"app.evidence.store.reset_evidence_store_for_tests ({_import_exc}). "
        "Without this helper, the R63-E autouse fixture cannot isolate "
        "test state and the R63-E flake "
        "(test_authenticated_request_writes_partner_tenant_chain_entry "
        "↔ test_consistency_guard.py) will silently return. Update the "
        "import path or the helper name and re-run."
    ) from _import_exc

# One-shot flag so a systematic runtime failure (e.g. broken DSN parsing
# during ``reset_evidence_store_for_tests``) logs once per session rather
# than once per test.
_RESET_FAILURE_LOGGED: bool = False


def _safe_reset_audit_store() -> None:
    """Call ``reset_evidence_store_for_tests`` with one-shot WARNING on failure.

    R64 — extracted from the autouse fixture body so the regression test
    can exercise the one-shot WARNING semantics directly (pytest forbids
    calling fixtures directly).
    """
    global _RESET_FAILURE_LOGGED
    try:
        reset_evidence_store_for_tests()
    except Exception as exc:  # noqa: BLE001 — never block a test on cleanup
        if not _RESET_FAILURE_LOGGED:
            logger.warning(
                "tests/conftest.py: reset_evidence_store_for_tests() raised "
                "%s; subsequent failures will be silent. R63-E test isolation "
                "may be degraded.",
                exc,
            )
            _RESET_FAILURE_LOGGED = True


@pytest.fixture(autouse=True)
def _reset_audit_store():
    """Drop the EvidenceStore singleton between tests.

    R64 — runtime failures here are wrapped in a one-shot WARNING so a
    transient cleanup error never blocks a test's real outcome, but a
    systematic degradation is still visible in the pytest log stream.
    Import failures are handled at module level above (loud-fail).
    """
    _safe_reset_audit_store()
    yield
    # No post-test reset needed; the next test's pre-yield reset
    # handles cleanup. Keeping this one-sided also means a failing
    # test's audit-chain state is still inspectable in a post-mortem
    # pytest --pdb session.
