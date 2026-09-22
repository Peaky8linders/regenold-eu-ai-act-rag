"""Offline reconciliation checks for the legal ontology and graph inputs.

This is intentionally a report-producing module, not a request-path validator.
It makes the EvoOntology-inspired Phase 1 contract inspectable before any
runtime browse/resolve or evolution proposal is allowed to influence answers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.data.article_existence import ARTICLE_EXISTENCE
from app.data.kb_xrefs import all_edges
from app.data.ontology import ROLE_OBLIGATIONS, all_articles_referenced
from app.graph.provision_schema import EDGE_ENDPOINTS, EdgeType


def _known_ref(ref: str) -> bool:
    if ref in ARTICLE_EXISTENCE:
        return True
    candidate = ref
    while "." in candidate:
        candidate = candidate.rsplit(".", 1)[0].strip()
        if candidate in ARTICLE_EXISTENCE:
            return True
    return False


@dataclass(frozen=True, slots=True)
class OntologyReconciliationReport:
    """Machine-readable result suitable for CI and an evolution ledger."""

    ontology_unknown_refs: tuple[str, ...] = ()
    role_unknown_refs: tuple[str, ...] = ()
    xref_unknown_endpoints: tuple[str, ...] = ()
    xref_self_edges: tuple[tuple[str, str], ...] = ()
    schema_edges_without_endpoints: tuple[str, ...] = ()
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(
            (
                self.ontology_unknown_refs,
                self.role_unknown_refs,
                self.xref_unknown_endpoints,
                self.xref_self_edges,
                self.schema_edges_without_endpoints,
            )
        ) and all(self.checks.values())

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["ok"] = self.ok
        return result


def build_reconciliation_report() -> OntologyReconciliationReport:
    """Reconcile deterministic ontology inputs without network or LLM calls."""
    ontology_unknown = sorted(
        ref for ref in all_articles_referenced() if not _known_ref(ref)
    )
    role_unknown = sorted(
        ref
        for by_risk in ROLE_OBLIGATIONS.values()
        for refs in by_risk.values()
        for ref in refs
        if not _known_ref(ref)
    )

    unknown_endpoints: set[str] = set()
    self_edges: set[tuple[str, str]] = set()
    for source, target in all_edges():
        if not _known_ref(source):
            unknown_endpoints.add(source)
        if not _known_ref(target):
            unknown_endpoints.add(target)
        if source == target:
            self_edges.add((source, target))

    missing_endpoint_declarations = sorted(
        edge_type.value
        for edge_type in EdgeType
        if edge_type not in EDGE_ENDPOINTS
    )
    checks = {
        "article_catalog_nonempty": bool(ARTICLE_EXISTENCE),
        "role_matrix_nonempty": bool(ROLE_OBLIGATIONS),
        "xref_graph_nonempty": bool(all_edges()),
    }
    return OntologyReconciliationReport(
        ontology_unknown_refs=tuple(ontology_unknown),
        role_unknown_refs=tuple(role_unknown),
        xref_unknown_endpoints=tuple(sorted(unknown_endpoints)),
        xref_self_edges=tuple(sorted(self_edges)),
        schema_edges_without_endpoints=tuple(missing_endpoint_declarations),
        checks=checks,
    )


__all__ = ["OntologyReconciliationReport", "build_reconciliation_report"]
