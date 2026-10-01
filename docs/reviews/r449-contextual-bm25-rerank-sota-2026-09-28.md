# R449 — Contextual retrieval, BM25 and reranking: external research mapped onto this stack

**Prepared:** 28 September 2026
**Scope:** Regulation (EU) 2024/1689 only. No claim in this document extends to later legislation.
**Working tree:** local checkout on `fix/r444-healthy-leg-screen` (dirty). This file is **local and untracked** — it has not been posted, pushed or attached to any PR.

**Status legend used throughout**

| Tag | Meaning |
|---|---|
| `[verified]` | Re-read from the live file in this working tree during this review. Line numbers are from this snapshot. |
| `[recorded]` | Read from a measurement record committed/untracked in `docs/measurements/`. Re-verify before quoting externally. |
| `[external]` | Published third-party claim. Vendor-run numbers are labelled as such; they are never assumed to transfer to this corpus. |
| `[unmeasured]` | Real code state, no measurement exists. Not evidence of "no effect". |

## 1. Method, and what this document is not

Three inputs were combined:

1. **External research** on contextual retrieval, late chunking, sparse+dense fusion, cross-encoder/LLM reranking, query-side expansion, hierarchical retrieval and retrieval-level evaluation (sources in §8).
2. **Direct reads of this repository's retrieval surfaces**: `app/data/kb_search.py`, `app/engines/turboquant_index.py`, `app/engines/embeddings_index.py`, `app/engines/vector_recall.py`, `app/engines/hybrid_rrf_retriever.py`, `app/engines/cohere_rerank.py`, `app/engines/_graph_rag_impl.py`, `app/data/provision_text.py`, `app/engines/kg_context.py`, `scripts/build_embeddings_index.py`.
3. **This repository's own recorded results**, including its negative results, which are treated as the strongest available prior here.

Not done, and explicitly not claimed: no flag flips shipped, no default changed, no live answer-level gate, no live 110-row generation, no judge pass, no deploy, no `/healthz` check. Every **external** number quoted in §2 is a published third-party claim, and every **repo** number in §3–§4 is a recorded measurement read from `docs/measurements/`.

The one thing this review does measure is its own instrument: P0 (a retrieval-grain harness) and P1 (deterministic contextual BM25 fields, default OFF) were both implemented and executed live against the production retrieval code, and §4/§5 carry those results. **Read §4 as superseding this document's original hypotheses where they disagree** — two of the cheap fixes proposed in the first draft are falsified by measurement, and §6 records the instrument bug that nearly made a third look like a no-op. Full record: `docs/measurements/r449/CHECKPOINT.md`.

The parallel-work request was served with batched concurrent research and repo reads. There is no sub-agent tool in this build, so "parallel agents" here means concurrent tool batches, not independent reviewers. Treat this as one reviewer's synthesis and check the citations rather than trusting the prose.

## 2. What the external research actually establishes

### 2.1 Contextual retrieval (index-time context) `[external]`

Anthropic's published method prepends a 50–100 token, chunk-specific context sentence to each chunk **before** both embedding and BM25 indexing. Reported results across code, fiction and paper corpora, top-20 retrieval, 1 − recall@20 as the failure metric:

| Configuration | Retrieval failure |
|---|---|
| Baseline (embeddings only) | 5.7% |
| Contextual embeddings | 3.7% (−35%) |
| Contextual embeddings + contextual BM25 | 2.9% (−49%) |
| + reranking (Cohere, top-150 → top-20) | 1.9% (−67%) |

Other details that matter for transfer: the benefit *stacked* with every embedding model tested; passing top-20 beat top-10 and top-5; generic document summaries on chunks gave "very limited gains"; HyDE and summary-based indexing were evaluated and underperformed. Context generation cost is quoted at ~$1.02 per million document tokens with prompt caching.

The independent academic comparison (Merola & Singh, *Reconstructing Context*, 2025) is the more honest source for trade-offs: contextual retrieval "preserves semantic coherence more effectively but requires greater computational resources", while late chunking "offers higher efficiency but tends to sacrifice relevance and completeness". That study also reports the fusion weighting it used — dense:BM25 = 1 : 0.25 (4:1), stating this "reflects" the Anthropic cookbook configuration.

**Transfer caveat for this repo:** every one of these numbers is a *chunk-level* retrieval result on corpora where a chunk is a few hundred tokens and the document is thousands. This system's BM25 units are **whole provisions plus hand-built virtual documents** (see §3.2), while its dense units are **whole sentences or whole virtual documents**. The failure mode contextual retrieval fixes — a chunk that cannot be interpreted without its parent — is therefore smaller here by construction, and the published deltas must not be reused as forecasts.

### 2.2 Late chunking `[external]`

Günther et al. (Jina, 2024): embed the whole document with a long-context encoder, then mean-pool token vectors per chunk so each chunk embedding inherits document context. No training, no extra LLM calls, but it requires a long-context neural embedder — the exact class of dependency `AGENTS.md` keeps out of the runtime path. The multi-vector pooling gives passage-grain embeddings with document context.

**Relevance here:** the mechanism is available in a reduced form. This repo already has a deterministic document-level factorization it could pool over (§3.3), which is a cheap *analogue*, not late chunking.

### 2.3 Hybrid fusion, and the finding that matters most `[external]`

Cormack et al. (2009) RRF remains the standard non-parametric fusion (`w / (k + rank)`, k = 60), robust to score-scale mismatch. Weighted-sum fusion needs score normalisation and is more sensitive to path quality.

The most consequential recent result is *Balancing the Blend* (PVLDB 2026, arXiv 2508.01405), a controlled study of four retrieval paradigms (full-text, learned sparse, dense, tensor) across 11 datasets. Three findings:

