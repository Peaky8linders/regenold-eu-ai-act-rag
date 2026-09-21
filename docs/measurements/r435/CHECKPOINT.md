# R435 — live evidence audit and retrieval-provider resilience

## Evidence reviewed

The latest complete published hard board remains R419 (110/110 rows): overall
72.48%, Ans Loose 94.15%, Ans Strict 90.91%, Ans Conciseness 44.19%, Ref Loose
96.08%, Ref Strict 70.59%, Ref Conciseness 44.79%, Regulatory Tone 93.64%, and
Response Speed 70.83%. Its judge remarks identify generation-side verbosity,
sub-point grain, and pushback capitulation as the remaining quality gaps; the
metric formulas reproduce from the stored rows.

The R435 six-row pushback probe was **not a valid board**. The first two draws
were incomplete (the live wrapper failed before all six rows), and a stale
Python 3.12 runner was concurrently writing the same checkpoints as the
current `.venv` runner. The stale process was stopped; no partial R435 numbers
were promoted or compared. This is intentionally treated as an operational
failure, not as evidence for or against the pushback contract.

Observed in the same live log: Cohere returned HTTP 429 for embeddings, then
retrieval fell back to the deterministic SVD path. Neo4j also emitted a
`db.index.vector.queryNodes` deprecation warning. The latter is compatibility
noise, not a proven answer regression; migrating the Cypher syntax without a
version-pinned Aura compatibility gate would be speculative.

## Grounded change

`external_embeddings` now marks a Cohere 429 as a bounded process-local quota
cooldown (60 seconds by default, configurable up to one hour). Subsequent
queries skip the exhausted provider and use the existing SVD fallback instead
of paying repeated retries. The cooldown setting is part of the route engine
cache key. Ordinary network/5xx failures retain the existing transient retry
behavior; no retrieval or answer-quality default was changed.

## Validation

- External embeddings and R112 regression tests: **36 passed**.
- Ruff and `git diff --check`: passed.
- No R435 quality delta is reported because the live sample was incomplete and
  void under the transport/provenance rule.

## Next measurement

Re-run a clean, single-owner significant pushback sample with primary and
Bedrock provenance recorded per row. Only after that sample is complete should
the full 110-row hard evaluation be launched.
