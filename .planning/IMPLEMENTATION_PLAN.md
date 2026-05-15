# Round 31 — High-Precision RAG Architecture integration

**Source spec**: `EU_AI_Act_High_Precision_RAG_Architecture.pdf` (CLARA + TAI Scan
+ Davvetas 4-task framework whitepaper).
**Companion docs**: Davvetas et al. 2026 benchmark paper, 2026 Digital Omnibus
text, Regenold competition rules, EU AI Act guide.

## What lands this round

The architecture PDF is a 7-layer prescription; we land **the 3 layers with the
largest rubric impact** in this PR and document the rest as follow-ups.

### Layer D (Hybrid Retrieval — dense vector path)  →  **turboquant_index.py**

The current `vector_rerank.py` is Linux-only (turbovec). We add a
Windows-friendly companion: `app/engines/turboquant_index.py`. It uses

* **TF-IDF + Truncated SVD-128** (pure NumPy) for deterministic, stdlib-only
  embeddings — captures the topical / paraphrase semantics that BM25 misses
  without pulling sentence-transformers (which would force torch, 2 GB wheel).
* **`turboquant-py` 4-bit codec** for compression — the literal "TurboQuant
  as a vector store" the user asked for. Pure-NumPy, Windows-installable,
  same TurboQuant algorithm Google Research published at ICLR 2026.
* **Brute-force cosine search** — at ~350 docs the lack of an ANN structure is
  irrelevant; the dot-product scan is sub-millisecond.

When the package is missing the module degrades to **plain float32** vectors
with the same API surface — no breaking on production paths.

Integration:
* `app/data/kb_search.py::top_articles_by_relevance` gets an optional dense
  re-rank step via Reciprocal Rank Fusion (k=60).
* `app/engines/sentence_index.py::select_answer_sentence` adds a Windows-safe
  dense fallback (the existing `vector_rerank.rerank_sentences` already covers
  the Linux turbovec path).
* Both paths are env-gated via `REGENOLD_TURBOQUANT_DENSE=1` (default OFF —
  zero impact on existing benchmarks until enabled).

### Layer G (Zero-Hallucination Generation — sentence-level citation guard)

A new `app/integrations/regenold/citation_guard.py` that walks every emitted
sentence and verifies it cites at least one article from the surfaced refs.
Sentences with zero supporting refs are dropped — but only when the post-drop
answer is still ≥ 1 sentence (the round-16 finding showed dropping the *only*
sentence hurts the rubric more than keeping an over-broad one).

Different from the disabled `_drop_orphan_refs`: that function dropped *refs*
without supporting sentences; this guard drops *sentences* without supporting
refs. They're inverse passes and the new one is safer.

### Layer B (Four-Task Modular Pipeline — explicit router)

A new `app/engines/task_router.py` exposes `classify_task_4way(question)` →
`"risk" | "article" | "obligation" | "open"` per the Davvetas 4-task taxonomy.
The route uses the label to pick the answer-shaping path (deterministic vs
extractive vs scenario). This is a refactor, not a feature — but it makes the
4-task fidelity explicit and unlocks per-task metric reporting in the bench
runner.

## Out of scope (tracked as follow-ups in PR description)

* **Cross-encoder rerank (Layer E)** — Cohere Rerank-v3 is a network call;
  sentence-transformers cross-encoder pulls torch (~2 GB). Both break the
  Windows-dev constraint. Documented as a known gap.
* **CLARA boolean tag extraction (Layer F)** — needs an LLM prompt + typed
  schema + matrix consumer. Out of scope to keep this PR < 1000 LOC. Tracked.
* **Layout-aware PDF re-parser (Layer A)** — current corpus from the Ansvar
  port already has full prose + chapter assignments. Re-parsing the raw PDF
  is a multi-day task and would be net-neutral on the rubric.
* **General Prohibited Gatekeeper for non-scenario questions (Layer C)** —
  the scenario_classifier already covers scenario shapes (where Art. 5 risk
  applies); free-form questions rarely match prohibited practices. Tracked.

## Implementation order

1. `app/engines/turboquant_index.py` — core module + pure-NumPy fallback
2. `requirements.txt` — add `turboquant-py>=0.1.0` (optional)
3. `app/data/kb_search.py` — RRF fusion into `top_articles_by_relevance`
4. `app/engines/sentence_index.py` — Windows dense fallback in
   `select_answer_sentence`
5. `app/integrations/regenold/citation_guard.py` — sentence-level guard
6. `app/routes/regenold.py` — invoke citation guard after extractive
7. `app/engines/task_router.py` — explicit 4-task classifier
8. Tests: `tests/test_turboquant_index.py`,
   `tests/test_citation_guard.py`, `tests/test_task_router.py`,
   `tests/test_dense_rerank_integration.py`
9. Run `pytest -q` + `python -m evals.bench.runner --label round31-turboquant`
10. Open PR; do eng-review-style self-audit inline.

## Success criteria

* All 578 existing tests still pass.
* New module test coverage ≥ 4 modules × ≥ 3 tests each = 12+ new tests.
* Benchmark scorecard (476 items): **no regression** on any rubric axis vs
  Round 28; lift of ≥ +0.005 on **either** Ans Correctness Loose **or** Ref
  Correctness Loose when `REGENOLD_TURBOQUANT_DENSE=1` is set.
* Latency p50 < 8 ms with dense-rerank ON (current Round 28 is 5.43 ms; budget
  +2.5 ms for the brute-force dense scan + RRF fusion).

## Hard rules we must not break

(From `CLAUDE.md`)
1. Reference format: `Article N(.subpoint)*` Arabic / `Annex X(.subpoint)*` Roman.
2. `MAX_ANSWER_SENTENCES = 3` + 600-char soft cap.
3. No new classification topics overfit to the 3 PDF example questions.
4. KB stubs ship faithful regulatory prose, never speculation.
5. `ARTICLE_EXISTENCE` is the lint floor — every emitted citation must resolve.
