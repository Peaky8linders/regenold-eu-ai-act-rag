# R438 — attack Ref. Correctness (Strict)

**Goal.** Take the one correctness axis where the 2026 frontier + live-web-search
baseline still leads, and close it with mechanisms that are count-neutral on the
graded wire. Bar: **hard-split Ref. Strict ≥ 80.0 %** on the official rubric with
the reconstructed key, i.e. **+6 pp over the frontier's 74.1** and +1.5 pp over its
easy-split 78.5, with Ref. Loose ≥ 96.0, Ref. Conciseness not below the R419
board by more than 1.0 pp, and `gold_dropped_head` unchanged.

Round label is R438 because R437 is already consumed in the record: a
R437-labelled harness attempt was started and stopped before scoring
(`docs/measurements/r436/CHECKPOINT.md`).

---

## 1. Where the axis actually stands

Last full board: **R419, 110/110, 2026-09-15** — the only current comparable. The
five reference-free axes are at parity or ahead; the two that are behind are the
verbosity pair, and the one pure-correctness axis behind is strict.

| axis | R419 hard | 2026 frontier + search (hard) | gap |
| :-- | ---: | ---: | ---: |
| Ans. Correctness Loose / Strict | 94.15 / 90.91 | 92.0 / 84.8 | **+2.1 / +6.1** |
| Ref. Correctness Loose | 96.08 | 94.6 | **+1.5** |
| **Ref. Correctness (Strict)** | **70.59** | **74.1** | **−3.5** |
| Ref. Conciseness | 44.79 | 58.5 | −13.7 |
| Ans. Conciseness | 44.19 | 71.8 | −27.6 |

Ref. Loose is already **level with the frontier**, so the axis is not a recall
problem: `rubric.reference_correctness_strict` is recall at full grain, and
`_is_descendant` credits a prediction only when it is **deeper or equal** — a bare
head never satisfies a limb-level key.

### 1.1 A fresh census: the gap is limb selection, not retrieval

Classification of every unmet expectation on the R419 capture against the
reconstructed key (`docs/measurements/r388/official_refkey_n110.jsonl`,
`unstable` rows dropped, the same key `score_arm` uses), instrument
`scratch/refstrict_taxonomy.mjs`:

```
ref-scored rows            102
expected refs (key)        129
strict hits                 89   (68.99 per-ref; the board's per-row 70.59)

unreached_head   5 refs   3.88 pp   4 rows   no citation of that head at all
sibling_limb    33 refs  25.58 pp  28 rows   right head, WRONG limb
head_only        2 refs   1.55 pp   2 rows   bare head shipped, key wants a limb
```

**33 of the 40 unmet expectations (25.6 of the ~31 pp gap) are a wrong limb under
a head we already cite.** Five are recall. Two are a bare head. So this axis is a
**limb-selection** problem, and the eight axes' most-mined seam — "cite fewer,
better references" — is the wrong frame for it entirely.

Gold grain census (the same 129 expected refs over the 102 ref-scored rows):

```
Article .N (one limb level)   87     Annex head                    11
Article .NL (limb + letter)    9     Article head                   9
Annex .NL                      6     Annex .N                       3
Annex .LN (section letter)     2     Article .NLL (roman)           1
Annex .L (section only)        1
```

**18 of the 129 scored expectations (14.0 %) sit at two dots or deeper.** Our wire
shipped 53 two-dot coordinates on the same board, so the form is expressible; the
deepener is simply never asked to go there (default `REGENOLD_REF_GRAIN_DEPTH=1`).

### 1.2 A coordinate-form defect class nobody has named

Three expected references name a **named section** of an annex:

| row | the key | our wire | our model |
| :-- | :-- | :-- | :-- |
| `rg_008` | `Annex I.a.11` | `Annex I.11` | `coordinate_exists('Annex I.a.11')` → **False** |
| `rg_072` | `Annex I.a.2` | `Annex I.2` | `coordinate_exists('Annex I.a.2')` → **False** |
| `rg_037` | `Annex VIII.a` | *(nothing)* | `coordinate_exists('Annex VIII.a')` → **False** |

