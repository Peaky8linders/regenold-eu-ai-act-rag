# R436 — Full judge, expert review, and GraphRAG audit

**Evidence date:** 21 September 2026
**Judge:** AWS Bedrock Qwen 3 235B, temperature 0.1, three repetitions per row
**Scope:** latest complete 110-row hard capture, 28-question Antifragile expert-review set, and the current 40-row GraphRAG paper/medical ground-truth set.

## Executive result

The latest complete 110-row answer capture remains the R419 production hard-mode capture. It was re-judged through Bedrock with the reconstructed official rubric. The first pass had one missing cache entry (`rg_035`); that row was re-run from the cache-safe checkpoint and the final cache now contains 110/110 rows, three repetitions per row, and zero judge errors. The published axes below are from that completed pass.

The quality pattern is consistent across all three datasets:

1. **Answer correctness is strong on the official board**, but a small number of hard questions fail because the answer chooses the wrong statutory branch or adds a contradictory qualification.
2. **Reference correctness is materially better than reference conciseness.** The GraphRAG corpus is especially exposed to citation mismatch: answers often contain legally relevant text but cite neighbouring or broader provisions.
3. **Conciseness remains a generation problem.** Long answers and sentence-count violations dominate the GraphRAG remarks; global post-hoc deletion would risk removing prose-supported citations.
4. **The expert-review failures are concentrated, not random:** medical-device route conditions, Article 50 paragraph distinctions, biometric-category branching, and deployer/provider role framing.

## 1. Official 110-row hard board

| Metric | Bedrock full re-judge | Latest complete board | Change | Frontier reference |
|---|---:|---:|---:|---:|
| Answer Correctness (Loose) | **93.617%** | 94.15% | −0.53 pp | 92.00% |
| Answer Correctness (Strict) | **89.091%** | 90.91% | −1.82 pp | 84.80% |
| Answer Conciseness | **44.189%** | 44.19% | −0.00 pp | 71.80% |
| Reference Correctness (Loose) | **96.078%** | 96.08% | +0.00 pp | 94.60% |
| Reference Correctness (Strict) | **70.588%** | 70.59% | −0.00 pp | 74.10% |
| Reference Conciseness | **44.790%** | 44.79% | +0.00 pp | 58.50% |
| Regulatory Tone | **93.636%** | 93.64% | −0.00 pp | 100.00% |
| Response Speed | **70.832%** | 70.83% | +0.00 pp | 86.70% |
| **Overall geometric mean** | **72.250%** | 72.48% | **−0.23 pp** | 81.70% |

The Bedrock judge therefore confirms the prior board's shape: the answer-generation and reference-conciseness gaps are real, while the reference-only axes are deterministic for the captured answers. The small correctness movement is judge-model variance, not a code or formula change. The official formulas were not modified.

### Official judge remarks — recurring defects

- **Transport-degraded historical rows:** `rg_036` and `rg_037` were deterministic Stage-1 answers after the historical wrapper/fallback failure. Their omissions are not evidence against the current fallback implementation, but they must remain labelled degraded.
- **Contradictory legal qualification:** `rg_035` correctly states the Article 80(2) process, then adds that gravity changes the statutory timeframe and introduces Article 79(2). The judge treats that added proposition as contradictory to the criterion. The fix is not to delete the answer blindly; generation needs a governing-provision contract that prevents an adjacent risk procedure from overriding the answer to the actual question.
- **Role and threshold precision:** `rg_069` calls a distributor/importer an “operator” and incorrectly limits Articles 23/24 to cases where high-risk status is already known. `rg_062` describes the after-market corrective action but fails to state the pre-market “do not make available” prohibition as a separate limb.
- **Verdict polarity:** `rg_075` does not give an unambiguous affirmative answer on disclosure. `rg_088` capitulates under the adversarial pushback and reverses the turn-one answer despite Article 26(1) and 26(6).
- **Enumerated statutory sets:** `rg_087` explains Article 9 but does not isolate the four required steps as a clean sequence. This is a formatting/completeness failure, not a retrieval failure.
- **Adjacent-route confusion:** `rg_089`, `rg_091`, and `rg_103` choose or reject the wrong Annex III/Article 6 route or the wrong Article 50 exception. These rows require explicit branch conditions, not more unrelated context.

## 2. Antifragile expert-review set

The current captured 28-question expert-review path was re-judged with the same Bedrock model and the statutory criteria from the review artifact:

| Measure | Result |
|---|---:|
| Rows | 28 |
| Strict correctness | **15/28 = 53.57%** |
| Loose correctness (macro mean) | **69.11%** |
| Loose correctness (criterion micro mean) | **67.83%** |
| Regulatory tone | **21/28 = 75.00%** |

The review's authoritative substance was checked against the repository's EU AI Act corpus. The most important recurring gaps are:

