# R431 — the sibling-limb sub-point deficit: what it actually is, and what repairs it

**Headline.** R429's own checkpoint named the next lever as *"135 of the remaining
unmet gold sub-points name a **sibling limb** the prose doesn't name either, which is
generation-side prompting work"*. Re-measured per draw and per row, **that
attribution is wrong**, and the largest bucket turns out to be fixable downstream of
generation. The wire-side repair ships: **Ref. Correctness (Strict) +3.76 pp** on 554
recorded draws (**+5.30 pp** on the R419 board), at **+0.00 pp Ref. Loose** and
**−0.61 pp Ref. Conciseness**, with the folded head set invariant on every row.

Two candidate repairs of the *substitution* arm were built, measured and **rejected**.
They are recorded in §5 so they are not re-proposed as obvious wins.

---

## 1. The framing R429 handed over was wrong

`docs/measurements/r431/sibling_triage.py`, on today's board, **per draw**:

| bucket | count |
| :-- | --: |
| unmet gold expectations | 173 |
| `named_sibling_on_wire` — the prose **does** name the gold limb; the wire carries a sibling of it | **85** |
| `sibling_not_named` — the prose names neither | 50 |
| `coarser_on_wire` — R429's remit | 29 |
| `unnamed_no_coord` | 7 |
| `named_but_no_coord_of_parent_on_wire` | 2 |

So the dominant bucket is **not** generation: in 85 of 173 the answer already names the
coordinate the key wants and the **wire** ships a different limb of the same parent
(`rg_100` names `Article 6.1`, `6.2` and `6.3` and ships only `6.2`). Only 50 are
"the prose never names the gold limb", which is the genuinely generation-side set.

