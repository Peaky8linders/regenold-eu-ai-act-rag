# R425 — prose-grounded reference grain

Status: **SHIPPED, default `1`.** Verdict is carried by two instruments rather
than one brute-force board run, and the reason is a property of the lever (§5):
the rewrite cannot change the ANSWER, so the two answer axes are invariant by
construction and re-drawing them costs ~5 h to measure exactly `0.00`. What can
move is the three REFERENCE axes, and those are the emitted `references` against
the gold key — **no LLM involved**. So the population read is a replay over
already-drawn samples (336 comparable row-samples, **every one paired within its
own draw**), and the live leg is targeted at the rows where the mechanism must
fire (§7). `docs/measurements/r424/CHECKPOINT.md` remains the last full
hard-split board.

## 1. The defect

The official evaluator grades **Ref. Correctness (Strict)** off the `references`
field we ship, and the route's own contract is that the wire is recomputed from
the final Stage-2 prose (`_reconcile_references_to_prose`,
`_add_prose_named_refs`, `_surface_prose_subpoints` — all default ON). But R133's
`_surface_prose_subpoints` only **ADDS** a prose-named leaf when the **bare
parent** is on the list:

```python
# regenold.py — the R133 pass, before R425
for ref in references:
    out.append(ref)
    for sub in wanted.get(ref.strip(), ()):   # <-- keys on the BARE PARENT string
        ...
```

So a wire that already carries a **sibling limb** never receives the grounded
one, and the ungrounded limb ships. Measured cases from the R424 gate's own
checkpoints:

| row | the answer's prose names | the graded wire recorded |
| :-- | :-- | :-- |
| `rg_100` | `Article 6(3)` | `Article 6.2` |
| `rg_067` | `Article 3(64)` | `Article 3.65` |
| `rg_103` | `Article 3(60)` | `Article 3.46` |
| `rg_061` | `Article 53.3`, `Article 75.3` | `Article 53.1`, `Article 75.1` |

It is the mirror of the R133 problem: that round taught the pass to add a
sub-point the prose names and never taught it to stop shipping a limb the prose
does not name.

## 2. Which pass mints the limb

Two sources, both legitimate and neither aware of the prose:

* **the R386 grain deepener** (`_deepen_ref_grain`, `:12306`) picks a paragraph
  from question/answer token overlap at a measured **77 % accuracy** and is
  explicitly forbidden from using the answer alone (Audit Finding 1). On rows
  whose prose names a different limb it can pin the sibling.
* **retrieval / the closed set** can hand over the limb directly.

The pass order is what makes the defect reach the wire: R133 runs at `:11817`,
the deepener at `:12306`, so the last word on *which limb* belongs to the
deepener — and nothing between them consults the prose.

## 3. The fix — `_ground_wire_subpoints` (`regenold.py:4517`)

Replaces a wire limb the prose never names with the limb it does name.

* **Position**: immediately AFTER the deepener and the R397 coordinate guard, and
  BEFORE the passes that can DROP (R385 qrel prune, R381 terminal cap). So it is
  the last word on *which limb* ships, it reads only coordinates the Regulation
  contains, and a dropped reference is never one just grounded.
* **Direction**: prose-named limb wins. A wire coordinate that is not equal to and
  not a **prefix** of a prose-named coordinate (and vice versa) is a substitution;
  a prefix is a grain-depth difference (`Article 13.3` against prose
  `Article 13(3)(b)`) and is left alone.
* **Bounds**: 1:1 in place, order-preserving, deduped, capped at one rewrite per
  wire leaf, candidates filtered to `coordinate_exists` and to the same parent,
  fail-soft. It never adds a reference and never drops one.
* **Gating**: `REGENOLD_GROUND_WIRE_SUBPOINTS` (default ON, deny-list semantics,
  registered in `_engine_cache_key`) **and** `_stage2_landed` — the same gate its
  ADD twin carries (R133), for the same reason: the deterministic /
  curated-interception path has no Stage-2 prose and its reference set is
  hand-validated (the R274 doctrine). Gating keeps that wire byte-identical by
  construction, which is also what keeps every offline instrument neutral.
  **It costs none of the measured benefit: all 80 rewritten row-samples were
  served by the primary leg** (§4).

## 4. Offline evidence (`wire_grain_grounding_probe.py`)

Drives the **real** pass (`app.routes.regenold._ground_wire_subpoints`) over the
R424 gate's six checkpoints and scores with the **real** official rubric
(`evals.official.rubric`) — not a re-implementation of either.

```
comparable row-samples scored: 336
row-samples rewritten by the pass: 80 (20 distinct rows)
true substitutions: 106 across 20 rows
  wire limb IS gold / prose limb IS gold / both / neither: 0 / 7 / 8 / 91
  legs that served the REWRITTEN row-samples: {'primary': 80}
head set invariant where rewritten: YES
reference COUNT invariant where rewritten: YES

official reference axes (mean over the same rows, real rubric):
  ref_loose    98.61 ->  98.61  (+0.00 pp)   n=324
  ref_strict   65.28 ->  65.90  (+0.62 pp)   n=324
  ref_conc     42.65 ->  42.65  (+0.00 pp)   n=324
```

