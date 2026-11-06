# Regenold EU AI Act RAG

Grounded EU AI Act Q&A — a FastAPI service that answers regulatory questions with verifiable Article / Annex references against EUR-Lex 2024/1689 and the May 2026 Digital Omnibus political agreement.

It mounts both the partner integration endpoint (`/api/v1/regenold/eu-ai-act/ask`) and a human-facing interactive compliance chat assistant UI called **Lexy** at the root path (`/`).

---

## Architecture

The service implements a hybrid, additive neuro-symbolic retrieval and generation pipeline. Retrieval is **KB-primary** (deterministic BM25 over the full EUR-Lex corpus) with the vector and graph layers stacked **additively on top** — they can raise a close candidate's rank but never displace a lexical winner. The whole system is **fail-soft**: if the graph database, the vector assets, or any LLM provider is unreachable or errors out, the pipeline falls back to an ultra-fast deterministic rule-based path so an answer always lands.

```
┌──────────────────────────────────────────────────────────────────┐
│ POST /api/v1/regenold/eu-ai-act/ask       (partner key required) │
│      messages (OpenAI/LiteLLM history) → answer + references     │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │ Lexy scope gate     │  scope.py + lexy_gate.py
                  │ • Prompt-injection  │  • safety-intent gate
                  │ • Topic filter      │    (dangerous / adversarial)
                  │   (branded replies) │  • LLM ambiguous-OOS gate
                  │ • Coref rescue      │    Groq→Gemini→Mistral→wrapper
                  └──────────┬──────────┘
                             │
                  ┌──────────▼──────────┐
                  │ Multi-turn query    │  app/routes/regenold.py
                  │ de-noiser           │  • standalone-query LLM rewrite
                  │                     │  • Groq → wrapper → deterministic
                  │                     │    salvage on any failure
                  └──────────┬──────────┘
                             │
                  ┌──────────▼──────────┐
                  │ Intent + qtype      │  app/llm/intent_classifier.py
                  │ classifiers         │  app/engines/sentence_index.py
                  │ • 57-way intent     │  • 8-way deterministic shape
                  │ • Groq Stage-0      │    (DEFINITION / BOOLEAN / …)
                  │ • Request-cached    │  • drives templates + budgets
                  └──────────┬──────────┘
                             │
       ┌─────────────────────▼─────────────────────┐
       │ Retrieval — KB-PRIMARY, layers ADDITIVE    │
       │ ┌────────────────────────────────────────┐│  app/data/kb_search.py
       │ │ BM25 over ~347-doc EUR-Lex corpus      ││  • full-prose + KB stubs
       │ │ + typed-entity NER priority boost      ││  • source-weighted score
       │ │   (8 roles × 24 concepts)              ││  • entity_extractor.py
       │ └────────────────────────────────────────┘│
       │ ┌────────────────────────────────────────┐│  embeddings_index.py
       │ │ NumPy TF-IDF + SVD-128 dense recall    ││  • 919-sentence index
       │ │ (additive fill)                        ││  • sub-ms warm queries
       │ └────────────────────────────────────────┘│
       │ ┌────────────────────────────────────────┐│  graph_*.py
       │ │ Neo4j 2-hop xref + PPR + PathRAG       ││  • 505 seeded nodes:
       │ │ (additive-only — never the primary     ││    113 arts + 13 annexes
       │ │  risk-tier dump; empty→KB fallback)    ││    + 180 recitals + 68 defs
       │ └────────────────────────────────────────┘│
       │ ┌────────────────────────────────────────┐│  routes + sufficient_context
       │ │ Deployer 1-hop • multi-article entity  ││  • FRAMES bounded 1-hop
       │ │ • Sufficient-Context bounded multi-hop ││    (≤3 deterministic
       │ │   (glass-box sub-query provenance)     ││    sub-queries, no LLM)
       │ └────────────────────────────────────────┘│
       └─────────────────────┬─────────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Engine (graph_rag.py)           │  always lands an answer
            │ • Stage-1 deterministic parse   │
            │ • CLARA neuro-symbolic verdict  │  37 boolean tags → tier
            │ • Prohibited Gatekeeper (Art.5) │  TAI Scan Layer C
            │ • Curated authoritative         │  definitions / penalties /
            │   intercepts → skip Stage-2     │  role-diff / Annex III(8)…
            │ • Semantic-contract validator   │  advisory grounding hints
            │ • Stage-2 answer: Opus 4.8      │  verdict-first; complex =
            │   (± MoA fusion, fail-soft)     │  extended thinking (4000t)
            │ • Stage-2 fidelity guard        │  cross-tier completeness
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Post-engine pipeline            │  app/routes/regenold.py
            │ • Verbatim / synthesis router   │  synthesis default; verbatim
            │                                 │    for explicit-quote asks
            │ • HRAIS chain-collapse          │  drops over-cited detail arts
            │ • Reference reconciliation      │  drop cited-but-undescribed
            │ • Smallest-cover dedup + sub-   │  Art. 5 → Art. 5.1.f
            │   point emission                │
            │ • Per-intent ref budget +       │  every cited article described
            │   per-ref description augmenter │  + curated-ref protection
            │ • Tone guard + dash / preamble  │  imperative regulator voice
            │   / meta-commentary strip       │  no dashes / ellipses
            │ • Confidence-gated LRU cache    │  no-poison contract (R78.1)
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Reasoning trace (glass-box)     │  reasoning_trace.py
            │ scope • anchors • sub-queries • │  serialised into `reasoning`
            │ references • LLM thinking       │  when ?include_reasoning=true
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Hash-chained audit store        │  app/evidence/store.py
            │ (in-memory / SQLite / Postgres) │  every Q&A round-trip persisted
            └────────────────┬────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │ RegenoldAskResponse │
                  │ { answer,           │
                  │   references,       │
                  │   reasoning }       │
                  └─────────────────────┘
```

