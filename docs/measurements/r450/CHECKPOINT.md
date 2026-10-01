# R450 — passage-emission sweep: budget × allocation

**Round:** R450 · **Date:** 28 September 2026
**Working tree:** local checkout on `fix/r444-healthy-leg-screen` (dirty). This file is **local and untracked** — nothing posted, pushed, or attached to a PR.
**Scope:** Regulation (EU) 2024/1689 only.
**Instrument:** `evals/retrieval/emit_sweep.py` (new) + `evals/retrieval/unit_grain.py` (`--unit-budget`, `--unit-alloc`, emitted-char columns).
**Determinism:** offline, no network, no judge, no LLM. Gold = `docs/measurements/r388/official_gold_n110.jsonl`; retrieval = the production `kb_search.top_articles_by_relevance(question, k=8, min_score=1.0)`; emission = the production `provision_text.select_relevant_paragraphs`.

## 1. Question and target

R449 measured that on rows where the gold head *was* retrieved, the shipped passage selector's top paragraph is the gold paragraph ~72% of the time, while its bounded output carried ≥80% of the gold paragraph on only **0.41** of rows (mean coverage 0.67, at `max_chars=500`). This round asks whether the **budget** and the **order in which the budget is spent** can lift that above 0.8 **without growing context cost**.

## 2. Two losses, separated

Gradable rows: **82** of 110 (gold head retrieved and the ref carries a numbered paragraph/item).

| budget | `rank` hits@0.8 | `density` hits | best cell | mean emitted chars (`rank`) |
|---|---|---|---|---|
| 300 | 34/82 | 34/82 | 35 (`split@0.6`) | 549 |
| 500 | 35/82 | 35/82 | 37 (`split@0.5`) | 574 |
| 700 | 42/82 | 42/82 | 44 (`split@0.7`) | 660 |
| 900 | 56/82 | **57/82** | 57 | 809 |
| **1200** | 61/82 | **64/82** | **64** | 1,061 (density **1,056**) |
| 1600 | 67/82 | 68/82 | 68 | 1,413 (density 1,382) |

Partition at the production Stage-2 **grounding** budget (1,200 chars/ref, `_graph_rag_impl._grounding_ref_budget()`):

* gold unit **fits** the budget: **62** rows — 53 hit under `rank`, **64** under `density`.
* gold unit is **oversized**: **20** rows — 8 hit. In **17** of those the *correct* unit is the top-scoring one, so the loss is the deliberate drilling (`_drill_subpoints`) that hands Stage-2 a proper subset: coverage of a 2,000-char paragraph inside a 1,200-char budget is ~0.6 by construction.
* **fits-but-missed: 9 rows** (`rg_001, rg_011, rg_033, rg_060, rg_069, rg_081, rg_088, rg_091, rg_110`) — the gold unit fits and still never arrives. On **all 9** the top-scoring unit is the *wrong* one, and on **6** of them that wrong unit alone consumes the whole budget (the `top1` arm emits the same characters as `rank`). These are the allocation-bound rows, and they are what `density` and `split` were built for.

## 3. Verdicts