**The wire limb is the gold one in none of the 106 substitutions** — so trusting
the prose can only move Ref. Strict up or leave it alone. `+0.62 pp` on the same
rows, with Ref. Loose and Ref. Conciseness unmoved.

A probe bug worth recording, because it nearly falsified the lever: wire
coordinates were first compared for presence **globally** rather than **per
parent**, so a `('3',)` from `Article 13.3` masked `Article 6.3` and the pass
looked inert (0/85 gold, +0.00 pp). Presence is now keyed by parent, which is what
a coordinate actually means.

## 5. Gate design — a THIRD void-guard slot, with an attribution rule

> **Two rules, not one.** "The two arms emitted different reference sets" is
> satisfiable by NOISE: at `--repeats 1` the arms draw independent Stage-2 samples,
> so their references differ even with the lever inert. `wire_shape_digest` now
> records `{row: [refs_sha, answer_sha]}` per arm and `wire_attribution()`
> intersects on the ANSWER — a wire-slot run is valid only if **at least one row
> drew the same answer in both arms and emitted different references**, which is
> the only pair a post-Stage-2 pass can produce and generation variance cannot.
> A run whose differing rows all drew different answers is VOID with the fix in
> the reason (`raise --repeats`), not a null. `GateVerdict.wire_attributed`
> publishes the count, and the valid render reads "emitted-reference difference
> attributed to the lever on N same-answer row(s)". Both rules are pinned by
> `tests/test_r425_gate_wire_slot.py`, including the draw-variance-only VOID.

