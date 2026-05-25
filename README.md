# Regenold EU AI Act RAG

Grounded EU AI Act Q&A — a FastAPI service that answers regulatory questions with verifiable Article / Annex references against EUR-Lex 2024/1689 and the May 2026 Digital Omnibus political agreement.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ POST /api/v1/regenold/eu-ai-act/ask                              │
│      messages (OpenAI/LiteLLM history) → answer + references     │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │ Scope gate          │  app/integrations/regenold/scope.py
                  │ • Prompt-injection  │  • prior-user-turn anchors only
                  │ • Out-of-regulation │  • plural Articles N supported
                  │ • Coref rescue      │  • hard refusals never flipped
                  └──────────┬──────────┘
                             │
                  ┌──────────▼──────────┐
                  │ Multi-turn query    │  app/routes/regenold.py
                  │ de-noiser           │  • Standalone-query LLM rewrite
                  │                     │  • 1.0s fail-fast, falls back to
                  │                     │    history-concat on any error
                  └──────────┬──────────┘
                             │
                  ┌──────────▼──────────┐
                  │ Intent + qtype      │  app/llm/intent_classifier.py
                  │ classifier          │  app/engines/sentence_index.py
                  │ • Davvetas 4-task   │  • 8-way deterministic shape
                  │ • Fail-soft         │    (DEFINITION / BOOLEAN / …)
                  │ • Request-cached    │  • drives templates + budgets
                  └──────────┬──────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Retrieval pipeline (additive)   │
            │ ┌──────────────────────────────┐│  app/data/kb_search.py
            │ │ BM25 over 348-doc corpus     ││  • EUR-Lex full prose
            │ │ + typed-entity priority      ││  • source-weighted scoring
            │ │   boost (role/concept NER)   ││  • 8 roles × 24 concepts
            │ └──────────────────────────────┘│
            │ ┌──────────────────────────────┐│  app/engines/embeddings_index.py
            │ │ NumPy TF-IDF + SVD-128       ││  • 919 sentence index
            │ │ additive recall              ││  • sub-ms warm queries
            │ └──────────────────────────────┘│
            │ ┌──────────────────────────────┐│  app/engines/graph_*.py
            │ │ Neo4j: 2-hop xref expand     ││  • 113 articles + 13 annexes
            │ │ + Personalized PageRank      ││    + 180 recitals + 68 defs
            │ │ + PathRAG (Jaccard prune)    ││    + 351 typed edges
            │ └──────────────────────────────┘│
            │ ┌──────────────────────────────┐│  app/routes/regenold.py
            │ │ Deployer 1-hop expansion     ││  • deterministic 4-edge map
            │ │ (definitional + intent-gated)│  • Art. 26 → 13/14/9 etc.
            │ └──────────────────────────────┘│
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Engine (graph_rag.py)           │
            │ • Stage-1 deterministic parse   │  always lands an answer
            │ • CLARA neuro-symbolic verdict  │  37 boolean tags → tier
            │ • Prohibited Gatekeeper (Art. 5)│  TAI Scan Layer C
            │ • Stage-2 Sonnet 4.6 polish     │  BLUF contrastive prompt
            │   (optional, fail-soft)         │  cross-ref grounding
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Post-engine pipeline            │  app/routes/regenold.py
            │ • Smallest-cover ref dedup      │  drops parents when child cited
            │ • Sub-point emission            │  Art. 5 → Art. 5.1.f
            │ • Per-intent ref budget         │  definitional=2 … scenario=8
            │ • Closed-world refusal gate     │  empty refs ⇒ no-match
            │ • Per-intent answer template    │  length cap by question shape
            │ • Per-ref description augmenter │  every cited article described
            │ • Tone guard + preamble strip   │  imperative regulator voice
            │ • Citation guard (optional)     │  sentence-level token overlap
            │ • Confidence-gated LRU cache    │  no-poison contract (R78.1)
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

The deterministic path always lands an answer; the LLM polish is opportunistic. The route never 500s on a downed LLM, a degraded Neo4j connection, or a missing graph asset — every external dependency is fail-soft with a deterministic substitute.

## Wire contract

```bash
curl -X POST https://<host>/api/v1/regenold/eu-ai-act/ask \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What does Art. 13 require?"}]}'
```

```json
{
  "answer": "Article 13(1) requires high-risk AI providers to design their systems to be sufficiently transparent for deployers to understand the system's output and use it appropriately. Article 13(2) requires accompanying instructions for use that include the provider's identity, the system's intended purpose, its capabilities and limitations, expected lifetime, and necessary maintenance.",
  "references": ["Article 13.1", "Article 13.2"],
  "reasoning": ""
}
```

References are strict: `Article N(.subpoint)*` (Arabic) or `Annex X(.subpoint)*` (Roman). Validated by `_ARTICLE_OUTPUT_RE` / `_ANNEX_OUTPUT_RE` in [`app/integrations/regenold/models.py`](app/integrations/regenold/models.py).

