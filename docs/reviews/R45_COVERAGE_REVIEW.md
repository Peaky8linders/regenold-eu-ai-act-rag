# R45 Coverage + Data-Integrity Review

**Scope**: C.1 coverage gaps, C.2 edge cases, C.3 data integrity, C.4 multi-turn correctness, C.5 wire-contract round-trip.
**Tools**: `pytest --cov=app` (coverage 7.14 + pytest-cov 7.1), direct TestClient probes, ripgrep across `app/`.
**Test base**: 1527 tests pass in 73.6s. Overall app coverage = **81%** (7131 statements, 1364 missing).
**No source files were modified.**

## Coverage summary — bottom of the table (>= 10 LOC)

| Module                                          | LOC | Coverage | Notes                                                                    |
| ----------------------------------------------- | --- | -------- | ------------------------------------------------------------------------ |
| `app/graph/reasoning.py`                        | 93  | **0%**   | Multi-hop reasoning engine — completely untested.                        |
| `app/data/agentic_taxonomy.py`                  | 84  | **0%**   | R41 surface (compound risks, threat categories, archetypes) — no tests. |
| `app/data/ontology_mapping_full.py`             | 24  | **0%**   | CodexAI port (R21) — not exercised in any test path.                     |
| `app/data/severity.py`                          | 15  | **0%**   | Severity-band registry — unused by any test.                             |
| `app/engines/vector_rerank.py`                  | 120 | 29%      | Turbovec rerank — env-gated, no test path enables it.                    |
| `app/graph/client.py`                           | 153 | 30%      | Neo4j driver — only the disabled-path is exercised.                      |
| `app/data/kb.py`                                | 43  | 56%      | Most stubs unreached by tests (string-keyed lookups).                    |
| `app/evidence/store.py`                         | 335 | 60%      | Postgres + SQLite backends largely untested (lines 545-658).             |
| `app/data/role_obligations.py`                  | 73  | 62%      | `compute_applicable_roles`, `filter_articles_for_role` untouched (501-541). |
| `app/engines/path_rag.py`                       | 65  | 71%      | Lines 111-129 (whole branch) untested.                                   |
| `app/engines/graph_rag.py` (the engine)         | 649 | **74%**  | 168 missing lines — most are LLM-provider branches.                      |
| `app/engines/cross_encoder_rerank.py`           | 265 | 75%      | Strategy-B ONNX rerank (657-755) entirely untested (no asset bundled).   |
| `app/main.py`                                   | 356 | 76%      | Auto-seed Neo4j hook (241-299), advisory-lock path untested.             |
| `app/routes/regenold.py` (the wire)             | 541 | **81%**  | `REGENOLD_EXTRACT_EMBEDDINGS=1` branch (517-550) + trust-proxy (301-308) untested. |
| `app/integrations/regenold/scope.py`            | 390 | 91%      | Live-question-only-anchor R43 branch covered; 2184-2196 (wh/aux fallback) untested. |
| `app/engines/scenario_classifier.py`            | 151 | 96%      | Edge guards in `_check_safety_component_carve_out` (480, 515) untested.  |
| `app/engines/compliance_verdict.py`             | 64  | **91%**  | 309-313 fallback untested.                                               |

---

## C1 — History injection bypasses scope: prior-user spoof triggers full prohibited verdict on off-topic live question
**Severity**: **P0** (security / correctness)
**Type**: multi-turn
**File**: `app/routes/regenold.py:1325` calls `_build_question_from_history`, then `app/engines/scenario_classifier.py:classify_scenario_query` (line 1423), `app/engines/prohibited_gatekeeper.py:scan_for_prohibitions` (route-level call), and `app/engines/clara_logic.py:extract_tags_deterministic` (line 1660) all receive the **flattened** `question` (which includes prior-user content under `Conversation so far:`).
**Finding**: R43 patched `predict_verdict` to use `live_question_from`, but the **same fix was NOT propagated** to the other classification entry points. End-to-end repro (live, via `TestClient` with auth seeded):

