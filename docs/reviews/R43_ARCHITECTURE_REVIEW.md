# R43 Architecture Review

Scope: R40–R42 sprint surface. Architecture-level concerns only — engineering / security findings are out of scope for this document (covered by parallel reviewers). All findings verified by reading source + executing probes against the live worktree.

---

## A1 — R41 letter-suffix articles break the wire-contract regex (data loss on emission)

**Severity**: P0
**Files**:
- `app/integrations/regenold/models.py:262` — `_ARTICLE_OUTPUT_RE = re.compile(r"^Article \d+(?:\.[A-Za-z0-9]+)*$")`
- `app/integrations/regenold/models.py:247` — `_ART_RE = re.compile(r"^(Art\.|Article)\s*(?P<num>\d+)\s*(?P<tail>.*)$", re.IGNORECASE)`
- `app/integrations/regenold/models.py:420` — `reference_from_article_ref`

**Finding**: R41 added seven letter-suffix articles to `ARTICLE_EXISTENCE` (`Art. 4a`, `Art. 60a`, `Art. 75a`–`75e`) — the Digital Omnibus insertions. The wire-contract output regex `_ARTICLE_OUTPUT_RE` accepts only `\d+` for the article number, so `Article 75a` is rejected. The internal parser `_ART_RE` matches `\d+` then captures the suffix `a` into the tail, where `_extract_subpoints` does NOT handle it, so `reference_from_article_ref("Art. 60a(2)")` returns `"Article 60.2"` — silently conflating two distinct articles (`Art. 60` and `Art. 60a` both exist in the catalog as separate entries). Verified live:

```
reference_from_article_ref('Art. 75e')       -> None
reference_from_article_ref('Art. 60a(2)')    -> 'Article 60.2'      # WRONG — should be None or 'Article 60a.2'
```

**Why it matters**: The R41 KB additions (Omnibus articles) cannot be emitted on the wire today. Worse, when the engine surfaces `Art. 60a` (it can — the KB has full prose for it), the route silently drops the suffix and ships `Article 60.2` to the partner, which is a different paragraph of a different article. This is a silent data-corruption bug on the canonical wire contract, and it's the foundational drift that lets the rest of R41's surface ship inconsistently (see A2).

**Suggested fix**: Treat the letter suffix as part of the article identifier across the stack. Extend `_ARTICLE_OUTPUT_RE` to `^Article \d+[a-z]?(?:\.[A-Za-z0-9]+)*$`, extend `_ART_RE`'s `\d+` to `\d+[a-z]?`, and have `_extract_subpoints` preserve the suffix into the formatted output (`Article 60a.2`). Add a parametrised unit-test sweep over the full `ARTICLE_EXISTENCE` keyset that asserts every catalog entry round-trips through `reference_from_article_ref` to a non-None wire-shape match — this would have caught the gap at R41 review time. Once the contract regex is fixed, audit downstream consumers (output validators, judge mapping in `evals/`, partner-facing docs) for the new shape.

---

## A2 — Letter-suffix articles violate single-source-of-truth across the codebase

**Severity**: P0
**Files**:
- `app/data/kb_xrefs.py:55` — `_ART_RE = re.compile(r"\bArt\.?\s*(\d{1,3})\b", re.IGNORECASE)`
- `app/integrations/regenold/scope.py:97-109` — `_ARTICLE_REF_RE` (number capture is `(-?\d+)`)
- `app/routes/regenold.py:634-637` — `_LIVE_ARTICLE_RE` (`(\d{1,3})\b`)
- `scripts/seed_neo4j_kb.py:195` — `int(num)` raises ValueError on `"4a"`/`"75c"`
- `app/data/article_existence.py` — the seven letter-suffix entries

**Finding**: R41 created a new article-identifier shape (`Art. 75a`), but only TWO consumers were updated:
1. `scripts/seed_neo4j_kb.py::_ART_NUMBER_RE` (accepts `\d{1,3}[a-z]?`) — partially fixed
2. `app/data/eu_ai_act_tree.py` — handles them

EVERY other regex that parses article references is still `\d+` / `\d{1,3}` and silently fails or mis-attributes:

