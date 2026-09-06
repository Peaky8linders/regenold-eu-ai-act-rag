# R384 — Live re-evaluation of the Regenold round: full metrics

**Date:** 2026-09-06
**Corpus:** the 110 official Regenold questions, as sent in the 2026-07-23/24 evaluator round
**Transport:** cloudflared tunnel (`wrapper.antifragile-ai.net`), Claude Max
**Judge:** `evals.judge.grounded`, `claude-sonnet-5`, `--provider wrapper`
**Artefacts:** `docs/measurements/r384/`

---

## 0. How to read this document

Two things must be said before any number, because they bound what the numbers mean.

**(a) These are not the official axes.** The evaluator has never published its per-question
correctness criteria, its expected-reference sets, or its reference answers. `gold_coverage` on
this run is **0.0**. Our judge grades free-form substance against the *verbatim Regulation text*.
That is a legitimate instrument and it is the best available, but it measures something adjacent
to what the official report measures. Every judged number below is a **proxy**, and is labelled
as one. The only numbers directly comparable to the official scorecard are the deterministic ones
(length, reference count, tone, latency).

**(b) The judge run is partial.** 10 of 110 rows errored on `wrapper_error: api_status_500` — all
of them the tail (`rg_101`–`rg_110`), where the wrapper hit the shared Claude Max quota. The R381
partial-failure guard caught this and refused to let the raw rate stand:

> `!! PARTIAL JUDGE FAILURE on: answer_correctness 10/110, citation_faithfulness 11/110,
> reference_correctness 10/110. The printed pass_rate DIVIDES BY ALL ROWS...`

So the honest figures are the **over-non-error** column on n=100, and the raw column is shown
only to make the gap visible.

---

## 1. Judge scorecard (sonnet-5, verbatim-Act grounded)

| axis | raw (n=110) | **over non-error (n=100)** | pass / fail / err |
| :--- | ---: | ---: | :--- |
| Answer correctness | 0.7909 | **0.8700** | 87 / 13 / 10 |
| Reference correctness | 0.4364 | **0.4800** | 48 / 52 / 10 |
| Citation faithfulness | 0.8636 | **0.9596** | 95 / 4 / 11 |

Reference sub-metrics: **precision 0.7441, recall 0.9447, F1 0.8325**.
⚠ With `gold_coverage = 0.0`, **recall is the judge model's recall** while **precision is
text-grounded** against verbatim provisions. Read them asymmetrically; do not average them.

**The shape is unambiguous: the answers are right and the references are wrong.** Answer
correctness 0.87 and citation faithfulness 0.96 against reference correctness 0.48 means we are
not fabricating law — every citation we emit is supported by what the answer says — but the *set*
of provisions we emit is wrong roughly half the time. Recall 0.94 with precision 0.74 localises it
further: we are not missing the governing provision, we are **shipping extra ones**.

---

## 2. Deterministic metrics, paired THEN vs NOW

Same 110 questions. THEN = the answers as served in the 2026-07-23/24 round, recovered from the
production audit chain. NOW = today, over the tunnel. **83 rows wrapper-served, 27 deterministic,
0 Bedrock** — a clean measurement.

| metric | THEN | NOW | delta |
| :--- | ---: | ---: | :--- |
| answer chars (mean) | 1042 | 1079 | +3.6 % |
| answer chars (median) | 971 | 1141 | +17.5 % |
| sentences | 3.65 | 3.55 | −0.1 |
| references / answer | 2.95 | **2.65** | 0.898× |
| Ref Conciseness `min(1, 1.4/P)` | 55.6 | **61.2** | **+5.5** |
| regulatory tone | 100.0 | 100.0 | 0.0 |
| latency p50 / p90 | — | 10.4 s / 19.4 s | — |

40 rows shorter, 55 longer, **p = 0.151** — the aggregate length change is **not significant**.

### The aggregate hides the real story

| difficulty | n | chars THEN → NOW | refs THEN → NOW |
| :--- | ---: | :--- | :--- |
| EASY | 51 | 620 → **926 (+49 %)** | 2.37 → 2.39 |
| HARD | 59 | 1407 → **1212 (−14 %)** | 3.46 → **2.88** |

**Hard answers tightened; easy answers grew by half.** Easy mode is 51 of the 110 and is where
Ans Conciseness carries its −16.0 pp gap to the frontier baseline, so a 49 % length increase there
is pointed the wrong way. This is the single clearest regression in the round.

---

## 3. Why 27 of 110 never reach Stage-2 — and whether Stage-2 earns its cost

27 rows are served by curated authoritative intercepts (R358), which **deliberately skip the
Stage-2 polish**. Splitting every measurement by transport:

| | deterministic (n=27) | Stage-2 (n=83) |
| :--- | ---: | ---: |
| answer correctness (judge) | 0.846 | **0.878** |
| **reference correctness (judge)** | **0.654** | 0.419 |
| **citation faithfulness (judge)** | **1.000** | 0.945 |
| mean answer chars | **547** | 1253 |
| mean references | **2.48** | 2.71 |
| mean latency | **2.3 s** | 13.0 s |

