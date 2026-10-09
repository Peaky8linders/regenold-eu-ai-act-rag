# Deep Code Review: feat/finalize-recent-fixes-and-optimisations

**Date:** 2026-10-09 08:39:46
**Branch:** feat/finalize-recent-fixes-and-optimisations -> main
**Commit:** 24538c34b25783e52bae0eb390855141eca567b4 (reviewed with the R463 working-tree fixes applied)
**Files changed:** 48 | **Lines changed:** +7928 / -386
**Diff size category:** Large

## Executive Summary

Seven specialist reviewers were dispatched in parallel over the branch diff
(43 files / +7489 at dispatch) and every loud finding was then re-read in the
code by the coordinator: two of the loudest were **deliberate, test-pinned
designs** and were reported rather than changed. Nine confirmed defects were
fixed, each proven two-sided (the new test fails on the pre-R463 code). The
highest-severity finding is a **credential leak in the evaluation harness**: two
eval entry points attached the Cloudflare Zero Trust service token to *any*
`OPENAI_API_BASE` / `R388_WRAPPER_URL`, including third-party hosts. The second
is a **statistics failure that flipped a published reading**: the R418/R419 audit's
tests were lazy `scipy.stats` imports, scipy is not a declared dependency, and the
degraded path returned `p=1.0` (Fisher) and `None`-read-as-support (paired tests),
so a re-run on this repo's own machine contradicted the committed artifact.

## Critical Issues

### [C1] The eval harness attached the Zero Trust service token to every host
- **File:** `evals/harness/frontier_baseline.py:110` (`_ask`), `evals/official/build_gold.py:60` (`_HDRS`)
- **Bug:** `_ask` looped `for h in ("CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET")` and attached the pair to whatever base it was handed, with **no host test at all**. `build_gold` had a host test but it was a substring check (`"127.0.0.1" not in base and "localhost" not in base`), which passes for any non-local URL. Both bypassed the resolver that exists precisely to pin this — `_resolve_cf_access_headers` / `_cf_access_trusted_hosts`, covered by `tests/test_r365_cf_access_host_pin.py`.
- **Impact:** Pointing `OPENAI_API_BASE` at any third-party OpenAI-compatible endpoint (or `R388_WRAPPER_URL` at a staging tunnel) transmitted the Cloudflare Access client id and **secret** to that host. That is a live credential to the production tunnel, and this repo's own measurement workflow is exactly where bases get repointed.
- **Suggested fix:** Both callers now resolve through `app.llm.openai_wrapper_provider._resolve_cf_access_headers`, which arms the pair only for a trusted host. `frontier_baseline` gained `_cf_access_headers` / `_headers_for`; `build_gold` gained the same helper for `_HDRS` (the browser `User-Agent` the tunnel needs and the `Authorization` header are untouched).
- **Confidence:** High
- **Found by:** Security specialist; verified by the coordinator (both call sites read directly)

### [C2] The R418/R419 audit's statistics silently degraded, flipping a published reading
- **File:** `docs/measurements/r418/kg_lever_ans_strict_repro.py:118` (`_fisher_p`), `:339` (the paired block), `:360` (`call`)
- **Bug:** Three lazy `scipy.stats` imports. scipy is **not** a declared dependency (`requirements.txt:67` names it only inside a transitive-note comment) and no CI job installs it, so in this repo's own environment: `_fisher_p` fell through its `except` and returned `1.0` for *every* table — a perfect 10/10 vs 0/10 separation reported as "no separation" with a printed `p=1.000`; and the paired block produced `sign_p = wilcoxon_p = None`, which the `call` ternary (`if sign_p is not None and sign_p > 0.05`) read as **"cost supported by the paired test"** with no test performed. Re-running the driver therefore contradicted the committed artifact, which records `p=0.69` / `0.2304` / "cost NOT supported".
- **Impact:** A measurement instrument whose verdict depends on an undeclared dependency. This was not hypothetical: the full suite had exactly one red test (`test_fisher_bar_separates_a_tie_from_a_separation`) and a driver re-run printed the opposite conciseness call to the artifact it was supposed to reproduce.
- **Suggested fix:** Exact, scipy-free implementations that **reproduce the committed values**: `_fisher_p` as a `math.comb` hypergeometric tail; `_sign_test_p(longer, shorter)` exact two-sided binomial (14/11 → 0.69); `_wilcoxon_p(diffs)` exact subset-sum DP over doubled average ranks (the 25 signed diffs → 0.2304; the normal approximation gives 0.226, so the exact route is the one kept). `call` now treats an uncomputed p as *not established*, never as support. A re-run is structurally **byte-identical** to the committed JSON.
- **Confidence:** High
- **Found by:** Coordinator (from the sole failing test; then generalised to the same family at `:339`)

