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

## ⛔ The deterministic suites are OFF as gates (operator directive, R330)

**Do not block a change on `evals.bench.runner` (davidath 476) or
`evals.regenold.runner` (the 276 scenarios). Do not run them by default.**

* **davidath** is a *regression guard*, never a win-measure, and costs ~9 min a run. Its
  gold is article-ints-only, so sub-point and Annex-grain changes are invisible to it.
* **the 276-scenario runner** is older still and largely superseded — treat its output as
  stale unless you have first confirmed the specific scenarios you care about are current.

**The merge gate is the live pairwise A/B** (`evals.harness.ab_judge` /
`evals.harness.easyhard_ab`), scored by the grounded judge (`evals/judge/grounded.py`)
against verbatim Act text. That is the only instrument that measures what the competition
measures. Run a deterministic suite only when a change is *expected* to move deterministic
retrieval and you specifically want the before/after — and say so explicitly.

R330 ran davidath four times to isolate the `.env` coupling below; that job is done and the
result was byte-identical to the reference table. The table is kept for provenance, not as
a thing to reproduce on every change.

## Reranking (R329)

**A cross-encoder reranker is standard in production RAG and is wired here** —
`app/engines/cohere_rerank.py`, applied at the RETRIEVAL stage in
`app/data/kb_search.py::top_articles_by_relevance` (retrieve wide with BM25 → rerank the
pool → cut to `k`). Gate `REGENOLD_COHERE_RERANK`, default OFF pending the A/B; needs
`COHERE_API_KEY`.

Two things to keep straight, because they are different interventions and only one has
been measured:

* **Retrieval-stage rerank (wired, being measured).** The reranker sees the raw candidate
  pool before anything is selected. Spot check: for *"must a deployer of an emotion
  recognition system inform the people exposed"*, it lifts `Art. 50.3` — the exact
  governing provision — from rank 2 to rank 1 and drops the irrelevant `Annex III` /
  `Art. 5` out of the top-5. Gate on `easyhard_ab` (gold-bearing).
* **Post-hoc reordering of the final emitted reference list (measured, does NOT help).**
  Zero-variance replay of the live HARD run: mean normalised position of judged-wrong refs
  0.582 → 0.562 (delta **−0.019**, i.e. slightly worse). By that point the wrong references
  are already semantically plausible — that is *why* they were emitted — so a relevance
  cross-encoder scores them high for the same reason the generator did. Do not re-propose
  this variant; it is the one that is dead, not reranking in general.

The wrong references on this corpus are **semantically plausible and legally inapposite**
(e.g. `Article 43`, conformity assessment, cited on a risk-classification question). The
signal that discriminates them is *legal applicability* — does this provision bind THIS
role at THIS risk class — which already exists here as `ROLE_OBLIGATIONS` /
`obligations_for` (`app/data/ontology.py`) and, unread, as the graph's
`Obligation`/`HAS_OBLIGATION` (113) and `RiskLevel`/`APPLIES_AT` (47) layers. That is a
grounding predicate, not a positional trimmer, so it sits outside the refuted trimmer
families.

⚠ **`gold_dropped` does not exist anywhere in this repo**, so the standing rule "a
reference change must drop ZERO gold" is currently **unenforceable**. Port
`gold_dropped_head` before gating any reference change. Do NOT port the upstream
`ref_crag_fine` / `gold_dropped_exact` as-is — measured defective: gold is head-projected
while predictions keep full coordinates, so `['Article 5.1.f','Annex III.2']` against gold
`['Article 5','Annex III']` scores `gold_dropped_exact = 2` and `ref_crag_fine = -1.0`,
penalising the most accurate citation shape the system emits.

## Baseline Performance Reference (Commit `b47c259`)

Deterministic environment: `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0`

| Metric Axis | Ans Loose | Ans Strict | Ans Conc | Ref Loose | Ref Strict | Ref Conc | Tone |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OVERALL (476)** | 0.1884 | **0.3545** | 0.6143 | **0.5971** | **0.4748** | 0.4316 | 1.0 |
| **QA (137)** | 0.1407 | 0.4072 | 0.1961 | 0.8394 | 0.5536 | 0.4390 | 1.0 |
| **Scenarios (339)** | 0.2076 | 0.3332 | 0.7833 | 0.4992 | 0.4430 | 0.4287 | 1.0 |

Multi-turn coherence: **20/20 coherent**.

> **R330 — the bench measures CODE DEFAULTS, never your `.env`.** R329's
> `_load_dotenv_once()` (`app/config.py`, added to fix the "No Conn" UI bug) put the
> repo `.env` into `os.environ` at **import time**. `.env` carries BEHAVIOURAL flags
> (`REGENOLD_ROLE_DUTY_NOUN_SEED`, `REGENOLD_GRAPH_2HOP`, `REGENOLD_MAX_ANSWER_SENTENCES`
> …) next to credentials, so from that commit on the guard silently scored whatever a
> developer happened to have locally. Measured cost on the full 476:
>
> | arm | Ref Loose | Ref Strict | multi-turn |
> | :--- | :--- | :--- | :--- |
> | code defaults | 0.5971 | 0.4748 | 20/20 |
> | `REGENOLD_ROLE_DUTY_NOUN_SEED=1` alone | 0.5971 | 0.4633 | 20/20 |
> | the full local `.env` | 0.5735 | 0.4489 | 13/20 |
>
> This looked exactly like a **−0.026 Ref Strict / −45 pp coherence regression across 15
> commits that are in fact behaviourally neutral.** 13 of the 14 flags are individually
> inert; `ROLE_DUTY_NOUN_SEED` alone costs −0.0114 Ref Strict and the rest is interaction.
> `evals/bench/runner.py` now sets `REGENOLD_SKIP_DOTENV=1` before the first `app` import,
> which reproduces the table above byte-for-byte. Set `REGENOLD_SKIP_DOTENV=0` for a
> deliberate `.env`-on arm. **Live harnesses are unaffected — they still need `.env` for
> `OPENAI_API_BASE` + `CF_ACCESS_*`.** Production is unaffected either way (Railway sets
> real env vars and `override=False` already makes those win).
>
> **It also breaks the SCOPE gate.** `runner_v2 --local --probe-oos --oos-suite all`
> (n=51), which still loads `.env`:
>
> | arm | pass | scope leaks | `hard_fail` |
> | :--- | :--- | :--- | :--- |
> | code defaults (`REGENOLD_SKIP_DOTENV=1`) | 49 | **0** | False |
> | `.env` loaded, `REGENOLD_*` blanked | 46 | **3** | True |
> | the full local `.env` | 35 | **15** (29.4%) | True |
>
> No single `REGENOLD_*` flag reproduces it (all measured individually at 0 leaks), and
> neither does `GROQ_API_KEY` alone — so it is the CREDENTIALS reaching the R267.1
> Groq→Gemini→Mistral fallback, plus interaction with the flags. **The "deterministic"
> OOS probe is not deterministic when `.env` is present: the scope classifier can make
> live third-party calls.** Run it as
> `REGENOLD_SKIP_DOTENV=1 … -m evals.regenold.runner_v2 --local --probe-oos` until
> `runner_v2` gets the same guard `evals/bench/runner.py` now has.
>
> ⚠ **Open operator question:** does the Railway dashboard carry the same behavioural
> flags? If yes, production pays this cost — including, potentially, the scope leaks.
> If no, local evals do not predict production. Neither is acceptable silently —
> reconcile the two flag sets.

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
