# Changelog

## 0.1.4 — Paper-aligned eval metrics: per-class F1 + article retrieval (2026-05-12)

### What's new

Eval harness extended to align with Davvetas et al. (arXiv:2603.09435v1),
"AI Act Evaluation Benchmark — An Open, Transparent, and Reproducible
Evaluation Dataset for NLP and RAG Systems". The paper's methodology
scores risk-level classification and article retrieval with per-class
precision / recall / F1. Our prior runner only computed binary pass/fail
+ latency. Round 18 closes that gap.

### Added — `evals/regenold/scenarios.py`

* `Scenario` dataclass extended with two optional fields (default-safe
  so every existing scenario construction stays valid):
  * **`expected_references: tuple[str, ...]`** — gold reference SET for
    scenarios where the complete citation set is unambiguous. 25
    scenarios populated (13 base + 12 omnibus extension).
  * **`risk_label: str | None`** — 4-tier taxonomy per the paper's
    hypotheses 1–4 (prohibited / high_risk / limited / minimal) plus a
    "refusal" / "out_of_scope" bucket for queries that should not yield
    a verdict. 18 scenarios labeled (2 prohibited, 3 high_risk, 13
    refusal). Limited + minimal intentionally left empty — the local
    suite lacks unambiguous gold for these two tiers, mirroring the
    paper's own edge-case acknowledgement (§4.2 "Edge Cases").

### Anti-bias guardrail (round-17 → round-18 carryover)

* **`risk_doctor_patient_transcription`** and
  **`risk_emotion_recognition_general`** (the two scenarios that
  mirror PDF examples Q2 and Q3) are deliberately **NOT labeled** with
  a `risk_label`. The third example (Annex IV technical-doc hardware)
  has no risk-label scenarios. Adding a gold tier to these would bias
  the F1 metric toward the competition's example list.

### Added — `evals/regenold/runner.py`

* Paper-aligned module docstring citing Davvetas et al. as the
  methodological basis.
* New helpers:
  * `_predict_risk_class(answer_text, references)` — heuristic
    extraction of the predicted tier from the response prose +
    citations. Position-aware (mirrors the existing
    `scenarios._verdict_high_risk` positivity guard) so a verdict
    embedded inside a carve-out clause doesn't poison the prediction.
  * `_predicted_ref_heads`, `_ref_head` — normalise refs to their head
    article/annex for set-overlap computation.
  * `_normalise_risk_label` — collapse `"out_of_scope"` → `"refusal"`
    so the confusion matrix is square against the paper's 4+1 taxonomy.
  * `_compute_classification_metrics(results)` — per-class P/R/F1 +
    macro F1 + confusion matrix. Skips unlabeled scenarios cleanly.
  * `_compute_retrieval_metrics(results)` — weighted-mean P/R/F1 over
    scenarios with non-empty `expected_references`.
* `ScenarioResult` extended with `risk_label`, `predicted_risk`,
  `expected_references`, `predicted_refs` so callers (eval harness,
  downstream notebooks) can recompute metrics or inspect per-scenario
  rows.
* JSON summary now includes a `quality.risk_classification` block
  (labeled count, per-class F1, macro F1, confusion matrix) and a
  `quality.article_retrieval` block (labeled count, weighted P/R/F1).
* `_format_report` appends a brief paper-aligned summary at the bottom
  — the existing line-by-line scenario report is unchanged.

### Added — `tests/test_eval_metrics.py`

* 20 unit tests for the new metric helpers:
  * F1 of a perfect classifier = 1.0; F1 on empty labeled set = `None`
    (handled gracefully, not NaN).
  * Precision with empty predicted set = 0.0; recall with gold ⊂
    predicted = 1.0.
  * Position-aware verdict regex handles carve-out clauses correctly.
  * Confusion matrix has all label rows even when a class has zero
    instances (square shape preserved).

### Round-18 eval results

