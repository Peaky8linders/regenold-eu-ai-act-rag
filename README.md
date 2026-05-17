# Regenold EU AI Act RAG

Grounded EU AI Act Q&A — a FastAPI service that answers regulatory questions with verifiable Article / Annex references against EUR-Lex 2024/1689 and the May 2026 Digital Omnibus political agreement.

## Architecture (end-to-end)

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
                  │ Intent + qtype      │  app/llm/intent_classifier.py
                  │ classifier          │  app/engines/sentence_index.py
                  │ • Haiku 4.5         │  • 8-way deterministic shape
                  │ • Davvetas 4-task   │    (DEFINITION / BOOLEAN / …)
                  │ • Fail-soft         │  • drives templates + budgets
                  └──────────┬──────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Retrieval pipeline (additive)   │
            │ ┌──────────────────────────────┐│  app/data/kb_search.py
            │ │ BM25 over 348-doc corpus     ││  • EUR-Lex full prose
            │ │  (KB + ontology + definitions)│   • source-weighted scoring
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
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Engine (graph_rag.py)           │
            │ • Stage-1 deterministic parse   │  always lands an answer
            │ • CLARA neuro-symbolic verdict  │  37 boolean tags → tier
            │ • Prohibited Gatekeeper (Art. 5)│  TAI Scan Layer C
            │ • Stage-2 Sonnet 4.6 polish     │  via openai_wrapper or
            │   (optional, fail-soft)         │  Anthropic SDK direct
            └────────────────┬────────────────┘
                             │
            ┌────────────────▼────────────────┐
            │ Post-engine pipeline            │  app/routes/regenold.py
            │ • Smallest-cover ref dedup      │  drops parents when child cited
            │ • Sub-point emission (R38)      │  Art. 5 → Art. 5.1.f
            │ • Per-intent ref-budget         │  definitional=2 … scenario=8
            │ • Closed-world refusal gate     │  empty refs ⇒ no-match
            │ • Per-intent answer template    │  length cap by question shape
            │ • Tone guard                    │  strip hedges, force imperative
            │ • Citation guard (optional)     │  sentence-level token overlap
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

**LLM provider:** picked via `P2P_GRAPH_RAG_PROVIDER` env (resolved on every call).

| Value | Behaviour | Setup |
|---|---|---|
| `cli` (default) | Pure deterministic. Sub-10 ms p50. | nothing |
| `anthropic` | Stage-2 polish via Anthropic SDK direct. | `P2P_GRAPH_RAG_API_KEY=sk-ant-…` |
| `openai_wrapper` | Stage-2 polish via local `claude-code-openai-wrapper` (Claude Max). | wrapper on `127.0.0.1:8000`; see [`SONNET_WRAPPER.md`](docs/partners/regenold/SONNET_WRAPPER.md) |

The deterministic path always lands an answer — the LLM polish is opportunistic. The route never 500s on a downed LLM.

## Wire contract

```bash
curl -X POST http://127.0.0.1:8002/api/v1/regenold/eu-ai-act/ask \
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

Telemetry block (confidence, retrieval path, KB version, graph stats) appears when `?include_telemetry=true`.

## Quick start

```powershell
# Python 3.12+
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .

# Run (deterministic mode — no LLM required)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8002

# Run the full pytest suite (~1300 tests)
.venv\Scripts\python.exe -m pytest -q

# Run the canonical competition benchmark (476 items)
.venv\Scripts\python.exe -m evals.bench.runner --label baseline

# Run the unbiased eval (holdout + AIReg-Bench + Regenold probe)
.venv\Scripts\python.exe -m evals.bench.unbiased_runner --label baseline
```

## Where to look

| Concern | Module |
|---|---|
| Wire contract + models | [`app/integrations/regenold/models.py`](app/integrations/regenold/models.py) |
| Route + post-engine pipeline | [`app/routes/regenold.py`](app/routes/regenold.py) |
| Scope gate | [`app/integrations/regenold/scope.py`](app/integrations/regenold/scope.py) |
| Engine + Stage-1/2 | [`app/engines/graph_rag.py`](app/engines/graph_rag.py) |
| BM25 + embeddings retrieval | [`app/data/kb_search.py`](app/data/kb_search.py), [`app/engines/embeddings_index.py`](app/engines/embeddings_index.py) |
| Neo4j PPR + PathRAG | [`app/engines/graph_ppr.py`](app/engines/graph_ppr.py), [`app/engines/path_rag.py`](app/engines/path_rag.py) |
| Sub-point emitter | [`app/data/subpoint_emitter.py`](app/data/subpoint_emitter.py) |
| Answer template + tone guard | [`app/engines/answer_template.py`](app/engines/answer_template.py), [`app/integrations/regenold/tone_guard.py`](app/integrations/regenold/tone_guard.py) |
| KB (113 articles + 13 annexes) | [`app/data/kb.py`](app/data/kb.py), [`app/data/article_existence.py`](app/data/article_existence.py) |
| Audit chain | [`app/evidence/store.py`](app/evidence/store.py) |
| Evals | [`evals/bench/`](evals/bench/), [`evals/regenold/`](evals/regenold/) |
| Partner docs | [`docs/partners/regenold/`](docs/partners/regenold/) |
| Detailed change history | [`CLAUDE.md`](CLAUDE.md), [`CHANGELOG.md`](CHANGELOG.md) |

## Feature flags

All default-ON in `railway.toml`. Flip OFF to A/B against earlier rounds.

| Flag | Effect |
|---|---|
| `REGENOLD_SUBPOINT_EMIT` | Upgrade base refs to leaf sub-points |
| `REGENOLD_ANSWER_TEMPLATE` | Per-intent length cap |
| `REGENOLD_REFBUDGET_PER_INTENT` | 10-way ref-count budget |
| `REGENOLD_TONE_GUARD` | Strip hedge openers |
| `REGENOLD_GRAPH_2HOP` | Neo4j 2-hop cross-ref expansion |
| `REGENOLD_GRAPH_PPR` | Neo4j Personalized PageRank (needs GDS plugin) |
| `REGENOLD_PATH_RAG` | Relational-path retrieval with Jaccard prune |
| `REGENOLD_CLARA_VERDICT` | Neuro-symbolic verdict (37-tag matrix) |
| `REGENOLD_EMBEDDINGS_INDEX` | NumPy TF-IDF + SVD-128 sentence index |

## License

Apache 2.0.
