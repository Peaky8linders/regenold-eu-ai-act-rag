"""Persistence for benchmark runs — JSON + SQLite + audit chain.

Three durability tiers, written on every run:

1. **JSON sidecar** — ``evals/bench/results/<label>.json``. Always
   written. Human-readable, diffable, the canonical reference.

2. **SQLite ledger** — ``evals/bench/results/ledger.sqlite``. Always
   written. Stores one row per run + one row per scored item so an
   operator can ``SELECT axis, AVG(score) FROM bench_items GROUP BY
   run_id`` for trend analysis without parsing 8x JSON files.

3. **Audit chain** — `get_evidence_store()`. Postgres when
   ``DATABASE_URL`` is set, else in-memory. Stores the summary blob
   only (not the per-item rows; the JSON sidecar is the source of
   truth for those, and the chain payload should be small enough to
   live in a single row).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evidence.store import (
    EvidenceEntryType,
    get_evidence_store,
)

RESULTS_DIR = Path(__file__).parent / "results"
LEDGER_PATH = RESULTS_DIR / "ledger.sqlite"

_TENANT_ID = "partner:regenold"


_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS bench_runs (
        id TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        qa_pairs_sha256 TEXT,
        scenarios_sha256 TEXT,
        n_qa INTEGER,
        n_scenarios INTEGER,
        summary_json TEXT NOT NULL,
        chain_entry_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bench_items (
        run_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        source TEXT NOT NULL,
        ans_correctness_loose REAL,
        ans_correctness_strict REAL,
        ans_conciseness REAL,
        ref_correctness_loose REAL,
        ref_correctness_strict REAL,
        ref_conciseness REAL,
        regulatory_tone REAL,
        latency_ms REAL,
        pred_answer TEXT,
        pred_refs_json TEXT,
        gold_answer TEXT,
        gold_articles_json TEXT,
        PRIMARY KEY (run_id, item_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bench_runs_label ON bench_runs(label)",
    "CREATE INDEX IF NOT EXISTS idx_bench_items_source ON bench_items(source)",
)


def _ensure_schema() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LEDGER_PATH, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for stmt in _SCHEMA_SQL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json_sidecar(label: str, payload: dict[str, Any]) -> Path:
    """Write the full benchmark payload to ``results/<label>.json``."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Slug the label so an operator-supplied label like "post-fix v2" doesn't
    # produce a problematic path. Keep alnum + hyphens only.
    slug = "".join(c if c.isalnum() or c in "._-" else "_" for c in label)
    out = RESULTS_DIR / f"{slug}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out


def write_sqlite_ledger(payload: dict[str, Any]) -> str:
    """Append the run + per-item rows to the durable SQLite ledger.

    Returns the run_id (uuid4) for cross-referencing with the audit
    chain entry.
    """
    _ensure_schema()
    run_id = payload.get("run_id") or str(uuid.uuid4())
    summary = payload.get("summary") or {}
    fingerprint = payload.get("dataset_fingerprint") or {}

    conn = sqlite3.connect(LEDGER_PATH, timeout=10.0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR REPLACE INTO bench_runs "
            "(id, label, started_at, finished_at, qa_pairs_sha256, "
            " scenarios_sha256, n_qa, n_scenarios, summary_json, chain_entry_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                payload.get("label", "adhoc"),
                payload.get("started_at", _now_iso()),
                payload.get("finished_at", _now_iso()),
                fingerprint.get("qa_pairs_sha256"),
                fingerprint.get("scenarios_sha256"),
                int((summary.get("qa") or {}).get("n", 0)),
                int((summary.get("scenarios") or {}).get("n", 0)),
                json.dumps(summary, default=str),
                payload.get("chain_entry_id"),
            ),
        )
        for source in ("qa", "scenarios"):
            for row in payload.get(source, []):
                conn.execute(
                    "INSERT OR REPLACE INTO bench_items "
                    "(run_id, item_id, source, "
                    " ans_correctness_loose, ans_correctness_strict, "
                    " ans_conciseness, ref_correctness_loose, "
                    " ref_correctness_strict, ref_conciseness, "
                    " regulatory_tone, latency_ms, "
                    " pred_answer, pred_refs_json, gold_answer, gold_articles_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        row.get("item_id", ""),
                        source,
                        row.get("scores", {}).get("ans_correctness_loose"),
                        row.get("scores", {}).get("ans_correctness_strict"),
                        row.get("scores", {}).get("ans_conciseness"),
                        row.get("scores", {}).get("ref_correctness_loose"),
                        row.get("scores", {}).get("ref_correctness_strict"),
                        row.get("scores", {}).get("ref_conciseness"),
                        row.get("scores", {}).get("regulatory_tone"),
                        row.get("scores", {}).get("latency_ms"),
                        (row.get("pred_answer") or "")[:2000],
                        json.dumps(row.get("pred_refs") or []),
                        (row.get("gold_answer") or "")[:2000],
                        json.dumps(row.get("gold_articles")),
                    ),
                )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return run_id


def write_audit_chain(payload: dict[str, Any]) -> str:
    """Append a single benchmark_run row to the audit chain.

    Returns the chain entry id so the caller can cross-reference it
    from the SQLite ledger row.
    """
    store = get_evidence_store()
    summary = payload.get("summary") or {}
    fingerprint = payload.get("dataset_fingerprint") or {}
    chain_payload = {
        "kind": "benchmark_run",
        "label": payload.get("label", "adhoc"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "dataset_fingerprint": fingerprint,
        "summary": summary,
    }
    entry = store.record(
        entry_type=EvidenceEntryType.benchmark_run,
        payload=chain_payload,
        article_ref="",
        created_by="evals.bench.runner",
        tenant_id=_TENANT_ID,
    )
    return entry.id


def persist(payload: dict[str, Any]) -> dict[str, Any]:
    """Top-level persistence — JSON + SQLite + audit chain.

    Returns the original payload mutated with ``run_id`` and
    ``chain_entry_id`` set, plus the JSON sidecar path.
    """
    label = payload.get("label", "adhoc")
    # Order: audit chain first (so the chain_entry_id can be stored in
    # the ledger row); SQLite ledger second; JSON sidecar last (so the
    # human-readable file carries every cross-reference id).
    try:
        chain_entry_id = write_audit_chain(payload)
        payload["chain_entry_id"] = chain_entry_id
    except Exception as exc:  # noqa: BLE001 — chain write is best-effort
        payload["chain_entry_id"] = None
        payload["chain_write_error"] = str(exc)

    run_id = write_sqlite_ledger(payload)
    payload["run_id"] = run_id
    sidecar = write_json_sidecar(label, payload)
    payload["sidecar_path"] = str(sidecar)
    return payload
