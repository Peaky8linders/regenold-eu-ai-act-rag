# R460 — the conciseness program: from 81/59 to the reference answer

Both remaining gaps are *conciseness* gaps. This closes the round's negative on
the Ref Conciseness axis (`REF-CONCISENESS-LEVERAGE.md` priced it and screened
every key-blind transform) by attacking the two places the count is actually
decided — the generator's compliance, and the validity of how we measure it.

Scripts: `conciseness_program_analysis.py` (offline targets),
`apply_conciseness_calibration.py` (generator lever),
`apply_length_control.py` (instrument validity). Tests:
`tests/test_r460_conciseness_calibration.py` (8), `tests/test_r460_length_control.py` (7).

## 1. The metric structure says what to optimise

The official rubric, as reconstructed and validated in
`evals/official/rubric.py`:

    ans_conc = min(1, len(reference_answer) / len(candidate_answer))
    ref_conc = min(1, |expected_refs| / |provided_refs|)
    ans_correctness_* = per-criterion recall      (omission costs; excess does not)
    ref_correctness_* = per-question recall       (omission costs; excess does not)

All four are **one-sided**. Being shorter than the reference, or citing fewer
provisions than the key, is *free*; only omission is punished. So the
scoring-dominant answer is the **minimum answer that still covers every criterion**
— and the gold reference answer is a per-row existence proof that such an answer
fits. Note what follows: the frontier's own weakness on these two axes
(ans_conc 71.8 / ref_conc 58.5 on hard) is not a knowledge gap, it is verbosity.

## 2. The measured prizes

From `conciseness_program_analysis.py` on the two live Cohere boards (n=37 each;
references and keys as scored):

