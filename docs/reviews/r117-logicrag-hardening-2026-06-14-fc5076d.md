# Deep Code Review: R117 (LogicRAG + Groq/Claude-Max provider arch + RushDB removal)

**Date:** 2026-06-14
**Branch:** fix/r117-logicrag-hardening -> main
**Base commit reviewed:** fc5076d (R117 range `6ab4aed..HEAD`)
**Files changed (R117):** 31 | **Lines:** +2562 / −3139
**Diff size category:** Large
**Trigger:** auto `/plan-eng-review` (eng-manager lens) + `CR-SKILL.md` (deep-code-review, 6 parallel specialists + verifier)

## Executive Summary

R117 shipped a new LLM-driven retrieval engine (`logic_rag.py`, default-ON in
production via `railway.toml REGENOLD_LOGIC_RAG=1`), a Groq/Claude-Max provider
rearchitecture, and a clean RushDB removal. The RushDB removal is well-scoped
(zero dangling references in `app/`). The provider rearchitecture is sound. The
**new LogicRAG engine carried the round's real defects** — all concentrated in
`app/engines/logic_rag.py`. Six specialists raised 20+ candidate findings; the
verifier confirmed 4 Critical + 5 supporting (one cross-agent "cache key
missing `REGENOLD_LOGIC_RAG`" was a **false positive** — it IS in the key at
`routes/regenold.py:1282-1283`). All confirmed findings are fixed on this
branch; davidath stays byte-identical by construction (LogicRAG is inert in the
deterministic bench).

## Critical Issues

### [C1] `_merge_contexts` discards `obligations` (and 9 other payload fields) on every multi-rank merge
- **File:** `app/engines/logic_rag.py:162-174` (pre-fix)
- **Bug:** The merge copied only `article_info` + the two traversal counters +
  `degraded`. `GraphContext` has 17 fields; `obligations` — the PRIMARY citation
  and answer source, consumed downstream as `context.obligations +
  context.article_info` and rendered first in `_build_context_references_block`
  — plus `semantically_relevant_statements`, `referenced_annexes_and_recitals`,
  `xrefs`, `gaps`, `satisfied`, `dimension_info`, `transitive_deps`,
  `cross_framework`, `web_search_results` were all silently dropped.