1. **>0.8 is not attainable without growing context cost.** Coverage is a share of the gold paragraph's own tokens; 79% of gold units exceed the 500-char budget and ~24% exceed 1,200. Crossing 0.8 needs ≈1,600 chars/ref (0.817 rank / 0.829 density at 1,413 / 1,382 mean chars = **+33%**). Recorded as a negative rather than re-scoped away.
2. **`density` weakly dominates `rank` at the same bound.** Ties at 300/500/700; +1 at 900, **+3 at 1,200**, +1 at 1,600 — and *fewer* characters at 1,200 (1,056 vs 1,061). Paired per-row at 1,200: rescues `rg_033` (0.40→1.00), `rg_069` (0.53→1.00), `rg_088` (0.47→1.00), **zero regressions**. At 1,600 it trades one row (`rg_060`). `rg_069` is the R399 storage/transport finding reproducing on a different instrument — a good sign that the mechanism is "buy the small operative paragraph instead of the big irrelevant one".
3. **`split` is falsified as a context-neutral lever.** It is the only policy that addresses the 6 rows where a wrong oversized top unit eats the budget, and it does gain at low budgets (+2 rows at 500, zero regressions), but it inflates p95 emitted chars 1,221 → 2,030 (mean 574 → 1,016) and at the production 1,200 budget it is *worse than shipped* (0.732 vs 0.744) on more chars. Kept behind `REGENOLD_EMIT_ALLOC=split` + `REGENOLD_EMIT_SPLIT_TOP`, documented as measured-dead so the next round does not re-derive it.
4. **`top1` is a context-saving control, not a coverage lever.** At 1,200 it emits 829 chars (‑22%) for 58/82 (0.707) — worth knowing, not worth shipping for this goal.

## 4. End-to-end through the harness (`HARNESS-EMISSION.md`)

The same numbers, produced by the R449 instrument after it was taught the emission axis (`--unit-budget`, `--unit-alloc`, emitted-char columns). Arms differ only in emission; all five share one retrieval configuration, so the unit denominators match within the family.

