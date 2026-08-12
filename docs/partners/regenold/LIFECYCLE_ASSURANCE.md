> **Superseded 2026-07-24.** This document was drafted against this extract and
> understates the platform. The current version lives in the legit-ai repository at
> `docs/partners/regenold/` and is grounded in legit-ai, which already ships much of
> what this draft proposed building. Do not circulate this copy.

<!-- Generated 2026-07-23. Backing document for the Regenold lifecycle-assurance proposal. -->

# Lifecycle Assurance for AI-Enabled Medical Products

> **Provenance.** Every EU AI Act citation in this document was verified against the
> repository's pinned official EUR-Lex snapshot via
> `app.data.provision_text.get_provision_text`. Claims about what the codebase can do
> were adversarially re-checked against the code. MDR, IVDR, DiGA and EMA points are
> marked EXTERNAL: they are real but not verifiable against our pinned corpus.
>
> **Reproduce the legal half in ten seconds, offline:**
> ```
> .venv/Scripts/python.exe scripts/lifecycle_demo/verify_demo.py
> ```
> Six checks: citation provenance, role routing, envelope evaluation, the Article 3(23)
> two-limb test, Regulation 1182/71 deadline arithmetic, and evidence-chain integrity.

---

# Continuous Lifecycle Assurance for AI-Enabled Medical Products

*A proposal and demonstration plan for Regenold*

---

## 1. What Regenold asked for, restated as a system

Regenold asked whether the platform could connect to medical devices with AI components and to hybrid therapies (drug plus software), so that it can keep track of whether they **keep working reliably**.

Restated as an engineering and regulatory problem, that is one question asked continuously:

> **Is this device still inside the envelope it was certified in, and if not, who owes what, by when, with what evidence?**

That question is not our framing. It is Article 43(4), verbatim from the pinned official text: a high-risk AI system already subject to conformity assessment "shall undergo a new conformity assessment procedure in the event of a substantial modification", except that for systems that continue to learn, changes "pre-determined by the provider at the moment of the initial conformity assessment and are part of the information contained in the technical documentation referred to in point 2(f) of Annex IV, shall not constitute a substantial modification."

Inside the envelope: nothing happens. Outside it: a new conformity assessment. The envelope is a named statutory artifact, not a product concept we invented.

The signal is already mandatory too. Article 12(2) requires logging capabilities that enable recording of events relevant for "(a) identifying situations that may result in the high-risk AI system presenting a risk within the meaning of Article 79(1) or in a substantial modification; (b) facilitating the post-market monitoring referred to in Article 72; and (c) monitoring the operation of high-risk AI systems referred to in Article 26(5)."

So the proposition is not "buy monitoring." It is: the law already requires the device to emit this signal, for exactly these three purposes; we are the system that reads it and converts it into a dated, cited, filed obligation.

---

## 2. Why this is the right pivot

- **The law, not the roadmap, is the retention mechanism.** Article 72(2) requires the provider to collect, document and analyse performance data "throughout their lifetime" to evaluate "continuous compliance" with Chapter III Section 2. Article 9(2) makes risk management "a continuous iterative process planned and run throughout the entire lifecycle, requiring regular systematic review and updating." A Q&A oracle is bought when someone feels uncertain; a lifecycle system of record is bought because Article 26(5) obliges a deployer to suspend use of a system it has reason to consider risky, and Article 73(3) allows two days to report certain serious incidents from the moment anyone became aware.

- **Article 43(4) converts monitoring into cost avoidance.** Notified-body review capacity is the sector's binding constraint. Every substantial modification consumes it; a properly specified Annex IV point 2(f) plan avoids consuming it. We sell the difference between a routine performance report and an unplanned notified-body re-engagement.

- **Article 72(4) removes the "second compliance stack" objection.** For Annex I Section A products (points 11 and 12 are the MDR and IVDR, verified), providers "shall have a choice of integrating, as appropriate, the necessary elements described in paragraphs 1, 2 and 3 using the template referred in paragraph 3 into systems and plans already existing under that legislation, provided that it achieves an equivalent level of protection." One integrated post-market surface, not two.

- **The obligation is two-sided, which makes the account expand by itself.** Article 26(5) puts a monitor, inform and suspend duty on the deployer; Articles 72 and 73 put post-market monitoring and reporting on the provider. Same telemetry event, two parties, one wire between them.

---

## 3. What we can stand on today

Only assets that survived adversarial verification appear here.

