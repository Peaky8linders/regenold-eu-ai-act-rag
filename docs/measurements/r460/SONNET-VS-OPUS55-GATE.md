# R460 — Stage-2 model gate: `claude-sonnet-5` vs `claude-opus-5-5` (hard board, paired)

## 0. The request, and the premise it rests on

"Make Sonnet 5.5 the main Stage-2 model instead of Opus 5.5 — it is cheaper and
faster." Two facts reshape that:

* There is **no `claude-sonnet-5-5`** on the wrapper catalogue; the candidate is
  `claude-sonnet-5`.
* The R139 floor in `_route_stage_model` rewrites **any** non-Opus Stage-2 id to
  `claude-opus-4-8`, so `P2P_GRAPH_RAG_MODEL`/`stage2_model` could never select
  Sonnet. A gated switch was added for this gate:
  `REGENOLD_STAGE2_ALLOW_NON_OPUS` (default **OFF**, deny-list semantics) and it
  is registered in `_engine_cache_key` (R263.2/R288.1 shape). With the flag OFF
  the route is byte-identical to the shipped one.
* There is **no app-side fast-mode knob**. Fast mode lives in the wrapper /
  Claude Code CLI; the app can only choose the model. This gate therefore
  measures the fastest *app-side* configuration available.

## 1. Arms, provenance, and the one harness interruption

| | A (shipped) | B (candidate) |
| :-- | :-- | :-- |
| label | `r460-hard-s3` | `r460-sonnet-hard-s3` |
| rows | `--mode hard --stride 3`, n=37 | same 37 rows |
| Stage-2 env | `P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-5-5` | `P2P_GRAPH_RAG_COMPLEX_MODEL=claude-sonnet-5` + `REGENOLD_STAGE2_ALLOW_NON_OPUS=1` |
| Stage-2 rows | 28 primary, 0 fallback, 9 no Stage-2 | 27 primary, **1 fallback**, 9 no Stage-2 |
| recorded model | `claude-opus-5-5` x28 | `claude-sonnet-5` x28 |
| errors | 0 | 0 |

Base: worktree @ `a9553ed` = `origin/main` (`git log a9553ed..origin/main` is
empty after a fetch, so the "rebase onto origin/main" request is a no-op; the
R449-R451 transplant onto that base is documented in `REBASE-R450-R451.md`).

**B was interrupted and resumed.** At 28/37 the harness guard tripped:
`Stage-2 PRIMARY transport is down: 5 consecutive primary calls failed (last:
network_error: read timed out)`. The wrapper Stage-2 call is made with the
provider's default **60 s client deadline**; five Sonnet generations in a row
crossed it. A's 74 turns never did (max 46.2 s, p50 18.0 s), so raising the
deadline to `OPENAI_TIMEOUT_SECONDS=150` for the resumed 9 rows cannot bind A:
the interruption is a transport property of B's window, not a config difference
that favours either arm on any axis. B finished 37/37, 0 errors.

**Judge.** One shared cache, pinned identity
`bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`, `--repeats 3`,
grouped, `--mode hard`. Scoring reported `9 cached, 28 to judge` — the 9 cached
rows are exactly the no-Stage-2 rows whose answers are byte-identical in both
arms, which is the intended sanity check on the pairing.

## 2. Paired result (`paired_ab`, n=37 shared rows, 0 dropped)

| axis | A Opus 5.5 | B Sonnet 5 | delta | 95% CI | McNemar |
| :-- | --: | --: | --: | :-- | :-- |
| ans_correctness_loose | 93.47 | 90.99 | -2.48 | [-6.08, +0.00] | 0/3, p=0.25 |
| ans_correctness_strict | 89.19 | 81.08 | **-8.11** | [-18.92, +0.00] | 0/3, p=0.25 |
| ans_conciseness | 81.61 | 86.80 | **+5.19** | [+1.96, +8.47] | 22/5, p=0.0015 B> |
| ref_correctness_loose | 95.71 | 100.00 | +4.29 | [+0.00, +11.43] | 2/0, p=0.50 |
| ref_correctness_strict | 82.38 | 80.48 | -1.90 | [-10.00, +4.29] | 2/2, p=1.00 |
| ref_conciseness | 59.90 | 60.24 | +0.33 | [-4.71, +5.38] | 6/5, p=1.00 |
| regulatory_tone | 97.30 | 100.00 | +2.70 | [+0.00, +8.11] | 1/0, p=1.00 |
| resp_speed | 82.76 | 67.29 | **-15.47** | [-22.56, -9.26] | 3/34, p<0.0001 A> |
| **overall** | **84.52** | **82.32** | -2.20 | | |

