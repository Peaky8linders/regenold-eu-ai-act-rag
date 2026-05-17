# R44 — Eval landscape survey for legal RAG (2024–2026)

Survey scope: state-of-the-art academic + industry evaluation surfaces for hard
legislative-text RAG, mapped against our current
[`evals/bench/`](../../../evals/bench/) harness (davidath + AIReg-Bench
projection + holdout + probe + MTRAG + prod-replay).

## 1. Landscape map

### 1.1 Legal-domain benchmarks

| Benchmark | Shape | License | Overlap with our rubric | Untapped axis |
| --- | --- | --- | --- | --- |
| **LegalBench** (Stanford, 162 tasks, NeurIPS 2023 Datasets) | 6 reasoning skill types — Issue-Spotting / Rule-Recall / Rule-Application / Rule-Conclusion / Interpretation / Rhetorical-Analysis | CC-BY-4.0, [HF: nguha/legalbench](https://huggingface.co/datasets/nguha/legalbench) | Loose / Strict Ans Correctness overlaps Rule-Recall + Rule-Application | **Interpretation** + **Rhetorical Analysis** — neither axis exists in davidath. Has a `rule_qa` subtask the bundle could project against. |
| **LexGLUE** (coastalcph, ACL 2022) | 7 tasks; **EUR-LEX** subtask = EU legal doc multi-label classification over EuroVoc concepts | CC-BY-4.0, [HF: coastalcph/lex_glue](https://huggingface.co/datasets/coastalcph/lex_glue) | Partial (EUR-LEX is classification, our wire is QA) | **EuroVoc concept assignment accuracy** — semantic tagging axis we don't measure. Out-of-shape for wire. |
| **EUR-Lex-Sum** (dennlinger, EMNLP 2023) | Multilingual summarisation of EU legal acts, 24 langs | CC-BY-4.0, [HF: dennlinger/eur-lex-sum](https://huggingface.co/datasets/dennlinger/eur-lex-sum) | None — our wire emits answers, not summaries | Out-of-shape; skip. |
| **AIReg-Bench** (camlsys, arXiv 2510.01474, 2025) | 120 HRAIS documentation excerpts × 3 legal-expert annotators × Likert 1–5 compliance probability over Arts. 9/10/12/14/15 | HF `camlsys/AIReg-Bench`, code MIT | Partial — we project against it but our scoring is binary | **Likert-scale compliance probability** — graded-judgement axis with inter-annotator agreement, which our binary refs-vs-gold can't match | 
| **COLIEE 2025** (Task 3 statute retrieval over Japanese Civil Code, ICAIL 2025) | 73 test Qs, gold 1–3 articles each, JP bar exam derived | Application-gated, NII Tokyo | Strong overlap with our Ref Correctness | **Multi-article gold cardinality is fixed** — gives a cleaner micro-F1@K signal than davidath's variable cardinality. Access friction is real. |
| **CUAD** (Hendrycks et al., NeurIPS 2021) | Contract clause extraction | CC-BY-4.0 | Out-of-shape (contracts ≠ regulation) | Skip. |
| **CaseHOLD** (in LegalBench) | Multi-choice case-holding identification | CC-BY-4.0 | Out-of-shape (US case law) | Skip. |
| **BillSum / EUR-Lex-Sum / LegalSum** | Summarisation | various | Out-of-shape | Skip. |
| **AI Act Evaluation Benchmark** (davidath, arXiv 2603.09435) | 137 QA + 339 scenarios — our primary bench | HF `davidath/ai-act-evaluation-benchmark` | Fully wired | — |

**Take-aways for legal-domain benchmarks**: the highest-leverage untapped
surface is **AIReg-Bench's Likert grading** + **COLIEE-style fixed-cardinality
F1@K** + the **LegalBench `rule_qa` + Rule-Application subtasks** (most
projectable onto our wire without reshaping it).

### 1.2 Citation-faithfulness evaluation methodologies

This is the most under-tapped layer in our current harness. Our refs-vs-gold
Jaccard is **set-similarity against a gold list**; the literature has moved
to **NLI-grounded sentence-level attribution** with separate recall +
precision sub-metrics.

| Methodology | Citation | Approach | Implementation cost |
| --- | --- | --- | --- |
| **ALCE** ([Gao et al., EMNLP 2023, princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE)) | Citation Recall (does every claim have a supporting citation entailed by an NLI model?) + Citation Precision (does each citation actually entail the sentence it's attached to?) | NLI model judges sentence–passage entailment; aggregate to F1 | NLI model dependency (TRUE / T5-NLI / GPT-judge); we'd ship a deterministic substitute |
| **LongBench-Cite + LongCite** ([Zhang et al., 2024](https://arxiv.org/html/2409.02897v3)) | **Sentence-level citation F1** computed against fine-grained spans (not just article numbers) | Same NLI shape, finer granularity | High cost; gold span annotation needed |
| **RAGCHECKER** (NeurIPS 2024 D&B Track) | Decomposes faithfulness into 10 sub-metrics including **noise sensitivity**, **hallucination rate**, **citation faithfulness** | Pipeline-level diagnostic | Heavy; LLM-judge required |
| **FACTUM** (arXiv 2601.05866, 2026) | **Mechanistic** citation-hallucination detection — flags refs not entailed by KB | Probes hidden states | Out-of-scope for deterministic engine |
| **CiteVerifier** (ICCS 2025) | Verifies whether the cited authority actually supports the claim | NLI + retrieval-loop | Mid cost |
| **Stanford Legal RAG Hallucinations study** (J. Emp. Legal Stud. 2025) | Two-dimensional framework: **correctness** × **groundedness**. Lexis+/Westlaw/GPT-4 hallucinate 17%/33%/43% | Manual audit + typology | Diagnostic shape, not bench-runnable |

**Take-away**: ALCE's two-axis decomposition (Citation Recall +
Citation Precision via NLI entailment) is the single most-cited
methodology and the easiest to project onto our wire. Our existing
gold list + the BM25 corpus + a deterministic entailment proxy
(token-overlap floor + xref-graph adjacency) can stand in for the
NLI model without shipping torch.

### 1.3 Refusal-correctness + scope-gate benchmarks

| Benchmark | Coverage | License | Status in bundle |
| --- | --- | --- | --- |
| **`dam9/eu-ai-act-red-teaming-v1`** (HF) | 100 adversarial prompts probing scope-gate refusal | Research-use | Listed in CLAUDE.md round 32; **not wired** |
| **RedBench** (arXiv 2601.03699) | 37 aggregated red-team datasets | MIT | General-purpose, not legal-shaped |
| **CoCoNot, ORBench, SGXTest, XSTest** | Refusal over-defence on benign prompts | various | Adjacent — measures `over-refusal`, the inverse of our scope-gate concern |
| **HarmBench** | Harmful behaviour evaluation | MIT | Out-of-scope (we don't generate harm; we refuse domain-irrelevant) |
| **"Red Teaming AI Policy: Taxonomy of Avoision and the EU AI Act"** (FAccT 2025, arXiv 2506.01931) | Taxonomy of legal-avoision strategies | n/a (paper) | Diagnostic framework, not a bench |

**Take-away**: the R34 P0 false-positive blocker (scope.py "withdraw" /
"certificate" / "designate" / "suspend" matching off-topic queries)
proved we lack regression coverage on refusal. `dam9/eu-ai-act-red-teaming-v1`
is the canonical fit and **already on the queue but not landed**.

### 1.4 Multi-turn legal coherence

| Benchmark | Coverage | License | Status |
| --- | --- | --- | --- |
| **MTRAG** ([IBM, TACL 2025, GH `IBM/mt-rag-benchmark`](https://github.com/IBM/mt-rag-benchmark)) | 110 conversations × 7.7 turns avg over 4 domains incl. **government knowledge**; deliberately partial / unanswerable turns | Apache-2.0 | Bundle has `mtrag.py` but lightly used |
| **MTRAGEval** at SemEval 2026 | Live task; evaluates clarification asking + "I don't know" handling | Same | Not wired |
| **LFQA-E** (arXiv 2410.01945) | 1,625 long-form QA pairwise comparisons | MIT | Out-of-shape (general LFQA) |

**Take-away**: MTRAG's **unanswerable + underspecified + non-standalone**
sub-categories map cleanly onto our scope.py and conversation-history-injection
hardening. Wiring it raises coverage without rewriting our harness.

### 1.5 Production-quality eval tooling

| Framework | Strength | Weakness for our use | Verdict |
| --- | --- | --- | --- |
| **Ragas** (arXiv 2309.15217, EACL 2024) | Reference-free Faithfulness / Answer Relevancy / Context Precision / Context Recall — **LLM-judge**-based | Faithfulness scoring uses a remote LLM judge; our wire is deterministic + sub-10ms p50, adding Ragas adds 1–3s/query | Adopt **only** as an offline reporting pass alongside the bench; not as a wire metric |
| **DeepEval** (Confident AI) | 50+ unit-test-style metrics, CI/CD integration, pytest-shaped | Heavy LLM-judge dependency; legal-domain metrics missing | Adopt as a **CI gate** layer if we want red/green PR signals beyond our delta table |
| **TruLens** (Snowflake/TruEra) | OpenTelemetry tracing + feedback functions for production sampling | Built for online RAG monitoring, not bench-time scoring | Wrong shape for our offline scorecard story |
| **LangSmith** | Polished SaaS observability | LangChain-coupled; we don't run LangChain | Skip |
| **HuggingFace `evaluate`** | Standard metric library | No legal-domain metrics | We already use Jaccard / token-overlap directly |

**Take-away**: industry consensus is **Ragas for dev + DeepEval as CI
gate + TruLens for prod**. For our deterministic competition wire the
ROI of any of these is low: they're all LLM-judge-based, expensive,
and don't beat hand-rolled token metrics on the davidath shape. But
**Ragas's Faithfulness metric** is the only off-the-shelf scorer that
projects cleanly onto the gap our rubric has (claim-level grounding).

## 2. Top 5 evaluation gaps in our current surface

Ranked by predicted competition signal.

### Gap 1 — Sentence-level citation faithfulness (Citation Precision)
Our `Ref Correctness Strict` measures set-similarity of refs vs gold.
It does NOT measure whether the **answer prose actually uses** the
cited refs. A response that surfaces 8 correct refs but whose
sentences would survive with refs stripped scores identically to a
response whose sentences each anchor to a cite. The literature
(ALCE) splits this as **Citation Precision** (per-cite: does it entail
its attached sentence?) and **Citation Recall** (per-claim: is it
backed by ≥1 cite?). Both are absent.
**Closes via**: ALCE-style two-axis citation scoring, deterministic NLI proxy.

### Gap 2 — Refusal correctness on adversarial out-of-scope prompts
R34's P0 release-blocker (scope.py false-positives on "queen withdraw",
"birth certificate", "Netflix subscription") had **zero bench coverage**.
A regression there is invisible until production. `dam9/eu-ai-act-red-teaming-v1`
+ a tiny hand-curated false-positive fixture set would close this.
**Closes via**: wire `dam9/eu-ai-act-red-teaming-v1` HF dataset + a 20-row
false-positive fixture covering the R34 patterns; score refusal precision/recall.

### Gap 3 — Multi-turn unanswerable / clarification handling
Our MTRAG harness exists but is "lightly used" per CLAUDE.md. MTRAG-UN
covers exactly the failure modes our scope-gate worries about: turns
that are individually out-of-scope but become in-scope under coref, and
turns that need clarification rather than confident answers. The R34
conversation-history-injection vulnerability would have been caught.
**Closes via**: load MTRAG `government` slice (the closest of its 4
domains) + measure: clarification-asking rate, abstain-correctness,
coreference-rescue accuracy.

### Gap 4 — Likert-scale compliance probability (AIReg-Bench native)
Our AIReg-Bench projection scores against article references (because
that's what our wire returns). The native metric is **Likert 1–5
compliance probability with inter-annotator agreement**. We don't
emit a compliance probability so we can't score it natively today.
Adding a `compliance_probability` field to the wire response would
unlock the native AIReg-Bench axis and a competition story ("we
match legal-expert Likert to within ±0.7").
**Closes via**: extending the wire schema (1 field) + a deterministic
verdict→probability map keyed off the CLARA Verdict.confidence.

### Gap 5 — Citation hallucination rate against ARTICLE_EXISTENCE
We assert `_ARTICLE_OUTPUT_RE` shape validity but never measure the
rate at which the engine wants to cite a non-existent provision (the
hard-rule lint floor catches the call but doesn't surface "how often
were we tempted"). The Stanford Legal RAG study reports 17–43%
hallucination rates on commercial tools — the implicit story is that
our deterministic engine is **fundamentally** lower, but we can't
prove it without measuring.
**Closes via**: a 10-line counter in the runner that records every
suppressed-by-`ARTICLE_EXISTENCE` candidate, reports rate per axis.

## 3. Top 3 axes we already cover well

1. **Ref Correctness Loose + Strict** — covered by both the davidath
   in-sample bench and the AIReg-Bench projection. Cumulative
   +24% / +13% relative since R28 (CLAUDE.md). Saturated for our
   purposes.
2. **Latency p50/p95** — sub-10ms determinism is comfortably ahead of
   the rubric budget; further compression isn't worth more measurement
   surface.
3. **Regulatory Tone** — heuristic scorer pegged at 1.0 across rounds.
   The rubric weight is small and ours is saturated; no need for a
   transformer-based tone scorer.

## 4. One-paragraph recommendation

**Build a home-grown ALCE-style Citation Faithfulness evaluator
(Gap 1) and wire `dam9/eu-ai-act-red-teaming-v1` for refusal
correctness (Gap 2).** Both fit inside 500 LOC and lift the
competition story on the two rubric blind-spots that the davidath
bench cannot expose. The Citation Faithfulness module reads our
existing `(answer, references)` pair, splits the answer into
sentences (we already have `app/engines/sentence_index.py`), and
scores each sentence × each ref pair under a **deterministic NLI
proxy**: token-overlap floor of 0.15 + xref-graph 1-hop adjacency
+ explicit-anchor match. Aggregate to Citation Recall (claims with
≥1 supporting cite) and Citation Precision (cites whose attached
sentence has overlap above the floor). The refusal module is a
straight HF download + score-vs-gold-refusal pass, ~80 LOC, and
gives us a single number ("refusal correctness 0.92") to report
alongside the existing axes. **Skip the third-party frameworks**
(Ragas/DeepEval/TruLens): they're LLM-judge-based, add seconds
per query, and don't beat hand-rolled metrics for our deterministic
wire — adopt them only as offline reporting if a Regenold judge asks
for "industry-standard" metrics, where Ragas's Faithfulness scorer
runs in ≤30 minutes over the full 476-item bench in a separate
non-blocking job. The ALCE+refusal combo gives us a measurable
+axis competition lift; the AIReg-Bench Likert work (Gap 4) is the
follow-up round once the wire schema gets a `compliance_probability`
field, and the citation-hallucination counter (Gap 5) is a 10-line
add to the runner that we can ship in the same PR for free.

## Sources

- [ALCE: Enabling LLMs to Generate Text with Citations (Gao et al., EMNLP 2023)](https://arxiv.org/abs/2305.14627) + [princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE)
- [LongCite + LongBench-Cite (arXiv 2409.02897v3)](https://arxiv.org/html/2409.02897v3)
- [LegalBench (NeurIPS 2023, arXiv 2308.11462)](https://arxiv.org/abs/2308.11462) + [HF: nguha/legalbench](https://huggingface.co/datasets/nguha/legalbench)
- [LexGLUE (ACL 2022)](https://aclanthology.org/2022.acl-long.297.pdf) + [HF: coastalcph/lex_glue](https://huggingface.co/datasets/coastalcph/lex_glue)
- [EUR-Lex-Sum (HF: dennlinger/eur-lex-sum)](https://huggingface.co/datasets/dennlinger/eur-lex-sum)
- [AIReg-Bench (arXiv 2510.01474)](https://arxiv.org/abs/2510.01474) + [camlsys/AIReg-Bench](https://huggingface.co/datasets/camlsys/AIReg-Bench)
- [COLIEE 2025 overview (Springer)](https://link.springer.com/article/10.1007/s12626-026-00199-9) + [coliee.org](https://coliee.org/overview)
- [Ragas (arXiv 2309.15217, EACL 2024)](https://arxiv.org/abs/2309.15217)
- [MTRAG (IBM, TACL 2025, arXiv 2501.03468)](https://arxiv.org/html/2501.03468v1) + [IBM/mt-rag-benchmark](https://github.com/IBM/mt-rag-benchmark)
- [Red Teaming AI Policy: Avoision Taxonomy (FAccT 2025, arXiv 2506.01931)](https://arxiv.org/abs/2506.01931)
- [Stanford Legal RAG Hallucinations (J. Emp. Legal Stud. 2025)](https://law.stanford.edu/wp-content/uploads/2024/05/Legal_RAG_Hallucinations.pdf)
- [RAGCHECKER (NeurIPS 2024)](https://proceedings.neurips.cc/paper_files/paper/2024/file/27245589131d17368cccdfa990cbf16e-Paper-Datasets_and_Benchmarks_Track.pdf)
- [LFQA-E (arXiv 2410.01945)](https://arxiv.org/abs/2410.01945)
- [LLM Eval Framework Comparison 2025/2026 (Medium / Atlan / Confident AI)](https://atlan.com/know/llm-evaluation-frameworks-compared/)
- [FACTUM citation hallucination detection (arXiv 2601.05866)](https://arxiv.org/pdf/2601.05866)
- [CiteVerifier (ICCS 2025)](https://www.iccs-meeting.org/archive/iccs2025/papers/159110235.pdf)
