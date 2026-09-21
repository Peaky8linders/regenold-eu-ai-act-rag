# R429 — the wire coordinate is COMPLETED to the grain the prose names

**Lever:** `REGENOLD_GROUND_WIRE_DEPTH` (default **ON**), inside
`_ground_wire_subpoints` (`app/routes/regenold.py`).

**One sentence.** R425 abstains when the prose names a *deeper* coordinate of the
wire's own limb — and that abstention was justified on a premise the official
rubric's own source falsifies, so completing the coordinate is monotone on every
reference axis and free on the other two.

---

## 1. The premise R425 abstained on, and why it is false

`_grain_compatible` (R425) treats a prefix relation as "depth, not substitution"
and abstains, with this reasoning in its own docstring:

> *A prefix means depth, not substitution: prose `Article 13(3)(b)` against a wire
> `Article 13.3` is the same limb at a shallower grain, and rewriting it would
> replace a graded coordinate with a deeper one **the evaluator may not key on**.*

The evaluator keys on it. Ref. Correctness (Strict) is per-question recall of the
expected coordinates, and its predicate is:

```python
def _is_descendant(pred: str, expected: str) -> bool:
    return pred == expected or pred.startswith(expected + ".")
```

A prediction **strictly more precise** than the key satisfies the key. So
completing `Article 13.3` → `Article 13.3.b`:

| axis | mechanism | outcome |
| :-- | :-- | :-- |
| Ref. Strict | a descendant satisfies every expectation its ancestors satisfied, **plus** the one that *is* the descendant | can only ADD satisfied keys |
| Ref. Loose | scored through `ref_head`; the parent never changes | bit-identical |
| Ref. Conciseness | `min(1, \|expected\| / \|provided\|)`, a pure COUNT ratio; the rewrite is 1:1 in place | bit-identical |

`gold_dropped_head` is therefore `+0` and the count invariant **by construction,
not by measurement** — the same shape as R386/R391/R425. Measured anyway (`§3`).

**Where the deficit was.** R428 classified the unmet gold sub-point expectations
and found the largest bucket was exactly this one. It is also the bucket R425 had
explicitly decided not to touch.

---

## 2. The mechanism

`_grain_relation(wire, prose)` replaces R425's boolean with four readings:
`same`, `**coarser**` (the wire is a strict prefix of the prose — the R429
population), `finer` (the wire is already the more precise of the two), `sibling`
(the R425 substitution population). `_grain_compatible` survives as the boolean
summary.

On a `coarser` reading the pass now **completes** the coordinate instead of
abstaining, to a coordinate that is (a) named by the answer's own prose — the
R425 grounding rule — and (b) admitted by `coordinate_exists`. It never mints a
coordinate, and it stays 1:1 in place.

Two things the first draft got wrong, both caught by measurement rather than by
reading the diff:

* **An early `break` on an exact-grain match suppressed a deeper completion the
  prose also named.** `rg_070` ships `Article 6.1` while its prose names both
  `6.1` and `Article 6.1.b`, and the old `break` returned before reaching `6.1.b`.
  Removing it took the completions from 79 (**15** gold) to 162 (**78** gold) —
  precision 19 % → 48 % — and the axis delta from +3.14 pp to +3.77 pp.
* **The tie-break between several prose-named descendants is where the remaining
  precision lives.** It is free either way (every rival is a descendant of the
  coordinate it replaces, so nothing graded can move), so it is a pure bet on
  which rival the gold keys on. Measured on the 18 cases where the choice actually
  DECIDES the gain:

  | rule | picks a max-gain rival |
  | :-- | --: |
  | **answer-token overlap with the rival's own provision text** | **18/18** |
  | question-token overlap | 13/18 |
  | order of mention in the prose | 13/18 |
  | lexicographic first (the first draft) | 3/18 |

  Answer overlap is the **R425 doctrine** applied to a tie-break: the wire follows
  the answer's prose, because the answer is the text that actually engages the
  provision (that round measured citation faithfulness 0.960 beside reference
  correctness 0.480 — the answer is not what drifts). The question is the weaker
  vote here for the opposite reason than in R386: a question almost never names a
  sub-limb, while the answer names both rivals by construction.

  ⚠ **18 deciding cases is a small sample and six rules were compared on it.**
  The 18/18 is not a promise; the *mechanism* is what justifies the pick, and the
  choice cannot cost a graded axis if the bet is wrong.

