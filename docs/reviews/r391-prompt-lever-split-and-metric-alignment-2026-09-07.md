# R391 — the codex/gemini prompt work: what it got right, what was confounded, and the metric alignment

**Date:** 2026-09-07
**Branch:** `feat/prompt-compact-and-r390-remediations`
**Method:** every finding below was produced by EXECUTION — a probe run, a counter read, a
provision pulled from the verbatim corpus — not by reading a diff. Claims that could not be
reproduced are marked as such.

---

## 0. Headline

The uncommitted `REGENOLD_PROMPT_COMPACT` work bundles **two independent levers that move
different axes in opposite directions**, behind one flag. Split and measured, one of them is
the best-evidenced finding of this round and the other is the highest-leverage remaining axis.

1. **The evidence half is right, and it is the measured root cause of the R390 §5.2
   enumeration family (~25 of 65 failed criteria).** `select_relevant_paragraphs` hands the
   model a PROPER SUBSET of a closed statutory set. **Annex IV: 0 of 8 lettered members reach
   the Stage-2 prompt. Article 17: 4 of 13. Article 13: 4 of 8. Article 10: 7 of 8.** No prompt
   instruction can recover a member that is not in the prompt — which is exactly why R390
   recorded that the delivered coverage clause's closed-set rule was "demonstrably
   insufficient". It was not a model failure; the evidence was never delivered.

2. **The contract half shrinks the answer,** which is where the remaining Overall gap sits
   (see §3), **and it is the only configuration that gets a real system prompt onto the
   production tunnel** — the compact system is 287 chars, under the R342 1000-char cap that
   replaces the 59,540-char `ANSWER_GENERATE_SYSTEM` with a 61-char persona.

