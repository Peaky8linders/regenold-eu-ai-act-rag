"""
W3C Ontology Mapping — IRI references for DPV, AIRO, and VAIR vocabularies.

Maps CodexAI's internal graph types to W3C-backed IRIs so the platform can
export standards-aligned RDF and claim vocabulary compatibility with auditors
and notified bodies.

Namespaces:
  - DPV EU-AIAct: https://w3id.org/dpv/legal/eu/aiact#
  - AIRO (AI Risk Ontology): https://w3id.org/airo#
  - VAIR (Vocabulary of AI Risks): https://w3id.org/vair#
  - DPV core: https://w3id.org/dpv#
  - DPV AI: https://w3id.org/dpv/ai#
"""

from __future__ import annotations

from pydantic import BaseModel


# ─── Namespace Constants ─────────────────────────────────────────────────────

DPV_NS = "https://w3id.org/dpv#"
DPV_AI_NS = "https://w3id.org/dpv/ai#"
DPV_EU_AIACT_NS = "https://w3id.org/dpv/legal/eu/aiact#"
AIRO_NS = "https://w3id.org/airo#"
VAIR_NS = "https://w3id.org/vair#"
CODEXAI_NS = "https://codexai.dev/ontology#"


class OntologyNamespace(BaseModel):
    """A namespace declaration for RDF serialization."""
    prefix: str
    iri: str
    description: str = ""


NAMESPACES: list[OntologyNamespace] = [
    OntologyNamespace(
        prefix="dpv", iri=DPV_NS,
        description="W3C Data Privacy Vocabulary",
    ),
    OntologyNamespace(
        prefix="dpv-ai", iri=DPV_AI_NS,
        description="W3C DPV AI Technology Concepts",
    ),
    OntologyNamespace(
        prefix="eu-aiact", iri=DPV_EU_AIACT_NS,
        description="W3C DPV EU AI Act Extension",
    ),
    OntologyNamespace(
        prefix="airo", iri=AIRO_NS,
        description="AI Risk Ontology (ADAPT Centre, TCD)",
    ),
    OntologyNamespace(
        prefix="vair", iri=VAIR_NS,
        description="Vocabulary of AI Risks (ADAPT Centre, TCD)",
    ),
    OntologyNamespace(
        prefix="codexai", iri=CODEXAI_NS,
        description="CodexAI internal compliance ontology",
    ),
    OntologyNamespace(
        prefix="rdf", iri="http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        description="RDF syntax",
    ),
    OntologyNamespace(
        prefix="rdfs", iri="http://www.w3.org/2000/01/rdf-schema#",
        description="RDF Schema",
    ),
    OntologyNamespace(
        prefix="xsd", iri="http://www.w3.org/2001/XMLSchema#",
        description="XML Schema datatypes",
    ),
    OntologyNamespace(
        prefix="skos", iri="http://www.w3.org/2004/02/skos/core#",
        description="Simple Knowledge Organization System",
    ),
    OntologyNamespace(
        prefix="dcterms", iri="http://purl.org/dc/terms/",
        description="Dublin Core Terms",
    ),
]


# ─── IRI Mapping Model ──────────────────────────────────────────────────────


class IRIMapping(BaseModel):
    """Maps a CodexAI node type to W3C-backed IRIs."""
    node_type: str
    dpv_class: str | None = None
    airo_class: str | None = None
    vair_class: str | None = None
    description: str = ""


# ─── Node Type → W3C Class Mappings ─────────────────────────────────────────

