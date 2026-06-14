# R118 — Antifragile live re-measurement + MedTech multi-turn eval + Opus 4.8 usage

**Date:** 2026-06-15
**Branch:** `r118-antifragile-live`
**Deployed commit measured:** `d8e6115` (Railway production, `provider=openai_wrapper`,
`model=claude-sonnet-4-6`, `complex_model=claude-opus-4-8`, Neo4j `kb_version=v17`).
**Endpoint:** `https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask`
(client → Railway → Cloudflare named tunnel → local Claude Max wrapper → Claude).

This round (1) re-extracted the Antifragile expert-review ground truth from the
`.docx`, (2) ran the 20 questions LIVE against the deployed wire and scored them
on the Regenold rubric + each expert-flagged mistake, (3) built + ran a fresh
**MedTech / life-sciences multi-turn** eval, and (4) audited + optimised the
**Opus 4.8** Stage-2 usage. Every code change is env-gated + davidath-neutral.

---

## 0. Executive summary

* **The reference axes are strong on the live wire.** Antifragile-20 LIVE:
  **Ref Loose 0.646 / Ref Strict 0.718 / Tone 1.0 / Ans Strict 0.482 (vs gold)
  / keyword recall 0.51**. Stage-2 polish fired on 20/20; Opus 4.8 fired on 5/20
  (the multi-phrase questions).
* **43% of the expert-flagged mistakes are now resolved** (16/37 by the
  programmatic proxy). The expert read confirms the load-bearing legal errors
  from the original review are fixed: the *"social scoring by public
  authorities"* factual error (q01/q02), the provider/deployer role error
  (q05), the generic-99(1)-instead-of-99(4) penalty omission (q09), and the
  irrelevant citations (q02 Annex II/Art 27, q04 Art 25, q06).
* **The #1 remaining gap is multi-part answer truncation** — q01 announces
  "four tiers" but delivers only tier 1; q03 "two routes" → one; q12/q13/q15
  drop the high-risk / transparency layers. This drops both answer completeness
  AND the citations for the missing parts (q01 Ref Loose 0.17, q03 0.33). When
  the answer is NOT truncated (q04/q05/q06) it scores Ref Loose 1.0. Notably
  q13 truncates **even on the Opus path** → this is a Stage-2 generation /
  over-compression issue, not a model-capability one.
* **Latency is the worst-scoring production axis: p50 22.8 s, p95 65 s** (one
  row 65 s). This is the Stage-2-via-tunnel cost, not the engine.
* **Opus 4.8 fires on the wrong discriminator.** The audit (full report:
  [`R118-opus48-usage-audit.md`](R118-opus48-usage-audit.md)) found Opus 4.8 is
  selected by *sentence count* (`_is_multi_phrase`), not regulatory difficulty —
  all 5 Opus routes on the 20 questions came through "the user wrote two
  sentences", and ZERO through the five difficulty regexes. Genuinely-hard
  single-sentence questions (q12 carve-out, q15 biometric triage, q19 workplace
  emotion, q20 conformity) get the weaker Sonnet. **R118 ships REC-1**
  (env-gated gate widening, fixes the `always prohibit*ed*` bug) + **REC-4**
  (Anthropic-SDK `max_tokens` floor parity).

---

## Part A — Antifragile ground-truth extraction (the `.docx` deep-dive)

Source: `Antifragile AI Review Questions and Answers.docx` — 20 EU-AI-Act Q&A,
each carrying the AI's original ("Lexy") answer, its citations, and an EU-law
expert's verdict + the specific mistakes flagged. No tables / no Word comments /
no tracked changes — all inline. The companion `AntifragileAI feedback.pdf` is
product-UX feedback (templates, helper sizing, save errors), not Q&A-correctness.

The extraction is encoded machine-readably in
[`evals/regenold/antifragile_groundtruth.py`](../../evals/regenold/antifragile_groundtruth.py)
— per question: `gold_refs` (corrected reference set), a synthesised concise
`gold_answer`, `expected_keywords`, the original `lexy_refs`, and a
machine-checkable `mistakes` list (each with `verify.present` / `verify.absent`
substrings + `ref_present` / `ref_absent`).

