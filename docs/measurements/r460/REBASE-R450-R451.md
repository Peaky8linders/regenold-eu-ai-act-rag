# R460 — transplanting the R449/R450/R451 work onto `origin/main`, and re-running both gates

## 1. What "rebase" actually meant here

`feat/r460-evidence-bundle-payload-cut` was **created from `origin/main` @ `a9553ed`**,
so it is not behind and a literal rebase is a no-op. The work that was behind is the
R449/R450/R451 round: it sits **uncommitted** in the main checkout on
`fix/r444-healthy-leg-screen` @ `1aa09b8` (65 commits behind), next to ~40 other
agents' modified files.

Rebasing that checkout was not done and should not be done without an explicit
decision: it is dirty, shared, and carries other agents' in-flight work. The
equivalent, non-destructive action was taken instead — the R449–R451 files were
transplanted onto the `origin/main` worktree.

Safety check that made it safe: `origin/main` **never touched** any of the three files
that carry a local delta. `git diff --stat 1aa09b8 origin/main -- app/data/provision_text.py
app/data/kb_search.py` is **empty**, so the local versions are exactly *origin/main +
my delta*, and a copy is lossless.

Transplanted: `evals/retrieval/` (untracked: `field_weight_sweep.py`, `emit_sweep.py`,
`unit_grain.py`, `__init__.py`), `tests/test_r449_contextual_fields.py`,
`tests/test_r449_dense_boost_displacement.py`, `tests/test_r449_unit_grain_harness.py`,
`tests/test_r450_emit_allocation.py`, `tests/test_r451_field_weights.py`,
`docs/measurements/{r450,r451}/`, `docs/reviews/r449-contextual-bm25-rerank-sota-2026-09-28.md`,
and the two modified sources `app/data/provision_text.py`, `app/data/kb_search.py`.

## 2. The integration gap the transplant exposed

On the first run **5 tests failed, all one class**: `_engine_cache_key` on `origin/main`
keys **none** of the transplanted knobs.

```
FAILED test_r451_field_weights.py::test_weights_are_in_the_engine_cache_key[REGENOLD_FIELD_WEIGHT_TITLE]
FAILED test_r451_field_weights.py:: ...[REGENOLD_FIELD_WEIGHT_BODY]
FAILED test_r451_field_weights.py:: ...[REGENOLD_FIELD_B_TITLE]
FAILED test_r451_field_weights.py:: ...[REGENOLD_FIELD_B_BODY]
FAILED test_r449_contextual_fields.py::test_engine_cache_key_includes_contextual_fields
```

This is the R263.2 / R288.1 cache-poisoning shape, and for the R451 harness it is
fatal rather than cosmetic: the sweep runs every cell **in one process**, so an
unkeyed weight would serve arm A's cached response to every later cell and report a
flat "weights do not matter" for the entire grid — a real effect read as a null.

Fixed by registering seven knobs in `app/routes/regenold.py` `_engine_cache_key`:
`REGENOLD_CONTEXTUAL_FIELDS`, `REGENOLD_EMIT_ALLOC`, `REGENOLD_EMIT_SPLIT_TOP`,
`REGENOLD_FIELD_WEIGHT_{TITLE,BODY}`, `REGENOLD_FIELD_B_{TITLE,BODY}`.
Applied with `apply_r449_r451_cache_keys.py` (asserted single-match byte replacement,
idempotent) — the worktree lives under an ignored path, so the ordinary editor cannot
open these files.

**88 passed** after the fix (the 5 R449/R450/R451 suites).

## 3. R451 field-weight sweep — re-run on origin/main

Reproduces the original verdict on the new base (17 OFAT cells + the `sparse`
un-fielded control, 110 gold rows, one built index, bootstrap seed 20260928):

* **Title side is flat.** `w1`, `w1.5`, `w3`, `w5` are indistinguishable from the
  shipped cell (Δ ≤ +0.003 vs `shipped`, every CI touching zero); every `bt` cell is
  ≤ 0.0003 apart. "Untuned title weights" is **eliminated**, not merely unproven.
* **`b_body` is the one live parameter, and it is monotone.** Against the `sparse`
  control, `bb0.5` **+0.0311 [+0.0138, +0.0506]** and `bb0.6` **+0.0270 [+0.0111,
  +0.0454]** are the only cells that clear **both** α=0.05 and the Bonferroni bar for a
  17-cell sweep (α=0.05/17 = 0.00294). `bb0.3`/`bb0.4` clear α=0.05 only; `bb0.9`,
  `bt*`, `w*` and the shipped cell do not clear either.
* **Promotion candidate: `bb0.6`** (same as before).
* Nothing beats `shipped` under the pre-registered rule (all HOLD inside noise), so
  the shipped weights stay — the known limitation is that clause 3 is precision-based
  and 92% of the nDCG gain comes from 4 rows, which is the recorded rule defect, not
  a new finding.

## 4. R450 emission gate — re-run on origin/main

Same conclusion at every budget (82 gradable rows): **`density` is the best
allocator, `split` is falsified.**

| budget | `rank` (shipped) | `density` | Δ |
|---|---:|---:|---:|
| 700 | 43/82 (0.524) | 43/82 (0.524) | 0.000 |
| 900 | 56/82 (0.683) | **57/82 (0.695)** | +0.012 |
| 1200 | 61/82 (0.744) | **64/82 (0.780)** | +0.036 |
| 1600 | 67/82 (0.817) | **68/82 (0.829)** | +0.012 |

`density` wins at matched characters (p95 1,221 chars at the shipped 1,200 budget in
both arms). The `split*` cells inflate characters (1,022–1,479 at 900–1200) without
beating `density` on hit-rate — the falsification holds. At the 500-char budget,
`rank → split@0.5` rescues `rg_091` and `rg_101` at identical characters, which is a
new, small, worth-following detail rather than a promotion.

## 5. Limits

* Nothing was committed. The transplant and the cache-key registration are working-tree
  changes on `feat/r460-evidence-bundle-payload-cut`; they need a review before they
  land, and the main checkout was deliberately left untouched.
* "Per-row provenance is recorded upstream" does not bear on these two gates: both are
  **offline retrieval** sweeps with no Stage-2 call, so there is no leg to provenance.
  Provenance matters for the *live* gate on the same levers, which is a separate run.
* The `density` and `bb0.5`/`bb0.6` levers remain **measured, not flipped**.
