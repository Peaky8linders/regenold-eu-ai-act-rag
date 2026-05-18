"""R50 — LLM-as-Judge for the regenold EU AI Act competition.

Consumes a bench JSON sidecar (from ``evals.bench.runner`` or
``evals.regenold.runner_v2``) plus the per-row ``reasoning`` field
populated by the route's ``?include_reasoning=true`` mode, and emits
per-row failure-mode diagnoses via four separate single-axis judge
prompts.

The judge is intentionally separate from the deterministic eval
runner — it catches SEMANTIC failures (cite-substance mismatch,
boilerplate hedging, tone drift) that token-overlap metrics miss.

CLI: ``python -m evals.judge.runner --bench-sidecar <path> --label r50``
"""
