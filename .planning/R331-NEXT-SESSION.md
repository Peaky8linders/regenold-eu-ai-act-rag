# R331 — next session: the reranker, done properly

Written at `e8e037c`. Read `CLAUDE.md` § Reranking (R329) and
`.planning/R329-PLAN-RANKER-AND-OVERCITATION.md` first.

---

## TL;DR — the one finding that changes the plan

**A reranker cannot fix this over-citation, because the wrong references never
pass through retrieval ranking.** They are minted from the model's own prose
after retrieval, at `app/routes/regenold.py:8752`:

```python
if catalog_key in ARTICLE_EXISTENCE:
    references.append(cite)          # <- the ONLY gate is catalog existence
```

Any article the model *names in prose* becomes a wire citation, gated solely on
"does this article exist in the EU AI Act", never on "was it retrieved".
`Article 43`, `Article 34`, `Annex I` were never candidates — so there is
nothing for a reranker to reorder.

This also explains the otherwise-puzzling shape of the measurement: reference
**precision 0.653** against **recall 0.879** at a mean of only **3.30 refs**.
Retrieval is doing its job; a post-hoc pass appends unretrieved articles.

### Proven dead ends — do not repeat these three

All three were instrumented with a call counter, not inferred:

| placement | result |
| --- | --- |
| reorder the FINAL emitted refs | fires, but **worse** — wrong-ref tail position 0.582 → 0.562 |
| inside `kb_search.top_articles_by_relevance` | **0 calls** — BM25 is gated behind `if not entities:`, so anchored questions never reach it |
| route candidate list before the budget cut | **0 calls** — `candidates` is already within budget; the cut is a no-op |

---

## State — what is on `main` and works

* `app/engines/cohere_rerank.py` — Cohere `rerank-v3.5` client. **Default OFF**
  (`REGENOLD_COHERE_RERANK`), fail-open, reorder-only. `COHERE_API_KEY` is in
  `.env` and on Railway. Verified live: on a hand-built probe it separates
  `Article 50(3)` **0.9244** from `Article 19` **0.0394** and `Article 99`
  **0.0090**, so the model is good — it was simply pointed at the wrong stage.
* `tests/test_r329_cohere_rerank.py` — 8 tests pinning permutation /
  never-drop / fail-open. All pass.
* AWS Bedrock rerank is **available in `eu-central-1`** (`amazon.rerank-v1:0`,
  `cohere.rerank-v3-5:0`; `eu-west-1` has neither) but **unreachable**: Rerank
  lives in `bedrock-agent-runtime`, which requires SigV4 and rejects the
  `AWS_BEARER_TOKEN_BEDROCK` this deploy holds (`IncompleteSignatureException`,
  measured). Needs IAM creds with `bedrock:Rerank` — a provisioning task, not a
  code task. Prefer it over Cohere once available: EU residency.

---

## The plan, in order. Do NOT reorder S0.

### S0 — port `gold_dropped_head`. Blocks everything else.

`gold_dropped` exists **nowhere in this repo**, so the standing rule "a
reference change must drop ZERO gold" is currently **unenforceable**. Every
step below changes which references ship, so without this you are flying blind —
this is exactly how R142.1 lost a live pairwise 11-0 (refs p=0.001).

* Port from the eval repo: `git show eval-repo/main:evals/bench/metrics.py`,
  function `gold_dropped_head`. It needs **zero new dependencies** —
  `_gold_ref_set`, `article_head`, `article_heads` are already byte-identical
  here. Wire it into `evals/harness/easyhard_ab.py::_score_row` + `_aggregate`.
* ⚠ **Do NOT port `ref_crag_fine` / `gold_dropped_exact`.** Measured defective:
  gold is head-projected by `_gold_exact_refs` while predictions keep full
  coordinates, so `['Article 5.1.f','Annex III.2']` against gold
  `['Article 5','Annex III']` scores `gold_dropped_exact = 2` and
  `ref_crag_fine = -1.0` — it penalises the most accurate citation shape the
  system emits. Details in `.planning/R329-PORT-AUDIT-RAW.md`.
* ⚠ **Never wholesale-copy `evals/harness/easyhard_ab.py` from upstream.** Ours
  never received R327; copying drags in an axis rename
  (`ref_loose` → `ref_loose_head_recall_proxy`) that breaks comparability with
  every recorded run here.

### S1 — the actual over-citation fix: ground Component D

