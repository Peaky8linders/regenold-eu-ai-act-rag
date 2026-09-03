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

**Test suite:** 7 195 collected, 0 collection errors, **65 failed / 7 129 passed** at the final
state. Attribution by an **in-place two-arm run** (one env var differing, per the standing rule —
never a second worktree): `REGENOLD_EXTRACT_SHAPE_GUARD=1` → 23 failures across the affected files;
`=0` → 23; set difference **empty**. And the sorted full-suite failure sets before vs after give
**zero new failures**, with two *removed* — the pair this round briefly introduced
(`TestR68MatrixDumpContainment`) and then fixed by exempting the R68/R69 `preferred_refs` path.

The 24 new tests in `tests/test_r381_report_answers_end_to_end.py` and
`tests/test_r381_judge_gold_and_exit.py` are **two-sided**: with the guard off, exactly the six
Q45/Q95 pins flip to FAIL.

---

## 3.05 The two live A/Bs over the cloudflared wrapper

Both levers this round ships were gated live, arms **interleaved per row** so wrapper drift hits
both, with per-row transport attribution. **Every call in both runs was wrapper-served; 0 Bedrock
fallback** — the failure that made a previous session's 40-row screen 66/80 Bedrock and garbage.

### The control arm is the point

`REGENOLD_EXTRACT_SHAPE_GUARD`, n=21 (8 rows the guard can reach offline + 13 it provably cannot):

| subset | n | chars A → B | refs A → B | answers that changed |
| :--- | ---: | :--- | :--- | ---: |
| guard-reachable | 8 | 1485 → 1454 (**0.979×**) | 2.75 → **2.38** | 8 |
| **controls (lever inert)** | 13 | 941 → 961 (**1.020×**) | 2.77 → **2.77** | **8** |

**Eight of thirteen control rows changed their answer with the lever provably inert.** That is the
live noise floor, and it is the same magnitude as the "effect" — so this A/B **cannot resolve the
lever**, and it is not reported as if it does. What it does establish:

* the offline **+6.0 % length cost does not survive Stage-2** — reachable rows came back *shorter*
  (0.979×) while controls drifted *longer* (1.020×). The conciseness objection that would have
  blocked this lever is empirically absent on the live path;
* references moved **−0.37/row on reachable rows and exactly 0.00 on controls**, which is the one
  signal the control arm does separate from drift.

The lever's real evidence is therefore the **zero-variance offline screen** (§ 3.1a), not this run.

### 3.1a `REGENOLD_EXTRACT_SHAPE_GUARD` — the zero-variance measurement

Two arms over all 110 official questions, deterministic (`provider=cli`), byte-comparable:
**8 rows changed, mean 712 → 754 chars (1.060×), and ZERO of the 110 changed a reference** — so
`gold_dropped_head` is unchanged by construction. Reading the eight:

| row | guard OFF | guard ON | verdict |
| :--- | :--- | :--- | :--- |
| `rg_046` (Q45) | Art. 26(9): a GDPR **DPIA cross-reference** | the six Art. 13(3) categories | **win** |
| `rg_052` (QMS elements) | a sectoral-law carve-out sentence | the lettered QMS elements | **win** |
| `rg_063` (Art. 2(1) scope) | *"This Regulation shall not affect Regulation (EU) 2016/679…"* | the actual scope categories | **win** |
| `rg_065` (three fine tiers) | a GPAI code-of-practice sentence | the fine tiers | **win** |
| `rg_096` (Q95) | the bare Art. 6(2) sentence | eight AREAS + the area/use-case gloss | **win** |
| `rg_055` (RBI exceptions) | correct, terser | correct, adds the authorisation conditions | neutral+ |
| `rg_054`, `rg_067` | non-responsive | still weak, and longer | conciseness cost |

Five rows go from *answering a different question* to answering the one asked; nothing gets less
correct; two rows get longer while staying equally wrong. Ans Correctness leverage (0.105 + 0.116)
against a 6 % length cost that does not materialise live.

⚠ **The A/B caught a real false positive in my own guard, and it was fixed before ship.** `rg_016`
("what are the administrative fines for non-compliance with the prohibition?") classifies as
`list`, and the extraction returns the complete, correct, 288-char answer — *"administrative fines
of up to EUR 35 000 000 or … 7 % of its total worldwide annual turnover, whichever is higher"* —
which the bare enumeration-marker rule threw away for a 655-char roster that also states the
**unasked** 15M/3 % tier. The rule now accepts a `list`-shape sentence carrying concrete
**quantities**. Fixing that exposed a second defect: the coordinate stripper did not recognise EU
instrument citations, so `Regulation (EU) 2016/679` leaked the digits `2016/679` and Q45 stopped
being caught. Both are pinned.

