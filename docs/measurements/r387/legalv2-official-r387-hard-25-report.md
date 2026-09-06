# Legal-V2 LLM Judge Evaluation Report

**Generated:** 2026-09-06 15:08:25 UTC  
**Evaluation System:** Legal-V2 (`evals.judge.legal_v2`)  
**Statutory Grounding:** Verbatim EU AI Act provisions from `app.data.provision_text`  
**Anti-Hallucination Gate:** Quote-or-retract literal substring verification  

---

## 1. Executive Summary

### Mode: HARD (`official-r387-hard-25-hard`)

- **Checkpoint File:** `official-r387_live_hard-hard.ckpt-enriched.ckpt.jsonl`
- **Judge Model / Provider:** `claude-sonnet-4-6` via `bedrock`
- **Evaluation Duration:** 74.5s
- **Substantiation Rate:** 78.57% (unsubstantiated claims downgraded: 6)

| Evaluation Axis | Sample Size (N) | Pass | Fail | Error | Pass Rate (Raw) | Pass Rate (Non-Error) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `answer_correctness` | 25 | 19 | 6 | 0 | **76.0%** | 76.0% |
| `reference_correctness` | 25 | 13 | 12 | 0 | **52.0%** | 52.0% |
| `citation_faithfulness` | 25 | 20 | 5 | 0 | **80.0%** | 80.0% |
| `answer_conciseness` | 25 | 11 | 14 | 0 | **44.0%** | 44.0% |

#### Key Metrics (HARD):
- **Factual Score (Chain-of-Verification):** 0.9886
- **Reference Focus Precision:** 0.5259
- **Reference Legal Soundness Precision:** 0.8794
- **Reference Statutory Recall:** 0.9200
- **Citation Faithfulness Pass Rate:** 80.0%
- **Answer Conciseness Pass Rate:** 44.0%