- **kb_xrefs** (`\b(\d{1,3})\b`): `re.search` on `"See Art. 75a"` returns **None** because `\b` between digit `5` and letter `a` is not a word boundary. So when R41's Omnibus prose mentions `"Art. 75a"` in any obligation summary, the regex extractor records NO edge. Letter-suffix articles enter the xref graph **only** via the 19 manual edges added in R41 — `Art. 75d` and `Art. 75e` exist in the catalog but appear in ZERO edges (verified).
- **scope `_ARTICLE_REF_RE`**: `re.search('Art. 75a')` returns None for the same reason. A user query like *"What does Art. 75a require for Omnibus SMC obligations?"* is classified by scope as `non_existent_article` (verified).
- **route `_LIVE_ARTICLE_RE`**: Same; the anchor-derivation pipeline never sees `Art. 75a` as an anchor.
- **seed script `_classify_risk_for_article`** (line 195): `int(num)` ValueErrors on `"4a"`, returns `None`, so the letter-suffix articles get NO `APPLIES_AT` edge in Neo4j.

Additionally, `Annex XIV` was added in R41 (Agentic AI designation), but `scope.py::_ROMAN_NUMERAL_VALUES` (line 122) only goes to `"xiii": 13` and `KEYWORD_TO_ARTICLE` lists Annex I–XIII. A query mentioning *"Annex XIV"* is rejected as non-existent by scope, even though it's in `ARTICLE_EXISTENCE`.

**Why it matters**: R41 shipped a regulatory update (Digital Omnibus) into the KB and into the catalog, but the regex-extraction layer that builds the cross-reference graph, the scope gate that decides "is this question on-topic", and the live-anchor extractor that drives `_prune_non_anchor_refs` all silently ignore those additions. The new articles are unreachable through the live query path — they exist in the static data only. Worse, when an end-user asks about the new articles by name, the route now refuses as `non_existent_article` even though the KB has full prose for them.

**Suggested fix**: Centralise the article-identifier regex into a single module-level constant (e.g. `app/data/article_existence.py::ARTICLE_ID_PATTERN = r"\d{1,3}[a-z]?"`) and import it everywhere a regex parses article numbers. Lift the Roman-numeral table out of `scope.py` and derive it from `ARTICLE_EXISTENCE`'s `Annex *` keys (a `Annex XIV` add then propagates automatically). Add a single CI guard that walks every regex pattern in `app/` and asserts a sample letter-suffix article matches.

---

## A3 — `compliance_verdict._already_stamped` false-positives on generic regulatory prose

**Severity**: P1
**Files**: `app/routes/regenold.py:1898-1902`

**Finding**: R42's verdict-prefix injection skips the prepend when the engine's existing answer "already" contains a verdict marker — implemented as raw substring `in` check:

```python
_already_stamped = any(m in _lower for m in (
    "compliant", "non-compliant", "non compliant",
    "context-dependent", "context dependent",
))
```

The substring `"compliant"` matches inside any sentence using the adjective "compliant" or "non-compliant" in passing. Verified:

```
True  | The system must be compliant with Article 13 transparency requirements.
True  | A non-compliant system can face fines under Article 99.
```

Both are perfectly normal regulatory prose the engine emits all the time. When the engine surfaces a sentence like *"…the system is **compliant** with the cybersecurity requirements of Article 15."* — exactly the kind of answer where AIReg-Bench scores `compliant` as the gold label — the route silently suppresses the verdict prefix and `predict_verdict`'s 1.000 accuracy gain on the AIReg-Bench eval evaporates whenever the engine happens to use the right adjective in passing.

**Why it matters**: Hidden contract — the verdict-stamp predicate assumes the substring `"compliant"` only appears in the canonical verdict opener phrasings, but the word lives in dozens of legitimate non-verdict regulatory sentences. The check is well-intentioned (avoid double-stamping) but its specification is too loose. The R42 commit message claims `VerdictAcc 0.000 → 1.000`; in production this rate degrades silently whenever the upstream engine emits a "compliant" mention.

