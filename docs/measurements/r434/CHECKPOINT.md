# R434 — evidence audit and hard-mode validation

## Scope

This round audited the four claims carried forward from R433: completeness,
citation discipline, grammatical tail repair, and the Neo4j Aura/ontology path.
The audit also checked the production-facing prompt and cache wiring rather than
assuming that a documented flag is active.

## Findings

### Completeness

The existing completeness guards remain explicitly gated and were not enabled by
this round. The prior evidence does not justify a new generation contract: the
need-proportional experiment exposed a miscalibrated estimator and the hard-mode
correctness cost was reproducible on two rows. No default was changed.

### Citation discipline

The global post-hoc pruning proposal remains rejected. The replay showed that
many apparent excess references are provisions actually described in the prose;
removing them can lose valid definitional or supporting citations. The safer
prompt-side minimality clause remains in place, with prose reconciliation as a
safety guard rather than a global deletion rule.

### Tail repair

The earlier easy-only result was insufficient evidence for hard mode. The gate
was extended to select a hard checkpoint and to score the generated arm files
with the hard rubric. On 25 strided hard rows, the two arms were paired over the
same 25 cut answers, with zero provider errors and zero incomplete shipped
answers:

| axis | splice | complete-sentence | delta |
|---|---:|---:|---:|
| Answer correctness (loose) | 98.9 | 98.9 | +0.0 pp |
| Answer correctness (strict) | 96.0 | 96.0 | +0.0 pp |
| Answer conciseness | 65.1 | 59.0 | -6.1 pp |
| Reference correctness (loose) | 100.0 | 100.0 | +0.0 pp |
| Reference correctness (strict) | 79.7 | 79.7 | +0.0 pp |
| Reference conciseness | 53.0 | 54.1 | +1.1 pp |
| Regulatory tone | 100.0 | 100.0 | +0.0 pp |
| Response speed | 93.5 | 91.8 | -1.7 pp |
| **Overall geometric mean** | **83.8** | **82.8** | **-1.0 pp** |

Both arms had 25/25 successful repairs, zero incomplete outputs, and zero
welds under the corrected final-sentence diagnostic. This is a valid hard-mode
sample, but it is not a ship signal: the sentence arm is slower and less
concise, with no correctness gain. The grammar repair remains unshipped.

### Neo4j Aura and ontology

The graph is not a primary retriever. `kg_context` uses Aura through a bounded,
circuit-breaker-protected executor only for hierarchy/context about already
selected references; the local hierarchy mirror is the fail-soft equivalent.
The point-text lever is modality-scoped, and the ontology citable expansion is
default OFF because its recorded replay admitted mostly excess references.
Those defaults are consistent with the evidence and were not widened.

Two real integrity defects were fixed and tested:

1. `articles_for_role()` and `applies_to_role()` now normalize authorised/
authorized representative aliases consistently, so ontology role queries cannot
silently return an empty obligation set.
2. Neo4j seeding now reconciles legacy `ART<N>` shadow Article nodes by writing
strict citation/number properties and preserving the verified Article →
OperatorRole edge direction. Deprecated `REQUIRES` edges are deliberately not
reintroduced because no production consumer reads them; copying them would
recreate the stale schema drift rather than improve retrieval.

The seed migration is idempotent and versioned. It was validated offline through
the payload/seed tests; no destructive Aura operation was performed.

## Validation

- R434 graph/ontology/seed tests: **46 passed**.
- Ruff and `git diff --check`: **passed**.
- R413 hard tail gate: **25 paired rows, zero transport errors**; table above.
- No completeness, citation-pruning, tail-repair, or graph-primary lever was
  enabled merely from a proxy or an easy-only result.

## Decision

Keep the current generation and retrieval defaults. Ship only the two grounded
integrity fixes and the corrected measurement harness/checkpoint. The next
answer-quality experiment should target a compact, modality-aware completeness
contract, but only with a pre-registered hard gate that measures correctness,
conciseness, reference heads, tone, and speed together.