Verified by execution, not by reading: `get_provision_text('Annex I')` begins
*"Section A. List of Union harmonisation legislation based on the New Legislative
Framework 1. Directive 2006/42/EC …"*, and `get_provision_text('Annex I.11')`
returns *"Regulation (EU) 2017/745 … medical devices"* — i.e. **Section A item
11**. The key's coordinate and ours are the same provision; the section letter is
the only difference, and our model drops it, so `_is_descendant('Annex I.11',
'Annex I.a.11')` is false.

This costs twice: the expectation is unmet **and** our flattened coordinate counts
in the Ref. Conciseness denominator (`min(1, |expected| / |provided|)`). Two to
three references, plus the conciseness overhang on those rows, for a change that
is pure structural fidelity. `Annex VIII` has the same shape (`Section A —
Information to be submitted by providers …`).

### 1.3 The number the project quotes is a STALE WIRE

R419 was captured on 15 Sep. The three wire-side passes that rewrite the graded
`references` field without touching the answer all landed **after** it:

| lever | round | measured |
| :-- | :-- | :-- |
| `REGENOLD_GROUND_WIRE_SUBPOINTS` | R425 | Ref. Strict **+0.62 pp** (336 row-samples, identical-draw pairing) |
| `REGENOLD_GROUND_WIRE_DEPTH` | R429 | Ref. Strict **+7.13 pp** offline (477 draws) / **+3.70 pp** live gate |
| `REGENOLD_GROUND_WIRE_ADD` | R431 | Ref. Strict **+3.76 pp** (554 rows) / **+3.70 pp** live; R419 board only **+5.30 pp** |

Every one of them is count-neutral or near-neutral (R431's ADD is the only one
that can add, and it is floor-gated at 66 % precision for **−0.86 pp** Ref. Conc),
and every one targets exactly the class §1.1 measured. So the honest position is:
**"Ref. Strict 70.59" is a wire that no longer exists.** Nothing may be designed
on top of it before it is re-scored.

---

## 2. P0 — prerequisites (do these before any lever)

### 2.1 Re-score HEAD on the R419 capture (`head_wire_rescore.py`, offline, no draws)

Drive the **real** passes in `app.routes.regenold` over the recorded R419
answers + wires (the R425 pattern: `wire_grain_grounding_probe.py`), score with
the **real** `evals.official.rubric`, and print the §1.1 taxonomy again under HEAD.
Judge-free, LLM-free, minutes not hours.

Pre-registered read-outs, per row where relevant (R428's lesson: a first
classifier folded "parent present at a shallower grain" into "parent absent" and
had to be corrected mid-round — assert per row, never argue):

* ref_loose / ref_strict / ref_conc, per row and mean, HEAD vs the recorded board;
* the §1.1 taxonomy recomputed with the residual classes split by **who owns
  them**: recovered-by-a-shipped-pass, prose names a rival (generation-side),
  prose names nothing (generation-side), coordinate-form (§1.2);
* count / folded-head-set / met→unmet violations asserted **per row** (R429's
  standard), not aggregated;
* the licence audit — for every coordinate any pass emits, which evidence named
  it (answer prose, question prose, or nothing).

Exit criterion: a residual table with a name and an owner for every unmet
expectation. This table is the round's specification; the workstreams below are
hypotheses about it that P0 may re-order or kill.

### 2.2 The harness needs a single-process invariant (blocking for any live board)

R436's own closing decision: the full hard run must be relaunched only after the
local harness **cannot** spawn a second Python 3.12 copy of the same batch (two
concurrent writers to one checkpoint were observed twice, R435 and R436/R437), or
against the deployed HTTP endpoint. A checkpoint lock or an owned-PID guard is the
minimum; the runner must refuse to grade if either arm contains a
fallback/degraded row or an incomplete checkpoint (already true) **and** refuse to
start if the checkpoint is open elsewhere.

---

## 3. The workstreams

Ordered by certainty × size. Each names its instrument and its gate, because a
lever without a gate is an opinion (R421 §3).

### P1 — Annex section coordinates (`Annex I.A.11`, `Annex VIII.A`) — **certain, bounded**

*The defect.* §1.2. Our coordinate model flattens a named annex section, so the
strict axis cannot credit a citation of the same provision, and the flattened form
still counts against Ref. Conciseness.

