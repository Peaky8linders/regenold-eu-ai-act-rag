"""Offline competency-question coverage over the official gold set.

The official 110-row gold file already contains real competency questions,
answer criteria and expected legal references. This module turns that source
into an auditable question-to-evidence coverage view instead of duplicating
those questions in a second registry. It makes citation precision explicit:
``exact`` is backed by an enumerated coordinate, ``parent_only`` means the
parent exists but the requested depth is not fully catalogued, and ``invalid``
means the coordinate contradicts the known legal structure.

This is evaluation/governance tooling only. It does not alter retrieval,
answer generation or request-path citation handling. Concept/relation tags,
per-question retrieval traces and question-linked regression-test IDs are
reported as gaps rather than inferred.

Run with::

    python -m evals.official.ontology_coverage
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.provision_coordinates import POINT_COORDINATES, PROVISION_COORDINATES
from app.data.provision_hierarchy import build_hierarchy_payload
from app.data.provision_text import annex_items_sectioned, article_body
from evals.official.rubric import canonical_annex_point, normalise_ref

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_PATH = _REPO / "docs" / "measurements" / "r388" / "official_gold_n110.jsonl"


class CoordinateResolution(StrEnum):
    """How strongly the local legal-coordinate inventory supports a reference."""

    EXACT = "exact"
    PARENT_ONLY = "parent_only"
    INVALID = "invalid"


class QuestionCoverageStatus(StrEnum):
    """Question-level summary; unannotated gold refs are not treated as failures."""

    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    UNANNOTATED = "unannotated"


@dataclass(frozen=True, slots=True)
class EvidenceCoverage:
    """Resolution for one gold citation, preserving its supplied spelling."""

    reference: str
    canonical_reference: str | None
    resolution: CoordinateResolution


@dataclass(frozen=True, slots=True)
class CompetencyQuestionCoverage:
    """Question, answer criteria and citation evidence from one gold row."""

    question_id: str
    question: str
    criteria: tuple[str, ...]
    evidence: tuple[EvidenceCoverage, ...]
    status: QuestionCoverageStatus


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Machine-readable summary suitable for CI artifacts and offline review."""

    questions: tuple[CompetencyQuestionCoverage, ...]

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = Counter(question.status.value for question in self.questions)
        return {status.value: counts.get(status.value, 0) for status in QuestionCoverageStatus}

    @property
    def evidence_counts(self) -> dict[str, int]:
        counts = Counter(
            item.resolution.value
            for question in self.questions
            for item in question.evidence
        )
        return {status.value: counts.get(status.value, 0) for status in CoordinateResolution}

    def as_dict(self) -> dict[str, object]:
        """Return JSON-compatible data while retaining per-question evidence."""
        return {
            "question_count": self.question_count,
            "question_status_counts": self.status_counts,
            "evidence_resolution_counts": self.evidence_counts,
            "untracked_dimensions": [
                "concept and relation annotations",
                "per-question retrieval-path traces",
                "question-linked regression-test IDs",
            ],
            "questions": [
                {
                    **asdict(question),
                    "status": question.status.value,
                    "evidence": [
                        {
                            **asdict(item),
                            "resolution": item.resolution.value,
                        }
                        for item in question.evidence
                    ],
                }
                for question in self.questions
            ],
        }


def load_official_gold(path: Path = DEFAULT_GOLD_PATH) -> list[dict[str, object]]:
    """Load official-gold competency questions without making network calls."""
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid gold JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"gold row at {path}:{line_number} must be a JSON object")
            rows.append(value)
    return rows


@lru_cache(maxsize=1)
def _point_children() -> dict[str, frozenset[str]]:
    """Top-level letter points indexed by their paragraph parent."""
    grouped: dict[str, set[str]] = {}
    for coordinate in POINT_COORDINATES:
        parent, _sep, _letter = coordinate.rpartition(".")
        grouped.setdefault(parent, set()).add(coordinate)
    return {parent: frozenset(children) for parent, children in grouped.items()}


