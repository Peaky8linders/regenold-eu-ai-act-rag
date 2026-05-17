# R41 — PageIndex Decision

## Verdict: **NO**

PageIndex (VectifyAI, MIT) is a *vectorless, LLM-agentic tree-walk* RAG
framework. Its FinanceBench 98.7% win comes from replacing dumb chunking on
long unstructured 10-K PDFs with an LLM-generated Table of Contents — a
problem we don't have, because the EU AI Act already ships with a perfect
statutory TOC that we parse deterministically into 1,426 nodes in
`app/data/eu_ai_act_tree.py`. The agentic descent fires 3–8 sequential LLM
calls per query (default `gpt-4o-2024-11-20`, no published latency bound),
which would blow our 6.83 ms p50 budget by 2–3 orders of magnitude, double
our wrapper traffic past `RATE_LIMIT_CHAT_PER_MINUTE=10`, and make the
`evidence/store.py` audit chain non-reproducible. The single borrowable
concept — per-node LLM summaries to enable a future agentic-descent path on
our existing tree — is a Round-42+ exploration on the unwired tree, not a
Round-41 dependency adoption. Closer rubric wins are queued (CLARA matrix
expansion, citation-guard threshold tuning, AIR-Bench probe wire-up). Pass.

See `R41_PAGEINDEX_RESEARCH.md` for the full integration-vector matrix,
rubric-axis estimates, and risk register.
