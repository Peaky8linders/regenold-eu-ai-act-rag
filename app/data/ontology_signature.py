"""Stable semantic fingerprint for the offline ontology and evidence surface.

The legacy KB snapshot covers only ``EC_CHECKER_OBLIGATION_MAP``. This module
adds a separate fingerprint for the typed ontology and its legal coordinate
inventory, including role obligations, source provenance pins and the evidence
proposal schema. It is tooling-only: computing the signature is explicit and
has no request-path caller.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, fields, is_dataclass
from datetime import date
from enum import Enum

from app.data import ontology
from app.data import role_obligations as role_duties
from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.official_eu_ai_act import (
    OFFICIAL_ARTICLE_TEXT,
    OFFICIAL_CONSOLIDATION_NOTE,
    OFFICIAL_FETCH_DATE,
    OFFICIAL_SHA256,
    OFFICIAL_SOURCE_URL,
)
from app.data.ontology_evidence import OntologyEvidence, OntologyLayer, OntologyPatchProposal
from app.data.provision_coordinates import POINT_COORDINATES, PROVISION_COORDINATES
from app.data.provision_hierarchy import build_hierarchy_payload

ONTOLOGY_SIGNATURE_VERSION = "2024.1689.v1"


def _canonical_value(value: object) -> object:
    """Convert supported ontology values into deterministic JSON data."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        entries = sorted(value.items(), key=lambda item: str(_canonical_value(item[0])))
        return {str(_canonical_value(key)): _canonical_value(item) for key, item in entries}
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical_value(item) for item in value), key=repr)
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported ontology signature value: {type(value).__name__}")


def ontology_signature_payload() -> dict[str, object]:
    """Return the canonical semantic inputs covered by this snapshot."""
    hierarchy = build_hierarchy_payload()
    subpoint_coordinates: set[str] = set()
    for node in hierarchy.subpoint_nodes:
        node_id = str(node["id"])
        if node_id.startswith("article_"):
            subpoint_coordinates.add(
                "Article " + ".".join(node_id[len("article_"):].split("_"))
            )
        elif node_id.startswith("annex_"):
            subpoint_coordinates.add(
                "Annex " + ".".join(node_id[len("annex_"):].split("_"))
            )

    return {
        "signature_version": ONTOLOGY_SIGNATURE_VERSION,
        "ontology": {
            "actor_roles": {
                name: role.value for name, role in ontology.ActorRole.__members__.items()
            },
            "risk_classes": {
                name: risk.value for name, risk in ontology.RiskClass.__members__.items()
            },
            "practices": ontology.PRACTICE_REGISTRY,
            "annex_iii_categories": ontology.ANNEX_III_REGISTRY,
            "phases": ontology.PHASE_REGISTRY,
            "role_risk_obligations": ontology.ROLE_OBLIGATIONS,
        },
        "role_duties": {
            "version": role_duties.ROLE_OBLIGATIONS_VERSION,
            "entries": role_duties.ROLE_OBLIGATIONS,
        },
        "legal_coordinates": {
            "heads": ARTICLE_EXISTENCE,
            "paragraphs": PROVISION_COORDINATES,
            "points": POINT_COORDINATES,
            "nested_points": subpoint_coordinates,
        },
        "source": {
            "url": OFFICIAL_SOURCE_URL,
            "sha256": OFFICIAL_SHA256,
            "fetch_date": OFFICIAL_FETCH_DATE,
            "consolidation_note": OFFICIAL_CONSOLIDATION_NOTE,
            "adopted_text": OFFICIAL_ARTICLE_TEXT,
        },
        "evidence_contract": {
            "evidence_fields": [item.name for item in fields(OntologyEvidence)],
            "proposal_fields": [item.name for item in fields(OntologyPatchProposal)],
            "layers": [layer.value for layer in OntologyLayer],
        },
    }


def semantic_digest(payload: Mapping[str, object]) -> str:
    """SHA-256 of canonical JSON; useful for focused mutation-sensitivity tests."""
    canonical = json.dumps(
        _canonical_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ontology_signature() -> str:
    """Compute the current versioned semantic fingerprint."""
    return semantic_digest(ontology_signature_payload())


__all__ = [
    "ONTOLOGY_SIGNATURE_VERSION",
    "ontology_signature_payload",
    "semantic_digest",
    "ontology_signature",
]
