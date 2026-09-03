# R381 — finalising the codex/gemini branch, and the scorecard finding that changes the roadmap

**Date:** 2026-09-03 · **Branch:** `codex/finalize-dual-pass-retrieval` · **Base:** `f46adb8`

Two things happened in this round. An eight-dimension executed audit of the branch found and
closed four defects, two of them P0. And a calibration of the official scorecard against the
report's own numbers **overturned the strategic reading this repo has been operating on since
R367**.

---

## 1. The strategic finding: the "conciseness collapse" is a METRIC REDEFINITION

Diff the two reports axis-by-axis **for the two BASELINES**, whose systems did not change between
them (`docs/Antifragile-Regenold-benchmark-report-preview.pdf` 2026-07-14 vs
`report_antifragile_ai.pdf` 2026-08-25):

| split / baseline | AnsL | AnsS | **AnsConc** | RefL | RefS | **RefConc** | Tone | Speed |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| easy, 2026 frontier | +0.0 | +0.0 | **−21.2** | +0.0 | +0.0 | **−28.8** | +0.0 | +2.1 |
| easy, 2025 baseline | +0.0 | +0.0 | **−39.2** | +0.0 | +0.0 | **−38.2** | +0.0 | −0.2 |
| hard, 2026 frontier | +0.0 | +0.0 | **−20.4** | +0.0 | +0.0 | **−20.6** | +0.0 | +1.5 |
| hard, 2025 baseline | +0.0 | +0.0 | **−31.5** | +0.0 | +0.0 | **−28.2** | +0.0 | −1.4 |

Every correctness and tone axis is identical to **0.0 pp**; only the two conciseness axes moved,
by −20 to −39 pp, on systems that did not change. Two unchanged systems cannot change their
scores unless the metric changed. All **twelve** printed Overalls reproduce as the plain geometric
mean to ≤0.06 pp, so the aggregation is untouched — only the two axis definitions are. The July
preview says so itself: *"More details will be provided in the final report."*

Corroborating measurement: the six candidate answers printed verbatim in the Aug-25 appendix
average **923 chars**; the July run averaged **914.9** (measured over all 110 from
`official_batch.jul07_answer`). Length barely moved while the score fell 44 points.

**Consequences.**

1. **⛔ The R367 counterfactual is void.** "Hold Aug-25 correctness + restore July conciseness →
   85.8 easy / 84.2 hard beats frontier" mixes new-metric correctness with old-metric conciseness.
   Never quote `96.0`, `−44.1`, or that table again. **Only compare within one report.**
2. Using the baselines as the metric-only control: of our −44.1 AnsConc, roughly **−35 pp is the
   metric** and only **~−9 pp** is real verbosity. On RefConc we slightly *improved*.
3. **The trajectory is good.** Gap to the 2026 frontier baseline: easy **−10.7 → −5.8**
   (closed 4.9 pp), hard **−14.4 → −8.3** (closed 6.1 pp). Against the 2025 baseline, easy went
   from **losing −3.4 to winning +5.0**.
4. **True remaining gaps (Aug-25, easy, vs frontier):** AnsConc **−16.0**, RefStrict **−10.2**,
   AnsStrict −7.9, RefLoose −6.7, AnsLoose −4.7, RefConc **−1.5**, Tone −0.9, and
   **Speed +5.8 — we beat frontier.**

### 1.1 Ref. Conciseness recovered exactly: `min(1, |expected| / |provided|)`

The appendix prints both reference sets for five questions. Fitted against the printed 50.4:

| candidate formula | mean over the 5 | err |
| :--- | ---: | ---: |
| exact-string precision | 39.0 | 11.4 pp |
| hierarchical precision | 63.0 | 12.6 pp |
| head-collapsed precision | 65.0 | 14.6 pp |
| **pure count excess `min(1, E/P)`** | **49.0** | **1.4 pp** |

Per case: Q45 1/2, Q17 1/5, Q95 2/4, Q104 min(1,2/1), Q74 1/4. **Which provisions you cite does
not affect this axis at all — only how many.** Expected sets are MINIMAL: **1.4 refs/row**.

**Validated live, twice, on this branch.** A 24-row stratified live run of the official batch over
the cloudflared wrapper (24/24 answered, 16 wrapper-served, **0 Bedrock fallback**) measured
**3.46 refs/row → predicted RefConc 50.0** against the official **50.4**, and mean latency
**12.3 s → predicted Speed 87.7** against the official **87.6**. Two independent axis predictions
inside 0.5 pp. The instrument is `scratchpad/official_calibration.py` + `refconc_formula.py`.