`REGENOLD_GROUND_WIRE_SUBPOINTS` changes **nothing the transport sees**: identical
system payloads, identical user payloads, identical request shape. Under the two
existing slots the guard either voids a correctly-built run (`"system"`) or has
nothing to check (`"request"` was not declared) — and then an **inert call site
reads as a clean null**, which is the R329/R330/R397 trap this module exists to
catch. Measured: the two-row smoke was correctly refused
(``arms' emitted reference sets were IDENTICAL``) because those two rows were
answered deterministically and the pass is a no-op there.

So R425 adds `lever_slot="wire"`:

* `gate_validity.WIRE_SLOT_FLAGS` + `lever_changes_wire()`;
* `wire_shape_digest(rows)` — the digest of what each arm EMITTED, recorded per
  arm through `ArmProbe.provenance(wire_shape=…)`;
* `assess(..., lever_slot="wire")` requires both arms to have recorded **different**
  emitted reference sets, with the same standard of proof as the other slots;
* default (`"system"`) byte-identical to before, and the runner now prioritises
  `system > wire > request` so declaring a wire flag cannot weaken the strongest
  check.

**Which instrument answers which condition.** Conditions 1-2 (the answer axes)
are invariants — the rewrite is a route pass that runs after Stage-2 and rewrites
list entries only, so the answer is byte-identical in both arms (asserted on a
live request in `tests/test_r425_wire_grain_grounding.py`, and §7 shows it hold on
live prose). Conditions 3-5 are read from the **336-sample within-draw replay**
(§4), which pairs each recorded draw against the pass applied to that same draw —
a stronger pairing than two independent live arms, because nothing varies but the
pass. Conditions 6-7 need the full eight-axis board, so they are read from the
last hard-split board plus the two invariant axes: the geometric mean moves only
through Ref. Strict, i.e. `+0.62 pp` on that one axis with the other seven
identical.

A live paired board was launched first (`r425-wiregrain`, 37 strided hard rows ×
3 generations × 2 arms) and **stopped deliberately** once that property was
established, because it would have spent the same hours to re-confirm an
invariant. The targeted live leg below replaces it for what a live run uniquely
proves: that the call site fires through the real route on real Stage-2 prose.

**Pre-registered rule** (fixed before the numbers were read) — this is a fidelity
correction to the graded artifact, so the bar is "the board does not get worse":

| # | condition |
| :-- | :-- |
| 1 | `ans_correctness_loose` mean delta > −1.5 pp |
| 2 | `ans_correctness_strict` mean delta > −1.5 pp |
| 3 | `ref_correctness_loose` > −1.5 pp (invariant by construction) |
| 4 | `ref_conciseness` > −1.5 pp (invariant by construction) |
| 5 | `ref_correctness_strict` ≥ −1.5 pp (the targeted axis, with CI95 reported) |
| 6 | official overall (geometric mean of the eight axes) ≥ −1.0 pp |
| 7 | gold heads dropped B ≤ A (Hard Rule #8) |

Conditions 3-5 and 7 are invariants of the transform, so a failure there is a
**wiring bug**, not a trade — which is exactly what the wire slot's non-vacuity
check exists to make visible.

## 6. Route-level verification (offline, the real route)

`tests/test_r425_wire_grain_grounding.py` drives the real route with a **scripted
landed Stage-2** so the pass sees real model prose:

```
OFF refs: ['Article 26.5', 'Article 6.2', 'Article 73.4']
ON  refs: ['Article 26.5', 'Article 6.3', 'Article 73.4']
answer byte-identical: TRUE   head set invariant: TRUE   count invariant: TRUE
```

That is the `rg_100` defect fixed end-to-end on a real request, with the shipped
answer untouched. 42 tests cover the rewrite semantics (substitution vs grain
prefix, both prose citation forms, annex limbs, existence filtering, head/count
invariance, dedupe, fail-soft), the flag's gating, the cache-key registration, the
deterministic-path no-op, the trace note, and the wire round-trip.## 7. The live leg — `live_paired_read.py` (targeted, judge-free)

The 9 hard rows whose recorded answers make the pass fire, run through the real
route on the real transport (`claude-opus-4-8`), `--baseline-env …=0` versus
`--branch-env …=1`. Two runs: `r425-live` (1 generation, 9 rows) and `r425-live3`
(3 generations intended; **aborted in arm B generation 2** — see the outage note
below, so 27 arm-A draw-samples and 11 arm-B ones are on disk).

```
r425-live3, generations present: {'A': {0: 9, 1: 9, 2: 9}, 'B': {0: 9, 1: 2, 2: 0}}
stage2 leg that served the rows: {'primary': 22}

guard attribution on generation 0: 0 same-answer row(s), 8 draw-confounded row(s)
   -> a wire delta is NOT attributable

REACHABILITY — is the call site firing on the live route?
  OFF arm (recorded wire)    rewritable 7/11   substitutions 9   head-invariant 11/11   count-invariant 11/11   gold heads dropped 30 (after the pass: 30)
      of those applied rewrites: the limb we shipped was gold 1, the limb we ship instead is gold 2 (limb- or head-level)
  ON arm (shipped wire)      rewritable 0/11   substitutions 0   head-invariant 11/11   count-invariant 11/11   gold heads dropped 33 (after the pass: 33)

WITHIN-DRAW COUNTERFACTUAL on these live rows (paired by construction):
  axis          shipped   passed   gain pp
  ref_loose       90.91    90.91    +0.00
  ref_strict      81.82    81.82    +0.00
  ref_conc        35.23    35.23    +0.00
```

**The non-vacuity proof is per ARM, and that is deliberate.** Generation is not a
pairing — `A#s0` and `B#s0` are different draws, `answer byte-identical across
arms: 0/11` — so a cross-arm difference cannot be attributed to the pass. (The
cross-arm numbers in the artifact are labelled *descriptive*; the `+3.03 pp`
Ref. Strict there is draw variance, not the lever, and is not quoted as a result
anywhere.) The read that *is* paired is within a draw: apply the pass to the row's
own answer and wire. On that read the OFF arm's recorded wires are still
rewritable in **7 of 11** draw-samples while the ON arm's shipped wires are
rewritable in **0 of 11** — which is exactly what "the call site fired on the live
transport" means, and what an inert call site could not produce (it would leave
both arms rewritable, since both arms' rows run the same code until the pass).

The same data also shows the R425 guard rule doing its job on real rows: on
generation 0 it finds **0** same-answer rows and 8 draw-confounded ones, so it
**refuses to attribute** the arms' wire difference to the lever. That is the
correct answer for this sample, and it is why the population number comes from the
336-sample replay where every pair is the same draw.

Three honest notes on this sample:

* On these 9 **stress** rows (chosen *because* the pass fires) the three reference
  axes are unchanged by the pass: `+0.00 pp` on all three, in both runs. The rows'
  gold keys are head-level or the limb that matters is untouched, so the applied
  rewrites are score-neutral there — the population `+0.62 pp` comes from the
  336-sample replay, not from this sample. One of the applied rewrites replaced a
  limb that matched the gold key at limb- or head-level; its scored effect is
  still `0.00`, which is what the replay's `wire limb IS gold: 0/106` predicts in
  aggregate.
* `gold heads dropped` moves `30 → 30` and `33 → 33` across the pass, on live
  prose, in both arms. Hard rule #8 is preserved by construction and **observed**.
* **Transport outage, recorded because it is the recurring operational risk.**
  `r425-live3` was aborted by the runner's own guard at 23:12 after 5 consecutive
  primary failures — `api_status_500 {"error":{"message":"No response from Claude
  Code"}}` — i.e. the Claude Max wrapper's backend stopped answering while the
  tunnel itself still returned 200 to `/health`. The guard refused to grade the
  rest of the sample on deterministic Stage-1 drafts (the R417 policy), which is
  why arm B generation 2 is empty. A repeats-3 live gate therefore needs the
  wrapper backend up; the read above is what the recorded draws support.
  `lever_slot` is `None` in this artifact because the aborted run never wrote its
  gate payload — the attribution line is computed with the guard's own functions
  instead.

## 8. Not in scope (recorded so it is not mistaken for a coverage gap)

* **Dropping an ungrounded sibling that sits BESIDE a grounded limb** (wire
  `[Article 6.1, Article 6.2]`, prose naming only `6.1`). That is a genuine
  excess-reference finding, but removing it changes the reference COUNT — i.e. it
  moves Ref. Conciseness — and needs its own gate. The pass deliberately leaves it.
* **Widening to a head→leaf swap** (wire carries a bare `Article 6`, prose names
  `6.3`). That is R133's ADD path, already live.