NODE_TYPE_IRI_MAP: dict[str, IRIMapping] = {
    "Article": IRIMapping(
        node_type="Article",
        dpv_class=f"{DPV_EU_AIACT_NS}Provision",
        airo_class=None,
        description="EU AI Act article / provision",
    ),
    "Obligation": IRIMapping(
        node_type="Obligation",
        dpv_class=f"{DPV_EU_AIACT_NS}Obligation",
        airo_class=f"{AIRO_NS}LegalRequirement",
        description="Regulatory obligation derived from an article",
    ),
    "Dimension": IRIMapping(
        node_type="Dimension",
        dpv_class=f"{DPV_NS}ComplianceMeasure",
        airo_class=f"{AIRO_NS}RiskControl",
        description="Compliance maturity dimension / risk control area",
    ),
    "Question": IRIMapping(
        node_type="Question",
        dpv_class=f"{DPV_NS}ComplianceAssessment",
        airo_class=None,
        description="Assessment question for compliance evaluation",
    ),
    "RiskLevel": IRIMapping(
        node_type="RiskLevel",
        dpv_class=f"{DPV_EU_AIACT_NS}RiskLevel",
        airo_class=f"{AIRO_NS}RiskLevel",
        description="AI Act risk classification tier",
    ),
    "AnnexIIICategory": IRIMapping(
        node_type="AnnexIIICategory",
        dpv_class=f"{DPV_EU_AIACT_NS}HighRiskAISystem",
        airo_class=None,
        vair_class=f"{VAIR_NS}HighRiskAICategory",
        description="Annex III high-risk AI system category",
    ),
    "RoadmapTask": IRIMapping(
        node_type="RoadmapTask",
        dpv_class=None,
        airo_class=f"{AIRO_NS}RiskControl",
        description="Compliance remediation task",
    ),
    "NISTSubcategory": IRIMapping(
        node_type="NISTSubcategory",
        dpv_class=None,
        airo_class=None,
        description="NIST AI RMF subcategory (no W3C equivalent)",
    ),
    "ISOClause": IRIMapping(
        node_type="ISOClause",
        dpv_class=None,
        airo_class=None,
        description="ISO/IEC 42001 clause (no W3C equivalent)",
    ),
    "HarmonizedStandard": IRIMapping(
        node_type="HarmonizedStandard",
        dpv_class=f"{DPV_EU_AIACT_NS}HarmonisedStandard",
        airo_class=None,
        description="EU harmonized standard under Art. 40-41",
    ),
    # ─── Layer 2 (per-tenant overlay) ────────────────────────────────────────
    # These map to the most-specific existing DPV-AI / AIRO class we can
    # reach. When a Layer 2 node type has no public W3C analogue (e.g. our
    # EvidenceBundle is a product-specific roll-up), we fall back to
    # codexai-namespace IRIs rather than omitting the mapping — the parity
    # test in tests/test_all.py asserts every NodeType has an entry.
    "AISystem": IRIMapping(
        node_type="AISystem",
        dpv_class=f"{DPV_AI_NS}AISystem",
        airo_class=f"{AIRO_NS}AISystem",
        description="Tenant-registered AI system instance (Layer 2 overlay)",
    ),
    "AuditResult": IRIMapping(
        node_type="AuditResult",
        # DPV ComplianceAssessment is already claimed by Question (the
        # unit of assessment). AuditResult is the outcome, not the act,
        # so we mint a codexai-namespace IRI rather than overloading DPV.
        dpv_class=f"{CODEXAI_NS}AuditResult",
        airo_class=None,
        description="Completed audit attached to an AISystem (Layer 2 overlay)",
    ),
    "ComplianceGap": IRIMapping(
        node_type="ComplianceGap",
        dpv_class=None,
        airo_class=f"{AIRO_NS}Risk",
        description="Discovered compliance gap (Layer 2 overlay)",
    ),
    "EvidenceBundle": IRIMapping(
        node_type="EvidenceBundle",
        dpv_class=None,
        airo_class=None,
        description=f"Evidence bundle grouped by correlation_id — see {CODEXAI_NS}EvidenceBundle",
    ),
    "ControlImplementation": IRIMapping(
        node_type="ControlImplementation",
        dpv_class=f"{DPV_NS}TechnicalOrganisationalMeasure",
        airo_class=f"{AIRO_NS}RiskControl",
        description="Tenant-declared control for an obligation (Layer 2 overlay)",
    ),
    "Campaign": IRIMapping(
        node_type="Campaign",
        dpv_class=None,
        airo_class=f"{AIRO_NS}RiskAssessment",
        description="Adversarial-testing campaign against an AISystem (Layer 2 overlay)",
    ),
    # ─── Layer 1 — Agentic-AI Compound-Risk Taxonomy (paper §10.4) ────────────
    "CompoundRiskType": IRIMapping(
        node_type="CompoundRiskType",
        dpv_class=None,
        airo_class=f"{AIRO_NS}RiskConcept",
        description="One axis of the four-axis compound-risk taxonomy",
    ),
    "ThreatCategory": IRIMapping(
        node_type="ThreatCategory",
        dpv_class=None,
        airo_class=f"{AIRO_NS}Threat",
        description="Threat category cross-walked from agentic-AI literature",
    ),
    "AgentArchetype": IRIMapping(
        node_type="AgentArchetype",
        # AgentArchetype is a *type* of AISystem, not the system itself
        # — leaving dpv_class None avoids colliding with the AISystem
        # IRI that the per-tenant Layer 2 node owns.
        dpv_class=None,
        airo_class=f"{AIRO_NS}AISystem",
        description="Agent architecture archetype (single, orchestrator+sub-agents, swarm, ...)",
    ),
    "OperatorRole": IRIMapping(
        node_type="OperatorRole",
        dpv_class=f"{DPV_EU_AIACT_NS}AIRole",
        airo_class=f"{AIRO_NS}Role",
        description="EU AI Act operator role (provider / deployer / GPAI / extraterritorial)",
    ),
}