1. **"Weakest link" phenomenon** — combining paths can improve accuracy, but "a weak path can substantially degrade overall performance", and the authors' first recommendation is **path-wise quality assessment before fusion**.
2. **No one-size-fits-all** configuration; the optimum depends on latency/memory constraints and data characteristics.
3. **Tensor-based Re-ranking Fusion (TRF) outperformed RRF** in their consolidation setting at a fraction of full tensor-search cost.

Finding (1) is not a hypothetical for this system. It is a mechanistic explanation of at least three of its recorded negative results (§3.2, §3.4, §3.5).

### 2.4 Reranking `[external]`

| Model class | Current state | Cost/latency shape |
|---|---|---|
| Hosted cross-encoder — Cohere Rerank 4 (`pro` / `fast`) | 32K-token context for the v4 family; `fast` tuned for latency/throughput | one bounded HTTP call per batch |
| Voyage `rerank-2.5` / `-lite` | +7.94% / +7.16% NDCG@10 over Cohere Rerank v3.5, averaged over 93 datasets and four first-stage retrievers; +12.70% / +10.36% on MAIR; 32K context (8× v3.5) | vendor-run numbers |
| Instruction-following rerankers (Voyage 2.5 series) | Natural-language steering of the relevance definition; +~8% on the vendor's domain-specific sets | same call, no extra infra |
| `jina-reranker-v3.5` | 0.6B, listwise scoring, vendor reports up to 56% faster than v3 at ~97% of teacher quality | self-host or API |
| LLM-as-reranker (listwise) | Practitioner consensus: better than open cross-encoders on hard relevance judgements, but "pointwise LLM reranking is almost never [worth it]" and the economics are harsh | seconds + tokens per query |

Two caveats with direct local analogues:

* **Reranker quality depends on first-stage quality.** Voyage's own evaluation reports Cohere Rerank v3.5 *hurting* retrieval quality when applied on top of their strongest first-stage retriever. A reranker is not a monotone improvement over any candidate list.
* **Instruction-following is the feature that addresses this repo's measured failure.** See §3.4: the reranker scores Article 99 (penalties) at 0.4583 on a transparency question because penalties text *enumerates the very articles being asked about*. A relevance cross-encoder cannot reject that; an instruction ("retrieve the operative obligation, not the penalty or oversight provision") is aimed exactly at it.

### 2.5 Query-side techniques `[external]`

HyDE, multi-query and decomposition reliably raise recall and reliably cost an extra LLM round-trip per query; the recurring practitioner conclusion is that always-on expansion is a latency/cost trap and should be **routed** by query complexity (Adaptive-RAG, arXiv 2403.14403). For a system whose Speed axis is already the second-worst scored axis, this is a budget question before it is a quality question.

### 2.6 Hierarchical and graph retrieval `[external]`

RAPTOR (recursive summary trees) reports F1 at least 5.3 points over BM25 on long-document QA. Microsoft GraphRAG separates entity-local from community-summary global search. Both are aimed at *broad* questions. The repo's own 13 September review already concluded that "broad community summaries are poorly aligned with minimal statutory references" and that graph-primary retrieval was measured and rejected — that conclusion is inherited here, not re-litigated.

### 2.7 Retrieval-level evaluation `[external]`

The measurement vocabulary the research uses is retrieval-grain: failure rate / recall@k, nDCG@10, MRR, plus minimal-span relevance sets (LegalBench-RAG) and citation-quality separation (ALCE: answer correctness and citation quality are distinct dimensions). This repo's eight official axes are **answer- and reference-level**. That mismatch is the single largest methodological gap in §4 (G8).

## 3. The stack as built

### 3.1 Where retrieval actually runs `[verified]`

```
_deterministic_parse (keyword entity map → entity list)
   └── if not entities:            ← _graph_rag_impl.py:3104
          └── top_articles_by_relevance(...)   ← kb_search.py:562
                 ├── BM25 scoring                       kb_search.py:411
                 ├── + dense A (article-level TF-IDF→SVD128), additive   kb_search.py:871-884
                 ├── + dense B (sentence-level SVD128 → collapsed to article max-sim), additive  kb_search.py:892-914
                 ├── + 2-hop graph expansion (gated REGENOLD_GRAPH_2HOP)  kb_search.py:930+
                 └── + optional Cohere pool rerank (budgeted, permutation-only)
```

Two things follow immediately, and they constrain every recommendation below:

* **The hybrid/dense machinery is on the fallback lane only.** `top_articles_by_relevance` is reached only when the deterministic parser extracted **no** anchors. Anchored questions take the KB-first route (`_retrieve_from_kb`). This is deliberate — the comment at `_graph_rag_impl.py:12402-12414` records the measurement that running BM25 unconditionally raised mean engine citations 2.60 → 9.00 and cost −0.2094 Ref Conciseness — but the consequence is that "the dense path is a wash" is mostly a statement about a lane that rarely executes.
* **The second RRF implementation is also confined to the zero-anchor case**: `is_rrf_retrieval_enabled() and not query.entities` (`_graph_rag_impl.py:12411`), with the dense arm forced on only inside that branch.

### 3.2 Sparse side `[verified]`

Homegrown Okapi BM25 in `app/data/kb_search.py`, `k1 = 1.5`, `b = 0.75`, Lucene-style IDF `log((N − df + 0.5)/(df + 0.5) + 1)`. Document units are whole provisions/virtual documents from four sources: KB obligation summaries (`"kb"`), ontology virtual docs (`"ontology"`), the 126-article upstream prose corpus (`"corpus"`), and 68 Art. 3 definition docs (`"definition"`, excluded from the dense build because they collapsed every query to Art. 3).

Field weighting exists only as a hack: Annex III short names are duplicated ×2 and keywords ×3 in the document text (`kb_search.py` `_build_ontology_docs`) to make discriminative tokens win on TF. There is **no field structure** — no per-field length normalisation, no independent field weights, no way to score "title matched" differently from "body matched".

