# R320 — CHECKPOINT (results, written 2026-08-07)

Session state saved so nothing is lost. Everything below is measured; where it
is an estimate or an assumption, it says so.

Branch: `main` @ `33ad45d` + uncommitted R320 changes (see §6).

---

## 1. Step 1 — the re-judge (DONE, and it is the round's biggest single result)

R319 raised the judge's answer window 1400 → 6000. The corpus mean answer is
1413 chars, so the old cap sat ON the median: **exactly 36 of 72 rows were
truncated before the judge saw them, and 36 were not.** That makes the
comparison self-controlling.

`.evalout/r320/rejudge_diff.py` — OLD = `legalv2-r309-hard`, NEW =
`legalv2-r320-rejudge-fixedwindow`.

| stratum | answer_corr | reference_corr | citation_faith | answer_concise |
| --- | --- | --- | --- | --- |
| **UNDER 1400** (control, identical prompt, n=36) | +0.000 | −0.028 | +0.028 | −0.056 |
| **OVER 1400** (judge sees more, n=36) | **+0.278** | +0.059 | −0.029 | −0.083 |

* **`answer_correctness` +0.278 on long rows (0.333 → 0.611), 11 fail→pass vs
  1 pass→fail, against a 0.000 control.** The old judge was failing two of
  every three long answers substantially because it could not read them.
  **Every pre-R319 judged answer-correctness number is understated.**
* **The plan's prediction is NOT supported.** It predicted
  `citation_faithfulness` would get WORSE because truncation hid claims and
  caused false passes. Measured −0.029 against a +0.028 control — i.e. inside
  noise, and the control moved the same magnitude the other way.
* `reference_correctness` never renders the answer, so it is a second control;
  it moved +0.059, small as expected.

Full re-judged baseline (n=72): answer_corr **0.5972** · reference_corr
**0.5000** · citation_faith **0.8732** · answer_concise **0.3056**.

⚠ Every future judged number must be compared to THIS, never to
`legalv2-r309-hard` or older `grounded-*`.

---

## 2. Step 2 — the calibration play (DONE)

### 2a. Overall IS the geometric mean — and the arithmetic mean is REFUTED

Reproduced independently on all 6 published rows:

| | geo mean err | arithmetic mean err |
| --- | --- | --- |
| worst of 6 rows | **0.06 pp** | **1.40 pp** |

So the aggregation is settled, and the obvious alternative is actively ruled
out (not merely "less good"). Per-axis leverage is therefore arithmetic, not
argument. Hard-mode leverage reproduces the plan exactly: AnsS +3.13 · Speed
+3.00 · RefS +2.60 · AnsL +2.01 · RefL +1.70 · RefCon +0.85 · Tone +0.17 ·
**AnsCon −0.12 (matching frontier LOSES points)**.

### 2b. July-7 per-request LATENCY recovered (the batch has no latency field)

All 333 rows carry a `timestamp`, the run is strictly monotonic over 252.5
min, and the ordering is 111 easy (blocked) then hard strictly interleaved
`18,20,18,20…`. So consecutive deltas recover per-request latency **and**
prove each hard conversation is two back-to-back calls.

| | p50 | mean |
| --- | --- | --- |
| turns=0 (regenold EASY, 1 call) | 35.8 s | 37.8 s |
| turns=18 | 40.4 s | 42.6 s |
| turns=20 (pushback) | 30.8 s | 30.9 s |
| **regenold HARD conversation = 18+20** | **71.2 s** | 73.5 s |

Cross-validated against independent direct measurements already in CLAUDE.md
(R286 easy 23.8 s / hard 37.4 s; R305 hard p50 37 s), so the method is sound.

### 2c. The Speed axis is CALIBRATED from the two official anchors

Anchors: easy 35.8 s → Speed 75.1; hard 71.2 s → Speed 61.7.

| form | T fitted on easy | T fitted on hard | spread |
| --- | --- | --- | --- |
| `100·exp(−t/T)` | 125.0 | 147.4 | 22.4 — inconsistent |
| **`100/(1+t/T)`** | **108.0** | **114.7** | **6.7 — consistent** |

