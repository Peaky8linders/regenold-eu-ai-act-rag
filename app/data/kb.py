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
# IMPORTANT: bump this string whenever EC_CHECKER_OBLIGATION_MAP / the
# canonical stub set changes. The engine LRU cache key
# (`app/routes/regenold.py::_engine_cache_key`) folds KB_VERSION into
# its sha256, AND the Neo4j auto-seed
# (`app/main.py::_maybe_auto_seed_neo4j`) skips re-seeding when the
# stored seed_version matches. R53.2 edited Art. 25 + Art. 101 stubs
# without bumping the string — the deep-code-review (R54.1) caught
# this as a cache+seed staleness bug. R54.1 fixes that by bumping v2
# → v3 to invalidate both surfaces. R57-B bumps v3 → v4 for the R57
# KB coverage audit additions (Art. 5 sub-point carve-outs, Art. 6
# Omnibus deferral, Art. 13 Art. 26(11) carry-over, Art. 14 two-
# person rule scope, Art. 22 mandate tasks, Art. 26 carve-outs,
# Art. 52(4) open-source designation, Art. 53(2) FOSS carve-out,
# Art. 55 four systemic-risk obligations, Art. 79 market-surveillance
# procedure).
KB_VERSION = "2024.1689.v5"


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


class _KBEntry(dict):
    """KB entry that iterates as a tuple of summary-stub strings.

    The R38 Tier-1 2026 content audit (nudification ban, dual-vintage
    Art. 50 watermark deadline, GPAI Code of Practice signatories,
    Art. 53 training-data template) needs each new prose stub to be
    auditable independently, so the test fixture does:

        blob = " ".join(EC_CHECKER_OBLIGATION_MAP["Art. 5"]).lower()

    A plain dict iterates keys (``"dimension"`` and ``"summary"``),
    which would defeat the audit. This subclass:

    * iterates the per-stub strings (``" ".join(entry)`` joins prose);
    * keeps ``entry["summary"]`` returning the joined string so every
      existing consumer (``kb_search``, ``kb_xrefs`` regex finder,
      ``graph_rag`` retrieval, ``seed_neo4j_kb`` text loader) sees a
      ``str`` value identical in shape to the legacy dict literal;
    * keeps ``entry.items()`` / ``entry.get("dimension")`` / ``entry.get(
      "summary", "")`` all returning the same values as before.

    Used only by the 4 R38-touched entries (Art. 5, 50, 53, 56). All
    other 100+ entries stay as plain ``dict[str, str]`` literals.
    """

    __slots__ = ("_stubs",)

    def __init__(self, *, dimension: str, stubs: tuple[str, ...]):
        if not stubs:
            raise ValueError("_KBEntry requires at least one stub string")
        joined = " ".join(stubs)
        super().__init__(dimension=dimension, summary=joined)
        object.__setattr__(self, "_stubs", tuple(stubs))

    def __iter__(self):  # type: ignore[override]
        return iter(self._stubs)


