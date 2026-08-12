> **Superseded 2026-07-24.** This document was drafted against this extract and
> understates the platform. The current version lives in the legit-ai repository at
> `docs/partners/regenold/` and is grounded in legit-ai, which already ships much of
> what this draft proposed building. Do not circulate this copy.

<!-- Generated 2026-07-23. Companion to LIFECYCLE_ASSURANCE.md. -->
<!-- Regulatory dates from the Digital Omnibus / PE-CONS 30/1/26 are workflow findings -->
<!-- at the confidence marked inline; the repo's pinned EUR-Lex text still carries the -->
<!-- superseded 2027 date and must be re-pinned once the Official Journal number lands. -->

# Gap register: what we must close

## 0. First, what "full requirements" means

"Full requirements" is not a fixed line. It is one of four bars, and they are roughly an order of magnitude apart in cost. The bar is a commercial choice, not a technical fact, and the honest move is to name it before committing capital.

- **L1, demo (credible in a room, synthetic data).** Register a device, declare a conformity envelope, ingest synthetic aggregate telemetry, watch drift fire, compute an Art 72(2)/73 obligation with its deadline, raise a consequence-split alert, show a generated report plus an evidence-chain hash. **Where we are:** reachable now. The parent platform already ships drift ingest, Post-Market Monitoring Plan generation, tiered Art 73 deadline computation, a 106-type hash-chained evidence store with PDF export, and an escalation state machine. Cost: days to two weeks of assembly, zero blockers.
- **L2, pilot (one design partner, one device family, real aggregate data, an output an RA function would show a notified body).** **Where we are:** a roughly 10 to 16 week build. Cost: dedicated engineering plus qualified regulatory-affairs capacity working in parallel, plus the partner's DPO turning around a DPIA. The engineering critical path is short; the schedule risk sits in regulatory-content authoring and the DPO lane.
- **L3, production (multi-customer, real regulatory reliance, contractual SLA).** **Where we are:** adds the entire supplier-side estate: organisation tenancy plus RBAC, an isolated non-public instance, an enterprise LLM contract with a DPA and transfer impact assessment, erasure and encryption reconciled with the hash chain, a real per-device scheduler, SRE and backup/DR, ISO 27001, and rule-pack change control. Cost: several months, with ISO 27001 (6 to 12 months) the longest single lead time, so it must start before feature work, not after.
- **L4, regulatory-grade (the output is relied on in a filing or an audit defence).** **Where we are:** adds what money and calendar cannot rush: a deterministic validatable model with a GAMP 5 CSV package, bitemporal replay, Part 11 attributability, ISO 13485 certification, independent third-party validation of the rule pack, product/professional-indemnity insurance, and at least one notified-body-accepted envelope precedent. It is additionally capped by regulatory dependencies outside our control (Art 96 guidelines, the Art 72(3) voluntary template due 2 September 2027, IMDRF PCCP), so full regulatory-grade status is not reachable before roughly 2027 regardless of spend.

The recommendation is to build toward L2 as the sellable proof, scoped so that L3 and L4 remain reachable without a rewrite.

## 1. The five that decide whether this works at all

These are the genuine blockers, ranked. Everything else is downstream of them or gated by level.

1. **The deterministic-determination decision (front gate, cheap now, near-impossible to retrofit).** The shipped regulatory determination (is this change pre-determined under Annex IV(2)(f), or a substantial modification under Art 43(4)) must be produced by deterministic logic, with any LLM confined to non-decisional prose that fails soft. Nothing downstream works without this: an output that a third-party model can change tomorrow cannot be validated (draft EU GMP Annex 22 permits only locked, repeatable models in critical use; **likely**), cannot be ground-truthed, and cannot be shown to a notified body. **Size:** the decision is free and the architecture already supports it (the pipeline is deterministic; the LLM is a Stage-2 polish that falls back deterministically and never fails the route). The work is a policy and configuration gate plus a Performance Qualification against the deterministic path: weeks, not the months a rebuild would cost. **Depends on:** nothing; it must be made before any L2 engineering, because the ground-truth work and the L4 CSV both assume a reproducible determination.

