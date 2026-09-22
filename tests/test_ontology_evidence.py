from __future__ import annotations

import pytest

from app.data.ontology_evidence import (
    OntologyEvidence,
    OntologyLayer,
    OntologyPatchProposal,
)


@pytest.fixture
def evidence() -> OntologyEvidence:
    return OntologyEvidence(
        source_id="eurlex:32024R1689",
        source_version="2024.1689.v18",
        locator="Article 14(4)(a)",
        quote="Human oversight shall enable...",
        content_hash="sha256:abc123",
    )


def test_evidence_requires_complete_provenance() -> None:
    with pytest.raises(ValueError, match="source, locator"):
        OntologyEvidence("", "v1", "Article 14", "quote", "sha256:x")


def test_patch_is_typed_and_evidence_bearing(evidence: OntologyEvidence) -> None:
    proposal = OntologyPatchProposal(
        proposal_id="r441-content-001",
        parent_snapshot="kb:2024.1689.v18",
        target_ids=("role:provider", "article:14"),
        layer=OntologyLayer.CONTENT,
        hypothesis="Adding the missing oversight condition restores the guarded criterion.",
        evidence=(evidence,),
    )
    assert proposal.layer is OntologyLayer.CONTENT
    # R442 — the key carries the source VERSION (its docstring always said so):
    # without it the same locator in two versions of the Act collapsed to one.
    assert proposal.evidence_keys == (
        ("eurlex:32024R1689", "2024.1689.v18", "Article 14(4)(a)"),
    )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"evidence": ()}, "supporting evidence"),
        ({"hypothesis": ""}, "falsifiable hypothesis"),
        ({"target_ids": ()}, "target ids"),
    ],
)
def test_patch_rejects_unreviewable_proposals(
    evidence: OntologyEvidence, kwargs: dict[str, object], message: str
) -> None:
    base: dict[str, object] = {
        "proposal_id": "p1",
        "parent_snapshot": "s1",
        "target_ids": ("article:14",),
        "layer": OntologyLayer.CONTENT,
        "hypothesis": "a testable change",
        "evidence": (evidence,),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        OntologyPatchProposal(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"target_ids": "article:14"}, "target ids"),  # a bare str iterated as chars
        ({"target_ids": ["article:14"]}, "target ids"),  # a list made it unhashable
        ({"layer": "bogus"}, "OntologyLayer"),
        ({"evidence": ("not evidence",)}, "tuple of OntologyEvidence"),
    ],
)
def test_patch_rejects_mistyped_fields(
    evidence: OntologyEvidence, kwargs: dict[str, object], message: str
) -> None:
    """R442 — each of these was accepted and failed later, or silently."""
    base: dict[str, object] = {
        "proposal_id": "p1",
        "parent_snapshot": "s1",
        "target_ids": ("article:14",),
        "layer": OntologyLayer.CONTENT,
        "hypothesis": "a testable change",
        "evidence": (evidence,),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        OntologyPatchProposal(**base)  # type: ignore[arg-type]


def test_a_valid_layer_string_is_coerced(evidence: OntologyEvidence) -> None:
    proposal = OntologyPatchProposal(
        "p1", "s1", ("article:14",), "schema", "a testable change", (evidence,),  # type: ignore[arg-type]
    )
    assert proposal.layer is OntologyLayer.SCHEMA
    assert hash(proposal)  # frozen + tuple fields: usable as a ledger key