# ─── Risk Level → eu-aiact IRI Mapping ──────────────────────────────────────

RISK_LEVEL_IRI_MAP: dict[str, str] = {
    "unacceptable": f"{DPV_EU_AIACT_NS}AIRiskLevelUnacceptable",
    "high": f"{DPV_EU_AIACT_NS}AIRiskLevelHigh",
    "limited": f"{DPV_EU_AIACT_NS}AIRiskLevelLimited",
    "minimal": f"{DPV_EU_AIACT_NS}AIRiskLevelMinimal",
    "gpai": f"{DPV_EU_AIACT_NS}GPAISystem",
    "gpai_systemic": f"{DPV_EU_AIACT_NS}GPAISystemSystemicRisk",
}


# ─── Operator Role → eu-aiact IRI Mapping ───────────────────────────────────

OPERATOR_ROLE_IRI_MAP: dict[str, str] = {
    "provider": f"{DPV_EU_AIACT_NS}AIProvider",
    "deployer": f"{DPV_EU_AIACT_NS}AIDeployer",
    "importer": f"{DPV_EU_AIACT_NS}AIImporter",
    "distributor": f"{DPV_EU_AIACT_NS}AIDistributor",
    "product_manufacturer": f"{DPV_EU_AIACT_NS}AIProductManufacturer",
    "authorised_representative": f"{DPV_EU_AIACT_NS}AIAuthorisedRepresentative",
}


# ─── Edge Type → W3C Property Mappings ──────────────────────────────────────

