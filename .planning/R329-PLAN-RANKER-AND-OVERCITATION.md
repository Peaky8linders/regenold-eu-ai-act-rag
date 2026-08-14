# R329 — plan: fix over-citation, and the ranker (AWS path)

Written 2026-08-13 at `9dc786f`, on the back of the live HARD measurement in
`docs/R329-SCORECARD-VS-FRONTIER.md`.

---

## 0. What the measurement actually says

Grounded Sonnet-5 judge, n=40 live HARD rows, Opus 5 via the tunnel:

```
reference_correctness   precision 0.653   recall 0.879*   F1 0.749
answer_correctness      0.625 pass        mean factual 0.881
citation_faithfulness   0.800 pass
```
\* `gold_coverage 0/40` — recall is judge memory, NOT text-grounded. Precision is.

**Precision 0.653 against recall 0.879 is the whole diagnosis.** We retrieve the
right provisions and then add wrong ones. Every sampled judge failure is an
EXTRA reference, never a missing one:

> "over-citation of inapplicable transparency and product-safety provisions" ·
> "over-cited log-retention provision (Art 19) not tied to competent-authority
> documentation" · "cited an unrelated Chapter II prohibition (criminal-risk
> profiling) instead of ..."

### The distinction that matters for what to build

Over-citation here is **two different defects** and they need different fixes:

| | signature | status |
| --- | --- | --- |
| **(a) count blow-out** | a row ships far past its budget (`july7-299`: 11 refs) | **being fixed in a concurrent session** — R330 §3.1 start-anchor narrowing takes that row `[11] -> ['Annex III','Art. 6','Art. 27']` |
| **(b) wrong refs inside a normal-sized set** | mean 3.30 refs, yet precision 0.653 | **unfixed — this is the ranker problem** |

Measured split on the 40 rows: only **2 rows exceed 5 refs**. So (a) is a tail
phenomenon. The bulk of the precision loss is (b): ~1.1 wrong references per
answer inside an otherwise reasonable set. **No clamp can fix (b)** — a count
cut cannot know *which* of 3 refs is the wrong one. That is a ranking problem.

⚠ This is why the five refuted trimmer families (`.planning/R318-PLAN.md` §1)
all failed, and why R325 closed the ranker with "nothing beats the engine's own
`rank`, AUC 0.703". The trimmers were attacking (a) with positional rules while
the damage was in (b).

### One real gap found in (a), NOT covered by the concurrent fix

`adaptive_ref_clamp` (`app/routes/regenold.py:4416`, called at `:9024`) is the
last ref pass and is correctly ordered AFTER the three prose-mining passes
(`:8534`, `:8829`, `:8894`). But it returns early on `if not stage2_landed`.

Measured on the live run:

| | n | mean refs | max |
| --- | --- | --- | --- |
| Stage-2 landed (clamp runs) | 32 | **3.19** | 6 |
| Stage-2 missed (clamp skipped) | 8 | **3.75** | **11** |

