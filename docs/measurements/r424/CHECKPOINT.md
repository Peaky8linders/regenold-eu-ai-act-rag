# R424 — the hard modality is now the OFFICIAL one

Status: **SHIPPED** — the gate passed all four pre-registered conditions and
`fixed` is now the harness default (`evals.regenold.hard_preamble.DEFAULT_MODE`,
PR #441). Verdict and the one open finding are in §6.

## 1. The defect

`evals.regenold.run_official_batch._run_hard` asked each question inside a
**rolling** conversation of our own prior questions and answers, trimmed to 4
exchanges and **starting empty**. Three consequences, all measured:

1. **No two rows were asked under the same modality.** Row 1 read
   `history_turn_count` 0 and row 5 read 8.
2. **Those leading rows were dispatched a different system prompt.** The engine's
   predicate is `history_turn_count <= 1`, so row 1 took the full **59 644-char**
   system prompt while every later row took the **61-char** persona. One arm, two
   system prompts, decided by a row's *position*.
3. **The graded task was not the official one.** The official description is
   explicit: *"a pre-fixed synthetic 9-turn conversation — so that the actual
   question being evaluated appears in the 10th turn."* Nothing about the run was
   pre-fixed, and the context was our own prose rather than a fixed regulatory
   dialogue.

R423.3 patched the *symptom* (`--resume` handing its pending rows a fresh empty
rolling history, which re-graded its first rows as near-single-turn). R424 removes
the cause: with a fixed prefix there is nothing to roll, so a resumed run is
identical to an uninterrupted one by construction.

## 2. The depth is measured, not guessed

The evaluator's own export for the graded 2026-07-07 run
(`REGENOLD_JULY_7_EVALUATOR_BATCH.md`) records `history_turns_used` per request
and it is **constant at 18 for all 111 hard turn-1 rows**, and 20 for turn 2
(18 + our answer + the pushback). A rolling window cannot hold a constant — it
grows across a session. 18 prior messages is **9 (user, assistant) exchanges**,
which is exactly the "9-turn conversation" of the description with the target
question on the 10th turn. The two pieces of evidence agree, so
`HARD_PREAMBLE_EXCHANGES = 9`.

The reconstruction is of the **shape and the purpose**, not of the grader's
verbatim text, which we do not hold. The fixture is deterministic and
byte-identical for every row and arm (`preamble_digest()` =
`cb85452c9c041721`, ~6.8 kB), which is what makes a board measured on it
comparable.

**Where the statutory numbers go, deliberately.** Every explicit Article / Annex
number lives in an *assistant* turn. `_extract_conversation_anchors` reads prior
**user** turns and prepends up to six article numbers to the live question, so
numbers in a user turn would inject the same fixed article list into the scope and
retrieval of all 110 rows — our machinery, not the official instrument, and a
global constant that would confound the very delta this fixture exists to measure.
`tests/test_r424_hard_preamble.py` runs the real extractor over the fixture and
asserts an empty anchor line, and asserts the role/risk word sets are absent too.

## 3. Measured at the seam (offline, reproducible)

`docs/measurements/r424/hard_preamble_probe.py` drives real rows through the real
route with a stubbed provider (the dispatch shape is decided *before* the provider
is reached, so the stub is faithful and the check costs no quota). The decisive
pair asks the **same row** twice, varying only its position:

| mode | row | turn | alone (hist, system) | behind (hist, system) | |
| :-- | :-- | :-- | ---: | ---: | :-- |
| rolling | `rg_004` | t1 | **(0, 59 644 — FULL)** | **(2, 61 — persona)** | **CHANGED with position** |
| rolling | `rg_004` | pb | (2, 61) | (4, 61) | changed |
| fixed | `rg_004` | t1 | (18, 61) | (18, 61) | invariant |
| fixed | `rg_004` | pb | (20, 61) | (20, 61) | invariant |

The fixed arm's depths **18 and 20 are the evaluator's own recorded values** for
the graded run — an independent confirmation that the reconstruction is the right
shape, not merely a consistent one.

**What the fixture does and does not do.** Every dispatch carries
`fixture=no, conv=no, anchors=no`: the route flattens prior turns into a
`"Conversation so far: … Latest question: …"` preamble and the engine STRIPS it
for the model-facing prompts, using it instead for classification, scope, anchors
and the deterministic retrieval input. So the official dialogue changes what the
**engine** sees — a constant, deep multi-turn request instead of a cold
single-turn one — **not what the model reads**. That is the honest scope of this
lever, and it is why the gate reports all eight axes rather than a headline.

## 4. The guard had to change with it

This lever lives **above the engine**: both arms dispatch the same system
payloads, which is the CORRECT outcome, and the existing non-vacuity rule
(`lever_changes_system`) would have voided a run that was built correctly. A
request-slot lever is now checked on the request slot:

* `gate_validity.lever_changes_request` + `REQUEST_SHAPE_FLAGS` decide the slot;
* `assess(..., lever_slot="request")` requires the two arms to have RECORDED
  different request shapes, and treats an identical system digest as expected
  rather than suspicious;
* the default (`lever_slot="system"`) is byte-identical to the old behaviour, so
  every existing caller is unchanged;
* `ArmProvenance.request_shape` is carried through `as_dict`/`from_dict`, so a
  saved verdict is still re-derivable without re-spending the draws.

## 5. The gate

37 strided hard rows (`--stride 3`) × **3 independent generations** per row per
arm, both arms in ONE process so the void guard can see them:

```
.venv/Scripts/python.exe -m evals.regenold.run_official_batch \
    --label r424-preamble --mode hard --stride 3 --repeats 3 \
    --baseline-env REGENOLD_HARD_PREAMBLE=rolling \
    --branch-env  REGENOLD_HARD_PREAMBLE=fixed
```

Arm A = rolling (the shipped board shape, i.e. every board on record); arm B =
fixed 9-turn dialogue. Judged with the R419/R423 board's exact instrument
(`openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:r=3`), cache seeded from the R419
cache. Comparability excludes rows that never reached Stage-2 **symmetrically**,
with a floor of 20 comparable rows.

**Pre-registered decision rule** (fixed before the numbers were read), because
this is a fidelity correction rather than an optimisation — a request shape that
costs correctness is not worth a more faithful harness:

| # | condition |
| :-- | :-- |
| 1 | `ans_correctness_loose` mean delta > −1.5 pp |
| 2 | `ans_correctness_strict` mean delta > −1.5 pp |
| 3 | official overall (geometric mean of the eight axes) ≥ −1.0 pp |
| 4 | gold heads dropped B ≤ A (Hard Rule #8) |

## 6. The gate — VALID, and the answer correctness cost is zero

Judge cache seeded from the R419 board and the gate scored all six checkpoints
with that instrument. Both arms' graded Stage-2 calls carried the **61-char
persona** (system digest `f46a309464083c54`, identical in both arms — the correct
outcome for a request-slot lever), `fallback_attempts=0`, `refused=0`,
`primary_failed=0` on both, every graded row served by the primary leg, and the
request shapes recorded differently (`rolling` vs `fixed:cb85452c9c041721`).
Two rows (`rg_058`, `rg_061`) excluded symmetrically by the caller's degraded-row
accounting. **28 of 37 comparable** (floor 20).

Per-row medians over the 3 generations:

| axis | A rolling | B fixed | Δ |
| :-- | ---: | ---: | ---: |
| Ans. Correctness (Loose) | 97.09 | 97.09 | **+0.00** |
| Ans. Correctness (Strict) | 92.86 | 92.86 | **+0.00** |
| Ans. Conciseness | 60.59 | 62.45 | +1.86 |
| Ref. Correctness (Loose) | 98.21 | 100.00 | +1.79 |
| Ref. Correctness (Strict) | 74.40 | 70.83 | −3.57 |
| Ref. Conciseness | 48.14 | 50.00 | +1.86 |
| Regulatory Tone | 100.00 | 100.00 | +0.00 |
| Resp. Speed | 73.21 | 73.63 | +0.42 |
| **OVERALL (geomean)** | 78.44 | 78.56 | **+0.11** |

```
[PASS] ans_loose > -1.5 pp
[PASS] ans_strict > -1.5 pp
[PASS] official overall >= -1.0 pp
[PASS] gold heads dropped B <= A
VERDICT: SHIP
```

The answer axes are **tied on all 28 rows**, not merely close: both correctness
means move by exactly 0.00 pp with a CI of [0.00, 0.00]. Gold heads dropped are
1 vs 1 — the same row (`rg_106`, `Annex III`) in both arms, so the fixed shape
neither creates nor fixes a drop. What the fidelity correction buys is a modality
that is a constant of the run instead of a function of a row's position, at no
measured cost in correctness.

Characterising the `Ref. Correctness (Strict)` −3.57 pp (`refstrict_draw_dependence.py`):

* It is **two rows and one partial** out of 28 (`rg_016` 1.00→0.00, `rg_082`
  1.00→0.00, `rg_085` 0.67→0.33). Mean −8.33 pp; median +0.00 pp.
* `rg_016` is **stable in arm A and unstable in arm B** — its own three
  generations record `99.3 / 99.4 / 99.3` — which is the R419 draw-dependence
  condition, not a systematic penalty of the shape. Dropping that one row moves
  the mean to **−4.94 pp**.
* The mechanism is a **reference-grain substitution**, and it is independent of
  the preamble: in 15 arm-row occurrences across 8 rows the graded wire reference
  records a *neighbouring limb of a parent the prose itself sub-points*. The
  clearest case is `rg_016` B s0, whose answer says in words
  "…(Article 99(3))" while the wire ships `Article 99.4` — the exclusion limb it
  mentions last instead of the penalty limb the question is about. Arm A's own
  turn-1/turn-pushback pair for the same row does the same thing
  (`turn1_refs=['Article 99.4', …]` against `pushback_refs=['Article 99.3', …]`).

That is recorded as the **next lever, not fixed here**, because it is a route
change to the graded `references` field that touches Ref Conciseness and Hard
Rule #8 and therefore needs its own paired gate — exactly the standard this round
was held to. See §7.

## 7. Open finding (R425 candidate) — wire grain substitutes a neighbouring limb

> **CLOSED IN R425.** Shipped as `REGENOLD_GROUND_WIRE_SUBPOINTS` (default ON,
> `_stage2_landed`-gated), with the direction measured over this gate's own six
> checkpoints (336 comparable row-samples, identical-draw pairing): 106 applied
> substitutions, the wire limb is gold in **0** of them, and Ref. Strict moves
> `65.28 → 65.90 (+0.62 pp)` with Ref. Loose and Ref. Conciseness byte-identical
> and the head set and reference count invariant on every row.
> See `docs/measurements/r425/CHECKPOINT.md`.

**Evidence.** `docs/measurements/r424/refstrict_draw_dependence.py` over the six
gate checkpoints. Signature: prose sub-points a parent at one limb, the wire
records another limb of the same parent the prose never names
(`rg_067` prose `Article 3.64` / wire `Article 3.65`; `rg_103` prose
`Article 3.60` / wire `Article 3.46`; `rg_100` prose `Article 6.3` / wire
`Article 6.2`; `rg_007` prose `Article 50.1` / wire `Article 50.3`).

**Why it is a defect and not a preference.** The official evaluator grades
Ref. Correctness (Strict) off the `references` field we ship, and the route's own
contract is that the wire is recomputed from the prose. A limb the prose never
names is therefore both a scoring loss and a fidelity error in the graded
artifact. It is the *mirror* of the R133 problem: that round taught
`_surface_prose_subpoints` to ADD a sub-point the prose names and the wire lacks,
and never taught it to REMOVE one the prose does not name.

**Proposed remediation (needs a gate).** Extend the prose-surface pass to
substitutions rather than only additions: when the prose sub-points a parent and
the wire carries a different limb of that parent the prose does not name, replace
the wire limb with the prose-named one. Bounded, order-preserving, deduped,
fail-soft — the same shape as the existing pass. It must be gated on the hard
split because it edits the graded reference set: the pre-registered bar is
Ref. Correctness (Strict) up, Ref. Conciseness not down, **gold heads dropped
unchanged** (Hard Rule #8), and both answer axes within −1.5 pp.