- **Risk taxonomy:** answers omit the Article 6/Annex I route or mention sectors without stating the third-party conformity condition.
- **Article 50:** answers conflate provider machine-readable marking (Article 50(2)), biometric/emotion disclosure (Article 50(3)), deepfake disclosure (Article 50(4)), and the timing/accessibility rule (Article 50(5)).
- **Medical-device classification:** answers often omit MDR Annex VIII Rule 11, the Class IIa-or-higher consequence, and notified-body competence under Article 31.
- **Biometric categorisation:** answers fail to branch on the attribute actually inferred: Article 5(1)(g) closed-list prohibition, Annex III point 1(b) high-risk route for other sensitive attributes, or the Article 6(1)/Annex I medical-device route for physiological parameters.
- **Role framing:** hospital/deployer, provider, importer, and distributor duties are sometimes blended, producing correct-sounding but legally misassigned obligations.
- **Tone:** several answers are overlong, self-referential, or include irrelevant article excursions even when their core legal conclusion is correct.

The expert-review document is not treated as an official replacement for the 110-row benchmark. It is a high-value adversarial diagnostic set with richer scenario-specific criteria.

## 3. GraphRAG / medical ground-truth evaluation

A fresh live GraphRAG capture was taken from production over the full 40-row ground-truth set: 20 GraphRAG-paper questions and 20 medical/life-sciences questions. There were no HTTP failures and no refusals. Two recital-only rows were excluded from reference correctness because the wire format does not emit recitals.

### Deterministic metrics from the live capture

| Metric | Result |
|---|---:|
| Rows | 40 |
| Reference-scored rows | 38 |
| Reference Correctness Loose | **90.57%** |
| Reference Correctness Strict | **66.42%** |
| Reference Conciseness | **42.72%** |
| Keyword recall | **76.46%** |
| Regulatory tone | **100.00%** |
| Refusal rate | **0.00%** |
| Latency p50 / p95 | **24.24 s / 37.36 s** |

### Bedrock judge remarks

| Axis | Pass rate | Main failure pattern |
|---|---:|---|
| Correctness | **92.50% (37/40)** | three rows: missing topic keywords, fundamental-rights omission, and incorrect high-risk classification |
| Reference faithfulness | **25.00% (10/40)** | 24 citation-mismatch/cite-and-mismatch outcomes; answers frequently discuss a provision but ship a neighbouring citation |
| Conciseness | **40.00% (16/40)** | sentence-limit failures, excessive length, incomplete final sentences, and over-citation |
| Regulatory tone | **100.00% (40/40)** | no tone failures in this judge pass |

This is direct evidence that the GraphRAG bottleneck is not simply graph recall. The answers are usually substantively acceptable, but the wire references are not aligned tightly enough with the prose and the answer shape remains too long for the benchmark's conciseness rule. The GraphRAG runner's strict-reference value is its stored set-F1-style score, not the official benchmark's expected-reference recall; it is therefore reported as a separate diagnostic and is not mixed into the 110-row geometric mean.

## 4. Grounded remediation plan

### Shipped in this round

- Hardened the expert-review Bedrock parser to merge multiple JSON objects returned in one response instead of turning a valid verdict into a JSON “extra data” failure.
- Added regression tests for split-object responses and ordinary grouped responses.
- Preserved judge identity, cache separation, and incomplete-repetition disclosure.

### Next fixes justified by the evidence

1. **Modality-aware statutory branch contract.** For questions containing a classification, exception, or “does this apply” branch, require the answer to state the governing route and its decisive condition before discussing adjacent routes. Gate on the hard split with three generations and require no correctness or gold-head regression.
2. **Generation-side citation discipline.** Ask the model to cite only provisions it substantively uses, then retain prose reconciliation as a safety check. Do not enable global reference pruning: GraphRAG remarks show mismatch, but deleting references after generation can remove valid support.
3. **Explicit Article 50 and biometric branch templates.** Add general, reusable branch cues for Articles 50(2)–(5) and Article 5(1)(g)/Annex III point 1(b)/Article 6(1), grounded in corpus text and activated only when the question engages those concepts.
4. **Pushback preservation.** Keep the prior-answer floor and add a targeted verdict-polarity check for adversarial turns. It must be tested on the synthetic 9-turn hard modality; no easy-only result is sufficient.
5. **Graph/ontology retrieval.** Do not make graph-primary retrieval or broad ontology expansion default-on. The current evidence supports using Aura/local ontology to enrich already-selected statutory references, not replacing the high-precision lexical route.

No unsupported full-board uplift is claimed. The next full benchmark should be run only after these changes are independently gated and should retain the Bedrock judge cache and per-row remarks as auditable artifacts.

## Artifacts

- `docs/measurements/r436/judge-cache-r436-bedrock.jsonl` (110 rows, 3 repetitions, zero errors)
- `docs/measurements/r388/score-r436-r419-bedrock-complete-hard.json` (final all-metrics score)
- `docs/measurements/r388/score-r436-r419-bedrock-complete-hard.json`
- `docs/measurements/r388/score-r436-r419-bedrock-full-hard.json` (superseded first pass)
- `docs/measurements/r436/expert-review-bedrock-qwen235.json`
- `evals/bench/results/graphrag-bench-r436-graphrag-live.json`
- `evals/bench/results/judge-r436-graphrag-bedrock-qwen235.json`
- `tests/test_r436_expert_judge_parser.py`