| Asset | Status | Evidence | What it does for this problem |
|---|---|---|---|
| Temporal compound-risk axis | [PARTIAL] written, zero importers | `app/data/agentic_taxonomy.py:250-303`. Grounded to Articles 3(23), 12, 14, 15, 43, 72, 73. Mitigation pattern already names "continuous behavioural-metric monitoring against the conformity-assessment baseline", "automated drift detection beyond defined thresholds", "Article 3(23) determination memo per detected drift" | This control loop is already specified, article by article, in the repository. Nothing consumes it. That is precisely what we propose to build, and `app/lifecycle/` becomes its first consumer |
| Verbatim provision engine | [EXISTS] wired | `app/data/provision_text.py`: `get_provision_text` :187, `provision_exists` :176, `select_relevant_paragraphs` :257. Resolves `Article 73(3)`, `Annex IV(2)`, `Article 3(49)`. Live at `verbatim_answer.py:30`, `routes/regenold.py:8139` | Every alert quotes the duty it asserts, at the paragraph the deadline actually lives at. The difference between a dashboard and a defensible record |
| Canonical article catalog | [EXISTS] wired | `app/data/article_existence.py`, 126 entries (113 articles, 13 annexes). Enforced as a repo-wide lint | Fail-closed hallucination floor: a citation that does not resolve cannot reach the wire |
| Hash-chained evidence store | [EXISTS] wired, with a stated limit | `app/evidence/store.py`: `_compute_data_hash` :115, Postgres :349 with advisory-lock serialisation, SQLite :672, `verify_chain` :295. Payload is unconstrained `dict[str, Any]` | Append-only, verifiable **payload** integrity. The digest covers `{payload, previous_hash}` only, so every legally significant timestamp is written **inside** the payload |
| Role and obligation matrix, 9 roles | [EXISTS] wired | `app/data/role_obligations.py`: `articles_for_role` :358, `applies_to_role` :372. Verified: provider returns 19 articles, deployer 7, product_manufacturer 13 | Routes one telemetry event to two different duty sets. Deployer duties include Articles 13 and 14, which strengthens the hospital-side story |
| Measured citation quality on medtech gold data | [EXISTS] | 24-question gold-labelled medtech set, run live: reference recall 0.896, reference F1 0.656, tone 1.0, zero refusals. Independent LLM judge: references-faithfulness 0.875, answer correctness 0.917, tone 1.0 | References-faithfulness is the axis that matters: an alert citing Article 73 while describing Article 72 is worse than no alert |
| Sub-point citation upgrader | [EXISTS] wired | `app/data/subpoint_emitter.py::upgrade_references` :237 | Lets an alert cite `Article 73.3` (the two-day clock) rather than a bare `Article 73`, which carries four different deadlines |
| Glass-box reasoning trace | [EXISTS] wired | `app/integrations/regenold/reasoning_trace.py`: `ReasoningTrace` :73, `record_note` :329, `record_sub_query` :398 | The "why did you raise this" layer, already serialised onto the wire |
| Persistent 3-backend entity registry | [EXISTS] wired | `app/integrations/regenold/user_store.py`: in-memory :131, SQLite with real DDL :180, Postgres :274, `_select_backend` :410. Live at `routes/auth.py:110` | The direct template to clone for a device, product-version and deployment registry. This is why the estimate is days, not weeks |
| MedTech standards bridge | [PARTIAL] wired, 4 entries | `app/data/medtech_standards.py`. Has Articles 9, 10, 15, 43. Missing 72, 73, 12, 26, 14 | The highest-value, lowest-effort content gap we hold: the two articles this ask turns on have no bridge |
| Severity ordering | [PARTIAL] dead port | `app/data/severity.py`: `rank` :59, `max_severity` :66, `score_to_severity` :77. Zero importers | Correct and copy-pasteable; nothing calls it today |

**Assets that do not exist and must be built:** device, product-version and deployment entities; telemetry ingest; the conformity envelope model; deadline arithmetic; outbound webhooks; per-manufacturer tenant isolation (`tenant_id` is presently a hardcoded literal at `routes/regenold.py:4523`); a scheduler (none is present in `app/` or `requirements.txt`).

---

## 4. The system

### 4.1 Object model in brief [BUILD]

| Object | Role |
|---|---|
| `RegulatedProduct` | Identity, UDI-DI, MDR or IVDR class, AI Act high-risk route, declared operator roles (multi-valued), placing-on-market date |
| `ConformityEnvelope` | Frozen, integer-versioned, content-hashed. Declared metrics with floors, ceilings and subgroup bands; approved input specification; oversight measures; the Annex IV point 2(f) pre-determined change plan. Never mutated; a change creates version *n+1* |
| `PerformanceSnapshot` | Aggregate metrics for a window: model version, volume, headline and subgroup metrics, input-drift profile, override rate. `data_class` is a required literal `aggregate_only` |
| `DriftFinding` | Typed breach with statistics, PCCP status, severity and the awareness timestamp |
| `ObligationTrigger` | Article reference, verbatim provision text, responsible role, computed deadline, required evidence artifact |
| `EvidenceRecord` | The above, written to the existing hash chain, with all timestamps inside the hashed payload |

The single highest-value field is `in_pccp` on each declared metric. It is the machine encoding of the Article 43(4) safe harbour: a movement inside the registered plan is documented and closed; a movement outside it is an Article 3(23) candidate. One boolean decides whether the customer's week involves a notified body.

### 4.2 The pipeline, six steps

1. **Ingest and validate** [BUILD]. Schema-enforced aggregate snapshot; tenant derived from the authenticated key; idempotency key; payload hash. Writes `performance_snapshot` to the chain.
2. **Envelope evaluation** [BUILD], deterministic. Metric floor and ceiling comparison with a Wilson lower bound against the floor; subgroup disparity; input-specification violation; distribution shift; undeclared version change; PCCP membership test. Severity via `app/data/severity.py`, its first consumer.
3. **Obligation mapping** [BUILD], deterministic. A versioned rule pack keyed on finding type, role, PCCP status and sectoral regime, executed against `provision_text`, `role_obligations`, `article_existence`, `subpoint_emitter` and `refs`.
4. **Deadline clock** [BUILD], deterministic. See the determinism boundary below.
5. **Evidence write** [EXISTS, extended]. Appends to the existing chain; a durable DSN is a precondition.
6. **Alert, task, filing pack** [PARTIAL to BUILD]. Email exists as one production template plus a diagnostic sender; the alert template, webhook, task queue and filing pack are new.

