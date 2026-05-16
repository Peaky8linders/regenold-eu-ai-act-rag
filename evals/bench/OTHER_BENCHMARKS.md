# Other Public EU AI Act Benchmarks — Market Research

**Date:** 2026-05-16
**Goal:** Find public EU AI Act benchmarks beyond `davidath/ai-act-evaluation-benchmark` so we can validate generalization across the Regenold rubric (correctness/conciseness/refs/tone/latency/multi-turn).

## TL;DR table

| # | Name | Size | License | Last update | Priority | One-line fit |
|---|------|------|---------|-------------|----------|--------------|
| 1 | **camlsys/AIReg-Bench** | 300 docs + 120×3 human annotations + LLM annotations | CC-BY-4.0 | Feb 2026 (v3) | **HIGH** | Document-level HRAIS compliance scoring against Arts. 9/10/12/14/15. Expert human gold. |
| 2 | **dam9/eu-ai-act-red-teaming-v1** | 100 adversarial prompts | Research-only ⚠️ | Jan 2026 | **HIGH** | Tests *refusal correctness* on Art. 5/6/52 violation prompts. Pairs perfectly with our scope-gate + prohibited gatekeeper. |
| 3 | **suhas-km/EU-AI-Act-Flagged** | 100K–1M items | MIT | 2025 | **MED** | Large-scale, but viewer is broken — sample first. |
| 4 | **AlexL115/AIAct** | 184 QA items | MIT | 2024–2025 | **MED** | Small SQuAD-shape over AI Act text. Quick smoke test, no refs field. |
| 5 | **compl-ai/compl-ai** | 27+ task framework | Apache 2.0 | active | **LOW** | Model-level safety/bias — out of rubric scope. |
| 6 | **Orcawise/...gemma** training data | 1023 QA pairs (claimed) | Not released | n/a | **SKIP** | Never published. |

The EU-AI-Act eval space is **sparse and recent** — most landed Oct 2025 – Feb 2026. Only two are genuinely complementary to davidath; the rest either overlap, have data issues, or are out-of-scope for our wire contract.

---

## Per-benchmark detail

### 1. AIReg-Bench (Marino et al., camlsys — Cambridge ML Systems group)