*The fix, in the model, not on the wire.* Add the section level to
`app/data/provision_text.py` + `provision_coordinates.py` + `eu_ai_act_tree.py` so
`Annex I.A.11` resolves to the same text as today's `Annex I.11`, and have the
citation path emit the **section-qualified** form where the corpus's own structure
has a section (Annex I, VIII). Bump `SEED_VERSION` (CLAUDE.md gotcha #3) so the
graph reseeds.

*Proof of sameness before any change:* `sibling_triage.py`'s Q3 test — two
coordinates whose statutory text is the same are one provision in two renderings,
and a pair that fails the text test must **not** be rewritten. No string hack, no
alias table: the section must exist in the model.

*Pre-registered conditions.* Count-invariant and head-invariant by construction
(1:1 in place, same parent); Ref. Loose and Ref. Conc byte-identical *except* the
Ref. Conc gain on rows where an excess flattened coordinate disappears; zero
met→unmet rows; `gold_dropped_head` unchanged. Instrument: replay over the R419
capture + the R424/R429 corpora; then the wire-slot live gate (§4).

### P2 — Depth-2 limb selection, question-voted — **the dominant class**

*The dominance argument (state it, it is the whole licence).* For a fixed head,
`_is_descendant` is one-sided: a prediction **more precise** than the key
satisfies it, and Ref. Loose reads `ref_head` (unchanged) while Ref. Conc is a pure
count ratio (unchanged by a 1:1 in-place completion). Therefore **replacing a
shallow limb with the deepest coordinate the answer's own substance establishes is
monotonically non-worse on all three reference axes.** This is R429's argument
extended from "the prose names it" to "the question's ask establishes it", which
is where the 18 deep gold refs live.

*The mechanism.* Extend the R386 deepener to descend one more level
(`REGENOLD_REF_GRAIN_DEPTH=2`, `_deepen_within` already recurses to 3), choosing
among candidate sub-limbs by **question-token overlap against each rival's own
statutory text** — R429's measured tie-break doctrine (18/18 on deciding cases),
and R431's finding that the question is the one vote a sibling cannot fake. Keep
R386's plateau discipline: `MIN_TOP`/`MIN_MARGIN` swept, every setting that drops a
gold head rejected, and no minting — a candidate must be admitted by
`coordinate_exists` **and** named by the answer *or* established by the question's
own text.

*Feasibility, measured:* `coordinate_exists('Article 5.1.h.iii')` → **True**
today, and `Annex III.7.b` is already on our wires; so the deep end is
expressible without new corpus work for most of the 18.

*Falsifier (do not skip).* The axes cannot see an ungrounded deeper pick: it is
free even when wrong. So the gate needs a **groundedness** criterion the axes do
not supply — a licence audit that every promoted coordinate is named or
established, plus R386's counterexample as the standing warning (minted
coordinates were 77 % accurate; 4 rows wanted the bare head).

*Pre-registered conditions.* Ref. Strict up with a CI; Ref. Loose and Ref. Conc
±0.00; 0 count violations; 0 met→unmet rows; `gold_dropped_head` B ≤ A; licence
violations 0. Two instruments: zero-variance replay over the recorded corpus
(coordinate-only, so the answer axes are invariant and re-judging them measures
0.00), then a live **wire-slot** gate (`lever_slot="wire"`, R425's third slot,
with the same-answer attribution rule so a draw difference can never be read as
the lever).

### P3 — Generation-side: the residue the wire cannot reach — **expensive, pre-register hard**

After P1/P2 and the shipped passes, what remains is the set where **the answer
never discusses the gold limb**: R431's triage called 50 of 173 expectations
"prose names neither", R428's census 79 of 223, and on the R419 board 5
expectations are heads we never cite at all — of which `rg_088` (Article 26.1,
26.6) is the **pushback capitulation** already characterised in R421 §2.3
(`REGENOLD_PUSHBACK_KEEP_CONTRACT`, default OFF, one row of evidence).

Two bounded items, in this order:

1. **Re-gate the pushback-keep contract.** One row, one axis, an existing lever,
   and R421's P1 already names it. Cheapest real correctness on the axis.
