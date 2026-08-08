# CLAUDE.md — Regenold EU AI Act RAG

Load-bearing context for an LLM coding assistant. Read top-to-bottom before
making changes. Every number here was re-measured in R324; the per-round
engineering log lives in **[`docs/ROUNDS.md`](docs/ROUNDS.md)** (112k words —
search it, don't read it).

## What this repo is

A standalone EU AI Act grounded Q&A surface, extracted from the parent
`legit-ai` (CodexAI) codebase as a transparency bundle for the Regenold
competition. The wire contract is a single
`POST /api/v1/regenold/eu-ai-act/ask` that accepts an OpenAI-style messages
array and returns `{answer, references, reasoning}`.

Scored on six axes: correctness, references-vs-gold, conciseness-vs-gold, tone,
latency, multi-turn coherence.

## Architecture

```
POST /api/v1/regenold/eu-ai-act/ask
        │
        ▼
app/routes/regenold.py
   ├── _build_question_from_history       — flatten recent turns
   ├── classify_conversation              — scope gate (refusal or in-scope)
   │      └── app/integrations/regenold/scope.py
   ├── ask_compliance_question            — engine entry
   │      └── app/engines/graph_rag.py → _graph_rag_impl.py
   │             ├── _deterministic_parse — keyword→entities + BM25 fallback
   │             ├── _retrieve_from_kb    — KB + ontology + xrefs
   │             ├── _deterministic_answer — verdict / role×risk / obligations
   │             └── _two_stage_generate  — Stage-2 LLM polish (live only)
   ├── _surface_anchor_citations          — keyword-derived anchors
   ├── _collapse_parent_refs              — smallest-cover citation pass
   ├── normalise_answer_for_regenold      — sentence + char caps
   └── RegenoldAskResponse
```

The Neo4j graph contributes **non-citable Stage-2 context** via
`app/engines/kg_context.py` — provision hierarchy, sub-point carve-outs, the
deontic layer, recital anchors. It is additive: never a ranker, never a wire
citation (see hard rule #10).

## Knowledge surface — counts measured 2026-08-09

| Module | Content |
| ------ | ------- |
| `app/data/article_existence.py` | **126** canonical refs = 113 articles + 13 annexes. The lint floor. |
| `app/data/kb.py` | `EC_CHECKER_OBLIGATION_MAP` — **131 entries** covering all 126 provisions (some articles carry multiple stubs). `KB_VERSION = 2024.1689.v18`. |
| `app/data/ontology.py` | `PRACTICE_REGISTRY` **×8**, `ANNEX_III_REGISTRY` **×8**, `PHASE_REGISTRY` **×4**. |
| `app/data/definitions.py` | **68** Art. 3 definitions. |
| `app/data/provision_text.py` | Verbatim resolver: article / paragraph / point / sub-point / annex item, section-aware (R323). |
| `app/data/official_eu_ai_act.py` | Pinned EUR-Lex text, CELEX `32024R1689` (**pre-Omnibus**), 180 recitals. |
| `app/data/kb_search.py` | BM25 index — **345 docs**. |
| `app/data/kb_xrefs.py` | Cross-reference graph: **149 core** edges, **249 full**. |
| `app/data/eu_ai_act_tree.py` | **1,412**-node document tree. |
| `app/data/role_obligations.py` | Role × risk obligation matrix. |

⚠ Older round entries quote `~165` / `348` / `347` BM25 docs, `Practice ×9`,
`Phase ×6`, and a `1,426`-node tree. **All four are stale** — the table above is
measured.

## Persistence / graph / LLM surfaces

| Module | Content |
| ------ | ------- |
| `app/evidence/store.py` | `get_evidence_store()` singleton. Backends: in-memory (default), Postgres (`postgresql://`), SQLite (`sqlite://`). Hash-chained tamper-evident audit. |
| `app/evidence/models.py` | `EvidenceEntry`, `EvidenceEntryType`, `ChainStatus`. |
| `app/graph/client.py` | Neo4j client (lazy import; disabled without a driver / DSN). `health_check()` treats an empty ping as unhealthy (R323). |
| `app/graph/embedded_graph.py` | R121 in-process SQLite property graph — the no-external-service backend. |
| `app/graph/timeouts.py` | `resolve_graph_timeout_ms` — one budget for every graph read. |
| `app/engines/kg_context.py` | The graph's contribution to an answer: hierarchy, sub-points, deontic layer, recitals. Non-citable, request-memoised. |
| `scripts/seed_neo4j_kb.py` | The seeder. `SEED_VERSION` gates the boot auto-seed — bump it or a fix never reaches production. |
| `app/llm/intent_classifier.py` | Stage-0 intent narrowing (wrapper or Groq). |

## Hard rules — don't break these

1. **Reference format is strict.** Only `Article N(.subpoint)*` (Arabic) or
   `Annex X(.subpoint)*` (Roman, uppercase). Never `Art. 13`, `Annex 3`, or
   `Article III` on the wire.
   ⚠ The *validator* is laxer than this rule: `_ANNEX_OUTPUT_RE` /
   `_ARTICLE_OUTPUT_RE` in `models.py` accept any alphanumeric sub-token, so
   `Annex III.foo.bar` and `Article 6.derogation` pass. `Annex III.4.employment`
   has actually shipped. Treat the rule as the contract, not the regex.
2. **Answer length is capped**, but the effective cap is env-dependent:
   `MAX_ANSWER_SENTENCES = 3` in code, `REGENOLD_MAX_ANSWER_SENTENCES` overrides
   it, and `REGENOLD_ANSWER_NO_CAP` (default ON since R308) removes both the
   sentence and soft-char caps on the live Stage-2 path. R320 measured the
   uncap costing **−1.1 to −2.2 pp Overall** on Answer-Conciseness — the ONE
   axis we lead. Any cap must be SENTENCE-only: the char cap deletes
   verdict-first leads.
3. **No new classification topics for the 3 PDF example questions** (technical-doc
   hardware / emotion-recognition prohibition / doctor-patient transcription).
   The rubric measures generalisation; topic-specific overfit is penalised.
4. **KB stubs ship faithful regulatory prose, never speculation.** A
   confidently-wrong summary loses more than a missing one.
5. **`ARTICLE_EXISTENCE` is the lint floor** — every emitted citation must
   resolve there. `tests/test_kb_consistency.py` enforces it.
   ⚠ It cannot catch a *wire-legal* fabrication: a foreign instrument's
   Article 5 collides with AI Act Article 5 and passes the lint (R323).
6. **A/B (`ab_judge`) IS THE MERGE GATE — davidath is NOT.** See Validation
   policy. Never ship an answer / Stage-2 / prompt / reference / scope change on
   "davidath byte-identical" alone.
7. **`--qa-only` is NOT a gate for a reference change — use the FULL 476.**
   davidath QA gold is single-article (mean 1.00 refs/row) and structurally
   cannot show a chain-dropping defect; scenarios carry mean **9.88**. R318
   measured a top-5 cap as FREE on a 132-row probe and it destroyed **421 gold**
   on scenarios.
8. **RECALL GUARD — a reference change must drop ZERO gold.** R142.1's
   positional clamp lost a live pairwise judge **11-0 (p=0.001)**. Measure
   `gold_dropped` FIRST; non-zero is a rejection, not a trade-off. "Head-level
   recall is invariant" is NOT sufficient — gold and the grounded judge both
   score at SUB-POINT grain.
9. **ABSENT IS NOT ZERO.** Pre-R302 judged runs emit `wrong_refs: []` even when
   the row's prose names the over-citation — **349 of 547 rows (63.8%)** lack
   the field. Filter to usable runs before computing any rate.
10. **The graph is ADDITIVE context only** — never a ranker, never a wire
    citation. R252 demoted graph-primary retrieval because the blunt
    `obligations_for_risk_level` dump buried the operative article.

## Validation policy — `ab_judge`, not davidath, is the merge gate

**Operator rule (2026-06-30):** ship on the live pairwise
`evals.harness.ab_judge`. davidath is a **regression guard only** — it runs
`provider=cli` with no Stage-2 and token-overlap metrics that R99.2/R139
measured as *diverging* from the live judge. "davidath byte-identical" means
**inert on the bench**, not "no regression" and never "a win".

Gate for any change that can move an answer, a reference, the tone, or a scope
decision:

1. **Live verification first** — probe the real failing case. A reference /
   Stage-2 / scope change MUST be seen working LIVE.
2. **`evals.harness.ab_judge`** — position-swapped pairwise, baseline-OFF vs
   branch-ON, per-axis win-rate + sign test. **This is the merge gate.**
   For a reference change prefer **`evals.harness.easyhard_ab`**: it scores ref
   conciseness as a count-ratio against gold, which `ab_judge` lacks — that gap
   is how R142.1 slipped through.
3. davidath + 276-runner + OOS probe — cheap regression guards only.

Env-gate every such change (default-ON in code) so `ab_judge` can A/B OFF↔ON,
and keep the off-switch for instant rollback.

## Current baseline — the single authoritative source

Measured at `8cd05a8` (2026-08-09), deterministic env
`OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0`.

**Grade every run against THIS block, never against a number in `docs/ROUNDS.md`.**

| davidath | Ans Loose | Ans Strict | Ans Conc | Ref Loose | Ref Strict | Ref Conc | Tone |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **OVERALL (476)** | 0.1884 | **0.3545** | 0.6143 | **0.5971** | **0.4748** | 0.4316 | 1.0 |
| QA (137) | 0.1407 | 0.4072 | 0.1961 | 0.8394 | 0.5536 | 0.4390 | 1.0 |
| Scenarios (339) | 0.2076 | 0.3332 | 0.7833 | 0.4992 | 0.4430 | 0.4287 | 1.0 |

Multi-turn **20/20 coherent**.

Other gates: `evals.regenold.runner` **255/255**, RISK_F1 macro **1.00** ·
OOS probe (`--oos-suite all`, 51 rows) **49 pass, 0 scope leaks** (2 known
`adjacent_eu` soft fails) · full `pytest` **87 pre-existing failures**, all the
documented `provider=cli` Stage-2 env artifact.

⚠ An older pin of **0.4079 / 0.5543** appears in the log — it is stale.

## Where we stand

* **Three separate scorecards. Never conflate them.** (a) The OFFICIAL regenold
  report — we beat 0 baselines, `Overall` is a **geometric mean** so the worst
  axis dominates, and **Answer-Conciseness is the only axis we lead** (zero
  headroom). (b) **davidath = regression guard**. (c) The **frontier
  head-to-head** = the "are we SOTA?" measure.
* **Frontier standing** (132 paired rows): we win Ref Loose and keyword recall;
  we lose **Ref Strict and Ref Conciseness — the same defect, over-citation**.
* **Over-citation is the whole remaining gap.** An oracle dropping every
  non-gold ref gains Ref Strict **+0.215** / Ref Conciseness **+0.229** at
  unchanged recall. Nothing has captured any of it.
* **The knowledge graph is live and used.** Aura `0644b854`, seed
  `2026-08-08-r323-annex-sections`, 1758 nodes / 1979 edges, 113/113 articles +
  13/13 annexes byte-identical to the pinned corpus. A live request reads 7
  Cypher shapes across Article / Annex / Paragraph / Point / **SubPoint** /
  Recital / **Practice** / **AnnexIIICategory** / **OperatorRole** /
  **LifecyclePhase**.

## Do not re-propose — measured and dead

Each of these was built or simulated and **failed on measurement**. The
underlying evidence is in `docs/ROUNDS.md`.

**Over-citation trimming (R317 killed five families):**
* Article-**identity blocklists** — the same head is gold on one question and
  wrong on another (`Article 6` wrong 21 / gold 22).
* **Positional / top-N clamps** — top-2 drops 23 gold. R142.1 lost a live
  pairwise **11-0, p=0.001**.
* **Prose-driven pruning** — a structural no-op: **86%** of wrong refs ARE
  described in the prose.
* **Ask-type × role exclusivity** — classifier-fragile; two competent
  implementations disagreed on 30% of rows.
* **Chapter-III tier exclusivity** — clean on five gates, then dropped **67
  gold across 40 scenarios** on the full 476.
* **Any global top-k cap** — looked free on two recorded arms, destroyed **421
  gold** on davidath scenarios.
* Lesson: **work the RANKER, not the trimmer.**

**Retrieval / graph:**
* **Graph-primary retrieval** (undoing R252) — the blunt risk-tier dump buries
  the operative article.
* **`REGENOLD_GRAPH_FUSE_SLACK`** — slack=2 destroyed gold (`st_v4_002` went
  from a perfect `['Article 5']` to three wrong refs).
* **Prose-mined recital→article edges** — only ~4 of 32 candidates are genuine
  AI Act refs; the rest point at GDPR/MDR/TFEU. Hallucination.
* **RRF fusion / dense rerank / paragraph extraction** — measured washes three
  times (R31, R69, R99). davidath is BM25-saturated.
* **Neural NLI citation verification** — ROC-AUC **0.585** vs the free lexical
  scorer's **0.749**, and 235× slower. Do not add torch.
* **Foreign-regulation full text in the retrieval corpus** — >2× the corpus,
  every doc non-citable, and R319 already demonstrated crowding-out.

**Model / latency:**
* **Fast mode** and **extended-thinking budget** are NOT latency levers — both
  measured washes. ~half of live latency is a fixed CLI-wrapper floor (a
  5-token request costs 12-17 s).
* **Opus-for-all Stage-2** — a wash; it trades a 1-row correctness lean for a
  lean against conciseness and tone.
* **`REGENOLD_STAGE2_SIMPLE_SKIP`** — refs 0.75 → 0.47.

**Method:**
* **R277's "minimal composer" result is a NULL EXPERIMENT** — both arms were
  identical at the model, because the swap was inside the system prompt the
  wrapper drops. Do not cite it as evidence that prompt volume is harmless.
* **The Cappelli et al. (2026) paper's 7 optimisations** — none buildable; the
  authors built no retrieval system and their failure mode is UNDER-citation,
  the inverse of ours.

## Gotchas that have each cost a session

* **The Stage-2 SYSTEM prompt is dropped by the Claude Max wrapper — 0% of
  requests see it.** Prompt fixes MUST go in the Stage-2 **user** message.
  Proven with a French-instruction probe: system slot ignored, user slot obeyed.
* **`railway.toml [deploy.envs]` has NEVER applied** — Railway's `[deploy]`
  schema has no `envs` key. Bake config as **code defaults**.
* **A `git worktree` baseline has no `.env`** — the denoiser / topic-filter /
  safety-gate cluster changes behaviour on `GROQ_API_KEY`. Full-suite failure
  diffs must be run **in place** (measured 63 vs 92 failures on the same commit).
* **Scripts don't load `.env`.** `scripts/seed_neo4j_kb.py` and
  `scripts/fetch_lawstronaut_provenance.py` are pure-stdlib — export the vars or
  they exit 1. The seeder prints its error at the TOP, so **never `tail` it**.
* **A code fix to `provision_text` is not live until you re-seed AND bump
  `SEED_VERSION`** — otherwise the boot hook hits `skip-current` and production
  keeps serving the old data. R323 found the graph serving *wrong law* this way.
* **`load_dotenv()` resolves relative to the calling script** — a probe outside
  the repo silently measures a DISABLED graph. Assert
  `get_graph_client().enabled` before drawing conclusions.
* **Check the key form before reporting a missing surface.** Annex node ids are
  `annex_IV` (uppercase Roman); `ARTICLE_EXISTENCE` keys articles as **`Art. N`**,
  not `Article N`. Both faked "empty surface" alarms in R323.
* **Console `�` on Windows is cp1252 rendering, never data.** Verify by codepoint.
* **`/healthz/llm` lies** — verify the wrapper with a real POST.
* **Never run two wrapper-bound jobs concurrently.**
* **The instrument trap.** Three times an authoritative-looking instrument was
  structurally blind to the decision: R110.1 (davidath is BM25-saturated, so a
  gate reads byte-identical *because* it is a no-op there), R318 (a
  deterministic reference measurement is not a valid proxy once Stage-2 makes
  refs a function of the answer), R319 (the judge rendered `answer[:1400]`
  against a corpus whose mean answer is 1413 chars). **Before trusting a
  measurement, ask: can this instrument physically observe the thing I am
  deciding?**
* **Small-n live A/Bs cannot resolve reference axes.** Two runs with an
  IDENTICAL baseline arm changed 20/40 rows' refs and sign-flipped all three
  reference axes. Use full n with repeats, or a deterministic offline sim.

## Env flags that matter

Defaults are the CODE default (what a fresh deploy gets). Verify in code before
relying on any of these — this project flip-flops on several.

| Flag | Default | Effect |
| --- | --- | --- |
| `P2P_GRAPH_RAG_PROVIDER` | `auto` | `cli` (deterministic) / `anthropic` / `openai_wrapper` |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | **ON** | Stage-2 polish master gate |
| `REGENOLD_ANSWER_NO_CAP` | **ON** | removes sentence + char caps live (see hard rule #2) |
| `REGENOLD_KG_CONTEXT` | **ON** | graph context into Stage-2 |
| `REGENOLD_KG_MAX_CHARS` | 16000 | total graph-context ceiling (R323) |
| `REGENOLD_GRAPH_BACKEND` | `neo4j` | `embedded` = in-process SQLite, no external service |
| `REGENOLD_GRAPH_TIMEOUT_MS` | **750** | cold round-trip measured 524 ms, warm 31 ms |
| `REGENOLD_GROUNDING_TEXT` | ON | verbatim paragraphs of cited refs into Stage-2 |
| `REGENOLD_SUFFICIENT_CONTEXT` | ON | bounded multi-hop (R319 reverted the OFF flip) |
| `REGENOLD_REF_PARTITION` | **OFF** | R300 — it deleted gold references |
| `REGENOLD_COMPLETENESS_VERIFIER` | **OFF** | R306 — it appended inverted law |
| `REGENOLD_FINAL_REF_CLAMP` | **OFF** | R142.1 — lost the pairwise judge 11-0 |
| `REGENOLD_LIVE_SENTENCE_CAP` | **OFF** | a trade, not a win (correctness −0.143) |
| `NEO4J_AUTO_SEED` | on unless `0` | boot hook seeds a fresh instance automatically |

## LLM provider story

`P2P_GRAPH_RAG_PROVIDER` selects one of three mutually exclusive paths:

| Value | Behaviour | Setup |
| --- | --- | --- |
| `cli` / `auto`* | Pure deterministic, no LLM, sub-10 ms. **This is what davidath runs.** | none |
| `anthropic` | Stage-1 + Stage-2 via Anthropic SDK (per-token billing) | `P2P_GRAPH_RAG_API_KEY=sk-ant-…` |
| `openai_wrapper` | Stage-1 + Stage-2 + Stage-0 intent via the local Claude Code Max wrapper | wrapper on `127.0.0.1:8000` + `OPENAI_API_BASE` |

`* auto` → `anthropic` when a key is set, else `cli`. Every sub-pipeline falls
back to a deterministic equivalent on error, so the route never 500s on a downed
LLM.

The wrapper lives at `D:\Claude Projects\claude-code-openai-wrapper` (not this
repo) and bills the flat Max subscription. Evals MUST use it, not SDK-direct.

```bash
$env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "dummy"
$env:P2P_GRAPH_RAG_PROVIDER = "openai_wrapper"
```

## Testing

```bash
# deterministic env for every gate
OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0

python -m pytest tests/ -q                                    # full suite
python -m evals.bench.runner                                  # davidath 476
python -m evals.regenold.runner                               # 276 scenarios
python -m evals.regenold.runner_v2 --local --probe-oos --oos-suite all
python -m evals.harness.ab_judge                              # THE MERGE GATE
```

## Open, ranked

1. **Over-citation** — the whole remaining frontier gap. Work the ranker.
2. **The Neo4j vector layer is unused** — 7 VECTOR indexes and ~1,490
   embeddings with **zero consumers** (`grep 'db.index.vector'` returns
   nothing). Largest built-but-unwired capability.
3. **A bounded Sufficient-Context hop** — the gate is ON but its added content
   measures **2.5% gold precision** with crowding-out demonstrated. Cap the
   merged obligations; require term overlap with the ORIGINAL question.
4. **The official answer-side gap** (`AnsL − RefL = −13.1`) is untouched.
5. **Foreign-instrument nodes** — registry ready (67/67 CELEX empirically
   verified in `.evalout/celex_verified.json`); seeding not written.

---

**History:** [`docs/ROUNDS.md`](docs/ROUNDS.md) — every round entry, verbatim.
**Handoff:** [`.planning/R323-HANDOFF.md`](.planning/R323-HANDOFF.md).