**Suggested fix**: Match the canonical verdict openers as left-anchored phrases, not bare substrings. Compile a small regex: `re.compile(r"\bthis (?:system|ai) (?:is|appears) (?:compliant|non-?compliant)\b", re.I)` and use that for `_already_stamped`. Pin the contract with a unit test on each false-positive sentence above. While there, factor the predicate into `compliance_verdict.is_already_stamped(answer)` so the canonical opener strings (`_COMPLIANT_PREFIX`, etc.) and the stamp-detector live next to each other.

---

## A4 — `intent_budget_for` (R40/F18 new helper) is dead code in production

**Severity**: P2
**Files**:
- `app/integrations/regenold/models.py:204-224` — `intent_budget_for(qtype, is_scenario_shape)`
- `app/routes/regenold.py:1723-1738` — only call site
- `railway.toml` — no `REGENOLD_REFBUDGET_PER_INTENT` setting

**Finding**: R40/F18 added the `intent_budget_for` helper plus the `description_short` / `description_scenario` budget split (8 ref vs 3 ref). The only call site in `app/routes/regenold.py` is gated on `os.getenv("REGENOLD_REFBUDGET_PER_INTENT", "0")` defaulting OFF. `railway.toml` does not set the flag, so production runs with it OFF. The helper, its tests, and the split-key table never fire on the live wire.

**Why it matters**: This is a quiet expansion of API surface (a new public helper + new dict keys) that the codebase commits to maintaining (test coverage, future refactors must keep it working) but which is gated behind an env flag the project explicitly chose NOT to flip ("R39: default OFF after eng-review found per-intent budgets regressed transparency_deepfake + omnibus_art101_gpai eval scenarios"). Two options are both defensible — either commit (flip the flag and re-tune the budgets so the help fires) or remove (drop the helper + the split keys + the only call site + the F18 unit tests) — but ship-and-leave-disabled creates maintenance debt with zero rubric upside.

**Suggested fix**: Pick one of:
1. **Commit**: Set `REGENOLD_REFBUDGET_PER_INTENT=1` in `railway.toml`, re-run the bench, lock in whatever budget calibration recovers the R39-regressed probes. Then bake the flag.
2. **Remove**: Delete `intent_budget_for`, the `description_short`/`description_scenario` keys (alongside the now-redundant `description` alias), the route's `REGENOLD_REFBUDGET_PER_INTENT` block, and `tests/test_r40_phase5_sweep.py::test_f18_*`. The existing `_effective_max_refs = 10 if _is_scenario_question else MAX_REFERENCES` binary split is the production path and it's working.

---

## A5 — `compliance_verdict._COMPLIANCE_DOMAIN_NOUNS` duplicates `scope._DIMENSION_KEYWORDS` + `_AI_ACT_ANCHORS`

**Severity**: P2
**Files**:
- `app/engines/compliance_verdict.py:98-153` — 50-entry domain-noun list
- `app/integrations/regenold/scope.py:1217-1280` — `_DIMENSION_KEYWORDS`
- `app/integrations/regenold/scope.py:425-1224` — `_AI_ACT_ANCHORS`

**Finding**: 18 of the 50 entries in `compliance_verdict._COMPLIANCE_DOMAIN_NOUNS` (36%) duplicate entries already in `scope.py`'s vocabulary (verified). R42 added `"automatic event recording"`, `"event recording"`, `"bias-mitigation"`, `"data governance"`, `"data-governance"`, `"risk-management process"`, `"risk management process"`, `"credit scoring"`, `"biometric identification"`, `"biometric categorisation"`, `"predictive policing"` to BOTH `scope._DIMENSION_KEYWORDS` (for the scope gate) AND `compliance_verdict._COMPLIANCE_DOMAIN_NOUNS` (for the verdict trigger). The two lists serve different purposes (in-scope detection vs scenario-shape detection) but the canonical vocabulary is the same regulatory taxonomy.

