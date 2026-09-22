# EvoOntology → Regenold architecture review

**Date:** 2026-09-22  
**Source reviewed:** Chong, Zhang, Fan & Du, *EvoOntology: A Self-Evolving Ontology Layer for Data Agents*, arXiv:2609.15779v1 (2026-09-14), supplied PDF and the authoritative arXiv HTML.

## Executive decision

EvoOntology is relevant to Regenold's ontology and knowledge-graph roadmap, but it is **not evidence for turning on an autonomous self-editing legal ontology**. The paper's transferable contribution is the separation of:

1. a typed semantic content layer;
2. a schema layer that constrains legal object and edge shapes; and
3. a runtime tool layer that retrieves only the semantic records needed for the current step.

Its second contribution is a controlled evolution loop: diagnose a trajectory failure, attribute it to one layer, propose a typed patch, and accept it only after a same-backbone paired held-out evaluation. That gate is compatible with this repository's existing paired-gate discipline. The paper does not establish that unconstrained LLM edits are safe for a statute, nor does it justify default-on graph expansion or automatic changes to legal citations.

## What the paper actually claims

The paper defines an ontology state as content, schema, and tools. Content contains four typed families: **Terms**, **Mappings**, **Constraints**, and **Evidence**. Mappings ground concepts to concrete data fields and paths; Evidence records the probe or observation supporting a mapping. The tool layer exposes selective browse and resolve operations through MCP rather than injecting the complete ontology into every prompt.

The builder proposes concepts from a workload, probes the underlying data, verifies declared types/filters/value distributions, and commits only verified candidates. The evolution loop clusters trajectory signatures, attributes each signature to Content, Tool, or Schema, applies a typed intervention, and compares parent/candidate on the same held-out validation set, backbone, decoding, and interaction budget. The paper uses reciprocal folds and reports results across data-agent benchmarks; those results are **not direct evidence for EU AI Act legal QA**.

The strongest internal ablations are directional rather than universal guarantees: removing the gate is reported as the largest regression, attribution is next, and typed patches outperform free-form rewrites. Mappings and Evidence are reported as the most important content families. The correct transfer is therefore the governance/evaluation pattern, not the paper's absolute percentage points.

## Current Regenold mapping

| EvoOntology concept | Current implementation | Status and consequence |
|---|---|---|
| Schema layer | `app/graph/provision_schema.py`, `app/graph/schema.py`, `app/graph/ontology.py`, `NodeType`/`EdgeType`, endpoint maps, import/self-checks | **Strong but split.** There are multiple graph vocabularies for provision-level and compliance-layer graphs. This is an existing integration risk; do not merge them casually because the modules serve different graphs. |
| Content: Terms | `app.data.ontology` practices, Annex III categories, phases, actor/risk enums; BM25 ontology virtual documents in `app.data.kb_search` | **Present.** Mostly hand-authored and deterministic. |
| Content: Mappings | `ROLE_OBLIGATIONS`, `kb_xrefs`, requirement anchors, GraphRAG entity/role maps, Neo4j hierarchy and shadow bridge | **Present but distributed.** Mappings are not represented as one typed, provenance-bearing object. |
| Content: Constraints | `validate_legal_triple`, existence checks, role/risk matrices, citation guards, scope guards, graph endpoint validation | **Strong and safety-critical.** These must remain authoritative over learned proposals. |
| Content: Evidence | `provision_text`, EUR-Lex corpus, graph provenance, reasoning traces, benchmark checkpoints, evidence store | **Present but not unified.** There is no common evidence object linking an ontology assertion to exact source text, hash/version, and validation status. |
| Runtime tools | `kg_context`, `graph_aware_retrieval`, `embedded_graph`, Neo4j/Aura queries, BM25/dense retrieval, deterministic route passes | **Partly present.** Retrieval is callable, but the model generally receives rendered context rather than a small, explicit browse/resolve tool contract. `graph_aware_retrieval` documents some wiring as future work and is default off. |
| Builder | Seed scripts and deterministic registries (`scripts/seed_neo4j_kb.py`, `app/graph/ontology_ingest.py`) | **Deterministic builder exists.** No LLM builder should be added before evidence/provenance schemas exist. |
| Trajectory attribution | Judge remarks, checkpoints, failure clusters, provenance and gate artifacts | **Operationally present, not productized.** Current analysis is manual/scripts rather than a typed signature store. |
| Typed evolution patch | No accepted/rejected ontology patch ledger | **Missing.** This is the clearest paper-derived gap. |
| Backbone-conditional paired gate | `evals.harness.gate_validity`, repeated generations, void/degraded guards, official scoring | **Strong existing foundation.** It must be reused, not replaced. |
| Versioned state / rollback | `KB_VERSION`, seed versions, cache-key wiring, Git/PR history | **Partial.** Versioning exists, but not as an atomic ontology snapshot with parent, patch, evidence, gate, and rollback metadata. |

