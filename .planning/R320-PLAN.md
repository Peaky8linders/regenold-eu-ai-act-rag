# R320 — final evals session: hard-batch numbers vs the OFFICIAL frontier

**Authoritative handoff. Written at the end of R319 (2026-08-07).**
Read `CLAUDE.md` (hard rules + Validation policy + Fresh-session plug-in) first.
Everything here is measured or verified; where it isn't, it says so.

---

## 0. State at handoff

* **Production is on `5e903b8`** (verified live: `/healthz/llm` → `commit
  5e903b81cc7f`, `provider=openai_wrapper`, `model=claude-opus-5`, `llm_ok=true`,
  CF Access headers attached). R319 **is** deployed.
* R319 shipped (PR #329/#330): `REGENOLD_SUFFICIENT_CONTEXT` default reverted
  OFF→**ON**; the LLM judge's answer window raised 1400→6000; `_article_key`
  made idempotent for Annexes; Fresh-session plug-in rewritten.
* Gates green: davidath 476 identical, 276-runner 0 fails, OOS 0 leaks, suite
  5773 collected / 0 errors.

---

## 1. TWO CORRECTIONS TO PRIOR ROUNDS — read before planning anything

### 1a. We have been benchmarking against the WRONG frontier

`evals/harness/frontier_baseline.py` runs `claude-opus-5` with **no retrieval,
no search, no tools** — deliberately handicapped. Every "we beat frontier on Ref
Loose / keyword recall" claim in R317-R319 is against THAT opponent.

The **official** 2026 baseline is a frontier model **with a live web search
tool**. Against the real one we lead **exactly one axis in each mode**
(Ans. Conciseness). **Retire `frontier_baseline.py` from the "are we SOTA?"
question**, or relabel it explicitly — it flatters us by roughly 20 pp.

### 1b. The official Overall formula IS reproducible (CLAUDE.md said otherwise)

CLAUDE.md records "No official formula is disclosed for ANY of the 8 axes".
True **per-axis**, but the AGGREGATION is now confirmed: the plain **geometric
mean of the 8 axes** reproduces the report to within 0.06 pp —
easy **77.44 vs 77.5**, hard **73.00 vs 73.0**. That makes per-axis leverage
computable, which is what section 3 uses.

---

## 2. The official scorecard (from `docs/Antifragile-Regenold-benchmark-report-preview.pdf`)

Benchmark scope note from the report: regulation 2024/1689 as of **1 May 2026**;
subsequent amendments/corrigenda/delegated acts are **not** considered. (This
vindicates the R316 pre-Omnibus CELEX pin — do not "update" to post-Omnibus.)

### Easy mode

| Contestant | Overall | AnsL | AnsS | AnsCon | RefL | RefS | RefCon | Tone | Speed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 Frontier + Search | **88.1** | 94.4 | 89.1 | 89.1 | 96.1 | 78.5 | 80.7 | 100.0 | 79.7 |
| 2025 Search-Integrated | **80.9** | 83.8 | 70.9 | 90.3 | 79.9 | 52.0 | 86.9 | 99.1 | 95.5 |
| **Antifragile AI** | **77.5** | 72.1 | 63.6 | **96.0** | 85.2 | 58.8 | 79.3 | 98.5 | 75.1 |

### Hard mode

| Contestant | Overall | AnsL | AnsS | AnsCon | RefL | RefS | RefCon | Tone | Speed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 Frontier + Search | **87.4** | 92.0 | 84.8 | 92.2 | 94.6 | 74.1 | 79.1 | 100.0 | 85.2 |
| 2025 Search-Integrated | **83.2** | 87.6 | 76.7 | 90.3 | 82.7 | 55.4 | 85.0 | 99.7 | 97.3 |
| **Antifragile AI (Hard)** | **73.0** | 74.0 | 60.6 | **93.4** | 78.7 | 56.0 | 72.1 | 98.2 | 61.7 |

We beat **0 baselines** in both modes. Gaps: easy −10.7 pp (2026) / −3.4 pp
(2025); hard −14.4 pp (2026) / −10.2 pp (2025).

**Note what this reframes:** references are NOT where we are worst — we actually
BEAT the 2025 baseline on Ref Strict (56.0 vs 55.4). **Answers and speed are.**

---

## 3. Per-axis leverage on Overall — prioritise by THIS, not by what's interesting

Computed by substituting the 2026-frontier value on one axis at a time and
recomputing the geometric mean.

| hard-mode lever | ours → frontier | Overall gain |
| --- | --- | --- |
| **Ans Strict** | 60.6 → 84.8 | **+3.13 pp** |
| **Speed** | 61.7 → 85.2 | **+3.00 pp** |
| Ref Strict | 56.0 → 74.1 | +2.60 pp |
| Ans Loose | 74.0 → 92.0 | +2.01 pp |
| Ref Loose | 78.7 → 94.6 | +1.70 pp |
| Ref Conciseness | 72.1 → 79.1 | +0.85 pp |
| Tone | 98.2 → 100.0 | +0.17 pp |
| Ans Conciseness | 93.4 → 92.2 | **−0.12 pp — matching them LOSES us points** |

Easy mode ranks: AnsS +3.33, RefS +2.85, AnsL +2.65, RefL +1.17, Speed +0.58,
RefCon +0.17, Tone +0.15, AnsCon −0.72.

**No single axis buys more than ~3 pp against a 14.4 pp gap** — this needs ~5
axes moving. And **Ans Conciseness must be actively PROTECTED**: it is the one
axis we lead in both modes and moving toward frontier on it costs points.

### ⚠ Open question R319 created — Speed vs Ref Loose

R319 reverted the Sufficient-Context gate to ON because OFF dropped gold refs
(ref_loose −0.1357, p=0.039). But the measured cost is **latency: 30.1 s (ON) vs
17.0 s (OFF)** on the ~26% of rows where the hop fires. Ref Loose's ceiling is
+1.70 pp; **Speed's is +3.00 pp**. So the revert may be net-NEGATIVE on the
official scorecard. It was optimised against ref recall, not against Overall.
**Re-A/B it with an official-shaped objective** (see step 5). One env var:
`REGENOLD_SUFFICIENT_CONTEXT=0`.

---

## 4. The dataset — use the right subset

`REGENOLD_JULY_7_EVALUATOR_BATCH.md` (16,435 lines) is the authoritative batch:
**333 requests**, each with full request + response JSON, including the
**July-7 answers that produced the official 77.5 / 73.0**.

Verified structure:

```
history_turns_used:   0 -> 111    18 -> 111    20 -> 111      (333 total)
header labels:        EASY MODE 52     HARD MODE 281
cross-tab:            EASY/single 52   HARD/single 59   HARD/multi 222
```

⚠ **TRAP.** The markdown's `EASY MODE` / `HARD MODE` headers are **our own**
`july7_difficulty.py` classification, NOT regenold's modality. The report
defines easy = no conversation history, hard = multi-turn. So:

* **regenold easy mode = the 111 single-turn requests** (`history_turns_used=0`)
* **regenold hard mode = the 222 multi-turn requests** (turns 18 and 20)

Using the 281 `HARD MODE`-labelled rows would silently mix 59 regenold-EASY rows
into a hard-mode comparison.

Already in the repo: `evals/regenold/official_batch.py` (110 unique questions as
`OfficialRow` with `jul07_answer` / `jul07_refs` / `difficulty`),
`evals/regenold/evaluator_batch_july7.py` (parser),
`evals/regenold/run_hard_sample_r297.py` (stratified live runner),
`evals/regenold/diff_hard_sample.py` (per-row diff, stratified on
`stage2_polish`). **There is NO gold** — regenold never published it — so
scoring is the grounded judge against verbatim Act text, plus then-vs-now.

---

## 5. The plan

### Step 1 — re-judge a recorded arm with the fixed judge (0 live calls) — DO FIRST

R319 raised the judge's answer window 1400→6000. **Any new judged number is
incomparable to `legalv2-r309-hard.json` or older `grounded-*` until this runs.**

```bash
.venv/Scripts/python.exe -m evals.judge.legal_v2 \
  --sidecar evals/bench/results/july7-r309-ALL.ckpt.jsonl \
  --label r320-rejudge-fixedwindow --provider wrapper
```

Only the **36 rows over 1400 chars** can change (the other 36 get a byte-identical
prompt) — stratify the read on that. Prediction to test: `citation_faithfulness`
may get **worse**, because truncation was hiding claims and causing false PASSES.

⚠ Do NOT conclude "the omission profile was an artifact". R319 measured the
control (`reference_correctness`, which never renders the answer) as having the
**largest** long-row failure gap (+0.400 vs answer_correctness's +0.250), so
length is a proxy for row difficulty. That overclaim is already refuted.

### Step 2 — the calibration play (highest value, low cost)

We have something we have never had: **the exact inputs (July-7 answers) AND all
16 official per-axis outputs.** Use them to check whether our local metrics track
theirs.

Score the July-7 arm (`jul07_answer` / `jul07_refs`) with our own metrics, split
by regenold modality, and compare against the official row for that mode. If our
proxy lands near the official axes, it becomes a usable **estimator for a new
arm** — which is the only way to claim "the official score should rise" without
another submission.

Be honest about the limit: 16 anchors cannot FIT anything. This is a
**calibration check**, not a fit. Even a negative result is valuable — it tells
you which local axes are not measuring what regenold measures (R280 already
showed our `Ans` metrics are structurally different: local loose ≤ strict is an
identity for us, while the official shows AnsL > AnsS on 6/6 rows).

### Step 3 — fresh hard-batch run against prod

```bash
# smoke first: evenly spaced, RNG-free, reproduces exactly
.venv/Scripts/python.exe -m evals.regenold.run_hard_sample_r297 \
  --label r320-hard-smoke --frac 0.25 --only both \
  --endpoint https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask \
  --api-key "$REGENOLD_API_KEY"
```

Then the full 222 multi-turn rows. **Budget honestly: at the measured ~30-60 s
hard-mode latency that is 2-4 h of wall clock**, and only one wrapper-bound job
can run at a time. Sample if the budget doesn't allow the full set — but say so
in the write-up rather than presenting a sample as the full batch.

### Step 4 — score two ways

1. **Then-vs-now**, same questions, against `jul07_answer` — the arm whose
   official score we KNOW. This is the defensible improvement claim.
2. **Grounded/legal_v2 judge** with the fixed window, compared against step 1's
   re-judged baseline (never against the pre-R319 numbers).

Report `pushback_conceded_rate` — the turn-20 rows are the adversarial
"I don't think this is correct, perhaps your answer contains hallucinations"
challenge. It has been **0.0000** in every measurement; keep it that way.

### Step 5 — re-A/B the R319 revert against an official-shaped objective

Not against ref recall alone. Use `.evalout/r319/context_delta.py` to find the
treatment rows, then `.evalout/r319/live_ab.py` with **latency as a first-class
axis**, and weigh the result on the geometric mean using the section-3 leverage.

### Step 6 — prioritised work

By leverage, and **protecting Ans Conciseness**:

1. **Ans Strict / Ans Loose** (+3.13 / +2.01). The known failure profile is
   omission-dominant, but see step 1 — that profile is measured with a judge
   that could not see half the answer, so re-establish it before acting.
   ⚠ Already refuted, do not re-pay: R277 minimal composer (noise), R284
   COMPLETENESS clause (over-cites), R307 uncap (metric trap — Ans Strict is
   recall and rises with length while Ans Loose stays flat), R312 answer-first
   (buys +0.100 correctness, pays −0.125 citation faithfulness), R282 forwarding
   the system prompt (rubric-negative).
2. **Speed** (+3.00, hard) — pure engineering, the cheapest points on the board,
   and largely untouched. Current hard p50 is 30-60 s against a frontier at
   85.2 and a 2025 baseline at 97.3. Start with the R319 gate A/B (step 5), the
   Opus-vs-Sonnet routing, and `complex_thinking_tokens`.
3. **Ref Strict** (+2.60) — the over-citation problem. Work the RANKER: R317
   killed all five removal-rule families, and rank-0 gold is 78.3% with ALL-gold
   coverage only 40.3% @ k=1 / 51.2% @ k=2, which is what actually blocks a clamp.

---

## 6. Traps for this session

* **The judge changed** — never compare new judged numbers to pre-R319 ones.
* **Hard mode = 222 multi-turn rows**, not the 281 `HARD MODE`-labelled ones.
* **No gold in this batch** — judge-scored only; do not invent gold.
* **Do not run two wrapper-bound jobs concurrently.**
* `/v1/auth/status` **lies** — verify the wrapper with a real POST.
* **Never read reference axes off one small-n live run** (R288: identical arms
  sign-flipped all three ref axes). Use repeats + a measured noise floor.
* Run `.evalout/r319/context_delta.py` before any A/B of a context-affecting flag.
* **Ans Conciseness is the only axis we lead — protect it.** Any "add coverage"
  lever must be measured against it.
* The benchmark is pinned to the Act as of **1 May 2026** — do not "update" the
  corpus to post-Omnibus text.
