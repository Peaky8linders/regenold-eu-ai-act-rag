# R461 — the count-only conciseness gate, on the SHIPPED transport

**Verdict: NOT PROMOTED on this draw — every measured acceptance target is met
except hard rule #8, which one TRANSPORT-DEGRADED row trips, and this gate
demonstrates that rule #8's per-row veto is not itself draw-stable at n=37.**
Read the refusal as a rule application, not as a measured regression: on the
substance this is the strongest arm the conciseness program has produced, and the
§7 decision is stated for the reader rather than buried.

The R460 wrapper gate refused the whole calibration block, but recorded that its
two halves behaved differently: the counted CITATION BUDGET reproduced on two
transports (+5.52 pp ref_conciseness here, +4.76 pp on Bedrock — the only axis
whose CI excluded zero in either gate), while the LENGTH BATTERY helped on
`opus-4-6` and made answers 64 chars LONGER on `opus-5-5` (-4.49 pp
ans_conciseness). This round splits them: the same numeric budget, no length
clause of any kind.

Lever: `REGENOLD_CONCISE_COUNT_ONLY` (`answer_need.count_only_block`), an
allow-list default OFF, keyed in `_engine_cache_key`. Launcher
`run_gate_count_only.sh`, scorer `score_gate_count_only.sh`, attribution
`count_only_attribution.py`, byte-identity check `verify_byte_identity.py`.

## 1. What the arm actually reads

The block is three lines, 331 chars, against the full block's 705:

    CITATION COUNT (count the provisions before you answer):
    * COUNT the provisions the draft NAMES: at most 2 for this question. Above
      that, keep the ones its answer rests on and drop the clauses about the
      rest. A provision the facts engage and the answer rules out still counts.
    * References: at most 2 provisions, in citation order.

The budget is per question: 2 for a direct ask, 3 for a fact-pattern ask (13/64
board questions). Two mechanical facts were checked rather than asserted, because
without them the gate would be comparing a re-wording instead of a removal
(`verify_byte_identity.py`, 64 real board questions):

* **the full block's rendering is byte-identical to the commit's** — 64/64, 705
  chars, by loading `git show ca71879:app/engines/answer_need.py` as a second
  module, so the R460 arm's baseline cannot have moved under it;
* **every line the count-only block emits is a line of the full block** (after
  normalising the indented skeleton clause to a bullet), and **no length clause
  appears at all** — `sentences`, `words`, `Match this shape`,
  `LENGTH AND CITATION`, `Delete the sentence`: 0 leaks.

`count_only_block` calls neither `answer_need` nor `concise_limits`, so the length
battery cannot leak back in and a broken length estimate cannot take the citation
budget down with it (asserted: it renders with both of those monkeypatched to
raise). 12 new tests, plus the 8 R460 and 7 length-control tests and 113
near-neighbour tests unchanged: 140 passed.

## 2. The gate, and the noise floor it is read against