2. **The conformity envelope, durably bound to persisted telemetry, emitting a signed monitoring report.** This is the product. It bundles three items that are one chain: persist the drift baseline (today it lives in an in-process dict wiped by every redeploy), bind the monitoring-plan thresholds to that persisted reference so a machine-checkable Annex IV(2)(f) envelope exists as an evaluable object (today the plan is a generated document and the drift reference is set independently, with no linkage), and emit the per-device, per-window monitoring report that binds envelope, telemetry, determination, and chain hash (today no such evaluation-result entity exists). Without it there is nothing to sell and nothing to show. **Size:** weeks; it is the headline new engineering. **Depends on:** the deterministic-determination decision.

3. **Trustable determination: an expert-adjudicated ground-truth set.** An RA function will not put a conclusion in front of a notified body that it cannot defend, and "the tests pass" proves only that the code matches the spec, not that the spec's regulatory judgement is correct. We need a curated set of real change scenarios, each independently adjudicated by qualified RA against Art 3(23), Art 43(4), Annex IV(2)(f), and MDCG 2025-6 Q30 (**verified** that the guidance says a pre-determined change is neither an AI Act substantial modification nor an MDR Annex IX 4.10 change; **verified** that the guidance is non-binding), measured for precision and recall. Without it the core claim is an unvalidated assertion. **Size:** weeks, RA-led. **Depends on:** the envelope model.

4. **Organisation tenancy plus RBAC plus an isolated non-public instance (the spine).** Today `tenant_id` is the authenticated user's own id; there is no Organisation, Workspace, or Team entity anywhere in the schema, and the entire authorization model is a single `is_admin` boolean plus a billing tier. A manufacturer is not one person (QA, regulatory affairs, the MDR Art 15 PRRC, clinical engineering), a device must survive an employee's account being erased, and a medtech customer must not be co-resident with anonymous public sign-ups on one process, one cache, one global hash chain. Five other blockers hang off this. **Size:** months, and it must be one workstream with RBAC and the chain re-architecture, not three. **Depends on:** nothing, but it entangles the audit-chain work below.

5. **A sound audit chain: erasable, correctable, attributable evidence.** The evidence chain is the product's proof, and as built it cannot honour it. There is no delete, purge, or retention path on any backend, and the `previous_hash` linkage is global across all tenants, so deleting one customer's row invalidates verification for every other customer: GDPR Art 17 and chain integrity are mutually exclusive as built (**verified** from the code). It also persists the verbatim customer question, and it has no supersession model, so when a customer corrects a past snapshot nothing states which entry is true at audit. No DPA is signed without an erasure answer, and no notified body relies on a chain that cannot represent a correction. **Size:** months, entangled with the tenancy re-architecture (per-tenant chains or crypto-shredding with per-tenant payload keys). **Depends on:** the organisation entity.

## 2. Gap register

Severity is post-challenge (the adversarial pass overrides the lanes where they conflict). Effort is order-of-magnitude. Level is the first bar at which the gap must be closed. Confidence marks the underlying regulatory or code claim.

### Product engineering

| Gap | Blocks | Severity | Effort | Level | Confidence |
|---|---|---|---|---|---|
| Drift baseline and observation history are in-process, wiped on every redeploy | Any durable Art 72(2) lifetime record | Blocker | Weeks | L2 | Verified |
| No conformity-envelope entity binding plan thresholds to the drift reference | The whole Annex IV(2)(f)/Art 43(4) determination | Blocker | Weeks | L2 | Verified |
| No monitoring-report artifact binding envelope, telemetry window, determination, chain hash | The showable L2 output | Major | Weeks | L2 | Verified |
| No idempotency/observation-id on telemetry ingest; a duplicate POST double-counts and can fire a false substantial-modification alert | Trustworthy clock | Major | Weeks | L2 | Verified |
| Registry models AI agents, not devices: no UDI-DI, MDR class, notified body, device-software version, or hybrid-therapy relationship | Device identity | Major | Weeks | L2 | Verified |
| No in-scope screener (Art 111(2), Art 74(3)/(4), in-house Art 5(5)) plus human-attested role wizard running first | Correct routing before data flows | Major | Weeks | L2 | Verified |
| Conformity envelope has no version/effective-date axis: an instructions-for-use change mid-window has no envelope version to judge against | Correct determination over time | Major | Weeks | L3 (decide L2) | Verified |
| One device across N Member States needs N authority clocks; registry is flat and (tenant, name)-unique | Multi-jurisdiction correctness | Major | Weeks | L3 | Verified |
| No outbound tenant-configurable notification channel (webhooks are inbound Stripe only; the one push channel is GitHub issue/PR) | Alerting | Major | Weeks | L3 | Verified |
| No Art 50(2) machine-readable marking of AI-generated text (a control we recommend to others and fail ourselves) | Our own compliance from 2 Aug 2026 | Major | Days | L2 | Verified |
| No historical backfill/replay ingest: a device already years in market starts its lifetime record blank | Credible Art 72(2) record | Minor | Days | L2 | Verified |
| No Art 50(1) "you are interacting with an AI" disclosure in the UI | Our own compliance from 2 Aug 2026 | Minor | Hours | L1 | Verified |