Single-parameter fit **T = 111.3** reproduces easy 75.7 (official 75.1) and
hard 61.0 (official 61.7) — **both anchors inside 0.7 pp**.

Required per-request latency for a hard-mode Speed target (conv = 2 requests):
61.7 → 34.6 s · 70 → 23.9 s · 75 → 18.6 s · 85.2 (frontier) → **9.7 s** ·
97.3 (2025 baseline) → 1.5 s.

### 2d. Answer-Conciseness — the formula, and the anchor it gives us

Local `answer_conciseness` = `(min(lp,lg)/max(lp,lg))²` on **character**
length (`evals/bench/metrics.py:302-310`) — a PEAKED metric, so moving away
from gold length in EITHER direction loses points.

July-7 scored 96.0 easy / 93.4 hard ⇒ implied per-row length ratio **0.980 /
0.966**. A near-maximal score means **July-7's answer lengths already tracked
the gold lengths closely** — which makes "match July-7 length" a
well-anchored target that does NOT depend on knowing the exact formula.

### 2e. Tone — a NEGATIVE calibration result worth keeping

Our local `regulatory_tone` returns **exactly 100.0 on all 333** July-7
answers (min = 100.0) while regenold scored 98.2–98.5. It is a floor
detector with **zero discriminating power at the top** — it does not measure
what regenold measures at the margin. (Tone is worth +0.17 pp, so this is a
confirmed dead end rather than a missed lever.)

---

## 3. THE REGRESSION THIS ROUND FOUND — we broke the axis we lead

**R308 (2026-08-03) flipped `REGENOLD_ANSWER_NO_CAP` default ON, twenty-seven
days AFTER the July-7 graded batch.** The batch that scored Answer-Conciseness
96.0 / 93.4 ran WITH caps; production has been uncapped since. R308's own
checkpoint records that its merge gate was never run.

Measured paired length drift vs the graded arm:

| sample | ratio to July-7 | rows longer |
| --- | --- | --- |
| `july7-r309-ALL` (72 rows) | **1.130** | 39/72 |
| R320 fresh hard sample (28 questions, paired) | **1.356** mean / 1.264 median-of-ratios | 19/28 |

Cost on Overall (hard), bounded under three plausible AnsCon forms, each
anchored so July-7 reproduces its known 93.4:

| assumed form | AnsCon today | Overall lost |
| --- | --- | --- |
| quadratic `(min/max)²` (our local metric) | 73.1 | **−2.20 pp** |
| linear `min/max` | 82.7 | −1.11 pp |
| one-sided `min(1, gold/pred)` | 82.7 | −1.11 pp |

**The direction is robust across all three; only the magnitude is
formula-dependent.** Independently corroborated by a completely different
instrument: the re-judged `answer_conciseness` is our worst axis at **0.3056**,
and the judge's stated failure reasons are *"verdict and conditional restated
three times"*, *"padding with tangential enumerations"*, *"scope creep"*.

---

## 4. Speed is an ARCHITECTURE problem, not a config one (plan assumption REFUTED)

The plan ranked Speed as "+3.00 pp, pure engineering, the cheapest points on
the board". Measured, it is not reachable with any knob we have:

* **A 5-token request costs 12–17 s on the LOCAL wrapper** (no Cloudflare
  tunnel), and it is the same for `claude-sonnet-5` and `claude-opus-5`.
  Production `/healthz/llm` reports `elapsed_ms 13528` for a 2-token probe.
  **Roughly half our latency is a fixed per-call floor** from the
  Claude-Code-CLI wrapper, independent of model and content.
* Recorded-arm split: Stage-2 ON p50 **31.4 s** vs Stage-2 OFF **5.1 s**. So
  Stage-2 dominates; CLARA (3 s) and the de-noiser chain (≤4 s, 1 s fail-fast
  per provider) are noise by comparison.
