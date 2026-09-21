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

## Deployment status

Commit `c4756cf` passed CI and is present in the GitHub production deployment
queue, but the deployment status is still `in_progress`; `/healthz` continues
to report the prior serving commit `91d40b6`. The full hard run is therefore
held until `/healthz` reports `c4756cf`. No claim of redeployment is made yet.

## Next measurement

The six-row live sample completed on the current source with both arms primary
served and zero errors. Bedrock Qwen-235B judging (three repetitions) completed
on both arms. OFF → ON was: Ans Loose 95.45 → 95.45 (0.00 pp), Ans Strict
83.33 → 83.33 (0.00 pp), Ans Conc 45.45 → 46.40 (+0.95 pp), Ref Loose 100.00
→ 100.00 (0.00 pp), Ref Strict 75.00 → 58.33 (-16.67 pp), Ref Conc 32.50 →
33.33 (+0.83 pp), Tone 100.00 → 66.67 (-33.33 pp), Speed 64.65 → 69.34
(+4.70 pp), and Overall 69.90 → 65.33 (-4.57 pp). This is a six-row signal,
not a ship gate; the correctness and tone regressions mean the contract remains
OFF pending a larger valid hard gate. The Bedrock judge's row remarks were
`rg_069` partial correctness/tone fail and `rg_088` tone fail on the ON arm.

Only after deployment is confirmed by `/healthz` should the full 110-row hard
evaluation be launched.