### 1.2 The arithmetic nobody has run

Marginal GM leverage at our Aug-25 point (pp Overall per pp axis) — easy: `ref_conc 0.186 >
ans_conc 0.181 > ref_strict 0.137 > ans_strict 0.116 > speed 0.107 ≈ ref_loose 0.105 ≈
ans_loose 0.105 > tone 0.095`. Applying a terminal cap to the **live** 24-row ref distribution:

| cap | mean refs | RefConc | ΔOverall | rows cut |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 3.33 | 50.5 | +0.02 | 2 |
| 4 | 3.00 | 52.8 | **+0.45** | 8 |
| 3 | 2.54 | 58.2 | **+1.36** | 11 |
| 2 | 1.88 | 73.8 | **+3.66** | 16 |

Even a −10 pp hit to BOTH ref-correctness axes costs only −2.4 pp. R282's live measurement of the
R281 `adaptive_ref_clamp` independently confirms the direction (RefS +0.060, RefConc +0.144,
recall −0.034, **est. Overall +2.34 pp**).

⚠ **This is in direct tension with Hard Rule #8.** `gold_dropped_head` is computed against our own
hand-built probe gold, which is NOT minimal, so the internal gate actively fights the official
RefConc axis — the highest-leverage of the eight in easy mode. **Not flipped here**: a
reference-dropping lever is an operator decision and needs its own powered gate. The table is the
deliverable, not the flip. Ready-made knobs with no code change:
`REGENOLD_REF_CLAMP_SCENARIO_BUDGET` (default `5`) and the R77 QA budget.

---

## 2. The audit: eight executed dimensions, four defects closed

Read-only agents that **executed** probes rather than reading diffs, each finding then handed to
an adversarial verifier. Two dimensions (full suite, live wire) were lost to a session quota limit
and were re-run by hand.

### 2.1 P0 — the committed Stage-0 de-noiser model does not exist (fixed)

`f46adb8` hardcoded `llama-3.3-70b-versatile`. Measured live against the account's own key:
`GET /openai/v1/models` returns 14 ids and **that is not one of them**; a POST returns
`404 model_not_found`. So **every multi-turn rewrite 404'd** and fell through to the 40-turn
concatenation — the exact history bleed R380 had just fixed, reintroduced.

The same commit also passed `reasoning_effort="none"` explicitly. Measured live on
`openai/gpt-oss-120b`:

| call | result |
| :--- | :--- |
| no `reasoning_effort` | OK, 83 completion tokens, 0.6 s |
| `reasoning_effort="low"` | OK, **30 completion tokens, 0.2 s** |
| `reasoning_effort="none"` | **HTTP 400** — *must be one of `low`, `medium`, `high`* |
| `qwen/qwen3.6-27b`, `"low"` | **HTTP 400** — *must be `none` or `default`* |

So the valid value is model-FAMILY specific and must never be hardcoded at the call site — and it
does not need to be: `openai_wrapper_provider.py:555-568` already auto-injects it per family
(gpt-oss → `low`, qwen → `none`), which R380's intent is fully served by. **The uncommitted revert
was correct on both counts and is what ships**, with the evidence recorded at the call site.

### 2.2 P0 — the July-7 judge was grading us against our own past output (fixed)

`evals/judge/grounded.py` carries an explicit anti-circularity note: *"`run_official_batch` writes
`jul07_refs` — which is OUR OWN prior output, NOT gold … so we deliberately do NOT."* The guard
named `jul07_refs`. **The sidecar key is `july7_refs`.** One character.

Measured on `evals/bench/results/july7-july7-live-r379.ckpt.jsonl`: **24/24 rows** had `gold_refs`
populated and **24/24 were byte-identical to our own 2026-07-07 citations**; the rendered prompt
shipped them under "GOLD CITATIONS"; and the run wrote `gold_coverage: 1.0` /
`recall_is_text_grounded: True`, so the <50 % warning never fired and the scorecard asserted it was
trustworthy while measuring self-similarity. `legal_v2` imports the same `_norm` and inherited it.

⚠ **Therefore `docs/reports/july7-live-run-and-judge-report-2026-09-02.md` and every earlier
July-7 judged scorecard measured "how close is today's citation set to July 7's".** They must not
be used to accept or reject a lever. Fixed, and pinned by
`tests/test_r381_judge_gold_and_exit.py`, including a test that the committed sidecar now reads
as gold-less.