### Expert verdict distribution (original answers)

| Verdict | Questions |
| ------- | --------- |
| Correct | q08, q10, q13, q17, q19 |
| Correct substance, wrong sub-citation | q11 (Annex IV.2.a→1(e)), q12 (Annex III.5→III.1(c); Art 50→50(3)), q16 (Art 113 irrelevant) |
| Mostly correct, omissions | q03 (Annex I conformity + Art 6(3) carve-outs) |
| Half-right | q02, q04, q06, q15, q18 |
| Correct rule, generic application | q14 (no Art 43(3)), q20 (no Art 14/72) |
| Wrong by omission | q09 (99(1) instead of 99(4)) |
| Partially wrong + incomplete + error | q01 (only 1 tier; 5/8 prohibitions; "public authorities" error) |
| Wrong / topic-shift | q07 (answered GPAI authrep instead of guiding principles) |

### Recurring mistake taxonomy (the expert's own framing)

1. **Incomplete closed-set enumeration** (q01 5/8 prohibitions, q02 3/8).
2. **Factual error — "social scoring *by public authorities*"** (q01, q02) —
   Art 5(1)(c) has no public-authority limit in the final Regulation.
3. **Provider/deployer role confusion** (q05, q18).
4. **Irrelevant / tangential citations** (q02 Annex II + Art 27, q04 Art 25,
   q06 all-high-risk cites).
5. **Wrong sub-citations** (q11, q12, q13 contradictory Annex III.5).
6. **Missing tier / route** (q01 GPAI, q03/q04 Annex I).
7. **Generic rule, no case application** (q14, q20).
8. **Wrong paragraph / missing specificity** (q09 99(1) vs 99(4)).

---

## Part B — Live measurement vs ground truth (Antifragile-20)

Runner: [`evals/regenold/antifragile_live.py`](../../evals/regenold/antifragile_live.py)
(throttled, retry-wrapped, `?include_reasoning=true`). Sidecar:
`.evalout/r118/live_r118-af.json`.

### Aggregate (n=20, all HTTP 200)

| Axis | Value |
| ---- | ----- |
| Ans Correctness Loose (Jaccard vs gold) | 0.337 |
| Ans Correctness Strict (recall vs gold) | **0.482** |
| Ans Correctness F1 | 0.493 |
| Ans Conciseness | 0.700 |
| **Ref Correctness Loose** | **0.646** |
| **Ref Correctness Strict** | **0.718** |
| Ref Conciseness | 0.577 |
| **Regulatory Tone** | **1.000** |
| Keyword recall (vs expected) | 0.509 |
| **Expert-mistakes resolved** | **16 / 37 (43%)** |
| Stage-2 polish fired | 20 / 20 |
| Opus 4.8 (complex) fired | 5 / 20 (q13/14/16/17/18) |
| Latency p50 | **22.8 s** |
| Latency p95 | **65.0 s** |

### Per-question

