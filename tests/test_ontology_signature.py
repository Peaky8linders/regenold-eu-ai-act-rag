from __future__ import annotations

from pathlib import Path

from app.data.ontology_signature import (
    ONTOLOGY_SIGNATURE_VERSION,
    ontology_signature,
    ontology_signature_payload,
    semantic_digest,
)

_SNAPSHOT = Path(__file__).parent / "_snapshots" / "ontology_signature.txt"


def test_ontology_signature_is_stable_and_pinned() -> None:
    expected_version, sep, expected_digest = _SNAPSHOT.read_text(encoding="utf-8").strip().partition("::")
    assert sep == "::"
    assert expected_version == ONTOLOGY_SIGNATURE_VERSION
    assert ontology_signature() == expected_digest


def test_semantic_digest_detects_content_changes_even_when_counts_do_not_change() -> None:
    payload = {"practice": {"description": "original"}, "registry_count": 1}
    changed = {"practice": {"description": "edited"}, "registry_count": 1}
    assert semantic_digest(payload) != semantic_digest(changed)


def test_signature_covers_core_ontology_coordinates_and_provenance() -> None:
    payload = ontology_signature_payload()
    assert set(payload) == {
        "signature_version",
        "ontology",
        "role_duties",
        "legal_coordinates",
        "source",
        "evidence_contract",
    }
    assert payload["legal_coordinates"]["heads"]
    assert payload["legal_coordinates"]["paragraphs"]
    assert payload["legal_coordinates"]["points"]
    assert payload["source"]["sha256"]
    assert "content_hash" in payload["evidence_contract"]["evidence_fields"]
