# R410 — Antifragile Frontier Evaluation, Code Validation, & Session Handoff Report

**Date:** 2026-09-11  
**Author / Agents:** Peaky8linders Antigravity Agent Swarm (Code Validation Specialist, Rubric & Criteria Auditor, Antifragile Benchmark Evaluator, Regenold Metric Analyst, Showcase Report Specialist)  
**Target Repository:** [`Peaky8linders/regenold-eu-ai-act-rag`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag)  
**Branch:** `fix/r409-r408-audit`  
**Primary Artifacts:**  
- Full Evaluation Dataset: [`docs/measurements/r409/antifragile_frontier_judge_results.json`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/docs/measurements/r409/antifragile_frontier_judge_results.json)  
- Triage Ledger: [`docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json)  
- Showcase HTML: [`docs/reports/Appendix-Remediation-Showcase.html`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/docs/reports/Appendix-Remediation-Showcase.html)  
- Evaluation Runner: [`docs/measurements/r409/run_antifragile_frontier_judge.py`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/docs/measurements/r409/run_antifragile_frontier_judge.py)  
- Metric Formulas: [`evals/official/rubric.py`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/evals/official/rubric.py)  

---

## 1. Executive Summary & State of the Repo

This handoff report equips any new session or incoming agent with complete context on the codebase, the R408/R409 audit findings, the implementation and verification of the 5 answer-completeness levers, and the live frontier evaluation of the **28 Antifragile AI review questions** (17 Part I baseline questions + 11 Part II expert reference questions/variants) judged live by **Claude Sonnet 5** via OpenRouter under the official Regenold rubric.

### 1.1 Git & Working Tree Status
- **Current Branch:** `fix/r409-r408-audit`
- **Remote Head:** `b725ebb` (Qwen 3 235B re-judge of R407 on corrected gold; KG point text gated behind `REGENOLD_KG_POINT_TEXT` default OFF; 6 reconstructed gold rows corrected).
- **Staged in Git (Deployability Secured):**
  - `app/engines/answer_completeness.py` (New module: 5 completeness levers, gap collectors, repair builder, and `accept_repair` gate).
  - `docs/measurements/r409/answer_completeness_offline_validation.py`
  - `tests/test_r409_answer_completeness.py` (105 unit tests).
  - `tests/test_r409_completeness_integration.py` (13 integration tests).
- **Modified Tracked Files:**
  - `app/engines/_graph_rag_impl.py`: Integrated governing provision clause, pushback keep clause, and `_guard_answer_completeness`.
  - `app/routes/regenold.py`: Registered all 5 answer-completeness flags in `_engine_cache_key()`.
  - `docs/reports/Appendix-Remediation-Showcase.html`: Updated Section 1 with all 6 R409 fixes; added Section 3 Part 3B containing Cases A–D.
  - `evals/official/score_arm.py`: Basis SHA cache keying (`_judge_basis_sha`) preventing stale verdicts on edited criteria.
  - `CLAUDE.md`, investor evaluation reports, and measurement score files.

### 1.2 Automated Gate Status
- **Deployability Gate (R394.1/R394.3):** `pytest tests/test_r394_2_tracked_module_imports.py -v` $\rightarrow$ **5/5 PASSED (0 warnings)**. Staging `app/engines/answer_completeness.py` guarantees Railway deployment from clean clone will not throw `ModuleNotFoundError`.
- **Cache Key AST Gate:** `pytest tests/test_r355_cache_key_complete.py -v` $\rightarrow$ **2/2 PASSED**. All flags verified as string literals in `_engine_cache_key`.
- **R409 Completeness Suites:** `pytest tests/test_r409_answer_completeness.py tests/test_r409_completeness_integration.py -v` $\rightarrow$ **118/118 PASSED**.
- **KG Point Traversal & Eval Accounting:** `pytest tests/test_r408_kg_context_point_traversal.py tests/test_r409_eval_accounting.py -v` $\rightarrow$ **10/10 PASSED**.
- **Full Test Suite:** **7,719 passed, 1 skipped**.

---

## 2. Official 8-Axis Scorecard: Live Frontier Evaluation ($n=28$)

Conducted live against **OpenRouter Claude Sonnet 5** (`anthropic/claude-sonnet-5`, temperature=0.1) with verbatim EUR-Lex ground-truth statutory text:

```
Part I Strict Correctness:  11.8% ───► 29.4% (+17.65 pp, +150% relative)
Part I Loose Correctness:   36.2% ──────────► 63.8% (+27.54 pp, +75% relative)
Part I Reference Precision: 92.9% ───────────────► 98.7% (+5.75 pp)
Part I Overall Geom. Mean:  54.0% ──────────► 67.8% (+13.75 pp)
```

| Official Axis (`evals/official/rubric.py`) | Part I: Live Original (17 Qs) | Part I: Current Engine (17 Qs) | Part I Delta (Remediation Gain) | Part II: Current Engine (11 Qs) |
| :--- | :---: | :---: | :---: | :---: |
| **1. Answer Correctness (Strict)** | 11.76% (2/17) | **29.41% (5/17)** | **+17.65 pp** | **0.00% (0/11)** |
| **2. Answer Correctness (Loose)** | 36.23% | **63.77%** | **+27.54 pp** | 23.91% |
| **3. Answer Conciseness** | **92.45%** | 69.88% | -22.57 pp *(exhaustiveness penalty)* | 94.43% |
| **4. Reference Correctness (Strict)** | 33.26% | **56.43%** | **+23.17 pp** | 47.51% |
| **5. Reference Correctness (Loose)** | 63.17% | **69.09%** | **+5.92 pp** | 64.13% |
| **6. Reference Conciseness** | 92.94% | **98.69%** | **+5.75 pp** | 90.40% |
| **7. Regulatory Tone** | **94.12%** (16/17) | 88.24% (15/17) | -5.88 pp | 63.64% (7/11) |
| **8. Response Speed** | 100.00% *(70.2% wire)* | 99.94% *(61 ms in-proc)* | -0.06 pp *(+29.7 pp wire)* | 99.97% *(29 ms in-proc)* |
| **OVERALL (Geometric Mean)** | 54.01% | **67.77%** | **+13.75 pp** | **0.00%** *(zero-floor collapse)* |

---

## 3. Statutory Criteria Audit: The 12 Reconstructed Errors

In [`docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json), 67 failing Sonnet 5 criteria across 39 rows were triaged against verbatim Regulation (EU) 2024/1689:
* **Judge Misreads = 0:** 59 of 67 failing criteria failed on unanimous 3/3 votes across repetitions.
* **Qwen 3 235B Leniency:** Passed 21 rows that Sonnet 5 fails (+17.7–21.7 pp on Qwen-written rows).
* **Generation vs Retrieval:** In **53 of 55 engine criteria (96.4%)**, the provision was **already present in emitted citations**. Content was lost at Stage-2 generation/condensing.
* **Deterministic vs Qwen:** No Stage-2 (deterministic) achieved an **88.0% strict pass rate**, vs Qwen 3 235B at **56.5%** and Qwen 3 32B at **60.9%**.

