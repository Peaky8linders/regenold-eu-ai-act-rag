# Antifragile AI — R419 live HARD run: the full metric board

**Run** `r419-hard` · hard mode (rolling multi-turn, then the official adversarial pushback) · 110/110 rows · in-process engine on merged `main` (`7ef9df05`) · Stage-2 primary = the Claude-Max wrapper via the cloudflared tunnel.

**Judge** `openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3` — three repetitions at temperature 0.1, grouped.

**Scored by** `evals.official.rubric.score_rows` (the published instrument), the same module that produced `docs/measurements/r388/score-r419-hard-hard.json`. This report recomputes them and the two agree: **yes**.

> The correctness criteria, reference answers and expected references are **reconstructed** (`evals/official/build_gold.py`), because the evaluator never published them. Compare arms under this instrument; do not read a number as an official score.

---

## 1. All eight metrics

| Metric | **This arm (R419 live)** | Min–max over 3 reps | Antifragile (Aug-25) | 2026 Frontier | Gap → frontier |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Ans. Correctness (Loose) | **94.15%** | 93.9–94.7 | 89.90% | 92.00% | +2.15 **BEATS** |
| Ans. Correctness (Strict) | **90.91%** | 90.0–90.9 | 80.00% | 84.80% | +6.11 **BEATS** |
| Ans. Conciseness | **44.19%** | — | 45.20% | 71.80% | -27.61 |
| Ref. Correctness (Loose) | **96.08%** | — | 89.50% | 94.60% | +1.48 **BEATS** |
| Ref. Correctness (Strict) | **70.59%** | — | 70.70% | 74.10% | -3.51 |
| Ref. Conciseness | **44.79%** | — | 49.80% | 58.50% | -13.71 |
| Regulatory Tone | **93.64%** | 93.6–94.5 | 96.10% | 100.00% | -6.36 |
| Resp. Speed | **70.83%** | — | 85.70% | 86.70% | -15.87 |
| **OVERALL (geometric mean)** | **72.48%** | 72.4–72.6 | 73.40% | 81.70% | -9.22 |