## Grounded gaps and risks

### 1. The ontology is not one coherent runtime contract

`app.data.ontology` is the deterministic legal registry, while `app.graph.ontology` and `app.graph.provision_schema` describe different graph concerns. This is intentional and documented, but the answer path also consumes role maps, xrefs, provision text, Neo4j schema, local mirrors, and prompt clauses. The risk is not that these modules are separate; it is that a new mapping can be added to one surface and silently omitted from another.

**Required improvement:** add a read-only reconciliation report that compares canonical IDs, role/risk mappings, graph edge declarations, seed templates, and citation existence. Do not refactor the schemas until this report is stable.

### 2. Evidence is available but not attached to each ontology claim

Current consistency tests prove references resolve, but a registry entry does not consistently carry: source document identity, exact quoted support, source hash/version, claim type, and validation timestamp. That makes expert review and rollback harder than it needs to be.

**Required improvement:** introduce an immutable, data-only `OntologyEvidence` record and require new proposed mappings to reference one or more records. Existing hand-authored entries can be migrated incrementally; no request-path behavior changes in phase one.

### 3. Runtime access is mostly context rendering, not selective browse/resolve

`kb_search`, `kg_context`, and `graph_aware_retrieval` already provide selective retrieval, but their outputs are assembled into prompt blocks. The paper's key operational distinction is that the agent can browse a compact manifest and resolve linked records on demand. For legal QA, this should be implemented as a deterministic internal contract first, not necessarily exposed as public MCP.

**Required improvement:** define two narrow read-only interfaces: `browse_concepts(query, kind, limit)` and `resolve_concept(id, include_evidence, include_constraints)`. They should return typed records, impose hard caps, and never create citations without an existence check. Existing retrieval remains the fallback during rollout.

### 4. Self-evolution is currently manual and lacks typed attribution artifacts

The repository has judge remarks, per-row provenance, and paired gates, but there is no durable `signature → attribution → patch → result` record. Without that record, it is difficult to distinguish a content defect from a tool/manifest defect, a prompt defect, or a judge/dataset artifact.

**Required improvement:** add an offline evolution ledger. Candidate patches must be one-level-only (`content`, `tool`, or `schema`), include a hypothesis and affected IDs, and be rejected by default until a paired hard-mode gate passes.

### 5. Legal QA needs stricter gates than the paper's task metrics

The paper evaluates data-agent task outcomes. Regenold must additionally enforce: no unsupported statutory citation, no gold-head loss, no polarity/exception regression, no tenant/provenance leak, no fallback contamination, and no change to the answer contract outside the declared scope. A scalar improvement is insufficient.

**Required improvement:** require a gate bundle: answer correctness loose/strict, reference correctness loose/strict, answer/reference conciseness, tone, speed, gold-head retention, transport validity, and repeated-draw stability. The existing void guards and three-generation hard split should be the admission mechanism.

## Proposed implementation sequence

### Phase 1 — evidence and reconciliation (safe, offline)

* Define immutable records for `Term`, `Mapping`, `Constraint`, and `Evidence` in an offline module.
* Add source/version/hash and exact-support fields; reject empty evidence for legal claims.
* Generate a reconciliation report across `app.data.ontology`, `role_obligations`, `kb_xrefs`, `ARTICLE_EXISTENCE`, graph schema, and seed templates.
* Add tests for missing references, invalid edge endpoints, role/risk contradictions, and evidence-less proposals.
* Keep all runtime flags and outputs unchanged.

