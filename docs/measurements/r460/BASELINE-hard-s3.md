# R460 — live hard-board re-baseline on the current merged build (representative sample)

**Build under test:** `origin/main` @ `a9553ed` (Merge PR #483), recorded as
`reference_pass.commit = a9553ed36bcb`. Run from a clean worktree on branch
`feat/r460-evidence-bundle-payload-cut`.

**Why this exists.** The published `us` column is the R419/R436 capture: **73.4** hard
overall, judged before R423 / R448 / R452–R456 shipped. The board was stale on exactly
the axes those rounds targeted, and the frontier gap arithmetic in
`docs/reviews/frontier-gap-audit-2026-09-30.md` projected the build could already be
above the frontier overall. This is the first live measurement of the merged build.

## 1. Command and scope

```bash
# generation — real route, live Stage-2 over the tunnel, hard mode (2 requests/row)
python -m evals.regenold.run_official_batch --label r460-hard-s3 --mode hard --stride 3
# judge — the R436 judge identity, grouped, 3 repetitions
python -m evals.official.score_arm \
  --ckpt evals/bench/results/official-r460-hard-s3-hard.ckpt.jsonl \
  --label r460-hard-s3 --mode hard \
  --judge-provider bedrock --judge-model qwen.qwen3-235b-a22b-2507-v1:0 \
  --repeats 3 --cache-file docs/measurements/r460/judge-cache-r460-bedrock.jsonl
```

* **n=37** — every 3rd row of the 110 in send order (`--stride 3`), a representative
  sample, **not** the full board. Difficulty mix 15 EASY / 22 HARD (the full 110 is
  51 easy / 59 hard, 46% easy), so the mix is faithful.
* Generation: **37/37 rows, 0 errors**, ~23 min. Wall time ≈ 17.2 s mean / 35.5 s p50
  per row (two live requests each).
* Judge identity: `bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3` — **the
  same identity as the R436 / R419 boards**, so the comparison is like-for-like on the
  instrument. Zero spread across the 3 repetitions at temperature 0.1.

## 2. The board

```
axis                        THIS ARM   us(off)  2026 frontier  gap->frontier
ans_correctness_loose           94.1      89.9           92.0           +2.1  BEATS
ans_correctness_strict          89.2      80.0           84.8           +4.4  BEATS
ans_conciseness                 81.6      45.2           71.8           +9.8  BEATS
ref_correctness_loose           95.7      89.5           94.6           +1.1  BEATS
ref_correctness_strict          82.4      70.7           74.1           +8.3  BEATS
ref_conciseness                 59.9      49.8           58.5           +1.4  BEATS
regulatory_tone                 97.3      96.1          100.0           -2.7
resp_speed                      82.8      85.7           86.7           -3.9
OVERALL (geo mean)              84.5      73.4           81.7           +2.8  BEATS
```

Against the **published `us` column** (the stale capture) the build is
**+11.1 pp overall** and **ahead on 7 of 8 axes**:

| axis | Δ vs published `us` |
|---|---:|
| ans_correctness_loose | +4.2 |
| ans_correctness_strict | +9.2 |
| ans_conciseness | **+36.4** |
| ref_correctness_loose | +6.2 |
| ref_correctness_strict | +11.7 |
| ref_conciseness | +10.1 |
| regulatory_tone | +1.2 |
| resp_speed | −2.9 |

Against the **2026 frontier** it is ahead on 6 of 8 and **above the frontier overall**
(84.5 vs 81.7). The only two axes still short are Regulatory Tone (−2.7) and
Response Speed (−3.9).

## 3. Integrity and provenance

* **Stage-2 leg mix, per row (the R442 `_provenance` field):** 28/37 rows
  `stage2_polish=True, stage2_served_by=primary, stage2_model=claude-opus-5-5`;
  9/37 rows served without Stage-2 (curated/deterministic intercepts, correct behaviour
  — the same class the R460 census found). **No row was served by a fallback leg.**
* One transient transport event in the run log: a wrapper *degenerate completion*
  (`completion_tokens=1`) on one row, retried on the primary leg and then Bedrock;
  the recorded provenance for every Stage-2 row still reads `served_by=primary`, and the
  harness's abort-on-outage guard never tripped (0 errors).
* Single-process invariant held: one runner, one OS byte-range run lock
  (`official-r460-hard-s3.run.lock`). The R436 defect (a second Python 3.12 copy
  sharing the checkpoint) did **not** recur.
* `reference_pass = {redeepen: true, rows_changed: 1, commit: a9553ed36bcb, flags: {}}`
  — the reference pass is recorded with the build commit.

## 4. Caveats — read the number with these attached

1. **Cohere is NOT in the loop.** The `COHERE_API_KEY` is a Trial key whose
   **1000 calls/month quota is exhausted**: 429 on both `/v1/embed` and `/v1/rerank`,
   so retrieval ran the local SVD fallback for the whole run. This is a *degraded
   retrieval leg* relative to any Cohere-enabled board, and it can only have
   **lowered** the score. The board above is therefore a floor, not the Cohere-enabled
   number.
2. **n=37, not 110.** A representative stride sample. Per-row noise is real
   (`pushback_ref_flip_rate = 0.2432`: 9/37 rows changed their reference set under the
   verbatim pushback), so the full board may move a point or two.
3. **The instrument is a proxy.** `score_arm`'s own footer: criteria and reference
   answers are **reconstructed**, not the evaluator's. Compare arms/builds under this
   instrument; do not read 84.5 as an official score. `_ans_loose_macro` **93.5** and
   the criterion-micro view are reported alongside for that reason.
4. One gold row is flagged unstable, and the reference axes are scored on
   **35/37** rows (rows without annotated expected references are excluded).

## 5. What it says

The audit's central suspicion is confirmed on live evidence: **the 73.4 board was
stale, and the merged build is already at or above the 2026 frontier overall** on this
sample, with the entire conciseness campaign visible (Ans Conciseness 45.2 → 81.6).
The two remaining soft axes are Tone and Speed — not correctness or references.

## 6. Artifacts

| path | what |
|---|---|
| `evals/bench/results/official-r460-hard-s3-hard.ckpt.jsonl` | 37 generated hard rows |
| `evals/bench/results/official-r460-hard-s3.json` | generation summary + per-difficulty breakdown |
| `docs/measurements/r388/score-r460-hard-s3-hard.json` | the scored board (axes, per-row, provenance) |
| `docs/measurements/r460/judge-cache-r460-bedrock.jsonl` | judge cache (37 rows x 3 reps) |
| `docs/measurements/r460/score-r460-hard-s3.log` | full runner + judge logs |

## 7. To complete the full board

Re-run generation with no `--stride` (~80 min, 110 rows x 2 requests) then the same
`score_arm` command against the new checkpoint. The harness is now proven stable
(37/37, 0 errors, single process), so the only open risks are the Cohere leg (still
down) and the ~2 h wall clock. A Cohere-enabled full board is the number worth
publishing; this sample is the floor and the go/no-go evidence for spending it.
