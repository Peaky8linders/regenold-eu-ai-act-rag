# Deep Code Review: HyPA-RAG integration (R329)

**Date:** 2026-08-13
**Branch:** `main` (uncommitted working tree) -> `3e18931`
**Scope:** the uncommitted Gemini-agent HyPA-RAG work + bundled R328 Bedrock path
**Diff size category:** Large (394 insertions across 11 tracked files, +660 lines of new untracked modules/tests)
**Source paper:** HyPA-RAG, Kalra et al. 2025, arXiv:2409.09046v2

## Executive summary

The HyPA-RAG integration shipped **default-ON without ever running the merge gate**, and it
is a measured regression on the one axis this project has least headroom on. An in-place
davidath 476 A/B attributes **100%** of the damage to the two HyPA flags: QA **Ref
Conciseness -0.2094** (0.4390 -> 0.2296, a 48% collapse), **Ref Strict -0.1137**, and **one
dropped gold reference** — the R142.1 red line. The paper's own ablations point the same
way: PA-RAG (*without* the knowledge graph) beats HyPA-RAG on all four metrics, and the only
ablation-positive component is a reranker, which was not implemented.

Highest-severity finding: **[C1] over-citation via unconditional BM25 fusion into
`query.entities`**. Confidence in the measurement is high — arm A reproduces the documented
baseline byte-for-byte on all six axes, and the two arms share an identical dataset
fingerprint.

## Measurement

Deterministic env, run **in place** (a worktree has no `.env` and manufactures phantom
regressions). Arms differ only by the two HyPA env flags, so this isolates the lever;
all other uncommitted changes are present in both arms.

| davidath 476, QA (n=137) | arm A (HyPA OFF) | arm B (HyPA ON) | delta |
| --- | --- | --- | --- |
| Ref Conciseness | 0.4390 | 0.2296 | **-0.2094** |
| Ref Strict | 0.5536 | 0.4399 | **-0.1137** |
| Ref Loose | 0.8394 | 0.8832 | +0.0438 |
| Ans Strict | 0.4072 | 0.3739 | -0.0333 |
| Ans Loose | 0.1407 | 0.1175 | -0.0232 |
| latency max | 2,089 ms | 10,761 ms | +8,672 ms |

Scenarios (n=339) are **byte-identical across arms** — HyPA fires only on QA-shaped rows.
Arm A equals the documented CLAUDE.md baseline exactly, which also proves the *other*
uncommitted changes (ontology, scenario_classifier, kg_context, the Stage-2 gate rewrite)
are davidath-neutral.

Per-row attribution (zero-variance, compares recorded `pred_refs`):

```
rows with changed pred_refs: 73  (all QA)
mean refs/row  A=5.952  B=6.242   total delta +138
GOLD DROPPED: 1  -> qa_041 lost 'Article 50'
top added:    Article 16 (+20), 17 (+18), 19 (+14), 6 (+7), 92 (+6)
top dropped:  Article 13 (-7), 11 (-4), 14 (-4), Article 10.3, Annex III.2
```

`Article 10.3` and `Annex III.2` disappearing is the sub-point-grain loss (C2).

## Critical issues

### [C1] Unconditional BM25 fusion into `query.entities` causes wire-level over-citation
- **File:** `app/engines/_graph_rag_impl.py:8351` (HyPA block in `ask_compliance_question`)
- **Bug:** the block calls `top_articles_by_relevance(...)` on every request and merges the
  result into `query.entities`. `_deterministic_parse` runs BM25 only behind `if not
  entities:`, and the comment at that site records the gate as load-bearing: for
  *"Summarise EU AI Act Art. 13"* the anchor is already extracted, but the tokens
  "eu"/"ai"/"act" score against unrelated rows, which "would pollute the citation set".
- **Impact:** `query.entities` feeds `EC_CHECKER_OBLIGATION_MAP` (one citation per match),
  `cross_refs(primary, limit=2)` (multiplicative), `get_article_requirements`, and the
  `"Annex III" in query.entities` AST trigger. Reproducing the comment's own example:
  `['Art. 13']` -> `['Art. 13','Art. 109','Art. 2','Art. 106','Art. 87']`. Engine citations
  mean **2.60 -> 9.00**. At the wire: *"What is a deployer under the AI Act?"*
  `['Article 3.4']` -> 7 references.
- **Fix applied:** gate fusion on `not query.entities`, plus both flags default OFF.
- **Confidence:** High. **Found by:** Logic, Contract, Error-handling, Paper-fidelity.

### [C2] Sub-point grain destroyed for pre-existing entities
- **File:** `app/engines/_graph_rag_impl.py:8395`, root cause
  `app/engines/hybrid_rrf_retriever.py:79` (`canonicalize_to_internal_ref`)
- **Bug:** the block applied `canonicalize_to_internal_ref` to **every** original entity, not
  just fused candidates. That function matches the sub-point group then discards it,
  returning the bare head. `['Art. 50','Art. 50.1'] -> ['Art. 50']`.
