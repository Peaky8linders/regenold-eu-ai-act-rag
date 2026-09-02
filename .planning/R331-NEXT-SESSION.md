# R331 — next session: the reranker, done properly

Written at `e8e037c`. Read `CLAUDE.md` § Reranking (R329) and
`.planning/R329-PLAN-RANKER-AND-OVERCITATION.md` first.

---

> ## ⚠ CORRECTIONS APPLIED (R331, post-audit)
>
> Three defects in this document were found by auditing it against the tree.
> The TL;DR below is left intact for provenance; read these first.
>
> **C1 — the line number is wrong, and probably the function is too.** The
> Component D gate is `regenold.py:8713`, the append `:8719`. Line **8752 is
> inside the unrelated verbatim block**. More importantly, Component D is *not*
> the first prose→citation path: `_add_prose_named_refs` runs before it at
> `:8624` (and again at `:8919`) doing the same job, and Component D only fires
> for prose citations that pass did **not** already add. The repo's own measured
> comment at `regenold.py:4106` names the re-inflation sources — R138
> `_add_prose_named_refs` (cap 8), R133 `_surface_prose_subpoints` (+3), R260 —
> and **Component D is not among them.** Before gating Component D (S1),
> instrument which pass actually mints the wrong refs. The 79-wrong/145-right
> table is upstream's, not measured here.
>
> **C2 — the central inference rests on a number this repo marks invalid.**
> `docs/R329-SCORECARD-VS-FRONTIER.md:25` states it outright: *"recall 0.879 is
> not a measurement; precision 0.653 is"* — `gold_coverage 0/40`, so recall is
> judge memory. Trap #4 below says the same thing and the TL;DR then uses the
> number anyway. **Precision 0.653 is real and the over-citation is real.** What
> is *not* established is the localisation: "retrieval is doing its job" is
> derived solely from the invalid recall figure. Do not treat retrieval as
> exonerated.
>
> **C3 — `CLAUDE.md § Reranking` was stale and has been corrected.** It claimed
> the reranker was wired at `kb_search::top_articles_by_relevance`; nothing
> imported the module at all. It is now wired at Stage-2 graph-context selection
> (S2) with a call counter — see `CLAUDE.md` and
> `tests/test_r331_rerank_placement.py`.
>
> **C4 — R327 semantic layers were default-ON and inert; FIXED by R330.**
> `kg_context._render_semantic_layers` returns `[]` when `question` is falsy
> (`kg_context.py:478`) and the only call site never passed one, so a feature
> documented as active had never emitted a line. Found independently by R331
> and by a concurrent R330 session; **R330's fix landed** — it passes
> `context.question` (populated at `_graph_rag_impl.py:5708`) and flips
> `REGENOLD_GRAPH_SEMANTIC_LAYERS` to default **OFF**, so repairing the wiring
> does not silently activate an unmeasured feature. Turning it ON is now a real
> lever: gate on `ab_judge`, watch latency (live Neo4j vector queries per
> request). R331's rerank sits between that fix and `render_kg_context` and is
> pinned not to re-break it.
>
> **C5 — S1's prerequisite does not exist here.** S1 says to gate Component D
> on "the retrieval-derived set". Upstream implements that with
> `_stage2_citable_reference_bases`, which has **zero occurrences** in this
> repo (`.planning/R329-PORT-AUDIT-RAW.md:224`). The set S1 names is undefined
> in this codebase — S1 is not implementable as written.
>
> **C6 — S1 is an arm this repo has already refuted.**
> `.planning/R330-PLAN.md:842-846`, filed under *do not resurrect*: Component D
> is "counterfactually **inert**" — the R138 pass subsumes it, simulating both
> arms on all 10 evidence rows loses **0** of the claimed 13 refs, and
> `_looks_like_scenario_shape` returns 0 scenario rows across all 38, so
> Component D is never uniquely reachable. Expect +0.0000 and do not misread it
> as "grounding does not help".
>
> **C7 — flipping the Component D gate discards the whole Stage-2 answer.**
> The `else` branch at `regenold.py:8721-8724` falls through to `:8726-8742`
> and sets `_stage2_landed = False`. S1 does not mention this; upstream's
> shipped version uses a bare `continue`. As written, S1 would tank the answer
> axes while trying to fix references.
>
> **C8 — S3's driver number is backwards, and the closed direction stands.**
> `AGENTS.md:107` closes thinking-budget latency tweaks.
> `docs/ROUNDS.md:4961-4968`: complex/4000 runs **p50 26.9 s** vs simple/0 at
> **41.8 s** — the opposite of S3's premise. `.planning/R330-PLAN.md:63-64`
> calls the −23.5 pp gap a **transport floor**. And "shortening is free" is a
> measured trade, not free: `app/integrations/regenold/models.py:1418-1426`,
> paired A/B, answer_conciseness **+0.095** but answer_correctness **−0.143**,
> worth ~+0.36 Speed pp of a 23.5 pp gap. AnsCon is also *peaked* (`ratio²`,
> symmetric — `evals/bench/metrics.py:295-310`): the arm that scored 93.4 had
> MORE sentences and FEWER chars than today's, so "1-4 sentences" is the wrong
> target.
>
> **C9 — the 79-wrong/145-right table is not ours.** It is upstream, EASY-mode,
> n=100, baseline 0.6960. Arithmetically impossible against our HARD run
> (55 wrong / 73 correct / 132 refs), and its four causes sum to 110 > 97
> judged-wrong — overlapping counterfactuals, not a partition. `Article 34`
> appears nowhere in any `.evalout/r330/*.json`.
>
> **C10 — "instrumented with a call counter, not inferred" was not true.**
> `git show 942404d:app/engines/cohere_rerank.py` has no counter; only the
> post-hoc-reorder row has a committed artifact. R331 adds the counter
> (`rerank_stats()`).
>
> **⚠ C11 — the central diagnosis is INVERTED for its own worked example.**
> `Article 43` is emitted by DETERMINISTIC retrieval, not by prose. R330's own
> instrumentation records `det_refs = ["Article 6","Article 43","Annex I",
> "Annex VI","Annex VII"]` for `july7-119` (`.evalout/r330/attribution_v3.json`),
> attributed `ENGINE:kb`. Reproduced under code defaults with Stage-2 off: still
> emitted, provenance `kb-conformity-Art. 43`, minted at
> `_graph_rag_impl.py:5886-5897` from `EC_CHECKER_OBLIGATION_MAP`. So the claim
> "these were never candidates, there is nothing for a reranker to reorder" is
> false — they ARE retrieval output. **The ranker lever is alive; R329 simply
> seated it wrong.** This reverses the handoff's headline conclusion.

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

> **⚠ C2 — this paragraph is the defect.** `recall 0.879` is not a measurement
> (`gold_coverage 0/40`; see Trap #4 and `docs/R329-SCORECARD-VS-FRONTIER.md:25`),
> so "retrieval is doing its job" does not follow from it. Precision 0.653 is
> text-grounded and stands: we emit wrong references. Where they are minted is
> still open — see C1.

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
