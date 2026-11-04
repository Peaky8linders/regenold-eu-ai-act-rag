# EU AI Act benchmark: evaluation discrepancies and improvement plan

> **Provenance (R474).** The evidence, probe outputs and `file:line` references in this
> document were produced against commit `5a64d896`, the tree BEFORE PR #510, which then edited
> the files they cite (`rubric.py`, `paired_ab.py`, `judge.py`, `score_arm.py`, `regenold.py`), so
> many line numbers no longer point where they did. The adjacent `pipeline_probe.json` was
> regenerated AFTER the fix and shows the post-fix behaviour; the pre-fix evidence this document
> describes is `docs/measurements/paper_2611_04546/pipeline_probe_pre_r473.json` (run on `beb7aeb9`,
> hospital paraphrases: 5 -> 3 and 5 -> 5 sentences, both with the single reference `Article 26.5`).

Date: 4 November 2026. Local service commit: `5a64d8965da6f723704e21ca2f0ecf22c19768d0`, branch `fix/r468-normaliser-shaping`.

**Repair evaluation fidelity and decision validity first. Then fix content and citation loss in finalization.** The audit reproduced several cases where the instrument rewards the wrong direction. A better generator cannot resolve those measurement errors.

Three specialist audits examined the published protocol, our judge, and the answer pipeline. This review combines their findings with independently rerun synthetic probes, HTTP checks, and focused tests. No application code, defaults, schemas, database, or deployed service was changed. No full official-question replay or paid model call was made. These are instrument and regression diagnostics, not measured performance improvements.

## Evidence and source identities