- **Impact:** the KB distinguishes sub-points — `Art. 50` is a summary, `Art. 50.1` is the
  provider chatbot-disclosure duty, `Art. 50.2` the synthetic-content marking duty. The
  grounded judge scores at sub-point grain (R286). Confirmed at the bench layer:
  `Article 10.3` and `Annex III.2` vanish from `pred_refs` in arm B.
- **Fix applied:** originals kept first and verbatim; fused candidates appended only if
  not already represented.
- **Confidence:** High. **Found by:** Logic (Contract asserted the opposite — refuted, its
  own evidence table contains `Article 3.4`).

### [C3] Stage-2 multi-article trigger rewritten into dead code
- **File:** `app/engines/_graph_rag_impl.py:5946`
- **Bug:** `len(query.entities) >= 3` was replaced with a predicate requiring
  `e in question or e.startswith("Article ")`. Entities are always internal short form
  (`Art. N`), so the second disjunct is unsatisfiable and the first demands the user type
  "Art. 9" literally.
- **Impact:** measured over all 476 davidath questions — old rule fired **346** times
  (72.7%), new rule fired **0**. Latent, not live: the sole call site
  (`_graph_rag_impl.py:7833`) is guarded by `_stage2_simple_skip_enabled()`, default OFF.
  It arms the moment that flag is flipped for the A/B its own docstring contemplates.
  Invisible to davidath, which runs `provider=cli` where Stage-2 never fires.
- **Fix applied:** reverted to `len(query.entities) >= 3`.
- **Confidence:** High. **Found by:** Logic (+ direct measurement).

## Important issues

### [I1] Duplicate `reciprocal_rank_fusion` — re-implements an already-refuted lever
`app/engines/hybrid_rrf_retriever.py:132` duplicates `app/engines/turboquant_index.py:539`,
consumed via `app/data/kb_search.py:506`. The existing one is gated by `REGENOLD_RRF_FUSION`,
default **`"0"`** (`kb_search.py:458`) because RRF measured a wash **three times**
(`docs/ROUNDS.md` R31/R69: *"davidath is BM25-saturated — proven again, third time since
R31"*). The new duplicate shipped default-ON. **Not deleted** — left as an opt-in knob.

### [I2] Duplicate `fetch_provision_hierarchy` definition (F811)
`app/engines/kg_context.py:624` shadowed the original at `:330`. Bodies were semantically
identical so runtime was unaffected, but edits to the first definition would silently do
nothing. **Fix applied:** duplicate deleted.

### [I3] Bedrock client pins region at first construction
`app/llm/bedrock_client.py:284`. `_get_runtime_client()` builds the boto3 client once;
`_resolve_region()` runs only at construction. Model selection *is* re-read per call, so a
mid-process region flip (exactly what the A/B harness does) desyncs region from model — an
`eu.` model against a non-EU region hard-fails `ValidationException`, which the new
fail-soft path swallows. Any Bedrock A/B would silently measure nothing.
**Not fixed** — Bedrock is not on the default path; flagged for the owner.

### [I4] Adaptive router provides almost no adaptivity
`app/engines/query_complexity_router.py:97`. Measured class distribution: QA
`{1: 118, 2: 18, 0: 1}` — Class 0 fires **0.7%**; Scenarios `{2: 339}` — Class 2
saturates **100%**. `is_complex_question` routes on sentence count, and every scenario is
multi-sentence, so the scenario half runs permanently at the widest, noisiest setting.

### [I5] Four of five adaptive parameters are dead
`query_rewrites`, `kg_max_keywords`, `kg_depth`, `kg_max_units` have zero production
consumers; only `top_k_dense` is read. The paper's distinguishing claim (§7 — the classifier
tunes KG depth and rewrites, not just top-k) is unimplemented. What ships resembles the
paper's `k`-only ablation row, its weakest adaptive configuration.

### [I6] "Hybrid sparse+dense" is sparse-only by default
`app/engines/vector_recall.py:66` requires `REGENOLD_GRAPH_VECTOR_RECALL=1`, default OFF, so
`vector_refs` is always `[]` and fusion degenerates to BM25 + role seeds.

### [I7] Test assertion that never ran
`tests/test_hypa_rag_integration.py:79` used `c.article if hasattr(c, "article")`.
`CitationNode` has only `article_ref`, so the guard was always False and the check degraded
to substring-matching `"13"` against the whole stringified citation — it would pass on an
incidental "13" in unrelated prose. **Fix applied:** scoped to `article_ref` and replaced
with an ON-vs-OFF parity assertion.

## Suggestions

- `_ANNEX_ARABIC_TO_ROMAN` is now a **third** copy of the same dict.
- `top_articles_by_relevance` ran twice per request on zero-entity questions.
- `_DEFINITION_QUERY_RE` misses hyphens, so *"What is a high-risk AI system?"* never matches;
  `_DIRECT_ARTICLE_RE` rejects letter sub-points like `Article 13(2)(a)`.