2. **A citation-grain contract in the Stage-2 user channel** (CLAUDE.md gotcha
   #1: the wrapper drops the system slot). R421's own finding is that the
   verbosity regression came from the scaffold's *instruction*, not its size, and
   that answer length is decoupled from what the row needs (corr with gold
   criteria +0.11 vs +0.55 for the reference). Target: name the operative limb the
   question turns on, in the same clause, without enumerating the article.

Gate: a paired hard run, **≥3 generations per row per arm** (R416: a one-draw
+8.0 pp re-scores to 0.00), gold-head retention as a hard constraint, and both
answer axes within −1.5 pp. Do not smuggle reference changes into a prompt lever.

### P4 — Keep the instruments honest

1. Extend `scratch/refstrict_taxonomy.mjs` into a checked-in
   instrument next to `wire_add_probe.py`/`wire_depth_probe.py`, so the census in
   §1.1 is reproducible per round rather than re-derived by hand.
2. Compute the seven-axis invariance claim from the wire (the pass runs after
   `_stage2_landed` and edits `references` only), which is what makes a
   zero-draw gate legitimate here — and say so explicitly in the checkpoint.
3. Every round report carries a `CHECKS PERFORMED` section (R421 P3: 4 of 5
   fabrication findings in that audit came from ungrounded claims).

---

## 4. The round gate (pre-registered, one table for every lever)

Fixed **before** the numbers are read. A wire-side lever may be read from the
replay plus a wire-slot live gate; a generation-side lever needs the full paired
board.

| # | condition |
| :-- | :-- |
| 1 | `ref_correctness_strict` (official rubric, same key) mean delta **> 0** with a reported CI |
| 2 | `ref_correctness_loose` **≥ −0.5 pp** (invariant by construction for P1/P2) |
| 3 | `ref_conciseness` **≥ −1.0 pp** (the one axis an ADD can lose) |
| 4 | `ans_correctness_loose` / `_strict` **≥ −1.5 pp** (invariant for wire-side levers) |
| 5 | `gold_dropped_head` B ≤ A — Hard Rule #8, and it is literally "drop ZERO more" |
| 6 | official overall (geometric mean of the eight axes) **≥ +0.0 pp** |
| 7 | zero count violations, zero folded-head-set violations, zero met→unmet rows, asserted **per row** |
| 8 | licence audit: every emitted coordinate named by the answer or established by the question's own text; 0 minted |

Board-level acceptance for the round: condition 1 cumulatively reaching
**Ref. Strict ≥ 80.0** on the hard split, on a board with **no** fallback/degraded
rows in either arm and a complete checkpoint (P0.2).

---

## 5. What NOT to do — every one of these has a measured price on disk

* **No global citation pruning.** 202 of 221 "excess" citations are provisions the
  answer's prose actually discusses; two of 19 prunable refs were expected ones.
  Measured, twice (R421 §3.1, R434).
* **No terminal reference cap.** Cap 3 fails by 4 gold heads at n=129; every value
  that passes is worth nothing, and the verdict **reversed** as n grew.
* **No keep-and-add repair of the substitution arm.** Strict +0.74 pp pays Ref.
  Conc −4.18 pp across 318 converted slots → −0.87 pp implied Overall.
* **No question-grounded veto on the substitution arm.** At its only firing floor
  it suppresses 43 winning substitutions to recover 11 keys: −0.61 pp net.
* **No unfiltered ADD.** 501 additions, 23.6 % precision, −0.80 pp implied
  Overall; and the `q = 0.0` column never reaches the plateau at any answer floor.
* **No ontology citable expansion.** 191 references unblocked, 1 gold, 190 excess.
* **No prompt-side pruning as the fix.** The prompt-size hypothesis is falsified
  (R422: with the five post-R390 additions OFF the Stage-2 payload is 6,530 chars
  *larger* and the answer is *shorter*), and the ref-precision lever family has
  failed four times against a non-minimal instrument.
* **No relaxing a test assertion to bank a gain** (the deepener's margin-0 2 pp is
  deliberately left on the table for this reason).

---

## 6. Artifacts

| path | what |
| :-- | :-- |
| `docs/measurements/r438/head_wire_rescore.py` + `.json` | P0 — HEAD re-score and residual taxonomy on the R419 capture |
| `docs/measurements/r438/taxonomy.py` | P4 — the census of §1.1, checked in |
| `docs/measurements/r438/section_coord_probe.py` | P1 — text-identity proof for the section-qualified forms |
| `docs/measurements/r438/depth2_probe.py` | P2 — zero-variance replay of the depth-2 pick + licence audit |
| `docs/measurements/r438/gate-*.json` | wire-slot / paired gate verdicts, pre-registered conditions printed |
| `docs/measurements/r438/CHECKPOINT.md` | verdict, in the R425/R429/R431 format |
| `scratch/refstrict_taxonomy.mjs` | this round's working instrument (promote, then delete) |

Reproduce today:

```bash
node scratch/refstrict_taxonomy.mjs                     # §1.1 census (no python needed)
.venv/Scripts/python.exe -m docs.measurements.r438.head_wire_rescore
.venv/Scripts/python.exe -m evals.official.score_arm --help   # the board scorer
```

## 7. Open questions and the one real fork

* **How much does HEAD already bank?** Unknown until P0 runs; the shipped passes'
  own numbers (+0.62, +3.70, +3.70/+5.30) were measured on different corpora and
  none of them was read against the R419 board's own key. If the re-scored
  baseline is already ≥ 74, the round should say so in the scorecard **before**
  adding a lever, and the bar moves to what a mechanism actually adds.
* **The fork.** P1/P2 are certain, bounded, count-neutral and reachable without a
  live draw; P3 is the only path to the last ~5 expectations and the only one that
  can also move Ans. Strict and the verbosity axes. Recommended split: land P1+P2
  and a hard board this round, and pre-register P3's Stage-2 contract for  the round after — unless the P0 table shows the residue is mostly P3, in which case
  invert.
* **The incentive risk worth stating out loud in the paper.** The strict axis
  rewards deeper coordinates for free; our own citation form is *less* precise
  than the Act's structure (the annex-section flattening of §1.2 is the proof).
  Closing the axis honestly means fixing the coordinate model, not minting
  coordinates the answer never establishes. Anything else would raise the number
  while lowering fidelity — and it would be invisible to all eight axes.
---

## Appendix A — the wrapper-served verbosity number is stale too (measured 2026-09-22)

Instrument: `scratch/answer_length_census.mjs`, `scratch/length_by_leg.mjs` (read-only
over `evals/bench/results/*.ckpt.jsonl` + the reconstructed gold).

**"The wrapper-served board averages 2,137 chars against a 649-char reference"**
describes the R419 capture (15 Sep, pre-R423.2) and is **false of HEAD**.

1. **The board mean is diluted.** 25 of 110 rows never reached Stage-2
   (`provenance.stage2_served_by == ""`, `retrieval_path: kb_fallback`) and average
   **579** chars (0.89x reference, `ans_conc` 94.8 %); 4 shipped deterministic drafts at
   971. The **81 wrapper-served rows average 2,677 = 4.12x** the reference, and their
   `ans_conc` is **27.0 %**, not the board's 44.19 %.
2. **Nothing caps length on the graded path.** The 53 kB full system prompt — the only
   lever ever measured to cut answers (0.199x, p50 37.4 -> 21.9 s) — is gated to
   `history_turn_count <= 1` (`REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`); the hard
   split's graded call is turn 10 (pushback 9/10), so it is past the gate BY
   CONSTRUCTION (R415: hard movement 0), and the R423 gate's own sidecar records the
   **61-char persona** on 108/109 primary rows.
3. **The user channel carried a flat, ask-independent enumeration instruction**
   (R422): `REGENOLD_CLOSED_SET_SKELETON` on **110/110** rows at mean 5,125 chars,
   including 5,862 chars on the four 1-criteria rows whose answers averaged 1,122 — and
   the five post-R390 additions OFF made the payload *larger* while answers got
   *shorter*, so it is the instruction, not the size.
4. **Decoupling, recomputed:** corr(gold criteria, reference length) **+0.552** vs
   corr(gold criteria, our answer) **+0.108**; p10 493 / p90 3,581 / max 5,308 chars;
   **79/110 rows > 2x** the reference and 62/110 > 3x.
5. **Not a pushback artifact:** turn-1 2,153.9 vs pushback 2,137.9 chars (0.99x),
   46/110 pushback longer, and `pred_answer == pushback_answer` on 37/37 of the R423 arms.
6. **A position confound rides on top:** corr(row index, chars) **+0.436**
   (+0.207 within primary-served); first 20 rows 1,825 vs last 20 rows 3,171. That is
   R424's rolling-harness defect (position decided the system prompt and the history
   depth), retired for new runs by the fixed 9-turn preamble — a measurement skew, not
   a system property.

