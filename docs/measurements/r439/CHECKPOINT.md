# R439-lawform — powered stratified gate

**Date:** 2026-09-22  
**Production identity at launch:** `c74ca99b296e` (`/healthz`)  
**Change under test:** `REGENOLD_NEED_PROPORTIONAL_CONTRACT=0` (A/OFF) vs `=1` (B/ON)  
**Transport:** local TestClient with the production `.env` and Claude-Max wrapper primary; arms sequential, never concurrent  
**Instrument:** `scratch/r439_stratified_gate.py` + `evals.harness.gate_validity`  
**Artifact:** `evals/bench/results/easyhard-r439-lawform-strat40.json` (working-tree result; benchmark results are ignored)

## Executive verdict

**The repair does not clear the R439 gate. Do not call it a measured win.** The run is
also **underpowered by the repository's own gate floor after two degraded rows were
excluded**: the surviving sample is easy `n=20`, hard `n=18`, below `_MIN_GATE_N=30`.
The hard split fails Hard Rule #8 on the observed sample: branch `gold_dropped_head`
`12` vs baseline `9` (`+3`). The easy split is `1` vs `2` (`-1`), so the net is `+2`,
but the rule is per split and zero-more, not netted across splits. The harness returned
`exit_code=1` because the hard split violated the rule; the sample must nevertheless
be reported as **indeterminate for power**, not promoted as a definitive board verdict.

This is the correct conservative outcome: the legal-form prompt repair removed the
known self-referential wording, but this sample also changed generation-side answers
and reference sets. The observed hard reference-loose loss and keyword-recall loss
make it unsafe to claim the repair improved strictness.

## Sample design

The requested 40 rows were selected before reading results:

- 20 easy / 20 hard, rather than a front-loaded prefix;
- largest-remainder allocation across all seven probe sources;
- evenly spaced rows within each source;
- all seven sources represented: `lower_risk_v149` 3, `multiarticle_r268` 3,
  `paper_st_v4` 4, `paper_tricky_v4` 4, `tricky_v2` 6, `mt_v2` 14,
  `paper_mt_v4` 6;
- 16 categories represented, including multi-turn, multi-article, borderline,
  omnibus, prohibited, role-ambiguity, GPAI, cross-framework, and lower-risk cases.

The preceding full 132-row attempt was stopped at 86/132 in arm A before any paired
comparison; it is not used as evidence. The 40-row run completed 40/40 in each arm.

## Transport and integrity checks

`gate_validity` reported **valid** with no void reasons. Both arms carried Stage-2 on
the primary wrapper path. Two rows were symmetrically excluded because either arm
hit the wrapper read-timeout/fallback path:

- `mt_v2:mt_v2_004`
- `paper_mt_v4:mt_v4_009`

The surviving paired sample is therefore easy 20 / hard 18. The optional Cohere
embedding provider returned HTTP 429 and the application used its documented SVD
fallback in both arms. Auxiliary Stage-0 denoising also hit its Groq daily quota,
Gemini truncation, and Mistral tier refusal; these are symmetric retrieval/query
noise, not Stage-2 fallback evidence. The Stage-2 transport guard remained valid.

## Paired metrics

Values are means over rows scored successfully in both arms. Deltas are B minus A.
The confidence intervals below are deterministic 20,000-resample paired bootstrap
95% intervals (seed 439); they are descriptive only because this is a stratified
sample and each split is below the repository's n=30 gate floor.

| split / axis | OFF A | ON B | delta | paired bootstrap 95% CI | wins / ties / losses |
| :--- | ---: | ---: | ---: | :--- | :--- |
| easy Ref Loose | 95.83% | 97.50% | +1.67 pp | [0.00, +5.00] | 1 / 19 / 0 |
| easy Ref Strict | 55.45% | 58.62% | +3.16 pp | [-1.73, +8.00] | 8 / 10 / 2 |
| easy Ref Conc. | 26.63% | 30.30% | +3.67 pp | [-2.56, +11.20] | 7 / 10 / 3 |
| hard Ref Loose | 76.85% | 68.52% | **−8.33 pp** | [−19.44, +2.78] | 1 / 13 / 4 |
| hard Ref Strict | 39.92% | 43.69% | +3.77 pp | [−4.76, +11.93] | 8 / 6 / 4 |
| hard Ref Conc. | 16.82% | 36.59% | +19.77 pp | [+6.60, +34.77] | 9 / 8 / 1 |
| hard keyword recall | 83.33% | 66.67% | **−16.67 pp** | [−27.78, −5.56] | 1 / 8 / 9 |
| easy keyword recall | 88.29% | 86.62% | −1.67 pp | [−6.67, +3.33] | 1 / 17 / 2 |
| easy/hard regulatory-tone heuristic | 100% | 100% | 0.00 pp | [0.00, 0.00] | no changes |

`gold_dropped_head` is not an average: it is the hard constraint. It was:

| split | OFF A | ON B | delta |
| :--- | ---: | ---: | ---: |
| easy | 2 | 1 | −1 |
| hard | 9 | 12 | **+3 FAIL** |

The observed strict improvement is not statistically separated from zero, while the
hard loose-recall and keyword-recall movements are adverse. The large hard
Ref-Conciseness improvement is not sufficient to waive a recall loss.

## Row-level tone and mechanism audit

The deterministic regulatory-tone score was `1.0` for every surviving row in both
arms: `20/20` easy and `18/18` hard. No answer in either arm contained the retired
self-referential forms (`no supporting text`, `evidence supplied`, `evidence before
me`, `references supplied`, `material supplied`, or `retrieved`). Thus the specific
R435 tone defect was successfully removed at the text level on this sample, but the
repo's deterministic tone metric cannot establish an LLM-judge tone win.

The hard reference-loss rows are generation differences, not the retired sentence:
`mt_v2:mt_v2_002`, `mt_v2:mt_v2_006`, `mt_v2:mt_v2_015`, `mt_v2:mt_v2_020`, and
`paper_mt_v4:mt_v4_011` changed citations between arms. The gate correctly refuses
to interpret those as proof that the legal-form wording improved strictness.

## Checks performed

- Full production identity checked before launch: `/healthz` served `c74ca99b296e`.
- A/B arms were sequential and used fresh per-call env reads.
- `gate_validity.valid == true`; no stage-2 transport void.
- Fallback rows were excluded symmetrically, never from one arm only.
- 40/40 rows completed in each arm; 38 paired survivors remained.
- `gold_dropped_head` was inspected per split and per row.
- Reference, keyword, and tone deltas were recomputed from the saved JSON.
- Paired bootstrap intervals used 20,000 resamples with seed 439.
- The prior 86-row partial full-board attempt was explicitly excluded.

## Decision

**R439-lawform is not a pass.** Keep the legal-form repair deployed because it removes
the known contradictory/self-referential instruction and the row-level tone scan found
no recurrence, but do not claim it as a measured strictness gain. The next valid gate
needs at least 30 survivors per split after transport exclusion (the project records
that even `n=30` is only a minimum honesty floor, while reference axes ideally need
`n>=120`) and must separately account for generation variance before attributing
citation changes to this wording-only repair.
