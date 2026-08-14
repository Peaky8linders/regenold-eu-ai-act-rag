# R330 / R331 — checkpoint

**Date:** 2026-08-14 · **main:** `2188714` · **production:** verified live on `21887144b177`
**Raw arms:** `evals/bench/results/` is **gitignored** — the judged summaries are copied into
`docs/measurements/r330/` so the numbers survive. The full sidecars exist only on the machine
that ran them.

---

## 1. What shipped (7 PRs, all merged, all deployed)

| PR | what |
| --- | --- |
| #339 | the R330 fixes (env guard, 3 gate/emitter fixes, kg_context, UI, speed gates) |
| #340 / #341 | deploy runbook — it documented a hook deleted in R127 |
| #342 | scope: the OOS probe fails safe offline and over-counts live |
| #343 | **the entire R327 semantic layer had never executed** |
| #344 | flip the three gate/emitter fixes ON, after the gate was run |
| #345 | R331 — seat the cross-encoder rerank where the truncation actually happens |

---

## 2. The headline numbers

Live HARD, n=40, Claude Max wrapper, graded by the grounded Sonnet-5 judge vs verbatim Act text.

**TWO post-fix arms, same configuration** (R331's rerank ships OFF), so their spread is
run-to-run variance. Error-adjusted (`pass_rate_over_non_error`):

| axis | before | post-fix A | post-fix B | mean | spread | gain |
| --- | --- | --- | --- | --- | --- | --- |
| **answer_correctness** | 0.6250 | 0.8750 | 0.8205 | **0.8478** | 0.055 | **+0.223** |
| reference_correctness | 0.2368 | 0.3333 | 0.2632 | 0.2983 | 0.070 | +0.062 |
| citation_faithfulness | 0.8000 | 0.8500 | 0.8462 | 0.8481 | 0.004 | +0.048 |

⚠ **The single-arm figures first reported (+0.2500 / +0.1000) were OPTIMISTIC.** The second
arm revised them down. Read the three axes differently:

* **answer_correctness +0.223 — SOLID.** Spread 0.055 sits well inside the gain; both arms
  clear the baseline by a wide margin.
* **citation_faithfulness +0.048 — SOLID.** Spread 0.004, the tightest axis.
* **reference_correctness +0.062 — NOT RESOLVABLE.** The spread (0.070) EXCEEDS the gain and
  arm B (0.2632) is barely above baseline (0.2368). This is the recorded n=40 noise floor:
  identical arms have previously drifted 0.053 and sign-flipped all three ref axes. **Treat
  the reference gain as unproven.**

What survives variance is the deterministic part: july7-265 and july7-259 reproduce
BYTE-IDENTICALLY across both arms, and max refs is 11 -> 5 in both.

Wire metrics across three independent arms:

| arm | mean refs | max refs | latency p50 | mean answer chars |
| --- | --- | --- | --- | --- |
| R329 (before) | 3.30 | **11** | 55.8 s | 1300 |
| R330 (gates ON) | 2.98 | 5 | 39.4 s | 1437 |
| R331 (final, current main) | 3.10 | **5** | **34.6 s** | 1494 |

**Latency −38 %** from R329. The `max 11 references` row that violated the rules PDF's
"minimal set" is gone; run-wide max is 5.

### ⚠ Attribution — do not overclaim this

The post-fix arms carry a **second** change: the operator removed
`REGENOLD_MAX_ANSWER_SENTENCES=4` from the environment. R320 measured that cap at
`answer_correctness −0.143`, so a large share of the +0.25 is plausibly its removal.
Per-row, 11 rows went fail→pass on `answer_correctness` and **8 are rows the gates do not
touch**.

What IS attributable, because it was predicted in advance from static analysis and then
reproduced live **twice**: every gate-target row improved, none regressed on any axis.

| row | before | after (both arms) |
| --- | --- | --- |
| july7-299 | 11 refs / 621 ch, generic four-tier blurb | 2-3 refs, cites Annex III point 7(b) |
| july7-265 | 1 ref / 378 ch "Defines 68 terms…" | 1 ref / **103 ch verbatim Art. 3 definition** |
| july7-259 | 5 refs / 1562 ch | 5 refs / **321 ch** |

july7-265 and july7-259 are **byte-identical across two independent runs** ⇒ deterministic
fixes, not generation noise.

**Verified in production** (`/api/v1/regenold/eu-ai-act/ask`): the july7-299 question returns
`['Article 6', 'Annex III']` and the Annex III point 7(b) content the judge said was missing.

---

## 3. The two findings that were NOT in the brief

### 3.1 The eval instrument was broken (fixed, #339)

R329's `_load_dotenv_once()` put `.env` into `os.environ` at **import time**. It guarded
pytest but not the eval harnesses. `.env` carries BEHAVIOURAL flags next to credentials.

| arm (davidath 476) | Ref Loose | Ref Strict | multi-turn |
| --- | --- | --- | --- |
| code defaults | 0.5971 | 0.4748 | 20/20 |
| `REGENOLD_ROLE_DUTY_NOUN_SEED=1` alone | 0.5971 | 0.4633 | 20/20 |
| the full local `.env` | 0.5735 | 0.4489 | 13/20 |

This presented as a **−0.026 Ref Strict / −45 pp coherence regression across 15 commits that
are byte-neutral**. A worktree at `b47c259` and main-with-env-blanked both reproduce
`0.3545 / 0.5971 / 0.4748 / 20-20` exactly.

`evals/bench/runner.py` now sets `REGENOLD_SKIP_DOTENV=1`; `runner_v2` does the same for
`--local --probe-oos`.

### 3.2 The entire R327 semantic layer had never executed (fixed, #343)

`_render_supplementary_sections` is the **only** `render_kg_context` call site in `app/`, and
it omitted the `question` argument. `kg_context._render_semantic_layers` opens with
`if not question: return []`.

So `REGENOLD_GRAPH_SEMANTIC_LAYERS` **and** `REGENOLD_SEMANTIC_GLOSS` emitted **zero** Stage-2
context on every request since R327 — while the layers flag read ON, sat in
`_engine_cache_key`, and was documented as active in CLAUDE.md.

⚠ Its own success evidence ("citation faithfulness 0.900 → 0.960") was collected **through the
broken path**, so both arms of that measurement were the same arm. Treat as unverified.

Wiring repaired; flag flipped to **default OFF** in the same commit so production is unchanged.
**It is now a real, untried lever.**

---

## 4. Corrections to the record (all measured)

1. **"Shortening buys Speed for free"** — no. R320's paired A/B on identical generations:
   `answer_correctness −0.143` (1 up / 4 down). The cap is the wrong instrument; the judge's
   own conciseness failures are *redundancy* and *scope creep*.
2. **`complex_thinking_tokens=4000` drives Speed** — measured **backwards**. Complex/4000 p50
   26.9 s vs simple/0 41.8 s. Speed is **transport**: a 5-token wrapper request costs 12–17 s,
   identical for Sonnet-5 and Opus-5 ⇒ process-spawn bound.
   `docs/R329-SCORECARD-VS-FRONTIER.md:127-128` still states this wrongly.
3. **Production leaks scope** — WRONG, retracted. Production is **12/12 on adversarial**
   (injection, base64/translate-then-follow obfuscation, multi-turn scope drift, nonsense).
   The 10 "leaks" were chit-chat + two legally-correct adjacent-regulation answers. Do **not**
   set `REGENOLD_TOPIC_FILTER` to "fix" it — R255 disabled that filter because it
   false-positived on genuine keyword-less AI Act questions.
4. **`/app` 404 on production** — WRONG, retracted. `api.antifragile-ai.net` is a *different*
   app (456 routes). The real host serves `/app` 200. "TWO app copies" gotcha.

---

## 5. Regression guards, current state

* **davidath 476** with all current defaults: **byte-identical** to the documented baseline —
  Ans Strict 0.3545, Ref Loose 0.5971, Ref Strict 0.4748, Ref Con 0.4316, Tone 1.0,
  multi-turn 20/20. (Operator directive: davidath + the 276-runner are **OFF as merge gates**.)
* **Unit tests:** 479 passed on the broad regression sweep, 0 failures.
  ⚠ The FULL suite is red (~49) on clean `main` from httpx-pool saturation — **pre-existing**,
  all pass file-scoped. `test_r115_followups` confirmed failing on clean HEAD in isolation.
* **OOS scope probe, live production:** 41/51, 12/12 adversarial. `hard_fail: True` is a
  harness artefact — see §4.3.

---

## 6. Open / next

1. **`REGENOLD_GRAPH_SEMANTIC_LAYERS`** — repaired and untried. Feeds sub-provision vector
   search into Stage-2 grounding, i.e. straight at Ans Strict, the biggest gap. Gate on
   `ab_judge` (answer axes), **not** `easyhard_ab`. Watch p50 — it issues live Aura queries.
2. **`REGENOLD_COHERE_RERANK`** (R331) — seated at the `max_refs=8` truncation, default OFF.
   Prove it fires with `rerank_stats()` before reading any number: three R329 placements all
   read +0.0000 because they never ran.
3. **Answer length is creeping** — 1300 → 1494 mean chars across the arms, from the sentence-cap
   removal. Ans Conciseness is the **only** axis we beat frontier on. Watch it.
4. **Railway flag reconciliation** — 8 `.env` flags differ from code defaults
   (`ROLE_DUTY_NOUN_SEED`, `GRAPH_2HOP`, `R89A_FORCE_APPEND`, `DYNAMIC_GROUNDING`,
   `GRAPH_AWARE`, `VECTOR_RERANK`, `QA_LENGTH_CAP`). Operator confirmed
   `MAX_ANSWER_SENTENCES` is gone from both. `REGENOLD_CLAUSE_COMPLETE` and
   `REGENOLD_RUSHDB_HYBRID` have **no string literal anywhere in `app/`** — inert, delete them.
5. **`app/graph/client.py`** — any Cypher error is still recorded as a graph **success**
   (`_bounded_execute_read` takes its success branch on an exception). `execute_read_strict` is
   referenced by a getattr probe and a test double but **has never existed**. Own commit.
6. **Third judged arm** (`r331-hard-final-grounded`) was still running at checkpoint time.

---

## 7. Traps this round paid for (do not repeat)

* A worktree baseline has **no `.env`**, and post-R329 `.env` changes behaviour ⇒ a
  worktree-vs-main diff now confounds in **both** directions. Diff in place, with the env
  explicitly controlled.
* The deterministic OOS probe **fails safe by construction**: an anchor-less question goes to
  the LLM scope gate and `regenold.py` records that "with no LLM wired it fails soft to the
  generic decline". Offline scope runs prove nothing. Probe the deployed endpoint.
* `evals/bench/results/` is gitignored — copy judged summaries out before you lose them.
* Two agents on one working tree: check `git status` for files you did not touch before
  `git add`. R330 and R331 both edited `_render_supplementary_sections` in the same session.