Sub-article selection is a separate lexical stage, `app/data/provision_text.py::select_relevant_paragraphs` with `_overlap_score` + `_sibling_idf`. It is token-overlap scoring, not BM25, and it has no embedding component.

### 3.3 Dense paths — four of them `[verified]`

| # | Path | Grain | Status |
|---|---|---|---|
| A | `app/engines/turboquant_index.py` — TF-IDF → truncated SVD → 128-d, optional TurboQuant 4-bit | article / virtual doc | default ON (`REGENOLD_TURBOQUANT_DENSE`, default `1`); precomputed asset on disk with a staleness guard |
| B | `app/engines/embeddings_index.py` — sentence-level TF-IDF → 128-d SVD, shared global basis, assets on disk | sentence (949-sentence corpus) | default ON inside `top_articles_by_relevance` (`REGENOLD_EMBEDDINGS_INDEX`, default `1`, threshold 0.15) |
| C | Neo4j native vector indexes (`v_article_embedding`, `v_annex_embedding`) via `app/engines/vector_recall.py` | article/annex node | default OFF (`REGENOLD_GRAPH_VECTOR_RECALL=0`), floor `REGENOLD_VECTOR_MIN_SIM=0.35`; forced only in the zero-anchor branch |
| D | External embeddings (Cohere / OpenAI) replacing path A's vector build when a key is present | article | opt-in (`REGENOLD_EXTERNAL_EMBEDDINGS` + key), plus the R435 process-local Cohere 429 cooldown |

Two structural facts about dense retrieval here:

* **Path B computes sentence-grain hits and then throws the grain away.** Hits are aggregated to `{article_ref: max cosine}` before fusion (`kb_search.py:892-914`). The passage identity — the thing a reranker or a paragraph selector would need — is discarded at the boundary.
* **Only the fill is additive-only; path B also displaces.** `additive_dense_fill` preserves the ranking it is handed and appends into vacant `k` slots — but path B applies a 1.20× sentence-similarity multiplier inside the BM25 scoring loop before the cut, so it evicts BM25 winners (this is what R449 measured; see §G4, where the older "all dense contributions are additive-only" reading is corrected). RRF is dormant; score fusion exists but is off (`REGENOLD_SCORE_FUSION`, α default 0.3, normalising BM25 by the max score **within the candidate set** — a fragile normaliser).

### 3.4 Reranking — one model, two placements, three constraints `[verified]`

* Model: `rerank-v4.0-pro` by default (`REGENOLD_COHERE_RERANK_MODEL`), v4-aware doc caps (24,000 chars vs 4,000 for v3.x), 6 s read timeout, fail-open.
* `rerank_enabled()` is **default ON** in code (R400) whenever `COHERE_API_KEY` is set. `CLAUDE.md`'s flag table (line 1761) still records `REGENOLD_COHERE_RERANK | 0` — **documentation drift; the code is the authority.**
* Placements: (a) the parse-level entity list, which is the placement that fires on the common path (`_graph_rag_impl.py:3408-3454`; entity *order* is load-bearing — it drives obligations and the 15-slot citation cap); (b) `_kg_refs` immediately before KG context rendering (`:9041`), load-bearing because `kg_context._node_ids(refs, limit=max_refs=8)` cuts by **list position**.
* Constraints: permutation-only (it never adds or drops a reference — a deliberate response to the R142.1 gold-drop loss); a request-scoped call budget (`REGENOLD_RERANK_REQUEST_BUDGET`, `_DEFAULT_REQUEST_BUDGET = 2` at `cohere_rerank.py:279`) added in R362 because the real profile was up to **5 serial rerank calls per request** against a 10 calls/min Cohere trial key.
* Measured limitation on this corpus `[recorded, cohere_rerank.py:344-400]`: Article 50.3 scores 0.8803, Article 19 scores 0.0286, but **Article 99 (penalties) scores 0.4583 on a transparency question** because penalty text enumerates the very articles being asked about.
* R329's lesson is pinned in the same file: three placements looked correct and made **zero** calls. `rerank_stats()["attempts"] > 0` is the precondition for believing any reranker number.

### 3.5 Graph and xref `[verified]`

`app/data/kb_xrefs.py` builds the cross-reference graph keyed on `Art. N` with curated reasons; 2-hop expansion is gated (`REGENOLD_GRAPH_2HOP`) and bounded at 50 ms. `docs/reviews/2026-09-13-sota-hybrid-rag-report.md` records the reason it stays gated `[recorded]`: over 132 rows, 660 hop-2 references were available and **4** were added, because BM25 had already filled the budget — "increasing slack is not automatically valuable".

## 4. Gap analysis

Each gap: research claim → repo state → why it matters here → cheapest discriminating test.

### G1 — No passage-grain retrieval index or fusion — and the two obvious fixes are now falsified

**Measured (R449, 110 rows, `docs/measurements/r449/UNIT-GRAIN-k8.md`).** On rows where the gold head *was* retrieved (79–85 of 110), the shipped selector's top-ranked paragraph is the gold one **72–73%** of the time, but its bounded 500-char output carries ≥80% of the gold paragraph's content only **41%** of the time (mean coverage ≈ 0.67). Two candidate replacements were measured on the same heads and both lose to the shipped selector: within-document paragraph BM25 **0.633**, paragraph-grain projection through the existing TF-IDF/SVD basis **0.576**, versus the shipped token-overlap + sibling-IDF selector **0.722**. So the sibling-IDF weighting is doing real work, and "index paragraphs into BM25 or into the SVD space" is not the fix.