Rows 110 · reference axes scored on 102 rows (the rest carry no annotated expected references and are excluded there by the benchmark's own rule).

Three axes are **not** judge-scored, which is why their bands are flat: `ans_conciseness` and `resp_speed` are computed from the answer text and the latency, and the two `ref_*` axes are matched against the expected reference key. `ref_conciseness` is deterministic for the same reason. The judge decides only the two answer-correctness axes and Regulatory Tone.

### Against the other published baselines

| Metric | R419 live | Antifragile (Aug-25) | 2025 Search-Integrated | 2026 Frontier |
| :--- | ---: | ---: | ---: | ---: |
| Ans. Correctness (Loose) | **94.15%** | 89.90% | 87.60% | 92.00% |
| Ans. Correctness (Strict) | **90.91%** | 80.00% | 76.70% | 84.80% |
| Ans. Conciseness | **44.19%** | 45.20% | 58.80% | 71.80% |
| Ref. Correctness (Loose) | **96.08%** | 89.50% | 82.70% | 94.60% |
| Ref. Correctness (Strict) | **70.59%** | 70.70% | 55.40% | 74.10% |
| Ref. Conciseness | **44.79%** | 49.80% | 56.80% | 58.50% |
| Regulatory Tone | **93.64%** | 96.10% | 99.70% | 100.00% |
| Resp. Speed | **70.83%** | 85.70% | 95.90% | 86.70% |
| **OVERALL** | **72.48%** | 73.40% | 74.80% | 81.70% |

---

## 2. What is actually scoring, and what is not

**Correctness is strong and measured, not lucky.** 354 of 376 criteria satisfied across 110 rows; 100 rows satisfy every criterion. 3 rows satisfy none.

| criteria satisfied | rows |
| :--- | ---: |
| none | 3 |
| 1 | 6 |
| 2 | 13 |
| 3 | 43 |
| 4 | 36 |
| 5 | 5 |
| 6 | 4 |

### Rows that fail at least one criterion

| row | satisfied | of | refs | expected | note |
| :--- | ---: | ---: | :--- | :--- | :--- |
| `rg_036` | 0 | 3 | Article 10.4 | Article 42.1 | **all criteria failed** deterministic-leg serve (transport) |
| `rg_037` | 0 | 6 | Article 6.2, Article 49.4 | Annex VIII.a | **all criteria failed** deterministic-leg serve (transport) |
| `rg_062` | 2 | 3 | Article 79.1, Article 24.4 | Article 24.4 |  |
| `rg_069` | 2 | 3 | Article 24.4, Article 23.2, Article 47.1, Article 16, Article 11.1 | Article 24.3, Article 23.4 |  |
| `rg_085` | 1 | 4 | Article 6.2, Article 5.1.d, Article 50.4, Annex III.7.b, Annex I | Article 6.1, Article 6.2, Annex III.1.a | deterministic-leg serve (transport) |
| `rg_087` | 3 | 4 | Article 9.5, Article 3.65, Article 5.1.d, Article 55.1, Article 51.1 | Article 9 |  |
| `rg_088` | 0 | 3 | Annex I.19, Annex III.7.b, Article 6.1, Article 25.2, Article 8.2 | Article 26.1, Article 26.6 | pushback capitulation (see §3) |
| `rg_089` | 2 | 3 | Annex III.5.d, Article 6.2, Article 5.1.d, Annex I.5, Article 50.1 | Article 6.3.a |  |
| `rg_091` | 1 | 3 | Article 6.1, Annex III.5.d, Annex I.11, Article 43.1, Article 9 | Article 6.1 |  |
| `rg_103` | 3 | 4 | Article 50.4, Article 6.3.d, Article 5.1.h, Annex III.3.d, Article 3.46 | Article 50.4 |  |

**The judge is stable.** 2 of 110 rows produced a different criteria vector across the three repetitions: rg_035, rg_037. Judge transport errors: 0.

**The gap is verbosity, and it is arithmetic.** `ans_conciseness` is `min(1, len(reference) / len(candidate))` and `ref_conciseness` is `min(1, len(expected) / len(provided))`.

| quantity | value |
| :--- | ---: |
| mean answer | 2137.9 chars |
| mean reference answer | 649.3 chars |
| mean answer / reference | 3.31x |
| rows already at or under the reference length | 19 of 110 |
| median answer | 2240 chars |
| answers over 3,000 chars | 30 |
| mean cited provisions | 3.56 per row |
| mean expected provisions | 1.26 per scored row (102 rows) |
| excess provisions beyond the minimal expected set | 231 |

So the two conciseness axes are not independent evidence about quality: they say the answers are ~3x the reference prose and the citation lists are ~2x the minimal key. **Answer length is a generation-side property**, which is why every post-hoc citation-pruning lever has failed and why the tracked lever is a prompt/interpreter change, not a filter.

### Is the metric wrong, or did the answers get longer?

The metric is a pure length ratio, and it reproduces exactly: recomputing `min(1, len(reference)/len(candidate))` from the rows gives 44.19% against the instrument's 44.19%. The formula has not changed since it was written (only two commits have ever touched `evals/official/rubric.py`), and the reference denominator is stable at 649-650 chars on EVERY board in `docs/measurements/r388/`, this one included. So the axis reports what it defines.

The comparison that settles it is **R390 live hard vs R419 live hard**: same 110 questions, same gold, and the SAME generator (opus-5 over the wrapper). Nothing in this report is a generator change against that board.

| measure | R390 hard (opus-5) | **R419 hard (opus-5)** | change |
| :--- | ---: | ---: | ---: |
| mean answer chars | 1139 | **2138** | 999 |
| median answer chars | 1136 | **2240** | 1104 |
| rows longer than 2x the reference | 45 | **79** | 34 |
| mean cited provisions | 3.09 | **3.56** | 0.47 |
| rows citing more than 4 provisions | 22 | **39** | 17 |
| ans_conciseness | 62.02% | **44.19%** | -17.83% |

**83 of 110 rows grew by more than 15%** (median ratio **1.70x**); **6 shrank** and **12 are byte-identical**. The identical ones are the curated deterministic subset (ratio exactly 1.00), and **4 of the 6 shrinking rows are the transport-degraded rows that shipped a deterministic Stage-1 draft** (`rg_036`, `rg_037`, `rg_085`, `rg_092` - R420's prior-answer floor), plus 1 more (`rg_006`) that is not Stage-2-polished at all (curated by design) rather than evidence that a lever shortened anything. That localises the change to the Stage-2 generation path, not to the metric, the corpus or the gold.

Every number in this subsection is generated by `docs/measurements/r422/conciseness_regression_attribution.py` (offline, zero API calls) into `docs/measurements/r422/attribution.json`. It recomputes `ans_conciseness` from the two checkpoints joined to the gold reference answers, which independently reproduces this axis (62.02 with R390's answers, 44.19 with this board's).

Which lever did it is a bisect, not a guess, but the candidate set is bounded **from git**: **46 `REGENOLD_*` flag names exist in `app/` at HEAD that did not exist at R390 (`74008ea`), and 15 of them are default-ON by their own literal default** (`REGENOLD_CLOSED_SET_SKELETON`, `REGENOLD_CONTRACT_COMPLETENESS`, `REGENOLD_COORD_MAP_PROMPT`, `REGENOLD_DENOISER_BEDROCK`, `REGENOLD_EVIDENCE_CONTRACT`, `REGENOLD_EXTRACT_SHAPE_GUARD`, `REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS`, `REGENOLD_KG_LOCAL_MIRROR`, ...). Several exist to make Stage-2 enumerate more (`COORD_MAP_PROMPT`, `CLOSED_SET_SKELETON`, `KG_POINT_TEXT` with its 26 -> 384 unit grounding block). The one lever MEASURED to shorten answers -- the full 53 kB system prompt, `+19.2 pp ans_conc` and 2456 -> 1426 chars on the R415 paired arm -- is single-turn-gated, so hard-mode turns run without it by construction.

### Is the denominator calibrated, or is the answer shape flat?

A length ratio can be uninformative in two opposite ways, and they need opposite remedies: either the reference does not scale with how much law a question needs (a metric defect), or our answer does not scale (a generation defect). Joining the gold criteria count to both lengths answers it.

| | value |
| :--- | ---: |
| reference answer length | mean **649** chars · min 160 · max 1007 · **202 chars per criterion** |
| corr(criteria count, reference length) | **+0.55** — the denominator scales with the question |
| corr(criteria count, our answer length) | **+0.11** — our answer does not |

Our answers spend ~668 chars per criterion against the reference's 202, and a large part of that is a **fixed component**: a 1-criteria row is written at 1,122 chars, so the marginal length per criterion is far smaller than the average.

| criteria on the row | n | mean reference | mean answer | ans_conciseness |
| :--- | ---: | ---: | ---: | ---: |
| 1 | 4 | 382 | **1122** | 48.6% |
| 2-3 | 57 | 621 | **2139** | 42.0% |
| 4-5 | 44 | 683 | **2247** | 45.4% |
| 6 | 5 | 893 | **1977** | 54.9% |

**The reference scales and our answer largely does not**, so the axis is worst exactly where most of the board sits: the 57 rows needing 2-3 limbs score 42.0%, while the 5 6-criteria rows score *best* (54.9%) only because the reference is longest there. That is the signature of a fixed answer *shape* (tier verdict, enumerated limbs, reference block) rather than of answering the question as asked.

The enumeration scaffold is injected just as flatly: `REGENOLD_CLOSED_SET_SKELETON` fires on **110/110 rows** and injects a mean **5,125 chars** (median 5,193) of member lists — **5,862 chars on the 4 one-criteria rows whose answers average 1,122 chars**, 5.2x the answer it is scaffolding. So the metric is measuring a real property; the property it is measuring is that our generation does not modulate with the question, and its prompt scaffolding does not either.

### The five new default-ON levers make the prompt SMALLER, not larger

It is tempting to blame answer length on prompt bulk — this board sends a ~38 kB Stage-2 user payload. That hypothesis is **falsified at the provider seam**, on the real request path with the provider stubbed (7-row strided sample of rows the live board actually polished; both arms fired a graded Stage-2 payload on every sampled row, so the run is non-vacuous and `comparable`):

| arm | mean Stage-2 user payload |
| :--- | ---: |
| HEAD defaults | 38,467 chars |
| the five post-R390 additions OFF | 44,997 chars |
| **delta (OFF - HEAD)** | **+6,530 chars** |

Turning the levers off makes the prompt *bigger*, though it removes 5 kB of member-list scaffold. So the ~1.9x answer growth since R390 did **not** come from those levers inflating the context — the smaller prompt produced the longer answer. The mechanism has to be **instructional** (the closed-set skeleton shows the model the complete member list of every head it cites, which is an instruction to enumerate), which is why the fix is a generation-side shape contract and not prompt pruning. The magnitudes here are prompt-side only; confirming the causal link needs the model in the loop.

**Latency.** mean 29.17 s · median 33.33 s · p90 49.95 s · max 70.88 s. Resp. Speed is `max(0, 100 - latency_s)` per response, so it is a latency measurement, not a quality one.

Turn-1 latency p50 33.1 s · p95 57.4 s · max 77.9 s; 7 rows were served sub-second from the deterministic path.

---

## 3. References in detail

| measure | value |
| :--- | ---: |
| expected provisions met at head level (Article / Annex number) | 124 of 129 |
| expected provisions met at exact subpoint level | 75 of 129 |
| scored rows | 102 |
| rows whose reference set CHANGED between turn 1 and the graded answer | 46 (of 110) |
| rows that DROPPED a gold head | 4 (of 110) |
| expected provisions matched by exact spelling (the axis also credits a descendant, so it reads higher) | 75 of 129 = 58.1% |
| mean reference-set Jaccard, turn 1 vs graded | 0.8298 |

### Rows whose graded answer lost a gold head

| row | head lost |
| :--- | :--- |
| `rg_036` | Article 42 |
| `rg_037` | Annex VIII |
| `rg_088` | Article 26 |
| `rg_100` | Article 6 |

---

## 4. Per-row verdicts

| row | crit. | of | tone | refs | expected | answer chars | ref chars | latency s | note |
| :--- | ---: | ---: | :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| `rg_001` | 2 | 2 | PASS | Article 11.1, Annex IV.1 | — | 387 | 479 | 7.5 |  |
| `rg_002` | 2 | 2 | PASS | Article 50.4 | Article 50.4 | 382 | 503 | 1.0 |  |
| `rg_003` | 4 | 4 | PASS | Annex III.7.b, Article 6.2, Article 49.3 | Article 6.3 | 2617 | 725 | 33.0 |  |
| `rg_004` | 4 | 4 | PASS | Article 6.1, Annex I.11, Article 8.2, Article 9.2, Annex VII.4, Article 10.5 | Article 6.1 | 3534 | 686 | 57.2 |  |
| `rg_005` | 3 | 3 | PASS | Article 13.3, Article 14.4, Article 15.1 | Article 13.1 | 441 | 614 | 1.2 |  |
| `rg_006` | 3 | 3 | PASS | Article 2.1.a, Article 3.1, Article 51.1 | Article 2.1.a | 478 | 626 | 0.8 |  |
| `rg_007` | 3 | 3 | PASS | Article 5.1.g, Article 6.2, Article 50.1, Annex III.1.a, Annex I | Annex III.1.a, Article 5.1 | 3164 | 537 | 39.4 |  |
| `rg_008` | 4 | 4 | PASS | Article 6.1, Annex I.11, Annex VII.4 | Article 6.1, Annex I.a.11 | 2872 | 639 | 42.2 |  |
| `rg_009` | 5 | 5 | PASS | Article 11.1, Article 18.1, Article 17.1, Article 47.1, Article 19.1 | Article 18.1 | 606 | 621 | 0.8 |  |
| `rg_010` | 5 | 5 | PASS | Article 14.4, Annex III | Article 14 | 2465 | 759 | 22.2 |  |
| `rg_011` | 3 | 3 | PASS | Article 3.32, Article 10.3 | Article 10.3 | 739 | 811 | 1.8 |  |
| `rg_012` | 3 | 3 | PASS | Annex III.8 | Annex III.8 | 691 | 736 | 0.9 |  |
| `rg_013` | 5 | 5 | PASS | Article 53.2, Article 51.1, Article 55.2, Annex XI.2 | Article 53.2 | 1075 | 778 | 1.8 |  |
| `rg_014` | 4 | 4 | PASS | Article 6.2, Annex III.3.c, Article 49, Annex I | — | 2859 | 620 | 29.2 |  |
| `rg_015` | 3 | 3 | PASS | Article 6.3, Article 50.1 | Article 50.1 | 1701 | 765 | 30.4 |  |
| `rg_016` | 2 | 2 | PASS | Article 5.1.g, Article 99.7 | Article 99.3 | 2562 | 318 | 39.8 |  |
| `rg_017` | 3 | 3 | PASS | Annex II, Article 5.1.h, Article 27.1, Article 49.3 | Article 5.1.h.iii, Annex II | 4170 | 726 | 46.2 |  |
| `rg_018` | 4 | 4 | PASS | Annex III.7.b, Article 7.2, Article 97.2, Article 6.2 | Article 7.1 | 4053 | 533 | 49.0 |  |
| `rg_019` | 4 | 4 | PASS | Article 3.60, Article 50.4 | Article 3.60 | 210 | 492 | 8.8 |  |
| `rg_020` | 3 | 3 | PASS | Article 74.12, Article 78.3 | Article 74.12 | 1490 | 611 | 24.9 |  |
| `rg_021` | 4 | 4 | PASS | Article 15.4, Article 16, Article 13.3, Article 17.1, Article 9.2, Article 43.4, Article 42.2 | Article 15.1 | 3454 | 693 | 37.2 |  |
| `rg_022` | 4 | 4 | PASS | Article 6, Article 5, Article 50, Article 51, Article 52, Annex I, Annex III, Article 53, Article 54, Article 55, Article 56 | — | 702 | 790 | 7.5 |  |
| `rg_023` | 2 | 2 | PASS | Article 55.1, Article 51.1, Article 53.2 | Article 51.1 | 961 | 681 | 7.6 |  |
| `rg_024` | 3 | 3 | PASS | Article 6.2, Annex III.3.c, Article 49.4, Annex I | Article 6.2, Annex III | 3317 | 687 | 33.7 |  |
| `rg_025` | 4 | 4 | PASS | Article 25.1, Article 16 | Article 25.1 | 785 | 711 | 1.2 |  |
| `rg_026` | 3 | 3 | PASS | Article 6.2, Annex III.6.d, Annex I.5 | Article 6.2 | 2556 | 612 | 39.4 |  |
| `rg_027` | 4 | 4 | PASS | Article 6.3, Article 50.1, Annex III.8 | Article 50.2 | 493 | 583 | 2.3 |  |
| `rg_028` | 4 | 4 | PASS | Article 1 | Article 1 | 1134 | 509 | 12.4 |  |
| `rg_029` | 3 | 3 | PASS | Article 6.2, Annex III.5.d | — | 707 | 541 | 0.7 |  |
| `rg_030` | 1 | 1 | PASS | Article 60.4.a, Article 57.5, Article 58.2, Article 76.2 | Article 76.2 | 1141 | 347 | 33.9 |  |
| `rg_031` | 4 | 4 | PASS | Article 6.3.a, Article 49.2, Annex III.7.b | Article 6.3.a | 825 | 715 | 0.8 |  |
| `rg_032` | 3 | 3 | PASS | Article 6.3, Annex III | Article 6.3 | 477 | 609 | 0.8 |  |
| `rg_033` | 4 | 4 | PASS | Article 65.5 | Article 65 | 508 | 528 | 2.0 |  |
| `rg_034` | 4 | 4 | PASS | Article 101.1, Article 99.7, Article 91.3, Article 92.1, Article 56.9 | Article 101.3 | 1739 | 321 | 34.8 |  |
| `rg_035` | 3 | 3 | fail | Article 20.1, Article 80.2, Article 99.7, Article 81.1, Article 79.2 | Article 80.2 | 3506 | 654 | 57.7 | draw-dependent |
| `rg_036` | 0 | 3 | PASS | Article 10.4 | Article 42.1 | 793 | 605 | 54.6 | **all failed** |
| `rg_037` | 0 | 6 | fail | Article 6.2, Article 49.4 | Annex VIII.a | 1137 | 795 | 43.8 | **all failed**; draw-dependent |
| `rg_038` | 4 | 4 | PASS | Article 3.55, Article 57.5 | Article 57.1 | 345 | 748 | 8.5 |  |
| `rg_039` | 3 | 3 | PASS | Article 50.4 | Article 50.4 | 600 | 590 | 1.3 |  |
| `rg_040` | 2 | 2 | PASS | Article 44.1 | Article 44.1 | 808 | 607 | 7.5 |  |
| `rg_041` | 3 | 3 | PASS | Article 11.1, Annex IV.2 | Article 11.1 | 362 | 535 | 8.1 |  |
| `rg_042` | 4 | 4 | PASS | Article 26.7 | Article 26.7 | 493 | 553 | 1.4 |  |
| `rg_043` | 6 | 6 | PASS | Article 10.5 | Article 10.5 | 986 | 1007 | 1.3 |  |
| `rg_044` | 4 | 4 | PASS | Annex III.7.b, Article 60.4.c, Article 71.4, Article 57.5, Article 75.3 | Article 60.4 | 3110 | 747 | 50.0 |  |
| `rg_045` | 4 | 4 | fail | Article 26.5, Article 79.2, Article 20.2 | Article 26.5 | 1317 | 371 | 25.3 |  |
| `rg_046` | 6 | 6 | PASS | Article 13.3, Article 9.5 | Article 13.3 | 2759 | 985 | 34.8 |  |
| `rg_047` | 3 | 3 | PASS | Article 20.1, Article 16, Article 79.2, Article 44.3 | Article 20.1 | 1465 | 503 | 26.2 |  |
| `rg_048` | 3 | 3 | PASS | Article 3.21, Article 43.3, Annex VI.3, Annex VII.4 | Article 3.20, Article 3.21 | 1028 | 383 | 28.0 |  |
| `rg_049` | 3 | 3 | PASS | Article 95.2 | Article 95.1, Article 95.2 | 1822 | 433 | 21.8 |  |
| `rg_050` | 2 | 2 | PASS | Annex III.5.b, Article 6.3.d, Article 49 | Annex III.5.b | 1667 | 319 | 34.7 |  |
| `rg_051` | 3 | 3 | PASS | Article 22.3, Article 13.3, Article 49.2, Annex VIII.10, Article 9.2 | Article 22.1 | 4543 | 825 | 40.2 |  |
| `rg_052` | 6 | 6 | PASS | Article 17.1, Article 9.2, Article 72.4, Article 40.2, Article 73.6 | Article 17.1 | 3138 | 959 | 32.0 |  |
| `rg_053` | 4 | 4 | PASS | Article 55.1, Article 51.1, Annex XIII, Article 53.1, Annex XI.2 | Article 55.1 | 2695 | 770 | 35.5 |  |
| `rg_054` | 4 | 4 | PASS | Article 79.6, Article 5.1.h, Article 50 | Article 79.6 | 1104 | 534 | 19.6 |  |
| `rg_055` | 3 | 3 | PASS | Article 5.1.h, Annex II, Article 27.1, Article 49.4 | Article 5.1.h | 3369 | 822 | 45.0 |  |
| `rg_056` | 3 | 3 | PASS | Article 32, Article 31.5 | Article 32 | 1863 | 551 | 28.6 |  |
| `rg_057` | 3 | 3 | PASS | Article 85 | Article 85.1 | 942 | 486 | 21.2 |  |
| `rg_058` | 5 | 5 | fail | Article 50.2, Article 56.9, Article 98 | Article 50.2 | 1750 | 858 | 26.9 |  |
| `rg_059` | 4 | 4 | PASS | Article 64.2, Article 98.2, Article 68.3, Article 90.1, Article 74.12 | Article 68 | 2880 | 985 | 33.1 |  |
| `rg_060` | 3 | 3 | PASS | Article 60.4.c, Article 73.2, Article 3.57 | Article 60.7 | 1257 | 534 | 31.3 |  |
| `rg_061` | 2 | 2 | PASS | Article 88.1, Article 51.1, Article 94, Article 75.1 | Article 88.1, Article 75.1 | 882 | 483 | 29.5 |  |
| `rg_062` | 2 | 3 | PASS | Article 79.1, Article 24.4 | Article 24.4 | 1423 | 580 | 29.3 | partial |
| `rg_063` | 6 | 6 | PASS | Article 2.1 | Article 2.1 | 1865 | 718 | 15.7 |  |
| `rg_064` | 1 | 1 | PASS | Article 60.4.e, Annex III | Article 60.4.e | 1794 | 502 | 20.5 |  |
| `rg_065` | 3 | 3 | PASS | Article 99.5, Article 5.1.d, Article 16, Article 23.6, Article 92.1 | Article 99 | 2217 | 822 | 37.8 |  |
| `rg_066` | 3 | 3 | fail | Article 49.4, Annex III.7.b, Article 71.1, Article 74.8, Annex VIII.12 | Article 71, Annex VIII | 4387 | 660 | 47.4 |  |
| `rg_067` | 3 | 3 | PASS | Article 55.1, Article 53.2, Article 51.1, Article 3.65, Annex XIII | Article 51.1, Annex XIII | 2633 | 673 | 34.5 |  |
| `rg_068` | 2 | 2 | PASS | Article 10.3, Article 26.1, Article 42.1, Article 13.3 | Article 26.4 | 1611 | 479 | 21.8 |  |
| `rg_069` | 2 | 3 | fail | Article 24.4, Article 23.2, Article 47.1, Article 16, Article 11.1 | Article 24.3, Article 23.4 | 4411 | 600 | 42.7 | partial |
| `rg_070` | 4 | 4 | PASS | Article 6.1, Annex I.11, Article 49.3 | Article 6.1 | 3311 | 697 | 38.2 |  |
| `rg_071` | 3 | 3 | PASS | Article 50.4 | — | 3078 | 754 | 18.8 |  |
| `rg_072` | 4 | 4 | PASS | Article 6.2, Annex I.2, Annex VII.4, Article 41.1 | Article 6.1, Annex I.a.2 | 2672 | 757 | 34.8 |  |
| `rg_073` | 4 | 4 | PASS | Article 6.1, Annex I.4, Annex VII.4, Article 41.1 | Article 6.1, Annex I | 2473 | 625 | 39.6 |  |
| `rg_074` | 4 | 4 | PASS | Article 5.1.f, Article 50.3, Annex III.1.c | Annex III.1.c, Article 5.1.f | 321 | 740 | 8.4 |  |
| `rg_075` | 3 | 3 | PASS | Article 50.4, Article 3.60, Article 6.3.d, Annex III.7.d | Article 50.4 | 2816 | 587 | 34.5 |  |
| `rg_076` | 1 | 1 | PASS | Article 3.2 | Article 3.2 | 103 | 160 | 1.5 |  |
| `rg_077` | 3 | 3 | PASS | Article 6.2, Annex III.7.b, Article 49.4, Article 71.4, Article 74, Annex VIII.12 | Article 49.2 | 2767 | 611 | 33.9 |  |
| `rg_078` | 3 | 3 | PASS | Article 60.4.i, Article 57.5, Annex III.7.b, Article 61.1, Annex I | Article 61.1 | 3072 | 723 | 36.9 |  |
| `rg_079` | 4 | 4 | PASS | Article 79.1, Article 20.2, Article 44.3, Article 73.6 | Article 20.2 | 3409 | 889 | 41.4 |  |
| `rg_080` | 4 | 4 | PASS | Article 50.4 | Article 50.4 | 2226 | 886 | 16.3 |  |
| `rg_081` | 4 | 4 | PASS | Article 6.2, Article 50.2, Annex III.7.d, Annex I.19, Article 5.1.d | Article 6 | 2253 | 582 | 40.5 |  |
| `rg_082` | 3 | 3 | PASS | Article 24.4, Article 79.2 | Article 24.3 | 2304 | 671 | 20.0 |  |
| `rg_083` | 4 | 4 | PASS | Annex III.7.b, Annex I.5, Article 6.2, Article 71.1, Article 49.3 | Article 6.2 | 1770 | 703 | 28.7 |  |
| `rg_084` | 3 | 3 | PASS | Article 6.2, Annex I.19, Annex III.5.d, Article 25.1.c | — | 2934 | 677 | 34.9 |  |
| `rg_085` | 1 | 4 | PASS | Article 6.2, Article 5.1.d, Article 50.4, Annex III.7.b, Annex I | Article 6.1, Article 6.2, Annex III.1.a | 574 | 739 | 70.9 | partial |
| `rg_086` | 3 | 3 | PASS | Article 1.2, Article 53.1, Annex XI.2, Article 40.2, Article 112.6 | — | 2295 | 708 | 35.8 |  |
| `rg_087` | 3 | 4 | PASS | Article 9.5, Article 3.65, Article 5.1.d, Article 55.1, Article 51.1 | Article 9 | 3166 | 803 | 39.7 | partial |
| `rg_088` | 0 | 3 | fail | Annex I.19, Annex III.7.b, Article 6.1, Article 25.2, Article 8.2 | Article 26.1, Article 26.6 | 2815 | 678 | 53.6 | **all failed** |
| `rg_089` | 2 | 3 | PASS | Annex III.5.d, Article 6.2, Article 5.1.d, Annex I.5, Article 50.1 | Article 6.3.a | 2867 | 597 | 44.1 | partial |
| `rg_090` | 4 | 4 | PASS | Article 26.6, Article 51.3, Article 3.4, Annex I.5, Article 25.1 | Article 26.6 | 2267 | 786 | 35.9 |  |
| `rg_091` | 1 | 3 | PASS | Article 6.1, Annex III.5.d, Annex I.11, Article 43.1, Article 9 | Article 6.1 | 2789 | 557 | 36.1 | partial |
| `rg_092` | 3 | 3 | PASS | Annex I, Annex II, Annex III | Annex I, Annex II, Annex III | 1379 | 842 | 35.7 |  |
| `rg_093` | 3 | 3 | PASS | Article 6.3.d, Article 27.1, Annex III.7.b, Annex I, Article 49.3 | Annex III.7.b | 3253 | 565 | 40.7 |  |
| `rg_094` | 5 | 5 | PASS | Article 53.1, Annex XII.1, Article 51.1, Annex IV.2 | Article 53.1.b | 2121 | 561 | 24.5 |  |
| `rg_095` | 3 | 3 | PASS | Article 72.2, Article 25.4, Article 17.1, Annex I.20 | Article 72.1, Article 72.2 | 3581 | 722 | 43.2 |  |
| `rg_096` | 3 | 3 | PASS | Article 6.2, Article 6.3, Annex III.5.c, Article 7.2, Article 112.2 | Article 6.2, Annex III | 2837 | 596 | 33.5 |  |
| `rg_097` | 2 | 2 | PASS | Article 6, Article 7, Annex III, Annex I, Article 97 | Annex III, Article 6.2 | 3258 | 647 | 36.2 |  |
| `rg_098` | 1 | 1 | PASS | Annex VII.5, Article 7.2, Annex III.6.d, Article 17.1 | — | 1448 | 520 | 28.8 |  |
| `rg_099` | 4 | 4 | PASS | Article 53.1, Article 55.1, Article 51.1, Article 25.4, Article 56.2, Annex XI.2, Article 3.65 | Article 55.1.a | 3960 | 724 | 56.4 |  |
| `rg_100` | 4 | 4 | PASS | Article 13.3, Article 25.1.c, Article 7.2, Article 8.2, Article 50.1 | Article 6.3 | 5308 | 699 | 68.1 |  |
| `rg_101` | 3 | 3 | PASS | Article 5.1.h, Annex II, Article 27.1, Article 49.4, Article 46.2 | Article 5.3 | 3174 | 620 | 37.9 |  |
| `rg_102` | 4 | 4 | PASS | Annex III.5.d, Article 6.2, Article 27.1, Article 13.3 | Article 27.1 | 3874 | 686 | 53.3 |  |
| `rg_103` | 3 | 4 | PASS | Article 50.4, Article 6.3.d, Article 5.1.h, Annex III.3.d, Article 3.46 | Article 50.4 | 3629 | 727 | 47.6 | partial |
| `rg_104` | 4 | 4 | PASS | Article 6.2, Article 111.1, Article 53.1, Article 113.3, Article 51.1 | Article 111.2, Article 111.3 | 3408 | 641 | 51.7 |  |
| `rg_105` | 2 | 2 | PASS | Annex X, Article 111.1, Article 5.1.d, Article 113 | Article 111.1, Annex X | 2043 | 625 | 26.3 |  |
| `rg_106` | 3 | 3 | PASS | Article 5.1.c, Annex III.6.d | Annex III.6 | 2737 | 781 | 31.9 |  |
| `rg_107` | 4 | 4 | PASS | Article 5.1.d, Article 6.2, Article 50.1, Annex I.20, Annex III.3 | Annex III.3.c, Article 6.3 | 3910 | 849 | 41.9 |  |
| `rg_108` | 3 | 3 | PASS | Annex I.1, Article 6.1, Article 43.3, Annex VII.4, Article 71.1 | Article 6.1, Article 43.3 | 3295 | 743 | 54.7 |  |
| `rg_109` | 3 | 3 | PASS | Article 6.1, Annex I.20, Article 43.3, Article 41.1, Annex VII.4 | Article 43.3 | 2822 | 689 | 43.8 |  |
| `rg_110` | 4 | 4 | PASS | Article 27.1, Article 6.3.d, Article 25.4, Article 50.1, Annex III.2 | Annex III.2, Article 25.1.a, Article 27.1 | 4591 | 676 | 57.5 |  |

---

## 5. The fixed defect and its projected board

4 rows (`rg_036`, `rg_037`, `rg_085`, `rg_092`) fell to the deterministic Stage-1 draft (wrapper degenerate one-token completion → the Bedrock fallback leg was dead in that environment → tail repair failed). Two of them shipped an answer thinner than the one the engine had already given on turn 1. **R420** makes the truncation guard keep the prior answer instead.

| row | draft scored | turn-1 answer scored | head(s) restored |
| :--- | ---: | ---: | :--- |
| `rg_036` | 0/3 | **2/3** | Article 42 |
| `rg_037` | 0/6 | **6/6** | Annex VIII |

| variant | ans loose | ans strict |
| :--- | ---: | ---: |
| as measured | 94.15% | 90.91% |
| with the R420 floor (+8 criteria, +1 strict row, measured on the turn-1 answers) | **96.28%** | **91.82%** |

---

## 6. Artifacts and how to reproduce

| path | what |
| :--- | :--- |
| `evals/bench/results/official-r419-hard-hard.ckpt.jsonl` | the 110 live rows (gitignored) |
| `docs/measurements/r419/judge-cache-r419-qwen235.jsonl` | the judged verdicts, 3 reps each |
| `docs/measurements/r388/score-r419-hard-hard.json` | the board this report re-derives |
| `docs/measurements/r388/score-r419-priorfloor-hard.json` | the turn-1 re-judge behind R420 |
| `docs/measurements/r419/live_hard_read.json` | the judge-free half (leg mix, heads, latency) |
| `docs/reports/r419-live-hard-questions-and-answers.md` | every question, answer and verdict |
| `docs/measurements/r419/CHECKPOINT.md` | the round record |

```bash
.venv/Scripts/python.exe -m docs.measurements.r419.build_metrics_report
```