**Why it matters**: Three problems:
1. **Drift risk**: A future regulatory update (e.g. Omnibus Phase II adds "operator override metric") will be added to one list and forgotten on the other. The verdict-detector and the scope-gate then disagree about whether the same question is "compliance-related".
2. **Test coverage doubled, signal halved**: Each vocabulary needs its own test sweep, but the failure modes overlap.
3. **Where does new vocabulary live?** A contributor adding a term has no canonical place to put it. The R42 diff actually added the SAME 11 phrases to both files in the same commit — there's no shared source of truth yet.

**Suggested fix**: Create a single registry `app/data/compliance_vocabulary.py` exposing typed buckets — `DOMAIN_NOUNS_HRAIS`, `COMPLIANCE_VERBS_POSITIVE`, `COMPLIANCE_VERBS_NEGATIVE`, etc. — and have both `scope.py` and `compliance_verdict.py` import from it. The route's existing taxonomy modules (`ontology.py`, `practice_registry.py`) follow this pattern; the new R42 vocabulary should join them instead of forking.

---

## A6 — Route ordering: verdict prefix runs AFTER `apply_template`, can blow past the qtype length cap

**Severity**: P2
**Files**: `app/routes/regenold.py:1860-1918`

**Finding**: The route's post-engine hook order is:
1. `apply_template(qtype, answer, primary_cite)` — trims to per-qtype `INTENT_LENGTH_CAP` (definition=660, description=600, …) with the cite anchor appended
2. **R42 verdict prefix prepend** (~70 chars) + `normalise_answer_for_regenold` (600-char soft cap)
3. `enforce_tone`

When `apply_template` trims a `definition`-qtype answer to its 660-char cap and the verdict prefix prepends ~70 chars, the combined text is ~730 chars. `normalise_answer_for_regenold`'s 600-char soft cap then kicks in and drops the longest non-cite-anchored sentence — which could be the load-bearing answer body that `apply_template` deliberately kept. The verdict's `(Article N)` cite anchor saves the verdict prefix from being dropped, but the body content (which `apply_template` calibrated against the davidath p90 gold distribution) may not survive.

The two cap pipelines are independent (`apply_template` doesn't know about the 600 soft cap; the soft cap doesn't know about per-qtype caps), and R42 inserts a high-priority prefix between them without budget reconciliation. Same hazard with the R31.2 prohibition verdict prepend and the CLARA citation injection, but those land BEFORE `apply_template` so the template trim still governs.

**Why it matters**: The R40/Phase 2a calibration of `INTENT_LENGTH_CAP` against davidath p90 was the lever for Ans Conciseness wins. Adding a downstream pass that ignores those caps and re-trims via the 600-char soft cap means the calibrated lengths are advisory, not binding. As more post-template hooks land (R43+ will likely add more), this discrepancy grows.

**Suggested fix**: Make a single canonical "answer normalisation epilogue" function that runs ALL of: prohibition-verdict prepend, CLARA injection (move it to answer-side too), compliance-verdict prepend, qtype-template trim, tone enforce — in that order, with the qtype cap as the OUTER governor. The route invokes the epilogue once with the engine's raw answer and the resolved cite list. This removes the soft-cap-vs-template-cap mismatch and gives every future hook a single point of insertion.

---

## A7 — Route function is becoming a god-function (700+ LOC of orchestration)

**Severity**: P2
**Files**: `app/routes/regenold.py:1228-2022` (the `regenold_eu_ai_act_ask` view + its 8 inline hooks)

**Finding**: The view function itself is 795 lines and orchestrates 11 distinct passes inline: input validation → scope gate → cache lookup → engine call → classification short-circuit detection → extractive QA → QA trim → candidates reshape → anchor surface → smallest-cover → subpoint emit → anchor prune → prohibition gatekeeper → verdict prepend → CLARA injection → graph expand → re-collapse → references cap → orphan-ref enforcer (gated off) → citation guard → apply_template → R42 verdict prefix → tone enforce → telemetry build → audit chain write. Every R31 / R32 / R34 / R36 / R38 / R40 / R42 round has appended another inline block with a multi-paragraph docstring above it.