### Non-functional (platform, security, data)

| Gap | Blocks | Severity | Effort | Level | Confidence |
|---|---|---|---|---|---|
| Audit chain has no erasure path on any backend and its hash linkage is global across tenants | Any DPA; GDPR Art 17 | Blocker | Months | L3 | Verified |
| No correction/supersession semantics on the append-only chain (no superseded-by, tombstone, current-truth projection) | Audit defensibility | Blocker | Weeks | L3 (decide L2) | Verified |
| Chain persists the verbatim question plus a 500-char answer excerpt, unencrypted and undeletable | Confidential performance data | Blocker | Days | L3 (interim at L2) | Verified |
| Production LLM path runs through a Cloudflare tunnel to a personal Claude Max subscription (no DPA, no SLA, single-human dependency) | Any regulated onboarding | Blocker | Weeks | L3 | Verified |
| Same deployment serves anonymous public sign-ups and would serve device data; no logical or network isolation | Supplier security review | Blocker | Weeks | L3 | Verified |
| Aggregate-only is not automatically anonymous: WP216 singling-out and inference tests bite at small cell counts | Lawful real-data processing | Blocker | Weeks | L2 | Verified |
| No DPIA support surface (GDPR Art 35(3)(a) systematic-monitoring trigger applies) | Lawful start of a real-data pilot | Blocker | Weeks | L2 | Likely |
| No CI pipeline at all, therefore no per-release regression evidence, test report, or build provenance | Change control, CSV, quality agreement | Blocker | Weeks | L3 | Verified |
| No sub-processor list, no transfer impact assessment; full question text leaves the EU to a US LLM provider | Any hospital DPA (Chapter V) | Blocker | Weeks | L3 | Verified |
| Non-deterministic third-party LLM cannot be CSV-validated (draft Annex 22); mitigated because the determination is deterministic and the LLM only polishes prose | GxP customers and L4 | Major | Weeks | L4 (decide L2) | Verified |
| Audit records have no user attribution (created_by is a constant): breaks Part 11 / Annex 11 attributability | GxP/FDA-facing use | Major | Weeks | L4 | Verified |
| No append-only hashed-payload schema-evolution plan (add a field and you break verify or must version the hash) | Multi-year lifecycle | Major | Weeks | L3 (decide L2) | Likely |
| No bitemporal model: cannot replay a historical determination against the law-then and the rule-pack-then | Audit defence in 2030 | Blocker | Months | L4 (decide L2) | Verified |
| No platform SRE posture (uptime monitoring, alerting, on-call, status, SLA measurement) | A contractual SLA | Major | Weeks | L3 | Likely |
| No documented, tested backup/restore or DR across the four data planes | Regulatory reliance on the record | Major | Weeks | L3 | Likely |
| No documented data residency or EU-only hosting across app, chain, graph, LLM | EU public-sector procurement | Major | Weeks | L3 | Verified |
| Only working scheduler is a global daily GitHub Actions sweep on a hand-rotated admin JWT (no per-entity cadence) | Per-device obligation clock | Major | Weeks | L3 | Verified |

### Regulatory knowledge and clock

