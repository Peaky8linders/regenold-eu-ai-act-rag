# CLAUDE.md — Regenold EU AI Act RAG

This file gives an LLM coding assistant the load-bearing context for this
repo. Read top-to-bottom before making changes.

## What this repo is

A standalone EU AI Act grounded Q&A surface — extracted from the parent
`legit-ai` (CodexAI) codebase as a transparency bundle for the Regenold
competition. The wire contract is a single `POST /api/v1/regenold/eu-ai-act/ask`
endpoint that accepts an OpenAI-style messages array and returns
`{answer, references, reasoning}` per the Regenold rubric.

The system is built to win on six axes the competition scores against:
correctness, references-vs-gold, conciseness-vs-gold, tone, latency, and
multi-turn coherence.

## Architecture (single source of truth)

```
POST /api/v1/regenold/eu-ai-act/ask
        │
        ▼
app/routes/regenold.py
   ├── _build_question_from_history       — flatten last 4 turns
   ├── classify_conversation              — scope gate (refusal or in-scope)
   │      └── app/integrations/regenold/scope.py
   ├── ask_compliance_question            — engine entry
   │      └── app/engines/graph_rag.py
   │             ├── _deterministic_parse — keyword→entities + BM25 fallback
   │             ├── _retrieve_from_kb    — KB + ontology + xrefs
   │             └── _deterministic_answer
   │                    ├── classification verdict (~17 topics)
   │                    ├── role × risk matrix    ← longest-match required
   │                    └── obligation dump
   ├── _surface_anchor_citations          — keyword-derived anchors
   ├── _collapse_parent_refs              — smallest-cover citation pass
   ├── normalise_answer_for_regenold      — 3-sentence + 600-char cap
   └── RegenoldAskResponse
```

## Knowledge surface

| Module                                | Content                                                       |
| ------------------------------------- | ------------------------------------------------------------- |
| `app/data/article_existence.py`       | 113 articles + 13 annexes canonical catalog.                  |
| `app/data/kb.py`                      | `EC_CHECKER_OBLIGATION_MAP` — 113 articles + 13 annexes (full coverage). |
| `app/data/ontology.py`                | Typed registries: Practice ×9, AnnexIIICategory ×8, Phase ×6. |
| `app/data/ontology_mapping_full.py`   | Extended ontology → article mapping (CodexAI port).           |
| `app/data/definitions.py`             | Art. 3 definitions — 31 high-impact terms.                    |
| `app/data/article_requirements_full.py` | Per-article requirement schema (CodexAI port).              |
| `app/data/role_obligations.py`        | Role × risk obligation matrix (provider/deployer/importer/distributor). |
| `app/data/agentic_taxonomy.py`        | Four-axis agentic compound-risk taxonomy.                     |
| `app/data/severity.py`                | Severity bands for downstream impact assessment.              |
| `app/data/kb_search.py`               | BM25 index over KB + ontology — ~165 docs (post-full-coverage). |
| `app/data/kb_xrefs.py`                | Cross-reference graph: regex-extracted + 20 manual edges.     |
| `app/data/graph_rag_prompts.py`       | Stage-1 / Stage-2 system prompts.                             |

## Persistence / audit chain

| Module                                | Content                                                       |
| ------------------------------------- | ------------------------------------------------------------- |
| `app/evidence/store.py`               | `get_evidence_store()` — singleton. Backends: in-memory (default), Postgres (`postgresql://` DSN), SQLite (`sqlite://` DSN). Hash-chained tamper-evident audit. |
| `app/evidence/models.py`              | `EvidenceEntry`, `EvidenceEntryType`, `ChainStatus`.          |
| `app/graph/client.py`                 | Neo4j client (lazy import — skipped when no driver / DSN).    |
| `app/graph/ontology.py`               | Graph-side ontology resolver.                                 |
| `app/graph/reasoning.py`              | Multi-hop reasoning over the graph.                           |
| `app/llm/intent_classifier.py`        | Intent-driven anchor narrowing (Claude Max wrapper).          |

## Hard rules — don't break these

1. **Reference format is strict.** Only `Article N(.subpoint)*` (Arabic) or
   `Annex X(.subpoint)*` (Roman, uppercased). Validated by
   `_ARTICLE_OUTPUT_RE` / `_ANNEX_OUTPUT_RE` in
   `app/integrations/regenold/models.py`. Never emit `Art. 13`, `Annex 3`,
   `Article 13(1)`, `Annex III(2)`, or `Article III` on the wire.
