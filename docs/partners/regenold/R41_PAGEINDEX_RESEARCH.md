# R41 — PageIndex (VectifyAI) Research

**Source**: <https://github.com/VectifyAI/PageIndex> · MIT licensed · Python (LiteLLM-based).

## A. What is PageIndex really doing?

Two-phase pipeline:

1. **Tree build (offline)**: an LLM walks the source PDF/Markdown and emits a
   JSON Table-of-Contents — `{node_id, name, description, sub_nodes,
   metadata}` — with an LLM-generated summary at every node. Tunables:
   `if_add_node_summary`, `max_tokens_per_node`, `summary_token_threshold`.
   Multiple LLM passes (structure extraction + summarisation).
2. **Query (online)**: an **agentic loop** — read top-level ToC, LLM picks a
   branch, drill down, extract, evaluate sufficiency, loop or answer.
   Multiple sequential LLM calls per query (no published bound). Default
   model: `gpt-4o-2024-11-20`.

**Differences vs our stack**:

| Dimension                | PageIndex                          | Our `eu_ai_act_tree.py`               |
| ------------------------ | ---------------------------------- | -------------------------------------- |
| Tree build               | LLM-summarised, per document       | Deterministic regex parse of EUR-Lex prose |
| Node summaries           | LLM-generated text                  | None (raw paragraph text)              |
| Retrieval                | LLM-agentic descent (multi-call)   | Not yet wired (R32 built, R33+ defers) |
| Determinism              | LLM-driven, non-reproducible        | Byte-for-byte deterministic           |
| Latency per query        | Seconds (multi-LLM round-trip)      | ~6.8 ms p50 (entire route)            |

PageIndex's "innovation" is **replacing the embedding step with LLM-generated
summaries** and **replacing top-k retrieval with LLM tree-walk**. It's
TOC-RAG with an agentic loop.

## B. Integration vectors

| Layer                            | Verdict           | Why                                                                                                |
| -------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------- |
| Article retrieval (BM25 + emb)   | **Not a fit**     | Our 348-doc BM25 corpus is saturated; LLM tree-walk costs seconds where we cost ms.                |
| Sentence extraction              | **Not a fit**     | `sentence_index.py` + `select_answer_sentence` already does deterministic question-type-aware picking with affinity bonuses. PageIndex would add 1–5 LLM calls. |
| Cross-reference traversal        | **Not a fit**     | `graph_expand_2hop.py` over Neo4j gives us deterministic 2-hop xref in <50 ms; PageIndex offers no equivalent. |
| Hierarchical tree (eu_ai_act_tree) | **Partial — concept only** | The tree is built (1,426 nodes) but unwired. PageIndex's *agentic-descent* idea is interesting for **rare paraphrased queries that miss BM25**, but our tree is regex-built and node summaries are absent. Borrow the **per-node summary** idea if we ever wire LLM-aided descent. |

## C. Cost-benefit on Regenold rubric

| Axis              | Expected lift          | Rationale                                                       |
| ----------------- | ---------------------- | --------------------------------------------------------------- |
| Ans Strict        | +0.00 to +0.01         | Sentence picker already saturated by R34. PageIndex's win is on long unstructured PDFs, not a 1426-node deterministic tree. |
| Ref Strict        | +0.00 to +0.02         | Possible on Regenold probe (paraphrased queries) where xref+embeddings miss. But adds zero on davidath. |
| Ref Conciseness   | **Negative**           | Agentic descent tends to surface broader sections (whole article > paragraph). Likely -0.02 to -0.05. |
| Latency p50       | **+500 ms to +3000 ms** | Each query fires 3–8 sequential LLM calls. **Catastrophic** vs our 6.83 ms p50 budget. |

PageIndex's headline 98.7% FinanceBench number is on **long unstructured 10-K
PDFs without a TOC**, where the LLM-built TOC adds real value. The EU AI Act
already has a perfect statutory TOC — we parsed it deterministically in 86
LOC.

## D. Risk register

- **LLM dependency doubles wrapper traffic.** We already burn one Claude
  Haiku call per query for query expansion. Adding an agentic loop (3–8
  calls minimum) would push wrapper RPS through the `RATE_LIMIT_CHAT_PER_MINUTE=10`
  ceiling on any non-trivial traffic.
- **Latency violates rubric.** Regenold rubric weights latency; p50 going
  from 6.83 ms to seconds is a tier-drop.
- **Non-determinism breaks audit chain.** Our `evidence/store.py` hash-chains
  question+answer pairs. PageIndex's LLM descent returns different paths on
  identical inputs — the chain becomes "audit theatre" not audit-tamper-evident.
- **License OK** (MIT, no conflict with our Apache-2.0).
- **Maintenance burden HIGH.** LiteLLM + per-document tree-build script +
  pinned `gpt-4o-2024-11-20` model. We'd own a second LLM provider path.
- **No benchmarks against tuned BM25 hybrid.** The 98.7% number is vs
  vanilla vector RAG. Our hybrid (BM25 + embeddings + Neo4j 2-hop + xref +
  CLARA + extractive QA + cross-encoder rerank) is already past where
  PageIndex's comparison sets stop.

## E. Recommendation: **NO**

Our retrieval surface already does what PageIndex offers — and does it
deterministically, in milliseconds, with an auditable hash-chain. The one
borrowable concept (per-node LLM summaries on the existing
`eu_ai_act_tree.py` to support a future agentic-descent path) is a
**Round-42+ exploration**, not a Round-41 integration. We have closer wins
queued (Layer-G citation-guard threshold tuning, AIR-Bench wire-up, CLARA
priority-matrix expansion) with smaller risk and clearer rubric paths.

## Sources

- [VectifyAI/PageIndex GitHub](https://github.com/VectifyAI/PageIndex)
- [PageIndex Introduction (blog)](https://pageindex.ai/blog/pageindex-intro)
- [Reasoning-Based RAG concept docs](https://www.mintlify.com/vectifyai/pageindex/concepts/reasoning-based-rag)
- [The Hidden Cost of 98% Accuracy — Tao An, Medium](https://tao-hpu.medium.com/the-hidden-cost-of-98-accuracy-a-practical-guide-to-rag-architecture-selection-6883adc5289c)
- [MarkTechPost — Mafin 2.5 + PageIndex announcement](https://www.marktechpost.com/2026/02/22/vectifyai-launches-mafin-2-5-and-pageindex-achieving-98-7-financial-rag-accuracy-with-a-new-open-source-vectorless-tree-indexing/)
- [PageIndex RAG vs Traditional RAG — Shubham Vedi, Medium](https://medium.com/@shubhamnv2/pageindex-rag-vs-traditional-rag-i-tested-both-heres-what-actually-works-in-2026-5a990726a80f)