| Gap | Blocks | Severity | Effort | Level | Confidence |
|---|---|---|---|---|---|
| MDR/IVDR incident-notification regime absent from the matrix; it currently emits a full-scope AI Act duty for a device, contra Art 73(10). Fix requires the narrowing suppressor plus per-authority routing | Correct duties for our exact customer | Blocker | Weeks | L2 | Verified (Art 73(10)) |
| No awareness clock-start provenance and no business-day/holiday/timezone model for the Art 73 2/10/15-day tiers (Reg (EEC, Euratom) 1182/71) | Correct statutory deadlines | Major | Weeks | L2/L3 | Verified |
| No signed AI Act self-classification dossier (we are a provider of a non-high-risk system; none of the 8 Annex III areas applies) | Supplier qualification | Major | Days | L2/L3 | Verified (Annex III) |
| In-house MDR Art 5(5) devices are not high-risk AI systems (MDCG 2025-6 Q35): the wizard must ask early or mis-route a customer class | Correct TAM and routing | Major | Hours | L2 | Verified |

### Organisational and QMS

| Gap | Blocks | Severity | Effort | Level | Confidence |
|---|---|---|---|---|---|
| No organisation/tenancy entity and no RBAC (only is_admin plus billing tier); spine for five other blockers | Multi-role manufacturer access | Blocker | Months | L3 | Likely |
| Continuous deploy from main violates the ISO 13485 4.1.5 duty to notify changes before implementation | Supplier qualification | Blocker | Weeks | L3 | Verified |
| No versioned rule pack, per-customer pinning, change-impact analysis, or revalidation trigger | Controlled-supplier status | Blocker | Months | L3/L4 | Verified |
| No expert-adjudicated determination-accuracy ground truth | RA trust; NB defence | Blocker | Weeks | L2 | Likely |
| No GAMP 5 CSV package (category rationale, URS, IQ/OQ/PQ, traceability) | GxP customers | Blocker | Months | L4 | Likely |
| No ISO 13485 supplier-qualification pack (QMS evidence, quality agreement) | Onboarding into a QMS | Blocker | Months | L4 | Verified |
| No ISO 27001 / SOC 2 (default procurement gate for SaaS on regulated data) | Enterprise procurement | Blocker | Months | L3 | Likely |
| No control decomposition for Arts 72/73/12; source text already pinned, only the control layer is new | The rule engine's vocabulary for the lifecycle articles | Major | Days | L2 | Verified |
| No one-family medtech crosswalk (ISO 13485/IEC 62304/ISO 14971/IEC 82304 absent from the crosswalk) | Art 72(4) integration story | Major | Weeks | L2 | Verified |
| Art 4 AI-literacy obligation in force since 2 Feb 2025, no training records, and no deployer-side flow-down | Our own compliance; customer onboarding | Major | Days | L2/L3 | Verified |
| No documented competence of the people authoring the rule pack, no two-person independent review | Supplier audit | Major | Weeks | L4 | Likely |
| No independent third-party validation of the rule pack (self-validation is the weakest evidence at the moment it matters) | Audit defence | Major | Months | L4 | Likely |
| No intended-purpose statement and no marketing-claims control (a single sales line flips us into MDR MDSW) | Staying a non-device | Major | Days | L1 | Verified |
| No ISO/IEC 42001 AI management system (increasingly demanded of AI suppliers) | Competitive procurement | Minor | Months | L4 | Likely |

### Content and data

| Gap | Blocks | Severity | Effort | Level | Confidence |
|---|---|---|---|---|---|
| Framework crosswalk covers ISO 42001/NIST/SOC 2 only; no medtech standard | Speaking the customer's QMS | Major | Weeks | L2 | Verified |

### Commercial and operational

| Gap | Blocks | Severity | Effort | Level | Confidence |
|---|---|---|---|---|---|
| Zero legal/policy document set (DPA, Art 28 terms, ToS, SLA, privacy notice, security whitepaper, sub-processor list) | Procurement opens with this pack | Blocker | Weeks | L3 | Verified |
| NIS2 Art 21(2)(d) supply-chain duties will be contractually flowed down by every hospital and manufacturer customer | Contracting | Major | Weeks | L3 | Verified |
| No notified-body-accepted precedent for an envelope determination (MDCG 2025-6 is non-binding) | Reliance in a filing | Major | Months | L4 | Likely |
| No product/professional-indemnity insurance sized to reliance (PLD 2024/2853 now covers software) | Procurement gate at L4 | Major | Weeks | L4 | Likely |

