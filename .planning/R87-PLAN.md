# R87 — Live-failure root-cause analysis + ranked improvement plan

**Source data**: [`evals/bench/results/representative-100-r86-live-postship.json`](../evals/bench/results/representative-100-r86-live-postship.json) — 100 rows, live Railway, Stage-2 polish ON via Cloudflare → Claude Max wrapper, reasoning trace on every row.

**Baseline comparison**: representative-100-r81-h-live.json (prior round).

| Axis | R81-H-live | r86-live-postship | Δ |
| ---- | ---------: | ----------------: | -- |
| Ans Strict | 0.2681 | **0.2874** | +0.019 ✓ |
| Ans Loose | 0.1258 | 0.1332 | +0.007 ✓ |
| Ref Loose | 0.6150 | 0.6102 | −0.005 (noise) |
| Ref Strict | 0.5729 | 0.5680 | −0.005 (noise) |
| Tone | 1.0 | **1.0** | flat ✓ |
| Latency p50 | 18.2 s | **14.9 s** | **−18%** ✓ |

R86 delivered the headline wins (Ans Strict + latency) but **multi-turn Ref Loose dropped 0.395 → 0.371** and deployer_obligation Ref Loose stayed flat at 0.466. This plan addresses the live regressions + the structural gaps the reasoning trace exposed.

## Distribution snapshot (n=100)

| Surface | Distribution |
| ------- | ------------ |
| Scope verdict | 100/100 in_scope (refusal axis not exercised in this sample) |
| Retrieval path | 60 neo4j · 30 consistency_guard · 8 deterministic · 2 zero_retrieval_fallback |
| Stage-2 polish | 53 ON / 47 OFF |
| Engine confidence | 0.7=40 · 0.5=20 · 0.3=38 · 0.0=2 |
| Pred-ref count | **bimodal**: 1-3 refs (41 rows, QA tight cap) / 8-10 refs (58 rows, scenario+MT cap) |
| Multi-turn pred-refs | **9 or 10, zero variance** across all 20 rows |
| Deployer-hop firing rate | **0 of 5 eligible rows** — never fired in live |
| Cache hits | 0 (post-R78.1 hotfix; healthy) |

The bimodal pred-ref distribution is the single most actionable signal. Gold cardinality on multi-turn HRAIS scenarios ranges **2 to 35 refs**; we ship 9-10 across the board.

## Per-row evidence — the 5 most diagnostic failures

