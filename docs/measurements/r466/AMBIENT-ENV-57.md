# R466 — the 57 "order-dependent" failures were the operator's shell

**Verdict: no test was poisoning any other. All 57 came from two environment
variables the repo itself tells the operator to export, which
`tests/conftest.py` never neutralised.** Each reproduces alone, in one file, on
a clean tree; the suite is otherwise order-independent.

## 1. The claim under test

R464 left a red full suite on this box — 9,681 passed / 57 failed — with three
observations that together looked like order dependence:

* every failing test passed when run alone;
* the same 57 failed with the R464 work stashed (i.e. not the change under review);
* CI's clean clone was green.

The 57 were blamed on "some earlier test's import or global state". That
hypothesis makes a prediction: a subset run must reproduce it. It does not —
and neither does collecting every module and running only the bridging test
(`pytest tests/ -k bridging` → 4 passed), so not even an import-time side effect
is involved.

## 2. The decomposition (measured, disjoint, exact)

| ambient flag | failures |
| --- | --- |
| `P2P_GRAPH_RAG_PROVIDER=cli` | **51** |
| `REGENOLD_EXTERNAL_EMBEDDINGS=0` | **6** |
| union | **57** |

The two sets are disjoint and their union is **identical** to the 57 recorded
from the failing full run — `comm -3` against the original FAILED list prints
nothing. Re-measured on the 16 affected files only (≈14 s each arm):

```
P2P_GRAPH_RAG_PROVIDER=cli   → 51 failed, 319 passed
REGENOLD_EXTERNAL_EMBEDDINGS=0 →  6 failed, 364 passed
(clean)                      →  370 passed
```

## 3. It is not order dependence — it is the process environment

Each flag reproduces on a **single file**, with no other test having run:

```bash
P2P_GRAPH_RAG_PROVIDER=cli pytest tests/test_bridging_taxonomy.py
# FAILED test_intent_classifier_attaches_bridging_context — assert None is not None
REGENOLD_EXTERNAL_EMBEDDINGS=0 pytest tests/test_external_embeddings.py
# 3 failed (test_is_available_logic, test_get_embedding_cohere_mock,
#          test_cohere_quota_cooldown_skips_followup_calls)
```

And the two flags are exactly the "deterministic environment" line that
`AGENTS.md` §2 and `CLAUDE.md:1361` hand the operator:

```
OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0
```

Whoever exported that in a shell (or whose IDE task did) ran a different suite
than CI — which is why "passes alone, fails in-suite" looked like leakage: the
subset runs were launched without the prefix, the full run with it.

## 4. Mechanism — two shipped gates, both read live

* `is_openai_wrapper_enabled()` returns **False** for `cli`
  (`app/llm/openai_wrapper_provider.py:636`). Stage-0 intent
  (`is_intent_enabled`), Stage-2 polish (`_stage2_provider_enabled`) and the
  CLARA gate all short-circuit **before** their own mocks, so 51 tests that
  patch the wrapper never see their patch used. The first one is
  `test_bridging_taxonomy.py:30`.
* `external_embeddings` is force-disabled by `=0` for **both** providers
  (`app/engines/external_embeddings.py:206`) — so a test that sets a Cohere key
  and expects `is_available()` to follow it gets `False`. Six tests, the first
  being `test_external_embeddings.py::test_is_available_logic` step 2.

`tests/conftest.py` already neutralises the *credentials* this way (R105) and
the collection-time *writes* (R382), which is why the remaining leak was easy to
misread as still-order-dependent. No `tests/` module writes these two at import,
so R382 has nothing to undo.

`app/config.py::_load_dotenv_once` is **not** a channel here: it returns early
when `"pytest" in sys.modules`, so `os.environ` inherited from the parent
process is the only path.

## 5. Fix

`tests/conftest.py`, inside the same `REGENOLD_TEST_ALLOW_LIVE` guard as the
credential neutralisation:

* `_AMBIENT_OFFLINE_FLAGS = ("P2P_GRAPH_RAG_PROVIDER", "REGENOLD_EXTERNAL_EMBEDDINGS")`
  are **dropped** (not pinned) at conftest import, so the code defaults apply —
  exactly what a clean CI clone sees. Per-test `monkeypatch.setenv` still owns
  either value, and the R361 snapshot keeps it for the test that set it.
* A one-shot `warnings.warn` names the dropped `key=value` pair, so the operator
  who deliberately exported the recipe sees *why* the suite ignored it instead
  of re-diagnosing 57 failures.

`tests/test_r466_ambient_env_hermetic.py` pins it two ways:

1. structural — the constant still names both flags;
2. behavioural — a real child `pytest` (fresh interpreter, recipe exported) over
   `test_bridging_taxonomy.py` + `test_external_embeddings.py` must exit 0.

The behavioural arm is the discriminating one: with the conftest hunk stashed it
reports **4 failed, 4 passed** in the child and the test fails; with the hunk it
is green. Asserting on module state alone would not notice the removal.

## 6. Verification

| run | result |
| --- | --- |
| full suite, **recipe exported**, post-fix | **9,741 passed, 23 skipped, exit 0** (343.9 s) |
| full suite, clean shell, pre-fix | 9,738 passed, 23 skipped |
| full suite, **recipe exported**, pre-fix | 9,681 passed, **57 failed** |
| the 16 affected files, clean | 370 passed, 2 skipped |
| the 16 affected files, `cli` | 51 failed pre-fix → 0 post-fix |
| new test file alone | 3 passed (≈8 s, incl. the child process) |
| child pytest in the new test, conftest hunk stashed | 4 failed, 4 passed → the test fails, as it must |

The post-fix run prints the cause once in its warnings summary:

```
UserWarning: R466 — ignored ambient offline-recipe flag(s)
P2P_GRAPH_RAG_PROVIDER='cli', REGENOLD_EXTERNAL_EMBEDDINGS='0'.
```

9,738 + the 3 new tests = 9,741, so the fix adds no other behaviour change.

## 7. Scope, stated

* This closes **the recipe the repo documents**. Other ambient `REGENOLD_*`
  flags are still honoured if exported — deliberately: the suite has no mandate
  to override an operator's arbitrary experiment, and the documented recipe is
  the one that gets copy-pasted.
* It does not claim the suite has never had order dependence. R382's comment
  records 28 failures that genuinely were collection-time writes and that fix
  still stands; this round only removes the last 57 that were *read* as the same
  class.