### Reframed by the adversarial pass (do not carry as build gaps)

| Item | Correct treatment | Effort | Confidence |
|---|---|---|---|
| Parent `campaign_schedules.cron_expression` (nothing evaluates it) | Not a build gap: a one-line "do not reuse; build a fresh per-entity scheduler" note in the design doc | Hours | Verified |
| FHIR/DICOM/HL7 clinical interop | Not a gap: a deliberate scope choice; adopting it would reintroduce the record-level data the design forbids. See section 5 | Zero | Verified |
| EUDAMED submission path | Watch item, not a build gap: generate the artifact, let the customer submit | Deferrable | Verified |
| CRA agent scope | A design decision, not a backlog item: an on-prem collector pulls us into CRA; offline aggregate upload keeps us out. See section 5 | Design-time | Verified |

## 3. Regulatory unknowns that are themselves gaps

These are the open legal questions where being wrong is expensive. Each carries a confidence mark and an interim posture.

- **Applicability date for AI-enabled MDR/IVDR devices: 2 August 2028 (verified).** The Digital Omnibus on AI replaces Art 113(3)(c) so that Chapter III obligations for Art 6(1)/Annex I high-risk systems apply from 2 August 2028 (**verified** against the signed act, PE-CONS 30/1/26 REV 1, LEX 2532, 8 July 2026). The repo's pinned text still carries the superseded 2 August 2027 date. **Interim posture:** lead go-to-market with MDR Art 83/84 post-market surveillance, which is live today, and treat the AI Act layer as a 2028 overlay. Parameterise the Art 111(2) grandfathering date; it is now a floating date, not 2 August 2026. Cost to resolve: none, it is settled; re-pin the text once the Official Journal number appears.
- **Digital Omnibus status and Section A/B (verified, with a residual watch).** MDR and IVDR remain in AI Act Annex I Section A (**verified**: only machinery was moved to Section B in the signed act). The Art 6(1) high-risk routing survives. However, the separate MDR simplification file 2025/0404(COD) is still pending and still proposes moving MDR/IVDR to Section B; the machinery precedent makes a revived attempt more plausible (**verified** the file is pending; the outcome is **unconfirmed**). **Interim posture:** make Section A vs Section B a data-driven attribute of the harmonisation-legislation record, never a hardcoded assumption. Cost to resolve: watch the file; a few counsel hours per quarter.
- **Art 72(3) template abolished, guidance and voluntary template due 2 September 2027 (verified).** The binding implementing act was deleted and replaced with non-binding guidance plus a voluntary template (**verified**). **Interim posture:** design the plan/envelope model from MDR Art 83/84 practice, version it, and make it export-mappable so we emit the voluntary template when it lands rather than migrate to it. Say plainly to the partner that we are designing into a vacuum until September 2027; do not imply regulatory endorsement.
- **Art 96(1)(c) substantial-modification guidelines not yet published (verified).** These will set the outer boundary of what an Annex IV(2)(f) envelope may pre-authorise, the single most important parameter of the envelope model. **Interim posture:** keep the envelope boundary as versioned, adjustable rules, not hardcoded, and align now to the FDA triad (Description of Modifications, Modification Protocol, Impact Assessment) since IMDRF convergence will most plausibly land near it. Cost to resolve: wait for the act, then a scoped RA reassessment.
- **New Art 2(13) delegated act (due 2 August 2027) may limit Arts 9 to 15 and 17 to 25 for Section A devices (verified).** Art 12 (logging) and Art 19 (log retention) are prime candidates to be disapplied for medical devices, which threatens the Art 12(2)(a) logging premise. Arts 72 and 73 sit outside the limitable range, so the monitoring anchor is safe (**verified**). **Interim posture:** do not build the product's core on the Art 12 logging signal alone; anchor it on Art 72/73. Cost to resolve: wait for the delegated act.
- **Whether Arts 72/73 bite before 2 August 2028 for Annex I devices (verified as an open question).** Chapter IX is not textually deferred, so a literal reading applies them from 2 August 2026; the counter-reading is that they bind only providers of high-risk systems, and none exist under Art 6(1) until 2028. This determines whether the AI Act hook is a 2026 or a 2028 conversation. **Interim posture:** sell on MDR PMS, which does not depend on the answer; obtain a counsel opinion before making an AI Act timing claim. Cost to resolve: a focused counsel memo.
- **Companion app is almost never an Art 117 integral combination (verified).** A drug plus companion app is two regulated objects (a medicinal product under a marketing authorisation with a pharmacovigilance clock, and a separate MDR device with its own PMS clock), not one integral product with a single notified-body opinion (**verified** against Art 117 and Art 1(8)/(9)). **Interim posture:** model a hybrid therapy as two entities joined by a relationship edge (referenced by SmPC, co-packaged, or integral); never present it as an integral combination to a pharma audience. Whether the EMA drug-device guideline even covers software is **unconfirmed** and needs the guideline PDF read in full.
- **MDCG 2025-6 Q30 is the strongest foundation, and it is non-binding (verified).** The AI Board and MDCG have jointly stated that a change inside the Annex IV(2)(f) envelope is neither an AI Act substantial modification nor an MDR Annex IX 4.10 change (**verified**), but MDCG guidance is expressly non-binding and parts of it are now stale on dates. **Interim posture:** cite it for the logic, never for timing; do not market the product as "the EU PCCP" (no such thing exists), market it as an Annex IV(2)(f) conformity envelope.
- **No Official Journal citation yet for the Digital Omnibus (verified).** As of the analysis it was signed but unpublished, so any date keyed to entry into force is unresolvable and the pinned text must be re-pinned once the OJ text appears (**verified**). **Interim posture:** cite the signed act (PE-CONS 30/1/26 REV 1) with a note that the OJ number is pending.
- **IMDRF PCCP status and EU uptake (unconfirmed).** The most likely future source of a mandated envelope schema; a final IMDRF document could not be confirmed. **Interim posture:** keep the envelope a versioned, migratable schema with an explicit mapping layer. Cost to resolve: a primary-source check.
- **DiGA and PECAN recurring duties (likely, not primary-verified).** Both are hard-deadline, time-boxed reimbursement regimes with a delisting consequence and an ongoing real-world-evidence duty, confirmed at statute-summary level but not from the DiGAV sections or the JORF decree (**likely**). This matters because it is what we can sell before 2028, pointed at a payer rather than a regulator. **Interim posture:** do not encode a specific DiGA/PECAN deadline until the primary text is read; the risk of a wrong compliance clock is a customer losing reimbursement.

