# Deep Code Review: R268 "latency optimisations and fixes" batch

**Date:** 2026-07-04 17:29:27
**Review target:** `d6fc4a1..5685c17` (the R268 batch) → base for fix branch `r268-1-oxford-comma-multiarticle` off `origin/main` `628fa20`
**Commit reviewed:** `5685c1753e68f964d3c2a6b41672377a66f6aa4a`
**Files changed (production):** 4 — `app/llm/openai_wrapper_provider.py` (+8), `app/config.py` (+19/-3), `app/engines/graph_rag.py` (+87/-11), `app/routes/regenold.py` (+4). Plus tests + `evals/regenold/scenarios_multiarticle_r268.py` + CLAUDE.md.
**Diff size category:** Medium (production footprint ~130 lines)

## Executive Summary

The R268 batch is sound and ships as-is. The four changes: (1) httpx
`keepalive_expiry=90s` to keep the Cloudflare-edge TLS connection warm — a
genuine, reliability-safe latency win; (2) `thinking_tokens` 4000→2048 — a
correct config restore, pinned tests green; (3) widened multi-article/annex
entity extraction; (4) an Art 65(4) cite-anchor. One **Important** correctness
gap was found *inside R268's own regex* (the Oxford-comma list shape silently
drops the trailing article) and is **fixed** in this branch; two **Suggestions**
(an inert annex over-capture; a misleading keepalive comment) are documented and
the comment corrected. No Critical issues. All findings verified against the
real code with empirical runs, not static reading alone.

**Process note:** the CR-SKILL parallel specialist fan-out (Logic / Error /
Contract / Concurrency / Security / Perf / Eng-Manager → adversarial Verifier)
was dispatched twice via a Workflow and both times **every** agent failed on a
sustained Anthropic server-side rate limit ("Server is temporarily limiting
requests · not your usage limit"). Rather than burn further attempts, the review
was completed inline covering all seven lenses, with each finding verified by
running the actual regexes, the engine (`ask_compliance_question` /
`_deterministic_parse` / `_retrieve_from_kb`), the pinned tests, and by tracing
the wrapper's `except` path and the wire existence gate.

## Critical Issues

None found.

## Important Issues

### [I1] Multi-article regex drops the trailing Oxford-comma item — FIXED
- **File:** `app/engines/graph_rag.py` (`_MULTI_ARTICLE_MENTION_RE` ~1583, `_MULTI_ANNEX_MENTION_RE` ~1596)
- **Bug:** The list separator was a single connector `\s*(?:,|&|/|\band\b|\bor\b)\s*`. On the Oxford-comma shape "Articles 9, 10, **and** 15" the connector before the last item is a comma *followed by* "and" (`, and`); the single-separator form matched only the comma, so the `\d` after it saw "and 15" → the list ended at "10" and **"15" was silently dropped**. Same for "Annex XI, XII, **or** XIII" → dropped "XIII".
- **Impact:** R268's stated goal is to ground *every* named article so its KB obligation substance reaches the Stage-2 context. The Oxford comma is the commonest way to write a 3+ item legal list, so the feature failed on exactly the shape it targets. (Still a strict improvement over pre-R268, which captured *nothing* for plural "Articles" — verified: `old(["Articles 9, 10, and 15"]) == []`.)
- **Verification (empirical):** ran both regexes — `NEW("Articles 9, 10, and 15") == ['9','10']` (drops 15); post-fix `== ['9','10','15']`.
- **Fix applied:** separator → one-or-more run `(?:\s*(?:,|&|/|\band\b|\bor\b)\s*)+`, consuming `, and` / `, or` as one separator. ReDoS-safe (each iteration consumes a required connector; bounded `{0,8}`; 0.12 ms on 600-comma pathological input). **davidath byte-identical** (0/6358 string-value deltas). +12 regression tests.
- **Confidence:** High
- **Found by:** Logic & Correctness (inline)

## Suggestions

- **[S1] Annex over-capture is inert but latent (`graph_rag.py` ~1596).** An UPPERCASE Roman-letter word after a connector ("Annex III, **CE** marking" → captures bogus "Annex C"; "LIVE" → "LIV"; "CIVIL") becomes a `query.entities` token. It yields no `EC_CHECKER_OBLIGATION_MAP` entry → surfaces no obligation → is dropped by the wire's existence gate (verified: `_retrieve_from_kb` surfaces no obligation for "Annex C"). Lowercase words are already filtered by the case-sensitive inner `re.findall(r"[IVXLC]+", …)`. Left as-is; pinned inert by a regression test. A future entity consumer that skips the existence gate would need to re-check this.
- **[S2] Keepalive comment overstates httpx (`openai_wrapper_provider.py` ~261) — CORRECTED.** The comment claimed "httpx transparently retries a server-closed stale connection." httpx does not auto-retry a mid-flight `RemoteProtocolError`. The actual safety net is `complete()`'s `except httpx.HTTPError` (base class of `RemoteProtocolError`/`ConnectError`) → provider error → Groq/deterministic fallback (fail-soft, never a 500). Comment rewritten to describe the real behaviour; the keepalive change itself is safe as shipped.

## Cleared on inspection (no finding)

- **Contract:** `keepalive_expiry` is a valid `httpx.Limits` kwarg; config moderate(2048)/extended(`complex_thinking_tokens`) split intact (24 pinned tests pass); the R268 cache-key correctly folds in `REGENOLD_MULTI_ARTICLE_ENTITIES`. (Minor: `_MULTI_ARTICLE_MENTION_RE` intentionally mirrors — but does not import — `scope.py::_ARTICLE_REF_RE`; acceptable duplication, the comment says so.)
- **Concurrency:** `httpx.Client` is thread-safe; the wrapper singleton is lock-guarded; `keepalive_expiry` adds no shared-state race; the engine LRU key is correct.
- **Security:** no ReDoS (bounded `{0,8}`, required-progress groups; smoke-tested); regexes are read-only over question text, no injection surface.
- **Perf/latency:** 90s < the edge's server-side idle close, so pooled reuse almost always hits a live connection (real handshake saving); the rare stale race fails soft. `thinking_tokens` is a ceiling the model does not fill → not a latency lever (consistent with the config doc + the live 4000/1024/0 wash measurement).

## Plan Alignment

R268 CLAUDE.md claims verified: "davidath byte-identical" (confirmed here for R268 and R268.1 by the 0-delta regex diff) and "thinking budget not a latency lever" (consistent with the code path + prior live measurement). The R268 `ab_judge` pairwise (branch leans win 4/4 axes, 0 regression) is the documented merge evidence per hard rule #6.

## Review Metadata

- **Lenses applied:** Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security, Performance & Reliability, Eng-Manager (plan-eng-review) — completed inline after the parallel Workflow was rate-limited.
- **Scope:** the 4 production files + their functions/callers + the new tests + the existence gate (`ARTICLE_EXISTENCE`, `EC_CHECKER_OBLIGATION_MAP.get`) + the wrapper `except`/fallback path + all davidath string values.
- **Raw findings:** 3 (1 Important, 2 Suggestion). **Verified:** 3. **Filtered:** 0 (the over-capture severity was empirically down-graded to inert; the keepalive to comment-only).
- **Fixes shipped in this branch:** I1 (regex) + S2 (comment); S1 documented + pinned inert.
- **Gates:** R268 tests 26/26 · OOS 21/21 (0 leaks) · 276-runner 255/255 (100%, RISK_F1 macro 1.00) · davidath byte-identical (0/6358 regex deltas).
- **Steering files consulted:** CLAUDE.md (claims verified against code).