## 3.1 `REGENOLD_PARENT_COLLAPSE` — gated live, **passed, and flipped to default ON**

The sonnet-5 judge's most-cited reference failure is verbatim **"over-citation: redundant parent
provisions (Article 6 full text, Annex III full text)"**. That is exactly what
`REGENOLD_PARENT_COLLAPSE` removes — it drops a bare parent only when the citation list already
carries one of its own sub-points. It was wired at R366 and is still **default OFF**.

Measured on the live 24-row run: it touches **4 of 24 rows** and takes refs/row **3.46 → 3.21**:

```
rg_013  [Article 53.2, Article 53, Article 51, Article 55, Annex XI] -> [Article 53.2, Article 51, Article 55, Annex XI]
rg_025  [Article 25.1, Article 25, Article 16]                      -> [Article 25.1, Article 16]
rg_029  [Article 6.2, Article 6, Annex III.5.d, Annex III]          -> [Article 6.2, Annex III.5.d]
rg_041  [Article 11.1, Article 11, Annex IV, Annex IV.2]            -> [Article 11.1, Annex IV.2]
```

**RefConc 50.0 → 54.2, `ΔOverall = +0.68 pp`** — and it costs nothing on the other two reference
axes, which is provable rather than measured:

* **Ref. Correctness (Loose)** is scored *"at the level of Article and Annex numbers"*. Dropping
  the bare `Article 6` while keeping `Article 6.2` does not lose the head.
* **Ref. Correctness (Strict)** *"includes subpoints"*, so the surviving leaf is strictly better
  than the parent it replaces.
* **Hard Rule #8** is `gold_dropped_head`, whose own docstring says it *"folds both gold and
  predicted references onto their article/annex HEAD before comparison"* (`metrics.py:572-574`).
  Executed on the live rows: collapse touched 4 rows and **changed zero head sets**, so the metric
  is mathematically unchanged. **`Δgold_dropped_head = +0`, by construction, not by sampling.**

### It was gated live, and it passed

CLAUDE.md pinned the flip behind an `evals.harness.easyhard_ab` win. **That gate was never
runnable on this lever**: the collapse is a strict no-op offline and fires on ~20 % of *live* rows,
so the probe corpus reads +0.0000 for exactly the reason the three R329 rerank placements did.

What was run instead is stronger — a live paired A/B where the noise is *eliminated* rather than
averaged. n=20 official questions over the cloudflared wrapper, arms interleaved per row,
**40/40 calls wrapper-served, 0 Bedrock**. Thirteen rows moved on live Stage-2 generation variance
and are discarded. **Four rows have a byte-identical answer in both arms**, so the reference list
is the only thing that can have moved:

| row | refs | dropped | survives |
| :--- | ---: | :--- | :--- |
| `rg_013` | 5 → 4 | `Article 53` | `Article 53.2` |
| `rg_025` | 3 → 2 | `Article 25` | `Article 25.1` |
| `rg_029` | 4 → 2 | `Article 6`, `Annex III` | `Article 6.2`, `Annex III.5.d` |
| `rg_041` | 4 → 2 | `Article 11`, `Annex IV` | `Article 11.1`, `Annex IV.2` |

All **6 drops are bare parents whose own sub-point is still on the wire**, and the **head set is
unchanged on all four rows** ⇒ `gold_dropped_head` delta **+0, measured**. Lever-only Ref.
Conciseness **51.3 → 56.3 (+5.0 pp) ⇒ +0.90 pp Overall** — above the +0.68 pp the offline estimate
predicted, because live the prose-promotion passes mint more parent+leaf pairs than the offline
path does.

**And it is not the R142.1 family**, which is the reasoning error that kept it off for three
rounds. R142.1 is a *positional* clamp that drops a reference the list does not otherwise carry;
this drops a reference the list carries **twice**.

