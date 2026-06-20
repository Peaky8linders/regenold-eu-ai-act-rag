"""R138-eval — the live pairwise-judge A/B win-measure harness.

The davidath bench (``evals/bench/runner.py``) is a deterministic REGRESSION
GUARD: it runs ``provider=cli`` (no Sonnet), so it cannot see any Stage-2 /
synthesis / live win, and its token-overlap metrics diverge from the
competition's judge-style scoring (R99.2: verbatim token-recall blind to a
0.25 judge-correctness). Thirty-plus rounds therefore end with the same
caveat — "byte-identical, win lands live, confirm post-deploy".

This package is that confirmation, made a first-class, repeatable, pre-merge
gate instead of a manual ritual:

* ``probe_set`` — one consolidated, weakness-targeted, gold-bearing probe
  corpus (paper-V4 + V2 tricky/multiturn), each row tagged by source +
  category + weakness axis.
* ``pairwise_prompts`` — 4 per-axis PAIRWISE judge renderers (A-vs-B), derived
  from the absolute ``evals/judge/prompts.py`` rubric.
* ``ab_judge`` — runs each probe row through the route under two env-defined
  arms (baseline vs branch) via the in-process TestClient + the local Claude
  Max wrapper, then a position-swapped pairwise judge aggregates a per-axis
  WIN-RATE + sign-test p-value. Pairwise + position-swap + win-rate is
  variance-robust where the existing absolute A/B (``graphrag_ab``) is only
  valid when one arm is deterministic. A deterministic tier (no Sonnet) scores
  deterministic-only changes for free; a no-wrapper fallback never substitutes
  token-overlap as a win proxy.
"""