**Stage-2 buys +3.2 pp of answer correctness and costs 23.5 pp of reference correctness, 5.5 pp of
citation faithfulness, 2.3× the length and 5.7× the latency.**

On the official rubric that trade is close to even at best: answer correctness carries 0.105–0.116
pp of Overall per pp, while reference correctness (0.105 + 0.137) plus conciseness (0.181 + 0.186)
plus speed (0.107) all move the other way.

⚠ **This is not a controlled comparison and must not be quoted as one.** The assignment is not
random: curated intercepts exist precisely for questions we already have an authoritative answer
for, which is a favourable subset. The controlled experiment — running the *same* questions both
ways with the intercept disabled — has not been run. What the table does establish is that the
deterministic path is not a degraded fallback: on the questions it covers it is **better on two of
three judged axes, and dramatically cheaper**.

**Recommendation:** do not narrow the deterministic path. Run the controlled test before widening
it. And treat "Stage-2 improves answers" as an assumption now under active doubt rather than a
settled fact.

---

## 4. Root causes found, with fixes

### 4.1 SHIPPED — `rg_020` answered the opposite of Article 74(12)

The question misspells its own anchor: *"Should market **surveilance** authorities be provided
with remote access to documentations and data sets…"* (one `l`). Our answer said *"the Act does
not oblige providers to give market surveillance authorities open remote access to those data
sets"*. Article 74(12) grants exactly that.

Two independent defects had to line up:

1. **The engine anchor map lacked the typo variant** that `scope.py:1764` has carried since R268 —
   with a comment describing this exact failure. Matching is ASCII-literal substring, so
   `_deterministic_parse` returned `['Annex IV','Art. 6','Art. 26','Art. 10','Art. 46']` and
   Article 74 never entered retrieval. This is the R367 rule paid for a second time: *a scope
   anchor is not enough on its own — the route only FRONTS an anchor already in candidates;
   retrieval is seeded from the ENGINE map.*
2. **The KB summary described only paragraph 13** (source-code access on reasoned request) and
   never mentioned paragraph 12, so the model generalised the narrow power into "no standing
   entitlement". Same class as the R379 Annex X finding: what a summary omits is as load-bearing
   as what it asserts.

**Both fixed and pinned** (`tests/test_r384_rg020_market_surveillance.py`, 8 tests). Retrieval now
returns `Art. 74` at rank 0 and the context carries the operative rule verbatim; citations
tightened from `['Article 26','Article 11','Annex IV']` to `['Article 74','Article 6']`.
Blast radius one row — `rg_030/035/079` spell it correctly and are byte-unaffected.

### 4.2 NOT YET SHIPPED — the granularity pass deletes every sub-point citation

**This is the largest single finding of the round, and it is close to free to fix.**

Measured on the 110 rows: `_surface_prose_subpoints` (`regenold.py:4532`) correctly adds **79
sub-point citations across 47 rows**. Thirty-eight lines later `_apply_ref_granularity`
(`regenold.py:3700`, mode `auto`) **deletes 79 of 79. Net survivors: zero.**

The mechanism is structural, not sampling. `_surface_prose_subpoints` only inserts a leaf whose
parent is already cited, so every leaf it adds is by construction in a *mixed* cluster — and
`auto` mode keeps the leaf only when the **user's question literally contains the coordinate**.
Measured: **8 of 110 official questions do (7.3 %)**. On the other 102, every leaf is deleted.

Reproduced independently — identical references, identical prose, only the question differs:

```
input                        ['Article 6', 'Article 6.2', 'Annex III']
q = "What makes a system high-risk?"        -> ['Article 6', 'Annex III']
q = "Does Article 6(2) make Annex III ...?" -> ['Article 6.2', 'Annex III']
```

**The sharpest form of it:** `_collapse_parent_when_subpoint_cited` on the *same input* returns
`['Article 6.2', 'Annex III']` — **same count, opposite grain, the better one**. Granularity runs
at `:10187` and collapse at `:10603`, so granularity wins and picks the Ref-Strict-worse level.
That also starves R381's parent-collapse win: only 4 of 292 refs (1.4 %) are still redundant by
the time collapse runs.

Current state: **40 of 292 references (13.7 %) carry sub-point grain**; 30 of 110 rows have any.
But **57 rows name a sub-point coordinate in their own prose and ship none**. All 79 candidate
sub-points resolve through `provision_text.get_provision_text` — 100 %, zero hallucinated
coordinates. E.g. `Annex IV.1.e` = *"the description of the hardware on which the AI system is
intended to run"*, on `rg_001`, which asks precisely about required hardware. We ship bare
`Annex IV`.

**Why this matters on the official rubric:** Ref Correctness Loose is scored at head level (89.4),
Strict includes sub-points (68.3). A **21.1 pp Loose→Strict gap** is a *grain* problem, and Strict
is one of our two largest deficits (−10.2 pp vs frontier).

**Proposed fix (Variant B):** in `_apply_ref_granularity`'s `auto` branch, let `leaf_signal` also
fire when the **final answer prose** names a sub-point of that head, and substitute **one** leaf
per parent. Projected on all 110 captured rows:

