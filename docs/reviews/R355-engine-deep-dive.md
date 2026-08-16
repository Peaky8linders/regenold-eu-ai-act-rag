# R355 — Neuro-Symbolic Engine & CLARA deep dive (main repo)

**Date:** 2026-08-16 · **Scope:** `D:/Claude Projects/regenold-eu-ai-act-rag`
**Methods:** call-site analysis, git archaeology, cache-key completeness scan, test-suite verification, market research (Microsoft GraphRAG/LazyGraphRAG, neuro-symbolic clinical/legal literature). Cross-checked against the existing R290 review and the 2026-08-13 deep code review so this report adds only new findings.

---

## 1. What the graph_rag "split" actually is

`f08fbd3 refactor(graph_rag): modularize graph_rag sub-package and MedTech risk architecture` renamed `app/engines/graph_rag.py` → `app/engines/_graph_rag_impl.py` (99% similarity — a pure rename) and added a thin `app/engines/graph_rag/` package (`__init__.py` `_GraphRAGModule` proxy + `parser/deterministic.py`, `parser/llm_parser.py`, `risk_engine/annex_iii.py`, `risk_engine/exemptions.py`, `generators/citation_verifier.py`, `pipeline.py`, `retrieval/context_seeder.py`, `config.py`, `models.py`).

**The split is a compatibility shim, not a modularization.** Independent evidence from this session:

- **Zero call-sites:** none of the split modules (except `models.py`) is imported or invoked from `_graph_rag_impl.py`, the route, or any other live path. The engine still calls the monolith's `_deterministic_parse`, `_detect_prohibited_practices_inquiry`, etc.
- **The split modules delegate back to the monolith:** `graph_rag/parser/deterministic.py` imports `_graph_rag_impl._deterministic_parse` — the package's own code acknowledges the monolith is the source of truth.
- **`config.py` is a shadow flag registry:** `REGENOLD_GRAPH_RAG_V2` (default `"1"`, `graph_rag/config.py:58`) is consumed **only** by the dead package — it has zero effect on the live engine. This matches R290 finding #11/#34: config.py invents env names that exist nowhere and contradicts the live engine on 3 of 7 knobs.

**This was already documented.** `docs/reviews/R290-gemini-graphrag-refactor-review.md` (2026-07-24, 60 agents / 6 lanes, 44 confirmed findings) reached the same conclusion with `sys.settrace` over 8 live `/ask` requests: *"every file under app/engines/graph_rag/ executes exactly 1x at IMPORT time and zero new functions run on a request. Only models.py is genuinely wired"* (`_graph_rag_impl.py:1125`). R290 also caught what the rename had silently shipped: **2 wrong live legal citations** (Art. 6(3) registration duty cited `Article 71(2)` instead of `Article 49(2)`; Art. 18 retention cited `Article 48` instead of `Article 47` — both reverted in `17b16d1`).

**Why it matters (beyond "dead code"):**
1. The package is a **second source of truth** that drifts (R290: `deterministic_parse` is a gutted 92-line copy returning 0 entities where the live parser returns correct anchors).
2. A maintainer reading the pretty split will fix bugs there, and the wire will not change — the R256/R286/R290 "silently inert port" trap, recurring a third time.
3. `pkg.config` shadows the `config` submodule; the proxy's attribute surface is import-order-dependent (266 vs 81 names); `mock.patch` teardown permanently poisons `_impl`; a failure in any unreachable sub-module hard-kills `/ask` and app boot (R290 #5/#7/#8/#30/#40).

---

## 2. Neuro-Symbolic Engine — real-world implementation check

