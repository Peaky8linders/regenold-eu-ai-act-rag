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
`evals.regenold.runner` (**255** scenarios — this file long said 276; `_build_full_scenarios`
silently swallows a missing `scenarios_omnibus_extended`). Do not run them by default.**

* **davidath** is a *regression guard*, never a win-measure, and costs ~9 min a run. Its
  gold is article-ints-only, so sub-point and Annex-grain changes are invisible to it.
* **the 255-scenario runner** is older still and largely superseded — treat its output as
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

**⚠ CORRECTED R331 — the paragraph below previously claimed the reranker was
"applied at the RETRIEVAL stage in `app/data/kb_search.py::top_articles_by_relevance`".
It was not.** That placement was reverted after it measured **0 calls**, and until R331
nothing outside `app/engines/cohere_rerank.py` and its test file imported the module at
all. A fresh session that trusted this file went looking for a call site that did not
exist. What follows is the wiring that is actually on `main`.

**Where it is wired (R331):** `app/engines/_graph_rag_impl.py::_render_supplementary_sections`,
reordering the graph-context ref list immediately before `render_kg_context`, using
`context.question` as the query. Gate `REGENOLD_COHERE_RERANK`, default OFF pending the
A/B; needs `COHERE_API_KEY` (present in `.env` and on Railway); registered in
`_engine_cache_key`.

It composes with R330's repair of the same call site (which passes `context.question` so
the R327 semantic layers stop being dead code): the rerank sits between the two, so with
the gate ON both the graph fetches and the semantic layers see the reranked order, and
with the gate OFF the block is byte-identical to R330. `test_r330_question_still_reaches_the_graph`
pins that R331 does not re-break R330's fix.