@lru_cache(maxsize=1)
def _subpoint_children() -> dict[str, frozenset[str]]:
    """Nested statutory points emitted by the tested hierarchy parser."""
    grouped: dict[str, set[str]] = {}
    payload = build_hierarchy_payload()
    for node in payload.subpoint_nodes:
        node_id = str(node.get("id") or "")
        if node_id.startswith("article_"):
            coordinate = "Article " + ".".join(node_id[len("article_"):].split("_"))
        elif node_id.startswith("annex_"):
            coordinate = "Annex " + ".".join(node_id[len("annex_"):].split("_"))
        else:  # pragma: no cover - the hierarchy contract has only these root types
            continue
        parent, _sep, _roman = coordinate.rpartition(".")
        grouped.setdefault(parent, set()).add(coordinate)
    return {parent: frozenset(children) for parent, children in grouped.items()}


@lru_cache(maxsize=1)
def _annex_sections() -> dict[str, dict[str, frozenset[int]]]:
    """Section label to item numbers for annexes with explicit sections."""
    sections: dict[str, dict[str, frozenset[int]]] = {}
    for head in ARTICLE_EXISTENCE:
        if not head.startswith("Annex "):
            continue
        body = article_body(head)
        if not body:
            continue
        parsed = {
            label: frozenset(items)
            for label, items in annex_items_sectioned(body)
            if label is not None
        }
        if parsed:
            sections[head] = parsed
    return sections


@lru_cache(maxsize=1)
def _ambiguous_annex_items() -> dict[str, frozenset[int]]:
    """Bare numbered annex coordinates duplicated across sections."""
    ambiguous: dict[str, frozenset[int]] = {}
    for head, sections in _annex_sections().items():
        owners: dict[int, int] = {}
        for items in sections.values():
            for item in items:
                owners[item] = owners.get(item, 0) + 1
        duplicate_items = frozenset(item for item, count in owners.items() if count > 1)
        if duplicate_items:
            ambiguous[head] = duplicate_items
    return ambiguous


@lru_cache(maxsize=1)
def _lettered_annex_sections() -> dict[str, frozenset[int]]:
    """Section-letter aliases and their item numbers, derived from adopted text.

    Annex I's legacy section-tagged citation (``Annex I.a.11``) is canonicalized
    by the official rubric. Annex VIII's ``Annex VIII.a`` gold key names Section
    A itself. Deriving the inventory from the same section-aware parser keeps
    those aliases exact without treating ordinary parent existence as proof.
    Numeric section labels are omitted because they collide with numbered items
    (notably Annex XI).
    """
    sections: dict[str, frozenset[int]] = {}
    for head, parsed in _annex_sections().items():
        for label, items in parsed.items():
            if label.isalpha():
                sections[f"{head}.{label.lower()}".lower()] = items
    return sections