**What it actually is (verified from code):** a deliberately hybrid engine:
- **Deterministic first:** `_deterministic_parse` extracts article/anchor entities with regex + role anchors; the parser carries documented hard rules (verbatim statutory text, Art. 3 rescue, MedTech routing).
- **KB-primary, Neo4j additive-only:** the engine deliberately routes knowledge-base retrieval first and treats the Neo4j graph as additive context, not the source of truth. This is a documented, hard-won lesson in the code comments.
- **Gated Stage-2 synthesis** (`P2P_GRAPH_RAG_ENABLE_STAGE2`): deterministic Stage-1 answer is polished by an LLM only when gated flags say so; confidence-scored; cache-poisoning guards on failure shapes.
- **Supporting retrievers:** `cohere_rerank`, `hybrid_rrf_retriever`, `vector_rerank`, `kg_context`, `graph_ppr`, `semantic_layer`, `query_complexity_router`, `turboquant_index`.
- **It works:** engine suite green (160 tests this session; 80 CLARA tests green; R290's settrace confirmed live execution).

**Real-world alignment (market research):**
- **Microsoft's GraphRAG lineage validates KB-primary over eager graphs.** The industry's headline lesson of 2024–2025 is the *cost cliff*: indexing one dataset for GraphRAG v1 cost ~$33,000; LazyGraphRAG cut indexing to ~$33 by deferring graph construction/summarization to query time. Eager, exhaustive knowledge-graph construction is the anti-pattern that burned production GraphRAG deployments. Regenold's "KB-first, Neo4j additive-only" is exactly the query-time-deferral philosophy — aligned with the current best practice, not an accident.
- **Clinical neuro-symbolic literature validates CLARA.** The 2025 review of neuro-symbolic LLM integration in medicine (NIH) describes the winning pattern as *"pair LLMs with explicit rules, ontologies, or knowledge graphs to constrain outputs"* — i.e., the LLM proposes, the deterministic layer decides. CLARA is precisely this: LLM tag extraction → deterministic verdict computation.
- **Determinism is the selling point.** Neuro-symbolic production systems advertise *"the same answer to the same question, every time"* — the property the deterministic parse + CLARA verdict provide where pure LLM RAG cannot.

**Real-world gaps found (this session):**
- **The dead split package is the one thing that does NOT match real-world practice** — a production neuro-symbolic engine should have one parser, one flag source, one confidence function. `compute_confidence` is duplicated verbatim (R290 #25); config contradicts the engine (R290 #11/#41). This is a hygiene debt, not a correctness bug (the monolith is still authoritative).
- **Flag sprawl (273 `REGENOLD_*`/`P2P_*` names codebase-wide, 205 read in `regenold.py`)** is the engine's most unusual production characteristic. No reference system carries this; it is the root cause of the cache-key risk in §5.

---

## 3. CLARA logical engine

**Architecture (verified):** `app/engines/clara_logic.py` (and route wiring) implements a neuro-symbolic decision tree: LLM tag extraction (e.g., risk-shape tags) → deterministic tree traversal → verdict + confidence; failure handling via `REGENOLD_CLARA_FAILURE_THRESHOLD`/`REGENOLD_CLARA_FAILURE_WINDOW` (circuit-breaker shape).

**Wiring verdict: correct.** CLARA is invoked **route-side** (`REGENOLD_CLARA_VERDICT`), i.e., it re-runs on every cache hit and is deliberately **excluded** from `_engine_cache_key` — the key's own docstring documents this (route post-processing re-runs on cache hit, so flipping a CLARA flag cannot serve a stale answer). This is the right design and nothing needs fixing here. The CLARA flags in the "missing from cache key" scan are *correctly absent*.

**Assessment:** genuinely well-built — deterministic, testable (80 tests green), cheap at request time, and it covers exactly the classification shapes where the grader cares about exactness. It is the strongest part of the neuro-symbolic architecture.

---

## 4. Why the improvements weren't ported here

The evaluation repo (`antifragileai-regenold-evaluation`, this worktree) carries the R328→R354 engine work that **main does not have**:

| module | main | eval repo |
|---|---|---|
| `cohere_rerank.py` | 322 lines (older) | 772 lines |
| `graph_semantic.py` | 466 lines (older) | 651 lines |
| `vector_recall.py` | 238 | 217 (refactored differently) |
| `neo4j_semantic_graph.py` | **missing** | 492 lines |
| `risk_classification.py` | **missing** | 116 lines |
| `query_expansion.py` | **missing** | 380 lines |
| `_graph_rag_impl.py` | baseline | +1,052 lines (R350/R352/R354: Fix A prose-consistency, reranker wiring, query expansion, KG candidates) |

Plus the eval repo carries the whole R350-R354 measured machinery: judge sidecars, the `dynamic_ab` harness, the R354 deterministic prose-consistency pass (merged default-ON), and the R352 annex-anchor measurement.

**Root cause:** the split (`f08fbd3`) landed on main **before** the eval work diverged (the eval lineage continued from the pre-rename `graph_rag.py`). Main froze at the renamed monolith; the eval repo kept evolving its own copy of the engine with A/B-validated improvements, and **no porting mechanism exists** — nothing mechanically links the two engine trees. The result: main's engine is the *older* implementation wrapped in a dead package, while the newer one lives only in the eval repo.

---

## 5. regenold.py — simplification & optimization findings

### 5a. NEW: cache-key completeness gap (engine-read flags missing from `_engine_cache_key`)

`_engine_cache_key` (regenold.py:1207–1831, **625 lines**, 153 flag literals) exists precisely to hash every input that flips the cached `GraphRAGResponse` (R30/R56/R79 doctrine; R331 note: *"Omitted from the key, an in-process A/B has arm B replay arm A's cache and every axis reads exactly +0.0000 — which is also what a genuinely inert lever looks like, so the run is unfalsifiable"*).

Empirical scan (all `REGENOLD_*`/`P2P_*` reads in `app/engines/**` vs key literals) found **36 engine-read flags absent from the key**. Triaged:

**HIGH — flips answer + citations, live in ask path, unkeyed:**
- `REGENOLD_GRAPH_EXPANSION` — `_graph_rag_impl.py:5858`; its own comment states it *"appends provision text into the Stage-2 grounding context, i.e. it can move the answer and the citations"*. Reads `euairagtest/provisions.json` (3.8 MB) and builds a TF-IDF index. **The single most clear-cut violation of the key doctrine in the codebase.**

**MEDIUM-HIGH — live in ask path, unkeyed:**
- `REGENOLD_CROSS_REF_CONTEXT` — `semantic_layer.py:89/330`, imported into the ask path at `_graph_rag_impl.py:7481`; default ON; injects context into generation.
- `REGENOLD_VECTOR_RERANK` — `vector_rerank.py:66`; a rerank stage (exactly the R331 class of flag).
- `REGENOLD_QA_LEAD_RANK` — `_graph_rag_impl.py:4684`; gates obligation lead-ranking at :4703, flips answer assembly.
- `REGENOLD_COMPLEX_SENTENCE_CAP` — `_graph_rag_impl.py:7871`; caps answer sentences on the complex path.
- `REGENOLD_FUSION_MIN_CANDIDATES` — `fusion.py:233`; gates the MoA fusion panel (live at `_graph_rag_impl.py:7818-7892`).

**MEDIUM (triage each):** `REGENOLD_TREE_EXTRACT`, `REGENOLD_VERBATIM_MAX_CHARS/PROVISIONS/PARA_CHARS`, `REGENOLD_ROLE_DUTY_*`, `REGENOLD_PPR_*`, `REGENOLD_KG_MAX_INFLIGHT`, `REGENOLD_EXTERNAL_EMBEDDINGS`, `REGENOLD_PROVENANCE_IN_PROMPT`, `REGENOLD_STRIP_PREAMBLE`, `REGENOLD_SEMANTIC_GLOSS_FANOUT`, `REGENOLD_DEFINITIONAL/CURATED_STAGE2_SKIP`, `REGENOLD_FRAMES_REWRITER_ALLOW_WRAPPER`, `REGENOLD_LOGIC_RAG_SAMPLE_RATE`.

**Correctly absent (NOT bugs):** `REGENOLD_CLARA_*` (route-side, re-runs on cache hit — by design), `P2P_GRAPH_RAG_API_KEY` (credential), `REGENOLD_NLI_API` (endpoint URL), `REGENOLD_GRAPH_RAG_V2` (dead — only consumed by the dead split package).

**This class is a live, known issue:** the 2026-08-13 deep code review found the same shape (Bedrock model flags `REGENOLD_BEDROCK_MODEL` etc. + `REGENOLD_STAGE2_VERDICT_GUARD` missing from the key). This scan extends it to engine-side flags the Aug-13 review did not cover. **Systemic fix:** a single typed flag-registry module + a generated key + a test asserting key completeness would have caught all 36 today and prevents the class permanently.

### 5b. Reference-pipeline duplication

The route re-implements reference shaping (2–3 ref passes, budget clamps) that partially duplicates what the engine already does in `_render_supplementary_sections`/`kg_context`. The engine builds the `GraphRAGResponse`; the route re-derives the wire references from prose. This split is intentional (R313: wire refs derive from verified prose) but the two-stage ownership makes every ref change touch both sides — the R354 Fix A work (deterministic prose-consistency) had to thread a citable-bases guard through both precisely because of this.

### 5c. The 3,097-line handler

`regenold_eu_ai_act_ask` is a sequential pipeline of ~40 gated passes. It is *not* badly written (each pass is documented, gated, traced) — the problem is **size and flag density**, which is the cost of the A/B-driven development process. Simplification is possible but the highest-value moves are the flag-registry + key-completeness test (§5a) and killing the dead package (§1), not re-slicing the handler.

---

## 6. Prioritized recommendations

| # | Priority | Action | Effort | Why |
|---|---|---|---|---|
| 1 | **P0** | Add the output-flipping flags (`REGENOLD_GRAPH_EXPANSION`, `CROSS_REF_CONTEXT`, `VECTOR_RERANK`, `QA_LEAD_RANK`, `COMPLEX_SENTENCE_CAP`, `FUSION_MIN_CANDIDATES`, + MEDIUM set after triage) to `_engine_cache_key` | Small | Stale-cache / unfalsifiable-A/B risk, documented doctrine violation, silent today |
| 2 | **P0** | Flag-registry module + generated cache key + completeness test (fail CI on any engine-read flag missing from key) | Medium | Eliminates the whole class; would have caught Aug-13 I1 + all 36 above |
| 3 | **P1** | Delete the dead `app/engines/graph_rag/` sub-package (keep `models.py` wired location) and its 18 tests that certify dead code | Medium | Removes second source of truth, boot-failure surface, R256/R286/R290 trap — recurs for the third time |
| 4 | **P1** | Port the eval-repo engine modules: `query_expansion.py`, `neo4j_semantic_graph.py`, `risk_classification.py`, updated `cohere_rerank` (772) and `graph_semantic` (651) — A/B-validated against the eval bench before merging | Large | Main's engine is measurably behind its own eval lineage; R352/R354 gains (gold-veto −12, annex anchors) never reached production |
| 5 | **P2** | Extract the ~40 gated passes from the 3,097-line handler into a pipeline module in the engine | Large | Size/flag density is the maintenance cost driver |

**Non-findings (deliberately NOT flagged):** CLARA's route-side wiring and unkeyed CLARA flags (correct by design); KB-primary/Neo4j-additive retrieval (aligned with LazyGraphRAG best practice); the deterministic-first parse (aligned with neuro-symbolic production practice).

---

*Verification basis: 160 engine tests + 80 CLARA tests green; call-site greps across app/engines and app/routes; cache-key literal scan vs engine reads (36 unkeyed); git archaeology (f08fbd3 split, 17b16d1 R290 fixes, eval-repo divergence at PR #327); market sources: Microsoft LazyGraphRAG cost-cliff research, NIH neuro-symbolic clinical review, arXiv 2508.05311.*
