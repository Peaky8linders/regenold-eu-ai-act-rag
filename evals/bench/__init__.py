"""Reproducible competition benchmark for the Regenold EU AI Act rubric.

Consumes the SHA-pinned ``davidath/ai-act-evaluation-benchmark`` dataset
(qa_pairs.json + scenarios.json) and scores the Regenold wire contract
against all 8 rubric axes from the 2026 competition rules:

    * Answer Correctness (Loose)
    * Answer Correctness (Strict)
    * Answer Conciseness (vs gold length)
    * Reference Correctness (Loose — recall of gold articles)
    * Reference Correctness (Strict — exact-set match)
    * Reference Conciseness (citation over/under-shoot)
    * Latency (p50, p95, max)
    * Regulatory Tone (rubric-derived heuristic)

Plus a multi-turn coherence pass on chained scenarios.

Results are written to:
    1. `evals/bench/results/<label>.json` (human-readable summary).
    2. `evals/bench/results/ledger.sqlite` (durable local ledger).
    3. The audit-chain store (Postgres when `DATABASE_URL` is set, else
       in-memory) under EvidenceEntryType.BENCHMARK_RUN.
"""