| | current | Variant B | Variant A (all leaves) |
| :--- | ---: | ---: | ---: |
| refs/row | 2.655 | **2.655** | 2.836 |
| Ref Conciseness | 61.15 | **61.15 (+0.00)** | 58.02 (−3.13) |
| sub-point refs | 13.7 % | **33.9 %** | 38.1 % |
| rows with ≥1 sub-point | 30 | **74** | 74 |
| head set lost | — | **0** | 0 |

`gold_dropped_head` delta is **+0 by construction** — the head survives inside the leaf and
`metrics.py:572-574` folds both sides onto heads. Ref Loose unchanged, Ref Conciseness
byte-identical. **The only axis that can move is Ref Strict, and only upward.**

⚠ **The prior rejection of this signal does not bind.** The mode banner (`:3634-3646`) records that
it "LOST exact-string F1 vs head-form gold". That instrument scores every leaf as a miss *by
construction* — the same trap R381 documented for `gold_dropped_exact` ("our probe gold carries
0/208 sub-point grain … penalising the most accurate citation shape the system emits"). The
official axis is the opposite: Ref Strict *"includes subpoints"*.

Ship behind a flag, gate offline on the captured rows (the transform is deterministic).

### 4.3 NOT SHIPPED — over-citation is in the prose, not the reference list

From the judge: precision 0.744, and **every named top failure mode is literally "over-citation"**.
Every wrong reference is head-level (`Article 50`, `Article 51`, `Article 5`, `Article 15`,
`Article 19`, `Annex XI/XII/XIII`) — not one is a sub-point.

The count lever is closed:
* redundancy is exhausted — only 1.4 % of refs are a leaf whose head is also present;
* a cap is refused — AGENTS.md Closed Directions, and R381's powered gate (cap 3 →
  `gold_dropped_head` 37→41 FAIL at n=129);
* **91.8 % of wire refs are named in the shipped prose**, and R274 makes those undroppable.

**The wire list *is* the prose.** Over-citation cannot be fixed by any reference-list transform;
it has to be fixed by stopping the model writing the unasked sentence. That is the
`REGENOLD_SCOPE_STOP_RULE` / `REGENOLD_PROMPT_V3` family, both currently default OFF on
`gold_dropped_head` failures (+1 and +7). Highest leverage available (0.186) and the only path —
but a separate, properly-powered, prompt-side gate. Do not bundle it with the grain fix.

---

## 5. Where we stand against the frontier baseline

The last *officially graded* numbers remain the 2026-08-25 report. This round did not re-grade
them and cannot: without the evaluator's criteria and expected sets, the correctness axes are not
reproducible locally.

| axis (easy) | us, Aug-25 | 2026 frontier + search | gap |
| :--- | ---: | ---: | ---: |
| Ans Correctness Loose | 89.7 | 94.4 | −4.7 |
| Ans Correctness Strict | 81.2 | 89.1 | −7.9 |
| **Ans Conciseness** | 51.9 | 67.9 | **−16.0** |
| Ref Correctness Loose | 89.4 | 96.1 | −6.7 |
| **Ref Correctness Strict** | 68.3 | 78.5 | **−10.2** |
| Ref Conciseness | 50.4 | 51.9 | −1.5 |
| Tone | 99.1 | 100.0 | −0.9 |
| **Speed** | 87.6 | 81.8 | **+5.8** |
| **Overall (geometric mean)** | **75.1** | **80.9** | **−5.8** |

What this round changes, on the axes it *can* measure:

* **Ref Conciseness 55.6 → 61.2** on the same questions (refs 2.95 → 2.65). At 0.186 pp Overall
  per pp, ≈ **+1.0 pp**.
* **Speed**: p50 10.4 s. We already beat the frontier baseline on this axis.
* **Ans Conciseness**: unchanged in aggregate, **worse in easy mode** (+49 % chars) — the largest
  gap got slightly larger where it counts.

Honest projection, Ref Conciseness + Speed only: **75.1 → 76.3 (+1.2 pp)**. The grain fix (§ 4.2)
is projected at a further **+0.7 to +1.6 pp** and would be the first movement on Ref Strict.
Neither closes the −5.8 pp gap on its own; the remaining distance is in Ans Conciseness and Ans
Correctness Strict.

---

## 6. What is not measured

* **Ans/Ref Correctness against the official rubric.** No criteria, no expected sets, no reference
  answers exist outside the evaluator. Everything in § 1 is a verbatim-text proxy.
* **10 rows of the judge run** (`rg_101`–`rg_110`) errored on wrapper 500s and are excluded.
* **The Ans Conciseness formula**, so no length change is projected onto that axis.
* **The hard-mode phases.** In hard mode the route persists the *flattened* query rather than the
  judge's raw turn, so only the single-turn phase is recoverable per question (110/110 single-turn;
  57 hard turn-1; 0 pushback). This round re-ran single-turn only.
* **The controlled deterministic-vs-Stage-2 test** (§ 3) — the honest version of that comparison
  has not been run.