The gate exists to keep davidath byte-identical ("Stage-2-gated, so davidath
(`provider=cli`, no wrapper) is byte-identical BY CONSTRUCTION"). That guarantee
can be preserved while closing the gap: clamp when Stage-2 was **attempted**
(i.e. `_stage2_provider_enabled()`), not when it **landed**. Under
`provider=cli` no attempt is made, so davidath stays byte-identical; under live,
a row whose Stage-2 call failed still gets capped.

**Do not implement this until the concurrent R330 work lands** — it touches the
same file and may subsume it.

---

## 2. The ranker — AWS path

### 2.1 Why a reranker is the right instrument here

* It attacks (b) directly: it reorders by *query-document relevance*, which is
  exactly the signal "is Art 19 on point for a documentation question" that the
  current lexical `rank` lacks.
* The HyPA paper's own ablation says the reranker — not the knowledge graph —
  is the load-bearing component (Correctness 0.8141 -> **0.8402**); the KG half
  LOSES without it.
* It respects `AGENTS.md`'s "No Torch / Heavy ML" rule **because it is a managed
  API**, not a local model. This is the constraint that has blocked every prior
  reranker attempt here (R32 built / R46 deleted as bench-negative; `bge-reranker-large`
  is torch+GPU and Railway is CPU-only).

### 2.2 Availability — MEASURED, not assumed

```
eu-central-1  rerank: ['amazon.rerank-v1:0', 'cohere.rerank-v3-5:0']   <- repo's BEDROCK_REGION
us-west-2     rerank: ['amazon.rerank-v1:0', 'cohere.rerank-v3-5:0']
eu-west-1     rerank: none
```

**Both models are in `eu-central-1`**, which is already `BEDROCK_REGION`. EU data
residency is preserved — the reason `eu-west-1` is listed is to record that the
obvious second EU region does NOT have it.

### 2.3 ⚠ BLOCKER — the Rerank API cannot be called with today's credentials

Rerank lives in **`bedrock-agent-runtime`**, not `bedrock-runtime`. Measured:

```
c.rerank(...)  ->  ClientError IncompleteSignatureException:
  Authorization header requires 'Credential' parameter.
  Authorization header requires 'Signature' parameter.
  Authorization header requires 'SignedHeaders' parameter.
```

This deployment holds **only `AWS_BEARER_TOKEN_BEDROCK`** (no
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`). `app/llm/bedrock_client.py::_create_client_with_auth`
works by building an **UNSIGNED** client and injecting `Authorization: Bearer …`
on `before-send`. The Bedrock API-key scheme is accepted by `bedrock` and
`bedrock-runtime` (which is why `list_foundation_models` and the existing Stage-2
path work) but **`bedrock-agent-runtime` requires SigV4** and rejects it.

**Prerequisite before any implementation work:** provision IAM credentials (user
or role) with `bedrock:Rerank` on
`arn:aws:bedrock:eu-central-1::foundation-model/amazon.rerank-v1:0`, and set
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on the Railway dashboard
(`railway.toml [deploy.envs]` is inert — R306). Until then this plan is not
buildable, and no amount of code will change that.

### 2.4 Design, once credentials exist

**Reorder-only. Never drop.** R142.1 lost a live pairwise 11-0 (p=0.001) by
dropping a gold ref. The reranker's job is to put the wrong refs at the TAIL so
the ALREADY-VALIDATED R281 `adaptive_ref_clamp` — which cuts from the tail and
measured +1.17pp — removes the right ones. Rerank supplies ordering; the
existing clamp supplies the cut. Neither is a new trimmer family.

```
candidates (engine rank)
   -> Bedrock Rerank(query, [provision_text...])       # reorder ONLY
   -> adaptive_ref_clamp (existing, budget-aware)      # cut from tail
```

* **Input documents = verbatim provision text**, which the repo already has
  (`app/data/provision_text.py::get_provision_text`, and the graph's 658
  Paragraph / 421 Point nodes). Do NOT rerank on article numbers — the model
  needs text.
* **Gate:** `REGENOLD_BEDROCK_RERANK`, default **OFF**. Register in
  `_engine_cache_key` only if it changes Stage-2 input; if it is pure route
  post-processing over cached engine output, keep it OUT (the R79 doctrine that
  makes the paired in-process A/B possible — same reasoning as
  `REGENOLD_ADAPTIVE_REF_CLAMP`).
* **Latency budget.** Speed is our second-worst axis (61.7%, −23.5 pp) and live
  p50 is already 57.3 s. One rerank call on ≤10 short documents should be
  ~100-300 ms, but it MUST be measured on the branch arm of every A/B — the
  cheapest inert-A/B detector, and here also a scored axis.
* **Fail-soft:** any error returns the input order unchanged. A reranker outage
  must never change the reference set.

### 2.5 Gate — this is the part that decides it

1. **Instrument first: port `gold_dropped_head`.** It does not exist anywhere in
   this repo, so hard rule #8 ("a reference change must drop ZERO gold") is
   currently **unenforceable**. It ports from the eval repo with **zero new
   dependencies** (`_gold_ref_set`, `article_head`/`article_heads` are
   byte-identical here). See `.planning/R329-PORT-AUDIT-RAW.md`.
   ⚠ Do **not** port `ref_crag_fine`/`gold_dropped_exact` as-is — measured
   defective: gold is head-projected while predictions keep full coordinates, so
   `['Article 5.1.f','Annex III.2']` against gold `['Article 5','Annex III']`
   scores `gold_dropped_exact = 2`, `ref_crag_fine = -1.0`. It penalises the
   most accurate citation shape we emit.
2. **Gate on `easyhard_ab`** (gold-bearing) with `gold_dropped == 0` as a hard
   reject, reading Ref Strict (F1) + Ref Conciseness, with Ref Loose as the
   R142.1 recall guard. NOT `ab_judge` — its refs axis grades faithfulness +
   gold recall with no minimality term, so it prefers the superset by
   construction and cannot validate a precision fix (this is written into
   `_adaptive_clamp_enabled`'s own docstring).
3. **Three runs, median with min/max.** Two runs with an *identical* baseline arm
   have changed 20/40 rows' refs here and sign-flipped all three reference axes.
4. **Prove it FIRES.** Byte-identical is also what inert looks like.

### 2.6 Expected value, stated honestly

Ref Strict is −18.1 pp to frontier and Ref Loose −15.9 pp, and precision 0.653 is
the mechanism. A reranker is the only untried instrument that targets it. But:

* R325 already measured that **nothing beat the engine's own `rank` (AUC 0.703)**
  — though that was a *local lexical* reranker, not a cross-encoder trained for
  query-document relevance. This is a genuinely different arm.
* The paper's gain came from reranker + adaptive params together, on a different
  corpus, with disclosed formulas. Ours are undisclosed.

Call it **plausible, not proven**. The instrument (step 1) is worth building
regardless — it is the thing that makes every future reference change decidable.

---

## 3. If IAM credentials cannot be provisioned

Fallbacks, in order of expected value:

1. **Cohere Rerank direct** (not via Bedrock) — same model family
   (`rerank-v3.5`), simple API key. Loses the EU-in-AWS residency story, so it
   needs a data-protection decision first, given this is an EU AI Act product.
2. **A cross-encoder scored by the Stage-2 model itself** — one extra
   wrapper call asking Opus 5 to rank candidate provisions by relevance to the
   question, using text already in the prompt. No new dependency, no new egress,
   and the wrapper is already load-bearing. Costs latency on our worst-but-one
   axis, so it must be measured, but it is buildable **today**.
3. **Do nothing on the ranker and take the Speed axis instead.** Speed is
   −23.5 pp with `complex_thinking_tokens = 4000` as the known driver, and
   Overall is a geometric mean. Cheaper points than the ranker, and no legal risk.

---

## 4. Sequence

```
S0  port gold_dropped_head            instrument — blocks everything else
S1  (concurrent session) R330 §3.1     count blow-out, already in flight
S2  clamp on stage2-ATTEMPTED          closes the 8/40 uncapped rows
S3  provision IAM creds for Rerank     PREREQUISITE, not code
S4  Bedrock Rerank, reorder-only, OFF  the actual ranker
S5  measure Speed separately           independent, cheapest points on the board
```

**Do not start S4 before S0.** Shipping a reference change without
`gold_dropped` is how R142.1 lost a pairwise 11-0.
