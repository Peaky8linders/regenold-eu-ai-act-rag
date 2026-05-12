# Changelog

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