`gold_dropped_head`: A=2, B=0, `new_drops_in_b=[]`. Mean answer chars 812 -> 752.
B's board (82.32) still clears the published frontier overall (81.7) and gains
on conciseness/tone/reference-loose; it is short on answer-strict and speed.

## 3. Gates, in the binding R448 order

**Gate 1 — answer correctness: FAIL.** Strict falls 8.11 pp; three rows pass ->
fail, none the other way:

* **rg_097** (`2/2 -> 1/2`) — substantive. The criterion's gold verdict is
  **"No"** for healthcare decision-making as a listed high-risk area; B answers
  **"Yes"**. This is a wrong verdict, not a wording difference.
* **rg_079** (`4/4 -> 3/4`) — B omits the Art 20(1) duty to "immediately bring
  the system into conformity".
* **rg_046** (`6/6 -> 5/6`) — B omits the Art 12 logging-mechanism description.

At n=37 a 3-row flip is not significant (McNemar 0/3, p=0.25). The repository
rule is not "significant", though: a lever is promoted only on evidence of **no
loss**, and a -8.11 pp point estimate with a wrong-verdict row cannot qualify.

**Gate 2 — references: PASS.** No new drops: `gold_dropped_head` A=2 -> B=0,
`new_drops_in_b=[]`; ref_loose +4.29 with 2 rows gained and 0 lost; ref_strict
-1.90 (2/2 flips, p=1.0). Never net — and here netting is not needed.

**Gate 3 — other axes: PASS.** Conciseness +5.19 (significant), tone 100.0
(+2.70), answers 812 -> 752 chars.

**Gate 4 — latency and tokens: MIXED, and the premise is only half right.**

* Board Resp. Speed: **-15.47 pp, 34 of 37 rows slower**, p<0.0001. But this
  axis carries the wrapper's queue and the five 60 s-deadline timeouts; the
  controlled seam probe below does not reproduce it.
* Tokens (probe, below): prompt tokens are **identical** between the models and
  scale exactly with the user payload (`chars / 4.00`); completion tokens are
  equal (median 227.5 vs 220.5). There is no token saving to buy.

## 4. The token leg — `token_leg_probe.py` on the recorded payloads

The live checkpoints carry `latency_ms` but no usage, so the token leg replays
the **recorded Stage-2 payloads** (`stage2-payloads.jsonl`) against both models
with byte-identical input. 4 draws, 10 calls, 0 errors:

| draw | user chars | prompt tokens (both models) | A out | B out | A ms | B ms |
| :-- | --: | --: | --: | --: | --: | --: |
| rg_003 | 40,700 | 10,175 | 312 | 192 | 8,256 | 6,722 |
| rg_062 | 31,101 | 7,775 | 255 | 263 | 6,683 | 6,515 |
| rg_008 | 15,975 | 3,994 | 186 | 206 | 9,653 | 6,109 |
| rg_069 | 39,663 | 9,916 | 181 | 249 | 9,868 | 44,114 |
| **median (n=4)** | | **8,845.5** | **220.5** | **227.5** | **8,954.5** | **6,618.5** |

Two findings that outlive this gate:

