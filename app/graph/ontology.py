"""
Compliance Knowledge Graph Ontology — Node and edge type definitions.

Defines the schema for the regulatory knowledge graph as Pydantic models.
These are internal graph representations, distinct from the typed
``app.data.ontology`` registry (which is the deterministic KB-side
ontology used by the engine in the disabled-Neo4j path).

Node types map to EU AI Act structural elements; edge types capture
regulatory relationships (obligation chains, framework mappings, task
dependencies).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.graph.schema import (
    REL_HAS_DEFINITION,
    REL_HAS_OBLIGATION,
    REL_HAS_RECITAL_ANCHOR,
    REL_TRIGGERS_HIGH_RISK_UNDER,
)

# ─── Node Types ──────────────────────────────────────────────────────────────


class NodeType(str, Enum):
    # ─── Layer 1 (global KB, tenant-agnostic) ─────────────────────────────
    article = "Article"
    obligation = "Obligation"
    dimension = "Dimension"
    question = "Question"
    risk_level = "RiskLevel"
    annex_iii_category = "AnnexIIICategory"
    roadmap_task = "RoadmapTask"
    nist_subcategory = "NISTSubcategory"
    iso_clause = "ISOClause"
    harmonized_standard = "HarmonizedStandard"
    # ─── Layer 1 — Agentic-AI compound-risk taxonomy (paper §10.4) ───────
    compound_risk_type = "CompoundRiskType"
    threat_category = "ThreatCategory"
    agent_archetype = "AgentArchetype"
    operator_role = "OperatorRole"
    # ─── Layer 2 (per-tenant overlay, mutable) ────────────────────────────
    # Every Layer 2 node carries ``tenant_id: str`` as a required property
    # plus a sharded label ``Tenant_<sha256[:8]>`` so missing tenant filters
    # return zero rows instead of cross-tenant leaks. See tenant_scope.py.
    ai_system = "AISystem"
    audit_result = "AuditResult"
    compliance_gap = "ComplianceGap"
    evidence_bundle = "EvidenceBundle"
    control_implementation = "ControlImplementation"
    campaign = "Campaign"


class ArticleNode(BaseModel):
    """EU AI Act article."""
    node_type: str = NodeType.article
    id: str
    number: str
    title: str
    description: str
    chapter: str = ""


class ObligationNode(BaseModel):
    """A specific regulatory obligation derived from an article."""
    node_type: str = NodeType.obligation
    id: str
    article_ref: str
    text: str
    mandatory: bool = True
    paragraph_ref: str = ""


class DimensionNode(BaseModel):
    """Compliance maturity dimension from KB."""
    node_type: str = NodeType.dimension
    id: str
    label: str
    article: str
    description: str


class QuestionNode(BaseModel):
    """Assessment question from KB."""
    node_type: str = NodeType.question
    id: str
    text: str
    plain_text: str
    weight: int
    evidence_type: str
    help_text: str = ""


class RiskLevelNode(BaseModel):
    """Risk classification level."""
    node_type: str = NodeType.risk_level
    id: str
    label: str
    description: str


class AnnexIIICategoryNode(BaseModel):
    """Annex III high-risk category."""
    node_type: str = NodeType.annex_iii_category
    id: str
    label: str
    description: str


class RoadmapTaskNode(BaseModel):
    """Compliance remediation task."""
    node_type: str = NodeType.roadmap_task
    id: str
    task: str
    priority: str
    effort_hours: float
    agent: str
    dimension_id: str


class NISTSubcategoryNode(BaseModel):
    """NIST AI RMF subcategory."""
    node_type: str = NodeType.nist_subcategory
    id: str
    name: str
    description: str
    function_id: str


class ISOClauseNode(BaseModel):
    """ISO/IEC 42001 clause."""
    node_type: str = NodeType.iso_clause
    id: str
    name: str
    description: str
    parent_clause: str


class HarmonizedStandardNode(BaseModel):
    """EU harmonized standard under Art. 40-41."""
    node_type: str = NodeType.harmonized_standard
    id: str
    name: str
    version: str
    status: str  # published | draft | expected
    description: str
    conformity_scope: str  # full | partial


# ─── Layer 1 — Agentic-AI Compound-Risk Taxonomy (paper §10.4) ───────────────


class CompoundRiskTypeNode(BaseModel):
    """One axis of the four-axis agentic-AI compound-risk taxonomy.

    Source: AI Agents Under EU Law (Working Paper, 7 April 2026), §10.4
    lines 2227-2245.
    """
    node_type: str = NodeType.compound_risk_type
    id: str  # cascading | emergent | attribution | temporal
    label: str
    summary: str
    paper_section: str
    paper_lines: str


class ThreatCategoryNode(BaseModel):
    """An agentic-AI threat category cross-walked from the literature.

    Sources: Kim et al. USENIX 2026, Hammond et al. multi-agent failure
    modes, OWASP Top-10 Agentic, AEPD rule-of-2 / lethal trifecta.
    """
    node_type: str = NodeType.threat_category
    id: str
    label: str
    source: str
    paper_lines: str


class AgentArchetypeNode(BaseModel):
    """An architecture archetype — single-agent, orchestrator+sub-agents,
    multi-agent swarm, GPAI-with-tools, RAG-grounded, dynamic tool
    discovery, continuously learning system."""
    node_type: str = NodeType.agent_archetype
    id: str
    label: str
    description: str


class OperatorRoleNode(BaseModel):
    """An operator role under the EU AI Act.

    Includes the six NLF-derived roles (provider, deployer, importer,
    distributor, product manufacturer, authorized representative) plus
    the GPAI provider, GPAI-with-systemic-risk provider, and the
    extraterritorial-non-EU modifier (Art. 2(1)(c) / Art. 74).
    """
    node_type: str = NodeType.operator_role
    id: str
    label: str
    art_3_definition: str
    summary: str


# ─── Layer 2 Node Types (per-tenant overlay) ─────────────────────────────────
#
# Every Layer 2 node carries ``tenant_id`` as a required property. At
# seed/write time the writer also attaches a sharded Neo4j label of the
# form ``Tenant_<sha256(tenant_id)[:8]>`` so reads missing the ``tenant_id``
# filter return zero rows instead of leaking across tenants.
# See tenant_scope.py for the helper that enforces this on every query.


class AISystemNode(BaseModel):
    """A tenant's registered AI system. Mirrors the portfolio row."""
    node_type: str = NodeType.ai_system
    id: str
    tenant_id: str
    name: str
    risk_level: str = ""
    article_ref: str = ""
    posture: str = ""  # ok | partial | gap | breach
    created_at: str = ""  # ISO-8601