## 4. What the parent platform closes for us

Verified on disk. These items can be removed from the build estimate.

- **A continuous post-market monitoring loop (verified).** The parent's Continuous Compliance Engine implements drift-to-reassessment, incident escalation with Art 73 deadline tracking, and monthly evidence-backed attestation, and carries the escalation state machine the prior gap list said did not exist. This is the architectural spine; the proposal is "harden and re-domain an existing loop," not "build a platform." It is a port-with-changes, not production-ready for devices.
- **An aggregate-only telemetry ingest endpoint and schema (verified).** The ingest contract is a bare aggregate metric map, structurally incapable of accepting patient data, and tenant-scoped. The "never ingest patient data" constraint is already enforced upstream, which is a strong proposal point. The persistence layer, however, is a rewrite (see the in-memory drift gap).
- **Deadline computation and a multi-regime notification matrix (verified).** Tiered Art 73 arithmetic, a classification model, and a per-regime duty matrix all exist and are reusable. The MDR/IVDR row, a durable timer, and a sweep driver are absent. Caveat: the Art 73 tier values are asserted by the parent's own docstring and were not independently re-verified against EUR-Lex, so re-verify before quoting them to a customer.
- **An extensible evidence type system with read/export (verified).** 106 hash-chained evidence types including several on-thesis, a Postgres store, an export module, an erasure module, and working PDF export. This closes the "closed 2-member enum," "no read/export surface," and "no report generation" concerns outright; those were artifacts of the extract, not the platform.
- **An asset registry with a recurring review clock (verified).** Tenancy, ownership, `next_review_date`, retirement, an advisory `enabled` flag, and idempotent registration transfer directly. The domain columns are agent-shaped and must be replaced with device identity. The `enabled` kill switch must stay advisory: suspension is a clinical judgement, not an actuator.
- **Conformity document generation (verified).** A QMS, EU Declaration, Art 72 PMMP, and registration-readiness suite, each stamped into the evidence chain. The strongest single commercial asset: a manufacturer can be shown a generated PMMP on day one. The gap is that nothing yet evaluates telemetry against the thresholds that plan declares; closing that link is the highest-leverage new work.
- **Billing, audit logging, MCP server skeleton, roadmap engine, and a crosswalk framework (verified).** Billing and audit logging are production-grade and can be removed from the estimate. A working MCP server skeleton exists in a sibling (specter-oss) and converts the MCP work from design to adaptation. The roadmap engine's deadline anchor is the right primitive. The crosswalk machinery is sound but speaks the wrong frameworks for a device manufacturer.

