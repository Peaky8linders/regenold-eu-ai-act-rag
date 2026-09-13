# R415 (cont.) — the single-turn lever on the OFFICIAL corpus

**Date:** 2026-09-12  **Branch:** `fix/r409-r408-audit`
**Why:** the R415 pushback measurement closed the hard split by construction, but
the easy half of "combined board movement" could only quote the reference axes
and latency. This gate closes the other two — answer correctness and answer
conciseness — on the corpus that can actually be judged.

---

## 1. The recorded reason was WRONG, and the correction changes the plan

`CHECKPOINT.md` §6 said the correctness axes were left unjudged because "they need
the Claude-Max wrapper judge, whose OAuth is expired". False, and fixing the reason
is what unblocked the work:

* **The binding constraint is the corpus.** Both prior gates run on the harness
  probe corpus (`paper_st_v4` / `paper_tricky_v4` / `multiarticle_r268`), which
  carries `expected_refs` and `expected_keywords` per row but **no correctness
  criteria**. There is nothing to judge correctness against, so a working judge
  would have changed nothing.
* **Measured:** `0 of 95` easy probe questions appear in
  `docs/measurements/r388/official_gold_n110.jsonl` (exact match after
  whitespace/case normalisation). The probe corpus and the graded corpus are
  disjoint.
* The criteria-bearing corpus is the reconstructed official gold (110 rows:
  `criteria`, `reference_answer`, `expected_refs`), which is what
  `evals.official.score_arm` ingests.

§6 is corrected in `CHECKPOINT.md` rather than left to mislead the next attempt.

## 2. The first gate design was falsified by its own smoke run

The obvious design — pair both arms on a contiguous slice — is invalid here. The
smoke run (n=6) showed **4 of the first 6** graded rows answered in ~4 s with
**zero** Stage-2 attempts: curated deterministic intercepts. The lever rewrites the
system slot of a model call, so on an intercept row there is no call to rewrite and
the lever is inert *by construction*. Diluting a reachable subset into a
convenience slice is exactly how a real effect reads as a weak one.

So the gate does two things instead:

1. sweep the shipped arm over the graded board, recording **per row** whether
   Stage-2 ran;
2. run the baseline arm over **only the reachable ids**, so no call is spent on an
   inert row and the pair is matched row-for-row.

## 3. Instrumentation had to get finer, twice

* **Per-row provenance replaced whole-arm counters.** An arm-level transport
  counter can say the tunnel carried the arm; it cannot say which rows the lever
  reached. `run_arm` now snapshots `stage2_policy.transport_stats()` around each
  row and records `stage2_used` / `stage2_fell_back`.
* **A fallback row is structurally incomparable, not merely noisy.** The Bedrock
  leg always receives the FULL system, so on a fallback row both arms dispatch
  identical bytes whatever the lever says. Those rows are now **excluded from the
  pair** rather than averaged in — the R412 lesson enforced per row instead of
  per run. If the tunnel were down for a whole arm the surviving set collapses to
  nothing and the scorer refuses (exit 3), so the R412 null-result trap stays shut.
* Judge-leg refusal (R414) and judge-leg voidiness (R413) are both carried over:
  `score_arm` exiting non-zero withholds the entire delta table.

## 4. Readings so far

Sample: the first **51** graded rows (stopped deliberately at a significant sample
rather than the full 110).

| | value |
| :--- | ---: |
| graded rows swept (arm B, shipped) | 51 |
| answered with a Stage-2 call | **28** (54.9%) |
| — of which served by the Bedrock fallback | 1 (`rg_016`) |
| answered by a deterministic intercept (no model call) | **23** (45.1%) |
| paired-eligible rows | 27 |
| model-served row latency p50 | **28.5 s** |
| arm A matched run | 27 rows, 0 errors, all Stage-2 served |
| — arm A rows dropped for falling back | 1 (`rg_037`) |
| **final paired n** | **26** |

Artifacts: `official-lever-b.ckpt.jsonl` (sweep),
`official-lever-a-matched.ckpt.jsonl` (baseline on reachable ids),
`official-board-stage2-reach.json` (reach lists),
`judge-cache-r415-wrapper.jsonl` (verdict cache).

## 5. The judged pass — all eight axes, and a real cost the probe corpus could not see