Also fixed alongside it: **a PARTIAL judge failure exited 0 while deflating the headline score.**
R361 only catches total failure (`error == n`). With 50 % of calls forced to the same 403,
`pass_rate` fell to 0.25 on two axes, `dead` was empty and `main()` returned 0 — because
`pass_rate` divides by ALL rows and an errored row counts as a failed row. Now exits **3**, with
`--allow-judge-errors` as the deliberate escape.

### 2.3 P0 — two report failures were fixed in the data and then overwritten on the way to the wire (fixed)

The R367 pins for Q45 and Q95 are green and assert on the KB dict and the router. Both questions
still failed at the wire, because the R93 extractive-QA pass replaced the engine's correct answer
with one unresponsive BM25 sentence:

| Q | qtype | what shipped | why it is wrong |
| :--- | :--- | :--- | :--- |
| **Q95** | `numeric` | Art. 6(2) verbatim — *"In addition to the high-risk AI systems referred to in paragraph 1, AI systems referred to in Annex III shall be considered to be high-risk."* | contains **no cardinal at all**; the question asks "how many areas exist?". The R367 "eight AREAS" gloss was computed and discarded |
| **Q45** | `list` | Art. 26(9) — a sentence that merely **cross-references** Article 13 to describe a GDPR DPIA duty | enumerates nothing; the question says "List the required categories". Art. 13(3)(a)-(f) was verbatim in the corpus the whole time. **5/5 criteria FAIL** |

This is the **fourth** instance of the shape CLAUDE.md records three times (R329 rerank
placements, R330 semantic layer, R366 parent collapse): a green, correctly-written pin that does
not touch the path the change had to affect.

**Fix — `REGENOLD_EXTRACT_SHAPE_GUARD`, default ON.** A `numeric` answer must contain a cardinal
that is not a provision coordinate (provision coordinates are stripped first, because
"paragraph 1" contains a digit); a `list` answer must enumerate. On rejection it falls back to
`_enumerated_categories(ref)` — the provision's top-level lettered limbs, rendered verbatim and
trimmed — and then to the engine prose. The R68/R69 `preferred_refs` path is **exempt**: it is
already bound to the question's own anchored article, and guarding it regressed
`TestR68MatrixDumpContainment`.

Two defects found while building the enumerator and fixed before ship, both caught by execution:

* the lead regex was unanchored and matched **mid-word** inside Article 6 ("ystem is placed on the
  market …"), and it matched a **condition** list ("where both of the following conditions are
  fulfilled:") as if it were a content list. The lead is now anchored to a sentence start and must
  name the content it introduces (`contain|include|comprise|consist of|set out|provide`).
* the letter walk **spliced across numbered blocks**: Annex III numbers its AREAS 1., 2., 3. and
  restarts letters inside each, so an unguarded (a)..(z) walk welded three areas into one list
  ("(c) emotion recognition. 2. Critical infrastructure: … (d) monitoring students during tests").
  The walk now stops at a numbered heading, and `_enumerated_categories("Annex III")` correctly
  returns `None`. A corpus-wide sweep pins zero splices.

### 2.4 P1 — Article 27(1) dropped a statutory FRIA class (fixed)

`f46adb8` rewrote the curated Art. 27(1) text and correctly added the Annex III point 2
carve-out, but dropped the **third** class the Act names: deployers of the Annex III **5(b)**
(creditworthiness / credit scoring) and **5(c)** (life and health insurance risk assessment and
pricing) systems. The repo's own verbatim oracles (`provision_text.get_provision_text`,
`official_eu_ai_act.OFFICIAL_ARTICLE_TEXT`) both carry it, so the curated layer was contradicting
the verbatim text rendered beside it in the same Stage-2 block, and answering "public bodies only"
for a bank or insurer. Restored. (Note the key form: the oracle writes `5 (b)` **with a space** —
a grep for `5(b)` alone returns a false zero.)

### 2.5 Documentation corrections

`f46adb8` introduced three false claims about the eval stack; all three are corrected in CLAUDE.md
with the executed evidence:

* *"Both are scored by the grounded judge against verbatim Act text"* — **neither harness calls
  it.** `easyhard_ab` scores with `evals.bench.metrics` (lexical); `ab_judge` grounds on KB
  summaries. `grounded.py` is a separate, post-hoc pass you must invoke explicitly.