What the parent does not close, so the gap stays open: **there is no organisation entity** (tenancy is the individual user, not shrinking the gap but deepening it), no MDR/IVDR regime content, no medtech crosswalk, no Art 72/73/12 control decomposition, no per-device scheduler (the `cron_expression` column is never evaluated), no outbound notification channel, no FHIR/DICOM/HL7, and no EUDAMED. **No sibling project contributes reusable runtime-monitoring infrastructure** (verified: each is stale, archival, or a static code scanner, which is the opposite of runtime telemetry). We must not let any unverified parent capability shorten the plan.

## 5. What we can delete instead of build

This is where the schedule is actually won. Each cut retires a whole class of gaps at zero engineering cost, with a stated commercial price.

- **Serve providers only, not deployers.** Drops the Art 26/27 deployer content, the FRIA path, and the Art 26(5) suspension-consequence complexity. Commercial cost: cannot sell to hospitals as deployers in the first release.
- **Annex I Section A devices only, not Annex III.** Art 74(3)/(4) suppress the generic Art 79/80/82/83 market-surveillance rows (**verified**), the Annex III content is never needed, and AI Act obligations do not bite until 2 August 2028, so the product sells as MDR PMS automation today. Commercial cost: excludes standalone Annex III medical AI that is not a Section A device.
- **Offline aggregate upload only, never a live integration or a shipped agent.** The single most valuable cut. It permanently retires FHIR/DICOM/HL7 (adopting them would reintroduce record-level data the design forbids) and keeps us entirely out of Cyber Resilience Act scope, because CRA obligations attach only when we place a product with digital elements (a collector, agent, SDK, or edge component) on the customer's fleet (**verified** against Reg (EU) 2024/2847 Art 2 to 3). A pull-from-customer-file model never triggers it. Commercial cost: the customer does more integration work; no real-time alerting.
- **One Member State only.** One holiday calendar, one competent authority, one language, and one reimbursement regime (DiGA or PECAN, not both). Permanently defers the multi-jurisdiction deadline clock and the per-device authority fan-out. Commercial cost: a single-country beachhead.
- **Generate, do not submit (EUDAMED and the AI Act Art 71 register).** Produce the artifact and let the customer submit. Commercial cost: not a submission service.
- **Exclude in-house MDR Art 5(5) devices.** Per MDCG 2025-6 Q35 they are not high-risk AI systems (**verified**), so serving them would be serving the wrong obligations. Commercial cost: excludes hospital-developed AI as an AI Act buyer, which is correct rather than lost revenue.

The recommendation is to adopt providers-only, Annex I Section A only, offline aggregate upload only, and one Member State as the default L2 scope. That combination closes roughly a third of the register and removes an entire regulatory regime (CRA).

## 6. Never defer

Deferring any of these is a safety, legal, or trust failure.