2. **`MAX_ANSWER_SENTENCES = 3`**, plus a soft 600-char cap that drops the
   longest non-cite-anchored sentence first. Don't relax this without
   measuring conciseness delta.
3. **No new classification topics for the 3 PDF example questions**
   (technical-doc hardware / emotion-recognition prohibition / doctor-
   patient transcription). The competition rubric measures generalisation;
   topic-specific overfit will be penalised. Add new topics only when
   they don't track the example list.
4. **KB stubs ship faithful regulatory prose, never speculation.** A
   confidently-wrong summary loses more than a missing one.
5. **`ARTICLE_EXISTENCE` is the lint floor** — every emitted citation
   must resolve here. The `tests/test_kb_consistency.py` suite enforces
   this across `EC_CHECKER_OBLIGATION_MAP`, `_KEYWORD_ENTITY_MAP`,
   `KEYWORD_TO_ARTICLE`, `_CLASSIFICATION_TOPICS`, the ontology
   registries, the xref graph (both regex and manual), and the
   definitions registry.

## Recent code changes (2026-05-15 — rounds 19–23 since 18.1)

### Round 19 — explicit-anchor pruning (591f0f5)
`app/routes/regenold.py::_surface_anchor_citations` learns to drop low-evidence
anchors when an **explicit** anchor (e.g. user said "Article 13") is present.
Lifts Article-retrieval **F1 +0.067 (P 0.52 → 0.61, R holds at 1.00)**.

### Round 20 — intent-driven anchor narrowing (dcfa031)
`app/llm/intent_classifier.py` — Claude Max wrapper that infers query intent
(definitional / obligational / classification / interpretive) and prunes
anchors that don't match that intent. Drops "Article 12 — logs" off a
definitional question about "providers" even though both keywords matched.

### Round 21 — CodexAI port (a19c2de + 4a5371f)
Audit / graph / KB stubs replaced with full CodexAI implementations.
- `app/data/kb.py`: **full coverage** — 35 newly-ported articles + 31 definitions.
- `app/graph/`: full Neo4j-backed reasoning module (lazy-imported, skipped without driver).
- `app/evidence/store.py`: hash-chained audit (in-memory + Postgres + SQLite).
- `app/data/role_obligations.py`, `agentic_taxonomy.py`, `severity.py`: new typed registries.

### Round 22 — Postgres audit persistence (7ed6ef4)
Full question + answer persisted to the audit chain (was previously just a hash).
Enables forensic replay + offline metric recomputation against historical queries.

### Round 23 — SQLite audit backend (500c1d3)
Stdlib-only `sqlite://` backend gated on the `DATABASE_URL` env var. Lets us
ship a durable audit chain without requiring Postgres at every deployment.

## Round 24 — Reproducible competition benchmark (2026-05-15)

### `evals/bench/` — new directory
- `dataset.py` — fetches `davidath/ai-act-evaluation-benchmark` (qa_pairs.json +
  scenarios.json) and pins it to a local SHA-256 (137 QA + 339 scenarios).
  Re-runnable offline once cached. Re-fetch only when upstream SHA changes.
- `runner.py` — runs the dataset against the Regenold wire (`TestClient`
  over `POST /api/v1/regenold/eu-ai-act/ask`). Scores **all 8 rubric axes**:
  Ans. Correctness (Loose / Strict), Ans. Conciseness, Ref. Correctness
  (Loose / Strict), Ref. Conciseness, Latency, Regulatory Tone. Plus a
  multi-turn coherence pass over chained scenarios.
- `metrics.py` — per-axis scoring functions (token-Jaccard for loose
  correctness, fraction-of-gold-tokens for strict, quadratic-length-ratio
  for conciseness, regulator-voice heuristic for tone).
- `storage.py` — writes results to (a) JSON sidecar at
  `evals/bench/results/<label>.json`, (b) SQLite ledger
  `evals/bench/results/ledger.sqlite`, (c) audit chain via
  `get_evidence_store()` (Postgres when `DATABASE_URL` is set, SQLite
  with `sqlite://` DSN, in-memory otherwise) under
  `EvidenceEntryType.benchmark_run`.