Protocol is the R460 wrapper gate's, unchanged: `--mode hard --stride 3
--require-cohere-rerank --cohere-rerank-min-gap 7`, `claude-opus-5-5` over the
Claude Max tunnel, judge `bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3`
with `--length-control`. Arms `r461-countoff-s3` (flags absent) and
`r461-counton-s3` (`REGENOLD_CONCISE_COUNT_ONLY=1`), drawn SEQUENTIALLY under one
launcher, 37/37 rows and 0 errors each, 20.1 and 20.6 minutes. All four arms in
play carry the same `hard_preamble_digest cb85452c9c04` and every block-OFF prompt
is byte-identical (§1), which is what makes the pair below interpretable.

Arm A was drawn FRESH rather than reusing `r460-tunnel-off-s3`, and that decision
paid: **R461-OFF vs R460-OFF is a pure re-draw of byte-identical prompts, so
every delta on it is noise, measured instead of assumed.**

| axis | A = R461 COUNT-OFF | B = R461 COUNT-ONLY | Δ | 95% CI | read |
| :-- | --: | --: | --: | :-- | :-- |
| ans_correctness_loose | 94.82 | 94.82 | **+0.00** | [-8.11, +8.11] | flat |
| ans_correctness_strict | 91.89 | 91.89 | **+0.00** | [-8.11, +8.11] | flat |
| ans_conciseness | 81.95 | 82.05 | **+0.10** | [-2.71, +3.18] | NOT DOWN (noise band ±4.0) |
| ref_correctness_loose | 95.71 | 97.14 | +1.43 | [-7.14, +10.00] | not down |
| ref_correctness_strict | 83.33 | 84.76 | +1.43 | [+0.00, +4.29] | not down |
| **ref_conciseness** | 56.62 | **64.31** | **+7.69** | **[+1.41, +15.05]** | McNemar 10/2, p=0.0386, B> |
| regulatory_tone | 97.30 | 97.30 | +0.00 | [-8.11, +8.11] | flat |
| resp_speed | 86.81 | 86.19 | -0.62 | [-2.52, +1.45] | flat |
| answers (chars) | 813.5 | 820.2 | +6.6 | [-32.4, +41.9] | flat |
| refs / row | 2.84 | 2.51 | -0.33 | [-0.6, -0.1] | budget obeyed in part |
| **overall** (per-row geo-mean) | 73.98 | **77.78** | **+3.80** | **[+0.58, +9.01]** | 20/35 rows better |
| gold heads dropped | 2 | 1 | | | new in B: `rg_037` |

Board `overall` (macro geo-mean of the eight axis means): **85.08 → 86.47**, both
above the 2026 frontier's 81.7. `ans_loose` macro 94.82 in both arms.

The same three pairs on one method, which is the point of running them together:

| pair | Δ overall | 95% CI | rows better |
| :-- | --: | :-- | --: |
| **THE GATE** R461-COUNT vs R461-OFF | **+3.80** | **[+0.58, +9.01]** | 20/35 |
| NOISE R461-OFF vs R460-OFF (identical prompts) | -0.56 | [-6.99, +5.79] | 10/35 |
| R460-FULL vs R460-OFF (recomputed) | +2.47 | [-0.52, +7.47] | 13/35 |

**This is the first overall delta in the conciseness program whose paired CI
excludes zero** — and the noise-floor pair, on inputs that are byte-identical by
construction, is centred on zero. The recomputation of the R460 verdict reproduces
its published numbers exactly (ref_conc +5.52 [+0.71, +11.90], ans_conc -4.49
[-8.77, -0.68], +64.0 chars), so the three rows of that table are the same
instrument.

## 3. What the block does mechanically

The budget is a COUNT, and the count moved in the direction it names:

| refs in the answer | R461 COUNT-OFF | R461 COUNT-ONLY | R460 FULL (R460-OFF base) |
| :-- | --: | --: | --: |
| ≤ 2 (the budget) | 22/37 | **27/37** | 24/37 (21/37) |
| ≤ 3 | 26/37 | **30/37** | 30/37 (26/37) |
| ≥ 4 | 11/37 | **7/37** | 7/37 (11/37) |

Ref Conciseness is `min(1, |expected| / |provided|)` and the key is ~1.26 refs/row,
so this is the whole axis: refs/row 2.84 → 2.51 is +7.69 pp. The count-only block
reaches the SAME refs/row (2.51) and the same `≤2` compliance as the full block —
**without the length battery, and therefore without the full block's costs.**

That the two costs are gone is the result, not a footnote:

| cost the full block paid on this transport | full block | count-only | noise floor |
| :-- | :-- | :-- | :-- |
| ans_conciseness | **-4.49** [-8.77, -0.68] | **+0.10** [-2.71, +3.18] | -0.37 [-4.00, +2.80] |
| answers (chars) | **+64.0** [+16.9, +114.6] | **+6.6** [-32.4, +41.9] | +10.2 [-30.8, +53.1] |
| resp_speed | -1.96 (p<0.0001) | -0.62 [-2.52, +1.45] | **-3.35** [-4.59, -2.07] |

The third column is why the speed row matters: **at byte-identical prompts, a
re-draw of the OFF arm moves `resp_speed` by -3.35 pp with a CI that excludes
zero.** The R460 gate's -1.96 "p<0.0001" was therefore never a lever effect, and
this round retires that finding outright rather than attributing it.

`ref_correctness_strict` moved +1.43 [+0.00, +4.29] and `ref_correctness_loose`
+1.43: pruning citations did NOT cost reference recall, matching the R460 finding
and the leverage study's conclusion that only a blind post-hoc cap does.

## 4. The one failing criterion, decoded

Hard rule #8 ("any lever that drops a gold HEAD on any row is vetoed regardless of
what the mean deltas say") is tripped, at HEAD grain, on exactly one row:

| | `rg_037` (key: `Annex VIII.a`) |
| :-- | :-- |
| R461 COUNT-OFF | refs `Article 71, 49.1, Annex III, Annex VIII, 49.5`; 6/6 criteria; `served_by=primary`, `polish=True` |
| R461 COUNT-ONLY | refs `Article 6.2, 71.4, 16, 49.4, 35, 112.12, 109`; **0/6 criteria**; **`served_by=deterministic`, `polish=False`** |

The COUNT row never ran the block. Its provenance says the wrapper primary and the
Bedrock leg both failed, tail repair failed, and the harness shipped the
deterministic Stage-1 draft — which is why the row contradicts the very block it
was given (7 refs and 1,474 chars against a stated budget of 2). It is the same
row and the same failure class the R460 FULL arm tripped on (`prior_turn` there).

And it is a lottery over rows, not a property of the lever — the incidence of a
degraded Stage-2 leg, across every wrapper arm on record:

| arm | `served_by=primary` | degraded | which row |
| :-- | --: | :-- | :-- |
| R460-OFF | 27 | 1 `deterministic` | `rg_049` |
| R460-FULL | 27 | 1 `prior_turn` | `rg_037` |
| R461-OFF | 28 | **0** | — |
| R461-COUNT | 27 | 1 `deterministic` | `rg_037` |

So the block is present in an arm that was never given the block, the rate is ~0-1
per 37 either way, and on the 36 rows where the lever DID run the count-only arm
drops **ZERO** gold heads against its OFF arm's two:

| subset | ref_conciseness | ans axes | answers | gold heads |
| :-- | :-- | :-- | :-- | :-- |
| all 37 rows | +7.69 [+1.41, +15.05] | 0.00 | +6.6 | A=2 B=1 (rg_037, degraded row) |
| 36 rows, same leg label | +8.09 [+1.91, +15.49] | +2.78 | +0.3 | **A=2 B=0** |
| 27 rows, PRIMARY in both | +10.19 [+2.41, +19.20] | +3.70 | +0.4 | **A=2 B=0** |

## 5. The instrument finding: rule #8 is not draw-stable at n=37

This is the round's most consequential result, because it applies to every future
lever and not just this one. The noise-floor pair is two draws of the SAME arm on
**byte-identical prompts**. It drops two gold heads that the first draw did not:

* `rg_061` (key `Article 88.1, 75.1`): the re-draw ships `Article 88.1, 94` —
  the second key head is simply absent (`Article 75.3` was cited by both R460 arms
  and by the count-only arm);
* `rg_088` (key `Article 26.1, 26.6`): the re-draw misses the row entirely,
  **0/3 criteria** against 3/3 in the earlier draw, `served_by=primary`,
  `polish=True` — a clean, undegraded generation miss.

`ref_correctness_loose` therefore reads 100.00 → 95.71 and `regulatory_tone`
100.00 → 97.30 between two draws of unchanged inputs. A single-draw gate can
trip the unconditional veto with no lever present, so at n=37 the rule as written
is not decidable for a prompt-level change. The mechanical fix the evidence
supports — proposed, not applied — is to evaluate the veto on rows where the lever
actually ran (`stage2_polish` true and `stage2_served_by` the primary leg), which
is the same-leg contract this round already uses for attribution, or to require
the drop to persist across an OFF re-draw.

This is why §7 is a decision for the reader and not a silent promotion: waiving an
unconditional rule on a one-row transport lottery is exactly the "argument from
construction" AGENTS.md invariant #5 forbids in place of the
`gold_dropped_head` check, and the fix belongs in the rule, not in this lever.

## 6. Acceptance, against the targets CONCISENESS-PROGRAM.md §5 wrote in advance

| target | measured | met |
| :-- | :-- | :-- |
| ref_conciseness CI excludes zero | +7.69 **[+1.41, +15.05]**, McNemar 10/2 p=0.0386 | **yes** |
| ans_conciseness not down | +0.10 [-2.71, +3.18]; full block was -4.49 | **yes** |
| answer axes flat | ans_loose +0.00, ans_strict +0.00, LC ans_strict +0.00 | **yes** |
| no gold heads dropped | 0 new drops on the 36 rows the lever ran; 1 on a row the lever never ran | **no** |
| overall ≥ 0 | +3.80 [+0.58, +9.01], 20/35 rows | **yes** |

Four of five, and the fifth is a rule application rather than a measurement. For
comparison on the same instrument, the full block met two of five.

Length control (the R460 instrument) does not separate the arms, as it should not:
answers are the same length (+6.6 chars). A = 62.96 / 56.76, B = 60.00 / 56.76
(LC ans_loose / ans_strict, 29 and 27 answers cut) — the -2.96 is one row.

## 7. The decision

**Not promoted in this commit.** `calibration_enabled()` and
`count_only_enabled()` both keep their allow-lists; nothing default-ON, nothing
promoted. `promote_conciseness_calibration.py` stays unapplied, and a
`promote_count_only.py` is deliberately NOT written: the honest next step is not a
promotion script, it is one of these two, in this order.

1. **Fix the veto's operating definition, then re-read this gate from the
   checkpoints.** The count-only arm's own numbers say the lever cost no gold head
   anywhere it ran; the failing row is a degraded transport leg. Making rule #8
   conditional on `stage2_polish`/`stage2_served_by` is a change to the
   INSTRUMENT, it is justified by §5's measurement, and it must be made and
   reviewed on its own — not used as a retro-fit exemption for this lever.
2. **Spend one replicate when the tunnel allows.** `run_gate_count_only.sh 3`
   tops the gate up from the existing checkpoints one replicate at a time. If
   `rg_037` runs the lever in replicate 2, the veto lifts on the merits.

Only then does the count-only block become a promotion candidate, and the
evidence to promote it is already on disk.

## 8. Caveats

* n=37, one draw per row: this decides DIRECTION. Both the gate delta and the
  noise floor are read that way, and §5 is the reason a single draw cannot decide
  more.
* The noise floor is one pair of draws, so it prices the noise band loosely. It
  is enough to show that (a) `resp_speed` moves by more than the full block's
  speed claim at identical prompts and (b) two gold heads can move with no lever.
* The coverage-budget split (2 direct / 3 fact-pattern) is the R460 constant,
  unchanged: `|expected| ≤ 2` is 97 % of the gold rows.
* No content-bearing exemplar is used, for the R460 reason (an exemplar's
  provisions prime citations).
* Arm A of this gate is a second OFF draw, not the recorded one. The R460 OFF arm
  remains the arm of record for R460's own verdict; §2's third pair is the bridge.