### Core Pipeline Stages

1. **Lexy Scope Gate (`app/integrations/regenold/scope.py`, `lexy_gate.py`)**: Blocks prompt injections and genuinely dangerous / adversarial prompts (safety-intent gate), filters out-of-regulation questions with branded Lexy replies (topic filter, default ON), and rescues coreferent multi-turn follow-ups from prior-turn anchors. An LLM ambiguous-OOS gate (Groq → Gemini → Mistral → Claude Max wrapper, fail-soft) rescues genuine keyword-less AI-Act questions the deterministic classifier cannot resolve.
2. **Query De-Noiser (`app/routes/regenold.py`)**: Rewrites multi-turn conversation logs into a dense standalone search query, keeping term-frequency metrics sharp. Runs through a provider chain (Groq → wrapper) with deterministic self-contained-turn salvage on any failure.
3. **Intent + qtype Classifiers (`app/llm/intent_classifier.py`, `app/engines/sentence_index.py`)**: A 57-way intent taxonomy (Groq Stage-0, request-cached, fail-soft) plus an 8-way deterministic question shape (DEFINITION / BOOLEAN / SCENARIO / …) drive length budgets and response templates. Anchors below the confidence floor only re-rank; they never delete a deterministic winner.
4. **Additive Retrieval (`app/data/kb_search.py`)**: A **KB-primary** BM25 pass over the ~347-doc EUR-Lex corpus with typed-entity NER boosts (8 roles × 24 concepts), layered additively with SVD-128 dense TF-IDF recall, Neo4j 2-hop / PPR / PathRAG cross-reference expansion (additive-only, with empty-graph → KB fallback), a deterministic deployer 1-hop map, multi-article entity extraction, and a bounded FRAMES-style Sufficient-Context multi-hop that logs every sub-query.
5. **Neuro-Symbolic Engine (`app/engines/graph_rag.py`)**: A deterministic Stage-1 parser, the CLARA logical engine (37 boolean compliance tags → risk tier), and the Art. 5 Prohibited Gatekeeper always land an answer. Curated authoritative intercepts short-circuit Stage-2 for high-precision topics (definitions, penalties, role differences, Annex III(8), minimal-risk, …). A Stage-2 LLM pass (**Claude Opus 4.8**, verdict-first; complex questions get a 4000-token extended-thinking budget; optional Mixture-of-Agents fusion) polishes the answer under an advisory semantic-contract validator and a cross-tier fidelity guard — all fail-soft to the deterministic verdict.
6. **Post-Engine Refinement (`app/routes/regenold.py`)**: A verbatim/synthesis answer router, HRAIS chain-collapse for over-citation, reference reconciliation (drop cited-but-undescribed refs), smallest-cover deduplication, sub-point emission, per-intent reference budgets, a per-ref description augmenter, curated-ref protection, tone / dash / preamble / meta-commentary strippers, and a confidence-gated no-poison LRU cache.
7. **Glass-box Reasoning (`reasoning_trace.py`)**: When `?include_reasoning=true` is set, every decision site — scope verdict, retrieval anchors, Sufficient-Context sub-queries, final references, and any LLM thinking — is serialised into the `reasoning` field and the hash-chained audit store.