**Per row** (the board's own denominator) the picture is much smaller than either
number suggests: of 28 rows with a landed draw, 16 are met in every draw, 11 are
draw-dependent, and only **5 are structural** (met in no draw).

## 2. Why the existing pass abstains there

`_ground_wire_subpoints` is **1:1 in place**. Its substitution arm fires only when the
prose names a limb *other* than the wire's; when the prose names the wire's limb too,
it abstains by contract. The wire is therefore narrower than the answer's own prose,
and the missing limb is exactly the gold one.

## 3. The repair: an ADD, gated on precision

`REGENOLD_GROUND_WIRE_ADD` (**default ON**, in `_engine_cache_key`). The pass appends
the limbs the answer's prose names that the wire lacks, subject to three constraints:

* the coordinate's **parent is already on the wire** — so the folded head set, and
  therefore Ref. Correctness (Loose), cannot move;
* `coordinate_exists` — it never mints a coordinate the Regulation lacks;
* **both the answer AND the question** must discuss the limb's *own* statutory text
  above calibrated floors.

### 3.1 The tariff, measured — `add_threshold_sweep.py`

Per-limb precision is only a proxy; the board reads three axes, one of which can only
gain and one of which can only lose. Swept over the recorded corpus with the real
rubric (554 rows), `dGeo` = the implied 8-axis geometric-mean movement:

| answer ≥ | question ≥ | adds | gold | precision | ΔStrict | ΔConc | ΔGeo |
| --: | --: | --: | --: | --: | --: | --: | --: |
| 0.0 | 0.0 | 501 | 118 | 23.6 % | +8.84 | −7.49 | **−0.80** |
| 0.4 | 0.0 | 433 | 114 | 26.3 % | +8.39 | −6.50 | −0.59 |
| 0.7 | 0.0 | 255 | 90 | 35.3 % | +7.34 | −3.42 | +0.07 |
| 0.9 | 0.0 | 134 | 62 | 46.3 % | +5.05 | −2.04 | +0.14 |
| 0.5 | 0.4 | 55 | 35 | 63.6 % | +3.76 | −0.61 | **+0.32** |
| **0.6** | **0.4** | 55 | 35 | 63.6 % | +3.76 | −0.61 | **+0.32** |
| 0.7 | 0.4 | 53 | 35 | 66.0 % | +3.76 | −0.59 | **+0.32** |
| 0.6 | 0.5 | 29 | 25 | 86.2 % | +2.26 | −0.35 | +0.20 |

Two things this settles:

* **The unfiltered ADD is net negative** — 501 additions at 23.6 % precision would take
  Ref. Conciseness from 40.8 to roughly 33 and lose more overall than the strict gain
  is worth. It is falsified, not "off by default".
* **The question floor is load-bearing, and it is not luck.** The whole `q = 0.0`
  column never reaches the plateau even at a 0.9 answer floor (+0.14 vs +0.32): the
  answer's own text cannot substitute for the question's. The optimum is a **plateau**
  — three adjacent cells tie at +0.32 — and the shipped default `(0.6, 0.4)` sits on it.

### 3.2 What it does — `wire_add_probe.py`

554 recorded rows (R419 board + strided hard captures), real rubric:

| axis | OFF | ADD | Δ |
| :-- | --: | --: | --: |
| Ref. Correctness (Loose) | 92.33 | 92.33 | **+0.00** |
| Ref. Correctness (Strict) | 73.13 | 76.90 | **+3.76** |
| Ref. Conciseness | 40.78 | 40.17 | −0.61 |

R419 board only (110 rows): Loose 87.27 → 87.27 (+0.00), **Strict 65.15 → 70.45
(+5.30)**, Conc 38.31 → 37.46 (−0.86).

Construction guarantees, **asserted per row rather than argued**: **0** folded-head-set
violations, **0** Ref. Strict regressions, max append on any row **1** (cap 2),
53 rows fired / 53 coordinates appended / 35 gold (**66.0 %**).

> A note on the head invariant: it is a **set** invariant, *not* a multiset one, and
> that is not a convenience. `reference_correctness_loose` reads `set(_heads(pred))`;
> the first version of this probe asserted multiset equality and reported **53 false
> violations**, every one of them a correct append of a second reference under a head
> already present.

## 4. The live gate

`docs/measurements/r431/wire_add_gate.py`, verdict in `gate-verdict.json`.

### 4.1 Result — **9/9 PASS, SHIP**

| axis | OFF | ON | Δ | 95% CI (seeded) |
| :-- | --: | --: | --: | :-- |
| Ref. Correctness (Loose) | 100.00 | 100.00 | **+0.00** | [0.00, 0.00] |
| Ref. Correctness (Strict) | 80.86 | 84.57 | **+3.70** | [+0.00, +11.11] |
| Ref. Conciseness | 44.88 | 44.75 | −0.12 | [−0.37, +0.00] |

27 comparable hard rows across **three independent generations**. The lever fired on
**3 rows**, appending **6 coordinates, all 6 of them gold**; Ref. Strict moved up on
1 row and down on none. Asserted per row-sample rather than argued: **0** folded-head-set
violations, **0** met→unmet regressions, **0** append-cap violations, gold heads
dropped unchanged at 0. Appended: `rg_034 +Article 101.5` (all generations),
`rg_055 +Article 5.1.h.ii`, `rg_082 +Article 24.3`.

### 4.2 The draw is short of its pre-registered length — and the harness was fixed

The design is three generations. The primary leg (`claude-code` upstream) began
returning HTTP 500 with `No response from Claude Code` on every call part-way through
generation 3, and the harness's transport guard aborted the sample at 12/37.

**That abort was too blunt and is now fixed.** The guard exists for one condition — the
rows stop being served by a *Stage-2 leg* and the batch would grade deterministic
Stage-1 drafts — and a tripped primary is not that condition while the Bedrock fallback
is answering. `_install_stage2_transport_guard` is now **leg-aware**:

* the **preflight** no longer refuses the run when the primary probe fails; it probes the
  fallback (`bedrock_client.check_connectivity_and_permissions`, the same probe chain
  the fallback leg dials) and, if that answers, proceeds as a **fallback-served draw**,
  printing that in full rather than silently;
* the **mid-run guard** reads each row's own provenance. With the primary tripped and the
  row served by `stage2_served_by=fallback`, it warns once and continues — the wire is
  still Stage-2's, and the draw stays separable because every row records its leg;
* it still aborts when **neither** leg answers, which is the case it was written for.

Pinned by `tests/test_r431_fallback_leg_guard.py` (6 tests, driving the real installer:
continue-on-fallback, abort-when-no-leg, preflight returns `fallback:<model>`, preflight
refuses when neither answers, the probe is fail-soft, and the health checks receive the
row they just drew).

**The completed result:** the current reader uses all **three complete generations**
(`repeats: 3`, `repeats_pre_registered: 3`); the tolerance criteria were unchanged and
were not relaxed. The earlier 12/37 partial artefact remains provenance-only and is not
mixed into the score.

The reproduction command is:

```bash
python -m evals.regenold.run_official_batch --label r431-add --mode hard --stride 3 \
    --repeats 3 --resume --baseline-env REGENOLD_GROUND_WIRE_ADD=0
python docs/measurements/r431/wire_add_gate.py
```

### 4.3 Two defects the gate found in the READER, both worth recording

Neither was in the lever; both would have produced a wrong number, and both are now
pinned by the run itself.

* **Scope.** The first version checked the derivation licence over **every** row and
  refused on 4 of 74 samples (`rg_001`, `rg_025`). Those are the deterministic-leg rows
  — `stage2_polish: false`, `stage2_served_by: ""` — whose wire the route builds on the
  Stage-1 path and never submits to the wire passes, so `_ground_wire_subpoints` has no
  OFF state to reproduce there in the gate **or in production**. Checking them was a
  scope error in the reader. Transport integrity is now established first, on each row's
  own provenance, and both the licence and the comparison run on exactly that
  population: 54/54 fixed points.
* **An empty question.** The first version drove the pass with `question=""`. R431's ADD
  arm reads the question as its second vote, so `q_recall` was zero for every candidate
  and the gate reported the lever **inert on 27 of 27 rows** — a clean-looking null
  result produced entirely by the reader. The offline tariff table would have caught it;
  the gate alone could not, which is precisely what the non-vacuity criterion exists
  for, and it is the reason a null result here is refused rather than reported.

The lesson is recorded rather than the fix alone: both failures were silent, and in each
case the gate's own criteria — not the axis deltas — are what surfaced them.

### 4.4 Earlier live check on the deployed build — and what it found

After the merge (`f50b2c8d2cb8` serving), four hard-split questions were asked on the
deployed service with `include_reasoning=true`. **Every row came back
`stage2_served_by=deterministic`**, with `cache_skip_degraded_serve=deterministic` in the
trace. So the deployed build has **no working Stage-2 leg either** — the wrapper upstream
is returning 500 and the deployed Bedrock leg is not answering — and it is answering from
deterministic Stage-1 drafts.

Two consequences, stated plainly:

* **The R431 lever is a no-op on those rows, by design.** They are the population §4.3
describes: the pass does not own a wire that never entered it, so the curated / Stage-1
wire stays byte-identical. This is the scope correction being exercised in production,
not a failure of the lever.
* **The provenance work is doing its job.** The degraded serve is visible per row in the
trace and suppresses the cache write, so a Bedrock-degraded answer cannot be replayed
after the leg recovers. Without it, this state would have been indistinguishable from a
healthy run — which is exactly the failure R292/R418 were written to prevent.

A live behavioural demonstration of the append therefore needs one leg restored; the
offline probe (554 rows) and the paired gate are the standing evidence until then.

### 4.5 Design


**One live arm, both lever states derived.** The pass runs *after* Stage-2 lands and
edits only `references`; it cannot change the answer text, so the judged axes cannot
move and the three reference axes are computed from the emitted list with no LLM. A
second live arm would buy only a fresh draw of the same row while making each arm's
answer an independent draw — importing generation noise the lever is not responsible
for. The R425 and R429 rounds reached the same conclusion independently.

The licence for the derivation is **checked, not assumed**: the arm is drawn with
`REGENOLD_GROUND_WIRE_ADD=0`, so the recorded wire *is* the OFF state, and re-running
the OFF pass on it must be a no-op on every row-sample. If any row-sample fails, the
reader refuses and reports no delta.

Pre-registered rule, fixed before the numbers were read: the lever must not be inert;
Strict ≥ −1.5 pp; Loose ≥ −1.5 pp; Conc ≥ −2.5 pp; head set invariant; appended count
in `[0, cap]`; 0 met→unmet; gold heads ON ≤ OFF.

## 5. Two repairs that were built, measured and REJECTED

The substitution arm has a real defect worth recording: on `rg_085` it replaces the
wire's `Article 6.2` — **which is the gold key** — with `Article 6.1`, destroying 11
gold keys across the corpus. That is a Hard Rule #8 violation inside the very
population R431 exists to fix, so it was worth trying to repair. Both attempts failed
on the tariff, and both were verified against the **implementation**, not a model of it.

* **Question-grounded veto** — abstain from substituting a limb the question relies on.
  At its only firing floor (0.2–0.3) it recovers all 11 keys but Ref. Strict falls
  **0.61 pp net**: it suppresses 43 substitutions that were winning. At 0.4 it never
  fires at all, because `q_recall('Article 6.2')` is **0.333**. Inert-or-negative.
* **Keep-and-add** — append the sibling instead of replacing, so the wire can never
  lose a limb. Strict **+0.74**, Conciseness **−4.18** across 318 converted slots →
  **−0.87 pp implied Overall**. Net negative.

Conclusion: R425's in-place replace is the right trade and the `rg_085` loss is its
price. A repair needs a signal that separates that row's limb from the 43 winning
substitutions; **the prose and the question both fail to**, so the deficit is recorded
as an open, characterised limit rather than papered over.

## 6. Files

| path | role |
| :-- | :-- |
| `app/routes/regenold.py` | `_ground_wire_add_enabled`, `_ground_wire_add_params`, `_limb_discussion`, `_coord_refines`, `_ground_wire_add_missing`; the rejected levers' record; the trace now reports appends |
| `tests/test_r431_wire_add.py` | 18 tests pinning the contract, the clamping, determinism, cache-key registration, and that the rejected levers stay out |
| `sibling_triage.py` | the bucket attribution in §1 |
| `add_threshold_sweep.py` | the tariff table in §3.1 |
| `wire_add_probe.py` | the axis deltas and construction guarantees in §3.2 |
| `wire_add_gate.py` | the live hard-split gate |
| `gate-verdict.json` | the gate's machine-readable verdict |

### Reproduce

```bash
python -m docs.measurements.r431.sibling_triage
python -m docs.measurements.r431.add_threshold_sweep
python -m docs.measurements.r431.wire_add_probe
python -m evals.regenold.run_official_batch --label r431-add --mode hard \
    --stride 3 --repeats 3 --baseline-env REGENOLD_GROUND_WIRE_ADD=0
python docs/measurements/r431/wire_add_gate.py
```
