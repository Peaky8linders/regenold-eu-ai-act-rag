# Judge audit against arXiv 2611.04546

> **Provenance (R474).** The evidence, probe outputs and `file:line` references in this
> document were produced against commit `5a64d896`, the tree BEFORE PR #510, which then edited
> the files they cite (`rubric.py`, `paired_ab.py`, `judge.py`, `score_arm.py`, `regenold.py`), so
> many line numbers no longer point where they did. The adjacent `pipeline_probe.json` was
> regenerated AFTER the fix and shows the post-fix behaviour; the pre-fix evidence this document
> describes is `docs/measurements/paper_2611_04546/pipeline_probe_pre_r473.json` (run on `beb7aeb9`,
> hospital paraphrases: 5 -> 3 and 5 -> 5 sentences, both with the single reference `Article 26.5`).

Audit date: 2026-11-04. Repository: `D:\Claude Projects\regenold-eu-ai-act-rag`, branch `fix/r468-normaliser-shaping`. Findings below concern inspected executable code and synthetic offline reproductions. No official-question replay, live generation, paid judging, or runtime changes were performed.

The published protocol should now replace inferred competition formulas as the fidelity target. Preserve historical reports under their original instrument version; do not silently relabel old scores. A separate grounded safety evaluation remains necessary.

## Sources and reproducibility

