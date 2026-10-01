# R451 — contextual-field (BM25F) weight sweep: is the by-argument weight wrong?

**Round:** R451 · **Date:** 28 September 2026
**Working tree:** local checkout on `fix/r444-healthy-leg-screen` (dirty, other agents active). This file is **local and untracked** — nothing posted, pushed, or attached to a PR.
**Scope:** Regulation (EU) 2024/1689 only.
**Instrument:** `evals/retrieval/field_weight_sweep.py` (new) + `tests/test_r451_field_weights.py` (new, 35 tests).
**Determinism:** offline, no network, no judge, no LLM. Gold = `docs/measurements/r388/official_gold_n110.jsonl` (110 rows); retrieval = the production `kb_search.top_articles_by_relevance(question, k=8, min_score=1.0)`; the sparse control rebuilds the index with `REGENOLD_CONTEXTUAL_FIELDS=0`. Runtime ≈75 s for 17 fielded cells + control.
**Artifacts:** `field-weight-sweep.json`, `FIELD-WEIGHT-SWEEP.md` (final grid); `field-weight-sweep-coarse.json`, `FIELD-WEIGHT-SWEEP-coarse.md` (the discovery pass, kept so the refinement is auditable).

## 1. Question

R449 built the fielded BM25 path and measured it at ONE weight setting — `title=2.0, body=1.0, b_title=0.6, b_body=0.75` — chosen **by argument** ("the title field is short, so it gets a higher weight"), never tuned. Its verdict was "weak-positive inside noise, stays OFF". That is a verdict on an untuned configuration, which is not a verdict on the technique. Which side of the optimum the shipped cell sits on is an empirical question.

## 2. What the instrument does

Sweeps the four parameters one-factor-at-a-time around the shipped cell (families `w` = title weight, `bt` = title length slope, `bb` = body length slope, `bw` = body weight) through the production entry point. Weights are read **per score call**, so ONE built index serves the whole grid — a rebuild per arm would re-measure the build, not the weights.

Three properties were load-bearing and are pinned by tests:

* **The sparse control must rebuild the index.** `_build_index` is `lru_cache(maxsize=1)` and the fielded/plain dispatch reads `index.field_freqs`, which is decided **at build time**. Flipping the env var in a warm process does nothing, so a control written the obvious way would have silently scored through the *fielded* index and read exactly like the shipped cell. `_fresh_index()` clears the cache and rebuilds.
* **Every grid value must be representable.** Production clamps weights to [0.1, 10.0] and `b` to [0.0, 0.999]. The first draft's `w0` cell was silently `0.1` — the table would have printed a weight the ranker never used. The grid now stops at 0.1 and `assert_grid_representable()` refuses any cell the clamp would move.
* **The shipped cell carries the `shipped` label.** It is the deduped baseline of all four families; letting a family overwrite the label (`w2`) silently breaks every paired delta and the churn reference.