*Research:* the entire contextual-retrieval literature is about chunks; LegalBench-RAG scores retrieval of *minimal relevant spans*; ALCE keeps citation quality separate from answer correctness.
*Repo:* BM25 is article-grain; dense B computes sentence-grain hits then collapses them to article max-sim; paragraph selection is a separate token-overlap scorer with no index.
*Why it matters:* R436's judge pass recorded **ref-faithfulness 25.00% (10/40)** and 24 citation-mismatch outcomes — "answers frequently discuss a provision but ship a neighbouring citation" — and its healthy-leg retest traced one surviving failure to an answer binding `Article 10(4)` where the criterion needed `Article 10(3)`. That failure class is *invisible* to article-grain retrieval and to all eight official axes.
*Cheapest test:* the instrument now exists (G8, built). The measured target is **emission**, not ranking: the top-1 is already 72% correct, so the loss is in what the bounded output contains.

### G2 — Contextual retrieval is absent by construction, and the expensive part is optional here

*Research:* index-time context is the mechanism; but generic summaries gave "very limited gains" while *chunk-specific* context did the work.
*Repo:* BM25 documents are `f"{article_ref} {summary}"` or full prose; no title/ancestry/actor prefix is indexed anywhere. All "context" work happens at **prompt** time via `kg_context`/`graph_semantic`. Nothing in the retrieval index knows that a provision is an Annex III point, which chapter governs it, or which actor it binds.
*Why it matters:* this is the one published technique with a large effect that costs **zero query-time latency** — it is index-time only. Unlike HyDE or an always-on reranker, it cannot move the Speed axis.
*Cheapest test:* build the prefixes deterministically from data already in the repo — `app/data/article_sections.py` (chapter/section), `app/data/eu_ai_act_tree.py::get_parent_context` (ancestry), `ontology.obligations_for` (actor), `provision_text` (governing paragraph). No LLM call, no network, reproducible.

### G3 — Concatenating context into BM25 without field structure would be actively harmful

*Research:* BM25F/field-weighted BM25 combines per-field term frequencies **before** saturation with independent per-field length normalisation (Robertson et al.; Elastic/OpenSearch `combined_fields`). Prepending context to a plain BM25 document inflates `len(D)` (penalised at b = 0.75) and raises `df` for context tokens, lowering their IDF — including the tokens the context was added to boost.
*Repo:* `_BM25Index` has `k1`/`b` only; the ontology hack (`short_name` ×2, keywords ×3) is a hand-rolled substitute for field weights.
*Why it matters:* without this, G2's implementation would likely measure flat or negative and be wrongly retired.
*Cheapest test:* unit-level qrels (G8) plus an A/B of `{no prefix, prefix-as-text, prefix-as-field}` at fixed k.

### G4 — The dense path is wired as an unconditional additive recall source with no path-quality gate — measured

**Measured (R449).** `dense_a` (the article-level SVD path, default ON) is a **strict no-op** on all 110 rows: identical recall/precision/nDCG/context cost and **0** added references, because `additive_dense_fill` can only fill slots BM25 left empty and BM25 fills `k` on every row. `dense_b` (sentence-level SVD, also default ON) is the only dense stage with an effect: **+30 references, 20% of them gold**, for +5.5 pp head recall — and it works by **displacement**, not addition: the 1.20× high-similarity boost is applied inside `best` before the `[:k]` cut, directly contradicting the "purely additive (never displaces a BM25 winner)" comment that stood over that stage at the call site. **Corrected in this round** (that comment carried no working line reference — the citation is by statement, not by line): the Round-32 block now names both mechanisms and states the measured numbers, the same qualifier is on `additive_dense_fill`'s docstring, and `tests/test_r449_dense_boost_displacement.py` fails if the boost stops reaching the cut. The test was verified by mutation — forcing `emb_boost` to `1.0` turns both behavioural tests red (`0 references added over 110 saturated rows`), and reverting it turns them green again. `REGENOLD_SCORE_FUSION` adds **254** references at **2.4%** gold precision for +1.2 pp recall and +1,359 context characters — the quantified weakest-link/waste case.

*Research:* arXiv 2508.01405's first recommendation is path-wise quality assessment before fusion; a weak path can substantially degrade accuracy.
*Repo:* two dense stages append into the BM25 ranking with no quality gate, no score floor, no per-path measured precision, and no cap on how many candidates they contribute. RRF is dormant precisely because the earlier measurement called fusion "a wash" — but that measurement fused with BM25 dominant (below), not with path-quality gating.
*Why it matters:* the repo's own results are consistent with the weakest-link reading — `[recorded]` R435's six-row signal, Ref Strict 75.00 → 58.33 (−16.67 pp) and Overall 69.90 → 65.33 (−4.57 pp); `[recorded]` R443's shadow browse adapter moved subpoint recall 0.151 → 0.161 but **head recall 0.957 → 0.935**, excess references 16.84 → 22.90 and context 68,807 → 88,159 chars on 31 rows. Adding a semantic path bought grain and lost precision and context budget.
*Cheapest test:* per-path precision at k on a labelled qrel set, then a margin gate ("only accept a dense candidate whose score clears the BM25 top-1 by X") evaluated offline before any live spend.

### G5 — The RRF configuration tested here is the opposite of the published one

*Research:* the configuration reported as mirroring the Anthropic setup is dense-dominant, 4:1.
*Repo:* `_fuse_dense` calls `reciprocal_rank_fusion(bm25_weight=2.0, dense_weight=1.0)` — BM25-dominant 2:1 (`kb_search.py:508-515`).
*Why it matters:* R31/R69's "RRF is a wash" and R329's "the dense arm is inert" were both measured under a weighting the published recipe does not use, on a corpus where BM25 saturates. The negative result is real for what was run; it does not test the published configuration. Re-running is nearly free (both weightings already exist behind one env flag).
*Cheapest test:* same 110 rows, same cached candidates, three fusion modes (additive / BM25-dominant RRF / dense-dominant RRF), retrieval-grain metrics only.