### The 12 Specific Criteria Errors
1. **`rg_037` (5 criteria):** Question asked for general provider registration items under Article 49(1) / Annex VIII Section A (points 1–11). Reconstructed gold erroneously imported the law-enforcement secure-section exception of **Article 49(4)**, Section B/C, and Annex IX.
   * *Fix:* Re-keyed to `Article 49.1` + Annex VIII Section A points 1–11.
2. **`rg_041` (1 criterion + refkey):** Question asked if SMEs can use a simplified technical documentation form. Criterion 2 named the "AI Office". Under **Article 11(1)**, the statutory empowerer is **the Commission**. Refkey was also miskeyed to `Article 17.4` (financial institutions QMS derogation).
   * *Fix:* Corrected empowerer to Commission; re-keyed refkey to `Article 11.1`.
3. **`rg_060` (2 criteria):** Question asked for 3 actions during serious incidents in *real-world testing*. Criteria copied post-market incident investigation from Article 73(6). The true statutory triad under **Article 60(7)** is: (1) report to MSA under Art 73; (2) adopt immediate mitigation or suspend/terminate testing; (3) establish a prompt recall procedure upon termination.
   * *Fix:* Rebuilt criteria on the Article 60(7) triad; re-keyed to `Article 60.7`.
4. **`rg_068` (3 criteria):** Question asked who is responsible for ensuring *input data* is relevant and representative. Criteria named providers and Article 10 training data. In the Act, the phrase pairing "input data" with "relevant and sufficiently representative" appears in exactly one place: **Article 26(4)** (*"to the extent the deployer exercises control over the input data..."*).
   * *Fix:* Rebuilt criteria on Article 26(4) deployer duties; dropped Article 10 provider criteria.
5. **`rg_110` (Criterion 4):** Contractor placed name on a high-risk municipal gas AI system. Criterion 4 claimed FRIA does not apply because the contractor became a provider under Art 25(1)(a) and stopped being a deployer. Deemed providers retain deployer status for own use. The true legal reason FRIA does not apply is the explicit carve-out in **Article 27(1)** for **Annex III point 2** (gas supply safety components).
   * *Fix:* Predicated FRIA exemption on the Article 27(1) Annex III point 2 exclusion.
6. **`rg_082` (Expected Refs Key):** Question and criteria addressed distributor storage and transport duties under Article 24(3). `expected_refs` was miskeyed to `Article 24.1` (CE marking). Re-keyed to `Article 24.3`.

---

## 4. Technical Diagnosis of Outstanding Issues

### Issue 1: Presupposition Rejection Defect (Part II Q1, Q5, Q6)
* **Finding:** When questions presuppose non-statutory constructs ("What risk categories are provided?", "Does the Act provide for minimal risk?", "What are the guiding principles?"), the engine cooperatively affirms PR commentary shorthand.
* **Statutory Reality:** The Act does not name "risk categories" (obligations attach conditionally under Arts 5, 6, 50, Ch V); it does not provide a formal "minimal risk category" (residual class); it does not establish binding "guiding principles" (Recital 27 non-binding; only operative link is Art 95(2)(a)).
* **Next Step:** Implement a prompt-side `PRESUPPOSITION_DENIAL_GUARD` enforcing an immediate opening rejection of non-statutory premises.

