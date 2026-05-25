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


# R84 (2026-05-24) — `app.routes.regenold._classify_intent_cached` memoises
# `classify_intent(question)` per request via a `ContextVar[dict | None]`.
# Inside the route the ContextVar is `.set({})` at the top of the handler
# (per-request scope). Tests that exercise `_classify_intent_cached` /
# `_intent_anchor_set` directly skip that reset, so the lazy-init dict
# from one test persists into the next and serves cached results across
# distinct `patch("classify_intent", ...)` setups. Symptom: two tests
# patching the SAME question key to different mocked IntentResult values
# see the FIRST test's value in BOTH (e.g.
# `test_unknown_article_anchor_is_dropped` caches an empty result for
# `"What's the max fine?"` and the subsequent `test_known_article_anchor_is_kept`
# reads the empty cache hit instead of the patched `Art. 99` result).
# Mirrors the R63-E EvidenceStore isolation pattern above.
try:
    from app.routes import regenold as _regenold_module
except ImportError:  # pragma: no cover — tested env always has this
    _regenold_module = None


@pytest.fixture(autouse=True)
def _reset_request_intent_cache():
    """Clear the per-request intent cache ContextVar between tests.

    R84 isolation — see comment above. Setting the ContextVar to ``None``
    re-arms the lazy-init path so each test starts with no in-flight
    cache state.
    """
    if _regenold_module is not None:
        try:
            _regenold_module._request_intent_cache.set(None)
        except Exception:  # noqa: BLE001 — never block a test on cleanup
            pass
    yield


# R89-A code-review fix (E&EC-F4) — clear REGENOLD_R89A_FORCE_APPEND
# before every test so a developer running the full suite with the
# production env var set (matches railway.toml) sees CI / local parity.
# Tests that want to exercise the force-append path explicitly opt in
# via ``monkeypatch.setenv("REGENOLD_R89A_FORCE_APPEND", "1")``. Mirrors
# the per-test env-clearing pattern documented in the R84 fixture above.
@pytest.fixture(autouse=True)
def _reset_r89a_force_append_env(monkeypatch):
    """Default the R89-A force-append env to OFF for every test.

    Without this, a developer who runs the full suite with the
    production env (``REGENOLD_R89A_FORCE_APPEND=1`` from railway.toml)
    in their shell would see different augmenter behavior than CI —
    the legacy R79 / R80 / R81-N appender-path guards would fail in a
    way that's hard to debug. Forcing OFF here keeps every test
    deterministic regardless of the developer's shell state.
    """
    monkeypatch.delenv("REGENOLD_R89A_FORCE_APPEND", raising=False)
    yield