| Row | Q (excerpt) | Gold | Pred | Pattern |
| --- | ----------- | ---- | ---- | ------- |
| `qa_028` | "When must deployers conduct a FRIA?" | `Article 27` (1) | `Article 27.1` (1) | **P3** Sub-point format mismatch — actually correct, scored 0 |
| `qa_078` | "When must deployers inform the provider of a serious incident?" | `Article 26` (1) | `Article 73.1` (1) | **P5** Wrong-Article — "serious incident" anchor stole the slot from the deployer-side duty (Art. 26.5) |
| `qa_101` | "When must deployers inform workers about a high-risk AI system?" | `Article 26` (1) | `Article 6` (1) | **P5** Wrong-Article — high-risk shadow re-emerged (R77 I2 didn't catch this phrasing) |
| `mt_031` | "[Turn 1] We are a provider … utility planning … risk classification + obligations? [Turn 2] Which Articles?" | 28 HRAIS Section-2 refs | 9 refs (Art. 4/6/50/51/52/90) | **P1 + P2** Budget cap 10 AND retrieval missed the Section-2 chain — engine anchored only on Art. 6 then pulled transparency/GPAI noise |
| `mt_033` | similar HRAIS provider scenario | 28 refs | 9 refs (IDENTICAL set to mt_031) | **P1 + P2** Same as mt_031 — suggests Stage-2 prompt is producing a canned reply for any HRAIS provider question |

## Root-cause patterns (ranked by addressable lift)

### P1 — Multi-turn ref-budget cap of 10 is the hard ceiling on multi_turn Ref axes  ★★★★★

**Evidence**:
- 20/20 multi-turn rows ship 9 or 10 refs (zero variance).
- 8 of 20 gold sets are > 20 refs (HRAIS Section-2 + 3 obligations chains).
- mt_031/033 gold=28, pred=9 → recall 0.036.

**Root cause**: `app/routes/regenold.py::regenold_eu_ai_act_ask` ~line 2627 sets `_effective_max_refs = 10` for any `_is_scenario_question` (multi-turn flattened questions match the scenario shape). No further widening for HRAIS-shape provider questions, no detection of "list every Article" intent.

**Fix**: shape-aware budget for the "list-every-Article" intent. When (a) the question carries the phrase "which articles" / "list the articles" / "what articles set them out" AND (b) the engine retrieves Art. 6 (classification anchor) → lift the budget to **22** (the typical HRAIS Section-2 + 3 chain length, deduped). Add `_HRAIS_LISTING_REF_BUDGET = 22` constant. Env-gated `REGENOLD_HRAIS_LISTING_BUDGET` (default ON).

**Risk**: davidath QA gold avg is 1 ref → tightening guard means the lift only fires on multi-turn flattened text that meets BOTH conditions; QA is unaffected. Davidath scenarios cap at gold ~10 refs → 22-budget would only over-cite on a handful; net-positive on the Jaccard given multi-turn pred goes from 9→22 against gold 22-35.

**Estimated lift**: multi_turn Ref Loose **0.371 → ~0.50**, multi_turn Ref Strict **0.396 → ~0.55**. Cumulative overall +0.025 Ref Loose.

**Code surface**: ~20 LOC in `app/routes/regenold.py` budget-resolution block + cache-key extension + 4 regression tests.

---

### P2 — HRAIS Section-2 graph expansion not firing on multi-turn flattened text  ★★★★

**Evidence**:
- mt_031/033/039 reasoning trace: `anchors_used: ['Art. 6']` and `retrieval_path: neo4j`.
- All three then pull Art. 4/50/51/52/90 (transparency + GPAI) — UNRELATED to HRAIS provider obligations.
- The R31.1 graphrag_expand HRAIS chain (`Art. 6 → 9/10/11/12/13/14/15/16/17/18/26/43/47/49/72 + Annex III/IV`) is documented as gated on scenario shape — but it's not surfacing those articles into the candidate set here.

**Hypothesis**: graphrag_expand's scenario-shape detection looks for "We are a {role}…" at the START of the question. Multi-turn flattened text prepends `[Turn 1] We are a provider…` → the bracket prefix breaks the regex match. The expander silently no-ops, then BM25 + intent-classifier dominate retrieval, and the GPAI/transparency keywords from the question text win.

**Fix**: extend the scenario-shape detector to strip leading `[Turn N]` markers before matching. Plus add an explicit HRAIS-chain expansion when (a) Art. 6 is the only Section-1 anchor AND (b) the question carries provider-role + obligation-list intent.

**Risk**: davidath scenarios already exercise the scenario-shape path and would be unaffected (no `[Turn N]` prefix). Multi-turn rows get a clean fix without touching the davidath scenario path.

**Estimated lift**: compounds with P1 — without P2 a 22-ref budget on a noisy candidate set would inject more noise. Together: multi_turn Ref Loose **0.371 → ~0.55**.

**Code surface**: ~15 LOC in `app/engines/graphrag_expand.py` regex + a new HRAIS-listing branch + 6 tests.

---

### P3 — Sub-point format mismatch against parent-only gold  ★★★

**Evidence**:
- `qa_028`: gold=`Article 27`, pred=`Article 27.1` → Jaccard 0.000 (treated as different strings).
- 1 visible row here but a known recurring pattern in the davidath bench too — R38 sub-point emission upgrades parent refs, but gold often uses the parent.

**Root cause**: the sub-point emitter ([`app/data/subpoint_emitter.py`](../app/data/subpoint_emitter.py)) replaces `Article 27` with `Article 27.1` when the answer prose mentions the deployer-FRIA trigger. The wire never ships the parent ref alongside.

**Fix**: when the emitter upgrades a parent to a child, KEEP the parent ref in the references list too. The competition's strict-ref rubric counts parent-as-superset-of-child, so shipping both can only help Jaccard (precision unchanged when parent already matches gold; recall improves when gold is parent-only).

**Risk**: small Ref Conciseness dip (each affected ref doubles up). Need an A/B against davidath to confirm net rubric positive — the R38 change was made to lift conciseness, so reversing in this shape needs verification.

**Estimated lift**: per-affected-row Jaccard 0.000 → 1.000. Hard to estimate aggregate without re-scoring the bench; likely +0.01 overall Ref Loose / Ref Strict.

**Code surface**: ~10 LOC in `app/data/subpoint_emitter.py` — emit both parent + child rather than replace; cache-key extension; 3 tests.

---

### P4 — Wrong-Article retrieval on definitional deployer-duty questions  ★★★

**Evidence**:
- `qa_078`: "When must deployers inform the PROVIDER of a serious incident?" → pred=`Article 73.1` (serious-incident reporting article), gold=`Article 26` (deployer's notification duty under Art. 26.5).
- `qa_101`: "When must deployers inform WORKERS about the use of a high-risk AI system?" → pred=`Article 6` (high-risk classification), gold=`Article 26` (deployer's worker-info duty under Art. 26.7).

**Root cause**: the entity extractor (R81-N) boosts ROLE `deployer` → Art. 26 by 3×, but BM25 raw scores for "serious incident" → Art. 73 and "high-risk AI system" → Art. 6 are still high enough to outscore the boosted Art. 26. The Deployer-Hop helper requires Art. 26 to already be a candidate before it appends 13/14/9; here Art. 26 isn't in candidates at all, so the hop has nothing to attach to.

**Fix**: stronger compound triggers. When the question contains BOTH a role noun (deployer / provider) AND a duty verb (inform / notify / report / register / conduct), inject the role-specific Article (26 for deployer, 16 for provider) as a synthetic candidate at injection score — independent of base retrieval. Mirrors the R81-N.1 QA-shape role injection pattern.

**Risk**: needs careful gating to avoid over-injecting Art. 26 on every question mentioning "deployer". Use intent classifier label as the secondary signal (only inject when intent ∈ {role_obligations, definition_qa_about_obligation}).

**Estimated lift**: 3-5 deployer-QA rows flip from 0.000 → 1.000 Ref Loose. Cumulative overall +0.015.

**Code surface**: ~30 LOC in `app/engines/entity_extractor.py` — new `is_role_duty_shape()` gate + injection in `kb_search.top_articles_by_relevance`; 8 tests.

---

### P5 — Deployer Graph-Hop firing rate is 0 in live  ★★

**Evidence**:
- 5 deployer-shape rows (definitional Wh-shape, no scenario opener) eligible per the R86 gate.
- 0 of 5 showed Art. 26 + (Art. 13|14|9) co-presence.

**Root cause**: the hop is gated on Art. 26 already being in candidates. Per P4 evidence, base retrieval is missing Art. 26 entirely on deployer-duty questions. The hop logic itself is correct — its precondition is never met.

**Fix**: P4 makes this irrelevant. Once Art. 26 is injected by the new role-duty compound trigger, the existing hop logic appends Art. 13/14/9. No new code needed in the hop; P4 unlocks it.

**Estimated lift**: counted under P4.

---

### P6 — 30% consistency_guard fire rate suggests Stage-2 polish drift  ★★

**Evidence**:
- 30 of 100 rows fell into `retrieval_path: consistency_guard` — meaning Stage-2 polish produced prose that contradicted the references list, and the R49-A grounded-prose substitute had to fire.
- This is unchanged from prior rounds but the R86 BLUF prompt was supposed to reduce it.

**Root cause**: Sonnet 4.6 still emits "the references block contains no…" or "no specific provisions were returned…" hedging on ~30% of rows even with the new BLUF rules. The hedging triggers `_STAGE2_REFUSAL_MARKERS` which routes to grounded prose. The grounded prose is OK but loses Sonnet's per-Article descriptions, which hurts Ans Strict on those rows.

**Fix**: two-step.
1. Examine which 30 rows hit consistency_guard — pattern likely correlates with low engine_confidence (0.3 or 0.5). Add a fast-path: when engine_confidence ≤ 0.5, skip Stage-2 polish entirely and ship deterministic + augmenter. Saves latency AND removes a contradiction source.
2. Extend `_STAGE2_REFUSAL_MARKERS` with any new hedging phrases the R86 measurement surfaced.

**Risk**: skipping Stage-2 on low-confidence rows trades tone polish for citation faithfulness. Tone is currently 1.0, so this trade is acceptable IF tone holds on the deterministic path (it has historically; deterministic is the tone crown jewel).

**Estimated lift**: latency p50 ~14.9 s → ~10 s; Ans Strict modest +0.005 (the consistency-guard rows already get grounded prose).

**Code surface**: ~20 LOC in `app/engines/graph_rag.py::_two_stage_generate` confidence gate; 5 tests.

---

### P7 — Reasoning trace lacks Query De-Noiser firing signal  ★

**Evidence**: We can't tell from the trace whether `_rewrite_multiturn_query` (R86) fired on the 20 multi-turn rows or fell back to concatenation. The mt_031/033/039 reasoning shows `anchors_used: ['Art. 6']` only — if the de-noiser fired and produced a focused query, BM25 should anchor on the role + obligation phrases, not just Art. 6.

**Fix**: instrument the trace. Add a `query_denoiser` block: `{fired: bool, latency_ms: int, rewritten_chars: int, fallback_reason: str | null}`. Pure observability — no behaviour change.

**Risk**: zero. Adds bytes to the trace; the route already serialises arbitrary trace fields.

**Estimated lift**: zero direct lift; enables targeted P1/P2 debugging.

**Code surface**: ~15 LOC across `app/routes/regenold.py` + `app/integrations/regenold/reasoning_trace.py` + 2 tests.

---

## Recommended R87 sequencing

1. **R87-A — P7 trace instrumentation** (lowest risk, unblocks observability)
2. **R87-B — P1 + P2 together** (multi-turn budget + HRAIS chain expansion — they compound)
3. **R87-C — P3 sub-point parent retention** (small surface, measurable on davidath)
4. **R87-D — P4 role-duty compound trigger** (deployer-QA rescue — needs P5 unlocked as side effect)
5. **R87-E — P6 confidence-gated Stage-2 skip** (latency + consistency_guard reduction)

Each stage davidath-byte-identical or rubric-positive on the bench gate. The wins compound on the next live representative-100.

## Estimated cumulative impact (post-R87)

| Axis | r86-live | R87 target | Mechanism |
| ---- | -------: | ---------: | --------- |
| Multi-turn Ref Loose | 0.371 | **~0.55** | P1+P2 |
| Multi-turn Ref Strict | 0.396 | **~0.55** | P1+P2 |
| Deployer Ref Loose | 0.466 | **~0.60** | P4 |
| Overall Ref Loose | 0.610 | **~0.66** | P1+P2+P4 compound |
| Overall Ans Strict | 0.287 | ~0.30 | P3+P6 |
| Tone | 1.000 | **1.000** (must hold) | unchanged |
| Latency p50 | 14.9 s | **~10 s** | P6 |

## What the R87 plan deliberately does NOT touch

- The Query De-Noiser (R86-1). The trace gap (P7) blocks honest measurement; instrument first, then re-evaluate. Premature tightening or removal would discard the multi_turn Ans Strict +0.05 we just earned.
- The BLUF prompt (R86-3). Tone held at 1.0; no measured regression. P6 confidence-gate is the lighter-touch fix for the consistency_guard rate.
- The R78.1 cache-no-poison contract. Live trace shows `cache_hit: false` on all 100 rows — the cache invalidation on the R86 deploy worked correctly.
- The audit chain. Per the live sidecar, every row carries a valid `chain_entry_id` — audit pipeline is healthy.

---

*Generated 2026-05-25 from `representative-100-r86-live-postship.json` (100 rows, live Railway, Stage-2 ON). All claims grounded in per-row reasoning traces; no LLM-judge involved in this analysis.*
