# R418 checkpoint — CR remediation shipped, live hard-mode re-eval in flight

**Branch** `fix/r409-r408-audit` · **commit** `86b2bfd` · **PR** #430 → merged as
**`b451463`** · **deployed** `b45146304c80` (verified on `/healthz.commit`, 2026-09-13).

## 1. What this round was

A deep code review of the last five merged PRs (#424 `f658a49`, #427 `04aa6c9`,
#428 `b27419b`, #429 `94bdbdc`, plus the R416/R417 branch work), run per
`CR-SKILL.md` with **ten specialist agents** — five lenses (`logic`, `errors`,
`contract`, `concurrency`, `security`) × two partitions (`app/`, and
`evals/`+`tests/`) — dispatched in parallel by `scripts/deep_code_review.py`.

Raw agent reports: `docs/reviews/cr-r416/*.md` (10 files).
Full ledger with dispositions: `docs/reviews/r418-cr-dispositions.md`.

**Outcome:** 17 production/harness defects fixed and pinned, **1 external claim
refuted by measurement**, 4 findings recorded open with a reason.

## 2. The result that matters — a falsification, not a fix list

Fix #2 was the single most-demanded change in the review: two lenses
(`contract-app`, `concurrency-app`) independently proved that
`is_challenge_turn(live_question)` can never fire the R377 leading-confirmation
family, because the predicate derives "a prior turn exists" from the
`Latest question:` flatten marker and the bare live turn never carries it.

Applying it **alone caused a regression**, and the regression was invisible to
reading:

| tree | deterministic eval result |
| :--- | :--- |
| clean HEAD (worktree) | **253 / 255** |
| `has_prior_turns=True` alone | **245 / 255** — 8 `in_scope_multi_turn` negatives flipped to `I cannot answer your question from my Knowledge Graph` |
| both halves of the fix | **253 / 255**, HEAD's exact failing set |

Mechanism: the recovery branch sets `self_contained_focus=True` for its
*reference-side* narrowing, and the **scope gate** reads that same flag to decide
whether to classify the live turn alone. On this branch the live turn is a dispute
that is **not self-contained by construction** (the branch is guarded on
`not _live_turn_is_self_contained(live_question)`), so scope had no anchor to see
and refused.

How it was caught, since this is the transferable part: run the eval gate on a
clean `HEAD` **worktree**, dump per-scenario outcomes to JSON on both trees, and
diff the failing-id sets. Aggregate pass rates hide a swap; the per-id diff names
all 8. The fix is a new `challenge_recovered` marker on
`QuestionHistoryResult` — the reference machinery stays narrowed, the scope gate
keeps reading the whole conversation.

## 3. Validation

| check | result |
| :--- | :--- |
| full test suite | **8 253 passed, 0 failed, 2 skipped** (268 s; the deterministic eval gate included) |
| ruff vs HEAD, 13 changed sources | **111 vs 111** — zero new lint |
| CI on the PR (clean clone) | `Test suite` pass 2 m 44 s · `Deployable` pass 35 s |
| deploy | `/healthz.commit == b45146304c80` |

Two tests were updated because they encoded now-refuted behaviour, both in the
**stricter** direction:

* `test_row_transport_*` — it asserted `stage2_fell_back is False` on an
  unobservable transport, i.e. "a row we never observed was tunnel-served". The
  corrected contract returns **no provenance**, so `_fallback_served`'s
  missing-key conservatism fires and the row is dropped instead of credited.
* the eval-negative scenarios above.

## 4. Live evaluation — the sample that found the blocker, and the full run

The full 110-row hard batch launched on 2026-09-13 was killed by a session restart
after one row (`official-r418-hard-hard.ckpt.jsonl` is 1 row, 14.8 kB — **not a
result**). A significant sample was run instead: **44 multi-turn rows + 24
single-turn HARD** (`official-r418sense-mt-hard.ckpt.jsonl`,
`official-r418sense-st-easy.ckpt.jsonl`), read by `live_sample_read.py` into
`live_sample_mt.json`. Two defects came out of it, both fixed here and pinned.

**1. 17 of 44 multi-turn rows returned an EMPTY answer — not a wrong one.**
`RegenoldChatMessage.content` is capped at 4 000 chars by Pydantic, and validation
runs BEFORE the route, so our own 4 011-char answer on `rg_069` 422d the pushback
turn that replayed it. The failed turn left the rolling history frozen and the next
16 consecutive rows 422d too. The cap's purpose is INPUT a caller chooses to send; an
assistant echo is our own previous answer, replayed by the caller exactly as the
official hard-mode protocol does. Fix: `_trim_assistant_echoes` trims the ECHO to the
cap (keeping the head, where the verdict and lead citations are), records
`assistant_echo_trimmed=`, and keeps the hard 422 for over-cap `user`/`system`
content (`tests/test_r418_assistant_echo_trim.py`). Consequence: the answer axes of
that sample are void — 17 rows scored zero on every metric by construction.

**2. The serving leg was not on the wire.** R417 records `stage2_served_by` in
`graph_stats`, but the deployed response exposes only `answer` / `references` /
`reasoning`, so a live audit had to INFER the leg from the model name — the
inference that mis-read `rg_010` as three independent fallback samples (R416 §6.5a).
The route now emits `stage2_served_by=` on both paths (cache hit and fresh ask), and
`run_official_batch._provenance` records it per row
(`tests/test_r418_leg_on_the_wire.py`).

The deterministic half of that sample that IS readable: `gold_head_dropped_total`
**0**, `refusal_rate` **0.0**, `sub_second_graded` 20/44, `turn1_chars_p50` 617,
`leg_mix` `{unrecorded: 25, wrapper: 19}` (unrecorded because the wire note did not
exist yet when it ran). Re-runnable with:

```
.venv/Scripts/python.exe -m evals.regenold.run_hard_sample_r297 --frac 0.4 ...
.venv/Scripts/python.exe -m docs.measurements.r418.live_sample_read \
    --mt-ckpt evals/bench/results/official-r418sense-mt-hard.ckpt.jsonl \
    --st-ckpt evals/bench/results/official-r418sense-st-easy.ckpt.jsonl
```

The full 110-row hard batch is re-launched on this tree after the merge, with the
echo-trim and leg fixes in, so the batch's multi-turn half is measurable for the
first time. Recorded from the earlier log, not acted on (pre-existing, unchanged by
this round): a Cohere `/v1/embed` **429** at startup makes the index fall back to the
SVD path; it affects the vector arm only, but any read of this run's latency or
dense-recall numbers should exclude it.

## 5. What is deliberately NOT in this round

* `R1` — the R355 cache-key AST gate does not scan `app/routes`; widening it
  means auditing every route literal for "changes the answer" vs "operational
  only", and a noisy gate gets waived. The instance is fixed (#10).
* `R2` — the `_root_q` picker still prefers a *self-contained* prior turn over
  the immediately-preceding one. Half-fixed (#12). On the official hard split
  both rules pick the same turn, so **no surface in this repo can rank them**;
  it needs a partner-shaped sample, not a coin flip.
* `R3` — possible residual operator/subject ambiguity in the widened workplace
  pattern (`confidence 60`, no named failing row).
* `R4` — the full-graph stack (`REGENOLD_GRAPH_2HOP`, PPR, PathRAG, dense recall)
  stays OFF. Each was flipped on a paired gate and each regressed or did nothing;
  those falsifications are in `docs/reviews/r411-architecture-audit.md`.

## 6. R419 — the R416 KG point-text lever's `Ans Strict` delta, re-scored for
credit reproducibility

**Question.** R416 flipped `REGENOLD_KG_POINT_TEXT` default-ON on an easy-board read of
`ans_correctness_strict` **88.0 -> 96.0 (+8.0 pp)** on 25 paired rows, naming `rg_010`
(4/5 -> 5/5) and `rg_045` (3/4 -> 4/4) as the mechanism. Every verdict behind that read is
on disk, so the re-score needs no calls: exclude any row whose credited criterion is not
reproducible across repeated samples, and see whether the sign survives.

**Answer: the sign does not survive — it is exactly +0.00 pp on the surviving rows.** The
entire answer-correctness movement of this lever is **two criteria out of 87**, and each
fails a different reproducibility test. The conciseness "cost" the flip was priced against
is not significant either, so on this corpus every axis of the lever is within single-draw
noise.

### 6.1 The delta is two criteria, not two rows' worth of behaviour

Diffing the two arms' per-criterion verdicts across all 25 rows:

| | rows | criteria | criteria passed |
| :--- | ---: | ---: | ---: |
| OFF | 25 | 87 | 84 (`ans_loose` 96.55) |
| ON | 25 | 87 | **86** (`ans_loose` 98.85) |
| changed | 2 | 87 | `rg_010` #2, `rg_045` #3 |

Two criteria changed. That is the whole of `ans_loose` (+2.30 pp = 2/87) **and** the whole
of `ans_strict` (+8.0 pp = the same two rows flipping all-satisfied). No other row, and no
other criterion on those rows, moved in either direction.

### 6.2 Rule J — the instrument's own repetitions

The judge repeats every judgement three times; `_corr_runs` holds each repetition, so a
row whose strict verdict is not unanimous is a row whose score depends on which draw you
get. Only one row in the whole board has any per-criterion instability, and it is a mover:

| row | arm | per-rep strict | credited criterion's reps |
| :--- | :--- | :--- | :--- |
| `rg_045` | OFF | `F F F` | criterion 3 — none |
| `rg_045` | ON | **`F T T`** | criterion 3 — **2 of 3** |
| `rg_010` | OFF | `F F F` | criterion 2 — none |
| `rg_010` | ON | `T T T` | criterion 2 — 3 of 3 |

The arm's own published min-max bound on `Ans Strict` (92.0-96.0, i.e. +4.0..+8.0 on the
delta) is this single row. Every other row is unanimous in both arms, so rule J excludes
exactly one row.

### 6.3 Rule G — 10 fresh generations per arm, measured rather than inferred

`rg_010`'s credit is judge-stable on that pair, so it needs the generation-level test.
`kgpt_credit_resample.py` re-asks each row's question **10 times per arm** (identical text,
`_ENGINE_CACHE.clear()` between samples so every answer is a live generation; the engine
cache otherwise replays one generation in 0.1-0.2 s, which is exactly how R416 §6.5a's
"three observations" turned out to be one) and judges each answer with the arms' own
instrument. All 40 samples were served by the **primary wrapper** leg (`claude-opus-5`),
zero fallbacks, so none is structurally incomparable.