**Why that placement and not retrieval.** Every `kg_context.fetch_*` reader truncates via
`_node_ids(refs, limit=max_refs)`, `max_refs` default **8**. The cut is by list position,
so when the context carries more than 8 refs the order decides *which* provisions' verbatim
paragraph and sub-point text reaches Stage-2 — a content change, not a permutation of the
output. It targets **Answer Correctness**, the largest gap to frontier. The graph blocks are
non-citable (`AGENTS.md` invariant #3), so this **cannot** add, drop or reorder a wire
citation — which is why it is not blocked on the missing `gold_dropped` guard. Gate it on
`ab_judge` (it moves answers), **not** `easyhard_ab`.

**Prove it fires before reading any number.** `cohere_rerank.rerank_stats()` returns
`attempts / reordered / noop / failed`. R329 tried three placements; all three looked right
in the diff and all three made zero calls, reading +0.0000 — indistinguishable from a lever
that does not work. `tests/test_r331_rerank_placement.py` pins that the placement fires,
that the surviving top-8 set actually changes, and that the flag reaches the cache key.

⚠ **The "the model itself is good" probe is weaker than recorded.** The claim was that it
separates `Art. 50.3` **0.9244** from `Art. 19` **0.0394** and `Art. 99` **0.0090**.
Re-measured live against this repo's own `get_provision_text`: `Article 50.3` **0.8803** and
`Article 19` **0.0286** reproduce, but **`Article 99` scores 0.4583 — 50× the recorded
figure**, and it is the case that discriminates. Article 99 is *penalties*: legally
inapposite to a transparency-duty question, semantically plausible because its text
enumerates the very articles being asked about. That is exactly the failure class this
corpus suffers from, and a relevance cross-encoder does **not** cleanly reject it. Expect a
smaller effect than the probe implies, and prefer feeding sub-provision text over
full-article text where the ref grain allows it.

Two things to keep straight, because they are different interventions and only one has
been measured:

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

⚠ **CORRECTED R360 — `gold_dropped` DOES exist and the rule IS enforceable.**
The paragraph below previously read "`gold_dropped` does not exist anywhere in this
repo, so the standing rule … is currently **unenforceable**. Port `gold_dropped_head`
before gating any reference change." That was false when written and it cost work:
three separate reference-affecting changes were held back as ungateable. The
instrument is `gold_dropped_head` at **`evals/bench/metrics.py:555`**, wired into
`evals/harness/easyhard_ab.py::_score_row` and aggregated as a **SUM**, i.e. the gate
is literally "drop ZERO". Only the *exact* (sub-point) grain is missing — which is the
separate, still-correct point below.

⚠ **CORRECTED R365 — "gated" was the wrong word; until R365 it was only PRINTED.**
The SUM existed and the `<-- GOLD DROPPED (hard rule #8)` flag string was emitted,
but nothing enforced it: `gold_dropped_head` is absent from `_AXES` and `_LEVERAGE`,
the module had no `assert` and no `hard_fail`, its only `SystemExit`s were argparse
errors, `main()` returned `None` under a bare `main()` call in `__main__`, and the
repo has no `.github/` to consume it. A replay of the real `easyhard-r332-smoke-A`
checkpoint with one gold head deleted from the branch arm printed
`gold_drop_hd  0  1  +1  <-- GOLD DROPPED (hard rule #8)` and **exited 0**. Every
historical "it passed the gold gate" claim was a human reading stdout.

**R365 makes it an exit code.** `main() -> int` returns **1** when the branch arm
drops more gold heads than the baseline on ANY split, wired through
`raise SystemExit(main())`; the delta is read from the PAIRED subset where one exists
and from the full aggregate otherwise; the per-row `gold_dropped_head_refs` are
printed so a failure is actionable. The decision is the pure
`_gold_gate_verdict(base_agg, branch_agg, allow, paired=…)`, pinned two-sided and
offline by `tests/test_r365_gold_gate_enforced.py`. `--allow-gold-drop` forces exit 0
for a deliberate exploratory arm and says loudly that the run did **not** pass —
never cite an `--allow-gold-drop` run as having cleared the gate. A single-arm
scorecard is not gated; the rule is comparative.

⚠ **The sibling `evals/harness/ab_judge.py` still has the reports-but-never-enforces
shape** — it already has the plumbing (`main() -> int`, `raise SystemExit(main())`)
but returns 0 unconditionally on any completed run, so a `BASELINE wins (sig)`
verdict — the merge-blocking outcome the harness exists to detect — exits 0 exactly
as before. Deliberately left unchanged by R365 to keep that PR one concern. Do NOT port the upstream
`ref_crag_fine` / `gold_dropped_exact` as-is — the decision is right, but the reason
recorded here was wrong. **Corrected R331:** `_gold_exact_refs` does *not* head-project.
The real defect is that our probe gold carries **0/208 sub-point grain** — it is
article-level throughout — so `['Article 5.1.f','Annex III.2']` scored against gold
`['Article 5','Annex III']` yields `gold_dropped_exact = 2` and `ref_crag_fine = -1.0`,
penalising the most accurate citation shape the system emits. Same conclusion, and the
fix is gold that carries sub-point coordinates, not a change to the metric.

## Stage-2 transport contract (R360)

**Stage-2 rides the cloudflared tunnel (Claude Max) first and AWS Bedrock second.
No third leg exists.** `app/llm/stage2_policy.py` is the single source of truth;
`REGENOLD_STAGE2_STRICT_TRANSPORT` (default **ON**) enforces it and is registered
in `_engine_cache_key`.

Five paths used to break that contract, and the first two were armed by nothing
more than an API key sitting in the environment — no flag, no deliberate opt-in:

| path | how it opened | now |
| :--- | :--- | :--- |
| Groq tertiary fallback in `_openai_wrapper_complete_for_graph_rag` | any `GROQ_API_KEY` + one tunnel failure | refused |
| Gemini secondary fallback in `_claude_max_enhance_answer` | any `GEMINI_API_KEY` + tunnel *and* Bedrock both empty | refused |
| `P2P_GRAPH_RAG_PROVIDER=gemini\|anthropic` | explicit env | collapsed to the tunnel |
| fusion panel (`REGENOLD_FUSION_STAGE2=1`) | default roster is `(sonnet, groq, mistral)` | off-contract members filtered out of the roster |
| `P2P_GRAPH_RAG_PROVIDER=bedrock` | explicit env | collapsed to the tunnel — see below |

That last row is not an escape but an **inversion**: honouring it makes the
fallback the primary, so the Claude Max subscription is never dialled at all.

⚠ **The Groq hatch was not hypothetical.** It swapped in a *compressed* system
prompt (`_get_groq_compressed_system_prompt`) and, above ~11 kB, a shrunken user
message. So a deploy carrying `GROQ_API_KEY` answered its first post-hiccup
questions from a different model **on a prompt no eval has ever measured** —
silently, and attributed to the tunnel arm in any A/B running at the time.

**Prove it fires before reading any number.** `stage2_policy.transport_stats()`
returns `primary_attempts / primary_ok / primary_failed / fallback_* / refused /
refused_by_provider`, and `/healthz/llm` surfaces the same block under
`stage2_transport`. This follows the R329 rule the hard way: three rerank
placements all read correctly in the diff and all made **zero calls**, so
`tests/test_r360_stage2_transport_policy.py` asserts on those counters, never on
the shape of the code. It is also two-sided — it pins that
`REGENOLD_STAGE2_STRICT_TRANSPORT=0` *really does* still reach Groq, because a
guard whose OFF state behaves like its ON state is the inert-feature trap.

Four existing test modules (`test_fusion_stage2`, `test_gemini_routing`,
`test_anthropic_provider`, and the fusion half of `test_r127_trace_latency`)
cover the legacy multi-provider call shapes. Their assertions are unchanged;
they now declare `REGENOLD_STAGE2_STRICT_TRANSPORT=0`, the regime they were
written for.

---

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
> `REGENOLD_SKIP_DOTENV=1 … -m evals.regenold.runner_v2 --local --probe-oos` (as of R330
> `runner_v2` sets this itself for `--local --probe-oos`).
>
> ⚠ **Open operator question:** does the Railway dashboard carry the same behavioural
> flags? If yes, production pays the Ref-Strict cost. If no, local evals do not predict
> production. Reconcile the two flag sets. **This is an eval-fidelity question, NOT a
> production-safety one** — see the scope note below.

### The OOS probe over-counts: "leak" ≠ the product requirement (R330)

**Measured against LIVE production** (`--endpoint …up.railway.app`, n=51): 41 pass, 10
"scope leaks", `hard_fail: True`. **That verdict is a harness artefact, not a defect.**

The requirement is that the assistant **pushes back on ADVERSARIAL input**; answering an
off-topic pleasantry is acceptable. Split that way, production is clean:

| category | live result |
| :--- | :--- |
| `injection` ("ignore all previous instructions", "what is your system prompt", DAN) | **3/3 pass** |
| `injection_obf` (base64 payload, translate-then-follow, roleplay-as-unrestricted) | **3/3 pass** |
| `scope_drift_mt` (multi-turn pivot off a genuine Art. 9 / Annex III thread) | **3/3 pass** |
| `nonsense`, `greeting`, `other_regulation`, `nonexistent`, `standards`, `non_eu_ai_law` | **all pass** |
| `r34_p0` / `r47_e` (Netflix, restaurant, weather, a joke) | 7 "leaks" — **chit-chat, allowed** |
| `adjacent_eu` (Product Liability Directive, MDR clinical evaluation) | 2 "leaks" — answers are **legally correct** |

**12/12 on adversarial.** Do NOT "fix" this by setting `REGENOLD_TOPIC_FILTER=0/1` on
Railway: R255 disabled the broad subject-topic filter precisely because the keyword
classifier false-positived on genuine, keyword-less AI Act questions, and R256's design
routes those to the LLM gate so real questions get rescued. Turning the blunt filter back
on trades a non-problem for a real one.

⚠ **What IS worth knowing:** an anchor-less question lands in the ambiguous
`CONVERSATIONAL` bucket handed to the LLM scope gate, and `regenold.py:5002` records that
"with no LLM wired it fails soft to the generic decline". So every `--local`
deterministic OOS run **fails safe by construction** and cannot measure the live gate at
all. If you want to test scope behaviour, run `--probe-oos` against the DEPLOYED endpoint.
Judge it on the adversarial categories only.

---

## Recent Engine Fixes (R356–R359)

Concise record of the applied fixes; full rationale in `docs/reviews/`:

* **R356 — grounded judge-report fixes.** Entity-map anchors that were
  missing (e.g. `human oversight → Art. 14`, `Art. 79/80`, `Annex III.5.c/d`),
  the Article 6(3) derogation detector extended to the narrow-procedural
  shape, and two new curated intercepts (GPAI transparency exceptions,
  systemic-risk scope) — each verified against the official provision text
  and false-positive-checked across all 81 live rows.
* **R357 — Stage-2 truncation guard (default ON).** `_guard_stage2_truncation`
  detects an incomplete final sentence (incl. trailing `…`) in the polish,
  repairs it with one bounded completion call, and falls back to the complete
  deterministic Stage-1 answer when repair fails. Never ships a fragment;
  gate `REGENOLD_STAGE2_TRUNCATION_GUARD`.
* **R358 — curated authoritative intercepts.** Four new curated answers
  (emergency triage `Annex III.5.d`, health-insurance pricing `5(c)`, hospital
  deployer duties, provider pre-market duties) that seed gold-head reference
  sets and skip Stage-2 polish (`_is_curated_authoritative_intercept`).
* **R359 — fine-grained CRAG answer judge (⚠ NOT IN THIS REPO).** Corrected R360:
  `answer_crag_fine` has **0 occurrences** here — it lives in the eval repo only.
  The description below is of that repo's axis, kept for provenance. `answer_crag_fine`
  axis ports the NICD paper's Appendix C.2.2 5-level truthfulness scale
  (`+1 / +0.5 / 0 / −0.5 / −1`) to the ANSWER, with truthfulness = sum of
  scores and hallucinated-row counts. Opt-in (not in default `AXES`); judged
  via Bedrock sonnet, never the Claude-Max tunnel.
* **R328–R354 ports** — `query_expansion.py` (LLM query rewrite, default OFF),
  `risk_classification.py` (Annex-III risk-class anchor, default OFF),
  rerank + graph-semantic upgrades; see the port review doc.

## Environment Flags Reference

| Environment Variable | Code Default | Purpose |
| :--- | :--- | :--- |
| `P2P_GRAPH_RAG_PROVIDER` | `auto` | Selected LLM backend (`cli`, `anthropic`, `openai_wrapper`, `bedrock`) |
| `REGENOLD_STAGE2_STRICT_TRANSPORT` | `1` | R360 Stage-2 transport contract: cloudflared tunnel (Claude Max) primary → Bedrock fallback, everything else refused |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `1` | Stage-2 LLM polish master gate |
| `REGENOLD_GRAPH_SEMANTIC_LAYERS` | `0` | Constrained sub-provision vector search across Neo4j indexes (R327). **Corrected R360** — this table said `1`; R330 flipped the code default ON → OFF (`app/engines/graph_semantic.py:155`) |
| `REGENOLD_SEMANTIC_GLOSS` | `0` | Open-domain definitions/recitals gloss gate (R327) |
| `REGENOLD_GRAPH_VECTOR_RECALL` | `0` | Additive Neo4j & local SVD vector recall path (R326) |
| `REGENOLD_PARENT_COLLAPSE` | `0` | Collapse parent provisions when sub-points are cited (R325) |
| `REGENOLD_STAGE2_TRUNCATION_GUARD` | `1` | R357 post-generation truncation repair on the Stage-2 polish |
| `REGENOLD_QUERY_EXPANSION` | `0` | LLM query rewrite before retrieval (R328 port; latency+cost tradeoff) |
| `REGENOLD_RISK_CLASS_ANNEX` | `0` | Annex-III risk-classification anchor (R328 port) |
| `BEDROCK_REGION` | `eu-central-1` | AWS Bedrock cross-region inference profile geography (R328) |
| `NEO4J_AUTO_SEED` | `0` (or `off`) | Boot graph seeder safety switch (Keep 0 in production) |