A seventh, optional step calls the existing grounded Q&A engine to explain a finding in prose. Its output never becomes a legal field.

### 4.3 The determinism boundary

> **No model output occupies a field a regulator reads, or a field that starts a clock.**

| Concern | Mechanism |
|---|---|
| Is the metric outside the envelope | Deterministic comparison plus Wilson interval |
| Is the change inside the PCCP | Set and interval membership. Article 43(4) is binary; a probabilistic answer is worthless |
| Which article applies | Versioned rule pack, fail-closed against the 126-entry catalog |
| What the article says | `get_provision_text()`, a pure lookup over pinned text |
| Who owes it | `applies_to_role()` |
| When it is due | Deterministic date arithmetic (below) |
| Explain it in English | Language model, advisory, human-facing |
| Draft the filing narrative | Language model, flagged machine-generated, excluded from the legal record until a named human attests |
| Novel or ambiguous pattern | Model triages to a human queue; never auto-fires a duty |

**Two honest engineering qualifications, stated before a notified body finds them.** First, the chain digest covers `{payload, previous_hash}` and not the row metadata; a forged `timestamp` still verifies. We therefore say "hash-chained payload integrity", never "we can prove the timestamp", and every awareness, report and suspension timestamp goes inside the payload. Second, deadlines are not naive day addition. EU time limits run under Regulation (EEC, Euratom) No 1182/71: day zero is excluded, the period ends at 23:59:59 on the final day, weekends and public holidays roll the deadline forward, and a period of two days or more must contain at least two working days. A two-day Article 73(3) clock computed naively across a weekend reports a deadline that has not expired. That regulation is external to our pinned corpus, so every computed deadline carries `confidence: "computed"` and its external basis, and both the nominal and adjusted dates are shown.

Note also that Article 79(2) is the one place the Regulation itself says working days: corrective action "within the shorter of 15 working days, or as provided for in the relevant Union harmonisation legislation."

### 4.4 One artifact, two regulators

| Artifact | EU AI Act obligation | MDR or IVDR obligation served | Confidence |
|---|---|---|---|
| Integrated post-market monitoring plan | Art 72(1) to (3); Annex IV point 9 | MDR Art 83, Art 84 | Direct; Art 72(4) expressly authorises the merge |
| Performance-versus-envelope report | Art 72(2); Art 15(1) | MDR Art 85 and Art 86 input; PMCF under Annex XIV Part B feeding the Art 61(11) clinical-evaluation update | Direct |
| Envelope-breach determination memo | Art 3(23); Art 43(4) | Notified-body change control | Direct on the AI Act; advisory on the notification threshold |
| Subgroup performance ledger | Annex IV(2)(g) metrics "as well as potentially discriminatory impacts" | MDR Annex XIV Part B; Art 88 trend reporting input | Direct |
| Serious-incident report and routing decision | Art 73(1) to (6), routed per **Art 73(10)** | MDR Art 87 vigilance, the other track | Direct; the two-track split is the differentiator |
| Log-retention attestation | Art 12(1); Art 19(1) and Art 26(6), each at least six months | MDR Art 10(8); ISO 13485 record control | Direct |
| Change-freeze record during an open incident | Art 73(6) | MDR Art 89 | Direct |
| Deployer monitoring and suspension record | Art 26(5), Art 26(6) | MDR Art 88 trend reporting input | Direct |
| Risk-management file update from post-market data | Art 9(2)(c) | ISO 14971 production and post-production information | Direct; `medtech_standards.py` already maps Art 9 to ISO 14971 |
| Version and change ledger | Annex IV 1(a), 1(c), point 6; Art 11(1) | IEC 62304 maintenance and configuration management | Direct |
| Ten-year retention manifest | Art 18(1), including 18(1)(c); Art 47(1) | MDR Art 10(8) | Direct |

**Article 73(10) is the credibility moment.** For a device covered by the MDR or IVDR, AI Act serious-incident notification is "limited to those referred to in Article 3, point (49)(c)" and goes to "the national competent authority chosen for that purpose by the Member States where the incident occurred." Death and health harm route through MDR vigilance instead. A generic AI Act tool that says "notify the market surveillance authority within 15 days" is wrong for exactly Regenold's customer base.

---

## 5. How a device or hybrid therapy connects

Design constraint: a hospital IT integration project kills the first sale. Tier 0 requires zero engineering from the customer.

**Tier 0, no integration.** A CSV or spreadsheet upload, one row per product, deployment, window and subgroup, with a downloadable header template. The uploader returns the full assessment synchronously: findings, triggers, verbatim citations and computed deadlines. A twenty-line SDK and a raw JSON POST are the same path with a different front door.

**Tier 1, MLOps adapters** [BUILD]. Map an existing Evidently, MLflow or Arize drift report into a snapshot through a customer-editable, versioned field map stored on the deployment, so the mapping is itself auditable.

**Tier 2, outbound.** Email alert extending the existing Resend integration [PARTIAL]; HMAC-signed webhook with retry [BUILD]; filing pack as PDF plus a JSON evidence manifest and chain excerpt [BUILD]; eQMS ticket adapters later.

