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

⚠ **`easyhard_ab` has THREE exit codes (R398): `0` PASS, `1` hard-rule-#8 FAIL,
`2` INDETERMINATE.** A verdict is indeterminate when no Stage-2 completion landed
(both arms then return the same deterministic answer and `delta=+0` is tautological,
not evidence), when a scored split is below `_MIN_GATE_N=30`, or when a split the
probe corpus carried scored zero rows. Before R398 all three printed **PASS, exit 0**
— measured at full corpus, easy n=95 / hard n=37. **Only exit 0 clears the gate;
never read the stdout instead of the exit code.** The n floor rejects smoke runs, it
does not confer power: the ref axes need n>=120 and the probe corpus holds 95/37.

### 1b. The DEPLOYABILITY gate — `.github/workflows/ci.yml` (R394.3)

⚠ **A green `pytest tests/` does NOT mean the commit deploys.** The suite runs
against your WORKING TREE; Railway deploys from a **clone**. PR #389 shipped
`from app.engines.prompt_budget import …` for a file that was never `git add`-ed,
so 7,525 tests passed locally while `import app.main` raised `ModuleNotFoundError`
on Railway, `/healthz` never bound, and production silently served the previous
release across two merges. Only git can see that class of defect.

CI is a clean clone, so it is the instrument. The `deployable` job runs the
tracked-module gate, imports `app.main`, then boots uvicorn using the start
command, healthcheck path and timeout it **parses out of `railway.toml`** (so CI
cannot drift into testing a command Railway does not run).

```bash
pytest tests/test_r394_2_tracked_module_imports.py -q (no tracked module may import an untracked one)
python .github/scripts/boot_healthcheck.py (boot per railway.toml and wait for /healthz — runs locally too)
git -c core.autocrlf=false archive HEAD | tar -x -C /tmp/cc (reproduce CI's exact tree)
```

⚠ **Use `-c core.autocrlf=false`.** On a Windows box `git archive` otherwise
writes CRLF, which changes the SHA of `evals/bench/data/*.json`, fails
`dataset.ensure_dataset()`'s pin, and makes 27 tests try to re-download the
davidath corpus — 27 phantom failures that do not exist on Linux CI.

Tests needing the gitignored competition data (`.gitignore:22-25`) **skip** with a
stated reason rather than fail; they still run wherever the data is present.
**Do not delete `.github/` again** — it was removed at `bc63f86`, which is why
there were no PR checks at all for the ~180 commits that followed.

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
   ├── _deepen_ref_grain                  — reference grain deepener (R386), default ON (R387)
   ├── _qrel_prune_references             — query-relevance pruning (R385), default OFF
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
   The AST gate now scans `app/engines`, `app/integrations/regenold`, `app/data`, and **`app/llm`**. Stage-0, Stage-2 and prompt flags are covered; the earlier warning that `app/llm` was invisible is stale (verified R416). Keep checking indirect/dynamic reads the literal AST collector cannot resolve.

5. **The Stage-2 prompt is NOT a sink** (R365). The wire `references` list is recomputed from the final Stage-2 prose by three default-ON, `stage2_landed`-gated passes - `_reconcile_references_to_prose` (drops), `_add_prose_named_refs` (adds), `_surface_prose_subpoints` (adds sub-points). So invariant #3 ("graph is additive only") means the graph cannot be a citation **SOURCE**; it does **not** mean a prompt-side change is reference-neutral. Any lever that changes the Stage-2 prompt must be gated on `gold_dropped_head`. A `provider=cli` test cannot show otherwise — the three passes are gated by `stage2_landed` at their route call sites and are skipped in the offline path, so a deterministic fixture pins reference-neutrality in the one regime where the coupling is switched off. (The functions themselves are NOT no-ops when called directly — R398 verified this.)

---

## Closed Directions (Do Not Re-propose)

Empirically measured failures in `docs/ROUNDS.md` — do not re-implement:
- **Global top-K clamps or positional reference trimming**: Drops gold references and loses pairwise A/B evals. **Re-confirmed R381 with a properly powered gate** — a terminal wire cap was built with a grounded ranker (so it would not be a naive positional clamp), then rejected: zero-variance simulation over a full live capture of the gold-bearing probe corpus (n=129) gives cap 3 → `gold_dropped_head` 37→41 FAIL, cap 2 → 65 FAIL, cap 1 → 113 FAIL, while the values that pass (4, 5) are worth ≤ +0.33 pp Overall. ⚠ The verdict REVERSED with n (cap=3 read "pass" at n=17/30/34); a zero-variance simulation removes GENERATION variance, not SAMPLING variance. And the grounded ranker itself measured WORSE than plain emission order — `_reference_described_in_prose` is number-anchored, so a gold provision the answer PARAPHRASES scores bottom tier and gets cut. `REGENOLD_WIRE_REF_CAP` stays at `0`. **Parent collapse is the part of this that IS free** (it removes a duplicate, not a provision) and ships default ON.
- **Neural NLI citation verification**: 235x slower and lower accuracy (ROC-AUC 0.585) than lexical scoring.
- **Graph-primary retrieval**: Buries operative articles under generic risk-tier dumps.
- **Fast mode / thinking token budget tweaks for latency**: Latency is dominated by wrapper CLI floor, not model token flags.
- **CLARA as a replacement for the prohibited gatekeeper** (`app/engines/clara_logic.py`): do not re-enable it for prohibited/curated classification verdicts; the recorded emotion-monitoring regression still rules that out. **R416 correction:** CLARA is NOT dead code. `regenold_eu_ai_act_ask` already imports and calls `analyse` under default-ON `REGENOLD_CLARA_VERDICT`, with non-empty candidates and exclusions for prohibited, classification and curated-intercept paths. Preserve those guards; do not delete the module based on the older "zero import sites" claim.