| row | criterion | OFF credited | ON credited | OFF atomic draws | ON atomic draws | Fisher p |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| `rg_010` | Art. 14 *aim* limb | **6/10** | **5/10** | 18/30 | 15/30 | **1.000** |
| `rg_045` | *without undue delay* limb | 2/10 | 5/10 | 11/30 | 17/30 | **0.350** |

`rg_010`: the clause the lever was credited with is produced at the **same rate with the
lever off**. The published 4/5 vs 5/5 was two draws from one distribution — which is the
second independent confirmation of §6.5a, now at a sample size rather than a spot check.

`rg_045`: the ON arm leans higher, but the baseline credits the limb 20 % of the time at
sample level (37 % of atomic draws), so a single 1-vs-1 pair becomes a gain by chance often
enough to explain the published `F T T` — and it does not clear any bar (p=0.35).

### 6.4 The re-score

`kg_lever_ans_strict_repro.py` applies each rule separately and jointly, computing every
number with `score_rows` — the published instrument, on a subset, never a second
implementation of the axis.

| variant | n | OFF strict | ON strict | delta |
| :--- | ---: | ---: | ---: | ---: |
| published (all rows) | 25 | 88.00 | 96.00 | **+8.00** |
| exclude judge-rep unstable (`rg_045`) | 24 | 91.67 | 95.83 | +4.17 |
| exclude generation-unstable (`rg_010`, `rg_045`) | 23 | 95.65 | 95.65 | **+0.00** |
| exclude both | 23 | 95.65 | 95.65 | **+0.00** |

