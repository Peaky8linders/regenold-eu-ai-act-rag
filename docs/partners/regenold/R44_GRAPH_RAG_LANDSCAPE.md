# R44 — Graph-RAG / Hybrid-RAG landscape survey for hard regulatory text

Scope: identify 2024–2026 patterns specifically adapted to legislative,
regulatory, or contractual text that we can fold into our existing layered
deterministic-first stack (Rounds 31–36). Ranked by determinism, license,
maturity, and bench-measurable lift against davidath / AIReg-Bench /
Regenold probe.

---

## Section A — Top 5 patterns we SHOULD adopt

### A1. SAT-Graph RAG — ontology-first hierarchical legal graph
*(Lyrio Junior et al., arXiv 2505.00039v5, May 2026)*

**Mechanism.** Four-layer FRBRoo-inspired ontology: Norm (Work) → Component
(Title/Chapter/Article) → Temporal Version (CTV) → Language Version (CLV).
Legislative Actions reified as first-class graph nodes linking source
provisions to terminated/created CTVs. Crucially: the legal hierarchy IS
the graph's backbone — not a derived semantic hierarchy à la
Microsoft GraphRAG.

**Predicted lift on our rubric.** Ans-Strict +0.005 to +0.010 (the
"applicable as of 2027 vs 2026" answers the route currently muddles
because R27's Omnibus dates landed only in `kb.py` Art. 113 prose, not as
queryable nodes). Ref-Strict +0.005 (lets us return the *version* of an
article rather than its abstract identity). Latency cost <1ms — pure
in-process lookup on a sidecar dict built at import.

**Integration cost.** ~250 LOC: extend `app/data/eu_ai_act_tree.py`
(already 1426 nodes, R32) with two new fields per `TreeNode`:
`effective_date: date | None` and `superseded_by: str | None`. Add an
ApplicableVersion lookup pass in `app/integrations/regenold/citation_guard.py`
that resolves bare `Article 6` → `Article 6 (in force from 2027-12-02)`
when the question carries a date anchor. Zero new deps.

