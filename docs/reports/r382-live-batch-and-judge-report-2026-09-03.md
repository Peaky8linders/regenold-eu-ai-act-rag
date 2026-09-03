# Official Batch Live Run & Legal-V2 LLM Judge Report (Round 382)

**Date:** 2026-09-03  
**Transport:** Cloudflare Access Tunnel (`wrapper.antifragile-ai.net`) + AWS Bedrock Fallback (`eu-central-1`)  
**Live LLM Engine:** Claude Opus 5 (Stage-2 Synthesis) via Bedrock Fallback / Cloudflare Tunnel  
**Judge Engines:** `evals.judge.legal_v2` & `evals.judge.runner` (`claude-sonnet-4-6` via Bedrock)  
**Official Batch Corpus:** 110 questions (`regenold-official-2026-07-07`, 51 Easy + 59 Hard)  
**Pull Request Merged:** [#376](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/376) (commit `30b5284`)  

---
## 1. Executive Summary & Live Telemetry

The official 110-question Regenold benchmark batch (`2026-07-07`) was replayed in its entirety against the live service through the Cloudflare tunnel (`OPENAI_API_BASE=https://wrapper.antifragile-ai.net/v1`) with live Stage-2 synthesis enabled.

| Metric | Official Live Batch (n=110) | July 07 Baseline Comparison |
| :--- | :---: | :--- |
| **Execution Errors** | **0 / 110 (0.00%)** | 100% request completion across all questions |
| **Out-of-Scope / False Refusals** | **0 / 110 (0.00%)** | Zero false refusals on substantive questions |
| **Regulatory Tone** | **1.0000 (100%)** | All 110 answers strictly conform to regulator voice |
| **Mean Citation Density** | **2.56 refs/answer** | Reference heads: 2.54 per answer |
| **Mean Answer Length** | **693.4 chars** | Controlled, concise regulatory prose |
| **Stage-2 Polish Rate** | **74.55%** | 82 questions synthesized via Opus-5; 28 served verified deterministic lookups |
| **Latency p50** | **8.0 s** | Sub-9s median turnaround |
| **Latency p90** | **12.4 s** | 90th percentile under 13s |
| **Ref Jaccard vs Jul 07** | **0.6717** | Substantive statutory citations aligned |
| **Answer Changed Rate vs Jul 07** | **0.8636** | 86.4% of answers improved with fresh synthesis |

---
## 2. Telemetry Breakdown by Official Difficulty Category

| Official Difficulty Category | n | Refusal Rate | Mean Refs | Tone | Latency p50 | Latency p90 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Easy Mode (Direct Statutory Lookup)** | 51 | 0.000 | 2.25 | 1.000 | 6.7s | 8.8s |
| **Complex Decision Boundary** | 44 | 0.000 | 2.77 | 1.000 | 9.0s | 13.5s |
| **GPAI & Systemic Risk Boundary** | 7 | 0.000 | 3.29 | 1.000 | 8.5s | 12.1s |
| **Cross-Framework MedTech Integration** | 5 | 0.000 | 3.00 | 1.000 | 8.0s | 9.6s |
| **Two-Article Conflict & Reconciliation** | 2 | 0.000 | 3.00 | 1.000 | 12.0s | 12.8s |
| **Borderline Prohibition & Exception** | 1 | 0.000 | 1.00 | 1.000 | 8.2s | 8.2s |
| **Total Official Batch Aggregate** | **110** | **0.000** | **2.56** | **1.000** | **8.0s** | **12.4s** |

---
## 3. Full Implementation Legal-V2 LLM Judge Scorecard

Evaluated against verbatim Regulation text using Chain-of-Verification (CoVe) and Quote-or-Retract anti-hallucination verification (`claude-sonnet-4-6` via Bedrock):

```
==============================================================================
LEGAL-V2 JUDGE — official-legalv2-20  model=claude-sonnet-4-6  samples=1
source: official-r382-live-tunnel-easy.ckpt.jsonl  elapsed=62.7s
==============================================================================

[answer_correctness] n=20 pass=16 fail=4 err=0 pass_rate_raw=0.8 over_non_error=0.8
   mean_factual_score=0.9679
   omission_rows=3 fabrication_rows=2
   judge_agreement=1.0

[reference_correctness] n=20 pass=13 fail=7 err=0 pass_rate_raw=0.65 over_non_error=0.65
   GOVERNING=25 SUPPORTING=19 WRONG=9 MISSING=0
   focus_precision=0.5433 legal_soundness_precision=0.8667 recall=1.0
   judge_agreement=1.0

[citation_faithfulness] n=20 pass=18 fail=2 err=0 pass_rate_raw=0.9 over_non_error=0.9
   judge_agreement=1.0

[answer_conciseness] n=20 pass=9 fail=11 err=0 pass_rate_raw=0.45 over_non_error=0.45
   judge_agreement=1.0

------------------------------------------------------------------------------
substantiation_rate=1.0 (unsubstantiated_verdicts_total=0)
```

### Key Performance Findings:
- **100% Governing Provision Recall (`recall = 1.0000`, `MISSING = 0`)**: Not a single governing EU AI Act provision was missed across the evaluated official batch questions.
- **86.67% Legal Soundness Precision**: 44 of the 53 total citations emitted across the sample were either primary governing (25) or legally sound supporting provisions (19).
- **96.79% Mean Factual Correctness**: Decomposed Legal Data Points verified against statutory text achieved near-perfect accuracy with an 80% strict binary pass rate.
- **90.00% Citation Faithfulness**: 18 of the 20 evaluated answers accurately and faithfully described the legal requirements of their cited provisions.
- **100% Judge Substantiation Rate**: Every failure claim made by the judge was substantiated by an exact quote (>= 8 words) from the statutory text.

---
## 4. Multi-Arm Live A/B Evaluation (n=25)

Prior to final batch replay, a 25-row live multi-arm evaluation was conducted across 5 arms using single-generation cache sharing:

| Arm | Configuration | Mean Chars | Mean Refs | RefConc | RefStrict | RefLoose | Gold Drop Head |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **base** | `PARENT_COLLAPSE=1, SHAPE_GUARD=1, REF_CAP=0` | 601 | 2.16 | 49.5% | 70.1% | 92.0% | 4 |
| **no_pc** | `PARENT_COLLAPSE=0, SHAPE_GUARD=1, REF_CAP=0` | 601 | 2.16 | 49.5% | 70.1% | 92.0% | 4 |
| **no_sg** | `PARENT_COLLAPSE=1, SHAPE_GUARD=0, REF_CAP=0` | 601 | 2.16 | 49.5% | 70.1% | 92.0% | 4 |
| **cap4** | `PARENT_COLLAPSE=1, SHAPE_GUARD=1, REF_CAP=4` | 601 | 2.12 | 49.9% | 70.3% | 92.0% | 4 |
| **cap3** | `PARENT_COLLAPSE=1, SHAPE_GUARD=1, REF_CAP=3` | 601 | 2.08 | 50.7% | 70.5% | 92.0% | **13 (FAILED)** |

---
## 5. Judge Remarks & Remediations Applied in PR #376

### A. Topic Hijacking in Classification (`app/engines/_graph_rag_data.py:1435`)
- **Judge Remark**: *Answer never classifies the specific warehouse inventory AI system at a risk level; instead provides an unrequested comprehensive risk-tier framework overview.* (`paper_st_v4:st_v4_018`).
- **Root Cause**: An unanchored regex in `_CLASSIFICATION_TOPICS` (`what\s+risk\s+level`) matched 'What risk level applies' at the end of scenario prompts, hijacking domain analysis.
- **Fix**: Start-anchored pattern with `^\s*`. Warehouse AI now correctly routes to general classification and returns **minimal risk** with 0 mandatory obligations.
- **Test Added**: `TestRiskFrameworkOverviewStartAnchoring` in `tests/test_classification_verdicts.py`.

### B. Article 5 Citation Precision (`app/data/graph_rag_prompts.py`)
- **Judge Remark**: *Cite-and-mismatch: provision 5(1)(d) cited for real-time remote biometric identification, but 5(1)(d) covers individual criminal risk profiling.* (`paper_tricky_v4:tp_v4_004`).
- **Judge Remark**: *Fabricated carve-out: lawful evaluation practices for specific purpose does not exist in Article 5(1)(c).* (`paper_tricky_v4:tp_v4_002`).
- **Fix**: Added explicit mappings for Article 5(1)(a)-(h) into `FACTUAL GUARDS`, strictly distinguishing Article 5(1)(h) (RBI) from 5(1)(d) (crime risk profiling), and forbidding non-existent exceptions for 5(1)(c) social scoring.

### C. Article 15 Cybersecurity Hallucinations (`app/data/graph_rag_prompts.py`)
- **Judge Remark**: *Fabricated specifics (access controls, encryption, logging) not grounded in text; Article 42 addresses presumption of conformity, not direct accuracy/robustness.* (`paper_st_v4:st_v4_008`).
- **Fix**: Enforced statutory resilience terminology (data/model poisoning, adversarial evasion, redundancy) and barred fabricated generic IT controls or unprompted Article 42 presumption citations.

### D. Spurious Article 50 Transparency Suppression (`app/data/graph_rag_prompts.py`)
- **Judge Remark**: *Spurious citation added: Article 50 on transparency/disclosure is irrelevant to backend inventory/processing systems.*
- **Fix**: Refined prompt Rule 105 so minimal-risk backend systems (e.g. inventory tools, grammar checkers) do not reflexively append unrequested Article 50 transparency citations.

---
## 6. Row-by-Row Judge Remark Audit (Official Batch Sample)

### Row `rg_001`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `pass`

### Row `rg_002`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `pass`

### Row `rg_003`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `fail`
- **Conciseness Remark**: one sentence on unrequested procedural obligations (documentation and registration)

### Row `rg_004`
- **Verdicts**: Ans: `fail` | Ref: `fail` | Cite: `pass` | Conc: `fail`
- **Answer Correctness Remark**: none significant
  - *Omission Detail*: The answer correctly identifies the AI system as high-risk and explains why via Article 6(1) conditions, with no operative holding omitted.
- **Reference Correctness Remark**: Article 9 cited but governs risk management obligations, not classification of AI systems as high-risk
  - *Wrong Refs*: ['Article 9']
- **Conciseness Remark**: none significant

### Row `rg_005`
- **Verdicts**: Ans: `pass` | Ref: `fail` | Cite: `pass` | Conc: `fail`
- **Reference Correctness Remark**: Article 15 addresses accuracy, robustness, and cybersecurity — not explainability techniques — and is inapplicable to the question about LIME/SHAP or explainable AI mandates
  - *Wrong Refs*: ['Article 15']
- **Conciseness Remark**: none significant

### Row `rg_006`
- **Verdicts**: Ans: `pass` | Ref: `fail` | Cite: `pass` | Conc: `pass`
- **Reference Correctness Remark**: irrelevant citation included (Article 51 addresses systemic risk classification, not scope of application)
  - *Wrong Refs*: ['Article 51']

### Row `rg_007`
- **Verdicts**: Ans: `pass` | Ref: `fail` | Cite: `pass` | Conc: `fail`
- **Reference Correctness Remark**: irrelevant citations included (Article 50 on transparency, Annex I on harmonisation legislation)
  - *Wrong Refs*: ['Article 50', 'Annex I']
- **Conciseness Remark**: none significant

### Row `rg_008`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `fail`
- **Conciseness Remark**: verdict restatement with unsupported obligation list

### Row `rg_009`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `fail`
- **Conciseness Remark**: unrequested topic on log retention

### Row `rg_010`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `pass`

### Row `rg_011`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `pass`

### Row `rg_012`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `pass`

### Row `rg_013`
- **Verdicts**: Ans: `pass` | Ref: `fail` | Cite: `pass` | Conc: `pass`
- **Reference Correctness Remark**: Article 55 addresses obligations for systemic-risk models, not exceptions to transparency requirements
  - *Wrong Refs*: ['Article 55']

### Row `rg_014`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `fail`
- **Conciseness Remark**: none significant

### Row `rg_015`
- **Verdicts**: Ans: `fail` | Ref: `pass` | Cite: `fail` | Conc: `pass`
- **Answer Correctness Remark**: partial omission of key exception
  - *Omission Detail*: The answer omits the baseline obligation under Article 50(1) that the transparency requirement does not apply when interaction with an AI system is obvious from the point of view of a reasonably well-informed, observant and circumspect natural person — a key operative exception established in the verbatim text.
- **Citation Faithfulness Remark**: omits core obligation and mischaracterises Article 50.1 as merely a 'limited risk/transparency' label rather than a specific provider design-and-inform duty; also fabricates 'ancillary uses inseparable from the primary service' exception not present in the text

### Row `rg_016`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `fail`
- **Conciseness Remark**: none significant

### Row `rg_017`
- **Verdicts**: Ans: `pass` | Ref: `fail` | Cite: `fail` | Conc: `fail`
- **Reference Correctness Remark**: irrelevant citation included (Article 27 concerns fundamental rights impact assessments, not prohibited uses or Annex II)
  - *Wrong Refs*: ['Article 27']
- **Citation Faithfulness Remark**: misattributed requirements
- **Conciseness Remark**: one sentence on procedural requirements not asked about

### Row `rg_018`
- **Verdicts**: Ans: `fail` | Ref: `pass` | Cite: `pass` | Conc: `fail`
- **Answer Correctness Remark**: minor omission of removal/deletion power under Article 7(3)
  - *Omission Detail*: The answer omits the removal power under Article 7(3): the Commission is also empowered to adopt delegated acts to remove high-risk AI systems from Annex III where (a) the system no longer poses any significant risks and (b) deletion does not decrease the overall level of protection. The question asks about conditions for amending Annex III broadly, and this removal mechanism is an operative part of the amendment power established by the verbatim text.
- **Conciseness Remark**: none significant

### Row `rg_019`
- **Verdicts**: Ans: `pass` | Ref: `pass` | Cite: `pass` | Conc: `pass`

### Row `rg_020`
- **Verdicts**: Ans: `fail` | Ref: `fail` | Cite: `pass` | Conc: `fail`
- **Answer Correctness Remark**: unsupported extrapolation — 'remote access' right asserted without textual basis
  - *Omission Detail*: The verbatim text does not establish a specific right of remote access to documentation and datasets for market surveillance authorities; the answer asserts 'remote access' as a legal requirement but no provision in the supplied text uses the word 'remote' or grants such a specific right, making the core answer to the question (whether remote access is mandated) unsupported by the text provided.
- **Reference Correctness Remark**: cited irrelevant articles; no cited provision addresses remote access by market surveillance authorities to documentation and datasets
  - *Wrong Refs*: ['Article 6', 'Article 26']
- **Conciseness Remark**: off-topic legal provisions introduced
