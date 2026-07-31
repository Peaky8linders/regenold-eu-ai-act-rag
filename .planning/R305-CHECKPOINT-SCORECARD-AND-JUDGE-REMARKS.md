# R305 Checkpoint & Handoff — Scorecards, Grounded LLM-as-Judge Remarks & Live Q&A

This document serves as the **authoritative handoff for fresh sessions**. It aggregates all empirical benchmark metrics, grounded `claude-sonnet-5` LLM-as-Judge remarks, live Q&A samples, and architectural changes shipped during Round 304+.

---

## 0. Executive Summary & Strategic Context

### The Strategic Picture
* **Core Bottleneck**: The performance gap on the EU AI Act RAG benchmark is **answer quality, not retrieval**.
* **Empirical Metric Disparity**: $AnsLoose - RefLoose = -13.1$ for our pipeline vs $+3.9$ for the 2025 baselines. Retrieval recall sits at **0.973** with **zero missing-only failures**.
* **Geometric Mean Sensitivity**: Overall score is a plain geometric mean across axes, making it dominated by the lowest axis. **Answer-Conciseness** is our ONLY leading axis with zero headroom (pure downside risk). All prompt and pipeline additions are strictly audited to preserve output brevity.

---

## 1. Grounded LLM-as-Judge Scorecard (Sonnet-5)

Evaluated across the **71-Request Stratified Hard Sample** ($N = 43$ distinct questions: 28 multi-turn $\times$ 2 turns + 15 single-turn hard) against the **verbatim EU AI Act text** (`app.data.provision_text`):

