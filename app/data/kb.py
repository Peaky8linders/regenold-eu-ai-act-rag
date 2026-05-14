"""Knowledge-base stub — only what the Regenold + Graph-RAG path needs.

The full CodexAI KB ships 24 compliance dimensions × 139 questions plus
risk-level mappings, dimension crosswalks, and an EC-Checker obligation
map. This bundle ships just enough scaffolding for ``graph_rag.py``'s
KB-fallback path to resolve cleanly.

If a partner wants to exercise the full graph-projection path they
should restore CodexAI's full KB module (and the Neo4j client).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Version pin surfaced on every Regenold response (telemetry mode).
KB_VERSION = "2024.1689.v2"


@dataclass(frozen=True)
class MaturityDimension:
    """A compliance dimension. Stubbed shape — only ``id`` / ``label`` /
    ``questions`` are read by the graph-RAG engine."""

    id: str
    label: str
    questions: tuple[str, ...] = field(default_factory=tuple)


# Minimal 4-dimension set covering the dimensions the engine surfaces
# when the question doesn't carry an explicit article anchor. This is a
# DELIBERATE skeleton — the engine's deterministic-fallback prose only
# names dimensions in the closed-world refusal branch.
MATURITY_DIMENSIONS: tuple[MaturityDimension, ...] = (
    MaturityDimension(
        id="risk_mgmt",
        label="Risk management system (Art. 9)",
        questions=("Risk management process established?", "Foreseeable misuse mapped?"),
    ),
    MaturityDimension(
        id="data_gov",
        label="Data governance (Art. 10)",
        questions=("Training data provenance recorded?", "Bias examination performed?"),
    ),
    MaturityDimension(
        id="tech_docs",
        label="Technical documentation (Art. 11 + Annex IV)",
        questions=("Annex IV pack drafted?", "Documentation kept up to date?"),
    ),
    MaturityDimension(
        id="transparency",
        label="Transparency to deployers (Art. 13)",
        questions=("Instructions for use shipped?", "Capabilities + limitations documented?"),
    ),
    MaturityDimension(
        id="conformity",
        label="Conformity assessment + CE marking (Arts. 43, 47-49)",
        questions=("Correct assessment procedure selected?", "Declaration of conformity issued?"),
    ),
    MaturityDimension(
        id="governance",
        label="Governance + competent authorities (Arts. 64-70)",
        questions=("National competent authority identified?", "Cooperation channels open?"),
    ),
    MaturityDimension(
        id="post_market",
        label="Post-market monitoring + incident reporting (Arts. 72-73)",
        questions=("Monitoring plan in place?", "Serious-incident reporting workflow set up?"),
    ),
    MaturityDimension(
        id="gpai_specific",
        label="General-Purpose AI obligations (Arts. 51-56)",
        questions=("GPAI classification assessed?", "Annex XI documentation prepared?"),
    ),
    # ─── Extended dimensions ported from CodexAI (May 2026 — round 19+) ────
    # The 16 entries below extend the original 8-dimension skeleton to the
    # full 24-dimension surface used by the parent CodexAI compliance
    # platform. These are NOT consumed by the Regenold deterministic
    # fallback as classification topics (hard rule #3 in CLAUDE.md) — the
    # engine only reads ``dim.id`` / ``dim.label`` / ``len(dim.questions)``
    # for dimension catalogue surfacing. They are added so:
    #
    #   * a question hinting at a downstream dimension (``dimension_hint``)
    #     can resolve cleanly instead of falling back to "no match",
    #   * the role × risk-class matrix in ``get_dimensions_for_role_and_risk``
    #     can filter the full 24-dimension set (matching CodexAI semantics),
    #   * the KB stays the single source of truth for the dimension catalogue
    #     the parent app's typed ontology references.
    #
    # The ``questions`` tuples are deliberately short — they're not
    # classification anchors, they're a synthesised summary of the
    # source ``AssessmentQuestion.text`` payload to keep the dimension
    # self-documenting without ballooning module size.
    MaturityDimension(
        id="ai_literacy",
        label="AI literacy (Art. 4)",
        questions=(
            "AI literacy training programme for staff?",
            "Training covers context of AI system use?",
            "Persons affected by AI considered in literacy programme?",
        ),
    ),
    MaturityDimension(
        id="logging",
        label="Record-keeping / automatic logging (Art. 12)",
        questions=(
            "Automatic event logging for AI decisions?",
            "Logs capture inputs, outputs, and timestamps?",
            "Logs tamper-resistant with defined retention?",
            "AI incident response playbooks rehearsed?",
        ),
    ),
    MaturityDimension(
        id="human_oversight",
        label="Human oversight (Art. 14)",
        questions=(
            "Human can override or stop the AI?",
            "Escalation procedures for edge cases?",
            "Automation-bias safeguards in place?",
            "Interface enables understanding of AI output?",
        ),
    ),
    MaturityDimension(
        id="security",
        label="Accuracy, robustness, cybersecurity (Art. 15)",
        questions=(
            "Accuracy metrics defined and declared?",
            "Tested against adversarial inputs?",
            "Cybersecurity measures proportionate to risk?",
            "Continuous performance monitoring in place?",
            "Disparate impact analysis with bias mitigation?",
        ),
    ),
    MaturityDimension(
        id="quality_management",
        label="Quality management system (Art. 17)",
        questions=(
            "QMS documented with compliance strategy and objectives?",
            "Design and development procedures defined?",
            "Testing and validation protocols established?",
            "Incident handling and corrective-action procedures in place?",
            "RACI matrix defines responsibilities across AI lifecycle?",
        ),
    ),
    MaturityDimension(
        id="deployer_obligations",
        label="Deployer obligations + FRIA (Arts. 26-27)",
        questions=(
            "Using the AI system per provider's instructions?",
            "Human oversight by competent individuals?",
            "Input data relevant and representative?",
            "Monitoring operation and reporting to provider?",
            "Fundamental Rights Impact Assessment conducted?",
            "Affected individuals informed of AI use?",
        ),
    ),
    MaturityDimension(
        id="content_transparency",
        label="Content transparency / deepfakes (Art. 50)",
        questions=(
            "Synthetic content marked in machine-readable format?",
            "Marking solutions interoperable and robust?",
            "Deep-fake content disclosed as AI-generated?",
            "Emotion-recognition / biometric users informed?",
            "Disclosures provided clearly at first interaction?",
        ),
    ),
    MaturityDimension(
        id="gpai_systemic_risk",
        label="GPAI systemic risk (Arts. 51, 55-56)",
        questions=(
            "Systemic risk evaluation performed (10^25 FLOP threshold)?",
            "Model evaluation + red-teaming conducted?",
            "Systemic risk mitigation measures documented?",
            "Serious incident reporting to AI Office established?",
            "Adequate cybersecurity for the GPAI model?",
        ),
    ),
    MaturityDimension(
        id="decision_governance",
        label="Decision governance / runtime interception (Arts. 9, 14, 15, 72)",
        questions=(
            "Behavioural rules defined for AI decision outputs?",
            "Decision interception layer captures all AI actions before execution?",
            "Escalation paths configured for blocked or uncertain decisions?",
            "Decision audit trail with full context retained?",
            "Behavioural baselines monitored for anomalous patterns?",
            "Confidence calibration validated against actual outcomes?",
        ),
    ),
    MaturityDimension(
        id="access_control",
        label="Access control & identity (Art. 15 / ISO 27002)",
        questions=(
            "RBAC enforced for AI infrastructure, model repos, and endpoints?",
            "Service-account keys rotated, vaulted, no defaults?",
            "MFA required for all admin / privileged AI access?",
        ),
    ),
    MaturityDimension(
        id="infra_mlops",
        label="Infrastructure & MLOps security (Art. 15)",
        questions=(
            "Network segmentation separates training, staging, production?",
            "CIS benchmarks applied to AI workload configuration?",
            "MLOps CI/CD pipeline secured with artifact signing?",
        ),
    ),
    MaturityDimension(
        id="supply_chain",
        label="Supply chain & third-party risk (Art. 15)",
        questions=(
            "Due diligence on external AI models and services?",
            "SCA scanning with CVE remediation and license compliance?",
            "Data-provider agreements include security + audit clauses?",
        ),
    ),
    MaturityDimension(
        id="agent_inventory",
        label="Agent inventory — 4-facet (Art. 11 + Nannini §3)",
        questions=(
            "Documented agent inventory artefact at the repo root?",
            "Deployment category declared (HR / Clinical / DevOps / etc.)?",
            "Each external action classified read-only / write / exec / network / payment?",
        ),
    ),
    MaturityDimension(
        id="tool_governance",
        label="Tool governance — prEN 18282 (Art. 15(4))",
        questions=(
            "Each tool's permission enforced at API level, not via prompt?",
            "Open-ended code execution bounded (sandbox, allow-list)?",
            "Credentials provisioned just-in-time with short TTLs (NHI)?",
            "Audit-log writes distinguish user-initiated from AI-initiated?",
        ),
    ),
    MaturityDimension(
        id="chain_transparency",
        label="Multi-party chain transparency (Arts. 12, 13, 50)",
        questions=(
            "Each decision record carries a parent_decision_id?",
            "Agent identities cryptographically signed (not self-asserted)?",
            "Synthetic content marked machine-readably before downstream tool calls?",
        ),
    ),
    MaturityDimension(
        id="runtime_drift",
        label="Runtime drift / Art. 3(23) substantial modification",
        questions=(
            "Upstream model pinned to a dated snapshot?",
            "System prompts stored as versioned templates?",
            "Tool catalogue declared in a versioned manifest?",
            "Trajectory / behavioural monitoring against a conformity baseline?",
            "Documented Art. 3(23) substantial-modification threshold procedure?",
        ),
    ),
    MaturityDimension(
        id="regulatory_perimeter",
        label="Regulatory perimeter — cross-instrument (Nannini Table 5)",
        questions=(
            "GDPR personal-data trace completed for every tool?",
            "Data Act applicability assessed?",
            "DSA applicability assessed?",
            "CRA applicability assessed (product with digital elements)?",
            "NIS2 applicability assessed (essential / important entity)?",
            "Sectoral legislation reviewed (MDR / MiFID II / PSD2 / DORA)?",
            "adjacent-legislation.md summarising the regulatory map?",
        ),
    ),
    MaturityDimension(
        id="voluntary_codes",
        label="Voluntary codes of conduct (Art. 95)",
        questions=(
            "Voluntary code of conduct adopted?",
            "Environmental sustainability considered?",
            "AI literacy promoted among stakeholders?",
            "Diversity and inclusion in design process?",
        ),
    ),
)


# ─── Role × risk-class dimension filter ──────────────────────────────────────
# Deployers of third-party high-risk AI carry roughly ~30-40% of the provider
# obligation surface. The map below mirrors the CodexAI surface — ``None``
# keeps the full dimension, a tuple of question-prefix tokens trims to a
# relevant subset. Because the Regenold bundle ships questions as plain
# strings (not :class:`AssessmentQuestion` instances with stable IDs), the
# subset filter operates on the leading substring of each question. Engines
# that don't need the trim ignore this surface entirely.
DEPLOYER_APPLICABLE_DIMENSIONS: dict[str, tuple[str, ...] | None] = {
    "ai_literacy": None,
    "deployer_obligations": None,
    "transparency": ("Instructions for use", "Capabilities"),
    "human_oversight": ("Human can override", "Escalation", "Interface enables"),
    "security": ("Cybersecurity", "Continuous performance"),
    "decision_governance": ("Behavioural rules", "Escalation paths", "Decision audit trail"),
    "supply_chain": None,
    "access_control": ("RBAC", "MFA"),
    "content_transparency": None,
}


def get_dimensions_for_risk_level(risk_level: str | None) -> tuple[MaturityDimension, ...]:
    """Return dimensions in scope for ``risk_level``.

    The minimal bundle returns the full dimension catalogue for every risk
    level. The full CodexAI implementation maps each level to a subset.
    """
    if risk_level not in {"high", "limited", "minimal", "unacceptable", None}:
        raise ValueError(f"Unknown risk level: {risk_level!r}")
    return MATURITY_DIMENSIONS


def get_dimensions_for_role_and_risk(
    risk_level: str | None,
    operator_role: str | None = None,
) -> tuple[MaturityDimension, ...]:
    """Return dimensions filtered by both risk level and operator role.

    * ``provider`` / ``None`` — same as :func:`get_dimensions_for_risk_level`.
    * ``deployer`` — restricted to :data:`DEPLOYER_APPLICABLE_DIMENSIONS`,
      with question lists trimmed to the role-relevant subset.
    * any other role — returns the full risk-level set unchanged (other roles
      surface through the typed role-obligation matrix in
      :mod:`app.data.role_obligations` and :data:`app.data.ontology.ROLE_OBLIGATIONS`).

    Ported from the CodexAI accessor to keep the engine surface symmetrical
    with the parent app. The Regenold deterministic fallback doesn't yet
    branch on operator role, but the helper is available for downstream
    consumers (and future Stage-2 enhancements) that need the filter.
    """
    base = get_dimensions_for_risk_level(risk_level)
    if operator_role is None or operator_role == "provider":
        return base
    if operator_role != "deployer":
        return base

    filtered: list[MaturityDimension] = []
    for dim in base:
        if dim.id not in DEPLOYER_APPLICABLE_DIMENSIONS:
            continue
        allowed_prefixes = DEPLOYER_APPLICABLE_DIMENSIONS[dim.id]
        if allowed_prefixes is None:
            filtered.append(dim)
            continue
        subset = tuple(
            q for q in dim.questions
            if any(q.startswith(prefix) for prefix in allowed_prefixes)
        )
        if subset:
            filtered.append(
                MaturityDimension(id=dim.id, label=dim.label, questions=subset)
            )
    return tuple(filtered)


# EC-Checker → KB-dimension surface. Used by the engine when a question
# explicitly mentions an Art. ref so it can look up a synthetic
# obligation row. The bundle ships minimal entries for the 12 most-cited
# high-risk articles so the deterministic-fallback path produces a
# tight answer instead of dumping the dimension catalog. Full CodexAI
# coverage is 113 articles × per-paragraph rows.
EC_CHECKER_OBLIGATION_MAP: dict[str, dict[str, str]] = {
    "Art. 5": {
        "dimension": "risk_mgmt",
        "summary": (
            "Prohibits eight categories of AI practice: (a) subliminal / "
            "manipulative / deceptive techniques causing significant harm; "
            "(b) exploitation of vulnerabilities by age, disability, or "
            "socio-economic situation; (c) social scoring leading to "
            "unjustified detrimental treatment in unrelated contexts; "
            "(d) profiling for criminal-risk assessment based solely on "
            "personality traits (exception for human-assessment support on "
            "objective facts); (e) untargeted scraping of facial images for "
            "facial-recognition databases; (f) emotion-inference in "
            "workplaces and educational institutions (narrow medical / "
            "safety exception); (g) biometric categorisation by sensitive "
            "attributes (race, political views, union membership, etc.); "
            "(h) real-time remote biometric identification in publicly "
            "accessible spaces by law enforcement (narrow exceptions). "
            "Art. 5(5) lets Member States impose stricter national laws on "
            "remote biometric ID. (Pending: Digital Omnibus political "
            "agreement of 7 May 2026 adds a 9th prohibition for AI systems "
            "generating CSAM or non-consensual intimate imagery, applying "
            "from 2 December 2026 once adopted.)"
        ),
    },
    "Art. 6": {
        "dimension": "risk_mgmt",
        "summary": (
            "Classifies an AI system as high-risk when it is intended as a safety "
            "component of a product covered by Annex I, or falls into one of the "
            "eight Annex III use cases."
        ),
    },
    "Art. 9": {
        "dimension": "risk_mgmt",
        "summary": (
            "Requires a documented, iterative risk-management system across the AI "
            "system's lifecycle covering known + foreseeable risks, residual-risk "
            "acceptability, and targeted testing for risk-control verification."
        ),
    },
    "Art. 10": {
        "dimension": "data_gov",
        "summary": (
            "Requires training, validation, and test datasets to be relevant, "
            "representative, free of errors, and complete; covers data-governance "
            "practices including provenance, preparation, bias examination + "
            "mitigation, and special-category personal data handling."
        ),
    },
    "Art. 11": {
        "dimension": "tech_docs",
        "summary": (
            "Requires technical documentation drawn up before placement on the "
            "market, kept up to date, demonstrating conformity to the essential "
            "requirements, with content per Annex IV. SMEs may use the simplified "
            "form supplied by the Commission."
        ),
    },
    "Art. 12": {
        "dimension": "tech_docs",
        "summary": (
            "Requires automatic logs of events relevant to identifying risks, "
            "post-market monitoring, and substantial modifications — retained at "
            "minimum 6 months."
        ),
    },
    "Art. 13": {
        "dimension": "transparency",
        "summary": (
            "Requires high-risk AI systems to be designed for sufficient operational "
            "transparency to deployers, accompanied by instructions for use covering "
            "provider identity, intended purpose, capabilities + limitations, "
            "expected lifetime, human-oversight measures, and required maintenance."
        ),
    },
    "Art. 14": {
        "dimension": "transparency",
        "summary": (
            "Requires effective human oversight by natural persons during system use "
            "— capability + limitation awareness, automation-bias safeguards, ability "
            "to interpret output, disregard / override / intervene, and (for biometric "
            "identification) a two-person verification rule."
        ),
    },
    "Art. 15": {
        "dimension": "risk_mgmt",
        "summary": (
            "Requires appropriate levels of accuracy, robustness, and cybersecurity "
            "across the lifecycle — accuracy metrics declared in instructions for "
            "use, resilience against errors, and resistance to data-poisoning, "
            "evasion, model-confidentiality, and adversarial attacks."
        ),
    },
    "Art. 17": {
        "dimension": "tech_docs",
        "summary": (
            "Requires providers of high-risk AI systems to operate a quality "
            "management system covering regulatory-compliance strategy, design "
            "verification, examination + test procedures, post-market monitoring, "
            "and incident-reporting workflows."
        ),
    },
    "Art. 26": {
        "dimension": "transparency",
        "summary": (
            "Deployer obligations: use the system per the instructions, assign "
            "human oversight to competent + trained natural persons, monitor "
            "operation, retain automatically generated logs, inform affected workers "
            "(for workplace use), and cooperate with market-surveillance authorities."
        ),
    },
    "Art. 27": {
        "dimension": "transparency",
        "summary": (
            "Deployers of certain high-risk AI systems (Annex III + public-sector "
            "deployers) must perform a Fundamental Rights Impact Assessment before "
            "first use, covering deployment process, affected persons, specific risks, "
            "human-oversight measures, and complaints workflows."
        ),
    },
    "Art. 50": {
        "dimension": "transparency",
        "summary": (
            "Transparency obligations: AI systems interacting with natural persons "
            "must disclose their AI nature; emotion-recognition + biometric-"
            "categorisation systems must inform exposed persons; deepfakes and "
            "AI-generated content must be labelled."
        ),
    },
    "Art. 53": {
        "dimension": "tech_docs",
        "summary": (
            "GPAI provider obligations: maintain technical documentation per "
            "Annex XI, supply downstream-provider information per Annex XII, "
            "implement a copyright policy, and publish a sufficiently detailed "
            "training-data summary."
        ),
    },
    "Art. 55": {
        "dimension": "risk_mgmt",
        "summary": (
            "GPAI systemic-risk provider obligations: model evaluation including "
            "adversarial testing, systemic-risk assessment + mitigation, serious-"
            "incident reporting to the AI Office, and adequate cybersecurity."
        ),
    },
    "Art. 72": {
        "dimension": "tech_docs",
        "summary": (
            "Requires a post-market monitoring plan + system documenting AI-system "
            "performance throughout its lifetime, with data collection, analysis, "
            "corrective-action workflows, and feedback into the risk-management "
            "system."
        ),
    },
    "Art. 99": {
        "dimension": "risk_mgmt",
        "summary": (
            "Penalty regime: up to EUR 35M or 7% of worldwide annual turnover for "
            "Article 5 prohibited-practice violations; up to EUR 15M / 3% for other "
            "obligations breaches; up to EUR 7.5M / 1% for incorrect or misleading "
            "information to authorities."
        ),
    },
    "Annex IV": {
        "dimension": "tech_docs",
        "summary": (
            "Technical documentation contents covering system description, design "
            "specifications, system architecture, data + training methodology, "
            "human oversight, risk-management measures, validation + testing "
            "procedures, and post-market monitoring system."
        ),
    },
    "Annex III": {
        "dimension": "risk_mgmt",
        "summary": (
            "Eight high-risk use-case categories: biometrics, critical infrastructure, "
            "education + vocational training, employment + worker management, "
            "essential private + public services, law enforcement, migration + asylum "
            "+ border control, and administration of justice + democratic processes."
        ),
    },
    # ─── Title I: Scope + Definitions (Arts. 1-4) ────────────────────────────
    "Art. 1": {
        "dimension": "governance",
        "summary": (
            "Lays down harmonised rules for placing on the market, putting into "
            "service, and use of AI systems in the Union; sets prohibitions, "
            "high-risk requirements, transparency obligations, GPAI rules, and "
            "innovation-support measures to ensure a high level of protection of "
            "health, safety, and fundamental rights."
        ),
    },
    "Art. 2": {
        "dimension": "governance",
        "summary": (
            "Scope: applies to providers placing AI systems on the EU market "
            "regardless of establishment, deployers established in the EU, "
            "providers/deployers in third countries whose output is used in the "
            "EU. Excludes military/defence/national-security uses, scientific "
            "R&D, purely personal non-professional use, and free/open-source "
            "AI systems outside the high-risk + prohibited + transparency scope."
        ),
    },
    "Art. 3": {
        "dimension": "governance",
        "summary": (
            "Defines 68 terms used in the Regulation, including 'AI system' "
            "(machine-based, varying autonomy, possibly adaptive, inferring from "
            "input how to generate output influencing physical/virtual "
            "environments), 'provider', 'deployer', 'placing on the market', "
            "'putting into service', 'substantial modification', 'general-"
            "purpose AI model', 'general-purpose AI system', 'systemic risk'."
        ),
    },
    "Art. 4": {
        "dimension": "governance",
        "summary": (
            "Requires providers and deployers to take measures to ensure a "
            "sufficient level of AI literacy among their staff and other persons "
            "dealing with AI systems on their behalf, considering technical "
            "knowledge, experience, education, training, and context of use."
        ),
    },
    # ─── Title III: High-risk providers + value chain (Arts. 7, 8, 16-25) ────
    "Art. 7": {
        "dimension": "risk_mgmt",
        "summary": (
            "Empowers the Commission to add, modify, or remove high-risk "
            "use-cases in Annex III by delegated act, based on criteria including "
            "intended purpose, extent of use, impact on health/safety/fundamental-"
            "rights, severity + reversibility of harm, and availability of "
            "redress."
        ),
    },
    "Art. 8": {
        "dimension": "risk_mgmt",
        "summary": (
            "Requires high-risk AI systems to comply with the requirements in "
            "Chapter III Section 2 (Arts. 9-15), taking into account their "
            "intended purpose, generally acknowledged state of the art, and the "
            "risk management system per Art. 9."
        ),
    },
    "Art. 16": {
        "dimension": "tech_docs",
        "summary": (
            "Provider obligations for high-risk AI: ensure system meets Section-2 "
            "requirements, indicate provider identity on the system, operate a "
            "quality-management system (Art. 17), keep documentation (Arts. 11 + "
            "18), keep logs (Art. 19), undertake conformity assessment (Art. 43), "
            "draw up declaration of conformity (Art. 47), affix CE marking (Art. "
            "48), register in EU database (Art. 49), take corrective actions (Art. "
            "20), and demonstrate compliance to authorities (Art. 21)."
        ),
    },
    "Art. 18": {
        "dimension": "tech_docs",
        "summary": (
            "Requires providers of high-risk AI to keep, for 10 years after the "
            "system is placed on the market, the technical documentation (Art. "
            "11), QMS documentation (Art. 17), notified-body documents (where "
            "applicable), declaration of conformity (Art. 47), and to make them "
            "available to national competent authorities on request."
        ),
    },
    "Art. 19": {
        "dimension": "tech_docs",
        "summary": (
            "Requires providers of high-risk AI to keep the logs automatically "
            "generated by the system (Art. 12) for a period appropriate to the "
            "intended purpose, at minimum 6 months, unless otherwise required by "
            "Union or national law."
        ),
    },
    "Art. 20": {
        "dimension": "post_market",
        "summary": (
            "Corrective-action obligation: where a provider considers or has "
            "reason to consider that a high-risk AI system placed on the market "
            "is not in conformity, they must take corrective actions (withdraw, "
            "disable, recall) and inform distributors, deployers, authorised "
            "representatives, and importers."
        ),
    },
    "Art. 22": {
        "dimension": "governance",
        "summary": (
            "Requires providers established outside the EU to appoint, by "
            "written mandate, an authorised representative established in the "
            "Union before placing a high-risk AI system on the market."
        ),
    },
    "Art. 23": {
        "dimension": "governance",
        "summary": (
            "Importer obligations for high-risk AI: verify that the provider has "
            "performed conformity assessment, drawn up technical documentation, "
            "affixed CE marking, accompanied the system with declaration of "
            "conformity + instructions for use, and appointed an authorised "
            "representative; indicate importer identity on the system."
        ),
    },
    "Art. 24": {
        "dimension": "governance",
        "summary": (
            "Distributor obligations for high-risk AI: verify CE marking, "
            "declaration of conformity, instructions for use, and that the "
            "provider + importer have complied with their obligations; take "
            "corrective action and inform authorities when non-compliance is "
            "identified."
        ),
    },
    "Art. 25": {
        "dimension": "governance",
        "summary": (
            "Responsibilities along the AI value chain: any distributor, "
            "importer, deployer, or third party becomes a provider (and assumes "
            "all provider obligations) if they put their name/trademark on the "
            "system, make a substantial modification, or modify the intended "
            "purpose making it high-risk."
        ),
    },
    # ─── Title III: Conformity, CE marking, registration (Arts. 43, 47-49) ───
    "Art. 43": {
        "dimension": "conformity",
        "summary": (
            "Requires providers of high-risk AI to undergo a conformity "
            "assessment: internal-control procedure (Annex VI) for Annex-III "
            "systems where harmonised standards / common specifications are "
            "applied, otherwise notified-body procedure (Annex VII); for Annex-I "
            "systems, the procedure under the relevant product-safety legislation."
        ),
    },
    "Art. 47": {
        "dimension": "conformity",
        "summary": (
            "Requires the provider to draw up a written, machine-readable, signed "
            "and dated EU declaration of conformity for each high-risk AI system, "
            "containing the information in Annex V, kept at the disposal of "
            "national competent authorities for 10 years."
        ),
    },
    "Art. 48": {
        "dimension": "conformity",
        "summary": (
            "Requires the CE marking to be affixed visibly, legibly, and "
            "indelibly to the high-risk AI system (or its packaging / "
            "documentation for digital-only systems), followed by the "
            "identification number of the notified body where applicable."
        ),
    },
    "Art. 49": {
        "dimension": "conformity",
        "summary": (
            "Requires providers (and deployers that are public authorities) to "
            "register themselves and their high-risk AI system in the EU "
            "database (Art. 71) before placing the system on the market or "
            "putting it into service."
        ),
    },
    # ─── Title V: General-Purpose AI (Arts. 51, 52, 54, 56) ──────────────────
    "Art. 51": {
        "dimension": "gpai_specific",
        "summary": (
            "Classifies a general-purpose AI model as having 'systemic risk' "
            "when it has high-impact capabilities (presumed when cumulative "
            "training compute exceeds 10^25 FLOPs) or when so designated by the "
            "Commission based on Annex XIII criteria."
        ),
    },
    "Art. 52": {
        "dimension": "gpai_specific",
        "summary": (
            "Procedure for GPAI-with-systemic-risk classification: providers "
            "must notify the Commission within 2 weeks of meeting / expecting to "
            "meet the threshold; provider may submit arguments against "
            "designation; Commission lists designated models publicly."
        ),
    },
    "Art. 54": {
        "dimension": "gpai_specific",
        "summary": (
            "Requires providers of GPAI models established outside the EU to "
            "appoint, by written mandate, an authorised representative "
            "established in the Union before placing the model on the market."
        ),
    },
    "Art. 56": {
        "dimension": "gpai_specific",
        "summary": (
            "AI Office encourages and facilitates voluntary codes of practice at "
            "Union level to contribute to proper application of the Regulation, "
            "particularly for GPAI obligations; codes may serve as a means to "
            "demonstrate compliance until harmonised standards are published."
        ),
    },
    # ─── Title VI: Innovation support (Arts. 57, 60) ─────────────────────────
    "Art. 57": {
        "dimension": "governance",
        "summary": (
            "Requires each Member State to establish at least one AI regulatory "
            "sandbox at national level, providing a controlled environment for "
            "developing, training, testing, and validating innovative AI systems "
            "for a limited time before placing on the market, with regulatory "
            "guidance and supervised mitigation of identified risks."
        ),
    },
    "Art. 60": {
        "dimension": "governance",
        "summary": (
            "Permits testing of high-risk AI systems in real-world conditions "
            "outside the sandbox, subject to a real-world-testing plan, "
            "informed consent of test subjects, registration in the EU "
            "database, and oversight by the market-surveillance authority."
        ),
    },
    # ─── Title VII: Governance (Arts. 64-66, 70) ─────────────────────────────
    "Art. 64": {
        "dimension": "governance",
        "summary": (
            "Establishes the AI Office within the Commission, tasked with "
            "supervising GPAI providers, contributing to enforcement, fostering "
            "Union-wide expertise, and supporting the European AI Board."
        ),
    },
    "Art. 65": {
        "dimension": "governance",
        "summary": (
            "Establishes the European Artificial Intelligence Board, composed "
            "of Member State representatives, with advisory + coordination "
            "duties: harmonised application of the Regulation, opinions on "
            "implementing acts, recommendations on enforcement priorities."
        ),
    },
    "Art. 66": {
        "dimension": "governance",
        "summary": (
            "Lists the Board's tasks: collect and share technical + regulatory "
            "expertise, advise on consistent application, contribute to "
            "harmonisation of administrative practices, issue recommendations + "
            "opinions on Commission requests."
        ),
    },
    "Art. 70": {
        "dimension": "governance",
        "summary": (
            "Requires each Member State to designate at least one notifying "
            "authority and at least one market-surveillance authority as "
            "national competent authorities, communicate their identity to the "
            "Commission, and ensure they have adequate technical + financial + "
            "human resources."
        ),
    },
    # ─── Title VIII: Post-market + enforcement (Arts. 71, 73, 74, 79) ───────
    "Art. 71": {
        "dimension": "governance",
        "summary": (
            "EU database for high-risk AI systems and GPAI models registered "
            "under Arts. 49 + 60, set up and managed by the Commission, with "
            "public + restricted-access sections; data is machine-readable + "
            "navigable + searchable."
        ),
    },
    "Art. 73": {
        "dimension": "post_market",
        "summary": (
            "Requires providers of high-risk AI systems placed on the EU "
            "market to report serious incidents to market-surveillance "
            "authorities of the Member State where the incident occurred — "
            "tiered deadlines: immediately for widespread infringement or "
            "critical-infrastructure disruption (and ≤ 2 days after "
            "awareness); ≤ 10 days for death; ≤ 15 days for other serious "
            "incidents (or immediately on established causal link). "
            "'Serious incident' (Art. 3(49)) covers death, serious "
            "irreversible critical-infrastructure disruption, fundamental-"
            "rights violation, or serious property / environmental harm. "
            "Dual reporting exemption for medical devices (Reg. 2017/745) "
            "and IVDs (Reg. 2017/746) except fundamental-rights infringements."
        ),
    },
    "Art. 74": {
        "dimension": "governance",
        "summary": (
            "Designates market-surveillance authorities and integrates AI-Act "
            "enforcement with Regulation (EU) 2019/1020; authorities have full "
            "investigation + corrective-measure powers, including access to "
            "source code where strictly necessary."
        ),
    },
    "Art. 79": {
        "dimension": "post_market",
        "summary": (
            "Procedure for handling AI systems presenting a risk: market-"
            "surveillance authority evaluates, requires corrective action, "
            "informs Commission + other authorities; Commission may extend the "
            "measures across the Union or propose a Union safeguard procedure."
        ),
    },
    # ─── Title XII / final provisions (Art. 113 — applicability dates) ───────
    "Art. 113": {
        "dimension": "governance",
        "summary": (
            "Entry into force + application (Regulation 2024/1689): in force "
            "1 August 2024; applies generally from 2 August 2026; "
            "prohibitions (Art. 5) + AI literacy (Art. 4) from 2 February "
            "2025; GPAI obligations (Chapter V) from 2 August 2025; "
            "high-risk Annex I systems from 2 August 2027; pre-existing "
            "high-risk for public-authority use from 2 August 2030. (Pending: "
            "the Digital Omnibus political agreement of 7 May 2026 defers "
            "Annex III high-risk obligations to 2 December 2027 and Annex I "
            "embedded-product obligations to 2 August 2028, with a "
            "transitional period for Art. 50(2) watermarking on legacy "
            "systems running until 2 December 2026 — not yet adopted but "
            "expected before 2 August 2026.)"
        ),
    },
    # ─── Additional Annexes ──────────────────────────────────────────────────
    "Annex I": {
        "dimension": "risk_mgmt",
        "summary": (
            "Union harmonisation legislation list (Section A: New Legislative "
            "Framework — machinery, toys, radio equipment, medical devices, "
            "lifts, etc.; Section B: civil aviation, motor vehicles, marine "
            "equipment, rail, agricultural vehicles) — AI safety-components of "
            "products covered here are classified high-risk under Art. 6(1)."
        ),
    },
    "Annex VI": {
        "dimension": "conformity",
        "summary": (
            "Conformity-assessment procedure based on internal control: "
            "provider verifies the QMS conforms to Art. 17, examines the "
            "technical documentation, verifies design + development + "
            "post-market plan; no notified-body involvement required."
        ),
    },
    "Annex VII": {
        "dimension": "conformity",
        "summary": (
            "Conformity assessment based on assessment of QMS + technical "
            "documentation with notified-body involvement: applies to Annex-"
            "III biometric systems when harmonised standards aren't fully "
            "applied — notified body audits QMS, examines technical "
            "documentation, issues EU technical-documentation assessment "
            "certificate."
        ),
    },
    "Annex XI": {
        "dimension": "gpai_specific",
        "summary": (
            "Technical documentation that GPAI providers must draw up + keep "
            "up to date: general description (tasks, integration paradigms, "
            "acceptable-use policies, release date + distribution methods), "
            "model architecture + parameter count, modality + format, "
            "licensing, training process, data + compute used, energy "
            "consumption, evaluation results."
        ),
    },
    "Annex XII": {
        "dimension": "gpai_specific",
        "summary": (
            "Information GPAI providers must supply to downstream providers "
            "integrating the model into their AI systems: tasks the model is "
            "intended to perform, type + nature of AI systems in which it can "
            "be integrated, acceptable use policies, training-data summary, "
            "computational + hardware resources required, model size, expected "
            "input + output modalities."
        ),
    },
    "Annex XIII": {
        "dimension": "gpai_specific",
        "summary": (
            "Criteria for designating a GPAI model as systemic-risk: number of "
            "parameters, dataset quality + size, training compute, input + "
            "output modalities, benchmarks + capability evaluations, reach "
            "(business users / EU registered end-users), registered users."
        ),
    },
    # ─── Title III: Cooperation duty (Art. 21) ───────────────────────────────
    "Art. 21": {
        "dimension": "governance",
        "summary": (
            "Providers of high-risk AI systems must, upon a reasoned request "
            "from a national competent authority, provide all information + "
            "documentation necessary to demonstrate conformity with Section-2 "
            "requirements, in an official Union language. Information shared "
            "is treated as confidential (IP, trade secrets, source code per "
            "Art. 78)."
        ),
    },
    # ─── Title III: Art. 6(3) — non-high-risk carve-out for Annex III ────────
    "Art. 6.3": {
        "dimension": "risk_mgmt",
        "summary": (
            "Carve-out: an Annex-III system is NOT high-risk if it doesn't "
            "pose a significant risk of harm AND one of four conditions is "
            "met — (a) performs a narrow procedural task; (b) improves the "
            "result of a previously completed human activity; (c) detects "
            "decision-making patterns or deviations without replacing the "
            "human assessment; (d) performs a preparatory task to an "
            "Annex-III use case. Kill-switch: the exception does NOT apply "
            "when the system performs profiling of natural persons. Provider "
            "must document the assessment before placing on market and "
            "still register the system per Art. 49(2)."
        ),
    },
    # ─── Title V: Art. 50 sub-articles — transparency obligations ────────────
    "Art. 50.1": {
        "dimension": "transparency",
        "summary": (
            "Provider obligation: AI systems intended to interact directly "
            "with natural persons must be designed so that affected persons "
            "are informed they are interacting with an AI system (unless "
            "obvious from context). Exception for AI systems authorised "
            "by law to detect / prevent / investigate criminal offences, "
            "subject to safeguards — but the exception is reversed when the "
            "system is available to the public to report criminal offences."
        ),
    },
    "Art. 50.2": {
        "dimension": "transparency",
        "summary": (
            "Provider obligation: providers of generative AI systems "
            "(including GPAI) that generate synthetic audio, image, video, "
            "or text content must ensure outputs are marked in a machine-"
            "readable format and detectable as artificially generated / "
            "manipulated — solutions must be effective, interoperable, "
            "robust, and reliable. Exemptions: standard editing functions "
            "that don't substantially alter input data; legal authorisation "
            "for criminal-investigation use."
        ),
    },
    "Art. 50.3": {
        "dimension": "transparency",
        "summary": (
            "Deployer obligation: deployers of emotion-recognition or "
            "biometric-categorisation systems must inform exposed natural "
            "persons and process personal data per GDPR / LED / EUDPR. "
            "Exceptions: systems used for detecting / preventing / "
            "investigating criminal offences (with safeguards); ancillary "
            "use inseparable from the primary service (Recital 16)."
        ),
    },
    "Art. 50.4": {
        "dimension": "transparency",
        "summary": (
            "Deployer obligation: deployers of AI that generates deep fakes "
            "must disclose the content is artificially generated. Deployers "
            "of AI that generates / manipulates text published to inform "
            "the public on matters of public interest must disclose AI "
            "origin. Exceptions: artistic / creative / satirical / fictional "
            "works (relaxed disclosure that doesn't disrupt the work); "
            "legal authorisation for criminal investigation; AI-generated "
            "text where a human reviewer or editor takes editorial "
            "responsibility."
        ),
    },
    # ─── Title VI: Sandbox + real-world testing detail (Arts. 58, 59, 61, 62, 63) ─
    "Art. 58": {
        "dimension": "governance",
        "summary": (
            "Sandbox modalities + detailed arrangements set by Commission "
            "implementing acts covering eligibility, application, selection, "
            "participation, monitoring, exit, termination, and applicable "
            "T&C. Sandboxes provide controlled environment with regulatory "
            "guidance + safeguarded mitigation of identified risks."
        ),
    },
    "Art. 59": {
        "dimension": "data_gov",
        "summary": (
            "Personal data processing in AI regulatory sandboxes is lawful "
            "under conditions: (1) substantial public interest (public "
            "health, energy sustainability, critical-infrastructure safety, "
            "etc.); (2) strict necessity — no anonymised or synthetic "
            "alternative; (3) separate protected sandbox environment with "
            "technical + organisational measures; (4) full description of "
            "training / testing / validation processes retained with "
            "results; processing must not adversely affect data subjects."
        ),
    },
    "Art. 61": {
        "dimension": "governance",
        "summary": (
            "Informed consent for real-world testing outside the sandbox "
            "(Art. 60): test subjects must give freely, specifically, "
            "informed, unambiguous, prior consent, with right to withdraw "
            "without detriment; participation must not adversely affect "
            "subjects; outcomes reversible / disregardable. Records of "
            "consent retained alongside testing plan."
        ),
    },
    "Art. 62": {
        "dimension": "governance",
        "summary": (
            "Measures for providers + deployers, in particular SMEs "
            "including start-ups: priority access to sandboxes (free for "
            "SMEs), specific awareness + training activities, dedicated "
            "communication channels, fee reductions for conformity "
            "assessment + database registration proportionate to size + "
            "market stage. (Digital Omnibus political agreement of 7 May "
            "2026 extends these privileges to 'small mid-cap' enterprises.)"
        ),
    },
    "Art. 63": {
        "dimension": "governance",
        "summary": (
            "Derogations for SMEs (and post-Omnibus small mid-caps): "
            "simplified compliance with Art. 17 quality-management-system "
            "obligations in a manner appropriate to size + market stage, "
            "without compromising the level of protection or compliance "
            "with the Section-2 requirements."
        ),
    },
    # ─── Title VII: Advisory Forum + Scientific Panel (Arts. 67, 68, 69) ─────
    "Art. 67": {
        "dimension": "governance",
        "summary": (
            "Establishes an Advisory Forum to provide technical expertise + "
            "advice to the Board + Commission, with balanced selection of "
            "stakeholders (industry, start-ups, SMEs, civil society, "
            "academia). Members appointed for renewable 2-year terms."
        ),
    },
    "Art. 68": {
        "dimension": "governance",
        "summary": (
            "Establishes a Scientific Panel of independent experts to "
            "support enforcement of Chapter V (GPAI) by alerting the AI "
            "Office to systemic risks, contributing to development of "
            "tools + methodologies for evaluating capabilities of GPAI "
            "models, and providing advice on classification of GPAI models "
            "with systemic risk."
        ),
    },
    "Art. 69": {
        "dimension": "governance",
        "summary": (
            "National competent authorities may request access to the "
            "Scientific Panel's expert pool for support in enforcing the "
            "Regulation, against a fee determined by the Commission to "
            "cover Panel-related costs."
        ),
    },
    # ─── Title VIII: Enforcement + remedies (Arts. 85, 86, 87, 89) ───────────
    "Art. 85": {
        "dimension": "post_market",
        "summary": (
            "Right to lodge a complaint with a market-surveillance "
            "authority. Broader than GDPR Art. 77: any natural OR legal "
            "person may complain about any infringement of the AI Act "
            "(not just infringements affecting their own rights). "
            "Authorities must inform complainants of the progress + outcome "
            "of the complaint within reasonable time, including possible "
            "judicial remedies under Art. 86."
        ),
    },
    "Art. 86": {
        "dimension": "post_market",
        "summary": (
            "Right to explanation of individual decision-making: any "
            "affected person subject to a decision taken by the deployer "
            "on the basis of output from a high-risk AI system listed in "
            "Annex III (excluding Annex III(2) critical infrastructure) — "
            "where the decision produces legal effects or similarly "
            "significant adverse effects on health, safety, or fundamental "
            "rights — has the right to obtain from the deployer clear + "
            "meaningful explanation of the AI system's role in the "
            "decision-making procedure and the main elements of the "
            "decision. Complements (does not replace) GDPR Art. 22."
        ),
    },
    "Art. 87": {
        "dimension": "post_market",
        "summary": (
            "Whistleblower protection: reporting of infringements of the "
            "AI Act and protection of persons reporting such infringements "
            "is governed by Directive (EU) 2019/1937 (the EU "
            "Whistleblowing Directive)."
        ),
    },
    "Art. 89": {
        "dimension": "post_market",
        "summary": (
            "Downstream-provider complaints to the AI Office regarding a "
            "GPAI model: must be well-substantiated and contain the "
            "complainant's provider identity + contact details, a "
            "description of the relevant facts + the provisions of the "
            "Regulation concerned, the reasons why the complainant "
            "considers an infringement has occurred, and any other "
            "information considered relevant."
        ),
    },
    # ─── Title IX: Codes of conduct + penalties (Arts. 95, 100, 101) ─────────
    "Art. 95": {
        "dimension": "governance",
        "summary": (
            "Voluntary codes of conduct: the AI Office + Member States "
            "encourage providers of non-high-risk AI systems to voluntarily "
            "apply some or all of the Section-2 high-risk requirements, "
            "adapted to intended purpose + risk. Codes must be based on "
            "clear objectives + KPIs measuring achievement; inclusive "
            "development. Applies from 2 August 2026. Commission evaluates "
            "impact by 2 August 2028 and every 3 years thereafter."
        ),
    },
    "Art. 100": {
        "dimension": "governance",
        "summary": (
            "Penalties for EU institutions, bodies, offices, and agencies "
            "imposed by the European Data Protection Supervisor (EDPS): up "
            "to EUR 1 500 000 for Art. 5 prohibited-practice violations, "
            "and up to EUR 750 000 for other infringements. Fines must not "
            "impair operational effectiveness of the institution; collected "
            "funds accrue to the Union general budget."
        ),
    },
    "Art. 101": {
        "dimension": "gpai_specific",
        "summary": (
            "GPAI penalties: the Commission may impose fines on GPAI model "
            "providers of up to EUR 15 000 000 or 3 % of worldwide annual "
            "turnover (whichever is higher) for breaches of Chapter V "
            "obligations, supplying incorrect / incomplete / misleading "
            "information, or failing to comply with a Commission request "
            "for measures. Applies from 2 August 2026. Provider has right "
            "to be heard; CJEU judicial review."
        ),
    },
    # ─── Title XII: Transition + review (Arts. 111, 112) ─────────────────────
    "Art. 111": {
        "dimension": "governance",
        "summary": (
            "Transitional provisions for AI systems and GPAI models already "
            "on the market / in service: high-risk AI for public-authority "
            "use placed on the market before 2 August 2026 must comply "
            "from 2 August 2030 (only if significant design change); pre-"
            "2 August 2025 GPAI models brought into compliance by 2 August "
            "2027; large-scale IT systems listed in Annex X covered by the "
            "Regulation from 31 December 2030."
        ),
    },
    "Art. 112": {
        "dimension": "governance",
        "summary": (
            "Commission evaluation + review: annual assessment of the need "
            "to amend the list of prohibited practices in Art. 5 and the "
            "list of Annex III high-risk use cases; biennial review of "
            "Member-State penalty regimes (Art. 99) and the AI Office's "
            "functioning; comprehensive review by 2 August 2028 and every "
            "4 years thereafter, reporting to the Parliament + Council."
        ),
    },
    # ─── Additional Annexes (II, V, VIII) ────────────────────────────────────
    "Annex II": {
        "dimension": "risk_mgmt",
        "summary": (
            "List of criminal offences referred to in Art. 5(1)(h) "
            "permitting real-time remote biometric identification by law "
            "enforcement: terrorism, trafficking in human beings, sexual "
            "exploitation of children, illicit trafficking in narcotic drugs "
            "/ weapons / nuclear material, murder, kidnapping, rape, armed "
            "robbery, organised crime, participation in a criminal "
            "organisation, environmental crime — provided the offence is "
            "punishable in the relevant Member State by a custodial "
            "sentence of at least 4 years."
        ),
    },
    "Annex V": {
        "dimension": "conformity",
        "summary": (
            "EU declaration of conformity contents: system name + type + "
            "additional unambiguous reference; provider identity (+ "
            "authorised representative); statement that the DoC is issued "
            "under sole responsibility of the provider; statement of "
            "conformity with the Regulation + applicable Union "
            "harmonisation legislation; references to harmonised standards "
            "or common specifications applied; notified-body identity + "
            "certificate reference where applicable; date + signatory + "
            "function."
        ),
    },
    "Annex VIII": {
        "dimension": "governance",
        "summary": (
            "Information for registration in the EU database (Art. 49): "
            "Section A populated by provider / authorised representative "
            "(system name, intended purpose, components/datasets, design "
            "specifications, instructions for use, CE marking, conformity-"
            "assessment certificate, supervisory authority); Section B for "
            "Art. 6(3) non-high-risk assessments; Section C populated by "
            "public-authority deployers. Public-access carve-out for law "
            "enforcement / migration / asylum / border-control systems."
        ),
    },
    # ─── Title III Ch. 4: Notified-body lifecycle (Arts. 28-34) ──────────────
    "Art. 28": {
        "dimension": "conformity",
        "summary": (
            "Requires each Member State to designate or establish at least "
            "one notifying authority responsible for setting up and carrying "
            "out the procedures for assessment, designation, notification, "
            "and monitoring of conformity-assessment bodies. Art. 28(2)-(4) "
            "require notifying authorities to be objective + impartial, "
            "organised so notification decisions are taken by competent "
            "persons different from those who carried out the assessment, "
            "and to safeguard the confidentiality of information obtained."
        ),
    },
    "Art. 29": {
        "dimension": "conformity",
        "summary": (
            "Sets the application procedure for conformity-assessment bodies "
            "seeking notification under Art. 28(1)(b): the body must submit "
            "the application to the notifying authority of the Member State "
            "in which it is established, together with a description of the "
            "conformity-assessment activities, modules, AI technologies, and "
            "evidence of compliance with the Art. 31 requirements. Per Art. "
            "29(2)-(3) an accreditation certificate from a national "
            "accreditation body may serve as such evidence."
        ),
    },
    "Art. 31": {
        "dimension": "conformity",
        "summary": (
            "Sets substantive requirements that notified bodies must meet "
            "and continuously satisfy: establishment under national law with "
            "legal personality (Art. 31(1)), independence from the provider "
            "and from the system being assessed (Art. 31(4)), no involvement "
            "in design / marketing / use of the AI systems they assess "
            "(Art. 31(5)), safeguards against conflicts of interest, "
            "documented procedures, sufficient permanent personnel with "
            "appropriate competences in AI technologies + data + computing, "
            "and adequate cybersecurity. Per Art. 31(12) notified bodies "
            "must hold appropriate liability insurance unless that "
            "liability is assumed by the Member State."
        ),
    },
    "Art. 33": {
        "dimension": "conformity",
        "summary": (
            "Sets operational obligations of notified bodies when carrying "
            "out conformity-assessment activities under Annex VII: "
            "assessments must be carried out proportionately, avoiding "
            "unnecessary burdens for providers, with particular regard for "
            "the size of the provider, the sector of operation, and the "
            "degree of complexity of the AI system (Art. 33(1)). Art. 33(2)-"
            "(4) require notified bodies to respect the degree of rigour + "
            "level of protection required, make publicly available fees, "
            "and notify the notifying authority of any refusal, restriction, "
            "suspension, or withdrawal of certificates."
        ),
    },
    "Art. 34": {
        "dimension": "conformity",
        "summary": (
            "Governs subsidiaries and subcontracting by notified bodies: "
            "where a notified body subcontracts specific assessment tasks "
            "or has recourse to a subsidiary, it must ensure the "
            "subcontractor / subsidiary meets the Art. 31 requirements and "
            "inform the notifying authority accordingly (Art. 34(1)-(2)). "
            "The notified body remains fully responsible for the tasks "
            "performed by subcontractors or subsidiaries, and "
            "subcontracting / subsidiary recourse may only take place with "
            "the agreement of the provider."
        ),
    },
    # ─── Title III Ch. 5: Harmonised standards + common specs (Arts. 40-42) ──
    "Art. 40": {
        "dimension": "conformity",
        "summary": (
            "High-risk AI systems and GPAI models in conformity with "
            "harmonised standards (or parts thereof) whose references have "
            "been published in the Official Journal under Regulation (EU) "
            "No 1025/2012 are presumed to conform with the corresponding "
            "Section-2 requirements of Chapter III, or with the Chapter V "
            "GPAI obligations, to the extent those standards cover those "
            "requirements (Art. 40(1)). Art. 40(2)-(3) require the "
            "Commission to issue standardisation requests covering the "
            "essential requirements without undue delay, and to promote "
            "stakeholder involvement in the European standardisation "
            "process."
        ),
    },
    "Art. 41": {
        "dimension": "conformity",
        "summary": (
            "Empowers the Commission to adopt, by implementing acts, common "
            "specifications for the Section-2 high-risk requirements or for "
            "the Chapter V GPAI obligations where harmonised standards do "
            "not exist, the Commission's standardisation request was not "
            "accepted, the request is unduly delayed, or the resulting "
            "standards are insufficient (Art. 41(1)). High-risk AI systems "
            "(and GPAI models) in conformity with such common specifications "
            "are presumed to conform with the corresponding requirements "
            "(Art. 41(3)). Providers that do not apply the common "
            "specifications must justify equivalent technical solutions."
        ),
    },
    "Art. 42": {
        "dimension": "conformity",
        "summary": (
            "Adds two further presumptions of conformity beyond Arts. 40-41: "
            "Art. 42(1) — high-risk AI systems trained and tested on data "
            "reflecting the specific geographical, behavioural, contextual, "
            "or functional setting in which they are intended to be used are "
            "presumed to comply with the relevant data-governance "
            "requirements of Art. 10(4); Art. 42(2) — high-risk AI systems "
            "certified or for which a statement of conformity has been "
            "issued under a cybersecurity scheme under Regulation (EU) "
            "2019/881 (the Cybersecurity Act) and whose references are "
            "published in the Official Journal are presumed to comply with "
            "the cybersecurity requirements of Art. 15 to the extent the "
            "cybersecurity certificate or statement covers those "
            "requirements."
        ),
    },
    # ─── Title VIII: Confidentiality + GPAI enforcement (Arts. 78, 88) ───────
    "Art. 78": {
        "dimension": "governance",
        "summary": (
            "Confidentiality obligation binding the Commission, market-"
            "surveillance authorities, notified bodies, and any other "
            "natural or legal person involved in the application of the "
            "Regulation: they must respect the confidentiality of "
            "information and data obtained in carrying out their tasks, in "
            "particular to protect intellectual-property rights, "
            "confidential business information + trade secrets (including "
            "source code, except as Art. 74(13) allows), the effective "
            "implementation of the Regulation (including investigations), "
            "public + national security interests, and the integrity of "
            "criminal / administrative proceedings (Art. 78(1)). Art. "
            "78(2)-(4) qualify intra-authority + cross-border information "
            "exchange."
        ),
    },
    "Art. 88": {
        "dimension": "gpai_specific",
        "summary": (
            "Vests enforcement of the Chapter V obligations of providers of "
            "general-purpose AI models exclusively in the Commission, acting "
            "through the AI Office, which exercises the powers laid down in "
            "the Regulation without prejudice to the institutional powers "
            "set out in the Treaties (Art. 88(1)). Art. 88(2) requires the "
            "Commission and the Member States to cooperate, in particular "
            "where a GPAI model is integrated into an AI system over which "
            "national market-surveillance authorities have competence under "
            "Art. 74."
        ),
    },
    # ─── Additional Annexes (IX, X) ──────────────────────────────────────────
    "Annex IX": {
        "dimension": "governance",
        "summary": (
            "Annex IX lists the Union legislative acts on large-scale IT "
            "systems in the area of freedom, security and justice referred "
            "to in Art. 6(1) and Art. 111: the Schengen Information System "
            "(SIS), the Visa Information System (VIS), Eurodac, the Entry/"
            "Exit System (EES), the European Travel Information and "
            "Authorisation System (ETIAS), the regulations on "
            "interoperability between EU information systems, and the "
            "European Criminal Records Information System for third-country "
            "nationals (ECRIS-TCN). AI systems intended to be used as safety "
            "components of, or by Union institutions in the management of, "
            "the IT systems listed in Annex IX fall under the high-risk "
            "regime with transitional dates set by Art. 111(1)."
        ),
    },
    "Annex X": {
        "dimension": "tech_docs",
        "summary": (
            "Annex X sets the information that providers (and, where "
            "applicable, authorised representatives) and public-authority "
            "deployers must enter in the EU database when registering "
            "high-risk AI systems referred to in Art. 49: provider / "
            "authorised-representative / deployer identity + contact "
            "details, system name + trade name + additional unambiguous "
            "reference, intended purpose, status of the system (on the "
            "market / in service / no longer placed on the market / "
            "recalled), type + number of the conformity-assessment "
            "certificate + identity of the issuing notified body where "
            "applicable, Member States in which the system is placed on "
            "the market or put into service, and a copy of the EU "
            "declaration of conformity (Art. 47) + the instructions for "
            "use. Public-access carve-outs in Annex X apply to law-"
            "enforcement, migration, asylum, and border-control systems."
        ),
    },
}
