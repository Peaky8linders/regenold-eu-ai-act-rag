"""Tests for the SQLite audit backend — stdlib sqlite3 path.

The backend activates when ``DATABASE_URL=sqlite://...`` is set.
These tests pin the contract: hash-chain integrity, full Q+A payload
retention, tenant scoping, durability across reset, and tamper
detection.
"""

from __future__ import annotations

import os

import pytest

from app.evidence.models import EvidenceEntryType
from app.evidence.store import (
    SQLiteAuditStore,
    _select_backend,
    _sqlite_path_from_url,
    reset_evidence_store_for_tests,
)


# ─── URL parsing ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite://", ":memory:"),
        ("sqlite:///", ":memory:"),
        ("sqlite:///./audit.db", "./audit.db"),
        ("sqlite:///regenold_audit.db", "regenold_audit.db"),
        ("sqlite:////app/data/audit.db", "/app/data/audit.db"),
    ],
)
def test_url_parsing(url, expected) -> None:
    assert _sqlite_path_from_url(url) == expected


# ─── Backend selection ───────────────────────────────────────────────────────


def test_sqlite_url_selects_sqlite_backend(monkeypatch, tmp_path) -> None:
    db_file = tmp_path / "audit.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    reset_evidence_store_for_tests()
    backend = _select_backend()
    assert isinstance(backend, SQLiteAuditStore)
    assert backend._db_path == str(db_file)


def test_in_memory_default_when_no_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_evidence_store_for_tests()
    backend = _select_backend()
    assert backend.__class__.__name__ == "InMemoryAuditStore"


# ─── Hash chain semantics ────────────────────────────────────────────────────


def _store(tmp_path) -> SQLiteAuditStore:
    return SQLiteAuditStore(db_path=str(tmp_path / "chain.db"))


def test_record_creates_genesis_with_empty_previous_hash(tmp_path) -> None:
    store = _store(tmp_path)
    entry = store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": "What is Art. 5?", "answer": "Prohibited practices."},
        tenant_id="partner:regenold",
    )
    assert entry.previous_hash == ""
    assert len(entry.data_hash) == 64  # sha256 hex
    assert entry.payload["question"] == "What is Art. 5?"
    assert entry.payload["answer"] == "Prohibited practices."


def test_chain_links_consecutive_entries(tmp_path) -> None:
    store = _store(tmp_path)
    e1 = store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": "Q1", "answer": "A1"},
    )
    e2 = store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": "Q2", "answer": "A2"},
    )
    assert e2.previous_hash == e1.data_hash


def test_chain_integrity_passes_on_clean_chain(tmp_path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        store.record(
            entry_type=EvidenceEntryType.regenold_question,
            payload={"question": f"Q{i}", "answer": f"A{i}"},
        )
    status = store.verify_chain()
    assert status.is_valid is True
    assert status.total_entries == 5
    assert status.verified_entries == 5


def test_chain_integrity_detects_tampered_payload(tmp_path) -> None:
    store = _store(tmp_path)
    for i in range(3):
        store.record(
            entry_type=EvidenceEntryType.regenold_question,
            payload={"question": f"Q{i}", "answer": f"A{i}"},
        )
    # Tamper with row 2 directly via raw SQL.
    import sqlite3

    conn = sqlite3.connect(store._db_path)
    try:
        conn.execute(
            "UPDATE evidence_entries SET payload_json = ? WHERE seq = 2",
            ('{"question":"TAMPERED","answer":"x"}',),
        )
        conn.commit()
    finally:
        conn.close()
    status = store.verify_chain()
    assert status.is_valid is False
    # Row at seq=2 is index 1 (0-indexed).
    assert status.first_broken_at == 1


# ─── Q+A payload retention ───────────────────────────────────────────────────


def test_full_question_and_answer_round_trip_through_sqlite(tmp_path) -> None:
    store = _store(tmp_path)
    q = "What does Article 13(1)(a) require? " * 10  # 350 chars
    a = "Article 13 requires providers of high-risk AI systems to publish clear and complete instructions for use that include the deployer's intended purpose, the level of accuracy expected, foreseeable misuse modes, and oversight mechanisms."
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": q, "answer": a, "references": ["Article 13"]},
        tenant_id="partner:regenold",
    )
    rows = list(store.get_chain(tenant_id="partner:regenold"))
    assert len(rows) == 1
    assert rows[0].payload["question"] == q
    assert rows[0].payload["answer"] == a
    assert rows[0].payload["references"] == ["Article 13"]


# ─── Tenant scoping ──────────────────────────────────────────────────────────


def test_tenant_scoped_get_chain(tmp_path) -> None:
    store = _store(tmp_path)
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": "p_q", "answer": "p_a"},
        tenant_id="partner:regenold",
    )
    store.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": "a_q", "answer": "a_a"},
        tenant_id="public:regenold-anon",
    )
    partner_rows = list(store.get_chain(tenant_id="partner:regenold"))
    anon_rows = list(store.get_chain(tenant_id="public:regenold-anon"))
    all_rows = list(store.get_chain(tenant_id=None))
    assert len(partner_rows) == 1
    assert partner_rows[0].payload["question"] == "p_q"
    assert len(anon_rows) == 1
    assert anon_rows[0].payload["question"] == "a_q"
    assert len(all_rows) == 2


# ─── Durability ──────────────────────────────────────────────────────────────


def test_chain_survives_store_reopen(tmp_path) -> None:
    db = str(tmp_path / "durable.db")
    s1 = SQLiteAuditStore(db_path=db)
    s1.record(
        entry_type=EvidenceEntryType.regenold_question,
        payload={"question": "persisted_q", "answer": "persisted_a"},
        tenant_id="partner:regenold",
    )
    # Reopen — simulates a process restart.
    s2 = SQLiteAuditStore(db_path=db)
    rows = list(s2.get_chain(tenant_id="partner:regenold"))
    assert len(rows) == 1
    assert rows[0].payload["question"] == "persisted_q"
    status = s2.verify_chain()
    assert status.is_valid is True
