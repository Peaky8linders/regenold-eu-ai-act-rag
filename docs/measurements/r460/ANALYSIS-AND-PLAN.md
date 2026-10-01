# R460 — deep analysis of the round, and the plan it implies

Everything below is measured in this worktree (`a9553ed` = `origin/main`), with
the artifacts named. Read the caveats at the end before quoting any number.

## 1. What this round actually established

### 1.1 The shipped stack is strong on correctness, weak on speed and tone

Live hard board, Opus 5.5, n=37 (`BASELINE-hard-s3.md`): **overall 84.52** vs
the published frontier 81.7, better on 6/8 axes. The two deficits:

| axis | ours | frontier | gap |
| :-- | --: | --: | --: |
| resp_speed | 82.76 | 86.7 | **-3.9** |
| regulatory_tone | 97.30 | 100.0 | **-2.7 (one row: rg_088)** |

Row latency composition (checkpoints, 37 rows): Opus per-turn p50 **18.0 s**
(t1 18.0 / pushback 17.6), row p90 51.7 s, max 77.4 s. `attempts=2` on every
row means one attempt per turn — **no retries anywhere**, so the wall time is
real work, not retry storms.

The seam probe puts a Stage-2 call at **~9 s** median on the same payloads, so
roughly **half of each hard turn is NOT Stage-2**: retrieval + KG + routing +
the post-generation guards. That is the only un-profiled half of the speed gap.

### 1.2 The Sonnet swap fails the correctness gate, and would need a transport
### fix anyway