- `compare.py` — side-by-side diff between two labels.

### Round 24 engine optimisations
- **`app/engines/scenario_classifier.py`** (new) — fast path for
  structured "We are a {role}…" scenarios. Risk-pyramid markers map
  intended-use phrases → prohibited / high-risk / limited / minimal,
  then bolt on role-specific obligation articles. Unicode-normalises
  the davidath dataset's non-breaking hyphens.
- **`app/engines/graph_rag.py`** — definitional routing for Articles 1
  (purpose), 2 (scope/who-must-comply), 3 (definitions), 18, 26, 43,
  44, 56, 57, 60, 70, 90, 95, 96. Bare "ai office" trigger narrowed
  (was over-routing to Art. 64 on 10 QA questions).
- **`app/integrations/regenold/models.py`** — `_strip_kb_stub_label`
  drops the leading `Art. N:` / `Annex IV:` prefix from KB-stub
  sentences AFTER the soft-cap pass. Cuts QA pred-len median 499→480
  chars without breaking the cite-anchored-sentence-preservation logic.

### Round 24 — Competition rubric scorecard (476 items)

| Axis                       | Baseline | Optimised | Δ        |
| -------------------------- | -------- | --------- | -------- |
| Ans Correctness (Loose)    | 0.0587   | 0.0755    | +0.017 ✓ |
| Ans Correctness (Strict)   | 0.1524   | 0.1757    | +0.023 ✓ |
| Ans Conciseness            | 0.4078   | 0.4118    | +0.004 ✓ |
| Ref Correctness (Loose)    | 0.2839   | 0.3471    | +0.063 ✓ |
| Ref Correctness (Strict)   | 0.2365   | 0.2969    | +0.060 ✓ |
| Ref Conciseness            | 0.3846   | 0.3887    | +0.004 ✓ |
| Regulatory Tone            | 1.0000   | 1.0000    |  0.000   |
| Latency p50 (ms)           | 4.84     | 4.36      | -0.48  ✓ |
| Latency p95 (ms)           | 7.26     | 5.67      | -1.59  ✓ |
| Multi-turn coherence rate  | 0.80     | 1.00      | +0.20  ✓ |

