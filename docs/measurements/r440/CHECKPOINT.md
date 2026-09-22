# R440 — branch-guard hard-cluster gate: RESULT

**Verdict (pre-registered rule applied): NO MEASURED WIN — keep
`REGENOLD_GROUNDED_BRANCH_GUARDS` OFF.**

The refuse rule came back **clean**: zero gold-head drops, zero answer-correctness
regressions, zero reference-loose loss. But no axis separates from zero in the ON
arm's favour on either read, and the one axis that *does* separate from zero
separates **against** it (answer conciseness). Under the rule fixed in
`PREFLIGHT.md` before the draw, that ships nothing. The lever stays default-OFF;
the code from PR #457 remains in the tree, unexercised.

This is a powered null, not an unmeasured lever.

## What was gated

The 21 frozen rows of the three failure clusters the R438 audit named
(`rg_002 rg_004 rg_007 rg_008 rg_026 rg_055 rg_058 rg_070 rg_073 rg_074 rg_075
rg_080 rg_081 rg_083 rg_088 rg_092 rg_101 rg_103 rg_106 rg_108 rg_109`), hard
mode, **3 samples per arm**, sequential arms, one process:

```
python -m evals.regenold.run_official_batch --label r440c-branch-cluster --mode hard \
  --ids "<21 ids>" --repeats 3 --allow-degraded-transport \
  --baseline-env REGENOLD_GROUNDED_BRANCH_GUARDS=0 \
  --branch-env   REGENOLD_GROUNDED_BRANCH_GUARDS=1
```

126 live generations. Scored with `evals.official.score_arm` against the n=110
refkey and the R436 judge identity
`bedrock:qwen.qwen3-235b-a22b-2507-v1:0:t=0.1:grouped:r=3` (concurrent endpoint,
so `--workers 4`; the local wrapper would have contended with the gate itself —
see *Run conditions*).

## Validity conditions (all met)

| Condition | Reading |
| :-- | :-- |
| Rows per pass | **21/21 unique in all six passes**, no duplicate or unparsed lines |
| Transport | every row `http_status=200`, `attempts=2` (turn 1 + graded pushback); the run's abort-on-outage guard never tripped |
| Generator identity | `stage2_model=claude-opus-5` on every polished row in all six passes |
| Arm non-vacuity | **57/63 pairs have distinct arm A/B answer text** — the ON arm's guard text demonstrably reached the payload |
| Judge identity | one identity for all six arms; one shared cache, as `paired_ab` requires |
| Effective n | 63 paired observations over 21 rows, row-clustered bootstrap |

`rg_002` and one other row are `stage2_polish=false` in both arms in every pass
(the deterministic Stage-1 draft), symmetrically.

## Result — pooled paired read (row-clustered bootstrap, n=63)

| Axis | Δ (ON − OFF) | 95% CI (by row) | ON/OFF flips |
| :-- | ---: | :-- | ---: |
| ans_correctness_loose | **+2.12** | [+0.00, +4.76] | 3/0 |
| ans_correctness_strict | **+4.76** | [+0.00, +9.52] | 3/0 |
| ans_conciseness | **−3.14** | **[−6.55, −0.10]** | 26/31 |
| ref_correctness_loose | +0.00 | [+0.00, +0.00] | 0/0 |
| ref_correctness_strict | +1.59 | [+0.00, +4.76] | 1/0 |
| ref_conciseness | +0.13 | [−2.30, +2.43] | 7/5 |
| regulatory_tone | +1.59 | [+0.00, +4.76] | 1/0 |
| resp_speed | −0.44 | [−1.49, +0.77] | 31/32 |

Mean answer length: **OFF 925 chars → ON 957 chars**. `gold_dropped_head`:
**A=0, B=0** across all three samples.

Per-sample deltas (the pre-registered consistency requirement) are in
`scratch/r440_score.log`; sample 0 carries the largest correctness movement
(ans_strict +9.52, CI [+0.0, +23.8]) and the significant conciseness cost
(−7.33, CI [−12.3, −2.9]). No axis clears zero in the ON arm's favour on ≥2 of 3
samples, and none does on the pooled read either.

## The per-row read — why this is a redundancy, not a miss

Read row by row (never netted), the ON arm **fixed 3 of 63 criterion misses and
broke 0**:

| row | sample | OFF | ON |
| :-- | ---: | :-- | :-- |
| rg_075 | 0 | 2/3 criteria | 3/3 |
| rg_106 | 0 | 1/3 criteria | 3/3 |
| rg_109 | 1 | 2/3 criteria | 3/3 |

That is the entire benefit: three single-sample flips, McNemar p=0.25. And the
mechanism is visible in the OFF arm's own text. The guards exist to supply
(biometric verification excluded from Annex III 1(a); Article 6(1) needs *both*
conditions for a safety component; Article 6(3) derogates from paragraph 2 only)
— and the OFF arm **already answers that way**: `rg_007`'s OFF answer reads
"Biometric verification solely to confirm a person's identity is explicitly
excluded from the definition of remote biometric identification", `rg_004`'s
reads "High-risk … Article 6(1) because it is intended to be used as a safety
component of a medical device".

So on 18 of 21 rows the OFF arm is already at 100 % on every correctness axis,
and the guard's provision-dense prose only makes answers longer: `rg_004`
+219 chars, `rg_070` +254, `rg_109` +302, `rg_081` +99. The clusters were
identified on the pre-R425/R429/R431 wire; the wire passes since then fixed the
answers the guards were aimed at.

## Residual defects the per-row read exposed (and an axis that cannot see one)

Only 2 of 21 rows are below 100 on any reference axis, and **both are at ref
strict 50 in all six passes**. Neither is moved by the guards. Each is a
different failure, and the first is in the *instrument*, not the system:

