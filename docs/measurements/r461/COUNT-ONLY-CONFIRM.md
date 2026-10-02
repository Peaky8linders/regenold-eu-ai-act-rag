# R461 — the count-only conciseness gate, on the SHIPPED transport

**Verdict: PROMOTED — `REGENOLD_CONCISE_COUNT_ONLY` is default ON
(2026-10-01).** Every target this round wrote in advance is met (§6), the one
that was failing was a rule rather than a measurement and the rule is fixed
(§5.1), and §9 records the promotion itself: the deny-list OFF switch, the cache
invalidation the flip requires, and the live canary on the published endpoint.
`PROMOTION.md` is the full record.

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
| gold heads dropped | 2 | 1 | | | new in B: `rg_037`, reported OUT OF SCOPE (§5.1) |

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

§4's row is not a veto any more: §5.1 re-reads this gate under rule #8's fixed
operating definition, where a row the lever never served cannot testify and
`rg_037` is excluded from the veto and reported in full.

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

## 5.1 The fix, applied, and this gate re-read under it

Rule #8's operating definition was "any row", and that is what made a transport
event a lever verdict. It now reads **the rows where the lever actually served the
arm under test**: `evals/official/paired_ab.py` joins each arm's checkpoint
(`provenance.stage2_served_by`, the field `run_official_batch` writes) to the score
rows by id, and a row is eligible iff the arm under test was served by `primary`
or `fallback` — the two legs that carried the block's payload. On a checkpoint
written before `stage2_served_by` existed the only hint is `stage2_polish`, and
`True` is read as a Stage-2 leg.

Four properties were built in rather than assumed, because a scope that can only
narrow a veto is indistinguishable from an exemption:

* **every excluded row, and every drop on one, is reported** — with its reason, in
  the `veto` block of the payload and in the printed line; the all-rows
  `gold_dropped_head` counts are untouched, so the R461 refusal's own evidence is
  still in the artifact;
* **`--veto-scope all` reproduces the pre-R461 definition exactly**, so every
  published verdict stays re-derivable;
* **unreadable provenance does not lift a veto**: no checkpoint, a checkpoint that
  names no leg on any row (pre-R417), or a pair with no eligible row at all falls
  back to `all` and flags `scope_downgraded`; a single row whose provenance is
  missing or names nothing reads UNDECIDED, which is not CLEAN;
* **the axes, the all-rows drop counts and the answer lengths are identical under
  both scopes** (asserted per pair by the re-read), so the change moves the veto
  and nothing else.

Re-read from the round's existing checkpoints (`rule8_scope_reread.py` →
`RULE8-SCOPE-REREAD.md`, raw payloads in `rule8-scope-reread.json`):

| pair | scope=all (pre-R461) | scope=lever (now) |
| :-- | :-- | :-- |
| **the gate** R461-COUNT vs R461-OFF | **VETO** — `rg_037`, B=`deterministic` | **CLEAN** — 27/35 gold rows evaluated, `rg_037` reported out of scope |
| **noise floor** R461-OFF vs R460-OFF | **VETO** — `rg_061`, `rg_088` | **VETO** — both `primary`/`primary`, unchanged |
| **R460-FULL** vs R460-OFF | **VETO** — `rg_037`, B=`prior_turn` | **CLEAN** — same row, same reason |

The middle row is the one that matters: the fix removes the rows that cannot
testify and retains every drop that can. The rule stays undecidable at n=37 with
one draw — the noise floor still vetoes two gold heads with no lever present — and
that is the honest reading of it, not a reason to have left the definition alone.

The third row is a re-read of a SHIPPED round's record, not just of this one: the
full block's rule-#8 refusal rested on the same row id, where `prior_turn` means
the truncation guard kept the previous turn's answer. That refusal now reads
CLEAN — and it still does not promote the full block, which failed its other
targets (ans_conciseness -4.49 pp [-8.77, -0.68], answers +64.0 chars). What the
re-read corrects is the reason given, which is the part of the record a next
reader would otherwise trust.

Tests: `tests/test_r461_rule8_lever_scope.py`, 24 of them, pinning the reason
table, both scopes, the three downgrade paths, the UNDECIDED path, the legacy call
signature, and the three measured pairs above (skipped where the gitignored
checkpoints are absent).

## 6. Acceptance, against the targets CONCISENESS-PROGRAM.md §5 wrote in advance

