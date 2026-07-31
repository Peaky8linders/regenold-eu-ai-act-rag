# R305 — Deep review of the R304 checkpoint: verdict, corrections, and what shipped

**Supersedes** `.planning/R305-CHECKPOINT-SCORECARD-AND-JUDGE-REMARKS.md` for every
claim marked CORRECTED below. That document is kept for the audit trail; do not
use it as a handoff without applying this file's corrections.

Method: 5 parallel specialist review lanes + an adversarial verifier (default
stance REFUTED, every finding re-confirmed by reading code or re-running a
probe), plus independent inline verification. Every number below was
reproduced from disk or from a live probe.

---

## 1. Verdict in one paragraph

The Section-1 aggregate cells **reproduce exactly** (all six single-turn, all
six multi-turn, all five pooled) and the r304↔r301 A/B is population-matched.
Everything built on top of them is not reliable: the `rg_038` row presented as
fixed **does not reproduce against its own code**, all three shipped curated
verdicts contain verbatim-text defects, one detector fires on questions it
should not, the claimed root cause of the truncation failure mode is
falsified, two of the three "judge failure modes" mis-assign their rows, and
three judge remarks are **judge false positives** promoted into the document
as evidence. Sections 1 (aggregates), 4.3 (davidath 0-hit, 276-runner) and 0
(recall 0.973, zero missing-only failures) stand.

---

## 2. What was wrong, and what shipped instead

### 2.1 The three curated intercepts — REMOVED

R304 added one hardcoded verdict per graded evaluator row. Measured against
the **verbatim** evaluator questions (not the abbreviations the R304 unit test
used), all three were unsound:

| Intercept | Defect | Evidence |
| --- | --- | --- |
| `_detect_sandbox_definition_inquiry` | **Returned `False` on its own target question.** Its negative guard rejects `"how long"`; the evaluator question ends *"...to do what, for how long)."* | The R304 test asserted on a TRUNCATED copy with that clause removed. 7/7 tests passed while production failed. |
| `_detect_irregular_migration_inquiry` | **Fired on obligations questions** (*"Which documentation must a provider keep for an AI system used in irregular migration control under Annex IV?"*). A curated intercept SKIPS Stage-2, so no LLM could correct the hijack; it also disables the QA ref budget, `_prune_non_anchor_refs`, noise suppression and the R281 clamp. | Direct call → `True`. Clause 3 is a bare substring conjunction; `"risk"` is a substring of `"high-risk"`, `"annex"` of `"annex iii"`. |
| all three | **Scanned the flattened conversation.** 27 of the 30 sibling detectors slice on `"Latest question:\n"`; these three did not, so a prior turn could fire the curated gate on an unrelated live turn. | Lane probe: `M(flattened) = True` with an unrelated live turn. |