- [Paper, version 1](https://arxiv.org/html/2611.04546v1), especially sections 3.3, 4, 5 and Appendix A.
- [Released reference scorer](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/ref_scoring.py) and [released aggregation](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/summarize_results.py), inspected in `tmp/paper-protocol-2611.04546` at commit `033e98fdfb6befc0be442c2d26f9851882d9cd80`.
- Reproduce judge-specific examples: `python docs/measurements/paper_2611_04546/judge_probe.py` (run offline synthetic instrument probes). The resulting `judge_probe.json` records exact outputs. These examples establish arithmetic/parser discrepancies, not an effectiveness estimate.

## P1: the paired answer-correctness estimator can reverse the result

`evals/official/rubric.py:279` correctly pools criteria for loose correctness. `evals/official/paired_ab.py:645` instead computes a fraction for each item, then `:723-749` averages item deltas. This estimates macro correctness, while the published scorer pools criteria.

Executed counterexample:

| Item | Number of criteria | Baseline passes | Branch passes |
| --- | ---: | ---: | ---: |
| A | 1 | 0 | 1 |
| B | 5 | 5 | 3 |

The published micro delta is **-16.67 pp**, but `paired_ab` reports **+30 pp** for the same outcomes. Its bootstrap CI therefore also targets the wrong estimand. Correct this before trusting loose-correctness deltas. Bootstrap question clusters, recomputing pooled successes divided by pooled criterion counts in each draw, rather than averaging question fractions. Report both metrics with explicit names if macro correctness is useful diagnostically.

## P1: malformed verdicts become valid ties, and the pairwise command is not an exit-code gate

`evals/harness/ab_judge.py:287-303` checks `judge_error`, but accepts every other dictionary. A missing/unknown winner becomes `('tie', True)`. Executed with `{"winner":"banana"}`: both calls become an agreed tie, and `:347` reports swap agreement. Thus the R418 repair handles declared transport failures but not semantic schema failures.

Further, `:568-577` counts transport/parse failures and position disagreements in the same tie bucket as actual indifference. `:688` always returns exit 0 after reporting, including a deterministic downgrade, all judge failures, zero decisive pairs, or significant baseline superiority. This is a diagnostic command, despite its documentation as a merge gate.

Use explicit outcomes `A`, `B`, `tie`, `invalid`, and `position_disagreement`; reject unknown/missing enums. Retain both raw orderings and per-call validity. Refuse promotion with an indeterminate exit code when required calls, Stage-2 provenance, or power are insufficient. Define a distinct policy for a demonstrated regression; do not infer a pass from non-significance. Apply the same repair to `pairwise_from_answers`, which reuses these helpers and also returns 0 after reporting.

## P1: both reference-scoring paths differ from the released scorer

`evals/harness/easyhard_ab.py:167-174` calls `evals.bench.metrics`. That implementation uses head-level F1 as strict reference correctness (`metrics.py:380-399`), collapses subpoints, gives scores to empty-gold rows, and uses a squared symmetric count ratio for reference conciseness (`:532-552`). These are useful historical diagnostics, but they are not the released formulas.

The newer `evals/official/rubric.py` fixes recall and exclusion semantics, but still differs:

| Rule | Current implementation | Released implementation |
| --- | --- | --- |
| Strict reference grain | Full coordinate descendant matching, `rubric.py:154-173` | First sublevel |
| Reference conciseness | `min(1, expected_count / predicted_count)`, `:176-203` | Expected count divided by expected count plus unrelated extras, with specified parent handling |
| Answer conciseness | Character ratio, `:249-273` | Whitespace-word ratio |

Executed comparisons against the pinned public scorer:

| Prediction / expectation | Local | Released |
| --- | ---: | ---: |
| Predict `Article 13.3`; expect `Article 13.3.a`, strict recall | 0 | 1 |
| Predict `Article 6.2, Article 7`; expect `Article 6.2, Article 8`, reference conciseness | 1 | 2/3 |
| Predict `Annex IV, Annex IV.1`; expect `Annex IV.1`, reference conciseness | 1/2 | 1 |

The parent-collapse benefit measured with the count-ratio instrument does not transfer automatically: the released scorer already exempts that parent from extras. This does not imply parent collapse is harmful; its score benefit needs remeasurement. Preserve the existing no-gold-loss constraint and closed directions; do not replace it with a global top-K cap.

## P1: aggregation across judge repetitions is different

`evals/official/judge.py:628-638` takes per-criterion majority and `:670-710` publishes majority criteria/tone. The paper/released summary reports per-run metric means and min/max. `score_arm.py:919-951` prints run ranges but its principal table still scores majority outcomes.

Executed two-criterion example with runs `[pass,fail]`, `[pass,pass]`, `[fail,pass]`: majority produces **100% loose and 100% strict**; mean-run scoring produces **66.67% loose and 33.33% strict**. The latter preserves within-run all-criteria dependence. Keep majority as an explicitly named robustness diagnostic, not the replicated benchmark estimate. Treat missing repetitions as missing measurement, not content failure or an opportunity to fill from majority.

## P1: judge prompt changes can reuse stale verdicts

`score_arm.py:97-123` keys on item ID, answer, judge identity and turn. `:144-153` fingerprints criteria text and reference labels. `judge.py:165-180` identifies provider/model/temperature/grouping/repeats. These fields omit the question text, rendered prompt, rubric version, and actual statutory evidence content.

The offline probe confirms that changing the question leaves `_judge_basis_sha` unchanged. Similarly, changing prompt instructions or provision text without changing model/labels does not invalidate identity. This matters immediately when adopting the published judge prompts: otherwise the supposed new judge may largely read old cached decisions.

Fingerprint exact rendered messages, model settings, parser/schema version and rubric version. Store source/evidence hashes as provenance; validate them on cache hits. Reject legacy entries without sufficient identity for the new instrument rather than trusting them based on an unchanged item ID.

## P2: the current judge should not be described as protocol-equivalent

The official path defaults to Sonnet (`judge.py:64`) with grouped correctness and tone (`:156-162`); it supplies gold-reference statutory excerpts (`:422-445`, `:453-455`) and custom instructions (`:358-419`, `:534-585`). The paper uses GPT-5.4, separate correctness/tone prompts and three runs at temperature 0.1. These choices can change judgments; neither the magnitude nor direction has been measured here.

Pairwise judging is further removed: `pairwise_prompts.py:76-87` uses keywords and references rather than item-specific atomic criteria; `:129-139` prefers a regulator voice with no first-person or hedging. The released tone rubric asks professional appropriateness and clarity. An assertive regulator voice can reward overstatement on a question requiring qualifications.

Recommended architecture:

1. A versioned **benchmark-fidelity** scorer using the published criteria and prompts, with deterministic published metrics.
2. A separate **grounded safety** scorer measuring unsupported/contradicted claims, scope/date errors and citation entailment. This should be able to fail an answer that satisfies the benchmark checklist but adds false material.
3. A blinded pairwise preference layer for explanatory diagnostics, calibrated against the first two layers. Retain position swaps, but do not combine their score names or treat keywords as equivalent to atomic criteria.

Budget efficiently by replaying identical captured answers for judge changes; use an independently calibrated second model only on disagreements or a prespecified audit sample. Escalate to human legal review on disagreement with the trusted rubric or source. Do not introduce the previously rejected neural NLI runtime path.

## P2: sampling and statistical significance need an explicit design

`probe_set.py:139-156` loads sources in fixed order and implements `--limit` as a prefix. There is no sample seed in `ab_judge`'s CLI (`:632-668`). A limited run is not a seeded random sample and may miss later sources/hard cases. Optional source-import exceptions are silently skipped (`probe_set.py:142-145`). `easyhard_ab` enforces an n floor and gold-drop guard, but its paired reference table (`:460-516`) is descriptive and does not by itself establish significance.

Add a fixed sample manifest, seeded random or prespecified stratified selection, source-loading diagnostics, requested/scored/excluded denominators and overlap checks against previously used development data. Preserve easy/hard pairing at the source-question level and bootstrap source-question clusters when variants share a question. For a post-generation lever, send one captured generation through both arms. For a generation lever, interleave arm order and use independent draws while retaining model/transport/cache provenance.

Predeclare the primary axis and safety non-inferiority margin. Size for expected **discordant pairs**, not just total rows. Report sampled n, scored n, wins/losses/ties/invalids, discordant n and a two-sided exact sign test or an appropriate cluster CI. Correct for multiple axes/variants when selecting a winner. Never replay all official 110 to measure a change.

## P2: historical score and calibration claims need version labels

`score_arm.py:43-55` embeds the older report's figures. Published Antifragile reference axes differ: easy historical `89.4/68.3/50.4` versus paper `92.4/70.8/50.9`; hard `89.5/70.7/49.8` versus `92.6/72.2/49.9`. This is a historical-source difference, not evidence that the current service improved. Investigate dataset/scorer/report revision provenance before comparing either table with new runs.

The R391 review's successful geometric-mean fit (`docs/reviews/r391-prompt-lever-split-and-metric-alignment-2026-09-07.md:51-99`) proves the final aggregation given printed axis values. It cannot prove how individual axis values were computed. That report's count-ratio and character-based recovery claims should now be marked superseded by published code, without rewriting the historical results.

`build_gold.py:1-44` reconstructs criteria and exemplary answers, explicitly targeting an inferred character-length band. `score_arm.py:62-93` still loads the reconstructed gold/refkey. These must remain labelled reconstructed until replaced by a provenance-verified public dataset mapping. Avoid fitting the new judge or exemplary-answer lengths to our system's failures.

`calibration.py:203-234` uses a small appendix replay and synthetic positives; the file itself notes an always-fail judge scores about 94% on the negative set (`:257-260`). Build a balanced, blinded held-out calibration set with both meaningful omissions and plausible false additions, verdict qualifications, irrelevant correct facts, citation-only answers and clean paraphrases. Report sensitivity, specificity, precision and stratum-weighted agreement, with uncertainty and independent human adjudication. Keep calibration/training examples separate from final judge-validation examples.

## Recommended implementation order

1. Freeze source, dataset and instrument identities; add a new versioned published scorer instead of mutating historical formulas.
2. Fix macro/micro inference and invalid-verdict handling; make promotion outcomes explicit.
3. Invalidate caches correctly, then compare published and current judges on the same blinded held-out answers with a prespecified paired analysis.
4. Calibrate the safety scorer independently; retain false-addition and groundedness checks outside the benchmark score.
5. Only then use the repaired instrument to measure system changes, starting with answer structure/completeness, operative first-sublevel citations and hard-mode stability. No runtime change has been justified by these synthetic probes alone.