- **HF:** https://huggingface.co/datasets/camlsys/AIReg-Bench
- **Paper:** [arXiv:2510.01474](https://arxiv.org/abs/2510.01474) "AIReg-Bench: Benchmarking Language Models That Assess AI Regulation Compliance" (v1 Oct 2025, v3 Feb 2026)
- **GitHub:** https://github.com/camlsys/aireg-bench
- **Size:** 300 technical-documentation `.txt` excerpts + 120 of them human-graded × 3 annotators each.
- **Schema:** `compliance_score` (1–5), `plausibility_score` (1–5), `explanation` (str).
- **License:** CC-BY-4.0 (dataset) — permissive, attribution required.
- **Articles covered:** Arts. 9 (RMS), 10 (data governance), 12 (logging), 14 (human oversight), 15 (accuracy/robustness/security). Targets HRAIS under Art. 6 + Annex III.
- **Why useful:** Only AI-Act benchmark with **expert-human gold labels**. Hits the *exact 5 articles* Regenold concentrates on. Asks a different question shape than davidath — generalization probe for our role×risk obligation matrix.
- **Fetch:**
  ```python
  from datasets import load_dataset
  human = load_dataset("camlsys/AIReg-Bench", data_files="human_annotations.parquet", split="train")
  from huggingface_hub import snapshot_download
  local = snapshot_download(repo_id="camlsys/AIReg-Bench", repo_type="dataset")
  ```
- **Gotchas:** Output is 1–5 score + explanation, not citations. Wire as: `f"Is this AI-system technical documentation compliant with Article {N} of the EU AI Act?\n\n{excerpt}"`. Bucket scores → verdict. Gold ref = `[f"Article {N}"]`.

### 2. dam9/eu-ai-act-red-teaming-v1

- **HF:** https://huggingface.co/datasets/dam9/eu-ai-act-red-teaming-v1
- **Size:** 100 adversarial prompts. JSONL, 236 kB. 61 Art. 5 / 31 Art. 6 / 1 Art. 52 / 8 general.
- **Format:** JSONL with `prompt`, `intent`, `regulatory_risk`, `bypass_probability`, `regulatory_context.{primary_article, all_articles}`, `success_criteria.pass_if_contains`.
- **License:** **Research Use Only** ⚠️ — internal eval only, don't redistribute.
- **Why useful:** Only public dataset that tests scope-gate refusal. GPT-4 + Copilot have 100% bypass on "Financial Inclusion" framings — fertile differentiation.
- **Fetch:**
  ```python
  from huggingface_hub import hf_hub_download
  path = hf_hub_download(
      repo_id="dam9/eu-ai-act-red-teaming-v1",
      filename="red_teaming_dataset_100_prompts_packaged.jsonl",
      repo_type="dataset",
  )
  ```
- **Gotchas:** Convert article refs (`"Article_5"` → `"Article 5"`). Stratify by `bypass_probability`. Keep raw prompts out of audit chain (env-gated via `REGENOLD_REDTEAM_BENCH=1`).

### 3. suhas-km/EU-AI-Act-Flagged

- **HF:** https://huggingface.co/datasets/suhas-km/EU-AI-Act-Flagged
- **Size:** 100K–1M (claimed) but viewer broken (JSON parse error on `violation`).
- **License:** MIT ✓.
- **Gotchas:** **Sample 20 items by hand first.** If salvageable, scale would finally let us trust ±0.005 deltas.

### 4. AlexL115/AIAct

- **HF:** https://huggingface.co/datasets/AlexL115/AIAct
- **Size:** 184 rows SQuAD-shape, single `train` split.
- **License:** MIT ✓.
- **Gotchas:** No `references` field — synthesize gold refs by matching `context` to `ARTICLE_FULL_TEXT`. Good fast smoke-test.

### 5. compl-ai/compl-ai (out of scope)

- Tests *model-level* properties (bias, safety, robustness) — not RAG over the Act. Skip.

### 6. Orcawise (never released)

- Skip.

### Also evaluated and excluded

- **laredoyin/eu-ai-act** — full text only, already covered by Ansvar-Systems corpus
- **hoololi/AI_Act_with_embeddings** — embeddings, not a benchmark
- **kenobijr/eu-ai-act-chromadb** — pickled DB, no schema
- **SdSarthak/AegisAI** — 75 rows, AGPL-3.0 (toxic)
- **Francesco-Sovrano/...DocAssessment** — replication package, no Q&A
- **isaacus/legal-rag-bench** — Victorian Australian law, zero EU AI Act

---

## Recommended integration plan

**Round 32 ships AIReg-Bench (#1) + dam9 red-teaming (#2) wired into `evals/bench/runner.py`.**

### Wire 1 — AIReg-Bench → `evals/bench/aireg_bench.py`
- Single-turn message: `f"Is this AI-system technical documentation compliant with Article {N}?\n\n{excerpt}"`
- Gold answer = median of 3 human scores bucketed to verdict
- Gold refs = `[f"Article {N}"]`
- Score: Ans Correctness Strict, Ref Correctness Loose/Strict, Conciseness, Tone

### Wire 2 — dam9 red-teaming → `evals/bench/redteam_bench.py`
- 1:1 mapping with article-ref normalization
- New axis: **Refusal Correctness** (`pass_if_contains` match)
- Env-gated `REGENOLD_REDTEAM_BENCH=1` (research-only license)

### Defer to Round 33+
- suhas-km — sample first
- AlexL115 — wire as CI smoke test
- Compl-AI — only if Regenold rubric extends to model-level

## Sources

- [camlsys/AIReg-Bench (HF)](https://huggingface.co/datasets/camlsys/AIReg-Bench) · [arXiv:2510.01474](https://arxiv.org/abs/2510.01474) · [GitHub](https://github.com/camlsys/aireg-bench)
- [dam9/eu-ai-act-red-teaming-v1 (HF)](https://huggingface.co/datasets/dam9/eu-ai-act-red-teaming-v1)
- [suhas-km/EU-AI-Act-Flagged (HF)](https://huggingface.co/datasets/suhas-km/EU-AI-Act-Flagged)
- [AlexL115/AIAct (HF)](https://huggingface.co/datasets/AlexL115/AIAct)
- [compl-ai/compl-ai (GitHub)](https://github.com/compl-ai/compl-ai) · [arXiv:2410.07959](https://arxiv.org/abs/2410.07959) · [Leaderboard](https://huggingface.co/spaces/latticeflow/compl-ai-board)
- [Davvetas et al. — AI Act Evaluation Benchmark (arXiv:2603.09435)](https://arxiv.org/abs/2603.09435)
- [davidath/ai-act-evaluation-benchmark (GitHub)](https://github.com/davidath/ai-act-evaluation-benchmark)