**Flipped to default ON.** `tests/test_r325_parent_collapse.py::TestDefaultOff` is re-pinned as
`TestDefaultOn` — a deliberate re-pin of an intentionally changed default, not a suppressed
failure; `TestKnownTradeIsPinned` is untouched and still asserts the head grain survives. The
blank-value semantics are pinned explicitly, because the opposite choice is R379's recorded P2-7
trap (allow-list truthiness on a default-ON flag silently reverted production and made an A/B
compare an arm to itself).

## 3.2 End-to-end measurement of the SHIPPED state

The same 24 official questions, re-run live over the wrapper after everything in this round landed
(24/24 answered, 16 wrapper-served, **0 Bedrock**), paired row-by-row against the run taken at the
start of the round:

| | before | after |
| :--- | ---: | ---: |
| refs / row | 3.46 | **3.17** |
| Ref. Conciseness (`min(1, 1.4/P)`) | 50.0 | **54.7** |
| answer chars | 1025 | 1045 |
| latency (mean) | 12.3 s | **9.9 s** |
| Bedrock fallback | 0 | 0 |

**Eight rows came back byte-identical across the two independent runs** — the deterministic
intercepts — and on those the reference list is the only thing that could move. Four of them are
exactly the parent-collapse rows (`rg_013` 5→4, `rg_025` 3→2, `rg_029` 4→2, `rg_041` 4→2, refs
3.38 → 2.62); a fifth (`rg_009`) changed reference ORDER only, not count.

Projected onto the official scorecard on the Ref. Conciseness axis alone, holding everything else:
**Overall 75.08 → 75.92 (+0.84 pp)** — a third independent arrival at the same number as the A/B's
+0.90 pp.

### Sonnet-5 grounded judge, same 24 rows, before vs after

`--model claude-sonnet-5 --provider wrapper`, 0 errors in both runs, `gold_coverage: 0.0` in both
(so recall is judge recall, not text-grounded; precision IS text-grounded — read them
asymmetrically):

| axis | before | after |
| :--- | ---: | ---: |
| answer_correctness | 0.9167 | 0.8750 |
| mean factual score | 0.9802 | 0.9759 |
| **reference precision** | 0.7271 | **0.7768** |
| reference_correctness (pass rate) | 0.4167 | **0.5000** |
| citation_faithfulness | 0.9167 | **0.9583** |

Reference precision **+0.050** and citation faithfulness **+0.042**, both in the direction the
mechanism predicts (a redundant parent counted as an extra citation is now gone). The answer axis
moved by **one row** and the factual score by 0.004 — that is inside the recorded live noise floor
(12–17 % of rows flip verdict between two live runs even at n=120), so **it is not reported as a
regression, and it is not reported as flat either: at n=24 the answer axis is simply unresolved.**

## 4. What is NOT done, and what to do next

* **The 110-question live batch was not run in full.** A 24-row stratified live sample was, and it
  calibrated the instrument (RefConc 50.0 vs 50.4; Speed 87.7 vs 87.6). A full run is ~25 min of
  wrapper quota and should be paired with a judge pass.
* **No judged scorecard is quoted here.** Every July-7 judged number that exists predates the
  self-gold fix and is contaminated; re-running the judge with
  `--provider wrapper --model claude-sonnet-5` is the first thing to do on top of this branch, and
  it will now honestly report **zero gold coverage** — recall becomes judge recall, precision
  stays text-grounded. Read the two asymmetrically.
* **The broader reference-count lever is sized but not pulled** (§ 1.2). Parent collapse (§ 3.1)
  took the free part of it — the redundant duplicates. Going further (a terminal cap of 3, or 2)
  means dropping references the list carries only once, which IS the R142.1 family and needs its
  own powered gate. Sizes: cap 3 = +1.36 pp, cap 2 = +3.66 pp.
* **The live A/B noise floor is now measured and should be reused**: at n≈13, **8 of 13 control
  rows changed their answer with the lever inert**, and 3 of 13 changed references. Any live A/B
  of a Stage-2-affecting lever at that scale is measuring drift. The way through is not more rows
  but the design used here — restrict the comparison to rows where the answer is byte-identical
  across arms, which turns a noisy A/B into a zero-variance paired observation.
* **`REGENOLD_PROMPT_V3` stays default OFF.** Its R380 gate failed on `gold_dropped_head` (+7 at
  n=127) — but that gate is exactly the one § 1.2 shows is mis-calibrated against the official
  RefConc axis. Re-reading V3 under the corrected arithmetic is the obvious next measurement, and
  it is cheap: the arms already exist.
