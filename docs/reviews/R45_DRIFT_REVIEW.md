# R45 Dead Code + Drift Review

**Scope**: `app/engines/`, `app/data/`, `app/integrations/`, `app/routes/`,
`docs/`, `README.md`, `.env.example`, `railway.toml`.
**Reviewer angle**: dead modules, duplicated data, doc drift, comment drift,
test-only helpers, plan-vs-implementation alignment.
**Constraint**: read-only — no source edits, no commits.

---

## Module status matrix

Status definitions:
- **LIVE** — imported by `app/routes/` or transitively via `app/data/kb_search.py`
  / `app/engines/graph_rag.py` on the live route. Fires on every request (or
  every request meeting a non-flag predicate).
- **LIVE-FLAGGED** — wired into the live route via `os.getenv(...)` gate; flag
  default-OFF and not set in `railway.toml`. Bookkeeping only in production.
- **LIVE-DORMANT** — wired live but cannot fire today because its precondition
  is a fallback path the route rarely reaches, or its self-exclusion logic
  fires on the davidath corpus.
- **TEST-ONLY** — only imported by `tests/` files (and possibly its sibling
  module's docstrings). Zero live callers.
- **TEST-ONLY-DOC** — only referenced from `_assets/README.md` or other
  documentation; no test or production caller.

| Module | LOC | Status | Live caller | Recommendation |
|---|---|---|---|---|
| `app/engines/answer_template.py` | 183 | LIVE | `regenold.py:58` (route) | KEEP |
| `app/engines/clara_logic.py` | 1259 | LIVE | `regenold.py:1655` (route) | KEEP |
| `app/engines/compliance_verdict.py` | 460 | LIVE | `regenold.py:1889` (route) | KEEP |
| `app/engines/cross_encoder_rerank.py` | **917** | **TEST-ONLY-DOC** | none in `app/` | **DELETE or PARK** |
| `app/engines/definition_expand.py` | 322 | LIVE-DORMANT | `kb_search.py:719` (fallback path only, self-excludes on davidath) | KEEP (queued for production paraphrased queries; defensible) |
| `app/engines/embeddings_index.py` | 448 | LIVE | `kb_search.py:573` | KEEP |
| `app/engines/graph_aware_retrieval.py` | **689** | **TEST-ONLY** | none in `app/` (only `test_graph_aware_retrieval.py`) | **DELETE or PARK** |
| `app/engines/graph_expand_2hop.py` | 473 | LIVE | `kb_search.py:660` (R40 baked) | KEEP |
| `app/engines/graph_ppr.py` | 103 | LIVE-FLAGGED | `kb_search.py:679` gated on `REGENOLD_GRAPH_PPR` (default `"0"`, not in `railway.toml`) | WIRE+bake OR DELETE |
| `app/engines/graph_rag.py` | 2897 | LIVE | route | KEEP |
| `app/engines/graphrag_expand.py` | 331 | LIVE | `regenold.py:63` (route) | KEEP |
| `app/engines/path_rag.py` | 129 | LIVE-FLAGGED | `kb_search.py:698` gated on `REGENOLD_PATH_RAG` (default `"0"`, not in `railway.toml`) | WIRE+bake OR DELETE |
| `app/engines/prohibited_gatekeeper.py` | 251 | LIVE | `regenold.py:67` (route) | KEEP |
| `app/engines/query_expansion.py` | 296 | LIVE-FLAGGED | `kb_search.py:615` (only fires when openai-wrapper provider is active — degraded silently on dev/prod default) | KEEP (cheap when wrapper absent) |
| `app/engines/scenario_classifier.py` | 877 | LIVE | route + `graph_rag.py:31` | KEEP |
| `app/engines/sentence_index.py` | 634 | LIVE | route, `vector_rerank`, `citation_guard`, `citation_faithfulness` | KEEP |
| `app/engines/task_router.py` | **218** | **TEST-ONLY** | none in `app/` (only `test_task_router.py`) | **DELETE or WIRE** |
| `app/engines/turboquant_index.py` | 540 | LIVE | `regenold.py:197`, `kb_search.py:543/623` (flag default-OFF but folded into cache key) | KEEP |
| `app/engines/vector_rerank.py` | 274 | LIVE | `regenold.py:571` (flag-gated, Linux+turbovec only) | KEEP |
| `app/data/eu_ai_act_tree.py` | (1426 nodes, 32.6 KB) | **TEST-ONLY** | none in `app/` (only `test_eu_ai_act_tree.py`) | **DELETE or PARK** |

**Dead-code total**: `cross_encoder_rerank.py` (917) + `graph_aware_retrieval.py`
(689) + `task_router.py` (218) + `eu_ai_act_tree.py` (~750 effective LOC) ≈
**~2,570 LOC** with **zero live callers** in `app/`. CLAUDE.md A10 estimated
~1,500 LOC across 4 modules; the real number is closer to 2,570 LOC across
the same 4 modules + `graph_aware_retrieval.py` (a 5th module that A10 did not
catch).

---

## B1 — `task_router.py` (R31) has zero live callers and is unreviewed since R31

**Severity**: P2
**Type**: dead-module
**Location**: `app/engines/task_router.py` (218 LOC)
**Finding**: CLAUDE.md R31 documents the module as "informational" — "every
task still routes through `ask_compliance_question`; the dispatch unlocks
per-task metric reporting in a future bench-runner upgrade." Five rounds
later (R32 → R44), no caller exists in `app/`. `grep -rnE "classify_task_4way|from app\.engines\.task_router|from app\.engines import.*task_router" app/` returns zero hits. Only `tests/test_task_router.py` imports it. The bench-runner has not consumed it. The R31 design hook (Davvetas 4-task taxonomy collapsed to `{"risk", "article", "obligation", "open"}`) was never wired into the per-task metric reporting it was designed for.
**Suggested fix**: One of:
1. **Wire it** in `evals/bench/runner.py` for per-task scorecard rows (the original R31 intent — 60 minutes work).
2. **Delete it** alongside its tests; the R31 plan can stay in `docs/superpowers/plans/` as historical context but `app/engines/task_router.py` shouldn't accumulate LOC.

Note: this is a separate finding from A10 — CLAUDE.md's A10 lists 4 modules
(`eu_ai_act_tree.py`, `cross_encoder_rerank.py`, `graph_ppr.py`, `path_rag.py`)
but the same standard catches `task_router.py` too. The R43 reviews missed it.

---

## B2 — `graph_aware_retrieval.py` (689 LOC) is test-only — R43 didn't list it as A10 dead-code

**Severity**: P2
**Type**: dead-module
**Location**: `app/engines/graph_aware_retrieval.py`
**Finding**: 689 LOC, env-gated `REGENOLD_GRAPH_AWARE=1` (line 81). Zero
`app/` callers. Only `tests/test_graph_aware_retrieval.py` imports it. The
module docstring claims it wires into the route — but the only place reading
`os.getenv("REGENOLD_GRAPH_AWARE")` is the module's own `is_enabled()`
helper, and **no production code calls that helper or the module's public
exports**. CLAUDE.md A10 listed 4 dead modules; this is a 5th the architecture
review missed. Its presence creates the same confusion A10 calls out
(reviewers have to trace four import patterns to confirm it's dead).
**Suggested fix**: Delete the module + its test file unless someone can name
the R-round it was supposed to wire in. If kept, add a clear `## Status:
unwired since R##` banner to the top of the file so future reviewers can
move on quickly.

---

## B3 — `intent_budget_for` (R40/F18) is dead code under default `railway.toml`

**Severity**: P2 (confirms R43 A4, still unfixed after R44)
**Type**: dead-code
**Location**: `app/integrations/regenold/models.py:204` (helper),
`app/routes/regenold.py:1723–1738` (call site)
**Finding**: The route block is gated on
`os.getenv("REGENOLD_REFBUDGET_PER_INTENT", "0") in ("1", "true", "yes", "on")`.
`railway.toml` does not set this flag. The flag is not listed in the bench
runner. The flag is not documented in `.env.example`. R43 surfaced this as A4
and recommended either bake or delete — R44 chose neither. The
`description_short` / `description_scenario` budget split, the helper, and
the gate block are now ~30 LOC of orchestration that nothing exercises in
production. The 5 unit tests in `tests/test_r40_phase5_sweep.py` are the
only consumers.
**Suggested fix**: Bake `REGENOLD_REFBUDGET_PER_INTENT=1` if it's
rubric-positive (R40 evidence ambiguous: Ans Strict -0.009, Conciseness
+0.011 — net negative on the davidath rubric). Otherwise delete the helper,
the split keys, the route block, and the 5 tests.

---

## B4 — CLAUDE.md `## Eval scorecard` table is anchored at R23/R25 (3 rounds stale × 2)

**Severity**: P3
**Type**: doc-drift
**Location**: `CLAUDE.md` lines ~436, 541, 649, 682, 1721, 1949 (test-count
claims), `README.md:118` (`~1300 tests`).
**Finding**: Multiple stale test-count claims across CLAUDE.md per-round
sections (`556 unit tests pass`, `578`, `718`, `678`, `912`, `971/971`,
`1331`, `1393`, `1474`, `1527`). The latest CLAUDE.md round (R44) correctly
shows `1527`. **README.md, however, still says "~1300 tests"** — that was
the R37/R38 count, four rounds out of date. New contributors copying the
quick-start instructions will see a 17% under-report.

Additionally, the Eval scorecard table at the bottom of CLAUDE.md (the
"Round 15 / 17 / 18 / 18.1 / 19 / 21" table) was last updated in R21 and
is nine rounds out of date. It claims F1=0.71 for R21 retrieval; current
ref-strict is 0.430.
**Suggested fix**: 1-line edit to README.md (`~1300` → `~1527`), and either
extend the Eval scorecard table through R44 or delete it (the per-round
bench scorecards inside CLAUDE.md already give richer numbers).

---

## B5 — `NEO4J_RUNBOOK.md`, `.env.example`, and `CLAUDE.md` reference the **removed** `REGENOLD_GRAPH_2HOP` env-var

**Severity**: P1 (operator-facing — runbook gives instructions that have no effect)
**Type**: doc-drift / comment-drift
**Locations**:
- `docs/partners/regenold/NEO4J_RUNBOOK.md:37` — `export REGENOLD_GRAPH_2HOP=1`
- `.env.example:71–74` — `REGENOLD_GRAPH_2HOP=1` (commented sample)
- `CLAUDE.md` Round 35 block (lines ~1490, 1513, 1557, 1594) — repeatedly
  documents `REGENOLD_GRAPH_2HOP` as a live flag, lists it in `railway.toml`
- `app/routes/regenold.py:192` (docstring only — correctly says "baked", OK)
**Finding**: R40 Phase 1 baked the 2-hop expand: the env-var was deleted from
the code (no `os.getenv("REGENOLD_GRAPH_2HOP")` survives in `app/`, only in
test fixtures). CLAUDE.md's R40 acceptance summary (line 1439) explicitly
celebrates "Zero `os.getenv("REGENOLD_SUBPOINT_EMIT|TONE_GUARD|GRAPH_2HOP|
CLARA_VERDICT|EMBEDDINGS_INDEX")` calls in `app/`". But:
1. The **Round 35** section of the same CLAUDE.md (still present) tells the
   operator to set the flag on Railway as the final activation step (line 1594).
2. `NEO4J_RUNBOOK.md` Step 3 has the same dead instruction.
3. `.env.example` Step 7 has the same dead sample line.
4. `railway.toml` no longer sets the flag (it was deleted along with the env
   reader) — yet R35's CLAUDE.md text shows it in the example
   `[deploy.envs]` block.

A new operator following `NEO4J_RUNBOOK.md` today will `railway variables
--set REGENOLD_GRAPH_2HOP=1`, see no effect, and conclude something is
broken. The doc-vs-code drift undermines trust in the runbook.
**Suggested fix**: Find-and-replace pass across the three docs:
- `NEO4J_RUNBOOK.md:36-37` — delete the "Optional" Step 3 block (it now does nothing).
- `.env.example:71-74` — delete the four-line REGENOLD_GRAPH_2HOP block.
- `CLAUDE.md` Round 35 — add a "## NOTE: R40 baked this flag; the section
  below is historical" preamble OR rewrite the activation steps to drop the
  flag. (Same treatment for the dead R32 flags `REGENOLD_CLARA_VERDICT` and
  `REGENOLD_EMBEDDINGS_INDEX` documented in CLAUDE.md lines 1904, 1940,
  1995, 1998.)

---

## B6 — Compliance-vocabulary registry duplicated three ways with measured 12-entry overlap (R43 A5 unfixed)

**Severity**: P2 (confirms R43 A5, plus new finding)
**Type**: duplicated-data
**Locations**:
- `app/engines/compliance_verdict.py:98–153` — `_COMPLIANCE_DOMAIN_NOUNS` (50 entries, tuple)
- `app/integrations/regenold/scope.py:1301–1341` — `_DIMENSION_KEYWORDS` (31 entries, frozenset)
- `app/data/ontology.py:242` — `PRACTICE_REGISTRY` (9 practices, 55 keywords)
**Quantified overlap** (verified at write time via Python):
- `_COMPLIANCE_DOMAIN_NOUNS ∩ _DIMENSION_KEYWORDS` = **12 exact**
  (accuracy, audit trail, automatic event recording, bias mitigation, data
  governance, data quality, event recording, human oversight, operator
  override, robustness, training data, transparency)
  — plus many near-duplicates (`bias-mitigation` vs `bias mitigation`,
  `risk-management process` vs `risk-management`).
- `_DIMENSION_KEYWORDS ∩ PRACTICE_REGISTRY.keywords` = **3 exact** (biometric
  categorisation, biometric identification, predictive policing).
- `_COMPLIANCE_DOMAIN_NOUNS ∩ PRACTICE_REGISTRY.keywords` = **0 exact** (the
  practice registry holds Art. 5 prohibited-practice keywords; the
  compliance-noun list holds HRAIS obligation keywords — different
  semantic spaces, but the hyphen-normalisation gap means they each
  half-cover the same underlying concepts).
**Drift risk**: any time a new compliance term lands (R44 added
"definition", "defined term" to definitional vocabulary; R42 added
"compliance-domain nouns"; R41 added "intended purpose"), the contributor
has to know whether to add to (a) the compliance verdict signal counter,
(b) the scope anchor pool, (c) the practice-registry keyword set, or
(d) all three. R42 + R44 each added to a different two of the three.
**Suggested fix** (R43 A5 unchanged):
1. Single source of truth at `app/data/compliance_vocab.py` (new module)
   exporting three derived frozensets via construction from a canonical
   list-of-tuples `(canonical, hyphenated_variant, intent)`.
2. Both consumers import the derived frozenset they need; the canonical
   list is the one place a contributor edits.
3. Add a `test_compliance_vocab_no_silent_drift.py` that fails if any
   future code re-introduces a literal vocabulary list.

---

## B7 — Stopword vocabulary forked verbatim into `evals/bench/citation_faithfulness.py` (R44)

**Severity**: P3
**Type**: duplicated-data
**Locations**:
- `app/data/kb_search.py:124–147` — `_STOPWORDS` (~140 tokens)
- `evals/bench/citation_faithfulness.py:43–66` — `_STOPWORDS` (same ~140
  tokens, comment says "copied verbatim from app/data/kb_search.py")
- `evals/bench/metrics.py:36` — third `_STOPWORDS` set (smaller)
- `evals/crystallize.py:90` — fourth `_BASIC_STOPWORDS` set
- `app/engines/embeddings_index.py:100` — fifth `_STOPWORDS` set
- `app/engines/cross_encoder_rerank.py:217` — sixth `_MIN_STOPWORDS` set
**Finding**: R44 deliberately forked the stopwords into the bench module to
"honour the eval-vs-app boundary — DO NOT touch app/." That's defensible
when the eval consumes a frozen snapshot; it's drift-positive when the
bench evolves and the runtime vocabulary changes. As of R44 the two lists
are byte-equal but there's no test pinning that — `app/data/kb_search.py`
can grow new stopwords ("furthermore", "moreover", "thereby" come up
frequently in EUR-Lex prose) and the bench's faithfulness scorer will
silently use an older vocabulary, biasing the citation-faithfulness score
the team uses to gate the wire.
**Suggested fix**: Either:
1. Add a `test_stopword_parity.py` that imports both `_STOPWORDS` sets and
   asserts `set_eq` (cheapest fix; respects the boundary).
2. Move the canonical list to `evals/bench/_shared.py` and have both modules
   import from there (more invasive; breaks the boundary in the eval
   direction, not the app direction).

The current state — six independent stopword sets across `app/` and `evals/`
— is the worst of both worlds.

---

## B8 — Article-ref format conversion (`Art. N` ↔ `Article N`) inlined in 7 modules

**Severity**: P3
**Type**: duplicated-logic
**Call sites** (each implements a slightly different `Art./Article` conversion):
1. `app/integrations/regenold/models.py:525,530` — canonical wire formatter
   `format_for_response()` → `f"Article {n}"` / `f"Article {n}.{sub}"`
2. `app/engines/graph_rag.py:2171` — `entity.replace("Art. ", "art").replace("Art.", "art")`
3. `app/engines/graphrag_expand.py:207` — `return f"Article {m.group(1)}"`
4. `app/engines/prohibited_gatekeeper.py:175` — `return f"Article {m.group(1)}"`
5. `app/data/eu_ai_act_tree.py:150,219` — `long_key = f"Article {n}"`
6. `app/routes/regenold.py:1677–1681` — `if ref.startswith("Art. "): user_facing = "Article " + ref[len("Art. "):]`
7. `app/integrations/regenold/scope.py` + `app/data/kb_search.py` (`Art.` parsing for ref extraction)
**Finding**: Each call site handles the conversion slightly differently:
some preserve sub-points, some don't; some use `replace`, some use regex
`m.group(1)`, the route uses `startswith` + slice. As long as the *input*
is well-formed (a real Art. 5 ref), they all agree. But subtleties: the
letter-suffix R43 fix (Art. 4a, 60a, 75a-e) required updating SIX regex
consumers (per CLAUDE.md R43 A1+A2). The seventh — the route's `Art.`
slice — happens to work because the slice operates on the entire suffix.
But there's no single converter the new contributor can locate via
"how do I emit `Article N` on the wire?" — they discover the formatter
during testing.
**Suggested fix**: Single helper at `app/integrations/regenold/models.py`
already exists (`format_for_response()`); make it the single import for
all 7 call sites. The R43 single-regex-constant pattern
(`ARTICLE_NUMBER_RE_BODY` in `app/data/article_existence.py`) was the
correct pattern for letter-suffix; this finding is the same pattern
applied to format conversion.

---

## B9 — `docs/superpowers/plans/2026-05-17-r38-r39-graphrag-upgrade.md` references **5 deleted env-vars**, not flagged for archival

**Severity**: P3
**Type**: doc-drift / plan-implementation-mismatch
**Location**: `docs/superpowers/plans/2026-05-17-r38-r39-graphrag-upgrade.md`
(implementation plan still in `plans/`)
**Finding**: The plan describes the R38–R39 work that was actually executed,
but R40 subsequently **baked** five of the env-flags the plan describes as
opt-in (`REGENOLD_SUBPOINT_EMIT`, `REGENOLD_TONE_GUARD`, `REGENOLD_GRAPH_2HOP`,
`REGENOLD_CLARA_VERDICT`, `REGENOLD_EMBEDDINGS_INDEX`). The plan documents
roll-back instructions, A/B benchmarks, and acceptance criteria pinned to
those flags — all dead since R40. New contributors reading the plan today
will believe these are still toggleable.

The plan also instructs `Remove-Item Env:REGENOLD_SUBPOINT_EMIT` (line
521) — pointing at a no-op variable in current production. The acceptance
criteria at line 1177 (`REGENOLD_SUBPOINT_EMIT=1 → Ref Strict +0.04–0.06`)
is now load-bearing for nothing, since the flag has no effect.
**Suggested fix**: Either:
1. Move the plan to `docs/superpowers/plans/archived/` (it's an executed
   plan with stale activation instructions).
2. Add a "## STATUS: executed and baked in R40 — env-flags removed" preamble
   at the top of the doc.
3. Delete the doc if its successor (`docs/superpowers/specs/...-design.md`)
   carries the same architectural narrative.

---

## B10 — `docs/competition-readiness-report.md` is anchored at **R22** (15 rounds stale)

**Severity**: P3
**Type**: doc-drift
**Location**: `docs/competition-readiness-report.md` (10.9 KB)
**Finding**: Header reads `# Regenold Competition Readiness Report — Round
22`, `Date: 2026-05-14`, `Eval label: r22-main`, `Pytest: 480/480`. Current
state is R44, 1527 tests, davidath holdout Ans Strict 0.300, Ref Strict
0.440. The report's scorecards quote pre-Round-26 numbers across multiple
axes. Any decision-maker reading the report today will under-estimate
current accuracy by ~25% on Ans Strict, and over-estimate on Ans
Conciseness.
**Suggested fix**: Either regenerate from `evals/bench/unbiased_runner`
(matches the post-R44 surface) or delete the file and let CLAUDE.md's
per-round scorecards stand. The report is in the documentation root —
external evaluators will read it first.

---

## B11 — `app/engines/__init__.py` is empty: no `__all__`, no controlled surface

**Severity**: P3
**Type**: structural / API-surface
**Location**: `app/engines/__init__.py` (0 bytes)
**Finding**: With 20 modules in `app/engines/`, none of which export through
the package init, every consumer hard-codes `from app.engines.X import Y`.
Refactoring (e.g. parking dead modules to `experimental/`) requires updating
every import site instead of just the package init. The hot path
(`app/routes/regenold.py`) opens with 11 module-level imports from
`app.engines.*`; another 10 lazy imports happen inside the route function.
There's no single place to read "what does the engines layer expose?".
This is the structural cost the R43 architecture review flagged in A7 (the
800-LOC god-function) and A10 (dead-module bloat) — both findings would
land cheaper with a curated `__init__.py`.
**Suggested fix**: Populate `app/engines/__init__.py` with explicit
re-exports of the LIVE surface only:
```python
from .answer_template import apply_template
from .clara_logic import analyse as clara_analyse
# … (one line per live entry point)
__all__ = ("apply_template", "clara_analyse", ...)
```
Then dead modules can be detected mechanically: `pyflakes app/engines/` will
flag any module not re-exported. Lower-priority but unblocks B1/B2's
mechanical fixes.

---

## Recommended deletions (conservative — only proven dead)

These have **zero callers in `app/`**, **only test or doc references**, and
the tests test the module in isolation rather than as a route component:

1. `app/engines/task_router.py` (218 LOC) + `tests/test_task_router.py`
   — verified by grep: `classify_task_4way` is imported only by its own test.
2. `app/engines/graph_aware_retrieval.py` (689 LOC) + `tests/test_graph_aware_retrieval.py`
   — same verification.
3. `app/engines/cross_encoder_rerank.py` (917 LOC) + `tests/test_cross_encoder_rerank.py`
   — only doc reference is `_assets/README.md` (which describes Strategy B
   asset loading for a model nobody ships). R32 said this was "scaffolded";
   it's still scaffolded.
4. `app/data/eu_ai_act_tree.py` (~750 effective LOC) + `tests/test_eu_ai_act_tree.py`
   — R32-built, 1426-node tree, zero consumers. R34 P1 (regex over-match)
   was a real bug fix, but the bug was latent precisely because the module
   isn't on any path.

**Combined savings if all 4 deleted**: ~2,570 LOC of `app/` + ~25 KB of
test files, no runtime change, no bench delta.

## Recommended wirings (alternative to deletion — flag-and-bake)

If the team wants to keep the optionality:

1. `app/engines/graph_ppr.py` + `app/engines/path_rag.py` — set
   `REGENOLD_GRAPH_PPR=1` and `REGENOLD_PATH_RAG=1` on a Neo4j-Aura
   instance with GDS, run the bench, decide. Either bake in `railway.toml`
   (drop the env reader, drop the cache-key bits in `_engine_cache_key`)
   or delete the modules. The R43 A10 follow-up never landed; this is the
   gate.
2. `app/engines/task_router.py` — wire into `evals/bench/runner.py` for
   per-task scorecards. The R31 plan suggested this; the bench-runner
   upgrade was never done.

## Recommended doc fixes (mechanical)

1. `README.md:118` — `~1300 tests` → `~1527 tests`.
2. `docs/partners/regenold/NEO4J_RUNBOOK.md:36-37` — delete the dead
   `REGENOLD_GRAPH_2HOP=1` step.
3. `.env.example:71-74` — delete the dead `REGENOLD_GRAPH_2HOP` sample block.
4. `docs/superpowers/plans/2026-05-17-r38-r39-graphrag-upgrade.md` — move to
   `archived/` or add a `STATUS: executed + baked R40` preamble.
5. `docs/competition-readiness-report.md` — regenerate from
   `unbiased_runner` against R44-final, or delete in favour of CLAUDE.md.
6. CLAUDE.md Round 35 block (lines ~1490, 1513, 1557, 1594) — drop the
   `REGENOLD_GRAPH_2HOP` lines from the "Production deploy commands" and
   add a "(baked in R40)" parenthetical to the Round 35 design narrative.

---

## Severity index

| Severity | Count | Findings |
|---|---|---|
| P1 | 1 | B5 (operator runbook gives broken instructions) |
| P2 | 4 | B1, B2, B3, B6 |
| P3 | 6 | B4, B7, B8, B9, B10, B11 |

No P0 issues — the live wire is correct; this review is exclusively about
code/doc that is **dead, stale, or duplicated** and therefore not
load-bearing for the May–June 2026 competition submission. But B5
(operator-runbook drift) and B6 (duplicated compliance vocabulary) compound
across rounds — each new round that touches one of these surfaces pays the
cost of re-deriving which copy is canonical.
