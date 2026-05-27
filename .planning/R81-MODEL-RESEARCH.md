# R81 — Pretrained EU-AI-Act LLM vs cheap fine-tune research

**Date**: 2026-05-23
**Scope**: Can Regenold get off the Claude Max wrapper / per-token Anthropic spend by (a) using a pretrained legal/regulatory LLM, or (b) cheaply fine-tuning our own model on serverless GPU?
**Status**: Research only — no code changes.

---

## 1. Executive summary

**Verdict: keep Anthropic (or migrate to Groq Llama 3.3 70B for Stage-2). Do NOT fine-tune yet, and do NOT switch to a "legal" LLM.**

1. **No pretrained EU-AI-Act-aware LLM exists** that is fit for production. SaulLM-141B (Equall.ai, July 2024) is the closest "legal" model but (a) it has not been benchmarked on the EU AI Act specifically, (b) it has 94 monthly HF downloads (effectively abandoned), (c) no managed inference endpoint, and (d) the broader pattern is consistent: **domain fine-tunes beat frontier models on classification but lose on reasoning** — which is exactly what Regenold needs ([Awesome Agents LegalBench leaderboard, Apr 2026](https://awesomeagents.ai/leaderboards/legal-llm-leaderboard/)).
2. **Fine-tuning is technically cheap (~$10–$50) but rubric-risky.** A LoRA fine-tune of Llama 3.1 8B on the davidath benchmark + KB stubs would cost $10–$50 on Modal, but Regenold's deterministic pipeline already saturates BM25 on davidath — the open question is whether a fine-tuned 8B model can match Sonnet 4.6 on Regulatory Tone (currently 1.000) and judge refs-faithfulness. **Unproven, and the rubric weights tone heavily.**
3. **The current Anthropic-direct spend is already small** (~$10–$30/mo at projected production volume per CLAUDE.md R56). The Claude Max wrapper *is* the cost issue, not Anthropic. Fixing it doesn't require a new model — just flipping `P2P_GRAPH_RAG_PROVIDER=anthropic` (already wired, R56).
4. **The economically rational migration is Groq Llama 3.3 70B for Stage-2** (~$0.59/$0.79 per M tokens at 250+ tok/s, [Groq pricing](https://groq.com/pricing)). The bundle's Stage-0 path is already on Groq (R52); extending to Stage-2 is ~50 LOC of provider work, not a fine-tune.

**Top recommendation**: do a 100-row live A/B of Groq Llama 3.3 70B vs Anthropic Sonnet 4.6 at Stage-2 BEFORE spending any cycles on fine-tuning. If Groq passes the judge axes (tone ≥ 0.85, refs ≥ 0.50), the entire "fine-tune or use legal LLM" question is moot at 10× cheaper than Anthropic.

---

## 2. Q1 findings — Pretrained legal / regulatory LLMs

### 2.1 The candidates

| Model | Vendor | Size | Released | Licence | Trained on EU AI Act? | LegalBench (Vals.ai) | Avail. | Verdict |
|---|---|---|---|---|---|---|---|---|
| **SaulLM-141B-Instruct** | Equall.ai | 141B (Mixtral MoE) | Jul 2024 | MIT | No — general legal corpus, EU + US | "outperformed GPT-4 average across LegalBench" (vendor claim, no independent score) | HF weights only; 94 downloads/mo; **no inference provider** | **Not fit for production.** Self-host required (>250 GB VRAM), abandoned trajectory, no EU AI Act tuning. |
| **SaulLM-54B-Instruct** | Equall.ai | 54B (Mixtral) | Jul 2024 | MIT | No | Sub-141B; vendor-claimed > similar-sized open models | HF weights only | Same blockers as 141B; not Regenold-shaped. |
| **SaulLM-7B (Saul-Instruct-v1)** | Equall.ai | 7B (Mistral) | Mar 2024 | MIT | No | **50.5% LegalBench avg** ([gist benchmark](https://gist.github.com/Malikeh97/bf1ae452a93693cd0f606be49ad6f329)) | HF weights; runnable on 1× A10 | **Materially worse than frontier models** (Gemini 3.1 Pro 87.4%, GPT-5 80%, Claude 4 Opus 77%). |
| **Orcawise/eu_ai_act_using_finetuned_gemma** | Orcawise (community) | 2B (Gemma-2) | 2024 | Gemma | **Yes — 1,023 QA pairs** | None | HF weights; **5 downloads/mo** | First-mover demo, not production. 2B model + 1k examples ≠ rubric-grade. |
| **Timo Laine multilingual EU AI Act fine-tune** | Personal blog ([Medium, 2024](https://medium.com/@timo.au.laine/eu-ai-act-fine-tune-multilingual-local-llm-2c0657cc47f8)) | Gemma-2-2b-it | 2024 | Gemma | **Yes — 9,175 train + 2,456 eval QA pairs, EN/FI/SV** | None vs base | One-person SFT experiment, no published model weights | Useful *recipe* (9.8 h on 1 GPU = ~$15 on Modal); not a model to download. |
| **Harvey** | Harvey AI | Undisclosed | Closed | Commercial | Unknown (US-litigation-centric per [Harvey blog](https://www.harvey.ai/blog/introducing-biglaw-bench)) | Internal benchmark only | **Closed; enterprise sales only** | Not a Regenold-shaped vendor. |
| **Lexion** | Docusign | n/a | Closed | SaaS | No (contract review tool) | n/a | Closed; CLM product | Off-shape — contract-lifecycle product, not Q&A. |
| **COMPL-AI Framework** | LatticeFlow AI + ETH + INSAIT | Not a model — a *benchmark suite* | Oct 2024 | n/a | **Yes — tests LLMs against EU AI Act GPAI requirements** | n/a | [Public benchmark](https://www.deeplearning.ai/the-batch/compl-ai-study-measures-llms-compliance-with-eus-ai-act/) | **Useful for measuring**, not a model to use. |

### 2.2 The verdict on Q1

**There is no production-ready pretrained EU-AI-Act LLM in May 2026.** What exists is:

1. **Legal-domain general LLMs** (SaulLM family) that trained on European + US legal corpora but not the AI Act specifically. They beat similar-sized base models on narrow legal classification but **don't beat frontier models on open-ended legal reasoning** — and they have effectively no adoption (94 downloads/mo for the 141B flagship). The Apr 2026 Awesome Agents leaderboard headline: *"Domain fine-tunes beat frontier models on classification — lose on reasoning."*
2. **Community fine-tunes** specifically on EU AI Act (Orcawise Gemma-2b, Timo Laine multilingual Gemma-2b) that are demonstrations, not products. Tiny base models, small datasets, no public benchmarks, near-zero adoption.
3. **The COMPL-AI framework** ([LatticeFlow AI / ETH / INSAIT, Oct 2024](https://www.deeplearning.ai/the-batch/compl-ai-study-measures-llms-compliance-with-eus-ai-act/)) is a benchmark suite, not a model. It's useful as a *target* for Regenold to measure against, but doesn't give us a model to ship.

**RAG + general-purpose frontier LLM is the de-facto industry pattern in May 2026.** The Hugging Face EU AI Act developer guidance ([HF blog](https://huggingface.co/blog/eu-ai-act-for-oss-developers)) recommends RAG + documentation, not specialized models.

---

## 3. Q2 findings — Cheap fine-tune options

### 3.1 Serverless GPU pricing (May 2026)

| Provider | H100 (per hr) | A100 80GB (per hr) | Billing | Cold-start | Production multiplier | Free tier |
|---|---|---|---|---|---|---|
| **Modal.com** | **$3.95** (on-demand) ([pricing](https://modal.com/pricing)) | $2.50 | Per-second / per-ms, no idle | Sub-second w/ memory snapshots | **3× for non-preemptible** | $30/mo credits |
| **RunPod** | $2.69–$2.99 on-demand pods; **$5.59 serverless** | $1.19–$1.39 | Per-second | "20× more per GPU-hr serverless vs on-demand for sustained" | None | None |
| **Together AI** | $6.49 (dedicated, single-tenant) | n/a | Per-hour | n/a (managed FT) | None | "Start for free" |
| **Lambda Labs** | $3.78 SXM on-demand | $1.29 | Per-minute | n/a | None | None |
| **vast.ai** | ~$2.00–$3.00 | $0.52–$1.50 | Per-second (marketplace) | Variable | None | None |
| **Thunder Compute** | n/a | **$0.78** | Per-second | n/a | None | None |

**Modal is the user-recommended option.** Per-second billing, no idle charges, $30/mo free credits, sub-second cold-starts with their memory-snapshot system. The 3× production multiplier matters only if you opt out of preemption; LoRA fine-tuning is fine to preempt.

### 3.2 Fine-tune cost reality check (real numbers from cited articles)

| Recipe | GPU | Hours | Cost | Source |
|---|---|---|---|---|
| QLoRA Llama 3.1 8B on 50k examples | 1× A100 80GB | 6 h | **~$12** | [Modal blog](https://10xstudio.ai/blog/how-much-does-it-cost-to-finetune-llama-with-lora) |
| LoRA Llama 3.1 8B on 15k examples | 1× A100 80GB | ~3–4 h | **$8.32** | [Saturn Cloud](https://saturncloud.io/blog/finetune-llama-with-affordable-on-demand-h100-and-h200-gpu-instances/) |
| QLoRA Llama 3 8B "under $20" | 1× consumer | various | **<$20** | [Medium](https://medium.com/@velinxs/how-to-fine-tune-llms-for-under-20-step-by-step-c187a3059ca2) |
| QLoRA Llama 3 8B (4× H100 scaling) | 4× H100 | 1.25 h | **$25–$50** | [Philschmid blog](https://www.philschmid.de/fsdp-qlora-llama3) |
| Personal "I spent $47.23" Llama 3 LoRA | mixed | various | **$47** | [Techoc blog](https://techoc.blog/i-spent-47-23-fine-tuning-llama-3/) |
| Multilingual Gemma-2-2b SFT (EU AI Act, 9.8 h) | single A100 | 9.8 h | **~$15** | [Timo Laine Medium](https://medium.com/@timo.au.laine/eu-ai-act-fine-tune-multilingual-local-llm-2c0657cc47f8) |
| Together AI managed LoRA (≤16B model) | n/a | n/a | **$0.48 per M training tokens** | [Together AI pricing](https://www.together.ai/pricing) |

**Concrete cost projection for Regenold:**

Dataset shape: 137 davidath QA + 339 davidath scenarios + ~500 KB-stub-derived QA pairs = **~1,000–1,500 training examples**, each ~300–500 tokens → ~600k tokens total. At 5 epochs = 3M total training tokens.

- **Modal QLoRA Llama 3.1 8B**: ~2–3 h on 1× A100 = **$5–$10**
- **Together AI managed LoRA (Llama 3.1 8B)**: 3M tokens × $0.48 / M = **$1.44** (cheapest option, hands-free)
- **Modal QLoRA Llama 3.3 70B**: ~8–12 h on 1× H100 = **$35–$50** (or $100–$150 with 3× production multiplier — opt out of preemption only if needed)

**End-to-end ship-a-model budget (incl. data prep + experiments + eval): well under $200** for an 8B model; **under $1,000** for a 70B model.

### 3.3 Base model recommendation for Regenold's shape

| Base | Params | Why | Why not |
|---|---|---|---|
| **Llama 3.1 8B Instruct** | 8B | Most tutorials / tooling; cheap; runnable on 1× A10G/A100; widely supported by Modal/Together/Groq | May not match Sonnet on tone polish |
| **Llama 3.3 70B Instruct** | 70B | Already on Groq at $0.59/$0.79 per M; instruct-tuned for chat; matches the bundle's Stage-2 prompt shape | 8× more expensive to fine-tune AND to serve |
| **Mistral 7B v0.3** | 7B | Apache 2.0; faster; multilingual European emphasis | Smaller community in 2026, less Modal tooling |
| **Qwen 3 14B** | 14B | Strong reasoning; trails Llama 3.3 70B on legal but ~5× cheaper to fine-tune | Less mainstream; tooling thinner |
| **Gemma 2 9B** | 9B | Google legal preference; existing EU AI Act demo (Orcawise/Timo Laine both use Gemma) | Gemma licence restricts commercial redistribution |

**Recommendation for Regenold**: if fine-tuning, **start with Llama 3.1 8B via Together AI managed LoRA at $1.44 / training run**. Trivial cost, zero infra setup, one CLI command. The Modal H100 route is for once you've validated the recipe.

### 3.4 LoRA vs QLoRA vs full fine-tune

| Method | When | Cost | Quality |
|---|---|---|---|
| **QLoRA (4-bit)** | Default for <70B base | Cheapest (single-GPU 7B–13B viable) | Within 1–2% of LoRA on most tasks |
| **LoRA (16-bit)** | When QLoRA quality regresses | ~2–3× QLoRA | Slightly better than QLoRA, much better than full FT on small datasets |
| **Full fine-tune** | Never at our scale | 10–100× LoRA | **Worse** than LoRA when training set <100k examples (overfits) |

At our 1k–1.5k example scale, **QLoRA is correct** ([HJ Labs 2026 best-practices](https://hjlabs.in/AIML/blog/post/llm-fine-tuning-best-practices.html), [Philschmid](https://www.philschmid.de/fsdp-qlora-llama3)). Full fine-tune would overfit catastrophically.

---

## 4. Q3 findings — Inference cost projection

### 4.1 Projection: 1,000 requests/month × 500 tokens average

Realistic per-request shape from the bundle: ~1,500 input tokens (Stage-2 prompt header + refs + draft + question), ~150 output tokens (3-sentence polished answer). Total ~1,650 tokens per request × 1,000 = **1.65M tokens/month**.

| Path | Input $ | Output $ | Per-1,000-req cost | Cold-start | Throughput |
|---|---|---|---|---|---|
| **Claude Max wrapper** (current) | flat | flat | **~$200/mo subscription** (Pro $20/mo, tightening rate limits) | n/a | wrapper-limited |
| **Anthropic Sonnet 4.6 direct** | $3.00 / M | $15.00 / M | **$2.25 + $7.50 = ~$10/mo** | n/a | Anthropic API |
| **Anthropic Sonnet 4.6 + prompt cache** | $0.30 / M (cached) | $15.00 / M | **~$3–$5/mo** | n/a | Same |
| **Anthropic Opus 4.7 (R51 complex path)** | $5.00 / M | $25.00 / M | $3.75 + $12.50 = ~$16/mo (full); **~$3/mo at 20% gate** | n/a | Anthropic API |
| **Groq Llama 3.3 70B** | $0.59 / M | $0.79 / M | **$0.44 + $0.39 = ~$0.83/mo** ([Groq pricing](https://groq.com/pricing)) | n/a (managed) | **250+ tok/s** |
| **Deepinfra Llama 3.3 70B** | $0.23 / M | $0.40 / M | **$0.17 + $0.20 = ~$0.37/mo** ([AI Pricing Guru](https://www.aipricing.guru/meta-pricing/)) | n/a | ~60 tok/s |
| **Cerebras Llama 3.3 70B** | ~$0.60–$3.90 / M | same | **~$3–$5/mo** | n/a | **1,800 tok/s** (10× Groq, 30× GPU) |
| **Together AI hosted LoRA endpoint** (8B fine-tune) | $0.10 / M | $0.10 / M | **~$0.16/mo** | n/a (managed) | ~60 tok/s |
| **Modal serverless vLLM (own 8B fine-tune)** | n/a (GPU-time billing) | n/a | **~$5–$15/mo** at 1k req (mostly cold-start GPU minutes) | **8.7 s vLLM cold**, sub-second w/ memory snapshots | 100+ tok/s on H100 |
| **Modal hosted 24/7 H100** | n/a | n/a | $3.95 × 24 × 30 = **$2,844/mo** (never scales to zero) | None | 100+ tok/s |

### 4.2 The cost story is clearer than expected

* **Claude Max ($200/mo) is the only expensive path.** Every other option is <$20/mo at projected production volume.
* **Anthropic direct (Sonnet 4.6) is already cheap** at $10/mo with no prompt cache, ~$3–5/mo with the 90% cache discount. The Pro-downgrade rate-limit risk is the migration driver, not raw cost.
* **Groq Llama 3.3 70B is ~10× cheaper than Anthropic Sonnet** and the bundle's Stage-0 path already runs through it. Extending to Stage-2 is ~50 LOC.
* **Self-hosted fine-tune is 100× cheaper than Anthropic** ($0.16/mo via Together AI hosted LoRA endpoint) — but only IF the fine-tuned 8B matches quality, which is the open question.
* **Modal cold-start is real**: vLLM takes 8.7 seconds cold start ([Mark AI 2026 benchmark](https://markaicode.com/ollama-vs-vllm-performance/)). Memory snapshots help but require setup. For Regenold's bursty traffic pattern, Together AI hosted endpoints sidestep this entirely.
* **Modal 24/7 H100 is economically irrational** at our volume — $2,844/mo to serve 1,000 requests is $2.84/request.

### 4.3 The competition-rubric angle

Regenold is scored on **latency** (p50 + p95). Round 60+ measurements show:

* Live Anthropic Sonnet 4.6 via wrapper: **p50 ~5–17s, p95 ~25–35s** (CLAUDE.md R64-live, R69-live).
* Groq Llama 3.3 70B at 276 tok/s for ~150 output tokens: **~0.5s output + network ≈ p50 1–2s, p95 3–5s**. ~5× faster than Anthropic.
* Cerebras at 1,800 tok/s: **~80ms output + network ≈ p50 300ms, p95 1s**. ~50× faster than Anthropic.

**Switching Stage-2 from Anthropic → Groq could lift the latency axis materially with NO infra changes.** This was already queued as R51 work but never executed.

---

## 5. Q4 recommendation — Ranked actionable experiments

### Rank 1 (HIGHEST PRIORITY): **Groq Llama 3.3 70B Stage-2 A/B**

* **What**: ~50 LOC provider adapter mirroring `app/llm/openai_wrapper_provider.py`. Env-gated `P2P_GRAPH_RAG_PROVIDER=groq_llama_70b`. Wire into `_two_stage_generate` Stage-2 polish path only (Stage-0 already on Groq per R52).
* **Why**: Cheapest possible win. 10× cheaper than Anthropic ($0.83/mo vs $10/mo at projected volume), 5–10× faster latency p50, no fine-tune cycle needed, no GPU infra to manage. **The result of this experiment determines whether everything else matters.**
* **Cost**: $0 in compute (Groq pay-per-token, project volume <$1/mo). 1–2 engineering days.
* **Verification**: 100-row live A/B (R76 representative-100 protocol) + 4-axis LLM judge. Gate: judge tone ≥ 0.85 AND refs ≥ 0.50 AND conciseness ≥ 0.55. If passes → flip default. If fails on tone → keep Anthropic for Stage-2 (the tone calibration that the codebase relies on is Sonnet-tuned).
* **Risk**: Llama 3.3 70B may not match Sonnet on EU-regulator voice tone (judge has been pinning tone at 1.0; that's the production crown jewel). Mitigated by the env-gated rollout — if tone regresses, flip env back.
* **Source basis**: [Groq pricing](https://groq.com/pricing), [Artificial Analysis Groq benchmarks](https://artificialanalysis.ai/providers/groq), CLAUDE.md R52 (Groq Stage-0 already wired).

### Rank 2: **Together AI managed LoRA fine-tune of Llama 3.1 8B** ($1.44 one-time)

* **What**: Run `together fine-tuning create --model meta-llama/Llama-3.1-8B-Instruct-Reference --training-file regenold-eu-act.jsonl --method lora`. Dataset: 137 davidath QA + 339 scenarios + ~500 KB-stub-generated QA pairs (~1k–1.5k examples).
* **Why**: Cheapest possible fine-tune experiment ($1.44 of training tokens, $0.16/mo to serve). Validates whether a fine-tune of a small model can match Sonnet on the judge axes BEFORE we invest in Modal infra. Hosted LoRA endpoint inference at ~$0.10 / M tokens = effectively free at our volume.
* **Cost**: **$1.44 to train + ~$0.20/mo to serve**. 1 engineering day to prep dataset + run train + wire as a fourth `P2P_GRAPH_RAG_PROVIDER=together_lora` adapter.
* **Verification**: Same 100-row live A/B + judge. Gate: matches OR exceeds the Rank-1 (Groq) numbers AND beats them on at least one of conciseness / refs-faithfulness. If passes → ship as Stage-2 default. If fails → archive the experiment; we proved the cheap fine-tune path doesn't work AT OUR SCALE for this rubric.
* **Risk**: 1k–1.5k examples is small. A LoRA on Llama 3.1 8B may not learn EU AI Act vocabulary deeply enough to outperform a Groq-served 70B. The Orcawise + Timo Laine fine-tunes (community, no benchmarks, near-zero downloads) suggest this is hard.
* **Source basis**: [Together AI fine-tuning pricing](https://www.together.ai/pricing), [LoRA cost calculator](https://10xstudio.ai/blog/how-much-does-it-cost-to-finetune-llama-with-lora), [Timo Laine EU AI Act fine-tune recipe](https://medium.com/@timo.au.laine/eu-ai-act-fine-tune-multilingual-local-llm-2c0657cc47f8).

### Rank 3 (CONTINGENT — only if Rank 1 + Rank 2 both fail tone): **Cerebras Llama 3.3 70B for latency**

* **What**: Same shape as Rank 1 (provider adapter), but pointed at Cerebras inference instead of Groq.
* **Why**: If we're staying on Llama 3.3 70B for cost but losing latency to Anthropic, Cerebras at 1,800 tok/s makes the latency axis trivial (p50 <1s). 3× faster than Groq, 30× faster than GPU inference.
* **Cost**: ~$3–5/mo at projected volume (2–6× Groq), still 2× cheaper than Anthropic direct.
* **Verification**: Same A/B protocol.
* **Risk**: Pricing higher than Groq; not yet wired into the bundle.
* **Source basis**: [Cerebras pricing & speed](https://artificialanalysis.ai/providers/cerebras), CLAUDE.md R50 (Cerebras queued as R51 work).

### Rank 4 (DO NOT PURSUE): Modal-hosted self-fine-tuned model

* **Why not**: Costs $5–$15/mo to serve via Modal serverless vLLM (cold-start tax), or $2,844/mo for an always-on H100. Either way it's more expensive AND more brittle than Together AI's managed LoRA endpoint, which abstracts the inference infra entirely. Only consider this if Together AI doesn't support the base model we want, or if we hit per-request data residency requirements that force EU-region hosting.

### Rank 5 (DO NOT PURSUE): Switch to SaulLM or other "legal" LLMs

* **Why not**: SaulLM-141B has 94 downloads/month and no managed inference. Self-hosting a 141B model is $5,000+/mo of GPU. It wasn't trained on the EU AI Act specifically. Frontier models (GPT-5, Claude 4 Opus, Gemini 3 Pro) beat it on LegalBench's reasoning tasks — which is the shape of Regenold's questions. The "legal LLM" thesis is a 2024 marketing artefact that didn't survive 2025–2026 frontier-model progress.

---

## 6. Sources

### Pretrained legal LLMs (Q1)
- [SaulLM-141B-Instruct model card](https://huggingface.co/Equall/SaulLM-141B-Instruct) — 94 monthly downloads, no inference provider, MIT licence
- [SaulLM-141B paper announcement (BigDATAwire, Aug 2024)](https://www.hpcwire.com/bigdatawire/this-just-in/equall-introduces-expanded-saul-family-of-legal-llms-with-54b-and-141b-models/)
- [Saul launch blog (Equall, 2024)](https://blog.equall.com/saul) — vendor claim "outperforms GPT-4 on LegalBench average"
- [Saul-Instruct-v1 LegalBench gist (Malikeh97)](https://gist.github.com/Malikeh97/bf1ae452a93693cd0f606be49ad6f329) — 50.5% LegalBench average
- [Awesome Agents Legal AI Leaderboard (Apr 2026)](https://awesomeagents.ai/leaderboards/legal-llm-leaderboard/) — top 10 LegalBench, "domain fine-tunes lose on reasoning"
- [Vals.ai LegalBench](https://www.vals.ai/benchmarks/legal_bench) — Gemini 3.1 Pro Preview 87.40% (top)
- [Orcawise/eu_ai_act_using_finetuned_gemma](https://huggingface.co/Orcawise/eu_ai_act_using_finetuned_gemma) — Gemma-2b LoRA, 1,023 QA pairs, 5 downloads/mo
- [Timo Laine EU AI Act multilingual fine-tune (Medium, 2024)](https://medium.com/@timo.au.laine/eu-ai-act-fine-tune-multilingual-local-llm-2c0657cc47f8) — Gemma-2-2b, 9,175 train examples, 9.8 GPU-hours
- [COMPL-AI Framework (DeepLearning.AI, Oct 2024)](https://www.deeplearning.ai/the-batch/compl-ai-study-measures-llms-compliance-with-eus-ai-act/) — ETH/INSAIT/LatticeFlow benchmark suite
- [TechXplore COMPL-AI coverage](https://techxplore.com/news/2024-10-llm-benchmarking-eu-artificial-intelligence.html)
- [HuggingFace Open Source EU AI Act guide](https://huggingface.co/blog/eu-ai-act-for-oss-developers) — recommends RAG, not specialized models
- [Harvey Legal Agent Benchmark (Harvey, 2026)](https://www.harvey.ai/blog/introducing-biglaw-bench) — closed; not addressable

### Serverless GPU + fine-tune costs (Q2)
- [Modal pricing](https://modal.com/pricing) — H100 $3.95/hr, A100 $2.50/hr, $30/mo free credits, per-second billing, 3× production multiplier
- [Modal H100 detail (Morph)](https://www.morphllm.com/modal-pricing)
- [RunPod pricing](https://www.runpod.io/pricing) — H100 $2.69–$2.99 on-demand, $5.59 serverless
- [Together AI pricing](https://www.together.ai/pricing) — LoRA $0.48/M tokens (≤16B), $1.50/M (17–69B), $2.90/M (70–100B); dedicated H100 $6.49/hr
- [Together AI fine-tuning docs](https://docs.together.ai/docs/fine-tuning-pricing)
- [Jarvislabs H100 price guide 2026](https://jarvislabs.ai/blog/h100-price)
- [Spheron GPU cloud comparison 2026](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/) — H100 from $1.03/hr at 15+ providers
- [10xstudio LoRA cost calculator](https://10xstudio.ai/blog/how-much-does-it-cost-to-finetune-llama-with-lora) — Llama 3.1 8B QLoRA, 4–6 h, ~$12 total
- [Saturn Cloud finetune costs](https://saturncloud.io/blog/finetune-llama-with-affordable-on-demand-h100-and-h200-gpu-instances/) — $8.32 for Llama 3.1 8B on 15k examples
- [Philschmid FSDP QLoRA Llama 3 recipe](https://www.philschmid.de/fsdp-qlora-llama3) — 4× H100 reference run
- [Medium "Under $20" LoRA tutorial](https://medium.com/@velinxs/how-to-fine-tune-llms-for-under-20-step-by-step-c187a3059ca2)
- [Techoc "$47.23" Llama 3 LoRA case study](https://techoc.blog/i-spent-47-23-fine-tuning-llama-3/)
- [HJ Labs LLM fine-tuning best practices 2026](https://hjlabs.in/AIML/blog/post/llm-fine-tuning-best-practices.html) — QLoRA recommendation for small datasets
- [Awesome Agents fine-tuning cost comparison](https://awesomeagents.ai/pricing/fine-tuning-costs-comparison/)

### Inference cost + latency (Q3)
- [Groq pricing](https://groq.com/pricing) — Llama 3.3 70B $0.59/$0.79 per M
- [Groq Llama 3.3 70B 6× speed benchmark](https://groq.com/blog/groq-first-generation-14nm-chip-just-got-a-6x-speed-boost-introducing-llama-3-1-70b-speculative-decoding-on-groqcloud)
- [Artificial Analysis Groq provider page](https://artificialanalysis.ai/providers/groq) — 276 tok/s independent benchmark
- [Cerebras pricing](https://www.cerebras.ai/pricing) + [TokenMix Cerebras review](https://tokenmix.ai/blog/cerebras-api-key-access-speed-tests-2026) — 1,800 tok/s, $0.60–$3.90 per M
- [Artificial Analysis Cerebras provider page](https://artificialanalysis.ai/providers/cerebras)
- [AI Pricing Guru Llama provider comparison](https://www.aipricing.guru/meta-pricing/) — Deepinfra cheapest at $0.23/$0.40 per M
- [Claude API pricing (BenchLM, Apr 2026)](https://benchlm.ai/blog/posts/claude-api-pricing) — Sonnet 4.6 $3/$15 per M, Opus 4.7 $5/$25 per M
- [Anthropic API pricing breakdown (Finout, 2026)](https://www.finout.io/blog/anthropic-api-pricing) — prompt-cache 90% discount
- [Modal vLLM cold-start benchmark](https://markaicode.com/ollama-vs-vllm-performance/) — vLLM 8.7s vs ollama 3.2s cold

### Misc
- [Hugging Face Equall org page](https://huggingface.co/Equall) — full SaulLM family
- [SaulLM-7B Register coverage (2024)](https://www.theregister.com/2024/03/09/better_call_saul_llm/)
- [Phuoc Nguyen Saul deep-dive (Medium)](https://medium.com/@phuocnguyen90/better-call-gpt-saul-might-disagree-with-you-e26345a1b054) — critical comparison Saul vs GPT-4