| quantity | hard | easy |
| :-- | --: | --: |
| our answer / reference length | 1.25x | 1.27x |
| rows over the reference length | 30/37 | 27/37 |
| ans_conciseness shipped → if every row hit the reference length | 81.54 → **100** | 81.30 → **100** |
| refs supplied per row vs expected (1.257) | 2.51 vs 1.257 | 2.43 vs 1.257 |
| ref_conciseness shipped → ceiling (rc=100 at today's recalls) | 59.14 → **100** | 61.10 → **100** |

Overall is the geometric mean of the eight axes, so the prize is large:
ans_conc → 100 alone is **+1.9 pp** (hard), and ref_conc → 100 is **+5.8 pp**
(`REF-CONCISENESS-LEVERAGE.md` §4-5). Both at once puts hard at ~92 against the
frontier's 81.7 — "way better than frontier 2026" is arithmetically reachable.

The engine's own target is **already calibrated**: `answer_need.target_chars`
lands a median of −36 chars from the reference answer (mean −4). So this is a
**compliance** problem, not an estimation problem: the contract states the right
number and the model writes 1.25x it. The R448 note already recorded the same
thing independently (Opus 5.5 wrote 1,040-2,180 chars against 533-985-char
references while the target was on screen).

And the key's citation count is **not shape-dependent**, so the count target is a
single number: |expected| is 1.25 (description), 1.32 (boolean), 1.08 (list),
1.33 (definition), 1.50 (role); `|expected| <= 2` covers **97%** of the 110 gold
rows and `<= 3` covers 100%. Nothing about the question shape predicts which two,
so *selection* has to stay with the model — which is why the lever below is a
prompt-side budget and not a post-hoc cap (`REF-CONCISENESS-LEVERAGE.md` §4
measured that every blind cap pays for its conciseness on Ref Strict).

## 3. What the research says actually converts

Length control (generation side):

* **Numbers, not adjectives.** "Be concise"/"be brief" are soft suggestions;
  explicit numeric ceilings and counted constraints are what models obey —
  measured reductions of 40-74% with no quality loss on ordinary tasks
  ([Output Length Control, NeuralTrust](https://neuraltrust.ai/blog/output-length-control)).
* **Externalise the count.** Transformers have no reliable internal counter, so
  the model must be made to count on the page: countdown/self-count prompting
  lifted strict length compliance from under 30% to above 95% on MT-Bench-LI with
  judged quality preserved, and beat the popular draft-then-revise baseline
  ([Prompt-Based One-Shot Exact Length-Controlled Generation, arXiv 2508.13805](https://arxiv.org/html/2508.13805v1)).
* **Show, don't tell.** Few-shot examples at the target length are the reliable
  way to calibrate output length, and instruction + examples together beat either
  alone.
* **Structure and stops**: JSON/prose fields and stop sequences cut trailing
  verbosity; `max_tokens` is the safety net, not the control. Caveat from the same
  source: on *regulated* content a word cap can drop required content — which is
  exactly the recall risk the criteria axes punish here.
* **Citation discipline** comes from the attributed-generation literature: ALCE
  defines citation precision/recall, and its consistent finding is systematic
  **over-citation**, with the fixes being per-claim citation (cite the sentence
  that needs support, one passage per claim) and a hard budget
  ([ALCE, arXiv 2305.14627](https://ar5iv.labs.arxiv.org/html/2305.14627)).

Judge validity (measurement side):

* **Verbosity bias in LLM judges is robust and first on every bias list**: longer
  answers collect more credit unless length is controlled for; the standard
  mitigation is a length-controlled score (regress the verdict on the length
  differential — Length-Controlled AlpacaEval,
  [arXiv 2404.04475](https://arxiv.org/html/2404.04475v2)) and explicit rubric
  language about conciseness
  ([LangChain](https://www.langchain.com/resources/llm-as-a-judge)).
* Our instrument has a **structural advantage** here: the two conciseness axes are
  deterministic ratios, not judge outputs, and the criteria judge is shown the
  *key's* provisions plus the answer text only — never our own ref list. So ref
  pruning cannot move the answer axes at all (`REF-CONCISENESS-LEVERAGE.md` §2).

## 4. What was implemented (all default OFF)

**Generator: `REGENOLD_CONCISE_CALIBRATION`** —
`answer_need.calibration_block()` appends a short COUNT-BEFORE-YOU-ANSWER block as
the **last** instruction in the Stage-2 user message:

* the sentence ceiling, taken from the same `concise_limits()` call as the
  shipped concise contract (never a second, contradictory number) plus the
  instruction to *count the draft and delete the least deciding sentence*;
* a **numeric citation budget** — 2 provisions for a direct ask, 3 for a
  fact-pattern ask (the counts that cost no recall at 97%/100% of the gold);
* a structural skeleton at the target size (sentences, words, citation line),
  which is the "show" half without smuggling statutory content into an exemplar;
* it keeps the existing rule that a provision the facts engage and the answer
  rules out still counts, so it cannot contradict `concise_block`.

Registered in `_engine_cache_key`. Off → the user message is byte-identical
(asserted).

**Generator: `REGENOLD_CONCISE_COUNT_ONLY` (R461)** — the citation-budget half of
the block above, rendered alone by `answer_need.count_only_block()`: three lines,
331 chars, the numeric budget, the rule that a provision the facts engage and the
answer rules out still counts, and the citation-order line. It deliberately calls
neither `answer_need` nor `concise_limits`, so the length battery cannot leak back
in and a broken length estimate cannot take the budget down with it. Allow-list,
default OFF, registered in `_engine_cache_key`, and byte-identically additive to
the shipped contract (asserted). Section 5.1 is its gate.

**Instrument: `--length-control`** —
`rubric.truncate_to_chars()` + `score_arm._length_controlled_rows()` re-judge
every answer **cut to its own reference answer's length** (at a sentence
boundary, never expanding a short answer) and report the answer axes next to the
raw ones, in the console and in the payload (`length_controlled`, marked
`cached: false`). This is the reference-based analogue of length-controlled
debiasing: a correctness edge that survives the cut is knowledge; one that
disappears was verbosity. A dead judge transport in that pass is loud (R393
doctrine), and an end-to-end test drives the whole path with a faked transport.

## 5. The gates that were run - and the verdict

Both levers shipped private-by-default, so the promotion question was a paired
board. The plan as written was:

> ~~`run_official_batch --mode hard --stride 3 --repeats 3 --branch-env
> REGENOLD_CONCISE_CALIBRATION=1` against the recorded `r460-cohere-hard-s3`
> baseline; score both with `--length-control`; acceptance ref_conciseness >= 85
> and ans_conciseness >= 92 with no correctness loss.~~

It was executed in a stronger shape - both arms drawn FRESH under one protocol and
one judge cache, rather than one arm against a day-old recorded baseline - and it
was executed twice, same protocol (`--mode hard --stride 3`, n=37, same judge
identity, `--length-control`), on two transports:

1. **Bedrock leg** (`eu.anthropic.claude-opus-4-6-v1`, inverted transport contract,
   both arms alike) - `GATE-CONCISENESS-BEDROCK.md`: ref_conc 59.14 -> 63.90
   (**+4.76 [+0.29, +10.43]**, the only axis whose CI excluded zero), ans_loose
   93.69 -> 95.95, ans_conc 82.99 -> 84.96, overall **+0.95**, gold heads 2 -> 2.
2. **The SHIPPED transport** (Claude Max wrapper, `claude-opus-5-5`) -
   `WRAPPER-CONFIRM.md`: ref_conc 58.43 -> 63.95 (**+5.52 [+0.71, +11.90]** - the
   count mechanism reproduces almost exactly), but **ans_conciseness 82.32 -> 77.84
   (-4.49 [-8.77, -0.68])**: on this model the block makes answers LONGER
   (+65 chars, 17/26 rows, CI [+10, +119]) and the board drops
   **86.90 -> 86.09**.

**Verdict: `REGENOLD_CONCISE_CALIBRATION` stays DEFAULT OFF.** The lever moved one
of the two conciseness axes the wrong way on the model that ships, so the
acceptance targets above are not close and are not claimed.
`promote_conciseness_calibration.py` is on disk, deliberately unapplied.

The wrapper board's correctness / tone / speed deltas are NOT lever effects, and
attributing them to the lever would be a measurement error: they are carried by
exactly two rows whose transport degraded differently (`rg_037` shipped a
`prior_turn` answer in B, `rg_049` a `deterministic` draft in A; the other 35 rows
have identical judged criteria vectors) plus B's retry-heavy draw (17 vs 5
degenerate-completion events, 8 vs 2 Bedrock fallback attempts). Section 3 of
`WRAPPER-CONFIRM.md` does that attribution row by row.

**The surviving sub-lever.** The block's two halves behaved differently: the
counted citation budget reproduces on both transports (about +5 pp ref_conc with
no other axis touched between legs), while the length battery (sentence count,
word ceiling, shape skeleton) helped on `opus-4-6` and hurt on `opus-5-5`. The
next gate is therefore the **count-only variant** - the same numeric budget with
the length clauses removed - before any default moves.

Replicates 2-3 of the wrapper gate were not spent: the tunnel's quota is the
scarce resource this round, and the deciding delta is systematic at the row level
rather than marginal. The launcher resumes them in one command
(`run_gate_wrapper.sh 3`).


### 5.1 The count-only variant, gated alone (R461) — every target met but the hard rule

The sub-lever section 5 identified was built and gated on its own transport run.
`REGENOLD_CONCISE_COUNT_ONLY` (`answer_need.count_only_block`, 331 chars) emits the
budget, the rule-out rule and the citation-order line and **nothing else**: no
sentence ceiling, no word count, no shape skeleton, and no call into
`answer_need`/`concise_limits`. `COUNT-ONLY-CONFIRM.md` is the round record.

`--mode hard --stride 3`, `claude-opus-5-5`, same judge identity, both arms fresh,
37/37 rows and 0 errors each, and arm A drawn fresh so the OFF arm is re-drawn on
**byte-identical prompts** (`verify_byte_identity.py` proves the bytes; the earlier
OFF arm loads as a second module from `git show` and renders identically on all 64
board questions).

| axis | OFF | COUNT-ONLY | Δ | CI |
| :-- | --: | --: | --: | :-- |
| ans_correctness_loose / _strict | 94.82 / 91.89 | 94.82 / 91.89 | **+0.00 / +0.00** | [-8.11, +8.11] |
| ans_conciseness | 81.95 | 82.05 | +0.10 | [-2.71, +3.18] |
| ref_conciseness | 56.62 | 64.31 | **+7.69** | **[+1.41, +15.05]** |
| regulatory_tone | 97.30 | 97.30 | +0.00 | flat |
| resp_speed | 86.81 | 86.19 | -0.62 | [-2.52, +1.45] |
| answers (chars) | 813.5 | 820.2 | +6.6 | [-32.4, +41.9] |
| **overall** (per-row) | 73.98 | 77.78 | **+3.80** | **[+0.58, +9.01]** |

The count mechanism reproduces a third time (+7.69 against +5.52 here and +4.76 on
Bedrock), and **the full block's two costs disappear**: answers no longer grow
(+6.6 vs +64.0, whose CI excluded zero) and speed no longer moves. On the same
method, the noise-floor pair (OFF re-drawn, byte-identical prompts) reads -0.56
[-6.99, +5.79], so **+3.80 is the first overall delta in this program whose paired
CI excludes zero.**

**Verdict: NOT PROMOTED.** Hard rule #8 is tripped on one row, `rg_037`, whose
provenance is `served_by=deterministic` / `polish=False` — both Stage-2 legs failed
and the deterministic Stage-1 draft shipped, so the block never ran on it (its 7
refs and 1,474 chars contradict the budget of 2 it was given). On the 36 rows where
the lever ran, the count-only arm drops ZERO gold heads against its OFF arm's two.

**And the rule itself was measured.** That same noise-floor pair drops two gold
heads on byte-identical prompts — `rg_061`, and `rg_088` at 0/3 criteria on an
UNDEGRADED row — and moves `resp_speed` -3.35 [-4.59, -2.07]. So rule #8 as
written is not draw-stable at n=37, a single-draw gate can trip it with no lever
present, and the R460 gate's speed reading was a draw artifact rather than a lever
effect. The fix the evidence supports is to evaluate the veto only on rows where
the lever ran, or to require the drop to persist across an OFF re-draw — a change
to the instrument, to be made on its own merits and not as a retro-fit exemption
for this lever.

## 6. Caveats

* The plans/deferrals above are measured on n=37 stride-3 boards; the analysis
  itself is exact (deterministic ratios over the answered rows).
* A content-bearing few-shot exemplar (the 8-shot form the length literature
  measures) is deliberately *not* used: an exemplar's provisions would prime
  citations. If the skeleton under-delivers, the next rung is an exemplar with
  non-Act placeholders, gated on a drift-guard check.
* R367's lesson stands: correctness and conciseness have been traded before in
  this engine. That is why the calibration block only restates counts derived from
  the existing estimate and never removes a rule from `concise_block`.
* Nothing in this program changes a default. Two live boards HAVE now been run
  with the lever (the Bedrock gate and the wrapper confirmation, section 5); the
  numbers in section 2 still describe the *shipped* board, because the lever was
  not promoted.
* A one-draw-per-row board (n=37) can only decide DIRECTION, and both gates were
  read that way. The wrapper verdict does not rest on a marginal delta: the
  length reversal is +65 chars on 17 of 26 same-leg rows with a CI excluding
  zero, while the delta the round was aiming at (ans_conciseness) moved against
  the intent.