- **Impact:** A multi-rank DAG (LogicRAG's whole reason to exist) accumulates
  `article_info` from every rank but `obligations` from NONE → the engine ships
  an obligation-empty context, **strictly worse than the single-rank
  deterministic path it replaces**. Fires on the complex questions LogicRAG
  gates on.
- **Fix:** `_merge_contexts` now carries every payload field, deduped by `id`
  where present; string lists order-preserving-deduped; `cross_framework`
  shallow-merged.
- **Confidence:** High. **Found by:** Logic (95), Architecture (90); verified
  against the `GraphContext` dataclass.

### [C2] No total wall-clock cap on LogicRAG → blows the sub-20s budget / Railway healthcheck
- **File:** `app/engines/logic_rag.py` (`execute_logic_rag`, pre-fix)
- **Bug:** The only latency bound was a per-`_call_llm` timeout (15s). A
  multi-rank DAG chains 1 decomposition + N per-rank pruning calls, each a
  Claude-Max round-trip over the Cloudflare tunnel, then Stage-2 polish runs
  AFTER. A 3-rank DAG ≈ 45-60s with no circuit-breaker; `railway.toml`
  `healthcheckTimeout = 30` → a 502 instead of a graceful answer. Latency is a
  scored competition axis.
- **Fix:** total wall-clock deadline `REGENOLD_LOGIC_RAG_BUDGET` (default 12s) —
  checked before each rank's pruning call (break + finalise) AND threaded into
  every `_call_llm` as `timeout_override = remaining` so a single in-flight call
  can't exceed the budget. Plus a DAG node cap `REGENOLD_LOGIC_RAG_MAX_NODES`
  (default 6) bounding the call count.
- **Confidence:** High. **Found by:** Architecture (95), Concurrency (70).

### [C3] `str.format()` on user/LLM/KB strings crashes on a literal `{` / `}`
- **File:** `app/engines/logic_rag.py:68` (DAG) + `:226-238` (context pruning), pre-fix
- **Bug:** `DAG_DECOMPOSITION_USER_TEMPLATE.format(q=query)` runs BEFORE the
  try/except; a question containing `{x}` raises `KeyError`. The pruning
  `.format(q=, memory=, subq=, context=)` substitutes LLM/KB-generated values
  that may contain braces. The route-level try/except catches it (no 500) but
  LogicRAG is silently disabled, or a brace matching a real keyword silently
  corrupts the prompt.
- **Fix:** new `_safe_fill` — single-pass regex substitution; brace-bearing
  values are inert and can never raise.
- **Confidence:** High. **Found by:** Error Handling (95/90), Architecture (85).

### [C4] Empty-DAG → empty (non-`None`) context bypasses the deterministic fallback → zero-retrieval floor
- **File:** `app/engines/logic_rag.py` (return) + `app/engines/graph_rag.py:4246` (gate)
- **Bug:** On an empty DAG (or a content-free retrieval), `execute_logic_rag`
  returned a zero-value `GraphContext`. The route gate is `if context is None`
  → False for an empty-but-non-None context → the deterministic
  `_retrieve_from_graph` fallback is SKIPPED → the request bottoms out in the
  R47-E `Art. 1/2/3` zero-retrieval floor.
- **Fix:** `execute_logic_rag` returns `None` when `not ranks` OR the
  accumulated context has no obligations AND no article_info, so the route falls
  back to deterministic retrieval.
- **Confidence:** High. **Found by:** Logic (95); verified against the gate.

## Important Issues (fixed)

- **[M1] Synthetic "LogicRAG Synthesis" `article_info` entry** reached the
  Stage-2 prompt via `_build_context_references_block(article_info[:15])` as a
  citable `(Article: LogicRAG Synthesis)` line and burned a citation-budget
  slot (the wire validator correctly drops it from `references`, so no malformed
  wire cite). **Fix:** rolling memory now flows via a dedicated
  `GraphContext.synthesis_memory` field rendered as a labelled NON-citation
  Stage-2 section; the fake article is gone. Found by Logic/Contract/Concurrency/Architecture (consensus).
- **[M2] Prompt-injection surface** — LogicRAG passed the raw user query into
  the DAG/pruning prompts with no `sanitize_for_llm` (the Stage-1/2 paths apply
  it; `PROMPT_HARDENING_PREFIX` is a `""` no-op, so `sanitize_for_llm` is the
  real defense). Injected content flows query → rolling_memory → Stage-2
  context. **Fix:** `sanitize_for_llm(query)` before any prompt build.
- **[M3] Topological-sort int/str id mismatch** — `"id": 1` vs
  `"dependencies": ["1"]` left the edge permanently unresolved → every node
  dumped into one rank. **Fix:** normalise ids + deps to `str`; drop deps
  referencing non-existent ids.
- **[M4] `_call_llm` ignored `finish_reason="length"`** → a truncated rolling
  memory shipped as complete. **Fix:** treat length-truncation as a soft
  failure (return `""`), mirroring the R91 Stage-2 guard.
- **[M5] No DAG node cap / duplicate-id dedup** — unbounded sequential calls;
  duplicate ids silently collapsed in the lookup. **Fix:** `_finalise_dag`
  dedups + caps.

## Suggestions (not fixed this round)

- Cache key: added `REGENOLD_LOGIC_RAG_{BUDGET,TIMEOUT,MAX_NODES}` to
  `_engine_cache_key` (the latency/cap knobs flip the engine output). **Done.**
- `seed_neo4j_kb.py` module-level `assert not _unmapped_dims` runs at import; on
  a future unmapped dim it surfaces as a thread import crash rather than a clean
  `auto_seed_failed` event (caught by `main.py`'s thread try/except — not a 500).
  Currently passes. Deferred (low risk).
- DRY: `_decompose_to_dag` reimplements JSON extraction that
  `graph_rag._extract_json_object` already does. Deferred (refactor).
- LogicRAG `_call_llm` hardcodes the wrapper; under `P2P_GRAPH_RAG_PROVIDER=
  anthropic` (Pro-tier fallback) it returns "" and degrades to single-node.
  Production uses the wrapper, so latent. Deferred.
- LogicRAG bypasses `_maybe_sufficient_context_hop` (R110) when it returns a
  context — intentional design (LogicRAG IS the multi-hop decomposition). Left.

## False Positives (verifier-rejected)

- "Cache key missing `REGENOLD_LOGIC_RAG`" (Architecture, 88) — **WRONG**, it is
  present at `routes/regenold.py:1282-1283` with `REGENOLD_LOGIC_RAG_MODEL`.

## Plan Alignment

No `R117-PLAN.md` exists; R117 lives only in commit messages + the test file
docstring (`test_logic_rag.py`: "Before R117 it shipped with ZERO test
coverage"). This review closes the gaps that hardening round left in the new
engine.

## Review Metadata

- **Agents dispatched:** Logic & Correctness, Error Handling & Edge Cases,
  Contract & Integration, Concurrency & State, Security, Architecture &
  Eng-Manager (6, parallel, Sonnet). Verifier pass by the orchestrator (Opus).
- **Scope:** R117 diff `6ab4aed..HEAD` — `logic_rag.py`, `graph_rag.py`
  (LogicRAG integration + GraphContext + extraction), `_graph_rag_data.py`,
  `prompts_logic.py`, `main.py`, `routes/regenold.py`, `kb_search.py`,
  `seed_neo4j_kb.py`, `railway.toml`, RushDB deletions + tests.
- **Raw findings:** 20+ | **Verified + fixed:** 9 (4 Critical, 5 Important) |
  1 false positive | several deferred suggestions.
- **Steering files consulted:** CLAUDE.md (R117 undocumented in narrative —
  reconstructed from commits), project memory.

## Verification (this branch)

- Focused: `test_logic_rag.py` + `test_r91_llm_truncation.py` — **48 pass** (+25 new R117-review tests).
- Full suite (deterministic `provider=cli`): **3685 pass, 1 skip**; the 22
  remaining failures are the documented pre-existing `provider=cli` Stage-2-gate
  env artifact (identical at baseline via stash A/B; all 135 pass under the
  wrapper-enabling env with these changes).
- OOS probe: **21/21 PASS, 0 leaks**.
- davidath bench + 276-runner: byte-identical by construction (LogicRAG inert in
  the deterministic bench) — see round entry.
