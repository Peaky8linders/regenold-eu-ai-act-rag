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

# Out-of-scope probes (optional, lightweight)
python -m evals.regenold.runner_v2 --local --probe-oos --oos-suite all (run 51 out-of-scope probes)

# THE MERGE GATE: Live pairwise A/B judge (the ONLY evaluation instrument)
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
   ├── _try_extractive_answer             — R93 extractive QA; R381 shape guard
   │     └── _extractive_shape_ok / _enumerated_categories (default ON)
   ├── _surface_anchor_citations          — keyword-derived anchors
   ├── _collapse_parent_when_subpoint_cited — parent collapse (R325), default ON (R381)
   ├── _apply_wire_ref_cap                — terminal reference cap (R381), default OFF
   └── normalise_answer_for_regenold      — sentence & char caps
```

⚠ **CORRECTED R366 — this diagram was ASPIRATIONAL for the parent-collapse
row until R366.** `a659849` (the R320-R328 port) brought
`_parent_collapse_enabled` / `_collapse_parent_when_subpoint_cited` across
with their unit tests, their `.env.example` row, the `_engine_cache_key`
entry and this line — but **not** the upstream call site.
`git log -S "_collapse_parent_when_subpoint_cited" -- app/routes/regenold.py`
returns exactly that one commit and it adds only the two `def` lines, so
`REGENOLD_PARENT_COLLAPSE` was a **dead flag** for the whole life of the
branch while this diagram and the CLAUDE.md flag table both described it as
live. R366 wired it as the LAST reference pass (after the R365 recall wire
guard, before the R50/R131 trace finalisation). R381 gated it live (0 gold dropped,
+5.0 pp RefConc) and flipped it to **default ON**. Offline it remains a strict
**no-op**, so deterministic instruments read +0.0000 with it ON. See
`tests/test_r366_parent_collapse_wired.py` and `tests/test_r325_parent_collapse.py`.

**The general lesson, third time paid for** (R329's three rerank placements
made zero calls; R330's entire R327 semantic layer never executed): a step
drawn in this diagram is a CLAIM, not evidence. Before relying on any row,
grep for the call site.

1. **Strict Reference Format**: Emitted citations MUST strictly follow `Article N(.subpoint)*` or `Annex X(.subpoint)*` (uppercase Roman for Annexes, Arabic for Articles). Never emit `Art. 13` or `Annex 3` on the wire.
2. **Lint Floor**: Every emitted reference must resolve in `app/data/article_existence.py` (**126 canonical references**).
3. **Graph is Additive Only**: `app/engines/kg_context.py` provides non-citable Stage-2 context. It is never a ranker or wire citation.
4. **Cache Key Identity**: **EVERY** runtime flag that can change the response must be registered in `_engine_cache_key` (`app/routes/regenold.py:1207`). This is enforced by an AST gate, `tests/test_r355_cache_key_complete.py` - run it after adding any flag. The four flags this line used to enumerate (`REGENOLD_GRAPH_SEMANTIC_LAYERS`, `REGENOLD_SEMANTIC_GLOSS`, `REGENOLD_GRAPH_VECTOR_RECALL`, `REGENOLD_PARENT_COLLAPSE`) are a stale R325-R327 subset; the register now carries 21+, including the rerank and `REGENOLD_STAGE2_*` families. **Corrected R365** - do not read that list as exhaustive.
   ⚠ The AST gate scans `app/engines` and `app/integrations/regenold` only (`tests/test_r355_cache_key_complete.py:32`), so flags living in **`app/llm/`** - every `REGENOLD_STAGE2_*` and `REGENOLD_BEDROCK_WRAPPER_FALLBACK` - are invisible to it and must be checked by hand.

5. **The Stage-2 prompt is NOT a sink** (R365). The wire `references` list is recomputed from the final Stage-2 prose by three default-ON, `stage2_landed`-gated passes - `_reconcile_references_to_prose` (drops), `_add_prose_named_refs` (adds), `_surface_prose_subpoints` (adds sub-points). So invariant #3 ("graph is additive only") means the graph cannot be a citation **SOURCE**; it does **not** mean a prompt-side change is reference-neutral. Any lever that changes the Stage-2 prompt must be gated on `gold_dropped_head`. A `provider=cli` test cannot show otherwise - it pins the property in the one regime where all three passes are documented no-ops.

---

## Closed Directions (Do Not Re-propose)

Empirically measured failures in `docs/ROUNDS.md` — do not re-implement:
- **Global top-K clamps or positional reference trimming**: Drops gold references and loses pairwise A/B evals. **Re-confirmed R381 with a properly powered gate** — a terminal wire cap was built with a grounded ranker (so it would not be a naive positional clamp), then rejected: zero-variance simulation over a full live capture of the gold-bearing probe corpus (n=129) gives cap 3 → `gold_dropped_head` 37→41 FAIL, cap 2 → 65 FAIL, cap 1 → 113 FAIL, while the values that pass (4, 5) are worth ≤ +0.33 pp Overall. ⚠ The verdict REVERSED with n (cap=3 read "pass" at n=17/30/34); a zero-variance simulation removes GENERATION variance, not SAMPLING variance. And the grounded ranker itself measured WORSE than plain emission order — `_reference_described_in_prose` is number-anchored, so a gold provision the answer PARAPHRASES scores bottom tier and gets cut. `REGENOLD_WIRE_REF_CAP` stays at `0`. **Parent collapse is the part of this that IS free** (it removes a duplicate, not a provision) and ships default ON.
- **Neural NLI citation verification**: 235x slower and lower accuracy (ROC-AUC 0.585) than lexical scoring.
- **Graph-primary retrieval**: Buries operative articles under generic risk-tier dumps.
- **Fast mode / thinking token budget tweaks for latency**: Latency is dominated by wrapper CLI floor, not model token flags.
- **CLARA logical engine re-wiring** (`app/engines/clara_logic.py`): superseded by `prohibited_gatekeeper` — recorded wrong verdict (risk_tier=minimal) on the prohibited emotion-monitoring scenario; zero import sites; re-wiring regresses a currently-passing scenario (2026-08-17 architecture review).
