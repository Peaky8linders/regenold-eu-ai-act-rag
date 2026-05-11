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
)


def get_dimensions_for_risk_level(risk_level: str | None) -> tuple[MaturityDimension, ...]:
    """Return dimensions in scope for ``risk_level``.

    The minimal bundle returns the full 4-dimension stub for every risk
    level. The full CodexAI implementation maps each level to a subset.
    """
    if risk_level not in {"high", "limited", "minimal", "unacceptable", None}:
        raise ValueError(f"Unknown risk level: {risk_level!r}")
    return MATURITY_DIMENSIONS


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
            "Prohibits eight categories of AI practice (subliminal manipulation, "
            "exploitation of vulnerabilities, social scoring, predictive policing of "
            "individuals, untargeted facial-image scraping, emotion recognition in "
            "workplaces and education, biometric categorisation by protected "
            "attribute, and real-time remote biometric identification in public spaces)."
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
            "market to report any serious incident to the market-surveillance "
            "authorities of Member States where the incident occurred — "
            "immediately, and no later than 15 days after becoming aware (2 "
            "days for widespread infringement or critical-infrastructure "
            "disruption, 10 days for death)."
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
            "Entry into force + application: enters into force 20 days after "
            "publication (2 August 2024); applies from 2 August 2026 generally; "
            "prohibitions (Art. 5) + AI-literacy (Art. 4) from 2 February 2025; "
            "GPAI obligations (Chapter V) from 2 August 2025; high-risk systems "
            "covered by Annex I from 2 August 2027."
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
}