- [Paper v1](https://arxiv.org/html/2611.04546v1), published 3 November 2026.
- [Released benchmark](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/tree/033e98fdfb6befc0be442c2d26f9851882d9cd80), pinned commit `033e98fdfb6befc0be442c2d26f9851882d9cd80`.
- Released workbook SHA-256: `c15167e6dcdcb8fac6eb6d934a02a6c851b8aa366a54fa467c63d29a0824345b`. Metadata inspection found 110 items, 288 criteria, and 98 reference-bearing items. Reading metadata did not generate or score answers.
- Reusable code/results: `docs/measurements/paper_2611_04546/{protocol_conformance,judge_probe,pipeline_probe}.{py,json}`. The protocol results include source-module hashes.
- Detailed reviews: `2026-11-04-paper-protocol-audit.md`, `2026-11-04-paper-judge-audit.md`, and `2026-11-04-paper-pipeline-audit.md` in this directory.

The release omits historical contestant outputs and integrations. Published tables, old private reports, and the current service are different artifacts. Their scores cannot establish a current improvement without matching data, service, judge, and scorer identities.

## What the paper establishes, and its limits

The task freezes legal scope at 1 May 2026. It uses binary question-specific criteria, deterministic citation/length/speed metrics, and a geometric mean of eight axes. GPT-5.4 judges correctness and tone three times at temperature 0.1. Hard mode adds fixed history and a challenge, then scores the final response. The reported calibration checks 50 sampled decisions; repeat selection matters. It is evidence of useful calibration, not a guarantee against shared judge bias. The paper acknowledges that extra false claims and actual citation support are not adequately measured. [Sections 3-6 and Appendix A](https://arxiv.org/html/2611.04546v1#S3).

Engineering implication: maintain both a reproducible benchmark score and an independent assessment of legal support. A criterion checklist can be satisfied by an answer that adds an unrelated false statement. Professional language cannot establish correctness.

The published Antifragile entry's largest gaps against the winning entry are conciseness and operative-reference recovery. These are historical competition figures, not a measurement of today's branch:

| Easy-mode axis | Antifragile | Pharos |
| --- | ---: | ---: |
| Answer conciseness | 51.9 | 83.1 |
| Reference conciseness | 50.9 | 83.4 |
| Strict reference correctness | 70.8 | 93.9 |
| Strict answer correctness | 81.2 | 89.1 |
| Regulatory tone | 99.1 | 100.0 |

This supports prioritizing complete, economical answers with precise support over more tone polishing. It does not identify which implementation change will succeed. [Table 3](https://arxiv.org/html/2611.04546v1#S5.T3).

The following findings rely primarily on executable released/local source and our probes.

## Findings that affect decisions

### 1. The paired correctness estimator can reverse sign

`evals/official/rubric.py:279` correctly pools passed criteria over all criteria. `evals/official/paired_ab.py:645` computes each question's fraction, and `:723` averages those fractions and their deltas. The paired table therefore estimates macro correctness even though its axis name denotes micro correctness.

| Synthetic question | Criteria | Baseline passes | Candidate passes |
| --- | ---: | ---: | ---: |
| A | 1 | 0 | 1 |
| B | 5 | 5 | 3 |

The current paired estimator reports **+30 percentage points**. Pooled correctness actually declines from 5/6 to 4/6: **-16.67 points**. This is a deterministic counterexample, not a sampling estimate.

**Fix:** use the ratio of pooled successes to pooled criteria for each arm. In every bootstrap draw, resample question clusters and recompute that ratio. Keep macro correctness under its own diagnostic name. Preserve pairing and the same eligibility mask. Bootstrap the complete geometric-mean aggregate as well; a mean of item-level geometric means is a different quantity.

### 2. Invalid judge output can count as agreement, and exit 0 does not mean PASS

The offline judge probe sends `{"winner":"banana"}` to the actual parser. `_judge_one_ok` in `evals/harness/ab_judge.py:287` returns a valid tie. Two such outputs become a stable, position-consistent tie. The main loop also puts failed calls and position disagreement in the tie bucket (`:568`), and the CLI returns 0 after reporting (`:688`).

**Fix:** retain outcomes `A`, `B`, `tie`, `invalid`, and `position_disagreement` separately, alongside both original orderings. Validate exact enums and required fields. Retry invalid outputs with bounded attempts, preserving attempts and failure reasons. Define promotion policy and explicit PASS/FAIL/INDETERMINATE exit codes; insufficient valid coverage, transport provenance, or power cannot establish a pass. Failure to reject a difference does not establish equivalence.

Keep position swaps. They address one bias, while verbosity and provider preference need separate calibration; the [MT-Bench study](https://arxiv.org/abs/2306.05685) motivates those additional controls.

### 3. Our published-score reconstruction uses different formulas

The newer `evals/official/rubric.py` still contains inferred formulas from the private report. The released [reference scorer](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/ref_scoring.py) and [summary](https://github.com/regenold-GmbH/eu-ai-act-benchmark-2026/blob/033e98fdfb6befc0be442c2d26f9851882d9cd80/src/summarize_results.py) now supply the implementation.

| Axis | Current local implementation | Released implementation | Why it matters |
| --- | --- | --- | --- |
| Answer conciseness | Character ratio, `rubric.py:249` | Whitespace-word ratio, runner `:243` | Can reverse which answer is preferred |
| Strict reference correctness | Full-coordinate descendant recall, `rubric.py:154` | First-sublevel recall | Local score can fail a citation the release accepts |
| Reference conciseness | Capped expected/provided count ratio, `rubric.py:176` | Expected / (expected + unrelated extras), with asymmetric parent handling | Same count does not imply the same score |
| Loose correctness in paired statistics | Mean of question fractions | Pooled criteria | Can reverse the estimated effect |
| Judge repetitions | Majority outcomes in principal local score | Per-run metric means, with min/max | Majority can create an all-pass result no typical run achieved |

Examples executed against both implementations:

- Expected `Article 13.3.b`, predicted `Article 13.3.c`: strict recall is local 0, released 1, because both collapse to `Article 13.3` in the release. Keep deeper legal precision as a separate diagnostic.
- Expected `Article 6.1`, predicted `Article 7.1`: reference conciseness is local 1, released 0.5. The local count ratio does not see the unrelated provision.
- Expected `Annex IV.1`, predicted both `Annex IV` and `Annex IV.1`: reference conciseness is local 0.5, released 1. The released implementation exempts the parent. Consequently, an earlier parent-collapse score gain does not automatically transfer to the released formula. This does not establish that parent collapse is harmful.
- Three two-criterion judge runs `[pass,fail]`, `[pass,pass]`, `[fail,pass]`: local majority strict correctness is 100%; mean-run strict correctness is 33.33%.

The older `easyhard_ab` path differs further: `evals/bench/metrics.py:380` uses head-level F1 as strict reference correctness, and `:532` uses a symmetric squared count ratio. A passing historical diagnostic is not evidence of replication fidelity.

The R391 geometric-mean fit validates the final aggregate given printed axis numbers. It cannot validate the inferred computations that produced those axes. Preserve historical results and label their instrument version; add a new released-protocol profile rather than rewriting history or deleting its regression assertions.

### 4. Gold, prompts, and cache identity need versioning together

`evals/official/score_arm.py:62` loads reconstructed criteria, exemplary answers, and an inferred reference key. Released annotations are now available. Use a provenance-checked adapter to those annotations for replication; keep the official set out of development-effect measurements. New held-out scenarios need their own independently reviewed criteria and exemplary answers.

Our judge also differs deliberately from replication: default Sonnet, grouped correctness/tone, and supplied statutory evidence. These choices may be useful, but their effect is unmeasured here. The pairwise prompts use keywords instead of atomic criteria and impose a stricter regulator voice, which can favor unjustified certainty.

`score_arm.py:97` and `:144` do not fingerprint the exact question, rendered prompt, or evidence content. The judge probe confirms that changing question text preserves its basis hash. A new prompt could therefore consume old verdicts.

**Fix:** hash exact rendered messages, criteria IDs/text, source evidence bytes, dataset version, model/provider/settings, parser/schema version, rubric version, and turn. Reject insufficiently identified legacy cache entries for the new profile. Preserve model responses, validity, and per-repeat criterion outcomes before aggregation.

### 5. Hard mode still uses reconstructed stimulus

`evals/regenold/hard_preamble.py:38` documents a reconstructed dialogue. Its user turns intentionally avoid article, role, and risk anchors that our extractor recognizes. The released dialogue has those anchors. The pipeline probe applies our real extractor: current fixture produces an empty anchor string; a single released user turn already produces an Annex III/high-risk anchor. The mismatch changes model/retrieval input, not just wording.

**Fix:** import the exact released history and pushback as versioned fixtures; retain reconstruction/rolling modes only for historical comparisons. Store history bytes/digest and actual request shape in the manifest. Test the final outgoing prompt, including any transport shortening.

`app/routes/regenold.py:10045` also iterates risk-marker sets with substring matching before taking the first two. `annex i` can match `annex iii`; set iteration can alter selected anchors. Use ordered canonical tokens and proper boundaries, with process-hash-seed checks.

For product diagnostics, cross history absent/present with pushback absent/present on new questions. Stratify by whether the first answer was correct. Report correct-to-wrong capitulation, wrong-to-correct repair, persistent error, and unresolved uncertainty. Final score alone confounds history effects with a second attempt. Preserve the existing legal-date pin; it is already present in `app/data/graph_rag_prompt_templates.py:296`.

### 6. Finalization loses content and changes citation meaning

The pipeline probe makes two offline HTTP requests for new hospital-deployer paraphrases, with no `.env`, default answer budgets, and a network tripwire. Both return HTTP 200; no application network connection is attempted.

| Wording | Curated draft sentences | Wire sentences | Wire references |
| --- | ---: | ---: | --- |
| What obligations must a hospital meet when it deploys a high-risk AI system? | 5 | 3 | `Article 26.5` |
| A hospital deploys a high-risk AI system. What are the hospital's obligations? | 5 | 5 | `Article 26.5` |

The first wording loses the explanation-right and provider-transition sentences. Both retain prose addressing several Article 26 paragraphs and Article 27, while returning only paragraph 26.5 in the reference list. The observed pass chain is:

`_curated_budget_cut` (`app/routes/regenold.py:5294`, called `:13059`) removes other heads; `_collapse_multi_leaf_clusters` (`:7053`, called `:14384`) collapses multiple paragraphs to Article 26; `_deepen_ref_grain` (`:5636`, called `:14815`) replaces that parent with Article 26.5.

The existing curated-reference protection does not protect against this whole chain. The sentence ceiling in `app/integrations/regenold/models.py:1838` is also sensitive to wording. This is reproduced default/offline behavior, not a claim about a live deployment's environment or how Stage-2 would respond.

**Fix direction:** preserve a small internal map from each answer claim/required slot to its supporting provision and source span. Make normalization and citation finalization operate on that shared map. A broad obligation summary cannot be treated as fully supported by one arbitrarily selected paragraph. Compress wording while retaining requested obligations, conditions, exceptions, and actor boundaries; prioritize complete support for claims that remain. This needs no wire-schema change.

Extend the already wired `EvidenceBundle` (`app/engines/evidence_bundle.py`, consumed at `_graph_rag_impl.py:10412`) instead of adding a parallel abstraction. Completeness repair also exists at `_graph_rag_impl.py:12210`; simply enabling its previously rejected broad detector is not a new or justified solution.

Do not blindly exempt every curated sentence from budgets: first classify what the question actually asks. The explanation right may be useful yet optional in some short summaries. The acceptance target is stable coverage of required content and surviving claims, with measured word cost, rather than universally longer answers.

## A judge architecture that answers both needs

1. **Replication:** exact released metrics, annotations, history, prompts, repeat aggregation, and source identities. Keep all eight denominators explicit. This answers how closely results reproduce the benchmark.
2. **Legal support:** independent claim extraction and evidence checks. Each material claim should have an answer span, supporting source span, and supported/contradicted/unresolved status. Check false additions, actor changes, negation, exceptions, dates, and conjunctions. These diagnostics can reject an answer whose checklist passes. Keep this offline/shadow initially; do not add a heavy neural verifier to request latency.
3. **Comparative diagnosis:** blind, position-swapped A/B with atomic criteria and recorded disagreement. Use it to explain tradeoffs and support the authorized paired gate, with repaired validity and significance policy. Do not silently combine this preference score with benchmark axes.

Claim-level retrieval/generation diagnosis is supported by the approach in [RAGChecker](https://arxiv.org/abs/2408.08067), while [ALCE](https://arxiv.org/abs/2305.14627) motivates checking citation support beyond citation overlap. These provide design ideas, not evidence that introducing either library will improve this service.

Calibrate a stronger judge on new, expert-adjudicated examples. Include clean paraphrases and controlled single-error mutations: actor swaps, negation, wrong paragraph, dropped condition, AND/OR change, date changes, incorrect quantities, and a correct answer with a false extra sentence. Include warranted uncertainty, citation-only answers, and prompt injection in candidate prose/references. Record sensitivity/specificity, false-pass rate, invalid rate, and uncertainty; balance diagnostic strata but retain a separate probability sample for population estimates. Use another model family and human review on disagreements and a prespecified random audit, rather than paying for an ensemble on every case.

## Efficient experiment sequence

| Order | Work | Evidence required before moving on |
| --- | --- | --- |
| 1 | Freeze versions; add released scorer/annotation/history adapter | Exact conformance on synthetic edge cases; metadata and eligibility checks; historical profiles preserved |
| 2 | Repair invalid handling, exit policy, micro inference, cache identity | Regression fixtures demonstrate former failures; missing/invalid coverage produces INDETERMINATE |
| 3 | Validate judge quality on saved held-out answers | Blinded human labels, mutation detection, calibrated false-pass rate, paired old/new judge comparison |
| 4 | Fix semantic coverage and citation finalization | Same saved generation through both arms; no newly lost required heads/subpoints; correct supported claims survive |
| 5 | Measure generation/retrieval changes | New scenario-family holdout, interleaved arms, fixed provider/model, live serving-leg provenance and end-to-end traces |

Use a small pilot to estimate discordance and cost, not to declare success. Pre-register the useful effect, primary axis, safety non-inferiority margins, sample manifest, and stopping rule. Select a seeded random/stratified sample from independent non-official scenarios; merely taking `--limit` prefixes is insufficient. Deduplicate source questions and paraphrase families. Bootstrap clusters when variants share a scenario. Preserve all failures and exclusions in a coverage report.

Power depends on **discordant pairs**, not just sampled rows. Exact calculations in the protocol probe show that a two-sided sign test at alpha 0.05 has about 81% power with 90 independent decisive pairs if the candidate wins 65% of decisive pairs. Thirty decisive pairs give about 36% power for that effect. If only 30% of questions are decisive, approximately 300 independent questions are needed in expectation; estimate this rate in the pilot and account for clustering/multiplicity. These are illustrative planning assumptions, not a guaranteed sample size.

For final-answer processing, generate once and replay both transformations; skip paid judging of identical pairs while retaining them in the full denominator. For generation changes, interleave/randomize arm order and record model fallback, retries, prompt hashes, evidence coverage, cache hits, and Stage-2 serving leg. Report sampled/scored n, discordant n, wins/losses, ties, invalids, two-sided sign test or paired cluster confidence interval, and the protected gold-head/subpoint checks. Treat operational failures separately from quality while also retaining an all-request reliability view.

Keep final-response latency for benchmark compatibility. Record initial response, total two-call time, and retrieval/generation/finalization timings separately for product performance. This distinguishes genuine speed improvements from repeated-question caching or transport changes.

## Published-source defects and provenance cautions

The released summary accepts uneven repeat coverage. Two synthetic one-criterion rows score strict correctness 50% with three repeats each, but 83.33% if the failed row has only one repeat. Its normal runner checkpoints completed rows, so this demonstrates weak input integrity, not mis-scoring of historical runs. Require exact row/repeat/criterion coverage before comparisons.

The released runner also accepts extra or unrelated criterion outputs and can crash on short lists. Add criterion IDs and exact one-to-one validation to our adapter; source compatibility does not require inheriting its malformed-input behavior.

Private report reference axes differ from the new paper's table. The local historical calibration encodes the former, so a current score must name which target it compares against. The paper also has editorial seven/eight-system denominator inconsistencies. Resolve such provenance questions before alleging substantive errors in published rankings.

## Verification and reproducibility

Executed successfully:

- `python docs/measurements/paper_2611_04546/protocol_conformance.py --benchmark-source tmp/paper-protocol-2611.04546 --out docs/measurements/paper_2611_04546/protocol_conformance.json` (compare pinned scorers and reproduce arithmetic/coverage failures).
- `python docs/measurements/paper_2611_04546/judge_probe.py` (reproduce parser, cache, aggregation, and paired-estimator failures without model calls).
- `python docs/measurements/paper_2611_04546/pipeline_probe.py` (trace two local HTTP responses and reference changes with application networking prohibited).
- `python -m pytest tests/test_official_rubric_alignment.py tests/test_harness_ab_judge.py tests/test_easyhard_paired.py tests/test_r424_hard_preamble.py -q` (68 existing local tests passed).
- `python -m pytest tmp/paper-protocol-2611.04546/tests/test_compute_ref_scores.py tmp/paper-protocol-2611.04546/tests/test_latency_scoring.py -q -p no:cacheprovider` (19 released scorer tests passed).

The local run emitted a pytest cache-write warning; the HTTP probe emitted a TestClient deprecation warning. Neither failed execution. Passing tests preserve current behavior; they do not refute the demonstrated protocol differences.

The public clone is a temporary audit dependency. Recreate it from the linked repository and check out the pinned commit to rerun the conformance probe. Scripts and JSON in `docs/measurements/paper_2611_04546` are the durable audit artifacts. A full suite, live paired gate, or deployability claim was not needed for these documentation/diagnostic additions. Runtime fixes and claimed quality gains remain to be implemented and measured with the repaired instruments.
