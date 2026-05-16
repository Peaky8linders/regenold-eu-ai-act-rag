# R38–R39 Graph RAG + Sub-point Surgical Strike — Design

**Date:** 2026-05-17
**Status:** Approved (Approach B picked over A / C)
**Target windows:** R38 = competition submission (May–June 2026); R39 = live-benchmark phase (post-June 2026)
**Baseline:** R37 — `Ans Strict 0.305, Ref Loose 0.549, Ref Strict 0.436, Tone 1.0, multi-turn 1.0, p50 ≈ 7 ms`

## Goal

Win the regenold 2026 EU AI Act Q&A competition (3-axis Ans correctness, 3-axis Ref correctness, conciseness, tone, latency, multi-turn) AND set up well for the live-benchmark phase regenold plans after the contest. Strategy: ship the highest-leverage rubric wins as **R38** (Phase 1, week 1) so they are in the submission, then upgrade the retrieval architecture as **R39** (Phase 2, weeks 2–3) for the live-benchmark phase.

## Research foundations

Three parallel research agents produced consolidated findings (full reports archived in this session's transcript; high-points summarized here).

### Hidden gold likely uses sub-point references

The regenold rules PDF's 3 example questions (`tech doc hardware`, `emotion recognition prohibited?`, `doctor-patient transcription`) all map naturally to sub-point references — `Article 5(1)(f)`, `Annex IV(2)(a–f)`, `Annex III(5)`. Our pipeline emits base articles for most topics; we lose Ref-Strict score whenever gold has sub-points. davidath's open gold is article-level only, so the loose-match metric won't regress when we emit sub-points.

**Expected lift:** +0.04 – 0.06 Ref Strict — the single largest measurable rubric win available.

### We're at the public-measurement frontier

No public competitor publishes Q&A-shaped numbers against a Regenold-style 8-axis rubric. Closest peers:

- Harvey AI: 89.6% Doc-QA on Vals VLAIR (no conciseness measured)
- Gemini 2.5 Pro on AIReg-Bench: κ=0.863, 60% exact-match (5 articles only, non-Q&A shape)
- LegalBench-RAG: character-level retrieval (not generation-aware)

R37's `Ans Strict 0.305 / Ref Loose 0.549` is at the frontier of public measurements on rubrics of this shape. Competition is effectively us vs zero-shot Mistral / OpenAI / Anthropic submissions.

### 4 Tier-1 2026 regulatory updates missing from our KB

| Update | Status | Article | Risk |
|---|---|---|---|
| Nudification / CSAM prohibition | Political agreement 2026-05-07 (Digital Omnibus); applies 2026-12-02 | Art. 5 new lit. | HIGH |
| Art. 50(2) watermarking grace | Deferred 2026-08-02 → 2026-12-02 | Art. 50 | HIGH |
| GPAI Code of Practice + signatories | Published 2025-07-10 | Art. 56 | MED |
| Training-data summary template | Adopted 2025-07-24 | Art. 53(1)(d) | MED |

The davidath bench is pre-Omnibus, so dual-vintage hedge phrasing in KB stubs ("The base regulation set X; the May 2026 Digital Omnibus agreement defers this to Y") wins on post-Omnibus golds without regressing pre-Omnibus.

### Phase 2 architectural upgrades are bench-neutral on davidath but pay off on hidden bench

HippoRAG 2 (PPR over KG), PathRAG (relational-path pruning), GraphCompliance (policy+context alignment) all have strong 2025–26 evidence. **But** davidath is BM25-saturated (per R31 finding) — these gains can't show on the open bench. Phase 2 is **insurance** for hidden-bench paraphrases and the live-benchmark phase.

## Architecture

```
                  POST /api/v1/regenold/eu-ai-act/ask
                                 │
                  scope.classify_conversation (unchanged)
                                 │
              intent_classifier + task_router + question_type_classifier
                                 │  → drives template + budget
                ★ B8 ★ RAG-Fusion query expansion (Haiku 4.5, R39)
                                 │  → 3 paraphrases, RRF fusion
                ★ B6+B7 ★ HippoRAG PPR → PathRAG prune (R39)
                                 │  → additive over existing dense/turboquant paths
                ask_compliance_question (engine, unchanged contract)
                                 │
                ★ A1 ★ subpoint_emitter — base→leaf ref upgrade
                                 │
                ★ A2+A3 ★ per-intent template + ref-budget normaliser
                                 │
                ★ A4 ★ tone enforcer
                                 │
                RegenoldAskResponse
```

Every new layer is env-gated (`REGENOLD_*` flags) and falls through cleanly to current behaviour when off. Zero-regression rollback path.

## Phased rollout

### Phase 1 (R38, week 1) — Surgical Strike

Visible-rubric wins. Ships as the competition submission.

- **A1 — Sub-point ref emission.** New `app/data/subpoint_emitter.py` with 31-entry topic → leaf-subpoint mapping (`Art. 5(1)(a–h)`, `Annex III(1–8)`, `Annex IV(1–9)`, others). Rewires `_collapse_parent_refs` to prefer sub-points when topic matches; emits BOTH base + sub-point as two refs when topic match is ambiguous (loose-bench safety net).
- **A2 — Per-intent answer-length templates.** New `app/engines/answer_template.py`. Per (`question_type` × Davvetas task) skeleton: definitional 1S/120c, classification 2S/260c, scenario 3S/500c, refusal 1S. Placeholder tokens `[CITE_PRIMARY]`, `[CITE_SECONDARY]` substituted after retrieval. Wires into post-engine pipeline in `routes/regenold.py`.
- **A3 — Per-intent ref-budget.** Extend R31.1's scenario-only 10-cap to QA-shape: definitional=2, classification=3, scenario=8, refusal=0. Cap applied AFTER smallest-cover pass.
- **A4 — Tone enforcement guard.** New `app/integrations/regenold/tone_guard.py`. Regex-strip hedge openers ("I think", "It seems", "Based on", "As an AI", "Please note that"); force imperative/declarative. Skip if answer already opens with `(Article` / `Annex` / `This system`.
- **A5 — Tier-1 2026 KB updates.** Modify `app/data/kb.py` with stubs for: Art. 5 new lit (nudification/CSAM), updated Art. 50 (dual watermarking deadline), Art. 56 (Code of Practice + signatory list), Art. 53(1)(d) (training-data summary template). Modify `app/data/role_obligations.py` to set numeric SMC thresholds (750 employees / €150 M turnover).

### Phase 2 (R39, weeks 2–3) — Architectural Upgrade

Retrieval-architecture gains + eval coverage. Ships after R38 lands.

- **B6 — HippoRAG 2 PPR over Neo4j.** New `app/engines/graph_ppr.py`. Personalized PageRank via Neo4j GDS `gds.pageRank.stream` with `sourceNodes` seeded from BM25 top-K. Replaces R28's ad-hoc in-degree log boost. Additive — never displaces a BM25 winner. Env-gated `REGENOLD_GRAPH_PPR=1`.
- **B7 — PathRAG relational-path pruning.** New `app/engines/path_rag.py`. Walks `CROSS_REFERENCES` paths between query-anchored entities; prunes redundant overlapping paths via Jaccard similarity on edge sets. Targets R31.1's ref-conciseness regression (over-citation cost). Env-gated `REGENOLD_PATH_RAG=1`.
- **B8 — RAG-Fusion + RRF.** New `app/engines/query_expansion.py`. Haiku 4.5 generates 3 query paraphrases (LRU-cached on question hash); BM25 + embeddings + KG run on all 4 queries; reciprocal rank fusion. Reuses existing `intent_classifier` circuit-breaker. Env-gated `REGENOLD_QUERY_EXPAND=1`.
- **B9 — Davvetas per-task scoring harness.** New `evals/bench/davvetas_per_task.py`. Aligns our R31 task router with the canonical arXiv 2603.09435 §4 metric taxonomy (risk-level / article-retrieval / obligation-generation / QA). Unlocks per-task reporting.
- **B10 — mtRAG multi-turn bench.** New `evals/bench/mtrag.py`. 110 conversations, 842 tasks (TACL). Reveals headroom past the locked 1.0 on our 20-scenario probe.

## Components — module-by-module

### New modules

| Module | Phase | Purpose | LOC est. | Risk |
|---|---|---|---|---|
| `app/data/subpoint_emitter.py` | 1 | 31-entry topic→leaf-subpoint map; emit base+sub-point as 2 refs when ambiguous | 250 | low |
| `app/engines/answer_template.py` | 1 | Per-(question_type × Davvetas task) skeletons with placeholder substitution | 300 | low |
| `app/integrations/regenold/tone_guard.py` | 1 | Hedge-strip regex + leading-verb / cite-anchor check | 150 | low |
| `app/engines/query_expansion.py` | 2 | Haiku-driven 3-paraphrase expansion; LRU+breaker | 200 | med |
| `app/engines/graph_ppr.py` | 2 | Neo4j GDS PPR wrapper; cap to top-N; env-gate | 250 | med |
| `app/engines/path_rag.py` | 2 | Relational-path retrieval + Jaccard prune; 50-ms timeout | 350 | med |
| `evals/bench/aireg_bench.py` | 2 | Cambridge MLSys AIReg-Bench loader + scorer | 200 | low |
| `evals/bench/mtrag.py` | 2 | TACL multi-turn bench loader + scorer | 200 | low |
| `evals/bench/davvetas_per_task.py` | 2 | Per-task scoring per arXiv 2603.09435 §4 | 150 | low |

### Modified modules

| Module | Phase | Changes |
|---|---|---|
| `app/data/kb.py` | 1 | Add stubs: Art. 5 new lit, updated Art. 50 (dual deadlines), Art. 56 (Code), Art. 53(1)(d) (template) |
| `app/data/role_obligations.py` | 1 | Numeric thresholds on `ROLE_SMALL_MID_CAP` (750 emp / €150 M turnover) |
| `app/routes/regenold.py` | 1 | Wire `subpoint_emitter`, `answer_template`, `tone_guard` into post-engine pipeline; add 6 env flags |
| `app/data/kb_search.py` | 2 | Fuse PPR scores into additive-dense path when `REGENOLD_GRAPH_PPR=1` |
| `app/llm/intent_classifier.py` | 1 | Adopt `sentence_index.classify_question` as fast-path before Haiku call |
| `railway.toml` | 1+2 | Default new flags to safe values |

## Data flow

**Phase 1 — successful path:**

1. Scope gate (unchanged) → in-scope
2. Intent classifier + `sentence_index.classify_question` → `(intent_label, question_type)` (e.g., `(definition, DEFINITION)`)
3. Engine runs (unchanged contract) → returns `candidates`, `answer_text`
4. **A1** Iterate candidates; for each ref, look up topic via `_KEYWORD_ENTITY_MAP`; if topic in `SUBPOINT_TOPIC_MAP`, emit `(base_ref, leaf_subpoint_ref)` pair instead of just `base_ref`
5. **A3** Slice `candidates` to `INTENT_REF_BUDGET[question_type]` (definitional=2, classification=3, scenario=8, refusal=0). Applied after R16 smallest-cover pass.
6. **A2** If `answer_text` length > `INTENT_LENGTH_CAP[question_type]`, run extractive trim and substitute into skeleton template; skeleton anchors first sentence on `[CITE_PRIMARY]` if available.
7. **A4** Tone guard: regex-strip hedge openers; ensure leading verb / `Article N` token; skip if already cite-anchored.
8. Build `RegenoldAskResponse(answer=..., references=..., reasoning=...)`.

**Phase 2 — successful path** (additions only):

- Between steps 2 and 3: `query_expansion.expand(question, intent_label)` → returns `(original, p1, p2, p3)`. Each query runs through BM25 + embeddings independently; RRF fuses ranks. Cache key includes intent_label.
- Inside step 3 (engine retrieval): PPR + PathRAG candidates ADDITIVELY merged into BM25/embedding pool. Never displaces a BM25 winner.

## Error handling — fail-soft everywhere

| Failure | Fallback | Latency cost |
|---|---|---|
| Subpoint emitter — unknown topic | Emit base article only (no regression) | 0 ms |
| Template substitution — placeholder mismatch | Fall through to existing `normalise_answer_for_regenold` | 0 ms |
| Tone guard — regex error | Return original `answer_text` | 0 ms |
| RAG-Fusion — Haiku call fails / circuit open | Use original query only | 0 ms (instant skip) |
| RAG-Fusion — Haiku >2s budget exceeded | Cancel, use original query | 2 s ceiling |
| PPR — Neo4j GDS plugin absent | Fall back to existing 2-hop expand | 0 ms (env detect) |
| PPR — Neo4j unreachable | `degraded=True` in `GraphContext` (R37 fix), KB fallback | 50 ms ceiling |
| PathRAG — path query timeout | Use BM25 + embedding candidates only | 50 ms ceiling |
| Bench harness — dataset SHA mismatch | Refuse to run; print clear error; current bench results preserved | n/a |

Same env-gate + circuit-breaker discipline as R32/R35. The deterministic pipeline always lands an answer.

## Testing

### Per-module unit tests (TDD)

Each new module gets a dedicated test file (`tests/test_subpoint_emitter.py`, `tests/test_answer_template.py`, `tests/test_tone_guard.py`, `tests/test_query_expansion.py`, `tests/test_graph_ppr.py`, `tests/test_path_rag.py`). Failing test first; ~15 tests per module.

Modified modules extend their existing test files (`tests/test_kb_consistency.py`, `tests/test_kb_stubs_filled.py`, `tests/test_role_obligations.py`, `tests/test_route_round_36_fixes.py`, `tests/test_intent_classifier.py`).

### Integration tests

`tests/test_r38_integration.py` (Phase 1) and `tests/test_r39_integration.py` (Phase 2): end-to-end through `TestClient` with each env flag combination. Verifies:

- All flags OFF → identical to R37 baseline.
- Each flag ON independently → expected per-axis lift on a 10-question probe set.
- All flags ON → full pipeline coherent (no double-trim, no double-emit).

### Bench gating

Every module must hold or improve every rubric axis on davidath:

- Phase 1 ship gate: `Ans Strict ≥ 0.305`, `Ref Loose ≥ 0.549`, `Ref Strict ≥ 0.436`, `Tone = 1.0`, multi-turn = 1.0, `latency p50 ≤ 10 ms`. Predicted post-Phase-1: `Ans Strict ≈ 0.32, Ref Loose ≈ 0.57, Ref Strict ≈ 0.49, Ans Conciseness +0.04`.
- Phase 2 ship gate: `Ans Strict ≥ Phase-1`, `Ref Loose ≥ Phase-1`, `Ref Strict ≥ Phase-1`, latency p50 ≤ 15 ms. Phase 2 is mostly bench-neutral on davidath; the gate is no-regression, not lift.

### New bench harnesses

AIReg-Bench, mtRAG, Davvetas per-task each run in CI parity with davidath. New result-comparison helper in `evals/bench/compare.py`.

## Rollout sequence

1. Land all Phase-1 modules with ALL flags `=0`. Bench reproduces R37 exactly → zero-regression confirmation. Commit, push, PR, merge.
2. Flip `REGENOLD_SUBPOINT_EMIT=1` in `railway.toml`, bench. Expect Ref Strict +0.04–0.06. Hold or roll back.
3. Flip `REGENOLD_ANSWER_TEMPLATE=1`, bench. Expect Ans Conciseness +0.04.
4. Flip `REGENOLD_TONE_GUARD=1`, bench. Expect Tone hold at 1.0; Ans Strict +~0.005 (lead-token recall).
5. Flip `REGENOLD_REFBUDGET_PER_INTENT=1`, bench. Expect Ref Conciseness +0.02.
6. Tier-1 KB updates already landed; bench. Expect rubric-neutral on davidath, +recall on post-Omnibus golds.
7. Submit R38 to regenold.
8. After submission: land Phase-2 modules with ALL Phase-2 flags `=0`. Bench R37+Phase-1 parity.
9. Flip Phase-2 flags one at a time per same discipline. Some flips will be bench-neutral on davidath — that's expected.
10. Release R39 for the live-benchmark phase.

Every flip is a separate commit + bench run. Never two flips at once. Watch `/healthz/llm` + `/healthz/graph` after each Railway env-var change.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sub-point emission over-narrows (gold expects base, we emit leaf) | Med | Ref Strict +0.02 → -0.02 | Emit BOTH base + sub-point as 2 refs when topic match is ambiguous; Ref Conciseness budget caps at 3 so we don't bloat. Loose-bench safety net intact. |
| Per-intent template under-cites scenarios | Low | Ref Loose / Strict -0.01 | Scenarios use R31.1 dynamic 10-ref budget; template adjusts length cap only, not ref count |
| RAG-Fusion Haiku call adds 0.5–2 s p50 | Med | Latency +500 ms p50 | Strict 2-s budget per fan-out call; cache by question hash; opt-in env flag; circuit-breaker on 3 failures in 60s |
| PPR / PathRAG bench-neutral on davidath | High (expected) | No headline metric move | Phase 2 is insurance, not headline. Document in CLAUDE.md alongside R31 finding |
| Tier-1 KB updates contradict pre-Omnibus gold | Low | Ans / Ref Strict -0.01 | Dual-vintage hedge phrasing ("The base regulation set X; the May 2026 Digital Omnibus agreement defers to Y") |
| Tone guard strips a legitimate sentence opener | Low | Ans Strict -0.005 | Whitelist exact-match openers: `This system`, `The provider`, `Article`, `Annex`, `Under` |
| GDS plugin absent on production Neo4j | High | PPR fallback to 2-hop | Env-detect at startup; log + skip; same `/healthz/graph` surface |
| Railway env-var typo on flip | Med | Live regression | Flip one flag at a time; canary on staging first if available; quick rollback via Railway dashboard |

## Out of scope

- HyDE on coref-rescue (Approach C)
- ColBERT v2 / Jina-ColBERT-v2 late-interaction rerank (Approach C — bench-test in R40 if BM25 still saturated)
- GraphCompliance policy/context-graph alignment (Approach C — heavy refactor of `scenario_classifier`)
- Tier-2 / Tier-3 2026 KB updates (Art. 5 prohibited-practices Guidelines, MDCG 2025-6, PLD 2024/2853, CJEU pending refs)
- Microsoft GraphRAG community detection (wrong shape for single-article QA per Phase-1 finding)
- Speculative decoding (no Anthropic API surface)
- ICR clarification turns (wire is one-shot)

These are R40+ candidates after the live-benchmark phase reveals what the hidden gold actually rewards.

## Source citations

Selected sources from the three parallel research reports (full URLs in session transcript):

- Research foundation A: davidath/ai-act-evaluation-benchmark dataset (HuggingFace + arXiv 2603.09435)
- Research foundation B: HippoRAG 2 — arXiv 2502.14802; PathRAG — arXiv 2502.14902; LegalGraphRAG / GraphCompliance — arXiv 2510.26309
- Research foundation C: Vals VLAIR (Harvey 89.6%); AIReg-Bench — arXiv 2510.01474; LegalBench-RAG — arXiv 2408.10343
- Digital Omnibus political agreement: Council & Parliament press release 7 May 2026; Latham & Watkins, William Fry, Hogan Lovells, Taylor Wessing memos
- GPAI Code of Practice: code-of-practice.ai; Commission press release 10 July 2025
- GPAI Guidelines: Commission release 18 July 2025
- Training-data summary template: Commission release 24 July 2025