### Phase 2 — read-only semantic access (safe, shadow mode)

* Implement bounded deterministic browse/resolve adapters over the existing registries and graph context.
* Log which semantic IDs were browsed/resolved and which records were actually used.
* Run shadow comparison against the current Stage-1 retrieval: recall, citation precision, latency, and context size.
* Do not let shadow results alter wire references or prompts until a paired gate proves non-regression.

### Phase 3 — trajectory attribution and typed candidate patches (offline)

* Convert judge remarks and checkpoint rows into normalized failure signatures: missing term, wrong mapping, missing constraint, missing evidence, tool miss, prompt omission, or transport degradation.
* Attribute exactly one primary layer per candidate, with optional linked content IDs.
* Generate a patch manifest, not a direct source mutation. Store parent snapshot, proposed diff, hypothesis, evidence, and target rows.

### Phase 4 — paired admission and promotion

* Evaluate parent/candidate on the same frozen hard rows, at least three independent generations per row per arm, with Bedrock/wrapper provenance and symmetric degraded-row exclusion.
* Promote only when the declared target axis improves and all safety axes meet floors; otherwise record rejection.
* Require a clean PR, CI, deployment health, and live smoke before promotion. Rollback is a pointer to the parent snapshot, never an inverse LLM edit.

## Recommended first gate

The highest-value, lowest-risk experiment is **not** autonomous evolution. It is a read-only semantic browse/resolve adapter for the existing ontology, evaluated in shadow mode on the Article 50, biometric, medical-device, role-assignment, and citation-grain failure clusters. It tests the paper's central runtime claim while isolating retrieval/tool exposure from content changes.

Pre-registered success conditions:

* no increase in unsupported or excess references;
* no loss of answer/reference strict correctness or gold heads;
* reduced missing-sub-point and role/risk mismatch counts;
* no increase in prompt size beyond the declared cap;
* no transport/fallback contamination;
* latency within the current board's tolerance;
* effect reproduced across three generations per row.

A result that fails any safety condition is a falsification of that adapter for production, not a reason to tune the gate after seeing the result.

## What should not be shipped from this paper alone

* No default-on LLM self-editing of the legal ontology.
* No free-form graph/schema rewrites.
* No global citation pruning based on ontology membership.
* No automatic acceptance from a single judge score or a data-agent benchmark score.
* No claim that the paper's DDR/BIRD/InsightBench gains transfer to EU AI Act QA.

## Validation performed for this review

The existing legal-ontology regression surface was inspected and is the correct baseline for the next change. It includes:

* ontology and legacy-map reference existence checks;
* cross-reference graph endpoint and self-edge checks;
* role/risk legal-triple checks;
* shadow-node and Neo4j seed reconciliation checks;
* paragraph/point hierarchy and citation-format checks;
* dotted-subpoint and citable-base safety tests.

The next implementation should add the Phase-1 data model and reconciliation tests before any runtime wiring. This review deliberately makes no unvalidated default change.

## Phase 1 completed in this pass

* Added `app.data.ontology_evidence`: immutable evidence records and typed,
  evidence-bearing patch proposals. These proposals are review artifacts only;
  they cannot mutate the live ontology.
* Added `app.data.ontology_reconciliation`: an offline report covering ontology
  references, role/risk mappings, xref endpoints/self-edges, and schema edge
  declarations.
* Added regression tests for both contracts. The current deterministic ontology
  reconciles cleanly.
* Audited an existing Codex-agent change and promoted only the evidence-backed
  emotion-route correction: the old negative lookahead was order-dependent, so
  medical-device questions mentioning emotion recognition could incorrectly enter
  the Article 50 supplement. The whole-question exclusion now routes those
  shapes away from the biometric/patient Article 50 trigger, while non-emotion
  biometric cases remain covered.

Validation for this pass: **102 focused tests passed**, Ruff passed on all new and
modified test/model files, and the live service health check remains HTTP 200.
The next phase remains shadow-only browse/resolve access; no autonomous evolution
or graph default has been enabled.