- **Never ingest record-level or patient data.** Architectural, already enforced by the aggregate-only ingest contract; it must never regress (Art 9 health data).
- **The small-cell anonymisation controls.** Minimum cell size, suppression, no free-text passthrough, subgroup allowlisting. "Aggregate" alone fails the WP216 inference and singling-out tests; deferring these is a re-identification failure on Art 9 data (**verified**).
- **Suspension is a clinical judgement, never an actuator.** Alerts split by consequence; the kill-switch stays advisory. Deferring this makes the platform an unlicensed clinical decision system that could cause patient harm.
- **Deterministic, reproducible determinations.** An output that changes under us is inadmissible in any GxP or filing context (**likely**, draft Annex 22). This is an architectural decision that must be locked at L2 design time; it cannot be retrofitted at L4.
- **Append-only, never-overwrite, always-versioned history.** The engineering can be staged, but the design decision must be locked from day one, because history cannot be retrofitted after entries exist.
- **The in-scope screener running first.** Art 111(2), Art 74(3)/(4), and the in-house Art 5(5) check, before any obligation fires. Deferring it mis-routes customers into obligations they do not have.
- **Intended-purpose and marketing-claims control locked before any sales material ships.** A single line ("detects malfunction affecting patient safety") flips the platform into MDR software as a medical device requiring a notified body (**verified** against MDR Art 2(1) and MDCG 2019-11). Cheap to lock, catastrophic to discover late.
- **Honest scope and status representation.** Never present the product as "the EU PCCP," never imply notified-body endorsement, never present a drug plus companion app as an Art 117 integral combination, and never sell "AI Act compliance now" for an obligation that binds in 2028. The first competent buyer detects the difference.

## 7. Critical path to a pilot

The realistic total to L2 is roughly three months (10 to 16 weeks), and it runs as two parallel lanes that converge on the signed monitoring-report artifact. The engineering critical path is short because the parent supplies most of the plumbing; the schedule risk is the parallel regulatory-affairs lane and the partner's DPO.

**Gate, before anything (days, a decision not a build):** lock the deterministic-determination architecture (determination is deterministic, LLM confined to non-decisional prose) and the append-only bitemporal history decision. Both are cheap now and near-impossible to retrofit; deferring either poisons the ground-truth work and the L4 CSV.

**Lane A, engineering critical path (serial, roughly 7 to 9 weeks):**
1. Persist the drift baseline (fix the in-memory state), roughly 2 to 3 weeks.
2. Bind the monitoring-plan thresholds to the persisted drift reference so a machine-checkable conformity envelope exists as an evaluable object, roughly 3 to 4 weeks. This is the headline new work.
3. Emit the signed monitoring-report artifact, roughly 2 weeks.

**Lane B, regulatory and legal, running in parallel (RA-led, not gating Lane A):**
- One-family medtech crosswalk plus Art 72/73/12 control decomposition (the source text is already pinned, so only the control layer is new), roughly 3 to 4 weeks.
- The MDR/IVDR regime row with the Art 73(10) narrowing suppressor, roughly days for the row and weeks for correct-and-safe behaviour.
- The device entity for the one family, roughly 1 to 2 weeks.
- The DPIA support pack plus a scoped pilot DPA, roughly 2 to 3 weeks, gated by the LLM-path decision.
- The enforced small-cell anonymisation controls, roughly 2 weeks.
- The expert-adjudicated determination-accuracy ground truth, roughly 3 to 4 weeks.

**Front door, before real data flows (roughly 2 weeks, must land before Lane B feeds the pilot):** the Art 111(2)/74(3)(4)/5(5) in-scope screener plus the human-attested role wizard.

**Honest total:** about three months, assuming dedicated engineering plus qualified RA capacity in parallel plus a responsive partner DPO. The binding constraint is not code volume; it is the RA capacity to author correct one-family content and adjudicate the ground truth at the same time, and the DPO's DPIA turnaround. Staff those two lanes first. Everything at L3 (organisation and RBAC, per-device scheduler, enterprise LLM and DPA, erasure and encryption, SRE and DR, ISO 27001, change control) is deliberately out of the L2 estimate and must not be allowed to creep in; ISO 27001, at 6 to 12 months, should nonetheless be started during the pilot so it does not gate the first production deal.