Append `?include_reasoning=true` to surface a structured reasoning trace (scope verdict, anchors used, retrieval path, Stage-2 polish state, engine confidence, cache hit) — useful for audit, debugging, and the LLM-as-judge harness.

## Engine modes

| Mode | Behaviour | Use case |
|---|---|---|
| Deterministic | Pure rule-based, sub-10 ms p50 | Default; always available; never fails |
| Anthropic SDK direct | Stage-1 + Stage-2 polish via the Anthropic API | Pro-tier production deploys |
| Claude Max wrapper | Stage-2 polish via local `claude-code-openai-wrapper` | Development; Max-subscription production |
| Groq Stage-0 / De-noiser | Llama 3.3 70B for intent + multi-turn query rewrite | Cost-optimised always-on |

The active mode is resolved per request — the route falls back to the next-best mode on any provider error.

## Performance posture

| Surface | Coverage |
|---|---|
| EU AI Act articles | 113 / 113 (EUR-Lex full prose) |
| Annexes | 13 / 13 |
| Recitals | 180 |
| Art. 3 definitions | 68 |
| KB obligation stubs | 126 / 126 (no placeholders) |
| Typed cross-reference edges | 351 (Neo4j) |
| Test suite | 2700+ unit tests + 1 skip |
| Davidath benchmark | 476 items (137 QA + 339 scenarios) |
| Out-of-scope regression set | 21 / 21 hard refusals preserved |

The system has been measured against four benchmarks: the davidath EU AI Act benchmark, the AIReg-Bench HRAIS subset, the Stanford CRFM AIR-Bench `eu_mandatory` subset, and an internal V2 probe of tricky / multi-turn / out-of-scope shapes. The deterministic pipeline saturates BM25 recall on the davidath corpus; quality lifts on paraphrased and multi-turn queries come from the LLM-driven Stage-0 (intent + query rewrite) and Stage-2 (polish) paths.

## Quick start

```powershell
# Python 3.12+
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .

# Run (deterministic mode — no LLM required)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8002

# Full test suite
.venv\Scripts\python.exe -m pytest -q

# Reproducible competition benchmark (476 items)
.venv\Scripts\python.exe -m evals.bench.runner --label baseline

# Out-of-scope regression probe (21 hardened refusal shapes)
.venv\Scripts\python.exe -m evals.regenold.runner_v2 --local --probe-oos --label oos

# Local scenario suite (276 categorised scenarios)
.venv\Scripts\python.exe -m evals.regenold.runner
```

## Where to look

| Concern | Module |
|---|---|
| Wire contract + models | [`app/integrations/regenold/models.py`](app/integrations/regenold/models.py) |
| Route + post-engine pipeline | [`app/routes/regenold.py`](app/routes/regenold.py) |
| Scope gate | [`app/integrations/regenold/scope.py`](app/integrations/regenold/scope.py) |
| Engine + Stage-1/2 | [`app/engines/graph_rag.py`](app/engines/graph_rag.py) |
| BM25 + entity-aware retrieval | [`app/data/kb_search.py`](app/data/kb_search.py), [`app/engines/entity_extractor.py`](app/engines/entity_extractor.py) |
| Dense embeddings + reranking | [`app/engines/embeddings_index.py`](app/engines/embeddings_index.py), [`app/engines/turboquant_index.py`](app/engines/turboquant_index.py) |
| Neo4j PPR + PathRAG | [`app/engines/graph_ppr.py`](app/engines/graph_ppr.py), [`app/engines/path_rag.py`](app/engines/path_rag.py) |
| CLARA neuro-symbolic verdict | [`app/engines/clara_logic.py`](app/engines/clara_logic.py) |
| Scenario classifier | [`app/engines/scenario_classifier.py`](app/engines/scenario_classifier.py) |
| Sub-point emitter | [`app/data/subpoint_emitter.py`](app/data/subpoint_emitter.py) |
| Tone guard + preamble strip | [`app/integrations/regenold/tone_guard.py`](app/integrations/regenold/tone_guard.py), [`app/integrations/regenold/answer_normaliser.py`](app/integrations/regenold/answer_normaliser.py) |
| KB (113 articles + 13 annexes) | [`app/data/kb.py`](app/data/kb.py), [`app/data/article_existence.py`](app/data/article_existence.py) |
| Audit chain | [`app/evidence/store.py`](app/evidence/store.py) |
| Evaluation harnesses | [`evals/bench/`](evals/bench/), [`evals/regenold/`](evals/regenold/), [`evals/judge/`](evals/judge/) |
| Partner-facing docs | [`docs/partners/regenold/`](docs/partners/regenold/) |
| Change history | [`CHANGELOG.md`](CHANGELOG.md), [`CLAUDE.md`](CLAUDE.md) |

## License

Apache 2.0.
