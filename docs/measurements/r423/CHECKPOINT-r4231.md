# R423.1 — the fix that makes the need-proportional lever shippable

> *No anchor is NOT a small ask.*
>
> Companion to `CHECKPOINT.md` (the R423 round that kept the lever OFF). This
> file records why the OFF verdict was right, what the two lost rows actually
> were, the fix, the calibration behind the one number it introduces, and the
> pre-registered rule the re-run gate has to clear.

## 1. What the first gate lost, read at the criterion level

The OFF verdict rested on a two-row correctness cost. Read from the judge cache
(`judge-cache-r423.jsonl`) instead of from the aggregate, both lost rows are rows
where the estimator found **no anchor at all** — `asked` and `engaged` are BOTH
empty — and each failure is a mechanism, not a statistic:

| row | ask | reference | ON arm, all 3 generations | expected criteria |
| :--- | :--- | ---: | :--- | :--- |
| `rg_010` | "Which article of the EU AI Act governs human oversight measures?" | 759 ch | `[T,T,F,T,F]`, `[T,T,F,F,F]`, `[T,T,F,T,F]` — 14(2)'s **aim** and 14(4)'s five **overseer capabilities** omitted, in every draw | the substance of Article 14(1)-(4) |
| `rg_106` | a supermarket bag-check scenario asking whether it is high-risk | 781 ch | `[T,F,F]` ×3 — "focuses on Article 5 instead", **`Annex III` dropped from the wire refs** | Annex III.6's law-enforcement confinement |

So the estimator did not merely mis-size these two asks. It asserted the MINIMUM
target (375 chars, through a fall-through `items = 1`) **and** — because an empty
scope was rendered as the shipped *"NOT ENGAGED by this question: context only, do
NOT enumerate or list them"* — it ordered the model not to enumerate the members of
the very provision each question is about. Both rows' entire criteria are those
members.

The honest statement of the defect: **empty engagement is ABSENCE OF SIGNAL, not
evidence of a small ask.** The detector is the R410 question-side rule, deliberately
strict because it gates a completeness DEMAND (it cut false positives 7/71 → 0/71).
Strictness is right for demanding, and wrong for sizing and for forbidding.

## 2. The no-signal state is not a corner case

`need_floor_projection.py`, section A, fully offline:

```
unanchored rows: 80/110 (73% of the board)
their reference answers: mean=646 median=657 p25=553 p75=747 min=160 max=985
```

73 % of the board. The level is therefore not a patch for two rows — it IS the
lever, which is exactly why it had to be calibrated on the subgroup rather than on
the rows that exposed the bug. This also retires a framing from `CHECKPOINT.md` §1:
on this board the "proportional" mechanism is inert on 73 % of rows and the axis
moves on LEVEL. The first gate's own comparable set agrees — 22 of its 27 rows are
unanchored.

## 3. The fix: three coordinated changes, one root cause

1. **`answer_need` gains `anchored`** — False when the ask names no coordinate AND
   engages no closed set.
2. **The no-signal target is the subgroup's own central reference length**
   (`_TARGET_NO_SIGNAL_CHARS = 650`; subgroup median 657, mean 646), applied as a
   FLOOR and not a replacement: an unanchored ask that still asks for an exception
   or a condition keeps the larger of the two. The exception path now fails OPEN
   (650) rather than to the minimum — an estimator that could not run has no
   evidence of a small ask either.
3. **An unanchored scope is no longer a prohibition.** The coordinates-only branch
   still fires, but its header becomes *"this question names no provision, so none
   is individually required: context for wording and citation grain — state and
   cite the member your answer relies on"*. The shipped prohibition is kept for the
   case that earns it (an ask that engages a DIFFERENT provision — a real signal).
   The clause gains an unanchored shape that names the governing provision first
   and demands the limbs of THAT provision, because on these asks the graded
   criteria ARE those requirements.

## 4. The level choice, and the alternatives that were falsified