- Class 0 is structurally unreachable for multi-turn traffic (the flattened
  "Conversation so far:" preamble blows past the `len(words) <= 10` gate).
- Aura emits `db.index.vector.queryNodes is deprecated ... replaced by SEARCH` 3x per
  question. Not breaking yet; unflagged anywhere in the repo.

## Paper fidelity

| Paper item | Code status | Verdict |
| --- | --- | --- |
| 3-class complexity classifier | regex + `is_complex_question` | adapted (no-torch rule) but **unvalidated** — no labelled set exists |
| Adaptive top-k | implemented | 3-class should be 3/5/**7**; code uses 3/5/**10** (borrowed from the 2-class table) |
| Adaptive rewrites / KG depth / keywords | dead fields | **unimplemented** |
| `kg_max_units` | dead field | **invented** — not a paper parameter |
| Hybrid sparse+dense RRF | implemented | dense arm inert; duplicate of existing RRF |
| **Reranker** | absent | the *only* ablation-positive component |
| PA-RAG (KG-free), the paper's actual winner | not built | not attempted |

The paper's own Table 2: PA-RAG beats HyPA-RAG on Faithfulness (0.9044 vs 0.8328), Answer
Relevancy, Absolute Correctness and Correctness (0.8141 vs 0.7918). §9: adding a KG
"potentially lower[s] response quality". §8.4: adding KG depth "**lowers Absolute
Correctness**". A.13 concedes the parameter mappings "were **not rigourously validated
quantitatively**".

## Knowledge-graph ground truth (corrects R323-HANDOFF)

The handoff's #1 open item — *"the vector layer is dead"* — is **stale**. R326/R327 wired it.
Verified live against Aura (`enabled is True` asserted first):

- **7 VECTOR indexes, all ONLINE, 128-dim cosine. 1490 embeddings (not 1483), 100% coverage.**
- `v_paragraph` / `v_point` / `v_subpoint` execute **on every question by default** via
  `kg_context -> _render_semantic_layers -> graph_semantic`, ~320 ms, 21,581 chars rendered.
- `v_article` / `v_annex` reachable only through `vector_recall` (default OFF);
  `v_definition` / `v_recital` gated by the gloss flag (default OFF, already A/B-negative
  at R327.1).
- Embedding parity is **not** a blocker: `graph_semantic._embed` and the seeder share
  `embeddings_index._embed_query`, which reads local `.npy` assets and is independent of
  `REGENOLD_EXTERNAL_EMBEDDINGS`. The layer works fully offline.
- Genuinely idle: `Obligation`/`HAS_OBLIGATION` (113), `CROSS_REFERENCES` (248 edges),
  `RiskLevel`/`APPLIES_AT` (47), `LegalInstrument`/`HAS_PROVENANCE` (126),
  `Guideline`/`INTERPRETS` (8).

**Medical regulations are not in the graph.** `MATCH (n) WHERE n.framework IS NOT NULL`
returns `[]` — the property does not exist. `LegalInstrument` has exactly **one** node
(the AI Act, CELEX 32024R1689). The only MDR/IVDR content is the Act's own Annex I citation
of 2017/745 and 2017/746. The new `MDR_IVDR` "cross-regulatory mapping"
(`kg_context.py:656`) is a hardcoded Python dict that performs a Neo4j round-trip and then
ignores the result, rendered under a heading reading "KNOWLEDGE-GRAPH CROSS-REGULATORY
MAPPINGS". Honest relabelling or real seeding is warranted.

## Process finding

The Gemini agents' own eval artifacts show the merge gate was never run:

- `easyhard-easyhard_hypa_eval.json` — `"baseline_env": {}, "branch_env": {}`: a single-arm
  run with no paired contrast.
- `july7-july7_hypa_fix_eval.json` — **`"stage2_landed_rate": 0.0`**: Stage-2 never fired
  once, so the feature was never measured under live conditions.
- Same file: `"vs_july7_ref_jaccard": 0.464` — 54% of references changed, shipped default-ON.

## Review metadata

- **Agents dispatched:** Logic & Correctness, Contract & Integration, Error Handling & Edge
  Cases, Concurrency & State, Security, Plan Alignment / Paper Fidelity, KG & Vector Layer.
- **Refuted during verification:** `query.entities` cache poisoning (`_deterministic_parse`
  is not memoised and the list is reassigned, not mutated); the `NEO4J_URI` always-skip test
  trap (28 new tests, 0 skipped); regex-widening reachability in `regenold.py`; Bedrock ->
  Gemini fallthrough (pre-existing R267.1 behaviour that the anthropic path shares, not new).
- **Gates:** davidath 476 in place x3 arms; per-row zero-variance attribution; full pytest;
  live pairwise `ab_judge` against the Claude Max wrapper.