Every axis improved or held steady. The biggest wins are on reference
correctness (the davidath dataset's primary scoring axis) and multi-turn
coherence (0.80 → 1.00 perfect on the 20-scenario probe).

## Round 25 — Ansvar-Systems corpus integration (2026-05-15)

### `app/data/eu_ai_act_corpus.py` (new, generated)
Ports the EUR-Lex AI Act corpus from
[Ansvar-Systems/EU_compliance_MCP](https://github.com/Ansvar-Systems/EU_compliance_MCP)
(Apache 2.0; regulation text itself is public-domain under Article 297 TFEU):

- 126 articles + annexes — **full EUR-Lex prose** for every entry.
- **68 Art. 3 definitions** (was 31 hand-curated).
- 180 recitals indexed by number.
- 8 severity-rated **pitfalls** anchored to specific articles.
- 7-tier **proportionality matrix** (prohibited / high-risk Annex I / high-risk
  Annex III / limited / GPAI standard / GPAI systemic / minimal).
- 10 sector-applicability rules with `basis_article` + `confidence`.

Regenerated via `py -3.12 scripts/generate_ansvar_corpus.py`; pinned to
upstream SHAs in the module header.

### `app/data/kb_search.py` — BM25 corpus expansion + source-weighted scoring
- Corpus 133 → 348 docs: 126 full-prose article docs + 68 definition virtual
  docs alongside the existing KB summary + ontology rows.
- Source-aware weighting: `kb`=1.0, `ontology`=1.0, `corpus`=0.6, `definition`=0.8.
  Stops long EUR-Lex prose from over-firing on scenario questions where a
  tight hand-authored summary should win.

### `app/engines/scenario_classifier.py` — widened markers
Verb-stem markers (`"manipulat"`, `"exploit"`, `"over-donat"`) catch
phrasings like "manipulates low-income families" that the literal forms
missed. Added `"economic vulnerability"`, `"persuasion tool"`, etc.

### Round 25 — Scorecard vs Round 24 (476 items)

| Axis                       | Round 24 | Round 25  | Δ        |
| -------------------------- | -------- | --------- | -------- |
| Ans Correctness (Loose)    | 0.0755   | 0.0757    | +0.000   |
| Ans Correctness (Strict)   | 0.1757   | 0.1773    | +0.002 ✓ |
| Ans Conciseness            | 0.4118   | 0.4074    | -0.004   |
| Ref Correctness (Loose)    | 0.3471   | 0.3619    | **+0.015 ✓** |
| Ref Correctness (Strict)   | 0.2969   | 0.3093    | **+0.012 ✓** |
| Ref Conciseness            | 0.3887   | 0.3936    | +0.005 ✓ |
| Regulatory Tone            | 1.0000   | 1.0000    |  0.000   |
| Latency p50 (ms)           | 4.36     | 4.76      | +0.40    |
| Latency p95 (ms)           | 5.67     | 6.11      | +0.44    |
| Multi-turn coherence rate  | 1.00     | 1.00      |  0.000   |

QA reference correctness lifted +0.029 (loose) / +0.017 (strict);
scenarios lifted +0.009 (loose) / +0.011 (strict). Tone and multi-turn
coherence held at 1.0. Latency cost ~0.4 ms p50 from the 2.6× larger
BM25 corpus — well within rubric budget.

Cumulative since baseline (Round 23 → Round 25): Ref Correctness Loose
**+0.078 (0.284 → 0.362)**, Strict **+0.073 (0.236 → 0.309)**, Ans
Correctness Strict **+0.025 (0.152 → 0.177)**, multi-turn coherence
**+0.20 (0.80 → 1.00)**, tone held at 1.0, latency held under 5 ms p50.

## Eval scorecard (deterministic-fallback, local 276-scenario suite)

| Round  | Pass     | p50    | p95    | avg refs | avg sentences | Retrieval F1 | Notes |
| ------ | -------- | ------ | ------ | -------- | ------------- | ------------ | ----- |
| 15     | 276/276  | 3.04ms | 4.41ms | 2.12     | 2.29          | —            | Baseline. |
| 17     | 276/276  | 4.31ms | 7.30ms | 2.12     | 2.04          | —            | Structural upgrades. |
| 18     | 276/276  | 6.29ms | 9.08ms | 2.12     | 2.04          | 0.64         | Paper-aligned metrics. |
| 18.1   | 276/276  | 6.61ms | 10.07ms| 2.12     | 2.04          | 0.64         | Fixes: Art. 113 protect, BM25 tokenizer. |
| 19     | 276/276  | 6.8ms  | 10.5ms | 2.10     | 2.04          | **0.71**     | Explicit-anchor pruning (+0.067 F1). |
| 21     | 276/276  | 7.2ms  | 11.4ms | 2.10     | 2.04          | 0.71         | Full CodexAI KB ports — articles 1–113 covered. |

Δ on the local rubric is modest (-11% sentences, +12% p50 latency) because
the local harness is binary substring-matched and already saturated. The
upgrades target the **competition rubric** axes the local harness can't
score against (citation precision-vs-gold, conciseness-vs-gold-length,
multi-turn coherence). The structural improvements (ontology in BM25, 12
new KB stubs, definitions index, manual xrefs, longest-match role
detection, smallest-cover pass) are de-overfitted from the 3 PDF example
questions.

## Non-goals / things to skip

- Vector embeddings / dense retrieval — the corpus is small and
  deterministic; BM25 + curated keyword + ontology covers it.
- Memory / RAG over user history — the API is stateless per turn,
  scope.py handles coref via anchor borrowing.
- Cross-encoder reranker — overkill for 133 docs; BM25 ranks well enough
  and the top-k cap is small.
- Streaming responses — out of competition scope; the wire returns one
  JSON.

## Testing

```
.venv\Scripts\python.exe -m pytest -q             # ~480 tests
.venv\Scripts\python.exe -m evals.regenold.runner # 276 local scenarios
.venv\Scripts\python.exe -m evals.bench.runner    # reproducible competition benchmark
```

All three must pass clean before any PR. Test files are organised so
each upgrade has its own regression module (`test_reference_parser_fixes.py`,
`test_kb_search_ontology.py`, `test_kb_stubs_filled.py`,
`test_definitions.py`, `test_intent_classifier.py`,
`test_intent_pruning_integration.py`, `test_sqlite_audit_store.py`).