Add a flag (upstream calls it `REGENOLD_COMPONENT_D_CITABLE_ONLY`), **default
OFF**, that changes the gate at `app/routes/regenold.py:8752` from "exists in
`ARTICLE_EXISTENCE`" to "exists AND is in the retrieval-derived set". This is a
**grounding predicate**, not a positional trimmer, so it is outside the five
refuted trimmer families (`.planning/R318-PLAN.md` §1).

⚠ **It will drop some gold.** Upstream's measured table: Component D is the
largest source of wrong refs (79) **and by far the largest source of right ones
(145, 65% correct)**. Deleting it is strongly net-negative; restricting it to the
grounded subset is the hypothesis. This is precisely why S0 comes first.

Gate: `easyhard_ab` (gold-bearing) with **`gold_dropped == 0` as a hard reject**,
reading Ref Strict (F1) + Ref Conciseness, with Ref Loose as the recall guard.
NOT `ab_judge` — its refs axis has no minimality term, so it prefers the
superset by construction and cannot validate a precision fix.

### S2 — where the reranker CAN still pay: answers, not references

The untested hypothesis. Reranking the retrieved provision pool changes which
provision TEXT reaches Stage-2, which should move **Ans Strict — the biggest gap
to frontier (60.6% vs 84.8%, −24.2 pp)** and the lowest axis in a geometric
mean. It does not need to touch the reference list at all.

Insert where Stage-2 context is assembled (`_build_context_references_block` /
`kg_context` selection), not in the reference path. Then:

1. **Prove it FIRES** with a call counter before reading any number. All three
   previous placements silently no-oped. Byte-identical is what inert looks like.
2. Gate on `ab_judge` (it moves answers, not refs).
3. Watch latency on the branch arm — Speed is 61.7%, our second-worst axis, and
   live p50 is already 57.3 s.

### S3 — Speed. Cheapest points on the board, independent of everything above.

−23.5 pp to frontier, second-lowest axis, and it needs no legal reasoning.
`complex_thinking_tokens = 4000` is the known driver. Also free: **58% of
answers exceed the rules' "1-4 sentences" guidance** (median 5, max 8) while
Ans Conciseness still scores 93.4%, because it is graded against an exemplary
answer rather than the literal rule. Shortening buys Speed without spending the
one axis we beat frontier on.

---

## Traps that will burn you

1. **`REGENOLD_COHERE_RERANK` is NOT in `_engine_cache_key`.** If you A/B it as
   an *engine*-level flag, arm B replays arm A's cache and every axis reads
   +0.0000. That already happened once. Route post-processing (like
   `adaptive_ref_clamp`) is deliberately kept OUT of the key because the route
   re-runs on cache hits — engine-level changes must be IN it. Know which you are.
2. **Prove the feature fires.** Counter-instrument it. Three placements returned
   0 calls this round while looking plausible in the diff.
3. **`evals/regenold/run_evaluator_batch_july7.py` never calls `load_dotenv()`.**
   Export `OPENAI_API_BASE`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`
   (`.env` has duplicate keys — `tail -1`). Otherwise the run reaches Cloudflare,
   gets **HTTP 401**, and reports `errors=0` with a full set of plausible
   deterministic numbers. **Read `stage2_landed_rate` and `latency_p50` before
   anything else** — live Stage-2 is ~57 s p50 per hard row; sub-second means you
   measured the fallback. The repo's own error text misattributes this 401 to an
   expired Claude-Max OAuth token; the `aud` claim proves it is Cloudflare Access.
4. **`gold_coverage = 0/40` on the July-7 batch.** No gold refs exist, so the
   grounded judge's reference RECALL is model memory, not measurement. Precision
   is text-grounded and real. Do not quote that recall as a result.
5. **regenold's metric formulas are UNDISCLOSED.** The rules PDF gives prose;
   the preview says details come in the final report. You cannot reproduce their
   numbers — quote their scorecard, report the judge separately, never subtract.
6. **Multiple sessions edit this tree.** Check `git status` before editing
   `app/routes/regenold.py` / `_graph_rag_impl.py`. A commit of mine landed on
   another session's branch this round. Never `git add -A` — `.claude/worktrees/*`
   are gitlinks.

## Do NOT re-propose

* Any positional / identity / prose-shape reference trimmer — five families
  refuted (`.planning/R318-PLAN.md` §1).
* RRF fusion — measured a wash three times (`docs/ROUNDS.md` R31/R69) and
  already exists at `turboquant_index.py:539` behind `REGENOLD_RRF_FUSION`,
  default OFF.
* Post-hoc reordering of the emitted reference list — measured −0.019 this round.
* Local torch/GPU rerankers — `AGENTS.md` forbids them and Railway is CPU-only.
  A hosted API is the only viable shape.