### [C3] `OPENAI_TIMEOUT_SECONDS` was missing from the engine cache key (invariant #4)
- **File:** `app/routes/regenold.py:1583` (`_engine_cache_key`)
- **Bug:** `REGENOLD_STAGE2_WRAPPER_TIMEOUT_S` was keyed, but the resolved deadline is `_stage2_wrapper_timeout_s()`, which **falls through to `OPENAI_TIMEOUT_SECONDS`** when the dedicated knob is unset — and unset is the shipped default. Only half the deadline was in the key.
- **Impact:** A read timeout is read as a leg *failure*, so flipping it changes which leg serves the answer — i.e. it changes `GraphRAGResponse.answer`, the object `_ENGINE_CACHE` stores. An unkeyed flip replays arm A's cached answer and measures "the deadline does not matter" (R263.2 / R288.1 doctrine). `tests/test_r355_cache_key_complete.py` is the AST gate that is supposed to catch this class; it watched the literal name, not the fall-through.
- **Suggested fix:** Registered the name in the key list with the fall-through reasoning recorded inline.
- **Confidence:** High
- **Found by:** Concurrency/state specialist (cache identity scope); verified by the coordinator

## Important Issues

### [I1] A completed Stage-2 call could still die on its own telemetry
- **File:** `app/llm/openai_wrapper_provider.py:902`, `:960`, `:978`
- **Bug:** `msg = choice["message"]; text = msg.get("content") or ""` — a facade sending `null` or a bare string raised `AttributeError`, which the decode guard's `except (KeyError, IndexError, TypeError, ValueError)` did **not** list. `usage = payload.get("usage") or {}` covered a missing key and a null, not a non-dict truthy value (`[]`, `"n/a"` → `.get` on a list). `int(usage.get("prompt_tokens") or 0)` raised `ValueError` on `"n/a"` **outside** the guarding try.
- **Impact:** `complete()`'s contract is "return an error string, never raise". Each of these turned a fail-soft Stage-2 miss into an exception over a telemetry field nothing downstream reads — the exact shape R360.12 fixed one layer in.
- **Suggested fix:** `isinstance(msg, dict)` check with a descriptive `TypeError` (inside the guard, now including `AttributeError`); content-parts list joined; non-str content/thinking coerced to `""`; `usage` type-checked; new `_token_count()` helper returning a non-negative int for anything.
- **Confidence:** High
- **Found by:** Error-handling specialist; verified by the coordinator

### [I2] `/healthz/llm` could be handed an infinite deadline, and a falsy-looking flag kept the billable probe ON
- **File:** `app/main.py:1370` (timeout), `:1423` (anthropic probe)
- **Bug:** `float()` accepts `"inf"`, `"-inf"`, `"nan"` and only `ValueError` was caught — `=inf` gave the probe an infinite deadline (the R461 wall-clock guard can never fire), `=nan` disarmed the guard, and `0`/`-1` made every probe read as a network error. Separately `REGENOLD_HEALTHZ_PROBE_ANTHROPIC` was compared to the literal `"0"`, so `"false"`, `"no"`, `"off"` left the **live, billable** network probe ON while the operator believed it was off.
- **Impact:** A health endpoint that can hang a worker; and a cost/latency knob that silently does the opposite of what it says.
- **Suggested fix:** `math.isfinite(probe_timeout) and probe_timeout > 0` or fall back to the documented 30 s; new `_HEALTHZ_FALSY` set (the inverse of the existing `_HEALTHZ_TRUTHY`) with a lowered, stripped comparison.
- **Confidence:** High
- **Found by:** Error-handling specialist (timeout), Concurrency specialist (probe flag)

