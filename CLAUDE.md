@AGENTS.md

# CLAUDE.md — Claude Code Context & Runtime Guidelines

This file extends `@AGENTS.md` with Claude-specific operational details, wrapper quirks, and runtime configuration.

## LLM Provider Architecture & Claude Wrapper

`P2P_GRAPH_RAG_PROVIDER` selects one of three mutually exclusive paths:

| Value | Behaviour | Configuration / Setup |
| :--- | :--- | :--- |
| `cli` / `auto`* | Pure deterministic, no LLM, sub-10 ms. **This is what davidath runs.** | Default offline path |
| `anthropic` | Stage-1 + Stage-2 via Anthropic SDK (per-token billing) | `P2P_GRAPH_RAG_API_KEY=sk-ant-...` |
| `openai_wrapper` | Stage-1 + Stage-2 + Stage-0 intent via the local Claude Code Max wrapper | Wrapper on `127.0.0.1:8000` + `OPENAI_API_BASE` |
| `bedrock` | AWS Bedrock Converse API (EU cross-region inference) | `BEDROCK_REGION=eu-central-1` + AWS keys |

`* auto` -> `anthropic` when an API key is set, otherwise falls back to `cli`. Every sub-pipeline falls back to a deterministic equivalent on error, so the route never 500s on a downed LLM.

### Local Claude Code OpenAI Wrapper Setup
The local proxy lives at `D:\Claude Projects\claude-code-openai-wrapper` and leverages the flat Claude Max subscription.

To run evaluations against the wrapper:
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "dummy"
$env:P2P_GRAPH_RAG_PROVIDER = "openai_wrapper"
```

### Cloudflare Access Service Token
When Cloudflare Zero Trust Access fronts `wrapper.antifragile-ai.net`, attach:
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

Verify live wrapper connectivity via `curl http://127.0.0.1:8000/healthz/llm`.

---

## Critical Claude-Specific Gotchas

1. **Stage-2 SYSTEM Prompt is Dropped by Wrapper**: The Claude Max wrapper drops the system prompt slot (0% of requests see it). **All Stage-2 prompt modifications MUST go into the user message**.
2. **`railway.toml [deploy.envs]` is Inert**: Railway's schema does not apply `[deploy.envs]`. All runtime defaults MUST be defined as code defaults in Python (`app/config.py` and `app/engines/graph_rag.py`).
3. **Graph Auto-Seeding Version Control**: Code fixes in `provision_text` require bumping `SEED_VERSION` in `scripts/seed_neo4j_kb.py`, otherwise boot auto-seeding skips execution and serves legacy graph data.
4. **Environment Loading Context**: `load_dotenv()` resolves relative to the calling script directory. Always assert `get_graph_client().enabled` before drawing graph benchmark conclusions.
5. **No Parallel Wrapper Jobs**: Never run multiple wrapper-bound evaluation runs concurrently over the single local proxy instance.

---

## Baseline Performance Reference (Commit `b47c259`)

Deterministic environment: `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0`

| Metric Axis | Ans Loose | Ans Strict | Ans Conc | Ref Loose | Ref Strict | Ref Conc | Tone |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OVERALL (476)** | 0.1884 | **0.3545** | 0.6143 | **0.5971** | **0.4748** | 0.4316 | 1.0 |
| **QA (137)** | 0.1407 | 0.4072 | 0.1961 | 0.8394 | 0.5536 | 0.4390 | 1.0 |
| **Scenarios (339)** | 0.2076 | 0.3332 | 0.7833 | 0.4992 | 0.4430 | 0.4287 | 1.0 |

Multi-turn coherence: **20/20 coherent**.

---

## Environment Flags Reference

| Environment Variable | Code Default | Purpose |
| :--- | :--- | :--- |
| `P2P_GRAPH_RAG_PROVIDER` | `auto` | Selected LLM backend (`cli`, `anthropic`, `openai_wrapper`, `bedrock`) |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `1` | Stage-2 LLM polish master gate |
| `REGENOLD_GRAPH_SEMANTIC_LAYERS` | `1` | Constrained sub-provision vector search across Neo4j indexes (R327) |
| `REGENOLD_SEMANTIC_GLOSS` | `0` | Open-domain definitions/recitals gloss gate (R327) |
| `REGENOLD_GRAPH_VECTOR_RECALL` | `0` | Additive Neo4j & local SVD vector recall path (R326) |
| `REGENOLD_PARENT_COLLAPSE` | `0` | Collapse parent provisions when sub-points are cited (R325) |
| `BEDROCK_REGION` | `eu-central-1` | AWS Bedrock cross-region inference profile geography (R328) |
| `NEO4J_AUTO_SEED` | `0` (or `off`) | Boot graph seeder safety switch (Keep 0 in production) |