1. **The usage counter ignores the system stack - but the model does not.** On
   `rg_003`, substituting the
   61-char persona for the full stack leaves `prompt_tokens` at **10,175** for
   *both* models: delta 0. The billed prompt is the user payload alone, at
   exactly 4.00 chars/token on every draw and model. The R460 evidence-bundle
   cut therefore removes **wire bytes only** (-65.8 % of the payload is the
   static system), and nothing the usage counter can see. The only part of
   the payload the counter prices is the evidence block, where the census
   found 0.2-1.6 % provably removable.
   What the counter cannot show, the canary settles
   (`system_delivery_canary.py --reps 3`, 18 calls, run after this section was
   first drafted): the system message **is** delivered - 3/3 at 129 and 3,131
   chars for both models - and at **60,774 chars Opus 5.5 obeys 3/3 while
   Sonnet 5 obeys 1/3**. That is not a transport drop: the wrapper's own log
   records both long calls as `System prompt 60877 chars >= 30000 argv limit -
   passing via --system-prompt-file` (`claude_cli.py` spills >= 30,000 chars to
   a temp file), i.e. the same path for both models, so the divergence is
   model-side adherence to a tail instruction inside a 60k stack. Consequences:
   the payload cut is a *behavioral* lever wherever the stack is delivered (the
   single-turn shape: easy mode and the opening hard dispatches of a run), not
   an inert byte reduction; and a long system prompt is a weaker contract on
   Sonnet than on Opus, which is a second reason not to promote it on this
   configuration.
2. **Per-call latency does not explain B's board speed.** At the seam B is at or
   below A on 3 of 4 draws (median 6.6 s vs 9.0 s) with equal output tokens. The
   board's -15.47 is wrapper transport (queueing + read timeouts), which is real
   production cost but not model cost. Treat B's Resp. Speed as
   transport-contaminated, not as a model property; do not read it as evidence
   either way.

## 5. Verdict

**HOLD. `claude-opus-5-5` stays the Stage-2 model; `REGENOLD_STAGE2_ALLOW_NON_OPUS`
stays default OFF (it is the switch a future promotion would flip).**

The premise "cheaper and faster" does not survive measurement on this board:
there is no token or price win (prompt identical, completion equal, and the
subscription wrapper bills none of this per token), and the one axis that
favours Sonnet - conciseness and tone - is paid for with a wrong-verdict row on
the gate that comes first. Mechanically the swap works end to end (37/37, 0
errors, `stage2_served_by=primary` on 27/28, no fallback rows except rg_085),
so the lever is safe to keep as a tested option; it is not safe to promote.
Independently of the axes: at production system length the wrapper delivers
the stack to Opus and a degraded (head-only) version to Sonnet, so promoting
Sonnet would silently change what the easy-board Stage-2 calls see.

To reopen: (a) adjudicate the three strict flips, rg_097 first; (b) re-measure
speed on a transport-stable window (wrapper-health gate + retry budget) so the
timeouts do not decide the axis; (c) at the repository's own power floor
(R367: reference axes n>=120) if the reference deltas are to be claimed.

## 6. Caveats

* **Cohere is out of quota** (trial key, 429 on `/v1/embed` and `/v1/rerank`),
  so both arms retrieve on the local SVD fallback. Every number here is a floor
  and is comparable only arm-to-arm.
* n=37 (`--stride 3`), not the 110-row board.
* B's row **rg_085** was served by the Bedrock fallback leg after a wrapper read
  timeout; it is graded like any other row and reported here, not hidden.
* B's last 9 rows ran with a 150 s per-call deadline (A: 60 s, never bound).
* The instrument reconstructs criteria and reference answers; do not quote any
  of these as official evaluator scores.
* The wrapper's `usage` is `round(len(user)/4.0)`, a character heuristic; it
  cannot price the system stack. The canary is n=6 calls (3 sizes x 2 models).
* Worktree is uncommitted: no default was changed, nothing was pushed.

## 7. Artifacts

* Boards: `evals/bench/results/official-r460-{hard-s3,sonnet-hard-s3}-hard.ckpt.jsonl`
* Scores: `docs/measurements/r388/score-r460-{hard-s3,sonnet-hard-s3}-hard.json`
* Paired: `docs/measurements/r460/paired-r460-sonnet-vs-opus55-hard.json`
* Judge cache (shared): `docs/measurements/r460/judge-cache-r460-bedrock.jsonl`
* Token/latency leg: `docs/measurements/r460/token_leg_probe.py`,
  `token-leg-probe.jsonl`, `token-leg-probe.json`, `token-leg-probe.log`
* Opus board write-up: `docs/measurements/r460/BASELINE-hard-s3.md`
* Lever patch: `docs/measurements/r460/apply_stage2_sonnet_flag.py` (calls
  `_stage2_allow_non_opus`; 30 tests pass with the flag OFF)
