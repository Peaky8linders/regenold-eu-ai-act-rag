"""Audit-chain store — hash-chained in-memory backend (default) plus an
optional Postgres backend gated on the ``DATABASE_URL`` env var.

Ports the **audit-chain slice** of the parent CodexAI
``app/evidence/store.py`` into this Regenold competition bundle. The
parent module's full surface covers ~30 method names across SQLite +
Postgres + S3/R2 payload backends + incident reporting + compliance
progress + execution-run persistence; this port keeps only the chain
mechanics the Regenold route depends on:

* :func:`get_evidence_store` — process-wide singleton accessor. Returns
  the Postgres-backed :class:`PostgresAuditStore` when ``DATABASE_URL``
  is set, otherwise the in-memory :class:`InMemoryAuditStore`. Both
  expose the same public surface (``record`` / ``get_chain`` /
  ``verify_chain`` / ``count``).
* :func:`reset_evidence_store_for_tests` — drops the singleton so
  test fixtures + eval batches can start from an empty chain.
* :class:`EvidenceEntryType` — re-exported from
  :mod:`app.evidence.models` for callers (``from app.evidence.store
  import EvidenceEntryType`` is a backwards-compatible alias).

Hash-chain semantics
--------------------
Every ``record()`` call:

1. Reads the previous tail row's ``data_hash`` (empty string for the
   genesis entry).
2. Computes ``data_hash = sha256(json({"payload": ..., "previous_hash":
   ...}, sort_keys=True))`` — byte-identical to the CodexAI
   :func:`_compute_data_hash` function so a chain written here
   verifies cleanly against a replay of a CodexAI chain.
3. Inserts the new row with ``previous_hash`` pointing at the prior
   tail.

Modifying any payload after the fact invalidates the recomputed hash
on that row AND breaks the ``previous_hash`` linkage of every row that
followed — that's the tamper evidence Art. 12(1) requires.

In-memory backend rationale
---------------------------
The CodexAI store is durable (SQLite/Postgres + S3/R2 payload
locator). Here we keep the chain in process memory by default because
the competition harness is single-process and the chain doesn't need
to survive a restart — every batch starts with
``reset_evidence_store_for_tests()``. The bounded ``deque`` caps the
chain at ``REGENOLD_AUDIT_CAP`` entries (default 10 000) so a
long-running uvicorn doesn't leak memory.

Postgres backend
----------------
Activated only when ``DATABASE_URL`` is set to a ``postgresql://`` or
``postgres://`` DSN. The SQLAlchemy + asyncpg drivers are imported
**lazily inside** :meth:`PostgresAuditStore._setup`, so the module
loads cleanly even when those packages aren't installed (the
in-memory path needs zero external deps).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Iterator

from app.evidence.models import (
    ChainStatus,
    EvidenceEntry,
    EvidenceEntryType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AuditStore",
    "ChainStatus",
    "EvidenceEntry",
    "EvidenceEntryType",
    "InMemoryAuditStore",
    "PostgresAuditStore",
    "get_evidence_store",
    "reset_evidence_store_for_tests",
]


# Hard cap on the in-memory audit chain. The CodexAI AuditStore is
# durable (SQLite/Postgres); this in-memory store trades durability
# for simplicity. Without a cap, a long-running uvicorn process leaks
# memory for every chain entry. ``deque(maxlen=...)`` drops the oldest
# entry in O(1) when full so insertion stays cheap.
_DEFAULT_MAX_RECORDS = int(os.getenv("REGENOLD_AUDIT_CAP", "10000"))


# ─── Shared hash function ───────────────────────────────────────────────────


def _compute_data_hash(payload: dict[str, Any], previous_hash: str) -> str:
    """Compute the tamper-evident hash linking ``payload`` to ``previous_hash``.

    Byte-identical to the CodexAI :func:`_compute_data_hash` so an
    in-memory chain written here verifies cleanly against a replay of
    the CodexAI Postgres chain (or vice versa).

    The canonical JSON form sorts keys and stringifies non-JSON values
    with ``default=str`` so two payloads that round-trip through
    Python dicts in different insertion orders still produce the same
    digest.
    """
    canonical = json.dumps(
        {"payload": payload, "previous_hash": previous_hash},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _coerce_entry_type(entry_type: Any) -> str:
    """Normalise an ``EvidenceEntryType`` / str / Enum into its wire value.

    The CodexAI route passes :class:`EvidenceEntryType` instances; some
    test stubs pass raw strings. Both paths need to land as the
    canonical string so the SQL/in-memory column carries a stable
    value.
    """
    if isinstance(entry_type, EvidenceEntryType):
        return entry_type.value
    if hasattr(entry_type, "value"):
        return str(entry_type.value)
    return str(entry_type)


# ─── In-memory backend ──────────────────────────────────────────────────────


class InMemoryAuditStore:
    """Hash-chained audit store backed by a bounded in-process deque.

    Every ``record()`` call extends the chain with a fresh
    :class:`EvidenceEntry` whose ``data_hash`` is computed via
    :func:`_compute_data_hash` and whose ``previous_hash`` points at
    the prior tail's hash (empty string for the genesis entry). This
    is the same tamper-evidence model the CodexAI SQLite/Postgres
    stores use — only the storage substrate is different.

    The deque is process-local. Tests reset between batches via
    :func:`reset_evidence_store_for_tests`; production reads survive
    uvicorn worker lifetime but not a process restart, which is
    acceptable for a single-binary competition surface.

    Thread safety: every public method acquires ``_lock`` before
    touching ``_records`` so concurrent uvicorn handlers don't race on
    the tail-hash read between ``SELECT`` and ``INSERT``.
    """

    def __init__(self, *, max_records: int = _DEFAULT_MAX_RECORDS) -> None:
        self._records: deque[EvidenceEntry] = deque(maxlen=max_records)
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────

    def record(
        self,
        *,
        entry_type: Any,
        payload: dict[str, Any],
        article_ref: str = "",
        correlation_id: str | None = None,
        created_by: str = "system",
        tenant_id: str | None = None,
    ) -> EvidenceEntry:
        """Append an entry to the chain. Returns the freshly written row.

        Keyword-only signature mirrors :meth:`PostgresAuditStore.record`
        and the CodexAI :meth:`AuditStore.record`. The Regenold route
        relies on this calling convention.

        ``payload`` is shallow-copied to defend against a caller
        mutating the dict after the chain entry is written (which
        would break the recomputed hash on a future ``verify_chain``).
        """
        et = _coerce_entry_type(entry_type)
        # Pydantic enum coercion accepts the string value directly.
        try:
            et_enum = EvidenceEntryType(et)
        except ValueError:
            # Unknown entry-type — fall back to the route's own type
            # so the chain row is still well-formed. The CodexAI store
            # maps unknown rows to ``system_event``; we only ship
            # ``regenold_question`` so falling back to it preserves
            # type-safety without crashing the route.
            et_enum = EvidenceEntryType.regenold_question

        with self._lock:
            previous_hash = self._records[-1].data_hash if self._records else ""
            payload_copy = dict(payload)
            data_hash = _compute_data_hash(payload_copy, previous_hash)
            entry = EvidenceEntry(
                id=str(uuid.uuid4()),
                timestamp=_utc_now_iso(),
                entry_type=et_enum,
                data_hash=data_hash,
                previous_hash=previous_hash,
                payload=payload_copy,
                article_ref=article_ref,
                correlation_id=correlation_id or str(uuid.uuid4()),
                created_by=created_by,
                tenant_id=tenant_id,
            )
            self._records.append(entry)

        logger.debug(
            "evidence.record entry_type=%s tenant_id=%s article_ref=%s",
            et,
            tenant_id,
            article_ref,
        )
        return entry

    def get_chain(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
        entry_type: str | None = None,
        ascending: bool = False,
    ) -> Iterator[EvidenceEntry]:
        """Return entries (newest-first by default), optionally filtered.

        Mirrors the CodexAI ``AuditStore.get_chain`` contract: when
        ``tenant_id`` is ``None`` the caller receives every row;
        otherwise rows with a matching ``tenant_id`` OR tenant-neutral
        (``tenant_id is None``) only — this preserves visibility of
        shared/system events while preventing cross-tenant reads.

        Capped at ``limit`` rows. Returns an iterator so callers can
        ``list(...)`` it without an extra allocation in the hot path.
        """
        with self._lock:
            # Snapshot under the lock so concurrent writers can't
            # mutate the deque while we iterate.
            rows = list(self._records)

        if ascending:
            seq: list[EvidenceEntry] = rows
        else:
            seq = list(reversed(rows))

        filtered: list[EvidenceEntry] = []
        for row in seq:
            if entry_type is not None and row.entry_type.value != entry_type:
                continue
            if tenant_id is not None:
                # Tenant-scoped reads see their own rows + tenant-neutral ones.
                if row.tenant_id is not None and row.tenant_id != tenant_id:
                    continue
            filtered.append(row)
            if len(filtered) >= limit:
                break
        return iter(filtered)

    def count(self, *, tenant_id: str | None = None) -> int:
        """Count entries, optionally scoped to one tenant (+ tenant-neutral)."""
        with self._lock:
            if tenant_id is None:
                return len(self._records)
            return sum(
                1
                for r in self._records
                if r.tenant_id is None or r.tenant_id == tenant_id
            )

    def verify_chain(self) -> ChainStatus:
        """Recompute every hash and check linkage.

        Any mismatch indicates tampering or data corruption — returns
        a ``ChainStatus`` whose ``is_valid=False`` carries the index of
        the first broken entry. Empty chains are trivially valid.
        """
        with self._lock:
            rows = list(self._records)

        if not rows:
            return ChainStatus(
                is_valid=True,
                total_entries=0,
                verified_entries=0,
                message="Empty chain — nothing to verify",
            )

        prev_hash = ""
        for idx, row in enumerate(rows):
            if row.previous_hash != prev_hash:
                return ChainStatus(
                    is_valid=False,
                    total_entries=len(rows),
                    verified_entries=idx,
                    first_broken_at=idx,
                    message=(
                        f"Chain broken at entry {idx}: previous_hash mismatch"
                    ),
                )
            expected = _compute_data_hash(row.payload, prev_hash)
            if row.data_hash != expected:
                return ChainStatus(
                    is_valid=False,
                    total_entries=len(rows),
                    verified_entries=idx,
                    first_broken_at=idx,
                    message=(
                        f"Hash mismatch at entry {idx}: data has been modified"
                    ),
                )
            prev_hash = row.data_hash

        return ChainStatus(
            is_valid=True,
            total_entries=len(rows),
            verified_entries=len(rows),
            message="Chain integrity verified — all entries authentic",
        )


# ─── Postgres backend (optional) ────────────────────────────────────────────


class PostgresAuditStore:
    """Postgres-backed hash-chained audit store.

    Activated only when ``DATABASE_URL`` is set to a ``postgresql://``
    or ``postgres://`` DSN at :func:`get_evidence_store` time. The
    backend mirrors the CodexAI ``PostgresAuditStore`` wire shape so a
    future migration to the full enterprise store is a structurally-
    identical swap.

    SQLAlchemy + the Postgres driver are imported **lazily** inside
    :meth:`_setup` — this keeps ``import app.evidence.store`` working
    in environments where those packages aren't installed (the
    in-memory backend is the default and requires zero external
    deps). If the DSN is set but the driver imports fail, we log the
    fallback and return an :class:`InMemoryAuditStore` so the route
    keeps writing audit rows instead of blowing up at startup.

    Concurrency model: row-level ``SELECT ... FOR UPDATE`` on the tail
    row inside the INSERT transaction prevents two gunicorn workers
    from forking the chain (same model the CodexAI ``PostgresAuditStore``
    uses).
    """

    _SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS evidence_entries (
        id TEXT PRIMARY KEY,
        seq BIGSERIAL NOT NULL,
        timestamp TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        data_hash TEXT NOT NULL,
        previous_hash TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL,
        article_ref TEXT DEFAULT '',
        correlation_id TEXT NOT NULL,
        created_by TEXT DEFAULT 'system',
        tenant_id TEXT DEFAULT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_evidence_timestamp ON evidence_entries(timestamp);
    CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence_entries(entry_type);
    CREATE INDEX IF NOT EXISTS idx_evidence_correlation ON evidence_entries(correlation_id);
    CREATE INDEX IF NOT EXISTS idx_evidence_seq ON evidence_entries(seq);
    CREATE INDEX IF NOT EXISTS idx_evidence_tenant ON evidence_entries(tenant_id);
    """

    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url
        self._engine: Any | None = None
        self._lock = threading.Lock()

    def _setup(self) -> Any:
        """Lazily build the SQLAlchemy engine + ensure the schema exists.

        Imports happen here, NOT at module-load time, so the
        ``DATABASE_URL`` env var triggers the dependency chain only
        when a partner actually opts in. Without this, every
        deployment of this bundle would require ``sqlalchemy`` (and
        a Postgres driver) on the install line, which contradicts the
        "zero-dependency competition harness" design.

        URL normalisation handled here:

        * Railway / Heroku-style ``postgres://`` → ``postgresql://``
          (SQLAlchemy 2 drops the legacy bare ``postgres`` scheme).
        * Bare ``postgresql://`` → ``postgresql+psycopg://`` so the
          v3 driver from ``requirements.txt`` is selected. SQLAlchemy
          2 defaults to ``psycopg2``, which we don't ship.

        Pool sizing: ``pool_pre_ping=True`` survives Railway's idle
        connection reaper; small pool to play nice with their
        ``max_connections`` budget on the free tier.
        """
        if self._engine is not None:
            return self._engine
        from sqlalchemy import create_engine  # noqa: PLC0415 — lazy
        from sqlalchemy import text  # noqa: PLC0415 — lazy

        url = self._database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
            url = "postgresql+psycopg://" + url[len("postgresql://"):]

        engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        with engine.begin() as conn:
            for stmt in self._SCHEMA_SQL.strip().split(";"):
                if stmt.strip():
                    conn.execute(text(stmt))
        self._engine = engine
        return engine

    def record(
        self,
        *,
        entry_type: Any,
        payload: dict[str, Any],
        article_ref: str = "",
        correlation_id: str | None = None,
        created_by: str = "system",
        tenant_id: str | None = None,
    ) -> EvidenceEntry:
        """Append an entry to the chain with row-level locking."""
        from sqlalchemy import text  # noqa: PLC0415 — lazy

        engine = self._setup()
        et = _coerce_entry_type(entry_type)
        try:
            et_enum = EvidenceEntryType(et)
        except ValueError:
            et_enum = EvidenceEntryType.regenold_question

        payload_copy = dict(payload)
        with self._lock:
            with engine.begin() as conn:
                row = conn.execute(
                    text(
                        "SELECT data_hash FROM evidence_entries "
                        "ORDER BY seq DESC LIMIT 1 FOR UPDATE"
                    )
                ).fetchone()
                previous_hash = row[0] if row else ""
                data_hash = _compute_data_hash(payload_copy, previous_hash)
                entry = EvidenceEntry(
                    id=str(uuid.uuid4()),
                    timestamp=_utc_now_iso(),
                    entry_type=et_enum,
                    data_hash=data_hash,
                    previous_hash=previous_hash,
                    payload=payload_copy,
                    article_ref=article_ref,
                    correlation_id=correlation_id or str(uuid.uuid4()),
                    created_by=created_by,
                    tenant_id=tenant_id,
                )
                conn.execute(
                    text(
                        "INSERT INTO evidence_entries "
                        "(id, timestamp, entry_type, data_hash, previous_hash, "
                        " payload_json, article_ref, correlation_id, created_by, tenant_id) "
                        "VALUES (:id, :timestamp, :entry_type, :data_hash, "
                        "        :previous_hash, :payload_json, :article_ref, "
                        "        :correlation_id, :created_by, :tenant_id)"
                    ),
                    {
                        "id": entry.id,
                        "timestamp": entry.timestamp,
                        "entry_type": entry.entry_type.value,
                        "data_hash": entry.data_hash,
                        "previous_hash": entry.previous_hash,
                        "payload_json": json.dumps(payload_copy, default=str),
                        "article_ref": entry.article_ref,
                        "correlation_id": entry.correlation_id,
                        "created_by": entry.created_by,
                        "tenant_id": entry.tenant_id,
                    },
                )
        return entry

    def get_chain(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
        entry_type: str | None = None,
        ascending: bool = False,
    ) -> Iterator[EvidenceEntry]:
        """Return entries from the Postgres chain, newest-first by default."""
        from sqlalchemy import text  # noqa: PLC0415 — lazy

        engine = self._setup()
        order = "ASC" if ascending else "DESC"
        where_parts: list[str] = []
        params: dict[str, Any] = {"limit": int(limit)}
        if entry_type is not None:
            where_parts.append("entry_type = :entry_type")
            params["entry_type"] = entry_type
        if tenant_id is not None:
            where_parts.append("(tenant_id = :tenant_id OR tenant_id IS NULL)")
            params["tenant_id"] = tenant_id
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        # ``order`` is always one of two literal strings, never user input.
        sql = (
            f"SELECT id, timestamp, entry_type, data_hash, previous_hash, "
            f"       payload_json, article_ref, correlation_id, created_by, "
            f"       tenant_id "
            f"FROM evidence_entries {where_sql} "
            f"ORDER BY seq {order} LIMIT :limit"
        )
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        entries: list[EvidenceEntry] = []
        for row in rows:
            try:
                payload = json.loads(row[5]) if row[5] else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}
            try:
                et_enum = EvidenceEntryType(row[2])
            except ValueError:
                et_enum = EvidenceEntryType.regenold_question
            entries.append(
                EvidenceEntry(
                    id=row[0],
                    timestamp=row[1],
                    entry_type=et_enum,
                    data_hash=row[3],
                    previous_hash=row[4],
                    payload=payload,
                    article_ref=row[6] or "",
                    correlation_id=row[7],
                    created_by=row[8] or "system",
                    tenant_id=row[9],
                )
            )
        return iter(entries)

    def count(self, *, tenant_id: str | None = None) -> int:
        from sqlalchemy import text  # noqa: PLC0415 — lazy

        engine = self._setup()
        if tenant_id is None:
            sql = "SELECT COUNT(*) FROM evidence_entries"
            params: dict[str, Any] = {}
        else:
            sql = (
                "SELECT COUNT(*) FROM evidence_entries "
                "WHERE tenant_id = :tenant_id OR tenant_id IS NULL"
            )
            params = {"tenant_id": tenant_id}
        with engine.connect() as conn:
            return int(conn.execute(text(sql), params).scalar() or 0)

    def verify_chain(self) -> ChainStatus:
        """Walk the chain in ascending seq order and recompute every hash."""
        from sqlalchemy import text  # noqa: PLC0415 — lazy

        engine = self._setup()
        with engine.connect() as conn:
            total = int(
                conn.execute(text("SELECT COUNT(*) FROM evidence_entries")).scalar() or 0
            )
            if total == 0:
                return ChainStatus(
                    is_valid=True,
                    total_entries=0,
                    verified_entries=0,
                    message="Empty chain — nothing to verify",
                )
            rows = conn.execute(
                text(
                    "SELECT data_hash, previous_hash, payload_json "
                    "FROM evidence_entries ORDER BY seq ASC"
                )
            ).fetchall()

        prev_hash = ""
        for idx, row in enumerate(rows):
            data_hash, previous_hash, payload_json = row[0], row[1], row[2]
            if previous_hash != prev_hash:
                return ChainStatus(
                    is_valid=False,
                    total_entries=total,
                    verified_entries=idx,
                    first_broken_at=idx,
                    message=f"Chain broken at entry {idx}: previous_hash mismatch",
                )
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}
            expected = _compute_data_hash(payload, prev_hash)
            if data_hash != expected:
                return ChainStatus(
                    is_valid=False,
                    total_entries=total,
                    verified_entries=idx,
                    first_broken_at=idx,
                    message=f"Hash mismatch at entry {idx}: data has been modified",
                )
            prev_hash = data_hash
        return ChainStatus(
            is_valid=True,
            total_entries=total,
            verified_entries=total,
            message="Chain integrity verified — all entries authentic",
        )