* *"with Bedrock fallback"* — **there is none.** `--provider` is an explicit choice; nothing chains.
* *"(or `claude-sonnet-5`)"* — true **only over the wrapper**. Verified: a real single-row grounded
  judge call with `--model claude-sonnet-5 --provider wrapper` scored 0 errors, and a bogus id
  (`claude-bogus-9-9`) 500s, so the id is genuinely resolved rather than silently defaulted. On
  **Bedrock** it returns `api_access_denied_403` — as do `claude-opus-5` and `claude-opus-4-8`,
  **so the R379/R380 Bedrock A/B legs cannot be reproduced on today's key.**

And the honest caveat that was missing: the judge prompt interpolates question + verbatim
provision text + our answer + our citations and **nothing else**. The official benchmark grades
Ans Correctness against *per-question criteria* and both conciseness axes against a *reference
answer*; the July-7 batch carries neither, because regenold never published them. **Every local
judged number is a proxy.** `REGENOLD_DUAL_PASS_RETRIEVAL` (the branch's headline feature, and
undocumented in either file) now has a flag-table row, including the audit's finding that while
ON it pre-empts R380's self-contained skip and re-opens assistant-turn bleed.

---

## 3. Verification

**Offline, deterministic** (`REGENOLD_SKIP_DOTENV=1`, `provider=cli`, Stage-2 off): all six
appendix questions re-run; Q45, Q95, Q17, Q104 answer correctly, Q96's refusal is gone.

**Live, over the cloudflared wrapper** (`wrapper.antifragile-ai.net`, 6/6 wrapper-served, no
Bedrock fallback) — every one of the six is now substantively correct:

| Q | before | now |
| :--- | :--- | :--- |
| Q45 | abstention, 5/5 criteria FAIL | enumerates all six Art. 13(3) categories; cites `Article 13` |
| Q96 | **total refusal** (`LEXY_OOS_GENERIC`) | names all eight areas and answers the healthcare sub-question |
| Q17 | 3/4 FAIL | both cumulative conditions verbatim; `Article 7` + `Article 97` on the wire |
| Q95 | 2/2 FAIL ("eight use cases") | area-vs-use-case distinguished, eight AREAS; **both** gold heads cited |
| Q104 | 2/2 FAIL (described Annex VIII) | correct large-scale-IT-systems content; **both** gold heads cited |
| Q74 | 2/2 FAIL (led "Yes, marking required") | leads on the artistic limit, states the machine-readable marking does not intrude, and that the deep-fake disclosure duty is relaxed but not removed |

**Test suite:** 7 193 collected, 0 collection errors. 67 failed / 7 125 passed. Attribution by an
**in-place two-arm run** (one env var differing, per the standing rule — never a second worktree):
`REGENOLD_EXTRACT_SHAPE_GUARD=1` → 23 failures across the affected files; `=0` → 23; set
difference **empty. Zero new failures.** The 21 new tests in
`tests/test_r381_report_answers_end_to_end.py` and `tests/test_r381_judge_gold_and_exit.py` are
**two-sided**: with the guard off, exactly the six Q45/Q95 pins flip to FAIL.

---

## 4. What is NOT done, and what to do next

* **The 110-question live batch was not run in full.** A 24-row stratified live sample was, and it
  calibrated the instrument (RefConc 50.0 vs 50.4; Speed 87.7 vs 87.6). A full run is ~25 min of
  wrapper quota and should be paired with a judge pass.
* **No judged scorecard is quoted here.** Every July-7 judged number that exists predates the
  self-gold fix and is contaminated; re-running the judge with
  `--provider wrapper --model claude-sonnet-5` is the first thing to do on top of this branch, and
  it will now honestly report **zero gold coverage** — recall becomes judge recall, precision
  stays text-grounded. Read the two asymmetrically.
* **The reference-count lever is sized but not pulled** (§ 1.2). It is the single highest-leverage
  change available and it is an operator decision, because it drops references and our internal
  gate is calibrated against non-minimal gold.
* **`REGENOLD_PROMPT_V3` stays default OFF.** Its R380 gate failed on `gold_dropped_head` (+7 at
  n=127) — but that gate is exactly the one § 1.2 shows is mis-calibrated against the official
  RefConc axis. Re-reading V3 under the corrected arithmetic is the obvious next measurement, and
  it is cheap: the arms already exist.
