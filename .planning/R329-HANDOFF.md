# R329 handoff — HyPA-RAG fixed and shipped; NICD port pending

Merged to `main`: `1db5e9e` → `4a220b4` (PR #337). Deployed and verified live
(`/healthz` → `commit: 4a220b4357f1`). Full review: `docs/reviews/main-2026-08-13-r329-hypa-rag.md`.

## State you can rely on (do not re-audit)

**davidath 476, deterministic, run IN PLACE.** Three arms, identical dataset
fingerprint (`qa a2fffe370fff`, `scenarios 0fc1c7491372`):

| arm | config | result |
| --- | --- | --- |
| A | HyPA flags OFF | **byte-identical to the documented CLAUDE.md baseline**, all 6 axes |
| B | HyPA flags ON, pre-fix | QA RefConc **0.2296**, RefStrict **0.4399** |
| C | HyPA flags ON, post-fix | **byte-identical to baseline**, all 6 axes |

Arm A reproducing the baseline exactly is what makes this a clean isolation: it
proves every *other* uncommitted change in that tree was davidath-neutral, so
100% of the regression was the two HyPA flags.

**Per-row attribution (zero-variance, compares recorded `pred_refs`):**
73/137 QA rows changed · **+138 refs** · **1 GOLD DROPPED** (`qa_041` lost
`Article 50`) · top added `Article 16 (+20) / 17 (+18) / 19 (+14)` · dropped
included `Article 10.3` and `Annex III.2` (the sub-point collapse).

**pytest:** 79 failed / 6027 passed (baseline `a692ffb` was 87 failed).
**Zero failures in any module touched by this round.** The 5
`test_bedrock_client` failures are `.env` credential leakage — all 57 pass with
`AWS_BEARER_TOKEN_BEDROCK`/`BEDROCK_REGION` unset.

**ReDoS, measured over HTTP and after the fix:**

| payload | before | after |
| --- | --- | --- |
| `"What does Art 1" + " , "*16 + "X require?"` (73 bytes) | 25,635 ms | **0.02 ms** |
| annex equivalent | 28,568 ms | **0.01 ms** |
| `_DIRECT_ARTICLE_RE`, 3,000 spaces | 146,514 ms | **0.65 ms** |

Oxford-comma parsing verified intact (`"9, 10, and 15"`, `"XI, XII, or XIII"`).

## Traps that cost real time this round

1. **`stage2_landed_rate: 0.0` is a provider gate, not a bug in the feature.**
   `_stage2_provider_enabled()` returns False on its FIRST branch when
   `P2P_GRAPH_RAG_PROVIDER=cli` ("never enables Stage-2"). The Gemini July-7 run
   was p50 **176 ms**; a live Stage-2 run measured **88 s p50 / 153 s p95** this
   session. Their eval never made a single LLM call ⇒ half the production
   pipeline was unmeasured.
2. **Therefore davidath CANNOT clear a Stage-2 change.** `provider=cli` means
   prompt-level work (P3a/P3b) and `_needs_stage2_enhancement` are invisible to
   it. My arm A matching baseline did **not** clear the Stage-2 predicate; only
   reading the call site did.
3. **Sonnet 5 is NOT reachable for Stage-2 via env.** Hard Opus floor at
   `_graph_rag_impl.py:~631` — `if not model or "opus" not in model.lower():
   model = "claude-opus-4-8"`. The only branch without the floor is
   `complex_question and complex_model`, so `P2P_GRAPH_RAG_COMPLEX_MODEL=claude-sonnet-5`
   reaches Sonnet for complex rows only. Standard Stage-2 needs a code change.
4. **A predicate over `query.entities` must never test for `"Article N"`.**
   Entities are ALWAYS internal short form (`Art. N`). The narrowed
   `_needs_stage2_enhancement` fired **0/476** where the old rule fired 346/476.
5. **The ReDoS shape to grep for:** `\s*` on BOTH sides of a separator
   alternation inside `+`. Adjacent iterations compete for the same whitespace
   run ⇒ 2^n splits. The in-code comment asserting it was "ReDoS-safe" was wrong.
6. **Never `git add -A`.** `.claude/worktrees/*` are gitlinks; `uv.lock` and
   `.planning/R318-PLAN.md` are concurrent work. Stage explicitly.
7. **Never two wrapper-bound jobs at once.** A stale `ab_judge` held the wrapper
   for ~2 h here while measuring pre-fix code (it imports modules at process
   start, so later edits do not reach it).
8. **Piping a long run through `tail` hides it.** `pytest ... | tail -40` and
   `ab_judge ... | tail -70` buffer until process exit — no interim output and a
   truncated failure set. Redirect to a file instead.

## Corrections to earlier handoffs

* **R323-HANDOFF open item #1 is STALE.** "The vector layer is dead / `grep
  db.index.vector` returns nothing" is false — R326/R327 wired it. Verified live
  (`enabled is True` asserted first): **5 call sites**, **7 indexes ONLINE,
  128-dim cosine, 1490 embeddings (not 1483), 100% coverage**.
  `v_paragraph`/`v_point`/`v_subpoint` execute on **every question by default**
  (~320 ms, 21,581 chars rendered). Only `v_article`/`v_annex`
  (`REGENOLD_GRAPH_VECTOR_RECALL=0`) and `v_definition`/`v_recital` (gloss off,
  already A/B-negative at R327.1) stay dark.
  **Embedding parity is not a blocker** — `graph_semantic._embed` and the seeder
  share `embeddings_index._embed_query`, local `.npy`, independent of
  `REGENOLD_EXTERNAL_EMBEDDINGS`. Works fully offline.
* **Medical regulations are NOT in the graph.** `MATCH (n) WHERE n.framework IS
  NOT NULL` → `[]` (property does not exist); `LegalInstrument` has exactly ONE
  node (the AI Act, CELEX 32024R1689). The only MDR/IVDR content is the Act's
  own Annex I citation of 2017/745/746. The `MDR_IVDR` "cross-regulatory
  mapping" at `kg_context.py` is a hardcoded Python dict that performs a Neo4j
  round-trip and then ignores the result.
* **Genuinely idle graph layers:** `Obligation`/`HAS_OBLIGATION` (113),
  `CROSS_REFERENCES` (248 edges), `RiskLevel`/`APPLIES_AT` (47),
  `LegalInstrument`/`HAS_PROVENANCE` (126), `Guideline`/`INTERPRETS` (8).
* ⚠ Aura now emits `db.index.vector.queryNodes is deprecated, replaced by
  SEARCH` on **every** call (3× per question). Not breaking yet, unflagged.

## The pending port — read before touching it

Source: `D:\Claude Projects\antifragileai-regenold-evaluation`, HEAD `431021a`
(R329 = the NICD graph-RAG paper applied). Available here as git remote
`eval-repo` (fetched). Its plan:
`.planning/R329-PLAN-GRAPHRAG-PAPER-INTEGRATION.md` in that repo.

**The repos DIVERGED at `c0799df` (2026-08-06)** with ~20 commits each of
parallel, overlapping work. `AGENTS.md` forbids a direct merge between diverged
branches without a file-by-file audit. **Do not cherry-pick `431021a` wholesale**
— it touches exactly the four files `1db5e9e` just changed:

| file | this repo's change that MUST survive |
| --- | --- |
| `app/engines/graph_semantic.py` | `_adaptive_int` / `_adaptive_fanout` |
| `app/engines/kg_context.py` | `_adaptive_int`; deleted duplicate `fetch_provision_hierarchy` |
| `app/engines/_graph_rag_impl.py` | ReDoS regex fixes; HyPA `not query.entities` gate; restored `len(entities) >= 3` |
| `app/routes/regenold.py` | HyPA flags in `_engine_cache_key` |

R329 there = 11 files, +2441 lines: P0 `gold_dropped` (`easyhard_ab.py`),
P0b `ref_crag_fine` (`evals/bench/metrics.py`), P2 `REGENOLD_SEMANTIC_COORDINATES`,
P3a `REGENOLD_CITABLE_UNIVERSE_BLOCK`, P3b `REGENOLD_REF_UNCERTAINTY`, P3c
duplicate-clause dedupe, + 3 test files.

Truncation work to port: eval-repo `c6db579` *"stop the graph amputating
enumerations"*. ⚠ **Check first whether this repo's R323 `5354b86` already covers
it** (that commit did whole-enumeration delivery + `[...]` marker +
`REGENOLD_KG_MAX_CHARS`). Diff the functions, not the commit messages.

⚠ **Their three new flags ship default-ON, ungated**, reasoning that
`railway.toml [deploy.envs]` never applies so a code default is the only delivery
mechanism. The Railway premise is correct; the shape is exactly what cost
−0.209 Ref Conciseness here. **Port them default-OFF and flip each on its own
measurement.**

Audit workflow run id: `wf_e6270cea-c56` (7 feature auditors + synthesizer).
Resume with `Workflow({scriptPath: ..., resumeFromRunId: "wf_e6270cea-c56"})`.
When the other repo is finished, re-fetch and diff `431021a..<new HEAD>` so only
the delta needs auditing.

## Open, ranked

1. **Land the NICD port** once the other repo settles — feature by feature, gate
   after each. `easyhard_ab` + `gold_dropped` for reference changes; `ab_judge`
   for prompt changes; davidath as the regression guard only.
2. **Re-run the July-7 batch with Stage-2 actually firing** — wrapper env
   `OPENAI_API_BASE=http://127.0.0.1:8000/v1 OPENAI_API_KEY=dummy
   P2P_GRAPH_RAG_PROVIDER=openai_wrapper`. Budget ~90 s/row serial (`--local`
   forces `workers=1`). The runner flushes a per-row `.ckpt.jsonl` but opens
   `"w"` — it restarts, it does not resume.
3. **The HyPA opt-in path is still unmeasured.** Default-OFF ships safely, but
   adaptive `top_k` inside the zero-anchor BM25 fallback has never been A/B'd.
4. **Bedrock, do not enable until gated:** region pinned at first client
   construction (`bedrock_client.py:284`) so any Bedrock A/B silently measures
   nothing; and the `BotoCoreError` path re-sends prompts to the wrapper host
   **skipping** the `is_openai_wrapper_enabled()` check the `ClientError` branch
   has — EU data-residency concern.
5. `evals/judge/runner.py:601` — `P2P_GRAPH_RAG_PROVIDER=bedrock` silently
   overrides an explicit `--provider`, violating the "evals use the wrapper" rule.
6. **Legally-correct but NOT live-A/B'd** (rode along in #337, authored
   upstream): `Art. 73` added to provider high-risk sets, downstream GPAI
   `Art. 89`→`Art. 25`, `Art. 27` FRIA dropped for `high-risk-annex-i`. All
   three verified against the Act. The Art. 27 **removal** is the R142.1 shape —
   revert first if the live judge disagrees.
7. Railway dashboard: confirm **no** `REGENOLD_HYPA_*` variable exists (a
   dashboard value would override the code default and reinstate the
   regression). Also still open from R323: is `REGENOLD_GRAPH_AWARE=1` set there?

## What the HyPA paper actually supports (do not re-propose)

Kalra et al. 2025, arXiv:2409.09046v2. **Its own Table 2 says PA-RAG (no
knowledge graph) BEATS HyPA-RAG on all four metrics** — Faithfulness 0.9044 vs
0.8328, Correctness 0.8141 vs 0.7918. §9: adding a KG "potentially lower[s]
response quality". §8.4: adding KG depth "lowers Absolute Correctness". The KG
half only wins **with `bge-reranker-large`** (0.8402) — and the reranker is the
one component not built (torch/GPU, forbidden; R46 already deleted a
cross-encoder as bench-negative).

* **RRF is refuted THREE times here** (`docs/ROUNDS.md` R31/R69: "davidath is
  BM25-saturated — proven again, third time since R31") and already exists at
  `turboquant_index.py:539` behind `REGENOLD_RRF_FUSION`, **default OFF**.
* Classifier: SVM-TFIDF **ties** DistilBERT at 0.92 on 2-class, so a no-torch
  classifier is defensible — but **no labelled complexity set exists** here, and
  sklearn is not installed (numpy/scipy are). That is the real blocker.
* The only transferable idea is a **lexical, reorder-only rerank** (no drops —
  R142.1 lost a pairwise 11-0, p=0.001), scored on the R317 zero-variance ref
  simulator before any live arm. Matches R318 §2 "work the ranker instead".