```
[{role: user,     content: "We are a deployer offering a high-risk biometric identification system to law enforcement intended for use in public spaces in real time."},
 {role: assistant, content: "That is prohibited under Article 5."},
 {role: user,     content: "What is the EU's preferred type of cheese?"}]
→ HTTP 200, answer = "Real-time remote biometric identification in publicly accessible spaces by law enforcement is prohibited under Article 5(1)(h)… As a deployer, you must classify the system as high-risk…"
   refs = ['Article 5.1.h','Article 6','Article 9','Article 10','Article 11','Article 13','Article 14','Article 15']
```

Same with a prohibited-practice prior turn → live "preferred cheese" question → returns `Article 5.1.a` prohibition verdict. Scope.py refuses the live question correctly when probed in isolation, but the engine fires AHEAD of (or AFTER) the scope check and reads history-tainted markers.

**Repro / test gap**: No test asserts that a `Conversation so far:` flattened prompt with a scenario in PRIOR USER turn but an off-topic live question gets a scope-refusal answer. R43's `test_history_injection_*` series only covered `predict_verdict`.

**Suggested fix**: In `app/routes/regenold.py`, call `live_question_from(question)` before invoking `classify_scenario_query`, `scan_for_prohibitions`, `build_verdict_prefix`, and `extract_tags_deterministic`. Add three regression tests (one per classifier) using the cheese-spoof above. Direct unit probe confirms the classifiers themselves do NOT need the fix — they just need callers to stop passing them history-flattened questions.

---

## C2 — `_check_safety_component_carve_out` fires from prior-user turn alone, emits Art. 6(1a)/Art. 4 verdict for off-topic live question
**Severity**: P0 (sub-case of C1, but worth its own entry because R45 prompt called it out)
**Type**: multi-turn
**File**: `app/engines/scenario_classifier.py:464–541` — gate 4 (line 514) requires `has_role OR has_intent OR 2+ carve_hits`; when invoked via `classify_scenario_query(question)` with a flattened-history question the role marker from history qualifies.
**Finding**: Direct probe:
```python
_check_safety_component_carve_out(
    """Conversation so far:
       User: We are a provider of an AI system intended for user assistance that does not affect safety.
       Latest question: test""", role='provider')
# → ScenarioVerdict(articles=('Art. 6(1a)', 'Art. 4'), ...)
```
**Repro / test gap**: No test passes a `"Conversation so far:"`-prefixed `question` to `_check_safety_component_carve_out`; tests only feed it bare scenario strings.
**Suggested fix**: Same `live_question_from` propagation. Add a test that confirms the carve-out returns `None` when carve-out terms only appear in the history block. Honour R43's principle: classification reads ONLY the live turn.

---

## C3 — `Annex XIV` (R41 Agentic AI surface) is unreachable end-to-end
**Severity**: P0 (data integrity)
**Type**: data-integrity / wire-contract
**File**: `app/integrations/regenold/scope.py:2007-2020` (refusal copy says "13 annexes (Annex I-XIII)") + scope's internal valid-Annex set vs `app/data/article_existence.py` (which DOES include `Annex XIV`).
**Finding**: Three contradictions across the codebase regarding R41's added Annex XIV:
1. `ARTICLE_EXISTENCE` contains `Annex XIV` — passes lint.
2. `ARTICLE_FULL_TEXT` (eu_ai_act_corpus.py) does NOT — no corpus prose.
3. `scope.classify_conversation()` returns `ScopeVerdict(in_scope=False, reason=NON_EXISTENT_ARTICLE)` for any question mentioning Annex XIV.
4. `app/integrations/regenold/scope.py:2019` emits the user-facing copy "The regulation has 113 numbered articles and 13 annexes (Annex I-XIII)".
5. `app/data/graph_rag_prompts.py:56` hardcodes the same "13 annexes (Annex I-XIII)" rule into the LLM system prompt.
6. `app/data/agentic_taxonomy.py::compound_risks_for_article("Annex XIV")` returns `[]` even though Round 41 was meant to link Agentic AI to Annex XIV.
End-to-end: question "What does Annex XIV cover?" returns the misleading refusal copy and empty refs.