**What we do not connect to in version 1:** no EHR, no PACS, no direct device integration, no personal data. The deployer's quality team already computes these aggregates for its own clinical governance. We ask for the aggregate they already have. Schema-level enforcement makes patient data structurally impossible to submit: `data_class` is a required literal, metric fields accept numbers only, there is no free-text field anywhere in the ingest schema, subgroup keys are drawn from a closed envelope-declared vocabulary, and any reported cell requires n of at least 20. We never receive the logs; those stay with the provider and deployer where Articles 19(1) and 26(6) put the retention duty, and we record a signed retention attestation instead.

---

## 6. What is genuinely new build, sized

| Work | Size | Notes |
|---|---|---|
| Prerequisites: add lifecycle members to `EvidenceEntryType`; require a durable DSN; derive `tenant_id` from the authenticated key | Half a day | Non-optional. Unknown entry types coerce silently at five sites in `store.py` (lines 214, 483, 580, 789, 881), so a snapshot written before the enum member is added lands mislabelled with no exception and no warning |
| Object model and product registry | 1 to 2 days | Clones the live `user_store.py` three-backend pattern |
| Envelope model, freeze, version, content hash | 1 day | |
| Deterministic evaluator, six finding types plus PCCP membership | 1 day | Wires `severity.py` as its first consumer |
| Rule pack and obligation mapper | 1 to 2 days | Seeded from the temporal compound-risk entry |
| Deadline clock under Reg 1182/71 with per-Member-State calendars | 1 day, plus counsel sign-off | |
| Route surface and evidence writers | 1 day | |
| `medtech_standards.py` extension: Articles 72, 73, 12, 26, 14 | Half a day | Highest visible value per hour in the repository |
| Filing pack, alert template, signed webhook | 3 to 5 days | Month one |
| Envelope import wizard, model-assisted with mandatory field-by-field human confirmation | 3 to 5 days | Month one; the hardest interaction problem |
| Chain digest hardening to cover metadata; trusted timestamping | Quarter one | A versioned digest format plus a re-hash migration |
| Scheduler and eQMS adapters | Quarter one | Only after durable persistence and idempotency |

The one-week target is a legal engine plus a synchronous assessment path. We do not promise a scheduler; evaluation fires on ingest, which is also the better product behaviour because the verdict is instant.

---

## 7. Risks and honest limits

1. **Telemetry access is the hard part, not the reasoning.** Mitigation: never make a live integration a precondition. Support the offline aggregate path permanently.
2. **Role determination is declared, not inferred.** Article 25(3) makes the product manufacturer the provider for a safety component sold under its name; Article 25(1) transfers the role to whoever rebrands, substantially modifies, or turns a non-high-risk system into a high-risk one. Roles are a versioned, human-attested field with the citation attached. Inconsistent declarations fail closed rather than guessing.
3. **Is the tool itself regulated?** It has no medical purpose, takes no patient data, produces no diagnosis or treatment recommendation, and never enters the clinical pathway; its user is a quality or regulatory professional. It is not high-risk under the AI Act because the load-bearing function is deterministic rule execution and the advisory layer sits in no Annex III category. We do carry Article 4 AI-literacy duties for staff operating the advisory layer. The boundary that preserves this posture is the same one in section 4.3: every outbound regulatory act requires a named human attestation.
4. **Not every device has an envelope.** Annex IV point 2(f) opens "where applicable" and Article 13(3)(c) says "if any." For many devices the first engagement is constructing the envelope, which is the stronger wedge: without one, Article 43(4) means every performance change is potentially a substantial modification.
5. **Article 111(2) grandfathering.** Systems placed before 2 August 2026 are covered "only if, as from that date, those systems are subject to significant changes in their designs", with a hard 2 August 2030 backstop for systems intended for use by public authorities. We compute this and never assert it. Note that "significant changes in their designs" (Art 111(2)) is a different term from "substantial modification" (Art 3(23)); we model them as distinct triggers and surface both verbatim. Crucially, MDR post-market obligations never grandfathered, so most rows in the section 4.4 table deliver value to a fully grandfathered device with zero AI Act exposure.
6. **Notified-body disagreement.** The system never presents a determination as authoritative. It presents evidence, verbatim provision text, a reasoning trace and a recommended determination that a named human accepts, amends or rejects; the human decision is the operative one.
7. **Timeline uncertainty.** Our knowledge base carries only dates in the adopted Regulation and this document cites only those. Applicability dates are configuration, versioned alongside the knowledge base, so a legislative change is a data update and every historical assessment remains replayable against the law version in force when it was made.
8. **Liability posture.** We are decision-support and record-keeping. Every output is traceable to a verifiable source. Clock outputs are labelled computed with an external legal basis. Failure modes are conservative: missing envelope means refusal to evaluate; ambiguous classification goes to a human queue; below the minimum cell count produces an explicit insufficient-data record so the absence is itself evidenced.

---

## 8. The ask

We are not asking for a procurement decision, only for enough reality to build against.

1. **One named design partner contact.** A Regulatory Affairs or Quality lead, or a PRRC, for sixty minutes.
2. **One real device profile, redacted as needed.** Intended purpose, MDR or IVDR class, whether the AI is a safety component or the device itself, the accuracy levels declared in the instructions for use under Article 15(3), and critically whether an Annex IV point 2(f) pre-determined change plan exists. Both answers are commercially useful.
3. **One sample telemetry extract.** Ten rows, synthetic is fine, aggregate only, no identifiers. We want to shape the snapshot schema against real data shape.
4. **A decision on a paid pilot.** Fixed fee, eight to twelve weeks, one device family, with exit criteria agreed in advance: a registered device with a frozen envelope derived from its declared metrics; ingested history evaluated against that envelope; at least one demonstrated breach producing a cited finding, a correctly computed statutory deadline and a human-owned determination record; and the whole sequence retrievable from the evidence chain as an audit-ready artefact.

