# R325 — live A/B of the R323/R324 knowledge-graph Stage-2 context

**Date:** 2026-08-08 · **Run:** `wf_ca4b4812-a19` · 67 agents, 0 errors, 28.0 M tokens
**Harness:** `evals/harness/faithful_graph.py` + `evals/harness/graph_ab_prompts.py`

## Result

**Wash at best; not shippable as-is.** The graph context buys a large, clean win on
answer correctness and pays for it with a larger, cleaner loss on conciseness — the
one axis the official scorecard says we lead, i.e. the axis with zero headroom. The
two axes that would justify the trade are washes. And the adversarial audit refuted
**both** ON wins it examined as artifacts, so the winning axis rests on the weakest
mechanism.

| axis | ON | OFF | tie | order-split | decisive n | two-sided sign p |
| --- | --- | --- | --- | --- | --- | --- |
| answer_correctness | **24** | 2 | 31 | 13 | 26 | **1.05e-05** |
| reference_correctness | 7 | 10 | 44 | 9 | 17 | 0.629 — **ns** |
| citation_faithfulness | 10 | 4 | 54 | 2 | 14 | 0.18 — **ns** |
| conciseness | 0 | **35** | 22 | 13 | 35 | **5.8e-11** |

A win counts only where BOTH judge position-orders agree; everything else is a tie.
Reference correctness and citation faithfulness reach nothing — do not report them
as leaning either way.

**`gold_dropped = []`.** Zero gold references present in the OFF arm were lost in
the ON arm. Hard rule #8 does **not** fire. Necessary, not sufficient: it clears the
R142.1 trap and says nothing about the over-citation the audit found ON adding.

## The audit is the headline

2 of 2 audited ON wins REFUTED. 2 of 4 audited OFF wins REFUTED. 2 confirmed, both
narrow and single-row.

The mechanism, re-verified by hand on `paper_st_v4:st_v4_002` (gold `Article 5`):

```
bare "Article 5" occurrences     OFF: 0    ON: 1
ON context: "...unless they are placed on the market or put into service as
             high-risk AI systems or as an AI system that falls under
             Article 5 or 50."
provision headings  OFF: []      ON: ['Article 2', 'Article 3']
ON-only delta: +10,793 chars
```

So the ON arm won answer *and* reference correctness by citing Article 5, which
reached it **only** as an incidental cross-reference buried inside another
provision's body — an ungrounded citation, explicitly forbidden by the delivered
prompt ("do NOT cite anything here that is not already listed above"), credited
because it happened to land on gold. That is the over-citation failure mode this
system is trying to suppress, scored as a win.

And the +10,793 chars added **zero new provisions** — it re-rendered Article 2 and
Article 3 at paragraph granularity, both already present in OFF. Bulk, not coverage.
Consistent with R319's measured 2.5% gold precision on hop-added content.

Two further reasons not to over-read the answer axis:

* one injected sentence on that row produced **three** decisive axis verdicts, so the
  four axes are not independent and treating them as four tests overstates the
  combined evidence;
* OFF's conciseness sweep is near-mechanically entailed by injecting +11.7 k chars.
  It is a real cost, but it is not independent corroboration.

**Judge reliability:** 13 of 70 rows (19%) flipped with judge position order on
answer correctness and on conciseness — the two axes carrying the significance are
the least order-stable.

## Setup

156 paired Stage-2 prompts assembled from the real system with the real seeded graph
payload. **156/156 are treatment rows** — the graph changes every prompt — at a mean
of **+11,746 chars**. A stratified 60 were answered by frontier models acting as the
Stage-2 generator in both processing orders, then judged on four axes in both
position orders, then the decisive wins were put to adversarial verifiers instructed
to default to REFUTED and to look specifically for length artifacts, over-citation
artifacts, and noise.

## Limits — stated, not hedged

* **No live Neo4j Aura.** Both bolt/7687 and `*.databases.neo4j.io` over HTTPS are
  proxy-blocked (`CONNECT` 403), and no `NEO4J_*` credentials exist in this checkout.
  An in-process stand-in answered the real queries from the seeder's own payload. It
  is faithful to the DATA and structurally incapable of catching a Cypher error, an
  edge-name drift (the R99.1 class), or an Aura latency path.
* **No live Stage-2 wrapper, and not the production model.** Frontier models stood in
  for production Opus 5. The answer→reference coupling (`_add_prose_named_refs`, the
  R72 reconcile) is model-dependent, so these reference verdicts do not transfer.
* **Answers were not persisted** — the prompt file holds prompts only, so two
  verifiers reconstructed by prompt forensics and the run is not independently
  re-auditable. Fix before the next run.
* **Bookkeeping mismatch:** every axis sums to 70 rows against 60 stratified rows
  requested; generation agents appear to have returned rows beyond their assigned
  slice. The direction is far too large for 10 rows to flip, but reconcile before any
  number here is cited again.

## Recommendation

**Do not ship the graph context as-is. Gate it, and fix the renderer before
re-measuring.** Both changes target the measured defect — unfiltered inflation, not
absent coverage:

1. **Cap the merged obligation set and require term overlap with the ORIGINAL
   question** — R319's bounded-hop prescription, still unimplemented.
2. **Suppress paragraph-level re-render of provisions already present verbatim** in
   the base context, and strip incidental cross-references from non-retrieved
   provisions. That single class produced every refuted verdict in this run.

What would settle it, in order: persist answers; run `.evalout/r319/context_delta.py`
to isolate the movable rows and A/B that treatment population only, with ≥2 repeats
per arm and the engine LRU cleared, so there is a measured noise floor; score with
`evals.harness.easyhard_ab` (count-ratio conciseness — `ab_judge`'s refs axis has no
minimality term, which is how R142.1 slipped) computing `gold_dropped` at **sub-point**
grain; gate any reference movement on the **full 476**, not `--qa-only` (hard rule #7);
and run it against real Aura with real credentials and production Opus 5.