**Repro / test gap**: No test asserts that `Annex XIV in ARTICLE_EXISTENCE` ⇔ `scope.classify_conversation(<q with Annex XIV>).in_scope == True`. The R41 mapping `is_agentic_ai_designation("AIH 0401") == True` but `is_agentic_ai_designation("agentic ai") == False`, `is_agentic_ai_designation("Annex XIV") == False` — no NL surface.

**Suggested fix**: Either (a) DROP `Annex XIV` from `ARTICLE_EXISTENCE` until upstream Digital Omnibus content lands, OR (b) wire it: add corpus prose, add to scope's valid-Annex set, update the user-facing copy and LLM prompt to "13–14 annexes" or fact-driven `len(ANNEX_LIST)`, and populate `compound_risks_for_article("Annex XIV")`. Lint test: `set(ARTICLE_EXISTENCE) & {Annex XIV, Annex XV, ...}` must round-trip through `scope.classify_conversation` as in-scope.

---

## C4 — `is_agentic_ai_designation` is regex-strict on `"AIH 0401"` — natural-language phrase "agentic AI" returns False
**Severity**: P1
**Type**: data-integrity / coverage-gap
**File**: `app/data/agentic_taxonomy.py:is_agentic_ai_designation` (module is 0% covered).
**Finding**:
```python
is_agentic_ai_designation('AIH 0401')   # True
is_agentic_ai_designation('agentic ai') # False
is_agentic_ai_designation('Annex XIV')  # False
```
The function only matches the exact `AIH 0401` code — every actual partner query will use natural English. Combined with C3 this makes the entire R41 agentic surface invisible to users.
**Repro / test gap**: 0% coverage on this module; no test invokes the natural-language alias paths.
**Suggested fix**: Broaden the matcher to recognise `agentic ai`, `agentic system`, `annex xiv`, `aih 0401`, and `aih-0401`. Add one test in `tests/test_agentic_taxonomy.py` (new file) covering all five forms plus a negative ("agent-based" — must still return False because it's not the taxonomy term).

---

## C5 — `whitespace-only` and `empty` content produce HTTP 422 "Each message content is limited to 4000 characters"
**Severity**: P2 (UX)
**Type**: edge-case
**File**: `app/integrations/regenold/models.py:RegenoldChatMessage` validator surfaced by `RegenoldAskRequest.model_validate` in `app/routes/regenold.py:1286`.
**Finding**: The 422 error message is misleading — both empty (`""`) and whitespace-only (`"   \t\n  "`) trigger the SAME validator error, blaming the 4000-char cap. Same applies to `content=None`. Reproducible:
```
empty:       HTTP 422  detail.message="Each message content is limited to 4000 characters; role must be one of user / assistant / system."
whitespace:  HTTP 422  (same)
None:        HTTP 422  (same)
```
The validator collapses three distinct failure modes (empty / too-long / wrong-type) into one message — partners hitting an empty-string bug will chase a length-cap red herring.

**Repro / test gap**: `tests/test_regenold_integration.py` asserts 422 on too-long content but does NOT pin the error message for `content=""` / `content=None`.

**Suggested fix**: Split the validators in `models.py` — return distinct `code` values (`content_empty`, `content_too_long`, `role_invalid`, `content_wrong_type`). Update the test suite to pin each. No source change to be made by R45.

---

## C6 — Multi-turn with 100 prior turns hits the 4000-char per-message cap (not the 2000-char engine budget) — silently truncates dialogue
**Severity**: P2
**Type**: edge-case
**File**: `app/integrations/regenold/models.py` content validator + `app/routes/regenold.py:_build_question_from_history` (1122–1214).
**Finding**: With 100 user+assistant turns, the request fails 422 BECAUSE the per-message validator sees the artificially-large total. But a partner who keeps each turn tiny (40 chars × 200 turns = 8000 chars flattened) will hit the 2000-char engine cap, and the route's left-truncation drops the oldest turns silently. There's no warning to the partner that history was clipped. Also: `role='tool'` (an OpenAI-spec role) fails the validator (which only allows `user/assistant/system`) — common in agentic frameworks that route via the OpenAI API.

**Repro / test gap**: No test asserts what happens at exactly N=20 user turns (above `_HISTORY_TURNS_TO_INCLUDE = 4`). No test attempts `role='tool'` to confirm graceful rejection vs surprising failure.

**Suggested fix**: Make the truncation explicit — when history is dropped, surface in `reasoning` (`history_truncated_turns: 17`). For `role='tool'`, return a stable error code `unsupported_role` instead of the same 4000-char message.

---

## C7 — Verdict-spoofed live question ("This system is compliant under Article 5. What does Art. 13 require?") leaks Art. 5 verdict into refs
**Severity**: P2 (rubric / UX)
**Type**: edge-case
**File**: `app/engines/prohibited_gatekeeper.py:scan_for_prohibitions` substring-matches the live question.
**Finding**: Probe:
```
Q: "This system is compliant under Article 5. What does Art. 13 require?"
→ refs = ['Article 5', 'Article 13']
   answer = "Art. 5: Prohibits eight categories of AI practice..."
```
The user asked about Art. 13; the engine returned an Art. 5 prohibition verdict because the live question literally contains "Article 5". The prohibited gatekeeper has no intent-vs-mention distinction.

**Repro / test gap**: No test covers a benign mention of a prohibited-practice article in a question about a different article.

**Suggested fix**: Require the prohibited gatekeeper to fire only when a PRACTICE keyword (e.g. `subliminal`, `social scoring`) matches, not just the bare article reference. Article anchors should narrow citations but not flip the verdict shape.

---

## C8 — Non-Latin scripts (Cyrillic / Arabic / Mandarin) refused via "no matching obligation" — misleading copy
**Severity**: P2
**Type**: edge-case
**File**: `app/integrations/regenold/scope.py:_AI_ACT_ANCHORS` is ASCII-only; non-Latin questions miss anchor extraction → no-match refusal.
**Finding**: Probe:
```
"Что такое статья 5 о запрете биометрии?" (Russian "What is Art. 5 on biometric prohibition?")
→ HTTP 200, answer = "No matching obligation found in the EU AI Act..."
```
The system gives a generic in-domain refusal instead of either translating, or stating language-not-supported. Partner adoption in multilingual EU markets will hit this on first try.

**Repro / test gap**: 0 tests for non-Latin input. Zero-width-space input (`​`) gets the scope-refusal copy instead of the in-scope path (R43 patched KB content but not input boundary).

**Suggested fix**: Either (a) normalise non-ASCII to NFKC + strip zero-width characters at the input boundary in `_build_question_from_history`; or (b) return a stable `code: language_not_supported` refusal pointing to the English Q&A surface. Add probes for ru/ar/zh and `​`.

---

## C9 — KB stubs reference sub-paragraphs that aren't in the corpus
**Severity**: P3
**Type**: data-integrity
**File**: `app/data/kb.py` (139 keys) vs `app/data/eu_ai_act_corpus.py::ARTICLE_FULL_TEXT` (133 keys).
**Finding**: 6 KB stub keys have NO corpus prose:
```
['Annex XIV', 'Art. 50.1', 'Art. 50.2', 'Art. 50.3', 'Art. 50.4', 'Art. 6.3']
```
These are sub-paragraph anchors. The KB carries a tight summary, but the long-form EUR-Lex prose for the parent article is the only fallback — `select_answer_sentence("Art. 50.1")` finds nothing because the corpus is keyed per article, not per sub-paragraph.
**Repro / test gap**: `tests/test_kb_consistency.py` checks KB → `ARTICLE_EXISTENCE` resolution but does NOT check KB → corpus resolution. The 6 sub-paragraph keys pass the existing lint.
**Suggested fix**: Add a new lint test `test_kb_subparagraphs_have_parent_corpus()`: for each KB key matching `Art. N.M`, assert `Art. N` is in `ARTICLE_FULL_TEXT` (parent prose exists). Optionally route sub-paragraph extractive-QA via the parent prose with a sub-point hint.

---

## C10 — Agentic taxonomy `article_refs` contain `Art. 25(4)`, `Art. 51(2)`, `Art. 3(23)` — parenthesized form
**Severity**: P3 (latent)
**Type**: wire-contract / data-integrity
**File**: `app/data/agentic_taxonomy.py:COMPOUND_RISK_TYPES[*].article_refs`.
**Finding**: Inspected:
```
COMPOUND_RISK_TYPES[*].article_refs ∋ {'Art. 25(4)', 'Art. 51(2)', 'Art. 15(4)', 'Art. 3(23)', ...}
```
The wire regex `^Article \d{1,3}[a-z]?(?:\.[A-Za-z0-9]+)*$` REJECTS the parenthesized form. If any code path surfaces these refs unmodified, the wire will either drop them or 500. R34 already noted that `_check_safety_component_carve_out` emits `Art. 6(1a)` — and the route does convert that one — but the taxonomy refs go through no such conversion because the taxonomy module is 0% covered: there's no path from a live question to these refs, but the next round that wires it in WILL break the wire unless the conversion is applied.
**Repro / test gap**: No test asserts that every `article_ref` in `agentic_taxonomy.COMPOUND_RISK_TYPES`, `agentic_taxonomy.AGENT_ARCHETYPES`, etc. round-trips through the wire regex (after normalisation).
**Suggested fix**: Either (a) normalise the taxonomy data to dot-notation at module-load time, OR (b) add a parametric test `test_taxonomy_refs_round_trip()` that runs every ref through whatever converter exists in `models.py` and asserts the result matches `_ARTICLE_OUTPUT_RE`/`_ANNEX_OUTPUT_RE`.

---

## C11 — `app/graph/reasoning.py` (93 LOC) and `app/data/severity.py` (15 LOC) are 0% covered
**Severity**: P2
**Type**: coverage-gap
**File**: as above.
**Finding**: `app/graph/reasoning.py` contains multi-hop reasoning over the audit graph (per CLAUDE.md R35 — "audit forensics, multi-hop reasoning, cross-framework mapping potential"). Zero tests exercise it. If a deploy enables Neo4j and an auditor invokes a Question→Obligation→RoadmapTask traversal, behaviour is unverified. Similarly `severity.py` — 15 statements, completely orphaned. Either it's dead code (Review B's domain) OR it has invisible regressions waiting.
**Repro / test gap**: No tests reference these modules.
**Suggested fix**: Either remove (Review B can decide) or add at least one structural test per public function. The 0%/15-LOC severity module is a particularly cheap thing to either delete or cover.