---

## Wire Contract

### Request
```bash
curl -X POST http://localhost:8002/api/v1/regenold/eu-ai-act/ask \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What does Art. 13 require?"}]}'
```

### Response
```json
{
  "answer": "Article 13(1) requires high-risk AI providers to design their systems to be sufficiently transparent for deployers to understand the system's output and use it appropriately. Article 13(2) requires accompanying instructions for use that include the provider's identity, the system's intended purpose, its capabilities and limitations, expected lifetime, and necessary maintenance.",
  "references": ["Article 13.1", "Article 13.2"],
  "reasoning": ""
}
```

*Note: Append `?include_reasoning=true` to the URL to receive the full glass-box diagnostic trace (scope verdict, retrieval anchors, Sufficient-Context sub-queries, final references, and LLM thinking) in the `reasoning` block.*

---

## Local Setup and Running the UI

Follow these steps to set up the codebase and run the Lexy compliance interface locally.

### Step 1: Environment and Virtualenv
The service requires Python 3.12+. Set up a virtual environment:
```bash
# Windows
py -3.12 -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3.12 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies
Install the package and all engine requirements in editable mode:
```bash
pip install -e .
```

### Step 3: Configure Environment Variables
Copy the template and adjust env variables as needed. The pipeline uses environment keys like `P2P_GRAPH_RAG_PROVIDER` to resolve LLM calls, falling back gracefully to the offline deterministic path if none are configured.
```bash
cp .env.example .env
```

### Step 4: Run the UI and API locally
Launch the development server with `uvicorn`:
```bash
python -m uvicorn app.main:app --reload --port 8002
```

Once running:
- **Interactive Web UI (Lexy)**: Open `http://localhost:8002/` in your browser. This serves the premium chat-assistant dashboard which persists your custom configuration client-side in `localStorage`.
- **API Endpoint**: Accessible at `http://localhost:8002/api/v1/regenold/eu-ai-act/ask`.
- **Interactive API Documentation**: Reachable at `http://localhost:8002/docs`.
- **Health Probes**: `/healthz` for basic uptime, `/healthz/llm` for downstream model checks, and `/healthz/graph` for database stats.

---

## Evaluation and Benchmarks

The system is continuously scored against benchmarks using both token-overlap metrics and a 4-axis LLM-as-a-judge (correctness, references-faithfulness, conciseness, tone). All scorecards below are **live production runs** against the deployed Railway endpoint.

### 1. GraphRAG-Paper Benchmark (`main-live`, 2026-06-29)

Appendix-B.2 questions grounded in the GraphRAG-Bench paper (n=40 ground-truth rows, 38 with scorable Article/Annex gold), run live against production:

| Axis | main-live | Notes |
| --- | ---: | --- |
| **Ref. Correctness (Loose)** | **0.853** | token-overlap vs gold refs |
| **Ref. Correctness (Strict)** | **0.701** | F1, precision-penalised |
| **Ref. Conciseness** | **0.510** | citation length-ratio |
| **Keyword Recall** | **0.576** | gold-keyword surfacing |
| **Regulatory Tone** | **1.000** | *perfect* |
| **Refusal Rate** | **0.000** | *no false refusals* |
| **Latency p50 / p95** | **16.4 s / 28.7 s** | live Opus Stage-2 |

### 2. MedTech GraphRAG Gold Set (`r260`, 2026-06-30, LLM-judged)

A 24-row medical / healthcare / life-sciences set (themes from GraphRAG-Bench medical, MedMCQA / MIRAGE; references grounded in verbatim EU AI Act text). Scored both on token-overlap **and** by the 4-axis LLM-as-a-judge (via the Claude Max wrapper):

| Axis | Token-overlap | LLM Judge (pass rate) |
| --- | ---: | ---: |
| **Correctness** | ref-driven (below) | **0.917** (22/24, mean factual 0.866) |
| **References faithfulness** | Ref Loose **0.823** / Strict **0.699** | **0.833** (20/24) |
| **Conciseness** | Ref Conc. **0.586** | **0.833** (20/24) |
| **Regulatory Tone** | **1.000** | **1.000** (24/24) |
| **Keyword Recall** | **0.615** | — |
| **Refusal Rate** | **0.000** | — |
| **Latency p50 / p95** | **21.1 s / 33.9 s** | — |

The judged **references-faithfulness axis** (historically the project floor, ~0.20–0.43) now sits at **0.833** — when the engine cites the right Article, the Opus Stage-2 pass describes the right substance.