### G6 — Reranking targets references and pool ordering, never the evidence bundle that reaches the model

*Research:* Anthropic's largest single jump (−49% → −67%) came from reranking contextual chunks; instruction-following rerankers now let you *state* the relevance policy.
*Repo:* the reranker reorders entity refs and `_kg_refs`. The actual rendered passages are then truncated by `kg_context` at `max_refs = 8` **by list position**. The query sent to Cohere is capped at 600 chars and carries only short repo-static labels; the measured Article-99 failure is a relevance-policy failure, not a capacity failure.
*Why it matters:* the highest-ROI published lever is aimed at the right *stage* but the wrong *objects*, under a call budget sized for a trial key rather than for the task.
*Cheapest test:* rerank the **unit bundle** (paragraph/sub-point candidates with their G2 prefixes) in one batched call, permutation-only, and check whether the Article-99 class moves. Requires a provider that is not rate-limited to 10 calls/min — Cohere via Bedrock `eu-central-1` (`cohere.rerank-v3-5:0`, `amazon.rerank-v1:0` are available there; the v4 family is the current default via api.cohere.com) or Voyage `rerank-2.5` are the candidates. `[recorded]` R435 already showed the Cohere trial key 429-ing into a deterministic fallback.

### G7 — Query-side expansion exists but is not gated by a retrieval-side signal

*Research:* expansion/decomposition raise recall and cost a call; routing by complexity is the standard mitigation.
*Repo:* `app/engines/query_expansion.py` (LLM paraphrase) and `app/engines/sufficient_context.py` (`decompose_question`, `max_sub_queries`, `assess_sufficiency`) already exist. `[recorded]` R350 counted up to 4 BM25-chain runs per `_deterministic_parse` when expansion is on.
*Why it matters:* Speed is a scored axis already at 70.832 (`[recorded]` R436) with live p50 24.24 s / p95 37.36 s. Always-on expansion is a direct tax on that axis.
*Cheapest test:* log the retrieval-side signal (top-1 lexical score, clause count, whether the deterministic parser found ≥1 anchor) against outcomes on the existing 110 rows, then gate expansion on it and measure retrieval-grain recall at equal call count.

### G8 — There is no retrieval-level evaluation harness, so none of the above can be measured cleanly

*Research:* the field's metrics are retrieval-grain.
*Repo:* all eight official axes are answer/reference-level (`evals/official/rubric.py`); `evals/bench/metrics.py` is `answer_*` / `reference_*` / `regulatory_tone` / `percentile` / `score_row` / `aggregate`. The only retrieval-grain instruments are ad-hoc probes: `docs/measurements/r384/qrel_probe.py` (reuses `turboquant_index.dense_top_k` as a question-relevance filter) and `docs/measurements/r384/fused_detector.py`.
*Why it matters:* any contextual/BM25/rerank change currently has to be judged through generation-mediated axes, where a retrieval win and a generation regression cancel invisibly. This is why P0 below is not a retrieval feature.
*Cheapest test:* the material largely exists — `docs/measurements/r388/official_gold_n110.jsonl` carries strict coordinates (e.g. `rg_001` → `expected_refs: ["Annex IV.1.e"]`), `provision_text` resolves them to text, and `embeddings_index`/`kb_search` can be scored head-to-head with recall@k and nDCG@k at both article and unit grain. Deterministic, offline, no network, no judge.

### G9 — Latency is the binding constraint on which research techniques are admissible

*Research:* all the generative variants (HyDE, always-on multi-query, LLM listwise reranking, LLM contextualisation at query time) add a round-trip.
*Repo:* `[recorded]` R436 Speed 70.832, p50 24.24 s, p95 37.36 s; the reranker alone is 6 s read timeout and budget-capped at 2 calls/request.
*Why it matters:* it produces a clean admissibility rule for §5: **index-time techniques are free and query-time LLM techniques are expensive.** G2, G3 and G8 cost nothing per request. G6 costs one already-paid call if batched. G7 must justify itself against the axis.

### G10 — Two documentation drifts worth fixing while touching nothing else

* `app/engines/turboquant_index.py:32` documents `app.data.kb_search.top_articles_by_relevance_hybrid` as the fusion entry point. **No such function exists.** The module header describes a two-step hybrid core that is, at the seam, aspirational.
* `CLAUDE.md:1761` still records `REGENOLD_COHERE_RERANK` default `0`; the code default is ON (R400). Anyone reasoning from the flag table will mis-model the live path.

## 5. Prioritised roadmap

Ordered so that each step is measurable before the next starts, and so the two zero-latency items come first. Gate column names the instrument; no step is "accepted" on an offline deterministic test alone (`CLAUDE.md`: a davidath no-op proves nothing about a live prompt change).

Status after measurement: **P0 is built** (`evals/retrieval/unit_grain.py`), **P1 is implemented behind a default-OFF flag and measured** (`REGENOLD_CONTEXTUAL_FIELDS`), and its result is weak-positive but inside noise, so it stays OFF pending tuning. A code audit also found the initial fielded path computed IDF only from body terms, making title-only context terms unscorable (`idf=0`); fielded IDF now counts the union of terms across fields once per document. This correction is covered by a focused offline regression test, but the recorded arm metrics above were produced before that correction and are not measurements of the corrected scoring path. The rest is unchanged.

