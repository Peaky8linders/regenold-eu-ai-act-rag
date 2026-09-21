# R433 — quota-aware query-denoiser failover

## Finding

The denoiser already had a provider chain, but a durable provider quota response (for
example Groq TPD exhaustion) was retried on every request. That repeatedly paid the
same failed call before reaching the next provider. This was an operational reliability
and latency defect, not an answer-quality claim.

## Fix

`app/routes/regenold.py` now keeps a short, provider-specific process-local cooldown
(default 60 seconds, bounded to 15 minutes) after recognized durable quota errors.
Normal network/5xx errors are not classified as quota exhaustion. A successful call
clears that provider's cooldown. The cooldown setting is part of the engine cache key.
The fallback chain remains unchanged: another configured provider is attempted, and
only then does the existing deterministic salvage path run.

## Validation

- Focused R433/R148/R432 transport tests: **17 passed**.
- Existing transport/security and fallback tests: **43 passed**.
- Completeness, tail-repair, citation-grain, and citable-base regression tests:
  **239 passed**, one pre-existing dependency deprecation warning.
- No live benchmark was run: this change affects provider retry behavior, not the
  answer contract, and live quota usage would not add evidence beyond the seam tests.

## Scope decision

The other roadmap items remain gated. No unconditional full-system prompt, global
reference pruning, graph-primary retrieval, or unmeasured tail/completeness repair
was enabled by this round. Those changes require their own paired hard-mode evidence.