### [I3] `content_hash` had two producers, two widths, and could not verify its own record
- **File:** `app/data/ontology_evidence.py:49` (new `content_hash_for`), `app/data/ontology_browse.py:608`, `app/data/ontology_ledger.py:1063`
- **Bug:** The browse adapter emitted 64 hex characters and the phase-3 ledger 16; **both hashed the untruncated text while storing only a prefix of it**. So the hash did not cover the bytes in the record, and the two producers were neither comparable nor joinable. Nothing caught it: the only assertion anywhere pinned one producer's width (`len(item.content_hash) == 64`) and never related hash to quote.
- **Impact:** An integrity field that cannot be checked — worse than absent, because consumers may trust it.
- **Suggested fix:** One shared `content_hash_for(quote, *, cap)` returning `(stored, digest)` over exactly the stored bytes; both producers call it (the ledger keeps its 400-char cap; the fix is the coverage, not uniform truncation).
- **Confidence:** High
- **Found by:** Logic/correctness (ontology) specialist; verified by the coordinator

### [I4] Two existence gates were dead because they tested wire form against an internal-form key space
- **File:** `app/data/ontology_browse.py:146` (`anchor_exists`), `app/data/ontology_ledger.py:1030` (`fabricated_targets`)
- **Bug:** `candidate = "Article 26"` (wire form) tested against `ARTICLE_EXISTENCE`, which is keyed `"Art. 26"` — `False` for every input. Same in the ledger's `known = (...)` disjunction. The documented "tolerating the short form" tolerance in `anchor_exists` never existed, and in `fabricated_targets` the article leg was vacuous — only `coordinate_exists` was doing any work.
- **Impact:** Both gates still returned the right answer *today* (the other legs cover it), so nothing was failing; but a future narrowing of the covering leg would silently turn the existence gate off instead of failing loudly. This is a latent-failure defect, not a live miss.
- **Suggested fix:** Convert with `to_internal()` first, following the precedent in `provision_coordinates._head_of`.
- **Confidence:** High
- **Found by:** Logic/correctness (ontology) specialist; verified by the coordinator

### [I5] `resolve_concept`'s shadow trace under-counted exactly the lookups that miss
- **File:** `app/data/ontology_browse.py:664`
- **Bug:** Five of the function's seven exits returned *before* the `calls` / `elapsed_ms` bookkeeping; only the malformed-id branch and the success path counted.
- **Impact:** `ShadowTrace` is an adapter-cost instrument. A manifest that resolves nothing looked **cheaper** than one that resolves everything — the wrong direction for a cost reading, and invisible because the number is plausible.
- **Suggested fix:** A local `_miss()` helper that records the call, then reports the miss; all five early exits route through it.
- **Confidence:** High
- **Found by:** Concurrency/state specialist (shared mutable state); verified by the coordinator

### [I6] The evidence-bundle census counted headers, not the lines the lever drops
- **File:** `app/engines/evidence_bundle.py:239`, `:312`
- **Bug:** `stats()` reported `non_engaged_blocks`, which counts **headers** (a different predicate), so a census row could report 12 blocks and have removed zero characters. The coupling between "header found" and "member dropped" is a hard-coded four-space indent test and is silent.
- **Impact:** A gate could not tell "the lever fired" from "the lever is a no-op on this producer", which is precisely the evidence it needs.
- **Suggested fix:** Report `non_engaged_member_lines = len(_non_engaged_member_lines(...))` beside the header count, so a header count with a zero drop is visible. **Not** taken: widening the indent test to any indentation — `tests/test_r460_evidence_bundle.py:330` pins that the two-space `VERBATIM (question-relevant)` line in the same region is not a member, and the widening measurably deleted verbatim prompt content. The existing pin caught this on the round's first cut; the four-space test stays and now says so.
- **Confidence:** High
- **Found by:** Logic/correctness (engines) specialist; the "widen it" remedy was falsified during verification

