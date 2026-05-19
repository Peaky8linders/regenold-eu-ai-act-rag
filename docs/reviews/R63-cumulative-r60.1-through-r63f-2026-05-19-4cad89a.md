# Deep Code Review: cumulative R60.1 / R61 / R62 / R63-C / R63-E / R63-F

**Date:** 2026-05-19
**Branch:** `claude/r64-deep-review-fixes` → `main`
**Base commit:** `4cad89a` (round 63-F: filter Neo4j UNRECOGNIZED-label warnings)
**Cumulative diff:** [`43f4afa..4cad89a`](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/compare/43f4afa...4cad89a) — PRs [#85](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/85) + [#86](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/86) + [#87](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/87)
**Files changed:** 17 (10 production + 7 tests) | **Lines changed:** +1,957 / −32
**Diff size category:** Large

## Executive Summary

The cumulative R60.1–R63-F work introduced one **Critical** correctness bug — `_KBEntry.select_best_stub` (R63-C) tokenises the full flattened multi-turn prompt instead of the live turn, so prior-turn vocabulary contaminates stub selection on every multi-turn Art. 5/50/53/56 question. The same R63-C selection is also asymmetric: it's wired into the direct-entity branch of `_retrieve_from_kb` but the cross-reference expansion branch still uses the joined-summary fallback, silently negating the R63-C win whenever the gold answer is reached via xref. Five **Important** findings round out the report: over-broad specificity markers, one over-broad R62 refusal marker (false-positive consistency-guard drops on legitimate Sonnet polish), `db.labels()` probe duplication that already shows drift, an R63-F fallback that re-introduces the warning storm it was meant to fix, and a `tests/conftest.py` bare-except that swallows the R63-E import-rename failure mode silently. Security audit was clean. The Concurrency specialist flagged one cosmetic boot-log race (Suggestion). Recommendation: **fix-then-ship**.

## Critical Issues

### [C1] `_KBEntry.select_best_stub` ingests the full flattened multi-turn prompt

- **File:** `app/data/kb.py:466` (selector body), `app/engines/graph_rag.py:2479` (engine call-site), `app/routes/regenold.py:2267` (route call-site)
- **Bug:** Both callers pass the route's flattened multi-turn shape (`"Conversation so far:\n<history>\n\nLatest question:\n<live>"`). `select_best_stub` calls `_tokenize_for_stub_selection(question)` on the entire blob and then substring-scans `_SPECIFICITY_MARKERS` against it. Prior-turn tokens / specificity markers — `"open-weights"`, `"carve-out"`, `"watermark"`, `"training-data summary"`, etc. — that appeared **two turns ago** will boost stub selection for the **current** turn, even when the current turn is asking about a completely different facet of the article.
- **Impact:** Silent quality regression on every multi-turn question whose primary article is one of the 4 multi-stub entries (Art. 5 / 50 / 53 / 56). Directly subverts the R63-C "specificity from the live question" design and may explain why V2 r63f-live multi-turn coherence (0.56) underperforms the in-context potential the davidath baseline suggested R63-C could deliver.
- **Suggested fix:** Inside `select_best_stub`, slice `question` to the post-`"Latest question:\n"` tail via `rfind` — mirror the R60.1 pattern already used in [`app/engines/question_complexity.py::is_complex_question`](app/engines/question_complexity.py). When the marker is absent (single-turn question, no flatten preamble), fall through to the full string so single-turn behaviour is unchanged. Self-contained 5-line fix.
- **Confidence:** 95
- **Found by:** Logic & Correctness (85), Contract & Integration (75), Error Handling (75) — **3 specialists agreed**

## Important Issues

### [I1] xref-expansion branch in `_retrieve_from_kb` doesn't apply `select_best_stub`

- **File:** [`app/engines/graph_rag.py:2502-2509`](app/engines/graph_rag.py)
- **Bug:** R63-C wired stub selection into the direct-entity branch (line 2479) but the cross-reference expansion loop seven lines later still does `xref_mapping["summary"]` — the joined-summary fallback. So when a question pulls Art. 50 (2 stubs) or Art. 5 (6 stubs) or Art. 53 (3 stubs) or Art. 56 (multi-stub) **via xref**, the wrong (joined) stub is used.
- **Impact:** Silently negates the R63-C win on any multi-anchor question whose primary doesn't itself hit a multi-stub entry. Likely contributor to the V2 r63f-live rows where the gold is reached via xref.
- **Suggested fix:** Mirror the direct-entity isinstance branch at line ~2502: `text = xref_mapping.select_best_stub(query.raw_question or "") if isinstance(xref_mapping, _KBEntry) else xref_mapping["summary"]`. (Same `rfind` slice from C1 applies inside `select_best_stub`.)
- **Confidence:** 90
- **Found by:** Logic & Correctness (65), Contract & Integration (80)

### [I2] `_SPECIFICITY_MARKERS` contains generic English words that over-boost

- **File:** [`app/data/kb.py:574`](app/data/kb.py) — `"medical"`, `"safety"`; also line 557 `"template"`, 566 `"threshold"`, 547 `"exempt"`, 549 `"exception"`, 562 `"labelled"`, `"labelling"`, `"marking"`
- **Bug:** Bare single-word markers get a +5 boost. A question like *"Is medical-diagnosis AI a high-risk system?"* hits the `"medical"` marker and forces Art. 5's emotion-recognition medical-carve-out stub instead of the main risk-pyramid stub or the Art. 6 + Annex III chain the question is actually asking about.
- **Impact:** Wrong-stub selection on common phrasings. Compounds with C1 — together they make stub selection unreliable on the very surface R63-C was designed to fix.
- **Suggested fix:** Tighten to multi-word phrases — `"medical exemption"`, `"medical device exemption"`, `"safety component"`, `"compute threshold"`, `"training-data template"`, `"labelled as ai-generated"`, `"marking as ai-generated"`. Drop the bare forms.
- **Confidence:** 85
- **Found by:** Logic & Correctness (75), Error Handling (70)

### [I3] R62 refusal marker `"to give you a grounded answer"` is over-broad

- **File:** [`app/engines/graph_rag.py:2752`](app/engines/graph_rag.py) in `_STAGE2_REFUSAL_MARKERS`
- **Bug:** The substring also matches legitimate Sonnet introductions on perfectly valid in-scope answers (`"To give you a grounded answer, I'll cite Article 13 first..."`). When matched, the consistency guard drops the polish and substitutes the R49-A grounded prose (3-sentence, less rich).
- **Impact:** False-positive consistency-guard fires on valid polish — silently regresses Stage-2 quality on the same V2 multi-turn surface R62 lifted.
- **Suggested fix:** Require pairing with a refusal token in the same sentence (e.g. require `"to give you a grounded answer"` + `"please re-run"` or `"cannot"` or `"no matching"`); OR replace with the full R62 phrase `"to give you a grounded answer, please re-run"` that the original V2 Sonnet output emitted.
- **Confidence:** 75
- **Found by:** Error Handling (70), Contract & Integration (65)

### [I4] `tests/conftest.py` `try / except: pass` swallows reset-helper import failure

- **File:** [`tests/conftest.py:34-39`](tests/conftest.py)
- **Bug:** Bare `try/except: pass` around `from app.evidence.store import reset_evidence_store_for_tests`. If the function is renamed / removed / its module path changes, every test silently loses isolation and the R63-E flake (`test_authenticated_request_writes_partner_tenant_chain_entry` ↔ `test_consistency_guard.py`) returns invisibly.
- **Impact:** CI green lies. A future audit-chain refactor could silently restore the very flake R63-E was shipped to fix.
- **Suggested fix:** Log at WARNING level (one-shot via a module-level flag) on `ImportError`. Keep `pass` on generic `Exception` if the import succeeded but the fixture call raised (defensive). Or raise `pytest.UsageError` for loud failure at collection time.
- **Confidence:** 80
- **Found by:** Error Handling

### [I5] R63-F `db.labels()` probe duplicated across `main.py` + `graph/client.py`

- **File:** [`app/main.py:748-756`](app/main.py) vs [`app/graph/client.py:242-250`](app/graph/client.py)
- **Bug:** Exact 9-line block duplicated. Logger keys already diverge slightly (`healthz_graph_db_labels_failed` vs `graph_stats_db_labels_failed`). Future fixes to one site won't cover the other — exactly the drift this lens flags.
- **Impact:** Drift risk — the I6 fix below would need to be applied in two places.
- **Suggested fix:** Add `GraphClient.existing_labels(allowlist: frozenset[str]) -> set[str]` helper on the client. Both call-sites consume the helper.
- **Confidence:** 95
- **Found by:** Contract & Integration

### [I6] R63-F fallback to full allowlist re-introduces the UNRECOGNIZED warning storm

- **File:** [`app/main.py:756`](app/main.py), [`app/graph/client.py:250`](app/graph/client.py)
- **Bug:** When `db.labels()` itself raises (transient Neo4j hiccup, Community edition without the procedure), both R63-F sites fall back to `set(_STATS_LABELS)` — querying all 5 stale parent-CodexAI labels, restoring exactly the warning storm R63-F was shipped to fix.
- **Impact:** On any Neo4j hiccup, the very condition R63-F targeted silently returns. Operators don't notice unless they specifically grep for `01N50 UNRECOGNIZED` in the log line.
- **Suggested fix:** Fall back to a hardcoded known-populated subset — the labels the seeder always writes: `{"Article", "Annex", "Obligation", "Definition", "KBMetadata"}`. Document the choice inline so future schema additions can update the subset.
- **Confidence:** 75
- **Found by:** Error Handling

## Suggestions

- **F6** — `select_best_stub` tie-break is silently FIFO (`app/data/kb.py:496`). On a true tie, returns first index. Fix when fixing C1+I2 by falling back to joined summary on tie among marker-firing stubs. (60% confidence)
- **F7** — R62 scope anchors `"placed on the (eu|union) market"` + `"publicly accessible space(s)"` lack AI co-occurrence (`app/integrations/regenold/scope.py:1034-1038, 1049-1050`). Theoretical OOS leak; V2 21/21 doesn't probe these shapes. Harden when convenient. (60% confidence)
- **F12** — Boot-time `_gc.get_stats()` call races with auto-seed daemon thread (`app/main.py:130`). On cold deploy or stale-version drift, boot log emits `node_count=0` while seed populates ~505 nodes seconds later. Misleading operator log; no correctness consequence. Defer log to after seed thread joins, or prefix with `at_boot=true`. (80% confidence)

## Rejected (false positives)

- **F5** — `"please re-run the query"` marker variations (`"please rerun"` / `"please run again"`). R62 added the exact form Sonnet actually emitted on mt_v2_003; speculative variants risk I3-style over-broadening. Wait for a real V2 row.
- **F11** — Refusal-marker substring scan tripped by quoted meta-commentary. Speculative; not observed.
- **F13** — `_KBEntry` lazy import in `_kb_summary` is cosmetic only; comment is mildly misleading but no behavioural cost (sys.modules cache).

## Plan Alignment

CLAUDE.md round descriptions for R60.1, R61, R62, R63-C, R63-E, R63-F are accurate against the merged code. **One contradiction:** R63-C CLAUDE.md row claims "Backward-compatible: empty question OR no specificity marker hit OR no clear winner (margin ≥ 2) → returns the joined string (R55+ behaviour)". The verified C1 bug means this guarantee is broken on multi-turn — the "live question" never reaches the selector intact, so the documented backward-compatibility on broad questions is silently subverted whenever a prior turn happened to mention a specificity marker.

## Review Metadata

- **Agents dispatched:** 5 specialists in parallel (Logic & Correctness, Error Handling & Edge Cases, Contract & Integration, Concurrency & State, Security) + 1 Verifier
- **Scope:** 10 production files + 7 test files + `CLAUDE.md` steering review
- **Raw findings:** 13 distinct after pre-verifier dedup (from 19 across specialists)
- **Verified findings:** 10 (1 Critical + 6 Important + 3 Suggestions)
- **Filtered out:** 3 (F5 / F11 / F13)
- **Steering files consulted:** [`CLAUDE.md`](CLAUDE.md)
- **Plan/design docs consulted:** PR descriptions for #85, #86, #87