**The shipped contract does reach that path — by construction and by measurement.**
The clause is appended by `graph_rag_prompts.build_evidence_answer_user`, i.e. the
**user** channel, and the wrapper only drops the *system* slot (CLAUDE.md gotcha #1).
On the wrapper's own leg, same 37 strided hard rows, three generations per arm
(`r423-need4`). **Score it on the COMPARABLE subset, never pooled** — 10 of the 37
rows have no primary sample in arm A and 9 of those are byte-identical across the
arms (the curated/deterministic path), so pooling them is exactly the error R423.1
records ("a curated-intercept row is answered identically in both arms, so
including one rigs the projection"). Recomputed independently from the six
checkpoints with the gate's own rule (≥2 primary samples per arm, per-row median
over 3 generations; `scratch/verify_need4_gate.mjs`):

| on the 27 comparable rows | OFF (A) | ON (B) | published gate |
| :-- | ---: | ---: | ---: |
| median answer chars | **3,242** | **1,134** | — |
| ans_conc | 22.08 % | 61.66 % | 23.09 -> 61.94 (**+38.86 pp**) |
| ref_loose | 96.30 % | 100 % | 96.30 -> 100 (**+3.70 pp**) |
| ref_strict | 72.22 % | 79.63 % | 72.22 -> 77.78 (**+5.56 pp**) |
| corr(criteria, chars) | **-0.051** | **+0.365** | — |
| corr(reference, chars) | +0.221 | +0.473 | gold's own +0.594 |

All 27/27 comparable rows shortened. So it does not merely shorten — it **restores
modulation** — and the gate held the answer axes flat (ans loose/strict ±0.00, gold
heads 1 -> 0, geomean +13.93).

**HEAD's wrapper-served level, primary-served rows only** (the all-rows mean is
dilution): R424 preamble A **1,162 chars / 60.6 %** (n=28), R429 depth A
**1,137 / 61.2 %** (n=28), R431 add A **1,143 / 61.7 %** (n=28) — i.e. **~1,140
chars, ~61 %**, not the ~1,000 / 68–70 % an all-rows mean reports. The comparable
subset's own ON value (1,134 chars) matches those boards to within 3 %.