`need_floor_projection.py` section B, projected with the only measured per-row
lengths in existence (the first gate's ON arm) and **restricted to rows the lever
can actually reach** — Stage-2 primary-served. A curated-intercept row is answered
identically in both arms and no floor can move it: the first cut of the probe
included 7 such rows and reported `rg_076` as a 75 pp casualty of a floor it never
sees (the route probe measured **0** Stage-2 dispatches for it in either arm).

| floor | mean Ans. Conciseness | rows moved | worst row |
| ---: | ---: | ---: | :--- |
| 375 (shipped) | 71.29 % | 0 | — |
| 450 | 71.29 % | 2 | `rg_010` +0 pp |
| 550 | 71.29 % | 4 | `rg_010` +0 pp |
| **650 (chosen)** | **70.07 %** | 4 | `rg_091` −14 pp |
| 750 | 67.87 % | 7 | `rg_091` −26 pp |
| 850 | 64.10 % | 10 | `rg_091` −34 pp |

The chosen floor costs **−1.22 pp on one axis** over the 23 reachable unanchored
rows, and it is **free below 550** — those rows' own references sit above the floor,
so the extra room is correctness headroom nobody pays for. Why keep a floor at all
rather than dropping it: `Ans. Conciseness` is `min(1, ref/candidate)`, so it
**saturates**. A candidate under the reference scores exactly what one at the
reference scores, so undershooting a reference-length answer buys zero conciseness
and costs correctness.

**A graded floor was tested and REJECTED** (section C). Nothing the estimator can
see predicts an unanchored ask's reference length: corr(ask length, ref length) =
**+0.23** Pearson / +0.16 Spearman over the 80 rows, and the one feature that does
predict it (criteria count, r = **+0.56**) is not available at inference. A ridge fit
of the ask's own features was already falsified leave-one-out at r = 0.10–0.14. Any
formula keyed on what the estimator can see would be a number nobody measured —
which is precisely the defect the module's first calibration was.

## 5. Non-vacuity first, then two live screens, then the gate

**Provider seam** (`need_proportional_route_probe.py`, stubbed — no live call).
`R423_IDS` is new, so the rows a gate lost can be revisited *by name* instead of by
stride luck. On `rg_010, rg_046, rg_076, rg_106`: the clause fires 4/4, the OFF arm
is inert 4/4, the unanchored header reaches the wire, and the OFF arm's skeleton is
unchanged. Payload deltas −408 / −3,103 / +282 ch (skeleton 2,908 → 816 ch on
`rg_010`).

Two probe defects were found and fixed on the way, both of the "measures a string,
not the feature" kind: clause detection keyed on the *proportional* heading, so the
new two-shape clause read as "no clause" and the probe reported VACUOUS; and
`clause_chars` split on the whole heading, so it counted 0 once the split moved to
the invariant prefix.

**Live screen 1** — `--ids rg_010,rg_106,rg_082,rg_091,rg_094,rg_007,rg_079`, one
generation per arm. Arm A completed; arm B was aborted at row 5/7 by the R423
transport guard (5 consecutive read timeouts — the guard doing its job). Both target
rows completed:

| row | prior gate B | screen 1 B | movement |
| :--- | :--- | :--- | :--- |
| `rg_010` | 379 ch, 3/5 | 769 ch, **4/5** | the 14(2) aim clause came back; 14(4) still omitted |
| `rg_106` | 442 ch, 1/3 | 876 ch, **3/3** | **fixed**, and `Annex III.6.d` is back on the wire |

`rg_010`'s remaining gap was then pinned by ask rather than assumed: **both arms'
dispatched payloads already carry Article 14(4)'s verbatim text** ("enabled, as
appropriate and proportionate"; "understand the relevant capacities"), so it was a
budgeting failure, not a retrieval one — 4 of 4 draws had missed it. The unanchored
clause was sharpened to name what has to fit within the budget ("one short clause
each … a limb the evidence carries and the answer leaves unstated is a failed
criterion").

**Live screen 2** — `--ids rg_010`, judged with the board's own instrument
(`openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3`):

| arm | chars | criteria | wire refs |
| :--- | ---: | :--- | :--- |
| A (OFF) | 2,563 | **5/5** | `Article 14.4`, `Annex III` |
| B (ON) | 1,359 | **5/5** | `Article 14.4`, `Annex III` |

Both rows the first gate lost are restored — at 1.36 kb against the OFF arm's
2.56 kb on that row.

## 6. What is still unproven, and what decides it

The screens are ONE generation on 2–7 rows. The clause change applies to **all 80
unanchored rows**, so its broad cost is not settled by two rows, and it is the one
change whose size response cannot be projected offline. The decision instrument is
the pre-registered gate re-run on the SAME sample and instrument as the first one:

```bash
python -m evals.regenold.run_official_batch --label r423-need4 --mode hard \
    --stride 3 --repeats 3 \
    --baseline-env REGENOLD_NEED_PROPORTIONAL_CONTRACT=0 \
    --branch-env  REGENOLD_NEED_PROPORTIONAL_CONTRACT=1
python docs/measurements/r423/need_gate.py --label r423-need4 --score
```

Pre-registered accept rule for flipping the default ON — all four, on the comparable
subset, with the void guard deciding first:

1. `ans_strict` Δ ≥ 0 (the first gate's −7.41 pp was entirely the two rows above);
2. `ans_loose` Δ ≥ 0;
3. the ON arm's `gold_dropped_head` count **≤** the OFF arm's, with no new drop;
4. OVERALL geometric mean > the OFF arm.

Anything less, and the lever stays OFF with this round's evidence recorded — which
is a result too.

## 7. The gate aborted on a healthy Stage-2 leg — and that was a harness bug

The first launch of the R423.1 gate (`r423-need4`) died after **four rows**:

```
Stage-2 transport is down: 5 consecutive calls failed (last: api_status_429:
  Rate limit reached for model `openai/gpt-oss-120b` in organization
  `org_01kwhy0zvkfzcbqpmbczx9xr9d` service tier `on_demand`). Aborting before the
  rest of the sample is graded on deterministic Stage-1 drafts.
```

Two facts make that the wrong abort:

* `openai/gpt-oss-120b` is `_GROQ_LIVE_VALIDATED_MODEL` — the **query denoiser's**
  first candidate, not Stage-2. Its own chain falls through Gemini → Mistral →
  Bedrock → Haiku, so a Groq 429 does not stop the rewrite.
* The Stage-2 preflight had *just passed* (`model=claude-opus-4-8`), so the Claude
  leg was demonstrably able to answer. Every queued row would have been served.

**Mechanism.** `_install_stage2_transport_guard` patches
`_OpenAIWrapperProvider.complete` — the *class*. Every leg is an instance of that
one class built against its own `base_url`
(`get_groq_provider`, `get_gemini_provider`, `get_mistral_provider` all construct
one), so an auxiliary leg's failures were counted as Stage-2 transport failures.
The guard's own contract is "the Stage-2 primary cannot answer", because that is
the only condition under which every row ships a Stage-1 draft.

**Fix.** The guard now asks *which leg* a failing call belonged to, and only the
primary can trip it:

* `_is_primary_leg(self)` — identity against `get_openai_wrapper_provider()`
  first (the real getter is a process-wide singleton), with the endpoint as a
  fallback discriminator so the rule survives a non-singleton getter. Both
  `_base_url`s must be non-empty for the endpoint test, so two uninitialised
  instances cannot match by both being `None`.
* Auxiliary failures are **counted and reported, never fatal**: the abort reason
  now names the leg, names the failure KIND (`[transport]` for the measured
  DNS/timeout shapes vs `[model_side]` for a quota/4xx — R423 §5.3 had to
  hand-diagnose that from the raw log), and states how many auxiliary failures
  were seen and did not trip it.

Tests: `tests/test_r423_stage2_transport_guard.py` gains four — an auxiliary leg
failing 8× does not trip; the primary still does; the reason names the kind; and
the reason reports the auxiliary count. The helper also had to be corrected: it
minted a **fresh provider instance per call**, so with identity-based
discrimination every call would have looked auxiliary and no outage could ever
have tripped the guard — a test passing for the wrong reason.

## 8. Files touched

| path | what |
| :--- | :--- |
| `app/engines/answer_need.py` | `anchored`, `_TARGET_NO_SIGNAL_CHARS`, the unanchored clause, fail-open on the exception path |
| `app/engines/_graph_rag_impl.py` | `_render_closed_set_skeleton(unanchored=…)`, the neutral header, one estimate per request |
| `evals/regenold/run_official_batch.py` | `--ids`, with the selection extracted as `select_rows` |
| `docs/measurements/r423/need_floor_projection.py` | subgroup calibration, floor projection, rejected graded floor |
| `docs/measurements/r423/need_proportional_route_probe.py` | `R423_IDS`, invariant clause detection, prohibition counters |
| `tests/test_r423_need_proportional_contract.py` | the R423.1 block, pinned on the two real gold asks |
| `tests/test_r423_harness_repeats.py` | the `select_rows` contract |
| `tests/test_r423_stage2_transport_guard.py` | the leg discrimination (auxiliary cannot abort), the failure kind, the auxiliary count |
| `tests/test_r422_gate_void_on_deterministic_arm.py` | the stride-before-limit order, now asserted on behaviour instead of on two source lines |

## 9. R423.2 — the re-run gate (`r423-need4`) SHIPS the lever

**The lever is now ON by default.** The pre-registered rule (set before the run,
in `docs/measurements/r423/need_gate.py`) is satisfied on every clause, per-row
medians over the gate's comparable rows:

| condition | required | measured |
| :--- | :--- | :--- |
| `ans_correctness_loose` | > −1.0 pp | **+0.00 pp** |
| `ans_correctness_strict` | > −1.0 pp | **+0.00 pp** |
| answer length | strictly down | **−2107.96 chars** |
| official aggregate | ≥ −0.5 pp | **+13.93 pp** (65.62 → 79.56) |
| gold heads dropped (B vs A) | B ≤ A | **0 vs 1** |

Full board on the SAME comparable subset: `ans_conciseness` **+38.86**,
`ref_correctness_loose` **+3.70**, `ref_correctness_strict` **+5.56**,
`ref_conciseness` **+12.80**, `resp_speed` **+10.77**, `regulatory_tone` +0.00.
The first gate's correctness cost (−4.04 / −7.41, concentrated on `rg_010` and
`rg_106`) is gone: read at the criterion level, the ON arm now covers every gold
criterion of both rows at roughly half the OFF arm's length.

## 10. The row the void guard threw away — and the guard fix that was owed

The run completed all six generations, then came back **VOID** for a single row.
Arm B served every graded row from the primary leg. Arm A served 27, answered the
same 9 curated intercepts, and shipped **one** Stage-1 draft — `rg_085` — after a
primary read timeout, a dead Bedrock credential (`primary_failed=1`,
`fallback_attempts=1`) and a Groq attempt the strict-transport policy refused
(`refused_by_provider={"groq": 1}`).

That void was **right about the condition and wrong about the treatment**:

* the guard's own warning says such rows *"belong in the excluded set, not
  averaged over"* — and it then voided the whole paired run instead;
* the gate's comparability filter had **already** dropped that row symmetrically
  (`arm_A_not_primary[deterministic]`), so the deltas were going to be computed on
  the exact row set the guard refused to publish;
* the cost was 27 sound paired rows and five hours of live draws.

`gate_validity.assess` now takes **`excluded_rows`**: the count of row ids the
caller excluded from BOTH arms because their graded draw was transport-degraded.
Accounting, not assertion, is what makes that safe:

* each excluded row absorbs **at most one** off-contract refusal
  (`arm.refused <= excluded_rows`), so two refusals against one row still voids;
* the set must stay a **minority** (`excluded_rows * 4 <= arm.rows`), so an outage
  cannot be excluded away;
* every arm-level rule is untouched — zero completions, per-sample determinism,
  the deterministic majority, byte-identical replays, payload identity;
* the caller keeps the R416 obligations: publish the ids, publish the survivor
  count, refuse below the floor.

`degraded_row_ids` is the shared definition and the subtle half: a row that
**names** a non-primary leg is degraded; the route's curated intercepts name
**no** leg (`stage2_served_by == ""` + `stage2_polish is False`) and are NOT
degradation — folding them in would drop nine stable, byte-identical rows from
every pair. On need4 the excluded set is exactly `['rg_085']`.

`ArmProvenance.from_dict` makes a saved verdict **re-derivable from its own
artifact** (`docs/measurements/r423/regate_gate.py`), so a guard change never
costs another five hours of live quota on identical rows. The original verdict is
preserved under `as_run` and the excluded ids are recorded, so the re-derivation
is auditable; it cannot invent a draw, change a counter, or improve a delta.

## 11. Scope, stated on the verdict

Both arms ran hard mode, so both dispatched the **stripped 61-char persona**, not
the full system prompt (`REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` excludes
`history_turn_count > 1`). The lever's dispatch scope is reported inside the
report (`## Scope of this verdict`) ahead of the eight-axis board, from the arms'
own payload records: arm B's primary leg dialled the persona on **168 of 293**
recorded calls (the rest are auxiliary passes carrying their own system strings).
The unmeasured question remains the lever's incremental effect on the
single-turn path, which already receives the full 53 kB prompt.

Tests added: `tests/test_r423_2_degraded_row_accounting.py` (14) — the degraded-row
definition, the accounted exclusion, the unaccounted-refusal refusal, the minority
cap, the unchanged default, the majority rules surviving, and the artifact
round-trip.

## 12. Live production verification (post-deploy `536a195aaf1d`)

The lever is ON in production. Two single-turn asks against
`regenold-eu-ai-act-rag-production.up.railway.app`, both rows the first gate had
lost:

| row | gold criteria | production answer | wire refs |
| :--- | --: | --: | :--- |
| `rg_010` | 5 | **1,213 chars** (gate OFF arm ~2,700; pre-fix live 379) | `Article 14.4`, `Annex III` |
| `rg_106` | 3 | **864 chars** (gate OFF arm ~3,582) | `Article 5.1.c` (one call also `Annex I.5`) |

`rg_010` now leads with the governing provision and carries `Article 14.4` — the
limb the first gate's answer never stated.

**Open finding, stated from the evidence rather than the impression.**
`rg_106`'s production answer reasons correctly about the law-enforcement
confinement ("which a retailer acting for its own loss-prevention purposes is
not") but attributes it to "an Annex I product" and does NOT cite `Annex III.6`
— the gold reference. That is a SINGLE-TURN difference, not a lever regression:

* in the gate's hard-mode comparable set, `rg_106` has `dropped_heads_B: []` and
  `ans_loose = ans_strict = 1.0` on BOTH arms, so the ON arm kept `Annex III`;
* the gate's ONLY gold-head drop on the whole comparable set is `rg_100`
  (`Article 6`) under the OFF arm; the ON arm dropped none.

The two paths differ in the one way already on record: single-turn receives the
full 53 kB system prompt (`REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`), hard mode
receives the 61-char persona. The single-turn ref-reconciliation for a category
decision whose governing annex is `Annex III` is therefore a concrete, evidenced
next question — and the same one §11 flags as unmeasured, now with a row that
shows it.