### Issue 2: Medtech Triage Regex Hard-Routing (Part II Q8–Q11)
* **Finding:** The classification topic `medtech_triage` in [`app/engines/_graph_rag_data.py:L910-L938`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/app/engines/_graph_rag_data.py#L910-L938) matches clinical trial prioritization queries and hard-routes them to Annex III(5)(d) emergency dispatch, emitting the identical 651-character answer across Q8, Q9, Q10, and Q11.
* **Statutory Reality:** Clinical trial selection is not emergency triage. It requires 3-branch conditional resolution:
  * **Branch A (Race - Q9):** Prohibited under Article 5(1)(g) (unambiguous "No").
  * **Branch B (Sex - Q10):** Outside 5(1)(g) closed list; high-risk under Annex III(1)(b) + Art 6(2); profiling under Art 3(52) extinguishes Art 6(3) derogation; hospital is deployer under Art 3(4) with Art 26 / 50(3) duties ("Yes, but high-risk").
  * **Branch C (Physiological - Q11):** Escapes Annex III(1)(b); falls back to Art 6(1) / Annex I MDR Regulation (EU) 2017/745 ("Yes, unclassified under Annex III").
* **Next Step:** Narrow `medtech_triage` regex exclusively to emergency response keywords ("emergency room", "emergency dispatch", "112 dispatch"), allowing clinical trials to synthesize across all 3 statutory branches.

### Issue 3: Answer Conciseness vs Legal Exhaustiveness Tension
* **Finding:** By providing complete legal explanations (four tiers, GPAI, Art 6(1)(b), Art 6(3), Art 4 literacy), Part I answer length increased from 424.5 to 757.4 chars.
* **Impact:** Ans. Conciseness (`min(1, len_ref / len_cand)`) dropped from 92.45% to 69.88% (-22.57 pp).
* **Lesson:** Legal completeness incurs an inverted verbosity penalty if reference answers are terse summaries. High AnsConc requires disciplined, bulleted sentence economy.

### Issue 4: Pushback Re-Ask Focus Coupling in Production
* **Finding:** With `REGENOLD_REASK_FOCUS=1` (production default), `_extract_reask_tail` strips prior dialogue down to the bare re-asked question on challenge turns.
* **Impact:** `REGENOLD_PUSHBACK_KEEP_CONTRACT` inspects `question` to locate `turn1_answer`. Because `question` is stripped, `dropped_pushback_points` fired on **0 of 110 rows** in offline validation.
* **Next Step:** Decouple retrieval query formation from synthesis context: use `_reask_tail` for vector/BM25 retrieval, but forward full dialogue history in `QuestionHistoryResult` so answer-completeness guards can inspect turn 1.

### Issue 5: Default-OFF Gating Invariants
* **Target Flags:** `REGENOLD_CLOSED_SET_COMPLETENESS_GUARD`, `REGENOLD_EXCEPTION_LIMB_GUARD`, `REGENOLD_VERDICT_LEAD_GUARD`, `REGENOLD_PUSHBACK_KEEP_CONTRACT`, `REGENOLD_GOVERNING_PROVISION_CLAUSE`, and `REGENOLD_KG_POINT_TEXT`.
* **Prerequisites Before Flipping Default ON:**
  1. `REGENOLD_KG_POINT_TEXT`: Expands context by **+3,491 chars/row** (>11x expansion). Must clear `easyhard_ab` (`gold_dropped_head = 0`) and wire latency profiling.
  2. Bounded LLM repair calls must be evaluated independently for latency impact on the production wire.

---

## 5. Showcase Report Enriched: `Appendix-Remediation-Showcase.html`

File [`docs/reports/Appendix-Remediation-Showcase.html`](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/docs/reports/Appendix-Remediation-Showcase.html) was updated (`+342 lines, -14 lines`, verified with `HTMLParser` for 0 syntax errors):
1. **Section 1:** Added the six R409 fixes to the primary remediation table.
2. **Section 3 Part 3B:** Added four Antifragile showcase remediation cases with side-by-side Before (August Live Baseline) vs After (Current Engine) panels, verbatim reviewer critiques, and live Claude Sonnet 5 judge remarks:
   * **Case A: Q6 Minimal Risk AI Systems:** `1/4 → 4/4 (100% Pass) ✅` (+75 pp loose, +100 pp strict). Purges irrelevant high-risk citations (Arts 9, 12, 13, 14, 27) and defines residual category, Art 4 AI literacy, and Art 95 codes.
   * **Case B: Q10 Deployer vs Provider:** `2/4 → 4/4 (100% Pass) ✅` (+25 pp loose, +100 pp strict). Delineates Art 3(3) and 3(4) definitions at paragraph grain; adds Art 25 role transitions.
   * **Case C: Q16 Workplace Emotion Monitoring:** `1/4 → 4/4 (100% Pass) ✅` (+75 pp loose, +100 pp strict). Front-loads unambiguous "No" lead; applies Art 5(1)(f) ban; denies efficiency carve-outs.
   * **Case D: Q17 Robotic Surgery Safety Component:** `0/4 → 4/4 (100% Pass) ✅` (+100 pp loose, +100 pp strict). Leads with "Yes"; applies MDR Annex VIII Rule 11 (Class IIb/III); details Art 14 surgical control loops; integrates Art 43(3) and Art 72 post-market surveillance.

---

## 6. R410 — What Has Now Been Fixed (status)

All four grounded defects below are implemented, tested and on the branch. The
verification instrument is `docs/measurements/r409/r410_wire_probe.py` (offline
`TestClient`, no Stage-2 provider), which asserts the Part II expectations
directly on the wire text and references.

### 6.1 Conciseness regression (the headline defect) — FIXED

The R409 repair-acceptance bound was a blanket
`max(1.8 * len(original), len(original) + 900)`. The levers ran at it: Part I
answers grew **424.5 -> 757.4 chars** (1.78x) and the graded Answer Conciseness
axis (`min(1, |reference| / |candidate|)`) fell **92.45 -> 69.88 (-22.57 pp)**.

Replaced with `answer_completeness.repair_char_budget()`: the allowance is
**additive in the gap count** (`120` chars of connective room + `90` per missing
item), capped at `1.6x` the original. A faithful repair adds one short clause per
missing item, so it no longer buys length with unrelated prose. The repair prompt
now carries the numeric budget and an explicit compress-don't-duplicate rule, and
`accept_repair` rejects anything over it. When a complete answer cannot fit, the
concise original ships — a deliberate bias toward the graded axis.

### 6.2 Presupposition denial (Part II Q1/Q5/Q6) — FIXED, with a wire-level trap found

* The guiding-principles detector only accepted `principles ... established by
the Act`. The presupposition-defusing re-ask reverses that order and names no
article, so it never fired and retrieval fell to BM25 (notifying-authority prose,
0/4 criteria). The regex now binds the Act to the principles in the act-first
verb form; the curated answer **denies** the presupposition and cites
Article 95(2)(a) as the single operative connection.
* **A second, silent defect was found on the wire.**
`normalise_answer_for_regenold` drops the longest sentence carrying no
`art.` / `article ` / `annex` token until the reply fits its soft cap (code
default **400**, Railway **1200**). A polar opener ("The EU AI Act does not
establish ...") is exactly that shape, so the pre-fix wire shipped the
Recital-27 enumeration **alone** — it asserted the principles existed and lost
both the No verdict and the recitals-are-not-binding point (2 of the 4 graded
criteria). The answer is now two sentences, **every sentence cite-anchored**, so
the cap has nothing it may drop at ANY cap value; this is asserted by a test.
* Art. 1 is dropped from this item's refs: it was a purpose-clause aside, not the
question's operative connection, and the annotated gold is Recital 27 +
Art. 95.2(a) + Art. 95. Pure-count Ref. Conciseness rises from 0.667 to 1.0 with
no reference-correctness loss and no gold head dropped.
* The minimal-risk answer denies its presupposition the same way.

### 6.3 Medtech hard-routing + the Art. 5(1)(g) gatekeeper over-fire — FIXED

Two separate over-matches produced the "four facts, one answer" defect:

1. `medtech_triage` matched `sort patients ... clinical trial` and hard-routed
   Part II Q8-Q11 to the Annex III(5)(d) **emergency-dispatch** verdict. Annex III
   point 5(d) reaches emergency calls and emergency healthcare triage, so the
   pattern now requires an emergency-response marker (order-independent
   conjunction of three lookaheads). Emergency triage still matches; clinical-trial
   selection cannot.
2. The prohibited-practices gatekeeper fired Art. 5(1)(g) on the bare keywords
   `sort patients` / `patient sorting` / `biometric categorisation`. Article
   5(1)(g) does not prohibit biometric categorisation as such — it prohibits
   categorisation that infers a **closed-list** attribute. A **required**
   qualifier (race | ethnic origin | political opinions | trade-union membership |
   religious or philosophical beliefs | sex life | sexual orientation) now gates
   it. The change is narrowing only: it can remove a match, never invent one.
   `sex` is deliberately absent from the required list — it is a protected
   attribute but **not** on the Art. 5(1)(g) closed list, so Q10 ("infers sex")
   correctly resolves to the Annex III(1)(b) high-risk branch instead of the
   prohibition.

Measured after: Q9 (race) leads with the Art. 5(1)(g) prohibition; Q8/Q10/Q11 no
longer assert emergency dispatch.

### 6.4 Reask/pushback coupling — FIXED

Under `REGENOLD_REASK_FOCUS` (default) the route hands the engine the **bare**
re-asked question, so `previous_answer()` found no turn 1 and the pushback-keep
guard was a no-op. The route now forwards the flattened history in a new
`GraphRAGRequest.guard_question` field (retrieval still uses the bare question, so
the retrieval contract is unchanged), and it is included in `_engine_cache_key`
(R263.2 doctrine: an unkeyed flip would serve arm A's cached answer to arm B).

### 6.5 Residual, NOT fixed (worth stating plainly)

Part II **Q8/Q10/Q11** no longer collapse to the wrong emergency answer, but they
still resolve to the *same* generic Art. 6 classification verdict, because no
curated topic covers biometric categorisation for prioritisation. That verdict is
directionally right ("high-risk only if an Annex I safety component or an Annex
III use case") but not branch-specific: Q10's gold wants Annex III(1)(b) applied
explicitly and Q11's wants the Art. 6(1)/Annex I fallback plus Art. 3(40). Fixing
that properly means a curated biometric-categorisation topic, which is new work,
not a finalisation of the R409 audit, and it is prompt/content-side so it needs
the live gold gate (invariant #5). **Do not read the current Q8/Q10/Q11 answers as
resolved.**

### 6.6 Metrics / judge calibration — AUDITED, no change needed

Every axis in `evals/official/rubric.py` was checked against the published
spec and is correct as written: Answer Conciseness and Reference Conciseness are
both one-sided `min(1, |ref| / |cand|)`; Ref. Correctness loose/strict are head vs
full-grain recall with questions lacking expected refs **excluded**
(`None`, not zero); Resp. speed is `100 - latency_s` clipped at zero; and the
aggregate is the geometric mean across all eight axes (which is why one zero axis
zeroes the score). The judge is **3 repetitions at temperature 0.1**
(`R388_JUDGE_REPEATS`/`R388_JUDGE_TEMPERATURE`), resolved by per-criterion
majority with **ties resolving to FAIL**, and the min-max spread across the
repetitions is carried on `_criteria_rate_min`/`_criteria_rate_max`. The R409
accounting fixes (basis-hash cache key including the judge's grounding refs,
per-turn graded latency) are in place and pinned by tests.

The formulas were also **calibrated empirically**, not just read. With the Claude
Max tunnel restored, `python -m evals.official.calibration` replays the
report's own transcribed appendix — 17 criterion-level verdicts of known ground
truth, over six questions, two arms (`docs/measurements/r388/calibration.json`):

| Arm | Agreement | Trivial-baseline comparison |
| :--- | :--- | :--- |
| Negative (the answers the evaluator printed, 16 FAIL / 1 PASS) | **15/17 = 88.2%** | always-FAIL scores 16/17 = 94.1% |
| Positive (reconstructed reference answers, same criteria) | **17/17 = 100.0%** | always-FAIL scores 0/17 |

The two arms are what make this meaningful: an always-FAIL judge beats us on the
negative arm but scores ZERO on the positive arm, and an always-PASS judge scores
1/17 negative. Our profile is the one that holds on both, so the judge is
neither degenerate-PASS nor degenerate-FAIL.

**The one caveat, stated plainly.** Both misses are over-acceptances on the same
row — Q74 (Art. 50(4) deepfake disclosure for an artistic work), criteria
"No need of marking that would compromise enjoyment" and "Still required: other
form of disclosure ...". The shipped answer does contain the relevant vocabulary
("does not hamper the display or enjoyment of the work", Article 50(4)) but
asserts the carve-out as belonging to a DIFFERENT duty from the one the question
asked about. That is a plausible judge miss, but the ground truth on that row is
itself ambiguous, so the judge prompt was deliberately **not** edited to flip
two criteria — that would be teaching to the test on n=2. If it is to be fixed,
it needs a rule for criteria phrased as a NEGATION or a RESIDUAL duty, validated
on a larger printed-verdict set first.

### 6.7 Verification

| Check | Result |
| :--- | :--- |
| `r410_wire_probe.py` (offline, Part II, 7 items) | all expectations met |
| Full suite `pytest tests/` | **7847 passed, 2 skipped** |
| Targeted R410/R409/R111/R109/R358/gatekeeper | 295 passed |
| CI `Deployable (clean clone)` on PR #407 | pass (32s) |
| CI `Test suite (clean clone)` on PR #407 | pass (2m11s) |
| **Production** `r410_live_prod_check.py` (Stage-2 live) | **all asserted invariants hold** |

Note on the offline probe: the local Stage-2 wrapper is currently 401 (expired
Claude-Max OAuth token), so the probe exercises the deterministic/intercept path —
which is exactly where all four fixes live. Stage-2 polish is a separate layer
above them.

**Post-deploy production evidence** (`2c8ed878`, the PR #407 merge commit; the
Railway GitHub integration auto-deploys `main`). The four Q8-Q11 variants now
resolve to three DIFFERENT statutory branches, which is the defect inverted:

| Item | Deployed verdict (lead) |
| :--- | :--- |
| Q6 | "The EU AI Act does not establish legally operative guiding principles: Article 95(2)(a) ..." (refs `Article 4`, `Article 95.2`) |
| Q8 (no fact) | "Yes ... but only if it stays outside Article 5(1)(g) and is then operated as a high-risk AI system" — conditional |
| Q9 (race) | "No. The hospital cannot deploy that system ... prohibited practice under Article 5(1)(g)" |
| Q10 (sex) | "Yes ... but only as a high-risk AI system: inferring a patient's sex from biometric data is not one of the attributes whose inference is banned" |
| Q11 (physiological) | "Yes ... neither a prohibited practice nor ..." — Annex I / Art. 6(1) fallback |

Q10 is the sharpest confirmation: the deployed engine now states the statutory
point the old gatekeeper obscured — `sex` is a protected attribute but is **not**
on the Art. 5(1)(g) closed list, so the question is high-risk, not prohibited.

### 6.8 Gold gate run on the largest R409 lever — it FAILS, so it stays OFF

With the Claude Max tunnel restored, the R409 flag table's own precondition ("gate
each lever on the live gold set before flipping") was finally executed for the
biggest lever, `REGENOLD_CLOSED_SET_COMPLETENESS_GUARD` (22 of the 55 engine-side
triage gaps). Live Stage-2, hard split, paired n=37, both arms scored 37/37 with
0 errors:

```
  axis          baseline    branch     delta
  ref_loose       0.7883    0.7748   -0.0135  <-- GOLD LOSS (R142.1 failure mode)
  ref_strict      0.3816    0.3813   -0.0003
  ref_conc        0.1551    0.1645   +0.0094
  tone            1.0000    1.0000   +0.0000
  kw_recall       0.8333    0.7883   -0.0450
  pred:gold         2.91      2.95     +0.03
  gold_drop_hd        15        16        +1  <-- GOLD DROPPED (hard rule #8)
```

**Verdict: FAIL — hard rule #8.** `gold_dropped_head` 15 → 16 on mt_v2_004,
007, 015, 022; est. Overall −0.04 pp. The only axis it improves is Reference
Conciseness (+0.0094). The gate exits NON-ZERO, so **the flag stays default
OFF** and must not be reported as having passed.

**Attribution caveat — this paired read is NOT same-generation, and it matters.**
All 37 branch answers differ from baseline (0/37 byte-identical), because
`REGENOLD_CLOSED_SET_COMPLETENESS_GUARD` is part of `_engine_cache_key`'s env
fingerprint, so each arm generated fresh through Stage-2. The delta therefore
mixes the lever's effect with sampling variance across the whole split. Two
measures bound how much of it the lever can possibly explain:

* The detector fires on only **4/37** hard rows (`mt_v4_004`, `mt_v4_011`,
  `mt_v2_004`, `mt_v2_010`); with every completeness lever ON, 8/37.
* Only **1 of the 4** gold-drop offenders (`mt_v2_004`) is a row where the
detector fires.

So what stands is the gate's own verdict: the branch arm dropped a gold head the
baseline kept, which is a rejection under hard rule #8, not a trade. What does
**not** stand is any claim about the size of the lever's effect — the plausible
mechanism (refs are partly a function of the answer via `_add_prose_named_refs`,
so a prose repair re-derives the reference set) is not established by this run.
Measuring it cleanly needs a same-generation comparison that shares the Stage-2
answer across arms, as the R381 parent-collapse A/B did, not two independent
arms.

Evidence: `docs/measurements/r409/score-r410-closed-set-gate-hard.md` (report)
and `-hard.json` (per-row sidecar). This run was taken from the working tree
after the R410 conciseness fix, so `repair_char_budget` **was** the acceptance
bound throughout — i.e. this is the lever's post-R410 performance, not a
pre-fix reading.

### 6.9 Judge-remark forensics: detector precision, and why the off-by-default levers stay off

**Root-cause split of the 67 triaged failing criteria**
(`docs/measurements/r409/r407_sonnet5_failing_criteria_triage.json`):

| root cause | criteria | lever that targets it | status |
| :--- | ---: | :--- | :--- |
| `OMITTED_ENUMERATED_ITEM` | 22 | `REGENOLD_CLOSED_SET_COMPLETENESS_GUARD` | **gated FAIL** (§6.8) — stays OFF |
| `NOT_APPLICABLE` | 12 | none — criterion defect, not an engine gap | gold work, not code |
| `WRONG_OR_MISSING_PROVISION` | 10 | `REGENOLD_GOVERNING_PROVISION_CLAUSE` | ungated |
| `MISSING_CONDITION_OR_EXCEPTION` | 9 | `REGENOLD_EXCEPTION_LIMB_GUARD` | ungated |
| `PUSHBACK_DRIFT` | 7 | `REGENOLD_PUSHBACK_KEEP_CONTRACT` | ungated |
| `VERDICT_POLARITY_OR_FRAMING` | 6 | `REGENOLD_VERDICT_LEAD_GUARD` | **precision fixed here** |
| `HEDGED_OR_UNSUPPORTED` | 1 | none | — |

**Detector precision/recall on the frozen 110-row R407 ledger**, measured with
the deterministic instrument that already ships (`docs/measurements/r409/
answer_completeness_offline_validation.py`, all five flags ON, no network):

| detector | target rows fired | PASSING rows fired (FP) |
| :--- | ---: | ---: |
| member | 3/12 (25.0%) | 7/71 (9.9%) |
| exception | 1/8 (12.5%) | 6/71 (8.5%) |
| verdict — **before** | 1/6 (16.7%) | 6/71 (8.5%) |
| verdict — **after the R410 fix** | **2/6 (33.3%)** | **0/71 (0.0%)** |
| keep | 1/6 (16.7%) | 3/71 (4.2%) |
| governing_clause | 1/8 (12.5%) | 0/71 (0.0%) |
| keep_clause | 6/6 (100.0%) | 69/71 (97.2%) — fires on everything, useless as a gate |

Two defects grounded by that table and fixed (`answer_completeness.py`):

1. **`_opens_with_verdict` required the literal token `Yes`/`No`.** 7 of the 11
verdict fires were correct answers that decided the question in words —
`rg_007`/`rg_089` "Not prohibited and not high-risk.", `rg_081`/`rg_084`/
`rg_106` "Not high-risk.", `rg_090` "Not high-risk, so no deployer log-keeping
obligation under Article 12.", `rg_074` "Emotion recognition is not categorically
prohibited ...". All 7 were flagged as *no verdict at all*, which forces a
needless repair on a correct answer — the same mechanism as the R410 verbosity
regression. It now also accepts a worded classification lead, while still
refusing a conditional framing (`rg_107` "High-risk only where ...", "Only where
the system is high-risk ... does Article 27 apply.") — a framing is not a verdict.
2. **`_yes_no_sentence` read the LAST interrogative of a multi-clause question.**
`rg_095` ("Who ... needs to establish the post-market monitoring system? Is it
possible that ...?") is a wh-ask with a follow-up and is not a yes/no question,
but the trailing clause made it one. Conversely `rg_069` ("Do I have an
obligation ...? What if I am an importer instead?") *is* a yes/no question and
the trailing clause made it not one. The FIRST interrogative now decides.

Measured effect: fires 11 → 2 rows, false positives on passing rows 6 → 0,
target recall 1/6 → 2/6. The two remaining fires are both genuine lead-shaped
defects (`rg_107` conditional framing, `rg_097` verdict not in the lead).

**The other three levers stay OFF, and the reason is measurable, not timid.**

* `member` fired on 7 of 71 PASSING rows — it demanded the full lettered list of a
  provision the answer merely *cited* (`rg_055` demanded Article 5(1)(a)-(g) for a
  question about the 5(1)(h) exceptions; `rg_064` demanded Article 60(4)(a)-(k) for
  a question answered from 60(4)(e); `rg_018` demanded Article 7(2)(b)-(j)). That
  was the direct explanation of the §6.8 gold drop: repairs on already-correct
  answers. **Fixed in §6.11** (question-side engagement): 7/71 → 0/71.
* `exception` fires on 6 passing rows and hits 0/9 target criteria by coordinate.
* `keep_clause` fires on 107/110 rows — a clause that always fires carries no
  signal.

### 6.10 TrustGraph: the oracle is correct, and its target failure mode does not occur

The §6.8 gate left one open question from the TrustGraph README
(`trustgraph-integration/README.md`): *"how often does the live path actually
emit a non-existent coordinate?"* — the precondition for turning the generated
`provision_coordinates` oracle into a wire guard.

**Measured: never.** Every wire reference in the frozen captures was replayed
through `coordinate_exists`:

| capture | rows | refs | non-existent coordinates |
| :--- | ---: | ---: | ---: |
| R407 hard, `pred_refs` | 110 | 310 | **0** |
| R407 hard, `turn1_refs` | 110 | 310 | **0** |
| R410 closed-set gate, arm A | 37 | 170 | **0** |
| R410 closed-set gate, arm B | 37 | 172 | **0** |
| **total** | **294** | **962** | **0 (0.00%)** |

The `coordinate_exists` oracle (655 paragraph + 421 point coordinates, CI-checked
by `tests/test_trustgraph_ontology.py`) is well-founded, but there is nothing for
it to catch on the wire: the `_repair_nonexistent_coordinates` pass at
`app/routes/regenold.py:4078`, enabled by `REGENOLD_REF_COORD_GUARD` (default
`1`), already folds an unreal coordinate back onto its head, and the three
prose→refs passes only emit coordinates they can substantiate. That is why the
count is 0 — the oracle is already applied, and 0 is the *post-guard* reading.
**A second wire guard built on this oracle would therefore be a no-op that can
only lose gold heads — hard rule #8 — so it is not added.** The remaining
TrustGraph benefit is not a reference guard; it is the SPARQL-queryable A-Box,
which stays available without the cluster.

### 6.11 Closed-set engagement is now question-side — the §6.8 gold drop explained and removed

§6.9 left the closed-set lever with one open question: it fired on 7 of 71 rows the
grader passed in full, and *which* closed set a question engages is what decides
whether a demanded member is a gap or noise. That rule is now implemented and
measured.

**Why the answer's own citations cannot be the engagement signal.** The clause was
`mentioned = prefix_closure(answer_paths) | prefix_closure(question_paths)`, so
naming *any* member engaged its whole group. `rg_055` cites Article 5(1)(h) — the
law-enforcement exception — and was asked for Article 5(1)(a)–(g), the
prohibitions. `rg_064` cites Article 60(4)(e) and was asked for 60(4)(a)–(k).

A bare token-overlap gate does not fix this, and that is worth stating because it
is counter-intuitive: the false positives score **higher** on chapeau overlap than
the true positives (16 and 15 shared stems for `rg_055`/`rg_064` against 8 and 7 for
`rg_046`/`rg_052`), because the Regulation's boilerplate ("high-risk AI system",
"information", "provider") dominates any raw count.

**The signal that works: a distinctive chapeau bigram.** A group is engaged when
the question names the parent coordinate exactly, or contains a two-word phrase
from the parent's chapeau whose words each occur in at most one member of the head.
The chapeau carries the set's own subject ("instructions for use", "quality
management system"); the document-frequency filter over the head's members removes
the boilerplate ("high risk", "AI system", "technical documentation"). The
answer-side requirement is kept, so a repair can never invent a head the answer did
not already name.

Measured on the frozen 110-row R407 ledger
(`docs/measurements/r409/closed_set_engagement_probe.py`, deterministic, no
network):

| rule | fires | true positives | FP on a PASSED row |
| :--- | ---: | ---: | ---: |
| citation-side (shipped before) | 13 | 3/12 | **7/71 (9.9%)** |
| question names the parent, or a distinctive chapeau bigram of it | **2** | 2/12 | **0/71 (0.0%)** |

Target-criteria coverage is **unchanged at 7/22**: the two fires are still `rg_046`
(Article 13(3), the instructions-for-use list) and `rg_052` (Article 17(1), the QMS
elements list). The three rows lost were not coverage — `rg_066`'s "hit" was the
Article 6(3) derogation demanded of a question about the EU database, i.e. a false
positive the old hit-count was crediting.

**What this does to the §6.8 gold drop — the headline.** Replayed over the recorded
hard-split answers:

| leverage | fires |
| :--- | ---: |
| citation-side rule, baseline answers | **1/37** — `mt_v2:mt_v2_004` |
| question-side rule (this change) | **0/37** |

`mt_v2_004` is **one of the four `gold_dropped_head` offenders** the failed gate
recorded. The one row this lever was harming on that split is exactly the fire the
new rule removes.

⚠ **The gate is now unsatisfiable on the current corpus, and that is a finding,
not an omission.** Running the whole `easyhard_ab` corpus (132 rows) with the
**gold** answer as the draft, the lever engages on **0** rows — there is no row in
the corpus that asks for the enumeration of a closed statutory set in the shape
`rg_046`/`rg_052` do. A live A/B on that corpus cannot exercise the lever at all: it
would measure Stage-2 sampling noise around a no-op, which is precisely the
confound that left §6.8's effect size unsettled. So the flag stays **default OFF**,
now for a *better* reason than "it lost gold": it has nothing to do on the corpus
available to gate it, and the one harmful fire is gone. Gating it needs either a
probe split with enumeration-ask rows, or the official 110-row benchmark as the
gate.

## 7. Actionable Roadmap for the Next Session

```mermaid
graph LR
    P1["Task 1: Commit & PR Deployability"] --> P2["Task 2: Fix Medtech Regex & Decouple Re-ask"]
    P2 --> P3["Task 3: Gated Rollout of Fix 5 & Fix 1"]
    P3 --> P4["Task 4: Production Investor Hard-Mode Run"]
```

### Task 1: Commit and Open PRs
1. Commit the staged files (`app/engines/answer_completeness.py`, tests, offline validation) and working tree changes.
2. Structure into clean PRs:
   - **PR 1:** Harness fixes (pacing subtraction, per-turn latency, basis hashing, Bedrock model reverts, point text allocation behind default-OFF flag).
   - **PR 2:** Gold rubric corrections in `official_gold_n110.jsonl` with `_revised: "R409"` metadata.
   - **PR 3:** The 5 answer-completeness levers behind individual default-OFF flags.

### Task 2: Fix Medtech Triage Regex & Re-Ask Focus Dialogue Coupling
1. In `app/engines/_graph_rag_data.py`, restrict `medtech_triage` strictly to emergency response keywords.
2. In `app/routes/regenold.py`, ensure `QuestionHistoryResult` retains structured conversation history while using `_reask_tail` for vector search, enabling `REGENOLD_PUSHBACK_KEEP_CONTRACT`.

### Task 3: Gated Evaluation of Fix 5 (Verdict Lead) & Fix 1 (Closed-Set Completeness)
1. Run `easyhard_ab` with `REGENOLD_VERDICT_LEAD_GUARD=1` to confirm `gold_dropped_head = 0`. This will immediately resolve failing verdict criteria across Part II questions 5, 6, 8, 9, 10, and 11.
2. ~~Run `easyhard_ab` with `REGENOLD_CLOSED_SET_COMPLETENESS_GUARD=1` …~~ **DONE (R410) and it FAILED** — see §6.8. `gold_dropped_head` 15 → 16, est. Overall −0.04 pp. The flag stays OFF. Do not re-propose it without a gold-drop-safe variant **and** a same-generation comparison.

### Task 4: Re-Run Investor Hard-Mode Benchmark on Production Stack
1. With the harness now recording single-turn latency and subtracting the 13-second Cohere pacing sleep, execute the 110-row official benchmark on the production Claude Sonnet 3.5 Stage-2 stack.
2. Update investor evaluation scorecards with verified production numbers, replacing provisional Qwen 3 data.
