# Deep Code Review: main (2026-08-13)

**Date:** 2026-08-13 13:06:00
**Branch:** main
**Commit:** HEAD
**Files changed:** 8 | **Lines changed:** +263 / -7
**Diff size category:** Medium

## Executive Summary

A multi-agent adversarial code review was conducted across recent changes in `app/engines/hybrid_rrf_retriever.py`, `app/engines/query_complexity_router.py`, `app/engines/_graph_rag_impl.py`, `app/llm/bedrock_client.py`, `app/routes/regenold.py`, and test modules. 9 verified bugs were identified, including a Critical parameter mismatch and dict-lookup error that broke BM25 candidate recall during HyPA RRF candidate fusion, a generator cancellation race in Bedrock streaming, and cache identity omissions.

---

## Critical Issues

### [C1] Broken BM25 Candidate Retrieval Call & Dict Lookup in HyPA RRF Candidate Fusion
- **File:** `app/engines/_graph_rag_impl.py:8329-8336`
- **Bug:** `top_articles_by_relevance` was invoked with `top_k=comp_params.top_k_dense` (`top_k` instead of `k`), raising `TypeError`. In addition, `top_articles_by_relevance` returns a `list[str]`, but code attempted dictionary lookups `art.get("article")`.
- **Impact:** BM25 sparse retrieval failed silently on every call with HyPA RRF enabled, completely stripping sparse candidates from candidate fusion.
- **Suggested fix:** Change keyword argument to `k=comp_params.top_k_dense` and extract string elements directly.
- **Confidence:** High (100%)
- **Found by:** Logic & Correctness Specialist

### [C2] Generator Cancellation Race (`ValueError: generator already executing`) in Bedrock Streaming
- **File:** `app/llm/bedrock_client.py:681-698`
- **Bug:** In `BedrockProvider.stream_async()`, `finally:` executed `sync_gen.close()` on the main event loop thread while a worker thread was still running `next(sync_gen)`.
- **Impact:** Raises `ValueError: generator already executing` on client disconnects during streaming.
- **Suggested fix:** Catch `ValueError` in `finally:` when closing `sync_gen`.
- **Confidence:** High (95%)
- **Found by:** Concurrency & State Specialist

---

## Important Issues

### [I1] Bedrock Model & Engine Flags Missing from `_engine_cache_key`
- **File:** `app/routes/regenold.py:1240-1270`
- **Bug:** Bedrock model environment variables (`REGENOLD_BEDROCK_MODEL`, `REGENOLD_BEDROCK_COMPLEX_MODEL`, etc.) and `REGENOLD_STAGE2_VERDICT_GUARD` were omitted from `_engine_cache_key()`.
- **Impact:** Violates cache identity invariants; model configuration changes serve stale cached responses.
- **Suggested fix:** Add missing Bedrock model flags and guard flags to `_engine_cache_key()`.
- **Confidence:** High (95%)
- **Found by:** Contract & Integration Specialist, Concurrency & State Specialist

### [I2] Reference Head Clamping & Parent Collapse Regex Failure on Parenthesized Subpoints
- **File:** `app/routes/regenold.py:2569, 4180`
- **Bug:** `split(".")[0]` retained `13(1)` for `Article 13(1)`, causing `_collapse_parent_when_subpoint_cited` to fail to recognize parent `"Article 13"`.
- **Impact:** Parent collapse fails to strip redundant parent citations on parenthesized subpoints.
- **Suggested fix:** Split on `[\.\(\s]` when extracting reference heads.
- **Confidence:** High (90%)
- **Found by:** Logic & Correctness Specialist

### [I3] Penalty Negative Lookahead Failure & Missing Article 5 Exclusion in Query Router
- **File:** `app/engines/query_complexity_router.py:25-38`
- **Bug:** `_DEFINITION_QUERY_RE` negative lookahead evaluated after matching `"the "`, failing to exclude `"penalty"`. `_DEFINITION_QUERY_RE` also lacked Article 5 exclusion.
- **Impact:** Penalty questions (e.g. `"What is the penalty..."`) and Article 5 queries were misclassified as Class 0 (Simple).
- **Suggested fix:** Include `penalties?|penalty` in lookahead list, and enforce explicit Article 5 check before returning Class 0 parameters.
- **Confidence:** High (90%)
- **Found by:** Logic & Correctness Specialist, Error Handling & Edge Cases Specialist

### [I4] Subpoint Regex & Rank Shift Penalty in HyPA RRF Retriever
- **File:** `app/engines/hybrid_rrf_retriever.py:30-84, 117-127`
- **Bug:** Regexes rejected multi-character lower-case Roman subpoints (e.g. `(ii)`, `(iv)`). Skipping duplicate candidate aliases incremented `rank`, penalizing subsequent unique candidates.
- **Impact:** Subpoint citations were rejected during validation, and candidate fusion scores were artificially skewed.
- **Suggested fix:** Strip trailing punctuation, accept `\([a-z0-9]+\)` in subpoints, use `_is_known_article_or_annex` and `reference_from_article_ref`, and increment `rank` only for valid unique candidates.
- **Confidence:** High (90%)
- **Found by:** Error Handling & Edge Cases Specialist, Logic & Correctness Specialist

### [I5] Bedrock Provider Exception Catch Order Blocks OpenAI Wrapper Fallback
- **File:** `app/llm/bedrock_client.py:574-637`
- **Bug:** `ClientError` is a subclass of `BotoCoreError`. `except ClientError:` caught all client errors, preventing `except BotoCoreError:` from executing proxy fallback.
- **Impact:** Recoverable Bedrock 429/500 errors failed immediately without trying proxy fallback.
- **Suggested fix:** Allow recoverable `ClientError` conditions to trigger proxy fallback.
- **Confidence:** High (90%)
- **Found by:** Error Handling & Edge Cases Specialist

### [I6] Unsynchronized Lazy Singleton Initialization
- **File:** `app/routes/regenold.py:207-213`, `app/engines/graph_expansion_engine.py:113-130`
- **Bug:** `_NLI_SCORER` and `_GLOBAL_EXPANSION_RETRIEVER` singletons were initialized lazily without thread locks.
- **Impact:** Concurrent cold requests race to instantiate models/retrievers.
- **Suggested fix:** Add `threading.Lock()` double-checked locking wrappers.
- **Confidence:** Medium (85%)
- **Found by:** Concurrency & State Specialist

### [I7] Roman Numeral Regex Pattern Omitted `D` and `M`
- **File:** `app/routes/regenold.py:3021`
- **Bug:** `_REF_PARSE_RE` character class `[IVXLC]` omitted `D` and `M`.
- **Impact:** References containing `D` or `M` failed parsing.
- **Suggested fix:** Update character class to `[IVXLCDM]`.
- **Confidence:** Medium (85%)
- **Found by:** Error Handling & Edge Cases Specialist

---

## Review Metadata

- **Agents dispatched:** 5 (Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security & Provider Safety)
- **Scope:** 8 files changed/new + adjacent modules
- **Raw findings:** 18
- **Verified findings:** 9
- **Filtered out:** 9 (duplicates / low confidence)
- **Steering files consulted:** `AGENTS.md`