# ─── Type alias for back-compat ─────────────────────────────────────────────

# The CodexAI parent re-exports ``AuditStore`` as the public class
# name. Keeping the alias here means a future call site that imports
# ``AuditStore`` from this module (e.g. an evidence-export helper port)
# binds to the same in-memory implementation without a code change.
AuditStore = InMemoryAuditStore


# ─── Singleton accessor + reset hook ────────────────────────────────────────


_SINGLETON: Any | None = None
_SINGLETON_LOCK = threading.Lock()


def _select_backend() -> Any:
    """Pick the backend at first-call time based on env state.

    Resolution order:
      1. ``DATABASE_URL=postgres(ql)?://...`` → :class:`PostgresAuditStore`.
         If SQLAlchemy import fails, fall back to in-memory with a
         debug log — we never want the route to lose audit writes
         because of a missing dep.
      2. Anything else → :class:`InMemoryAuditStore`.

    The env var is read once per ``reset_evidence_store_for_tests``
    cycle. Tests that want to flip backends per case can set the env
    var and call the reset hook.
    """
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn and (dsn.startswith("postgres://") or dsn.startswith("postgresql://")):
        try:
            # Probe-import: don't actually open the connection here
            # (that happens lazily on the first record/read), but verify
            # the driver is available so we can fall back gracefully.
            import sqlalchemy  # noqa: F401, PLC0415 — probe only

            return PostgresAuditStore(database_url=dsn)
        except ImportError as exc:
            logger.debug(
                "evidence.postgres_unavailable falling back to in-memory: %s",
                exc,
            )
    return InMemoryAuditStore()


def get_evidence_store() -> Any:
    """Return the process-wide audit store (in-memory by default).

    First call latches the backend choice; subsequent calls return
    the same singleton. Reset via
    :func:`reset_evidence_store_for_tests` to re-read environment
    (used by test fixtures + eval-runner batches).
    """
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:  # double-checked locking
                _SINGLETON = _select_backend()
    return _SINGLETON


def reset_evidence_store_for_tests() -> Any:
    """Drop the singleton and rebuild it from a fresh env read.

    Tests + eval runners call this between batches to keep the chain
    bounded and re-resolve the backend after env-var changes. Returns
    the new instance so callers can ``store = reset_...()`` in a
    fixture if they want a typed reference.
    """
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = _select_backend()
    return _SINGLETON