| Priority | Change | Axis it can move | Cost/request | Gate to pass | Kill condition |
|---|---|---|---|---|---|
| **P0 ✅ built** | Retrieval-grain eval harness (`evals/retrieval/unit_grain.py`): head-grain recall/precision/F1/nDCG, per-stage added-reference precision, context-char cost, and unit-grain top-1 + coverage. Offline, deterministic, one subprocess per arm. | none directly — enables everything else | 0 | reproduces the recorded R435/R443 directions from cached data (stateful-index hazard handled by process isolation) | cannot resolve gold coordinates to units |
| **P1 ⚠ measured, weight sweep DONE (R451), NOT adopted** | Deterministic contextual prefixes (title + chapter + section + ref) indexed as **BM25F fields**, `REGENOLD_CONTEXTUAL_FIELDS` default OFF. | Ref Strict, Ref Conc, Ans Strict | 0 | +1.2 pp head recall, +1.6 pp nDCG and −325 context chars, but only **3** gold references gained while **94** references churned (3.2% addition precision) — inside noise at n=110. R451 swept the four weights: the title weight is **flat** in [1.5, 3] so untuned weights were not the cause, and `b_body` is the one live parameter — at **0.5/0.6** the fielded path moves from *inside noise* to **beyond noise vs no-fields at all** (`+0.026…+0.030` nDCG, CI excludes zero at α=0.05/17). `b_body=0.6` clears the pre-registered promotion rule but not the multiplicity bar against the shipped weights, so it goes to a live gate, not to a default. | any lost gold head; or no gain beyond noise after a weight sweep — **the sweep ran (R451): the title side came back flat, so "untuned weights" is eliminated as the explanation; the gain, where it exists, is in the body length slope** |
| **P2** | Path-quality gate on dense A/B: score floor + contribution cap, and per-path precision recorded per request. Directly the weakest-link finding. | Ref Conc, Tone, Speed (fewer junk refs → less context) | 0 | P0: removing the gate must measurably *hurt* unit recall, or the gate is worth keeping anyway for precision | gate removes a candidate that ≥2 gold rows depend on |
| **P3 ⬆ promoted** | Fusion re-test: additive vs BM25-dominant RRF vs dense-dominant (4:1) RRF, on cached candidates. Measured precedent: `rrf` has an **identical reference set** to the shipped additive fusion yet the best nDCG of that family (.625 vs .612), while `score` fusion adds 254 refs at 2.4% gold precision. | Ref Strict/Conc, Ans Strict (ordering decides which evidence survives `kg_context`'s positional cut) | 0 | P0 metrics, then one live A/B on the fallback lane | no ranking-level difference at all → retire RRF permanently with a recorded reason |
| **P4** | Rerank the **unit bundle** with prefixes, single batched call, permutation-only, instruction-following reranker; move off the 10 calls/min trial key (Bedrock eu-central-1 or Voyage). | Ans Strict, Ref Strict, Ref Conc | +1 call (replacing the existing budgeted ones) | `rerank_stats()` attempts > 0 **and** the Article-99 class specifically moves on a pre-registered row set | gold-drop (hard rule #8) or no change in the penalty-article class |
| **P5** | Complexity-routed expansion/decomposition gated on the retrieval-side signal from G7. | Ans Loose, Ref Strict | +1 call on a minority of rows | Speed axis non-regression **and** a paired retrieval-grain recall gain | p95 latency regression without recall gain |
| **P6 ⚠ measured, NOT flipped** | Passage-**emission** allocation: spend the per-provision verbatim budget by relevance-per-character instead of rank order (`REGENOLD_EMIT_ALLOC=density`), same budget and same char cost. R450. | Ans Strict/Loose (the prompt carries the operative paragraph, not its neighbours), Speed (chars flat) | 0 | retrieval-grain on the production grounding budget: hit rate **0.718 → 0.753** with emitted chars **1,061 → 1,056** (sweep grid on its own denominator: 0.744 → 0.780, three rows rescued, **zero** regressions); then the live paired gate below | any lost gold head, or a Speed regression |

### 5.1 R450 addendum — the emission gap, made precise

[`docs/measurements/r450/CHECKPOINT.md`](../measurements/r450/CHECKPOINT.md) measures the gap §4 attributed to emission, by sweeping the two things §4 never varied: the per-provision **budget** and the **allocation order** (`evals/retrieval/emit_sweep.py`). Four results change the reading of the R449 headline, and one of them is a correction of *this document*.

1. **The 0.41 figure was a budget artifact for the answer path.** It was measured at `max_chars=500`, which is the verbatim-**answer** budget (`REGENOLD_VERBATIM_PARA_CHARS`). The evidence the *scored* answer reads is the Stage-2 grounding block at **1200** per ref (`_graph_rag_impl._grounding_ref_budget()`). The same instrument, now that the harness takes `--unit-budget`, reports **0.718** for the shipped allocation at 1200 (85 gradable rows). The gap is real; it was roughly half the size the headline implied.
2. **>0.8 is not reachable without growing context cost — on this metric.** Coverage is a share of the gold *paragraph's own* tokens, and 79% of gold units are individually larger than the 500-char budget while about a quarter exceed 1,200. Crossing 0.8 needs ≈**1,600 chars/ref**: 0.817 (rank) / 0.829 (density) at 1,413 / 1,382 mean emitted chars = **+33%** over the shipped grounding cost. Any claim of ">0.8 at no extra context" would have to redefine the metric, so it is not made.
3. **The allocator that ships is Pareto-dominated by a cheaper one.** `density` (fill the leftover budget by score per character) ties `rank` at 300/500/700 and beats it at 900/1200/1600 — and at 1,200 it emits **five fewer characters on average**. At 1,200 the paired per-row flips are three rescues (`rg_033` 0.40→1.00, `rg_069` 0.53→1.00, `rg_088` 0.47→1.00) and **zero** regressions. This is P6.
4. **The one deeper idea is falsified.** `split` (cap the oversized top unit and reserve the remainder for whole siblings) is the only policy that attacks the dominant loss — on 9 fits-but-missed rows at 1,200 the gold unit fits and still never arrives because a *wrong*, oversized top unit consumes the whole budget. Measured, it gains only at low budgets (+2 rows at 500) while inflating p95 emitted chars 1,221 → 2,030, and at 1,200 it is **worse than shipped** (0.732 vs 0.744) on more characters. It stays in the code as a measured-dead option behind its own env gate, documented as such rather than deleted, so the next round does not re-derive it.

What P6 still needs before it can be flipped is the thing offline instruments cannot give: a live paired run at the shipped grounding budget with `REGENOLD_EMIT_ALLOC` 0/1, judged on the eight official axes plus `gold_dropped_head`. The emission does not move the emitted **reference list**, so the axes at risk are Ans Loose/Strict (does the operative paragraph in the prompt raise completeness?) and Speed (flat: −0.5% chars). Until that runs, the default stays `rank` and the R449 numbers stay reproducible through the harness's 500-char arms.

Two things deliberately **not** in this roadmap. Late chunking (`[unmeasured]`, needs a long-context neural encoder — excluded by `AGENTS.md`) is not proposed, and its deterministic analogue has now been **measured and rejected**: projecting paragraph TF-IDF through the existing SVD basis scored **0.576** top-1 against the shipped selector's **0.722** on the same heads, so the paragraph grain is not where the missing evidence is. RAPTOR-style summary trees are not proposed: broad community summaries conflict with minimal-citation scoring, and the repo's own review already reached that conclusion.

### 5.2 R451 addendum — the weight sweep P1's kill condition asked for

[`docs/measurements/r451/CHECKPOINT.md`](../measurements/r451/CHECKPOINT.md) runs the sweep P1 named as its kill condition, through `evals/retrieval/field_weight_sweep.py` (17 one-factor-at-a-time cells plus an un-fielded control, 110 rows, paired row bootstrap, pre-registered verdict).

1. **"Untuned weights" is eliminated as an explanation.** The title weight and the title length slope are flat: `w1.5`/`w2.0`/`w3`/`w5` are mutually indistinguishable (churn 6/0/20/45 rows, no significant nDCG delta), and `bt` moves nDCG by ≤0.0003 across its whole range. The by-argument `2.0/0.6` happens to sit in a flat basin, so R449's weak-positive verdict was **not** a cost of never having tuned. Turning the field nearly off does hurt (−0.0127 nDCG at `w0.1`), but not significantly.
2. **The one live parameter is the body length slope, and the shipped value is on the wrong side.** `b_body` is monotone over [0.4, 0.9]: 0.5 gives **+0.0158** nDCG (CI [+0.0037, +0.0303]) and 0.9 gives **−0.0095** (CI [−0.0206, −0.0012]); the sign is established at both ends rather than by one marginal cell. Three independent knobs point the same way — title weight up, body weight down, body `b` down all mean "let the context field count for more relative to the body".
3. **The better-powered comparison re-reads R449's headline.** With the shipped weights the fielded path is **+0.0140** nDCG over having no fields at all, CI [−0.0007, +0.0311] — R449's "inside noise", reproduced on an independent instrument. At `b_body` **0.5 or 0.6** it is **+0.030 / +0.026** with a CI that clears the α=0.05/17 Bonferroni level. So the claim R449 could not make — the fielded path beats no-fields beyond noise — becomes supportable at a tuned `b_body` and remains unsupportable at the shipped one.
4. **The rule's churn clause is precision-based and is the wrong instrument at this k.** `b_body=0.6` is the only cell to clear P1's pre-registered rule, and it clears clause 3 by **0.03252 vs 0.03191** — one gold reference out of 123 additions; `b_body=0.5` is the stronger cell against the control and fails the clause outright (4/141). Over a k=8 list where gold is three or four references, precision differences at the 0.001 level are noise. The clause is recorded as a **defect to re-register** next round (compare *gold additions*, not precision), not edited after the numbers were seen.
5. **Still no default flip.** The effect is concentrated (92% of the summed nDCG gain over shipped comes from 4 of 110 rows, median row delta exactly 0), the cell changes the returned set on 56/110 rows while only 8 change nDCG, and it costs +2.0% context. That is a live-gate candidate; the lever is already env-driven and read per call, so the gate needs no code change.

## 6. What the research does *not* license here

### 6.0 Two failures of this instrument, recorded so they are not repeated

* **A stateful index makes a lever look inert.** `kb_search._build_index` is `lru_cache(maxsize=1)` and the dense index is a process singleton, so arms sharing a process share the *first* arm's index. The first harness run reported `ctx_fields` ≡ `bm25` on every metric — a false "contextual fields do nothing" that was really the OFF index being replayed. Every arm now runs in its own subprocess (`--in-process` is opt-in and documented as valid only for index-identical arms).
* **A sign convention inverted every verdict (R451).** The R451 sweep's paired bootstrap helper computed `b − a` while its callers passed `(cell, baseline)`, so each cell's printed delta and verdict were the *opposite* of its data: a cell with aggregate nDCG 0.606 against a 0.590 baseline was reported as −0.0158 and graded "significant loss". The tell was not the CI — it was the **contradiction between an aggregate column and its own paired delta**, which is why the harness now checks that the two agree and why the helper is named `paired_delta_ci(baseline, cell)` with the argument order *being* the convention. Any statistic whose sign is expressed by parameter order will eventually be called with the arguments reversed.
* **A provider fallback makes a live arm look null.** The live external-embedding arm returned *exactly* the local-SVD numbers because `api.cohere.com/v1/embed` answered **HTTP 429** on all three attempts and `turboquant_index` silently fell back to SVD (`index_diagnostics()["embedding_backend"] == "svd"`). The correct reading is "this key cannot measure the external path" (a 110-row sweep is ~111 calls against a 10 calls/min ceiling), not "external embeddings add nothing". The harness now records and prints the resolved backend per arm.

* Importing the −49% / −67% failure-reduction figures as forecasts. Different corpus, different chunk sizes, different metric.
* Turning on symmetric or dense-dominant fusion *without* P2's path-quality gate — arXiv 2508.01405's central finding is that this is how a strong path gets degraded.
* Re-proposing reranking the **emitted reference list** post-hoc: `[recorded]` R329 measured mean normalised position of judged-wrong refs 0.582 → 0.562, i.e. slightly worse. That variant is dead; reranking the *evidence that reaches the context* is a different intervention and is exactly P4.
* Any always-on query-time LLM stage without a Speed budget, per G9.
* Reviving graph-primary retrieval, community-summary context, or the R443-style browse/resolve adapter without a P0 harness to prove the direction first.
* Treating a green offline suite as evidence a retrieval change is safe: `CLAUDE.md`'s recurring lesson is that gate-off/offline-deterministic "no-ops" look identical to inert features.

## 7. Verification commands

```bash
# Confirm the two documentation drifts (G10)
grep -n "top_articles_by_relevance_hybrid" app/engines/turboquant_index.py
grep -n "REGENOLD_COHERE_RERANK" CLAUDE.md | head

# Confirm the fallback-lane gate and the RRF confinement (G1/G4)
grep -n "if not entities" app/engines/_graph_rag_impl.py
grep -n "is_rrf_retrieval_enabled() and not query.entities" app/engines/_graph_rag_impl.py

# Confirm fusion defaults and weights (G4/G5)
grep -n "_rrf_fusion_enabled\|_score_fusion_enabled\|bm25_weight=2.0\|additive_dense_fill" app/data/kb_search.py

# Confirm rerank model/limits/default (G6)
grep -n "_DEFAULT_MODEL\|_MAX_RERANK_DOC_CHARS\|def rerank_enabled" app/engines/cohere_rerank.py

# Confirm the sentence grain is computed then collapsed (G1)
sed -n '892,914p' app/data/kb_search.py

# Confirm assets exist so paths A and B are live, not dead code
ls app/engines/_assets/

# Offline unit tests for the retrieval surfaces touched by any of P1-P5
../.venv/Scripts/python.exe -m pytest tests/test_turboquant_index.py tests/test_retrieval_upgrades.py tests/test_semantic_layer.py tests/test_r329_cohere_rerank.py -q
```

## 8. Sources

| Source | Used for |
|---|---|
| [Anthropic — Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | −35% / −49% / −67% failure reduction; 50–100 token prefixes; top-20 > top-10/5; summary-on-chunk and HyDE underperformance; $1.02/M tokens |
| Merola & Singh, *Reconstructing Context* ([arXiv 2504.19754](https://arxiv.org/html/2504.19754v1)) | Independent contextual retrieval vs late chunking trade-off; reported 4:1 dense:BM25 fusion weighting |
| Günther et al., *Late Chunking* ([Jina](https://jina.ai/news/late-chunking-in-long-context-embedding-models/), [arXiv 2409.04701](https://arxiv.org/pdf/2409.04701)) | Mechanism; long-context encoder requirement |
| Wang et al., *Balancing the Blend* ([arXiv 2508.01405](https://arxiv.org/html/2508.01405v2), PVLDB 2026) | Weakest-link phenomenon; path-wise assessment before fusion; TRF > RRF; no universal configuration |
| [Voyage — rerank-2.5 blog](https://blog.voyageai.com/2025/08/11/rerank-2-5/) | +7.94%/+7.16% NDCG@10 over Cohere v3.5; MAIR margins; 32K context; instruction-following gains; Cohere v3.5 hurting a strong first stage |
| [Cohere Rerank docs](https://docs.cohere.com/docs/rerank), [Rerank 4 blog](https://cohere.com/blog/rerank-4) | v4 pro/fast; 32K context family (matches the repo's own v4 caps) |
| Elastic Search Labs — jina-reranker-v3.5 | 0.6B listwise, up to 56% faster than v3 (vendor-reported) |
| zeroentropy / Fin.ai reranker guides | LLM-as-reranker quality vs economics; pointwise rarely worth it |
| BM25F references (Robertson; OpenSearch `combined_fields`) | Per-field weights and independent per-field length normalisation |
| Adaptive-RAG ([arXiv 2403.14403](https://arxiv.org/abs/2403.14403)), LegalBench-RAG ([arXiv 2408.10343](https://arxiv.org/abs/2408.10343)), ALCE, Sufficient Context, RAPTOR ([arXiv 2401.18059](https://arxiv.org/html/2401.18059v1)), Lost in the Middle | Routed effort; minimal-span retrieval; citation-quality separation; RAPTOR's ≥5.3-point F1 edge over BM25 |
| `docs/reviews/2026-09-13-sota-hybrid-rag-report.md` | Inherited prior review: metric duality, 660-to-4 hop-2 inertness, A0–A7 ablation ordering, closed directions |
| `docs/measurements/r436/FULL-JUDGE-REPORT.md` | Overall 72.250; Speed 70.832; latency p50/p95 24.24/37.36 s; ref-faithfulness 25.00% (10/40) |
| `docs/measurements/r435/CHECKPOINT.md` | Six-row dense-signal delta: Ref Strict −16.67 pp, Overall −4.57 pp; Cohere 429 behaviour |
| `docs/measurements/r443/CHECKPOINT.md`, `shadow_browse_report.json` | Head recall 0.957 → 0.935; excess refs 16.84 → 22.90; context 68,807 → 88,159 chars |
| `docs/measurements/r442/CHECKPOINT.md`, `docs/reviews/r411-architecture-audit.md` | Keep-floor split; engine-gap criteria vs emitted references |
| `docs/measurements/r450/CHECKPOINT.md`, `EMIT-SWEEP.md`, `HARNESS-EMISSION.md` | Emission budget × allocation sweep; 0.744 → 0.780 at the production grounding budget; >0.8 requires ≈1,600 chars/ref; `split` falsified |