Wrapper judge (`claude-sonnet-5`, temp 0.1, grouped, 3 repeats — the recorded
official judge setup), 26 paired rows, both arms served by the tunnel, no void
banner. Artifacts: `official-lever-paired.json`,
`docs/measurements/r388/score-r415-official-lever-{a,b}-matched-easy.json`.

| axis | A lever OFF | B lever ON | Δ pp |
| :--- | ---: | ---: | ---: |
| ans_correctness_loose | 98.9 | 96.7 | **−2.2** |
| ans_correctness_strict | 96.2 | 88.5 | **−7.7** |
| ans_conciseness | 27.9 | 47.1 | **+19.2** |
| ref_correctness_loose | 100.0 | 100.0 | 0.0 |
| ref_correctness_strict | 72.0 | 72.0 | 0.0 |
| ref_conciseness | 40.3 | 51.5 | **+11.2** |
| regulatory_tone | 61.5 | 61.5 | 0.0 |
| resp_speed | 66.6 | 70.4 | **+3.8** |
| **OVERALL (geo mean)** | 64.9 | **71.0** | **+6.1** |

The mechanical cause, so it is not read as a prompt quality change: mean answer
length **2456 → 1442 chars (−41.3%)**, mean refs/row **3.73 → 3.00 (−19.6%)**,
mean latency **33.35 → 29.60 s (−3.75 s)**. The lever does not change the
reference grain (loose and strict both flat at 100.0 / 72.0 on this subset — it is
at ceiling for loose and the strict misses are not lever-driven).

### The correctness cost is two rows, and both are real drops

`ans_strict` is 25/26 → 23/26; `ans_loose` is 89/90 → 87/90. **Exactly two rows**
change, one criterion each, every other row identical:

* **`rg_010`** (which article governs human oversight) — B still names Article 14
  and all five overseer capabilities, but **never states the aim** of Art. 14
  oversight (to prevent/minimise risks to health, safety and fundamental rights).
* **`rg_045`** (deployer with a risk suspicion) — B names all three duties, but
  attaches *"without undue delay"* to the informing actions only, leaving the
  suspension unqualified. The judge's remark is explicit about the scope narrowing.

Both are **content omissions in the shorter answer**, not judge variance: the
qualifier/aim clause was carried by the longer draft and does not survive a 41%
compression. `rg_045` is therefore the first *measured instance* of the failure
mode that the next roadmap row exists to fix — the polished answer narrowing a
qualifier the Stage-1 draft carried correctly. That is a sharper target than the
prose in R411 §F2 ("Stage-2 omits the sub-point") because it names the operand:
not a missing citation, a **narrowed scope**.

### Why this still ships

The official aggregate is the geometric mean, and the floor moved: conciseness
27.9 → 47.1 lifts the product far more than 2 of 90 criteria cost it, giving
**+6.1 pp overall**. The trade is deliberate and now measured, not assumed.

Board movement, exactly: the lever reaches 26 of the 51 swept rows, so it
multiplies the board geomean by `1.0940^(26/51)` = **×1.047** — the intercept rows
are identical between arms, so they cancel out of the product regardless of what
they score. That is **≈ +3.4 pp at a board value of 72**, ≈ +3.8 pp at 80.9. On the
full 110-row board (reach 26/110) the factor is ×1.0215, ≈ +1.5 pp — the reach
ratio, not the lever, is what limits board movement.

## 6. What this does NOT establish

* It is **not** the official board. Criteria and reference answers are
  reconstructed, and the reachable subset is a contiguous slice, not a random
  sample. Compare the arms; never quote an arm as a score. Arm B's 71.0 is the
  *reachable* subset — the rows that need a model call at all — so it is the hard
  tail of the board, not the board.
* `regulatory_tone` is flat (61.5 both arms) and low in absolute terms on this
  subset. That is a property of the subset, not of the lever: the same judge
  scored tone 95.0/92.5 on the R413 arms and 99.1/100.0 in the published
  reference scorecard. Nothing here should be read as a tone reading.
* The **hard split is absent by design** — R415 §3 proved the graded multi-turn
  payload is byte-identical between the arms, so its movement is zero by
  construction, not by measurement. Nothing here changes that.
* The sweep was stopped at 51 of 110 rows, so the reach ratio (54.9% served) is a
  head-of-corpus figure and may not hold across the tail.