### 1. `rg_008` — the strict axis cannot tell a right coordinate from a wrong one

The key serves `Article 6.1`, **`Annex I.a.11`** (sectioned form). The adopted
text's Annex I is a **flat numbered list**, `1.`–`12.` under Section A and
`13.`–`20.` under Section B, and its point 11 *is* Regulation (EU) 2017/745 — the
MDR the question is about; `19.` and `20.` are Section B acts (`13.` =
Regulation (EC) No 300/2008). What the six passes emit:

| pass | emitted | substantively | strict |
| :-- | :-- | :-- | ---: |
| A s0 | `Annex I.19` | **wrong act** | 0.50 |
| A s1, A s2, B s0, B s1, B s2 | `Annex I.11` | **the MDR — correct** | 0.50 |

`_is_descendant('Annex I.11', 'Annex I.a.11')` is `False`, and so is
`_is_descendant('Annex I.19', 'Annex I.a.11')`. The axis reads **50 for a
correct citation and 50 for a wrong one.** The guards actually fixed this row in
sample 0 — arm A cited point 19, arm B cited point 11 — and the instrument
scored both identically, so that repair is invisible in every number above.

This is a coordinate-form defect in the key/scorer, and the corpus's own flat
numbering is what the system is matching. Two keys also disagree with each
other on these rows: the **refkey** (what `score_arm` serves) says `Annex I.a.11`
on `rg_008` and no Annex head on `rg_004`, while `official_gold_n110.jsonl` says
`Annex I.A.11` on `rg_004` and no Annex head on `rg_008` — differing in both
membership and letter case, and case alone defeats `_is_descendant`.

### 2. `rg_088` — a genuine recall miss the guards do not address

Expected `Article 26.1` + `Article 26.6` (deployer obligations). All six passes
emit `Article 26.6` and **never `Article 26.1`** (they add `Annex I`, `Article 25`,
`Article 13.3.b`, `Annex III.7` instead). Strict 0.50 in every pass, both arms.
This one is a real completeness gap on a deployer-obligation row — and it is the
kind of gap branch guards were supposed to close and demonstrably did not.

The wrong-point emission itself is the model's prose count promoted verbatim by
the Component-D augmentation pass (`app/routes/regenold.py:12350-12374`), which
appends a prose citation as-is; the corpus carries no numbered `Annex I.<n>` keys
to resolve it against. **Next lever: resolve an Annex I point citation against
the sectioned list and normalise key/corpus coordinate forms** — a lever the
branch guards cannot substitute for, because they add prose and this defect is in
the coordinate the prose produces.

## Run conditions and caveats

* **The draw is `r440c`, not `r440`.** Label `r440` was corrupted by concurrent
  writers (duplicate `rg_109`, one unparsed line in `.r1`); `r440b` aborted when
  the Stage-2 primary went down (`No response from Claude Code`, 500s — the
  judge and the gate share the one local wrapper CLI). PR #458's eval-owner lock
  is what makes `r440c` clean, and this gate was scored only after the runner
  exited and released the lock. **Never score while a draw is live.**
* Arm A sample 0 served 13 of its 19 polished rows through the **fallback leg** —
  same model (`claude-opus-5`), different transport. Recorded, not voided; the
  other five passes are `primary` throughout. It is the pass with the largest
  deltas, so a reader who wants the most conservative read can take samples 1
  and 2 alone: both are 0.00 on every reference axis and on answer correctness,
  with conciseness −2.53 and +0.42.
* `ref_correctness_loose` is at **100 % in every arm and every sample**, so the
  refuse rule's "no reference-loose loss" clause is *vacuous* here, not evidence
  of safety. The sample is the audit's failure clusters, not a random board
  slice; nothing here is a board-level claim, and `n=21` rows is under the
  repository's n≥30 power floor for a board statement.
* The conciseness cost is the only CI that excludes zero, and it excludes it in
  the OFF arm's favour.

## Reproduce

```
# score all six arms, pair them, apply the rule
.venv/Scripts/python.exe docs/measurements/r440/branch_cluster_gate.py \
    --score --compare --verdict            # --verdict alone re-reads existing artifacts
```

Artifacts: `docs/measurements/r388/score-r440c-branch-cluster-{A,B}-hard-s{0,1,2}-hard.json`,
`docs/measurements/r440/paired-r440c-branch-cluster-s{0,1,2}.json`,
`docs/measurements/r440/judge-cache-r440-bedrock.jsonl`.
Raw checkpoints: `evals/bench/results/official-r440c-branch-cluster-*.ckpt.jsonl`.

## Verdict (gate complete — all 6 checkpoints 21/21)

Both arms drew to completion (63 paired generations, zero fallback-served,
zero refusals; non-vacuity 57/63 distinct pairs, the 6 identical being the
curated deterministic floor). Per the pre-registered rule:

- **Correctness is untouched** — ans/ref loose and strict are 100/100 across
  both arms on all 21 cluster rows; `gold_dropped_head` A=0, B=0.
- **No axis separates from zero** — pooled `ans_correctness_strict` +4.76 pp
  has CI [+0.00, +9.52]; no pooled or per-sample CI excludes 0 in B's favour.
  `ans_conciseness` median −5.61 pp (A 78.90 → B 73.28) is a net cost.
- **VERDICT: NO WIN — the branch-aware generation guard stays OFF.** The
  pre-flight coverage work (PR #457) was necessary and stands; the guard is
  proven *safe* on its target clusters, but "no regression" alone does not
  justify a default-on prompt change under hard rule #9 (ship on evidence).

Full numbers: `docs/measurements/r440/gate-verdict.txt` (regenerate with
`--verdict`).
