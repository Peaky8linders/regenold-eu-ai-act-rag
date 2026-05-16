"""Tests for the Postgres audit-chain advisory-lock fix (Issue #39).

``PostgresAuditStore.record()`` previously relied on
``SELECT ... FOR UPDATE ... ORDER BY seq DESC LIMIT 1`` to serialise
concurrent appends. That row-lock only locks the row it actually
returns — when the table is empty it returns no rows and locks
nothing, letting two concurrent writers each compute
``previous_hash=""`` and insert two genesis rows. Even on a non-empty
table, READ COMMITTED can re-read the tail after another writer
commits and proceed with a stale previous_hash.

The fix wraps every append in ``pg_advisory_xact_lock`` keyed on
:data:`_AUDIT_CHAIN_LOCK_KEY` so concurrent transactions queue at
the lock regardless of whether the chain is empty. The lock is
transaction-scoped — auto-released on COMMIT/ROLLBACK.

We unit-test this without a real Postgres by intercepting the
SQLAlchemy engine: the test driver collects every SQL statement
``record()`` emits and verifies (a) ``pg_advisory_xact_lock`` is
issued, (b) it is issued BEFORE the tail SELECT, (c) the SELECT no
longer carries the now-redundant (and unsafe) ``FOR UPDATE`` row-
lock clause.

A real-Postgres concurrency race test is deferred to the integration
suite where a live ``DATABASE_URL`` is available.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.evidence.models import EvidenceEntryType
from app.evidence.store import (
    PostgresAuditStore,
    _AUDIT_CHAIN_LOCK_KEY,
)


# ─── Fake SQLAlchemy engine + connection ────────────────────────────────────


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def scalar(self) -> Any:
        if not self._rows:
            return 0
        row = self._rows[0]
        return row[0] if isinstance(row, (list, tuple)) else row


class _FakeConn:
    """Records every (sql_text, params) pair as ``record()`` executes them.

    ``record()`` issues this fixed sequence today:
      1. ``SELECT pg_advisory_xact_lock(:lock_key)``        — the new lock
      2. ``SELECT data_hash FROM evidence_entries ...``     — tail read
      3. ``INSERT INTO evidence_entries ...``               — the append
    """

    def __init__(
        self,
        calls: list[tuple[str, dict[str, Any] | None]],
        *,
        tail_rows: list[Any] | None = None,
    ) -> None:
        self._calls = calls
        self._tail_rows = tail_rows or []

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        # SQLAlchemy ``text(...)`` clauses stringify back to their original SQL,
        # which is enough for our assertions.
        sql = str(stmt)
        self._calls.append((sql, params))
        if "SELECT data_hash" in sql:
            return _FakeResult(self._tail_rows)
        return _FakeResult([])


class _FakeBeginCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def __enter__(self) -> _FakeConn:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeEngine:
    def __init__(self, *, tail_rows: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self._conn = _FakeConn(self.calls, tail_rows=tail_rows)

    def begin(self) -> _FakeBeginCtx:
        return _FakeBeginCtx(self._conn)


def _make_store(*, tail_rows: list[Any] | None = None) -> tuple[PostgresAuditStore, _FakeEngine]:
    """Build a PostgresAuditStore with its engine pre-stubbed.

    Avoids touching ``_setup`` (which would import SQLAlchemy and try
    to contact Postgres). The store's ``record()`` only needs
    ``engine.begin()`` + ``conn.execute()``, both of which the fake
    supplies.
    """
    store = PostgresAuditStore(database_url="postgresql://fake")
    fake = _FakeEngine(tail_rows=tail_rows)
    store._engine = fake  # type: ignore[assignment] — direct injection
    return store, fake


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_audit_chain_lock_key_is_distinct_from_neo4j_seed_lock() -> None:
    """The audit-chain lock and the Neo4j auto-seed lock must not collide.

    Two unrelated subsystems holding the same advisory key would
    serialise on each other for no reason — and worse, in theory
    deadlock if either path ever tried to acquire the other while
    holding its own. The Neo4j auto-seed key is hard-coded as
    ``7340518364729403841`` in ``app/main.py::_maybe_auto_seed_neo4j``
    (CLAUDE.md Round 36).
    """
    NEO4J_SEED_KEY = 7340518364729403841
    assert _AUDIT_CHAIN_LOCK_KEY != NEO4J_SEED_KEY


def test_audit_chain_lock_key_fits_signed_64_bit_range() -> None:
    """``pg_advisory_xact_lock`` accepts a signed 64-bit BIGINT."""
    assert -(2 ** 63) <= _AUDIT_CHAIN_LOCK_KEY <= (2 ** 63) - 1


def test_record_issues_advisory_lock_before_tail_select_on_empty_chain() -> None:
    """Genesis-row case: the empty-table fork that motivated the fix.

    The advisory lock must be the FIRST SQL statement so concurrent
    writers serialise even when the SELECT would lock nothing.
    """
    store, fake = _make_store(tail_rows=[])  # empty chain → genesis row
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"q": "Article 5?"},
    )

    sqls = [sql for sql, _ in fake.calls]
    assert len(sqls) >= 3, f"expected lock + select + insert, got {sqls}"

    # 1) lock first
    assert "pg_advisory_xact_lock" in sqls[0], (
        f"first stmt must acquire the advisory lock, got: {sqls[0]!r}"
    )
    # 2) lock params carry our module constant
    _, lock_params = fake.calls[0]
    assert lock_params is not None and lock_params.get("lock_key") == _AUDIT_CHAIN_LOCK_KEY

    # 3) tail SELECT comes AFTER the lock
    select_idx = next(i for i, s in enumerate(sqls) if "SELECT data_hash" in s)
    lock_idx = next(i for i, s in enumerate(sqls) if "pg_advisory_xact_lock" in s)
    assert lock_idx < select_idx, "advisory lock must precede tail SELECT"

    # 4) INSERT comes after both
    insert_idx = next(i for i, s in enumerate(sqls) if "INSERT INTO evidence_entries" in s)
    assert select_idx < insert_idx


def test_record_drops_for_update_clause_from_tail_select() -> None:
    """``FOR UPDATE`` is redundant once the advisory lock holds, and on an
    empty table it locks nothing — keeping it would invite confusion
    about which mechanism is actually serialising writes.
    """
    store, fake = _make_store(tail_rows=[])
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"q": "anything"},
    )
    tail_select = next(sql for sql, _ in fake.calls if "SELECT data_hash" in sql)
    assert "FOR UPDATE" not in tail_select.upper(), (
        f"tail SELECT should no longer use FOR UPDATE: {tail_select!r}"
    )


def test_record_acquires_lock_even_with_non_empty_chain() -> None:
    """Non-empty chain: READ COMMITTED can re-read the tail after a
    concurrent commit, so the advisory lock must still serialise.
    """
    prior_tail = ["abc123" * 6 + "abcdef"]  # 64-char sha256-shaped hash
    store, fake = _make_store(tail_rows=[prior_tail])
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"q": "follow-up"},
    )

    sqls = [sql for sql, _ in fake.calls]
    assert "pg_advisory_xact_lock" in sqls[0]
    # Genesis fix shouldn't regress the non-empty path: previous_hash
    # should still flow through to the INSERT.
    insert_call = next((sql, params) for sql, params in fake.calls if "INSERT INTO" in sql)
    _, insert_params = insert_call
    assert insert_params is not None
    assert insert_params["previous_hash"] == prior_tail[0]


def test_record_acquires_lock_per_transaction_not_per_process() -> None:
    """Each ``record()`` call must re-acquire the lock — the lock is
    transaction-scoped (``pg_advisory_xact_lock``), not session-scoped.
    """
    store, fake = _make_store(tail_rows=[])
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"q": "first"},
    )
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"q": "second"},
    )
    lock_acquires = [sql for sql, _ in fake.calls if "pg_advisory_xact_lock" in sql]
    assert len(lock_acquires) == 2, (
        f"expected 1 lock acquire per record(), got {len(lock_acquires)}"
    )


def test_record_returns_well_formed_entry_with_lock_path() -> None:
    """End-to-end smoke: the lock-first append still produces a valid
    EvidenceEntry with the chained ``data_hash``.
    """
    store, _ = _make_store(tail_rows=[])
    entry = store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"q": "Art. 5?", "a": "prohibited under Art. 5(1)(a)"},
        article_ref="Article 5",
        tenant_id="tenant-xyz",
    )
    assert entry.previous_hash == ""  # genesis
    assert entry.data_hash and len(entry.data_hash) == 64  # sha256 hex
    assert entry.entry_type == EvidenceEntryType.regenold_question
    assert entry.tenant_id == "tenant-xyz"
    assert entry.article_ref == "Article 5"