class AuditResultNode(BaseModel):
    """A completed audit attached to an AISystem."""
    node_type: str = NodeType.audit_result
    id: str
    tenant_id: str
    system_id: str
    overall_score: float = 0.0  # 0-100, mirrors AuditResultResponse.overall_score
    gap_count: int = 0
    risk_level: str = ""
    completed_at: str = ""  # ISO-8601


class ComplianceGapNode(BaseModel):
    """A single gap discovered during an audit or code scan."""
    node_type: str = NodeType.compliance_gap
    id: str
    tenant_id: str
    audit_id: str
    kb_dimension: str
    article_ref: str = ""
    severity: str = ""  # critical | major | minor
    current_state: str = ""


class EvidenceBundleNode(BaseModel):
    """A set of evidence artifacts uploaded or produced for a tenant."""
    node_type: str = NodeType.evidence_bundle
    id: str
    tenant_id: str
    article_ref: str = ""
    correlation_id: str = ""
    file_count: int = 0
    sha256: str = ""  # hash of the concatenated file hashes, for chain integrity
    uploaded_at: str = ""


class ControlImplementationNode(BaseModel):
    """A tenant-declared control for an obligation."""
    node_type: str = NodeType.control_implementation
    id: str
    tenant_id: str
    obligation_id: str
    status: str = ""  # declared | detected | enforced
    evidence_ref: str = ""