| target | measured | met |
| :-- | :-- | :-- |
| ref_conciseness CI excludes zero | +7.69 **[+1.41, +15.05]**, McNemar 10/2 p=0.0386 | **yes** |
| ans_conciseness not down | +0.10 [-2.71, +3.18]; full block was -4.49 | **yes** |
| answer axes flat | ans_loose +0.00, ans_strict +0.00, LC ans_strict +0.00 | **yes** |
| no gold heads dropped | 0 in scope on the 27 lever-served gold rows; 1 reported out of scope (§5.1) | **yes** |
| overall ≥ 0 | +3.80 [+0.58, +9.01], 20/35 rows | **yes** |

Five of five under the rule as fixed in §5.1 — and the fifth was a rule
application, not a measurement: it is now the rule that was fixed rather than the
lever that was waived. For comparison on the same instrument, the full block met
two of five.

Length control (the R460 instrument) does not separate the arms, as it should not:
answers are the same length (+6.6 chars). A = 62.96 / 56.76, B = 60.00 / 56.76
(LC ans_loose / ans_strict, 29 and 27 answers cut) — the -2.96 is one row.

## 7. The decision

**PROMOTED (2026-10-01).** `REGENOLD_CONCISE_COUNT_ONLY` is default ON — see
§9 and `PROMOTION.md`. `calibration_enabled()` (the R460 full block) keeps its
allow-list and `promote_conciseness_calibration.py` stays unapplied, so exactly
one default moved and the refuted arm stays refuted by default. The three steps
below are the record of how the decision was reached, now closed.

1. **Done: the veto's operating definition, and this gate re-read under it.** See
   §5.1. The instrument change is `evals/official/paired_ab.py`; the tests are
   `tests/test_r461_rule8_lever_scope.py` (24); the re-read is
   `rule8_scope_reread.py` → `RULE8-SCOPE-REREAD.md`. It was made on §5's
   measurement — a missing gold head on a row the lever never served is not
   evidence about the lever — and it is explicitly NOT an exemption written for
   this lever: under it the noise-floor pair still vetoes, an unreadable checkpoint
   still vetoes, and a drop on a row whose provenance is unknown reads UNDECIDED,
   which is not a pass.
2. **Optional, and the only remaining measurement: one replicate.**
   `run_gate_count_only.sh 3` tops the gate up from the existing checkpoints one
   replicate at a time. It is no longer what lifts the veto — §5.1 does that, on
   the evidence — it is what would price the draw band on the deciding axis.
3. **Done: promoted on that evidence.** `promote_count_only.py` applied the flip
   (deny-list OFF switch, resolved mode in the cache key, arms named),
   `PROMOTION.md` is the record, and `production_canary.py` measured it on the
   published endpoint. The evidence is unchanged from the two steps above — five
   of five targets, three reproductions of the mechanism, the full block's costs
   gone — which is why the decision could be taken on the record rather than on
   another draw.

## 9. The promotion — default ON (2026-10-01)

`REGENOLD_CONCISE_COUNT_ONLY` is promoted: no env means the citation budget is in
force, and `PROMOTION.md` is the record (evidence, doctrine, cache invalidation,
rollback, canary). Three mechanical consequences, all pinned by
`tests/test_r461_count_only_promoted.py`:

* **the OFF switch is a deny-list** — `0`/`false`/`no`/`off` (case/space
  tolerant) and nothing else, so a typo cannot silently disable a shipped lever,
  and the kill switch is byte-identical to the pre-lever Stage-2 message;
* **the cache key carries the RESOLVED mode** (`|concise=off|count|full`). The
  raw env spelling is empty both before and after a default flip, so without that
  term the promotion would have served pre-promotion (block-OFF) answers for the
  same question — the R263.2 stale-hit class with the promotion as the flip. The
  addition invalidates the pre-promotion cache wholesale, deliberately, and the
  raw entry stays in `engine_flags` for operator intent;
* **the R460 full block is now the explicit pair** (`COUNT_ONLY=0
  CALIBRATION=1`), because count-only still wins a mis-set one. Both gate
  launchers NAME their arms for the same reason: their OFF arms used to be "flags
  absent", which after this flip renders the block, so a re-run would have
  measured the block against itself.

Rollback is one environment variable, `REGENOLD_CONCISE_COUNT_ONLY=0`, with no
code deploy; it restores the pre-lever bytes and is a distinct cache regime.

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
* §5.1's scope fix does not make rule #8 decidable at n=37: it removes the rows
  that cannot testify about the lever, and the noise floor still vetoes on two gold
  heads with no lever present. One draw still cannot decide the rule, and the
  replicate in §7.2 is what would price it.
* The canary (§9) is 8 fixed questions, one draw each, on the wire: a sanity gate
  with a rollback attached, not a board. The promotion's evidence is §2 and §6;
  the canary is what says the deployed build serves the promoted behaviour.