Several anti-patterns visible:
- Repeated inline `from app.engines.X import Y  # noqa: PLC0415` blocks (each pass lazy-imports its dependency).
- Hook-flag truthiness logic duplicated across 5 places (`if _is_scenario and not _is_classification_topic and not _is_multiturn...`).
- Two near-identical `for ref in ...primary_articles: if ref.startswith("Art. "): user_facing = "Article " + ref[5:]` blocks (CLARA at line 1675, extractive at line 540) — see A8.

**Why it matters**: The class of bug surfaced in A3 (verdict-stamp substring) and A6 (cap-pipeline mismatch) becomes inevitable once a 795-LOC view function is the integration point for 11 cross-cutting concerns. Each new round adds another concern, and the local reasoning required to add it correctly (knowing all the prior passes' invariants) is impossible to perform without reading the whole function. CLAUDE.md describes the architecture as a layered pipeline but the route IS the pipeline — the layering only exists in module names.

**Suggested fix**: Extract a `PipelineContext` dataclass (question, system_context, engine_response, candidates, scope_verdict, qtype, primary_cite, …) plus a sequence of `PipelineStage` objects (`ExtractiveQA`, `ProhibitionGatekeeper`, `CLARAInjection`, `GraphExpand`, `Subpoints`, `AnchorPrune`, `TemplateTrim`, `VerdictPrefix`, `ToneEnforce`). Each stage is a `process(ctx) -> ctx` callable in its own module (most already live in `app/engines/` or `app/integrations/regenold/`). The route becomes a 30-line driver that constructs `ctx`, runs stages in order, writes the audit chain, and serialises the response. Per-stage feature flags + ordering become a list literal, not nested conditionals. This is the refactor R43 should do BEFORE adding more hooks.

---

## A8 — Internal `Art. N` ↔ wire `Article N` conversion duplicated in 3+ inline locations

**Severity**: P2
**Files**:
- `app/routes/regenold.py:1677-1680` — CLARA injection
- `app/routes/regenold.py:540-548` — extractive-QA citation refs
- `app/integrations/regenold/models.py:284-298` — `_normalise_to_catalog_form` (the inverse direction)
- `app/integrations/regenold/models.py:420` — `reference_from_article_ref` (the official converter)

**Finding**: The bundle has a strict rule (CLAUDE.md "Hard rules" #1) that internal refs are `Art. N(.subpoint)*` / `Annex X(.subpoint)*` and wire refs are `Article N.subpoint*` / `Annex X.subpoint*`. The route has TWO ad-hoc inline conversions (`"Article " + ref[len("Art. "):]`) instead of calling the canonical converter. These work for the simple case but they bypass:
- the existence gate (`_is_known_article_or_annex`)
- the subpoint normaliser (`_extract_subpoints` — which is what's broken for letter suffixes per A1)
- the output regex gate (`_validate_output_shape`)

The downstream `reference_from_article_ref(user_facing)` call at line 1684 catches the failure for CLARA injection (good — the bad ref is dropped) but the extractive-QA conversion at line 540 doesn't run through it at all. The dual code paths also mean any future fix to the converter (e.g. the A1 letter-suffix fix) has to be replicated in three places or the inline conversions silently drift.

**Why it matters**: This is the same single-source-of-truth violation as A2 but at the route layer. The canonical converter exists and is tested; ad-hoc inline conversions mean R41-style additions don't propagate uniformly. Today the only safety net is that the canonical converter eventually validates — but if the ad-hoc shape never reaches the validator (extractive-QA case), bugs land silently.

**Suggested fix**: Add `to_wire_form(internal_ref: str) -> str | None` and `to_internal_form(wire_ref: str) -> str | None` helpers to `app/integrations/regenold/models.py`, both implemented in terms of `reference_from_article_ref` and `_normalise_to_catalog_form`. Replace every inline conversion with a call. Add a unit test that iterates over every `ARTICLE_EXISTENCE` entry and confirms the wire-form → internal-form → wire-form round-trip is the identity.

---

## A9 — `compliance_verdict.py` shape-detection regex is permissive enough to trip on third-person definitional QA

**Severity**: P3
**Files**: `app/engines/compliance_verdict.py:78-93`

**Finding**: The third-person-opener regex matches `(?:^|[:.]\s+)(?:an?|the)\s+(?:[a-z][a-z\-]*\s+){0,5}(?:ai(?:-\w+)?|system|tool|model|application|software|...)`. Combined with the `≥2 compliance-domain nouns` gate, it should fire only on scenarios. But: the AIReg-Bench wrapper string the runner uses is *"Consider the following AI system description and assess its compliance with EU AI Act Article N: …"*. That preamble itself contains "AI system" (post-colon path) and "compliance" — so on a query like *"Is the system compliant with the data-governance and human-oversight rules of Annex IV?"* (which is a definitional QA, not a scenario), the regex matches "the system" after the preamble colon AND the domain-noun count is ≥2 ("data governance", "human oversight"). The verdict-prefix injects on what should be a Q-A definitional answer.

The triple-gate is defense in depth but the gates aren't independent — they're partial overlapping signals. The `_FIRST_PERSON_RE` anti-match catches davidath ("we are..."), but there's no anti-match for "what" / "how" / "does" / "is" QA-shape questions.

**Why it matters**: R42's headline is `VerdictAccuracy 0.000 → 1.000` on AIReg-Bench. The downside risk is verdict-stamping definitional QA — and the rubric penalty for an unwarranted "This system is non-compliant…" lead on a what-is-X answer is sharp (per CLAUDE.md round 31's experience: a verdict on the wrong question type costs Ans Strict and Ref Conciseness). The triple-gate plus the substring `_already_stamped` (broken per A3) together make the verdict's actual production behaviour hard to predict.

**Suggested fix**: Add an anti-match for QA-shape question words: `_QA_OPENER_RE = re.compile(r"^\s*(?:what|how|when|where|who|why|does|is|are|can|must|should)\b", re.IGNORECASE)`. Skip the verdict when this fires AND the question doesn't carry a `_FIRST_PERSON_RE` mismatch (i.e. definitional or info-seeking shape). Pin the contract with at least 3 unit tests covering: scenario fires verdict, davidath first-person doesn't fire, QA-shape doesn't fire.

---

## A10 — Dead-code stack: 4 modules built in R31/R32/R39 with no production wiring or planned wiring

**Severity**: P3
**Files**:
- `app/data/eu_ai_act_tree.py` (1426-node parsed tree — built, no consumer)
- `app/engines/cross_encoder_rerank.py` (built in R32, never wired)
- `app/engines/graph_ppr.py` (env-gated `REGENOLD_GRAPH_PPR=0`, no creds doc, not bench-positive)
- `app/engines/path_rag.py` (env-gated `REGENOLD_PATH_RAG=0`, same)

**Finding**: Verified by grep + reading the wiring at `app/data/kb_search.py:670-707`. The two graph modules check `is_ppr_available()` / `is_pathrag_available()` which read `os.getenv(_FLAG_VAR, "0")` — not set anywhere including `railway.toml`. The tree module is imported only by its own test file. The cross-encoder is referenced only in `app/engines/_assets/README.md`. CLAUDE.md documents this:

> Layer A's wire and Layer D's cross-encoder route integration are deferred to Round 33 once bench-side gate tuning confirms the rubric direction.

It's now R42 and the deferred wiring hasn't happened.

**Why it matters**: ~1500 LOC across four modules accreting in the engines layer, with tests + docs + import graph weight, none of it shipping. The cache-key folding in `_engine_cache_key` (R40/F5) had to be extended to fold `REGENOLD_GRAPH_PPR` + `REGENOLD_PATH_RAG` into the hash to guard against runtime flag flips — that's bookkeeping cost for two modules that nobody can turn on (no Neo4j-GDS creds on the dev env, no operator docs). Each new round has to read past these modules to understand what's live vs scaffolded.

**Suggested fix**: Pick one of two strategies per module:
1. **Wire by R44**: turn `REGENOLD_GRAPH_PPR=1` on a Neo4j Aura instance, run the bench, measure. If +Ref Strict, bake the flag. If neutral/negative, remove.
2. **Park to a branch**: Move `eu_ai_act_tree.py`, `cross_encoder_rerank.py`, `graph_ppr.py`, `path_rag.py` to a `experimental/` package or a long-lived `experimental` branch. Keep the bench results + research notes in `docs/research/`. The mainline `app/` shrinks ~1500 LOC of unused code, the cache-key + the test sweep + the wiring blocks in `kb_search.py:670-707` go with them.

---

## Verification probes used

(Run via the parent-folder `.venv/Scripts/python.exe`. All commands reproducible.)

```bash
# A1: wire-contract regex rejects letter suffix
python -c "from app.integrations.regenold.models import reference_from_article_ref; \
  print(reference_from_article_ref('Art. 75e'), reference_from_article_ref('Art. 60a(2)'))"
# Output: None  Article 60.2     <-- silent data corruption

# A2: xref regex misses letter suffix
python -c "from app.data.kb_xrefs import _ART_RE; \
  print(list(_ART_RE.finditer('Art. 75a SMC')))"
# Output: []     <-- regex doesn't match at all

# A2: scope.py rejects valid Annex XIV
python -c "from app.integrations.regenold.scope import classify_scope; \
  v = classify_scope('What does Annex XIV require?'); print(v.reason)"
# Output: ScopeReason.NON_EXISTENT_ARTICLE

# A2: letter-suffix articles have zero edges
python -c "from app.data.kb_xrefs import _build_xref_graph; g = _build_xref_graph(); \
  print('Art. 75d in graph:', 'Art. 75d' in g, 'Art. 75e in graph:', 'Art. 75e' in g)"
# Output: False False    <-- catalog entries with no edges

# A3: substring stamp check fires on generic prose
python -c "
for s in ['The system must be compliant with Article 13.', \
          'A non-compliant system can face fines.']: \
  print(any(m in s.lower() for m in ('compliant','non-compliant')), s)"
# Both print True
```

---

## Findings priority summary

| ID | Severity | One-line | Fix-cost |
|----|----------|----------|----------|
| A1 | P0 | `_ARTICLE_OUTPUT_RE` rejects R41 letter-suffix articles; `Art. 60a(2)` silently becomes `Article 60.2` | Small (extend regex + add suffix-aware subpoint parser) |
| A2 | P0 | Letter-suffix + Annex XIV not propagated to kb_xrefs / scope / live-anchor regex / seed risk-classifier | Medium (centralise ARTICLE_ID_PATTERN; rebuild xref edges) |
| A3 | P1 | Verdict `_already_stamped` substring `"compliant"` false-positives on generic prose | Small (replace substring check with anchored regex) |
| A4 | P2 | `intent_budget_for` + description_short/scenario split is dead code under default env | Small (commit or remove) |
| A5 | P2 | `compliance_verdict._COMPLIANCE_DOMAIN_NOUNS` duplicates `scope._DIMENSION_KEYWORDS` (18/50 overlap) | Small (extract canonical vocabulary module) |
| A6 | P2 | Verdict prepend runs AFTER `apply_template`; per-qtype char cap is bypassed by the 600-char soft cap | Medium (factor a single normalisation epilogue) |
| A7 | P2 | `regenold_eu_ai_act_ask` view is 795 LOC orchestrating 11 inline hooks (god-function) | Large (pipeline-stage refactor) |
| A8 | P2 | `Art. N` ↔ `Article N` conversion duplicated inline (CLARA, extractive-QA) | Small (`to_wire_form` / `to_internal_form` helpers) |
| A9 | P3 | Compliance-verdict shape regex permissive enough to fire on definitional QA via AIReg-Bench preamble | Small (add QA-opener anti-match) |
| A10 | P3 | 4 modules (~1500 LOC) built in R31/R32/R39 with no production wiring or planned wiring | Medium (wire or park) |

**Critical-path recommendation for R43**: A1 + A2 are a single coordinated fix (the letter-suffix / Annex XIV propagation is one decision spanning eight files) and they should land FIRST — otherwise the R41 Digital Omnibus integration is half-shipped on every axis the wire touches. A3 is the largest single-axis correctness risk for the R42 verdict-stamp win. A7 is the load-bearing refactor that makes A4, A5, A6, A8 cheap to fix in batch.