EDGE_TYPE_IRI_MAP: dict[str, str] = {
    "REQUIRES": f"{DPV_EU_AIACT_NS}hasObligation",
    "ASSESSES": f"{DPV_NS}hasComplianceAssessment",
    "BELONGS_TO": f"{DPV_NS}hasScope",
    "APPLIES_AT": f"{DPV_EU_AIACT_NS}hasRiskLevel",
    "CATEGORIZED_AS": f"{DPV_EU_AIACT_NS}hasHighRiskCategory",
    "MAPS_TO_NIST": f"{CODEXAI_NS}mapsToNIST",
    "MAPS_TO_ISO": f"{CODEXAI_NS}mapsToISO",
    "DEPENDS_ON": f"{CODEXAI_NS}dependsOn",
    "REMEDIATES": f"{AIRO_NS}mitigatesRiskConcept",
    "PREREQUISITE_FOR": f"{CODEXAI_NS}prerequisiteFor",
    "SUPERSEDES": f"{CODEXAI_NS}supersedes",
    "CROSS_REFERENCES": "http://purl.org/dc/terms/relation",
    "PRESUMED_CONFORMITY_VIA": f"{DPV_EU_AIACT_NS}hasConformityVia",
    # ─── Layer 2 edges (tenant overlay → Layer 1) ───────────────────────────
    "AUDIT_OF": f"{CODEXAI_NS}auditOf",
    "REFERS_TO": "http://purl.org/dc/terms/references",
    "ASSESSED_BY": f"{DPV_NS}hasComplianceAssessment",
    "EVIDENCED_BY": f"{DPV_NS}hasEvidence",
    "IMPLEMENTS": f"{DPV_NS}hasTechnicalOrganisationalMeasure",
    "RAN_AGAINST": f"{CODEXAI_NS}ranAgainst",
    # ─── Layer 1 — Agentic-AI Taxonomy edges (paper §10.4) ──────────────────
    "MITIGATES_RISK": f"{AIRO_NS}mitigatesRiskConcept",
    "EXHIBITS_THREAT": f"{AIRO_NS}exposes",
    "ARCHETYPE_CARRIES": f"{CODEXAI_NS}archetypeCarries",
    "APPLIES_TO_ROLE": f"{CODEXAI_NS}appliesToRole",
    "FLIPS_PROVIDER_UNDER": f"{CODEXAI_NS}flipsProviderUnder",
}


# ─── Dimension → AIRO Risk Control Mapping ──────────────────────────────────

DIMENSION_AIRO_MAP: dict[str, str] = {
    "ai_literacy": f"{DPV_EU_AIACT_NS}AILiteracy",
    "risk_mgmt": f"{AIRO_NS}RiskManagementProcess",
    "data_gov": f"{AIRO_NS}DataGovernance",
    "tech_docs": f"{AIRO_NS}DocumentationControl",
    "logging": f"{AIRO_NS}RecordKeeping",
    "transparency": f"{AIRO_NS}TransparencyMeasure",
    "human_oversight": f"{AIRO_NS}HumanOversightControl",
    "security": f"{AIRO_NS}SecurityControl",
    "conformity_assessment": f"{DPV_EU_AIACT_NS}ConformityAssessment",
    "quality_management": f"{AIRO_NS}QualityManagementSystem",
    "deployer_obligations": f"{DPV_EU_AIACT_NS}DeployerObligation",
    "content_transparency": f"{DPV_EU_AIACT_NS}ContentTransparency",
    "gpai": f"{DPV_EU_AIACT_NS}GPAISystemObligation",
    "gpai_systemic_risk": f"{DPV_EU_AIACT_NS}GPAISystemSystemicRisk",
    "decision_governance": f"{AIRO_NS}DecisionGovernance",
    "access_control": f"{AIRO_NS}AccessControl",
    "infra_mlops": f"{AIRO_NS}InfrastructureControl",
    "supply_chain": f"{AIRO_NS}SupplyChainControl",
    "voluntary_codes": f"{DPV_EU_AIACT_NS}VoluntaryCode",
    # Agent-aware obligations (Nannini et al. 2026, "AI Agents under EU Law").
    # No published AIRO/DPV term yet — these IRIs sit under the CodexAI
    # internal namespace and will be migrated when the W3C / JTC 21 vocabularies
    # ship corresponding terms (paper §6 + §7).
    "agent_inventory": f"{CODEXAI_NS}AgentInventory",
    "tool_governance": f"{CODEXAI_NS}ToolGovernance",
    "chain_transparency": f"{CODEXAI_NS}ChainTransparency",
    "runtime_drift": f"{CODEXAI_NS}RuntimeDrift",
    "regulatory_perimeter": f"{CODEXAI_NS}RegulatoryPerimeter",
}
