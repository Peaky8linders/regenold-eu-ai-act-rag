"""Evidence-bearing ontology records for offline, gated evolution work.

This module is deliberately not on the request path.  It provides the small
contract missing from the current registries: a proposed semantic mapping must
identify its source evidence, its parent snapshot, and the one layer it intends
to change.  A later gate can persist these records without allowing an LLM to
mutate the legal ontology directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OntologyLayer(StrEnum):
    """The only independently editable levels in an evolution proposal."""

    CONTENT = "content"
    TOOL = "tool"
    SCHEMA = "schema"


@dataclass(frozen=True, slots=True)
class OntologyEvidence:
    """A precise, versioned source supporting one ontology claim."""

    source_id: str
    source_version: str
    locator: str
    quote: str
    content_hash: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.source_id,
                self.source_version,
                self.locator,
                self.quote,
                self.content_hash,
            )
        ):
            raise ValueError("ontology evidence requires source, locator, quote, and hash")


@dataclass(frozen=True, slots=True)
class OntologyPatchProposal:
    """A reviewable candidate patch; it is not an applied ontology mutation."""

    proposal_id: str
    parent_snapshot: str
    target_ids: tuple[str, ...]
    layer: OntologyLayer
    hypothesis: str
    evidence: tuple[OntologyEvidence, ...]

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.parent_snapshot.strip():
            raise ValueError("ontology proposals require an id and parent snapshot")
        # R442 — a bare string is iterable, so ``target_ids="article:14"`` used
        # to pass as ten one-character targets; a list made the record unhashable.
        if (
            not isinstance(self.target_ids, tuple)
            or not self.target_ids
            or any(not isinstance(t, str) or not t.strip() for t in self.target_ids)
        ):
            raise ValueError("ontology proposals require non-empty target ids")
        # ``layer="bogus"`` was accepted; a valid string value is coerced.
        object.__setattr__(self, "layer", OntologyLayer(self.layer))
        if not self.hypothesis.strip():
            raise ValueError("ontology proposals require a falsifiable hypothesis")
        if not self.evidence:
            raise ValueError("legal ontology proposals require supporting evidence")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, OntologyEvidence) for item in self.evidence
        ):
            raise ValueError("ontology proposal evidence must be a tuple of OntologyEvidence")

    @property
    def evidence_keys(self) -> tuple[tuple[str, str, str], ...]:
        """Stable ``(source, version, locator)`` keys for audit and deduplication.

        R442 — the version was left out, so the same locator in two versions of
        a source collapsed to one key, defeating the audit this exists for.
        """

        return tuple(
            (item.source_id, item.source_version, item.locator) for item in self.evidence
        )


__all__ = ["OntologyEvidence", "OntologyLayer", "OntologyPatchProposal"]
