# AGENTS.md — Regenold EU AI Act RAG

Repository instructions and operational guidelines for coding agents.

## Project Overview

A standalone EU AI Act grounded Q&A service built for the Regenold competition.
- **Wire Contract**: `POST /api/v1/regenold/eu-ai-act/ask`
- **Payload**: OpenAI-style `messages` array -> `{answer, references, reasoning}`
- **Evaluation Axes**: Correctness, Reference Precision/Recall, Answer Conciseness, Tone, Latency, Multi-turn Coherence.

---

## Commands & Execution Flags

Run commands with full flags and explicit parenthetical purposes:

### 1. Verification & Testing
```bash
# Run single file / fast test during iteration (file-scoped execution)
pytest tests/test_vector_recall.py -v (run vector recall unit tests)

# Run full project unit test suite
pytest tests/ -v (run all unit tests)

# Run deterministic evaluation benchmarks
python -m evals.bench.runner (run davidath 476 benchmark - regression guard)
python -m evals.regenold.runner (run 276 scenario evaluation)
python -m evals.regenold.runner_v2 --local --probe-oos --oos-suite all (run 51 out-of-scope probes)

# THE MERGE GATE: Live pairwise A/B judge
python -m evals.harness.ab_judge (run position-swapped live pairwise A/B evaluation)
python -m evals.harness.easyhard_ab (run ref conciseness & strict recall pairwise evaluation)
```

### 2. Local Environment Setup & Execution
```bash
# Set deterministic environment variables for local testing
$env:OPENAI_API_BASE = "http://127.0.0.1:1/v1"; $env:P2P_GRAPH_RAG_PROVIDER = "cli"; $env:REGENOLD_EXTERNAL_EMBEDDINGS = "0" (set offline deterministic testing flags)

# Run development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload (start local API server)
```

---

## File-Scoped Iteration & Fast Development

1. **Iterate Locally First**: Use file-scoped test execution (`pytest tests/<test_file>.py -v`) during code modifications to preserve token budget and execution speed.
2. **Run Full Verification Only Before Commit**: Execute `pytest tests/ -v` and evaluation harnesses only when code edits are complete.
3. **No Torch / Heavy ML Dependencies**: Do not introduce PyTorch, heavy neural NLI, or external model servers into the runtime path.

---

## Safety, Security & Permissions Boundary

### Allowed Freely
- Editing application modules in `app/`, unit tests in `tests/`, and evaluation scripts in `evals/`.
- Adding new unit tests covering introduced features or bug fixes.
- Running local unit tests, lints, and benchmark evaluation runners.

### Requires Confirmation
- Bumping database or seeder versions (`SEED_VERSION` in `scripts/seed_neo4j_kb.py`).
- Changing default environment variable values in `app/config.py` or `.env.example`.
- Modifying core wire schemas (`RegenoldAskResponse` in `app/routes/regenold.py`).

### Prohibited Actions (Strict Boundaries)
- **NEVER** commit secret keys, API credentials, or Cloudflare Zero Trust service tokens.
- **NEVER** set `NEO4J_AUTO_SEED=1` by default (keep `NEO4J_AUTO_SEED=0` to protect live Aura graph nodes).
- **NEVER** perform direct `git merge` between diverged branches without file-by-file audit.
- **NEVER** alter or suppress failing unit tests or drop test assertions to force a pass.

---

## Core Architecture & Invariants

```
POST /api/v1/regenold/eu-ai-act/ask
        │
        ▼
app/routes/regenold.py
   ├── _build_question_from_history       — flatten recent turns
   ├── classify_conversation              — scope gate (refusal or in-scope)
   ├── ask_compliance_question            — engine entry (`app/engines/_graph_rag_impl.py`)
   │     ├── _deterministic_parse         — keyword -> entities + BM25 + vector recall (R326)
   │     ├── _retrieve_from_kb            — KB + ontology + xrefs + graph semantic layers (R327)
   │     ├── _deterministic_answer        — verdict / role x risk / obligations
   │     └── _two_stage_generate          — Stage-2 LLM polish (live only)
   ├── _surface_anchor_citations          — keyword-derived anchors
   ├── _collapse_parent_when_subpoint_cited — parent collapse (R325)
   └── normalise_answer_for_regenold      — sentence & char caps
```

1. **Strict Reference Format**: Emitted citations MUST strictly follow `Article N(.subpoint)*` or `Annex X(.subpoint)*` (uppercase Roman for Annexes, Arabic for Articles). Never emit `Art. 13` or `Annex 3` on the wire.
2. **Lint Floor**: Every emitted reference must resolve in `app/data/article_existence.py` (**126 canonical references**).
3. **Graph is Additive Only**: `app/engines/kg_context.py` provides non-citable Stage-2 context. It is never a ranker or wire citation.
4. **Cache Key Identity**: All runtime flags (`REGENOLD_GRAPH_SEMANTIC_LAYERS`, `REGENOLD_SEMANTIC_GLOSS`, `REGENOLD_GRAPH_VECTOR_RECALL`, `REGENOLD_PARENT_COLLAPSE`) must be registered in `_engine_cache_key` in `app/routes/regenold.py`.

---

## Closed Directions (Do Not Re-propose)

Empirically measured failures in `docs/ROUNDS.md` — do not re-implement:
- **Global top-K clamps or positional reference trimming**: Drops gold references and loses pairwise A/B evals.
- **Neural NLI citation verification**: 235x slower and lower accuracy (ROC-AUC 0.585) than lexical scoring.
- **Graph-primary retrieval**: Buries operative articles under generic risk-tier dumps.
- **Fast mode / thinking token budget tweaks for latency**: Latency is dominated by wrapper CLI floor, not model token flags.
- **CLARA logical engine re-wiring** (`app/engines/clara_logic.py`): superseded by `prohibited_gatekeeper` — recorded wrong verdict (risk_tier=minimal) on the prohibited emotion-monitoring scenario; zero import sites; re-wiring regresses a currently-passing scenario (2026-08-17 architecture review).
