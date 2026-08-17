# Deep Code Review: full-architecture wiring audit (retrieval → graph → generation → route)

**Date:** 2026-08-17
**Scope:** app/engines/*, app/data/kb_search.py, app/routes/regenold.py, app/engines/_graph_rag_impl.py, eval judge (cross-ref)
**Method:** CR-SKILL deep-code-review adapted to a whole-architecture manifest — specialist passes (wiring/contract, logic, edge cases, architecture) over every engine module's import graph, followed by code-level verification of each finding. **Every finding below was confirmed by reading the actual code; false positives were dropped.**
**Goal:** SOTA real-world performance vs frontier 2026 models — findings ranked by leverage toward that goal, not by code churn.

---

## Executive summary

The architecture is **healthy at the seams that were already fixed** (cache keys, truncation guard, judge grounding) and **deliberately conservative at the levers that would move performance**. The verified facts:

1. At default settings the live wire is a **BM25 + KB + semantic-gloss system** — the graph stack (Neo4j 2-hop, PPR, PathRAG, vector recall) is wired but **additively-inert** (measured 4 refs added / 132 rows).
2. **Two levers with a measured or paper-grounded positive signal sit default-OFF**: query expansion (R346: ref_loose +0.039, confirmatory re-run interrupted) and the cross-encoder reranker (never measured with a cross-encoder; the paper's faithfulness champion 0.9098).
3. **One built engine is dead code with a recorded wrong verdict**: CLARA (`clara_logic.py`) — superseded by `prohibited_gatekeeper`'s verb-form emotion coverage, and re-wiring it blindly would be a regression.
4. The route handler (`regenold_eu_ai_act_ask`, 3,000+ lines) still re-implements reference shaping parallel to the engine — the earlier "extract the gated passes" work was never completed.

The path to SOTA is **measurement, not more gates**: complete the interrupted R346.2 expansion confirmatory A/B, then the reranker A/B (graded with the R360/R361 reference-free + recital-aware axes), then HyPA-on-top-of-reranker per the paper's Table 8/9 sequence.

---

## Findings (verified, by severity)

### F1 — [Lever, HIGH] Query expansion: measured positive, confirmatory re-run interrupted, default OFF

- **Where:** `app/engines/_graph_rag_impl.py:2284` — `REGENOLD_QUERY_EXPANSION` default `"0"`; consumer `app/engines/query_expansion.py`.
- **Evidence:** eval CLAUDE.md R346: ref_loose **+0.039**, kw_recall **+0.029**, gold 17→14 (branch BETTER), flat latency — "the arm to push"; **R346.2 (frontier-tier paraphrase) was interrupted before completing** ("re-run before trusting those numbers").
- **Why it matters:** this is the only lever with a *measured positive* signal that is still OFF. Every other OFF lever is OFF because it measured negative, was never measured, or is a paper-hypothesis.
- **Fix:** complete the R346.2-style confirmatory A/B via Bedrock only (`live_ab_env` forces Bedrock + embedded graph; tunnel untouched). If the frontier-tier paraphrase holds the +0.03 ref_loose with no gold regression, flip the default ON (with the R355 cache-key entry — already present? verify `REGENOLD_QUERY_EXPANSION` is in the engine key; the R355 completeness test will fail CI if not).

### F2 — [Lever, HIGH] Cross-encoder reranker: never measured, default OFF

- **Where:** `app/engines/cohere_rerank.py:241` — `REGENOLD_COHERE_RERANK` default `"0"`; wired into `_render_supplementary_sections` (engine-level) and the route cache key (`regenold.py:1266`).
- **Evidence:** R325 measured only a **lexical** reranker (AUC 0.703, "genuinely different arm" per the module's own docstring). The paper (R360/R361 review) shows the **cross-encoder** reranker is the faithfulness champion: `k,Q + reranker` = 0.9098, `HyPA + reranker` = 0.8402 correctness. This is the single most valuable unmeasured component.
- **Fix:** run `REGENOLD_COHERE_RERANK=1` vs default on the 81-row bench + no-gold half, graded with the R360 reference-free axes (`answer_faithfulness`/`answer_relevancy`, now recital-aware per R361) plus the gold-bound axes. The data-protection egress question is real but orthogonal: run on the public bench, no partner PII.

### F3 — [Wiring, MEDIUM] CLARA (`clara_logic.py`) is dead code with a recorded wrong verdict

- **Where:** `app/engines/clara_logic.py` (1,159+ lines) — **zero import sites in app/** (verified: no reference outside the module except data-file strings).
- **Evidence of why:** `docs/ROUNDS.md:6319` records the emotion-monitoring scenario returning CLARA verdict `minimal` for a prohibited practice ("monitor the emotions and stress levels of workers" → clara said `minimal`). The successor `prohibited_gatekeeper.py:58-61` now explicitly covers verb-form emotion phrasing ("verb-stem × emotional-state-noun proximity"). The current engine answers that exact scenario correctly (expert review Q19 = PASS).
- **Why it matters:** the operator asked about the "CLARA logical engine" in the first session; it is built, offered to the route ("the route can pick either path"), and never wired — the "built but inert" pattern. **Re-wiring it would be a regression** (recorded wrong verdict on a now-passing scenario).
- **Fix (applied):** mark CLARA as superseded/retired in its docstring and the steering docs' "Do not re-propose" list, so no future session re-wires it. No runtime change.

### F4 — [Architecture, MEDIUM] The graph stack is additively-inert at default settings

- **Where:** `app/data/kb_search.py:920-1035` — 2-hop (`REGENOLD_GRAPH_FUSE_SLACK` default 0 → **measured 4 refs added / 132 rows**, ~99.4% of the graph's contribution discarded at the fusion budget), PPR (`REGENOLD_GRAPH_PPR` default OFF), PathRAG (`REGENOLD_PATH_RAG` default OFF); `app/engines/_graph_rag_impl.py:6310` KB-primary retrieval (`REGENOLD_KB_PRIMARY_RETRIEVAL` ON, R252 — the graph's blunt risk-tier dump was retired); `app/engines/vector_recall.py:66` (`REGENOLD_GRAPH_VECTOR_RECALL` must equal `"1"`).
- **Why it matters:** the positioning is "graph-enhanced RAG", but at defaults the graph contributes ~nothing to the wire. This is **documented and deliberate** (BM25-saturation finding R31/R69/R110, R252, R295) — not a bug. It is the SOTA headroom: each graph lever is a real A/B candidate once the reranker/expansion wins are banked.
- **Fix:** none this round. Sequence them after F1/F2 (the freebuff review's "graph expansion layers built but effectively inert at the fusion step" finding is reproduced and confirmed).

### F5 — [Contract/Integration, MEDIUM] Route re-implements the reference pipeline

- **Where:** `app/routes/regenold.py` `regenold_eu_ai_act_ask` (lines 6419–9514, ~3,000 lines, single function to EOF): its own `_effective_max_refs` budget logic (7581–7984), `_one_per_head` (4426–4454), `_r115_rescue` (8018), curated anchors (8039), `_clamp_pair_rescue` — parallel to the engine's `_build_context_references_block` (`_graph_rag_impl.py:7341`) + R72 refs reconcile.
- **Why it matters:** the two implementations can drift (the R355 cache-key doctrine: engine flags not reflected on the route side silently change the wire). Both sides have their own tests (`test_r142_refprecision_truncation`, `test_r284_one_per_head`, `test_citation_minimisation_and_caps`) but **no cross-side contract test** asserting route output refs stay consistent with engine refs through the route's validation.
- **Fix:** add a contract test (route post-validated refs == engine refs for a fixed fixture set, modulo the documented caps/curated rescues), then extract the route's shaping into a single shared helper. Not a runtime bug today.

### F6 — [Verified healthy] Cache keys are consistent and current

- Route key (`regenold.py:1245-1330`) folds in rerank, entity boost, truncation guard, Stage-2 gates, provider; engine key passes the R355 completeness test in main (2/2). No stale-serving defect found. The R331 comment ("rerank MUST be in the key — an in-process A/B replays the other arm's cache") is the right doctrine and is honored.

### F7 — [Process] The measurement loop is the bottleneck, not the code

- The judge is now well-instrumented: R359 CRAG, R360 reference-free axes, R361 recital grounding, R349 judge axes in `dynamic_ab`, R350 Unicode + fail→pass fixes. The gated-lever pile is deliberate; the path to SOTA is the measurement sequence in F1/F2, not more gates.

---

## Applied fixes this round

1. **CLARA retirement marker** (`app/engines/clara_logic.py` docstring + steering note) — prevents a future session from re-wiring a module with a recorded wrong verdict. Zero runtime risk.

## Recommended sequence to SOTA (Bedrock-only, tunnel untouched)

1. **R346.2 confirmatory A/B** — query expansion with frontier-tier paraphrases (complete the interrupted run). If it holds: flip `REGENOLD_QUERY_EXPANSION` ON.
2. **Reranker A/B** — `REGENOLD_COHERE_RERANK=1` vs default, graded with R360/R361 axes. If positive: ON.
3. **HyPA-on-top-of-reranker** — `REGENOLD_HYPA_ADAPTIVE_ROUTER=1` + reranker (the paper's 0.8402-correctness config), per the R360/R361 sequence.
4. **Graph levers** — `REGENOLD_GRAPH_FUSE_SLACK` (2-hop), then PPR/PathRAG/vector-recall, each A/B'd after the retrieval wins are banked.

Each flip is default-OFF until its A/B nets positive — the R329 lesson, applied.