* **The thinking budget is NOT the latency lever** — contrary to the R280 note
  in `config.py`. Complex rows (`complex_thinking_tokens=4000`) run p50
  **26.9 s**; simple rows (thinking 0) run **41.8 s** — the "expensive" path is
  15 s *faster*. Observational, not an A/B, but it points the opposite way to
  the assumption.
* Answer-length↔latency correlation is only **0.347**, so it is not output
  generation either.

This is now the **fourth** independent line agreeing with the two findings
already in memory (fast mode = wash; thinking budget = wash). **The real Speed
lever is replacing the Cloudflare-tunnel + Claude-Max-wrapper transport with a
direct API path (R56 already built the Anthropic SDK direct path).** That is an
operator/infra decision, not a code knob.

---

## 5. The cap A/B — a TRADE, not a win, so it ships default OFF

Paired judge A/B on the **21 rows the cap actually changes** (the other 51 are
byte-identical ⇒ guaranteed ties that only dilute — the R319 lesson). Arm A
and arm B share the SAME Opus generations, because the caps are pure route
post-processing ⇒ **zero generation variance**.

| axis | A (uncapped) | B (R320 cap) | delta | B>A / A>B / tie |
| --- | --- | --- | --- | --- |
| answer_conciseness | 0.238 | 0.333 | **+0.095** | 3 / 1 / 17 |
| citation_faithfulness | 0.810 | 0.905 | **+0.095** | 2 / 0 / 19 |
| reference_correctness | 0.190 | 0.190 | 0.000 | 0 / 0 / 21 (inert, as designed) |
| **answer_correctness** | 0.476 | 0.333 | **−0.143** | 1 / **4** / 16 |

Neither delta is close to significant at n=21 (sign test p≈0.375 / p≈0.625),
and the losing axis has the larger official leverage. **Shipping it ON would
repeat R308 (uncap shipped with its gate un-run) and R299 (partition shipped
with no A/B).** Default OFF; `REGENOLD_LIVE_SENTENCE_CAP=4` enables it.

Two instrument bugs found and fixed while building this (both would have
produced a false PASS):
1. an explicit `REGENOLD_MAX_ANSWER_SENTENCES` **overrides** the ContextVar
   (`models.py:1375`), so a "baseline" computed with the sweep env set was
   itself capped — the enumeration check compared a thing to itself;
2. `normalise_answer_for_regenold` is **not idempotent**, so re-running it
   changes 9/72 rows even with the cap OFF. That floor must be subtracted or a
   safe config gets rejected for damage it did not cause.

Also measured and rejected: the **char cap** drops "the longest
NON-CITE-ANCHORED sentence", which is exactly a crisp verdict-first opener —
it deleted **16 lead sentences**, including `"No such list exists."`, the
direct answer to an adversarial premise-check (`july7-287`). Any future cap
must be SENTENCE-only.

---

## 6. What is SHIPPED (uncommitted, in the working tree)

| change | file | status |
| --- | --- | --- |
| Remove the **duplicated** `USER_ANSWER_COVERAGE_CLAUSE` append (a copy-paste bug: the model received the same 1955-char completeness instruction twice, ~3910 chars, doubling the pressure toward longer answers) | `app/engines/_graph_rag_impl.py` | **SHIPPED** — it is a bug, not a trade |
| Live-path **sentence** cap, char cap skipped (`REGENOLD_LIVE_SENTENCE_CAP`) | `app/integrations/regenold/models.py` | **default OFF**, opt-in pending a powered A/B |
| 14 regression tests | `tests/test_r320_live_sentence_cap.py` | new |

### Gates (all green)

| gate | result |
| --- | --- |
| **davidath 476** | **byte-identical, proven PER-ROW**: 476/476 rows, 0 diffs on `pred_answer`, `pred_refs`, and every score axis vs the `r319-gateon` sidecar. Ans Strict 0.3545 · Ans Loose 0.1884 · AnsCon 0.6143 · Ref Loose 0.5971 · Ref Strict 0.4748 · RefCon 0.4316 · Tone 1.0 · mt 20/20 |
| 276-runner | **254/254 (100%)**, RISK_F1 macro 1.00 |
| OOS probe (`--oos-suite all`) | **49 pass, 0 leaks** (only the 2 documented pre-existing `adjacent_eu` soft fails) |
| touched suites | **153 pass** (incl. the 2 R308 tests, which pass again now the cap is default OFF) |