### 3. Representative 100 Benchmark (`olh-live`, 2026-06-23)

A 100-row stratified live sample drawn from the 476-row competition benchmark, scored on token-overlap (a proxy that structurally under-scores verbatim provisions and detailed obligation stubs):

- **Ref. Correctness (Loose, token overlap)**: **0.599**
- **Ref. Correctness (Strict, token overlap)**: **0.454**
- **Ref. Conciseness (token overlap)**: **0.322**
- **Ans. Correctness (Strict, token overlap)**: **0.318**
- **Ans. Correctness (Loose, token overlap)**: **0.114**
- **Ans. Conciseness (token overlap)**: **0.257**
- **Answer Keyword Recall**: **0.319**
- **Regulatory Tone (heuristic)**: **0.910**
- **Latency p50 / p95 / mean**: **8.4 s / 49.5 s / 18.0 s**

*The LLM-as-a-judge factual-consistency scorecard is reported on the GraphRAG / MedTech sets above (token-overlap on the representative sample under-measures the verbatim-first answer style).*

### Running Evals Locally

You can execute the automated evaluation and check progress locally using the following scripts:

```bash
# Run the reproducible 476-item competition benchmark
python -m evals.bench.runner --label baseline

# Run the out-of-scope regression check (21 hard refusal probes)
python -m evals.regenold.runner_v2 --local --probe-oos --label oos

# Run the local scenario suite (276 categorized medtech & general scenarios)
python -m evals.regenold.runner

# Run the MedTech GraphRAG gold set live + the 4-axis LLM-as-a-judge
python -m evals.regenold.run_medtech_graphrag_v124 --endpoint <live-url> --label latest
python -m evals.judge.runner --bench-sidecar evals/bench/results/medtech-graphrag-v124-latest.json --label latest --provider wrapper
```

---

## Where to Look

| Feature | Module |
|---|---|
| API Contract & Models | [`app/integrations/regenold/models.py`](app/integrations/regenold/models.py) |
| Route Handling | [`app/routes/regenold.py`](app/routes/regenold.py) |
| Scope, Refusal & Lexy Gate | [`app/integrations/regenold/scope.py`](app/integrations/regenold/scope.py), [`app/integrations/regenold/lexy_gate.py`](app/integrations/regenold/lexy_gate.py) |
| Web UI Interface | [`app/web_ui.py`](app/web_ui.py) |
| GraphRAG Engine | [`app/engines/graph_rag.py`](app/engines/graph_rag.py) |
| CLARA Verdict & Prohibited Gatekeeper | [`app/engines/clara_logic.py`](app/engines/clara_logic.py), [`app/engines/prohibited_gatekeeper.py`](app/engines/prohibited_gatekeeper.py) |
| Additive KB Search & Entity NER | [`app/data/kb_search.py`](app/data/kb_search.py), [`app/engines/entity_extractor.py`](app/engines/entity_extractor.py) |
| Neo4j 2-hop / PPR / PathRAG | [`app/engines/graph_expand_2hop.py`](app/engines/graph_expand_2hop.py), [`app/engines/graph_ppr.py`](app/engines/graph_ppr.py), [`app/engines/path_rag.py`](app/engines/path_rag.py) |
| Sufficient-Context Multi-hop | [`app/engines/sufficient_context.py`](app/engines/sufficient_context.py) |
| Semantic Contract & Fidelity Guard | [`app/engines/semantic_validator.py`](app/engines/semantic_validator.py), [`app/engines/stage2_fidelity.py`](app/engines/stage2_fidelity.py) |
| Verbatim / Synthesis Router & MoA Fusion | [`app/engines/answer_router.py`](app/engines/answer_router.py), [`app/engines/fusion.py`](app/engines/fusion.py) |
| Grounded Prose & Reasoning Trace | [`app/integrations/regenold/grounded_prose.py`](app/integrations/regenold/grounded_prose.py), [`app/integrations/regenold/reasoning_trace.py`](app/integrations/regenold/reasoning_trace.py) |
| Tone & Style Normalizers | [`app/integrations/regenold/tone_guard.py`](app/integrations/regenold/tone_guard.py), [`app/integrations/regenold/answer_normaliser.py`](app/integrations/regenold/answer_normaliser.py) |
| Knowledge Base Data | [`app/data/kb.py`](app/data/kb.py) |
| Evaluation Harnesses | [`evals/bench/`](evals/bench/), [`evals/judge/`](evals/judge/), [`evals/regenold/`](evals/regenold/) |

---

## License

Apache 2.0.
