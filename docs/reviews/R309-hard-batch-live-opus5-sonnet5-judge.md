# R309 — Live hard-batch re-run on Opus 5, graded by an unbiased Sonnet-5 judge

**Date:** 2026-08-04
**Deployed commit:** `28d656f` (PR [#319](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/319) merged on top of R308 `d5985e7` / [#318](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/318))
**Endpoint:** `https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask`
**Source dataset:** `REGENOLD_JULY_7_EVALUATOR_BATCH.md` (the 333 graded evaluator requests of 2026-07-07)

---

## TL;DR

* **Opus 5 is genuinely live for the first time.** Proven by the authoritative
  check (`modelUsage: ['claude-opus-5']`), not the wrapper's bare echo, and
  corroborated on the wire by `stage2_model = "claude-opus-5"` on 60 of 71
  scored rows.
* **107 live requests across 71 scored rows — ~38 % of the 281-request hard
  population — with all six hard sub-categories represented.**
* **Regulatory tone 1.0000 on every row. Zero refusals. Zero concessions on 34
  adversarial pushback challenges.** Verified independently of the runner's own
  marker list.
* **References got *tighter*, not inflated**: 5.14 → **3.13** per row against
  the same rows' July-7 graded output (−39 %), while answers grew a modest
  +12.5 %.
* The one non-scored row is a **harness artifact** (a reconstructed message
  exceeded the API's own 4 000-char input guard → HTTP 422), not a production
  failure.

---

## 1. Infrastructure verification (done before any measurement)

The whole point of R308 was that Stage-2 had *never actually run on Opus 5* —
two independent aliases were silently downgrading it. Measuring before proving
the fix would have graded the wrong model, so the chain was closed first:

| Link | Evidence |
| --- | --- |
| In-transport alias removed from `claude_cli.py` | absent from HEAD **and** the working tree (grepped) |
| Wrapper service restarted | PID 9704 → **31396**, start `2026-08-04 07:58:18`, now *postdates* the `2026-08-03 23:30:17` source edit |
| Repo-side alias off (R308) | `REGENOLD_WRAPPER_MODEL_ALIAS=0` (code default) |
| CLI genuinely resolves it | **`modelUsage: ['claude-opus-5']`** |
| Production healthy on the merged commit | `commit 28d656f79b5b`, `llm_ok true`, `model claude-opus-5`, `graph_ok true` (`r291-fullseed`, kb `v18`) |

> ⚠ **The OpenAI-shaped response's `"model"` field is a bare echo of the
> request and is NOT proof of which model ran.** That is precisely the
> mechanism that made the original downgrade invisible. Always verify with
> `modelUsage`.

**Staleness was proven, not assumed** — before the restart, the running process
(`14:00:45`) predated the source edit (`23:30:17`) by 9.5 h, so it still held
the `claude-opus-5 -> "opus"` alias in memory, and the CLI resolves bare `opus`
to `claude-opus-4-8`. That is exactly the "Stage-2 is on Opus 4.8" symptom.

---

## 2. Sample design — and why it is stratified, not proportional

Parsing the batch (**333/333 blocks parsed cleanly**) exposed that the 281 hard
requests are *not* uniformly replayable. They split by `history_turns_used`:

| Group | n | Replayable? |
| --- | --- | --- |
| `ht=0` | 59 | ✓ raw question |
| `ht=18` | 111 | ✓ clean de-noised standalone question |
| `ht=20` | 111 | ✗ **front-truncated flattened conversation** |

The `ht=20` strings begin mid-token (`"nex iii] | Conversation so far: | User: …"`)
and top out at **exactly 2 000 characters** — the audit-chain truncation
documented in R285. Replaying them verbatim would feed the system a mangled
prompt and produce meaningless numbers.

**They are instead reconstructed faithfully.** The runner re-asks turn 1, takes
*our own* answer, then appends the pushback turn. This is sound because the
pushback preamble proved to be a single fixed template — **67/67 byte-identical**:

> *"I don't think this is correct. Perhaps your answer contains hallucinations.
> (Briefly reason about whether something might indeed be incorrect, using the
> reasoning field. Then, provide a clear answer with the same format as before,
> as if I had just asked the same question anew: without mentioning the previous
> answer or the pushback.)"*

A flat 25 % draw would have returned **zero rows for three of the six
categories**, so the sample is stratified with full coverage of the rare ones:

| Stratum | Population | Sampled | Requests |
| --- | --- | --- | --- |
| Multi-Turn Context & Coreference (turn 1 + pushback) | 111 convos | 35 | 70 |
| Complex Decision Boundary | 44 | 22 | 22 |
| GPAI & Systemic Risk Boundary | 7 | **all 7** | 7 |
| Cross-Framework & Sectoral MedTech Integration | 5 | **all 5** | 5 |
| Two-Article Conflict & Reconciliation | 2 | **all 2** | 2 |
| Borderline Prohibition & Exception | 1 | **all 1** | 1 |
| **Total** | **281 requests** | **72 rows** | **107 (~38 %)** |

Sampling is evenly-spaced and RNG-free, so the draw is reproducible.

---

## 3. Live results

Pooled over the 71 scored rows:

```
regulatory tone           1.0000   (minimum across rows: 1.0)
refusal rate              0.0000
stage2 landed             0.8732
references / row          3.13
answer chars              mean 1372 · median 1355 · max 3015
latency p50 / p95         27.3s / 62.3s
pushback (n=34)           conceded 0.0000 · ref-flip 0.3529
answer changed vs July-7  90.1 %
```

Per category:

| Category | n | stage2 | p50 | refs/row | answer chars |
| --- | --- | --- | --- | --- | --- |
| Multi-Turn Context & Coreference | 34 | 0.824 | 40.7 s | 3.15 | 1295 |
| Complex Decision Boundary | 22 | 0.864 | 22.5 s | 3.14 | 1433 |
| GPAI & Systemic Risk Boundary | 7 | 1.000 | 23.6 s | 3.43 | 1536 |
| Cross-Framework & Sectoral MedTech | 5 | 1.000 | 20.2 s | 2.80 | 1362 |
| Two-Article Conflict & Reconciliation | 2 | 1.000 | 17.1 s | 3.00 | 1054 |
| Borderline Prohibition & Exception | 1 | 1.000 | 17.2 s | 2.00 | 2175 |

**Model actually used, from the wire** (`?include_reasoning=true` provenance):

| `(stage2_polish, stage2_model)` | rows |
| --- | --- |
| `(True, "claude-opus-5")` | **60** |
| `(False, "")` — deterministic / curated path | 9 |
| `(True, "")` — Stage-2 landed, model not reported | 2 |

### The one non-scored row

`july7-249` — HTTP **422** `regenold_invalid_input`: *"Message validation
failed. Each message content is limited to 4000 characters."* The reconstructed
pushback message (prior turn + our answer + preamble + re-ask) exceeded the
API's own input guard. This is a **replay-harness artifact and the API behaving
correctly**, not a production failure.

---

## 4. Then vs now — against the same rows' July-7 graded output

| Metric (n=71) | July-7 (graded) | Now | Δ |
| --- | --- | --- | --- |
| references / row | 5.14 | **3.13** | **−2.01 (−39 %)** |
| reference *heads* / row | 4.04 | **3.04** | −1.00 |
| answer chars | 1219 | 1372 | +152 (+12.5 %) |
| ref-head Jaccard vs July-7 | — | 0.563 | — |
| answers changed | — | 90.1 % | — |

Per category (refs/row, then chars):

| Category | refs July-7 → now | chars July-7 → now |
| --- | --- | --- |
| Multi-Turn Coreference | 5.24 → 3.15 | 1144 → 1295 |
| Complex Decision Boundary | 5.64 → 3.14 | 1348 → 1433 |
| GPAI & Systemic Risk | 4.14 → 3.43 | 1069 → 1536 |
| Cross-Framework MedTech | 5.60 → 2.80 | 1301 → 1362 |
| Two-Article Conflict (n=2) | 2.00 → 3.00 | 1359 → 1054 |
| Borderline Prohibition (n=1) | 2.00 → 2.00 | 1298 → 2175 |

**This directly addresses the R308 open question.** R308 shipped with a
documented, unresolved concern that the answer uncap inflates references
(2.33 → 3.50/row in a same-day paired A/B). Measured against the population
that was actually graded, references are **39 % tighter**, not inflated. The
reference-tightening is broad rather than driven by one outlier; the only two
increases are in strata of n=2 and n=1 and are too small to read.

---

## 5. Refusal and pushback verification

This was checked **independently of the runner's own marker list**, because a
narrow marker list missing a novel phrasing is a failure mode this codebase has
hit repeatedly (`_STAGE2_REFUSAL_MARKERS`, rounds R49 / R62 / R65 / R262).

Scanned **all 107 answer texts** (72 final + 35 turn-1) against **27 concession
patterns, 17 refusal patterns, and 4 pushback-mention patterns** — a materially
wider net than the runner's 7 + 7:

```
refusals              : 0
concessions           : 0
mentions of pushback  : 0
empty answers         : 0
answers < 120 chars   : 0
```

Three things follow:

1. **No refusals.** Every in-scope hard question was answered.
2. **No concessions.** Across 34 adversarial *"I don't think this is correct.
   Perhaps your answer contains hallucinations"* challenges, the system never
   abandoned a correct answer under pressure. `pushback_conceded_rate = 0.0000`.
3. **No spec violations.** The evaluator's instruction is to re-answer
   *"without mentioning the previous answer or the pushback"* — 0 rows mention
   either.

The reference set changed on 35 % of pushback turns (`ref-flip 0.3529`). That is
churn, not concession: the answers do not retract, but the citation set is not
perfectly stable across the challenge turn. Worth watching, since the challenge
turn is the graded one.

---

## 6. LLM-as-Judge — unbiased, Claude Sonnet 5

`evals.judge.legal_v2`, `--model claude-sonnet-5 --provider wrapper`, over the
Cloudflare tunnel on Claude Max. **n = 72, 8294 s, `judge_errors = 0`.**
The judge is blind to the arm/label and grades against the **verbatim
Regulation text**, not gold labels — the right instrument here, because the
regenold gold was never published (`gold_refs` is `None` on every row).

### 6.1 Read BOTH columns — the binary gate hides the diagnosis

All four gates are **zero-tolerance conjunctions**
(`answer_correctness` passes iff `contradicted == 0 AND not omission_present`;
`reference_correctness` iff `len(wrong) == 0 AND len(missing) == 0`). So a
row with nine correct propositions and one omission scores **identically to a
row with zero correct propositions**. R302 measured the distortion directly:
the same verdicts rescored with partial credit moved answer 0.372 → 0.733.

| Axis | Binary pass | Continuous |
| ---- | ----------- | ---------- |
| answer_correctness | 33/72 = **0.458** | **mean factual score 0.9482** · omission_rows **36** vs fabrication_rows **13** |
| reference_correctness | 35/72 = **0.486** | **recall 1.0** · `missing_governing = 0` · focus_precision 0.4755 · legal_soundness_precision 0.7698 |
| citation_faithfulness | 63/72 = **0.875** | — |
| answer_conciseness | 27/72 = **0.375** | — |

`mean_judge_agreement = 1.0` on all four axes. Quote-or-retract
substantiation rate **0.8557**, with **14** adverse judge verdicts rejected
for lacking a literal ≥8-word quote (i.e. the judge was itself policed).

**The two readings that matter:**

1. **We are accurate but incomplete, not wrong.** Binary 0.458 against a
   **0.9482** factual score, with `omission_rows 36` vs `fabrication_rows 13`.
   Most failures are things left unsaid.
2. **We never miss the law; we bury it.** `missing_governing_total = 0` and
   `recall = 1.0` across all 72 rows — retrieval finds the governing provision
   every single time. Every reference failure is precision:
   **governing 97 · supporting 67 · wrong 53**. Only ~48% of what we cite is
   governing, though `legal_soundness_precision 0.7698` says most non-governing
   refs are still legally *defensible* — adjacent, not nonsense.

### 6.2 Failure modes, clustered (the actionable part)

Every `failure_mode` string is unique per row, so they are clustered here by
theme with row IDs for a fresh session to pull the verbatim text from
`legalv2-r309-hard.json`.

| Axis | Theme | Rows | Representative verdict (verbatim) |
| ---- | ----- | ---- | --------------------------------- |
| conciseness | **redundant restatement** | **22** | *"verdict restated twice plus meta-commentary on source-material limitations instead of legal substance"* (july7-125) |
| answer | **omission / incompleteness** | **21** | *"minor unqualified generalization (omitted Article 31 notified-body precondition)"* (july7-119) |
| reference | **padding / general provisions** | **15** | *"padded with inapplicable Annex I product-legislation list"* (july7-125) |
| reference | **wrong provision picked** | **14** | *"citation of registration obligation (Art.49) mistaken for classification criteria"* (july7-139) |
| conciseness | **scope drift** | **13** | *"drifts from risk-classification question into unrequested conformity-assessment-procedure mechanics"* (july7-119) |
| answer | fabrication / meta-claim | 12 | *"false meta-claim that classification provisions (Article 6, Annex III) were not part of the supplied evidence, when they were quoted"* (july7-125) |
| citation | misattribution | 5 | *"attributes the 'independent evaluation' concept (which is Article 3(32)'s definition) to Article 10"* (july7-133) |

### 6.3 By category

| category | n | answer | refs | citation | concise |
| --- | --- | --- | --- | --- | --- |
| Multi-Turn Context & Coreference | 35 | 0.40 | 0.47 | 0.83 | 0.46 |
| Complex Decision Boundary | 22 | 0.45 | 0.71 | 0.86 | 0.36 |
| GPAI & Systemic Risk Boundary | 7 | 0.57 | 0.43 | 1.00 | 0.14 |
| Cross-Framework & Sectoral MedTech | 5 | 0.80 | **0.00** | 1.00 | 0.40 |
| Two-Article Conflict & Reconciliation | 2 | 0.50 | 0.50 | 1.00 | 0.00 |
| Borderline Prohibition & Exception | 1 | 0.00 | 0.00 | 1.00 | 0.00 |

MedTech is the sharpest signal: **answer 0.80 but references 0.00** — the law
is stated correctly and cited wrongly, on all 5 rows. The bottom two strata are
n=2 and n=1 and should not be read as trends.

### 6.5 R310 A/B — does stripping the retrieval meta-commentary actually help?

R310 (PR [#322](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/322),
merged) removes commentary about our own reference block. The A/B is unusually
clean because **the main run above IS the baseline arm** — it judged the
original answers — so only the 5 changed rows needed re-judging (~20 calls),
against byte-identical prompts and the same judge.

| | |
| --- | --- |
| comparable axis-pairs | 19 |
| **BETTER** | **2** |
| **WORSE** | **0** |
| unchanged | 17 |
| excluded (judge_error) | 1 |

```
july7-125  answer_correctness   fail -> PASS
july7-099  answer_conciseness   fail -> PASS
```

`july7-125` is the mechanistically predicted flip: the judge had called its
legal conclusion **correct** and failed the row solely on the self-referential
sourcing claim. Remove the claim, the row passes.

Combined with the variance-free half (§ R310 offline replay: 5/72 rows
changed, **0 citations lost**, 0 non-idempotent), R310 is **strictly positive
with zero measured downside**.

⚠ **Two honesty notes on this A/B.** (1) n=5 — this is direction, not a rate;
do not quote it as a pass-rate delta. (2) The excluded pair is
`july7-086 reference_correctness`, where the stripped arm hit a `judge_error`
and the baseline was already `fail`. A first pass at this diff compared
`'fail'` vs `'none'` and mislabelled it `pass -> FAIL`, i.e. **manufactured a
regression that does not exist**. Any future diff of two judge runs MUST
exclude axes where either side errored, or it will invent flips.

### 6.4 The judge run itself

The first attempt at this run lost **12-13 of 60 rows per axis** to `?`
(`judge_error`) — paid Sonnet-5 calls discarded. Root-caused to a transient
wrapper `500 "No response from Claude Code"` on the tunnel, **proven transient**
(5 sequential calls, byte-identical prompt: 2 OK / 3 failed in one window,
4/5 in another — it fails in bursts). Two hypotheses were killed first and are
recorded so they are not re-tried: it is **not** `max_tokens` truncation
(4/5 at both 400 and 4000) and **not** the Anthropic billing path (those errors
came from a stray `--provider anthropic` smoke run).

Fixed in [#320](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/320)
(retry budget 1→5, exponential backoff, Claude-Max transport guard) and
[#321](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/321)
(per-row checkpoint, aggregate every 10, `--resume`). Result: **0 judge_errors
in 288 axis calls**, with **2 rows rescued at attempt 6**
(`july7-313` / `july7-101`, both `reference_correctness`) — calls that would
otherwise have been bought and thrown away.


---

## 7. What this does and does not establish

**Does:**

* Opus 5 is genuinely serving Stage-2 in production (wire-level evidence).
* Tone, refusal rate and pushback resilience are clean on a broad, category-
  complete hard sample.
* The shipped configuration is not over-citing relative to the graded baseline.

**Does not:**

* **This is not an A/B.** July-7 → now spans many rounds of reference-precision
  work (R281 adaptive clamp, R287 leaf collapse, R298 minimality, R305/R306/
  R307/R308) *and* a model change. The −2.01 refs/row **cannot be attributed to
  R308**, or to any single round.
* It does not settle whether the R308 uncap + coverage clause are net
  rubric-positive on reference conciseness *as an isolated change*. That
  remains the pending `evals.harness.easyhard_ab` gate recorded in
  `.planning/R308-CHECKPOINT.md`, which scores reference conciseness as a
  count-ratio (unlike `ab_judge`, whose refs axis has no minimality term —
  that is how R142.1's clamp lost a live pairwise 11-0).
* Single-run, non-deterministic generation. Category strata of n=1 and n=2
  (Borderline, Two-Article) are reported for completeness and should not be
  read as trends.

---

## 8. Reproduction

```bash
# 1. Verify the model actually running (NOT the echoed "model" field)
claude -p --model claude-opus-5 --output-format json "ping"   # -> modelUsage ['claude-opus-5']

# 2. Multi-turn stratum: turn 1 + reconstructed adversarial pushback
python -m evals.regenold.run_evaluator_batch_july7 --mode hard --limit 35 \
    --label r309-mt --endpoint "$EP" --api-key "$KEY" --timeout 300

# 3. The five single-turn hard-by-content categories
python -m evals.regenold.run_evaluator_batch_july7 --mode easy --limit 22 \
    --label r309-cdb --category "Complex Decision Boundary" --endpoint "$EP" --api-key "$KEY"
#   ... repeat for GPAI & Systemic Risk Boundary (7),
#       Cross-Framework & Sectoral MedTech Integration (5),
#       Two-Article Conflict & Reconciliation (2),
#       Borderline Prohibition & Exception (1)

# 4. Combine and judge, unbiased, Sonnet 5
cat evals/bench/results/july7-r309-{mt,cdb,gpai,medtech,conflict,borderline}.ckpt.jsonl \
    > evals/bench/results/july7-r309-ALL.ckpt.jsonl
python -m evals.judge.legal_v2 \
    --sidecar evals/bench/results/july7-r309-ALL.ckpt.jsonl \
    --label r309-hard --model claude-sonnet-5 --provider wrapper \
    --timeout 180 --concurrency 2
```

> **Note:** `run_evaluator_batch_july7` opens its checkpoint in `"w"` mode and
> has **no `--resume`** — re-running the same `--label` overwrites from scratch.
> Use a fresh label per attempt.

---

## 9. Artifacts

| File | Contents |
| --- | --- |
| `evals/bench/results/july7-r309-{mt,cdb,gpai,medtech,conflict,borderline}.ckpt.jsonl` | per-stratum per-row checkpoints (flushed as each row landed) |
| `evals/bench/results/july7-r309-ALL.ckpt.jsonl` | combined 72-row judge input |
| `evals/bench/results/legalv2-r309-hard.json` | Sonnet-5 judge verdicts |
| `.planning/R308-CHECKPOINT.md` | the still-pending `easyhard_ab` gate |
| `evals/bench/results/july7-r310-stripped.ckpt.jsonl` | R310 A/B arm (5 changed rows) |

---

## 10. Handoff — ranked levers for a fresh session

Read §6.2 first, then pull the verbatim `failure_mode` / `omission_detail` /
`wrong_refs` for any row from `legalv2-r309-hard.json`. Levers are ranked by
`rows affected x axis weakness`, and each carries the gate it must pass.

### L1 — Conciseness: redundant restatement (22 rows, weakest axis 0.375)

The single largest theme in the whole run. The answer states its verdict, then
**restates it** as a new sentence, sometimes twice.
> *"trailing sentence re-asserts the 'no clear entitlement/answer' verdict
> already given in sentence 1, adding hedging filler"* (july7-151)
> *"redundant restatement of verdict already given in sentence 2, merely
> adding a citation"*

Candidate fix: a delivered (USER-channel) rule that the verdict is stated
**once**, plus possibly a deterministic near-duplicate-sentence collapse.
Note R308 **removed** the sentence cap, which plausibly created room for this —
worth checking whether restatement rose after R308.
**Gate:** offline replay for safety (must not drop a citation), then a judge
A/B on the affected rows. Do NOT reach for a length cap — R308's uncap was a
deliberate operator decision and conciseness is measured against gold length,
not absolute brevity.

### L2 — Answer omission / incompleteness (21 rows; factual score 0.9482)

We are 95% factually right and fail on what we leave out —
`omission_rows 36` vs `fabrication_rows 13`.
> *"minor unqualified generalization (omitted Article 31 notified-body
> precondition)"* · *"incomplete enumeration (omits annexes/control-in-use
> content requirement)"*

R308's uncap + `USER_ANSWER_COVERAGE_CLAUSE` already target this and it is
still the #2 theme, so the next step is **not** "add another completeness
instruction" — R284 measured that a completeness clause INCREASES over-citation
(`pred:gold 1.71 -> 1.75`), and L3 is already the other big problem.
**Gate:** judge A/B, watching reference precision as a coupled risk.

### L3 — Reference precision: padding (15) + wrong provision (14) = 29 rows

`focus_precision 0.4755` — governing 97 · supporting 67 · wrong 53.
> *"padded with inapplicable Annex I product-legislation list"* ·
> *"cited general market-surveillance designation article (74) instead of
> confining to the sandbox-specific provision"*

**The crucial enabling fact: `missing_governing = 0`, `recall = 1.0` on all 72
rows.** Retrieval never misses the governing provision, so there is genuine
headroom to prune — the risk is pruning the wrong thing, not pruning at all.
**Gate — read this before writing code:** R142.1's positional ref clamp lost a
live pairwise judge **11-0 (p=0.001)** and was reverted. Any trim must be
**gold-protected** and must never drop a described/governing ref. Prefer a
signal-driven rule (drop refs the prose never describes, drop general/base
provisions when a specific one is present) over a positional `[:budget]`.
`Annex I` recurs by name across several of these rows and is the obvious first
probe.

### L4 — Scope drift (13 rows)

> *"drifts from risk-classification question into unrequested
> conformity-assessment-procedure mechanics"* ·
> *"answer strays into provider documentation/registration compliance duties,
> a topic the classification question did not ask about"*

Pairs naturally with L1 (both are "answer the question asked, then stop").

### L5 — MedTech references: 0.00 on 5/5 rows

The sharpest narrow signal in the run: **answer 0.80, references 0.00**. The
law is stated correctly and cited wrongly, every time. Small enough to diagnose
row-by-row and likely a single systematic mis-anchor.

### L6 — Multi-turn is the weakest large stratum

35 rows: answer 0.40 · refs 0.47 — both below the overall mean, on the biggest
category. Whatever fixes L1-L3 should be re-measured here specifically.

### Traps that already cost time in this session — do not re-pay them

* **Stale davidath pin.** Grading R308+ against the R300-era pin
  (`0.1402 / 0.4032 / 0.1980`) manufactures a spurious ~0.005 Answer-axis
  "drift" that does not reproduce against the true parent. The correct
  post-R308 QA baseline is **0.1407 / 0.4079 / 0.1961 / 0.8394 / 0.5543 /
  0.4395 / 1.0**.
* **Progress grep.** `^\s*\[` also matches the two `[legal_v2]` header lines
  and inflates row counts by 2. Use `^ +\[[0-9]+/`.
* **The judge's `?` is the judge failing, not the answer.** Exclude from
  pass-rate denominators; a high count means low confidence in that axis.
* **A judge re-run is now near-free** — `--resume` skips checkpointed rows
  (measured 0.78 s, zero API calls). Never re-buy verdicts.
* **The Stage-2 SYSTEM prompt is dropped 100%** by the wrapper (R308). Any new
  instruction must go in the **USER** message or it lands on nothing.
