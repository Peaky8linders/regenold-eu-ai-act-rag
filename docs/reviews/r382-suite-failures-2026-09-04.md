# R382 — the 65 suite failures: what they actually were, and the one that is left

**Date:** 2026-09-04
**Result:** `65 failed / 7148 passed` → **`1 failed / 7221 passed`**, runtime **9:53 → 2:29**.

---

## 1. The diagnostic that shaped the work

Before fixing anything, every failing file was run **in isolation**. That split the 65 into two
disjoint classes with completely different remedies:

| class | files | failures | meaning |
| :--- | ---: | ---: | :--- |
| passes alone, fails in-suite | 17 | ~43 | cross-module state **pollution** |
| fails alone too | 13 | 19 | genuine **test-vs-behaviour** mismatch |

Two thirds of the "failures" were not defects in the code under test at all. Fixing them file by
file would have been 17 patches with a long tail; they turned out to be **three** leaks.

---

## 2. The pollution — three leaks, ~43 failures

### 2.1 Collection-time env writes (28 failures, fixed in `494edca`)

A dozen test modules write `os.environ[...]` at **module scope**. Pytest imports every test module
during collection, so those writes land **before the first test runs** — and therefore before the
per-test `_restore_process_environment` snapshot is taken. The fixture then faithfully restored the
poisoned value for the whole session. Fixed by snapshotting the baseline at the end of conftest's
own import-time setup and restoring it once collection finishes.

### 2.2 A module-scoped fixture writing env without monkeypatch (26 failures, fixed here)

`tests/test_r267_submission_fixes.py::client` wrote `os.environ["P2P_GRAPH_RAG_PROVIDER"] = "cli"`
with a bare assignment. A **module-scoped** fixture is instantiated during the setup of its
module's first test, and pytest runs higher-scoped fixtures **before** function-scoped ones — so it
ran before the per-test snapshot, which then captured and preserved the poison. The R382
collection-time guard cannot see this either: the write happens at *fixture* time, after collection.

`P2P_GRAPH_RAG_PROVIDER` is the worst variable to leak, and conftest's own R105 block says so: it is
*"deliberately NOT forced to `cli`"* because the R97/R100/R56 Stage-2 tests patch
`is_openai_wrapper_enabled` and rely on default provider routing — `cli` makes
`_stage2_provider_enabled()` short-circuit **before** their patch, so the mocked wrapper is never
called.

Minimal reproducer, before the fix:

```
pytest tests/test_r267_submission_fixes.py tests/test_r97_answer_router.py -q -p no:randomly
-> 8 failures, all "Expected '_openai_wrapper_complete_for_graph_rag' to have been called once.
   Called 0 times."
```

Fixed with `pytest.MonkeyPatch.context()`, which gives a module-scoped fixture the same
revert-on-teardown guarantee the function-scoped `monkeypatch` fixture has.

### 2.3 The global `settings` singleton (leak class closed; see § 4)

Thirty-plus modules do `settings.regenold.api_key = SecretStr(...)` and never restore it. Because
*"settings wins over env at the route"* the leaked key is authoritative. Closed with an autouse
snapshot/restore in conftest, deliberately narrow so it cannot mask a real default change.

---

## 3. The genuine failures — 19, and two were real product defects

Every one was checked against **why** the behaviour changed before touching the test, per AGENTS.md:
*"NEVER alter or suppress failing unit tests."* Where a contract changed deliberately the test was
re-pinned with the round that changed it quoted, and made **at least as strong** as what it replaced.