`ans_loose` follows the identical shape (98.72 vs 98.72, +0.00). On the surviving 23 rows
the arms are **row-for-row identical**: the only remaining failure is `rg_035`, in both.

### 6.5 The corrected board, and the cost that is not a cost either

Substituting the corrected correctness axes into the published paired reading (all other
axes unchanged, since the re-score changes no latency and never touches the reference
axes):

| axis | OFF | ON | delta |
| :--- | ---: | ---: | ---: |
| ans_correctness_loose | 98.72 | 98.72 | +0.00 |
| ans_correctness_strict | 95.65 | 95.65 | +0.00 |
| ans_conciseness | 47.80 | 44.50 | -3.30 |
| ref_correctness_loose / strict | 100.00 / 70.80 | 100.00 / 70.80 | 0.00 / 0.00 |
| ref_conciseness | 51.60 | 52.20 | +0.60 |
| regulatory_tone | 60.00 | 60.00 | 0.00 |
| resp_speed | 70.40 | 71.30 | +0.90 |
| **overall** | 71.67 | 71.25 | **-0.42** (was **+0.6**) |

The `-0.42` rests entirely on `ans_conciseness`, which is answer length — and that is not
a measured cost either. On the same 25 paired rows the ON arm is longer on only **14 of 25**
(mean 1,426 -> 1,543 chars; sign-test **p=0.69**, Wilcoxon **p=0.23**); a few large rows
move the mean, and the resample shows one row returning **450-1,492 chars at fixed input and
arm**. On the two rows the lever is credited with, the sampled direction is not even
consistent — `rg_010` is SHORTER with the lever on (1,027 vs 1,213 chars, `ans_conc` 72.5 vs
65.8) and `rg_045` is a wash (1,403 vs 1,464). So the honest reading of the corrected board is not "-0.42" either: it is **0 on every
axis of this lever, within single-draw noise**, with the two directions (length, and the
`ref_conc` +0.6 that favoured ON) both inside their spread.

