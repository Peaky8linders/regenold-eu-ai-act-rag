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
| `app/data/kb.py`                      | `EC_CHECKER_OBLIGATION_MAP` — 94 articles/annexes covered.    |
| `app/data/ontology.py`                | Typed registries: Practice ×9, AnnexIIICategory ×8, Phase ×6. |
| `app/data/definitions.py`             | Art. 3 definitions — 30 high-impact terms.                    |
| `app/data/kb_search.py`               | BM25 index over KB + ontology — 133 docs (96 KB + 23 ontology + …). |
| `app/data/kb_xrefs.py`                | Cross-reference graph: regex-extracted + 20 manual edges.     |
| `app/data/graph_rag_prompts.py`       | Stage-1 / Stage-2 system prompts.                             |

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

## Recent code changes (2026-05-12 — round 17 optimization)

### `app/integrations/regenold/models.py`
- `MAX_ANSWER_SENTENCES`: 4 → 3.
- `_MAX_ANSWER_CHARS_SOFT = 600` — drops longest non-cite-anchored sentence
  when answer exceeds 600 chars and >1 sentence remains.
- `_extract_subpoints`: rewritten as a unified single-sweep regex —
  mixed-tail inputs like `Art. 13(1).a` now parse correctly to
  `Article 13.1.a` (was: dropped `.a`).
- `_META_LEAK_SUBSTRINGS`: added hedge markers `"i think"`, `"it appears"`,
  `"arguably"`, `"from my understanding"`, `"based on what i know"`.
- `_ABBREV_END_RE`: accepts opening-quote chars before abbreviations so
  refusal copy containing `(e.g. "Art. 13")` is not mis-split.

### `app/routes/regenold.py`
- `_collapse_parent_refs(refs)` — smallest-cover citation pass. Drops a
  parent ref when a more-specific child exists (`Article 13` dropped when
  `Article 13.2` is present; `Annex III` dropped when `Annex III.1.b` is
  present). Order-preserving.
- `_ref_appears_in_answer` + `_drop_orphan_refs` — phantom-citation
  helper. **Currently disabled** at the call site (round 17 eval showed
  net-negative impact on competition rubric: the judge matches refs to
  gold-set, not to answer prose). Kept in code behind
  `_ORPHAN_ENFORCEMENT_ENABLED = False` for future use.