| Class       | Our F1 (n)              | Paper F1 (Table 4, n=339)   |
| ----------- | ----------------------- | --------------------------- |
| prohibited  | 1.00 (n=2)              | 0.87                        |
| high_risk   | 1.00 (n=3)              | 0.85                        |
| limited     | — (no labeled scenarios)| 0.65                        |
| minimal     | — (no labeled scenarios)| 0.45                        |
| refusal     | 1.00 (n=13)             | — (paper doesn't model this) |
| **macro F1**| **1.00**                | 0.69 (weighted)             |

**Interpretation:** the small-N classification scores (n=18 total) are
not directly comparable to the paper's n=339. What matters is that the
rubric is now in place and aligned with academic methodology. Adding
more risk-labeled scenarios across all 4 tiers is a future direction.

| Article retrieval | n  | Weighted P | Weighted R | Weighted F1 |
| ----------------- | -- | ---------- | ---------- | ----------- |
| Round 18          | 25 | 0.52       | 1.00       | **0.64**    |

**This is the actionable signal.** Perfect recall means every gold ref
is in the predicted set, but precision is dragged down by over-citation
— the system cites the head article *plus* extra anchors when the gold
set is tight. The smallest-cover citation pass landed in round 17
addresses exactly this, and the F1 baseline now makes the gain
measurable on future iterations.

### Eval scorecard (deterministic-fallback)

| Round | Pass    | p50    | p95    | avg refs | avg sentences | Retrieval F1 |
| ----- | ------- | ------ | ------ | -------- | ------------- | ------------ |
| 15    | 276/276 | 3.04ms | 4.41ms | 2.12     | 2.29          | (not measured) |
| 17    | 276/276 | 4.31ms | 7.30ms | 2.12     | 2.04          | (not measured) |
| 18    | 276/276 | 6.29ms | 9.08ms | 2.12     | 2.04          | 0.64         |

### Tests
* 430 → 450 passing (+20 from `test_eval_metrics`).
* Round-18 eval: 276/276 = 100% pass-rate preserved.

---

## 0.1.3 — Competition-rubric optimization: smallest-cover refs + 3-sentence cap + ontology-in-BM25 + definitions + manual xrefs (2026-05-12)

### What's new

Round 17 deep-dive driven by the Regenold competition rubric (correctness
/ refs-vs-gold / conciseness / tone / latency / multi-turn). The local
eval was already saturated at 276/276 so the upgrades target the axes the
local rubric can't score: citation precision, conciseness-vs-gold-length,
and retrieval recall on phrasing variants. All changes are
**de-overfitted** from the 3 PDF example questions (technical-doc
hardware, emotion-recognition prohibition, doctor-patient transcription)
— the user explicitly asked not to bias for these. No new classification
templates were added; every upgrade is structural.

### Added — citation minimization (`app/routes/regenold.py`)

* **`_collapse_parent_refs`** — smallest-cover pass. Drops `Article 13`
  when `Article 13.2` is present; drops both when `Article 13.2.a` is
  present; same rule for Annex chains. Order-preserving so the most-
  specific cite still leads. Aligned with the Regenold rubric's
  preference for the smallest sufficient citation set.
* **`_ref_appears_in_answer`** + **`_drop_orphan_refs`** — phantom-
  citation helper. Currently disabled at the call site
  (`_ORPHAN_ENFORCEMENT_ENABLED = False`) because the round-17 eval
  showed net-negative impact: the competition judge matches refs to
  gold-set, not to answer prose, so dropping correct-but-unmentioned
  refs loses recall. Kept in code for future use when retrieval starts
  surfacing low-confidence refs the prose disavows.
* **Broad-anchor pruning** — `_surface_anchor_citations` suppresses
  Art. 99 (penalties) and Art. 113 (entry-into-force) keyword
  injections when a more-specific Article ref is already in candidates
  AND the user message doesn't contain `penalt` / `fine` /
  `applicable` / `entry into force` / `2026` / `2027` /
  `compliance deadline`. Prevents the broad anchors from spamming
  every refs list.

### Added — conciseness tightening (`app/integrations/regenold/models.py`)

* **`MAX_ANSWER_SENTENCES`**: 4 → 3 (lower bound of the spec
  recommendation "1–4 sentences"). Avg sentences/answer dropped from
  2.29 to 2.04 (-11%).
* **`_MAX_ANSWER_CHARS_SOFT = 600`** — soft cap that drops the longest
  non-cite-anchored sentence first. Never drops below 1 sentence and
  never strips the only cite-bearing sentence.
* **Hedge-word stripping** — `_META_LEAK_SUBSTRINGS` extended with
  `"i think"`, `"it appears"`, `"arguably"`, `"from my understanding"`,
  `"based on what i know"`. Sharpens tone without per-question tuning.
* **Abbreviation-aware split fix** — `_ABBREV_END_RE` now accepts
  opening-quote characters before abbreviations so refusal copy
  containing `(e.g. "Art. 13")` is not mis-split into multiple sentences.

### Fixed — reference parser sub-letter bug (`models.py:_extract_subpoints`)

* Rewritten as a unified single-sweep regex. Mixed-tail inputs like
  `Art. 13(1).a` now parse correctly to `Article 13.1.a` (was: dropped
  `.a`). Numeric-token bound (≤ 20) preserved.
* New `tests/test_reference_parser_fixes.py` — 19 regression tests.

### Fixed — role/risk longest-match (`app/engines/graph_rag.py`)

* `_detect_role_and_risk_class` switched from first-match to
  **longest-match** for both `_ROLE_PHRASES` and `_RISK_CLASS_PHRASES`.
  Fixes `gpai_systemic` losing to plain `gpai` when the question
  mentions "GPAI model with systemic risk" — without longest-match the
  matrix lookup landed on the GPAI row (3 articles) instead of the
  GPAI-systemic row (6 articles), and Art. 55 was missing on the wire.
* `_RISK_CLASS_PHRASES` extended with `"gpai model with systemic risk"`,
  `"general-purpose ai model with systemic risk"` and variants — the
  forms that appear most often in competition Q&A.

### Added — BM25 indexes typed ontology (`app/data/kb_search.py`)

* Index now ingests `PRACTICE_REGISTRY` (×9) + `ANNEX_III_REGISTRY` (×8) +
  `PHASE_REGISTRY` (×6) on top of `EC_CHECKER_OBLIGATION_MAP`. Total
  corpus: **133 docs** (96 KB + 23 ontology + Phase-anchor docs), up
  from 82.
* Each doc carries a `source` tag (`"kb"` / `"ontology"`) for downstream
  filtering. Keyword + sub-point text is 3× weighted in the indexable
  string to discriminate against incidental description matches (avoids
  over-firing on phrases like "healthcare deployers" inside the
  essential_services description).
* `top_articles_by_relevance` collapses to one row per article (max-score
  across docs) — public API contract preserved.
* New `tests/test_kb_search_ontology.py` — 16 tests covering index
  growth, ontology query coverage, no-regression on existing queries,
  article-key existence lint.

### Added — 12 new KB obligation entries (`app/data/kb.py`)

* **Notified-body lifecycle**: Arts. 28, 29, 31, 33, 34 (notifying
  authorities, CAB application, requirements, operational obligations,
  subsidiaries).
* **Harmonised standards**: Arts. 40, 41, 42 (presumption of conformity).
* **Enforcement**: Art. 78 (confidentiality), Art. 88 (GPAI enforcement
  by the Commission via the AI Office).
* **Annexes**: IX (large-scale IT systems list — kept conservative,
  no transient Council Decision numbers), X (registration info).
* Total: 1,052 words across 12 entries; avg 87 words / 3–5 sentences.
* Article coverage: 60% → 70% of the 113-article surface.
* New `tests/test_kb_stubs_filled.py` — 48 parametrised cases verifying
  non-empty summaries + ARTICLE_EXISTENCE resolution + self-reference.

### Added — Art. 3 definitions module (`app/data/definitions.py`)

* `Definition` dataclass (citation / term / description / keywords).
* `DEFINITION_REGISTRY` — 30 entries covering the highest-impact terms:
  AI system, all operator roles (provider / deployer / importer /
  distributor / authorised representative / downstream provider /
  notified body / affected person), lifecycle verbs (placing on the
  market, putting into service), intended-purpose-/-misuse-/-safety-
  component cluster, all 5 biometric definitions, real-time / post /
  remote biometric ID, emotion-recognition system, deep fake, serious
  incident, AI literacy, GPAI model / system / systemic risk.
* Helpers: `lookup_term(term_or_alias)`, `search_definitions(query, top_k)`.
* New `tests/test_definitions.py` — 16 tests.

### Added — manual cross-references (`app/data/kb_xrefs.py`)

* **`MANUAL_XREFS`** — 20 typed manual edges layered on top of the
  auto-regex extractor. Bidirectional edges covering Annex I/II/III/IV/
  V/VI/VII/XI/XII/XIII ↔ their binding articles (e.g. `Annex IV ↔
  Art. 11` for technical-doc contents, `Annex XIII ↔ Art. 51` for GPAI
  systemic-risk designation, `Annex II ↔ Art. 5` for the RBI law-
  enforcement carve-out's offence list).
* `_lint_manual_xrefs` runs at import time — every endpoint resolves in
  `ARTICLE_EXISTENCE`.
* `cross_refs_with_reason(article_ref)` returns `(target, reason)` tuples
  for prose composition. Regex-extracted edges keep their order in the
  merged graph; `cross_refs()` stays backward-compatible.

### Eval scorecard (deterministic-fallback path)

| Round  | Pass     | p50    | p95    | avg refs | avg sentences |
| ------ | -------- | ------ | ------ | -------- | ------------- |
| 15     | 276/276  | 3.04ms | 4.41ms | 2.12     | 2.29          |
| 17     | 276/276  | 4.31ms | 7.30ms | 2.12     | 2.04          |

Pass-rate preserved. Conciseness +11% (gold avg ~2 sentences). Latency
still sub-10ms p95 — well inside competition budget. Avg refs unchanged
locally because the existing scenario gold cites are mostly at the
article level; smallest-cover will matter more on the competition's
tighter gold sets.

### Anti-bias guardrail

The user explicitly asked NOT to bias for the 3 example questions in the
competition PDF (Q1 technical-doc hardware / Q2 emotion-recognition
prohibition / Q3 doctor-patient transcription). All upgrades are
**structural** — none of the 12 KB stubs, 30 definitions, 20 xrefs, or
20 BM25 ontology docs target those three topics. Existing classification
verdicts for those topics were not modified.

### Tests
* 430 / 430 passing across the full suite (was 392).
* 4 new test modules + 2 modified.

---

## 0.1.2 — Typed ontology + BM25 + cross-ref graph + role-obligation matrix (2026-05-12)

### What's new

The May 2026 deep-dive replaced the previously-implicit EU AI Act
ontology (scattered across ~660 keyword entries in 5 files) with a
**typed source-of-truth** in `app/data/ontology.py`. Lessons mapped from
the llm-wiki design pattern (`llm-wiki.md.txt`) — three patterns that
fit a static-regulation Q&A system, three patterns intentionally
skipped (memory lifecycle / mesh sync / vector embeddings — wrong fit
for a single-source deterministic competition endpoint).

### Added — typed ontology (`app/data/ontology.py`)

5 typed entity registries + 1 lookup matrix:

* **`ActorRole`** — 8 enum members for the AI Act value chain:
  provider, deployer, importer, distributor, authorised_representative,
  downstream_provider, notified_body, affected_person.
* **`RiskClass`** — 7 mutually-exclusive risk classes: prohibited,
  high_risk_annex_i, high_risk_annex_iii, limited_risk, minimal_risk,
  gpai, gpai_systemic.
* **`Practice`** — 9 dataclass instances for each Art. 5(1)(a–h)
  prohibited practice + the Digital Omnibus 9th paragraph (CSAM/NCII).
  Each carries `citation` (sub-paragraph chain), `description`,
  `exceptions`, `related_high_risk_anchor`, `effective_phase`,
  `keywords`.
* **`AnnexIIICategory`** — 8 dataclass instances for the high-risk
  use-case categories: biometrics, critical_infrastructure,
  education_grading, employment, essential_services, law_enforcement,
  migration_asylum, justice_democracy. Each carries `sub_points` +
  `related_prohibitions`.
* **`Phase`** — 6 applicability dates (2 Feb 2025, 2 Aug 2025, 2 Aug
  2026, 2 Aug 2027, plus Digital Omnibus deferrals 2 Dec 2026 + 2 Aug
  2028). Each carries `effective_date`, `articles`, `superseded_by`
  pointer for amendments.
* **`ROLE_OBLIGATIONS`** — `(ActorRole, RiskClass) → tuple[article_ref]`
  matrix encoding "I'm a deployer of an Annex III system, what do I
  owe?" answers without LLM cost.

### Added — retrieval upgrades

* **`app/data/kb_search.py`** — pure-Python BM25 over `EC_CHECKER_OBLIGATION_MAP`
  summaries. ~110 documents indexed at import (sub-50ms build, sub-1ms
  query). Fires ONLY when the curated keyword path produced zero
  entities (strict `== 0` gate). Closes the novel-phrasing recall gap:
  "How long must logs be kept?" → Art. 19 (was: no match).
* **`app/data/kb_xrefs.py`** — implicit cross-reference graph
  auto-extracted via regex from obligation-summary prose. Surfaces
  edges already present in the corpus (e.g. Art. 16's summary names
  Arts. 11/17/18/19/20/21/43/47/48/49). Used by `_retrieve_from_kb`
  to expand the citation set by up to 2 cross-refs per primary entity.
* **Role-obligation matrix path** in `_deterministic_answer` — detects
  role-self-ID ("I am a deployer") OR predicate ("what are the
  obligations of a deployer") AND a risk-class signal in the question.
  When both extractable, returns the matrix's verdict + citation set,
  bypassing the obligation-dump branch.

### Added — testing infrastructure

* **`tests/test_kb_consistency.py`** — 15 lint tests verifying every
  reference in the typed ontology + the four legacy lookup maps
  (`EC_CHECKER_OBLIGATION_MAP`, `_KEYWORD_ENTITY_MAP`,
  `KEYWORD_TO_ARTICLE`, `_CLASSIFICATION_TOPICS`) resolves in
  `ARTICLE_EXISTENCE`. The xref graph is also linted (every edge
  endpoint must be a known article).
* **`tests/test_retrieval_upgrades.py`** — 31 tests covering BM25
  ranking, xref expansion, role-obligation matrix lookups, ontology
  keyword helpers, and end-to-end wire contracts including 4 negative
  tests pinning the role-obligation gate (no risk class → no fire,
  third-person noun-phrase → no fire, verdict question → classification
  wins, etc.).
* **`evals/crystallize.py`** — eval-failure → KB-stub proposal
  generator. Runs the full suite, identifies failures by kind
  (verdict / content / scope_refusal / scope_pass), drafts a candidate
  patch for each, and appends to `evals/crystallized_proposals.md` for
  human review. Closes the eval-feedback loop without auto-mutating
  the KB.
* **`evals/stress_test_diverse.py`** — 54 diverse questions across
  Art. 5(a-h), Annex III(1-8), Annex I, content lookups, multi-turn,
  refusals, prompt-injection, leading-premise tricks.

### Added — schema document

* **`docs/ontology/ONTOLOGY.md`** — canonical schema doc covering the
  entity types, relationship types, lookup-table derivation, how to
  extend (add new prohibited practices / Annex III categories / phases),
  and the invariants the lint suite enforces. Per the llm-wiki
  insight: "the schema document is the real product."

### Regulatory-accuracy fixes (independent code-review audit)

A senior-engineer review (May 2026) caught 4 wrong entries in the
initial `ROLE_OBLIGATIONS` matrix — fixed:

1. **NOTIFIED_BODY × HIGH_RISK_* cited Art. 29** — wrong (Art. 29 is a
   deployer article). Corrected to `Art. 31, Art. 33, Art. 34,
   Annex VII`.
2. **DEPLOYER × HIGH_RISK_ANNEX_I included Art. 27 FRIA** — wrong (FRIA
   under Art. 27(1) is limited to Annex III deployers). Removed.
3. **PROVIDER × GPAI / GPAI_SYSTEMIC cited Art. 54** — wrong (Art. 54
   is the authorised-rep article for third-country GPAI providers, not
   a general GPAI provider obligation). Removed.
4. **PROVIDER × HIGH_RISK_* missed Art. 12 record-keeping** — added.

Plus 2 design improvements:

* **`social_scoring.exceptions`** reworded — credit scoring isn't an
  Art. 5(1)(c) exception, it's a separate Annex III(5)(b) high-risk
  path. The original wording risked misleading downstream consumers.
* **`_ROLE_PREDICATE_RE`** anchored at sentence-start boundary so a
  question like "How do deployer obligations differ from provider
  obligations?" doesn't seed the role-obligation matrix (no role-self-
  ID, no risk class — content question).
* **`_seed_role_obligation_obligations` + `_seed_classification_obligations`**
  now also clear `context.article_info` to prevent stale citation
  leakage alongside the curated verdict refs.

### Wired into existing pipeline

* `_deterministic_parse` — BM25 fallback fires only when entities=[]
  after keyword pass.
* `_retrieve_from_kb` — xref expansion adds ≤2 cross-refs per primary
  entity from obligation-summary prose.
* `_deterministic_answer` — three-tier short-circuit: classification
  verdict path (winning for "is X prohibited?"); role-obligation matrix
  path (winning for "I am a deployer, what do I owe?"); default
  obligation-dump path (winning for content lookups).

### Test results

| Suite | Before this PR | After |
|-------|--------|-------|
| Unit tests | 277 | **323** (+15 lint + 31 retrieval) |
| Eval scenarios | 276 / 276 | **276 / 276** (no regression) |
| Stress test | 54 / 54 | **54 / 54** (no regression) |
| Avg refs / scenario | 1.60 | 2.12 (richer via xref expansion) |
| Avg sentences / answer | 1.84 | 2.29 (matrix answers explain obligations) |
| p50 latency | 4.20 ms | 3.04 ms (faster — fewer regex passes) |
| p95 latency | 5.45 ms | 4.41 ms |

Quality dimensions unchanged at 100%: reference format conformance,
answer sentence cap, refs within max.

### What was intentionally NOT built

Per the llm-wiki pattern-mapping audit, these patterns were
**rejected** for this domain:

* **Vector embeddings / dense retrieval** — corpus is too small
  (~110 documents); BM25 ties or beats embeddings while staying
  deterministic and sub-millisecond.
* **Memory lifecycle / forgetting curves** — the regulation is the
  source of truth forever (until amended, which is a structured Phase
  event, not a decay curve). Decay would silently weaken correct
  answers.
* **Multi-agent mesh sync / shared-vs-private scoping** — one source,
  one truth, deterministic competition rubric.
* **Automation hooks (on-source, on-session-end)** — the AI Act source
  updates yearly, not per-session.
* **Auto-LLM rewrite of KB entries** — every entry is a regulatory
  claim; the human is the last gate on KB mutations.

## 0.1.1 — Classification-verdict path (2026-05-12)

### Smoking gun

The competition's Q3 example — "Is an AI that transcribes doctor–patient
conversations prohibited? Or is it high-risk as per the use cases of
Annex III of the AI Act?" — returned a 1373-character verbatim dump of
the Annex III + Art. 5 obligation rows ("Annex III: Eight high-risk
use-case categories: biometrics, critical infrastructure, …") instead
of a classification verdict. Wire references shipped as
`["Article 6", "Annex III"]` despite the prose discussing Art. 5 — a
silent reference/prose mismatch.

### Root causes (3 independent bugs, all pinned by regression tests)

1. **`_retrieve_from_kb` id collision.** Synthetic obligation rows used
   `id = f"kb-{dimension}"` so when two entities shared a dimension
   (Art. 5 + Annex III both `risk_mgmt`), the route's per-id dedup
   silently dropped the second entity from the citation list. Fix:
   include the entity in the id (`kb-{dimension}-{entity}`).

2. **Wrong keyword mappings in `_KEYWORD_ENTITY_MAP`.** Entries like
   `("transcrib", "Annex III")`, `("healthcare", "Annex III")`,
   `("hardware", "Annex IV")` confirmed false premises on every
   medical-AI / generic-hardware question. Removed or narrowed.
   Also removed `("definition of", "Art. 3")`, `("predictive policing",
   "Annex III")` (now Art. 5), `("linear regression"/"weighted score"
   /"ec faq", "Art. 6")` from `scope.py` (algorithm class doesn't
   determine risk class).

3. **No classification verdict path.** `_deterministic_answer` had only
   a "dump `obligations[:3]`" branch with no reasoner for "is X
   prohibited / high-risk / not?" questions. Added 14 curated
   classification topics (medical transcription, emotion recognition
   workplace + general, social scoring, RBI in public spaces,
   predictive policing, hiring screening, credit scoring, education
   grading, subliminal manipulation, vulnerability exploitation, facial
   recognition databases, biometric categorisation by sensitive
   attributes, Annex III categories 2/6/7/8, Annex I safety component,
   omnibus CSAM) covering the canonical regulatory verdicts. Each topic
   emits a 1-4 sentence verdict + minimal citation set.

### Detector (`_detect_classification_topic`)

Two-pass: question must look like a verdict ask AND match a topic regex.

* **Verdict-ask detector** (`_CLASSIFICATION_QUESTION_RE`): regex matches
  sub-clauses that start with `is` / `are` / `does` and contain a
  classification predicate (`prohibited` / `high-risk` / `minimal-risk`
  / `exempt` / `in scope` / `fall under`), plus a user-asserted-verdict
  branch (`it's (not) high-risk`) for "Confirm X doesn't apply"-style
  framings. Splits the question on `?` `!` `,` `;` `—` `or` `so`
  `then` `therefore` and sentence boundaries (period followed by
  capital letter) so verdict-ask clauses embedded in longer prose are
  caught.

* **Topic regex catalog**: ordered narrow → broad (workplace
  emotion-recognition before general; specific medical-device keywords
  before generic safety-component). First-match wins. Patterns allow
  hyphens (`CV-screening`, `credit-scoring`) so the common compound
  forms route correctly.

### Wire integration

`_seed_classification_obligations` replaces `context.obligations` with
synthetic entries for the topic's refs (each with a unique id), so the
route's citation extraction surfaces exactly the verdict's citation set.
`_two_stage_generate` re-detects the classification topic and skips
Stage-2 LLM polish — the curated verdict prose is already a 1-4
sentence professional answer; LLM rephrasing would risk diluting the
binary verdict the rubric scores against.

### Scope hardening

Added ~50 scope anchors across `_AI_ACT_ANCHORS` + `KEYWORD_TO_ARTICLE`
for prohibited-practice phrases (`facial recognition`, `subliminal`,
`exploit vulnerabilities`, `csam`, `non-consensual intimate`) and
Annex III categories (`critical infrastructure`, `asylum`, `migration`,
`judicial`, `creditworthiness`) so questions about these topics pass
the in-scope gate without an explicit `Art. N` / `Annex N` token.

### Eval scope tightened (Agent B audit response)

The pre-fix `risk_classification` scenarios passed any answer that cited
the right anchor — even one that said "Annex III doesn't apply". Added
verdict-checking predicate helpers (`_verdict_high_risk`,
`_verdict_prohibited`, `_verdict_not_categorically`,
`_classification_verdict_given`, `_rebuts_premise`) with
position-aware logic (positive verdict in the lead sentence overrides
a later carve-out clause). Tightened the 3 baseline
`risk_classification` scenarios with verdict gates AND added 4 new
strict-verdict scenarios mirroring Q2/Q3:

* `risk_doctor_patient_transcription` — Q3 verbatim. Pins all 5
  citation anchors (Article 5/6, Annex I/III, Article 50) AND requires
  `_verdict_not_categorically`.
* `risk_emotion_recognition_general` — Q2 verbatim. Requires nuanced
  verdict + rebuts "always prohibited" framing.
* `risk_social_scoring_prohibited` — must emit "prohibited" verdict.
* `risk_real_time_rbi_prohibited` — must emit "prohibited" verdict.

### Test coverage

* `tests/test_classification_verdicts.py` — 44 new tests covering
  detector unit-level (`_is_classification_question`,
  `_detect_classification_topic`), topic-catalog shape (refs are
  internal form, answer within sentence cap), and end-to-end Q3 wire
  contract (verdict prose, all 5 citation anchors, sentence cap).
* `tests/test_*` (existing) — 277 tests still green; no regressions.

### Results

| Suite | Before | After |
|-------|--------|-------|
| Unit tests | 233 / 233 | 277 / 277 |
| Eval scenarios | 272 / 272 (baseline-biased predicates) | 276 / 276 (tightened) |
| Stress test (54 diverse Qs) | 34 / 54 (63%) | 54 / 54 (100%) |
| Q3 wire response | 1373-char dump, refs `["Article 6", "Annex III"]` | 3-sentence verdict, refs `["Article 5", "Article 6", "Article 50", "Annex I", "Annex III"]` |
| Avg answer sentences | 1.83 | 1.84 (no regression) |
| Avg refs per scenario | 1.56 | 1.60 (more precise) |
| Latency p95 | 5.33ms | 5.45ms |

## 0.1.0 — Initial extraction + round-5 expansion (2026-05-10)

### Origin

Extracted from `Peaky8linders/legit-ai` (CodexAI EU AI Act Path-to-Production compliance platform) at version **1.2.132**.

Module structure preserved 1:1 so file paths in CodexAI's `CLAUDE.md` verification entries still resolve here.

### What's included

* `app/integrations/regenold/` — auth, models, scope, route (verbatim copies).
* `app/engines/graph_rag.py` — two-stage RAG engine (parse → retrieve → generate) with the LLM-or-deterministic fallback.
* `app/data/article_existence.py` — 113 articles + 13 annexes catalog (verbatim).
* `app/data/graph_rag_prompts.py` — engine system prompts (verbatim).
* `app/data/kb.py` — minimal 4-dimension KB stub + 19-article `EC_CHECKER_OBLIGATION_MAP` so the engine's deterministic-fallback path produces useful prose without the full KB.
* `app/routes/regenold.py` — `POST /api/v1/regenold/eu-ai-act/ask` route (verbatim).
* `evals/regenold/` — eval harness with **51 baseline scenarios + 100 multi-conversation + 100 tricky/misleading** = **251 total scenarios** across 28 categories.
* `tests/test_regenold_*.py` — regression tests (verbatim) + new `test_regenold_followup_fixes.py` pinning the two follow-up fixes.
* `docs/partners/regenold/` — integration guide + partner-side client example + Sonnet wrapper setup.

### Stubbed (vs production)

* `app/evidence/store.py` — in-memory recorder. Wire shape preserved (records `tenant_id` / `payload` / `article_ref` / `created_by`); `get_chain(tenant_id=..., limit=...)` returns newest-first records. No durable storage.
* `app/graph/client.py` — Neo4j stub returning `enabled=False`. Forces KB-fallback path. Restore a real Neo4j client to enable graph traversal.
* `app/llm/mistral_provider.py` — REAL httpx wrapper around `POST /v1/chat/completions`. Requires `MISTRAL_API_KEY` env var.
* `app/llm/openai_wrapper_provider.py` — NEW. Routes through `claude-code-openai-wrapper` for Sonnet 4.6 via Claude Max subscription. Detects "Not logged in" sentinel and surfaces as error.

### Two follow-up engineering fixes shipped on top of the extraction

1. **`app/integrations/regenold/scope.py::_live_question_borrows_anchor`** — restructured so STRONG follow-up markers (`what if we re-train`, `what if we retrain`, `how often`, `are these`, `tell me more`, `more details`) fire regardless of question length. The original gate required the live question to be ≤7 alphabetic tokens AND carry a marker; longer process-question follow-ups like "What if we re-train the model quarterly?" got refused as "no anchor" even when the prior assistant turn established Art. 11 unambiguously. Closes 3 multi-conversation eval refusals.

2. **`app/engines/graph_rag.py::_extract_json_object`** — robust JSON cleanup. The original markdown-fence stripper only handled the case where the entire LLM response was wrapped in ` ```json ... ``` `. Claude Sonnet 4.6 in particular ships markdown-fenced JSON with explanatory prose around it; the new helper walks three strategies (direct parse → fenced-block extraction → balanced brace-span fallback) and tolerates trailing commas + `json5`/`jsonc` language tags. Closes 2 simple-question reference-misses where Sonnet's "parsed intent" prose caused the engine to fall through to deterministic-parse with no entity extraction.

Both fixes carry regression tests in `tests/test_regenold_followup_fixes.py` (28 tests covering happy path + new behaviour + failure modes).

### Eval expansion — round 5 (this release)

Authored under this partner-transparency repo and merged into `evals/regenold/scenarios.py::SCENARIOS` via a lazy-import builder so the runner's existing `from evals.regenold.scenarios import SCENARIOS` import picks them up without changes:

* **100 multi-conversation scenarios** in `evals/regenold/scenarios_multiturn_extended.py` (category `in_scope_multi_turn`):
  - A. Pronoun / anaphor carry (12)
  - B. Process follow-ups that exercise the new `how often` / `are these` / `what if we re-train` markers (12)
  - C. Topic-shift inside the same article (12)
  - D. Cross-article carry (12)
  - E. Negative-confirmation traps (12)
  - F. Multi-turn with reference correction (12)
  - G. Long histories — anchors 3+ turns back (14)
  - H. Boundary cases — turn 1 conversational/refused, turn 2 in-scope, turn 3 follow-up (14)

* **100 tricky/misleading scenarios** in `evals/regenold/scenarios_tricky_extended.py` (10 categories × 10 scenarios):
  - `leading_premise` — "Just confirm X doesn't apply" framings
  - `non_existent_article` — out-of-range references in 10 phrasings (`Art. 1500`, `Annex XX(2)(b)`, `Annex 99`, `Art. 0`, `Art. -5`, etc.)
  - `prompt_injection` — DAN, base64, "educational only", system-prompt dump, Unicode homoglyph
  - `sycophancy` — "I'm pretty sure / surely / agree?" confirmation-seeking
  - `citation_poisoning` — bogus refs in turn-1, valid follow-up
  - `role_play_jailbreak` — persona-flip attacks
  - `mixed` — multi-regulation (NIS2, CRA, PLD, DSA, GDPR Art. 22 vs AI Act Art. 22, etc.)
  - `regulation_confusion` — AI Act anchors used for non-AI-Act content
  - `false_authority` — invented citations (`Annex VII Art. 4(2)`, fake Board guideline IDs)
  - `risk_classification` — tier-extraction traps (HR calc as minimal, satire deepfake exempt, etc.)

### Eval result snapshots

| Snapshot | Path | Pass-rate | Notes |
|----------|------|-----------|-------|
| Round 5 deterministic, 251 scenarios | `evals/regenold_results_round5_deterministic_251.json` | 196 / 251 (78.1%) | No LLM — pure deterministic-fallback path. CI-safe. |
| Round 5 Mistral live, 251 scenarios | `evals/regenold_results_round5_mistral_251.json` | TBD — see file | mistral-large-latest via httpx. |
| Round 5 Sonnet 4.6 via wrapper | `evals/regenold_results_round5_anthropic_wrapper.json` | TBD — see file | Claude Max subscription via `claude-code-openai-wrapper`. Requires interactive `login.bat` setup. See `docs/partners/regenold/SONNET_WRAPPER.md`. |

Round 5 builds on rounds 1-4 (run inside parent `legit-ai` repo):

* Round 1 baseline (deterministic, 25 scenarios): 6 / 25 (25%).
* Round 1 post-fix (after scope-filter v1 + extract-referenced-articles + lattice catalog v1): 24 / 25.
* Round 2 (eval expansion to 51 scenarios + KEYWORD_TO_ARTICLE 80-anchor sweep): 50 / 51 (98%).
* Round 2 final + round 3 (after meta-leak preamble strip + sub-paragraph chain capture + multi-article tail regex + injection regression guards): 51 / 51 (100%).
* Round 5 (this release — adds 200 new scenarios): full deterministic + LLM results above.

Snapshot history from rounds 1-3 is preserved at `evals/regenold_results_baseline.json` / `evals/regenold_results_postfix.json` / `evals/regenold_results_round2_final.json` / `evals/regenold_results_round3_final.json` — copied unchanged from the parent repo.