⚠ The documented RefCon baseline of 0.4319 is STALE — the `r319-gateon`
sidecar itself reads **0.4316**. Grade against the sidecar, not the doc.

---

## 7. Step 3/4 — fresh hard-mode validation (DONE)

25% stratified sample of the **222 multi-turn** rows = regenold hard mode
(NOT the 281 `HARD MODE`-labelled rows — that trap would mix in 59
regenold-easy rows). 28 questions × 2 turns = **56 requests, 0 errors**.
Run LOCALLY against the wrapper so it exercises the shipped code, not
production's older commit.

| metric | value |
| --- | --- |
| tone | **1.0000** |
| refusal_rate | **0.0000** |
| **pushback_conceded_rate** | **0.0000** — the adversarial challenge never flipped an answer |
| refs / row | 2.96 (July-7 paired: 3.61 ⇒ **−18%**) |
| answer chars | 1064 (July-7 paired: 785 ⇒ **+35.6%**) |
| latency p50 / p90 per question (2 turns) | 44.6 s / 66.7 s |
| stage2_landed | 0.75 |
| pushback_ref_flip_rate | 0.4643 |

Judged with the SAME fixed-window judge as the Step-1 baseline:

| axis | July-7 arm re-judged (n=72) | R320 fresh hard (n=28) |
| --- | --- | --- |
| answer_correctness | 0.5972 | **0.7857** (mean factual 0.9884) |
| reference_correctness | 0.5000 | **0.6071** (recall **1.0**, focus_precision 0.572) |
| citation_faithfulness | 0.8732 | **1.0000** (28/28) |
| answer_conciseness | 0.3056 | **0.5714** |

⚠ **HONEST LIMIT: this is NOT a paired comparison.** The two arms are
different row sets (72 R309-sampled rows vs 28 R297-stratified multi-turn
rows), so the deltas are confounded by sample composition. What IS
like-for-like is the judge (same model, same fixed 6000-char window). Treat
these as two current-state readings, not as a measured improvement.

⚠ **The 44.6 s latency is LOCAL** (no Cloudflare tunnel) and is therefore NOT
comparable to July-7's 71.2 s through production.

Reference precision remains the standing weakness: **WRONG=20 vs
GOVERNING=38, focus_precision 0.572, recall 1.0** — i.e. over-citation, not
under-retrieval, exactly the R287/R291/R302/R316 finding.

---

## 8. Next, ranked

1. **Answer-Conciseness at the SOURCE, not by truncation.** The judge's own
   failure reasons are redundancy and scope creep, so a blunt cap treats the
   symptom. The duplicate-clause removal is the first source-side fix; measure
   its effect before adding more instruction.
2. **A properly powered cap A/B** (n≫21, repeats, measured noise floor) if the
   source-side fix does not close the length gap.
3. **Speed: raise it with the operator, not with a knob** — direct API
   transport instead of the CLI wrapper. Nothing else moves it.
4. **Reference precision** (focus_precision 0.572, WRONG=20, recall 1.0).
   R317 killed all five removal-rule families; work the RANKER.

## 9. Traps confirmed or added this round

* **`--only mt` is the correct hard-mode selector** (222 multi-turn). Verified.
* An explicit `REGENOLD_MAX_ANSWER_SENTENCES` **overrides** the no-cap
  ContextVar — any offline cap experiment must drive the ContextVar, not the env.
* `normalise_answer_for_regenold` is **not idempotent** — subtract the floor.
* The **char cap deletes verdict-first leads**. Sentence-only, always.
* Groq's daily token cap (TPD) fires during long runs; the de-noiser falls
  back. Documented behaviour, not a regression.
