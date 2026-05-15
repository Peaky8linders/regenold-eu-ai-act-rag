"""Evidence-chain models — scoped subset of the CodexAI catalog.

This bundle ships only the audit-chain primitives the Regenold route
needs:

* :class:`EvidenceEntryType` — the closed-vocabulary of entry-type
  strings written on the chain. The full CodexAI catalog covers ~50
  entry types across the platform; we keep the **Q&A endpoint slice**
  here (everything the in-memory chain plus the route may emit) and
  intentionally skip enterprise-only types (GDPR DSAR/Art. 17 erasure,
  Stripe lifecycle, Agent Passport, SOC 2 MFA, document-package
  evidence, governance/RAI/security-hub) since none of them apply to
  a Q&A endpoint.
* :class:`EvidenceEntry` — the typed shape of a row on the chain.
  Mirrors the CodexAI :class:`app.evidence.models.EvidenceEntry`
  surface (id, timestamp, entry_type, data_hash, previous_hash,
  payload, article_ref, correlation_id, created_by, tenant_id).
* :class:`ChainStatus` — the result of a chain-integrity verification
  pass (used by ``AuditStore.verify_chain``).

Keeping these as Pydantic models (rather than dataclasses) gives us
zero-cost serialisation on the audit endpoints and matches the
CodexAI wire shape so a future migration to the full store is a
schema-compatible swap.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format with Z suffix.

    Inlined here (instead of imported from ``app.utils``) so the
    evidence module has no cross-module runtime dependencies — keeps
    the audit chain importable even if other parts of the app are
    half-loaded (e.g. during test collection).
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EvidenceEntryType(str, Enum):
    """Closed vocabulary of evidence-chain entry types.

    Only the entry types the Regenold Q&A route may emit are listed.
    The CodexAI parent repo carries the full ~50-member catalog;
    porting them here without the matching call sites would be dead
    code that drifts on the next regenerate cycle.
    """

    # Partner integration — Regenold EU AI Act ask endpoint. Written on
    # every /api/v1/regenold/eu-ai-act/ask call with a question hash +
    # citation refs (never raw partner key; answer excerpt is capped).
    # Tenant bucket is "partner:regenold" so the chain stays separated
    # from any future tenant buckets.
    regenold_question = "regenold_question"

    # Reproducible-benchmark run. Written once per
    # ``evals.bench.runner`` invocation with a summary blob (per-axis
    # means, latency percentiles, dataset SHA-pin) so the audit chain
    # carries every benchmark score the system has ever produced. The
    # tenant bucket is ``"partner:regenold"`` so a chain restored from
    # backup keeps the benchmark history alongside the live partner
    # queries.
    benchmark_run = "benchmark_run"


class EvidenceEntry(BaseModel):
    """A single evidence-chain entry with hash linkage for tamper resistance.

    ``tenant_id`` identifies whose data this entry belongs to. For the
    Regenold endpoint this is always ``"partner:regenold"``. The hash
    chain itself is global — chain-integrity verification is not
    per-tenant, and the ``previous_hash`` linkage spans every entry
    regardless of tenant.

    ``created_by`` identifies what performed the write (route name,
    "system" for automated events). It is deliberately separate from
    ``tenant_id``: a future scheduled-sweep job would run as
    "system" on behalf of the partner tenant.

    Fields kept compatible with the CodexAI ``EvidenceEntry`` shape so
    a future migration to the full store is a structurally-identical
    swap.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=_utc_now_iso)
    entry_type: EvidenceEntryType
    data_hash: str = ""
    previous_hash: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    article_ref: str = ""
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_by: str = "system"
    tenant_id: str | None = None


class ChainStatus(BaseModel):
    """Result of an evidence-chain integrity verification pass."""

    is_valid: bool
    total_entries: int
    verified_entries: int
    first_broken_at: int | None = None
    message: str