- `_surface_anchor_citations` — accepts `user_message`; suppresses broad
  `Art. 99` (penalties) and `Art. 113` (entry-into-force) injections when
  a more-specific Article ref is already in candidates AND the user
  message doesn't contain `penalt` / `fine` / `applicable` / `entry into
  force` / `2026` / `2027` / `compliance deadline`.

### `app/engines/graph_rag.py`
- `_detect_role_and_risk_class`: switched from first-match to
  **longest-match** for both role and risk-class phrases. Fixes
  `gpai_systemic` losing to plain `gpai` when the question mentions
  "GPAI model with systemic risk".
- `_RISK_CLASS_PHRASES`: added `"gpai model with systemic risk"`,
  `"general-purpose ai model with systemic risk"` and variants so the
  matrix lookup lands on the systemic row.

### `app/data/kb.py`
- 12 new obligation-map entries — total coverage 60% → 70% of articles:
  - Notified-body lifecycle: Arts. 28, 29, 31, 33, 34.
  - Harmonised standards: Arts. 40, 41, 42.
  - Enforcement: Arts. 78, 88.
  - Annexes IX (large-scale IT systems list), X (registration info).
- All entries hand-written conservative regulatory prose (avg 87 words,
  3–5 sentences). Annex IX explicitly avoids citing transient Council
  Decision / Regulation numbers.

### `app/data/kb_search.py`
- BM25 index extended to also ingest the typed ontology — 96 KB docs +
  23 ontology virtual docs = **133 docs total** (was 82). Each carries a
  `source` tag (`"kb"` / `"ontology"`) for downstream filtering.
- Ontology docs are keyed by their primary article anchor: Practice → its
  citation (e.g. `Art. 5`), AnnexIIICategory → `Annex III`, Phase → its
  first substantive article. Keyword + sub-point text is 3× repeated in
  the indexable string to discriminate against incidental description
  matches (avoids over-firing on phrases like "healthcare deployers").
- `top_articles_by_relevance` collapses to one row per article (max-score
  across docs) preserving the public API contract.

### `app/data/kb_xrefs.py`
- `MANUAL_XREFS` — 20 typed manual edges layered on top of the regex
  extractor. Covers Annex I/II/III/IV/V/VI/VII/XI/XII/XIII ↔ their
  binding articles (e.g. `Annex IV ↔ Art. 11` for technical docs,
  `Annex XIII ↔ Art. 51` for GPAI systemic-risk designation).
- `_lint_manual_xrefs` runs at import time — every endpoint must resolve
  in `ARTICLE_EXISTENCE`.
- `cross_refs_with_reason(article_ref)` returns `(target, reason)` tuples
  so the engine can compose prose like "Annex IV details what Art. 11
  requires" instead of citing both opaquely. The regex-extracted edges
  keep their order in the merged graph — `cross_refs()` is
  backward-compatible.

### `app/data/definitions.py` (NEW)
- Typed Art. 3 definitions catalogue: 30 entries covering AI system, all
  operator roles, lifecycle verbs, conformity-assessment terms, all 5
  biometric definitions, deep fake, serious incident, AI literacy, GPAI
  model / system / systemic risk.
- `DEFINITION_REGISTRY` (dict), `lookup_term`, `search_definitions(top_k)`.

## Eval harness

`evals/regenold/runner.py` runs all 276 scenarios against an in-process
`TestClient(app)`. Three layers — the last two added in round 18 to
align with Davvetas et al. (arXiv:2603.09435v1), "AI Act Evaluation
Benchmark":

- **Binary `passed` flag** — every scenario's `ScenarioCheck` predicate
  must return True. This is the gate.
- **Quality metrics** — reference-format conformance, sentence-cap
  conformance, refs-within-max, latency p50/p95/max. Reported but
  non-gating.
- **Paper-aligned IR metrics** (new in round 18):
  - **Risk-level classification** F1 per class (prohibited / high_risk /
    limited / minimal / refusal). Computed only on scenarios with a
    populated `risk_label`. Currently 18 scenarios labeled (2 prohibited,
    3 high_risk, 13 refusal). Macro F1 = 1.00 on this small sample —
    the rubric is the artefact, not the score; meaningful comparison to
    the paper's 0.85 / 0.87 requires labeling more scenarios.
  - **Article retrieval** weighted precision / recall / F1 against
    `expected_references` gold sets. 25 scenarios with explicit gold
    sets. **Current baseline: P=0.52, R=1.00, F1=0.64** — recall is
    perfect, precision drags from over-citation. This is the
    actionable competition lever the smallest-cover pass targets.

Run via:
```
.venv\Scripts\python.exe -m evals.regenold.runner --json evals/regenold_results_local.json
```

The harness measures TestClient-against-deterministic-fallback latency
(~5–7ms p50). Competition will measure real provider latency — single-
digit ms here is a measurement artefact, not a competition predictor.

## Verification entries

| Property                                              | File:Line                                                                |
| ----------------------------------------------------- | ------------------------------------------------------------------------ |
| 3-sentence answer cap                                 | `app/integrations/regenold/models.py:159` (`MAX_ANSWER_SENTENCES = 3`)   |
| 600-char soft cap                                     | `app/integrations/regenold/models.py` (`_MAX_ANSWER_CHARS_SOFT = 600`)   |
| Smallest-cover citation pass                          | `app/routes/regenold.py:232` (`_collapse_parent_refs`)                   |
| Orphan-citation enforcement DISABLED                  | `app/routes/regenold.py` (`_ORPHAN_ENFORCEMENT_ENABLED = False`)         |
| Anchor-keyword pruning (Art. 99 / 113)                | `app/routes/regenold.py:494` (`_PENALTY_KEYWORDS`)                       |
| Longest-match role/risk detection                     | `app/engines/graph_rag.py:1759` (`_detect_role_and_risk_class`)          |
| BM25 indexes 133 docs (ontology + KB)                 | `app/data/kb_search.py`                                                  |
| Manual xrefs (20 typed edges)                         | `app/data/kb_xrefs.py` (`MANUAL_XREFS`)                                  |
| 30 Art. 3 definitions                                 | `app/data/definitions.py` (`DEFINITION_REGISTRY`)                        |
| Article existence catalog (113 + 13)                  | `app/data/article_existence.py`                                          |

## Round-by-round eval scoreboard (deterministic-fallback)

| Round  | Pass     | p50    | p95    | avg refs | avg sentences | Notes                                      |
| ------ | -------- | ------ | ------ | -------- | ------------- | ------------------------------------------ |
| 15     | 276/276  | 3.04ms | 4.41ms | 2.12     | 2.29          | Pre-optimization baseline (ontology + matrix). |
| 17     | 276/276  | 4.31ms | 7.30ms | 2.12     | 2.04          | Structural optimizations (smallest-cover + 3-sent cap + ontology-in-BM25 + KB stubs + definitions + xrefs). |
| 18     | 276/276  | 6.29ms | 9.08ms | 2.12     | 2.04          | Paper-aligned IR metrics added. Article-retrieval F1=0.64 (P=0.52 R=1.00) — actionable precision lever. |

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
.venv\Scripts\python.exe -m pytest -q             # 430 tests
.venv\Scripts\python.exe -m evals.regenold.runner # 276 scenarios
```

Both must pass clean before any PR. Test files are organised so each
upgrade has its own regression module (`test_reference_parser_fixes.py`,
`test_kb_search_ontology.py`, `test_kb_stubs_filled.py`,
`test_definitions.py`).