def resolve_coordinate(reference: str) -> EvidenceCoverage:
    """Resolve a citation at its deepest locally enumerated legal grain.

    The function is intentionally conservative where the repository does not
    model a depth. It rejects impossible paragraph/point members when the
    sibling set is known, but returns ``parent_only`` rather than guessing when
    the data source is silent about that depth.
    """
    normalized = normalise_ref(reference)
    if normalized is None:
        return EvidenceCoverage(reference, None, CoordinateResolution.INVALID)

    canonical = canonical_annex_point(normalized)
    parts = canonical.split(".")
    head = parts[0]
    head_key = "Art. " + head[len("Article "):] if head.startswith("Article ") else head
    if head_key not in ARTICLE_EXISTENCE:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.INVALID)
    if len(parts) == 1:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.EXACT)

    # Lettered annex sections are exact anchors when the adopted text exposes
    # that section. This covers Annex VIII.a and supports the rubric's Annex I
    # aliases without treating Annex XI's ambiguous numeric section labels as
    # legal coordinates.
    section_key = ".".join(parts[:2]).lower() if head.startswith("Annex ") else ""
    section_items = _lettered_annex_sections().get(section_key)
    if section_items is not None:
        if len(parts) == 2:
            return EvidenceCoverage(reference, canonical, CoordinateResolution.EXACT)
        if len(parts) == 3 and parts[2].isdigit():
            resolution = (
                CoordinateResolution.EXACT
                if int(parts[2]) in section_items
                else CoordinateResolution.INVALID
            )
            return EvidenceCoverage(reference, canonical, resolution)
        if len(parts) > 3 and parts[2].isdigit() and int(parts[2]) in section_items:
            return EvidenceCoverage(reference, canonical, CoordinateResolution.PARENT_ONLY)
        return EvidenceCoverage(reference, canonical, CoordinateResolution.INVALID)

    paragraph = ".".join(parts[:2])
    if paragraph not in PROVISION_COORDINATES:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.INVALID)
    if len(parts) == 2:
        if head.startswith("Annex ") and parts[1].isdigit():
            item_number = int(parts[1])
            ambiguous_items = _ambiguous_annex_items().get(head, frozenset())
            if item_number in ambiguous_items:
                return EvidenceCoverage(reference, canonical, CoordinateResolution.PARENT_ONLY)
            sectioned = _annex_sections().get(head, {})
            if sectioned and not any(item_number in items for items in sectioned.values()):
                return EvidenceCoverage(reference, canonical, CoordinateResolution.INVALID)
        return EvidenceCoverage(reference, canonical, CoordinateResolution.EXACT)

    point = ".".join(parts[:3])
    points = _point_children().get(paragraph, frozenset())
    if not points:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.PARENT_ONLY)
    if point not in points:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.INVALID)
    if len(parts) == 3:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.EXACT)

    nested = _subpoint_children().get(point, frozenset())
    subpoint = ".".join(parts[:4])
    if len(parts) == 4:
        if not nested:
            return EvidenceCoverage(reference, canonical, CoordinateResolution.PARENT_ONLY)
        resolution = (
            CoordinateResolution.EXACT
            if subpoint in nested
            else CoordinateResolution.INVALID
        )
        return EvidenceCoverage(reference, canonical, resolution)

    if nested and subpoint not in nested:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.INVALID)
    if subpoint in nested:
        return EvidenceCoverage(reference, canonical, CoordinateResolution.PARENT_ONLY)
    return EvidenceCoverage(reference, canonical, CoordinateResolution.PARENT_ONLY)


def _row_status(evidence: tuple[EvidenceCoverage, ...]) -> QuestionCoverageStatus:
    if not evidence:
        return QuestionCoverageStatus.UNANNOTATED
    resolutions = {item.resolution for item in evidence}
    if CoordinateResolution.INVALID in resolutions:
        return QuestionCoverageStatus.UNRESOLVED
    if CoordinateResolution.PARENT_ONLY in resolutions:
        return QuestionCoverageStatus.PARTIAL
    return QuestionCoverageStatus.SUPPORTED


def build_coverage_report(
    rows: Iterable[Mapping[str, object]],
) -> CoverageReport:
    """Build a deterministic coverage report from official-gold-shaped rows."""
    questions: list[CompetencyQuestionCoverage] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        question_id = str(row.get("id") or "").strip()
        question = str(row.get("question") or "").strip()
        if not question_id or not question:
            raise ValueError(f"gold row {index} requires a non-empty id and question")
        if question_id in seen_ids:
            raise ValueError(f"duplicate competency-question id: {question_id}")
        seen_ids.add(question_id)

        raw_refs = row.get("expected_refs") or []
        if not isinstance(raw_refs, (list, tuple)):
            raise ValueError(f"{question_id}: expected_refs must be a list")
        evidence = tuple(resolve_coordinate(str(ref)) for ref in raw_refs)

        raw_criteria = row.get("criteria") or []
        if not isinstance(raw_criteria, (list, tuple)):
            raise ValueError(f"{question_id}: criteria must be a list")
        criteria = tuple(str(item).strip() for item in raw_criteria if str(item).strip())
        questions.append(
            CompetencyQuestionCoverage(
                question_id=question_id,
                question=question,
                criteria=criteria,
                evidence=evidence,
                status=_row_status(evidence),
            )
        )
    return CoverageReport(tuple(questions))


def main() -> int:
    """Print the official question-to-evidence coverage matrix as JSON."""
    report = build_coverage_report(load_official_gold())
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