| Q | model | RefL | AnsS | fixed | pred_refs | gold_refs | read |
| - | ----- | ---- | ---- | ----- | --------- | --------- | ---- |
| q01 | sonnet | 0.17 | 0.38 | 2/4 | Art 5 | 5,6,AnxI,AnxIII,50,51 | **truncated** — "four tiers" → tier 1 only |
| q02 | sonnet | 1.00 | 0.46 | 2/3 | Art 5 | 5 | "public authorities" error FIXED; lists 4/8 (still incomplete) |
| q03 | sonnet | 0.33 | 0.51 | 1/3 | Art 6 | 6,AnxI,AnxIII | **truncated** — "two routes" → route 1 only |
| q04 | sonnet | **1.00** | 0.40 | 2/2 | 6,AnxIII,AnxI | 6,AnxIII,AnxI | **model answer** — both routes; Art 25 dropped |
| q05 | sonnet | **1.00** | 0.58 | 1/2 | Art 50 | 50 | role split FIXED (50(1) provider, 50(3) deployer) |
| q06 | sonnet | **1.00** | 0.28 | 1/2 | 5,6,50 | 5,6,50 | residual framing + relevant cites FIXED |
| q07 | sonnet | 0.50 | 0.69 | 2/2 | Art 1 | 1,4 | 7 principles FIXED (was topic-shift); missing Art 4 |
| q08 | (cache) | 1.00 | 0.88 | 0/0 | Art 3 | 3 | correct |
| q09 | sonnet | 1.00 | 0.56 | 1/2 | Art 99 | 99 | **99(4) €15M/3% FIXED**; missing 99(6) SME rule |
| q10 | sonnet | **0.00** | 0.37 | 0/1 | Art 16 | 3,25 | **mis-cite** — role-duty-seed forced Art 16 on a definitional Q |
| q11 | sonnet | 0.50 | 0.55 | 0/2 | AnxIV, AnxIV.1.e | 11,AnxIV | hardware sub-cite (1(e)) FIXED; missing Art 11 in refs |
| q12 | sonnet | 0.33 | 0.45 | 0/2 | 5, 5.1.f | 5,AnxIII,50 | **truncated** — only prohibition layer; no Annex III/50(3) |
| q13 | **opus** | 0.25 | 0.18 | 1/1 | Art 5 | 6,AnxI,5,50 | **truncated** — answers "prohibited?" only, drops "high-risk?" half |
| q14 | **opus** | 0.67 | 0.48 | 0/2 | 6,AnxI,AnxIII | 6,AnxI,43 | high-risk rule good; Art 43(3) not named |
| q15 | sonnet | 0.33 | 0.35 | 0/2 | 5.1.g, 5 | 5,AnxIII,6 | closed-list named (good); Annex III route missing |
| q16 | **opus** | 0.33 | 0.49 | 1/2 | 53, 53.1 | 53,51,55 | 4 GPAI duties good; missing Art 51/55 gating |
| q17 | **opus** | 1.00 | 0.47 | 0/1 | Art 2 | 2 | correct (2(6)+2(8) in prose) |
| q18 | **opus** | 1.00 | 0.58 | 2/3 | Art 50 | 50 | classify-first + deployer role |
| q19 | sonnet | 1.00 | 0.56 | 0/0 | 5.1.f, 5 | 5 | correct |
| q20 | sonnet | 0.50 | 0.41 | 0/1 | 6, AnxI | 6,AnxI,14,72 | rule good; generic (no Art 14/72) |

### What is fixed vs the original review

**Fixed** (the load-bearing legal errors): social-scoring-public-authorities
factual error (q01/q02), provider/deployer role error (q05), penalty 99(4)
(q09), guiding-principles topic-shift (q07), residual minimal-risk framing +
de-cluttered citations (q06), Annex I route on q04, the q11 hardware
sub-citation (Annex IV.1(e)).

**Remaining** (clustered into three mechanisms):
1. **Multi-part truncation** (q01, q03, q12, q13, q15) — see Part C. Biggest
   lever.
2. **Definitional mis-cite** (q10) — the R87-D role-duty-seed injects Art 16
   on *"difference between deployer and provider"*; a definitional contrast
   question should anchor Art 3 (+ Art 25 for the role transition).
3. **Case-specific depth** (q14 Art 43(3), q20 Art 14/72, q16 Art 51/55) —
   correct rule, missing the named follow-on provisions.

---

## Part C — The #1 finding: multi-part answer truncation

Five of the lowest-scoring rows share one mechanism: the answer **introduces a
multi-part structure then delivers only the first part**.

* q01: *"…a framework comprising **four tiers**… Unacceptable Risk, Article 5
  prohibits…"* — stops after tier 1. Only `Article 5` cited.
* q03: *"…high-risk on one of **two routes**: under Article 6(1) [route 1]…"* —
  stops after route 1. Only `Article 6` cited.
* q13: *"Article 5 does not prohibit… The system is therefore not a prohibited
  practice."* — answers only the "prohibited?" half; never reaches the
  "high-risk per Annex III?" half (the actual question). Only `Article 5`.