### [I7] Three tests that could not fail
- **File:** `tests/test_r460_length_control.py:68`, `:150`; `tests/test_official_judge_model_compatibility.py`
- **Bug:** (a) `assert capped["question"] if "question" in capped else True` — the rows literal has only `id`/`answer`/`reference_answer`, so it is `assert True`; the real invariant (`_length_controlled_rows` preserves unknown keys) was never exercised. (b) The flag "wiring" test scanned `inspect.getsource(score_arm)` for a literal — that proves the text exists, not that the flag reaches the payload. (c) The parametrized rejection test let `configure_judge` write `R388_JUDGE_PROVIDER` / `R388_JUDGE_MODEL` into `os.environ` before raising, leaking the rejected `claude-sonnet-5-5` and a non-wrapper provider to every later module.
- **Impact:** (a) and (b) are false confidence on exactly the levers this branch ships; (c) is cross-test contamination that depends on file order.
- **Suggested fix:** (a) carry `"question"` in a row and assert it survives; (b) drive `score_arm.main()` twice over one checkpoint with only `_call_json` faked and assert on the written payload (flag off → `length_controlled is None`; on → `cached is False`, `n == 2`, `answers_cut == 1`, the four axis keys); (c) `monkeypatch.delenv(..., raising=False)` both names before the call so teardown restores the pre-call environment.
- **Confidence:** High
- **Found by:** Test-fidelity specialist; verified by the coordinator

## Suggestions

- `evals/harness/frontier_baseline.py` still carries **six pre-existing** ruff findings (E702 ×4, F841, E741) that were copied from `evals/official/judge.py`; left as-is so the fix stays a one-concern diff. Worth a separate cleanup of both files.
- `docs/measurements/r386/mingold.py` attaches the same `CF_ACCESS_*` pair, but to a hardcoded module-constant URL, so it is not env-addressable; deliberately left alone.
- Pre-existing lint at HEAD, untouched: `app/main.py` (W293, I001), `app/routes/regenold.py` (UP037).
- The `apply_r036_gold_correction.py` fix writes through `os.replace` on a `.jsonl.tmp` sibling; the gold row is already `_revised: "R448"`, so a run today is a no-op — verify with `git diff --stat docs/measurements/r388/official_gold_n110.jsonl` rather than reading the script's exit code.

## Plan Alignment

- **Implemented:** the branch's own plan (R444–R462 rounds: ontology ledger/browse, evidence bundle, Stage-2 wrapper deadline, wire probe, CF Access naming) is what the diff carries; R463 adds no new lever, only corrections to it.
- **Not yet implemented (neutral):** the R463 findings are fixed in the working tree, not yet committed/deployed at review time.
- **Deviations:** `docs/measurements/r418/kg_lever_ans_strict_repro.py` and `tests/test_r419_ans_strict_repro.py` are outside the branch diff's file list — they were reached from the failing test, which is the correct direction (a red test on the branch is a branch defect regardless of which commit introduced it).

## Review Metadata

- **Agents dispatched:** 7 specialists in parallel — (1) logic/correctness, ontology+data; (2) logic/correctness, engines+routes; (3) error handling & edge cases (external-string parsing); (4) contracts, integration & logic duplication; (5) concurrency, state & caches; (6) test fidelity; (7) security & secrets.
- **Scope:** the 43-file branch diff vs `main` (sliced per specialist) plus their adjacent tests; coordinator re-read `app/routes/regenold.py`, `app/engines/_graph_rag_impl.py`, `app/llm/openai_wrapper_provider.py`, `app/main.py`, `app/data/ontology_*`, `evals/**` and the r418/r419 measurement pair.
- **Raw findings:** seven reports, triaged in Phase 3; the two loudest (the zero-evidence `llm_ok` pass and the `CF_ACCESS_HOSTNAME` pin) were **read as deliberate, test-pinned designs** and reported rather than changed.
- **Verified findings:** 9 fixed (C1–C3, I1–I7), each with a test that fails on the pre-R463 code.
- **Filtered out:** the remainder — style/quality nits, plus findings that the code contradicted.
- **Steering files consulted:** `AGENTS.md`, `CLAUDE.md`, `CR-SKILL.md`, `docs/ROUNDS.md` (closed directions: global top-K clamps, neural NLI, graph-primary retrieval).
- **Plan/design docs consulted:** `docs/measurements/r448/*`, `docs/measurements/r461/*`, `docs/reviews/r428-cr-dispositions.md` (prior CR round format).
