# Legal-V2 LLM Judge Evaluation Report

**Generated:** 2026-09-06 14:58:23 UTC  
**Evaluation System:** Legal-V2 (`evals.judge.legal_v2`)  
**Statutory Grounding:** Verbatim EU AI Act provisions from `app.data.provision_text`  
**Anti-Hallucination Gate:** Quote-or-retract literal substring verification  

---

## 1. Executive Summary

### Mode: EASY (`official-r387-easy-25-easy`)

- **Checkpoint File:** `official-r387_live_easy-easy.ckpt-enriched.ckpt.jsonl`
- **Judge Model / Provider:** `claude-sonnet-4-6` via `bedrock`
- **Evaluation Duration:** 74.6s
- **Substantiation Rate:** 73.33% (unsubstantiated claims downgraded: 8)

| Evaluation Axis | Sample Size (N) | Pass | Fail | Error | Pass Rate (Raw) | Pass Rate (Non-Error) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `answer_correctness` | 25 | 21 | 4 | 0 | **84.0%** | 84.0% |
| `reference_correctness` | 25 | 14 | 11 | 0 | **56.0%** | 56.0% |
| `citation_faithfulness` | 25 | 20 | 5 | 0 | **80.0%** | 80.0% |
| `answer_conciseness` | 25 | 13 | 12 | 0 | **52.0%** | 52.0% |

#### Key Metrics (EASY):
- **Factual Score (Chain-of-Verification):** 0.9786
- **Reference Focus Precision:** 0.5059
- **Reference Legal Soundness Precision:** 0.8694
- **Reference Statutory Recall:** 0.9600
- **Citation Faithfulness Pass Rate:** 80.0%
- **Answer Conciseness Pass Rate:** 52.0%