EC_CHECKER_OBLIGATION_MAP: dict[str, dict[str, str]] = {
    "Art. 5": _KBEntry(
        dimension="risk_mgmt",
        stubs=(
            (
                "Art. 5: Prohibits eight categories of AI practice: (a) "
                "subliminal / manipulative / deceptive techniques causing "
                "significant harm; (b) exploitation of vulnerabilities by "
                "age, disability, or socio-economic situation; (c) social "
                "scoring leading to unjustified detrimental treatment in "
                "unrelated contexts; (d) profiling for criminal-risk "
                "assessment based solely on personality traits (exception "
                "for human-assessment support on objective facts); (e) "
                "untargeted scraping of facial images for facial-recognition "
                "databases; (f) emotion-inference in workplaces and "
                "educational institutions (narrow medical / safety "
                "exception); (g) biometric categorisation by sensitive "
                "attributes — race, ethnicity, political views, religious or "
                "philosophical beliefs, trade-union membership, sex life or "
                "sexual orientation; "
                "(h) real-time remote biometric identification in publicly "
                "accessible spaces by law enforcement (narrow exceptions). "
                "Art. 5(5) lets Member States impose stricter national laws "
                "on remote biometric ID."
            ),
            (
                "Art. 5: Digital Omnibus political agreement (7 May 2026) "
                "added a new sub-paragraph to Art. 5(1) prohibiting AI "
                "systems that generate non-consensual sexual or intimate "
                "content and child sexual abuse material ('nudification' "
                "apps and CSAM generators). Applies 2 December 2026. "
                "Maximum fine €35 M or 7 % of global turnover under "
                "Art. 99."
            ),
            (
                "Art. 5(1)(c) carve-out: the social-scoring prohibition "
                "does not affect lawful evaluation practices of natural "
                "persons that are carried out for a specific purpose in "
                "accordance with Union and national law (Recital 31 final "
                "sentence). The prohibited conduct is scoring across "
                "unrelated social contexts producing unjustified detrimental "
                "treatment; targeted lawful evaluation for a specific "
                "purpose under Union or national law remains permitted."
            ),
            (
                "Art. 5(1)(f) carve-out: emotion-recognition systems "
                "placed on the market strictly for medical or safety "
                "reasons — including systems intended for therapeutical "
                "use, fatigue detection in pilots/drivers for accident "
                "prevention, and pain/fatigue physical-state monitoring "
                "(which Recital 18 expressly excludes from the 'emotion' "
                "definition itself) — are NOT prohibited (Recital 44 "
                "final sentence). The carve-out is narrow: the system's "
                "primary purpose at market-placement must be medical or "
                "safety, not retrofittable post-hoc."
            ),
            (
                "Art. 5(1)(g) carve-out: the biometric-categorisation "
                "prohibition does not cover lawful labelling, filtering "
                "or categorisation of biometric datasets acquired in line "
                "with Union or national law — including sorting by hair "
                "colour or eye colour, which is permitted in law-"
                "enforcement contexts (Recital 30)."
            ),
            (
                "Art. 5(1)(h) carve-out catalogue: real-time remote "
                "biometric identification in publicly accessible spaces "
                "by law enforcement is permitted only for three exhaustive "
                "law-enforcement objectives — (i) targeted search for "
                "victims of abduction, trafficking and sexual exploitation, "
                "and missing persons; (ii) prevention of a specific, "
                "substantial and imminent threat to life or physical "
                "safety, or a genuine and foreseeable terrorist attack; "
                "(iii) localisation or identification of suspects of "
                "Annex II offences punishable by at least 4 years' "
                "custody. Use requires prior FRIA (Art. 27), Art. 49 "
                "EU-database registration, prior judicial or independent-"
                "administrative authorisation (urgency exception: "
                "authorisation within 24h, else immediate stop), and "
                "notification of the relevant market-surveillance "
                "authority and national data-protection authority."
            ),
        ),
    ),
    "Art. 6": {
        "dimension": "risk_mgmt",
        "summary": (
            "Classifies an AI system as high-risk when it is intended as a safety "
            "component of a product covered by Annex I, or falls into one of the "
            "eight Annex III use cases. Per the Digital Omnibus political "
            "agreement (7 May 2026), Annex III high-risk applicability is "
            "deferred to 2 December 2027 (originally 2 August 2026), and Annex I "
            "embedded-product high-risk applicability is deferred to 2 August "
            "2028, to allow harmonised standards and AI Office guidelines to "
            "land first."
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
            "expected lifetime, human-oversight measures, and required maintenance. "
            "Where the high-risk system is an Annex-III biometric-identification, "
            "emotion-recognition, or biometric-categorisation system, Art. 26(11) "
            "preserves the Art. 50 transparency-to-end-user obligations on top of "
            "the Art. 13 transparency-to-deployer chain."
        ),
    },
    "Art. 14": {
        "dimension": "transparency",
        "summary": (
            "Requires effective human oversight by natural persons during system use "
            "— capability + limitation awareness, automation-bias safeguards, ability "
            "to interpret output, disregard / override / intervene, and (for biometric "
            "identification) a two-person verification rule. Under Art. 14(5), no "
            "action or decision may be taken by the deployer on the basis of "
            "identification resulting from an Annex-III point-1(a) remote biometric "
            "identification system unless that identification has been separately "
            "verified and confirmed by at least two natural persons with the "
            "necessary competence, training and authority. The two-person rule does "
            "not apply where Union or national law considers its application "
            "disproportionate for law-enforcement, migration, asylum or border-"
            "control authorities (Art. 14(5) second subparagraph)."
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
            "(for workplace use), and cooperate with market-surveillance authorities. "
            "Art. 26 carve-outs: deployers that are financial institutions subject "
            "to Union financial-services internal-governance requirements fulfil "
            "the Art. 26(5) monitoring obligation and the Art. 26(6) log-retention "
            "obligation by complying with the governance arrangements under that "
            "financial-services law (Art. 26(5) second subparagraph; Art. 26(6) "
            "second subparagraph). Workplace deployers who are employers must "
            "inform workers' representatives and the affected workers BEFORE "
            "putting the high-risk system into service (Art. 26(7)); applicable "
            "Union and national worker-information rules continue to apply."
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
    "Art. 50": _KBEntry(
        dimension="transparency",
        stubs=(
            (
                "Art. 50: Transparency obligations: AI systems interacting "
                "with natural persons must disclose their AI nature; "
                "emotion-recognition + biometric-categorisation systems must "
                "inform exposed persons; deepfakes and AI-generated content "
                "must be labelled."
            ),
            (
                "Art. 50(2): Generative-AI output watermarking — the base "
                "Regulation set the obligation in force from 2 August 2026. "
                "The May 2026 Digital Omnibus political agreement defers "
                "this to 2 December 2026 (4-month grace). Both dates are "
                "operative for transitional questions."
            ),
        ),
    ),
    "Art. 53": _KBEntry(
        dimension="tech_docs",
        stubs=(
            (
                "Art. 53: GPAI provider obligations: maintain technical "
                "documentation per Annex XI, supply downstream-provider "
                "information per Annex XII, implement a copyright policy, "
                "and publish a sufficiently detailed training-data summary."
            ),
            (
                "Art. 53(1)(d): Training-data content summary — the "
                "Commission adopted the mandatory disclosure template on "
                "24 July 2025. GPAI providers must publish a publicly "
                "available summary covering: public datasets, scraped web "
                "content, user data, synthetic data and licensed content. "
                "GPAI models placed on the market before 2 August 2025 are "
                "grandfathered until 2 August 2027."
            ),
            (
                "Art. 53(2) free / open-source carve-out: the Annex XI "
                "technical-documentation obligation and the Annex XII "
                "downstream-provider information obligation under "
                "Art. 53(1)(a)-(b) do NOT apply to GPAI models released "
                "under a free and open-source licence permitting access, "
                "use, modification and distribution, with publicly "
                "available parameters (weights, architecture and usage "
                "information). The carve-out does NOT apply to GPAI models "
                "designated as systemic-risk under Art. 51 — once "
                "systemic-risk designation lands, the open-source carve-"
                "out is gone and the full Art. 53 obligations plus the "
                "Art. 55 systemic-risk obligations apply regardless of "
                "licence. The Art. 53(1)(c) copyright policy and the "
                "Art. 53(1)(d) public training-data summary apply to ALL "
                "GPAI providers including open-source releases."
            ),
        ),
    ),
    "Art. 55": {
        "dimension": "risk_mgmt",
        "summary": (
            "Art. 55 adds four obligations on top of Art. 53 for GPAI providers "
            "with systemic risk: (a) model evaluation in accordance with "
            "standardised protocols and tools reflecting the state of the art, "
            "including conducting and documenting adversarial testing to identify "
            "and mitigate systemic risks; (b) assess and mitigate possible "
            "systemic risks at Union level — including their sources — that may "
            "stem from development, market-placement, or use of the model; (c) "
            "keep track of, document, and report without undue delay to the AI "
            "Office (and national competent authorities where appropriate) "
            "information about serious incidents and possible corrective "
            "measures; (d) ensure an adequate level of cybersecurity protection "
            "for both the model AND its physical infrastructure. Providers may "
            "rely on Art. 56 codes of practice to demonstrate compliance until "
            "a harmonised standard is published."
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
            "Union before placing a high-risk AI system on the market. The "
            "Art. 22(3) mandate must empower the authorised representative to "
            "(a) verify that the provider's Art. 47 EU declaration of "
            "conformity and Art. 11 technical documentation were drawn up; "
            "(b) keep the declaration of conformity, technical documentation, "
            "certificates and contact details available for national competent "
            "authorities for 10 years after the system is placed on the market; "
            "(c) supply that documentation to national authorities on reasoned "
            "request and register on their behalf with national authorities; "
            "(d) cooperate with market-surveillance authorities. Under "
            "Art. 22(4), the authorised representative must terminate the "
            "mandate and inform the AI Office and the relevant market-"
            "surveillance authority where it has reason to believe the "
            "provider is acting contrary to its obligations."
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
            "purpose making it high-risk. Art. 25(4) requires the original "
            "provider and the new provider to cooperate along the value "
            "chain — original providers must supply information, technical "
            "access, and reasonable assistance so that downstream actors can "
            "meet their own obligations. For general-purpose AI models, the "
            "one-third fine-tune rule (per the Commission's 18 July 2025 GPAI "
            "Guidelines, anchored on Art. 51) makes the downstream modifier a "
            "new provider when additional training compute exceeds 1/3 of the "
            "base model's compute, or 1/3 of the 10^25 FLOPs systemic threshold "
            "(~3.3×10^24 FLOPs) when base compute is unknown. Below the "
            "one-third threshold the downstream modifier does NOT become a "
            "new provider; original-provider obligations remain with the "
            "upstream actor and the downstream actor stays in its prior role "
            "(deployer / integrator). Small mid-cap "
            "entities (per the Digital Omnibus 7 May 2026 political agreement) "
            "now qualify for the Art. 62/63 SME-tier compliance simplifications "
            "when they take on a new-provider role under this Article."
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
            "Commission based on Annex XIII criteria. Commission's 18 July 2025 "
            "GPAI Guidelines presume a model is general-purpose (Art. 3(63)) "
            "when training compute exceeds 10^23 FLOPs and the model can "
            "generate language, image, audio, or video output. Fine-tuned or "
            "modified models become new providers under Art. 25 when their "
            "additional training compute exceeds one-third of the base model's "
            "compute (or one-third of the 10^25 systemic threshold, ~3.3×10^24 "
            "FLOPs, when base compute is unknown)."
        ),
    },
    "Art. 52": {
        "dimension": "gpai_specific",
        "summary": (
            "Procedure for GPAI-with-systemic-risk classification: providers "
            "must notify the Commission within 2 weeks of meeting / expecting to "
            "meet the threshold; provider may submit arguments against "
            "designation; Commission lists designated models publicly. Under "
            "Art. 52(4), the Commission may designate a GPAI model as "
            "systemic-risk ex officio (or following an Art. 90 scientific-"
            "panel qualified alert) on the Annex XIII criteria, independent "
            "of the Art. 51(1)(a) compute threshold. Reassessment requests "
            "are permitted at the earliest 6 months after designation. The "
            "2-week pre-training notification obligation is especially "
            "important for open-source models per Recital 112 — once weights "
            "are released publicly, downstream compliance measures become "
            "harder to implement, so providers planning open-source releases "
            "must engage with the AI Office before training completes."
        ),
    },
    "Art. 54": {
        "dimension": "gpai_specific",
        "summary": (
            "Requires providers of GPAI models established outside the EU to "
            "appoint, by written mandate, an authorised representative "
            "established in the Union before placing the GPAI model on the "
            "market. Art. 54 is the GPAI-specific authorised-representative "
            "regime and is distinct from Art. 22 — Art. 22 applies to "
            "high-risk AI SYSTEMS, Art. 54 applies to GPAI MODELS. The "
            "Art. 54(3) mandate must empower the representative to (a) verify "
            "that the Art. 53(1)(a) technical documentation and Annex XI "
            "information are drawn up and that Art. 53 obligations have been "
            "complied with; (b) keep the documentation and contact details "
            "available for the AI Office and national competent authorities "
            "for 10 years; (c) provide the AI Office on reasoned request "
            "with all information and documentation necessary to demonstrate "
            "compliance with Chapter V; (d) cooperate with the AI Office and "
            "competent authorities. The representative must terminate the "
            "mandate and inform the AI Office where it has reason to believe "
            "the provider is acting contrary to its obligations. GPAI-with-"
            "systemic-risk providers face the same Art. 54 obligation plus "
            "Art. 55 systemic obligations regardless of where they are "
            "established."
        ),
    },
    "Art. 56": _KBEntry(
        dimension="gpai_specific",
        stubs=(
            (
                "Art. 56: AI Office encourages and facilitates voluntary "
                "codes of practice at Union level to contribute to proper "
                "application of the Regulation, particularly for GPAI "
                "obligations; codes may serve as a means to demonstrate "
                "compliance until harmonised standards are published."
            ),
            (
                "Art. 56: GPAI Code of Practice — published 10 July 2025 by "
                "the AI Office. Voluntary instrument for GPAI providers; "
                "adherence constitutes 'adequate compliance demonstration' "
                "under Art. 56. Signatories include Amazon, Anthropic, "
                "Google, Microsoft and OpenAI; Meta and several Chinese "
                "providers did not sign; xAI signed only the Safety & "
                "Security chapter. Final compliance framework references "
                "the 18 July 2025 Commission Guidelines on the 10^23 / "
                "10^25 FLOPs thresholds."
            ),
        ),
    ),
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
            "Art. 79 procedure for AI systems presenting a risk: market-"
            "surveillance authorities that have sufficient reasons to consider "
            "that an AI system presents a risk to health, safety or fundamental "
            "rights (per the Art. 3(19) definition as amended by Art. 79(1)) "
            "carry out an evaluation of the system. Where non-compliance is "
            "found, the authority requires the relevant operator to take "
            "corrective action — withdrawal of the system from the EU market, "
            "recall from the distribution chain, or restriction of its "
            "availability — within a set period proportionate to the risk, "
            "applying Article 18 of Reg. (EU) 2019/1020 mutatis mutandis. The "
            "authority informs the Commission and the other Member States of "
            "the measures taken; if no objection is raised within 3 months, "
            "the national measure is considered justified and applies Union-"
            "wide under Art. 81."
        ),
    },
    # ─── Title XII / final provisions (Art. 113 — applicability dates) ───────
    "Art. 113": {
        "dimension": "governance",
        "summary": (
            "Entry into force + application (Regulation 2024/1689): in force "
            "1 August 2024; prohibitions (Art. 5) + AI literacy (Art. 4) from "
            "2 February 2025; GPAI obligations (Chapter V) from 2 August 2025; "
            "general application from 2 August 2026; pre-existing high-risk "
            "for public-authority use from 2 August 2030. Digital Omnibus on "
            "AI (political agreement reached 7 May 2026 between Parliament + "
            "Council) defers Annex III high-risk obligations to 2 December "
            "2027 and Annex I embedded-product obligations to 2 August 2028 "
            "to allow harmonised standards + AI Office guidelines to land "
            "first; remaining provisions unchanged."
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
            "GPAI penalties: the Commission, acting through the AI Office "
            "(per Art. 64), may impose direct fines on GPAI model providers "
            "of up to EUR 15 000 000 or 3 % of worldwide annual turnover "
            "(whichever is higher) for breaches of Chapter V obligations, "
            "supplying incorrect / incomplete / misleading information, or "
            "failing to comply with a Commission request for measures. The "
            "AI Office is the sole EU-level enforcement body for GPAI "
            "providers — Member State market-surveillance authorities do "
            "NOT have direct fining power over GPAI model providers under "
            "this Article. Applies from 2 August 2026. Provider has right "
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
    # ─── Title III Ch. 4: Notified-body lifecycle gap-fill (Arts. 30, 32) ────
    "Art. 30": {
        "dimension": "conformity",
        "summary": (
            "Notification procedure: the notifying authority may notify only "
            "conformity-assessment bodies that satisfy the Art. 31 "
            "requirements (Art. 30(1)). Per Art. 30(2)-(3) the notifying "
            "authority must notify the Commission and the other Member "
            "States, using the electronic notification tool developed and "
            "managed by the Commission, of each conformity-assessment body "
            "it has assessed — including the assessment activities, "
            "conformity-assessment modules, AI technologies covered, and "
            "the relevant attestation of competence. A body may carry out "
            "the activities of a notified body only if no objection is "
            "raised by the Commission or other Member States within 2 weeks "
            "of validation (where the accreditation certificate is used) "
            "or within 2 months (where it is not)."
        ),
    },
    "Art. 32": {
        "dimension": "conformity",
        "summary": (
            "Presumption of conformity with requirements relating to "
            "notified bodies: where a conformity-assessment body "
            "demonstrates its conformity with the criteria laid down in "
            "the relevant harmonised standards (or parts thereof) the "
            "references of which have been published in the Official "
            "Journal of the European Union, it is presumed to comply with "
            "the Art. 31 requirements to the extent those harmonised "
            "standards cover those requirements (Art. 32)."
        ),
    },
    # ─── Title III Ch. 4: Notified-body coordination + lifecycle (Arts. 35-39) ─
    "Art. 35": {
        "dimension": "conformity",
        "summary": (
            "Identification numbers and lists of notified bodies "
            "designated under the Regulation: the Commission assigns a "
            "single identification number to each notified body, even "
            "where the body is notified under several Union acts (Art. "
            "35(1)). The Commission makes publicly available the list of "
            "the bodies notified under the Regulation, including their "
            "identification numbers and the activities for which they "
            "have been notified, and keeps that list up to date (Art. "
            "35(2))."
        ),
    },
    "Art. 36": {
        "dimension": "conformity",
        "summary": (
            "Changes to notifications: the notifying authority must use "
            "the electronic notification tool to notify the Commission "
            "and the other Member States of any relevant changes to the "
            "notification of a notified body (Art. 36(1)). Where a "
            "notifying authority has ascertained — or has been informed "
            "— that a notified body no longer meets the Art. 31 "
            "requirements or is failing to fulfil its obligations, it "
            "must restrict, suspend, or withdraw the notification as "
            "appropriate, depending on the seriousness of the failure, "
            "and inform the Commission and the other Member States "
            "(Art. 36(3)-(4)). Where notification is restricted, "
            "suspended, or withdrawn, or the notified body has ceased "
            "activity, the notifying authority must take appropriate "
            "steps to ensure the files of that body are either taken "
            "over by another notified body or kept available for the "
            "responsible notifying and market-surveillance authorities."
        ),
    },
    "Art. 37": {
        "dimension": "conformity",
        "summary": (
            "Challenge to the competence of notified bodies: the "
            "Commission must, where necessary, investigate all cases "
            "where there are reasons to doubt the competence of a "
            "notified body or whether a notified body continues to fulfil "
            "the Art. 31 requirements and its applicable responsibilities "
            "(Art. 37(1)). The notifying Member State must provide the "
            "Commission, on request, with all information relating to the "
            "notification or the maintenance of the competence of the "
            "body. Where the Commission ascertains that a notified body "
            "does not meet — or no longer meets — the notification "
            "requirements, it adopts an implementing act requesting the "
            "notifying Member State to take the necessary corrective "
            "measures, including, where necessary, the withdrawal of the "
            "notification (Art. 37(2)-(4))."
        ),
    },
    "Art. 38": {
        "dimension": "conformity",
        "summary": (
            "Coordination of notified bodies: the Commission ensures that "
            "appropriate coordination and cooperation between notified "
            "bodies active in the conformity-assessment procedures under "
            "the Regulation is put in place and properly operated in the "
            "form of a sectoral group of notified bodies (Art. 38(1)). "
            "Member States must ensure that the bodies they have notified "
            "participate in the work of that group, directly or through "
            "designated representatives (Art. 38(2))."
        ),
    },
    "Art. 39": {
        "dimension": "conformity",
        "summary": (
            "Conformity-assessment bodies established under the law of a "
            "third country may be authorised to carry out the activities "
            "of notified bodies under the Regulation only where the Union "
            "has concluded an agreement with the third country concerned "
            "and the third-country body satisfies the Art. 31 "
            "requirements or ensures an equivalent level of compliance "
            "(Art. 39)."
        ),
    },
    # ─── Title III Ch. 5: Certificates + information + derogation (Arts. 44-46) ─
    "Art. 44": {
        "dimension": "conformity",
        "summary": (
            "Certificates of conformity issued by notified bodies under "
            "Annex VII: certificates must be drawn up in a language "
            "easily understandable by the relevant authorities of the "
            "Member State in which the notified body is established (Art. "
            "44(1)). Certificates are valid for the period they indicate, "
            "not exceeding 5 years for Annex-I systems and 4 years for "
            "Annex-III systems, with possible extensions on the basis of "
            "re-assessment (Art. 44(2)). Where a notified body finds that "
            "a system no longer meets the Section-2 requirements, it must "
            "— taking account of the principle of proportionality — "
            "suspend or withdraw the certificate issued, or impose "
            "restrictions on it, unless compliance is ensured by "
            "appropriate corrective action by the provider within the "
            "deadline set by the notified body. The notified body must "
            "give reasons for its decision and provide a procedure for "
            "appeal (Art. 44(3))."
        ),
    },
    "Art. 45": {
        "dimension": "conformity",
        "summary": (
            "Information obligations of notified bodies: notified bodies "
            "must inform the notifying authority of (a) any Union "
            "technical-documentation assessment certificates, supplements "
            "to those certificates, and quality-management-system "
            "approvals issued under Annex VII, (b) any refusal, "
            "restriction, suspension, or withdrawal of such certificates "
            "or approvals, (c) any circumstances affecting the scope or "
            "conditions of notification, (d) any request for information "
            "on conformity-assessment activities they have received from "
            "market-surveillance authorities, and (e) on request, the "
            "conformity-assessment activities they have performed within "
            "the scope of their notification and any other activity "
            "performed, including cross-border activities and "
            "subcontracting (Art. 45(1)-(2)). Notified bodies must also "
            "provide the other bodies notified under the Regulation that "
            "carry out similar activities with relevant information on "
            "issues relating to negative — and, on request, positive — "
            "conformity-assessment results (Art. 45(3))."
        ),
    },
    "Art. 46": {
        "dimension": "conformity",
        "summary": (
            "Derogation from the conformity-assessment procedure: by way "
            "of derogation from Art. 43, a market-surveillance authority "
            "may authorise the placing on the market or putting into "
            "service of specific high-risk AI systems within the "
            "territory of the Member State concerned, for exceptional "
            "reasons of public security or the protection of life and "
            "health of persons, environmental protection, or the "
            "protection of key industrial and infrastructural assets "
            "(Art. 46(1)). The authorisation is granted for a limited "
            "period while the necessary conformity-assessment procedures "
            "are being carried out, taking into account the exceptional "
            "reasons that justify the derogation, and terminates as soon "
            "as those procedures have been completed (Art. 46(2)). The "
            "authorising Member State must immediately inform the "
            "Commission and the other Member States; the Commission may, "
            "where the authorisation is unjustified, raise objections and "
            "require the Member State to withdraw it (Art. 46(3)-(5)). "
            "Law-enforcement / civil-protection authorities may, in a "
            "duly justified situation of urgency, put a specific high-"
            "risk AI system into service without the authorisation "
            "provided that authorisation is requested without undue delay "
            "(Art. 46(4))."
        ),
    },
    # ─── Title IX: Market-surveillance + enforcement gap-fill (Arts. 75-84, 90-94) ──
    # Appended at end-of-dict so concurrent subagent merges stay
    # line-disjoint (CLAUDE.md hard rule #5 — every emitted citation
    # must resolve in ARTICLE_EXISTENCE; all 13 keys are catalog members).
    "Art. 75": {
        "dimension": "governance",
        "summary": (
            "Art. 75: mutual assistance + control of AI systems based "
            "on GPAI models. Where the model + system share a provider, "
            "the AI Office holds market-surveillance powers under Reg. "
            "(EU) 2019/1020; national authorities may request the AI "
            "Office to exercise its Art. 91-93 powers over a GPAI model "
            "they cannot otherwise investigate."
        ),
    },
    "Art. 76": {
        "dimension": "post_market",
        "summary": (
            "Art. 76: market-surveillance supervision of real-world "
            "testing under Art. 60. Authorities verify registration, "
            "informed consent + incident reporting; may require the "
            "provider or prospective-provider deployer to modify, "
            "suspend, or terminate the test, including by unannounced "
            "on-site inspection."
        ),
    },
    "Art. 77": {
        "dimension": "governance",
        "summary": (
            "Art. 77: powers of national authorities protecting "
            "fundamental rights. On reasoned request they may obtain "
            "any documentation drawn up under the AI Act for Annex-III "
            "high-risk systems and may ask the market-surveillance "
            "authority to organise technical testing where the "
            "documentation proves insufficient."
        ),
    },
    "Art. 80": {
        "dimension": "risk_mgmt",
        "summary": (
            "Art. 80: procedure for AI systems classified by the "
            "provider as non-high-risk under the Art. 6(3) carve-out. "
            "Where misclassification is suspected, the authority runs "
            "an Art. 79-style evaluation, may fine the provider, and "
            "may rely on the EU registration database."
        ),
    },
    "Art. 81": {
        "dimension": "governance",
        "summary": (
            "Art. 81: Union safeguard procedure. Where a Member State "
            "or the Commission objects to a national measure under "
            "Art. 79/80/82, the Commission decides within 6 months "
            "(60 days for Art. 5 prohibitions) whether the measure is "
            "justified; if so, it applies Union-wide."
        ),
    },
    "Art. 82": {
        "dimension": "post_market",
        "summary": (
            "Art. 82: compliant high-risk AI systems that nevertheless "
            "present a risk to safety, fundamental rights, or other "
            "public-interest protection. The market-surveillance "
            "authority requires the operator to take appropriate "
            "measures and may trigger the Art. 81 safeguard procedure."
        ),
    },
    "Art. 83": {
        "dimension": "conformity",
        "summary": (
            "Art. 83: formal non-compliance — missing or incorrect CE "
            "marking, EU declaration of conformity, authorised "
            "representative, technical documentation, EU-database "
            "registration, or instructions for use. The authority "
            "requires rectification within a set period, escalating to "
            "recall or withdrawal if non-compliance persists."
        ),
    },
    "Art. 84": {
        "dimension": "governance",
        "summary": (
            "Art. 84: Union AI testing support structures designated "
            "by the Commission to provide independent technical + "
            "scientific advice to national market-surveillance "
            "authorities — including for the technical evaluations "
            "underpinning Art. 79-83 enforcement."
        ),
    },
    "Art. 90": {
        "dimension": "gpai_systemic_risk",
        "summary": (
            "Art. 90: alerts of systemic risks by the scientific panel "
            "(Art. 68). The panel may issue a qualified alert to the "
            "AI Office where a general-purpose AI model poses a "
            "concrete Union-level risk or meets the Art. 51 systemic-"
            "risk thresholds, triggering Art. 91-93 powers."
        ),
    },
    "Art. 91": {
        "dimension": "gpai_specific",
        "summary": (
            "Art. 91: power to request documentation + information. "
            "The Commission, through the AI Office, may by reasoned "
            "decision require GPAI-model providers to supply the "
            "Annex XI / Annex XII / systemic-risk documentation drawn "
            "up under Arts. 53 + 55 and any further information "
            "needed to assess Chapter V compliance."
        ),
    },
    "Art. 92": {
        "dimension": "gpai_specific",
        "summary": (
            "Art. 92: power to conduct evaluations. The AI Office may "
            "evaluate a general-purpose AI model — directly or via "
            "independent experts — to assess Chapter V compliance "
            "where Art. 91 documentation is insufficient, or to "
            "investigate Art. 90 systemic-risk alerts. Art. 92(6) "
            "foresees an implementing act."
        ),
    },
    "Art. 93": {
        "dimension": "gpai_specific",
        "summary": (
            "Art. 93: power to request measures. The Commission, "
            "through the AI Office, may require a GPAI-model provider "
            "to comply with Chapter V, mitigate identified systemic "
            "risk at Union level, or restrict / withdraw / recall the "
            "model — subject to the Art. 94 procedural rights."
        ),
    },
    "Art. 94": {
        "dimension": "governance",
        "summary": (
            "Art. 94: procedural rights of economic operators. The "
            "Art. 18 rights of defence in Reg. (EU) 2019/1020 apply "
            "mutatis mutandis to GPAI-model providers facing Art. "
            "91-93 / 101 enforcement — right to be heard, file "
            "access, judicial review before the CJEU, and Art. 78 "
            "confidentiality."
        ),
    },
    # ─── Title XII: Final provisions — guidelines, delegation, comitology, ───
    # sectoral amendments (Arts. 96-98, 102-110) ────────────────────────────
    "Art. 96": {
        "dimension": "governance",
        "summary": (
            "Empowers the Commission to develop non-binding guidelines on "
            "the practical implementation of the Regulation, in particular "
            "on: the application of the requirements and obligations for "
            "high-risk AI systems (including responsibilities along the AI "
            "value chain, Arts. 8-15 and Art. 25); the application of the "
            "prohibited practices in Art. 5; the practical implementation "
            "of the provisions on substantial modification; the practical "
            "implementation of the transparency obligations laid down in "
            "Art. 50; detailed information on the relationship of the "
            "Regulation with the Union harmonisation legislation listed in "
            "Annex I and with other relevant Union law (including as "
            "regards consistency in their enforcement); and the "
            "application of the AI system definition in Art. 3(1) (Art. "
            "96(1)). The Commission pays particular attention to the needs "
            "of SMEs (including start-ups), local public authorities, and "
            "the sectors most likely to be affected, and updates the "
            "guidelines as necessary (Art. 96(2))."
        ),
    },
    "Art. 97": {
        "dimension": "governance",
        "summary": (
            "Exercise of the delegation: the power to adopt delegated "
            "acts is conferred on the Commission subject to the "
            "conditions set out in this Article. The delegations under "
            "Arts. 6(6)-(7), 7(1) and (3), 11(3), 43(5) and (6), 47(5), "
            "51(3), 52(4) and 53(5)-(6) are conferred for a period of "
            "five years from 1 August 2024 (Art. 97(2)). The Commission "
            "must draw up a report on the delegation not later than nine "
            "months before the end of the five-year period, and the "
            "delegation is tacitly extended for further five-year periods "
            "unless the European Parliament or the Council opposes the "
            "extension at least three months before the end of each "
            "period (Art. 97(2)). The delegation may be revoked at any "
            "time by the Parliament or the Council (Art. 97(3)). Before "
            "adopting a delegated act the Commission consults experts "
            "designated by each Member State in accordance with the "
            "Interinstitutional Agreement of 13 April 2016 on Better "
            "Law-Making (Art. 97(4)). A delegated act enters into force "
            "only if no objection is raised by the Parliament or the "
            "Council within three months of notification, extendable by "
            "a further three months (Art. 97(6))."
        ),
    },
    "Art. 98": {
        "dimension": "governance",
        "summary": (
            "Committee procedure: the Commission is assisted by a "
            "committee within the meaning of Regulation (EU) No 182/2011 "
            "(Art. 98(1)). Where reference is made to this Article, "
            "Art. 5 of Regulation (EU) No 182/2011 — the examination "
            "procedure — applies (Art. 98(2)). Implementing acts adopted "
            "under the AI Act follow this comitology track, under which "
            "the Commission is assisted by a committee of Member-State "
            "representatives that delivers an opinion on draft "
            "implementing acts before adoption."
        ),
    },
    "Art. 102": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Amends Regulation (EC) No 300/2008 on common rules in the "
            "field of civil aviation security. A new point is inserted "
            "into Art. 4(3) of Regulation (EC) No 300/2008 so that, when "
            "adopting detailed measures relating to technical "
            "specifications and procedures for the approval and use of "
            "security equipment concerning AI systems within the meaning "
            "of the AI Act, the requirements laid down in Chapter III, "
            "Section 2 of the AI Act (the essential requirements for "
            "high-risk AI systems) are taken into account. Civil-aviation "
            "security is one of the Section-B Annex I sectors where the "
            "AI Act applies through the existing sectoral safety regime "
            "rather than through a stand-alone AI conformity assessment."
        ),
    },
    "Art. 103": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Amends Regulation (EU) No 167/2013 on the approval and "
            "market surveillance of agricultural and forestry vehicles. "
            "An equivalent insertion is made so that, when adopting "
            "delegated or implementing acts under Regulation (EU) No "
            "167/2013 concerning AI systems that are safety components "
            "within the meaning of the AI Act, the essential requirements "
            "for high-risk AI systems set out in Chapter III, Section 2 "
            "of the AI Act are taken into account. Agricultural and "
            "forestry vehicles are an Annex I, Section B sector — AI "
            "safety components are high-risk but conformity is verified "
            "through the existing type-approval framework."
        ),
    },
    "Art. 104": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Amends Regulation (EU) No 168/2013 on the approval and "
            "market surveillance of two- or three-wheel vehicles and "
            "quadricycles. Mirrors Arts. 102-103: when the Commission "
            "adopts delegated or implementing acts under Regulation (EU) "
            "No 168/2013 concerning AI systems that are safety components "
            "within the meaning of the AI Act, it must take into account "
            "the essential requirements for high-risk AI systems set out "
            "in Chapter III, Section 2 of the AI Act. Two- or three-wheel "
            "vehicles and quadricycles are an Annex I, Section B sector."
        ),
    },
    "Art. 105": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Amends Directive 2014/90/EU on marine equipment. When the "
            "Commission adopts implementing acts under Directive 2014/90/"
            "EU concerning AI systems that are safety components within "
            "the meaning of the AI Act, the essential requirements for "
            "high-risk AI systems set out in Chapter III, Section 2 of "
            "the AI Act must be taken into account. Marine equipment is "
            "an Annex I, Section B sector: AI safety components are "
            "treated as high-risk but conformity is verified through the "
            "existing marine-equipment framework."
        ),
    },
    "Art. 106": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Amends Directive (EU) 2016/797 on the interoperability of "
            "the rail system within the European Union. When the "
            "Commission adopts delegated or implementing acts under "
            "Directive (EU) 2016/797 concerning AI systems that are "
            "safety components within the meaning of the AI Act, the "
            "essential requirements for high-risk AI systems set out in "
            "Chapter III, Section 2 of the AI Act must be taken into "
            "account. Rail systems are an Annex I, Section B sector."
        ),
    },
    "Art. 107": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Amends Regulation (EU) 2018/858 on the approval and market "
            "surveillance of motor vehicles and their trailers, and of "
            "systems, components and separate technical units intended "
            "for such vehicles. When the Commission adopts delegated or "
            "implementing acts under Regulation (EU) 2018/858 concerning "
            "AI systems that are safety components within the meaning of "
            "the AI Act, the essential requirements for high-risk AI "
            "systems set out in Chapter III, Section 2 of the AI Act "
            "must be taken into account. Motor vehicles are an Annex I, "
            "Section B sector — AI safety components are high-risk but "
            "conformity flows through the EU type-approval framework."
        ),
    },
    "Art. 108": {
        "dimension": "regulatory_perimeter",
        "summary": (
            "Makes parallel amendments to Regulation (EU) 2018/1139 on "
            "common rules in the field of civil aviation and Regulation "
            "(EU) 2019/2144 on type-approval requirements for motor "
            "vehicles and their trailers as regards general safety. In "
            "both cases, when the Commission adopts delegated or "
            "implementing acts concerning AI systems that are safety "
            "components within the meaning of the AI Act, the essential "
            "requirements for high-risk AI systems set out in Chapter "
            "III, Section 2 of the AI Act must be taken into account. "
            "Both sectors are listed in Annex I, Section B."
        ),
    },
    "Art. 109": {
        "dimension": "governance",
        "summary": (
            "Amends Regulation (EU) 2019/1020 on market surveillance and "
            "compliance of products to integrate the AI Act into the "
            "horizontal market-surveillance framework. The Annex to "
            "Regulation (EU) 2019/1020 is amended by adding the AI Act "
            "to the list of Union harmonisation legislation it covers, "
            "so that the powers, procedures and cooperation mechanisms "
            "of Regulation (EU) 2019/1020 — including the broad "
            "investigative and corrective powers of market-surveillance "
            "authorities and the procedural safeguards in Art. 18 of "
            "Regulation (EU) 2019/1020 — apply to AI systems governed by "
            "the AI Act, without prejudice to the AI-specific additions "
            "made by Chapter IX of the AI Act (e.g. fundamental-rights "
            "risks added to Art. 3(19) by Art. 79(1) of the AI Act)."
        ),
    },
    "Art. 110": {
        "dimension": "governance",
        "summary": (
            "Amends Directive (EU) 2020/1828 on representative actions "
            "for the protection of the collective interests of consumers. "
            "Annex I to Directive (EU) 2020/1828 is amended by adding a "
            "reference to the AI Act, so that qualified entities may "
            "bring representative actions on behalf of consumers against "
            "infringements of the AI Act. The amendment brings AI Act "
            "infringements within the scope of consumer collective "
            "redress under Union law."
        ),
    },
}
