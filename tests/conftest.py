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
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_audit_store():
    """Drop the EvidenceStore singleton between tests.

    Wrapped in a broad try/except so a transient import failure here
    can never poison the entire pytest collection — at worst the test
    runs against whatever singleton state was left over (the pre-R63-E
    status quo).
    """
    try:
        from app.evidence.store import reset_evidence_store_for_tests

        reset_evidence_store_for_tests()
    except Exception:  # noqa: BLE001 — never block test collection
        pass
    yield
    # No post-test reset needed; the next test's pre-yield reset
    # handles cleanup. Keeping this one-sided also means a failing
    # test's audit-chain state is still inspectable in a post-mortem
    # pytest --pdb session.