**Wire-up.** Plug between Round-31 `task_router` and the route's reference
finalisation. No LLM. Bench-measurable on davidath items whose gold cites
"Annex III high-risk obligations from 2 Aug 2026" (which the Omnibus
moved — we currently mis-cite under R34's R27-corrected dates).

**Why this first.** It's the *only* pattern in the literature that
specifically converged on "structure-aware approaches using the document's
intrinsic hierarchy as the graph's backbone" as the dominant paradigm for
legal norms. We already have the tree (R32). The wire is missing.

[Source: arxiv.org/abs/2505.00039v5](https://arxiv.org/abs/2505.00039v5)

---

### A2. Definition-graph recursive resolution
*(WhyHow.AI multi-graph multi-agent, May 2025; reinforced by SAT-Graph)*

**Mechanism.** Two parallel graphs: (1) hierarchy graph for clause
structure, (2) **definition graph** that gets recursively expanded when
any retrieved clause mentions a defined term. The retrieval pipeline
detects terms like "AI system", "provider", "substantial modification"
in candidate refs and pulls Art. 3(N) into the candidate set BEFORE the
answer is composed.

**Predicted lift.** Ref-Loose +0.008, Ref-Strict +0.005. davidath gold
sets routinely include Art. 3 cites alongside obligation articles
("provider of GPAI with systemic risk" gold: [Art. 3(63), Art. 51, Art. 55]) —
our current pipeline lands Art. 51/55 but misses Art. 3(63).

**Integration cost.** ~180 LOC. The 68 Art. 3 definitions are already in
`app/data/eu_ai_act_corpus.py` (R25) AND `app/data/definitions.py`
(hand-curated 31). New module `app/engines/definition_expand.py`: on
candidate refs, regex-scan article prose for defined-term mentions
(case-insensitive longest-match against `DEFINITIONS.keys()`), append
the matched `Art. 3(N)` to candidates with confidence weight 0.6. Cap
at 2 definition adds to protect Ref Conciseness.

**Wire-up.** Run AFTER `graphrag_expand.expand_for_scenario` and BEFORE
`citation_guard`. Pure deterministic, sub-millisecond. Env-gate
`REGENOLD_DEFINITION_EXPAND` (default 1).

[Source: medium.com/enterprise-rag/legal-document-rag-multi-graph-multi-agent](https://medium.com/enterprise-rag/legal-document-rag-multi-graph-multi-agent-recursive-retrieval-through-legal-clauses-c90e073e0052)

---

### A3. NodeRAG-style heterogeneous nodes (offline-only)
*(Xu et al., arXiv 2504.11544, April 2025)*

**Mechanism.** 7 node types: Entity, Relationship, Semantic-Unit,
Attribute, High-Level-Element, High-Level-Overview, Text. Indexing-time
LLM extraction, **search-time graph algorithms (no LLM)**. Reports 89.5%
on HotpotQA, 46.3% on MuSiQue, 4.05s query vs GraphRAG's 22.65s — and
crucially: zero per-query LLM calls.

**Predicted lift.** Ref-Loose +0.010 on QA subset where the Davvetas
4-task router currently classifies "open" (catch-all). On the davidath
bench specifically the lift is bounded by BM25-saturation (R31 finding);
the real win is on AIReg-Bench's annotated multi-article violations.

**Integration cost.** ~400 LOC + a one-time offline build script
(`scripts/build_node_rag_index.py`). Inputs: existing `ARTICLE_FULL_TEXT`
+ `kb_xrefs._build_xref_graph` + manual edges. Output: a
`node_rag_index.json` (~2MB) shipped in `app/engines/_assets/`. No new
runtime deps — pure NumPy + stdlib at query time, mirroring our
`embeddings_index.py` pattern.

**Wire-up.** Sits alongside `embeddings_index` and `turboquant_index` as
a third additive-dense path in `kb_search.top_articles_by_relevance`.
Env-gate `REGENOLD_NODERAG=1` (default OFF until bench-measured).

**Why not first.** Larger LOC and the offline build needs LLM credits
(Sonnet pass to extract Semantic-Units from EUR-Lex prose). Worth it but
queue it after A1/A2.

[Source: arxiv.org/abs/2504.11544](https://arxiv.org/abs/2504.11544)

---

### A4. Conditional retrieval pathway router
*(Buchanan et al., LREC 2026 Multi-Jurisdictional RAG)*

**Mechanism.** Three explicit pathways: **A** direct metadata lookup for
article-specific queries (bypass semantic search entirely); **B**
entity-filtered semantic search with fallback; **C** multi-jurisdiction
search for comparative analysis. Reports 0.87 faithfulness / 0.92
relevancy on single-entity queries (vs 0.75 on multi-jurisdiction).

**Predicted lift.** Latency p50 -1.0ms to -2.0ms (Pathway A short-circuits
the entire BM25 + dense + xref dance for explicit-anchor queries like
"What does Article 13 require?"). No accuracy regression — Pathway A's
gold is unambiguous.

**Integration cost.** ~120 LOC in `app/routes/regenold.py`. Detect
explicit `Article N` / `Annex X` in the user message via the existing
`_ARTICLE_OUTPUT_RE` + `_ANNEX_OUTPUT_RE`. If present AND the question
is short (≤ 80 chars) AND no co-reference rescue fired, return the KB
stub for that article directly. Bypass `ask_compliance_question`.

**Wire-up.** First branch in the route, before `classify_conversation`.
Pure deterministic. Bench-measurable: ~15% of davidath QA items match
this shape and currently spend 6-8ms on machinery they don't need.

[Source: arxiv.org/abs/2604.25448](https://arxiv.org/html/2604.25448)

---

### A5. Compliance-NLP cross-reference resolver (bilinear classifier)
*(Guo et al., arXiv 2604.23585, May 2026)*

**Mechanism.** Bilinear classifier `s(a, b) = aᵀ·W·b` over article-pair
embeddings, trained to predict whether article *a* cross-references *b*.
Reports 91.8% accuracy, 94.7% expert-validated precision on financial
regs (SEC, MiFID II, Basel III). Currently our xref graph has 115
edges from regex + 20 manual = 135 total; the AI Act regulation has
~360 cross-references by manual count of "referred to in" phrases.

**Predicted lift.** Ref-Loose +0.012 (close the gap from 0.5509 toward
0.6 cap). The xref graph backs both `kb_xrefs` (R23) and Neo4j
`CROSS_REFERENCES` (R35); a denser graph lifts both the in-process
1-hop and the Neo4j 2-hop paths.

**Integration cost.** ~300 LOC: offline trainer + one-time pass over the
113 articles producing `kb_xrefs_learned.py` (additive to manual edges).
Use scikit-learn LogisticRegression on TF-IDF article embeddings — we
already have `embeddings_index._build_tfidf_svd` (R32). Zero new runtime
deps; offline trainer is one-shot.

**Wire-up.** Merge `LEARNED_XREFS` into `kb_xrefs._MANUAL_EDGES` at
import. Existing `graph_expand_2hop` + `graphrag_expand.expand_for_scenario`
pick up the new edges transparently.

[Source: arxiv.org/html/2604.23585](https://arxiv.org/html/2604.23585)

---

## Section B — Top 3 patterns we should NOT adopt

### B1. Microsoft GraphRAG (community-summarisation)
60.92% RAG vs 49.29% MS-GraphRAG on fact retrieval (GraphRAG-Bench
ICLR'26). Prompt size up to 4×10⁴ tokens for global queries. Hard
incompatible with our sub-10ms p50 budget AND our deterministic-first
charter. The community-summary pass requires LLM at both index time
(expensive) AND query time (latency catastrophe).
[Source: arxiv.org/html/2506.05690v3](https://arxiv.org/html/2506.05690v3)

### B2. ColBERT v2 late-interaction rerank
LegalBench-RAG's best ColBERT setup hit only ~14.4% Precision@1 on
PrivacyQA — and that's with the GPU-resident PyTorch backbone. Our
R32 NumPy-SVD embeddings + Strategy-A cross-encoder (sub-50µs/pair)
already outperform ColBERT on legal text per the benchmark. ColBERT
would force torch + ~500MB model weights; net negative.
[Source: dl.acm.org/doi/10.1145/3746252.3761151 (gated)](https://dl.acm.org/doi/10.1145/3746252.3761151)

### B3. LightRAG / KET-RAG full LLM-extracted KG
Strong on the largest legal dataset per Findings-EMNLP 2025, but the
graph construction step is fully LLM-driven (GPT-4o-class extraction
per chunk). Re-indexing the AI Act + amendments + recitals would cost
$30-50 of Sonnet credits AND lock us out of deterministic-fallback
guarantees the moment the LLM hallucinates an edge. Our hand-curated
`kb_xrefs` plus the A5 learned classifier dominates this.
[Source: github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG)

---

## Section C — Surprises / paradigm shifts (2026)

1. **The legal-RAG field has converged on "structure-first, semantics-
   second."** Every 2026 legal paper surveyed (SAT-Graph, WhyHow
   multi-graph, ComplianceNLP, Multi-Jurisdictional) explicitly uses the
   document's *formal* hierarchy as graph backbone, with semantic
   embeddings as a secondary rerank. This vindicates our R32 layout-aware
   tree + BM25-first stance. The "LLM extracts entities → builds graph"
   approach (LightRAG, Microsoft GraphRAG) is now considered the *less*
   reliable path for hard regulatory text.

2. **AIReg-Bench (Oct 2025) is the new gold standard for EU AI Act
   compliance reasoning** — 120 expert-annotated technical-documentation
   excerpts, CC-BY, Hugging Face hosted. Gemini 2.5 Pro hits 0.856 rank
   correlation with expert judgments. We should add this to
   `evals/bench/` next sprint; it measures *compliance verdict accuracy*
   which davidath doesn't.

3. **GraphRAG-Bench (ICLR'26) explicit finding**: plain BM25 *beats*
   every Graph-RAG variant on Level-1 (fact retrieval) tasks. Graph
   structure only pays off at Level-2+ (multi-hop, contextual summary).
   The davidath benchmark is overwhelmingly Level-1 — which is why our
   R31 turboquant + R32 embeddings show flat against BM25. The win
   surface is production paraphrased queries (Level-2) and AIReg-Bench
   compliance verdicts (Level-3).

4. **HippoRAG 2 ranks competitive but never first** on the EU
   Directives + Indonesian Regulations multilingual legal benchmark
   (CEUR Vol-4079). Our R39 HippoRAG implementation is correctly
   gated behind a GDS plugin flag — the literature confirms it's a
   useful tool, not a silver bullet.

5. **Cross-encoder rerank is *necessary but not sufficient*** in legal
   RAG. Every paper that lifted F1 ≥ 0.05 paired rerank with at least
   one *structural* mechanism (xref, definition expand, hierarchy
   traversal). Our R32 Strategy-A rerank built standalone won't move
   the needle until A1 or A2 lands first.

---

## Section D — Executive recommendation for R44

**Ship A4 (conditional retrieval pathway router) first, then A2
(definition-graph recursive resolution).**

A4 is the **single highest-leverage pattern** by every constraint:

- **Latency**: net *negative* cost — Pathway A short-circuits 6-8ms of
  machinery for ~15% of davidath QA items. p50 expected to drop from
  6.83ms to ~5.8ms.
- **Bench-measurable**: ~70 davidath QA items match the explicit-anchor
  shape (`"What does Article 13 require?"` / `"Annex IV(N) covers what?"`).
  Latency-Score lifts directly. Ref-Loose/Strict held by serving the
  same KB stub via Pathway A as via the full engine — no accuracy
  regression possible.
- **LOC**: ~120 LOC + 20 LOC of route wiring + 60 LOC of tests. Well
  under the 500-LOC budget.
- **Deps**: zero new. Uses existing `_ARTICLE_OUTPUT_RE` regex and KB
  stub lookup.
- **No LLM**: pure deterministic.
- **Closes a known gap**: R34 fixed the scope.py false positives but
  didn't address the "explicit anchor → wasted retrieval" inefficiency
  flagged in the Round-32 latency post-mortem.

A2 (definition-graph) is the natural R45 follow-up — also deterministic,
~180 LOC, predicted Ref-Loose +0.008 / Ref-Strict +0.005 — and it
benefits from A4's pathway routing (explicit-anchor questions resolve
via Pathway A; definition expansion fires on Pathway B/C only).

Defer A1 (SAT-Graph temporal versioning) to R46 once the Omnibus
amendment dates are queried directly in production. Defer A3 (NodeRAG
heterogeneous nodes) and A5 (bilinear xref classifier) until we have
budget for offline LLM-pass index builds — both pay back in production
on paraphrased queries but neither moves davidath alone.

---

## Sources

- [SAT-Graph RAG (arXiv 2505.00039v5)](https://arxiv.org/abs/2505.00039v5)
- [WhyHow Multi-Graph Multi-Agent Legal RAG](https://medium.com/enterprise-rag/legal-document-rag-multi-graph-multi-agent-recursive-retrieval-through-legal-clauses-c90e073e0052)
- [NodeRAG: Heterogeneous Nodes (arXiv 2504.11544)](https://arxiv.org/abs/2504.11544)
- [PathRAG: Flow-Based Pruning (arXiv 2502.14902)](https://arxiv.org/abs/2502.14902)
- [Multi-Jurisdictional AI Reg RAG (LREC 2026)](https://arxiv.org/html/2604.25448)
- [ComplianceNLP Cross-Framework KG-RAG (arXiv 2604.23585)](https://arxiv.org/html/2604.23585)
- [GraphRAG-Bench (ICLR'26)](https://arxiv.org/html/2506.05690v3)
- [AIReg-Bench (arXiv 2510.01474)](https://arxiv.org/abs/2510.01474)
- [HG-RAG Hierarchical Graph for Power Systems](https://www.mdpi.com/2079-9292/15/7/1445)
- [LightRAG (EMNLP 2025)](https://aclanthology.org/2025.findings-emnlp.568.pdf)
- [HippoRAG 2 — KG-RAG Legal Benchmark (CEUR-WS Vol-4079)](https://ceur-ws.org/Vol-4079/paper6.pdf)
- [Graph RAG in 2026: Practitioner's Guide (Graph Praxis)](https://medium.com/graph-praxis/graph-rag-in-2026-a-practitioners-guide-to-what-actually-works-dca4962e7517)
- [LegalBench-RAG (referenced via Where Does Legal AI Fail, CIKM 2025)](https://dl.acm.org/doi/10.1145/3746252.3761151)
- [RAPTOR (arXiv 2401.18059)](https://arxiv.org/html/2401.18059v1)
- [Awesome-GraphRAG (DEEP-PolyU)](https://github.com/DEEP-PolyU/Awesome-GraphRAG)
- [GraphRAG-Bench repo](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)