| arm | hit rate ≥0.8 | coverage mean | emitted chars mean | emitted chars p95 |
|---|---|---|---|---|
| `emit_density_500` (= R449's budget, new allocator) | 0.412 | 0.673 | 574 | 1,221 |
| `emit_rank_1200` (= **shipped grounding configuration**) | 0.718 | 0.834 | 1,061 | 1,221 |
| `emit_density_1200` | **0.753** | 0.853 | **1,056** | 1,221 |
| `emit_top1_1200` | 0.682 | 0.807 | 829 | 1,221 |
| `bm25` @500/rank (R449 baseline, 79 rows) | 0.405 | 0.666 | 580 | 1,221 |

`density` at the shipped budget: **+3.5 pp hit rate, −5 chars per row, p95 unchanged.**

## 5. What shipped in code (default unchanged)

* `app/data/provision_text.py` — `_choose_units()` allocation policies (`rank` shipped, `pack`, `density`, `top1`, `split`), `emit_alloc()` / `emit_split_top()` env gates, `alloc=` kwarg on `select_relevant_paragraphs`. **Default is `rank`: the emitted bytes are unchanged.**
* `app/routes/regenold.py` — `REGENOLD_EMIT_ALLOC` and `REGENOLD_EMIT_SPLIT_TOP` registered in `_engine_cache_key` (they change which verbatim text Stage-2 sees, so they change the cached answer; unkeyed they would reproduce the R263.2/R288.1 cross-arm contamination).
* `tests/test_r450_emit_allocation.py` — 12 tests: default byte-identical, per-call env reads, typo fallback, harness/production env-name parity, whole-unit + budget-bound invariants under every policy, policy non-vacuity, the density mechanism pinned directly on `_choose_units`, the `split` guard, and a verbatim-containment check that the emitted text is findable in the provision body.
* `evals/retrieval/emit_sweep.py` — the sweep; `evals/retrieval/unit_grain.py` — the emission axis added to the R449 harness.

## 6. What is NOT done — and the gate that is required

* **No live gate, no default flipped.** Changing which verbatim paragraphs reach Stage-2 is reference-affecting under invariant #5: the R399 precedent requires a live paired run clearing `gold_dropped_head` before a flip. `density` is therefore *measured and recommended*, not adopted.
* **No answer-level claim.** Unit-grain coverage is a proxy for "the operative paragraph is in the prompt"; it is not evidence that any official axis moves.
* **No subpoint-grain claim.** The sweep calls the selector with the head (`Art. N` / `Annex N`) exactly as the harness does. Production passes the *actual* coordinate, so a deep-cited ref (`Article 13.3.b.iv`) takes the `spec.subpoints` early-return path instead of the allocation path. These numbers do not extend to those rows.
* **Gate specification for `density`:** one paired run at the shipped grounding budget with `REGENOLD_EMIT_ALLOC=0` vs `density`, wrapper/Bedrock served, judged on the 8 official axes plus `gold_dropped_head` and excess references. Expected movement: reference axes flat (the emission does not touch `references`), Ans Loose/Strict the axes at risk, Speed flat (−0.5% chars).

## 7. R450b — rank-level fusion as the candidate default (in flight)

Requested: make rank-level fusion the default candidate and run the live pairwise gates on it, on the ground that it is the only fusion arm that improves ordering with *identical reference membership*.

### 7.1 The premise, re-measured row by row (offline, all 110 official questions)

| comparison | k=8 | k=15 |
|---|---|---|
| retrieved **set** differs (`REGENOLD_RRF_FUSION` 0 vs 1) | **0/110** | **0/110** |
| retrieved **order** differs | **110/110** | **110/110** |
| first-8 slice (the Stage-2 grounding block and `kg_context._node_ids(limit=8)` cut) differs | **110/110** | 110/110 |

So the premise holds in the strong sense — no row can gain or lose a citation — and it is *reach* that is universal, not marginal: the lever reorders every question and changes which provisions receive verbatim grounding text on every question. That is what makes a live gate necessary rather than optional (an ordering default cannot be validated by a membership-identical offline read).

### 7.2 The candidate flip, and the two pins it breaks

`app/data/kb_search.py::_rrf_fusion_enabled()` default moved `"0"` → `"1"` (candidate, documented in the docstring); `REGENOLD_RRF_FUSION=0` restores the additive-fill ranking byte-for-byte and is the gate's arm A. `tests/test_semantic_layer.py` moved with it: the default-off pin became a default-on pin plus an explicit `=0` case, and the two additive-fill tests now select the additive arm explicitly instead of relying on an unset variable.

**Two pre-existing ordering pins now FAIL under the flip, and they are evidence, not noise:**

* `tests/test_r112_scope_fixes.py::TestR112PenaltiesAlias::test_sanctions_question_retrieval_art99_first` — "What are the sanctions … for transparency risk systems?" must return **`Art. 99` first**. Under rank-level fusion it returns **`Art. 13` first**, with `Art. 99` fourth (membership still contains it). An operative head demoted on a real question.
* `tests/test_r112_perf_fixes.py::TestEntityExtractionDedupe::test_ranking_identical_default_env` — the k=5 fused-path ranking table captured from the previous default.

Both assert *ordering*, so any default flip breaks them by construction; the deciding question is whether the reordering costs a scored axis, which only the gate can answer. Until then the flip is **provisional and revertible in one line**, and the pins stay failing rather than being rewritten to match the new default.

### 7.3 The live paired gate (launched; status in `GATE-STATUS.txt`)

Design: the R415 official-corpus gate, reused on its one-flag interface, **both arms fresh** on the same 27 rows (the reachable set from `official-lever-b.ckpt.jsonl`) and the same working tree, differing only in `REGENOLD_RRF_FUSION`. The cached R415 arm-A baseline is deliberately NOT reused: it was produced with `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=0`, and that flag has since been flipped ON, so baselining against it would pair the fusion flag with a system-prompt difference (the R416 one-flag-invariant defect).

```bash
.venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --arm a --matched-from b \
    --flag REGENOLD_RRF_FUSION --arm-values 0,1 --tag=-rrf
.venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --arm b --matched-from b \
    --flag REGENOLD_RRF_FUSION --arm-values 0,1 --tag=-rrf
.venv/Scripts/python.exe docs/measurements/r415/official_lever_gate.py --score \
    --flag REGENOLD_RRF_FUSION --arm-values 0,1 --tag=-rrf \
    --baseline docs/measurements/r415/official-lever-a-matched-rrf.ckpt.jsonl
```

Artifacts: `arm-a-rrf.log`, `arm-b-rrf.log`, `score-rrf.log`, `official-lever-{a,b}-matched-rrf.ckpt.jsonl` (+ `.run.json` sidecars) in `docs/measurements/r415/`, and the paired table in `docs/measurements/r415/official-lever-paired-rrf.json`. Cost basis: 27 rows × ~33 s p50 per arm (measured from the R415 matched arm: p50 32.8 s, p95 51.1 s, 925 s per arm).

Pre-registered accept rule (fixed before the run): **KEEP the flip** only if the paired table prints (no void), `gold_dropped_head` does not rise, and no reference axis falls by more than 1 pp; **REVERT** on any gold-head rise, on a reference-axis fall beyond that, or on a void run.

### 7.4 Outcome — the gate VOIDED at the judge leg, so the flip was reverted

The **generation** half of the gate ran clean on both arms, and that is itself worth recording:

| arm | rows | errors | Stage-2 served | fallback rows | transport |
|---|---|---|---|---|---|
| A (`REGENOLD_RRF_FUSION=0`) | 27/27 | 0 | 27 | **0** | primary 28/28 ok |
| B (`REGENOLD_RRF_FUSION=1`) | 27/27 | 0 | 27 | **0** | primary 27/27 ok |

Both arms therefore cleared the void conditions the *run* can control (no fallback dilution, no errors, matched rows), and their paired answers are on disk (`official-lever-{a,b}-matched-rrf.ckpt.jsonl`, tagged `-rrf`).

**The judge leg refused, so no axis was read.** `evals.official.score_arm` exited 1 on *both* arms: "refusing to grade rows without evidence of healthy primary polish or a recognized intentional Stage-2 skip: rg_003 (missing_provenance), rg_004 (missing…". The cause is an instrument gap, not the lever: the rows this gate writes carry `stage2_used` / `stage2_fell_back` and **no provenance field**, while `score_arm`'s R417-era guard requires per-row evidence of healthy primary polish (or a recognized intentional skip). The old R415 artifacts have the same ten-key schema, so this gate cannot be scored on the current tree at all until its runner persists provenance.

Consequence, applied rather than deferred: the provisional default flip was **reverted** (`_rrf_fusion_enabled()` back to `"0"`), the original default-off pin restored, and the two pre-existing ordering pins now pass again (161 tests green across the fusion, retrieval, emission and dense-boost suites). `REGENOLD_RRF_FUSION=1` remains the candidate for the next gate; nothing about production ranking changed.

**Next step for the gate (in order):** (1) make the arm runner persist the provenance `score_arm` demands and prove it on one arm (the R415 `official-lever-b.ckpt.jsonl` rows are the control — they must become gradeable without re-generating answers, or the guard's scope must be recorded as the reason it cannot be); (2) re-run only the judge leg on the two `-rrf` checkpoints already on disk (no new generation spend); (3) decide the flip on the pre-registered rule above. Until then the candidate's status is: premise measured and strong, **zero axis evidence**, two ordering pins failing under it — the `Art. 99` demotion in particular is a hypothesis the gate must resolve, not a detail to wave through. Answer axes may move either way inside the judge's noise; they are recorded, not gated.

## 8. Reproduce

```bash
../.venv/Scripts/python.exe -m evals.retrieval.emit_sweep \
    --out docs/measurements/r450/emit-sweep.json --md-out docs/measurements/r450/EMIT-SWEEP.md
../.venv/Scripts/python.exe -m evals.retrieval.unit_grain \
    --arms bm25,emit_rank_1200,emit_density_1200,emit_density_500,emit_top1_1200 \
    --md-out docs/measurements/r450/HARNESS-EMISSION.md
../.venv/Scripts/python.exe -m pytest tests/test_r450_emit_allocation.py tests/test_r449_unit_grain_harness.py -q
```