**Verbatim-text defects (hard rule #4) — all confirmed against
`provision_text.get_provision_text`:**

* **Article 7(3) stated as ONE condition.** Shipped: *"Article 7(3) permits
  removing a use-case where it no longer presents a significant risk."*
  Verbatim 7(3) requires **both** (a) the system no longer poses any
  significant risks **and** (b) *"the deletion does not decrease the overall
  level of protection of health, safety and fundamental rights under Union
  law."*
* *"Adding new area headings requires the ordinary legislative procedure"* —
  the phrase "ordinary legislative procedure" appears in **0** of the 126
  articles. Unsourced.
* **Sandbox definition** omitted two verbatim definitional elements the
  question explicitly asked for — *"pursuant to a sandbox plan"* and *"where
  appropriate in real-world conditions"* — and invented AI Office
  co-establishment. Art 3(55): *"a controlled framework set up by a competent
  authority ... pursuant to a sandbox plan"*.
* **Annex III(7) mischaracterised.** Shipped: *"to detect, recognise, or assist
  in managing irregular migration"*. Verbatim 7(b): *"to assess a risk,
  including a security risk, a risk of irregular migration, or a health risk,
  posed by a natural person who intends to enter or who has entered into the
  territory of a Member State"*. The shipped phrase is absent from the Act, and
  the Annex III(7) chapeau qualifier *"in so far as their use is permitted
  under relevant Union or national law"* was dropped.

**None of the three needed a hardcode.** The measured root causes are ordinary
routing bugs, now fixed generically:

1. **engine↔scope keyword divergence.** `"irregular migration" → Annex III`
   existed in `scope.KEYWORD_TO_ARTICLE` but **not** in the engine's
   `_KEYWORD_ENTITY_MAP`, so the route surfaced `Annex III` as a wire
   reference while the ENGINE never retrieved it — the deterministic answer
   and the Stage-2 grounding both came from the Art. 3 / Art. 5 fallback. The
   graded row shipped an **Article 5 real-time-RBI answer** for a migration
   classification question: a cite-and-mismatch.
2. **`classify_question` tests `duration` before `definition`.** The sandbox
   question ends *"for how long"*, so it classified as `duration` and
   `select_answer_sentence` hunted a duration sentence inside Article 57,
   returning *"The AI Office shall make publicly available a list of planned
   and existing sandboxes..."* — reproduced byte-identically to the shipped
   wire answer. `select_definition_sentence` on the **same** question already
   resolved the correct verbatim Article 3(55) text.
3. **`_is_classification_question` did not recognise the verdict ask.**
   *"to what risk category does it belong"* matched neither regex, so the
   question was read as a description and fell to the QA dump.

### 2.2 What shipped (commit `a272be1`, branch `r305-review-fixes`)

| Fix | Blast radius |
| --- | --- |
| Removed the 3 detectors + verdicts + both registrations | — |
| `_KEYWORD_ENTITY_MAP` += `irregular migration` / `migration control` / `asylum application` / `border control` → `Annex III` | davidath byte-identical |
| `classify_question` definitional precedence (env `REGENOLD_DEFINITION_QTYPE_PRECEDENCE`, default ON) | **0 of 476** davidath, **exactly 1 of 333** evaluator questions change qtype |
| `_RISK_CATEGORY_ASK_RE` verdict-ask shape in `_is_classification_question` | **0** davidath rows match |
| `migration_asylum` topic += the statutory term `irregular migration` (occurs in the Act ONLY in Annex III(7)(b)) | davidath byte-identical |
| **R305 re-ask focus** (env `REGENOLD_REASK_FOCUS`, default ON) | fires 0/111 easy, 0/111 turn-1, **62/111** challenge turns; 0 false fires on a coreference/OOS probe set |
| Stage-2 curated skip gated on `resolved_q` (the LIVE turn), not the flattened `question` | the sibling gate 20 lines below already did |
| `_detect_robotic_surgery_inquiry` gained the scenario-opener guard its 7 siblings already had | davidath curated-gate 0-hit test **RED → GREEN** |
| 3 env flags added to `_engine_cache_key` | eval integrity (R263.2) |
| Sub-paragraph clause no longer contradicts the closed-set completeness rule | prompt-only |
| 4 weakened test assertions tightened | see §4 |

### 2.3 The re-ask lever — the largest measured opportunity

The graded challenge turn ends:

```
Let's try again:
<the original question, verbatim>
```

preceded by *"provide a clear answer with the same format as before, as if I
had just asked the same question anew"*. **67/111** challenge turns carry that
shape and the trailing question matched a first-turn question **exactly
67/67**. Yet on the graded batch the challenge turn shipped answers **+376
chars and +0.64 references** longer than the identical stand-alone ask (49/67
rows longer, 31/67 more refs; worst row 749 → 2740 chars) — because the whole
flattened history still drove retrieval, `scope.anchor_articles`, and the
R88-A assistant-anchor inheritance. Honouring the instruction is both correct
behaviour and the conciseness-preserving one. Answer-Conciseness is the only
rubric axis this system leads, i.e. the one with pure downside risk.

---

## 3. Judge-remark adjudication — REAL vs FALSE POSITIVE

The operator asked specifically to separate clear issues from judge artifacts.

| Remark | Rows | Verdict | Evidence |
| --- | --- | --- | --- |
| Art 7(3) removal stated as a single condition | rg_018 | **REAL** | Verbatim 7(3): *"where **both** of the following conditions are fulfilled"* |
| "ordinary legislative procedure" unsupported | rg_018 | **REAL** | Phrase absent from all 126 articles |
| Sandbox: AI Office co-establishment fabricated; *"pursuant to a sandbox plan"* omitted | rg_038 | **REAL** | Art 3(55) verbatim |
| Annex III 7(b) conflation | rg_093 | **REAL** | *"assist in managing irregular migration"* absent from the Act |
| Over-citation of **Article 15** on explainability | rg_005 | **REAL** | Art 15 is accuracy / robustness / cybersecurity — no explainability nexus |
| Over-citation of **Article 14** on explainability | rg_005 | **JUDGE FALSE POSITIVE** | Art 14(4)(c): *"the interpretation tools and methods available"* — the only such phrase in the Regulation |
| Article 19 over-cited alongside Article 18 | rg_009 | **REAL** | Art 18(1) is a closed 5-item list; it does not mention Article 19 or logs |
| Annex XI/XII/Art 51 "tangential" on the GPAI exception | rg_013 | **JUDGE FALSE POSITIVE** | Art 53(2) relieves 1(a)+(b), whose objects **are** Annex XI/XII; the carve-out is systemic-risk (Art 51) |
| Answer truncated before Article 55(1)(d) | rg_053 | **JUDGE FALSE POSITIVE** | 55(1)(d) stated near-verbatim, followed by a complete Art 56 closing sentence |
| Omits Annex VIII completion | rg_037 | **REAL** — incompleteness, **not** cap-truncation | 442 tok vs a 2048-tok envelope |
| Gas-supply system classified limited-risk | rg_110 | **REAL** | Annex III(2) verbatim covers *"supply of water, gas, heating or electricity"*; `stage2_polish=False` |
| Never states Annex VII 5.1 | rg_098 | **REAL** — the documented raw-KB-dump mode | `stage2_polish=False`, 998 chars |
| Root cause *"complex questions exceed token headroom caps"* | rg_037/098/110 | **FALSIFIED** | Envelope 2048 tok on both tiers; longest row 442 tok; **2 of 3 rows never invoked Stage-2** |

**Consequence:** do not tune `REGENOLD_STAGE2_ANSWER_HEADROOM` for these rows.
The three named rows are three *different* defects — incompleteness, a
raw-KB-dump, and a misclassification — and two of them never reached Stage-2.

---

## 4. Scorecard corrections

| Claim | Doc value | Reproduced | Verdict |
| --- | --- | --- | --- |
| ST / MT / pooled aggregate cells (all 17) | as printed | identical | **MATCH** |
| R301 answer pass / recall / F1 / citation faithfulness | 0.3720 / 0.9410 / 0.7630 / 0.5580 | 0.3721 / 0.9412 / 0.7628 / 0.5581 | MATCH |
| **R301 mean factual score** | **0.8270** | **0.7328** | **MISMATCH** — no sidecar yields 0.827; the round's true delta is **+14.6pp**, not +5.2pp |
| **"N = 43 distinct questions"** | 43 | **38** (5 rows appear in both splits) | **FALSE** — say "43 request-instances / 38 distinct questions" |
| Deltas "+30.2% / +5.2% / …" | % | percentage **points** | **UNIT WRONG** (answer pass is +81.3% relative) |
| **`rg_038` reproduces at 421 chars** | 421 | **1005 chars, does not reproduce** | **FALSE** — the scorecard measured pre-guard code |
| `rg_018` "Answer Pass / Cite Pass" | pass | answer **fail**, reference **fail** | **FALSE** |
| `rg_038` / `rg_093` verdicts | pass | each has an **undisclosed failing axis** | **MISLEADING** |
| `rg_018` / `rg_093` cited refs | as printed | disagree with the sidecar | **MISMATCH** |
| "Latency Before ~60.0 s" (×3) | ~60 s | rg_038 7.1–16.3 s; rg_093 32–55 s | **FALSE** for 2 of 3 |
| §2 "un-curated deterministic bucket eliminated" | eliminated | grew 3 → 6, still 0% | **FALSE** |
| §4.3 davidath 0-hit / 276-runner | 0 / 255 | 0 / 255 | **TRUE** |
| §0 recall 0.973, zero missing-only | — | 0.9733 | **TRUE** |
| "Reference Recall" implies gold | implied | `gold_coverage 0.0`, `recall_is_text_grounded false` | **NO GOLD** — recall is the judge model's reading, not a gold match; not comparable across datasets |

---

## 5. The Aura knowledge graph — used, or not?

**Healthy and fully seeded, and contributing ~nothing to answers — by measured
design, not by failure.**

* `/healthz/graph`: `graph_ok: true`, seed `2026-07-24-r291-fullseed`,
  113 Article / 656 Paragraph / 416 Point / 37 SubPoint / 248 CROSS_REFERENCES.
* **All 333 graded responses have `retrieval_path: "kb_fallback"`.** That is
  the R252 design: the blunt Neo4j `obligations_for_risk_level` primary dump
  mis-anchored (it returned the generic high-risk chain for any tier), so it
  was retired and the graph demoted to an ADDITIVE 2-hop path.
* The additive path is then zeroed at the fusion cap: `fuse_with_kb_xrefs` is
  called with `winners == budget`, so `remaining = 0`. Measured in R295 over
  the 132-row probe set: **660 hop2 refs available, 4 added (~99.4%
  discarded)**.
* Opening it is **measured-negative** and is item 7 on the do-not-repropose
  list: with `REGENOLD_GRAPH_FUSE_SLACK=2`, `st_v4_002` went from a perfect
  `['Article 5']` to `['Article 2','Article 27','Article 49']` — gold
  destruction, the R142.1 failure mode.

So the honest answer is: the graph is available and correct, it is **not** the
lever, and two prior rounds measured that forcing it to contribute more makes
answers worse. The remaining precision-safe uses (definition lookup, recital
context, the R110 bounded sufficient-context hop) are wired and fire on their
own gates.

---

## 6. Gates on the shipped fix set (branch `r305-review-fixes`)

| Gate | Result |
| --- | --- |
| davidath 476 vs `main` a83bbcc, isolated worktree | **byte-identical on every axis** — Ans Loose 0.1879 / Ans Strict 0.3526 / Ans Conc 0.615 / Ref Loose 0.5967 / Ref Strict 0.4744 / Ref Conc 0.4319 / Tone 1.0 / multi-turn 20/20 |
| davidath QA 137 | matches the documented baseline exactly (0.1402 / 0.4032 / 0.198 / 0.8394 / 0.5543 / 0.4395 / 1.0) |
| `evals.regenold.runner` (276) | **255/255 (100%)**, RISK_F1 macro 1.00, every category 100% |
| OOS probe (`--oos-suite all`) | **0 scope leaks** |
| davidath curated-gate 0-hit guard | **RED → GREEN** (was 1 hit via `_detect_robotic_surgery_inquiry`) |
| New tests | +24 `tests/test_r305_review_fixes.py` (every test uses the VERBATIM evaluator question, never an abbreviation) |

**Live verification** (in-process route + Claude Max wrapper, Opus):

* sandbox → now returns the **verbatim Article 3(55) definition** including
  *"pursuant to a sandbox plan"* and *"where appropriate in real-world
  conditions"* — the two elements the R304 hardcode omitted. Refs
  `['Article 3.55', 'Article 57', 'Article 1']`.
* migration → now cites **Annex III point 7(b)** and quotes the actual
  statutory language (*"to assess a risk, including specifically a risk of
  irregular migration, posed by a natural person who intends to enter..."*) —
  exactly the characterisation the hardcode got wrong.
* amendment → refs unchanged (`Article 7` present) but the prose leads with
  Article 6(6) rather than Article 7(1). **Open item** — see §7.

---

## 7. Open items, ranked, with the instrument that gates each

1. **`amend Annex III` leads with Article 6(6), not Article 7(1).** Art 6(6)
   amends the Art 6(3) derogation conditions — a different power from Art 7(1)
   (amending Annex III itself). Refs are right, the lead is wrong.
   *Gate:* `evals.harness.ab_judge` live pairwise (Stage-2 answer content).
2. **A/B the sub-paragraph clause** — shipped default-ON by R304 with no A/B,
   and its cache-key entry was missing (so any earlier in-process A/B measured
   nothing). Now keyed.
   `python -m evals.harness.ab_judge --label r305-subpara --baseline-env REGENOLD_SUBPARAGRAPH_ATTRIBUTION=0 --branch-env REGENOLD_SUBPARAGRAPH_ATTRIBUTION=1 --judge-provider wrapper`
3. **`rg_005` Article 15 drop on explainability** — the one reference-precision
   item with a real legal basis (Art 14 is NOT — see §3).
   *Gate:* live pairwise; it is a Stage-2 content change.
4. **`rg_110` gas-supply misclassification** — Annex III(2) verbatim covers gas
   supply; `stage2_polish=False`, so this is a deterministic classification
   gap, gateable deterministically.
5. **`rg_098` raw-KB-dump mode** — the documented R301 defect (a Stage-2
   double-failure ships the Stage-1 KB dump whose lead ref has a noun-phrase
   summary). That composer IS the davidath path, so it needs its own round.
6. **`GEMINI_API_KEY` unset on Railway** — the documented Stage-2
   Groq→Gemini→Mistral fallback chain collapses to the deterministic dump.
   Operator action, zero code, cheapest available reliability win.

**Do not do** (measured-refuted; re-proposing any of these is a review
failure): positional / top-N / budget reference clamps; pushback-turn
reference freeze; prose-driven "drop cited-but-undescribed" pruners;
completeness instructions; answer length caps / re-sentencers;
article-identity blocklists; `REGENOLD_GRAPH_FUSE_SLACK > 0`; and tuning
`REGENOLD_STAGE2_ANSWER_HEADROOM` for the §3 truncation rows (falsified).

---

## 8. New evaluation surfaces built this round

* **`evals/regenold/evaluator_batch_july7.py`** — parses the raw 333-request
  export (111 easy / 111 hard turn-1 / 111 hard turn-2), exposes the
  conversation pairing, the pushback template and a `pairing_report()` that
  states how much is exact vs reconstructed. 18 data-integrity tests.
* **`evals/regenold/run_evaluator_batch_july7.py`** — replays easy and/or hard
  against `--local` or `--endpoint`, records the 2026-07-07 shipped answer for
  a then-vs-now diff plus pushback concession, and writes a judge-compatible
  sidecar.
* **`evals/judge/legal_v2.py`** — the upgraded judge. Four axes; **three-way**
  reference classification (`GOVERNING` / `SUPPORTING` / `WRONG`, where
  SUPPORTING can never fail — this is the direct fix for the §3 false-positive
  class); **quote-or-retract** substantiation (an adverse verdict without an
  ≥8-word literal quote from the supplied verbatim text is downgraded and
  logged); Chain-of-Verification on the answer axis with an explicit
  omission-vs-fabrication split; optional self-consistency (`--samples K`,
  majority/median + per-row agreement); a strict key allowlist so the judge
  never sees the arm, the label or the baseline; anti-sycophancy calibration;
  and a **conciseness** axis the old judge lacked (the rubric axis with zero
  headroom). 29 offline tests.