---

## C12 — `REGENOLD_TRUST_PROXY=true` path (regenold.py:301-308) untested
**Severity**: P2 (security)
**Type**: coverage-gap
**File**: `app/routes/regenold.py:_client_addr` lines 301-308.
**Finding**: When `REGENOLD_TRUST_PROXY=true`, the route reads the leftmost hop of `X-Forwarded-For` as the source IP for rate-limit bucketing. The docstring warns "the deploy operator is on the hook for ensuring the proxy actually overwrites (not appends), otherwise an attacker can spoof their address" — but the branch itself is untested. A malformed `XFF` header (empty after split, e.g. `","` or `"   "`) would fall through to `get_remote_address` (line 308) — but a single-segment `XFF` like `"127.0.0.1"` would return as-is, with no validation that it's a real IP. An attacker behind a CDN that DOES append-not-overwrite gets the original-client IP slot for the anonymous rate-limit bucket → spoofable bypass of the 30/min cap.
**Repro / test gap**: No test sets `REGENOLD_TRUST_PROXY=true` and exercises XFF parsing.
**Suggested fix**: Add tests for (a) trust-proxy disabled + XFF present → ignored; (b) trust-proxy enabled + XFF present → first hop used; (c) trust-proxy enabled + XFF empty → falls back to `get_remote_address`; (d) trust-proxy enabled + XFF malformed (`",,"`, `"127.0.0.1, 10.0.0.1"`, `"not-an-ip"`) → predictable behaviour. Production deploys with `REGENOLD_TRUST_PROXY=true` enabled today have an untested IP-extraction path.