We are not asking for access to any production system, any patient data, or any integration work. If the pilot does not produce an artefact your regulatory affairs function would put in front of a notified body, it has failed, and both sides should prefer to learn that in eight weeks for a fixed fee.

---
---

# Demo Preparation Plan

**The demo thesis:** we do not simulate the law, we simulate the device. Every citation and every deadline rule is computed live by real repository modules against the pinned official text. Only the telemetry is synthetic. That split must be visible on screen.

A persistent provenance chip appears on every card:

| Chip | Meaning |
|---|---|
| **VERIFIED** | Verbatim from the pinned EUR-Lex snapshot via `get_provision_text()`, resolving in the 126-entry catalog |
| **EXTERNAL** | Real citation not verifiable against our corpus: MDR articles, Reg (EEC, Euratom) 1182/71, ISO and IEC standards |
| **SIMULATED** | Synthetic demo data: telemetry, device identity, envelope values, notified-body name |

A reviewer who sees EXTERNAL on the MDR claims will trust the VERIFIED ones considerably more than if everything were painted the same colour.

All three scenarios render in one artifact, three tabs, one five-zone layout: identity strip, the frozen envelope, the timeline scrubber, the duty stack, and a **considered-and-not-fired panel**. That last panel is the single most differentiating element: every compliance tool shows what fired; almost none shows what it considered and rejected, with the citation and the reason. That is exactly the artefact needed to defend a decision to a notified body eighteen months later.

---

## D1. Three scenarios

### Scenario A: an AI diagnostic drifts out of its envelope