The answers are ~200–500 chars and 1–2 sentences — **well under** the 4-sentence
/ 1200-char caps (R103) — so the wire normaliser is **not** the chopper. The
deterministic engine produces the complete enumeration (e.g. the R109
`risk_framework_overview` describer names all four tiers + Arts 51-55), and the
contrast row q04 ("which sectors") delivers BOTH routes in one compound
sentence. So the truncation is **Stage-2 over-compression**: the
"AT MOST 3 sentences" discipline (R80.1) is winning over the closed-set /
multi-part completeness intent (R111 12b), and the model abandons the
enumeration after the first item — dropping the other parts AND their citations.

**This is the highest-leverage remaining lever** and is **distinct from the
Opus 4.8 audit**: q13 truncates on the Opus path too, so a stronger model does
not fix it. The fix is a Stage-2 generation-length adjustment for multi-part /
closed-set questions (the audit's REC-3 5-sentence complex envelope is adjacent
but narrower). It needs a live A/B (prompt-length changes are not davidath-
measurable and R111/R114 showed they need iteration), so it is **recommended
for a focused R119 round**, not shipped blind here.

---

## Part D — MedTech / life-sciences multi-turn eval

New surface: [`evals/regenold/scenarios_medtech_multiturn_r118.py`](../../evals/regenold/scenarios_medtech_multiturn_r118.py)
— **10 scenarios × 3-4 turns**, each ending on a user turn, every gold ref
resolving in `ARTICLE_EXISTENCE`. Domains: medical-device safety component
(MDR Class IIb → Art 6/Annex I/43/14), risk-tier escalation (wellness → triage),
Art 25 role flip, GPAI genomic systemic-risk scale-up (Art 51/53/55), R&D
exclusion → market placement (Art 2(6)/2(8)), hospital chatbot limited-risk
(Art 50 not 13), biometric triage + clinical-trial stratification, worker
emotion monitoring (Art 5(1)(f)), cross-framework MDR+GDPR+CTR, post-market +
incident reporting (Art 72/73). Run via the same `antifragile_live.py` runner
(`--set medtech`).

### Live results (n=10, all HTTP 200) — re-scored

The first run scored gold refs in internal `Art. N` format against the wire's
user-facing `Article N` output → `article_head()` returned None for the gold →
Ref Loose 0.00 uniformly. **This was an eval-format bug, not an engine miss**
(the format-agnostic keyword recall was non-zero throughout; mt_med_08 hit
kw 1.0 with refL "0.00"). Fixed in
[`antifragile_live._to_user_facing_ref`](../../evals/regenold/antifragile_live.py);
the table below re-scores the captured live answers (no re-run). Sidecar:
`.evalout/r118/live_r118-medtech-rescored.json`.

| Axis | Value |
| ---- | ----- |
| Ref Loose | **0.485** |
| Ref Strict | 0.485 |
| Ref Conciseness | 0.378 |
| Keyword recall | 0.380 |
| Regulatory Tone | **1.000** |
| Coherence rate (refL≥0.5 ∧ kw≥0.5 ∧ not refusal) | **4/10** |
| Opus 4.8 (complex) fired | 4/10 |
| Latency p50 | 33.2 s |

| Scenario | model | refL | kw | coh | read |
| -------- | ----- | ---- | -- | --- | ---- |
| mt_med_04 (GPAI systemic) | sonnet | **1.00** | 0.20 | — | Art 51/53/55 all cited |
| mt_med_08 (worker emotion) | sonnet | **1.00** | 1.00 | ✓ | Art 5(1)(f) — fully correct |
| mt_med_02 (risk escalation) | sonnet | 0.67 | 0.60 | ✓ | limited→high-risk, Art 6/50 |
| mt_med_09 (cross-framework) | sonnet | 0.60 | 0.40 | — | MDR+GDPR, Art 10/11/Annex IV |
| mt_med_03 (Art 25 role flip) | sonnet | 0.50 | 0.60 | ✓ | Art 16/25 cited + HRAIS chain |
| mt_med_10 (post-market/incident) | opus | 0.50 | 0.60 | ✓ | Art 73 (gold 72/73) |
| mt_med_07 (biometric triage) | opus | 0.33 | 0.40 | — | Art 5(1)(f); missing Annex III/6 |
| mt_med_01 (MDR safety component) | sonnet | 0.25 | 0.00 | — | final turn narrowly re human oversight → cited Art 14 (right for that turn; gold is the cumulative chain) |
| mt_med_05 (R&D → market) | **opus** | **0.00** | 0.00 | — | **mis-anchor** — cited Art 61, gold Art 2/6/Annex I |
| mt_med_06 (chatbot deployer duty) | **opus** | **0.00** | 0.00 | — | **mis-anchor** — cited Art 16, gold Art 50 |