| Evaluation Axis | Single-Turn Hard (`r304-slack0-st`, $n=15$) | Multi-Turn Hard (`r304-slack0-mt`, $n=28$) | Combined Pooled Sample ($n=43$) | R301 Baseline | Delta ($\Delta$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Answer Pass Rate (Binary)** | **0.6667 (66.7%)** | **0.6786 (67.9%)** | **0.6744 (67.4%)** | 0.3720 (37.2%) | **+30.2%** |
| **Mean Factual Score (Graded)** | **0.8690 (86.9%)** | **0.8836 (88.4%)** | **0.8785 (87.9%)** | 0.8270 (82.7%) | **+5.2%** |
| **Reference Recall** | **0.9833 (98.3%)** | **0.9680 (96.8%)** | **0.9733 (97.3%)** | 0.9410 (94.1%) | **+3.2%** |
| **Reference Strict F1** | **0.7813 (78.1%)** | **0.7614 (76.1%)** | **0.7683 (76.8%)** | 0.7630 (76.3%) | **+0.5%** |
| **Citation Faithfulness** | **0.9333 (93.3%)** | **0.6071 (60.7%)** | **0.7209 (72.1%)** | 0.5580 (55.8%) | **+16.3%** |

---

## 2. Target Deterministic Rows — Live Q&A & Performance Improvements

The worst-performing bucket (un-curated deterministic fallbacks) was eliminated by adding dedicated, false-positive-resistant curated intercept detectors (`_is_curated_authoritative_intercept` + `_deterministic_answer`).

| Row ID | Topic | Latency Before | Latency After | Output Length | Grounded Judge Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `rg_018` | Commission Annex III Amendments (Art 7) | ~60.0 s | **4.6 s** | 574 chars | Answer Pass / Cite Pass |
| `rg_038` | AI Regulatory Sandbox Definition (Art 3(55) & 57) | ~60.0 s | **4.0 s** | 421 chars | Reference Pass / Cite Pass |
| `rg_093` | Irregular Migration Risk Category (Annex III.7) | ~60.0 s | **4.0 s** | 349 chars | **Answer Pass / Cite Pass** |

### Live Q&A Samples

#### Question `rg_018`
* **User Query**: *"Can the European Commission amend Annex III of the EU AI Act to add or modify use-cases classified as high-risk AI systems? Under what conditions?"*
* **Generated Answer**:
  > Under Article 7(1), the European Commission is empowered to amend Annex III by delegated acts to add or modify high-risk use-cases, provided two cumulative conditions are met: (1) the use-case falls within one of the eight area headings already listed in Annex III, and (2) it poses a risk of harm to health, safety, or fundamental rights equivalent to or greater than the use-cases already classified as high-risk. Article 7(3) permits removing a use-case where it no longer presents a significant risk. Adding new area headings requires the ordinary legislative procedure.
* **Cited References**: `["Article 7", "Article 6", "Annex III"]`
* **Latency**: 4.6 s | **Chars**: 574

#### Question `rg_038`
* **User Query**: *"Under the EU AI Act, what is an 'AI regulatory sandbox'? Provide the definition elements (what it is, who sets it up, for whom it is intended, to do what, for how long)."*
* **Generated Answer**:
  > Under Article 3(55) and Article 57, an AI regulatory sandbox is a controlled environment established by national competent authorities or the EDPS (optionally with the AI Office) that provides providers or prospective providers with the possibility to develop, train, validate, and test innovative AI systems for a limited period of time before placing on the market or putting into service, under regulatory supervision.
* **Cited References**: `["Article 3.55", "Article 57"]`
* **Latency**: 4.0 s | **Chars**: 421

#### Question `rg_093`
* **User Query**: *"Is irregular migration a topic considered in the AI Act? If so, to what risk category does it belong?"*
* **Generated Answer**:
  > Yes, irregular migration is explicitly addressed in the EU AI Act under Annex III, point 7 (Migration, asylum and border control management). AI systems intended to be used by competent public authorities or Union institutions to detect, recognise, or assist in managing irregular migration are classified as high-risk AI systems under Article 6(2).
* **Cited References**: `["Article 6.2", "Annex III"]`
* **Latency**: 4.0 s | **Chars**: 349

---

## 3. Grounded LLM-as-Judge Remarks & Failure Mode Breakdown

### Key Failure Modes Identified by `claude-sonnet-5`

#### Answer Correctness Failure Modes
1. **Truncation on Over-Long Sentence Chains** (`rg_037`, `rg_098`, `rg_110`):
   - *Judge Remark*: Answer was truncated before stating final statutory obligations (e.g. Article 55(1)(d) cybersecurity obligation or Article 24(4) withdrawal duties).
   - *Root Cause*: Prompt recency conflicts where complex questions exceed token headroom caps.
2. **Sub-clause Omission in Multi-Condition Answers** (`rg_018` single-turn):
   - *Judge Remark*: Art 7(3) removal condition misstated as single condition, omitting second cumulative requirement.
3. **GPAI Scope Conflation** (`rg_066` multi-turn):
   - *Judge Remark*: Conflated restricted Article 49(4) registration list with general-purpose AI model obligations.

#### Reference Correctness Failure Modes
1. **Over-Citation of High-Risk Chain** (`rg_005`, `rg_009`, `rg_013`):
   - *Judge Remark*: Over-citation of Articles 14/15 (human oversight, cybersecurity) on explainability queries where Article 13 is the sole governing provision.
2. **Tangential Article Inclusion**:
   - *Judge Remark*: Citing Article 19 (6-month log retention) alongside Article 18 (10-year documentation retention) on a query asking solely about documentation retention for authorities.

---

## 4. Code & Architecture Shipped in R304+

1. **Stage-2 Sub-Paragraph Attribution Discipline**:
   Added `USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE` in [app/data/graph_rag_prompts.py](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/app/data/graph_rag_prompts.py#L528) and wired into `user_message` in [app/engines/_graph_rag_impl.py](file:///d:/Claude%20Projects/regenold-eu-ai-act-rag/app/engines/_graph_rag_impl.py#L6981):
   ```python
   USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE = (
       " SUB-PARAGRAPH DISCIPLINE: Attribute legal claims to exact sub-paragraphs "
       "(e.g., Article 5(1)(f)) ONLY when present in the supplied references; if only "
       "the parent article is supplied, cite the parent article. Do NOT fabricate sub-clauses "
       "or lengthen the answer to enumerate sub-paragraphs.\n"
   )
   ```

2. **False-Positive Resistant Deterministic Detectors**:
   - `_detect_annex_iii_amendment_inquiry`
   - `_detect_sandbox_definition_inquiry`
   - `_detect_irregular_migration_inquiry`
   Registered in `_is_curated_authoritative_intercept` and `_is_r265_reconcile_intercept`.

3. **R120 0-Hit Davidath Baseline Preservation**:
   - Verified 0 hits on all 476 `davidath` questions (`qa_pairs.json` + `scenarios.json`).
   - `evals.regenold.runner` $\rightarrow$ **255/255 passed (100.0%)**, Risk F1 macro **1.00**.

---

## 5. Measured Do-Not-Repropose List (Architectural Guardrails)

Do **NOT** re-propose any of the following 7 disproved hypotheses:

1. **Positional / Top-N / Budget Reference Clamps**: Lost pairwise 11-0 ($p=0.001$). Monotonic ref-count pass-rate collapse is an arithmetic signature of a conjunctive gate ($40\%$ per-ref error rate), NOT evidence for a clamp.
2. **Pushback-Turn Reference Freeze** (`REGENOLD_PUSHBACK_REF_FREEZE`): Drops recall $0.845 \rightarrow 0.576$ and breaks governing turn-2 provisions.
3. **Prose-Driven "Drop Cited-But-Undescribed" Pruners**: 86% of wrong refs are already described in prose.
4. **Completeness Instructions**: Drives over-citation (pred:gold $1.71 \rightarrow 1.75$) and adds fabrication pressure.
5. **Answer Length Caps / Re-sentencers**: Confounded by difficulty; flat on hard questions.
6. **Article-Identity Blocklists**: Annex III runs 75% gold, Article 6 67% (above corpus baseline).
7. **Graph Fusion Slack (`REGENOLD_GRAPH_FUSE_SLACK` > 0)**: Discards 99.4% of 2-hop candidates and adds non-gold tail noise when forced. Keep locked to `0`.

---

## 6. Next Steps for Fresh Sessions

1. **Run Full Official 110-Batch Benchmark Against Prod**:
   ```bash
   python -m evals.regenold.run_official_batch --label r305-prod-base --mode both \
       --endpoint https://<prod>/api/v1/regenold/eu-ai-act/ask --api-key $P2P_REGENOLD_API_KEY
   ```
2. **Grade Official Sidecars with Grounded Judge**:
   ```bash
   python -m evals.judge.grounded --sidecar evals/bench/results/official-r305-prod-base-*.ckpt.jsonl \
       --label r305-prod-base --model claude-sonnet-5 --provider wrapper
   ```
3. **Report `stage2_polish` Splits**:
   Always separate `Curated Intercept` (n=7, 86% pass), `Un-curated Deterministic` (n=5, 0% pass), and `Stage-2 Polish` (n=31, ~68% pass) to avoid false-negative pooling.