**Product** (SIMULATED): PulmoTriage CXR v2.3, chest-radiograph triage flagging suspected pneumothorax. MDR class IIb (EXTERNAL, manufacturer's own determination, displayed as an input not a claim). High-risk via **Article 6(1)** with Annex I Section A point 11; conformity assessment via **Article 43(3)**; the manufacturer is the provider under **Article 25(3)**. Four sites, two Member States.

**Envelope** (SIMULATED values, VERIFIED legal basis): overall sensitivity floor 0.920 and per-subgroup floor 0.880 (Art 15(3), Art 13(3)(b)(ii)); specificity floor 0.850; input-shift ceiling 0.150 and calibration ceiling 0.050 (Annex IV(2)(g)). **No pre-determined change plan filed** (Annex IV(2)(f) opens "where applicable"), so the Article 43(4) safe harbour is unavailable, and the platform states that with the citation as a standing posture.

**Timeline:** six monthly snapshots. A fourth site goes live in month three with a different scanner vendor and a heavy portable-AP case mix. Drift climbs. Nothing alerts, because nothing is outside the envelope, and the panel shows that deliberately.

**Month five is the trap.** Overall sensitivity reads **0.921** against a 0.920 floor: green on every headline dashboard. Portable-AP subgroup sensitivity reads **0.861** against the declared 0.880 floor.

**Obligations that fire:**

| Duty | Who | Citation | Deadline |
|---|---|---|---|
| System no longer performs at the declared level; Art 15(1) requires consistent performance "throughout their lifecycle" | Provider | Art 15(1), Art 15(3), Art 13(3)(b)(ii) | Trigger, not a duty |
| "immediately take the necessary corrective actions to bring that system into conformity, to withdraw it, to disable it, or to recall it" and inform distributors and deployers | Provider | Art 20(1) | Immediately; elapsed-time counter opens |
| Feed the finding into risk management: "evaluation of other risks possibly arising, based on the analysis of data gathered from the post-market monitoring system referred to in Article 72" | Provider | Art 9(2)(c) | Continuous |
| Monitor operation and, where relevant, inform the provider | Deployer, site 4 | Art 26(5) first subparagraph | Where relevant |
| Input data must be "relevant and sufficiently representative in view of the intended purpose" | Deployer, site 4 | Art 26(4) | Continuous; the scanner change is deployer-side |
| Keep documentation current and log the lifecycle change | Provider | Art 11(1), Annex IV point 6 | Continuous |

**The human-decision gate.** Article 26(5) second subparagraph is a mandatory stop: on reason to consider an Article 79(1) risk the deployer "shall, without undue delay, inform the provider or distributor and the relevant market surveillance authority, and shall suspend the use of that system." The platform does **not** assert that the risk exists. It presents the trigger, quotes the duty verbatim, and records the named decider, the rationale and the timestamp.

**Considered and not fired:** Article 43(4) substantial modification does not fire, because Article 3(23) requires "a change to the AI system" and the model version is unchanged across all six months; this is a population shift, so it is a performance non-conformity under Article 20(1). Article 73 does not fire, because Article 3(49) requires an incident or malfunctioning leading to harm, and no harm event is linked. Article 73(10) is pre-computed and standing by, showing that if harm does occur, AI Act notification narrows to Article 3(49)(c) fundamental-rights infringements and goes to a national competent authority, not the market surveillance authority.

**Aha line:** *"Your headline sensitivity never breached. The number declared in the instructions for use did, on one subgroup, at one new site. Article 15(3) makes that declaration the floor. It was caught in month five. Without this, it surfaces at the next periodic report, or not at all."*

### Scenario B: a hybrid therapy, one change, three regulators

**Product** (SIMULATED): an oral kinase inhibitor with a narrow therapeutic index, plus DoseCompanion v4, a separately CE-marked companion app whose AI component recommends dose reduction from patient-reported toxicity and lab values, and which is named in the summary of product characteristics as the titration method. Standalone MDSW, class IIb (EXTERNAL). High-risk via **Article 6(1)** with Annex I Section A point 11; conformity via **Article 43(3)**.

The Article 117 integral-medicinal-product branch is shown greyed with its trigger condition stated, marked EXTERNAL, and explicitly not asserted. Showing the branch and its gate rather than claiming a notified-body opinion is what earns trust from someone who does this for a living.

**This device did file** an Annex IV point 2(f) plan: quarterly retraining permitted, architecture unchanged, the grade-2 hepatotoxicity decision boundary held within plus or minus 5 percent of the validated 3.0 times upper limit of normal, grade-3 sensitivity at or above 0.90, no change to intended purpose or population.

**The change event** (SIMULATED): a scheduled quarterly retrain, ticketed as routine. Three of four conditions pass. The boundary moved from 3.00 to **2.46** times upper limit of normal, an **18.0 percent** shift against a 5 percent envelope. Clinically that may be an improvement; legally, better is not the test.

**The fan-out, three gates:**

- **AI Act, VERIFIED.** Article 3(23) two-limb test, both limbs displayed and both true: not foreseen or planned in the initial conformity assessment, and Chapter III Section 2 compliance affected. Therefore a substantial modification, and **Article 43(4)** requires a new conformity assessment, routed via Article 43(3) to the notified body. Also firing: Art 11(1) with Annex IV 1(a) and point 6; Art 47(4); Art 17(1)(a) modification-management procedures. **Hard block**, no numeric clock.
- **MDR, EXTERNAL.** The notified body that approved the technical documentation requires **prior approval before implementation** for changes affecting safety, performance or prescribed conditions of use. Route-dependent; regulatory affairs must confirm which conformity route applies.
- **Medicinal product, EXTERNAL.** The app is named in the summary of product characteristics as the titration method, so this may be a variation to the marketing authorisation. The platform does **not** classify the variation type; the three classes have materially different clocks, which is precisely why we will not guess. It renders a decision card and routes it.

**Aha line:** *"One retrain. Three regulators. Three different gates: one hard block, one prior approval, one judgement call with its own clock. Today that ships on a Tuesday and someone finds out at the next audit. This caught it at the pull request."*

### Scenario C: the fleet, and the role flip nobody noticed

**Forty assets** (SIMULATED), one tenant, one screen: thirty-one green, six amber, three red.

The **six amber** rows are the unglamorous work that proves this is a product rather than two case studies: log retention configured at 90 days against **Art 19(1)** "at least six months"; deployer-side retention at 120 days against **Art 26(6)**; input shift trending toward its ceiling; instructions for use predating the deployed model version against **Art 11(1)** and **Art 13(3)(b)(ii)**; no Annex IV point 9 post-market monitoring plan on file against **Art 72(3)**; and a workplace deployment with no worker-information record predating go-live against **Art 26(7)** ("Before putting into service or using"). Six articles, all machine-checkable from metadata alone, no telemetry required.

**Red 1 and red 2** are scenarios A and B. **Red 3** is the one nobody expected: a vendor's CE-marked general-purpose clinical documentation assistant, procured as a deployer for discharge summaries, seven obligations. Four months ago an internal team fine-tuned it on local emergency-department records and repointed it at triage, via an internal change ticket.

- **Annex III point 5(d)** covers "emergency healthcare patient triage systems", so under **Article 6(2)** the system is high-risk.
- **Article 25(1)(c)**: any deployer or third party who "modifies the intended purpose of an AI system, including a general-purpose AI system, which has not been classified as high-risk … in such a manner that the AI system concerned becomes a high-risk AI system in accordance with Article 6" is considered a provider, subject to the Article 16 obligations.
- The role badge flips from deployer to provider, and the article count computed by `articles_for_role()` goes from **7 to 19**.
- **Article 25(2)**: the initial provider "shall no longer be considered to be a provider of that specific AI system." The vendor is off the hook.
- **Article 26(8)**: where the system is not registered in the Article 71 EU database, deployers "shall not use that system and shall inform the provider or the distributor."

Fourteen provider obligations have been running unmet for four months, each with verbatim text and an evidence-none-on-file stamp.

Above the grid, one persistent panel carries **Article 72(4)** verbatim, with the count of Annex I Section A assets in the fleet that already run an MDR post-market surveillance system: the law permits one integrated plan, and this view is that single plane.

**Aha line:** *"Nobody bought a high-risk AI system. One was built, the moment a documentation assistant was pointed at emergency triage. Article 25(1)(c) made the hospital the provider, Article 25(2) took the vendor off the hook, and fourteen provider obligations started running. That happened four months ago on an internal change ticket, and nothing in the estate was watching for it."*

---

## D2. What is real versus simulated

| Real | Simulated | External |
|---|---|---|
| Every AI Act quotation, pulled live from `get_provision_text()` at build time | All telemetry: six monthly snapshots, the change event, fleet metadata | MDR classification rules and article numbers |
| Every reference validated against the 126-entry `ARTICLE_EXISTENCE` catalog | Device identities, sites, notified-body names | MDR vigilance routing and prior-approval thresholds |
| Role-to-duty routing via `articles_for_role()`, including the 7-to-19 expansion | Envelope numeric values and the plus-or-minus 5 percent bound | Medicinal-product variation regime |
| Envelope evaluation and the Article 3(23) two-limb test, executed in code | | Regulation (EEC, Euratom) 1182/71 deadline arithmetic |
| Deadline arithmetic implementation and its shown working | | Public-holiday calendars, a customer-supplied input |
| Evidence-chain writes and `verify_chain()` on a durable SQLite backend | | |

There is no scheduler, no live device integration, no persistent multi-tenant registry and no notified-body export in the demo. The demo does not need the device registry to exist: the fixtures are the registry. We build the legal engine, which is the differentiated and credible part, and feed it fixtures.

---

## D3. Build plan

**Files to create**

```
app/lifecycle/models.py                      entities
app/lifecycle/citations.py                   ref -> {wire_ref, verbatim, provenance}
app/lifecycle/envelope.py                    evaluate_snapshot -> breaches
app/lifecycle/substantial_modification.py    Art 3(23) two-limb test
app/lifecycle/duties.py                      duties_for(...) including NOT-FIRED
app/lifecycle/clocks.py                      Reg 1182/71 arithmetic
app/lifecycle/role_flip.py                   Art 25(1)(a)-(c), Art 6(2), Annex III matching
app/lifecycle/evidence_bridge.py             chain writes, timestamps inside payload
app/lifecycle/pack.py                        filing-pack renderer

app/evidence/models.py            EDIT  +5 EvidenceEntryType members (hard prerequisite)
app/data/medtech_standards.py     EDIT  +Art 72, 73, 12, 26, 14 bridges

scripts/lifecycle_demo/fixtures/*.json       three scenarios + EU holiday calendars
scripts/lifecycle_demo/build_demo_data.py    real modules -> demo_data.json
scripts/lifecycle_demo/verify_demo.py        the anti-smoke-and-mirrors CLI
demo/lifecycle_control_plane.html            one self-contained file, JSON inlined

tests/test_lifecycle_envelope.py
tests/test_lifecycle_clocks.py
tests/test_lifecycle_substantial_modification.py
tests/test_lifecycle_role_flip.py
tests/test_lifecycle_citations_resolve.py    every fixture ref resolves
tests/test_lifecycle_evidence_roundtrip.py   entry_type survives the write
```

**Repository modules called:** `provision_text.get_provision_text` and `provision_exists`; `article_existence.ARTICLE_EXISTENCE`; `refs.to_user_facing`; `role_obligations.articles_for_role` and `applies_to_role`; `kb.EC_CHECKER_OBLIGATION_MAP` and `KB_VERSION`; `medtech_standards.MEDTECH_STANDARD_MAP`; `agentic_taxonomy.compound_risks_for_article`; `severity.score_to_severity`; `evidence.store.get_evidence_store().record` and `verify_chain`; and the existing `/ask` route once per scenario, at build time only.

**Day by day**

- **Day 1.** Enum members plus the round-trip test first, because this failure is silent. Then models, citations, envelope evaluation, the clock, and scenario A fixtures. By end of day, scenario A runs in a terminal with verbatim citations and a computed deadline. That is the insurance policy.
- **Day 2.** Duties including the not-fired reasoner as a first-class output, the substantial-modification test, the evidence bridge with a SQLite DSN, scenario B fixtures.
- **Day 3.** `verify_demo.py`, `build_demo_data.py`, first pass of the artifact with all five zones. Tabs A and B live.
- **Day 4.** Role flip, Annex III point 5(d) matcher, the forty-asset fleet fixture and the six amber checks.
- **Day 5.** Fleet tab, the fan-out and role-badge animations, filing-pack export.
- **Day 6.** Extend `medtech_standards.py`. Pre-compute the narrative blocks. Publish.
- **Day 7.** Rehearsal, failure drills, provenance legend, final citation audit.

**`verify_demo.py`** is the single most persuasive artefact we can hand a partner engineer: ten seconds, no network, no language model. Six checks, printed with evidence: citation provenance (every reference resolved live out of the Act text, with the quotation shown); role routing (provider 19, deployer 7, and the 7-to-19 flip); envelope evaluation including the month-five trap; the two-limb substantial-modification test returning not-substantial for A and substantial for B; deadline arithmetic showing its working across a weekend roll-forward; and the evidence chain reporting its backend class, the entry-type round-trip count, and `verify_chain()`.

---

## D4. The three-minute script

**Frame, before anything is on screen (0:00 to 0:20).** "Two things first. Everything legal here is pulled live from the official EU AI Act text, and every article reference is checked against the canonical 113-article, 13-annex catalogue before it renders. Nothing is paraphrased. All the device data is synthetic, because I do not have your telemetry. The law is real; the devices are invented. Green chips are law, blue chips are fiction. Watch which is which."

**Scenario A (0:20 to 1:15).** Identity strip: class IIb, high-risk via Article 6(1), CE marked through the notified body under Article 43(3), manufacturer is the provider under Article 25(3), nineteen obligations, computed not typed. Envelope: the performance declared in the instructions for use, made binding by Article 15(3). Scrub months one to four: a new site, drift climbing, and no alert, because it is inside the envelope, and a tool that alerts here is a tool that gets turned off. Land on month five: overall 0.921 against a 0.920 floor, green everywhere. Click the subgroup row: 0.861 against 0.880. Below the number given to the notified body, on one subgroup, at one site, hidden by the headline metric. Then Article 20(1) immediate corrective action, Article 9(2)(c) into the risk file, and Article 26(4) routing the input-data duty to the hospital rather than the manufacturer. Then the decision card: we do not decide whether this is an Article 79(1) risk; if it is, Article 26(5) obliges suspension, that is a clinical judgement, and anyone selling an automatic answer to it is selling a liability. Then the considered-and-not-fired panel, slowly: Article 43(4) not fired because the model version never changed; Article 73 not fired because no harm event is linked; this is what one shows a notified body when asked why nothing was filed. Then Article 73(10): for this device, notification narrows to fundamental-rights infringements and goes to a different authority; a generic tool would have said market surveillance authority within fifteen days, and for these customers that is wrong.

**Scenario B (1:15 to 2:15).** Two regimes in parallel. This device did file an Annex IV point 2(f) plan, which is the Article 43(4) safe harbour: quarterly retraining pre-approved within plus or minus 5 percent on the dose-reduction threshold. Tuesday morning, scheduled retrain, ticket says routine, three of four conditions pass. The threshold moved 18.0 percent. Clinically that might be an improvement; legally, better is not the test. Fan-out: Article 3(23), both limbs true, substantial modification, Article 43(4) new conformity assessment back through the notified body under Article 43(3), hard block. Second branch: notified-body approval before implementation, different clock. Third branch: the app is named in the summary of product characteristics as the titration method, so this may be a marketing-authorisation variation with its own three clock regimes, and we do not classify that; we flag it and route it to whoever owns it.

**Scenario C (2:15 to 2:50).** Forty assets, thirty-one green, six amber, three red. The ambers are the unglamorous items that actually attract fines: retention under six months against Article 19(1), instructions for use out of date against the deployed model version, a workplace deployment with no worker-information record under Article 26(7). Then red three: a general-purpose documentation assistant, bought as a deployer, seven obligations. Four months ago it was fine-tuned on local records and pointed at emergency triage. Badge flips, seven to nineteen. Emergency healthcare patient triage is Annex III point 5(d); Article 6(2) makes it high-risk; Article 25(1)(c) makes whoever modified the intended purpose the provider; Article 25(2) removes the vendor; Article 26(8) says an unregistered system shall not be used. Fourteen provider obligations, four months, evidence on file: none.

**Close (2:50 to 3:00).** "Article 12(2)(a) already requires the logging to identify situations that may lead to a risk or to a substantial modification. The signal is already mandatory. Nobody is reading it. Here is the verification script; run it yourself, and it pulls every one of those quotations live out of the official text in about ten seconds."

---

## D5. Rehearsal and failure modes

| Risk | Mitigation |
|---|---|
| Language-model latency of nine to twenty seconds through the wrapper kills a three-minute demo | **Zero live model calls in the demo path.** All narrative pre-computed at build time and baked into the JSON, labelled as generated with its date |
| Wrapper or tunnel outage, or venue wifi | One self-contained HTML file, no CDN, no fonts, no fetch. Tested with wifi off. Carried on a USB stick with the hosted link as backup |
| `verify_chain()` raises a false corruption alarm | The default in-memory backend is a bounded ring buffer; after eviction it reports "Chain broken at entry 0" on an untampered chain. The build script sets a SQLite DSN before importing the store and asserts the backend class; `verify_demo.py` prints that class before it prints the result |
| Silent `entry_type` coercion | Five coercion sites in `store.py` catch the error and relabel with no exception and no warning. Enum members are added on day one, before any other code, with a round-trip equality test in continuous integration |
| A reference fails to resolve, leaving a blank citation box | Every reference in every fixture is checked against the catalog and `provision_exists()` in a test. The build fails, not the demo |
| "Your MDR claims are wrong" | The EXTERNAL chip pre-empts it: correct, the MDR is not in our verified corpus, which is exactly why it is yellow; the green ones can be checked right now. Rehearse this as a strength |
| "Is this just a dashboard with hardcoded rules?" | Run `verify_demo.py` live, ten seconds, no network. Then open `duties.py` and show the citation being fetched rather than stored |
| "Where did 0.88 come from?" | Answer immediately: it was invented, it is blue; in a real deployment that number comes out of the instructions for use and the Annex IV filing. The point is what happens when it is crossed |
| Character-encoding corruption in quoted text | UTF-8 throughout, non-ASCII preserved, charset declared, verified by eye in the browser before shipping |
| Screen-share legibility | Designed at 1280 by 720, tested on a projector, every font at fourteen pixels or larger |
| They ask to run it against their real fleet | Have the answer ready: a spreadsheet of thirty devices with name, role, class, intended purpose, log retention, instructions-for-use version and model version, and the six amber checks run against it with no telemetry at all. That is a week |

**Discipline list, to carry into the room.** Say hash-chained payload integrity, not tamper-evident. Say the temporal compound-risk axis is a specification we wrote and have not built, and that this proposal is its first consumer, because that is true and it is the stronger claim. Say no device entity exists, and that the persistent registry pattern it clones is live in production, which is why the estimate is days. Say tenant isolation is a prerequisite build, not existing scaffolding. Say the AI Act and MDR clocks coincide numerically but their triggers differ, and never reuse one clock table across both. Cite Article 73(10), not 73(9). Say MDR Article 61 is clinical evaluation and post-market clinical follow-up lives in Annex XIV Part B. And never present a deadline as awareness plus N days.