**Finding:** medtech multi-turn is mixed (Ref Loose 0.485, 4/10 coherent, tone
1.0). The weak rows (mt_05/06/07) **mis-anchor the final turn** and are **all on
the Opus 4.8 path** — so a stronger model does NOT rescue multi-turn
coreference/retrieval. This mirrors the AF Part-C finding: the lever is the
multi-turn final-turn retrieval (the final turn doesn't inherit the
earlier-turn anchors), not the answer-generation model.

---

## Part E — Opus 4.8 usage: audit + what shipped

Full audit: [`R118-opus48-usage-audit.md`](R118-opus48-usage-audit.md) (verified
independently — the firing table, the `always prohibit*ed*` boundary bug, and
the `forced_synthesis_override` "Stage-2 always" directive all reproduced).

**The load-bearing finding:** since the 2026-06-11 `forced_synthesis_override`,
Stage-2 fires for **every** in-scope question; `is_complex_question` only
selects the **model** (Sonnet 4.6 vs Opus 4.8). On the 20 questions, Opus fired
on exactly the 5 multi-phrase ones (q13/14/16/17/18) — all via the "two
sentences ≥4 words" rule, **none** via the five difficulty regexes. The
genuinely-hard single-sentence questions (q12/q15/q19/q20) get Sonnet.

### Shipped this round (both env-gated, davidath byte-identical)

* **REC-1 — `REGENOLD_COMPLEX_GATE_WIDE`** (default OFF) in
  [`app/engines/question_complexity.py`](../../app/engines/question_complexity.py).
  A widened difficulty pattern routes hard single-sentence questions to Opus 4.8
  (always/ever-prohibited, monitor-emotions, biometric-sort/triage,
  general-purpose-AI-model, safety-component, robotic-surgery,
  conformity-assessment). Also fixes the latent `always\s+prohibit\b` boundary
  bug (now `(?:always|ever)\s+prohibit\w*`). **Verified:** env OFF → 5 complex
  (byte-identical to baseline: q13/14/16/17/18); env ON → 9 complex (adds
  q12/15/19/20). The gate only selects the MODEL — a false fire costs latency,
  never correctness, and never touches scope.
* **REC-4 — Anthropic-SDK `max_tokens` floor parity** in
  [`app/engines/graph_rag.py`](../../app/engines/graph_rag.py). The
  wrapper path floored `max_tokens` to 1024 (R112.2) but the SDK sibling passed
  the raw config default (384) → a Pro-tier Opus complex answer was capped at
  384 and truncated → soft-fail to deterministic. Now floored to 1024, matching
  the wrapper.

### Deferred (recommended, need a live A/B)

* **REC-2 — small extended-thinking budget for the complex tier**
  (`P2P_GRAPH_RAG_COMPLEX_THINKING_TOKENS=1500`; engine already clamps
  [1024,16000]). Env-only A/B, no code change. The 0-default was a *latency*
  decision (R103 after the 8000-token disaster), never measured at a small
  budget.
* **REC-3 — 5-sentence envelope for the complex tier** — partly addresses the
  Part-C truncation for the Opus rows.
* **Default REC-1 ON** — recommended after a live A/B confirms the Opus lift on
  q12/q15/q19/q20 beats the added latency (Opus runs at ~Sonnet latency with
  thinking OFF).

---

## Part F — What shipped + verification gates

**New / changed files (all in this PR):**