| test | class | resolution |
| :--- | :--- | :--- |
| `test_grounded_prose::test_user_facing_ref_form` | **product defect** | invariant #1 forbids `Art. N` on the wire; the stitcher converted the reference *label* but not the KB stub *bodies* it splices in. R380 added `Art. 26(6)/(7)` text to the Article 26 stub and it reached the user. Normalised at the single internal→user-facing boundary, **not** in `kb.py` — `Art. N` is the internal key form the KB, ontology and engine all index on, so rewriting its 362 occurrences would break lookups. |
| `test_r134::test_stage2_augmenter_called_when_enabled` | **product-adjacent defect** | R358's `_is_curated_authoritative_intercept` exists to *skip* Stage-2 for curated answers, and the test's question became one. Worse, its sibling `test_..._not_called_by_default` passed **vacuously** — it asserts `call_count == 0`, trivially true when Stage-2 never runs, and its `"Article" in answer` guard cannot detect the skip because the curated answer also cites Articles. Both now use a non-intercept question, both assert the mocked Stage-2 prose actually landed *before* asserting anything about the augmenter, and a tripwire fails loudly if a future intercept starts matching it. |
| `test_r268_board65_4::test_references_carry_article_65_4` | deliberate change | R276-D1's granularity pass defaults to `auto`, emitting **one level per parent+leaf cluster**, so `[65, 65.3, 65.4, 65.5, 65.7]` folds to `[65]`. Re-pinned to the invariant and made **two-sided**: the documented rollback `REGENOLD_REF_GRANULARITY=both` must restore the sub-points, proving they are still generated upstream and only folded here. |
| `test_r138::test_thinking_tokens_adaptive_r139` | deliberate change | R340 set `thinking_tokens` 0 → 1024 and raised `max_tokens` to 1536 *"to accommodate R340 thinking_tokens=1024"*. Re-pinned to the exact current defaults per the test's own standing instruction, not widened, with the two now-coupled defaults pinned together. |
| `test_r93_scope_rescue` ×3 | deliberate change | R364 made adjacent-EU-framework questions in-scope. New assertion is stronger: in-scope **and** the evidence attributes the framework **and** `near_oos_framework` carries its name — a genuine scope leak carries no attribution and still fails. |
| `test_r267_*` ×2 | deliberate change | R289 collapsed nine Groq model literals into `default_groq_model()`; R273 + R364 changed who answers a GDPR question. Both re-pinned against the source of truth rather than literals. |
| the rest | pollution | resolved by § 2. |

---

## 4. The one that is left

```
tests/test_r365_citable_base_guard.py::TestRouteWireEffect
    ::test_default_wire_is_byte_identical_to_pre_r365
```

**It passes in isolation.** Minimal reproducer, bisected from a 254-file prefix down to a single
poisoning test:

```
pytest tests/test_r138_bluf_verdict_citations.py::test_every_cited_article_is_in_references \
       tests/test_r365_citable_base_guard.py -q -p no:randomly
```

The wire references come back as `['Article 27', 'Annex III', …, 'Article 26', 'Article 73']`
instead of the pinned `['Article 27', 'Article 14', …, 'Article 111']` — two extra refs and a
different retrieval, so some in-process state is changing what the engine returns.

**Ruled out by execution**, each tested individually:

* every env var the poisoning test sets (`REGENOLD_CITE_CONSISTENCY`, `REGENOLD_ANSWER_ROUTER`,
  `REGENOLD_VERBATIM_ANSWER`, `REGENOLD_STAGE2_MIN_CONFIDENCE`, `P2P_GRAPH_RAG_ENABLE_STAGE2`) —
  setting each one alone leaves `test_r365` green;
* `_ENGINE_CACHE` — already cleared before every test by conftest;
* the slowapi route limiter — already reset before every test by conftest;
* the `kb_search` / `_graph_rag_impl` `lru_cache`s — cleared via a probe plugin, no effect;
* `clara_logic._LLM_CACHE` and `lexy_gate._SAFETY_CACHE` — cleared via a probe plugin, no effect;
* the `settings` singleton — now restored between tests (§ 2.3), no effect on this instance.

**It is deliberately left failing rather than xfail-ed or weakened.** A red suite with one
precisely-localised, reproducible failure is more honest than a green one that hides it, and
AGENTS.md forbids suppressing a failing test to force a pass. The next step is to diff the engine
input (`GraphContext.obligations` / `article_info`) between the isolated and polluted runs for the
same question — that will name the leaked state directly, where elimination has not.