---

## 3. Offline evidence — the population replay

`docs/measurements/r429/wire_depth_probe.py` (no live calls). 630 recorded hard
draws, **477** of them carrying gold refs *and* a landed Stage-2; 153 excluded
because the route gates this pass on `_stage2_landed` and a replay that grounded a
deterministic, hand-validated wire would measure a change production never makes.

The captures predate the R425 merge (dated 2026-09-19/20 against `981ec6d` on
2026-09-20), which is visible in the data — `rg_007` ships `Article 50.3` where its
prose names `Article 50(1)`. That is what makes the arms clean:

| arm | definition |
| :-- | :-- |
| `shipped` | the wire as recorded (pre-R425; not today's board) |
| `r425` | `pass(shipped)` with the depth lever OFF = **today's board** |
| `r429` | `pass(shipped)` with the depth lever ON |

| axis | shipped | r425 | r429 | **Δ r429 − r425** |
| :-- | --: | --: | --: | --: |
| Ref. Correctness (Loose) | 98.32 | 98.32 | 98.32 | **+0.00** |
| Ref. Correctness (Strict) | 64.92 | 65.55 | **72.68** | **+7.13** |
| Ref. Conciseness | 42.73 | 42.73 | 42.73 | **+0.00** |

*(context: R425's own already-shipped effect on the same board is `+0.63` pp strict.)*

Safety, asserted per row rather than argued:

| check | value |
| :-- | --: |
| reference-count violations | 0 |
| folded-head-set violations | 0 |
| Ref. Strict regressions (met → **unmet**) | **0** |
| Ref. Loose regressions | **0** |
| coordinates completed | 162 (94 gold / 68 excess) |
| ... of which a tie-break had to decide | 84 |
| rows where Ref. Strict moved | 34 |

Attribution over the unmet gold sub-point expectations **on today's board** (207
total):

| bucket | count | owner |
| :-- | --: | :-- |
| wire ships a COARSER coordinate | 63 | **R429** |
| ... wire ships the BARE HEAD | 22 | R386's deepener / R133's add — out of scope |
| ... no prose-named descendant to use | 7 | nothing to complete to — out of scope |
| ... reachable, and **converted** | **34** | (34 of 34 reachable) |
| same parent, other limb | 135 | R425's substitution population |
| no coordinate of the parent on the wire | 9 | a coverage pass |

## 3.1 Real surface, read directly

Driving the REAL route in-process (`TestClient`, scripted Stage-2) rather than
reasoning from the diff, two questions:

| question | OFF refs | ON refs | count | heads | answer |
| :-- | :-- | :-- | :-- | :-- | :-- |
| "What must a provider of a GPAI model document?" | `['Article 53.1']` | `['Article 53.1.b']` | invariant | invariant | byte-identical |
| "...technical documentation... hardware?" | `['Article 11.1', 'Annex IV.1']` | `['Article 11.1', 'Annex IV.1']` | — | — | — |

The second row is **correct and not a miss**: that question is a curated
intercept, so Stage-2 never lands and the route gates this pass on
`_stage2_landed` — the hand-validated wire is deliberately untouched (the R274
doctrine). A direct call to the pass on the same inputs proves the mechanism on
the fixture the row is about: `['Article 11.1', 'Annex IV.1']` →
`['Article 11.1', 'Annex IV.1.e']` with the answer and the count unchanged.

### The switch, driven at runtime on real rows

Not just "the default is ON" but "the default is ON and `=0` is a true no-op",
driven by re-importing the route with the env var flipped and running the pass over
the three live `r429-depth` checkpoints:

```
flag=1: changes=31 on 13 rows
flag=0: changes=0  on  0 rows
rows touched: rg_001, rg_025, rg_046, rg_055, rg_067, rg_070, rg_073, rg_088,
              rg_091, rg_094, rg_100, rg_106, rg_109
```

## 4. Tests

* `tests/test_r429_wire_depth_completion.py` — 39 new tests: the gate, the four
  relation readings, the completion (incl. multi-level `13.3` → `13.3.b.i`), the
  never-a-swap contract, the tie-break, the bare-head and non-existent-coordinate
  refusals, fail-soft, and a parametrised **monotonicity assertion against the real
  `evals.official.rubric`** on five board-shaped fixtures. Plus a route-level test
  that the third argument really is the live question.
* `tests/test_r425_wire_grain_grounding.py` — `test_a_grain_depth_difference...`
  **rewritten**: R425 pinned the abstention, and the abstention is what this round
  falsified. The test now asserts the completion *and* that `=0` restores the
  abstention, so the old contract is still pinned as the OFF arm. Four route spies
  gained the third parameter.
* `tests/test_sota_legal_kg_ontology.py` — one assertion updated (`Annex IV.1` →
  `Annex IV.1.e`).

Full suite on a stable tree: **8586 passed, 2 skipped, 0 failed** (up from 8547).

## 5. What this changes about R428's own record

`docs/measurements/r428/dotted_subpoint_probe.py` still reproduces its conclusions
(the R426 dotted ADD contributes 0 references, moves Ref. Strict on 0 rows, and
satisfies 0 unmet expectations — every ADD delta is `+0.00`). Its classifier's
`named_only_a_shallower_grain` bucket falls **138 → 86**, because the completion now
repairs those before the classifier sees them. That is the intended interaction,
not a regression.

## 6. The live gate

`docs/measurements/r429/wire_depth_gate.py`, launched as:

```bash
python -m evals.regenold.run_official_batch --label r429-depth --mode hard \
    --stride 3 --repeats 3 \
    --baseline-env REGENOLD_GROUND_WIRE_DEPTH=0 \
    --branch-env  REGENOLD_GROUND_WIRE_DEPTH=1
python docs/measurements/r429/wire_depth_gate.py
```

The paired-arm form was launched as written; it was **stopped after arm A finished**
because, for this lever, a second live arm buys noise rather than evidence — see
"Why there is only ONE live arm" below. What the reader scores is **37 strided hard
rows × 3 independent generations = 111 fresh live draws** with the lever OFF, each
re-scored with the lever ON by re-running the pass over the SAME answer. The reader
is deliberately cheap and deliberately strict:

* the **void guard decides first**, with `lever_slot="wire"` — this lever changes
  no byte the transport sees, so the run is valid only if the arms EMITTED
  different reference sets;
* the **answer axes are PROVEN invariant, not re-measured**: the pass runs after
  Stage-2 landed and edits only `references`, so the reader asserts the answer text
  is byte-identical across arms on every paired row. That closes Answer Correctness
  (loose and strict) and Regulatory Tone by construction, and saves an hour of
  judge calls on a channel that cannot open;
* the three reference axes need **no judge** — they are the emitted `references`
  against the gold key, pure arithmetic;
* every number is a per-row **median over the 3 generations**, paired, with a
  seeded bootstrap CI over rows;
* pre-registered rule: strict ≥ −1.5 pp, loose and conc within −1.5 pp, gold heads
  B ≤ A, count and head set invariant. **SHIP iff all hold**, else the default
  reverts to `0`.

**RESULT — `VERDICT: SHIP (default stays ON)`, all nine criteria PASS.**
One live arm, 37 strided hard rows × 3 independent generations = **111 fresh
live draws** (arm A with the lever OFF); artefact `gate-verdict.json`.

| check | value |
| :-- | :-- |
| **licence — the recorded wire is a fixed point of the pass** | **111/111** |
| comparable rows (≥ 2/3 primary-served, gold refs) | 27 |
| non-vacuity — rows where the derived arm differs | **11/27** |
| coordinates completed | 25 (gold 15) |
| answer-axis invariance | by construction (one arm, one answer) |

| axis | OFF | ON | Δ | 95% CI (seeded) |
| :-- | --: | --: | --: | :-- |
| Ref. Correctness (Loose) | 100.00 | 100.00 | **+0.00** | [0.00, 0.00] |
| Ref. Correctness (Strict) | 69.75 | **73.46** | **+3.70** | [0.00, +11.11] |
| Ref. Conciseness | 45.80 | 45.80 | **+0.00** | [0.00, 0.00] |

| safety check | value |
| :-- | --: |
| rows where Ref. Strict moved | up **1** / down **0** |
| gold heads dropped | OFF 1 → ON 1 (Hard Rule #8 satisfied) |
| count-invariance violations | 0 |
| folded-head-set violations | 0 |
| met → unmet regressions | 0 |

Worked examples from the live draw: `rg_046` `Article 13.3` → `Article 13.3.e`,
`rg_055` `Article 5.1.h` → `Article 5.1.h.i`, `rg_067` `Article 51.1` →
`Article 51.1.b`, `rg_070` `Article 6.1` → `Article 6.1.b`.

⚠ **Read the CI, not the point estimate.** Exactly ONE of 27 rows moved, and it
moved a full 1.0 of its strict recall, so the mean shift is that one row divided by
27 — which is why the lower bound is 0. The direction is not established by this
CI; it is established by `rubric._is_descendant`, which makes a deeper prediction
satisfy every expectation its ancestors satisfied. The live gate's job was to prove
the edit is harmless and reachable on a fresh draw, and it does.

### Why there is only ONE live arm

The pass runs AFTER Stage-2 and edits only `references`, so a second live arm would
re-draw the LLM answer for nothing while making the reference comparison inherit
generation noise — the exact thing the 3-generation protocol exists to control.
Deriving both lever states from the SAME draw is strictly less noisy. The licence
for the derivation is the 111/111 fixed-point check above (and it is the same
reasoning the R425 round used to stop its own two-arm wire gate).

## 7. The licence, asserted instead of sampled

Both the probe (477 recorded draws) and the gate (111 fresh draws) are SAMPLES. A
sample can only fail to find a counterexample. `wire_depth_fuzz.py` asserts the
property over the REAL pass on 20 000 randomised inputs, built from the 249
coordinates the board has actually emitted plus synthetically deepened ones that
`coordinate_exists` admits.

```
pool                 : 249 recorded coordinates
parent pool          : 241
trials               : 20000  (prose forms {'paren': 10033, 'dotted': 9967})
trials with an edit  : 19567
R429 completions     : 2222  (strict descendants)
R425 substitutions   : 17345  (rewrites onto a prose-named limb)
violations           : NONE
```

Held universally: **count invariance** (`len(out) == len(refs)` — what makes the
lever free on Ref. Conciseness), **folded-head-set invariance** (Ref. Loose, and
Hard Rule #8 by construction), **no minting** (`coordinate_exists` on every emitted
coordinate), and **fixed point** (re-running the pass over its own output changes
nothing, so a replayed or cached answer cannot drift).

**The first run of this file FALSIFIED, and the falsification was informative —
about the record, not the pass.** I asserted "every changed coordinate is a strict
descendant of what it replaced" and got 17 345 counterexamples. They are all one
shape: `before='Article 18.1.e'` → `after='Article 18.1.a'`, i.e. **R425's sibling
substitution**, which shares this function. R425's licence is a board measurement
(the replaced wire limb was gold in 0 of 106 substitutions), **not** an algebraic
property, and R429's monotonicity argument does not extend to it. The assertion is
now the honest disjunction — a change is either a monotone completion *or* a
rewrite onto a limb the answer's own prose names — and the R429 population is
asserted non-empty separately (2 222 of the 20 000). Anything in neither class is
a violation, and there were none.

### The live draw is pure R429, measured rather than assumed

The gate's counter (`coords_completed`) counts ANY new coordinate, so it would mix
the two populations if any substitution survived on today's wire. It does not, and
that is checkable: today's board already has R425 ON, so its recorded wire IS the
post-substitution wire and the only residual work is the depth completion.
Classifying all 37 rows × 3 generations of the live draw by
`rubric._is_descendant`:

```
change populations: {'descendant': 31}
of which gold:       {'descendant': 21}
```

**Zero substitutions.** Every one of the 31 live changes is a strict descendant,
21 of them onto a gold key (`Annex IV.1 → Annex IV.1.e`, `Article 13.3 →
Article 13.3.e`, `Article 5.1.h → Article 5.1.h.i`, `Article 25.1 → Article 25.1.c`,
`Article 49.4 → Article 49.4.a`, …). The gate prints 25 rather than 31 because it
scores the 27 comparable rows; the population over all 37 is 31.