---

## C13 — `app/engines/vector_rerank.py` (120 LOC) 29% covered — main rerank/passthrough branch (lines 122-225) untested
**Severity**: P3
**Type**: coverage-gap
**File**: `app/engines/vector_rerank.py`.
**Finding**: The Linux-only turbovec asset path is in production toggled by `REGENOLD_VECTOR_RERANK=1`. The branch is opt-in and Linux-only, so CI (Windows) skips it — but there's no smoke test against a mocked-asset stub either, so if asset paths change or the API drifts, no test catches it.
**Repro / test gap**: No test mocks `turbovec` or the asset directory.
**Suggested fix**: Add a mock-asset test that injects fake artefacts into `app/engines/_assets/` and asserts the rerank passthrough vs scoring branch fires on the env-var toggle. Even just a "module imports without raising" smoke test would lift coverage above 50%.

---

## Coverage rollup of critical modules

| Module                              | % covered | Concerning untested |
| ----------------------------------- | --------- | ------------------- |
| `routes/regenold.py`                | 81%       | 301-308 (trust-proxy), 517-550 (REGENOLD_EXTRACT_EMBEDDINGS), 1660-1738 (CLARA hook), 1786-1789 (citation guard wire-up) |
| `integrations/regenold/scope.py`    | 91%       | 1542-1545 (annex-num-out-of-range), 2184-2196 (wh-/aux- fallback), 2305-2308 (governance refusal copy) |
| `engines/compliance_verdict.py`     | 91%       | 309-313 (predict_verdict fallback when no markers fire) |
| `engines/scenario_classifier.py`    | 96%       | 480 (empty question), 515 (gate-4 failure), 583/566 (LLM-extension stubs) |
| `engines/graph_rag.py` (the engine) | 74%       | 168 missing — most in the openai_wrapper/anthropic provider branches |
| `data/kb_search.py`                 | 82%       | 666-712 (xref boost, additive dense paths) |

The lower-tier modules (kb_search.py at 82%, graph_rag.py at 74%) carry the latency-critical retrieval logic — every uncovered branch is a latent rubric-regression risk.

---

## Summary

13 findings, severity-ranked: **2× P0 (history injection across 4 classifiers, Annex XIV data-integrity contradiction)**, 1× P0/P1 boundary (carve-out variant of C1), 4× P2 (UX / coverage / security), 6× P3 (latent / lint).

**Action prioritisation** (read: which 3 to fix first):
1. **C1+C2** — propagate `live_question_from` from R43 to `classify_scenario_query`, `scan_for_prohibitions`, `extract_tags_deterministic`, `_check_safety_component_carve_out`. Single-line change at the 4 call sites, ~150 LOC of regression tests.
2. **C3+C4** — pick a side on Annex XIV. Either drop from `ARTICLE_EXISTENCE` (and remove `AIH 0401` from agentic taxonomy) or wire it (corpus prose, scope's valid set, user-facing copy, NL alias matcher). Today the surface is internally inconsistent.
3. **C12** — `REGENOLD_TRUST_PROXY` untested with a security-sensitive header parser. 30 min of tests.

The remaining 10 findings are coverage-debt / rubric-neutral data-integrity tightening — schedule for Round 46.