3. **They were confounded.** One flag, and the two pull opposite ways on prompt size: measured
   over six questions the evidence half more than DOUBLES the reference block (**2.08x mean**;
   21,031 → 51,597 chars on one row) while the contract half roughly halves the instruction
   stack. Net user-message size ranged from **0.67x to 1.70x** depending on the question. A
   combined arm that moved would not have been attributable to either half (hard rule #6).

---

## 1. Executed findings on the incoming diff

| # | sev | finding | disposition |
| :--- | :--- | :--- | :--- |
| 1 | **P1** | **The hard-mode pushback clause was dropped.** The compact override replaces `user_message` wholesale at the end of the builder, discarding the challenge clause appended ~190 lines earlier. Measured on the benchmark's verbatim pushback template: `is_challenge_turn(...) == True` while `'CHALLENGE' in user_message == False`. That clause is the only instruction telling the model to hold a correct answer when the evaluator says "I don't think this is correct". **Hard mode is half the official score.** | **fixed** — re-appended after the contract so it stays inside the `_shrink_user_for_groq` protected tail |
| 2 | **P1** | **The resolved search question was dropped.** The full prompt carries `ORIGINAL QUESTION` *and* `REWRITTEN / SEARCH QUESTION`; the compact builder took only the first. In multi-turn mode `original_question` is the flattened conversation while the rewritten form is the R380 focused turn, so the model got the concatenation with no indication of which turn to answer — undoing `REGENOLD_DENOISE_SELF_CONTAINED_SKIP` and `REGENOLD_REASK_ANCHORLESS`. | **fixed** — `build_compact_answer_user(..., rewritten_question=...)` |
| 3 | **P1** | **Two levers, one flag** (§0.3). | **fixed** — split into `REGENOLD_PROMPT_COMPACT` and `REGENOLD_FULL_PROVISION_EVIDENCE`, both default OFF, both registered in `_engine_cache_key` |
| 4 | P2 | The full-provision substitution carried a bare `12000` literal and no knob, so one pathological reference (Article 5, Annex III) could make the prompt unbounded with no way to tune it. | **fixed** — `REGENOLD_FULL_PROVISION_MAX_CHARS`, clamped 1,000–40,000, fails OPEN to 12,000, cache-keyed |
| 5 | INFO | The contract names four provisions as examples of closed sets (Art. 17(1), 13(3), 10(3), Annex VIII) and two as examples of unasked tails (Art. 17(2)-(4), 49(2)-(5)). **All eight verify against `provision_text`**: 17(2) is proportionality, 17(3) sectoral integration, 17(4) financial institutions, 49(2) the Article 6(3) non-high-risk registration, 49(3) public-authority deployers. Unlike the `cea6cba` block R390 de-overfitted, **this one does not misstate the law**. | kept |
| 6 | INFO | `_extract_context_grounded_refs` is unchanged by the evidence lever, so completeness does not widen the citation universe. | pinned by test |

Not reproduced, and therefore not claimed: no evidence the evidence lever changes which heads
are citable, and no evidence the contract changes tone.

---

## 2. The metric instrument — aligned against the report, and now pinned

Requested check: do our axes match `report_antifragile_ai.pdf`'s own definitions? **Yes, and
the aggregation is now proven against the report's own printed numbers.**

Transcribing Table 1's descriptions and Tables 2–3's figures verbatim, our
`evals.official.rubric.overall` reproduces **all six published Overall scores** — two baselines
and us, across both modes — to a **maximum error of 0.044 pp**:

| row | printed | our GM | err |
| :--- | ---: | ---: | ---: |
| easy / 2026 frontier | 80.9 | 80.87 | 0.032 |
| easy / 2025 baseline | 70.1 | 70.06 | 0.044 |
| easy / Antifragile | 75.1 | 75.08 | 0.018 |
| hard / 2026 frontier | 81.7 | 81.73 | 0.033 |
| hard / 2025 baseline | 74.8 | 74.83 | 0.029 |
| hard / Antifragile | 73.4 | 73.41 | 0.013 |

Per-axis, each against its printed Description:

* **Ans. Correctness (Loose)** — "Percentage of individual correctness criteria satisfied": a
  MICRO average, so a 5-criterion question outweighs a 2-criterion one. ✓
* **Ans. Correctness (Strict)** — "Percentage of questions for which ALL required correctness
  criteria are satisfied". ✓
* **Ans. Conciseness** — "Inverted measure of answer verbosity relative to the reference
  answers". No formula is printed; recovered as `min(1, len(reference)/len(candidate))` and
  **one-sided** — an answer shorter than the reference is not penalised, omission is paid for
  on the correctness axes.
* **Ref. Correctness (Loose)** — "at the level of Article and Annex numbers (e.g. Article 6)".
  A more precise prediction covers the head, which is what the R386 grain deepener relies on. ✓
* **Ref. Correctness (Strict)** — "including subpoints (e.g. Article 6.1)". The bare head does
  NOT satisfy a sub-point key. ✓
* **Ref. Conciseness** — "Excess references relative to expected references": the pure COUNT
  ratio `min(1, |expected|/|provided|)`. WHICH provisions are cited does not move it. ✓
* **Regulatory Tone** — "Fraction of responses judged both appropriate and clear w.r.t. few
  shot examples". ✓
* **Resp. speed** — "100 minus latency in seconds, clipped at zero". ✓ (Verified against the
  arms: r389 mean latency 3.58 s → 96.42; r390 8.25 s → 91.76.)
* "Questions without annotated expected references are excluded from the reference metrics" —
  99 of 110 are annotated, and `n_ref_scored` reads 100. ✓
* "Ans. Correctness and Regulatory Tone are judged three times per question" at temperature
  0.1 with the min–max spread reported. ✓ (`REPEATS = 3`.)

**Until this round nothing pinned any of it.** `tests/test_official_rubric_alignment.py` (23
tests) now does, with the report's own numbers as fixtures, so a silent edit to the rubric
fails a test instead of silently moving every historical score.

### 2.1 The answer-length calibration this makes possible

Measured over the 110 gold reference answers: **mean 650 chars, median 652, p10 487, p90 822.**
Because the axis is `min(1, ref/cand)` per row and then averaged, a FIXED candidate length maps
to a known Ans. Conciseness:

| answer chars | 400 | 500 | 600 | 700 | 800 | 900 | 1000 | 1100 | 1200 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Ans. Conciseness** | 98.7 | 97.4 | 94.3 | **88.2** | 80.0 | 71.9 | **65.0** | 59.1 | 54.2 |

We shipped **989.8 chars → 69.0** on the r390 arm. This table is the design target for any
length instruction, and it is why the contract's current "strictly under 950 (target 500-850)"
is loose: 850 chars is ~75, 950 is ~68.

---

## 3. Where the round actually stands, and the size of the prize

⚠ **The two full-110 arms on record are NOT a prompt A/B — they used different Stage-2 models.**
Read from the checkpoints, not the labels:

| arm | Stage-2 model | AnsL | AnsS | AnsC | RefL | RefS | RefC | Tone | Speed | **Overall** | chars |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `r389-bedrock-stage2` | Qwen 3 (Bedrock) | 82.71 | 69.09 | **88.02** | 87.67 | 62.17 | **58.70** | 96.36 | **96.42** | 78.86 | 690.6 |
| `r390-opus5-live` | claude-opus-5 (tunnel) | **85.64** | **70.91** | 69.03 | **97.50** | **69.17** | 55.30 | **98.18** | 91.76 | 78.27 | 989.8 |
| 2026 frontier | — | 94.4 | 89.1 | 67.9 | 96.1 | 78.5 | 51.9 | 100.0 | 81.8 | **80.87** | — |

**R390 improved every correctness axis and every tone axis over r389** (AnsL +2.9, AnsS +1.8,
RefL +9.8, RefS +7.0, Tone +1.8). It lost 19.0 pp of Ans. Conciseness and 4.7 pp of Speed
purely to answer length (690 → 990 chars), and because Overall is a geometric mean that ate
the entire gain: **78.86 → 78.27.** Do not read that −0.59 as "R390 regressed"; the conciseness
column is a model/length artefact, not a prompt regression.

**The prize, computed on the rubric above:** hold r390's correctness and tone, restore r389's
length and speed —

```
AnsL 85.64  AnsS 70.91  AnsC 88.02  RefL 97.50
RefS 69.17  RefC 58.70  Tone 98.18  Speed 96.42   ->  Overall 81.79
```

**81.79 beats the 2026 frontier baseline's 80.87 by +0.9 pp**, in easy mode, on the reconstructed
official rubric. That is the whole round, and it is a *length and latency* target on an
already-correct answer — precisely what the two split levers are built to move.

Marginal leverage at the r390 point (pp Overall per pp axis): `RefC 1.415 > AnsC 1.134 ≈
RefS 1.132 ≈ AnsS 1.104 > AnsL 0.914 > Speed 0.853 > RefL 0.803 ≈ Tone 0.797`.

---

## 4. What ships in this change

Both levers **default OFF**. Nothing in production behaviour changes on merge; the gates below
decide the flip.

| flag | default | what it does |
| :--- | :--- | :--- |
| `REGENOLD_PROMPT_COMPACT` | `0` | Replaces the Stage-2 instruction stack and the draft with one ~3.4k answer contract, and the 59,540-char system prompt with a 287-char one that survives the R342 cap. Keeps the challenge clause and the resolved search question. |
| `REGENOLD_FULL_PROVISION_EVIDENCE` | `0` | Substitutes the COMPLETE provision for the question-relevant paragraph selection in the grounding block. Adds no citable head. |
| `REGENOLD_FULL_PROVISION_MAX_CHARS` | `12000` | Per-provision bound on the above. Clamped 1,000–40,000; fails OPEN. |

Tests: `tests/test_prompt_compact.py` (18) pins the 2x2 independence, the hard-mode clause, the
cap, the no-new-citable-head property and cache identity for all three flags;
`tests/test_official_rubric_alignment.py` (23) pins the instrument. 493 passed / 0 failed on the
touched paths (`-k "prompt or grounding or cache_key or compact or grain or parent_collapse or
transport or r390 or r380 or r386"`).

---

## 5. Live gate — status

Running: `evals.regenold.run_official_batch --label r391-ab --mode easy`, n=110, baseline
(both OFF) vs branch (both ON), over the cloudflared tunnel, scored with
`evals.official.score_arm`.

Smoke (n=8) came back 0 errors, 8/8 wrapper-served (`claude-opus-5`), branch **shorter (657.6
vs 684.8 chars) and faster (p50 9.8 s vs 13.1 s)**. Baseline reproduces the r390 arm to within
noise at n=20 (944 chars vs 989.8, 8.66 s vs 8.25 s).

⚠ **Read before quoting any number from it:**

* The runner is **whole-arm sequential**, not row-interleaved, so ~1 hour of wrapper drift sits
  between the arms. The deterministic axes (Ans. Conciseness, Ref. Conciseness, Speed) are
  immune — they are pure functions of the captured output — but the judged axes are not.
* **`gold_dropped_head` is the merge gate** (hard rule #8: drop ZERO more), and the reference
  axes do not resolve below n≈120 per this repo's own noise-floor measurements. Answer LENGTH
  resolves at n≈48 (R367, p=7.2e-04); a conciseness lever can be *screened* on length but never
  *cleared* on the same run.
* Attribute every row to `wrapper|bedrock` and abort on fallback — the wrapper shares the
  operator session's Claude Max quota, which is exactly what invalidated the `r389-live` arm.

---

## 6. The finding of the round — two reference passes were fighting each other

Found while sizing the reference axes on the captured baseline rows, not by reading code.

**Symptom.** On 48 gold-bearing rows of the live capture, **16 ship a bare head where the
official answer key wants a sub-point** (`Article 13` vs `Article 13.3`, `Article 6` vs
`Article 6.1`, `Article 10` vs `Article 10.4`, `Article 51` vs `Article 51.1` ...). We ship
**65.0 % sub-point grain against a key that is 98.1 % sub-point**. Ref. Correctness (Loose)
measured **95.8** — level with the frontier baseline's 96.1, i.e. **we retrieve the right
provisions** — while Ref. Correctness (Strict) measured **56.2**. The entire spread is grain.

**Diagnosis.** Replaying `_deepen_ref_grain` — the exact list-level function the route calls,
with the exact shipped references, question and answer — **changes 8 of 9 sampled lists and
lands the gold coordinate**. So the deepener works and was not reaching those references.

Spying on the real route settles why:

```
[spy] in=['Article 6', 'Article 13', 'Article 26']
     out=['Article 6.2', 'Article 13', 'Article 26.1']  exempt=['Article 13']
```

`_apply_ref_granularity` (auto) collapses a head's leaves onto the head and records that head
in `_collapsed_to_heads`; the deepener is then told to **SKIP exactly those heads**. The two
non-exempt heads were deepened; the exempt one was not — on a row whose answer key is
`Article 13.3`. **One pass discards the sub-point coordinate and the other is forbidden from
restoring it.**

**Why lifting the exemption is free**, against the rubric definitions pinned in §2:

| axis | printed definition | effect of head -> its own leaf |
| :--- | :--- | :--- |
| Ref. Correctness (Loose) | "at the level of Article and Annex numbers" | head survives inside the leaf — **no change** |
| Ref. Conciseness | "excess references relative to expected" (pure COUNT ratio) | one reference becomes one reference — **no change** |
| Ref. Correctness (Strict) | "including subpoints" | leaf scores where the head scores zero — **pure gain** |

And `gold_dropped_head` folds both sides onto heads while deepening maps a head to its OWN
leaf, so **the head set is invariant and hard rule #8 is `+0` BY CONSTRUCTION**. Verified both
ways: **0 of 57** captured live rows change their head set, and a zero-variance replay over the
gold-bearing rows (n=52) reads

| arm | RefLoose | RefStrict | RefConc | refs/row | `gold_dropped_head` | rows changed |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| exemption kept (as shipped) | 96.15 | 57.69 | 51.33 | 2.71 | 2 | 0 |
| **exemption lifted** | 96.15 | **72.76** | 51.33 | 2.71 | **2** | **21** |

**+15.06 pp Ref. Correctness (Strict) with every other reference axis byte-identical while 21
of 52 rows change their reference list** — the same signature as R381 parent collapse and R386
grain deepening: added precision without moving a provision.

**Projected effect on Overall**, applying the measured ratio to the r390 arm's Ref Strict:

| arm | RefStrict | Overall |
| :--- | ---: | ---: |
| r390 as measured | 69.17 | 78.27 |
| **+ R391 grain fix** | **87.2** | **80.57  (+2.30)** |
| + the conciseness/speed levers on top | — | 83.57 |
| 2026 frontier baseline | 78.5 | 80.87 |

**Ships `REGENOLD_GRAIN_DEEPEN_COLLAPSED_HEADS`, default ON** (`=0` restores the exemption),
registered in `_engine_cache_key`, pinned two-sided on the wire by
`tests/test_r391_grain_deepen_collapsed_heads.py` (11 tests) — including the inert-feature
tripwire that the OFF arm really does still suppress the deepener.

⚠ The +15.06 is a zero-variance replay at n=52, which removes GENERATION variance but not
SAMPLING variance. The `gold_dropped_head` claim does not depend on n (it is structural), but
the size of the Ref Strict gain does. Re-measure on a live n>=110 arm before quoting the +2.30.