**The R435 six-row sample is a CONTRARY signal in the tree, and it must be
reconciled before this appendix is quoted as settled.** Row-level audit
(`scratch/r435_sample_audit.mjs`) over `docs/measurements/r388/score-r435-sample-{A,B}-hard.json`:

* `ref_strict` 75.00 -> 58.33 (-16.67 pp) is **one row**: `rg_100` cited `Article 6.3`
  (the key) in arm A and `Article 6.2` in arm B — the R425 sibling class, not a
  contract mechanism. At n=6 one row moves the axis by 16.7 pp.
* `regulatory_tone` 6/6 -> 4/6 is **two rows**, and one has a named mechanism the
  prompt itself supplies. `rg_088`'s ON answer ends *"The evidence supplied contains
  no text for Articles 10(2), 12(2) or 43(1), so I cannot address those limbs"*, and
  the judge failed it for self-referential commentary. `rg_100`'s ON answer emits the
  same shape. **Arm A emits that sentence on 0 of 6 rows; arm B on 2 of 6.**
* The mechanism is `answer_need.shape_directive`'s last bullet, in BOTH branches
  (`answer_need.py:402` and `:417`): *"If a limb above has no supporting text in the
  evidence, say so in one sentence instead of padding."* It **contradicts the shipped
  default-ON V2 coverage clause**, which forbids exactly this (`graph_rag_prompts.py`:
  *"NEVER as a matter of your own sources: do not mention the references, provisions
  or material supplied to you, what was or was not retrieved, or how complete your
  inputs are ... self-contradictory whenever the answer cites the very provision it
  claims to be missing"*). The new clause wins, and the tone axis pays. No test pins
  the bullet, and no report names it.
* The level effect is absent on that sample (3 rows shorter, 2 longer, 1 flat;
  mean 1,404 -> 1,492) and the rows are adversarially chosen — `rg_010` is the
  unanchored Article 14 row, `rg_069`/`rg_088` are the rows R434 already flagged for
  tone, `rg_088` is the pushback-capitulation row. It is not a board; the R435
  checkpoint says so itself.

**The record is also self-contradictory at HEAD.** `answer_need`'s docstring,
`_graph_rag_impl._need_proportional_contract_enabled`'s docstring and
`r423/CHECKPOINT.md` all read **default ON** (aligned by `39931d7`, the newest
conciseness commit), while `r435/CHECKPOINT.md` — amended by that same commit — still
ends *"the correctness and tone regressions mean the contract remains OFF pending a
larger valid hard gate"*. The code is ON; the newest prose says OFF.

**The lever has never been measured at board scale, and half of the attempt is on
disk.** `evals/bench/results/official-r436-need-full-A-hard.ckpt.jsonl` is the aborted
R436 full hard run — 84/110 rows, and it is the lever's **OFF** arm: on the 28 rows it
shares with `r429-depth-A` it is **2.24x longer** (2,148 vs 961 chars). Its 59
primary-served rows run **2,942 chars / 25.1 % `ans_conc`**, matching R423's OFF
comparable subset (3,242 / 22.08 %). The paired ON arm was never captured, so the
board-scale claim rests on the gate's 27 rows until that run is redone under P0.2.

**Consequences for reporting.** (a) The conciseness gap to the frontier is **~10 pp**
wrapper-served-to-wrapper-served (61.7 vs 71.8), not the 27.6 pp the published boards
imply and not the ~3 pp a pooled figure suggests. (b) R421 §2.2, R430's projection and
the R436 checkpoint all still quote the R419 figure — ~17 pp below what the shipped
code does on the same leg. (c) Quote the **primary-served population separately**; the
no-Stage-2 rows flatter the axis (579 chars, 94.8 %, and 10 of those 25 are still
longer than the reference). (d) Verified sound: the clause reaches the graded pushback
call (the R435 ON answers contain its output), it is appended on the user channel with
fail-soft handling, the flag has one reader, a deny-list default, a cache-key entry, and
the scoped completeness block renders only when the clause does; 34 contract tests pass.

**Two open items this audit creates, both prompt-side and both gated:**

1. **P0-fix — SHIPPED as R438.1.** The missing-evidence bullet is restated in the
   legal form and every clause that speaks to an unsettled point now renders ONE
   shared string (`graph_rag_prompts.UNSETTLED_POINT_RULE`): the two coverage
   clauses, the evidence contract, and both branches of
   `answer_need.shape_directive`. Pinned by §3c of
   `tests/test_r423_need_proportional_contract.py` (the rule is contained in all
   four renderings, the bullet carries no input-state vocabulary, and the two
   coverage clauses are asserted byte-identical to their pre-refactor sha256, so
   the shared-constant splice is provably a no-op on delivered bytes).

   **A correction to the appendix above, and the reason a second clause had to
   move.** The contradicting partner is NOT the V2 coverage clause. V2 is default
   OFF since R379, and on the wrapper leg the coverage clause is not delivered at
   all: `_graph_rag_impl.py:10303` REPLACES the whole user message with
   `build_evidence_answer_user(...)` when `REGENOLD_EVIDENCE_CONTRACT` is ON
   (default ON), and `user_answer_coverage_clause()` is appended only at :10175,
   i.e. before that assignment — the same wholesale-replacement trap R391/R398/
   R399 each paid for. So the clause that actually co-ships with the need clause,
   in the same message, is `EVIDENCE_ANSWER_CONTRACT`, whose second sentence read
   "State the narrow unresolved condition if the evidence is insufficient" — an
   input-state trigger, the sibling of the bullet's "no supporting text in the
   evidence". It now reads "... where a point does not settle, but [rule]: never
   expose internal graph errors." The substance (state the narrow unresolved
   condition) is kept, so the R399 assertion on it still holds.

   ⚠ **Prompt-side, default ON → not yet a verdict.** Both changed strings ship in
   the delivered payload of default-ON gates, so AGENTS.md invariant #5 applies:
   the pair needs the `gold_dropped_head` / paired-judge gate before any number is
   quoted. Suggested label `r439-lawform`, 37 strided hard rows, both arms on the
   same leg, `ans_correctness_*` and tone read row-level (the failure mode is one
   sentence in a minority of rows, so an aggregate-only read cannot see it).
2. **Re-gate the contract on tone**, which is judge-gated and therefore needs a live
   pass: the R423.2 gate's own tone axis was 100 -> 100 on 27 comparable rows, so this
   is a targeted six-row-class check, not a full board.

---