### 6.6 What this does and does not settle

* **It removes the measured justification for the R416 default flip.** The flip was priced
  on +8.0 `ans_strict`; that number is a single-draw pair. No decision should now rest on it.
* **It does not by itself argue for reverting the default.** This audit is evidence-neutral
  about the direction: it removes a scored gain, and equally removes the scored cost. The
  remaining case for ON is the deterministic grounding evidence (the legacy query returns
  **0** units for bare points such as those carrying Art. 5(1)(a)-(h); the block changes on
  23/26 rows, units 26 -> 384) — a plausibility argument about omitted limbs, not a measured
  axis. The case for OFF is the same absence. That is a judgement for the operator, and it
  is now stated in the flag's own docstring so the next reader does not requote the +8.0.
* **Unaffected:** the hard-split read and its modality scope (measured independently, and
  the multi-turn path is byte-identical to OFF), the reference axes, and the reach evidence.
* **A note on the instrument's own bound:** the min-max band alone still reads +4.0..+8.0.
  The reproducibility test — not the band — is what moves this to zero, which is the point:
  a band computed from the same three draws cannot detect that the *pair itself* is one draw.

### 6.7 Artifacts

| file | what |
| :--- | :--- |
| `kg_lever_ans_strict_repro.py` / `kg-lever-ans-strict-repro.json` | rules J + G, the four variants, the corrected board, the conciseness test |
| `kgpt_credit_resample.py` / `kgpt-credit-resample.jsonl` / `kgpt-credit-resample.json` | 40 live generations (10 per arm per row) + 120 judge calls, per-criterion credit and per-sample lengths |
| `tests/test_r419_ans_strict_repro.py` | pins the rule functions and both artifacts (10 tests) |
| `../r416/CHECKPOINT.md` §3 | the correction carried back to where the +8.0 was published |
| `app/engines/kg_context.py` (`_kg_point_text_enabled`) | the docstring that requoted it |