| File | Change |
| ---- | ------ |
| `evals/regenold/antifragile_groundtruth.py` | NEW — machine-readable ground truth for the 20 Q&A (gold refs + answer + flagged mistakes). |
| `evals/regenold/antifragile_live.py` | NEW — live runner + Regenold-rubric + mistake-resolution scorer (single-turn AF + multi-turn medtech). |
| `evals/regenold/scenarios_medtech_multiturn_r118.py` | NEW — 10 medtech/life-sci multi-turn scenarios. |
| `evals/regenold/build_judge_input.py` | NEW — adapts a live sidecar into a `evals.judge.runner` input. |
| `app/engines/question_complexity.py` | REC-1 — `REGENOLD_COMPLEX_GATE_WIDE` widened difficulty gate (default OFF). |
| `app/engines/graph_rag.py` | REC-4 — Anthropic-SDK `max_tokens` floor parity. |
| `tests/test_r118_opus_gate.py` | NEW — REC-1 gate + REC-4 floor regression tests. |
| `docs/reviews/R118-*.md` | NEW — this report + the Opus 4.8 usage audit. |

**Gates:**

| Gate | Result |
| ---- | ------ |
| `pytest` — R118 gate (10) + complexity (30) + anthropic (21) | **61/61 pass** ✓ (1 existing anthropic assertion updated for the REC-4 floor) |
| REC-1 gate env OFF → ON | **5 → 9 complex** (q12/15/19/20 added); OFF byte-identical to baseline firing ✓ |
| Single in-process route call (deterministic) | status 200, correct refs `[Article 3]` — route healthy with the edits ✓ |
| MedTech multi-turn scenarios validate | 10 scenarios, 0 unresolved refs ✓ |
| OOS scope-safety probe (`runner_v2 --local --probe-oos`) | **21/21 pass, 0 scope leaks** ✓ (REC-1 doesn't touch scope) |
| davidath bench (476) | **byte-identical by construction** — see note below |

**davidath bench note.** The only production-code changes (REC-1, REC-4) are
**inert on the deterministic path**: REC-1 is env-gated OFF (firing verified
identical to baseline) and only selects the Stage-2 *model* (which never fires
under `provider=cli`); REC-4 is reachable only under `provider=anthropic` + a
key. So a full 476-row run is byte-identical to `main` by construction. The
full run could not be completed in this session due to a **pre-existing
eval-harness latency unrelated to R118**: role-noun questions
("provider"/"deployer") trigger an external-embeddings path that reaches
`api.openai.com` and times out ~6.5 s/call (then falls back to deterministic) —
it affects `main` identically (per-call timing measured [6.5 s, 5.7 ms, 6.1 s]
on three probes). The fast-path env for in-process eval runs is
`OPENAI_API_BASE=http://127.0.0.1:1/v1` (dead-port) — **not** `env -u
OPENAI_API_BASE` (which routes external-embeddings to the live OpenAI host).

---

## Part G — Recommendations (ranked)

1. **Fix multi-part answer truncation (R119)** — the single biggest live lever.
   Multi-part / closed-set questions (q01 tiers, q03 routes, q12/q13 layered)
   must deliver every part. A Stage-2 length adjustment for these shapes +
   live A/B. Expected to lift Ref Loose on q01 (0.17→~0.8), q03 (0.33→~0.7),
   q12/q13/q15.
2. **A/B + default REC-1 ON** — route q12/q15/q19/q20 to Opus 4.8.
3. **Fix the q10 definitional mis-cite** — a "difference between X and Y"
   definitional question should anchor Art 3 (+ Art 25), not the role-duty-seed
   Art 16.
4. **Latency** — p50 22.8 s / p95 65 s is the worst production axis. The R84/
   R87-E Stage-2 gates were tuned for this; the `forced_synthesis_override`
   (Stage-2 on every question) re-inflated it. Re-evaluate whether simple
   single-anchor QA needs Stage-2 at all.
5. **REC-2 small-thinking-budget A/B** for the complex tier.

The davidath bench is the regression guard (byte-identical by construction);
every win in this round lands on the LIVE wire + the next live judge re-run.