`SONNET-VS-OPUS55-GATE.md`: paired n=37, one shared judge cache, pinned identity.
Answer-strict -8.11 pp (3 rows, none the other way; **rg_097 is a wrong verdict**
- the criterion's gold answer is "No" and Sonnet answers "Yes"), references pass
(`gold_dropped_head` A=2 -> B=0, `new_drops_in_b=[]`), conciseness +5.19
(p=0.0015) and tone +2.70 pass, board speed -15.47 (p<0.0001).

Two things this round added around that verdict:

* **Speed, board vs seam.** The board says Sonnet is 4x slower per row
  (p50 62.4 s vs 35.5 s; t1/t2 p50 30.8 vs 18.0); the seam probe says it is
  *faster* per call (median 6.6 s vs 9.0 s) on identical payloads. The board run
  also hit five consecutive 60 s-deadline read timeouts (the abort at 28/37).
  Conclusion: the board's speed axis is transport-contaminated for B, and
  neither number is a clean model-latency statement. The 60 s client deadline is
  close to Opus's own p100 (46.2 s) - it is a latent production hazard on its own.
* **The premise check.** "Cheaper": the only counter the wrapper reports is
  `round(len(user)/4.0)` (verified to the digit on 4 draws and 6 canary calls);
  it is identical across models and **ignores the system entirely**, so it cannot
  price the 60k stack. Completion tokens are equal (median 227.5 vs 220.5).
  There is no measured cost win to trade for the correctness loss.

### 1.3 The system message IS delivered - but not to Sonnet at 60k

`system-delivery-canary.json`: a canary instruction written **only** into the
system message, three sizes, both models:

| system chars | Sonnet 5 | Opus 5.5 |
| --: | :-- | :-- |
| 129 | obeyed 3/3 | obeyed 3/3 |
| 3,131 | obeyed 3/3 | obeyed 3/3 |
| 60,774 | **obeyed 1/3** | **obeyed 3/3** |

Three consequences:

1. The standing R282/R298 premise "the wrapper drops the system message 100 %"
   (which is why R298 moved the ref-minimality rule into the user message) is
   **false as stated**. Both models receive short and mid-size systems.
2. At production length it is **model-dependent, and the wrapper is not the
   cause**: both long calls were handed to the CLI as `--system-prompt-file`
   (the wrapper's own log, 12:44:19 / 12:44:38: `System prompt 60877 chars >=
   30000 argv limit` - `claude_cli.py` spills >= 30,000 chars to a temp file),
   i.e. the same path for both models, and yet Opus obeyed 3/3 while Sonnet
   managed 1/3. So this is model-side adherence to a tail instruction buried in
   60k of prompt, not a delivery gap - and it is why the R411/R412 full-system
   result does not transfer to Sonnet without its own gate.
3. The R460 payload cut is therefore **not inert**: the 60k stack is read by the
   model where it is delivered, so the `REGENOLD_PROMPT_COMPACT` /
   `REGENOLD_MINIMAL_COMPOSER` levers are behavioral changes needing a gate, not
   free byte reductions. (They remain real byte reductions on the wire; the
   wrapper's usage counter just cannot show them.)

### 1.4 The payload census measured the wrong shape for hard mode

`capture_payloads.py` replays with `depth=0`, i.e. an empty rolling history. On
the live hard board the rolling history means only the **opening dispatches of a
run** carry the full stack (`history_turn_count <= 1`, R411/R412's gate: R423.3
measures rows 1-2 reading 0 and 1, and row 1's pushback also reads 1 - roughly
2-3 of 74 dispatches); every later dispatch carries the 61-char persona. So the census headline "66 % of the
payload is the static system stack" describes **easy mode and the opening hard
dispatches**, not the hard board at large (where the evidence block dominates,
~24,272 chars of ~27-31k). The probe data agrees: the recorded draws are
system=60,643 + user 15,975..40,700, and only the user part is counted by the
wrapper's usage.

### 1.5 The two transplanted levers: one promotion candidate, one closed

* **R450 emission allocation** (`REBASE-R450-R451.md`): `density` is best at
  every budget (1200: 64/82 = 0.780 vs `rank` 61/82 = 0.744; 900: 57 vs 56;
  1600: 68 vs 67), matched chars p95 1,221, `split*` falsified. Measured, **not
  flipped**; needs the live paired gate.
* **R451 field weights**: title side flat (w1..w5 indistinguishable, every `bt`
  <= 0.0003); body weight `bb0.5`/`bb0.6` beat the `sparse` control but **nothing
  beats `shipped`** - HOLD, and stop sweeping the title side.

### 1.6 Instrument debt this round exposed

* No per-row token capture in the official schema (the probe had to be written).
* The census/capture shape is single-turn-only (1.4).
* The harness cannot tell "wrapper slow" from "wrapper down" (1.2).
* Cohere is out of quota, so every live number this round is an SVD-retrieval
  **floor** (429 on `/v1/embed` and `/v1/rerank` in every run).

## 2. The plan

Ordered by what unblocks the most evidence per unit of work. Every item names
the artifact that already justifies it.

**Status (evening): Tier-0 items 1-5 are DONE and verified live** —
`TIER0-FIXES.md` (deadline, slow-not-down probe, per-row usage capture,
wrapper root cause) and `COHERE-REBASELINE.md` (easy 87.35, hard 85.77,
shape measured per row). Tier-1 item 6 (the `density` live gate) is **no longer
blocked by the trial key** — a paced arm keeps a clean Speed axis because the
harness nets the pacer's sleep out of the measured latency — but it is
**underpowered at n=37** (+3/82 rows offline, ~1 row here). Item 10's premise is
corrected: Ref Conciseness is priced, screened and closed as a key-blind lever
(`REF-CONCISENESS-LEVERAGE.md`: +5.82 pp of headroom, +0.9 reachable), and
hard-mode Speed is a 0.04 tie, not a deficit. Nothing further in Tier 1 is worth
a board. The Ref Conciseness axis is NOT closed - only its pruner family is: the
count is decided in the generator, so the work moved there
(`CONCISENESS-PROGRAM.md`: a default-OFF counted-ceiling + citation-budget lever,
and a default-OFF length-controlled judge pass that stops a correctness edge from
being verbosity). The remaining scored lever is RESERVE, which needs the
operator ruling.

### Tier 0 - measurement and transport (do first; no default changes)

1. **Fix the Stage-2 deadline and the abort semantics.**
   Raise the wrapper Stage-2 per-call deadline above the observed p100 (Opus hit
   46.2 s against a 60 s deadline; Sonnet tripped it five times in a row), add
   bounded retry with jitter, and make the harness abort only on evidence of
   transport *down* (health probe / failures with no interleaved success) rather
   than N consecutive slow calls. Evidence: `r460-sonnet-hard-s3.log` abort,
   `official-r460-*-hard.ckpt.jsonl` latency distributions.
2. **Restore Cohere, then re-baseline.** Rotate/raise the key and rerun hard +
   easy. Every current number is a floor and production has rerank on. This also
   re-ranks the Tier-1 levers under the real retriever.
3. **Record tokens (and payload bytes) per row in the batch schema.** One engine
   note (`stage2_tokens_in/out` at the wrapper response) parsed by
   `_provenance`, plus `system_chars`/`user_chars` per dispatch. Keep
   `token_leg_probe.py` as the controlled cross-check. Note the wrapper counter
   is `round(len(user)/4)`, so store the raw chars next to it.
4. **Make capture shape match the board.** Either replay with the board's rolling
   history or record `(row, turn, history_turn_count, system_chars, user_chars)`
   per live dispatch. Evidence: 1.4.
5. **Treat the long-system contract as model-specific.** The wrapper's own log
   rules out a delivery drop (>= 30,000 chars spills to `--system-prompt-file`
   for every model); at 60 k Opus obeyed 3/3 and Sonnet 1/3, so what remains is
   model adherence to a tail instruction inside a 60k stack. Keep the R412
   full-system gate Opus-only until Sonnet has its own measurement, and note
   that fast mode (`CLAUDE_CODE_FAST_MODE`) is Opus-only by design, so it cannot
   make Sonnet faster.

### Tier 1 - levers already at the promotion line

6. **`REGENOLD_EMIT_ALLOC=density` - live paired gate** (R450 evidence). It
   changes which provisions reach the evidence block, so it needs the
   correctness-first gate on hard + easy, not an offline sweep. **Re-scoped
   later:** measure it at n=110 with `--repeats 3`, or ship it as a default
   behind a regression gate - at n=37 the expected effect (~1 row) is below the
   detection floor, and the trial key no longer blocks a *paced* arm
   (`REF-CONCISENESS-LEVERAGE.md` 6/7).
7. **Close R451.** Record HOLD in the R451 doc: title side flat, `bb0.5/0.6`
   beat `sparse` but not `shipped`. Reopen only if the retrieval path changes
   (item 2), since the sweep's control is the offline SVD retriever.
8. **Reclassify the payload-cut levers** (`REGENOLD_PROMPT_COMPACT`,
   `REGENOLD_MINIMAL_COMPOSER`, `REGENOLD_REF_MINIMALITY`): gate them on the easy
   board like any behavior change (1.3), because the stack is read where it is
   delivered. If the goal was bytes, say so in the doc; there is no token win.

### Tier 2 - quality and speed (the scored gaps)

9. **Profile the non-Stage-2 half of a turn.** Opus turn p50 18.0 s vs ~9 s seam
   call (1.1). Instrument retrieval/KG, route, guards and the tail-repair pass
   on ~10 hard rows. **Premise corrected:** the live hard board scores Speed
   86.66 against the frontier's 86.70 (a 0.04 tie, and easy is +6.5 ahead), so
   this is a latency-hygiene item now, not the largest scored deficit. Also note
   hard-mode Speed grades the **pushback** turn only
   (`score_arm._graded_latency_ms`): turn-1 latency on hard is unscored.
10. **Decide on RESERVE** (R442 audit, `PR-AUDIT-456-460.md` §4): answering the
    verbatim pushback with the verified previous answer measures Speed 79.0 ->
    94.8 (~+1 to +2 pp overall) but drops gold heads on two pools and contradicts
    "always Stage-2". Needs an operator ruling; if approved, gate it. **Now the
    only measured lever left above the detection floor** - Ref Conciseness was
    priced at +5.82 pp of headroom with +0.9 reachable
    (`REF-CONCISENESS-LEVERAGE.md`), and density is underpowered at n=37.
11. **Tone slip rg_088** (addresses the reader as "the operator"): 1/37 rows and
    the only tone loss. If touched at all, do it as an addressee ban in the user
    message (the channel that reaches the model, R298/R357 precedent) and tone-
    check it; do not over-fit one row.
12. **The three Sonnet strict flips as guard candidates** (rg_097 wrong Yes/No
    verdict, rg_079 lost "immediately", rg_046 missing the Art 12 logging
    category). Opus passes all three today, so these are belt-and-braces only -
    do them after 9.

### Tier 3 - cost, and the kill list

13. The only billed input is the **user payload** (~7.8k tokens median per
    dispatch; the evidence block ~6.1k of it). The evidence-bundle work removes
    0.2-1.6 % of that: not a cost lever. If cost matters, the measured levers
    are R450 `density` (same budget, better selection) and the conciseness
    contract (grammar-side: 812 -> 752 chars with Sonnet, +5.19 pp conciseness;
    Opus-side gated variants exist in R448).
14. **Kill list** (stop spending on these): title-side field weights (flat),
    `split*` allocations (falsified), evidence micro-minification (0.2-1.6 %),
    "payload cut reduces tokens" (counter ignores the system; the stack is read
    where delivered), Sonnet-as-default (correctness gate + long-system
    truncation), and any comparison run while Cohere is 429.

## 3. What would change the Sonnet verdict

Not more samples of the same thing. In order: (a) adjudicate rg_097 (a wrong
verdict is not a judge artifact), (b) re-measure speed on a stable transport
after Tier 0.1, (c) quantify the long-system truncation's effect on the easy
board, (d) only then the R367 power-floor run on the reference axes.

## 4. Caveats

* Cohere 429 throughout: all live boards are floors on SVD retrieval.
* Hard board n=37 (`--stride 3`), one run per arm; the probe is n=4 draws and
  the canary n=6 calls.
* The wrapper's `usage` is a character heuristic, not a tokenizer.
* The instrument reconstructs criteria and reference answers; none of these
  numbers are official evaluator scores.
* One Sonnet row (rg_085) was served by the Bedrock fallback leg; one arm
  resume used a 150 s per-call deadline (Opus never needed >46.2 s).
* Nothing in this round was flipped; all changed files are uncommitted.

## 5. Artifacts

Boards `evals/bench/results/official-r460-{hard-s3,sonnet-hard-s3}-hard.ckpt.jsonl`;
scores `docs/measurements/r388/score-r460-{hard-s3,sonnet-hard-s3}-hard.json`;
`docs/measurements/r460/{BASELINE-hard-s3,SONNET-VS-OPUS55-GATE,REBASE-R450-R451,CHECKPOINT}.md`;
`paired-r460-sonnet-vs-opus55-hard.json`; `judge-cache-r460-bedrock.jsonl`;
`token_leg_probe.py` + `token-leg-probe.{jsonl,json}`;
`system_delivery_canary.py` + `system-delivery-canary.{jsonl,json}`;
`apply_stage2_sonnet_flag.py`, `apply_r449_r451_cache_keys.py`.
