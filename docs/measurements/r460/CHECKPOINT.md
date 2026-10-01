# R460 — the Stage-2 payload census, and what the evidence bundle can actually cut

**Status: measurement + mechanism. Nothing is flipped, no default moved, nothing wired.**

The request was to cut the Stage-2 prompt and context payload down from the measured
~115k characters with an evidence-bundle design, gated so correctness and gold
references are unchanged while latency and token use fall. The first honest step is
not a cut — it is a census, because a total cannot say which bytes are removable.

## 1. Method

The real route, the real retrieval, the real prompt builders, with the Stage-2
provider **stubbed at the provider seam** (the R423 probe's pattern). No network, no
spend. `REGENOLD_QUERY_DENOISER=0` / `REGENOLD_EXTERNAL_EMBEDDINGS=0` remove the two
network-dependent legs so runs are comparable (the R422/R423 baseline).

Instruments (all in this directory):

* `stage2_payload_census.py` — decomposes system vs user, then the user payload by
  section, then the evidence block by section, plus a redundancy count per draw.
* `capture_payloads.py` — writes the raw draws to `stage2-payloads.jsonl`, the
  recorded-draw artifact every later minifier is measured against.
* `evidence_bundle_cut.py` — measures the gated cuts over those draws. No route.
* `_dump_payload.py` — dumps one draw's system+user to disk for inspection.

Sample: `R460_ROWS=10 R460_STRIDE=3 R460_DIFFICULTY=HARD`. Ten HARD single-turn
official draws were attempted; **seven reached Stage-2**. `rg_033`, `rg_038` and
`rg_074` serve a curated/deterministic answer (`stage2_skipped_curated_authoritative`)
and are reported vacuous, never averaged in.

Retrieval is **not** byte-stable across invocations (R423 measured the same row
dispatching 19,206 then 42,782 chars), so per-row totals move with retrieval and only
the aggregate and the section SHARES are read.

## 2. Where the characters actually are

Seven HARD single-turn draws, median chars:

| Block | Median chars | Share of payload |
|---|---:|---:|
| **Static system instruction stack** | **60,643** | **66%** |
| Evidence block (`EU AI ACT REFERENCES:`) | 24,272 | 26% |
| Answer contract + completeness + shape | 3,855 | 4.2% |
| Concise block (`LENGTH LIMIT`) | 1,307 | 1.4% |
| Reference minimality + sub-paragraph + coordinates + provisions-to-name + final sentence | 1,552 | 1.7% |
| Header (`ORIGINAL QUESTION`, `LEGAL VERSION`) | 237 | 0.3% |
| **Total (median)** | **91,744** | |

The higher R455 figure (~114,436) is the long-question end. The system half is
**constant** across every draw — it is one string, `ANSWER_GENERATE_SYSTEM`, 60,646
chars. The widest draw in this sample was `rg_003` at `60,643 + 40,700 = 101,343`.

Inside the evidence block (same sample, medians):

| Evidence section | Median chars |
|---|---:|
| VERBATIM PROVISION TEXT | 9,772 |
| APPLICABLE OBLIGATIONS | 5,800 |
| KNOWLEDGE-GRAPH SUB-POINT DETAIL | 4,497 |
| ARTICLE-SPECIFIC OBLIGATIONS | 1,263 |
| DIMENSION DETAILS | 730 |
| REFERENCED ANNEXES AND RECITALS | 497 |
| KNOWLEDGE-GRAPH CROSS-REGULATORY MAPPINGS | 290 |

## 3. The finding that reframes the request

**The payload is not dominated by redundant context. It is dominated by a static
system prompt.** The evidence block is 26% of the payload, and inside it only
**0.2–1.6% is provably removable** (a provision rendered twice under two node ids, or
member lines under a heading that itself says "NOT ENGAGED ... do NOT enumerate").

Even the "NOT ENGAGED" member lists are **not free**: the ANSWER SHAPE clause
explicitly says "the COMPLETE STRUCTURE lists in the evidence block describe whole
provisions", so deleting the lists leaves that instruction pointing at nothing. An
evidence-only redesign cannot halve 115k. The lever is the system prompt, and it
already exists.

## 4. The 60.6k lever, measured at the seam

`resolve_answer_system()` (`app/data/graph_rag_prompts.py`) already supports smaller
system prompts. Measured on the same row, same route, same stub:

| Config | System chars | User chars |
|---|---:|---:|
| default | 60,643 | 40,700 |
| `REGENOLD_PROMPT_COMPACT=1` → `COMPACT_ANSWER_SYSTEM` | **287** | 40,700 |
| `REGENOLD_MINIMAL_COMPOSER=1` → `MINIMAL_COMPOSER_SYSTEM` | 3,181 | 40,700 |

The **user** payload is byte-identical in all three arms. Both flags are already
folded into `_engine_cache_key` (`app/routes/regenold.py`, `REGENOLD_MINIMAL_COMPOSER`
~L1578, `REGENOLD_PROMPT_COMPACT` ~L1698), so an in-process two-arm A/B is valid.

⚠ **Correction to the record.** `docs/measurements/r442/PR-AUDIT-456-460.md` P2 says
`REGENOLD_PROMPT_COMPACT=1` "dispatch[es] a request byte-identical to the default".
That is true of the **user** payload only; the **system** payload changes by 60,356
chars. Read as a whole-request claim it is wrong, and it is the likeliest reason a 60k
lever sat ungated: it looked like a no-op. R442's own note anchors the claim at "the
provider seam", so the measurement did what it said — the inference drawn from it is
what needs correcting.

⚠ **Delivery is not settled.** R282/R308 measured that the *claude_cli* transport drops
the system message 100%. The production transport is `openai_wrapper`, and
`app/llm/openai_wrapper_provider.py` **does** put `{"role": "system", ...}` on the wire
(L579–587). Whether the upstream honours it is unmeasured. That matters: if the system
stack is dropped, cutting it is free; if it is delivered, cutting it is a quality lever
(R282 measured forwarding it as rubric-negative: kw_recall −0.267).

## 5. The evidence bundle — what it is, and what it buys

`app/engines/evidence_bundle.py` is a typed, **lossless** projection, not a rewriter:

* `parse_evidence_block(text) -> EvidenceBundle` carries per-item `section`,
  `source_id`, canonical `provision`, exact `text`, `context_only` and `line_no`; the
  span stops at the `ANSWER CONTRACT`, so a whole-message caller can splice the
  minified span back without doubling the contract.
* `render()` returns the parsed bytes verbatim; `verify()` raises unless the typed view
  reproduces `raw` line-for-line (the R448 "byte-identical replay" requirement).
* `minified(level)` drops **only** bytes that are provably redundant, and is a strict
  line subsequence of `raw` at every level (pinned by test).
* `minify_evidence_block()` is the gate-aware entry point; when the gate is OFF it
  returns its argument untouched.

Level 1 removes a provision rendered twice (the real `kb-risk_mgmt-Art. 6` /
`kb-xref-risk_mgmt-Art. 6` duplication); level 2 additionally removes the indented
member coordinates under a `STRUCTURE of ... NOT ENGAGED` heading, keeping the heading,
its count and the do-not-enumerate instruction.

Measured over the seven recorded draws (`evidence-bundle-cut.json`):

| Lever | Median payload | Cut |
|---|---:|---:|
| before | 91,744 | — |
| system compact only | 31,388 | **−65.8%** |
| system compact + bundle L2 | 30,998 | **−66.2%** |
| worst-case draw (`rg_003`) | 101,343 → 38,120 | −62.4% |

Evidence-only cut: **L1 0.2%, L2 1.6%**. All draws lossless at both levels.

So: the bundle is the right structure for the R448 recommendation (canonical id,
provision, mandatory/optional, claim↔evidence wiring) and it is the honest, small,
second lever. It is **not** the big cut.

## 6. Gate plan (nothing flips without this)

Per R448's binding order — correctness first, references second, other axes third,
latency/tokens last, and only among candidates that passed the first three:

1. **Wiring (required before any gate).** Fold `REGENOLD_EVIDENCE_BUNDLE` +
   `REGENOLD_EVIDENCE_BUNDLE_LEVEL` into `_engine_cache_key`, and call
   `minify_evidence_block(reference_block)` once at the production reference-block
   call site in `_graph_rag_impl._claude_max_enhance_answer` (~L9962), before
   `build_evidence_answer_user`. Default OFF, so the shipped payload is byte-identical.
   One guarded call site, no other behaviour change. (Not done in this round: R448's
   order puts the extraction + replay ahead of the wired experiment, and the gate has
   not been run.)
2. **Gate 1 (correctness) → Gate 2 (gold references).** Run the two candidates as
   separate levers — `REGENOLD_PROMPT_COMPACT` alone, and `REGENOLD_EVIDENCE_BUNDLE`
   alone. Do **not** stack them: a stacked arm cannot attribute a regression. This
   requires a clean full-board re-baseline of the current `origin/main` build first
   (the R436 board predates R423/R448/R452–R456), one pinned judge identity, per-row
   provenance, and `gold_dropped_head` reported with row ids and coordinates, never
   netted.
3. **Delivery probe (cheap, do it first).** Send the same question twice with a
   behavioural instruction in the system slot vs the user slot (the R308 BANANA test)
   over `openai_wrapper`. If the system slot is inert, the 60.6k cut is free and the
   compact prompt is a pure token/latency win.

## 7. Limits

* Chars are not tokens. The `≈ chars/4` column in `evidence-bundle-cut.json` is labelled
  as the rough estimate it is; real token/latency numbers need the live gate.
* The census covers HARD **single-turn** official rows. Production hard mode is a
  pushback over a flattened nine-exchange history, whose user payload is larger; the
  system half is unchanged by that, so the split holds, but the evidence share here is a
  lower bound.
* Judge identity must be pinned; do not compare deltas across judge identities.
* This round flipped nothing and wired nothing. `baseline` and `frontier` are untouched.

## 8. Artifacts

* `stage2-payload-census.json` — per-draw and aggregate decomposition (the sample above).
* `stage2-payloads.jsonl` — the seven recorded draws (system + user, raw).
* `evidence-bundle-cut.json` — per-draw cut table.
* `app/engines/evidence_bundle.py` — the typed, gate-bearing module.
* `tests/test_r460_evidence_bundle.py` — 29 tests: gate deny-list, byte-identical
  render, typed projection, subsequence + engaged-content invariants, and two tests
  pinned to the capture that fail if the evidence block is ever re-labelled as the
  dominant cost.

---

## 2026-09-30 (later) -- Sonnet-vs-Opus Stage-2 gate is DONE, verdict HOLD

`SONNET-VS-OPUS55-GATE.md` carries the full result. Headlines: 37/37 rows both
arms, paired n=37, one shared judge cache; answer-strict -8.11 (3 rows, of which
rg_097 is a wrong verdict), references PASS (no new gold drops, A=2 -> B=0),
conciseness/tone PASS, board speed -15.47 but transport-contaminated (five
consecutive 60 s-deadline timeouts aborted the first Sonnet run at 28/37; it was
resumed with a 150 s deadline, which never binds the Opus arm). Token leg:
prompt tokens equal the user payload at exactly 4.00 chars/token, identical
across models and invariant to the 60,643-char system stack, so the payload cut
buys wire bytes, not tokens. Nothing was flipped;
`REGENOLD_STAGE2_ALLOW_NON_OPUS` stays default-OFF.

---

## 2026-09-30 (final) -- analysis + plan

`ANALYSIS-AND-PLAN.md` consolidates the round and lists the next work in tiers.
Two findings landed after the gate doc: the system-delivery canary shows the
wrapper DOES deliver the system at short/mid sizes, delivers the 60,774-char
stack to Opus 5.5 but not to Sonnet 5, and the wrapper's `usage` is
`round(len(user)/4.0)` (a character heuristic, blind to the system). Tier 0 of
the plan is measurement/transport: Stage-2 deadline + abort semantics, restore
Cohere and re-baseline, per-row token/byte capture, capture-shape parity, and
characterising the long-system behaviour for Sonnet.

---

## 2026-09-30 (Tier-0) -- transport + instrumentation fixes landed

`TIER0-FIXES.md` records them: the wrapper Stage-2 deadline
(`REGENOLD_STAGE2_WRAPPER_TIMEOUT_S`, default 150 s, cache-keyed), the harness
slow-not-down probe (`REGENOLD_BATCH_PROBE_BEFORE_ABORT`, default ON), and
per-dispatch `stage2_usage` capture into the row schema. 397 tests pass, lint
neutral. The wrapper was root-caused read-only: `WRAPPER_FORWARD_SYSTEM_PROMPT`
is ON, >= 30,000-char systems spill to `--system-prompt-file` for BOTH models,
so the canary's 3/3 (Opus) vs 1/3 (Sonnet) at 60 k is model-side. Still blocked:
Cohere quota (live numbers remain SVD floors), the R450 `density` live gate,
and the R451 HOLD note.

---

## 2026-09-30 (Cohere) -- re-baseline is in

`COHERE-REBASELINE.md`: easy **87.35** (frontier 80.9, ahead on all 8 axes),
hard **85.77** (frontier 81.7; +2.86 ref_loose, +2.38 ref_strict, tone 100,
speed 86.66 vs 86.7 - the only axis still behind, by 0.04). Both n=37, 0 errors,
Opus 5.5, all Tier-1 knobs at default, with the Tier-0 instrumentation live.
Live shapes: easy rows send the full 60.6k stack (turns=1); hard rows send the
61-char persona on EVERY dispatch (fixed fixture, turns=20), so the hard board
never carries the stack. Prompt counter is `len(user)/4.0` to the digit
(easy 9,236.5 median, hard 8,360). Hard `rg_049` is deterministic-served and
reported. The Cohere key is TRIAL (10 rerank calls/min): one board fits at
natural pace, nothing may run alongside it, and the R450 `density` live gate
needs a production key (pacing would corrupt the Speed axis). The first hard
attempt aborted because my own rate-limit burst stole the minute's budget, not
because of the board.

---

## 2026-09-30 (Ref Conciseness) -- priced, screened, closed

`REF-CONCISENESS-LEVERAGE.md` (+ `ref_conc_leverage.py`, `ref_prune_screen.py`,
both offline and exact: they reproduce 59.14 / 61.10 / 85.77 / 87.35 from the
checkpoints). Ref Conciseness is the lowest axis (59.14 hard) and the
highest-leverage one (elasticity 0.181 vs 0.107-0.132 for the rest); the ceiling
is +5.82 hard / +5.55 easy, and **+0.9 is what any key-blind rule can reach**.

* Exact structure: rc = `min(1, |expected|/|provided|)`, a count ratio; 27/35
  hard rows have a ONE-ref key, 24/35 are over-supplied, 88 supplied vs 44
  expected (2.00x). Because the judge prompt carries the KEY's provisions and the
  answer text only (never our ref list), ref pruning cannot move the answer axes
  - the only risk is the two reference axes.
* Screened: mention +0.55/+0.54 (bit-identical correctness axes), dedupe
  +0.00/+0.19, drop-redundant-parent a no-op (no row carries such a pair),
  cap@2 +0.36/-0.11, cap@1 -1.00/-1.83, mention+cap@2 +0.79/-0.11. Ceilings:
  min preserving subsequence +4.96/+4.68, oracle match +3.06/+2.75.
* Why the mention rule is weak: of supplied refs, 63.6% are NOT key-relevant but
  ARE named in the answer prose (only 3.4% are neither). `graph_rag_prompts.py`
  already says the same thing -- a pruner downstream of the prose is a no-op or
  drops gold; the count is decided in the generator, and the generator already
  carries the minimality contract (`USER_REF_MINIMALITY` V2 default ON).
* Two premises corrected: (1) hard-mode Speed grades the **pushback** turn only
  (`_graded_latency_ms`), so turn-1 latency on hard is unscored; (2) the rerank
  pacer's sleep is **netted out** of measured latency (`_net_of_pacing`, R409), so
  the trial key does not block a paced arm -- the R450 `density` gate is blocked
  by *power* at n=37 (~1 row), not by the key.
* Nothing changed a default; the `mention` candidate (+0.55) is below the n=37
  detection floor and was recorded, not run. RESERVE remains the only measured
  lever above the floor and still needs the operator ruling.

---

## 2026-09-30 (Conciseness program) -- generator + measurement levers (default OFF)

`CONCISENESS-PROGRAM.md`. The Ref Conciseness negative was a PRUNER negative, not
an axis negative: both conciseness axes are one-sided ratios, so the scoring
optimum is the minimum answer that still covers every criterion, and the gold
reference answer is a per-row existence proof that it fits.

* Measured targets (`conciseness_program_analysis.py`): answers ship 1.25x the
  reference length (81% of hard rows over it) with 2.0x its citations, while
  `answer_need.target_chars` is ALREADY calibrated (median -36 chars from the
  reference). So it is a COMPLIANCE failure, not an estimation one. Prize:
  ans_conc 81.54 -> 100 is +1.9 pp overall; ref_conc 59.14 -> 100 is +5.8 pp.
* Citation COUNT is not shape-dependent: |expected| is 1.25-1.50 on every shape
  and `<= 2` covers 97% of the 110 gold rows. Which two must stay the model's
  judgement - every blind cap pays for its conciseness on Ref Strict.
* Implemented, default OFF: `REGENOLD_CONCISE_CALIBRATION`
  (`answer_need.calibration_block`, appended LAST in `build_evidence_answer_user`)
  restates the shipped ceiling as a COUNTED self-check, adds a numeric citation
  budget (2 direct / 3 scenario) and a structural skeleton at the target size;
  registered in `_engine_cache_key`; tests `test_r460_conciseness_calibration.py`
  (8). Byte-identical when off.
* Implemented, default OFF: `--length-control` on `evals/official/score_arm.py`
  (`rubric.truncate_to_chars` + `_length_controlled_rows`) re-judges every answer
  CUT to its reference length and reports those axes beside the raw ones in the
  console and the payload, so a correctness edge cannot be verbosity; loud when
  the judge transport dies; end-to-end tested with a faked transport
  (`test_r460_length_control.py`, 7).
* 207 tests pass across the touched suites; ruff clean on every file touched
  (the one UP037 in `regenold.py` is pre-existing at HEAD).
* Gate design in the doc: paired hard board with the flag ON vs the recorded
  `r460-cohere-hard-s3`, scored with `--length-control`; acceptance is
  ans_conc >= 92 and ref_conc >= 85 with no correctness loss.

---

## 2026-09-30 (Conciseness gate on BEDROCK) -- the mechanism works, +0.95 overall

Operator instruction: the Claude Max tunnel is low on quota, so the gate ran on
the Bedrock client for both the live arm and the judge. Both arms therefore ran
the SAME Bedrock model (`eu.anthropic.claude-opus-4-6-v1`, after the credential
403s Opus 5 / 4.8), which makes this a within-transport A/B and not a frontier
comparison. Transport inversion is explicit and auditable: the primary is pinned
off-contract (`REGENOLD_STAGE2_PRIMARY_HOSTS=bedrock-direct.invalid`), every
dispatch logs the strict-transport refusal + `bedrock_auto_fallback`, and every
row records `stage2_served_by=fallback`.

`GATE-CONCISENESS-BEDROCK.md`. Arms A `r460-bedrock-hard-s3` (flag OFF) and B
`r460-bedrockconc-hard-s3` (`REGENOLD_CONCISE_CALIBRATION=1`), 37/37 rows each,
0 errors, 28/37 polished in BOTH (same denominator as the wrapper baseline).

* Paired, n=37: **ref_conciseness 59.14 -> 63.90 (+4.76, CI [+0.29, +10.43], the
  only axis whose CI excludes zero, McNemar 7/1 p=0.070 B>)**; ans_conciseness
  82.99 -> 84.96; ans_loose 93.69 -> 95.95; ans_strict / ref_loose / tone flat;
  ref_strict -2.86 (one flip); speed +0.11. **overall 84.94 -> 85.90 (+0.95)**.
  `gold_dropped_head` 2 -> 2: the numeric budget did NOT cost gold recall, which
  is exactly where every post-hoc pruner failed. Answers 786.7 -> 755.8 chars,
  refs 2.78 -> 2.49 per row.
* First launch died on a Cohere rerank failure at row 1 - my own smoke rows had
  spent the trial key's minute. Re-run paced at `--cohere-rerank-min-gap 7`; the
  harness nets the pacer out of latency (R409), so Speed stays clean.
* NEW measurement finding (`--length-control`): cutting answers to their
  reference length drops ans_loose 94.07 -> 54.81 (A) and 96.30 -> 51.85 (B), i.e.
  ~40 pp of our answer correctness is LENGTH-MEDIATED. The frontier prints
  ans_conc 71.8 (~1.39x the reference length), so their correctness was also
  measured long; the instrument can now measure any arm at equal length.
* Not promoted: n=37, one draw per row, and a different model vintage than the
  shipped Opus 5.5-over-wrapper. Next confirmation: the same paired A/B on the
  wrapper transport with `--repeats 3`.

---

## 2026-10-01 (Conciseness gate on the SHIPPED transport) -- REFUSED, default stays OFF

The Bedrock gate's stated confirmation step, executed on the transport and model
that actually ship: Claude Max wrapper, `claude-opus-5-5`, n=37 (`--stride 3`),
both arms drawn fresh under one protocol, one judge identity and one cache
(`bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`), scored with
`--length-control`. Tunnel liveness probed first (one call: `claude-opus-5-5`,
7.3 s, stop, `wrapper_tunnel_probe.py`). Arms `r460-tunnel-off-s3` (flag absent)
and `r460-tunnel-on-s3` (`REGENOLD_CONCISE_CALIBRATION=1`), 37/37 rows and 0
errors each, p50 21.4 s / 22.0 s. `WRAPPER-CONFIRM.md`; launcher
`run_gate_wrapper.sh`, scorer `score_gate_wrapper.sh`.

* Paired: **ref_conciseness 58.43 -> 63.95 (+5.52, CI [+0.71, +11.90], McNemar
  7/1)** -- the count mechanism REPRODUCES (Bedrock gate: +4.76 [+0.29, +10.43]),
  refs/row 2.78 -> 2.51, and the axis never touches the judge.
* But **ans_conciseness 82.32 -> 77.84 (-4.49, CI [-8.77, -0.68])**: on Opus 5.5
  the block makes answers LONGER (+65 chars, 17/26 rows, CI [+10, +119]; the
  Bedrock gate's opus-4-6 SHORTENED them 786.7 -> 755.8). Overall
  **86.90 -> 86.09 (-0.81)**; speed -1.96 (p<0.0001) is CONFOUNDED, not a lever
  result - B logged 17 degenerate-completion events and 8 Bedrock-fallback
  attempts against A's 5 and 2, so B paid more retries.
* Attribution, because the board alone misleads: the correctness / tone /
  gold-head deltas are NOT the lever. They are carried by exactly two rows whose
  transport degraded differently (`rg_037` shipped a `prior_turn` answer in B --
  its refs `Article 49.4/71.4/6.3` against the key's `Annex VIII.a`; `rg_049`
  shipped a `deterministic` draft in A), and the other 35 rows have identical
  judged criteria vectors (`wrapper_gate_subset.py`, recomputation asserted
  against the scored axis before it is used).
* **Verdict: NOT promoted.** `calibration_enabled()` keeps its allow-list; the
  prepared `promote_conciseness_calibration.py` is deliberately unapplied, and
  `CONCISENESS-PROGRAM.md` section 5 records the refusal plus the acceptance
  targets that are not claimed. Next gate: the COUNT-ONLY variant of the block
  (the citation budget without the length battery), the half that survived two
  transports.
* Replicates 2-3 were not spent (tunnel quota is the scarce resource; the
  deciding delta is systematic, not marginal). `run_gate_wrapper.sh 3` resumes
  them from the existing checkpoints if a draw-stability check is wanted.