Noise discipline: every cell is paired against the shipped cell with a **paired row bootstrap** (seed 20260928, 10,000 resamples), and the verdict column is **computed**, never eyeballed. The rule was fixed before the run: PROMOTE requires (1) the paired recall CI **or** the paired nDCG CI to exclude zero upwards, (2) neither axis to exclude zero downwards, and (3) additions not to be churn (`added_precision` at least matches shipped's, or nothing is added). A Bonferroni CI at α=0.05/17 is also reported — as a **diagnostic**, not as a rule change.

## 3. Result: the title side was fine, the body slope was wrong

Final grid, 110 rows, k=8. Δ columns are paired vs `shipped`; positive = better.

| cell | head recall | nDCG@8 | ctx chars | added/gold | churn rows | recall Δ [95% CI] | nDCG Δ [95% CI] | verdict | survives α=0.05/17 |
|---|---|---|---|---|---|---|---|---|---|
| `sparse` (no fields) | 0.7500 | 0.5758 | 31,363 | 0/0 | 69 | −0.0091 [−0.0455, +0.0182] | −0.0140 [−0.0311, +0.0007] | HOLD (noise) | no |
| `shipped` | 0.7591 | 0.5898 | 31,401 | 94/3 | 0 | 0 | 0 | HOLD (noise) | no |
| `bb0.3` | 0.7773 | 0.6110 | 34,286 | 196/5 | 98 | +0.0182 [−0.0182, +0.0545] | +0.0212 [−0.0029, +0.0473] | HOLD (noise) | no |
| `bb0.4` | 0.7773 | 0.6111 | 32,868 | 167/5 | 88 | +0.0182 [−0.0182, +0.0545] | +0.0213 [+0.0003, +0.0435] | HOLD (churn) | no |
| `bb0.5` | 0.7773 | 0.6057 | 32,396 | 141/4 | 72 | +0.0182 [+0.0000, +0.0455] | +0.0158 [+0.0037, +0.0303] | HOLD (churn) | no |
| **`bb0.6`** | 0.7773 | 0.6016 | 32,014 | 123/4 | 56 | +0.0182 [+0.0000, +0.0455] | +0.0118 [+0.0023, +0.0241] | **PROMOTE** | no |
| `bb0.9` | 0.7591 | 0.5803 | 31,160 | 109/3 | 49 | +0.0000 | −0.0095 [−0.0206, −0.0012] | HOLD (loss) | no |
| `bt0` | 0.7591 | 0.5895 | 31,251 | 104/3 | 15 | +0.0000 | −0.0003 [−0.0022, +0.0016] | HOLD (noise) | no |
| `bt0.3` | 0.7591 | 0.5896 | 31,380 | 99/3 | 6 | +0.0000 | −0.0003 [−0.0008, +0.0000] | HOLD (noise) | no |
| `bt0.9` | 0.7591 | 0.5897 | 31,407 | 91/3 | 3 | +0.0000 | −0.0001 [−0.0004, +0.0000] | HOLD (noise) | no |
| `bw0.5` | 0.7712 | 0.5984 | 31,016 | 165/3 | 81 | +0.0121 [+0.0000, +0.0333] | +0.0086 [−0.0031, +0.0218] | HOLD (noise) | no |
| `bw2` | 0.7561 | 0.5828 | 32,274 | 110/2 | 58 | −0.0030 [−0.0303, +0.0242] | −0.0070 [−0.0226, +0.0071] | HOLD (noise) | no |
| `w0.1` | 0.7561 | 0.5772 | 31,432 | 28/1 | 62 | −0.0030 [−0.0303, +0.0242] | −0.0127 [−0.0286, +0.0014] | HOLD (noise) | no |
| `w0.5` | 0.7500 | 0.5800 | 31,631 | 43/1 | 52 | −0.0091 [−0.0273, +0.0000] | −0.0098 [−0.0230, +0.0004] | HOLD (noise) | no |
| `w1` | 0.7591 | 0.5868 | 31,583 | 75/3 | 25 | +0.0000 | −0.0031 [−0.0114, +0.0020] | HOLD (noise) | no |
| `w1.5` | 0.7591 | 0.5896 | 31,362 | 89/3 | 6 | +0.0000 | −0.0002 [−0.0014, +0.0009] | HOLD (noise) | no |
| `w3` | 0.7591 | 0.5929 | 31,233 | 109/3 | 20 | +0.0000 | +0.0031 [−0.0008, +0.0101] | HOLD (noise) | no |
| `w5` | 0.7621 | 0.5971 | 31,367 | 131/3 | 45 | +0.0030 [+0.0000, +0.0091] | +0.0072 [−0.0001, +0.0169] | HOLD (noise) | no |

### 3.1 The title weight is not a knife-edge — the by-argument value is fine

`w1.5`, `w2.0` (shipped), `w3` and `w5` are mutually indistinguishable: churn 6, 0, 20 and 45 rows respectively, nDCG Δ −0.0002, 0, +0.0031, +0.0072, none significant. The shipped **2.0 sits in a flat basin**, so "the title weight was never tuned" is not a defect that was costing anything. Turning the field nearly off does cost (w0.1: nDCG −0.0127, churn 62 rows; w0.5: −0.0098) — but not significantly.

`bt` (title length slope) is flat across its whole range [0.0, 0.9]: nDCG Δ ≤ 0.0003 either way, churn 3–15 rows. At k=8 with a saturated list, the title field's length normalisation is not load-bearing.

**This is a negative result worth having:** R449's weak-positive verdict was *not* an artefact of untuned title weights, so that explanation is now eliminated.

### 3.2 `b_body` is the one live parameter, and the shipped value is on the wrong side

The family is monotone over [0.4, 0.9]: the lower the body length-normalisation slope, the better the ordering.

| `b_body` | 0.4 | 0.5 | 0.6 | 0.75 (shipped) | 0.9 |
|---|---|---|---|---|---|
| nDCG@8 | 0.6111 | 0.6057 | 0.6016 | 0.5898 | 0.5803 |
| nDCG Δ vs shipped | +0.0213 | +0.0158 | +0.0118 | 0 | −0.0095 |
| CI excludes zero? | yes | yes | yes | — | yes (loss) |

`bb0.9` is a **significant loss** (CI [−0.0206, −0.0012]) and `bb0.5`/`bb0.6` are significant gains, so the sign of the effect is established at both ends of the family rather than by a single marginal cell. Lower `b` means **less penalty for long body documents**, and three different knobs all point the same way — `w_title` up (+0.0072 at w5), `w_body` down (+0.0086 at bw0.5), `b_body` down (+0.0158 at bb0.5) are all "let the context field count for more relative to the body". That coherence is the strongest part of the finding; the individual cells are correlated knobs, not independent replications.

Plausible mechanism (interpretation, not measurement): the `body` field mixes short authored KB summaries with long EUR-Lex corpus prose, and the shipped `b=0.75` — the classic BM25 default — over-penalises the long ones. This is the same under-ranking that Round 25 patched *outside* BM25 with a 0.6× source-tier multiplier; `b_body` is a cleaner place to fix it.

### 3.3 Recall moves on a handful of rows

Membership changes vs the sparse control, named:

| cell | head-recall gained vs control | lost | net |
|---|---|---|---|
| `shipped` | `rg_013`, `rg_088` | `rg_011` | +1 |
| `bb0.5` / `bb0.6` | `rg_013`, `rg_068`, `rg_088` | — | **+3** |
| `bb0.4` | `rg_006`, `rg_013`, `rg_068`, `rg_088` | `rg_076` | +3 |

So the shipped weights **lose `rg_011`** relative to having no contextual fields at all, and `b_body=0.5/0.6` recovers it *and* wins `rg_068`. The `bb0.6` recall gain over shipped is exactly two rows (`rg_011`, `rg_068`), with nothing lost. The returned list length is unchanged (`excess refs` 7.16–7.19 for every cell, i.e. k=8 saturated everywhere), so this is not bought by admitting more candidates.

### 3.4 The better-powered comparison: fields vs NO fields

The pre-registered rule scores against `shipped`. The prior question — does the fielded path beat having no fields at all, and at which weights — is a different pairing, and it is the one with the power to answer R449's verdict. Reported as a **read**, with no verdict of its own, so a friendlier baseline cannot manufacture a PROMOTE:

| cell | nDCG Δ vs `sparse` [95% CI] | beats control | beats control after α=0.05/17 |
|---|---|---|---|
| `shipped` | +0.0140 [−0.0007, +0.0311] | no | no |
| `bb0.3` | +0.0352 [+0.0080, +0.0645] | yes | no |
| `bb0.4` | +0.0353 [+0.0107, +0.0618] | yes | no |
| **`bb0.5`** | **+0.0299 [+0.0127, +0.0496]** | yes | **yes** |
| **`bb0.6`** | **+0.0258 [+0.0101, +0.0441]** | yes | **yes** |
| `bb0.9` | +0.0046 [−0.0136, +0.0232] | no | no |
| `bw0.5` | +0.0226 [+0.0056, +0.0422] | yes | no |
| `w3` / `w5` | +0.0171 / +0.0213 | yes | no |
| all `bt*`, `w0.1`, `w0.5`, `w1`, `bw2` | ≤ +0.0139 | no | no |

**This is the round's headline.** With the shipped weights the contextual-fields path is +0.0140 nDCG over no-fields at all, CI [−0.0007, +0.0311] — R449's "inside noise", reproduced on an independent instrument. With `b_body` at **0.5 or 0.6** it is +0.026 to +0.030 with a CI that excludes zero in the **0.0294-level** Bonferroni sense. The claim R449 could not make — *the fielded path beats no fields at all, beyond noise* — becomes supportable at a tuned `b_body` and stays unsupportable at the shipped one.

## 4. Verdict

**No default changes.** No cell clears the pre-registered rule at the multiplicity bar, and the one cell that clears it at all (`bb0.6`) does so on evidence that is thin in a way the checkpoint must not bury.

`bb0.6` = `b_body 0.6`, everything else shipped. Pre-registered rule: PASS.

* gain: nDCG Δ +0.0118, CI [+0.0023, +0.0241] → excludes zero upwards ✓
* no loss: recall CI [+0.0000, +0.0455], nDCG CI upper +0.0241 → neither excludes zero downwards ✓
* churn: `added_precision` 4/123 = 0.03252 vs shipped 3/94 = 0.03191 ✓ — **by 0.0006, i.e. one extra gold reference out of 123 additions. A single row would flip this clause.**

Why it is still a candidate and not a promotion:

1. **It does not survive multiplicity *against `shipped`*.** Adjusted nDCG CI [−0.0003, +0.0322] straddles zero. At α=0.05/17 nothing in the grid beats the shipped weights. The effect that *does* survive is the one against the `sparse` control (§3.4), which is a bigger, better-powered difference.
2. **The gain is concentrated.** Summed over 110 rows the cell gains +1.339 and loses +0.045 nDCG; **+1.226 of that gain (92%) comes from 4 rows**, and the median row delta is exactly 0.0000. Membership moves on 2 rows.
3. **`churn rows` 56/110 overstates the substantive change and understates the risk.** 56 rows get a different candidate set while only 8 rows change nDCG — i.e. the gold heads' discounted positions — so most of the churn is non-gold tail reshuffling that the gold set cannot grade. A displaced non-gold provision can still be one the answer legitimately cites, which retrieval grain cannot see.
4. **It costs context**: +613 chars/row mean (+2.0%).
5. **`bb0.5` is arguably the better candidate** (+0.0299 vs control, also multiplicity-surviving, more churn 72 rows) and it fails the shipped-baseline churn clause outright (4/141 = 0.0284 < 0.0319). The rule's clause 3 is **precision**-based, and over a k=8 list where gold is 3 or 4 references, precision differences of ~0.001 are noise. That clause was the right guard against "add 100 refs for +0.5 pp recall" and the wrong instrument for "add 1 gold ref and 29 noise refs". Recorded as a **rule defect for the next round to re-register** — not edited after seeing the numbers.

**Action:** route `REGENOLD_FIELD_B_BODY=0.5` and `=0.6` to a **live paired gate** (27-row set, R415 instrument once the provenance gap is closed), with a re-registered clause that compares **gold additions** rather than precision. The lever is already env-driven and read per call, so a gate needs no code change.

## 5. What shipped in code

* `app/data/kb_search.py` — `_FIELD_NAMES`, `_FIELD_WEIGHT_ENVS` / `_FIELD_B_ENVS`, `_FIELD_WEIGHT_BOUNDS` / `_FIELD_B_BOUNDS`, `_field_env()` (clamped, NaN/inf/garbage → shipped default), `field_weight()` / `field_b()` read **per score call** from `_score_fielded`. **Shipped defaults unchanged** (`2.0 / 1.0 / 0.6 / 0.75`), so the default ranking is byte-identical.
* `app/routes/regenold.py` — the four env names registered in `_engine_cache_key`. Unkeyed, an in-process weight sweep would serve arm A's cached answer to every later arm — which reads exactly like "weights do not matter".
* `evals/retrieval/field_weight_sweep.py` — the sweep (17 fielded cells + sparse control, paired bootstrap, pre-registered verdict, multiplicity diagnostic, control comparison, per-row arrays in the JSON so any pairing can be re-derived without re-running).
* `tests/test_r451_field_weights.py` — 35 tests: defaults, per-call reads, garbage/NaN/inf fallback, clamping, grid representability, one-factor-at-a-time shape, the single `shipped` label, non-vacuity of both the title weight and the body slope, explicit-shipped-env-is-a-no-op, the sparse control genuinely rebuilding, the paired-delta **sign convention**, all four verdict clauses, the multiplicity diagnostic not rewriting the verdict, markdown shape, cache-key registration, and `run_sweep`'s control-as-its-own-baseline wiring.

**Two defects found and fixed while verifying, both by contradiction rather than by reading:**

* **Sign inversion.** `paired_bootstrap_ci(a, b)` computed `b − a` while callers passed `(cell, baseline)`, so every printed delta and every verdict was inverted while the aggregate columns stayed correct — `bb0.5` showed aggregate nDCG 0.606 > shipped 0.590 with a printed Δ of **−0.0158**. Renamed to `paired_delta_ci(baseline, cell)` so the argument order *is* the convention, and pinned by two tests. Mutation check: reverting to `b − c` turns **8 tests red**.
* **Multiplicity denominator.** The adjusted CI originally re-ran the whole bootstrap; it now slices one resample set, so the verdict and the diagnostic cannot disagree about the data. Output verified **byte-identical** across the refactor.

## 6. Reproduce

```
.venv/Scripts/python.exe -m evals.retrieval.field_weight_sweep \
    --out docs/measurements/r451/field-weight-sweep.json \
    --md-out docs/measurements/r451/FIELD-WEIGHT-SWEEP.md
.venv/Scripts/python.exe -m pytest tests/test_r451_field_weights.py -q
```

Deterministic: fixed seed (20260928), fixed resample count (10,000), fixed grid, offline env applied before any `app.*` import. Re-running reproduces the table byte-for-byte.

## 7. Scope and honesty

* **Retrieval grain only.** Head-grain recall and nDCG@8 over the gold heads. Nothing here says an official axis moves; a retrieval win and a generation regression cancel invisibly inside the answer-level axes.
* The gold set is 110 rows and the effects are concentrated on 2–12 of them. Paired CIs respect the pairing but cannot manufacture rows that are not there.
* `head_recall` and `nDCG@8` are the two pre-registered axes; `all heads`, `excess refs` and `context chars` are descriptive and no verdict depends on them.
* The Row-25-style mechanism story in §3.2 is interpretation. The measurement is the monotone family and the control comparison.
* `bb0.3`/`bb0.4` reach higher mean nDCG (+0.021 raw) but with a wider spread, so their CIs do not clear even α=0.05 against the control after adjustment; they are not better candidates, they are noisier ones.