class CampaignNode(BaseModel):
    """An adversarial-testing campaign run against an AISystem."""
    node_type: str = NodeType.campaign
    id: str
    tenant_id: str
    system_id: str
    antifragility_score: float = 0.0
    ran_at: str = ""


# ─── Edge Types ──────────────────────────────────────────────────────────────


class EdgeType(str, Enum):
    # ─── Layer 1 (global KB) ──────────────────────────────────────────────
    # R121 — the article→obligation / definition / recital / high-risk edges
    # the seeder actually MERGEs, sourced from the single schema source of
    # truth (``app.graph.schema``). ``requires`` below is a stale, UNSEEDED
    # alias kept only for backward-compat; the real article→obligation edge
    # is ``has_obligation`` (= ``HAS_OBLIGATION``). See R99.1 for the drift bug
    # this divergence caused (the read query matched ``REQUIRES`` → empty graph
    # → wire zero-retrieval floor).
    has_obligation = REL_HAS_OBLIGATION
    has_definition = REL_HAS_DEFINITION
    has_recital_anchor = REL_HAS_RECITAL_ANCHOR
    triggers_high_risk_under = REL_TRIGGERS_HIGH_RISK_UNDER
    requires = "REQUIRES"  # DEPRECATED / unseeded — use ``has_obligation``
    assesses = "ASSESSES"
    belongs_to = "BELONGS_TO"
    applies_at = "APPLIES_AT"
    categorized_as = "CATEGORIZED_AS"
    maps_to_nist = "MAPS_TO_NIST"
    maps_to_iso = "MAPS_TO_ISO"
    depends_on = "DEPENDS_ON"
    remediates = "REMEDIATES"
    prerequisite_for = "PREREQUISITE_FOR"
    supersedes = "SUPERSEDES"
    cross_references = "CROSS_REFERENCES"
    presumed_conformity_via = "PRESUMED_CONFORMITY_VIA"
    # ─── Layer 1 — Agentic-AI taxonomy edges (paper §10.4) ────────────────
    mitigates_risk = "MITIGATES_RISK"           # Article → CompoundRiskType
    exhibits_threat = "EXHIBITS_THREAT"         # CompoundRiskType → ThreatCategory
    archetype_carries = "ARCHETYPE_CARRIES"     # AgentArchetype → CompoundRiskType
    applies_to_role = "APPLIES_TO_ROLE"         # Article → OperatorRole
    flips_provider_under = "FLIPS_PROVIDER_UNDER"  # OperatorRole → Article (the flip trigger)
    # ─── Layer 2 (tenant overlay → Layer 1) ───────────────────────────────
    # Every edge where the source is a Layer 2 node MUST have the source
    # node already scoped to the caller's tenant via tenant_scope.scoped_read.
    audit_of = "AUDIT_OF"              # AuditResult → AISystem
    refers_to = "REFERS_TO"            # ComplianceGap → Obligation / Article
    assessed_by = "ASSESSED_BY"        # AuditResult → Question (evidence)
    evidenced_by = "EVIDENCED_BY"      # ComplianceGap → EvidenceBundle
    implements = "IMPLEMENTS"          # ControlImplementation → Obligation
    ran_against = "RAN_AGAINST"        # Campaign → AISystem


class GraphEdge(BaseModel):
    """A typed, directed edge in the compliance graph."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict = Field(default_factory=dict)


# ─── Graph Summary ───────────────────────────────────────────────────────────


class GraphStats(BaseModel):
    """Summary statistics for the compliance graph."""
    total_nodes: int = 0
    total_edges: int = 0
    nodes_by_type: dict[str, int] = Field(default_factory=dict)
    edges_by_type: dict[str, int] = Field(default_factory=dict)
    seed_version: str = ""
    healthy: bool = False
